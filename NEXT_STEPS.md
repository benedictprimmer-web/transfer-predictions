# Next steps — pathways, and what we use vs ignore

*Written 2026-07-12, after the data clean. Companion to `DATA_INDEX.md` (what we hold) and the
two visual reports. This doc is about **direction**: where to spend effort next, along three
pathways — gathering, processing, analysis — and an explicit account of which data points the
model uses for which job, and why it ignores the rest.*

---

## The one move that matters most

**Compute xT / VAEP from the StatsBomb events already on disk.**

Everything below is real, but this is the single highest-value step. Today the model counts value
only at *shots and the pass before them*, so it is sharp for forwards and blind to defenders and
deep midfielders. xT (expected threat) / VAEP (valuing actions by success) put a number on
*every* action — a progressive carry, an interception, a line-breaking pass — which is the root
fix for the blind spot, not another patch. The data is on disk (`data/statsbomb/`, `socceraction`
is the standard library), so this is a *processing* task, not a *gathering* one. Start here.

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

1. **xT / VAEP from StatsBomb events** *(the top move — see above)*. Output: a per-player,
   per-season action-value that finally scores defending and build-up. Wire it into `impact/`
   next to `usage.py` and `xg_model.py`.
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
| **xT / VAEP** | Not computed yet | It's built from the StatsBomb events — **do this first** |
| **Defensive layer** | Unitless; can't be priced | It's calibrated to an xT-value scale |
| **League strength** | Failed its predictive gate | It passes a real out-of-sample test (don't force it) |
| **Club revenue series** | Only a COVID-season POC | The year-by-year extraction is worth the effort (buyer-specific pricing demand) |
| **Raw age curves** | Failed the predictor gate | Kept in NPV as a shape, not a point predictor — leave as is |

**The discipline that makes this trustworthy:** signals enter the *price* only after passing a
predictive gate; anything that fails stays descriptive. Sub-agents' self-checks have passed while
results were broken (a £425m inflation blow-up, a numpy downgrade that silently corrupted the shot
cache) — so gate on *behaviour and backtests*, never on "the check went green."

---

## Suggested order (next ~5 moves)

1. **xT / VAEP** from StatsBomb events → the defender/midfielder fix *(Pathway B)*
2. **Calibrate the defensive layer** onto the xT scale so it can be priced *(B)*
3. **Ship the undervaluation screen** on current data; re-sharpen once xT lands *(C)*
4. **Widen selling-league xG + wages** in the leagues where the market is softest *(A)*
5. **Buyer-specific pricing** once (or if) the revenue series is worth building *(A→C)*
