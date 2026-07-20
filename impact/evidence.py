"""Evidence-layer primitives (SPEC layer: player evidence card, `docs/mustermann.md`).

Per-90 rates, exposure-aware Gamma-Poisson shrinkage, and domestic
percentiles for count metrics (npxG, xA, progression, defensive actions...).
This module does NOT decide whether these features improve any predictor —
it only implements the falsifiable pieces so `docs/mustermann.md` §7 can
report what was tested.

REWRITE NOTE (external review, reproduced independently before this rewrite):
the original shrinkage weight used `k = within-cell variance of the per-90
rate / between-cell variance of cell means` and `w = minutes/(minutes+k)`.
That `k` is a dimensionless ratio of two variances measured on different
things (individual-player dispersion vs. cell-mean dispersion) — nothing
ties it to a "number of minutes" scale, so `minutes+k` was adding a minutes
count to a unitless number. The self-check only verified *direction*
(shrinks toward the mean, more minutes -> less shrinkage), never whether
the resulting interval had correct coverage. Both are fixed here:

- Shrinkage is now a proper Gamma-Poisson (negative-binomial) conjugate
  model on RAW COUNTS and MINUTES, not the already-divided rate. Exposure
  is `minutes/90`; the prior's pseudo-exposure `beta` is estimated in the
  same units via method-of-moments, so `exposure + beta` is dimensionally
  a sum of two "count of 90-minute blocks" — the thing the original code
  was trying to do, done with matching units.
- The card's interval is now an exact posterior credible interval for the
  PLAYER's own rate (Monte Carlo draws from the closed-form Gamma
  posterior), not a bootstrap of the cohort's mean. The old
  `interval_lo/interval_hi` was a cohort reference range mislabeled as
  player uncertainty; `EvidenceCard` below keeps both, separately named.
- `_check()` now includes a simulation-based coverage test: simulate known
  true rates, check the posterior interval's empirical coverage is close
  to its nominal level, not just that it moves the right direction.

    python3 -m impact.evidence      # offline self-check
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CELL = ["role", "league", "season"]
MIN_EXPOSURE_90 = 1e-6  # floor to avoid division by zero for a 0-minute row


def per90(raw: pd.Series, minutes: pd.Series) -> pd.Series:
    """90 * raw / minutes. Only for count metrics — never call this on a
    field that is already a rate, a percentage, or a share (see
    `docs/mustermann.md` §1)."""
    return np.where(minutes > 0, 90.0 * raw / minutes, np.nan)


class GammaPoissonShrinkage:
    """Exposure-aware empirical-Bayes shrinkage for a count metric.

    Model: raw_i | rate_i ~ Poisson(rate_i * exposure_i), exposure_i =
    minutes_i / 90. Prior: rate ~ Gamma(alpha, beta) within each
    (role, league, season) cell, fit by method of moments from the
    training fold ONLY. Posterior: Gamma(alpha + raw_i, beta + exposure_i).

    `fit()` must only ever see the training fold; `transform()`/`posterior()`
    can be applied to any rows once fit. This split is the whole point — a
    prior fit on rows that include the evaluation fold is leakage.
    """

    def __init__(self):
        self.cell_mu_: pd.Series | None = None       # prior mean rate per cell
        self.cell_beta_: pd.Series | None = None      # prior pseudo-exposure (90-min blocks) per cell
        self.global_mu_: float | None = None
        self.global_beta_: float | None = None

    def fit(self, df: pd.DataFrame, raw_col: str, minutes_col: str = "minutes") -> "GammaPoissonShrinkage":
        d = df.copy()
        d["_exposure90"] = np.maximum(d[minutes_col] / 90.0, MIN_EXPOSURE_90)
        d["_rate"] = d[raw_col] / d["_exposure90"]

        def moments(g: pd.DataFrame) -> pd.Series:
            mu = np.average(g["_rate"], weights=g["_exposure90"])
            # Var(rate_hat) = tau^2 (true dispersion) + mu * E[1/exposure] (Poisson sampling noise)
            sampling_term = mu * np.mean(1.0 / g["_exposure90"])
            observed_var = np.var(g["_rate"], ddof=1) if len(g) > 1 else sampling_term
            tau2 = max(observed_var - sampling_term, 1e-9)
            beta = mu / tau2  # prior pseudo-exposure, in 90-minute-block units
            return pd.Series({"mu": mu, "beta": beta})

        cell_stats = d.groupby(CELL).apply(moments, include_groups=False)
        self.cell_mu_ = cell_stats["mu"]
        self.cell_beta_ = cell_stats["beta"]
        g_mu = np.average(d["_rate"], weights=d["_exposure90"])
        g_sampling = g_mu * np.mean(1.0 / d["_exposure90"])
        g_tau2 = max(np.var(d["_rate"], ddof=1) - g_sampling, 1e-9)
        self.global_mu_ = g_mu
        self.global_beta_ = g_mu / g_tau2
        return self

    def _cell_prior(self, row: pd.Series) -> tuple[float, float]:
        key = tuple(row[c] for c in CELL)
        mu = self.cell_mu_.get(key, self.global_mu_)
        beta = self.cell_beta_.get(key, self.global_beta_)
        if pd.isna(mu) or pd.isna(beta) or beta <= 0:
            mu, beta = self.global_mu_, self.global_beta_
        return float(mu), float(beta)

    def posterior_params(self, df: pd.DataFrame, raw_col: str, minutes_col: str = "minutes") -> pd.DataFrame:
        """Returns alpha_post, beta_post per row — the full Gamma posterior,
        not just its mean. Use `posterior_mean` / `posterior_interval` below.

        Vectorized via a merge on CELL rather than a Python-level per-row
        loop — this needs to run over tens of thousands of rows (e.g. all
        of `fbref_perf`) in the V3 sporting-evidence pipeline."""
        assert self.cell_mu_ is not None, "call fit() on a training fold first"
        exposure90 = np.maximum(df[minutes_col] / 90.0, MIN_EXPOSURE_90)
        cell_stats = pd.DataFrame({"mu": self.cell_mu_, "beta": self.cell_beta_})
        joined = df[CELL].merge(cell_stats, left_on=CELL, right_index=True, how="left")
        mu = joined["mu"].fillna(self.global_mu_).to_numpy()
        beta_prior = joined["beta"].fillna(self.global_beta_).to_numpy()
        bad = ~np.isfinite(beta_prior) | (beta_prior <= 0)
        mu[bad] = self.global_mu_
        beta_prior[bad] = self.global_beta_
        alpha_prior = mu * beta_prior
        alpha_post = alpha_prior + df[raw_col].to_numpy()
        beta_post = beta_prior + exposure90.to_numpy()
        return pd.DataFrame({"alpha_post": alpha_post, "beta_post": beta_post}, index=df.index)

    def posterior_mean(self, df: pd.DataFrame, raw_col: str, minutes_col: str = "minutes") -> pd.Series:
        p = self.posterior_params(df, raw_col, minutes_col)
        return p.alpha_post / p.beta_post

    def posterior_interval(self, row: pd.Series, alpha_post: float, beta_post: float,
                            level: float = 0.90, n_draws: int = 5000, seed: int = 0) -> tuple[float, float]:
        """Monte Carlo credible interval for the PLAYER's own rate, drawn
        exactly from the closed-form Gamma posterior (not a cohort bootstrap)."""
        rng = np.random.default_rng(seed)
        draws = rng.gamma(shape=alpha_post, scale=1.0 / beta_post, size=n_draws)
        tail = (1 - level) / 2
        return float(np.percentile(draws, 100 * tail)), float(np.percentile(draws, 100 * (1 - tail)))


def shrink_per90(train: pd.DataFrame, apply_to: pd.DataFrame, raw_col: str, minutes_col: str = "minutes") -> pd.Series:
    """Convenience wrapper: fit on `train`'s raw counts/minutes, return the
    posterior mean rate (per-90) for `apply_to`."""
    prior = GammaPoissonShrinkage().fit(train, raw_col, minutes_col)
    return prior.posterior_mean(apply_to, raw_col, minutes_col)


def domestic_percentile(df: pd.DataFrame, value_col: str, min_low: int = 20,
                         min_moderate: int = 50, min_high: int = 100) -> pd.DataFrame:
    """Rank within role x competition(league) x season. Cohort confidence
    tiers (task's revised defaults): <20 unavailable, 20-49 low, 50-99
    moderate, 100+ high descriptive support. A raw percentile number is
    never reported without its tier."""
    out = df.copy()
    g = out.groupby(CELL)
    out["cohort_size"] = g[value_col].transform("size")
    out["domestic_percentile"] = g[value_col].rank(pct=True) * 100

    def tier(n: int) -> str:
        if n < min_low:
            return "unavailable"
        if n < min_moderate:
            return "low"
        if n < min_high:
            return "moderate"
        return "high"

    out["cohort_confidence"] = out.cohort_size.map(tier)
    out.loc[out.cohort_confidence == "unavailable", "domestic_percentile"] = np.nan
    return out


@dataclass
class EvidenceCard:
    player: str
    metric: str
    raw_total: float
    minutes: float
    exposure_status: str       # observed | unknown
    per90: float | None        # None if exposure_status == "unknown" — never fabricated
    shrunk_per90: float | None
    domestic_percentile: float | None
    cohort_size: int
    cohort_confidence: str     # unavailable | low | moderate | high
    support_flag: str          # in_distribution | low_minutes | unknown_exposure | out_of_cohort
    player_interval_lo: float | None   # posterior credible interval for THIS player's rate
    player_interval_hi: float | None
    cohort_reference_lo: float | None  # separately: the cohort's own descriptive spread (NOT player uncertainty)
    cohort_reference_hi: float | None
    cutoff_date: str
    adjusted_global_percentile: float | None = None  # None: no supported translation (mustermann.md §4)


def support_flag(minutes, cohort_size: int, low_minutes_threshold: float = 900,
                  min_cohort: int = 20) -> str:
    """Fixed: unknown exposure (NaN minutes) is its own category, never
    silently falls through to "in_distribution" (the original bug — NaN
    comparisons are always False in Python/numpy, so `minutes < threshold`
    was False for NaN and the function returned the highest-confidence
    label for a player with no known minutes at all)."""
    if minutes is None or (isinstance(minutes, float) and np.isnan(minutes)):
        return "unknown_exposure"
    if cohort_size < min_cohort:
        return "out_of_cohort"
    if minutes < low_minutes_threshold:
        return "low_minutes"
    return "in_distribution"


def build_evidence_card(train: pd.DataFrame, row: pd.Series, raw_col: str,
                         min_cohort: int = 20, low_minutes_threshold: float = 900) -> EvidenceCard:
    """train: prior-fold rows (raw counts + minutes) used to fit the
    shrinkage prior and cohort percentile. row: the single player-season
    snapshot being cardified (needs raw_col, minutes, role, league, season)."""
    minutes = row.get("minutes", np.nan)
    exposure_status = "unknown" if pd.isna(minutes) else "observed"
    flag = support_flag(minutes, len(train[(train.role == row.get("role")) &
                                            (train.league == row.get("league")) &
                                            (train.season == row.get("season"))]),
                         low_minutes_threshold, min_cohort)

    cohort = train[(train.role == row.get("role")) & (train.league == row.get("league")) & (train.season == row.get("season"))]
    cohort_size = len(cohort)

    if exposure_status == "unknown":
        # Never fabricate a per-90 rate or a shrunk estimate from unknown exposure.
        return EvidenceCard(
            player=row.get("player", "?"), metric=raw_col, raw_total=float(row.get(raw_col, np.nan)),
            minutes=np.nan, exposure_status="unknown", per90=None, shrunk_per90=None,
            domestic_percentile=None, cohort_size=cohort_size, cohort_confidence="unavailable",
            support_flag="unknown_exposure", player_interval_lo=None, player_interval_hi=None,
            cohort_reference_lo=None, cohort_reference_hi=None, cutoff_date=str(row.get("cutoff_date", "?")),
        )

    prior = GammaPoissonShrinkage().fit(train, raw_col)
    post = prior.posterior_params(pd.DataFrame([row]), raw_col).iloc[0]
    shrunk = float(post.alpha_post / post.beta_post)
    p_lo, p_hi = prior.posterior_interval(row, post.alpha_post, post.beta_post)

    cohort_rate = per90(cohort[raw_col], cohort["minutes"]) if cohort_size else np.array([])
    cohort_rate = cohort_rate[~np.isnan(cohort_rate)] if len(cohort_rate) else cohort_rate
    if len(cohort_rate) >= 2:
        c_lo, c_hi = float(np.percentile(cohort_rate, 5)), float(np.percentile(cohort_rate, 95))
    else:
        c_lo = c_hi = None

    def conf_tier(n: int) -> str:
        if n < 20:
            return "unavailable"
        if n < 50:
            return "low"
        if n < 100:
            return "moderate"
        return "high"

    return EvidenceCard(
        player=row.get("player", "?"), metric=raw_col, raw_total=float(row.get(raw_col, np.nan)),
        minutes=float(minutes), exposure_status="observed",
        per90=float(90.0 * row[raw_col] / minutes),
        shrunk_per90=shrunk,
        domestic_percentile=(float((cohort_rate < shrunk).mean() * 100) if len(cohort_rate) >= 20 else None),
        cohort_size=cohort_size, cohort_confidence=conf_tier(cohort_size), support_flag=flag,
        player_interval_lo=p_lo, player_interval_hi=p_hi,
        cohort_reference_lo=c_lo, cohort_reference_hi=c_hi,
        cutoff_date=str(row.get("cutoff_date", "?")),
    )


def _check():
    rng = np.random.default_rng(0)

    # --- simulate a known ground truth: 2 role x league x season cells, true rates
    # drawn from a known Gamma, counts drawn from Poisson(true_rate * exposure). ---
    rows = []
    true_rates = {}
    for role in ["FW", "MF"]:
        for season in ["2021-2022", "2022-2023"]:
            cell_mu = 0.4 if role == "FW" else 0.2
            cell_shape = 6.0  # true between-player Gamma shape for this cell
            for i in range(60):
                true_rate = rng.gamma(shape=cell_shape, scale=cell_mu / cell_shape)
                minutes = rng.uniform(90, 3000)
                exposure90 = minutes / 90
                raw = rng.poisson(true_rate * exposure90)
                rows.append(dict(player=f"{role}{season}_{i}", role=role, league="L1", season=season,
                                  minutes=minutes, raw=float(raw), true_rate=true_rate))
    df = pd.DataFrame(rows)

    # unknown-exposure rows must never reach per90/shrinkage as if they were 0-minute
    unknown_row = df.iloc[0].copy()
    unknown_row["minutes"] = np.nan
    assert support_flag(unknown_row.minutes, 60) == "unknown_exposure", \
        "NaN minutes must be its own category, not silently in_distribution"
    assert support_flag(0.0, 60) == "low_minutes", "0 minutes is a known (low) exposure, distinct from unknown"

    # --- fold split, fit on train only ---
    train, test = df.iloc[:180].copy(), df.iloc[180:].copy()
    prior = GammaPoissonShrinkage().fit(train, "raw")

    # fold safety: fit() on train must differ from a fit on train+test
    leaked = GammaPoissonShrinkage().fit(pd.concat([train, test]), "raw")
    assert not prior.cell_mu_.equals(leaked.cell_mu_), "fit() must differ from a fit on train+test"

    # shrinkage direction: a low-minute player's posterior mean sits between
    # his raw rate and the cell's prior mean (monotone shrinkage property of
    # a proper conjugate posterior).
    low_row = test.iloc[0].copy()
    low_row["minutes"] = 90.0
    low_row["raw"] = 3.0  # a big spike off one 90-minute cameo
    raw_rate = low_row.raw / (low_row.minutes / 90)
    cell_mu, _ = prior._cell_prior(low_row)
    post = prior.posterior_params(pd.DataFrame([low_row]), "raw").iloc[0]
    shrunk = post.alpha_post / post.beta_post
    lo, hi = sorted([cell_mu, raw_rate])
    assert lo <= shrunk <= hi, (shrunk, lo, hi)

    hi_row = low_row.copy()
    hi_row["minutes"] = 3000.0
    hi_row["raw"] = float(round(raw_rate * 3000 / 90))
    post_hi = prior.posterior_params(pd.DataFrame([hi_row]), "raw").iloc[0]
    shrunk_hi = post_hi.alpha_post / post_hi.beta_post
    assert abs(shrunk_hi - raw_rate) < abs(shrunk - raw_rate), \
        "more minutes must mean less shrinkage toward the prior"

    # --- calibration test: does the posterior credible interval have
    # approximately correct empirical coverage against the KNOWN true_rate? ---
    hits = 0
    n_test = 0
    for _, row in test.iterrows():
        if row.minutes < 30:
            continue  # near-zero exposure makes the Gamma posterior degenerate; skip, don't test
        post = prior.posterior_params(pd.DataFrame([row]), "raw").iloc[0]
        lo, hi = prior.posterior_interval(row, post.alpha_post, post.beta_post, level=0.80, n_draws=2000)
        hits += lo <= row.true_rate <= hi
        n_test += 1
    coverage = hits / n_test
    assert 0.65 <= coverage <= 0.95, f"80% interval coverage way off nominal: {coverage:.2f} (n={n_test})"

    # percentile: tiny cohort must abstain (None), not fabricate a rank
    tiny = df.head(5).copy()
    tiny["role"], tiny["league"], tiny["season"] = "GK", "L1", "2099-2100"
    tiny["rate90"] = per90(tiny.raw, tiny.minutes)
    dperc = domestic_percentile(pd.concat([df.assign(rate90=per90(df.raw, df.minutes)), tiny]), "rate90")
    assert dperc.loc[dperc.role == "GK", "domestic_percentile"].isna().all(), \
        "a 5-player cohort must not receive a percentile"
    assert (dperc.loc[dperc.role == "GK", "cohort_confidence"] == "unavailable").all()
    assert dperc.loc[dperc.role == "FW", "cohort_confidence"].isin(["moderate", "high"]).any()

    # evidence card end to end, including the unknown-exposure path
    row = test.iloc[1].copy()
    row["cutoff_date"] = "2023-06-30"
    card = build_evidence_card(train, row, "raw")
    assert card.adjusted_global_percentile is None, "no supported league translation yet (mustermann.md §4)"
    assert card.player_interval_lo <= card.shrunk_per90 <= card.player_interval_hi
    assert card.support_flag != "unknown_exposure"

    unk_row = row.copy()
    unk_row["minutes"] = np.nan
    unk_card = build_evidence_card(train, unk_row, "raw")
    assert unk_card.support_flag == "unknown_exposure"
    assert unk_card.per90 is None and unk_card.shrunk_per90 is None, \
        "unknown exposure must never produce a fabricated per-90 or shrunk estimate"

    print(f"ok — per90, exposure-aware Gamma-Poisson shrinkage (fold-safe, monotone in minutes), "
          f"80% interval coverage {coverage:.2f} on simulation, unknown-exposure abstention, "
          f"cohort confidence tiers, evidence card")


if __name__ == "__main__":
    _check()
