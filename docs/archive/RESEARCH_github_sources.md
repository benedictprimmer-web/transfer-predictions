# Open football-data research — GitHub & open sources (2026-07-12)

*Deep-research pass over the open-source football-data landscape, run as five parallel
verification agents. Every existing source was **curl-tested from this project's real
datacenter egress IP** (not a browser fetcher); every new source was checked live and
graded. Complements [`DATA_SOURCES.md`](DATA_SOURCES.md) (the starter stack) and
[`LICENCES.md`](LICENCES.md) (the commercial-risk audit) — read those first.*

Scope requested: (1) verify the existing stack, (2) broad landscape sweep, (3) deep-dive
the three priority gaps — **defensive/event data, revenue/commercial, wages/contracts/injury**.
Scrape-only sources are catalogued too, flagged clearly.

**Access legend:** `STATIC` = downloadable dump (git raw / Kaggle / figshare / release), always
datacenter-safe · `DC-API` = real API that answers datacenter IPs · `SCRAPE` = live-site scrape,
fragile and often 403s a datacenter IP like FBref does.

---

## TL;DR — the eight things that matter

1. **Your existing core is healthy but two mirrors froze.** Transfermarkt (R2, refreshed
   2026-07-11) and StatsBomb open-data (2026-05-26) are current. **`worldfootballR_data` was
   archived 2025-09-18** — your Understat shots + FBref snapshot + big5-transfers now come from a
   read-only snapshot that **stops at ~Jan 2025** (no 2025/26 season will ever land). Your
   `ingest/understat.py` is already on the correct combined-blob path, so nothing is *broken* —
   but the well is now capped. Plan a live Understat replacement before you need 2025/26 data.
2. **ClubElo's live API now answers your datacenter IP** (200 in 2.0s; it timed out when
   `DATA_SOURCES.md` was written). `ingest/strength.py` already has the `_API_URL` path wired —
   flip to it and retire the stale 2023 `tonyelhabr` mirror. *Free upgrade, code already exists.*
3. **Defensive axis is unblocked, commercially cleanly:** the **Pappalardo/Wyscout** event logs
   (figshare, **CC-BY-4.0 — commercial OK**), big-5 2017/18 with x,y coordinates, fed through
   **socceraction/VAEP**, give you a real defensive-value + progression axis you can *legally ship*.
   This is the single most strategically valuable find — see §5.
4. **Contracts are solved and you already have the file:** `dcaribou/transfermarkt-datasets`
   (which you mount for fees) has a `contract_expiration_date` date column (CC0, weekly). You just
   aren't reading it. Amortise fees over `contract_expiration_date − transfer_date`.
5. **Injuries are solved:** figshare #25648788 "Injuries from Transfermarkt" — 107k spells with
   from/until dates + days-out, **CC-BY**. Compute availability% and a durability score per player-season.
6. **Non-EPL revenue is sourceable:** the full UCL/UEL/UECL 2024–27 prize ladder plus verified
   per-league central-distribution figures (La Liga reparto, DFL 4-pillar, Serie A diritti TV,
   parachute payments) are in §3b — enough to price a non-Arsenal club.
7. **Wages stay grade-D and that won't change for free.** No redistributable real-wage dump exists;
   Capology is the ground truth everyone resells but it's scrape-only/paid. Only static option is
   FM24/FIFA game-derived *ordinal* proxies. Correction to prior notes: FBref wages were **not**
   removed (still Capology-powered) — but FBref 403s your IP, so it's dead for you regardless.
8. **Biggest additive breadth win:** `football-data.co.uk` — STATIC CSVs, 22+ divisions back to
   1993/94 **with betting odds** (a market-implied strength signal you have no equivalent for) and
   no scraping. Highest value-to-effort for league coverage beyond Understat's big-5+RFPL.

---

## 1. Verification of existing stack (curl-tested from sandbox, July 2026)

