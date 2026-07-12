# LANE_B_HARVEST.md — Recent deals & fees 2023–2026

**Ask:** the canonical spine's fee coverage collapses after 2022 (2023 ~8%, 2024 ~6%, 2025 ~5%) —
reporting lag, not a real market crash. Backfill recent fees/dates/contracts so the inflation
index and fee ranker extend to the present.

**Verdict: fixed, not just backfilled.** The "collapse" was mostly two bugs, not a real data
gap — the dense fix (10,211 real dated fees, already harvested and sitting on disk) existed but
two defects in `ingest/merge.py` kept it from reaching 2023+ rows. Fixing those, plus one new
row-generator, took clean fee>0 2023–25 coverage from **~6% to ~22%** and extended the inflation
index gate from **2022 to 2025**.

---

## Phase 0 — hole map (before)

| Season | rows | fee>0 (not suspect) | fee coverage |
|---|--:|--:|--:|
| 2019 | 5,360 | 1,405 | 26.2% |
| 2020 | 4,757 | 950 | 20.0% |
| 2021 | 4,655 | 915 | 19.7% |
| 2022 | 3,759 | 794 | 21.1% |
| **2023** | 2,146 | 173 | **8.1%** |
| **2024** | 3,846 | 215 | **5.6%** |
| **2025** | 2,448 | 122 | **5.0%** |
| **2026** | 710 | 20 | **2.8%** |

Matches the brief's stated numbers exactly. `transfer_type` was **null for all 9,150** of the
2023+ extension rows — a second, sharper problem: `money/inflation.py::build_frame()` filters
on `transfer_type == "permanent"`, so **zero** 2023+ rows could ever enter the hedonic model
regardless of any fee-coverage fix. Corrupt-fee landmines (the audit's warning): none newly
found in the 2023+ slice — `fee_suspect` correctly stayed 0 on the new rows (checked against
the €222m Neymar ceiling).

## Reachability

| Source | Route | Status |
|---|---|---|
| dcaribou GH `.dvc` pointer (`raw.githubusercontent.com/...transfermarkt-datasets`) | sandbox-ok | HTTP 200 |
| dcaribou R2 DVC store (`pub-e682421888d945d684bcae8890b0ec20.r2.dev`, browser UA) | sandbox-ok | 200 on real file paths (root path 404s, expected — not a listing endpoint) |
| dcaribou raw `transfermarkt-api` seasons upstream | sandbox-ok | listing confirms **2012–2025 available**; no 2026 season crawled yet upstream (dataset re-crawls Tue/Fri) — already fully harvested locally |
| dcaribou raw `transfermarkt-scraper` (contracts) upstream | sandbox-ok | **2005,2007,2009,2011–2025 available**; 2012–2025 already harvested locally |
| ewenme/transfers (community CC0, historical Big-5 fees) | sandbox-ok | 200 (repo reachable) but **404 on any 2023 file** — confirmed frozen, no recent seasons, not useful for this lane |
| Capology (wages, checked in passing — Lane A territory) | sandbox-ok | 200, not pursued here (out of scope) |

No source needed a residential/datacenter-proxy route for this lane — the raw harvest was
already fully fetched to the latest available upstream season (2012–2025) before this session
started; the real problem was in the merge, not the fetch.

## What was actually wrong (root-caused, not just re-fetched)

`ingest/merge.py` already had the dense raw harvest (`raw_transfers.parquet`: 87,463 dated
events, 10,211 with a real fee, including Bellingham €127m) sitting on disk, but three defects
kept 2023+ coverage thin:

1. **NaN-sort dedup bug** in `_enrich_from_raw()` — `rt.sort_values("fee_eur")` relies on
   pandas' default `na_position="last"`, so a real fee sorted *before* a NaN duplicate; then
   `drop_duplicates(keep="last")` kept the **NaN row**, discarding the real fee, inverting the
   code's own stated intent ("prefer a fee-bearing event"). Confirmed 715 real fee events lost
   to this across the whole dataset. Fixed: `na_position="first"`.
2. **`transfer_type` hardcoded to `None`** for the entire 2023+ extension (`ext["transfer_type"]
   = None`) because Estate A's thin prep table (`transfers.csv.gz`) has no type field at all —
   silently locking every 2023+ row out of `build_frame()`'s permanent-transfer filter forever.
   Fixed: infer `transfer_type` from the raw harvest's `fee_type` (fee→permanent, free→free,
   loan/loan_fee→loan) via the existing player/club/season join, wherever a raw event matches.
