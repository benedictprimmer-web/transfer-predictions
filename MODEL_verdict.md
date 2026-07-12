# MODEL VERDICT — the price-blind talent model

*Phase 4 of `transfer-model-improvement/PROMPT.md`, executed end-to-end by Claude Code
(`impact/talent.py`, `validate/talent_gate.py`), 2026-07-12. See `MODEL_00_scope.md` and
`MODEL_01_research.md` for the design record.*

## What was built

One pooled `HistGradientBoostingRegressor`, expanding-window walk-forward by season (never
random K-fold), predicting age(+league)-residualized forward 2-year Δlog(market value) from 12
price-blind features (usage/efficiency, age, minutes, defensive actions, turnovers, xA,
progression, point-in-time durability, position). **16,842 trainable player-seasons; 14,891
scored** after the first season is dropped to the `MIN_TRAIN_ROWS` floor (disclosed, not
backfilled). Price-blindness enforced structurally: `_assert_price_blind` rejects any feature
whose name contains a price token, checked at both import time and fit time.

`data/money/talent_scores.csv` — one row per scored player-season: `talent_score`, `talent_lo`,
`talent_hi` (reconciled so lo≤point≤hi — independent quantile fits can cross, a known GBT
artifact; fixing the ordering doesn't change what either model learned), `talent_pctl` (rank
within season×position), `price_pctl` (contemporaneous market-value rank, same grouping — the
benchmark, never a feature). Wired into `money/scout.py` as an additional diagnostic column
(`talent_pctl`), alongside the existing `prog_pctl` possession flag — augmenting the board, not
replacing its NPV ranking, per the brief. `validate/npv_backtest.py` re-run clean: Haaland
£-32m / Antony £-66m / Ronaldo £-86m NPV anchor unchanged — no regression from the wiring.

## The four gates

| Gate | Result | Number | CI | n |
|---|---|---|---|---|
| 1 — beats age-only baseline, out-of-time | **PASS** | Spearman lift **+0.150** | [+0.127, +0.171] | 12,907 |
| 2 — Haaland underpay / Antony overpay | **FAIL** | Haaland gap **+75.9** (reads overpay, wrong sign); Antony **not scoreable** | — | 1 of 2 runnable |
| 3 — decile cohort monotonicity | **FAIL** (narrowly) | top−bottom spread **+0.118**, but only **55.6%** of deciles step up (bar: 60%) | [+0.041, +0.262] | 14,891 |
| 4 — reformulated gem screen beats base rate | **PASS** | precision **23.5%** vs base rate **13.2%** | gap CI [+0.083, +0.122] | 1,806 screened |

**Verdict: edge PRESENT BUT UNPROVEN** (the rule is gates 3 *and* 4 both pass; gate 3 missed on
the monotonicity sub-criterion, not the direction).

## Reading each result honestly

**Gate 1 is the clean win.** The price-blind features carry real signal beyond age — a
+0.150 Spearman lift with a CI nowhere near zero, on 12,907 out-of-time predictions. This is
new: the July review never had a trained model to test this against.

**Gate 4 is the second clean win, and it overturns the review's headline negative finding.**
The old gem screen (flat MV threshold, pooled across positions) tied the base rate (0.44 vs
0.43). The reformulated screen — within position×season, percentile-based rather than a flat
MV cut — screens players who hit 2x forward MV growth at **23.5%**, against a **13.2%** base
rate for the same cohort, n=1,806, CI on the gap excluding zero by a wide margin. That the
review's conversion-gate failure was a formulation problem, not an absence-of-edge problem, is
now directly supported by evidence, not just argued.

**Gate 3's failure is a near-miss, and the direction is actually the good news.** Top-minus-
bottom decile spread is positive with a CI that clears zero (+0.041 to +0.262) — this alone is
already better than the July review's within-age-band persistence test, which found Spearman
0.006–0.066 (indistinguishable from noise) everywhere it looked. What fails is *strict*
decile-by-decile monotonicity: only 5 of 9 steps go the right way. With ~1,489 rows per decile,
some zigzag is expected noise rather than evidence the relationship is fake — but the gate's bar
is monotonicity, not just a positive spread, and it wasn't loosened to manufacture a pass.

