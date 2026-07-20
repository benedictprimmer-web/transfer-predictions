"""V3 data spine: transfer_performance_features_prior and
transfer_performance_outcomes_future, built entirely from this repo's
tracked data (fbref_perf + transfers_canonical + players_master) — no
Estate B dependency anywhere in this module.

This directly answers the correction in `docs/contradiction-log.md`:
`transfer_performance_link_safe` was never a destination-season source (it
is a strictly-prior feature link by its own definition). This module builds
the thing that actually was missing.

Two separate, differently-purposed tables (task §3.1, §7.2, §7.3):

- `transfer_performance_features_prior`: the player's OWN performance
  strictly before the transfer, ANY club. A feature. No destination
  matching needed — it describes what he'd already shown before the move.
- `transfer_performance_outcomes_future`: performance AT THE DESTINATION
  CLUB, in the next season and/or the following two seasons. A label. Only
  usable as `y` after temporal splitting, never as a feature. Requires
  BOTH player identity (tm_player_id, already reliable — same crosswalk
  `money/scout.py` and `impact/talent.py` already use) AND destination
  club identity (via `ingest.club_crosswalk`, which is NOT fully reliable —
  every outcome row carries its club-match confidence tier, and only
  `exact`/`high`/`alias` confidence is used; `low`/`unmatched` rows are
  excluded from the outcome table entirely, not included with a caveat,
  because `ingest.club_crosswalk`'s own validation found real false
  positives in the `low` tier (Atlético/Athletic Club, Real Murcia/Real
  Madrid) that must not silently enter a sporting label).

`fbref_perf` spans 2010-2026 and OVERLAPS the locked period
(`season >= 2023`) — corrected from the original V2 assumption that FBref
coverage stopped in 2022. Every query here filters through
`validate.locked_guard` explicitly; nothing relies on a coverage-window
assumption to stay locked-safe.

    python3 -m validate.v3_sporting_target
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ingest.club_crosswalk import build_crosswalk
from validate.locked_guard import LOCKED_SEASON_MIN, dev_only, write_locked_audit
from validate.modelling_contract import SUPPORTED_OUTFIELD

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
OUT = REPO / "reports" / "v3-data-spine"

# fbref_perf's Comp values are already Premier League/Serie A/Ligue 1/
# La Liga/Bundesliga; transfers_canonical's to_league mostly matches
# directly except for the La Liga/LaLiga split found in the V2 pass
# (docs/contradiction-log.md). This is a presentation-layer alias for THIS
# module only -- it does not touch the canonical warehouse column.
LEAGUE_ALIASES = {"LaLiga": "La Liga"}
FBREF_COMPS = ["Premier League", "Serie A", "Ligue 1", "La Liga", "Bundesliga"]
TRUSTED_CONFIDENCE = {"exact", "high", "alias"}


def dev_outcomes_only(outcomes_future: pd.DataFrame) -> pd.DataFrame:
    """The ONE correct way to get a locked-safe slice of
    transfer_performance_outcomes_future: filter on outcome_season, not
    transfer_season. validate.locked_guard.dev_only() filters on a single
    event-date column and is correct for tables like the fee scope where
    features and label share one date; it UNDER-PROTECTS a future-outcome
    table, because a two-season horizon adds +2 to transfer_season, so a
    transfer_season that itself passes dev_only() can still produce an
    outcome_season inside the locked period (e.g. transfer_season=2021,
    two-season outcome_season=2023). Caught by this module's own integrity
    assertion in main() before this function existed -- every downstream
    consumer of transfer_performance_outcomes_future.csv must go through
    this function, never validate.locked_guard.dev_only() directly."""
    return outcomes_future[outcomes_future.outcome_season < LOCKED_SEASON_MIN].copy()

# Funnel steps 1-4 (task §7.4): canonical -> stable player_id -> exact/PIT
# date -> supported outfield role. EVERY downstream table (features_prior,
# outcomes_future) must be built FROM this filtered population, not the
# full 134,147-row transfers_canonical -- otherwise step 5+ counts can
# exceed step 4's, which is not a funnel. (This was a real bug caught by
# inspecting the first run's output: step 5 > step 4.)
BASE_POPULATION_FILTER = f"""
player_id is not null
and date_source in ('exact','exact_raw')
and coalesce(pos_group,'') in {SUPPORTED_OUTFIELD}
"""


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DATA / "warehouse.duckdb"), read_only=True)


def _write_csv(df: pd.DataFrame, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    df.to_csv(path, index=False)
    return path


def build_club_lookup(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per (to_league, to_club_name) with the best-confidence
    fbref_squad match, scoped within the aliased competition (not global —
    reduces cross-league collisions)."""
    tm = con.execute(
        f"""
        select distinct to_league, to_club_name from transfers_canonical
        where to_league in {tuple(LEAGUE_ALIASES.keys()) + tuple(FBREF_COMPS)}
          and to_club_name is not null
        """
    ).fetchdf()
    tm["comp"] = tm.to_league.map(lambda x: LEAGUE_ALIASES.get(x, x))

    rows = []
    for comp in FBREF_COMPS:
        fb_names = con.execute(
            "select distinct Squad from fbref_perf where Comp = ?", [comp]
        ).fetchdf().Squad.tolist()
        tm_names = tm.loc[tm.comp == comp, "to_club_name"].tolist()
        if not tm_names or not fb_names:
            continue
        cw = build_crosswalk(tm_names, fb_names)
        cw["comp"] = comp
        rows.append(cw)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["tm_club_name", "fbref_squad", "confidence", "comp"])
    return out.merge(tm[["to_league", "to_club_name", "comp"]],
                      left_on=["tm_club_name", "comp"], right_on=["to_club_name", "comp"], how="left")


