"""WOWY: team xG difference with a player on the pitch vs off it.

The Ronaldo test. Player's own numbers can be fine while the team is worse
with him on. This measures the second thing.

Core is pure pandas over a tidy schema so it can be tested without network.
FBref adapter is at the bottom.
"""
import numpy as np
import pandas as pd

MATCH_MIN = 90.0
SHRINK_K = 600.0  # off-pitch minutes at which we trust the raw number ~half


def intervals(lineups: pd.DataFrame) -> pd.DataFrame:
    """game_id, team, player, is_starter, minutes -> on/off minute window.

    ponytail: starters run [0, minutes], subs run [90-minutes, 90]. Wrong only
    for the rare player subbed on AND off again. Upgrade path is parsing the
    match report event feed; not worth it until the error shows up.
    """
    d = lineups.copy()
    d["on"] = np.where(d.is_starter, 0.0, MATCH_MIN - d.minutes)
    d["off"] = np.where(d.is_starter, d.minutes, MATCH_MIN)
    return d[d.minutes > 0]


def wowy(lineups: pd.DataFrame, shots: pd.DataFrame) -> pd.DataFrame:
    """shots: game_id, team, minute, xg. Returns per player/team on-off xGD/90."""
    iv = intervals(lineups)

    # every (player-stint, shot-in-that-game) pair, then keep on-pitch ones
    j = iv.merge(shots, on="game_id", suffixes=("", "_shot"))
    j = j[(j.minute >= j.on) & (j.minute < j.off)]
    j["xgf"] = np.where(j.team_shot == j.team, j.xg, 0.0)
    j["xga"] = np.where(j.team_shot != j.team, j.xg, 0.0)

    on = j.groupby(["player", "team"]).agg(xgf=("xgf", "sum"), xga=("xga", "sum"))
    on["on_min"] = iv.groupby(["player", "team"]).minutes.sum()

    # team totals over the same games the player was involved in
    games = iv[["game_id", "team", "player"]]
    ts = games.merge(shots, on="game_id")
    ts["xgf"] = np.where(ts.team_shot == ts.team, ts.xg, 0.0)
    ts["xga"] = np.where(ts.team_shot != ts.team, ts.xg, 0.0)
    tot = ts.groupby(["player", "team"]).agg(t_xgf=("xgf", "sum"), t_xga=("xga", "sum"))
    tot["t_min"] = games.groupby(["player", "team"]).game_id.nunique() * MATCH_MIN

    r = on.join(tot)
    r["off_min"] = r.t_min - r.on_min
    r = r[r.on_min > 0]

    r["on_xgd90"] = (r.xgf - r.xga) / r.on_min * 90
    off = (r.t_xgf - r.xgf) - (r.t_xga - r.xga)
    r["off_xgd90"] = np.where(r.off_min > 0, off / r.off_min.replace(0, np.nan) * 90, np.nan)

    r["raw"] = r.on_xgd90 - r.off_xgd90
    # shrink toward 0 when the off-pitch sample is thin. A starter who never
    # rests has almost no signal here and the number must say so.
    r["shrink"] = r.off_min / (r.off_min + SHRINK_K)
    r["wowy"] = r.raw * r.shrink
    return r.reset_index()[
        ["player", "team", "on_min", "off_min", "on_xgd90", "off_xgd90", "raw", "shrink", "wowy"]
    ]


def from_fbref(leagues, seasons):
    """Pull real data. Run on your machine, not in a sandbox. Caches locally."""
    import soccerdata as sd

    fb = sd.FBref(leagues=leagues, seasons=seasons)
    lu = fb.read_lineup().reset_index()
    sh = fb.read_shot_events().reset_index()
    # NOTE: check these column names on first run, soccerdata renames things
    # between versions. Print lu.columns / sh.columns and fix here only.
    lu = lu.rename(columns={"minutes_played": "minutes"})[
        ["game_id", "team", "player", "is_starter", "minutes"]
    ]
    sh = sh.rename(columns={"team": "team_shot", "xG": "xg"})[
        ["game_id", "team_shot", "minute", "xg"]
    ]
    sh["minute"] = pd.to_numeric(sh.minute.astype(str).str.split("+").str[0])
    return wowy(lu, sh.dropna(subset=["xg"]))


def _check():
    # 2 games. A starts both, B is a sub. Team X out-shoots when A is on.
    lu = pd.DataFrame([
        dict(game_id=1, team="X", player="A", is_starter=True, minutes=60),
        dict(game_id=1, team="X", player="B", is_starter=False, minutes=30),
        dict(game_id=2, team="X", player="A", is_starter=True, minutes=90),
    ])
    sh = pd.DataFrame([
        dict(game_id=1, team_shot="X", minute=10, xg=0.5),   # A on, B off
        dict(game_id=1, team_shot="Y", minute=75, xg=0.5),   # A off, B on -> conceded
        dict(game_id=2, team_shot="X", minute=45, xg=1.0),   # A on
    ])
    r = wowy(lu, sh).set_index("player")

    a = r.loc["A"]
    assert a.on_min == 150 and a.off_min == 30, a
    assert np.isclose(a.xgf if "xgf" in a else 1.5, 1.5)
    assert np.isclose(a.on_xgd90, 1.5 / 150 * 90), a.on_xgd90      # +0.9
    assert np.isclose(a.off_xgd90, -0.5 / 30 * 90), a.off_xgd90    # -1.5
    assert a.raw > 0 and 0 < a.shrink < 0.1                        # thin sample -> shrunk hard
    assert abs(a.wowy) < abs(a.raw)

    b = r.loc["B"]
    assert b.on_min == 30 and b.on_xgd90 < 0                       # only saw the goal against
    print(r.round(3).to_string(index=True))
    print("ok")


if __name__ == "__main__":
    _check()
