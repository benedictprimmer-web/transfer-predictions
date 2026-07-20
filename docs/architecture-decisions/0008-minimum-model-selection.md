# ADR 0008: Minimum Model Selection

Status: accepted.

## Context

The MVP brief required simple models, temporal validation, uncertainty, and no locked-test access. The merged implementation only validated next-season minutes, so the correction narrows the claim to future availability/minutes rather than future sporting quality or total contribution.

## Decision

Use the smallest transparent ladder:

- S0: fitted joint age-role ridge baseline using fold-local preprocessing;
- M0: S0 plus prior minutes and data freshness, measuring prior availability rather than sporting-rate value;
- S1: M0 plus role-appropriate prior sporting-rate evidence with exposure-aware shrinkage and a fold-trained coefficient. Missing role-relevant rates remain missing, and unsupported rows fall back to M0 with `s1_evidence_status`.

S2 remains conditional on S1 passing the predeclared material-improvement gate and the temporal-rate coverage requirement.

## Gate Result

The M0-versus-S1 common supported-rate comparison has 614 rows and 500 players.

- informative S1 folds: 2;
- required informative folds: 3;
- M0 supported-rate Spearman: 0.2072;
- S1 supported-rate Spearman: 0.1836;
- Spearman lift: -0.0236;
- top-tier precision lift: +4.84 percentage points;
- 1,000-repetition exploratory player-cluster interval: [-0.0687, +0.0230];
- result: `ABSTAIN_INSUFFICIENT_TEMPORAL_RATE_COVERAGE`.

The interval is conditional on generated out-of-fold predictions. It is not parameter uncertainty and not proof of temporal stability.

## Consequence

The selected minimum artifact is a development-only next-season minutes evidence explorer with explicit fallback status. No production sporting ranking, total-contribution model, or buyer-specific economic ranking ships from this PR. S2 is not fit.
