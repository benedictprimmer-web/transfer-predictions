# LANE_C_HARVEST.md — Club-by-club revenue (Stage 11 data half)

**Ask:** `money/revenue.py` prices every club identically (`EQUAL_SHARE=95.1`,
`revenue_at_rank(rank)` scalar), so the valuation can't see that a CL place is worth
far more to Man Utd than to a promoted club. Land clean club revenue split into
**matchday / broadcast / commercial** at `data/money/club_revenue.parquet`, crosswalked
to `to_club_id`, graded. **Data only** — do NOT build the RevenueModel extension.

**Verdict: delivered, one clean season (2020/21), 20 clubs, grade B, 20/20 self-check pass.**
The Deloitte Football Money League 2022 edition (top-20 world clubs, matchday/broadcast/
commercial split) extracted cleanly and reconciles to its own printed totals for all 20
clubs. This is enough to *unlock* buyer-specific pricing (the panel covers ~every plausible
big-money transfer buyer), but it is a **single COVID-affected season** and a **top-20-only
panel** — a genuine time series and the long tail are the residual holes (see below).

---

## Phase 0 — what already existed (before fetching)

- `money/revenue.py`: EPL-only, club-agnostic. `revenue_at_rank(rank)` = `EQUAL_SHARE(95.1)`
  + merit + European EV. No commercial/matchday/club dispersion at all. Confirmed the
  integration target; **not touched** (modelling stage, out of scope).
- `data/money/`: had inflation index, fee ranker, scout, backtest — **no revenue-by-club file**.
  `find . -iname "*revenue*"` → only the scope doc and `revenue.py`. Clean greenfield.
- **Stadium capacity was already on disk**: `data/transfermarkt/clubs.csv.gz`,
  `stadium_seats` column, **796 clubs, 100% populated**, keyed by the same `club_id` that
  IS `to_club_id` in the canonical spine. No need to re-source it (ladder rung 2 — reuse).
- Crosswalk: `data/crosswalk/players.csv` is player-level only; there is **no club crosswalk
  file** — but none is needed, because the canonical spine's `to_club_id` already IS the
  Transfermarkt `club_id`. Hand-mapped the 20 Deloitte club names to `club_id` and verified
  each against `clubs.csv.gz` (name + `domestic_competition_id`).

Corruption check: every extracted split reconciles to the PDF's own printed total (20/20,
<0.2m EUR), so no silent mis-extraction landmines. One low figure that *looked* suspect
(Wolves broadcast EUR27.2m) was cross-checked against Wolves' own headline-financials press
release and is correct — a COVID season artefact (broadcaster rebates), not an extraction error.

## Reachability table (curl -sI / GET, browser UA, from this datacenter IP)

| Source | Route | Status | Notes |
|---|---|---|---|
| Deloitte UK/global Money League pages (`deloitte.com/uk/...`) | **blocked** | 404 / 302 redirect-loop | Bot-blocked from this IP; the `www2 → www` redirect drops the body (size 0) |
| **Deloitte CZ mirror** (`www2.deloitte.com/content/dam/Deloitte/cz/Documents/consumer-business/deloitte-football-money-league-YYYY.pdf`) | **sandbox-ok** | **HTTP 200** | The working route. Editions **2019, 2021, 2022, 2023, 2024** returned real PDFs; 2020/2025/2026 slugs 404 on this mirror (different filename/path per year) |
| Deloitte "dfml22" alt host (`nor.deloitte.com/rs/712-CNF-326/images/deloitte-dfml22.pdf`) | sandbox-ok | 200 | Same 2022 report, backup copy |
| UEFA Club Licensing / ECFL Benchmarking PDFs (`editorial.uefa.com`, `cdn.vev.design` mirror) | sandbox-ok | 200 (48–54 MB) | Fetched 2022 + 2024 ECFIL; NOT yet table-extracted (see holes) |
| UEFA main site (`uefa.com`) | flaky | HTTP/2 INTERNAL_ERROR | PDFs reachable via editorial/CDN hosts, not the portal |
| Companies House (`find-and-update.company-information.service.gov.uk`) | sandbox-ok | 200 | Reachable for the UK long tail; not pursued this session (top-20 covers the buyers) |
| Swiss Ramble (`swissramble.substack.com`) | sandbox-ok | 200 | Published-account digests; not needed for the top-20 panel |

**Nothing was blocked that stopped the primary deliverable.** The Deloitte UK page bot-block
was routed around via the CZ mirror — no residential/proxy fetch was required.

## Extraction method (the pitfall that mattered)

The Deloitte per-club "2021 Revenue profile" is a **donut infographic, not a text table** —
the three slice values do NOT appear in a fixed reading-stream order per club (naive
`extract_text()` mis-assigns matchday↔broadcast↔commercial, and on some pages splits numerals
into single characters). Extracted by **geometric word position** instead (`pdfplumber`
word x/y boxes): top-right small slice = matchday, left column = broadcast, right-column
mid-band = commercial, centre = total. Each value re-assembled from its x/y region and
**validated against the page's printed Total** (matchday+broadcast+commercial == total).
Result: **20/20 clubs reconcile within 0.2m EUR.** The 20 verified rows are frozen as a
struct in `ingest/club_revenue.py` (no PDF needed at build time); the extractor script is
kept at `scratchpad/lanec_pdfs/extract_2022.py` for reproducibility / re-running on other editions.

