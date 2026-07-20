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
LEAGUE_SEASON_MATCHES = {
    **{("Bundesliga", y): 34 for y in range(2012, LOCKED_SEASON_MIN)},
    **{("Premier League", y): 38 for y in range(2012, LOCKED_SEASON_MIN)},
    **{("La Liga", y): 38 for y in range(2012, LOCKED_SEASON_MIN)},
    **{("Serie A", y): 38 for y in range(2012, LOCKED_SEASON_MIN)},
    **{("Ligue 1", y): 38 for y in range(2012, LOCKED_SEASON_MIN)},
}
LEAGUE_SEASON_MATCHES[("Ligue 1", 2020)] = None

EVENT_IDENTITY_COLS = [
    "player_id", "decision_date", "transfer_season", "from_club_identity",
    "to_club_identity", "to_league", "transaction_type", "source_event_id",
]
OUTCOME_EVENT_JOIN_COLS = ["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name"]
FEATURE_EVENT_JOIN_COLS = ["transfer_uid", "player_id", "transfer_season", "transfer_date"]
MATERIAL_EVENT_COLS = [
    "transfer_uid", "player_id", "player_name", "player_age", "pos_group", "from_club_id",
    "from_club_name", "to_club_id", "to_club_name", "to_league", "season", "date",
    "transfer_type", "date_source", "to_league_source_label",
]


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