| Source | curl result | Last updated | Status | Note |
|---|---|---|---|---|
| **Understat shots** `worldfootballR_data/.../epl_shot_data.rds` | 200, 2.21 MB | data 2025-01-05; **repo archived 2025-09-18** | ⚠️ FROZEN | Combined blob per league (`epl_/la_liga_/bundesliga_/serie_a_/ligue_1_/rfpl_shot_data.rds`). Old per-season path (`EPL/EPL_2023.rds`) now **404s** — your ingest already migrated |
| **Transfermarkt R2** `pub-…r2.dev/data/transfers.csv.gz` | 200, 1.06 MB | repo commit **2026-07-11** | ✅ HEALTHY | `player_valuations` 5.7MB, `appearances` ~40MB, `players` 4.1MB all 200. Weekly refresh. **Has `contract_expiration_date`** (see §2c) |
| **StatsBomb** competitions/events/LICENSE | 200 (34.9KB / 3.26MB / 165KB) | commit **2026-05-26** | ✅ HEALTHY | Actively maintained; non-commercial LICENSE.pdf still present |
| **ClubElo mirror** `tonyelhabr/club-rankings` release | 206 ranged OK (48.9MB) | release frozen **2023-03-26** | ⚠️ STALE | Data 2+ years old — superseded by live API below |
| **ClubElo API** `api.clubelo.com/2024-01-01` | **200, 35.9KB, 2.0s** | live | ✅ **NOW WORKS** | Was blocked/timeout per notes; now serves this IP. Retire the mirror |
| **FBref** `fbref.com/en/` | **403** (0.58s) | — | ❌ DEAD (expected) | Still hard-blocked; advanced xG still absent site-wide since Jan-2025 Opta removal |
| **worldfootballR big_5_transfers.rds** | 200, 1.97 MB | data **2022-09-06** | ⚠️ FROZEN | Only file in `tm_transfers/`; part of archived repo |
| **fb_big5_advanced_season_stats** (snapshot) | 200, 1.88 MB | archived 2025-09-18 | ⚠️ FROZEN | 22 .rds files (player/team × standard/shooting/passing/defense/gca/possession/misc) |

**What changed since 2026-07-11 notes:**
- **`worldfootballR_data` archived (read-only) 2025-09-18** — Understat + FBref-snapshot + big5-transfers are all now dead snapshots. Downloads still 200, but no future refreshes. **This is the biggest thing to plan around.**
- **ClubElo API flipped from blocked → working.** Live per-club history back to ~1946 is now reachable; the 2023 mirror is obsolete.
- **Unchanged & good:** Transfermarkt (R2 + Kaggle CC0), StatsBomb, FBref-still-403.

---

## 2. Priority gap-fillers

### 2a. Defensive & event-level data — *unblocks the defensive-value axis*

Model is attacking-output-only today (Understat shots). These add tackles/interceptions/pressures/
duels/recoveries + progression + possession-value (VAEP/xT).

