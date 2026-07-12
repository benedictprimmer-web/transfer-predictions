"""Player crosswalk: Understat player_id  <->  Transfermarkt player_id.

The sibling of ingest/crosswalk.py (which bridges *match* ids). Until the
shots.pkl fidelity fix (2026-07-12) the Understat side had no player_id, so
every downstream Understat<->TM player join was name-based and fragile. Now
that shots.pkl carries `player_id`, we can build a real id<->id bridge and
retire the name join.

Method — match within (league, season), then reconcile per Understat player:
  * per league-season, normalize both sides' names (crosswalk.norm_player);
  * a normalized name unique on BOTH sides -> match  (method 'name');
  * if it collides, disambiguate by club: the TM candidate whose normalized
    club equals the Understat team -> match  (method 'club');
  * each matched (us_pid -> tm_pid) is a *vote*. A player appears in many
    league-seasons; reconcile to the tm_pid with the most votes, and record
    vote_share (agreement) + n_seasons as the confidence signal.

Output: data/crosswalk/players.csv
  us_player_id, tm_player_id, us_name, tm_name, n_seasons, votes, vote_share, method
One row per Understat player that resolved to a TM player.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

from ingest.crosswalk import norm_player, norm_team

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "crosswalk"


def _vote_pairs(us: pd.DataFrame, tm: pd.DataFrame) -> pd.DataFrame:
    """One (us_pid, tm_pid, method) vote per (league, season) agreement.

    us: league, season, us_pid, us_name_norm, us_team_norm
    tm: league, season, tm_pid, tm_name_norm, tm_club_norm
    """
    votes = []
    keys = set(map(tuple, us[["league", "season"]].drop_duplicates().to_numpy()))
    tm_g = {k: g for k, g in tm.groupby(["league", "season"])}
    for (lg, se), ug in us.groupby(["league", "season"]):
        tg = tm_g.get((lg, se))
        if tg is None:
            continue
        # unique-name pools on each side within this league-season
        us_counts = ug.us_name_norm.value_counts()
        tm_counts = tg.tm_name_norm.value_counts()
        tm_by_name = {n: g for n, g in tg.groupby("tm_name_norm")}
        for r in ug.itertuples():
            n = r.us_name_norm
            cands = tm_by_name.get(n)
            if cands is None:
                continue
            if us_counts[n] == 1 and tm_counts[n] == 1:
                votes.append((r.us_pid, cands.iloc[0].tm_pid, "name"))
            else:
                # name collision -> disambiguate by club
                hit = cands[cands.tm_club_norm == r.us_team_norm]
                if len(hit) == 1:
                    votes.append((r.us_pid, hit.iloc[0].tm_pid, "club"))
    return pd.DataFrame(votes, columns=["us_pid", "tm_pid", "method"])


def reconcile(votes: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-season votes to one tm_pid per us_pid (modal, with share)."""
    if votes.empty:
        return pd.DataFrame(columns=["us_player_id", "tm_player_id", "n_seasons",
                                     "votes", "vote_share", "method"])
    g = votes.groupby(["us_pid", "tm_pid"])
    tally = g.size().rename("votes").reset_index()
    tally["method"] = g.method.agg(lambda s: "club" if (s == "club").all() else "name").values
    total = tally.groupby("us_pid").votes.transform("sum")
    tally["vote_share"] = tally.votes / total
    # winner = most votes per us_pid; ties broken by 'name' method then tm_pid
    tally["_pri"] = (tally.method == "name").astype(int)
    win = (tally.sort_values(["us_pid", "votes", "_pri", "tm_pid"],
                             ascending=[True, False, False, True])
                .drop_duplicates("us_pid"))
    return win[["us_pid", "tm_pid", "votes", "vote_share", "method"]].rename(
        columns={"us_pid": "us_player_id", "tm_pid": "tm_player_id"})


# ------------------------------------------------------------------ build

def _us_players(shots: pd.DataFrame) -> pd.DataFrame:
    d = shots.dropna(subset=["player_id"]).copy()
    d["us_pid"] = d.player_id.astype("int64")
    d["us_name_norm"] = d.player.map(norm_player)
    d["us_team_norm"] = d.team_shot.map(norm_team)
    return (d[["league", "season", "us_pid", "player", "us_name_norm", "us_team_norm"]]
            .drop_duplicates(["league", "season", "us_pid"]))


