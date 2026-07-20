# Target Definitions

Status: PROPOSED for architecture review.

## Candidate Labels

| Label | Formula and timestamp rule | Measures | Does not measure | Leakage risk | Selection risk | Role/era support | Contract status |
|---|---|---|---|---|---|---|---|
| next-season minutes | Sum destination minutes in season immediately after prediction cutoff; feature cutoff strictly before transfer date/window | availability and selection | quality or value | destination-season data as feature | only linked leagues/players | incomplete future builder | secondary, NOT V1-SUPPORTED |
| two-season available minutes | Sum minutes over two seasons after cutoff, with injury/loan status flagged | availability over horizon | sporting quality | future appearances as feature | survival and league coverage | incomplete | secondary, NOT V1-SUPPORTED |
| next-season role-adjusted sporting contribution | role-normalized contribution in first post-transfer season | sporting output | price or surplus | post-transfer performance leakage | performance-rich subset | weak for GK/defensive roles | primary candidate, NOT V1-SUPPORTED |
| two-season cumulative sporting contribution | sum role-adjusted contribution over two seasons | sustained contribution | fee/value | future features, survivorship | observed survivors | incomplete | primary candidate, NOT V1-SUPPORTED |
| forward market-value change | `log(MV_t+2y) - log(MV_pre)` using valuations 300-800 days after cutoff | market repricing diagnostic | true talent or surplus | transfer-fee contamination | survival/observation bias | 68,320 audit rows before stricter V1 scope | diagnostic only |
| realized resale fee | next later transfer with `fee_eur > 0` | realized later transaction price | value of non-resold players | later fee as feature | selected on resale and disclosure | 32,073 audit rows | diagnostic only |
| retention/starter outcome | starts/minutes share at buyer after transfer | buyer retention | intrinsic value | destination info leakage | destination coverage | not built | secondary, NOT V1-SUPPORTED |
| early loan/termination | loan/free/end-of-loan within 730 days after transfer | negative acquisition outcome proxy | quality alone | future transfer rows as feature | taxonomy ambiguity | 48,621 audit proxy rows | diagnostic only |
| negotiated fee | observed `fee_eur > 0` for disclosed paid permanent deals only | likely transaction fee | true player value | post-transfer MV/current contracts | fee disclosure MNAR | 5,151 strict V1 candidate rows | V1-CANDIDATE |
| observed wage | observed player wage at prediction timestamp | salary cost | fee or surplus | current snapshot leakage | source/licence selection | not clean historical PIT | NOT V1-SUPPORTED |

## Future Market Value Caution

INFERENCE - Forward market-value growth is not independent ground truth. It is contaminated by later transfer events, survival in observable leagues, regression to mean, age effects, and Transfermarkt consensus dynamics.

## Primary V1 Labels

OWNER DECISION REQUIRED - No single label currently proves genuine undervaluation. The recommended V1 keeps fee, sporting contribution, wage, replacement importance and surplus as separate outputs. Negotiated fee is the only V1-candidate supervised continuous target, and only under the strict exact-date paid-permanent scope.

## Sporting MVP target correction

FACT - `reports/sporting-mvp/validated-output-contract.csv` is a development-only next-season minutes output contract. It is not a validated sporting-quality, total-contribution, fee, market-consensus-value, or buyer-specific economic-value contract.

FACT - Available-minute shares now use an audited competition-season table: Bundesliga uses 34 matches where supported; Premier League, La Liga, Ligue 1 and Serie A use 38 matches where supported. Unsupported or interrupted formats, including Ligue 1 2019/20 as represented by outcome season 2020, keep raw minutes but set share to null with `ABSTAIN_UNSUPPORTED_DENOMINATOR`.

FACT - Missing future outcomes and missing prior sporting-rate components remain null. A genuine zero is valid only when observation coverage is established through the corresponding observation-status field.
