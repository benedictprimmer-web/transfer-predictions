"""The four falsifiable gates for impact.talent (GATES.md). NEVER loosen a threshold to pass.

    python3 -m validate.talent_gate          -> offline _check (synthetic, proves the gate math)
    python3 -m validate.talent_gate run      -> real gates against data/money/talent_scores.csv

Each gate returns {name, passed, number, ci, n, note}. A FAIL is a finding to report, not a bug
to hide — see MODEL_verdict.md for what actually happened on real data.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "data" / "money" / "talent_scores.csv"


def _boot_ci(stat_fn, *arrays, n_boot: int = 1000, seed: int = 0):
    rng = np.random.default_rng(seed)
    a = [np.asarray(x) for x in arrays]
    n = len(a[0])
    point = stat_fn(*a)
    draws = [stat_fn(*[x[idx] for x in a]) for idx in
             (rng.integers(0, n, n) for _ in range(n_boot))]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(point), float(lo), float(hi)


def gate1_beats_age_baseline(test_df: pd.DataFrame, target: str,
                             talent_pred: str, age_pred: str) -> dict:
    from scipy.stats import spearmanr
    y = test_df[target].to_numpy()
    t = test_df[talent_pred].to_numpy()
    a = test_df[age_pred].to_numpy()

    def lift(y_, t_, a_):
        return spearmanr(t_, y_).statistic - spearmanr(a_, y_).statistic
    point, lo, hi = _boot_ci(lift, y, t, a)
    return {"name": "gate1_beats_age_baseline", "passed": lo > 0,
            "number": point, "ci": (lo, hi), "n": len(y),
            "note": "talent vs age-only Spearman lift; PASS iff CI excludes 0"}


def gate2_haaland_antony(price_gap_fn) -> dict:
    haa = price_gap_fn("Haaland", "2021-2022")
    ant = price_gap_fn("Antony", "2021-2022")
    missing = [n for n, v in [("Haaland", haa), ("Antony", ant)] if v is None]
    passed = (haa is not None and ant is not None and haa < 0 and ant > 0)
    return {"name": "gate2_haaland_antony", "passed": passed,
            "number": {"haaland": haa, "antony": ant}, "ci": None, "n": 2 - len(missing),
            "note": ("PASS iff Haaland<0 (underpay) and Antony>0 (overpay); no sign flip. "
                     f"NOT RUNNABLE for: {missing}" if missing else
                     "PASS iff Haaland<0 (underpay) and Antony>0 (overpay); no sign flip")}


def gate3_cohort_monotonicity(test_df: pd.DataFrame, gap_col: str, realized_col: str,
                              n_deciles: int = 10) -> dict:
    d = test_df[[gap_col, realized_col]].dropna().copy()
    d["decile"] = pd.qcut(d[gap_col].rank(method="first"), n_deciles, labels=False)
    med = d.groupby("decile")[realized_col].median()
    top = d[d["decile"] == n_deciles - 1][realized_col].to_numpy()
    bot = d[d["decile"] == 0][realized_col].to_numpy()
    rng = np.random.default_rng(0)
    draws = [np.median(rng.choice(top, len(top))) - np.median(rng.choice(bot, len(bot)))
             for _ in range(1000)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    steps = np.diff(med.to_numpy())
    mono = float((steps > 0).mean())
    return {"name": "gate3_cohort_monotonicity", "passed": bool(lo > 0 and mono >= 0.6),
            "number": {"top_minus_bottom": float(np.median(top) - np.median(bot)),
                       "upward_step_frac": mono}, "ci": (float(lo), float(hi)), "n": len(d),
            "note": "PASS iff top-bottom spread CI excludes 0 AND >=60% deciles step up"}


def gate4_screen_beats_base_rate(screen_hits: int, screen_n: int,
                                 base_hits: int, base_n: int) -> dict:
    p_screen = screen_hits / screen_n if screen_n else float("nan")
    p_base = base_hits / base_n if base_n else float("nan")
    rng = np.random.default_rng(0)
    s = np.r_[np.ones(screen_hits), np.zeros(screen_n - screen_hits)]
    b = np.r_[np.ones(base_hits), np.zeros(base_n - base_hits)]
    draws = [rng.choice(s, screen_n).mean() - rng.choice(b, base_n).mean() for _ in range(2000)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"name": "gate4_screen_beats_base_rate", "passed": bool(lo > 0),
            "number": {"precision": p_screen, "base_rate": p_base}, "ci": (float(lo), float(hi)),
            "n": screen_n, "note": "PASS iff (screen - base) CI excludes 0; report n / power"}


def report(gates: list[dict]) -> str:
    lines = ["", "=== TALENT-MODEL GATES ==="]
    for g in gates:
        flag = "PASS" if g["passed"] else "FAIL"
        lines.append(f"[{flag}] {g['name']}: {g['number']}  ci={g['ci']}  n={g['n']}  ({g['note']})")
    core = {g["name"]: g["passed"] for g in gates}
    if core.get("gate3_cohort_monotonicity") and core.get("gate4_screen_beats_base_rate"):
        verdict = "edge PROVEN"
    else:
        verdict = "edge PRESENT BUT UNPROVEN (a conversion gate failed)"
    lines.append(f"VERDICT: {verdict}")
    out = "\n".join(lines)
    print(out)
    return verdict


# ------------------------------------------------------------------ real wiring

def _age_only_baseline(panel: pd.DataFrame, target: str, min_train_rows: int) -> pd.Series:
    """Same walk-forward scheme as impact.talent.fit_walk_forward, age(+position)-only features
    — the thing gate 1 tests the talent model against."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    d = panel.sort_values("season").reset_index(drop=True)
    X = d[["age", "age_sq", "position_group"]].copy()
    X["position_group"] = X["position_group"].astype("category")
    pred = pd.Series(np.nan, index=d.index, dtype=float)
    for s in sorted(d.season.unique()):
        train = d.season < s
        test = d.season == s
        if train.sum() < min_train_rows:
            continue
        m = HistGradientBoostingRegressor(categorical_features=[False, False, True], random_state=0)
        m.fit(X[train], d.loc[train, target])
        pred[test] = m.predict(X[test])
    return pred


