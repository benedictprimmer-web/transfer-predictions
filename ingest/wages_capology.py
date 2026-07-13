"""Wages — Capology real per-player salaries (grade-B), personal/research-use.

Capology (capology.com) publishes an estimated gross annual salary per player per
club/season across ~30 leagues. Confirmed HTTP 200 from this sandbox (unlike FBref,
it does not block the datacenter IP). It is a ToS-protected site (no public API,
no redistribution licence) so this fetch is gated behind an explicit go-ahead and
is for personal/research use only, per DATA_ACQUISITION_PLAN.md's current footing
(commercial constraints dropped) and the user's direct instruction to pursue it.

No login wall, no bot-detection JS, no headless browser needed: each salaries page
embeds the whole table as a plain JS array literal —

    var data = [{'name': "<a href='/player/erling-haaland-36728/'>...Erling Haaland</a>",
                 'annual_gross_gbp': accounting.formatMoney("27300000", "£ ", 0),
                 'age': Math.round("25"), 'position': "F", 'country': "Norway",
                 'club': "<a href='/club/manchester-city/salaries/'>Manchester City</a>",
                 'signed': moment("2025-01-17")..., 'expiration': moment("2034-06-30")..., ...}, ...]

— so this is a plain regex extraction of already-rendered HTML, not a scrape that
needs JS execution or defeats bot-detection.

Two-step, resumable:
    fetch(leagues=LEAGUES)  -> caches raw HTML per (league, season) to
                               data/wages/capology_raw/<cc>_<slug>_<season>.html
                               skips files already on disk (resumable / re-runnable)
    build()                 -> parses every cached HTML file, crosswalks to
                               tm_player_id (reusing wages_fifa.crosswalk's unique-
                               name matching passes — real dob is unavailable here so
                               only its no-dob passes fire), writes:
                                 data/wages/capology_all_seasons.parquet (every row, every season)
                                 data/wages/capology.csv (one row per player: latest
                                   season only, in the exact schema wages.load_capology_csv()
                                   expects, tm_player_id attached)

If this sandbox ever gets blocked, the fetch loop is unchanged in shape from a run on
a residential/other IP: re-run `python -m ingest.wages_capology fetch --yes` from
wherever is reachable, then copy data/wages/capology_raw/*.html back and run `build`.

Run:
    python -m ingest.wages_capology fetch --yes   # harvest (politely rate-limited)
    python -m ingest.wages_capology build          # parse cache -> capology.csv
    python -m ingest.wages_capology                # offline self-check (no network)
"""
from __future__ import annotations

from html import unescape as _html_unescape
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

import pandas as pd

from ingest import wages_fifa

REPO = Path(__file__).resolve().parent.parent
RAW_DIR = REPO / "data" / "wages" / "capology_raw"
ALL_SEASONS_OUT = REPO / "data" / "wages" / "capology_all_seasons.parquet"
CSV_OUT = REPO / "data" / "wages" / "capology.csv"

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_BASE = "https://www.capology.com"

# (country_code, slug, wages.LEAGUE_MULT key or None for "other"/feeder leagues).
# Priority set: big-5 (real anchors) + the project's stated feeder-league focus
# (Portugal/Eredivisie/Championship/Brazil/Belgium/Argentina, per
# DATA_ACQUISITION_PLAN.md) + MLS/Saudi/Scotland for extra US-reachable/high-wage tail.
LEAGUES = [
    ("uk", "premier-league",       "ENG-Premier League"),
    ("es", "la-liga",              "ESP-La Liga"),
    ("it", "serie-a",              "ITA-Serie A"),
    ("de", "1-bundesliga",         "GER-Bundesliga"),
    ("fr", "ligue-1",              "FRA-Ligue 1"),
    ("uk", "championship",         None),
    ("ne", "eredivisie",           None),
    ("pt", "primeira-liga",        None),
    ("br", "brasileiro",           None),
    ("be", "first-division-a",     None),
    ("ar", "primera-division",     None),
    ("us", "mls",                  None),
    ("sa", "saudi-pro-league",     None),
    ("uk", "scottish-premiership", None),
]

# Must be scoped to THIS league's own path -- the page also embeds an unrelated
# "jump to a club" dropdown for other leagues/seasons (e.g. Argentine clubs at
# /club/.../salaries/2026/) that a bare `salaries/(season)/` regex would wrongly
# vacuum up as if they were this league's season history.
def _season_re(cc: str, slug: str) -> re.Pattern:
    return re.compile(rf"/{re.escape(cc)}/{re.escape(slug)}/salaries/(\d{{4}}(?:-\d{{4}})?)/")


def _get(url: str, tries: int = 4) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    print(f"  giving up on {url}", file=sys.stderr)
    return None


