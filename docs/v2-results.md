# V2 Development Verdict

Status: development-only. Nothing here is a locked-final-test result and
nothing here is a production model. See `docs/v2-full-data-plan.md` for what
was and wasn't attempted, and `docs/reconciliation.md` for the branch
repair this builds on.

**CORRECTIONS (2026-07-13, external code review, reproduced independently
before any fix — see `docs/contradiction-log.md` for the full record):**
this document originally (a) mischaracterized `transfer_performance_link_safe`
as a future/destination-season source when it is explicitly a strictly-prior
feature link by design, (b) reported a fee-prototype confidence interval
computed on the *absolute* RMSE difference as if it were a *relative*
percentage-improvement interval, and (c) compared F1 only against a trivial
untrained baseline. All three are fixed below. **For the V3 follow-up that
this correction enabled — a real destination-season sporting target built
without Estate B — see `docs/v3-plan.md` and `docs/v3-results.md`.**

## 1. Sporting target: originally BLOCKED — corrected framing, see V3

FACT (corrected) — `transfer_performance_link_safe` is not a destination-
season source at all, regardless of Estate B availability: its own
definition (`perf_season < transfer_season`) makes it a strictly-**prior**
feature link, deliberately leak-guarded. The original "BLOCKED by missing
Estate B" framing was based on a mischaracterization of what this table
does. See `docs/mustermann.md` §0 and `docs/contradiction-log.md`.

No sporting prototype was run in the original V2 pass, and no proxy target
was substituted — that part stands. **`docs/v3-plan.md` builds a genuine
future-outcome table (`transfer_performance_outcomes_future`) from in-repo
`fbref_perf` + `transfers_canonical`, entirely avoiding Estate B; see
`docs/v3-results.md` for the resulting effective sample and whether a
sporting prototype cleared its gate on it.**

## 2. Fee prototype: corrected baseline and CI

**CORRECTED (2026-07-13):** the original table below reported F1 beating
"F0" (market value = fee, no fit) by "+11.3%, 90% CI [+6.2%,+12.0%]". Two
bugs, reproduced independently before fixing: the bootstrap computed the
*absolute* RMSE difference in log1p(fee) units and that was reported as a
*relative percentage* CI (the two numbers only looked similar because F0's
RMSE, 0.808, happened to be close to 1.0); and the baseline itself (fee=MV,
no fit at all) is trivial — task §13's fee gate explicitly requires
comparing against a *calibrated* baseline, not a naive identity. See
`validate/v2_fee_prototypes.py` and `docs/contradiction-log.md`.

Population: strict V1 negotiated-fee scope (`V1_FEE_SCOPE`,
`validate/modelling_contract.py`) — exact-date, disclosed, paid-permanent,
outfield, age 18-29, PIT market value. 5,151 rows total; 2,461 in the dev
folds used here (`train<=2018`: 1,536, `tune=2019`: 399,
`calibration=2020-2021`: 526); 2,690 in the locked period (`season>=2023`),
**never loaded** (`reports/v2-full-data/locked_test_audit.json`).

Gate, frozen in `validate/v2_fee_prototypes.py::EXPERIMENT_MANIFEST` before
any model beyond F0a/F0b was fit: a design ships as a challenger over
**F0b** (not F0a — F0a is descriptive only, task §13) only if it cuts
pooled dev-evaluation log1p(fee) RMSE by >= 5% relative to F0b, with a
club-block-bootstrapped (`to_club_id`, cluster-robust) 90% CI on the
*relative* improvement that excludes 0.

| Design | Features | n | log1p(fee) RMSE | Relative improvement vs F0b | 90% CI (relative) | Gate |
|---|---|---:|---:|---:|---|---|
| F0a naive | `market_value_eur` only, no fit | 925 | 0.808 | −2.4% | descriptive only, not gated | context |
| F0b calibrated | log(fee) ~ log(MV), refit per fold — **the real baseline** | 925 | 0.789 | 0.0% | — | baseline |
| F1 minimal | F0b + age, age², position, origin/dest. league | 925 | 0.717 | **+9.15%** | **[+6.8%, +11.5%]** | **PASS** |
| F2 contract | F1 + PIT contract years (rows where `contract_is_pit`, 74% of scope) | 925 | 0.736 | +6.7% | [+4.4%,+9.0%] | PASS, but worse than F1 |
| F3 existing HistGBR | `money/fees.py::fit_residuals` on the identical rows/seasons (context only, not row-paired) | 925 | 0.767 | +2.7% | not computed (context only) | context |

