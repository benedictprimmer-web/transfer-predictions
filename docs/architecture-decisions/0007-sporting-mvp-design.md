# ADR 0007: Sporting MVP Design

Status: accepted for development evidence only.

## Context

The V3 data spine produced a leak-tested destination-season sporting target. The next question was whether strict-prior sporting evidence improves enough over age/role history to support a scouting shortlist.

## Decision

Build the MVP as two views over one validated output contract:

- Scouting Desk: light evidence-list view for rapid retrospective comparison;
- Recruitment Lab: dark diagnostic view for folds, uncertainty, support, and subgroup health.

Both views use `reports/sporting-mvp/validated-output-contract.csv` and label rows as retrospective development examples.

## Consequences

Because S1 failed its gate, the MVP does not rank unsupported current players. It shows what would have been predicted on development rows, the uncertainty, and why production scoring is blocked.

This preserves the product surface while preventing a weak signal from becoming a misleading shortlist.

