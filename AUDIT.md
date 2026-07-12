# DATA AUDIT & GAME PLAN — Transfer Predictions

*Full audit, 2026-07-12. Every number below was computed from the files on disk, not the summary table. Where I found the table optimistic or pessimistic, I say so.*

Two estates:
- **Estate A** — `Transfer Predictions/data/` — live raw dumps (TM + Understat + ClubElo). The working backbone.
- **Estate B** — `~/Downloads/football-transfer-db/02_transfers/transfers.duckdb` — the older DuckDB build (16 tables).

The headline: you don't have a data-*quantity* problem, you have a **fidelity, connective-tissue, and consolidation** problem. Three specific defects are quietly capping every model downstream. One is already fixed in this pass.

---

## The seven levels (audit)

### L0 — Acquisition / freshness / provenance
| Asset | Verified | Grade |
|---|---|---|
| `player_valuations` | 507,815 rows, **0 dup on (player,date)**, 2000-01-20 → 2026-02-27, 31,507 players | **Gold** (table was right) |
| `transfers` (TM) | 35,139 rows, real `transfer_date` 1993→2030(!), **fee>0 only 7.4%** | **Gold dates, thin fees** |
| `appearances` | 1,894,350 rows, 2012-07 → 2026-06, 48 comps | **Gold** |
| `games` | 88,958 rows, 2006 → 2026-07, **70 comps** | **Gold** |
| ClubElo | 581,279 rows but window **only 2023-03-27 → 2026-01-14** | **Thin — history missing** |

- **Finding L0-a:** `transfers` fee coverage is 7.4% fee>0 (20,064 zero, 12,491 null). That's *normal* for a full TM dump (most moves are free/loan/youth) — but it means this table is **not** the fee-modelling source, and correctly Stage 6 uses `big_5_transfers.rds` instead. Don't let the "Gold" grade mislead a future modeller into fitting fees off this table.
- **Finding L0-b:** 15 transfer rows are **future-dated past today** (max 2030-06-30) — rumoured/corrupt. Trivial to filter; today they can leak into any "latest move" logic.
- **Finding L0-c:** ClubElo is only a ~3-year window despite 581k rows. Full history (2000+) is a free backfill from the same mirror/API.

### L1 — Parse / ingest fidelity  ⚠️ **the big one**
- **Finding L1-a (FIXED THIS PASS):** `shots.pkl` was built with **13 of the source's 22 columns**. `tidy_shots()` hand-constructed the frame and silently dropped **`player_id`, `X`, `Y`, `shotType`, `lastAction`**. Consequences that rippled through the whole model:
  - No `player_id` → every Understat↔TM player join fell back to **name matching** (fragile on accents, transliteration, name collisions).
  - No `X`/`Y` → **no shot-quality/location features** (distance, angle) — you had xG but threw away the geometry behind it.
  - No `shotType`/`lastAction` → no header-vs-foot, no build-up context (cross/rebound/through-ball).
  - **Fix applied:** `ingest/understat.py::tidy_shots` now appends `player_id, x, y, shot_type, last_action` (guarded `_opt()`, appended after the first 13 so caller column-order asserts still hold). `shots.pkl` is being rebuilt from the rds now.
- The `h_a → home_away` mis-assignment bug (2022+ shots to wrong team) was already found and fixed per HANDOFF §4; re-runs done. Good — but note it's the *same class of bug* as L1-a: a hand-built tidy silently losing/mangling a source column. See L7.

### L2 — Identity & joins (the connective tissue)  ⚠️ **the second big one**
This is where value is leaking, because the two estates barely touch.
- **Finding L2-a:** Estate B's `player_crosswalk.player_id` is stored as **text** and **17% of rows disagree with the TM `spieler` id in their own `url_tmarkt`**. After casting to int, the crosswalk resolves — but that 17% is silent corruption. Recovering the id from the URL (`/spieler/(\d+)`) repairs it.
- **Finding L2-b:** With the cast, **11,022 Estate A players reach Estate B's 221-column FBref `perf_player_season`** (path: Estate A TM `player_id` → `player_crosswalk` → `fbref_id` → `perf_player_season`; 81.8% of crosswalk ids land in Estate A, 73.3% of those have perf rows). That link is currently **used by nothing** — the richest performance table you own is stranded behind a dtype and a broken column.
- **Finding L2-c:** There is **no TM↔Understat player crosswalk** — only a *match*-level one (`crosswalk/matches.csv`, game↔game). Player joins to Understat are name-based. Now that `shots.pkl` carries Understat `player_id` (L1-a fix), a proper player crosswalk is finally buildable.

