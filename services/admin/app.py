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
import kleal_contracts as kc              # §4 canonical data contracts (ReceivingPolicy + UserProfile builders)

PORT = int(os.environ.get("ADMIN_PORT", "7077"))
MATCH_URL = os.environ.get("MATCH_URL", "http://127.0.0.1:7074").rstrip("/")
STORE = os.environ.get("KLEAL_USERS", os.path.join(_HERE, "..", "matching", "users.json"))
_LOCK = threading.Lock()
_seeded = {"done": False}

VIBES = ["calm", "energetic", "intellectual", "creative", "competitive", "chill", "social", "introvert", "extrovert"]
ROLES = ["play", "watch", "discuss", "practise", "attend", "meet"]

# ---- canonical profile-card schema: the 139 slots + 65 context profiles from the global taxonomy ----
# Source of truth: data/taxonomy/{slots,context_profiles}.json (extracted from
# Kleal_Global_Context_Profiles_Intent_Taxonomy_RU_v1.xlsx). The profile card is DEFINED by this data:
# per-domain slots (type / required / hard-soft / unknown_behavior / question RU-EN-ES) grouped into
# context profiles (disclosure profile + 10 dials + gates). We load it once; empty if the files are absent.
_TAXO_DIR = os.path.join(_HERE, "..", "..", "data", "taxonomy")


