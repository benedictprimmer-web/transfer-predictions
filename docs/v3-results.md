# V3 Results

Labels per task convention: FACT (reproduced from code/data), INFERENCE
(interpretation), HYPOTHESIS (testable, not yet supported), DECISION
(architectural/product choice), BLOCKER (needs new authority/data).

## 1. Headline

FACT — A genuine, in-repo, leakage-tested destination-season sporting
outcome table now exists (`transfer_performance_outcomes_future`,
`validate/v3_sporting_target.py`), built without any Estate B dependency.
This corrects the V2 pass's claim that the sporting component was blocked
by missing Estate B — it wasn't Estate B specifically; the table V2 pointed
at was never going to serve this purpose regardless (`docs/contradiction-log.md`).

DECISION — No sporting-quality model was fit against this population in
this pass. Per the task's own closing instruction, a portable, leakage-safe
target with an honest sample funnel is the deliverable here, not a rushed
model. The population (§2) is real and large enough to be worth fitting
against — that is the next step, not this PR's.

## 2. Effective-sample funnel (task §7.4)

FACT — `python3 -m validate.v3_sporting_target` → `reports/v3-data-spine/effective_sample_funnel.csv`:

| Step | Condition | Rows | Parent |
|---:|---|---:|---:|
| 1 | canonical transfer | 134,147 | — |
| 2 | stable player_id | 101,524 | 1 |
| 3 | exact/PIT decision date | 29,032 | 2 |
| 4 | supported outfield role | 25,954 | 3 |
| 5 | has prior performance (fbref_perf, any club) | 4,594 | 4 |
| 6 | prior performance with known minutes | 4,196 | 5 |
| 7 | destination-club outcome link (trusted club match) | 2,778 | 6 |
| 8 | one-season outcome observed | 2,117 | 7 |
| 9 | two-season outcome observed (both windows) | 1,266 | 8 |
| 10 | eligible dev fold (outcome_season < locked, one-season) | 2,117 | 8 |

INFERENCE — the funnel narrows hard at step 3→4→5 (134,147 → 25,954 →
4,594): exact-dated, supported-role transfers with ANY prior fbref_perf
record are a small slice of the canonical table. This matches
`docs/data-audit.md`'s own finding that exact-date coverage (29,032/134,147
= 21.6%) is the single biggest population cut, and is now confirmed to
compound sharply once a real Big-5 performance join is required —
`fbref_perf`'s Big-5-only footprint is the second major cut.

FACT — step 10 == step 8 (both 2,117): every one-season outcome observed
in this population happens to have `transfer_season <= 2021`
(`reports/v3-data-spine/transfer_performance_outcomes_future.csv`, checked
directly — max `transfer_season` with a `next_season` outcome is 2021).
Not a bug: recent exact-dated, fully-fbref-linked transfers thin out
because the label needs a full subsequent fbref_perf season to have
settled, consistent with `docs/data-audit.md` §14's existing finding that
"the recent locked period has no prior-performance links in the
recommended strict fold manifest."

## 3. Two real bugs caught building this, both fixed before shipping

FACT — **Non-monotone funnel (bug 1)**: an earlier version computed step 5
and step 7 against the *unfiltered* `transfers_canonical` rather than the
population already narrowed by prior steps, producing step 5 > step 4 and
step 7 > step 6 — not a valid funnel. Fixed by threading
`BASE_POPULATION_FILTER` through `build_features_prior`/
`build_outcomes_future` and adding a parent-aware monotonicity assertion to
`effective_sample_funnel`'s `add()` helper that now fails loudly on any
regression.

FACT — **Locked-period under-protection (bug 2)**: the standard
`validate.locked_guard.dev_only()` filter (built for tables where features
and label share one date, e.g. the fee scope) filters on `transfer_season`.
Applied naively to `transfer_performance_outcomes_future`, a transfer with
`transfer_season=2021` and a two-season outcome produces
`outcome_season=2023` — inside the locked period — even though 2021 itself
passes the `season < 2022` dev-fold filter. `dev_outcomes_only()` now
filters on `outcome_season` directly, the actually-protected quantity; a
regression test in `main()` proves the naive filter would have been unsafe
on this real data and that the fix is safe. **This was caught by an
integrity assertion before any downstream use, not discovered after.**

