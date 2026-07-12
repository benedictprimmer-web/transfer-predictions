"""League strength — how a unit of attacking output converts between leagues.

MODELS.md §2: two-way fixed effects on player output, league FE identified by
players who moved. We implement it as a WITHIN-player estimator: demean each
player's log-output across his own seasons (weighted by volume), then regress
the residual on league dummies with ridge. Movers are the only rows that carry
within-player league variation, so they alone identify the multipliers —
exactly the intended identification, and non-movers harmlessly contribute ~0.

WHAT TRAVELS, precisely. Understat xG is a single fixed model applied in every
league, so a 0.1xG chance is 0.1 everywhere — the multiplier is NOT a finishing
adjustment. It captures the *chance quality a player achieves against a league's
defences*: move to a stronger league, get into worse positions per action, your
value-per-action falls. That fall, measured on the same player across his move,
is the multiplier.

HONEST LIMITS (do not hide): identified off a few hundred movers per pair,
selected for moving (survivorship biases multipliers toward the stronger league
-> report wide CIs, weight by minutes). Age is a mild uncontrolled confounder
here; the age-curve layer carries it, and moves happen across varied ages so it
partly averages out. RFPL has few clean movers -> its interval will be wide.
ClubElo is the prior/sanity check, never the answer.
"""
import numpy as np
import pandas as pd

REF = "ENG-Premier League"          # multipliers are relative to the EPL = 1.00
BIG = ["ENG-Premier League", "ESP-La Liga", "ITA-Serie A",
       "GER-Bundesliga", "FRA-Ligue 1", "RUS-Premier League"]


def player_season_output(shots: pd.DataFrame, min_actions=30) -> pd.DataFrame:
    """(player, league, season) -> efficiency, actions, value. A player with two
    clubs in a league-season is pooled; cross-league same-season rows stay split
    (that within-season split is itself identifying if he moved mid-year)."""
    from impact.usage import usage_efficiency
    u = usage_efficiency(shots)
    g = (u.groupby(["player", "league", "season"], as_index=False)
           .agg(actions=("actions", "sum"), value=("value", "sum")))
    g["efficiency"] = g.value / g.actions
    return g[g.actions >= min_actions].reset_index(drop=True)


def _wdemean(cols: np.ndarray, w: np.ndarray, pid: np.ndarray) -> np.ndarray:
    """Vectorised weighted within-`pid` demeaning of each column of `cols`."""
    f = pd.factorize(pid)[0]
    sw = np.bincount(f, weights=w)
    out = np.empty_like(cols, dtype=float)
    for j in range(cols.shape[1]):
        wm = np.bincount(f, weights=w * cols[:, j]) / sw
        out[:, j] = cols[:, j] - wm[f]
    return out


def _fit_once(d: pd.DataFrame, leagues, ridge) -> dict:
    """Weighted within-player ridge of log-efficiency on league dummies.
    Returns {league: multiplier relative to REF}."""
    y = np.log(d.efficiency.clip(lower=1e-4).values)[:, None]
    w = d.actions.values.astype(float)
    D = pd.get_dummies(d.league).reindex(columns=leagues, fill_value=0).values.astype(float)
    pid = d.player.values

    M = _wdemean(np.hstack([y, D]), w, pid)          # absorb player FE
    yb, Db = M[:, :1], M[:, 1:]

    A = Db.T * w @ Db + ridge * np.eye(Db.shape[1])   # weighted ridge
    beta = np.linalg.solve(A, (Db.T * w) @ yb).ravel()
    beta -= beta[leagues.index(REF)]                  # REF = 0 in log space
    return {lg: float(np.exp(b)) for lg, b in zip(leagues, beta)}


