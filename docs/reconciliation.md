# Branch Reconciliation — PR #1 x main

Written after merging `origin/main` (SHA `45fc61e`) into `agent/data-audit-pr`
(SHA `84c6b41`) at merge commit `ead7c73`, then regenerating every audit and
contract exhibit on the combined tree. Every number below was reproduced by
running the listed command on the combined branch on 2026-07-13, not copied
from either branch's Markdown.

## 1. What each branch actually contained

FACT — `agent/data-audit-pr` (5 commits) added Phase 0 audit machinery
(`validate/data_audit.py`), a proposed V1 modelling contract
(`validate/modelling_contract.py`), ADRs, target/leakage docs, and generated
exhibits under `reports/`. It did not touch `money/scout.py`,
`impact/talent.py`, or any data file.

FACT — `main` (5 commits beyond the same merge base) added a price-blind
talent model (`impact/talent.py`, `validate/talent_gate.py`), wired a
`talent_pctl` diagnostic column into `money/scout.py`'s board, fixed an
HTML-entity bug in two name parsers, archived stale root docs into
`docs/archive/`, and added a root `README.md`. It did not touch anything
`validate/data_audit.py` or `validate/modelling_contract.py` depend on.

FACT — The merge (`ead7c73`) was a clean, conflict-free 3-way merge. Git's
rename detection matched every doc-archival move on `main` with the
unmodified files still at their old paths on the PR branch. `git diff
--diff-filter=U` shows zero conflicted paths.

## 2. Reconciliation table

