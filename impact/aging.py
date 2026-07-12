"""Age curves — within-player output change by age, per position (MODELS.md §3).

The rule: compare a player to himself a year later, never one player to another.
Across-player age contrasts measure who survived, not how players age. So every
fit here is a **player fixed effect** — each player's own seasons are demeaned
before age enters, minutes-weighted so a 34-90s starter counts more than an
8-90s fringe player.

Output metric: value_p90 = (npxG + xAG) per 90, from impact.usage aggregated to
player-league-season and divided by Transfermarkt minutes. Secondarily
`efficiency` (value per terminal action). Both are *attacking* output — a
defender's value lives mostly off this axis, so DF/MF curves describe how a
player's attacking contribution ages, not his total worth. Read the DF/MF peaks
with that caveat; the FW curve is the one that maps cleanly to intuition.

Fit: minutes-weighted player-FE quadratic of output on (age, age^2). The
population level curve L(age) = mean_output + b1*(age-agebar) + b2*(age^2-...)
gives a peak at argmax and a relative multiplier L(age)/L(peak) (peak=1.0).
A quadratic is symmetric-decline — enough to place the peak and rank decline
speed by curvature |b2|, not enough to model a slow rise / fast fall. Simple
beats clever (MODELS.md); revisit with a spline only if the residuals demand it.

Run: `python3 -m impact.aging`  -> _check (synthetic, no network)
     `python3 -m impact.aging build` -> real fit, prints peaks + caches curve.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "data" / "aging"
CURVES = CACHE / "curves.csv"

AGES = np.arange(17.0, 38.01, 0.5)          # curve support
POS_GROUP = {"Attack": "FW", "Midfield": "MF", "Defender": "DF"}  # TM -> coarse
GROUPS = ["FW", "MF", "DF"]
MIN_90S = 8.0                                # a real season; thinner is noise


# ------------------------------------------------------------------ the fit

def _fit_arrays(y, a, w, g, k):
    """Minutes-weighted player-FE quadratic on arrays.

    y,a,w: output, age, weight per row. g: cluster label 0..k-1 (the player).
    Demean y, age, age^2 within cluster (weighted) so player levels drop out,
    then WLS the residuals on (age, age^2). Returns (b1, b2, M, agebar, age2bar)
    — enough to rebuild the population level curve.
    """
    a2 = a * a

    def wdemean(x):
        num = np.bincount(g, x * w, k)
        den = np.bincount(g, w, k)
        return x - (num / den)[g]

    sw = np.sqrt(w)
    X = np.column_stack([wdemean(a) * sw, wdemean(a2) * sw])
    b, *_ = np.linalg.lstsq(X, wdemean(y) * sw, rcond=None)
    return (b[0], b[1],
            np.average(y, weights=w),
            np.average(a, weights=w),
            np.average(a2, weights=w))


def _level(coef, ages=AGES):
    """Population output level at each age (per-position average player)."""
    b1, b2, M, am, a2m = coef
    return M + b1 * (ages - am) + b2 * (ages ** 2 - a2m)


def _multipliers(coef, ages=AGES):
    """Relative multiplier vs peak (peak=1.0) and the peak age."""
    L = _level(coef, ages)
    return np.clip(L / L.max(), 0.0, None), float(ages[np.argmax(L)])


def fit_curve(d: pd.DataFrame, metric: str = "value_p90"):
    """Fit one position group. d needs: player, age, n90s, <metric>."""
    d = d.dropna(subset=[metric, "age", "n90s"])
    g, _ = pd.factorize(d.player)
    return _fit_arrays(d[metric].to_numpy(float), d.age.to_numpy(float),
                       d.n90s.to_numpy(float), g, g.max() + 1)


def bootstrap(d: pd.DataFrame, metric: str = "value_p90",
              n_boot: int = 400, seed: int = 0):
    """Cluster bootstrap over players. Returns (lo, hi) multiplier bands over
    AGES and the peak-age (2.5, 50, 97.5) percentiles.

    Each draw relabels the sampled players as fresh clusters, so a player drawn
    twice is two independent clusters — the correct cluster bootstrap, not a
    reweighting.
    """
    d = d.dropna(subset=[metric, "age", "n90s"])
    y, a, w = (d[metric].to_numpy(float), d.age.to_numpy(float),
               d.n90s.to_numpy(float))
    rows = list(d.groupby("player").indices.values())   # per-player row indices
    sizes = np.array([len(r) for r in rows])
    rng = np.random.default_rng(seed)

    mults, peaks = [], []
    for _ in range(n_boot):
        pick = rng.integers(0, len(rows), len(rows))
        ix = np.concatenate([rows[i] for i in pick])
        lab = np.repeat(np.arange(len(pick)), sizes[pick])
        coef = _fit_arrays(y[ix], a[ix], w[ix], lab, len(pick))
        mu, pk = _multipliers(coef)
        mults.append(mu)
        peaks.append(pk)
    lo, hi = np.percentile(mults, [2.5, 97.5], axis=0)
    return lo, hi, np.percentile(peaks, [2.5, 50, 97.5])


# ------------------------------------------------------------- real data pull

def player_seasons() -> pd.DataFrame:
    """Assemble player-league-season output + age + position group (network).

    Understat attacking output -> Transfermarkt for birthdate/position (unique
    normalized-name join) and minutes (player_id join, exact). One row per
    player-league-season; value_p90 = value / n90s.
    """
    from impact.usage import usage_efficiency
    from ingest.understat import read_shots
    from ingest.transfermarkt import BIG5, _read, download
    from ingest.crosswalk import norm_player

    u = usage_efficiency(read_shots())
    ps = u.groupby(["player", "league", "season"], as_index=False).agg(
        actions=("actions", "sum"), value=("value", "sum"))
    ps["efficiency"] = ps.value / ps.actions
    ps["key"] = ps.player.map(norm_player)

    download(("players", "appearances"))
    pl = _read("players", usecols=["player_id", "name", "date_of_birth", "position"])
    pl["key"] = pl.name.map(norm_player)
    # drop normalized names shared by >1 player — an ambiguous join is a wrong join
    solo = pl.groupby("key").player_id.nunique().loc[lambda s: s == 1].index
    pl = pl[pl.key.isin(solo)].drop_duplicates("key")
    m = ps.merge(pl[["key", "player_id", "date_of_birth", "position"]],
                 on="key", how="left")

    ap = _read("appearances", usecols=["player_id", "competition_id",
                                       "minutes_played", "date"])
    ap = ap[ap.competition_id.isin(BIG5)].copy()
    dt = pd.to_datetime(ap.date, errors="coerce")
    ap = ap[dt.notna()]
    dt = dt[dt.notna()]
    start = np.where(dt.dt.month >= 7, dt.dt.year, dt.dt.year - 1)  # Aug-May season
    ap["league"] = ap.competition_id.map(BIG5)
    ap["season"] = [f"{y}-{y + 1}" for y in start]
    mins = ap.groupby(["player_id", "league", "season"],
                      as_index=False).minutes_played.sum()
    mins["n90s"] = mins.minutes_played / 90.0
    m = m.merge(mins, on=["player_id", "league", "season"], how="left")

    yr = m.season.str[:4].astype(int)
    dob = pd.to_datetime(m.date_of_birth, errors="coerce")
    mid = pd.to_datetime(dict(year=yr + 1, month=1, day=1))   # season midpoint
    m["age"] = (mid - dob).dt.days / 365.25
    m["position_group"] = m.position.map(POS_GROUP)
    m["value_p90"] = m.value / m.n90s
    return m


# ---------------------------------------------------------------- public API

_CURVES = None


def age_multiplier(age: float, position: str):
    """(mult, lo, hi) at `age` for `position` (TM label or FW/MF/DF), from the
    cached curve. For downstream NPV decay. Age clipped to the fitted 17-38."""
    global _CURVES
    if _CURVES is None:
        _CURVES = pd.read_csv(CURVES)
    pos = POS_GROUP.get(position, position)
    c = _CURVES[_CURVES.position == pos].sort_values("age")
    if c.empty:
        raise KeyError(position)
    x = np.clip(age, AGES[0], AGES[-1])
    return tuple(float(np.interp(x, c.age, c[k])) for k in ("mult", "lo", "hi"))


def build(n_boot: int = 400):
    df = player_seasons()
    total = len(df)
    matched = df.position_group.notna() & df.age.notna()
    fit_rows = df[matched & (df.n90s >= MIN_90S)].dropna(
        subset=["value_p90", "age", "n90s"])

    print(f"player-seasons: {total:,}  "
          f"age+position matched: {matched.sum():,} "
          f"({100 * matched.mean():.1f}%)  "
          f"in fit (n90s>={MIN_90S:g}): {len(fit_rows):,}")

    rows = []
    print("\nposition  n     peak  peak95CI      21    25    27    29    33    36")
    for pg in GROUPS:
        d = fit_rows[fit_rows.position_group == pg]
        coef = fit_curve(d)
        mu, peak = _multipliers(coef)
        lo, hi, pcis = bootstrap(d, n_boot=n_boot)
        for i, ag in enumerate(AGES):
            rows.append(dict(position=pg, age=ag, mult=mu[i], lo=lo[i], hi=hi[i]))
        at = {a: mu[list(AGES).index(a)] for a in (21, 25, 27, 29, 33, 36)}
        e_peak = _multipliers(fit_curve(d, "efficiency"))[1]
        print(f"{pg:8s} {len(d):<5d} {peak:4.1f}  "
              f"[{pcis[0]:.1f},{pcis[2]:.1f}]  " +
              "  ".join(f"{at[a]:.2f}" for a in (21, 25, 27, 29, 33, 36)) +
              f"   (efficiency peak {e_peak:.1f})")

    curves = pd.DataFrame(rows)
    CACHE.mkdir(parents=True, exist_ok=True)
    curves.to_csv(CURVES, index=False)
    print(f"\nwrote {CURVES}")
    print("note: value_p90 is attacking output (npxG+xAG/90); DF/MF curves are "
          "attacking-role aging, not total value.")
    return curves


# ------------------------------------------------------------------- _check

def _synth(peak=27.0, curved=True, seed=0):
    """~60 players, each a within-player parabola peaking at `peak` + noise.
    Player levels vary widely, so a naive across-player fit would fail; only the
    FE demeaning recovers the planted peak."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(60):
        base = rng.uniform(0.1, 0.6)                 # player fixed effect
        start = rng.integers(19, 30)
        for age in range(start, start + int(rng.integers(3, 8))):
            true = base + (-0.004 * (age - peak) ** 2 if curved else 0.0)
            rows.append(dict(player=i, age=float(age),
                             value_p90=max(0.0, true + rng.normal(0, 0.03)),
                             n90s=float(rng.uniform(10, 34))))
    return pd.DataFrame(rows)


