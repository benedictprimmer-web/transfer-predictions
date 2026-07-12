# DATA INDEX — every dataset, mapped

*Generated 2026-07-12 by `ingest/data_index.py` (re-run `python3 -m ingest.data_index build`). Sizes/dates scanned live from disk; row counts from the warehouse. The single map of all data — see `warehouse.py` to query it, `LICENCES.md` for the full licence audit, `DATA_SOURCES.md` for source detail.*

**38 datasets · 790.3MB on disk · 15 warehouse tables · 2,410,601 rows registered.**

Status: **LIVE** refreshes upstream · **FROZEN** static snapshot · **DERIVED** built from other rows · **OUTPUT** model result.


## xG / performance

| Dataset | Rows | Size | Status | Key | Producer | Source | Licence | Updated |
|---|--:|--:|---|---|---|---|---|---|
| **Understat shots** | 539,971 | 9.2MB | FROZEN | `match_id+player` | `ingest/understat.py` | worldfootballR_data (GitHub) | NC-understat | 2026-07-12 |
| **Understat shots (raw)** | — | 11.3MB | FROZEN | `-` | `ingest/understat.py` | worldfootballR_data | NC-understat | 2026-07-11 |
| **Selling-league shots** | 234,800 | 2.5MB | FROZEN | `tm_player_id` | `ingest/fbref_shots.py` | worldfootballR_data FBref | PROP-opta | 2026-07-12 |
| **Selling-league shots (raw)** | — | 96.5MB | FROZEN | `-` | `ingest/fbref_shots.py` | worldfootballR_data | PROP-opta | 2026-07-12 |
| **FBref perf (221-col)** | 52,951 | 6.8MB | FROZEN | `tm_player_id` | `ingest/fbref_perf.py` | worldfootballR_data snapshot | PROP-opta | 2026-07-12 |
| **FBref defense/niche** | 14,634 | 1.4MB | DERIVED | `tm_player_id` | `ingest/fbref_perf.py` | worldfootballR_data snapshot | PROP-opta | 2026-07-12 |
| **StatsBomb events** | — | 3.0MB | LIVE | `match/player` | `ingest/statsbomb.py` | statsbomb/open-data | NC-statsbomb | 2026-07-11 |
| **StatsBomb La Liga/Ronaldo** | — | 2.0MB | FROZEN | `-` | `ingest/statsbomb_laliga.py` | statsbomb/open-data | NC-statsbomb | 2026-07-12 |
| **StatsBomb event cache (raw)** | — | 121.7MB | FROZEN | `-` | `ingest/statsbomb.py` | statsbomb/open-data | NC-statsbomb | 2026-07-12 |
| **FBref turnover snapshot** | — | 1.1MB | FROZEN | `-` | `ingest/fbref_snapshot.py` | worldfootballR_data | PROP-opta | 2026-07-11 |
| **Defensive value layer** | — | 881KB | DERIVED | `tm_player_id` | `ingest/defensive_value.py` | FBref defensive_summary | PROP-opta | 2026-07-12 |
| **xT weights (StatsBomb)** | — | 3KB | DERIVED | `-` | `ingest/xt.py` | StatsBomb EPL 2015/16 | NC-statsbomb | 2026-07-12 |
| **Possession value layer** | — | 745KB | DERIVED | `tm_player_id` | `ingest/possession_value.py` | FBref niche × xT weights | PROP-opta | 2026-07-12 |
- *Understat shots* — Big-5+RFPL 2014-Jan2025; parquet is the primary store (read_shots writes it)
- *Understat shots (raw)* — one combined blob per league
- *Selling-league shots* — Eredivisie/Portugal/Championship/Brazil; 82.7% TM-linked
- *Selling-league shots (raw)* — raw match shooting .rds, 4 feeders
- *FBref perf (221-col)* — frozen Opta snapshot, Big-5 2010-2022
- *FBref defense/niche* — per-90 defensive + niche stats extracted from perf
- *StatsBomb events* — turnovers, lineups, player/team season; narrow elite coverage
- *StatsBomb La Liga/Ronaldo* — shot pulls for validation
- *StatsBomb event cache (raw)* — ~120MB raw event/360/lineup JSON caches from open-data
- *FBref turnover snapshot* — dispossessed+miscontrols, Big-5 2017-2022
- *Defensive value layer* — 14.6k player-seasons, Big-5 2018-2025; off-ball box-score composite, grade-C, unitless until calibrated
- *xT weights (StatsBomb)* — self-fit xT surface + per-action value weights (prog pass/carry, final-third); feeds possession_value
- *Possession value layer* — 14.6k player-seasons; xT-weighted buildup progression, grade-B. DESCRIPTIVE — failed NPV gate, scouting flag only

