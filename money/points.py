"""Stage 7a — xGD -> league points (MODELS.md §money). The engine's whole output
currency is npxGD; this is the fitted link from a team-season's non-penalty
expected-goal difference to the league points it buys.

Both sides come from Understat shots so team names match with no crosswalk:
  - points: reconstruct each game's scoreline from shots (result in Goal/OwnGoal),
    W/D/L -> 3/1/0. An OwnGoal row's `team_shot` is the CONCEDING team (verified
    empirically: it reproduces the real 2021-22 EPL GF=99 for Man City), so it
    scores for the opponent.
  - npxGD: sum shot xG (excl. penalties and own goals) for vs against, per team-season.

Fit is per-game (points-per-game ~ npxGD-per-game) so the Big-5's 34/38-game
seasons pool cleanly. Season points = 38 * (a + b * npxGD_per_game) for the EPL.

Run: `python3 -m money.points`      -> _check (synthetic + deterministic, no network)
     `python3 -m money.points run`  -> real fit, prints coefficients + caches.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "money" / "points_fit.csv"


def team_season_table(shots: pd.DataFrame) -> pd.DataFrame:
    """One row per (league, season, team): games, points, npxGD for/against."""
    s = shots.copy()
    opp = np.where(s.team_shot == s.home_team, s.away_team, s.home_team)
    s["scorer"] = np.where(s.result == "OwnGoal", opp, s.team_shot)

    # --- goals per game per side (from reconstructed scorers) ---
    goals = s[s.result.isin(["Goal", "OwnGoal"])]
    gg = goals.groupby(["game_id", "scorer"]).size().rename("g").reset_index()
    games = s[["league", "season", "game_id", "home_team", "away_team"]].drop_duplicates("game_id")
    hg = games.merge(gg.rename(columns={"scorer": "home_team", "g": "hg"}),
                     on=["game_id", "home_team"], how="left")
    ag = hg.merge(gg.rename(columns={"scorer": "away_team", "g": "ag"}),
                  on=["game_id", "away_team"], how="left")
    ag[["hg", "ag"]] = ag[["hg", "ag"]].fillna(0).astype(int)
    ag["hp"] = np.select([ag.hg > ag.ag, ag.hg == ag.ag], [3, 1], 0)
    ag["ap"] = np.select([ag.ag > ag.hg, ag.hg == ag.ag], [3, 1], 0)

    # --- npxG per game per side (excl. pens + own goals) ---
    xs = s[(s.situation != "Penalty") & (s.result != "OwnGoal")]
    tx = xs.groupby(["game_id", "team_shot"]).xg.sum().rename("x").reset_index()
    ag = ag.merge(tx.rename(columns={"team_shot": "home_team", "x": "hx"}),
                  on=["game_id", "home_team"], how="left")
    ag = ag.merge(tx.rename(columns={"team_shot": "away_team", "x": "ax"}),
                  on=["game_id", "away_team"], how="left")
    ag[["hx", "ax"]] = ag[["hx", "ax"]].fillna(0.0)

    # --- stack to team rows and aggregate to team-season ---
    home = ag.rename(columns={"home_team": "team", "hp": "pts", "hg": "gf", "ag": "ga",
                              "hx": "xgf", "ax": "xga"})
    away = ag.rename(columns={"away_team": "team", "ap": "pts", "ag": "gf", "hg": "ga",
                              "ax": "xgf", "hx": "xga"})
    cols = ["league", "season", "team", "pts", "gf", "ga", "xgf", "xga"]
    long = pd.concat([home[cols], away[cols]], ignore_index=True)
    t = long.groupby(["league", "season", "team"], as_index=False).agg(
        games=("pts", "size"), points=("pts", "sum"),
        gf=("gf", "sum"), ga=("ga", "sum"), xgf=("xgf", "sum"), xga=("xga", "sum"))
    t["npxgd"] = t.xgf - t.xga
    t["ppg"] = t.points / t.games
    t["npxgd_pg"] = t.npxgd / t.games
    return t


def fit(t: pd.DataFrame):
    """OLS ppg ~ a + b * npxgd_pg. Returns (a, b, r2, pts_per_season_slope@38)."""
    d = t.dropna(subset=["ppg", "npxgd_pg"])
    X = np.column_stack([np.ones(len(d)), d.npxgd_pg.values])
    b, *_ = np.linalg.lstsq(X, d.ppg.values, rcond=None)
    pred = X @ b
    ss_res = ((d.ppg.values - pred) ** 2).sum()
    ss_tot = ((d.ppg.values - d.ppg.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot
    return float(b[0]), float(b[1]), float(r2), float(b[1] * 38)


def run():
    from ingest.understat import read_shots
    t = team_season_table(read_shots())
    a, b, r2, per_season = fit(t)

    # gate: real 2021-22 EPL table must match reality
    epl = t[(t.league == "ENG-Premier League") & (t.season == "2021-2022")]
    mc = epl[epl.team == "Manchester City"]
    print(f"team-seasons: {len(t)}  leagues: {t.league.nunique()}")
    if not mc.empty:
        r = mc.iloc[0]
        print(f"CHECK Man City 2021-22: {r.points:.0f} pts (real 93), "
              f"GF {r.gf:.0f} (real 99), GA {r.ga:.0f} (real 26)")

    print(f"\n=== ppg ~ a + b*npxGD_per_game (OLS, {len(t)} team-seasons) ===")
    print(f"intercept a = {a:.3f} ppg   slope b = {b:.3f} ppg per (npxGD/game)")
    print(f"R^2 = {r2:.3f}")
    print(f"season scale: +1.0 npxGD/game ~ +{per_season:.1f} points over 38 games")
    print(f"practical: +10 season npxGD (EPL) ~ +{b * (10 / 38) * 38:.1f} points")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([dict(intercept=a, slope_ppg=b, r2=r2,
                       points_per_npxgd_season=b)]).to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")
    return t


def _check():
    # deterministic scoreline: 2 games, known results -> known points/goals
    shots = pd.DataFrame([
        # game 1: A home beat B 2-1 (one B goal is an own goal by A's keeper)
        dict(league="L", season="S", game_id=1, home_team="A", away_team="B",
             team_shot="A", result="Goal", situation="OpenPlay", xg=0.5),
        dict(league="L", season="S", game_id=1, home_team="A", away_team="B",
             team_shot="A", result="Goal", situation="OpenPlay", xg=0.4),
        dict(league="L", season="S", game_id=1, home_team="A", away_team="B",
             team_shot="A", result="OwnGoal", situation="OpenPlay", xg=0.0),  # counts for B
        # game 2: A away vs B, 0-0
        dict(league="L", season="S", game_id=2, home_team="B", away_team="A",
             team_shot="A", result="MissedShots", situation="OpenPlay", xg=0.3),
    ])
    t = team_season_table(shots)
    A = t[t.team == "A"].iloc[0]
    B = t[t.team == "B"].iloc[0]
    assert A.points == 4 and B.points == 1, (A.points, B.points)   # A: win+draw, B: loss+draw
    assert A.gf == 2 and A.ga == 1, (A.gf, A.ga)                    # own goal scored for B
    assert abs(A.xgf - (0.5 + 0.4 + 0.3)) < 1e-9, A.xgf            # OG excluded from xG

    # synthetic fit: plant ppg = 1.4 + 0.9*npxgd_pg + noise, recover slope
    rng = np.random.default_rng(0)
    npg = rng.normal(0, 0.6, 300)
    d = pd.DataFrame(dict(ppg=1.4 + 0.9 * npg + rng.normal(0, 0.1, 300), npxgd_pg=npg))
    a, b, r2, _ = fit(d)
    assert abs(b - 0.9) < 0.1 and r2 > 0.9, (a, b, r2)
    print(f"scoreline ok (A={A.points}pts B={B.points}pts, OG->B); "
          f"fit recovered slope {b:.2f} (planted 0.90), R^2 {r2:.2f}")
    print("ok")


if __name__ == "__main__":
    import sys
    run() if "run" in sys.argv[1:] else _check()
