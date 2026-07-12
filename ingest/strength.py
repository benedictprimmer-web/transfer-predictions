"""Club Elo strength prior — via the tonyelhabr/club-rankings GitHub mirror.

api.clubelo.com times out from this environment; the mirror scrapes clubelo.com
daily and publishes one CSV on a GitHub release (asset `clubelo-club-rankings.csv`,
tag `club-rankings`). Columns: Rank, Club, Country, Level (league tier), Elo,
From, To, plus scrape `date`/`updated_at`. See DATA_SOURCES.md.

History is shallow: snapshots start 2023-03-27 (when the mirror began scraping).
Full per-club history back decades exists at api.clubelo.com/<Club> — needs a
residential-IP pull; do NOT fabricate pre-2023 values from this source.

Tidy output: club, country, date, elo, level (one row per club per snapshot
date). `league_strength(elo, date)` gives per-country mean Elo of tier-1 clubs
at the nearest snapshot on/before `date` — the cross-league conversion prior.
Caches to data/strength/.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "strength"
_URL = ("https://github.com/tonyelhabr/club-rankings/releases/download/"
        "club-rankings/clubelo-club-rankings.csv")
_RAW_FILE = "clubelo-club-rankings.csv"
# ponytail: opta-club-rankings.csv (170MB, 2023+ only) skipped — ClubElo alone
# is the strength prior; add if a second rating source is ever wanted.

_API_URL = "http://api.clubelo.com/{slug}"  # per-club CSV back to ~1946
_HISTORY_DIR = DATA_DIR / "history"          # raw per-club cache (resumable)
_HISTORY_FILE = "clubelo_history.csv"        # combined tidy history
_COUNTRIES = ["ENG", "ESP", "ITA", "GER", "FRA", "NED", "POR"]


def download(force=False) -> Path:
    """Fetch the mirror CSV into data/strength/ (~47MB). Idempotent."""
    import urllib.request
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / _RAW_FILE
    if force or not dest.exists():
        urllib.request.urlretrieve(_URL, dest)
    return dest


def tidy_elo(raw: pd.DataFrame) -> pd.DataFrame:
    """Mirror CSV -> club, country, date, elo, level.

    One row per club per snapshot date: manual workflow triggers can produce
    multiple scrapes per day; keep the last (by updated_at order in the file).
    """
    out = pd.DataFrame({
        "club": raw["Club"].astype(str),
        "country": raw["Country"].astype(str),
        "date": pd.to_datetime(raw["date"]),
        "elo": pd.to_numeric(raw["Elo"], errors="coerce"),
        "level": pd.to_numeric(raw["Level"], errors="coerce").astype("Int64"),
    })
    out = out.dropna(subset=["elo"])
    out = out.drop_duplicates(subset=["club", "date"], keep="last")
    return out.sort_values(["date", "country", "club"]).reset_index(drop=True)


def read_elo() -> pd.DataFrame:
    """Download (if needed) + tidy the full Elo snapshot series."""
    return tidy_elo(pd.read_csv(download()))


def league_strength(elo: pd.DataFrame, date) -> pd.Series:
    """Per-country mean Elo of its tier-1 clubs at the nearest snapshot
    on/before `date` (falls back to the earliest snapshot for pre-history
    dates). Series indexed by country — the cross-league prior."""
    date = pd.Timestamp(date)
    dates = elo["date"].drop_duplicates().sort_values()
    past = dates[dates <= date]
    snap_date = past.iloc[-1] if len(past) else dates.iloc[0]
    snap = elo[(elo["date"] == snap_date) & (elo["level"] == 1)]
    return snap.groupby("country")["elo"].mean().rename("league_elo")


def _history_clubs() -> list[str]:
    """Club universe to backfill: tier-1 clubs of _COUNTRIES seen anywhere in the
    2023+ mirror. Uses real ClubElo spellings, so slugs resolve on the API.

    # ponytail: derived from the mirror only, not transfermarkt/clubs.csv.gz —
    # the task allows this and it dodges a TM->ClubElo name-crosswalk. Add TM
    # clubs (with a spelling map) if a club outside the mirror is ever needed.
    """
    elo = read_elo()
    t1 = elo[elo.country.isin(_COUNTRIES) & (elo.level == 1)]
    return sorted(t1["club"].unique())


def download_history(clubs, force=False) -> list[str]:
    """Pull http://api.clubelo.com/<slug> per club, cache raw CSV under
    data/strength/history/<slug>.csv. Idempotent + resumable (skips cached).
    Returns slugs that resolved to a non-empty series; logs 404/empty misses."""
    import time
    import urllib.request
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    got = []
    for club in clubs:
        slug = club.replace(" ", "")  # ClubElo slug = club name, spaces stripped
        dest = _HISTORY_DIR / f"{slug}.csv"
        if not force and dest.exists():
            if dest.stat().st_size > 40:  # >header only = real data
                got.append(slug)
            continue
        try:
            with urllib.request.urlopen(_API_URL.format(slug=slug), timeout=20) as r:
                body = r.read()
        except Exception as e:  # network hiccup / 404 -> skip, log
            print(f"MISS {club} ({slug}): {e}")
            time.sleep(0.3)
            continue
        # empty series comes back as header-only (one line, no data rows).
        if body.count(b"\n") < 2:
            print(f"MISS {club} ({slug}): empty series")
            time.sleep(0.3)
            continue
        dest.write_bytes(body)
        got.append(slug)
        time.sleep(0.3)  # polite rate-limit
    return got


def tidy_history(raw: pd.DataFrame) -> pd.DataFrame:
    """API per-club CSV -> club, country, date, elo, level. One row per (club,
    From): date = the interval From, so the as-of-nearest-on/before logic in
    league_strength works over contiguous intervals."""
    out = pd.DataFrame({
        "club": raw["Club"].astype(str),
        "country": raw["Country"].astype(str),
        "date": pd.to_datetime(raw["From"]),
        "elo": pd.to_numeric(raw["Elo"], errors="coerce"),
        "level": pd.to_numeric(raw["Level"], errors="coerce").astype("Int64"),
    })
    out = out.dropna(subset=["elo"])
    out = out.drop_duplicates(subset=["club", "date"], keep="last")
    return out.sort_values(["date", "country", "club"]).reset_index(drop=True)


def read_history() -> pd.DataFrame:
    """Tidy every cached raw club CSV into the combined history frame."""
    frames = [tidy_history(pd.read_csv(p))
              for p in sorted(_HISTORY_DIR.glob("*.csv"))]
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["date", "country", "club"]).reset_index(drop=True)


def build_history(force=False) -> pd.DataFrame:
    """Download (resumable) + tidy + write data/strength/clubelo_history.csv."""
    clubs = _history_clubs()
    got = download_history(clubs, force=force)
    print(f"resolved {len(got)}/{len(clubs)} clubs")
    hist = read_history()
    hist.to_csv(DATA_DIR / _HISTORY_FILE, index=False)
    return hist


def _check():
    # synthetic mirror-shaped frame -> tidy -> league_strength, no network.
    raw = pd.DataFrame([
        # dup scrape same day: keep last
        dict(Rank=1, Club="Man City", Country="ENG", Level=1, Elo=2000.0,
             From="2024-01-01", To="2024-01-05", date="2024-01-05",
             updated_at="2024-01-05 06:00:00"),
        dict(Rank=1, Club="Man City", Country="ENG", Level=1, Elo=2010.0,
             From="2024-01-01", To="2024-01-05", date="2024-01-05",
             updated_at="2024-01-05 12:00:00"),
        dict(Rank=2, Club="Arsenal", Country="ENG", Level=1, Elo=1990.0,
             From="2024-01-01", To="2024-01-05", date="2024-01-05",
             updated_at="2024-01-05 12:00:00"),
        dict(Rank=50, Club="Leeds", Country="ENG", Level=2, Elo=1700.0,  # tier 2: excluded from league mean
             From="2024-01-01", To="2024-01-05", date="2024-01-05",
             updated_at="2024-01-05 12:00:00"),
        dict(Rank=3, Club="Ajax", Country="NED", Level=1, Elo=1800.0,
             From="2024-01-01", To="2024-01-05", date="2024-01-05",
             updated_at="2024-01-05 12:00:00"),
        # a later snapshot, to prove asof picks the right date
        dict(Rank=1, Club="Man City", Country="ENG", Level=1, Elo=2050.0,
             From="2024-01-06", To="2024-01-10", date="2024-01-10",
             updated_at="2024-01-10 12:00:00"),
        dict(Rank=9, Club="NoElo", Country="ENG", Level=1, Elo=None,  # dropped
             From="2024-01-06", To="2024-01-10", date="2024-01-10",
             updated_at="2024-01-10 12:00:00"),
    ])
    elo = tidy_elo(raw)
    assert list(elo.columns) == ["club", "country", "date", "elo", "level"]
    assert len(elo) == 5, "dup-day row and NaN-elo row dropped"
    mc = elo[(elo.club == "Man City") & (elo.date == "2024-01-05")]
    assert mc.elo.iloc[0] == 2010.0, "keep last scrape of the day"

    ls = league_strength(elo, "2024-01-07")  # between snapshots -> uses 01-05
    assert ls["ENG"] == (2010.0 + 1990.0) / 2, "tier-1 only, tier-2 excluded"
    assert ls["NED"] == 1800.0
    ls2 = league_strength(elo, "2024-01-10")
    assert ls2["ENG"] == 2050.0
    ls0 = league_strength(elo, "2020-01-01")  # pre-history -> earliest snapshot
    assert ls0["NED"] == 1800.0

    # synthetic api-shaped frame -> tidy_history: date = From, one row per From.
    api = pd.DataFrame([
        dict(Rank="None", Club="Arsenal", Country="ENG", Level=1, Elo=1551.14,
             From="1946-07-07", To="1946-08-31"),
        dict(Rank="None", Club="Arsenal", Country="ENG", Level=1, Elo=1539.57,
             From="1946-09-01", To="1946-09-04"),
        dict(Rank="None", Club="Arsenal", Country="ENG", Level=2, Elo=1300.0,
             From="1950-01-01", To="1950-02-01"),  # tier-2 spell, kept in history
        dict(Rank="None", Club="Arsenal", Country="ENG", Level=1, Elo=None,
             From="1960-01-01", To="1960-02-01"),  # dropped
    ])
    h = tidy_history(api)
    assert list(h.columns) == ["club", "country", "date", "elo", "level"]
    assert len(h) == 3, "NaN-elo row dropped"
    row = h[h.date == pd.Timestamp("1946-09-01")]
    assert row.elo.iloc[0] == 1539.57, "From-date interval maps to its Elo"
    assert (h.club == "Arsenal").all()

    print(elo.to_string(index=False))
    print(ls.to_string())
    print(h.to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build_history" in sys.argv[1:]:
        hist = build_history()
        print(f"\n{len(hist):,} rows, {hist['club'].nunique()} clubs, "
              f"{hist['date'].min().date()} -> {hist['date'].max().date()}")
    elif "build" in sys.argv[1:]:
        elo = read_elo()
        big = elo[elo.country.isin(["ENG", "ESP", "ITA", "GER", "FRA", "NED", "POR"])]
        cov = big[big.level == 1].groupby("country").agg(
            n_rows=("elo", "size"), n_clubs=("club", "nunique"),
            first=("date", "min"), last=("date", "max"),
        )
        print(cov.to_string())
        print(league_strength(elo, elo["date"].max()).loc[
            ["ENG", "ESP", "ITA", "GER", "FRA", "NED", "POR"]].round(1).to_string())
        print(f"\n{len(elo):,} rows total, {elo['date'].nunique()} snapshot dates, "
              f"{elo['date'].min().date()} -> {elo['date'].max().date()}")
    else:
        _check()
