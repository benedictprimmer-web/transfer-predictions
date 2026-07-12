"""Fee model: what should this transfer have cost, and what did it cost?

The only part of the whole system with real ground truth: the fee happened.
Predict log(fee) from what was knowable before the deal, and the residual is
the verdict. Positive = paid over the curve.

HONEST CAVEAT, read this before trusting a number:
Transfermarkt market value is crowd-sourced and is itself informed by fees.
So this model measures "above/below market consensus", not "above/below true
value". Consensus can be wrong for the whole market at once (see: 2017
onwards). Use the residual as a conversation starter, not a verdict.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import cross_val_predict

TM_DIR = Path(__file__).resolve().parent.parent / "data" / "transfermarkt"
CANONICAL = TM_DIR.parent / "merged" / "transfers_canonical.parquet"
SHIP_OUT = TM_DIR.parent / "money" / "fee_ranker.csv"
_WFR = "https://raw.githubusercontent.com/JaseZiv/worldfootballR_data/master/data/{}"

# HistGBR handles categoricals and NaNs natively.
# ponytail: no XGBoost, no Optuna. Defaults are within noise of a tuned model on
# ~15k rows and you can read the code. Tune only if CV error is actually the
# thing blocking you.
FEATURES = ["age", "market_value", "position", "from_league", "to_league", "season", "contract_years"]
CATS = [False, False, True, True, True, False, False]


def fit_residuals(df: pd.DataFrame) -> pd.DataFrame:
    """df needs FEATURES + `fee`. Returns df with predicted fee and residual."""
    d = df[df.fee > 0].dropna(subset=["fee", "market_value", "age"]).copy()
    for c in FEATURES:                       # a source may not carry every feature (e.g. contract_years)
        if c not in d.columns:
            d[c] = np.nan
    X = d[FEATURES].copy()
    for c, is_cat in zip(FEATURES, CATS):
        X[c] = X[c].astype("category") if is_cat else pd.to_numeric(X[c])
    y = np.log1p(d.fee)

    m = HistGradientBoostingRegressor(categorical_features=CATS, random_state=0)
    # out-of-fold, so a deal is never priced by a model that saw it
    d["fee_pred"] = np.expm1(cross_val_predict(m, X, y, cv=5))
    d["overpay"] = d.fee - d.fee_pred
    d["overpay_pct"] = d.overpay / d.fee_pred * 100
    # sort relative, not absolute: absolute € residual just ranks the big fees
    return d.sort_values("overpay_pct", ascending=False)


def load_transfermarkt(path: str) -> pd.DataFrame:
    """Kaggle `davidcariboo/player-scores`. Unzip, point at the folder.

        kaggle datasets download -d davidcariboo/player-scores --unzip -p data/
    """
    t = pd.read_csv(f"{path}/transfers.csv", parse_dates=["transfer_date"])
    p = pd.read_csv(f"{path}/players.csv", parse_dates=["date_of_birth"])
    d = t.merge(p[["player_id", "date_of_birth", "position"]], on="player_id", how="left")
    d["age"] = (d.transfer_date - d.date_of_birth).dt.days / 365.25
    d["season"] = d.transfer_date.dt.year
    return d.rename(columns={
        "transfer_fee": "fee",
        "market_value_in_eur": "market_value",
        "from_club_name": "from_league",   # club is a finer proxy than league; TM
        "to_club_name": "to_league",       # has no league col on transfers.csv
    })


def _rds(name: str, sub: str) -> pd.DataFrame:
    """Download (once) + read a worldfootballR .rds into a DataFrame."""
    import rdata
    dest = TM_DIR / name
    if not dest.exists():
        import urllib.request
        TM_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_WFR.format(f"{sub}/{name}"), dest)
    return rdata.read_rds(str(dest), default_encoding="latin-1",
                          force_default_encoding=True)


def load_big5_transfers() -> pd.DataFrame:
    """Big-5 transfers with fees + pre-move market value -> the FEATURES frame.

    The R2 `transfers` table is thin (35k rows, no Haaland/Antony). worldfootballR's
    big_5_transfers.rds is the real Big-5 fee history. Its companion big5_player_vals
    only lists start-of-season Big-5 squads, so it can't price mid-window arrivals or
    non-Big-5 origins (Antony from Ajax) — instead we join the full, dated R2
    player_valuations as-of just before the window: the value *knowable before the
    deal*, which is exactly what the fee model should regress on.
    ponytail: league-level from/to (not club) — low-cardinality categoricals are
    steadier at this sample size; market_value + age carry the signal anyway.
    """
    from ingest.transfermarkt import _read, download
    from ingest.understat import _fix_mojibake  # latin-1 .rds -> proper accents
    t = _rds("big_5_transfers.rds", "tm_transfers")
    is_loan = t.is_loan.astype(str).str.lower().eq("true")
    t = t[(t.transfer_type == "Arrivals") & ~is_loan].copy()  # dest side; no loans
    t["season"] = pd.to_numeric(t.season, errors="coerce")
    t["pid"] = t.player_url.astype(str).str.extract(r"spieler/(\d+)")[0]
    # window date proxy: summer -> Jul 15 of season, winter -> Jan 15 of season+1
    yr = t.season.astype("Int64").astype(str)
    winter = t.window.astype(str).str.lower().str.contains("winter")
    t["tdate"] = pd.to_datetime(np.where(winter, (t.season + 1).astype("Int64").astype(str)
                                         + "-01-15", yr + "-07-15"), errors="coerce")

    download(("player_valuations",))
    v = _read("player_valuations", usecols=["player_id", "date", "market_value_in_eur"])
    v = v.assign(pid=v.player_id.astype(str),
                 date=pd.to_datetime(v.date, errors="coerce"),
                 mv=pd.to_numeric(v.market_value_in_eur, errors="coerce"))
    v = v.dropna(subset=["date"]).sort_values("date")[["pid", "date", "mv"]]
    t = pd.merge_asof(t.dropna(subset=["tdate"]).sort_values("tdate"), v,
                      left_on="tdate", right_on="date", by="pid", direction="backward")

    return pd.DataFrame({
        "age": pd.to_numeric(t.player_age, errors="coerce"),
        "market_value": t.mv,
        "position": t.player_position.astype(str),
        "from_league": t.league_2.astype(str),   # origin league
        "to_league": t.league.astype(str),        # destination league
        "season": t.season,
        "fee": pd.to_numeric(t.transfer_fee, errors="coerce"),
        "player": t.player_name.astype(str).map(_fix_mojibake),
        "to_club": t.team_name.astype(str).map(_fix_mojibake),  # for locating gate players
        "from_club": t.club_2.astype(str).map(_fix_mojibake),
    })


def load_canonical(path=CANONICAL) -> pd.DataFrame:
    """The merged canonical table (ingest.merge) -> the FEATURES frame.

    Wider than big_5_transfers.rds: real from/to league names, age, pos, and a
    point-in-time market value on ~78% of id'd rows (as-of the pre-window date),
    with suspect mega-fees already flagged out. `mv_point_in_time`/`date_source`
    ride along so the shipped board can show which inputs are gold vs proxied.
    """
    d = pd.read_parquet(path)
    d = d[(d.fee_eur > 0) & ~d.fee_suspect.fillna(False)].copy()
    return pd.DataFrame({
        "age": pd.to_numeric(d.player_age, errors="coerce"),
        "market_value": pd.to_numeric(d.market_value_eur, errors="coerce"),
        "position": d.pos_group.astype(str),
        "from_league": d.from_league.fillna("Other").astype(str),
        "to_league": d.to_league.fillna("Other").astype(str),
        "season": pd.to_numeric(d.season, errors="coerce"),
        "contract_years": pd.to_numeric(d.get("contract_years_remaining"), errors="coerce"),
        "fee": pd.to_numeric(d.fee_eur, errors="coerce"),
        "player": d.player_name.astype(str),
        "to_club": d.to_club_name.astype(str),
        "from_club": d.from_club_name.astype(str),
        "mv_point_in_time": d.mv_is_point_in_time.fillna(False),
        "date_source": d.date_source.astype(str),
    })


def _gate(r: pd.DataFrame) -> None:
    """Two known deals must read the right way, or the ranker isn't trustworthy."""
    def find(player, club):
        m = r[r.player.str.contains(player, case=False, na=False)
              & r.to_club.str.contains(club, case=False, na=False)]
        return m.iloc[0] if len(m) else None
    haa, ant = find("Haaland", "Manchester City"), find("Antony", "Manchester United")
    print("\n=== GATE (Haaland underpay, Antony overpay) ===")
    for label, row in [("Haaland -> Man City (want <0)", haa),
                       ("Antony  -> Man Utd  (want >0)", ant)]:
        print(f"  {label}: " + ("NOT FOUND" if row is None else
              f"fee €{row.fee/1e6:.0f}m  pred €{row.fee_pred/1e6:.0f}m  overpay {row.overpay_pct:+.0f}%"))
    assert haa is not None and ant is not None, "gate players missing from canonical"
    assert haa.overpay_pct < 0, "Haaland should read underpay"
    assert ant.overpay_pct > 0, "Antony should read overpay"


