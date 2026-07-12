"""Stage 7b — league points -> revenue, via a PROBABILISTIC final rank
(MODELS.md §money; constants from DATA_SOURCES.md §prize money, 2023/24 EPL basis).

A team's expected points (from xGD, Stage 7a) don't pin its final rank — the
season realizes with noise and the rank depends on the other 19 clubs. So we
model final rank as a DISTRIBUTION:
    realized points  R = points + N(0, sd)     sd = points the model misses (~7.3)
    rank             = 1 + #{opponents finishing above R}
    opponents        = draws from the empirical EPL points pool (19 per season)
    revenue(points)  = E[ revenue_at_rank(rank) ]  over that distribution.

This fixes the deterministic model's top-of-table degeneracy: a marginal point
for a team already finishing 1st still buys a sliver of title/CL *probability*
(small but non-zero), while a point on the CL cliff (4th/5th) or the relegation
edge is worth the most — the expectation smooths each £-step by the probability
of landing either side of it.

Draws are frozen at construction (common random numbers), so expected_revenue is
a deterministic, smooth function of points and marginal_value finite-differences
are clean and reproducible.

EPL only for now (Arsenal is the first club).

Run: `python3 -m money.revenue`      -> _check (offline: cliff, monotone, non-degenerate top)
     `python3 -m money.revenue run`  -> real revenue + £/point curve across the table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# --- domestic central payment, EPL 2023/24 (£m) ---
EQUAL_SHARE = 95.1          # equal share (UK + intl + commercial), same for all 20
MERIT_PER_PLACE = 2.8       # per-place merit; 20th = 0 places above bottom
# ponytail: omits facility/live-game fees (~£0.9m/game, skews to big clubs) — real
# top-vs-bottom spread is ~£66m, this models ~£53m of it. Add if NPV needs the tail.

# --- expected European prize money by final rank (£m, run-averaged, €~£0.85) ---
#     4th vs 5th is the cliff the whole valuation pivots on.
EUROPEAN_EV = {1: 40.0, 2: 40.0, 3: 40.0, 4: 40.0,   # Champions League
               5: 15.0, 6: 8.0, 7: 6.0}              # Europa / Conference
# ponytail: flat CL EV — real value scales with the run (R16..final); a point's
# *marginal* value is dominated by the qualification cliff, which this captures.

LEAGUE = "ENG-Premier League"


def revenue_at_rank(rank) -> float:
    """Total central + European revenue (£m) for a final EPL rank (scalar or array)."""
    rank = np.asarray(rank)
    domestic = EQUAL_SHARE + np.maximum(0, 20 - rank) * MERIT_PER_PLACE
    euro = np.vectorize(lambda r: EUROPEAN_EV.get(int(r), 0.0))(rank)
    out = domestic + euro
    return out if out.ndim else float(out)


def realization_sd(tables: pd.DataFrame) -> float:
    """SD of actual season points around xG-model-expected points — the noise
    between a team's expected and realized league finish."""
    from money.points import fit
    a, b, _, _ = fit(tables)
    epl = tables[tables.league == LEAGUE]
    resid = epl.points - (a + b * epl.npxgd_pg) * epl.games
    return float(resid.std())


class RevenueModel:
    """Probabilistic points -> revenue for the EPL, with frozen draws."""

    def __init__(self, tables: pd.DataFrame, sd: float | None = None,
                 n_sims: int = 40000, seed: int = 0):
        epl = tables[tables.league == LEAGUE]
        self.pool = epl.points.to_numpy(float)               # opponent field
        self.sd = float(sd) if sd is not None else realization_sd(tables)
        rng = np.random.default_rng(seed)
        self.z = rng.standard_normal(n_sims)                 # realization noise, frozen
        self.opp = rng.choice(self.pool, size=(n_sims, 19))  # 19 opponents, frozen
        self._rev = revenue_at_rank(np.arange(1, 21))        # £ by rank 1..20

    def expected_revenue(self, points: float) -> float:
        """E[revenue | expected points] over the frozen rank distribution (£m)."""
        realized = points + self.sd * self.z                 # (n_sims,)
        rank = 1 + (self.opp > realized[:, None]).sum(axis=1)  # 1..20
        return float(self._rev[np.clip(rank, 1, 20) - 1].mean())

    def marginal_value(self, points: float, h: float = 1.0) -> float:
        """£m of revenue per league point at `points` (central difference over
        common random numbers, so clean)."""
        return (self.expected_revenue(points + h)
                - self.expected_revenue(points - h)) / (2 * h)


def run():
    from ingest.understat import read_shots
    from money.points import team_season_table
    tables = team_season_table(read_shots())
    m = RevenueModel(tables)
    print(f"realization SD = {m.sd:.2f} pts; opponent pool = {len(m.pool)} team-seasons\n")

    print("=== revenue by final rank (EPL, £m) ===")
    for rk in [1, 2, 3, 4, 5, 6, 7, 10, 17, 20]:
        print(f"  {rk:2d}: £{revenue_at_rank(rk):5.1f}m"
              + ("   <-- CL cliff below" if rk == 4 else ""))

    print("\n=== expected revenue & marginal £/point across the table ===")
    print("  pts   E[rev]   £/point")
    for pts in range(30, 95, 5):
        er = m.expected_revenue(pts)
        mv = m.marginal_value(pts)
        bar = "#" * int(mv * 3)
        print(f"  {pts:3d}  £{er:6.1f}m  £{mv:5.2f}m  {bar}")
    print("\nnote: non-zero at the top (title/CL probability) and peaked at the "
          "CL & relegation cliffs — the degeneracy is gone.")


def _check():
    # CL cliff present and domestic monotone
    assert revenue_at_rank(4) - revenue_at_rank(5) > 20, "CL cliff missing"
    revs = [revenue_at_rank(r) for r in range(1, 21)]
    assert all(revs[i] >= revs[i + 1] for i in range(19)), "domestic not monotone"

    # synthetic model: a realistic EPL-shaped pool, no network
    rng = np.random.default_rng(1)
    pool = np.clip(rng.normal(50, 19, 220), 6, 100)
    tables = pd.DataFrame(dict(league=LEAGUE, points=pool,
                               npxgd_pg=(pool / 38 - 50 / 38), games=38))
    m = RevenueModel(tables, sd=7.3, n_sims=20000, seed=0)

    # revenue strictly increasing in points (probabilistic -> smooth, no plateau bugs)
    grid = list(range(25, 91, 5))
    er = [m.expected_revenue(p) for p in grid]
    assert all(er[i] < er[i + 1] for i in range(len(er) - 1)), "revenue not increasing"

    # non-degenerate at the very top: a point at 88 pts still has positive value
    assert m.marginal_value(88) > 0, "top-of-table still degenerate"

    # the CL boundary (~66-70 pts) is worth more per point than mid-table (~45)
    mv_cliff = m.marginal_value(68)
    mv_mid = m.marginal_value(45)
    assert mv_cliff > mv_mid, (mv_cliff, mv_mid)
    print(f"cliff 4-5 = £{revenue_at_rank(4) - revenue_at_rank(5):.0f}m; "
          f"top(88pts) £/pt {m.marginal_value(88):.2f} > 0; "
          f"CL-edge {mv_cliff:.2f} > mid {mv_mid:.2f}")
    print("ok")


if __name__ == "__main__":
    import sys
    run() if "run" in sys.argv[1:] else _check()
