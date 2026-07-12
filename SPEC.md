# Transfer Predictions — build spec

Everything a fresh code session needs. Read this first, then `DATA.md`, then start at Milestone 0.

---

## 1. The thesis

Clubs buy players. Almost nobody checks whether the price made sense, because "made sense" has never been defined in money.

This system defines it. A signing costs an amortised fee plus wages, every season, for the length of the contract. It returns impact: the team wins more, finishes higher, earns more. Subtract one from the other and you get a number in pounds. Positive means the deal created value.

Two things fall out of that, and they're the reason this is worth building.

**Impact is measured against the player he displaces, not against nothing.** Ronaldo at United scored 18 league goals. United were worse with him on the pitch. Both facts are true and only the second one matters, because the minutes he took came from someone else, and the team's structure changed to accommodate him. A system that scores players in isolation cannot see this. A system that scores them against the incumbent can.

**Value to the club and price in the market are different numbers.** A player worth £70m to Arsenal (because Arsenal are one place off the Champions League cliff) may be worth £25m to Everton. The market charges one price. The gap between that price and the club-specific value is the entire product.

---

## 2. What gets built

Four layers. Each is independently useful and independently testable, which is deliberate — if layer 3 turns out to be noise, layers 1 and 2 still stand on their own.

### Layer 1 — Impact (xG)
Team xG difference per 90 with the player on the pitch versus off it. WOWY. Shrunk toward zero when the off-pitch sample is thin, because a starter who never rests carries almost no signal and the output has to admit that.

Working prototype exists: `wowy.py`, self-check passes.

### Layer 2 — Usage and marginal impact
The engine. Full model spec in `MODELS.md §1`.

Usage in football is zero-sum. A team has a fixed budget of terminal actions per match, so a signing who consumes a share of it takes that share off his teammates.

```
team_output = Σ (usage_i × efficiency_i)     where Σ usage_i = 1
```

A signing improves the team only if his efficiency beats the weighted average efficiency of the usage he takes.

Efficiency travels with the player. Usage belongs to the situation and does not. Separating them is what lets the system evaluate a transfer that hasn't happened: predict the new usage from the destination squad, apply the player's own efficiency, see what gets displaced.

This explains both of the cases the system exists to get right. Martial had huge usage and moderate efficiency at Monaco; his usage collapsed at United, so his output collapsed, and United had priced him off the output. Ronaldo consumed the largest shot share at United at an efficiency below the players he took it from, which is negative by construction.

Predicting usage requires role overlap: a similarity score across positional minutes and per-90 profile, identifying who the signing displaces. If the incumbent is already efficient, the signing has to clear a high bar.

### Layer 3 — Money
Two independent conversions, and the gap between them is the output.

**Value to the club:** xGD → expected points → league position → revenue.
- xGD-to-points is fitted from data, not assumed. Regress final points on season xGD across the sample. Do not use a rule of thumb off a blog.
- Position-to-revenue is where the Champions League cliff lives. Merit payments step roughly linearly per place; CL qualification is a discontinuity worth an order of magnitude more than one league place. So a player's value to a club depends on where that club already sits. A club sitting 6th values a +4 point player enormously. A club sitting 14th barely values him at all.
- *Verify the actual prize-money and CL revenue figures before hard-coding anything. Do not trust my recollection of them.*

**Price in the market:** what a player of this profile actually sells for. Fee model, out-of-fold. Working prototype exists: `fees.py`, self-check passes.

**Output:** club value minus market price. Positive is an arbitrage.

### Layer 4 — The deal
Both sides annualised, both discounted, then subtracted.

**Cost per season:**
```
(fee / contract_years) + annual_wages
```
Wages are not optional. £100m over 5 years is £20m a season; £300k/week is £15.6m a season. Nearly half the true cost is salary, and a system that ignores it will call a free transfer on enormous wages a bargain. It is the single most common error in public transfer analysis.

**Benefit per season:**
```
marginal_impact(season_n) × £_per_unit_impact(club, season_n)
```
where `marginal_impact` decays along a position-specific age curve, fitted from the data rather than assumed. Attackers and centre-backs age differently. Ronaldo's 2-year deal at 36 was underwater before he kicked a ball, and the age curve is what lets the system say so in advance.

Both streams discounted at ~8%. Net present value is the verdict. Add residual resale value at contract end for the young ones, because a 22-year-old who plateaus is still an asset and a 33-year-old who plateaus is a liability.

---

## 3. Decisions already locked

| Question | Decision |
|---|---|
| Impact → money | Both club-revenue value and market price. Report the gap. |
| Horizon | Full contract. Amortised fee plus wages, age-decayed impact, discounted. |
| Data depth | Top 5 leagues **plus selling leagues** (Championship, Eredivisie, Primeira, Liga MX, Brasileirão). Match, shot, and lineup level. 10 seasons. |
| Club context | Squad-aware. Same player scores differently at different clubs. |
| Wages | Capology/Spotrac estimates. Flagged as estimates everywhere they appear. |
| ML | Only where ground truth exists: the fee model, the xGD→points fit, the age curve. Nowhere else. |

**Explicitly not built:** no XGBoost on "transfer success", because no such label exists and never will within a useful timeframe. No SHAP theatre. No event-level tracking data, which doesn't exist free at this scale and isn't needed. If a future session proposes training a model to predict whether a transfer was good, that session has misunderstood the project.

---

## 4. The hard parts, named in advance

