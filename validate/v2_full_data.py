"""V2 full-data descriptive analysis (task §7). Deterministic, warehouse-only —
no raw-cache scanning, no network. Describes coverage/support/distributions
across the *entire* tracked estate (that is what "use the full data" means
for a descriptive pass); it does not train anything and does not compute any
metric on the locked final period (`validate.locked_guard.LOCKED_SEASON_MIN`).

    python3 -m validate.v2_full_data
"""
from __future__ import annotations

import hashlib
import json
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
        with base as (
            select "{col}" as raw, "playing_time__Min_Playing.Time" as minutes
            from fbref_perf
            where "{col}" is not null
        ), j as (
            select raw, minutes from base where minutes is not null and minutes > 0
        ), p as (
            select raw, minutes, 90.0 * raw / minutes as per90 from j
        )
        select
          (select count(*) from base) as n_metric_known,
          (select count(*) from base where minutes is null) as n_unknown_minutes,
          count(*) as n_observed_minutes,
          sum(case when raw = 0 then 1 else 0 end) as zero_rows,
          avg(raw) as raw_mean, median(raw) as raw_median,
          quantile_cont(raw, 0.9) as raw_p90, quantile_cont(raw, 0.99) as raw_p99,
          avg(per90) as per90_mean, median(per90) as per90_median,
          quantile_cont(per90, 0.9) as per90_p90, quantile_cont(per90, 0.99) as per90_p99,
          sum(case when minutes < 450 then 1 else 0 end) as n_low_minutes_under_450
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


def cohort_support(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Role x league x season cell sizes — the exact denominator a domestic
    percentile (docs/mustermann.md §3) would be computed within. Confidence
    tiers match `impact.evidence.domestic_percentile`'s revised defaults
    (<20 unavailable, 20-49 low, 50-99 moderate, 100+ high) — a 20-player
    cohort is no longer called "viable" without qualification; it's the
    floor for the lowest usable tier."""
    q = """
    select f.Season_End_Year as season, f.Comp as league,
           coalesce(m.position, 'unknown') as role,
           count(*) as cohort_size
    from fbref_perf f
    left join players_master m on f.fbref_id = m.fbref_id
    group by 1,2,3
    order by 1,2,3
    """
    out = con.execute(q).fetchdf()
    out["cohort_confidence"] = pd.cut(
        out.cohort_size, bins=[-1, 19, 49, 99, float("inf")],
        labels=["unavailable", "low", "moderate", "high"])
    return out


def missingness_patterns(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Joint feature/label availability for the two populations this repo's
    models actually use: the strict V1 fee scope (transfers_canonical) and
    the fbref_perf performance table. Required artifact, not produced in the
    original V2 pass."""
    from validate.modelling_contract import V1_FEE_SCOPE
    rows = []

    fee_checks = {
        "market_value_eur_present": "market_value_eur is not null",
        "contract_years_pit": "coalesce(contract_is_pit,false)",
        "fee_undisclosed": "coalesce(fee_undisclosed,false)",
        "exact_date": "date_source in ('exact','exact_raw')",
    }
    base = con.execute(f"select count(*) from transfers_canonical where {V1_FEE_SCOPE}").fetchone()[0]
    for name, pred in fee_checks.items():
        n = con.execute(f"select count(*) from transfers_canonical where ({V1_FEE_SCOPE}) and {pred}").fetchone()[0]
        rows.append({"population": "v1_fee_scope", "base_rows": base, "field": name,
                     "present_rows": n, "present_pct": round(100 * n / base, 2) if base else None})

    perf_base = con.execute("select count(*) from fbref_perf").fetchone()[0]
    perf_checks = {
        "minutes_known": '"playing_time__Min_Playing.Time" is not null',
        "npxg_known": "standard__npxG_Expected is not null",
        "xag_known": "standard__xAG_Expected is not null",
        "prog_actions_known": "standard__PrgP_Progression is not null",
        "tackles_known": "defense__Tkl_Tackles is not null",
        "interceptions_known": "defense__Int is not null",
        "tm_player_id_linked": "tm_player_id is not null",
    }
    for name, pred in perf_checks.items():
        n = con.execute(f"select count(*) from fbref_perf where {pred}").fetchone()[0]
        rows.append({"population": "fbref_perf", "base_rows": perf_base, "field": name,
                     "present_rows": n, "present_pct": round(100 * n / perf_base, 2) if perf_base else None})

    # joint pattern: metric known but minutes unknown (can't build a per-90 rate at all)
    joint = con.execute(
        """
        select
          sum(case when standard__npxG_Expected is not null and "playing_time__Min_Playing.Time" is null then 1 else 0 end) as npxg_known_minutes_unknown,
          sum(case when standard__npxG_Expected is not null and "playing_time__Min_Playing.Time" is not null then 1 else 0 end) as npxg_known_minutes_known
        from fbref_perf
        """
    ).fetchdf().iloc[0]
    rows.append({"population": "fbref_perf", "base_rows": perf_base,
                 "field": "npxg_known_but_minutes_unknown_JOINT",
                 "present_rows": int(joint.npxg_known_minutes_unknown), "present_pct": None})
    rows.append({"population": "fbref_perf", "base_rows": perf_base,
                 "field": "npxg_known_and_minutes_known_JOINT",
                 "present_rows": int(joint.npxg_known_minutes_known), "present_pct": None})
    return pd.DataFrame(rows)


def _sha256(path: Path, chunk: int = 2**20) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def full_data_manifest(con: duckdb.DuckDBPyConnection) -> dict:
    source_files = [
        DATA / "warehouse.duckdb",
        DATA / "fbref" / "perf_player_season.parquet",
        DATA / "merged" / "transfers_canonical.parquet",
        DATA / "master" / "players_master.parquet",
    ]
    hashes = {str(p.relative_to(REPO)): _sha256(p) for p in source_files}
    schema = {
        tbl: con.execute(f"select count(*) from {tbl}").fetchone()[0]
        for tbl in ["fbref_perf", "transfers_canonical", "players_master"]
    }
    return {
        "command": "python3 -m validate.v2_full_data",
        "determinism_note": "Manifest omits commit/branch so tracked reports can be regenerated "
                             "byte-for-byte across commits (same convention as validate.data_audit). "
                             "Data hashes below make the manifest sensitive to data changes even "
                             "though it stays stable across code-only commits.",
        "warehouse": str((DATA / "warehouse.duckdb").relative_to(REPO)),
        "source_file_sha256": hashes,
        "table_row_counts_schema_proxy": schema,
        "locked_season_min": LOCKED_SEASON_MIN,
        "seeds": {"impact.evidence._check": 0, "validate.v2_fee_prototypes": 0},
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
    artifacts["missingness_patterns"] = str(_write_csv(missingness_patterns(con), "missingness_patterns.csv").relative_to(REPO))

    all_transfers = con.execute("select transfer_uid, season from transfers_canonical").fetchdf()
    artifacts["locked_test_audit"] = str(
        write_locked_audit(all_transfers, OUT / "locked_test_audit.json").relative_to(REPO)
    )

    manifest_path = OUT / "full_data_manifest.json"
    manifest = full_data_manifest(con)
    manifest["outputs"] = artifacts
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    artifacts["full_data_manifest"] = str(manifest_path.relative_to(REPO))

    print(json.dumps(artifacts, indent=2, sort_keys=True))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
