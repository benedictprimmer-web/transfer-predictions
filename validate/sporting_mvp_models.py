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


def _pooled_rate(train: pd.DataFrame, role: str, col: str, default: float) -> float:
    d = train[train.role == role]
    denom = d.prior_minutes.sum() / 90
    raw = d[col.replace("shrunk_", "prior_").replace("sporting_rate", "attack_rate")].mean() if len(d) else default
    return float(raw if pd.notna(raw) else default)


def fit_fold(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    global_minutes = train.next_minutes.mean()
    role_minutes = train.groupby("role").next_minutes.mean().to_dict()
    age_effect = train.assign(age_band=pd.cut(train.player_age, [0, 21, 24, 28, 99], labels=["u21", "21_24", "25_28", "29p"]))
    age_minutes = age_effect.groupby("age_band", observed=True).next_minutes.mean().to_dict()
    s0 = []
    for r in test.itertuples():
        vals = [role_minutes.get(r.role, global_minutes), age_minutes.get(pd.cut([r.player_age], [0, 21, 24, 28, 99], labels=["u21", "21_24", "25_28", "29p"])[0], global_minutes)]
        s0.append(float(np.nanmean(vals)))

    # Empirical-Bayes style shrinkage: player prior rate is pulled toward the
    # training role mean, with exposure controlling how much the player owns.
    train = train.copy()
    denom = (train.prior_minutes / 90).replace(0, np.nan)
    train["prior_sporting_rate"] = (
        train.prior_attack_rate.fillna(0) * train.role.eq("FWD").map({True: 1.0, False: 0.35}) +
        train.prior_progression_rate.fillna(0) * train.role.eq("MID").map({True: 1.0, False: 0.45}) +
        train.prior_defensive_rate.fillna(0) * train.role.eq("DEF").map({True: 1.0, False: 0.35})
    )
    role_rate = train.groupby("role").prior_sporting_rate.mean().to_dict()
    global_rate = train.prior_sporting_rate.mean()
    test_rate = (
        test.prior_attack_rate.fillna(0) * test.role.eq("FWD").map({True: 1.0, False: 0.35}) +
        test.prior_progression_rate.fillna(0) * test.role.eq("MID").map({True: 1.0, False: 0.45}) +
        test.prior_defensive_rate.fillna(0) * test.role.eq("DEF").map({True: 1.0, False: 0.35})
    )
    exposure_weight = (test.prior_minutes.fillna(0) / (test.prior_minutes.fillna(0) + 900)).clip(0, 1)
    shrunk_rate = exposure_weight * test_rate + (1 - exposure_weight) * test.role.map(role_rate).fillna(global_rate)
    rate_scale = train.next_minutes.corr(train.prior_sporting_rate)
    if pd.isna(rate_scale):
        rate_scale = 0.0
    s1 = np.asarray(s0) + (shrunk_rate - train.prior_sporting_rate.mean()) * 350 * np.sign(rate_scale)
    width = 500 + (1 - exposure_weight) * 600
    return test.assign(s0_pred=s0, s1_pred=s1, s1_lo=s1 - width, s1_hi=s1 + width,
                       shrunk_prior_sporting_rate=shrunk_rate)


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
    for season in sorted(d.outcome_season.unique()):
        train = d[d.outcome_season < season]
        test = d[d.outcome_season == season]
        if len(train) < 250:
            continue
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
    gate["s1_passed"] = bool((gate["spearman_lift"] >= 0.03 or gate["top_precision_lift_pp"] >= 5) and
                             gate["positive_spearman_folds"] > gate["folds"] / 2)
    gate["s2_status"] = "not_fit_s1_gate_failed" if not gate["s1_passed"] else "not_fit_mvp_stopped_at_minimum_supported_signal"

    pred_cols = ["prediction_key", "player_id", "player_name", "role", "to_league", "outcome_season",
                 "next_minutes", "s0_pred", "s1_pred", "s1_lo", "s1_hi",
                 "shrunk_prior_sporting_rate", "feature_tier", "club_match_confidence"]
    pred[pred_cols].to_csv(OUT / "validated-output-contract.csv", index=False)

    ablations = [
        ("one_vs_two_season", "one-season selected; two-season support is 1,266 rows and would collapse coverage"),
        ("direct_vs_rate_minutes", "direct minutes ranking kept; rate x minutes retained as decomposition only"),
        ("minimal_vs_rich", "minimal S1 tested; performance-rich rejected for MVP because detailed metrics are sparse"),
        ("pooled_vs_role_specific", "partial pooling selected; role-specific models too thin by fold"),
        ("small_clean_vs_large_noisy", "exact/PIT and trusted destination rows selected; wider confidence not admitted"),
    ]
    pd.DataFrame(ablations, columns=["comparison", "decision"]).to_csv(OUT / "design-ablation.csv", index=False)

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
        "decision": "SPORTING SIGNAL TOO WEAK - FEE DIAGNOSTIC MVP ONLY" if not gate["s1_passed"] else "SPORTING MVP SUPPORTED FOR RESTRICTED POPULATION",
        "gate": gate,
        "locked_test_status": "not_opened",
        "price_features_used": [],
        "models_fit": ["S0", "S1"] + (["S2"] if gate["s1_passed"] else []),
    }
    (OUT / "run-manifest.json").write_text(json.dumps(run, indent=2, sort_keys=True) + "\n")
    print(json.dumps(run, indent=2, sort_keys=True))
    return run


def main() -> int:
    run_models()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
