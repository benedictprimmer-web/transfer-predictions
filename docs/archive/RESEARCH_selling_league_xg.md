# SELLING-LEAGUE xG — 6-scout fan-out results

*2026-07-12. Six agents, six channels, hunting shot/xG data for Eredivisie, Liga Portugal, EFL Championship, Brazil Série A — from this datacenter-IP environment. Every finding below was reachability-tested and sample-verified, not assumed.*

## The answer

**We found it, and it's reachable from here.** `worldfootballR_data` caches FBref shot-level data as static **GitHub release assets** (`.../releases/download/fb_match_shooting/{CTRY}_{GENDER}_{TIER}_match_shooting.rds`). Release-asset downloads are static files — **not** subject to the FBref/FotMob/SofaScore live IP-block. All four leagues, ~235k shots, ~100% with xG. **Built into `ingest/fbref_shots.py`.**

| League | Shots | Seasons | xG | Coords |
|---|---|---|---|---|
| EFL Championship | 88,084 | 2019–2025 | ✓ | ✗ (Distance only) |
| Brazil Série A | 55,146 | 2019–2024 | ✓ | ✗ |
| Liga Portugal | 47,447 | 2019–2025 | ✓ | ✗ |
| Eredivisie | 44,129 | 2019–22, 2024–25 (2023 gap) | ✓ | ✗ |

Granularity = FBref shooting table: **xG + PSxG + Distance + Body Part + shot-creating-action chains + Player_Href**. That last one is an `fbref_id`, so it joins straight into the `players_master` bridge → TM ids → the whole stack. No pitch coordinates, but it *has* xG, so we use FBref's directly (our geometry model isn't needed here).

## What each scout found

| Scout | Channel | Result |
|---|---|---|
| **Lateral** | Wayback/HF/Zenodo/R-pkgs | 🏆 **the winner** — worldfootballR_data release assets, all 4 leagues verified |
| **GitHub** | code/repo search | No committed shot-*dump* for 3 of 4 (only Brazil, partial). Confirmed the negative; handed over the FotMob league-id map (Eredivisie 57, Liga Portugal 61, Championship 48, Brazil 268) for a future residential FotMob pull |
| **Live feeds** | APIs not blocking datacenter | **API-Football** (`v3.football.api-sports.io`) is *not* IP-blocked — its 403 is app-auth; a free key (100/day) returns **team-level xG + shot counts for all 4**. TheSportsDB gives shot counts with no key |
| **Build-our-own** | shot counts / coords | **football-data.co.uk** serves team shot counts for Championship (2000+), Eredivisie & Portugal (2018-19+) — not Brazil. Delivered a full coordinate-conversion table (every provider → our 0..1 frame) for any future coord source |
| **Kaggle** | community datasets | No shot-level, but player-season **aggregate xG**: Brazil (MIT), Eredivisie & Portugal; needs your `~/.kaggle/kaggle.json` to pull |
| **Open corpora** | StatsBomb/Wyscout/Metrica/SkillCorner | **None of the 4 leagues** — all elite-Europe or teaching samples. Clean negative |

## The tiered picture (what gets you what)

1. **Shot-level xG + player, all 4 leagues — REACHABLE NOW, built.** worldfootballR_data release assets → `ingest/fbref_shots.py`. This is the coverage gap closed. Caveat: static snapshots (refresh when maintainer re-scrapes), Eredivisie 2023 missing, no pitch coordinates.
2. **Team-level xG, live/refreshable.** API-Football free key (all 4) or football-data.co.uk shot counts (3 of 4). Use for recency/ongoing seasons the frozen dump lags.
3. **Pitch coordinates (to feed our geometry model / positional work).** Not free-reachable for these leagues from any channel. Only a **residential** ScraperFC(SofaScore)/worldfootballR(FotMob) run gets true X/Y — and the coordinate-conversion table is ready for when it does. This is a nice-to-have; we don't need it, because layer 1 already has xG.

## Bottom line
The four selling leagues that feed ~70% of realistic inbound signings now have **shot-level xG keyed to your player ids**, sourced entirely from this environment. Live team-xG (API-Football) and player-aggregate xG (Kaggle) are backups for recency. Pitch coordinates are the only thing still needing a residential pull, and they're optional.
