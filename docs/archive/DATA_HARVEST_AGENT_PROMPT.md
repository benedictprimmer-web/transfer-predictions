# Data-Harvest Agent Prompt — move every data pillar up a grade or two

**Purpose.** Hand this to fresh sub-agents. Their job: raise the *quality and coverage* of the
transfer model's data, pillar by pillar — **wages first and hardest** — by (1) fully understanding
what already exists, (2) sourcing more by any legitimate means, (3) pre-processing, cross-walking,
and **finding the holes**, then (4) wiring it into the existing integration points with self-checks.

This is an **acquisition + validation** brief, not a modelling one. Do not retrain the valuation
model. Deliver clean, graded, crosswalked data + a report of what's still missing.

> **How to dispatch.** There are four lanes (A–D) plus a shared Phase 0 every agent runs first.
> Run one agent per lane in parallel, or one agent through all four in sequence. **Lane A (wages)
> is the priority and should get the most effort** — if you only finish one lane, finish A.

---

## 0. Context you are inheriting (READ THIS FIRST — all lanes)

- **Working dir:** `/Users/benrimmer/Transfer Predictions`. Python, stdlib-first, pandas/statsmodels
  available. Every `ingest/*` and `money/*` module runs an offline `_check()` with no args.
- **What the system does:** prices a transfer as NPV = benefit (team wins more → league rank →
  revenue) − cost (amortised fee + **wages**). Read `START_HERE.md`, then `HANDOFF.md`, `AUDIT.md`,
  `DATA.md`, `MODELS.md`. For lane specifics also read the MEMO/RESEARCH docs named in each lane.
- **The canonical spine:** `data/merged/transfers_canonical.parquet` (124,183 transfers; 24,674 with
  a real positive fee; schema: player_id, player_name, player_age, pos_group, from/to club+league,
  season, window, fee_eur, market_value_eur, transfer_type, transfer_date, contract_years_remaining,
  and quality flags fee_suspect/…). Confirm the schema empirically before trusting this list.
- **The universal join key is `tm_player_id`** (Transfermarkt player id). Everything must crosswalk
  to it. The bridge lives at `data/crosswalk/players.csv`
  (cols: us_player_id, tm_player_id, us_name, tm_name, n_seasons, votes, vote_share, method) and the
  name+dob matcher is in `ingest/wages_fifa.py::crosswalk()`. Reuse it; do not reinvent matching.
- **Grades:** A = audited/redistributable (e.g. CC0 dumps, published accounts). B = reachable
  personal-use source, per-entity. C = modelled/proxy with a real signal. D = weak proxy/guess.
  **Every row you deliver carries a `grade` and a `source` column.** Never blend grades silently.

### 0.1 Reachability reality (this matters — probe it, don't assume)
This sandbox runs on a **datacenter IP**. Some sites hard-block it (FBref, FotMob, SofaScore → 403),
others don't (Capology → HTTP 200, ClubElo API → 200, GitHub release assets → 200, dcaribou R2 via
DVC with a browser User-Agent → 200). **The user also has separate datacenter/proxy infrastructure
available.** Therefore, as the FIRST action of any lane:

1. `curl -sI` (or a HEAD request with a browser UA) each candidate source and **record the status
   code** in your report. Do not guess reachability — measure it.
