# Model Card: Proposed V1 Staged System

Status: PROPOSED, no production model trained in this PR.

## Intended Use

Internal research prototype for identifying candidate football transfer bargains while controlling false positives through abstention, uncertainty and separate component outputs.

## Not Intended For

Do not use as a headline economic undervaluation engine. Do not use for unsupported goalkeepers/defensive roles, proxy-dated rows, current-state wage/contract historical backtests, or commercial deployment without licensing review.

## Inputs

Timestamped player/transfer snapshot, strictly pre-cutoff market-consensus value, transaction taxonomy, role/age/league fields, and PIT contract years only when `contract_is_pit`.

## Outputs

Market bargain: low expected negotiated fee relative to market consensus.

Sporting bargain: high expected future sporting contribution relative to acquisition cost. NOT V1-SUPPORTED until sporting target builder is approved.

Buyer-specific bargain: expected economic benefit to a named buyer exceeds acquisition cost. NOT V1-SUPPORTED as headline score.

## Evidence

FACT - Current usage/WOWY correlation is weak positive: r=0.0767, CI [0.0301, 0.1250], n=1,614.

FACT - Current NPV board has 120 rows and 5 positive recommendations on the combined branch (post-merge). The earlier "0/98" figure was a stale, never-regenerated artifact from the PR branch's initial snapshot commit, not a live disagreement with `main`'s work — see `docs/reconciliation.md` §2-3. Re-running `python3 -m money.scout run` against unchanged code and data reproduces 120/5.

FACT - Possession/xT gate is descriptive only: slope -0.0466, CI [-0.0876, -0.0067], n=1,294.

FACT - Strict negotiated-fee candidate rows: 5,151.

FACT - Price-blind talent model (`main`, now merged): edge PRESENT BUT UNPROVEN. Gate 1 (beats age baseline) and gate 4 (screen beats base rate) PASS; gate 2 (Haaland/Antony sign check) and gate 3 (cohort monotonicity) FAIL. Reproduced via `python3 -m validate.talent_gate run`.

## V2 development-only prototype (this PR, corrected 2026-07-13)

FACT - Fee prototype ladder: F0a (naive fee=MV, descriptive only) / F0b (calibrated log-fee~log-MV, the real baseline) / F1 (F0b + age, position, origin/destination league) / F2 (F1 + PIT contract years) / F3 (existing `money/fees.py` HistGBR, context only), Ridge regression except F3, expanding-window walk-forward on the strict V1 fee scope's dev folds (train<=2018, tune=2019, calibration=2020-2021; locked period `season>=2023` never loaded). F1 cleared its predeclared gate over F0b (>=5% relative log1p-RMSE improvement, club-block-bootstrap CI excludes 0): **+9.15% relative improvement, 90% CI [+6.8%, +11.5%]**, positive and stable across position and eval-split subgroups. F2 (contract years) is worse than F1 (+6.7%) — added complexity did not earn its place. **F3, the existing production HistGBR model, underperforms the simple F1 linear design on the identical population (+2.7% vs F0b)** — a real finding for the owner, not row-paired but same rows/seasons. (Corrected from an earlier reported "+11.3%, CI [+6.2%,+12.0%]", which bootstrapped an absolute RMSE difference but reported it as a relative-percentage CI, and compared only against the trivial F0a baseline — see `docs/contradiction-log.md`.) See `docs/v2-results.md`, `reports/v2-full-data/fee_prototype_verdict.json`.

FACT - No sporting-contribution prototype (S0-S7) was attempted in the original V2 pass. The reason given then — blocked by `transfer_performance_link_safe`/Estate B — was itself a mischaracterization: that table was never a destination-season source regardless of Estate B (`docs/contradiction-log.md`). See `docs/v3-results.md` for the corrected attempt, built from in-repo data.

FACT - This V2 pass is development-only. F1's provisional status is NOT a claim that it would clear the locked final test; the locked period was never loaded (`reports/v2-full-data/locked_test_audit.json`).

## Evaluation Plan

Sporting: temporal rank correlation, minutes-weighted error, contribution-tier calibration, interval coverage, subgroup stability.

Fee/wage: log error, absolute currency error, interval coverage, upper-tail error, era and league calibration.

Recommendation: top-k precision, false-positive rate, NDCG, conservative precision under uncertainty, abstention/coverage trade-off, multi-outcome retrospective diagnostics.

No single positive recommendation label is currently approved.

## Baselines and Complexity

Every nonlinear model must beat the baseline ladder in `docs/modelling-contract.md`. LightGBM, XGBoost and CatBoost are not approved by name; they require temporal evidence.

