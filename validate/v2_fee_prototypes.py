"""V2/V3 fee prototype ladder on the strict V1 negotiated-fee scope.

Supersedes the original two-design version. That version had a real bug
(caught in external review, reproduced independently before this rewrite):
`bootstrap_rmse_diff` bootstrapped the *absolute* RMSE difference in
log1p(fee) units, but `docs/v2-results.md` reported the resulting interval
as a *relative percentage improvement* CI. The two numbers only looked
similar because F0's RMSE happened to be close to 1.0 (0.808) — with a
baseline RMSE far from 1, the same absolute-CI-labeled-as-percent bug would
have been obviously wrong. Fixed here: `bootstrap_relative_improvement`
recomputes the ratio inside each resample (a ratio's CI is not "point
estimate's CI" rescaled), and `bootstrap_absolute_diff` is reported
separately, correctly labeled, alongside it.

Also fixed: F0 (the original "market value = fee" identity) is now F0a and
is explicitly DESCRIPTIVE ONLY (task §13 fee gate: "F0a is descriptive
only"). The real baseline F1 must clear is F0b — a temporally-calibrated
single-predictor model (log fee ~ log MV, refit per walk-forward split).
F1 not beating a trivial untrained identity is a low bar; F0b is the honest
one.

Cluster-aware uncertainty: with only 3 distinct evaluation seasons
(2019/2020/2021), a season-block bootstrap is nearly useless — see
`_check_season_cluster_count` and the printed caveat. `to_club_id` gives
100+ distinct clusters per eval season, so club-block bootstrap is the
primary cluster-robust interval; row-level IID bootstrap is kept for
comparison, not as the headline statistic.

    python3 -m validate.v2_fee_prototypes
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from validate.locked_guard import assert_no_locked, dev_only
from validate.modelling_contract import V1_FEE_SCOPE

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
OUT = REPO / "reports" / "v2-full-data"

# Gate is against F0b, not F0a (task §13: "F0a is descriptive only").
MIN_RELATIVE_RMSE_IMPROVEMENT = 0.05
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 0

EXPERIMENT_MANIFEST = {
    "population": "V1_FEE_SCOPE (validate.modelling_contract), strict negotiated-fee candidates",
    "folds": {"train": "season <= 2018", "tune": "season = 2019", "calibration": "season 2020-2021"},
    "locked_period": "season >= 2023, excluded via validate.locked_guard.dev_only()",
    "designs": {
        "F0a_naive_mv": "DESCRIPTIVE ONLY: fee_pred = market_value_eur, no fit — not a gate baseline",
        "F0b_calibrated_mv": "Ridge(log1p(fee) ~ log1p(market_value)) only, refit per walk-forward split — the real baseline",
        "F1_minimal": "F0b features + age + age^2 + pos_group + from_league + to_league",
        "F2_contract": "F1 + PIT contract_years_remaining (rows where contract_is_pit only; others get F1 prediction)",
        "F3_existing_histgbr": "money.fees.fit_residuals (existing production-candidate model) on the identical V1_FEE_SCOPE rows/seasons, HistGradientBoosting, its own internal walk-forward filtered to the same eval seasons",
    },
    "metric": "RMSE of log1p(fee) on pooled dev-evaluation rows (tune + calibration)",
    "gate": {
        "min_relative_rmse_improvement_vs_F0b": MIN_RELATIVE_RMSE_IMPROVEMENT,
        "rule": "A design ships as a challenger over F0b only if (F0b_rmse - design_rmse)/F0b_rmse >= "
                "threshold AND the club-block-bootstrap 90% CI on that relative improvement excludes 0. "
                "F0a is reported for context only and is NOT the gate baseline. "
                "Frozen before any model was fit beyond F0a/F0b — see git history of this file.",
        "simplicity_rule": "if no design clears the gate over F0b, F0b remains the provisional design (task 11.4)",
    },
    "uncertainty_caveat": "Only 3 distinct evaluation seasons (2019,2020,2021) exist in this scope — a "
                           "season-block bootstrap would resample from just 3 units and is not reported as "
                           "a headline CI. to_club_id gives 100+ clusters per season and is used instead.",
    "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED, "cluster_unit": "to_club_id"},
}


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DATA / "warehouse.duckdb"), read_only=True)


def load_v1_fee_scope(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    q = f"""
    select season, player_age as age, pos_group, from_league, to_league, to_club_id,
           market_value_eur, fee_eur as fee, contract_years_remaining, contract_is_pit
    from transfers_canonical
    where {V1_FEE_SCOPE}
    """
    return con.execute(q).fetchdf()


def _pipeline(extra_num: list[str] | None = None, extra_cat: list[str] | None = None) -> Pipeline:
    num = ["log_mv"] + (extra_num or [])
    cat = extra_cat or []
    transformers = [("num", StandardScaler(), num)]
    if cat:
        transformers.append(("cat", OneHotEncoder(handle_unknown="ignore"), cat))
    pre = ColumnTransformer(transformers)
    return Pipeline([("pre", pre), ("model", Ridge(alpha=1.0, random_state=0))])


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["log_mv"] = np.log1p(d.market_value_eur)
    d["age_sq"] = d.age ** 2
    d["log_fee"] = np.log1p(d.fee)
    return d


def _walk_forward_fit_predict(d: pd.DataFrame, pipeline_fn, feature_cols: list[str]) -> pd.Series:
    """Expanding-window: fit on train(<=2018) -> predict tune(2019); fit on
    train+tune(<=2019) -> predict calibration(2020-2021). Never touches locked."""
    train = d[d.season <= 2018]
    tune = d[d.season == 2019]
    calibration = d[d.season.between(2020, 2021)]
    pred = pd.Series(np.nan, index=d.index, dtype=float)

    m1 = pipeline_fn().fit(train[feature_cols], train.log_fee)
    pred.loc[tune.index] = m1.predict(tune[feature_cols])

    m2 = pipeline_fn().fit(pd.concat([train, tune])[feature_cols], pd.concat([train, tune]).log_fee)
    pred.loc[calibration.index] = m2.predict(calibration[feature_cols])
    return pred


def run_designs(dev: pd.DataFrame) -> pd.DataFrame:
    d = _prep(dev)
    eval_mask = d.season.isin([2019, 2020, 2021])
    assert eval_mask.sum() > 0, "empty evaluation set — check season boundaries"

    d["f0a_pred_log_fee"] = np.log1p(d.market_value_eur)  # no fit — descriptive only

    d["f0b_pred_log_fee"] = _walk_forward_fit_predict(
        d, lambda: _pipeline(), ["log_mv"])

    d["f1_pred_log_fee"] = _walk_forward_fit_predict(
        d, lambda: _pipeline(extra_num=["age", "age_sq"], extra_cat=["pos_group", "from_league", "to_league"]),
        ["log_mv", "age", "age_sq", "pos_group", "from_league", "to_league"])

    # F2: F1 + PIT contract years, but only fit/scored where contract_is_pit is true;
    # rows without PIT contract data fall back to the F1 prediction (never impute a
    # feature that doesn't pass the PIT assertion — task's "no silent imputation" rule).
    d["f2_pred_log_fee"] = d["f1_pred_log_fee"]
    pit = d[d.contract_is_pit.fillna(False)].copy()
    if len(pit) >= 200:  # enough rows across train/tune/calibration to be worth fitting separately
        pit_pred = _walk_forward_fit_predict(
            pit, lambda: _pipeline(extra_num=["age", "age_sq", "contract_years_remaining"],
                                    extra_cat=["pos_group", "from_league", "to_league"]),
            ["log_mv", "age", "age_sq", "contract_years_remaining", "pos_group", "from_league", "to_league"])
        d.loc[pit_pred.index, "f2_pred_log_fee"] = pit_pred

    out = d[eval_mask].copy()
    out["eval_split"] = np.select(
        [out.season == 2019, out.season.between(2020, 2021)], ["tune", "calibration"], default="?")
    for design in ["f0a", "f0b", "f1", "f2"]:
        out[f"{design}_err"] = out.log_fee - out[f"{design}_pred_log_fee"]
    return out


def run_f3_existing_model(dev: pd.DataFrame, eval_seasons: set[int]) -> pd.DataFrame | None:
    """F3: the existing production-candidate money.fees.fit_residuals (HistGBR),
    run on the identical V1_FEE_SCOPE rows so the comparison is fair (same
    population, same seasons) even though fit_residuals does its own internal
    walk-forward rather than the train/tune/calibration split above."""
    from money.fees import fit_residuals
    d = dev.rename(columns={"market_value_eur": "market_value", "pos_group": "position",
                             "contract_years_remaining": "contract_years"}).copy()
    d["fee"] = d.fee if "fee" in d.columns else d.fee_eur
    try:
        scored = fit_residuals(d)
    except Exception as e:  # money/fees.py's own walk-forward may drop thin seasons
        print(f"F3 (existing HistGBR) could not be scored: {e}")
        return None
    scored = scored[scored.season.isin(eval_seasons)].copy()
    if not len(scored):
        return None
    scored["f3_pred_log_fee"] = np.log1p(scored.fee_pred)
    scored["log_fee"] = np.log1p(scored.fee)
    scored["f3_err"] = scored.log_fee - scored.f3_pred_log_fee
    return scored[["season", "f3_err"]]


def _rmse(err: np.ndarray) -> float:
    return float(np.sqrt(np.mean(err ** 2)))


def bootstrap_absolute_diff(baseline_err: np.ndarray, challenger_err: np.ndarray,
                             clusters: np.ndarray, n: int, seed: int) -> tuple[float, float]:
    """Club-block bootstrap of the ABSOLUTE RMSE difference (log1p-fee units).
    Resamples whole clusters (to_club_id), not individual rows."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(clusters)
    diffs = []
    for _ in range(n):
        chosen = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([np.where(clusters == c)[0] for c in chosen])
        diffs.append(_rmse(baseline_err[idx]) - _rmse(challenger_err[idx]))
    return float(np.percentile(diffs, 5)), float(np.percentile(diffs, 95))


