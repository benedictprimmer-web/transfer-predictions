"""Stage-1 gate: xG / shot-minute / lineup coverage per league-season.

DATA.md: "Before committing to any league, produce a coverage table: rows are
league-seasons, columns are has_xg, has_shot_minutes, has_lineup_minutes,
pct_matches_complete. Any league-season below ~95% complete gets dropped or
flagged, never silently averaged in."

Cost model (soccerdata rate-limits itself, ~3s/request):
  - read_schedule: 2 requests / league-season -> has_xg + pct_matches_complete
    for EVERY league-season cheaply.
  - shot/lineup availability tracks has_xg (same Opta feed), but we don't assume
    it: we sample ONE match per league-season (+2 requests) and check the frames
    are non-empty with minute/xg and minutes. ~4 req x ~100 league-seasons.

RUN ON YOUR OWN MACHINE. FBref 403s sandbox IPs (verified 2026-07). Output ->
data/coverage.csv.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

from . import fbref

COMPLETE_THRESHOLD = 0.95  # DATA.md's ~95% line

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def coverage_from_schedule(sched: pd.DataFrame) -> pd.DataFrame:
    """Pure: soccerdata read_schedule().reset_index() -> per league-season rows.

    Defensive about the xG columns: FBref simply omits home_xg/away_xg for
    league-seasons with no xG, so a missing column means has_xg=False, not error.
    A row counts as 'played' when it has a score.
    """
    d = sched.copy()
    has_score = d["score"].notna() if "score" in d else pd.Series(False, index=d.index)
    if "home_xg" in d and "away_xg" in d:
        has_xg_row = d["home_xg"].notna() & d["away_xg"].notna()
    else:
        has_xg_row = pd.Series(False, index=d.index)
    d = d.assign(_played=has_score.values, _xg=has_xg_row.values)

    g = d.groupby(["league", "season"], sort=True)
    out = g.agg(n_matches=("_played", "size"),
                n_played=("_played", "sum"),
                n_xg=("_xg", "sum")).reset_index()
    out["pct_matches_complete"] = out.n_played / out.n_matches
    # xG completeness among played matches — the honest "how much xG" number
    out["pct_xg"] = np.where(out.n_played > 0, out.n_xg / out.n_played, 0.0)
    out["has_xg"] = out.pct_xg >= COMPLETE_THRESHOLD
    return out


def _sample_match_id(sched: pd.DataFrame, league: str, season) -> str | None:
    """A game_id with a match report for (league, season), for the shot/lineup
    probe. Picks the median-dated played match to avoid opening-day oddities."""
    sub = sched[(sched.league == league) & (sched.season == season)]
    sub = sub[sub.get("game_id").notna() & sched.get("match_report").notna()]
    if len(sub) == 0:
        return None
    return sub.sort_values("date").iloc[len(sub) // 2].game_id


def build_coverage(leagues=fbref.ALL_LEAGUES, seasons=fbref.SEASONS,
                   sample=True, save=True) -> pd.DataFrame:
    """NETWORK. Schedules for all league-seasons, then one sampled match each
    for shot/lineup confirmation. Writes data/coverage.csv."""
    fbref.ensure_league_dict()
    sched = fbref.read_schedule(leagues, seasons)
    cov = coverage_from_schedule(sched)

    cov["has_shot_minutes"] = pd.NA
    cov["has_lineup_minutes"] = pd.NA
    if sample:
        for i, row in cov.iterrows():
            gid = _sample_match_id(sched, row.league, row.season)
            if gid is None:
                continue
            try:
                sh = fbref.read_shots([row.league], [row.season], match_id=gid)
                cov.at[i, "has_shot_minutes"] = bool(len(sh) > 0)
            except Exception as e:  # noqa: BLE001 — one bad match must not kill the sweep
                cov.at[i, "has_shot_minutes"] = False
                print(f"  shot probe failed {row.league} {row.season}: {e}")
            try:
                lu = fbref.read_lineup([row.league], [row.season], match_id=gid)
                cov.at[i, "has_lineup_minutes"] = bool(len(lu) > 0)
            except Exception as e:  # noqa: BLE001
                cov.at[i, "has_lineup_minutes"] = False
                print(f"  lineup probe failed {row.league} {row.season}: {e}")

    cols = ["league", "season", "n_matches", "pct_matches_complete",
            "has_xg", "pct_xg", "has_shot_minutes", "has_lineup_minutes"]
    cov = cov[cols].sort_values(["league", "season"]).reset_index(drop=True)
    if save:
        DATA_DIR.mkdir(exist_ok=True)
        cov.to_csv(DATA_DIR / "coverage.csv", index=False)
        print(f"wrote {DATA_DIR / 'coverage.csv'}  ({len(cov)} league-seasons)")
    return cov


def verdict(cov: pd.DataFrame) -> pd.DataFrame:
    """Per league: seasons with usable xG (has_xg & complete). The written
    decision the gate asks for, as a frame."""
    ok = cov[cov.has_xg & (cov.pct_matches_complete >= COMPLETE_THRESHOLD)]
    return (ok.groupby("league")
              .agg(usable_seasons=("season", "count"),
                   first=("season", "min"), last=("season", "max"))
              .reset_index()
              .sort_values("usable_seasons", ascending=False))


def _check():
    # two league-seasons: one with full xG, one with none. Pure, no network.
    rows = []
    for m in range(20):
        rows.append(dict(league="ENG-Premier League", season="2324",
                         score="2–1", home_xg=1.4, away_xg=0.9,
                         game_id=f"pl{m}", match_report=f"/x/{m}", date=f"2023-08-{m+1:02d}"))
    for m in range(20):
        # older season: played but NO xg columns present at all in real data;
        # simulate the "column exists but all-NaN" variant too
        rows.append(dict(league="FRA-Ligue 1", season="1516",
                         score="1–0" if m < 19 else None, home_xg=np.nan, away_xg=np.nan,
                         game_id=f"l1{m}", match_report=f"/y/{m}", date=f"2015-08-{m+1:02d}"))
    sched = pd.DataFrame(rows)
    cov = coverage_from_schedule(sched)

    pl = cov[cov.league == "ENG-Premier League"].iloc[0]
    l1 = cov[cov.league == "FRA-Ligue 1"].iloc[0]
    assert pl.has_xg and pl.pct_matches_complete == 1.0, pl.to_dict()
    assert not l1.has_xg, l1.to_dict()
    assert abs(l1.pct_matches_complete - 19 / 20) < 1e-9, l1.pct_matches_complete

    # missing xg columns entirely -> has_xg False, no crash
    cov2 = coverage_from_schedule(sched.drop(columns=["home_xg", "away_xg"]))
    assert not cov2.has_xg.any()

    v = verdict(cov)
    assert list(v.league) == ["ENG-Premier League"], "only the xG league is usable"

    print(cov.to_string(index=False))
    print("--- verdict ---")
    print(v.to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    # `python -m ingest.coverage build` -> real pull (run on your own machine).
    # no arg -> offline self-check.
    (build_coverage if "build" in sys.argv[1:] else _check)()
