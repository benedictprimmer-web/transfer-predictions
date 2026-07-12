"""fbref_shots — selling-league shot xG, the coverage gap closed.

The find (2026-07-12 scout fan-out): worldfootballR_data caches FBref
shot-level data as static GitHub *release assets*, which are NOT IP-blocked
like FBref-live is. That gets us shot xG for the four biggest feeder leagues
Understat never covered — ~235k shots, ~100% with xG:
  Championship (ENG-2, 2019-25), Liga Portugal (2019-25),
  Brazil Série A (2019-24), Eredivisie (2019-22 + 2024-25; 2023 gap upstream).

Granularity is FBref's shooting table: xG + PSxG + Distance + Body Part +
shot-creating actions + Player_Href (→ fbref_id, so it joins straight into
players_master). NO pitch coordinates — but it already carries xG, so we use
FBref's xG directly rather than our geometry model. Feeds usage/efficiency
(and WOWY, via MatchURL opponent pairing) for these leagues, keyed to TM ids.

    python3 -m ingest.fbref_shots build     # download 4 leagues + tidy + write
    python3 -m ingest.fbref_shots           # offline self-check
"""
from __future__ import annotations
import re
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "fbref_shots"
_REL = ("https://github.com/JaseZiv/worldfootballR_data/releases/download/"
        "fb_match_shooting/{asset}")

# our league key, release asset, calendar-year? (Brazil runs Feb-Dec)
LEAGUES = {
    "ENG-Championship":   ("ENG_M_2nd_match_shooting.rds", False),
    "POR-Primeira Liga":  ("POR_M_1st_match_shooting.rds", False),
    "NED-Eredivisie":     ("NED_M_1st_match_shooting.rds", False),
    "BRA-Serie A":        ("BRA_M_1st_match_shooting.rds", True),
}

# penalty xG is a fixed ~0.79 from the spot (~12yd). FBref drops the pen flag
# in this extract, so we detect it to keep an npxG basis (as Understat does).
# ponytail: heuristic (xG>=0.7 & dist<=13); upgrade path = the pen flag if a
# future dump restores it. Costs at most a handful of mislabeled long-range screamers.
def _is_penalty(xg, dist):
    return (xg >= 0.70) & (dist <= 13)


def _season_label(end_year, calendar_year: bool):
    y = pd.to_numeric(end_year, errors="coerce").astype("Int64")
    if calendar_year:
        return y.astype(str)                      # Brazil: "2024"
    return (y - 1).astype(str) + "-" + y.astype(str)  # "2023-2024"


def _fbref_id(href):
    m = re.search(r"/players/([0-9a-f]+)/", str(href))
    return m.group(1) if m else None


def tidy_shots(raw: pd.DataFrame, league: str, calendar_year: bool) -> pd.DataFrame:
    d = raw.copy()
    d.columns = [str(c) for c in d.columns]
    xg = pd.to_numeric(d["xG"], errors="coerce")
    dist = pd.to_numeric(d["Distance"], errors="coerce")
    notes = d.get("Notes", pd.Series("", index=d.index)).astype(str)
    out = pd.DataFrame({
        "league": league,
        "season": _season_label(d["Season_End_Year"], calendar_year),
        "match_id": d["MatchURL"].astype(str),
        "team_shot": d["Squad"].astype(str),
        "home_away": d["Home_Away"].astype(str),
        "minute": pd.to_numeric(d["Minute"].astype(str).str.extract(r"(\d+)")[0], errors="coerce"),
        "xg": xg,
        "psxg": pd.to_numeric(d["PSxG"], errors="coerce"),
        "result": np.where(d["Outcome"].astype(str) == "Goal", "Goal", d["Outcome"].astype(str)),
        "is_goal": d["Outcome"].astype(str).eq("Goal"),
        "distance": dist,
        "body_part": d["Body Part"].astype(str),
        "is_penalty": _is_penalty(xg, dist).fillna(False),
        "is_freekick": notes.str.contains("Free kick", case=False, na=False),
        "player": d["Player"].astype(str),
        "fbref_id": d["Player_Href"].map(_fbref_id),
    })
    return out.dropna(subset=["xg", "minute"]).reset_index(drop=True)


