# Sporting MVP Contract

Status: development-only evidence explorer. The locked test is not opened.

## Question

Can strict-prior sporting-rate evidence improve a next-season minutes/availability model after controlling for age, role, prior minutes and data freshness?

This corrected MVP formally abstains: `ABSTAIN_INSUFFICIENT_TEMPORAL_RATE_COVERAGE`. The event-safe minutes baseline is usable for development diagnostics, but current prior sporting-rate coverage is too recent and sparse for a credible temporal persistence test. This does not establish whether future sporting quality or total sporting contribution is predictable.

## Output Contract

The validated output is `reports/sporting-mvp/validated-output-contract.csv`.

Each row is a retrospective development prediction event with:

- `prediction_event_key` / `prediction_key`: deterministic `spmvp1` prediction-event key.
- `player_id`, `player_name`, `role`, `to_league`.
- `outcome_season`: validation season, always below the locked period.
- `next_minutes`: observed next-season minutes. Missing values are excluded from model metrics.
- `next_available_minutes`, `next_minutes_share`, `next_minutes_observation_status`: competition-season denominator and observation status. Unsupported denominators retain raw minutes and null shares.
- `s0_pred`: fold-fitted joint age-role ridge baseline.
- `m0_pred`: S0 plus prior minutes and data freshness.
- `s1_pred`: M0 plus fold-fitted shrunk prior sporting-rate evidence for supported rows; otherwise fallback to M0.
- `s1_evidence_status`: whether a row has supported rate evidence or a fallback reason.
- `shrunk_prior_sporting_rate`: price-blind prior sporting rate after exposure shrinkage.
- `feature_tier`, `club_match_confidence`: support indicators.

Never display this output as future sporting quality, total contribution, true player value, fee residual, market value, buyer-specific surplus, or a production recommendation. The visual MVPs label all rows as retrospective development examples.

## Commands

```bash
python3 -m ingest.merge
python3 -m ingest.warehouse build
python3 -m validate.v3_sporting_target
python3 -m validate.sporting_mvp_integrity
python3 -m validate.sporting_mvp_models
python3 -m validate.sporting_mvp_visuals
```