**Cross-league translation.** Adding selling leagues is what makes the system able to find value before it's priced in, and it's also the thing most likely to break it. A 0.4 xG/90 striker in the Eredivisie is not a 0.4 xG/90 striker in the Premier League. You need a league-strength multiplier, and you get it by fitting on players who actually moved between the two leagues and observing what happened to their output. That's a real dataset, it's a few hundred players per league pair, and the confidence intervals will be wide. Report them.

**xG coverage outside the top 5 is patchy.** FBref has xG for Championship and Eredivisie in recent seasons; Liga MX and Brasileirão coverage is thinner and starts later. Check coverage per league-season before committing, and let the system fall back to non-xG metrics with a clear quality flag rather than silently producing a worse number that looks identical.

**WOWY sample size.** A first-choice starter plays ~90% of available minutes. His "without" sample might be 600 minutes across a season, which is noise. Mitigations: pool across seasons and clubs, shrink toward the team mean, and always display `off_min` next to `wowy`. Never report the point estimate alone.

**Market value circularity.** Transfermarkt values are crowd-sourced and partly informed by the fees they're used to evaluate. So the fee model measures deviation from consensus, not deviation from truth. It catches the club that paid out of line with its own market. It cannot catch a market that's collectively wrong, which post-2017 it largely has been. This is a real ceiling, and the club-revenue valuation in Layer 3 is the independent second opinion that partly escapes it. That's why we build both.

**Wage estimates are estimates.** Capology and Spotrac are informed guesses, not filings. Directionally right, individually unreliable. Every output that depends on them says so.

---

## 5. Validation — how we know it isn't nonsense

This section matters more than the modelling. Build the tests before the features.

**Null test for WOWY.** Shuffle player identities within a team and recompute. WOWY should collapse to approximately zero. If a randomised player still shows large impact, the estimator is picking up team-level or game-level variance and the whole layer is void.

**The Ronaldo case.** Manchester United, 2021-22. Ronaldo's individual output was good; the team's xGD with him on the pitch was worse. If the engine doesn't produce a negative WOWY here, it's wrong, and nothing downstream can be trusted. This is the acceptance test for Layer 1.

**Sanity set for the fee model.** Assemble a list of deals where informed opinion is close to unanimous, and check the model agrees. Haaland at £51m should read as a substantial underpay. Antony at £85m should read as a substantial overpay. If the model disagrees with the entire football world on these, the model is broken, not brave.

**Backtest with a real outcome.** There is no "was this transfer good" label, but there are proxies with actual ground truth:
- resale value versus fee paid, three years on
- whether the player was still a starter two seasons later
- whether the contract was terminated or the player loaned out early

Take the fee residuals and marginal-impact predictions from 2015-2020 deals and check they correlate with these outcomes. If the system's flagged overpays didn't subsequently underperform on any of these, the system has no predictive content and we should know that before building a UI on top of it.

**Out-of-fold, always.** No deal is ever priced by a model that has seen it. Time-aware splits where possible, because market inflation makes random splits leak.

---

## 6. Build order

Do not skip ahead. Each stage has a test that gates the next, and a gate is never passed by loosening it.

1. **Data.** Pull and cache everything. See `DATA.md`. Gate: coverage table showing xG availability per league-season, and a written decision on which leagues make the cut.
2. **Usage and efficiency.** Define both, compute both, fit the usage-efficiency curve. Gate: usage sums to 1 across a squad, and Ronaldo's 2021-22 United shot share comes out highest in the squad at an efficiency below the players he displaced.
3. **WOWY.** Prototype exists. Run on real data. Gate: null test passes, Ronaldo comes out negative.
4. **Usage model predicts WOWY.** Gate: positive out-of-sample correlation on completed transfers, reported with error bars. This is the make-or-break gate for the project.
5. **League strength and age curves.** Both fitted, both with intervals. Gate: curves look like the football you know, with wide bars where data is thin.
6. **Fee model.** Prototype exists. Run on real Transfermarkt data. Gate: the sanity set agrees.
7. **Money.** xGD to points, position to revenue, NPV. Gate: backtest against resale outcomes shows signal.
8. **Interface.** Only now.

---

## 7. Repository shape

```
transfer-predictions/
  data/                 # cached parquet, gitignored
  ingest/
    fbref.py            # soccerdata wrapper, caches locally
    transfermarkt.py    # Kaggle player-scores loader
    wages.py            # Capology/Spotrac, estimates, quality-flagged
  impact/
    wowy.py             # ✅ built, self-check passes
    replacement.py      # role overlap, marginal impact vs incumbent
    aging.py            # position-specific curves, fitted
    leagues.py          # cross-league translation multipliers
  money/
    fees.py             # ✅ built, self-check passes
    points.py           # xGD → expected points, fitted
    revenue.py          # position → prize money, CL cliff
    npv.py              # amortised cost vs discounted benefit
  validate/
    null_test.py
    ronaldo.py          # the acceptance test
    sanity_deals.py
    backtest.py
  cli.py
```

Every module carries a `_check()` with assertions that run offline on synthetic data. The two existing files do this and both pass. Keep the habit — it's the only reason you can refactor the maths without fear.

---

## 8. Settled and still open

**Settled.** First club is Arsenal. Tactical style gets stored as a team-season cluster column and only becomes a feature if it explains the usage model's residuals. League strength gets fitted from movers, with ClubElo as the prior rather than the answer.

**Still open.** Whether Liga MX and Brasileirão come in at the data stage or wait until the cross-league method is proven on the easier pairs. Recommend waiting. And whether the betting angle stays open, which costs nothing to preserve now and is expensive to retrofit at the money stage.
