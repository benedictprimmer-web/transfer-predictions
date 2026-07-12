# Stage 1 — Data coverage & scope memo

*Status: **xG coverage gate PASSED** for Big-5 + RFPL from real data (539,971 shots). Lineup-minutes (one more source) pending. Scope decision below.*

---

## What changed since the first pass

The original plan (FBref via soccerdata) is dead, for two independent reasons:

1. **FBref lost its advanced data.** Stats Perform (Opta) terminated FBref's feed in Jan 2025 — xG, shot-creating actions and turnovers are gone from the site regardless of how you access it.
2. **FBref 403s this environment** anyway (datacenter IP, verified 2026-07-11).

We pivoted to **Understat** shot-level xG via the `worldfootballR_data` static `.rds` dumps (see `DATA_SOURCES.md`). These are reachable and parseable from here — **no user-in-the-loop pull needed.** `ingest/fbref.py` + `ingest/coverage.py` are kept only as a record of the dead end; the live engine is **`ingest/understat.py`**.

Rebuild any time with: `python3 -m ingest.understat build` → `data/coverage.csv`.

---

## Coverage — real numbers (`data/coverage.csv`)

539,971 shots, 6 leagues, 11 seasons. **Every league-season has full shot-level xG** (`has_xg = has_shot_minutes = True` throughout). Understat starts at **2014-15 — two seasons earlier than FBref ever had xG.**

| League | Seasons present | Complete seasons | Shots/match | Notes |
|---|---|---|---|---|
| ENG Premier League | 2014-15 → 2024-25 | 2014-15 → 2023-24 (380 ea.) | ~25 | |
| ESP La Liga | 2014-15 → 2024-25 | 2014-15 → 2023-24 | ~24 | |
| ITA Serie A | 2014-15 → 2024-25 | 2014-15 → 2023-24 | ~26 | |
| GER Bundesliga | 2014-15 → 2024-25 | 2014-15 → 2023-24 (306 ea.) | ~26 | 18 teams = 306 |
| FRA Ligue 1 | 2014-15 → 2024-25 | 2014-15 → 2023-24 | ~24 | 2019-20 = 279 (COVID, real); 2023-24 onward 306 (18 teams, real) |
| RUS Premier League | 2014-15 → 2024-25 | 2014-15 → 2023-24 (240 ea.) | ~25 | bonus league, not a target |

**Two real caveats, both flagged not hidden:**
- **2024-25 is ~half a season** everywhere (EPL 196/380, etc.) — the static dump's refresh cut off mid-2024-25. Completable with a live Understat refresh (Understat is reachable from here) when we need the latest season.
- **The Ronaldo acceptance-test season is complete:** EPL 2021-22 = 380 matches, 9,775 shots, 450 players. Arsenal's seasons are all present. The make-or-break Stage-2/3 gates sit inside complete data.

---

## Scope decision (the written gate requirement)

1. **Confident corpus = Big-5, 2014-15 → 2023-24.** Ten complete seasons of shot-level xG per league. Everything squad-aware (usage, efficiency, WOWY) is built and validated here. Contains Arsenal and Man Utd 2021-22.

2. **Selling leagues have NO free shot-xG.** Understat is Big-5 + RFPL only. Championship, Eredivisie, Primeira, Liga MX and Brazil Série A have no free shot-level xG dump anywhere (confirmed in `DATA_SOURCES.md`). So the cross-league value engine (SPEC §4) cannot use xG for the selling side — it must lean on Transfermarkt output + a league-strength multiplier, or accept goal-based proxies. **Defer selling-league modelling until the cross-league method is proven on Big-5 pairs**, exactly as SPEC §8 recommends.

3. **RFPL (Russia) is available but out of scope** as a target market; keep it only as extra data for fitting league-strength and age curves if useful.

4. **Net honest scope:** a **Big-5, 2014-2024 xG-era transfer valuator.** Selling-league reach is limited by data, not method, and only extends as far as the cross-league multiplier's error bars justify.

---

## Remaining data to wire (not blocking the xG gate)

| Need | Source | Status |
|---|---|---|
| Lineups & minutes (WOWY on/off windows) | Transfermarkt `player-scores` appearances/game_lineups | **next ingest step** — Understat has shot-minutes, not lineups |
| Turnovers (usage 3rd component) | StatsBomb open-data (narrow coverage) | usage falls back to shots + shot-assists elsewhere |
| Transfers, fees, market values | Transfermarkt `player-scores` | for Stage 6 (fees) |
| Wages | no free dump → wage model | biggest NPV uncertainty; flag everywhere |
| League strength prior | `tonyelhabr/club-rankings` (ClubElo mirror) | Stage 5 |
| Prize money / CL revenue | figures in `DATA_SOURCES.md` | Stage 7 |

---

## Gate status

- [x] Coverage table populated with **real** numbers (`data/coverage.csv`, 539,971 shots)
- [x] xG + shot-minute availability confirmed per league-season (100% across the corpus)
- [x] Written scope decision (this memo)
- [ ] Lineup-minutes coverage — pending the Transfermarkt appearances pull (near-universal, low risk)

**xG coverage gate: passed.** The one open item (lineups) is a different source and doesn't gate the shot/usage work. Clear to start **Stage 2 — usage & efficiency**, whose gate is Ronaldo's 2021-22 United shot share coming out highest in the squad at below-displaced efficiency — and that season's data is complete and loaded.
