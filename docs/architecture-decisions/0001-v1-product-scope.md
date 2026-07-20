# ADR 0001: V1 Product Scope

Status: PROPOSED

## Context

FACT - Phase 0 found target confusion between usage/WOWY/NPV, fee residuals and talent-vs-price repricing.

FACT - Strict negotiated-fee V1 candidate scope has 5,151 rows. Source: `reports/model-contract/component_support.csv`.

FACT - Future sporting contribution and observed wage are marked NOT V1-SUPPORTED in `reports/model-contract/component_support.csv`.

## Decision

Use a staged, abstaining V1:

1. Buyer-agnostic discovery and market/fee diagnostics first.
2. Buyer-specific economic surplus only when buyer context is provided.
3. Unsupported players/roles/leagues/eras return ABSTAIN.
4. Fee residual is never presented as true value or genuine undervaluation.

## Consequences

Positive: reduces false-positive recommendations and keeps each quantity interpretable.

Negative: coverage is smaller, especially for proxy-dated transfers, goalkeepers, defensive roles, wages and buyer-specific surplus.

OWNER DECISION REQUIRED - Commercial deployment remains blocked until risky data sources are licensed or replaced.

