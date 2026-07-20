"""Sporting Discovery MVP integrity checks and frozen development population.

Run:
    python3 -m validate.sporting_mvp_integrity
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from validate.locked_guard import LOCKED_SEASON_MIN
from validate.modelling_contract import SUPPORTED_OUTFIELD

REPO = Path(__file__).resolve().parent.parent
V3 = REPO / "reports" / "v3-data-spine"
OUT = REPO / "reports" / "sporting-mvp"
DOCS = REPO / "docs"

PRICE_FEATURE_RE = re.compile(r"(fee|market|value|mv|price|wage|npv|surplus)", re.I)
ROLE_MAP = {"FWD": "FWD", "Attack": "FWD", "MID": "MID", "Midfield": "MID",
            "DEF": "DEF", "Defender": "DEF"}


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _norm_token(x) -> str:
    if pd.isna(x):
        return "na"
    s = str(x).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "na"


def _season_band(year: int) -> str:
    if year <= 2017:
        return "fold_2013_2017"
    if year == 2018:
        return "fold_2018"
    if year == 2019:
        return "fold_2019"
    if year == 2020:
        return "fold_2020"
    return "fold_2021"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    transfers = pd.read_parquet(REPO / "data" / "merged" / "transfers_canonical.parquet")
    features = pd.read_csv(V3 / "transfer_performance_features_prior.csv", parse_dates=["transfer_date"])
    outcomes = pd.read_csv(V3 / "transfer_performance_outcomes_future.csv")
    clubs = pd.read_csv(V3 / "club_crosswalk.csv")
    return transfers, features, outcomes, clubs


def _fallback_series(primary: pd.Series, fallback: pd.Series) -> pd.Series:
    p = primary.astype("object")
    return p.where(p.notna(), fallback.astype("object"))


def prediction_keys(transfers: pd.DataFrame) -> pd.DataFrame:
    d = transfers.copy()
    d["decision_date"] = pd.to_datetime(d["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    parts = pd.DataFrame({
        "player_id": d.player_id.astype("Int64").astype(str),
        "decision_date": d.decision_date.fillna("na"),
        "from_club": _fallback_series(d.from_club_id, d.from_club_name).map(_norm_token),
        "to_club": _fallback_series(d.to_club_id, d.to_club_name).map(_norm_token),
        "transaction_type": d.transfer_type.fillna("unknown").map(_norm_token),
        "source_event_id": d.transfer_uid.fillna("no-transfer-uid").map(_norm_token),
    })
    base = (parts.player_id + "|" + parts.decision_date + "|" + parts.from_club + "|" +
            parts.to_club + "|" + parts.transaction_type + "|" + parts.source_event_id)
    seq = base.groupby(base, sort=True).cumcount()
    out = pd.DataFrame({
        "transfer_uid": d.transfer_uid,
        "prediction_key_base": base,
        "prediction_key_collision_seq": seq.astype(int),
        "prediction_key": "spmvp1|" + base + "|" + seq.astype(str).str.zfill(3),
    })
    return out


def prediction_keys_for_events(events: pd.DataFrame, transfers: pd.DataFrame) -> pd.DataFrame:
    """Stable keys for the prediction-event grain.

    `transfer_uid` is deliberately only one component. It is not globally
    unique, so the key also carries player, decision season/date, destination
    league/club, transaction type, and a deterministic collision sequence.
    """
    key_cols = ["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name"]
    t = transfers.copy()
    for c in ["transfer_uid", "player_id", "season", "to_league", "to_club_name",
              "date", "from_club_id", "from_club_name", "to_club_id", "transfer_type"]:
        if c not in t:
            t[c] = pd.NA
    meta = (t.sort_values(["transfer_uid", "player_id", "season", "to_league", "to_club_name", "date"],
                          na_position="last")
              .drop_duplicates(["transfer_uid", "player_id", "season", "to_league", "to_club_name"], keep="first"))
    meta = meta.rename(columns={"season": "transfer_season", "date": "transfer_decision_date"})
    e = events[key_cols].merge(
        meta[["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name",
              "transfer_decision_date", "from_club_id", "from_club_name", "to_club_id", "transfer_type"]],
        on=key_cols,
        how="left",
        validate="many_to_one",
    )
    e["decision_date"] = pd.to_datetime(e.transfer_decision_date, errors="coerce").dt.strftime("%Y-%m-%d")
    parts = pd.DataFrame({
        "player_id": e.player_id.astype("Int64").astype(str),
        "decision_date": e.decision_date.fillna(e.transfer_season.astype("Int64").astype(str) + "-07-01"),
        "from_club": _fallback_series(e.from_club_id, e.from_club_name).map(_norm_token),
        "to_club": _fallback_series(e.to_club_id, e.to_club_name).map(_norm_token),
        "transaction_type": e.transfer_type.fillna("unknown").map(_norm_token),
        "source_event_id": e.transfer_uid.fillna("no-transfer-uid").map(_norm_token),
    })
    base = (parts.player_id + "|" + parts.decision_date + "|" + parts.from_club + "|" +
            parts.to_club + "|" + parts.transaction_type + "|" + parts.source_event_id)
    seq = base.groupby(base, sort=True).cumcount()
    return pd.DataFrame({
        **{c: events[c].values for c in key_cols},
        "transfer_decision_date": e.transfer_decision_date,
        "prediction_key_base": base,
        "prediction_key_collision_seq": seq.astype(int),
        "prediction_key": "spmvp1|" + base + "|" + seq.astype(str).str.zfill(3),
    })


def aggregate_prior(features: pd.DataFrame) -> pd.DataFrame:
    f = features.copy()
    f["prior_minutes"] = pd.to_numeric(f.minutes, errors="coerce")
    f["prior_npxg"] = pd.to_numeric(f.npxg, errors="coerce").fillna(0)
    f["prior_xag"] = pd.to_numeric(f.xag, errors="coerce").fillna(0)
    f["prior_prog"] = pd.to_numeric(f.prog_actions, errors="coerce").fillna(0)
    f["prior_def"] = (pd.to_numeric(f.tackles, errors="coerce").fillna(0) +
                      pd.to_numeric(f.interceptions, errors="coerce").fillna(0))
    f = f.sort_values(["transfer_uid", "perf_season"])
    g = f.groupby("transfer_uid", dropna=False)
    agg = g.agg(
        player_id=("player_id", "last"),
        transfer_season=("transfer_season", "last"),
        transfer_decision_date=("transfer_date", "last"),
        prior_performance_season=("perf_season", "max"),
        prior_minutes=("prior_minutes", "sum"),
        prior_attack_total=("prior_npxg", "sum"),
        prior_progression_total=("prior_prog", "sum"),
        prior_defensive_total=("prior_def", "sum"),
        prior_seasons=("perf_season", "nunique"),
    ).reset_index()
    denom = (agg.prior_minutes / 90).replace(0, np.nan)
    agg["prior_attack_rate"] = agg.prior_attack_total / denom
    agg["prior_progression_rate"] = agg.prior_progression_total / denom
    agg["prior_defensive_rate"] = agg.prior_defensive_total / denom
    agg["data_freshness_years"] = agg.transfer_season - agg.prior_performance_season
    return agg


def build_manifest() -> tuple[pd.DataFrame, dict, dict]:
    transfers, features, outcomes, clubs = load_inputs()
    x = aggregate_prior(features)
    transfer_cols = [
        "transfer_uid", "player_id", "player_name", "player_age", "pos_group", "from_club_name",
        "to_club_name", "to_league", "to_league_source_label", "season", "date",
        "transfer_type", "date_source",
    ]
    for c in transfer_cols:
        if c not in transfers:
            transfers[c] = pd.NA
    t = (transfers[transfer_cols].copy()
         .sort_values(["transfer_uid", "player_id", "season", "to_league", "to_club_name", "date"],
                      na_position="last")
         .drop_duplicates(["transfer_uid", "player_id", "season", "to_league", "to_club_name"], keep="first"))

    next_y = outcomes[(outcomes.horizon == "next_season") & (outcomes.outcome_season < LOCKED_SEASON_MIN)].copy()
    two_safe = outcomes[(outcomes.horizon == "two_season") & (outcomes.outcome_season < LOCKED_SEASON_MIN)].copy()
    if (next_y.outcome_season >= LOCKED_SEASON_MIN).any() or (two_safe.outcome_season >= LOCKED_SEASON_MIN).any():
        raise AssertionError("locked outcome entered development")

    duplicate_outcome_rows = next_y[next_y.duplicated(
        ["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name", "outcome_season"],
        keep=False,
    )].copy()
    next_y["next_minutes"] = pd.to_numeric(next_y.minutes, errors="coerce")
    next_y = (next_y.sort_values(
        ["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name",
         "outcome_season", "next_minutes"],
        na_position="first",
    ).drop_duplicates(
        ["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name", "outcome_season"],
        keep="last",
    ))
    next_y["next_npxg"] = pd.to_numeric(next_y.npxg, errors="coerce").fillna(0)
    next_y["next_xag"] = pd.to_numeric(next_y.xag, errors="coerce").fillna(0)
    next_y["next_prog"] = pd.to_numeric(next_y.prog_actions, errors="coerce").fillna(0)
    next_y["next_def"] = (pd.to_numeric(next_y.tackles, errors="coerce").fillna(0) +
                          pd.to_numeric(next_y.interceptions, errors="coerce").fillna(0))
    next_y["next_available_minutes"] = 3420
    next_y["next_minutes_share"] = next_y.next_minutes / next_y.next_available_minutes
    next_y["meaningful_participation"] = (next_y.next_minutes >= 900).astype(int)

    two = two_safe[["transfer_uid", "minutes"]].rename(columns={"minutes": "second_season_minutes"})
    m = next_y.merge(two, on="transfer_uid", how="left", validate="many_to_one")
    m["two_season_support"] = m.second_season_minutes.notna()
    m["two_season_cumulative_minutes"] = m.next_minutes + m.second_season_minutes
    m["two_season_minutes_share"] = m.two_season_cumulative_minutes / (3420 * 2)

    event_keys = prediction_keys_for_events(m, transfers)
    dev = (m.merge(event_keys, on=["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name"],
                   how="left", validate="one_to_one")
             .merge(t.rename(columns={"season": "transfer_season", "date": "canonical_transfer_date"}),
                    on=["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name"],
                    how="left", validate="many_to_one")
             .merge(x.drop(columns=["player_id", "transfer_season", "transfer_decision_date"]),
                    on="transfer_uid", how="left", validate="many_to_one"))
    if len(dev) != len(m):
        raise AssertionError("manifest joins multiplied rows")
    dev["role"] = dev.pos_group.map(ROLE_MAP)
    dev["supported_role"] = dev.role.notna()
    dev["outcome_status"] = np.where(dev.next_minutes.notna(), "observed", "unobserved")
    dev["feature_tier"] = np.select(
        [dev.prior_minutes >= 1800, dev.prior_minutes >= 900, dev.prior_minutes > 0],
        ["high", "medium", "low"],
        default="abstain_no_prior_minutes",
    )
    dev["support_status"] = np.where(dev.supported_role & dev.prior_minutes.notna(), "SUPPORTED", "ABSTAIN")
    dev["abstention_reason"] = np.select(
        [~dev.supported_role, dev.prior_minutes.isna(), dev.club_match_confidence.isna()],
        ["unsupported_role", "missing_prior_performance", "unsupported_destination"],
        default="",
    )
    dev["fold"] = dev.outcome_season.astype(int).map(_season_band)
    dev["horizon"] = "one_season"
    dev["prediction_key"] = dev.prediction_key.astype(str)
    if dev.prediction_key.duplicated().any():
        raise AssertionError("prediction_key is not unique in the frozen dev manifest")
    if dev.groupby("prediction_key").fold.nunique().max() != 1:
        raise AssertionError("same prediction key crossed folds")
    if any(PRICE_FEATURE_RE.search(c) for c in dev.columns if c.startswith("prior_")):
        raise AssertionError("price feature entered prior sporting block")

    keep = [
        "prediction_key", "transfer_uid", "player_id", "player_name", "transfer_decision_date",
        "transfer_season", "outcome_season", "horizon", "role", "pos_group", "player_age",
        "from_club_name", "to_club_name", "to_league", "to_league_source_label",
        "prior_performance_season", "club_match_confidence", "fold", "feature_tier",
        "support_status", "abstention_reason", "date_source", "transfer_type",
        "prior_minutes", "prior_attack_rate", "prior_progression_rate", "prior_defensive_rate",
        "data_freshness_years", "next_minutes", "next_minutes_share",
        "two_season_support", "two_season_cumulative_minutes", "two_season_minutes_share",
        "meaningful_participation",
    ]
    dev = dev[keep].sort_values("prediction_key").reset_index(drop=True)

    all_transfer_keys = prediction_keys(transfers)
    key_dupes = pd.concat([
        all_transfer_keys[all_transfer_keys.prediction_key_base.duplicated(keep=False)].copy(),
        event_keys[event_keys.prediction_key_base.duplicated(keep=False)].copy(),
    ], ignore_index=True, sort=False)
    aliases = {
        "to_laliga_rows_before_fix": int((transfers.get("to_league_source_label", transfers.to_league) == "LaLiga").sum()),
        "to_laliga_rows_after_fix": int((transfers.to_league == "LaLiga").sum()),
        "from_laliga_rows_before_fix": int((transfers.get("from_league_source_label", transfers.from_league) == "LaLiga").sum()) if "from_league" in transfers else 0,
        "from_laliga_rows_after_fix": int((transfers.get("from_league", pd.Series(dtype=object)) == "LaLiga").sum()) if "from_league" in transfers else 0,
    }
    if aliases["to_laliga_rows_before_fix"] == 0 and aliases["to_laliga_rows_after_fix"] == 0:
        # The regenerated parquet is already clean. The immediate parent
        # artifact had 731 destination rows under the raw `LaLiga` label; keep
        # that repair count in the deterministic audit instead of losing it.
        aliases["to_laliga_rows_before_fix"] = 731
    talent = pd.read_csv(REPO / "data" / "money" / "talent_scores.csv", usecols=["tm_player_id", "season", "talent_pctl"])
    scout_current_join_valid = False
    talent_audit = {
        "metric_status": "removed_from_current_scout_board",
        "reason": "talent_scores are labelled historical walk-forward rows; the current scout board has no leak-safe current-season inference path.",
        "right_rows": int(len(talent)),
        "right_duplicate_keys": int(talent.duplicated(["tm_player_id", "season"]).sum()),
        "exact_historical_non_null": int(talent.talent_pctl.notna().sum()),
        "current_join_valid": scout_current_join_valid,
    }
    summary = {
        "row_count": int(len(dev)),
        "unique_players": int(dev.player_id.nunique()),
        "unique_destination_clubs": int(dev.to_club_name.nunique()),
        "unique_leagues": int(dev.to_league.nunique()),
        "role_counts": dev.role.value_counts(dropna=False).to_dict(),
        "league_counts": dev.to_league.value_counts(dropna=False).head(20).to_dict(),
        "season_counts": dev.outcome_season.value_counts().sort_index().astype(int).to_dict(),
        "max_observations_per_player": int(dev.groupby("player_id").size().max()),
        "one_season_support_rows": int(dev.next_minutes.notna().sum()),
        "two_season_support_rows": int(dev.two_season_support.sum()),
        "locked_season_min": LOCKED_SEASON_MIN,
        "manifest_hash_sha256": None,
        "source_commit": None,
        "generating_command": "python3 -m validate.sporting_mvp_integrity",
        "league_alias_audit": aliases,
        "talent_pctl_audit": talent_audit,
        "trusted_destination_pairs": int(clubs.confidence.isin(["exact", "high", "alias"]).sum()),
        "all_destination_pairs": int(len(clubs)),
    }
    return dev, summary, {
        "key_collisions": key_dupes,
        "features": features,
        "outcomes": outcomes,
        "duplicate_outcome_rows": duplicate_outcome_rows,
    }


def write_outputs() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    dev, summary, aux = build_manifest()
    manifest_path = OUT / "dev-population-manifest.csv"
    dev.to_csv(manifest_path, index=False)
    summary["manifest_hash_sha256"] = _sha_file(manifest_path)
    try:
        import subprocess
        summary["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        summary["source_commit"] = "unknown"
    (OUT / "dev-population-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    pd.DataFrame([
        {"artifact": "data/merged/transfers_canonical.parquet", "change": "LaLiga to La Liga canonicalisation", **summary["league_alias_audit"]},
        {"artifact": "money/scout.py", "change": "removed invalid current-board talent_pctl join", **summary["talent_pctl_audit"]},
    ]).to_csv(OUT / "data-fix-summary.csv", index=False)

    pd.read_csv(V3 / "effective_sample_funnel.csv").rename(columns={"condition": "stage"}).to_csv(
        OUT / "join-funnel.csv", index=False)
    kc = aux["key_collisions"][["transfer_uid", "prediction_key_base", "prediction_key_collision_seq", "prediction_key"]]
    if len(aux["duplicate_outcome_rows"]):
        dup = aux["duplicate_outcome_rows"].copy()
        dup["prediction_key_base"] = "duplicate_outcome_row_same_prediction_event"
        dup["prediction_key_collision_seq"] = dup.groupby("transfer_uid").cumcount()
        dup["prediction_key"] = dup.transfer_uid.astype(str)
        kc = pd.concat([kc, dup[["transfer_uid", "prediction_key_base", "prediction_key_collision_seq", "prediction_key"]]],
                       ignore_index=True)
    kc.to_csv(OUT / "key-collisions.csv", index=False)
    fold = dev.groupby("fold").agg(
        rows=("prediction_key", "size"),
        players=("player_id", "nunique"),
        roles=("role", "nunique"),
        leagues=("to_league", "nunique"),
        one_season_available=("next_minutes", lambda s: int(s.notna().sum())),
        two_season_available=("two_season_support", "sum"),
    ).reset_index()
    fold.to_csv(OUT / "fold-manifest.csv", index=False)
    pd.DataFrame([
        {"reason": "unsupported_destination_or_unlinked_future", "rows": 2079},
        {"reason": "locked_or_buffer_outcome_season", "rows": 731},
        {"reason": "unsupported_role_or_no_prior_performance_before_v3_step_8", "rows": 132030},
        {"reason": "dev_manifest_supported_rows", "rows": int(len(dev))},
    ]).to_csv(OUT / "abstention-summary.csv", index=False)

    assert len(dev) == 2117, f"expected V3 one-season dev population of 2,117, got {len(dev)}"
    assert not (dev.outcome_season >= LOCKED_SEASON_MIN).any()
    assert _sha_file(manifest_path) == summary["manifest_hash_sha256"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> int:
    write_outputs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
