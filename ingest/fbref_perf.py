"""FBref perf_player_season — the 221-col frozen snapshot, keyed to TM ids.

Audit finding: this table (Estate B, 52,951 player-seasons, 2010-2026, Big-5,
221 stat cols) is the ONE irreplaceable thing in the old DuckDB build and the
model's known blind spot — it carries the DEFENSIVE + PROGRESSION signal that
Understat xG (attacking output only) cannot see. It was stranded behind a
broken crosswalk id. We attach tm_player_id via ingest.players_master (repaired
fbref bridge) so Estate-A players can finally reach it.

Two outputs:
  * read_perf()          -> all 221 cols + tm_player_id (fbref_id preserved)
  * defensive_summary()  -> the blind-spot axis, per-90, one row per
    (tm_player_id, season): tackles, interceptions, blocks, recoveries,
    aerials won, progressive carries/passes. This is what feeds a future
    defensive-value term in impact/.

FBref lost xG/advanced data to the Opta pull (Jan 2025); this is a FROZEN
snapshot, not refreshable — treat it as historical (2010-2024 usable).
"""
from __future__ import annotations
import os
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ESTATE_B = Path(os.environ.get(
    "ESTATE_B_DIR", "/Users/benrimmer/Downloads/football-transfer-db"))
SRC = ESTATE_B / "03_performance" / "perf_player_season.parquet"
OUT = REPO / "data" / "fbref" / "perf_player_season.parquet"

# blind-spot axis: raw counting col -> summary name. Guarded (snapshot may vary).
_DEF_COLS = {
    "defense__Tkl_Tackles": "tackles",
    "defense__Int": "interceptions",
    "defense__Blocks_Blocks": "blocks",
    "misc__Recov": "recoveries",
    "misc__Won_Aerial": "aerials_won",
    "standard__PrgC_Progression": "prog_carries",
    "standard__PrgP_Progression": "prog_passes",
}
_MIN90 = "defense__Mins_Per_90"  # FBref's 90s-played denominator

# Curated niche stats -> (source col, kind). kind: 'count' = divide by 90s;
# 'rate' = already per-90 or a percentage, pass through; 'raw' = absolute
# season total worth keeping as-is (overperformance, avg distance).
_NICHE = {
    # creation
    "key_passes": ("passing__KP", "count"),
    "xa": ("passing__xA", "count"),
    "passes_into_box": ("passing__PPA", "count"),
    "passes_into_final_third": ("passing__Final_Third", "count"),
    "through_balls": ("passing_types__TB_Pass", "count"),
    "switches": ("passing_types__Sw_Pass", "count"),
    "prog_passes": ("standard__PrgP_Progression", "count"),  # better-populated than passing__PrgP
    # carrying / receiving
    "prog_carries": ("possession__PrgC_Carries", "count"),
    "carries_into_box": ("possession__CPA_Carries", "count"),
    "carries_into_final_third": ("possession__Final_Third_Carries", "count"),
    "miscontrols": ("possession__Mis_Carries", "count"),
    "dispossessed": ("possession__Dis_Carries", "count"),
    "prog_receptions": ("possession__PrgR_Receiving", "count"),
    "att_pen_touches": ("possession__Att Pen_Touches", "count"),
    # dribbling
    "take_ons": ("possession__Att_Take", "count"),
    "take_on_success_pct": ("possession__Succ_percent_Take", "rate"),
    # shooting
    "npxg": ("shooting__npxG_Expected", "count"),
    "npg_minus_npxg": ("shooting__np:G_minus_xG_Expected", "raw"),
    "avg_shot_distance": ("shooting__Dist_Standard", "raw"),
    # defending
    "tackle_win_pct": ("defense__Tkl_percent_Challenges", "rate"),
    "errors_to_shot": ("defense__Err", "count"),
    # duels / discipline
    "aerials_won": ("misc__Won_Aerial", "count"),
    "aerials_lost": ("misc__Lost_Aerial", "count"),
    "recoveries": ("misc__Recov", "count"),
    "fouled": ("misc__Fld", "count"),
    "fouls": ("misc__Fls", "count"),
    # goalkeeping
    "psxg_per_sot": ("keepers_adv__PSxG_per_SoT_Expected", "rate"),
    "psxg_plus_minus": ("keepers_adv__PSxG+_per__minus__Expected", "raw"),
    "def_actions_outside_box_p90": ("keepers_adv__#OPA_per_90_Sweeper", "rate"),
    "gk_avg_pass_distance": ("keepers_adv__AvgDist_Sweeper", "raw"),
    "launch_completion_pct": ("keepers_adv__Cmp_percent_Launched", "rate"),
}


def attach_tm(perf: pd.DataFrame, bridge: pd.DataFrame) -> pd.DataFrame:
    """Join tm_player_id onto perf via fbref_id (bridge = fbref_id,tm_player_id)."""
    return perf.merge(bridge.drop_duplicates("fbref_id"), on="fbref_id", how="left")


def defensive_summary(perf: pd.DataFrame) -> pd.DataFrame:
    """Per-90 blind-spot metrics, one row per (tm_player_id, Season_End_Year).

    Only rows with a tm_player_id and >= 5 90s (450 min) — small samples make
    per-90 defensive rates meaningless. Missing source cols are skipped.
    """
    d = perf[perf.tm_player_id.notna()].copy()
    if _MIN90 in d.columns:
        n90 = pd.to_numeric(d[_MIN90], errors="coerce")
    else:
        n90 = pd.Series(1.0, index=d.index)
    out = pd.DataFrame({
        "tm_player_id": d.tm_player_id.astype("int64"),
        "season_end_year": pd.to_numeric(d.Season_End_Year, errors="coerce").astype("Int64"),
        "comp": d.Comp, "squad": d.Squad, "n90": n90,
    })
    for raw, name in _DEF_COLS.items():
        if raw in d.columns:
            out[name + "_p90"] = pd.to_numeric(d[raw], errors="coerce") / n90.replace(0, pd.NA)
    out = out[out.n90 >= 5]
    return out.reset_index(drop=True)


