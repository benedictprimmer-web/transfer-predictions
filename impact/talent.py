"""Price-blind talent model — score a player's on-pitch quality independent of price.

DROP-IN per `transfer-model-improvement/BUILD_PLAN.md` + `GATES.md`. Run:
    python3 -m impact.talent          -> offline _check (synthetic)
    python3 -m impact.talent build    -> real fit, prints coverage + peeks
    python3 -m impact.talent ship     -> real fit, writes data/money/talent_scores.csv

The commercial thesis: edge = players whose on-pitch quality ranks far above what their price
implies. Market value / wage / fee are PARALLEL CONTEXT, never inputs here — price enters only
as the TARGET (forward MV growth) and the benchmark gap computed downstream. See
`MODEL_00_scope.md` / `MODEL_01_research.md` for the design record and coverage numbers this
module was built against.

Target : age(+league)-residualized forward 2-year Δlog(market value) [RESEARCH_PLAN R1]
Model  : one pooled HistGradientBoostingRegressor, expanding-window walk-forward (never random)
Guard  : _assert_price_blind() fires at fit time — do not remove it.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "money" / "talent_scores.csv"

_PRICE_TOKENS = ("market_value", "mv_", "_mv", "value_eur", "wage", "salary", "fee", "overpay", "price")

FEATURES = [
    "usage_share", "shot_share", "efficiency", "age", "age_sq", "n90s",
    "def_actions_p90", "turnover_p90", "xa_p90", "prog_actions_p90",
    "avail_trailing3y", "position_group",
]
CATS = [False, False, False, False, False, False, False, False, False, False, False, True]

MIN_TRAIN_ROWS = 200
TARGET = "fwd_mv_resid"
KEY = ["tm_player_id", "season"]


def _assert_price_blind(cols) -> None:
    """Fail loudly if any feature smells of price. This assertion is the whole point — keep it."""
    bad = [c for c in cols for t in _PRICE_TOKENS if t in c.lower()]
    if bad:
        raise AssertionError(f"price leaked into talent features: {sorted(set(bad))}")


_assert_price_blind(FEATURES)   # fires at import time too — the guard is structural, not optional


# ------------------------------------------------------------------ panel construction

def _usage_panel(con) -> pd.DataFrame:
    """One row per (tm_player_id, season): action-weighted usage/efficiency, real player_id join
    (crosswalk_players.us_player_id -> tm_player_id), not the fuzzy name join impact.aging uses."""
    from ingest.understat import read_shots
    from impact.usage import usage_efficiency

    shots = read_shots()
    u = usage_efficiency(shots)
    id_map = (shots.groupby("player")["player_id"]
              .agg(lambda s: s.value_counts().idxmax()).rename("us_player_id"))
    u = u.merge(id_map, left_on="player", right_index=True, how="left")
    cw = con.execute("select us_player_id, tm_player_id from crosswalk_players").fetchdf()
    u = u.merge(cw, on="us_player_id", how="left").dropna(subset=["tm_player_id"]).copy()
    u["tm_player_id"] = u.tm_player_id.astype(int)

    def _collapse(g):
        w = g.actions.to_numpy()
        return pd.Series(dict(
            actions=g.actions.sum(), value=g.value.sum(),
            usage_share=np.average(g.usage_share, weights=w),
            shot_share=np.average(g.shot_share, weights=w),
            league=g.loc[g.actions.idxmax(), "league"]))

    ps = u.groupby(KEY, as_index=False).apply(_collapse, include_groups=False)
    ps["efficiency"] = ps.value / ps.actions
    return ps


def _age_position(con, ps: pd.DataFrame) -> pd.DataFrame:
    from impact.aging import POS_GROUP
    pm = con.execute("select tm_player_id, date_of_birth, position from players_master").fetchdf()
    ps = ps.merge(pm, on="tm_player_id", how="left")
    season_end_year = ps.season.str[:4].astype(int) + 1
    snap = pd.to_datetime(dict(year=season_end_year, month=6, day=30)).astype("datetime64[ns]")
    dob = pd.to_datetime(ps.date_of_birth, errors="coerce")
    ps["age"] = (snap - dob).dt.days / 365.25
    ps["age_sq"] = ps.age ** 2
    ps["position_group"] = ps.position.map(POS_GROUP).fillna("UNK")
    ps["season_end_year"] = season_end_year
    ps["snapshot_date"] = snap
    return ps


def _minutes(ps: pd.DataFrame) -> pd.DataFrame:
    from ingest.transfermarkt import _read, download, BIG5
    download(("appearances",))
    ap = _read("appearances", usecols=["player_id", "competition_id", "minutes_played", "date"])
    ap = ap[ap.competition_id.isin(BIG5)].copy()
    dt = pd.to_datetime(ap.date, errors="coerce")
    ap = ap[dt.notna()].copy()
    dt = dt[dt.notna()]
    sy = np.where(dt.dt.month >= 7, dt.dt.year, dt.dt.year - 1)
    ap["season"] = [f"{y}-{y + 1}" for y in sy]
    mins = ap.groupby(["player_id", "season"], as_index=False).minutes_played.sum()
    mins = mins.rename(columns={"player_id": "tm_player_id"})
    mins["n90s"] = mins.minutes_played / 90.0
    return ps.merge(mins[["tm_player_id", "season", "n90s"]], on=["tm_player_id", "season"], how="left")


def _defense_niche(con, ps: pd.DataFrame) -> pd.DataFrame:
    """fbref_defense/niche are already tm_player_id+season_end_year keyed — but some
    player-seasons have >1 squad row (mid-season club change), so pre-aggregate (n90-weighted)
    before the merge or the join fans out silently."""
    n_before = len(ps)
    dfn = con.execute("""
        select tm_player_id, season_end_year,
            sum((tackles_p90+interceptions_p90+blocks_p90+recoveries_p90+aerials_won_p90) * n90)
                / nullif(sum(n90),0) as def_actions_p90
        from fbref_defense group by 1,2
    """).fetchdf()
    ps = ps.merge(dfn, on=["tm_player_id", "season_end_year"], how="left")
    nch = con.execute("""
        select tm_player_id, season_end_year,
            sum(((miscontrols+dispossessed)/nullif(n90,0)) * n90) / nullif(sum(n90),0) as turnover_p90,
            sum((xa/nullif(n90,0)) * n90) / nullif(sum(n90),0) as xa_p90,
            sum(((prog_passes+prog_carries)/nullif(n90,0)) * n90) / nullif(sum(n90),0) as prog_actions_p90
        from fbref_niche group by 1,2
    """).fetchdf()
    ps = ps.merge(nch, on=["tm_player_id", "season_end_year"], how="left")
    assert len(ps) == n_before, f"fan-out in fbref merge: {n_before} -> {len(ps)}"
    return ps


def _durability(ps: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time durability: trailing-3y days missed as-of snapshot_date, from the RAW spell
    file — NOT `injuries.load()`'s career column (that module's own docstring: 'not point-in-time
    safe'). Vectorized via per-player cumsum + searchsorted (a per-row `spells_before` re-read of
    the CSV timed out past 2 minutes on 23k rows)."""
    src = REPO / "data" / "injuries" / "player_injuries.csv"
    spells = pd.read_csv(src, usecols=["player_id", "end_date", "days_missed"])
    spells["tm_player_id"] = pd.to_numeric(spells.player_id, errors="coerce")
    spells["end_date"] = pd.to_datetime(spells.end_date, errors="coerce")
    spells = spells.dropna(subset=["tm_player_id", "end_date"])
    spells["tm_player_id"] = spells.tm_player_id.astype(int)
    spells = spells.sort_values(["tm_player_id", "end_date"])
    groups = {tid: (g.end_date.to_numpy(), g.days_missed.cumsum().to_numpy())
              for tid, g in spells.groupby("tm_player_id")}

    snap = ps.snapshot_date.to_numpy()
    tid_arr = ps.tm_player_id.to_numpy()
    window_start = (ps.snapshot_date - pd.DateOffset(years=3)).to_numpy()
    avail = np.empty(len(ps))
    for i in range(len(ps)):
        g = groups.get(tid_arr[i])
        if g is None:
            avail[i] = 1.0                      # no record -> assumed fit (flagged upstream)
            continue
        dates, cum = g
        hi = np.searchsorted(dates, snap[i], side="right")
        lo = np.searchsorted(dates, window_start[i], side="right")
        days = cum[hi - 1] - (cum[lo - 1] if lo > 0 else 0.0) if hi > 0 else 0.0
        avail[i] = max(0.40, 1.0 - days / (365.0 * 3))
    ps["avail_trailing3y"] = avail
    return ps


