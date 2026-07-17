# -*- coding: utf-8 -*-
# Kleal admin-service — an admin panel to view / add / edit / delete the platform's users while the app
# runs in TEST MODE. It runs on its OWN address (a separate cloudflared tunnel, not behind the main
# gateway). Users are stored in a shared JSON file (KLEAL_USERS) that the matching agent reads, so admin
# edits directly change who gets matched. Seeds itself once from the matching agent's demo pool.
#
# NO auth: protection is the obscure/separate URL only (test-mode tool). Holds no model keys.
import os
import sys
import json
import uuid
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
from http_util import send, send_json, read_json

PORT = int(os.environ.get("ADMIN_PORT", "7077"))
MATCH_URL = os.environ.get("MATCH_URL", "http://127.0.0.1:7074").rstrip("/")
STORE = os.environ.get("KLEAL_USERS", os.path.join(_HERE, "..", "matching", "users.json"))
_LOCK = threading.Lock()
_seeded = {"done": False}

VIBES = ["calm", "energetic", "intellectual", "creative", "competitive", "chill", "social", "introvert", "extrovert"]
ROLES = ["play", "watch", "discuss", "practise", "attend", "meet"]


# ---------------- user normalisation (every stored user is complete + matching-safe) ----------------
def _as_list(v):
    """Single-token list (interests, languages, topics) — split on commas AND whitespace."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.replace(",", " ").split() if x.strip()]
    return []


def _as_phrases(v):
    """Multi-word phrase list (deal-breakers, communities) — split ONLY on commas."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def _norm_user(u, keep_id=None):
    u = u or {}

    def _int(v, d):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return d

    interests = [x.lower() for x in _as_list(u.get("interests"))] or ["coffee"]
    langs = [x.lower()[:2] for x in _as_list(u.get("langs") or u.get("languages"))] or ["en"]
    try:
        km = round(float(u.get("km", 2.0)), 1)
    except (TypeError, ValueError):
        km = 2.0
    vibe = str(u.get("vibe") or "chill").lower()
    role = str(u.get("role") or "meet").lower()
    deal = _as_phrases(u.get("dealBreakers"))[:6]
    ents = _as_phrases(u.get("entities"))[:6] or [interests[0].capitalize() + " scene"]
    # own active intent -> makes this person a RECIPROCAL (T0) match. From an `intents` list, or the form's ownIntent* fields.
    intents = u.get("intents") if isinstance(u.get("intents"), list) else []
    oi_topics = [t.lower() for t in _as_list(u.get("ownIntentTopics"))][:3]
    if oi_topics:
        oi_type = str(u.get("ownIntentType") or "social").lower()
        oi_role = str(u.get("ownIntentRole") or "meet").lower()
        intents = [{"type": oi_type, "topics": oi_topics, "role": oi_role if oi_role in ROLES else "meet"}]
    dcd = u.get("declinedOwnerDaysAgo")
    dcd = int(dcd) if str(dcd).strip().lstrip("-").isdigit() else None
    out = {
        "id": keep_id or u.get("id") or ("u" + uuid.uuid4().hex[:8]),
        "name": (str(u.get("name") or "").strip() or "User"),
        "interests": interests[:6],
        "vibe": vibe if vibe in VIBES else "chill",
        "langs": langs[:4],
        "area": str(u.get("area") or "").strip(),
        "km": km, "lat": u.get("lat"), "lon": u.get("lon"),
        "open": bool(u.get("open", True)),
        "role": role if role in ROLES else "meet",
        "datingOk": bool(u.get("datingOk", False)),
        "age": _int(u.get("age", 28), 28),
        "verified": bool(u.get("verified", True)),
        "paused": bool(u.get("paused", False)),
        "pending": _int(u.get("pending"), 0),
        "blocksMe": bool(u.get("blocksMe", False)),
        "lastActiveDays": _int(u.get("lastActiveDays"), 0),
        "declinedOwnerDaysAgo": dcd,
        "intents": intents,
        "entities": ents,
        "dealBreakers": deal,
    }
    # Preserve fields this form doesn't know about — receiving policy (matching's readiness engine
    # reads it), geo, tags, source, summary... An admin edit/toggle must never silently strip data
    # that other services own.
    for k, v in (u or {}).items():
        if k not in out:
            out[k] = v
    return out


# ---------------- store (atomic writes) ----------------
def _read():
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        lst = data.get("users") if isinstance(data, dict) else data
        return lst if isinstance(lst, list) else []
    except Exception:
        return []


