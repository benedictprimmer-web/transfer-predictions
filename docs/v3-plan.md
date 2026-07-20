# V3 Data Spine — Plan

Status: PARTIALLY EXECUTED. This document is the contract; `docs/v3-results.md`
has what actually ran, with numbers. Read `docs/contradiction-log.md` first —
this plan exists because of a mischaracterization in the V2 pass, not
because Estate B ever needed to be found.

## 0. Why this exists

`docs/v2-results.md` (as originally written) said the sporting-contribution
component was blocked by a missing `transfer_performance_link_safe`
(sourced from an external `ESTATE_B_DIR`). External review caught that this
was wrong on the merits: `transfer_performance_link_safe`'s own definition
(`perf_season < transfer_season`) makes it a strictly-**prior** feature
link, not a destination-season outcome source — it was never going to
provide what V2 needed, Estate B or not. This plan builds the thing that
actually was missing, from data already tracked in this repo.

## 1. Canonical grains (task §7.1)

- **Player snapshot**: `player_id × decision_cutoff_date × trailing_window`
  — not separately materialized in this pass; `transfer_performance_features_prior`
  is the closest existing approximation (one row per transfer × prior
  fbref_perf season, which is a trailing-window snapshot at transfer time).
- **Transfer**: `transfer_uid` (existing canonical key, `docs/data-audit.md`
  §2 — not globally unique, 19,113 duplicate-key rows across all of
  `transfers_canonical`; this pass's `BASE_POPULATION_FILTER` scope
  narrows to exact-dated rows where uniqueness is far less of an issue,
  not separately re-verified here).
- **Prior performance**: transfer_uid × prior fbref_perf season.
  `transfer_performance_features_prior`.
- **Future outcome**: transfer_uid × destination-club fbref_perf season,
  1- or 2-season horizon. `transfer_performance_outcomes_future`.
- **Buyer scenario / contract scenario**: not built. Depends on
  Importance/fit and Market cost arms respectively (ADR 0004), neither of
  which has an implementation yet.

## 2. Source provenance (task §3.5, resolved)

| Table | Producer | Tracked at | Season range (verified) | Depends on Estate B at build time? |
|---|---|---|---|---|
| `fbref_snapshot` (→ `shots_selling` view) | `ingest/fbref_snapshot.py` | `data/fbref_snapshot/` | 2018-19 to 2024-25, 4 feeder leagues (not Big-5) | No — frozen local snapshot |
| `fbref_perf` | `ingest/fbref_perf.py` | `data/fbref/perf_player_season.parquet` | **2010-2026**, Big-5 (per its own module docstring, reproduced in `reports/v2-full-data/coverage_cube.csv`) | **Sourced from Estate B originally, but already copied into this repo's tracked `data/`** — `ingest.warehouse build` succeeds without `ESTATE_B_DIR` set |
| `transfer_performance_link_safe` | `ingest/warehouse.py` (materializes live) | not tracked — lives outside `data/` at `ESTATE_B_DIR` | n/a | **Yes** — this is the one table that still needs Estate B present at build time |

`fbref_perf` overlaps the locked period (`season >= 2023`). Every query in
`validate/v3_sporting_target.py` filters explicitly through locked-period
logic; nothing relies on the (previously wrong) assumption that FBref
coverage stopped before the locked boundary.

## 3. Prior feature table

`transfer_performance_features_prior` (`validate/v3_sporting_target.py::build_features_prior`):
one row per (transfer, prior fbref_perf season) where `perf_season <
transfer_season`, joined on `tm_player_id` directly (the same stable ID
`money/scout.py` and `impact/talent.py` already trust). No destination
matching needed — it's the player's own record, any club. Carries raw
counts, minutes, and the per-90-eligible metrics from `docs/mustermann.md`
§1.

## 4. Future outcome table

`transfer_performance_outcomes_future` (`build_outcomes_future`): requires
BOTH stable player ID AND a destination-club match. No club ID crosswalk
exists anywhere in this repo (`ingest/club_crosswalk.py`'s docstring: only
player-level crosswalks exist) — built a deterministic name-normalization
+ token/ratio matcher with an explicit confidence tier (`exact`/`high`/
`alias`/`low`/`unmatched`). **Only `exact`/`high`/`alias` are used in the
outcome table.** This was not a formality: validating the matcher against
the real production club-name lists surfaced genuine false positives at
`low` confidence (Atlético Madrid → Athletic Club, Real Murcia → Real
Madrid, Barnsley → Burnley, Luton → Bolton) — all now locked in as
regression tests in `ingest/club_crosswalk.py::_check()`. Match rate on the
real data: 332/434 (76.5%) of destination club names resolve at trusted
confidence.

Horizons: `next_season` (transfer_season+1) and `two_season`
(transfer_season+2), both computed, kept as separate `horizon` values in
one long table (not two tables) so availability-vs-contribution and
one-vs-two-season comparisons share a schema.

**Locked-period protection is keyed on `outcome_season`, not
`transfer_season`** — a real leakage bug caught during development
(`validate/v3_sporting_target.py::dev_outcomes_only`'s docstring has the
full account): a transfer in season 2021 with a two-season outcome lands
at `outcome_season=2023`, inside the locked period, even though 2021
itself passes the standard `season < 2022` dev-fold filter used elsewhere
in this repo (e.g. the fee prototypes, where features and label share one
date so the simpler filter is correct). Any future consumer of this table
must use `dev_outcomes_only()`, not `validate.locked_guard.dev_only()`
directly.

## 5. Effective-sample funnel (task §7.4)

Implemented as `validate/v3_sporting_target.py::effective_sample_funnel`,
ten steps, each declaring its own parent step (most are step-1, but step 9
and step 10 both branch off step 8 rather than off each other — see
`docs/v3-results.md` for why and the actual numbers). Every `add()` call
asserts `n <= parent`, so a non-monotone funnel fails loudly rather than
shipping quietly wrong (this caught two real bugs during development —
see `docs/v3-results.md` §2).

## 6. What this plan does NOT cover yet

- Buyer scenario / contract scenario grains (blocked on Importance/fit and
  Market cost arms having any implementation).
- A sporting-quality model (S0-S5 ladder, task §9) — the population this
  plan unblocks (2,117 one-season / 1,266 two-season dev rows,
  `docs/v3-results.md`) is real and gated, but no model was fit against it
  in this pass. Explicitly not claimed as done — see
  `docs/v3-results.md`'s brutal verdict.
- Uneven-data tiers A/B/C (task §8) as a formal fitting pattern — Tier A
  fields exist (age, role, competition, PIT MV/contract) and Tier B/C
  fields exist in `fbref_perf` (per-90 metrics, defensive counts), but the
  tiered fit/compare/promote workflow itself was not run.
