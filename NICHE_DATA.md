# NICHE DATA — the hard-to-find side stats, and where each one actually is

*2026-07-12. The "obscure" stats scouts pay for. Three layers, in order of laziness: (1) already on your disk, untapped; (2) computable from event data you already have — nobody publishes these because you derive them; (3) open/GitHub sources for what's genuinely missing. Blocked live sources (FBref/SofaScore) are irrelevant — everything below is reachable or already here.*

---

## Layer 1 — already on disk, barely touched (do this first, zero network)

### `fbref_perf` (221 cols, keyed to TM id, 11,004 players) — you imported it, then used 7 columns
Sitting in `data/fbref/perf_player_season.parquet` right now:

| Niche stat | FBref family | Example columns |
|---|---|---|
| **GK: post-shot xG (PSxG), PSxG+/−, sweeper actions, launch %, cross-stopping** | keepers_adv (27) | `PSxG`, `PSxG+/-`, `#OPA` (def. actions outside box), `AvgDist`, `Launch%` |
| **Touches by pitch zone** (def pen → att pen) | possession (23) | `Def Pen_Touches`, `Att 3rd_Touches`, `Att Pen_Touches` |
| **Take-ons / dribbles: attempted, success%, tackled** | possession | `Att_Take-Ons`, `Succ%`, `Tkld%` |
| **Carries: progressive, into final third, into box, miscontrols, dispossessed** | possession | `PrgC_Carries`, `CPA_Carries` (carries into box), `Mis`, `Dis` |
| **Pass types: through balls, switches, crosses, corners (in/out/straight), FKs** | passing_types (16) | `TB_Pass`, `Sw_Pass`, `Crs_Pass`, `CK`, `In/Out/Str` |
| **Passing by distance + progressive + xA + key passes** | passing (28) | `PrgP`, `KP`, `xA`, `1/3` (into final third), `PPA` (into box) |
| **Defense by zone + dribblers stopped + errors leading to shots** | defense (17) | `Def/Mid/Att 3rd_Tackles`, `Tkl%_Challenges`, `Err` |
| **Discipline + duels: fouls, fouled, aerials won/lost, recoveries, pens won/conceded** | misc (17) | `Fld`, `Won_Aerial`, `Lost_Aerial`, `Recov`, `PKwon`, `PKcon`, `2CrdY` |
| **Shot quality: npxG, G−xG overperformance, avg shot distance, SoT%** | shooting (18) | `npxG`, `G-xG`, `Dist`, `SoT%` |

**This is the single biggest niche win and needs no network** — it's already keyed to TM id. `ingest/fbref_perf.py` now has a `niche_summary()` extracting these per-90 (built alongside this doc). Coverage: Big-5 2010-2024 (frozen; FBref lost the feed Jan 2025, so it doesn't grow — but it's clean history).

### StatsBomb open-data (on disk: `data/statsbomb/`, 80 comps, 448 event files, **360 + freeze-frames**)
Full event stream + **positional freeze-frames on every shot** and 360 tracking on many comps (Champions League back to 1999, Bundesliga 23/24, AFCON 23). Only `turnovers.csv` is derived so far. Untapped niche from the raw events:
- **Pressures / counterpressing / PPDA** (Pressure events) — pressing intensity, a top-tier scouting signal nobody has free.
- **Pressure-on-shot / defenders between ball and goal** (shot freeze-frames) — StatsBomb's positional xG inputs.
- **Ball recoveries, duels (aerial/ground win%), carries under pressure, receptions under pressure.**
- **Set-piece routines** (pass → shot chains from corners/FKs).

Narrow coverage (elite comps, not selling leagues), but it's the *deepest* free data and needs no residential IP.

---

## Layer 2 — compute it yourself (the truly rare stuff nobody publishes)

The fanciest "side stats" aren't sourced — they're **derived from event data you already hold** (StatsBomb on disk; Understat shots; FBref frozen). Open libraries do the heavy lifting:

| Metric (what scouts actually want) | What it measures | How to get it |
|---|---|---|
| **Expected Threat (xT)** | value a player adds by moving the ball into dangerous zones | `socceraction` xT, or a 16×12 grid model on our shots/carries |
| **VAEP / possession value** | value of *every* action (pass, carry, tackle) toward scoring/conceding | `socceraction` (ML-KULeuven) — reads StatsBomb events directly |
| **Progressive value / packing** | defenders bypassed by a pass/carry | derive from event coords (StatsBomb) |
| **Pass networks / centrality** | how central a player is to buildup | `networkx` on StatsBomb passes |
| **Pitch control / space occupation** | space a player controls (off-ball) | `kloppy` + tracking (Metrica/SkillCorner) |
| **PPDA, high turnovers, pressing traps** | team pressing style (fit to a signing) | count Pressure/Def-action events per opp pass |
| **Shot-quality context (crowdedness, keeper position)** | is the xG "easy" or "earned" | shot freeze-frames (StatsBomb) |

