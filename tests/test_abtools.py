import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import abtools as ab  # noqa: E402

DATA = ROOT / "data" / "mailing_events.csv"


# ---------------------------------------------------------------- pure functions
def test_split_sql_statements_drops_comments_and_empty():
    text = "-- comment\nSELECT 1;\n\n-- another\nCREATE VIEW v AS SELECT 2;\n"
    assert ab.split_sql_statements(text) == ["SELECT 1", "CREATE VIEW v AS SELECT 2"]


def test_wilson_ci_matches_known_value():
    low, high = ab.wilson_ci(50, 1000)
    assert low == pytest.approx(0.0381, abs=5e-4)
    assert high == pytest.approx(0.0653, abs=5e-4)


def test_two_proportion_test_null_case():
    res = ab.two_proportion_test(100, 2000, 100, 2000)
    assert res.diff == 0
    assert res.p == pytest.approx(1.0)
    assert res.ci_low < 0 < res.ci_high


def test_two_proportion_test_detects_difference():
    res = ab.two_proportion_test(1290, 17710, 995, 17817)
    assert res.diff == pytest.approx(0.0170, abs=1e-4)
    assert res.z == pytest.approx(6.53, abs=0.01)
    assert res.p < 1e-9


def test_srm_test_balanced_split_is_not_flagged():
    _, p = ab.srm_test(17710, 17817)
    assert p > 0.05


def test_srm_test_broken_split_is_flagged():
    _, p = ab.srm_test(12000, 8000)
    assert p < 1e-6


def test_mde_and_sample_size_are_consistent():
    baseline, n = 0.0558, 17710
    mde = ab.mde_absolute(baseline, n)
    assert 0.005 < mde < 0.01
    assert ab.n_per_group_for_lift(baseline, mde) == pytest.approx(n, rel=0.02)


def test_rate_table_sums_to_input():
    df = pd.DataFrame({"g": ["a"] * 6 + ["b"] * 4, "user_id": range(10), "clicked": [1, 0, 0, 1, 0, 0, 1, 1, 0, 0]})
    t = ab.rate_table(df, "g").set_index("g")
    assert t.loc["a", "sent"] == 6 and t.loc["a", "success"] == 2
    assert t.loc["b", "rate"] == pytest.approx(0.5)
    assert (t.ci_low <= t.rate).all() and (t.rate <= t.ci_high).all()


def test_add_neighbour_gaps_ignores_same_touch_pair():
    df = pd.DataFrame({
        "user_id": [1, 1, 1, 2],
        "sent_date": pd.to_datetime(["2021-01-05 14:00:00", "2021-01-05 14:00:10", "2021-01-08 16:00:00", "2021-01-05 14:00:00"]),
    })
    out = ab.add_neighbour_gaps(df)
    # the push sent 10 s after the email is not a separate touch, so the first message's next touch is 3 days later
    assert out.days_to_next.iloc[0] == pytest.approx(3.083, abs=0.01)
    assert out.days_since_prev.iloc[2] == pytest.approx(3.083, abs=0.01)
    assert np.isnan(out.days_since_prev.iloc[3]) and np.isnan(out.days_to_next.iloc[3])


def test_within_user_effect_recovers_simulated_lift():
    # users differ strongly in baseline CTR; the true within-user lift is 3 pp
    rng = np.random.default_rng(0)
    n_users, msgs = 2000, 10
    users = np.repeat(np.arange(n_users), msgs)
    user_base = rng.uniform(0.02, 0.15, n_users)[users]
    treat = rng.integers(0, 2, len(users))
    y = (rng.uniform(size=len(users)) < user_base + 0.03 * treat).astype(int)
    df = pd.DataFrame({"user_id": users, "fri": treat, "clicked": y})
    res = ab.within_user_effect(df, "user_id", "fri", "clicked")
    se = (res["ci_high"] - res["ci_low"]) / 3.92
    assert abs(res["coef"] - 0.03) < 3 * se
    # a few simulated users get the same treatment in all 10 messages and are correctly excluded
    assert 0.99 * n_users <= res["n_users"] <= n_users
    assert res["n_obs"] == res["n_users"] * msgs


def _panel(seed=3, n_users=60, periods=6, effect=0.04):
    rng = np.random.default_rng(seed)
    users = np.repeat(np.arange(n_users), periods)
    weeks = np.tile(np.arange(periods), n_users)
    user_effect = rng.normal(0, 0.05, n_users)[users]
    week_effect = np.linspace(0.06, -0.02, periods)[weeks]
    treat = rng.integers(0, 2, len(users))
    y = 0.10 + user_effect + week_effect + effect * treat + rng.normal(0, 0.05, len(users))
    return pd.DataFrame({"user_id": users, "week": weeks, "fri": treat, "y": y})


def test_two_way_fe_matches_dense_dummy_regression():
    import statsmodels.formula.api as smf
    df = _panel()
    both = df[df.groupby("user_id").fri.transform("nunique") == 2]
    dense = smf.ols("y ~ fri + C(user_id) + C(week)", both).fit()
    res = ab.two_way_fe_effect(df, "user_id", "week", "fri", "y")
    assert res["coef"] == pytest.approx(dense.params["fri"], abs=1e-6)
    assert res["n_obs"] == len(both)