3. **The real bottleneck: the 2023+ extension only ever drew ROWS from the thin Estate A prep
   table** (2,584 fees, ever), and `_enrich_from_raw` only backfills fields onto rows that
   already exist. Of 3,354 real-fee 2023–25 events in the raw harvest, only **13** had a
   matching (player, club) pair anywhere in canonical — **3,341 real transfers were never rows
   at all**, so no backfill could reach them. Added `ingest/merge.py::_extension_from_raw()` — a
   second row-generator that builds canonical rows **directly from the raw harvest**
   (`raw_transfers.parquet`) for 2023+, crosswalked to Estate A's `players.csv.gz` /
   `clubs.csv.gz` for age/league (same TM player_id namespace, same leakage-safe PIT-MV/contract
   pipeline as the existing extension). This is what delivered the bulk of the lift: **+9,964
   net-new rows**, origin `raw_2023plus`.

A minor self-inflicted duplication (114 near-duplicate rows, differing only by from-club-name
spelling or a 1-day date drift across snapshot crawls) was caught and deduped in the same pass
(`_extension_from_raw`, keep the fee-bearing copy) — 14 of those carried a real fee up to €12m.

## Coverage lift (before → after)

| Season | rows before → after | fee>0 before → after | coverage % before → after |
|---|---|---|---|
| 2023 | 2,146 → 4,241 | 173 → 1,140 | 8.1% → **26.9%** |
| 2024 | 3,846 → 7,500 | 215 → 1,347 | 5.6% → **18.0%** |
| 2025 | 2,448 → 5,334 | 122 → 1,118 | 5.0% → **21.0%** |
| 2026 (partial, window open) | 710 → 2,039 | 20 → 239 | 2.8% → 11.7% |

For reference, 2020/2021 (already inside the old valid range) run 20.0%/19.7% — 2023 and 2025
now sit *above* that; 2024 sits a little below it (residual noted, not fully explained — possibly
a crawl-timing artifact in that season's snapshot file — flagged, not papered over).

Canonical total: **124,183 → 134,147** rows (+9,964). Clean fee>0 (not suspect): **24,754 →
28,068** (+3,314). Model-ready (fee+MV+age): **16,599 → 19,859** (+3,260). Exact-date coverage:
15.4% → **21.6%**. Contract-years PIT coverage: 27.2% → **31.0%**.

Fee ranker board (`money/fees.py::ship`): **14,060 → 17,308** ranked deals (+23%). Gate still
passes: Haaland −41% (underpay), Antony +171% (overpay).

## Inflation index gate — extended

`money/inflation.py`: **`YEAR_MIN, YEAR_MAX = 1992, 2022` → `1992, 2025`.** 2023–25 now clear
the same coverage bar 2020/2021 already cleared inside the old valid range. 2026 stays excluded
— that's a genuinely open transfer window (partial-season undercount), not a sourcing gap;
re-run `python3 -m money.inflation build` again once the 2026/27 window closes.

Also fixed two things that would otherwise have silently broken once the range moved:
- Self-check #1's CPI-comparison lookup hard-indexed `UK_CPI_2015_100[vmax]`; the CPI table
  (a directional benchmark only, never a deflator) only runs to 2022, so it now caps the CPI
  side at `min(vmax, 2022)` instead of guessing/fabricating 2023–25 CPI figures.
- Self-check #5's "out-of-range year" test was hardcoded to 2025 — now genuinely out-of-range
  (`vmax + 1`), so it keeps testing what it claims to test after the extension.

Rebuilt index: `[build] clean universe: 25,368 permanent positive-fee transfers (1992–2025)`.

```
=== self-checks on freshly built index ===
  [PASS] 1 Shearer 1996->2025 elite in modern-record band, not CPI — £425m vs CPI £27m (x15.8)
  [PASS] 2 COVID dip (2017->2021 < 2017->2019 elite) — 0.957 < 1.080
  [PASS] 3 elite != median (same window) — elite 12.606 vs median 3.285
  [PASS] 4 round-trip 2012->2020->2012 recovers original — 40.0 -> 76.37 -> 40.000000
  [PASS] 5 out-of-range year flagged, not silently CPI'd — year 2026 outside validated range [1992,2025]
  ALL PASS
```

`INFLATION_AUDIT.md` and `INFLATION_FINDINGS.md` regenerated with the new range and dynamic
(not hardcoded) recent-coverage figures.

## Self-check — known 2023–2025 headline signings resolve to the right fee (PASS)

Pulled straight from the new `raw_2023plus` rows, checked against publicly reported fees:

| Player | Move | Season | fee_eur (ours) | Known reported fee |
|---|---|---|---|---|
| Declan Rice | West Ham → Arsenal | 2023 | €116.6m | £105m (~€116–122m) ✓ |
| Moisés Caicedo | Brighton → Chelsea | 2023 | €116.0m | £115m (TM-listed €116m) ✓ |
| Kai Havertz | Chelsea → Arsenal | 2023 | €75.0m | ~£65m (~€75m) ✓ |
| Jude Bellingham | Dortmund → Real Madrid | 2023 | €103.0m | €103m ✓ |
| Khvicha Kvaratskhelia | Napoli → PSG | 2025 | €80.0m | ~€70–90m reported range ✓ |
| Florian Wirtz | Leverkusen → Liverpool | 2025 | €125.0m | £116m (~€125m) ✓ |
| Alexander Isak | Newcastle → Liverpool | 2025 | €145.0m | £125m (~€145m) ✓ |

All PASS — no fee_suspect flags on any of these, no invented numbers, all sourced from the
CC0 raw harvest.

## Residual holes (honest, not fixed here)

- **`transfer_type` still null for 2,711 / 134,147 rows** — legacy Estate-A-prep extension rows
  (origin `estateA_2023plus`) that couldn't be matched to a raw event by (player, club, season).
  They stay out of the permanent-fee model; not fabricated a type for them.
- **Exact-date coverage still 21.6%**, capped by the raw harvest's own player coverage (~11k
  distinct players across all seasons) vs ~50k+ total players in canonical — a real, stated
  ceiling, not something this pass could close further from CC0 sources alone.
