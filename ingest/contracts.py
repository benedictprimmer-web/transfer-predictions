"""contracts — current contract/agent/physical snapshot from players.csv.gz.

Audit finding L6: Estate B's `contracts` table is 0 rows, but Estate A's
players.csv already carries contract_expiration_date (63%), agent_name (53%),
foot (88%), height (91%). This materializes them.

CRITICAL — this is a CURRENT snapshot, NOT point-in-time. players.csv holds one
`contract_expiration_date` per player (today's contract). ingest/merge.py
correctly refuses to use it on *historical* deals (it would leak the future).
So: use this for forward-looking work only — free-agent / expiring-contract
scouting, and amortisation of a *prospective* signing (years left on the deal
you'd be buying out). Never join it to a past transfer as a feature.

Output: data/master/contracts.parquet
  tm_player_id, contract_expiration_date, contract_years_left, is_free_agent,
  agent_name, foot, height_cm, sub_position, snapshot_note
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ESTATE_A = REPO / "data" / "transfermarkt"
OUT = REPO / "data" / "master" / "contracts.parquet"

# Estate A is a live dump; "today" for years-left is its newest valuation date.
# ponytail: newest player_valuations date as the clock; exact vs asof-today is
# within a month and this table is explicitly a snapshot, not point-in-time.
_ASOF = "2026-02-27"


def tidy_contracts(players: pd.DataFrame, asof: str = _ASOF) -> pd.DataFrame:
    p = players
    exp = pd.to_datetime(p.contract_expiration_date, errors="coerce")
    now = pd.Timestamp(asof)
    years_left = (exp - now).dt.days / 365.25
    out = pd.DataFrame({
        "tm_player_id": p.player_id.astype("int64"),
        "contract_expiration_date": exp.dt.date.astype("object"),
        "contract_years_left": years_left.round(2),
        "is_free_agent": exp.notna() & (exp < now),
        "agent_name": p.get("agent_name"),
        "foot": p.get("foot"),
        "height_cm": pd.to_numeric(p.get("height_in_cm"), errors="coerce"),
        "sub_position": p.get("sub_position"),
        "snapshot_note": "current snapshot; NOT point-in-time — do not join to past transfers",
    })
    # negative years-left that isn't a real expiry (parse noise) -> clip at 0 floor kept as free agent
    return out.reset_index(drop=True)


def build() -> pd.DataFrame:
    p = pd.read_csv(ESTATE_A / "players.csv.gz", compression="gzip", low_memory=False,
                    usecols=["player_id", "contract_expiration_date", "agent_name",
                             "foot", "height_in_cm", "sub_position"])
    c = tidy_contracts(p)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c.to_parquet(OUT, index=False)

    n = len(c)
    have = c.contract_expiration_date.notna()
    print(f"contracts rows:               {n:,}")
    print(f"  contract_expiration present: {100*have.mean():.1f}%")
    print(f"  agent_name present:          {100*c.agent_name.notna().mean():.1f}%")
    print(f"  currently free agents:       {int(c.is_free_agent.sum()):,}")
    print(f"  expiring <=1yr (scout pool): {int(((c.contract_years_left>0)&(c.contract_years_left<=1)).sum()):,}")
    print(f"wrote {OUT}")
    return c


def load() -> pd.DataFrame:
    return pd.read_parquet(OUT)


# ------------------------------------------------------------------ check

def _check():
    p = pd.DataFrame([
        dict(player_id=1, contract_expiration_date="2028-06-30", agent_name="A",
             foot="right", height_in_cm=185, sub_position="Centre-Back"),
        dict(player_id=2, contract_expiration_date="2025-06-30", agent_name=None,  # past asof -> free
             foot="left", height_in_cm=170, sub_position="Left Winger"),
        dict(player_id=3, contract_expiration_date=None, agent_name="B",
             foot=None, height_in_cm=None, sub_position=None),
    ])
    c = tidy_contracts(p, asof="2026-02-27").set_index("tm_player_id")
    assert abs(c.loc[1].contract_years_left - 2.34) < 0.05, c.loc[1].contract_years_left
    assert c.loc[2].is_free_agent and not c.loc[1].is_free_agent
    assert not c.loc[3].is_free_agent  # unknown expiry != free agent
    assert pd.isna(c.loc[3].contract_expiration_date)
    print(c.to_string())
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