### L3 — Derived / feature tables
- `shots.pkl` — was the L1-a victim; post-fix it becomes the clean feature base (player_id + geometry + context).
- `merged/transfers_canonical.parquet` (5.2 MB, regenerated 2026-07-12) — the canonical transfer layer; correct place to apply the L0-b date filter (never mutate the raw `.csv.gz`).
- `perf_shots_raw` (Estate B, 502,406) and `perf_shots_player_season` (26,060) **mirror Understat** — redundant with Estate A. Don't maintain twice.

### L4 — Modelling subsets
- `fee_model_ready` (16,731; fee 1k→222M, avg 6.3M) — clean, Neymar-capped, genuine. **Gold.**
- `transfer_performance_link` (123,457) — **leak risk**: `perf_season` is *not* uniformly strictly-prior to `transfer_season` (sampled pairs include perf 4 years stale, and same-season contemporaneous rows). HANDOFF flags 91,081 strictly-prior. **Must filter `perf_season < transfer_season` before training** or you leak the outcome. Usable *with the filter*, dangerous without.

### L5 — Coverage (temporal / league breadth)
- Confident xG corpus = Big-5 + RFPL, 2014-2025 (real, 0 null xG). **Selling leagues (Eredivisie, Liga Portugal, Championship, Brazil…) have no free xG** — the structural blind spot for scouting *inbound* talent from feeder leagues. Deferred, correctly, but it's the #1 coverage limit on the product's usefulness.

### L6 — Empty scaffolds / enrichment
- Estate B `contracts`, `wages`, `clauses`, `club_wage_bills` = **0 rows** (schema-only).
- **BUT** Estate A `players.csv` already carries: `contract_expiration_date` **63%**, `agent_name` **53.5%**, `foot` **88.2%**, `height_in_cm` **91.3%**, `sub_position`, `date_of_birth` 88.3%. The "contracts are empty" story is **half-false** — contract expiry (the input to free-transfer / amortisation logic) is sitting unused in the players table. Wages remain genuinely absent (modelled only, grade D — the biggest NPV uncertainty per HANDOFF §6).

### L7 — Governance (the meta-defect)
Both big bugs (h_a, and L1-a column-drop) are the **same failure mode**: a hand-written tidy function silently loses source columns, and nothing tests for it. There is no schema contract, no "source has N cols → derived keeps the ones we promised" assert, no id-overlap test between estates, no freshness check. That absence is why these bugs lived undetected. This is the highest-ROI fix after the data itself.

---

## Estate consolidation verdict

Estate B is **90% redundant with Estate A** and older:
- `transfers` (115k, season-grain, 1992-2022) — superseded by A's dated 35k + 507k valuations.
- `valuations` (32,929, 2009-2021) — superseded by A's 507,815 point-in-time.
- `perf_shots_raw` — mirrors Understat.

Estate B's **only irreplaceable assets** are:
1. **`perf_player_season`** — 221-col frozen FBref (2010-2026), the *defensive actions + progression* data that Estate A entirely lacks. This is the model's known blind spot (attacking-output-only). **This is the one thing worth importing.**
2. `player_crosswalk` — the TM↔FBref bridge (once L2-a is repaired).

Everything else in Estate B should be **archived, not maintained**.

---

## GAME PLAN (prioritized)

Effort: S ≤1h · M ≤half-day · L ≤multi-day. Payoff in model terms.

### P0 — fidelity & tissue (do first; cheap, unblocks everything)
| # | Action | Effort | Payoff |
|---|---|---|---|
| 1 | **shots.pkl full-fidelity rebuild** — `player_id, x, y, shot_type, last_action`. | S | ✅ **DONE this pass** (rebuild running). Clean joins + shot-geometry features + shot context. |
| 2 | **Build TM↔Understat player crosswalk** from the rebuilt shots.pkl (Understat player_id ⋈ TM player_id via name+season+club). Persist `data/crosswalk/players_understat_tm.csv`. | M | Kills name-matching fragility across the whole impact/ stack. |
| 3 | **Repair the cross-estate bridge** — parse `spieler` id from `player_crosswalk.url_tmarkt` (fixes the 17%), cast to int, materialize `players_master(tm_id, understat_id, fbref_id, name, dob, pos)`. | M | 11,022 players ↔ 221-col FBref, one canonical id map. |
| 4 | **Date-sanity guard** in the canonical/merged layer: drop `transfer_date > today` (15 rows) and null-date rows; assert bounds. Never touch raw `.csv.gz`. | S | No rumour rows leaking into "latest move". |

