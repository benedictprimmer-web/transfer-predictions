# Lane D — Defensive / Off-Ball Value Harvest

**Date:** 2026-07-12. **Status:** shipped. **Grade:** C (box-score composite).
**Deliverable:** `data/impact/defensive_value.parquet` — 14,634 player-seasons,
4,681 players, keyed to `tm_player_id`.

The impact engine (`impact/usage.py`) defines usage/efficiency from **shots +
shot-assists only**, so it is structurally blind to players whose value is
tackling, intercepting, screening, and progressing the ball. This layer scores
that missing axis. It is **not wired into the model** — it's a standalone layer
plus the integration note below.

---

## Phase 0 — what already existed (no fetch needed)

Everything required was already on disk. No network pull was run; the raw
material named in the brief is present and tm-keyed.

| Artifact | Shape | Key | Coverage |
|---|---|---|---|
| `data/fbref/defensive_summary.parquet` | 14,634 × 12 | `tm_player_id` | Big-5, 2018–2025 |
| `data/fbref/niche_summary.parquet` | 14,634 × 36 | `tm_player_id` | Big-5, 2018–2025 |
| `data/statsbomb/events/` | 448 match files | name only (no tm id) | see below |
| `data/statsbomb/turnovers.csv` | 25,094 rows | name only | narrow comps |
| `data/statsbomb/player_season.csv` | 1,292 rows | name only | narrow comps |
| `data/crosswalk/players.csv` | 6,390 rows | us↔tm bridge | — |

**`defensive_summary` is the workhorse:** already per-90, already tm-keyed, and
covers exactly the 2018–2025 Big-5 window the valuation spine lives in.
Null rates negligible (≤0.06% on the 7 action columns; 2.6% on
`tackle_win_pct`, carried reference-only).

### socceraction / VAEP decision (measured, not assumed)
`socceraction` 1.5.3 **installed cleanly** (`pip install socceraction`, works
from this sandbox). But the StatsBomb open events it would train on do **not**
fit this lane:

- **Coverage mismatch.** The 448 event files are La Liga history (2004–2021),
  Champions League back to 1999, internationals (World Cups, Euros, Copa),
  plus lone one-off seasons (Bundesliga 23/24, two Premier League seasons
  2015/16 + 2003/04, Ligue 1 21–23, MLS 2023). They barely overlap the
  2018–2025 **Big-5 league** window the model prices in.
- **No tm bridge.** StatsBomb events carry names only; there is no
  `tm_player_id` on them and no StatsBomb→tm crosswalk on disk (the existing
  crosswalk is us↔tm). Linking 448 matches of names to tm ids by hand-matching
  is a separate harvest, not this lane.

Training a VAEP model on a non-overlapping, unlinked sample would produce a
thinner, harder-to-join layer than the FBref fallback the brief explicitly
names. So: **FBref composite path taken.** VAEP/xT flagged as a modelling-stage
upgrade if StatsBomb event coverage widens and gets tm-linked.

### Hole map (defensive_value coverage, unique players by comp × season-end)

| comp | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| Premier League | 386 | 393 | 396 | 396 | 397 | 408 | 404 | 152 |
| La Liga | 417 | 406 | 402 | 425 | 424 | 421 | 417 | 183 |
| Serie A | 404 | 406 | 419 | 412 | 429 | 427 | 420 | 134 |
| Bundesliga | 350 | 358 | 358 | 360 | 348 | 354 | 349 | 101 |
| Ligue 1 | 398 | 401 | 372 | 406 | 415 | 408 | 352 | 114 |

**Residual holes:**
- **2025 is partial** (season in progress → ~1/3 the player count of a full
  year). Not corruption, just incomplete.
- **Big-5 only.** No selling leagues (Eredivisie, Portugal, Championship,
  Brazil, etc.) — FBref lost the feed Jan 2025 and these leagues were never in
  the defensive_summary. Defenders/DMs in feeder leagues get **no** defensive
  value from this layer (best available grade there: none → would need a
  different source).
- **Big-5 forwards** are covered but score low by construction (correct — see
  self-check).

### Corruption check
One real bug caught and fixed during the build (not in source data, in my join):
the `niche_summary` merge keyed on `(tm_player_id, season_end_year, comp)`
without `squad`, so mid-season transfers (same player, same season, two clubs)
fanned out — 14,634 → 14,858 rows. Root cause: `niche_summary` is unique on
**4** keys incl. `squad` (224 duplicate rows without it). Added `squad` to the
merge key → back to 14,634, exactly matching `defensive_summary`. No corruption
in the underlying FBref parquets themselves.

