"""Executable V1 modelling-contract checks.

This module does not train models. It codifies the Phase 0 audit constraints as
data and policy assertions, then writes small manifests under
reports/model-contract/.

Run:
    python3 -m validate.modelling_contract
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
OUT = REPO / "reports" / "model-contract"

SUPPORTED_OUTFIELD = ("FWD", "MID", "DEF", "Attack", "Midfield", "Defender")
NAMED_DEVELOPMENT_CASES = ("Antony", "Erling Haaland", "Cristiano Ronaldo")

V1_FEE_SCOPE = f"""
transfer_type = 'permanent'
and fee_eur > 0
and mv_is_point_in_time
and date_source in ('exact','exact_raw')
and player_age between 18 and 29
and coalesce(pos_group,'') in {SUPPORTED_OUTFIELD}
and coalesce(fee_suspect,false) = false
and coalesce(fee_undisclosed,false) = false
"""

V1_DISCOVERY_SCOPE = f"""
player_id is not null
and mv_is_point_in_time
and date_source in ('exact','exact_raw')
and player_age between 18 and 29
and coalesce(pos_group,'') in {SUPPORTED_OUTFIELD}
"""

FEATURE_POLICY = [
    {
        "component": "negotiated_fee_v1_candidate",
        "allowed_features": "age, supported_position, origin/destination league, strictly pre-transfer market consensus, PIT contract years if contract_is_pit",
        "prohibited_features": "future performance, post-transfer market value, current-state contract snapshots, current-state wages, buyer identity for buyer-agnostic variants",
        "requires_buyer_context": False,
        "feature_cutoff_rule": "all features strictly before prediction cutoff; proxy-dated rows excluded from V1 fee scope",
    },
    {
        "component": "buyer_specific_surplus",
        "allowed_features": "buyer squad context, replacement set, buyer revenue curve, fee, wage, contract assumptions",
        "prohibited_features": "destination importance when buyer is unknown; final-test calibration; unflagged modelled wages",
        "requires_buyer_context": True,
        "feature_cutoff_rule": "buyer context must be known at prediction timestamp",
    },
]

OUTPUT_POLICY = [
    {
        "output": "fee_residual",
        "approved_label": "deviation from expected negotiated fee / market-consensus pricing",
        "prohibited_label": "true player value or genuine undervaluation",
        "requires_uncertainty": True,
    },
    {
        "output": "buyer_specific_surplus",
        "approved_label": "buyer-specific expected acquisition surplus",
        "prohibited_label": "available without named buyer context",
        "requires_uncertainty": True,
    },
    {
        "output": "wage_estimate",
        "approved_label": "observed wage or modelled wage, explicitly flagged",
        "prohibited_label": "unqualified wage",
        "requires_uncertainty": True,
    },
]


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool | None  # None = not run (e.g. missing environment dependency), not a pass or fail
    detail: str


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DATA / "warehouse.duckdb"), read_only=True)


def write_csv(df: pd.DataFrame, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    df.to_csv(path, index=False)
    return path


def write_json(obj, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    return path


def q1(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def _has_table(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    return con.execute(
        "select count(*) from information_schema.tables where table_name = ?", [name]
    ).fetchone()[0] > 0


def v1_key_expr() -> str:
    return """
    coalesce(cast(player_id as varchar),'?') || '|' ||
    strftime(cast(date as date),'%Y-%m-%d') || '|' ||
    coalesce(cast(from_club_id as varchar), from_club_name, '?') || '|' ||
    coalesce(cast(to_club_id as varchar), to_club_name, '?') || '|' ||
    coalesce(cast(fee_eur as varchar),'?')
    """


def fold_manifest(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    designs = [
        ("design_A_recommended", "train", "season <= 2018"),
        ("design_A_recommended", "tune", "season = 2019"),
        ("design_A_recommended", "calibration", "season between 2020 and 2021"),
        ("design_A_recommended", "locked_final_test", "season >= 2023"),
        ("design_B_historical_rolling", "train", "season <= 2017"),
        ("design_B_historical_rolling", "tune", "season between 2018 and 2019"),
        ("design_B_historical_rolling", "calibration", "season between 2020 and 2021"),
        ("design_B_historical_rolling", "diagnostic_recent", "season >= 2023"),
    ]
    has_link = _has_table(con, "transfer_performance_link_safe")
    rows = []
    for design, split, season_filter in designs:
        if has_link:
            prior_perf_link_rows = q1(
                con,
                f"""
                select count(*) from transfers_canonical t
                where {V1_DISCOVERY_SCOPE} and {season_filter}
                  and exists (
                    select 1 from transfer_performance_link_safe l
                    where l.transfer_uid=t.transfer_uid
                  )
                """,
            )
        else:
            # UNAVAILABLE_IN_THIS_ENVIRONMENT: transfer_performance_link_safe is materialized from
            # ESTATE_B_DIR, a raw source directory outside this repo's tracked data/ that is not
            # present in this checkout. This is a missing-data marker, not a zero finding.
            prior_perf_link_rows = pd.NA
        rows.append(
            {
                "design": design,
                "split": split,
                "season_filter": season_filter,
                "v1_negotiated_fee_rows": q1(con, f"select count(*) from transfers_canonical where {V1_FEE_SCOPE} and {season_filter}"),
                "v1_discovery_snapshot_rows": q1(con, f"select count(*) from transfers_canonical where {V1_DISCOVERY_SCOPE} and {season_filter}"),
                "forward_mv_diagnostic_rows": q1(
                    con,
                    f"""
                    select count(*) from transfers_canonical t
                    where {V1_DISCOVERY_SCOPE} and {season_filter}
                      and exists (
                        select 1 from valuations v
                        where v.player_id=t.player_id
                          and v.date > cast(t.date as date) + interval 300 day
                          and v.date <= cast(t.date as date) + interval 800 day
                      )
                    """,
                ),
                "prior_perf_link_rows": prior_perf_link_rows,
                "prior_perf_link_note": (
                    "ok" if has_link else
                    "UNAVAILABLE_IN_THIS_ENVIRONMENT: ESTATE_B_DIR not present; not a zero finding"
                ),
            }
        )
    return pd.DataFrame(rows)


def component_support(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    has_link = _has_table(con, "transfer_performance_link_safe")
    link_note = (
        None if has_link else
        "UNAVAILABLE_IN_THIS_ENVIRONMENT: ESTATE_B_DIR not present; evidence_count not computed, not zero"
    )
    rows = [
        {
            "component": "future_minutes_availability",
            "v1_status": "NOT V1-SUPPORTED",
            "row_grain": "player snapshot / transfer candidate",
            "evidence_count": q1(con, "select count(*) from transfers_canonical t where exists(select 1 from transfer_performance_link_safe l where l.transfer_uid=t.transfer_uid and l.minutes is not null)") if has_link else pd.NA,
            "reason": "current link is prior-performance-safe, not a destination next-season label builder" + (f" | {link_note}" if link_note else ""),
        },
        {
            "component": "future_sporting_contribution",
            "v1_status": "NOT V1-SUPPORTED",
            "row_grain": "player snapshot / transfer candidate",
            "evidence_count": q1(con, "select count(*) from transfers_canonical t where exists(select 1 from transfer_performance_link_safe l where l.transfer_uid=t.transfer_uid)") if has_link else pd.NA,
            "reason": "usage/WOWY signal is weak and target builder is incomplete for destination-season contribution" + (f" | {link_note}" if link_note else ""),
        },
        {
            "component": "market_consensus_value",
            "v1_status": "SUPPORTED AS INPUT, NOT GROUND TRUTH",
            "row_grain": "player-date valuation",
            "evidence_count": q1(con, "select count(*) from valuations"),
            "reason": "Transfermarkt valuation is consensus proxy with PIT availability on canonical rows",
        },
        {
            "component": "negotiated_transfer_fee",
            "v1_status": "V1-CANDIDATE WITH EXACT-DATE PAID-PERMANENT SCOPE",
            "row_grain": "paid permanent transfer",
            "evidence_count": q1(con, f"select count(*) from transfers_canonical where {V1_FEE_SCOPE}"),
            "reason": "continuous target restricted to disclosed paid permanent deals with PIT MV and exact dates",
        },
        {
            "component": "wage",
            "v1_status": "NOT V1-SUPPORTED AS OBSERVED HISTORICAL LABEL",
            "row_grain": "player-season wage",
            "evidence_count": q1(con, "select count(*) from wages_fifa"),
            "reason": "FIFA/Capology/modelled wages require source/status separation and licensing review",
        },
        {
            "component": "replacement_based_importance",
            "v1_status": "DECISION LAYER ONLY",
            "row_grain": "buyer-player-role snapshot",
            "evidence_count": 0,
            "reason": "no approved supervised label; requires named buyer squad context",
        },
        {
            "component": "buyer_specific_economic_value",
            "v1_status": "NOT V1-SUPPORTED AS HEADLINE SCORE",
            "row_grain": "buyer-player-contract scenario",
            "evidence_count": 98,
            "reason": "current NPV board has 0/98 positives and benefit generalization is mixed",
        },
    ]
    return pd.DataFrame(rows)


def check_transaction_scope(con: duckdb.DuckDBPyConnection) -> list[Check]:
    total = q1(con, "select count(*) from transfers_canonical")
    categorized = q1(
        con,
        """
        select count(*) from (
          select case
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
          end as taxonomy from transfers_canonical
        )
        """,
    )
    v1_bad_types = q1(con, f"select count(*) from transfers_canonical where ({V1_FEE_SCOPE}) and transfer_type <> 'permanent'")
    v1_undisclosed = q1(con, f"select count(*) from transfers_canonical where ({V1_FEE_SCOPE}) and coalesce(fee_undisclosed,false)")
    v1_zero = q1(con, f"select count(*) from transfers_canonical where ({V1_FEE_SCOPE}) and coalesce(fee_eur,0)=0")
    return [
        Check("transaction_taxonomy_covers_all_rows", categorized == total, f"{categorized}/{total} rows categorized"),
        Check("continuous_fee_scope_paid_permanent_only", v1_bad_types == 0, f"{v1_bad_types} non-permanent rows in V1 fee scope"),
        Check("undisclosed_fee_excluded_from_continuous_target", v1_undisclosed == 0, f"{v1_undisclosed} undisclosed rows in V1 fee scope"),
        Check("zero_fee_excluded_from_continuous_target", v1_zero == 0, f"{v1_zero} zero/null fee rows in V1 fee scope"),
    ]


def check_timestamp_integrity(con: duckdb.DuckDBPyConnection) -> list[Check]:
    proxy_in_v1 = q1(con, f"select count(*) from transfers_canonical where ({V1_FEE_SCOPE}) and date_source='proxy'")
    non_pit_mv = q1(con, f"select count(*) from transfers_canonical where ({V1_FEE_SCOPE}) and not coalesce(mv_is_point_in_time,false)")
    non_pit_contract = q1(
        con,
        f"""
        select count(*) from transfers_canonical
        where ({V1_FEE_SCOPE})
          and contract_years_remaining is not null
          and not coalesce(contract_is_pit,false)
        """,
    )
    has_link = _has_table(con, "transfer_performance_link_safe")
    if has_link:
        future_perf = q1(con, "select count(*) from transfer_performance_link_safe where perf_season >= transfer_season")
        link_check = Check("future_performance_excluded_from_safe_link", future_perf == 0, f"{future_perf} future performance rows in safe link")
    else:
        link_check = Check(
            "future_performance_excluded_from_safe_link", None,
            "NOT RUN: transfer_performance_link_safe unavailable in this environment "
            "(ESTATE_B_DIR not present) — assertion not evaluated, not passed or failed",
        )
    prohibited_fee_features = [f for f in FEATURE_POLICY[0]["prohibited_features"].split(", ") if "future" in f or "post-transfer" in f or "current-state" in f]
    return [
        Check("proxy_dated_rows_excluded_from_v1_fee_scope", proxy_in_v1 == 0, f"{proxy_in_v1} proxy rows in V1 fee scope"),
        Check("post_transfer_market_value_excluded", non_pit_mv == 0, f"{non_pit_mv} non-PIT MV rows in V1 fee scope"),
        Check("current_state_contract_excluded_historically", non_pit_contract == 0, f"{non_pit_contract} non-PIT contract rows in V1 fee scope"),
        link_check,
        Check("feature_policy_names_prohibited_temporal_features", len(prohibited_fee_features) >= 3, ", ".join(prohibited_fee_features)),
    ]


def check_join_and_fold_integrity(con: duckdb.DuckDBPyConnection, folds: pd.DataFrame) -> list[Check]:
    key = v1_key_expr()
    rows, distinct_keys = con.execute(f"select count(*), count(distinct {key}) from transfers_canonical where {V1_FEE_SCOPE}").fetchone()
    join_rows = q1(
        con,
        f"""
        select count(*) from transfers_canonical t
        left join players_master p on t.player_id=p.tm_player_id
        where {V1_FEE_SCOPE}
        """,
    )
    ambiguous_tm = q1(con, "select count(*) from (select tm_player_id from crosswalk_players group by 1 having count(distinct us_player_id)>1)")
    fold_keys = {}
    for _, row in folds.iterrows():
        if row["design"] != "design_A_recommended":
            continue
        keys = set(
            r[0]
            for r in con.execute(
                f"select {key} from transfers_canonical where {V1_FEE_SCOPE} and {row['season_filter']}"
            ).fetchall()
        )
        fold_keys[row["split"]] = keys
    overlap = 0
    splits = list(fold_keys)
    for i, left in enumerate(splits):
        for right in splits[i + 1 :]:
            overlap += len(fold_keys[left] & fold_keys[right])
    return [
        Check("v1_transfer_prediction_key_unique", rows == distinct_keys, f"{rows} rows, {distinct_keys} distinct V1 keys"),
        Check("player_master_join_no_expansion", join_rows == rows, f"{join_rows} joined rows from {rows} V1 rows"),
        Check("crosswalk_ambiguity_known_and_not_silent", ambiguous_tm == 3, f"{ambiguous_tm} TM-to-Understat ambiguous ids; V1 fee scope does not consume this crosswalk"),
        Check("same_deal_does_not_cross_recommended_folds", overlap == 0, f"{overlap} overlapping V1 keys across design_A folds"),
    ]


def check_population_and_output_policy(con: duckdb.DuckDBPyConnection) -> list[Check]:
    gk_in_v1 = q1(con, f"select count(*) from transfers_canonical where ({V1_DISCOVERY_SCOPE}) and pos_group in ('GK','Goalkeeper')")
    unsupported_pos = q1(con, f"select count(*) from transfers_canonical where ({V1_DISCOVERY_SCOPE}) and coalesce(pos_group,'') not in {SUPPORTED_OUTFIELD}")
    exact_missing_critical = q1(con, f"select count(*) from transfers_canonical where ({V1_FEE_SCOPE}) and (player_age is null or market_value_eur is null or fee_eur is null)")
    semantics_ok = all("true player value" not in row["approved_label"] for row in OUTPUT_POLICY)
    buyer_context_required = any(row["output"] == "buyer_specific_surplus" and "without named buyer" in row["prohibited_label"] for row in OUTPUT_POLICY)
    wage_flagged = any(row["output"] == "wage_estimate" and "flagged" in row["approved_label"] for row in OUTPUT_POLICY)
    return [
        Check("unsupported_goalkeepers_abstain", gk_in_v1 == 0, f"{gk_in_v1} GK rows in V1 discovery scope"),
        Check("unsupported_roles_abstain", unsupported_pos == 0, f"{unsupported_pos} unsupported-position rows in V1 discovery scope"),
        Check("missing_critical_pit_inputs_abstain", exact_missing_critical == 0, f"{exact_missing_critical} V1 fee rows missing critical inputs"),
        Check("fee_residual_not_labelled_true_value", semantics_ok, "fee residual approved label is negotiated-fee deviation"),
        Check("buyer_surplus_requires_buyer_context", buyer_context_required, "buyer-specific surplus unavailable without named buyer context"),
        Check("modelled_wage_visibly_distinct", wage_flagged, "wage policy requires observed/modelled status"),
    ]


def run_checks(con: duckdb.DuckDBPyConnection, folds: pd.DataFrame) -> pd.DataFrame:
    checks = []
    checks.extend(check_transaction_scope(con))
    checks.extend(check_timestamp_integrity(con))
    checks.extend(check_join_and_fold_integrity(con, folds))
    checks.extend(check_population_and_output_policy(con))
    df = pd.DataFrame([c.__dict__ for c in checks])
    return df.sort_values("name").reset_index(drop=True)


def main() -> int:
    con = connect()
    folds = fold_manifest(con)
    support = component_support(con)
    checks = run_checks(con, folds)

    artifacts = {
        "fold_manifest": str(write_csv(folds, "fold_manifest.csv").relative_to(REPO)),
        "component_support": str(write_csv(support, "component_support.csv").relative_to(REPO)),
        "acceptance_results": str(write_csv(checks, "acceptance_results.csv").relative_to(REPO)),
        "feature_policy": str(write_csv(pd.DataFrame(FEATURE_POLICY), "feature_policy.csv").relative_to(REPO)),
        "output_policy": str(write_csv(pd.DataFrame(OUTPUT_POLICY), "output_policy.csv").relative_to(REPO)),
        "named_development_cases": str(write_csv(pd.DataFrame({"player": NAMED_DEVELOPMENT_CASES, "status": "development_sanity_case_not_untouched_test"}), "named_development_cases.csv").relative_to(REPO)),
    }
    write_json({"command": "python3 -m validate.modelling_contract", "outputs": artifacts}, "run_manifest.json")

    not_run = checks[checks.passed.isna()]
    failed = checks[checks.passed == False]  # noqa: E712 — explicit False, distinct from NaN "not run"
    print(checks.to_string(index=False))
    print(json.dumps(artifacts, indent=2, sort_keys=True))
    if len(not_run):
        print("\nNOT RUN (missing environment dependency, not a pass or fail)")
        print(not_run.to_string(index=False))
    if len(failed):
        print("\nFAILED CONTRACT CHECKS")
        print(failed.to_string(index=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
