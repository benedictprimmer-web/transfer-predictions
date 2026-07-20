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
- S0 Spearman: 0.1462;
- S1 Spearman: 0.1576;
- S1 Spearman lift: +0.0113;
- player-clustered 90% CI for out-of-fold Spearman lift: [-0.0106, +0.0305] from 1,000 deterministic bootstrap repetitions;
- top-tier precision lift: -1.66 percentage points;
- positive Spearman folds: 1/7;
- S2 status: not fit because S1 failed.

The deterministic model/data artifacts do not embed the changing Git commit SHA. Runtime provenance should be collected outside the byte-stable artifacts.

Final wording:

`The revised fold-fitted prior sporting-rate challenger did not pass the temporal gate over the joint age-role baseline for next-season minutes.`

Locked test status: not opened.
