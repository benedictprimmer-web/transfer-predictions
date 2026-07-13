# Mustermann — Evidence-Layer Design Notes

Status: HYPOTHESES, most untested in this codebase. This document translates
MustermannFM's scouting-analytics philosophy into falsifiable designs against
*this repository's* actual data and existing architecture. It does not claim
any idea here works — see §7 for what was actually tested versus left as an
untested hypothesis, and why.

The useful philosophy, stated once and referred back to everywhere below:

> Evaluate what a player produced in a defined role and environment, compare
> it with the right population, and only then ask whether the market priced
> it correctly.

This repo already has a version of the first half of that sentence — `usage
x efficiency` (`impact/usage.py`) is a per-role, per-environment production
measure, denominated in *team-action share* rather than per-90 minutes. What
follows asks whether a per-90/percentile/shrinkage evidence layer adds
anything on top of that, or whether it is presentation sugar for a system
that already does the hard part in a different unit.

## 0. What data actually exists to build this from

FACT — this repo has, per `warehouse.duckdb` (rebuilt `2026-07-13`, see
`docs/reconciliation.md`):

- `shots` (539,971 rows, Understat, 2014-2025): shot-level xG, assists,
  situation, home/away. Attacking actions only.
- `fbref_perf` (52,951 player-seasons, 222 columns): the advanced FBref
  snapshot, Big-5 leagues 2017-22 only (frozen before Opta pulled the feed —
  `HANDOFF.md` §1). This is the only source with progression, pressures,
  turnovers as *counting stats* rather than derived from shots.
- `fbref_defense` / `fbref_niche` (14,634 rows each): defensive summary and
  niche stats, same Big-5 2017-22 window.
- `clubelo_history` (771,384 rows, 1939-2026): club Elo, usable as a
  league/opponent-strength signal.
- `shots_selling` (234,800 rows): FBref xG for 4 feeder/selling leagues —
  the one non-Big-5 xG source, per `HANDOFF.md`.

