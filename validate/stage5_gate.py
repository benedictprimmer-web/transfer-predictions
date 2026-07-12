"""Does league strength lift the Stage-4 correlation? The standing rule:
a refinement must move r or it doesn't ship.

Baseline predictor compared efficiency_from (in the ORIGIN league) against the
destination team's bar — an apples-to-oranges comparison for cross-league
movers. Here we translate efficiency_from into destination-league terms via the
fitted multipliers, then re-run the identical gate. Within-league movers are
unaffected (ratio = 1), so any change is pure cross-league signal.
"""
import numpy as np
import pandas as pd

from validate.stage4 import add_prediction, team_eff_before, boot_corr
from impact.leagues import multiplier_map, translate


def run():
    from ingest.understat import read_shots
    shots = read_shots()
    panel = pd.read_csv("data/stage4/panel.csv")
    p = add_prediction(panel, team_eff_before(shots))

    strength = pd.read_csv("data/league_strength.csv")
    mult = multiplier_map(strength)

    # translated efficiency: restate origin efficiency in destination terms
    p["eff_from_translated"] = translate(
        p.efficiency_from.values, p.league_from.values, p.league_to.values, mult)
    p["predicted_gain_lg"] = p.usage_share_from * (p.eff_from_translated - p.team_to_eff_before)

    cross = p[p.league_from != p.league_to]
    print(f"panel {len(p)}; cross-league movers {len(cross)} "
          f"({cross.predicted_gain_lg.notna().sum()} with prediction)")
    print(f"multipliers: " + ", ".join(f"{k.split('-')[0]} {v}" for k, v in mult.items()))

    print("\n=== does league adjustment lift r? (spearman, boot 95% CI) ===")
    for label, frame in [("ALL movers", p), ("CROSS-league only", cross)]:
        print(f"\n{label} (n={frame.delta_team_xgd90.notna().sum()}):")
        for tname, pred in [("baseline predictor", "predicted_gain"),
                            ("league-adjusted   ", "predicted_gain_lg")]:
            r, (lo, hi), n = boot_corr(frame[pred], frame.delta_team_xgd90)
            print(f"  {tname} vs team-delta: r={r:+.3f} CI[{lo:+.3f},{hi:+.3f}] n={n}")
        pw = frame[frame.on_min >= 450] if "on_min" in frame else frame
        for tname, pred in [("baseline predictor", "predicted_gain"),
                            ("league-adjusted   ", "predicted_gain_lg")]:
            r, (lo, hi), n = boot_corr(pw[pred], pw.wowy)
            print(f"  {tname} vs WOWY:       r={r:+.3f} CI[{lo:+.3f},{hi:+.3f}] n={n}")


if __name__ == "__main__":
    run()