| # | Source | Identifier | Fields / granularity | Coverage | Access | Licence (commercial?) | Grade |
|---|---|---|---|---|---|---|---|
| 1 | **Wyscout events** (koenvo mirror) | `github.com/koenvo/wyscout-soccer-match-event-dataset` | Event-level duels (ground/air/loose), interceptions, clearances, ball losses/recoveries, passes — **with x,y** | Big-5 2017/18 (~1,826) + WC18 + Euro16 (~1,851 matches) | STATIC (JSON + parquet) | **CC BY 4.0 — YES** | **A** |
| 2 | **StatsBomb open-data** | `statsbomb/open-data` | Richest free events: Pressure, Duel, Interception, Block, Ball Recovery, Clearance, Dribbled Past + **360 freeze-frames** | UCL full history, La Liga (all Messi), WCs, Euro 20/24, single-season PL/Serie A/Ligue 1/Bundesliga slices | STATIC | User Agreement — **NON-COMMERCIAL** + logo | A (data) / research-only |
| 3 | **socceraction** (VAEP / atomic-VAEP / xT) | `ML-KULeuven/socceraction` | *Library.* Per-action offensive **and defensive** value; SPADL loaders for StatsBomb+Wyscout+Opta | runs on #1/#2 | STATIC (pip) | **MIT — YES** | A |
| 4 | **Pappalardo "Soccer logs"** (canonical) | figshare DOI **10.6084/m9.figshare.c.4415000** (Nature Sci Data 6:236) | Source of #1; same fields | Big-5 2017/18 + WC18 + Euro16 | STATIC (figshare — *403s this IP*; use #1) | **CC BY 4.0 — YES** | A |
| 5 | **worldfootballR_data** season aggregates | `JaseZiv/worldfootballR_data` `big5_player_defense/_possession` | **Per-90 season** tackles/interceptions/blocks/pressures, progressive carries, touches-by-third | Big-5 through ~2022/23 | STATIC (.rds) | FBref/Opta terms — **NO** | B+ (frozen) |
| 6 | **Karun Singh xT grid** | `karun.in/blog/data/open_xt_12x8_v1.json` | 8×12 expected-threat grid | grid (any x,y) | STATIC (live JSON) | Open, attribution | A |
| 7 | **kloppy** | `PySport/kloppy` | Loader/normaliser (StatsBomb/Wyscout/Metrica/SkillCorner/Sportec/Opta) → one schema | n/a | STATIC (pip) | **BSD-3 — YES** | A |
| 8 | **Metrica sample-data** | `metrica-sports/sample-data` | Synced tracking + event | 3 games | STATIC | permissive | A |
| 9 | **SkillCorner opendata** | `SkillCorner/opendata` | Broadcast tracking + off-ball runs | 10 games (A-League 24/25) | STATIC | **MIT — YES** | A |
| 10 | **DFL/IDSSE** | `spoho-datascience/idsse-data` | Official DFL synced position+event XML | 7 Bundesliga matches 22/23 | STATIC | **CC BY 4.0 — YES** | A |
| — | soccerdata / ScraperFC / worldfootballR (live) | resp. repos | FBref/WhoScored/Sofascore scrapers | live | SCRAPE (FBref 403s this IP) | mixed | C from this IP |

