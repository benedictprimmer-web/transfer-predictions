# DATA ACQUISITION PLAN — selling leagues, niche data, and researching other countries

*2026-07-12. Commercial constraints dropped (personal/research use), so this is purely: **where does the data live, can we reach it, and how does it plug into the machinery we just built.** Reachability claims below were tested from this environment — that egress constraint is the whole game and has been since FBref died.*

---

## 1. The gap, ranked by YOUR funnel

Not a generic "add more leagues" list — this is where Big-5 clubs actually buy from, computed from `transfers_canonical` (paid moves into a top-5 club, by origin):

| Priority | Feeder | Paid moves→Big5 | Avg fee | Our xG today | Notes |
|---|---|---|---|---|---|
| **1** | **Portugal** (Liga Portugal) | 242 | €9.6m | ✗ | highest-value feeder; Núñez/Darwin/Fernández pipeline |
| **1** | **Netherlands** (Eredivisie) | 185 | €8.2m | ✗ | Antony/Timber/Gakpo pipeline |
| **1** | **England 2nd tier** (Championship) | (in "England") | — | ✗ | biggest single non-top-flight market |
| **2** | **Brazil** (Série A) | 177 | €7.1m | ✗ | calendar-year season; heavy scouting |
| **2** | **Belgium** (Pro League) | 154 | €5.8m | ✗ | Openda/Doku/Lukebakio |
| **2** | **Argentina** (Primera) | 132 | €4.6m | ✗ | calendar-year; Garnacho/Álvarez |
| **2** | **Russia** (RPL) | 91 | €5.5m | **✓** | *already have via Understat* |
| **3** | Switzerland, Turkey, Austria, Greece, Croatia, Ukraine, Denmark | 60–100 each | €3–7m | ✗ | Austria (RB Salzburg) punches above weight |
| **3** | 2nd tiers: Ligue 2, 2.Bundesliga, Serie B | — | — | ✗ | same-country crosswalk is easiest |
| **4** | Scandinavia (DEN/SWE/NOR), Uruguay, Serbia, Scotland, Poland, Czech | 39–68 each | €2–5m | ✗ | Scandinavia = calendar-year; low fees, high churn |

**Takeaway:** eight feeders (Portugal, Netherlands, Championship, Brazil, Belgium, Argentina, + Switzerland/Austria) cover the overwhelming majority of realistic inbound value. Solve those and the coverage gap is effectively closed. Russia you already have.

---

## 2. Reachability reality (tested from this environment)

The sandbox egresses through a datacenter IP, so the aggressive anti-bot sites block us exactly as FBref does. This dictates the *method*, not just the source.

| Source | What it has | From sandbox | Verdict |
|---|---|---|---|
| **GitHub raw / API** | pre-scraped `.rds`/`.csv` dumps, StatsBomb open-data | ✓ 200 | **primary channel** |
| **api.clubelo.com** | Elo, every club/country, to 1939 | ✓ 200 | done (P1-7) |
| **TM R2 mirror** | fees/values/minutes, 48 comps incl. all feeders | ✓ 200 | have it |
| **understat.com** | xG+coords — but only 6 leagues, no feeders | ✓ 200 | maxed out |
| **football-data.co.uk** | results + odds, ~22 leagues, **no xG** | ✓ 200 | useful for priors, not xG |
| **FBref (Opta)** | stats for 20+ leagues; lost xG Jan 2025 anyway | ✗ 403 | dead here and degraded |
| **SofaScore API** | xG+shotmaps, ~30 leagues | ✗ 403 (Cloudflare) | residential-only |
| **FotMob API** | xG+shotmaps, 500+ leagues incl. every feeder | ✗ token-gated (`x-mas`) | residential-only |

**The one hard truth:** selling-league **shot xG+coordinates** — the fuel our `xg_model.py` needs — lives in FotMob and SofaScore, and both are unreachable from this sandbox. That is the real blocker, and it's a *network egress* blocker, not a data-existence one. Two ways around it (§4).

