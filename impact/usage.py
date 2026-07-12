"""Usage and efficiency — the engine's core definitions (SPEC layer 2).

usage_i      = player's share of his team's terminal actions
efficiency_i = value produced per terminal action  (travels with the player)

From Understat shots alone, terminal actions = shots taken + shot-assists
(`player_assisted`), value = xG + assisted-xG. Turnovers (dispossessed,
miscontrols) join later from StatsBomb where covered; usage here is therefore
attacking usage. ponytail: denominator is team season totals, not
on-pitch-only minutes — MODELS.md accepts that bias at first; revisit via the
crosswalk once minutes are joined.

Stage-2 gate (run: `python3 -m impact.usage ronaldo`): Man Utd 2021-22 —
Ronaldo's shot share highest in the squad, efficiency below the players he
displaced. Definitions are wrong if this fails; do not loosen it.
"""
import numpy as np
import pandas as pd

KEY = ["league", "season", "team"]


def usage_efficiency(shots: pd.DataFrame, min_actions: int = 0) -> pd.DataFrame:
    """Per (league, season, team, player): usage share and efficiency.

    shots: the ingest.understat tidy schema (team_shot, player,
    player_assisted, xg, result). Own goals excluded — an OG credits the
    scorer to the *other* team's attack and is not a chosen terminal action.
    """
    s = shots[shots.result != "OwnGoal"].rename(columns={"team_shot": "team"})
    if "situation" in s.columns:
        # npxG basis: a penalty's ~0.76 xG is awarded, not created — counting
        # it inflates the taker's efficiency (Ronaldo took United's pens).
        s = s[s.situation != "Penalty"]

    taken = s.groupby(KEY + ["player"]).agg(shots=("xg", "size"), xg=("xg", "sum"))
    a = s.dropna(subset=["player_assisted"])
    assists = (a.groupby(KEY + ["player_assisted"])
                .agg(shot_assists=("xg", "size"), xag=("xg", "sum")))
    assists.index = assists.index.set_names("player", level=-1)

    t = taken.join(assists, how="outer").fillna(0.0)
    t["actions"] = t.shots + t.shot_assists
    t["value"] = t.xg + t.xag

    g = t.groupby(KEY)
    t["usage_share"] = t.actions / g.actions.transform("sum")
    t["shot_share"] = t.shots / g.shots.transform("sum")
    t["efficiency"] = np.where(t.actions > 0, t.value / t.actions, np.nan)

    t = t[t.actions >= min_actions]
    return t.reset_index().sort_values(
        KEY + ["usage_share"], ascending=[True] * len(KEY) + [False])


def merge_turnovers(usage: pd.DataFrame, turnovers: pd.DataFrame) -> pd.DataFrame:
    """Full-spec usage: terminal actions = attacking actions + turnovers.

    turnovers: ingest.fbref_snapshot.read_turnovers() schema (league, season,
    team, player, n90s, turnovers). Exact-name join; the crosswalk agent's
    normalizer upgrades this later. Rows without turnover data keep attacking
    usage with turnovers=NaN — flagged, never silently zeroed.
    """
    keep = [c for c in ["league", "season", "team", "player",
                        "n90s", "turnovers", "pos"] if c in turnovers.columns]
    m = usage.merge(turnovers[keep],
                    on=["league", "season", "team", "player"], how="left")
    m["actions_full"] = m.actions + m.turnovers          # NaN where no coverage
    g = m.groupby(KEY)
    m["usage_share_full"] = m.actions_full / g.actions_full.transform("sum")
    m["efficiency_full"] = m.value / m.actions_full      # turnovers add 0 value
    return m


def displacement_check(squad: pd.DataFrame, player: str, top_n: int = 6,
                       eff_col: str = "efficiency",
                       usage_col: str = "usage_share"):
    """Is `player`'s efficiency below the usage-weighted mean efficiency of
    the other top-`top_n` usage players (the ones his volume displaces)?

    ponytail: 'who he displaces' is really role overlap (SPEC layer 2);
    top-usage teammates is the first-cut proxy until replacement.py exists.
    Returns (player_row, displaced_frame, weighted_mean_efficiency, verdict).
    """
    sq = squad.sort_values(usage_col, ascending=False).reset_index(drop=True)
    me = sq[sq.player == player]
    if me.empty:
        raise KeyError(player)
    me = me.iloc[0]
    others = sq[sq.player != player].head(top_n)
    w_eff = float((others[eff_col] * others[usage_col]).sum()
                  / others[usage_col].sum())
    return me, others, w_eff, bool(me[eff_col] < w_eff)


