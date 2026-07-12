# Models: what to use for each job, and why

One rule underneath all of this. Fit a model only where something real was observed. Fees happened. Points happened. League transfers happened. "This was a good signing" never happened, so nothing gets trained on it.

---

## 1. Usage and efficiency

The centre of the system. Get the definitions right and most of the rest follows.

### Usage

Borrowed from basketball's USG%, adapted to football. A player's share of his team's **terminal actions** while he is on the pitch. A terminal action ends a possession, for good or bad.

```
usage_i = (shots + shot_assists + dispossessed + miscontrols)_i
        / Σ_team (same, while i is on the pitch)
```

All four components are on FBref (shooting, passing, possession, misc tables). Shot-assists rather than key passes, because it counts the pass that produced the shot regardless of outcome.

Compute usage from per-90 rates rather than raw totals, so a squad player and a starter are comparable. The team denominator should ideally cover only the minutes the player was on the pitch. Approximating it with team per-90 totals introduces a small bias, and that is acceptable at first. Mark it in a comment and revisit only if it shows up in the residuals.

**Sanity check before proceeding:** usage across a team's outfield players, weighted by minutes, must sum to roughly 1. If it doesn't, the definition is broken.

### Efficiency

Value produced per unit of usage.

```
efficiency_i = (xG + xAG)_i / (usage_i × team_terminal_actions_per90)
```

Or more simply, value per terminal action. Efficiency is the part of a player that travels between clubs. Usage is the part that doesn't.

### The usage-efficiency curve

Efficiency falls as usage rises. A player asked to do everything takes worse shots. This is well established in basketball and there's no reason football differs, but **fit it, don't assume it**.

**Model:** spline or LOESS regression of efficiency on usage, fitted **within player** (player fixed effects) so that you're capturing what happens when a given player's role expands, not the fact that better players get more of the ball. Fit separately by position. Report the slope with a confidence interval, and if the interval crosses zero, say so loudly, because a flat curve changes the conclusions.

### Predicting usage at a new club

Usage is zero-sum, so a signing's usage must be taken from somewhere. Model it as a reallocation: predict the incoming player's usage share from his role, his quality relative to the squad, and the destination's existing usage distribution. Then rescale everyone else down.

**Model:** start with a simple positional-share heuristic (the signing takes usage from players in overlapping roles, proportional to role similarity). Fit and validate against real transfers where you can observe what actually happened to the squad's usage distribution the following season. Only reach for something more elaborate if the heuristic's error is large.

The output that matters:

```
Δ team_output = usage_new × efficiency_new − Σ (usage_taken_from_j × efficiency_j)
```

Positive means the signing improves the team. Ronaldo should come out negative. That is the acceptance test.

---

## 2. League strength

Rankings tell you which league is better. They don't tell you what output *converts* at, and conversion is what you need.

**Do not** take Opta or Elo rankings as the answer. Use **ClubElo** (free, API, wide coverage) as a prior and a sanity check.

**Model:** two-way fixed effects on player-season output.

```
output_ps = player_FE_p + league_FE_l + f(age) + g(usage) + ε
```

The league fixed effect is league strength, and it's identified by players who moved between leagues. Same idea as adjusted plus-minus. Ridge-regularise it, because the leagues with few movers will otherwise produce wild coefficients.

**The honest limit:** a league pair is only identified by the players who actually crossed it, which may be a few hundred, and those players were selected for moving. A Championship striker who moves to the Premier League was probably good; the ones who stayed weren't sampled. That's survivorship, it biases the multiplier upward, and the fix is to weight by minutes and report a wide interval rather than pretend precision. Do not hide this.

Expect Liga MX and Brasileirão to have thin, late xG coverage and few clean movers. They may not survive the coverage gate. That's fine.

---

## 3. Age curves

**Model:** within-player output change by age, fitted per position, with a smoother. Player fixed effects again, and for the same reason: comparing 22-year-olds to 32-year-olds across players tells you who survived, not how players age. Comparing a player to himself a year later tells you how players age.

Expect different peaks by position. Centre-backs and goalkeepers age slower than wide attackers. If the fitted curves don't look like the football you know, something is wrong with the fit, not with football.

---

## 4. Fee model

Already built (`money/fees.py`), passes self-check.

**Model:** `HistGradientBoostingRegressor` on log fee. Handles categoricals and missing values natively, no tuning needed at this sample size. Out-of-fold predictions only, time-aware splits, because market inflation leaks through random splits.

No XGBoost. No Optuna. On roughly fifteen thousand rows the tuned model sits inside the noise of the default one, and you can read the default one. Tune only if cross-validated error is genuinely the constraint.

