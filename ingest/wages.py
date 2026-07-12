"""Wages — modelled estimates, quality-flagged. The weakest input, and it says so.

No free audited wage dump exists (see DATA_SOURCES.md, grade D). Capology and
Spotrac publish on-site *estimates* not licensed for redistribution, so we do
not scrape them. Instead this module ships a small parametric wage model
anchored to publicly reported salaries, and every number it emits carries a
`source` flag and a wide interval. There is no API that returns a bare wage.

Model (log-linear, fitted to the ANCHORS below at import time):

    wage = K_EPL * league_mult * (MV_eur_m ^ 0.75) * age_mult(age) * pos_mult

grounded in three well-documented empirical regularities:
  * wages scale with market value with elasticity < 1 (superstar-pay
    literature, e.g. Lucifora & Simmons 2003; Garcia-del-Barrio & Pujol 2007);
  * wage levels differ sharply by league (Sporting Intelligence GSSS:
    EPL >> Ligue 1 ex-PSG);
  * wages peak later than market value — MV peaks ~26-27, pay peaks ~29-31
    because contracts reprice with a lag and reward past output. This is why
    a 23yo at €180m MV earns less than a 31yo at €80m MV.

Future upgrade paths (documented, not built):
  * Capology manual snapshot: browse capology.com yourself, copy a league
    salary table into a CSV, drop it at data/wages/capology.csv, load with
    `load_capology_csv()`. Rows come back flagged source='capology_estimate'
    and slot in ahead of the model without code changes downstream (consumers
    key off the `source` column, which is always present).
  * FIFA/FM ordinal prior: Kaggle `ultimus/football-salaries-dataset` (and
    FM24-derived files) hold game-estimated wages — useful only as a *ranking*
    prior, and Kaggle needs an API token we don't have. If a token appears:
    `kaggle datasets download ultimus/football-salaries-dataset` into
    data/wages/ and join on player name; keep source='fifa_prior'.

Reliability, honestly: modelled numbers are directionally right (league,
age, MV gradient) and individually unreliable — anchors reproduce within
about ±25%, so the shipped interval is x/÷1.55 (-35%/+55%). Per SPEC.md,
every downstream output that touches these must surface the flag.
"""
from __future__ import annotations
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "wages"

# --- anchors: PUBLICLY reported salaries (weekly gross GBP) + contemporaneous
# Transfermarkt MV. Citations in-line; all widely reported figures, not filings.
_WEEKS = 52
ANCHORS = [
    # De Bruyne, Man City 2021 renewal: ~£400k/wk widely reported (BBC/Guardian,
    # Apr 2021); TM value then ~€100m; age 30.
    dict(player="De Bruyne", weekly_gbp=400_000, mv_eur_m=100.0, age=30),
    # Haaland, Man City: ~£375k/wk per 2023 reporting (The Athletic/Sky);
    # TM value €180m (Dec 2023); age 23.
    dict(player="Haaland", weekly_gbp=375_000, mv_eur_m=180.0, age=23),
    # Salah, Liverpool 2022 renewal: ~£350k/wk widely reported (BBC, Jul 2022);
    # TM value then ~€65m; age 30.
    dict(player="Salah", weekly_gbp=350_000, mv_eur_m=65.0, age=30),
    # League-average anchor: Sporting Intelligence GSSS 2019 put EPL average
    # first-team pay at ~£3.0m/yr; ~£3.9m by ~2023 with wage inflation.
    # Average EPL squad member: TM value ~€18m, age ~26.
    dict(player="_epl_average", weekly_gbp=75_000, mv_eur_m=18.0, age=26),
]

# wage-vs-MV elasticity < 1 (see docstring). Calibration knob.
ELASTICITY = 0.75

# Age multiplier knots: pay ramps steeply through the early 20s (first big
# contracts lag MV), peaks ~30, declines gently — later than the MV peak.
_AGE_KNOTS = np.array([17, 21, 24, 27, 30, 32, 34, 36, 40], dtype=float)
_AGE_MULT = np.array([0.35, 0.55, 0.72, 0.92, 1.00, 0.97, 0.88, 0.78, 0.60])

