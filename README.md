# Transfer Predictions

A football transfer valuation and scouting system: which players are worth signing, and how much
should you pay? Built to keep sporting quality, market price, and the negotiated fee as separate,
falsifiable questions instead of one black-box number.

## About

Most transfer-value tools collapse "is he good," "what's he worth," and "what will he cost" into
a single price prediction. This project keeps them apart on purpose:

```
timestamped player snapshot
        ↓
future performance & minutes forecast     (sporting quality — price-blind)
        ↓
replacement-based importance              (how much of it is his)
        ↓
economic player value                     (what that's worth to a specific club)
        ↓
separate fee & wage models                (what the market actually charges)
        ↓
uncertainty propagation                   (a point estimate is a lie)
        ↓
underpriced-player ranking
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
- **The NPV chain** (`money/npv.py`, `money/price.py`) separates cost (fee + wages, amortised)
  from benefit (xGD → league position → broadcast/prize revenue, with a real Champions-League
  cliff) and correctly ranks known cases: Antony's £85m move to Manchester United reads deeply
  negative NPV, Erling Haaland's £51m release clause reads as the bargain it was.
- **A fee model** (`money/fees.py`) trained on real, disclosed transfer fees (the one part of the
  system with actual ground truth) with season-grouped, expanding-window validation — no random
  cross-validation anywhere near time-ordered data.

## Repository map

| Path | What |
|---|---|
| `ingest/` | Data acquisition — Understat shots, Transfermarkt, FBref, StatsBomb, injuries, wages, the DuckDB warehouse |
| `impact/` | On-pitch value — usage/efficiency, aging curves, WOWY, the price-blind talent model |
| `money/` | Economic layer — fees, wages, revenue, NPV, the scouting board |
| `validate/` | Every falsifiable gate, run independently of the model that must pass it |
| `data/` | ~1.2GB local warehouse (gitignored raw cache; parquet working set tracked) — see `data/README.md` |
| `HANDOFF.md` | Full current state and next steps, for picking this up cold |
| `MODELS.md` | The modelling decisions and why, stage by stage |

## Quickstart

```bash
python3 -m ingest.warehouse build      # assemble the DuckDB warehouse from data/ (once)
make checks                            # every module's offline self-check (no network)
python3 -m validate.talent_gate run    # the talent model's four gates, on real data
python3 -m money.scout run --to Arsenal --top 20
```

## Honest limits

This is a research/portfolio project, not a commercial product. The underlying data
(StatsBomb, Transfermarkt, FBref, Understat) carries non-commercial or database-rights
restrictions — see `LICENCES.md` — so raw data isn't shipped or redistributable, and nothing
here is investment or transfer advice. What's genuinely reusable is the method: the gate
discipline, the NPV framing, and the assembled cross-source join (a 100% game crosswalk, a
76%+ player crosswalk across 15 tables), not the data itself.
