"""Stage-4 panel: one row per Big-5→Big-5 mover, seasons 2014-15→2023-24.

A mover is a player whose modal team (most npxG-basis actions, from
impact/usage.py over Understat shots) changes between consecutive seasons,
with >=20 actions in season t-1 at the origin — a measurable prior.

Each row carries: origin usage/efficiency (t-1), destination realized
usage/efficiency (t), destination + origin club npxG-diff/90 before/after
(team context deltas), squad-churn controls, and the mover's WOWY at the
destination (validate/ronaldo.py's Understat↔TM join, impact/wowy.py maths).

Per MEMO_stage2 §2-3: 1-season WOWY is ~80% noise — this panel exists so the
Stage-4 regression can pool many movers and let the noise average out.

`python3 -m validate.stage4_panel`        -> offline _check
`python3 -m validate.stage4_panel build`  -> data/stage4/panel.csv (caches only)
"""
from pathlib import Path

import numpy as np
import pandas as pd

from impact.usage import usage_efficiency
from ingest.understat import read_shots

BIG5 = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A",
        "GER-Bundesliga", "FRA-Ligue 1"]
SEASONS = [f"{y}-{y + 1}" for y in range(2014, 2024)]
MIN_ACTIONS = 20
OUT = Path(__file__).resolve().parent.parent / "data" / "stage4" / "panel.csv"

COLS = ["player", "season_from", "season_to", "league_from", "league_to",
        "team_from", "team_to",
        "usage_share_from", "shot_share_from", "efficiency_from",
        "actions_from", "value_from",
        "usage_share_to", "efficiency_to", "actions_to", "value_to",
        "team_np_xgd90_before", "team_np_xgd90_after", "delta_team_xgd90",
        "team_from_np_xgd90_before", "team_from_np_xgd90_after",
        "delta_team_from_xgd90",
        "n_other_movers_in", "usage_inflow_other"]


def modal_usage(shots: pd.DataFrame) -> pd.DataFrame:
    """Per (player, season): the usage_efficiency row at the modal team —
    the team where the player logged the most actions that season.
    ponytail: name collisions (two players, one name, different leagues)
    collapse to the bigger row; upgrade path is the crosswalk's player ids."""
    ue = usage_efficiency(shots)
    return (ue.sort_values("actions")
              .groupby(["player", "season"], as_index=False).tail(1))


def team_np_xgd90(shots: pd.DataFrame) -> pd.Series:
    """Per (league, season, team): npxG for minus npxG against, per match.
    Penalties excluded; matches (from the full shots frame) proxy the 90s."""
    s = shots[shots.situation != "Penalty"]
    against = np.where(s.team_shot == s.home_team, s.away_team, s.home_team)
    xf = s.groupby(["league", "season", "team_shot"]).xg.sum()
    xa = s.groupby(["league", "season", against]).xg.sum()
    sides = pd.concat([
        shots[["league", "season", "game_id", "home_team"]]
        .rename(columns={"home_team": "team"}),
        shots[["league", "season", "game_id", "away_team"]]
        .rename(columns={"away_team": "team"})])
    n = sides.groupby(["league", "season", "team"]).game_id.nunique()
    names = ["league", "season", "team"]
    xf.index.names = xa.index.names = names
    r = pd.DataFrame({"xf": xf, "xa": xa}).reindex(n.index).fillna(0.0)
    return (r.xf - r.xa) / n


def movers(shots: pd.DataFrame, min_actions: int = MIN_ACTIONS) -> pd.DataFrame:
    """The panel, minus WOWY: one row per modal-team change between
    consecutive seasons with >= min_actions at the origin in t-1."""
    mu = modal_usage(shots)
    txgd = team_np_xgd90(shots)

    def tx(league, season, team):
        return txgd.reindex(
            pd.MultiIndex.from_arrays([league, season, team])).to_numpy()

    rows = []
    seasons = sorted(mu.season.unique())
    for s0, s1 in zip(seasons[:-1], seasons[1:]):
        m = mu[mu.season == s0].merge(mu[mu.season == s1],
                                      on="player", suffixes=("_from", "_to"))
        m = m[(m.team_from != m.team_to) & (m.actions_from >= min_actions)]
        rows.append(m)
    p = pd.concat(rows, ignore_index=True)

    p["team_np_xgd90_before"] = tx(p.league_to, p.season_from, p.team_to)
    p["team_np_xgd90_after"] = tx(p.league_to, p.season_to, p.team_to)
    p["delta_team_xgd90"] = p.team_np_xgd90_after - p.team_np_xgd90_before
    p["team_from_np_xgd90_before"] = tx(p.league_from, p.season_from, p.team_from)
    p["team_from_np_xgd90_after"] = tx(p.league_from, p.season_to, p.team_from)
    p["delta_team_from_xgd90"] = (p.team_from_np_xgd90_after
                                  - p.team_from_np_xgd90_before)

    # squad churn: the OTHER qualifying movers landing at team_to same summer
    g = p.groupby(["league_to", "season_to", "team_to"])
    p["n_other_movers_in"] = g.player.transform("size") - 1
    p["usage_inflow_other"] = (g.usage_share_from.transform("sum")
                               - p.usage_share_from)
    return p[COLS].sort_values(["season_to", "league_to", "team_to", "player"],
                               ignore_index=True)