def discover_seasons(cc: str, slug: str, home_html: str) -> list[str]:
    return sorted(set(_season_re(cc, slug).findall(home_html)))


def fetch(leagues=LEAGUES, delay: float = 1.2, confirm: bool = False) -> None:
    """Resumable harvest: caches raw HTML, skips files already on disk.

    `confirm=True` (or CLI `--yes`) is the go-ahead flag required by the harvest
    rules of engagement for a ToS-protected personal-use scrape.
    """
    if not confirm:
        raise RuntimeError(
            "Capology fetch is a ToS-protected personal-use scrape and requires an "
            "explicit go-ahead: call fetch(confirm=True) or run with --yes.")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    n_fetched = n_skipped = n_missing = 0
    for cc, slug, _ in leagues:
        home_path = RAW_DIR / f"{cc}_{slug}_current.html"
        if home_path.exists():
            home_html = home_path.read_text(encoding="utf-8", errors="ignore")
            n_skipped += 1
        else:
            print(f"fetching {cc}/{slug} (current) ...")
            home_html = _get(f"{_BASE}/{cc}/{slug}/salaries/")
            if home_html is None:
                print(f"  {cc}/{slug}: 404, skipping league")
                n_missing += 1
                continue
            home_path.write_text(home_html, encoding="utf-8")
            n_fetched += 1
            time.sleep(delay)
        seasons = discover_seasons(cc, slug, home_html)
        print(f"  {cc}/{slug}: {len(seasons)} historical seasons found")
        for season in seasons:
            path = RAW_DIR / f"{cc}_{slug}_{season}.html"
            if path.exists():
                n_skipped += 1
                continue
            html = _get(f"{_BASE}/{cc}/{slug}/salaries/{season}/")
            if html is None:
                n_missing += 1
                continue
            path.write_text(html, encoding="utf-8")
            n_fetched += 1
            time.sleep(delay)
    print(f"fetch done: {n_fetched} pages fetched, {n_skipped} already cached, "
          f"{n_missing} 404/failed")


# ------------------------------------------------------------------ parse

_TAG_RE = re.compile(r"<[^>]+>")
_OBJ_SPLIT_RE = re.compile(r"\{\s*'name':")

_FIELD_RES = {
    "name_raw":     re.compile(r"'name':\s*\"(.*?)\",\s*\n\s*'verified'", re.S),
    "annual_gbp":   re.compile(r"'annual_gross_gbp':\s*accounting\.formatMoney\(\"(-?\d+)\""),
    "annual_eur":   re.compile(r"'annual_gross_eur':\s*accounting\.formatMoney\(\"(-?\d+)\""),
    "age":          re.compile(r"'age':\s*Math\.round\(\"(\d+)\"\)"),
    "position":     re.compile(r"'position':\s*\"([A-Za-z]*)\""),
    "position_detail": re.compile(r"'position_detail':\s*\"([A-Za-z]*)\""),
    "country":      re.compile(r"'country':\s*\"([^\"]*)\""),
    "club_raw":     re.compile(r"'club':\s*\"(.*?)\",\s*\n\s*'active'", re.S),
    "signed":       re.compile(r"'signed':\s*moment\(\"([^\"]*)\""),
    "expiration":   re.compile(r"'expiration':\s*moment\(\"([^\"]*)\""),
    "years":        re.compile(r"'years':\s*\"([^\"]*)\""),
    "active":       re.compile(r"'active':\s*\"([^\"]*)\""),
    "loan":         re.compile(r"'loan':\s*\"([^\"]*)\""),
}
_HREF_RE = re.compile(r"/player/([a-z0-9-]+?)-(\d+)/")


def _grp(key: str, seg: str) -> str | None:
    m = _FIELD_RES[key].search(seg)
    return m.group(1) if m else None


