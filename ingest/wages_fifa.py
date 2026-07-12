"""Wages — FIFA/FM game-estimated prior, crosswalked to Transfermarkt ids.

The upgrade path `ingest/wages.py` documented but never built. No free *audited*
wage dump exists (Capology is scrape/paid, non-redistributable). EA Sports' FIFA
database publishes a per-player weekly wage that turns out to be a surprisingly good
*cardinal* estimate at the top (FIFA 21: De Bruyne €370k/wk ≈ his real wage) and a
solid ordinal signal below — good enough for a grade-C prior once recalibrated to the
handful of real anchors the parametric model is fitted on.

WHY BLEND, not replace: the parametric model (`wages.estimate_wage`) has the right
*level* (fitted to real reported salaries) and clean league/age structure, but is blind
to the individual — it can't see that a 23yo on a legacy contract earns below his MV.
FIFA supplies that per-player deviation. So:

    fifa_cal   = monotone map of FIFA weekly wage onto the model's £ scale  (learns
                 EUR->GBP + FIFA's compression, fitted vs the model on matched players)
    wage_gbp   = geometric mean of model_wage and fifa_cal   (level from the model,
                 individual nudge from FIFA)

Coverage: FIFA 21 (primary) + FIFA 20 (fallback), ~19k players/edition incl. the big-5
AND Championship / MLS / Argentina etc. — broader league reach than Understat. Crosswalked
to `tm_player_id` by normalised name + date-of-birth (dob disambiguates same-name players).

Honesty (unchanged rule, per SPEC.md): every row carries `source` ('fifa_prior' when a
FIFA wage was found, else 'modelled') and a wide interval (x/÷1.6). FIFA is a *game*
estimate — directionally strong, individually noisy, and its levels are frozen at the
edition year (2020/21), so for a current signing treat the *rank* as more reliable than
the absolute. Not for resale (game data); research/personal use, which is this project's
current footing.

Output: data/wages/wages_fifa.parquet
  tm_player_id, player_name, league_key, age, mv_eur_m, position, overall,
  fifa_wage_eur_wk, model_wage_gbp, fifa_cal_gbp, wage_gbp, lo, hi, source
"""
from __future__ import annotations
import re
import unicodedata
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

from ingest import wages  # reuse the fitted parametric model + anchors

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data" / "wages"
TM_PLAYERS = REPO / "data" / "transfermarkt" / "players.csv.gz"
OUT = REPO / "data" / "wages" / "wages_fifa.parquet"
_FIFA_URL = ("https://raw.githubusercontent.com/ifrankandrade/data-visualization/"
             "main/datasets/players_{}.csv")   # {} = 17..21
# Editions 17-21 confirmed live at this mirror (checked 2026-07-12: 15/16/22/23 -> 404,
# 17-21 -> 200). Extends the prior from 2 editions (2020/21 only) to a 5-year time
# series (FIFA 17 ~= 2016/17 season through FIFA 21 ~= 2020/21).
FIFA_EDITIONS = [21, 20, 19, 18, 17]
FIFA_21 = DATA_DIR / "fifa_players_21.csv"   # back-compat alias, still used elsewhere
FIFA_20 = DATA_DIR / "fifa_players_20.csv"


def _fifa_path(ed: int) -> Path:
    return DATA_DIR / f"fifa_players_{ed}.csv"


def _ensure_sources():
    """Fetch the FIFA player CSVs if not cached (makes `build` reproducible)."""
    import urllib.request
    for ed in FIFA_EDITIONS:
        path = _fifa_path(ed)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"fetching FIFA {ed} ...")
            urllib.request.urlretrieve(_FIFA_URL.format(ed), path)

# ponytail: fixed EUR->GBP; a real rate drifts, but this is a knob absorbed by the
# recalibration fit below (it re-maps FIFA onto the £ anchors regardless), so the
# constant only matters as a starting point. Update if levels look off.
_EUR_GBP = 0.85
_WEEKS = 52
_BAND = 1.6                 # blended proxy -> wider than the model's own x/÷1.55
_FIFA_WEIGHT = 0.5          # geometric blend weight on the FIFA signal

