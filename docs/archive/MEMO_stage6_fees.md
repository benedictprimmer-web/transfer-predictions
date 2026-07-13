# Stage 6 — Transfer fees (what should it have cost?)

**Status: GATE PASSED 2026-07-11.** `money/fees.py` now fits on real Big-5 fees and
both ground-truth deals read the right way.

## What it does
`fit_residuals(df)` regresses `log1p(fee)` on what was knowable before the deal —
`[age, market_value, position, from_league, to_league, season]` — with a
`HistGradientBoostingRegressor`, **out-of-fold** (`cross_val_predict`, cv=5) so no
deal is priced by a model that saw it. Residual `overpay = fee − fee_pred`;
`overpay_pct = overpay / fee_pred`. Positive = paid over the curve.

## Data source (the real work was here)
- The R2 `transfers` table is **thin** — 35k rows, 7.4% disclosed fees, and it
  **doesn't contain Haaland or Antony at all**. Unusable for the gate.
- Switched to worldfootballR **`tm_transfers/big_5_transfers.rds`** (63k rows, real
  Big-5 fee history). Filter to `transfer_type == "Arrivals"` (destination side, no
  double-count) and drop loans.
- Its companion `big5_player_vals.rds` is a **dead end for market value** — it only
  lists start-of-season Big-5 squads, so it can't price mid-window arrivals (Antony's
  MV came out NaN) or non-Big-5 origins (Ajax isn't in it).
- **Fix:** join the full, dated R2 `player_valuations` **as-of just before the
  window** (summer→Jul 15, winter→Jan 15), keyed by the TM id extracted from
  `player_url`. That's the pre-deal value the model *should* see. MV coverage
  82.4% → **6,660 model-ready arrivals** (of 14,191; 6,967 with a disclosed fee).

## GATE (the falsifiable check, in `build()` as asserts)
| Deal | Fee | Model pred | Overpay | Reads |
|---|---|---|---|---|
| Haaland → Man City 2022 | €60m | €76m | **−21%** | underpay ✓ |
| Antony → Man Utd 2022 | €95m | €34m | **+183%** | overpay ✓ |

Both decisive and correct. Biggest sane bargains (fee ≥ €10m): Eriksen→Inter −68%,
Soler→PSG −65%, Zapata→Atalanta −65%. Biggest overpays include Andy Carroll
€41m→€4m pred (the textbook one).

## Caveats (read before trusting a number)
- **`overpay_pct` explodes for sub-€10m fees** where `fee_pred≈0` (a €13m Akpa Akpro
  reads "+3371%"). This is display noise, not model error — headline lists are floored
  at €10m. Even there, a handful of big fees with `pred≈€0` (missing/near-zero MV at
  the as-of date) are unreliable; trust the entries with sane predictions.
- **TM market value is itself informed by fees** (crowd-sourced), so this measures
  "above/below market *consensus*", not true value. Conversation starter, not verdict.
  (See the docstring in `fees.py`.)

## Model validation (real data, not just the 2 gate deals)
`python3 -m money.fees validate`: n=6,660, **Spearman(fee, pred) = 0.845** (the
overpay *ranking* is strong), log-R² 0.678, OOF median |log-err| 0.418.
**Calibration** by predicted-fee decile: well-calibrated at the top (€30m decile
actual/pred = 1.04) but predicts **low at the bottom** (€0.5m decile = 1.80). This
is log-retransform bias — worst for small fees. **Guidance for Stage 8:** trust
`fee_pred` *levels* for ≥€10m deals (≤12% low, and that's the range you'd price a
real target with error bars); below that use overpay *rank*, not the level.

## Integration note — cost ↔ benefit join (for npv.py / Stage 8)
The fee frame keys on **Transfermarkt** spellings; the benefit side (Understat/panel)
keys on Understat. Measured join rates:
- **League:** TM→Understat key map is **100%** clean (all 5 Big-5 leagues).
- **Fee-deal → Understat destination player-season production: 53%** (56.8% for
  attackers/mids). The miss is mostly *structural, not fixable by name-matching*:
  keepers/defenders who don't shoot, signings who didn't play, non-Big-5 origins with
  no prior Understat history. The recoverable slice is the ~16% name-spelling gap
  (same one `validate/ronaldo.py`'s WOWY join hits, ~84% there).
- **Don't** expect to price every transfer — only players with a real Understat
  production signal. For a concrete Arsenal target (Big-5 attacker) the join lands.

## Run
```
python3 -m money.fees          # offline synthetic _check
python3 -m money.fees build    # real fit + gate on big_5_transfers
python3 -m money.fees validate # OOF error + calibration diagnostics
```

## For Stage 7
Per-deal `overpay` is available as `fit_residuals(load_big5_transfers())`. Not
persisted to disk (YAGNI) — call it when NPV needs the fee-vs-value delta.
See [[stage2-3-gate-results]], `HANDOFF.md` §5.2.