---

## 3. Source map by data type (what feeds which part of the stack)

| Niche need | Feeds | Best free source | Coverage | Reach |
|---|---|---|---|---|
| **Shot xG + X/Y coords** | `xg_model.py`, usage/efficiency | **FotMob** (own xG model) | ~500 leagues, all feeders, ~2016+ | ⚠ residential |
| ” (alt) | ” | **SofaScore** | ~30 leagues | ⚠ residential |
| ” (deep, free) | ” | **StatsBomb open-data** | narrow: some comps/seasons, but *full events + coords* | ✓ GitHub |
| **Defensive/progression events** | blind-spot axis (`fbref_defense`) | FBref (frozen snapshot) / FotMob | Big-5 have it; feeders via FotMob | ⚠ residential |
| **Fees / values / minutes** | fees, NPV, usage denominator | **Transfermarkt** (R2 mirror) | 48 comps, all feeders | ✓ have it |
| **Contracts / expiry / agent** | free-transfer scouting | TM `players.csv` | 63% (global) | ✓ have it |
| **Wages** | NPV cost side (biggest uncertainty) | **Capology** (scrape) | Big-5 + a few; feeders thin | ⚠ residential |
| **Injuries / availability** | risk/durability | Transfermarkt injury history | broad | ⚠ scrape TM |
| **Youth / academy / U21** | prospect scouting | TM youth pages, some FBref | patchy | ⚠ scrape |
| **League strength prior** | cross-league conversion | **ClubElo** | every country, to 1939 | ✓ done |

---

## 4. The acquisition playbook (3 tiers, in order of laziness)

**Tier 1 — pre-scraped dumps (pullable from the sandbox today).**
Someone has usually already scraped it and dropped it on GitHub/Kaggle. Reachable here.
- `worldfootballR_data` (GitHub, JaseZiv) — the repo we already pull; enumerate its `data/` + `raw-data/` for any feeder dumps beyond Big-5 before scraping anything.
- **StatsBomb open-data** (GitHub) — `statsbombpy`/`mplsoccer` read it; full events with coordinates. Narrow competition list but it feeds `xg_model.py` *directly* (same geometry) and needs no residential IP. Best zero-friction win for *some* extra coverage.
- Kaggle: search "Eredivisie/Championship/Brazil shots xG"; many one-off dumps exist (CC0). Kaggle downloads work from here with an API token.

**Tier 2 — residential-IP scraper (the real answer for feeder xG).**
FotMob/SofaScore block the datacenter but not a home connection. The pattern that already works in this project (user runs the network step, we ingest the output):
- Generate a small scraper using **`ScraperFC`** (Python: FotMob + SofaScore + Understat shot data) or **`worldfootballR`** (R: `fotmob_get_match_details` returns a shotmap with `x`, `y`, `expectedGoals`).
- **You run it in your own terminal** (residential IP) for the target leagues → it writes `.parquet`/`.csv` → we ingest with a module that mirrors `ingest/understat.py`.
- FotMob's `x-mas` token is derivable (ScraperFC/worldfootballR handle it); from a home IP it just works.
- Output slots straight into the geometry model — FotMob shot coords are normalized like Understat's.

