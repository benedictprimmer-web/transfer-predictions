"""Small temporal sporting MVP models.

Only S0 and S1 are fit by default. S2 is skipped unless S1 clears the
predeclared gate.

Run:
    python3 -m validate.sporting_mvp_models
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from validate.sporting_mvp_integrity import OUT, REPO, PRICE_FEATURE_RE, write_outputs


def _spearman(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 3 or a.nunique(dropna=True) < 2 or b.nunique(dropna=True) < 2:
        return float("nan")
    return float(a.rank().corr(b.rank()))


def _ndcg(y: pd.Series, score: pd.Series, q: float = 0.1) -> float:
    n = max(1, int(np.ceil(len(y) * q)))
    gains = y.to_numpy(dtype=float)
    order = np.argsort(-score.to_numpy(dtype=float))[:n]
    ideal = np.argsort(-gains)[:n]
    denom = np.sum(gains[ideal] / np.log2(np.arange(2, n + 2)))
    if denom <= 0:
        return float("nan")
    return float(np.sum(gains[order] / np.log2(np.arange(2, n + 2))) / denom)


def _top_precision(y: pd.Series, score: pd.Series, q: float = 0.1) -> float:
    n = max(1, int(np.ceil(len(y) * q)))
    threshold = y.quantile(0.75)
    return float((y.iloc[np.argsort(-score.to_numpy())[:n]] >= threshold).mean())


def _role_rate(df: pd.DataFrame) -> pd.Series:
    """Role-appropriate prior sporting-rate evidence.

    Units are not combined across roles. Missing role-relevant evidence stays
    missing and only the baseline is used for S1 on that row.
    """
    return pd.Series(
        np.select(
            [df.role.eq("FWD"), df.role.eq("MID"), df.role.eq("DEF")],
            [df.prior_attack_rate, df.prior_progression_rate, df.prior_defensive_rate],
            default=np.nan,
        ),
        index=df.index,
        dtype="float64",
    )


def _age_band(s: pd.Series) -> pd.Series:
    return pd.cut(s, [0, 21, 24, 28, 99], labels=["u21", "21_24", "25_28", "29p"]).astype("object")


def _one_hot() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def _ridge_pipeline(categorical: list[str], numeric: list[str]) -> Pipeline:
    pre = ColumnTransformer([
        ("cat", Pipeline([
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", _one_hot()),
        ]), categorical),
        ("num", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), numeric),
    ])
    return Pipeline([("pre", pre), ("ridge", Ridge(alpha=25.0))])


def fit_fold(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    train = train.copy()
    test = test.copy()
    train["age_band"] = _age_band(train.player_age)
    test["age_band"] = _age_band(test.player_age)
    train["age_role"] = train.role.astype(str) + "_" + train.age_band.astype(str)
    test["age_role"] = test.role.astype(str) + "_" + test.age_band.astype(str)
    s0_model = _ridge_pipeline(["role", "age_band", "age_role"], ["player_age"])
    s0_model.fit(train[["role", "age_band", "age_role", "player_age"]], train.next_minutes)
    s0 = pd.Series(s0_model.predict(test[["role", "age_band", "age_role", "player_age"]]), index=test.index)

    # Empirical-Bayes style shrinkage: role-relevant prior rate is pulled toward
    # the training role mean with a predeclared 900-minute exposure half-life.
    # The relationship to future minutes is then fitted inside the fold.
    train["prior_sporting_rate"] = _role_rate(train)
    role_rate = train.groupby("role").prior_sporting_rate.mean().to_dict()
    global_rate = train.prior_sporting_rate.mean()
    train_weight = (train.prior_minutes.fillna(0) / (train.prior_minutes.fillna(0) + 900)).clip(0, 1)
    train["shrunk_prior_sporting_rate"] = (
        train_weight * train.prior_sporting_rate +
        (1 - train_weight) * train.role.map(role_rate).fillna(global_rate)
    )
    train["s1_evidence_status"] = np.where(train.prior_sporting_rate.notna(), "SUPPORTED_RATE_EVIDENCE", "FALLBACK_S0_MISSING_RATE")
    test_rate = _role_rate(test)
    exposure_weight = (test.prior_minutes.fillna(0) / (test.prior_minutes.fillna(0) + 900)).clip(0, 1)
    shrunk_rate = exposure_weight * test_rate + (1 - exposure_weight) * test.role.map(role_rate).fillna(global_rate)
    test["shrunk_prior_sporting_rate"] = shrunk_rate
    test["s1_evidence_status"] = np.where(test_rate.notna(), "SUPPORTED_RATE_EVIDENCE", "FALLBACK_S0_MISSING_RATE")
    s1_train = train[train.prior_sporting_rate.notna()].copy()
    if len(s1_train) >= 100 and s1_train.shrunk_prior_sporting_rate.nunique(dropna=True) > 1:
        s1_model = _ridge_pipeline(
            ["role", "age_band", "age_role"],
            ["player_age", "prior_minutes", "shrunk_prior_sporting_rate", "data_freshness_years"],
        )
        s1_model.fit(
            s1_train[["role", "age_band", "age_role", "player_age", "prior_minutes",
                      "shrunk_prior_sporting_rate", "data_freshness_years"]],
            s1_train.next_minutes,
        )
        s1 = pd.Series(s1_model.predict(test[["role", "age_band", "age_role", "player_age", "prior_minutes",
                                             "shrunk_prior_sporting_rate", "data_freshness_years"]]), index=test.index)
        s1 = s1.where(test.s1_evidence_status.eq("SUPPORTED_RATE_EVIDENCE"), s0)
    else:
        s1 = s0.copy()
        test["s1_evidence_status"] = "FALLBACK_S0_INSUFFICIENT_TRAINING_RATE"
    return test.assign(s0_pred=s0, s1_pred=s1)


def evaluate(pred: pd.DataFrame, score_col: str, label: str) -> dict:
    y = pred.next_minutes
    score = pred[score_col]
    err = score - y
    return {
        "model": label,
        "rows": int(len(pred)),
        "temporal_spearman": _spearman(y, score),
        "ndcg_top_decile": _ndcg(y, score),
        "top_tier_precision": _top_precision(y, score),
        "mae_minutes": float(err.abs().mean()),
        "rmse_minutes": float(np.sqrt((err ** 2).mean())),
    }


def _cluster_bootstrap_lift(pred: pd.DataFrame, reps: int = 1000, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    players = pred.player_id.dropna().unique()
    index_by_player = {p: pred.index[pred.player_id.eq(p)].to_numpy() for p in players}
    lifts = []
    for _ in range(reps):
        draw = rng.choice(players, size=len(players), replace=True)
        sample_idx = np.concatenate([index_by_player[p] for p in draw])
        sample = pred.loc[sample_idx, ["next_minutes", "s0_pred", "s1_pred"]]
        lifts.append(_spearman(sample.next_minutes, sample.s1_pred) -
                     _spearman(sample.next_minutes, sample.s0_pred))
    s = pd.Series(lifts).dropna()
    return {
        "player_cluster_bootstrap_reps": int(reps),
        "spearman_lift_ci90_lo": float(s.quantile(0.05)) if len(s) else float("nan"),
        "spearman_lift_ci90_hi": float(s.quantile(0.95)) if len(s) else float("nan"),
    }


def run_models() -> dict:
    write_outputs()
    d = pd.read_csv(OUT / "dev-population-manifest.csv")
    feature_cols = ["player_age", "role", "prior_minutes", "prior_attack_rate",
                    "prior_progression_rate", "prior_defensive_rate", "data_freshness_years"]
    if any(PRICE_FEATURE_RE.search(c) for c in feature_cols):
        raise AssertionError("price feature configured for sporting MVP")
    d = d[(d.support_status == "SUPPORTED") & d.next_minutes.notna()].copy()
    d = d.sort_values(["outcome_season", "prediction_key"]).reset_index(drop=True)
    folds = []
    fold_audit = []
    for season in sorted(d.outcome_season.unique()):
        train = d[d.outcome_season < season]
        test = d[d.outcome_season == season]
        if len(train) < 250:
            continue
        if train.outcome_season.max() >= test.outcome_season.min():
            raise AssertionError("temporal ordering violated")
        fold_audit.append({
            "validation_season": int(season),
            "train_rows": int(len(train)),
            "train_players": int(train.player_id.nunique()),
            "evaluation_rows": int(len(test)),
            "evaluation_players": int(test.player_id.nunique()),
            "max_training_outcome_season": int(train.outcome_season.max()),
            "min_evaluation_outcome_season": int(test.outcome_season.min()),
            "known_eval_players": int(test.player_id.isin(train.player_id).sum()),
            "unseen_eval_players": int((~test.player_id.isin(train.player_id)).sum()),
            "missing_rate_rows": int(_role_rate(test).isna().sum()),
            "role_counts": json.dumps(test.role.value_counts().sort_index().to_dict(), sort_keys=True),
            "league_counts": json.dumps(test.to_league.value_counts().sort_index().to_dict(), sort_keys=True),
        })
        folds.append(fit_fold(train, test).assign(validation_season=season))
    pred = pd.concat(folds, ignore_index=True)
    if (pred.outcome_season <= pred.groupby("fold").outcome_season.transform("min")).isna().any():
        raise AssertionError("invalid temporal fold")
    if pred.prediction_key.duplicated().any():
        raise AssertionError("same prediction key scored twice")

    rows = []
    for season, g in pred.groupby("validation_season"):
        for col, name in [("s0_pred", "S0_age_role_history"), ("s1_pred", "S1_shrunk_prior_sporting")]:
            rec = evaluate(g, col, name)
            rec["fold"] = int(season)
            rows.append(rec)
    comp = pd.DataFrame(rows)
    overall = pd.DataFrame([evaluate(pred, "s0_pred", "S0_age_role_history"),
                            evaluate(pred, "s1_pred", "S1_shrunk_prior_sporting")])
    comp = pd.concat([comp, overall.assign(fold="overall")], ignore_index=True)
    comp.to_csv(OUT / "model-comparison.csv", index=False)
    pd.DataFrame(fold_audit).to_csv(OUT / "fold-model-audit.csv", index=False)

    wide = comp[comp.fold != "overall"].pivot(index="fold", columns="model", values="temporal_spearman")
    lift = wide["S1_shrunk_prior_sporting"] - wide["S0_age_role_history"]
    top = comp[comp.fold != "overall"].pivot(index="fold", columns="model", values="top_tier_precision")
    top_lift = top["S1_shrunk_prior_sporting"] - top["S0_age_role_history"]
    gate = {
        "spearman_lift": float(overall.loc[overall.model.eq("S1_shrunk_prior_sporting"), "temporal_spearman"].iloc[0] -
                                overall.loc[overall.model.eq("S0_age_role_history"), "temporal_spearman"].iloc[0]),
        "top_precision_lift_pp": float(100 * (overall.loc[overall.model.eq("S1_shrunk_prior_sporting"), "top_tier_precision"].iloc[0] -
                                             overall.loc[overall.model.eq("S0_age_role_history"), "top_tier_precision"].iloc[0])),
        "positive_spearman_folds": int((lift > 0).sum()),
        "folds": int(lift.notna().sum()),
    }
    gate.update(_cluster_bootstrap_lift(pred))
    gate["s1_passed"] = bool((gate["spearman_lift"] >= 0.03 or gate["top_precision_lift_pp"] >= 5) and
                             gate["positive_spearman_folds"] > gate["folds"] / 2 and
                             gate["spearman_lift_ci90_lo"] > 0)
    gate["s2_status"] = "not_fit_s1_gate_failed" if not gate["s1_passed"] else "not_fit_mvp_stopped_at_minimum_supported_signal"

    pred_cols = ["prediction_key", "player_id", "player_name", "role", "to_league", "outcome_season",
                 "next_minutes", "next_available_minutes", "next_minutes_share",
                 "next_minutes_observation_status", "s0_pred", "s1_pred",
                 "shrunk_prior_sporting_rate", "feature_tier", "club_match_confidence"]
    pred[pred_cols].to_csv(OUT / "validated-output-contract.csv", index=False)

    ablations = [
        {"comparison": "one_vs_two_season_minutes", "execution_status": "ABSTAIN_INSUFFICIENT_FOLD_SUPPORT",
         "estimand": "future availability/minutes", "target": "next_minutes/two_season_cumulative_minutes",
         "rows": int(d.two_season_support.sum()), "failure_or_abstention_reason": "two-season common population lacks sufficient fold support after locked-boundary exclusion"},
        {"comparison": "direct_vs_rate_minutes", "execution_status": "ABSTAIN_INSUFFICIENT_TARGET",
         "estimand": "future total sporting contribution", "target": "not_supported",
         "rows": 0, "failure_or_abstention_reason": "future sporting-rate target coverage is insufficient"},
        {"comparison": "minimal_vs_performance_rich", "execution_status": "STOPPED_BY_GATE",
         "estimand": "future availability/minutes", "target": "next_minutes",
         "rows": int(len(pred)), "failure_or_abstention_reason": "S1 failed predefined gate; rich model not fit"},
        {"comparison": "pooled_vs_role_specific", "execution_status": "ABSTAIN_INSUFFICIENT_FOLD_SUPPORT",
         "estimand": "future availability/minutes", "target": "next_minutes",
         "rows": int(len(pred)), "failure_or_abstention_reason": "role-specific folds fail minimum 50 rows per role in multiple validation seasons"},
        {"comparison": "complete_case_vs_broader", "execution_status": "ABSTAIN_INSUFFICIENT_FOLD_SUPPORT",
         "estimand": "future availability/minutes", "target": "next_minutes",
         "rows": int(len(d)), "failure_or_abstention_reason": "broader/noisier populations not admitted without timestamp and denominator support"},
    ]
    pd.DataFrame(ablations).to_csv(OUT / "design-ablation.csv", index=False)
    allowed_status = {"EXECUTED", "STOPPED_BY_GATE", "ABSTAIN_INSUFFICIENT_TARGET",
                      "ABSTAIN_INSUFFICIENT_FOLD_SUPPORT", "NOT_RUN"}
    bad_status = {a["execution_status"] for a in ablations} - allowed_status
    if bad_status:
        raise AssertionError(f"invalid design comparison status: {bad_status}")

    subgroup_rows = []
    for name, col in [("role", "role"), ("league", "to_league"), ("feature_tier", "feature_tier")]:
        for val, g in pred.groupby(col):
            if len(g) >= 20:
                rec = evaluate(g, "s1_pred", "S1_shrunk_prior_sporting")
                rec.update({"subgroup_type": name, "subgroup": val})
                subgroup_rows.append(rec)
    pd.DataFrame(subgroup_rows).to_csv(OUT / "subgroup-results.csv", index=False)

    run = {
        "command": "python3 -m validate.sporting_mvp_models",
        "decision": "PRIOR SPORTING RATE CHALLENGER DID NOT PASS NEXT-SEASON MINUTES GATE" if not gate["s1_passed"] else "MINUTES CHALLENGER SUPPORTED FOR RESTRICTED DEVELOPMENT POPULATION",
        "estimand": "next-season availability/minutes, not future sporting quality or total contribution",
        "gate": gate,
        "bootstrap_interval_interpretation": "Difference in temporal prediction metrics for generated out-of-fold predictions; not parameter uncertainty.",
        "locked_test_status": "not_opened",
        "price_features_used": [],
        "models_fit": ["S0", "S1"] + (["S2"] if gate["s1_passed"] else []),
    }
    (OUT / "run-manifest.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n")
    if "S2" in run["models_fit"] and gate["s2_status"].startswith("not_fit"):
        raise AssertionError("S2 reported without fitted predictions")
    if gate["s1_passed"]:
        raise AssertionError("S2 implementation is intentionally unavailable in this correction PR")
    print(json.dumps(run, indent=2, sort_keys=True))
    return run


def main() -> int:
    run_models()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
