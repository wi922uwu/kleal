# -*- coding: utf-8 -*-
"""Интерактивный стенд для РУЧНОГО теста движка matching_core (stdlib http.server, без фреймворков).

Открой в браузере -> собери интент (тип/темы/режим/роль/радиус/язык/expansion/consent) и профиль «me» ->
жми «Match». Сервер на КАЖДЫЙ запрос реально прогоняет полный пайплайн `orchestrator.search()` (B.1) по
детерминированному пулу и возвращает ранжированную выдачу (tier / band / decision / reciprocal / readiness /
причины / gap) + терминальные случаи (нет пересечения -> честный no-result; всё загейчено).

Запуск:  python matching_core/sim/serve.py [port]      (по умолчанию 7099)
stdlib-only, без сети/LLM. Пул генерится на каждый запрос (можно менять размер/seed и добавлять своих людей).
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.orchestrator import search as S
from matching_core.orchestrator import pipeline as P
from matching_core.orchestrator import expansion as EX
from matching_core.retrieval import retriever as RET
from matching_core.observability import trace as OB
from matching_core.sim.simulate import gen_pool

CFG = V.load_config()
PURPOSE_OF = {"games": "games", "sport": "sport", "language": "language", "dating": "dating",
              "networking": "networking", "social": "friendship", "culture": "friendship",
              "walk": "friendship", "coworking": "networking"}


def run_match(req):
    """Прогнать один интент через движок. Возвращает dict для UI."""
    intent = dict(req.get("intent") or {})
    intent.setdefault("version", 1)
    if req.get("broad_consent"):     # Аудит #2: согласие живёт в intent snapshot, не в loose-аргументе
        intent.setdefault("fallback", {}).setdefault("consent", {})["broad_matching"] = True
    me = req.get("me") or {"name": "me"}
    purpose = req.get("purpose") or PURPOSE_OF.get(intent.get("type"), "friendship")
    pool = gen_pool(int(req.get("pool_size") or 90), int(req.get("seed") or 42))
    extra = req.get("extra_candidates") or []
    if isinstance(extra, list):
        pool = pool + [c for c in extra if isinstance(c, dict) and c.get("name")]
    tl = OB.TraceLog()
    if intent.get("type") == "dating":     # Аудит #7: dating — только через dating-обёртку
        user = dict(me); user.update({"dating_optin": True, "target_preferences_confirmed": True})
        user.setdefault("age", me.get("age") or 30)
        try:
            slate = P.run_dating_search(user, intent, me, pool, CFG, now=0.0, search_id="ui", trace_log=tl)["slate"]
        except P.PipelineError as e:
            return {"pool_size": len(pool), "purpose": purpose, "config_version": CFG.get("config_version"),
                    "traces": 0, "slate": [], "terminal": {"kind": "dating_flow_error", "detail": str(e)}}
    else:
        slate = S.search(intent, me, pool, CFG, purpose=purpose, now=0.0, trace_log=tl, search_id="ui")
    res = {"pool_size": len(pool), "purpose": purpose, "config_version": CFG.get("config_version"),
           "traces": len(tl.all()), "slate": slate, "terminal": None}
    if not slate:
        retrieved = RET.retrieve(intent, pool)
        if retrieved:
            res["terminal"] = {"kind": "all_gated", "retrieved": len(retrieved)}
        else:
            nearby = [c["name"] for c in pool if c.get("open") is True][:3]
            resp = EX.no_topical_overlap_response(intent, has_alt_types=False, nearby_open=nearby)
            res["terminal"] = {"kind": "no_overlap", "steps": resp["steps"],
                               "nearby_open_block": resp["nearby_open_block"]}
    return res


def sample_pool(size, seed):
    """Отдать сам пул (чтобы вручную посмотреть, кто в нём)."""
    return gen_pool(int(size or 90), int(seed or 42))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/pool"):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            self._send(200, {"pool": sample_pool(q.get("size", [90])[0], q.get("seed", [42])[0])})
        else:
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/match":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            self._send(200, run_match(req))
        except Exception as e:  # noqa: BLE001 — отдать ошибку в UI, не падать
            self._send(200, {"error": "%s: %s" % (type(e).__name__, e)})


HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Matching Core — ручной тест</title>
<style>
:root{--bg:#F7F3EE;--surface:#FFF;--surface2:#FBF7F2;--ink:#221D17;--muted:#8B8073;--faint:#B7AC9D;
--line:#EAE1D6;--accent:#D6472B;--accent-ink:#FFF;--pos:#2E8B57;--info:#316F9E;--warn:#A9761C;--neutral:#8B8073;
--t0:#C63D22;--t1:#D06A2A;--t2:#B5901F;--t3:#5E7C8C;--t4:#2E8B7E;
--mono:ui-monospace,"Cascadia Code","JetBrains Mono","SF Mono",Menlo,Consolas,monospace;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--shadow:0 1px 2px rgba(40,28,18,.05),0 8px 26px rgba(40,28,18,.07)}
@media(prefers-color-scheme:dark){:root{--bg:#141110;--surface:#1D1916;--surface2:#241F1A;--ink:#F1EAE0;
--muted:#9C9081;--faint:#6E6456;--line:#322B23;--accent:#F0664A;--accent-ink:#1B0D06;--pos:#57B585;--info:#69A7D8;
--warn:#D8A94E;--neutral:#9C9081;--t0:#EE6247;--t1:#E68A46;--t2:#D6AC43;--t3:#8AA6B5;--t4:#4FB6A4;
--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.4)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5}
.top{padding:20px 24px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}
.top h1{margin:0;font-size:19px;letter-spacing:-.01em}.top .eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);font-weight:600}
.top .meta{font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.layout{display:grid;grid-template-columns:360px 1fr;gap:0;min-height:calc(100vh - 62px)}
@media(max-width:820px){.layout{grid-template-columns:1fr}}
.form{padding:18px 20px;border-right:1px solid var(--line);background:var(--surface2);overflow-y:auto}
.results{padding:18px 22px;overflow-y:auto}
.grp{margin-bottom:16px}.grp h3{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin:0 0 9px;font-weight:600}
label{display:block;font-size:12px;color:var(--muted);margin:9px 0 3px;font-weight:560}
input,select,textarea{width:100%;font-family:var(--sans);font-size:13px;padding:7px 9px;border:1px solid var(--line);
border-radius:8px;background:var(--surface);color:var(--ink)}
input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:transparent}
.row{display:flex;gap:8px}.row>*{flex:1}
.check{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:13px;color:var(--ink)}
.check input{width:auto}
.presets{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.presets button{font-family:var(--mono);font-size:11px;padding:5px 9px;border:1px solid var(--line);background:var(--surface);
color:var(--muted);border-radius:7px;cursor:pointer}.presets button:hover{border-color:var(--accent);color:var(--accent)}
.go{width:100%;margin-top:6px;padding:11px;background:var(--accent);color:var(--accent-ink);border:0;border-radius:9px;
font-size:14px;font-weight:640;cursor:pointer;font-family:var(--sans)}.go:active{transform:translateY(1px)}
details{margin-top:12px}summary{cursor:pointer;font-size:12px;color:var(--muted);font-family:var(--mono)}
textarea{min-height:70px;font-family:var(--mono);font-size:11.5px}
.hint{font-size:11px;color:var(--faint);margin-top:4px}
.rmeta{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:14px;display:flex;flex-wrap:wrap;gap:6px 14px}
.rmeta b{color:var(--ink)}
.tbl-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface);box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;font-size:12.5px}
thead th{font-family:var(--mono);font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--faint);
font-weight:600;text-align:left;padding:9px 11px;border-bottom:1px solid var(--line);white-space:nowrap}
tbody td{padding:10px 11px;border-bottom:1px solid var(--line);vertical-align:middle}tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--surface2)}
.pos{font-family:var(--mono);color:var(--faint);font-size:11px}.who{font-family:var(--mono);font-weight:600;white-space:nowrap}
.reasons{color:var(--muted);font-size:11.5px;max-width:240px}
.chip{display:inline-flex;font-family:var(--mono);font-weight:700;font-size:10.5px;padding:3px 8px;border-radius:6px;border:1px solid;white-space:nowrap}
.t-T0{color:var(--t0);border-color:color-mix(in srgb,var(--t0) 45%,transparent);background:color-mix(in srgb,var(--t0) 12%,transparent)}
.t-T1{color:var(--t1);border-color:color-mix(in srgb,var(--t1) 45%,transparent);background:color-mix(in srgb,var(--t1) 12%,transparent)}
.t-T2{color:var(--t2);border-color:color-mix(in srgb,var(--t2) 45%,transparent);background:color-mix(in srgb,var(--t2) 12%,transparent)}
.t-T3{color:var(--t3);border-color:color-mix(in srgb,var(--t3) 45%,transparent);background:color-mix(in srgb,var(--t3) 14%,transparent)}
.t-T4{color:var(--t4);border-color:color-mix(in srgb,var(--t4) 45%,transparent);background:color-mix(in srgb,var(--t4) 12%,transparent)}
.pill{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;padding:3px 9px;border-radius:999px;white-space:nowrap}
.pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.d-strong_personal{color:var(--pos);background:color-mix(in srgb,var(--pos) 15%,transparent)}
.d-usable_personal{color:var(--pos);background:color-mix(in srgb,var(--pos) 9%,transparent)}
.d-discovery_only{color:var(--info);background:color-mix(in srgb,var(--info) 14%,transparent)}
.d-no_outreach{color:var(--neutral);background:color-mix(in srgb,var(--neutral) 13%,transparent)}
.d-clarification{color:var(--warn);background:color-mix(in srgb,var(--warn) 15%,transparent)}
.rc{display:flex;align-items:center;gap:8px;min-width:92px}.rc .track{flex:1;height:5px;border-radius:3px;background:var(--line);overflow:hidden;min-width:40px}
.rc .fill{height:100%;background:var(--accent)}.rc .n{font-family:var(--mono);font-size:11px;color:var(--muted);width:30px;text-align:right;font-variant-numeric:tabular-nums}
.rd{font-family:var(--mono);font-size:11px;color:var(--muted)}.rd.busy,.rd.paused{color:var(--warn)}.rd.unknown{color:var(--faint)}
.empty{padding:20px;border:1px dashed var(--line);border-radius:12px;color:var(--muted);font-size:13px}
.terminal{border:1px dashed color-mix(in srgb,var(--accent) 40%,var(--line));border-radius:12px;padding:16px 18px;background:color-mix(in srgb,var(--accent) 5%,transparent)}
.terminal .steps{font-family:var(--mono);font-size:12.5px;color:var(--ink);margin:8px 0 12px;line-height:1.9}
.nearby{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--surface)}
.nearby .h{font-size:12.5px;font-weight:640;margin-bottom:3px}.nearby .p{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:8px}
.guard{display:flex;flex-wrap:wrap;gap:6px}.guard span{font-family:var(--mono);font-size:10.5px;padding:3px 8px;border-radius:6px;
background:color-mix(in srgb,var(--warn) 12%,transparent);color:var(--warn);border:1px solid color-mix(in srgb,var(--warn) 28%,transparent)}
.note{font-size:11.5px;color:var(--warn);margin-top:10px}
.err{color:#c0392b;font-family:var(--mono);font-size:12px;padding:12px;border:1px solid #c0392b40;border-radius:10px;background:#c0392b12}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
</style></head><body>
<div class="top">
  <div><div class="eyebrow">Kleal · Matching Core</div><h1>Ручной тест мэтчинга — живой движок</h1></div>
  <div class="meta" id="topmeta">config …</div>
</div>
<div class="layout">
  <div class="form">
    <div class="presets" id="presets"></div>
    <div class="grp"><h3>Интент</h3>
      <label>Тип</label>
      <select id="type"><option>social</option><option>games</option><option>sport</option><option>language</option><option>dating</option><option>networking</option><option>culture</option></select>
      <label>Темы (через запятую)</label><input id="topics" placeholder="coffee, walk">
      <div class="row"><div><label>Режим</label><select id="mode"><option>offline</option><option>online</option><option>hybrid</option></select></div>
      <div><label>Роль</label><input id="role" placeholder="meet / support / native / play"></div></div>
      <div class="row"><div><label>Радиус, км</label><input id="radiusKm" type="number" placeholder="8"></div>
      <div><label>Языки (hard)</label><input id="reqlang" placeholder="es"></div></div>
      <div class="row"><div><label>minAge</label><input id="minAge" type="number" placeholder=""></div>
      <div><label>maxAge</label><input id="maxAge" type="number" placeholder=""></div></div>
      <label>expansion_policy</label>
      <select id="expansion"><option value="">(авто)</option><option>exact_only</option><option>allow_family</option><option>allow_adjacent_after_confirmation</option><option>event_fallback_allowed</option></select>
      <div class="check"><input type="checkbox" id="broad"><label for="broad" style="margin:0">broad_consent (разблокирует T2 в персоналку)</label></div>
    </div>
    <div class="grp"><h3>Профиль «me» (искатель)</h3>
      <label>Интересы</label><input id="me_int" placeholder="coffee">
      <div class="row"><div><label>Вайб</label><input id="me_vibe" placeholder="chill"></div>
      <div><label>Языки</label><input id="me_lang" placeholder="en, es"></div></div>
      <label>Возраст (для dating)</label><input id="me_age" type="number" placeholder="30">
    </div>
    <div class="grp"><h3>Пул</h3>
      <div class="row"><div><label>Размер</label><input id="pool_size" type="number" value="90"></div>
      <div><label>Seed</label><input id="seed" type="number" value="42"></div></div>
      <div class="hint">Один и тот же seed = один и тот же пул (детерминированно).</div>
    </div>
    <details><summary>Добавить своих кандидатов (JSON-массив)</summary>
      <textarea id="extra" placeholder='[{"name":"Custom1","interests":["coffee"],"role":"meet","vibe":"chill","langs":["en"],"km":2,"age":29,"open":true}]'></textarea>
      <div class="hint">Поля: name, interests[], role, vibe, langs[], km, age, open, datingOk, intents[{topics[]}].</div>
    </details>
    <button class="go" id="go">▶ Match</button>
  </div>
  <div class="results" id="results">
    <div class="empty">Собери интент слева и нажми «Match». Пример: type=games, темы=dota2, роль=support, режим=online.</div>
  </div>
</div>
<script>
const $=id=>document.getElementById(id);
const DECISION_LBL={strong_personal:"сильная персоналка",usable_personal:"персоналка",discovery_only:"только подборка",no_outreach:"без исходящего",clarification:"нужно уточнение"};
const STEP_LBL={offer_expansion_consent:"предложить расширение (не молча)",relevant_event_group_room:"событие / группа / комната",background_search:"фоновый поиск",offer_create_open_intent:"создать открытый intent",honest_no_result:"честный no-result"};
const PRESETS={
 "dota2 / support":{type:"games",topics:"dota2",mode:"online",role:"support",me_int:"dota2",me_vibe:"calm",me_lang:"en"},
 "spanish / native":{type:"language",topics:"spanish",mode:"offline",role:"native",radiusKm:10,reqlang:"es",me_int:"spanish",me_vibe:"chill",me_lang:"en, es"},
 "coffee рядом":{type:"social",topics:"coffee",mode:"offline",radiusKm:6,me_int:"coffee",me_vibe:"chill",me_lang:"en"},
 "tennis":{type:"sport",topics:"tennis",mode:"offline",role:"play",radiusKm:12,me_int:"tennis",me_vibe:"competitive",me_lang:"en"},
 "dating":{type:"dating",topics:"coffee",mode:"offline",radiusKm:10,minAge:25,maxAge:40,me_int:"coffee",me_vibe:"social",me_lang:"en",me_age:30},
 "нет пересечения":{type:"social",topics:"astrophotography",mode:"offline",radiusKm:8,expansion:"event_fallback_allowed",me_int:"astrophotography",me_vibe:"calm",me_lang:"en"}
};
function applyPreset(p){
 const d=PRESETS[p];["type","topics","mode","role","radiusKm","reqlang","minAge","maxAge","expansion","me_int","me_vibe","me_lang","me_age"].forEach(k=>{if($( k))$(k).value="";});
 $("broad").checked=false;
 for(const k in d){const el=$(k);if(el)el.value=d[k];}
 run();
}
(function(){const box=$("presets");Object.keys(PRESETS).forEach(p=>{const b=document.createElement("button");b.textContent=p;b.onclick=()=>applyPreset(p);box.append(b);});})();
function csv(v){return (v||"").split(",").map(s=>s.trim()).filter(Boolean);}
function buildReq(){
 const intent={type:$("type").value,topics:csv($("topics").value),mode:$("mode").value};
 if($("role").value)intent.role=$("role").value.trim();
 if($("radiusKm").value)intent.radiusKm=parseFloat($("radiusKm").value);
 if($("reqlang").value)intent.requiredLanguages=csv($("reqlang").value);
 if($("minAge").value)intent.minAge=parseInt($("minAge").value);
 if($("maxAge").value)intent.maxAge=parseInt($("maxAge").value);
 if($("expansion").value)intent.expansion_policy=$("expansion").value;
 const me={name:"me",interests:csv($("me_int").value)};
 if($("me_vibe").value)me.vibe=$("me_vibe").value.trim();
 if($("me_lang").value)me.langs=csv($("me_lang").value);
 if($("me_age").value)me.age=parseInt($("me_age").value);
 let extra=[];try{if($("extra").value.trim())extra=JSON.parse($("extra").value);}catch(e){}
 return {intent,me,broad_consent:$("broad").checked,pool_size:parseInt($("pool_size").value)||90,seed:parseInt($("seed").value)||42,extra_candidates:extra};
}
function bar(v){const pct=Math.round((v||0)*100);return `<div class="rc"><div class="track"><div class="fill" style="width:${pct}%"></div></div><span class="n">${(v||0).toFixed(2)}</span></div>`;}
function render(d){
 const R=$("results");
 if(d.error){R.innerHTML=`<div class="err">Ошибка: ${d.error}</div>`;return;}
 let meta=`<div class="rmeta"><span>purpose <b>${d.purpose}</b></span><span>пул <b>${d.pool_size}</b></span><span>config <b>${d.config_version}</b></span><span>traces <b>${d.traces}</b></span><span>показано <b>${d.slate.length}</b></span></div>`;
 if(d.slate.length){
  let rows=d.slate.map(s=>`<tr><td class="pos">${s.allocation?s.allocation.position+1:""}</td>
   <td class="who">${s.name}</td>
   <td><span class="chip t-${s.tier}">${s.tier}</span></td>
   <td>${s.band_label}</td>
   <td><span class="pill d-${s.decision_class}">${DECISION_LBL[s.decision_class]||s.decision_class}</span></td>
   <td>${bar(s.reciprocal)}</td>
   <td class="rd ${s.readiness}">${s.readiness}</td>
   <td class="reasons">${(s.reasons||[]).slice(0,2).join(" · ")}${s.gap?` <span style="color:var(--faint)">· gap: ${s.gap}</span>`:""}</td></tr>`).join("");
  R.innerHTML=meta+`<div class="tbl-scroll"><table><thead><tr><th>#</th><th>человек</th><th>tier</th><th>band</th><th>decision</th><th>reciprocal</th><th>readiness</th><th>причины / gap</th></tr></thead><tbody>${rows}</tbody></table></div>`
   +($("type").value==="dating"?`<div class="note">Dating изолирован: даже при высокой релевантности decision может быть «без исходящего» — строгие пороги, без авто-персоналки (§17).</div>`:"");
 } else if(d.terminal && d.terminal.kind==="no_overlap"){
  const t=d.terminal,nb=t.nearby_open_block;
  R.innerHTML=meta+`<div class="terminal"><b>Тематического пересечения нет — случайного человека не подсовываем (T5 ≠ персоналка).</b>
   <div class="steps">${t.steps.map((s,i)=>`${i+1}. ${STEP_LBL[s]||s}`).join("<br>")}</div>
   ${nb?`<div class="nearby"><div class="h">${nb.title_ru}</div><div class="p">${nb.members.join(" · ")}</div>
   <div class="guard"><span>⛔ личное приглашение запрещено</span><span>↻ нужно новое подтверждение</span><span>▚ отделено от результатов intent</span></div></div>`:""}</div>`;
 } else if(d.terminal && d.terminal.kind==="all_gated"){
  R.innerHTML=meta+`<div class="terminal"><b>Тематически подходящих было ${d.terminal.retrieved}, но ВСЕ отсечены гейтами</b> (например dating-изоляция: нужен явный datingOk + возраст в диапазоне; или приватность/блок/возраст). Персоналки нет — это корректно.</div>`;
 } else {
  R.innerHTML=meta+`<div class="empty">Пусто.</div>`;
 }
}
async function run(){
 $("results").innerHTML=`<div class="empty">Считаю…</div>`;
 try{
  const r=await fetch("/api/match",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(buildReq())});
  render(await r.json());
 }catch(e){$("results").innerHTML=`<div class="err">Сеть: ${e}</div>`;}
}
$("go").onclick=run;
fetch("/api/pool?size=1").then(r=>r.json()).catch(()=>({}));
$("topmeta").textContent="config "+"''' + str(CFG.get("config_version")) + r'''"+" · deterministic · no-LLM";
</script></body></html>'''


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT") or 7099)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Matching Core manual tester -> http://127.0.0.1:%d   (config %s)" % (port, CFG.get("config_version")))
    print("Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
