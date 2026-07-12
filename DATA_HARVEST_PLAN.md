# Data Harvest Plan — dates, fees, contracts, wages (the money side)

Goal: close three gaps — **exact transfer dates · recent big-club fees · point-in-time
contracts/wages** — with **current, refreshable** data back to 2000, wrapped in a reproducible
harvest harness. Grounded in live recon (every source probed today).

> Complements `DATA_ACQUISITION_PLAN.md` (a separate effort on feeder-league **xG coverage** for
> the performance/impact side). That plan sources shot data; this one sources transfers, fees,
> contracts. No overlap.

## Governing rule (non-negotiable)

**No scraping Transfermarkt or FBref.** Everything here is an **open redistribution** (dcaribou
CC0, worldfootballR/ewenme GitHub caches). If a field's only route is scraping a ToS-protected
site, it stays a flagged gap.

## The unlock: dcaribou *raw* data (not the prep tables)

The prep `transfers.csv.gz` is thin (4,345 players, 2,584 fees) — a dead end. The **raw** data on
the *same* CC0 R2 host solves all three gaps, with stable/reproducible DVC access:

```
1. GitHub pointer  →  raw.githubusercontent.com/dcaribou/transfermarkt-datasets/master/
                       data/raw/{transfermarkt-api,transfermarkt-scraper}.dvc   → current <md5>.dir
2. R2 DVC listing  →  pub-e682421888d945d684bcae8890b0ec20.r2.dev/dvc/files/md5/<h[:2]>/<h[2:]>   → [{md5,relpath}]
3. R2 file         →  …/dvc/files/md5/<m[:2]>/<m[2:]>   → the json/json.gz
```
Anchoring on the GitHub `.dvc` pointer means the harness always pulls the **freshest** raw data
(re-crawled Tue/Fri). No auth. CC0.

## Source map — verified, per field

| Gap | Source | Verified evidence (today) | Cadence |
|---|---|---|---|
| **Exact transfer dates** | raw `transfermarkt-api/transfers.json` | 2024 snapshot: **52,599 events, 100% exact ISO dates** | Tue/Fri |
| **Recent big-club fees** | same | **38,150 events with a fee**; e.g. **Bellingham → Real Madrid 2023-07-01 €127.00m**. Fees are strings (`€180k`, `€127.00m`, `free transfer`, `End of loan`) → parse to EUR + type | Tue/Fri |
| **Market-value series** | prep `player_valuations.csv.gz` | 507,815 rows, 2000→2026-02 (already in use) | Tue/Fri |
| **Historical fees ≤2022/23** | ewenme/transfers + worldfootballR big5 | ewenme Big-5 24,170 fee>0 incl. 2022/23; name/url-keyed | frozen (fine for history) |
| **Point-in-time contracts** | raw `transfermarkt-scraper/players.json.gz` per season | 2013 file: 8,337 players, **3,430 with as-of-2013 `contract_expires`**; one file/season 2012–2025 → a true PIT panel | Tue/Fri |
| **Wages** | — | **No free redistributable source** — see decision | — |

Back to 2000: values reach 2000; raw api transfer events include early-career moves; fees dense
2010→now (pre-2010 fees stay sparse — a real, stated limit).

## The one decision only you can make: wages

Every free path to *real* wages is non-redistributable or off-limits:
- **Capology** (the only serious set) via **Dewey** = academic-only, non-commercial, non-redistributable ($25–35k/yr); via **direct commercial licence** = usable, **bespoke price on request**.
- **FBref** shows Capology wages but its licence precludes bulk reuse; scraping off-limits.
- **Spotrac** ToS bans mining; thin for Europe. **Kaggle "wages"** are FIFA/FM *game* data — grade-D.

**Recommendation:** ship **modelled grade-D wages** (proxy from market value + age + league — data
we already hold, fully redistributable) until/unless you sign a **Capology commercial licence**.
Contracts are solved free via dcaribou raw. → *Tell me if you want a Capology quote pursued.*

*(Recon fact-fix: FBref's blackout was Opta/xG in **Jan 2026**, not wages — the `fbref-blocked` memory date is off.)*

## Harness architecture

A thin, provenance-first layer around the existing `ingest/` modules — reuse every tested
transform (`tidy_*`, `build_canonical`); add fetch/validate/promote. **No new deps** (stdlib
`urllib`/`hashlib`/`json`).

- **`ingest/sources.py`** — declarative `Source` registry (url template, licence, cadence, cache path, canonical fields, row-floor) + `RAW_SCHEMA`/`CANONICAL_SCHEMA` contracts.
- **`ingest/manifest.py`** — `data/manifest.json` ledger (etag, last-modified, sha256, rows, fetched_at) → conditional GET, shrink guards, provenance.
- **`ingest/harvest.py`** — `refresh → validate → build_canonical → promote → report`; idempotent (304 / hash-match skip; atomic `os.replace`); snapshot-versioned (`data/merged/snapshots/<ts>_<sha>/`); CLI `--dry-run/--only/--strict/--force/--no-promote`.
- **`ingest/tm_raw.py`** — DVC resolver + parser for raw api transfers (dated fees) & scraper contracts. **Built first — the unlock.**

**Gates (block promotion):** fetch sha256 · raw-schema present · row-floor + >10% shrink guard ·
freshness · canonical-schema contract · leakage asserts (reuse `merge._check`) · coverage
non-regression (MODEL-READY ≥ 0.95× prior). **Schedule:** weekly `launchd`/cron, exit code alerts.

## Implementation sequence & status

1. **`ingest/tm_raw.py`** — raw dated fees + PIT contracts. **← building now** (access verified ✅)
2. Wire tm_raw into `ingest/merge.py`: exact-date backfill at scale + recent fees + leakage-safe `contract_years_remaining` (is_point_in_time=True).
3. Add **ewenme** dense historical fees (`sources.py`), bridged by TM id parsed from player URLs.
4. Build harness (`sources.py` → `manifest.py` → `harvest.py`).
5. Re-run merge + fee ranker; report before→after coverage.
6. (Decision-gated) wages: grade-D proxy now; Capology if approved.
