# Data Audit

Run `python3 -m validate.data_audit` to regenerate all audit exhibits. The command writes only small summaries under `reports/data-audit/`.

## 1. File and table inventory

FACT - File inventory: `reports/data-audit/file_inventory.csv`. Warehouse inventory: `reports/data-audit/warehouse_inventory.csv`.

FACT - Current canonical transfer count is 134,147 rows, not 124,183. Source: `reports/data-audit/canonical_summary.json`; row grain: canonical transfer row; filter: all rows; time range: seasons 1992-2026; command: `python3 -m validate.data_audit`.

INFERENCE - The 124,183 count is stale from `MEMO_stage9_merge.md`; the current table includes later raw enrichment/current data.

## 2. Row grain and keys

FACT - `transfer_uid` is not unique in `transfers_canonical`: 19,113 duplicate-key rows. Source: `reports/data-audit/canonical_summary.json` and `reports/data-audit/warehouse_inventory.csv`.

FACT - `valuations` is unique at `(player_id, date)` with 0 duplicate-key rows. Source: `reports/data-audit/warehouse_inventory.csv`.

FACT - TM-to-Understat one-to-many collisions: 3; Understat-to-TM one-to-many collisions: 0. Source: `reports/data-audit/crosswalk_collisions.csv`; row grain: crosswalk row; filter: all rows.

FACT - Understat crosswalk has 6,433 rows, 6,390 distinct lowercased names, and 43 duplicate-name rows. Source: `reports/data-audit/understat_name_join.csv`.

INFERENCE - Production joins must use tested keys or explicit de-duplication rules; `transfer_uid` alone is unsafe as a primary key for fold assignment.

## 3. Timestamp semantics

FACT - Canonical exact-date rows: 29,032; proxy-date rows: 105,115; undated rows: 0. Source: `reports/data-audit/canonical_summary.json`.

FACT - Timestamp gap distribution by date and MV source is in `reports/data-audit/timestamp_gap_summary.csv`.

INFERENCE - A prediction-time feature contract must distinguish exact event date from window proxy date. Proxy-dated rows are not equivalent to announcement or registration dates.

## 4. Transaction taxonomy

FACT - Season/source transaction taxonomy is in `reports/data-audit/transaction_taxonomy_by_season.csv`.

FACT - Current type counts from `warehouse.transfers_canonical`: permanent 49,616; loan 38,770; free 23,287; end-of-loan 19,208; unknown/null 2,711; retirement 555. Source query: `select transfer_type, count(*) from transfers_canonical group by 1`; command used interactively and encoded by taxonomy script.

INFERENCE - Loans, frees, loan returns, paid permanent transfers and undisclosed permanent deals cannot share one continuous fee target.

## 5. Fee semantics and selection

FACT - Thin R2 fee disclosure is 2,584 / 35,139 = 7.35%. Source: `data/transfermarkt/transfers.csv.gz`; filter: `transfer_fee > 0`; time range: 1993-07-01 to 2030-06-30; artifact: `reports/data-audit/fee_disclosure_reconciliation.csv`.

FACT - Current canonical all-type positive-fee coverage is 28,102 / 134,147 = 20.95%. Source: `warehouse.transfers_canonical`; filter: `fee_eur > 0`; artifact: `reports/data-audit/fee_disclosure_reconciliation.csv`.

FACT - Current permanent-only positive-fee coverage is 25,596 / 49,616 = 51.59%. Source: same artifact; filter: `transfer_type='permanent' and fee_eur > 0`.

FACT - Current all-type model-ready fee filter yields 19,859 rows; current paid-permanent eligible filter yields 17,410 rows. Source: `reports/data-audit/fee_disclosure_reconciliation.csv`.

INFERENCE - Fee disclosure is missing-not-at-random. The MNAR audit by era, league, position, age band and transfer type is in `reports/data-audit/fee_selection_mnar_audit.csv`.

## 6. Wages and contracts

FACT - Wage source inventory is in `reports/data-audit/file_inventory.csv`: FIFA wage prior, Capology CSV/parquet, and model outputs are separate artifacts.

FACT - `warehouse.wages_fifa` has 13,650 rows at `(tm_player_id, edition_year)` grain with 0 duplicate-key rows. Source: `reports/data-audit/warehouse_inventory.csv`.

FACT - `warehouse.contracts` has 50,149 rows at `tm_player_id` grain with 0 duplicate-key rows; date range by `contract_expiration_date` is 2000-05-31 to 2035-06-30. Source: `reports/data-audit/warehouse_inventory.csv`.

INFERENCE - Historical contract decisions cannot use current snapshots unless a point-in-time snapshot rule is attached and asserted. No silent wage imputation is approved.

## 7. Market-value integrity

FACT - `warehouse.valuations` has 507,815 rows at `(player_id, date)` grain, 0 duplicates, time range 2000-01-20 to 2026-02-27. Source: `reports/data-audit/warehouse_inventory.csv`.

FACT - Canonical non-null market value rows: 80,727; point-in-time market value rows: 75,857. Source: `reports/data-audit/canonical_summary.json`.