# FIFA league_name -> the model's LEAGUE_MULT key (substring match, spelling-tolerant).
_LEAGUE_RULES = [
    (("english", "premier league"), "ENG-Premier League"),
    (("primera division",),         "ESP-La Liga"),
    (("italian", "serie a"),        "ITA-Serie A"),
    (("bundesliga",),               "GER-Bundesliga"),   # "German 1. Bundesliga"
    (("ligue 1",),                  "FRA-Ligue 1"),
]


def _league_key(name: str) -> str | None:
    n = str(name).lower()
    if "bundesliga" in n and ("2." in n or "second" in n):
        return None  # 2. Bundesliga is not top-flight
    for needles, key in _LEAGUE_RULES:
        if all(x in n for x in needles):
            return key
    return None


def _norm(s) -> str:
    """Accent-fold + lowercase + alpha-only, for name joins."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", s.lower())).strip()


def _cname(nname: str) -> str:
    """First + last token — bridges FIFA full birth names to TM common names
    ('bruno miguel borges fernandes' -> 'bruno fernandes')."""
    toks = str(nname).split()
    return f"{toks[0]} {toks[-1]}" if len(toks) >= 2 else str(nname)


def _tm_position(pos, sub) -> str:
    """TM position/sub_position -> GK/DF/MF/FW."""
    p = str(pos).lower()
    if "goalkeep" in p or str(sub).lower().startswith("goalkeep"):
        return "GK"
    if "defend" in p or "back" in str(sub).lower():
        return "DF"
    if "midfield" in p:
        return "MF"
    if "attack" in p or "forward" in p or "striker" in p or "wing" in str(sub).lower():
        return "FW"
    return "MF"


# ------------------------------------------------------------------ load

def load_fifa(dedup: bool = True) -> pd.DataFrame:
    """All cached FIFA editions (17-21, whichever are on disk), wage>0 only.

    dedup=True (default, used by the existing single-row-per-player prior in
    `build()`): keep only the newest edition per player. dedup=False (used by
    `build_timeseries()`): keep every edition -> a real per-player wage history.
    """
    cols = ["sofifa_id", "long_name", "short_name", "age", "dob", "club_name",
            "league_name", "overall", "value_eur", "wage_eur"]
    frames = []
    for ed in FIFA_EDITIONS:
        path = _fifa_path(ed)
        if path.exists():
            d = pd.read_csv(path, usecols=lambda c: c in cols, low_memory=False)
            d["edition_year"] = 2000 + ed
            frames.append(d)
    f = pd.concat(frames, ignore_index=True)
    f["wage_eur"] = pd.to_numeric(f["wage_eur"], errors="coerce")
    f["value_eur"] = pd.to_numeric(f["value_eur"], errors="coerce")
    f = f[f["wage_eur"] > 0].copy()
    if dedup:
        # prefer the newest edition per player
        f = f.sort_values("edition_year", ascending=False).drop_duplicates("sofifa_id", keep="first")
    f["dob"] = pd.to_datetime(f["dob"], errors="coerce").dt.date.astype("object")
    f["nname"] = f["long_name"].map(_norm)
    f["cname"] = f["nname"].map(_cname)
    return f.reset_index(drop=True)


def load_tm() -> pd.DataFrame:
    t = pd.read_csv(TM_PLAYERS, compression="gzip", low_memory=False,
                    usecols=["player_id", "name", "date_of_birth", "position",
                             "sub_position", "market_value_in_eur"])
    t["dob"] = pd.to_datetime(t["date_of_birth"], errors="coerce").dt.date.astype("object")
    t["nname"] = t["name"].map(_norm)
    t["cname"] = t["nname"].map(_cname)
    t["pos"] = [_tm_position(p, s) for p, s in zip(t["position"], t["sub_position"])]
    return t


# ------------------------------------------------------------------ crosswalk

_FIFA_KEEP = ["sofifa_id", "long_name", "age", "overall", "wage_eur", "value_eur",
              "league_name", "edition_year"]
_TM_KEEP = ["player_id", "pos", "market_value_in_eur"]


def crosswalk(fifa: pd.DataFrame, tm: pd.DataFrame) -> pd.DataFrame:
    """FIFA -> tm_player_id. Cascade of passes, safest first; each FIFA row is
    matched at most once, dob disambiguating same-name collisions:

      1. full name + dob        4. unique full name (no dob needed)
      2. first+last + dob       5. unique first+last name
      3. (both above are exact) ...

    Ambiguous names that never agree on dob are dropped, not guessed.
    """
    tm = tm[tm["nname"].astype(bool)].copy()
    matched, seen = [], set()

    def _take(m):
        m = m[~m["sofifa_id"].isin(seen)]
        matched.append(m[_FIFA_KEEP + ["player_id", "pos", "market_value_in_eur"]])
        seen.update(m["sofifa_id"])

    # passes 1-2: name + dob (exact, safest)
    for key in ("nname", "cname"):
        left = fifa[fifa["dob"].notna() & ~fifa["sofifa_id"].isin(seen)]
        right = tm.dropna(subset=["dob"]).drop_duplicates([key, "dob"])[[key, "dob", *_TM_KEEP]]
        _take(left.merge(right, on=[key, "dob"], how="inner"))

    # passes 3-4: unique name on both sides (no dob)
    for key in ("nname", "cname"):
        tm_c = tm[key].value_counts()
        tm_u = tm[tm[key].isin(tm_c[tm_c == 1].index)][[key, *_TM_KEEP]]
        rest = fifa[~fifa["sofifa_id"].isin(seen)]
        f_c = rest[key].value_counts()
        f_u = rest[rest[key].isin(f_c[f_c == 1].index)]
        _take(f_u.merge(tm_u, on=key, how="inner"))

    out = pd.concat(matched, ignore_index=True) if matched else pd.DataFrame()
    return out.drop_duplicates("player_id").reset_index(drop=True)


# ------------------------------------------------------------------ wages

def compute_wages(matched: pd.DataFrame) -> pd.DataFrame:
    """Era-consistent model wage + FIFA recalibration + blend. Pure.

    Both the model wage and the FIFA wage are anchored to the SAME edition year:
    the model runs on FIFA's own market value (`value_eur`), not TM's current value,
    so an aged star's low 2026 MV doesn't get blended against his peak-era FIFA pay.
    The result is a wage estimate AS OF the edition year (2020/21) — a point-in-time
    prior. `mv_eur_m` (TM current value) is carried for reference only.
    """
    df = matched.copy()
    df["mv_eur_m"] = pd.to_numeric(df["market_value_in_eur"], errors="coerce") / 1e6  # TM current, ref
    df["mv_fifa_m"] = pd.to_numeric(df["value_eur"], errors="coerce") / 1e6           # era-matched
    df["league_key"] = df["league_name"].map(_league_key)
    df["fifa_annual_gbp"] = df["wage_eur"] * _WEEKS * _EUR_GBP
    df = df[(df["mv_fifa_m"] > 0) & (df["fifa_annual_gbp"] > 0)].copy()

    def _model(r):
        lg = r.league_key if isinstance(r.league_key, str) else "OTHER"
        return wages.estimate_wage(r.age, lg, r.mv_fifa_m, r.pos).annual_wage_gbp
    df["model_wage_gbp"] = df.apply(_model, axis=1)

    # recalibrate FIFA -> £: fit log(model) ~ a + b log(fifa) on big-5 rows (level
    # best anchored there). Monotone map absorbs EUR/GBP + FIFA's top-end compression.
    fit = df[df["league_key"].notna()]
    a, b = np.log(_EUR_GBP), 1.0        # identity-in-£ fallback
    if len(fit) >= 40:
        bb, aa = np.polyfit(np.log(fit["fifa_annual_gbp"]), np.log(fit["model_wage_gbp"]), 1)
        if 0.3 <= bb <= 1.5:            # accept only a plausible slope
            a, b = aa, bb
    df["fifa_cal_gbp"] = np.exp(a + b * np.log(df["fifa_annual_gbp"]))

    w = _FIFA_WEIGHT
    df["wage_gbp"] = np.exp((1 - w) * np.log(df["model_wage_gbp"])
                            + w * np.log(df["fifa_cal_gbp"])).round()
    df["lo"] = (df["wage_gbp"] / _BAND).round()
    df["hi"] = (df["wage_gbp"] * _BAND).round()
    df["source"] = "fifa_prior"
    df = df.rename(columns={"player_id": "tm_player_id", "long_name": "player_name",
                            "wage_eur": "fifa_wage_eur_wk", "pos": "position"})
    keep = ["tm_player_id", "player_name", "league_key", "edition_year", "age",
            "mv_eur_m", "mv_fifa_m", "position", "overall", "fifa_wage_eur_wk",
            "model_wage_gbp", "fifa_cal_gbp", "wage_gbp", "lo", "hi", "source"]
    return df[keep].sort_values("wage_gbp", ascending=False).reset_index(drop=True)


def build() -> pd.DataFrame:
    _ensure_sources()
    fifa, tm = load_fifa(), load_tm()
    matched = crosswalk(fifa, tm)
    out = compute_wages(matched)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)

    print(f"FIFA players (wage>0):    {len(fifa):,}")
    print(f"crosswalked to TM id:     {len(matched):,}  ({100*len(matched)/len(fifa):.0f}% of FIFA)")
    print(f"priced (TM MV present):   {len(out):,}")
    print(f"  big-5 leagues:          {int(out.league_key.notna().sum()):,}")
    print(f"  median wage:            £{out.wage_gbp.median()/_WEEKS:,.0f}/wk")
    # spot-check a few marquee names against reality
    for nm in ("Kevin De Bruyne", "Virgil van Dijk", "Harry Kane"):
        r = out[out.player_name == nm]
        if not r.empty:
            r = r.iloc[0]
            print(f"  {nm:<18} model £{r.model_wage_gbp/_WEEKS:,.0f}/wk  "
                  f"fifa_cal £{r.fifa_cal_gbp/_WEEKS:,.0f}/wk  -> £{r.wage_gbp/_WEEKS:,.0f}/wk")
    print(f"wrote {OUT}")
    return out


TIMESERIES_OUT = REPO / "data" / "wages" / "wages_fifa_timeseries.parquet"


def build_timeseries() -> pd.DataFrame:
    """Per-player wage HISTORY across every cached FIFA edition (17-21), not just
    the newest. sofifa_id is EA's persistent cross-edition player id, so the
    tm_player_id mapping learned once (from the latest-edition crosswalk in
    `build()`/`crosswalk()`) is reused to key every edition's row -> no re-matching,
    no re-implementing the join.
    """
    _ensure_sources()
    fifa_latest, tm = load_fifa(dedup=True), load_tm()
    matched = crosswalk(fifa_latest, tm)
    id_map = dict(zip(matched["sofifa_id"], matched["player_id"]))

    fifa_all = load_fifa(dedup=False)
    ts = fifa_all[fifa_all["sofifa_id"].isin(id_map)].copy()
    ts["tm_player_id"] = ts["sofifa_id"].map(id_map)
    ts["league_key"] = ts["league_name"].map(_league_key)
    ts["annual_wage_gbp"] = (ts["wage_eur"] * _WEEKS * _EUR_GBP).round()
    ts = ts.rename(columns={"long_name": "player_name"})
    keep = ["tm_player_id", "player_name", "edition_year", "age", "overall",
            "league_key", "annual_wage_gbp"]
    ts = (ts[keep].sort_values(["tm_player_id", "edition_year"])
                   .reset_index(drop=True))
    TIMESERIES_OUT.parent.mkdir(parents=True, exist_ok=True)
    ts.to_parquet(TIMESERIES_OUT, index=False)
    n_players = ts["tm_player_id"].nunique()
    n_multi = ts.groupby("tm_player_id").size().gt(1).sum()
    print(f"timeseries rows: {len(ts):,}  players: {n_players:,}  "
          f"with >=2 editions: {n_multi:,} ({100*n_multi/max(n_players,1):.0f}%)")
    print(f"wrote {TIMESERIES_OUT}")
    return ts


def load() -> pd.DataFrame:
    return pd.read_parquet(OUT)


class Wage(NamedTuple):
    annual_wage_gbp: float
    lo: float
    hi: float
    source: str


def blended_wage(tm_player_id=None, *, age=None, league=None, market_value=None,
                 position="MF", table: pd.DataFrame | None = None) -> Wage:
    """Best available wage: the FIFA-blended row if we have one for this TM id,
    else the parametric model (flagged 'modelled'). Drop-in for wages.estimate_wage —
    consumers key off `.source`.
    """
    if tm_player_id is not None:
        t = load() if table is None else table
        row = t[t.tm_player_id == tm_player_id]
        if not row.empty:
            r = row.iloc[0]
            return Wage(float(r.wage_gbp), float(r.lo), float(r.hi), "fifa_prior")
    if not (age and league and market_value):
        raise ValueError("no FIFA wage for that id; pass age/league/market_value to fall back")
    e = wages.estimate_wage(age, league, market_value, position)
    return Wage(e.annual_wage_gbp, e.lo, e.hi, "modelled")


# ------------------------------------------------------------------ check

def _check():
    # normaliser: accents + punctuation folded
    assert _norm("Kevin De Bruyne") == "kevin de bruyne"
    assert _norm("Ángel Di María") == "angel di maria"

    # league mapper
    assert _league_key("English Premier League") == "ENG-Premier League"
    assert _league_key("German 1. Bundesliga") == "GER-Bundesliga"
    assert _league_key("German 2. Bundesliga") is None
    assert _league_key("USA Major League Soccer") is None

    # crosswalk: dob disambiguates two players sharing a normalised name; a full
    # birth name still matches TM's common name via the first+last (cname) pass.
    def _ff(**k):
        k.setdefault("value_eur", 30_000_000); k.setdefault("edition_year", 2021)
        k["nname"] = _norm(k["long_name"]); k["cname"] = _cname(k["nname"])
        return k
    fifa = pd.DataFrame([
        _ff(sofifa_id=1, long_name="John Smith", age=25, overall=80, wage_eur=50000,
            league_name="English Premier League", dob=pd.Timestamp("1999-01-01").date()),
        _ff(sofifa_id=2, long_name="John Smith", age=30, overall=70, wage_eur=20000,
            league_name="English Premier League", dob=pd.Timestamp("1994-05-05").date()),
        _ff(sofifa_id=3, long_name="Bruno Miguel Borges Fernandes", age=28, overall=85,
            wage_eur=90000, league_name="Italian Serie A", dob=pd.Timestamp("1996-03-03").date()),
    ])
    def _ft(**k):
        k["nname"] = _norm(k["name"]); k["cname"] = _cname(k["nname"]); return k
    tm = pd.DataFrame([
        _ft(player_id=1001, name="John Smith", dob=pd.Timestamp("1999-01-01").date(),
            pos="MF", market_value_in_eur=30_000_000),
        _ft(player_id=1002, name="John Smith", dob=pd.Timestamp("1994-05-05").date(),
            pos="DF", market_value_in_eur=8_000_000),
        _ft(player_id=1003, name="Bruno Fernandes", dob=pd.Timestamp("1990-01-01").date(),  # dob differs
            pos="MF", market_value_in_eur=40_000_000),
    ])
    m = crosswalk(fifa, tm)
    ids = dict(zip(m.sofifa_id, m.player_id))
    assert ids[1] == 1001 and ids[2] == 1002, ids   # dob routed each Smith correctly
    assert ids.get(3) == 1003, "first+last unique-name pass should bridge full birth name"

    # compute_wages: blend sits between model and fifa_cal, monotone in FIFA wage,
    # interval brackets it, source flagged.
    big = pd.DataFrame([
        dict(sofifa_id=i, long_name=f"P{i}", age=27, overall=80, value_eur=40_000_000,
             edition_year=2021, wage_eur=w, league_name="English Premier League",
             player_id=2000 + i, pos="MF", market_value_in_eur=40_000_000)
        for i, w in enumerate([5000, 20000, 60000, 120000, 250000] * 12)])  # 60 rows for the fit
    cw = compute_wages(big)
    assert (cw.source == "fifa_prior").all()
    assert (cw.lo < cw.wage_gbp).all() and (cw.wage_gbp < cw.hi).all()
    # higher FIFA wage -> higher blended wage, holding MV/age/league fixed
    by_fifa = cw.sort_values("fifa_wage_eur_wk")
    assert list(by_fifa.wage_gbp) == sorted(by_fifa.wage_gbp), "blend must be monotone in FIFA wage"

    # blended_wage fallback path (no id / not in table) -> modelled
    w = blended_wage(age=27, league="ENG-Premier League", market_value=40, position="MF")
    assert w.source == "modelled" and w.lo < w.annual_wage_gbp < w.hi

    print("crosswalk + blend + fallback all ok")


if __name__ == "__main__":
    import sys
    if "timeseries" in sys.argv[1:]:
        build_timeseries()
    elif "build" in sys.argv[1:]:
        build()
    else:
        _check()
