"""Injuries — durability / availability per player, from Transfermarkt injury spells.

Source: salimt/football-datasets `player_injuries.csv` (143k spells, 18.5k players,
CC-committed GitHub dump, keyed to the SAME Transfermarkt player_id the rest of the
stack uses — no crosswalk needed). Complements the money side: `contracts.py` gives
years-left for amortisation, this gives an availability discount for the benefit side.

This closes a real NPV gap: a player who misses 60 days a season delivers less of the
modelled per-season benefit than his on-pitch rate implies. `availability_multiplier`
is that discount, with an interval from season-to-season variance.

CAVEAT (honest): Transfermarkt injury records are editor-maintained, better for recent
seasons and bigger leagues; `days_missed` is calendar days out, not matches, so the
availability fraction is days-based (a league-agnostic proxy), floored — treat as a
durability *signal*, not audited medical data. Not point-in-time safe: a player's injury
history includes spells after any past transfer date, so for a *historical* deal use only
the spells up to that date (`spells_before(tm_id, date)`), never the career summary.

Output: data/master/injuries.parquet — one row per player:
  tm_player_id, n_spells, seasons_observed, career_days_missed, career_games_missed,
  avg_days_per_season, recent3_days, recent3_games, last_injury_season,
  availability, avail_lo, avail_hi, injury_prone
"""
from __future__ import annotations
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "data" / "injuries" / "player_injuries.csv"
OUT = REPO / "data" / "master" / "injuries.parquet"
_URL = ("https://raw.githubusercontent.com/salimt/football-datasets/main/"
        "datalake/transfermarkt/player_injuries/player_injuries.csv")


def _ensure_source():
    """Fetch the raw spell CSV if it isn't cached yet (makes `build` reproducible)."""
    if SRC.exists():
        return
    import urllib.request
    SRC.parent.mkdir(parents=True, exist_ok=True)
    print(f"fetching {_URL} ...")
    urllib.request.urlretrieve(_URL, SRC)

_DAYS_PER_SEASON = 365.0
# floor: nobody is modelled below 40% available (even the most fragile play *some*).
_AVAIL_FLOOR = 0.40
# a season counts as "injury-prone" above this many days out.
_PRONE_DAYS = 60.0


def _season_start_year(s: pd.Series) -> pd.Series:
    """'15/16' -> 2015, '99/00' -> 1999. Vectorised, tolerant of junk."""
    first = s.astype(str).str.slice(0, 2)
    yy = pd.to_numeric(first, errors="coerce")
    # 00-29 -> 2000s, 30-99 -> 1900s (football data spans ~1990-2026)
    return np.where(yy <= 29, 2000 + yy, 1900 + yy)


def tidy(raw: pd.DataFrame) -> pd.DataFrame:
    """Raw spell rows -> per-player durability summary."""
    df = raw.copy()
    df["tm_player_id"] = pd.to_numeric(df["player_id"], errors="coerce").astype("Int64")
    df["days_missed"] = pd.to_numeric(df["days_missed"], errors="coerce").fillna(0.0)
    df["games_missed"] = pd.to_numeric(df["games_missed"], errors="coerce").fillna(0.0)
    df["yr"] = _season_start_year(df["season_name"])
    df = df.dropna(subset=["tm_player_id"])
    df = df[df["days_missed"] >= 0]

    # per player-season totals (a player can have several spells in a season).
    # Transfermarkt lists overlapping spells whose summed days can exceed a year —
    # clip at the physical ceiling (you cannot miss more than 365 days in a season).
    ps = (df.groupby(["tm_player_id", "yr"], as_index=False)
            .agg(days=("days_missed", "sum"), games=("games_missed", "sum"),
                 spells=("days_missed", "size")))
    ps["days"] = ps["days"].clip(upper=_DAYS_PER_SEASON)

    max_yr = int(ps["yr"].max())
    recent_cut = max_yr - 2  # last 3 seasons in the data

    rows = []
    for pid, g in ps.groupby("tm_player_id"):
        n_seasons = g["yr"].nunique()
        career_days = float(g["days"].sum())
        recent = g[g["yr"] >= recent_cut]
        # average over OBSERVED seasons; if a player has spells they were tracked.
        avg_days = career_days / max(n_seasons, 1)
        recent_days = float(recent["days"].sum()) / max(len(recent), 1) if len(recent) else avg_days
        # availability from recent form, days-based, floored.
        avail = max(_AVAIL_FLOOR, 1.0 - recent_days / _DAYS_PER_SEASON)
        # interval from season-to-season spread of days-out (uncertainty in a noisy record)
        sd = float(g["days"].std(ddof=0)) if n_seasons > 1 else avg_days * 0.5
        lo = max(_AVAIL_FLOOR, 1.0 - (recent_days + sd) / _DAYS_PER_SEASON)
        hi = min(1.0, 1.0 - max(0.0, recent_days - sd) / _DAYS_PER_SEASON)
        rows.append(dict(
            tm_player_id=int(pid), n_spells=int(g["spells"].sum()),
            seasons_observed=int(n_seasons), career_days_missed=round(career_days, 1),
            career_games_missed=int(g["games"].sum()),
            avg_days_per_season=round(avg_days, 1), recent3_days=round(recent_days, 1),
            recent3_games=int(recent["games"].sum()), last_injury_season=int(g["yr"].max()),
            availability=round(avail, 3), avail_lo=round(lo, 3), avail_hi=round(hi, 3),
            injury_prone=bool(avg_days >= _PRONE_DAYS)))
    return pd.DataFrame(rows).sort_values("career_days_missed", ascending=False).reset_index(drop=True)