def _target(con, ps: pd.DataFrame) -> pd.DataFrame:
    """Age(+league)-residualized forward 2y Δlog(MV). Anchor MV within 365d of snapshot_date
    (season end); forward MV nearest snapshot+2y within 182d, required to postdate snapshot
    (strict future-dating, defensively re-checked even though the tolerance already guarantees it)."""
    from sklearn.linear_model import LinearRegression

    v = con.execute(
        "select player_id as tm_player_id, date, market_value_in_eur as mv from valuations").fetchdf()
    v["date"] = pd.to_datetime(v.date, errors="coerce").astype("datetime64[ns]")
    v = v.dropna(subset=["date", "mv"])
    v = v[v.mv > 0].sort_values("date")

    ps2 = ps.sort_values("snapshot_date")
    anchor = pd.merge_asof(
        ps2, v.rename(columns={"date": "anchor_date", "mv": "mv_anchor"}),
        left_on="snapshot_date", right_on="anchor_date", by="tm_player_id",
        direction="nearest", tolerance=pd.Timedelta(days=365))
    fwd_target_date = anchor.snapshot_date + pd.DateOffset(years=2)
    tmp = anchor.assign(fwd_target_date=fwd_target_date).sort_values("fwd_target_date")
    fwd = pd.merge_asof(
        tmp, v.rename(columns={"date": "fwd_date", "mv": "mv_fwd"}),
        left_on="fwd_target_date", right_on="fwd_date", by="tm_player_id",
        direction="nearest", tolerance=pd.Timedelta(days=182))

    d = fwd.dropna(subset=["mv_anchor", "mv_fwd"]).copy()
    d = d[d.fwd_date > d.snapshot_date]                       # strict future-dating
    d["fwd_growth_raw"] = np.log(d.mv_fwd) - np.log(d.mv_anchor)
    d = d.dropna(subset=["fwd_growth_raw", "age", "league"])

    X = pd.get_dummies(d[["age", "age_sq", "league"]], columns=["league"], drop_first=True)
    lr = LinearRegression().fit(X, d.fwd_growth_raw)
    d = d.copy()
    d["price_pctl"] = d.groupby(["season", "position_group"]).mv_anchor.rank(pct=True) * 100
    d[TARGET] = d.fwd_growth_raw - lr.predict(X)
    return d