## transfers / money

| Dataset | Rows | Size | Status | Key | Producer | Source | Licence | Updated |
|---|--:|--:|---|---|---|---|---|---|
| **Transfermarkt players** | — | 3.9MB | LIVE | `player_id` | `ingest/transfermarkt.py` | dcaribou R2 (CC0 tag) | TM-risk | 2026-07-11 |
| **TM valuations** | 507,815 | 5.5MB | LIVE | `player_id+date` | `ingest/transfermarkt.py` | dcaribou R2 | TM-risk | 2026-07-11 |
| **TM transfers/fees** | — | 1.0MB | LIVE | `player_id+date` | `ingest/transfermarkt.py` | dcaribou R2 | TM-risk | 2026-07-11 |
| **TM raw (dated fees + PIT contracts)** | — | 1.9MB | LIVE | `player_id` | `ingest/tm_raw.py` | dcaribou RAW via DVC | TM-risk | 2026-07-12 |
| **TM minutes/lineups** | — | 158.4MB | LIVE | `game+player` | `ingest/transfermarkt.py` | dcaribou R2 | TM-risk | 2026-07-11 |
| **TM big-5 fees/vals (frozen)** | — | 3.7MB | FROZEN | `player_url` | `ingest/transfermarkt.py` | worldfootballR_data | TM-risk | 2026-07-11 |
| **TM raw harvest cache (JSON)** | — | 215.8MB | LIVE | `player_id` | `ingest/tm_raw.py` | dcaribou RAW via DVC | TM-risk | 2026-07-12 |
| **Canonical transfers** | 134,147 | 5.4MB | DERIVED | `transfer_id` | `ingest/merge.py` | merged estates | MIXED | 2026-07-12 |
| **Money outputs** | — | 2.0MB | OUTPUT | `-` | `money/*.py` | model | OWN | 2026-07-12 |
| **Club revenue (Deloitte)** | — | 7KB | DERIVED | `to_club_id` | `ingest/club_revenue.py` | Deloitte Money League (PDF) | PROP-deloitte | 2026-07-12 |
- *Transfermarkt players* — 50k players; MV, contract, agent, physical
- *TM valuations* — 507k rows, 2000-2026, PIT market value
- *TM transfers/fees* — thin prep table; raw below is denser
- *TM raw (dated fees + PIT contracts)* — 87k dated events, PIT contract expiries
- *TM minutes/lineups* — 726k appearances, lineups (starter/sub), 113MB lineups
- *TM big-5 fees/vals (frozen)* — big_5_transfers + big5_player_vals; historical fees <=2022/23 for money/fees.py
- *TM raw harvest cache (JSON)* — ~220MB DVC-pulled api transfers + scraper players JSON; source for raw_*.parquet
- *Canonical transfers* — 124k, deduped, leakage-safe; the money-layer backbone
- *Money outputs* — fee_ranker, scout board, backtests, calibrations
- *Club revenue (Deloitte)* — matchday/broadcast/commercial split; Stage-11 buyer-dispersion data (POC: COVID season)

## identity / master

| Dataset | Rows | Size | Status | Key | Producer | Source | Licence | Updated |
|---|--:|--:|---|---|---|---|---|---|
| **Players master** | 50,149 | 1.5MB | DERIVED | `tm_player_id` | `ingest/players_master.py` | TM + crosswalks | MIXED | 2026-07-12 |
| **Contracts** | 50,149 | 556KB | DERIVED | `tm_player_id` | `ingest/contracts.py` | TM players.csv | TM-risk | 2026-07-12 |
| **Injuries / durability** | 34,561 | 598KB | DERIVED | `tm_player_id` | `ingest/injuries.py` | salimt/football-datasets | TM-risk | 2026-07-12 |
| **Injuries (raw spells)** | — | 7.7MB | FROZEN | `tm_player_id` | `ingest/injuries.py` | salimt/football-datasets | TM-risk | 2026-07-12 |
| **Crosswalks** | 6,390 | 1.5MB | DERIVED | `us_id<->tm_id` | `ingest/crosswalk_players.py` | Understat<->TM match | MIXED | 2026-07-12 |
- *Players master* — one row/player + every foreign id (fbref/understat/sofifa)
- *Contracts* — CURRENT expiry snapshot (not PIT); for amortisation of prospective signings
- *Injuries / durability* — 34.5k players; availability multiplier + spells_before() PIT-safe
- *Injuries (raw spells)* — 143k raw spells; source for the durability summary
- *Crosswalks* — 6.4k player + 18.9k match links, 100% matched