def fit_league_strength(po: pd.DataFrame, leagues=BIG, ridge=1.0,
                        n_boot=400, seed=0) -> pd.DataFrame:
    """Multiplier per league (EPL=1.00) with player-bootstrap 95% CI.
    <1 means output there converts to less in EPL terms (weaker league)."""
    po = po[po.league.isin(leagues)]
    point = _fit_once(po, leagues, ridge)

    # cluster bootstrap over players: pre-split each player's rows once, then
    # each resample draws players and gives every draw a FRESH id (so duplicate
    # draws are independent FE clusters, the correct clustered bootstrap).
    players = po.player.unique()
    blocks = {p: g for p, g in po.groupby("player")}
    rng = np.random.default_rng(seed)
    boots = {lg: [] for lg in leagues}
    for _ in range(n_boot):
        samp = rng.choice(players, len(players), replace=True)
        parts = []
        for k, p in enumerate(samp):
            b = blocks[p].copy(); b["player"] = k
            parts.append(b)
        d = pd.concat(parts, ignore_index=True)
        try:
            f = _fit_once(d, leagues, ridge)
            for lg in leagues:
                boots[lg].append(f[lg])
        except np.linalg.LinAlgError:
            continue

    # movers-in/out count per league (rows where the player is seen in >1 league)
    multi = po.groupby("player").league.nunique()
    movers = po[po.player.isin(multi[multi > 1].index)]
    mv = movers.groupby("league").player.nunique()

    rows = []
    for lg in leagues:
        b = np.array(boots[lg])
        rows.append(dict(league=lg, multiplier=round(point[lg], 3),
                         lo=round(np.percentile(b, 2.5), 3),
                         hi=round(np.percentile(b, 97.5), 3),
                         movers=int(mv.get(lg, 0))))
    return pd.DataFrame(rows).sort_values("multiplier", ascending=False).reset_index(drop=True)


def multiplier_map(strength: pd.DataFrame) -> dict:
    return dict(zip(strength.league, strength.multiplier))


def translate(efficiency, from_league, to_league, mult: dict):
    """Restate an efficiency observed in from_league into to_league terms.
    mult is EPL-relative; the ratio cancels the reference."""
    fm = np.array([mult.get(l, np.nan) for l in np.atleast_1d(from_league)])
    tm = np.array([mult.get(l, np.nan) for l in np.atleast_1d(to_league)])
    return np.asarray(efficiency) * (tm / fm)


def _check():
    # synthetic: 3 leagues, B=0.7x and C=0.5x of A for the SAME player.
    rng = np.random.default_rng(0)
    rows = []
    for p in range(120):
        base = rng.uniform(.08, .22)          # player's true A-league efficiency
        for lg, k in [("ENG-Premier League", 1.0), ("ESP-La Liga", .7), ("ITA-Serie A", .5)]:
            if rng.random() < 0.5:            # ~half the players seen in each league
                rows.append(dict(player=f"p{p}", league=lg,
                                 season="x", actions=rng.integers(30, 300),
                                 efficiency=base * k * rng.lognormal(0, .12)))
    po = pd.DataFrame(rows)
    s = fit_league_strength(po, leagues=["ENG-Premier League", "ESP-La Liga", "ITA-Serie A"],
                            ridge=0.05, n_boot=120)
    m = multiplier_map(s)
    assert abs(m["ENG-Premier League"] - 1.0) < 1e-9
    assert abs(m["ESP-La Liga"] - 0.7) < 0.12, m
    assert abs(m["ITA-Serie A"] - 0.5) < 0.12, m
    # translate: 0.10 eff in La Liga -> ~0.10/0.7 in EPL terms
    t = translate(0.10, "ESP-La Liga", "ENG-Premier League", m)[0]
    assert abs(t - 0.10 / 0.7) < 0.03, t
    print(s.to_string(index=False))
    print("ok")


def main():
    from ingest.understat import read_shots
    po = player_season_output(read_shots())
    s = fit_league_strength(po)
    print(s.to_string(index=False))
    try:
        from ingest.strength import league_strength  # ClubElo sanity, if built
        print("\n(ClubElo ordering is the independent sanity check — see ingest/strength.py)")
    except Exception:
        pass
    s.to_csv("data/league_strength.csv", index=False)
    print("\nwrote data/league_strength.csv")


if __name__ == "__main__":
    import sys
    main() if "run" in sys.argv[1:] else _check()
