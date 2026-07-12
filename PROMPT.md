# Paste this into the code session

---

You are building a football transfer valuation system. The repo is at `~/Transfer Predictions`. Read `START_HERE.md`, `SPEC.md`, `DATA.md` and `MODELS.md` before writing any code.

## What it does

Price a transfer in pounds. Cost is the amortised fee plus wages, per season, across the contract. Benefit is the team winning more, converted to revenue. Subtract, discount, and you get a verdict.

The first club to evaluate is **Arsenal**. Every squad-aware feature gets sanity-checked against the Arsenal squad, because that's the one the user knows well enough to catch it being wrong.

## The core model — read this twice

Usage in football is zero-sum. A team has a fixed budget of terminal actions per match (shots, shot-assists, turnovers). If a signing consumes a share of it, that share comes off his teammates.

```
team_output = Σ (usage_i × efficiency_i)     where Σ usage_i = 1
```

A signing improves the team only if his efficiency exceeds the weighted average efficiency of the usage he takes from others.

This explains the two cases the system exists to get right:

- **Martial.** Very high usage at Monaco, moderate efficiency. His usage collapsed at United, so his raw output collapsed. United priced him off raw output and bought a volume artefact.
- **Ronaldo, United 2021-22.** Consumed the largest shot share in the squad at an efficiency below the players he displaced. Individually productive, collectively negative. Any system that scores players in isolation calls this a good signing, and that is the failure mode we are engineering against.

Separating **volume** from **efficiency** is the whole trick. Efficiency is a property of the player and travels with him. Volume is a property of his situation and does not. Predict the new volume from the destination squad, apply his efficiency, and you can evaluate transfers that have not happened.

## Two engines, one validates the other

- **WOWY** (`impact/wowy.py`, already built and passing self-check): team xG difference with a player on the pitch versus off it. Measured, noisy, backward-looking, no causal mechanism. This is the **validator**.
- **Usage model** (to build): mechanistic, forward-looking, works on hypothetical deals. This is the **engine**.

Fit the usage model, then test whether it predicts WOWY out-of-sample on real completed transfers. If it does, the system has predictive content. If it doesn't, stop and say so rather than building a UI on top of noise.

## Build order

Each stage has a gate. Do not pass a gate by loosening it.

1. **Data.** Pull and cache per `DATA.md`. Gate: coverage table showing xG availability per league-season, and a written decision on which leagues make the cut.
2. **Usage and efficiency.** Define and compute both. Fit the usage-efficiency curve. Gate: Ronaldo's 2021-22 United shot share comes out as the highest in the squad, and his efficiency comes out below the players he displaced. If not, the definitions are wrong.
3. **WOWY on real data.** Gate: null test passes (shuffle player identities within a team, WOWY must collapse to roughly zero). And Ronaldo's United WOWY is negative.
4. **Usage model predicts WOWY.** Gate: out-of-sample correlation on completed transfers is positive and reported honestly, with error bars. This is the make-or-break gate for the whole project.
5. **League strength and age curves.** Both fitted, not assumed. Both with confidence intervals.
6. **Fees.** `money/fees.py` exists and passes self-check. Run on real Transfermarkt data. Gate: Haaland at £51m reads as a substantial underpay, Antony at £85m as a substantial overpay. If the model disagrees with unanimous football opinion on these, it's broken, not brave.
7. **Money.** xGD to points (fitted). Points to revenue (Champions League cliff). Amortised cost against discounted benefit. NPV.
8. **Interface.** Only now.

## Hard rules

- **No model without ground truth.** Fees happened, so model them. Points happened, so model them. "Was this transfer good" never happened and never will inside a useful timeframe, so do not train a classifier on it. If you find yourself writing an XGBoost model to predict transfer success, you have misunderstood the project.
- **Wages are half the cost.** £100m over five years is £20m a season. £300k/week is £15.6m a season. A system that ignores wages will call a free transfer on enormous wages a bargain. Wages are in the cost side from the start, flagged as estimates wherever they appear.
- **Show the error bars.** WOWY off a thin bench sample, cross-league multipliers fitted on a few hundred movers, wage estimates that are informed guesses. Every one of these has wide uncertainty and the output must display it. A number without an interval is a lie in this domain.
- **Every module carries a `_check()`** with assertions that run offline on synthetic data. The two existing files do this. Keep it. It's the only reason the maths can be refactored without fear.
- **Out-of-fold, time-aware, always.** No deal is ever priced by a model that has seen it. Market inflation makes random splits leak.
- **Simple beats clever.** If a ratio answers the question, don't fit a model. If linear answers it, don't go non-linear. Push back if the plan is over-engineered.

## Tactical style

Tag every team-season with a style cluster (possession share, PPDA, directness, width; k-means on FBref team stats, four to six clusters). Store it as a column. Do not build a tactical model yet.

Once the usage model is fitted, check whether style transitions explain its residuals. If they do, promote style to a feature. If they don't, you have saved yourself a model nobody could have validated.

## First deliverable

The coverage table from stage 1, plus a one-page memo: which leagues have usable xG and shot-minute data, which don't, and what the honest scope of the system is as a result.

---