## 4. Club crosswalk (task §7.2/§7.3's destination-club requirement)

FACT — No club ID crosswalk exists anywhere in this repo (only player-level
ones). Built `ingest/club_crosswalk.py`: deterministic name normalization
(diacritics, generic-entity-token stripping, `utd`/`united` synonym
collapse) + token-subset/ratio matching + a small curated alias table for
abbreviations that share no substring with the full name (`M'Gladbach`,
`Paris S-G`, `Man City`).

FACT — validated against the real production name lists (408 TM
destination-club names in Big-5 leagues vs. 193 fbref Squad values): 76.5%
(332/434 league-scoped name pairs) resolve at trusted confidence
(`exact`/`high`/`alias`). The `low`-confidence tier was checked by hand and
found to contain **real false positives** — Atlético Madrid → Athletic
Club, Real Murcia → Real Madrid, Barnsley → Burnley, Luton → Bolton — all
different clubs. **Policy: only `exact`/`high`/`alias` are used in
`transfer_performance_outcomes_future`; `low` and `unmatched` are excluded
entirely, not included with a caveat.** The four false positives are now
regression tests in `ingest/club_crosswalk.py::_check()`.

INFERENCE — 23.5% of destination club names don't resolve at trusted
confidence. Some are genuine misses (crosswalk limitations); many are
likely correct non-matches — TM's `to_club_name` includes second/lower-tier
destination clubs (relegations, loans to non-Big-5-top-flight sides) that
never appear in `fbref_perf`'s top-flight-only scrape at all, so "unmatched"
is often the right answer, not a crosswalk failure.

## 5. Separate arms (ADR 0004)

See `docs/architecture-decisions/0004-separate-arms.md` for the full table.
Status this PR: Sporting quality has a data spine, no model. Market cost has
a gated fee-diagnostic prototype (`docs/v2-results.md`). Importance/fit,
Economic worth, and Undervaluation have no implementation — correctly
abstained, not stubbed with a placeholder.

## 6. Locked test: untouched

FACT — `reports/v3-data-spine/locked_test_audit.json`: of 3,462 total
(transfer, outcome-season) pairs in the full (not dev-filtered)
`transfer_performance_outcomes_future` table, 198 fall in the locked period
(`outcome_season >= 2023`) and are excluded by row-key hash only; 533 are
excluded as a one-season buffer; 2,731 are dev-eligible. No locked-row
outcome value was read or computed anywhere in this module — verified by
the regression assertions in §3 above, not just asserted in prose.

## 7. Uneven-data tiers (task §8) — not executed

BLOCKER (soft — data exists, workflow doesn't) — Tier A fields (age, role,
competition, PIT MV/contract) and Tier B/C fields (fbref_perf per-90
metrics, defensive counts) both exist in the data now assembled. The
fit/compare/promote-only-if-it-beats-the-lower-tier workflow itself was not
run in this pass. This is real, scoped-out work, not a silent gap — see
`docs/v3-plan.md` §6.

## Remaining decisions (owner)

1. Whether to fit a sporting-quality prototype (S0 baseline vs. S1
   shrunk-rate challenger, task §9) against the 2,117-row dev population
   now that it's known to exist and be leak-safe. This is the natural next
   PR.
2. Whether `ingest/club_crosswalk.py`'s 76.5% trusted match rate is
   sufficient to proceed, or whether the ~23.5% unmatched pool should be
   triaged further (many are likely correctly non-Big-5 destinations, not
   fixable by a better matcher).
3. Same open items as `docs/v2-results.md`: Estate B still needed for
   `transfer_performance_link_safe` specifically (now understood to be a
   different, non-blocking gap — it was never the outcome source); La
   Liga/LaLiga canonical normalization; `impact/talent.py`'s right-censored
   label horizon.
4. Whether Importance/fit is worth building next (needs a named-buyer
   product decision the owner hasn't made yet, per ADR 0004 and the
   original PR's still-open owner decisions).
