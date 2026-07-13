# Next steps — pathways, and what we use vs ignore

*Written 2026-07-12, after the data clean. Companion to `DATA_INDEX.md` (what we hold) and the
two visual reports. This doc is about **direction**: where to spend effort next, along three
pathways — gathering, processing, analysis — and an explicit account of which data points the
model uses for which job, and why it ignores the rest.*

---

## Update (2026-07-12, later same day): superseded below

Both moves this doc originally pointed to are now **done**, not pending:

- **xT / VAEP was built** (`ingest/xt.py` + `possession_value.py`, self-fit on StatsBomb, no
  `socceraction`) — and it **failed its NPV gate** (`validate/possession_gate.py`, coef≈0). It ships
  as a descriptive scout flag only, not priced. Don't re-attempt it expecting a different answer;
  the gate result is the finding.
- **The price-blind talent model was then built** (`impact/talent.py`, `validate/talent_gate.py`,
  scoped by `transfer-model-improvement/BUILD_PLAN.md` + `GATES.md`). Gates 1 (beats age-only
  baseline) and 4 (reformulated gem screen beats base rate) **pass**; gates 2 (Haaland/Antony
  sanity) and 3 (decile monotonicity) **fail**, for specific, named reasons — see `MODEL_verdict.md`.
  A first fix attempt for gate 2 (a single-season injury-day count) was tried and made it worse
  (reverted, documented in the same file).

**The one move that matters most, as of now**, per `MODEL_verdict.md`'s own "what would close the
gap" section:

1. **A career-shape minutes feature** (trailing 2-3 season n90s trend, not a raw injury-day count)
   to fix gate 2's Haaland-class injury/fringe-player confound — untried; the raw-count version
   that *was* tried backfired.
2. **Wire `shots_selling` (234,800 rows, already on disk) into the talent panel** to close the
   Antony-class selling-league blind spot — the standing fix, not yet done for this model.
3. **Re-check gate 3's monotonicity at quintile granularity** before concluding the relationship is
   flawed rather than under-powered at the decile level.

Everything below this point is the *original* doc and is otherwise still accurate, but its framing
of xT/VAEP as "not yet done" is stale — treat the update above as the current priority list.

---

## Three pathways

Think of the work as three lanes that feed each other. Most weeks you want one active step in
each, not all effort in one lane.

### Pathway A — Data gathering (acquire what we don't have)

Ranked by value-per-effort. We are **not** short of data in general; we are short in specific,
named places.

| Priority | Get | Why | Effort | Blocker / route |
|---|---|---|---|---|
| High | **More selling-league xG** (Belgium, Argentina, more Brazil/Portugal seasons) | Widens the "find them before the big clubs" edge where the market is least efficient | Med | worldfootballR_data release assets (proven route); residential IP for live FBref |
| High | **Wages beyond the 8 Capology leagues** | Cost side is the weakest link outside the covered leagues; a real wage swings NPV hard | Med | Capology personal-use scraping (already wired); watch rate limits |
| Med | **Club revenue time series** (Deloitte year-by-year) | Makes valuations buyer-specific (a fee is what *that* club will pay) | High | Deloitte PDFs are fiddly; POC proves it works — see `scratchpad/lanec_pdfs/`. Low yield for now — parked on purpose |
| Med | **Contract *history*** (not just current expiry) | PIT amortisation needs expiries as they were, not as they are | Med | dcaribou RAW via DVC has some; gaps remain |
| Low | Newer Understat seasons | Mirror is archived at Jan 2025; no clean live route from here | High | Blocked — residential only. Don't chase |

**Rule for this lane:** never gather what we already reduce to a parquet, and never gather a
source we can't legally ship if the product ships. Check `LICENCES.md` *before* scraping, not after.

### Pathway B — Data processing (compute new signal from what we hold)

This is where the leverage is — most of the value is *latent in data already on disk*.

1. ~~xT / VAEP from StatsBomb events~~ **Done — failed its NPV gate, descriptive only** (see the
   update at the top of this doc). The defender/build-up blind spot it was meant to fix is now
   partially addressed instead by the price-blind talent model's defensive-action features.
