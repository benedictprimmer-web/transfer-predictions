# ADR 0008: Minimum Model Selection

Status: accepted.

## Context

The MVP brief required simple models, temporal validation, uncertainty, and no locked-test access. The merged implementation only validated next-season minutes, so the correction narrows the claim to future availability/minutes rather than future sporting quality or total contribution.

## Decision

Fit S0 and S1 only:

- S0: fitted joint age-role ridge baseline using fold-local preprocessing;
- S1: S0 plus role-appropriate prior sporting-rate evidence with exposure-aware shrinkage and a fold-trained ridge coefficient. Missing role-relevant rates remain missing, and unsupported rows fall back to S0 with an explicit status.

S2 is conditional on S1 passing one of the predeclared material-improvement gates. S1 failed, so S2 is not fit.

## Gate Result

- Spearman lift: +0.0113;
- player-clustered 90% CI for out-of-fold Spearman lift: [-0.0106, +0.0305] from 1,000 deterministic bootstrap repetitions;
- top-tier precision lift: -1.66 percentage points;
- positive Spearman folds: 1/7;
- result: S1 failed.

## Consequence

The selected minimum model is S0 for diagnostic comparison only on next-season minutes. No production sporting ranking, total-contribution model, or buyer-specific economic ranking ships from this PR.
