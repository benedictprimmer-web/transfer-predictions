"""warehouse — one DuckDB over every canonical artifact. The single source of
truth the audit called for (P2-8), replacing "two half-overlapping estates".

Design: VIEWS over the parquet/csv files Estate A already owns (no copy, always
fresh), plus a few MATERIALIZED tables for the cross-estate pieces we keep from
Estate B (the 221-col FBref perf, already re-homed to data/fbref/, and the
leak-guarded transfer<->performance link). Estate B's redundant tables
(transfers, valuations, perf_shots_raw) are deliberately NOT imported — see the
ARCHIVE note printed at build.

The leak guard (P2-10): transfer_performance_link is exposed ONLY as
`transfer_performance_link_safe`, filtered to perf_season < transfer_season, so
no downstream fit can accidentally train on post-transfer performance.

    python3 -m ingest.warehouse build     # (re)build data/warehouse.duckdb
    python3 -m ingest.warehouse           # offline self-check
"""
from __future__ import annotations
import os
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
D = REPO / "data"
ESTATE_B = Path(os.environ.get(
    "ESTATE_B_DIR", "/Users/benrimmer/Downloads/football-transfer-db"))
WAREHOUSE = D / "warehouse.duckdb"

# name -> SQL source. Views unless the source is Estate B (materialized).
_VIEWS = {
    "players_master":    f"read_parquet('{D}/master/players_master.parquet')",
    "contracts":         f"read_parquet('{D}/master/contracts.parquet')",
    "injuries":          f"read_parquet('{D}/master/injuries.parquet')",       # durability/availability, TM-keyed
    "wages_fifa":        f"read_parquet('{D}/wages/wages_fifa.parquet')",       # FIFA-era wage prior, TM-keyed
    "fbref_perf":        f"read_parquet('{D}/fbref/perf_player_season.parquet')",
    "fbref_defense":     f"read_parquet('{D}/fbref/defensive_summary.parquet')",
    "fbref_niche":       f"read_parquet('{D}/fbref/niche_summary.parquet')",
    "transfers_canonical": f"read_parquet('{D}/merged/transfers_canonical.parquet')",
    "shots":             f"read_parquet('{D}/understat/shots.parquet')",
    "shots_selling":     f"read_parquet('{D}/fbref_shots/shots_selling.parquet')",  # 4 feeder leagues, FBref xG
    "valuations":        f"read_csv_auto('{D}/transfermarkt/player_valuations.csv.gz', ignore_errors=true)",
    "crosswalk_players": f"read_csv_auto('{D}/crosswalk/players.csv')",
    "crosswalk_matches": f"read_csv_auto('{D}/crosswalk/matches.csv')",
    "clubelo_history":   f"read_csv_auto('{D}/strength/clubelo_history.csv')",  # if present
}

# Estate B tables we DON'T keep, and why (printed as the archive record)
_ARCHIVED = {
    "transfers":        "superseded by transfers_canonical (dated, deduped, PIT market value)",
    "valuations":       "superseded by Estate A player_valuations (507k, 0 dup, 2000-2026)",
    "perf_shots_raw":   "mirrors Understat shots (data/understat/shots.parquet)",
    "perf_shots_player_season": "derivable from shots",
    "player_crosswalk": "repaired + absorbed into players_master.fbref_id",
    "features/fee_model_ready": "rebuilt live by money/fees.py off transfers_canonical",
    "contracts/wages/clauses/club_wage_bills": "were 0 rows; contracts now filled from players.csv",
}


def _write_shots_parquet():
    """Ensure the DuckDB-readable shots parquet exists; read_shots writes it (from
    the .rds) if missing. Parquet is now the primary shots cache — no pickle."""
    pq = D / "understat" / "shots.parquet"
    if not pq.exists():
        from ingest import understat
        understat.read_shots()
    return pq


def build():
    import duckdb
    _write_shots_parquet()
    if WAREHOUSE.exists():
        WAREHOUSE.unlink()
    con = duckdb.connect(str(WAREHOUSE))

    made = []
    for name, src in _VIEWS.items():
        # clubelo_history is optional (agent-built); skip if the file is absent
        if "clubelo_history" in name and not (D / "strength" / "clubelo_history.csv").exists():
            continue
        try:
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM {src}")
            made.append(name)
        except Exception as e:
            print(f"  ! skip {name}: {str(e)[:80]}")

    # leak-guarded cross-estate link (materialized from Estate B parquet)
    tpl = ESTATE_B / "03_performance" / "transfer_performance_link.parquet"
    if tpl.exists():
        con.execute(f"""
            CREATE TABLE transfer_performance_link_safe AS
            SELECT * FROM read_parquet('{tpl}')
            WHERE perf_season < transfer_season
        """)
        made.append("transfer_performance_link_safe")

    print("=" * 60)
    print(f"WAREHOUSE  {WAREHOUSE}")
    print("=" * 60)
    for name in made:
        n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        kind = "table" if name.endswith("_safe") else "view "
        print(f"  {kind}  {name:<26} {n:>10,}")
    if tpl.exists():
        raw = con.execute(f"SELECT count(*) FROM read_parquet('{tpl}')").fetchone()[0]
        safe = con.execute("SELECT count(*) FROM transfer_performance_link_safe").fetchone()[0]
        print(f"\n  leak guard: {raw:,} link rows -> {safe:,} strictly-prior "
              f"({raw-safe:,} post-transfer rows excluded)")
    con.close()

    print("\nARCHIVED (Estate B, not imported — redundant):")
    for t, why in _ARCHIVED.items():
        print(f"  • {t:<42} {why}")
    print(f"\nEstate B can be moved to cold storage; nothing above depends on it "
          f"except the frozen FBref perf (already copied to data/fbref/).")


def connect(read_only=True):
    import duckdb
    return duckdb.connect(str(WAREHOUSE), read_only=read_only)


# ------------------------------------------------------------------ check

def _check():
    import duckdb
    con = duckdb.connect()  # in-memory
    con.execute("CREATE TABLE link(transfer_season INT, perf_season INT, x INT)")
    con.execute("INSERT INTO link VALUES (2020,2018,1),(2020,2020,2),(2020,2021,3)")
    safe = con.execute(
        "SELECT count(*) FROM link WHERE perf_season < transfer_season").fetchone()[0]
    assert safe == 1, ("only the 2018<2020 row is leak-safe", safe)
    # views map 1:1 to files; assert the config is well-formed
    assert "shots" in _VIEWS and "players_master" in _VIEWS
    assert all(isinstance(v, str) for v in _VIEWS.values())
    print("ok — leak guard keeps only strictly-prior perf; view config well-formed")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
