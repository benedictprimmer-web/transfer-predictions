# REVIEW 00 — Scope & plan of record

*Fable orchestrator, 2026-07-12. Full data→model review per `REVIEW_fable_prompt.md`. Thesis under
test: the two-model hypothesis — a price-blind **talent model** vs a **price model**; the edge is
players whose talent rank sits far above their price rank.*

## Scorecard skeleton (headline deliverable — filled in `REVIEW_verdict.md`)

| Axis | Grade | Where it stands (one line) | Highest-value next move |
|---|---|---|---|
| 1 · Quantity of data | | | |
| 2 · Quality of data | | | |
| 3 · Usefulness (fitness for the questions) | | | |
| 4 · Visualisation | | | |
| 5 · Modelling | | | |

## Phase questions

- **P1 (A1–A7):** coverage limits per use-case · dataset reliability/leakage/licence · talent-vs-price
  separability (the core, with numbers) · modelling design (trained model? one or many? target?) ·
  stack/repo fitness + proposal · what can we show that impresses · commodity-vs-proprietary honesty.
- **P2:** every material claim adversarially refuted — CONFIRMED / REVISED / REFUTED. Nothing
  unverified reaches the roadmap.
- **P3:** B1 known-players ranking (no outcome peeking) · B2 gem screen + historical backtest of the
  method · B3 live Transfermarkt rumour verdicts (good/bad/can't-say + reason, no-coverage flagged).
- **P4:** verdict + explicit answers to all owner questions + gated improvement wave.

## Priors (from maps + warehouse census, 2026-07-12 — to be confirmed or refuted, not assumed)

1. **Quantity**: strong spine — 539,971 Understat shots (Big-5 2014-24, frozen), 234,800 selling-league
   shots (2018+), 134k canonical transfers (1992–2026), 507k valuations, 771k Elo rows. Thin: wages
   beyond 8 Capology leagues, PIT contracts, selling leagues pre-2018, anything post-Jan-2025 Understat.
2. **Quality**: one **known live defect** (random KFold on time-ordered data, `money/fees.py::fit_residuals`,
   MODELLING_PLAN L6). Join ceilings: Understat→TM crosswalk 76.1% (6,390/8,399); 24% of
   transfers_canonical rows NULL player_id; 17% of shots_selling NULL tm_player_id. Contracts are
   current-state, not PIT (leakage risk if promoted). Licences: StatsBomb/TM/Opta/Understat all block
   commercial shipping — research-grade only today.
3. **The sauce**: price-blind signals exist (usage, own xG, WOWY, aging, injuries, turnovers, defensive
   layer) and the money layer is separate by construction. Separability is **untested** — the core
   unknown of this review.
4. **Modelling**: no trained primary model in production; a hand-built mechanistic chain (NPV, r≈0.08
   predictor) plus a planned-but-defective supervised fee model. Two philosophies (SPEC mechanistic vs
   MODELLING_PLAN supervised) not merged. Stage-4 gate survives on corrected data (WOWY r=+0.077).
5. **Stack/repo**: DuckDB+parquet+Makefile fits the scale; but **no git repo**, no tests/ dir, no
   packaging, self-checks proven insufficient (£425m blow-up, numpy cache corruption passed green).
6. **Viz**: two live artifacts (dossier, dashboard) + a 50-map descriptive spec. Nothing yet shows the
   thesis (talent-vs-price gap).
7. **Competitive**: data is largely commodity (public mirrors); if an edge exists it is the *method*
   (two-model gap, NPV framing, gate discipline) — to be argued honestly in A7.

## Rules of engagement
Query-don't-crawl (warehouse, `python3`); structured JSON returns; every claim carries evidence or is
marked unverified; refute before trusting; never loosen a gate; honest "can't judge" beats confident guess.
