"""V2 full-data descriptive analysis (task §7). Deterministic, warehouse-only —
no raw-cache scanning, no network. Describes coverage/support/distributions
across the *entire* tracked estate (that is what "use the full data" means
for a descriptive pass); it does not train anything and does not compute any
metric on the locked final period (`validate.locked_guard.LOCKED_SEASON_MIN`).

    python3 -m validate.v2_full_data
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from validate.locked_guard import LOCKED_SEASON_MIN, write_locked_audit

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
OUT = REPO / "reports" / "v2-full-data"


def _write_csv(df: pd.DataFrame, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    df.sort_values(list(df.columns)[:3] if len(df.columns) >= 3 else list(df.columns)).to_csv(path, index=False)
    return path


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DATA / "warehouse.duckdb"), read_only=True)


def coverage_cube(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Season x league x role x minutes-band player-season support, from
    fbref_perf (the only source with a real minutes column and 222 raw
    counting stats) joined to players_master for role."""
    q = """
    with j as (
        select f.Season_End_Year as season, f.Comp as league,
               coalesce(m.position, 'unknown') as role,
               f."playing_time__Min_Playing.Time" as minutes
        from fbref_perf f
        left join players_master m on f.fbref_id = m.fbref_id
    )
    select season, league, role,
           case when minutes is null then 'unknown'
                when minutes < 450 then '<450'
                when minutes < 900 then '450-899'
                when minutes < 1800 then '900-1799'
                else '1800+' end as minutes_band,
           count(*) as player_seasons
    from j
    group by 1,2,3,4
    order by 1,2,3,4
    """
    return con.execute(q).fetchdf()


def metric_distributions(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Raw-total vs per-90 distribution for the count metrics
    docs/mustermann.md §1 approves for the per-90 transform. Reports
    zero-inflation and tails so a modeller can see where per-90 becomes
    unstable (low minutes -> extreme rates)."""
    metrics = {
        "npxg": "standard__npxG_Expected",
        "xag": "standard__xAG_Expected",
        "prog_actions": "standard__PrgP_Progression",
        "tackles": "defense__Tkl_Tackles",
        "interceptions": "defense__Int",
    }
    rows = []
    for label, col in metrics.items():
        q = f"""
        with j as (
            select "{col}" as raw, "playing_time__Min_Playing.Time" as minutes
            from fbref_perf
            where "{col}" is not null and "playing_time__Min_Playing.Time" > 0
        ), p as (
            select raw, minutes, 90.0 * raw / minutes as per90 from j
        )
        select
          count(*) as n,
          sum(case when raw = 0 then 1 else 0 end) as zero_rows,
          avg(raw) as raw_mean, median(raw) as raw_median,
          quantile_cont(raw, 0.9) as raw_p90, quantile_cont(raw, 0.99) as raw_p99,
          avg(per90) as per90_mean, median(per90) as per90_median,
          quantile_cont(per90, 0.9) as per90_p90, quantile_cont(per90, 0.99) as per90_p99,
          sum(case when minutes < 450 then 1 else 0 end) as n_under_450min
        from p
        """
        r = con.execute(q).fetchdf().iloc[0].to_dict()
        r["metric"] = label
        r["source_column"] = col
        rows.append(r)
    return pd.DataFrame(rows)


def mover_support(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Cross-league mover counts, full estate (all seasons, all transfer
    types) — this is a coverage/support question, not a model fit, so the
    locked period is included here deliberately (it is excluded from every
    computation that fits or scores anything)."""
    q = """
    select from_league, to_league, count(*) as movers,
           sum(case when season >= ? then 1 else 0 end) as movers_in_locked_period,
           min(season) as min_season, max(season) as max_season
    from transfers_canonical
    where from_league is not null and to_league is not null and from_league <> to_league
    group by 1,2
    having count(*) >= 5
    order by movers desc
    """
    return con.execute(q, [LOCKED_SEASON_MIN]).fetchdf()


def cohort_support(con: duckdb.DuckDBPyConnection, min_cohort: int = 20) -> pd.DataFrame:
    """Role x league x season cell sizes — the exact denominator a domestic
    percentile (docs/mustermann.md §3) would be computed within. Flags which
    cells are too small to support a percentile at all."""
    q = """
    select f.Season_End_Year as season, f.Comp as league,
           coalesce(m.position, 'unknown') as role,
           count(*) as cohort_size,
           count(*) >= ? as viable_for_percentile
    from fbref_perf f
    left join players_master m on f.fbref_id = m.fbref_id
    group by 1,2,3
    order by 1,2,3
    """
    return con.execute(q, [min_cohort]).fetchdf()


def full_data_manifest() -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO).decode().strip()
    except Exception:
        commit = None
    return {
        "commit": commit,
        "command": "python3 -m validate.v2_full_data",
        "warehouse": str((DATA / "warehouse.duckdb").relative_to(REPO)),
        "locked_season_min": LOCKED_SEASON_MIN,
        "note": "Descriptive coverage/support only. No model fit, no metric computed on the locked period.",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()
    artifacts = {}
    artifacts["coverage_cube"] = str(_write_csv(coverage_cube(con), "coverage_cube.csv").relative_to(REPO))
    artifacts["metric_distributions"] = str(_write_csv(metric_distributions(con), "metric_distributions.csv").relative_to(REPO))
    artifacts["mover_support"] = str(_write_csv(mover_support(con), "mover_support.csv").relative_to(REPO))
    artifacts["cohort_support"] = str(_write_csv(cohort_support(con), "cohort_support.csv").relative_to(REPO))

    all_transfers = con.execute("select transfer_uid, season from transfers_canonical").fetchdf()
    artifacts["locked_test_audit"] = str(
        write_locked_audit(all_transfers, OUT / "locked_test_audit.json").relative_to(REPO)
    )

    manifest_path = OUT / "full_data_manifest.json"
    manifest = full_data_manifest()
    manifest["outputs"] = artifacts
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    artifacts["full_data_manifest"] = str(manifest_path.relative_to(REPO))

    print(json.dumps(artifacts, indent=2, sort_keys=True))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
