"""Crosswalk: Understat <-> Transfermarkt match ids + name normalizers.

The lynchpin join. Understat shots (xG) and Transfermarkt minutes use
different match ids and club spellings; WOWY needs both on one game key.

Match identity on the Understat side is (league, season, home, away) —
unique in a double round-robin league — because the tidy shots frame
carries no date. TM side comes from data/transfermarkt/games.csv.gz
(domestic_league rows, Big-5).

Club names are matched per league, data-driven, in four passes:
  exact  - identical after norm_team()
  alias  - hand ALIASES entry, or one side's token set contained in the
           other's (unique among still-unclaimed names)
  fuzzy  - difflib best match >= 0.75, unique among unclaimed
Exact matches claim first and leave the pools, so "Inter" can't collide
with "AC Milan" over TM's "Inter Milan".

Output: data/crosswalk/matches.csv with
  understat_game_id, tm_game_id, league, season, home, away, match_confidence
(home/away are the Understat spellings; confidence is the worst of the
two team mappings).
"""
from __future__ import annotations

import difflib
import html
import re
import unicodedata
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "crosswalk"

# tokens that carry no club identity once case/punctuation is gone.
# 1-2 char tokens and pure digits are dropped unconditionally (FC, AC, 04...).
_NOISE = {
    "afc", "cfc", "ssc", "rcd", "sco", "bsc", "hsc", "fco", "losc", "ogc",
    "vfl", "vfb", "fsv", "tsg", "spvgg", "estac",
    "club", "calcio", "football", "fussballclub", "fusballclub",
    "associazione", "sportiva", "societa",
}

# normalized Understat spelling -> normalized TM spelling, per stragglers the
# data-driven passes can't bridge. Keyed on norm_team() of both sides.
ALIASES = {
    "cologne": "koln",                              # FC Cologne / 1.FC Köln
    "rasenballsport leipzig": "leipzig",            # RB Leipzig ('rb' token dropped)
    "evian thonon gaillard": "thonon evian grand geneve",
    "psg": "paris saint germain",
    "spal 2013": "spal",
    "athletic club": "athletic bilbao",
    "wolves": "wolverhampton wanderers",
    "rennes": "stade rennais",                      # Stade Rennais FC
    "brest": "stade brestois",                      # Stade Brestois 29
}


def _strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def norm_team(name: str) -> str:
    """Casefold, de-accent, drop punctuation + org-suffix noise tokens."""
    s = _strip_diacritics(str(name)).casefold()
    toks = re.sub(r"[^a-z0-9]+", " ", s).split()
    keep = [t for t in toks
            if len(t) > 2 and not t.isdigit() and t not in _NOISE]
    return " ".join(keep) or " ".join(toks)  # never normalize to empty


def norm_player(name: str) -> str:
    """De-accent, casefold, punctuation->space. 'N. Kanté' -> 'n kante'.

    Understat names carry literal HTML entities (e.g. "N&#039;Golo Kanté");
    unescape (up to twice, for double-encoded cases) before stripping.
    """
    s = html.unescape(html.unescape(str(name)))
    s = _strip_diacritics(s).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


_CONF = {"exact": 0, "alias": 1, "fuzzy": 2}


def team_map(us_names, tm_names) -> dict:
    """Map Understat club names to TM club names (one league at a time).

    Returns {us_name: (tm_name, confidence)}; unmatched names are absent.
    Understat spellings that share a normalized form ('Parma' and
    'Parma Calcio 1913') all map to the same TM club.
    """
    us = {}  # normalized -> [original spellings]
    for n in dict.fromkeys(us_names):
        us.setdefault(norm_team(n), []).append(n)
    tm_pool = {}  # normalized -> original, unclaimed
    for n in dict.fromkeys(tm_names):
        tm_pool.setdefault(norm_team(n), n)

    out = {}

    def claim(us_norm, tm_norm, conf):
        tm_name = tm_pool.pop(tm_norm)
        for spelling in us.pop(us_norm):
            out[spelling] = (tm_name, conf)

    # pass 1: exact normalized match
    for n in list(us):
        if n in tm_pool:
            claim(n, n, "exact")

    # pass 2: hand aliases
    for n in list(us):
        a = ALIASES.get(n)
        if a and a in tm_pool:
            claim(n, a, "alias")

    # pass 3: token-set containment, unique among unclaimed
    for n in list(us):
        st = set(n.split())
        hits = [t for t in tm_pool if st <= set(t.split()) or set(t.split()) <= st]
        if len(hits) == 1:
            claim(n, hits[0], "alias")

    # pass 4: difflib, unique best match among unclaimed
    for n in list(us):
        hits = difflib.get_close_matches(n, tm_pool, n=2, cutoff=0.75)
        if len(hits) == 1 or (len(hits) > 1 and
                              difflib.SequenceMatcher(None, n, hits[0]).ratio()
                              - difflib.SequenceMatcher(None, n, hits[1]).ratio() > 0.1):
            claim(n, hits[0], "fuzzy")

    return out


