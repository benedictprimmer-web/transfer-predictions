"""Stage 7c — NPV of a transfer (the capstone). Composes every layer:

  cost      = amortised fee (fee / contract years) + annual wage      [Stage 6 + wages]
  benefit_t = CALIBRATED team-npxGD contribution, AGE-DECAYED         [Stage 5 + benefit gate]
              pg_t  = usage_share × (age-decayed efficiency − team_eff)   (validated form)
              npxGD_t = CAL_SLOPE × pg_t × 38                             (zero-sum-shrunk, honest units)
              -> points   (× points_slope, money.points)                 [Stage 7a]
              -> revenue  (× £/point at the club's table position)        [Stage 7b, probabilistic rank]
  NPV       = Σ_t (benefit_t − cost_t)/(1+r)^t  +  residual resale/(1+r)^N

The benefit uses the calibrated proxy (validate.benefit_gate): usage_share ×
(efficiency − team MEAN eff) is the form Stage 4 validated (the marginal/replacement
bars predict WORSE), and CAL_SLOPE (delta_team_xgd90 per unit pg, from the panel
regression) converts it to real team-npxGD, absorbing the zero-sum displacement
that raw `actions × eff-gap` overstated. The calibration's bootstrap CI is the
dominant NPV error bar — it carries the honest r≈0.08 uncertainty.

Units: efficiency & team_eff in npxG+xAG per action; usage_share in [0,1]; fee/wage
/MV in GBP. market_value passed to the wage layer is EUR-millions (its contract).

Run: `python3 -m money.npv`      -> _check (synthetic, local reads only)
     `python3 -m money.npv run`  -> real worked examples priced to Arsenal.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

from impact.aging import age_multiplier

POINTS_SLOPE = 0.721        # points per season-npxGD (money.points fit)
# Net discount on future football cashflows. NOT a raw time-value rate: future
# resale, wages and revenue are denominated in *inflated* future pounds, so the
# rate that matters is nominal_discount − football_growth.
#   nominal club discount r_nom ≈ 9%  (UK 10y gilt ~4.5% Jul-2026 + ~4.5% football risk premium)
#   football value growth   g     ≈ 5%  (MEASURED, not assumed: the hedonic fee index runs
#         5.3%/yr in the 2017–2022 regime and 6.3%/yr over 1996–2022 — see INFLATION_FINDINGS.md
#         and money.inflation. g rounded down to 5% for forward PSR/rate headwinds; was a 4% guess.)
#   => r_net ≈ 4%.  See MEMO_discounting.md. Sensitivity 3%/4%/5%/8% there.
# (Distinct from the Stage-4 calibration correlation r≈0.08 elsewhere in this file —
#  that coincidental clash of "0.08" is why this is now spelled out.)
DISCOUNT = 0.04
GAMES = 38
_CALIB = Path(__file__).resolve().parent.parent / "data" / "money" / "benefit_calibration.csv"


def calibration() -> dict:
    """Benefit calibration (slope + CI) from validate.benefit_gate; fallback to
    the recorded central fit if the file isn't built yet."""
    if _CALIB.exists():
        return pd.read_csv(_CALIB).iloc[0].to_dict()
    return dict(slope=9.25, lo=3.86, hi=14.25, intercept=-0.0122)


def _decay(age_now, age_then, position):
    return age_multiplier(age_then, position)[0] / age_multiplier(age_now, position)[0]