2. **Calibrate the defensive layer to a value.** It exists (`ingest/defensive_value.py`) but is
   unitless, so it can't be priced. Once xT lands, anchor the defensive composite to xT-value and
   it graduates from descriptive to priced.
3. **Extend the fee-inflation index forward** as new transfers land, and **re-fit the discount
   rate** when the football-growth assumption (`g`) can be measured rather than assumed.
4. **Backfill wages** by blending Capology (real) with the FIFA prior more carefully per era, so
   the ±15%/±55% gap narrows for partially-covered players.

### Pathway C — Data analysis (answer questions, ship outputs)

What the processed data is *for*.

1. **The undervaluation screen.** The best signal for a cheap player: **high efficiency at low
   usage, young, cheap vs market value** — a good player stuck in a small role at a small club the
   market hasn't repriced. This is shippable *today* from existing data; xT will sharpen it for
   non-forwards.
2. **Buyer-specific pricing.** Once the revenue series exists, price the same player differently
   for a CL side vs a mid-table club (the COVID-season POC already shows this works).
3. **Backtest discipline.** Keep running `validate/npv_backtest.py` on every model change — the
   Haaland-vs-Antony £60m gap is the sanity anchor. A change that widens known-good gaps is right;
   one that compresses them is a regression.

---

## What we use, what we ignore — and why

The model is **deliberately partial**. It prices what it can measure *and defend*. This table is
the standing policy; revisit a row only when its "why" changes.

### Priced in

| Signal | Used for | Why it's in |
|---|---|---|
| **Usage rate** (shot & key-pass share) | The core contribution measure | Most predictive input; cheap to compute anywhere shots exist |
| **xG / shot geometry** | Output value (goals) | Where goals actually come from; our own xG adds pitch-position fidelity |
| **Market value + transacted fees** | Price anchor + training target | Calibrates to reality; the fee model's supervision signal |
| **Real wages (Capology)** | Cost side of NPV | A real ±15% wage beats a ±55% guess; flows straight to present value |
| **Contract length** | Amortisation | A fee is spread over contract years; length changes the annual cost |
| **Injury / durability** | Availability discount | Expected minutes, not nominal ability, is what you pay for |
| **ClubElo strength** | Opponent-quality context | Normalises performance without over-claiming a league effect |

### Held out (and the condition to bring it in)

| Signal | Why it's out | Bring it in when |
|---|---|---|
| **xT / VAEP** | Built, but failed its NPV gate (coef≈0) | It passes a real out-of-sample repricing test (not attempted again without new signal) |
| **Defensive layer** | Unitless; can't be priced | It's calibrated to an xT-value scale |
| **League strength** | Failed its predictive gate | It passes a real out-of-sample test (don't force it) |
| **Club revenue series** | Only a COVID-season POC | The year-by-year extraction is worth the effort (buyer-specific pricing demand) |
| **Raw age curves** | Failed the predictor gate | Kept in NPV as a shape, not a point predictor — leave as is |

**The discipline that makes this trustworthy:** signals enter the *price* only after passing a
predictive gate; anything that fails stays descriptive. Sub-agents' self-checks have passed while
results were broken (a £425m inflation blow-up, a numpy downgrade that silently corrupted the shot
cache) — so gate on *behaviour and backtests*, never on "the check went green."

---

## Suggested order (next ~5 moves) — superseded, see the update at the top

1. ~~xT / VAEP~~ **done, failed gate** — no longer next
2. ~~Calibrate defensive layer onto xT scale~~ — moot, since xT didn't pass the gate it would've been
   calibrated against; the talent model's defensive features are the live path instead
3. **Career-shape minutes feature** for talent-model gate 2 *(Pathway B — new #1)*
4. **Wire `shots_selling` into the talent panel** for gate 2's Antony-class blind spot *(B)*
5. **Ship the undervaluation screen** on current data (gate 4 already passes) *(C)*
