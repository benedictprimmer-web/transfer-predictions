# Stage 2/3 — data readiness & gate results

*Produced by the parallel ingestion harness, 2026-07-11. All numbers below are from real builds, not synthetic checks.*

---

## 1. Data readiness table

| Source | Module | Schema (tidy) | Coverage | Rows | Quality |
|---|---|---|---|---|---|
| Understat shots (xG) | `ingest/understat.py` | game_id, team_shot, minute, xg, player, player_assisted, situation, date | Big-5 + RFPL, 2014-15→2023-24 complete, 2024-25 ~half | **539,971 shots** | A- |
| Transfermarkt minutes/lineups | `ingest/transfermarkt.py` | game_id, team, player, is_starter, minutes (+league, season, date) | Big-5 **2012-13→2025-26, every season** | 726,823 | A- |
| Transfermarkt transfers/values | same | fees.py FEATURES + fee, fee_disclosed | all TM comps | 35,139 transfers | B (fees thin: **7.4% disclosed**) |
| FBref advanced **snapshot** | `ingest/fbref_snapshot.py` | league, season, team, player, pos, n90s, dispossessed, miscontrols | Big-5 **2017-18→2021-22** (2022-23 rows are zeros — excluded) | 16,139 player-seasons | B+ |
| StatsBomb events | `ingest/statsbomb.py` | per-90 turnovers + self-keyed lineups | EPL 2015-16; BUN 2015-16, 2023-24 | 1,292 player-seasons | A quality / C coverage |
| Club Elo (mirror) | `ingest/strength.py` | club, country, date, elo | Big-5 + NED/POR, **2023-03→2026-01 only** | 578,762 | B+ (shallow history) |
| Wages | `ingest/wages.py` | estimate_wage() → (value, lo, hi, source) | model, not data | — | **D — flagged everywhere** |
| **Crosswalk** Understat↔TM | `ingest/crosswalk.py` | understat_game_id ↔ tm_game_id + confidence | 55 league-seasons | **18,917/18,917 = 100.0% matched** | A |

All ten module `_check()`s pass offline. `data/coverage.csv` now carries `has_xg` + `has_shot_minutes` + `has_lineup_minutes` per league-season (55 Big-5 rows all True). Total cache ~450MB.

**The unexpected win:** `worldfootballR_data` froze FBref's advanced tables before Opta's Jan-2025 takedown — that snapshot restored **dispossessed + miscontrols** (the spec's full usage definition) for Big-5 2017-18→2021-22, which nothing live provides anymore.

## 2. Gate results (real data, definitions never loosened)

### Stage 2 — usage & efficiency (`impact/usage.py`, run: `python3 -m impact.usage ronaldo`)
- **Gate 1 — Ronaldo 2021-22 highest shot share: PASS.** 21.3% npxG-basis (107 shots), top of squad; Bruno 17.3%.
- **Gate 2 — efficiency below displaced: FAIL under every principled definition.**
  npxG/action 0.146 vs displaced-top-6 0.095 · with turnovers 0.090 vs 0.051 · forwards-only displaced set: 0.146 vs 0.128 and 0.090 vs 0.060. Consistent across all four: **his per-action output was fine — above the players he displaced.**
- **Interpretation, not exoneration:** the spec's expected mechanism (bad per-action efficiency) is empirically wrong for this case. Ronaldo's damage was systemic — pressing, tempo, off-ball — which a per-action metric cannot see. This is a *finding about where the signal lives*, and it sharpens Stage 4's question: how much of team impact does the usage×efficiency channel actually carry?

### Stage 3 — WOWY on real data (`validate/ronaldo.py run`, `validate/null_test.py run`)
- **Ronaldo WOWY negative: PASS.** −0.248/90 shrunk (raw −0.866). United +0.891 xGD/90 without him, +0.025 with him. Combined with Stage 2: **individually productive, collectively negative — the exact signature the system exists to catch, caught by the layer built to catch it.**
- **Null test: honest FAIL on spread.** Shuffled identities: signed mean ≈ 0 (**no bias**), but mean |wowy| 0.224 vs real 0.254 → **~80% of one-season point-estimate spread is game variance**. Ronaldo's −0.248 sits at the **18th percentile** of the matched null — directionally right, not individually significant on one season.

## 3. What the null result means (and doesn't)

It does **not** void the layer: the estimator is unbiased, the synthetic planted-signal test collapses correctly, and ~20% of variance is real signal. It **does** mean single-season WOWY point estimates must never be shown without intervals, and Stage 4 must use the spec's own mitigations: pool across seasons, shrink toward team mean, and evaluate the usage→WOWY correlation across many players where noise averages out. WOWY was always the validator, "too noisy to price anyone" — the data just quantified exactly how noisy.

## 4. Remaining gaps

| Gap | Impact | Least-bad path |
|---|---|---|
| Turnovers outside 2017-22 | full usage metric limited to that window | attacking-only usage elsewhere, flagged; StatsBomb calibration seasons |
| Disclosed fees only 7.4% (2.6k) | fee model training set thin | `worldfootballR_data` `tm_transfers` (richer fee history) — small follow-up ingest |
| Elo history starts 2023-03 | league-strength prior shallow | fit league FE from movers (MODELS.md §2, the primary method anyway); ClubElo full history via residential pull if needed |
| Wages | grade D, model only | ±30%+ intervals, flagged `modelled`, Capology snapshot slot ready |
| Player-name join 92.4% exact (EPL 21-22) | cross-source player joins lose ~8% | alias/difflib pass when Stage 4 needs it |

## 5. Go / no-go

**GO for Stage 4** (usage model predicts WOWY out-of-sample — the make-or-break gate), with two binding conditions from the evidence above:
1. WOWY targets must be pooled (player-stint level, multi-season) with intervals; single-season points are 80% noise.
2. The Stage-2 Gate-2 finding stands as recorded: the usage×efficiency channel alone did not flag Ronaldo. If Stage 4's correlation comes out near zero, the honest conclusion the spec pre-authorized applies: *stop and say so rather than building a UI on top of noise.*

Stage 5+ (league strength, age curves, fees, money) can proceed in parallel on their own data, which is ready.
