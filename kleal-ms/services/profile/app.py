# -*- coding: utf-8 -*-
# Kleal Profile demo — the "agent memory" profile screens, rebuilt from the Figma board
# "Section 1" (node 244-7677) of Kleal — Progress. ALL data comes from the UX spec
# "dating/UX задание на карточку профиля.docx" (Dmitry / Barcelona / football / Dota 2 / ...).
# Static demo (no LLM): stdlib http.server on :7073. Design tokens from Figma (Geist, coral #f5455c).
# Run: python kleal_profile.py    Preview config: .claude/launch.json -> "kleal-profile".
import os, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PROFILE_PORT", "7073"))

# ---------------------------------------------------------------- data (verbatim from the UX docx)
DATA = {
  "name": "Dmitry",
  "subtitle": "Barcelona · RU / EN · learning ES",
  "verified": True,
  "confidence": 74,
  "summaryLabel": "Kleal’s summary",
  "summary": "You’re usually open to coffee, walks, football, AI / startup talks, language practice and online fallback plans. You prefer low-pressure 1:1 or small groups, mostly evenings and weekends, in public places.",
  "matchingPaths": ["Football", "AI / startups", "Spanish practice"],

  "snapshot": [
    {"icon": "pin",    "title": "Location",       "value": "Barcelona · Eixample · Gràcia · Poblenou · Max travel 25 min"},
    {"icon": "globe",  "title": "Languages",      "value": "Russian native · English fluent · Spanish B1 practice"},
    {"icon": "users",  "title": "Social formats", "value": "1:1 ✓ · Small group ✓ · Events ○ · Online fallback ✓"},
    {"icon": "clock",  "title": "Availability",   "value": "Weekday evenings · Weekends · Spontaneous sometimes"},
    {"icon": "shield", "title": "Safety",         "value": "Public places · Verified preferred · No private locations"},
  ],

  "interests": [
    {"name": "Football", "icon": "football", "conf": "High", "used": True,
     "source": "onboarding + 3 intents", "expanded": True,
     "what": ["Watch matches", "Play casually", "Discuss football", "Sports bar sometimes"],
     "kv": [["Teams", "FC Barcelona"]],
     "expansion": "Football → Sport → Watch together → Casual evening group"},
    {"name": "AI / startups", "icon": "rocket", "conf": "High"},
    {"name": "Architecture", "icon": "building", "conf": "Medium"},
    {"name": "Spanish practice", "icon": "chat", "conf": "High", "used": True,
     "kv": [["Current level", "B1"], ["Goal", "Speaking practice"],
            ["Preferred format", "30-min call / coffee walk"], ["Correction style", "Gentle corrections"],
            ["Partner preference", "Native or fluent speaker"]]},
    {"name": "Dota 2", "icon": "gamepad", "conf": "Medium", "used": True,
     "kv": [["Platform", "PC"], ["Rank / level", "Ancient"], ["Role", "Support / Flex"],
            ["Mode", "Ranked preferred"], ["Voice chat", "Preferred"],
            ["Toxicity preference", "Low toxicity only"], ["Looking for", "One-time lobby / regular teammates"]]},
    {"name": "Cinema", "icon": "film", "conf": "Low"},
  ],

  "social": {
    "rows": [
      {"icon": "spark", "title": "Energy",             "value": "Calm / medium"},
      {"icon": "chat",  "title": "Conversation depth", "value": "Deep topics + casual warmth"},
      {"icon": "coffee","title": "Best first format",  "value": "Low-pressure coffee or walk"},
      {"icon": "users", "title": "Group comfort",      "value": "1:1 or small group up to 4"},
      {"icon": "pin",   "title": "Places",             "value": "Quiet cafes, walks, public spaces"},
      {"icon": "ban",   "title": "Avoid",              "value": "Loud bars, big random groups"},
    ],
    "vibe": [["calm", True], ["friendly", True], ["intellectual", True], ["playful", False],
             ["energetic", False], ["cozy", True], ["focused", False]],
    "depth": [["light casual", False], ["medium", True], ["deep talk", True], ["topic-based", True]],
  },

  "availability": [
    {"icon": "clock", "title": "Weekdays",         "value": "19:00–22:00"},
    {"icon": "clock", "title": "Weekends",         "value": "Flexible"},
    {"icon": "spark", "title": "Spontaneous plans","value": "Sometimes"},
    {"icon": "clock", "title": "Needs advance notice","value": "1–2 hours"},
    {"icon": "moon",  "title": "Quiet hours",      "value": "23:00–09:00"},
  ],
  "places": [
    {"icon": "pin",   "title": "City",             "value": "Barcelona"},
    {"icon": "pin",   "title": "Comfortable areas","value": "Eixample, Gràcia, Poblenou"},
    {"icon": "ban",   "title": "Avoid areas",      "value": "None selected"},
    {"icon": "route", "title": "Max travel",       "value": "25 min / 5 km"},
    {"icon": "eye",   "title": "Location sharing", "value": "Area only, never exact location"},
  ],

  "goals": {
    "active": ["Meet new people in Barcelona", "Coffee / walks / dinners", "Practice Spanish",
               "Find football / watch plans", "Gaming teammates", "AI / startup conversations"],
    "optional": ["Networking", "Dating mode off", "Regular groups"],
  },

  # Safety & Privacy is now a flat FLAGS object (single source of truth); scr_safety builds the
  # grouped, typed rows from it via safetyGroups(). Redesigned into 6 purpose-scoped groups.
  "safety": {
    "autonomy": "ask",          # 'ask' | 'auto'  (How Kleal acts for you)
    "confirmShare": True, "paused": False,
    "publicFirst": True, "noLateNight": True, "avoidAlcohol": False, "sharePlan": False,
    "trustedContact": None,
    "useInterestsArea": True, "useFeedback": True, "inferNew": True, "noSensitive": True,
    "suggestBeyond": True, "publicMap": False, "datingMode": False,
    "verified": False, "preferVerified": True, "blockedCount": 0, "excludeKnown": True,
  },

  # V4: quick-facts on the overview + the intent flow + discovery + messages
  "basics": [
    {"icon": "person", "title": "Basics", "value": "Male · 29"},
    {"icon": "pin", "title": "Location", "value": "Barcelona · Gràcia, Poblenou · Max 10 km"},
    {"icon": "globe", "title": "Languages", "value": "Russian · English · Spanish (B1)"},
  ],
  "intents": [
    {"id": "seed-coffee", "title": "Coffee & AI talk", "tags": ["coffee", "ai", "discuss"],
     "confidence": 82, "status": "searching",
     "spec": [["moon", "Mode", "Offline"], ["users", "Format", "1:1 or small group"],
              ["clock", "Time", "Today evening"], ["pin", "Area", "Public places nearby"],
              ["shield", "Safety", "Public places only"], ["compass", "Reach", "Adjacent interests"],
              ["eye", "Visibility", "Via Kleal only"]],
     "candidates": [
       {"name": "Marc", "score": 82, "km": 0.6, "agree": True, "interests": ["coffee", "ai", "startups"],
        "reasons": ["shares coffee, ai", "very close (0.6 km)"]},
       {"name": "Nina", "score": 69, "km": 1.1, "agree": True, "interests": ["startups", "networking", "ai"],
        "reasons": ["shares ai", "open to meet today"]}]},
  ],
  "plans": [
    {"title": "Morning coffee & AI chat", "who": "Marc · verified", "when": "Today 09:30", "dist": "0.6 km", "x": 33, "y": 26},
    {"title": "Startup founders meetup", "who": "4 going · public place", "when": "Tomorrow 18:00", "dist": "1.2 km", "x": 63, "y": 44},
    {"title": "Spanish + coffee swap", "who": "Ana · verified", "when": "Wed 17:00", "dist": "0.9 km", "x": 42, "y": 64},
  ],
  "messages": [
    {"who": "Kleal", "last": "2 people match your Coffee & AI talk — want intros?", "time": "now", "kleal": True},
    {"who": "Marc", "last": "Sounds great, see you at 9:30!", "time": "12m", "kleal": False},
    {"who": "Ana", "last": "Hola! Happy to swap Spanish for coffee.", "time": "1h", "kleal": False},
  ],

  "memory": [
    {"signal": "You prefer small groups", "source": "Onboarding + 2 accepted plans",
     "confidence": "High", "status": "Confirmed", "used": True, "updated": "Yesterday"},
    {"signal": "Prefers public places", "source": "Onboarding",
     "confidence": "High", "status": "Confirmed", "used": True, "updated": "3 days ago"},
    {"signal": "Football watch plans work for you", "source": "3 accepted plans",
     "confidence": "Medium", "status": "Inferred", "used": True, "updated": "Yesterday"},
    {"signal": "Avoid loud bars", "source": "Feedback on 1 plan",
     "confidence": "Medium", "status": "Inferred", "used": True, "updated": "Last week"},
    {"signal": "Wants an offline plan tonight", "source": "Current session",
     "confidence": "Low", "status": "Temporary", "used": False, "updated": "Just now"},
  ],

  "knows": {
    "total": 82, "confirmed": 54, "inferred": 19, "temporary": 9,
    "confirmedList": ["Lives in Barcelona", "Speaks RU / EN", "Learning Spanish", "Likes football",
                      "Supports FC Barcelona", "Open to small groups", "Prefers public places",
                      "Online fallback allowed"],
    "inferredList": ["Often accepts evening plans", "Prefers quiet venues",
                     "Likes topic-based conversations", "Better with clear plan details"],
  },
}

HTML_HEAD = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<title>Kleal Profile</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{
  --bg:#F7F8FA; --surface:#F7F8FA; --card:#FFFFFF; --fg:#181B22; --muted:#5A616E; --border:#E2E5EC;
  --line:#ECEEF2; --neutral100:#EEF0F4; --neutral300:#CDD2DC; --primary:#F5455C; --primary-fg:#FFFFFF;
  --coral50:#FFF1F3; --coral200:#FECDD4; --coral700:#BC1F38;
  --success-text:#0F7340; --success-bg:#E8F7EE; --info-text:#1F58BE; --info-bg:#E8F1FD;
  --warn-text:#9A5400; --warn-bg:#FFF4E5; --danger:#E5484D;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{background:#2b2d33;display:flex;align-items:center;justify-content:center;
  font-family:"Geist",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--fg)}
