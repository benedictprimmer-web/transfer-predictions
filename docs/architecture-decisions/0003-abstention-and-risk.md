# ADR 0003: Abstention and Risk

Status: PROPOSED

## Decision

V1 is precision-first. False positives are materially more costly than missed bargains. Any published recommendation must carry uncertainty and support status.

Rows must abstain when:

- transaction is loan, free, loan return, undisclosed, unknown or not paid permanent for fee modelling;
- transfer date is proxy-dated for the V1 fee model;
- PIT market value is missing;
- position/role is unsupported, including goalkeepers and unsupported defensive roles;
- buyer-specific surplus is requested without named buyer context;
- wage is modelled or unavailable and the downstream output requires observed wage;
- row is outside approved league/era/age support;
- prediction key is non-unique or join expansion exceeds the contract.

## Executable Checks

FACT - `python3 -m validate.modelling_contract` verifies the abstention and output-semantics rules and writes `reports/model-contract/acceptance_results.csv`.