def parse_page(html: str, cc: str, slug: str, season: str) -> list[dict]:
    i = html.find("var data = [")
    if i < 0:
        return []
    j = html.find("];", i)
    blob = html[i:j] if j > 0 else html[i:]
    segments = ["{'name':" + s for s in _OBJ_SPLIT_RE.split(blob)[1:]]
    rows = []
    for seg in segments:
        m = _FIELD_RES["name_raw"].search(seg)
        if not m:
            continue
        name_html = m.group(1)
        # Capology names can carry literal HTML entities the same way Understat's do
        # (see ingest/crosswalk.py::norm_player) — unescape before they reach the join.
        name = _html_unescape(_TAG_RE.sub("", name_html).strip())
        href = _HREF_RE.search(name_html)
        capology_id = href.group(2) if href else None
        gbp_m = _FIELD_RES["annual_gbp"].search(seg)
        eur_m = _FIELD_RES["annual_eur"].search(seg)
        annual_gbp = float(gbp_m.group(1)) if gbp_m and gbp_m.group(1) else None
        annual_eur = float(eur_m.group(1)) if eur_m and eur_m.group(1) else None
        if not annual_gbp and not annual_eur:
            continue  # no salary data for this row (undisclosed) -> skip, don't fabricate
        club_m = _FIELD_RES["club_raw"].search(seg)
        club = _html_unescape(_TAG_RE.sub("", club_m.group(1)).strip()) if club_m else None
        age = _grp("age", seg)
        rows.append(dict(
            capology_id=capology_id,
            player=name,
            season=season,
            league_cc=cc,
            league_slug=slug,
            annual_gross_gbp=annual_gbp,
            annual_gross_eur=annual_eur,
            age=int(age) if age else None,
            position=_grp("position", seg) or None,
            position_detail=_grp("position_detail", seg),
            country=_grp("country", seg),
            club=club,
            signed=_grp("signed", seg),
            expiration=_grp("expiration", seg),
            contract_years=_grp("years", seg),
            active=_grp("active", seg),
            loan=_grp("loan", seg),
        ))
    return rows


def parse_all_cached() -> pd.DataFrame:
    frames = []
    for path in sorted(RAW_DIR.glob("*.html")):
        cc, slug, season = path.stem.split("_", 2)
        html = path.read_text(encoding="utf-8", errors="ignore")
        rows = parse_page(html, cc, slug, season)
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["position"] = df["position"].replace({"": None})
    return df


# ------------------------------------------------------------------ crosswalk + build

def _season_sort_key(s: str) -> str:
    # 'current' sorts last; 'YYYY' and 'YYYY-YYYY' sort naturally by their start year
    if s == "current":
        return "9999"
    return s[:4]


def crosswalk_to_tm(cap: pd.DataFrame) -> pd.DataFrame:
    """Capology player -> tm_player_id, reusing wages_fifa.crosswalk()'s unique-name
    matching passes (its dob-based passes no-op here since Capology has no dob; the
    unique-nname / unique-cname passes are the real matching logic and are shared
    verbatim rather than re-implemented).

    Identity key is (capology_id, normalised name), NOT bare capology_id: Capology
    recycles its internal player ids across different real players over time (found
    empirically -- id 34178 is "harry-kane" on one season page and "niklas-lomb" on
    another). A composite key keeps those apart; a bare id would silently merge them.
    """
    cap = cap.copy()
    cap["nname"] = cap["player"].map(wages_fifa._norm)
    cap["match_key"] = cap["capology_id"].astype(str) + "|" + cap["nname"]

    # one representative row per match_key (its most recent season) to match on
    rep = (cap.sort_values("season", key=lambda s: s.map(_season_sort_key))
              .drop_duplicates("match_key", keep="last")
              .copy())
    rep["sofifa_id"] = pd.factorize(rep["match_key"])[0]
    rep["long_name"] = rep["player"]
    rep["cname"] = rep["nname"].map(wages_fifa._cname)
    rep["dob"] = None
    rep["overall"] = None
    rep["wage_eur"] = rep["annual_gross_eur"].fillna(0)
    rep["value_eur"] = 0
    rep["league_name"] = rep["league_slug"]
    rep["edition_year"] = rep["season"]

    tm = wages_fifa.load_tm()
    matched = wages_fifa.crosswalk(rep, tm)  # -> sofifa_id, player_id(=tm_player_id), ...
    id_map = dict(zip(matched["sofifa_id"], matched["player_id"]))
    rep["tm_player_id"] = rep["sofifa_id"].map(id_map)
    key_to_tm = dict(zip(rep["match_key"], rep["tm_player_id"]))
    out = cap.copy()
    out["tm_player_id"] = out["match_key"].map(key_to_tm)
    return out


