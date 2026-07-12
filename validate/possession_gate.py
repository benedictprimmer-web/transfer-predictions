"""Possession-value calibration gate — does buildup progression predict realized team
improvement BEYOND the shot channel? (MODELS.md rule: fit only where something real happened.)

The shot channel (pg_mean = usage_share × (efficiency − team_mean_eff)) is already calibrated to
realized `delta_team_xgd90` on the Stage-4 mover panel (validate/benefit_gate.py). This gate adds
a player's `possession_value_z` (ingest/possession_value.py) as a SECOND regressor on the same
panel and asks whether its coefficient is positive with a bootstrap CI that clears zero.

  delta_team_xgd90 ~ b0 + b_pg·pg_mean + b_poss·possession_value_z

GATE: b_poss CI excludes 0 (and > 0)  -> SHIP: persist possession_calibration.csv, wire into NPV.
      otherwise                        -> DESCRIPTIVE ONLY (like league_strength) — do NOT wire.

Units: b_poss is delta_team_xgd90 (per-90) per 1 sd of possession value; ×38 → season npxGD, then
the standard points/£ chain in money/npv.py.

Run: python3 -m validate.possession_gate         -> _check (synthetic, offline)
     python3 -m validate.possession_gate run      -> real gate on the panel; writes calibration if it ships.
"""
from pathlib import Path

import numpy as np
import pandas as pd

CALIB = Path(__file__).resolve().parent.parent / "data" / "money" / "possession_calibration.csv"
PANEL = Path(__file__).resolve().parent.parent / "data" / "stage4" / "panel.csv"
POSS = Path(__file__).resolve().parent.parent / "data" / "impact" / "possession_value.parquet"


def build_frame() -> pd.DataFrame:
    """Panel movers with both the shot-channel predictor (pg_mean) and possession_value_z."""
    from ingest.understat import read_shots
    from ingest.crosswalk import norm_player
    from validate.benefit_gate import team_bars

    panel = pd.read_csv(PANEL)
    bars = team_bars(read_shots())                       # league,season,team -> team_mean_eff
    p = panel.merge(bars.rename(columns={"league": "league_to", "season": "season_from",
                                         "team": "team_to"})[["league_to", "season_from", "team_to", "team_mean_eff"]],
                    on=["league_to", "season_from", "team_to"], how="left")
    p["pg_mean"] = p.usage_share_from * (p.efficiency_from - p.team_mean_eff)

    # bridge Understat player name -> tm_player_id -> possession_value_z at the FROM season
    xw = pd.read_csv(Path(PANEL).parent.parent / "crosswalk" / "players.csv")[["us_name", "tm_player_id"]].dropna()
    xw["k"] = xw.us_name.map(norm_player)
    p["k"] = p.player.map(norm_player)
    p["season_end"] = p.season_from.str[:4].astype(int) + 1
    p = p.merge(xw.drop_duplicates("k"), on="k", how="left")
    pv = (pd.read_parquet(POSS).groupby(["tm_player_id", "season_end_year"])
          .possession_value_z.mean().reset_index())
    p = p.merge(pv, left_on=["tm_player_id", "season_end"],
                right_on=["tm_player_id", "season_end_year"], how="inner")
    return p.dropna(subset=["pg_mean", "possession_value_z", "delta_team_xgd90"])


def calibrate(p: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> dict:
    """Two-feature OLS + bootstrap CI on the possession coefficient."""
    X = np.column_stack([np.ones(len(p)), p.pg_mean.values, p.possession_value_z.values])
    y = p.delta_team_xgd90.values

    def fit(Xa, ya):
        return np.linalg.lstsq(Xa, ya, rcond=None)[0]

    b = fit(X, y)
    yhat = X @ b
    r2 = 1 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    rng = np.random.default_rng(seed)
    bs = np.array([fit(X[i], y[i]) for i in
                   (rng.integers(0, len(y), len(y)) for _ in range(n_boot))])
    lo, hi = np.percentile(bs[:, 2], [2.5, 97.5])
    ships = bool(lo > 0)                                   # CI clears zero, positive
    return dict(slope_poss=float(b[2]), lo=float(lo), hi=float(hi), slope_pg=float(b[1]),
                intercept=float(b[0]), r2=float(r2), n=len(p), ships=ships)


def run():
    p = build_frame()
    cal = calibrate(p)
    print(f"panel joined to possession: n={cal['n']}")
    print(f"  b_pg (shot channel)      = {cal['slope_pg']:+.4f}")
    print(f"  b_poss (possession, /sd) = {cal['slope_poss']:+.4f}  95% CI [{cal['lo']:+.4f}, {cal['hi']:+.4f}]")
    print(f"  joint R² = {cal['r2']:.3f}")
    if cal["ships"]:
        CALIB.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([cal]).to_csv(CALIB, index=False)
        print(f"\nGATE: SHIPS — possession CI clears zero. Wrote {CALIB.name}.")
        print(f"  season npxGD per sd of possession = slope×38 = {cal['slope_poss']*38:+.2f} "
              f"[{cal['lo']*38:+.2f},{cal['hi']*38:+.2f}]")
        print("  -> wire into money/npv.py as the possession benefit term.")
    else:
        print("\nGATE: DESCRIPTIVE ONLY — possession CI includes zero; do NOT wire into NPV.")
        print("  possession_value.parquet ships as a scouting signal, like league_strength.")
    return cal


def _check():
    # synthetic: delta driven by a known possession slope + noise -> gate must recover a +ve CI
    rng = np.random.default_rng(0)
    n = 800
    pg = rng.normal(0, 0.02, n)
    poss = rng.normal(0, 1, n)
    delta = 0.5 * pg + 0.08 * poss + rng.normal(0, 0.1, n)   # true possession slope 0.08 > 0
    p = pd.DataFrame(dict(pg_mean=pg, possession_value_z=poss, delta_team_xgd90=delta))
    cal = calibrate(p, n_boot=500)
    assert cal["ships"], f"should ship a real +ve slope: {cal}"
    assert cal["lo"] > 0 and abs(cal["slope_poss"] - 0.08) < 0.03, cal
    # null case: no possession signal -> must NOT ship
    delta0 = 0.5 * pg + rng.normal(0, 0.1, n)
    p0 = pd.DataFrame(dict(pg_mean=pg, possession_value_z=poss, delta_team_xgd90=delta0))
    cal0 = calibrate(p0, n_boot=500)
    assert not cal0["ships"], f"null possession must not ship: {cal0}"
    print(f"recovered slope {cal['slope_poss']:.3f} [{cal['lo']:.3f},{cal['hi']:.3f}] SHIPS; "
          f"null slope {cal0['slope_poss']:.3f} [{cal0['lo']:.3f},{cal0['hi']:.3f}] rejected")
    print("ok")


if __name__ == "__main__":
    import sys
    run() if "run" in sys.argv[1:] else _check()