**The ceiling:** Transfermarkt market value is crowd-sourced and partly informed by the fees it's being used to evaluate. So the residual measures deviation from consensus, not deviation from truth. It catches the club that paid out of line with its own market. It cannot catch a market that's collectively wrong. The revenue valuation in §6 is the independent second opinion, and that's precisely why both exist.

---

## 5. WOWY

Already built (`impact/wowy.py`), passes self-check.

Team xG difference per 90 with the player on versus off, shrunk toward zero when the off-pitch sample is thin. Not a model, an estimator, and it needs no fitting.

Its job in this system is to **validate the usage model**, not to price players. It's too noisy to price anyone. But if the usage model predicts WOWY out-of-sample on completed transfers, the usage model is real.

---

## 5b. Progression value (xT) — built, DESCRIPTIVE ONLY

The shot engine (§1) values a player only at shots and the assist. It is blind to *buildup
progression* — carrying and passing the ball forward — so it structurally under-measures deep
midfielders and ball-playing defenders. `defensive_value.py` patched the defensive side
(equal-weighted box-score); `possession_value.py` does the offensive-progression side, but
**xT-weighted**: an xT surface fit on StatsBomb EPL 2015/16 (`ingest/xt.py`, self-contained, no
socceraction) gives an empirical value per action type, applied to the tm-keyed FBref buildup
columns (prog passes/carries, final-third entries). Box passes / through-balls / key passes are
excluded — the shot-assist term (xAG) already owns the final ball.

**It failed the predictor gate.** `validate/possession_gate.py` adds `possession_value_z` as a
second regressor to the shot channel on the Stage-4 mover panel (n=1,289). The coefficient is
essentially zero (slightly negative, 95% CI [−0.089, −0.006], joint R² 0.009) — buildup
progression does not predict realized team npxGD improvement beyond shots. Likely structural: the
target is a *shot-based* differential, so progression that doesn't convert to shots can't move it,
and the 1-season team panel is a weak instrument (even the shot channel gets only r≈0.08 here).

Verdict, same as league strength (§2): **it does NOT enter NPV.** It ships as a *scouting signal*
(`data/impact/possession_value.parquet`, a 0-100 percentile, and a `prog_pctl` column on the scout
board) — a distinct axis (corr≈0.17 with the defensive layer) that a scout reads alongside the
priced NPV, not a priced term. Revisit if a non-shot-based validation target becomes available.

## 6. Money

**xGD to points:** OLS on team-season data. The relationship is close to linear and a straight line is the right amount of model. Fit it, don't quote a rule of thumb from a blog post.

**Points to revenue:** step function, not a line. Premier League merit payments rise roughly evenly per place. Champions League qualification is a cliff worth an order of magnitude more than one league position. This discontinuity is why the same player is worth far more to a club sitting sixth than to one sitting fourteenth, and modelling it is the single largest source of the system's edge.

Source the actual figures from Premier League financial reports and UEFA's revenue distribution documents. Do not hard-code a remembered number. The whole valuation scales off this coefficient.

**NPV:** amortised fee plus wages against age-decayed impact, both discounted at around 8%, plus residual resale value at contract end.

---

## 7. Uncertainty

Bootstrap everything, and put an interval on every published number.

Four things in this system carry wide uncertainty and pretending otherwise would make the whole thing dishonest: WOWY off a thin bench sample, cross-league multipliers fitted on selected movers, wage figures that are estimates rather than filings, and the usage-efficiency slope. A point estimate without an interval, in this domain, is a lie with a decimal place.

---

# Research needed

Four questions worth answering properly before or during the build. The first is the one that matters.

### A. Usage and efficiency in football — prior art
Does anyone credibly define a football usage rate, and has anyone fitted a usage-efficiency curve? Basketball has this settled. Football may not, which is either an opportunity or a warning. Find the video that prompted this, find whatever it cites, and find the academic work on possession-adjusted involvement metrics. Deliverable: a definition to adopt or a documented reason to deviate.

### B. Cross-league conversion factors
Published multipliers between leagues, the methods behind them, and their honest error bars. Check whether anyone has handled the survivorship problem properly, because most attempts don't.

### C. Prize money and Champions League revenue, exact figures
Premier League merit payments per place, central distribution, and UEFA's Champions League breakdown (participation, performance, market pool, coefficient share). Primary sources. This is a coefficient, not a vibe.

### D. Wage data reliability
How Capology and Spotrac actually derive their estimates, and whether anyone has audited them against the figures that do get published. Determines how much weight the cost side can carry.

Run A first. It changes the design. The rest only change the constants.