def _tm_players() -> pd.DataFrame:
    """TM player-league-seasons from appearances, season from games, club name
    from clubs. Big-5 only (Understat's TM-coverable leagues)."""
    from ingest.transfermarkt import BIG5, _read, _season
    ap = _read("appearances", usecols=["game_id", "player_id", "player_club_id",
                                        "player_name", "competition_id"])
    ap = ap[ap.competition_id.isin(BIG5)]
    gm = _read("games", usecols=["game_id", "season"])
    cl = _read("clubs", usecols=["club_id", "name"])
    d = ap.merge(gm, on="game_id", how="left").merge(
        cl.rename(columns={"club_id": "player_club_id", "name": "club_name"}),
        on="player_club_id", how="left")
    d["league"] = d.competition_id.map(BIG5)
    d["season"] = d.season.map(lambda y: _season(y) if pd.notna(y) else None)
    d["tm_pid"] = pd.to_numeric(d.player_id, errors="coerce").astype("Int64")
    d["tm_name_norm"] = d.player_name.map(norm_player)
    d["tm_club_norm"] = d.club_name.map(lambda s: norm_team(s) if pd.notna(s) else "")
    return (d.dropna(subset=["season", "tm_pid"])
             [["league", "season", "tm_pid", "player_name", "tm_name_norm", "tm_club_norm"]]
             .drop_duplicates(["league", "season", "tm_pid"]))


def build() -> pd.DataFrame:
    from ingest import understat
    shots = understat.read_shots()
    shots = shots[shots.league != "RUS-Premier League"]  # TM dump is Big-5 only
    us = _us_players(shots)
    tm = _tm_players()
    votes = _vote_pairs(us, tm)

    n_seasons = votes.groupby("us_pid").size().rename("n_seasons")
    xw = reconcile(votes)
    xw = xw.merge(n_seasons.rename("n_seasons_total"), left_on="us_player_id",
                  right_index=True, how="left")
    xw["n_seasons"] = xw.pop("n_seasons_total")

    # attach display names
    us_name = us.drop_duplicates("us_pid").set_index("us_pid").player
    tm_name = tm.drop_duplicates("tm_pid").set_index("tm_pid").player_name
    xw["us_name"] = xw.us_player_id.map(us_name)
    xw["tm_name"] = xw.tm_player_id.map(tm_name)
    xw = xw[["us_player_id", "tm_player_id", "us_name", "tm_name",
             "n_seasons", "votes", "vote_share", "method"]]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "players.csv"
    xw.to_csv(out, index=False)

    tot_us = us.us_pid.nunique()
    print(f"Understat players (Big-5):     {tot_us:,}")
    print(f"resolved to a TM player:       {len(xw):,}  ({100*len(xw)/tot_us:.1f}%)")
    print(f"  high-confidence (share=1.0): {int((xw.vote_share==1).sum()):,}")
    print(f"  method: {xw.method.value_counts().to_dict()}")
    print(f"  multi-season (n>=2):         {int((xw.n_seasons>=2).sum()):,}")
    # dupes: two Understat ids landing on one TM id (rare; report)
    dup = xw.tm_player_id.duplicated(keep=False).sum()
    print(f"  tm ids claimed by >1 us id:  {dup}  (name twins / merged accounts)")
    print(f"wrote {out}")
    return xw


def load() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "players.csv")


# ------------------------------------------------------------------ check

def _check():
    # us: 2 players, one unique-name, one name-collision resolved by club
    us = pd.DataFrame([
        ("EPL", "2020-2021", 1, "Bruno Fernandes", "bruno fernandes", "man united"),
        ("EPL", "2020-2021", 2, "Danny Ward", "danny ward", "leicester"),
        ("EPL", "2021-2022", 1, "Bruno Fernandes", "bruno fernandes", "man united"),
        ("EPL", "2020-2021", 3, "Danny Ward", "danny ward", "nott forest"),  # twin
    ], columns=["league", "season", "us_pid", "player", "us_name_norm", "us_team_norm"])
    tm = pd.DataFrame([
        ("EPL", "2020-2021", 900, "Bruno Fernandes", "bruno fernandes", "man united"),
        ("EPL", "2021-2022", 900, "Bruno Fernandes", "bruno fernandes", "man united"),
        ("EPL", "2020-2021", 901, "Danny Ward", "danny ward", "leicester"),
        ("EPL", "2020-2021", 902, "Danny Ward", "danny ward", "nott forest"),
    ], columns=["league", "season", "tm_pid", "player_name", "tm_name_norm", "tm_club_norm"])
    votes = _vote_pairs(us, tm)
    xw = reconcile(votes)
    m = xw.set_index("us_player_id").tm_player_id.to_dict()
    assert m[1] == 900, ("unique name, 2 seasons -> 1 tm id", m)
    assert m[2] == 901, ("collision resolved by club (Leicester)", m)
    assert m[3] == 902, ("collision resolved by club (Forest)", m)
    assert xw.set_index("us_player_id").loc[1].votes == 2      # both seasons voted
    assert xw.set_index("us_player_id").loc[2].method == "club"
    print(xw.to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
