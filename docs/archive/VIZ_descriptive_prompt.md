# PROMPT — 50 descriptive football data maps (dark, gradient, one HTML artifact)

*Hand this to a fresh Claude Code agent in `/Users/benrimmer/Transfer Predictions`. It is self-contained. Read `HANDOFF.md` first for data provenance, then execute.*

---

## Mission
Build **one scrollable, published HTML artifact** — "The Big-5 Data Room" — containing **50 high-quality descriptive data visualisations** from the data already on disk. Big-5 leagues (EPL, La Liga, Bundesliga, Serie A, Ligue 1) + RFPL, seasons **2014–2015 → 2024–2025**. Modern dark theme, gradient accents (The Athletic / modern-analytics look). Every chart carries a one-line takeaway. **Descriptive only** — no models to fit, no predictions; surface what's interesting in the data.

## Honesty rules (do not violate)
- **Only build what the data supports.** We have **shot-level xG** (Understat, 539,971 shots) and **Transfermarkt** (minutes, goals, assists, cards, market values, ages, fees, transfers). We do **NOT** have tackles, interceptions, dribbles, progressive passes/carries, or an official "big chance" flag. **Do not invent these.** Where a proxy is used (e.g. "big chances created" = assists to shots with xG ≥ 0.30), **label it as a proxy in the chart subtitle.**
- Apply minimum-sample floors on every leaderboard (e.g. ≥ 1,000 minutes or ≥ 40 shots) and **print the floor** on the chart.
- Penalties excluded from efficiency/finishing metrics (npxG basis) — the project standard. Show penalty specialists separately (map #5).
- Every metric that comes from a project engine (WOWY, usage, NPV, fees/overpay, aging, league strength) must reuse the existing module output — don't re-derive.

## Setup (do these first)
1. **Read the `dataviz` skill** before writing any chart code — follow its colour formula, mark specs, and accessibility rules. Swap its placeholder palette for the dark palette below.
2. **Read the `artifact-design` skill** to calibrate design investment (this warrants high investment).
3. Confirm data loads: `python3 -c "import pandas as pd; print(len(pd.read_pickle('data/understat/shots.pkl')))"` → 539971.

## Data you have (real columns)
- `data/understat/shots.pkl` — `league, season, game_id, team_shot, home_team, away_team, minute, xg, player, player_assisted, result, situation, date`. `result` ∈ {Goal, MissedShots, SavedShot, BlockedShot, ShotOnPost, OwnGoal}. `situation` ∈ {OpenPlay, FromCorner, SetPiece, DirectFreekick, Penalty}. Goal flag = `result == 'Goal'`. npxG = `xg` where `situation != 'Penalty'`.
- `data/transfermarkt/appearances.csv.gz` — `player_id, game_id, date, player_name, competition_id, yellow_cards, red_cards, goals, assists, minutes_played`.
- `data/transfermarkt/players.csv.gz` — `player_id, name, date_of_birth, position, sub_position, foot, height_in_cm, country_of_citizenship, contract_expiration_date, market_value_in_eur, highest_market_value_in_eur, ...`.
- `data/transfermarkt/player_valuations.csv.gz` — dated `market_value_in_eur` history (for trajectories).
- `data/transfermarkt/big_5_transfers.rds`, `data/transfermarkt/player_valuations.csv.gz` — fees + values (via `money/fees.py`).
- Engine outputs / interfaces: `impact/usage.py` (usage & efficiency), `validate/ronaldo.py` + WOWY, `impact/aging.py` → `data/aging/curves.csv`, `money/fees.py` (`overpay_pct`), `money/scout.py` → `data/money/scout_arsenal.csv`, `data/league_strength.csv`. Understat↔TM join via `data/crosswalk/matches.csv` (cast `game_id` to str).

## Build approach
1. **Aggregation pass** — write `scratchpad/build_viz_data.py` that produces a set of small tidy CSVs / a JSON blob under `scratchpad/viz/` (one per chart or per family). Compute once, cache. Player-season and player-career aggregates from shots.pkl; join TM age/position/value via crosswalk. Keep each chart's data payload small enough to inline into the HTML.
2. **Render pass** — one self-contained `scratchpad/data_room.html` with all 50 sections. Inline all data as JS consts (CSP blocks external fetches). Use inline SVG or a single small charting approach — **no external CDNs**. Responsive; wide charts scroll inside their own `overflow-x:auto` container; page body never scrolls sideways.
3. **Publish** with the `Artifact` tool (favicon ⚽📊, title "The Big-5 Data Room"). Redeploy the same file path to keep the URL.

## Visual system (dark, gradient)
- Background `#0B0F14` → panels `#131A22`; text `#E6EDF3` / muted `#8B97A6`; hairlines `#222C38`.
- Sequential gradient for xG intensity: deep indigo `#3B2F87` → magenta `#C026A9` → amber `#F5A623`.
- Categorical (leagues): EPL `#00E0B8`, La Liga `#FF5C8A`, Bundesliga `#FFC24B`, Serie A `#5B8DEF`, Ligue 1 `#B980FF`, RFPL `#8B97A6`.
- Over-performance = warm (`#F5A623`/`#FF5C8A`), under-performance = cool (`#5B8DEF`/`#00E0B8`). Consistent everywhere.
- Header hero with a headline stat. Sticky section nav / table of contents. Each chart: title, one-line proxy/floor subtitle, the viz, one **bold takeaway** sentence. Number formatting: xG to 1 dp, values as €Xm, per-90 to 2 dp.
- Follow the `dataviz` skill for legends, axis labels, direct labelling of the top N, and colour-blind safety. Motion: subtle fade-in on scroll only, respect `prefers-reduced-motion`.

## The 50 maps (build all; keep the numbering)

**A · Finishing — Goals vs xG (the crown jewel)**
1. Career G vs npxG scatter, all Big-5 (floor ≥ 40 shots) — diagonal y=x, biggest over/under-performers labelled.
2. Best single-season finishing over-performances ever (G − xG), top 25.
3. Does finishing persist? Season-to-season G−xG for repeat players — scatter + weak correlation callout (mostly noise).
4. Clinical vs wasteful quadrant — xG/shot (chance quality) vs conversion rate.
5. Penalty specialists — pen conversion & volume, shown separately from open play.
6. Header finishing — headed G vs xG (use `situation`/aerial context available; label proxy if inferred).
7. Elite striker head-to-head — finishing of the era's top 8 (Kane, Haaland, Salah, Lewandowski, Benzema, Mbappé, Suárez, Cavani).
8. Messi vs Ronaldo in the Big-5 window — cumulative xG & goals timeline.
9. Regression to the mean — career arc of finishing luck for 3–4 famous over-performers.

**B · Chance creation**
10. Top chance creators — total xG of shots they assisted (xG created), leaderboard.
11. "Big chances created" (PROXY: assists to shots xG ≥ 0.30) — leaderboard.
12. Playmaker efficiency — xG created per 90 (floor ≥ 1,500 min).
13. Creator vs scorer 2×2 — npxG/90 vs xG-created/90.
14. Assist over/under-performance — actual assists vs xG created.
15. Deadliest partnerships — top passer→scorer pairs by combined xG created (from `player_assisted`).

**C · Volume & efficiency**
16. Shot-volume kings vs xG/shot — do high-volume shooters take worse shots?
17. Efficiency leaders — npxG per 90 (floor ≥ 1,500 min).
18. Shot monopolists — share of team shots (usage), Ronaldo/Salah highlighted (`impact/usage.py`).
19. Goal involvement (G+A) all-time leaderboard, Big-5 window.
20. Raw output vs minutes-adjusted — who'd score more with more minutes.

**D · Shot profile / situational**
21. Shot-location xG profile — box vs outside-box share, top scorers.
22. Set-piece threat — most xG from corners/set pieces.
23. Counter-attack specialists — xG from fast breaks.
24. Situation mix per player — stacked bar (open play / set piece / pen / free kick).
25. The shot-quality drift — league-wide xG/shot 2014→2025 (are teams shooting smarter?).

**E · Timing / clutch**
26. Late-goal merchants — goals in minute 76–90+ leaderboard.
27. When goals happen — minute-bucket heatmap for the top 10 scorers.
28. Fast starters vs slow burners — first-15 vs last-15 goal share.
29. Home vs away finishing splits — biggest home-comfort / road-warrior gaps.

**F · Team-level**
30. Team goals vs xG (for & against) — over/under-performing sides.
31. Shot dominance — team shots per game across 11 seasons, small-multiples.
32. Champions' signatures — xG profile of each league's title winners.
33. Biggest season-over-season swings — most improved / collapsed attacks.
34. xG table vs real table — how much luck decided the standings (one league, latest season).

**G · Transfer value & age**
35. Market-value trajectories — line chart of the era's biggest movers (`player_valuations`).
36. Age curves — attacking output by age, per position (`impact/aging.py` / `data/aging/curves.csv`).
37. Value vs age scatter — who's peaking, who's declining.
38. Biggest value explosions — largest % MV gains.
39. Biggest value collapses — largest % MV drops.
40. Value efficiency — €m of market value per npxG/90.
41. Contract-expiry cliff — stars in their final contract year (bargain radar).

**H · Fees / market**
42. Fee vs output — most expensive signings and their subsequent xG.
43. Overpays vs bargains — `money/fees.py` `overpay_pct` (Antony +183% vs Haaland −21%).
44. Transfer-market inflation — median/top fees over time.
45. Value-for-money board — top NPV-positive signings (`money/scout.py`).

**I · Engine outputs (already computed — reuse)**
46. WOWY leaderboard — team xGD on/off pitch; Ronaldo's negative highlighted.
47. NPV scout board — undervalued efficient forwards (`data/money/scout_arsenal.csv`).
48. League strength — descriptive "easiest league to sustain value-per-action" (`data/league_strength.csv`), flagged descriptive-only.

**J · Era / league trends**
49. Goals & xG per game by league, 2014→2025 — which league is most attacking.
50. The xG era — league-wide finishing (G/xG ratio) and shot quality over 11 seasons; closing "what the data says" panel.

## Definition of done
- 50 sections render, dark theme, gradient accents, sticky nav, every chart has floor/proxy subtitle + bold takeaway.
- No external network calls; page body has no horizontal scroll on mobile width.
- Published via `Artifact`; URL returned. `scratchpad/build_viz_data.py` re-runs clean end-to-end (leave a `python3 scratchpad/build_viz_data.py` one-command rebuild).
- A short `demo()`/`__main__` assert in the build script that fails if any leaderboard is empty or any xG total is NaN.
```
