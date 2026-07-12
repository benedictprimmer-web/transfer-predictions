"""Harvest dcaribou RAW Transfermarkt data (CC0) — the dated fees + point-in-time
contracts the prep tables lack.

The prep `transfers.csv.gz` is thin (4,345 players, 2,584 fees). The RAW data, on the
SAME public CC0 R2 host via dcaribou's DVC store, is dense and dated:

  * transfermarkt-api `transfers/<season>.json`  (JSONL, ~50k events/season)
      -> tidy_raw_transfers(): player_id, transfer_date (exact ISO), from/to club id+name,
         fee_eur, fee_type, market_value_eur, season. Recent + marquee (Bellingham €127m).
  * transfermarkt-scraper `.../players.json.gz` per season (JSONL, one player/line)
      -> tidy_contracts(): player_id, season, contract_expires (as-of THAT season) — a
         leakage-safe point-in-time contract panel (`is_point_in_time=True`).

NOT scraping: dcaribou already redistributes this under CC0. We resolve the CURRENT version
through the GitHub `.dvc` pointer, so every pull is the freshest crawl (re-run Tue/Fri).

    python -m ingest.tm_raw --seasons 2023 2024   # fetch + build + report
    python -m ingest.tm_raw --check               # offline parser self-check
"""
from __future__ import annotations

import gzip
import json
import re
import urllib.request
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "transfermarkt" / "raw"
_GH = "https://raw.githubusercontent.com/dcaribou/transfermarkt-datasets/master/data/raw/{}.dvc"
_R2_DVC = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/dvc/files/md5/{}/{}"

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _get(url: str, timeout: int = 120) -> bytes:
    """Fetch with a browser UA — the R2/Cloudflare edge 403s default Python-urllib."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=timeout).read()


_VEREIN = re.compile(r"/verein/(\d+)")
_SPIELER = re.compile(r"/spieler/(\d+)")
_MONEY = re.compile(r"€\s*([\d.]+)\s*(bn|m|k)?", re.I)
_MULT = {"bn": 1e9, "m": 1e6, "k": 1e3, None: 1.0}


# ─────────────────────────── DVC resolver ───────────────────────────

def _dir_md5(dataset: str) -> str:
    """Current `<md5>.dir` for a raw dataset, from its GitHub .dvc pointer (stays fresh)."""
    txt = _get(_GH.format(dataset), timeout=30).decode()
    m = re.search(r"md5:\s*([0-9a-f]+)\.dir", txt)
    if not m:
        raise RuntimeError(f"no .dir md5 in {dataset}.dvc")
    return m.group(1)


def _fetch_dvc(md5: str, is_dir: bool = False) -> bytes:
    # DVC store: directory objects carry a .dir suffix, leaf files don't.
    url = _R2_DVC.format(md5[:2], md5[2:]) + (".dir" if is_dir else "")
    return _get(url)


def _listing(dataset: str) -> list[dict]:
    """[{md5, relpath}, ...] for every file in the raw dataset."""
    return json.loads(_fetch_dvc(_dir_md5(dataset), is_dir=True))


def download_raw(dataset: str, pattern: str, force: bool = False) -> list[Path]:
    """Fetch raw files whose relpath matches `pattern` (regex) -> RAW_DIR/<dataset>/<basename>.
    Idempotent: skips files already cached unless force."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    rx = re.compile(pattern)
    for e in _listing(dataset):
        if not rx.search(e["relpath"]):
            continue
        dest = RAW_DIR / dataset / e["relpath"]     # preserve relpath (season lives in the dir)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if force or not dest.exists():
            dest.write_bytes(_fetch_dvc(e["md5"]))
        out.append(dest)
    return out


# ─────────────────────────── parsers ───────────────────────────

def parse_money(s) -> float | None:
    """'€127.00m'->127e6, '€180k'->180e3, 'free transfer'->0, '-'/loan/None->None."""
    s = (s or "").strip().lower()
    if not s or s in ("-", "?", "n/a"):
        return None
    m = _MONEY.search(s)
    if m:
        return float(m.group(1)) * _MULT[m.group(2).lower() if m.group(2) else None]
    if "free" in s:
        return 0.0
    return None   # 'end of loan', 'loan transfer', 'draft' -> no fee


def fee_type(s) -> str:
    s = (s or "").strip().lower()
    if "loan" in s and _MONEY.search(s):
        return "loan_fee"
    if "loan" in s:
        return "loan"
    if "free" in s:
        return "free"
    if _MONEY.search(s):
        return "fee"
    if "draft" in s:
        return "draft"
    return "unknown"


def _club_id(href) -> int | None:
    m = _VEREIN.search(href or "")
    return int(m.group(1)) if m else None


