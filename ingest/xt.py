"""Expected Threat (xT) surface + per-action value weights, fit on StatsBomb events.

WHY THIS EXISTS
---------------
The valuation engine (impact/usage.py) values a player only at shots and the pass
before them (xG + xAG). It is blind to ball PROGRESSION — carrying and passing the
ball into dangerous areas — so it under-prices deep midfielders and ball-playing
defenders. xT (Karun Singh, 2019) measures exactly that: how much a move raises the
probability the possession ends in a goal.

We can't compute true per-action xT for the 2018-2025 Big-5 players we price (no event
data on disk for them). But we DO have full StatsBomb events for **EPL 2015/16** (380
matches, ~438k passes, ~331k carries, ~11.7k shots with xG). So we fit an xT surface
here, then use it (ingest/possession_value.py) to derive an empirical VALUE WEIGHT per
progression action type — replacing defensive_value.py's arbitrary equal weighting with
xT-grounded ones, applied to the tm_player_id-keyed FBref progression data.

METHOD (standard xT value-iteration)
  Grid the pitch 12(x)×8(y). StatsBomb orients every event so the team in possession
  attacks toward x=120 (goal at (120,40)). Per zone z:
    shoot(z) = shots / (shots+moves),  move(z) = moves / (shots+moves)
    goal(z)  = mean statsbomb_xg of shots from z        (mean-xG is steadier than goals/shots)
    T(z→z')  = successful moves z→z' / moves(z)          (incomplete moves -> 0 future value)
    xT(z)    = shoot(z)·goal(z) + move(z)·Σ_z' T(z,z')·xT(z')   (iterate to convergence)
  xt_value(move) = xT(end_zone) − xT(start_zone), for successful moves.

  NO socceraction: it's import-broken here (multimethod 2.0) and heavy; this grid is
  ~80 lines of numpy, self-contained, no network. (Fallback: pin multimethod<2.0.)

Run: python3 -m ingest.xt            -> _check (synthetic, offline)
     python3 -m ingest.xt build      -> fit on cached EPL 2015/16 -> data/impact/xt_weights.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "impact" / "xt_weights.json"

NX, NY = 12, 8            # pitch zones: 12 along length (x, 0..120), 8 across (y, 0..80)
PITCH_X, PITCH_Y = 120.0, 80.0
PROG_DX = 10.0           # a "progressive" move advances >=10 units toward goal (FBref ~10yd)
FINAL_THIRD_X = 80.0     # StatsBomb attacking third begins at x=80
BOX = (102.0, 120.0, 18.0, 62.0)   # opponent penalty area (x0,x1,y0,y1)
FIT_SEASONS = [(2, 27)]  # EPL 2015/16 — the one full league-season cached on disk


def _in_box(x, y):
    return BOX[0] <= x <= BOX[1] and BOX[2] <= y <= BOX[3]


def _zone(x: float, y: float) -> int:
    """Flat zone index 0..NX*NY-1 for a pitch location."""
    cx = min(int(x / (PITCH_X / NX)), NX - 1)
    cy = min(int(y / (PITCH_Y / NY)), NY - 1)
    return cy * NX + cx


# ------------------------------------------------------------------ extract --
def load_moves_shots(seasons=FIT_SEASONS):
    """Pull (moves, shots) from cached StatsBomb events. moves: list of
    (sx, sy, ex, ey, success, kind); shots: list of (x, y, xg)."""
    from ingest import statsbomb as sb

    moves, shots = [], []
    for comp, season in seasons:
        for m in sb.matches(comp, season):
            for e in sb.events(m["match_id"]):
                t = e["type"]["name"]
                loc = e.get("location")
                if t == "Pass" and loc and e["pass"].get("end_location"):
                    end = e["pass"]["end_location"]
                    success = e["pass"].get("outcome") is None      # StatsBomb: no outcome == complete
                    moves.append((loc[0], loc[1], end[0], end[1], success, "pass"))
                elif t == "Carry" and loc and e["carry"].get("end_location"):
                    end = e["carry"]["end_location"]
                    moves.append((loc[0], loc[1], end[0], end[1], True, "carry"))
                elif t == "Shot" and loc:
                    shots.append((loc[0], loc[1], float(e["shot"].get("statsbomb_xg") or 0.0)))
    return moves, shots


# ------------------------------------------------------------------ fit xT ---
def fit_xt(moves, shots, iters=60):
    """Value-iterate the xT surface. Returns a flat np.array length NX*NY."""
    nz = NX * NY
    n_move = np.zeros(nz)
    n_shot = np.zeros(nz)
    xg_sum = np.zeros(nz)
    T = np.zeros((nz, nz))

    for sx, sy, ex, ey, success, _ in moves:
        z = _zone(sx, sy)
        n_move[z] += 1
        if success:
            T[z, _zone(ex, ey)] += 1
    for x, y, xg in shots:
        z = _zone(x, y)
        n_shot[z] += 1
        xg_sum[z] += xg

    total = n_move + n_shot
    with np.errstate(divide="ignore", invalid="ignore"):
        shoot_p = np.where(total > 0, n_shot / total, 0.0)
        move_p = np.where(total > 0, n_move / total, 0.0)
        goal_p = np.where(n_shot > 0, xg_sum / n_shot, 0.0)      # mean xG from the zone
        T = np.where(n_move[:, None] > 0, T / np.where(n_move[:, None] > 0, n_move[:, None], 1), 0.0)

    xt = np.zeros(nz)
    for _ in range(iters):
        xt_new = shoot_p * goal_p + move_p * (T @ xt)
        if np.max(np.abs(xt_new - xt)) < 1e-7:
            xt = xt_new
            break
        xt = xt_new
    return xt


# ---------------------------------------------------------- action weights ---
def action_weights(xt, moves):
    """Mean xt_value (= xT(end) − xT(start)) per action CATEGORY, matching FBref's
    progression columns. A pass into the box carries far more xT than a midfield
    progression — that differentiation is the whole point of xT-weighting."""
    def mean_val(kind, cond):
        vals = [xt[_zone(ex, ey)] - xt[_zone(sx, sy)]
                for sx, sy, ex, ey, ok, k in moves
                if k == kind and ok and cond(sx, sy, ex, ey)]
        return float(np.mean(vals)) if vals else 0.0

    prog = lambda sx, sy, ex, ey: (ex - sx) >= PROG_DX
    f3 = lambda sx, sy, ex, ey: ex >= FINAL_THIRD_X
    box = lambda sx, sy, ex, ey: _in_box(ex, ey)
    return {
        "prog_pass":  mean_val("pass", prog),
        "pass_f3":    mean_val("pass", f3),
        "pass_box":   mean_val("pass", box),
        "prog_carry": mean_val("carry", prog),
        "carry_f3":   mean_val("carry", f3),
        "carry_box":  mean_val("carry", box),
        "all_pass":   mean_val("pass", lambda *a: True),   # baseline, for the self-check
    }


def build():
    print("[xt] loading EPL 2015/16 events (cached)…")
    moves, shots = load_moves_shots()
    print(f"[xt] {len(moves):,} moves, {len(shots):,} shots")
    xt = fit_xt(moves, shots)
    weights = action_weights(xt, moves)
    grid = xt.reshape(NY, NX)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "weights": weights,
        "grid": grid.tolist(),
        "meta": dict(nx=NX, ny=NY, prog_dx=PROG_DX, seasons=[list(s) for s in FIT_SEASONS],
                     n_moves=len(moves), n_shots=len(shots),
                     note="xT fit on StatsBomb EPL 2015/16; weights = mean xT added per action."),
    }, indent=2))
    print(f"[xt] grid max (att third) {grid[:, -1].max():.4f}  own third {grid[:, 0].max():.4f}")
    print(f"[xt] weights: prog_pass {weights['prog_pass']:.5f}  prog_carry {weights['prog_carry']:.5f}")
    print(f"[xt] wrote {OUT}")
    return weights, grid


def load_weights() -> dict:
    if not OUT.exists():
        raise FileNotFoundError(f"{OUT} missing — run `python3 -m ingest.xt build`")
    return json.loads(OUT.read_text())["weights"]


# ---------------------------------------------------------------- selfcheck --
def _check():
    # Synthetic: shots only from the attacking third (high xG near goal), moves that
    # march the ball up-pitch. xT must rise toward goal and progressive weights be > 0.
    moves, shots = [], []
    # up-pitch passes across every zone boundary (progressive), all complete
    for x in range(5, 115, 10):
        moves += [(float(x), 40.0, float(x + 10), 40.0, True, "pass")] * 20
        moves += [(float(x), 40.0, float(x + 10), 40.0, True, "carry")] * 20
    # a few backward passes (non-progressive) to populate all_pass
    moves += [(80.0, 40.0, 60.0, 40.0, True, "pass")] * 10
    # shots only from near goal, with real xG
    shots += [(110.0, 40.0, 0.3)] * 50
    shots += [(60.0, 40.0, 0.02)] * 10

    xt = fit_xt(moves, shots)
    grid = xt.reshape(NY, NX)
    w = action_weights(xt, moves)

    att = grid[:, -1].max()      # attacking third (near x=120)
    own = grid[:, 0].max()       # own third (near x=0)
    assert att > own, f"xT must increase toward goal: att {att:.4f} !> own {own:.4f}"
    assert w["prog_pass"] > 0, f"progressive pass must add xT: {w['prog_pass']}"
    assert w["prog_carry"] > 0, f"progressive carry must add xT: {w['prog_carry']}"
    # progressive (up-pitch) is worth more than the average pass (which includes backward ones)
    assert w["prog_pass"] >= w["all_pass"], "progressive pass should out-value the average pass"
    print(f"xT att-third {att:.4f} > own-third {own:.4f}; "
          f"prog_pass {w['prog_pass']:.4f}, prog_carry {w['prog_carry']:.4f}, all_pass {w['all_pass']:.4f}")
    print("ok")


if __name__ == "__main__":
    import sys
    build() if "build" in sys.argv[1:] else _check()
