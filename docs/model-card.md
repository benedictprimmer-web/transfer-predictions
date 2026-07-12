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

FACT - Current NPV board has 0/98 positive recommendations on the clean PR branch.

FACT - Possession/xT gate is descriptive only: slope -0.0466, CI [-0.0876, -0.0067], n=1,294.

FACT - Strict negotiated-fee candidate rows: 5,151.

## Evaluation Plan

Sporting: temporal rank correlation, minutes-weighted error, contribution-tier calibration, interval coverage, subgroup stability.

Fee/wage: log error, absolute currency error, interval coverage, upper-tail error, era and league calibration.

Recommendation: top-k precision, false-positive rate, NDCG, conservative precision under uncertainty, abstention/coverage trade-off, multi-outcome retrospective diagnostics.

No single positive recommendation label is currently approved.

## Baselines and Complexity

Every nonlinear model must beat the baseline ladder in `docs/modelling-contract.md`. LightGBM, XGBoost and CatBoost are not approved by name; they require temporal evidence.

