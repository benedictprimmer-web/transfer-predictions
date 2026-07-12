"""FBref advanced-stats SNAPSHOT via worldfootballR_data — turnovers + 90s.

FBref removed all Opta advanced data in Jan 2025, but worldfootballR_data
froze the Big-5 per-player season tables before the takedown. The possession
table carries the two usage components nothing else provides at this
coverage: Dispossessed and Miscontrols, per player-season, 2017-18→2022-23.

That window includes Man Utd 2021-22 (the stage-2 gate) and Arsenal's recent
seasons. Outside it, usage falls back to attacking actions only, flagged.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "fbref_snapshot"
_RAW = ("https://raw.githubusercontent.com/JaseZiv/worldfootballR_data/master/"
        "data/fb_big5_advanced_season_stats/{}")

COMP_TO_LEAGUE = {
    "Premier League": "ENG-Premier League",
    "La Liga": "ESP-La Liga",
    "Serie A": "ITA-Serie A",
    "Bundesliga": "GER-Bundesliga",
    "Ligue 1": "FRA-Ligue 1",
}
# FBref squad spellings that differ from Understat's
TEAM_ALIASES = {
    "Manchester Utd": "Manchester United",
    "Newcastle Utd": "Newcastle United",
    "Sheffield Utd": "Sheffield United",
    "Wolves": "Wolverhampton Wanderers",
    "West Ham": "West Ham United",
    "Brighton": "Brighton and Hove Albion",   # ponytail: extend as joins demand
    "Nott'ham Forest": "Nottingham Forest",
    "Tottenham": "Tottenham Hotspur",
    "Leicester City": "Leicester",
    "Leeds United": "Leeds",
    "Norwich City": "Norwich",
}


def download(name="big5_player_possession.rds", force=False) -> Path:
    import urllib.request
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / name
    if force or not dest.exists():
        urllib.request.urlretrieve(_RAW.format(name), dest)
    return dest


def tidy_turnovers(raw: pd.DataFrame) -> pd.DataFrame:
    """possession table -> league, season, team, player, n90s, dispossessed,
    miscontrols. Season_End_Year 2022 == season '2021-2022'."""
    d = raw
    out = pd.DataFrame({
        "league": d["Comp"].map(COMP_TO_LEAGUE),
        "season": d["Season_End_Year"].astype(int).map(lambda y: f"{y-1}-{y}"),
        "team": d["Squad"].astype(str).replace(TEAM_ALIASES),
        "player": d["Player"].astype(str),
        "pos": d["Pos"].astype(str),   # e.g. 'FW', 'FW,MF' — role overlap needs it
        "n90s": pd.to_numeric(d["Mins_Per_90"], errors="coerce"),
        "dispossessed": pd.to_numeric(d["Dis_Carries"], errors="coerce").fillna(0),
        "miscontrols": pd.to_numeric(d["Mis_Carries"], errors="coerce").fillna(0),
    })
    out["turnovers"] = out.dispossessed + out.miscontrols
    return out.dropna(subset=["league", "n90s"]).reset_index(drop=True)


def read_turnovers() -> pd.DataFrame:
    import rdata
    raw = rdata.read_rds(str(download()),
                         default_encoding="latin-1", force_default_encoding=True)
    return tidy_turnovers(raw)


def _check():
    raw = pd.DataFrame([
        dict(Season_End_Year=2022, Comp="Premier League", Squad="Manchester Utd",
             Player="Cristiano Ronaldo", Pos="FW", Mins_Per_90=30.0,
             Dis_Carries=40, Mis_Carries=50),
        dict(Season_End_Year=2022, Comp="Premier League", Squad="Manchester Utd",
             Player="Bruno Fernandes", Pos="MF", Mins_Per_90=35.0,
             Dis_Carries=60, Mis_Carries=55),
        dict(Season_End_Year=2018, Comp="La Liga", Squad="Barcelona",
             Player="Lionel Messi", Pos="FW", Mins_Per_90=34.0,
             Dis_Carries=80, Mis_Carries=40),
    ])
    t = tidy_turnovers(raw)
    assert list(t.columns) == ["league", "season", "team", "player", "pos",
                               "n90s", "dispossessed", "miscontrols", "turnovers"]
    r = t.set_index("player")
    assert r.loc["Cristiano Ronaldo"].season == "2021-2022"
    assert r.loc["Cristiano Ronaldo"].team == "Manchester United", "alias applied"
    assert r.loc["Cristiano Ronaldo"].turnovers == 90
    assert r.loc["Lionel Messi"].league == "ESP-La Liga"
    print(t.to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        t = read_turnovers()
        print(t.groupby(["league", "season"]).agg(
            players=("player", "nunique"), turnovers=("turnovers", "sum")).to_string())
        print(f"{len(t):,} player-season rows")
    else:
        _check()
