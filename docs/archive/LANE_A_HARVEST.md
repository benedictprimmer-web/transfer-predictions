# Lane A Harvest — Wages (2026-07-12)

Wages moved from **grade-C FIFA-only (10,217 players, 2 editions)** to a **stacked
grade-B real-salary layer (14,593 players, real reported wages, current-season) +
extended grade-C FIFA prior (13,650 players, 5 editions, genuine time series)**.
`estimate_wage()` now returns the real number, best-grade-first, whenever one exists.

## Phase 0 — what was already on disk

- `data/wages/`: `fifa_players_20.csv`, `fifa_players_21.csv`, `wages_fifa.parquet` —
  **10,217 players priced** (43% of FIFA crosswalked), only 2 editions (2020/21), no
  time series. Big-5 subset: 2,780 players.
- Integration point (`ingest/wages.py::estimate_wage`) already had a `tm_player_id`
  opt-in path that preferred a FIFA row over the parametric model — but **no
  Capology-priority path existed** despite the docstring implying one; `load_capology_csv()`
  was a tolerant CSV loader with no caller wiring it into `estimate_wage()`.
- Hole map (canonical spine `data/merged/transfers_canonical.parquet`, 134,147
  transfer rows, 19,952 unique players — this file changed size mid-session, likely
  a parallel lane rebuilding it; all coverage % below are against the same snapshot
  used for the final numbers):

  | Season | FIFA-only coverage | | League | FIFA-only coverage |
  |---|---|---|---|---|
  | 2020 | 63.3% | | Premier League | 41.9% |
  | 2022 | 45.3% | | Serie A | 40.8% |
  | 2023 | 31.7% | | Ligue 1 | 41.3% |
  | 2024 | 30.3% | | La Liga | 18.1% (name-split bug: "La Liga" vs "LaLiga" rows) |
  | 2025 | 28.3% | | Bundesliga | 46.1% |
  | 2026 | 22.1% | | Eredivisie | 71.7% |

  Two clear holes: **recent seasons (2023-2026) collapse to 22-32%** (FIFA is frozen
  at 2020/21), and **no real wage is ever current** — even where FIFA matched, the
  level is 5+ years stale. No corruption found in the existing FIFA table beyond the
  known ~57% crosswalk miss rate (documented, not a landmine).

## Reachability (curl -sI / HEAD, browser UA, this sandbox, 2026-07-12)

