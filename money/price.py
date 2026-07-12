"""Stage 8 — the interface. Price any transfer for a club, end-to-end, with error
bars and quality flags on every input. Assembles real numbers from the engine and
runs the full stack (usage → age → points → probabilistic revenue → NPV).

    python3 -m money.price "Victor Osimhen" --to Arsenal --fee 90 --wage 250000 \
            --age 25 --pos FW --mv 100 --contract 5
    python3 -m money.price "Alexander Isak" --to Arsenal --fee 70 --mv 75   # wage modelled

Programmatic: `price_transfer(player="...", to_team="Arsenal", fee_gbp=..., ...)`
returns a PriceVerdict (NPV central + band, per-year breakdown, component values,
and a list of quality flags naming every modelled / low-confidence input).

Run with no args: `python3 -m money.price` -> _check (synthetic, local reads only).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from money.npv import npv_transfer, npv_band, calibration, DISCOUNT
from impact.aging import POS_GROUP

LEAGUE = "ENG-Premier League"


@dataclass
class PriceVerdict:
    player: str
    to_team: str
    to_season: str
    npv_central: float
    npv_lo: float
    npv_hi: float
    breakdown: pd.DataFrame
    components: dict
    flags: list = field(default_factory=list)

    def __str__(self):
        m = lambda x: f"£{x/1e6:+.1f}m"
        c = self.components
        lines = [
            f"{self.player} → {self.to_team} {self.to_season}",
            f"  efficiency {c['efficiency']:.4f} (from {c['from_season']}), "
            f"usage_share {c['usage_share']:.3f}, bar {c['team_eff']:.4f}",
            f"  £{c['gbp_per_point']/1e6:.2f}m/point at {c['team_points']:.0f} pts; "
            f"fee £{c['fee_gbp']/1e6:.0f}m/{c['contract_years']}y; "
            f"wage £{c['wage_annual_gbp']/1e6:.1f}m ({c['wage_source']})",
            f"  NPV central {m(self.npv_central)}  band [{m(self.npv_lo)} … {m(self.npv_hi)}]",
        ]
        if self.flags:
            lines.append("  flags: " + "; ".join(self.flags))
        return "\n".join(lines)


_XWALK = None


def _tm_player_id(us_name: str):
    """Map an understat player name -> Transfermarkt player id via data/crosswalk/players.csv
    (exact us_name, else normalized contains). Returns int or None. Cached."""
    global _XWALK
    from ingest.crosswalk import norm_player
    if _XWALK is None:
        p = Path(__file__).resolve().parent.parent / "data" / "crosswalk" / "players.csv"
        _XWALK = pd.read_csv(p)[["us_name", "tm_player_id"]].dropna()
        _XWALK["_n"] = _XWALK.us_name.map(norm_player)
    hit = _XWALK[_XWALK.us_name == us_name]
    if hit.empty:
        hit = _XWALK[_XWALK._n == norm_player(us_name)]
    return int(hit.tm_player_id.iloc[0]) if not hit.empty else None


def _find_player(ue: pd.DataFrame, player: str, from_season: str | None):
    """Locate a player's efficiency + usage_share. Exact name, else normalized
    contains. Picks the requested season or the most-recent high-volume one; if he
    played for >1 team that season, take the row with the most actions."""
    from ingest.crosswalk import norm_player
    hit = ue[ue.player == player]
    if hit.empty:
        key = norm_player(player)
        hit = ue[ue.player.map(norm_player).str.contains(key, na=False)]
    if hit.empty:
        raise KeyError(f"player not found: {player!r}")
    hit = hit[hit.actions >= 20]
    if from_season:
        hit = hit[hit.season == from_season] if (hit.season == from_season).any() else hit
    season = hit.sort_values("season").season.iloc[-1]
    row = hit[hit.season == season].sort_values("actions").iloc[-1]
    return row, season


def price_transfer(*, player, fee_gbp, market_value_eur_m, age, position,
                   to_team="Arsenal", to_season=None, contract_years=5,
                   wage_annual_gbp=None, from_season=None, discount=DISCOUNT,
                   shots=None, ue=None, tteam=None, revmodel=None) -> PriceVerdict:
    """Full end-to-end pricing. Heavy engine objects can be passed in (shots, ue,
    tteam, revmodel) to price many players without rebuilding; otherwise built once."""
    from ingest.understat import read_shots
    from impact.usage import usage_efficiency
    from money.points import team_season_table
    from money.revenue import RevenueModel
    from ingest.wages import estimate_wage

    if shots is None:
        shots = read_shots()
    if ue is None:
        ue = usage_efficiency(shots)
    if tteam is None:
        tteam = team_season_table(shots)
    if revmodel is None:
        revmodel = RevenueModel(tteam)

    flags = []
    prow, fseason = _find_player(ue, player, from_season)

    # destination baseline: requested season, else the team's most recent COMPLETE
    # one (a partial season understates points/games and mis-prices the £/point).
    tt = tteam[(tteam.league == LEAGUE) & (tteam.team == to_team)]
    if tt.empty:
        raise KeyError(f"destination team-season not found: {to_team}")
    if to_season:
        season = to_season
    else:
        full = tt[tt.games >= 34]
        season = (full if not full.empty else tt).sort_values("season").season.iloc[-1]
    ars = tt[tt.season == season].iloc[0]
    if ars.games < 34:
        flags.append(f"{to_team} {season} is a partial season ({ars.games:.0f} games) — baseline noisy")
    team_eff = ue[(ue.league == LEAGUE) & (ue.team == to_team) & (ue.season == season)] \
        .pipe(lambda d: d.value.sum() / d.actions.sum())
    gbp_per_point = revmodel.marginal_value(ars.points) * 1e6

    # wage: modelled unless supplied. Bridge the understat player name -> tm_player_id via the
    # crosswalk so estimate_wage can prefer a REAL Capology/FIFA wage (grade B/C) over the
    # parametric prior. Without this the harvested wages never reach the valuation.
    if wage_annual_gbp is None:
        tid = _tm_player_id(prow.player)
        w = estimate_wage(age, LEAGUE, market_value_eur_m, position, tm_player_id=tid)
        wage_annual_gbp, wage_lo, wage_hi, wsource = w.annual_wage_gbp, w.lo, w.hi, w.source
        _grade = {"capology_estimate": "B (real, Capology)", "fifa_prior": "C (FIFA prior)"}.get(
            wsource, "D (parametric)")
        flags.append(f"wage {wsource} ±{round(100*(wage_hi/wage_annual_gbp-1))}% — grade {_grade}")
    else:
        wage_lo = wage_hi = wage_annual_gbp
        wsource = "given"

    cal = calibration()
    flags.append(f"benefit calibrated to Stage-4 channel r≈0.08 (slope {cal['slope']:.1f} "
                 f"[{cal['lo']:.1f},{cal['hi']:.1f}]) — wide by design")
    if position.upper()[:2] in ("GK",) or POS_GROUP.get(position, position) not in ("FW", "MF", "DF"):
        flags.append("no age curve for this position (GK) — decay held flat")
    if fseason != season:
        flags.append(f"efficiency from {fseason}; usage assumed to travel to {season}")
    if gbp_per_point < 0.5e6:
        flags.append("club near top of table — marginal point worth little (title/CL probability only)")

    common = dict(efficiency=prow.efficiency, usage_share=prow.usage_share, team_eff=team_eff,
                  gbp_per_point=gbp_per_point, age=age, position=position, fee_gbp=fee_gbp,
                  contract_years=contract_years, market_value_gbp=market_value_eur_m * 1e6 * 0.85,
                  discount=discount)
    npv, bd, resid = npv_transfer(cal_slope=cal["slope"], wage_annual_gbp=wage_annual_gbp, **common)
    pess, cen, opt = npv_band(wage_lo=wage_lo, wage_hi=wage_hi, cal_lo=cal["lo"], cal_hi=cal["hi"],
                              wage_annual_gbp=wage_annual_gbp, cal_slope=cal["slope"], **common)

    comp = dict(efficiency=prow.efficiency, usage_share=prow.usage_share, team_eff=team_eff,
                gbp_per_point=gbp_per_point, team_points=ars.points, fee_gbp=fee_gbp,
                contract_years=contract_years, wage_annual_gbp=wage_annual_gbp,
                wage_source=wsource, from_season=fseason, residual_pv=resid)
    return PriceVerdict(player, to_team, season, cen, pess, opt, bd, comp, flags)


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Price a transfer, end-to-end, for a club.")
    ap.add_argument("player")
    ap.add_argument("--to", default="Arsenal", dest="to_team")
    ap.add_argument("--season", default=None, dest="to_season")
    ap.add_argument("--fee", type=float, required=True, help="fee in £m")
    ap.add_argument("--wage", type=float, default=None, help="annual wage in £ (omit -> modelled)")
    ap.add_argument("--mv", type=float, required=True, help="market value in €m")
    ap.add_argument("--age", type=float, required=True)
    ap.add_argument("--pos", default="FW", dest="position")
    ap.add_argument("--contract", type=int, default=5, dest="contract_years")
    a = ap.parse_args()
    v = price_transfer(player=a.player, to_team=a.to_team, to_season=a.to_season,
                       fee_gbp=a.fee * 1e6, wage_annual_gbp=a.wage, market_value_eur_m=a.mv,
                       age=a.age, position=a.position, contract_years=a.contract_years)
    print(v)
    print(v.breakdown.assign(
        benefit=lambda d: (d.benefit/1e6).round(1), cost=lambda d: (d.cost/1e6).round(1),
        net_pv=lambda d: (d.net_pv/1e6).round(1))[["year", "age", "d_npxgd", "benefit", "cost", "net_pv"]]
        .to_string(index=False))


def _check():
    # offline: synthetic engine frames, exercise the full assembly path
    ue = pd.DataFrame([
        dict(league=LEAGUE, season="2023-2024", team="Foo", player="Test Striker",
             actions=200, value=32.0, usage_share=0.18, efficiency=0.16),
        # destination squad rows so the bar (team_eff) is real, not 0/0
        dict(league=LEAGUE, season="2023-2024", team="Arsenal", player="A",
             actions=150, value=15.0, usage_share=0.15, efficiency=0.10),
        dict(league=LEAGUE, season="2023-2024", team="Arsenal", player="B",
             actions=100, value=8.0, usage_share=0.10, efficiency=0.08)])
    tteam = pd.DataFrame([dict(league=LEAGUE, season="2023-2024", team="Arsenal",
                               points=70, games=38, npxgd_pg=0.5)])

    class FakeRev:
        def marginal_value(self, pts): return 2.0   # £2m/point
    v = price_transfer(player="Test Striker", fee_gbp=40e6, market_value_eur_m=50, age=25,
                       position="FW", to_team="Arsenal", to_season="2023-2024",
                       shots="x", ue=ue, tteam=tteam, revmodel=FakeRev())
    assert v.npv_lo <= v.npv_central <= v.npv_hi, (v.npv_lo, v.npv_central, v.npv_hi)
    assert v.components["wage_source"] == "modelled"
    assert any("calibrated" in f for f in v.flags)
    assert len(v.breakdown) == 5
    # fuzzy name match works
    v2 = price_transfer(player="test striker", fee_gbp=40e6, market_value_eur_m=50, age=25,
                        position="FW", to_season="2023-2024", shots="x", ue=ue, tteam=tteam,
                        revmodel=FakeRev())
    assert v2.player == "test striker" and v2.npv_central == v.npv_central
    print(f"assembled NPV {v.npv_central/1e6:+.1f}m band [{v.npv_lo/1e6:+.1f},{v.npv_hi/1e6:+.1f}], "
          f"{len(v.flags)} flags, fuzzy-match ok")
    print("ok")


if __name__ == "__main__":
    import sys
    _check() if len(sys.argv) == 1 else _cli()
