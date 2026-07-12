# Stage 4 — the make-or-break gate: results

*2026-07-11. Run: `python3 -m validate.stage4 run`. Panel: `data/stage4/panel.csv` (2,462 Big-5→Big-5 movers, 2014-15→2023-24, built by `validate/stage4_panel.py`).*

> **RE-RUN on corrected data (2026-07-11, post `h_a`→`home_away` fix).** The pre-fix panel scrambled every 2022+ shot to the away team; numbers below are recomputed on clean `shots.pkl`. Headline survives: WOWY r went **up** (+0.052→+0.077), team-delta softened slightly (+0.083→+0.064), both CIs still exclude zero. Old (corrupted) figures kept in the second table for the record.

## Design

Predictor is **unfitted** (pure mechanism, so no leakage possible):
`predicted_gain = usage_share_from × (efficiency_from − team_to_eff_before)` — efficiency
travels, origin usage share as the v0 volume heuristic, destination team's prior-season
value-per-action as the bar to clear.

Two realized targets per mover: within-season **WOWY** at the destination, and the
**before/after team npxGD/90 delta** (the season-over-season design that catches system
effects on/off minutes can't — the "Rodri problem").

## Results (corrected data)

| Target | Spearman r | boot 95% CI | n | verdict |
|---|---|---|---|---|
| WOWY at destination (≥450 on-min) | **+0.077** | [+0.030, +0.125] | 1,614 | **PASS** |
| Team npxGD/90 delta | **+0.064** | [+0.020, +0.107] | 2,164 | **PASS** |
| Era 2015-2018 (WOWY/delta target) | +0.089 | [+0.021, +0.148] | 1,003 | replicates |
| Era 2019-2024 (WOWY/delta target) | +0.043 | [−0.016, +0.100] | 1,161 | weaker (this is the era the bug lived in — now honest) |
| Partial slope (controls: mean reversion, churn) | +4.73 | [−0.39, +9.58] | 2,164 | inconclusive (CI spans 0) |

### Old (pre-fix, corrupted 2022+) — for the record only
| Target | Spearman r | boot 95% CI | n |
|---|---|---|---|
| Team npxGD/90 delta | +0.083 | [+0.042, +0.123] | 2,064 |
| WOWY at destination | +0.052 | [+0.002, +0.100] | 1,509 |

## Honest interpretation

1. **The gate passes as written**: positive out-of-sample correlation, error bars excluding
   zero, stable across time. The mechanistic channel carries real predictive content.
2. **The signal is small** (r ≈ 0.08). The crudest possible predictor — no league-strength
   adjustment, no age, no role-overlap reallocation — explains a sliver of variance in an
   outcome that is mostly squad churn, tactics, and luck. Nobody prices a deal off r=0.08;
   the system's value must come from the *stack* (mechanism + money model + market residual).
3. **Effect size is not yet pinned down**: with mean-reversion and churn controls, the slope's
   CI spans zero. The correlation survives controls in sign but not in magnitude.
4. **Case echo**: Ronaldo→United 2021 predicted +0.006 (his efficiency just cleared United's
   bar — the stage-2 finding), realized −0.248 WOWY / −0.427 team delta. The mechanism
   under-predicts systemic damage; that residual is precisely what stages 5+ (and the style
   clusters) get tested against.

## What this authorizes

Proceed to Stage 5 (league strength + age curves — both plausibly *increase* the correlation,
since cross-league efficiency is currently unadjusted), then fees and money. Re-run this gate
after each refinement: **each addition must move r or it doesn't ship** — that's the standing
test against over-engineering. If refinements can't lift r meaningfully, the valuation leans
on the fee-residual + revenue layers, and the usage engine stays a sanity-checker, honestly
labelled as such.
