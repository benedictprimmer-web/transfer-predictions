"""Stage-3 acceptance test: Ronaldo's Man Utd 2021-22 WOWY must be negative.

Individual output good, team worse with him on — WOWY is the layer that can
see it (per-action efficiency provably cannot: impact/usage.py gate 2 runs).

Joins Understat shots (xG, shot minutes) to Transfermarkt lineups (on/off
windows) through the crosswalk, remaps team spellings to Understat's, and
runs the existing wowy estimator unchanged.
"""
import pandas as pd

from impact.wowy import wowy


def wowy_inputs(league: str, season: str):
    """(lineups, shots) for one league-season, joined + name-aligned.

    Everything reads from local caches; run the ingest builds first.
    """
    from ingest.understat import read_shots
    from ingest.transfermarkt import read_minutes, DATA_DIR as TM_DIR

    cw = pd.read_csv("data/crosswalk/matches.csv", dtype=str)
    cw = cw[(cw.league == league) & (cw.season == season)]

    sh = read_shots()
    sh = sh[(sh.league == league) & (sh.season == season)].copy()
    sh["game_id"] = sh.game_id.map(dict(zip(cw.understat_game_id, cw.tm_game_id)))
    sh = sh.dropna(subset=["game_id"])

    lu = read_minutes()
    lu = lu[(lu.league == league) & (lu.season == season)].copy()
    lu = lu[lu.game_id.isin(set(cw.tm_game_id))]

    # remap TM team spelling -> Understat spelling: TM games says who was home,
    # the crosswalk row carries Understat's home/away names for that game.
    games = pd.read_csv(TM_DIR / "games.csv.gz", usecols=["game_id", "home_club_name"],
                        dtype={"game_id": str})
    lu = lu.merge(games, on="game_id", how="left")
    lu = lu.merge(cw[["tm_game_id", "home", "away"]],
                  left_on="game_id", right_on="tm_game_id", how="left")
    is_home = lu.team == lu.home_club_name
    lu["team"] = lu.home.where(is_home, lu.away)
    lu = lu[["game_id", "team", "player", "is_starter", "minutes"]]

    sh = sh.rename(columns={})[["game_id", "team_shot", "minute", "xg"]]
    return lu, sh


def _check():
    # offline: two tiny frames through the same remap logic shape — the pure
    # part here is just column plumbing; wowy.py carries the maths checks.
    lu = pd.DataFrame([
        dict(game_id="g1", team="X", player="A", is_starter=True, minutes=90),
        dict(game_id="g1", team="Y", player="B", is_starter=True, minutes=90),
    ])
    sh = pd.DataFrame([dict(game_id="g1", team_shot="X", minute=10, xg=0.5)])
    r = wowy(lu, sh).set_index("player")
    assert r.loc["A"].on_xgd90 > 0 and r.loc["B"].on_xgd90 < 0
    print("ok")


def main(team="Manchester United", player="Cristiano Ronaldo",
         league="ENG-Premier League", season="2021-2022"):
    lu, sh = wowy_inputs(league, season)
    print(f"{league} {season}: {lu.game_id.nunique()} games, "
          f"{len(lu):,} lineup rows, {len(sh):,} shots")
    r = wowy(lu, sh)
    squad = r[r.team == team].sort_values("wowy")
    cols = ["player", "on_min", "off_min", "on_xgd90", "off_xgd90", "raw", "shrink", "wowy"]
    print(f"\n=== {team} squad WOWY (sorted, worst first) ===")
    print(squad[cols].round(3).to_string(index=False))

    me = squad[squad.player.str.contains(player.split()[-1])]
    if me.empty:
        print(f"\n{player}: NOT FOUND — check name spelling across sources")
        return
    me = me.iloc[0]
    print(f"\nGATE — {player} WOWY: {me.wowy:+.3f} "
          f"(raw {me.raw:+.3f}, on {me.on_min:.0f}', off {me.off_min:.0f}') "
          f"-> {'PASS (negative)' if me.wowy < 0 else 'FAIL (non-negative)'}")


if __name__ == "__main__":
    import sys
    main() if "run" in sys.argv[1:] else _check()
