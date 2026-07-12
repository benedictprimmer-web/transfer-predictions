"""Understat shots — the xG engine, via the worldfootballR_data static dump.

Replaces FBref for advanced data. FBref lost xG/shot data in Jan 2025 (Opta
pulled the feed) AND 403s datacenter IPs; Understat's dump is neither. Big-5 +
RFPL, 2014/15 onward. See DATA_SOURCES.md.

Static .rds files on GitHub (raw), read with `rdata` (pure-Python, no compile).
Verified reachable + parseable from this environment 2026-07-11 (EPL = 102,257
shots). Files cache to data/understat/.

Tidy output feeds impact/wowy.py's shots schema (game_id, team_shot, minute, xg)
and carries the extra columns (player, player_assisted, season) that stage 2's
usage/efficiency needs.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "understat"
_RAW = "https://raw.githubusercontent.com/JaseZiv/worldfootballR_data/master/data/understat_shots/{}"

# league key -> dump filename. Big-5 + Russian PL (the whole Understat corpus).
LEAGUE_FILES = {
    "ENG-Premier League": "epl_shot_data.rds",
    "ESP-La Liga":        "la_liga_shot_data.rds",
    "ITA-Serie A":        "serie_a_shot_data.rds",
    "GER-Bundesliga":     "bundesliga_shot_data.rds",
    "FRA-Ligue 1":        "ligue_1_shot_data.rds",
    "RUS-Premier League": "rfpl_shot_data.rds",
}


def download(leagues=tuple(LEAGUE_FILES), force=False) -> list[Path]:
    """Fetch missing .rds dumps into data/understat/. Idempotent."""
    import urllib.request
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for lg in leagues:
        fn = LEAGUE_FILES[lg]
        dest = DATA_DIR / fn
        if force or not dest.exists():
            urllib.request.urlretrieve(_RAW.format(fn), dest)
        out.append(dest)
    return out


def _season(start_year) -> str:
    """Understat season is the start year (2014 -> '2014-2015')."""
    y = int(start_year)
    return f"{y}-{y + 1}"


def _fix_mojibake(s):
    """The .rds mixes UTF-8 and Latin-1 CHARSXPs; we read them all as latin-1
    (lossless), then re-interpret the UTF-8-origin ones. 'Ã©'->'é', genuine
    'é' left alone. Makes accented names join-safe."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def tidy_shots(raw: pd.DataFrame, league: str) -> pd.DataFrame:
    """Understat rds frame -> shot schema for wowy + usage.

    team_shot is derived from the home/away flag against home_team/away_team.
    The upstream dump renamed that column h_a -> home_away from season 2022
    (h_a is None for 2022+ rows, home_away None before), so coalesce both.
    """
    d = raw
    home = d["home_team"].astype(str).map(_fix_mojibake)
    away = d["away_team"].astype(str).map(_fix_mojibake)
    ha = None
    for col in ("h_a", "home_away"):
        if col in d.columns:
            ha = d[col] if ha is None else ha.fillna(d[col])
    if ha is None:
        raise KeyError("shots dump has neither 'h_a' nor 'home_away'")
    is_home = ha.astype(str).str.lower().eq("h")
    # optional source cols — present in every current dump, guarded for safety
    def _opt(col):
        return d[col] if col in d.columns else pd.Series([None] * len(d), index=d.index)
    out = pd.DataFrame({
        "league": league,
        "season": d["season"].map(_season),
        "game_id": d["match_id"].astype(float).astype("Int64").astype(str),
        "team_shot": np.where(is_home, home, away),
        "home_team": home,
        "away_team": away,
        "minute": pd.to_numeric(d["minute"], errors="coerce"),
        "xg": pd.to_numeric(d["xG"], errors="coerce"),
        "player": d["player"].astype(str).map(_fix_mojibake),
        "player_assisted": d["player_assisted"].map(_fix_mojibake),  # shot-assist: who set it up
        "result": d["result"].astype(str),
        "situation": d["situation"].astype(str),  # OpenPlay/Penalty/... — npxG needs it
        "date": pd.to_datetime(d["date"], errors="coerce").dt.date.astype(str),
        # appended (never reorder the first 13 — callers assert on the prefix):
        "player_id": pd.to_numeric(_opt("player_id"), errors="coerce").astype("Int64"),  # clean Understat join key — kills name-matching
        "x": pd.to_numeric(_opt("X"), errors="coerce"),  # 0..1 normalised pitch coords
        "y": pd.to_numeric(_opt("Y"), errors="coerce"),  # -> distance/angle shot-quality features
        "shot_type": _opt("shotType").astype("object"),  # RightFoot/LeftFoot/Head/Other
        "last_action": _opt("lastAction").astype("object"),  # build-up context (Pass/Cross/Rebound/...)
    })
    return out.dropna(subset=["xg", "minute"]).reset_index(drop=True)