def crosswalk(us_matches: pd.DataFrame, tm_games: pd.DataFrame) -> pd.DataFrame:
    """Join Understat matches to TM games.

    us_matches: league, season, game_id, home_team, away_team (one row/match)
    tm_games:   league, season, game_id, home_club_name, away_club_name

    Returns understat_game_id, tm_game_id, league, season, home, away,
    match_confidence — one row per matched Understat fixture.
    """
    rows = []
    for lg, us_lg in us_matches.groupby("league"):
        tm_lg = tm_games[tm_games.league == lg]
        names = team_map(pd.concat([us_lg.home_team, us_lg.away_team]).unique(),
                         pd.concat([tm_lg.home_club_name, tm_lg.away_club_name]).unique())
        tm_key = tm_lg.set_index(
            ["season", "home_club_name", "away_club_name"]).game_id
        for r in us_lg.itertuples():
            h, a = names.get(r.home_team), names.get(r.away_team)
            if h is None or a is None:
                continue
            tm_id = tm_key.get((r.season, h[0], a[0]))
            if tm_id is None:
                continue
            conf = max(h[1], a[1], key=_CONF.get)
            rows.append((r.game_id, str(tm_id), lg, r.season,
                         r.home_team, r.away_team, conf))
    return pd.DataFrame(rows, columns=[
        "understat_game_id", "tm_game_id", "league", "season",
        "home", "away", "match_confidence"])


# ------------------------------------------------------------------ build

def _us_matches(shots: pd.DataFrame) -> pd.DataFrame:
    m = (shots[["league", "season", "game_id", "home_team", "away_team"]]
         .drop_duplicates("game_id"))
    dup = m.duplicated(["league", "season", "home_team", "away_team"], keep=False)
    if dup.any():  # replayed fixture would break the identity key — surface it
        print(f"WARNING: {dup.sum()} Understat rows share a fixture key:")
        print(m[dup].to_string(index=False))
    return m


def _tm_games() -> pd.DataFrame:
    from ingest.transfermarkt import BIG5, _read, _season
    g = _read("games")
    g = g[(g.competition_type == "domestic_league") & g.competition_id.isin(BIG5)]
    return pd.DataFrame({
        "league": g.competition_id.map(BIG5),
        "season": g.season.map(_season),
        "game_id": g.game_id.astype(str),
        "home_club_name": g.home_club_name,
        "away_club_name": g.away_club_name,
        "date": g.date,
    }).dropna(subset=["home_club_name", "away_club_name"])


def build() -> pd.DataFrame:
    from ingest import understat
    shots = understat.read_shots()
    shots = shots[shots.league != "RUS-Premier League"]  # TM dump is Big-5 only
    us = _us_matches(shots)
    tm = _tm_games()
    xw = crosswalk(us, tm)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "matches.csv"
    xw.to_csv(out, index=False)

    # --- report: match rate per league-season
    denom = us.groupby(["league", "season"]).size().rename("us_matches")
    num = xw.groupby(["league", "season"]).size().rename("matched")
    rep = pd.concat([denom, num], axis=1).fillna(0).astype(int).reset_index()
    rep["rate_pct"] = (100 * rep.matched / rep.us_matches).round(2)
    print(rep.to_string(index=False))
    print(f"\nconfidence: {xw.match_confidence.value_counts().to_dict()}")

    un = us.merge(xw[["understat_game_id"]], left_on="game_id",
                  right_on="understat_game_id", how="left", indicator=True)
    un = un[un._merge == "left_only"]
    if len(un):
        print(f"\n{len(un)} unmatched Understat fixtures; first 20:")
        print(un[["league", "season", "home_team", "away_team"]]
              .head(20).to_string(index=False))
    print(f"\nwrote {out} ({len(xw):,} rows)")

    # --- player exact-normalized match rate, EPL 2021-22
    from ingest.transfermarkt import _read
    ap = _read("appearances", usecols=["player_name", "competition_id", "date"])
    ap = ap[(ap.competition_id == "GB1")
            & ap.date.between("2021-07-01", "2022-06-30")]
    tm_players = {norm_player(p) for p in ap.player_name.dropna().unique()}
    us_players = shots.loc[(shots.league == "ENG-Premier League")
                           & (shots.season == "2021-2022"), "player"].unique()
    hit = sum(norm_player(p) in tm_players for p in us_players)
    print(f"\nEPL 2021-22 players: {hit}/{len(us_players)} "
          f"({100 * hit / len(us_players):.1f}%) exact-normalized match in TM")
    return xw


