# Stage 5 — age curves: FINDING (doesn't lift the predictor; ships in NPV decay)

*2026-07-11, on corrected data. Runs: `python3 -m impact.aging build` (fit) → `python3 -m validate.stage5_age_gate run` (the gate). Curves in `data/aging/curves.csv`.*

## What was tested
Whether scaling the traveling efficiency by the age-curve ratio `mult(age_to)/mult(age_from)`
lifts the Stage-4 correlation. Standing rule: a refinement must move r or it doesn't ship
**as a predictor adjustment**.

## The fit (well-estimated; minutes-weighted player-FE quadratic)
Peaks: FW 24.5, MF 22.5, DF 24.5 (attacking output; DF/MF are attacking-role aging). Curves
decline sanely (FW: 0.97 at 21 → 1.00 at 25 → 0.79 at 33 → 0.61 at 36). Self-checks pass
(recovers a planted peak, stays flat on a null, absorbs an across-player survivorship confound).

## The gate: one-year age adjustment does NOT lift r
Matched 1,928/2,462 movers (78%) to age+position via the TM unique-name join.

| slice | target | baseline r | age-adjusted r |
|---|---|---|---|
| ALL matched (n=1928) | team-delta | +0.057 [+0.013,+0.102] | +0.057 [+0.014,+0.102] |
| ALL matched (n=1519) | WOWY | +0.084 [+0.034,+0.134] | +0.084 [+0.035,+0.136] |
| YOUNG <23 (n=508) | team-delta | +0.079 | +0.077 |
| YOUNG <23 (n=386) | WOWY | +0.136 | +0.141 |
| OLD ≥30 (n=235) | team-delta | +0.023 | +0.026 |
| OLD ≥30 (n=178) | WOWY | +0.100 | +0.101 |

All deltas ≤ ±0.005 — noise, even on the young/old tails where the ratio departs most from 1.

## Why (this is the honest mechanism, not a shrug)
A single transfer is a **one-year** age step, so the ratio sits in ~[0.93, 1.02]. Multiplying
efficiency_from by a near-uniform ~1.0 barely reorders the movers, and the gate is a **rank**
(Spearman) correlation — so ranks are essentially unchanged. Age over one year is a small nudge
to a quantity that already varies a lot player-to-player.

## Verdict — different from league strength
- **NOT applied as a Stage-4 predictor adjustment** (fails the gate, same rule).
- **DOES ship in the NPV decay layer (Stage 7).** That is age curves' actual job (MODELS.md §3):
  the benefit stream runs 3-5 contract years, and the decay **compounds** over that horizon
  (a 30yo at 0.79 → 33yo territory is a large multi-year haircut, unlike the ~2% one-year step).
  The gate tests the wrong horizon for age; the fit is load-bearing where it's actually used.

So: league strength = descriptive-only (didn't earn its place anywhere in the predictor).
Age curves = not in the predictor rank, but **required** for NPV — keep and wire into Stage 7.
