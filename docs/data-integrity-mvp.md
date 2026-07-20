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

## Prediction Event Key

`validate.sporting_mvp_integrity` creates immutable deterministic `spmvp1` prediction-event keys before feature aggregation or outcome attachment. The key is exposed as `prediction_event_key`; `prediction_key` is retained as a backward-compatible alias.

The key is built from:

- player id;
- decision date, or season fallback where the transfer date is unavailable;
- origin club id/name;
- destination club id/name;
- transaction type;
- original transfer uid as source-event id;
- deterministic collision sequence.

`transfer_uid` is preserved but is not trusted as globally unique.

`reports/sporting-mvp/key-collisions.csv` records base-key collisions and the two duplicate-null outcome rows that are explicitly collapsed into the 2,117-row frozen manifest.

Executable assertions now require:

- no duplicate `prediction_event_key`;
- no material join expansion;
- unique right-hand keys for material joins where expected;
- no target assigned to multiple unrelated events.

`reports/sporting-mvp/join-audit.csv` records before/after row counts and unmatched counts for material Sporting MVP joins.

## Available Minutes and Missingness

The universal 38-match denominator has been removed. Available minutes now come from the supported competition format:

- Bundesliga: 34 matches, 3,060 minutes;
- Premier League, La Liga, Ligue 1 and Serie A: 38 matches, 3,420 minutes.

Unsupported or interrupted competition formats must return `abstain_no_supported_format` rather than a fabricated share.

Missing prior sporting-rate components and unobserved outcomes remain null. `meaningful_participation` is only defined when next-season minutes are observed. Missingness by role, league, season and fold is reported in `reports/sporting-mvp/missingness-summary.csv`.

## Locked Protection

Development artifacts filter on `outcome_season`, not transfer season.

Rows with `outcome_season >= 2023` are not scored, summarised, fitted, or calibrated in the MVP scripts. The locked test remains closed.
