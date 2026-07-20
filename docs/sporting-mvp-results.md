# Sporting MVP Results

Decision: `SPORTING SIGNAL TOO WEAK - FEE DIAGNOSTIC MVP ONLY`.

S1 did not pass the predeclared gate, so S2 was not fit and no sporting shortlist is shipped.

## Models

S0: age/role historical baseline.

S1: price-blind shrunk prior sporting evidence with exposure-aware partial pooling.

S2: compact elastic net, not fit because S1 failed.

## Overall Development Metrics

Same-row temporal development rows with observed next-season minutes: 1,808.

| Model | Rows | Spearman | NDCG top decile | Top-tier precision | MAE minutes | RMSE minutes |
|---|---:|---:|---:|---:|---:|---:|
| S0 age/role history | 1,808 | 0.1278 | 0.5482 | 0.3370 | 730.9 | 858.7 |
| S1 shrunk prior sporting | 1,808 | 0.0762 | 0.5549 | 0.3591 | 793.2 | 962.6 |

Gate:

- Spearman lift: -0.0516;
- top-tier precision lift: +2.21 percentage points;
- positive Spearman folds: 0/7;
- S1 gate: failed;
- locked test: not opened.

## Design Comparisons

One-season versus two-season: one-season selected. Two-season support falls to 1,047 rows in the frozen manifest, so it is useful as support metadata, not the MVP target.

Direct versus rate x minutes: direct minutes ranking is the only fitted validation target. Rate x minutes is retained as a decomposition in the visuals, not promoted to a ranking model.

Minimal versus rich: minimal S1 was tested. Performance-rich features were rejected for MVP because detailed metrics are sparse and would change the population.

Pooled versus role-specific: partial pooling was selected. Role-specific models are too thin by fold for this sample.

Small clean versus large noisy: exact/PIT and trusted destination rows are selected. Wider match-confidence rows are excluded because the V3 crosswalk found real false positives in low-confidence matches.

## Minimum Design

The smallest defensible shipped design is not a sporting ranking. It is a retrospective evidence explorer over the validated development contract.

The current evidence does not justify current-player sporting recommendations.