**Wire-first:** **#1 Wyscout → #3 socceraction/VAEP** is the only combination that is static,
coordinate-rich enough to value defensive actions, **and CC-BY-4.0 (shippable)**. Add **#6 Karun xT**
as a 2-line possession-value feature first. Use **#2 StatsBomb** (Pressure/360) + **#5** (per-90 join)
as *offline validation only* — keep both out of any commercial build (StatsBomb licence; #5 frozen).

### 2b. Revenue & commercial — *extends the benefit side beyond EPL*

| # | Source | Provides | Coverage | Access | Grade |
|---|---|---|---|---|---|
| 1 | **UEFA distribution circular** `editorial.uefa.com/.../circular_2024_13_en.pdf` | Full UCL/UEL/UECL prize ladder | 2024–27 cycle | PRIMARY (PDF 403s IP — mirror below) | A |
| 2 | **football-coefficient.eu/money** | Reproduced 3-comp ladder + live per-club totals | UCL/UEL/UECL | SCRAPE (fetchable) | B+ |
| 3 | **LALIGA transparency portal** `laliga.com/en-GB/transparency` | Official per-club audiovisual *reparto* + formula | La Liga 1&2, 2015/16→24/25 | PRIMARY | A |
| 4 | **DFL Wirtschaftsreport** `report.dfl.de/2324/` | 4-pillar media split + per-club floor | Bundesliga 1&2 | PRIMARY (PDF only) | A |
| 5 | **Serie A** via `calcioefinanza.it` | Per-club *diritti TV* (Melandri formula) | Serie A 24/25 | SCRAPE (secondary) | B+ |
| 6 | **EFL/PL parachute + solidarity** | Parachute tiers + solidarity per tier | English pyramid | PRIMARY + wiki | A/B |
| 7 | **Deloitte Football Money League** | Top-20 club revenue + matchday/broadcast/commercial split | global top-20, 1996/97→ | PRIMARY (PDF, no official CSV) | A |
| 8 | **Wikipedia Deloitte tables** / `MikeyBronowski/FootballDataSets` CSV | Same, machine-readable | top-20 multi-year | STATIC/SCRAPE | B+/C+ |
| 9 | **UEFA ECFIL Benchmarking** `ecfil.uefa.com/2024` | Per-league aggregate club revenue, wage ratios | all UEFA top divs | PRIMARY (PDF) | A |
| 10 | **Companies House** free API | Statutory accounts (turnover, wages) | English clubs, all tiers | PRIMARY (REST API, OGL) | A |

**Verified figures — UEFA 2024/25 (per club, EUR), 36-team league phase:**
```
CHAMPIONS LEAGUE (club pool ~€2.03bn)
  Start €18.62M · win €2.10M · draw €0.70M · rank-share ~€275k/unit (×666 units)
  KO (2026/27 ladder): R16 €11M · QF €12.5M · SF €15M · Final €18.5M · Winner +€6.5M
  (2024/25 secondary reporting differs on KO — pin to the circular before shipping)
EUROPA LEAGUE   start €4.31M · win €0.45M · draw €0.15M · Final €7M · Winner +€6M
CONFERENCE LGE  start €3.17M · win €0.40M · draw €0.133M · Final €4M · Winner +€3M
```
**Domestic central distribution — 2024/25:**
```
LA LIGA (total €1.29bn; 50% equal / 25% sporting / 25% social+commercial)
  Madrid €157.9M · Barça €156.5M · Atléti €108.2M · equal-share floor ~€35–37M
BUNDESLIGA (total €1,212M; Equality 50% / Performance 43% / Youth 4% / Interest 3%)
  BL1 equal floor €26.2M · BL2 floor €7.4M · national rights → €1.121bn/season from 25/26
SERIE A (total €898M; Melandri: ranking + audience + history)
  Inter €81.9M … Venezia €25.5M (top:bottom ~3.2:1)
LIGUE 1 (2024–29 ~€500M/yr gross; net pool ~€142M) PSG ~€30–35M, very unequal (~1:10–15)
ENGLISH PYRAMID  parachute ~£49M(y1)/£40M(y2)/20%(y3); solidarity Champ ~£5.5M
EREDIVISIE  ESPN €150M/season, no public per-club table
LIGA PORTUGAL  still DECENTRALISED in 24/25 (no central formula until 2028/29)
```
**Baselines:** Deloitte ML 24/25 — top-20 combined revenue >€12bn. UEFA ECFIL 2024 — top-division
club revenue >€29bn FY2024; ~€300m gap between 8th and 12th club (polarisation).

**Minimum set to price a non-EPL club:** (1) lift the UCL/UEL/UECL ladder once, apply by
qualification tier; (2) one *equal-share floor* + one *merit-per-place slope* per domestic league
from the primary per-club tables; (3) anchor a revenue baseline with Deloitte top-20 + ECFIL
per-league aggregates, Companies House for English precision. **Access caveat:** UEFA
`editorial.uefa.com` PDFs 403 this IP → use football-coefficient.eu / the `cdn.vev.design` ECFIL mirror.

### 2c. Wages, contracts & injuries

**Contracts — SOLVED (you already have the file):**
- `dcaribou/transfermarkt-datasets` = Kaggle `davidcariboo/player-scores`, `players.contract_expiration_date`
  (real `date` column, parsed by `parse_contract_expiration_date`) — **CC0**, weekly, joins on `player_id`.
  Amortise over `contract_expiration_date − transfer_date`. Snapshot (current expiry), not historical
  series; back-fill contract *start* from `salimt/football-datasets` `joined` (licence unstated → use, don't resell).

**Injuries — SOLVED:**
- figshare **#25648788** "Injuries from Transfermarkt" — spells with `from/until/Days/Games missed/player_id`,
  107k injuries / 18.5k players, **CC-BY**. → availability% + durability per player-season.
- `salimt/football-datasets` `player_injuries` — largest (143k records) + `injury_reason` (severity weighting),
  licence unstated. `irrazional/transfermarkt-injuries` (Kaggle) — same schema. **UEFA Elite Club Injury Study**
  — aggregate base-rates by position/age (priors to shrink thin individual histories).

**Wages — STILL HARD (the grade-D gap):**
| Source | Provides | Access | Licence | Grade |
|---|---|---|---|---|
| **Capology** `capology.com` | Per-player gross/net wage estimates + expiry year | **SCRAPE** (+ paid API) | proprietary, **not redistributable** | B data / F access |
| **Spotrac** | *Reported* salaries (EPL+MLS) | SCRAPE (+ paid API) | proprietary | B / F |
| FBref wages (Capology-powered) | same estimates | **403 this IP** | Capology terms | B / F |
| `ultimus/football-salaries-dataset` (Kaggle) | ~40k players, one figure | STATIC | **FM24 game-derived** | C (ordinal) |
| FIFA/SoFIFA dumps (FIFA 15–24) | per-player wage+value | STATIC | **EA game-derived** | C (ordinal) |

*Correction:* FBref wage tables were **not** removed (still "Data via Capology", live 2025-26) — but
FBref 403s your IP so it's dead for you. **No free static Capology dump exists** — only scrapers.
**Least-bad workaround:** ordinal wage prior — rank into bands from FM24 (ultimus) + FIFA (both static/CC),
calibrate band→£ against the ~50–100 publicly-reported real salaries per league. Narrows ±30% → ~±20%,
legally clean. A whitelisted-IP Capology scrape upgrades to grade-B but is non-redistributable.

---

## 3. Broad landscape sweep — additive finds you're not using

Full grouped tables live in the agent reports; the genuinely **additive** rows:

| Source | Identifier | Adds | Access | Licence | Grade |
|---|---|---|---|---|---|
| **football-data.co.uk** | football-data.co.uk CSVs | 22+ divisions to 1993/94 + **betting odds** (market strength) + match stats | STATIC | free/unrestricted | A |
| **Pappalardo/Wyscout** | figshare (see §2a #1/#4) | commercially-usable full-season events | STATIC | CC-BY-4.0 | A |
| **socceraction + penaltyblog** | `ML-KULeuven/socceraction`, `martineastwood/penaltyblog` | VAEP/xT valuation + Dixon-Coles/Poisson/Elo models | STATIC | MIT | A |
| **FiveThirtyEight SPI** | `fivethirtyeight/data/soccer-spi` | ~40-league off/def ratings + match xG (frozen 2023) | STATIC | CC-BY-4.0 | A |
| **openfootball / footballcsv** | `openfootball/*` | fixtures+scores incl. non-big-5/lower tiers | STATIC | CC0 | A |
| **api-football** (RapidAPI) | rapidapi | 1000+ leagues incl. selling leagues + injuries | DC-API (paid) | commercial | B |
| **kloppy / mplsoccer / statsbombpy** | resp. | event/tracking loaders + viz | STATIC | BSD/MIT | A |
| **European Soccer DB** (Kaggle) | Hugo Mathien sqlite | FIFA attributes + 11 countries 2008–2016 | STATIC | **CC-BY-NC** (⚠) | B (stale) |
| **ScraperFC** | `oseymour/ScraperFC` | Capology/Sofascore scrapers | SCRAPE | GPL-3.0 (⚠ copyleft) | B |

**Best index to mine further:** `eddwebster/football_analytics` and `matiasmascioto/awesome-soccer-analytics`.
Cross-checking the awesome-lists surfaced nothing material beyond the above (they point back to
StatsBomb/Wyscout/openfootball/soccerdata).

---

## 4. Action list (ranked by value-to-effort)

1. **Read the contract column you already have** — add `contract_expiration_date` from the mounted
   `dcaribou` dump to fee amortisation. Zero new dependency. *(Fixes an approximation in `money/`.)*
2. **Flip ClubElo to the live API** — `ingest/strength.py` already has `_API_URL`; the API now answers
   your IP. Retire the frozen 2023 mirror; gain full history back to ~1946. Add a per-club cache.
3. **Wire the defensive axis: Wyscout (#1) → socceraction/VAEP (#3)** — CC-BY-4.0, static, coordinate-rich.
   This is the one commercially-clean path to the defensive-value axis §6 of HANDOFF flags as missing.
   Start with Karun xT (#6) as a cheap possession-value feature, then full VAEP. **Re-run through the
   Stage-4 gate** — it only ships if it lifts r (standing firewall).
4. **Add injuries** — figshare #25648788 (CC-BY): availability% + durability per player-season → a
   durability discount in NPV. Shrink thin histories toward UEFA-study base-rates.
5. **Extend revenue beyond EPL** — encode the UCL/UEL/UECL ladder (§3b) + one floor+slope per domestic
   league. Unblocks pricing non-Arsenal / selling-side clubs (the one real scope limit in HANDOFF §6a).
6. **Add football-data.co.uk** — cheap, static, huge league breadth + an odds-implied strength signal.
   Good cross-check for the (failed-as-predictor) league-strength work and a route into selling leagues.
7. **Plan an Understat live replacement** — the mirror is frozen at Jan 2025. Options: understat.com
   direct (earlier notes: returns 200 to this IP), ScraperFC Understat, or accept the frozen corpus for
   backtesting and source 2025/26 elsewhere. Not urgent until you need current-season shots.
8. **Wage prior upgrade (optional)** — FM24 + FIFA ordinal bands calibrated to public salaries.
   ±30%→~±20%, legally clean; keep the grade-D honesty flag.

---

## 5. Commercial-licence lens (ties to `LICENCES.md`)

`LICENCES.md` concludes the stack is a sound *research* system but **not sellable**: its two core
engines (Understat xG, Transfermarkt money) plus the StatsBomb turnover input each carry a
commercial-use problem. This research changes the picture in one important way and confirms it in others:

**New — commercially CLEAN sources (safe to build a product on):**
- **Wyscout/Pappalardo events — CC-BY-4.0.** Coordinate-rich event data → via **socceraction (MIT)** a
  full offensive+defensive VAEP layer. **This can replace the non-commercial StatsBomb turnover input**
  for the confident big-5 2017/18 window, removing LICENCES.md blocker #1 from the *shipped* path.
- **figshare injuries — CC-BY**, **football-data.co.uk — free/unrestricted**, **openfootball — CC0**,
  **FiveThirtyEight SPI — CC-BY-4.0**, **Karun xT — open**, **kloppy/mplsoccer/statsbombpy — BSD/MIT**,
  **UEFA/league revenue — facts**. All shippable.

**Confirmed still-encumbered (unchanged from `LICENCES.md`):**
- **Understat** (lean non-commercial), **Transfermarkt** (CC0 tag can't relicense TM's DB — the
  `contract_expiration_date` win inherits this risk), **StatsBomb open-data** (non-commercial),
  **FBref/Opta snapshot** (proprietary, remove), **Capology wages** (not redistributable),
  **European Soccer DB** (CC-BY-**NC**), **ScraperFC** (GPL-3 copyleft — CLI-only, don't link).

**Net:** the fastest route toward a *sellable* build is **Wyscout(CC-BY) + VAEP** for the on-pitch value
engine, licensed Transfermarkt (or a paid feed) for money, and the CC-BY/CC0/free revenue+injury
sources above — leaving Understat and StatsBomb as research-only enrichment you strip for a product.

---

*Method: 5 parallel research agents, 2026-07-12. Existing sources curl-tested from the project's
datacenter egress IP; new sources verified live via web fetch. Grades weigh provenance, licence
clarity, durability, and datacenter-reachability. Re-verify prize-money figures against primary
circulars before they enter `money/` coefficients.*
