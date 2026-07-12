"""Possession-value layer — the OFFENSIVE PROGRESSION axis the shot engine misses.

WHY (and how it differs from defensive_value.py)
-------------------------------------------------
impact/usage.py values a player at shots + the assist (xG+xAG). It is blind to *buildup
progression* — carrying and passing the ball forward through midfield — so it under-prices
deep midfielders and ball-playing defenders. `defensive_value.py` patched the defensive
side with an EQUAL-weighted box-score composite. This layer does the OFFENSIVE progression
side, and weights each action by its empirical **xT value** (ingest/xt.py, fit on StatsBomb
EPL 2015/16) instead of equal weights — a pass into the final third is worth ~1.4× a
generic progression, and that differentiation is real.

DELIBERATE EXCLUSIONS (each avoids double-counting a channel we already have):
  - box passes / carries, through-balls, key passes, xA -> the FINAL BALL, already valued by
    the usage engine's shot-assist term (xAG). This layer is BUILDUP, not the final ball.
  - take-ons -> a successful take-on is almost always followed by the carry it enables, which
    IS counted (prog_carries / carries_into_final_third); counting both double-counts it.
  - prog_receptions -> receiver-side (being an outlet), which double-counts the progressive
    passer who fed it. We credit who ADVANCES the ball, not who receives it advanced.
  Net: four creator-side buildup actions, each distinct. Verified corr≈0.17 with the defensive
  layer (a genuinely new axis) and it floors poachers/keepers (Haaland/Alisson bottom-decile).

Method mirrors defensive_value.py: z-score each per-90 component, then take the
**xT-weighted** mean of the z-scores -> percentile 0-100. tm_player_id-keyed, Big-5
2018-2025, from FBref niche_summary (already tm-keyed). Grade B (empirically weighted).

Run: python3 -m ingest.possession_value            -> _check (synthetic, offline)
     python3 -m ingest.possession_value build       -> data/impact/possession_value.parquet
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "impact" / "possession_value.parquet"

# FBref niche_summary column -> xt.py weight category. Buildup progression only; box/
# through-ball/key-pass columns are intentionally absent (shot-assist channel owns them).
# take_ons ~ carrying past a man; prog_receptions ~ receiver side of a progressive pass.
COL_WEIGHT = {
    "prog_passes":              "prog_pass",
    "passes_into_final_third":  "pass_f3",
    "prog_carries":             "prog_carry",
    "carries_into_final_third": "carry_f3",
}
KEY = ["tm_player_id", "season_end_year", "comp", "squad"]


def possession_value(niche: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """niche: ingest.fbref_perf niche_summary schema (tm_player_id-keyed, raw totals + n90).
    weights: {category: mean_xT} from ingest.xt.load_weights()."""
    df = niche.copy()
    comps = list(COL_WEIGHT)
    per90 = pd.DataFrame({c: df[c] / df["n90"] for c in comps})     # totals -> per 90
    z = per90.apply(lambda c: (c - c.mean()) / c.std(ddof=0))       # standardise each, like defensive_value
    w = pd.Series({c: weights[COL_WEIGHT[c]] for c in comps})
    df["possession_value_z"] = (z * w).sum(axis=1) / w.sum()        # xT-WEIGHTED mean of z-scores
    df["possession_value_score"] = df["possession_value_z"].rank(pct=True) * 100

    for c in comps:                                                 # ride-along per-90 rates for legibility
        df[c + "_p90"] = per90[c]
    df["grade"] = "B"
    df["source"] = "fbref_niche_summary × xt_weights(statsbomb_epl_2015_16)"
    keep = [*KEY, "n90", *[c + "_p90" for c in comps],
            "possession_value_z", "possession_value_score", "grade", "source"]
    return df[keep].sort_values("possession_value_score", ascending=False).reset_index(drop=True)


def build():
    from ingest.xt import load_weights
    niche = pd.read_parquet("data/fbref/niche_summary.parquet")
    out = possession_value(niche, load_weights())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"wrote {OUT}: {len(out)} rows, {out.tm_player_id.nunique()} players")
    return out


def _check():
    # weights: box-ish entries out-value generic progression, matching a real xT fit
    weights = dict(prog_pass=0.0067, pass_f3=0.0092, prog_carry=0.0065, carry_f3=0.0029)
    niche = pd.DataFrame([
        # deep progressive midfielder: heavy prog passes/carries + final-third entries
        dict(tm_player_id=1, season_end_year=2020, comp="EPL", squad="A", n90=30.0,
             prog_passes=180, passes_into_final_third=150, prog_carries=90,
             carries_into_final_third=60),
        # pure poacher: barely touches buildup
        dict(tm_player_id=2, season_end_year=2020, comp="EPL", squad="B", n90=30.0,
             prog_passes=15, passes_into_final_third=10, prog_carries=8,
             carries_into_final_third=5),
        # middling
        dict(tm_player_id=3, season_end_year=2020, comp="EPL", squad="C", n90=30.0,
             prog_passes=70, passes_into_final_third=55, prog_carries=35,
             carries_into_final_third=25),
    ])
    out = possession_value(niche, weights)
    s = out.set_index("tm_player_id").possession_value_score
    assert s.loc[1] == out.possession_value_score.max(), "deep progressor must top the ranking"
    assert s.loc[2] == out.possession_value_score.min(), "poacher must rank lowest"
    assert out.iloc[0].grade == "B"
    print(out[["tm_player_id", "possession_value_score", "grade"]].to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    build() if "build" in sys.argv[1:] else _check()
