"""data_index — the single human-readable map of every dataset on disk.

Complements `warehouse.py` (the queryable DuckDB of canonical tables): this renders
DATA_INDEX.md — every dataset grouped by domain, with its producer module, upstream
source, licence, join key, freshness and on-disk size, scanned live so it never goes
stale. Row counts come from the warehouse views where a dataset is registered there.

    python3 -m ingest.data_index build     # (re)write DATA_INDEX.md
    python3 -m ingest.data_index           # self-check (registry matches disk)

The registry below is the organising content — provenance/licence/key can't be derived
from bytes. Sizes, file counts and mtimes ARE derived, so those never drift. Licence
codes track LICENCES.md; treat every row by its ORIGIN, not its mirror.
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
D = REPO / "data"
OUT = REPO / "DATA_INDEX.md"

# licence codes -> one-line meaning (see LICENCES.md for the full audit)
LICENCE = {
    "NC-understat": "Understat — non-commercial (owner e-mail), attribution",
    "NC-statsbomb": "StatsBomb — non-commercial user agreement + logo",
    "PROP-opta":    "FBref/Opta — proprietary, not licensable (remove for any product)",
    "TM-risk":      "Transfermarkt — CC0 mirror tag can't relicense TM's DB (commercial risk)",
    "CC-clubelo":   "ClubElo — free for research w/ attribution; commercial undocumented",
    "GAME-fifa":    "EA/FIFA game-derived — research/personal only, not for resale",
    "FACTS":        "factual figures (revenue) — usable, cite primary",
    "PROP-deloitte": "Deloitte Money League — proprietary report, cite; figures are facts",
    "OWN":          "own model output — yours",
    "MIXED":        "mixed upstreams — treat each by origin",
}

# status codes
# LIVE = refreshes upstream · FROZEN = static snapshot, no future data ·
# DERIVED = built from other rows here · OUTPUT = model result
REG = [
    # name, domain, glob, producer, source, licence, key, status, warehouse_view, note
    ("Understat shots", "xG / performance", "understat/shots.parquet", "ingest/understat.py",
     "worldfootballR_data (GitHub)", "NC-understat", "match_id+player", "FROZEN", "shots",
     "Big-5+RFPL 2014-Jan2025; parquet is the primary store (read_shots writes it)"),
    ("Understat shots (raw)", "xG / performance", "understat/*_shot_data.rds", "ingest/understat.py",
     "worldfootballR_data", "NC-understat", "-", "FROZEN", None, "one combined blob per league"),
    ("Selling-league shots", "xG / performance", "fbref_shots/shots_selling.parquet", "ingest/fbref_shots.py",
     "worldfootballR_data FBref", "PROP-opta", "tm_player_id", "FROZEN", "shots_selling",
     "Eredivisie/Portugal/Championship/Brazil; 82.7% TM-linked"),
    ("Selling-league shots (raw)", "xG / performance", "fbref_shots/*_match_shooting.rds", "ingest/fbref_shots.py",
     "worldfootballR_data", "PROP-opta", "-", "FROZEN", None, "raw match shooting .rds, 4 feeders"),
    ("FBref perf (221-col)", "xG / performance", "fbref/perf_player_season.parquet", "ingest/fbref_perf.py",
     "worldfootballR_data snapshot", "PROP-opta", "tm_player_id", "FROZEN", "fbref_perf",
     "frozen Opta snapshot, Big-5 2010-2022"),
    ("FBref defense/niche", "xG / performance", "fbref/{defensive,niche}_summary.parquet", "ingest/fbref_perf.py",
     "worldfootballR_data snapshot", "PROP-opta", "tm_player_id", "DERIVED", "fbref_defense",
     "per-90 defensive + niche stats extracted from perf"),
    ("StatsBomb events", "xG / performance", "statsbomb/*.csv", "ingest/statsbomb.py",
     "statsbomb/open-data", "NC-statsbomb", "match/player", "LIVE", None,
     "turnovers, lineups, player/team season; narrow elite coverage"),
    ("StatsBomb La Liga/Ronaldo", "xG / performance", "statsbomb/*.pkl", "ingest/statsbomb_laliga.py",
     "statsbomb/open-data", "NC-statsbomb", "-", "FROZEN", None, "shot pulls for validation"),
    ("StatsBomb event cache (raw)", "xG / performance",
     "statsbomb/{events,lineups,matches,ronaldo_cache,laliga_cache}/**",
     "ingest/statsbomb.py", "statsbomb/open-data", "NC-statsbomb", "-", "FROZEN", None,
     "~120MB raw event/360/lineup JSON caches from open-data"),
    ("FBref turnover snapshot", "xG / performance", "fbref_snapshot/*.rds", "ingest/fbref_snapshot.py",
     "worldfootballR_data", "PROP-opta", "-", "FROZEN", None, "dispossessed+miscontrols, Big-5 2017-2022"),

    ("Transfermarkt players", "transfers / money", "transfermarkt/players.csv.gz", "ingest/transfermarkt.py",
     "dcaribou R2 (CC0 tag)", "TM-risk", "player_id", "LIVE", None, "50k players; MV, contract, agent, physical"),
    ("TM valuations", "transfers / money", "transfermarkt/player_valuations.csv.gz", "ingest/transfermarkt.py",
     "dcaribou R2", "TM-risk", "player_id+date", "LIVE", "valuations", "507k rows, 2000-2026, PIT market value"),
    ("TM transfers/fees", "transfers / money", "transfermarkt/transfers.csv.gz", "ingest/transfermarkt.py",
     "dcaribou R2", "TM-risk", "player_id+date", "LIVE", None, "thin prep table; raw below is denser"),
    ("TM raw (dated fees + PIT contracts)", "transfers / money", "transfermarkt/raw/raw_*.parquet", "ingest/tm_raw.py",
     "dcaribou RAW via DVC", "TM-risk", "player_id", "LIVE", None, "87k dated events, PIT contract expiries"),
    ("TM minutes/lineups", "transfers / money", "transfermarkt/{appearances,game_lineups,games}.csv.gz",
     "ingest/transfermarkt.py", "dcaribou R2", "TM-risk", "game+player", "LIVE", None,
     "726k appearances, lineups (starter/sub), 113MB lineups"),
    ("TM big-5 fees/vals (frozen)", "transfers / money", "transfermarkt/big*.rds", "ingest/transfermarkt.py",
     "worldfootballR_data", "TM-risk", "player_url", "FROZEN", None,
     "big_5_transfers + big5_player_vals; historical fees <=2022/23 for money/fees.py"),
    ("TM raw harvest cache (JSON)", "transfers / money", "transfermarkt/raw/**", "ingest/tm_raw.py",
     "dcaribou RAW via DVC", "TM-risk", "player_id", "LIVE", None,
     "~220MB DVC-pulled api transfers + scraper players JSON; source for raw_*.parquet"),
    ("Canonical transfers", "transfers / money", "merged/transfers_canonical.parquet", "ingest/merge.py",
     "merged estates", "MIXED", "transfer_id", "DERIVED", "transfers_canonical",
     "124k, deduped, leakage-safe; the money-layer backbone"),
    ("Money outputs", "transfers / money", "money/*.csv", "money/*.py",
     "model", "OWN", "-", "OUTPUT", None, "fee_ranker, scout board, backtests, calibrations"),

    ("Players master", "identity / master", "master/players_master.parquet", "ingest/players_master.py",
     "TM + crosswalks", "MIXED", "tm_player_id", "DERIVED", "players_master",
     "one row/player + every foreign id (fbref/understat/sofifa)"),
    ("Contracts", "identity / master", "master/contracts.parquet", "ingest/contracts.py",
     "TM players.csv", "TM-risk", "tm_player_id", "DERIVED", "contracts",
     "CURRENT expiry snapshot (not PIT); for amortisation of prospective signings"),
    ("Injuries / durability", "identity / master", "master/injuries.parquet", "ingest/injuries.py",
     "salimt/football-datasets", "TM-risk", "tm_player_id", "DERIVED", "injuries",
     "34.5k players; availability multiplier + spells_before() PIT-safe"),
    ("Injuries (raw spells)", "identity / master", "injuries/player_injuries.csv", "ingest/injuries.py",
     "salimt/football-datasets", "TM-risk", "tm_player_id", "FROZEN", None,
     "143k raw spells; source for the durability summary"),
    ("Crosswalks", "identity / master", "crosswalk/*.csv", "ingest/crosswalk_players.py",
     "Understat<->TM match", "MIXED", "us_id<->tm_id", "DERIVED", "crosswalk_players",
     "6.4k player + 18.9k match links, 100% matched"),

    ("Wages (FIFA prior)", "wages", "wages/wages_fifa.parquet", "ingest/wages_fifa.py",
     "EA/FIFA 20-21 (GitHub)", "GAME-fifa", "tm_player_id", "DERIVED", "wages_fifa",
     "10.2k players, era-consistent blend; grade-C real signal"),
    ("FIFA raw", "wages", "wages/fifa_players_*.csv", "ingest/wages_fifa.py",
     "ifrankandrade (GitHub raw)", "GAME-fifa", "sofifa_id", "FROZEN", None, "FIFA 17-21 player DB (extended 2026-07)"),
    ("Wages (Capology real)", "wages", "wages/capology.csv", "ingest/wages_capology.py",
     "capology.com (personal-use)", "TM-risk", "tm_player_id", "LIVE", None,
     "14.6k players, 8 leagues 2013-2026, REAL salaries; grade-B, wired into estimate_wage"),
    ("Wages Capology (full history)", "wages", "wages/capology_all_seasons.parquet", "ingest/wages_capology.py",
     "capology.com", "TM-risk", "tm_player_id+season", "LIVE", None, "64.7k rows, per-season history"),
    ("Wages FIFA time-series", "wages", "wages/wages_fifa_timeseries.parquet", "ingest/wages_fifa.py",
     "EA/FIFA 17-21", "GAME-fifa", "tm_player_id+year", "DERIVED", None, "40.3k rows, per-year wage panel"),

    ("ClubElo ratings", "strength", "strength/clubelo_history.csv", "ingest/strength.py",
     "api.clubelo.com (now live)", "CC-clubelo", "club+date", "LIVE", "clubelo_history",
     "771k rows; history to ~1946 via the now-reachable API"),
    ("ClubElo per-club history", "strength", "strength/history/*.csv", "ingest/strength.py",
     "api.clubelo.com", "CC-clubelo", "club", "LIVE", None, "one CSV per club (~230 clubs)"),
    # (removed 2026-07-12) clubelo-club-rankings.csv stale GitHub mirror — deleted in the
    #   disk clean, superseded by the live api.clubelo.com pull (ClubElo ratings, above).
    ("League strength fit", "strength", "league_strength.csv", "impact/leagues.py",
     "fitted from shots", "OWN", "league-pair", "OUTPUT", None, "descriptive only (failed the predictor gate)"),

    ("Defensive value layer", "xG / performance", "impact/defensive_value.parquet", "ingest/defensive_value.py",
     "FBref defensive_summary", "PROP-opta", "tm_player_id", "DERIVED", None,
     "14.6k player-seasons, Big-5 2018-2025; off-ball box-score composite, grade-C, unitless until calibrated"),
    ("xT weights (StatsBomb)", "xG / performance", "impact/xt_weights.json", "ingest/xt.py",
     "StatsBomb EPL 2015/16", "NC-statsbomb", "-", "DERIVED", None,
     "self-fit xT surface + per-action value weights (prog pass/carry, final-third); feeds possession_value"),
    ("Possession value layer", "xG / performance", "impact/possession_value.parquet", "ingest/possession_value.py",
     "FBref niche × xT weights", "PROP-opta", "tm_player_id", "DERIVED", None,
     "14.6k player-seasons; xT-weighted buildup progression, grade-B. DESCRIPTIVE — failed NPV gate, scouting flag only"),
    ("Club revenue (Deloitte)", "transfers / money", "money/club_revenue.parquet", "ingest/club_revenue.py",
     "Deloitte Money League (PDF)", "PROP-deloitte", "to_club_id", "DERIVED", None,
     "matchday/broadcast/commercial split; Stage-11 buyer-dispersion data (POC: COVID season)"),

    ("Coverage / panels", "analysis artifacts", "{coverage.csv,stage4/panel.csv,aging/curves.csv}",
     "ingest/coverage.py + validate", "derived", "OWN", "-", "DERIVED", None,
     "Stage-1 coverage, Stage-4 mover panel, age curves"),
    ("Warehouse", "unified", "warehouse.duckdb", "ingest/warehouse.py",
     "views over the above", "OWN", "-", "DERIVED", None,
     "one DuckDB; views (always fresh) + leak-guarded link table"),
]

_DOMAIN_ORDER = ["xG / performance", "transfers / money", "identity / master", "wages",
                 "strength", "analysis artifacts", "unified"]


def _scan(glob_expr: str):
    """Sum size + count files + newest mtime for a path/brace-glob under data/.

    Supports {a,b} brace expansion and a trailing '/**' meaning 'every file under
    this directory, recursively' (for raw caches with nested per-season folders).
    """
    # expand simple {a,b} braces into multiple globs
    exprs = [glob_expr]
    while any("{" in e for e in exprs):
        out = []
        for e in exprs:
            if "{" in e:
                pre, rest = e.split("{", 1)
                opts, post = rest.split("}", 1)
                out += [f"{pre}{o}{post}" for o in opts.split(",")]
            else:
                out.append(e)
        exprs = out
    files = []
    for e in exprs:
        if e.endswith("/**"):                       # recurse a directory subtree
            d = D / e[:-3]
            files += [f for f in d.rglob("*")] if d.exists() else []
        elif "/" in e:
            base, pat = e.rsplit("/", 1)
            files += list((D / base).glob(pat))
        else:
            files += list(D.glob(e))
    files = [f for f in files if f.is_file()]
    size = sum(f.stat().st_size for f in files)
    mtime = max((f.stat().st_mtime for f in files), default=0)
    return size, len(files), mtime


def _rows(view):
    if not view or not WAREHOUSE_ROWS:
        return None
    return WAREHOUSE_ROWS.get(view)


WAREHOUSE_ROWS = {}


def _load_warehouse_rows():
    wh = D / "warehouse.duckdb"
    if not wh.exists():
        return {}
    try:
        import duckdb
        con = duckdb.connect(str(wh), read_only=True)
        views = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables").fetchall()]
        out = {}
        for v in views:
            try:
                out[v] = con.execute(f"SELECT count(*) FROM {v}").fetchone()[0]
            except Exception:
                pass
        con.close()
        return out
    except Exception:
        return {}


def _fmt_size(b):
    return f"{b/1048576:.1f}MB" if b >= 1048576 else f"{b/1024:.0f}KB" if b else "—"


def _fmt_date(ts):
    return dt.date.fromtimestamp(ts).isoformat() if ts else "—"


def render() -> str:
    global WAREHOUSE_ROWS
    WAREHOUSE_ROWS = _load_warehouse_rows()
    today = dt.date.today().isoformat()

    total_size = missing = 0
    by_domain = {d: [] for d in _DOMAIN_ORDER}
    for row in REG:
        name, domain, glob, producer, source, lic, key, status, view, note = row
        size, nfiles, mtime = _scan(glob)
        if nfiles == 0:
            missing += 1
        total_size += size
        by_domain.setdefault(domain, []).append(
            dict(name=name, size=size, nfiles=nfiles, mtime=mtime, producer=producer,
                 source=source, lic=lic, key=key, status=status, rows=_rows(view), note=note))

    L = []
    L.append("# DATA INDEX — every dataset, mapped\n")
    L.append(f"*Generated {today} by `ingest/data_index.py` (re-run `python3 -m ingest.data_index build`). "
             "Sizes/dates scanned live from disk; row counts from the warehouse. The single map of "
             "all data — see `warehouse.py` to query it, `LICENCES.md` for the full licence audit, "
             "`DATA_SOURCES.md` for source detail.*\n")
    nrows = sum(r["rows"] or 0 for d in by_domain.values() for r in d)
    L.append(f"**{sum(len(v) for v in by_domain.values())} datasets · {_fmt_size(total_size)} on disk · "
             f"{len(WAREHOUSE_ROWS)} warehouse tables · {nrows:,} rows registered.**\n")
    L.append("Status: **LIVE** refreshes upstream · **FROZEN** static snapshot · "
             "**DERIVED** built from other rows · **OUTPUT** model result.\n")

    for domain in _DOMAIN_ORDER:
        rows = by_domain.get(domain)
        if not rows:
            continue
        L.append(f"\n## {domain}\n")
        L.append("| Dataset | Rows | Size | Status | Key | Producer | Source | Licence | Updated |")
        L.append("|---|--:|--:|---|---|---|---|---|---|")
        for r in rows:
            flag = " ⚠️MISSING" if r["nfiles"] == 0 else ""
            rows_s = f"{r['rows']:,}" if r["rows"] else "—"
            L.append(f"| **{r['name']}**{flag} | {rows_s} | {_fmt_size(r['size'])} | {r['status']} | "
                     f"`{r['key']}` | `{r['producer']}` | {r['source']} | {r['lic']} | {_fmt_date(r['mtime'])} |")
        for r in rows:
            if r["note"]:
                L.append(f"- *{r['name']}* — {r['note']}")

    L.append("\n## Licence codes\n")
    for code, meaning in LICENCE.items():
        L.append(f"- **{code}** — {meaning}")

    L.append("\n## Querying\n")
    L.append("```python\nfrom ingest import warehouse\ncon = warehouse.connect()          "
             "# read-only DuckDB\ncon.execute('SELECT * FROM injuries LIMIT 5').df()\n"
             "# joins on tm_player_id: players_master ⋈ contracts ⋈ injuries ⋈ wages_fifa\n```")
    L.append("\n*Commercial note: most upstreams are non-commercial / proprietary / DB-risk "
             "(see LICENCES.md). Clean-to-ship: own model outputs, ClubElo (attribution), revenue facts.*")
    return "\n".join(L) + "\n"


def _folder(glob_expr: str) -> str:
    """Top-level data/ folder a dataset lives in ('.' for files directly under data/)."""
    seg = glob_expr.split("/", 1)[0]
    # bare filename or brace over root files -> lives directly in data/
    return "." if ("." in seg or "{" in seg) and "/" not in glob_expr else seg


def _is_raw(name: str, note: str) -> bool:
    hay = f"{name} {note}".lower()
    return any(w in hay for w in ("raw", "cache", "stale", "mirror"))


def readmes():
    """Write a README.md into each data/ subfolder — a pivot of REG by folder, so a
    model can learn a folder's contents from ~1KB instead of loading the blobs. Kept in
    sync by regenerating from the same registry as DATA_INDEX.md.
    """
    global WAREHOUSE_ROWS
    WAREHOUSE_ROWS = _load_warehouse_rows()
    by_folder = {}
    for row in REG:
        by_folder.setdefault(_folder(row[2]), []).append(row)

    written = 0
    for folder, rows in by_folder.items():
        if folder == ".":            # root files are few + in DATA_INDEX; data/README.md is hand-kept
            continue
        d = D / folder
        if not d.exists():
            continue
        # folder totals span EVERYTHING on disk (rglob); the table rows below are only the
        # REGISTERED datasets (_scan by glob). The gap is deliberate and load-bearing — it's
        # what surfaces unregistered bulk (e.g. capology_raw/ HTML) as "size not in the table".
        fsize = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        nfiles = sum(1 for f in d.rglob("*") if f.is_file())
        title = folder
        L = [f"# data/{title}\n",
             f"*Auto-generated by `python3 -m ingest.data_index readmes` — do not edit by hand. "
             f"{_fmt_size(fsize)} · {nfiles} files. Full map: `../DATA_INDEX.md`. "
             f"Query via `ingest/warehouse.py`, not by reading these files.*\n"]
        if nfiles > 100 or fsize > 100 * 1048576:
            L.append(f"> ⚠️ **Heavy folder ({nfiles} files, {_fmt_size(fsize)}).** Most of the bulk is "
                     "raw/re-fetchable cache — do NOT `grep`/`ls -R`/read it to understand the data. "
                     "Read the table below and the derived parquet instead.\n")
        L.append("| Dataset | Size | Status | Producer | What it is |")
        L.append("|---|--:|---|---|---|")
        for name, domain, glob, producer, source, lic, key, status, view, note in rows:
            size, nf, _ = _scan(glob)
            flag = " 🗑️raw" if _is_raw(name, note or "") else ""
            L.append(f"| **{name}**{flag} | {_fmt_size(size)} | {status} | `{producer}` | {note or '—'} |")
        if any(_is_raw(n, no or "") for n, _, _, _, _, _, _, _, _, no in rows):
            L.append("\n🗑️raw = re-fetchable source blob (idempotent `download()` in the producer). "
                     "Safe to delete to reclaim disk; re-fetches on next run.")
        (d / "README.md").write_text("\n".join(L) + "\n")
        written += 1
    print(f"wrote {written} folder READMEs under data/")


def build():
    OUT.write_text(render())
    wh = _load_warehouse_rows()
    total = sum(_scan(r[2])[0] for r in REG)
    missing = [r[0] for r in REG if _scan(r[2])[1] == 0]
    print(f"wrote {OUT}")
    print(f"  {len(REG)} datasets · {total/1048576:.0f}MB · {len(wh)} warehouse tables")
    if missing:
        print(f"  ⚠️ {len(missing)} registered but MISSING on disk: {', '.join(missing)}")
    else:
        print("  all registered datasets present on disk")


def _check():
    # brace expansion works
    size, n, _ = _scan("understat/shots.parquet")
    assert n == 1 and size > 0, ("shots.parquet should exist", n, size)
    # every registered dataset resolves to >=1 file on disk (catches drift/typos)
    absent = [(r[0], r[2]) for r in REG if _scan(r[2])[1] == 0]
    assert not absent, f"registered datasets missing on disk: {absent}"
    # domains all known
    assert all(r[1] in _DOMAIN_ORDER for r in REG), "unknown domain in registry"
    # licences all defined
    assert all(r[5] in LICENCE or r[5] in ("derived",) for r in REG), \
        [r[5] for r in REG if r[5] not in LICENCE and r[5] != "derived"]
    print(f"ok — {len(REG)} datasets all present, domains + licences well-formed")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    elif "readmes" in sys.argv[1:]:
        readmes()
    else:
        _check()
