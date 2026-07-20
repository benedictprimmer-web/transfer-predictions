# Sporting MVP Contract

Status: development-only evidence explorer. The locked test is not opened.

## Question

Can strict-prior player data predict future sporting contribution better than a simple age/role history baseline, with enough temporal stability to support a cautious scouting shortlist?

This MVP answers: not yet. S1 did not clear the predeclared gate, so no production sporting ranking is produced.

## Output Contract

The validated output is `reports/sporting-mvp/validated-output-contract.csv`.

Each row is a retrospective development prediction event with:

- `prediction_key`: deterministic `spmvp1` prediction key.
- `player_id`, `player_name`, `role`, `to_league`.
- `outcome_season`: validation season, always below the locked period.
- `next_minutes`: observed next-season minutes. Missing values are excluded from model metrics.
- `s0_pred`: age/role historical baseline.
- `s1_pred`, `s1_lo`, `s1_hi`: shrunk prior sporting-evidence estimate and uncertainty band.
- `shrunk_prior_sporting_rate`: price-blind prior sporting rate after exposure shrinkage.
- `feature_tier`, `club_match_confidence`: support indicators.

Never display this output as true player value, fee residual, market value, buyer-specific surplus, or a production recommendation. The visual MVPs label all rows as retrospective development examples.

## Commands

```bash
python3 -m ingest.merge
python3 -m ingest.warehouse build
python3 -m validate.v3_sporting_target
python3 -m validate.sporting_mvp_integrity
python3 -m validate.sporting_mvp_models
python3 -m validate.sporting_mvp_visuals
```