**Gate 2's failure is a real, specific, and instructive finding — not a bug.** Investigated
directly: Haaland's 2021-22 (pre-Man City) row has `efficiency=0.19` (well above the FW median)
and `usage_share=0.13`, both strong — but `n90s=21.3`, a partial season (his well-documented
injury-interrupted Dortmund year), and `talent_pctl` lands at only the 24th percentile among
423 Bundesliga-era FW rows that season, while his contemporaneous market value sits at the
100th. **The model is conflating "low minutes because you're a fringe player" with "low minutes
because an elite player missed time to injury/rotation"** — it has no feature that
distinguishes these, so a star having an interrupted season reads as ordinary. Antony is not a
sign-flip; he is **structurally unscoreable pre-transfer**: his 2021-22 Ajax season was in the
Eredivisie, which Understat (this panel's shot-signal source) does not cover — the same
selling-league blind spot `REVIEW_verdict.md` already flagged for axis 1 (quantity of data),
now confirmed to propagate into this model specifically, not fixed by it. Neither finding was
smoothed over to pass the gate.

## What this changes, honestly

The July review's bottom line was: *"the sauce is real but not yet an edge... every conversion
test failed honestly."* This build moves that forward on two of four fronts (gates 1 and 4 now
pass, cleanly, where nothing existed to test before) and leaves two open (gate 2's injury/
minutes blind spot, gate 3's near-miss monotonicity). That is real progress, not the full
promotion to "proven" — reporting it as proven would require gate 3 to clear its bar and gate 2
to stop sign-flipping on a marquee case, and neither happened. **Edge PRESENT BUT UNPROVEN**
remains the honest label.

## Addendum — the gate-2 fix was tried, and it made things worse

Tested the first item in the list above directly: added `days_missed_in_season` (point-in-time,
this-season-only injury days, from the raw spell file) alongside the existing trailing-3y
durability feature, retrained, re-gated. **Result: gate 2 got worse, not better** — Haaland's
gap widened from +75.9 to +91.8 (further from the correct sign). Gate 3's spread widened
(+0.118→+0.174, CI even more clearly positive) but its step-monotonicity got worse (55.6%→44.4%
of deciles). Gates 1 and 4 were roughly flat.

**Why the fix backfired, once checked:** `days_missed_in_season` is legitimately negatively
correlated with forward growth across the training set (corr −0.07 on prior seasons) —
players who miss a lot of a season, for *any* reason, tend on average to see flatter or
declining valuations next. That's a real, sensible pattern for the population. Haaland's row
has `days_missed_in_season=99` (about a third of the season) — a large number on the very axis
the model has learned to discount. Adding the feature didn't teach the model "this explains away
his low minutes"; it added a second independently-negative signal on top of the first, because
the model has no way to know his 99 missed days were a one-off in an otherwise-healthy career
rather than the chronic pattern the feature usually flags. **This isn't a fixable-in-five-minutes
problem** — distinguishing "one bad injury season for an elite player" from "an unreliable
player" needs career-shape context (e.g., a multi-season trend), not a single-season count,
and that's a materially bigger feature-engineering job than the one tried here.

**Reverted.** `impact/talent.py` and `data/money/talent_scores.csv` are back to the committed,
gated version (`git diff` clean against HEAD) — shipping a change that measurably regressed the
exact gate it was meant to fix would be the "loosen the gate" failure mode in a different
costume. The negative result is recorded here instead of discarded, per the project's own rule
that a failed hypothesis is a finding, not nothing.

## What would close the gap (not built here — scoped, not started)

1. **A career-shape minutes feature** — a trailing-2-3-season n90s *trend/baseline*, so a dip
   reads as "down from his own normal" rather than an absolute injury-day count. **The simple
   version of this was tried (see addendum above) and made gate 2 worse**, because a raw
   single-season injury-day count is itself negatively correlated with growth across the
   population, and Haaland's 99 missed days looks like the same pattern chronic-injury players
   show. A trend feature is a different, untried idea, not a retry of the same one.
2. **Selling-league coverage** (`shots_selling`, already on disk, 234,800 rows,
   Eredivisie/Portugal/Championship/Brazil) wired into the same panel — the standing fix for
   the Antony-class blind spot, and the review's own highest-value-next-move for axis 3.
3. **Gate 3's monotonicity at finer or coarser granularity** (quintiles instead of deciles, to
   halve the per-bucket noise at this sample size) before concluding the relationship itself is
   flawed rather than under-powered — an honest power question, not yet answered either way.

None of the above is built speculatively here — per the brief, this pass ships what the four
gates could evaluate today and reports exactly where each one landed.

## Bottom line

**The edge moved from "present but unproven" to "present, two of four conversion tests now
pass, and the two that don't have specific, named, fixable causes" — not to "proven."** The
model beats an age-only baseline cleanly (gate 1) and the reformulated gem screen clearly beats
base rate (gate 4, reversing the review's headline negative result), but a single high-profile
sanity check still reads the wrong sign because of an injury-vs-fringe-player confound in the
minutes feature (gate 2), and the cohort-conversion signal, while directionally real and
statistically significant in aggregate, isn't yet monotone enough to call proven (gate 3).
