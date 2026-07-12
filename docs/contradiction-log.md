# Contradiction Log

Generated from current files plus `reports/data-audit/*`.

| Claim | Reproduced evidence | Label | Resolution |
|---|---:|---|---|
| Canonical transfers are 124,183 | Current `warehouse.transfers_canonical` has 134,147 rows | FACT | 124,183 is an older documented post-merge/pre-raw-enrichment count in `MEMO_stage9_merge.md`. Current table is 134,147. Do not reuse 124,183 for current artifacts. |
| Canonical transfers are 134,147 | `reports/data-audit/canonical_summary.json` reports 134,147 | FACT | This is the current reproducible count. |
| Fee disclosure is 7.4% | Thin R2 `data/transfermarkt/transfers.csv.gz`: 2,584 / 35,139 = 7.35% | FACT | Valid only for the thin source file, not canonical. |
| Fee disclosure is 19.7% | Current canonical all-type positive-fee rate is 28,102 / 134,147 = 20.95% | FACT | The 19.7% claim is close to a previous canonical denominator. Current all-type canonical coverage is 20.95%; permanent-only coverage is 51.59%. |
| Fee-model rows are 16,233 | Current canonical model-ready filter yields 19,859 all-type rows; paid-permanent eligible yields 17,410 | FACT | 16,233 was an older documented model-ready count. Current filters differ after raw enrichment/current table changes. |
| Market-value observations are 445,671 | Current `warehouse.valuations` has 507,815 rows | FACT | 445,671 is stale or from a stricter historical subset not reproduced by current warehouse. |
| Usage/efficiency impact correlation is about 0.077 | Real `validate.stage4` reproduction: WOWY Spearman r=0.0767, CI [0.0301, 0.1250], n=1,614 | FACT | Reproduced. |
| Single-season WOWY is roughly 80% noise | Existing `validate.null_test` command only prints synthetic/summary output, not the exact 80% ratio | INFERENCE | Treat 80% as supported by older memo unless a dedicated table-level null-noise script is added. |
| Gem screen scored about 44% against 43% base rate | Not reproducible on clean `origin/main` because the talent-model commit is not in the PR base | FACT | Treat as out of scope for this audit-only PR unless the modelling commits are merged first. |
| Talent-minus-price failed to predict repricing reliably | Not reproducible on clean `origin/main` because the talent-model commit is not in the PR base | FACT | Treat as out of scope for this audit-only PR unless the modelling commits are merged first. |
| NPV board produced no positives among 98 candidates | Current clean-branch `data/money/scout_arsenal.csv` has 98 rows and 0 positive `npv_m` rows | FACT | Reproduced on the PR branch. Local unpushed modelling commits change this artifact to 120 rows/5 positives, so compare only within a pinned commit. |
| Fee model uses random CV | Current `money/fees.py::fit_residuals` uses walk-forward seasons | FACT | The random-CV claim is stale for current code; older docs correctly describe it as a prior/live defect. |
| Haaland and Antony are development sanity cases | `validate.talent_gate` and `money/fees.py` explicitly use them as gates | FACT | They must not be presented as untouched final-test observations. |
| Goalkeeper/defensive valuation coverage is inadequate | FBref and defensive tables exist, but target and coverage artifacts do not establish position-comparable value for GKs/defenders | INFERENCE | Unsupported populations should abstain until a target-specific validation passes. |
| Historical wage, contract, ClubElo, xT freshness claims conflict | Inventory shows Capology/FIFA wage files, current/PIT contract ambiguity, ClubElo through 2026-08-30, and possession gate descriptive-only | FACT | Resolve per artifact and timestamp rule, not by doc prose. |
