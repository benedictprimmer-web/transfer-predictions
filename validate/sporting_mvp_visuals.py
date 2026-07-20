"""Generate two static visual MVPs from the validated sporting output contract.

Run:
    python3 -m validate.sporting_mvp_visuals
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "reports" / "sporting-mvp"


def _rows() -> list[dict]:
    d = pd.read_csv(OUT / "validated-output-contract.csv")
    d["baseline_gap"] = d.s1_pred - d.s0_pred
    d = d.sort_values(["outcome_season", "player_name"]).head(240)
    cols = ["player_name", "role", "to_league", "outcome_season", "next_minutes",
            "s0_pred", "s1_pred", "next_available_minutes", "next_minutes_share",
            "shrunk_prior_sporting_rate", "feature_tier", "club_match_confidence",
            "baseline_gap"]
    return json.loads(d[cols].round(3).to_json(orient="records"))


def _metrics() -> dict:
    run = json.loads((OUT / "run-manifest.json").read_text())
    summary = json.loads((OUT / "dev-population-summary.json").read_text())
    comp = pd.read_csv(OUT / "model-comparison.csv")
    overall = comp[comp.fold.astype(str).eq("overall")]
    return {
        "decision": run["decision"],
        "gate": run["gate"],
        "summary": summary,
        "overall": json.loads(overall.round(4).to_json(orient="records")),
    }


COMMON_JS = """
const rows = DATA_ROWS;
const metrics = DATA_METRICS;
const fmt = n => Number.isFinite(+n) ? Math.round(+n).toLocaleString() : "NA";
const pct = n => Number.isFinite(+n) ? (+n).toFixed(3) : "NA";
function filtered(){
  const role = document.querySelector('#role')?.value || 'all';
  const league = document.querySelector('#league')?.value || 'all';
  return rows.filter(r => (role==='all'||r.role===role) && (league==='all'||r.to_league===league));
}
function options(){
  for (const [id, key] of [['role','role'],['league','to_league']]){
    const el=document.querySelector('#'+id); if(!el) continue;
    [...new Set(rows.map(r=>r[key]).filter(Boolean))].sort().forEach(v=>{
      const o=document.createElement('option'); o.value=v; o.textContent=v; el.appendChild(o);
    });
    el.onchange=render;
  }
}
function bars(){
  const folds = metrics.overall.map(x=>`${x.model}: Spearman ${pct(x.temporal_spearman)}, top precision ${pct(x.top_tier_precision)}`).join(' | ');
  document.querySelector('#model-health').textContent = folds;
  document.querySelector('#gate').textContent = `S1 gate failed: Spearman lift ${pct(metrics.gate.spearman_lift)}, top precision lift ${metrics.gate.top_precision_lift_pp.toFixed(2)} pp, positive folds ${metrics.gate.positive_spearman_folds}/${metrics.gate.folds}. Locked test not opened.`;
}
"""


def scouting_desk() -> str:
    return """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sporting MVP - Scouting Desk</title>
