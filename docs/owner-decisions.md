# Owner Decisions

These are product choices the data cannot settle.

| Decision | Recommended answer | Alternatives | Architectural consequence |
|---|---|---|---|
| Deployment population | Paid permanent, supported outfield, ages 18-29, adequate leagues/eras | all players; all transactions; include GK/defenders | broader scope requires new labels and abstention logic; all-transaction scope invalidates continuous fee target |
| False-positive tolerance | Precision-first with conservative abstention | recall-first discovery | changes thresholds, uncertainty lower bounds, and top-k evaluation |
| Buyer specificity | Buyer-agnostic discovery first, buyer-specific surplus second | one generic value score; Arsenal-only system | generic score cannot use buyer context; Arsenal-only can use replacement importance but is not general |
| Horizon | two seasons for sporting validation; full contract for NPV | one season; resale-only; fee-only | changes labels, folds, target availability and economic mapping |
| Licensing | internal research only until risky sources licensed/replaced | commercial now; open-data-only | commercial now is blocked by source risk; open-data-only reduces coverage and may remove FBref/Capology/TM-derived inputs |
| Positive recommendation definition | multi-outcome diagnostic, no single binary yet | define binary now | premature binary would encode product preference as fact and can hide target conflict |