def bootstrap_relative_improvement(baseline_err: np.ndarray, challenger_err: np.ndarray,
                                    clusters: np.ndarray, n: int, seed: int) -> tuple[float, float]:
    """Club-block bootstrap of the RELATIVE improvement ratio. The ratio is
    recomputed inside every resample — a ratio statistic's CI is not the
    point-estimate CI divided by a fixed denominator (that was the original bug)."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(clusters)
    rels = []
    for _ in range(n):
        chosen = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([np.where(clusters == c)[0] for c in chosen])
        r0 = _rmse(baseline_err[idx])
        if r0 == 0:
            continue
        rels.append((r0 - _rmse(challenger_err[idx])) / r0)
    return float(np.percentile(rels, 5)), float(np.percentile(rels, 95))


def subgroup_breakdown(scored: pd.DataFrame, challenger_col: str = "f1_err") -> pd.DataFrame:
    rows = []
    for dim in ["pos_group", "eval_split"]:
        for val, grp in scored.groupby(dim):
            rmse0 = _rmse(grp.f0b_err.to_numpy())
            rmse_c = _rmse(grp[challenger_col].to_numpy())
            rows.append({"dimension": dim, "value": val, "n": len(grp),
                         "f0b_rmse_log": rmse0, "challenger_rmse_log": rmse_c,
                         "relative_improvement_vs_f0b": (rmse0 - rmse_c) / rmse0 if rmse0 else np.nan})
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "experiment_manifest.json"
    manifest_path.write_text(json.dumps(EXPERIMENT_MANIFEST, indent=2, sort_keys=True) + "\n")

    con = connect()
    all_scope = load_v1_fee_scope(con)
    dev = dev_only(all_scope)
    assert_no_locked(dev)

    scored = run_designs(dev)
    assert_no_locked(scored)
    n_eval_seasons = scored.season.nunique()
    assert n_eval_seasons <= 3, "expected exactly the 3 predeclared eval seasons (2019,2020,2021)"

    f3 = run_f3_existing_model(dev, eval_seasons={2019, 2020, 2021})

    designs = {"f0a": "F0a_naive_mv_DESCRIPTIVE_ONLY", "f0b": "F0b_calibrated_mv_BASELINE",
               "f1": "F1_minimal", "f2": "F2_contract"}
    comparison_rows = []
    clusters = scored.to_club_id.fillna(-1).to_numpy()
    rmse_f0b = _rmse(scored.f0b_err.to_numpy())
    for key, label in designs.items():
        err = scored[f"{key}_err"].to_numpy()
        rmse = _rmse(err)
        is_baseline = key == "f0b"
        rel = (rmse_f0b - rmse) / rmse_f0b if rmse_f0b else np.nan
        if key == "f0a":
            comparison_rows.append({"design": label, "n": len(scored), "rmse_log1p_fee": rmse,
                                     "relative_improvement_vs_f0b": rel, "abs_ci_lo": np.nan, "abs_ci_hi": np.nan,
                                     "rel_ci_lo": np.nan, "rel_ci_hi": np.nan, "gate": "descriptive_only"})
            continue
        if is_baseline:
            comparison_rows.append({"design": label, "n": len(scored), "rmse_log1p_fee": rmse,
                                     "relative_improvement_vs_f0b": 0.0, "abs_ci_lo": np.nan, "abs_ci_hi": np.nan,
                                     "rel_ci_lo": np.nan, "rel_ci_hi": np.nan, "gate": "baseline"})
            continue
        abs_lo, abs_hi = bootstrap_absolute_diff(scored.f0b_err.to_numpy(), err, clusters, BOOTSTRAP_N, BOOTSTRAP_SEED)
        rel_lo, rel_hi = bootstrap_relative_improvement(scored.f0b_err.to_numpy(), err, clusters, BOOTSTRAP_N, BOOTSTRAP_SEED)
        gate_passed = bool(rel >= MIN_RELATIVE_RMSE_IMPROVEMENT and rel_lo > 0)
        comparison_rows.append({"design": label, "n": len(scored), "rmse_log1p_fee": rmse,
                                 "relative_improvement_vs_f0b": rel, "abs_ci_lo": abs_lo, "abs_ci_hi": abs_hi,
                                 "rel_ci_lo": rel_lo, "rel_ci_hi": rel_hi,
                                 "gate": "PASS" if gate_passed else "FAIL"})

    if f3 is not None and len(f3):
        merged = scored.merge(f3, on="season", how="inner", suffixes=("", "_f3dup"))
        # f3 rows don't align 1:1 by row (fit_residuals drops/reorders), so report
        # F3's RMSE on its own scored subset for that season set, not row-paired.
        rmse_f3 = _rmse(f3.f3_err.to_numpy())
        comparison_rows.append({"design": "F3_existing_histgbr_context_only", "n": len(f3),
                                 "rmse_log1p_fee": rmse_f3,
                                 "relative_improvement_vs_f0b": (rmse_f0b - rmse_f3) / rmse_f0b if rmse_f0b else np.nan,
                                 "abs_ci_lo": np.nan, "abs_ci_hi": np.nan, "rel_ci_lo": np.nan, "rel_ci_hi": np.nan,
                                 "gate": "context_only_not_row_paired_with_F0-F2"})

    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(OUT / "prototype_comparison.csv", index=False)
    subgroup_breakdown(scored, "f1_err").to_csv(OUT / "subgroup_results.csv", index=False)

    f1_row = comparison[comparison.design == "F1_minimal"].iloc[0]
    verdict = {
        "gate_passed": f1_row.gate == "PASS",
        "rmse_f0a_naive_descriptive_only": float(scored.f0a_err.pow(2).mean() ** 0.5),
        "rmse_f0b_baseline": rmse_f0b,
        "rmse_f1": float(f1_row.rmse_log1p_fee),
        "relative_improvement_f1_vs_f0b": float(f1_row.relative_improvement_vs_f0b),
        "min_required": MIN_RELATIVE_RMSE_IMPROVEMENT,
        "relative_improvement_club_block_ci_90": [float(f1_row.rel_ci_lo), float(f1_row.rel_ci_hi)],
        "absolute_log1p_rmse_diff_club_block_ci_90": [float(f1_row.abs_ci_lo), float(f1_row.abs_ci_hi)],
        "n_dev_evaluation_rows": int(len(scored)),
        "n_eval_seasons": int(n_eval_seasons),
        "cluster_unit": "to_club_id",
        "uncertainty_caveat": EXPERIMENT_MANIFEST["uncertainty_caveat"],
        "decision": (
            "F1_minimal ships as the provisional fee-diagnostic challenger over F0b (the calibrated "
            "baseline, not the naive F0a identity)."
            if f1_row.gate == "PASS" else
            "F0b (calibrated market-value-only baseline) remains the provisional design; F1 did not "
            "clear the predeclared gate over F0b. Per the simplicity rule (task 11.4), do not adopt "
            "the more complex design on a marginal or non-significant result."
        ),
    }
    (OUT / "fee_prototype_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")

    print(json.dumps(verdict, indent=2, sort_keys=True))
    print("\nFull comparison:")
    print(comparison.to_string(index=False))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