# League multipliers vs EPL. Level differences from Sporting Intelligence
# GSSS 2019 average first-team pay (EPL ~£3.0m, La Liga ~£2.5m, Serie A ~£1.9m,
# Bundesliga ~£1.7m, Ligue 1 ~£1.0m ex-PSG), shrunk toward 1 because MV already
# absorbs part of the league effect when we condition on it.
LEAGUE_MULT = {
    "ENG-Premier League": 1.00,
    "ESP-La Liga":        0.85,
    "ITA-Serie A":        0.72,
    "GER-Bundesliga":     0.68,
    "FRA-Ligue 1":        0.55,   # ex-PSG; PSG pays EPL-level
}
_OTHER_LEAGUE_MULT = 0.40         # selling leagues; widest uncertainty

# Mild position effect (Capology distributions: keepers paid least,
# forwards command a premium at equal profile).
POSITION_MULT = {"GK": 0.85, "DF": 0.95, "MF": 1.00, "FW": 1.05}

# Interval: x/÷1.55 => -35% / +55%. Covers every anchor's residual; spec
# floor is ±30%. Unknown leagues get x/÷1.9.
_BAND = 1.55
_BAND_OTHER = 1.9


def _age_mult(age: float) -> float:
    return float(np.interp(float(age), _AGE_KNOTS, _AGE_MULT))


def _fit_k_epl() -> float:
    """EPL scale constant: geometric mean of the K implied by each anchor."""
    ks = [a["weekly_gbp"] * _WEEKS / (a["mv_eur_m"] ** ELASTICITY * _age_mult(a["age"]))
          for a in ANCHORS]
    return float(np.exp(np.mean(np.log(ks))))


K_EPL = _fit_k_epl()   # ~£0.64m/yr per unit of MV^0.75 at peak age


class WageEstimate(NamedTuple):
    """A wage never travels without its interval and quality flag."""
    annual_wage_gbp: float
    lo: float
    hi: float
    source: str        # always 'modelled' from estimate_wage()


# Real-wage tables are consulted first when a tm id is given, best grade first:
# Capology (grade-B, real reported salary) beats the FIFA prior (grade-C, game
# estimate) beats the parametric model (grade-C/D, pure proxy). Lazily loaded +
# cached so importing wages stays cheap and there's no import cycle.
_UNSET = object()
_FIFA_CACHE = _UNSET
_CAPOLOGY_CACHE = _UNSET
_CAPOLOGY_BAND = 1.15   # real reported figure -> tight interval (excludes bonuses/image rights)


def _fifa_row(tm_player_id):
    global _FIFA_CACHE
    if _FIFA_CACHE is _UNSET:
        try:
            from ingest import wages_fifa
            _FIFA_CACHE = wages_fifa.load().set_index("tm_player_id")
        except (FileNotFoundError, ImportError, OSError):
            _FIFA_CACHE = None            # table not built -> silently fall back to model
    if _FIFA_CACHE is None or tm_player_id not in _FIFA_CACHE.index:
        return None
    return _FIFA_CACHE.loc[tm_player_id]


def _capology_row(tm_player_id):
    global _CAPOLOGY_CACHE
    if _CAPOLOGY_CACHE is _UNSET:
        try:
            df = load_capology_csv()
            df = df.dropna(subset=["tm_player_id"])
            df["tm_player_id"] = df["tm_player_id"].astype(int)
            _CAPOLOGY_CACHE = df.drop_duplicates("tm_player_id", keep="last").set_index("tm_player_id")
        except (FileNotFoundError, OSError, ValueError, KeyError):
            _CAPOLOGY_CACHE = None        # csv not built / no tm_player_id col -> fall back
    if _CAPOLOGY_CACHE is None or tm_player_id not in _CAPOLOGY_CACHE.index:
        return None
    return _CAPOLOGY_CACHE.loc[tm_player_id]