def _check():
    # planted parabola: FE fit must recover the peak within +/-2 years
    d = _synth(peak=27.0, curved=True)
    coef = fit_curve(d)
    mu, peak = _multipliers(coef)
    assert abs(peak - 27.0) <= 2.0, f"peak {peak} != 27"
    assert mu[list(AGES).index(34.0)] < 0.9, "must decline past peak"
    _, _, pcis = bootstrap(d, n_boot=200)
    assert pcis[0] <= 27.0 <= pcis[2], f"27 outside peak CI {pcis}"

    # null: flat signal -> near-flat curve (range < 0.1), peak ill-defined
    d0 = _synth(curved=False, seed=1)
    mu0, _ = _multipliers(fit_curve(d0))
    grid = (AGES >= 20) & (AGES <= 34)
    assert np.ptp(mu0[grid]) < 0.10, f"null curve not flat: range {np.ptp(mu0[grid]):.3f}"

    # a strong across-player confound must NOT fool the FE fit: give players a
    # level tied to their *career* age (older cohorts better = survivorship),
    # flat within each career. A naive across-player fit would read an upward
    # age slope; the FE demeaning must absorb it and stay flat.
    dc = _synth(curved=False, seed=2)
    off = dc.groupby("player").age.transform("mean")
    dc["value_p90"] += 0.02 * (off - 25)             # per-player, flat in career
    muc, _ = _multipliers(fit_curve(dc))
    assert np.ptp(muc[grid]) < 0.10, "FE must absorb the across-player age confound"

    print(f"planted peak recovered: {peak:.1f} (CI {pcis[0]:.1f}-{pcis[2]:.1f})")
    print(f"null curve range 20-34: {np.ptp(mu0[grid]):.3f}  "
          f"confounded range: {np.ptp(muc[grid]):.3f}")
    print("ok")


if __name__ == "__main__":
    import sys
    build() if "build" in sys.argv[1:] else _check()