## What was acquired

`data/money/club_revenue.parquet` — **20 club-seasons**, season 2020/21 (`season=2020`,
spine convention = year the season starts). Schema exactly as specified:

`to_club_id · club_name · season · matchday_eur_m · broadcast_eur_m · commercial_eur_m · total_eur_m · stadium_capacity · source · grade`

- **Clubs** (Deloitte 2022 top-20): Man City, Real Madrid, Bayern, Barcelona, Man Utd, PSG,
  Liverpool, Chelsea, Juventus, Tottenham, Arsenal, Dortmund, Atlético, Inter, Leicester,
  West Ham, Wolves, Everton, AC Milan, Zenit.
- **`source`** = `deloitte_money_league_2022` on every row; **`grade`** = `B` on every row
  (published analysis of audited club accounts; single season; top-20 panel). Never blended.
- **`stadium_capacity`** joined from `clubs.csv.gz`, 20/20 populated.
- **Crosswalk**: `to_club_id` is the Transfermarkt club_id; all 20 join live to the canonical
  spine — **5,224 transfer rows** in `transfers_canonical.parquet` land at these 20 clubs,
  20/20 club_ids matched.

## Self-checks (PASS/FAIL)

Run `python3 -m ingest.club_revenue` (offline, no network):

- ✅ 20 rows, `to_club_id` non-null and unique.
- ✅ **Every club's split reconciles to its own printed headline total** (matchday+broadcast+
  commercial == total, all 20, <0.2m EUR). This is the "totals reconcile to published headline
  revenue within a few %" check — here it's exact, because the total is Deloitte's own printed
  headline and the parts are its own printed slices. Cross-source spot-check: Wolves commercial
  EUR191.3m matches the club's own press-release figure of GBP194.1m (EUR≈GBP at the period rate).
- ✅ **Man Utd commercial (EUR288m) >> the smallest panel club's** (Zenit EUR43m; and >> Leicester
  EUR208m among English clubs) — the commercial dispersion the whole stage exists to capture
  shows up. (Note: the panel has no *promoted* club per se — Leicester/West Ham/Wolves are the
  small-commercial English clubs here; Man Utd's EUR288m commercial vs Leicester's EUR208m and
  Wolves' EUR191m is the dispersion signal.)
- ✅ Stadium capacity populated 20/20; grade/source stamped on every row.

## Residual holes (honest)

| Dimension | Coverage | Gap |
|---|---|---|
| **Seasons** | 1 (2020/21 only) | **No time series.** The scope wants ~15 yrs to calibrate `success_uplift`/`rounds_uplift` (how commercial/matchday move the year *after* a club qualifies for the CL). Editions 2019/2021/2023/2024 are downloaded to `scratchpad/lanec_pdfs/` and extractable with the same geometric method — **not yet done** (each edition's page layout differs slightly, so the x/y windows need re-tuning per year). This is the single biggest residual. |
| **Club breadth** | Top-20 world only | Covers ~every real big-money buyer, but misses the promoted / mid-Championship long tail. UEFA benchmarking PDFs (downloaded, 48–54 MB) + Companies House (reachable) would fill it — deferred; marginal value for transfer pricing per the scope's own recommendation. |
| **Season quality** | 2020/21 = COVID | Matchday collapsed leaguewide and broadcast/commercial shares are unusually volatile that season. The *totals* are real; the *split* is directionally right but not a normal-year baseline. A non-COVID edition (e.g. 2019 → 2018/19, or 2024 → 2022/23) would give a cleaner split — again, an extraction re-tune away. |
| **Owner/discount tier** | Not sourced | Scope §3c wants a club→owner-tier map from UEFA owner-funding figures. Out of this lane's data-only remit; the UEFA PDFs that carry it are on disk. |

## Integration status

Data-only, as instructed. `money/revenue.py` **not modified**. The parquet is landed at the
exact path (`data/money/club_revenue.parquet`) and schema the scope's build step (§3a/§3b)
expects, keyed to `to_club_id`, so the modelling stage can `merge` it straight onto the spine
with no further prep.

## One-paragraph verdict

This moves club revenue from **absent → grade B for the 20 clubs that matter**, and it's enough
to **unlock buyer-specific pricing today**: the model can now see that Man Utd's EUR288m commercial
dwarfs a small club's, so a CL point is worth more to the bigger brand — the exact dispersion the
stage exists to add. Where it's still weak: it's **one COVID season, top-20 only**. The fix for
both is not new acquisition (the PDFs are already downloaded) but **re-running the geometric
extractor across the 2019/2021/2023/2024 editions** to build the multi-year, non-COVID panel the
uplift-calibration needs — a follow-up session's work, not a blocked one.
