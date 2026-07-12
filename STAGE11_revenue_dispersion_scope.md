# Stage 11 — Revenue dispersion: club-specific commercial, matchday & owner/discount

**Status:** SCOPE (not built). Needs a new data-acquisition lane + two decisions only you can make.
**Why now:** the inflation index (Stage 10b) retired the last *time-value* assumption. The next
first-order error is **cross-club dispersion** — the model prices "value to a generic top-6 club",
not "value to *this* buyer". This scope fixes that.

---

## 1. The gap (verified against `money/revenue.py`)

Today's valuation runs through ONE channel: marginal xGD → league points → final rank → revenue.
The revenue side (`revenue_at_rank`) is:

```
revenue(rank) = EQUAL_SHARE(95.1) + merit(2.8/place) + European_EV(CL 40 … Europa/Conf 6)   [£m, EPL 2023/24]
```

Three things it deliberately does **not** model — all flagged in the file's own `ponytail:` comments:

| Missing | What it is | Why it matters to a transfer valuation |
|---|---|---|
| **Club commercial** | Shirt/kit/stadium-naming/tour income — Man Utd ~£300m/yr vs a promoted club ~£15m | The single biggest cross-club differentiator. CL football unlocks a *bigger* shirt deal for a big brand than a small one → the *same* league point is worth more to Man Utd than to Brentford. Model can't see this. |
| **Matchday** | Gate × stadium size × premium seating | A 74k-seat club monetises success (extra rounds, bigger crowds) far more than a 25k one. Absent entirely. |
| **Owner / cost-of-capital** | Ambition + financial constraint + risk premium | (a) *Willingness-to-pay*: every club currently values a point identically. (b) *Discount rate*: `DISCOUNT` is a flat 4% for all; Deloitte's own caveat is DCF breaks for loss-making owner-funded clubs → they warrant a club-specific premium. |

**Net effect:** revenue-by-rank is ~uniform across clubs by design (central pot is equal-share), so
the model **compresses the dispersion** in willingness-to-pay. Real WTP fans out with commercial
upside and owner ambition — exactly the two axes not represented.

---

## 2. Data lane (new — the real cost of this stage)

All annual, club-level, legitimately obtainable. Priority order:

1. **Deloitte Football Money League** (annual PDF, top ~30 clubs). Splits revenue into
   **matchday / broadcast / commercial** per club per year — the exact decomposition we need.
   ~15 yrs of history. Free to read; extract tables (see `anthropic-skills:pdf`).
2. **UEFA Club Licensing Benchmarking Report** (annual). Broader club coverage (all top-division
   clubs), revenue + wage/revenue + owner-funding figures. Free PDF.
3. **Companies House** (UK clubs file statutory accounts) + published-account digests
   (Swiss Ramble-style breakdowns) for clubs outside Deloitte's top-30. Manual but authoritative.
4. **Stadium capacity** table (Wikipedia/​club sites) — a cheap, static join key for matchday.

**Reachability caveat:** these are the same class of source as the selling-league xG lane — some
PDFs/pages may need residential fetch. Test from sandbox first; fall back to your Mac (mirrors the
`DATA_ACQUISITION_PLAN.md` pattern).

**Grade target:** commercial/matchday → grade B (audited published accounts). Owner premium → grade
C (partly judgemental). Do NOT over-invest: top-30 clubs cover ~every plausible transfer buyer.

---

## 3. Build (once data lands)

### 3a. `data/money/club_revenue.parquet`
`club · season · matchday · broadcast · commercial · total · stadium_capacity · source · grade`.
Bridged to `to_club_id` via the existing crosswalk.

### 3b. Extend `RevenueModel` → club-specific
Replace the scalar `revenue_at_rank(rank)` with `revenue_at_rank(rank, club)`:
```
revenue(rank, club) = central(rank)                         # unchanged, equal-share + merit + Euro
                    + commercial(club) × success_uplift(rank)   # commercial scales with CL/finish
                    + matchday(club)   × rounds_uplift(rank)     # extra home games in Europe/cups
```
`success_uplift` / `rounds_uplift` calibrated from the Deloitte panel (how a club's commercial &
matchday moved the year *after* it qualified for the CL vs missed). Keep `marginal_value(points)`
finite-difference interface identical so `npv.py`/`price.py`/`scout.py` don't change.

### 3c. Owner / discount adjustment
`club_discount(club) = base r_net (4%) ± owner_premium`, where owner_premium comes from a small
club→tier map (state-backed / billionaire-trophy / self-sustaining / distressed) derived from
UEFA owner-funding figures. Feed as the `discount=` arg already plumbed through `price_transfer`.
Optionally a `wtp_multiplier(club)` on the benefit side for ambition — **gate this hard**, it's the
most speculative knob.

### 3d. Self-checks (must pass)
1. Man Utd's £/CL-point > a promoted club's £/CL-point (commercial dispersion shows up).
2. Same player priced to two clubs → different NPV (the whole point of the stage).
3. Big-stadium club's matchday uplift on a deep cup run > small-stadium club's.
4. Owner premium moves a distressed club's valuation *down* vs a state-backed club, same player.
5. Central-only clubs (no `club_revenue` row) fall back to today's uniform model + a `grade` flag —
   **never silently zero commercial**.

---

## 4. Sequencing & effort

- **Data lane** (Deloitte + UEFA extract, crosswalk): the bulk. 1–2 sessions, gated on reachability.
- **Model extension** (3b–3c): ~1 session once data exists; interfaces already accommodate it.
- **Not urgent:** only pays off when pricing *named* buyers. Today's generic-top-6 output is correct
  for "is this a good signing at all"; Stage 11 is for "how much is he worth *to Newcastle vs Spurs*".

## 5. Two decisions only you can make (before building 3c)

1. **How far to push the owner knob.** A pure cost-of-capital premium (defensible) vs a WTP/ambition
   multiplier (speculative, risks fitting narratives). Recommend: ship the discount premium, gate the
   WTP multiplier behind a flag until backtested.
2. **Scope of club coverage.** Deloitte top-30 only (clean, covers ~all real buyers) vs the long tail
   via Companies House (much more work, marginal value). Recommend: top-30 + fallback flag.

## 6. What this stage explicitly is NOT
- Not a club-finances forecaster. It's a *dispersion correction* on the existing valuation.
- Not a PSR/FFP compliance model (separate concern; could be a Stage 12 constraint layer).
- Not a substitute for the wage grade — commercial revenue ≠ wage capacity.
