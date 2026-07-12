"""StatsBomb open-data — the turnover engine (Dispossessed + Miscontrol).

Only clean free source of per-player turnovers (see DATA_SOURCES.md). Raw JSON
on GitHub: competitions.json -> matches/{comp}/{season}.json ->
events/{match_id}.json + lineups/{match_id}.json. Files cache (gzipped) to
data/statsbomb/ so the pull is paid once.

TRUE Big-5 *league* coverage (verified 2026-07-11, match counts in brackets):
full seasons only for EPL [380], La Liga [380], Serie A [380], Ligue 1 [377],
all 2015/16. Everything else is one team's matches: Bundesliga 15/16 + 23/24
(Leverkusen, 34 each), EPL 03/04 (Arsenal, 38), La Liga 04/05-14/15 + 16/17-
20/21 (Barcelona, 7-38 each), Ligue 1 21/22 + 22/23 (PSG, 26/32), Serie A
86/87 (1 match). DEFAULT_SEASONS below is the <=6-season build subset.

Outputs: tidy per-match lineups/minutes (the impact/wowy.py schema:
game_id, team, player, is_starter, minutes) + per player-season and
team-season turnover counts and per-90 rates.
"""
from __future__ import annotations
import gzip
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "statsbomb"
_RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data/{}"

# competition_id -> league key (understat.py naming). These five ids are the
# Big-5 men's domestic leagues in the open-data corpus.
LEAGUE_NAMES = {
    2:  "ENG-Premier League",
    11: "ESP-La Liga",
    12: "ITA-Serie A",
    9:  "GER-Bundesliga",
    7:  "FRA-Ligue 1",
}

# Build subset: the four FULL 2015/16 league seasons + both Leverkusen-only
# Bundesliga seasons so all five leagues are represented (<=6 league-seasons).
# Dropped: EPL 03/04 (Arsenal-only), all Barcelona-only La Liga seasons,
# PSG-only Ligue 1 21/22 + 22/23, Serie A 86/87 (1 match).
DEFAULT_SEASONS = [
    (2, 27),    # EPL 2015/16          full, 380 matches
    (11, 27),   # La Liga 2015/16      full, 380
    (12, 27),   # Serie A 2015/16      full, 380
    (7, 27),    # Ligue 1 2015/16      full, 377
    (9, 27),    # Bundesliga 2015/16   Leverkusen only, 34
    (9, 281),   # Bundesliga 2023/24   Leverkusen only, 34
]

# StatsBomb event type ids we care about. Nothing else is parsed.
_STARTING_XI, _SUBSTITUTION = 35, 19
_TURNOVER_TYPES = {3: "dispossessed", 38: "miscontrol"}


# ---------------------------------------------------------------- download --

def _fetch_json(rel: str, dest: Path, force=False):
    """GET one open-data file, cache gzipped, return parsed JSON."""
    if force or not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(_RAW.format(rel), timeout=90) as r:
            dest.write_bytes(gzip.compress(r.read()))
    return json.loads(gzip.decompress(dest.read_bytes()))


def competitions():
    return _fetch_json("competitions.json", DATA_DIR / "competitions.json.gz")


def matches(comp_id: int, season_id: int):
    return _fetch_json(f"matches/{comp_id}/{season_id}.json",
                       DATA_DIR / "matches" / f"{comp_id}_{season_id}.json.gz")


def events(match_id: int):
    return _fetch_json(f"events/{match_id}.json",
                       DATA_DIR / "events" / f"{match_id}.json.gz")


def lineups_raw(match_id: int):
    """Raw lineups file, cached for completeness; minutes come from events."""
    return _fetch_json(f"lineups/{match_id}.json",
                       DATA_DIR / "lineups" / f"{match_id}.json.gz")


def download_season(comp_id: int, season_id: int, workers=12) -> list[int]:
    """Cache events+lineups for every match of a league-season. One failed
    match is logged and skipped, never fatal. Returns usable match_ids."""
    mids = [m["match_id"] for m in matches(comp_id, season_id)]

    def pull(mid):
        try:
            events(mid)
            lineups_raw(mid)
            return mid
        except Exception as e:  # noqa: BLE001 — resilience is the point
            print(f"  SKIP match {mid}: {e}")
            return None

    with ThreadPoolExecutor(workers) as ex:
        return [m for m in ex.map(pull, mids) if m is not None]


# -------------------------------------------------------------------- tidy --

def big5_league_seasons(comps: list) -> pd.DataFrame:
    """competitions.json -> the Big-5 domestic-league seasons it truly has."""
    rows = [
        dict(competition_id=c["competition_id"], season_id=c["season_id"],
             league=LEAGUE_NAMES[c["competition_id"]],
             season=c["season_name"].replace("/", "-"))
        for c in comps if c["competition_id"] in LEAGUE_NAMES
    ]
    return pd.DataFrame(rows).sort_values(["league", "season"]).reset_index(drop=True)


