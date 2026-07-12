"""Pull every StatsBomb open-data source Cristiano Ronaldo appears in, to build
the richest possible xG record for him (his league xG mostly doesn't exist free).

Sources: PL 2003/04 (Man Utd rookie year), all Champions League finals,
World Cup 2018 + 2022, Euro 2020 + 2024. (His 2015/16 Real Madrid La Liga
season + Clasicos are already in data/statsbomb/laliga_shots.pkl.)

Extracts ALL shots (reusable) + goal-assist passes for CR7. Resumable.
Run:  python3 -m ingest.statsbomb_ronaldo build
Output: data/statsbomb/ronaldo_sources_shots.pkl  (+ ronaldo_assists.json)
"""
import os, json, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE = os.path.join(ROOT, "data/statsbomb/ronaldo_cache")
OUT = os.path.join(ROOT, "data/statsbomb/ronaldo_sources_shots.pkl")
AST = os.path.join(ROOT, "data/statsbomb/ronaldo_assists.json")
CR = "Cristiano Ronaldo dos Santos Aveiro"

# (competition_id, season_name) — everything CR7 could be in, minus what we have
WANT = [
    (2, "2003/2004"),      # Premier League — Man Utd, age 18-19
    (43, "2018"), (43, "2022"),   # World Cup
    (55, "2020"), (55, "2024"),   # Euro
    # all Champions League finals added dynamically below
]


def _get(url):
    with urllib.request.urlopen(url, timeout=40) as r:
        return json.load(r)


def _resolve():
    comps = _get(f"{B}/competitions.json")
    by = {}
    for c in comps:
        by[(c["competition_id"], c["season_name"])] = c["season_id"]
    jobs = []
    for cid, sn in WANT:
        sid = by.get((cid, sn))
        if sid is not None:
            jobs.append((cid, sid, sn))
    # every CL season (they are single finals)
    for c in comps:
        if c["competition_id"] == 16:
            jobs.append((16, c["season_id"], "CL " + c["season_name"]))
    return jobs


def _match_shots(cid, mid, label):
    cf = os.path.join(CACHE, f"{mid}.json")
    if os.path.exists(cf):
        return json.load(open(cf))
    ev = _get(f"{B}/events/{mid}.json")
    shots, assists = [], []
    for e in ev:
        t = e.get("type", {}).get("name")
        if t == "Shot":
            sh = e.get("shot", {})
            shots.append({
                "comp": cid, "season": label, "match_id": mid,
                "player": (e.get("player") or {}).get("name"),
                "team": (e.get("team") or {}).get("name"),
                "minute": e.get("minute"),
                "xg": sh.get("statsbomb_xg"),
                "goal": 1 if sh.get("outcome", {}).get("name") == "Goal" else 0,
                "is_pen": sh.get("type", {}).get("name") == "Penalty",
            })
        elif t == "Pass":
            pa = e.get("pass", {})
            if pa.get("goal_assist") and (e.get("player") or {}).get("name") == CR:
                assists.append({"season": label, "match_id": mid})
    payload = {"shots": shots, "assists": assists}
    json.dump(payload, open(cf, "w"))
    return payload


def build(workers=8):
    os.makedirs(CACHE, exist_ok=True)
    seasons = _resolve()
    jobs = []
    for cid, sid, label in seasons:
        try:
            matches = _get(f"{B}/matches/{cid}/{sid}.json")
        except Exception as e:
            print(f"{label}: match-list FAIL {e}"); continue
        for m in matches:
            jobs.append((cid, m["match_id"], label))
    print(f"{len(jobs)} matches to fetch")
    all_shots, all_ast, done, err = [], [], 0, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_match_shots, cid, mid, lbl): (mid, lbl) for cid, mid, lbl in jobs}
        for f in as_completed(futs):
            try:
                p = f.result(); all_shots.extend(p["shots"]); all_ast.extend(p["assists"]); done += 1
            except Exception as e:
                err += 1
                if err <= 5:
                    print("  err", futs[f], e)
            if done % 60 == 0:
                print(f"  ...{done}/{len(jobs)}, {len(all_shots)} shots")
    df = pd.DataFrame(all_shots)
    df["xg"] = pd.to_numeric(df["xg"], errors="coerce").fillna(0.0)
    df.to_pickle(OUT)
    json.dump(all_ast, open(AST, "w"))
    print(f"DONE: {len(df)} shots, {done} matches, {err} errors -> {OUT}")
    _summ(df, all_ast)


def _summ(df, assists=None):
    cr = df[df["player"] == CR]
    if cr.empty:
        print("!! no Cristiano Ronaldo shots found"); return
    g = cr.groupby("season").agg(shots=("goal", "size"), goals=("goal", "sum"),
                                 xg=("xg", "sum")).round(1)
    print("Ronaldo by source:\n", g)
    print(f"Ronaldo TOTAL (these sources): {int(cr['goal'].sum())} goals, "
          f"{cr['xg'].sum():.0f} xG, {len(cr)} shots"
          + (f", {len(assists)} assists" if assists is not None else ""))


def _check():
    if os.path.exists(OUT):
        df = pd.read_pickle(OUT)
        assert df["xg"].between(0, 1.01).all(), "xg range"
        ast = json.load(open(AST)) if os.path.exists(AST) else []
        print(f"OK: {len(df)} shots, {df['season'].nunique()} sources")
        _summ(df, ast)
    else:
        print("no cache — run: python3 -m ingest.statsbomb_ronaldo build")


if __name__ == "__main__":
    import sys
    build() if (len(sys.argv) > 1 and sys.argv[1] == "build") else _check()
