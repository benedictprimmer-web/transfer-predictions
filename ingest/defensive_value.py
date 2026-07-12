"""Lane D — defensive / off-ball value layer (SPEC: impact/usage.py is shot-based
and structurally blind to defenders/deep midfielders; this fills that gap).

Composite, not a trained possession-value model: `socceraction` (VAEP/xT) is
installed but StatsBomb's open events (448 matches, mostly La Liga/Champions
League history + internationals + two lone Premier League seasons) barely
overlap the 2018-2025 Big-5 window this needs to match, and carry no
tm_player_id bridge (name-only). Training a VAEP model on a non-overlapping,
unlinked sample isn't worth it here — ponytail: FBref's own defensive_summary
+ niche_summary (already tm_player_id-keyed, Big-5, 2018-2025, 14,634
player-seasons) is the fallback path the brief names, and it IS the broad-
coverage answer. Revisit StatsBomb VAEP as a modelling-stage upgrade if event
coverage widens.

Method: equal-weight z-score of 7 per-90 defensive/progressive actions
(tackles, interceptions, blocks, recoveries, aerials won, progressive
carries, progressive passes), pooled across the full sample -> percentile
0-100. Absolute, not position-relative: the point is that defenders/DMs
should score high in absolute terms (that's exactly the value the shot-based
engine misses), not "best defender for a CB". tackle_win_pct and
errors_to_shot ride along as reference-only quality columns, not blended
into the score (keeps the grade legible: box-score composite, not a
quality-adjusted model).

Run: python3 -m ingest.defensive_value build
"""
import pandas as pd

_COMPONENTS = [
    "tackles_p90", "interceptions_p90", "blocks_p90", "recoveries_p90",
    "aerials_won_p90", "prog_carries_p90", "prog_passes_p90",
]


def defensive_value(defensive_summary: pd.DataFrame, niche_summary: pd.DataFrame) -> pd.DataFrame:
    """defensive_summary/niche_summary: ingest.fbref_perf schema, tm_player_id-keyed."""
    df = defensive_summary.copy()
    z = df[_COMPONENTS].apply(lambda c: (c - c.mean()) / c.std(ddof=0))
    df["defensive_value_z"] = z.mean(axis=1)
    df["defensive_value_score"] = df["defensive_value_z"].rank(pct=True) * 100

    extra = niche_summary[["tm_player_id", "season_end_year", "comp", "squad", "tackle_win_pct", "errors_to_shot"]]
    df = df.merge(extra, on=["tm_player_id", "season_end_year", "comp", "squad"], how="left")

    df["grade"] = "C"
    df["source"] = "fbref_defensive_summary+niche_summary"
    keep = ["tm_player_id", "season_end_year", "comp", "squad", "n90",
            *_COMPONENTS, "tackle_win_pct", "errors_to_shot",
            "defensive_value_z", "defensive_value_score", "grade", "source"]
    return df[keep].sort_values("defensive_value_score", ascending=False).reset_index(drop=True)


def build():
    ds = pd.read_parquet("data/fbref/defensive_summary.parquet")
    ns = pd.read_parquet("data/fbref/niche_summary.parquet")
    out = defensive_value(ds, ns)
    out.to_parquet("data/impact/defensive_value.parquet", index=False)
    print(f"wrote data/impact/defensive_value.parquet: {len(out)} rows, "
          f"{out.tm_player_id.nunique()} players")
    return out


def _check():
    ds = pd.DataFrame([
        # ball-winning DM: high tackles/interceptions/recoveries/progression
        dict(tm_player_id=1, season_end_year=2020, comp="EPL", squad="A", n90=30.0,
             tackles_p90=3.5, interceptions_p90=2.0, blocks_p90=1.0, recoveries_p90=8.0,
             aerials_won_p90=1.5, prog_carries_p90=2.5, prog_passes_p90=7.0),
        # pure poacher: almost no defensive/progressive load
        dict(tm_player_id=2, season_end_year=2020, comp="EPL", squad="B", n90=30.0,
             tackles_p90=0.2, interceptions_p90=0.1, blocks_p90=0.1, recoveries_p90=1.5,
             aerials_won_p90=0.5, prog_carries_p90=0.8, prog_passes_p90=0.5),
        # middling squad player
        dict(tm_player_id=3, season_end_year=2020, comp="EPL", squad="C", n90=30.0,
             tackles_p90=1.5, interceptions_p90=1.0, blocks_p90=0.5, recoveries_p90=4.0,
             aerials_won_p90=1.0, prog_carries_p90=1.5, prog_passes_p90=3.0),
    ])
    ns = pd.DataFrame([
        dict(tm_player_id=pid, season_end_year=2020, comp="EPL", squad=sq, tackle_win_pct=50.0, errors_to_shot=0)
        for pid, sq in ((1, "A"), (2, "B"), (3, "C"))
    ])
    out = defensive_value(ds, ns)
    dm = out.set_index("tm_player_id").loc[1]
    poacher = out.set_index("tm_player_id").loc[2]
    assert dm.defensive_value_score == out.defensive_value_score.max(), "ball-winner must top the ranking"
    assert poacher.defensive_value_score == out.defensive_value_score.min(), "poacher must rank lowest"
    assert dm.grade == "C" and dm.source.startswith("fbref_")
    print(out[["tm_player_id", "defensive_value_score", "grade"]].to_string(index=False))
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