def build() -> pd.DataFrame:
    cap = parse_all_cached()
    if cap.empty:
        raise FileNotFoundError(
            f"no cached pages in {RAW_DIR} — run fetch(confirm=True) first")
    cap = crosswalk_to_tm(cap)
    ALL_SEASONS_OUT.parent.mkdir(parents=True, exist_ok=True)
    cap.to_parquet(ALL_SEASONS_OUT, index=False)

    matched = cap.dropna(subset=["tm_player_id"])
    n_players = cap["match_key"].nunique()
    n_matched_players = matched["match_key"].nunique()
    print(f"parsed rows:       {len(cap):,}  ({n_players:,} unique players, "
          f"{cap['season'].nunique()} league-seasons)")
    print(f"crosswalked to TM: {len(matched):,} rows "
          f"({n_matched_players:,}/{n_players:,} players = "
          f"{100*n_matched_players/max(n_players,1):.0f}%)")

    latest = (matched.sort_values("season", key=lambda s: s.map(_season_sort_key))
                      .drop_duplicates("tm_player_id", keep="last")
                      .copy())
    latest["tm_player_id"] = latest["tm_player_id"].astype(int)
    out = pd.DataFrame({
        "Player": latest["player"],
        "Annual Gross": latest["annual_gross_gbp"].fillna(latest["annual_gross_eur"] * 0.85),
        "Season": latest["season"],
        "League": latest["league_slug"],
        "Country": latest["country"],
        "Position": latest["position"],
        "Club": latest["club"],
        "Signed": latest["signed"],
        "Expiration": latest["expiration"],
        "Contract Years": latest["contract_years"],
        "tm_player_id": latest["tm_player_id"],
    })
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CSV_OUT, index=False)
    print(f"wrote {CSV_OUT} ({len(out):,} players, latest season each)")
    print(f"wrote {ALL_SEASONS_OUT} ({len(cap):,} rows, full history)")
    return cap


def load_latest() -> pd.DataFrame:
    """tm_player_id -> best (latest-season) real Capology wage. Empty if not built."""
    if not CSV_OUT.exists():
        return pd.DataFrame(columns=["tm_player_id", "annual_wage_gbp"])
    from ingest.wages import load_capology_csv
    df = load_capology_csv(CSV_OUT)
    return df.dropna(subset=["tm_player_id"])


# ------------------------------------------------------------------ check

def _check():
    sample = """
    var data = [{
            'name': "<a class='firstcol' href='/player/erling-haaland-36728/'><img src='x.svg'>Erling Haaland</a>",
            'verified':"<img/>",
            'weekly_gross_gbp': accounting.formatMoney("27300000"/52, "£ ", 0),
            'annual_gross_eur': accounting.formatMoney("32012451", "€ ", 0),
            'annual_gross_gbp': accounting.formatMoney("27300000", "£ ", 0),
            'position': "F",
            'position_detail': "CF",
            'age': Math.round("25"),
            'country': "Norway",
            'club': "<a href='/club/manchester-city/salaries/'>Manchester City</a>",
            'active': "True",
            'signed': moment("2025-01-17").format("MMM D, YYYY"),
            'expiration': moment("2034-06-30").format("MMM D, YYYY"),
            'years': "8",
            'loan': "False",
          },{
            'name': "<a href='/player/no-salary-99999/'>No Salary Guy</a>",
            'verified':"<img/>",
            'annual_gross_gbp': accounting.formatMoney(""/52, "£ ", 0),
            'annual_gross_eur': accounting.formatMoney("", "€ ", 0),
            'position': "D",
            'age': Math.round("22"),
            'country': "England",
            'club': "<a href='/club/x/'>X</a>",
            'active': "True",
            'signed': moment("").format("MMM D, YYYY"),
            'expiration': moment("").format("MMM D, YYYY"),
            'years': "",
            'loan': "False",
          },{
            'name': "<a href='/player/ngolo-kante-999/'>N&#039;Golo Kant&eacute;</a>",
            'verified':"<img/>",
            'annual_gross_gbp': accounting.formatMoney("5000000", "£ ", 0),
            'annual_gross_eur': accounting.formatMoney("5850000", "€ ", 0),
            'position': "M",
            'age': Math.round("28"),
            'country': "France",
            'club': "<a href='/club/x/'>X</a>",
            'active': "True",
            'signed': moment("").format("MMM D, YYYY"),
            'expiration': moment("").format("MMM D, YYYY"),
            'years': "",
            'loan': "False",
          }];
    """
    rows = parse_page(sample, "uk", "premier-league", "2025-2026")
    assert len(rows) == 2, rows  # the undisclosed-salary row must be dropped, not fabricated
    r = rows[0]
    assert r["player"] == "Erling Haaland", r
    assert r["annual_gross_gbp"] == 27_300_000, r
    assert r["capology_id"] == "36728", r
    assert r["age"] == 25 and r["position"] == "F" and r["country"] == "Norway"
    assert r["club"] == "Manchester City"
    assert r["expiration"] == "2034-06-30"
    assert rows[1]["player"] == "N'Golo Kanté", rows[1]  # HTML entities must be unescaped

    assert _season_sort_key("2025-2026") == "2025"
    assert _season_sort_key("2022") == "2022"
    assert _season_sort_key("current") == "9999"

    print("parser + season-sort ok (offline, no network)")


if __name__ == "__main__":
    if "fetch" in sys.argv[1:]:
        fetch(confirm="--yes" in sys.argv[1:])
    elif "build" in sys.argv[1:]:
        build()
    else:
        _check()
