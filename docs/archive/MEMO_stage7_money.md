# Stage 7–8 — money layer + interface (COMPLETE)

*2026-07-11, on corrected data. `money/{points,revenue,npv,price}.py`, `validate/benefit_gate.py`.
All 11 module self-checks pass (incl. Agent B's `money/fees.py`).*

## 7a — xGD → points (`money/points.py`)
Points and npxGD both reconstructed from Understat shots (identical team names, **no crosswalk**).
An OwnGoal row's `team_shot` is the CONCEDING team (verified — reproduces the real 2021-22 EPL
table: **Man City 93 pts / GF 99 / GA 26**, exact). OLS `ppg ~ a + b·npxGD_pg`, 1,250 team-seasons:
intercept 1.373, slope **0.721**, **R²=0.797**. +10 season npxGD ≈ **+7.2 points**. Cached `data/money/points_fit.csv`.

## 7b — points → revenue, PROBABILISTIC rank (`money/revenue.py`)
Expected points don't pin final rank — the season realizes with noise (SD **7.31 pts**, from the
points-fit residual) and rank depends on the other 19 clubs (drawn from the 220-team-season EPL
pool). `RevenueModel` freezes the draws (common random numbers) so `expected_revenue(points)` is a
smooth, reproducible function; revenue(rank) = domestic central payment + expected European prize.
- **CL cliff:** rank 4 £179.9m vs rank 5 £152.1m = **£28m**.
- **Marginal £/point** peaks at **£2.1m near the CL boundary (~65 pts)**, and is **non-zero at the
  top** (£0.32m at 90 pts — title/CL *probability*). This replaced the earlier deterministic-rank
  model, whose flat rank-1 plateau priced a top team's marginal point at **£0** (degeneracy fixed).

## Benefit hardening — gated, then calibrated (`validate/benefit_gate.py`)
The benefit form is `usage_share × (efficiency − BAR)`. Tested three bars through the Stage-4 gate:
| bar | team-delta r | verdict |
|---|---|---|
| team MEAN eff (V0) | +0.064 [+0.020,+0.107] | **retained** |
| marginal (bottom-⅓ usage) | +0.052 | rejected (predicts worse) |
| replacement (25th pct) | +0.011 | rejected |
The "signings displace the fringe" intuition does **not** hold — the mean bar wins. Then the raw
`actions × eff-gap` was overstating benefit (Lewandowski +20 season npxGD → +14 pts, absurd) by
ignoring that usage is **zero-sum**. Fix: **calibrate** the validated proxy to realized team-npxGD
via the panel regression — slope **9.25 [3.86, 14.25]** (delta_team_xgd90 per unit pg). Now an elite
signing adds ~**3–6 season npxGD → ~2–4 points** (sane). Cached `data/money/benefit_calibration.csv`;
the slope's CI is the dominant, honest NPV error bar (carries the r≈0.08 uncertainty).

## 7c — NPV (`money/npv.py`)
cost = fee/contract-years + wage; benefit_t = `cal_slope × usage_share × (age-decayed eff − team_eff)
× 38 × 0.721 × £/point`; NPV = Σ discounted(benefit − cost)@8% + age-decayed residual resale.
Band = pessimistic (low calibration slope + high wage) … optimistic (reverse). Self-checks: bargain
NPV>0, dud<0, benefit decays with age, npxGD/yr in a sane range, band ordered.

## Stage 8 — the interface (`money/price.py`)
`price_transfer(player=…, to_team=…, fee_gbp=…, market_value_eur_m=…, age=…, position=…)` →
`PriceVerdict` (NPV central + band, per-year breakdown, component values, **quality flags** naming
every modelled/low-confidence input). Player lookup (exact → normalized-contains), destination
defaults to the latest **complete** season (partials flagged), wage modelled if not given. CLI:
```
python3 -m money.price "Alexander Isak" --to Arsenal --fee 70 --mv 75 --age 24 --pos FW
```
Worked: Isak → title-winning Arsenal (89 pts) NPV **−£60m [−89,−41]**, auto-flagged *"club near top
of table — marginal point worth little"* — the probabilistic-rank insight, made legible.

## Honest limitations (documented, not hidden)
- Benefit rests on the Stage-4 channel (r≈0.08) — directionally real, **wide by design**; treat NPV
  sign near zero as undetermined. This is why NPVs read negative for big-fee/high-wage deals on pure
  table revenue: the model prices *on-pitch table value only*, not brand/cups/squad-risk.
- Wages grade-D modelled (±55%). Revenue constants EPL 2023/24; omit facility fees; flat CL EV.
- EPL-only revenue (Arsenal is the first club); other leagues need their central deal + CL slots.
