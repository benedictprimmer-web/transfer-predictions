# Deep Audit & Analysis Prompt — Football Transfer Inflation Index

**Purpose:** Hand this to a fresh model/agent. It must (1) audit whether the data can support a
transfer-fee inflation index, then (2) *build* that index and deliver a validated function that
scales any historical fee to any target year — correcting for **time inflation AND football-market
inflation**, which are different things.

Do not deflate fees by CPI. CPI is the wrong deflator here; the whole point is to measure the
sector-specific index and compare it to CPI as a diagnostic, not use CPI as the answer.

---

## 0. Context you are inheriting

- Working dir: `/Users/benrimmer/Transfer Predictions`
- Primary data: `data/merged/transfers_canonical.parquet` (~124k transfers, ~57% fee coverage).
  Confirm the real schema before assuming columns — do NOT trust this list blindly:
  expected-ish fields: player id/name, from_club, to_club, from_league, to_league, season/date,
  fee (nominal), fee_currency, transfer_type (permanent/loan/free/loan-with-option), position, age,
  market_value (Transfermarkt), contract_length if present.
- Companion estates per `HANDOFF.md` and `AUDIT.md` (read both first). Transfermarkt market-value
  dumps and Understat output metrics exist next door and can be bridged (~11k players via TM→FBref).

**First action: read `HANDOFF.md`, `AUDIT.md`, then load the parquet and print
`df.info()`, dtypes, min/max date, currency mix, and fee null-rate by year. Everything below
depends on what you actually find, not on this description.**

---

## 1. Audit phase (prove the data can answer the question) — do this BEFORE modelling

Produce an `INFLATION_AUDIT.md` answering each, with numbers:

1. **Currency & real-value hygiene.** Are fees stored in one currency or many? If mixed
   (£/€/$), how are they converted, and at *what date's* FX rate? A €222m fee converted at
   today's GBP rate vs 2017's rate materially changes the index. Decide and document one rule.
2. **Fee definition drift.** Do "fees" include add-ons/sell-on clauses/loan fees, or just the
   base? Are release-clause activations (Neymar, Griezmann) flagged? These are structurally
   different transactions and can distort the top tail.
3. **Coverage bias over time.** Plot fee non-null rate by year and by league tier. Older years
   and smaller leagues under-report fees and under-report *small* fees especially → naive
   yearly-mean inflation will be overstated by survivorship. Quantify this.
4. **Free/loan contamination.** Confirm frees are £0 not null, and loans are excluded (or
   loan fees separated). A shifting free-transfer share fakes deflation.
5. **The tail.** Report yearly p50 / p90 / p99 / max of fees. State explicitly whether you will
   index the *median market* or the *elite market* — they inflate at different rates and the
   answer must not silently mix them.
6. **Structural-break candidates.** Mark 1995 (Bosman), 2003 (Abramovich), 2008 (City),
   2011 (PSG/QSI), 2017 (Neymar €222m), 2020–21 (COVID deflation), 2023+ (Saudi PIF, Chelsea
   long-amortisation contracts). You will test these formally later.

**Gate:** if fee coverage before some year Y is too thin/biased to model, say so and set the
index's valid start year to Y. Do not extrapolate an index into years the data can't support.

---

## 2. Build three inflation indices (not one)

### 2a. Naive index (baseline, known to be biased)
Yearly p50 and mean of positive permanent fees, and total-market-spend index. Report it,
label it biased, keep it only as a sanity foil.

### 2b. Hedonic index (the real deliverable)
Regress log(fee) on player/deal quality controls + **year fixed effects**:

```
log(fee) ~ C(year) + age + age^2 + C(position) + C(to_league_tier) + C(from_league_tier)
           + log(market_value) [if available] + output_metrics [xG/xA/minutes if bridged]
           + contract_length [if available] + C(transfer_type)
```

The **exp(year fixed-effect) series IS the pure inflation index** — it's the price change after
holding player quality constant. This is the gold standard because repeat-sales indexing is
impossible (players are rarely re-sold in identical condition). Report the year-FE trajectory
with confidence intervals. Anchor to a base year (e.g. index = 100 at 2010).

Requirements:
- Cluster standard errors by player and by selling club.
- Use log fee (fees are heavy-tailed, multiplicative); handle £0 frees by excluding or a
  separate model, not log(0).
- Report R² and which controls matter. If market_value is present it will dominate — run the
  model both with and without it and reconcile (market_value is itself inflating, so a
  fee/market_value model gives a *premium* index, not a raw price index — report both readings).

### 2c. Segmented indices
Refit 2b separately (or via interactions) for at least: **elite market (p90+)** vs **median
market**, and **forwards vs other positions**. Deliver the finding that these diverge — a single
scalar index is a lie the data will expose.

---

## 3. Structural breaks & regime detection
- Run Bai–Perron / Chow tests on the hedonic year-FE series for the candidate break years in §1.6.
- Report the empirically detected breakpoints and the CAGR *within each regime* (e.g. pre-Bosman,
  Bosman→Abramovich, Abramovich→Neymar, Neymar→COVID, post-COVID).
- Overlay the football index vs UK CPI vs Premier League TV-deal value per cycle. The gap between
  the football index and CPI **is the answer to "how much football inflation, and to what degree."**
  Quantify the multiple (e.g. "football fees inflated Nx faster than CPI over the window").

## 4. The deliverable: a scaling function
Ship `money/inflation.py` exposing:

```python
def scale_fee(fee_nominal, from_year, to_year, *,
              market="elite"|"median", position=None,
              basis="hedonic"|"naive", currency="GBP") -> dict:
    """Returns {scaled_fee, index_from, index_to, multiplier, ci_low, ci_high, basis, caveats}."""
```

- Backed by the §2b/2c index tables (persist them as a small parquet/csv, don't recompute live).
- Must expose confidence intervals and a `caveats` string that fires when either year is outside
  the validated range, or the segment has thin support.
- **Do not** silently fall back to CPI. If football index is unavailable for a year, return a flag.

## 5. Self-checks (must pass, print PASS/FAIL)
Ground the model against known transactions — it must reproduce football intuition, not just fit:
1. Shearer £15m (1996, record) scaled to 2023 elite index lands in the modern world-record band
   (£100m+), NOT the ~£30m a CPI deflator would give. If it lands near CPI, the index is broken.
2. A 2017→2021 elite scaling shows the **COVID dip** (multiplier < the 2017→2019 multiplier).
3. Median-market and elite-market multipliers for the same year pair **differ** (prove §2c).
4. Round-trip: scale a real 2012 fee to 2020 and back to 2012 → recovers original within FP error.
5. Total predicted market spend rebuilt from the hedonic index tracks actual total spend
   (directional check, not exact).

## 6. Output artifacts
- `INFLATION_AUDIT.md` — §1 findings + go/no-go gate.
- `INFLATION_FINDINGS.md` — the index charts, regime CAGRs, football-vs-CPI multiple, the
   headline "to what degree" number, and the divergence-by-segment finding.
- `money/inflation.py` + persisted index tables + the §5 self-check block runnable as `__main__`.
- One caveats section: FX assumptions, coverage gaps, tail sensitivity, what the index must NOT
  be used for (e.g. scaling non-elite fees with the elite index).

## Rules of engagement
- Verify the schema and coverage empirically before every modelling claim; cite counts.
- Prefer the hedonic year-FE index as the authoritative answer; the naive index is a foil only.
- Never present a single scalar "football inflation rate" without the regime + segment breakdown —
  the whole thesis is that it's non-stationary and non-uniform.
- If a step's data support is too thin, say so and narrow scope rather than fabricate an index.