def test_icc_anova_zero_for_iid_and_positive_for_clustered():
    rng = np.random.default_rng(0)
    users = np.repeat(np.arange(300), 10)
    iid = pd.DataFrame({"user_id": users, "y": (rng.uniform(size=len(users)) < 0.1).astype(int)})
    res_iid = ab.icc_anova(iid, "user_id", "y")
    assert res_iid["icc"] < 0.02 and res_iid["deff"] < 1.2
    # user baselines spread over 0..0.8: between-user variance 0.053 vs within ~0.19 -> ICC about 0.2
    base = rng.uniform(0.0, 0.8, 300)[users]
    clustered = pd.DataFrame({"user_id": users, "y": (rng.uniform(size=len(users)) < base).astype(int)})
    res_cl = ab.icc_anova(clustered, "user_id", "y")
    assert res_cl["icc"] > 0.15 and res_cl["deff"] > 2.0
    assert res_cl["avg_cluster_size"] == 10


def test_holm_adjust_known_example():
    out = ab.holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03}).set_index("test")
    assert out.loc["a", "p_holm"] == pytest.approx(0.03)
    assert out.loc["b", "p_holm"] == pytest.approx(0.06)
    assert out.loc["c", "p_holm"] == pytest.approx(0.06)
    assert bool(out.loc["a", "significant_holm"]) and not bool(out.loc["b", "significant_holm"])


def test_heterogeneity_test_detects_interaction():
    rng = np.random.default_rng(5)
    n = 20000
    users = rng.integers(0, 2000, n)
    seg = rng.integers(0, 2, n)
    treat = rng.integers(0, 2, n)
    y_same = (rng.uniform(size=n) < 0.05 + 0.02 * treat).astype(int)
    y_diff = (rng.uniform(size=n) < 0.05 + 0.02 * treat + 0.05 * treat * seg).astype(int)
    df = pd.DataFrame({"user_id": users, "seg": seg, "fri": treat, "y_same": y_same, "y_diff": y_diff})
    same = ab.heterogeneity_test(df, "fri", "seg", "y_same", "user_id")
    diff = ab.heterogeneity_test(df, "fri", "seg", "y_diff", "user_id")
    assert same["n_terms"] == 1 and 0 <= same["p"] <= 1
    assert diff["p"] < 0.001


def test_cuped_reduces_variance_and_keeps_effect_unbiased():
    rng = np.random.default_rng(11)
    n_users, per_user = 1500, 30          # довга історія користувача -> попередній CTR інформативний
    users = np.repeat(np.arange(n_users), per_user)
    base = rng.uniform(0.02, 0.20, n_users)[users]           # користувацький рівень схильності до кліку
    treat = rng.integers(0, 2, len(users))
    y = (rng.uniform(size=len(users)) < base + 0.02 * treat).astype(int)
    df = pd.DataFrame({"user_id": users, "fri": treat, "clicked": y})
    # коваріата: попередній CTR користувача (без поточного спостереження); перше спостереження -> NaN
    df["msg_no"] = df.groupby("user_id").cumcount() + 1
    df["prior_ctr"] = ((df.groupby("user_id").clicked.cumsum() - df.clicked) / (df.msg_no - 1)).where(df.msg_no > 1)
    res = ab.cuped_effect(df, "user_id", "fri", "clicked", "prior_ctr")
    assert 0 < res["variance_reduction"] < 1 and res["corr"] > 0.03   # бінарний результат: кореляція з попереднім CTR невелика, але додатна
    assert res["ci_low"] < 0.02 < res["ci_high"]                       # ефект не зсувається
    assert res["covariate_missing_share"] == pytest.approx(1 / per_user)
    # на незалежних спостереженнях (без кластерів) CUPED має зменшувати SE
    iid = pd.DataFrame({"user_id": np.arange(20000), "fri": rng.integers(0, 2, 20000)})
    x = rng.normal(size=20000)
    iid["clicked"] = (rng.uniform(size=20000) < 0.1 + 0.03 * x.clip(-2, 2) + 0.02 * iid.fri).astype(int)
    iid["x"] = x
    res_iid = ab.cuped_effect(iid, "user_id", "fri", "clicked", "x")
    assert res_iid["se_cuped"] < res_iid["se_raw"]


# ---------------------------------------------------------------- integration with the real log
@pytest.mark.skipif(not DATA.exists(), reason="raw log not present")
def test_observation_table_matches_report_numbers():
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW events AS SELECT * FROM read_csv_auto('{DATA.as_posix()}')")
    ab.run_sql_file(con, ROOT / "sql" / "01_observations.sql")
    obs = con.execute("SELECT send_day, clicked FROM observations").df()
    assert len(obs) == 35527
    res = ab.compare_groups(obs, "send_day", "friday", "tuesday")
    assert res.n_a == 17710 and res.n_b == 17817
    assert res.rate_a == pytest.approx(0.0728, abs=1e-4)
    assert res.rate_b == pytest.approx(0.0558, abs=1e-4)