def npv_transfer(*, efficiency, usage_share, team_eff, gbp_per_point, age, position,
                 fee_gbp, wage_annual_gbp, contract_years, market_value_gbp,
                 cal_slope, points_slope=POINTS_SLOPE, discount=DISCOUNT):
    """Deterministic NPV for one deal. Returns (npv, breakdown, residual_pv).

    benefit_t = cal_slope × usage_share × (decayed_eff − team_eff) × GAMES
                × points_slope × gbp_per_point."""
    amort_fee = fee_gbp / contract_years
    rows = []
    for t in range(1, int(contract_years) + 1):
        age_mid = age + t - 0.5
        eff_t = efficiency * _decay(age, age_mid, position)
        pg = usage_share * (eff_t - team_eff)
        d_npxgd = cal_slope * pg * GAMES               # season team-npxGD contribution
        benefit = d_npxgd * points_slope * gbp_per_point
        cost = amort_fee + wage_annual_gbp
        disc = 1.0 / (1 + discount) ** t
        rows.append(dict(year=t, age=round(age_mid, 1), eff=round(eff_t, 4),
                         d_npxgd=round(d_npxgd, 2), benefit=benefit, cost=cost,
                         net_pv=(benefit - cost) * disc))
    bd = pd.DataFrame(rows)
    residual = market_value_gbp * _decay(age, age + contract_years, position)
    residual_pv = residual / (1 + discount) ** contract_years
    return bd.net_pv.sum() + residual_pv, bd, residual_pv


def npv_band(*, wage_lo, wage_hi, cal_lo, cal_hi, **kw):
    """(pessimistic, central, optimistic) NPV. Pessimistic pairs the low calibration
    slope with the high wage; optimistic the reverse — the two dominant uncertainties."""
    central = npv_transfer(cal_slope=kw.pop("cal_slope"),
                           wage_annual_gbp=kw.pop("wage_annual_gbp"), **kw)[0]
    pess = npv_transfer(cal_slope=cal_lo, wage_annual_gbp=wage_hi, **kw)[0]
    opt = npv_transfer(cal_slope=cal_hi, wage_annual_gbp=wage_lo, **kw)[0]
    return pess, central, opt


def _fmt(x):
    return f"£{x/1e6:+.1f}m"


def _price_example(shots, ue, tteam, revmodel, *, team, season, target_row,
                   age, position, mv_eur_m, fee_gbp, contract):
    from ingest.wages import estimate_wage
    LEAGUE = "ENG-Premier League"
    ars = tteam[(tteam.league == LEAGUE) & (tteam.team == team) & (tteam.season == season)].iloc[0]
    team_eff = ue[(ue.league == LEAGUE) & (ue.team == team) & (ue.season == season)] \
        .pipe(lambda d: d.value.sum() / d.actions.sum())
    gbp_per_point = revmodel.marginal_value(ars.points) * 1e6
    wage = estimate_wage(age, LEAGUE, mv_eur_m, position)
    cal = calibration()

    common = dict(efficiency=target_row.efficiency, usage_share=target_row.usage_share,
                  team_eff=team_eff, gbp_per_point=gbp_per_point, age=age, position=position,
                  fee_gbp=fee_gbp, contract_years=contract, market_value_gbp=mv_eur_m * 1e6 * 0.85)
    npv, bd, resid = npv_transfer(cal_slope=cal["slope"], wage_annual_gbp=wage.annual_wage_gbp, **common)
    pess, cen, opt = npv_band(wage_lo=wage.lo, wage_hi=wage.hi, cal_lo=cal["lo"], cal_hi=cal["hi"],
                              wage_annual_gbp=wage.annual_wage_gbp, cal_slope=cal["slope"], **common)

    print(f"\n{'='*70}\n{target_row.player} → {team} {season}")
    print(f"  {team}: {ars.points:.0f} pts, team_eff {team_eff:.4f}, "
          f"£{gbp_per_point/1e6:.2f}m/point (probabilistic rank)")
    print(f"  target: efficiency {target_row.efficiency:.4f}, usage_share {target_row.usage_share:.3f}")
    print(f"  deal: £{fee_gbp/1e6:.0f}m/{contract}y, wage £{wage.annual_wage_gbp/1e6:.1f}m "
          f"[{wage.lo/1e6:.1f}–{wage.hi/1e6:.1f}] ({wage.source}), MV €{mv_eur_m:.0f}m")
    print(bd.assign(benefit=bd.benefit.map(_fmt), cost=bd.cost.map(_fmt),
                    net_pv=bd.net_pv.map(_fmt))[["year", "age", "d_npxgd", "benefit", "cost", "net_pv"]]
          .to_string(index=False))
    print(f"  residual resale PV: {_fmt(resid)}")
    print(f"  NPV central: {_fmt(cen)}   band [{_fmt(pess)} … {_fmt(opt)}]  (calibration + wage)")
    return cen


