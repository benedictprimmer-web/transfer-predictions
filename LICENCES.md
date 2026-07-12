# Data licences & provenance audit

Audit date: 2026-07-12. Purpose: this project is heading toward a **commercial**
scouting product. Several inputs are fine for private research but **not** licensed
for commercial redistribution. This file records, per source, what the licence
actually says and where the commercial risk sits. Every claim carries a URL.

**One structural point up front.** Most "advanced" data here is pulled from
convenience mirrors — `JaseZiv/worldfootballR_data` (`.rds` dumps),
`dcaribou/transfermarkt-datasets` (R2 CSVs), `tonyelhabr/club-rankings` (a ClubElo
scrape). A mirror's own repo licence (e.g. `worldfootballR` is GPL-3) covers the
*code and the packaging*, **not** the underlying facts. The licence that binds a
commercial product is the **upstream source's** terms (StatsBomb, Understat,
Transfermarkt, Opta). A CC0 tag or a GPL repo on a scraper does not launder
proprietary or non-commercial source data. Treat every row below by its *origin*,
not its mirror.

---

## Summary table

| Source | What it feeds | Licence / terms | Commercial use? | Attribution required | Notes / risk |
|---|---|---|---|---|---|
| **StatsBomb open-data** (`data/statsbomb/`, `ingest/statsbomb.py`) | Turnovers (Dispossessed/Miscontrol), lineups on covered seasons | Public Data **User Agreement** (LICENSE.pdf) | **No — non-commercial only** | **Yes** — name "StatsBomb" + logo | **BLOCKER #1.** Explicitly non-commercial. Must be removed or a commercial licence bought before selling. |
| **Understat** (via `worldfootballR_data/understat_shots/*.rds`, `ingest/understat.py`) | Primary xG + usage engine | No formal published licence; scraped site data | **Ambiguous → treat as No** | Expected (be polite / attribute) | **BLOCKER #2 (joint).** Owner e-mail (2018) OK'd *non-commercial* use only; commercial reuse needs a licence. Underlying stats are Understat's, not the mirror's. |
| **Transfermarkt** (via `dcaribou/transfermarkt-datasets` R2 mirror → upstream Kaggle `davidcariboo/player-scores`, `ingest/transfermarkt.py`) | Fees, market values, minutes, lineups | Mirror tagged **CC0-1.0**; underlying data is **Transfermarkt's**, whose site ToS forbid scraping/commercial reuse | **Ambiguous → high risk** | CC0 says none; TM would say yes | **BLOCKER #2 (joint).** CC0 tag cannot relicense Transfermarkt's proprietary DB. Selling on it invites a TM ToS / DB-rights claim. |
| **ClubElo** (`api.clubelo.com` + `tonyelhabr/club-rankings` mirror, `ingest/strength.py`) | League-strength prior | **No formal licence found** (site unreachable from this env) | **Unknown — must confirm** | Attribution customary | Historically free-to-use-with-attribution for research; commercial terms not documented. Contact operator (Lars, @clubelo) before commercial use. |
| **FBref / Opta snapshot** (frozen `worldfootballR_data/fb_big5_advanced_season_stats/*`, `ingest/fbref_snapshot.py`; live `ingest/fbref.py` unused — blocked) | Turnover snapshot 2017/18–2022/23 | Data is **Opta / Stats Perform proprietary**; Sports-Reference ToU restricts bulk/commercial use | **No** | Opta/Stats Perform | High risk. This is a frozen copy of proprietary Opta data that Stats Perform pulled off FBref in Jan 2025. Not yours to sell. Remove for commercial. |
| **worldfootballR_data big-5 `.rds`** | (same frozen FBref/Opta snapshot as above) | See FBref/Opta row | **No** | — | Same source, different framing. The `.rds` packaging is GPL-adjacent; the *facts* are Opta's. |
| **UEFA / Premier League revenue figures** (`DATA_SOURCES.md`, hard-coded in `money/`) | Prize-money / NPV coefficients | Facts from primary UEFA circulars + PL press releases | **Yes (facts)** | Cite source docs | Low risk. Individual factual figures aren't copyrightable; don't lift UEFA's tables/prose verbatim. |
| **Wages** (`ingest/wages.py`) | Wage estimates | Own parametric model; no external data shipped | **Yes (own model)** | — | Low risk *as shipped*. The documented upgrade paths (Capology/Spotrac scrape, FIFA/FM Kaggle) are **not** redistributable — do not add them to a product. |

