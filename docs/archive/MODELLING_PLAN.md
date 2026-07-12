# Data-Model Plan

Reconciles the two philosophies on disk — Estate B's supervised **fee/market-value**
prompt and this repo's mechanistic **usage-efficiency** system (`MODELS.md`) — against the
**canonical table we just built** (`data/merged/transfers_canonical.parquet`, 124,183 rows)
and the shipped fee ranker (`data/money/fee_ranker.csv`). Every number here came from a query
run against the real files, not an estimate.

## 0. The one rule and the two layers

Fit a model only where something real was observed. **Fees happened** → the fee model has
ground truth. "Good signing" never happened → the impact layer is a *sanity check*, never the
headline.

| Layer | Status | Model | Ground truth |
|---|---|---|---|
| **Fee-vs-market residual** | PRIMARY (shippable) | LightGBM on `log1p(fee)` | the fee that was paid |
| **Market-value** | supporting | LightGBM on `log1p(MV)` | crowd-sourced MV (biased, lagged) |
| **Impact / NPV** | SECONDARY (sanity) | existing `money.price`, r≈0.08 calibrated, wide band | nothing — inferred |

Read the fee residual as *"paid over/under prior market **consensus**,"* not "vs truth."

---

## 1. Models to build

### A. Fee model (LightGBM) — the upgrade from the shipped HistGBR ranker

- **Trainable set (verified):** `fee_eur>0 AND NOT fee_suspect AND market_value_eur AND player_age` → **16,233 rows**, seasons 2004–2026. By bucket: **≤2018 = 12,191 · 2019–20 = 2,159 · 2021–22 = 1,370 · 2023+ = 513**.
- **Target:** `y = log1p(fee_eur)`; report back-transformed EUR (`expm1`).
- **Baseline to beat (verified):** naive `fee = market_value_eur` → **MAE €2.94M, RMSE €6.13M, log1p-MAE 0.776, Spearman 0.744**. A global multiplier doesn't help (fees run ~0.82× MV). LightGBM must beat MAE €2.94M / log1p-MAE 0.776; the ranker already beats it on *ordering* (ρ 0.787) — the regressor adds calibrated EUR output.
- **Config:** `LGBMRegressor(objective="regression_l1", n_estimators=1500, learning_rate=0.02, num_leaves=31, min_child_samples=40, subsample=0.8, colsample_bytree=0.7, reg_lambda=1.0)`, native categoricals (`pos_group, window, transfer_type, to/from_league, to/from_country, player_nation`), NaN passed through. **XGBoost** (`reg:absoluteerror`, hist, depth 6) as cross-check on identical folds — >10% MAE disagreement on any fold = unstable, investigate before shipping.

### B. Market-value model — a genuine second deliverable

- **Universe (verified):** every valuation observation with ≥2 prior points in the same player's series → **445,671 usable rows** (of 507,815; 31,507 players; 2000–2026).
- **Target:** `log1p(market_value_in_eur)` from `[age, mv_prior_last, mv_prior_max, mv_slope_1y, mv_n_prior, months_since_last, club comp, optional strict-prior perf]`.
- **Why:** replaces the stale-snapshot fallback for the **433 trainable fee rows without point-in-time MV**, and prices any future deal missing a fresh valuation.

### C. Feature layer — build BOTH tiers, then measure the lift

Nested universes (real sizes on the trainable set):

- **Broad model** — MV-trajectory + roster metadata (age, pos_group, from/to league/country, window, type). Coverage **~89.7%**. No FBref/Understat dependency → degrades gracefully to pre-2010 and uncovered leagues. **The production backbone.**
- **Performance-rich model** — adds FBref prior-season features. Hard ceiling **7,692 rows (50.9%)**; the xG-family (xG/npxG/xAG) exists for only **~2,650** (FBref carries xG only from 2018+, and 0% for 2023+ — the FBref pipeline is dead). Big-5, recent subset.
- **The lift experiment (run, don't assume):** fit broad-only vs broad+perf on the **same 7,692 perf-rich rows**; report held-out MAE delta. Material lift → two-tier ensemble with a `feature_tier` flag; marginal → ship broad-only and drop the FBref join (7,692 rows / 15 features risks overfit).

Feature catalog with verified coverage and strict-before rules is in the appendix table below.

### D. Impact / NPV — unchanged, stays the sanity check

`money.price` already assembles usage→age→points→revenue→NPV with the r≈0.08 calibration and a
wide band by design. **Do not promote it to a headline number.** Its job: catch a deal the fee
model likes but the mechanics don't (and be honest about the one neither catches — Ronaldo 2021,
individually efficient, WOWY −0.248).