## wages

| Dataset | Rows | Size | Status | Key | Producer | Source | Licence | Updated |
|---|--:|--:|---|---|---|---|---|---|
| **Wages (FIFA prior)** | 13,650 | 677KB | DERIVED | `tm_player_id` | `ingest/wages_fifa.py` | EA/FIFA 20-21 (GitHub) | GAME-fifa | 2026-07-12 |
| **FIFA raw** | — | 45.4MB | FROZEN | `sofifa_id` | `ingest/wages_fifa.py` | ifrankandrade (GitHub raw) | GAME-fifa | 2026-07-12 |
| **Wages (Capology real)** | — | 1.1MB | LIVE | `tm_player_id` | `ingest/wages_capology.py` | capology.com (personal-use) | TM-risk | 2026-07-12 |
| **Wages Capology (full history)** | — | 1.7MB | LIVE | `tm_player_id+season` | `ingest/wages_capology.py` | capology.com | TM-risk | 2026-07-12 |
| **Wages FIFA time-series** | — | 504KB | DERIVED | `tm_player_id+year` | `ingest/wages_fifa.py` | EA/FIFA 17-21 | GAME-fifa | 2026-07-12 |
- *Wages (FIFA prior)* — 10.2k players, era-consistent blend; grade-C real signal
- *FIFA raw* — FIFA 17-21 player DB (extended 2026-07)
- *Wages (Capology real)* — 14.6k players, 8 leagues 2013-2026, REAL salaries; grade-B, wired into estimate_wage
- *Wages Capology (full history)* — 64.7k rows, per-season history
- *Wages FIFA time-series* — 40.3k rows, per-year wage panel

## strength

| Dataset | Rows | Size | Status | Key | Producer | Source | Licence | Updated |
|---|--:|--:|---|---|---|---|---|---|
| **ClubElo ratings** | 771,384 | 29.0MB | LIVE | `club+date` | `ingest/strength.py` | api.clubelo.com (now live) | CC-clubelo | 2026-07-12 |
| **ClubElo per-club history** | — | 39.9MB | LIVE | `club` | `ingest/strength.py` | api.clubelo.com | CC-clubelo | 2026-07-12 |
| **League strength fit** | — | 0KB | OUTPUT | `league-pair` | `impact/leagues.py` | fitted from shots | OWN | 2026-07-11 |
- *ClubElo ratings* — 771k rows; history to ~1946 via the now-reachable API
- *ClubElo per-club history* — one CSV per club (~230 clubs)
- *League strength fit* — descriptive only (failed the predictor gate)

## analysis artifacts

| Dataset | Rows | Size | Status | Key | Producer | Source | Licence | Updated |
|---|--:|--:|---|---|---|---|---|---|
| **Coverage / panels** | — | 937KB | DERIVED | `-` | `ingest/coverage.py + validate` | derived | OWN | 2026-07-11 |
- *Coverage / panels* — Stage-1 coverage, Stage-4 mover panel, age curves

## unified

| Dataset | Rows | Size | Status | Key | Producer | Source | Licence | Updated |
|---|--:|--:|---|---|---|---|---|---|
| **Warehouse** | — | 4.8MB | DERIVED | `-` | `ingest/warehouse.py` | views over the above | OWN | 2026-07-12 |
- *Warehouse* — one DuckDB; views (always fresh) + leak-guarded link table

## Licence codes

- **NC-understat** — Understat — non-commercial (owner e-mail), attribution
- **NC-statsbomb** — StatsBomb — non-commercial user agreement + logo
- **PROP-opta** — FBref/Opta — proprietary, not licensable (remove for any product)
- **TM-risk** — Transfermarkt — CC0 mirror tag can't relicense TM's DB (commercial risk)
- **CC-clubelo** — ClubElo — free for research w/ attribution; commercial undocumented
- **GAME-fifa** — EA/FIFA game-derived — research/personal only, not for resale
- **FACTS** — factual figures (revenue) — usable, cite primary
- **PROP-deloitte** — Deloitte Money League — proprietary report, cite; figures are facts
- **OWN** — own model output — yours
- **MIXED** — mixed upstreams — treat each by origin

## Querying

```python
from ingest import warehouse
con = warehouse.connect()          # read-only DuckDB
con.execute('SELECT * FROM injuries LIMIT 5').df()
# joins on tm_player_id: players_master ⋈ contracts ⋈ injuries ⋈ wages_fifa
```

*Commercial note: most upstreams are non-commercial / proprietary / DB-risk (see LICENCES.md). Clean-to-ship: own model outputs, ClubElo (attribution), revenue facts.*
