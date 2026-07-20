# Sporting MVP Data Integrity

## League Canonicalisation

`ingest/merge.py` now maps Transfermarkt competition id `ES1` to canonical `La Liga`, not `LaLiga`.

The canonical transfer table preserves source labels in `from_league_source_label` and `to_league_source_label`, then exposes canonical labels through `from_league` and `to_league`.

Audit result:

- prior branch artifact had 731 destination rows labelled `LaLiga`;
- regenerated artifact has 0 destination rows labelled `LaLiga`;
- `reports/sporting-mvp/data-fix-summary.csv` records the repair;
- `reports/sporting-mvp/join-funnel.csv` reproduces the V3 funnel after the fix.

## Talent Percentile Join

The current scout board previously attempted to join `talent_pctl` from `data/money/talent_scores.csv`.

That join is invalid for current candidates. The right-hand table is historical walk-forward output with labelled seasons; the scout board uses current Understat season strings and has no leak-safe current-season inference path for the talent model.

Decision: remove `talent_pctl` from `money/scout.py` rather than manufacture coverage. Existing historical `talent_scores.csv` rows remain untouched.

Audit result:

- right table rows: 14,891;
- duplicate right keys: 0;
- current-board join validity: false;
- current board no longer exposes `talent_pctl`.

## Prediction Key

`validate.sporting_mvp_integrity` creates deterministic `spmvp1` keys from:

- player id;
- decision date, or season fallback where the transfer date is unavailable;
- origin club id/name;
- destination club id/name;
- transaction type;
- original transfer uid as source-event id;
- deterministic collision sequence.

`transfer_uid` is preserved but is not trusted as globally unique.

`reports/sporting-mvp/key-collisions.csv` records base-key collisions and the two duplicate-null outcome rows that are explicitly collapsed into the 2,117-row frozen manifest.

## Locked Protection

Development artifacts filter on `outcome_season`, not transfer season.

Rows with `outcome_season >= 2023` are not scored, summarised, fitted, or calibrated in the MVP scripts. The locked test remains closed.

