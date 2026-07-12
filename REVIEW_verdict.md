# REVIEW — Verdict

*Fable orchestrator, 2026-07-12. Full data→model review per `REVIEW_fable_prompt.md`. Method: 7 axis
assessors → 63 adversarial refutations (40 confirmed / 20 revised / 3 re-verified after a scratchpad
mixup) → 3 live-fire tests, each independently verified (B1 confirmed, B2 confirmed, B3 revised in
metadata only). Nothing below is unverified. Scope doc: `REVIEW_00_scope.md`.*

---

## 1. The five-axis scorecard

| Axis | Grade | Where it stands (one line) | Highest-value next move |
|---|---|---|---|
| 1 · Quantity of data | **C** | Deep Big-5 attacker spine (540k+235k shots, 134k transfers, 508k valuations) but frozen at Jan 2025, position-skewed (0 scoreable GKs, defenders thin), and only 27% of 2025/26 movers have recent shot data | Refresh Understat + TM dumps; wire the *already-on-disk* fbref_perf 2024-26 xG the "frozen ≤2023" framing ignores |
| 2 · Quality of data | **C** | Internal hygiene genuinely good (leak-guard holds, PIT MV verifies on sample) but the fee ranker ships through a confirmed random-KFold time leak, contracts are current-state not PIT, and the whole estate is non-commercial on licence | Fix `money/fees.py` CV to season-grouped/expanding-window and re-gate |
| 3 · Usefulness | **C−** | Player comparison works for attackers only (B1: 4/9, every miss diagnosed); the gem screen **does not beat base rate** (0.440 vs 0.428 — 43% of all young-cheap players double MV anyway); rumour demo runs but 6/10 verdicts are honest `cant_say` (freshness + EPL-only pricing) | Reformulate the screen within-position with an age-residual price baseline, tested against realized fees, not MV growth |
| 4 · Visualisation | **B** | Dossier is investor-presentable and Data Room has real polish, but no visual anywhere shows the thesis, and the flagship board reads "never buy anyone" (0/98 positive NPV) | Build the talent-rank vs price-rank gem-corner scatter (age-adjusted; 694 labelled points verified feasible) |
| 5 · Modelling | **C** | No trained model exists — a hand-built chain with ~24 hand-set constants and one leaky in-memory fee model; hygiene culture (gates, bands, era splits) is the best part | Fix the fee CV, then build the price-blind talent model: pooled, target = forward 2-yr Δlog(MV) residualized on age, expanding-window, gated |

## 2. The sauce — bottom line

**The sauce is measurable and real, but not yet an edge.** A price-blind talent score (efficiency +
usage, penalties excluded) is stable season-over-season (rho 0.43 composite, 0.66 raw efficiency) and
correlates-but-diverges from market value exactly as the thesis wants (Spearman 0.32 age-blind, 0.41
age-adjusted — re-verified end-to-end, no price contamination, clean joins). The market structurally
overpays volume relative to efficiency (MV loads: actions 0.394 > efficiency 0.292 > usage 0.139), so
the divergence is systematic, not noise. **But every conversion test failed honestly:** the
talent-minus-price gap does not predict next-season repricing within any age band (rho 0.006–0.066;
the pooled −0.114 is a Simpson's artifact of the age adjustment saturating at 29+, filling the tail
with correctly-cheap veterans), and the B2 gem screen's 44% hit rate is statistically
indistinguishable from the 43% base rate. The precondition for an edge exists; the current
formulation doesn't extract it. The fix is specific, not vague: within-position screening, an
age-residual price baseline instead of a linear bump, realized-fee outcomes instead of the soft
MV-growth label, and the selling leagues (where TM is least informed) instead of the Big-5 (where it
is best informed). Until one of those passes a gate, the honest label is **edge-but-unproven**.

## 3. Direct answers to the owner's questions

**Best way (ML or otherwise) + tech stack to use this data most effectively?**
Keep the stack — DuckDB views over parquet + Makefile is right-sized (largest table 771k rows,
queries instant, checks run in 15s); adding an experiment tracker, feature store, or model registry
would be over-engineering for one user. The two real infra gaps are operational, not architectural:
**no git repo** on code that has already survived two silent corruptions, and a `make data` that
cannot actually rebuild the warehouse from empty (6 of ~10 builders wired, ESTATE_B lives in
~/Downloads). Fix those; change nothing else.