FACT — `transfer_performance_link_safe`, the table that would connect a
transfer row to the player's *destination-season* performance, is
**unavailable in this environment** (`docs/reconciliation.md` §4 — it is
materialized from an external `ESTATE_B_DIR` never committed to this repo).
This means every idea below that needs a *destination-season* label (e.g.
"did the per-90 shrinkage estimate predict what he actually did after the
move") cannot be validated here. Presentation-only and origin-side
(pre-transfer) uses are unaffected.

FACT — the Big-5 FBref window (2017-22) does not overlap the locked final
period (`season >= 2023` per `docs/modelling-contract.md`'s
`design_A_recommended`). Any FBref-based per-90/shrinkage feature is
therefore currently usable only on `train`/`tune`/`calibration` folds by
construction — there is no FBref coverage in the locked period to
accidentally leak.

## 1. Per-90 metrics

DECISION — adopt the per-90 transform for count metrics only, never for
already-relative fields:

```
x_90 = 90 * x / minutes
```

FACT — eligible FBref count columns for this repo's schema: non-penalty xG
(`npxG`), xA (`xAG`), shots, shot-creating actions, progressive passes,
progressive carries, tackles, interceptions, and the turnover fields
(`fbref_defense`/`fbref_niche`). Understat's shot-level `value`/`actions`
(from `impact/usage.py`) are *already* a share (`usage_share`), not a count —
they must not be re-divided by minutes; `usage x efficiency` and per-90 are
two different, non-interchangeable denominators (team-action-share vs.
opportunity-time) and mixing them silently would misrepresent what "usage"
means in the acceptance-gated Stage 2/3/4 results this repo already has.

DECISION — never per-90: percentages/rates already computed upstream, age,
contract duration, any existing per-90 or per-shot rate, boolean flags.

REQUIREMENT (implemented, see `impact/evidence.py`) — every per-90 value
must be displayed alongside: the raw total, minutes/90s played, cutoff date,
and a reliability/support flag. A per-90 rate with no minutes context is the
exact "volume vs. efficiency" confusion `PROMPT.md` names as the Martial
failure mode, just relocated to a different denominator.

## 2. Minutes, reliability, and shrinkage

HYPOTHESIS — a fold-safe empirical-Bayes shrinkage toward the
`(role, league, season)` mean will produce more stable evidence-card numbers
for low-minute players than a hard cutoff, without discarding valid rows:

```
x̃_i = w_i * x_i + (1 - w_i) * μ_(role, league, season)
```

DECISION — the prior `μ` and the shrinkage weight `w_i` (`minutes_i /
(minutes_i + k)`, `k` fit to the training fold's within-cell variance) are
fit **inside each training fold only**. Implemented in
`impact/evidence.py::shrink_per90` with a fold-safe `fit()`/`transform()`
split and an executable self-check (`_check()`).

DECISION — minute thresholds (450 / 900 / 1,800) are a **display
sensitivity analysis**, not the reliability treatment. §7 reports how much
the shrunk estimate moves as the threshold changes for a sample of players;
shrinkage is the thing that ships, hard cutoffs are not, per the owner's
"test whether less is more" instruction — dropping valid low-minute rows
outright is more data loss than shrinkage, for no proven gain.

CAVEAT (untested here) — the shrinkage prior's correctness depends on
`(role, league, season)` cells having enough players to estimate a stable
mean/variance; §7 reports the smallest cells actually observed rather than
assuming they are adequate.

## 3. Percentiles

DECISION — three percentile definitions, kept separate, none conflated into
"the" rating:

1. **Domestic percentile** — role x competition x season. Cheapest, most
   defensible, smallest cohort.
2. **Adjusted-global percentile** — role x season after a *supported*
   league/context translation (see §4 — currently none is supported, so
   this definition is presently unavailable, not silently degraded to
   domestic).
3. **Recruitment percentile** — rank within an explicit, stated candidate
   universe (e.g. `money/scout.py`'s `candidate_universe`, which already
   exists and is buyer-agnostic-discovery-shaped).

DECISION — percentiles are a **presentation output by default**. Models use
the continuous shrunk per-90 value, not the percentile, unless a
predeclared percentile-feature challenger is run and gated separately (none
was run in this pass — see §7). Percentiles compress tails and are
cohort-definition-dependent; the repo's own house style (`SPEC.md`: "simple
beats clever... push back if the plan is over-engineered") argues against
using a lossier transform as a model input without a demonstrated reason.

REQUIREMENT — every percentile exposes cohort definition, cohort size,
eligibility rule, source metric, direction of desirability, reliability, and
cutoff date. Implemented in `impact/evidence.py::EvidenceCard`.

## 4. League strength

FACT — this repo already ran this experiment. `impact/leagues.py` fits a
per-league multiplier on cross-league movers; `validate/stage5_gate.py`
tests whether it lifts the Stage-4 usage-predicts-WOWY predictor.
`HANDOFF.md` §5: **it failed the gate** — "doesn't lift r → descriptive
only, not applied to the predictor." The fitted values are still recorded
(La Liga 1.107 … RFPL 0.966, EPL=1.000 reference) and are directionally
sane, but per this repo's own standing rule ("every refinement... must move
r or it doesn't ship"), a single hand-fit multiplier is out.

DECISION — this finding stands as a **prior against automatic inclusion** of
any league adjustment, single-multiplier or metric-specific, until a new
challenger clears the same gate on a metric it hasn't been tested on yet.
Section 10.4/11.3's three-design comparison (no adjustment / simple
per-league effect / metric-specific mover translation with partial pooling)
was not re-run in this pass — it would be re-litigating an already-gated
result on the same Stage-4 predictor without new data or a new metric, which
the "never loosen a gate after seeing a result" rule forecloses. A
metric-specific translation on a *different* metric (e.g. a per-90 defensive
count rather than the WOWY-linked attacking predictor) is a legitimate new
hypothesis, not covered by the existing failed gate, and is left as
untested future work — see §8.

## 5. Team and tactical context

FACT — `PROMPT.md` already specifies a style-cluster column (possession
share, PPDA, directness, width; k-means, 4-6 clusters) to be added *after*
the usage model is fitted, promoted only if it explains residuals. Per
`HANDOFF.md`, this was never reached (roadmap item 6c, "optional loop").

HYPOTHESIS (untested here) — possession/opponent-strength context could
sharpen a per-90 defensive or progression metric's cross-team comparability.
`validate.possession_gate` already exists and gates a *different* claim
(descriptive xT/possession slope, `docs/data-audit.md` §13: slope -0.0466,
CI [-0.0876,-0.0067], descriptive only) — it is evidence that possession
context correlates with something, not that it belongs in a predictive
feature. Not run against a per-90 evidence-card metric in this pass.

DECISION — starts/substitute status is treated as a support signal (already
partially available via `n90s`/appearance counts in `fbref_perf`), not a
correction factor. No possession/context adjustment ships in this PR.

## 6. Evidence card

IMPLEMENTED — `impact/evidence.py::EvidenceCard`, a dataclass over: raw
total, per-90, shrunk per-90, minutes/90s, domestic percentile (adjusted-
global left `None` — no supported translation, per §4), support flag
(`in_distribution` / `low_minutes` / `out_of_cohort`), and a 90%
bootstrap interval on the shrunk estimate. Seven dimensions are supported by
current data: goal threat (npxG/90), chance creation (xA/90), progression
(prog. actions/90), retention (pass completion under pressure — FBref-only),
defensive disruption (tackles+interceptions/90), aerial contribution (FBref
niche, sparse), and usage/importance (existing `usage_share` from
`impact/usage.py`, unchanged unit). No single weighted score is computed —
per owner decision 7 ("do not define one universal positive-recommendation
label yet"), and because no gate has tested whether a weighted composite
outperforms the separate dimensions.

## 7. What was adopted, tested, or rejected

| Idea | Status | Evidence |
|---|---|---|
| Per-90 transform for count metrics | ADOPTED for display | `impact/evidence.py`, `reports/v2-full-data/metric_distributions.csv` |
| Raw total always shown alongside rate | ADOPTED, hard requirement | `EvidenceCard` schema |
| Fold-safe empirical-Bayes shrinkage | ADOPTED, implemented + self-tested | `impact/evidence.py::shrink_per90`, `_check()` passes |
| Hard minute thresholds as sole reliability rule | REJECTED | shrinkage adopted instead per owner instruction; thresholds kept as a display sensitivity note only, see `reports/v2-full-data/cohort_support.csv` |
| Domestic percentile | ADOPTED for display only | `EvidenceCard`, cohort sizes in `reports/v2-full-data/cohort_support.csv` |
| Adjusted-global percentile | NOT SHIPPED — no supported translation exists | §4 |
| Recruitment percentile | DESCRIPTIVE ONLY, reuses existing `money/scout.py` candidate universe | not re-implemented; would duplicate existing code |
| League strength (single multiplier) | REJECTED, already gated and failed | `HANDOFF.md` §5, `validate/stage5_gate.py` |
| League strength (metric-specific mover translation) | UNTESTED — different metric than the gated case, left as future work | §4, §8 |
| Possession/tactical context adjustment | UNTESTED — descriptive possession/xT gate exists for a different claim | §5 |
| Evidence card (7-dimension, no composite score) | ADOPTED, implemented | `impact/evidence.py` |
| Single weighted composite rating | REJECTED for this PR | owner decision 7; no gate run to justify collapsing dimensions |
| Percentile as a *model* feature (vs. continuous) | NOT RUN as a challenger this pass | would require its own predeclared gate against the continuous-feature baseline; deferred, see `docs/v2-results.md` remaining decisions |

## 8. Explicitly deferred, not silently dropped

- Metric-specific league/context translation on a metric other than the
  already-gated WOWY predictor (e.g. defensive per-90 counts).
- Style-cluster promotion to a feature (`PROMPT.md`'s own deferred item).
- Any destination-season validation of the shrinkage estimate — blocked by
  the missing `transfer_performance_link_safe` (§0), not abandoned.
- Percentile-as-model-feature challenger.

None of these were run "just to see." They are recorded here as the next
predeclared experiments, contingent on Estate B (or an in-repo equivalent)
becoming available for the destination-season items.