def niche_summary(perf: pd.DataFrame) -> pd.DataFrame:
    """The hard-to-find side stats already in the 221-col table, per-90 where
    it makes sense, keyed to (tm_player_id, season). >= 5 90s only. Missing
    source cols are skipped (snapshot-safe)."""
    d = perf[perf.tm_player_id.notna()].copy()
    n90 = pd.to_numeric(d[_MIN90], errors="coerce") if _MIN90 in d.columns \
        else pd.Series(1.0, index=d.index)
    out = pd.DataFrame({
        "tm_player_id": d.tm_player_id.astype("int64"),
        "season_end_year": pd.to_numeric(d.Season_End_Year, errors="coerce").astype("Int64"),
        "comp": d.Comp, "squad": d.Squad, "n90": n90,
    })
    for name, (col, kind) in _NICHE.items():
        if col not in d.columns:
            continue
        v = pd.to_numeric(d[col], errors="coerce")
        out[name] = (v / n90.replace(0, np.nan)).round(3) if kind == "count" else v.round(3)
    return out[out.n90 >= 5].reset_index(drop=True)


def read_perf() -> pd.DataFrame:
    perf = pd.read_parquet(SRC)
    from ingest import players_master
    m = players_master.load()
    bridge = (m[m.has_fbref][["fbref_id", "tm_player_id"]]
              if "has_fbref" in m.columns else m[["fbref_id", "tm_player_id"]].dropna())
    return attach_tm(perf, bridge)


def build() -> pd.DataFrame:
    perf = read_perf()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    perf.to_parquet(OUT, index=False)
    ds = defensive_summary(perf)
    ds.to_parquet(OUT.parent / "defensive_summary.parquet", index=False)
    ns = niche_summary(perf)
    ns.to_parquet(OUT.parent / "niche_summary.parquet", index=False)

    n = len(perf)
    print(f"perf_player_season rows:      {n:,}  ({len(perf.columns)} cols)")
    print(f"  with tm_player_id:          {int(perf.tm_player_id.notna().sum()):,}  "
          f"({100*perf.tm_player_id.notna().mean():.1f}%)")
    print(f"  distinct TM players reached: {perf.tm_player_id.nunique():,}")
    print(f"  season range:               {int(pd.to_numeric(perf.Season_End_Year).min())}"
          f"-{int(pd.to_numeric(perf.Season_End_Year).max())}")
    print(f"defensive_summary rows (>=5x90): {len(ds):,}  cols {list(ds.columns)}")
    print(f"niche_summary rows (>=5x90):     {len(ns):,}  ({len([c for c in ns.columns if c not in ('tm_player_id','season_end_year','comp','squad','n90')])} niche stats)")
    print(f"wrote {OUT} + defensive_summary.parquet + niche_summary.parquet")
    return perf


# ------------------------------------------------------------------ check

def _check():
    perf = pd.DataFrame([
        dict(fbref_id="a", Player="X", Season_End_Year=2020, Comp="EPL", Squad="Arsenal",
             **{_MIN90: 30.0, "defense__Tkl_Tackles": 60.0, "defense__Int": 30.0,
                "defense__Blocks_Blocks": 15.0, "misc__Recov": 300.0,
                "misc__Won_Aerial": 90.0, "standard__PrgC_Progression": 120.0,
                "standard__PrgP_Progression": 150.0}),
        dict(fbref_id="b", Player="Y", Season_End_Year=2020, Comp="EPL", Squad="Spurs",
             **{_MIN90: 2.0, "defense__Tkl_Tackles": 10.0, "defense__Int": 5.0,
                "defense__Blocks_Blocks": 2.0, "misc__Recov": 20.0, "misc__Won_Aerial": 5.0,
                "standard__PrgC_Progression": 8.0, "standard__PrgP_Progression": 9.0}),  # <5x90 -> dropped
    ])
    bridge = pd.DataFrame([dict(fbref_id="a", tm_player_id=111),
                           dict(fbref_id="c", tm_player_id=222)])  # b has no tm id
    p = attach_tm(perf, bridge)
    assert p.set_index("fbref_id").loc["a"].tm_player_id == 111
    assert pd.isna(p.set_index("fbref_id").loc["b"].tm_player_id)
    ds = defensive_summary(p)
    assert len(ds) == 1, "only player a: has tm id AND >=5x90"
    r = ds.iloc[0]
    assert r.tackles_p90 == 2.0 and r.interceptions_p90 == 1.0  # 60/30, 30/30
    assert r.prog_passes_p90 == 5.0

    # niche_summary: a 'count' stat divides by 90s, a 'rate' passes through
    perf2 = perf.assign(**{"passing__KP": [90.0, 6.0],  # key passes: 90/30=3.0
                           "possession__Succ_percent_Take": [55.0, 40.0]})  # rate: passthrough
    ns = niche_summary(attach_tm(perf2, bridge))
    assert len(ns) == 1
    assert ns.iloc[0].key_passes == 3.0, "count stat per-90'd"
    assert ns.iloc[0].take_on_success_pct == 55.0, "rate stat passed through, not divided"
    print(ds.to_string(index=False))
    print(f"niche cols: {[c for c in ns.columns if c not in ('tm_player_id','season_end_year','comp','squad','n90')]}")
    print("ok")


if __name__ == "__main__":
    import sys
    if "build" in sys.argv[1:]:
        build()
    else:
        _check()