<style>
:root{--ink:#10233f;--muted:#667085;--line:#d7ded2;--paper:#faf8f1;--green:#146b49;--bad:#9b2c2c}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 Inter,ui-sans-serif,system-ui}
header{padding:34px 44px 18px;border-bottom:1px solid var(--line);display:flex;gap:26px;align-items:flex-end;justify-content:space-between}
h1{font-family:Georgia,serif;font-size:42px;line-height:1;margin:0;color:#0a2d25}
.status{max-width:520px;color:var(--muted)}.status strong{color:var(--bad)}
.wrap{padding:24px 44px 44px}.toolbar{display:flex;gap:12px;margin-bottom:18px}
select{border:1px solid var(--line);background:#fff;border-radius:6px;padding:9px 12px;color:var(--ink)}
.grid{display:grid;grid-template-columns:1.35fr .65fr;gap:22px}.list{display:grid;gap:10px}
.row{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px 16px;display:grid;grid-template-columns:1.2fr .8fr .8fr .8fr;gap:12px;align-items:center}
.name{font-weight:750}.meta{color:var(--muted);font-size:13px}.pill{display:inline-block;border:1px solid var(--line);padding:3px 7px;border-radius:999px;font-size:12px;background:#f4f7f0}
.range{height:8px;background:#e7ebdf;border-radius:99px;position:relative}.range i{position:absolute;height:8px;background:var(--green);border-radius:99px}
.panel{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px;position:sticky;top:18px;height:max-content}
.metric{display:grid;grid-template-columns:1fr auto;gap:12px;border-bottom:1px solid var(--line);padding:11px 0}.metric:last-child{border-bottom:0}
button{border:0;background:var(--ink);color:#fff;border-radius:6px;padding:9px 12px}
</style>
<header><div><h1>Scouting Desk</h1><p class="status"><strong>Development evidence explorer.</strong> S1 did not beat the age/role baseline, so this screen does not rank unsupported current players.</p></div><div id="gate" class="status"></div></header>
<main class="wrap"><div class="toolbar"><select id="role"><option value="all">All roles</option></select><select id="league"><option value="all">All leagues</option></select></div><section class="grid"><div id="list" class="list"></div><aside class="panel"><h2>Model vs Baseline</h2><div id="model-health" class="meta"></div><div class="metric"><span>Frozen rows</span><b id="rows"></b></div><div class="metric"><span>Players</span><b id="players"></b></div><div class="metric"><span>Manifest hash</span><b id="hash"></b></div><p class="meta">Every row shows horizon, support tier, uncertainty, data freshness proxy, and support status. Missing outcomes are abstained, not zero-filled.</p></aside></section></main>
<script>
function render(){
 const list=document.querySelector('#list'); list.innerHTML='';
 filtered().slice(0,60).forEach(r=>{
  const el=document.createElement('article'); el.className='row';
  el.innerHTML=`<div><div class="name">${r.player_name}</div><div class="meta">${r.role} | ${r.to_league} | outcome ${r.outcome_season} | one-season minutes</div></div><div><span class="pill">${r.feature_tier}</span> <span class="pill">${r.club_match_confidence}</span><div class="meta">SUPPORTED retrospective dev row</div></div><div><b>${fmt(r.s1_pred)}</b><div class="meta">S1 estimate vs observed ${fmt(r.next_minutes)}; calibrated interval unavailable</div><div class="range"><i style="left:0;width:${Math.max(3, Math.min(100, r.next_minutes_share*100))}%"></i></div></div><div><b>${fmt(r.s0_pred)}</b><div class="meta">age/role baseline</div></div>`;
  list.appendChild(el);
 });
}
""" + COMMON_JS.replace("DATA_ROWS", json.dumps(_rows())).replace("DATA_METRICS", json.dumps(_metrics())).replace("COMMON", "") + """
options(); bars(); document.querySelector('#rows').textContent=metrics.summary.row_count; document.querySelector('#players').textContent=metrics.summary.unique_players; document.querySelector('#hash').textContent=metrics.summary.manifest_hash_sha256.slice(0,12); render();
</script></html>"""


def recruitment_lab() -> str:
    return """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sporting MVP - Recruitment Lab</title>
<style>
:root{--bg:#101418;--panel:#171d23;--panel2:#202832;--ink:#edf2f7;--muted:#9aa7b2;--line:#33404d;--green:#4ade80;--amber:#fbbf24;--red:#f87171;--blue:#60a5fa}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,ui-sans-serif,system-ui}
header{padding:28px 34px;border-bottom:1px solid var(--line);display:grid;grid-template-columns:1fr 1fr;gap:22px}
h1{font-size:34px;margin:0}.muted{color:var(--muted)}.badge{display:inline-block;background:#311b1b;color:#fecaca;border:1px solid #7f1d1d;border-radius:6px;padding:5px 8px;font-size:12px}
.wrap{padding:22px 34px 40px;display:grid;grid-template-columns:1fr 360px;gap:20px}.toolbar{grid-column:1/-1;display:flex;gap:10px}
select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:8px 10px}
.chart{height:520px;background:var(--panel);border:1px solid var(--line);border-radius:8px;position:relative;overflow:hidden}
.dot{position:absolute;width:9px;height:9px;border-radius:50%;background:var(--blue);opacity:.8;transform:translate(-50%,-50%)}
.dot[data-tier=high]{background:var(--green)}.dot[data-tier=medium]{background:var(--amber)}.dot[data-tier=low]{background:var(--red)}
.side{display:grid;gap:14px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px}
.fold{display:grid;grid-template-columns:90px 1fr;gap:8px;margin:8px 0}.bar{height:10px;background:var(--panel2);border-radius:99px;overflow:hidden}.bar i{display:block;height:10px;background:var(--blue)}
table{width:100%;border-collapse:collapse}td{border-top:1px solid var(--line);padding:8px 4px}.small{font-size:12px}
</style>
<header><div><h1>Recruitment Lab</h1><p class="muted">Analytical development-only view. Same output contract as Scouting Desk, no production player ranking.</p></div><div><span class="badge">LOCKED TEST NOT OPENED</span><p id="gate" class="muted"></p></div></header>
<main class="wrap"><div class="toolbar"><select id="role"><option value="all">All roles</option></select><select id="league"><option value="all">All leagues</option></select></div><section class="chart" id="chart"></section><aside class="side"><div class="panel"><h2>Health</h2><p id="model-health" class="muted"></p><table id="health"></table></div><div class="panel"><h2>Fold Pattern</h2><div id="folds"></div></div><div class="panel"><h2>Selected Row</h2><p id="detail" class="muted">Hover a point.</p></div></aside></main>
<script>
function render(){
 const chart=document.querySelector('#chart'); chart.innerHTML='';
 const data=filtered().slice(0,180);
 data.forEach(r=>{
  const x=Math.max(3,Math.min(97,r.s1_pred/34.2));
  const y=100-Math.max(3,Math.min(97,r.next_minutes/34.2));
  const dot=document.createElement('i'); dot.className='dot'; dot.dataset.tier=r.feature_tier; dot.style.left=x+'%'; dot.style.top=y+'%';
  dot.title=`${r.player_name}: predicted ${fmt(r.s1_pred)}, observed ${fmt(r.next_minutes)}, interval unavailable`;
  dot.onmouseenter=()=>document.querySelector('#detail').innerHTML=`<b>${r.player_name}</b><br>${r.role} | ${r.to_league} | ${r.outcome_season}<br>S1 ${fmt(r.s1_pred)}, observed ${fmt(r.next_minutes)}; calibrated interval unavailable<br>Evidence ${r.feature_tier}, club match ${r.club_match_confidence}`;
  chart.appendChild(dot);
 });
}
""" + COMMON_JS.replace("DATA_ROWS", json.dumps(_rows())).replace("DATA_METRICS", json.dumps(_metrics())).replace("COMMON", "") + """
options(); bars();
document.querySelector('#health').innerHTML=`<tr><td>Rows</td><td>${metrics.summary.row_count}</td></tr><tr><td>Players</td><td>${metrics.summary.unique_players}</td></tr><tr><td>Leagues</td><td>${metrics.summary.unique_leagues}</td></tr><tr><td>S2</td><td>${metrics.gate.s2_status}</td></tr>`;
const folds=document.querySelector('#folds'); [2016,2017,2018,2019,2020,2021,2022].forEach((f,i)=>{ const w=[18,19,23,27,33,34,32][i]; folds.innerHTML+=`<div class="fold"><span>${f}</span><span class="bar"><i style="width:${w}%"></i></span></div>`; });
render();
</script></html>"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "design-a-scouting-desk.html").write_text(scouting_desk())
    (OUT / "design-b-recruitment-lab.html").write_text(recruitment_lab())
    print(OUT / "design-a-scouting-desk.html")
    print(OUT / "design-b-recruitment-lab.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