Grades of confidence: StatsBomb and FBref/Opta rows are firm. Understat, Transfermarkt
and ClubElo rows are **genuinely ambiguous** and are flagged as such below — do not
read "ambiguous" as "probably fine".

---

## Per-source detail

### StatsBomb open-data — non-commercial, attribution + logo
The data is "freely available for public **non-commercial** use" and its use "is
subject to a user agreement"; anyone publishing derived work must "state the data
source as StatsBomb and use their logo." The binding document is the
`LICENSE.pdf` (Public Data User Agreement) in the repo, which users agree to by
using the repository.
- Repo + README: https://github.com/statsbomb/open-data
- Licence file: https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf
- Third-party confirmation of the non-commercial + logo terms: https://socceraction.readthedocs.io/en/latest/documentation/data/statsbomb.html

**Verdict: non-commercial only.** Cannot be included in a product sold for money
without a separate commercial agreement with StatsBomb/Hudl.

### Understat — scraped, no formal licence, non-commercial by the owner's word
Understat publishes no open-data licence. The community's standing understanding
comes from an owner e-mail exchange (8 Nov 2018) confirming the data is free for
**non-commercial** purposes, "subject to change", with attribution expected;
commercial or heavy use needs licensing. We consume it via the
`worldfootballR_data` `.rds` dump, but the mirror does not own or relicense the
figures — they remain Understat's.
- Mirror we use: https://github.com/JaseZiv/worldfootballR_data (path `data/understat_shots/`)
- Community summary of the non-commercial e-mail confirmation + attribution norm: https://github.com/collinb9/understatAPI  and  https://footballdotpy.medium.com/scrape-a-whole-leagues-worth-of-shot-and-xg-data-from-understat-75f1f112e874

**Verdict: ambiguous, lean non-commercial.** No document grants commercial rights.
Get written permission or a licence from Understat before selling on its xG.

### Transfermarkt — CC0 mirror over proprietary source (the tension)
The pipeline reads the `dcaribou/transfermarkt-datasets` project, which is tagged
**CC0-1.0** and republishes the Kaggle dataset `davidcariboo/player-scores` (also
CC0) as public R2 CSVs. **But** CC0 is a dedication the *scraper's author* has no
standing to make over Transfermarkt's underlying database: the fees, valuations
and appearances are Transfermarkt's own content, gathered against Transfermarkt's
site terms (which prohibit automated collection and commercial reuse). The project
itself carries no statement reconciling this — it "simply identifies itself as
extracting data from Transfermarkt" with no permission claim.
- Mirror/project + CC0 tag: https://github.com/dcaribou/transfermarkt-datasets
- Upstream Kaggle dataset (CC0): https://www.kaggle.com/datasets/davidcariboo/player-scores

**Verdict: high commercial risk.** The CC0 label does not bind Transfermarkt.
Building a paid product on scraped Transfermarkt data exposes you to a ToS /
database-right claim. Needs a licensed data source or Transfermarkt's own API/permission.

### ClubElo — terms not formally published (and unreachable from here)
ClubElo (run by Lars, @clubelo) provides Elo ratings via `api.clubelo.com`; we read
the daily `tonyelhabr/club-rankings` GitHub mirror because the API times out from
this environment. Neither the ClubElo site (`clubelo.com/Data`, unreachable from
this datacenter IP at audit time), the soccerdata docs, nor the mirror publishes a
formal licence. ClubElo's long-standing practice is free use for research with
attribution; **commercial** terms are undocumented.
- API / data page (could not be fetched here): http://clubelo.com/Data
- Mirror we use: https://github.com/tonyelhabr/club-rankings
- soccerdata reference (no licence stated): https://soccerdata.readthedocs.io/en/latest/datasources/ClubElo.html

**Verdict: unknown — must confirm.** Do not assume commercial use is granted.
Contact the ClubElo operator for a commercial-use position before shipping.