def _load_json(name, default):
    try:
        with open(os.path.join(_TAXO_DIR, name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


SLOTS = _load_json("slots.json", [])                       # 139 slot definitions
CTX_PROFILES = _load_json("context_profiles.json", [])     # 65 context profiles
SLOTS_BY_DOMAIN = {}
for _s in SLOTS:
    SLOTS_BY_DOMAIN.setdefault(_s.get("domain"), []).append(_s)


def profile_schema():
    """The canonical profile-card schema the UI/onboarding drives off: per-domain slots + context profiles."""
    return {
        "slots_by_domain": SLOTS_BY_DOMAIN,
        "domains": sorted(SLOTS_BY_DOMAIN),
        "context_profiles": CTX_PROFILES,
        "counts": {"slots": len(SLOTS), "context_profiles": len(CTX_PROFILES),
                   "domains": len(SLOTS_BY_DOMAIN)},
    }


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


def _receiving_from_form(u):
    """Map the editor's rcv* fields into the canonical §4.4 receiving policy, or None. Delegates to the
    shared contract builder kc.build_receiving_policy, which preserves the EXACT None-return semantics
    (a full save carries rcvStatus and can clear the policy by blanking everything; a partial patch never
    carries rcvStatus and passes the stored `receiving` through) and adds the new §4.4 fields
    (location_scope / allowed_proposal_types / disclosure_stage / per_7d / paused_until) omitted-when-unset."""
    return kc.build_receiving_policy(u)


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
    # social formats they accept (online/offline/1:1/group/any) -> lets mode_format reach a known state
    formats = [x.lower() for x in _as_list(u.get("formats"))][:5]
    rcv = _receiving_from_form(u)                            # editor rcv* fields -> receiving policy (§4.4) or None
    return kc.build_user_profile({
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
        "formats": formats,
        "receiving": rcv,
        # canonical profile-card slot values (spec slots.json), kept as {slot_name: value}
        "slots": u.get("slots") if isinstance(u.get("slots"), dict) else {},
    })


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


def match_call(payload, path="/api/agent/match"):
    """Forward a structured request to the matching agent (deterministic scorer, no LLM). `path` is
    /api/agent/match for the ranked slate or /api/agent/explain for the full diagnostic (matched +
    gated-out + per-feature breakdown) — lets an admin test who matches, why, and how the ranking
    reacts to a changed parameter."""
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(MATCH_URL + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _path(handler):
    return handler.path.split("?", 1)[0]


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        p = _path(self)
        if p == "/admin" or p == "/admin/" or p == "/":
            send(self, 200, HTML, "text/html")
        elif p == "/api/admin/ping":
            send_json(self, 200, {"ok": True})
        elif p == "/api/admin/schema":
            send_json(self, 200, profile_schema())          # canonical profile-card schema (slots + context profiles)
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
        elif p == "/api/admin/match":
            try:
                send_json(self, 200, match_call(body, "/api/agent/match"))
            except Exception as e:
                send_json(self, 502, {"candidates": [], "error": "matching agent unreachable: " + str(e)[:160]})
        elif p == "/api/admin/explain":
            try:
                send_json(self, 200, match_call(body, "/api/agent/explain"))
            except Exception as e:
                send_json(self, 502, {"matched": [], "excluded": [], "considered": [], "error": "matching agent unreachable: " + str(e)[:160]})
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
.chk.end{align-self:end;padding-bottom:8px}
.chk input{min-width:auto}
.adv{border-top:1px dashed #e7e8ec;margin-top:14px;padding-top:6px}
.advtog{cursor:pointer;color:#f5455c;font-size:12px;font-weight:600;user-select:none}
/* matching lab */
.lab-sec{font-size:11px;color:#8a909c;text-transform:uppercase;letter-spacing:.04em;margin:14px 0 6px;font-weight:700}
.tnum{font-variant-numeric:tabular-nums}
.dombar{display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px}
.dombar .gname{width:158px;color:#6b7180;flex:none}
.dombar .track2{flex:1;height:8px;background:#eef0f3;border-radius:5px;overflow:hidden}
.dombar .fill2{display:block;height:100%;background:#aeb9ff;border-radius:5px}
.dombar .wv{width:40px;text-align:right;color:#8a909c;font-variant-numeric:tabular-nums}
.stchip{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 6px;border-radius:5px;white-space:nowrap}
.st-known_match{background:#e9f9f0;color:#1f9d57}
.st-known_mismatch{background:#fdeceb;color:#d94c3d}
.st-unknown{background:#eef0f3;color:#8a909c}
.st-not_applicable{background:#f6f7f9;color:#b7bcc6}
.exrow{cursor:pointer}
.exrow:hover{background:#fafbfc}
.det>td{background:#fafbfc;border-top:1px dashed #e7e8ec}
.fgtab{width:100%;border-collapse:collapse;font-size:12px;margin:2px 0}
.fgtab td{padding:4px 7px;border-bottom:1px solid #f0f1f4;white-space:nowrap}
.fgtab thead td{color:#8a909c;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.03em}
.cbar{display:inline-block;height:7px;background:#aeb9ff;border-radius:4px;vertical-align:middle;min-width:1px}
.mathline{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:12px;color:#4a505c;background:#f1f2f5;padding:6px 10px;border-radius:7px;margin:2px 0 8px;display:inline-block}
.collap{cursor:pointer;color:#6b7180;font-weight:600;font-size:12.5px;user-select:none;margin-top:14px;display:block}
.collap:hover{color:#181b22}
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

async function load(){const r=await api('/api/admin/users');USERS=r.users||[];await loadSchema();render();}
const gv=id=>{const e=$(id);return e?e.value:'';}, gc=id=>{const e=$(id);return e?e.checked:false;};
async function saveUser(){
  const u={name:gv('#f_name'),age:+gv('#f_age')||28,area:gv('#f_area'),interests:gv('#f_int'),vibe:gv('#f_vibe'),
    langs:gv('#f_lang'),km:+gv('#f_km')||2,role:gv('#f_role'),formats:gv('#f_fmt'),
    dealBreakers:gv('#f_deal'),entities:gv('#f_ent'),
    ownIntentType:gv('#f_oit'),ownIntentTopics:gv('#f_oitop'),ownIntentRole:gv('#f_oirole'),
    open:gc('#f_open'),verified:gc('#f_ver'),datingOk:gc('#f_dat'),paused:gc('#f_pau'),blocksMe:gc('#f_blk'),
    pending:+gv('#f_pend')||0,lastActiveDays:+gv('#f_last')||0,declinedOwnerDaysAgo:gv('#f_cool'),
    rcvStatus:gv('#f_rst'),rcvPassive:gc('#f_rpas'),rcvDomains:gv('#f_rdom'),
    rcvQuietStart:gv('#f_rqs'),rcvQuietEnd:gv('#f_rqe'),rcvPer24:gv('#f_r24'),
    rcvPer7d:gv('#f_r7d'),rcvLocationScope:gv('#f_rloc'),rcvProposalTypes:gv('#f_rpt'),
    rcvDisclosureStage:gv('#f_rds'),rcvPausedUntil:gv('#f_rpu')};
  if(!u.name.trim()){toast('Name required');return;}
  if(editing){await api('/api/admin/user/'+editing,{method:'POST',body:JSON.stringify(u)});toast('Updated');}
  else{await api('/api/admin/users',{method:'POST',body:JSON.stringify(u)});toast('User added');}
  editing=null;await load();
}
function editRow(id){const u=USERS.find(x=>x.id===id);if(!u)return;editing=id;render();setTimeout(()=>{
  const sv=(id,val)=>{const e=$(id);if(e)e.value=(val==null?'':val);}, sc=(id,val)=>{const e=$(id);if(e)e.checked=!!val;};
  sv('#f_name',u.name);sv('#f_age',u.age);sv('#f_area',u.area);sv('#f_int',(u.interests||[]).join(', '));
  sv('#f_vibe',u.vibe);sv('#f_lang',(u.langs||[]).join(', '));sv('#f_km',u.km);sv('#f_role',u.role);
  sv('#f_deal',(u.dealBreakers||[]).join(', '));sv('#f_ent',(u.entities||[]).join(', '));sv('#f_fmt',(u.formats||[]).join(', '));
  const oi=(u.intents||[])[0]||{};sv('#f_oit',oi.type||'social');sv('#f_oitop',(oi.topics||[]).join(', '));sv('#f_oirole',oi.role||'meet');
  sc('#f_open',u.open);sc('#f_ver',u.verified);sc('#f_dat',u.datingOk);sc('#f_pau',u.paused);sc('#f_blk',u.blocksMe);
  sv('#f_pend',u.pending);sv('#f_last',u.lastActiveDays);sv('#f_cool',u.declinedOwnerDaysAgo);
  const rc=u.receiving||{};sv('#f_rst',rc.status||'');sc('#f_rpas',rc.passive_outreach!==false);
  sv('#f_rdom',(rc.allowed_domains||[]).join(', '));sv('#f_rqs',(rc.quiet_hours||{}).start||'');
  sv('#f_rqe',(rc.quiet_hours||{}).end||'');sv('#f_r24',(rc.proposal_budget||{}).per_24h);
  sv('#f_r7d',(rc.proposal_budget||{}).per_7d);sv('#f_rloc',(rc.location_scope||[]).join(', '));
  sv('#f_rpt',(rc.allowed_proposal_types||[]).join(', '));sv('#f_rds',rc.disclosure_stage||'');sv('#f_rpu',rc.paused_until||'');
  window.scrollTo(0,0);},0);}
function toggleAdv(){const a=$('#advbox');if(a)a.style.display=(a.style.display==='none'?'block':'none');}
async function delRow(id){const u=USERS.find(x=>x.id===id);if(!confirm('Delete '+(u?u.name:'user')+'?'))return;await api('/api/admin/user/'+id+'/delete',{method:'POST'});toast('Deleted');await load();}
async function toggle(id,field){const u=USERS.find(x=>x.id===id);if(!u)return;await api('/api/admin/user/'+id,{method:'POST',body:JSON.stringify({[field]:!u[field]})});await load();}
async function reseed(){if(!confirm('Reset the user list to the demo pool? This replaces all users.'))return;const r=await api('/api/admin/reseed',{method:'POST'});toast('Reseeded '+r.count+' users');await load();}
async function clearAll(){if(!confirm('Delete ALL users? The system will have no people until you add some. This cannot be undone.'))return;await api('/api/admin/clear',{method:'POST'});toast('All users deleted');await load();}

// ---- matching lab: full diagnostic (matched + gated-out + considered + per-feature breakdown) ----
const defMIN=()=>({int:'',vibe:'chill',lang:'en',top:'chess',type:'social',role:'meet',mode:'offline',
  time:'Flexible',reqlang:'',minage:'',maxage:'',ver:false,radius:'',broad:false,exact:false,adj:true});
let MRES=null, LAB_EXP={}, MIN=defMIN();
const GN={semantic_activity:'Interests / topic',time_feasibility:'Time',location_feasibility:'Location',mode_format:'Mode & format',directed_preferences:'Role / target',social_context:'Vibe',domain_constraints:'Domain (lang/platform)'};
const splitc=s=>String(s||'').split(',').map(x=>x.trim().toLowerCase()).filter(Boolean);
const pctv=v=>v==null?'—':Math.round(v*100)+'%';
function readLab(){MIN={int:gv('#l_int'),vibe:gv('#l_vibe'),lang:gv('#l_lang'),top:gv('#l_top'),type:gv('#l_type'),
  role:gv('#l_role'),mode:gv('#l_mode'),time:gv('#l_time'),reqlang:gv('#l_reqlang'),minage:gv('#l_minage'),
  maxage:gv('#l_maxage'),ver:gc('#l_ver'),radius:gv('#l_radius'),broad:gc('#l_broad'),exact:gc('#l_exact'),adj:gc('#l_adj')};}
function buildReq(){
  const topics=splitc(MIN.top);
  const intent={title:topics.join(' & ')||'plan',type:MIN.type,topics:topics,role:MIN.role,mode:MIN.mode,
    time:MIN.time||'Flexible',broadConsent:MIN.broad,exactMatchRequired:MIN.exact,adjacentAllowed:MIN.adj};
  if(MIN.reqlang) intent.requiredLanguages=splitc(MIN.reqlang);
  if(MIN.minage) intent.minAge=+MIN.minage;
  if(MIN.maxage) intent.maxAge=+MIN.maxage;
  if(MIN.ver) intent.verifiedOnly=true;
  if(MIN.radius) intent.radiusKm=+MIN.radius;
  const ints=splitc(MIN.int);
  const profile={vibe:MIN.vibe,interests:ints.length?ints:topics,langs:splitc(MIN.lang)};
  return {intent:intent,profile:profile,ctx:{}};
}
async function runLab(){
  readLab();
  if(!splitc(MIN.top).length){toast('Enter a topic to search for');return;}
  $('#m_out').innerHTML='<p class="muted">Running the engine over every user…</p>';
  let d; try{d=await api('/api/admin/explain',{method:'POST',body:JSON.stringify(buildReq())});}
  catch(e){$('#m_out').innerHTML='<p class="muted">Matching agent unreachable — is matching (:7074) running?</p>';return;}
  MRES=d; renderLab(d);
}
function preset(p){
  const P={chess:{top:'chess',type:'social',role:'meet',mode:'offline'},
    spanish:{top:'spanish',type:'language',role:'practise',mode:'offline',lang:'en',reqlang:'es'},
    dota:{top:'dota',type:'gaming',role:'play',mode:'online'},
    coffee:{top:'coffee, ai',type:'social',role:'discuss',mode:'offline'},
    dating:{top:'coffee',type:'dating',role:'meet',mode:'offline'},
    padel:{top:'padel',type:'sport',role:'play',mode:'offline'}}[p]||{};
  MIN=Object.assign(defMIN(),P);
  LAB_EXP={}; render(); setTimeout(runLab,0);
}
function toggleRow(i){const n=MRES.matched[i].name; LAB_EXP[n]=!LAB_EXP[n]; renderLab(MRES);}
function stateChip(st){const l={known_match:'match',known_mismatch:'mismatch',unknown:'unknown',not_applicable:'n/a'}[st]||st;return `<span class="stchip st-${st}">${l}</span>`;}
function renderLab(d){
  const box=$('#m_out'); if(!box)return;
  if(!d){box.innerHTML='';return;}
  if(d.error){box.innerHTML='<p class="muted">'+esc(d.error)+'</p>';return;}
  const dc=d.domain_config||{}, W=dc.weights||{}, wv=Object.values(W), maxW=Math.max(0.01,...(wv.length?wv:[1]));
  const c=d.counts||{}, matched=d.matched||[], considered=d.considered||[], excluded=d.excluded||[], B=d.bands||{};
  const bcut=k=>`${(B[k]||{}).min_lcb}/${(B[k]||{}).min_coverage}`;
  const bars=Object.keys(W).map(k=>`<div class="dombar"><span class="gname">${GN[k]||k}</span><span class="track2"><span class="fill2" style="width:${Math.round(W[k]/maxW*100)}%"></span></span><span class="wv">${(+W[k]).toFixed(2)}</span></div>`).join('');
  const banner=`<div class="lab-sec">Inferred domain &amp; weights</div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
      <span class="tag" style="background:#eef1ff;color:#3f56d6;font-size:13px">${esc(d.domain)}</span>
      <span class="muted" style="font-size:12px">λ ${(+dc.uncertainty_lambda).toFixed(2)} · discovery lcb≥${dc.discovery_min_lcb} cov≥${dc.discovery_min_coverage} · outreach lcb≥${dc.outreach_min_lcb} cov≥${dc.outreach_min_coverage}</span></div>
    <div style="max-width:520px">${bars}</div>
    <div style="font-size:12px;margin-top:7px" class="muted">band cutoffs (lcb/cov): Top ≥${bcut('especially_close')} · Strong ≥${bcut('strong_option')} · Broad ≥${bcut('broader_option')}</div>
    <div style="margin:9px 0 2px;font-size:12.5px" class="muted">pool <b>${c.pool}</b> · matched <b style="color:#1f9d57">${c.matched}</b> · considered <b>${c.considered}</b> · excluded <b>${c.excluded}</b>${c.matched>d.slate_cut?` · real slate caps at ${d.slate_cut}+diversity`:''}</div>`;
  const bmap={especially_close:['#e9f9f0','#1f9d57'],strong_option:['#e9f9f0','#1f9d57'],broader_option:['#fff2e8','#d9700f'],needs_clarification:['#f1f2f5','#8a909c']};
  const rows=matched.map((m,i)=>{
    const ab=m.a_to_b||{}, col=bmap[m.band]||bmap.needs_clarification, open=!!LAB_EXP[m.name];
    const head=`<tr class="exrow" onclick="toggleRow(${i})">
      <td class="muted">${i+1}</td><td><b>${esc(m.name)}</b> <span class="muted" style="font-size:11px">${open?'▾':'▸'}</span></td>
      <td><span class="tag" style="background:${col[0]};color:${col[1]}">${esc(m.band_en)}</span></td>
      <td class="muted">${esc(m.tier)}${m.kind==='reciprocal'?' ↔':''}</td>
      <td class="tnum">${pctv(m.reciprocal)}</td><td class="tnum">${pctv(ab.coverage)}</td><td class="tnum">${pctv(ab.lcb)}</td>
      <td class="muted">${esc(m.readiness_en)}</td>
      <td>${m.can_outreach?'<span style="color:#1f9d57;font-weight:600">✓ reach</span>':'<span class="muted">discovery</span>'}</td></tr>`;
    if(!open) return head;
    const maxC=Math.max(0.001,...(ab.features||[]).map(f=>f.contribution||0));
    const frows=(ab.features||[]).map(f=>`<tr>
      <td>${GN[f.group]||f.group}</td><td>${stateChip(f.state)}</td>
      <td class="tnum">${f.value==null?'—':(+f.value).toFixed(2)}</td>
      <td class="tnum muted">${(+f.weight).toFixed(2)}</td>
      <td><span class="cbar" style="width:${Math.round((f.contribution||0)/maxC*64)}px"></span> <span class="tnum">${(+f.contribution).toFixed(3)}</span></td>
      <td class="muted">${esc(f.detail||'')}</td></tr>`).join('');
    const raw=(+ab.mean)-(+ab.lam)*(1-(+ab.coverage)), clamped=Math.abs(raw-(+ab.lcb))>0.0005;
    const math=`mean ${(+ab.mean).toFixed(3)} − λ${(+ab.lam).toFixed(2)}·(1−cov ${(+ab.coverage).toFixed(2)}) = ${raw.toFixed(3)}${clamped?' → clamp[0,1] = ':' = '}lcb <b>${(+ab.lcb).toFixed(3)}</b>`;
    const det=`<tr class="det"><td colspan="9" style="padding:10px 14px">
      <div class="mathline">${math}</div>
      <table class="fgtab"><thead><tr><td>Feature group</td><td>State</td><td>Value</td><td>Weight</td><td>Contribution</td><td>Detail</td></tr></thead><tbody>${frows}</tbody></table>
      <div style="font-size:12px;margin-top:6px" class="muted">Reverse fit (them → you): mean ${pctv((m.b_to_a||{}).mean)} · cover ${pctv((m.b_to_a||{}).coverage)} · lcb ${pctv((m.b_to_a||{}).lcb)} → reciprocal <b>${pctv(m.reciprocal)}</b></div>
      ${(m.reasons||[]).length?`<div style="font-size:12.5px;margin-top:4px"><b>Why:</b> ${esc(m.reasons.join(' · '))}</div>`:''}
      ${m.gap?`<div style="font-size:12.5px;margin-top:2px" class="muted">Gap: ${esc(m.gap)}</div>`:''}
      ${m.why_no_outreach?`<div style="font-size:12px;margin-top:3px;color:#d9700f">No personal outreach → ${esc(m.why_no_outreach)}</div>`:''}
    </td></tr>`;
    return head+det;
  }).join('');
  const tbl=matched.length?`<div class="tabler"><table>
    <thead><tr><th>#</th><th>Name</th><th>Match</th><th>Tier</th><th title="two-sided fit">Recip</th><th title="evidence coverage">Cover</th><th title="conservative score R_lcb">LCB</th><th>Availability</th><th>Outreach</th></tr></thead>
    <tbody>${rows}</tbody></table></div><p class="muted" style="font-size:11.5px;margin-top:4px">Click a row for the feature-group breakdown behind the score.</p>`
    :`<p class="muted">No one qualifies for this request.${considered.length?' '+considered.length+' were considered but filtered — see below.':' Add users into this topic, or loosen the levers.'}</p>`;
  const list=(arr,gate)=>arr.map(x=>`<tr><td><b>${esc(x.name)}</b></td><td>${gate?'<span class="stchip st-known_mismatch">gate</span>':`<span class="muted">${esc(x.tier||'')}</span>`}</td><td class="muted">${esc(x.reason||'')}</td>${(!gate&&x.lcb!=null)?`<td class="tnum muted">lcb ${(+x.lcb).toFixed(2)} · cov ${(+x.coverage).toFixed(2)}</td>`:'<td></td>'}</tr>`).join('');
  const flip="var a=this.nextElementSibling;a.style.display=(a.style.display==='none'?'block':'none')";
  const consid=considered.length?`<div class="collap" onclick="${flip}">▸ Considered but not shown (${considered.length})</div><div style="display:none"><table class="fgtab"><tbody>${list(considered,false)}</tbody></table></div>`:'';
  const excl=excluded.length?`<div class="collap" onclick="${flip}">▸ Excluded by hard gates (${excluded.length})</div><div style="display:none"><table class="fgtab"><tbody>${list(excluded,true)}</tbody></table></div>`:'';
  box.innerHTML=banner+`<div class="lab-sec">Matched — ranked</div>`+tbl+consid+excl;
}

// ---- canonical profile card: fields defined by the spec's slots + context profiles ----
let SCHEMA=null, CANON={user:'', cp:''};
async function loadSchema(){ if(SCHEMA)return SCHEMA;
  try{SCHEMA=await api('/api/admin/schema');}catch(e){SCHEMA={slots_by_domain:{},domains:[],context_profiles:[],counts:{}};}
  return SCHEMA; }
const cpById=id=>((SCHEMA&&SCHEMA.context_profiles)||[]).find(c=>c.profile_id===id);
const sid=n=>'cs_'+String(n).replace(/[^a-z0-9_]/gi,'_');
function canonPick(){ CANON.user=gv('#cn_user'); CANON.cp=gv('#cn_cp'); renderCanonForm(); }
function slotInput(s, val){
  const dt=s.data_type||'', id=sid(s.slot_name);
  const req=s.requirement==='required'?'<span style="color:#e5384f">*</span>'
    :(s.requirement==='conditional'?'<span class="muted" style="font-size:10px">усл.</span>':'');
  const imp=s.importance==='hard'?'<span class="stchip st-known_mismatch">hard</span>':'<span class="stchip st-unknown">soft</span>';
  const inp=(dt==='bool')
    ? `<input type="checkbox" id="${id}" ${(val===true||val==='true')?'checked':''}>`
    : `<input id="${id}" style="width:100%" placeholder="${esc(s['Вопрос RU']||'')}" value="${esc(val==null?'':val)}">`;
  return `<div style="min-width:230px;flex:1"><label>${esc(s['Название RU']||s.slot_name)} ${req} `
    +`<span class="muted" style="font-size:10px">${esc(dt)}</span> ${imp}</label>${inp}</div>`;
}
const DIALS=[['Соц.энергия','Социальная энергия 1–5'],['Спонтанность','Спонтанность 1–5'],['Повторяемость','Повторяемость 1–5'],
  ['Глубина','Глубина разговора 1–5'],['Физ.интенс.','Физическая интенсивность 1–5'],['Соревнов.','Соревновательность 1–5'],
  ['Комплемент.','Комплементарность 1–5'],['Логистика','Логистическая сложность 1–5'],['Планир.','Планирование 1–5'],['Online','Online fit 1–5']];
function renderCanonForm(){
  const box=$('#canon_out'); if(!box)return;
  const cp=cpById(CANON.cp);
  if(!cp){box.innerHTML='<p class="muted">Выбери контекст-профиль (режим), чтобы увидеть его карточку из слотов.</p>';return;}
  const dom=cp.domain, slots=(SCHEMA.slots_by_domain[dom]||[]);
  const u=USERS.find(x=>x.id===CANON.user), vals=((u&&u.slots)||{})[dom]||{};
  const meta=`<div class="lab-sec">${esc(cp.profile_id)} · ${esc(cp['Название RU'])}</div>
    <div class="muted" style="font-size:12px;margin-bottom:6px">purpose <b>${esc(cp.purpose)}</b> · domain <b>${esc(cp.domain)}</b> · раскрытие <b>${esc(cp['Профиль раскрытия'])}</b> · фаза ${esc(cp['Фаза запуска'])} · кандидаты: ${esc(cp.candidate_types)}</div>
    <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px">${DIALS.map(d=>`<span class="tag" style="background:#eef1ff;color:#3f56d6">${d[0]} ${esc(cp[d[1]])}/5</span>`).join('')}</div>
    <div class="muted" style="font-size:11.5px;margin-bottom:8px"><b>Hard gates:</b> ${esc(cp['Hard gates'])}<br><b>Fallback:</b> ${esc(cp['Fallback / расширение'])}<br><b>Нельзя переносить:</b> ${esc(cp['Запрещённый перенос данных'])}</div>`;
  const form=`<div class="lab-sec">Слоты домена «${esc(dom)}» (${slots.length})</div>
    <div class="row">${slots.map(s=>slotInput(s, vals[s.slot_name])).join('')||'<span class="muted">нет слотов</span>'}</div>
    <div class="row" style="justify-content:flex-end;margin-top:10px">${u?`<button onclick="saveCanon()">Сохранить слоты для ${esc(u.name)}</button>`:'<span class="muted">выбери пользователя выше, чтобы сохранить значения</span>'}</div>`;
  box.innerHTML=meta+form;
}
async function saveCanon(){
  const cp=cpById(CANON.cp); if(!cp||!CANON.user){toast('Выбери профиль и пользователя');return;}
  const dom=cp.domain, slots=(SCHEMA.slots_by_domain[dom]||[]), out={};
  for(const s of slots){ const el=$('#'+sid(s.slot_name)); if(!el)continue;
    const v=(s.data_type==='bool')?el.checked:el.value.trim();
    if(v!==''&&v!==false) out[s.slot_name]=v; }
  const u=USERS.find(x=>x.id===CANON.user);
  const merged=Object.assign({},(u&&u.slots)||{}); merged[dom]=out;
  await api('/api/admin/user/'+CANON.user,{method:'POST',body:JSON.stringify({slots:merged})});
  toast('Слоты сохранены для '+(u?u.name:'')); await load();
}

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
        <div><label>Formats</label><input id="f_fmt" style="min-width:130px" placeholder="offline, 1:1" title="mode/format they accept — feeds the mode_format group"></div>
        <div style="flex:1;min-width:180px"><label>Communities (comma)</label><input id="f_ent" style="width:100%" placeholder="Casa del Chess club"></div>
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
          <label class="chk end"><input id="f_blk" type="checkbox"> blocks me</label>
        </div>
        <div class="sec" style="margin-top:12px">Receiving policy — availability &amp; outreach (spec §4.4)</div>
        <div class="row">
          <div><label>Status</label><select id="f_rst"><option value="">— use open flag —</option><option>active</option><option>busy</option><option>paused</option></select></div>
          <label class="chk end"><input id="f_rpas" type="checkbox" checked> passive outreach</label>
          <div><label>Allowed domains</label><input id="f_rdom" style="min-width:150px" placeholder="all if blank" title="e.g. social_meet, walk — domains outside this become discovery-only"></div>
          <div><label>Quiet start</label><input id="f_rqs" style="min-width:78px" placeholder="22:00"></div>
          <div><label>Quiet end</label><input id="f_rqe" style="min-width:78px" placeholder="09:00"></div>
          <div><label>Max /24h</label><input id="f_r24" type="number" style="min-width:78px" placeholder="4"></div>
          <div><label>Max /7d</label><input id="f_r7d" type="number" style="min-width:78px" placeholder="—" title="§4.4 per_7d proposal budget, enforced at the send boundary"></div>
        </div>
        <div class="row">
          <div><label>Location scope</label><input id="f_rloc" style="min-width:150px" placeholder="all if blank" title="§4.4 e.g. Barcelona — proposals only within this location scope"></div>
          <div><label>Proposal types</label><input id="f_rpt" style="min-width:150px" placeholder="all if blank" title="§4.4 subset of: person, small_group, group, event, room"></div>
          <div><label>Disclosure stage</label><select id="f_rds"><option value="">— default —</option><option>minimal</option><option>limited_profile</option><option>match_only</option><option>full</option></select></div>
          <div><label>Paused until</label><input id="f_rpu" style="min-width:150px" placeholder="YYYY-MM-DDTHH:MM" title="§4.4 paused_until — excluded from retrieval until this time"></div>
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
    <div class="card">
      <h2>🔬 Matching lab</h2>
      <p class="muted" style="margin:-6px 0 10px;font-size:12.5px">Run the real engine over your users and see <b>every</b> decision: who matched with the per-feature-group breakdown, who was gated out (and why), the inferred domain and its weights. Change any lever and re-run.</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">
        <span class="muted" style="align-self:center;font-size:12px">Presets:</span>
        ${['chess','spanish','dota','coffee','dating','padel'].map(p=>`<button class="ghost mini" onclick="preset('${p}')">${p}</button>`).join('')}
      </div>
      <div class="lab-sec">You (the searcher)</div>
      <div class="row">
        <div style="flex:1;min-width:170px"><label>Your interests (comma)</label><input id="l_int" style="width:100%" placeholder="(defaults to the topic)" value="${esc(MIN.int)}"></div>
        <div><label>Your vibe</label><select id="l_vibe">${VIBES.map(v=>`<option ${v===MIN.vibe?'selected':''}>${v}</option>`).join('')}</select></div>
        <div><label>Your languages</label><input id="l_lang" style="min-width:90px" value="${esc(MIN.lang)}"></div>
      </div>
      <div class="lab-sec">Looking for</div>
      <div class="row">
        <div style="flex:1;min-width:170px"><label>Topic(s) (comma)</label><input id="l_top" style="width:100%" placeholder="chess" value="${esc(MIN.top)}"></div>
        <div><label>Category</label><select id="l_type">${['social','gaming','sport','language','networking','dating','other'].map(v=>`<option ${v===MIN.type?'selected':''}>${v}</option>`).join('')}</select></div>
        <div><label>Role</label><select id="l_role">${ROLES.map(v=>`<option ${v===MIN.role?'selected':''}>${v}</option>`).join('')}</select></div>
        <div><label>Mode</label><select id="l_mode">${['offline','online'].map(v=>`<option ${v===MIN.mode?'selected':''}>${v}</option>`).join('')}</select></div>
        <div><label>Time</label><input id="l_time" style="min-width:120px" placeholder="Flexible" value="${esc(MIN.time)}"></div>
      </div>
      <div class="adv"><span class="advtog" onclick="var a=$('#labadv');a.style.display=(a.style.display==='none'?'block':'none')">▸ Gates &amp; expansion levers</span>
        <div id="labadv" style="display:none;margin-top:10px"><div class="row">
          <div><label>Required language</label><input id="l_reqlang" style="min-width:110px" placeholder="e.g. es" value="${esc(MIN.reqlang)}"></div>
          <div><label>Min age</label><input id="l_minage" type="number" style="min-width:78px" value="${esc(MIN.minage)}"></div>
          <div><label>Max age</label><input id="l_maxage" type="number" style="min-width:78px" value="${esc(MIN.maxage)}"></div>
          <div><label>Radius km (offline)</label><input id="l_radius" type="number" step="0.5" style="min-width:120px" placeholder="any" value="${esc(MIN.radius)}"></div>
          <label class="chk end"><input id="l_ver" type="checkbox" ${MIN.ver?'checked':''}> verified only</label>
          <label class="chk end"><input id="l_broad" type="checkbox" ${MIN.broad?'checked':''}> broad consent (T2 outreach)</label>
          <label class="chk end"><input id="l_exact" type="checkbox" ${MIN.exact?'checked':''}> exact only (drop T2)</label>
          <label class="chk end"><input id="l_adj" type="checkbox" ${MIN.adj?'checked':''}> allow adjacent (T3)</label>
        </div></div>
      </div>
      <div class="row" style="margin-top:12px;justify-content:flex-end"><button onclick="runLab()">Run match</button></div>
      <div id="m_out" style="margin-top:10px"></div>
    </div>
    <div class="card">
      <h2>📋 Карточка профиля (канон · из спеки)</h2>
      <p class="muted" style="margin:-6px 0 10px;font-size:12.5px">Поля профиля определяются файлом онтологии: <b>${SCHEMA?SCHEMA.counts.slots:'…'}</b> слотов, <b>${SCHEMA?SCHEMA.counts.context_profiles:'…'}</b> контекст-профилей (data/taxonomy). Выбери режим — увидишь его слоты (тип · required · hard/soft · вопрос), гейты, профиль раскрытия и 10 шкал; можно заполнить и сохранить для пользователя.</p>
      <div class="row">
        <div><label>Пользователь (для сохранения)</label><select id="cn_user" onchange="canonPick()"><option value="">— только просмотр —</option>${USERS.map(u=>`<option value="${u.id}" ${CANON.user===u.id?'selected':''}>${esc(u.name)}</option>`).join('')}</select></div>
        <div style="flex:1;min-width:280px"><label>Контекст-профиль (режим)</label><select id="cn_cp" onchange="canonPick()"><option value="">— выбрать режим —</option>${SCHEMA?SCHEMA.context_profiles.map(c=>`<option value="${esc(c.profile_id)}" ${CANON.cp===c.profile_id?'selected':''}>${esc(c.profile_id)} · ${esc(c['Название RU'])} (${esc(c.domain)})</option>`).join(''):''}</select></div>
      </div>
      <div id="canon_out" style="margin-top:12px"></div>
    </div>
    <p class="muted" style="font-size:12px">Changes take effect for the matching agent within a few seconds (shared user store). Test mode.</p>
  </div>`;
  if(MRES)renderLab(MRES);
  if(CANON.cp)renderCanonForm();
}
load().catch(()=>toast('Load failed — is the server up?'));
</script></body></html>'''


if __name__ == "__main__":
    print("Kleal admin-service on http://127.0.0.1:%d  (store=%s, seed from %s)" % (PORT, STORE, MATCH_URL))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
