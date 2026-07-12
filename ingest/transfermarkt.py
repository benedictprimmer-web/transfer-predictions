"""Transfermarkt dump — minutes/lineups + transfers/valuations, no Kaggle auth.

Source: `davidcariboo/player-scores` (Kaggle, CC0), built by the GitHub project
`dcaribou/transfermarkt-datasets`, which publishes every table unauthenticated
on a Cloudflare R2 public bucket as `<table>.csv.gz`. Verified reachable from
this machine 2026-07-11. Files cache to data/transfermarkt/.

Two tidy outputs:
- tidy_minutes  -> lineup schema impact/wowy.py consumes
  (game_id, team, player, is_starter, minutes) + league/season/date tags,
  Big-5 leagues only. Minutes from appearances; starter/sub from game_lineups
  where present, else estimated from minutes and flagged (starter_estimated).
- tidy_transfers -> the FEATURES frame money/fees.py consumes
  (age, market_value, position, from_league, to_league, season, fee)
  + player/date/fee_disclosed. from_/to_league are club names, matching
  fees.py's convention. market_value is the player_valuations record nearest
  BEFORE the transfer date; age from players.date_of_birth. Undisclosed fees
  (0/null) are kept and marked fee_disclosed=False, never dropped.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "transfermarkt"
_R2 = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/{}.csv.gz"

TABLES = ("appearances", "game_lineups", "transfers", "player_valuations",
          "players", "games", "clubs")

# dump competition_id -> league key (same keys as ingest/understat.py)
BIG5 = {
    "GB1": "ENG-Premier League",
    "ES1": "ESP-La Liga",
    "IT1": "ITA-Serie A",
    "L1":  "GER-Bundesliga",
    "FR1": "FRA-Ligue 1",
}


def download(tables=TABLES, force=False) -> list[Path]:
    """Fetch missing .csv.gz tables into data/transfermarkt/. Idempotent."""
    import urllib.request
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for t in tables:
        dest = DATA_DIR / f"{t}.csv.gz"
        if force or not dest.exists():
            urllib.request.urlretrieve(_R2.format(t), dest)
        out.append(dest)
    return out


def _read(table: str, **kw) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{table}.csv.gz", **kw)


def _season(start_year) -> str:
    """Dump season is the start year (2014 -> '2014-2015'), as in understat.py."""
    y = int(start_year)
    return f"{y}-{y + 1}"


# Horizon past which a transfer_date is a rumour/corruption, not a pre-agreed
# deal. TM lists confirmed future moves (summers ahead), so we don't cap at
# today — but nothing legitimate is dated >18 months out (the 2030 rows are junk).
_DATE_HORIZON = pd.Timestamp("2026-07-12") + pd.DateOffset(months=18)


def sane_transfer_dates(dates: pd.Series, horizon: pd.Timestamp = _DATE_HORIZON) -> pd.Series:
    """Boolean mask: a real, usable transfer_date (non-null, not absurdly future)."""
    d = pd.to_datetime(dates, errors="coerce")
    return d.notna() & (d <= horizon)


# ---------------------------------------------------------------- minutes

def tidy_minutes(appearances: pd.DataFrame, lineups: pd.DataFrame,
                 games: pd.DataFrame) -> pd.DataFrame:
    """appearances + game_lineups + games -> wowy lineup schema, Big-5 only.

    team is the club name from games (home/away matched on player_club_id);
    rows whose club matches neither side (broken scrapes) are dropped.
    is_starter comes from game_lineups.type; appearances without a lineup row
    get minutes>=60 as the starter guess and starter_estimated=True.
    """
    ap = appearances[appearances.competition_id.isin(BIG5)].copy()
    ap["minutes"] = pd.to_numeric(ap.minutes_played, errors="coerce")

    g = games[["game_id", "season", "home_club_id", "away_club_id",
               "home_club_name", "away_club_name"]]
    d = ap.merge(g, on="game_id", how="left")
    is_home = d.player_club_id == d.home_club_id
    is_away = d.player_club_id == d.away_club_id
    d["team"] = np.where(is_home, d.home_club_name, d.away_club_name)
    d = d[is_home | is_away]  # club on neither side = broken row, drop

    # one lineup row per (game, player); prefer starting_lineup over substitutes
    lu = (lineups[["game_id", "player_id", "type"]]
          .sort_values("type")  # 'starting_lineup' < 'substitutes'
          .drop_duplicates(["game_id", "player_id"]))
    d = d.merge(lu, on=["game_id", "player_id"], how="left")
    d["starter_estimated"] = d.type.isna()
    # ponytail: no-lineup fallback is minutes>=60 -> starter; a sub playing 60+
    # exists but is rare. Upgrade path: game_events sub timestamps.
    d["is_starter"] = np.where(d.type.notna(),
                               d.type.eq("starting_lineup"),
                               d.minutes >= 60).astype(bool)

    out = pd.DataFrame({
        "game_id": d.game_id.astype(str),
        "team": d.team,
        "player": d.player_name,
        "is_starter": d.is_starter,
        "minutes": d.minutes,
        "league": d.competition_id.map(BIG5),
        "season": d.season.map(_season),
        "date": pd.to_datetime(d.date, errors="coerce"),
        "starter_estimated": d.starter_estimated,
    })
    return out.dropna(subset=["minutes", "team"]).reset_index(drop=True)


def read_minutes() -> pd.DataFrame:
    """Download (if needed) + tidy the Big-5 minutes/lineups frame."""
    download(("appearances", "game_lineups", "games"))
    ap = _read("appearances", usecols=["game_id", "player_id", "player_club_id",
                                       "player_name", "date", "competition_id",
                                       "minutes_played"])
    lu = _read("game_lineups", usecols=["game_id", "player_id", "type"])
    gm = _read("games", usecols=["game_id", "season", "home_club_id",
                                 "away_club_id", "home_club_name",
                                 "away_club_name"])
    return tidy_minutes(ap, lu, gm)


def minutes_coverage(minutes: pd.DataFrame) -> pd.DataFrame:
    """League-season coverage of the minutes frame (games, players, starter info)."""
    g = minutes.groupby(["league", "season"], sort=True)
    cov = g.agg(
        n_games=("game_id", "nunique"),
        n_players=("player", "nunique"),
        n_rows=("minutes", "size"),
        pct_starter_known=("starter_estimated", lambda s: round(100 * (1 - s.mean()), 1)),
    ).reset_index()
    return cov


# --------------------------------------------------------------- transfers

def tidy_transfers(transfers: pd.DataFrame, players: pd.DataFrame,
                   valuations: pd.DataFrame) -> pd.DataFrame:
    """transfers + players + player_valuations -> fees.py FEATURES frame.

    market_value = valuation nearest before the transfer date (merge_asof
    backward); NaN when the player has no prior valuation — left NaN, fees.py
    drops those. fee_disclosed=False where the fee is 0/null (free transfers
    and undisclosed deals are indistinguishable in the dump — both marked).
    Rows with no transfer_date are dropped (nothing downstream can use them).
    """
    t = transfers.copy()
    t["date"] = pd.to_datetime(t.transfer_date, errors="coerce")
    t = t[sane_transfer_dates(t.date)]  # drop null + absurd-future (rumour) dates
    t["fee"] = pd.to_numeric(t.transfer_fee, errors="coerce")

    p = players[["player_id", "date_of_birth", "position"]].copy()
    p["date_of_birth"] = pd.to_datetime(p.date_of_birth, errors="coerce")
    t = t.merge(p, on="player_id", how="left")
    t["age"] = (t.date - t.date_of_birth).dt.days / 365.25

    v = valuations[["player_id", "date", "market_value_in_eur"]].copy()
    v["date"] = pd.to_datetime(v.date, errors="coerce")
    v = v.dropna(subset=["date"]).sort_values("date")
    t = pd.merge_asof(t.sort_values("date"), v.rename(columns={
        "market_value_in_eur": "market_value"}),
        on="date", by="player_id", direction="backward")

    out = pd.DataFrame({
        "age": t.age,
        "market_value": pd.to_numeric(t.market_value, errors="coerce"),
        "position": t.position,
        "from_league": t.from_club_name,  # club name, per fees.py convention
        "to_league": t.to_club_name,
        "season": t.date.dt.year,
        "fee": t.fee,
        "player": t.player_name,
        "date": t.date,
        "fee_disclosed": t.fee.notna() & (t.fee > 0),
    })
    return out.reset_index(drop=True)


def read_transfers() -> pd.DataFrame:
    """Download (if needed) + tidy the transfers frame."""
    download(("transfers", "players", "player_valuations"))
    return tidy_transfers(_read("transfers"),
                          _read("players", usecols=["player_id", "date_of_birth",
                                                    "position"]),
                          _read("player_valuations"))


# ------------------------------------------------------------------ check

def _check():
    # --- minutes: 1 Big-5 game + 1 non-Big-5 row + 1 wrong-club row
    ap = pd.DataFrame([
        dict(game_id=1, player_id=10, player_club_id=100, player_name="A",
             date="2023-08-12", competition_id="GB1", minutes_played=90),
        dict(game_id=1, player_id=11, player_club_id=200, player_name="B",
             date="2023-08-12", competition_id="GB1", minutes_played=30),
        dict(game_id=1, player_id=12, player_club_id=100, player_name="C",
             date="2023-08-12", competition_id="GB1", minutes_played=90),  # no lineup row
        dict(game_id=2, player_id=13, player_club_id=300, player_name="D",
             date="2023-08-12", competition_id="TR1", minutes_played=90),  # not Big-5
        dict(game_id=1, player_id=14, player_club_id=999, player_name="E",
             date="2023-08-12", competition_id="GB1", minutes_played=90),  # broken club
    ])
    lu = pd.DataFrame([
        dict(game_id=1, player_id=10, type="starting_lineup"),
        dict(game_id=1, player_id=11, type="substitutes"),
        dict(game_id=1, player_id=11, type="substitutes"),  # dup row survives dedup
    ])
    gm = pd.DataFrame([
        dict(game_id=1, season=2023, home_club_id=100, away_club_id=200,
             home_club_name="Arsenal", away_club_name="Spurs"),
        dict(game_id=2, season=2023, home_club_id=300, away_club_id=400,
             home_club_name="X", away_club_name="Y"),
    ])
    m = tidy_minutes(ap, lu, gm)
    assert list(m.columns)[:5] == ["game_id", "team", "player", "is_starter", "minutes"]
    assert len(m) == 3, m                       # non-Big-5 + broken-club dropped
    r = m.set_index("player")
    assert r.loc["A"].is_starter and r.loc["A"].team == "Arsenal"
    assert not r.loc["B"].is_starter and r.loc["B"].team == "Spurs"
    assert r.loc["C"].is_starter and r.loc["C"].starter_estimated  # flagged guess
    assert not r.loc["A"].starter_estimated
    assert r.loc["A"].league == "ENG-Premier League" and r.loc["A"].season == "2023-2024"

    # tidy output plugs into wowy's lineup schema
    from impact import wowy
    assert {"game_id", "team", "player", "is_starter", "minutes"}.issubset(m.columns)
    iv = wowy.intervals(m).set_index("player")
    assert iv.loc["B"].on == 60.0 and iv.loc["B"].off == 90.0

    # --- transfers: disclosed fee, undisclosed (0), pre-transfer valuation pick
    tr = pd.DataFrame([
        dict(player_id=1, transfer_date="2020-07-01", from_club_name="Ajax",
             to_club_name="Chelsea", transfer_fee=40e6, player_name="H"),
        dict(player_id=2, transfer_date="2020-07-01", from_club_name="X",
             to_club_name="Y", transfer_fee=0.0, player_name="Free"),
        dict(player_id=3, transfer_date="2020-07-01", from_club_name="X",
             to_club_name="Y", transfer_fee=None, player_name="NoDate&Fee",
             ),
    ])
    pl = pd.DataFrame([
        dict(player_id=1, date_of_birth="2000-07-01", position="Attack"),
        dict(player_id=2, date_of_birth=None, position="Defender"),
        dict(player_id=3, date_of_birth="1995-01-01", position="Midfield"),
    ])
    va = pd.DataFrame([
        dict(player_id=1, date="2020-06-01", market_value_in_eur=30e6),  # before -> used
        dict(player_id=1, date="2020-08-01", market_value_in_eur=50e6),  # after -> ignored
        dict(player_id=2, date="2021-01-01", market_value_in_eur=1e6),   # only after -> NaN
    ])
    # sane-date guard: a 2030 rumour row and a null date are both dropped
    assert sane_transfer_dates(pd.Series(["2030-06-30", None, "2025-01-01"])).tolist() == [False, False, True]

    tt = tidy_transfers(tr, pl, va)
    assert list(tt.columns)[:7] == ["age", "market_value", "position",
                                    "from_league", "to_league", "season", "fee"]
    h = tt.set_index("player").loc["H"]
    assert h.market_value == 30e6, "must take the valuation BEFORE the transfer"
    assert np.isclose(h.age, 20.0, atol=0.01) and h.season == 2020 and h.fee_disclosed
    f = tt.set_index("player").loc["Free"]
    assert not f.fee_disclosed and np.isnan(f.market_value) and np.isnan(f.age)
    assert not tt.set_index("player").loc["NoDate&Fee"].fee_disclosed

    # tidy output carries every feature fees.py trains on
    from money import fees
    assert set(fees.FEATURES).issubset(tt.columns)

    print(m.to_string(index=False))
    print(tt.to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        download()  # all tables, incl. players/clubs for downstream joins
        mins = read_minutes()
        cov = minutes_coverage(mins)
        tr = read_transfers()
        out = DATA_DIR / "coverage_minutes.csv"
        cov.to_csv(out, index=False)
        print(cov.to_string(index=False))
        print(f"\nminutes rows: {len(mins):,}  transfers rows: {len(tr):,}  "
              f"fee disclosed: {100 * tr.fee_disclosed.mean():.1f}%")
        print(f"wrote {out}")
    else:
        _check()
