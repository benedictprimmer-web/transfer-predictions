# Data sources — verified, ranked, datacenter-safe (2026-07)

Supersedes the FBref-centric plan in `DATA.md` for advanced data. **FBref advanced
stats (xG, shot-creating actions, turnovers) were removed in Jan 2025** after Stats
Perform (Opta) terminated FBref's feed access — gone from the site regardless of IP.
Do not plan around FBref advanced stats.

**Verified reachable from this environment's datacenter IP (2026-07-11):** GitHub raw,
StatsBomb open-data, Understat live (200), Transfermarkt GitHub dumps. **Not reachable:**
FBref (403), ClubElo api (timeout — use the `tonyelhabr/club-rankings` GitHub mirror).

---

## Starter stack (what we build on)

1. **Understat shots** — `JaseZiv/worldfootballR_data` → `data/understat_shots/*.rds`
   (Big-5 + RFPL, 2014/15→). Shot-level: minute, player, xG, x/y, result, situation,
   shotType, `player_assisted` (shot-assist), match_id, teams, date, season. Read with
   `rdata` (pure-Python, no compile). **Primary xG + usage engine.** Proven: EPL file =
   102,257 shots.
2. **Transfermarkt** — Kaggle `davidcariboo/player-scores` (CC0, ~weekly) OR its R2/
   data.world unauth mirror OR `JaseZiv/worldfootballR_data` `data/tm_transfers/`,
   `data/tm_player_vals/`. Tables: transfers (fee, clubs, date), player_valuations,
   appearances (**per-player minutes**), game_lineups (**starter/sub**). **Primary money +
   minutes/lineups.** Undisclosed fees = 0/null → impute from valuation.
3. **StatsBomb open-data** — `github.com/statsbomb/open-data` (JSON). Only clean free
   source of **turnovers**: event `Dispossessed` (id 3) + `Miscontrol` (id 38). Coverage
   narrow (EPL 2015/16, La Liga multi-season, Ligue 1/Serie A 2015/16, WCs/Euros/Messi).
   Use for turnover calibration + WOWY validation on covered seasons.
4. **League strength** — ClubElo CSV (blocked here) → mirror `tonyelhabr/club-rankings`
   (GitHub, daily Opta+ClubElo CSV). FiveThirtyEight SPI is frozen/discontinued but its
   historical CSVs remain on `fivethirtyeight/data`.
5. **Revenue** — figures below (UEFA circular + Premier League releases).

## Gaps + least-bad workarounds
- **Turnovers outside StatsBomb coverage**: no free per-player dispossession source (FBref
  gone). → derive from 2017/18 Pappalardo/Wyscout figshare (DOI 10.6084/m9.figshare.c.4415000;
  tags 2001 dangerous_ball_lost + 1302 missed_ball + lost duels + inaccurate passes) and
  calibrate; or proxy from Understat (shots − key_passes residual, xGChain involvement); or
  restrict WOWY validation to StatsBomb seasons. **Usage falls back to shots + shot-assists.**
- **Wages**: no free audited dump. Capology/Spotrac are on-site estimates, not redistributable.
  Free files are FIFA/EA-game proxies (`ultimus/football-salaries-dataset`, FM24-derived) —
  ordinal prior only. → wage model (age, output, league, club revenue) anchored to a few public
  salaries; flag as the largest NPV uncertainty band.
- **Tactical style (possession/width/directness)**: no free static set post-FBref. → engineer
  PPDA + possession proxy from Understat; full metrics from StatsBomb where covered.
- **xG pre-2014/15 and in selling leagues**: Understat = Big-5 only, 2014/15+. Championship/
  Eredivisie/Primeira/Liga MX/Brazil have no free shot-xG dump. → StatsBomb-trained xG on
  whatever shot-location data exists, or goal-based season proxies for selling leagues.

---

## Prize money & CL revenue (primary sources — for Layer 3 / NPV)

**UEFA Champions League 2024/25** (new 36-team league phase; UEFA Circular 13/2024, 22 Mar 2024;
2024–27 cycle). Total UCL + Super Cup pot **€2.467bn**. Pillars: equal/starting **27.5% (€670m)**,
performance **37.5% (€914m)**, value **35% (€853m)**.
- **Starting fee €18.62m** per club (all 36).
- **Performance**: **€2.1m per league-phase win, €700k per draw**; league-rank bonus in 666 shares
  (1+2+…+36) at €275k/share; +€2m for clubs 1–8, +€1m for 9–16.
- **Knockout**: play-off €1m; R16 €11m; QF €12.5m; SF €15m; final €18.5m; **winner +€6.5m**.
- **Value pillar**: former market pool + coefficient, European/non-European parts, 666 shares each.
- Sister: UEL total €565m; UECL total €285m.
- Outcome check (ESPN via UEFA report): PSG (winner) €144.4m; Inter €136.6m; €2.47bn / 36 clubs.

**Premier League central payments** (premierleague.com primary releases):
- **2024/25** (pub. 1 Jul 2025): domestic equal share **£29.8m**/club; domestic merit **£1.6m/place**
  (champions max £32.3m); international equal share **£59.2m**; intl merit ~£1.04m/place; central
  commercial ~£7.9m. (Combined domestic+intl merit spread reported ~£2.7m/place; champions ~£53.1m.)
- **2023/24**: total **£2.848bn**; equal share **£95.1m**/club (£31.2m UK + £55.7m intl + £8.2m
  commercial); merit ~**£2.8m/place**; facility ~£0.9m/live game. Man City top **£175.9m**, Sheff Utd
  bottom **£109.7m**. Structure ~67% equal / ~21% merit / ~12% facility.

*UEFA/PL figures are provisional/gross where noted; re-verify at Layer 3 build. The CL R16→QF→SF→final
steps and PL merit-per-place are the coefficients the whole valuation scales off.*

---

## Source table (condensed)

| Area | Best source | Access | Grade |
|---|---|---|---|
| Shot xG | `worldfootballR_data/data/understat_shots` (.rds) | GitHub raw, static | A- |
| Lineups/minutes | `davidcariboo/player-scores` appearances/game_lineups | Kaggle / R2 mirror | A- |
| Usage: shots, shot-assists | Understat (shots, player_assisted) | static | A- |
| Usage: turnovers | StatsBomb open-data Dispossessed/Miscontrol | static, narrow | A qual / C cov |
| Transfers/values | `davidcariboo/player-scores` transfers/valuations | static | A- |
| Wages | none free; FIFA/FM proxies | — | D |
| League strength | `tonyelhabr/club-rankings` (ClubElo mirror) | GitHub, static | B+ |
| Tactical style | Understat PPDA + StatsBomb where covered | static | C |
| Revenue | UEFA circular + PL releases | primary docs | A |