- **2024 coverage (18.0%) sits below 2023/2025 (~27%/~21%)** — noted, not explained; flagging
  rather than smoothing it away.
- **Community CC0 alternatives (ewenme/transfers) confirmed frozen** (404 on any 2023+ file) —
  not a usable second source for recent fees; dcaribou raw remains the only productive route
  found from this sandbox for 2023+.
- **Pre-official leaks/rumours (Fabrizio Romano-style reporting)** — out of scope per the
  governing no-scraping rule; the clean route (news APIs/RSS) is unstructured and wasn't built.
- **Wages** — untouched, Lane A's territory.

## Integration status

- `ingest/merge.py` — `_enrich_from_raw()` dedup fix + transfer_type inference; new
  `_extension_from_raw()` wired into `build_canonical()` as step 4b, before the existing
  raw-enrichment pass so contract-PIT/date backfill still applies to the new rows too.
- `data/merged/transfers_canonical.parquet` — rebuilt (134,147 rows), self-check passes
  (`python3 -m ingest.merge --check`).
- `money/inflation.py` — gate extended, self-checks patched to stay meaningful post-extension,
  rebuilt (`python3 -m money.inflation build`), all 5 self-checks PASS.
- `money/fees.py` — re-shipped (`data/money/fee_ranker.csv`, 17,308 rows), Haaland/Antony gate
  PASS.
- No model retraining performed (out of scope) — this is acquisition + a merge-pipeline fix.

## Verdict

This lane moved from "backfill what's missing" to "fix why it was missing" — the raw fee data
was already sitting on disk, harvested in a prior session, but a sort-order bug and a
never-populated column meant almost none of it reached the canonical spine or the inflation
model. With those fixed plus a genuine new source-to-row path from the raw harvest, recent-fee
coverage roughly **tripled to quadrupled** (2023: 8%→27%, 2025: 5%→21%) and the inflation index's
valid range extended three years (2022→2025) on real, not manufactured, coverage. Still weak:
exact-date coverage outside the ~11k raw-covered players, and the unexplained 2024 dip — both
flagged rather than hidden.
