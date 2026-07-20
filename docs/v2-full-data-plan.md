# V2 Full-Data Plan

Status: EXECUTED (scoped). This is the short plan/scope document; results
are in `docs/v2-results.md`, the reconciliation is in
`docs/reconciliation.md`, and the Mustermann evidence-layer design is in
`docs/mustermann.md`.

## Scope actually executed

1. Reconcile PR #1 with `main` (git merge, reproduce audit + contract on the
   combined tree) — `docs/reconciliation.md`.
2. Translate MustermannFM's ideas into guarded, falsifiable designs against
   this repo's real data — `docs/mustermann.md`, implemented in
   `impact/evidence.py`.
3. Deterministic full-data descriptive analysis (coverage, per-90
   distributions, cross-league mover support, percentile cohort viability,
   locked-period exclusion proof) — `validate/v2_full_data.py`,
   `reports/v2-full-data/`.
4. One development-only prototype comparison with a gate frozen before any
   result was inspected: F0 (market-value baseline) vs F1 (minimal
   age/role/league structure) on the strict V1 negotiated-fee scope —
   `validate/v2_fee_prototypes.py`.

## Scope explicitly not executed, and why

- **Sporting designs S0-S7** (task §10.1): every one needs
  `transfer_performance_link_safe` (a destination-season performance link),
  which is materialized from an external `ESTATE_B_DIR` not present in this
  environment (`docs/reconciliation.md` §4). This is a BLOCKER, not a
  deprioritization — attempting a proxy target here would violate the "no
  fabricated proxy to keep modelling moving" rule (task §9.1).
- **F2-F5** (contract years, sporting-evidence block, league/context
  challengers, broad kitchen-sink): F1 already cleared its gate cleanly
  (`docs/v2-results.md` §2). Running F2-F5 without a specific reason to
  suspect F1 is insufficient would be exploring for a better leaderboard
  number rather than testing a predeclared hypothesis — contrary to the
  "less is more" instruction (owner decision 8, task §11.4). F2 (adding PIT
  contract years) is recorded as the next predeclared experiment if the
  owner wants to pursue further complexity — see `docs/v2-results.md`
  "Remaining decisions."
- **Multi-agent wave orchestration** (task §5, three-agent waves): the
  actual repository state (a small, mature, single-maintainer-style
  Python/DuckDB codebase, not the hypothetical scale implied by "134k-row
  enterprise estate needing three parallel research teams") did not warrant
  parallel sub-agent waves for this pass. All work in this PR was done by
  one accountable lead with the same verification standard the task
  specifies for wave synthesis — every number in `docs/v2-results.md` was
  independently re-executed, not narrated from a sub-agent report.
- **League translation, possession/context adjustment challengers**
  (task §6.4, §6.5, §10.4): league strength already failed its gate on the
  Stage-4 predictor (`HANDOFF.md` §5); re-testing the same gate without new
  data/metric would violate "never loosen a gate after seeing a result."
  A *new* metric-specific translation is left as future work
  (`docs/mustermann.md` §8), not run "just to see."
- **One-page HTML summary**: built from the artifacts above — see
  `docs/v2-results.md` for the link.