.phone{width:390px;height:844px;max-height:100vh;background:var(--bg);border-radius:44px;overflow:hidden;
  position:relative;display:flex;flex-direction:column;box-shadow:0 30px 90px #0008}
@media(max-width:430px){body{background:var(--bg)}.phone{width:100vw;height:100vh;border-radius:0}}
.sb{flex:none;height:47px;display:flex;align-items:center;justify-content:space-between;padding:0 24px 0 28px;
  font-weight:600;font-size:15px}
.sb .ic{display:flex;gap:6px;align-items:center}
.appbar{flex:none;height:56px;display:flex;align-items:center;justify-content:space-between;padding:0 16px}
.rbtn{width:44px;height:44px;border-radius:50%;background:#fff;border:1px solid var(--border);color:var(--fg);
  display:flex;align-items:center;justify-content:center;cursor:pointer;flex:none}
.appbar .ttl{font-weight:600;font-size:17px;letter-spacing:-.01em}
/* tab strip removed — Figma V2 uses a settings-row drill-in on the Overview */
.tabs{display:none}
/* V2 identity + confidence combined card */
.idcard{padding:16px}
.idrow{display:flex;align-items:center;gap:14px}
.idrow .ava{width:56px;height:56px;border-radius:50%;background:var(--neutral100);display:flex;align-items:center;
  justify-content:center;color:#9AA1AE;flex:none}
.idrow .it{flex:1;min-width:0}
.idrow .nm{display:flex;align-items:center;gap:7px;font-size:18px;font-weight:700}
.idrow .sub{font-size:13px;color:var(--muted);margin-top:2px;line-height:1.35;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gearbtn{width:40px;height:40px;border-radius:50%;border:1px solid var(--border);background:#fff;color:var(--fg);
  display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer}
.confrow2{display:flex;align-items:center;justify-content:space-between;margin-top:16px}
.confrow2 .l{font-size:14px;color:var(--muted)}
.confpct{font-size:14px;font-weight:600;color:var(--fg)}
/* V2 settings row (drill-in) */
.setrow{display:flex;align-items:center;gap:16px;padding:16px}
.setrow .sic{width:40px;height:40px;border-radius:50%;border:1px solid var(--border);color:var(--fg);
  display:flex;align-items:center;justify-content:center;flex:none}
.setrow .st{flex:1;min-width:0}
.setrow .stt{font-size:16px;font-weight:500;line-height:1.35}
.setrow .sts{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.setrow .sedit{display:flex;flex-direction:column;align-items:center;gap:4px;color:var(--primary);flex:none;cursor:pointer}
.setrow .sedit span{font-size:11px;font-weight:500}
.setrow:active{background:#fafafb}
/* V3 interests: toggle per interest + expandable summary */
.intsub{font-size:12.5px;color:var(--muted);text-align:center;margin:2px 8px 12px;line-height:1.45}
.irow2{display:flex;align-items:center;gap:12px;padding:14px 16px}
.irleft{flex:1;display:flex;align-items:center;gap:12px;min-width:0;cursor:pointer}
.ii2{width:26px;height:26px;flex:none;color:var(--fg);display:flex;align-items:center;justify-content:center}
.ii2 svg{width:24px;height:24px}
.inm2{font-size:16px;font-weight:700}
.intexp{padding:0;overflow:hidden;margin-top:-4px}
.intimg{height:150px;background:linear-gradient(135deg,#e7eaef,#d7dbe3)}
.intedit{display:flex;align-items:center;gap:10px;margin-top:14px}
.intav{width:44px;height:44px;border-radius:50%;background:var(--primary);flex:none}
.editbtn{flex:1;height:44px;border:0;border-radius:12px;background:var(--neutral100);color:var(--fg);
  font:600 15px inherit;display:flex;align-items:center;justify-content:center;gap:8px;cursor:pointer}
/* V3 your personality */
.persimg{width:120px;height:120px;border-radius:50%;background:linear-gradient(135deg,#e7eaef,#d7dbe3);margin:8px auto 18px;
  display:flex;align-items:center;justify-content:center;color:var(--neutral300)}
/* V3 goals */
.goalcard{padding:16px}
.goalcard .gc{display:flex;align-items:center;gap:14px}
.goalcard .gci{width:40px;height:40px;border-radius:50%;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;color:var(--fg);flex:none}
.goalcard .gct{flex:1;min-width:0}.goalcard .gctn{font-size:15px;font-weight:700}
.goalcard .gcts{font-size:12.5px;color:var(--muted);margin-top:2px}
.goalcard .gedit{color:var(--primary);cursor:pointer;flex:none}
/* body */
.body{flex:1;overflow-y:auto;padding:2px 16px 20px;scrollbar-width:none}
.body::-webkit-scrollbar{display:none}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 8px 24px #0000000d}
.pad{padding:16px}
.h2{font-size:22px;font-weight:700;letter-spacing:-.02em}
.seeall{font-size:13px;color:var(--muted);font-weight:500;cursor:pointer}
.rowhead{display:flex;align-items:center;justify-content:space-between;margin:18px 2px 12px}
.seclbl{font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.muted{color:var(--muted)}
/* identity */
.ident{display:flex;align-items:center;gap:14px;padding:16px}
.ava{width:56px;height:56px;border-radius:50%;background:var(--neutral100);display:flex;align-items:center;
  justify-content:center;color:#9AA1AE;flex:none}
.ident .nm{display:flex;align-items:center;gap:8px;font-size:18px;font-weight:700}
.badge-verify{color:var(--primary);display:flex}
.ident .sub{font-size:13px;color:var(--muted);margin-top:2px;line-height:1.35}
/* confidence */
.confrow{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.confrow .l{font-size:14px;color:var(--muted)}
.pill-pct{background:var(--primary);color:#fff;font-size:12px;font-weight:600;padding:4px 10px;border-radius:999px}
.track{height:8px;border-radius:999px;background:var(--neutral100);overflow:hidden}
.track>i{display:block;height:100%;background:var(--primary);border-radius:999px}
/* summary */
.sumlbl{color:var(--fg);font-size:16px;font-weight:700;margin-bottom:8px}
.sumhead{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px}
.sumhead .sumlbl{margin-bottom:0}
.updated{font-size:12px;color:var(--muted);flex:none}
.sumtxt{font-size:15px;line-height:1.5;color:var(--muted)}
.linkrow{display:flex;gap:24px;margin-top:16px}
.linkrow button{background:none;border:0;font:inherit;font-size:14px;font-weight:600;color:var(--primary);cursor:pointer}
.sumta{width:100%;min-height:120px;border:1.5px solid var(--border);border-radius:12px;padding:12px;
  font:14px/1.5 inherit;color:var(--fg);outline:none;resize:vertical;margin-top:2px}
.sumta:focus{border-color:var(--primary)}
.toast{position:absolute;left:50%;bottom:88px;transform:translateX(-50%) translateY(10px);background:var(--fg);
  color:#fff;font-size:13px;font-weight:500;padding:11px 16px;border-radius:12px;max-width:86%;text-align:center;
  opacity:0;pointer-events:none;transition:.22s;z-index:60;box-shadow:0 10px 28px #0005}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
/* chips */
.chips{display:flex;flex-wrap:wrap;gap:10px}
.chip{padding:9px 16px;border-radius:999px;font-size:14px;font-weight:600;cursor:pointer;user-select:none}
.chip.primary{background:var(--primary);color:#fff}
.chip.sel{background:var(--primary);border:1.5px solid var(--primary);color:#fff}
.chip.unsel{background:#fff;border:1.5px solid var(--border);color:var(--fg)}
/* summary row card */
.srow{display:flex;align-items:flex-start;gap:14px;padding:16px}
.srow .si{width:24px;height:24px;color:var(--fg);flex:none;margin-top:1px}
.srow .st{flex:1;min-width:0}
.srow .stt{font-size:16px;font-weight:600}
.srow .stv{font-size:14px;color:var(--muted);margin-top:3px;line-height:1.4}
.srow .edit{color:var(--primary);cursor:pointer;flex:none}
/* interest row */
.irow{display:flex;align-items:center;gap:12px;padding:14px 16px}
.irow .ii{width:28px;height:28px;flex:none;color:var(--fg);display:flex;align-items:center;justify-content:center}
.irow .ii svg{width:27px;height:27px}
.irow .inm{flex:1;font-size:16px;font-weight:700}
.cbadge{font-size:11px;font-weight:600;letter-spacing:.02em;padding:5px 10px;border-radius:999px}
.cb-High{background:var(--success-bg);color:var(--success-text)}
.cb-Medium{background:var(--warn-bg);color:var(--warn-text)}
.cb-Low{background:var(--neutral100);color:var(--muted)}
/* domain card */
.dcard{padding:16px}
.dtop{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.pill-on{border:1px solid var(--coral200);background:var(--coral50);color:var(--coral700);font-size:12px;
  font-weight:600;padding:4px 10px;border-radius:999px}
.dsrc{font-size:13px;color:var(--muted);margin:2px 0 14px}
.bullets{display:flex;flex-direction:column;gap:12px;margin-top:8px}
.bullet{display:flex;align-items:center;gap:12px;font-size:15px}
.bullet .dot{width:6px;height:6px;border-radius:50%;background:var(--primary);flex:none}
.kv{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-top:1px solid var(--line)}
.kv .k{font-size:14px;color:var(--muted)}.kv .v{font-size:14px;font-weight:600;text-align:right}
.expansion{margin-top:14px;background:var(--coral50);border-radius:12px;padding:12px 14px;color:var(--coral700);
  font-size:13px;font-weight:600;line-height:1.4}
.dactions{display:flex;align-items:center;gap:8px;margin-top:16px}
.dactions .txtbtn{flex:1;background:none;border:0;font:inherit;font-size:15px;font-weight:600;color:var(--fg);
  cursor:pointer;padding:12px}
.btn-remove{background:var(--primary);color:#fff;border:0;border-radius:999px;padding:12px 24px;
  font:inherit;font-size:15px;font-weight:600;cursor:pointer}
/* Edit Signal screen */
.bigbtn{width:100%;height:56px;border:0;border-radius:999px;font:600 16px inherit;cursor:pointer;margin-top:12px;
  display:flex;align-items:center;justify-content:center;gap:8px}
.bigbtn.primary{background:var(--primary);color:#fff}
.bigbtn.ghost{background:var(--neutral100);color:var(--fg)}
.bigbtn:active{transform:scale(.99)}
.chip.gsel{background:var(--neutral100);border:1.5px solid transparent;color:var(--fg)}
/* toggle row */
.trow{display:flex;align-items:center;gap:12px;padding:12px 16px}
.trow .tt{flex:1;min-width:0}
.trow .ttl{font-size:15px;font-weight:600}
.trow .tts{font-size:12px;color:var(--muted);margin-top:2px;line-height:1.35}
.seccap{font-size:12.5px;color:var(--muted);margin:2px 2px 8px;line-height:1.4}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:44px 24px;color:var(--muted)}
.empty .eic{width:52px;height:52px;border-radius:16px;background:var(--neutral100);display:flex;align-items:center;justify-content:center;color:var(--neutral300)}
.empty .etx{font-size:15px;font-weight:600;color:var(--fg);margin-top:14px}
.empty .esub{font-size:13px;margin-top:6px;color:var(--muted);max-width:250px;line-height:1.5}
.sw{width:46px;height:28px;border-radius:16px;background:var(--neutral300);flex:none;position:relative;transition:.2s;cursor:pointer}
.sw>i{position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:50%;background:#fff;
  box-shadow:0 1px 3px #0003;transition:left .2s}
.sw.on{background:var(--primary)}.sw.on>i{left:21px}
/* checkbox row */
.crow{display:flex;align-items:center;gap:14px;padding:11px 16px}
.cbx{width:24px;height:24px;border-radius:7px;border:2px solid var(--neutral300);flex:none;display:flex;
  align-items:center;justify-content:center;color:#fff;cursor:pointer}
.cbx.on{background:var(--primary);border-color:var(--primary)}
.crow .cl{font-size:15px}
/* stat tiles */
.stat{display:flex;flex-direction:column;align-items:center;padding:16px 0;border-left:1px solid var(--line)}
.stat:first-child{border-left:0}
.stat .n{font-size:22px;font-weight:700}.stat .l{font-size:12px;color:var(--muted);margin-top:3px}
.statbig{text-align:center;padding:22px 0 12px}
.statbig .n{font-size:34px;font-weight:700;letter-spacing:-1px}
.statbig .l{font-size:14px;color:var(--muted);margin-left:8px}
/* signal card (agent memory) */
.sig{padding:16px}
.sig .stopline{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.sig .ssig{font-size:16px;font-weight:600;line-height:1.35}
.stbadge{font-size:11px;font-weight:600;padding:4px 10px;border-radius:999px;flex:none;margin-left:10px}
.st-Confirmed{background:var(--success-bg);color:var(--success-text)}
.st-Inferred{background:var(--info-bg);color:var(--info-text)}
.st-Temporary{background:var(--warn-bg);color:var(--warn-text)}
.sig .smeta{font-size:13px;color:var(--muted);line-height:1.6}
.divider{height:1px;background:var(--line);margin:0 16px}
/* Safety & Privacy typed rows */
.trow .rt{display:flex;align-items:center;gap:8px;flex:none;color:var(--muted)}
.trow .rt svg{color:var(--neutral300)}
.sval{font-size:13px;color:var(--muted)}
.sbtn{font:inherit;font-size:13px;font-weight:700;color:var(--primary);background:var(--coral50);
  border:0;border-radius:999px;padding:6px 14px;cursor:pointer}
.ssub{font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);
  padding:12px 16px 4px;background:var(--card)}
.crow2{padding:12px 16px}
.crow2 .tt{margin-bottom:11px}
.seg{display:flex;gap:5px;background:var(--neutral100);border-radius:12px;padding:4px}
.seg button{flex:1;font:inherit;font-size:13px;font-weight:600;color:var(--muted);background:none;border:0;
  border-radius:9px;padding:9px 6px;cursor:pointer;transition:.15s}
.seg button.sel{background:var(--card);color:var(--fg);box-shadow:0 1px 3px rgba(20,20,40,.10)}
/* bottom nav with center FAB */
.bnav{flex:none;height:66px;display:flex;align-items:center;justify-content:space-around;position:relative;
  background:#fff;border-top:1px solid var(--line);padding-bottom:env(safe-area-inset-bottom)}
.bnav a{display:flex;flex-direction:column;align-items:center;gap:3px;font-size:11px;color:var(--muted);cursor:pointer;width:60px}
.bnav a.on{color:var(--primary)}
.bnav .fabgap{width:60px}
.fab{position:absolute;left:50%;top:-16px;transform:translateX(-50%);width:56px;height:56px;border-radius:50%;
  background:var(--primary);color:#fff;border:4px solid var(--bg);display:flex;align-items:center;justify-content:center;
  cursor:pointer;box-shadow:0 8px 20px rgba(245,69,92,.35)}
.gap8{height:8px}.gap12{height:12px}.gap16{height:16px}
.stack>*+*{margin-top:10px}
.fade{animation:fd .28s ease}@keyframes fd{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
/* ---- V4: intents, intent chat, discovery, messages ---- */
.itag{display:inline-flex;align-items:center;font-size:12px;font-weight:600;color:var(--coral700);
  background:var(--coral50);border:1px solid var(--coral200);border-radius:999px;padding:5px 11px;margin:0 6px 8px 0}
.specrow{display:flex;align-items:center;gap:12px;padding:11px 16px}
.specrow .spi{width:20px;color:var(--muted);flex:none;display:flex}
.specrow .sl{flex:1;font-size:14px;color:var(--muted)}
.specrow .sv{font-size:14px;font-weight:600;color:var(--fg);text-align:right}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;border-radius:999px;padding:4px 10px}
.pill.searching{color:var(--coral700);background:var(--coral50)}
.pill.dot::before{content:'';width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block}
.thread{display:flex;flex-direction:column;gap:12px;padding-bottom:8px}
.kbub{background:var(--neutral100);border-radius:16px 16px 16px 4px;padding:12px 14px;font-size:14px;color:var(--fg);max-width:88%;align-self:flex-start}
.mbub{background:var(--primary);color:#fff;border-radius:16px 16px 4px 16px;padding:10px 14px;font-size:14px;max-width:82%;align-self:flex-end}
.composer{position:sticky;bottom:0;background:var(--bg);display:flex;align-items:center;gap:10px;padding:10px 2px 8px;margin-top:6px}
.composer .cin{flex:1;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:11px 16px;color:var(--muted);font-size:14px}
.composer .csend{width:40px;height:40px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer}
.composer .csend svg{width:19px;height:19px}
.composer input.cinput{outline:0}.composer input.cinput::placeholder{color:var(--muted)}
.typing3{display:inline-flex;gap:3px;vertical-align:middle}
.typing3 i{width:5px;height:5px;border-radius:50%;background:var(--muted);display:inline-block;animation:tb 1s infinite}
.typing3 i:nth-child(2){animation-delay:.15s}.typing3 i:nth-child(3){animation-delay:.3s}
@keyframes tb{0%,60%,100%{opacity:.3}30%{opacity:1}}
.candrow{display:flex;align-items:center;gap:12px;padding:12px 16px}
.candav{width:38px;height:38px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#FF7A8A,#F5455C);color:#fff;font-weight:800;font-size:15px}
.candt{flex:1;min-width:0}
.candn{font-size:14.5px;font-weight:700}
.candn .candkm{font-size:11px;font-weight:500;color:var(--muted);margin-left:6px}
.cands{font-size:12px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.candsc{flex:none;text-align:right}
.candpct{font-size:15px;font-weight:800;color:var(--fg)}
.candok{font-size:10.5px;font-weight:700;color:#0f7340}
.candbusy{font-size:10.5px;font-weight:600;color:var(--muted)}
.candno{font-size:10.5px;font-weight:600;color:var(--muted)}
.introbtn{flex:none;font:inherit;font-size:12px;font-weight:700;color:#fff;background:var(--primary);border:0;
  border-radius:999px;padding:7px 13px;cursor:pointer;margin-left:2px}
/* ===== Buddy chat (Figma "assistant chat") ===== */
.bchat{display:flex;flex-direction:column;height:100%;min-height:0}
.chd{flex:none;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:4px 4px 10px}
.chd-back{display:flex;align-items:center;gap:2px;background:transparent;border:0;color:var(--fg);
  font:inherit;font-size:16px;font-weight:600;cursor:pointer;padding:6px 4px}
.chd-back svg{width:22px;height:22px}
.chd-pills{display:flex;gap:8px}
.chd-pill{display:flex;align-items:center;gap:5px;background:var(--card);border:1px solid var(--border);
  border-radius:999px;padding:8px 13px;font:inherit;font-size:13px;font-weight:600;color:var(--fg);cursor:pointer;white-space:nowrap}
.chd-pill svg{width:16px;height:16px}
.chd-pill .pl{font-size:17px;line-height:0;font-weight:500;color:var(--primary);margin-right:1px}
.bthread{flex:1;min-height:0;overflow-y:auto;scrollbar-width:none;display:flex;flex-direction:column;gap:14px;padding:6px 2px 10px}
.bthread::-webkit-scrollbar{display:none}
.khello{display:flex;align-items:center;gap:12px;margin:6px 0 4px}
.khello .khtxt{font-size:22px;font-weight:700;letter-spacing:-.02em;line-height:1.25}
.krow{display:flex;align-items:flex-end;gap:9px;max-width:90%}
.krow .kav{flex:none}
.krow .kcol{display:flex;flex-direction:column;gap:3px;min-width:0}
.kav{width:34px;height:34px;border-radius:50%;flex:none;background:linear-gradient(135deg,#FF7A8A,#F5455C)}
.kav.sp{background:transparent}
.mrow{display:flex;flex-direction:column;align-items:flex-end;gap:3px;align-self:flex-end;max-width:82%}
.btime{font-size:11px;color:var(--muted);padding:0 4px}
.btime.r{align-self:flex-end}
.bc2{flex:none;display:flex;align-items:center;gap:9px;padding:8px 2px calc(8px + env(safe-area-inset-bottom))}
.bc2-plus{width:44px;height:44px;border-radius:50%;background:#fff;border:1px solid var(--border);color:var(--muted);
  font-size:26px;font-weight:300;line-height:0;display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer}
.bc2-field{flex:1;min-width:0;display:flex;align-items:center;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:0 4px 0 16px}
.bc2-field input{flex:1;min-width:0;border:0;outline:0;background:transparent;font-size:16px;padding:12px 0;color:var(--fg)}
.bc2-field input::placeholder{color:var(--muted)}
.bc2-mic{width:36px;height:36px;border-radius:50%;background:transparent;border:0;color:var(--muted);display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer}
.bc2-mic.on{color:var(--primary)}
.bc2-mic svg{width:21px;height:21px}
.bc2-send{width:44px;height:44px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer;box-shadow:0 6px 14px rgba(245,69,92,.35)}
.bc2-send svg{width:19px;height:19px}
/* profile-edit confirmation card */
.ecard{padding:12px 14px;max-width:80%}
.epatch{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;color:var(--fg);padding:3px 0}
.epatch svg{width:16px;height:16px;color:var(--primary);flex:none}
.eactions{display:flex;gap:8px;margin-top:10px}
.ebtn{flex:1;font:inherit;font-size:14px;font-weight:700;border-radius:999px;padding:9px 0;cursor:pointer;border:1px solid var(--border)}
.ebtn.primary{background:var(--primary);color:#fff;border-color:var(--primary)}
.ebtn.ghost{background:#fff;color:var(--muted)}
/* match chat */
.matchhead{display:flex;align-items:center;gap:12px;padding:6px 2px 4px}
.mava{width:52px;height:52px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#FF7A8A,#F5455C);color:#fff;font-weight:800;font-size:20px;transition:filter .4s}
.mmeta{flex:1;min-width:0}.mnm{font-size:17px;font-weight:800}
.mnm .mscore{font-size:12px;font-weight:600;color:var(--primary);margin-left:6px}
.mhint{font-size:12px;color:var(--muted);margin-top:2px}
/* notifications */
.abell{position:relative}
.abadge{position:absolute;top:-3px;right:-3px;min-width:17px;height:17px;border-radius:999px;background:var(--primary);
  color:#fff;font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center;padding:0 4px;border:2px solid var(--bg)}
.notifrow{display:flex;align-items:center;gap:12px;padding:12px 14px}
.notifrow.unread{border-color:var(--coral200);background:var(--coral50)}
.nnic{width:38px;height:38px;border-radius:999px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;color:var(--primary);flex:none}
.nnt{flex:1;min-width:0}.nntt{font-size:14.5px;font-weight:700}.nnts{font-size:12.5px;color:var(--muted);margin-top:2px}
.nntime{font-size:11px;color:var(--muted);flex:none;align-self:flex-start}
/* explore event rows */
.evrow{display:flex;align-items:center;gap:12px;padding:12px 14px}
.evic{width:38px;height:38px;border-radius:999px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;color:var(--fg);flex:none}
.evt{flex:1;min-width:0}.evtt{font-size:14.5px;font-weight:700}.evts{font-size:12px;color:var(--muted);margin-top:2px}
/* real map (Leaflet) on Explore */
.lmap{height:340px;border-radius:18px;overflow:hidden;border:1px solid var(--border);background:#e7ebf2}
.lmap .leaflet-container{font:inherit}
.meDot{width:16px;height:16px;border-radius:50%;background:#181B22;border:3px solid #fff;box-shadow:0 0 0 4px rgba(24,27,34,.16)}
.mapop{min-width:150px}.mapop .mopt{font-size:13.5px;font-weight:700;line-height:1.25}
.mapop .mopm{font-size:11.5px;color:var(--muted);margin:3px 0 8px}
.mapop .mopj{font:inherit;font-size:12px;font-weight:700;color:#fff;background:var(--primary);border:0;border-radius:999px;padding:6px 14px;cursor:pointer}
.leaflet-popup-content{margin:10px 12px}.leaflet-popup-content-wrapper{border-radius:12px}
.chkrow{display:flex;align-items:center;gap:12px;padding:12px 16px}
.chkic{width:22px;height:22px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center}
.chkic.done{background:#0f7340}.chkic.now{border:2px solid var(--primary)}.chkic.wait{border:2px solid var(--neutral300)}
.chklb{flex:1;font-size:14px;color:var(--fg)}.chklb.wait{color:var(--muted)}
.chkst{font-size:12px;font-weight:700}
.chkst.done{color:#0f7340}.chkst.now{color:var(--primary)}.chkst.wait{color:var(--neutral300)}
.sbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.sbar .box{flex:1;display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:10px 14px;color:var(--muted);font-size:14px}
.sbar .filt{width:42px;height:42px;border-radius:50%;background:var(--card);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;color:var(--fg);flex:none;cursor:pointer}
.map{position:relative;height:360px;border-radius:18px;overflow:hidden;background:linear-gradient(135deg,#eef1f6,#e7ebf2);border:1px solid var(--border)}
.map .grid{position:absolute;inset:0;background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:44px 44px;opacity:.55}
.mpin{position:absolute;transform:translate(-50%,-100%);color:var(--primary);cursor:pointer;filter:drop-shadow(0 3px 4px rgba(20,20,40,.2))}
.mpin.me{color:var(--fg)}
.plan-card{position:absolute;transform:translate(-50%,-118%);width:156px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:9px 11px;box-shadow:0 8px 20px rgba(20,20,40,.14);cursor:pointer}
.plan-card .pt{font-size:12.5px;font-weight:700;line-height:1.25}
.plan-card .pm{font-size:11px;color:var(--muted);margin-top:3px}
.searchbtn{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);white-space:nowrap;width:auto;padding:11px 20px}
.msgrow{display:flex;align-items:center;gap:12px;padding:12px 4px;cursor:pointer}
.msgav{width:46px;height:46px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;background:var(--neutral100);color:var(--muted)}
.msgav.k{background:linear-gradient(135deg,#FF7A8A,#F5455C);color:#fff;font-weight:800}
.msgt{flex:1;min-width:0}.msgt .mn{font-size:15px;font-weight:600}
.msgt .ml{font-size:13px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.msgtime{font-size:11px;color:var(--muted);flex:none;align-self:flex-start;margin-top:3px}
.reddot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--primary);margin-left:6px;vertical-align:middle}
/* ---- Agent Home (main landing) ---- */
.ahome{padding:4px 0 14px}
.ahead{display:flex;align-items:center;justify-content:space-between;padding:6px 2px 16px}
.agreet{font-size:24px;font-weight:800;letter-spacing:-.02em}
.abell{width:40px;height:40px;border-radius:50%;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;color:var(--fg);cursor:pointer;flex:none}
.aintro{display:flex;gap:11px;align-items:flex-start;margin-bottom:14px}
.aintro .amascot{flex:none}
.aintro .abub{background:var(--neutral100);border-radius:16px 16px 16px 4px;padding:12px 14px;font-size:14px;line-height:1.5;color:var(--fg)}
.asearch{display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--border);border-radius:999px;padding:6px 6px 6px 16px;margin-bottom:22px;box-shadow:0 2px 8px rgba(20,20,40,.05)}
.asearch input{flex:1;min-width:0;border:0;outline:0;background:none;font:inherit;font-size:14px;color:var(--fg)}
.asearch input::placeholder{color:var(--muted)}
.asend{width:40px;height:40px;border-radius:50%;background:var(--primary);color:#fff;border:0;display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer}
.asend svg{width:19px;height:19px;transform:translate(-1px,0)}
.qhead,.thead .th{font-size:15px;font-weight:700}
.qhead{margin-bottom:11px}
.quick{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-bottom:24px}
.qcard{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:12px 5px;display:flex;flex-direction:column;align-items:center;gap:8px;cursor:pointer;text-align:center}
.qcard .qic{width:34px;height:34px;border-radius:999px;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;color:var(--fg);flex:none}
.qcard .qic svg{width:18px;height:18px}
.qcard .qt{font-size:10.5px;color:var(--muted);line-height:1.25;font-weight:500}
.thead{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.thead .tall{color:var(--primary);font-size:13px;font-weight:600;cursor:pointer}
.tcard{display:flex;gap:12px;align-items:center;background:var(--card);border:1px solid var(--border);border-radius:16px;padding:10px;cursor:pointer}
.tcard .timg{width:92px;height:76px;border-radius:12px;flex:none;background:linear-gradient(135deg,#caa27a,#6f4a2c)}
.tcard .tbody{flex:1;min-width:0}
.tcard .tt{font-size:15px;font-weight:700;line-height:1.25}
.tcard .tm{font-size:12px;color:var(--muted);margin-top:5px}
.tcard .tpart{display:flex;align-items:center;gap:9px;margin-top:11px}
.stack5{display:flex}
.stack5 .av{width:22px;height:22px;border-radius:50%;background:linear-gradient(135deg,#FF7A8A,#F5455C);border:2px solid var(--card);margin-left:-7px}
.stack5 .av:first-child{margin-left:0}
.stack5 .more{width:22px;height:22px;border-radius:50%;background:var(--neutral100);border:2px solid var(--card);margin-left:-7px;font-size:9px;font-weight:700;display:flex;align-items:center;justify-content:center;color:var(--muted)}
.tcard .pn{font-size:12px;color:var(--muted)}
.tcard .tbm{color:var(--muted);flex:none;align-self:flex-start}
</style></head><body>
<div class="phone">
  <div class="sb"><span>9:41</span><span class="ic" id="sbic"></span></div>
  <div class="appbar">
    <div class="rbtn" id="back"></div>
    <div class="ttl" id="title">My Kleal Profile</div>
    <div class="rbtn" id="bookmark"></div>
  </div>
  <div class="tabs" id="tabs"></div>
  <div class="body" id="app"></div>
  <div class="bnav" id="bnav"></div>
</div>
<script>
const DEMO = __DATA__;                       // fallback demo data (docx / Dmitry)
// CONNECTED MODE: the onboarding app (:7072) hands off its final profile as ?p=<base64(utf8 json)>.
let DATA = DEMO, _TABIDS = null;
try{
  const _p = new URLSearchParams(location.search).get('p');
  if(_p){ const op = JSON.parse(decodeURIComponent(escape(atob(_p)))); const m = mapOnboarding(op);
          DATA = m.data; _TABIDS = m.tabs; }
}catch(e){ console.error('profile: could not read ?p', e); }
// PERSISTENCE: the demo has no backend, so edits used to vanish on a page refresh (it reverted
// to the seed data). Keep the working state in localStorage and rehydrate on load. Keyed by the
// data SOURCE so a fresh onboarding hand-off (a new ?p=) shows new data instead of stale edits.
const _pParam = new URLSearchParams(location.search).get('p');
const PKEY = 'kleal_profile_state_v1';
const _psrc = _pParam ? ('p:'+_pParam.length+':'+_pParam.slice(-40)) : 'demo';
let _saved = null; try{ _saved = JSON.parse(localStorage.getItem(PKEY)||'null'); }catch(_e){}
if(_saved && _saved._src===_psrc && _saved.data){ DATA = _saved.data; }
else { try{ localStorage.removeItem(PKEY); }catch(_e){} _saved = null; }
const A=document.getElementById('app');
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function svg(inner,vb,w){return '<svg viewBox="'+(vb||'0 0 24 24')+'" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="'+(w||24)+'" height="'+(w||24)+'">'+inner+'</svg>';}
const IC={
  back:svg('<path d="M15 6l-6 6 6 6"/>'),
  bookmark:svg('<path d="M6 4h12v17l-6-4-6 4V4z"/>'),
  chevL:svg('<path d="M15 6l-6 6 6 6"/>'),
  verify:'<svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 2.6l2.2 1.7 2.8-.2.9 2.7 2.4 1.5-.7 2.8.7 2.8-2.4 1.5-.9 2.7-2.8-.2L12 21.4l-2.2-1.7-2.8.2-.9-2.7-2.4-1.5.7-2.8-.7-2.8 2.4-1.5.9-2.7 2.8.2L12 2.6z" fill="#F5455C"/><path d="M8.6 12l2.2 2.2 4.6-4.6" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  edit:svg('<path d="M4 20h4L18.5 9.5a2 2 0 0 0-2.83-2.83L5 17z"/><path d="M14 7l3 3"/>',null,22),
  person:svg('<circle cx="12" cy="8.5" r="3.6"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/>',null,26),
  pin:svg('<path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/>'),
  globe:svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>'),
  users:svg('<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M16 6.2a3 3 0 0 1 0 5.6M20.5 19a5.5 5.5 0 0 0-3.5-5.1"/>'),
  clock:svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>'),
  shield:svg('<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z"/>'),
  football:svg('<circle cx="12" cy="12" r="9"/><path d="M12 8l3.2 2.3-1.2 3.7h-4L8.8 10.3 12 8z"/><path d="M12 3v3M4.5 8.5l2.5 1.8M19.5 8.5l-2.5 1.8M7.5 19l1.3-3M16.5 19l-1.3-3"/>'),
  rocket:svg('<path d="M14 4c3 1 5 3 6 6-2 3-6 6-9 7l-3-3c1-3 3-7 6-9z"/><path d="M9 15l-2 4M6 12l-3 1M8 18l-3 1"/><circle cx="14.5" cy="9.5" r="1.4"/>'),
  building:svg('<rect x="5" y="4" width="9" height="16" rx="1"/><path d="M14 9h5v11h-5M8 8h3M8 12h3M8 16h3"/>'),
  chat:svg('<path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-4 4v-4a2 2 0 0 1-1-1.7V6z"/>'),
  gamepad:svg('<rect x="3" y="8" width="18" height="9" rx="4"/><path d="M8 12h3M9.5 10.5v3"/><circle cx="16" cy="11.5" r="1"/><circle cx="17.8" cy="13.5" r="1"/>'),
  film:svg('<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 5v14M16 5v14M4 9.5h4M16 9.5h4M4 14.5h4M16 14.5h4"/>'),
  spark:svg('<path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17l-1.9-5.1L4.5 10l5.6-1.4L12 3z"/>'),
  coffee:svg('<path d="M4 8h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V8z"/><path d="M17 9h2.5a2 2 0 0 1 0 4H17"/><path d="M7 3v2M11 3v2"/>'),
  ban:svg('<circle cx="12" cy="12" r="9"/><path d="M6 6l12 12"/>'),
  moon:svg('<path d="M20 14a8 8 0 1 1-9.5-9.7A6.5 6.5 0 0 0 20 14z"/>'),
  route:svg('<circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="6" r="2.4"/><path d="M8.4 18H14a3.6 3.6 0 0 0 0-7.2H10a3.6 3.6 0 0 1 0-7.2h.6" transform="translate(0 1.4)"/>'),
  eye:svg('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>'),
  check:'<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" width="15" height="15"><path d="M5 12.5l4.5 4.5L19 7"/></svg>',
  nIntents:svg('<path d="M4 6h16M4 12h16M4 18h10"/>',null,22),
  nSearch:svg('<circle cx="11" cy="11" r="6.5"/><path d="M20.5 20.5L16 16"/>',null,22),
  nMsg:svg('<path d="M4 5h16v11H9l-4 4V5z"/>',null,22),
  nProfile:svg('<circle cx="12" cy="8.5" r="3.6"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/>',null,22),
  chevR:svg('<path d="M9 6l6 6-6 6"/>',null,20),
  compass:svg('<circle cx="12" cy="12" r="9"/><path d="M15.4 8.6l-2 4.8-4.8 2 2-4.8 4.8-2z"/>'),
  flag:svg('<path d="M6 21V4M6 5h11l-2 3.2 2 3.2H6"/>'),
  star:svg('<path d="M12 4l2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.5-4.8 2.5.9-5.4L4.2 9.7l5.4-.8L12 4z"/>',null,20),
  gear:svg('<circle cx="12" cy="12" r="3.1"/><path d="M12 3.2v2.3M12 18.5v2.3M4.6 7.7l2 1.15M17.4 15.15l2 1.15M4.6 16.3l2-1.15M17.4 8.85l2-1.15M3.4 12h2.3M18.3 12h2.3"/>',null,20),
  faceScan:svg('<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M9.3 11h.01M14.7 11h.01M9.2 14.5c1.2 1.1 4.4 1.1 5.6 0"/>',null,20),
  sun:svg('<circle cx="12" cy="12" r="3.8"/><path d="M12 2.5v2M12 19.5v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2.5 12h2M19.5 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>',null,20),
  userLock:svg('<circle cx="9" cy="8" r="3.1"/><path d="M3.6 19.5a5.5 5.5 0 0 1 8.4-4.2"/><rect x="13.5" y="14" width="7.5" height="6.2" rx="1.4"/><path d="M15.1 14v-1.4a2.15 2.15 0 0 1 4.3 0V14"/>',null,20),
  wand:svg('<path d="M6 18L14 10"/><path d="M15 4.2l.9 1.9 1.9.9-1.9.9-.9 1.9-.9-1.9-1.9-.9 1.9-.9.9-1.9z"/><path d="M17.5 11l.6 1.3 1.3.6-1.3.6-.6 1.3-.6-1.3-1.3-.6 1.3-.6.6-1.3z"/>',null,16),
  refresh:svg('<path d="M20 11.5a8 8 0 1 0-.9 5"/><path d="M20 4.5v5h-5"/>'),
  boxx:svg('<rect x="4" y="5.5" width="16" height="13" rx="2"/><path d="M9.5 10l5 4.5M14.5 10l-5 4.5"/>',null,20),
  nHome:svg('<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9.5 20v-6h5v6"/>',null,22),
  nPlans:svg('<rect x="4" y="5" width="16" height="16" rx="2.5"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4"/>',null,22),
  bell:svg('<path d="M6 9a6 6 0 0 1 12 0c0 4.5 1.8 5.7 2 6H4c.2-.3 2-1.5 2-6z"/><path d="M10 20a2 2 0 0 0 4 0"/>'),
  send:svg('<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>'),
  calen:svg('<rect x="4" y="5" width="16" height="16" rx="2.5"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4"/>'),
  heart:svg('<path d="M12 20s-7-4.6-9.3-9A4.6 4.6 0 0 1 12 6.2 4.6 4.6 0 0 1 21.3 11c-2.3 4.4-9.3 9-9.3 9z"/>'),
  mic:svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/>',null,26),
  peoplePin:svg('<circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 9-4"/><path d="M17.5 21s3-2.6 3-5a3 3 0 0 0-6 0c0 2.4 3 5 3 5z"/><circle cx="17.5" cy="16" r="1"/>'),
};
const MASCOT = '<svg viewBox="0 0 48 48" width="46" height="46"><rect x="6" y="6" width="36" height="36" rx="16" fill="#FDE7EB"/><circle cx="19" cy="24" r="2.4" fill="#F5455C"/><circle cx="29" cy="24" r="2.4" fill="#F5455C"/><path d="M18.5 30c2.2 1.8 8.8 1.8 11 0" fill="none" stroke="#F5455C" stroke-width="2" stroke-linecap="round"/></svg>';
document.getElementById('sbic').innerHTML=
 '<svg viewBox="0 0 20 14" fill="#181B22" width="18" height="13"><rect x="0" y="9" width="3" height="5" rx="1"/><rect x="5.3" y="6" width="3" height="8" rx="1"/><rect x="10.6" y="3" width="3" height="11" rx="1"/><rect x="15.9" y="0" width="3" height="14" rx="1"/></svg>'
 +'<svg viewBox="0 0 20 15" fill="none" stroke="#181B22" stroke-width="1.9" stroke-linecap="round" width="18" height="14"><path d="M2 5.2a13 13 0 0 1 16 0M5 8.6a8 8 0 0 1 10 0M8 12a3 3 0 0 1 4 0"/></svg>'
 +'<svg viewBox="0 0 28 14" width="25" height="13"><rect x="1" y="1.4" width="22" height="11.2" rx="3" stroke="#181B22" stroke-opacity=".5" fill="none"/><rect x="2.8" y="3.1" width="16.5" height="7.8" rx="1.6" fill="#181B22"/><rect x="24.3" y="4.6" width="2.3" height="4.8" rx="1.1" fill="#181B22" fill-opacity=".5"/></svg>';
document.getElementById('back').innerHTML=IC.back;
// bottom nav (Intents · Search · [create] · Messages · Profile) — rebuilt each render for the active state
const ROOTS=['agenthome','overview','intents','search','messages'];
function navFam(){
  if(cur==='agenthome'||cur==='buddychat'||cur==='profileedit'||cur==='notifs')return'';   // center FAB owns these — no pill highlight
  if(cur==='search')return'explore';
  if(cur==='intents'||cur==='intentchat'||cur==='matchchat')return'plans';
  if(cur==='messages')return'messages';
  return'profile'; }
function bnavHTML(){ const fam=navFam();
  // Intents · Explore · [Home] · Messages · Profile  (Figma "My Intents · Search · [FAB] · Messages · Profile").
  // The center FAB opens the AGENT HOME (agenthome) — the main landing that carries the Kleal banner, the
  // "Say hi to Kleal" field and quick actions. The conversational chat is reached from there.
  const items=[['nIntents','Intents','intents','plans'],['nSearch','Explore','search','explore'],['fab','','',''],
    ['nMsg','Messages','messages','messages'],['nProfile','Profile','overview','profile']];
  return '<div class="fab" data-act="go-home">'+IC.mic+'</div>'+
    items.map(x=>{ if(x[0]==='fab') return '<div class="fabgap"></div>';
      return `<a class="${fam===x[3]?'on':''}" data-nav="${x[2]}">${IC[x[0]]}<span>${x[1]}</span></a>`; }).join('');
}

// ---------- map the onboarding profile (:7072) -> this card's DATA shape ----------
function mapOnboarding(op){
  op = op || {};
  const lc = s => String(s==null?'':s).toLowerCase();
  const arr = v => Array.isArray(v) ? v : (v!=null && v!=='' ? [v] : []);
  const cap = s => s ? String(s).charAt(0).toUpperCase()+String(s).slice(1) : s;
  const pickBy = (m,name)=>{ if(!m||typeof m!=='object')return null; const k=lc(name);
    for(const key in m){ const kl=lc(key); if(kl===k||kl.includes(k)||k.includes(kl)) return m[key]; } return null; };
  const inList = (list,name)=>arr(list).some(x=>{const a=lc(x),b=lc(name);return a===b||a.includes(b)||b.includes(a);});
  const iconFor = name=>{ const n=lc(name);
    if(/dota|valorant|\bcs\b|league|\blol\b|fifa|apex|fortnite|gaming|\bgame/.test(n))return'gamepad';
    if(/football|soccer|basket|tennis|\bgym\b|\brun|box|climb|swim|cycl|sport/.test(n))return'football';
    if(/coffee|walk|dinner|\btea\b|brunch|drinks/.test(n))return'coffee';
    if(/movie|cinema|film|series|\bshow/.test(n))return'film';
    if(/\bai\b|startup|\btech|business|network|career|founder/.test(n))return'rocket';
    if(/archit4|architecture|design|\bart\b|photo|museum/.test(n))return'building';
    if(/language|spanish|english|french|german|italian|practice|jazz|music/.test(n))return'chat';
    if(/hik|nature|outdoor|travel|park/.test(n))return'pin';
    return'spark'; };

  const langs = arr(op.languages && (op.languages.comfortable||op.languages.fluent||op.languages.native));
  const areas = arr(op.geo && op.geo.comfortableAreas);
  const city  = areas[0] || op.city || '';
  const km    = op.geo && op.geo.maxDistanceKm;
  const ints  = arr(op.interests && op.interests.explicit);
  const rolesRaw = (op.interests && op.interests.roles) || {};
  const exp   = (op.interests && op.interests.experienceByInterest) || {};
  const games = (op.domains && op.domains.games) || {}, sport = (op.domains && op.domains.sport) || {};
  const langd = (op.domains && op.domains.language) || {}, net = (op.domains && op.domains.networking) || {};
  const sf = op.safety || {}, pm = op.permissions || {};

  function roleOf(name){
    const flat={}; (function eat(d){ if(d && typeof d==='object' && !Array.isArray(d)){
      for(const k in d){ const v=d[k]; if(v && typeof v==='object' && !Array.isArray(v)) eat(v); else if(v) flat[lc(k)]=v; } } })(rolesRaw);
    const k=lc(name); for(const kk in flat){ if(kk===k||kk.includes(k)||k.includes(kk)) return flat[kk]; }
    if((typeof rolesRaw==='string'||Array.isArray(rolesRaw)) && ints.length===1) return rolesRaw;
    return null;
  }
  const roleTxt = r => arr(r).map(cap).join(' / ');

  const interests = ints.map((name,i)=>{
    const kv=[], r=roleOf(name), e=pickBy(exp,name); const n=lc(name);
    if(r)kv.push(['Role', roleTxt(r)]);
    if(e)kv.push(['Experience', e]);
    if(inList(games.gamesList,name) || /dota|valorant|league|\bcs\b|apex|game/.test(n)){
      const p=pickBy(games.platformsByGame,name); if(p)kv.push(['Platform', p]);
      const rk=pickBy(games.rankByGame,name); if(rk)kv.push(['Rank / level', rk]);
      if(games.competitiveMode)kv.push(['Mode', cap(games.competitiveMode)]);
      if(games.toxicityPreference)kv.push(['Toxicity', String(games.toxicityPreference).replace(/_/g,' ')]);
    }
    if(inList(sport.sportsList,name)){
      const lv=pickBy(sport.skillLevelBySport,name); if(lv)kv.push(['Skill level', cap(lv)]);
      const tm=pickBy(sport.favoriteTeams,name) || (Array.isArray(sport.favoriteTeams)?sport.favoriteTeams.join(', '):null); if(tm)kv.push(['Team', tm]);
    }
    if(/language|spanish|english|french|german|italian|practice/.test(n)){
      if(langd.targetLanguage)kv.push(['Language', langd.targetLanguage]);
      if(langd.targetLevel)kv.push(['Level', langd.targetLevel]);
    }
    if(/network|startup|business|career|founder/.test(n)){
      if(net.industry)kv.push(['Industry', net.industry]); if(net.goal)kv.push(['Goal', net.goal]);
    }
    return {name, icon:iconFor(name), conf: i<2?'High':(kv.length?'Medium':'Low'), used:true, kv};
  });

  const snap=[];
  if(areas.length||km) snap.push({icon:'pin',   title:'Location',  value:[areas.join(' · '), km?('Max travel '+km+' km'):null].filter(Boolean).join(' · ')});
  if(langs.length)      snap.push({icon:'globe', title:'Languages', value:langs.join(' · ')});
  if(ints.length)       snap.push({icon:'spark', title:'Interests', value:ints.join(' · ')});
  snap.push({icon:'shield', title:'Safety', value:[sf.publicPlacesOnly!==false?'Public places':null, pm.useProfileForMatching?'Matching on':null, pm.allowAdjacentMatches!==false?'Adjacent on':null].filter(Boolean).join(' · ')||'Default'});

  const places=[];
  if(city) places.push({icon:'pin',  title:'City', value:city});
  if(areas.length>1 || (areas.length===1 && areas[0]!==city)) places.push({icon:'pin', title:'Comfortable areas', value:areas.join(', ')});
  if(km!=null) places.push({icon:'route', title:'Max travel', value:km+' km'});
  places.push({icon:'eye', title:'Location sharing', value:'Area only, never exact location'});

  const consent  = pm.useProfileForMatching!==false;   // implied by completing onboarding
  const remember = !!pm.rememberPreferences;           // "Remember preferences" -> learning consents
  const safety={
      autonomy:'ask', confirmShare:true, paused:false,
      publicFirst:   sf.publicPlacesOnly!==false,
      noLateNight:   sf.lateNight!==false,
      avoidAlcohol:  !!sf.avoidAlcohol,
      sharePlan:     !!sf.sharePlan,
      trustedContact: sf.trustedContact||null,
      useInterestsArea: consent, useFeedback: remember, inferNew: remember, noSensitive:true,
      suggestBeyond: !!pm.allowAdjacentMatches,
      publicMap:     !!pm.publicMap,
      datingMode:    !!pm.datingMode,
      verified:false,
      preferVerified: !!sf.verifiedOnly,
      blockedCount:0, excludeKnown:true };

  const conf=[];
  if(op.name) conf.push('Name is '+op.name);
  if(op.age)  conf.push(op.age+' years old');
  if(city)    conf.push('Lives in '+city);
  if(langs.length) conf.push('Speaks '+langs.join(' / '));
  ints.forEach(nm=>{ const r=roleOf(nm); conf.push((r?cap(arr(r)[0])+'s ':'Into ')+nm); });
  if(sf.publicPlacesOnly!==false) conf.push('Prefers public places');
  const knows={total:conf.length, confirmed:conf.length, inferred:0, temporary:0, confirmedList:conf, inferredList:[]};

  const memory=[];
  ints.forEach(nm=>{ const r=roleOf(nm), e=pickBy(exp,nm);
    memory.push({signal:(r?cap(arr(r)[0])+'s ':'Into ')+nm+(e?' ('+e+')':''), source:'Onboarding', confidence:'High', status:'Confirmed', used:true, updated:'Just now'}); });
  if(city) memory.push({signal:'Based in '+city+(km?', within '+km+' km':''), source:'Onboarding', confidence:'High', status:'Confirmed', used:true, updated:'Just now'});
  if(langs.length) memory.push({signal:'Comfortable in '+langs.join(', '), source:'Onboarding', confidence:'High', status:'Confirmed', used:true, updated:'Just now'});

  let f=0; [op.name, langs.length, areas.length, ints.length, op.summary, pm.useProfileForMatching!==undefined].forEach(x=>{ if(x)f++; });
  const confidence=Math.round(100*f/6);
  const sub=[city, langs.join(' / ')].filter(Boolean).join(' · ') || 'New profile';

  // Social Style + Goals: shown only if the profile carries them (onboarding doesn't collect them yet,
  // but the "Emulate onboarding" shortcut does, so the full card is inspectable).
  const social = (op.social && ((op.social.rows||[]).length || (op.social.vibe||[]).length))
    ? {rows:op.social.rows||[], vibe:op.social.vibe||[], depth:op.social.depth||[]} : {rows:[],vibe:[],depth:[]};
  const goals = (op.goals && ((op.goals.active||[]).length || (op.goals.optional||[]).length))
    ? {active:op.goals.active||[], optional:op.goals.optional||[]} : {active:[],optional:[]};

  const basics=[];
  if(op.gender||op.age) basics.push({icon:'person', title:'Basics', value:[cap(op.gender||''), op.age].filter(Boolean).join(' · ')||'—'});
  if(areas.length||city) basics.push({icon:'pin', title:'Location', value:[(areas.join(', ')||city), km?('Max '+km+' km'):null].filter(Boolean).join(' · ')});
  if(langs.length) basics.push({icon:'globe', title:'Languages', value:langs.join(' · ')});

  const data={ name:op.name||'You', subtitle:sub, verified:false, confidence,
    summaryLabel:"Kleal's summary", summary: op.summary||'',
    matchingPaths: ints.slice(0,3), snapshot:snap, interests, basics,
    social, availability:[], places, goals, safety, memory, knows,
    intents:[], plans:[], messages:[] };

  const tabs=['overview'];
  if(snap.length) tabs.push('snapshot');
  if(interests.length) tabs.push('interests');
  if(social.rows.length||social.vibe.length) tabs.push('social');
  if(places.length) tabs.push('places');
  if(goals.active.length||goals.optional.length) tabs.push('goals');
  tabs.push('safety');
  if(memory.length) tabs.push('memory');
  if(conf.length) tabs.push('knows');
  return {data, tabs};
}

// ---------------- screens ----------------
// Figma V3 (node 297-11116): the profile has FOUR sub-sections.
const ALL_TABS=[
  ['overview','Overview','My Kleal Profile'],
  ['interests','Interests','Interests'],
  ['social','Your personality','Your personality'],
  ['goals','Goals','Goals'],
  ['safety','Safety','Safety & Privacy'],
];
const TABS = ALL_TABS;
let cur = 'agenthome';   // main landing after onboarding
const TITLES={memory:'What Kleal remembers', intents:'Plans', search:'Explore', messages:'Messages', agenthome:'Home', notifs:'Notifications', buddychat:'Kleal'};   // screens reachable but not in the nav TABS
if(!DATA.notifs) DATA.notifs=[]; if(!DATA.intents) DATA.intents=[];   // buddy-agent stores
function setTab(id){ detail=null; cur=id; render(); }
// Overview is a hub of drill-in "Settings Rows"
const SECMETA={
  interests:['star','Interests','What you like doing with people'],
  social:['faceScan','Your personality','How you come across'],
  goals:['sun','Goals','What you want Kleal to help with'],
  safety:['userLock','Safety & Privacy','What Kleal can use, and your limits'],
};
function navRows(){
  return TABS.filter(t=>t[0]!=='overview').map(t=>{ const m=SECMETA[t[0]]||['star',t[2],''];
    return `<div class="card setrow" data-nav="${t[0]}"><div class="sic">${IC[m[0]]}</div>
      <div class="st"><div class="stt">${esc(m[1])}</div><div class="sts">${esc(m[2])}</div></div>
      <div class="sedit" data-act="editrow" data-row="${esc(m[1])}">${IC.wand}<span>Edit</span></div></div>`; }).join('');
}

function cbadge(c){ return `<span class="cbadge cb-${c}">${c}</span>`; }
function summaryRow(r, edit){ return `<div class="card srow"><div class="si">${IC[r.icon]||''}</div>
  <div class="st"><div class="stt">${esc(r.title)}</div><div class="stv">${esc(r.value)}</div></div>
  ${edit?`<div class="edit" data-act="editrow" data-row="${esc(r.title)}">${IC.edit}</div>`:''}</div>`; }
const UI={};  // persists toggle/checkbox state across re-renders (keyed control state)
if(_saved && _saved.ui){ Object.assign(UI, _saved.ui); }   // rehydrate control state across refresh
let _saveT=null;
function saveState(){ try{ localStorage.setItem(PKEY, JSON.stringify({_src:_psrc, data:DATA, ui:UI})); }catch(_e){}
  clearTimeout(_saveT); _saveT=setTimeout(()=>{ try{ fetch('/api/agent/save',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({state:{data:DATA,ui:UI}})}); }catch(_e){} }, 800); }
const ui=(k,def)=>(k&&UI[k]!==undefined)?UI[k]:def;
// ---- Safety & Privacy: typed rows built from the DATA.safety flags object ----
function sTt(label,desc,danger){ return `<div class="tt"><div class="ttl"${danger?' style="color:var(--danger)"':''}>${esc(label)}</div>${desc?`<div class="tts">${esc(desc)}</div>`:''}</div>`; }
function sTog(label,desc,on,flag){ return `<div class="trow">${sTt(label,desc)}
  <div class="sw ${on?'on':''}" data-sflag="${flag}"><i></i></div></div>`; }
function sAct(label,desc,val,act,danger){ return `<div class="trow" data-act="${act}">${sTt(label,desc,danger)}
  <div class="rt">${val?`<span class="sval">${esc(val)}</span>`:''}${IC.chevR}</div></div>`; }
function sStat(label,desc,val,btn,act,icon){
  const right = btn ? `<span class="sval">${esc(val)}</span><button class="sbtn" data-act="${act}">${esc(btn)}</button>`
                    : `<span class="sval">${esc(val)}</span>${icon||''}`;
  return `<div class="trow">${sTt(label,desc)}<div class="rt">${right}</div></div>`; }
function sChoice(label,desc,options,sel,act){ return `<div class="crow2">${sTt(label,desc)}
  <div class="seg">${options.map((o,i)=>`<button class="${i===sel?'sel':''}" data-schoice="${act}" data-i="${i}">${esc(o)}</button>`).join('')}</div></div>`; }
function sSub(label){ return `<div class="ssub">${esc(label)}</div>`; }

function safetyGroups(f){ f=f||{}; return [
  {t:'How Kleal acts for you', c:'The big levers — your agent’s autonomy and a one-tap pause.', items:[
    {k:'choice', label:'When Kleal finds someone', desc:'Ask before reaching out, or let Kleal introduce you automatically.',
      options:['Ask me first','Introduce automatically'], sel:(f.autonomy==='auto'?1:0), act:'autonomy'},
    {k:'tog', label:'Confirm before sharing my details', desc:'Ask before revealing your name, photo or contact — even when Kleal arranges plans for you.', on:f.confirmShare!==false, flag:'confirmShare'},
    {k:'tog', label:'Pause Kleal', desc:'Stop all new matching and outreach. Your profile and memory stay saved.', on:!!f.paused, flag:'paused'},
  ]},
  {t:'Meeting in person', c:'How Kleal keeps real-world plans safe. Every switch here: on = safer.', items:[
    {k:'tog', label:'Keep first meetups public', desc:'First meets stay in cafes, parks and other public spots.', on:f.publicFirst!==false, flag:'publicFirst'},
    {k:'tog', label:'No solo late-night meets', desc:'Kleal avoids one-on-one plans late at night.', on:f.noLateNight!==false, flag:'noLateNight'},
    {k:'tog', label:'Avoid alcohol-focused venues', desc:'Skip bars and heavy-drinking spots for first meets.', on:!!f.avoidAlcohol, flag:'avoidAlcohol'},
    {k:'tog', label:'Share my plan with a trusted contact', desc:'Auto-send who, where and when to someone you choose, with a check-in after.', on:!!f.sharePlan, flag:'sharePlan'},
    {k:'stat', label:'Trusted contact', desc:'Choose who receives your plans. They’ll be told you added them.', val:(f.trustedContact||'Not set'), btn:(f.trustedContact?'Change':'Add'), act:'trusted-contact'},
  ]},
  {t:'What Kleal may use & remember', c:'Your consent for what Kleal reads and learns. On = Kleal may use it.', items:[
    {k:'tog', label:'Match on my interests & area', desc:'Use what you like and your city area — never your exact location.', on:f.useInterestsArea!==false, flag:'useInterestsArea'},
    {k:'tog', label:'Learn from my feedback & activity', desc:'Use your ratings and which plans you accept or decline.', on:f.useFeedback!==false, flag:'useFeedback'},
    {k:'tog', label:'Let Kleal infer new things about me', desc:'Allow guesses beyond what you stated, like preferred venues.', on:f.inferNew!==false, flag:'inferNew'},
    {k:'sub', label:'Guardrails'},
    {k:'tog', label:'Never infer sensitive traits', desc:'Keep health, religion, politics and orientation out of memory.', on:f.noSensitive!==false, flag:'noSensitive'},
    {k:'act', label:'Review what Kleal remembers', desc:'See, correct or forget individual signals.', act:'review-memory'},
  ]},
  {t:'How people find you', c:'Your reach and visibility. On = more reach, off = more private.', items:[
    {k:'tog', label:'Suggest people beyond my usual circles', desc:'Occasionally propose friends-of-interests and plans outside your usuals.', on:f.suggestBeyond!==false, flag:'suggestBeyond'},
    {k:'tog', label:'Show me on the discovery map', desc:'Let others come across you on the public map.', on:!!f.publicMap, flag:'publicMap'},
    {k:'tog', label:'Dating mode', desc:'Off by default. Turn on to let Kleal suggest dating intros too.', on:!!f.datingMode, flag:'datingMode'},
  ]},
  {t:'Verification & people', c:'Who Kleal will introduce you to. On = more protective.', items:[
    {k:'stat', label:'My verification', desc:'Verify your photo and ID so others know you’re real.',
      val:(f.verified?'Verified':'Not verified'), btn:(f.verified?null:'Verify'), act:'verify-me', icon:(f.verified?IC.verify:'')},
    {k:'tog', label:'Prefer verified people', desc:'Kleal favours verified profiles when it matches you.', on:f.preferVerified!==false, flag:'preferVerified'},
    {k:'act', label:'Blocked people', desc:'People Kleal will never match or introduce you to.', val:((f.blockedCount||0)+' blocked'), act:'blocked'},
    {k:'tog', label:'Don’t match me with people I may know', desc:'Exclude coworkers, exes and phone contacts from suggestions.', on:f.excludeKnown!==false, flag:'excludeKnown'},
    {k:'act', label:'Report a problem or get help', desc:'Report someone or reach the safety centre.', act:'report'},
  ]},
  {t:'Your data', c:'Your data rights. Take a copy or erase everything, anytime.', items:[
    {k:'act', label:'Download my data', desc:'Export everything Kleal holds about you.', act:'export-data'},
    {k:'act', label:'Delete my account & memory', desc:'Permanently erase your profile and everything Kleal learned. Any in-flight introductions are cancelled.', act:'delete-account', danger:true},
  ]},
]; }
function safetyRow(it){
  if(it.k==='tog')    return sTog(it.label,it.desc,it.on,it.flag);
  if(it.k==='act')    return sAct(it.label,it.desc,it.val,it.act,it.danger);
  if(it.k==='stat')   return sStat(it.label,it.desc,it.val,it.btn,it.act,it.icon);
  if(it.k==='choice') return sChoice(it.label,it.desc,it.options,it.sel,it.act);
  if(it.k==='sub')    return sSub(it.label);
  return ''; }
function checkRow(label,on,key){ on=ui(key,on); return `<div class="crow"><div class="cbx ${on?'on':''}" data-cbx data-uk="${key||''}">${on?IC.check:''}</div>
  <div class="cl">${esc(label)}</div></div>`; }

let editingSummary=false;
function scr_overview(){
  const d=DATA;
  const sum = editingSummary
    ? `<textarea id="sumta" class="sumta">${esc(d.summary)}</textarea>
       <div class="linkrow"><button data-act="savesum">Save</button><button data-act="cancelsum">Cancel</button></div>`
    : `<div class="sumtxt">${esc(d.summary||"Kleal will summarise you here as it learns more.")}</div>
       <button class="bigbtn primary" style="margin-top:16px" data-act="createintent">Create intent</button>`;
  return `<div class="stack fade">
    <div class="card idcard">
      <div class="idrow"><div class="ava">${IC.person}</div>
        <div class="it"><div class="nm">${esc(d.name)} ${d.verified?`<span class="badge-verify">${IC.verify}</span>`:'<span class="reddot"></span>'}</div></div></div>
      <div class="confrow2"><span class="l">Profile confidence</span><span class="confpct">${d.confidence}%</span></div>
      <div class="track"><i style="width:${d.confidence}%"></i></div></div>
    ${(d.basics||[]).map(r=>summaryRow(r,true)).join('')}
    <div class="card pad"><div class="sumhead"><div class="sumlbl">${esc(d.summaryLabel)}</div><span class="updated">Updated today</span></div>${sum}</div>
    <div class="stack" style="margin-top:6px">${navRows()}</div>
  </div>`;
}
function emptyState(title,sub){ return `<div class="empty fade"><div class="eic">${IC.spark}</div>
  <div class="etx">${esc(title)}</div>${sub?`<div class="esub">${esc(sub)}</div>`:''}</div>`; }
function scr_snapshot(){ if(!DATA.snapshot.length) return emptyState("Nothing to match on yet","Kleal fills this in as it learns about you.");
  return `<div class="stack fade">${DATA.snapshot.map(r=>summaryRow(r,true)).join('')}</div>`; }

function interestSummary(it){
  const kv=(it.kv||[]).map(k=>k[1]).filter(Boolean);
  const base = (it.what&&it.what.length) ? it.what.join(', ') : kv.join(', ');
  return base || ("Kleal is still learning about your "+it.name+".");
}
let expInt=null;  // which interest is expanded (V3 inline)
function scr_interests(){
  const d=DATA;
  if(!(d.interests||[]).length) return `<div class="fade">${emptyState("No interests yet","Tell Kleal what you're into and they'll show up here.")}<button class="bigbtn primary" style="margin-top:8px" data-act="add-interests">Add interests</button></div>`;
  const exp = expInt!==null ? expInt : ((d.interests[0]||{}).name);
  let rows='';
  for(const it of d.interests){
    const on = it.used!==false;
    rows+=`<div class="card irow2"><div class="irleft" data-open="${esc(it.name)}"><div class="ii2">${IC[it.icon]||IC.spark}</div><div class="inm2">${esc(it.name)}</div></div>
      <div class="sw ${on?'on':''}" data-imatch="${esc(it.name)}"><i></i></div></div>`;
    if(it.name===exp){
      rows+=`<div class="card intexp"><div class="intimg"></div><div class="pad">
        <div class="sumhead"><div class="sumlbl">Kleal's summary</div><span class="updated">Updated today</span></div>
        <div class="sumtxt">${esc(interestSummary(it))}</div>
        <div class="intedit"><div class="intav"></div>
          <button class="editbtn" data-act="edit-int" data-int="${esc(it.name)}">${IC.wand}<span>Edit</span></button></div></div></div>`;
    }
  }
  return `<div class="fade"><div class="intsub">When a toggle is on, Kleal uses that interest for matching.</div>
    <div class="stack">${rows}</div>
    <button class="bigbtn primary" style="margin-top:14px" data-act="add-interests">Add interests</button></div>`;
}
function scr_domain(it){  // expanded detail (Dota 2 / Spanish style key-value)
  return `<div class="fade"><div class="card dcard">
    <div class="dtop"><span class="pill-on">Used for matching · ON</span>${cbadge(it.conf)}</div>
    ${it.source?`<div class="dsrc">Source: ${esc(it.source)}</div>`:'<div style="height:6px"></div>'}
    ${(it.what||[]).length?`<div class="seclbl">What exactly</div><div class="bullets" style="margin-bottom:6px">${it.what.map(w=>`<div class="bullet"><span class="dot"></span>${esc(w)}</div>`).join('')}</div>`:''}
    ${(it.kv||[]).map(k=>`<div class="kv"><span class="k">${esc(k[0])}</span><span class="v">${esc(k[1])}</span></div>`).join('')}
    ${it.expansion?`<div class="expansion">${esc(it.expansion)}</div>`:''}
    <div class="dactions"><button class="txtbtn" data-act="edit-int" data-int="${esc(it.name)}">Edit</button>
      <button class="txtbtn" data-act="dontuse-int" data-int="${esc(it.name)}">Don’t use</button>
      <button class="btn-remove" data-act="remove-int" data-int="${esc(it.name)}">Remove</button></div></div></div>`;
}
function personalitySummary(s){
  const vibe=(s.vibe||[]).filter(v=>v[1]).map(v=>v[0]);
  const rm={}; (s.rows||[]).forEach(r=>rm[r.title]=r.value);
  const out=[];
  if(vibe.length) out.push("You come across as "+vibe.slice(0,3).join(', ')+".");
  if(rm['Conversation depth']) out.push("You like "+rm['Conversation depth'].toLowerCase()+".");
  if(rm['Best first format']) out.push("Best first meet: "+rm['Best first format'].toLowerCase()+".");
  if(rm['Group comfort']) out.push("Most comfortable "+rm['Group comfort'].toLowerCase()+".");
  return out.join(' ');
}
function scr_social(){  // "Your personality"
  const s=DATA.social;
  const has = s.rows.length || s.vibe.length || s.depth.length;
  const txt = has ? personalitySummary(s) : "Take the test and Kleal will describe how you come across and who you click with.";
  return `<div class="fade" style="text-align:center">
    <div class="persimg">${IC.faceScan}</div>
    <button class="bigbtn primary" data-act="personality-test">Take your personality test</button>
    <div class="card pad" style="text-align:left;margin-top:16px">
      <div class="sumhead"><div class="sumlbl">Kleal's summary</div><span class="updated">Updated today</span></div>
      <div class="sumtxt">${esc(txt)}</div>
      <div class="intedit"><div class="intav"></div>
        <button class="editbtn" data-act="edit-personality">${IC.wand}<span>Edit</span></button></div></div></div>`;
}
function scr_places(){
  if(!DATA.availability.length && !DATA.places.length) return emptyState("No places or times yet","Kleal will note where and when you like to meet.");
  return `<div class="fade"><div class="rowhead"><div class="seclbl">Usual availability</div></div>
    <div class="stack">${DATA.availability.length?DATA.availability.map(r=>summaryRow(r,false)).join(''):`<div class="seccap">Not set yet — Kleal will learn your usual times.</div>`}</div>
    <div class="rowhead"><div class="seclbl">Places</div></div>
    <div class="stack">${DATA.places.length?DATA.places.map(r=>summaryRow(r,false)).join(''):`<div class="seccap">Not set yet.</div>`}</div></div>`;
}
function scr_goals(){
  const g=DATA.goals;
  const active=(g.active||[]);
  const sub=`<div class="intsub">Be thoughtful with your goals. Others can see them when they invite you to a plan, and Kleal uses them to find the best matches.</div>`;
  if(!active.length) return `<div class="fade">${sub}${emptyState("No goals yet","Add a goal and Kleal will start finding the right people and plans.")}<button class="bigbtn primary" style="margin-top:8px" data-act="add-goal">Add goal</button></div>`;
  const cards=active.map((x,i)=>`<div class="card goalcard"><div class="gc"><div class="gci">${IC.sun}</div>
    <div class="gct"><div class="gctn">Goal #${i+1}</div><div class="gcts">${esc(x)}</div></div>
    <div class="gedit" data-act="edit-goal" data-goal="${i}">${IC.edit}</div></div></div>`).join('');
  return `<div class="fade">${sub}<div class="stack">${cards}</div>
    <button class="bigbtn primary" style="margin-top:14px" data-act="add-goal">Add goal</button></div>`;
}
function scr_safety(){
  const groups=safetyGroups(DATA.safety).map(gr=>{
    let inner='';
    gr.items.forEach((it,i)=>{
      inner+=safetyRow(it);
      const next=gr.items[i+1];
      if(next && it.k!=='sub' && next.k!=='sub') inner+='<div class="divider"></div>';
    });
    return `<div class="rowhead"><div class="seclbl">${esc(gr.t)}</div></div>
      <div class="seccap">${esc(gr.c)}</div><div class="card">${inner}</div>`;
  }).join('');
  return `<div class="fade">
    <div class="card pad" style="margin-bottom:4px"><div class="sumlbl" style="color:var(--coral700)">You’re in control</div>
      <div class="sumtxt" style="font-size:13.5px;color:var(--muted)">Kleal never acts without your say-so. It shares your city area, never your exact location, learns only what you allow, and everything here is reversible anytime.</div></div>
    ${groups}</div>`;
}
function scr_memory(){
  if(!DATA.memory.length) return emptyState("No signals yet","As you use Kleal, everything it learns shows up here.");
  return `<div class="stack fade">${DATA.memory.map((m,i)=>`<div class="card sig">
    <div class="stopline"><div class="ssig">${esc(m.signal)}</div><span class="stbadge st-${m.status}">${m.status}</span></div>
    <div class="smeta">Source: ${esc(m.source)}<br>Confidence: ${esc(m.confidence)} · Used for matching: ${m.used===false?'No':'Yes'}<br>Last updated: ${esc(m.updated)}</div>
    <div class="dactions" style="margin-top:12px"><button class="txtbtn" data-act="edit-sig" data-sig="${i}">Edit</button>
      <button class="txtbtn" data-act="dontuse-sig" data-sig="${i}">${m.used===false?'Use again':'Don’t use'}</button>
      <button class="txtbtn" style="color:var(--danger)" data-act="remove-sig" data-sig="${i}">Remove</button></div>
    </div>`).join('')}</div>`;
}
function scr_knows(){
  const k=DATA.knows;
  if(!(k.confirmedList||[]).length && !(k.inferredList||[]).length) return emptyState("Nothing tracked yet","Kleal builds this summary as it gets to know you.");
  return `<div class="fade"><div class="card">
      <div class="statbig"><span class="n">${k.total}</span><span class="l">signals tracked</span></div>
      <div style="display:flex">${[[k.confirmed,'confirmed'],[k.inferred,'inferred'],[k.temporary,'temporary']]
        .map(t=>`<div class="stat" style="flex:1"><div class="n">${t[0]}</div><div class="l">${t[1]}</div></div>`).join('')}</div>
    </div>
    <div class="rowhead"><div class="h2">Confirmed</div><div class="seeall">See All</div></div>
    <div class="card">${k.confirmedList.map((x,i)=>checkRow(x,true,'k-c-'+i)+(i<k.confirmedList.length-1?'<div class="divider"></div>':'')).join('')}</div>
    <div class="rowhead"><div class="h2">Inferred</div><div class="seeall">See All</div></div>
    <div class="card">${k.inferredList.map((x,i)=>checkRow(x,false,'k-i-'+i)+(i<k.inferredList.length-1?'<div class="divider"></div>':'')).join('')}</div></div>`;
}
// ================= V4: intents · intent chat · discovery · messages =================
let curIntent=null, intentLaunched=false, agentBusy=false;
function openIntent(it, launched){ curIntent=it||null; intentLaunched=!!launched; cur='intentchat'; render(); }
function capw(s){ s=String(s==null?'':s); return s.charAt(0).toUpperCase()+s.slice(1); }
// Feedback loop: tell the backend the owner's accept/reject so future ranking learns (fire-and-forget).
function postFeedback(name,decision){ try{ fetch('/api/agent/feedback',{method:'POST',
  headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,decision:decision})}); }catch(_e){} }
// Online fallback UI: when 0 offline matches — go live, or broaden the search (each option re-matches for real).
function fallbackCard(fb){
  const rooms=(fb.room&&fb.room.options||[]).map(o=>`<button class="chip" data-act="live" data-kind="${esc(o.id)}" style="margin:4px 6px 0 0">${esc(o.label)}</button>`).join('');
  const sugg=(fb.suggestions||[]).map(s=>`<button class="chip" data-act="broaden" data-kind="${esc(s.id)}" style="margin:4px 6px 0 0">${esc(s.label)}</button>`).join('');
  return `<div style="padding:12px 16px 16px"><div class="cands" style="margin-bottom:8px">${esc(fb.note||'No offline matches right now.')}</div>
    <div style="font-size:11px;color:var(--muted);margin:6px 0 2px">Go live</div>${rooms}
    <div style="font-size:11px;color:var(--muted);margin:10px 0 2px">Broaden the search</div>${sugg}</div>`;
}
// A fallback broaden action re-runs the plan with a relaxed scope override — real re-matching, not a stub.
async function broadenIntent(kind){
  if(!curIntent) return;
  const cur=curIntent.intent||{}; let ov=null;
  if(kind==='inexact') ov={exactMatchRequired:false,adjacentAllowed:true,broadAllowed:true};
  else if(kind==='adjacent') ov={adjacentAllowed:true,broadAllowed:true};
  else if(kind==='radius') ov={radiusKm:Math.max(30,(+cur.radiusKm||15)+20),mode:'offline'};
  else { addNotif('intent','Still searching “'+(curIntent.title||'plan')+'”','Kleal will ping you when someone fits',curIntent.id||null); saveState(); toast('Kleal keeps searching in the background'); return; }
  toast('Broadening the search…');
  let r; try{ r=await fetch('/api/agent/plan',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({query:curIntent.query,profile:{name:DATA.name||''},override:ov})}).then(x=>x.json()); }catch(e){ r=null; }
  if(r&&r.candidates&&r.candidates.length){ curIntent.candidates=r.candidates; curIntent.fallback=null;
    curIntent.intent=r.intent; curIntent.confidence=r.candidates[0].score; toast(r.candidates.length+' matches after broadening'); }
  else { curIntent.fallback=(r&&r.fallback)||curIntent.fallback; toast('Still no offline matches — try going live'); }
  render(); saveState();
}
// Buddy agent: free-text request -> real structured intent + ranked candidates (backend /api/agent/plan).
async function runAgent(query){
  query=(query||'').trim(); if(!query||agentBusy) return;
  agentBusy=true; curIntent={pending:true, query:query}; intentLaunched=false; cur='intentchat'; render();
  let r; try{
    r=await fetch('/api/agent/plan',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({query:query, profile:{name:DATA.name||''}})}).then(x=>x.json());
  }catch(e){ r=null; }
  agentBusy=false;
  if(!r||!r.intent){ curIntent={title:'New plan',tags:[],query:query,confidence:0,candidates:[],spec:[],error:true}; render(); return; }
  const it=r.intent, cands=r.candidates||[];
  const reach = it.exactMatchRequired?'Exact matches only':(it.broadAllowed===false?'Same activity only':(it.adjacentAllowed===false?'Same + related':'Adjacent + related'));
  const area = (it.place||'Public places nearby')+(it.mode==='offline'&&it.radiusKm?(' · within '+it.radiusKm+' km'):'');
  curIntent={ title:it.title||'New plan', tags:it.topics||[], query:query, type:it.type, role:it.role,
    intent:it, fallback:r.fallback||null,
    confidence:cands[0]?cands[0].score:70, candidates:cands,
    spec:[['moon','Mode',capw(it.mode||'Offline')],['users','Format',it.format||'1:1 or small group'],
          ['clock','Time',it.time||'Flexible'],['pin','Area',area],
          ['shield','Safety',it.verifiedOnly?'Verified people only':'Public places only'],
          ['compass','Reach',reach],['eye','Visibility','Via Kleal only']] };
  intentLaunched=false; render();
}
function intentSpec(it){ const s=it.spec||[]; return s.map((r,i)=>`<div class="specrow"><div class="spi">${IC[r[0]]||IC.spark}</div>
  <div class="sl">${esc(r[1])}</div><div class="sv">${esc(r[2])}</div></div>${i<s.length-1?'<div class="divider"></div>':''}`).join(''); }

// ===== Conversational "Create intent": Kleal collects the essentials + validates, THEN builds the card =====
// Replaces the old "any text -> instant card" behaviour: /api/buddy/intent-build runs a short dialogue
// (gibberish -> ask again; missing when/format -> ask; enough -> ready) and only then do we build a card.
let intentMsgs=[], intentBusy=false;
function openCreateIntent(){ curIntent=null; intentLaunched=false;
  intentMsgs=[{who:'them',text:"Что хочешь устроить? Опиши, чем заняться — например «кофе и поговорить про ИИ сегодня вечером» или «найти напарника в зал на неделе»."}];
  cur='intentchat'; render(); }
async function intentTurn(text){ text=(text||'').trim(); if(!text||intentBusy) return;
  intentBusy=true; intentMsgs.push({who:'me',text}); intentMsgs.push({who:'them',text:'…',loading:true}); render();
  let r; try{ r=await fetch('/api/buddy/intent-build',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({messages:intentMsgs.filter(m=>!m.loading).map(m=>({role:m.who==='me'?'user':'assistant',content:m.text})),
      profile:buddyProfile()})}).then(x=>x.json()); }catch(e){ r=null; }
  intentMsgs=intentMsgs.filter(m=>!m.loading); intentBusy=false;
  if(!r){ intentMsgs.push({who:'them',text:'Связь пропала — повтори, пожалуйста.'}); render(); return; }
  intentMsgs.push({who:'them',text:r.reply||'…'}); render(); saveState();
  if(r.ready && r.intent) buildIntentCard(r.intent);      // enough detail -> structure the card
}
async function buildIntentCard(intent){
  curIntent={pending:true, query:''}; render();
  let r; try{ r=await fetch('/api/agent/match',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({intent:intent, profile:{name:DATA.name||''}, ctx:{self:DATA.name||''}})}).then(x=>x.json()); }catch(e){ r=null; }
  const cands=(r&&r.candidates)||[]; const it=intent;
  const reach=it.exactMatchRequired?'Exact matches only':(it.broadAllowed===false?'Same activity only':(it.adjacentAllowed===false?'Same + related':'Adjacent + related'));
  const area=(it.place||'Public places nearby')+(it.mode==='offline'&&it.radiusKm?(' · within '+it.radiusKm+' km'):'');
  curIntent={ title:it.title||it.activity||'New plan', tags:it.tags||it.topics||[], query:'', type:it.type, role:it.role, intent:it,
    fallback:(r&&r.fallback)||null, confidence:cands[0]?cands[0].score:70, candidates:cands,
    spec:[['moon','Mode',capw(it.mode||'Offline')],['users','Format',it.format||'1:1 or small group'],
          ['clock','Time',it.time||'Flexible'],['pin','Area',area],
          ['shield','Safety',it.verifiedOnly?'Verified people only':'Public places only'],
          ['compass','Reach',reach],['eye','Visibility','Via Kleal only']] };
  intentLaunched=false; render(); saveState(); }

// ---------- Phase 2 (prod): LLM agent-to-agent negotiation on launch ----------
async function negotiateIntent(){
  if(!curIntent){ return; }
  if(curIntent.negotiated){ saveCurIntent(); return; }
  curIntent.negotiating=true; render();
  let r; try{ r=await fetch('/api/agent/negotiate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({intent:curIntent, candidates:curIntent.candidates||[]})}).then(x=>x.json()); }catch(e){ r=null; }
  if(r&&r.candidates&&r.candidates.length){ curIntent.candidates=r.candidates;
    curIntent.confidence=(r.candidates[0]&&r.candidates[0].score)||curIntent.confidence; }
  curIntent.negotiating=false; curIntent.negotiated=true; curIntent.status='matched';
  saveCurIntent(); render();
  const ag=(curIntent.candidates||[]).filter(c=>c.agree).length;
  toast(ag+' agent'+(ag===1?'':'s')+' agreed — approve an intro to connect');
}
// ---------- Phase 1: saved intents ----------
function openSavedIntent(id){ const it=(DATA.intents||[]).find(x=>x.id===id); if(!it)return; curIntent=it; intentLaunched=true; cur='intentchat'; render(); }
function saveCurIntent(){
  if(curIntent && !curIntent.id){
    curIntent.id='i'+String(Date.now()); curIntent.status='searching'; curIntent.createdAt='just now';
    DATA.intents=DATA.intents||[]; DATA.intents.unshift(curIntent);
    const cs=curIntent.candidates||[];
    addNotif('intent','“'+curIntent.title+'” — '+cs.length+' matches', cs.filter(c=>c.agree).length+' agreed · tap to review', curIntent.id);
  }
  saveState();
}
// ---------- Phase 4: notifications ----------
function addNotif(kind,title,body,ref){ DATA.notifs=DATA.notifs||[];
  DATA.notifs.unshift({id:'n'+String(Date.now())+Math.round(Math.abs(Math.sin(DATA.notifs.length))*1000),kind:kind,title:title,body:body,ref:ref,read:false,time:'now'}); }
function unreadNotifs(){ return (DATA.notifs||[]).filter(n=>!n.read).length; }
function scr_notifications(){
  const list=DATA.notifs||[];
  if(!list.length) return emptyState("No notifications yet","When Kleal finds people or agents agree, it shows up here.");
  return `<div class="stack fade" style="padding-top:4px">${list.map(n=>`<div class="card notifrow ${n.read?'':'unread'}" data-notif="${n.id}">
    <div class="nnic">${n.kind==='match'?IC.users:IC.spark}</div>
    <div class="nnt"><div class="nntt">${esc(n.title)}</div><div class="nnts">${esc(n.body)}</div></div>
    <div class="nntime">${esc(n.time)}</div></div>`).join('')}</div>`;
}
function openNotif(id){ const n=(DATA.notifs||[]).find(x=>x.id===id); if(!n)return; n.read=true;
  if(n.kind==='match' && matchWith){ cur='matchchat'; render(); saveState(); return; }
  if(n.ref){ openSavedIntent(n.ref); saveState(); return; }
  render(); saveState();
}
// ---------- Phase 2: match chat (blurred photo clears as you talk) ----------
let matchWith=null;
// find (or create) the PERSISTENT thread for a candidate in DATA.messages, so the conversation shows up
// in the Messages tab and survives navigation — the bug was that intros lived only in a transient variable.
function msgThreadFor(cand, intent){
  DATA.messages=DATA.messages||[];
  const key=String((cand&&cand.name)||'').toLowerCase();
  let t=DATA.messages.find(m=>!m.kleal && String(m.who||'').toLowerCase()===key);
  if(!t){ t={who:(cand&&cand.name)||'Someone', last:'', time:'now', kleal:false, msgs:[]};
    DATA.messages.unshift(t); }
  t.cand=cand; if(intent) t.intent=intent;
  return t;
}
async function approveIntro(cand, intent){
  if(!cand) return;
  const t=msgThreadFor(cand, intent);
  t.msgs=[{who:'them',text:'…'}]; t.loading=true; t.last='…';
  t.fromMessages=false; t.fromBuddy=false;       // opened from an intro; back goes to the intent/buddy chat
  matchWith=t; cur='matchchat'; render();
  let r; try{ r=await fetch('/api/agent/intro',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({intent:intent||{}, candidate:cand})}).then(x=>x.json()); }catch(e){ r=null; }
  const opener=(r&&r.opener)||('Hey! Looks like we both like '+(((intent||{}).tags||[]).join(', ')||'similar things')+' — want to make a plan?');
  t.msgs=[{who:'them',text:opener}]; t.loading=false; t.last=opener; t.time='now';
  postFeedback(cand.name,'accepted');   // feedback loop: approving an intro teaches the ranker
  addNotif('match','You matched with '+cand.name, 'Their agent agreed — say hi', null);
  render(); saveState();
}
function openMsgThread(i){
  const t=(DATA.messages||[])[i]; if(!t) return;
  if(t.kleal){ openBuddy(''); return; }          // the pinned Kleal thread -> the agent chat
  matchWith=t; matchWith.fromMessages=true; cur='matchchat'; render(); saveState();
}
function scr_matchchat(){
  const m=matchWith; if(!m) return scr_agenthome();
  const mine=m.msgs.filter(x=>x.who==='me').length; const blur=Math.max(0, 9-mine*3);
  const thread=m.msgs.map(x=>x.who==='me'?`<div class="mbub">${esc(x.text)}</div>`
    :`<div class="kbub">${m.loading&&x.text==='…'?'<span class="typing3"><i></i><i></i><i></i></span>':esc(x.text)}</div>`).join('');
  return `<div class="fade"><div class="matchhead">
      <div class="mava" style="filter:blur(${blur}px)">${esc(String(m.cand.name||'?')[0])}</div>
      <div class="mmeta"><div class="mnm">${esc(m.cand.name)} <span class="mscore">${m.cand.score}% match</span></div>
        <div class="mhint">Photo clears as you chat${blur>0?' — keep going':' ✓'}</div></div></div>
    <div class="thread" style="padding-top:12px">${thread}</div>
    <div class="composer"><input id="mcin" class="cin cinput" placeholder="Message ${esc(m.cand.name)}…"><button class="csend" data-act="match-send">${IC.send}</button></div></div>`;
}

// ================= BUDDY AGENT — the conversational agent you just talk to =================
// You chat freely; the buddy quietly gathers your SIGNALS and, when you want to meet someone,
// it calls the matching agent (server-side, agent-to-agent) and drops the best match into the chat.
let buddyMsgs=[], buddySignals={}, buddyBusy=false;
function buddyProfile(){   // seed the buddy with what we already know about the user
  return { name:DATA.name||'', interests:(DATA.interests||[]).map(i=>({name:i.name})),
           city:((DATA.subtitle||'').split('·')[0]||'').trim()||null };
}
function fmtTime(t){ const d=t?new Date(t):new Date(); let h=d.getHours(),m=d.getMinutes(); const ap=h<12?'AM':'PM'; h=h%12||12; return h+':'+(m<10?'0':'')+m+' '+ap; }
function openBuddy(first){
  cur='buddychat';
  if(!buddyMsgs.length) buddyMsgs=[{who:'them',text:"Hey dear! How can I help you?",hello:true}];
  render();
  if(first && String(first).trim()) buddyTurn(first);
}
async function buddyTurn(text){
  text=(text||'').trim(); if(!text||buddyBusy) return;
  buddyBusy=true; buddyMsgs.push({who:'me',text,t:Date.now()}); buddyMsgs.push({who:'them',text:'…',loading:true}); render();
  let r; try{
    r=await fetch('/api/buddy/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ messages:buddyMsgs.filter(m=>!m.loading).map(m=>({role:m.who==='me'?'user':'assistant',content:m.text})),
                            profile:buddyProfile(), signals:buddySignals })}).then(x=>x.json());
  }catch(e){ r=null; }
  buddyMsgs=buddyMsgs.filter(m=>!m.loading); buddyBusy=false;
  if(!r){ buddyMsgs.push({who:'them',text:'I lost the connection for a second — say that again?',t:Date.now()}); render(); return; }
  buddySignals=r.signals||buddySignals;
  buddyMsgs.push({who:'them', text:r.reply||'…', t:Date.now(), match:(r.match&&r.match.top)?r.match:null});
  if(r.match&&r.match.top) addNotif('match','Kleal found you a match: '+r.match.top.name, (r.match.top.reasons||[])[0]||'tap to connect', null);
  render(); saveState();
}
// browser-native dictation for the mic button — no backend needed; graceful toast where unsupported
let _rec=null;
function buddyMic(){
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  const mic=document.querySelector('.bc2-mic');
  if(!SR){ toast('Voice input isn’t supported in this browser'); return; }
  if(_rec){ try{_rec.stop();}catch(_e){} return; }
  _rec=new SR(); _rec.lang='ru-RU'; _rec.interimResults=true; _rec.continuous=false;
  _rec.onresult=(e)=>{ const el=document.getElementById('bcin'); if(!el)return; let s=''; for(let k=0;k<e.results.length;k++) s+=e.results[k][0].transcript; el.value=s; };
  _rec.onend=()=>{ _rec=null; if(mic)mic.classList.remove('on'); };
  _rec.onerror=()=>{ _rec=null; if(mic)mic.classList.remove('on'); };
  try{ _rec.start(); if(mic)mic.classList.add('on'); toast('Listening…'); }catch(_e){ _rec=null; }
}
function scr_buddychat(){
  const hd=`<div class="chd">
    <button class="chd-back" data-act="buddy-back">${IC.back}<span>Back</span></button>
    <div class="chd-pills">
      <button class="chd-pill" data-act="buddy-profile">${IC.person}<span>Profile</span></button>
      <button class="chd-pill" data-act="buddy-create"><span class="pl">+</span><span>Create Intent</span></button>
    </div></div>`;
  const thread=buddyMsgs.map((x,i)=>{
    if(x.who==='me') return `<div class="mrow"><div class="mbub">${esc(x.text)}</div><div class="btime r">${fmtTime(x.t)}</div></div>`;
    if(x.hello) return `<div class="khello"><div class="kav" style="width:44px;height:44px"></div><div class="khtxt">${esc(x.text)}</div></div>`;
    const first=(i===0)||buddyMsgs[i-1].who!=='them'||buddyMsgs[i-1].hello;   // avatar only on the first of a run
    const inner=x.loading?'<span class="typing3"><i></i><i></i><i></i></span>':esc(x.text).replace(/\n/g,'<br>');
    const time=x.loading?'':(x.t?`<div class="btime">${fmtTime(x.t)}</div>`:'');
    const row=`<div class="krow"><div class="kav${first?'':' sp'}"></div><div class="kcol"><div class="kbub">${inner}</div>${time}</div></div>`;
    if(x.match&&x.match.top){ const t=x.match.top; const why=(t.reasons||[]).slice(0,2).join(' · ');
      return row+`<div class="card" style="margin:2px 0 2px 43px"><div class="candrow">
        <div class="candav">${esc(String(t.name||'?')[0])}${t.verified?'<span style="color:var(--ok);font-size:11px;margin-left:3px">✓</span>':''}</div>
        <div class="candt"><div class="candn">${esc(t.name)} <span class="candkm">${t.km} km</span></div><div class="cands">${esc(why)}</div></div>
        <div class="candsc"><div class="candpct">${t.score}%</div></div>
        <button class="introbtn" data-act="buddy-intro" data-bi="${i}">Intro</button></div></div>`; }
    return row;
  }).join('');
  return `<div class="bchat fade">${hd}<div class="bthread" id="bthread">${thread}</div>
    <div class="bc2">
      <button class="bc2-plus" data-act="buddy-plus">+</button>
      <div class="bc2-field"><input id="bcin" placeholder="Message…" ${buddyBusy?'disabled':''}>
        <button class="bc2-mic" data-act="buddy-mic">${IC.mic}</button></div>
      <button class="bc2-send" data-act="buddy-send">${IC.send}</button>
    </div></div>`;
}

// ===== "Edit with Kleal": change the profile by talking to the editor agent (/api/buddy/profile-edit) =====
// The editor returns a semantic PATCH ([{op,field,value,label}]); we show a confirmation, and only on
// "Применить" apply it to DATA here (the frontend owns the profile). Fields map 1:1 to applyProfilePatch.
let editMsgs=[], editBusy=false;
// section -> a focused opening line, so the Edit buttons on the profile sections land the editor in context
const EDIT_GREET={
  'Interests':"Что поменять в интересах? Например: «добавь теннис» или «убери футбол».",
  'Your personality':"Расскажи, как ты общаешься с людьми — например «я больше интроверт» или «люблю глубокие разговоры».",
  'Goals':"Какая у тебя цель? Например «хочу найти напарника по бегу» или «убери нетворкинг».",
  'Safety & Privacy':"Что настроить в безопасности и приватности? Например «встречаться только в публичных местах» или «только проверенные».",
  'Location':"Куда переехал или где удобно встречаться? Например «город Мадрид».",
  'Languages':"Какие языки добавить или убрать? Например «добавь французский».",
};
function openProfileEdit(section){
  cur='profileedit';
  const greet = EDIT_GREET[section] || (section
    ? ("Что поменять в разделе «"+section+"»? Опиши своими словами.")
    : "Что поменять в профиле? Скажи, например: «добавь теннис», «город Мадрид» или «убери футбол».");
  if(!editMsgs.length || section) editMsgs=[{who:'them',hello:true,text:greet}];   // Edit button -> fresh, focused
  render();
}
function snapRow(title){ return (DATA.snapshot||[]).find(r=>String(r.title).toLowerCase()===String(title).toLowerCase()); }
function setSnap(title,icon,value){ const r=snapRow(title); if(r){ r.value=value; } else { (DATA.snapshot=DATA.snapshot||[]).push({icon,title,value}); } }
function editIcon(name){ const n=String(name).toLowerCase();
  if(/dota|valorant|\bcs\b|league|fifa|game/.test(n))return'gamepad';
  if(/football|soccer|basket|tennis|gym|run|box|climb|swim|cycl|sport/.test(n))return'football';
  if(/coffee|walk|dinner|tea|brunch|drinks/.test(n))return'coffee';
  if(/movie|cinema|film|series/.test(n))return'film';
  if(/\bai\b|startup|tech|business|network|career|founder/.test(n))return'rocket';
  if(/archit|design|\bart\b|photo|museum/.test(n))return'building';
  if(/language|spanish|english|french|german|italian|practice|music/.test(n))return'chat';
  if(/hik|nature|outdoor|travel|park/.test(n))return'pin';
  return'spark'; }
// current profile in the semantic shape the editor agent reasons over (mirror of applyProfilePatch fields)
function fullProfileForEdit(){ const g=t=>{const r=snapRow(t);return r?r.value:'';};
  return { name:DATA.name||'', location:g('Location'), languages:g('Languages'),
    formats:g('Social formats'), availability:g('Availability'), safety:g('Safety'),
    interests:(DATA.interests||[]).map(i=>i.name), goals:((DATA.goals||{}).active)||[],
    vibe:((DATA.social||{}).rows||[]).map(r=>r.title+': '+r.value).join(' · '), summary:DATA.summary||'' }; }
function applyProfilePatch(patch){ const lc=s=>String(s==null?'':s).toLowerCase();
  (patch||[]).forEach(p=>{ const f=p.field, v=p.value, op=p.op;
    if(f==='name') DATA.name=v;
    else if(f==='summary') DATA.summary=v;
    else if(f==='location'){ setSnap('Location','pin',v); const pc=(DATA.places||[]).find(r=>lc(r.title)==='city'); if(pc)pc.value=v; }
    else if(f==='languages') setSnap('Languages','globe',v);
    else if(f==='formats') setSnap('Social formats','users',v);
    else if(f==='availability') setSnap('Availability','clock',v);
    else if(f==='safety') setSnap('Safety','shield',v);
    else if(f==='vibe'){ DATA.social=DATA.social||{rows:[],vibe:[],depth:[]}; DATA.social.rows=DATA.social.rows||[];
      const row=DATA.social.rows.find(r=>lc(r.title)==='energy'); if(row) row.value=v;
      else DATA.social.rows.unshift({icon:'spark',title:'Energy',value:v}); }   // personality -> the personality section, never appended to the summary
    else if(f==='interests'){ DATA.interests=DATA.interests||[];
      if(op==='remove') DATA.interests=DATA.interests.filter(i=>lc(i.name)!==lc(v));
      else if(!DATA.interests.some(i=>lc(i.name)===lc(v))) DATA.interests.push({name:v,icon:editIcon(v),conf:'Medium',used:true});
      DATA.matchingPaths=DATA.interests.slice(0,3).map(i=>i.name);
      setSnap('Interests','spark',DATA.interests.map(i=>i.name).join(' · ')); }
    else if(f==='goals'){ DATA.goals=DATA.goals||{active:[],optional:[]}; DATA.goals.active=DATA.goals.active||[];
      if(op==='remove') DATA.goals.active=DATA.goals.active.filter(x=>lc(x)!==lc(v));
      else if(!DATA.goals.active.some(x=>lc(x)===lc(v))) DATA.goals.active.push(v); }
  }); }
async function editTurn(text){ text=(text||'').trim(); if(!text||editBusy) return;
  editBusy=true; editMsgs.push({who:'me',text,t:Date.now()}); editMsgs.push({who:'them',text:'…',loading:true}); render();
  let r; try{ r=await fetch('/api/buddy/profile-edit',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({message:text, profile:fullProfileForEdit()})}).then(x=>x.json()); }catch(e){ r=null; }
  editMsgs=editMsgs.filter(m=>!m.loading); editBusy=false;
  if(!r){ editMsgs.push({who:'them',text:'Связь пропала — повтори, пожалуйста.',t:Date.now()}); render(); return; }
  editMsgs.push({who:'them', text:r.reply||'…', t:Date.now(), patch:(r.patch&&r.patch.length)?r.patch:null});
  render(); saveState(); }
function confirmEdit(i){ const m=editMsgs[i]; if(!m||!m.patch) return;
  applyProfilePatch(m.patch); m.patch=null;
  editMsgs.push({who:'them',text:'✓ Готово — обновил профиль.',t:Date.now()});
  render(); saveState(); toast('Профиль обновлён');
  adaptSummary();   // rewrite Kleal's summary to fit the new profile (adapt, don't append)
}
// After any profile change, ask Kleal to rewrite the summary paragraph so it reflects the new data
// naturally — instead of a word being tacked onto the end.
let _resumBusy=false;
async function adaptSummary(){
  if(_resumBusy) return; _resumBusy=true;
  try{ const r=await fetch('/api/buddy/resummary',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({profile:fullProfileForEdit(), current:DATA.summary||''})}).then(x=>x.json());
    if(r&&r.summary){ DATA.summary=r.summary; DATA.summaryLabel="Kleal's summary"; render(); saveState(); }
  }catch(e){}
  _resumBusy=false;
}
function cancelEdit(i){ const m=editMsgs[i]; if(!m) return; m.patch=null;
  editMsgs.push({who:'them',text:'Ок, оставил как было.',t:Date.now()}); render(); }
function scr_profileedit(){
  const hd=`<div class="chd">
    <button class="chd-back" data-act="edit-back">${IC.back}<span>Back</span></button>
    <div class="chd-pills"><button class="chd-pill" data-act="edit-view">${IC.person}<span>Профиль</span></button></div></div>`;
  const thread=editMsgs.map((x,i)=>{
    if(x.who==='me') return `<div class="mrow"><div class="mbub">${esc(x.text)}</div><div class="btime r">${fmtTime(x.t)}</div></div>`;
    if(x.hello) return `<div class="khello"><div class="kav" style="width:44px;height:44px"></div><div class="khtxt">${esc(x.text)}</div></div>`;
    const first=(i===0)||editMsgs[i-1].who!=='them'||editMsgs[i-1].hello;
    const inner=x.loading?'<span class="typing3"><i></i><i></i><i></i></span>':esc(x.text).replace(/\n/g,'<br>');
    const time=x.loading?'':(x.t?`<div class="btime">${fmtTime(x.t)}</div>`:'');
    const row=`<div class="krow"><div class="kav${first?'':' sp'}"></div><div class="kcol"><div class="kbub">${inner}</div>${time}</div></div>`;
    if(x.patch){ const chips=x.patch.map(p=>`<div class="epatch">${IC.wand}<span>${esc(p.label||(p.op+' '+p.field+': '+p.value))}</span></div>`).join('');
      return row+`<div class="card ecard" style="margin:2px 0 2px 43px">${chips}
        <div class="eactions"><button class="ebtn ghost" data-act="edit-cancel" data-ei="${i}">Отмена</button>
        <button class="ebtn primary" data-act="edit-apply" data-ei="${i}">Применить</button></div></div>`; }
    return row;
  }).join('');
  return `<div class="bchat fade">${hd}<div class="bthread" id="bthread">${thread}</div>
    <div class="bc2"><button class="bc2-plus" data-act="buddy-plus">+</button>
      <div class="bc2-field"><input id="ecin" placeholder="Например: добавь теннис…" ${editBusy?'disabled':''}>
        <button class="bc2-mic" data-act="buddy-mic">${IC.mic}</button></div>
      <button class="bc2-send" data-act="edit-send">${IC.send}</button></div></div>`;
}

// ---------- Phase 3: public intents on the Explore map ----------
const ME_LATLON=[41.3874, 2.1686];   // Barcelona (demo user's coarse area)
// Explore plans are REAL — pulled from the matching pool (/api/agent/explore), not hard-coded here.
let PUBLIC_INTENTS=[], exploreLoaded=false, exploreLoading=false;
async function loadExplore(){
  if(exploreLoading) return; exploreLoading=true;
  let r; try{ r=await fetch('/api/agent/explore?self='+encodeURIComponent(DATA.name||'')).then(x=>x.json()); }catch(e){ r=null; }
  exploreLoading=false; exploreLoaded=true;
  PUBLIC_INTENTS=(r&&r.plans)||[];
  if(cur==='search') render();
}
let exploreMap=null;
function initExploreMap(){
  if(typeof L==='undefined') return;                 // Leaflet not loaded
  if(exploreMap){ try{ exploreMap.remove(); }catch(_e){} exploreMap=null; }
  const el=document.getElementById('lmap'); if(!el) return;
  const map=L.map('lmap',{zoomControl:false,scrollWheelZoom:false,attributionControl:false});
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{maxZoom:19}).addTo(map);
  const pin='<svg viewBox="0 0 24 24" width="30" height="30" style="filter:drop-shadow(0 3px 3px rgba(20,20,40,.28))"><path d="M12 22s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" fill="#F5455C"/><circle cx="12" cy="10.5" r="2.6" fill="#fff"/></svg>';
  const cIcon=L.divIcon({html:pin,className:'',iconSize:[30,30],iconAnchor:[15,30],popupAnchor:[0,-28]});
  const meIcon=L.divIcon({html:'<div class="meDot"></div>',className:'',iconSize:[16,16],iconAnchor:[8,8]});
  const pts=[];
  PUBLIC_INTENTS.forEach((p,i)=>{ const m=L.marker([p.lat,p.lon],{icon:cIcon}).addTo(map);
    m.bindPopup('<div class="mapop"><div class="mopt">'+esc(p.title)+'</div><div class="mopm">'+esc(p.who)+' · '+esc(p.when)+' · '+esc(p.dist)+' km</div><button class="mopj" onclick="joinPublic('+i+')">Join</button></div>');
    pts.push([p.lat,p.lon]); });
  L.marker(ME_LATLON,{icon:meIcon}).addTo(map); pts.push(ME_LATLON);
  try{ map.fitBounds(pts,{padding:[36,36]}); }catch(_e){ map.setView(ME_LATLON,13); }
  setTimeout(()=>{ try{ map.invalidateSize(); map.fitBounds(pts,{padding:[36,36]}); }catch(_e){} }, 90);
  exploreMap=map;
}
function joinPublic(i){ const p=PUBLIC_INTENTS[i]; if(!p)return; addNotif('intent','Asked to join “'+p.title+'”','Waiting for '+p.who+'’s agent to confirm', null); saveState(); toast('Requested to join — '+p.who+'’s agent will confirm'); }

function scr_intents(){
  const list=DATA.intents||[];
  const head=`<div class="seccap" style="margin:2px 2px 12px">Intents are the plans you ask Kleal to arrange. It searches, matches schedules and lines up intros — you approve every one.</div>`;
  if(!list.length) return `<div class="fade">${head}${emptyState("No intents yet","Tap Create intent and tell Kleal what you'd like to do.")}
    <button class="bigbtn primary" style="margin-top:8px" data-act="createintent">Create intent</button></div>`;
  const cards=list.map((it)=>{ const cs=it.candidates||[]; const ag=cs.filter(c=>c.agree).length;
    return `<div class="card pad intentrow" ${it.id?`data-savedintent="${it.id}"`:''}>
    <div class="sumhead"><div class="sumlbl">${esc(it.title)}</div><span class="pill searching dot">${esc(capw(it.status||'searching'))}</span></div>
    <div style="margin:10px 0 6px">${(it.tags||[]).map(t=>`<span class="itag">${esc(t)}</span>`).join('')}</div>
    <div class="confrow2"><span class="l">${cs.length} ${cs.length===1?'match':'matches'}${ag?' · '+ag+' agreed':''}</span><span class="confpct">${it.confidence||0}%</span></div>
    <div class="track"><i style="width:${it.confidence||0}%"></i></div></div>`; }).join('');
  return `<div class="stack fade">${head}${cards}
    <button class="bigbtn primary" style="margin-top:4px" data-act="createintent">Create intent</button></div>`;
}

function scr_intentchat(){
  const it=curIntent;
  const composer=`<div class="composer"><input id="acin" class="cin cinput" placeholder="Опиши, что хочешь сделать…" ${intentBusy?'disabled':''}>
    <button class="csend" data-act="intent-send">${IC.send||IC.nMsg}</button></div>`;
  if(!it){
    // conversational collection: Kleal asks for the missing essentials and validates before building a card
    const thread=(intentMsgs||[]).map(x=>{
      if(x.who==='me') return `<div class="mbub">${esc(x.text)}</div>`;
      const inner=x.loading?'<span class="typing3"><i></i><i></i><i></i></span>':esc(x.text).replace(/\n/g,'<br>');
      return `<div class="kbub">${inner}</div>`;
    }).join('');
    return `<div class="fade"><div class="thread">${thread}</div>${composer}</div>`;
  }
  if(it.pending){
    return `<div class="fade"><div class="thread">
      <div class="mbub">${esc(it.query)}</div>
      <div class="kbub"><span class="typing3"><i></i><i></i><i></i></span> structuring your intent…</div>
    </div>${composer}</div>`;
  }
  const cands=it.candidates||[]; const negotiating=!!it.negotiating;
  const agreed=cands.filter(c=>c.agree).length;
  const candCard=`<div class="card"><div class="sumhead" style="padding:14px 16px 6px"><div class="sumlbl">Kleal ищет</div>
      <span class="confpct">${negotiating?'договариваюсь…':'согласны: '+agreed}</span></div>
    ${cands.length ? cands.map((c,i)=>{
      const negot=negotiating && !c.decided;
      const sub=(c.decided&&c.reason)?c.reason:(c.reasons||[]).slice(0,2).join(' · ');
      const status=negot?'<div class="candbusy"><span class="typing3"><i></i><i></i><i></i></span></div>'
        :(c.passed?'<div class="candno">пропущен</div>':(c.agree?'<div class="candok">✓ согласен</div>':'<div class="candno">отказ</div>'));
      const tier=c.kind==='reciprocal'?'<span style="font-size:10px;font-weight:700;color:var(--accent);background:var(--accent-soft);border-radius:6px;padding:1px 5px;margin-left:5px">↔ mutual</span>'
        :(c.tier?`<span style="font-size:10px;font-weight:700;color:var(--muted);background:var(--field);border-radius:6px;padding:1px 5px;margin-left:5px">${esc(c.tier)}</span>`:'');
      const vtick=c.verified?'<span style="color:var(--ok);font-size:11px;margin-left:3px">✓</span>':'';
      return `<div class="candrow" style="${c.passed?'opacity:.5':''}"><div class="candav">${esc(String(c.name||'?')[0])}</div>
      <div class="candt"><div class="candn">${esc(c.name)}${vtick}${tier} <span class="candkm">${c.km} km</span></div>
        <div class="cands">${esc(sub)}</div></div>
      <div class="candsc"><div class="candpct">${c.score}%</div>${status}</div>
      ${(!negot&&c.agree&&!c.passed)?`<button class="introbtn" data-act="intro" data-ci="${i}">Intro</button>
        <button data-act="pass" data-ci="${i}" title="Not interested" style="border:none;background:var(--field);color:var(--muted);width:26px;height:26px;border-radius:50%;font-size:13px;margin-left:6px;cursor:pointer">✕</button>`:''}
      </div>${i<cands.length-1?'<div class="divider"></div>':''}`; }).join('')
      : (it.fallback ? fallbackCard(it.fallback)
        : '<div class="chkrow"><div class="chklb wait">Пока никто не подошёл — продолжаю искать в фоне.</div></div>')}
    </div>`;
  return `<div class="fade"><div class="thread">
    ${it.query?`<div class="mbub">${esc(it.query)}</div>`:''}
    <div class="kbub">Вот интент, который я собрал${it.error?' (офлайн — грубый разбор)':''}. Запусти поиск, когда всё верно.</div>
    <div class="card pad"><div class="sumhead"><div class="sumlbl">${esc(it.title)}</div><span class="confpct">${it.confidence||0}%</span></div>
      <div style="margin:10px 0 2px">${(it.tags||[]).map(t=>`<span class="itag">${esc(t)}</span>`).join('')}</div></div>
    <div class="card">${intentSpec(it)}</div>
    ${intentLaunched ? '' : `<button class="bigbtn primary" data-act="launch-intent">Запустить поиск</button>`}
    ${intentLaunched ? `<div class="mbub">Запускаю</div>
      <div class="kbub">${negotiating?'Связываюсь с агентами кандидатов — договариваюсь за тебя…':('Их агенты ответили — согласны: '+agreed)}</div>
      ${candCard}
      ${negotiating?'':'<div class="kbub">Сделать интро? Я пишу только после твоего одобрения.</div>'}` : ''}
  </div>${composer}</div>`;
}

function scr_search(){
  const P=PUBLIC_INTENTS;
  const list=P.map((p,i)=>`<div class="card evrow" data-public="${i}"><div class="evic">${IC.pin}</div>
    <div class="evt"><div class="evtt">${esc(p.title)}</div><div class="evts">${esc(p.who)} · ${esc(p.when)} · ${esc(p.dist)} km</div></div>
    <button class="introbtn" data-act="join" data-pi="${i}">Join</button></div>`).join('');
  const below = P.length ? `<div class="stack">${list}</div>`
    : (exploreLoaded
        ? emptyState('Пока рядом нет открытых планов','Создай интент — и Kleal предложит его людям вокруг.')
        : `<div class="stack"><div class="card evrow"><div class="evt"><div class="evts"><span class="typing3"><i></i><i></i><i></i></span> ищу планы рядом…</div></div></div></div>`);
  return `<div class="fade">
    <div class="sbar"><div class="box">${IC.nSearch}<span>Search this area…</span></div>
      <div class="filt" data-act="filter">${IC.compass}</div></div>
    <div id="lmap" class="lmap"></div>
    <div class="seccap" style="margin:12px 2px 8px">Open plans people posted near you — tap a pin to see it, Join and Kleal handles the intro. Only your area is shown, never your exact spot.</div>
    ${below}
  </div>`;
}

function scr_messages(){
  const list=DATA.messages||[];
  if(!list.length) return emptyState("No messages yet","When Kleal lines up an intro, your chats show up here.");
  return `<div class="stack fade" style="padding-top:4px">${list.map((m,i)=>`<div class="card" style="padding:0">
    <div class="msgrow" data-msg="${i}"><div class="msgav ${m.kleal?'k':''}">${m.kleal?'K':esc(String(m.who||'?')[0])}</div>
    <div class="msgt"><div class="mn">${esc(m.who)}${m.kleal?'<span class="reddot"></span>':''}</div><div class="ml">${esc(m.last)}</div></div>
    <div class="msgtime">${esc(m.time)}</div></div></div>`).join('')}</div>`;
}

// ================= Agent Home — the main landing after onboarding (Figma Flow 4) =================
function scr_agenthome(){
  const nm=DATA.name||'there';
  const plan=(DATA.plans||[])[0];
  const qa=[['peoplePin','People nearby','q-people'],['calen','Events nearby','q-events'],
            ['heart','Interests & groups','q-interests'],['bookmark','Saved','q-saved']];
  const planCard = plan ? `<div class="tcard" data-plan="0">
      <div class="timg"></div>
      <div class="tbody"><div class="tt">${esc(plan.title)}</div>
        <div class="tm">${esc(plan.when)} · ${esc(plan.dist)}</div>
        <div class="tpart"><div class="stack5"><span class="av"></span><span class="av"></span><span class="av"></span><span class="av"></span><span class="more">+5</span></div><span class="pn">8 going</span></div></div>
      <div class="tbm">${IC.bookmark}</div></div>` : '';
  return `<div class="ahome fade">
    <div class="ahead"><div class="agreet">Hi, ${esc(nm)}! 👋</div>
      <div class="abell" data-act="notif">${IC.bell}${unreadNotifs()?`<span class="abadge">${unreadNotifs()}</span>`:''}</div></div>
    <div class="aintro" data-act="talk-buddy" style="cursor:pointer"><div class="amascot">${MASCOT}</div>
      <div class="abub">I'm Kleal, your buddy. Just chat with me — tell me what you're into and who you'd like to meet, and I'll find them for you. Tap to talk →</div></div>
    <div class="asearch"><input id="ainput" placeholder="Say hi to Kleal…" autocomplete="off">
      <button class="asend" data-act="agent-go">${IC.send}</button></div>
    <div class="qhead">Quick actions</div>
    <div class="quick">${qa.map(q=>`<div class="qcard" data-act="${q[2]}"><div class="qic">${IC[q[0]]}</div><div class="qt">${q[1]}</div></div>`).join('')}</div>
    <div class="thead"><span class="th">For you today</span><span class="tall" data-act="see-all">See all</span></div>
    ${planCard}
  </div>`;
}

const SCREENS={agenthome:scr_agenthome,profileedit:scr_profileedit,overview:scr_overview,snapshot:scr_snapshot,interests:scr_interests,social:scr_social,
  places:scr_places,goals:scr_goals,safety:scr_safety,memory:scr_memory,knows:scr_knows,
  intents:scr_intents,intentchat:scr_intentchat,search:scr_search,messages:scr_messages,
  notifs:scr_notifications,matchchat:scr_matchchat,buddychat:scr_buddychat};

// ---------- Edit Signal screen (Figma "Edit Signal") ----------
function intKind(name){ const n=(name||'').toLowerCase();
  if(/dota|valorant|league|\bcs\b|apex|fortnite|fifa|game|gaming/.test(n))return'game';
  if(/football|soccer|basket|tennis|\bgym\b|\brun|\bbox|climb|swim|cycl|\bhik|sport/.test(n))return'sport';
  if(/movie|cinema|film|series|\bshow|anime/.test(n))return'watch';
  if(/language|spanish|english|french|german|italian|practice/.test(n))return'language';
  if(/\bai\b|startup|\btech|business|career|network|\bdesign|architect|coding/.test(n))return'topic';
  return'social'; }
const KNOW_OPTS={
  game:[['I play it',['play']],['I watch it / streams',['watch']],['I discuss it',['discuss']],['I play ranked',[]],['I play casually',['play']],['Voice chat is fine',[]]],
  sport:[['I watch matches',['watch']],['I play casually',['play']],['I discuss it',['discuss']],['I support a team',[]],['Sports bar sometimes',[]],['Only online plans',[]]],
  watch:[['I watch on my own',['watch']],["I'm open to watch parties",['watch']],['I discuss it',['discuss']],['I want recommendations',[]]],
  language:[['I want speaking practice',['practice']],['I want a language partner',['practice']],["I'm open to corrections",['practice']],['Casual conversation only',[]]],
  topic:[['I build / practice it',['practice','play']],['I discuss it',['discuss','practice']],['I learn about it',['practice']],['I attend events',[]],['I follow the news',[]],['I want collaborators',[]]],
  social:[['Casual chats',['discuss']],['Deeper conversations',[]],['1:1 or small group',[]],['Public places',[]]],
};
function openEditInterest(name){
  const it=(DATA.interests||[]).find(i=>i.name===name)||{name:name,kv:[]};
  const role=((it.kv||[]).find(k=>k[0]==='Role')||[])[1]||''; const rl=role.toLowerCase();
  const know=(KNOW_OPTS[intKind(name)]||KNOW_OPTS.social).map(o=>({label:o[0], on:o[1].some(r=>rl.includes(r))}));
  editSig={ kind:'interest', name:name, used:it.used!==false, know, expansion:'Related' };
  detail=null; render();
}
function openEditSignal(i){
  const m=DATA.memory[i]||{}; editSig={ kind:'signal', sig:i, name:m.signal||'Signal', used:m.used!==false, status:m.status, source:m.source };
  render();
}
function scr_editSignal(){
  const e=editSig;
  const toggle=`<div class="card trow"><div class="tt"><div class="ttl">Used for matching</div>
    <div class="tts">Turn off to keep it but stop matching on this</div></div>
    <div class="sw ${e.used?'on':''}" data-esw><i></i></div></div>`;
  if(e.kind==='signal'){
    return `<div class="fade">${toggle}
      <div class="rowhead"><div class="h2">About this signal</div></div>
      <div class="card pad"><div class="sumtxt" style="font-size:14px">${esc(e.name)}</div>
        <div class="smeta" style="margin-top:8px;color:var(--muted);font-size:13px">Status: ${esc(e.status||'Confirmed')} &middot; Source: ${esc(e.source||'Onboarding')}</div></div>
      <div style="height:16px"></div>
      <button class="bigbtn primary" data-act="savesig">Save</button>
      <button class="bigbtn ghost" data-act="removesig">${IC.boxx} Remove signal</button></div>`;
  }
  return `<div class="fade">${toggle}
    <div class="rowhead"><div class="h2">What should Kleal know?</div></div>
    <div class="card">${e.know.map((k,i)=>`<div class="crow"><div class="cbx ${k.on?'on':''}" data-ecbx="${i}">${k.on?IC.check:''}</div><div class="cl">${esc(k.label)}</div></div>${i<e.know.length-1?'<div class="divider"></div>':''}`).join('')}</div>
    <div class="rowhead"><div class="h2">Matching expansion</div></div>
    <div class="chips">${['Exact only','Related','Broad'].map(x=>`<div class="chip ${e.expansion===x?'gsel':'unsel'}" data-eexp="${x}">${esc(x)}</div>`).join('')}</div>
    <div style="height:18px"></div>
    <button class="bigbtn primary" data-act="savesig">Save</button>
    <button class="bigbtn ghost" data-act="removesig">${IC.boxx} Remove interest</button></div>`;
}

let editSig=null;  // {kind:'interest'|'signal', ...}
let detail=null;  // {interest}
function render(){
  const meta=TABS.find(t=>t[0]===cur)||TABS[0];
  const isHome = !editSig && !detail && cur==='overview';
  const isRoot = !editSig && !detail && ROOTS.includes(cur);
  const titleFor = cur==='intentchat' ? (curIntent&&curIntent.title?curIntent.title:'Create intent')
    : cur==='matchchat' ? (matchWith?matchWith.cand.name:'Chat')
    : cur==='buddychat' ? 'Kleal'
    : (cur==='overview'?'My Kleal Profile':(TITLES[cur]||meta[2]));
  document.getElementById('title').textContent= editSig? editSig.name : (detail? detail.name : titleFor);
  document.getElementById('back').style.visibility= (editSig||detail||!ROOTS.includes(cur))? 'visible' : 'hidden';
  // app-bar right icon: gear on Overview, refresh on drill-ins, nothing on the other root tabs
  const rgt=document.getElementById('bookmark');
  rgt.innerHTML = isHome ? IC.gear : IC.refresh;
  rgt.style.visibility = (isRoot && !isHome) ? 'hidden' : 'visible';   // no right icon on Intents/Search/Messages
  rgt.onclick = ()=> toast(isHome?'Settings are coming soon':'Kleal is refreshing this');
  // bottom nav: rebuilt for the active tab; hidden on the intent chat (which has its own composer)
  const bn=document.getElementById('bnav'); if(bn){ bn.style.display=(cur==='intentchat'||cur==='matchchat'||cur==='buddychat'||cur==='profileedit')?'none':'flex'; bn.innerHTML=bnavHTML(); }
  // Home + Buddy chat carry their own headers, so hide the shared app bar there
  const ab=document.querySelector('.appbar'); if(ab) ab.style.display=(cur==='agenthome'||cur==='buddychat'||cur==='profileedit')?'none':'flex';
  if(editSig){ A.innerHTML=scr_editSignal(); }
  else if(detail){ A.innerHTML=scr_domain(detail); }
  else { A.innerHTML=(SCREENS[cur]||scr_overview)(); }
  // Buddy chat owns the full height: app area becomes a flex column so the thread scrolls internally
  // and the composer stays pinned. Other screens keep the normal scrolling body.
  const chat=(cur==='buddychat'||cur==='profileedit');
  A.style.display=chat?'flex':''; A.style.flexDirection=chat?'column':'';
  A.style.overflowY=chat?'hidden':''; A.style.paddingBottom=chat?'0':'';
  A.scrollTop=0;
  if(chat){ const bt=document.getElementById('bthread'); if(bt) bt.scrollTop=bt.scrollHeight; }
  // real Leaflet map on Explore; tear it down when leaving
  if(cur==='search'){ if(!exploreLoaded) loadExplore(); setTimeout(initExploreMap, 0); }
  else if(exploreMap){ try{ exploreMap.remove(); }catch(_e){} exploreMap=null; }
  // wire (drill-in nav: Overview hub -> section -> back)
  document.querySelectorAll('[data-nav]').forEach(el=>el.onclick=()=>setTab(el.dataset.nav));
  document.querySelectorAll('[data-go]').forEach(el=>el.onclick=()=>setTab(el.dataset.go));
  document.querySelectorAll('[data-open]').forEach(el=>el.onclick=()=>{ expInt=(expInt===el.dataset.open?'':el.dataset.open); render(); });
  document.querySelectorAll('[data-imatch]').forEach(el=>el.onclick=(ev)=>{ ev.stopPropagation(); const it=DATA.interests.find(i=>i.name===el.dataset.imatch); if(it){ it.used=(it.used===false); el.classList.toggle('on', it.used!==false); } });
  document.querySelectorAll('[data-tog]').forEach(el=>el.onclick=()=>{ const on=!el.classList.contains('on'); el.classList.toggle('on'); if(el.dataset.uk)UI[el.dataset.uk]=on; });
  // Safety & Privacy: flags are the single source of truth on DATA.safety
  document.querySelectorAll('[data-sflag]').forEach(el=>el.onclick=()=>{ const k=el.dataset.sflag; const on=!el.classList.contains('on'); el.classList.toggle('on'); if(DATA.safety)DATA.safety[k]=on; });
  document.querySelectorAll('[data-schoice]').forEach(el=>el.onclick=()=>{ if(el.dataset.schoice==='autonomy'&&DATA.safety){ DATA.safety.autonomy=(+el.dataset.i===1?'auto':'ask'); render(); } });
  document.querySelectorAll('[data-cbx]').forEach(el=>el.onclick=()=>{ const on=!el.classList.contains('on'); el.classList.toggle('on'); el.innerHTML=on?IC.check:''; if(el.dataset.uk)UI[el.dataset.uk]=on; });
  // Social Style chips (Vibe / Conversation depth) — toggle selection, persist to DATA
  document.querySelectorAll('[data-vibe]').forEach(el=>el.onclick=()=>{ const i=+el.dataset.vibe; DATA.social.vibe[i][1]=!DATA.social.vibe[i][1]; el.classList.toggle('sel'); el.classList.toggle('unsel'); });
  document.querySelectorAll('[data-depth]').forEach(el=>el.onclick=()=>{ const i=+el.dataset.depth; DATA.social.depth[i][1]=!DATA.social.depth[i][1]; el.classList.toggle('sel'); el.classList.toggle('unsel'); });
  // Edit Signal controls
  const esw=document.querySelector('[data-esw]'); if(esw)esw.onclick=()=>{ editSig.used=!editSig.used; esw.classList.toggle('on'); };
  document.querySelectorAll('[data-ecbx]').forEach(el=>el.onclick=()=>{ const i=+el.dataset.ecbx; editSig.know[i].on=!editSig.know[i].on; el.classList.toggle('on'); el.innerHTML=editSig.know[i].on?IC.check:''; });
  document.querySelectorAll('[data-eexp]').forEach(el=>el.onclick=()=>{ editSig.expansion=el.dataset.eexp; render(); });
  // V4: intents list, discovery pins/cards, message rows
  document.querySelectorAll('[data-intent]').forEach(el=>el.onclick=()=>{ const it=(DATA.intents||[])[+el.dataset.intent]; openIntent(it, !!(it&&it.status==='searching')); });
  document.querySelectorAll('[data-plan]').forEach(el=>el.onclick=()=>toast('Plan details are coming soon'));
  document.querySelectorAll('[data-msg]').forEach(el=>el.onclick=()=>openMsgThread(+el.dataset.msg));
  document.querySelectorAll('[data-savedintent]').forEach(el=>el.onclick=()=>openSavedIntent(el.dataset.savedintent));
  document.querySelectorAll('[data-notif]').forEach(el=>el.onclick=()=>openNotif(el.dataset.notif));
  document.querySelectorAll('[data-public]').forEach(el=>el.onclick=()=>{ const p=PUBLIC_INTENTS[+el.dataset.public]; if(p)toast(p.title+' — '+p.who+' · '+p.when); });
  document.querySelectorAll('[data-act]').forEach(el=>el.onclick=(ev)=>{ ev.stopPropagation(); doAct(el.dataset.act, el.dataset); });
  const acin=document.getElementById('acin'); if(acin){ acin.onkeydown=(e)=>{ if(e.key==='Enter')intentTurn(acin.value); }; setTimeout(()=>{try{acin.focus();}catch(_e){}},40); }
  const ainput=document.getElementById('ainput'); if(ainput){ ainput.onkeydown=(e)=>{ if(e.key==='Enter'){ openBuddy(ainput.value); } }; }
  const bcin=document.getElementById('bcin'); if(bcin){ bcin.onkeydown=(e)=>{ if(e.key==='Enter')buddyTurn(bcin.value); }; setTimeout(()=>{try{bcin.focus();}catch(_e){}},40); }
  const ecin=document.getElementById('ecin'); if(ecin){ ecin.onkeydown=(e)=>{ if(e.key==='Enter')editTurn(ecin.value); }; setTimeout(()=>{try{ecin.focus();}catch(_e){}},40); }
  const mcin=document.getElementById('mcin'); if(mcin){ mcin.onkeydown=(e)=>{ if(e.key==='Enter')doAct('match-send',{}); }; setTimeout(()=>{try{mcin.focus();}catch(_e){}},40); }
  saveState();   // persist after every re-render (covers all doAct-driven edits)
}
// also persist after direct toggle/chip clicks that mutate state without a re-render, and on unload
A.addEventListener('click', ()=>setTimeout(saveState, 0));
window.addEventListener('beforeunload', saveState);
document.getElementById('back').onclick=()=>{ if(editSig){ editSig=null; render(); } else if(detail){ detail=null; render(); }
  else if(cur==='matchchat'){ cur=(matchWith&&matchWith.fromMessages)?'messages':(matchWith&&matchWith.fromBuddy)?'buddychat':'intentchat'; render(); }
  else if(cur==='buddychat'){ cur='agenthome'; render(); }
  else if(cur==='profileedit'){ cur='buddychat'; render(); }
  else if(cur==='intentchat'){ cur='intents'; render(); }
  else if(cur==='notifs'){ cur='agenthome'; render(); }
  else if(!ROOTS.includes(cur)){ cur='overview'; render(); } };
// ---- toast + every button does something ----
function toast(msg){ let t=document.getElementById('toast');
  if(!t){ t=document.createElement('div'); t.id='toast'; t.className='toast'; document.querySelector('.phone').appendChild(t); }
  t.textContent=msg; t.classList.add('show'); clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('show'),1900); }
function doAct(act, ds){
  switch(act){
    case 'editsum': editingSummary=true; render(); break;
    case 'cancelsum': editingSummary=false; render(); break;
    case 'savesum': { const el=document.getElementById('sumta'); DATA.summary=(el?el.value:'').trim(); editingSummary=false; render(); toast('Summary saved'); break; }
    case 'askwhy': toast('Kleal built this from what you shared during onboarding. Every detail is editable.'); break;
    case 'editbasics': openProfileEdit(''); break;   // name / city / languages — all editable by talking
    case 'editrow': openProfileEdit(ds.row||''); break;   // section Edit -> talk to Kleal, in context
    case 'edit-int': openEditInterest(ds.int); break;
    case 'dontuse-int': toast('"'+(ds.int||'')+'" will not be used for matching'); break;
    case 'remove-int': { DATA.interests=DATA.interests.filter(i=>i.name!==ds.int);
      DATA.matchingPaths=(DATA.matchingPaths||[]).filter(p=>p!==ds.int);
      if(detail&&detail.name===ds.int)detail=null; render(); toast('Removed '+(ds.int||'')); break; }
    case 'edit-sig': openEditSignal(+ds.sig); break;
    case 'dontuse-sig': { const m=DATA.memory[+ds.sig]; if(m)m.used=(m.used===false); render(); break; }
    case 'remove-sig': { DATA.memory.splice(+ds.sig,1); render(); toast('Signal removed'); break; }
    case 'savesig': { const e=editSig; editSig=null;
      if(e&&e.kind==='interest'){ const it=(DATA.interests||[]).find(i=>i.name===e.name); if(it)it.used=e.used; cur='interests'; detail=null; }
      else { const m=DATA.memory[e&&e.sig]; if(m)m.used=e.used; cur='memory'; }
      render(); toast('Saved'); break; }
    case 'removesig': { const e=editSig; editSig=null;
      if(e&&e.kind==='interest'){ DATA.interests=DATA.interests.filter(i=>i.name!==e.name);
        DATA.matchingPaths=(DATA.matchingPaths||[]).filter(p=>p!==e.name); detail=null; cur='interests'; render(); toast('Removed '+e.name); }
      else { if(e)DATA.memory.splice(e.sig,1); cur='memory'; render(); toast('Signal removed'); }
      break; }
    // Safety & Privacy actions
    case 'autonomy': break;   // handled by data-schoice
    case 'trusted-contact': toast('Add a trusted contact — coming soon'); break;
    case 'review-memory': setTab('memory'); break;   // opens the agent-memory screen
    case 'verify-me': toast('Photo & ID verification — coming soon'); break;
    case 'blocked': toast('Your blocked list is empty'); break;
    case 'report': toast('Safety centre & reporting — coming soon'); break;
    case 'export-data': toast('Preparing your data export — we’ll email you a copy'); break;
    case 'delete-account': toast('Delete account would ask you to confirm, then erase everything'); break;
    case 'nav': setTab(ds.tab||'overview'); break;
    case 'fab': case 'createintent': openCreateIntent(); break;
    case 'intent-send': { const el=document.getElementById('acin'); intentTurn(el&&el.value||''); break; }
    case 'agent-send': { const el=document.getElementById('acin'); intentTurn(el&&el.value||''); break; }
    case 'launch-intent': intentLaunched=true; render(); negotiateIntent(); break;
    case 'intro': { const i=+ds.ci; approveIntro((curIntent&&curIntent.candidates||[])[i], curIntent); break; }
    case 'pass': { const i=+ds.ci; const c=(curIntent&&curIntent.candidates||[])[i]; if(!c)break;
      postFeedback(c.name,'rejected'); c.passed=true; c.agree=false; render(); saveState();
      toast('Kleal will remember you passed on '+c.name); break; }
    case 'live': { const k=ds.kind||'voice'; addNotif('match',(k==='watch'?'Watch-together room opened':'Live voice room opened'),
      'Kleal is inviting nearby people to “'+((curIntent&&curIntent.title)||'your plan')+'”',null); saveState();
      toast((k==='watch'?'Watch room':'Voice room')+' created — inviting people'); break; }
    case 'broaden': broadenIntent(ds.kind); break;
    case 'match-send': { const el=document.getElementById('mcin'); const t=(el&&el.value||'').trim(); if(!t||!matchWith)break;
      matchWith.msgs.push({who:'me',text:t}); matchWith.last=t; matchWith.time='now'; render(); saveState();
      const R=['Sounds great!','Perfect, that works for me.','Yeah, let’s do it 🙌','Nice — where works for you?','See you there!'];
      setTimeout(()=>{ if(matchWith){ const rep=R[matchWith.msgs.length%R.length]; matchWith.msgs.push({who:'them',text:rep}); matchWith.last=rep; matchWith.time='now'; render(); saveState(); } }, 750); break; }
    case 'edit-intent': toast('Editing the intent is coming soon'); break;
    case 'search-area': toast('Searching this area…'); break;
    case 'filter': toast('Filters are coming soon'); break;
    case 'join': joinPublic(+ds.pi); break;
    // Agent Home
    case 'notif': setTab('notifs'); break;
    case 'agent-go': { const el=document.getElementById('ainput'); openBuddy(el&&el.value||''); break; }
    case 'buddy-send': { const el=document.getElementById('bcin'); buddyTurn(el&&el.value||''); break; }
    case 'buddy-intro': { const i=+ds.bi; const m=buddyMsgs[i]; if(m&&m.match&&m.match.top){ approveIntro(m.match.top, m.match.intent); if(matchWith)matchWith.fromBuddy=true; } break; }
    case 'buddy-back': cur='agenthome'; render(); break;
    case 'buddy-profile': openProfileEdit(); break;   // "Edit with Kleal" — change the profile by talking
    case 'edit-send': { const el=document.getElementById('ecin'); editTurn(el&&el.value||''); break; }
    case 'edit-apply': confirmEdit(+ds.ei); break;
    case 'edit-cancel': cancelEdit(+ds.ei); break;
    case 'edit-back': cur='buddychat'; render(); break;
    case 'edit-view': cur='overview'; render(); break;
    case 'buddy-create': openCreateIntent(); break;
    case 'buddy-plus': toast('Attachments are coming soon'); break;
    case 'buddy-mic': buddyMic(); break;
    case 'go-home': editSig=null; detail=null; cur='agenthome'; render(); break;   // center FAB -> agent home
    case 'talk-buddy': openBuddy(''); break;
    case 'q-people': setTab('search'); break;
    case 'q-events': setTab('search'); break;
    case 'q-interests': setTab('interests'); break;
    case 'q-saved': toast('Saved items are coming soon'); break;
    case 'see-all': setTab('search'); break;
    case 'add-interests': openProfileEdit('Interests'); break;
    case 'personality-test': toast('The personality test is coming soon'); break;
    case 'edit-personality': openProfileEdit('Your personality'); break;
    case 'add-goal': openProfileEdit('Goals'); break;
    case 'edit-goal': openProfileEdit('Goals'); break;
    default: toast('Coming soon');
  }
}
render();
</script></body></html>'''

# escape "</" so a stray "</script>" inside data can never terminate the inline <script> early
HTML = HTML_HEAD.replace("__DATA__", json.dumps(DATA, ensure_ascii=False).replace("</", "<\\/"))

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] == "/":   # ignore ?p=<onboarding profile> query
            b = HTML.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print("Kleal Profile demo on http://127.0.0.1:%d" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
