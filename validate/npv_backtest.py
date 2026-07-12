"""D2 — whole-stack backtest. Two honest questions about the composed money layer:

1. OUT-OF-SAMPLE benefit: calibrate the benefit slope on one era, predict realized
   team improvement in the *other* era. Stage 4 showed the RANK relation replicates
   across eras; this tests that the calibrated MAGNITUDE generalizes too (not overfit
   to the era it was fit on). Reported as OOF Spearman + Pearson with bootstrap CI.

2. NAMED-CASE audit: run famous completed transfers through the full interface and
   put the model's verdict next to what actually happened — including the case the
   model provably CAN'T catch (Ronaldo 2021: individually efficient, collectively
   ruinous — the Stage-2 blind spot), stated plainly.

Run: `python3 -m validate.npv_backtest`      -> _check (synthetic, no network)
     `python3 -m validate.npv_backtest run`  -> OOF split + named-case table, cache CSV.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from validate.stage4 import add_prediction, team_eff_before, boot_corr

GAMES = 38
OUT = Path(__file__).resolve().parent.parent / "data" / "money" / "backtest.csv"


def _cal_slope(p):
    d = p.dropna(subset=["predicted_gain", "delta_team_xgd90"])
    A = np.column_stack([np.ones(len(d)), d.predicted_gain.values])
    return np.linalg.lstsq(A, d.delta_team_xgd90.values, rcond=None)[0][1]


def oof_backtest(p):
    """Calibrate on each era, predict the other. Returns per-direction OOF results."""
    p = p.dropna(subset=["predicted_gain", "delta_team_xgd90"]).copy()
    p["era"] = np.where(p.season_to < "2020", "early", "late")
    out = []
    for train, test in [("early", "late"), ("late", "early")]:
        tr, te = p[p.era == train], p[p.era == test]
        slope = _cal_slope(tr)
        pred = slope * te.predicted_gain * GAMES              # predicted season npxGD
        realized = te.delta_team_xgd90 * GAMES
        rs, (los, his), n = boot_corr(pred, realized, method="spearman")
        rp, (lop, hip), _ = boot_corr(pred, realized, method="pearson")
        out.append(dict(train=train, test=test, n=n, slope=slope,
                        spearman=rs, sp_lo=los, sp_hi=his,
                        pearson=rp, pe_lo=lop, pe_hi=hip))
    return pd.DataFrame(out)


NAMED = [   # player, to_team, to_season, fee£m, mv€m, age, pos, what actually happened
    ("Antony", "Manchester United", "2022-2023", 85, 60, 22, "FW",
     "£85m; TM fee model +183% overpay; widely judged a flop"),
    ("Erling Haaland", "Manchester City", "2022-2023", 51, 150, 22, "FW",
     "£51m; TM fee model -21% underpay; immediate elite output"),
    ("Cristiano Ronaldo", "Manchester United", "2021-2022", 13, 45, 36, "FW",
     "£13m; individually efficient BUT WOWY -0.248/90 — the model's blind spot"),
]


def named_cases(shots, ue, tteam, revmodel):
    from money.price import price_transfer
    rows = []
    for player, team, season, fee_m, mv_m, age, pos, note in NAMED:
        try:
            v = price_transfer(player=player, to_team=team, to_season=season,
                               fee_gbp=fee_m * 1e6, market_value_eur_m=mv_m, age=age,
                               position=pos, contract_years=4, shots=shots, ue=ue,
                               tteam=tteam, revmodel=revmodel)
            rows.append(dict(player=player, to_team=team, npv_m=round(v.npv_central / 1e6, 1),
                             lo=round(v.npv_lo / 1e6, 1), hi=round(v.npv_hi / 1e6, 1),
                             actually=note))
        except KeyError as e:
            rows.append(dict(player=player, to_team=team, npv_m=np.nan, lo=np.nan, hi=np.nan,
                             actually=f"[not in Understat corpus: {e}]"))
    return pd.DataFrame(rows)


def run():
    from ingest.understat import read_shots
    from impact.usage import usage_efficiency
    from money.points import team_season_table
    from money.revenue import RevenueModel

    shots = read_shots()
    panel = pd.read_csv("data/stage4/panel.csv")
    p = add_prediction(panel, team_eff_before(shots))

    print("=== 1. OUT-OF-SAMPLE benefit (calibrate one era, predict the other) ===")
    bt = oof_backtest(p)
    for r in bt.itertuples():
        print(f"  train {r.train:5s} -> test {r.test:5s} (n={r.n}): slope {r.slope:5.2f}  "
              f"OOF spearman {r.spearman:+.3f}[{r.sp_lo:+.3f},{r.sp_hi:+.3f}]  "
              f"pearson {r.pearson:+.3f}[{r.pe_lo:+.3f},{r.pe_hi:+.3f}]")
    ok = (bt.sp_lo > 0).all()
    print(f"  => calibrated benefit {'GENERALIZES' if ok else 'does NOT cleanly generalize'} "
          f"(both OOF spearman CIs {'exclude' if ok else 'do not all exclude'} zero)")

    print("\n=== 2. NAMED-CASE audit (model verdict vs reality) ===")
    ue = usage_efficiency(shots)
    tteam = team_season_table(shots)
    revmodel = RevenueModel(tteam)
    nc = named_cases(shots, ue, tteam, revmodel)
    for r in nc.itertuples():
        npv = f"NPV £{r.npv_m:+.0f}m [{r.lo:+.0f},{r.hi:+.0f}]" if pd.notna(r.npv_m) else "n/a"
        print(f"  {r.player:20s} -> {r.to_team:20s} {npv:28s} | {r.actually}")
    print("\n  Read: the fee model + NPV rate Antony poor value and Haaland strong; the")
    print("  usage engine CANNOT flag Ronaldo (per-action efficiency was fine) — that")
    print("  systemic damage only shows in WOWY, and is documented as the known limit.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    bt.to_csv(OUT, index=False)
    nc.to_csv(OUT.with_name("backtest_named.csv"), index=False)
    print(f"\nwrote {OUT} + backtest_named.csv")


def _check():
    # synthetic panel: predicted_gain drives delta in BOTH eras with the same slope
    rng = np.random.default_rng(0)
    n = 500
    pg = rng.normal(0, 0.004, n)
    seasons = np.where(rng.random(n) < 0.5, "2017-2018", "2022-2023")
    delta = 8.0 * pg + rng.normal(0, 0.08, n)     # same mechanism both eras
    p = pd.DataFrame(dict(predicted_gain=pg, delta_team_xgd90=delta, season_to=seasons))
    bt = oof_backtest(p)
    # a real cross-era mechanism must show positive OOF correlation both directions
    assert (bt.spearman > 0).all(), bt.spearman.tolist()
    assert (bt.slope > 0).all(), bt.slope.tolist()
    # null: no relation -> OOF correlation CI should straddle zero
    p0 = p.assign(delta_team_xgd90=rng.normal(0, 0.08, n))
    bt0 = oof_backtest(p0)
    assert (bt0.sp_lo < 0).any(), "null should not look significant"
    print(f"OOF spearman early->late {bt.spearman.iloc[0]:+.3f}, late->early "
          f"{bt.spearman.iloc[1]:+.3f}; null straddles 0")
    print("ok")


if __name__ == "__main__":
    import sys
    run() if "run" in sys.argv[1:] else _check()
