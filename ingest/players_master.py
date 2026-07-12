"""players_master — one row per Transfermarkt player with every foreign id
attached. The single identity spine the whole project should join through.

Spine: Estate A data/transfermarkt/players.csv.gz (TM player_id, name, dob,
position, nationality, ...). Onto it we graft:
  * understat_player_id  — via data/crosswalk/players.csv (ingest.crosswalk_players)
  * fbref_id             — via Estate B's player_crosswalk, with its broken
                           `player_id` column REPAIRED from url_tmarkt.

The FBref-bridge repair (audit finding L2-a): player_crosswalk.player_id is
stored as text and ~17% of rows disagree with the TM `spieler` id embedded in
their own url_tmarkt. We recover the true TM id with /spieler/(\\d+) and prefer
it; that lifts the bridge and de-corrupts those rows. This is what unlocks the
221-col FBref perf table (ingest.fbref_perf) for Estate A players.

Output: data/master/players_master.parquet
  tm_player_id, name, date_of_birth, position, sub_position, nationality,
  understat_player_id, fbref_id, contract_expiration_date,
  has_understat, has_fbref
"""
from __future__ import annotations
import os
import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ESTATE_A = REPO / "data" / "transfermarkt"
ESTATE_B = Path(os.environ.get(
    "ESTATE_B_DIR", "/Users/benrimmer/Downloads/football-transfer-db"))
DUCKDB = ESTATE_B / "02_transfers" / "transfers.duckdb"
OUT = REPO / "data" / "master" / "players_master.parquet"


def repair_fbref_bridge(xw: pd.DataFrame) -> pd.DataFrame:
    """player_crosswalk -> (tm_player_id, fbref_id), TM id repaired from url.

    Prefer the `spieler` id parsed from url_tmarkt over the stored player_id
    (which disagrees ~17% of the time). Rows where neither yields a numeric id
    are dropped. One fbref_id per tm id (first wins on the rare dup).
    """
    url_id = pd.to_numeric(
        xw.url_tmarkt.astype(str).str.extract(r"/spieler/(\d+)")[0], errors="coerce")
    stored = pd.to_numeric(xw.player_id, errors="coerce")
    tm_id = url_id.fillna(stored)
    out = pd.DataFrame({"tm_player_id": tm_id, "fbref_id": xw.fbref_id})
    out = out.dropna(subset=["tm_player_id", "fbref_id"])
    out["tm_player_id"] = out.tm_player_id.astype("int64")
    return out.drop_duplicates("tm_player_id")


def build() -> pd.DataFrame:
    import duckdb
    # spine
    pl = pd.read_csv(ESTATE_A / "players.csv.gz", compression="gzip", low_memory=False,
                     usecols=["player_id", "name", "date_of_birth", "position",
                              "sub_position", "country_of_citizenship",
                              "contract_expiration_date"])
    pl = pl.rename(columns={"player_id": "tm_player_id",
                            "country_of_citizenship": "nationality"})

    # understat bridge
    from ingest import crosswalk_players
    up = crosswalk_players.load()[["tm_player_id", "us_player_id"]].rename(
        columns={"us_player_id": "understat_player_id"}).drop_duplicates("tm_player_id")

    # fbref bridge (repaired)
    con = duckdb.connect(str(DUCKDB), read_only=True)
    xw = con.execute("select player_id, fbref_id, url_tmarkt from player_crosswalk").df()
    con.close()
    fb = repair_fbref_bridge(xw)

    m = (pl.merge(up, on="tm_player_id", how="left")
           .merge(fb, on="tm_player_id", how="left"))
    m["has_understat"] = m.understat_player_id.notna()
    m["has_fbref"] = m.fbref_id.notna()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_parquet(OUT, index=False)

    n = len(m)
    print(f"players_master rows (TM spine): {n:,}")
    print(f"  with understat_player_id:     {int(m.has_understat.sum()):,}  ({100*m.has_understat.mean():.1f}%)")
    print(f"  with fbref_id:                {int(m.has_fbref.sum()):,}  ({100*m.has_fbref.mean():.1f}%)")
    print(f"  with BOTH:                    {int((m.has_understat & m.has_fbref).sum()):,}")
    print(f"  contract_expiration present:  {100*m.contract_expiration_date.notna().mean():.1f}%")
    print(f"wrote {OUT}")
    return m


def load() -> pd.DataFrame:
    return pd.read_parquet(OUT)


# ------------------------------------------------------------------ check

def _check():
    # url repair: row with correct stored id, row with WRONG stored id, row w/ no url
    xw = pd.DataFrame([
        dict(player_id="92571", fbref_id="abc", url_tmarkt=".../spieler/92571"),
        dict(player_id="99999", fbref_id="def", url_tmarkt=".../spieler/12345"),  # stored wrong
        dict(player_id="555", fbref_id="ghi", url_tmarkt="no-id-here"),
        dict(player_id=None, fbref_id="jkl", url_tmarkt=".../spieler/777"),
    ])
    fb = repair_fbref_bridge(xw).set_index("fbref_id").tm_player_id.to_dict()
    assert fb["abc"] == 92571
    assert fb["def"] == 12345, "must prefer url spieler id over wrong stored id"
    assert fb["ghi"] == 555, "fall back to stored id when url has none"
    assert fb["jkl"] == 777, "url id used when stored is null"
    print("ok — fbref bridge repair prefers url spieler id, falls back cleanly")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