def _match_end(evs: list) -> float:
    """Final whistle in cumulative minutes (2nd-half stoppage included)."""
    return max((e["minute"] for e in evs if e.get("period", 1) <= 2), default=90) + 1


def tidy_lineups(evs: list, game_id: str) -> pd.DataFrame:
    """Events of one match -> game_id, team, player, is_starter, minutes.

    Starters from Starting XI (type 35), entries/exits from Substitution
    (type 19). Real elapsed minutes incl. stoppage, so a full match is ~93-98.
    ponytail: red cards ignored — a sent-off player is counted to full time.
    Upgrade path: also close intervals on Bad Behaviour/red-card events.
    """
    end = _match_end(evs)
    on, off, team_of, starter = {}, {}, {}, {}
    for e in evs:
        tid = e["type"]["id"]
        if tid == _STARTING_XI:
            for p in e["tactics"]["lineup"]:
                name = p["player"]["name"]
                on[name], team_of[name], starter[name] = 0.0, e["team"]["name"], True
        elif tid == _SUBSTITUTION:
            out_p = e["player"]["name"]
            in_p = e["substitution"]["replacement"]["name"]
            off[out_p] = float(e["minute"])
            on[in_p], team_of[in_p], starter[in_p] = float(e["minute"]), e["team"]["name"], False
    rows = [dict(game_id=game_id, team=team_of[p], player=p,
                 is_starter=starter[p], minutes=off.get(p, end) - t_on)
            for p, t_on in on.items()]
    return pd.DataFrame(rows, columns=["game_id", "team", "player", "is_starter", "minutes"])


def tidy_turnovers(evs: list, game_id: str) -> pd.DataFrame:
    """Events of one match -> one row per Dispossessed/Miscontrol event."""
    rows = [dict(game_id=game_id, team=e["team"]["name"],
                 player=e["player"]["name"], event=_TURNOVER_TYPES[e["type"]["id"]])
            for e in evs
            if e["type"]["id"] in _TURNOVER_TYPES and "player" in e and "team" in e]
    return pd.DataFrame(rows, columns=["game_id", "team", "player", "event"])


_KEY = ["league", "season", "team", "player"]


def _turnover_counts(turnovers: pd.DataFrame, key: list) -> pd.DataFrame:
    tv = (turnovers.assign(n=1)
          .pivot_table(index=key, columns="event", values="n", aggfunc="sum", fill_value=0)
          .reindex(columns=["dispossessed", "miscontrol"], fill_value=0)
          .reset_index())
    tv.columns.name = None
    return tv


def player_season(lineups: pd.DataFrame, turnovers: pd.DataFrame) -> pd.DataFrame:
    """Per player-season minutes + turnover counts + per-90 rates.
    Both inputs must carry league/season columns (build adds them)."""
    ps = (lineups.groupby(_KEY)
          .agg(matches=("game_id", "nunique"), minutes=("minutes", "sum"))
          .reset_index()
          .merge(_turnover_counts(turnovers, _KEY), on=_KEY, how="left")
          .fillna({"dispossessed": 0, "miscontrol": 0}))
    for c in ("dispossessed", "miscontrol"):
        ps[c] = ps[c].astype(int)
        ps[f"{c}_p90"] = np.where(ps.minutes > 0, ps[c] / ps.minutes * 90, np.nan)
    ps["turnovers_p90"] = ps.dispossessed_p90 + ps.miscontrol_p90
    return ps


def team_season(lineups: pd.DataFrame, turnovers: pd.DataFrame) -> pd.DataFrame:
    """Team-level totals per league-season."""
    key = ["league", "season", "team"]
    ts = (lineups.groupby(key).agg(matches=("game_id", "nunique")).reset_index()
          .merge(_turnover_counts(turnovers, key), on=key, how="left")
          .fillna({"dispossessed": 0, "miscontrol": 0}))
    for c in ("dispossessed", "miscontrol"):
        ts[f"{c}_pm"] = ts[c] / ts.matches
    return ts


# ------------------------------------------------------------------- build --

