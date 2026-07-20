# Sporting MVP Contract

Status: development-only evidence explorer. The locked test is not opened.

## Question

Can strict-prior player data improve a next-season minutes/availability model over a simple age/role history baseline?

This corrected MVP answers: no, not on the tested development contract. The tested handcrafted prior sporting-rate score did not produce stable temporal improvement over the age/role baseline for next-season minutes. This does not establish whether future sporting quality or total sporting contribution is predictable.

## Output Contract

The validated output is `reports/sporting-mvp/validated-output-contract.csv`.

Each row is a retrospective development prediction event with:

- `prediction_event_key` / `prediction_key`: deterministic `spmvp1` prediction-event key.
- `player_id`, `player_name`, `role`, `to_league`.
- `outcome_season`: validation season, always below the locked period.
- `next_minutes`: observed next-season minutes. Missing values are excluded from model metrics.
- `next_available_minutes`, `next_minutes_share`, `next_minutes_observation_status`: competition-season denominator and observation status.
- `s0_pred`: age/role historical baseline.
- `s1_pred`: shrunk prior sporting-rate challenger for next-season minutes. Calibrated intervals are not reported.
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