**Toolchain (all pip/CRAN, all open):** `socceraction` (VAEP/xT), `mplsoccer` (StatsBomb loader + freeze-frames + pitch viz), `kloppy` (loads & standardizes tracking + event coords across providers), `statsbombpy` (open-data API), `penaltyblog`. These read exactly the data on your disk.

---

## Layer 3 — open/GitHub sources for what's genuinely missing

### Physical / tracking data (normally impossible to find free)
- **SkillCorner open-data** (GitHub `skillcorner/opendata`) — **broadcast tracking**: player x/y, off-ball runs, physical/running output (distance, sprints, high-intensity). This is the tracking data clubs pay five figures for. Free sample of matches; they also periodically release off-ball-run + physical datasets.
- **Metrica Sports sample-data** (GitHub `metrica-sports/sample-data`) — full 2D tracking (all players, 25fps) + synced events for sample matches. The reference dataset for pitch control / off-ball work.
- **Wyscout public dataset** (Pappalardo et al., figshare/PLOS) — ~1,941 matches of full event data (2017-18 Big-5 + WC/Euro), public. A second event corpus beyond StatsBomb.

### Contracts, wages, market, availability
- **Wages** — Capology (scrape; some community GitHub dumps exist). Biggest NPV uncertainty; even partial Big-5 wage data beats the current model-only estimate.
- **Injuries / suspensions / availability** — Transfermarkt injury-history pages (scrape); durability is a real transfer-risk signal.
- **Market-value history, loan spells, agent, national-team** — already in the TM dump (`players.csv`, `transfers`, `player_valuations`) — mostly untapped enrichment, no new source needed.
- **Release clauses** — genuinely hard; TM lists some, otherwise press-reported. Treat as sparse/manual.

### Discipline, officials, context
- **Referee, cards, corners, shots-on-target, odds** — `football-data.co.uk` (reachable, ~22 leagues incl. feeders) — good for match context + a cheap results/priors layer.
- **Formations, lineups, xI** — StatsBomb lineups (have); TM/openfootball for breadth.

---

## What maps to which scouting question

| Scouting question | Best niche stat | Where |
|---|---|---|
| Does he create *more* than his goals suggest? | xT / VAEP / xA, key passes, PPA | compute (L2) / FBref (L1) |
| Can he beat a man? | take-on success%, carries into box, PrgC | FBref possession (L1) |
| Does he progress play or just tidy it? | PrgP, through balls, switches, packing | FBref passing_types (L1) / compute |
| Will he fit our press? | PPDA, pressures, counterpress recoveries | StatsBomb events (L1/L2) |
| Is he a defensive liability off the ball? | pressure-on-shot conceded, errors, position | freeze-frames (L1) / tracking (L3) |
| GK: shot-stopping vs distribution vs sweeping | PSxG+/−, #OPA, Launch%, AvgDist | FBref keepers_adv (L1) |
| Durability / availability risk | injury history, minutes reliability | TM injuries (L3) |
| True cost | wages + fee + clause | Capology (L3) + have |
| Physical profile / athleticism | sprints, HI distance, top speed | SkillCorner (L3) |

---

## Recommended order
1. **`fbref_perf.niche_summary()`** — expose the ~40 highest-value niche per-90 stats already on disk (built now). Instant, no network.
2. **StatsBomb pressures + freeze-frames** — a `ingest/statsbomb_niche.py` deriving PPDA/pressure-on-shot from the 448 event files on disk.
3. **`socceraction` VAEP/xT** on the StatsBomb events → possession value per player-season, joined by TM id.
4. **SkillCorner + Metrica** open tracking → the physical/off-ball layer (pull from GitHub, standardize with `kloppy`).
5. **Capology wages + TM injuries** — the two cost/risk gaps, via residential scrape when convenient.

Layers 1–3(#1-3) are all reachable/on-disk right now. Layer 3(#4-5) is the only part needing an external pull, and none of it needs SofaScore/FBref-live.