**Are we / should we be training a model? One or several? What's the target?**
Today nothing is trained — the system is a hand-built scoring chain plus an in-memory HistGBR fee
ranker with a confirmed time leak. Yes, train — but exactly one new model: a **pooled price-blind
talent model** (per-position splits fragment coverage that is already thin). Target: **forward 2-year
Δlog(market value), residualized on an age(+league) baseline** — dense (445k usable MV rows),
strictly future-dated, and the honest proxy for "the market repriced him." Not per-deal team impact:
Stage-4's r=+0.077 ceiling says WOWY-level outcomes are ~99% unexplainable at deal level. Keep the
existing fee model as the *price* benchmark (after the CV fix) and the NPV chain as the sanity layer
it already is — separate axes, never merged into one model.

**How do we train / test / calibrate / avoid overfit?**
Expanding-window splits by season (the repo already does this right in `validate/npv_backtest.py` —
make it the only pattern; the fee model's random KFold is the one live violation). Gates before
anything ships: (1) beat an age-only baseline out-of-time — a talent model that is secretly an age
curve is worthless; (2) the Haaland-underpay / Antony-overpay sanity pair, never loosened; (3) decile
forward-MV cohort monotonicity. Every number carries a band; the ~24 hand-set money-chain constants
get consolidated into one module with a sensitivity sweep so NPV's fragility is visible instead of
buried.

**Is our data high-level? Does it give an advantage? Are we near proprietary?**
No, partially, and no. Every large asset is a public mirror anyone can curl in a weekend
(Understat/TM/ClubElo/FBref dumps); CIES and TransferLab ship the core concepts at 10–100× the league
coverage; and the repo's own licence audit is correct that the estate is research-grade, not sellable
(StatsBomb non-commercial, TM database-rights risk, Opta proprietary, Understat ambiguous). What *is*
near-proprietary: the **method** — the never-loosened gate discipline (rare even commercially), the
calibrated NPV chain, the talent-vs-price framing — and the **assembled merge** (100% game crosswalk,
76% player crosswalk, PIT-flagged joins across 15 tables), which is replicable in weeks but is real
work someone would have to do. That's a personal/consulting edge, not defensible IP.

**Is more/better data the problem, or using it better?**
Using it better — with two narrow exceptions. The evidence: the single most valuable signal (xT/VAEP)
is computable from StatsBomb events *already on disk*; fresher Big-5 xG through 2025-26 is *already on
disk* in fbref_perf, unused; and the B-tests failed on formulation (screen design, age handling,
EPL-only pricing), not on missing rows. The two exceptions where gathering matters: the **freshness
refresh** (Understat/TM re-pulls — the Jan-2025 freeze is what killed 6/10 rumour verdicts and makes
the scout board 18 months stale) and, later, thin-coverage selling leagues where TM is least informed.
Stop collecting commodity-mirror variants.

**Can we visualise this to genuinely impress people?**
Yes — the craft is already there (the dossier is the strongest single artifact in the estate), but it
currently sells the wrong story: an NPV board where 0/98 candidates are worth buying, and no visual
of the thesis. The gem-corner scatter (talent rank vs price rank, age-adjusted, named players in the
corner) is verified feasible with 694 labelled points and is the picture that makes a football person
lean in. Second: the per-player "sauce card" — every radar axis already computed. Both are S–M effort.

## 4. Live-fire results (all independently verified)

- **B1 — known cases: 4/9.** Hits: Haaland (eff 95th pct), Salah (96th), Antony correctly flagged
  (mediocre Eredivisie efficiency at high price), Gnabry, plus an honest "no data" on Mahrez (Ligue 2
  pre-coverage). Misses, each diagnosed: Bellingham (deep-#8 role → 59th pct; role changes are
  invisible to shot signal), Lukaku (99th pct — model scores talent, not manager fit; genuine scope
  limit), Pépé (volume in a weak league mistaken for safety; no league step-up adjustment since league
  strength failed its gate), Maguire (CB — the metric sees only his attacking slice), **Kanté (17th
  pct — the destroyer blind spot as predicted, PLUS a real bug: his Understat name is stored with a
  literal `&#039;` HTML entity, which breaks the crosswalk, `_find_player`, and silently degrades his
  wage to the modelled prior)**. Also surfaced: `money/price.py` hardcodes `LEAGUE = "ENG-Premier
  League"` — non-EPL destinations cannot be priced at all.
- **B2 — gem screen: no edge as formulated.** 2023-24 shortlist (Bamba, Knauff, Cancellieri, Diakite,
  Daramy — all numbers verified exact). Backtest 2015-16→2021-22: precision 0.440 (11/25) vs base
  rate 0.428 (89/208), robust across 5 threshold variants. Real hits it did find (Havertz 8→90m,
  Abraham, Raspadori, Baumgartner) are matched by false positives and, more damningly, by the base
  rate itself. n=25 is too small to detect even a +10pp edge. The screen needs reformulation, not
  polish.
- **B3 — live rumours (2026-07-12): 10 pulled, all cited.** 3 priced verdicts (Tonali→Spurs BAD at
  ~£100m; Mateus Fernandes→Utd BAD at £80m; João Gomes→Utd BAD at €45m), 1 priced-but-cant_say
  (Osimhen — data predates Galatasaray move), 6 honest cant_say: Isak (our data predates his
  Liverpool move entirely), Álvarez + Kolo Muani + Garnacho (freeze straddles their key seasons),
  Nathaniel Brown (defender + non-EPL), Salah (Saudi/MLS unmodelled). Every number reproduced exactly
  on independent re-run. The demo works mechanically; freshness and the EPL hardcode are what cap it.

## 5. Go-forward roadmap (value-per-token, all axes)

| # | Move | Axis | Effort | Status |
|---|---|---|---|---|
| 1 | `git init` + initial commit (+ .gitignore additions) | infra | S | **done this run** |
| 2 | Fix `money/fees.py` CV → season-grouped expanding-window, re-run ship, re-gate Haaland/Antony | quality/model | S | **done this run** |
| 3 | Fix the HTML-entity name bug (Kanté class) in the crosswalk chain, rebuild, verify | quality | S | **done this run** |
| 4 | Pin `requirements.txt` (esp. duckdb exact) | infra | S | **done this run** |
| 5 | Gem-corner scatter — the thesis visual | viz | M | **done this run** |
| 6 | Freshness refresh: re-pull TM dump (valuations past 2026-02) + Understat/FBref 2025-26 where reachable | quantity | M | next |
| 7 | Reformulated gem screen: within-position, age-residual baseline, realized-fee outcome, selling leagues — behind a base-rate gate | sauce | M | next |
| 8 | Price-blind talent model per §3 design, behind the age-baseline gate | model | L | next |
| 9 | xT/VAEP from on-disk StatsBomb + calibrate defensive layer (the standing NEXT_STEPS top move — unblocks defenders/DMs, the biggest B1 miss class) | model | L | next |
| 10 | Extend `transfer_performance_link_safe` past 2022 from on-disk fbref_perf 2024-26 (keeps the gate) | quality | M | next |
| 11 | Multi-league pricing: lift the `ENG-Premier League` hardcode in `money/price.py` | usefulness | M | next |
| 12 | Sauce card + rumour verdict card visuals; fix the all-negative NPV board framing | viz | M | next |
| 13 | Consolidate the ~24 money constants into one module + sensitivity sweep | model | S | next |
| 14 | Decide product identity (research/consulting vs sellable) — licence blockers make this a fork in spend | strategy | owner | **decision needed** |

## 6. Decisions that are the owner's, not mine

1. **Product identity** (roadmap #14): if this ever ships commercially, StatsBomb/Opta/TM/Understat
   all have to be replaced or licensed — a different spend profile than the research path. Everything
   above assumes research/consulting.
2. **ESTATE_B dependency**: three builders read `~/Downloads/football-transfer-db`. Archive it into
   the repo's data root (795MB estate is fine) or formally accept the external dependency.
3. **Doc sprawl**: 42 root markdown files; moving 38 to `docs/` is safe post-git but touches paths
   other notes reference. Deferred rather than done silently.
