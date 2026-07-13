# ADR 0004: Separate Arms

Status: PROPOSED

## Decision

The product is five separate-ish arms, never collapsed into one supervised target or one universal score. Each has its own grain, output and gate. A row in one arm's output is not comparable to a row in another's without going through the explicit bridge below.

| Arm | Question | Grain | Output | Status (this PR) |
|---|---|---|---|---|
| Sporting quality | Is he good and will it translate? | player-cutoff snapshot | future availability/contribution distribution | Data spine exists (`transfer_performance_features_prior`/`_outcomes_future`, `validate/v3_sporting_target.py`); no model fit yet |
| Importance/fit | How much does he improve this named buyer over replacement? | player-buyer-role scenario | marginal sporting impact | NOT V1/V3-SUPPORTED — no buyer context, no replacement-set builder |
| Economic worth | What is that impact worth to this buyer? | buyer-player-contract scenario | buyer-specific benefit distribution | NOT V1/V3-SUPPORTED — depends on Importance/fit |
| Market cost | What fee and wage will the market demand? | transfer/contract | acquisition-cost distribution | PARTIAL — fee ladder gated (`docs/v2-results.md`), wage NOT V1-SUPPORTED as observed label |
| Undervaluation | Is buyer-specific worth above total cost? | decision scenario | surplus distribution/support | NOT V1/V3-SUPPORTED — depends on Economic worth and Market cost both existing |

## The bridge (must stay explicit, never collapsed)

```
metrics -> future availability/contribution -> replacement delta -> points/wins -> buyer money
```

separately:

```
market context -> fee + wage + transaction costs
```

then, only once both sides exist for a NAMED buyer:

```
surplus_buyer = worth_buyer - cost
```

## Rules

1. Sporting quality is structurally price-blind. No fee, wage, market value, or buyer identity enters this arm's features (`docs/mustermann.md`'s per-90/shrinkage work already follows this; `validate/v3_sporting_target.py`'s feature/outcome split enforces it at the table level — `transfer_performance_features_prior` carries no price columns).
2. Market cost may use market-consensus value and market context but makes no claim about true sporting worth (`docs/modelling-contract.md`'s existing output-policy rule: fee residual is "deviation from expected negotiated fee," never "true value").
3. Buyer-specific worth uses sporting contribution and replacement context but excludes acquisition cost until the final comparison.
4. No output from one arm is relabeled as an output of another. A high sporting-quality score is not "undervalued." A negative fee residual is not "worth more than he costs." These require the full bridge, computed, not asserted.
5. Buyer-agnostic discovery (existing V1 scope) stays buyer-agnostic; buyer-specific arms activate only with named buyer, squad, replacement set, wages and contract assumptions supplied (owner decision 6, unchanged from the original PR).

## Executable checks

None yet beyond the existing V1 feature-policy checks (`reports/model-contract/feature_policy.csv`) and the prior/future table separation enforced by `validate/v3_sporting_target.py`'s own integrity assertions (features_prior contains no post-transfer row; outcomes_future is only ever read as `y`, never joined back as a feature — no code path in this repo does that join). A dedicated `feature_allowlist` test per arm (task's own "buyer identity in buyer-agnostic value" leakage-register row already exists for the discovery/surplus split) is future work once Importance/fit and Economic worth have any implementation to test against.