def _ship_frame(path=CANONICAL) -> pd.DataFrame:
    """Union the two fee sources, deduped, best-informed row per deal.

    canonical  -> breadth + point-in-time MV + real league names (1992–2026), but
                  inherits Estate B's ~32k null player_ids (marquee like Antony lose MV).
    big5 rds   -> proper player-url keys, so it carries the marquee + MV that Estate B
                  dropped (Big-5, 2010–2022).
    Keep one row per (player, season, to_club); prefer whichever actually has a
    market value, then prefer canonical (point-in-time over proxy).
    """
    from ingest.crosswalk import norm_player
    a = load_canonical(path).assign(pri=0)
    frames = [a]
    try:
        b = load_big5_transfers()
        b = b.assign(mv_point_in_time=False, date_source="proxy", pri=1)
        frames.append(b[[c for c in a.columns if c in b.columns]])
    except Exception as e:   # offline / missing rds -> canonical only, softer gate
        print(f"  (big5 rds unavailable: {e} -> shipping canonical-only)")
    df = pd.concat(frames, ignore_index=True)
    df["k"] = (df.player.map(norm_player) + "|" + df.season.astype("Int64").astype(str)
               + "|" + df.to_club.map(_norm_club_name))
    df["has_mv"] = df.market_value.notna()
    return (df.sort_values(["has_mv", "pri"], ascending=[False, True])
              .drop_duplicates("k").drop(columns=["k", "pri", "has_mv"]))


