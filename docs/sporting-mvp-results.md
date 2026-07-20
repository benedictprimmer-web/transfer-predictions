# Sporting MVP Results

Decision: `HANDCRAFTED SPORTING RATE DID NOT IMPROVE NEXT-SEASON MINUTES`.

The merged experiment predicts `next_minutes`. It does not properly test future sporting quality or total sporting contribution.

S1 did not pass the predeclared gate, so S2 was not fit and no sporting shortlist is shipped. The supported conclusion is narrower: the tested handcrafted prior sporting-rate score did not produce stable temporal improvement over the age/role baseline for next-season minutes.

## Models

S0: age/role historical baseline.

S1: role-appropriate prior sporting-rate evidence with exposure-aware shrinkage. Missing role-relevant rates remain missing; they are not encoded as zero.

S2: compact elastic net, not fit because S1 failed.

## Overall Development Metrics

Same-row temporal development rows with observed next-season minutes: 1,808. Target: future availability/playing minutes over the next-season horizon.

| Model | Rows | Spearman | NDCG top decile | Top-tier precision | MAE minutes | RMSE minutes |
|---|---:|---:|---:|---:|---:|---:|
| S0 age/role history | 1,808 | 0.1278 | 0.5482 | 0.3370 | 730.9 | 858.7 |
| S1 shrunk prior sporting | 1,808 | 0.0974 | 0.5187 | 0.3039 | 761.8 | 909.0 |

Gate:

- Spearman lift: -0.0304;
- player-clustered 90% CI for Spearman lift: [-0.0615, -0.0039];
- top-tier precision lift: -3.31 percentage points;
- positive Spearman folds: 0/7;
- S1 gate: failed;
- S2: not fit because S1 failed;
- locked test: not opened.

## Design Comparisons

One-season versus two-season: count comparison executed. Two-season support falls to 1,047 rows in the frozen manifest, so it is useful as support metadata, not a selected MVP target.

Direct contribution versus rate x minutes: abstained. Future sporting-rate target coverage is insufficient, so rate x minutes is not reported as ground truth or as a validated challenger.

Minimal versus rich: minimal S1 was tested. Performance-rich features were not compared as evidence because detailed metrics are sparse and would change the population.

Pooled versus role-specific: pooled/shrunk S1 was tested. Role-specific models are too thin by fold for this sample and are not reported as executed.

Small clean versus large noisy: count comparison executed. Wider/noisier populations are not admitted without timestamp, destination-link and denominator support.

## Minimum Design

The smallest defensible shipped design is not a sporting ranking. It is a retrospective development evidence explorer over a next-season minutes contract.

The current evidence does not justify current-player sporting recommendations or buyer-specific economic claims.