def attach_wowy(panel: pd.DataFrame) -> pd.DataFrame:
    """Mover's wowy/on_min/off_min at team_to in season_to, via
    validate.ronaldo.wowy_inputs — run once per (league_to, season_to).
    TM-vs-Understat name mismatches stay NaN; caller reports the rate."""
    import functools
    import ingest.transfermarkt
    from impact.wowy import wowy
    from validate.ronaldo import wowy_inputs

    # ponytail: memoize the TM loader so ~45 wowy_inputs calls read the csvs
    # once (read_shots already caches its own pkl). Process-local.
    ingest.transfermarkt.read_minutes = functools.lru_cache(maxsize=1)(
        ingest.transfermarkt.read_minutes)

    frames = {}
    for lg, ss in (panel[["league_to", "season_to"]]
                   .drop_duplicates().itertuples(index=False)):
        lu, sh = wowy_inputs(lg, ss)
        r = wowy(lu, sh)[["player", "team", "wowy", "on_min", "off_min"]]
        r["league_to"], r["season_to"] = lg, ss
        frames[(lg, ss)] = r
        print(f"wowy {lg} {ss}: {len(r):,} player-teams")
    w = pd.concat(frames.values()).rename(columns={"team": "team_to"})
    return panel.merge(w, on=["player", "team_to", "league_to", "season_to"],
                       how="left")


def build():
    shots = read_shots()
    shots = shots[shots.league.isin(BIG5) & shots.season.isin(SEASONS)]
    p = attach_wowy(movers(shots))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    p.to_csv(OUT, index=False)

    cross = (p.league_from != p.league_to).sum()
    print(f"\n{len(p):,} mover rows -> {OUT}")
    print(f"cross-league {cross:,} / within-league {len(p) - cross:,}")
    print("movers per season pair:")
    print(p.groupby(["season_from", "season_to"]).size().to_string())
    print(f"WOWY matched: {p.wowy.notna().sum():,}/{len(p):,} "
          f"({p.wowy.notna().mean():.1%})")
    print(f"delta_team_xgd90 mean {p.delta_team_xgd90.mean():+.3f} "
          f"sd {p.delta_team_xgd90.std():.3f}")
    return p


def _check():
    # 1 league, 2 teams, 2 seasons, 1 planted mover M: X (2014-15) -> Y.
    def sh(n, season, team, player, xg, situation="OpenPlay"):
        game, home = ("g1", "X") if season == "2014-2015" else ("g2", "X")
        return [dict(league="L", season=season, game_id=game, home_team=home,
                     away_team="Y", team_shot=team, player=player,
                     player_assisted=None, xg=xg, result="MissedShots",
                     situation=situation)] * n

    rows = (sh(20, "2014-2015", "X", "M", 0.1)      # the mover's prior: 20 actions
            + sh(5, "2014-2015", "X", "P", 0.2)
            + sh(1, "2014-2015", "X", "P", 0.76, "Penalty")  # excluded everywhere
            + sh(10, "2014-2015", "Y", "Q", 0.1)
            + sh(10, "2015-2016", "Y", "M", 0.3)    # M moved to Y
            + sh(10, "2015-2016", "Y", "Q", 0.1)
            + sh(5, "2015-2016", "X", "P", 0.2))
    shots = pd.DataFrame(rows)

    p = movers(shots)
    assert len(p) == 1, p          # only M moved; P and Q stayed put
    r = p.iloc[0]
    assert (r.player, r.team_from, r.team_to) == ("M", "X", "Y")
    assert (r.season_from, r.season_to) == ("2014-2015", "2015-2016")
    assert r.league_from == r.league_to == "L"

    # origin: X 2014-15 has 25 np actions (penalty excluded), M took 20
    assert r.actions_from == 20 and np.isclose(r.value_from, 2.0)
    assert np.isclose(r.usage_share_from, 0.8) and np.isclose(r.shot_share_from, 0.8)
    assert np.isclose(r.efficiency_from, 0.1)
    # destination realized: Y 2015-16, 10 of 20 actions at 0.3 xG each
    assert r.actions_to == 10 and np.isclose(r.value_to, 3.0)
    assert np.isclose(r.usage_share_to, 0.5) and np.isclose(r.efficiency_to, 0.3)

    # team context: s0 X npxGD = 3.0-1.0 = +2, Y = -2; s1 X = 1.0-4.0 = -3, Y = +3
    assert np.isclose(r.team_np_xgd90_before, -2.0)
    assert np.isclose(r.team_np_xgd90_after, 3.0)
    assert np.isclose(r.delta_team_xgd90, 5.0)
    assert np.isclose(r.team_from_np_xgd90_before, 2.0)
    assert np.isclose(r.team_from_np_xgd90_after, -3.0)
    assert np.isclose(r.delta_team_from_xgd90, -5.0)

    # churn: M is the only qualifying mover into Y
    assert r.n_other_movers_in == 0 and np.isclose(r.usage_inflow_other, 0.0)

    # threshold is a real gate: demand more prior actions than M has -> no rows
    assert movers(shots, min_actions=21).empty

    print(p.round(3).T.to_string())
    print("ok")


if __name__ == "__main__":
    import sys
    build() if "build" in sys.argv[1:] else _check()