**Tier 3 — keyed free-tier APIs (fallback / recent seasons).**
- **football-data.org** — free key, clean, but **no xG** (fixtures/lineups/scorers only). Good for the identity/results layer of obscure leagues.
- **API-Football (RapidAPI)** — free tier ~100 req/day; has some xG on higher tiers. Fine for backfilling a specific league's recent season.
- These are reachable from the sandbox (they're built for API access, no bot-blocking).

---

## 5. Integration — why new leagues are cheap now

The build we just finished is what makes this tractable. Each new feeder league is the same three steps, already coded:

1. **Land shots** with `x, y, xg, shot_type, player, player_id` → a new `ingest/<source>.py` mirroring `understat.py::tidy_shots` (same 18-col schema).
2. **Crosswalk to TM** — reuse `ingest/crosswalk_players.py` verbatim: it matches on normalized name within (league, season), disambiguated by club. Works for any league whose players are in the TM dump (all 48 comps are).
3. **Score + join** — `impact/xg_model.py` already scores any shot with coordinates; `players_master` + `warehouse` absorb the new ids with no schema change.

So the marginal cost of a league is: one tidy function + a residential scrape. The identity spine, the xG model, the defensive join, the contract join, the audit contracts — all already generalize.

**One gotcha to code once:** the geometry xG model is currently fit on Understat coords. FotMob/SofaScore use their own coordinate normalization — add a per-source coordinate transform in `geometry()` (a 5-line affine map) and refit/validate per source. The `_check()` harness is already there.

---

## 6. General methodology — researching football data in a new country

The transferable playbook, learned the hard way on this project:

1. **Test egress before you plan.** The first question is never "does the data exist" — it's "can *this* machine reach it." One `curl -o /dev/null -w "%{http_code}"` per candidate saves days. Datacenter IPs get 403'd by FBref/SofaScore/Cloudflare; residential don't. Know which you're on.

2. **Anchor on the ID backbone, then hang stats off it.** Transfermarkt covers virtually every country and is your `player_id` spine. Find the *stats* source second and crosswalk by (normalized name, club, season) — never try to make the stats source your identity source. This is exactly what `crosswalk_players.py` does; it generalizes.

3. **Prefer a dump to a scrape, a scrape to an API, an API to a payment** — but test reachability at each rung (the ladder is useless if rung 1 is 403'd here). Community dumps (GitHub/Kaggle) are usually 1–2 years stale but zero-friction and legal-enough for research.

4. **Season-calendar landmines.** Big-5 = Aug→May. But **Brazil, Argentina, MLS, Scandinavia (SWE/NOR/DEN), Russia (historically), Ireland, Japan, K-League run calendar-year (Feb/Mar→Nov)**. A naive `season = start_year` mapping silently misaligns every join. Handle per-league.

5. **Name matching degrades outside Latin script.** Diacritics (Portuguese/Croatian), transliteration (Russian/Ukrainian/Serbian Cyrillic → multiple Latin spellings), single-name players (Brazil: "Hulk", "Fred"), and Spanish/Portuguese compound surnames all break exact match. `norm_player()` handles diacritics; for Cyrillic/Brazilian you'll want the TM-id anchor (step 2) rather than name match, plus a fuzzy fallback.

6. **Tier and promotion structure.** ClubElo/`Level` and TM `competition tier` disagree in some countries; a "second division" in one country is stronger than a "first" in another (Championship > many top flights). Use ClubElo, not nominal tier, for strength — you already have the full history.

7. **Coverage honesty per country.** Free xG basically exists for: Big-5 + top ~30 leagues via FotMob/SofaScore (residential), and a handful via StatsBomb (deep, free, narrow). Below that (most of Africa, most of Asia, lower South America) there is **no free shot data at all** — the geometry model has nothing to score, and that's a real wall, not a sourcing gap. Say so rather than fake coverage.

---

## 7. Concrete first sprint (highest value, least friction)

1. **Zero-friction win:** enumerate `worldfootballR_data/data` + pull **StatsBomb open-data** via `statsbombpy` → run `xg_model.geometry()` on it (coords already there) → validate our xG on a non-Understat source. Proves the multi-source pipeline end-to-end from the sandbox, no residential step.
2. **Biggest coverage win:** a `ScraperFC`/`worldfootballR` FotMob scraper for **Portugal + Eredivisie + Championship** (your top-3 feeders), 2016→now. You run it once on your home connection (~an evening of pulls); we ingest via a new `ingest/fotmob.py` and the existing crosswalk/model absorb it.
3. **Then** Brazil + Belgium + Argentina (mind the calendar-year season) to cover the next tier.

After sprint 2 you'd have xG-based scouting for the leagues that supply ~70% of realistic inbound signings — the coverage gap the audit flagged as the #1 limit, effectively closed.