| Claim | PR branch before merge | main before merge | Combined branch (reproduced) | Command/source | Explanation |
|---|---:|---:|---:|---|---|
| Canonical transfer rows | 134,147 (claimed) | 134,147 (same parquet, untouched by main) | **134,147** | `python3 -m validate.data_audit` → `reports/data-audit/canonical_summary.json` | `data/merged/transfers_canonical.parquet` is byte-identical across both branches (unchanged since merge base); reproduces exactly. |
| Strict V1 negotiated-fee scope | 5,151 (claimed) | N/A — contract script didn't exist on `main` | **5,151** | `python3 -m validate.modelling_contract` → `v1_transfer_prediction_key_unique` check | Reproduces exactly; check passes (5,151 rows, 5,151 distinct V1 keys). |
| Usage/WOWY Spearman | 0.0767, CI [0.0301, 0.1250], n=1,614 (claimed) | Same result would reproduce — `validate/stage4.py` and every data file it reads (`shots.parquet`, crosswalk, transfermarkt) are byte-identical between branches (`git diff main...PR -- validate/stage4.py` empty) | **0.0767, CI [0.0301, 0.1250], n=1,614** | `python3 -m validate.stage4 run` | Reproduces exactly. Not a race between branches — same code, same data on both sides. |
| **NPV board (clean scout_arsenal.csv)** | **98 rows, 0 positive** (claimed, matches PR branch's *committed* file) | **120 rows, 5 positive** (main's committed file — `money/scout.py` was re-run as part of the talent-model commit) | **120 rows, 5 positive** (`python3 -m money.scout run`, re-executed post-merge) | `reports/data-audit/existing_results.csv`, `data/money/scout_arsenal.csv` | **Real contradiction, resolved by re-running, not by picking a branch.** `money/scout.py`'s NPV logic is byte-identical on both branches (main only *adds* a diagnostic `talent_pctl` column — see §3). The PR branch's checked-in `scout_arsenal.csv` was never regenerated on that branch; it is the stale artifact carried over from the `33dae99` "pre-improvement-wave snapshot" initial commit. Actually executing the unchanged `money/scout.py` against the unchanged input data — on either branch — produces 120/5, matching what main's own re-run already showed. **0/98 was stale, not a live finding.** |
| Talent-gate reproduction | Not reproducible on PR branch (talent-model commit wasn't on `origin/main`'s ancestry the PR branch shared, per `docs/data-audit.md` §13) | `MODEL_verdict.md` claims "edge PRESENT BUT UNPROVEN" | **Reproduced: edge PRESENT BUT UNPROVEN** — gate1 PASS (Spearman lift 0.150, CI [0.127,0.171] excl. 0), gate2 FAIL (Antony not runnable — no fee/MV match), gate3 FAIL (cohort monotonicity CI includes non-monotone step), gate4 PASS (screen beats base rate) | `python3 -m validate.talent_gate run` | Matches `MODEL_verdict.md` exactly. |
| Prior-performance link (linked/unlinked, join funnels) | Linked 30,489 / unlinked 103,658 (claimed) | N/A | **UNAVAILABLE IN THIS ENVIRONMENT** — `transfer_performance_link_safe` is materialized at warehouse-build time from `ESTATE_B_DIR` (default `/Users/benrimmer/Downloads/football-transfer-db`), a raw source directory outside this repo's tracked `data/`. It is not present in this container and was never committed (it lives outside `data/` entirely). | `python3 -m validate.data_audit` (patched to detect and flag, not crash or fabricate zero) | This is an environment gap, not a merge conflict — it would have blocked the PR branch's own audit re-run in *this* environment too. Recorded as `NaN` / explicit `UNAVAILABLE_IN_THIS_ENVIRONMENT` markers, never as 0. See §4. |
| League strength | Failed predictor gate, descriptive only (HANDOFF.md, MEMO_stage5_leagues.md) | Same (unaffected by merge — `impact/leagues.py`, `validate/stage5_gate.py` untouched by either branch's diff) | **Unaffected — still descriptive only.** Not independently re-run this session (out of scope of the two required validate commands); no code in the merge touched it. | `docs/archive/MEMO_stage5_leagues.md`, `HANDOFF.md` §5 | No reconciliation needed; neither branch changed the inputs. |
| Fold manifest / temporal counts | design_A/B train/tune/calibration/final_test row counts (claimed) | N/A | **Reproduces**: e.g. design_A final_test (season≥2022) = 22,873 all-transfers / 4,075 paid-permanent / 4,345 model-ready-fee / 10,273 mv-forward-2y | `python3 -m validate.data_audit` → `reports/data-audit/temporal_fold_counts.csv` | Confirms `season >= 2022` (design_A) / `season >= 2023` (modelling-contract's `design_A_recommended`) as the locked-final-test boundary — see locked-test protection below. |
| Contract acceptance checks | 19 checks listed as passing in PR body (implied) | N/A | **18/19 pass, 1 explicitly NOT RUN** (`future_performance_excluded_from_safe_link`, blocked by the same Estate B gap) | `python3 -m validate.modelling_contract` — exit code 0 | The one non-runnable check is a leakage assertion on `transfer_performance_link_safe`; it is reported as `passed=None` ("not run"), never silently passed or silently failed. |

## 3. Why the merge itself was safe (no factual contradiction to adjudicate)

FACT — `money/scout.py`, `money/inflation.py`, and `ingest/wages_capology.py`
each appear in the file-level diff stat as "changed on both sides", but the
actual PR-branch-vs-merge-base diff for all three is empty. All real changes
came from `main`, and every one was additive/cosmetic (a new diagnostic
column, an HTML-unescape bug fix, an output-path rename) — none altered the
NPV, fee, or usage/efficiency computation. The merge did not have to choose
between two different numeric claims for the same computation; the apparent
98-vs-120 discrepancy above was a staleness bug (an artifact nobody
regenerated), not two branches computing a different truth.

## 4. Estate B: a genuine, pre-existing environment gap

`ingest/warehouse.py` builds every warehouse table as a DuckDB view over
files under this repo's `data/` — except one: `transfer_performance_link_safe`
is `CREATE TABLE ... AS SELECT * FROM read_parquet('{ESTATE_B_DIR}/03_performance/transfer_performance_link.parquet')`,
where `ESTATE_B_DIR` defaults to `/Users/benrimmer/Downloads/football-transfer-db`
— the original author's local machine, never tracked in this repo (it is
outside `data/`, and the commit that "tracked the full data/ directory"
(`8869f0`) could not have included it). This container does not have that
directory, `ESTATE_B_DIR` is unset, and the table silently fails to
materialize.

`validate/data_audit.py` and `validate/modelling_contract.py` both crashed
outright the first time they were re-run on the combined branch, on a
`CatalogException` for this table. This is not something the merge caused —
it would have hit the PR branch's own re-run in this same environment, and
was masked only because the PR's exhibits in the repo were generated on a
machine that *did* have Estate B mounted. Both scripts are now patched
(commit `09f524a`) to detect the table's absence via
`information_schema.tables` and mark the ~5 dependent numbers as
unavailable rather than crashing the whole audit or reporting a false zero.
This also unblocked `data/warehouse.duckdb` itself, which had been committed
with view definitions baked to the same absolute author-machine path
(`/Users/benrimmer/Transfer Predictions/...`) and needed a straight rebuild
(`python3 -m ingest.warehouse build`) to resolve against this checkout.

**Consequence for V2 scope:** any full-data analysis of linked-vs-unlinked
prior-performance populations, or a sporting/availability target that needs
`transfer_performance_link_safe`, cannot be built or verified in this
environment. Section 9.1 sporting-target work in this PR is scoped down
accordingly (see `docs/v2-results.md`) — this is a documented BLOCKER for
that one component, not a silent gap.
