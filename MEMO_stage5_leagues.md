# Stage 5 — league strength: FINDING (does not ship)

*2026-07-11, on corrected data (post `h_a`→`home_away` fix). Runs: `python3 -m impact.leagues run` (fit) → `python3 -m validate.stage5_gate` (the gate). Fit in `data/league_strength.csv`.*

## What was tested
Whether discounting a player's per-action output by the strength of his **origin league**
lifts the Stage-4 correlation. The standing over-engineering rule: *a refinement must move r
or it doesn't ship.*

## The fit (well-estimated, EPL = reference)
| league | multiplier | 95% CI | movers |
|---|---|---|---|
| ESP-La Liga | 1.107 | [1.065, 1.149] | 212 |
| GER-Bundesliga | 1.072 | [1.021, 1.133] | 172 |
| FRA-Ligue 1 | 1.071 | [1.029, 1.116] | 250 |
| ENG-Premier League | 1.000 | (ref) | 279 |
| ITA-Serie A | 1.000 | [0.965, 1.040] | 225 |
| RUS-Premier League | 0.966 | [0.890, 1.047] | 69 |

Reading: EPL is the *hardest* league to sustain value-per-action in — output earned elsewhere
discounts on a move to the EPL. Ordering matches ClubElo (independent sanity check). Tight CIs.
This fit is sound; it is *identical* to the pre-fix provisional fit (corruption didn't move it).

## The gate: league adjustment does NOT lift r
| slice | target | baseline r | league-adjusted r | verdict |
|---|---|---|---|---|
| ALL movers (n=2164) | team-delta | +0.064 [+0.020,+0.107] | +0.064 [+0.021,+0.107] | no change |
| ALL movers (n=1614) | WOWY | +0.077 [+0.030,+0.125] | +0.074 [+0.026,+0.123] | slightly worse |
| cross-league (n=872) | team-delta | +0.088 [+0.020,+0.155] | +0.090 [+0.022,+0.157] | +0.002 (noise) |
| cross-league (n=635) | WOWY | +0.112 [+0.032,+0.192] | +0.104 [+0.024,+0.186] | worse |

## Verdict
**League strength does not ship as a predictor multiplier.** Even on cross-league movers —
where it should matter most — it moves r by +0.002 on one target and *down* on the other.
That is noise. The multiplier is a well-estimated quantity that carries almost no marginal
predictive signal once usage and efficiency are already known.

Same discipline that recorded the Stage-2 usage gate as a finding rather than loosening it.
This is the over-engineering firewall doing its job: the model refusing to bolt on a plausible
knob that doesn't earn its place.

## What this changes downstream
- `data/league_strength.csv` stays as a **descriptive** artifact (and may still matter for
  fee/market comparisons across leagues), but is **not** applied to the usage predictor.
- Next refinement to test through the same gate: **age curves** (`impact/aging.py`) for NPV
  decay. Same rule — must move r (for age-relevant movers) or it's descriptive-only.
