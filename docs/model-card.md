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

## V2 development-only prototype (this PR)

FACT - Fee prototype ladder F0 (market-value baseline) vs F1 (minimal: age, position, origin/destination league on top of log market value), Ridge regression, expanding-window walk-forward on the strict V1 fee scope's dev folds (train<=2018, tune=2019, calibration=2020-2021; locked period `season>=2023` never loaded). F1 cleared its predeclared gate (>=5% relative log1p-RMSE improvement, bootstrap CI excludes 0): **11.3% relative improvement, 90% CI [6.2%, 12.0%]**, positive and stable across position and eval-split subgroups. See `docs/v2-results.md`, `reports/v2-full-data/fee_prototype_verdict.json`.

FACT - No sporting-contribution prototype (S0-S7) was attempted. Every design needs `transfer_performance_link_safe`, unavailable in this environment (`docs/reconciliation.md` §4). This is a documented BLOCKER, not a negative result on the sporting target itself.

FACT - This V2 pass is development-only. F1's provisional status is NOT a claim that it would clear the locked final test; the locked period was never loaded (`reports/v2-full-data/locked_test_audit.json`).

## Evaluation Plan

Sporting: temporal rank correlation, minutes-weighted error, contribution-tier calibration, interval coverage, subgroup stability.

Fee/wage: log error, absolute currency error, interval coverage, upper-tail error, era and league calibration.

Recommendation: top-k precision, false-positive rate, NDCG, conservative precision under uncertainty, abstention/coverage trade-off, multi-outcome retrospective diagnostics.

No single positive recommendation label is currently approved.

## Baselines and Complexity

Every nonlinear model must beat the baseline ladder in `docs/modelling-contract.md`. LightGBM, XGBoost and CatBoost are not approved by name; they require temporal evidence.

