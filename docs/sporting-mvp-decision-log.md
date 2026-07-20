# Sporting MVP Correction Decision Log

As of: 2026-07-20

Source commit before corrections: `75d5781ded752d13bcac5043f6c4fa2eb9855302`.

Environment:

- Python 3.9.6
- pandas 2.3.3
- numpy 1.26.4
- scikit-learn 1.6.1
- pyarrow 21.0.0

Reproduced baseline commands before editing:

```bash
python3 -m validate.sporting_mvp_integrity
python3 -m validate.sporting_mvp_models
python3 -m validate.sporting_mvp_visuals
```

Baseline reproduction:

- frozen rows: 2,117;
- unique players: 1,024;
- one-season support rows: 2,067;
- two-season support rows: 1,047;
- pre-correction manifest hash: `d971a2aa0c44e3f08c1046c42e05da7515e0184c15b574662ea43dfda6989508`;
- pre-correction decision text: `SPORTING SIGNAL TOO WEAK - FEE DIAGNOSTIC MVP ONLY`.

Correction decision:

The merged experiment is a next-season minutes experiment. It does not validate future sporting quality, future sporting rate, total sporting contribution, transfer fee, market-consensus value, or buyer-specific economic value.

Corrected executable result after semantic event-key repair:

- frozen rows: 2,115;
- rows quarantined from the merged 2,117-row population: 2 ambiguous event rows;
- unique players: 1,022;
- corrected manifest hash: `a32621ef87e152e3b6ff761da0c794ccbb33d3254a9a42170029508b03593b0e`;
- model rows with observed next-season minutes: 1,806;
- supported denominator rows: 2,067;
- denominator abstentions: 48;
- S0 age-role Spearman: 0.1462;
- M0 prior-availability Spearman: 0.1806;
- S1 incremental sporting-rate Spearman on the deployment population: 0.1757;
- common supported-rate rows for M0-versus-S1: 614;
- common supported-rate players: 500;
- M0 supported-rate Spearman: 0.2072;
- S1 supported-rate Spearman: 0.1836;
- informative S1 folds: 2;
- required informative folds: 3;
- official decision: `ABSTAIN_INSUFFICIENT_TEMPORAL_RATE_COVERAGE`;
- exploratory player-clustered 90% interval for M0-versus-S1 out-of-fold Spearman lift: [-0.0687, +0.0230] from 1,000 deterministic bootstrap repetitions;
- S2 status: not fit because temporal sporting-rate coverage is insufficient.

The deterministic model/data artifacts do not embed the changing Git commit SHA. Runtime provenance should be collected outside the byte-stable artifacts.

Final wording:

`The event-safe minutes baseline is usable for development diagnostics, but current prior sporting-rate coverage is too recent and sparse for a credible temporal persistence test.`

Locked test status: not opened.
