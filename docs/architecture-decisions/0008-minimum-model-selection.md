# ADR 0008: Minimum Model Selection

Status: accepted.

## Context

The MVP brief required simple models, temporal validation, uncertainty, and no locked-test access. The merged implementation only validated next-season minutes, so the correction narrows the claim to future availability/minutes rather than future sporting quality or total contribution.

## Decision

Fit S0 and S1 only:

- S0: age/role historical baseline;
- S1: role-appropriate prior sporting-rate evidence with exposure-aware shrinkage. Missing role-relevant rates remain missing.

S2 is conditional on S1 passing one of the predeclared material-improvement gates. S1 failed, so S2 is not fit.

## Gate Result

- Spearman lift: -0.0304;
- player-clustered 90% CI for Spearman lift: [-0.0615, -0.0039];
- top-tier precision lift: -3.31 percentage points;
- positive Spearman folds: 0/7;
- result: S1 failed.

## Consequence

The selected minimum model is S0 for diagnostic comparison only on next-season minutes. No production sporting ranking, total-contribution model, or buyer-specific economic ranking ships from this PR.
