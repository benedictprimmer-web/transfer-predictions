"""Stage-3 null test: shuffle player identities within team-game, WOWY must
collapse toward zero. If shuffled players still show large impact, the
estimator is reading team/game variance, not players, and the layer is void.
"""
import numpy as np
import pandas as pd

from impact.wowy import wowy


def shuffle_players(lineups: pd.DataFrame, seed=0) -> pd.DataFrame:
    """Permute player labels within each (game_id, team) — windows stay,
    identities randomize, so any per-player season signal is destroyed."""
    rng = np.random.default_rng(seed)
    lu = lineups.copy()
    lu["player"] = (lu.groupby(["game_id", "team"], group_keys=False)
                      .player.transform(lambda s: rng.permutation(s.values)))
    return lu


def _check():
    # synthetic: A always on when team scores. Shuffling kills the pattern.
    games, rows, shots = 40, [], []
    rng = np.random.default_rng(1)
    for g in range(games):
        rows += [dict(game_id=g, team="X", player="A", is_starter=True, minutes=60),
                 dict(game_id=g, team="X", player="B", is_starter=False, minutes=30)]
        shots.append(dict(game_id=g, team_shot="X", minute=int(rng.integers(0, 60)), xg=0.5))
    lu, sh = pd.DataFrame(rows), pd.DataFrame(shots)

    real = wowy(lu, sh).set_index("player")
    null = wowy(shuffle_players(lu), sh).set_index("player")
    assert real.loc["A"].raw > 0.5, "planted signal exists"
    assert abs(null.raw.mean()) < abs(real.loc["A"].raw), "shuffle shrinks it"
    print(f"real A raw {real.loc['A'].raw:+.2f} -> null mean raw {null.raw.mean():+.2f}")
    print("ok")


def main(league="ENG-Premier League", season="2021-2022", n_shuffles=5):
    from validate.ronaldo import wowy_inputs
    lu, sh = wowy_inputs(league, season)

    real = wowy(lu, sh)
    real_spread = real.wowy.abs().mean()

    null_spreads = []
    for i in range(n_shuffles):
        null = wowy(shuffle_players(lu, seed=i), sh)
        null_spreads.append(null.wowy.abs().mean())
    null_spread = float(np.mean(null_spreads))

    print(f"{league} {season}")
    print(f"mean |wowy| real:     {real_spread:.4f}")
    print(f"mean |wowy| shuffled: {null_spread:.4f}  (n={n_shuffles} shuffles)")
    ratio = null_spread / real_spread
    print(f"null/real ratio: {ratio:.2f} -> "
          f"{'PASS (null collapses)' if ratio < 0.5 else 'FAIL (estimator leaks team variance)'}")


if __name__ == "__main__":
    import sys
    main() if "run" in sys.argv[1:] else _check()