def _check():
    # one team, three players. B = volume monster with poor efficiency:
    # most shots, lowest xg/shot. A = efficient sniper. C = creator.
    rows = []
    rows += [dict(team_shot="X", player="B", player_assisted=None,
                  xg=0.05, result="MissedShots")] * 10
    rows += [dict(team_shot="X", player="A", player_assisted="C",
                  xg=0.30, result="Goal")] * 4
    rows += [dict(team_shot="X", player="C", player_assisted="A",
                  xg=0.20, result="SavedShot")] * 2
    sh = pd.DataFrame(rows)
    sh["league"], sh["season"] = "L", "2021-2022"
    # own goal must be excluded from usage entirely
    sh = pd.concat([sh, pd.DataFrame([dict(
        league="L", season="2021-2022", team_shot="X", player="OGguy",
        player_assisted=None, xg=0.9, result="OwnGoal")])], ignore_index=True)

    t = usage_efficiency(sh)
    assert "OGguy" not in set(t.player), "own goals are not usage"
    assert np.isclose(t.usage_share.sum(), 1.0), "usage sums to 1 in a team"

    t = t.set_index("player")
    # B: 10 shots, 0 assists = 10 actions of 22 total (16 shots + 6 assists)
    assert t.loc["B"].actions == 10 and np.isclose(t.loc["B"].usage_share, 10 / 22)
    assert t.shot_share.idxmax() == "B", "B has the biggest shot share"
    # A: 4 shots (1.2 xG) + 2 shot-assists (0.4 xAG) = 6 actions, eff ~0.267
    assert np.isclose(t.loc["A"].efficiency, (4 * .3 + 2 * .2) / 6)
    assert t.loc["B"].efficiency < t.loc["A"].efficiency

    me, others, w_eff, worse = displacement_check(t.reset_index(), "B", top_n=2)
    assert worse, "the volume monster must flag as below displaced efficiency"

    # full usage: B also bleeds turnovers -> efficiency_full drops further
    tv = pd.DataFrame([dict(league="L", season="2021-2022", team="X",
                            player=p, n90s=10.0, turnovers=n)
                       for p, n in [("A", 2.0), ("B", 10.0), ("C", 2.0)]])
    f = merge_turnovers(t.reset_index(), tv).set_index("player")
    assert f.loc["B"].actions_full == 20 and np.isclose(
        f.loc["B"].efficiency_full, 0.5 / 20)
    assert np.isclose(f.usage_share_full.sum(), 1.0)
    assert f.loc["B"].efficiency_full < f.loc["B"].efficiency, "turnovers cost"

    print(t.round(3).to_string())
    print(f"B efficiency {me.efficiency:.3f} < displaced weighted {w_eff:.3f} -> {worse}")
    print("ok")


def _ronaldo():
    """The Stage-2 gate, on real data."""
    from ingest.understat import read_shots
    shots = read_shots()
    t = usage_efficiency(shots)
    squad = t[(t.league == "ENG-Premier League") & (t.season == "2021-2022")
              & (t.team == "Manchester United")]
    cols = ["player", "shots", "shot_assists", "actions", "usage_share",
            "shot_share", "efficiency"]
    top = squad.sort_values("shot_share", ascending=False).head(12)[cols]
    print(top.round(3).to_string(index=False))

    ron = squad.loc[squad.player.str.contains("Ronaldo"), "player"].iloc[0]
    me, others, w_eff, worse = displacement_check(squad, ron)
    print(f"\nGATE 1 — highest shot share: "
          f"{'PASS' if top.iloc[0].player == ron else 'FAIL'} "
          f"({ron} {me.shot_share:.1%})")
    print(f"GATE 2a (attacking-only npxG eff) — {me.efficiency:.3f} vs displaced "
          f"top-6 weighted {w_eff:.3f}: {'PASS' if worse else 'FAIL'}")

    # full spec definition: + dispossessed + miscontrols (FBref snapshot)
    from ingest.fbref_snapshot import read_turnovers
    full = merge_turnovers(squad, read_turnovers())
    fcols = ["player", "actions", "turnovers", "actions_full",
             "usage_share_full", "efficiency_full"]
    me2, others2, w_eff2, worse2 = displacement_check(
        full.dropna(subset=["actions_full"]), ron,
        eff_col="efficiency_full", usage_col="usage_share_full")
    print(f"GATE 2b (FULL usage: + turnovers) — {me2.efficiency_full:.3f} vs "
          f"displaced top-6 weighted {w_eff2:.3f}: {'PASS' if worse2 else 'FAIL'}")
    print(f"\nfull-usage squad table (top 10 by usage):")
    print(full.dropna(subset=["actions_full"])
              .sort_values("usage_share_full", ascending=False)
              .head(10)[fcols].round(3).to_string(index=False))
    print("\ndisplaced under full usage (top-6):")
    print(others2[fcols].round(3).to_string(index=False))


if __name__ == "__main__":
    import sys
    _ronaldo() if "ronaldo" in sys.argv[1:] else _check()