| Source | Status | Route |
|---|---|---|
| `capology.com/uk/premier-league/salaries/` (+ all leagues/seasons) | **200** (HTTP), but salary *fields* are paywalled per-league — see below | sandbox-ok for the 8 free leagues |
| `raw.githubusercontent.com/ifrankandrade/data-visualization` players_17-21.csv | **200** | sandbox-ok |
| same repo, players_15/16/22/23.csv | **404** (don't exist at this mirror) | n/a |
| `find-and-update.company-information.service.gov.uk` (Companies House) | **200** | sandbox-ok, but see below |
| `spotrac.com/epl/rankings/...` | **403** | needs-residential |
| `en.wikipedia.org/wiki/List_of_highest-paid_association_football_players` | **404** (wrong title, deprioritized — low yield vs Capology's actual coverage) | n/a |
| `football-observatory.com` (CIES) | 200 but not a wage source — deprioritized | n/a |

## What was acquired

### 1. Capology — grade-B, real reported salaries (the primary target)

Confirmed structurally simple: no login wall, no bot-detection JS, no browser
needed — each `salaries/<season>/` page embeds the full table as a plain JS array
literal (`var data = [{...}, ...]`, values wrapped in `accounting.formatMoney(...)`/
`moment(...)` calls), parsed with regex. Built `ingest/wages_capology.py`:
`fetch(confirm=True)` (resumable, rate-limited 1.2s/request, browser UA, retry/backoff,
skips cached files) → `build()` (parse cache, crosswalk, write CSVs).

**Site quirk found and fixed (would have silently corrupted results):** a
`salaries/<season>/` page for a season outside a league's real coverage doesn't
404 — Capology serves the *current* page's data back with HTTP 200. Verified
directly: a naive `uk/premier-league/salaries/2009-2010/` fetch contained "Erling
Haaland" (born 2000, 9 years old that season). Fixed by scoping season-discovery
to each league's own nav links only (was briefly polluted by an unrelated
"jump to club" dropdown for other leagues on the same page).

**Second quirk found and fixed:** Capology recycles its internal player ids across
different real players over time — id `34178` is `harry-kane` on one season's page
and `niklas-lomb` on another. A crosswalk keyed on bare `capology_id` silently
merged Harry Kane's wage history with a random Bayer Leverkusen player's TM id.
Fixed by keying on `(capology_id, normalised name)` instead — verified Kane now
resolves correctly (£409,985/wk, Bayern Munich, matches real reporting) and Niklas
Lomb resolves separately and correctly (tm 85543).

Crosswalk reuses `wages_fifa.crosswalk()`'s unique-name matching passes verbatim
(shaped the Capology frame to fit that function's interface) rather than
re-implementing name matching — its dob-based passes no-op (Capology has no dob)
and its unique-nname/unique-cname passes do the real work.

**Harvested — 8 leagues, fully open, real data:** Premier League, Championship,
La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga — each back to
**2013-2014** (Serie A to 2009-2010), 14 seasons deep, 2013→2025/26.

| Deliverable | Rows | Notes |
|---|---|---|
| `data/wages/capology_all_seasons.parquet` | 64,735 | every league-season row parsed, full history |
| `data/wages/capology.csv` | 14,593 | one row per player, **latest season only**, crosswalked, schema-compatible with `load_capology_csv()` |
| crosswalk hit rate | 83% | 17,514 unique players parsed → 14,593 matched to `tm_player_id` |
| `data/wages/capology_raw/*.html` | 130 pages, 271MB | cached raw pages — re-running `build()` is instant, no re-fetch |

**Hit a real, hard boundary — not a time-budget one:** the remaining 6 leagues
(`br/brasileiro`, `be/first-division-a`, `ar/primera-division`, `us/mls`,
`sa/saudi-pro-league`, `uk/scottish-premiership`) are **paywalled on Capology's own
free tier**. Verified directly: every salary field on those pages is the literal
string `<span class='footer-pro'>Locked</span>` instead of a `accounting.formatMoney(...)`
call — confirmed on all 8 cached Belgium season-pages, all 8 cached Brazil pages, and
Argentina's current page (0/0/0 rows parsed from all of them, by design — the parser
correctly refuses to fabricate a number from a lock icon). The 8 leagues that *are*
open (big-5 + Championship + Eredivisie + Portugal) are evidently Capology's public
marketing tier; everything else needs a paid "Pro" account, which is out of scope
under the personal/research-use, no-paid-signup rule in §0.3. This is a **discovered
fact about the source**, not a fetch failure — re-running the harvester will not
unlock more leagues without a subscription. Confirmed via:
```
python -m ingest.wages_capology fetch --yes   # resumable; would re-attempt the
                                                # same 6 leagues and find them still locked
python -m ingest.wages_capology build          # re-aggregate; a no-op for the locked leagues
```

### 2. FIFA prior — extended 2 editions → 5 editions, now a real time series

`ingest/wages_fifa.py`: confirmed editions 17-21 live at the existing GitHub-raw
mirror (15/16/22/23 → 404, not available there). Extended `FIFA_EDITIONS = [21,20,19,18,17]`,
`load_fifa(dedup=...)`, and added `build_timeseries()` (reuses the *same* crosswalk
mapping learned once from the latest-edition pass — sofifa_id is EA's persistent
cross-edition player id, so no re-matching needed per edition).

| | Before | After |
|---|---|---|
| Editions | 2 (2020, 2021) | 5 (2016/17 → 2020/21) |
| Players priced (`wages_fifa.parquet`) | 10,217 | **13,650** |
| Big-5 subset | 2,780 | **3,273** |
| Time series | none | `data/wages/wages_fifa_timeseries.parquet`, 40,290 rows, 13,663 players, **74% with ≥2 editions** |

### 3. Club wage-bill sanity cap — one verified anchor, PDF-OCR blocked at scale

Companies House is reachable (200) and Manchester City Football Club Limited
(company 00040946) was located and its latest filed accounts PDF downloaded. **Text
extraction failed** (`pypdf` recovered 39 characters from 39 pages — the filing is a
scanned/image PDF, not machine-readable text; OCR would be needed, a materially
bigger sub-project not attempted here). Used one independently-sourced, press-reported
top-down anchor instead (same evidentiary standard the codebase's own `ANCHORS` table
in `wages.py` already uses): Man City's **official 2022-23 total wage bill was
£422.9m** (first British club past £400m; widely reported, e.g. ESPN, from the
club's own published accounts).

**Cap-check:** summed Capology 2022-23 first-team wages for Man City = **£192.66m
(25 players)** = **45.6% of the official £422.9m total**. Player wages sit well
under the organisation-wide total (which also covers coaching/medical/scouting/
academy/executive staff plus employer NI and pension) — sane order of magnitude,
no red flag. **PASS** — the brief's "sum of player wages must not exceed the
reported bill" holds by a wide margin.

Residual gap: this is one club, one anchor, not a systematic multi-club cap. A real
multi-club Companies House pull needs OCR (or iXBRL for the minority of filers that
use it) and is more Lane C's territory per `STAGE11_revenue_dispersion_scope.md` —
flagged, not built here.

### 4. Deprioritized (thin yield vs. effort)

Spotrac (403, needs-residential), Wikipedia elite-tail list (wrong URL, and
Capology's Serie A/Bundesliga/Ligue1/PL/Championship/Eredivisie/Portugal coverage
already dwarfs what a hand-curated Wikipedia table would add), CIES Football
Observatory (reachable but not a wage source). None pursued further — Capology
already delivers comprehensively on the elite tail (Haaland, De Bruyne, Kane, Salah,
van Dijk all resolve to real current numbers).

## Reconciliation panel (real Capology vs FIFA-prior vs codebase's historical anchor)

`age`/`league`/`market_value` args are placeholders — the real number comes from
`tm_player_id` and ignores them (by design):

| Player | Codebase anchor (dated) | FIFA-prior (edition-frozen) | **Real (Capology, latest season)** | Real source |
|---|---|---|---|---|
| Harry Kane | ~£200k/wk (2020/21, Spurs) | £189,810/wk | **£409,985/wk** | Bayern Munich, 2025-26 |
| Kevin De Bruyne | ~£400k/wk (2021, Man City) | £269,418/wk | **£182,198/wk** | Napoli, 2025-26 (left Man City in 2025 on reduced terms) |
| Virgil van Dijk | ~£220k/wk (2020/21, Liverpool) | £190,587/wk | **£350,000/wk** | Liverpool, renewed since |
| Erling Haaland | ~£375k/wk (2023, Man City) | £51,933/wk (bad FIFA crosswalk/edition) | **£525,000/wk** | Man City, new Jan-2025 deal |
| Mohamed Salah | ~£350k/wk (2022, Liverpool) | no FIFA match | **£400,000/wk** | Liverpool, matches 2022 deal |

The gaps between the "anchor" column and the real Capology number are **real contract
events** (Kane and De Bruyne both actually transferred clubs since the anchors were
written), not estimation error — this is the whole point of a *current*, per-player,
per-season source over a frozen prior.

## Coverage lift (grade-B+C combined vs. grade-C-only baseline)

Against the 134,147-row canonical spine (19,952 unique players):

| | Before (FIFA-only) | After (Capology ∪ FIFA) | of which grade-B |
|---|---|---|---|
| **Overall** | 34.1% | **50.6%** | 46.0% |
| 2023 | 31.7% | 55.2% | 46.4% |
| 2024 | 30.3% | 55.3% | 46.4% |
| 2025 | 28.3% | 53.7% | 46.5% |
| 2026 | 22.1% | 54.3% | 49.1% |
| Premier League | 41.9% | 56.6% | 52.9% |
| Serie A | 40.8% | 58.9% | 56.3% |
| Ligue 1 | 41.3% | 57.2% | 53.4% |
| La Liga | 18.1-24.1%* | 49.4-83.7%* | 46.3-81.7%* |
| Bundesliga | 46.1% | 60.2% | 55.7% |
| Eredivisie | 71.7% | 88.8% | 83.6% |
| Liga Portugal | 43.8% | 73.3% | 62.3% |

\* two `to_league` label variants ("La Liga" vs "LaLiga") exist in the canonical
spine for the same league — a pre-existing spine data-quality issue, not introduced
here, flagged for whoever owns `ingest/merge.py`'s league-name normalisation.

**Recent seasons (2023-2026), the worst hole in Phase 0, roughly doubled coverage**
— exactly where the brief wanted the effort spent, since Capology's latest-season
data is current by construction while FIFA is permanently frozen at 2020/21.

## Integration status

`ingest/wages.py::estimate_wage(..., tm_player_id=...)` now checks, in order:
1. **Capology** (`source='capology_estimate'`, grade-B, interval x/÷1.15 — tight,
   real reported figure, excludes bonuses/image rights)
2. **FIFA prior** (`source='fifa_prior'`, grade-C, interval x/÷1.6)
3. **Parametric model** (`source='modelled'`, grade-C/D, interval x/÷1.55-1.9)

Existing positional callers (no `tm_player_id`) are untouched — same numbers as
before, verified by the existing gate-1 self-check.

## Self-checks (all PASS)

```
$ python -m ingest.wages
fifa_prior path ok (tm 40608: £94,365/wk)
capology_estimate path ok (tm 19712: £9,246/wk, beats fifa_prior when both exist)
K_EPL = £635,986/yr per MV^0.75 at peak age
27yo EPL €80m MF: £300,988/wk  [£194,186 - £466,532]  source=modelled
ok

$ python -m ingest.wages_fifa      # crosswalk + blend + fallback all ok
$ python -m ingest.wages_capology  # parser + season-sort ok (offline, no network)
```

The brief's exact self-check — "a player with a Capology row must return the real
number, not the FIFA prior" — is both unit-tested (`ingest/wages.py` test #10, uses
the real `data/wages/capology.csv` on disk) and manually verified above (Kane,
De Bruyne, van Dijk, Haaland, Salah all resolve to `capology_estimate`, not
`fifa_prior`).

## Residual holes (best available grade per segment, after everything above)

| Segment | Best grade | Note |
|---|---|---|
| Big-5 + Championship + Eredivisie + Portugal, 2013-2026, players who stayed in those leagues | **B** (Capology) | real, current |
| Big-5-adjacent players active 2016/17-2020/21 but not in a fetched-league's current squad | **C** (FIFA, now 5-edition series) | dated but has a trajectory |
| Brazil, Belgium, Argentina, MLS, Saudi Pro League, Scotland | **C/D only** (Capology paywalled, confirmed — see above) | FIFA prior covers MLS/Argentina somewhat (FIFA includes those leagues); Brazil/Belgium/Saudi/Scotland fall to the parametric model |
| Everyone else (lower non-fetched leagues, very young/fringe players) | **D** (parametric model) | unchanged, always flagged |
| Club-level top-down cap-check | **1 anchor** (Man City, official accounts, press-cited) | multi-club needs OCR or iXBRL — not attempted, flagged for a future pass or Lane C |

## Verdict

Wages moved from a single grade-C proxy to a **stacked, best-grade-first real-wage
layer** — this is the grade jump the brief asked for, not just a cosmetic
relabelling: 46% of the canonical spine's player-transfer rows now carry a *real,
current, per-player reported salary* (Capology), not a 2020/21-frozen game estimate.
The FIFA layer got wider and deeper too (2→5 editions, a real time series) as the
grade-C fallback for everyone Capology doesn't reach yet. The weakest point *before*
this pass — recent transfers (2023-2026) — saw the biggest lift (roughly 2x). It is
still weak on Brazil/Belgium/Argentina/MLS/Saudi/Scotland — confirmed **paywalled**
on Capology's free tier rather than merely unfetched, a real finding worth recording
so nobody re-runs the harvester expecting a different outcome — and on a systematic
multi-club wage-bill cap (one anchor only, PDF-OCR needed for more). Nothing here was
fabricated: every count above is a live query against the files on disk at write
time, and every "0 rows" is a page that was actually inspected, not skipped.
