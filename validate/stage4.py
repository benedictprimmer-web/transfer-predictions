"""Stage 4 — the make-or-break gate: does the usage model predict impact
out-of-sample on completed transfers?

Predictor (mechanistic v0, per MODELS.md — no fitting, so no leakage):
    predicted_gain = usage_share_from x (efficiency_from - team_to_eff_before)
Efficiency travels with the player; usage is approximated by his origin share
(v0 heuristic; destination reallocation model comes later if this carries
signal). team_to_eff_before = destination team's value per terminal action in
the season before he arrives: the bar his efficiency must clear.

Targets, both measured after the move:
  1. wowy       — his on/off xGD at the destination (noisy per player, but
                  direction pools across ~2k movers)
  2. delta_team_xgd90 — destination team npxGD/90 change season-over-season
                  (the before/after design; catches system effects on/off
                  can't). Controlled for mean reversion + other signings via
                  OLS partial correlation.

Gate: positive correlation, bootstrap 95% CI excluding zero, reported per
target and per era. If the CI straddles zero, stop and say so.
"""
import numpy as np
import pandas as pd

PANEL = "data/stage4/panel.csv"


def team_eff_before(shots: pd.DataFrame) -> pd.DataFrame:
    """Destination bar: team value per terminal action, per team-season."""
    from impact.usage import usage_efficiency
    u = usage_efficiency(shots)
    g = u.groupby(["league", "season", "team"], as_index=False).agg(
        team_value=("value", "sum"), team_actions=("actions", "sum"))
    g["team_eff"] = g.team_value / g.team_actions
    return g[["league", "season", "team", "team_eff"]]


def add_prediction(panel: pd.DataFrame, teff: pd.DataFrame) -> pd.DataFrame:
    p = panel.merge(
        teff.rename(columns={"league": "league_to", "season": "season_from",
                             "team": "team_to", "team_eff": "team_to_eff_before"}),
        on=["league_to", "season_from", "team_to"], how="left")
    p["predicted_gain"] = p.usage_share_from * (p.efficiency_from - p.team_to_eff_before)
    return p


def boot_corr(x, y, n=2000, seed=0, method="spearman"):
    """correlation + bootstrap 95% CI, NaNs dropped pairwise."""
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(d) < 10:
        return np.nan, (np.nan, np.nan), len(d)
    rng = np.random.default_rng(seed)
    r = d.x.corr(d.y, method=method)
    bs = [d.sample(len(d), replace=True, random_state=rng.integers(1e9))
            .pipe(lambda s: s.x.corr(s.y, method=method)) for _ in range(n)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return r, (lo, hi), len(d)


def partial_slope(panel: pd.DataFrame, n_boot=2000, seed=0):
    """delta_team_xgd90 ~ predicted_gain + controls (OLS via lstsq).
    Returns slope on predicted_gain with bootstrap CI."""
    cols = ["predicted_gain", "team_np_xgd90_before", "usage_inflow_other",
            "n_other_movers_in"]
    d = panel[cols + ["delta_team_xgd90"]].dropna()
    X = np.column_stack([np.ones(len(d))] + [d[c] for c in cols])
    y = d.delta_team_xgd90.values

    def fit(Xa, ya):
        return np.linalg.lstsq(Xa, ya, rcond=None)[0][1]  # predicted_gain coef

    slope = fit(X, y)
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n_boot):
        i = rng.integers(0, len(d), len(d))
        bs.append(fit(X[i], y[i]))
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return slope, (lo, hi), len(d)


def _check():
    rng = np.random.default_rng(0)
    n = 400
    pred = rng.normal(0, .01, n)
    # planted: target = signal + heavy noise; boot CI must still exclude 0
    wowy = 5 * pred + rng.normal(0, .1, n)
    r, (lo, hi), m = boot_corr(pred, wowy, n=500)
    assert r > 0 and lo > 0, (r, lo, hi)
    # null: no relation -> CI straddles zero
    r0, (lo0, hi0), _ = boot_corr(pred, rng.normal(0, .1, n), n=500)
    assert lo0 < 0 < hi0, (r0, lo0, hi0)

    # partial slope recovers a planted coefficient with a confounder
    conf = rng.normal(0, .5, n)
    df = pd.DataFrame(dict(
        predicted_gain=pred, team_np_xgd90_before=conf,
        usage_inflow_other=rng.uniform(0, .3, n), n_other_movers_in=rng.integers(0, 5, n),
        delta_team_xgd90=4 * pred - 0.5 * conf + rng.normal(0, .05, n)))
    s, (slo, shi), _ = partial_slope(df, n_boot=300)
    assert slo > 0 and abs(s - 4) < 1.5, (s, slo, shi)
    print(f"planted corr {r:.2f} [{lo:.2f},{hi:.2f}]; null [{lo0:.2f},{hi0:.2f}]; "
          f"slope {s:.1f} [{slo:.1f},{shi:.1f}]")
    print("ok")


def main():
    from ingest.understat import read_shots
    panel = pd.read_csv(PANEL)
    p = add_prediction(panel, team_eff_before(read_shots()))
    p_w = p[p.on_min >= 450]  # wowy target needs a real minutes sample

    print(f"panel {len(p)} movers; prediction available {p.predicted_gain.notna().sum()}; "
          f"wowy target n={p_w.wowy.notna().sum()} (on_min>=450)")

    print("\n=== GATE: predicted_gain vs realized targets (spearman, boot 95% CI) ===")
    for name, frame, target in [("WOWY at destination", p_w, "wowy"),
                                ("team npxGD/90 delta", p, "delta_team_xgd90")]:
        r, (lo, hi), n = boot_corr(frame.predicted_gain, frame[target])
        verdict = "PASS" if lo > 0 else ("FAIL" if hi < 0 else "INCONCLUSIVE (CI spans 0)")
        print(f"{name:22s} r={r:+.3f}  CI[{lo:+.3f},{hi:+.3f}]  n={n}  -> {verdict}")

    s, (slo, shi), n = partial_slope(p)
    verdict = "PASS" if slo > 0 else ("FAIL" if shi < 0 else "INCONCLUSIVE (CI spans 0)")
    print(f"\npartial slope (controls: mean reversion, churn): "
          f"{s:+.2f}  CI[{slo:+.2f},{shi:+.2f}]  n={n}  -> {verdict}")

    print("\n=== per era (leakage check: relation should hold across time) ===")
    p["era"] = np.where(p.season_to < "2019", "2015-2018", "2019-2024")
    for era, g in p.groupby("era"):
        r, (lo, hi), n = boot_corr(g.predicted_gain, g.delta_team_xgd90)
        print(f"{era}: r={r:+.3f} CI[{lo:+.3f},{hi:+.3f}] n={n}")


if __name__ == "__main__":
    import sys
    main() if "run" in sys.argv[1:] else _check()