def _norm_club_name(s) -> str:
    from ingest.merge import _norm_club
    return _norm_club(s)


def ship(path=CANONICAL, out=SHIP_OUT) -> pd.DataFrame:
    """SHIP: fit the fee ranker on the merged sources, gate it, write the board.

    Output CSV (`data/money/fee_ranker.csv`) is the deliverable: one row per
    disclosed, non-suspect deal with the modelled fair fee and the over/under-pay
    verdict, sorted most-overpaid first. Impact/NPV is deliberately NOT here — that
    lives in money.price as a wide-error sanity check, not a headline number.
    """
    df = _ship_frame(path)
    ready = df.dropna(subset=["fee", "market_value", "age"])
    print(f"union fee>0 (clean): {len(df):,} | model-ready (fee+mv+age): {len(ready):,}")
    r = fit_residuals(df)
    _gate(r)

    # data-quality guard: a fee >=€10m at >15x its market value is a decimal/data
    # error (Malomo €50m to AC Prato), not a real overpay. Real overpays top out
    # near 3x (Antony ~2.4x). Flag, don't drop -> stays in the CSV, out of the ranking.
    r["fee_vs_mv_implausible"] = (r.fee >= 10e6) & (r.fee > 15 * r.market_value)
    n_flag = int(r.fee_vs_mv_implausible.sum())

    clean = r[~r.fee_vs_mv_implausible]
    lf, lp = np.log1p(r.fee), np.log1p(r.fee_pred)
    r2 = 1 - ((lf - lp) ** 2).sum() / ((lf - lf.mean()) ** 2).sum()
    rho = r[["fee", "fee_pred"]].rank().corr().iloc[0, 1]
    rho_c = clean[["fee", "fee_pred"]].rank().corr().iloc[0, 1]
    big5 = clean[clean.to_league.isin(["Premier League", "LaLiga", "La Liga",
                                       "Serie A", "Ligue 1", "Bundesliga"])]
    rho_b5 = big5[["fee", "fee_pred"]].rank().corr().iloc[0, 1]
    print(f"\nOOF log-R2={r2:.3f}  spearman(fee,pred): all={rho:.3f}  "
          f"plausible={rho_c:.3f}  Big5-core={rho_b5:.3f}  (n={len(r):,})")
    print(f"flagged {n_flag} fee-vs-MV-implausible rows (kept in CSV, out of ranking)")

    board = r.assign(
        fee_eur=r.fee.round(0), fee_pred_eur=r.fee_pred.round(0),
        overpay_pct=r.overpay_pct.round(0),
    )[["player", "season", "to_club", "from_club", "from_league", "to_league",
       "age", "market_value", "fee_eur", "fee_pred_eur", "overpay_pct",
       "mv_point_in_time", "date_source", "fee_vs_mv_implausible"]]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(out, index=False)
    print(f"\nwrote {len(board):,} ranked deals -> {out}")

    # headline lists: established players only (fee & MV >= €10m). Below that, MV lag
    # (a breakout buy's prior consensus value is low) makes overpay_pct explode into
    # noise — the documented crowd-sourced-MV caveat. Full board + all deals are in the CSV.
    big = board[(board.fee_eur >= 10e6) & (board.market_value >= 10e6)
                & ~board.fee_vs_mv_implausible]
    show = ["player", "to_club", "season", "fee_eur", "fee_pred_eur", "overpay_pct"]
    fmt = lambda x: x.assign(fee_eur=(x.fee_eur/1e6).round(0),
                             fee_pred_eur=(x.fee_pred_eur/1e6).round(0))[show]
    print(f"\n=== biggest overpays (fee & MV >= €10m, plausible, n={len(big):,}) ===\n"
          + fmt(big.head(10)).to_string(index=False))
    print("\n=== biggest bargains (fee >= €10m) ===\n"
          + fmt(big.tail(10)).to_string(index=False))
    print("\nSHIPPED — fee ranker board written; impact score stays a sanity check (money.price).")
    return board


