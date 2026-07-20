"""D1 — the scout board. Turns the single-transfer pricer into a market scan:
rank a universe of real players by NPV-to-Arsenal, full stack on each.

Candidate universe = Understat efficiency + usage (a recent season, min volume)
joined to Transfermarkt (age, position, latest market value) via the solo-name
crosswalk. Fee assumed ≈ market value (the standard first approximation; swap in
Agent B's fee_pred per player when pricing a specific deal). Wage modelled.

    python3 -m money.scout            -> _check (synthetic, no network)
    python3 -m money.scout run        -> build the board, print top/bottom, cache CSV
    python3 -m money.scout run --season 2023-2024 --top 25 --max-age 27
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

from money.npv import npv_transfer, npv_band, calibration
from impact.aging import POS_GROUP

LEAGUE = "ENG-Premier League"
OUT = Path(__file__).resolve().parent.parent / "data" / "money" / "scout_arsenal.csv"
_POSS = None


def _prog_pctl(tid, season_end):
    """Buildup-progression percentile (ingest/possession_value.py) — DESCRIPTIVE only.
    It failed the NPV predictor gate (validate/possession_gate), so it never enters the
    valuation; it rides the board as a scouting flag (0-100) the shot-based NPV can't see."""
    global _POSS
    if _POSS is None:
        p = Path(__file__).resolve().parent.parent / "data" / "impact" / "possession_value.parquet"
        _POSS = (pd.read_parquet(p).groupby(["tm_player_id", "season_end_year"])
                 .possession_value_score.mean() if p.exists() else pd.Series(dtype=float))
    if tid is None or _POSS.empty:
        return None
    try:
        return round(float(_POSS.loc[(tid, season_end)]))
    except KeyError:
        try:
            return round(float(_POSS.loc[tid].iloc[-1]))     # fall back to his latest season
        except Exception:
            return None


def candidate_universe(ue: pd.DataFrame, season: str, min_actions: float = 150) -> pd.DataFrame:
    """Players with a real `season` in Understat, enriched with TM age/position/MV.
    One row per player (his highest-volume team that season)."""
    from ingest.transfermarkt import _read, download
    from ingest.crosswalk import norm_player

    g = ue[(ue.season == season) & (ue.actions >= min_actions)].sort_values("actions")
    main = g.groupby("player", as_index=False).tail(1).copy()      # his main team-season
    main["key"] = main.player.map(norm_player)

    download(("players", "player_valuations"))
    pl = _read("players", usecols=["player_id", "name", "date_of_birth", "position"])
    pl["key"] = pl.name.map(norm_player)
    solo = pl.groupby("key").player_id.nunique().loc[lambda s: s == 1].index  # unambiguous only
    pl = pl[pl.key.isin(solo)].drop_duplicates("key")
    pv = _read("player_valuations", usecols=["player_id", "date", "market_value_in_eur"])
    pv["date"] = pd.to_datetime(pv.date, errors="coerce")
    mv = pv.sort_values("date").groupby("player_id").tail(1)[["player_id", "market_value_in_eur"]]
    pl = pl.merge(mv, on="player_id", how="left")

    m = main.merge(pl[["key", "player_id", "date_of_birth", "position", "market_value_in_eur"]],
                   on="key", how="left")
    m = m.rename(columns={"player_id": "tm_player_id"})   # carry TM id -> real-wage lookup
    yr = int(season[:4])
    dob = pd.to_datetime(m.date_of_birth, errors="coerce")
    m["age"] = (pd.Timestamp(yr + 1, 1, 1) - dob).dt.days / 365.25
    m["mv_eur_m"] = m.market_value_in_eur / 1e6
    return m.dropna(subset=["age", "mv_eur_m", "position"])


def _destination(ue, tteam, revmodel, to_team, to_season, context_points):
    """Destination baseline. team_eff from `to_season` (or the latest complete
    one). £/point priced at `context_points` — a REPRESENTATIVE competitive final
    position — unless to_season is pinned, in which case that season's actual
    points are used. This decouples the board from an anomalous season: a
    title-winning club has ~zero marginal table upside, which would make every
    signing look bad; a CL-contender (~72 pts) is the realistic decision context."""
    tt = tteam[(tteam.league == LEAGUE) & (tteam.team == to_team)]
    full = tt[tt.games >= 34]
    eff_season = to_season or (full if not full.empty else tt).sort_values("season").season.iloc[-1]
    team_eff = ue[(ue.league == LEAGUE) & (ue.team == to_team) & (ue.season == eff_season)] \
        .pipe(lambda d: d.value.sum() / d.actions.sum())
    pts = tt[tt.season == to_season].iloc[0].points if to_season else context_points
    return eff_season, team_eff, revmodel.marginal_value(pts) * 1e6, pts