### P1 — fill what's already on disk (no new scraping)
| # | Action | Effort | Payoff |
|---|---|---|---|
| 5 | **Fill `contracts`** from `players.csv` `contract_expiration_date` (63%) + `agent_name`, `foot`, `height`. | S | Free-transfer & amortisation logic gets real contract-expiry input. |
| 6 | **Import `perf_player_season` (221 cols)** into the working estate keyed by TM id via the P0-3 bridge. | M | Adds the **defensive-value axis** — directly attacks the model's biggest known blind spot. |
| 7 | **ClubElo full-history backfill** from the same mirror (extend below 2023). | S | League-strength prior stops being a 3-year stub. |

### P2 — consolidation & governance (make it durable)
| # | Action | Effort | Payoff |
|---|---|---|---|
| 8 | **One source of truth.** Land Estate A + the two useful Estate B tables into a single DuckDB/parquet lake; **archive** Estate B's redundant tables. Document lineage per table. | L | Stops maintaining two half-overlapping copies. |
| 9 | **Data contracts + `make audit`** — cheap assertions (no framework): source-col-count → derived-col-promise, null caps, id-overlap between estates ≥ threshold, date bounds, row-count floors. Wire as an offline check like the existing `_check()`s. | M | The h_a and shots.pkl bugs could never have shipped silently with this in place. **Highest governance ROI.** |
| 10 | **`transfer_performance_link` leak guard** — bake `perf_season < transfer_season` into the view, not the caller. | S | Removes a foot-gun from every future model fit. |

### P3 — breadth (real limits, not blockers)
- **Selling-league xG** (Eredivisie/Championship/Portugal/Brazil): no *free* xG source → this is the one gap that needs either paid data or a fitted xG model on StatsBomb-calibrated shots. The single biggest expansion of product usefulness (scouting inbound talent).
- **StatsBomb licence** — 122 MB, non-commercial. Flag before any commercial use.
- Wages remain modelled-only (grade D) — the dominant NPV uncertainty; no free source exists.

---

## What I changed in this pass

### Pass 1 (audit) — the fidelity fix
- `ingest/understat.py::tidy_shots` — now carries `player_id, x, y, shot_type, last_action` (P0-1). `shots.pkl` rebuilt 13 → 18 cols, player_id/x at 100%.

### Pass 2 (burn-the-ocean) — P0 through P3 all built, all self-checked
| # | Module / file | Result (measured) |
|---|---|---|
| P0-2 | `ingest/crosswalk_players.py` → `data/crosswalk/players.csv` | **6,390 Understat→TM players resolved (90.2%)**, 6,389 at vote_share=1.0, 6 collisions. Name join retired. |
| P0-3 | `ingest/players_master.py` → `data/master/players_master.parquet` | 50,149 players; **15,012 with fbref_id, 6,387 with understat_id**; FBref bridge repaired from URL (was 17% corrupt). |
| P0-4 | `ingest/transfermarkt.py::sane_transfer_dates` | Rumour/future dates (2030 rows) dropped at the tidy boundary; guarded in `_check()`. |
| P1-5 | `ingest/contracts.py` → `data/master/contracts.parquet` | 50,149 rows, 63% contract expiry, **6,310 expiring ≤1yr** (free-transfer scout pool). Flagged current-snapshot (no leak). |
| P1-6 | `ingest/fbref_perf.py` → `data/fbref/*.parquet` | 221-col FBref keyed to TM id, **11,004 players reached**; `defensive_summary` = 14,634 player-seasons of per-90 defensive/progression metrics (the blind-spot axis). |
| P1-7 | `ingest/strength.py::build_history` → `data/strength/clubelo_history.csv` | api.clubelo.com reachable again → **193/193 clubs, 771,384 rows, 1939→2026** (was a 2023-only stub). |
| P2-8 | `ingest/warehouse.py` → `data/warehouse.duckdb` | **Single source of truth**: 10 views + leak-guarded table over every canonical artifact. Estate B redundant tables documented as archived. |
| P2-9 | `validate/audit.py` + `Makefile` (`make audit`) | **10/10 data contracts pass** — regression guard that would have caught both column-drop bugs. |
| P2-10 | `warehouse.transfer_performance_link_safe` | Leak baked out: 123,457 → **91,081 strictly-prior** rows (32,376 post-transfer excluded). |
| P3-xg | `impact/xg_model.py` | Self-owned xG from geometry: **log-loss 0.277 vs 0.323 baseline, 0.79 corr with Understat xG**, well-calibrated. Unlocks StatsBomb geometry; honest note that selling leagues have no coordinates to score. |
| P3-lic | `LICENCES.md` | Every source's commercial-use status. **2 blockers**: StatsBomb (non-commercial), Transfermarkt (CC0 mirror can't relicense proprietary data). |

Non-destructive throughout: no raw dump mutated; Estate B read-only (its useful FBref table copied into `data/fbref/`, the rest documented as safe to cold-store). Rebuild anything with `make data` / `make warehouse` / `make audit`.
