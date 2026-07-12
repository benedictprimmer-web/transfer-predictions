# MODEL 01 — research (Phase 1)

*Every number below is from a live warehouse query, re-run to produce this doc, 2026-07-12.*

## R1 — target

**Target: age(+league)-residualized forward 2-year Δlog(market value).**

Pipeline: for each (tm_player_id, season) row, `snapshot_date` = season end (June 30 of
start_year+1 — deliberately the season's *end*, not `impact/aging.py`'s Jan-1 midpoint, so the
feature window and the price anchor don't overlap). Anchor MV = nearest `valuations` row within
365 days of snapshot; forward MV = nearest valuation to snapshot+2y within 182 days, **required
to postdate the snapshot** (0 rows dropped by that filter — the tolerance window already
guarantees it, kept as a defensive check). `fwd_growth_raw = log(mv_fwd) - log(mv_anchor)`.

- Anchor MV coverage: **97.6%** of player-seasons.
- Forward MV coverage (of anchor-covered): **72.9%** — the miss is almost entirely 2023-24
  onward, where "+2 years" runs past the valuations freeze (fresh to 2026-02) or close to it.
- **16,842 trainable player-seasons** with both a price-blind feature vector and a future-dated
  target — well above the ≥5,000 go/no-go floor, and denser than the review's headline 445,671
  MV-row count because that figure was raw valuation rows, not player-seasons with a matched
  price-blind feature vector (the actual trainable set for *this* model).
- Age+league OLS baseline on raw growth: **R²=0.288** — age and league genuinely explain a
  quarter of who gets repriced, which is exactly why the target must be residualized on them
  (raising the SEPARABILITY.md concern: an un-residualized model would mostly relearn "young").
  Residual is confirmed orthogonal to age (corr = -1e-13, i.e. exactly zero by OLS construction).
- Season coverage: dense 2014-15 → 2021-22 (~2,000/season), thinning at 2022-23 (1,133), and
  **2023-24 effectively empty (24 rows)** — the same freshness freeze `KNOWN_TRAPS.md` documents.
  2023-24 is diagnostic-only in any split, never a real test fold.

## R2 — price-blind feature panel

One row per (tm_player_id, season), joined via `crosswalk_players.us_player_id→tm_player_id`
(the id join, not `aging.py`'s fuzzy name join — same 76-79% Understat-side ceiling but no
*additional* collision loss on top of it).

| Feature | Coverage | Decision |
|---|---|---|
| `usage_share`, `shot_share`, `efficiency` | 100% | keep — the core signal, by construction (only rows with Understat coverage reach this panel) |
| `age`, `age_sq` | 100% | keep |
| `n90s` (TM minutes, Big-5 comps) | 97.2% | keep |
| `avail_trailing3y` (injury days in trailing 3y as-of snapshot, **not** the leaky career column) | 100% (no-history rows scored 1.0 = assumed fit, flagged) | keep |
| `def_actions_p90` (fbref_defense, tackles+int+blocks+recoveries+aerials) | 53.2% | keep, NaN left as-is |
| `turnover_p90`, `xa_p90`, `prog_actions_p90` (fbref_niche) | 53.0–53.2% | keep, NaN left as-is |
| `position_group` (FW/MF/DF via `impact.aging.POS_GROUP`) | 98.5% | keep, missing → `"UNK"` category |

**Imputation policy: none.** HistGradientBoostingRegressor (the model chosen in `BUILD_PLAN.md`
§2) handles `NaN` natively as a first-class split value — the ~47% missingness on the fbref
features is almost entirely "season < 2018", which the model can and should learn as a signal
about *which era* it's scoring, not something to paper over with a mean-fill. Satisfies the R2
go/no-go floor (≥4 price-blind features clear 50% coverage — four do, at ~53%).

**Deliberately not built:** pooled WOWY as a feature. `impact/wowy.py` needs lineups (thin,
DATA_MAP flags it "pooled per-player-season only") and `BUILD_PLAN.md` §5's R2 table lists it as
optional. Coverage would be materially below the fbref features for a marginal signal already
partially captured by usage_share; not worth the join cost for v1. Same call on
xT/VAEP — deferred per `PROMPT.md`'s explicit instruction (only build if gate 1 or 4 comes back
marginal).

**Position balance** (SEPARABILITY.md's stated concern, re-confirmed on this panel): DF 6,097 /
MF 5,474 / FW 5,019 / unmapped 252. Less forward-skewed than the review's ≥100-career-shots pool
(680 FW vs 215 DF) because this panel counts *any* player-season with matched Understat
coverage, not just career-volume shooters — defenders take fewer shots per season but still
clear the crosswalk. GKs are absent by construction (shots table has no goalkeeper rows).
`position_group` enters as a categorical feature, not a split — a pooled model per `BUILD_PLAN.md`.

## R3 — leakage audit

- **Features are season-S performance, target starts after season S ends** — by construction
  (`snapshot_date` = season end; forward target strictly postdates it, checked and enforced).
  This is not itself leakage: predicting a future price change *from* the season's own on-pitch
  output is the whole point.
- **`avail_trailing3y` was leaky in its raw form** — `ingest/injuries.py`'s own docstring says
  the career `availability` column is "not point-in-time safe." Rebuilt from the raw spell CSV,
  filtered to `end_date <= snapshot_date`, trailing-3y window only. This is the one real leak
  this research phase found and fixed before it reached the model.
- **`contracts.contract_expiration_date` and `wages_fifa`/`market_value*`/`fee*` are excluded
  entirely** — not point-in-time (contracts) or structurally price (the rest). The
  `_assert_price_blind` guard in the scaffold checks feature-name tokens
  (`market_value|mv_|wage|salary|fee|overpay|price`) at fit time; none of the 12 features above
  match, confirmed by running the guard against the real `FEATURES` list.
- **No random K-fold anywhere** — Phase 2 mirrors `money/fees.py::fit_residuals`'s
  expanding-window pattern exactly; this is enforced by construction in `fit_walk_forward`, not
  just a stated intention.

## R4 — the ceiling, confirmed understood

`validate/stage4.py`'s usage→WOWY r=+0.077 rules out per-deal team-impact as a target (near-zero
variance explained). Forward-MV-growth is the right call: 16,842 dense rows vs. the 2,364-row
Stage-4 panel, and "the market re-rated him" is a well-posed, observable outcome in a way
"how much did this signing swing the table" is not at deal granularity.

## Go/no-go

**GO.** (a) 16,842 ≥ 5,000 floor. (b) leakage audit clean (one issue found and fixed:
`avail_trailing3y`). (c) 4 price-blind features (def/turnover/xa/prog) clear 50% coverage, and
the other 8 clear 97%+.