def _write(users):
    tmp = STORE + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(STORE)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False)
    os.replace(tmp, STORE)


def _seed_if_empty():
    """First run: pull the matching agent's demo pool so admins have something to curate."""
    if _seeded["done"] or os.path.exists(STORE):
        _seeded["done"] = True
        return
    users = []
    try:
        with urllib.request.urlopen(MATCH_URL + "/api/agent/pool", timeout=8) as r:
            users = (json.loads(r.read().decode("utf-8")) or {}).get("users") or []
    except Exception:
        users = []
    users = [_norm_user(u, keep_id=u.get("id")) for u in users]
    with _LOCK:
        if not os.path.exists(STORE):
            _write(users)
    _seeded["done"] = True


def list_users():
    _seed_if_empty()
    return _read()


def add_user(u):
    with _LOCK:
        users = _read()
        nu = _norm_user(u)
        users.append(nu)
        _write(users)
        return nu


def update_user(uid, patch):
    with _LOCK:
        users = _read()
        for i, u in enumerate(users):
            if u.get("id") == uid:
                merged = dict(u)
                merged.update(patch or {})
                users[i] = _norm_user(merged, keep_id=uid)
                _write(users)
                return users[i]
    return None


def delete_user(uid):
    with _LOCK:
        users = _read()
        n = len(users)
        users = [u for u in users if u.get("id") != uid]
        if len(users) != n:
            _write(users)
            return True
    return False


def clear_users():
    """Remove ALL users — leaves an empty (but present) store, so matching sees an empty system."""
    with _LOCK:
        _write([])
    return True


def _path(handler):
    return handler.path.split("?", 1)[0]


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        p = _path(self)
        if p == "/admin" or p == "/admin/" or p == "/":
            send(self, 200, HTML, "text/html")
        elif p == "/api/admin/ping":
            send_json(self, 200, {"ok": True})
        elif p == "/api/admin/users":
            u = list_users()
            send_json(self, 200, {"count": len(u), "users": u})
        else:
            send_json(self, 404, {})

    def do_POST(self):
        p = _path(self)
        body = read_json(self)
        if p == "/api/admin/users":
            send_json(self, 200, {"ok": True, "user": add_user(body)})
        elif p.startswith("/api/admin/user/") and p.endswith("/delete"):
            uid = p[len("/api/admin/user/"):-len("/delete")]
            send_json(self, 200, {"ok": delete_user(uid)})
        elif p.startswith("/api/admin/user/"):
            uid = p[len("/api/admin/user/"):]
            u = update_user(uid, body)
            send_json(self, 200 if u else 404, {"ok": bool(u), "user": u})
        elif p == "/api/admin/clear":
            send_json(self, 200, {"ok": clear_users(), "count": 0})
        elif p == "/api/admin/reseed":
            with _LOCK:
                try:
                    os.remove(STORE)
                except OSError:
                    pass
            _seeded["done"] = False
            send_json(self, 200, {"ok": True, "count": len(list_users())})
        else:
            send_json(self, 404, {})

    def log_message(self, *a):
        pass


HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Kleal Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;background:#f6f7f9;color:#181b22}
.top{background:#fff;border-bottom:1px solid #e7e8ec;padding:14px 22px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:5}
.logo{font-weight:800;color:#f5455c;font-size:20px;letter-spacing:-.02em}
.pill{font-size:12px;color:#6b7180;background:#f1f2f5;border-radius:20px;padding:3px 10px}
.wrap{max-width:1180px;margin:22px auto;padding:0 22px}
.card{background:#fff;border:1px solid #e7e8ec;border-radius:14px;padding:18px;margin-bottom:18px;box-shadow:0 1px 2px rgba(20,20,40,.04)}
h2{font-size:15px;margin-bottom:12px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}
label{display:block;font-size:12px;color:#6b7180;margin-bottom:4px}
input,select{border:1px solid #dfe1e7;border-radius:9px;padding:8px 10px;font:inherit;background:#fff;min-width:120px}
input:focus,select:focus{outline:none;border-color:#f5455c}
button{border:none;border-radius:9px;padding:9px 14px;font:inherit;font-weight:600;cursor:pointer;background:#f5455c;color:#fff}
button.ghost{background:#f1f2f5;color:#181b22}
button.mini{padding:4px 9px;font-size:12px;font-weight:600}
button.danger{background:#fdecee;color:#e5384f}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid #eef0f3;white-space:nowrap}
th{color:#8a909c;font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.03em}
td.wrap2{white-space:normal;max-width:220px}
.flag{display:inline-block;width:22px;height:22px;border-radius:6px;text-align:center;line-height:22px;cursor:pointer;font-size:12px;user-select:none;background:#f1f2f5;color:#b7bcc6}
.flag.on{background:#e9f9f0;color:#1f9d57}
.flag.warn.on{background:#fff2e8;color:#d9700f}
.tag{display:inline-block;background:#fde7eb;color:#c32b40;border-radius:6px;padding:1px 7px;margin:1px 3px 1px 0;font-size:11.5px}
.muted{color:#8a909c}
.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap}
.search{min-width:220px}
.gate{max-width:360px;margin:12vh auto;text-align:center}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#181b22;color:#fff;padding:9px 16px;border-radius:10px;opacity:0;transition:.2s;pointer-events:none;font-size:13px}
.toast.show{opacity:1}
.tabler{overflow-x:auto}
.sec{font-size:11px;color:#8a909c;text-transform:uppercase;letter-spacing:.04em;margin:16px 0 6px;font-weight:700}
.chk{display:flex;align-items:center;gap:6px;margin:0;font-size:13px}
.chk input{min-width:auto}
.adv{border-top:1px dashed #e7e8ec;margin-top:14px;padding-top:6px}
.advtog{cursor:pointer;color:#f5455c;font-size:12px;font-weight:600;user-select:none}
</style></head><body>
<div id="app"></div>
<div class="toast" id="toast"></div>
<script>
let TOK=sessionStorage.getItem('kleal_admin_tok')||'', USERS=[], Q='', editing=null;
const $=s=>document.querySelector(s), esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),1800);}
async function api(path,opts){opts=opts||{};opts.headers=Object.assign({'Content-Type':'application/json','X-Admin-Token':TOK},opts.headers||{});const r=await fetch(path,opts);if(r.status===401){TOK='';sessionStorage.removeItem('kleal_admin_tok');render();throw new Error('unauthorized');}return r.json();}
const VIBES=["calm","energetic","intellectual","creative","competitive","chill","social","introvert","extrovert"];
const ROLES=["play","watch","discuss","practise","attend","meet"];

async function load(){const r=await api('/api/admin/users');USERS=r.users||[];render();}
const gv=id=>{const e=$(id);return e?e.value:'';}, gc=id=>{const e=$(id);return e?e.checked:false;};
async function saveUser(){
  const u={name:gv('#f_name'),age:+gv('#f_age')||28,area:gv('#f_area'),interests:gv('#f_int'),vibe:gv('#f_vibe'),
    langs:gv('#f_lang'),km:+gv('#f_km')||2,role:gv('#f_role'),
    dealBreakers:gv('#f_deal'),entities:gv('#f_ent'),
    ownIntentType:gv('#f_oit'),ownIntentTopics:gv('#f_oitop'),ownIntentRole:gv('#f_oirole'),
    open:gc('#f_open'),verified:gc('#f_ver'),datingOk:gc('#f_dat'),paused:gc('#f_pau'),blocksMe:gc('#f_blk'),
    pending:+gv('#f_pend')||0,lastActiveDays:+gv('#f_last')||0,declinedOwnerDaysAgo:gv('#f_cool')};
  if(!u.name.trim()){toast('Name required');return;}
  if(editing){await api('/api/admin/user/'+editing,{method:'POST',body:JSON.stringify(u)});toast('Updated');}
  else{await api('/api/admin/users',{method:'POST',body:JSON.stringify(u)});toast('User added');}
  editing=null;await load();
}
function editRow(id){const u=USERS.find(x=>x.id===id);if(!u)return;editing=id;render();setTimeout(()=>{
  const sv=(id,val)=>{const e=$(id);if(e)e.value=(val==null?'':val);}, sc=(id,val)=>{const e=$(id);if(e)e.checked=!!val;};
  sv('#f_name',u.name);sv('#f_age',u.age);sv('#f_area',u.area);sv('#f_int',(u.interests||[]).join(', '));
  sv('#f_vibe',u.vibe);sv('#f_lang',(u.langs||[]).join(', '));sv('#f_km',u.km);sv('#f_role',u.role);
  sv('#f_deal',(u.dealBreakers||[]).join(', '));sv('#f_ent',(u.entities||[]).join(', '));
  const oi=(u.intents||[])[0]||{};sv('#f_oit',oi.type||'social');sv('#f_oitop',(oi.topics||[]).join(', '));sv('#f_oirole',oi.role||'meet');
  sc('#f_open',u.open);sc('#f_ver',u.verified);sc('#f_dat',u.datingOk);sc('#f_pau',u.paused);sc('#f_blk',u.blocksMe);
  sv('#f_pend',u.pending);sv('#f_last',u.lastActiveDays);sv('#f_cool',u.declinedOwnerDaysAgo);
  window.scrollTo(0,0);},0);}
function toggleAdv(){const a=$('#advbox');if(a)a.style.display=(a.style.display==='none'?'block':'none');}
async function delRow(id){const u=USERS.find(x=>x.id===id);if(!confirm('Delete '+(u?u.name:'user')+'?'))return;await api('/api/admin/user/'+id+'/delete',{method:'POST'});toast('Deleted');await load();}
async function toggle(id,field){const u=USERS.find(x=>x.id===id);if(!u)return;await api('/api/admin/user/'+id,{method:'POST',body:JSON.stringify({[field]:!u[field]})});await load();}
async function reseed(){if(!confirm('Reset the user list to the demo pool? This replaces all users.'))return;const r=await api('/api/admin/reseed',{method:'POST'});toast('Reseeded '+r.count+' users');await load();}
async function clearAll(){if(!confirm('Delete ALL users? The system will have no people until you add some. This cannot be undone.'))return;await api('/api/admin/clear',{method:'POST'});toast('All users deleted');await load();}

function gate(){
  $('#app').innerHTML=`<div class="top"><span class="logo">kleal</span><span class="pill">admin · test mode</span></div>
    <div class="gate card"><h2>Admin sign-in</h2><p class="muted" style="margin-bottom:12px">Enter the admin token.</p>
    <input id="tok" type="password" placeholder="Admin token" style="width:100%;margin-bottom:10px"><br>
    <button onclick="tryLogin()">Enter</button></div>`;
  setTimeout(()=>{const i=$('#tok');i.focus();i.onkeydown=e=>{if(e.key==='Enter')tryLogin();};},0);
}
async function tryLogin(){TOK=$('#tok').value.trim();const r=await fetch('/api/admin/ping',{headers:{'X-Admin-Token':TOK}}).then(x=>x.json()).catch(()=>({}));
  if(r&&r.ok){sessionStorage.setItem('kleal_admin_tok',TOK);load();}else{toast('Wrong token');}}

function render(){
  const q=Q.toLowerCase();
  const rows=USERS.filter(u=>!q||(u.name+' '+(u.interests||[]).join(' ')+' '+u.vibe).toLowerCase().includes(q));
  const flag=(u,f,label,warn)=>`<span class="flag ${warn?'warn':''} ${u[f]?'on':''}" title="${label}" onclick="toggle('${u.id}','${f}')">${u[f]?(warn?'❚':'✓'):'·'}</span>`;
  $('#app').innerHTML=`<div class="top"><span class="logo">kleal</span><span class="pill">admin · test mode</span>
    <span class="muted" style="margin-left:auto">${USERS.length} users</span>
    <button class="ghost mini" onclick="reseed()">Reset to demo pool</button>
    <button class="danger mini" onclick="clearAll()">Delete all users</button></div>
  <div class="wrap">
    <div class="card"><h2>${editing?'Edit user':'Add user'}</h2>

      <div class="sec">Basics &amp; location</div>
      <div class="row">
        <div><label>Name</label><input id="f_name"></div>
        <div><label>Age</label><input id="f_age" type="number" style="min-width:74px" value="28"></div>
        <div><label>Area / city</label><input id="f_area" style="min-width:130px" placeholder="Barcelona"></div>
        <div><label>Distance km</label><input id="f_km" type="number" step="0.1" style="min-width:90px" value="2"></div>
        <div><label>Languages</label><input id="f_lang" style="min-width:110px" placeholder="en, es" value="en"></div>
      </div>

      <div class="sec">Interests &amp; personality</div>
      <div class="row">
        <div style="flex:1;min-width:220px"><label>Interests (comma)</label><input id="f_int" style="width:100%" placeholder="chess, coffee"></div>
        <div><label>Preferred role</label><select id="f_role">${ROLES.map(v=>`<option>${v}</option>`).join('')}</select></div>
        <div><label>Vibe</label><select id="f_vibe">${VIBES.map(v=>`<option>${v}</option>`).join('')}</select></div>
        <div style="flex:1;min-width:200px"><label>Communities (comma)</label><input id="f_ent" style="width:100%" placeholder="Casa del Chess club"></div>
      </div>

      <div class="sec">Active intent — makes them a reciprocal (T0) match</div>
      <div class="row">
        <div><label>Intent type</label><select id="f_oit"><option value="">— none —</option>${['sport','gaming','networking','language','dating','social','other'].map(v=>`<option>${v}</option>`).join('')}</select></div>
        <div style="flex:1;min-width:220px"><label>Intent topics (comma)</label><input id="f_oitop" style="width:100%" placeholder="chess (leave blank for no active intent)"></div>
        <div><label>Intent role</label><select id="f_oirole">${ROLES.map(v=>`<option>${v}</option>`).join('')}</select></div>
      </div>

      <div class="sec">Safety &amp; matching flags</div>
      <div class="row">
        <label class="chk"><input id="f_open" type="checkbox" checked> open to meet</label>
        <label class="chk"><input id="f_ver" type="checkbox" checked> verified</label>
        <label class="chk"><input id="f_dat" type="checkbox"> dating opt-in</label>
        <label class="chk"><input id="f_pau" type="checkbox"> paused</label>
        <div style="flex:1;min-width:200px"><label>Deal-breakers (comma)</label><input id="f_deal" style="width:100%" placeholder="no smokers, no late nights"></div>
      </div>

      <div class="adv"><span class="advtog" onclick="toggleAdv()">▸ Advanced state (anti-spam / activity)</span>
        <div id="advbox" style="display:none;margin-top:10px"><div class="row">
          <div><label>Open invites (pending)</label><input id="f_pend" type="number" style="min-width:120px" value="0" title="≥6 = overloaded, gated out"></div>
          <div><label>Last active (days ago)</label><input id="f_last" type="number" style="min-width:130px" value="0" title="≤3 = 'recently active' bonus"></div>
          <div><label>Declined me (days ago)</label><input id="f_cool" type="number" style="min-width:150px" placeholder="blank = no" title="<7 = cooldown, gated out"></div>
          <label class="chk" style="align-self:end;padding-bottom:8px"><input id="f_blk" type="checkbox"> blocks me</label>
        </div></div>
      </div>

      <div class="row" style="margin-top:14px;justify-content:flex-end">
        ${editing?`<button class="ghost" onclick="editing=null;render()">Cancel</button>`:''}
        <button onclick="saveUser()">${editing?'Save changes':'Add user'}</button>
      </div>
    </div>
    <div class="card">
      <div class="bar"><h2 style="margin:0">Users</h2>
        <input class="search" placeholder="Search name / interest / vibe…" value="${esc(Q)}" oninput="Q=this.value;render()"></div>
      <div class="tabler"><table>
        <thead><tr><th>Name</th><th>Age</th><th>Area</th><th>Interests</th><th>Vibe</th><th>Langs</th><th>km</th><th>Role</th>
          <th title="open">Op</th><th title="verified">Vf</th><th title="dating">Dt</th><th title="paused">Pa</th><th></th></tr></thead>
        <tbody>${rows.map(u=>`<tr>
          <td><b>${esc(u.name)}</b>${(u.intents||[]).length?'<span class="tag" title="has an active intent — reciprocal match" style="background:#e9f9f0;color:#1f9d57">↔</span>':''}</td><td>${u.age}</td>
          <td class="muted">${esc(u.area||'—')}</td>
          <td class="wrap2">${(u.interests||[]).map(i=>`<span class="tag">${esc(i)}</span>`).join('')}</td>
          <td>${esc(u.vibe)}</td><td class="muted">${(u.langs||[]).join(', ')}</td><td>${u.km}</td><td class="muted">${esc(u.role)}</td>
          <td>${flag(u,'open','open to meet')}</td><td>${flag(u,'verified','verified')}</td>
          <td>${flag(u,'datingOk','dating opt-in')}</td><td>${flag(u,'paused','paused',true)}</td>
          <td style="text-align:right"><button class="ghost mini" onclick="editRow('${u.id}')">Edit</button>
            <button class="danger mini" onclick="delRow('${u.id}')">Delete</button></td></tr>`).join('')
          ||`<tr><td colspan="13" class="muted" style="padding:22px;text-align:center">No users. Add one above or reset to the demo pool.</td></tr>`}
        </tbody></table></div>
    </div>
    <p class="muted" style="font-size:12px">Changes take effect for the matching agent within a few seconds (shared user store). Test mode.</p>
  </div>`;
}
load().catch(()=>toast('Load failed — is the server up?'));
</script></body></html>'''


if __name__ == "__main__":
    print("Kleal admin-service on http://127.0.0.1:%d  (store=%s, seed from %s)" % (PORT, STORE, MATCH_URL))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
