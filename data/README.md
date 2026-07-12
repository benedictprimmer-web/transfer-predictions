# data/ — read this first

**~1.2GB on disk, but the working set is a few tens of MB.** Don't `grep`/`ls -R`/read
your way through this tree to understand it — most of the bulk is raw re-fetchable
cache. Use the map and the warehouse instead.

## How to actually use this data

1. **The map:** [`../DATA_INDEX.md`](../DATA_INDEX.md) — every dataset, its size, status,
   producer, licence, join key. Auto-generated, never stale.
2. **Query it:** `from ingest import warehouse; con = warehouse.connect()` — a read-only
   DuckDB with fresh views over the derived parquets. Join on `tm_player_id`.
3. **Per-folder detail:** each subfolder has a `README.md` (pivot of the map). Read that
   1KB file, not the blobs inside.

Regenerate both: `python3 -m ingest.data_index build && python3 -m ingest.data_index readmes`

## Working set vs. raw cache

- **Working set** (what models query): the `*.parquet` derivatives + `warehouse.duckdb`.
  Small, fast, already in the warehouse views.
- **Raw cache** (🗑️ in folder READMEs): scraped HTML / downloaded JSON / `.rds` / pickles
  that ingest scripts *reduce* into the parquets. Idempotent `download()` — safe to delete
  to reclaim disk; re-fetches on next run. **Never read these to understand the data.**

## Where the fat is (2026-07-12)

| Folder | Size | Files | Note |
|---|--:|--:|---|
| `statsbomb/` | 131M | **2059** | ⚠️ file-COUNT is the real slow-down — `laliga_cache`/`ronaldo_cache` = ~1150 tiny JSONs. Re-fetchable. |
| `wages/` | 388M | 149 | `capology_raw/` ~340M scraped HTML (unregistered), re-fetchable. |
| `transfermarkt/` | 388M | 29 | `raw/…/transfers.json` 161M uncompressed; `game_lineups.csv.gz` 113M. |
| `strength/` | 116M | 195 | `clubelo-club-rankings.csv` 47M is a **stale mirror, superseded by the live API**. |
| `fbref_shots/` | 99M | 5 | raw `.rds`, reduced to a 2.5M parquet. |
| `understat/` | 72M | 9 | `shots.pkl` 92M is the read cache; `shots.parquet` is the identical 18-col twin (regenerate the pkl from it if a numpy version breaks the pickle). |

## Reclaiming disk (optional, opt-in)

Deleting raw cache trades disk for re-fetch time. The two clean wins with no re-fetch cost:
`strength/clubelo-club-rankings.csv` (stale, superseded) and any `capology_raw/*.html`
already parsed into `capology.csv`. Everything else 🗑️ is re-fetchable but costs a
re-download. See folder READMEs for the per-dataset flags.