def build(seasons=tuple(DEFAULT_SEASONS)):
    comps = competitions()
    cov = big5_league_seasons(comps)
    meta = {(c, s): (LEAGUE_NAMES[c], next(r.season for r in cov.itertuples()
                                           if r.competition_id == c and r.season_id == s))
            for c, s in seasons}
    print("TRUE Big-5 league coverage in open-data:")
    print(cov.to_string(index=False))
    print(f"\nBuilding {len(seasons)} league-seasons: "
          + ", ".join(f"{lg} {ssn}" for lg, ssn in meta.values()))

    lu_frames, to_frames = [], []
    for (c, s), (lg, ssn) in meta.items():
        mids = download_season(c, s)
        print(f"{lg} {ssn}: {len(mids)} matches cached")
        for mid in mids:
            try:
                evs = events(mid)
                gid = str(mid)
                lu_frames.append(tidy_lineups(evs, gid).assign(league=lg, season=ssn))
                to_frames.append(tidy_turnovers(evs, gid).assign(league=lg, season=ssn))
            except Exception as e:  # noqa: BLE001
                print(f"  SKIP tidy {mid}: {e}")

    lu = pd.concat(lu_frames, ignore_index=True)
    to = pd.concat(to_frames, ignore_index=True)
    ps, ts = player_season(lu, to), team_season(lu, to)

    for name, df in [("lineups", lu), ("turnovers", to),
                     ("player_season", ps), ("team_season", ts)]:
        df.to_csv(DATA_DIR / f"{name}.csv", index=False)

    reg = ps[ps.minutes >= 900]
    print(f"\n{lu.game_id.nunique():,} matches, {len(lu):,} lineup rows, "
          f"{len(to):,} turnover events, {len(ps):,} player-seasons")
    print("median per-90 (>=900 min): dispossessed "
          f"{reg.dispossessed_p90.median():.2f}, miscontrol {reg.miscontrol_p90.median():.2f}")
    print(f"wrote lineups/turnovers/player_season/team_season .csv to {DATA_DIR}")
    return lu, to, ps, ts


# ------------------------------------------------------------------- check --

def _check():
    # synthetic one-match event feed, no network. X beat-up: starter A goes
    # 90+4, starter B subbed off 60' for C; C miscontrols twice; A dispossessed.
    def ev(tid, **kw):
        return dict(type=dict(id=tid), period=kw.pop("period", 1),
                    minute=kw.pop("minute", 0), **kw)

    evs = [
        ev(_STARTING_XI, team=dict(name="X"),
           tactics=dict(lineup=[dict(player=dict(name="A")), dict(player=dict(name="B"))])),
        ev(_STARTING_XI, team=dict(name="Y"),
           tactics=dict(lineup=[dict(player=dict(name="D"))])),
        ev(3, team=dict(name="X"), player=dict(name="A"), minute=10),           # dispossessed
        ev(_SUBSTITUTION, team=dict(name="X"), player=dict(name="B"), minute=60,
           period=2, substitution=dict(replacement=dict(name="C"))),
        ev(38, team=dict(name="X"), player=dict(name="C"), minute=70, period=2),  # miscontrol
        ev(38, team=dict(name="X"), player=dict(name="C"), minute=80, period=2),
        ev(38, team=dict(name="Y"), minute=81, period=2),                       # no player -> dropped
        ev(30, team=dict(name="Y"), player=dict(name="D"), minute=93, period=2),  # last whistle-ish
    ]
    lu = tidy_lineups(evs, "m1")
    assert list(lu.columns) == ["game_id", "team", "player", "is_starter", "minutes"]
    r = lu.set_index("player")
    assert r.loc["A"].minutes == 94 and r.loc["A"].is_starter          # 93 + 1
    assert r.loc["B"].minutes == 60 and r.loc["B"].is_starter
    assert r.loc["C"].minutes == 34 and not r.loc["C"].is_starter      # 94 - 60
    assert r.loc["D"].team == "Y"

    to = tidy_turnovers(evs, "m1")
    assert len(to) == 3, "player-less event dropped"
    assert to.event.value_counts().to_dict() == {"miscontrol": 2, "dispossessed": 1}

    lu2, to2 = lu.assign(league="L", season="2015-2016"), to.assign(league="L", season="2015-2016")
    ps = player_season(lu2, to2).set_index("player")
    assert ps.loc["C"].miscontrol == 2 and np.isclose(ps.loc["C"].miscontrol_p90, 2 / 34 * 90)
    assert ps.loc["A"].dispossessed == 1 and ps.loc["D"].turnovers_p90 == 0
    ts = team_season(lu2, to2)
    assert ts.set_index("team").loc["X"].dispossessed == 1
    assert ts.set_index("team").loc["X"].miscontrol == 2

    # competitions filter keeps only Big-5 leagues
    cov = big5_league_seasons([
        dict(competition_id=2, season_id=27, season_name="2015/2016"),
        dict(competition_id=43, season_id=3, season_name="2018"),     # World Cup -> dropped
    ])
    assert len(cov) == 1 and cov.iloc[0].league == "ENG-Premier League"
    assert cov.iloc[0].season == "2015-2016"

    # tidy lineups plug straight into wowy's schema
    from impact import wowy  # noqa: F401
    assert {"game_id", "team", "player", "is_starter", "minutes"} == set(lu.columns)

    print(lu.to_string(index=False))
    print(ps.reset_index()[["player", "minutes", "dispossessed", "miscontrol", "turnovers_p90"]]
          .to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        # optional args like "2:27" build ONLY those league-seasons
        picked = [tuple(map(int, a.split(":"))) for a in sys.argv[1:] if ":" in a]
        build(tuple(picked) or tuple(DEFAULT_SEASONS))
    else:
        _check()