---

## 2. Leakage protocol — 9 checks, one live defect

Ship `validate/leakage_audit.py::audit(frame) -> list[str]` (empty = pass), asserted in every
frame-builder's `--check`:

| # | Check | Fail condition |
|---|---|---|
| L1 | No future performance | any `perf_season >= transfer_season` as a feature |
| L2 | No post-move MV | joined valuation `date >= transfer cutoff` (assert, don't trust `direction="backward"`) |
| L3 | Point-in-time MV honesty | `mv_is_point_in_time=False` (46.6% of canonical MV) treated as dated — must carry the flag |
| L4 | No destination-only features | any feature from the *post*-move team-season (key on `season_from`, never `season_to`) |
| L5 | Encoders fit on train only | `.fit()` sees a test-fold row |
| **L6** | **Season-based folds** | **random KFold on time-ordered data — `money/fees.py::fit_residuals` uses `cv=5` (random). THIS IS THE ONE LIVE DEFECT.** |
| L7 | Target not in features | `fee/overpay/wowy` leaks into X |
| L8 | No same-deal across folds | dedup on `(player, season, to_club)` before CV |
| L9 | Contract/wage not future-dated | never source from a latest-state snapshot |

**L6 is the top fix.** Market inflation leaks through random folds; `MODELS.md §4` demands
time-aware splits. Tension to resolve when fixing: a pure `TimeSeriesSplit` leaves the earliest
season with no OOF prediction — use expanding-window forward-chaining and report that the first
fold is unscored, rather than silently keeping the leaky full-coverage KFold.

---

## 3. Validation & backtest

**Season folds (expanding window, keyed on `season` int):**
train ≤2018 · validate 2019–20 (model selection, thresholds) · test 2021–22 (report once; Haaland/Antony live here) · **2023+ = diagnostic bucket only** (513 rows, no perf — thin, wide interval, never the headline).

**The test that actually matters — "does the fee residual predict anything real?"**
A good fee-fit is *not* self-validating (consensus MV partly *is* the fee). Independent test using
strictly-later data we already have (`validate/fee_residual_forward.py`, new):

> Form two cohorts from train/val-era deals (established value, fee & MV ≥ €10m, not implausible):
> **bargain** (overpay_pct bottom tercile) vs **overpay** (top tercile). Follow each player forward,
> measure **2-yr Δlog(market_value)** from the dated valuation series.
> **Metric:** difference in median forward Δlog-MV, bootstrap 95% CI on the difference.
> **Pass = CI excludes zero AND bargains > overpays.** Report ρ(overpay_pct, forward-Δlog-MV) too.

MV growth is the right target: later, independent of the fee paid, and what a bargain *should*
produce. The benefit-side backtest (`validate/npv_backtest.py`) already exists and is honestly
mixed (generalizes late→early ρ+0.086 CI[+0.032,+0.142]; early→late straddles zero) — report both,
claim neither as clean.

---

## 4. Uncertainty — no point estimate without a band

| Quantity | Interval | Current |
|---|---|---|
| **Fee residual** | percentile bootstrap of OOF `overpay_pct` → per-row `overpay_lo/hi` | **not on the board yet — ADD** |
| Benefit calibration | 2000× bootstrap OLS slope | 9.25 [3.86, 14.25] |
| Wage estimate | grade-D modelled band | flagged per verdict |
| NPV | `npv_band` (low-cal×high-wage … reverse) | `[lo … hi]` per verdict |

The only gap is the fee residual band — add `overpay_lo/hi` so the PRIMARY signal obeys the rule the SECONDARY already does.

---

## 5. Product spec — the board contract

One row per disclosed, non-suspect deal; CSV columns are the stable interface:
```
player, season, to_club, from_club, from_league, to_league, age,
market_value, fee_eur, fee_pred_eur, overpay_pct,        # PRIMARY signal
overpay_lo, overpay_hi,                                    # ADD — §4 band
mv_point_in_time, date_source, fee_vs_mv_implausible       # quality flags (present)
```
**Disclaimers that ride with the board:** (1) residual = deviation from *consensus, not truth*;
(2) crowd-sourced MV lags breakouts → young breakout buys read as overpays → headline lists
restrict to fee & MV ≥ €10m; (3) when `money.price` NPV is shown, its band + `r≈0.08` flag ride with it.

---

## 6. Definition of done + coverage ceilings

**Ship-blockers (all green to ship):**
1. `ingest.merge --check`, `money.fees`, `money.npv`, `money.price`, every `validate/*` `_check` pass.
2. `leakage_audit.audit` empty on both frames — **including L6 fixed** (currently RED, the sole outstanding blocker).
3. Fee gate passes (Haaland underpay, Antony overpay).
4. LightGBM pooled MAE < €2.94M and log1p-MAE < 0.776 (beat baseline); LGBM vs XGB within 10%/fold.
5. §3 forward-MV cohort test runs, CI reported (a disclosed fail is done; a missing test is not).
6. Every published number carries a band, incl. `overpay_lo/hi`; out-of-support deals abstain.

**Coverage (accepted limits, disclosed — not blockers):** disclosed fee 19.7% · any MV 57.3% (PIT 53.4% / 94.2% of the board) · exact date 9.6% (proxy flagged) · crosswalk→FBref 89.2% of trainable / perf-rich 50.9% / xG-rich ~17%.

**Three data gaps (from Stage 9), classified:** exact-dates-at-scale = accepted (annual resolution is fine); recent Big-5 fees = accepted, disclosed (2023+ holdout is thin); point-in-time contracts/wages = accepted **for the sanity layer only** — would be a blocker if NPV were ever the headline, which is why it isn't.

---

## 7. Build sequence

1. **Fix L6** — swap `fit_residuals`' random KFold for expanding-window forward-chaining; re-ship the board with honest (lower) ρ + add `overpay_lo/hi`.
2. `build/model_frame.py` — one builder producing the fee frame (16,233) and MV frame (445,671) from the queries in the appendix; assert counts; run `leakage_audit`.
3. `train_fee_model.py` — LightGBM + XGBoost cross-check, season folds, `results.json`, per-season table, SHAP top-15.
4. `train_mv_model.py` — MV model; wire as the MV fallback.
5. `validate/fee_residual_forward.py` — the forward-MV cohort test.
6. `MODEL_REPORT.md` — per-season metrics, SHAP, honest coverage/selection-bias write-up.

---

## Appendix — leakage-safe feature catalog (verified coverage on the 16,233 trainable rows)

| Feature | Source | Join key | Coverage | Strict-before rule |
|---|---|---|---|---|
| market_value_eur | canonical | — | 100% (filter) | point-in-time; `mv_is_point_in_time` on 97% |
| player_age, pos_group, window | canonical | — | 100% | as-of / static |
| transfer_type | canonical | — | 96.8% | static |
| to/from_is_top5 | canonical | — | 72.8% / 57.1% | static (null→own category) |
| to/from_league, to/from_country | canonical | — | 55–82% | static (null→"unknown") |
| mv_prior_last, mv_prior_max, mv_n_prior, mv_slope_1y | valuations (507k) | player_id + date | **≥2 priors 91.7%** | `date < cutoff − 7d` |
| minutes, goals/90, assists, min%_of_team | perf link | fbref_id + season | 50.9% strict-prior | `perf_season < transfer_season` |
| xG/90, npxG, xAG, npxG/shot | perf | fbref_id + season | ~17.5% (2018+ only) | strict-prior; emit `has_xg` flag |
| prog_passes, prog_carries, tkl+int, pass% | perf | fbref_id + season | ~17.5% | strict-prior |
| xg_overperformance (finishing) | Understat shots | **name + season** | ~75% (2015+) | `shots.season < transfer.season`; drop ambiguous names |

**ID-bridge gates (precision-first):** dedup crosswalk to 1:1 before joining (126 TM ids map to >1 fbref_id → +194 phantom rows); accept the Understat name-join only where `(norm_name, season)` is unique (drop ~2%, never fuzzy-match); for proxy-dated transfers additionally require `mv.date < season-start` so no post-signing valuation leaks.
