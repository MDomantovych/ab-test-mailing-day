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