def run():
    from ingest.understat import read_shots
    from impact.usage import usage_efficiency
    from money.points import team_season_table
    from money.revenue import RevenueModel

    shots = read_shots()
    ue = usage_efficiency(shots)
    tteam = team_season_table(shots)
    revmodel = RevenueModel(tteam)

    # a real target: highest-usage-weighted-efficiency cross-league forward, 2023-24
    fw = ue[(ue.season == "2023-2024") & (ue.actions >= 120) & (ue.league != "ENG-Premier League")]
    fw = fw.sort_values("efficiency", ascending=False)
    tgt = fw.iloc[0]

    print("Worked examples — NPV to Arsenal, calibrated benefit + probabilistic rank.")
    # (a) on the CL cliff (2021-22, 5th/69pts) — where a point is worth most
    _price_example(shots, ue, tteam, revmodel, team="Arsenal", season="2021-2022",
                   target_row=tgt, age=25, position="FW", mv_eur_m=60.0, fee_gbp=55e6, contract=5)
    # (b) already top of the table (2023-24, ~89pts) — the case that used to price at £0
    _price_example(shots, ue, tteam, revmodel, team="Arsenal", season="2023-2024",
                   target_row=tgt, age=25, position="FW", mv_eur_m=60.0, fee_gbp=55e6, contract=5)
    print("\ncaveat: benefit is calibrated to the Stage-4 channel (r≈0.08); the band is")
    print("wide by design. Treat NPV sign near zero as undetermined, not precise.")


def _check():
    common = dict(team_eff=0.08, gbp_per_point=2e6, contract_years=5,
                  market_value_gbp=40e6, cal_slope=9.25)
    # bargain: high eff, decent usage, cheap, prime age -> NPV > 0
    good, bd, resid = npv_transfer(efficiency=0.16, usage_share=0.18, age=24, position="FW",
                                   fee_gbp=30e6, wage_annual_gbp=6e6, **common)
    assert good > 0 and resid > 0, (good, resid)
    # dud: efficiency below the bar, old, overpaid -> NPV < 0
    bad, *_ = npv_transfer(efficiency=0.05, usage_share=0.15, age=33, position="FW",
                           fee_gbp=80e6, wage_annual_gbp=18e6, **common)
    assert bad < 0, bad
    # age decay: an old player's benefit falls across the contract
    _, bdo, _ = npv_transfer(efficiency=0.16, usage_share=0.18, age=32, position="FW",
                             fee_gbp=30e6, wage_annual_gbp=6e6, **common)
    assert bdo.benefit.iloc[-1] < bdo.benefit.iloc[0], "benefit must decay with age"
    # calibrated magnitude sane: a strong signing adds a few points, not a dozen
    assert 0 < bd.d_npxgd.iloc[0] < 12, bd.d_npxgd.iloc[0]
    # band ordering: pessimistic <= central <= optimistic
    pess, cen, opt = npv_band(wage_lo=4e6, wage_hi=9e6, cal_lo=3.86, cal_hi=14.25,
                              efficiency=0.16, usage_share=0.18, age=24, position="FW",
                              fee_gbp=30e6, wage_annual_gbp=6e6, team_eff=0.08,
                              gbp_per_point=2e6, contract_years=5, market_value_gbp=40e6,
                              cal_slope=9.25)
    assert pess <= cen <= opt, (pess, cen, opt)
    print(f"bargain {_fmt(good)}>0, dud {_fmt(bad)}<0, npxGD/yr1 {bd.d_npxgd.iloc[0]:.1f} (sane), "
          f"band {_fmt(pess)}..{_fmt(opt)}")
    print("ok")


if __name__ == "__main__":
    import sys
    run() if "run" in sys.argv[1:] else _check()