def scout(*, to_team="Arsenal", to_season=None, context_points=72, min_actions=90,
          max_age=29, fee_mult=1.0, contract=5, ue=None, tteam=None, revmodel=None,
          season=None, cands=None):
    """Rank candidates by NPV-to-`to_team`. Returns the full scored frame.
    `context_points` sets the competitive position signings are priced against
    (default 72 = CL race). Pass `cands` to skip the network universe build."""
    from ingest.understat import read_shots
    from impact.usage import usage_efficiency
    from money.points import team_season_table
    from money.revenue import RevenueModel
    from ingest.wages import estimate_wage

    if ue is None:
        shots = read_shots(); ue = usage_efficiency(shots)
    if tteam is None:
        tteam = team_season_table(read_shots())
    if revmodel is None:
        revmodel = RevenueModel(tteam)
    if season is None:
        season = sorted(ue.season.unique())[-2]   # penultimate = latest complete

    dseason, team_eff, gbp_per_point, team_points = _destination(
        ue, tteam, revmodel, to_team, to_season, context_points)
    cal = calibration()
    if cands is None:
        cands = candidate_universe(ue, season, min_actions)
    cands = cands[(cands.position.map(POS_GROUP).isin(["FW", "MF", "DF"]))     # no GK
                  & (cands.age <= max_age) & (cands.team != to_team) & (cands.mv_eur_m > 0)]

    rows = []
    for c in cands.itertuples():
        fee = c.mv_eur_m * 1e6 * 0.85 * fee_mult
        tid = getattr(c, "tm_player_id", None)
        tid = int(tid) if pd.notna(tid) else None            # prefer real Capology/FIFA wage
        w = estimate_wage(c.age, LEAGUE, c.mv_eur_m, c.position, tm_player_id=tid)
        common = dict(efficiency=c.efficiency, usage_share=c.usage_share, team_eff=team_eff,
                      gbp_per_point=gbp_per_point, age=c.age, position=c.position, fee_gbp=fee,
                      contract_years=contract, market_value_gbp=c.mv_eur_m * 1e6 * 0.85)
        npv, _, _ = npv_transfer(cal_slope=cal["slope"], wage_annual_gbp=w.annual_wage_gbp, **common)
        lo, cen, hi = npv_band(wage_lo=w.lo, wage_hi=w.hi, cal_lo=cal["lo"], cal_hi=cal["hi"],
                               wage_annual_gbp=w.annual_wage_gbp, cal_slope=cal["slope"], **common)
        rows.append(dict(player=c.player, from_league=c.league, age=round(c.age, 1),
                         position=POS_GROUP.get(c.position, c.position),
                         efficiency=round(c.efficiency, 4), usage=round(c.usage_share, 3),
                         mv_eur_m=round(c.mv_eur_m, 1), fee_gbp_m=round(fee / 1e6, 1),
                         wage_gbp_m=round(w.annual_wage_gbp / 1e6, 1),
                         npv_m=round(cen / 1e6, 1), npv_lo_m=round(lo / 1e6, 1),
                         npv_hi_m=round(hi / 1e6, 1),
                         prog_pctl=_prog_pctl(tid, int(season[:4]) + 1)))  # descriptive scouting flag
    board = pd.DataFrame(rows).sort_values("npv_m", ascending=False).reset_index(drop=True)
    board.attrs.update(to_team=to_team, dseason=dseason, season=season,
                       gbp_per_point=gbp_per_point, team_points=team_points)
    return board


def run(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None)
    ap.add_argument("--to", default="Arsenal", dest="to_team")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-actions", type=float, default=90, dest="min_actions")
    ap.add_argument("--max-age", type=float, default=29, dest="max_age")
    ap.add_argument("--context-points", type=float, default=72, dest="context_points",
                    help="competitive final position to price against (default 72 = CL race)")
    a = ap.parse_args(argv)

    board = scout(to_team=a.to_team, season=a.season, min_actions=a.min_actions,
                  max_age=a.max_age, context_points=a.context_points)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(OUT, index=False)
    at = board.attrs
    print(f"Scout board: {len(board)} candidates (from {at['season']}) priced to "
          f"{at['to_team']} as a {at['team_points']:.0f}-pt club "
          f"(£{at['gbp_per_point']/1e6:.2f}m/point; eff bar from {at['dseason']})\n")
    cols = ["player", "from_league", "age", "position", "efficiency", "usage", "prog_pctl",
            "mv_eur_m", "fee_gbp_m", "wage_gbp_m", "npv_m", "npv_lo_m", "npv_hi_m"]
    print(f"=== TOP {a.top} by NPV ===")
    print(board.head(a.top)[cols].to_string(index=False))
    print(f"\n=== BOTTOM 5 (worst value) ===")
    print(board.tail(5)[cols].to_string(index=False))
    print(f"\nwrote {OUT}  (fee≈MV; NPV = on-pitch table value only, wide bands — see MEMO)")


def _check():
    # synthetic universe -> ranking runs, better player ranks above worse
    ue = pd.DataFrame([
        dict(league="X", season="2023-2024", team="Z", player="Great", game_id=1,
             actions=250, value=45.0, usage_share=0.20, efficiency=0.18),
        dict(league="X", season="2023-2024", team="Z", player="Weak", game_id=1,
             actions=250, value=20.0, usage_share=0.20, efficiency=0.08),
        dict(league=LEAGUE, season="2023-2024", team="Arsenal", player="A", game_id=2,
             actions=200, value=20.0, usage_share=0.15, efficiency=0.10)])
    tteam = pd.DataFrame([dict(league=LEAGUE, season="2023-2024", team="Arsenal",
                              points=70, games=38, npxgd_pg=0.5)])

    class FakeRev:
        def marginal_value(self, p): return 2.0

    fake = pd.DataFrame([
        dict(player="Great", league="X", team="Z", efficiency=0.18, usage_share=0.20,
             age=25.0, position="Attack", mv_eur_m=50.0),
        dict(player="Weak", league="X", team="Z", efficiency=0.08, usage_share=0.20,
             age=25.0, position="Attack", mv_eur_m=50.0)])
    board = scout(ue=ue, tteam=tteam, revmodel=FakeRev(), season="2023-2024", cands=fake)
    assert list(board.player) == ["Great", "Weak"], list(board.player)
    assert board.iloc[0].npv_m > board.iloc[1].npv_m
    print(f"board ranks Great ({board.iloc[0].npv_m:+.1f}m) > Weak ({board.iloc[1].npv_m:+.1f}m)")
    print("ok")


if __name__ == "__main__":
    import sys
    (run(sys.argv[2:]) if "run" in sys.argv[1:2] else _check())