Absolute log1p(fee)-RMSE-difference CI (separately, correctly labeled, not
the same statistic as the relative CI above): F1 vs F0b, 90% CI
[0.052, 0.092] log1p-fee units.

Subgroup stability (`reports/v2-full-data/subgroup_results.csv`): positive
improvement in every position group and both eval splits — no subgroup
shows deterioration.

**Decision**: F1 (age/role/league on top of a *calibrated* market-value
model) is the provisional fee-diagnostic design over F0b. **F2 does not
earn its added complexity** — contract years make F1 worse, not better, on
this scope (a genuine "less is more" finding, not a bug: PIT contract
coverage is 74%, and the extra feature/reduced-sample tradeoff nets
negative here). **The existing production `money/fees.py` HistGBR (F3)
underperforms the simple linear F1 on this identical population** — worth
flagging to the owner as a real, if not row-paired, finding rather than
assuming more model complexity implies better fit. This is a *development*
result on `tune`/`calibration` folds only; it says nothing about the locked
period and must not be read as validating a production fee model. F1's
residual is a deviation from market consensus, not a labelled
"undervaluation" — the existing V1 output-policy prohibition
(`docs/modelling-contract.md`) still applies.

F4-F5 (sporting-evidence block, broader context/league challengers) were
not run — F1 already cleared cleanly over the honest baseline, and adding a
sporting-evidence feature (F4) only became possible after the V3 sporting
spine existed (see `docs/v3-results.md`).

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

- 27% of `fbref_perf` rows are low-minutes (`<450`, known exposure) and a
  **separate** 12.6% (6,694/52,951) have **unknown** exposure (minutes
  field is null) — corrected from the original pass, which reported these
  as a single "~40% low-minutes-or-unknown" figure. The distinction matters:
  `impact/evidence.py::support_flag` now has a dedicated `unknown_exposure`
  category (originally, `NaN < threshold` silently evaluated `False` and
  such rows fell through to the *highest*-confidence label — a real bug,
  fixed; see `docs/contradiction-log.md`).
- Cohort confidence is now tiered (unavailable `<20`, low `20-49`, moderate
  `50-99`, high `100+`), not a single "viable at 20" cutoff: of 439
  (season, league, role) cells, 265 are `high`, 88 `moderate`, 52 `low`, 34
  `unavailable`. The 5-league `fbref_perf` footprint is small relative to
  the 134,147-row canonical transfer table, so this coverage is real but
  narrow.
- **Data-quality finding**: `transfers_canonical` league labels split
  `"La Liga"`/`"LaLiga"` at the competition's 2023 rebrand — a real defect
  in `ingest/merge.py`'s normalization, out of scope to fix here, logged in
  `docs/contradiction-log.md`.
- New: `reports/v2-full-data/missingness_patterns.csv` (joint feature/label
  availability, previously a required-but-missing artifact) and data-hash
  entries in `full_data_manifest.json` (previously commit-only, no data
  hashes — both fixed).

## 5. Locked test: untouched

`reports/v2-full-data/locked_test_audit.json` and
`validate/locked_guard.py::assert_no_locked()` (called at load time inside
`validate/v2_fee_prototypes.py` and `validate/v2_full_data.py`) prove the
`season >= 2023` period was excluded by row-key hash before any model saw
data, with no locked-row outcome computed or exposed. `validate/locked_guard.py`
has its own offline self-check (`python3 -m validate.locked_guard`).

## Remaining decisions (owner)

1. **`La Liga`/`LaLiga` league-name normalization**: a real, narrow fix to
   `ingest/merge.py`, still not made — fixing it would re-churn the
   reconciled row counts in `docs/reconciliation.md`. Now also affects
   `docs/v3-plan.md`'s destination-club matching.
2. **Talent-model `talent_pctl` scout-board join** — root-caused, not just
   flagged: the join key is fine (confirmed overlapping IDs exist); the
   real cause is `impact/talent.py`'s forward-2-year-market-value label
   construction, which structurally starves the most recent season (24
   rows for 2023-2024 vs. 1,100-2,060/season historically) via right-
   censoring. Not fixed here — it's a `main`-authored feature and the fix
   (a different label horizon or explicit right-censoring handling) is a
   product decision about `impact/talent.py`, not this PR's scope.
3. Whether F1's log1p(fee) residual, framed strictly as "deviation from
   market consensus," is worth exposing as a new diagnostic column — and,
   given F3 (existing `money/fees.py` HistGBR) underperforms F1 on the
   identical population (§2 above), whether the existing production fee
   model should be revisited.
4. See `docs/v3-results.md` for the sporting-target and separate-arms
   decisions that follow from this V2 correction pass.
