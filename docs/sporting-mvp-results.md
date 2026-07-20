# Sporting MVP Results

Decision: `PRIOR SPORTING RATE CHALLENGER DID NOT PASS NEXT-SEASON MINUTES GATE`.

The merged experiment predicts `next_minutes`. It does not properly test future sporting quality or total sporting contribution.

S1 did not pass the predeclared gate, so S2 was not fit and no sporting shortlist is shipped. The supported conclusion is narrower: the revised fold-fitted prior sporting-rate challenger did not pass the temporal gate over the joint age-role baseline for next-season minutes.

## Models

S0: fitted joint age-role ridge baseline using age, age band, role, and age-role interactions inside each training fold.

S1: S0 plus role-appropriate prior sporting-rate evidence with exposure-aware shrinkage and a fold-trained ridge coefficient. Missing role-relevant rates remain missing; rows without supported rate evidence fall back to S0 with an explicit status.

S2: compact elastic net, not fit because S1 failed.

## Overall Development Metrics

Same-row temporal development rows with observed next-season minutes: 1,806. Target: future availability/playing minutes over the next-season horizon.

| Model | Rows | Spearman | NDCG top decile | Top-tier precision | MAE minutes | RMSE minutes |
|---|---:|---:|---:|---:|---:|---:|
| S0 age/role history | 1,806 | 0.1462 | 0.5763 | 0.3425 | 731.9 | 862.7 |
| S1 shrunk prior sporting | 1,806 | 0.1576 | 0.5650 | 0.3260 | 730.0 | 858.8 |

Gate:

- Spearman lift: +0.0113;
- player-clustered 90% CI for out-of-fold Spearman lift: [-0.0106, +0.0305] using 1,000 deterministic player-cluster bootstrap repetitions;
- top-tier precision lift: -1.66 percentage points;
- positive Spearman folds: 1/7;
- S1 gate: failed;
- S2: not fit because S1 failed;
- locked test: not opened.

## Design Comparisons

One-season versus two-season: `ABSTAIN_INSUFFICIENT_FOLD_SUPPORT`. Two-season support is 1,047 rows in the frozen manifest and 1,042 rows in the observed modelling population; it is useful as support metadata, not a selected MVP target.

Direct contribution versus rate x minutes: abstained. Future sporting-rate target coverage is insufficient, so rate x minutes is not reported as ground truth or as a validated challenger.

Minimal versus rich: `STOPPED_BY_GATE`. Performance-rich features were not fit because S1 failed the predefined gate.

Pooled versus role-specific: `ABSTAIN_INSUFFICIENT_FOLD_SUPPORT`. Role-specific folds fail the minimum fold-role support threshold.

Small clean versus large noisy: `ABSTAIN_INSUFFICIENT_FOLD_SUPPORT`. Wider/noisier populations are not admitted without timestamp, destination-link and denominator support.

## Minimum Design

The smallest defensible shipped design is not a sporting ranking. It is a retrospective development evidence explorer over a next-season minutes contract.

The current evidence does not justify current-player sporting recommendations or buyer-specific economic claims.