def build_panel(con) -> pd.DataFrame:
    """One row per player-season: price-blind FEATURES + future-dated TARGET + context columns
    (tm_player_id, season, position_group, price_pctl for the gem screen / gates downstream)."""
    ps = _usage_panel(con)
    ps = _age_position(con, ps)
    ps = _minutes(ps)
    ps = _defense_niche(con, ps)
    ps = _durability(ps)
    return _target(con, ps)


# ------------------------------------------------------------------ fit

def fit_walk_forward(panel: pd.DataFrame) -> pd.DataFrame:
    """Expanding-window walk-forward. For target season s (ascending), train on rows whose
    season < s; predict s. Earliest thin seasons are left UNSCORED and dropped (MIN_TRAIN_ROWS
    floor), never backfilled — the only validation scheme (random K-fold is the leak this
    project already fixed in money/fees.py; do not reintroduce it here)."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    d = panel.dropna(subset=[TARGET]).sort_values("season").reset_index(drop=True)
    X_all = d[FEATURES].copy()
    for c, is_cat in zip(FEATURES, CATS):
        X_all[c] = X_all[c].astype("category") if is_cat else pd.to_numeric(X_all[c])
    _assert_price_blind(X_all.columns)

    point = pd.Series(np.nan, index=d.index, dtype=float)
    lo = pd.Series(np.nan, index=d.index, dtype=float)
    hi = pd.Series(np.nan, index=d.index, dtype=float)

    for s in sorted(d.season.unique()):
        train = d.season < s
        test = d.season == s
        if train.sum() < MIN_TRAIN_ROWS:
            continue                                          # unscored, dropped — disclosed
        y = d.loc[train, TARGET]
        m = HistGradientBoostingRegressor(categorical_features=CATS, random_state=0)
        m.fit(X_all[train], y)
        point[test] = m.predict(X_all[test])
        for q, bucket in ((0.1, lo), (0.9, hi)):
            mq = HistGradientBoostingRegressor(
                categorical_features=CATS, loss="quantile", quantile=q, random_state=0)
            mq.fit(X_all[train], y)
            bucket[test] = mq.predict(X_all[test])

    # independent quantile fits can cross (a known GBT-quantile artifact); reconcile so the band
    # is always internally consistent (lo <= point <= hi) without changing what any model learned.
    lo_fixed = np.minimum(lo, point)
    hi_fixed = np.maximum(hi, point)
    out = d.assign(talent_score=point, talent_lo=lo_fixed, talent_hi=hi_fixed).dropna(subset=["talent_score"])
    out["talent_pctl"] = out.groupby(["season", "position_group"]).talent_score.rank(pct=True) * 100
    out["signal_asof"] = out.season
    return out


def ship(con, out_path=OUT) -> pd.DataFrame:
    """Fit on real data and persist scores. data/ is gitignored — this is a build artifact."""
    scored = fit_walk_forward(build_panel(con))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(out_path, index=False)
    print(f"wrote {len(scored):,} talent scores -> {out_path}")
    return scored


def build() -> pd.DataFrame:
    from ingest import warehouse
    con = warehouse.connect()
    panel = build_panel(con)
    print(f"trainable panel: {len(panel):,} player-seasons")
    for f in FEATURES:
        print(f"  {f:20s} coverage {panel[f].notna().mean():.1%}")
    scored = fit_walk_forward(panel)
    print(f"\nscored (after MIN_TRAIN_ROWS floor): {len(scored):,}")
    print(scored.groupby("season").size())
    return scored


# ------------------------------------------------------------------ _check

def _check() -> None:
    """Offline synthetic self-check. Proves the code RUNS and the guardrails BITE — it does NOT
    prove the model is correct (that is validate/talent_gate.py's job). Never gate on this alone."""
    rng = np.random.default_rng(0)
    n = 800
    panel = pd.DataFrame({
        "tm_player_id": rng.integers(0, 200, n),
        "season": rng.integers(2015, 2023, n).astype(str),
        "position_group": rng.choice(["FW", "MF", "DF"], n),
        "feat_a": rng.normal(0, 1, n),
        "feat_b": rng.normal(0, 1, n),
        TARGET: rng.normal(0, 1, n),
    })
    global FEATURES, CATS
    saved_f, saved_c = FEATURES, CATS
    FEATURES, CATS = ["feat_a", "feat_b"], [False, False]
    try:
        scored = fit_walk_forward(panel)
        assert "talent_score" in scored and scored["talent_score"].notna().all()
        assert (scored.talent_lo <= scored.talent_score + 1e-9).all()
        assert (scored.talent_score <= scored.talent_hi + 1e-9).all()
        assert scored.talent_pctl.between(0, 100).all()
        leaked = False
        try:
            _assert_price_blind(["market_value_eur"])
        except AssertionError:
            leaked = True
        assert leaked, "price-blindness guard failed to fire"
    finally:
        FEATURES, CATS = saved_f, saved_c
    print("ok")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if "ship" in args:
        from ingest import warehouse
        ship(warehouse.connect())
    elif "build" in args:
        build()
    else:
        _check()
