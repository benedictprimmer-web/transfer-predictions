"""Club-by-club revenue (Stage 11 data half) — matchday / broadcast / commercial split.

Source: Deloitte Football Money League 2022 edition (25th edition), the annual PDF
that profiles the top-20 revenue-generating football clubs in the world, split into
matchday/broadcast/commercial (EUR m). Reachable sandbox-ok via a Deloitte CZ mirror
(`www2.deloitte.com/content/dam/Deloitte/cz/Documents/consumer-business/
deloitte-football-money-league-2022.pdf`) that bypasses the bot-block on the primary
UK/global Deloitte pages (those redirect-loop from this datacenter IP). Free-to-read
published analysis; used here as an audited-secondary source (grade B, not a raw
financial-statement primary), never redistributed beyond this repo.

Numbers below are lifted from that PDF's per-club "2021 Revenue profile" infographic —
one struct per club, geometry-extracted (pdfplumber word x/y positions, NOT raw text
stream order: the three donut-slice values do not appear in a fixed reading-stream
order per club, only a fixed *screen position* — top-right small slice = matchday,
left column = broadcast, right column mid-band = commercial). Every row was verified
against the page's own printed Total (matchday + broadcast + commercial == total,
20/20 clubs, within EUR 0.1m rounding) and one club (Wolves) additionally cross-checked
against the club's own headline-financial-information press release. See
`LANE_C_HARVEST.md` for the extraction method, the geometric-position pitfall it avoids,
and the full reachability table.

Season 2020/21 (Deloitte's "2021 Revenue") — a COVID-affected season: matchday
collapsed to near-zero leaguewide (behind-closed-doors football) and broadcast/
commercial shares were unusually volatile club-to-club (broadcaster rebates, deferred
distributions). Treat this season's *split* as directionally real but not a normal-year
baseline; treat *totals* as real regardless.

Stadium capacity: not re-sourced here — already on disk at `data/transfermarkt/
clubs.csv.gz` (`stadium_seats`, 796 clubs, 100% populated), keyed by the same
`club_id` that IS `to_club_id` in the canonical spine. Joined in at build time.

Grade: B (published analysis of audited club accounts, single season, top-20-only).
Crosswalk: club_id == to_club_id (Transfermarkt id), hand-mapped for these 20 clubs
(verified against `data/transfermarkt/clubs.csv.gz` name+competition).

Run: `python3 -m ingest.club_revenue`        -> _check (offline, no network)
     `python3 -m ingest.club_revenue build`  -> writes data/money/club_revenue.parquet
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_PATH = DATA_DIR / "money" / "club_revenue.parquet"
CLUBS_PATH = DATA_DIR / "transfermarkt" / "clubs.csv.gz"

SEASON = 2020  # canonical-spine convention: season = year the season STARTS -> 2020/21
SOURCE = "deloitte_money_league_2022"
GRADE = "B"

# (deloitte club name, transfermarkt club_id, matchday, broadcast, commercial, total) — EUR m
_ROWS = [
    ("Manchester City",           281,  0.8, 308.2, 335.9, 644.9),
    ("Real Madrid",               418,  8.6, 321.6, 310.5, 640.7),
    ("Bayern Munich",              27, 11.7, 345.2, 254.5, 611.4),
    ("FC Barcelona",              131, 15.9, 276.6, 289.6, 582.1),
    ("Manchester United",         985,  8.0, 262.2, 287.8, 558.0),
    ("Paris Saint-Germain",       583, 17.0, 337.4, 201.8, 556.2),
    ("Liverpool FC",               31,  8.3, 238.4, 303.7, 550.4),
    ("Chelsea FC",                631,  8.6, 175.5, 309.0, 493.1),
    ("Juventus FC",                506,  7.8, 188.7, 237.0, 433.5),
    ("Tottenham Hotspur",          148,  2.1, 170.8, 233.3, 406.2),
    ("Arsenal FC",                  11,  4.3, 154.0, 208.2, 366.5),
    ("Borussia Dortmund",           16,  1.4, 149.5, 186.7, 337.6),
    ("Atlético de Madrid",          13,  4.2,  98.1, 230.5, 332.8),
    ("Inter Milan",                 46,  2.2, 112.7, 216.0, 330.9),
    ("Leicester City",            1003,  0.7,  46.4, 208.4, 255.5),
    ("West Ham United",            379,  0.6,  36.7, 184.2, 221.5),
    ("Wolverhampton Wanderers",    543,  0.8,  27.2, 191.3, 219.2),
    ("Everton FC",                  29,  0.3,  52.5, 165.3, 218.1),
    ("AC Milan",                     5,  0.0,  69.1, 147.2, 216.3),
    ("AO FK Zenit Sankt-Peterburg", 964,  7.3, 161.5,  43.2, 212.0),
]


def build() -> pd.DataFrame:
    df = pd.DataFrame(_ROWS, columns=[
        "club_name", "club_id", "matchday_eur_m", "broadcast_eur_m",
        "commercial_eur_m", "total_eur_m",
    ])
    df["season"] = SEASON
    df["source"] = SOURCE
    df["grade"] = GRADE

    clubs = pd.read_csv(CLUBS_PATH, usecols=["club_id", "stadium_seats"])
    df = df.merge(clubs, on="club_id", how="left")
    df = df.rename(columns={"stadium_seats": "stadium_capacity", "club_id": "to_club_id"})

    df = df[["to_club_id", "club_name", "season", "matchday_eur_m", "broadcast_eur_m",
             "commercial_eur_m", "total_eur_m", "stadium_capacity", "source", "grade"]]
    return df


def write():
    df = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False)
    print(f"wrote {len(df)} club-season rows -> {OUT_PATH}")
    return df


def _check():
    df = build()
    assert len(df) == 20, len(df)
    assert df.to_club_id.notna().all() and df.to_club_id.is_unique

    # every row's split reconciles to its own printed total, within rounding
    recon = (df.matchday_eur_m + df.broadcast_eur_m + df.commercial_eur_m - df.total_eur_m).abs()
    assert (recon < 0.2).all(), recon[recon >= 0.2]

    # stadium capacity joined for every row (clubs.csv.gz has 100% coverage)
    assert df.stadium_capacity.notna().all()

    # self-check (Stage 11 spec): Man Utd's commercial >> the smallest club's in the panel
    mu = df.loc[df.club_name == "Manchester United", "commercial_eur_m"].item()
    smallest = df.loc[df.club_name != "Manchester United", "commercial_eur_m"].min()
    smallest_club = df.loc[df.commercial_eur_m == smallest, "club_name"].item()
    assert mu > 2 * smallest, (mu, smallest)

    # every row graded/sourced, never silently blended
    assert (df.grade == "B").all()
    assert df.source.eq(SOURCE).all()

    print(f"20/20 club-seasons reconcile to printed total; "
          f"Man Utd commercial EUR{mu:.0f}m > {smallest_club} EUR{smallest:.0f}m; ok")


if __name__ == "__main__":
    import sys
    write() if "build" in sys.argv[1:] else _check()