def _pair_opponents(shots: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct home_team/away_team/opponent per match from the 2 squads
    sharing a MatchURL (WOWY needs both sides). Single-squad matches -> NaN."""
    sides = (shots[["match_id", "team_shot", "home_away"]].drop_duplicates())
    home = sides[sides.home_away == "Home"].set_index("match_id").team_shot
    away = sides[sides.home_away == "Away"].set_index("match_id").team_shot
    shots = shots.copy()
    shots["home_team"] = shots.match_id.map(home)
    shots["away_team"] = shots.match_id.map(away)
    shots["opponent"] = np.where(shots.home_away == "Home",
                                 shots.away_team, shots.home_team)
    return shots


def download(force=False) -> list[Path]:
    import urllib.request
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for league, (asset, _cal) in LEAGUES.items():
        dest = DATA_DIR / asset
        if force or not dest.exists():
            urllib.request.urlretrieve(_REL.format(asset=asset), dest)
        paths.append(dest)
    return paths


def read_shots() -> pd.DataFrame:
    import rdata
    from ingest.understat import _fix_mojibake
    frames = []
    for league, (asset, cal) in LEAGUES.items():
        # some CHARSXPs carry no encoding flag -> force latin-1 (lossless), as
        # in ingest/understat.py, else accented names (Léo, Série) hit rdata's
        # ascii fallback and raise UnicodeDecodeError.
        raw = rdata.read_rds(str(DATA_DIR / asset),
                             default_encoding="latin-1", force_default_encoding=True)
        raw = raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
        d = tidy_shots(raw, league, cal)
        for col in ("team_shot", "player"):
            d[col] = d[col].map(_fix_mojibake)
        frames.append(d)
    shots = pd.concat(frames, ignore_index=True)
    return _pair_opponents(shots)  # derives home/away/opponent off the fixed team_shot


def build() -> pd.DataFrame:
    download()
    shots = read_shots()
    # attach TM id via the fbref bridge in players_master
    from ingest import players_master
    m = players_master.load()
    bridge = m[m.has_fbref][["fbref_id", "tm_player_id"]].drop_duplicates("fbref_id") \
        if "has_fbref" in m.columns else m[["fbref_id", "tm_player_id"]].dropna()
    shots = shots.merge(bridge, on="fbref_id", how="left")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "shots_selling.parquet"
    shots.to_parquet(out, index=False)

    print("=" * 60)
    print("SELLING-LEAGUE SHOTS  (FBref xG via release assets)")
    print("=" * 60)
    cov = shots.groupby("league").agg(
        shots=("xg", "size"), seasons=("season", "nunique"),
        players=("fbref_id", "nunique"),
        pct_tm=("tm_player_id", lambda s: round(100 * s.notna().mean(), 1)),
        goals=("is_goal", "sum"), pens=("is_penalty", "sum"),
    )
    print(cov.to_string())
    print(f"\n  total shots {len(shots):,}  |  with xG 100%  |  "
          f"TM-linked {100*shots.tm_player_id.notna().mean():.1f}%  "
          f"|  opponent paired {100*shots.opponent.notna().mean():.1f}%")
    print(f"  season span: {sorted(shots.season.unique())}")
    print(f"wrote {out}")
    return shots


# ------------------------------------------------------------------ check

def _check():
    # 2-squad match: pairing, season label (league vs calendar), pen flag, fbref id
    raw = pd.DataFrame([
        dict(MatchURL="/m1", Date="2024-05-01", Squad="Benfica", Home_Away="Home",
             Minute="10", Player="A", Player_Href="/en/players/abcd1234/A", xG="0.5",
             PSxG="0.4", Outcome="Goal", Distance="8", **{"Body Part": "Right Foot"},
             Notes="", Season_End_Year="2024"),
        dict(MatchURL="/m1", Date="2024-05-01", Squad="Porto", Home_Away="Away",
             Minute="90+2", Player="B", Player_Href="/en/players/ef567890/B", xG="0.79",
             PSxG="", Outcome="Saved", Distance="12", **{"Body Part": "Left Foot"},
             Notes="", Season_End_Year="2024"),
        dict(MatchURL="/m1", Date="2024-05-01", Squad="Porto", Home_Away="Away",
             Minute="55", Player="B", Player_Href="/en/players/ef567890/B", xG=None,  # no xg -> dropped
             PSxG="", Outcome="Off Target", Distance="30", **{"Body Part": "Head"},
             Notes="", Season_End_Year="2024"),
    ])
    s = _pair_opponents(tidy_shots(raw, "POR-Primeira Liga", False))
    assert len(s) == 2, "null-xG shot dropped"
    r = s.set_index("player")
    assert r.loc["A"].season == "2023-2024", "league season label"
    assert r.loc["A"].minute == 10 and r.loc["B"].minute == 90  # stoppage parsed
    assert r.loc["A"].home_team == "Benfica" and r.loc["A"].opponent == "Porto"
    assert r.loc["B"].opponent == "Benfica"
    assert r.loc["A"].fbref_id == "abcd1234"
    assert bool(r.loc["B"].is_penalty) and not bool(r.loc["A"].is_penalty)  # 0.79@12yd vs 0.5@8yd

    # Brazil calendar-year label
    braw = raw.assign(Season_End_Year="2024")
    sb = tidy_shots(braw, "BRA-Serie A", True)
    assert (sb.season == "2024").all(), "Brazil = calendar-year label"
    print(s[["player", "team_shot", "opponent", "season", "xg", "is_penalty", "fbref_id"]].to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
