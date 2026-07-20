# ADR 0007: Sporting MVP Design

Status: accepted for development evidence only.

## Context

The V3 data spine produced a development-only next-season minutes target. The next question was whether strict-prior sporting-rate evidence improved enough over age/role history to support further sporting modelling.

## Decision

Build the MVP as two views over one validated output contract:

- Scouting Desk: light evidence-list view for rapid retrospective comparison;
- Recruitment Lab: dark diagnostic view for folds, support, denominator health, and subgroup health.

Both views use `reports/sporting-mvp/validated-output-contract.csv` and label rows as retrospective development examples.

## Consequences

Because S1 failed its gate, the MVP does not rank unsupported current players. It shows what would have been predicted on development rows for next-season minutes, with calibrated intervals omitted because they were not fitted.

This preserves the product surface while preventing a minutes-only negative result from becoming a misleading sporting-quality or buyer-value claim.
