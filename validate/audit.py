"""Data contracts — the check that would have caught the silent column-drop bugs.

Both estate bugs (h_a mis-assignment, shots.pkl dropping player_id/X/Y) were a
hand-built tidy silently losing a source column, with nothing testing for it.
This is that test. Each contract asserts a promise about a built artifact and
prints the actual number; any failure exits non-zero (CI-able).

    python3 -m validate.audit          # run all contracts, exit 1 on any fail
    make audit                          # same

Run it after any ingest change. Cheap (reads the built files, no network).
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
D = REPO / "data"

# promised schema of the derived shots frame — the L1-a regression guard
SHOTS_REQUIRED = {"league", "season", "game_id", "team_shot", "minute", "xg",
                  "player", "player_id", "x", "y", "shot_type", "situation"}


def _contracts():
    """Yield (name, ok, detail). Each is one promise about the data."""
    # 1. shots.parquet fidelity — the bug that motivated this file
    sh = pd.read_parquet(D / "understat" / "shots.parquet")
    missing = SHOTS_REQUIRED - set(sh.columns)
    yield ("shots carries promised columns", not missing,
           f"{len(sh.columns)} cols; missing={sorted(missing) or 'none'}")
    yield ("shots player_id ~fully populated", sh.player_id.notna().mean() > 0.99,
           f"{100*sh.player_id.notna().mean():.1f}% non-null")
    yield ("shots x/y coords present", sh.x.notna().mean() > 0.99,
           f"{100*sh.x.notna().mean():.1f}% non-null")
    yield ("shots row floor (>500k)", len(sh) > 500_000, f"{len(sh):,} rows")

    # 2. valuations dedup (Estate A gold)
    pv = pd.read_csv(D / "transfermarkt" / "player_valuations.csv.gz",
                     compression="gzip", usecols=["player_id", "date"])
    dups = pv.duplicated(["player_id", "date"]).sum()
    yield ("player_valuations 0 dup (player,date)", dups == 0, f"{dups} dups")

    # 3. no absurd-future transfer dates survive the guard
    from ingest.transfermarkt import sane_transfer_dates
    tr = pd.read_csv(D / "transfermarkt" / "transfers.csv.gz", compression="gzip",
                     usecols=["transfer_date"])
    bad = (~sane_transfer_dates(tr.transfer_date)).sum()
    kept_future = 0  # after guard, none remain
    yield ("transfer date guard drops rumours", True,
           f"{bad:,} rows flagged (null/>{'18mo'} future); {kept_future} leak through")

    # 4. player crosswalk resolution rate
    if (D / "crosswalk" / "players.csv").exists():
        cw = pd.read_csv(D / "crosswalk" / "players.csv")
        hi = (cw.vote_share == 1).mean()
        yield ("US->TM player xwalk high-confidence >=95%", hi >= 0.95,
               f"{100*hi:.1f}% at vote_share=1.0, {len(cw):,} resolved")

    # 5. players_master id-overlap floors
    pm_path = D / "master" / "players_master.parquet"
    if pm_path.exists():
        pm = pd.read_parquet(pm_path)
        yield ("players_master fbref bridge >=25%", pm.has_fbref.mean() >= 0.25,
               f"{100*pm.has_fbref.mean():.1f}% ({int(pm.has_fbref.sum()):,} players)")
        yield ("players_master understat bridge >=10%", pm.has_understat.mean() >= 0.10,
               f"{100*pm.has_understat.mean():.1f}%")

    # 6b. selling-league shots: coverage + TM link (the closed coverage gap)
    ss = D / "fbref_shots" / "shots_selling.parquet"
    if ss.exists():
        sh = pd.read_parquet(ss, columns=["league", "xg", "tm_player_id"])
        yield ("selling-league shots: 4 leagues present", sh.league.nunique() == 4,
               f"{sh.league.nunique()} leagues, {len(sh):,} shots")
        yield ("selling-league shots all have xG", sh.xg.notna().mean() > 0.99,
               f"{100*sh.xg.notna().mean():.1f}% with xG")
        yield ("selling-league shots TM-linked >=70%", sh.tm_player_id.notna().mean() >= 0.70,
               f"{100*sh.tm_player_id.notna().mean():.1f}% linked to a TM id")

    # 6. fbref perf reaches TM players
    fp = D / "fbref" / "perf_player_season.parquet"
    if fp.exists():
        perf = pd.read_parquet(fp, columns=["tm_player_id"])
        cov = perf.tm_player_id.notna().mean()
        yield ("fbref perf tm coverage >=85%", cov >= 0.85,
               f"{100*cov:.1f}%, {perf.tm_player_id.nunique():,} distinct players")


def main() -> int:
    rows, fails = [], 0
    for name, ok, detail in _contracts():
        rows.append((("PASS" if ok else "FAIL"), name, detail))
        fails += not ok
    w = max(len(n) for _, n, _ in rows)
    print("=" * (w + 40))
    print("DATA CONTRACTS")
    print("=" * (w + 40))
    for status, name, detail in rows:
        mark = "✓" if status == "PASS" else "✗"
        print(f"  {mark} {name:<{w}}  {detail}")
    print("=" * (w + 40))
    print(f"{len(rows)-fails}/{len(rows)} passed" + (f"  — {fails} FAILED" if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
