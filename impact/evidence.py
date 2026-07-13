"""Evidence-layer primitives (SPEC layer: player evidence card, `docs/mustermann.md`).

Per-90 rates, fold-safe empirical-Bayes shrinkage, and domestic percentiles
for count metrics (npxG, xA, progression, defensive actions...). This module
does NOT decide whether these features improve any predictor — it only
implements the falsifiable pieces so §7 of `docs/mustermann.md` can report
what was tested. Percentiles and raw per-90 rates are presentation by
default; `shrink_per90` is the one piece with a fold-safe fit/transform
split because it is a legitimate model-feature candidate.

    python3 -m impact.evidence      # offline self-check
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CELL = ["role", "league", "season"]


def per90(raw: pd.Series, minutes: pd.Series) -> pd.Series:
    """90 * raw / minutes. Only for count metrics — never call this on a
    field that is already a rate, a percentage, or a share (see
    `docs/mustermann.md` §1)."""
    return np.where(minutes > 0, 90.0 * raw / minutes, np.nan)


class ShrinkagePrior:
    """Fold-safe empirical-Bayes shrinkage toward the (role, league, season)
    mean. `fit()` must only ever see the training fold; `transform()` can be
    applied to any rows once fit. This split is the whole point — a prior
    fit on rows that include the evaluation fold is leakage."""

    def __init__(self, k: float | None = None):
        self.k = k          # shrinkage strength; None until fit
        self.cell_mean_: pd.Series | None = None
        self.global_mean_: float | None = None

    def fit(self, df: pd.DataFrame, value_col: str, weight_col: str = "minutes") -> "ShrinkagePrior":
        g = df.groupby(CELL)
        self.cell_mean_ = g[value_col].mean()
        self.global_mean_ = df[value_col].mean()
        # k = median within-cell variance / between-cell variance, floored — cells
        # with noisier evidence get shrunk harder toward the wider prior.
        within_var = g[value_col].var().median()
        between_var = self.cell_mean_.var()
        self.k = float(within_var / between_var) if between_var and between_var > 0 else 50.0
        self.k = max(self.k, 1.0)
        return self

    def transform(self, df: pd.DataFrame, value_col: str, weight_col: str = "minutes") -> pd.Series:
        assert self.cell_mean_ is not None, "call fit() on a training fold first"
        prior = df[CELL].apply(tuple, axis=1).map(self.cell_mean_).fillna(self.global_mean_)
        w = df[weight_col] / (df[weight_col] + self.k)
        return w * df[value_col] + (1 - w) * prior


def shrink_per90(train: pd.DataFrame, apply_to: pd.DataFrame, value_col: str) -> pd.Series:
    """Convenience wrapper: fit on `train`, transform `apply_to`. Both frames
    need CELL + value_col + minutes columns."""
    prior = ShrinkagePrior().fit(train, value_col)
    return prior.transform(apply_to, value_col)


def domestic_percentile(df: pd.DataFrame, value_col: str, min_cohort: int = 20) -> pd.DataFrame:
    """Rank within role x competition(league) x season. Cohorts smaller than
    `min_cohort` are flagged, not silently ranked — a percentile within 6
    players is not a percentile."""
    out = df.copy()
    g = out.groupby(CELL)
    out["cohort_size"] = g[value_col].transform("size")
    out["domestic_percentile"] = g[value_col].rank(pct=True) * 100
    out.loc[out.cohort_size < min_cohort, "domestic_percentile"] = np.nan
    return out


@dataclass
class EvidenceCard:
    player: str
    metric: str
    raw_total: float
    minutes: float
    per90: float
    shrunk_per90: float
    domestic_percentile: float | None
    cohort_size: int
    support_flag: str          # in_distribution | low_minutes | out_of_cohort
    interval_lo: float
    interval_hi: float
    cutoff_date: str
    adjusted_global_percentile: float | None = None  # None: no supported translation (mustermann.md §4)


def support_flag(minutes: float, cohort_size: int, low_minutes_threshold: float = 900,
                  min_cohort: int = 20) -> str:
    if cohort_size < min_cohort:
        return "out_of_cohort"
    if minutes < low_minutes_threshold:
        return "low_minutes"
    return "in_distribution"


def bootstrap_interval(values: np.ndarray, n_boot: int = 500, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    if len(values) < 2:
        v = float(values[0]) if len(values) else np.nan
        return v, v
    boots = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(n_boot)]
    return float(np.percentile(boots, 5)), float(np.percentile(boots, 95))


def build_evidence_card(train: pd.DataFrame, row: pd.Series, value_col: str,
                         min_cohort: int = 20, low_minutes_threshold: float = 900) -> EvidenceCard:
    """train: prior-fold rows used to fit the shrinkage prior and cohort
    percentile. row: the single player-season snapshot being cardified."""
    prior = ShrinkagePrior().fit(train, value_col)
    shrunk = float(prior.transform(pd.DataFrame([row]), value_col).iloc[0])
    cohort = train[(train.role == row.role) & (train.league == row.league) & (train.season == row.season)]
    cohort_size = len(cohort)
    pct = (float((cohort[value_col] < row[value_col]).mean()) * 100) if cohort_size >= min_cohort else None
    lo, hi = bootstrap_interval(cohort[value_col].to_numpy()) if cohort_size >= 2 else (shrunk, shrunk)
    return EvidenceCard(
        player=row.get("player", "?"),
        metric=value_col,
        raw_total=float(row.get(f"{value_col}_raw", row[value_col])),
        minutes=float(row.minutes),
        per90=float(row[value_col]),
        shrunk_per90=shrunk,
        domestic_percentile=pct,
        cohort_size=cohort_size,
        support_flag=support_flag(row.minutes, cohort_size, low_minutes_threshold, min_cohort),
        interval_lo=lo, interval_hi=hi,
        cutoff_date=str(row.get("cutoff_date", "?")),
    )


def _check():
    rng = np.random.default_rng(0)
    # 3 role x league x season cells, 30 players each, one deliberately low-minutes.
    rows = []
    for role in ["FW", "MF"]:
        for season in ["2021-2022", "2022-2023"]:
            true_mean = 0.4 if role == "FW" else 0.2
            for i in range(30):
                minutes = rng.uniform(200, 2500)
                raw = max(0.0, rng.normal(true_mean, 0.15)) * minutes / 90
                rows.append(dict(player=f"{role}{season}_{i}", role=role, league="L1",
                                  season=season, minutes=minutes))
                rows[-1]["npxg_raw"] = raw
    df = pd.DataFrame(rows)
    df["npxg_p90"] = per90(df.npxg_raw, df.minutes)

    # per90 basic correctness
    assert np.isclose(df.npxg_p90.iloc[0], 90 * df.npxg_raw.iloc[0] / df.minutes.iloc[0])

    # shrinkage: a low-minute player's shrunk estimate must sit strictly between
    # his raw per-90 and the cell mean (never outside that range).
    train, test = df.iloc[:100].copy(), df.iloc[100:].copy()
    low_row = test.iloc[0].copy()
    low_row["minutes"] = 90.0  # one 90-minute cameo -> should shrink hard
    low_row["npxg_p90"] = 3.0  # implausible single-game spike
    cell_mean = train[(train.role == low_row.role) & (train.league == "L1") &
                       (train.season == low_row.season)].npxg_p90.mean()
    shrunk = shrink_per90(train, pd.DataFrame([low_row]), "npxg_p90").iloc[0]
    lo, hi = sorted([cell_mean, low_row.npxg_p90])
    assert lo <= shrunk <= hi, (shrunk, lo, hi)
    assert abs(shrunk - cell_mean) < abs(low_row.npxg_p90 - cell_mean), \
        "a 90-minute cameo must shrink toward the prior, not stay near its raw value"

    # a high-minutes player shrinks much less than a low-minutes player with the same raw value
    hi_row = low_row.copy()
    hi_row["minutes"] = 3000.0
    shrunk_hi = shrink_per90(train, pd.DataFrame([hi_row]), "npxg_p90").iloc[0]
    assert abs(shrunk_hi - low_row.npxg_p90) < abs(shrunk - low_row.npxg_p90), \
        "more minutes must mean less shrinkage toward the prior"

    # fold safety: fitting on train must not see test rows' values
    prior = ShrinkagePrior().fit(train, "npxg_p90")
    assert not train.equals(pd.concat([train, test])), "sanity: test rows exist"
    leaked_mean = pd.concat([train, test]).groupby(CELL).npxg_p90.mean()
    assert not prior.cell_mean_.equals(leaked_mean), "fit() must differ from a fit on train+test"

    # percentile: tiny cohort must abstain (None), not fabricate a rank
    tiny = df.head(5).copy()
    tiny["role"], tiny["league"], tiny["season"] = "GK", "L1", "2099-2100"
    out = domestic_percentile(pd.concat([df, tiny]), "npxg_p90", min_cohort=20)
    assert out.loc[out.role == "GK", "domestic_percentile"].isna().all(), \
        "a 5-player cohort must not receive a percentile"
    assert out.loc[out.role == "FW", "domestic_percentile"].notna().any()

    # support flag
    assert support_flag(minutes=100, cohort_size=30) == "low_minutes"
    assert support_flag(minutes=2000, cohort_size=5) == "out_of_cohort"
    assert support_flag(minutes=2000, cohort_size=30) == "in_distribution"

    # evidence card end to end
    row = test.iloc[1].copy()
    row["cutoff_date"] = "2023-06-30"
    card = build_evidence_card(train, row, "npxg_p90")
    assert card.adjusted_global_percentile is None, "no supported league translation yet (mustermann.md §4)"
    assert card.interval_lo <= card.shrunk_per90 <= card.interval_hi or card.cohort_size < 2

    print("ok — per90, fold-safe shrinkage (monotone in minutes), percentile abstention, evidence card")


if __name__ == "__main__":
    _check()
