# Stage 10 — Real data harvest: raw fees/dates/contracts + refresh harness

**Ask:** get real, current, back-to-2000 data (exact dates · recent fees · contracts/wages);
wire it into the merge; build a weekly refresh harness. Governing rule: **no scraping
TM/FBref — CC0 open redistributions only.**

## Built

| Artifact | Path | What |
|---|---|---|
| Raw harvester | `ingest/tm_raw.py` | pulls dcaribou RAW via DVC — dated fees + point-in-time contracts |
| Merge enrichment | `ingest/merge.py::_enrich_from_raw` | exact dates + recent fees + leakage-safe `contract_years_remaining` |
| Refresh harness | `ingest/{sources,manifest,harvest}.py` | one command: refresh → validate → rebuild → promote → report |

All carry runnable self-checks (`--check`). Harness is **stdlib-only** (no new deps).

## The data unlock — dcaribou RAW (not the thin prep table)

Prep `transfers.csv.gz` is a dead end (4,345 players, 2,584 fees). The RAW data on the same CC0
R2 host, via DVC, is dense. Access (non-obvious): GitHub `.dvc` pointer → `<md5>.dir` (needs
**`.dir` suffix**) → leaf files (no suffix); **browser User-Agent required** (Cloudflare 403s
default urllib). Harvested seasons 2012–2025:
- `transfermarkt-api/<season>/transfers.json` → **87,463 dated events, 10,211 with a fee** (100% exact dates), incl. Bellingham→Real Madrid 2023-07-01 €127m.
- `transfermarkt-scraper/<season>/players.json.gz` → **140,147 contract snapshots, 69,503 dated** point-in-time expiries.

## Coverage lift (canonical, before → after raw enrichment)

| Field | Before | After |
|---|--:|--:|
| Exact `transfer_date` | 11,880 (9.6%) | **19,068 (15.4%)** |
| `contract_years_remaining` (PIT, leakage-safe) | **0** (empty scaffold) | **33,772 (27.2%)** |
| Recent fees filled from raw api | — | +253 |
| Model-ready fee rows | 16,233 | 16,485 |

`contract_years_remaining` uses the contract snapshot from a season **strictly before** the
transfer (merge_asof, `allow_exact_matches=False`) — never the post-move contract.

## Fee ranker — re-shipped

Gates still pass (Haaland −8%, Antony +164%). Added `contract_years` to the model features.
**Honest finding: it barely moved accuracy** (Spearman 0.787 → 0.786) — a real signal, but
little lift on top of market value at 27% coverage. Board now 14,060 deals.

## Scraping question — the honest answer

- **Agents:** already solved, no scraping — `players.csv` has `agent_name` for 26,853 players (54%), 3,958 agencies (CAA, Wasserman, SEG…).
- **Completed transfers (dates + fees):** solved via dcaribou raw above.
- **Pre-official "leaks"/rumours (Fabrizio Romano etc.):** this is **news/social data, not structured**, and the clean channels (X API, TM) are paid or ToS-restricted. Scraping TM/FBref/X stays off-limits even for personal use — ToS applies regardless of commercial intent. The legitimate route is **news APIs / official RSS** (GNews, club feeds) — messy, unstructured, and out of scope unless you want a rumour-ingest built.
- **Wages:** the one real blocker — Capology (paid commercial licence, bespoke) or grade-D modelled proxy. Everything else is CC0.

## Weekly refresh

`python -m ingest.harvest` — conditional GET (etag/hash skip), row-floor + shrink gates,
rebuilds canonical, promotes a versioned snapshot (`data/merged/snapshots/<ts>_<sha>/`),
manifest provenance (`data/manifest.json`). `--dry-run/--only/--force/--no-promote`. Schedule via
launchd/cron. Verified: all self-checks pass, dry-run runs against live sources.

## Reproduce
```bash
python -m ingest.tm_raw --seasons 2012 2013 ... 2025   # harvest raw (or let harvest do it)
python -m ingest.merge                                  # rebuild canonical (enriched)
python -m money.fees ship                               # re-ship fee ranker
python -m ingest.harvest                                # the whole thing, weekly
```