def available_minutes(league: pd.Series, outcome_season: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Competition-season denominator for league minutes share.

    This intentionally uses a league-format table, not a universal 38-match
    denominator. Interrupted or unsupported formats abstain.
    """
    pairs = list(zip(league.astype("object"), outcome_season.astype("Int64")))
    matches = pd.Series([LEAGUE_SEASON_MATCHES.get((l, int(y)), np.nan) if pd.notna(y) else np.nan
                         for l, y in pairs], index=league.index, dtype="Float64")
    status = pd.Series("competition_season_supported", index=league.index)
    known_pair = pd.Series([(l, int(y)) in LEAGUE_SEASON_MATCHES if pd.notna(y) else False
                            for l, y in pairs], index=league.index)
    status = status.mask(~known_pair, "ABSTAIN_UNSUPPORTED_DENOMINATOR")
    status = status.mask(known_pair & matches.isna(), "ABSTAIN_UNSUPPORTED_DENOMINATOR")
    return matches * 90, pd.Series(status, index=league.index)


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    transfers = pd.read_parquet(REPO / "data" / "merged" / "transfers_canonical.parquet")
    features = pd.read_csv(V3 / "transfer_performance_features_prior.csv", parse_dates=["transfer_date"])
    outcomes = pd.read_csv(V3 / "transfer_performance_outcomes_future.csv")
    clubs = pd.read_csv(V3 / "club_crosswalk.csv")
    return transfers, features, outcomes, clubs


def _fallback_series(primary: pd.Series, fallback: pd.Series) -> pd.Series:
    p = primary.astype("object")
    return p.where(p.notna(), fallback.astype("object"))


def build_event_table(transfers: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create semantic prediction events before any aggregation or target join."""
    d = transfers.copy()
    for c in MATERIAL_EVENT_COLS:
        if c not in d:
            d[c] = pd.NA
    d = d[MATERIAL_EVENT_COLS].drop_duplicates().copy()
    d["decision_date"] = pd.to_datetime(d["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    d["transfer_season"] = d["season"]
    d["from_club_identity"] = _fallback_series(d.from_club_id, d.from_club_name).map(_norm_token)
    d["to_club_identity"] = _fallback_series(d.to_club_id, d.to_club_name).map(_norm_token)
    d["transaction_type"] = d.transfer_type.fillna("unknown").map(_norm_token)
    d["source_event_id"] = d.transfer_uid.fillna("no-transfer-uid").map(_norm_token)
    parts = pd.DataFrame({
        "player_id": d.player_id.astype("Int64").astype(str),
        "decision_date": d.decision_date.fillna("na"),
        "transfer_season": d.transfer_season.astype("Int64").astype(str),
        "from_club": d.from_club_identity,
        "to_club": d.to_club_identity,
        "to_league": d.to_league.map(_norm_token),
        "transaction_type": d.transaction_type,
        "source_event_id": d.source_event_id,
    })
    base = (parts.player_id + "|" + parts.decision_date + "|" + parts.transfer_season + "|" +
            parts.from_club + "|" + parts.to_club + "|" + parts.to_league + "|" +
            parts.transaction_type + "|" + parts.source_event_id)
    d["prediction_key_base"] = base
    d["prediction_event_key"] = "spmvp1|" + base.map(lambda x: hashlib.sha256(x.encode()).hexdigest()[:24])
    duplicated = d[d.duplicated("prediction_key_base", keep=False)].copy()
    exact = d.drop_duplicates(MATERIAL_EVENT_COLS + ["prediction_key_base", "prediction_event_key"]).copy()
    conflicting_bases = exact.loc[exact.duplicated("prediction_key_base", keep=False), "prediction_key_base"].unique()
    exact["event_identity_status"] = np.where(
        exact.prediction_key_base.isin(conflicting_bases),
        "ABSTAIN_AMBIGUOUS_EVENT",
        "EVENT_SUPPORTED",
    )
    collisions = exact[exact.prediction_key_base.isin(conflicting_bases)].copy()
    if not duplicated.empty:
        identical = duplicated.groupby("prediction_key_base", dropna=False).size().reset_index(name="source_duplicate_rows")
        collisions = collisions.merge(identical, on="prediction_key_base", how="left")
    else:
        collisions["source_duplicate_rows"] = 0
    supported = exact[exact.event_identity_status.eq("EVENT_SUPPORTED")].copy()
    return supported, collisions


def prediction_keys(transfers: pd.DataFrame) -> pd.DataFrame:
    events, collisions = build_event_table(transfers)
    out = pd.DataFrame({
        "transfer_uid": events.transfer_uid,
        "prediction_key_base": events.prediction_key_base,
        "prediction_key_collision_seq": 0,
        "prediction_key": events.prediction_event_key,
    })
    if len(collisions):
        out = pd.concat([out, collisions[["transfer_uid", "prediction_key_base", "prediction_event_key"]].rename(
            columns={"prediction_event_key": "prediction_key"}).assign(prediction_key_collision_seq=-1)], ignore_index=True)
    return out


def prediction_keys_for_events(events: pd.DataFrame, transfers: pd.DataFrame) -> pd.DataFrame:
    """Stable keys for the prediction-event grain.

    `transfer_uid` is deliberately only one component. It is not globally
    unique, so the key also carries player, decision season/date, destination
    league/club, and transaction type. Ambiguous available-key matches abstain.
    """
    event_table, _ = build_event_table(transfers)
    right = event_table.rename(columns={"date": "transfer_decision_date"})
    right_keys = OUTCOME_EVENT_JOIN_COLS
    ambiguous_keys = right[right.duplicated(right_keys, keep=False)][right_keys].drop_duplicates()
    if len(ambiguous_keys):
        right = right.merge(ambiguous_keys.assign(_ambiguous_event_key=True), on=right_keys, how="left")
        right = right[right._ambiguous_event_key.isna()].drop(columns=["_ambiguous_event_key"])
    attached = events[right_keys].merge(
        right[right_keys + ["transfer_decision_date", "prediction_key_base", "prediction_event_key"]],
        on=right_keys,
        how="left",
        validate="many_to_one",
    )
    return attached.rename(columns={"prediction_event_key": "prediction_key"})


def attach_feature_events(features: pd.DataFrame, event_table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    f = features.copy()
    f["transfer_date"] = pd.to_datetime(f["transfer_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    right = event_table.copy()
    right["transfer_date"] = pd.to_datetime(right["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    right = right.rename(columns={"prediction_event_key": "prediction_key"})
    key_counts = right.groupby(FEATURE_EVENT_JOIN_COLS, dropna=False).prediction_key.nunique().reset_index(name="event_matches")
    unique_right = right.merge(key_counts, on=FEATURE_EVENT_JOIN_COLS, how="left")
    unique_right = unique_right[unique_right.event_matches.eq(1)].copy()
    ambiguous = key_counts[key_counts.event_matches.gt(1)].copy()
    attached = f.merge(
        unique_right[FEATURE_EVENT_JOIN_COLS + ["prediction_key", "prediction_key_base"]],
        on=FEATURE_EVENT_JOIN_COLS,
        how="left",
        validate="many_to_one",
    )
    attached["feature_event_status"] = np.where(
        attached.prediction_key.notna(), "EVENT_SUPPORTED", "ABSTAIN_AMBIGUOUS_OR_UNMATCHED_EVENT")
    return attached, ambiguous


def aggregate_prior(features: pd.DataFrame, event_table: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    f, ambiguous = attach_feature_events(features, event_table)
    f = f[f.feature_event_status.eq("EVENT_SUPPORTED")].copy()
    f["prior_minutes"] = pd.to_numeric(f.minutes, errors="coerce")
    f["prior_npxg"] = pd.to_numeric(f.npxg, errors="coerce")
    f["prior_xag"] = pd.to_numeric(f.xag, errors="coerce")
    f["prior_prog"] = pd.to_numeric(f.prog_actions, errors="coerce")
    tackles = pd.to_numeric(f.tackles, errors="coerce")
    interceptions = pd.to_numeric(f.interceptions, errors="coerce")
    f["prior_def"] = tackles.add(interceptions, fill_value=np.nan)
    f = f.sort_values(["prediction_key", "perf_season"])
    g = f.groupby("prediction_key", dropna=False)
    agg = g.agg(
        player_id=("player_id", "last"),
        transfer_season=("transfer_season", "last"),
        transfer_decision_date=("transfer_date", "last"),
        prior_performance_season=("perf_season", "max"),
        prior_minutes=("prior_minutes", "sum"),
        prior_attack_total=("prior_npxg", lambda s: s.sum(min_count=1)),
        prior_progression_total=("prior_prog", lambda s: s.sum(min_count=1)),
        prior_defensive_total=("prior_def", lambda s: s.sum(min_count=1)),
        prior_seasons=("perf_season", "nunique"),
        source_transfer_uids=("transfer_uid", lambda s: "|".join(sorted(set(map(str, s.dropna()))))),
    ).reset_index()
    denom = (agg.prior_minutes / 90).replace(0, np.nan)
    agg["prior_attack_rate"] = agg.prior_attack_total / denom
    agg["prior_progression_rate"] = agg.prior_progression_total / denom
    agg["prior_defensive_rate"] = agg.prior_defensive_total / denom
    agg["data_freshness_years"] = agg.transfer_season - agg.prior_performance_season
    return agg, ambiguous


def run_adversarial_event_tests() -> None:
    base = {
        "player_name": "Player",
        "player_age": 24,
        "pos_group": "FWD",
        "from_club_id": 1,
        "from_club_name": "A",
        "to_club_id": 2,
        "to_club_name": "B",
        "to_league": "Premier League",
        "season": 2020,
        "date": "2020-08-01",
        "transfer_type": "transfer",
        "date_source": "exact",
        "to_league_source_label": "Premier League",
    }
    transfers = pd.DataFrame([
        {**base, "transfer_uid": "shared", "player_id": 10, "to_club_id": 2, "to_club_name": "B"},
        {**base, "transfer_uid": "shared", "player_id": 11, "to_club_id": 3, "to_club_name": "C"},
        {**base, "transfer_uid": "same-player", "player_id": 12, "date": "2020-08-01", "to_club_id": 4, "to_club_name": "D"},
        {**base, "transfer_uid": "same-player", "player_id": 12, "date": "2020-09-01", "to_club_id": 5, "to_club_name": "E"},
        {**base, "transfer_uid": "same-season", "player_id": 13, "to_club_id": 6, "to_club_name": "F"},
        {**base, "transfer_uid": "same-season", "player_id": 13, "to_club_id": 7, "to_club_name": "G"},
    ])
    events, collisions = build_event_table(transfers)
    assert collisions.empty
    assert events.prediction_event_key.nunique() == len(events)
    assert events.loc[events.transfer_uid.eq("shared"), "prediction_event_key"].nunique() == 2
    assert events.loc[events.transfer_uid.eq("same-player"), "prediction_event_key"].nunique() == 2
    assert events.loc[events.transfer_uid.eq("same-season"), "prediction_event_key"].nunique() == 2

    duplicate = pd.DataFrame([{**base, "transfer_uid": "dup", "player_id": 20},
                              {**base, "transfer_uid": "dup", "player_id": 20}])
    dup_events, dup_collisions = build_event_table(duplicate)
    assert len(dup_events) == 1
    assert dup_collisions.empty

    conflict = pd.DataFrame([{**base, "transfer_uid": "conflict", "player_id": 30, "player_age": 24},
                             {**base, "transfer_uid": "conflict", "player_id": 30, "player_age": 25}])
    conflict_events, conflict_collisions = build_event_table(conflict)
    assert conflict_events.empty
    assert not conflict_collisions.empty
    assert conflict_collisions.event_identity_status.eq("ABSTAIN_AMBIGUOUS_EVENT").all()

    ambiguous_outcome = pd.DataFrame([{
        "transfer_uid": "same-season", "player_id": 13, "transfer_season": 2020,
        "to_league": "Premier League", "to_club_name": "F",
    }])
    attached = prediction_keys_for_events(ambiguous_outcome, transfers)
    assert attached.prediction_key.notna().all()

    ambiguous_features = pd.DataFrame([
        {"transfer_uid": "same-season", "player_id": 13, "transfer_season": 2020, "transfer_date": "2020-08-01",
         "perf_season": 2019, "minutes": 900, "npxg": 1.0, "xag": 1.0, "prog_actions": 1.0,
         "tackles": 1.0, "interceptions": 1.0}
    ])
    attached_features, ambiguous_feature_keys = attach_feature_events(ambiguous_features, events)
    assert attached_features.feature_event_status.eq("ABSTAIN_AMBIGUOUS_OR_UNMATCHED_EVENT").all()
    assert not ambiguous_feature_keys.empty
    prior, _ = aggregate_prior(ambiguous_features, events)
    assert prior.empty


def run_denominator_tests() -> None:
    leagues = pd.Series(["Premier League", "Bundesliga", "Ligue 1", "Unknown League", "Premier League"])
    seasons = pd.Series([2022, 2022, 2020, 2022, 2025])
    minutes, status = available_minutes(leagues, seasons)
    assert minutes.iloc[0] == 3420
    assert minutes.iloc[1] == 3060
    assert pd.isna(minutes.iloc[2]) and status.iloc[2] == "ABSTAIN_UNSUPPORTED_DENOMINATOR"
    assert pd.isna(minutes.iloc[3]) and status.iloc[3] == "ABSTAIN_UNSUPPORTED_DENOMINATOR"
    assert pd.isna(minutes.iloc[4]) and status.iloc[4] == "ABSTAIN_UNSUPPORTED_DENOMINATOR"


def build_manifest() -> tuple[pd.DataFrame, dict, dict]:
    transfers, features, outcomes, clubs = load_inputs()
    event_table, event_collisions = build_event_table(transfers)
    x, ambiguous_feature_keys = aggregate_prior(features, event_table)
    transfer_cols = [
        "transfer_uid", "player_id", "player_name", "player_age", "pos_group", "from_club_name",
        "to_club_name", "to_league", "to_league_source_label", "season", "date",
        "transfer_type", "date_source",
    ]
    for c in transfer_cols:
        if c not in transfers:
            transfers[c] = pd.NA
    t = event_table[transfer_cols + ["prediction_event_key", "prediction_key_base"]].copy()

    next_y = outcomes[(outcomes.horizon == "next_season") & (outcomes.outcome_season < LOCKED_SEASON_MIN)].copy()
    two_safe = outcomes[(outcomes.horizon == "two_season") & (outcomes.outcome_season < LOCKED_SEASON_MIN)].copy()
    if (next_y.outcome_season >= LOCKED_SEASON_MIN).any() or (two_safe.outcome_season >= LOCKED_SEASON_MIN).any():
        raise AssertionError("locked outcome entered development")

    next_event = prediction_keys_for_events(next_y, transfers)
    two_event = prediction_keys_for_events(two_safe, transfers)
    next_y = next_y.reset_index(drop=True)
    two_safe = two_safe.reset_index(drop=True)
    next_y["prediction_key"] = next_event["prediction_key"].values
    next_y["transfer_decision_date"] = next_event["transfer_decision_date"].values
    two_safe["prediction_key"] = two_event["prediction_key"].values
    next_y["outcome_event_status"] = np.where(next_y.prediction_key.notna(), "EVENT_SUPPORTED", "ABSTAIN_AMBIGUOUS_EVENT")
    two_safe["outcome_event_status"] = np.where(two_safe.prediction_key.notna(), "EVENT_SUPPORTED", "ABSTAIN_AMBIGUOUS_EVENT")
    next_y = next_y[next_y.outcome_event_status.eq("EVENT_SUPPORTED")].copy()
    two_safe = two_safe[two_safe.outcome_event_status.eq("EVENT_SUPPORTED")].copy()
    outcome_key = ["prediction_key", "outcome_season"]
    duplicate_outcome_rows = next_y[next_y.duplicated(outcome_key, keep=False)].copy()
    material_next_cols = ["prediction_key", "outcome_season", "minutes", "npxg", "xag",
                          "prog_actions", "tackles", "interceptions", "club_match_confidence"]
    exact_next = next_y.drop_duplicates(material_next_cols).copy()
    conflicting_next = exact_next.loc[exact_next.duplicated(outcome_key, keep=False), "prediction_key"].unique()
    if len(conflicting_next):
        next_y = exact_next[~exact_next.prediction_key.isin(conflicting_next)].copy()
    else:
        next_y = exact_next.copy()
    next_y["next_minutes"] = pd.to_numeric(next_y.minutes, errors="coerce")
    next_y["next_npxg"] = pd.to_numeric(next_y.npxg, errors="coerce")
    next_y["next_xag"] = pd.to_numeric(next_y.xag, errors="coerce")
    next_y["next_prog"] = pd.to_numeric(next_y.prog_actions, errors="coerce")
    next_tackles = pd.to_numeric(next_y.tackles, errors="coerce")
    next_interceptions = pd.to_numeric(next_y.interceptions, errors="coerce")
    next_y["next_def"] = next_tackles.add(next_interceptions, fill_value=np.nan)
    next_y["next_available_minutes"], next_y["next_available_minutes_status"] = available_minutes(
        next_y.to_league, next_y.outcome_season)
    next_y["next_minutes_share"] = next_y.next_minutes / next_y.next_available_minutes
    next_y["next_minutes_observation_status"] = np.where(
        next_y.next_minutes.notna(), "observed", "unobserved")
    next_y["meaningful_participation"] = np.where(
        next_y.next_minutes.notna(), (next_y.next_minutes >= 900).astype(int), pd.NA)

    two = two_safe[["prediction_key", "minutes"]].drop_duplicates().rename(columns={"minutes": "second_season_minutes"})
    two_dupe_keys = two[two.duplicated("prediction_key", keep=False)].prediction_key.unique()
    if len(two_dupe_keys):
        two = two[~two.prediction_key.isin(two_dupe_keys)].copy()
    m = next_y.merge(two, on="prediction_key", how="left", validate="one_to_one")
    m["two_season_support"] = m.second_season_minutes.notna()
    m["two_season_cumulative_minutes"] = m.next_minutes + m.second_season_minutes
    m["two_season_available_minutes"] = np.where(m.next_available_minutes.notna(), m.next_available_minutes * 2, np.nan)
    m["two_season_minutes_share"] = m.two_season_cumulative_minutes / m.two_season_available_minutes
    m["two_season_observation_status"] = np.where(
        m.two_season_support, "observed_two_season", "incomplete_or_unobserved")

    join_audit = []
    join_audit.append({"join_name": "outcomes_next_to_two_season", "join_columns": "prediction_key",
                       "left_rows": len(next_y), "right_rows": len(two), "output_rows": len(m),
                       "unmatched_left_rows": int(m.second_season_minutes.isna().sum()),
                       "expected_right_key_unique": bool(not two.prediction_key.duplicated().any()),
                       "many_to_many": False})
    if len(m) != len(next_y):
        raise AssertionError("two-season attachment multiplied rows")
    t_join = t.rename(columns={"season": "transfer_season", "date": "canonical_transfer_date"})
    dev = (m.merge(t_join.drop(columns=["transfer_uid", "player_id", "transfer_season", "to_league", "to_club_name"]),
                   left_on="prediction_key", right_on="prediction_event_key", how="left", validate="one_to_one")
             .merge(x.drop(columns=["player_id", "transfer_season", "transfer_decision_date"]),
                    on="prediction_key", how="left", validate="one_to_one"))
    if len(dev) != len(m):
        raise AssertionError("manifest joins multiplied rows")
    join_audit.extend([
        {"join_name": "next_outcome_event_key_attachment", "join_columns": "|".join(OUTCOME_EVENT_JOIN_COLS),
         "left_rows": int(len(outcomes[(outcomes.horizon == "next_season") & (outcomes.outcome_season < LOCKED_SEASON_MIN)])),
         "right_rows": int(len(event_table.drop_duplicates(OUTCOME_EVENT_JOIN_COLS))), "output_rows": int(len(next_y)),
         "unmatched_left_rows": int(next_event.prediction_key.isna().sum()),
         "expected_right_key_unique": True,
         "many_to_many": False},
        {"join_name": "canonical_transfer_metadata", "left_rows": len(m), "right_rows": len(t),
         "output_rows": len(m), "unmatched_left_rows": int(dev.canonical_transfer_date.isna().sum()),
         "join_columns": "prediction_key=prediction_event_key",
         "expected_right_key_unique": bool(not t_join.prediction_event_key.duplicated().any()),
         "many_to_many": False},
        {"join_name": "prior_performance_aggregation", "left_rows": len(m), "right_rows": len(x),
         "output_rows": len(m), "unmatched_left_rows": int(dev.prior_minutes.isna().sum()),
         "join_columns": "prediction_key",
         "expected_right_key_unique": bool(not x.prediction_key.duplicated().any()),
         "many_to_many": False},
    ])
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
        "data_freshness_years", "next_minutes", "next_available_minutes",
        "next_available_minutes_status", "next_minutes_share", "next_minutes_observation_status",
        "two_season_support", "two_season_cumulative_minutes", "two_season_available_minutes",
        "two_season_minutes_share", "two_season_observation_status",
        "meaningful_participation",
    ]
    dev = dev[keep].sort_values("prediction_key").reset_index(drop=True)
    dev.insert(0, "prediction_event_key", dev.pop("prediction_key"))
    dev["prediction_key"] = dev.prediction_event_key

    all_transfer_keys = prediction_keys(transfers)
    key_dupes = pd.concat([
        all_transfer_keys[all_transfer_keys.prediction_key_base.duplicated(keep=False)].copy(),
        event_collisions.rename(columns={"prediction_event_key": "prediction_key"}).copy(),
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
        "previous_merged_row_count": 2117,
        "rows_removed_by_event_identity_quarantine": int(2117 - len(dev)),
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
        "generating_command": "python3 -m validate.sporting_mvp_integrity",
        "determinism_note": "No git commit SHA is embedded in deterministic model/data artifacts.",
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
        "event_collisions": event_collisions,
        "ambiguous_feature_keys": ambiguous_feature_keys,
        "ambiguous_outcome_keys": int(next_event.prediction_key.isna().sum()),
        "join_audit": pd.DataFrame(join_audit),
    }


def write_outputs() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    run_adversarial_event_tests()
    run_denominator_tests()
    dev, summary, aux = build_manifest()
    manifest_path = OUT / "dev-population-manifest.csv"
    dev.to_csv(manifest_path, index=False)
    summary["manifest_hash_sha256"] = _sha_file(manifest_path)
    (OUT / "dev-population-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    pd.DataFrame([
        {"artifact": "data/merged/transfers_canonical.parquet", "change": "LaLiga to La Liga canonicalisation", **summary["league_alias_audit"]},
        {"artifact": "money/scout.py", "change": "removed invalid current-board talent_pctl join", **summary["talent_pctl_audit"]},
    ]).to_csv(OUT / "data-fix-summary.csv", index=False)

    pd.read_csv(V3 / "effective_sample_funnel.csv").rename(columns={"condition": "stage"}).to_csv(
        OUT / "join-funnel.csv", index=False)
    aux["join_audit"].to_csv(OUT / "join-audit.csv", index=False)
    miss_cols = [
        "next_minutes", "prior_attack_rate", "prior_progression_rate", "prior_defensive_rate",
        "next_minutes_share", "two_season_cumulative_minutes",
    ]
    miss = []
    for group_cols in [["role"], ["to_league"], ["outcome_season"], ["fold"]]:
        for keys, g in dev.groupby(group_cols, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            base = {f"group_{i+1}": v for i, v in enumerate(keys)}
            base["grouping"] = "+".join(group_cols)
            base["rows"] = len(g)
            for c in miss_cols:
                base[f"{c}_missing"] = int(g[c].isna().sum())
            miss.append(base.copy())
    pd.DataFrame(miss).to_csv(OUT / "missingness-summary.csv", index=False)
    kc = aux["key_collisions"][["transfer_uid", "prediction_key_base", "prediction_key_collision_seq", "prediction_key"]]
    if len(aux["duplicate_outcome_rows"]):
        dup = aux["duplicate_outcome_rows"].copy()
        dup["prediction_key_base"] = "duplicate_outcome_row_same_prediction_event"
        dup["prediction_key_collision_seq"] = -1
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
        {"reason": "ABSTAIN_AMBIGUOUS_EVENT", "rows": int(summary["rows_removed_by_event_identity_quarantine"])},
        {"reason": "ABSTAIN_UNSUPPORTED_DENOMINATOR", "rows": int(dev.next_available_minutes_status.eq("ABSTAIN_UNSUPPORTED_DENOMINATOR").sum())},
        {"reason": "unsupported_role_or_no_prior_performance_before_v3_step_8", "rows": 132030},
        {"reason": "dev_manifest_supported_rows", "rows": int(len(dev))},
    ]).to_csv(OUT / "abstention-summary.csv", index=False)

    assert not dev.prediction_event_key.duplicated().any(), "duplicate prediction_event_key"
    assert aux["join_audit"].output_rows.le(aux["join_audit"].left_rows).all(), "material join expansion"
    assert aux["join_audit"].expected_right_key_unique.all(), "material right join key is not unique"
    assert not (dev.outcome_season >= LOCKED_SEASON_MIN).any()
    assert dev.loc[dev.next_available_minutes_status.eq("ABSTAIN_UNSUPPORTED_DENOMINATOR"), "next_minutes_share"].isna().all()
    missing_prior_metric = dev[["prior_attack_rate", "prior_progression_rate", "prior_defensive_rate"]].isna()
    assert missing_prior_metric.any().any(), "missing prior metrics were unexpectedly eliminated"
    assert dev.loc[dev.next_minutes_observation_status.eq("unobserved"), "meaningful_participation"].isna().all()
    assert _sha_file(manifest_path) == summary["manifest_hash_sha256"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> int:
    write_outputs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
