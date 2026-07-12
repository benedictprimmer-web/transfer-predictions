# MEMO — How to weigh future transfers & wages (the discount decision)

**Question:** how much is £1 of resale fee received, or wage paid, in year 3 vs year 1 worth?
**Answer shipped:** net discount **5%/yr** on future football cashflows (was a flat 8%). See
`money/npv.py:DISCOUNT`.

## The mistake the old 8% made

The model conflated two different forces into one knob, and it double-penalised the future:

1. **Time value of money** — a future £ is worth less now (opportunity cost + risk). Pulls the
   rate UP.
2. **Football inflation** — future resale, wages and TV revenue are paid in *inflated* future
   pounds (the sector index from `INFLATION_audit_prompt.md`: elite ~8–10%/yr long-run). Pulls
   the effective rate DOWN.

The old model discounted the residual resale at 8% **but valued it at today's market value** — it
took the hit for time but never took the credit for the market inflating underneath it. Same for
wages: discounted at 8% but held flat, when real wages grow ~5%/yr. Net result: the future was
penalised twice. The residual (a large line item) was the biggest victim.

## The number

The rate that matters is **nominal discount − football growth**, applied to today's-pound cashflows:

| Component | Value | Source |
|---|---|---|
| Nominal risk-free (UK 10y gilt) | ~4.4% | July 2026, BoE base 4.00% |
| Football risk premium | ~+4.5% | clubs loss-making, revenue volatile — Deloitte notes DCF is *flawed* here, so a fat premium |
| **Nominal club discount r_nom** | **~9%** | |
| Football value growth g (fee/wage) | **~5%** | **MEASURED** (was a 4% guess): the hedonic fee index runs **5.3%/yr in the 2017–2022 regime, 6.3%/yr over 1996–2022** (`INFLATION_FINDINGS.md`, `money.inflation`). Rounded down to 5% for forward PSR/rate headwinds. |
| **Net discount r_net = r_nom − g** | **≈ 4%** | shipped default (was 5% under the g=4% guess) |

One net rate (not three) is deliberate: benefit (revenue, cooler broadcast growth → net ~6%),
resale (fee growth → net ~4%) and wages (net ~4%) differ, but the spread sits inside the model's
±factor-of-2 calibration band. Splitting it would be false precision. `ponytail: one knob.`

## Sensitivity (use these, not a point estimate)

| r_net | reading | 5y residual factor | when to use |
|---|---|---|---|
| **3%** | football inflation ≈ discount; future barely discounted | 0.86× | boom market, elite asset, buyer flush |
| **4%** | **shipped default** (g = measured 5% ≈ recent-regime fee CAGR) | 0.82× | base case |
| **5%** | prior default (g = 4% guess) | 0.78× | conservative-g read |
| **8%** | old behaviour; football-inflation-blind, pure time-value | 0.68× | bear market / small club / conservative board |

## Measured impact (worked examples, `python3 -m money.npv run`)

Kane→Arsenal residual PV **£31.6m → £36.4m (+15%)** at 5% vs 8% — the resale line was the most
under-weighted, exactly as predicted. Net NPV barely moves here because Kane's annual stream is
small and negative (lower discount also makes his later-year wages weigh more — correct). Self-check
passes; the uncertainty band widens slightly (lower discount amplifies both tails — correct).

## Caveats / what this does NOT fix

- **Fee timing.** The fee is paid in full at t=0 but the model amortises it (fee/years) and
  discounts the slices — that *understates* its PV. Kept because it matches football/FFP accounting
  ("book NPV"), but a cash-NPV would charge the whole fee at t=0. Flagged, not changed.
- g is now **measured** (2026-07-12): the `money.inflation` hedonic year-FE index gives fee CAGR
  5.3%/yr (2017–2022) and 6.3%/yr (1996–2022); g set to 5% (forward-conservative), so r_net 5%→4%.
  A subtlety the measurement exposed: almost all headline fee inflation *is* market-value inflation
  (the fee-vs-MV *premium* index is ~flat since 2010) — so g is really "how fast football money
  inflates", which is what belongs in the discount. See `INFLATION_FINDINGS.md`.
- Non-stationary: g was ~10% pre-2017, negative in 2020–21. A single r_net is a 5-year-horizon
  average, not a claim the rate is constant.