### FBref / Opta / Stats Perform — proprietary, and the well is poisoned
FBref's advanced stats were **Opta (Stats Perform)** data under a partnership.
Stats Perform terminated FBref's feed and forced removal of all advanced stats in
**January 2025**, alleging FBref breached their agreement. Sports Reference's own
terms of use restrict bulk extraction and commercial reuse. This project only
holds a **frozen pre-takedown snapshot** (2017/18–2022/23) via `worldfootballR_data`
— which is a copy of proprietary Opta data that its owner has since pulled from
public circulation.
- Removal / termination context: https://www.sports-reference.com/blog/2026/01/fbref-stathead-data-update/
- Data-partner background (Opta replaced StatsBomb on FBref): https://www.sports-reference.com/blog/2022/10/fbref-leagues-%F0%9F%87%B5%F0%9F%87%B9-leagues-%F0%9F%87%A7%F0%9F%87%B7-leagues-%F0%9F%87%B2%F0%9F%87%BD-expanded-womens-and-mens-data-new-data-partner/
- Snapshot source path: https://github.com/JaseZiv/worldfootballR_data (path `data/fb_big5_advanced_season_stats/`)

**Verdict: not licensable by us.** Remove from any commercial build. (Note the live
`ingest/fbref.py` path is already unused — datacenter IPs are 403'd and the feed is
gone regardless.)

### UEFA / Premier League revenue figures — factual, low risk
The prize-money and central-payment figures in `DATA_SOURCES.md` (and hard-coded in
`money/`) are individual facts drawn from primary UEFA circulars and Premier League
press releases. Facts aren't copyrightable; the risk is only in reproducing UEFA's
tables or prose verbatim, which we don't.
- Sources are UEFA Circular 13/2024 and premierleague.com financial releases (cited inline in `DATA_SOURCES.md`).

**Verdict: safe as facts.** Keep citing the primary docs; don't paste their tables.

### Wages — own model, safe; documented upgrades are not
`ingest/wages.py` ships a **parametric model**, not third-party data, so nothing to
license there. The upgrade paths it documents (a manual Capology/Spotrac snapshot;
Kaggle FIFA/FM salary files) are third-party **estimates not licensed for
redistribution** — usable privately, but do not fold them into a sold product.
- Module docstring: `ingest/wages.py`.

**Verdict: safe as shipped.** Keep the non-redistributable proxies out of any product build.

---

## Commercial-product risk assessment

Before anything is **sold**, these must be resolved. Ranked by severity:

1. **StatsBomb open-data — MUST REMOVE or LICENSE (hard blocker).** The User
   Agreement is explicitly non-commercial. There is no reading of it that permits a
   paid product. Either drop the StatsBomb turnover/WOWY inputs or buy a StatsBomb
   commercial licence. This is the headline blocker.

2. **Transfermarkt — MUST RELICENSE (hard blocker).** Fees, valuations and minutes
   are the money layer's backbone, and they come from a CC0-tagged scrape of
   Transfermarkt's proprietary database. The CC0 tag does not bind Transfermarkt.
   Selling on it risks a ToS / database-right claim. Needs a licensed feed
   (Transfermarkt API/partnership or a paid provider) before commercialisation.

3. **FBref / Opta snapshot — REMOVE.** Proprietary Opta data that Stats Perform has
   already forced off the public web. Not licensable by us at any price we'd pay;
   strip the `fbref_snapshot` inputs from the commercial build.

4. **Understat — CONFIRM or REPLACE.** The de facto position is non-commercial. The
   xG engine is central, so this is a real dependency: get explicit permission from
   Understat, or move to a licensed xG source, before selling.

5. **ClubElo — CONFIRM.** Lower volume (a strength prior), but terms are
   undocumented. Get the operator's commercial-use position in writing; cheap to
   resolve, cheap to replace if refused.

Low/no risk: UEFA/PL revenue **facts** (keep citing primaries), and the **wage
model** (own work — just don't add the non-redistributable Capology/FIFA proxies).

**Bottom line:** as built, the stack is a sound *research* system but is **not
sellable** without action on at least items 1–4. Two of its three core engines
(xG = Understat, money = Transfermarkt) plus the turnover input (StatsBomb) each
carry a commercial-use problem. A commercial version needs licensed replacements
for the money and xG layers and removal of the StatsBomb and FBref/Opta inputs.