def build() -> pd.DataFrame:
    _ensure_source()
    raw = pd.read_csv(SRC)
    out = tidy(raw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"injury spells (raw):      {len(raw):,}")
    print(f"players with a history:   {len(out):,}")
    print(f"  injury-prone (>{int(_PRONE_DAYS)}d/yr): {int(out.injury_prone.sum()):,}")
    print(f"  median availability:    {out.availability.median():.3f}")
    print(f"  most days out (career): {out.iloc[0].tm_player_id} = {out.iloc[0].career_days_missed:,.0f}d")
    print(f"wrote {OUT}")
    return out


def load() -> pd.DataFrame:
    return pd.read_parquet(OUT)


def spells_before(tm_player_id: int, date) -> pd.DataFrame:
    """Point-in-time safe: spells that ended on/before `date` for one player.

    Use this to build a durability feature for a *historical* transfer without
    leaking injuries that happened after the deal.
    """
    raw = pd.read_csv(SRC, usecols=["player_id", "from_date", "end_date", "days_missed"])
    cut = pd.Timestamp(date)
    raw = raw[pd.to_numeric(raw.player_id, errors="coerce") == tm_player_id].copy()
    raw["end_date"] = pd.to_datetime(raw.end_date, errors="coerce")
    return raw[raw.end_date <= cut].reset_index(drop=True)


class Availability(NamedTuple):
    mult: float
    lo: float
    hi: float
    source: str  # 'injury_record' if found, 'assumed_fit' if no history


def availability_multiplier(tm_player_id: int, table: pd.DataFrame | None = None) -> Availability:
    """Availability discount for NPV benefit. No record -> assume fit (1.0), flagged.

    A clean injury sheet is not proof of durability, so 'assumed_fit' is a *flag*,
    not a fact — same honesty rule as the wage model.
    """
    t = load() if table is None else table
    row = t[t.tm_player_id == tm_player_id]
    if row.empty:
        return Availability(1.0, 0.90, 1.0, "assumed_fit")
    r = row.iloc[0]
    return Availability(float(r.availability), float(r.avail_lo), float(r.avail_hi), "injury_record")


def _check():
    raw = pd.DataFrame([
        # p1: chronic — 3 seasons, ~120d/yr -> injury-prone, low availability
        dict(player_id=1, season_name="21/22", injury_reason="Knee", from_date="2021-09-01",
             end_date="2021-12-01", days_missed=90, games_missed=12),
        dict(player_id=1, season_name="21/22", injury_reason="Calf", from_date="2022-02-01",
             end_date="2022-03-03", days_missed=30, games_missed=5),
        dict(player_id=1, season_name="22/23", injury_reason="Knee", from_date="2022-09-01",
             end_date="2022-12-30", days_missed=120, games_missed=16),
        dict(player_id=1, season_name="23/24", injury_reason="Hamstring", from_date="2023-09-01",
             end_date="2023-11-30", days_missed=90, games_missed=12),
        # p2: one minor knock, recent
        dict(player_id=2, season_name="23/24", injury_reason="Ankle", from_date="2024-01-01",
             end_date="2024-01-11", days_missed=10, games_missed=2),
    ])
    out = tidy(raw)
    o = out.set_index("tm_player_id")
    # p1 is injury-prone, p2 is not
    assert o.loc[1].injury_prone and not o.loc[2].injury_prone, out
    # availability ordering: fragile p1 well below fit p2
    assert o.loc[1].availability < o.loc[2].availability
    # p1 recent = 3-season avg (120,120,90)/3 = 110d -> avail ~ 1-110/365 = 0.699
    assert abs(o.loc[1].availability - 0.699) < 0.02, o.loc[1].availability
    # bounds sane, floor respected
    assert (out.availability >= _AVAIL_FLOOR - 1e-9).all()
    assert (out.avail_lo <= out.availability).all() and (out.availability <= out.avail_hi).all()
    # multiplier lookup: known -> injury_record, unknown -> assumed_fit=1.0
    a1 = availability_multiplier(1, out)
    assert a1.source == "injury_record" and a1.mult == o.loc[1].availability
    am = availability_multiplier(99999, out)
    assert am.source == "assumed_fit" and am.mult == 1.0
    # season parser
    assert list(_season_start_year(pd.Series(["15/16", "99/00", "05/06"]))) == [2015, 1999, 2005]
    print(out.to_string())
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
