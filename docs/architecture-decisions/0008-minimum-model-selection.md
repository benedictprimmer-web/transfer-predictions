# ADR 0008: Minimum Model Selection

Status: accepted.

## Context

The MVP brief required simple models, temporal validation, uncertainty, and no locked-test access. It also required stopping if the strict-prior sporting signal was weak.

## Decision

Fit S0 and S1 only:

- S0: age/role historical baseline;
- S1: shrunk prior sporting evidence with exposure-aware partial pooling.

S2 is conditional on S1 passing one of the predeclared material-improvement gates. S1 failed, so S2 is not fit.

## Gate Result

- Spearman lift: -0.0516;
- top-tier precision lift: +2.21 percentage points;
- positive Spearman folds: 0/7;
- result: S1 failed.

## Consequence

The selected minimum model is S0 for diagnostic comparison only. No production sporting ranking ships from this PR.