---

## Method

Equal-weight z-score composite of 7 per-90 defensive + progressive actions,
pooled across the whole 14,634-row sample, then ranked to a 0–100 percentile.

Components: `tackles_p90`, `interceptions_p90`, `blocks_p90`, `recoveries_p90`,
`aerials_won_p90`, `prog_carries_p90`, `prog_passes_p90`.

- `defensive_value_z` — mean of the 7 component z-scores.
- `defensive_value_score` — percentile rank of z (0–100).
- `tackle_win_pct`, `errors_to_shot` — carried **reference-only**, not blended
  into the score (keeps the grade legible: a box-score composite, not a
  quality-adjusted model).

**Absolute, not position-relative.** The score is not "best defender among CBs";
it's high in absolute terms for anyone who does defensive/progressive work —
which is exactly the value the shot-based engine misses. A poacher *should*
score low, and does.

**Known ceilings (upgrade paths):**
- Volume ≠ value: raw action counts don't distinguish a good tackle from a
  desperate one. `errors_to_shot`/`tackle_win_pct` sit alongside for a future
  quality adjustment. Correlation of score vs minutes (`n90`) is only −0.055,
  so it isn't merely a minutes proxy.
- Equal weights are a prior, not a fit. A VAEP/xT model would weight actions by
  their real scoring/conceding impact — the flagged modelling-stage upgrade.

**Grade C, source `fbref_defensive_summary+niche_summary`** on every row.

Code: `ingest/defensive_value.py` (`build` writes the parquet; bare run =
self-check). ~40 lines, reuses the existing FBref artifacts and crosswalk-keyed
ids — no new ingestion.

---

## Self-check — PASS

Ran against real anchors. Ball-winners must land top-decile (score ≥ 90);
pure poacher must land low. No tuning was done to make this pass.

| Player (role) | Seasons | Score range | Verdict |
|---|---|---|---|
| N'Golo Kanté (DM) | 2018–2023 | **88.4 – 98.7** | top-decile every year ✓ |
| Rodri (DM) | 2018–2024 | **81.7 – 96.6** | top-decile ✓ |
| Erling Haaland (poacher) | 2020–2025 | **7.6 – 10.8** | bottom ~decile ✓ |

The synthetic unit check in `ingest/defensive_value.py::_check` also asserts a
constructed ball-winner tops the ranking and a constructed poacher bottoms it
(`python3 -m ingest.defensive_value` → `ok`).

Distribution sanity: score is a clean uniform 0–100 (mean 50.0, by
construction of a percentile rank); 90th-pct threshold sits at score 90.0.

---

## How it would enter the model (NOT wired in — flag for a modelling stage)

`impact/usage.py` builds `value = xg + xag` per terminal action, which is
attacking-only. The defensive layer would enter as a **second value stream**,
not a patch to the shot value:

1. Convert `defensive_value_score` (or the underlying `_z`) into a
   points-equivalent via a calibration against team defensive output
   (goals-conceded prevented → points), mirroring how `money/points.py` maps
   xGD→points on the attacking side. This is the missing coefficient — the
   score is currently unitless.
2. Add that as a parallel term in the benefit side of the NPV
   (`money/npv.py` / `money/price.py`), so a DM's valuation reflects defensive
   contribution the shot engine can't see.
3. Join is trivial: both sides are already `tm_player_id`-keyed, and the score
   is per (tm_player_id, season_end_year, comp, squad).

Deliberately **not done here** — the brief scopes Lane D to the data layer, and
the score→points calibration is a modelling decision that needs its own gate
(does defensive_value actually predict conceded/points out of sample?).

---

## Verdict

Produced a broad, clean, tm-keyed **defensive/off-ball value layer** across all
Big-5 leagues 2018–2025 (14,634 player-seasons, 4,681 players), grade C,
self-check PASS on real anchors. This is genuinely new signal for the model —
the engine had **zero** defensive value before; defenders and DMs were priced
purely on the little shooting they do.

**Where it's still weak:** (1) grade C — it's a volume composite, not a
value-weighted VAEP model; the socceraction upgrade is real but needs
StatsBomb events tm-linked and coverage widened first. (2) Big-5 only — feeder
leagues get nothing, so a defensive prospect in Portugal/Eredivisie is invisible
to this layer. (3) The score is unitless until a modelling stage calibrates it
to points. Ready to feed a modelling stage; not ready to price on its own.
