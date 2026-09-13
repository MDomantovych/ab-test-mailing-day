"""Reusable helpers for the mailing-day A/B analysis.

Everything here is plain pandas / numpy / scipy / statsmodels. The notebook imports
these functions so that the analytical logic is testable outside Jupyter.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from scipy.optimize import brentq
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_confint, proportion_effectsize, proportions_ztest


# --------------------------------------------------------------------------- SQL helpers
def split_sql_statements(text: str) -> list[str]:
    """Split a .sql file into executable statements, dropping full-line comments."""
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    return [stmt.strip() for stmt in body.split(";") if stmt.strip()]


def run_sql_file(con, path) -> list[pd.DataFrame]:
    """Execute every statement in a .sql file; return DataFrames for SELECT / WITH statements."""
    text = open(path, encoding="utf-8").read()
    frames = []
    for stmt in split_sql_statements(text):
        result = con.execute(stmt)
        if stmt.upper().startswith(("SELECT", "WITH")):
            frames.append(result.df())
    return frames


# --------------------------------------------------------------------------- proportions
def wilson_ci(successes: int, trials: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    low, high = proportion_confint(successes, trials, alpha=alpha, method="wilson")
    return float(low), float(high)


def rate_table(df: pd.DataFrame, by, y: str = "clicked", user_col: str = "user_id") -> pd.DataFrame:
    """Sends, unique users, successes, rate and Wilson CI per group."""
    grouped = df.groupby(by)
    table = grouped.agg(sent=(y, "size"), users=(user_col, "nunique"), success=(y, "sum")).reset_index()
    table["rate"] = table.success / table.sent
    bounds = [wilson_ci(int(s), int(n)) for s, n in zip(table.success, table.sent)]
    table["ci_low"] = [b[0] for b in bounds]
    table["ci_high"] = [b[1] for b in bounds]
    return table


@dataclass
class TwoProportionResult:
    rate_a: float
    rate_b: float
    diff: float
    ci_low: float
    ci_high: float
    z: float
    p: float
    n_a: int
    n_b: int

    @property
    def relative(self) -> float:
        return self.diff / self.rate_b


def two_proportion_test(success_a: int, n_a: int, success_b: int, n_b: int) -> TwoProportionResult:
    """Two-sided z-test for p_a - p_b with a Wald CI for the difference."""
    p_a, p_b = success_a / n_a, success_b / n_b
    z, p = proportions_ztest([success_a, success_b], [n_a, n_b])
    se = np.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    diff = p_a - p_b
    return TwoProportionResult(p_a, p_b, diff, diff - 1.96 * se, diff + 1.96 * se, float(z), float(p), n_a, n_b)


def compare_groups(df: pd.DataFrame, group_col: str, a: str, b: str, y: str = "clicked") -> TwoProportionResult:
    """Convenience wrapper: z-test of y between group_col == a and group_col == b."""
    counts = df.groupby(group_col)[y].agg(["sum", "size"])
    return two_proportion_test(int(counts.loc[a, "sum"]), int(counts.loc[a, "size"]),
                               int(counts.loc[b, "sum"]), int(counts.loc[b, "size"]))


# --------------------------------------------------------------------------- design checks
def srm_test(n_a: int, n_b: int, expected_share_a: float = 0.5) -> tuple[float, float]:
    """Chi-square goodness-of-fit for the group split (Sample Ratio Mismatch)."""
    total = n_a + n_b
    chi2, p = stats.chisquare([n_a, n_b], f_exp=[total * expected_share_a, total * (1 - expected_share_a)])
    return float(chi2), float(p)


def mde_absolute(baseline: float, n_per_group: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """Minimum detectable absolute lift (in proportion units) for a two-sample proportion test."""
    es = NormalIndPower().solve_power(nobs1=n_per_group, alpha=alpha, power=power, ratio=1.0)
    target = brentq(lambda p1: proportion_effectsize(p1, baseline) - es, baseline, 0.999)
    return float(target - baseline)


def n_per_group_for_lift(baseline: float, lift: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Sample size per group needed to detect an absolute lift with given power."""
    es = proportion_effectsize(baseline + lift, baseline)
    return float(NormalIndPower().solve_power(effect_size=es, alpha=alpha, power=power, ratio=1.0))


