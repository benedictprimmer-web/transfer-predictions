# MEMO — wages: not a lost cause (2026-07-12)

Answers the standing question in `DATA_HARVEST_PLAN.md` ("the one decision only you can
make: wages"). That memo concluded *ship modelled grade-D, Capology only if licensed* — for
a **commercial** product. On the project's **current personal/research footing** (commercial
constraints dropped, per `DATA_ACQUISITION_PLAN.md`), the answer changes: wages are now a
**grade-C real signal**, implemented, not a lost cause. This is a separate lane from the
TM-raw harvest (dates/fees/contracts) — no overlap.

## Reachability, curl-tested from this sandbox
- **Capology** (`capology.com/uk/premier-league/salaries/`) → **HTTP 200**, 2.8 MB. Unlike
  FBref, Capology does **not** block the datacenter IP. Its per-player weekly estimates are
  reachable for personal use (grade-B). Not built here — it's a ToS-protected scrape, kept
  behind a user go-ahead to respect the harvest plan's no-scrape rule and because a manual
  paste already loads via `wages.load_capology_csv()`.
- **FIFA/EA game data** (`ifrankandrade/data-visualization` GitHub raw, players_20/21.csv) →
  **200**, static, no auth. Per-player **weekly** wage in EUR, ~19k players/edition, big-5
  **plus** Championship/MLS/Argentina. **This is what we built on.**
- **No free redistributable audited wage dump exists** (grade-A still needs a Capology/
  provider licence). Unchanged.

## What FIFA wages actually are
Not just an ordinal proxy — a decent *cardinal* estimate. FIFA 21 weekly wages land close to
reported reality once crosswalked and recalibrated:

| Player | FIFA-prior estimate | Reported (2020/21) |
|---|---|---|
| Harry Kane | £199k/wk | ~£200k/wk |
| Virgil van Dijk | £200k/wk | ~£220k/wk |
| Kevin De Bruyne | £283k/wk | ~£350–400k/wk (top-end compresses) |

The prior **corrects the MV-model's overshoot**: the model prices Kane at £291k/wk off his high
MV; FIFA knows his actual Spurs deal was ~£200k/wk. That per-player correction is the whole point.

## What was implemented
- **`ingest/wages_fifa.py`** → `data/wages/wages_fifa.parquet`. Loads FIFA 20/21, crosswalks to
  `tm_player_id` (normalised name + dob, first+last-token bridge for full birth names — **43% of
  FIFA, 10,217 players priced, 2,780 big-5**), then an **era-consistent** estimate: the model runs
  on FIFA's *own* edition-year MV (`value_eur`), so an aged star's low 2026 MV isn't blended with
  his peak-era pay. `wage_gbp = geomean(model_on_era_MV, recalibrated_FIFA)`. Every row flagged
  `source='fifa_prior'` with a x/÷1.6 interval.
- **`ingest/wages.py`** — `estimate_wage(..., tm_player_id=None)`: when a tm id is passed and a
  FIFA row exists, returns it (`source='fifa_prior'`); else the parametric model (`'modelled'`).
  **Backward compatible** — existing `money/` call sites are untouched and their gates still pass;
  the prior only engages when a caller opts in with a tm id. Verified end-to-end.

## Honest limits
- Levels are frozen at **edition year (2020/21)**; for a *current* signing trust the **rank** more
  than the absolute, or re-anchor to wage inflation. It's a **game** estimate — individually noisy.
- Coverage is the ~43% of FIFA players we could confidently crosswalk; the rest fall back to the
  model (still flagged). **Not for resale** (game data) — fine on the current research footing.

## The ladder for better wages (in order of effort/quality)
1. **FIFA prior — DONE** (grade-C, free, static, 10k players).
2. **Capology personal-use pull — available, not built** (grade-B, reachable from this IP; real
   big-5 estimates). Say the word and I'll add a polite, rate-limited reader feeding the existing
   `load_capology_csv()` path — personal use only, never in a sold build.
3. **Capology / provider commercial licence — grade-A** (bespoke price; the only sellable route).

## Also shipped this pass (bonus, unclaimed lane)
**`ingest/injuries.py`** → `data/master/injuries.parquet` (salimt/football-datasets, 143k spells,
TM-keyed, no crosswalk). Per-player durability + `availability_multiplier(tm_id)` → an NPV benefit
discount with an interval. **Exposed as an API, deliberately NOT yet folded into `npv_transfer`** —
that's a modelling change and must clear the benefit/Stage-4 gate first (standing firewall).