def build_features_prior(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Player's own performance strictly before the transfer. Any club --
    this is what he'd already shown, not tied to the destination. Built
    from BASE_POPULATION_FILTER so the effective-sample funnel is
    monotone (never re-includes rows step 4 already excluded)."""
    q = f"""
    select t.transfer_uid, t.player_id, t.season as transfer_season, t.date as transfer_date,
           f.Season_End_Year as perf_season, f.Comp as perf_league, f.Squad as perf_club,
           f."playing_time__Min_Playing.Time" as minutes,
           f.standard__npxG_Expected as npxg, f.standard__xAG_Expected as xag,
           f.standard__PrgP_Progression as prog_actions,
           f.defense__Tkl_Tackles as tackles, f.defense__Int as interceptions,
           'fbref_perf' as source, 'tm_player_id_direct' as join_method
    from transfers_canonical t
    join fbref_perf f on f.tm_player_id = t.player_id
    where f.Season_End_Year < t.season
      and {BASE_POPULATION_FILTER}
    """
    return con.execute(q).fetchdf()


def build_outcomes_future(con: duckdb.DuckDBPyConnection, club_lookup: pd.DataFrame,
                           eligible_transfer_uids: set[str]) -> pd.DataFrame:
    """Performance AT THE DESTINATION CLUB, next-season and two-season
    windows. Only trusted-confidence club matches are used, and only for
    transfers already in the step-6 population (BASE_POPULATION_FILTER +
    has known-minutes prior performance) -- a label is only useful where a
    feature also exists, and this keeps the funnel monotone (task §7.4)."""
    trusted = club_lookup[club_lookup.confidence.isin(TRUSTED_CONFIDENCE)]
    if not len(trusted) or not eligible_transfer_uids:
        return pd.DataFrame()

    con.execute("CREATE OR REPLACE TEMP TABLE _club_lookup AS SELECT * FROM trusted")
    eligible_df = pd.DataFrame({"transfer_uid": list(eligible_transfer_uids)})
    con.register("_eligible_df", eligible_df)
    con.execute("CREATE OR REPLACE TEMP TABLE _eligible AS SELECT * FROM _eligible_df")
    q = f"""
    select t.transfer_uid, t.player_id, t.season as transfer_season, t.to_league, t.to_club_name,
           cl.fbref_squad as matched_club, cl.confidence as club_match_confidence,
           f.Season_End_Year as outcome_season,
           case when f.Season_End_Year = t.season + 1 then 'next_season'
                when f.Season_End_Year = t.season + 2 then 'two_season'
                else 'other' end as horizon,
           f."playing_time__Min_Playing.Time" as minutes,
           f.standard__npxG_Expected as npxg, f.standard__xAG_Expected as xag,
           f.standard__PrgP_Progression as prog_actions,
           f.defense__Tkl_Tackles as tackles, f.defense__Int as interceptions
    from transfers_canonical t
    join _eligible e on e.transfer_uid = t.transfer_uid
    join _club_lookup cl on cl.to_league = t.to_league and cl.to_club_name = t.to_club_name
    join fbref_perf f on f.tm_player_id = t.player_id
                      and f.Squad = cl.fbref_squad
                      and f.Season_End_Year in (t.season + 1, t.season + 2)
    where {BASE_POPULATION_FILTER}
    """
    return con.execute(q).fetchdf()


def effective_sample_funnel(con: duckdb.DuckDBPyConnection, features_prior: pd.DataFrame,
                             outcomes_future: pd.DataFrame, club_lookup: pd.DataFrame,
                             step6_transfer_uids: set[str]) -> pd.DataFrame:
    """Task §7.4's ten-step funnel. Steps 1-8 are each a STRICT SUBSET of
    the previous one. Steps 9 and 10 both branch off step 8 (population
    with a one-season outcome) rather than off each other: step 9 adds "AND
    also has a two-season outcome" (a stricter, alternative narrowing);
    step 10 adds "AND is in the dev fold" (an unrelated, orthogonal
    narrowing). Comparing step 10 against step 9 for monotonicity is wrong
    — they measure different things off the same parent — so each step
    declares its own parent to check against. (An earlier version of this
    function computed step 5/7 against the full unfiltered table, AND
    separately asserted a blanket step-N <= step-(N-1) rule that broke on
    9->10 for the reason above; both are fixed here.)"""
    steps = []

    def add(step, label, n, note="", parent=None):
        parent = step - 1 if parent is None else parent
        parent_row = next((s for s in steps if s["step"] == parent), None)
        assert parent_row is None or n <= parent_row["rows"], \
            f"funnel step {step} ({n}) exceeds its parent step {parent} ({parent_row['rows']}) — not a funnel"
        steps.append({"step": step, "condition": label, "rows": n, "note": note, "parent_step": parent})

    n0 = con.execute("select count(*) from transfers_canonical").fetchone()[0]
    add(1, "canonical transfer", n0)

    n1 = con.execute("select count(*) from transfers_canonical where player_id is not null").fetchone()[0]
    add(2, "stable player_id (tm_player_id)", n1)

    n2 = con.execute(
        "select count(*) from transfers_canonical where player_id is not null "
        "and date_source in ('exact','exact_raw')"
    ).fetchone()[0]
    add(3, "exact/PIT decision date", n2)

    n3 = con.execute(
        f"select count(*) from transfers_canonical where {BASE_POPULATION_FILTER}"
    ).fetchone()[0]
    add(4, "supported outfield role", n3)

    # features_prior/outcomes_future are already built FROM BASE_POPULATION_FILTER
    # (see build_features_prior/build_outcomes_future), so their transfer_uids
    # are automatically a subset of step 4's population.
    n4 = features_prior.transfer_uid.nunique()
    add(5, "has prior performance (any club, fbref_perf)", n4,
        "built entirely in-repo from fbref_perf; independent of transfer_performance_link_safe")

    n5 = len(step6_transfer_uids)
    add(6, "prior performance with known minutes/exposure", n5)

    trusted_clubs = club_lookup[club_lookup.confidence.isin(TRUSTED_CONFIDENCE)]
    trusted_pairs = set(zip(trusted_clubs.to_league, trusted_clubs.to_club_name))
    tc = con.execute(
        f"select transfer_uid, to_league, to_club_name from transfers_canonical where {BASE_POPULATION_FILTER}"
    ).fetchdf()
    tc = tc[tc.transfer_uid.isin(step6_transfer_uids)]
    n6 = int(tc.apply(lambda r: (r.to_league, r.to_club_name) in trusted_pairs, axis=1).sum())
    add(7, "destination-club outcome link (trusted club-name match)", n6,
        f"club match confidence in {sorted(TRUSTED_CONFIDENCE)} only; "
        f"{len(club_lookup) - len(trusted_clubs)} club names excluded as low-confidence/unmatched")

    n7 = outcomes_future[outcomes_future.horizon == "next_season"].transfer_uid.nunique()
    add(8, "one-season (next-season) outcome observed", n7)

    n8 = outcomes_future[outcomes_future.horizon.isin(["next_season", "two_season"])].groupby(
        "transfer_uid").horizon.nunique()
    n8 = int((n8 == 2).sum())
    add(9, "two-season outcome observed (both windows)", n8, parent=8)

    dev_outcomes = dev_outcomes_only(outcomes_future)
    n9 = dev_outcomes[dev_outcomes.horizon == "next_season"].transfer_uid.nunique()
    add(10, "eligible development fold (outcome_season < locked, one-season outcome)", n9,
        f"locked period outcome_season>={LOCKED_SEASON_MIN} excluded directly (not via "
        "transfer_season, which under-protects 2-season horizons); "
        "branches off step 8 (one-season outcome), not step 9 (two-season)", parent=8)

    return pd.DataFrame(steps)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    con = connect()

    club_lookup = build_club_lookup(con)
    _write_csv(club_lookup, "club_crosswalk.csv")

    features_prior = build_features_prior(con)
    _write_csv(features_prior, "transfer_performance_features_prior.csv")

    step6_transfer_uids = set(
        features_prior.groupby("transfer_uid").minutes.apply(lambda s: s.notna().any())
        .loc[lambda s: s].index
    )

    outcomes_future = build_outcomes_future(con, club_lookup, step6_transfer_uids)
    _write_csv(outcomes_future, "transfer_performance_outcomes_future.csv")

    # integrity assertions on the ACTUAL production output, run every time
    # this regenerates -- not a separate synthetic _check(), these are the
    # invariants that matter and synthetic data wouldn't exercise the real
    # club-name/season data this module depends on.
    assert (features_prior.perf_season < features_prior.transfer_season).all(), \
        "features_prior leaked a same-or-post-transfer-season row"
    if len(outcomes_future):
        assert outcomes_future.club_match_confidence.isin(TRUSTED_CONFIDENCE).all(), \
            "outcomes_future contains a club match below trusted confidence"
        assert (outcomes_future.outcome_season - outcomes_future.transfer_season).isin([1, 2]).all(), \
            "outcomes_future contains an outcome_season outside the declared 1-/2-season horizon"
        assert outcomes_future.horizon.isin(["next_season", "two_season"]).all(), \
            "outcomes_future produced a horizon outside next_season/two_season"
        # Regression guard for the bug dev_outcomes_only()'s docstring describes:
        # the naive dev_only() (transfer_season-based) under-protects two-season
        # horizons. Prove the naive filter would have been unsafe (documents why
        # dev_outcomes_only exists) and that the real one is safe.
        naive_dev_slice = dev_only(outcomes_future, "transfer_season")
        naive_would_leak = (naive_dev_slice.outcome_season >= LOCKED_SEASON_MIN).any()
        assert naive_would_leak, (
            "expected the naive transfer_season-based filter to be unsafe for at least one "
            "two-season row in this data (documents why dev_outcomes_only() exists) -- if this "
            "no longer reproduces, the underlying data window may have changed; re-verify by hand"
        )
        correct_dev_slice = dev_outcomes_only(outcomes_future)
        assert (correct_dev_slice.outcome_season < LOCKED_SEASON_MIN).all(), \
            "dev_outcomes_only() itself let a locked outcome_season through -- this must never happen"

    # locked-period proof, keyed on OUTCOME_season (the protected quantity
    # -- see dev_outcomes_only()'s docstring for why transfer_season is not
    # sufficient here). Nothing in this module computes a metric on the
    # locked slice; this only proves it was identified and excluded.
    audit_frame = outcomes_future.rename(columns={"outcome_season": "season"})[
        ["transfer_uid", "season"]].drop_duplicates()
    write_locked_audit(audit_frame, OUT / "locked_test_audit.json")

    funnel = effective_sample_funnel(con, features_prior, outcomes_future, club_lookup, step6_transfer_uids)
    _write_csv(funnel, "effective_sample_funnel.csv")

    manifest = {
        "command": "python3 -m validate.v3_sporting_target",
        "league_aliases": LEAGUE_ALIASES,
        "trusted_club_confidence": sorted(TRUSTED_CONFIDENCE),
        "locked_season_min": LOCKED_SEASON_MIN,
        "club_crosswalk_match_rate": {
            "total_club_names": int(len(club_lookup)),
            "trusted": int(club_lookup.confidence.isin(TRUSTED_CONFIDENCE).sum()),
        },
        "note": "transfer_performance_outcomes_future built entirely from in-repo fbref_perf + "
                "transfers_canonical. No ESTATE_B_DIR dependency anywhere in this module.",
    }
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(json.dumps(manifest, indent=2, sort_keys=True))
    print("\nEffective sample funnel:")
    print(funnel.to_string(index=False))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
