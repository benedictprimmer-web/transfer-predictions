# Transfer Predictions

A football transfer valuation and scouting research system. Built to keep future availability,
sporting rate, total contribution, market-consensus value, negotiated fee, and buyer-specific
economics as separate, falsifiable questions instead of one black-box number.

## About

Most transfer-value tools collapse "is he good," "what's he worth," and "what will he cost" into
a single price prediction. This project keeps them apart on purpose:

```
timestamped player snapshot
        ↓
future minutes / availability             (price-blind, not sporting quality)
        ↓
future sporting rate                      (conditional on observed playing time)
        ↓
total contribution challenger             (derived, not ground truth)
        ↓
market-consensus and negotiated-fee diagnostics
        ↓
uncertainty propagation                   (a point estimate is a lie)
        ↓
abstaining decision support
```

The core mechanism is **usage is zero-sum**: `team_output = Σ(usage_i × efficiency_i)`. A signing
only helps if his efficiency beats the weighted efficiency of the playing time he displaces — so
"individually good" and "actually helps this team" are checked as two different claims, not one.
The acceptance test for the whole engine is Cristiano Ronaldo's 2021-22 season at Manchester
United: excellent by his own numbers, and the team was −0.25 xGD/90 worse with him on the pitch.
If a model can't reproduce that gap, it doesn't ship.

## The discipline that makes the numbers trustworthy

Every stage of this pipeline sits behind a **falsifiable gate**, decided before the result is
seen, and **never loosened to make a number look better**. A finding that fails its gate ships as
a documented limitation, not a quiet omission — for example, league-strength adjustment and raw
age curves both failed their predictor gates and are kept out of the price, not forced in. This
matters in practice: the project has caught two silent-corruption bugs (a £425m valuation
blow-up, a numpy-version cache corruption) that a green self-check alone would have missed —
gates run on real out-of-time behaviour, not on "the code ran."

A July 2026 adversarial review (70 sub-agent passes, every material claim independently
re-verified) graded the estate honestly rather than generously:

| Axis | Grade | Headline |
|---|---|---|
| Quantity of data | C | Deep Big-5 attacker spine (540k+ shots, 134k transfers, 508k valuations), but frozen and position-skewed |
| Quality of data | C | Internal hygiene good; one confirmed time-leak found and fixed; estate is research-grade, not licensed for resale |
| Usefulness | C− | Works well for attackers; the original "cheap gem" screen didn't beat the base rate |
| Visualisation | B | Investor-presentable dossier and data-room artifacts already live |
| Modelling | C | No trained model at review time — since built and gated (see below) |

## What's actually been proven

- **A price-blind talent model** (`impact/talent.py`) beats an age-only baseline out-of-time
  (Spearman lift +0.150, CI clear of zero) and its reformulated "undervalued player" screen
  catches real gems at 23.5% precision against a 13.2% base rate — reversing the review's
  original negative finding. Two of its four gates still fail honestly (see
  [`MODEL_verdict.md`](MODEL_verdict.md)): a star's injury-shortened season can misread as an
  ordinary one, and non-Big-5 sellers (e.g. Eredivisie) aren't covered yet. **Verdict: edge
  present, not yet proven** — reported as such, not rounded up.
- **The Sporting MVP correction** (`validate/sporting_mvp_*`) now uses S0 age/role,
  M0 prior availability/freshness, and S1 incremental sporting-rate evidence. It formally
  abstains with `ABSTAIN_INSUFFICIENT_TEMPORAL_RATE_COVERAGE`: only 2021 and 2022 are
  informative S1 folds. This is a minutes/availability diagnostic, not evidence that
  future sporting quality is predictable or unpredictable.
- **The NPV chain** (`money/npv.py`, `money/price.py`) remains exploratory. It is not the
  recommended headline product path and must not be used as a validated buyer-specific surplus
  or player-ranking claim without a separately approved buyer context and validation design.
- **A fee model** (`money/fees.py`) trained on real, disclosed transfer fees (the one part of the
  system with actual ground truth) with season-grouped, expanding-window validation — no random
  cross-validation anywhere near time-ordered data.

## Repository map

| Path | What |
|---|---|
| `ingest/` | Data acquisition — Understat shots, Transfermarkt, FBref, StatsBomb, injuries, wages, the DuckDB warehouse |
| `impact/` | On-pitch value — usage/efficiency, aging curves, WOWY, the price-blind talent model |
| `money/` | Economic diagnostics — fees, wages, revenue, archived exploratory NPV/scout board |
| `validate/` | Every falsifiable gate, run independently of the model that must pass it |
| `data/` | ~1.2GB local warehouse (gitignored raw cache; parquet working set tracked) — see `data/README.md` |
| `HANDOFF.md` | Full current state and next steps, for picking this up cold |
| `MODELS.md` | The modelling decisions and why, stage by stage |

## Quickstart

```bash
python3 -m ingest.warehouse build      # assemble the DuckDB warehouse from data/ (once)
make checks                            # every module's offline self-check (no network)
python3 -m validate.talent_gate run    # the talent model's four gates, on real data
python3 -m validate.sporting_mvp_integrity
python3 -m validate.sporting_mvp_models
```

## Honest limits

This is a research/portfolio project, not a commercial product. The underlying data
(StatsBomb, Transfermarkt, FBref, Understat) carries non-commercial or database-rights
restrictions — see `LICENCES.md` — so raw data isn't shipped or redistributable, and nothing
here is investment or transfer advice. What's genuinely reusable is the method: the gate
discipline, the NPV framing, and the assembled cross-source join (a 100% game crosswalk, a
76%+ player crosswalk across 15 tables), not the data itself.
