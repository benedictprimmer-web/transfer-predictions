# HANDOFF — Transfer Predictions, state & next steps

*Written 2026-07-11 for a fresh chat. Read this, then `MEMORY.md` (auto-loaded), then the memo files it points to. Everything below is real — computed from data on disk, not planned.*

**Update 2026-07-13 (this branch, `agent/data-audit-pr`, PR #1):** this branch
has since merged `main` and added a Phase 0 data audit, V1 modelling
contract, and a scoped V2 pass (Mustermann evidence layer, full-data
descriptive analysis, one gated fee-model prototype comparison). Start with
`docs/reconciliation.md` (what changed and what was reconciled),
`docs/v2-results.md` (V2 verdict), and §9 below before trusting any number
in this file against the current branch — several (notably the NPV board
count) were superseded. `main` itself is unchanged from what's described
below.

---

## 0. What this is
A football transfer valuation system. Cost = amortised fee + wages; benefit = team winning more → revenue; NPV is the verdict. Core engine: **usage is zero-sum** — `team_output = Σ(usage_i × efficiency_i)`; a signing helps only if his efficiency beats the weighted efficiency of the usage he displaces. WOWY (team xGD on/off pitch) is the independent validator. First club: Arsenal. Acceptance case: Man Utd 2021-22 Ronaldo (individually good, collectively negative). Full spec in `SPEC.md`, `MODELS.md`, `PROMPT.md`.

## 1. THE PIVOT (most important context)
`DATA.md` planned FBref via soccerdata. **FBref is dead**: Opta pulled its feed Jan 2025 (no xG/turnovers on the site anymore) AND it 403s this environment's datacenter IP (egress is a Slovenian host, not residential). We pivoted — see `DATA_SOURCES.md`. New stack, **all reachable from here, no user-in-the-loop**:
- **Understat** shot xG via `worldfootballR_data` GitHub `.rds` dumps → `ingest/understat.py` (539,971 shots, Big-5+RFPL 2014-24)
- **Transfermarkt** via public R2 CSV mirror → `ingest/transfermarkt.py` (minutes, lineups, fees, values)
- **FBref advanced SNAPSHOT** (frozen before takedown) → `ingest/fbref_snapshot.py` (turnovers, Big-5 2017-22) — the one source of dispossessed+miscontrols
- **StatsBomb** open events → `ingest/statsbomb.py` (turnover calibration, narrow coverage)
- **ClubElo mirror** `tonyelhabr/club-rankings` → `ingest/strength.py` (2023+ only)

## 2. Build progress & GATE RESULTS (never loosened)
- **Stage 1 (data/coverage): PASS.** `MEMO_stage1_coverage.md`, `data/coverage.csv`. Confident corpus = Big-5 2014-24. Selling leagues have NO free xG → deferred.
- **Stage 2 (usage/efficiency): PASS + FINDING.** `impact/usage.py`. Ronaldo highest shot share (21.3%) ✓. Gate 2 (efficiency below displaced) FAILS under all 4 definitions — his per-action output was *fine*; his damage was systemic, invisible to a per-action metric. Recorded as a finding, not loosened. Penalties excluded (npxG basis).
- **Stage 3 (WOWY): PASS + honest FINDING.** `validate/ronaldo.py`, `validate/null_test.py`. Ronaldo WOWY −0.248/90 ✓ (United +0.89 xGD/90 without him). Null test: unbiased but **~80% of 1-season WOWY is game noise** (his value at 18th pct of null). → intervals + pooling mandatory.
- **Stage 4 (usage predicts impact — MAKE-OR-BREAK): PASS, weak.** `validate/stage4.py`, `MEMO_stage4_results.md`, `data/stage4/panel.csv` (2,364 movers). Unfitted predictor `usage_from × (eff_from − team_to_eff_before)`: team-delta r=**+0.083** [+0.042,+0.123], WOWY r=+0.052 [+0.002,+0.100], replicates across eras. Real but small — value must come from the whole stack, not this alone.
- **Stage 5 (league strength + age curves): IN PROGRESS** — see §4.

**STANDING RULE (over-engineering firewall):** every refinement (league strength, age, role overlap, style) gets re-run through the Stage-4 gate and **must move r or it doesn't ship.**

## 3. Data on disk (~450MB in data/, gitignored)
| dir | rows | feeds |
|---|---|---|
| understat/shots.pkl | 539,971 shots | xG, usage, efficiency, WOWY |
| transfermarkt/ | 726k minutes, 35k transfers | lineups, fees, values |
| fbref_snapshot/ | 16,139 player-seasons | turnovers |
| statsbomb/ | 1,292 player-seasons | turnover calibration |
| strength/ | 578k Elo rows | league prior (2023+ only) |
| crosswalk/matches.csv | 18,917 (100% matched) | joins Understat↔TM |
| stage4/panel.csv | 2,364 movers | the gate |

## 4. ⚠️ DATA BUG FIXED — RE-RUN REQUIRED (do this FIRST)
The `h_a/home_away` fix **landed** in `ingest/understat.py`. The dump renamed `h_a`→`home_away` from **season 2022**, so before the fix **every 2022-23, 2023-24, 2024-25 shot was mis-assigned to the away team** (`h_a=None` never matched "h"). Consequences:
- **Unaffected**: Stage 1 coverage (counts only); Stages 2-3 Ronaldo/WOWY (2021-22 had `h_a`) — football-correct, trust them.
- **CORRUPTED for 2022+ rows**: usage/efficiency/team-xGD for 2022-24, therefore part of `data/stage4/panel.csv`, the Stage-4 numbers for recent movers, and the league fit.
- **Action (in progress)**: `shots.pkl` is being rebuilt on the fixed tidy (background, ~10min). **When done, re-run in order**: `stage4_panel` build → `validate/stage4.py run` (confirm r holds) → `impact/leagues.py run` → `validate/stage5_gate.py`. Update memos/dashboard with corrected numbers.

**Also were running (now on STALE data — redo after rebuild):**
- `impact/leagues.py` fit → `data/league_strength.csv` (bootstrap slow; drop `n_boot` to ~200 if it times out).
- `impact/aging.py` (LANDED, method sound) → `data/aging/curves.csv`, API `age_multiplier(age, pos)→(mult,lo,hi)`. Within-player FE quadratic per position, cluster-boot CIs. Ran on pre-fix data → re-run `python3 -m impact.aging build` after rebuild. *Provisional peaks (value_p90, = attacking output only): FW 24.5 [23.0,25.5], DF 24.5 [22.0,26.0], MF 22.5 [18.0,24.0]; decline orders correctly (FW steepest, DF flattest — DF@33=0.78 vs MF@33=0.69). Read MF/DF as "attacking-role aging" — their true value (deep progression / defending) is off the npxG+xAG axis. Efficiency-per-action peaks much later (FW ~37) — use value_p90 curve for NPV decay.* Age+pos join = 84% of player-seasons via TM date_of_birth.

## 5. NEXT STEPS (in order)
0. **DONE 2026-07-11: rebuild + full re-run on corrected data complete.** shots.pkl verified clean. Stage 4 SURVIVED (WOWY r=+0.077 [+0.030,+0.125], team-delta +0.064 [+0.020,+0.107]). Stage 5 league strength FAILED the gate (doesn't lift r) → descriptive only, not applied to the predictor. See [[stage4-5-corrected-results]], `MEMO_stage4_results.md`, `MEMO_stage5_leagues.md`. **Nothing to redo here.**
1. **Stage 5 — DONE 2026-07-11.** League strength: failed the gate → descriptive-only. Age curves (`validate/stage5_age_gate.py`, new): one-year adjustment does NOT lift the predictor r (ratio ~1.0 barely reorders ranks) — but age curves **DO ship in NPV decay** (Stage 7), their real job (multi-year compounding). Fit re-run on corrected data (peaks FW 24.5 / MF 22.5 / DF 24.5). See `MEMO_stage5_aging.md`. **Next: Stage 6 fees (Agent B in flight) + Stage 7 money.**
   - *Provisional league fit (on pre-fix data, method sound, redo on clean): La Liga 1.107, Bundesliga 1.072, Ligue 1 1.071, EPL 1.000, Serie A 1.000, RFPL 0.966 (EPL=ref). Higher = easier to be efficient there → output discounts when moving to EPL. Read that way it's correct: EPL is the hardest league to sustain value-per-action in. ~200-280 movers/pair, tight CIs.*
2. **Stage 6 — fees. DONE 2026-07-11, gate passed (Agent B).** `money/fees.py` fits log1p(fee) OOF (HistGBR) on worldfootballR `big_5_transfers.rds`, market value joined as-of pre-window from dated R2 `player_valuations` (keyed by TM id from player_url). **Gate: Haaland→City −21% (underpay), Antony→Utd +183% (overpay).** 6,660 model-ready arrivals. Interface for Stage 7: `fit_residuals(load_big5_transfers())` → per-deal `fee`, `fee_pred`, `overpay_pct` (not persisted, YAGNI). DON'T use the R2 `transfers` table (thin, no Haaland/Antony) or `big5_player_vals.rds` (can't price inbound) for fees. Caveats (`MEMO_stage6_fees.md`): overpay_pct explodes for sub-€10m fees (display floored); TM MV is fee-informed so overpay measures vs consensus.
3. **Stage 7 + 8 — money + interface. COMPLETE 2026-07-11 (burn-the-ocean pass).** `money/points.py`: xGD→points R²=0.797, +10 npxGD≈+7.2 pts, validated exactly vs Man City 2021-22. `money/revenue.py`: **PROBABILISTIC rank** (`RevenueModel`, realization SD 7.31, frozen draws) → revenue with £28m CL cliff; marginal £/point peaks £2.1m at the CL boundary, **non-zero at the top** (fixed the deterministic degeneracy). `validate/benefit_gate.py`: gated bar variants (mean bar retained; marginal/replacement predict worse) + **calibrated** benefit to team-npxGD (slope 9.25 [3.86,14.25]) so raw actions×eff-gap no longer overstates. `money/npv.py`: calibrated benefit + age decay + probabilistic revenue → NPV + band. `money/price.py` (**Stage 8**): `price_transfer(...)` + CLI, PriceVerdict with quality flags. All 11 self-checks pass. See `MEMO_stage7_money.md`.
4. **Stage 8 — interface. DONE** (`money/price.py`, see step 3). End-to-end Arsenal pricing with error bars + quality flags.
5. **Scouting product + validation. DONE 2026-07-11 (burn-the-ocean).**
   - `money/scout.py`: ranks a real candidate universe (Understat eff/usage ⋈ TM age/pos/MV) by NPV-to-Arsenal, priced against a representative competitive position (default 72 pts = CL race, configurable; a title-winning season makes every signing look bad). Finds undervalued efficient forwards (Boniface €12m top); flags £100m+ galácticos as NPV-negative (Haaland €200m → −£100m). Cache `data/money/scout_arsenal.csv`.
   - `validate/npv_backtest.py`: (a) OOF benefit generalization — calibrate one era, predict the other: late→early +0.086 [+0.032,+0.142] clears zero, early→late +0.036 straddles (honestly mixed, recent era noisier); (b) named-case audit — model separates Haaland (−£2.5m) from Antony (−£62m) by £60m, matching reality; states the Ronaldo blind spot. Cache `data/money/backtest*.csv`.
   - **Visual artifact (scouting dossier):** https://claude.ai/code/artifact/0a80c1c0-b030-45ad-b50c-407f4759c9a9 — scout board, CL-cliff £/point curve, backtest, Haaland waterfall, honest limits. Source `scratchpad/dossier.html` (ASCII-safe; data from `scratchpad/make_artifact_data.py`).
6. **Remaining / optional loops:** (a) extend revenue beyond EPL (other leagues' central deals + CL slots) so non-Arsenal clubs / selling-side can be priced — the one real limit on scope of use; (b) defensive-value axis (model is attacking-output only → deep mids underrated); (c) style clusters; (d) richer fees; ClubElo full history. The headline system + scouting product are complete — these are breadth, not blockers.

## 6. Gotchas (will bite you)
- **rdata reads .rds** (pyreadr won't build). Understat/fbref_snapshot mix UTF-8/Latin-1 → read with `default_encoding="latin-1", force_default_encoding=True` then `_fix_mojibake`.
- **shots.pkl cache**: `read_shots()` returns it in ~1s; rds parse is ~10min. Rebuild with `read_shots(cache=False)` after any tidy change.
- **Penalties**: excluded from usage/efficiency (`situation != 'Penalty'`) — npxG basis, or Ronaldo's pens inflate his efficiency.
- **Crosswalk game_id is str** in caches but int in matches.csv — cast to str before merging (bit `validate/ronaldo.py`).
- **Agents idle-out** with "waiting on build" non-reports; their code is usually fine — check disk, finish the build yourself, don't re-spawn.
- **Wages** grade D, model only (`ingest/wages.py`), always flagged `modelled`, ±30%+ — the biggest NPV uncertainty.

## 7. Reproduce / verify
```bash
python3 -m impact.usage ronaldo      # stage 2 gate
python3 -m validate.ronaldo run      # stage 3 WOWY
python3 -m validate.null_test run    # stage 3 null
python3 -m validate.stage4 run       # stage 4 make-or-break
python3 -m impact.leagues run        # league strength (stage 5)
python3 -m validate.stage5_gate      # does league strength lift r?
# every module: python3 -m <module>  (no arg) runs its offline _check()
```
Dashboard artifact (redeploy same scratchpad `dashboard.html` path to update, keeps URL):
https://claude.ai/code/artifact/3e282ec9-0aae-4f2a-8b9c-b0d3c1a82bf4

## 8. Working style that fit this project
Parallel sub-agents for independent grunt work (each: one module, tidy fns + offline `_check()`, `build` for real pull, report data not prose). Judgment/synthesis + anything feeding the gate: do inline. Every gate falsifiable, never loosened; a surviving FAIL becomes a documented finding. Show error bars — a point estimate here is a lie. Memory files in `~/.claude/projects/.../memory/` track the durable facts.

## 9. PR #1 branch repair + V2 pass (2026-07-13, `agent/data-audit-pr`)

**Read `docs/reconciliation.md` first** — it supersedes some numbers above
(notably: NPV board is 120 rows / 5 positive, not 98/0; that was a stale
artifact, not new data). Then `docs/v2-results.md` for what the V2 pass
found, and `docs/mustermann.md` for the evidence-layer design.

**One-line status**: git repair clean (no conflicts); Phase 0 audit and V1
contract both reproduce on the combined branch; one gated fee-prototype
comparison ran and passed (F1 minimal beats F0 market-value baseline by
+11.3%, CI [+6.2%,+12.0%]); sporting-target prototypes are **blocked**, not
run — `transfer_performance_link_safe` needs an external `ESTATE_B_DIR` this
environment doesn't have; locked period (`season>=2023`) was never loaded,
proven in `reports/v2-full-data/locked_test_audit.json`.

**New this branch**: `impact/evidence.py` (per-90/shrinkage/percentile/
evidence-card primitives, self-tested), `validate/locked_guard.py` (the
locked-period exclusion helper — route any new dev-only loader through
`dev_only()`), `validate/v2_full_data.py` and `validate/v2_fee_prototypes.py`
(the two commands that produced `reports/v2-full-data/`).

**Biggest open gap**: Estate B. Without `transfer_performance_link_safe` (or
an in-repo rebuild of it from `fbref_perf` + `transfers_canonical`), the
sporting-contribution component — the more interesting half of the product —
stays unvalidatable here. See `docs/v2-results.md` "Remaining decisions".

**Also found, not fixed**: `transfers_canonical` league labels split
`"La Liga"`/`"LaLiga"` at the 2023 rebrand (`ingest/merge.py` normalization
bug); `main`'s `talent_pctl` scout-board column is wired but joins to
nothing on the live board (0/120 non-null). Both in
`docs/contradiction-log.md`.
