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

Corrected executable result:

- frozen rows: 2,117;
- unique players: 1,024;
- corrected manifest hash: `8df9e5662689ac9d83d963685b261166fec98d61ba2636cfcf2e2a138f03eef0`;
- model rows with observed next-season minutes: 1,808;
- S0 Spearman: 0.1278;
- S1 Spearman: 0.0974;
- S1 Spearman lift: -0.0304;
- player-clustered 90% CI for Spearman lift: [-0.0615, -0.0039];
- top-tier precision lift: -3.31 percentage points;
- positive Spearman folds: 0/7;
- S2 status: not fit because S1 failed.

Final wording:

`The tested handcrafted sporting score did not produce stable temporal improvement over the age/role baseline for next-season minutes.`

Locked test status: not opened.
