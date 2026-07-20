# Sporting MVP Results

Decision: `ABSTAIN_INSUFFICIENT_TEMPORAL_RATE_COVERAGE`.

The merged experiment predicts `next_minutes`. It does not properly test future sporting quality or total sporting contribution.

The event-safe minutes baseline is usable for development diagnostics, but current prior sporting-rate coverage is too recent and sparse for a credible temporal persistence test. S2 was not fit and no sporting shortlist is shipped.

## Model Ladder

S0: joint age-role ridge baseline using age, age band, role, and age-role interactions inside each training fold.

M0: S0 plus prior minutes and data freshness. This measures ordinary prior availability, not sporting-rate value.

S1: M0 plus role-appropriate shrunk prior sporting-rate evidence, fit inside each training fold. Rows without supported rate evidence fall back to M0 with `s1_evidence_status`.

S2: compact elastic net, not fit because fewer than three informative S1 folds exist.

## Deployment-Population Metrics

Rows with observed next-season minutes: 1,806. Target: future availability/playing minutes over the next-season horizon.

| Model | Rows | Spearman | NDCG top decile | Top-tier precision | MAE minutes | RMSE minutes |
|---|---:|---:|---:|---:|---:|---:|
| S0 age/role | 1,806 | 0.1462 | 0.5763 | 0.3425 | 731.9 | 862.7 |
| M0 prior availability | 1,806 | 0.1806 | 0.5941 | 0.3260 | 730.9 | 862.0 |
| S1 incremental sporting rate | 1,806 | 0.1757 | 0.5974 | 0.3536 | 729.8 | 859.3 |

Deployment-population S1 includes fallback behaviour and must not be interpreted as clean sporting-rate evidence.

## Rate-Evidence Metrics

Common supported-rate evaluation rows: 614; players: 500. M0 and S1 are compared on identical rows.

| Model | Rows | Spearman | NDCG top decile | Top-tier precision | MAE minutes | RMSE minutes |
|---|---:|---:|---:|---:|---:|---:|
| M0 prior availability | 614 | 0.2072 | 0.5640 | 0.3065 | 707.6 | 842.2 |
| S1 incremental sporting rate | 614 | 0.1836 | 0.5168 | 0.3548 | 704.4 | 833.9 |

Exploratory M0-versus-S1 fold diagnostics:

- informative S1 folds: 2;
- required informative folds: 3;
- rate-evidence Spearman lift: -0.0236;
- rate-evidence top-tier precision lift: +4.84 percentage points;
- 1,000-repetition player-cluster bootstrap interval: [-0.0687, +0.0230], labelled `EXPLORATORY_CONDITIONAL_OOF_INTERVAL`.

This interval is conditional on generated out-of-fold predictions. It is not parameter uncertainty, not proof of temporal stability, and not a substitute for sufficient informative folds.

## Informative-Fold Evidence

`reports/sporting-mvp/fold-model-audit.csv` shows:

- 2016-2019: zero rate-supported evaluation rows;
- 2020: 288 rate-supported evaluation rows but zero rate-supported training rows, so S1 fell back to M0;
- 2021: 288 rate-supported training rows, 315 rate-supported evaluation rows, and 315 rows where M0 and S1 differ;
- 2022: 603 rate-supported training rows, 299 rate-supported evaluation rows, and 299 rows where M0 and S1 differ.

Fallback folds are not counted as positive, negative, or neutral evidence for sporting-rate lift.

## Design Comparisons

One-season versus two-season: `ABSTAIN_INSUFFICIENT_FOLD_SUPPORT`. See `reports/sporting-mvp/design-feasibility.csv`; folds 2016, 2017 and 2022 fail the common two-season threshold.

Direct contribution versus rate x minutes: `ABSTAIN_INSUFFICIENT_TARGET`. Future sporting-rate target coverage is insufficient, so rate x minutes is not reported as ground truth or as a validated challenger.

Minimal versus rich: `STOPPED_BY_GATE`. Performance-rich features were not fit because the S1 temporal-rate coverage gate was not met.

Pooled versus role-specific: `ABSTAIN_INSUFFICIENT_FOLD_SUPPORT`. See `reports/sporting-mvp/design-feasibility.csv`; the role-specific comparison fails the predeclared fold-role requirement.

Small clean versus large noisy: `ABSTAIN_INSUFFICIENT_FOLD_SUPPORT`. Wider/noisier populations are not admitted without timestamp, destination-link and denominator support.

## Minimum Design

The smallest defensible shipped design is not a sporting ranking. It is a retrospective development evidence explorer over a next-season minutes contract with explicit S0/M0/S1 fallback status.

The current evidence does not justify current-player sporting recommendations or buyer-specific economic claims.
