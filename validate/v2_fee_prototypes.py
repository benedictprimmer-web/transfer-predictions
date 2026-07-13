"""V2 fee prototype comparison — F0 (market-value baseline) vs F1 (minimal
structure): does age/role/league context beat pure market-consensus pricing
on the strict V1 negotiated-fee scope? (task §10.2, §10.4, §11.2, §11.4)

Sporting designs (S0-S7, task §10.1) are NOT attempted here: every one of
them needs `transfer_performance_link_safe`, which is unavailable in this
environment (`docs/reconciliation.md` §4). That is a documented BLOCKER, not
an oversight — see `docs/v2-results.md` §1. The fee ladder does not depend
on that table, so it is the one prototype comparison this environment can
actually run and verify.

GATE — frozen in `EXPERIMENT_MANIFEST` below, written to disk before any
model is fit or any result is inspected (see `main()`): F1 must beat F0 by
>= `MIN_RELATIVE_RMSE_IMPROVEMENT` on pooled dev-evaluation log1p(fee) RMSE,
with a bootstrap CI on the RMSE difference that excludes 0. No result
below was used to choose or adjust this threshold after the fact.

Folds follow `docs/modelling-contract.md`'s `design_A_recommended`:
train <= 2018, tune = 2019, calibration = 2020-2021, expanding-window
(F1 refits once, on train+tune, to predict calibration — same walk-forward
convention as `money/fees.py`). The locked period (season >= 2023) and the
season==2022 buffer are excluded by `validate.locked_guard.dev_only()`
before any frame reaches a model.

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

MIN_RELATIVE_RMSE_IMPROVEMENT = 0.05   # F1 must cut log1p RMSE by >= 5% vs F0
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 0

EXPERIMENT_MANIFEST = {
    "population": "V1_FEE_SCOPE (validate.modelling_contract), strict negotiated-fee candidates",
    "folds": {"train": "season <= 2018", "tune": "season = 2019", "calibration": "season 2020-2021"},
    "locked_period": "season >= 2023, excluded via validate.locked_guard.dev_only()",
    "designs": {
        "F0": "market-value baseline: fee_pred = market_value_eur, no fitting",
        "F1_minimal": "Ridge(log1p(fee) ~ log1p(market_value) + age + age^2 + pos_group + from_league + to_league), expanding-window walk-forward",
    },
    "metric": "RMSE of log1p(fee) on pooled dev-evaluation rows (tune + calibration)",
    "gate": {
        "min_relative_rmse_improvement": MIN_RELATIVE_RMSE_IMPROVEMENT,
        "rule": "F1 ships as a challenger only if (F0_rmse - F1_rmse)/F0_rmse >= threshold "
                "AND a paired bootstrap 90% CI on the RMSE difference excludes 0. "
                "Frozen before any model was fit — see git history of this file.",
        "simplicity_rule": "if the gate is not cleared, F0 remains the provisional design (task 11.4)",
    },
    "bootstrap": {"n": BOOTSTRAP_N, "seed": BOOTSTRAP_SEED},
}


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DATA / "warehouse.duckdb"), read_only=True)


def load_v1_fee_scope(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    q = f"""
    select season, player_age as age, pos_group, from_league, to_league,
           market_value_eur, fee_eur as fee
    from transfers_canonical
    where {V1_FEE_SCOPE}
    """
    return con.execute(q).fetchdf()


def _f1_pipeline() -> Pipeline:
    num = ["log_mv", "age", "age_sq"]
    cat = ["pos_group", "from_league", "to_league"]
    pre = ColumnTransformer([
        ("num", StandardScaler(), num),
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat),
    ])
    return Pipeline([("pre", pre), ("model", Ridge(alpha=1.0, random_state=0))])


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["log_mv"] = np.log1p(d.market_value_eur)
    d["age_sq"] = d.age ** 2
    d["log_fee"] = np.log1p(d.fee)
    return d


def run_walk_forward(dev: pd.DataFrame) -> pd.DataFrame:
    """Returns per-row F0/F1 predictions for tune and calibration splits only
    (train never gets scored — it's not held out)."""
    d = _prep(dev)
    train = d[d.season <= 2018]
    tune = d[d.season == 2019]
    calibration = d[d.season.between(2020, 2021)]
    assert len(train) and len(tune) and len(calibration), "empty fold — check season boundaries"

    rows = []
    # split 1: fit on train, score tune
    m1 = _f1_pipeline().fit(train, train.log_fee)
    for split_name, split in [("tune", tune)]:
        pred = m1.predict(split)
        rows.append(split.assign(f1_pred_log_fee=pred, eval_split=split_name))
    # split 2 (expanding): fit on train+tune, score calibration
    m2 = _f1_pipeline().fit(pd.concat([train, tune]), pd.concat([train, tune]).log_fee)
    pred2 = m2.predict(calibration)
    rows.append(calibration.assign(f1_pred_log_fee=pred2, eval_split="calibration"))

    out = pd.concat(rows, ignore_index=True)
    out["f0_pred_log_fee"] = np.log1p(out.market_value_eur)  # F0: MV itself, no fit
    out["f0_err"] = out.log_fee - out.f0_pred_log_fee
    out["f1_err"] = out.log_fee - out.f1_pred_log_fee
    return out


def bootstrap_rmse_diff(f0_err: np.ndarray, f1_err: np.ndarray, n: int, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    idx = np.arange(len(f0_err))
    diffs = []
    for _ in range(n):
        s = rng.choice(idx, size=len(idx), replace=True)
        rmse0 = np.sqrt(np.mean(f0_err[s] ** 2))
        rmse1 = np.sqrt(np.mean(f1_err[s] ** 2))
        diffs.append(rmse0 - rmse1)
    return float(np.percentile(diffs, 5)), float(np.percentile(diffs, 95))


def subgroup_breakdown(scored: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dim in ["pos_group", "eval_split"]:
        for val, grp in scored.groupby(dim):
            rmse0 = float(np.sqrt(np.mean(grp.f0_err ** 2)))
            rmse1 = float(np.sqrt(np.mean(grp.f1_err ** 2)))
            rows.append({"dimension": dim, "value": val, "n": len(grp),
                         "f0_rmse_log": rmse0, "f1_rmse_log": rmse1,
                         "relative_improvement": (rmse0 - rmse1) / rmse0 if rmse0 else np.nan})
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "experiment_manifest.json"
    manifest_path.write_text(json.dumps(EXPERIMENT_MANIFEST, indent=2, sort_keys=True) + "\n")

    con = connect()
    all_scope = load_v1_fee_scope(con)
    dev = dev_only(all_scope)
    assert_no_locked(dev)  # defense-in-depth: must not raise

    scored = run_walk_forward(dev)
    assert_no_locked(scored)  # scored rows must still all be dev rows

    rmse0 = float(np.sqrt(np.mean(scored.f0_err ** 2)))
    rmse1 = float(np.sqrt(np.mean(scored.f1_err ** 2)))
    rel_improvement = (rmse0 - rmse1) / rmse0
    ci_lo, ci_hi = bootstrap_rmse_diff(scored.f0_err.to_numpy(), scored.f1_err.to_numpy(),
                                        BOOTSTRAP_N, BOOTSTRAP_SEED)
    gate_passed = bool(rel_improvement >= MIN_RELATIVE_RMSE_IMPROVEMENT and ci_lo > 0)

    comparison = pd.DataFrame([
        {"design": "F0_market_value_baseline", "n": len(scored), "rmse_log1p_fee": rmse0,
         "relative_improvement_vs_f0": 0.0, "ci_lo": np.nan, "ci_hi": np.nan, "gate": "baseline"},
        {"design": "F1_minimal", "n": len(scored), "rmse_log1p_fee": rmse1,
         "relative_improvement_vs_f0": rel_improvement, "ci_lo": ci_lo, "ci_hi": ci_hi,
         "gate": "PASS" if gate_passed else "FAIL"},
    ])
    comparison.to_csv(OUT / "prototype_comparison.csv", index=False)
    subgroup_breakdown(scored).to_csv(OUT / "subgroup_results.csv", index=False)

    verdict = {
        "gate_passed": gate_passed,
        "rmse_f0_log1p_fee": rmse0,
        "rmse_f1_log1p_fee": rmse1,
        "relative_improvement": rel_improvement,
        "min_required": MIN_RELATIVE_RMSE_IMPROVEMENT,
        "bootstrap_ci_90": [ci_lo, ci_hi],
        "n_dev_evaluation_rows": int(len(scored)),
        "decision": (
            "F1_minimal ships as the provisional fee-diagnostic challenger over F0."
            if gate_passed else
            "F0 (market-value baseline) remains the provisional design; F1 did not clear "
            "the predeclared gate. Per the simplicity rule (task 11.4), do not adopt the "
            "more complex design on a marginal or non-significant result."
        ),
    }
    (OUT / "fee_prototype_verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")

    print(json.dumps(verdict, indent=2, sort_keys=True))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