def read_shots(leagues=tuple(LEAGUE_FILES), cache=True) -> pd.DataFrame:
    """Download (if needed) + tidy all requested leagues into one shots frame.

    rdata's pure-python .rds parse takes minutes, so the tidy frame is cached
    once to data/understat/shots.parquet and reloaded in ~1s thereafter. Parquet
    (not pickle) so the cache survives a numpy/pandas bump and DuckDB can read it.
    """
    pq = DATA_DIR / "shots.parquet"
    if cache and pq.exists() and set(leagues) == set(LEAGUE_FILES):
        return pd.read_parquet(pq)
    import rdata
    download(leagues)
    frames = []
    for lg in leagues:
        # some CHARSXPs carry no encoding flag; force UTF-8 or accented names
        # (La Liga, Serie A, ...) hit rdata's ascii fallback and raise.
        raw = rdata.read_rds(str(DATA_DIR / LEAGUE_FILES[lg]),
                             default_encoding="latin-1", force_default_encoding=True)
        frames.append(tidy_shots(raw, lg))
    out = pd.concat(frames, ignore_index=True)
    if cache and set(leagues) == set(LEAGUE_FILES):
        out.to_parquet(pq, index=False)     # self-writing cache; no orphan pickle
    return out


def coverage(shots: pd.DataFrame) -> pd.DataFrame:
    """Real xG/shot-minute coverage per league-season from the shots frame.
    (Lineup-minutes coverage comes from the Transfermarkt appearances table —
    a separate source; see DATA_SOURCES.md.)"""
    g = shots.groupby(["league", "season"], sort=True)
    cov = g.agg(
        n_shots=("xg", "size"),
        n_matches=("game_id", "nunique"),
        n_players=("player", "nunique"),
        total_xg=("xg", "sum"),
    ).reset_index()
    cov["shots_per_match"] = (cov.n_shots / cov.n_matches).round(1)
    cov["has_xg"] = cov.total_xg > 0        # Understat rows ARE xG by definition
    cov["has_shot_minutes"] = True
    return cov.drop(columns="total_xg")


def _check():
    # synthetic rds-shaped frame -> tidy -> coverage, no network.
    raw = pd.DataFrame([
        dict(match_id=1.0, h_a="h", home_team="Arsenal", away_team="Spurs",
             minute=10, xG=0.3, player="Saka", player_assisted="Odegaard",
             result="Goal", situation="OpenPlay", date="2023-09-24 14:00:00", season=2023),
        dict(match_id=1.0, h_a="a", home_team="Arsenal", away_team="Spurs",
             minute=80, xG=0.1, player="Son", player_assisted=None,
             result="MissedShots", situation="Penalty", date="2023-09-24 14:00:00", season=2023),
        dict(match_id=1.0, h_a="h", home_team="Arsenal", away_team="Spurs",
             minute=90, xG=np.nan, player="X", player_assisted=None,  # no xg -> dropped
             result="BlockedShot", situation="OpenPlay", date="2023-09-24 14:00:00", season=2023),
        # 2022+ rows carry home_away (h_a is None); coalesce must still tag them
        dict(match_id=2.0, home_away="h", home_team="Man City", away_team="United",
             minute=20, xG=0.5, player="Haaland", player_assisted=None,
             result="Goal", situation="OpenPlay", date="2022-09-24 14:00:00", season=2022),
        dict(match_id=2.0, home_away="a", home_team="Man City", away_team="United",
             minute=70, xG=0.2, player="Rashford", player_assisted=None,
             result="MissedShots", situation="OpenPlay", date="2022-09-24 14:00:00", season=2022),
    ])
    sh = tidy_shots(raw, "ENG-Premier League")
    assert list(sh.columns)[:4] == ["league", "season", "game_id", "team_shot"]
    assert len(sh) == 4, "NaN-xg shot dropped"
    assert sh.iloc[0].team_shot == "Arsenal" and sh.iloc[1].team_shot == "Spurs"
    assert sh.iloc[0].season == "2023-2024"
    # home_away coalesce: 2022 rows tagged to the right side, not defaulted away
    assert sh.iloc[2].team_shot == "Man City" and sh.iloc[3].team_shot == "United"

    cov = coverage(sh)
    row = cov.iloc[0]
    assert row.n_matches == 1 and row.n_shots == 2 and row.has_xg
    assert row.n_players == 2

    # tidy output plugs into wowy's shots schema
    from impact import wowy  # noqa: F401 — import proves the columns line up
    assert {"game_id", "team_shot", "minute", "xg"}.issubset(sh.columns)

    print(sh.to_string(index=False))
    print(cov.to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        shots = read_shots()
        cov = coverage(shots)
        out = Path(__file__).resolve().parent.parent / "data" / "coverage.csv"
        cov.to_csv(out, index=False)
        print(cov.to_string(index=False))
        print(f"\n{len(shots):,} shots; wrote {out}")
    else:
        _check()