# ------------------------------------------------------------------ check

def _check():
    # normalizers
    assert norm_team("Borussia Mönchengladbach") == "borussia monchengladbach"
    assert norm_team("Atlético de Madrid") == norm_team("Atletico Madrid")
    assert norm_team("1.FSV Mainz 05") == norm_team("Mainz 05") == "mainz"
    assert norm_team("Società Sportiva Lazio S.p.A.") == "lazio"
    assert norm_team("Paris Saint-Germain") == norm_team("Paris Saint Germain")
    assert norm_team("FC St. Pauli") == norm_team("St. Pauli")  # both 'pauli'
    assert norm_team("SD Eibar") == "eibar" and norm_team("US Lecce") == "lecce"
    assert norm_player("N'Golo Kanté") == "n golo kante"
    assert norm_player("Trent Alexander-Arnold") == "trent alexander arnold"

    # team_map: exact / subset-alias / hand-alias / fuzzy, Inter-Milan trap
    tm = team_map(
        ["AC Milan", "Inter", "Athletic Club", "FC Cologne",
         "Borussia M.Gladbach", "Real Betis", "Nowhere Town"],
        ["Inter Milan", "AC Milan", "Athletic Bilbao", "1.FC Köln",
         "Borussia Mönchengladbach", "Real Betis Balompié", "Elsewhere City"])
    assert tm["AC Milan"] == ("AC Milan", "exact")
    assert tm["Inter"] == ("Inter Milan", "alias")          # subset, post-exact
    assert tm["Athletic Club"] == ("Athletic Bilbao", "alias")
    assert tm["FC Cologne"] == ("1.FC Köln", "alias")       # hand alias
    assert tm["Borussia M.Gladbach"][0] == "Borussia Mönchengladbach"
    assert tm["Real Betis"] == ("Real Betis Balompié", "alias")
    assert "Nowhere Town" not in tm                          # no forced match

    # two Understat spellings of one club both land on the same TM club
    tm2 = team_map(["Parma", "Parma Calcio 1913"], ["Parma Calcio 1913"])
    assert tm2["Parma"] == tm2["Parma Calcio 1913"] == ("Parma Calcio 1913", "exact")

    # crosswalk on a synthetic league-season
    us = pd.DataFrame([
        ("ENG-Premier League", "2023-2024", "101", "Wolverhampton Wanderers", "Tottenham"),
        ("ENG-Premier League", "2023-2024", "102", "Tottenham", "Wolverhampton Wanderers"),
        ("ENG-Premier League", "2023-2024", "103", "Ghost FC", "Tottenham"),
    ], columns=["league", "season", "game_id", "home_team", "away_team"])
    tmg = pd.DataFrame([
        ("ENG-Premier League", "2023-2024", "9001", "Wolverhampton Wanderers", "Tottenham Hotspur"),
        ("ENG-Premier League", "2023-2024", "9002", "Tottenham Hotspur", "Wolverhampton Wanderers"),
    ], columns=["league", "season", "game_id", "home_club_name", "away_club_name"])
    xw = crosswalk(us, tmg)
    assert list(xw.columns) == ["understat_game_id", "tm_game_id", "league",
                                "season", "home", "away", "match_confidence"]
    assert len(xw) == 2, xw                                  # ghost fixture skipped
    assert xw.set_index("understat_game_id").tm_game_id.to_dict() == \
        {"101": "9001", "102": "9002"}
    # reversed fixture didn't cross-wire; Tottenham matched via subset -> alias
    assert set(xw.match_confidence) == {"alias"}

    print(xw.to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
