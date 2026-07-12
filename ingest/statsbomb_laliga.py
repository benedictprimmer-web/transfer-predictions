"""Pull StatsBomb open-data La Liga shots (comp 11, 2004/05-2020/21) for the
Messi full-xG-career showpiece. Barca matches every season + the complete
2015/16 La Liga. Resumable: caches extracted shots per match as small JSON.

Run:  python3 -m ingest.statsbomb_laliga build   (background, ~10-15 min)
      python3 -m ingest.statsbomb_laliga            # offline aggregate check
Output: data/statsbomb/laliga_shots.pkl
"""
import os, json, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE = os.path.join(ROOT, "data/statsbomb/laliga_cache")
OUT = os.path.join(ROOT, "data/statsbomb/laliga_shots.pkl")


def _get(url):
    with urllib.request.urlopen(url, timeout=40) as r:
        return json.load(r)


def _season_map():
    comps = _get(f"{B}/competitions.json")
    return {c["season_id"]: c["season_name"] for c in comps
            if c["competition_id"] == 11 and c["season_name"] != "1973/1974"}


def _extract_shots(match_id, season):
    """Pull one match's events, return list of shot dicts (cached)."""
    cf = os.path.join(CACHE, f"{match_id}.json")
    if os.path.exists(cf):
        return json.load(open(cf))
    ev = _get(f"{B}/events/{match_id}.json")
    out = []
    for e in ev:
        if e.get("type", {}).get("name") != "Shot":
            continue
        sh = e.get("shot", {})
        out.append({
            "season": season, "match_id": match_id,
            "player": (e.get("player") or {}).get("name"),
            "team": (e.get("team") or {}).get("name"),
            "minute": e.get("minute"),
            "xg": sh.get("statsbomb_xg"),
            "goal": 1 if sh.get("outcome", {}).get("name") == "Goal" else 0,
            "is_pen": sh.get("type", {}).get("name") == "Penalty",
        })
    json.dump(out, open(cf, "w"))
    return out


def build(workers=8):
    os.makedirs(CACHE, exist_ok=True)
    seasons = _season_map()
    # collect (match_id, season) across all seasons
    jobs = []
    for sid, name in seasons.items():
        try:
            matches = _get(f"{B}/matches/11/{sid}.json")
        except Exception as e:
            print(f"season {name}: match-list FAILED {e}"); continue
        for m in matches:
            jobs.append((m["match_id"], name))
    print(f"{len(jobs)} matches to fetch (cached ones skip)")
    all_shots, done, err = [], 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_extract_shots, mid, name): (mid, name) for mid, name in jobs}
        for f in as_completed(futs):
            mid, name = futs[f]
            try:
                all_shots.extend(f.result()); done += 1
            except Exception as e:
                err += 1
                if err <= 5:
                    print(f"  match {mid} ({name}) err: {e}")
            if done % 100 == 0:
                print(f"  ...{done}/{len(jobs)} matches, {len(all_shots)} shots")
    df = pd.DataFrame(all_shots)
    df["xg"] = pd.to_numeric(df["xg"], errors="coerce").fillna(0.0)
    df.to_pickle(OUT)
    print(f"DONE: {len(df)} shots from {done} matches ({err} errors) -> {OUT}")
    _summ(df)
    return df


def _summ(df):
    m = df[df["player"] == "Lionel Messi Cuccittini"]
    if m.empty:
        m = df[df["player"].astype(str).str.startswith("Lionel")]
    g = m.groupby("season").agg(shots=("goal", "size"), goals=("goal", "sum"),
                                xg=("xg", "sum")).round(1)
    print("Messi by season:\n", g)
    print(f"Messi TOTAL: {int(m['goal'].sum())} goals, {m['xg'].sum():.0f} xG, {len(m)} shots")


def _check():
    if os.path.exists(OUT):
        df = pd.read_pickle(OUT)
        assert (df["xg"] >= 0).all() and df["xg"].max() <= 1.01, "xg out of range"
        assert df["player"].astype(str).str.contains("Lionel").any(), "no Messi shots"
        print(f"OK cache: {len(df)} shots, {df['season'].nunique()} seasons")
        _summ(df)
    else:
        print("no cache yet — run: python3 -m ingest.statsbomb_laliga build")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build()
    else:
        _check()
