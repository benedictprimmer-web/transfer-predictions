# Deep-research prompt — data sources for a football transfer valuation system

*Paste everything below the line into a deep-research tool. It is self-contained.*

---

You are a data-sourcing researcher. I am building a football (soccer) transfer valuation system and need to assemble the highest-quality **freely obtainable** dataset before writing analysis code. Your job is to find, verify, and rank concrete data sources for each data area listed below — real datasets with real identifiers (Kaggle dataset slugs, GitHub repos, Zenodo/figshare DOIs, API endpoints), not general advice.

## Hard access constraint — read first, it eliminates most obvious answers

My data pipeline runs from **cloud / datacenter IP addresses**. Two of the canonical sources actively block these:

- **FBref.com** returns HTTP 403 (Cloudflare) to any datacenter IP, on every request.
- **Transfermarkt.com** live scraping is similarly hostile and against ToS.

So I **cannot** live-scrape those sites. I therefore need, in order of preference:

1. **Static downloadable dumps** of the underlying data — Kaggle datasets, GitHub repos, Zenodo/figshare archives, university data releases. A mirror of FBref/Transfermarkt/Understat data as a file is fine; live-scraping the site is not.
2. **APIs or file endpoints that do NOT block datacenter IPs.** For every API you propose, state explicitly whether it is known to serve datacenter/cloud IPs (e.g. AWS, GCP), or flag it as "unverified — may block."

For each source, tell me which category it falls in. Treat "you can scrape FBref" as a wrong answer.

## What the system does (context for judging relevance)

It prices a transfer in money: cost = amortised fee + wages per season; benefit = the team winning more, converted to revenue; net present value is the verdict. The analytical core is a **usage-and-efficiency model**: a player's share of his team's terminal actions (shots, shot-assists, turnovers) while on the pitch, and the value he produces per action. This is validated against **WOWY** (team xG difference with a player on vs off the pitch). Because of that, **shot-level and minute-level granularity matters far more than season-total stats.**

## Coverage target

- **Leagues:** the big 5 (England, Spain, Italy, Germany, France) as the confident core, plus "selling leagues" (English Championship, Dutch Eredivisie, Portuguese Primeira Liga, and — lower priority — Liga MX and Brazilian Série A).
- **Seasons:** 2015-16 through 2024-25 (~10 seasons). Note xG generally only exists from ~2017-18; earlier is a bonus, not required.

## Data areas needed (find the best source for each)

For each area, granularity requirements are strict — say clearly whether a source meets them.

1. **Shot events with xG.** Per shot: minute, team, player, xG value, and ideally shot type/outcome. This drives xG, WOWY, and efficiency. *(Prime lead to verify: Understat — shot-level xG, top-5 leagues + RFPL from 2014-15. Find the best-maintained Kaggle/GitHub dump AND confirm whether the Understat API/site serves datacenter IPs. Also assess StatsBomb open data's actual league-season coverage.)*
2. **Lineups and minutes played.** Per match, per player: starter/sub and minutes on the pitch. Required to compute on-pitch vs off-pitch windows for WOWY and usage denominators.
3. **Player per-90 stats for the usage metric.** Specifically shots, shot-assists (the pass leading to a shot), and **turnovers — times dispossessed and miscontrols**. The turnover components are the hardest to source outside FBref/Opta and are essential; flag any event-level dataset (e.g. Wyscout/SciSports/StatsBomb open, the Pappalardo et al. "Soccer logs" figshare release) that contains dispossessions/losses so I can derive them.
4. **Transfers: fees, market values, contracts.** Per transfer: fee, player market value at the time, dates, from/to club, contract length. *(Known lead: the Kaggle `davidcariboo/player-scores` Transfermarkt dump — confirm it's current, list its files/columns, note the "undisclosed fee = 0/null" gap. Find alternatives/supplements.)*
5. **Player wages / salaries.** Estimated annual wages, ideally top-5 leagues. *(Leads: Capology, Spotrac. Find any static dump; assess how their estimates are derived and how reliable they are. These are estimates, not filings — I need to know how much to trust them.)*
6. **League strength prior.** A cross-league team-rating time series. *(Lead: ClubElo — free API/CSV. Confirm access from datacenter IPs and coverage of the leagues above. Find alternatives.)*
7. **Team tactical-style stats.** Per team-season: possession share, PPDA (pressing intensity), directness, width — for a style-cluster feature. Where does this exist as a download?
8. **Prize money & Champions League revenue (primary sources).** Premier League merit payments per finishing place and central distribution; UEFA Champions League revenue breakdown (participation, performance, market pool, coefficient/"value pillar"). I need **exact published figures from primary documents** (Premier League financial reports, UEFA distribution circulars), not blog estimates — this is the single largest coefficient in the model. Give me the actual numbers and cite the source document and year.

## For every source you recommend, report

- Exact identifier (Kaggle slug / GitHub URL / DOI / API base URL) and how to download.
- Which data areas above it covers, and at what granularity (does it have shot-level xG? minutes? turnovers?).
- League + season coverage, and known gaps.
- **Access category** (static dump / datacenter-safe API / IP-blocking risk).
- Format (CSV/parquet/JSON), approximate size, last-updated date, and update cadence.
- **Licence** and whether redistribution/derivative use is allowed.
- A trust grade A–F with one line of justification.

## Deliverables

1. A **ranked table per data area** (best source first).
2. A recommended **"starter stack"**: the minimum set of sources that together cover shot xG + minutes + usage components + transfers + wages for the big-5, 2017-2025, maximizing coverage with the fewest, most reliable, datacenter-safe sources.
3. An explicit **gaps list**: what none of the free, accessible sources provide (I expect turnover/dispossession data and reliable wages to be the weak points) and the least-bad workaround for each.
4. The **prize-money / CL-revenue figures** from area 8, with primary-source citations.

Verify that each recommended source is currently live and downloadable before listing it. Prefer primary and well-maintained sources; flag anything stale, abandoned, or licence-encumbered. Cite everything.