def _load_scored_with_names() -> pd.DataFrame:
    import sys
    sys.path.insert(0, str(REPO))
    from ingest import warehouse
    con = warehouse.connect()
    names = con.execute("select tm_player_id, name from players_master").fetchdf()
    d = pd.read_csv(SCORES)
    return d.merge(names, on="tm_player_id", how="left")


def _price_gap_fn(d: pd.DataFrame):
    def f(name_contains: str, season: str):
        m = d[d.name.str.contains(name_contains, case=False, na=False) & (d.season == season)]
        if m.empty:
            return None
        row = m.iloc[0]
        return float(row.price_pctl - row.talent_pctl)      # >0 overpay, <0 underpay
    return f


def run() -> None:
    d = _load_scored_with_names()
    print(f"scored panel: {len(d):,} rows, seasons {sorted(d.season.unique())}")

    # gate 1: age-only baseline, same walk-forward scheme, MIN_TRAIN_ROWS matching impact.talent
    from impact.talent import MIN_TRAIN_ROWS
    d = d.assign(age_pred=_age_only_baseline(d, "fwd_mv_resid", MIN_TRAIN_ROWS).to_numpy())
    g1_df = d.dropna(subset=["talent_score", "age_pred", "fwd_mv_resid"])
    g1 = gate1_beats_age_baseline(g1_df, "fwd_mv_resid", "talent_score", "age_pred")

    g2 = gate2_haaland_antony(_price_gap_fn(d))

    d["talent_minus_price"] = d.talent_pctl - d.price_pctl
    g3 = gate3_cohort_monotonicity(d, "talent_minus_price", "fwd_growth_raw")

    # gate 4: reformulated gem screen — within position x season (already how price_pctl/
    # talent_pctl are computed), gem = talent top tercile AND price bottom tercile; hit = MV
    # roughly doubles forward (log growth > log(2)), matching the review's original definition
    # for comparability. Realized-FEE outcome (BUILD_PLAN's stated ideal) is NOT wired — no
    # cheap point-in-time fee-at-next-transfer join exists in this panel; flagged, not hidden.
    d["hit"] = d.fwd_growth_raw > np.log(2)
    gem = (d.talent_pctl >= 200 / 3) & (d.price_pctl <= 100 / 3)
    screen_hits, screen_n = int(d.loc[gem, "hit"].sum()), int(gem.sum())
    base_hits, base_n = int(d.hit.sum()), int(len(d))
    g4 = gate4_screen_beats_base_rate(screen_hits, screen_n, base_hits, base_n)
    g4["note"] += " | outcome=MV>=2x fwd (fee-premium outcome not wired, disclosed)"

    verdict = report([g1, g2, g3, g4])
    return {"gates": [g1, g2, g3, g4], "verdict": verdict}


def _check() -> None:
    rng = np.random.default_rng(1)
    n = 600
    y = rng.normal(0, 1, n)
    df = pd.DataFrame({"y": y, "talent": y * 0.4 + rng.normal(0, 1, n),
                       "age": rng.normal(0, 1, n),
                       "gap": y * 0.3 + rng.normal(0, 1, n), "realized": y})
    g1 = gate1_beats_age_baseline(df, "y", "talent", "age")
    g3 = gate3_cohort_monotonicity(df, "gap", "realized")
    g4 = gate4_screen_beats_base_rate(30, 50, 43, 100)
    assert g1["passed"], "planted signal should beat age baseline"
    assert g3["passed"], "planted monotone cohort should pass"
    assert g4["passed"], "0.60 vs 0.43 with these n should pass"
    dfn = pd.DataFrame({"y": rng.normal(0, 1, n), "talent": rng.normal(0, 1, n),
                        "age": rng.normal(0, 1, n)})
    assert not gate1_beats_age_baseline(dfn, "y", "talent", "age")["passed"], "noise must fail gate 1"
    g2_none = gate2_haaland_antony(lambda name, season: None)
    assert not g2_none["passed"], "missing players must not silently pass gate 2"
    print("ok")


if __name__ == "__main__":
    import sys
    (run() if "run" in sys.argv[1:] else _check())