def price_transfers() -> pd.DataFrame:
    """Stage-7/8 seam: one row per disclosed Big-5 arrival with the fee model applied.

    THE public interface — npv.py should call only this, not the internals.
    Columns (stable contract):
      player, season (int start-year), to_club, from_club, position   -- keys/ctx
      to_league, from_league          -- TM league names ("Premier League", ...)
      age, market_value               -- pre-deal, EUR
      fee                             -- actual paid, EUR (>0; undisclosed dropped)
      fee_pred                        -- modelled fair fee, EUR (out-of-fold)
      overpay, overpay_pct            -- fee - fee_pred; +ve = paid over the curve
    Sorted by overpay_pct desc. NOTE: keys are Transfermarkt spellings — to join the
    benefit side (Understat/panel: "ENG-Premier League", Understat club names) you
    must name-align player + club/league, same gap validate/ronaldo.py bridges.
    """
    return fit_residuals(load_big5_transfers())


def validate():
    """Real-data diagnostics — is fee_pred trustworthy, or did we just pass 2 deals?

    Reports OOF error, rank correlation, and calibration by predicted-fee decile.
    Informational (the gate lives in build()); run when touching the model.
    """
    r = price_transfers()
    lf, lp = np.log1p(r.fee), np.log1p(r.fee_pred)
    mae = np.abs(lf - lp).median()
    r2 = 1 - ((lf - lp) ** 2).sum() / ((lf - lf.mean()) ** 2).sum()
    rho = r[["fee", "fee_pred"]].rank().corr().iloc[0, 1]   # Spearman, no scipy dep
    print(f"n={len(r):,}  OOF median|log-err|={mae:.3f}  log-R2={r2:.3f}  "
          f"spearman(fee,pred)={rho:.3f}")
    cal = (r.assign(dec=pd.qcut(r.fee_pred, 10, labels=False, duplicates="drop"))
             .groupby("dec").agg(pred_m=("fee_pred", "mean"),
                                 actual_m=("fee", "mean"), n=("fee", "size")))
    cal[["pred_m", "actual_m"]] = (cal[["pred_m", "actual_m"]] / 1e6).round(1)
    cal["actual/pred"] = (cal.actual_m / cal.pred_m).round(2)
    print("calibration by predicted-fee decile (EUR m):")
    print(cal.to_string())
    # retransform bias: back-transformed log-model underpredicts on the raw scale,
    # worst for small fees. Trust fee_pred *levels* for >=€10m (<=12% low); below
    # that use overpay *rank*, not the level.
    return r