def estimate_wage(age, league, market_value, position="MF", tm_player_id=None) -> WageEstimate:
    """Annual gross wage in GBP with a wide interval.

    If `tm_player_id` is given, prefers a real wage over any proxy, best grade
    first: a Capology row (source='capology_estimate', grade-B real reported
    salary) beats a FIFA-prior row (source='fifa_prior', grade-C game estimate)
    beats the parametric model (source='modelled'). Existing positional callers
    are unaffected — the real-wage lookup only engages when a tm id is passed.

    age: years. league: key of LEAGUE_MULT (unknown -> generic multiplier, wider band).
    market_value: Transfermarkt value in EUR millions. position: GK/DF/MF/FW.
    """
    if tm_player_id is not None:
        c = _capology_row(tm_player_id)
        if c is not None:
            w = float(c.annual_wage_gbp)
            return WageEstimate(w, w / _CAPOLOGY_BAND, w * _CAPOLOGY_BAND, "capology_estimate")
        r = _fifa_row(tm_player_id)
        if r is not None:
            return WageEstimate(float(r.wage_gbp), float(r.lo), float(r.hi), "fifa_prior")
    mv = float(market_value)
    if not mv > 0:
        raise ValueError("market_value (EUR millions) must be > 0")
    known = league in LEAGUE_MULT
    lg = LEAGUE_MULT.get(league, _OTHER_LEAGUE_MULT)
    pos = POSITION_MULT.get(str(position)[:2].upper(),
                            POSITION_MULT.get(str(position)[:1].upper(), 1.0))
    w = K_EPL * lg * mv ** ELASTICITY * _age_mult(age) * pos
    band = _BAND if known else _BAND_OTHER
    return WageEstimate(round(w), round(w / band), round(w * band), "modelled")


def load_capology_csv(path=DATA_DIR / "capology.csv") -> pd.DataFrame:
    """Load a manually saved Capology table (user pastes from browser).

    Tolerant of Capology's column headers ('Player', 'Weekly Gross',
    'Annual Gross', ...) and of '£1,234' formatting. Needs a player column
    plus a weekly or annual gross column. Returns columns
    [player, annual_wage_gbp, source] (+ any extras passed through),
    every row flagged source='capology_estimate'.
    """
    df = pd.read_csv(path)
    cols = {c.strip().lower().replace(" ", "_"): c for c in df.columns}

    def _num(series):
        return pd.to_numeric(
            series.astype(str).str.replace(r"[£€$,]", "", regex=True),
            errors="coerce")

    player_col = next((cols[k] for k in ("player", "name") if k in cols), None)
    if player_col is None:
        raise ValueError(f"no player/name column in {path}: {list(df.columns)}")
    if "annual_gross" in cols:
        annual = _num(df[cols["annual_gross"]])
    elif "weekly_gross" in cols:
        annual = _num(df[cols["weekly_gross"]]) * _WEEKS
    else:
        raise ValueError(f"no weekly_gross/annual_gross column in {path}")

    out = df.copy()
    out["player"] = df[player_col].astype(str).str.strip()
    out["annual_wage_gbp"] = annual
    out["source"] = "capology_estimate"
    return out.dropna(subset=["annual_wage_gbp"]).reset_index(drop=True)


