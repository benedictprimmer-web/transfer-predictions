"""Reproducible data audit for the transfer-predictions repository.

This script deliberately profiles the built artifacts in-place. It does not
fetch data, rebuild models, or write raw-data derivatives; it only writes small
summary tables under reports/data-audit/.

Run:
    python3 -m validate.data_audit
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
OUT = REPO / "reports" / "data-audit"


def _write_csv(df: pd.DataFrame, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    df.to_csv(path, index=False)
    return path


def _write_json(obj, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")
    return path


def _git(cmd: list[str]) -> str:
    return subprocess.check_output(["git", *cmd], cwd=REPO, text=True).strip()


def _size(path: Path) -> tuple[int, int | None]:
    if not path.exists():
        return 0, None
    compressed = path.stat().st_size
    uncompressed = None
    if path.suffix == ".gz":
        try:
            import gzip

            with gzip.open(path, "rb") as f:
                uncompressed = len(f.read())
        except Exception:
            uncompressed = None
    return compressed, uncompressed


SOURCE_META = {
    "data/transfermarkt/transfers.csv.gz": ("Transfermarkt-derived dcaribou/player-scores R2", "CC0 claimed upstream; verify TM database-rights risk before commercial use", "ingest/transfermarkt.py"),
    "data/transfermarkt/player_valuations.csv.gz": ("Transfermarkt-derived dcaribou/player-scores R2", "CC0 claimed upstream; market values are consensus estimates, not ground truth", "ingest/transfermarkt.py"),
    "data/transfermarkt/players.csv.gz": ("Transfermarkt-derived dcaribou/player-scores R2", "CC0 claimed upstream; current snapshot fields leak for historical contracts", "ingest/transfermarkt.py"),
    "data/merged/transfers_canonical.parquet": ("Merged Transfermarkt estates plus raw harvest", "Not safe for public/commercial redistribution without TM/source review", "ingest/merge.py"),
    "data/warehouse.duckdb": ("Local DuckDB views over tracked artifacts", "Derived index; same restrictions as source tables", "ingest/warehouse.py"),
    "data/understat/shots.parquet": ("Understat shot data", "Terms unclear for commercial redistribution", "ingest/understat.py"),
    "data/fbref/perf_player_season.parquet": ("FBref/Stathead-style player seasons", "Proprietary/terms risk; do not redistribute publicly without review", "ingest/fbref_perf.py"),
    "data/fbref_shots/shots_selling.parquet": ("FBref shot data for selling leagues", "Proprietary/terms risk; do not redistribute publicly without review", "ingest/fbref_shots.py"),
    "data/wages/wages_fifa.parquet": ("FIFA/SoFIFA-derived wage prior", "Game-derived wage proxy; commercial redistribution needs review", "ingest/wages_fifa.py"),
    "data/wages/capology_all_seasons.parquet": ("Capology scrape/cache", "Not redistributable; proprietary wage estimates", "ingest/wages_capology.py"),
    "data/master/contracts.parquet": ("Transfermarkt current/PIT contract-derived records", "Current snapshots leak for historical decisions unless PIT flag proves otherwise", "ingest/contracts.py"),
    "data/master/injuries.parquet": ("Transfermarkt injury histories", "TM/source rights need review", "ingest/injuries.py"),
    "data/strength/clubelo_history.csv": ("ClubElo history/API or mirror", "Licence not formally verified", "ingest/strength.py"),
    "data/crosswalk/players.csv": ("Derived Understat/TM player crosswalk", "Redistribution inherits source-name/id risks", "ingest/crosswalk_players.py"),
    "data/money/fee_ranker.csv": ("Derived fee model board", "Derived model output; includes source-derived fields", "money/fees.py"),
    "data/money/scout_arsenal.csv": ("Derived NPV/scout board", "Derived model output; includes source-derived fields", "money/scout.py"),
    "data/money/talent_scores.csv": ("Derived talent-vs-price panel", "Derived model output; includes source-derived fields", "impact/talent.py"),
    "data/impact/possession_value.parquet": ("Derived possession/xT-style value", "Derived from source event/player data", "ingest/possession_value.py"),
    "data/impact/defensive_value.parquet": ("Derived defensive value summary", "Derived from source event/player data", "ingest/defensive_value.py"),
    "data/stage4/panel.csv": ("Derived completed-mover validation panel", "Derived validation artifact", "validate/stage4.py"),
}


WAREHOUSE_KEYS = {
    "transfers_canonical": ["transfer_uid"],
    "valuations": ["player_id", "date"],
    "players_master": ["tm_player_id"],
    "contracts": ["tm_player_id"],
    "injuries": ["tm_player_id"],
    "wages_fifa": ["tm_player_id", "edition_year"],
    "crosswalk_players": ["us_player_id", "tm_player_id"],
    "crosswalk_matches": ["understat_game_id", "tm_game_id"],
    "fbref_perf": ["fbref_id", "Season_End_Year", "Comp", "Squad"],
    "fbref_defense": ["tm_player_id", "season_end_year", "comp", "squad"],
    "fbref_niche": ["tm_player_id", "season_end_year", "comp", "squad"],
    "shots": ["league", "season", "game_id", "minute", "player_id", "x", "y"],
    "shots_selling": ["league", "season", "match_id", "minute", "fbref_id", "xg"],
    "clubelo_history": ["club", "date"],
    "transfer_performance_link_safe": ["transfer_uid", "perf_season"],
}


def file_inventory() -> pd.DataFrame:
    rows = []
    for rel, (source, licence, producer) in SOURCE_META.items():
        p = REPO / rel
        compressed, uncompressed = _size(p)
        rows.append(
            {
                "path": rel,
                "exists": p.exists(),
                "compressed_bytes": compressed,
                "uncompressed_bytes_if_gzip": uncompressed,
                "source": source,
                "licence_commercial_redistribution": licence,
                "producer_script": producer,
                "git_tracked": bool(subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0),
                "rebuild_status_from_clean_checkout": "tracked artifact or produced by listed script; network/raw-source rebuild not attempted in audit",
            }
        )
    return pd.DataFrame(rows)


def warehouse_inventory(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    rows = []
    for (name,) in con.execute("show tables").fetchall():
        desc = con.execute(f'describe "{name}"').fetchdf()
        cols = desc["column_name"].tolist()
        n = con.execute(f'select count(*) from "{name}"').fetchone()[0]
        date_cols = [c for c in cols if c.lower() in {"date", "transfer_date"} or c.lower().endswith("_date")]
        earliest, latest = None, None
        if date_cols:
            c = date_cols[0]
            try:
                earliest, latest = con.execute(f'select min(try_cast("{c}" as date)), max(try_cast("{c}" as date)) from "{name}"').fetchone()
            except Exception:
                pass
        key = WAREHOUSE_KEYS.get(name, [])
        dup = None
        if key and all(k in cols for k in key):
            expr = ", ".join([f'"{k}"' for k in key])
            dup = con.execute(
                f'select coalesce(sum(cnt - 1),0) from (select {expr}, count(*) cnt from "{name}" group by {expr} having count(*) > 1)'
            ).fetchone()[0]
        rows.append(
            {
                "table_or_view": name,
                "rows": n,
                "columns": len(cols),
                "date_column_used": date_cols[0] if date_cols else "",
                "earliest_date": earliest,
                "latest_date": latest,
                "intended_grain_key_tested": "|".join(key),
                "duplicate_key_rows": dup,
            }
        )
    return pd.DataFrame(rows)


def canonical_summary(con: duckdb.DuckDBPyConnection) -> dict:
    sqls = {
        "current_canonical_rows": "select count(*) from transfers_canonical",
        "canonical_unique_transfer_uid": "select count(distinct transfer_uid) from transfers_canonical",
        "canonical_duplicate_transfer_uid_rows": "select coalesce(sum(cnt-1),0) from (select transfer_uid, count(*) cnt from transfers_canonical group by 1 having count(*)>1)",
        "canonical_distinct_deal_key": "select count(distinct coalesce(cast(player_id as varchar),'?')||'|'||coalesce(cast(season as varchar),'?')||'|'||coalesce(\"window\",'?')||'|'||coalesce(from_club_name,'?')||'|'||coalesce(to_club_name,'?')) from transfers_canonical",
        "player_id_null_rows": "select count(*) from transfers_canonical where player_id is null",
        "positive_fee_rows_all_types": "select count(*) from transfers_canonical where fee_eur > 0",
        "positive_fee_rows_paid_permanent": "select count(*) from transfers_canonical where transfer_type='permanent' and fee_eur > 0",
        "trainable_fee_rows_current_filter": "select count(*) from transfers_canonical where fee_eur > 0 and market_value_eur is not null and player_age is not null and coalesce(fee_suspect,false)=false",
        "market_value_nonnull_rows": "select count(*) from transfers_canonical where market_value_eur is not null",
        "market_value_pit_rows": "select count(*) from transfers_canonical where mv_is_point_in_time",
        "exact_transfer_date_rows": "select count(*) from transfers_canonical where date_source in ('exact','exact_raw')",
        "proxy_transfer_date_rows": "select count(*) from transfers_canonical where date_source='proxy'",
        "undated_transfer_rows": "select count(*) from transfers_canonical where transfer_date is null and date is null",
    }
    out = {}
    for k, q in sqls.items():
        out[k] = con.execute(q).fetchone()[0]
    out["canonical_time_range"] = con.execute("select min(season), max(season), min(cast(date as date)), max(cast(date as date)) from transfers_canonical").fetchone()
    out["filter_definitions"] = sqls
    return out


def transaction_taxonomy(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    q = """
    select
      season,
      case
        when transfer_type='permanent' and fee_eur > 0 then 'paid_permanent_transfer'
        when transfer_type='free' then 'disclosed_free_transfer'
        when transfer_type='permanent' and fee_undisclosed then 'permanent_undisclosed_fee'
        when transfer_type='permanent' and fee_eur is null then 'permanent_unknown_fee'
        when transfer_type='loan' and fee_eur > 0 then 'loan_with_fee'
        when transfer_type='loan' and (fee_eur is null or fee_eur=0) then 'loan_without_fee_or_unknown'
        when transfer_type='end_of_loan' then 'loan_return'
        when transfer_type='retirement' then 'retirement_or_internal_exit'
        when transfer_type is null then 'genuinely_unknown'
        else 'other_review_required'
      end as taxonomy,
      coalesce(fee_source,'no_fee_source') as fee_source,
      count(*) as row_count,
      count(fee_eur) as fee_nonnull_rows,
      sum(case when fee_eur > 0 then 1 else 0 end) as positive_fee_rows
    from transfers_canonical
    group by 1,2,3
    order by 1,2,3
    """
    return con.execute(q).fetchdf()


def fee_disclosure(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    raw = pd.read_csv(DATA / "transfermarkt" / "transfers.csv.gz", compression="gzip", usecols=["transfer_fee", "market_value_in_eur", "transfer_date", "transfer_season"])
    raw_fee = pd.to_numeric(raw.transfer_fee, errors="coerce") > 0
    rows = [
        {
            "claim_context": "thin R2 Transfermarkt transfers.csv.gz",
            "source_table": "data/transfermarkt/transfers.csv.gz",
            "row_grain": "one transfer row from source file",
            "filter": "all rows; disclosed fee := transfer_fee > 0",
            "time_range": f"{raw.transfer_date.min()} to {raw.transfer_date.max()}",
            "denominator": len(raw),
            "numerator": int(raw_fee.sum()),
            "coverage_pct": float(raw_fee.mean() * 100),
        }
    ]
    for label, where in [
        ("current canonical, all transaction types", "1=1"),
        ("current canonical, permanent only", "transfer_type='permanent'"),
        ("current canonical, paid-permanent training eligible", "transfer_type='permanent' and fee_eur > 0 and market_value_eur is not null and player_age is not null and coalesce(fee_suspect,false)=false"),
        ("current canonical, all positive fee model-ready filter", "fee_eur > 0 and market_value_eur is not null and player_age is not null and coalesce(fee_suspect,false)=false"),
    ]:
        den = con.execute(f"select count(*) from transfers_canonical where {where if 'fee_eur > 0' not in where else '1=1'}").fetchone()[0]
        num = con.execute(f"select count(*) from transfers_canonical where ({where}) and fee_eur > 0").fetchone()[0]
        rows.append(
            {
                "claim_context": label,
                "source_table": "warehouse.transfers_canonical",
                "row_grain": "canonical transfer row",
                "filter": where + "; disclosed fee := fee_eur > 0",
                "time_range": str(con.execute("select min(season), max(season) from transfers_canonical").fetchone()),
                "denominator": den,
                "numerator": num,
                "coverage_pct": float(num / den * 100) if den else np.nan,
            }
        )
    return pd.DataFrame(rows)


def fee_selection(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    q = """
    select
      case when season < 2000 then '<2000'
           when season < 2010 then '2000-2009'
           when season < 2020 then '2010-2019'
           else '2020+' end as era,
      coalesce(to_league,'Unknown') as to_league,
      coalesce(pos_group,'Unknown') as pos_group,
      case when player_age is null then 'unknown'
           when player_age < 21 then '<21'
           when player_age < 25 then '21-24'
           when player_age < 29 then '25-28'
           when player_age < 33 then '29-32'
           else '33+' end as age_band,
      coalesce(transfer_type,'Unknown') as transfer_type,
      count(*) as row_count,
      sum(case when fee_eur > 0 then 1 else 0 end) as positive_fee_rows,
      avg(case when fee_eur > 0 then 1.0 else 0.0 end) as positive_fee_rate,
      avg(case when market_value_eur is not null then 1.0 else 0.0 end) as mv_coverage
    from transfers_canonical
    group by 1,2,3,4,5
    order by row_count desc
    limit 500
    """
    return con.execute(q).fetchdf()


def joins_and_linkage(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    out = {}
    out["crosswalk_collisions"] = con.execute(
        """
        select metric, row_count from (
          select 'tm_to_understat_one_to_many' metric, count(*) row_count from (
            select tm_player_id from crosswalk_players group by 1 having count(distinct us_player_id)>1
          )
          union all
          select 'understat_to_tm_one_to_many', count(*) from (
            select us_player_id from crosswalk_players group by 1 having count(distinct tm_player_id)>1
          )
          union all
          select 'crosswalk_rows', count(*) from crosswalk_players
        )
        """
    ).fetchdf()
    out["understat_name_join"] = con.execute(
        """
        select
          count(*) as crosswalk_rows,
          count(distinct lower(us_name)) as distinct_normalized_names,
          count(*) - count(distinct lower(us_name)) as duplicate_name_rows
        from crosswalk_players
        """
    ).fetchdf()
    out["join_funnel_transfer_perf"] = con.execute(
        """
        select step, row_count from (
          select 1 ord, 'canonical transfers' step, count(*) row_count from transfers_canonical
          union all select 2, 'canonical with player_id', count(*) from transfers_canonical where player_id is not null
          union all select 3, 'player_master fbref-linked players', count(*) from players_master where has_fbref
          union all select 4, 'safe transfer-performance link rows', count(*) from transfer_performance_link_safe
          union all select 5, 'safe link distinct transfers', count(distinct transfer_uid) from transfer_performance_link_safe
        ) order by ord
        """
    ).fetchdf()
    out["linked_vs_unlinked"] = con.execute(
        """
        with base as (
          select t.*,
                 p.has_fbref,
                 p.has_understat,
                 exists(select 1 from transfer_performance_link_safe l where l.transfer_uid=t.transfer_uid) as has_prior_perf_link
          from transfers_canonical t
          left join players_master p on t.player_id=p.tm_player_id
        )
        select
          case when has_prior_perf_link then 'linked_prior_perf' else 'unlinked_prior_perf' end as group_name,
          count(*) row_count,
          avg(case when fee_eur>0 then 1.0 else 0.0 end) positive_fee_rate,
          avg(case when market_value_eur is not null then 1.0 else 0.0 end) mv_rate,
          avg(player_age) avg_age,
          avg(case when to_is_top5 then 1.0 else 0.0 end) to_top5_rate
        from base group by 1
        """
    ).fetchdf()
    return out


def timestamp_gaps(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    q = """
    select
      date_source,
      mv_source,
      mv_is_point_in_time,
      count(*) row_count,
      approx_quantile(abs(date_diff('day', cast(transfer_date as date), cast(date as date))), 0.5) as median_transferdate_proxy_gap_days,
      approx_quantile(abs(date_diff('day', cast(transfer_date as date), cast(date as date))), 0.9) as p90_transferdate_proxy_gap_days,
      sum(case when date_source in ('exact','exact_raw') then 1 else 0 end) exact_date_rows,
      sum(case when date_source='proxy' then 1 else 0 end) proxy_date_rows,
      sum(case when date is null then 1 else 0 end) undated_rows
    from transfers_canonical
    group by 1,2,3
    order by row_count desc
    """
    return con.execute(q).fetchdf()


def target_funnels(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    base = con.execute("select count(*) from transfers_canonical").fetchone()[0]
    rows = []
    specs = [
        ("next-season sporting performance", "exists(select 1 from transfer_performance_link_safe l where l.transfer_uid=t.transfer_uid)", "prior performance only in current safe link; future label not audited as leak-safe here"),
        ("next-season minutes/availability", "exists(select 1 from transfer_performance_link_safe l where l.transfer_uid=t.transfer_uid and l.minutes is not null)", "minutes present in safe prior link, but next-season target must be rebuilt with post-transfer horizon rules"),
        ("forward two-year market-value change", "t.player_id is not null and exists(select 1 from valuations v where v.player_id=t.player_id and v.date > cast(t.date as date) + interval 300 day and v.date <= cast(t.date as date) + interval 800 day)", "survival-observed valuation label; biased toward still-observed players"),
        ("realized resale/transfer fee", "t.player_id is not null and exists(select 1 from transfers_canonical f where f.player_id=t.player_id and f.date > t.date and f.fee_eur > 0)", "selected on resale and fee disclosure"),
        ("starter retention", "t.player_id is not null and exists(select 1 from transfer_performance_link_safe l where l.transfer_uid=t.transfer_uid)", "not directly available without destination-season appearances"),
        ("early loan or termination", "t.player_id is not null and exists(select 1 from transfers_canonical f where f.player_id=t.player_id and f.date > t.date and f.date <= t.date + interval 730 day and f.transfer_type in ('loan','end_of_loan','free'))", "proxy target; requires taxonomy review"),
        ("replacement-based importance", "exists(select 1 from fbref_perf p where cast(p.tm_player_id as bigint)=t.player_id)", "performance-rich subset only; not full deployment population"),
    ]
    for target, pred, caveat in specs:
        n = con.execute(f"select count(*) from transfers_canonical t where {pred}").fetchone()[0]
        by_period = con.execute(
            f"""
            select
              case when season < 2010 then '<2010'
                   when season < 2020 then '2010-2019'
                   else '2020+' end as period,
              count(*) as eligible_rows
            from transfers_canonical t where {pred}
            group by 1 order by 1
            """
        ).fetchdf()
        rows.append(
            {
                "candidate_target": target,
                "source_table": "warehouse.transfers_canonical plus linked tables",
                "row_grain": "canonical transfer row",
                "eligibility_filter": pred,
                "base_rows": base,
                "eligible_rows": n,
                "eligible_pct": n / base * 100,
                "period_counts": by_period.to_json(orient="records"),
                "leakage_or_selection_note": caveat,
                "simpler_baseline": "age + position + prior market value/league cohort baseline, evaluated by expanding window",
            }
        )
    return pd.DataFrame(rows)


def temporal_folds(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    periods = [
        ("design_A", "train", "season <= 2017"),
        ("design_A", "tune", "season between 2018 and 2019"),
        ("design_A", "calibration", "season between 2020 and 2021"),
        ("design_A", "final_test", "season >= 2022"),
        ("design_B", "train", "season <= 2019"),
        ("design_B", "tune", "season = 2020"),
        ("design_B", "calibration", "season = 2021"),
        ("design_B", "final_test", "season >= 2022"),
    ]
    rows = []
    for design, split, filt in periods:
        rows.append(
            {
                "design": design,
                "split": split,
                "filter": filt,
                "all_transfers": con.execute(f"select count(*) from transfers_canonical where {filt}").fetchone()[0],
                "paid_permanent": con.execute(f"select count(*) from transfers_canonical where {filt} and transfer_type='permanent' and fee_eur>0").fetchone()[0],
                "model_ready_fee": con.execute(f"select count(*) from transfers_canonical where {filt} and fee_eur>0 and market_value_eur is not null and player_age is not null and coalesce(fee_suspect,false)=false").fetchone()[0],
                "mv_forward_2y_observed": con.execute(f"select count(*) from transfers_canonical t where {filt} and t.player_id is not null and exists(select 1 from valuations v where v.player_id=t.player_id and v.date > cast(t.date as date) + interval 300 day and v.date <= cast(t.date as date) + interval 800 day)").fetchone()[0],
            }
        )
    return pd.DataFrame(rows)


def coverage(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    q = """
    select
      coalesce(pos_group,'Unknown') as position_or_role,
      coalesce(to_league,'Unknown') as to_league,
      case when player_age is null then 'unknown'
           when player_age < 21 then '<21'
           when player_age < 25 then '21-24'
           when player_age < 29 then '25-28'
           when player_age < 33 then '29-32'
           else '33+' end as age_band,
      count(*) row_count,
      avg(case when fee_eur>0 then 1.0 else 0.0 end) fee_rate,
      avg(case when market_value_eur is not null then 1.0 else 0.0 end) mv_rate,
      avg(case when exists(select 1 from fbref_perf p where cast(p.tm_player_id as bigint)=transfers_canonical.player_id) then 1.0 else 0.0 end) fbref_perf_rate,
      avg(case when exists(select 1 from wages_fifa w where w.tm_player_id=transfers_canonical.player_id) then 1.0 else 0.0 end) wage_prior_rate
    from transfers_canonical
    group by 1,2,3
    order by row_count desc
    limit 500
    """
    return con.execute(q).fetchdf()


def existing_results() -> pd.DataFrame:
    rows = []
    # Stage 4 real gate.
    try:
        from ingest.understat import read_shots
        from validate.stage4 import add_prediction, boot_corr, partial_slope, team_eff_before

        panel = pd.read_csv(DATA / "stage4" / "panel.csv")
        p = add_prediction(panel, team_eff_before(read_shots()))
        pw = p[p.on_min >= 450]
        for target, frame, col in [("usage_efficiency_vs_wowy", pw, "wowy"), ("usage_efficiency_vs_team_delta", p, "delta_team_xgd90")]:
            r, (lo, hi), n = boot_corr(frame.predicted_gain, frame[col])
            rows.append({"result": target, "number": r, "ci_lo": lo, "ci_hi": hi, "n": n, "command": "python3 -m validate.stage4 run", "artifact": "reports/data-audit/existing_results.csv"})
        s, (lo, hi), n = partial_slope(p)
        rows.append({"result": "usage_efficiency_partial_slope", "number": s, "ci_lo": lo, "ci_hi": hi, "n": n, "command": "python3 -m validate.stage4 run", "artifact": "reports/data-audit/existing_results.csv"})
    except Exception as e:
        rows.append({"result": "stage4_real_gate_error", "number": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "n": 0, "command": "python3 -m validate.stage4 run", "artifact": str(e)})

    for file, label, cols in [
        (DATA / "money" / "backtest.csv", "npv_oof_backtest", None),
        (DATA / "money" / "backtest_named.csv", "npv_named_cases", None),
        (DATA / "money" / "fee_ranker.csv", "fee_ranker_rows", None),
        (DATA / "money" / "scout_arsenal.csv", "npv_board", None),
        (DATA / "money" / "talent_scores.csv", "talent_scores_rows", None),
    ]:
        if file.exists():
            d = pd.read_csv(file)
            rows.append({"result": label, "number": len(d), "ci_lo": np.nan, "ci_hi": np.nan, "n": len(d), "command": f"read {file.relative_to(REPO)}", "artifact": "reports/data-audit/existing_results.csv"})
            if label == "npv_board":
                npv_cols = [c for c in d.columns if "npv" in c.lower()]
                if npv_cols:
                    c = npv_cols[0]
                    rows.append({"result": "npv_board_positive_count", "number": int((pd.to_numeric(d[c], errors='coerce') > 0).sum()), "ci_lo": np.nan, "ci_hi": np.nan, "n": len(d), "command": f"read {file.relative_to(REPO)} column {c}", "artifact": "reports/data-audit/existing_results.csv"})
    return pd.DataFrame(rows)


def leakage_register() -> pd.DataFrame:
    rows = [
        ("future performance", "transfer_performance_link_safe", "perf_season < transfer_season only", "prior-history models", "target-period feature models", "assert all perf_season < transfer_season"),
        ("post-transfer market value", "valuations", "feature valuation must be strictly before prediction date", "fee-vs-consensus models with PIT MV", "future repricing features", "assert valuation.date < prediction_date"),
        ("current-state contracts", "contracts/players_master", "PIT only when contract_is_pit true or raw snapshot predates transfer", "prospective current-board context", "historical backtests without PIT", "assert contract snapshot date < transfer date"),
        ("wage snapshots", "wages_fifa/capology", "edition/season must be <= prediction season", "scenario costs when flagged observed/modelled", "silent imputation", "assert wage edition_year <= season"),
        ("destination-season information", "fbref_perf/transfer_performance_link", "only pre-transfer seasons as features", "post-transfer labels", "pre-transfer features", "assert feature season < transfer season"),
        ("encoders fitted outside folds", "model code", "fit within each temporal train split", "all models", "random full-sample preprocessing", "unit test pipeline fit per split"),
        ("random temporal splits", "money/fees.py history", "expanding-window only", "validation", "random KFold on market-inflated data", "grep/sklearn split audit plus fold table"),
        ("duplicate deals across folds", "transfers_canonical", "deal key must be assigned to one split", "all temporal CV", "same deal repeated train/test", "assert duplicate deal key not split"),
        ("player history across folds", "players longitudinal tables", "future seasons excluded", "history features", "future aggregates", "assert max feature season < prediction season"),
        ("target-derived inflation features", "money/inflation", "fit inflation index using training period only", "fee models", "full-history inflation in train", "assert inflation fit window <= train max"),
        ("future transfer-induced market value", "valuations", "future MV target must flag transfer-contaminated observations", "target feasibility only", "ground-truth value labels", "exclude/flag valuations after subsequent paid transfer"),
        ("calibration/test reuse", "validation reports", "calibration split separate from final test", "model calibration", "final test tuning", "fold table enforces separate periods"),
        ("buyer identity in buyer-agnostic value", "transfers_canonical.to_club_id", "exclude unless model estimand is buyer-specific", "buyer-specific surplus", "buyer-agnostic value models", "feature allowlist test"),
    ]
    return pd.DataFrame(rows, columns=["item", "source", "timestamp_rule", "permitted_models", "prohibited_models", "executable_assertion"])


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DATA / "warehouse.duckdb"), read_only=True)

    artifacts = {}
    artifacts["file_inventory"] = str(_write_csv(file_inventory(), "file_inventory.csv").relative_to(REPO))
    artifacts["warehouse_inventory"] = str(_write_csv(warehouse_inventory(con), "warehouse_inventory.csv").relative_to(REPO))
    artifacts["canonical_summary"] = str(_write_json(canonical_summary(con), "canonical_summary.json").relative_to(REPO))
    artifacts["transaction_taxonomy"] = str(_write_csv(transaction_taxonomy(con), "transaction_taxonomy_by_season.csv").relative_to(REPO))
    artifacts["fee_disclosure"] = str(_write_csv(fee_disclosure(con), "fee_disclosure_reconciliation.csv").relative_to(REPO))
    artifacts["fee_selection"] = str(_write_csv(fee_selection(con), "fee_selection_mnar_audit.csv").relative_to(REPO))
    artifacts["timestamp_gaps"] = str(_write_csv(timestamp_gaps(con), "timestamp_gap_summary.csv").relative_to(REPO))
    artifacts["target_funnels"] = str(_write_csv(target_funnels(con), "target_sample_funnels.csv").relative_to(REPO))
    artifacts["temporal_folds"] = str(_write_csv(temporal_folds(con), "temporal_fold_counts.csv").relative_to(REPO))
    artifacts["coverage"] = str(_write_csv(coverage(con), "position_league_coverage.csv").relative_to(REPO))
    artifacts["existing_results"] = str(_write_csv(existing_results(), "existing_results.csv").relative_to(REPO))
    artifacts["leakage_register"] = str(_write_csv(leakage_register(), "leakage_register.csv").relative_to(REPO))
    for name, df in joins_and_linkage(con).items():
        artifacts[name] = str(_write_csv(df, f"{name}.csv").relative_to(REPO))
    artifacts["run_manifest"] = str(
        _write_json(
            {
                "command": "python3 -m validate.data_audit",
                "git_commit": _git(["rev-parse", "HEAD"]),
                "git_branch": _git(["branch", "--show-current"]),
                "outputs": artifacts,
            },
            "run_manifest.json",
        ).relative_to(REPO)
    )
    print(json.dumps(artifacts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
