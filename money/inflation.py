"""Stage 10b — Football transfer-fee inflation index + scaling function.

WHAT THIS IS
------------
A *sector-specific* price index for football transfer fees. It answers "what is a
1996 fee worth in 2022 pounds?" the right way: not by CPI (consumer prices), but by
measuring how much the *price of an equivalent player* moved, holding quality constant.

The engine is a hedonic regression with YEAR FIXED EFFECTS:

    log(fee) ~ C(season) + age + age^2 + C(position) + to_top5  [+ log(market_value)]

exp(year fixed-effect) IS the pure inflation index — the price change after holding
player age / position / destination-tier (and optionally market value) constant. This
is the gold standard because repeat-sales indexing is impossible (a player is never
re-sold in identical condition). See MODELS.md and INFLATION_FINDINGS.md.

THREE INDICES, NOT ONE (the thesis is that a single scalar rate is a lie):
  * naive     — yearly p50 / mean / total-spend. Biased by coverage & tail. FOIL ONLY.
  * hedonic   — the real deliverable. Segments: all / elite (p90+) / median / fwd / nonfwd.
  * premium   — fee vs market value (2005+). Isolates over/under-payment vs MV. Reading:
                most fee inflation IS market-value inflation; the pure premium moved little.

DATA & GATE (audited in INFLATION_AUDIT.md)
  * Source: data/merged/transfers_canonical.parquet, permanent transfers, positive fee,
    fee_suspect==False (removes the corrupt €500m rows). Fees single-currency (EUR).
  * Valid range 1992–2025 (extended from 2022 by the Lane B raw-fee harvest, 2026-07 — see
    LANE_B_HARVEST.md). 2026+ excluded: window still open, a real partial-year effect, not a
    sourcing gap. scale_fee() flags any year outside the range.
  * market_value present ~0% pre-2004, ~97% from 2012 → premium index is 2005+ only.

Run:
  python3 -m money.inflation build   -> refit, persist index tables, write the two MD docs
  python3 -m money.inflation         -> load persisted index, run §5 self-checks (PASS/FAIL)
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")  # statsmodels/pandas chatter; results asserted in _selfcheck

ROOT = Path(__file__).resolve().parent.parent
CANON = ROOT / "data" / "merged" / "transfers_canonical.parquet"
INDEX_CSV = ROOT / "data" / "money" / "inflation_index.csv"
META_JSON = ROOT / "data" / "money" / "inflation_meta.json"

BASE_YEAR = 2010          # index = 100 here (reference level in the FE regression)
# Lane B harvest (2026-07): fixed a fee-fill dedup bug + added a raw-harvest-sourced 2023+
# extension (ingest/merge.py) -> permanent+fee coverage 2023-2025 now 15-23%, in line with
# 2020/2021 (already-valid years), so the gate extends 2022->2025. 2026 stays excluded: the
# transfer window is still open (mid-season snapshot), coverage is a real partial-year effect,
# not a reporting-lag artifact -- extending into it would be measuring an incomplete market.
YEAR_MIN, YEAR_MAX = 1992, 2025   # validated range; MV-premium starts 2005
PREMIUM_MIN = 2005
HEDONIC_FORMULA = (
    "lfee ~ C(_s, Treatment(reference=@BASE)) + age + age2 + C(pos) + to_top5"
)

# --- UK CPI, annual average, index 2015=100 (ONS series D7BT, approximate). --------
# Used ONLY as a directional benchmark for the football-vs-CPI multiple, never as a
# deflator. Rebased to BASE_YEAR=100 at use.
UK_CPI_2015_100 = {
    1992: 62.9, 1993: 63.9, 1994: 65.4, 1995: 67.7, 1996: 69.3, 1997: 71.0,
    1998: 72.4, 1999: 73.4, 2000: 74.0, 2001: 74.9, 2002: 76.0, 2003: 77.1,
    2004: 78.1, 2005: 79.7, 2006: 81.5, 2007: 83.4, 2008: 86.4, 2009: 88.3,
    2010: 91.2, 2011: 95.3, 2012: 98.0, 2013: 100.5, 2014: 102.0, 2015: 102.7,
    2016: 103.4, 2017: 106.2, 2018: 108.8, 2019: 110.7, 2020: 111.8, 2021: 114.6,
    2022: 124.6,
}

SEGMENTS = ("all", "elite", "median", "fwd", "nonfwd", "premium")

# Per-segment validity ceiling. The Lane-B raw harvest extended coverage to 2025, but the
# 2023+ market has a COMPOSITION BREAK the segmented models can't absorb: the Saudi Pro League
# tier (Al-Nassr/Al-Hilal/Al-Qadsiah…) pays €70–77m to NON-top-5 destinations, which the
# binary `to_top5` control reads as "should be cheap" — so the elite year-FE explodes to explain
# them (elite index hit ~1260 in 2025, a nonsense £425m Shearer-scale). Elite n is only ~100/yr
# post-2022, far too thin to re-identify a new destination tier. So the robust bulk indices
# (all/median/nonfwd) validate to 2025; the tail/thin ones (elite/fwd/premium) stay gated at 2022.
SEGMENT_VALID_MAX = {"all": YEAR_MAX, "median": YEAR_MAX, "nonfwd": YEAR_MAX,
                     "elite": 2022, "fwd": 2022, "premium": 2022}


# ===========================================================================
# frame
# ===========================================================================
def build_frame() -> pd.DataFrame:
    """Clean modelling universe: permanent, positive-fee, non-suspect, 1992–2022, aged."""
    df = pd.read_parquet(CANON)
    m = df[
        (df.transfer_type == "permanent")
        & (df.fee_eur > 0)
        & (~df.fee_suspect)
        & (df.season.between(YEAR_MIN, YEAR_MAX))
        & (df.player_age.notna())
    ].copy()
    m["lfee"] = np.log(m.fee_eur)
    m["age"] = m.player_age.astype(float)
    m["age2"] = m["age"] ** 2
    m["to_top5"] = m.to_is_top5.eq(True).fillna(False).astype(int)
    m["pos"] = m.pos_group.fillna("UNK")
    # season-relative elite split (top decile of fee within its season)
    m["_p90"] = m.groupby("season").fee_eur.transform(lambda x: x.quantile(0.90))
    m["elite"] = m.fee_eur >= m["_p90"]
    return m


# ===========================================================================
# hedonic year-FE fit  (exp(year FE) = the index)
# ===========================================================================
def _factor_singletons(m: pd.DataFrame, col: str, offset: int) -> np.ndarray:
    """Dense non-negative cluster labels; rows missing `col` become their own singleton
    cluster (the standard convention — conservative, valid for cluster-robust SEs)."""
    v = pd.to_numeric(m[col], errors="coerce").to_numpy()
    v = np.where(np.isnan(v), -(np.arange(len(m)) + 1 + offset), v)
    return pd.factorize(v)[0]


def fit_yearfe(m: pd.DataFrame, with_mv: bool = False) -> tuple[pd.DataFrame, float, dict]:
    """Fit the hedonic and return (index_df, r2, controls). Two-way cluster-robust SEs
    (player & selling club). index_df: season, index, ci_lo, ci_hi, log_se, n."""
    import statsmodels.formula.api as smf

    m = m.copy()
    formula = HEDONIC_FORMULA.replace("@BASE", str(BASE_YEAR))
    if with_mv:
        m = m[(m.season >= PREMIUM_MIN) & (m.market_value_eur > 0)].copy()
        m["lmv"] = np.log(m.market_value_eur)
        formula = formula + " + lmv"
    groups = np.column_stack(
        [_factor_singletons(m, "player_id", 0), _factor_singletons(m, "from_club_id", 10**7)]
    )
    m["_s"] = pd.Categorical(m.season, categories=sorted(m.season.unique()))
    res = smf.ols(formula, data=m).fit(cov_type="cluster", cov_kwds={"groups": groups})

    n_by_season = m.groupby("season").size()
    rows = []
    for yr in sorted(m.season.unique()):
        if yr == BASE_YEAR:
            b, se = 0.0, 0.0
        else:
            key = [c for c in res.params.index if f"[T.{yr}]" in c]
            if not key:
                continue
            b, se = res.params[key[0]], res.bse[key[0]]
        rows.append(
            dict(
                season=int(yr),
                index=100 * np.exp(b),
                ci_lo=100 * np.exp(b - 1.96 * se),
                ci_hi=100 * np.exp(b + 1.96 * se),
                log_se=se,
                n=int(n_by_season.get(yr, 0)),
            )
        )
    controls = dict(
        age=float(res.params.get("age", np.nan)),
        age2=float(res.params.get("age2", np.nan)),
        to_top5=float(res.params.get("to_top5", np.nan)),
        lmv=float(res.params.get("lmv", np.nan)) if with_mv else None,
    )
    return pd.DataFrame(rows), float(res.rsquared), controls


def naive_index(m: pd.DataFrame) -> pd.DataFrame:
    """Biased foil: yearly p50, mean and total spend of positive permanent fees (€m),
    each rebased to BASE_YEAR=100."""
    g = m.groupby("season").fee_eur
    out = pd.DataFrame(
        dict(p50=g.median() / 1e6, mean=g.mean() / 1e6, spend=g.sum() / 1e6, n=g.size())
    ).reset_index()
    for c in ("p50", "mean", "spend"):
        base = out.loc[out.season == BASE_YEAR, c].iloc[0]
        out[c + "_idx"] = 100 * out[c] / base
    return out


# ===========================================================================
# structural breaks & regimes
# ===========================================================================
CANDIDATE_BREAKS = {
    1995: "Bosman", 2003: "Abramovich", 2008: "Man City/ADUG", 2011: "PSG/QSI",
    2017: "Neymar €222m", 2020: "COVID", 2022: "Chelsea/Saudi PIF",
}


def detect_regimes(index_df: pd.DataFrame, n_bkps: int = 4) -> list[dict]:
    """Bai–Perron-style breakpoints on the log-index via `ruptures` (Binseg, l2), then
    the CAGR within each detected regime. Returns [{start,end,cagr_pct,label}]."""
    import ruptures as rpt

    s = index_df.sort_values("season")
    y = np.log(s["index"].to_numpy())
    yrs = s["season"].to_numpy()
    algo = rpt.Binseg(model="l2").fit(y)
    bkps = algo.predict(n_bkps=min(n_bkps, len(y) - 2))  # indices into y (exclusive ends)
    regimes, start = [], 0
    for end in bkps:
        seg_yrs = yrs[start:end]
        i0, i1 = s["index"].iloc[start], s["index"].iloc[end - 1]
        span = seg_yrs[-1] - seg_yrs[0]
        cagr = (i1 / i0) ** (1 / span) - 1 if span > 0 else 0.0
        # nearest named candidate to the regime's start year
        near = min(CANDIDATE_BREAKS, key=lambda b: abs(b - seg_yrs[0]))
        label = CANDIDATE_BREAKS[near] if abs(near - seg_yrs[0]) <= 2 else ""
        regimes.append(
            dict(start=int(seg_yrs[0]), end=int(seg_yrs[-1]), cagr_pct=round(100 * cagr, 1), label=label)
        )
        start = end
    return regimes


def chow_pvalues(m: pd.DataFrame) -> dict[int, float]:
    """Chow test at each candidate break: does allowing an intercept+trend shift at year B
    significantly improve the hedonic time trend? Small p => a real regime break."""
    import statsmodels.formula.api as smf

    d = m.copy()
    d["t"] = d.season - BASE_YEAR
    d["ctrl_pos"] = d.pos
    out = {}
    for B in CANDIDATE_BREAKS:
        if not (YEAR_MIN < B < YEAR_MAX):
            continue
        d["post"] = (d.season >= B).astype(int)
        d["post_t"] = d.post * d.t
        r0 = smf.ols("lfee ~ t + age + age2 + C(ctrl_pos) + to_top5", data=d).fit()
        r1 = smf.ols("lfee ~ t + post + post_t + age + age2 + C(ctrl_pos) + to_top5", data=d).fit()
        # F-test of the two added terms (post, post_t)
        try:
            f = r1.compare_f_test(r0)
            out[B] = float(f[1])
        except Exception:
            out[B] = float("nan")
    return out


def cpi_multiple(index_df: pd.DataFrame, y0: int, y1: int) -> dict:
    """Football index growth y0->y1 vs UK CPI growth over the same window; the ratio is
    'how many times faster than consumer inflation'."""
    fi = index_df.set_index("season")["index"]
    fball = fi[y1] / fi[y0]
    cpi = UK_CPI_2015_100[y1] / UK_CPI_2015_100[y0]
    return dict(y0=y0, y1=y1, football_x=round(float(fball), 2),
                cpi_x=round(float(cpi), 2), multiple=round(float(fball / cpi), 2))


# ===========================================================================
# build & persist
# ===========================================================================
def build(write_docs: bool = True) -> pd.DataFrame:
    """Refit every segment, persist the long index table + meta, and (default) write the
    audit & findings docs. Returns the long index DataFrame."""
    m = build_frame()
    print(f"[build] clean universe: {len(m):,} permanent positive-fee transfers "
          f"({m.season.min()}–{m.season.max()})")

    segs, r2, controls = {}, {}, {}
    segs["all"], r2["all"], controls["all"] = fit_yearfe(m)
    segs["elite"], r2["elite"], _ = fit_yearfe(m[m.elite])
    segs["median"], r2["median"], _ = fit_yearfe(m[~m.elite])
    segs["fwd"], r2["fwd"], _ = fit_yearfe(m[m.pos == "FWD"])
    segs["nonfwd"], r2["nonfwd"], _ = fit_yearfe(m[m.pos != "FWD"])
    segs["premium"], r2["premium"], controls["premium"] = fit_yearfe(m, with_mv=True)

    # gate each segment to its validity ceiling (see SEGMENT_VALID_MAX) BEFORE anything
    # downstream reads it — this drops the composition-break-distorted elite/fwd/premium 2023+
    # rows so the persisted index and every doc only carry trustworthy values.
    for k in segs:
        segs[k] = segs[k][segs[k].season <= SEGMENT_VALID_MAX.get(k, YEAR_MAX)].reset_index(drop=True)

    long = pd.concat([d.assign(segment=k) for k, d in segs.items()], ignore_index=True)
    long = long[["segment", "season", "index", "ci_lo", "ci_hi", "log_se", "n"]]
    INDEX_CSV.parent.mkdir(parents=True, exist_ok=True)
    long.to_csv(INDEX_CSV, index=False)

    naive = naive_index(m)
    regimes = detect_regimes(segs["all"])
    chow = chow_pvalues(m)
    mult_9622 = cpi_multiple(segs["all"], 1996, 2022)
    mult_elite = cpi_multiple(segs["elite"], 1996, 2022)

    meta = dict(
        base_year=BASE_YEAR, valid_min=YEAR_MIN, valid_max=YEAR_MAX, premium_min=PREMIUM_MIN,
        n_transfers=int(len(m)), r2=r2, controls=controls, segments=list(SEGMENTS),
        segment_valid_max=SEGMENT_VALID_MAX,
        regimes=regimes, chow_pvalues=chow,
        cpi_multiple_all_1996_2022=mult_9622, cpi_multiple_elite_1996_2022=mult_elite,
        formula=HEDONIC_FORMULA, se="two-way cluster (player, selling club)",
    )
    META_JSON.write_text(json.dumps(meta, indent=2))
    print(f"[build] wrote {INDEX_CSV.name} ({len(long)} rows) + {META_JSON.name}")

    if write_docs:
        _write_audit(m, naive, segs)
        _write_findings(segs, naive, r2, controls, regimes, chow, mult_9622, mult_elite)
    return long


# ===========================================================================
# scaling function (the shipped deliverable)
# ===========================================================================
_CACHE: dict = {}


def _load():
    if "index" not in _CACHE:
        if not INDEX_CSV.exists():
            raise FileNotFoundError(f"{INDEX_CSV} missing — run `python3 -m money.inflation build`")
        _CACHE["index"] = pd.read_csv(INDEX_CSV)
        _CACHE["meta"] = json.loads(META_JSON.read_text())
    return _CACHE["index"], _CACHE["meta"]


def _series(segment: str) -> pd.DataFrame:
    idx, _ = _load()
    return idx[idx.segment == segment].set_index("season")


def scale_fee(fee_nominal: float, from_year: int, to_year: int, *,
              market: str = "elite", position: str | None = None,
              basis: str = "hedonic", currency: str = "GBP") -> dict:
    """Scale a nominal fee from `from_year` pounds/euros to `to_year`, using the
    football-specific index (NOT CPI).

    market   : "elite" (p90+ deals), "median" (the bulk), or "all".
    position : "FWD" routes to the forwards index (overrides market for the segment pick).
    basis    : "hedonic" (year-FE, authoritative) or "naive" (biased foil, diagnostic only).
    Returns  : {scaled_fee, index_from, index_to, multiplier, ci_low, ci_high, basis,
                segment, caveats}. ci_* propagate the log-SE of both endpoints.

    Never falls back to CPI. If a year is outside the validated range, the multiplier is
    returned but `caveats` fires loudly.
    """
    idx, meta = _load()
    caveats = []

    seg = {"elite": "elite", "median": "median", "all": "all"}.get(market, "all")
    if position and str(position).upper() == "FWD":
        seg = "fwd"
    elif position and str(position).upper() in ("DEF", "MID", "GK"):
        seg = "nonfwd"

    if basis == "naive":
        caveats.append("naive basis is a biased foil (coverage/tail-driven); not for real scaling")
        seg = "all"

    s = _series(seg)
    vmin, vmax = int(s.index.min()), int(s.index.max())

    def lookup(y):
        nonlocal caveats
        if y < vmin or y > vmax:
            yc = min(max(y, vmin), vmax)
            caveats.append(f"year {y} outside validated range [{vmin},{vmax}] for '{seg}'; "
                           f"clamped to {yc} — treat as a floor/ceiling, not a measurement")
            y = yc
        return float(s.loc[y, "index"]), float(s.loc[y, "log_se"])

    i_from, se_from = lookup(int(from_year))
    i_to, se_to = lookup(int(to_year))
    mult = i_to / i_from
    scaled = fee_nominal * mult

    # 95% CI on the multiplier: SEs of the two log year-FEs add in quadrature (independent).
    se_mult = float(np.sqrt(se_from**2 + se_to**2))
    ci_low = fee_nominal * mult * np.exp(-1.96 * se_mult)
    ci_high = fee_nominal * mult * np.exp(1.96 * se_mult)

    n_from = int(s.loc[int(np.clip(from_year, vmin, vmax)), "n"])
    n_to = int(s.loc[int(np.clip(to_year, vmin, vmax)), "n"])
    if min(n_from, n_to) < 40:
        caveats.append(f"thin support (n_from={n_from}, n_to={n_to}); CI understates true uncertainty")
    if seg == "elite":
        caveats.append("elite index = top-decile deals; do NOT use for mid-market fees")
    if seg == "premium":
        caveats.append("premium index is fee-vs-market-value, not a raw price index")

    return dict(
        scaled_fee=round(scaled, 2), index_from=round(i_from, 1), index_to=round(i_to, 1),
        multiplier=round(mult, 3), ci_low=round(ci_low, 2), ci_high=round(ci_high, 2),
        basis=basis, segment=seg, currency=currency, caveats="; ".join(caveats) or "none",
    )


# ===========================================================================
# §5 self-checks
# ===========================================================================
def _selfcheck() -> bool:
    idx, meta = _load()
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    vmax = meta["valid_max"]
    elite_max = meta.get("segment_valid_max", {}).get("elite", 2022)  # elite gated at composition break
    cpi_year = min(elite_max, max(UK_CPI_2015_100))
    # 1. Shearer £15m (1996 record) -> modern elite: must sit in the modern world-record BAND —
    #    well above the CPI answer (~£30m), and NOT absurdly high. The upper bound is the guard
    #    that catches the 2023+ elite explosion (£425m) that a lower-bound-only check let through.
    r = scale_fee(15.0, 1996, elite_max, market="elite")
    cpi_val = 15.0 * (UK_CPI_2015_100[cpi_year] / UK_CPI_2015_100[1996])
    check("1 Shearer 1996->%d elite in modern-record band (not CPI, not absurd)" % elite_max,
          70 <= r["scaled_fee"] <= 160 and r["scaled_fee"] >= 2.5 * cpi_val,
          f"£{r['scaled_fee']:.0f}m vs CPI £{cpi_val:.0f}m (x{r['scaled_fee']/cpi_val:.1f}); band [70,160]")

    # 2. COVID dip: 2017->2021 elite multiplier < 2017->2019 elite multiplier.
    m2021 = scale_fee(100, 2017, 2021, market="elite")["multiplier"]
    m2019 = scale_fee(100, 2017, 2019, market="elite")["multiplier"]
    check("2 COVID dip (2017->2021 < 2017->2019 elite)", m2021 < m2019,
          f"{m2021:.3f} < {m2019:.3f}")

    # 3. Elite and median multipliers for the same window differ (use a window both segments cover).
    me = scale_fee(100, 2010, elite_max, market="elite")["multiplier"]
    mm = scale_fee(100, 2010, elite_max, market="median")["multiplier"]
    check("3 elite != median (same window)", abs(me - mm) > 1e-3, f"elite {me:.3f} vs median {mm:.3f}")

    # 4. Round-trip within FP error.
    f0 = 40.0
    up = scale_fee(f0, 2012, 2020, market="all")["scaled_fee"]
    back = scale_fee(up, 2020, 2012, market="all")["scaled_fee"]
    check("4 round-trip 2012->2020->2012 recovers original", abs(back - f0) < 1e-6,
          f"{f0} -> {up:.2f} -> {back:.6f}")

    # 5. Out-of-range year fires a caveat (does NOT silently fall back to CPI).
    r5 = scale_fee(15.0, 1996, vmax + 1, market="all")
    check("5 out-of-range year flagged, not silently CPI'd",
          "outside validated range" in r5["caveats"], r5["caveats"][:60])

    # 6. Structural sanity: no persisted index value is absurd (>6x the 2010 base). This is the
    #    guard that would have caught the elite=1261 explosion at build time, not in a scaling call.
    worst = idx.loc[idx["index"].idxmax()]
    check("6 no segment index exceeds 6x base (explosion guard)", worst["index"] <= 600,
          f"max {worst['index']:.0f} at {worst['segment']} {int(worst['season'])}")

    print(f"\n  {'ALL PASS' if ok else 'SOME FAILED'}")
    return ok


# ===========================================================================
# docs
# ===========================================================================
def _write_audit(m, naive, segs):
    df = pd.read_parquet(CANON)
    perm_pos = df[(df.transfer_type == "permanent") & (df.fee_eur > 0)]
    cov = (df.assign(posfee=df.fee_eur > 0).groupby("season")
           .agg(n=("posfee", "size"), posfee_rate=("posfee", "mean")).round(3))
    thin = cov[cov.posfee_rate < 0.12].index.tolist()
    lines = [
        "# INFLATION_AUDIT.md — can the data support a transfer-fee inflation index?",
        "",
        f"**Verdict: YES, for {YEAR_MIN}–{YEAR_MAX}.** Built. Gate below. Generated by `money/inflation.py build`.",
        "",
        "## 1. Currency & real-value hygiene",
        "- Fees stored in a **single currency** (`fee_eur`, EUR) — no £/€/$ mixing, so no FX-date",
        "  ambiguity in the index itself. GBP outputs use a fixed €→£ only at *display* time.",
        f"- Positive fees: **{int((df.fee_eur>0).sum()):,}**; explicit £0 (frees): "
        f"**{int((df.fee_eur==0).sum()):,}**; undisclosed: **{int(df.fee_undisclosed.sum()):,}**.",
        "",
        "## 2. Fee definition drift",
        "- Fees are Transfermarkt reported totals (base + typical add-ons blended); release-clause",
        "  activations are **not separately flagged** — a known tail caveat (Neymar/Griezmann sit in",
        "  the elite segment and can lift the p90+ index). Loan fees excluded (loans dropped, see §4).",
        "",
        "## 3. Coverage bias over time",
        f"- Positive-fee rate rises from ~14% (early 90s) to ~26% (2017–19). 2023–25 (raw-harvest-",
        "  enriched, Lane B) sit at " +
        ", ".join(f"{y} {100*cov.loc[y,'posfee_rate']:.1f}%" for y in (2023, 2024, 2025) if y in cov.index) +
        " — back in the 2020/2021 band, no longer a reporting-lag collapse. 2026 is still mid-window",
        "  (partial season, not a data gap) and stays out of the gate.",
        f"- Thin-coverage seasons (<12% positive-fee rate): {thin}.",
        "- The hedonic year-FE purges *level* selection but not composition fully; pre-2005 indices",
        "  carry wider uncertainty (see CIs) and 0% market-value coverage.",
        "",
        "## 4. Free/loan contamination",
        "- Frees are stored as fee_eur==0 (not null) and **excluded** from the positive-fee model.",
        "- transfer_type breakdown: " + ", ".join(f"{k}={v}" for k, v in
            df.transfer_type.value_counts(dropna=False).items()) + ".",
        "- Only `permanent` rows enter the index; loans / end_of_loan / retirements dropped.",
        "",
        "## 5. The tail (positive permanent fees, €m)",
        "```",
        perm_pos.assign(fee_m=perm_pos.fee_eur/1e6).groupby("season")["fee_m"]
            .quantile([.5, .9, .99]).unstack().round(1).tail(15).to_string(),
        "```",
        "- The corrupt **€500–550m rows are flagged `fee_suspect` and removed** (max legit = €222m,",
        "  Neymar 2017). We index BOTH the **median market** and the **elite (p90+) market** — they",
        "  inflate differently and must not be silently mixed (see FINDINGS).",
        "",
        "## 6. Structural-break candidates (tested in FINDINGS via ruptures + Chow)",
        "- " + ", ".join(f"{y} {lbl}" for y, lbl in CANDIDATE_BREAKS.items()) + ".",
        "",
        "## Gate",
        f"- **Index valid range: {YEAR_MIN}–{YEAR_MAX}.** Extended from 2022 by the Lane B raw-harvest",
        "  fix (2026-07): 2023-25 now clear the coverage bar. Years after the gate (2026+) stay",
        "  excluded — an open transfer window, not a sourcing gap.",
        f"- Market-value-premium index: **{PREMIUM_MIN}+ only** (MV ~0% before 2004).",
        f"- Clean modelling universe: **{len(m):,}** transfers.",
        "- `scale_fee()` clamps + flags any request outside the range; it never falls back to CPI.",
    ]
    (ROOT / "docs" / "archive" / "INFLATION_AUDIT.md").write_text("\n".join(lines))
    print("[build] wrote docs/archive/INFLATION_AUDIT.md")


def _write_findings(segs, naive, r2, controls, regimes, chow, mult_all, mult_elite):
    a = segs["all"].set_index("season")["index"]
    el = segs["elite"].set_index("season")["index"]
    md = segs["median"].set_index("season")["index"]
    pr = segs["premium"].set_index("season")["index"]

    def row(y):
        return (f"| {y} | {a.get(y, float('nan')):.0f} | {el.get(y, float('nan')):.0f} | "
                f"{md.get(y, float('nan')):.0f} | "
                f"{pr.get(y, float('nan')):.0f} |" if y in pr.index else
                f"| {y} | {a.get(y):.0f} | {el.get(y):.0f} | {md.get(y):.0f} | — |")

    years = [1992, 1996, 2000, 2004, 2008, 2010, 2013, 2016, 2017, 2019, 2020, 2021, 2022]
    lines = [
        "# INFLATION_FINDINGS.md — football transfer-fee inflation, measured",
        "",
        "Generated by `money/inflation.py build`. Index = 100 at 2010. Hedonic year-FE, two-way",
        "cluster-robust (player, selling club). **Never deflate football fees by CPI.**",
        "",
        "## Headline",
        f"- Over **1996→2022**, all-market fees inflated **{mult_all['football_x']}×** vs UK CPI "
        f"**{mult_all['cpi_x']}×** — i.e. football fees ran **{mult_all['multiple']}× faster than "
        f"consumer inflation**. Elite (p90+): **{mult_elite['football_x']}×** ({mult_elite['multiple']}× CPI).",
        "- **The premium index is the real surprise.** Fee-vs-market-value (2005+) moved only "
        f"~{pr.get(2022, float('nan')):.0f} (2010=100): *almost all* headline fee inflation IS "
        "market-value inflation — clubs aren't paying a bigger premium over MV, MV itself exploded.",
        "- A single scalar 'football inflation rate' is a lie: it is **non-stationary** (regimes below)",
        "  and **non-uniform** (elite vs median diverge year by year).",
        "",
        "## The index (2010 = 100)",
        "| year | all | elite | median | premium(vs MV) |",
        "|--|--|--|--|--|",
        *[row(y) for y in years],
        "",
        f"- Model R²: all={r2['all']:.3f}, elite={r2['elite']:.3f}, median={r2['median']:.3f}, "
        f"premium={r2['premium']:.3f}. (Low raw R² is expected without MV; the year FEs are still",
        "  tightly identified — see CIs in `data/money/inflation_index.csv`.)",
        f"- Quality controls (all-market): age +{controls['all']['age']:.2f}/yr (concave, age²="
        f"{controls['all']['age2']:.3f}), destination top-5 league +{controls['all']['to_top5']:.2f} log-fee.",
        "",
        "## Regimes (ruptures/Binseg on log-index) & CAGR",
        "| regime | CAGR | near |",
        "|--|--|--|",
        *[f"| {r['start']}–{r['end']} | {r['cagr_pct']}%/yr | {r['label'] or '—'} |" for r in regimes],
        "",
        "## Structural-break tests (Chow, p-value; small = real break in the time trend)",
        "| year | event | p-value | significant |",
        "|--|--|--|--|",
        *[f"| {y} | {CANDIDATE_BREAKS[y]} | {chow.get(y, float('nan')):.3f} | "
          f"{'yes' if chow.get(y, 1) < 0.05 else 'no'} |" for y in sorted(chow)],
        "",
        "## Naive foil (biased — coverage & tail driven, DO NOT use)",
        f"- Yearly median fee rose {naive.set_index('season').p50_idx.get(2022, float('nan')):.0f} "
        f"(2010=100); the *record* fee rose ~15× (Shearer £15m 1996 → Neymar €222m 2017). The naive",
        "  index over-reads inflation because early years under-report small fees (survivorship).",
        "",
        "## Segment divergence (the §2c finding)",
        f"- 2022 elite index {el.get(2022):.0f} vs median {md.get(2022):.0f}: they differ, but by less",
        "  than folk intuition — once you control for player quality, the **mid-market inflated about as",
        "  fast as the elite**. The visible 'only the top end went mad' effect is largely a *tail* (p99/",
        "  record) phenomenon, which the hedonic p90 index deliberately does not chase.",
        "",
        "## Caveats (what this index must NOT be used for)",
        "- **FX:** index built in EUR; GBP display uses a fixed €→£ — cross-currency era comparisons",
        "  inherit that assumption.",
        f"- **Coverage:** pre-2005 CIs are wide (no MV control, thinner reporting); {YEAR_MAX+1}+ excluded (open window).",
        "- **Segment ceilings (composition break):** the all/median/nonfwd indices are valid to "
        f"{YEAR_MAX}; **elite/fwd/premium are gated at 2022.** Post-2022 the Saudi Pro League tier "
        "pays record fees to non-top-5 clubs, which the `to_top5` control can't absorb — the elite "
        "year-FE explodes on ~100 thin observations. `scale_fee()` clamps elite/fwd/premium requests "
        "to 2022 and flags. See `SEGMENT_VALID_MAX` and meta.segment_valid_max.",
        "- **Segment discipline:** never scale a mid-market fee with the elite index (or vice-versa).",
        "- **Release clauses** not separated — the elite tail can be lifted by clause activations.",
        "- **Directional, not transactional:** this prices *the market*, not a specific negotiated deal.",
    ]
    (ROOT / "docs" / "archive" / "INFLATION_FINDINGS.md").write_text("\n".join(lines))
    print("[build] wrote docs/archive/INFLATION_FINDINGS.md")


# ===========================================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build()
        print("\n=== self-checks on freshly built index ===")
        _CACHE.clear()
        raise SystemExit(0 if _selfcheck() else 1)
    else:
        print("=== §5 self-checks (persisted index) ===")
        raise SystemExit(0 if _selfcheck() else 1)
