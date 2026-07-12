"""Does age-adjusting the traveling efficiency lift the Stage-4 correlation?
Same standing rule as league strength: a refinement must move r or it doesn't ship.

Baseline predictor treats efficiency_from as static — but a mover is a year (or
more) older at the destination. Here we scale efficiency_from by the age-curve
ratio mult(age_to)/mult(age_from) for his position, then re-run the identical
gate. A rising 21yo gets ratio>1 (predict improvement); a declining 33yo gets
ratio<1. If age carries signal about which movers help their teams, the lift
shows up strongest on the young/old tails where the ratio departs most from 1.

Run: `python3 -m validate.stage5_age_gate`      -> _check (synthetic, no network)
     `python3 -m validate.stage5_age_gate run`  -> real gate.
"""
import numpy as np
import pandas as pd

from validate.stage4 import add_prediction, team_eff_before, boot_corr
from impact.aging import age_multiplier


def _season_age(season: pd.Series, dob: pd.Series) -> pd.Series:
    """Age at the Jan-1 season midpoint (matches impact.aging's convention)."""
    yr = season.str[:4].astype(int)
    mid = pd.to_datetime(dict(year=yr + 1, month=1, day=1))
    return (mid - dob).dt.days / 365.25


def _bio() -> pd.DataFrame:
    """Per-player DOB + position from Transfermarkt, unique-normalized-name join
    (same dedup as impact.aging.player_seasons — an ambiguous name is a wrong join)."""
    from ingest.transfermarkt import _read, download
    from ingest.crosswalk import norm_player
    download(("players",))
    pl = _read("players", usecols=["player_id", "name", "date_of_birth", "position"])
    pl["key"] = pl.name.map(norm_player)
    solo = pl.groupby("key").player_id.nunique().loc[lambda s: s == 1].index
    pl = pl[pl.key.isin(solo)].drop_duplicates("key")
    return pl[["key", "date_of_birth", "position"]]


def _age_ratio(age_from, age_to, position):
    """mult(age_to)/mult(age_from) for the position's curve; NaN if unusable
    (missing age/pos, or a GK — no attacking curve)."""
    if pd.isna(position) or pd.isna(age_from) or pd.isna(age_to):
        return np.nan
    try:
        return age_multiplier(age_to, position)[0] / age_multiplier(age_from, position)[0]
    except KeyError:
        return np.nan


def add_age_prediction(p: pd.DataFrame) -> pd.DataFrame:
    from ingest.crosswalk import norm_player
    p = p.copy()
    p["key"] = p.player.map(norm_player)
    p = p.merge(_bio(), on="key", how="left")
    dob = pd.to_datetime(p.date_of_birth, errors="coerce")
    p["age_from"] = _season_age(p.season_from, dob)
    p["age_to"] = _season_age(p.season_to, dob)
    p["age_ratio"] = [_age_ratio(af, at, pos)
                      for af, at, pos in zip(p.age_from, p.age_to, p.position)]
    p["eff_from_aged"] = p.efficiency_from * p.age_ratio
    p["predicted_gain_age"] = p.usage_share_from * (p.eff_from_aged - p.team_to_eff_before)
    return p


def _report(frame, label):
    print(f"\n{label} (n={frame.delta_team_xgd90.notna().sum()}):")
    for tname, pred in [("baseline     ", "predicted_gain"),
                        ("age-adjusted ", "predicted_gain_age")]:
        r, (lo, hi), n = boot_corr(frame[pred], frame.delta_team_xgd90)
        print(f"  {tname} vs team-delta: r={r:+.3f} CI[{lo:+.3f},{hi:+.3f}] n={n}")
    pw = frame[frame.on_min >= 450]
    for tname, pred in [("baseline     ", "predicted_gain"),
                        ("age-adjusted ", "predicted_gain_age")]:
        r, (lo, hi), n = boot_corr(pw[pred], pw.wowy)
        print(f"  {tname} vs WOWY:       r={r:+.3f} CI[{lo:+.3f},{hi:+.3f}] n={n}")


def run():
    from ingest.understat import read_shots
    panel = pd.read_csv("data/stage4/panel.csv")
    p = add_prediction(panel, team_eff_before(read_shots()))
    p = add_age_prediction(p)

    # apples-to-apples: only rows where BOTH predictors exist
    m = p[p.predicted_gain.notna() & p.predicted_gain_age.notna()].copy()
    print(f"panel {len(p)}; age+position matched with prediction: {len(m)} "
          f"({100 * len(m) / len(p):.0f}%)")
    print(f"age_from: median {m.age_from.median():.1f}, "
          f"<23: {(m.age_from < 23).sum()}, >=30: {(m.age_from >= 30).sum()}")

    print("\n=== does age adjustment lift r? (spearman, boot 95% CI) ===")
    _report(m, "ALL matched movers")
    _report(m[m.age_from < 23], "YOUNG (age_from < 23)")
    _report(m[m.age_from >= 30], "OLD (age_from >= 30)")


def _check():
    # age computation: a 2000-06-01 DOB is ~21.6 at the 2021-2022 midpoint (Jan 2022)
    dob = pd.to_datetime(pd.Series(["2000-06-01"]))
    age = _season_age(pd.Series(["2021-2022"]), dob).iloc[0]
    assert 21.4 < age < 21.8, age

    # ratio direction: young player rising toward peak -> >1; old declining -> <1
    young = _age_ratio(20.0, 21.0, "Attack")
    old = _age_ratio(33.0, 34.0, "Attack")
    assert young > 1.0, young
    assert old < 1.0, old
    # missing/GK -> NaN, never a crash
    assert np.isnan(_age_ratio(np.nan, 25.0, "Attack"))
    assert np.isnan(_age_ratio(25.0, 26.0, "Goalkeeper"))
    print(f"age@2021-22={age:.2f}; young-ratio={young:.3f} old-ratio={old:.3f}")
    print("ok")


if __name__ == "__main__":
    import sys
    run() if "run" in sys.argv[1:] else _check()