# --------------------------------------------------------------------------- dependence-aware estimates
def cluster_bootstrap_diff(df: pd.DataFrame, user_col: str, treat_col: str, y: str,
                           n_boot: int = 2000, seed: int = 42) -> dict:
    """Resample users (clusters) with replacement; return bootstrap distribution summary of rate(treat=1) - rate(treat=0)."""
    per_user = df.groupby(user_col).apply(
        lambda g: pd.Series({
            "n1": (g[treat_col] == 1).sum(), "x1": g.loc[g[treat_col] == 1, y].sum(),
            "n0": (g[treat_col] == 0).sum(), "x0": g.loc[g[treat_col] == 0, y].sum(),
        }), include_groups=False).values.astype(float)
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        sample = per_user[rng.integers(0, len(per_user), len(per_user))].sum(axis=0)
        diffs[i] = sample[1] / sample[0] - sample[3] / sample[2]
    low, high = np.percentile(diffs, [2.5, 97.5])
    return {"mean": float(diffs.mean()), "ci_low": float(low), "ci_high": float(high),
            "share_below_zero": float((diffs <= 0).mean()), "n_boot": n_boot}


def clustered_lpm(df: pd.DataFrame, formula: str, user_col: str, term: str = "fri") -> dict:
    """Linear probability model with user-clustered standard errors; returns the coefficient of `term`."""
    model = smf.ols(formula, df).fit(cov_type="cluster", cov_kwds={"groups": df[user_col]})
    ci = model.conf_int().loc[term]
    return {"coef": float(model.params[term]), "ci_low": float(ci[0]), "ci_high": float(ci[1]),
            "p": float(model.pvalues[term]), "model": model}


def within_user_effect(df: pd.DataFrame, user_col: str, treat_col: str, y: str) -> dict:
    """Fixed-effects (within-user) estimate: demean y and treatment inside each user, regress without intercept."""
    both = df[df.groupby(user_col)[treat_col].transform("nunique") == 2].copy()
    both["_y_dm"] = both[y] - both.groupby(user_col)[y].transform("mean")
    both["_t_dm"] = both[treat_col] - both.groupby(user_col)[treat_col].transform("mean")
    model = smf.ols("_y_dm ~ _t_dm - 1", both).fit(cov_type="cluster", cov_kwds={"groups": both[user_col]})
    ci = model.conf_int().loc["_t_dm"]
    return {"coef": float(model.params["_t_dm"]), "ci_low": float(ci[0]), "ci_high": float(ci[1]),
            "p": float(model.pvalues["_t_dm"]), "n_users": int(both[user_col].nunique()), "n_obs": len(both)}


def paired_weekly_effect(df: pd.DataFrame, week_col: str, treat_col: str, y: str) -> dict:
    """Treat each week as a pair (rate under treat=1 minus rate under treat=0); t-test and sign test."""
    weekly = df.groupby([week_col, treat_col])[y].mean().unstack().dropna()
    diffs = weekly[1] - weekly[0]
    t, p = stats.ttest_rel(weekly[1], weekly[0])
    half = stats.t.ppf(0.975, len(diffs) - 1) * diffs.std(ddof=1) / np.sqrt(len(diffs))
    wins = int((diffs > 0).sum())
    return {"mean": float(diffs.mean()), "ci_low": float(diffs.mean() - half), "ci_high": float(diffs.mean() + half),
            "p": float(p), "weeks": len(diffs), "wins": wins,
            "sign_test_p": float(stats.binomtest(wins, len(diffs)).pvalue), "table": weekly}


# --------------------------------------------------------------------------- message sequence
def add_neighbour_gaps(df: pd.DataFrame, user_col: str = "user_id", ts_col: str = "sent_date",
                       min_gap_days: int = 1) -> pd.DataFrame:
    """Add days_since_prev / days_to_next: gap to the nearest other message of the same user
    that is more than `min_gap_days` away (so an email+push pair sent seconds apart is one touch)."""
    out = df.sort_values([user_col, ts_col]).copy()
    gap = np.timedelta64(min_gap_days, "D")
    prev_gap = np.full(len(out), np.nan)
    next_gap = np.full(len(out), np.nan)
    pos = 0
    for _, g in out.groupby(user_col, sort=False):
        s = g[ts_col].values
        for i in range(len(s)):
            earlier = s[s < s[i] - gap]
            later = s[s > s[i] + gap]
            if len(earlier):
                prev_gap[pos + i] = (s[i] - earlier.max()) / np.timedelta64(1, "D")
            if len(later):
                next_gap[pos + i] = (later.min() - s[i]) / np.timedelta64(1, "D")
        pos += len(s)
    out["days_since_prev"] = prev_gap
    out["days_to_next"] = next_gap
    return out