def _check():
    # 1. plausibility band: 27yo EPL player at €80m MV -> £150k-£450k/wk
    est = estimate_wage(27, "ENG-Premier League", 80, "MF")
    wk = est.annual_wage_gbp / _WEEKS
    assert 150_000 <= wk <= 450_000, wk
    assert est.source == "modelled"
    assert est.lo < est.annual_wage_gbp < est.hi

    # 2. interval at least ±30%
    assert est.hi >= 1.3 * est.annual_wage_gbp
    assert est.lo <= est.annual_wage_gbp / 1.3

    # 3. monotone in market value
    ws = [estimate_wage(27, "ENG-Premier League", mv).annual_wage_gbp
          for mv in (2, 10, 30, 80, 150)]
    assert ws == sorted(ws) and len(set(ws)) == len(ws), ws

    # 4. league ordering: EPL > La Liga > Ligue 1 > unknown, same profile
    def w(lg):
        return estimate_wage(27, lg, 40).annual_wage_gbp
    assert w("ENG-Premier League") > w("ESP-La Liga") > w("FRA-Ligue 1") > w("NED-Eredivisie")
    # unknown league -> wider band
    assert (estimate_wage(27, "NED-Eredivisie", 40).hi / estimate_wage(27, "NED-Eredivisie", 40).annual_wage_gbp
            > est.hi / est.annual_wage_gbp)

    # 5. wages peak later than MV: 30 > 24 and 30 > 37, same MV
    a24, a30, a37 = (estimate_wage(a, "ENG-Premier League", 50).annual_wage_gbp
                     for a in (24, 30, 37))
    assert a30 > a24 and a30 > a37

    # 6. position: FW > GK
    assert (estimate_wage(27, "ENG-Premier League", 40, "FW").annual_wage_gbp
            > estimate_wage(27, "ENG-Premier League", 40, "GK").annual_wage_gbp)

    # 7. anchors reproduced within the shipped interval (x/÷1.55)
    for a in ANCHORS:
        pred = K_EPL * a["mv_eur_m"] ** ELASTICITY * _age_mult(a["age"])
        actual = a["weekly_gbp"] * _WEEKS
        ratio = actual / pred
        assert 1 / _BAND <= ratio <= _BAND, (a["player"], round(ratio, 2))

    # 8. capology loader: header/format tolerance + flag
    import io
    csv = io.StringIO(
        "Player,Weekly Gross,Age\nMohamed Salah,\"£350,000\",30\nBad Row,n/a,29\n")
    cap = load_capology_csv(csv)
    assert len(cap) == 1
    assert cap.iloc[0].annual_wage_gbp == 350_000 * _WEEKS
    assert (cap.source == "capology_estimate").all()

    # 9. tm_player_id path: unknown id -> modelled fallback (identical to no-id call);
    #    a real id (if the FIFA table is built) -> fifa_prior.
    base = estimate_wage(27, "ENG-Premier League", 80, "MF")
    miss = estimate_wage(27, "ENG-Premier League", 80, "MF", tm_player_id=-1)
    assert miss == base and miss.source == "modelled", miss
    try:
        from ingest import wages_fifa
        fifa_ids = wages_fifa.load().tm_player_id
        try:
            cap_only_ids = set(load_capology_csv().dropna(subset=["tm_player_id"]).tm_player_id.astype(int))
        except (FileNotFoundError, OSError, ValueError, KeyError):
            cap_only_ids = set()
        fifa_only = fifa_ids[~fifa_ids.isin(cap_only_ids)]
        some_id = int(fifa_only.iloc[0]) if len(fifa_only) else int(fifa_ids.iloc[0])
        hit = estimate_wage(27, "ENG-Premier League", 80, "MF", tm_player_id=some_id)
        assert hit.source == "fifa_prior" and hit.lo < hit.annual_wage_gbp < hit.hi
        print(f"fifa_prior path ok (tm {some_id}: £{hit.annual_wage_gbp/_WEEKS:,.0f}/wk)")
    except FileNotFoundError:
        print("fifa table not built yet; fallback path verified")

    # 10. capology path: a tm id with a real Capology row must return the real
    # number (source='capology_estimate'), NOT the FIFA prior -- this is the
    # exact self-check the harvest brief asks for.
    try:
        cap_tbl = load_capology_csv().dropna(subset=["tm_player_id"])
        if len(cap_tbl):
            cap_id = int(cap_tbl.iloc[0].tm_player_id)
            expected = float(cap_tbl.iloc[0].annual_wage_gbp)
            hit = estimate_wage(27, "ENG-Premier League", 80, "MF", tm_player_id=cap_id)
            assert hit.source == "capology_estimate", hit
            assert hit.annual_wage_gbp == expected, (hit.annual_wage_gbp, expected)
            print(f"capology_estimate path ok (tm {cap_id}: £{hit.annual_wage_gbp/_WEEKS:,.0f}/wk, "
                  f"beats fifa_prior when both exist)")
        else:
            print("capology.csv has no crosswalked rows yet; fallback path verified")
    except FileNotFoundError:
        print("capology.csv not built yet; fallback path verified")

    print(f"K_EPL = £{K_EPL:,.0f}/yr per MV^{ELASTICITY} at peak age")
    print(f"27yo EPL €80m MF: £{wk:,.0f}/wk  "
          f"[£{est.lo / _WEEKS:,.0f} - £{est.hi / _WEEKS:,.0f}]  source={est.source}")
    for a in ANCHORS:
        e = estimate_wage(a["age"], "ENG-Premier League", a["mv_eur_m"])
        print(f"  {a['player']:>14}: reported £{a['weekly_gbp']:,}/wk, "
              f"modelled £{e.annual_wage_gbp / _WEEKS:,.0f}/wk")
    print("ok")


if __name__ == "__main__":
    _check()
