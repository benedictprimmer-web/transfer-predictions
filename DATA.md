# Data sources

Every source graded on how much you should trust it. Nothing here gets scraped by hand if a maintained dump already exists.

**Run all pulls on your own machine.** Cloud IPs and sandboxes get blocked by FBref and Transfermarkt within seconds. Everything caches locally, so the network cost is paid once.

---

## Match, shot, lineup — FBref via `soccerdata`

Grade: **A** for top 5, **B** for Championship and Eredivisie, **C** and check-before-use for Liga MX and Brasileirão.

```python
import soccerdata as sd
fb = sd.FBref(leagues=["ENG-Premier League", ...], seasons=["2015-2016", ..., "2024-2025"])
fb.read_schedule()      # fixtures, results, team xG
fb.read_lineup()        # starters, subs, minutes  <- WOWY needs this
fb.read_shot_events()   # minute, team, xG         <- and this
fb.read_player_season_stats("standard")
```

`soccerdata` caches to `~/soccerdata` and rate-limits itself. Don't write a scraper. Don't override the rate limit — a ban costs you the project.

Column names move between `soccerdata` versions. On first run, print `.columns` on each frame and fix the rename maps in `ingest/fbref.py`. That is the only place this can break, and it will break exactly once.

**Before committing to any league, produce a coverage table:** rows are league-seasons, columns are `has_xg`, `has_shot_minutes`, `has_lineup_minutes`, `pct_matches_complete`. Any league-season below ~95% complete gets dropped or flagged, never silently averaged in.

---

## Fees, market values, contracts — Transfermarkt via Kaggle

Grade: **B**. Reliable structure, circular values (see SPEC §4).

```bash
kaggle datasets download -d davidcariboo/player-scores --unzip -p data/
```

Maintained dump, refreshed regularly. `transfers.csv`, `players.csv`, `player_valuations.csv`, `appearances.csv`, `clubs.csv`.

Do not scrape Transfermarkt. The dump exists, someone else maintains it, and their scraper breaks instead of yours.

Known gaps: fees are frequently `0` or null for deals reported as "undisclosed", which are disproportionately the mid-size deals. Filter them out for training and be aware you've just introduced a selection effect toward deals big enough to leak. Contract expiry dates are present but stale for some players.

---

## Wages — Capology / Spotrac

Grade: **D**. Estimates, not filings. Use them, flag them, never present them as fact.

No maintained dump. This is the one place you'll write a scraper, and it should be small, cached hard, and refreshed once a season rather than continuously.

Coverage is top-5 only, and thins out below the biggest clubs. For players with no wage estimate, fall back to a wage *model* (predict from age, output, league, club revenue) and mark the row as modelled. Never impute silently — a modelled wage and a scraped wage must be visually distinguishable in every output, because half the conclusions in Layer 4 hinge on which one you're looking at.

---

## Prize money and Champions League revenue

Grade: **A** if sourced properly, **F** if guessed.

Premier League merit payments and UEFA's revenue distribution are both published. Find the actual figures. Do not hard-code a number from memory, mine or anyone else's — the CL cliff is the single largest coefficient in Layer 3 and the whole valuation scales off it.

Sources to verify: Premier League annual financial reports for merit payments and central distributions; UEFA's club competition revenue distribution documents for the CL breakdown (participation, performance, market pool, coefficient share).

---

## Deliberately not used

**StatsBomb open data.** It's World Cups, a few WSL seasons, and Messi's La Liga career. It is not a league-season corpus and cannot support transfer analysis across the leagues we care about. The spatial pitch maps it enables are attractive and answer no question we're asking.

**Football-Data.co.uk.** Match results and closing odds. No player data at all. Nothing to contribute to a player valuation.

**Anything paid.** Not yet. Revisit only when the free version has produced something you believe and the constraint is data quality rather than method.
