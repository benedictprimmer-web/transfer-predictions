"""FBref via soccerdata: thin cached wrapper + tidy layer.

RUN THIS ON YOUR OWN MACHINE. FBref (Cloudflare) 403s datacenter / sandbox IPs
within seconds — DATA.md says so and it is true, verified 2026-07. soccerdata
caches to ~/soccerdata, so the network cost is paid once.

The tidy_* functions are pure (no network) and map soccerdata 1.8.8 output to
the schema wowy.py already consumes:
    lineup -> game_id, team, player, is_starter, minutes
    shots  -> game_id, team_shot, minute, xg
so `wowy.wowy(read_lineup(...), read_shots(...))` just works.

Column names move between soccerdata versions (DATA.md's "breaks exactly once").
The tidy layer is written against 1.8.8's source and is defensive about the
handful of columns that drift. If a real pull raises a KeyError here, print the
raw .columns and fix the picker below — this is the only place it can break.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

# --- scope: SPEC §3 "top 5 + selling leagues", 10 seasons -------------------
SEASONS = [f"{y}-{y+1}" for y in range(2015, 2025)]  # 2015-2016 .. 2024-2025

BIG5 = [
    "ENG-Premier League", "ESP-La Liga", "ITA-Serie A",
    "GER-Bundesliga", "FRA-Ligue 1",
]
# soccerdata ships only Big-5 for FBref. These need a custom league_dict.json
# (see ensure_league_dict). FBref comp names are best-effort; confirm on the
# first real pull and correct here if read_seasons can't find one.
SELLING = ["ENG-Championship", "NED-Eredivisie", "POR-Primeira Liga",
           "MEX-Liga MX", "BRA-Serie A"]
ALL_LEAGUES = BIG5 + SELLING

# Merged into ~/soccerdata/config/league_dict.json by ensure_league_dict().
# Only the FBref key matters for this project; other sources left out on purpose.
SELLING_LEAGUE_DICT = {
    "ENG-Championship":  {"FBref": "Championship",   "season_start": "Aug", "season_end": "May"},
    "NED-Eredivisie":    {"FBref": "Eredivisie",     "season_start": "Aug", "season_end": "May"},
    "POR-Primeira Liga": {"FBref": "Primeira Liga",  "season_start": "Aug", "season_end": "May"},
    # single-year calendars — Liga MX is split Apertura/Clausura, Brazil is Apr-Dec.
    "MEX-Liga MX":       {"FBref": "Liga MX",        "season_code": "single-year"},
    "BRA-Serie A":       {"FBref": "Serie A",        "season_code": "single-year"},
}


def ensure_league_dict(config_dir: str | None = None) -> Path:
    """Merge SELLING_LEAGUE_DICT into soccerdata's custom league_dict.json.

    soccerdata reads ~/soccerdata/config/league_dict.json at import and merges
    it over its built-in dict (_config.py). Idempotent; never clobbers entries
    you already added by hand.
    """
    cfg = Path(config_dir) if config_dir else Path.home() / "soccerdata" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    f = cfg / "league_dict.json"
    existing = json.loads(f.read_text()) if f.is_file() else {}
    merged = {**SELLING_LEAGUE_DICT, **existing}  # hand edits win
    f.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    return f


def client(leagues, seasons=SEASONS):
    """Construct the soccerdata FBref reader. Import is local so the tidy layer
    and _check() work without soccerdata installed."""
    import soccerdata as sd
    return sd.FBref(leagues=leagues, seasons=seasons)


# --- tidy layer (pure, offline-testable) ------------------------------------
def _pick(df: pd.DataFrame, *candidates: str) -> str:
    """First column matching any candidate (exact, then case-insensitive)."""
    for c in candidates:
        if c in df.columns:
            return c
    low = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in low:
            return low[c.lower()]
    raise KeyError(f"none of {candidates} in {list(df.columns)}")


def _minute(series: pd.Series) -> pd.Series:
    """'45+2' -> 45, '90' -> 90, 90 -> 90. Stoppage time folded into the base
    minute; good enough for on/off-pitch windowing (wowy uses [on, off))."""
    s = series.astype(str).str.extract(r"(\d+)", expand=False)
    return pd.to_numeric(s, errors="coerce")


def tidy_lineup(raw: pd.DataFrame) -> pd.DataFrame:
    """soccerdata read_lineup().reset_index() -> wowy lineup schema."""
    d = raw.rename(columns={"minutes_played": "minutes"})
    gid = _pick(d, "game", "game_id")
    out = pd.DataFrame({
        "game_id": d[gid],
        "team": d[_pick(d, "team")],
        "player": d[_pick(d, "player")],
        "is_starter": d[_pick(d, "is_starter")].astype(bool),
        "minutes": pd.to_numeric(d[_pick(d, "minutes")], errors="coerce").fillna(0),
    })
    return out[out.minutes > 0].reset_index(drop=True)


def tidy_shots(raw: pd.DataFrame) -> pd.DataFrame:
    """soccerdata read_shot_events().reset_index() -> wowy shots schema."""
    d = raw
    gid = _pick(d, "game", "game_id")
    out = pd.DataFrame({
        "game_id": d[gid],
        "team_shot": d[_pick(d, "team", "squad")],
        "minute": _minute(d[_pick(d, "minute")]),
        "xg": pd.to_numeric(d[_pick(d, "xg", "xG")], errors="coerce"),
    })
    return out.dropna(subset=["xg", "minute"]).reset_index(drop=True)


def read_lineup(leagues, seasons=SEASONS, **kw) -> pd.DataFrame:
    return tidy_lineup(client(leagues, seasons).read_lineup(**kw).reset_index())


def read_shots(leagues, seasons=SEASONS, **kw) -> pd.DataFrame:
    return tidy_shots(client(leagues, seasons).read_shot_events(**kw).reset_index())


def read_schedule(leagues, seasons=SEASONS, **kw) -> pd.DataFrame:
    return client(leagues, seasons).read_schedule(**kw).reset_index()


def _check():
    # synthetic soccerdata-shaped frames -> assert tidy schema, no network.
    lu_raw = pd.DataFrame([
        dict(league="ENG-Premier League", season="2324", game="g1",
             player="A", team="X", is_starter=True, minutes_played=90, position="FW"),
        dict(league="ENG-Premier League", season="2324", game="g1",
             player="B", team="X", is_starter=False, minutes_played=0, position="MF"),
    ])
    lu = tidy_lineup(lu_raw)
    assert list(lu.columns) == ["game_id", "team", "player", "is_starter", "minutes"]
    assert len(lu) == 1 and lu.iloc[0].player == "A", "0-minute sub dropped"

    sh_raw = pd.DataFrame([
        dict(league="ENG-Premier League", season="2324", game="g1",
             minute="45+2", player="A", team="X", xg=0.3),
        dict(game="g1", minute="90", player="C", team="Y", xg=np.nan),  # no xg -> dropped
    ])
    sh = tidy_shots(sh_raw)
    assert list(sh.columns) == ["game_id", "team_shot", "minute", "xg"]
    assert len(sh) == 1 and sh.iloc[0].minute == 45, "stoppage folded to base minute"

    # ensure_league_dict is idempotent and preserves hand edits
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        f = ensure_league_dict(tmp)
        (Path(tmp) / "league_dict.json").write_text(json.dumps(
            {**json.loads(f.read_text()), "MY-League": {"FBref": "x"}}))
        f = ensure_league_dict(tmp)
        j = json.loads(f.read_text())
        assert "MY-League" in j and "ENG-Championship" in j, "merge kept both"

    print(lu.to_string(index=False))
    print(sh.to_string(index=False))
    print(f"seasons: {SEASONS[0]}..{SEASONS[-1]} ({len(SEASONS)}); "
          f"leagues: {len(ALL_LEAGUES)} ({len(BIG5)} native + {len(SELLING)} custom)")
    print("ok")


if __name__ == "__main__":
    _check()
