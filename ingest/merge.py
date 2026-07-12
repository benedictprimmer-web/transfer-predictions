"""Merge the two data estates into one canonical, leakage-safe transfers table.

Two builds of this project exist:
  * Estate B  ~/Downloads/football-transfer-db/  -- a validated 16-table DuckDB.
    Rich, enriched transfers (league/country/top-5/age/pos + fee_suspect flags),
    but built under a sandbox network block: no exact dates, stops 2022, market
    value on only 40% of rows, and still carries 8,065 dup groups.
  * Estate A  ~/Transfer Predictions/data/transfermarkt/  -- the live raw dumps.
    The gold here is player_valuations.csv.gz: 507,815 point-in-time market
    values (2000->2026), which Estate B never got to use.

This module makes Estate B the enriched spine and fills it from Estate A:
  1. dedup the spine with the SAME fee-conflict-guarded logic Estate B shipped
     (apply_dedup_v2.py) -- never merge two distinct non-null fees;
  2. backfill exact `transfer_date` where the (thin) Estate A transfers slice
     covers it, else keep a window proxy date (date_source flags which);
  3. point-in-time MV fill: as-of the pre-window date, the last valuation
     STRICTLY BEFORE it (leakage-safe backward as-of) -> 40% -> ~78% coverage;
  4. extend past 2022 with Estate A's 2023+ rows enriched from clubs/players.

Honest ceilings, stated not hidden (see build_canonical()'s report):
  * exact dates cover only a sliver -- Estate A's transfers slice is 4.3k players,
    no marquee. Exact-date-at-scale is a real data gap (needs more sourcing).
  * recent-window FEE coverage is poor (Estate A transfers has ~2.6k fees total).
    The 2023+ extension mostly adds roster/MV, not trainable fees.
  * point-in-time CONTRACTS remain empty -- the only source (players.csv latest
    contract) is not point-in-time and would leak on historical deals.

    python -m ingest.merge            # build + write + coverage report
    python -m ingest.merge --check    # fast self-check on a synthetic frame
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ESTATE_A = REPO / "data" / "transfermarkt"                       # live raw dumps
ESTATE_B = Path(os.environ.get(
    "ESTATE_B_DIR", "/Users/benrimmer/Downloads/football-transfer-db"))
OUT = REPO / "data" / "merged" / "transfers_canonical.parquet"

BIG5_COMP = {"GB1": "Premier League", "ES1": "LaLiga", "IT1": "Serie A",
             "FR1": "Ligue 1", "L1": "Bundesliga"}


def _norm_club(s: str) -> str:
    """Same club normalizer Estate B's dedup used, so keys line up 1:1."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    for aff in (" fc", " cf", " ac", " sc", " ssc", " as", " rc", " cd", " ud",
                " afc", " sv", " vfb", " vfl", " calcio", "fc ", "cf ", "ac ",
                "as ", "sc ", "ss ", "rcd ", "real ", "club "):
        s = s.replace(aff, " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _dedup_spine(con, src_parquet: str) -> pd.DataFrame:
    """Estate B's fee-conflict-guarded dedup (apply_dedup_v2.py), on the parquet.

    Collapses (player_id, season, window, from_club, to_club) groups, but keeps
    rows apart when they carry two DIFFERENT non-null fees -- that signals two
    real deals (a multi-loan season), not a duplicate.
    """
    con.create_function("norm_club", _norm_club, ["VARCHAR"], "VARCHAR")
    return con.execute(f"""
    WITH keyed AS (
      SELECT *,
        CASE WHEN player_id IS NOT NULL
          THEN player_id||'|'||season||'|'||coalesce("window",'?')
               ||'|'||norm_club(from_club_name)||'|'||norm_club(to_club_name)
          ELSE transfer_uid END AS nkey,
        (CASE WHEN fee_eur IS NOT NULL THEN 4 ELSE 0 END
         + CASE WHEN market_value_eur IS NOT NULL THEN 3 ELSE 0 END
         + CASE WHEN player_nation IS NOT NULL THEN 1 ELSE 0 END) AS score
      FROM read_parquet('{src_parquet}')
    ),
    fee_conflict AS (
      SELECT nkey FROM keyed WHERE fee_eur IS NOT NULL
      GROUP BY nkey HAVING count(DISTINCT fee_eur) > 1
    ),
    merged AS (
      SELECT
        max(transfer_uid) AS transfer_uid, max(player_id) AS player_id,
        arg_max(player_name, score) AS player_name, max(player_age) AS player_age,
        arg_max(pos_group, score) AS pos_group, max(player_nation) AS player_nation,
        max(from_club_id) AS from_club_id, arg_max(from_club_name, score) AS from_club_name,
        arg_max(from_league, CASE WHEN from_league IS NOT NULL THEN score ELSE -1 END) AS from_league,
        arg_max(from_country, CASE WHEN from_country IS NOT NULL THEN score ELSE -1 END) AS from_country,
        max(to_club_id) AS to_club_id, arg_max(to_club_name, score) AS to_club_name,
        arg_max(to_league, CASE WHEN to_league IS NOT NULL THEN score ELSE -1 END) AS to_league,
        arg_max(to_country, CASE WHEN to_country IS NOT NULL THEN score ELSE -1 END) AS to_country,
        max(season) AS season, arg_max("window", CASE WHEN "window" IS NOT NULL THEN score ELSE -1 END) AS window,
        max(fee_eur) AS fee_eur, bool_and(fee_undisclosed) AS fee_undisclosed,
        arg_max(transfer_type, score) AS transfer_type, max(market_value_eur) AS market_value_eur,
        bool_or(fee_suspect) AS fee_suspect, bool_or(age_suspect) AS age_suspect,
        bool_or(fee_zero_suspect) AS fee_zero_suspect,
        bool_or(from_is_top5) AS from_is_top5, bool_or(to_is_top5) AS to_is_top5
      FROM keyed WHERE nkey NOT IN (SELECT nkey FROM fee_conflict)
      GROUP BY nkey
    ),
    passthrough AS (
      SELECT transfer_uid, player_id, player_name, player_age, pos_group, player_nation,
        from_club_id, from_club_name, from_league, from_country, to_club_id, to_club_name,
        to_league, to_country, season, "window", fee_eur, fee_undisclosed, transfer_type,
        market_value_eur, fee_suspect, age_suspect, fee_zero_suspect, from_is_top5, to_is_top5
      FROM keyed WHERE nkey IN (SELECT nkey FROM fee_conflict)
    )
    SELECT * FROM merged UNION ALL SELECT * FROM passthrough
    """).df()


def _proxy_date(season, window) -> pd.Series:
    """Window proxy: summer -> Aug 1 of season, winter -> Jan 20 of season+1.
    Deliberately pre/early-window so the as-of MV is knowable before the deal."""
    yr = pd.Series(pd.to_numeric(pd.Series(season).values, errors="coerce")).astype("Int64")
    win = pd.Series(window, dtype="object").astype(str).str.lower().str.contains("w").to_numpy()
    d = np.where(win, (yr + 1).astype(str) + "-01-20", yr.astype(str) + "-08-01")
    return pd.Series(pd.to_datetime(d, errors="coerce")).astype("datetime64[ns]")


def _asof_mv(rows: pd.DataFrame, vals: pd.DataFrame) -> pd.Series:
    """Last valuation STRICTLY BEFORE each row's date, per player (leakage-safe)."""
    L = rows.dropna(subset=["player_id", "date"]).copy()
    L["player_id"] = L["player_id"].astype("int64")
    m = pd.merge_asof(
        L.sort_values("date"),
        vals[["player_id", "vd", "mv"]].sort_values("vd"),
        left_on="date", right_on="vd", by="player_id", direction="backward",
        allow_exact_matches=False,   # strictly before -> no same-day leak
    )
    return m.set_index(L.sort_values("date").index)["mv"]


def _load_valuations(con) -> pd.DataFrame:
    v = con.execute(f"""
        SELECT player_id, strftime(CAST(date AS DATE),'%Y-%m-%d') AS d, market_value_in_eur AS mv
        FROM read_csv_auto('{ESTATE_A}/player_valuations.csv.gz', ignore_errors=true)
        WHERE market_value_in_eur > 0
    """).df()
    v["player_id"] = pd.to_numeric(v.player_id, errors="coerce")
    v["vd"] = pd.to_datetime(v.d, errors="coerce").astype("datetime64[ns]")
    return v.dropna(subset=["player_id", "vd"]).assign(player_id=lambda x: x.player_id.astype("int64"))


def _exact_dates(con) -> pd.DataFrame:
    """Estate A transfers slice: (player_id, to_club_id, year) -> exact transfer_date.
    Thin (4.3k players) but real where present."""
    a = con.execute(f"""
        SELECT player_id, to_club_id, CAST(transfer_date AS DATE) AS transfer_date
        FROM read_csv_auto('{ESTATE_A}/transfers.csv.gz', ignore_errors=true)
        WHERE player_id IS NOT NULL AND transfer_date IS NOT NULL
    """).df()
    a["player_id"] = pd.to_numeric(a.player_id, errors="coerce")
    a["to_club_id"] = pd.to_numeric(a.to_club_id, errors="coerce")
    a["transfer_date"] = pd.to_datetime(a.transfer_date, errors="coerce").astype("datetime64[ns]")
    a["yr"] = a.transfer_date.dt.year
    return a.dropna(subset=["player_id", "transfer_date"]).drop_duplicates(["player_id", "to_club_id", "yr"])


def _extension(con, vals: pd.DataFrame, seen_keys: set) -> pd.DataFrame:
    """Estate A transfers with year>=2023 not already in the Estate B spine.
    Enriched with age (players.date_of_birth) and league/top-5 (clubs comp id)."""
    ext = con.execute(f"""
        WITH cl AS (SELECT club_id, domestic_competition_id FROM read_csv_auto('{ESTATE_A}/clubs.csv.gz', ignore_errors=true))
        SELECT t.player_id, t.player_name, CAST(t.transfer_date AS DATE) AS transfer_date,
               t.from_club_id, t.from_club_name, t.to_club_id, t.to_club_name,
               t.transfer_fee AS fee_eur, t.market_value_in_eur AS market_value_eur,
               fc.domestic_competition_id AS from_comp, tc.domestic_competition_id AS to_comp,
               p.date_of_birth, p.sub_position, p.position
        FROM read_csv_auto('{ESTATE_A}/transfers.csv.gz', ignore_errors=true) t
        LEFT JOIN read_csv_auto('{ESTATE_A}/players.csv.gz', ignore_errors=true) p USING (player_id)
        LEFT JOIN cl fc ON t.from_club_id = fc.club_id
        LEFT JOIN cl tc ON t.to_club_id = tc.club_id
        WHERE t.player_id IS NOT NULL
          AND t.transfer_date BETWEEN DATE '2023-07-01' AND DATE '2026-08-31'
    """).df()
    if ext.empty:
        return ext
    ext["player_id"] = pd.to_numeric(ext.player_id, errors="coerce")
    ext["transfer_date"] = pd.to_datetime(ext.transfer_date, errors="coerce").astype("datetime64[ns]")
    ext["season"] = ext.transfer_date.dt.year
    dob = pd.to_datetime(ext.date_of_birth, errors="coerce")
    ext["player_age"] = ((ext.transfer_date - dob).dt.days / 365.25).round(1)
    ext["from_league"] = ext.from_comp.map(BIG5_COMP)
    ext["to_league"] = ext.to_comp.map(BIG5_COMP)
    ext["from_is_top5"] = ext.from_comp.isin(BIG5_COMP)
    ext["to_is_top5"] = ext.to_comp.isin(BIG5_COMP)
    ext = ext.dropna(subset=["player_id"]).copy()
    ext["player_id"] = ext.player_id.astype("int64")
    # drop any that collide with a spine key (player_id, to_club_id, year)
    key = list(zip(ext.player_id, pd.to_numeric(ext.to_club_id, errors="coerce"), ext.season))
    ext = ext[[k not in seen_keys for k in key]].copy()
    return ext


RAW_HARVEST = ESTATE_A / "raw"     # ingest.tm_raw output (dcaribou RAW via DVC)
# raw api fee_type -> spine transfer_type vocabulary (permanent/loan/free/end_of_loan/retirement)
_RAW_TYPE_MAP = {"fee": "permanent", "free": "free", "loan": "loan", "loan_fee": "loan"}


def _extension_from_raw(con, seen_keys: set) -> pd.DataFrame:
    """2023+ transfers straight from the dcaribou RAW harvest (ingest.tm_raw), not the thin
    Estate A prep table `_extension()` draws from. The prep table only has 2,584 fees total
    and misses ~99% of 2023-25 real-fee events as ROWS (they're not backfillable by
    `_enrich_from_raw` if the row never existed). Same age/league enrichment as `_extension`,
    keyed on the same TM player_id namespace (verified: raw/Estate A/B share player_id)."""
    tr_p = RAW_HARVEST / "raw_transfers.parquet"
    if not tr_p.exists():
        return pd.DataFrame()
    rt = pd.read_parquet(tr_p)
    rt = rt.dropna(subset=["player_id", "to_club_id", "transfer_date"]).copy()
    rt = rt[rt.transfer_date.between("2023-07-01", "2026-08-31")]
    rt = rt[rt.fee_type.isin(_RAW_TYPE_MAP)]                      # fee / free / loan / loan_fee only
    if rt.empty:
        return rt
    rt["player_id"] = rt.player_id.astype("int64")
    rt["to_club_id"] = rt.to_club_id.astype("int64")
    # a real event can repeat across seasonal snapshot files with one fee-bearing copy and
    # one blank one (e.g. loan-then-buy) -- na_position="first" so the real fee always wins
    rt = (rt.sort_values("fee_eur", na_position="first")
            .drop_duplicates(["player_id", "to_club_id", "transfer_date"], keep="last"))
    key = list(zip(rt.player_id, rt.to_club_id, rt.transfer_date.dt.year))
    rt = rt[[k not in seen_keys for k in key]].copy()
    if rt.empty:
        return rt

    cl = con.execute(f"SELECT club_id, domestic_competition_id FROM "
                      f"read_csv_auto('{ESTATE_A}/clubs.csv.gz', ignore_errors=true)").df()
    pl = con.execute(f"SELECT player_id, name, date_of_birth, sub_position, position FROM "
                      f"read_csv_auto('{ESTATE_A}/players.csv.gz', ignore_errors=true)").df()
    cl["club_id"] = pd.to_numeric(cl.club_id, errors="coerce")
    pl["player_id"] = pd.to_numeric(pl.player_id, errors="coerce")

    ext = rt.merge(pl, on="player_id", how="left")
    ext = ext.merge(cl.rename(columns={"club_id": "from_club_id", "domestic_competition_id": "from_comp"}),
                     on="from_club_id", how="left")
    ext = ext.merge(cl.rename(columns={"club_id": "to_club_id", "domestic_competition_id": "to_comp"}),
                     on="to_club_id", how="left")
    ext["player_name"] = ext.name
    ext["season"] = ext.transfer_date.dt.year
    dob = pd.to_datetime(ext.date_of_birth, errors="coerce")
    ext["player_age"] = ((ext.transfer_date - dob).dt.days / 365.25).round(1)
    ext["from_league"] = ext.from_comp.map(BIG5_COMP)
    ext["to_league"] = ext.to_comp.map(BIG5_COMP)
    ext["from_is_top5"] = ext.from_comp.isin(BIG5_COMP)
    ext["to_is_top5"] = ext.to_comp.isin(BIG5_COMP)
    ext["transfer_type"] = ext.fee_type.map(_RAW_TYPE_MAP)
    ext["fee_source"] = np.where(ext.fee_type.eq("fee"), "raw_api", None)
    _window = np.where(ext.transfer_date.dt.month.isin([1, 2]), "winter", "summer")
    # a handful of real events survive the exact-date dedup above as near-duplicates (same
    # player/club/season/window, transfer_date off by a day or from_club_name spelled two
    # ways across crawls) -- collapse those too, preferring the fee-bearing copy.
    ext = (ext.assign(_w=_window)
              .sort_values("fee_eur", na_position="first")
              .drop_duplicates(["player_id", "to_club_id", "season", "_w"], keep="last")
              .drop(columns="_w"))
    return ext


def _enrich_from_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Upgrade the spine with the dcaribou RAW harvest (ingest.tm_raw):
      • exact `transfer_date` at scale (raw api transfers, dense + dated),
      • recent fees where the enriched spine had none,
      • a leakage-safe `contract_years_remaining` (contract snapshot from a season
        STRICTLY BEFORE the transfer season — never the post-move contract).
    No-op (columns still added, empty) if the harvest hasn't been run."""
    df["fee_source"] = np.where(df.fee_eur.notna(), "spine", None)
    df["contract_years_remaining"] = np.nan
    df["contract_is_pit"] = False
    tr_p, ct_p = RAW_HARVEST / "raw_transfers.parquet", RAW_HARVEST / "raw_contracts.parquet"
    if not tr_p.exists():
        return df

    df["player_id"] = pd.to_numeric(df.player_id, errors="coerce").astype("Int64")
    df["to_club_id"] = pd.to_numeric(df.to_club_id, errors="coerce").astype("Int64")
    df["_yr"] = pd.to_numeric(df.season, errors="coerce").astype("Int64")

    # --- exact dates + recent fees from raw api transfers ---
    rt = pd.read_parquet(tr_p)
    rt["player_id"] = pd.to_numeric(rt.player_id, errors="coerce").astype("Int64")
    rt["to_club_id"] = pd.to_numeric(rt.to_club_id, errors="coerce").astype("Int64")
    rt["transfer_date"] = pd.to_datetime(rt.transfer_date, errors="coerce")
    rt["ryear"] = rt.transfer_date.dt.year.astype("Int64")
    # ponytail: na_position="first" so a real fee (sorted last, ascending) always beats a
    # NaN dup for the same (player, club, year) -- pandas default na_position="last" put
    # NaN AFTER the max fee, so keep="last" was silently discarding real fees on dup groups.
    rt = (rt.sort_values("fee_eur", na_position="first")          # prefer a fee-bearing event
            .drop_duplicates(["player_id", "to_club_id", "ryear"], keep="last"))
    look = rt[["player_id", "to_club_id", "ryear", "transfer_date", "fee_eur", "fee_type"]]

    # match on (player, to_club) with the raw event in the transfer's window:
    # summer -> ryear == season ; winter -> ryear == season + 1
    for off in (0, 1):
        j = df.merge(look.rename(columns={"transfer_date": "_rd", "fee_eur": "_rf", "fee_type": "_rft"}),
                     left_on=["player_id", "to_club_id", "_yr"],
                     right_on=["player_id", "to_club_id", "ryear"], how="left",
                     suffixes=("", "_j")) if off == 0 else None
        if off == 1:
            look2 = look.assign(match_season=(look.ryear - 1).astype("Int64"))
            j = df.merge(look2.rename(columns={"transfer_date": "_rd", "fee_eur": "_rf", "fee_type": "_rft"}),
                         left_on=["player_id", "to_club_id", "_yr"],
                         right_on=["player_id", "to_club_id", "match_season"], how="left")
        # upgrade proxy dates to the exact raw date
        up = j["_rd"].notna() & df.date_source.eq("proxy")
        df.loc[up, "transfer_date"] = j.loc[up, "_rd"]
        df.loc[up, "date"] = j.loc[up, "_rd"]
        df.loc[up, "date_source"] = "exact_raw"
        # fill a real fee where the spine had none (apply the €222m sanity ceiling)
        fill = df.fee_eur.isna() & j["_rf"].notna() & j["_rft"].eq("fee") & (j["_rf"] > 0)
        df.loc[fill, "fee_eur"] = j.loc[fill, "_rf"]
        df.loc[fill, "fee_source"] = "raw_api"
        df.loc[fill, "fee_suspect"] = j.loc[fill, "_rf"] > 222_000_000
        # the 2023+ extension (estateA_2023plus) never gets a transfer_type -- Estate A's prep
        # transfers.csv.gz has no such field. Infer it from the raw api's fee_type where we have
        # a matched event (same join as the fee fill above); leaves it None where unmatched.
        tset = df.transfer_type.isna() & j["_rft"].notna()
        df.loc[tset, "transfer_type"] = j.loc[tset, "_rft"].map(_RAW_TYPE_MAP)

    # --- leakage-safe contract_years_remaining (snapshot STRICTLY before the season) ---
    if ct_p.exists():
        rc = pd.read_parquet(ct_p)
        rc["player_id"] = pd.to_numeric(rc.player_id, errors="coerce").astype("Int64")
        rc["contract_expires"] = pd.to_datetime(rc.contract_expires, errors="coerce")
        rc = rc.dropna(subset=["player_id", "contract_expires", "season"]).copy()
        rc["season"] = rc.season.astype("int64")
        d2 = df.reset_index()[["index", "player_id", "_yr", "date"]].dropna(subset=["player_id", "_yr"])
        d2["_yr"] = d2._yr.astype("int64")
        m = pd.merge_asof(
            d2.sort_values("_yr"), rc.sort_values("season")[["player_id", "season", "contract_expires"]],
            left_on="_yr", right_on="season", by="player_id",
            direction="backward", allow_exact_matches=False)     # season < transfer season only
        m = m.dropna(subset=["contract_expires"]).set_index("index")
        yrs = ((m.contract_expires - m.date).dt.days / 365.25).clip(lower=0)
        df.loc[yrs.index, "contract_years_remaining"] = yrs
        df.loc[yrs.index, "contract_is_pit"] = True

    return df.drop(columns=["_yr"], errors="ignore")


def build_canonical(write: bool = True) -> pd.DataFrame:
    import duckdb
    con = duckdb.connect()
    src = str(ESTATE_B / "02_transfers" / "transfers.parquet")
    raw_n = con.execute(f"SELECT count(*) FROM read_parquet('{src}')").fetchone()[0]

    # 1. dedup spine ---------------------------------------------------------
    df = _dedup_spine(con, src)
    df["origin"] = "estateB"

    # 2. exact-date backfill (else proxy) -----------------------------------
    ex = _exact_dates(con)
    df["yr"] = pd.to_numeric(df.season, errors="coerce").astype("Int64")
    for col, frame in [("player_id", df), ("to_club_id", df), ("player_id", ex), ("to_club_id", ex)]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("Int64")
    ex["yr"] = pd.to_numeric(ex.yr, errors="coerce").astype("Int64")
    df = df.merge(ex[["player_id", "to_club_id", "yr", "transfer_date"]],
                  on=["player_id", "to_club_id", "yr"], how="left")
    df["date_source"] = np.where(df.transfer_date.notna(), "exact", "proxy")
    proxy = _proxy_date(df.season, df.window)
    df["date"] = df.transfer_date.fillna(pd.Series(proxy, index=df.index))

    # 3. point-in-time MV fill ----------------------------------------------
    vals = _load_valuations(con)
    pit = _asof_mv(df, vals)
    df["pit_mv"] = pit.reindex(df.index)
    df["mv_is_point_in_time"] = df.pit_mv.notna()
    df["mv_source"] = np.where(df.pit_mv.notna(), "pit_valuation",
                        np.where(df.market_value_eur.notna(), "estateB_snapshot", "none"))
    df["market_value_eur"] = df.pit_mv.where(df.pit_mv.notna(), df.market_value_eur)

    # 4. 2023+ extension -----------------------------------------------------
    seen = set(zip(df.player_id.fillna(-1).astype("int64"),
                   pd.to_numeric(df.to_club_id, errors="coerce").fillna(-1).astype("int64"),
                   df.yr.fillna(-1).astype("int64")))
    ext = _extension(con, vals, seen)
    if not ext.empty:
        ext["date"] = ext.transfer_date
        ext["date_source"] = "exact"
        ext["pit_mv"] = _asof_mv(ext.assign(player_id=ext.player_id), vals).reindex(ext.index)
        ext["mv_is_point_in_time"] = ext.pit_mv.notna()
        ext["mv_source"] = np.where(ext.pit_mv.notna(), "pit_valuation",
                             np.where(ext.market_value_eur.notna(), "estateA_snapshot", "none"))
        ext["market_value_eur"] = ext.pit_mv.where(ext.pit_mv.notna(), ext.market_value_eur)
        ext["origin"] = "estateA_2023plus"
        for c in ("fee_undisclosed", "fee_suspect", "age_suspect", "fee_zero_suspect"):
            ext[c] = False
        ext["window"] = np.where(ext.transfer_date.dt.month.isin([1, 2]), "winter", "summer")
        ext["transfer_type"] = None    # Estate A prep has no type field; _enrich_from_raw infers it below
        ext["pos_group"] = ext.position
        cols = [c for c in df.columns if c in ext.columns]
        df = pd.concat([df, ext[cols]], ignore_index=True)

    # 4b. 2023+ extension, take two -- straight from the RAW harvest (dense, fee-bearing),
    # not the thin Estate A prep table. Covers the ~99% of recent real-fee deals `_extension`
    # can't see because they were never a row in transfers.csv.gz to begin with.
    seen2 = set(zip(df.player_id.fillna(-1).astype("int64"),
                    pd.to_numeric(df.to_club_id, errors="coerce").fillna(-1).astype("int64"),
                    pd.to_numeric(df.season, errors="coerce").fillna(-1).astype("int64")))
    ext2 = _extension_from_raw(con, seen2)
    if not ext2.empty:
        ext2["date"] = ext2.transfer_date
        ext2["date_source"] = "exact"
        ext2["pit_mv"] = _asof_mv(ext2.assign(player_id=ext2.player_id), vals).reindex(ext2.index)
        ext2["mv_is_point_in_time"] = ext2.pit_mv.notna()
        ext2["mv_source"] = np.where(ext2.pit_mv.notna(), "pit_valuation",
                              np.where(ext2.market_value_eur.notna(), "raw_snapshot", "none"))
        ext2["market_value_eur"] = ext2.pit_mv.where(ext2.pit_mv.notna(), ext2.market_value_eur)
        ext2["origin"] = "raw_2023plus"
        ext2["fee_suspect"] = ext2.fee_eur > 222_000_000
        for c in ("fee_undisclosed", "age_suspect", "fee_zero_suspect"):
            ext2[c] = False
        ext2["window"] = np.where(ext2.transfer_date.dt.month.isin([1, 2]), "winter", "summer")
        ext2["pos_group"] = ext2.position
        cols2 = [c for c in df.columns if c in ext2.columns]
        df = pd.concat([df, ext2[cols2]], ignore_index=True)

    # 5. raw-harvest enrichment: exact dates at scale + recent fees + PIT contracts
    df = df.drop(columns=["yr", "pit_mv"], errors="ignore")
    df = _enrich_from_raw(df)

    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(OUT, index=False)

    _report(df, raw_n, ext)
    return df


def _report(df, raw_n, ext):
    pid = df.player_id.notna()
    feepos = (df.fee_eur > 0) & ~df.fee_suspect.fillna(False)
    mvcov = df.market_value_eur.notna()
    modelready = feepos & mvcov & df.player_age.notna() & pid
    print("=" * 68)
    print("CANONICAL TRANSFERS — coverage report")
    print("=" * 68)
    print(f"  Estate B raw rows          {raw_n:>9,}")
    _removed = raw_n - int((df.origin == 'estateB').sum())
    print(f"  after guarded dedup        {int((df.origin=='estateB').sum()):>9,}   "
          f"({'already clean' if _removed==0 else f'removed {_removed:,}'})")
    print(f"  + 2023+ extension rows     {int((df.origin!='estateB').sum()):>9,}")
    print(f"  = canonical total          {len(df):>9,}")
    print(f"  season range               {int(df.season.min())}–{int(df.season.max())}")
    print("  ---- backfills ----")
    exact = df.date_source.isin(["exact", "exact_raw"])
    print(f"  exact transfer_date        {int(exact.sum()):>9,}   "
          f"({100*exact.mean():.1f}%)  [prep {int((df.date_source=='exact').sum()):,} + raw {int((df.date_source=='exact_raw').sum()):,}]")
    print(f"  market value (any)         {100*mvcov.mean():>8.1f}%   (Estate B alone was 40.0%)")
    print(f"  market value point-in-time {100*df.mv_is_point_in_time.mean():>8.1f}%")
    print(f"  clean fee>0 (not suspect)  {int(feepos.sum()):>9,}   "
          f"(raw-api filled {int(df.get('fee_source', pd.Series(dtype=object)).eq('raw_api').sum()):,})")
    if "contract_is_pit" in df:
        print(f"  contract_years (PIT, safe) {int(df.contract_is_pit.sum()):>9,}   "
              f"({100*df.contract_is_pit.mean():.1f}%)  <- was 0 (empty scaffold)")
    print(f"  MODEL-READY (fee+mv+age)   {int(modelready.sum()):>9,}   <- fee-ranker training set")
    print("=" * 68)
    print("REMAINING GAPS (say the word to spawn agents):")
    print("  • exact dates: raw harvest lifted to 15.4%; capped by raw player coverage (~11k)")
    print("  • recent Big-5 fees: raw api adds some; pre-official leaks/rumours = news data, not structured")
    print("  • WAGES: still a paid-only blocker (Capology licence) or grade-D proxy — needs your call")


def _check():
    """Self-check: dedup guard + leakage-safe as-of, on a tiny synthetic frame."""
    rows = pd.DataFrame({
        "player_id": [1, 1], "date": pd.to_datetime(["2020-08-01", "2020-08-01"]),
    })
    vals = pd.DataFrame({
        "player_id": [1, 1, 1],
        "vd": pd.to_datetime(["2020-01-01", "2020-08-01", "2021-01-01"]),
        "mv": [10.0, 999.0, 50.0],  # 999 is same-day: must NOT be picked (leak)
    })
    mv = _asof_mv(rows, vals)
    assert (mv == 10.0).all(), f"as-of leaked a same-day/future value: {mv.tolist()}"
    assert _norm_club("Real Madrid CF") == _norm_club("real madrid"), "club norm mismatch"
    assert _proxy_date([2020], ["winter"]).iloc[0] == pd.Timestamp("2021-01-20")
    assert _proxy_date([2020], ["summer"]).iloc[0] == pd.Timestamp("2020-08-01")
    print("ok — as-of is strictly-before (no leak), club-norm + proxy-date correct")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        build_canonical()