def _read_jsonl(path: Path):
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def tidy_raw_transfers(paths: list[Path]) -> pd.DataFrame:
    """Raw api transfers.json (list of files) -> one dated, fee-parsed row per event."""
    rows = []
    for p in paths:
        for rec in _read_jsonl(p):
            pid = rec.get("player_id")
            for t in (rec.get("response", {}) or {}).get("transfers", []) or []:
                date = t.get("dateUnformatted")
                if not date:
                    continue
                feestr = t.get("fee")
                rows.append({
                    "player_id": pid,
                    "transfer_date": date,
                    "season": t.get("season"),
                    "from_club_id": _club_id((t.get("from") or {}).get("href")),
                    "from_club_name": (t.get("from") or {}).get("clubName"),
                    "to_club_id": _club_id((t.get("to") or {}).get("href")),
                    "to_club_name": (t.get("to") or {}).get("clubName"),
                    "fee_eur": parse_money(feestr),
                    "fee_type": fee_type(feestr),
                    "market_value_eur": parse_money(t.get("marketValue")),
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["player_id"] = pd.to_numeric(df.player_id, errors="coerce").astype("Int64")
    df["transfer_date"] = pd.to_datetime(df.transfer_date, errors="coerce")
    # a player's history repeats across seasonal snapshots -> dedup on the real event
    return df.dropna(subset=["transfer_date"]).drop_duplicates(
        ["player_id", "transfer_date", "to_club_id"]).reset_index(drop=True)


def tidy_contracts(paths_with_season: list[tuple[Path, int]]) -> pd.DataFrame:
    """Scraper players.json.gz per season -> point-in-time contract expiry.
    `paths_with_season`: [(path, season_year), ...]. Returns player_id, season,
    contract_expires (date), is_point_in_time=True."""
    rows = []
    for p, season in paths_with_season:
        for rec in _read_jsonl(p):
            m = _SPIELER.search(rec.get("href", ""))
            if not m:
                continue
            exp = (rec.get("contract_expires") or "").strip()
            rows.append({
                "player_id": int(m.group(1)),
                "season": season,
                "contract_expires": None if exp in ("", "-") else exp,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["contract_expires"] = pd.to_datetime(df.contract_expires, errors="coerce")
    df["is_point_in_time"] = True
    return df.drop_duplicates(["player_id", "season"]).reset_index(drop=True)


# ─────────────────────────── orchestration ───────────────────────────

def harvest(seasons=(2023, 2024), force: bool = False) -> dict:
    """Fetch + parse raw api transfers (dated fees) and scraper contracts for `seasons`.
    Writes two parquets to data/transfermarkt/raw/ and returns the frames + a report."""
    yr = "|".join(str(s) for s in seasons)
    tr_paths = download_raw("transfermarkt-api", rf"^({yr})/transfers\.json$", force)
    transfers = tidy_raw_transfers(tr_paths)

    sc_files = download_raw("transfermarkt-scraper", rf"^({yr})/players\.json\.gz$", force)
    # relpath preserved -> season is the parent dir name (e.g. .../2024/players.json.gz)
    pws = [(p, int(p.parent.name)) for p in sc_files if p.parent.name.isdigit()]
    contracts = tidy_contracts(pws)

    out = {}
    if not transfers.empty:
        transfers.to_parquet(RAW_DIR / "raw_transfers.parquet", index=False)
        out["transfers"] = transfers
    if not contracts.empty:
        contracts.to_parquet(RAW_DIR / "raw_contracts.parquet", index=False)
        out["contracts"] = contracts
    _report(transfers, contracts)
    return out


def _report(transfers, contracts):
    print("=" * 64)
    print("dcaribou RAW harvest")
    print("=" * 64)
    if transfers is not None and not transfers.empty:
        fee = transfers.fee_type.eq("fee").sum()
        print(f"  dated transfer events   {len(transfers):>8,}")
        print(f"  with a real fee         {fee:>8,}  "
              f"(dmin {transfers.transfer_date.min().date()} .. {transfers.transfer_date.max().date()})")
        print(f"  distinct players        {transfers.player_id.nunique():>8,}")
    else:
        print("  transfers: none fetched")
    if contracts is not None and not contracts.empty:
        pit = contracts.contract_expires.notna().sum()
        print(f"  contract snapshots      {len(contracts):>8,}  "
              f"({pit:,} with a dated expiry, point-in-time)")
    else:
        print("  contracts: none fetched")


def _check():
    assert parse_money("€127.00m") == 127_000_000
    assert parse_money("€180k") == 180_000
    assert parse_money("free transfer") == 0.0
    assert parse_money("End of loan") is None and parse_money("-") is None
    assert fee_type("€2.00m loan fee") == "loan_fee"
    assert fee_type("loan transfer") == "loan" and fee_type("free transfer") == "free"
    assert fee_type("€90.00m") == "fee"
    assert _club_id("/karpaty-lviv/transfers/verein/85465/saison_id/2025") == 85465
    assert _SPIELER.search("/x/profil/spieler/50487").group(1) == "50487"
    # end-to-end parse on a synthetic api record (no network)
    rec = {"player_id": 581678, "response": {"transfers": [
        {"dateUnformatted": "2023-07-01", "fee": "€127.00m", "marketValue": "€120.00m",
         "season": "23/24", "from": {"href": "/verein/16/", "clubName": "Dortmund"},
         "to": {"href": "/verein/418/", "clubName": "Real Madrid"}}]}}
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write(json.dumps(rec) + "\n")
        tmp = Path(f.name)
    df = tidy_raw_transfers([tmp])
    assert len(df) == 1 and df.fee_eur.iloc[0] == 127_000_000
    assert df.to_club_name.iloc[0] == "Real Madrid" and str(df.transfer_date.iloc[0].date()) == "2023-07-01"
    print("ok — money/fee-type/id parsers + end-to-end api parse correct")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        args = sys.argv[1:]
        seasons = tuple(int(a) for a in args[args.index("--seasons") + 1:]) if "--seasons" in args else (2023, 2024)
        harvest(seasons)
