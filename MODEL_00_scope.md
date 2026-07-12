# MODEL 00 — scope & plan of record

*Phase 0 of `transfer-model-improvement/PROMPT.md`. Executed by Claude Code (the external
GPT 5.6 handoff was abandoned — the returned pack didn't engage with this bundle's specific
findings; see chat). 2026-07-12.*

## Warehouse spot-check (vs `context/DATA_MAP.md`)

Connected `data/warehouse.duckdb` read-only and re-counted every table DATA_MAP cites. All
match exactly, no drift since the July review: `players_master` 50,149, `shots` 539,971,
`valuations` 507,815, `transfers_canonical` 134,147, `fbref_perf` 52,951, `fbref_defense`
14,634, `fbref_niche` 14,634, `injuries` 34,561, `wages_fifa` 13,650, `contracts` 50,149,
`crosswalk_players` 6,433, `shots_selling` 234,800, `transfer_performance_link_safe` 91,081.

Additional schema facts DATA_MAP didn't spell out, confirmed by `describe`:
- `shots.player_id` is the **Understat** id; `crosswalk_players.us_player_id` maps it to
  `tm_player_id` — a cleaner, less lossy join than the name-normalization join
  `impact/aging.py::player_seasons` uses (that one drops ambiguous names before joining;
  the id join only drops what the crosswalk itself couldn't resolve, same 76% ceiling but
  no *additional* collision loss).
- `fbref_defense` / `fbref_niche` are **already TM-keyed** (`tm_player_id`, `season_end_year`)
  — no name join needed for the defensive/turnover features.
- `injuries` is a **career summary, not point-in-time** (module docstring says so explicitly:
  "Not point-in-time safe... for a historical deal use only `spells_before(tm_id, date)`").
  Using the `availability` column as-is on a player-season snapshot would leak future injury
  history into a past prediction. Handled in R3 below.

## Target

Age(+league)-residualized forward 2-year Δlog(market value), per `RESEARCH_PLAN.md` R1.
`valuations` joined on `tm_player_id` (== TM's `player_id`, same numbering as everywhere else
in this warehouse).

## Feature panel (price-blind)

One row per (`tm_player_id`, season), season = Understat "YYYY-YYYY+1" string, snapshot date
= season midpoint (Jan 1 of start_year+1, matching `impact/aging.py`'s convention so
`age_multiplier` slots in directly):

| Feature | Source | Join |
|---|---|---|
| `usage_share`, `shot_share`, `efficiency`, `actions` | `impact.usage.usage_efficiency` on Understat shots | native |
| `age`, `age_sq` | `players_master.date_of_birth` | crosswalk (us→tm) |
| `position_group` (FW/MF/DF) | `players_master.position` via `impact.aging.POS_GROUP` | crosswalk |
| `n90s` (minutes-at-level) | TM `appearances`, Big-5 comps | tm_player_id (native TM numbering) |
| `def_actions_p90` (tackles+int+blocks+recoveries+aerials p90) | `fbref_defense` | tm_player_id + season_end_year |
| `turnover_rate`, `xa_p90`, `prog_actions_p90` | `fbref_niche` | tm_player_id + season_end_year |
| `avail_trailing3y` | `ingest.injuries` raw spells, re-derived **point-in-time** (trailing 3y as-of snapshot date, not the leaky career column) | tm_player_id |
| `age_curve_mult` | `impact.aging.age_multiplier(age, position)` | native |

Excluded by the price-blindness guard (never as features): `market_value*`, `mv_*`, `wage*`,
`fee*`, `overpay*`, `price*`. `wages_fifa` and `contracts` are not used as features at all —
wage is price, and `contract_expiration_date` is current-state (leak risk independent of the
price-blindness rule).

## Split scheme

Expanding-window walk-forward by season, mirroring `money/fees.py::fit_residuals` exactly
(the pattern already fixed there this review cycle). `MIN_TRAIN_ROWS` floor; thin early
seasons dropped, never backfilled. No random K-fold anywhere in this model.

## The four gates (unchanged from `GATES.md`, copied here for the record)

1. Beats an age(+league)-only baseline out-of-time (CI on Spearman lift excludes 0).
2. Haaland→City underpay / Antony→Utd overpay sign-holds when the talent score feeds the
   price gap.
3. Decile cohort monotonicity: talent-minus-price gap decile → realized forward-MV growth,
   top−bottom spread CI excludes 0.
4. Reformulated gem screen (within-position, age-residual baseline, realized-fee outcome)
   beats the ~0.43 base rate the July review measured, CI excludes 0.

**Edge PROVEN** iff gates 3 and 4 both pass. Anything less is reported as **PRESENT BUT
UNPROVEN**, honestly, per the house rule (never loosen a gate to manufacture a pass).

## What's out of scope for this pass

xT/VAEP enrichment (`PROMPT.md`'s optional track) — deferred unless gate 1 or gate 4 comes
back marginal, per the brief. Not built speculatively.
