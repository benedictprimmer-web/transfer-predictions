# V2 Development Verdict

Status: development-only. Nothing here is a locked-final-test result and
nothing here is a production model. See `docs/v2-full-data-plan.md` for what
was and wasn't attempted, and `docs/reconciliation.md` for the branch
repair this builds on.

## 1. Sporting target: BLOCKED, not run

FACT — `transfer_performance_link_safe`, the table that would connect a
transfer to the player's destination-season performance, is unavailable in
this environment (materialized from an external `ESTATE_B_DIR` never
committed to this repo — `docs/reconciliation.md` §4). Every sporting design
in the task's S0-S7 ladder needs it. No sporting prototype was run, and no
proxy target was substituted. This is recorded as a BLOCKER: the sporting
component of V1/V2 remains `NOT V1-SUPPORTED` for the same reason it already
was before this PR (`docs/target-definitions.md`), now additionally blocked
from *any* re-validation in this specific environment.

## 2. Fee prototype: F0 vs F1, gate PASSED

Population: strict V1 negotiated-fee scope (`V1_FEE_SCOPE`,
`validate/modelling_contract.py`) — exact-date, disclosed, paid-permanent,
outfield, age 18-29, PIT market value. 5,151 rows total; 2,461 in the dev
folds used here (`train<=2018`: 1,536, `tune=2019`: 399,
`calibration=2020-2021`: 526); 2,690 in the locked period (`season>=2023`),
**never loaded** (`reports/v2-full-data/locked_test_audit.json`).

Gate, frozen in `validate/v2_fee_prototypes.py::EXPERIMENT_MANIFEST` before
any model was fit: F1 ships as a challenger only if it cuts pooled
dev-evaluation log1p(fee) RMSE by >= 5% relative to F0, with a 90%
bootstrap CI on the RMSE difference that excludes 0.

| Design | Features | n (tune+calibration) | log1p(fee) RMSE | Relative improvement vs F0 | 90% CI | Gate |
|---|---|---:|---:|---:|---|---|
| F0 | `market_value_eur` only, no fit | 925 | 0.808 | — | — | baseline |
| F1 minimal | age, age², position, origin league, destination league, log(MV) — Ridge, expanding-window walk-forward | 925 | 0.717 | **+11.3%** | **[+6.2%, +12.0%]** | **PASS** |

Subgroup stability (`reports/v2-full-data/subgroup_results.csv`): positive
improvement in every position group (DEF +10.8%, FWD +6.8%, MID +16.8%) and
both eval splits (tune +10.8%, calibration +11.8%) — no subgroup shows
deterioration, which the gate also required.

**Decision**: F1 (age/role/league on top of market value) is the
provisional fee-diagnostic design over the pure market-value baseline. This
is a *development* result on `tune`/`calibration` folds only; it says
nothing about the locked period and must not be read as validating a
production fee model. F1's residual is a deviation from market consensus,
not a labelled "undervaluation" — the existing V1 output-policy prohibition
(`docs/modelling-contract.md`) still applies.

F2-F5 (contract years, sporting-evidence block, league/context challengers,
broad kitchen-sink) were not run — see `docs/v2-full-data-plan.md` for why,
and "Remaining decisions" below for what would be next.

## 3. Mustermann evidence layer

See `docs/mustermann.md` §7 for the full per-idea table. Summary: per-90
transform, raw-total-always-shown, fold-safe shrinkage, domestic
percentiles, and the 7-dimension evidence card (no composite score) were
implemented and self-tested (`impact/evidence.py`). Adjusted-global
percentile, league-strength challengers, and possession/context adjustment
were **not shipped** — either already gated-and-failed on a different
metric (league strength) or left as untested future hypotheses (context,
metric-specific translation).

## 4. Full-data descriptive findings

See `reports/v2-full-data/analysis.md` for the complete FACT/INFERENCE
synthesis. Headlines:

- ~40% of `fbref_perf` rows are low-minutes or minutes-unknown — the
  concrete case for shrinkage over a hard cutoff.
- 405/439 (92%) of (season, league, role) cells support a domestic
  percentile at a 20-player minimum; the 5-league `fbref_perf` footprint is
  small relative to the 134,147-row canonical transfer table, so this
  coverage is real but narrow.
- **Data-quality finding**: `transfers_canonical` league labels split
  `"La Liga"`/`"LaLiga"` at the competition's 2023 rebrand — a real defect
  in `ingest/merge.py`'s normalization, out of scope to fix here, logged in
  `docs/contradiction-log.md`.

## 5. Locked test: untouched

`reports/v2-full-data/locked_test_audit.json` and
`validate/locked_guard.py::assert_no_locked()` (called at load time inside
`validate/v2_fee_prototypes.py` and `validate/v2_full_data.py`) prove the
`season >= 2023` period was excluded by row-key hash before any model saw
data, with no locked-row outcome computed or exposed. `validate/locked_guard.py`
has its own offline self-check (`python3 -m validate.locked_guard`).

## Remaining decisions (owner)

1. **F2 (add PIT contract years)**: the next predeclared experiment if
   further fee-model complexity is wanted. Not run — F1 already cleared its
   gate and section 11.4's simplicity rule argues against adding complexity
   without a specific reason to suspect F1 is insufficient.
2. **Estate B / `transfer_performance_link_safe`**: without it (or an
   in-repo equivalent), the entire sporting-contribution component stays
   unsupported and unvalidatable in this environment. This blocks the
   single highest-value V2 component (task's own framing: "usage/WOWY
   evidence is weak and noisy," `docs/data-audit.md` §14).
2b. Restoring it likely means either committing the relevant Estate B
    parquet into this repo's tracked `data/` (licensing permitting — not
    checked here) or rebuilding an equivalent link from `fbref_perf` +
    `transfers_canonical` directly inside this repo.
3. **`La Liga`/`LaLiga` league-name normalization**: a real, narrow fix to
   `ingest/merge.py`, not made in this PR to avoid re-churning the
   reconciled row counts in `docs/reconciliation.md`.
4. **Talent-model `talent_pctl` scout-board join**: 0/120 non-null despite
   24 same-season talent scores existing — a real but narrow defect in
   `main`'s own feature, flagged in `docs/contradiction-log.md`, not fixed
   here (out of scope: it's a `main`-authored feature, not part of the
   audit/V1 contract or this PR's V2 additions).
5. Whether F1's log1p(fee) residual, framed strictly as "deviation from
   market consensus," is worth exposing as a new diagnostic column
   alongside the existing `money/fees.py` HistGBR fee ranker, or whether one
   fee model is enough — this is a product decision, not a modelling one.