INFERENCE - Transfermarkt market value is a market-consensus proxy, not ground truth. Future market-value growth labels require transfer-contamination and survival-bias flags.

## 8. Future-target feasibility

FACT - Target funnels are in `reports/data-audit/target_sample_funnels.csv`; temporal partition counts are in `reports/data-audit/temporal_fold_counts.csv`.

INFERENCE - Forward two-year market value and resale fee are feasible but selected labels. Sporting contribution and starter retention need stricter destination-season target builders before modelling.

## 9. Missingness and linkage

FACT - Linked prior-performance transfers: 30,489 rows. Unlinked prior-performance transfers: 103,658 rows. Linked rows have 96.95% market-value coverage; unlinked rows have 49.36%. Source: `reports/data-audit/linked_vs_unlinked.csv`.

FACT - Position/league/age coverage is in `reports/data-audit/position_league_coverage.csv`.

INFERENCE - Performance-rich rows are not automatically representative deployment candidates.

## 10. Leakage register

FACT - Executable leakage register: `reports/data-audit/leakage_register.csv` and `docs/leakage-register.md`.

INFERENCE - Random temporal splits, duplicate deals across folds, current-state contracts, post-transfer market values and buyer identity in buyer-agnostic models are all prohibited unless the model contract explicitly permits them.

## 11. Temporal samples and folds

FACT - Expanding-window designs with train/tune/calibration/final-test counts are in `reports/data-audit/temporal_fold_counts.csv`.

INFERENCE - Calibration must be separate from final test. Named sanity cases are not final-test observations.

## 12. Coverage by football population

FACT - `reports/data-audit/position_league_coverage.csv` reports coverage by position/role, destination league and age band, including fee, market-value, FBref and wage-prior rates.

INFERENCE - Current evidence supports abstention for unsupported goalkeeper/defender/defensive-midfielder outputs rather than low rankings.

## 13. Existing-result reproduction

FACT - Usage/WOWY reproduction: Spearman r=0.0767, CI [0.0301, 0.1250], n=1,614. Source: `reports/data-audit/existing_results.csv`; command: `python3 -m validate.stage4 run`.

FACT - Team-delta reproduction: Spearman r=0.0635, CI [0.0201, 0.1067], n=2,164. Source: same artifact.

FACT - Partial slope with controls is inconclusive: 4.73, CI [-0.39, 9.58], n=2,164. Source: same artifact.

FACT - Possession/xT gate result: `python3 -m validate.possession_gate run` gives n=1,294, possession slope -0.0466, CI [-0.0876, -0.0067], descriptive only.

FACT - Benefit OOF backtest: early-to-late Spearman +0.036 CI [-0.031,+0.102]; late-to-early +0.086 CI [+0.032,+0.142]. Command: `python3 -m validate.npv_backtest run`; output written to `data/money/backtest.csv`.

FACT - Current clean-branch NPV board has 98 rows and 0 positive `npv_m` values. Source: `reports/data-audit/existing_results.csv`; filter: `npv_m > 0`.

FACT - Talent-gate claims are not reproduced on the clean PR branch because the talent-model commit is not in `origin/main`. Local unpushed modelling commits can be audited after they are part of the review base.

## 14. Architecture comparison

FACT - Product candidates A-E are assessed in `docs/target-feasibility.md` and this section.

INFERENCE - A fee-versus-consensus residual can be built for disclosed paid permanent deals with PIT market value, but it estimates above/below consensus fee, not genuine undervaluation.

INFERENCE - Future market repricing can be tested, but label selection and fee-contamination must be controlled before it can be treated as an undervaluation target.

INFERENCE - Future sporting contribution has the weakest direct target support today; current usage/WOWY evidence is weak and noisy.

INFERENCE - Buyer-specific economic surplus is the right commercial estimand but needs buyer context, wages/contracts, destination usage and uncertainty. Current data only partially supports it.

PROVISIONAL ARCHITECTURE - Smallest defensible V1 after architecture review: an abstaining staged system with (1) transaction classifier, (2) PIT consensus-fee residual for paid permanent disclosed-fee deals only, (3) separate future-MV repricing monitor flagged as selected/non-ground-truth, (4) separate sporting-availability coverage flags, and (5) no recommendation when wage/contract/position support is missing.

## 15. Owner questions

OWNER DECISION - What is the deployment population: all players, paid permanent transfers only, or buyer-specific shortlists? This changes the transaction target and abstention rules.

OWNER DECISION - What false-positive tolerance is acceptable for "underpriced" recommendations? This controls calibration, thresholding and whether low-coverage rows abstain.

OWNER DECISION - Is the product buyer-specific? If yes, buyer identity/context is required; if no, buyer identity is prohibited.

OWNER DECISION - What horizon matters: next season, two seasons, contract length, or resale window? This selects the target and fold design.

OWNER DECISION - Are non-redistributable/proprietary sources allowed for internal-only use? This changes whether FBref, Capology, Understat and TM-derived artifacts can support production.
