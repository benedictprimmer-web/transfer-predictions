"""Declarative source registry for the harvest harness.

One `Source` per open-redistribution feed. URL templates and cache dirs are
imported from the module that owns each source (a URL change stays a one-place
edit). Two kinds:
  * "http" — plain files fetched by conditional GET (dcaribou prep csv.gz).
  * "dvc"  — dcaribou RAW via the DVC store; refresh delegates to ingest.tm_raw.

Governing rule: OPEN REDISTRIBUTIONS ONLY (CC0 / GitHub caches). No TM/FBref scraping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import ingest.transfermarkt as tm
from money.fees import FEATURES


@dataclass(frozen=True)
class Source:
    key: str
    licence: str
    cadence: str                     # "weekly" | "daily" | "static"
    feeds: tuple                     # canonical field(s) this source supplies
    kind: str = "http"               # "http" | "dvc"
    cache_dir: Path | None = None
    url_template: str = ""           # http: one {} slot per artifact
    artifacts: tuple = ()            # http: artifact names
    filename: Callable[[str], str] = lambda a: f"{a}.csv.gz"
    min_rows: int = 0                # row-count floor (0 = raw-only / not gated)

    def url(self, artifact: str) -> str:
        return self.url_template.format(artifact)

    def path(self, artifact: str) -> Path:
        return self.cache_dir / self.filename(artifact)


REGISTRY: dict[str, Source] = {
    "transfermarkt": Source(
        key="transfermarkt", licence="CC0", cadence="weekly",
        feeds=("transfers", "player_valuations", "players", "clubs", "minutes"),
        kind="http", cache_dir=tm.DATA_DIR, url_template=tm._R2, artifacts=tm.TABLES,
        min_rows=500),
    "tm_raw": Source(
        key="tm_raw", licence="CC0", cadence="weekly",
        feeds=("exact_dates", "recent_fees", "contract_years_remaining"),
        kind="dvc"),
    # understat / clubelo feed the impact side (a separate refresh) — registered for
    # completeness; the canonical fee pipeline is gated on the two above.
}

# Downstream contract the rebuilt canonical must satisfy (checked as a promotion gate).
# These are the columns money.fees.load_canonical + ingest.merge produce/consume.
CANONICAL_REQUIRED = {
    "player_id", "player_name", "season", "fee_eur", "fee_suspect", "market_value_eur",
    "player_age", "pos_group", "from_league", "to_league", "to_club_name",
    "mv_is_point_in_time", "date_source", "contract_years_remaining",
}
CANONICAL_NUMERIC = {"market_value_eur", "player_age", "fee_eur"}


def _check():
    assert "transfermarkt" in REGISTRY and REGISTRY["transfermarkt"].artifacts
    s = REGISTRY["transfermarkt"]
    assert s.url("transfers").endswith("transfers.csv.gz")
    assert s.path("transfers").name == "transfers.csv.gz"
    assert REGISTRY["tm_raw"].kind == "dvc"
    print(f"ok — {len(REGISTRY)} sources; transfermarkt has {len(s.artifacts)} artifacts")


if __name__ == "__main__":
    _check()
