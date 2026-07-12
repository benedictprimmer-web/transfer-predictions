"""xg_model — our own xG from shot geometry, enabled by the shots.pkl fidelity
fix (X/Y/shot_type were being dropped; now present).

WHY this exists (audit P3): the confident xG corpus is Big-5 + RFPL, because
those are the only leagues with free Opta xG. Selling leagues (Eredivisie,
Championship, Portugal, Brazil) — the ones you scout inbound talent FROM — have
NO free xG and, more fundamentally, NO free shot-location data at all. So a
geometry xG model does NOT by itself fill that gap (there are no coordinates to
score). What it DOES give:
  1. a *validated, self-owned* xG we control — not dependent on Opta's feed
     (which FBref already lost once, Jan 2025);
  2. shot-quality features (distance, angle) for the impact stack;
  3. a drop-in scorer for the one place selling-league shot data IS free —
     StatsBomb open-data (same X/Y geometry) — should that route be taken.

Model: logistic regression on [distance, angle, is_header, is_open_play].
Understat X/Y are normalized 0..1 (X = along length toward attacked goal at
x=1, Y = across, goal centre y=0.5). Penalties excluded (npxG basis, as the
rest of the project). Trained/validated by season split; reported against both
actual goals (log-loss, Brier) and Understat's own xG (agreement).
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
PITCH_L, PITCH_W = 105.0, 68.0          # metres
GOAL_HALF = 7.32 / 2                     # half goal-width, metres


def geometry(x, y):
    """Understat normalized (x,y) -> (distance_m, angle_rad) to attacked goal.

    Goal centre at (1, 0.5). distance in metres; angle = the horizontal angle
    subtended by the two posts from the shot location (bigger = better chance).
    """
    x = np.asarray(x, float); y = np.asarray(y, float)
    dx = (1.0 - x) * PITCH_L                        # metres to goal line
    dy = (y - 0.5) * PITCH_W                         # metres off-centre
    dist = np.sqrt(dx**2 + dy**2)
    # angle between the posts (law of cosines via the two post vectors)
    a = np.hypot(dx, dy - GOAL_HALF)
    b = np.hypot(dx, dy + GOAL_HALF)
    cos = (a**2 + b**2 - (2 * GOAL_HALF) ** 2) / (2 * a * b)
    angle = np.arccos(np.clip(cos, -1, 1))
    return dist, angle


def features(shots: pd.DataFrame) -> pd.DataFrame:
    d = shots.dropna(subset=["x", "y", "xg"]).copy()
    d = d[d.situation != "Penalty"]                  # npxG basis
    dist, angle = geometry(d.x, d.y)
    return pd.DataFrame({
        "distance": dist, "angle": angle,
        "is_header": d.shot_type.fillna("").str.contains("Head").astype(float),
        "is_open_play": (d.situation == "OpenPlay").astype(float),
        "goal": (d.result == "Goal").astype(float),
        "understat_xg": d.xg.astype(float),
        "season": d.season.values,
    }).reset_index(drop=True)


def fit_eval(f: pd.DataFrame) -> dict:
    """Train on earlier seasons, evaluate out-of-sample on the latest two."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss, brier_score_loss
    seasons = sorted(f.season.unique())
    test_seasons = set(seasons[-2:])
    tr, te = f[~f.season.isin(test_seasons)], f[f.season.isin(test_seasons)]
    X = ["distance", "angle", "is_header", "is_open_play"]
    m = LogisticRegression(max_iter=1000).fit(tr[X], tr.goal)
    p = m.predict_proba(te[X])[:, 1]
    # baseline = predict the mean conversion rate
    base = np.full(len(te), tr.goal.mean())
    return {
        "n_train": len(tr), "n_test": len(te),
        "logloss": log_loss(te.goal, p),
        "logloss_baseline": log_loss(te.goal, base),
        "brier": brier_score_loss(te.goal, p),
        "corr_vs_understat": float(np.corrcoef(p, te.understat_xg)[0, 1]),
        "mean_pred": float(p.mean()), "mean_actual": float(te.goal.mean()),
        "mean_understat": float(te.understat_xg.mean()),
        "coef": dict(zip(X, m.coef_[0].round(4))),
        "model": m, "features": X,
    }


def build():
    from ingest import understat
    shots = understat.read_shots()
    f = features(shots)
    r = fit_eval(f)
    print("=" * 56)
    print("xG-from-geometry  (npxG basis, season out-of-sample)")
    print("=" * 56)
    print(f"  train shots {r['n_train']:,} / test {r['n_test']:,}")
    print(f"  log-loss        {r['logloss']:.4f}  (baseline {r['logloss_baseline']:.4f})")
    print(f"  Brier           {r['brier']:.4f}")
    print(f"  corr vs Understat xG   {r['corr_vs_understat']:.3f}")
    print(f"  calibration  pred {r['mean_pred']:.3f} | actual {r['mean_actual']:.3f} "
          f"| understat {r['mean_understat']:.3f}")
    print(f"  coefs           {r['coef']}")
    print("\n  COVERAGE NOTE: this scores any source with shot X/Y. Understat &")
    print("  StatsBomb have it; selling-league free feeds do NOT — so this")
    print("  validates our xG and unlocks StatsBomb, but does not by itself")
    print("  create selling-league coverage (no coordinates exist to score).")
    return r


# ------------------------------------------------------------------ check

def _check():
    # geometry sanity: penalty spot vs corner of the box
    dist_c, ang_c = geometry([0.88], [0.5])   # central, ~12.6m out
    dist_w, ang_w = geometry([0.88], [0.9])   # same depth, wide
    assert 10 < dist_c[0] < 15, dist_c
    assert ang_c[0] > ang_w[0], "central shot subtends a wider angle than a wide one"
    dist_far, _ = geometry([0.5], [0.5])
    assert dist_far[0] > dist_c[0], "halfway line is farther than the box"

    # a tiny fit: closer/central shots convert more -> model learns negative
    # distance coef and positive angle coef
    rng = np.random.RandomState(0)
    n = 4000
    x = rng.uniform(0.6, 0.99, n); y = rng.uniform(0.2, 0.8, n)
    dist, angle = geometry(x, y)
    p_true = 1 / (1 + np.exp(-(3.0 - 0.25 * dist + 2.0 * angle)))
    goal = (rng.uniform(size=n) < p_true).astype(float)
    # 3 seasons so the season-holdout split (last two) leaves a real train set
    season = np.array(["2017-2018", "2018-2019", "2019-2020"])[np.arange(n) % 3]
    f = pd.DataFrame({"x": x, "y": y, "xg": p_true, "situation": "OpenPlay",
                      "shot_type": "RightFoot", "result": np.where(goal == 1, "Goal", "Miss"),
                      "season": season})
    r = fit_eval(features(f))
    assert r["coef"]["distance"] < 0, ("farther = worse", r["coef"])
    assert r["coef"]["angle"] > 0, ("wider angle = better", r["coef"])
    assert r["logloss"] < r["logloss_baseline"], "model beats mean-rate baseline"
    print(f"geometry ok; fit coefs {r['coef']}; logloss {r['logloss']:.3f} "
          f"< baseline {r['logloss_baseline']:.3f}")
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