def build():
    """Fit on real Big-5 fees; the gate is two known deals reading the right way."""
    df = load_big5_transfers()
    ready = (df.fee > 0) & df.market_value.notna() & df.age.notna()
    print(f"{len(df):,} arrivals | {int((df.fee>0).sum()):,} with fee | "
          f"{int(ready.sum()):,} model-ready (fee & market_value & age)")

    r = fit_residuals(df)

    def find(player, club, season=2022):
        m = r[r.player.str.contains(player, case=False, na=False)
              & r.to_club.str.contains(club, case=False, na=False)
              & (r.season == season)]
        return m.iloc[0] if len(m) else None

    haa, ant = find("Haaland", "Manchester City"), find("Antony", "Manchester United")
    print("\n=== GATE (Haaland underpay, Antony overpay) ===")
    for label, row in [("Haaland -> Man City (want <0)", haa),
                       ("Antony  -> Man Utd  (want >0)", ant)]:
        print(f"  {label}: " + ("NOT FOUND" if row is None else
              f"fee €{row.fee/1e6:.0f}m  pred €{row.fee_pred/1e6:.0f}m  "
              f"overpay {row.overpay_pct:+.0f}%"))
    assert haa is not None and ant is not None, "gate players missing"
    assert haa.overpay_pct < 0, "Haaland should read underpay"
    assert ant.overpay_pct > 0, "Antony should read overpay"

    # headline lists: floor at €10m fee — below that, fee_pred~0 makes overpay_pct
    # explode into noise (a €1m fee predicted €0.1m reads "+900%"). Model unchanged.
    show = ["player", "to_club", "season", "fee", "fee_pred", "overpay_pct"]
    big = r[r.fee >= 10e6]
    fmt = lambda x: x.assign(fee=(x.fee / 1e6).round(0),
                             fee_pred=(x.fee_pred / 1e6).round(0),
                             overpay_pct=x.overpay_pct.round(0))[show]
    print(f"\n=== biggest overpays (fee >= €10m, n={len(big):,}) ===\n"
          + fmt(big.head(10)).to_string(index=False))
    print("\n=== biggest bargains (fee >= €10m) ===\n"
          + fmt(big.tail(10)).to_string(index=False))
    print("\nGATE PASSED")
    return r


def _check():
    rng = np.random.default_rng(0)
    n = 800
    mv = rng.lognormal(16, 1, n)
    age = rng.uniform(17, 34, n)
    # truth: fee tracks market value, discounted with age
    fee = mv * (1.6 - 0.02 * age) * rng.lognormal(0, 0.15, n)
    d = pd.DataFrame(dict(
        fee=fee, market_value=mv, age=age,
        position=rng.choice(["FW", "MF", "DF"], n),
        from_league=rng.choice(["a", "b"], n), to_league=rng.choice(["a", "b"], n),
        season=rng.integers(2015, 2025, n),
    ))
    # plant one obvious mug: 4x the going rate
    d.loc[0, "fee"] = d.loc[0, "fee"] * 4

    r = fit_residuals(d)
    assert r.index[0] == 0, "the planted overpay should rank first"
    err = np.abs(np.log1p(r.fee) - np.log1p(r.fee_pred)).median()
    assert err < 0.20, f"median log error {err:.3f} too high"
    print(f"median log fee error {err:.3f}; top overpay = row {r.index[0]} "
          f"({r.iloc[0].overpay_pct:.0f}% over)")
    print("ok")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if "ship" in args:
        ship()
    elif "build" in args:
        build()
    elif "validate" in args:
        validate()
    else:
        _check()