2. For every source, label the required route: **`sandbox-ok`** / **`needs-residential`** (the user's
   Mac) / **`needs-datacenter-proxy`** (the user's infra). 
3. Write pulls as **standalone runnable scripts** that work regardless of where they run (browser UA,
   ret/backoff, resumable), so the user can execute a blocked pull from the right place. Put a one-line
   run command at the top of each script.

### 0.2 Phase-0 audit (EVERY lane does this before fetching anything)
Prove you understand what's already on disk — half the "missing" data is often already next door.
- Load the relevant existing artifacts, print `df.info()`, row counts, **coverage by season and by
  league**, and null-rates. Cite numbers.
- Produce a **hole map**: a small table of `[dimension × coverage %]` showing exactly where the gaps
  are (which years, which leagues, which player tiers).
- **Double-check** existing data for silent corruption (the canonical spine had corrupt €500m fees
  caught only by a `fee_suspect` flag — assume similar landmines exist). Report anomalies.
- Only then fetch. When you fetch, fetch to fill *measured* holes, not blindly.

### 0.3 Rules of engagement (all lanes)
- **No fabrication.** Cite counts for every claim. If a source is thin, say so and narrow scope.
- **Legality/ToS.** Freely redistributable/CC0 dumps and published statutory accounts → use directly.
  ToS-protected scrapes (e.g. Capology, Transfermarkt pages) → build the fetch, run it for
  **personal/research use only**, keep it **behind a clear go-ahead flag**, and never commit the user
  to a paid tier or an account signup. Flag anything legally grey; let the user decide.
- **Leakage-safe joins.** Any point-in-time field (wage, contract, value at transfer date) must use
  the snapshot *strictly before* the event — mirror `ingest/merge.py`'s `merge_asof` with
  `allow_exact_matches=False`.
- **Self-checks.** Each deliverable ships a runnable `_check()`/`--check` with assert-based PASS/FAIL
  against known-truth anchors (named players/clubs whose real numbers you can sanity-check).
- **Output:** graded parquet/csv at the specified path + a `<LANE>_HARVEST.md` report (what you got,
  coverage lift, holes remaining, reachability table, integration status).

---

## LANE A — WAGES (top priority: find them by any legitimate means) 🔴

**Goal:** turn wages from a **grade-C FIFA guess (±55%)** into a **grade-B real-salary layer** across
as many players, leagues and *years* as possible. Wages are half the cost side of every valuation;
this is the single highest-value get. Go deep, exhaust every source, stack them best-grade-first.

**Read first:** `MEMO_wages.md`, `DATA_HARVEST_PLAN.md`, and the wage code:
- `ingest/wages.py` — **the integration point already exists.** `estimate_wage(age, league,
  market_value, position, tm_player_id=None)` returns a `WageEstimate`, and `load_capology_csv(path=
  data/wages/capology.csv)` ingests real wages flagged `source='capology_estimate'`. **A real wage
  keyed to `tm_player_id` is preferred over the FIFA prior automatically.** So your job is to *produce
  the CSVs*, not rewire the model.
- `ingest/wages_fifa.py` — current FIFA-based prior (10,217 players from FIFA 20/21 only).

**Current state (verify):** `data/wages/` has `fifa_players_20.csv`, `fifa_players_21.csv`,
`wages_fifa.parquet`. Only TWO FIFA editions → no wage *time series*, thin non-Big-5.

**Sources to exhaust (stack them, best grade first — pursue ALL, don't stop at one):**
1. **Capology** (`capology.com/uk/premier-league/salaries/` etc.) — per-player **weekly** gross,
   many leagues. Confirmed HTTP 200 from this sandbox. **Primary grade-B target.** Build a resumable
   fetch across all covered leagues + as many historical seasons as the site exposes → normalise to
   annual gross GBP → crosswalk to `tm_player_id` → write `data/wages/capology.csv` in the schema
   `load_capology_csv()` expects (inspect that function for exact columns). Behind a go-ahead flag.
2. **FIFA/EA editions — full history.** You only have 20/21. The same static GitHub-raw source
   (`ifrankandrade/data-visualization`, players_15..23) and other public FIFA-data mirrors give a
   **per-player weekly wage per year 2015–2024** → a real *time series* and a much bigger base
   (incl. Championship/MLS/Argentina). Extend `wages_fifa.py` to load every available edition.
3. **Spotrac / public salary aggregators** — cross-check + fill (esp. MLS/US-reachable data).
4. **Published club accounts → top-down wage bills.** Companies House (UK) + annual reports give the
   *total* wage bill per club per year. Allocate across the squad by minutes×MV to get a grade-C
   per-player prior where nothing else exists — and to **sanity-cap** the model (sum of player wages
   must not exceed the reported bill). This alone catches over/under-estimates.
5. **CIES Football Observatory, community Kaggle/GitHub salary datasets, Wikipedia contract mentions**
   for elite players — low yield but high-grade anchors for the top tail.
6. Any other legitimate source you find. **By any means** = exhaust the legal search space, not skip
   the rules.

**Deliverables:**
- `data/wages/capology.csv` (+ any per-source raw dumps), all crosswalked to `tm_player_id`, graded.
- Extended `wages_fifa.py` covering FIFA 15–24 → a wage time series.
- A **reconciliation**: for a panel of known players (Kane ~£200k/wk, De Bruyne ~£350–400k/wk, etc.)
  show real vs FIFA-prior vs model, and report the correction. Cap-check against club wage bills.
- Coverage lift table: players priced grade-B before→after, by league and by season.
- Wire real wages so `estimate_wage()` returns grade-B where available, C/D fallback elsewhere, always
  flagged. Self-check: a player with a Capology row must return the real number, not the FIFA prior.

**Hole-finding:** report exactly which leagues/seasons/tiers still lack real wages after all sources,
and the best available grade for each — so the user knows the residual ±band per segment.

---

## LANE B — RECENT DEALS & FEES 2023–2026 (keep the model live) 🟠

**Goal:** the canonical spine's fee coverage **collapses after 2022** (2023 8%, 2024 6%, 2025 5%) —
this is *reporting lag*, not a real gap. Backfill recent permanent-transfer **fees + exact dates +
contracts** so the inflation index (`money/inflation.py`, currently gated to 2022) and the
fee-ranker extend to the present. **The user especially wants recent deals.**

**Read first:** `MEMO_stage10_harvest.md`, `DATA_HARVEST_PLAN.md`. The harvester already exists:
`ingest/tm_raw.py` pulls dcaribou RAW via DVC (browser UA + `.dir`-suffix quirk; seasons 2012–2025;
87k dated events, 10k dated fees), and `ingest/merge.py::_enrich_from_raw` folds it in leakage-safe.

**Do:**
1. **Refresh the dcaribou RAW pull** to the latest available season and re-run the enrichment — the
   upstream CC0 dump may already have 2023–2025 fees you don't have yet. Measure the lift.
2. Fill remaining recent fees from other legitimate sources (community CC0 transfer datasets;
   Transfermarkt current-window pages behind a go-ahead flag; reputable transfer-news aggregations
   with a fee field). Grade each; flag rumoured vs confirmed.
3. Re-run `money/inflation.py build` and check whether the **valid range can extend past 2022** once
   coverage clears the audit's threshold. If it can, update the gate; if not, report why.

**Deliverables:** updated canonical enrichment + a coverage table (recent fees before→after), and a
note on whether the inflation index range and fee-ranker now reach the present. Self-check: a handful
of known 2023–2025 deals (e.g. headline summer signings) resolve to the right fee±.

---

## LANE C — CLUB-BY-CLUB REVENUE (Stage 11: the buyer-dispersion unlock) 🟠

**Goal:** the revenue model (`money/revenue.py`) is EPL-central-only and **identical for every club**
(`EQUAL_SHARE=95.1`, `revenue_at_rank(rank)`), so the valuation can't see that a CL place is worth
far more to Man Utd than to a promoted club. Acquire club revenue split into **matchday / broadcast /
commercial** so pricing becomes buyer-specific.

**Read first:** `STAGE11_revenue_dispersion_scope.md` (the full build spec already exists — follow it).
This lane is the **data-acquisition half** of that scope; do not build the model extension, just land
clean data at `data/money/club_revenue.parquet`.

**Sources (all annual, club-level, legitimate):**
1. **Deloitte Football Money League** (annual PDF, top ~30 clubs) — the exact matchday/broadcast/
   commercial split. Use the `anthropic-skills:pdf` skill to extract tables. ~15 yrs history.
2. **UEFA Club Licensing Benchmarking Report** (annual PDF) — broader coverage + owner-funding.
3. **Companies House** statutory accounts for the long tail of UK clubs.
4. **Stadium capacity** static table (cheap join key for matchday).

**Deliverables:** `data/money/club_revenue.parquet`
(`club · season · matchday · broadcast · commercial · total · stadium_capacity · source · grade`),
crosswalked to `to_club_id`. Coverage table by club/season. Self-check: Man Utd commercial ≫ a
promoted club's; totals reconcile to the published headline revenue within a few %.

---

## LANE D — DEFENSIVE / OFF-BALL VALUE (fix the shot-blind spot) 🟡

**Goal:** the impact engine is shot-based, so it **under-measures defenders and deep midfielders**
(they rarely shoot). Compute a defensive/off-ball value layer from raw material **already on disk**.

**Read first:** `NICHE_DATA.md`, and check what exists: `data/fbref/defensive_summary.parquet`,
`data/fbref/niche_summary.parquet`, `data/statsbomb/events/`, `data/statsbomb/turnovers.csv`.
Per the niche-data notes, `socceraction` (VAEP/xT) can run on the StatsBomb events; Wyscout is
CC-BY. Raw material is present — the *value layer* is what's missing.

**Do:**
1. Inventory the defensive/event data (coverage by league/season) — Phase 0.
2. Compute a per-player **off-ball/defensive value** (VAEP or xT from events; tackles/interceptions/
   progressive actions from FBref defensive_summary as a fallback), keyed to `tm_player_id`.
3. Deliver `data/impact/defensive_value.parquet` (graded) + a note on how it *would* enter the usage/
   efficiency model (do not wire it in — flag for a modelling stage). Self-check: known ball-winners
   (e.g. Kanté-type) rank top-decile; pure poachers rank low on defensive value.

---

## Final deliverable (each agent)
A `<LANE>_HARVEST.md` with: Phase-0 hole map, reachability table (source → status code → route),
what was acquired (counts + grades), coverage lift (before→after), residual holes with best-available
grade per segment, integration status, and PASS/FAIL self-checks. Plus a one-paragraph honest verdict:
did this move the pillar up a grade, and where is it still weak?

**Governing principle:** understand first, fetch to fill measured holes, grade everything, crosswalk to
`tm_player_id`, keep scrapes personal-use + behind a go-ahead, never fabricate, and prove it with a
self-check. Wages get the most effort. Recent deals get real attention. Leave nothing dangling that a
five-minute follow-up would have closed — but this task is to EXECUTE the harvest, not to re-plan it.
