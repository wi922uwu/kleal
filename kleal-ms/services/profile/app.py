# -*- coding: utf-8 -*-
# Kleal Profile demo — the "agent memory" profile screens, rebuilt from the Figma board
# "Section 1" (node 244-7677) of Kleal — Progress. ALL data comes from the UX spec
# "dating/UX задание на карточку профиля.docx" (Dmitry / Barcelona / football / Dota 2 / ...).
# Static demo (no LLM): stdlib http.server on :7073. Design tokens from Figma (Geist, coral #f5455c).
# Run: python kleal_profile.py    Preview config: .claude/launch.json -> "kleal-profile".
import os, json, base64
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
  # No seeded intents: an intent is created by the user and filled by the matching service.
  "intents": [],
  # Plans come from /api/agent/explore (real users posting real intents), never from a seed.
  "plans": [],
  "messages": [],

  # Memory is written from onboarding and profile edits, not seeded.
  "memory": [],

  "knows": {
    # No stored counters: scr_knows derives them from the lists below, so the headline
    # number can never drift away from what is actually rendered.
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
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{
  --bg:#F7F8FA; --surface:#F7F8FA; --card:#FFFFFF; --fg:#181B22; --muted:#5A616E; --border:#E2E5EC;
  --line:#ECEEF2; --neutral100:#EEF0F4; --neutral300:#CDD2DC; --primary:#F5455C; --primary-fg:#FFFFFF;
  --coral50:#FFF1F3; --coral200:#FECDD4; --coral700:#BC1F38;
  --success-text:#0F7340; --success-bg:#E8F7EE; --info-text:#1F58BE; --info-bg:#E8F1FD;
  --warn-text:#9A5400; --warn-bg:#FFF4E5; --danger:#E5484D;

  /* Referenced 6x but never declared, so .candbadge/.passbtn rendered with no background and
     the verified tick came out black instead of green. Aliases of existing tokens — no new colours. */
  --field:var(--neutral100); --accent:var(--coral700); --accent-soft:var(--coral50); --ok:var(--success-text);
  --neutral400:#A9B0BE;   /* placeholder-avatar glyph on a --neutral100 circle; sits between 300 and --muted */
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
.langtoggle{display:flex;gap:4px;background:var(--neutral100);border-radius:999px;padding:3px;flex:none}
.langbtn{border:0;background:transparent;color:var(--muted);font:inherit;font-size:13px;font-weight:700;padding:5px 12px;border-radius:999px;cursor:pointer}
.langbtn.on{background:#fff;color:var(--fg);box-shadow:0 1px 3px rgba(20,20,40,.12)}
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
.persimg.hasphoto{background:var(--neutral100);background-size:cover;background-position:center}
.bigbtn.dark{background:var(--fg);color:#fff}
/* «Личность» is a plain .body scroller, not a flex column, so the mock's pinned CTA pins with sticky
   (the .composer trick) instead of .kfoot. The negative margins full-bleed it over .body's own
   2px 16px 20px padding, so the story scrolls UNDER a solid bar rather than past a floating one. */
.stickycta{position:sticky;bottom:-20px;z-index:5;margin:20px -16px -20px;padding:12px 16px 20px;
  background:var(--bg);box-shadow:0 -8px 16px -8px rgba(0,0,0,.10)}
.stickycta .bigbtn{margin-top:0}
.sumtxt.clamp3{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.penbtn{width:44px;height:44px;border-radius:50%;background:var(--neutral100);color:var(--muted);flex:none;
  display:flex;align-items:center;justify-content:center;border:0;cursor:pointer}
.penbtn svg{width:20px;height:20px}
.storyta{width:100%;box-sizing:border-box;display:block;border:1px solid var(--line);border-radius:16px;
  background:var(--card);color:var(--fg);padding:16px;font:inherit;font-size:15px;line-height:1.55;
  resize:none;outline:none;min-height:220px;box-shadow:0 8px 24px #0000000d}
.storyta::placeholder{color:var(--muted)}
.storyta:focus{border-color:var(--primary)}
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
/* gap + truncation: a long intent title used to butt straight against the band label
   ("кофе и творческие людиХороший вариант") */
.sumhead{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px;gap:10px}
.sumhead .sumlbl{margin-bottom:0;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sumhead .confpct{flex:none;white-space:nowrap}
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
/* Bottom nav (Figma "Bottom Nav"): a floating white pill, not an edge-to-edge bar, with the coral
   ai-spark FAB raised over its centre. The pill floats over whatever is behind it — clouds on Home,
   the page on every other screen. */
.bnav{flex:none;position:relative;display:flex;align-items:flex-end;justify-content:center;
  height:92px;background:transparent;border:0;padding:0 15px calc(16px + env(safe-area-inset-bottom))}
.navpill{width:100%;max-width:360px;height:64px;display:flex;align-items:center;justify-content:space-between;
  gap:6px;padding:0 20px;background:#fff;border-radius:36px;box-shadow:0 8px 24px rgba(0,0,0,.10)}
.navpill a{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;gap:4px;
  font-size:10px;font-weight:500;line-height:1.4;color:var(--muted);cursor:pointer}
.navpill a.on{color:var(--primary)}
.navpill a svg{width:24px;height:24px}
.navpill a span{max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.navpill .navgap{flex:none;width:58px}
.fab{position:absolute;left:50%;top:0;transform:translateX(-50%);width:60px;height:60px;border-radius:50%;
  background:var(--primary);border:0;display:flex;align-items:center;justify-content:center;cursor:pointer;
  box-shadow:0 4px 10px rgba(245,69,92,.45),0 8px 20px rgba(0,0,0,.18)}
.fab svg{width:30px;height:30px;color:#fff;display:block}
.fab:active{transform:translateX(-50%) scale(.94)}
/* Mascot art. Sized in one place so a pose can be swapped per screen without touching layout. */
.masc{display:block;margin:0 auto;width:132px;height:132px;pointer-events:none;user-select:none}
.masc.sm{width:88px;height:88px}
.masc.xs{width:56px;height:56px;margin:0}
.masc.fill{width:100%;height:100%;object-fit:contain}
.kdraft .masc.xs{width:18px;height:18px;margin:0}
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
/* Candidate row: a COLUMN (identity line, then actions) instead of one flex row cramming avatar +
   name + tier + distance + band + Intro + dismiss into ~340px. That fight made "3.6 км" break across
   two lines, wrapped "Хороший вариант" mid-phrase, and gave rows with buttons a different height
   from rows without, so the list read as ragged. */
.candrow{display:flex;flex-direction:column;gap:8px;padding:12px 16px}
.candmain{display:flex;align-items:center;gap:12px;min-width:0}
.candav{width:38px;height:38px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#FF7A8A,#F5455C);color:#fff;font-weight:800;font-size:15px}
.candt{flex:1;min-width:0}
.candn{font-size:14.5px;font-weight:700;display:flex;align-items:center;gap:4px;min-width:0}
.candnm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.candn .candkm{font-size:11px;font-weight:500;color:var(--muted);white-space:nowrap;flex:none}
.cands{font-size:12px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* The band label sits on its OWN line, not in a right-hand column. Measured: with name + badge + band
   competing for one row, the right column has to drop to 26% before "Zoe Smirnov" stops truncating —
   and by then "Хороший вариант" itself wraps. No column width satisfies both, so the row stacks. */
.candsc{display:flex;align-items:baseline;gap:6px;margin-top:3px;flex-wrap:wrap}
.candpct{font-size:12px;font-weight:800;color:var(--fg);line-height:1.25}
.candbadge{font-size:10px;font-weight:700;color:var(--muted);background:var(--field);border-radius:6px;
  padding:1px 5px;white-space:nowrap;flex:none}
.candbadge.acc{color:var(--accent);background:var(--accent-soft)}
.candacts{display:flex;align-items:center;gap:8px;padding-left:50px}
.candacts .introbtn{margin-left:0}
.passbtn{border:none;background:var(--field);color:var(--muted);width:30px;height:30px;border-radius:50%;
  font-size:13px;cursor:pointer;flex:none}
.candok{font-size:10.5px;font-weight:700;color:#0f7340}
.candbusy{font-size:10.5px;font-weight:600;color:var(--muted)}
.candno{font-size:10.5px;font-weight:600;color:var(--muted)}
.candwait{font-size:10.5px;font-weight:600;color:var(--muted);opacity:.7}
.introbtn{flex:none;font:inherit;font-size:12px;font-weight:700;color:#fff;background:var(--primary);border:0;
  border-radius:999px;padding:7px 13px;cursor:pointer;margin-left:2px}
/* ===== Buddy chat (Figma "assistant chat") ===== */
.bchat{display:flex;flex-direction:column;height:100%;min-height:0}
.chd{flex:none;position:relative;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 4px 12px;min-height:44px}
.chd-ttl{position:absolute;left:0;right:0;text-align:center;font-size:16px;font-weight:700;letter-spacing:-.01em;
  color:var(--fg);pointer-events:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 96px}
.chd-back,.chd-pills{position:relative;z-index:1}
.chd-sub{display:block;font-size:11px;font-weight:500;color:var(--muted);margin-top:1px}
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
/* home -> buddy chat transition: the side blocks fade + slide away, then the chat opens */
.a-leaving{opacity:0;transform:translateY(-8px);transition:opacity .22s ease,transform .22s ease;pointer-events:none}
.asearch.a-lift{transform:translateY(-6px);transition:transform .22s ease}
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
/* ===================== Figma "Agent Home / request flow" (479:14518…14661) =====================
   Design tokens match the existing ones (#F7F8FA / #181B22 / #F5455C / #EEF0F4 / Geist), so these
   rules only add the shapes the new screens need. Sizes are taken verbatim from the frames. */
.k-h2{font-size:24px;line-height:32px;font-weight:600;letter-spacing:-.24px}
.k-h3{font-size:20px;line-height:28px;font-weight:600;letter-spacing:-.1px}
.k-title{font-size:17px;line-height:24px;font-weight:600}
.k-body{font-size:15px;line-height:22px}
.k-small{font-size:13px;line-height:18px}
.k-label{font-size:13px;line-height:16px;font-weight:500}
.k-cap{font-size:12px;line-height:16px}
.k-lbls{font-size:11px;line-height:16px;font-weight:500}
.k-card{background:var(--card);border-radius:16px;box-shadow:0 8px 24px rgba(0,0,0,.06)}
/* greeting + intro */
/* Home sits on the luxeir cloud sky (Figma 1615-21279). The sky is painted on the whole .phone
   (class toggled per-screen in render) so it bleeds behind the status bar and the bottom nav —
   edge to edge. The nav becomes a frosted-glass panel so the sky reads through it while the labels
   stay legible. Cards/field surfaces are translucent for the same reason. */
.phone.homebg{background:#dcebfa url(assets/clouds.jpg) top center/cover no-repeat}
.ah2{display:flex;flex-direction:column;height:100%;background:transparent}
.ah2 .ahd{display:flex;align-items:center;gap:4px;padding:8px 20px}
.ah2 .ahd .nm{flex:1;min-width:0}
.ah2 .bell{width:44px;height:44px;border:.5px solid rgba(226,229,236,.75);border-radius:999px;display:flex;
  align-items:center;justify-content:center;flex:none;cursor:pointer;position:relative;
  background:rgba(255,255,255,.22);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.ah2 .body{flex:1;min-height:0;overflow-y:auto;padding:0 20px 12px;display:flex;flex-direction:column;gap:20px}
.aintro2{display:flex;gap:12px;align-items:center;padding:12px 16px;border-radius:16px}
/* ── Home, rebuilt to the mockup ────────────────────────────────────────────────────────────────
   Two honest substitutions, both forced by what the app actually has:
   the "photo" band is the TILE_SVG illustration atlas (there is not a single photograph anywhere in
   this product), and the participants footer shows the ONE host we really know plus the real `going`
   count — not three invented faces. */
.serif{font-family:'Fraunces',Georgia,'Times New Roman',serif;font-weight:700;letter-spacing:-.4px}
.ah2 .ahd .nm.serif{font-size:22px;line-height:28px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ah2 .bell .dot{position:absolute;top:9px;right:11px;width:8px;height:8px;border-radius:50%;
  background:var(--primary);border:2px solid var(--card)}
.seclbl2{display:flex;align-items:center;gap:6px;font-size:14px;line-height:20px;font-weight:600;color:var(--fg)}
.seclbl2 svg{width:16px;height:16px;color:var(--primary)}

/* the carousel centres its active card and lets BOTH neighbours peek */
.icar{flex:none;display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;
  scroll-padding:0 34px;padding:6px 34px 2px;margin:0 -20px;scrollbar-width:none}
.icar::-webkit-scrollbar{display:none}
.icar .idea{flex:0 0 80%;scroll-snap-align:center}
/* Event Hero Card v2: cover (100) + bookmark, title, date/time + area meta rows, going pill */
.idea{background:var(--card);border-radius:16px;overflow:hidden;position:relative;cursor:pointer;
  box-shadow:0 4px 21.6px #00000014;transition:transform .28s cubic-bezier(.2,.9,.25,1.12),opacity .28s ease}
.idea:not(.on){transform:scale(.95);opacity:.78}
.idea .cov{height:100px;background:var(--neutral100);overflow:hidden;position:relative}
.idea .cov img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;z-index:1}
.idea .cov svg{position:absolute;inset:0;width:100%;height:100%;display:block}
.idea .bm{position:absolute;top:12px;right:12px;z-index:2;width:36px;height:36px;border-radius:999px;
  background:rgba(255,255,255,.18);-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);
  display:flex;align-items:center;justify-content:center;cursor:pointer;color:#fff}
.idea .bm svg{width:19px;height:19px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))}
.idea .bm.on{background:#fff;color:var(--primary)}
.idea .bm.on svg{filter:none;fill:currentColor}
.idea .bd{padding:14px 16px 16px;display:flex;flex-direction:column;gap:10px}
.idea .ti{font-size:17px;line-height:22px;font-weight:600;letter-spacing:-.2px;color:var(--fg);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.idea .mt{display:flex;align-items:center;gap:6px;font-size:13px;line-height:18px;color:var(--fg);
  overflow:hidden;white-space:nowrap}
.idea .mt svg{width:16px;height:16px;flex:none;color:var(--muted)}
.idea .mt span{overflow:hidden;text-overflow:ellipsis;min-width:0}
.idea .mt span+svg{margin-left:2px}
.idea .ft{display:flex;align-items:center;margin-top:2px}
.gpill{display:flex;align-items:center;gap:8px;font-size:13px;line-height:16px;font-weight:500;color:var(--muted);
  min-width:0}
.gpill>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gpill .avg{display:flex;flex:none}
.gpill .av{width:24px;height:24px;border-radius:999px;background:var(--neutral100);border:2px solid var(--card);
  margin-right:-6px;display:flex;align-items:center;justify-content:center;color:var(--muted)}
.gpill .av svg{width:13px;height:13px}
.gpill .av.ct{font-size:11px;font-weight:600;color:var(--muted);margin-right:0}
.gpill .hav{width:24px;height:24px;border-radius:999px;flex:none;background:linear-gradient(135deg,#FF7A8A,#F5455C);
  color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center}
.idots{flex:none;display:flex;gap:6px;justify-content:center;padding-top:10px}
.idots i{width:6px;height:6px;border-radius:999px;background:var(--neutral300);transition:all .2s ease}
.idots i.on{background:var(--primary);width:18px}

/* invite row */
.invrow{flex:none;display:flex;align-items:center;gap:12px;background:var(--card);border-radius:18px;padding:12px 14px;
  box-shadow:0 8px 24px #0000000d;cursor:pointer}
.invrow .iav{width:44px;height:44px;border-radius:50%;flex:none;position:relative;color:#fff;font-weight:700;
  background:linear-gradient(135deg,#FF7A8A,#F5455C);display:flex;align-items:center;justify-content:center}
.invrow .iav .dot{position:absolute;top:0;right:0;width:11px;height:11px;border-radius:50%;
  background:var(--primary);border:2px solid var(--card)}
.invrow .ib{flex:1;min-width:0}
.invrow .ib .t1{font-size:14px;line-height:19px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.invrow .ib .t2{font-size:13px;line-height:18px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.invrow .ir{display:flex;align-items:center;gap:2px;color:var(--primary);font-size:14px;font-weight:600;flex:none}
.invrow .ir svg{width:18px;height:18px}

/* confirmed-meet card — photo, status badge, coral meta, CTA (Figma "Event Card") */
.emeet{flex:none;display:flex;gap:12px;align-items:stretch;background:var(--card);
  border-radius:28px 16px 16px 16px;padding:12px 16px 12px 12px;
  box-shadow:0 2px 6px #0000000f,0 1px 2px #0000000a;cursor:pointer}
.emeet .ava{width:72px;height:72px;flex:none;border-radius:999px;background:var(--neutral100);overflow:hidden;
  display:flex;align-items:center;justify-content:center;color:var(--primary)}
.emeet .ava svg{width:30px;height:30px}
.emeet .ava img{width:100%;height:100%;object-fit:cover;display:block}
.emeet .ava.init{background:linear-gradient(135deg,#FF7A8A,#F5455C);color:#fff;font-weight:700;font-size:26px}
.emeet .mbd{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}
.emeet .mtop{display:flex;align-items:center;justify-content:space-between;gap:10px}
.emeet .mt-title{font-size:15px;line-height:20px;font-weight:600;color:var(--fg);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sbadge{flex:none;padding:4px 10px;border-radius:999px;font-size:11px;line-height:16px;font-weight:500}
.sbadge.ok{background:#E8F7EE;color:#0F7340}
.emeet .mmeta{display:flex;gap:12px;font-size:12px;line-height:16px;color:var(--muted);min-width:0}
.emeet .mmeta span{display:flex;align-items:center;gap:4px;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.emeet .mmeta svg{width:14px;height:14px;flex:none;color:var(--primary)}
.emeet .mbtn{margin-top:2px;height:32px;border:0;border-radius:999px;background:var(--primary);color:#fff;
  font:inherit;font-size:13px;font-weight:500;cursor:pointer}

/* the Buddy composer — avatar + field + history link (Figma "Message Composer v2") */
.bcard{flex:none;padding:6px 20px 12px}
.bcard .brow{display:flex;align-items:center;gap:8px}
.bcard .bav{width:64px;height:64px;flex:none;border-radius:999px;background:var(--neutral100);overflow:hidden;
  display:flex;align-items:center;justify-content:center}
.bcard .fld{flex:1;min-width:0;display:flex;gap:8px;align-items:center;background:#EEF0F473;
  border:.5px solid #ffffff5c;border-radius:22px;padding:12px 16px}
.bcard .fld input{flex:1;min-width:0;border:0;outline:0;background:transparent;font:inherit;
  font-size:15px;color:var(--fg)}
.bcard .fld input::placeholder{color:var(--muted)}
.bcard .fld .mic{color:var(--muted);display:flex;flex:none}
.bcard .fld .mic svg{width:20px;height:20px}
.bcard .snd{width:36px;height:36px;flex:none;border-radius:999px;background:var(--primary);color:#fff;border:0;
  display:flex;align-items:center;justify-content:center;cursor:pointer}
.bcard .snd svg{width:18px;height:18px}
.bcard .hist{display:flex;align-items:center;justify-content:center;gap:6px;margin:12px auto 0;padding:7px 16px;
  background:var(--card);border-radius:16px;box-shadow:0 1px 2px #0000000a;width:max-content;max-width:100%;
  font-size:12px;font-weight:500;color:var(--fg);cursor:pointer}
.bcard .hist svg{width:14px;height:14px;color:var(--primary);flex:none}

.aintro2 .msc{width:72px;height:72px;border-radius:999px;background:var(--neutral100);flex:none;
  display:flex;align-items:center;justify-content:center;color:var(--muted)}
.aintro2 .txt{flex:1;min-width:0;font-size:13px;line-height:18px;color:var(--fg)}
/* composer pill */
.kcomp{display:flex;gap:10px;align-items:center;padding:10px 0}
.kcomp .fld{flex:1;min-width:0;display:flex;gap:8px;align-items:center;background:var(--neutral100);
  border-radius:22px;padding:12px 12px 12px 16px}
.kcomp .fld input{flex:1;min-width:0;border:0;outline:0;background:none;font:inherit;font-size:15px;line-height:22px;color:var(--fg)}
.kcomp .fld input::placeholder{color:var(--muted)}
.kcomp .snd{width:44px;height:44px;flex:none;border-radius:22px;background:var(--primary);color:#fff;
  display:flex;align-items:center;justify-content:center;cursor:pointer;border:0}
/* quick tiles */
.qtile .ic{width:20px;height:20px;color:var(--fg);display:flex;align-items:center;justify-content:center}
.qtile .lb{font-size:10px;line-height:13px;font-weight:500;color:var(--muted)}
/* event card */
.ecard{display:flex;gap:12px;align-items:flex-start;background:var(--card);border-radius:16px;
  padding:12px 16px 12px 12px;position:relative;cursor:pointer}
.ecard .ph{width:94px;height:94px;border-radius:8px;background:var(--neutral100);flex:none;overflow:hidden}
.ecard .ph svg{width:100%;height:100%;display:block}
.ecard .bd{flex:1;min-width:0;display:flex;flex-direction:column;gap:6px;justify-content:center}
.ecard .ti{font-size:15px;line-height:20px;font-weight:600;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ecard .meta{display:flex;gap:12px;margin-top:2px}
.ecard .mi{display:flex;gap:4px;align-items:center;font-size:12px;line-height:16px;color:var(--muted)}
.ecard .mi svg{width:14px;height:14px}
.ecard .who{font-size:12px;line-height:16px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ecard .pact{display:flex;align-items:center;gap:10px;margin-top:4px}
.ecard .pact .kbtn{width:auto;padding:0 18px}
.ecard .pbm{width:26px;height:26px;flex:none;display:flex;align-items:center;justify-content:center;color:var(--muted);cursor:pointer}
.ecard .pbm svg{width:20px;height:20px}
/* "Plans for you" = a horizontal carousel: one wide card at a time, the next peeking to signal swipe.
   Bleeds to the screen edges (cancels .ah2 .body's 20px padding) so a card can be near full-width. */
.carousel{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;
  scrollbar-width:none;margin:0 -20px;padding:2px 0 8px 20px;scroll-padding-left:20px}
.carousel::-webkit-scrollbar{display:none}
.carousel .ecard{flex:0 0 89%;max-width:none;scroll-snap-align:start}
/* flow screens: prompt row, bubbles, plan card, chips */
.kflow{display:flex;flex-direction:column;height:100%;background:var(--bg)}
.kflow .kbar{height:56px;display:flex;align-items:center;gap:8px;padding:0 16px;flex:none}
.kflow .kback{width:44px;height:44px;border:1px solid var(--border);background:var(--card);border-radius:999px;
  display:flex;align-items:center;justify-content:center;cursor:pointer;flex:none}
.kflow .kcont{flex:1;min-height:0;overflow-y:auto;padding:8px 20px 24px;display:flex;flex-direction:column;
  gap:12px;align-items:stretch}
.kflow .kcont > *{flex:0 0 auto}
.kprompt{display:flex;gap:8px;align-items:center}
.kprompt .av{width:32px;height:32px;border-radius:999px;background:var(--primary);color:#fff;flex:none;
  display:flex;align-items:center;justify-content:center}
.kprompt .av svg{width:16px;height:16px}
.kbub{max-width:260px;padding:12px 16px;font-size:15px;line-height:22px}
.kbub.ag{background:var(--neutral100);color:var(--fg);border-radius:18px 18px 18px 1px}
.kbub.me{background:var(--primary);color:#fff;border-radius:18px 18px 1px 18px;align-self:flex-end}
.ktime{font-size:12px;line-height:16px;color:var(--muted)}
.kplan{background:var(--card);border-radius:16px;box-shadow:0 8px 24px rgba(0,0,0,.06);padding:24px 16px 16px;
  display:flex;flex-direction:column;gap:20px;flex:0 0 auto}
.kplan.tight{padding:16px}
/* Summary card «Вот что получилось» — Figma 1688-26605 */
.isumm{flex:none;background:var(--card);border-radius:16px;overflow:hidden;box-shadow:0 4px 21.6px #00000014}
.isumm .cov{height:131px;background:var(--neutral100);position:relative;overflow:hidden}
.isumm .cov svg{position:absolute;inset:0;width:100%;height:100%;display:block}
.isumm .cov img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.isumm .cnt{padding:20px;display:flex;flex-direction:column;gap:20px}
.isumm .ti{font-size:17px;line-height:24px;font-weight:600;color:var(--fg);word-break:break-word}
.isumm .meta{display:flex;flex-direction:column;gap:12px}
.isumm .mt{display:flex;align-items:center;gap:8px;font-size:13px;line-height:18px;color:var(--fg);overflow:hidden}
.isumm .mt svg{width:16px;height:16px;flex:none;color:var(--muted)}
.isumm .mt span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.isumm .mt span+svg{margin-left:2px}
.isumm .kv{display:flex;flex-direction:column;gap:16px}
.isumm .kv .r{display:flex;gap:12px;font-size:13px;line-height:18px;align-items:flex-start}
.isumm .kv .k{width:88px;flex:none;font-weight:500;color:var(--fg)}
.isumm .kv .v{color:var(--fg);min-width:0;word-break:break-word}
.isumm .why{position:relative;background:var(--bg);border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:6px}
.isumm .why .h{font-size:12px;line-height:1.3;font-weight:600;color:var(--primary)}
.isumm .why .tx{font-size:12px;line-height:1.5;color:var(--muted)}
.isumm .why .ed{position:absolute;top:12px;right:12px;width:16px;height:16px;color:var(--primary);cursor:pointer}
.isumm .why .ed svg{width:16px;height:16px}
/* Public profile (candidate) — reconstructed from the Recommendations→Profile flow screenshots */
.cpub{display:flex;flex-direction:column;height:100%;background:var(--bg)}
.cpub .chero{flex:none;position:relative;height:46%;min-height:280px;max-height:440px;background:var(--neutral100);overflow:hidden}
.cpub .chero img{width:100%;height:100%;object-fit:cover;display:block}
.cpub .cnav{position:absolute;top:12px;left:0;right:0;display:flex;justify-content:space-between;padding:0 16px}
.cpub .cbtn{width:44px;height:44px;border-radius:999px;background:#ffffffcc;-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);
  display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--fg);box-shadow:0 1px 3px #0000001f}
.cpub .cbtn svg{width:20px;height:20px}
.cpub .cpb{flex:1;min-height:0;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:16px}
.cpub .chd{display:flex;flex-direction:column;align-items:center;gap:10px;text-align:center}
.cpub .chd .nm{font-size:22px;line-height:28px;font-weight:700;color:var(--fg);display:flex;align-items:center;gap:6px}
.cpub .chd .nm .vf{color:var(--primary);display:flex}
.cpub .chd .nm .vf svg{width:20px;height:20px}
.cpub .chd .bio{font-size:15px;line-height:22px;color:var(--muted);max-width:300px}
.cpub .chd .tgs{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:2px}
.cpub .tg{padding:7px 14px;border-radius:999px;background:var(--neutral100);font-size:13px;font-weight:500;color:var(--fg)}
.cpub .chd .meta{display:flex;align-items:center;gap:6px;font-size:14px;color:var(--fg)}
.cpub .chd .meta svg{width:16px;height:16px;color:var(--muted);flex:none}
.cpub .ksum{background:var(--card);border-radius:16px;padding:16px;box-shadow:0 4px 21.6px #0000000f}
.cpub .ksum .h{font-size:14px;font-weight:600;color:var(--primary);margin-bottom:6px}
.cpub .ksum .tx{font-size:14px;line-height:1.5;color:var(--fg)}
.cpub .cpriv{display:flex;gap:8px;align-items:flex-start;font-size:13px;line-height:1.4;color:var(--muted);padding:0 4px}
.cpub .cpriv svg{width:18px;height:18px;flex:none;color:var(--muted);margin-top:1px}
.cpub .cfoot{flex:none;padding:6px 16px 10px}
.cpub .cinv{width:100%;height:60px;border:0;background:var(--card);border-radius:999px;box-shadow:0 8px 24px #0000000f;
  display:flex;align-items:center;gap:10px;padding:6px;cursor:pointer}
.cpub .cinv .ck{width:48px;height:48px;border-radius:999px;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;flex:none}
.cpub .cinv .ck svg{width:22px;height:22px}
.cpub .cinv .lb{flex:1;text-align:center;font-size:16px;font-weight:600;color:var(--fg)}
.cpub .cinv .ch{display:flex;color:var(--neutral300);padding-right:14px}
.cpub .cinv .ch svg{width:15px;height:15px;margin-left:-5px}
.cpub .bnav{flex:none}
/* Profile options bottom sheet */
.ksheet.copts{display:flex;flex-direction:column;gap:10px}
.copts .chdr{display:flex;align-items:center;justify-content:space-between;margin:2px 0 6px}
.copts .chdr .x{cursor:pointer;color:var(--muted);display:flex}
.copts .chdr .x svg{width:22px;height:22px}
.coptbtn{width:100%;height:56px;border:0;border-radius:16px;font:inherit;font-size:15px;font-weight:600;cursor:pointer;
  display:flex;align-items:center;justify-content:center;gap:10px}
.coptbtn .i{display:flex}.coptbtn .i svg{width:20px;height:20px}
.coptbtn.mute{background:var(--neutral100);color:var(--fg)}
.coptbtn.warn{background:var(--primary);color:#fff}
.coptbtn.dark{background:#181B22;color:#fff}
/* Recommendation card (candidate) */
.rcard{background:var(--card);border-radius:20px;padding:16px;box-shadow:0 4px 21.6px #0000000f;
  display:flex;flex-direction:column;gap:14px}
.rcard .rtop{display:flex;gap:12px;align-items:flex-start;cursor:pointer}
.rcard .rph{width:64px;height:64px;flex:none;border-radius:999px;background:var(--neutral100);overflow:hidden}
.rcard .rph img{width:100%;height:100%;object-fit:cover;display:block}
.rcard .rbd{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.rcard .rnm{font-size:16px;line-height:20px;font-weight:700;color:var(--fg)}
.rcard .rrole{font-size:13px;line-height:18px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rcard .rloc{display:flex;align-items:center;gap:4px;font-size:13px;line-height:18px;color:var(--muted);margin-top:1px}
.rcard .rloc svg{width:14px;height:14px;flex:none}
.rcard .rtags{display:flex;flex-wrap:wrap;gap:8px}
.rcard .rtag{padding:6px 12px;border-radius:999px;background:var(--neutral100);font-size:12px;font-weight:500;color:var(--fg)}
.rcard .rsum .h{font-size:13px;font-weight:600;color:var(--primary);margin-bottom:4px}
.rcard .rsum .tx{font-size:13px;line-height:1.5;color:var(--muted)}
.rcard .rinv{width:100%;height:48px;border:0;border-radius:999px;background:var(--primary);color:#fff;
  font:inherit;font-size:15px;font-weight:600;cursor:pointer}
.kgrp{display:flex;flex-direction:column;gap:12px}
.kgrp .hd{display:flex;gap:8px;align-items:center;font-size:15px;line-height:20px;font-weight:600}
.kgrp .hd svg{width:18px;height:18px}
.kchips{display:flex;gap:8px;flex-wrap:wrap}
.kchip{height:36px;min-height:36px;flex:0 0 auto;padding:0 14px;border-radius:999px;display:flex;align-items:center;justify-content:center;
  font-size:11px;line-height:16px;font-weight:500;cursor:pointer;background:var(--card);
  border:1px solid var(--border);color:var(--fg);white-space:nowrap}
.kchip.on{background:var(--primary);border-color:var(--primary);color:#fff}
.kchip.soft{background:var(--card);border-color:var(--border)}
/* a whole sentence cannot live in a 36px nowrap pill — the hint variant wraps and grows */
.kchip.hint{height:auto;min-height:36px;padding:8px 14px;white-space:normal;text-align:left;
  justify-content:flex-start;max-width:100%;line-height:16px;overflow-wrap:anywhere}
.kwhy{background:var(--bg);border-radius:12px;padding:12px;font-size:12px;line-height:normal;color:var(--muted)}
.krow{display:flex;gap:12px;align-items:center}
.krow .lb{width:80px;flex:none;display:flex;gap:8px;align-items:center;font-size:13px;line-height:16px;font-weight:500}
.krow .lb svg{width:18px;height:18px}
.krow .vl{font-size:13px;line-height:16px;font-weight:500;flex:1;min-width:0}
.kreq{background:var(--bg);border-radius:8px;padding:16px;display:flex;flex-direction:column;gap:12px;justify-content:center}
.kreq .hd{display:flex;gap:8px;align-items:center;font-size:15px;line-height:20px;font-weight:600}
.kreq .hd svg{width:22px;height:22px}
.kcta{display:flex;gap:12px}
.kbtn{flex:0 0 auto;height:48px;min-height:48px;width:100%;border-radius:999px;display:flex;align-items:center;
  justify-content:center;gap:8px;font-size:15px;line-height:20px;font-weight:600;cursor:pointer;border:0;
  font-family:inherit;padding:0 20px}
.kcta .kbtn{flex:1 1 0;width:auto}
.kbtn.pri{background:var(--primary);color:#fff}
.kbtn.sec{background:var(--neutral100);color:var(--fg)}
/* the CTA footer sits under a scrolling body — give it breathing room and a surface so long
   content reads as scrolled-under rather than colliding with the buttons */
.kfoot{flex:none;padding:12px 20px 16px;display:flex;flex-direction:column;gap:8px;
  background:var(--bg);box-shadow:0 -8px 16px -8px rgba(0,0,0,.08)}
.kfoot .kbtn{height:52px}
/* searching */
.ksearching{flex:1;min-height:0;overflow-y:auto;padding:8px 20px 24px;display:flex;flex-direction:column;
  gap:20px;align-items:center;text-align:center}
.ksearching .msc{width:96px;height:96px;border-radius:999px;background:var(--neutral100);
  display:flex;align-items:center;justify-content:center;color:var(--muted)}
.ksearching .brand{font-size:20px;line-height:28px;font-weight:600}
.ksearching .lead{font-size:20px;line-height:28px;font-weight:600;letter-spacing:-.1px}
.ksteps{width:100%;background:var(--card);border-radius:16px;box-shadow:0 8px 24px rgba(0,0,0,.06);
  padding:8px 0;display:flex;flex-direction:column}
.kstep{display:flex;gap:12px;align-items:center;padding:12px 16px;text-align:left}
.kstep .dot{width:18px;height:18px;border-radius:999px;border:2px solid var(--neutral300);flex:none}
.kstep.done .dot{border-color:#0F7340;background:#0F7340}
.kstep.now .dot{border-color:var(--primary);border-right-color:transparent;animation:kspin .8s linear infinite}
@keyframes kspin{to{transform:rotate(360deg)}}
.kstep .tx{flex:1;min-width:0;font-size:13px;line-height:18px}
.kstep .bg{font-size:10px;line-height:14px;font-weight:600;padding:2px 8px;border-radius:999px;
  background:var(--neutral100);color:var(--muted);white-space:nowrap}
.kstep.done .bg{background:var(--success-bg);color:var(--success-text)}
.kstep.now .bg{background:var(--coral50);color:var(--primary)}
/* ============ Figma batch 2 (479:14710…15090): results, profile, why-suggested ============ */
/* new tokens the frames introduced */
.kflow{--success:#1FAE5E;--success-subtle:#E8F7EE;--succ-text:#0F7340;--accent-100:#FCEBC4;
  --warning:#F08C00;--neutral400:#A6ADBB;--primary-subtle:#F7E3E7;--radius-2xl:28px}
/* segmented tabs (Your options / Why suggested) */
.ktabs{display:flex;justify-content:space-between;background:#fff;border-radius:20px;padding:2px;
  flex:0 0 auto;min-height:40px}
.ktabs .kchip{flex:1;min-width:0}
.cityPin{width:44px;height:44px;border-radius:999px;background:var(--primary);color:#fff;font-weight:800;
  font-size:15px;display:flex;align-items:center;justify-content:center;border:3px solid #fff;
  box-shadow:0 3px 10px rgba(20,20,40,.28);cursor:pointer}
.cityPin.me{background:var(--fg)}
.kinput{width:100%;border:1px solid var(--border);border-radius:12px;padding:12px;font-size:14px;
  background:var(--bg);color:var(--fg);outline:none;font-family:inherit}
.kinput:focus{border-color:var(--primary)}
.ksheet.bottom{max-height:86%;display:flex;flex-direction:column}
/* The safety sheet carries 15 toggles: without a scrolling body the sheet grew past the viewport and
   «Принять изменения» sat below the screen edge, unreachable. Header and footer stay put. */
.eshmap{height:210px;margin-top:12px;border-radius:12px;overflow:hidden;background:var(--neutral100);
  border:1px solid var(--line)}
.eshmap .leaflet-container{font:inherit;background:var(--neutral100)}
.esbody{overflow-y:auto;-webkit-overflow-scrolling:touch;flex:1 1 auto;min-height:0;scrollbar-width:none}
.esbody::-webkit-scrollbar{display:none}
/* Personality sheet (Figma 479:19422) — Kleal's own description of you as ONE prose block you can
   correct, on a sheet that keeps its full height so the text has room and «Принять изменения»
   stays pinned at the bottom edge. */
.ksheet.bottom.tall{height:86%}
.pertx{width:100%;box-sizing:border-box;display:block;border:0;border-radius:14px;
  background:var(--neutral100);color:var(--fg);padding:16px;font:inherit;font-size:15px;
  line-height:1.55;resize:none;outline:none;overflow:hidden}
.pertx:focus{box-shadow:inset 0 0 0 1.5px var(--primary)}
/* ===== Explore: full-screen interactive map (Zenly / Citymapper / Airbnb flavoured) ===== */
/* One motion system, so every surface moves like it belongs to the same object. */
.xwrap{position:absolute;inset:0;overflow:hidden;--xtop:14px;
  --e-out:cubic-bezier(.22,.68,0,1);      /* arriving  — emphasised decelerate */
  --e-in:cubic-bezier(.32,0,.78,.16);     /* leaving   — accelerate */
  --e-std:cubic-bezier(.4,.14,.3,1);      /* moving between two places */
  --e-pop:cubic-bezier(.2,.9,.25,1.12);   /* one small overshoot, chips + pins only */
  --d-card-in:340ms; --d-card-out:200ms; --d-chip-in:280ms; --d-chip-out:150ms;
  --xlift:180px;
  /* warm-tinted shadow ramp: neutral grey under coral reads muddy */
  --sh-1:rgba(20,25,40,.16); --sh-2:rgba(20,25,40,.13); --sh-3:rgba(140,22,40,.34)}
.xmap{position:absolute;inset:0;background:#EDF0F5;z-index:0}
.xmap .leaflet-container{font:inherit;background:#EDF0F5}
/* One filter function, not three — this pane is re-transformed every frame during a pan. */
.xmap .leaflet-tile-pane{filter:saturate(.58)}
.xmap::before{content:'';position:absolute;inset:0;z-index:200;pointer-events:none;
  background:linear-gradient(180deg,rgba(255,255,255,.10) 0%,rgba(255,255,255,.05) 100%)}
/* Marker motion is suppressed during the gesture and plays on settle. */
.xmap.moving .xpin,.xmap.moving .xlab,.xmap.moving .xhome{transition:none;animation:none}
.xwrap::after{content:'';position:absolute;inset:0;z-index:1;pointer-events:none;
  box-shadow:inset 0 0 90px rgba(20,25,40,.07),inset 0 0 24px rgba(20,25,40,.04)}
/* --- floating top row --- */
.xtop{position:absolute;left:12px;right:12px;top:var(--xtop);z-index:600;display:flex;gap:8px;align-items:center}
.xtop::before{content:'';position:absolute;left:-12px;right:-12px;top:-58px;height:132px;z-index:-1;
  pointer-events:none;background:linear-gradient(180deg,rgba(247,248,250,.86) 0%,rgba(247,248,250,.56) 46%,rgba(247,248,250,0) 100%)}
.xpill{height:44px;padding:0 14px;border-radius:22px;display:flex;align-items:center;gap:8px;
  background:rgba(255,255,255,.94);-webkit-backdrop-filter:blur(14px) saturate(1.5);backdrop-filter:blur(14px) saturate(1.5);
  border:1px solid rgba(20,25,40,.07);box-shadow:0 1px 2px rgba(20,25,40,.12),0 8px 24px -6px rgba(20,25,40,.28);
  font-size:14px;font-weight:500;letter-spacing:-.005em;color:var(--fg);cursor:pointer;white-space:nowrap;flex:none;
  transition:transform var(--d-chip-out) var(--e-out),box-shadow 160ms linear}
.xpill:active{transform:scale(.97)}
.xpill:focus-within{box-shadow:0 0 0 3px rgba(245,69,92,.18),0 1px 2px rgba(20,25,40,.12),0 8px 24px -6px rgba(20,25,40,.28)}
.xpill svg{width:18px;height:18px;flex:none;color:var(--muted)}
.xpill.grow{flex:1;min-width:0;cursor:text}
.xpill input{flex:1;min-width:0;border:0;outline:0;background:none;font:inherit;font-weight:400;color:var(--fg)}
.xpill input::placeholder{color:var(--muted)}
.xpill b{min-width:22px;height:20px;padding:0 6px;border-radius:10px;
  background:linear-gradient(180deg,#EE3A52 0%,#E02D48 100%);color:#fff;
  font-size:11.5px;font-weight:700;font-variant-numeric:tabular-nums;display:flex;align-items:center;justify-content:center}
.xclr{width:22px;height:22px;border-radius:999px;background:var(--neutral100);color:var(--muted);flex:none;
  display:none;align-items:center;justify-content:center;font-size:13px;line-height:1;cursor:pointer}
.xclr.on{display:flex}
.xredo{position:absolute;left:50%;top:calc(var(--xtop) + 54px);z-index:590;
  height:38px;padding:0 16px;border-radius:19px;background:var(--fg);color:#fff;font-size:13px;font-weight:600;
  display:flex;align-items:center;gap:7px;box-shadow:0 8px 24px -6px rgba(20,25,40,.5);cursor:pointer;
  opacity:0;pointer-events:none;transform:translate(-50%,-8px) scale(.96);
  transition:opacity var(--d-chip-out) linear,transform var(--d-chip-out) var(--e-in);white-space:nowrap}
.xredo.on{opacity:1;pointer-events:auto;transform:translate(-50%,0) scale(1);
  transition:opacity var(--d-chip-in) linear,transform var(--d-chip-in) var(--e-pop)}
.xredo svg{width:15px;height:15px}
/* --- floating right controls --- */
.xctl{position:absolute;right:12px;bottom:20px;z-index:600;display:flex;flex-direction:column;gap:10px;
  align-items:flex-end;transition:transform var(--d-card-out) var(--e-in) 60ms}
.xwrap.card-on .xctl{transform:translate3d(0,calc(-1 * var(--xlift)),0);
  transition:transform var(--d-card-in) var(--e-out)}
.xbtn{width:44px;height:44px;border-radius:999px;background:rgba(255,255,255,.94);
  -webkit-backdrop-filter:blur(14px) saturate(1.5);backdrop-filter:blur(14px) saturate(1.5);
  border:1px solid rgba(20,25,40,.07);color:var(--fg);
  box-shadow:0 1px 2px rgba(20,25,40,.12),0 8px 24px -6px rgba(20,25,40,.30);
  display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:20px;font-weight:500;line-height:1;
  user-select:none;transition:transform 90ms var(--e-out),background 140ms linear}
.xbtn:active{transform:scale(.92);background:#F1F3F7}
.xbtn svg{width:20px;height:20px}
.xzoom{border-radius:22px;overflow:hidden;background:rgba(255,255,255,.94);
  -webkit-backdrop-filter:blur(14px) saturate(1.5);backdrop-filter:blur(14px) saturate(1.5);
  border:1px solid rgba(20,25,40,.07);box-shadow:0 1px 2px rgba(20,25,40,.12),0 8px 24px -6px rgba(20,25,40,.30)}
.xzoom .xbtn{background:none;border:0;box-shadow:none;border-radius:0;-webkit-backdrop-filter:none;backdrop-filter:none}
.xzoom .xbtn+.xbtn{box-shadow:inset 0 1px 0 rgba(20,25,40,.08)}
.xbtn.acc{color:var(--primary);box-shadow:0 0 0 .5px rgba(245,69,92,.18),0 1px 2px rgba(20,25,40,.12),0 8px 24px -6px rgba(188,31,56,.30)}
/* --- pins: wrap TRANSLATES, pin SCALES, label fades on its own --- */
.xpinwrap{display:flex;flex-direction:column;align-items:center;pointer-events:none;
  transform:translate3d(var(--bx,0px),var(--by,0px),0)}
.xpinwrap .xpin{pointer-events:auto}
.xpin{--s:1;--press:1;position:relative;
  border-radius:999px;background:#fff;padding:3px;cursor:pointer;touch-action:manipulation;
  box-shadow:0 0 0 .5px rgba(20,25,40,.10),0 1px 1px var(--sh-1),0 8px 20px -6px var(--sh-2);
  transform:scale(calc(var(--s) * var(--press)));transform-origin:50% 50%;
  transition:transform 160ms var(--e-out),opacity 180ms linear,box-shadow 180ms linear}
.xpin:active{--press:.92}
.xpin .in{width:100%;height:100%;border-radius:999px;display:flex;align-items:center;justify-content:center;
  position:relative;z-index:1}
/* a soft density bloom instead of hard concentric rings (which read as radar/GPS) */
.xpin.city::before{content:'';position:absolute;z-index:0;pointer-events:none;
  left:50%;top:50%;width:var(--bloom,250%);height:var(--bloom,250%);
  transform:translate(-50%,-50%);border-radius:50%;
  background:radial-gradient(circle closest-side,rgba(245,69,92,.18) 0%,rgba(245,69,92,.12) 38%,
    rgba(245,69,92,.045) 68%,rgba(245,69,92,0) 100%)}
.xpin.city[data-n="lg"]{--bloom:300%}
.xpin.city[data-n="md"]{--bloom:270%}
/* coral surfaces get a light model: rim highlight on top, deeper base */
.xpin.city .in,.xpin.grp .in,.xpin.plan.sel .in{
  background:radial-gradient(115% 90% at 50% 4%,rgba(255,255,255,.30) 0%,rgba(255,255,255,0) 52%),
    linear-gradient(180deg,#FF6072 0%,#F5455C 42%,#DE2A46 100%);
  color:#fff;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums;
  box-shadow:inset 0 .5px 0 rgba(255,255,255,.45),inset 0 -1px 0 rgba(120,8,26,.30)}
.xpin.plan{padding:2px}
.xpin.plan .in{background:linear-gradient(180deg,#fff 0%,#F7F9FC 100%);color:var(--primary);
  box-shadow:inset 0 0 0 1.5px rgba(245,69,92,.22),inset 0 .5px 0 rgba(255,255,255,.9)}
.xpin.plan .in svg{width:20px;height:20px;stroke-width:2.1}
/* cluster reads as a STACK of cards — offset solid shadows, no extra DOM */
.xpin.grp{padding:2.5px;
  box-shadow:2.5px 2.5px 0 -.5px #fff,2.5px 2.5px 0 0 rgba(20,25,40,.10),
    5px 5px 0 -1.5px rgba(255,255,255,.92),5px 5px 0 -1px rgba(20,25,40,.08),
    0 0 0 .5px rgba(20,25,40,.10),0 1px 1px var(--sh-1),0 10px 20px -8px var(--sh-3)}
.xpin.grp .in{font-size:13px}
/* selection: overshoot in, flat out — elevation via shadow character, never translateY
   (the pin's CENTRE is the coordinate; lifting it would misplace the mark) */
.xpin.sel{--s:1.3;
  box-shadow:0 0 0 .5px rgba(20,25,40,.12),0 2px 3px rgba(20,25,40,.18),
    0 8px 14px -4px rgba(20,25,40,.22),0 20px 34px -10px rgba(160,20,44,.48);
  transition:transform 260ms var(--e-pop),box-shadow 260ms var(--e-out)}
.xpin.desel{transition:transform 180ms var(--e-out),box-shadow 180ms var(--e-out)}
.xpin.city.sel{--bloom:300%}
.xmap.hasSel .xpin:not(.sel){opacity:.45;transition:opacity 180ms linear}
.xmap.hasSel .xlab{opacity:.40}
/* city name chip: keyline separates better than blur, and costs nothing per marker */
.xlab{margin-top:7px;padding:3px 9px;border-radius:999px;background:rgba(255,255,255,.97);
  box-shadow:0 0 0 .5px rgba(20,25,40,.10),0 1px 1px rgba(20,25,40,.08),0 4px 10px -4px rgba(20,25,40,.30);
  color:#1B1F28;font-size:11.5px;line-height:15px;font-weight:600;letter-spacing:-.006em;
  white-space:nowrap;max-width:118px;overflow:hidden;text-overflow:ellipsis;transition:opacity 160ms linear}
@keyframes xpop{0%{opacity:0;transform:scale(.6)}100%{opacity:1;transform:scale(1)}}
.xpin.new{animation:xpop 200ms var(--e-pop) both;animation-delay:var(--pd,0ms)}
.xpin.sel.new{animation:none}
/* "you" is a PLACE (a city centroid), not a GPS fix: a hollow ink ring, never a blue puck, never a pulse */
.xhome{display:flex;flex-direction:column;align-items:center;pointer-events:none}
.xhome .ring{width:20px;height:20px;border-radius:50%;
  background:radial-gradient(circle at 50% 30%,#fff 0%,#EEF1F6 100%);
  display:flex;align-items:center;justify-content:center;color:#181B22;
  box-shadow:inset 0 0 0 2px rgba(24,27,34,.72),0 0 0 .5px rgba(20,25,40,.10),
    0 1px 2px rgba(20,25,40,.22),0 6px 14px -6px rgba(20,25,40,.34)}
.xhome .ring svg{width:10px;height:10px;stroke-width:2.4}
.xhome .cap{margin-top:5px;padding:2px 7px;border-radius:999px;background:rgba(24,27,34,.86);color:#F2F4F8;
  font-size:10px;line-height:14px;font-weight:600;white-space:nowrap;box-shadow:0 2px 6px -2px rgba(20,25,40,.5)}
.xpin.city.me{box-shadow:0 0 0 2px #fff,0 0 0 3.5px rgba(24,27,34,.62),
  0 1px 1px var(--sh-1),0 12px 22px -8px var(--sh-3)}
/* the ±1.5 km jitter drawn in METRES, so it means the same thing at every zoom */
.xarea{stroke-dasharray:4 6;stroke-linecap:round;pointer-events:none}
/* --- tapped-pin card: the hidden state IS the exit state --- */
.xcard{position:absolute;left:12px;right:12px;bottom:16px;z-index:650;background:#fff;border-radius:22px;
  border:1px solid rgba(20,25,40,.05);box-shadow:0 2px 6px rgba(20,25,40,.10),0 20px 48px -12px rgba(20,25,40,.38);
  padding:16px 18px 18px;
  visibility:hidden;opacity:0;transform:translate3d(0,calc(100% + 20px),0) scale(.97);transform-origin:50% 100%;
  transition:transform var(--d-card-out) var(--e-in),opacity 140ms linear 30ms,
             visibility 0s linear var(--d-card-out)}
.xcard.on{visibility:visible;opacity:1;transform:translate3d(0,0,0) scale(1);
  transition:transform var(--d-card-in) var(--e-out),opacity 130ms linear,visibility 0s}
.xcard .k-h3{font-size:17px;line-height:23px;font-weight:600;letter-spacing:-.01em}
.xcard .k-cap{font-size:12px;line-height:16px}
.xcard .itags{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap}
.xcard .ktag{font-size:11px;line-height:16px;padding:4px 10px}
.xcard .kbtn{height:46px;min-height:46px;margin-top:14px}
.xclose{width:44px;height:44px;margin:-12px -14px -12px 0;display:flex;align-items:center;justify-content:center;
  color:var(--muted);cursor:pointer;font-size:19px;line-height:1;flex:none}
/* --- plans sheet --- */
.xscrim{position:absolute;inset:0;z-index:690;background:rgba(15,18,28,.34);opacity:0;pointer-events:none;
  transition:opacity 260ms var(--e-out)}
.xscrim.on{opacity:1;pointer-events:auto}
.xsheet{position:absolute;left:0;right:0;bottom:0;top:42%;z-index:700;background:var(--bg);
  border-radius:22px 22px 0 0;box-shadow:0 -10px 40px rgba(20,25,40,.22);
  transform:translate3d(0,101%,0);transition:transform 380ms var(--e-out);display:flex;flex-direction:column;contain:paint}
.xsheet.on{transform:translate3d(0,0,0)}
.xsheet .grab{width:38px;height:5px;border-radius:99px;background:var(--neutral300);opacity:.7;margin:10px auto 4px;flex:none}
.xsheet .hd{flex:none;padding:8px 16px 12px;display:flex;align-items:center;justify-content:space-between}
.xsheet .bd{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;
  padding:0 16px calc(18px + env(safe-area-inset-bottom));scrollbar-width:none}
.xsheet .bd::-webkit-scrollbar{display:none}
@media(prefers-reduced-motion:reduce){
  .xsheet,.xcard,.xctl,.xredo,.xpill{transition:none}
  .xpin,.xpin.new,.xpin.sel,.xpin.desel,.xlab{animation:none;transition:none}
}
.khelp{display:flex;justify-content:center;padding:0 12px 6px}
.khelp .kchip{gap:6px;cursor:pointer;height:34px;min-height:34px}
.khelp .kchip svg{width:15px;height:15px}
.khelp .kchip.busy{opacity:.55;pointer-events:none}
.ksugg{display:block;width:100%;box-sizing:border-box;padding:12px 14px;border-radius:16px;
  background:var(--neutral100);border:1px solid var(--border);color:var(--fg);
  font-size:15px;line-height:22px;text-align:left;white-space:normal;overflow-wrap:anywhere;cursor:pointer}
.ksugg:active{background:var(--border)}
/* grouped result surface: one card split by right-inset hairlines, no shadow */
.kgroup{background:var(--card);border-radius:16px;overflow:hidden}
.kgroup .hr{height:1px;background:var(--bg);margin-left:33px}
/* person row / person result card */
.prow{display:flex;gap:12px;align-items:flex-start;padding:12px 16px 12px 12px;position:relative;
  background:var(--card);cursor:pointer}
.prow .ph{width:94px;height:94px;border-radius:999px;background:var(--neutral100);flex:none;
  display:flex;align-items:center;justify-content:center;color:var(--neutral400);overflow:hidden}
.prow .ph img{width:100%;height:100%;object-fit:cover}
.prow .bd{flex:1;min-width:0;display:flex;flex-direction:column;gap:12px}
.prow .nm{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.prow .nm b{font-size:15px;line-height:20px;font-weight:600}
.prow .sub{font-size:12px;line-height:16px;color:var(--muted)}
.prow .meta{display:flex;gap:12px;flex-wrap:wrap}
.prow .mi{display:flex;gap:4px;align-items:center;font-size:12px;line-height:16px;color:var(--muted)}
.prow .mi svg{width:14px;height:14px}
.prow .bm{position:absolute;right:12px;top:12px;width:20px;height:20px;color:var(--muted);cursor:pointer}
.prow.top{border-radius:28px 16px 16px 16px}
.kbadge{padding:4px 10px;border-radius:999px;font-size:11px;line-height:16px;font-weight:500;white-space:nowrap}
.kbadge.ok{background:var(--success-bg);color:var(--success-text)}
.kbadge.warn{background:#FCEBC4;color:#F08C00}
.kbadge.mut{background:var(--neutral100);color:#A6ADBB}
.ktag{padding:4px 10px;border-radius:999px;background:var(--bg);color:var(--muted);
  font-size:11px;line-height:16px;font-weight:500;white-space:nowrap}
/* best fit: fused candidate + reason rows, flat white */
.kfused{background:var(--card);border-radius:16px;padding:8px 0 16px;display:flex;flex-direction:column;gap:8px}
.krsn{display:flex;gap:16px;align-items:center;padding:16px}
.krsn .ic{width:24px;height:24px;flex:none;color:var(--fg)}
.krsn .bd{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.krsn .ti{font-size:17px;line-height:24px;font-weight:600}
.krsn .su{font-size:13px;line-height:18px;color:var(--muted)}
.kbtn.tall{height:56px;min-height:56px}
/* Create-intent suggestions (Figma 1615:21018). A card of stacked rows, not chips: the design
   promotes the openers from a chip row into the primary way in, with its own regenerate control. */
.sugg{display:flex;flex-direction:column;gap:16px;padding:24px 0 16px}
.sugg .lbl{font-size:13px;line-height:16px;font-weight:500;color:var(--muted)}
.sugg .card{display:flex;flex-direction:column;background:var(--card);border-radius:16px;overflow:hidden;
  filter:drop-shadow(0 4px 6px rgba(0,0,0,.08)) drop-shadow(0 1px 1px rgba(0,0,0,.04))}
.sugg .row{min-height:48px;display:flex;align-items:center;justify-content:center;padding:12px 18px;
  font-size:15px;line-height:22px;color:var(--fg);text-align:center;cursor:pointer;background:var(--card)}
.sugg .row:active{background:var(--neutral100)}
.sugg .row+.row{border-top:1px solid var(--border)}
.sugg .hintline{font-size:15px;line-height:22px;color:var(--muted)}
/* Create-intent branching (Figma: format -> group size -> 3-step details) */
.chrow{display:flex;align-items:center;gap:14px;background:var(--card);border:1.5px solid transparent;
  border-radius:16px;padding:14px 16px;cursor:pointer;margin-bottom:10px}
.chrow.on{border-color:var(--primary)}
.chrow .ic{width:24px;height:24px;flex:none;display:flex;align-items:center;justify-content:center;color:var(--fg)}
.chrow .ic svg{width:20px;height:20px}
.chrow .bd{flex:1;min-width:0}
.chrow .ti{font-size:15px;line-height:22px;font-weight:600;color:var(--fg)}
.chrow .su{font-size:13px;line-height:18px;color:var(--muted)}
.chrow .ck{color:var(--primary);opacity:0;flex:none}
.chrow .ck svg{width:20px;height:20px}
.chrow.on .ck{opacity:1}
.stepper{display:flex;align-items:center;padding:2px 0 10px}
.stepper .st{width:22px;height:22px;border-radius:999px;border:1.5px solid var(--border);display:flex;
  align-items:center;justify-content:center;font-size:11px;font-weight:600;color:var(--muted);background:var(--card);flex:none}
.stepper .st.on{border-color:var(--primary);color:var(--primary)}
.stepper .ln{flex:1;height:1.5px;background:var(--border)}
.stepper .ln.on{background:var(--primary)}
.dcard{background:var(--card);border-radius:20px;padding:16px;display:flex;flex-direction:column;gap:14px;
  box-shadow:0 8px 24px rgba(0,0,0,.06)}
.dsec{display:flex;align-items:center;gap:8px;font-size:15px;line-height:22px;font-weight:600;color:var(--fg)}
.dsec svg{width:18px;height:18px;color:var(--primary)}
.dchips{display:flex;gap:8px;overflow-x:auto;padding-bottom:2px;-webkit-overflow-scrolling:touch}
.dchips .c{flex:none;padding:8px 12px;border-radius:999px;border:1px solid var(--border);background:var(--card);
  font-size:13px;color:var(--fg);cursor:pointer;white-space:nowrap}
.dchips .c.on{background:var(--primary);border-color:var(--primary);color:#fff}
.seg{display:flex;background:var(--neutral100);border-radius:999px;padding:3px}
.seg .o{flex:1;text-align:center;padding:8px 6px;border-radius:999px;font-size:13px;color:var(--fg);cursor:pointer}
.seg .o.on{background:var(--primary);color:#fff}
.dial{display:block;margin:0 auto;touch-action:none;cursor:pointer}
.dial .val{font-size:34px;font-weight:600;letter-spacing:-1px;fill:var(--fg)}
.rowlbl{display:flex;justify-content:space-between;align-items:center;font-size:13px;color:var(--muted)}
.rowlbl b{color:var(--primary);font-weight:600}
.disc{display:flex;gap:8px;font-size:11px;line-height:15px;color:var(--muted)}
.disc svg{width:16px;height:16px;flex:none;opacity:.7}
.tinput{width:100%;border:1px solid var(--border);background:var(--card);border-radius:12px;padding:12px 14px;
  font-size:15px;color:var(--fg);outline:none}
.kbtn.sm{height:40px;min-height:40px;font-size:13px;line-height:16px;font-weight:500}
/* candidate profile */
.cprof{display:flex;gap:12px;align-items:center;padding:0 16px 12px 12px}
.cprof .av{width:124px;height:124px;border-radius:999px;background:var(--neutral100);flex:none;position:relative;
  display:flex;align-items:center;justify-content:center;color:var(--neutral400);overflow:hidden}
.cprof .av img{width:100%;height:100%;object-fit:cover}
.cprof .dot{position:absolute;left:102px;top:102px;width:8px;height:8px;border-radius:999px;
  background:#1FAE5E;box-shadow:0 0 0 2px rgba(52,185,0,.4)}
.cprof .bd{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}
.kplan.flat{box-shadow:none}
.kblk{display:flex;flex-direction:column;gap:12px}
.kblk .hd{font-size:13px;line-height:16px;font-weight:500}
.kblk .tx{font-size:13px;line-height:18px;color:var(--muted)}
.kfacts{display:flex;flex-direction:column;gap:8px}
.kfact{display:flex;gap:8px;align-items:center;font-size:13px;line-height:18px;color:var(--muted)}
.kfact i{width:6px;height:6px;border-radius:999px;background:var(--neutral300);flex:none}
/* why suggested: check bullets */
.kwhycard{background:var(--card);border-radius:16px;padding:20px 16px;display:flex;flex-direction:column;gap:16px}
.kbullet{display:flex;gap:8px;align-items:center}
.kbullet .dot{width:16px;height:16px;border-radius:999px;background:#1FAE5E;flex:none;
  display:flex;align-items:center;justify-content:center}
.kbullet .dot svg{width:10px;height:10px}
.kbullet .tx{flex:1;min-width:0;font-size:13px;line-height:18px}
.kbullet.neg .dot{background:var(--neutral300)}
/* modal sheet */
.kscrim{position:absolute;inset:0;background:rgba(0,0,0,.4);backdrop-filter:blur(2px);
  display:flex;align-items:center;justify-content:center;padding:16px;z-index:40}
.ksheet{width:100%;background:var(--card);border-radius:16px;box-shadow:0 -4px 32px rgba(0,0,0,.10);
  padding:24px 20px 20px;display:flex;flex-direction:column;gap:24px;align-items:center;text-align:center}
.kmedal{width:88px;height:88px;border-radius:999px;background:#F7E3E7;display:flex;align-items:center;
  justify-content:center;color:var(--primary)}
.kmedal svg{width:36px;height:36px}
/* ============ Figma batch 3: request → mutual → meetup planning → meetup day ============ */
/* summary rows on "What will be sent" */
.kshare{background:var(--card);border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:20px}
.kshare .it{display:flex;gap:12px;align-items:flex-start}
.kshare .ic{width:22px;height:22px;flex:none;color:var(--fg);margin-top:1px}
.kshare .bd{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.kshare .ti{font-size:15px;line-height:20px;font-weight:600}
.kshare .su{font-size:13px;line-height:18px;color:var(--muted)}
.knote{display:flex;gap:8px;align-items:flex-start;font-size:12px;line-height:16px;color:var(--muted);padding:0 2px}
.knote svg{width:14px;height:14px;flex:none;margin-top:1px}
.kinfo{display:flex;gap:8px;align-items:flex-start;background:var(--info-bg);color:var(--info-text);
  border-radius:12px;padding:12px;font-size:13px;line-height:18px}
.kinfo svg{width:16px;height:16px;flex:none;margin-top:1px}
/* big centred state (waiting / mutual) */
.kstate{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;padding:8px 0 4px}
.kstate .hero{width:160px;height:160px;border-radius:999px;background:var(--neutral100);
  display:flex;align-items:center;justify-content:center;color:var(--neutral300);margin-bottom:8px}
.kstate .hero.sm{width:72px;height:72px}
.kstate .ti{font-size:24px;line-height:32px;font-weight:600;letter-spacing:-.24px}
.kstate .su{font-size:13px;line-height:18px;color:var(--muted)}
/* list rows with chevron (Change request / See other options / What's next) */
.klist{background:var(--card);border-radius:16px;overflow:hidden}
.klist .row{display:flex;gap:12px;align-items:center;padding:16px;cursor:pointer}
.klist .row+.row{border-top:1px solid var(--line)}
.klist .ic{width:36px;height:36px;border-radius:999px;background:var(--card);border:1px solid var(--border);
  display:flex;align-items:center;justify-content:center;flex:none;color:var(--fg)}
.klist .bd{flex:1;min-width:0}
.klist .ti{font-size:17px;line-height:24px;font-weight:600}
.klist .su{font-size:12px;line-height:16px;color:var(--muted)}
.klist .ch{color:var(--neutral300);flex:none}
/* two participant cards */
.kpair{display:flex;gap:12px}
.kpair .p{flex:1;min-width:0;background:var(--card);border-radius:16px;padding:16px 12px;
  display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center}
.kpair .av{width:64px;height:64px;border-radius:999px;background:var(--neutral100);
  display:flex;align-items:center;justify-content:center;color:var(--neutral300)}
.kpair .nm{font-size:15px;line-height:20px;font-weight:600}
.kpair .su{font-size:12px;line-height:16px;color:var(--muted)}
/* plan card rows with icon (time / place) */
.kplanrow{display:flex;gap:8px;align-items:flex-start}
.kplanrow .ic{width:20px;height:20px;flex:none;color:var(--primary);margin-top:2px}
.kplanrow .bd{flex:1;min-width:0}
.kplanrow .ti{font-size:15px;line-height:20px;font-weight:600}
.kplanrow .su{font-size:12px;line-height:16px;color:var(--muted)}
.kquote{background:var(--bg);border-radius:12px;padding:12px;font-size:13px;line-height:18px}
.kdraft{display:flex;gap:4px;align-items:center;background:var(--neutral100);border-radius:999px;
  padding:4px 10px;font-size:11px;line-height:16px;font-weight:500;color:var(--muted);white-space:nowrap}
.kdraft svg{width:12px;height:12px}
/* time slots */
.kslot{display:flex;gap:12px;align-items:center;background:var(--card);border-radius:12px;padding:14px 16px;
  border:1px solid transparent;cursor:pointer;flex:0 0 auto}
.kslot.on{border-color:var(--primary)}
.kslot .ic{width:32px;height:32px;border-radius:999px;background:var(--card);border:1px solid var(--border);
  display:flex;align-items:center;justify-content:center;flex:none;color:var(--fg)}
.kslot .bd{flex:1;min-width:0}
.kslot .d{font-size:15px;line-height:20px;font-weight:600}
.kslot .w{font-size:12px;line-height:16px;color:var(--muted)}
.kslot .t{font-size:15px;line-height:20px;font-weight:600;flex:none}
.kslot .ck{color:var(--primary);flex:none;width:20px}
/* places */
.kmap{height:150px;border-radius:12px;background:var(--neutral100);position:relative;overflow:hidden;
  display:flex;align-items:center;justify-content:center;color:var(--neutral300)}
.kmap .pin{position:absolute;color:var(--primary)}
.kplace{display:flex;gap:12px;background:var(--card);border-radius:12px;padding:12px;
  border:1px solid transparent;cursor:pointer;flex:0 0 auto}
.kplace.on{border-color:var(--primary)}
.kplace .ph{width:88px;height:88px;border-radius:8px;background:var(--neutral100);flex:none}
.kplace .bd{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}
.kplace .nm{font-size:15px;line-height:20px;font-weight:600}
.kplace .meta{display:flex;gap:12px;flex-wrap:wrap}
.kplace .mi{display:flex;gap:4px;align-items:center;font-size:12px;line-height:16px;color:var(--muted)}
.kplace .mi svg{width:14px;height:14px}
.kplace .tags{display:flex;gap:6px;flex-wrap:wrap}
/* toggles list (calendar / reminder) */
.ktogrow{display:flex;gap:12px;align-items:center;padding:12px 0}
.ktogrow .ic{width:20px;height:20px;flex:none;color:var(--primary)}
.ktogrow .tx{flex:1;min-width:0;font-size:15px;line-height:20px}
/* meetup status options */
.kstatus{display:flex;gap:12px;align-items:flex-start;border-radius:16px;padding:16px;cursor:pointer;
  border:1px solid transparent}
.kstatus .ic{width:24px;height:24px;flex:none}
.kstatus .bd{flex:1;min-width:0}
.kstatus .ti{font-size:17px;line-height:24px;font-weight:600}
.kstatus .su{font-size:13px;line-height:18px;color:var(--muted)}
.kstatus.go{background:var(--success-bg)} .kstatus.go .ic,.kstatus.go .ti{color:var(--success-text)}
.kstatus.late{background:var(--warn-bg)} .kstatus.late .ic,.kstatus.late .ti{color:var(--warn-text)}
.kstatus.here{background:var(--success-bg)} .kstatus.here .ic,.kstatus.here .ti{color:var(--success-text)}
.kstatus.on{border-color:currentColor}
.kbanner{display:flex;gap:12px;align-items:center;background:var(--success-bg);border-radius:12px;padding:14px 16px}
.kbanner .ic{width:24px;height:24px;flex:none;color:var(--success-text)}
.kbanner .bd{flex:1;min-width:0}
.kbanner .ti{font-size:17px;line-height:24px;font-weight:600;color:var(--success-text)}
.kbanner .su{font-size:12px;line-height:16px;color:var(--success-text);opacity:.8}
/* accordion rows (What's next / Security) */
.kacc{background:var(--card);border-radius:16px;overflow:hidden}
.kacc .row{display:flex;gap:12px;align-items:center;padding:16px;cursor:pointer}
.kacc .row+.row{border-top:1px solid var(--line)}
.kacc .ic{width:24px;height:24px;flex:none;color:var(--fg)}
.kacc .bd{flex:1;min-width:0}
.kacc .ti{font-size:15px;line-height:20px;font-weight:600}
.kacc .su{font-size:12px;line-height:16px;color:var(--muted)}
/* bottom sheet (Security) */
.ksheet.bottom{border-radius:20px 20px 0 0;align-items:stretch;text-align:left;padding:12px 16px 24px;
  margin-top:auto;gap:16px}
.kscrim.bot{align-items:flex-end;padding:0}
.kgrab{width:44px;height:4px;border-radius:999px;background:var(--neutral300);margin:0 auto}
/* intents tab cards */
.icard{background:var(--card);border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:12px}
.itile{margin:-16px -16px 4px;height:94px;overflow:hidden;border-radius:16px 16px 0 0;background:#FFF3EC}
.itile svg{width:100%;height:100%;display:block}
.ftile{height:118px;border-radius:12px;overflow:hidden;margin-bottom:12px}
.ftile svg{width:100%;height:100%;display:block}
.ihd{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}
.itl{flex:1;min-width:0;font-size:17px;line-height:24px;font-weight:600;overflow:hidden;
  text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.itags{display:flex;gap:6px;flex-wrap:wrap}
.ifoot{display:flex;align-items:center;justify-content:space-between;gap:10px}
.iacts{display:flex;gap:8px}
.iacts .kbtn{flex:1}
/* few matches: adjustment options */
.kopt{display:flex;gap:12px;align-items:flex-start;padding:16px;border-radius:12px;border:1px solid transparent;cursor:pointer}
.kopt.sel{border-color:var(--primary);background:var(--card)}
.kopt .ic{width:22px;height:22px;flex:none;color:var(--fg);margin-top:2px}
.kopt .bd{flex:1;min-width:0}
.kopt .ti{font-size:15px;line-height:20px;font-weight:600}
.kopt .su{font-size:12px;line-height:16px;color:var(--muted);margin-top:2px}
.kopt .ck{color:var(--primary);flex:none}
.ktog{width:44px;height:26px;border-radius:999px;background:var(--neutral300);position:relative;flex:none;
  transition:background .18s;cursor:pointer}
.ktog.on{background:var(--primary)}
.ktog i{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:999px;background:#fff;transition:left .18s}
.ktog.on i{left:21px}
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
// True when nobody arrived from onboarding: the screens are then filled with a sample identity,
// and the app must SAY so rather than passing "Dmitry" off as the user's own profile.
const IS_DEMO = !_pParam;
let _saved = null; try{ _saved = JSON.parse(localStorage.getItem(PKEY)||'null'); }catch(_e){}
if(_saved && _saved._src===_psrc && _saved.data){ DATA = _saved.data; }
else { try{ localStorage.removeItem(PKEY); }catch(_e){} _saved = null; }
// ---- migrate saved state: strip the demo seed people/plans that used to ship in DATA ----
// Removing the seed from the source is not enough: anyone who opened the app before still has
// the fake intents ("Coffee & AI talk", Marc/Nina) and duplicate cards in localStorage.
(function migrate(){
  if(!DATA) return;
  let changed=false;
  // Threads saved by an older build carry the AI-drafted opener as a message FROM the other person —
  // a real name, a "now" timestamp, and words they never wrote. A thread where the other side spoke
  // first and the user never sent anything is impossible in this product, so it is unambiguous: demote
  // that text to the suggestion it always was. Without this, everyone who opened the app before the
  // fix keeps seeing the fabricated message.
  if(Array.isArray(DATA.messages)){
    DATA.messages.forEach(t=>{
      if(!t||t.kleal||!Array.isArray(t.msgs)||!t.msgs.length) return;
      if(t.msgs.some(m=>m&&m.who==='me')) return;              // a real exchange — leave it alone
      const first=t.msgs.find(m=>m&&m.who==='them'&&m.text&&m.text!=='…');
      if(!first) return;
      if(!t.suggest) t.suggest=first.text;
      t.msgs=[]; t.last=T('Интро сделано — напиши первым','Intro made — say hi first');
      changed=true;
    });
  }
  const GHOSTS=['marc','nina','ana','coffee & ai talk','startup founders meetup','spanish + coffee swap',
                'morning coffee & ai chat'];
  const ghost=v=>GHOSTS.includes(String(v||'').trim().toLowerCase());
  if(Array.isArray(DATA.intents)){
    const key=x=>String((x&&(x.title||x.query))||'').trim().toLowerCase(), seen=new Set();
    const keep=DATA.intents.filter(it=>{
      if(!it) return false;
      if(String(it.id||'').startsWith('seed-')||ghost(it.title)) return false;
      (it.candidates||[]).some(c=>ghost(c&&c.name)) && (it.candidates=[]);
      const k=key(it); if(k&&seen.has(k)) return false; if(k) seen.add(k);
      if(it.confidence!==undefined){ delete it.confidence; }        // percentages are gone
      return true; });
    if(keep.length!==DATA.intents.length){ changed=true; } DATA.intents=keep;
  }
  ['plans','messages','memory'].forEach(k=>{
    if(!Array.isArray(DATA[k])) return;
    const keep=DATA[k].filter(x=>!(ghost(x&&(x.who||x.title||x.signal))));
    if(keep.length!==DATA[k].length){ DATA[k]=keep; changed=true; }
  });
  if(Array.isArray(DATA.notifs)){
    const keep=DATA.notifs.filter(n=>!ghost(n&&n.title)&&!/Coffee & AI talk/i.test((n&&n.title)||''));
    if(keep.length!==DATA.notifs.length){ DATA.notifs=keep; changed=true; }
  }
  if(changed){ try{ localStorage.setItem(PKEY, JSON.stringify({_src:_psrc, data:DATA, ui:(_saved&&_saved.ui)||{}})); }catch(_e){} }
})();
const A=document.getElementById('app');
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// ---- UI language (i18n). Default RU; a switch in the profile flips it. T(ru,en) picks the string. ----
let UILANG='ru'; try{ const _l=localStorage.getItem('kleal_uilang'); if(_l==='ru'||_l==='en') UILANG=_l; }catch(_e){}
function T(ru,en){ return UILANG==='en' ? en : ru; }
// Localize machine/back-end DISPLAY strings (times, distances, generic place labels) to the UI
// language. The server and the buddy emit these in English — "Sat 17:00", "tomorrow afternoon",
// "within 10 km", "Public places nearby" — and the client used to render them verbatim, so a Russian
// UI showed English fragments. User-authored content (plan titles, names, areas) is NOT touched.
const _LOC_RU=[
  [/\bmonday\b/gi,'понедельник'],[/\btuesday\b/gi,'вторник'],[/\bwednesday\b/gi,'среда'],[/\bthursday\b/gi,'четверг'],[/\bfriday\b/gi,'пятница'],[/\bsaturday\b/gi,'суббота'],[/\bsunday\b/gi,'воскресенье'],
  [/\bMon\b/g,'Пн'],[/\bTue\b/g,'Вт'],[/\bWed\b/g,'Ср'],[/\bThu\b/g,'Чт'],[/\bFri\b/g,'Пт'],[/\bSat\b/g,'Сб'],[/\bSun\b/g,'Вс'],
  [/\bCenter\b/gi,'Центр'],[/\bWest\b/gi,'Запад'],[/\bEast\b/gi,'Восток'],[/\bSouth\b/gi,'Юг'],[/\bBeach\b/gi,'Пляж'],
  [/\bTomorrow\b/g,'Завтра'],[/\btomorrow\b/g,'завтра'],[/\bToday\b/g,'Сегодня'],[/\btoday\b/g,'сегодня'],[/\btonight\b/gi,'сегодня вечером'],
  [/\bthis weekend\b/gi,'в выходные'],[/\bweekend\b/gi,'выходные'],[/\bthis week\b/gi,'на неделе'],
  [/\blate evening\b/gi,'поздно вечером'],[/\bmorning\b/gi,'утром'],[/\bafternoon\b/gi,'днём'],[/\bevening\b/gi,'вечером'],[/\bnight\b/gi,'ночью'],[/\blate\b/gi,'поздно'],
  [/\bFlexible\b/gi,'Гибко'],
  [/\bMax travel\b/gi,'до'],[/\bwithin\b/gi,'в пределах'],[/\bMax\b/g,'до'],
  [/\bkm\b/gi,'км'],[/\bmin\b/gi,'мин'],
  [/\bPublic places nearby\b/gi,'Публичные места рядом'],[/\bOnline if it falls through\b/gi,'Онлайн, если не сложится'],[/\bOnline\b/gi,'Онлайн'],
];
function locStr(s){ if(UILANG!=='ru'||!s) return s||''; let out=String(s); _LOC_RU.forEach(p=>{ out=out.replace(p[0],p[1]); }); return out; }
// Interest/topic vocabulary. Topics are stored canonically in English (the taxonomy the matcher
// ranks on), so tags and the "vibe" line rendered raw English words inside a Russian UI. Generic
// concepts are translated; proper names (game titles, K-pop, UX) deliberately pass through, and any
// word not in the table is returned unchanged — a user's own free-text interest is never mangled.
const _TOPIC_RU={
  coffee:'кофе',tea:'чай',brunch:'бранч',cafe:'кафе',dinner:'ужин',lunch:'обед',food:'еда',
  restaurant:'ресторан',cooking:'готовка',baking:'выпечка',bar:'бар',drinks:'напитки',pub:'паб',
  beer:'пиво',wine:'вино',party:'вечеринки',club:'клуб',clubbing:'клубы',nightlife:'ночная жизнь',
  walk:'прогулки',walking:'прогулки',stroll:'прогулки',hang:'тусовки',hangout:'тусовки',chill:'чилл',
  talk:'разговоры',chat:'разговоры',cowork:'коворкинг',coworking:'коворкинг',remotework:'удалёнка',
  football:'футбол',soccer:'футбол',basketball:'баскетбол',volleyball:'волейбол',handball:'гандбол',
  tennis:'теннис',padel:'падел',badminton:'бадминтон',squash:'сквош',pingpong:'настольный теннис',
  running:'бег',jogging:'пробежки',cycling:'велосипед',biking:'велосипед',swimming:'плавание',
  triathlon:'триатлон',marathon:'марафон',gym:'зал',fitness:'фитнес',workout:'тренировки',
  crossfit:'кроссфит',boxing:'бокс',mma:'ММА',climbing:'скалолазание',bouldering:'болдеринг',
  yoga:'йога',pilates:'пилатес',stretching:'растяжка',sports:'спорт',team:'командные',
  chess:'шахматы',boardgames:'настолки',tabletop:'настолки',poker:'покер',cards:'карты',
  gaming:'игры',games:'игры',game:'игры',esports:'киберспорт',multiplayer:'мультиплеер',strategy:'стратегии',
  cinema:'кино',movies:'кино',film:'кино',screen:'кино',series:'сериалы',art:'искусство',museum:'музеи',
  gallery:'галереи',photography:'фотография',exhibition:'выставки',painting:'живопись',visual:'визуальное',
  theatre:'театр',opera:'опера',ballet:'балет',standup:'стендап',stage:'сцена',books:'книги',
  reading:'книги',literature:'литература',bookclub:'книжный клуб',architecture:'архитектура',
  urbanism:'урбанистика',city:'город',culture:'культура',
  startup:'стартапы',startups:'стартапы',product:'продукт',founder:'фаундеры',entrepreneur:'предприниматели',
  business:'бизнес',ai:'ИИ',ml:'машинное обучение',programming:'программирование',coding:'программирование',
  software:'софт',data:'данные',crypto:'крипта',blockchain:'блокчейн',networking:'нетворкинг',
  investing:'инвестиции',investor:'инвесторы',career:'карьера',mentorship:'менторство',design:'дизайн',
  tech:'технологии',engineering:'инженерия',
  concert:'концерты',gig:'концерты',festival:'фестивали',music:'музыка',vinyl:'винил',guitar:'гитара',
  piano:'пианино',drums:'барабаны',dj:'диджеинг',jam:'джемы',producing:'продюсирование',singing:'вокал',
  karaoke:'караоке',band:'группа',rave:'рейвы',techno:'техно',edm:'электронная музыка',electronic:'электроника',
  listening:'музыка',making:'музыка',
  hiking:'походы',trekking:'треккинг',nature:'природа',camping:'кемпинг',mountains:'горы',trail:'тропы',
  outdoor:'на природе',outdoors:'на природе',surfing:'сёрфинг',kayaking:'каякинг',skiing:'лыжи',
  snowboard:'сноуборд',travel:'путешествия',roadtrip:'автопутешествия',sightseeing:'прогулки по городу',
  fishing:'рыбалка',sailing:'парусный спорт',diving:'дайвинг',
  spanish:'испанский',english:'английский',french:'французский',german:'немецкий',italian:'итальянский',
  portuguese:'португальский',russian:'русский',language:'языки',languages:'языки',exchange:'языковой обмен',
  practice:'практика',course:'курсы',workshop:'воркшопы',study:'учёба',skills:'навыки',learning:'обучение',
  social:'общение',casual:'неформально',meet:'встреча',
  pets:'питомцы',dogs:'собаки',cats:'кошки',fashion:'мода',pottery:'керамика',knitting:'вязание',
  gardening:'садоводство',volunteering:'волонтёрство',meditation:'медитация',astrology:'астрология',
  anime:'аниме',cosplay:'косплей',podcasting:'подкасты',
};
// Personality words the test emits. They are not topics, so they never reached _TOPIC_RU and the
// vibe chips stayed English on a Russian screen.
const _TRAIT_RU={
  'calm':'спокойный','friendly':'дружелюбный','intellectual':'интеллектуальный','playful':'игривый',
  'energetic':'энергичный','cozy':'уютный','focused':'сосредоточенный','curious':'любознательный',
  'warm':'тёплый','open':'открытый','quiet':'тихий','funny':'с юмором','thoughtful':'вдумчивый',
  'confident':'уверенный','easy-going':'лёгкий в общении','easygoing':'лёгкий в общении',
  'ambitious':'амбициозный','creative':'творческий','caring':'заботливый','honest':'честный',
  'adventurous':'лёгок на подъём','reserved':'сдержанный','optimistic':'оптимистичный',
  'light casual':'лёгкое общение','light':'лёгкое общение','casual':'неформальное',
  'medium':'среднее','deep talk':'глубокие разговоры','deep':'глубокие разговоры',
  'topic-based':'по теме','topic based':'по теме','small talk':'светская беседа'};
function locTopic(w){ if(UILANG!=='ru'||!w) return w||''; const k=String(w).trim().toLowerCase();
  if(_TRAIT_RU[k]) return _TRAIT_RU[k];
  // plain plurals too — the store holds both "walk" and "walks", "book"/"books"
  return _TOPIC_RU[k] || (k.length>3&&k.slice(-1)==='s'&&_TOPIC_RU[k.slice(0,-1)]) || w; }
// "dota, game, multiplayer" -> "dota, игры, мультиплеер"
function locTopicList(s){ if(UILANG!=='ru'||!s) return s||'';
  return String(s).split(/\s*,\s*/).filter(Boolean).map(locTopic).join(', '); }
function setUILang(l){ UILANG=(l==='en'?'en':'ru'); try{localStorage.setItem('kleal_uilang',UILANG);}catch(_e){} render(); }
// ---- receiving policy (доступность): читаем/пишем свой статус через onboarding /api/onboarding/receiving ----
// RECV_ERR: the profile may not exist in the matching store at all — the demo identity never does, and
// a user who hasn't finished onboarding doesn't either. Without this the screen drew three availability
// buttons that silently could not work: none selected, nothing saved, no reason given.
let RECV=null, RECV_BUSY=false, RECV_ERR=null;
function loadRecv(){ if(RECV||RECV_ERR||RECV_BUSY||!(DATA&&DATA.name)) return; RECV_BUSY=true;
  fetch('/api/onboarding/receiving',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:DATA.name})}).then(x=>x.json())
    .then(r=>{ RECV_BUSY=false; if(r&&r.ok){ RECV=r.receiving; } else { RECV_ERR=(r&&r.error)||'unavailable'; } render(); })
    .catch(()=>{ RECV_BUSY=false; RECV_ERR='network'; render(); }); }
function setAvail(st){ if(!(DATA&&DATA.name)) return;
  fetch('/api/onboarding/receiving',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:DATA.name,receiving:{status:st}})}).then(x=>x.json())
    .then(r=>{ if(r&&r.ok){ RECV=r.receiving; toast(T('Доступность обновлена','Availability updated')); }
               else toast(T('Не удалось сохранить','Could not save')); render(); })
    .catch(()=>toast(T('Не удалось сохранить','Could not save'))); }
function svg(inner,vb,w){return '<svg viewBox="'+(vb||'0 0 24 24')+'" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="'+(w||24)+'" height="'+(w||24)+'">'+inner+'</svg>';}
const IC={
  // --- Figma "Agent Home / request flow" set (479:14518…14661) ---
  mic:svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3"/>',null,20),
  send:svg('<path d="M21 3L10.5 13.5M21 3l-6.8 18-3.7-7.5L3 9.8 21 3z"/>',null,20),
  bell:svg('<path d="M18 15.5V10a6 6 0 1 0-12 0v5.5L4 18h16l-2-2.5z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',null,20),
  calen:svg('<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 9.8h17M8 3.2v3.6M16 3.2v3.6"/>',null,18),
  target:svg('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.2"/><circle cx="12" cy="12" r="1.1" fill="currentColor"/>',null,18),
  diamond:svg('<path d="M6 3h12l3.5 5.4L12 21 2.5 8.4 6 3z"/><path d="M2.5 8.4h19M9 3l3 5.4L15 3M12 8.4V21"/>',null,18),
  binoc:svg('<path d="M7 4h3v11H4V9l3-5zM17 4h-3v11h6V9l-3-5z"/><circle cx="7" cy="17" r="3.4"/><circle cx="17" cy="17" r="3.4"/><path d="M10.4 15h3.2"/>',null,22),
  radius:svg('<circle cx="12" cy="12" r="3"/><path d="M12 3.2v2.4M12 18.4v2.4M3.2 12h2.4M18.4 12h2.4"/><circle cx="12" cy="12" r="8.6" stroke-dasharray="3 3"/>',null,22),
  homeSm:svg('<path d="M4 10.5L12 4l8 6.5V20H4z"/>',null,22),
  groups:svg('<circle cx="8.5" cy="9" r="3"/><circle cx="16" cy="10.5" r="2.4"/><path d="M3 19a5.5 5.5 0 0 1 11 0M15 19a4.4 4.4 0 0 1 6 0" />',null,22),
  photo:svg('<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="9" cy="10.5" r="1.8"/><path d="M4.5 17.5l4.8-4.3 3.4 3 2.6-2.1 4.2 3.6"/>',null,22),
  doc:svg('<path d="M14 3H7.5A2.5 2.5 0 0 0 5 5.5v13A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V8z"/><path d="M14 3v5h5"/><path d="M8.5 13h7"/><path d="M8.5 16.5h4.5"/>',null,20),
  // --- batch 3: meetup planning + meetup day ---
  info:svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.6v.6"/>',null,16),
  bolt:svg('<path d="M13 3L5.5 13H11l-1 8 7.5-10H12l1-8z"/>',null,24),
  pinDot:svg('<path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/>',null,24),
  walk:svg('<circle cx="13" cy="4.5" r="1.8"/><path d="M12.5 8l-3 3 1.5 4M12.5 8l3.5 2M11 15l-2 6M15 13l1.5 3 .5 5"/>',null,14),
  calAdd:svg('<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 9.8h17M8 3.2v3.6M16 3.2v3.6M12 12.6v5M9.5 15.1h5"/>',null,20),
  bellSm:svg('<path d="M18 15.5V10a6 6 0 1 0-12 0v5.5L4 18h16l-2-2.5z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',null,20),
  shieldSm:svg('<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z"/>',null,14),
  checkCircle:svg('<circle cx="12" cy="12" r="9"/><path d="M8 12.4l2.6 2.6L16 9.6"/>',null,24),
  userLeave:svg('<circle cx="9" cy="8" r="3.2"/><path d="M3.4 19.5a5.6 5.6 0 0 1 9.2-4.3"/><path d="M15.5 15.5l4 4M19.5 15.5l-4 4"/>',null,24),
  help:svg('<circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .9-1 1.6v.3M12 17.2v.3"/>',null,24),
  dots:svg('<circle cx="12" cy="5.5" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="12" cy="18.5" r="1.3"/>',null,20),
  plusCircle:svg('<circle cx="12" cy="12" r="9"/><path d="M12 8.4v7.2M8.4 12h7.2"/>',null,20),
  expand:svg('<path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7"/>',null,18),
  back:svg('<path d="M15 6l-6 6 6 6"/>'),
  bookmark:svg('<path d="M6 4h12v17l-6-4-6 4V4z"/>'),
  chevL:svg('<path d="M15 6l-6 6 6 6"/>'),
  verify:'<svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 2.6l2.2 1.7 2.8-.2.9 2.7 2.4 1.5-.7 2.8.7 2.8-2.4 1.5-.9 2.7-2.8-.2L12 21.4l-2.2-1.7-2.8.2-.9-2.7-2.4-1.5.7-2.8-.7-2.8 2.4-1.5.9-2.7 2.8.2L12 2.6z" fill="#F5455C"/><path d="M8.6 12l2.2 2.2 4.6-4.6" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  edit:svg('<path d="M4 20h4L18.5 9.5a2 2 0 0 0-2.83-2.83L5 17z"/><path d="M14 7l3 3"/>',null,22),
  person:svg('<circle cx="12" cy="8.5" r="3.6"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/>',null,26),
  pin:svg('<path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/>'),
  globe:svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>'),
  chain:svg('<path d="M9.5 14.5l5-5"/><path d="M11.5 6.5l1.2-1.2a3.7 3.7 0 0 1 5.2 5.2l-2 2a3.7 3.7 0 0 1-5.2 0"/><path d="M12.5 17.5l-1.2 1.2a3.7 3.7 0 0 1-5.2-5.2l2-2a3.7 3.7 0 0 1 5.2 0"/>'),
  users:svg('<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M16 6.2a3 3 0 0 1 0 5.6M20.5 19a5.5 5.5 0 0 0-3.5-5.1"/>'),
  clock:svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>'),
  shield:svg('<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z"/>'),
  football:svg('<circle cx="12" cy="12" r="9"/><path d="M12 8l3.2 2.3-1.2 3.7h-4L8.8 10.3 12 8z"/><path d="M12 3v3M4.5 8.5l2.5 1.8M19.5 8.5l-2.5 1.8M7.5 19l1.3-3M16.5 19l-1.3-3"/>'),
  rocket:svg('<path d="M14 4c3 1 5 3 6 6-2 3-6 6-9 7l-3-3c1-3 3-7 6-9z"/><path d="M9 15l-2 4M6 12l-3 1M8 18l-3 1"/><circle cx="14.5" cy="9.5" r="1.4"/>'),
  building:svg('<rect x="5" y="4" width="9" height="16" rx="1"/><path d="M14 9h5v11h-5M8 8h3M8 12h3M8 16h3"/>'),
  chat:svg('<path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-4 4v-4a2 2 0 0 1-1-1.7V6z"/>'),
  gamepad:svg('<rect x="3" y="8" width="18" height="9" rx="4"/><path d="M8 12h3M9.5 10.5v3"/><circle cx="16" cy="11.5" r="1"/><circle cx="17.8" cy="13.5" r="1"/>'),
  film:svg('<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 5v14M16 5v14M4 9.5h4M16 9.5h4M4 14.5h4M16 14.5h4"/>'),
  peek:'<svg viewBox="14 9 68 68" width="44" height="44" fill="none" aria-hidden="true">'+
    '<defs><linearGradient id="kpk" x1="21" y1="10" x2="74" y2="73" gradientUnits="userSpaceOnUse">'+
    '<stop stop-color="#FF796D"/><stop offset="1" stop-color="#E84242"/></linearGradient></defs>'+
    '<circle cx="48" cy="43" r="34" fill="url(#kpk)"/>'+
    '<ellipse cx="48" cy="39" rx="21" ry="19" fill="#FFF8EB"/>'+
    '<circle cx="41" cy="39" r="2.7" fill="#111217"/><circle cx="55" cy="39" r="2.7" fill="#111217"/>'+
    '<path d="M43 47c3 3 7 3 10 0" stroke="#111217" stroke-width="2.5" stroke-linecap="round"/></svg>',
  spark:svg('<path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17l-1.9-5.1L4.5 10l5.6-1.4L12 3z"/>'),
  aispark:'<svg viewBox="0 0 30 30" width="30" height="30" fill="currentColor" aria-hidden="true">'
    +'<path d="M15 3.5l2 5.9a4.3 4.3 0 0 0 2.7 2.7l5.9 2-5.9 2a4.3 4.3 0 0 0-2.7 2.7l-2 5.9-2-5.9a4.3 4.3 0 0 0-2.7-2.7l-5.9-2 5.9-2A4.3 4.3 0 0 0 13 9.4l2-5.9z"/>'
    +'<path d="M24 3.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2z"/>'
    +'<path d="M7 19l.6 1.7 1.7.6-1.7.6L7 23.6l-.6-1.7L4.7 21.3l1.7-.6L7 19z"/></svg>',
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
document.getElementById('sbic').innerHTML=
 '<svg viewBox="0 0 20 14" fill="#181B22" width="18" height="13"><rect x="0" y="9" width="3" height="5" rx="1"/><rect x="5.3" y="6" width="3" height="8" rx="1"/><rect x="10.6" y="3" width="3" height="11" rx="1"/><rect x="15.9" y="0" width="3" height="14" rx="1"/></svg>'
 +'<svg viewBox="0 0 20 15" fill="none" stroke="#181B22" stroke-width="1.9" stroke-linecap="round" width="18" height="14"><path d="M2 5.2a13 13 0 0 1 16 0M5 8.6a8 8 0 0 1 10 0M8 12a3 3 0 0 1 4 0"/></svg>'
 +'<svg viewBox="0 0 28 14" width="25" height="13"><rect x="1" y="1.4" width="22" height="11.2" rx="3" stroke="#181B22" stroke-opacity=".5" fill="none"/><rect x="2.8" y="3.1" width="16.5" height="7.8" rx="1.6" fill="#181B22"/><rect x="24.3" y="4.6" width="2.3" height="4.8" rx="1.1" fill="#181B22" fill-opacity=".5"/></svg>';
document.getElementById('back').innerHTML=IC.back;
// bottom nav (Intents · Search · [create] · Messages · Profile) — rebuilt each render for the active state
const ROOTS=['agenthome','overview','intents','search','messages'];
function navFam(){
  if(cur==='agenthome'||cur==='notifs')return'';   // center FAB owns these — no pill highlight
  if(cur==='search')return'explore';
  if(cur==='intents'||cur==='matchchat')return'plans';
  if(cur==='messages')return'messages';
  return'profile'; }
function bnavHTML(){ const fam=navFam();
  // Intents · Explore · [Home] · Messages · Profile  (Figma "My Intents · Search · [FAB] · Messages · Profile").
  // The center FAB opens the AGENT HOME (agenthome) — the main landing that carries the Kleal banner, the
  // "Say hi to Kleal" field and quick actions. The conversational chat is reached from there.
  const items=[['nIntents',T('Интенты','Intents'),'intents','plans'],['nSearch',T('Обзор','Explore'),'search','explore'],['fab','','',''],
    ['nMsg',T('Сообщения','Messages'),'messages','messages'],['nProfile',T('Профиль','Profile'),'overview','profile']];
  return '<div class="fab" data-act="go-home">'+IC.aispark+'</div>'+
    '<div class="navpill">'+
    items.map(x=>{ if(x[0]==='fab') return '<span class="navgap"></span>';
      return `<a class="${fam===x[3]?'on':''}" data-nav="${x[2]}">${IC[x[0]]}<span>${x[1]}</span></a>`; }).join('')+
    '</div>';
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

  // English 3rd-person -s: naive concatenation produced "Watchs football" / "Studys Spanish".
  const verb3 = v => { v=String(v||''); return /(?:[sxz]|ch|sh)$/i.test(v) ? v+'es'
    : (/[^aeiou]y$/i.test(v) ? v.slice(0,-1)+'ies' : v+'s'); };
  const conf=[];
  if(op.name) conf.push('Name is '+op.name);
  if(op.age)  conf.push(op.age+' years old');
  if(city)    conf.push('Lives in '+city);
  if(langs.length) conf.push('Speaks '+langs.join(' / '));
  ints.forEach(nm=>{ const r=roleOf(nm); conf.push((r?cap(verb3(arr(r)[0]))+' ':'Into ')+nm); });
  if(sf.publicPlacesOnly!==false) conf.push('Prefers public places');
  const knows={confirmedList:conf, inferredList:[], temporaryList:[]};   // counters are derived from these lists at render time

  const memory=[];
  ints.forEach(nm=>{ const r=roleOf(nm), e=pickBy(exp,nm);
    memory.push({signal:(r?cap(verb3(arr(r)[0]))+' ':'Into ')+nm+(e?' ('+e+')':''), source:'Onboarding', confidence:'High', status:'Confirmed', used:true, updated:'Just now'}); });
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
    summaryUpdated: op.summary?Date.now():null,   // device-local: the store has no such column
    story: op.story||'',                          // the free-form life story, own field, own whitelist entry
    personality: op.personality||'', personalityUpdated: op.personality?Date.now():null,
    persona: op.persona||null,                    // the test's own record of what was answered
    matchingPaths: ints.slice(0,3), snapshot:snap, interests, basics,
    social, availability:[], places, goals, safety, memory, knows,
    // canonical shared-profile fields — the same names the users.json row carries, so the
    // client, buddy and matching all read one vocabulary instead of re-parsing display strings
    age:op.age||null, gender:op.gender||null, area:city||'', radiusKm:km||null,
    langsList:langs.map(l=>({'english':'en','spanish':'es','german':'de','french':'fr','portuguese':'pt',
      'italian':'it','russian':'ru','catalan':'ca'}[String(l).toLowerCase()]||String(l).slice(0,2).toLowerCase())),
    formats:[], geo:(op.geo&&op.geo.coarseLat!=null)?{coarseLat:op.geo.coarseLat,coarseLon:op.geo.coarseLon}:null,
    intents:[], plans:[], messages:[] };

  const tabs=['overview'];
  if(snap.length) tabs.push('snapshot');
  if(interests.length) tabs.push('interests');
  tabs.push('social');   // the screen now has three reasons to exist — photo, the test, the story —
                         // none of which depend on Kleal having collected social data first
  if(places.length) tabs.push('places');
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
  ['safety','Safety','Safety & Privacy'],
];
const TABS = ALL_TABS;
let cur = 'agenthome';   // main landing after onboarding
// The profile sub-sections were missing here, so render() fell through to ALL_TABS — a table whose
// two columns are both English. Result: the app bar stayed «Your personality» / «Safety & Privacy»
// on a fully Russian screen.
const TITLES=()=>({interests:T('Интересы','Interests'), social:T('Личность','Personality'),
  safety:T('Безопасность и приватность','Safety & Privacy'), places:T('Места и время','Places & times'),
  knows:T('Что Kleal знает','What Kleal knows'),
  memory:T('Что Kleal помнит','What Kleal remembers'), intents:T('Интенты','Plans'), search:T('Обзор','Explore'), messages:T('Сообщения','Messages'), agenthome:T('Главная','Home'), notifs:T('Уведомления','Notifications'),
  settings:T('Настройки','Settings'), help:T('Помощь и поддержка','Help & Support'),
  privacy:T('Приватность и безопасность','Privacy & Security')});   // functions so language switch re-evaluates
if(!DATA.notifs) DATA.notifs=[]; if(!DATA.intents) DATA.intents=[];   // buddy-agent stores
function setTab(id){ detail=null; cur=id; render(); }
// Overview is a hub of drill-in "Settings Rows"
const SECMETA=()=>({
  interests:['star',T('Интересы','Interests'),T('Чем ты любишь заниматься с людьми','What you like doing with people')],
  social:['faceScan',T('Твоя личность','Your personality'),T('Как ты воспринимаешься','How you come across')],
  safety:['userLock',T('Безопасность и приватность','Safety & Privacy'),T('Что Kleal может использовать и твои границы','What Kleal can use, and your limits')],
});
function navRows(){
  return TABS.filter(t=>t[0]!=='overview').map(t=>{ const m=SECMETA()[t[0]]||['star',t[2],''];
    return `<div class="card setrow" data-nav="${t[0]}"><div class="sic">${IC[m[0]]}</div>
      <div class="st"><div class="stt">${esc(m[1])}</div><div class="sts">${esc(m[2])}</div></div>
      <div class="sedit" data-act="editrow" data-row="${esc(t[0])}">${IC.wand}<span>${T('Изменить','Edit')}</span></div></div>`; }).join('');
}

function cbadge(c){ return `<span class="cbadge cb-${c}">${c}</span>`; }
// ---- display localisation for generated profile strings ----
// mapOnboarding() bakes English sentences into DATA ("Lives in Barcelona", "Plays football", "Just now")
// and those strings are PERSISTED to localStorage and used as lookup keys (summaryRow's title is the
// editrow key). Translating them at build time would freeze the language and break the keys, so the
// stored value stays canonical English and only the RENDERED text is localised — the same approach
// whyDetail() already uses for engine details. Language switching therefore keeps working live.
const _RU_FIELD={'Basics':'Основное','Location':'Локация','Languages':'Языки','Interests':'Интересы',
  'Social formats':'Формат встреч',
  'Safety':'Безопасность','Onboarding':'Онбординг','High':'Высокая','Medium':'Средняя','Low':'Низкая',
  'Confirmed':'Подтверждено','Inferred':'Предположение','Temporary':'Временно','Just now':'Только что',
  'Role':'Роль','Experience':'Опыт','New profile':'Новый профиль'};
const _RU_PAT=[
  [/^Name is (.+)$/,           m=>'Имя: '+m[1]],
  [/^(\d+) years old$/,        m=>m[1]+' лет'],
  [/^Lives in (.+)$/,          m=>'Живёт в '+m[1]],
  [/^Based in (.+?)(, within (\d+) km)?$/, m=>'Живёт в '+m[1]+(m[3]?', в радиусе '+m[3]+' км':'')],
  [/^Speaks (.+)$/,            m=>'Говорит на '+m[1]],
  [/^Comfortable in (.+)$/,    m=>'Общается на '+m[1]],
  [/^Prefers public places$/,  ()=>'Предпочитает публичные места'],
  [/^Public places( only)?$/,  ()=>'Публичные места'],
  [/^Matching on$/,            ()=>'Подбор включён'],
  [/^Adjacent (on|matches allowed)$/,()=>'Смежные совпадения включены'],
  [/^Verified preferred$/,     ()=>'Предпочитает верифицированных'],
  [/^No private locations$/,   ()=>'Без частных адресов'],
  [/^Default$/,                ()=>'По умолчанию'],
  [/^Location sharing$/,       ()=>'Геолокация'],
  [/^Area only, never exact location$/,()=>'Только район, никогда точное место'],
  [/^Max (\d+) km$/,           m=>'до '+m[1]+' км'],
  [/^Into (.+)$/,              m=>'Увлекается: '+m[1]],
  [/^Plays? (.+)$/,            m=>'Играет в '+m[1]],
  // the s? / s{0,2} slack absorbs strings already persisted by the old naive pluraliser ("Watchs",
  // "Discusss") — those live in users' localStorage and can't be regenerated.
  [/^Watch(?:e?s)? (.+)$/,     m=>'Смотрит '+m[1]],
  [/^Practi[sc]e?s? (.+)$/,    m=>'Практикует '+m[1]],
  [/^Discuss(?:e?s{0,2})? (.+)$/, m=>'Обсуждает '+m[1]],
  [/^Reads? (.+)$/,            m=>'Читает '+m[1]],
  [/^Visits? (.+)$/,           m=>'Ходит: '+m[1]],
  [/^Learns? (.+)$/,           m=>'Учит '+m[1]],
  [/^Supports? (.+)$/,         m=>'Болеет за '+m[1]],
];
function ruTxt(s){
  s=String(s==null?'':s);
  if(UILANG!=='ru'||!s) return s;
  if(_RU_FIELD[s]) return _RU_FIELD[s];
  for(const [re,f] of _RU_PAT){ const m=s.match(re); if(m) return f(m); }
  // Values are often "<sentence> · <sentence>" — translate each part rather than giving up on the row.
  if(s.includes(' · ')){ const parts=s.split(' · '); const t=parts.map(p=>ruTxt(p));
    if(t.some((x,i)=>x!==parts[i])) return t.join(' · '); }
  return s;   // unknown shape (a real name, a city, free text) -> leave it exactly as the user wrote it
}
function summaryRow(r, edit){ return `<div class="card srow"><div class="si">${IC[r.icon]||''}</div>
  <div class="st"><div class="stt">${esc(ruTxt(r.title))}</div><div class="stv">${esc(ruTxt(r.value))}</div></div>
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
// `act` lets the same row live inside an edit sheet, where taps must mutate the sheet's draft and
// re-render rather than write DATA behind the user's back.
function sTog(label,desc,on,flag,act){ return `<div class="trow">${sTt(label,desc)}
  <div class="sw ${on?'on':''}" ${act?`data-act="${act}" data-v="${flag}"`:`data-sflag="${flag}"`}><i></i></div></div>`; }
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
  {t:T('Как Kleal действует за тебя','How Kleal acts for you'), c:T('Главные рычаги: насколько агент самостоятелен и пауза в один тап.','The big levers — your agent’s autonomy and a one-tap pause.'), items:[
    {k:'choice', label:T('Когда Kleal кого-то находит','When Kleal finds someone'), desc:T('Спрашивать перед тем, как написать, или пусть Kleal знакомит сам.','Ask before reaching out, or let Kleal introduce you automatically.'),
      options:[T('Сначала спросить','Ask me first'),T('Знакомить сам','Introduce automatically')], sel:(f.autonomy==='auto'?1:0), act:'autonomy'},
    {k:'tog', label:T('Спрашивать перед тем, как делиться моими данными','Confirm before sharing my details'), desc:T('Спрашивать, прежде чем показать твоё имя, фото или контакты — даже когда Kleal сам договаривается о встрече.','Ask before revealing your name, photo or contact — even when Kleal arranges plans for you.'), on:f.confirmShare!==false, flag:'confirmShare'},
    {k:'tog', label:T('Поставить Kleal на паузу','Pause Kleal'), desc:T('Остановить новые подборы и знакомства. Профиль и память сохранятся.','Stop all new matching and outreach. Your profile and memory stay saved.'), on:!!f.paused, flag:'paused'},
  ]},
  {t:T('Встречи вживую','Meeting in person'), c:T('Как Kleal делает встречи безопаснее. Здесь везде: включено = безопаснее.','How Kleal keeps real-world plans safe. Every switch here: on = safer.'), items:[
    {k:'tog', label:T('Первые встречи — только в людных местах','Keep first meetups public'), desc:T('Первые встречи проходят в кафе, парках и других общественных местах.','First meets stay in cafes, parks and other public spots.'), on:f.publicFirst!==false, flag:'publicFirst'},
    {k:'tog', label:T('Никаких встреч один на один поздно вечером','No solo late-night meets'), desc:T('Kleal не будет предлагать встречи наедине поздним вечером.','Kleal avoids one-on-one plans late at night.'), on:f.noLateNight!==false, flag:'noLateNight'},
    {k:'tog', label:T('Избегать мест, где всё вокруг алкоголя','Avoid alcohol-focused venues'), desc:T('Пропускать бары и подобные места для первых встреч.','Skip bars and heavy-drinking spots for first meets.'), on:!!f.avoidAlcohol, flag:'avoidAlcohol'},
    {k:'tog', label:T('Делиться планом с доверенным контактом','Share my plan with a trusted contact'), desc:T('Автоматически отправлять близкому человеку, с кем, где и когда ты встречаешься, и проверять потом, как всё прошло.','Auto-send who, where and when to someone you choose, with a check-in after.'), on:!!f.sharePlan, flag:'sharePlan'},
    {k:'stat', label:T('Доверенный контакт','Trusted contact'), desc:T('Выбери, кому уходят твои планы. Мы сообщим человеку, что ты его добавил.','Choose who receives your plans. They’ll be told you added them.'), val:(f.trustedContact||T('Не выбран','Not set')), btn:(f.trustedContact?T('Изменить','Change'):T('Добавить','Add')), act:'trusted-contact'},
  ]},
  {t:T('Что Kleal может использовать и запоминать','What Kleal may use & remember'), c:T('Твоё согласие на то, что Kleal читает и узнаёт. Включено = Kleal может это использовать.','Your consent for what Kleal reads and learns. On = Kleal may use it.'), items:[
    {k:'tog', label:T('Подбирать по моим интересам и району','Match on my interests & area'), desc:T('Использовать твои увлечения и район города — но никогда точное местоположение.','Use what you like and your city area — never your exact location.'), on:f.useInterestsArea!==false, flag:'useInterestsArea'},
    {k:'tog', label:T('Учиться на моих оценках и действиях','Learn from my feedback & activity'), desc:T('Использовать твои оценки и то, какие планы ты принимаешь или отклоняешь.','Use your ratings and which plans you accept or decline.'), on:f.useFeedback!==false, flag:'useFeedback'},
    {k:'tog', label:T('Разрешить Kleal делать выводы обо мне','Let Kleal infer new things about me'), desc:T('Разрешить догадки сверх того, что ты сказал напрямую — например, о любимых местах.','Allow guesses beyond what you stated, like preferred venues.'), on:f.inferNew!==false, flag:'inferNew'},
    {k:'sub', label:T('Ограничения','Guardrails')},
    {k:'tog', label:T('Никогда не делать выводов о чувствительном','Never infer sensitive traits'), desc:T('Не хранить в памяти здоровье, религию, политику и ориентацию.','Keep health, religion, politics and orientation out of memory.'), on:f.noSensitive!==false, flag:'noSensitive'},
    {k:'act', label:T('Посмотреть, что Kleal помнит','Review what Kleal remembers'), desc:T('Посмотреть, исправить или удалить отдельные сигналы.','See, correct or forget individual signals.'), act:'review-memory'},
  ]},
  {t:T('Как тебя находят люди','How people find you'), c:T('Твой охват и видимость. Включено = больше охват, выключено = больше приватности.','Your reach and visibility. On = more reach, off = more private.'), items:[
    {k:'tog', label:T('Предлагать людей за пределами привычного круга','Suggest people beyond my usual circles'), desc:T('Иногда предлагать людей со смежными интересами и планы вне привычного.','Occasionally propose friends-of-interests and plans outside your usuals.'), on:f.suggestBeyond!==false, flag:'suggestBeyond'},
    {k:'tog', label:T('Показывать меня на карте','Show me on the discovery map'), desc:T('Другие смогут наткнуться на тебя на общей карте.','Let others come across you on the public map.'), on:!!f.publicMap, flag:'publicMap'},
    {k:'tog', label:T('Режим знакомств','Dating mode'), desc:T('По умолчанию выключен. Включи, чтобы Kleal предлагал и романтические знакомства.','Off by default. Turn on to let Kleal suggest dating intros too.'), on:!!f.datingMode, flag:'datingMode'},
  ]},
  {t:T('Верификация и люди','Verification & people'), c:T('С кем Kleal будет тебя знакомить. Включено = осторожнее.','Who Kleal will introduce you to. On = more protective.'), items:[
    {k:'stat', label:T('Моя верификация','My verification'), desc:T('Подтверди фото и документ, чтобы другие знали, что ты настоящий.','Verify your photo and ID so others know you’re real.'),
      val:(f.verified?T('Подтверждён','Verified'):T('Не подтверждён','Not verified')), btn:(f.verified?null:T('Подтвердить','Verify')), act:'verify-me', icon:(f.verified?IC.verify:'')},
    {k:'tog', label:T('Предпочитать подтверждённых людей','Prefer verified people'), desc:T('Kleal будет отдавать предпочтение подтверждённым профилям.','Kleal favours verified profiles when it matches you.'), on:f.preferVerified!==false, flag:'preferVerified'},
    {k:'act', label:T('Чёрный список','Blocked people'), desc:T('Люди, с которыми Kleal никогда тебя не сведёт.','People Kleal will never match or introduce you to.'), val:((f.blockedCount||0)+T(' заблокировано',' blocked')), act:'blocked'},
    {k:'tog', label:T('Не сводить меня с теми, кого я могу знать','Don’t match me with people I may know'), desc:T('Исключить коллег, бывших и контакты из телефона.','Exclude coworkers, exes and phone contacts from suggestions.'), on:f.excludeKnown!==false, flag:'excludeKnown'},
    {k:'act', label:T('Пожаловаться или получить помощь','Report a problem or get help'), desc:T('Пожаловаться на человека или связаться с центром безопасности.','Report someone or reach the safety centre.'), act:'report'},
  ]},
  {t:T('Твои данные','Your data'), c:T('Твои права на данные. В любой момент забери копию или удали всё.','Your data rights. Take a copy or erase everything, anytime.'), items:[
    {k:'act', label:T('Скачать мои данные','Download my data'), desc:T('Выгрузить всё, что Kleal о тебе хранит.','Export everything Kleal holds about you.'), act:'export-data'},
    {k:'act', label:T('Удалить аккаунт и память','Delete my account & memory'), desc:T('Навсегда стереть профиль и всё, что Kleal узнал. Все текущие знакомства будут отменены.','Permanently erase your profile and everything Kleal learned. Any in-flight introductions are cancelled.'), act:'delete-account', danger:true},
  ]},
]; }
function safetyRow(it, act){
  if(it.k==='tog')    return sTog(it.label,it.desc,it.on,it.flag,act);
  if(it.k==='act')    return sAct(it.label,it.desc,it.val,it.act,it.danger);
  if(it.k==='stat')   return sStat(it.label,it.desc,it.val,it.btn,it.act,it.icon);
  if(it.k==='choice') return sChoice(it.label,it.desc,it.options,it.sel,it.act);
  if(it.k==='sub')    return sSub(it.label);
  return ''; }
function checkRow(label,on,key){ on=ui(key,on); return `<div class="crow"><div class="cbx ${on?'on':''}" data-cbx data-uk="${key||''}">${on?IC.check:''}</div>
  <div class="cl">${esc(label)}</div></div>`; }

let editingSummary=false, SUMBUSY=false, _sumTried=false;
// The summary used to be written ONLY by adaptSummary() after a profile edit, so a user who never
// edited anything saw the placeholder forever. Generate it the first time the profile is opened,
// as soon as there is enough to describe.
function ensureSummary(){
  if(_sumTried||SUMBUSY||DATA.summary) return;
  const ints=(DATA.interests||[]).length, snap=(DATA.snapshot||[]).length;
  if(ints+snap < 2) return;                     // nothing real to describe yet — keep the placeholder
  _sumTried=true; SUMBUSY=true;
  adaptSummary().then(()=>{ SUMBUSY=false; render(); });
}
function scr_overview(){
  const d=DATA;
  ensureSummary();
  const sum = editingSummary
    ? `<textarea id="sumta" class="sumta">${esc(d.summary)}</textarea>
       <div class="linkrow"><button data-act="savesum">${T('Сохранить','Save')}</button><button data-act="cancelsum">${T('Отмена','Cancel')}</button></div>`
    : (d.summary
        ? `<div class="sumtxt">${esc(d.summary)}</div>
           <div class="linkrow" style="margin-top:10px"><button data-act="editsum">${T('Изменить','Edit')}</button>
             <button data-act="resum">${T('Пересобрать','Rewrite')}</button></div>`
        : `<div class="sumtxt">${esc(SUMBUSY
             ? T('Kleal составляет описание…','Kleal is writing your summary…')
             : T('Kleal опишет тебя здесь по мере знакомства.','Kleal will summarise you here as it learns more.'))}</div>`);
  const langRow=`<div class="card setrow" style="justify-content:space-between">
    <div class="sic">${IC.globe}</div>
    <div class="st"><div class="stt">${T('Язык интерфейса','Interface language')}</div></div>
    <div class="langtoggle">
      <button class="langbtn ${UILANG==='ru'?'on':''}" data-act="set-lang" data-lang="ru">RU</button>
      <button class="langbtn ${UILANG==='en'?'on':''}" data-act="set-lang" data-lang="en">EN</button></div></div>`;
  const rst=(RECV&&RECV.status)||null; if(!RECV) loadRecv();
  const availRow=`<div class="card setrow" style="justify-content:space-between">
    <div class="sic">${IC.spark}</div>
    <div class="st"><div class="stt">${T('Доступность','Availability')}</div>
      ${RECV_ERR?`<div class="stv">${T('Доступно после онбординга','Available after onboarding')}</div>`:''}</div>
    ${RECV_ERR?'':`<div class="langtoggle">
      <button class="langbtn ${rst==='active'?'on':''}" data-act="set-avail" data-st="active">${T('Открыт','Open')}</button>
      <button class="langbtn ${rst==='busy'?'on':''}" data-act="set-avail" data-st="busy">${T('Занят','Busy')}</button>
      <button class="langbtn ${rst==='paused'?'on':''}" data-act="set-avail" data-st="paused">${T('Пауза','Pause')}</button></div>`}</div>`;
  syncBasicsRows();          // the four cards always reflect canonical fields, incl. a not-yet-set formats card
  return `<div class="stack fade">
    <div class="card idcard">
      <div class="idrow"><div class="ava" data-act="edit-photo" style="cursor:pointer${DATA.photo?`;background-image:url(${DATA.photo});background-size:cover;background-position:center`:''}">${DATA.photo?'':IC.person}</div>
        <div class="it"><div class="nm">${esc(d.name)} ${d.verified?`<span class="badge-verify">${IC.verify}</span>`:'<span class="reddot"></span>'}</div></div></div>
      <div class="confrow2"><span class="l">${T('Наполненность профиля','Profile confidence')}</span><span class="confpct">${d.confidence}%</span></div>
      <div class="track"><i style="width:${d.confidence}%"></i></div></div>
    ${(d.basics||[]).map(r=>summaryRow(r,true)).join('')}
    <div class="card pad"><div class="sumhead"><div class="sumlbl">${T("Сводка Kleal","Kleal's summary")}</div><span class="updated">${esc(fmtUpdated(DATA.summaryUpdated))}</span></div>${sum}
      <button class="kbtn pri" data-act="createintent" style="margin-top:12px">${T('Создать интент','Create intent')}</button></div>
    <div class="stack" style="margin-top:6px">${navRows()}${availRow}${langRow}</div>
  </div>`;
}
// Mascot poses live at /assets/<name>.svg (see ASSETS in this file). The container each one sits in
// already has its own size and round background, so the image fills the box rather than carrying a
// size of its own — that keeps a pose swap from changing any layout.
function masc(pose, extra){ return `<img class="masc fill${extra||''}" src="assets/${pose}.svg" alt="" draggable="false">`; }
function emptyState(title,sub){ return `<div class="empty fade"><div class="eic">${IC.spark}</div>
  <div class="etx">${esc(title)}</div>${sub?`<div class="esub">${esc(sub)}</div>`:''}</div>`; }

function interestSummary(it){
  const kv=(it.kv||[]).map(k=>k[1]).filter(Boolean);
  const base = (it.what&&it.what.length) ? it.what.join(', ') : kv.join(', ');
  return base || (T("Kleal ещё разбирается, что для тебя значит ","Kleal is still learning about your ")+it.name+".");
}
let expInt=null;  // which interest is expanded (V3 inline)
function scr_interests(){
  const d=DATA;
  if(!(d.interests||[]).length) return `<div class="fade">${emptyState(T("Пока нет интересов","No interests yet"),T("Расскажи Kleal, чем увлекаешься — и они появятся здесь.","Tell Kleal what you're into and they'll show up here."))}<button class="bigbtn primary" style="margin-top:8px" data-act="add-interests">${T('Добавить интересы','Add interests')}</button></div>`;
  const exp = expInt!==null ? expInt : ((d.interests[0]||{}).name);
  let rows='';
  for(const it of d.interests){
    const on = it.used!==false;
    rows+=`<div class="card irow2"><div class="irleft" data-open="${esc(it.name)}"><div class="ii2">${IC[it.icon]||IC.spark}</div><div class="inm2">${esc(it.name)}</div></div>
      <div class="sw ${on?'on':''}" data-imatch="${esc(it.name)}"><i></i></div></div>`;
    if(it.name===exp){
      rows+=`<div class="card intexp"><div class="intimg"></div><div class="pad">
        <div class="sumhead"><div class="sumlbl">${T("Сводка Kleal","Kleal's summary")}</div></div>
        <div class="sumtxt">${esc(interestSummary(it))}</div>
        <div class="intedit"><div class="intav"></div>
          <button class="editbtn" data-act="edit-int" data-int="${esc(it.name)}">${IC.wand}<span>${T('Изменить','Edit')}</span></button></div></div></div>`;
    }
  }
  return `<div class="fade"><div class="intsub">${T('Если переключатель включён, Kleal учитывает этот интерес при подборе.','When a toggle is on, Kleal uses that interest for matching.')}</div>
    <div class="stack">${rows}</div>
    <button class="bigbtn primary" style="margin-top:14px" data-act="add-interests">${T('Добавить интересы','Add interests')}</button></div>`;
}
function scr_domain(it){  // expanded detail (Dota 2 / Spanish style key-value)
  return `<div class="fade"><div class="card dcard">
    <div class="dtop"><span class="pill-on">${T('Учитывается при подборе · ВКЛ','Used for matching · ON')}</span>${cbadge(it.conf)}</div>
    ${it.source?`<div class="dsrc">${T('Источник:','Source:')} ${esc(it.source)}</div>`:'<div style="height:6px"></div>'}
    ${(it.what||[]).length?`<div class="seclbl">${T('Что именно','What exactly')}</div><div class="bullets" style="margin-bottom:6px">${it.what.map(w=>`<div class="bullet"><span class="dot"></span>${esc(w)}</div>`).join('')}</div>`:''}
    ${(it.kv||[]).map(k=>`<div class="kv"><span class="k">${esc(k[0])}</span><span class="v">${esc(k[1])}</span></div>`).join('')}
    ${it.expansion?`<div class="expansion">${esc(it.expansion)}</div>`:''}
    <div class="dactions"><button class="txtbtn" data-act="edit-int" data-int="${esc(it.name)}">${T('Изменить','Edit')}</button>
      <button class="txtbtn" data-act="dontuse-int" data-int="${esc(it.name)}">${T('Не использовать','Don’t use')}</button>
      <button class="btn-remove" data-act="remove-int" data-int="${esc(it.name)}">${T('Удалить','Remove')}</button></div></div></div>`;
}
function personalitySummary(s){
  const vibe=(s.vibe||[]).filter(v=>v[1]).map(v=>v[0]);
  const rm={}; (s.rows||[]).forEach(r=>rm[r.title]=r.value);
  const out=[];
  if(vibe.length) out.push(T('Тебя воспринимают как: ','You come across as ')+vibe.slice(0,3).join(', ')+".");
  if(rm['Conversation depth']) out.push(T('Тебе нравится: ','You like ')+rm['Conversation depth'].toLowerCase()+".");
  if(rm['Best first format']) out.push(T('Лучше всего для первой встречи: ','Best first meet: ')+rm['Best first format'].toLowerCase()+".");
  if(rm['Group comfort']) out.push(T('Комфортнее всего: ','Most comfortable ')+rm['Group comfort'].toLowerCase()+".");
  return out.join(' ');
}
// One prose field, one owner. This is the same `summary` the shared user row carries, so the text
// on this screen, the text the sheet edits and the text in the store cannot drift apart.
// Two texts, two owners. `personality` is what the Kleal test writes; «Сводка Kleal» keeps its own
// `summary` and afterwards RE-WEAVES to carry this strand. Merging them (as an earlier pass did) made
// the test silently eat the summary.
function personalityText(){
  const t=String(DATA.personality||'').trim();
  return t || personalitySummary(DATA.social||{rows:[],vibe:[],depth:[]});
}
function setPersonality(text){ DATA.personality=String(text||'').trim(); DATA.personalityUpdated=Date.now(); }
// Every write to the summary goes through here, so no call site can forget the timestamp and leave
// the card claiming «Обновлено сегодня» about a paragraph written last month.
function setSummary(text){ DATA.summary=String(text||'').trim(); DATA.summaryUpdated=Date.now(); }
function fmtUpdated(ts){
  if(!ts) return '';                       // never written -> no label at all, which is the honest state
  const d=Math.floor((Date.now()-ts)/864e5);
  if(d<=0) return T('Обновлено сегодня','Updated today');
  if(d===1) return T('Обновлено вчера','Updated yesterday');
  if(d<7)   return T('Обновлено '+d+' дн. назад','Updated '+d+' days ago');
  const dt=new Date(ts);
  return T('Обновлено '+dt.toLocaleDateString('ru-RU',{day:'numeric',month:'short'}),
           'Updated '+dt.toLocaleDateString('en-GB',{day:'numeric',month:'short'}));
}
// The story saves on blur and on «Сохранить и закрыть»; the dirty check keeps blur→confirm from
// posting the same text twice.
let _storySaved=null;
function saveStory(){
  const el=document.getElementById('storyta'); if(el) DATA.story=el.value;
  DATA.story=String(DATA.story||'').slice(0,4000);
  if(_storySaved===null) _storySaved=DATA.story;
  else if(DATA.story===_storySaved) return false;
  _storySaved=DATA.story;
  pushProfile({story:DATA.story}); saveState(); return true;
}
function scr_social(){  // "Личность" — the entry screen: photo, Kleal's test, the summary, your story
  const txt=personalityText(), up=fmtUpdated(DATA.personalityUpdated);
  return `<div class="fade" style="text-align:center">
    <div class="persimg${DATA.photo?' hasphoto" style="background-image:url('+DATA.photo+')':'"'} data-act="edit-photo">${DATA.photo?'':IC.photo}</div>
    <button class="bigbtn primary" data-act="start-persona">${IC.doc}<span>${T('Пройти тест от Kleal','Take your personality test')}</span></button>
    <div class="card pad" style="text-align:left;margin-top:16px">
      <div class="sumhead"><div class="sumlbl">${T('Твоя личность','Your personality')}</div>
        ${up?`<span class="updated">${esc(up)}</span>`:''}</div>
      <div class="sumtxt clamp3">${esc(txt||T('Пройди тест — и Kleal расскажет, как ты воспринимаешься со стороны и с кем тебе легко.','Take the test and Kleal will describe how you come across and who you click with.'))}</div>
      <div class="intedit">
        <button class="penbtn" data-act="edit-personality" aria-label="${T('Изменить','Edit')}">${IC.edit}</button>
        <button class="bigbtn dark" style="margin-top:0;height:44px;font-size:15px" data-act="edit-personality">${IC.wand}<span>${T('Изменить с Kleal','Edit with Kleal')}</span></button></div>
    </div>
    <div style="text-align:left;margin-top:18px">
      <div class="seccap">${T('Расскажи историю своей жизни в свободном формате (детство, обучение, интересы, профессия)','Tell your life story in your own words — childhood, studies, interests, work')}</div>
      <textarea id="storyta" class="storyta" maxlength="4000" spellcheck="false"
        placeholder="${T('Пиши как получится — Kleal сам разберётся.','Write it however it comes out — Kleal will make sense of it.')}"
        oninput="DATA.story=this.value" onblur="saveStory()">${esc(DATA.story||'')}</textarea>
    </div>
    ${ptestResultCard()}
    <div class="stickycta"><button class="bigbtn primary" data-act="story-confirm">${T('Сохранить и закрыть','Confirm & Close')}</button></div>
  </div>`;
}
// Nothing derived is hidden inside prose: every field the test wrote is named, with whether it
// actually reaches the ranking, and every axis it could NOT derive is named too.
const _AXIS_RU={energy:['Заряд','Energy'],group:['Формат','Group size'],depth:['Глубина общения','Conversation depth'],
  firstMeet:['Первая встреча','First meet'],pace:['Темп сближения','Pace'],planning:['Планы','Planning'],seek:['Что ищешь','Looking for']};
const _TOK_RU={energised:['заряжаешься','energised'],drained:['устаёшь','drained'],one:['один на один','one to one'],
  small:['малая группа','small group'],crowd:['большая компания','big crowd'],deep:['про смыслы','deep'],
  light:['лёгкий','light'],practical:['по делу','practical'],talk:['кофе и разговор','coffee and a talk'],
  doing:['что-то делать вместе','doing something'],event:['событие','an event'],fast:['быстро','fast'],
  slow:['постепенно','slowly'],advance:['заранее','in advance'],spontaneous:['спонтанно','spontaneous'],
  long:['друзья надолго','friends for the long run'],interest:['компания под интерес','company for an interest'],
  wider:['расширить круг','a wider circle'],extrovert:['экстраверт','extrovert'],introvert:['интроверт','introvert'],
  party:['компания 10+','party'],events:['события и митапы','events']};
function tokRU(t){ const h=_TOK_RU[String(t)]; return h?T(h[0],h[1]):String(t); }
function ptestResultCard(){
  const R=PTEST_RESULT; if(!R) return '';
  const axes=R.axes||{}, all=PTEST_Q().filter(q=>!q.free);
  const line=(l,v,note)=>`<div style="display:flex;justify-content:space-between;gap:12px;padding:7px 0">
      <div style="font-size:14.5px;min-width:0">${esc(l)}: <b>${esc(v)}</b></div>
      <div class="k-cap" style="color:var(--muted);flex:none;text-align:right">${esc(note)}</div></div>`;
  const inMatch=(R.applied||[]).map(a=>a[0]==='vibe'
    ? line(T('Вайб','Vibe'), tokRU(a[1]), T('влияет на подбор','affects matching'))
    : line(T('Формат','Format'), tokRU(a[1]), T('сохранено, на подбор пока не влияет','saved, not yet weighed'))).join('');
  const missing=all.filter(q=>!axes[q.k]).map(q=>
    line(T(_AXIS_RU[q.k][0],_AXIS_RU[q.k][1]), T('не участвует','not used'),
         T('нет ответа или «зависит»','no answer, or "it depends"'))).join('');
  const conf=(R.conflicts||[]).map(c=>`<div style="padding:8px 0;border-top:1px solid var(--line)">
      <div style="font-size:14px">${esc(T('В профиле','In your profile'))}: <b>${esc(tokRU(c[1]))}</b> · ${esc(T('в тесте','in the test'))}: <b>${esc(tokRU(c[2]))}</b></div>
      <div class="iacts" style="margin-top:8px">
        <button class="kbtn sec sm" style="flex:1" data-act="ptest-keep" data-f="${esc(c[0])}">${T('Оставить как в профиле','Keep my profile')}</button>
        <button class="kbtn pri sm" style="flex:1" data-act="ptest-take" data-f="${esc(c[0])}">${T('Взять из теста','Take from the test')}</button></div></div>`).join('');
  return `<div class="card pad" style="text-align:left;margin-top:12px">
    <div class="sumlbl">${T('Kleal записал из теста','What Kleal saved from the test')}</div>
    ${inMatch||`<div class="seccap" style="margin:6px 0 0">${T('Из ответов ничего не легло в поля подбора.','Nothing from your answers landed in a matching field.')}</div>`}
    ${missing}
    ${conf}
    <div class="seccap" style="margin:10px 0 0">${T('Пока в подборе участвует только вайб — он двигает твой счёт с людьми похожего склада и делает тебя заметнее. Остальное сохранено в профиле.','Only the vibe is weighed today — it moves your score with similar people and makes you more visible. The rest is stored on your profile.')}</div>
  </div>`;
}

// ---- The Kleal personality test ------------------------------------------------------------------
// A fixed eight-question ladder on the client, then exactly ONE call to /api/buddy/persona. An LLM
// turn per question would give eight chances to hang on a chain with no abort and no visible error,
// for questions a personality test fixes by design anyway.
let PTEST=null;   // {i, answers:[{k,q,a}], busy, failed}
function ptestInit(){ PTEST={i:0, answers:[], busy:false, failed:false}; }
// Each option carries the canonical token it means, ON the question object. Deriving by bare index
// against a separate table is silently corrupting the day someone reorders an option; `null` is an
// honest hedge («зависит», «гибко») and derives nothing at all.
const PTEST_Q = () => [
 {k:'energy', q:T('После насыщенного дня с людьми ты скорее…','After a full day around people you usually feel…'),
  o:[T('Заряжен','Energised'),T('Вымотан','Drained'),T('Зависит от людей','Depends who they were')],
  m:['energised','drained',null]},
 {k:'group',  q:T('Как тебе комфортнее знакомиться?','How do you prefer to meet people?'),
  o:[T('Один на один','One to one'),T('Небольшая группа, 3–5','A small group of 3–5'),T('Большая компания','A big crowd')],
  m:['one','small','crowd']},
 {k:'depth',  q:T('Какой разговор тебе ближе?','What kind of conversation suits you?'),
  o:[T('Глубокий, про смыслы','Deep, about what matters'),T('Лёгкий и весёлый','Light and funny'),T('Практичный, по делу','Practical, to the point')],
  m:['deep','light','practical']},
 {k:'firstMeet', q:T('Идеальная первая встреча — это…','An ideal first meet is…'),
  o:[T('Кофе и разговор','Coffee and a talk'),T('Что-то делать вместе','Doing something together'),T('Событие или мероприятие','An event or a meetup')],
  m:['talk','doing','event']},
 {k:'pace',   q:T('Как ты сходишься с людьми?','How do you warm up to people?'),
  o:[T('Быстро и открыто','Fast and openly'),T('Постепенно, присматриваюсь','Slowly, I watch first'),T('Зависит от человека','Depends on the person')],
  m:['fast','slow',null]},
 {k:'planning',q:T('Планы или спонтанность?','Plans or spontaneity?'),
  o:[T('Договариваться заранее','Agree in advance'),T('Лучше спонтанно','Rather spontaneous'),T('Гибко','Flexible')],
  m:['advance','spontaneous',null]},
 {k:'seek',   q:T('Что тебе сейчас важнее всего в новых знакомствах?','What matters most in new connections right now?'),
  o:[T('Друзья надолго','Friends for the long run'),T('Компания под интерес','Company for a specific interest'),T('Расширить круг','A wider circle')],
  m:['long','interest','wider']},
 {k:'own',    q:T('Что о тебе стоит знать, чтобы понять, с кем тебе легко?','What should Kleal know to understand who you click with?'),
  o:[], m:[], free:true}];
// Load-bearing correspondence, so assert it rather than hope.
PTEST_Q().forEach(q=>{ if((q.m||[]).length!==(q.o||[]).length)
  console.error('PTEST_Q: option/token length mismatch on', q.k); });

// ---- The bridge from the test to the ranking engine ------------------------------------------
// Only what the engine can actually read, and only from a tapped option. A typed or skipped answer
// derives NOTHING: we cannot know which option a sentence meant, and a guess written into a matching
// field is the profile asserting something nobody said.
const PTEST_WRITABLE=['vibe','formats','persona','personality'];   // no gate field is here, ever
const _SIZE_TOKENS=['1:1','small','party','events'];
function ptestDerive(answers){
  const axes={};
  (answers||[]).forEach(a=>{ if(a && a.t) axes[a.k]=a.t; });
  const patch={}, notes=[];
  // Q1 -> vibe. ('introvert','extrovert') is a literal pair in the engine's clash matrix, which is
  // the only vibe semantics it has.
  if(axes.energy==='energised') patch.vibe='extrovert';
  else if(axes.energy==='drained') patch.vibe='introvert';
  // Q2/Q4 -> the SIZE half of formats. Mode tokens (online/offline/hybrid) belong to the profile form
  // and are never touched here.
  const sizes=[];
  if(axes.group==='one') sizes.push('1:1');
  else if(axes.group==='small') sizes.push('small');
  else if(axes.group==='crowd') sizes.push('party');
  if(axes.firstMeet==='event') sizes.push('events');
  if(sizes.length) patch.formats=sizes;
  return {patch, axes, notes};
}
// An explicit form entry is a statement; a test answer is an inference from a proxy question. The
// weaker evidence never overwrites the stronger one, and never silently.
function ptestApply(d){
  const applied=[], conflicts=[], out={};
  const ownedVibe=((DATA.persona||{}).axes||{}).energy;   // did the test write the current vibe?
  if(d.patch.vibe){
    const cur=String(DATA.vibeWord||'').trim();
    if(!cur || ownedVibe) { out.vibe=d.patch.vibe; DATA.vibeWord=d.patch.vibe;
                            applied.push(['vibe', d.patch.vibe]); }
    else conflicts.push(['vibe', cur, d.patch.vibe]);
  }
  if(d.patch.formats){
    const cur=(DATA.formats||[]).slice();
    const handSize=cur.filter(f=>_SIZE_TOKENS.indexOf(f)>=0);
    const ownedSize=((DATA.persona||{}).axes||{}).group;
    if(!handSize.length || ownedSize){
      const keep=cur.filter(f=>_SIZE_TOKENS.indexOf(f)<0);          // mode tokens survive verbatim
      const next=keep.concat(d.patch.formats.filter(f=>keep.indexOf(f)<0));
      out.formats=next; DATA.formats=next;
      d.patch.formats.forEach(f=>applied.push(['formats', f]));
    } else conflicts.push(['formats', handSize.join(', '), d.patch.formats.join(', ')]);
  }
  DATA.persona={v:1, takenAt:Date.now(), axes:d.axes};
  out.persona=DATA.persona;
  // Nothing leaves this function that is not on the writable list.
  Object.keys(out).forEach(k=>{ if(PTEST_WRITABLE.indexOf(k)<0) delete out[k]; });
  return {patch:out, applied, conflicts};
}
function scr_persona(){
  if(!PTEST) ptestInit();
  const Q=PTEST_Q(), q=(PTEST.i<Q.length)?Q[PTEST.i]:null;
  const said=PTEST.answers.map(a=>`<div class="kbub ag">${esc(a.q)}</div>`
    +(a.a?`<div class="kbub me">${esc(a.a)}</div>`:`<div class="kbub me">${T('Пропустить','Skip')}</div>`)).join('');
  return `<div class="kflow fade">${kbar(false)}
    <div class="kcont">
      ${kprompt(T('Тест от Kleal','Kleal’s personality test'))}
      <div class="seccap" style="margin:0 0 4px">${T('Вопрос','Question')} ${Math.min(PTEST.i+1,Q.length)} / ${Q.length}</div>
      ${said}
      ${q?`<div class="kbub ag">${esc(q.q)}</div>
           <div class="kchips" style="margin-top:2px">${q.o.map((o,i)=>
             `<div class="kchip" data-act="ptest-pick" data-v="${esc(o)}" data-i="${i}">${esc(o)}</div>`).join('')
             +(q.free?`<div class="kchip" data-act="ptest-pick" data-v="" data-i="-1">${T('Пропустить','Skip')}</div>`:'')}</div>`:''}
      ${PTEST.busy?`<div class="kbub ag">${T('Kleal пишет о тебе…','Kleal is writing you up…')}</div>`:''}
      ${PTEST.failed?`<div class="kbub ag">${T('Kleal не смог собрать текст — попробуй ещё раз.','Kleal could not write it up — try again.')}</div>
        <div class="kchips" style="margin-top:2px"><div class="kchip" data-act="ptest-retry">${T('Повторить','Retry')}</div></div>`:''}
    </div>
    ${kcomposer('ptestinp',T('Или ответь своими словами…','Or answer in your own words…'))}</div>`;
}
function ptestAnswer(text, idx){
  const Q=PTEST_Q(); if(!PTEST||PTEST.busy||PTEST.i>=Q.length) return;
  const q=Q[PTEST.i], i=(typeof idx==='number')?idx:-1;
  // t is the canonical token, or null when the answer was typed, skipped, or an honest hedge.
  PTEST.answers.push({k:q.k, q:q.q, a:String(text||'').trim(), i:i, t:(i>=0?(q.m||[])[i]:null)||null});
  PTEST.i++;
  if(PTEST.i>=Q.length) ptestFinish(); else render();
}
async function ptestFinish(){
  PTEST.busy=true; PTEST.failed=false; render();
  const el=document.getElementById('storyta'); if(el) DATA.story=el.value;   // typed but never blurred
  let r=null;
  try{ r=await fetch('/api/buddy/persona',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({profile:fullProfileForEdit(), story:String(DATA.story||'').slice(0,4000),
      answers:PTEST.answers.filter(a=>a.a).map(a=>({q:a.q,a:a.a})),
      current:DATA.personality||'', lang:UILANG})}).then(x=>x.json());
  }catch(e){ r=null; }
  PTEST.busy=false;
  // buddy answers 200 with a chat-shaped body when a route throws, and returns an empty paragraph when
  // the model won't write in the right language — so our own key being non-empty is the only honest
  // test. `summary` is read too: the route ships both keys for one release.
  const txt=r&&(r.personality||r.summary);
  if(!txt){ PTEST.failed=true; render(); return; }
  setPersonality(txt);
  // What the eight answers actually mean to the engine, and what they may not touch.
  const res=ptestApply(ptestDerive(PTEST.answers));
  PTEST_RESULT={applied:res.applied, conflicts:res.conflicts, axes:(DATA.persona||{}).axes||{}, at:Date.now()};
  pushProfile(Object.assign({personality:DATA.personality}, res.patch));
  saveState(); PTEST=null; cur='social'; render();
  toast(T('Kleal записал результат теста','Kleal saved your test result'));
  // Only NOW the weave, and only into the summary's own field — never the other way round.
  adaptSummary().then(ok=>{ if(ok) render(); });
}
// The result of the last test run, shown on «Личность» until the user resolves it. Device-local:
// it describes a decision, not profile data.
let PTEST_RESULT=null;
// «Взять из теста» on a conflict row — the only path by which a test answer overrides a hand entry.
function ptestResolve(field){
  if(!PTEST_RESULT) return;
  const c=(PTEST_RESULT.conflicts||[]).find(x=>x[0]===field); if(!c) return;
  const patch={};
  if(field==='vibe'){ DATA.vibeWord=c[2]; patch.vibe=c[2]; }
  else if(field==='formats'){
    const keep=(DATA.formats||[]).filter(f=>_SIZE_TOKENS.indexOf(f)<0);
    const next=keep.concat(String(c[2]).split(', ').filter(Boolean));
    DATA.formats=next; patch.formats=next;
  } else return;
  PTEST_RESULT.conflicts=PTEST_RESULT.conflicts.filter(x=>x[0]!==field);
  PTEST_RESULT.applied.push([field, c[2]]);
  pushProfile(patch); saveState(); render(); toast(T('Взято из теста','Taken from the test'));
}
function ptestKeep(field){
  if(!PTEST_RESULT) return;
  PTEST_RESULT.conflicts=(PTEST_RESULT.conflicts||[]).filter(x=>x[0]!==field);
  saveState(); render();
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
    <div class="card pad" style="margin-bottom:4px"><div class="sumlbl" style="color:var(--coral700)">${T('Всё под твоим контролем','You’re in control')}</div>
      <div class="sumtxt" style="font-size:13.5px;color:var(--muted)">${T('Kleal ничего не делает без твоего согласия. Он показывает район города, а не точное место, узнаёт только то, что ты разрешил, и всё здесь можно откатить в любой момент.','Kleal never acts without your say-so. It shares your city area, never your exact location, learns only what you allow, and everything here is reversible anytime.')}</div></div>
    ${groups}</div>`;
}
function scr_memory(){
  if(!DATA.memory.length) return emptyState(T("Пока нет сигналов","No signals yet"),T("По мере использования Kleal всё, что он узнаёт, появится здесь.","As you use Kleal, everything it learns shows up here."));
  return `<div class="stack fade">${DATA.memory.map((m,i)=>`<div class="card sig">
    <div class="stopline"><div class="ssig">${esc(ruTxt(m.signal))}</div><span class="stbadge st-${m.status}">${esc(ruTxt(m.status))}</span></div>
    <div class="smeta">${T('Источник:','Source:')} ${esc(ruTxt(m.source))}<br>${T('Уверенность:','Confidence:')} ${esc(ruTxt(m.confidence))} · ${T('Используется для подбора:','Used for matching:')} ${m.used===false?T('Нет','No'):T('Да','Yes')}<br>${T('Обновлено:','Last updated:')} ${esc(ruTxt(m.updated))}</div>
    <div class="dactions" style="margin-top:12px"><button class="txtbtn" data-act="edit-sig" data-sig="${i}">${T('Изменить','Edit')}</button>
      <button class="txtbtn" data-act="dontuse-sig" data-sig="${i}">${m.used===false?T('Использовать снова','Use again'):T('Не использовать','Don’t use')}</button>
      <button class="txtbtn" style="color:var(--danger)" data-act="remove-sig" data-sig="${i}">${T('Удалить','Remove')}</button></div>
    </div>`).join('')}</div>`;
}
function scr_knows(){
  const k=DATA.knows||{};
  // Counters are DERIVED from the lists rendered right below, never stored, so the headline
  // number is always exactly what the user can scroll through and count.
  const cList=k.confirmedList||[], iList=k.inferredList||[], tList=k.temporaryList||[];
  const nConf=cList.length, nInf=iList.length, nTmp=tList.length, nTotal=nConf+nInf+nTmp;
  if(!(k.confirmedList||[]).length && !(k.inferredList||[]).length) return emptyState(T("Пока ничего не отслеживается","Nothing tracked yet"),T("Kleal собирает эту сводку по мере знакомства.","Kleal builds this summary as it gets to know you."));
  // An empty section header over an empty card reads as "we have nothing on you here" noise —
  // render a section only when it actually has rows.
  const sect=(title,list,on,pfx)=>!list.length?'':`<div class="rowhead"><div class="h2">${title}</div></div>
    <div class="card">${list.map((x,i)=>checkRow(ruTxt(x),on,pfx+i)+(i<list.length-1?'<div class="divider"></div>':'')).join('')}</div>`;
  return `<div class="fade"><div class="card">
      <div class="statbig"><span class="n">${nTotal}</span><span class="l">${T('сигналов отслеживается','signals tracked')}</span></div>
      <div style="display:flex">${[[nConf,T('подтверждённые','confirmed')],[nInf,T('предполагаемые','inferred')],[nTmp,T('временные','temporary')]]
        .map(t=>`<div class="stat" style="flex:1"><div class="n">${t[0]}</div><div class="l">${t[1]}</div></div>`).join('')}</div>
    </div>
    ${sect(T('Подтверждённые','Confirmed'), cList, true, 'k-c-')}
    ${sect(T('Предполагаемые','Inferred'), iList, false, 'k-i-')}</div>`;
}
// ================= V4: intents · intent chat · discovery · messages =================
let curIntent=null;
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
    body:JSON.stringify({query:curIntent.query,profile:matchProfile(),override:ov})}).then(x=>x.json()); }catch(e){ r=null; }
  if(r&&r.candidates&&r.candidates.length){ curIntent.candidates=r.candidates; curIntent.fallback=null;
    curIntent.intent=r.intent; curIntent.confidence=r.candidates[0].score; toast(r.candidates.length+' matches after broadening'); }
  else { curIntent.fallback=(r&&r.fallback)||curIntent.fallback; toast('Still no offline matches — try going live'); }
  render(); saveState();
}
// ===== Conversational "Create intent": Kleal collects the essentials + validates, THEN builds the card =====
// Replaces the old "any text -> instant card" behaviour: /api/buddy/intent-build runs a short dialogue
// (gibberish -> ask again; missing when/format -> ask; enough -> ready) and only then do we build a card.
function saveCurIntent(){
  if(!curIntent) return;
  DATA.intents=DATA.intents||[];
  const cs=curIntent.candidates||[], ag=cs.filter(c=>c.agree).length;
  const key=(x)=>String((x&&x.query)||'').trim().toLowerCase();
  const tkey=(x)=>String((x&&x.title)||'').trim().toLowerCase();
  // re-launching the same request must UPDATE its intent, not stack another identical card
  const same=DATA.intents.find(x=>x!==curIntent && (
      (x.id&&x.id===curIntent.id) ||
      (key(x)&&key(x)===key(curIntent)) ||
      (tkey(x)&&tkey(x)===tkey(curIntent))));
  if(same){
    Object.assign(same,{candidates:cs, tags:curIntent.tags||same.tags, intent:curIntent.intent||same.intent,
      status:cs.length?(ag?'matched':'searching'):'searching', confidence:undefined});
    curIntent=same; saveState(); return;
  }
  if(!curIntent.id){
    curIntent.id='i'+String(Date.now()); curIntent.createdAt=Date.now();
    DATA.intents.unshift(curIntent);
    addNotif('intent','“'+curIntent.title+'”',
      cs.length? (cs.length+' '+plural(cs.length,T('кандидат','match'),T('кандидата','matches'),T('кандидатов','matches'))
                  + (ag?(' · '+ag+' '+T('согласны','agreed')):''))
               : T('пока никого — можно расширить поиск','no one yet — try widening the search'), curIntent.id);
  }
  curIntent.status=cs.length?(ag?'matched':'searching'):'searching';
  delete curIntent.confidence;                 // percentages are not shown anywhere (spec §9.7)
  saveState();
}
// ---------- Phase 4: notifications ----------
function addNotif(kind,title,body,ref){
  if(((DATA.prefs||{}).notifs)===false) return;   // the Settings switch really gates this
  DATA.notifs=DATA.notifs||[];
  DATA.notifs.unshift({id:'n'+String(Date.now())+Math.round(Math.abs(Math.sin(DATA.notifs.length))*1000),kind:kind,title:title,body:body,ref:ref,read:false,time:'now'}); }
function unreadNotifs(){ return (DATA.notifs||[]).filter(n=>!n.read).length; }
function scr_notifications(){
  const list=DATA.notifs||[];
  if(!list.length) return emptyState(T("Пока нет уведомлений","No notifications yet"),T("Когда Kleal найдёт людей или агенты договорятся — появится здесь.","When Kleal finds people or agents agree, it shows up here."));
  return `<div class="stack fade" style="padding-top:4px">${list.map(n=>`<div class="card notifrow ${n.read?'':'unread'}" data-notif="${n.id}">
    <div class="nnic">${n.kind==='match'?IC.users:IC.spark}</div>
    <div class="nnt"><div class="nntt">${esc(n.title)}</div><div class="nnts">${esc(n.body)}</div></div>
    <div class="nntime">${esc(n.time==='now'?T('сейчас','now'):locStr(n.time))}</div></div>`).join('')}</div>`;
}
function openNotif(id){ const n=(DATA.notifs||[]).find(x=>x.id===id); if(!n)return; n.read=true;
  if(n.kind==='match' && matchWith){ cur='matchchat'; render(); saveState(); return; }
  if(n.ref){ openIntentFlow(n.ref); saveState(); return; }
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
  // /api/agent/intro returns "an icebreaker opener B COULD send A" — a DRAFT, generated by the model.
  // It used to be pushed in as {who:'them'}, so the app showed it under the other person's name with a
  // "now" timestamp: the user believed a real person had written to them and could sit waiting for a
  // reply to a message nobody sent. It is now offered as a suggested first line for the USER to send,
  // which is what it actually is, and the thread starts genuinely empty.
  const opener=(r&&r.opener)||'';
  t.msgs=[]; t.loading=false; t.suggest=opener;
  t.last=T('Интро сделано — напиши первым','Intro made — say hi first'); t.time='now';
  postFeedback(cand.name,'accepted');   // feedback loop: approving an intro teaches the ranker
  addNotif('match',T('Взаимный интерес: ','You matched with ')+cand.name,
           T('Их агент согласился — можно написать','Their agent agreed — say hi'), null);
  render(); saveState();
}
function openMsgThread(i){
  const t=(DATA.messages||[])[i]; if(!t) return;
  if(t.kleal){ flowStart(''); return; }          // the pinned Kleal thread -> the one chat screen
  matchWith=t; matchWith.fromMessages=true; cur='matchchat'; render(); saveState();
}
// ---- Kleal's help: it drafts YOUR next message, in your voice, from your profile and the thread ----
// It never sends. The screen already promises «я пишу только после твоего одобрения», and the
// recipient is a real person — so the draft lands in the composer and you decide.
let GHOSTBUSY=false;
async function klealHelp(){
  if(GHOSTBUSY||!matchWith) return;
  GHOSTBUSY=true; render();
  let r=null;
  try{
    r=await fetch('/api/buddy/ghostwrite',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({profile:matchProfile(), candidate:matchWith.cand||{name:matchWith.who||''},
        messages:(matchWith.msgs||[]).map(m=>({who:m.who,text:m.text})), lang:UILANG})}).then(x=>x.json());
  }catch(e){ r=null; }
  GHOSTBUSY=false; render();
  const d=(r&&r.draft||'').trim();
  if(!d){ toast(T('Не получилось составить — попробуй ещё раз','Could not draft that — try again')); return; }
  const el=document.getElementById('mcin');
  if(el){ el.value=d; el.focus(); try{ el.setSelectionRange(d.length,d.length); }catch(_e){} }
}
// ---- real message delivery (the chat used to be local-only) ----
async function sendMsg(thread, text){
  const to=(thread.cand&&thread.cand.name)||thread.who||'';
  const me=(DATA.name||'').trim();
  if(!to||!me){ thread.failed=true; render(); return; }
  let r=null;
  try{
    r=await fetch('/api/agent/message',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({from:me, to:to, text:text})}).then(x=>x.json());
  }catch(e){ r=null; }
  // Do not claim delivery that did not happen — the bubble is marked and the user can retry.
  if(!r||!r.ok){ thread.failed=true; toast(T('Не удалось отправить — попробуй ещё раз','Could not send — try again')); }
  else { thread.failed=false; thread.since=Math.max(thread.since||0, r.t||0); }
  render(); saveState();
}
// Poll the open conversation for what the other person actually wrote.
let _msgT=null, _msgBusy=false;
// The old version returned early WITHOUT clearing _msgT whenever the chat was not on screen, so the
// `if(!_msgT)` starter could never fire again — after leaving a chat once, nothing polled until the
// page was reloaded. That is why messages only appeared after a refresh.
async function pollThread(){
  clearTimeout(_msgT); _msgT=null;
  if(_msgBusy) return;               // guard before the await; see the duplicate-append fix
  const th=matchWith, me=(DATA.name||'').trim();
  if(!th||cur!=='matchchat'||!me){ return; }
  _msgBusy=true;
  const other=(th.cand&&th.cand.name)||th.who||'';
  if(other){
    try{
      const r=await fetch('/api/agent/thread?self='+encodeURIComponent(me)+'&with='+encodeURIComponent(other)
                          +'&since='+encodeURIComponent(th.since||0)).then(x=>x.json());
      const have=new Set((th.msgs||[]).map(x=>x.mid).filter(Boolean));
      const incoming=(r&&r.messages||[]).filter(m=>String(m.from).toLowerCase()!==me.toLowerCase()
                                                   && !have.has(m.id));
      if(incoming.length){
        incoming.forEach(m=>{ th.msgs.push({who:'them',mid:m.id,text:m.text,t:(m.t||0)*1000}); th.last=m.text; th.time='now'; });
        th.awaiting=false;
        th.since=Math.max(th.since||0, ...(r.messages||[]).map(m=>m.t||0));
        render(); saveState();
      } else if(r&&r.messages&&r.messages.length){
        th.since=Math.max(th.since||0, ...r.messages.map(m=>m.t||0));
      }
    }catch(e){}
  }
  _msgBusy=false;
  _msgT=setTimeout(pollThread, 2000);   // an open conversation should feel live
}
function scr_matchchat(){
  const m=matchWith; if(!m) return scr_agenthome();
  // A thread rehydrated from localStorage can have lost `cand` (it is re-attached by msgThreadFor on
  // the live path only), and reading m.cand.name then threw, taking the whole Messages tab down.
  if(!m.cand) m.cand={name:m.who||T('Собеседник','Someone')};
  m.msgs=m.msgs||[];
  const mine=m.msgs.filter(x=>x.who==='me').length; const blur=Math.max(0, 9-mine*3);
  const hd=chatHead(m.cand.name||m.who||'', {back:'chat-back', sub:(m.cand.band?bandLabel(m.cand,true):null)});
  const thread=m.msgs.map(x=>x.who==='me'?`<div class="mrow"><div class="mbub">${esc(x.text)}</div></div>`
    :`<div class="krow"><div class="kav" style="filter:blur(${Math.min(blur,4)}px)"></div><div class="kcol"><div class="kbub">${m.loading&&x.text==='…'?'<span class="typing3"><i></i><i></i><i></i></span>':esc(x.text)}</div></div></div>`).join('');
  const hint=blur>0?`<div class="candbusy" style="text-align:center;padding:2px 0 6px">${T('Фото проявится по мере общения','The photo unblurs as you talk')}</div>`:'';
  // A suggested opener is Kleal's draft FOR THE USER — labelled as such, and tapping it fills the input
  // rather than sending anything on its own.
  const sugg=(!m.msgs.length&&m.suggest)?`<div style="padding:8px 2px">
      <div class="k-cap" style="color:var(--muted);margin-bottom:6px">${T('Kleal предлагает начать так','Kleal suggests opening with')}</div>
      <div class="ksugg" data-act="use-suggest">${esc(m.suggest)}</div></div>`:'';
  const nostart=(!m.msgs.length)?`<div class="k-cap" style="color:var(--muted);text-align:center;padding:6px 0">${T('Переписка ещё не началась.','No messages yet.')}</div>`:'';
  const wait=m.awaiting?`<div class="k-cap" style="color:var(--muted);text-align:center;padding:6px 0">${T('Отправлено. Ждём ответа — сообщим, когда он придёт.','Sent. Waiting for their reply — we’ll let you know.')}</div>`:'';
  return `<div class="bchat fade">${hd}<div class="bthread" id="bthread">${hint}${nostart}${thread}${sugg}${wait}</div>
    <div class="khelp">
      <div class="kchip soft ${GHOSTBUSY?'busy':''}" data-act="kleal-help">${IC.spark}
        ${GHOSTBUSY?T('Kleal пишет…','Kleal is writing…'):T('Kleal, подскажи ответ','Kleal, draft a reply')}</div>
    </div>
    <div class="bc2"><button class="bc2-plus" data-act="buddy-plus">+</button>
      <div class="bc2-field"><input id="mcin" placeholder="${T('Сообщение для','Message')} ${esc(m.cand.name)}…"><button class="bc2-mic" data-act="buddy-mic">${IC.mic}</button></div>
      <button class="bc2-send" data-act="match-send">${IC.send}</button></div></div>`;
}

// ================= BUDDY AGENT — the conversational agent you just talk to =================
// You chat freely; the buddy quietly gathers your SIGNALS and, when you want to meet someone,
// it calls the matching agent (server-side, agent-to-agent) and drops the best match into the chat.
// Profile of the SEARCHER as the matching engine reads it. Sending only {name} meant the engine
// knew nothing about the person searching: vibe/geo/language groups came back `unknown`, coverage
// stayed low, and the outreach thresholds could never be met — every launch ended in "согласны: 0"
// no matter how good the candidates were.
// ---- the users.json row is the single source of truth for the shared profile ----
// Edits used to live only in this device's localStorage while matching ranked everyone by the row
// onboarding wrote once — two profiles that could only drift apart. Boot pulls the row; every
// accepted edit pushes back through the onboarding service, the store's only writer.
async function loadServerProfile(){
  const me=(DATA.name||'').trim(); if(!me||IS_DEMO) return;
  try{
    const r=await fetch('/api/onboarding/profile',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:me})}).then(x=>x.json());
    const u=r&&r.user; if(!u) return;
    if(u.area!=null&&u.area!=='') DATA.area=u.area;
    if(u.radiusKm!=null) DATA.radiusKm=u.radiusKm;
    if(u.lat!=null&&u.lon!=null) DATA.geo={coarseLat:u.lat,coarseLon:u.lon};
    if(Array.isArray(u.langs)&&u.langs.length) DATA.langsList=u.langs;
    if(u.age!=null) DATA.age=u.age;
    if(u.gender) DATA.gender=u.gender;
    if(Array.isArray(u.formats)) DATA.formats=u.formats;
    if(typeof u.story==='string') DATA.story=u.story;
    if(typeof u.personality==='string') DATA.personality=u.personality;
    if(u.persona&&typeof u.persona==='object') DATA.persona=u.persona;
    // DATA.vibeWord was read by matchProfile but never assigned anywhere — so the searcher's vibe
    // token was a whole SENTENCE from the first social row. The store holds the real one.
    if(typeof u.vibe==='string') DATA.vibeWord=u.vibe;
    if(Array.isArray(u.goals)&&u.goals.length&&!((DATA.goals||{}).active||[]).length)
      DATA.goals={active:u.goals.slice(),optional:[]};
    syncBasicsRows(); render(); saveState();
  }catch(e){}
}
function pushProfile(patch){
  const me=(DATA.name||'').trim(); if(!me||IS_DEMO) return;
  fetch('/api/onboarding/profile-update',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:me,patch})}).catch(()=>{});
}
const _LANG_NAMES={en:['Английский','English'],es:['Испанский','Spanish'],ru:['Русский','Russian'],
  fr:['Французский','French'],de:['Немецкий','German'],it:['Итальянский','Italian'],
  ca:['Каталанский','Catalan'],pt:['Португальский','Portuguese'],uk:['Украинский','Ukrainian'],
  pl:['Польский','Polish'],sr:['Сербский','Serbian'],sv:['Шведский','Swedish']};
function langName(c){ const h=_LANG_NAMES[String(c||'').toLowerCase()]; return h?T(h[0],h[1]):String(c); }
// Display rows mirror the canonical fields, so a card can never show one value while matching
// quietly uses another.
function syncBasicsRows(){
  const rows=DATA.basics||(DATA.basics=[]);
  const put=(title,icon,value)=>{ if(!value) return; const r=rows.find(x=>x.title===title);
    if(r) r.value=value; else rows.push({icon,title,value}); };
  // «Формат встреч» is gone from the profile. DATA.formats itself stays — it is a real field in the
  // shared store, written by onboarding and by the personality test, and read on the candidate side.
  // Only the row and its editor go. Removing it from rows already persisted matters: `put` never
  // deleted anything, so a saved profile would have kept the row forever.
  const _i=rows.findIndex(x=>String(x.title)==='Social formats'); if(_i>=0) rows.splice(_i,1);
  put('Basics','person',[DATA.gender,DATA.age].filter(Boolean).join(' · '));
  put('Location','pin',[DATA.area, DATA.radiusKm?T('до '+DATA.radiusKm+' км','up to '+DATA.radiusKm+' km'):null].filter(Boolean).join(' · '));
  put('Languages','globe',(DATA.langsList||[]).map(langName).join(' · '));
  // DATA.snapshot is a SECOND copy of the same facts, written once when the profile was built from
  // onboarding and never updated after. It is what fullProfileForEdit() hands to the model that
  // writes «Сводка Kleal» — so changing your city updated the card, the store and matching, while
  // the summary went on describing the city you signed up in. Keep both sets in step here, in the
  // one function every accepted edit already calls.
  if(DATA.area) setSnap('Location','pin',[DATA.area, DATA.radiusKm?('Max travel '+DATA.radiusKm+' km'):null].filter(Boolean).join(' · '));
  if((DATA.langsList||[]).length) setSnap('Languages','globe',DATA.langsList.map(langName).join(' · '));
  if(DATA.age||DATA.gender) setSnap('Basics','person',[DATA.gender,DATA.age].filter(Boolean).join(' · '));
  const ORD=['Basics','Location','Languages'];
  rows.sort((a,b)=>{const x=ORD.indexOf(a.title),y=ORD.indexOf(b.title);return (x<0?9:x)-(y<0?9:y);});
}
// Languages, when all we have is the DISPLAY row («Russian native · English fluent · Spanish B1
// practice»). Two bugs lived in the old one-liner, and both sent the matcher words that are not
// languages or codes that are not real:
//   1. every word became a language, so «native», «fluent», «B1», «practice» were shipped as
//      na / fl / b / pr — four of seven "languages" on that profile were proficiency labels;
//   2. an unknown word fell back to its first two letters, which is wrong far more often than it
//      is right: Portuguese -> "po" (candidates store "pt"), German -> "ge" (de), Serbian -> "se"
//      (sr). Onboarding offers Portuguese, so that one was reachable by picking it from the menu.
// A word is now a language only if it IS one. Anything unrecognised is dropped rather than
// guessed — an invented code matches nobody and cannot be told apart from a real preference.
const LANG_CODES={english:'en',английский:'en',spanish:'es',испанский:'es','español':'es',
  russian:'ru',русский:'ru',french:'fr',французский:'fr','français':'fr',
  german:'de',немецкий:'de',deutsch:'de',italian:'it',итальянский:'it',italiano:'it',
  portuguese:'pt',португальский:'pt','português':'pt',catalan:'ca',каталанский:'ca','català':'ca',
  serbian:'sr',сербский:'sr',srpski:'sr',dutch:'nl',нидерландский:'nl',голландский:'nl',
  polish:'pl',польский:'pl',ukrainian:'uk',украинский:'uk',turkish:'tr',турецкий:'tr',
  arabic:'ar',арабский:'ar',chinese:'zh',китайский:'zh',japanese:'ja',японский:'ja',
  hebrew:'he',иврит:'he',greek:'el',греческий:'el',czech:'cs',чешский:'cs',
  swedish:'sv',шведский:'sv',norwegian:'no',норвежский:'no',danish:'da',датский:'da',
  finnish:'fi',финский:'fi',hungarian:'hu',венгерский:'hu',romanian:'ro',румынский:'ro',
  bulgarian:'bg',болгарский:'bg',hindi:'hi',хинди:'hi',korean:'ko',корейский:'ko'};
const LANG_OK=new Set(Object.keys(LANG_CODES).map(k=>LANG_CODES[k]));
function langCode(w){
  const s=String(w||'').toLowerCase();
  if(LANG_CODES[s]) return LANG_CODES[s];
  if(s.length===2&&LANG_OK.has(s)) return s;      // already a canonical code
  return '';                                       // proficiency word, level, anything else
}
function parseLangRow(txt){
  let words; try{ words=String(txt||'').split(/[^\p{L}]+/u); }
  catch(e){ words=String(txt||'').match(/[A-Za-zÀ-ÿА-Яа-яЁё]+/g)||[]; }
  return words.map(langCode).filter((v,i,a)=>v&&a.indexOf(v)===i);
}
function matchProfile(){
  const g=t=>{const r=snapRow(t);return r?String(r.value||''):'';};
  const langs=(DATA.langsList&&DATA.langsList.length)?DATA.langsList.slice()
    :parseLangRow(g('Languages'));
  // city used to be the RAW snapshot row — «Barcelona · Eixample · Gràcia · Max travel 25 min» went
  // to the matcher as a "city". Canonical DATA.area wins; the first display segment is the fallback.
  const p={ name:DATA.name||'',
            interests:(DATA.interests||[]).map(i=>i.name).filter(Boolean),
            langs:langs, languages:{comfortable:langs},
            // A vibe is a TOKEN the engine compares by equality ('introvert' vs 'extrovert'). The old
            // fallback sent the first social row's sentence, which matched nobody and silently parked
            // social_context on its flat neutral branch. No token -> null -> honestly unknown.
            vibe:(DATA.vibeWord||'')||null,
            city:(DATA.area||String(g('Location')).split('·')[0].trim())||null };
  if(DATA.age!=null) p.age=DATA.age;
  if(DATA.gender) p.gender=DATA.gender;
  if(DATA.radiusKm!=null) p.radiusKm=DATA.radiusKm;
  if(DATA.geo&&DATA.geo.coarseLat!=null) p.geo=DATA.geo;
  return p;
}
function buddyProfile(){   // seed the buddy with what we already know about the user
  return { name:DATA.name||'', interests:(DATA.interests||[]).map(i=>({name:i.name})),
           city:((DATA.subtitle||'').split('·')[0]||'').trim()||null };
}
function fmtTime(t){ const d=t?new Date(t):new Date(); let h=d.getHours(),m=d.getMinutes(); const mm=(m<10?'0':'')+m;
  if(UILANG==='ru') return h+':'+mm;                    // 24-hour clock, as Russian expects (no AM/PM)
  const ap=h<12?'AM':'PM'; h=h%12||12; return h+':'+mm+' '+ap; }
// Matching Core v2: качественный уровень вместо числового процента (спека §9.7). Фолбэк на score
// оставлен для legacy-ответов без band.
function bandLabel(c,full){ if(!c) return '';
  const M={especially_close:[T('Очень близко','Very close'),T('Особенно близко к вашему запросу','Especially close to your request')],
           strong_option:[T('Хороший вариант','Good option'),T('Хороший вариант','A good option')],
           broader_option:[T('Шире запроса','Broader'),T('Более широкий вариант','A broader option')],
           needs_clarification:[T('Уточнить','Clarify'),T('Нужно уточнение','Needs clarification')]};
  if(c.band&&M[c.band]) return M[c.band][full?1:0];
  // No band means the legacy v1 scorer answered (KLEAL_CORE_V2=0 rollback). Show nothing rather than a
  // percentage: spec §9.7 bans user-facing percentages outright, and the v1 score is a different scale
  // that cannot be honestly relabelled as a band.
  return ''; }
// Unified chat header so you always know WHERE you are: Back (left) · centered title (+ optional subtitle) ·
// optional action pills (right). Every chat screen uses this — consistent look, consistent back button.
function chatHead(title, opts){ opts=opts||{};
  const acts=(opts.actions||[]).map(a=>`<button class="chd-pill" data-act="${a.act}">${a.icon||''}${a.label?'<span>'+a.label+'</span>':''}</button>`).join('');
  const sub=opts.sub?`<span class="chd-sub">${esc(opts.sub)}</span>`:'';
  return `<div class="chd"><button class="chd-back" data-act="${opts.back||'chat-back'}">${IC.back}<span>${esc(opts.backLabel||'Назад')}</span></button>
    <div class="chd-ttl">${esc(title||'')}${sub}</div>
    <div class="chd-pills">${acts}</div></div>`;
}
// generic chat back: return to a sensible place per screen
function chatBack(){
  if(cur==='matchchat'){ cur=(matchWith&&matchWith.fromMessages)?'messages':'intents'; }
  else { cur='agenthome'; }
  render();
}
// Smooth transition from the home screen into the buddy chat: the side blocks (quick actions, plan, greeting)
// fade + slide away first, THEN the chat opens — so it feels like the page transforms, not a hard jump.
// The + in the buddy header and the «Собрать интент» chip both land here: the flow starts from what
// was ALREADY said, instead of the blank canned greeting openCreateIntent used to show.

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

// ===== "Edit with Kleal": change the profile by talking to the editor agent (/api/buddy/profile-edit) =====
// The editor returns a semantic PATCH ([{op,field,value,label}]); we show a confirmation, and only on
// "Применить" apply it to DATA here (the frontend owns the profile). Fields map 1:1 to applyProfilePatch.
// section -> a focused opening line, so the Edit buttons on the profile sections land the editor in context
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
  // Canonical fields first, the snapshot only as a fallback: the snapshot is a copy and a copy can lag.
  const loc=[DATA.area, DATA.radiusKm?('Max travel '+DATA.radiusKm+' km'):null].filter(Boolean).join(' · ');
  const lng=(DATA.langsList||[]).map(langName).join(' · ');
  return { name:DATA.name||'', location:loc||g('Location'), languages:lng||g('Languages'),
    formats:g('Social formats'), availability:g('Availability'), safety:g('Safety'),
    interests:(DATA.interests||[]).map(i=>i.name), goals:((DATA.goals||{}).active)||[],
    vibe:((DATA.social||{}).rows||[]).map(r=>r.title+': '+r.value).join(' · '), summary:DATA.summary||'',
    personality:DATA.personality||'', story:String(DATA.story||'').slice(0,2500) }; }
// After any profile change, ask Kleal to rewrite the summary paragraph so it reflects the new data
// naturally — instead of a word being tacked onto the end.
let _resumBusy=false;
async function adaptSummary(){
  if(_resumBusy) return false; _resumBusy=true;
  let ok=false;
  try{ const r=await fetch('/api/buddy/resummary',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({profile:fullProfileForEdit(), current:DATA.summary||'',
                         personality:DATA.personality||'', lang:UILANG})}).then(x=>x.json());
    const woven=r&&r.summary, norm=x=>String(x||'').toLowerCase().replace(/\s+/g,' ').trim();
    // Guard the thing this whole change exists to prevent: a "weave" that is really a replacement.
    // If the model just handed back the personality text, or lost half the summary, keep the old one —
    // «сводка ещё не догнала» is recoverable, «тест съел сводку» is not.
    if(woven && norm(woven)!==norm(DATA.personality)
             && !(DATA.summary && woven.length < DATA.summary.length*0.5)){
      setSummary(woven); saveState(); pushProfile({summary:DATA.summary}); ok=true;
    }
  }catch(e){}
  _resumBusy=false; return ok;
}

// ---------- Phase 3: public intents on the Explore map ----------
const ME_LATLON=[41.3874, 2.1686];   // Barcelona (demo user's coarse area)
// Explore plans are REAL — pulled from the matching pool (/api/agent/explore), not hard-coded here.
let PUBLIC_INTENTS=[], exploreLoaded=false, exploreLoading=false;
async function loadExplore(){
  if(exploreLoading) return; exploreLoading=true;
  // The map wants a populated world; the old default of 12 rows left it almost empty.
  const me=encodeURIComponent(DATA.name||'');
  let r,gr; try{ [r,gr]=await Promise.all([
    fetch('/api/agent/explore?limit=300&self='+me).then(x=>x.json()),
    fetch('/api/agent/groups?limit=60&self='+me).then(x=>x.json())]); }catch(e){ r=null; gr=null; }
  exploreLoading=false; exploreLoaded=true;
  // Real groups are plans you can actually join, so they lead — a synthesized "X likes football"
  // row is only an invitation to write to one person.
  GROUPS=(gr&&gr.groups)||[];
  PUBLIC_INTENTS=GROUPS.map(g=>({gid:g.gid, title:g.title, who:g.host, topics:g.topics||[],
      when:g.when||'', area:g.area||'', lat:g.lat, lon:g.lon, size:g.size, max_size:g.max_size,
      state:g.state, mine:g.mine, hosting:g.hosting, waiting:g.waiting, version:g.version}))
    .concat((r&&r.plans)||[]);
  PUBLIC_INTENTS.forEach((p,i)=>{ p._i=i; });     // stable id; indexOf per pin was O(n^2) over 2000 rows
  // Agent Home's "For you today" shows the same REAL plans (the seed carries none)
  DATA.plans=PUBLIC_INTENTS.map(p=>({title:p.title||p.who||'', who:p.who||'',
    when:p.when||'', area:p.area||'', topics:p.topics||[],
    dist:(p.km!=null?(p.km+' '+T('км','km')):''), going:p.going||p.participants||0}));
  if(cur==='search'){ xSyncList(); if(exploreMap) drawExploreMarkers(); else render(); }
  else if(cur==='agenthome') render();
}
// Explore rows: prefer the person's stated area over a distance figure. The stored km is measured to a
// fixed origin, so for someone in another city it reads as a few kilometres away — showing «Москва»
// tells the truth where «2.6 км» does not.
// The user's own area lives in different places depending on how the profile was built (onboarding
// hand-off, demo seed, or an edited state restored from localStorage), so check all of them before
// giving up — an empty answer here silently disables the cross-area check below.
function myArea(){
  if(DATA.area) return String(DATA.area).trim();     // canonical beats the snapshot copy
  const r=snapRow('Location'); if(r&&r.value) return String(r.value).trim();
  const b=(DATA.basics||[]).find(x=>String(x.title).toLowerCase()==='location');
  if(b&&b.value) return String(b.value).trim();
  // NOT DATA.places — that list holds privacy settings ("Area only, never exact location"), not a place.
  const sub=String(DATA.subtitle||'').split('·')[0].trim();
  // 'New profile' / 'Новый профиль' is mapOnboarding's placeholder for "no location yet". Returning it
  // as an area made every comparison mismatch and silently hid every distance.
  return /^(new profile|новый профиль)$/i.test(sub) ? '' : sub;
}
function sameArea(a,b){
  a=String(a||'').toLowerCase().trim(); b=String(b||'').toLowerCase().trim();
  if(!a||!b) return null;                       // unknown on either side -> can't say
  return a===b || a.includes(b) || b.includes(a);
}
function planWhere(p){
  const a=(p&&p.area||'').trim();
  const same=sameArea(a, myArea());
  // Only show a distance when it can mean something. The stored km is measured to a FIXED origin, so
  // for someone in another city it renders as «Москва · 2.6 км» — a contradiction on one line. When the
  // areas differ we show the area alone; the honest statement is "they're in Moscow", not a number.
  const d=(p&&p.dist!=null&&same!==false)?(p.dist+' '+T('км','km')):'';
  return a && d ? (a+' · '+d) : (a || d || T('место не указано','area not set'));
}
let AREAFILTER=null;
function focusArea(key){ AREAFILTER=(AREAFILTER===key)?null:key; cur='search'; render(); }
// ---- area map: plot CITIES we can name, never people we cannot locate ----
// Not one real user in the store has coordinates — onboarding collects a free-text area and nothing
// else. The old map invented a position per person (a golden-angle spiral around the centre), which
// put pins in the sea and drew people whose area says «Москва» a few km from Barcelona. Removing that
// left an empty map. What we genuinely know is the CITY and how many plans are in it, so that is what
// the map shows: one marker per city, carrying a count. A city marker claims a fact; a person pin
// would claim a location we were never given.
const CITY_LATLON={
  'barcelona':[41.3874,2.1686], 'madrid':[40.4168,-3.7038], 'valencia':[39.4699,-0.3763],
  'moscow':[55.7558,37.6173], 'saint petersburg':[59.9311,30.3609],
  'belgrade':[44.7866,20.4489], 'lisbon':[38.7223,-9.1393], 'berlin':[52.52,13.405],
  'london':[51.5074,-0.1278], 'paris':[48.8566,2.3522], 'amsterdam':[52.3676,4.9041],
  'tbilisi':[41.7151,44.8271], 'yerevan':[40.1792,44.4991], 'istanbul':[41.0082,28.9784],
  'warsaw':[52.2297,21.0122], 'prague':[50.0755,14.4378], 'kyiv':[50.4501,30.5234],
  'dubai':[25.2048,55.2708], 'new york':[40.7128,-74.006], 'tel aviv':[32.0853,34.7818],
};
// Areas arrive as free text — "bARCELONE", "Москва", "  Barcelona ". Fold spelling and language so a
// city is one marker, not three.
const CITY_ALIAS={
  'москва':'moscow','мск':'moscow','moskva':'moscow',
  'санкт-петербург':'saint petersburg','спб':'saint petersburg','питер':'saint petersburg',
  'барселона':'barcelona','barcelone':'barcelona','bcn':'barcelona',
  'белград':'belgrade','мадрид':'madrid','лиссабон':'lisbon','берлин':'berlin',
  'лондон':'london','париж':'paris','тбилиси':'tbilisi','ереван':'yerevan',
  'стамбул':'istanbul','варшава':'warsaw','прага':'prague','киев':'kyiv','київ':'kyiv',
  'дубай':'dubai','амстердам':'amsterdam','тель-авив':'tel aviv','валенсия':'valencia',
};
function cityKey(area){
  let a=String(area||'').toLowerCase().trim().replace(/[.,]/g,' ').replace(/\s+/g,' ');
  if(!a) return null;
  if(CITY_ALIAS[a]) a=CITY_ALIAS[a];
  if(CITY_LATLON[a]) return a;
  for(const k in CITY_LATLON){ if(a.indexOf(k)>=0) return k; }      // "Barcelona, Eixample"
  for(const k in CITY_ALIAS){ if(a.indexOf(k)>=0) return CITY_ALIAS[k]; }
  return null;                                                       // unknown city -> not plotted
}
function cityLabel(key){
  const RU={moscow:'Москва','saint petersburg':'Санкт-Петербург',barcelona:'Барселона',belgrade:'Белград',
    madrid:'Мадрид',lisbon:'Лиссабон',berlin:'Берлин',london:'Лондон',paris:'Париж',tbilisi:'Тбилиси',
    yerevan:'Ереван',istanbul:'Стамбул',warsaw:'Варшава',prague:'Прага',kyiv:'Киев',dubai:'Дубай',
    amsterdam:'Амстердам','tel aviv':'Тель-Авив',valencia:'Валенсия','new york':'Нью-Йорк'};
  const en=key.replace(/\b\w/g,c=>c.toUpperCase());
  return T(RU[key]||en, en);
}
// Plans grouped by the city we could resolve. Unresolvable areas are counted, never guessed.
function exploreAreas(src){
  const by={}; let unknown=0;
  (src||PUBLIC_INTENTS||[]).forEach(p=>{
    const k=cityKey(p.area);
    if(!k){ unknown++; return; }
    (by[k]=by[k]||{key:k,plans:[]}).plans.push(p);
  });
  return {areas:Object.values(by).sort((a,b)=>b.plans.length-a.plans.length), unknown};
}
let exploreMap=null, xLayer=null, xMarkers={};
let GROUPS=[];                                  // real, joinable groups (spec §15) — not synthesized rows
function initExploreMap(){
  if(typeof L==='undefined') return;                 // Leaflet not loaded
  const el=document.getElementById('lmap'); if(!el) return;
  // Build ONCE. Rebuilding on every render threw the user's pan/zoom away and made every pin blink;
  // when the map is already alive we only re-measure and redraw the markers.
  if(exploreMap && exploreMap.getContainer && document.body.contains(exploreMap.getContainer())){
    try{ exploreMap.invalidateSize(); }catch(_e){}
    drawExploreMarkers(); return;
  }
  if(exploreMap){ try{ exploreMap.remove(); }catch(_e){} }
  const map=L.map(el,{zoomControl:false,attributionControl:false,scrollWheelZoom:true,dragging:true,
    touchZoom:true,doubleClickZoom:true,zoomSnap:0,zoomDelta:1,wheelPxPerZoomLevel:90,
    inertia:true,inertiaDeceleration:2600,easeLinearity:.22,tap:true,tapTolerance:18,
    minZoom:2.5,maxZoom:17,bounceAtZoomLimits:false,
    maxBounds:[[-72,-190],[84,190]],maxBoundsViscosity:1});
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    {maxZoom:19,maxNativeZoom:18,detectRetina:true,updateWhenIdle:false,updateWhenZooming:false,keepBuffer:3}).addTo(map);
  xLayer=L.layerGroup().addTo(map); xMarkers={};
  const mine=cityKey(myArea());
  const start=exploreCam||{c:(mine&&CITY_LATLON[mine])||ME_LATLON, z:10};
  map.setView(start.c, start.z);                     // a view must exist before layers/bounds are used
  // Landing on an empty view is a dead end: if your own city has no plans, frame the ones that do.
  if(!exploreCam){
    const {areas}=exploreAreas(xVisiblePlans());
    const mineHas=areas.some(a=>a.key===mine&&a.plans.length);
    const pts=areas.map(a=>CITY_LATLON[a.key]).filter(Boolean);
    if(!mineHas&&pts.length){
      try{ map.fitBounds(L.latLngBounds(pts).pad(.25),{maxZoom:11,paddingBottomRight:[0,120]}); }catch(_e){}
    }
  }
  let t=null;
  const redraw=()=>{ clearTimeout(t); t=setTimeout(drawExploreMarkers,120); };
  map.on('movestart zoomstart', ()=>el.classList.add('moving'));
  map.on('moveend zoomend', ()=>{ el.classList.remove('moving');
    exploreCam={c:map.getCenter(), z:map.getZoom()};  // survives leaving and re-entering the tab
    xRedoCheck(); redraw(); });
  map.on('click', ()=>xDeselect());                  // tapping empty map dismisses the card
  exploreMap=map;
  drawExploreMarkers();
  const fit=()=>{ try{ map.invalidateSize(); }catch(_e){} };
  fit(); setTimeout(fit,90); setTimeout(fit,320);
}
// Below this zoom the map speaks in cities; above it, in individual plans. z12 is ~3.8 km across the
// 390px frame, so plans jittered +/-1.5 km around a centre are finally separable — at z9 they piled
// into one unreadable blob exactly when the split was meant to reveal detail.
const XCITY_MAX=12;
// Collapse anything closer than one cell so pins never stack (a clusterer in 10 lines, no plugin).
function xGrid(list, map, cell){
  const z=map.getZoom(), out={};
  list.forEach(p=>{ const q=map.project([+p.lat,+p.lon], z);
    const k=Math.round(q.x/cell)+':'+Math.round(q.y/cell);
    (out[k]=out[k]||[]).push(p); });
  return out;
}
function xPinIcon(p){ return IC[editIcon((p.topics&&p.topics[0])||p.title||'')]||IC.spark; }
function hasGeo(p){ const la=+p.lat, lo=+p.lon; return isFinite(la)&&isFinite(lo)&&!(la===0&&lo===0); }
// Selection lives as a class on the surviving node, so .xpin.sel / .xpin.desel can animate.
function xPaintSelection(){
  Object.keys(xMarkers).forEach(k=>{
    const node=xMarkers[k].getElement&&xMarkers[k].getElement();
    const pin=node&&node.querySelector('.xpin'); if(!pin) return;
    const on=(xSel!==null && k==='p'+xSel);
    if(on && !pin.classList.contains('sel')){ pin.classList.remove('desel'); pin.classList.add('sel'); }
    else if(!on && pin.classList.contains('sel')){
      pin.classList.remove('sel'); pin.classList.add('desel');
      setTimeout(()=>pin.classList.remove('desel'),200);
    }
  });
}
// The plans are jittered ~1.5 km around a city centroid, so a 42px pin claims a doorway it does not
// know. L.circle takes METRES and scales with zoom, so this ring means the same thing at every zoom.
const XJITTER_M=1500;
let xArea=null;
function xClearArea(){ if(xArea&&exploreMap){ try{ exploreMap.removeLayer(xArea); }catch(_e){} } xArea=null; }
function xShowArea(ll){
  if(!exploreMap) return; xClearArea();
  xArea=L.circle(ll,{radius:XJITTER_M,interactive:false,className:'xarea',
    color:'#F5455C',weight:1.25,opacity:.42,fillColor:'#F5455C',fillOpacity:.07}).addTo(exploreMap);
}
function xDeselect(){
  if(xSel===null) return;
  xSel=null;
  const c=document.getElementById('xcard'); if(c) c.classList.remove('on');
  const w=document.querySelector('.xwrap'); if(w) w.classList.remove('card-on');
  const m=document.getElementById('lmap'); if(m) m.classList.remove('hasSel');
  xClearArea();
  xPaintSelection();
}
// Group plans for the zoomed-out band. Deliberately NOT keyed off the CITY_LATLON lookup: that table
// knows 20 cities while the population lives in ~64, so 177 of 300 plans had real coordinates but an
// unrecognised city name and were invisible on the map — zooming into Copenhagen showed nothing at
// all. A group is positioned by the CENTROID of its own plans; the table is only a fallback for a
// group whose plans carry no coordinates. A group we cannot place at all is not drawn.
function xClusters(src){
  const by={};
  (src||[]).forEach(p=>{
    const ck=cityKey(p.area), raw=String(p.area||'').trim();
    const k=ck||(raw?('~'+raw.toLowerCase()):'');
    if(!k) return;
    (by[k]=by[k]||{key:k, ck:ck, raw:raw, plans:[]}).plans.push(p);
  });
  return Object.keys(by).map(k=>{
    const g=by[k], geo=g.plans.filter(hasGeo);
    const ll=geo.length
      ? [geo.reduce((a,p)=>a+(+p.lat),0)/geo.length, geo.reduce((a,p)=>a+(+p.lon),0)/geo.length]
      : (g.ck&&CITY_LATLON[g.ck])||null;
    return {key:k, ll:ll, label:g.ck?cityLabel(g.ck):g.raw, plans:g.plans};
  }).filter(g=>g.ll);
}
function drawExploreMarkers(){
  const map=exploreMap; if(!map||!xLayer) return;
  const z=Math.floor(map.getZoom()), mine=cityKey(myArea());
  const B=map.getBounds().pad(.35);                  // cull: never build pins the camera cannot see
  const want={};
  const src=xVisiblePlans();
  const showLab=z>=5;                                // below this the chips collide into a wall of text
  const cityNode=(key,count,isMine,label,ll)=>{
    const size=count>49?56:count>9?48:40, fs=count>49?16:count>9?15:13.5;
    return {ll:ll||CITY_LATLON[key], size:[110,size+22], anchor:[55,size/2],
      sig:'c'+key+':'+count+':'+(showLab?1:0),
      lab:label,
      html:'<div class="xpinwrap"><div class="xpin city'+(isMine?' me':'')+'" data-n="'
           +(count>49?'lg':count>9?'md':'sm')+'" role="button" tabindex="0" aria-label="'
           +esc(label||cityLabel(key))+', '+count+'" style="width:'+size+'px;height:'+size+'px">'
           +'<div class="in" style="font-size:'+fs+'px">'+(count>99?'99+':count)+'</div></div>'
           +(showLab?'<div class="xlab">'+esc(label||cityLabel(key))+'</div>':'')+'</div>'};
  };
  if(z<XCITY_MAX){
    xClusters(src).forEach(a=>{
      if(!B.contains(a.ll)) return;
      const n=cityNode(a.key, a.plans.length, a.key===mine, a.label, a.ll);
      n.onClick=()=>{ const pts=a.plans.filter(hasGeo).map(p=>[+p.lat,+p.lon]);
        const dz=Math.abs((pts.length?13:11)-map.getZoom()), dur=Math.min(1.1, .35+.11*dz);
        if(pts.length>=2) map.flyToBounds(L.latLngBounds(pts).pad(.15),{maxZoom:14,paddingBottomRight:[0,180],duration:dur});
        else map.flyTo(a.ll, 13, {duration:dur}); };
      want['c'+a.key]=n; });
  } else {
    // Coordinates are enough to place a plan — no city lookup involved.
    const geoAll=src.filter(p=>hasGeo(p)&&B.contains([+p.lat,+p.lon]));
    const cells=xGrid(geoAll, map, 64);
    Object.keys(cells).forEach(k=>{
        const grp=cells[k];
        if(grp.length===1){
          const p=grp[0];
          want['p'+p._i]={ll:[+p.lat,+p.lon], size:[42,42], anchor:[21,21],
            sig:'p'+p._i,
            html:'<div class="xpinwrap"><div class="xpin plan" role="button" tabindex="0" aria-label="'
                 +esc(p.title||'')+'" style="width:42px;height:42px"><div class="in">'+xPinIcon(p)+'</div></div></div>',
            onClick:()=>showPlanCard(p._i), zoff:(p._i===xSel?1000:0)};
        } else {
          const la=grp.reduce((m,p)=>m+(+p.lat),0)/grp.length, lo=grp.reduce((m,p)=>m+(+p.lon),0)/grp.length;
          want['g'+k]={ll:[la,lo], size:[36,36], anchor:[18,18], sig:'g'+grp.length,
            html:'<div class="xpinwrap"><div class="xpin grp" role="button" tabindex="0" aria-label="'
                 +grp.length+' '+T('планов рядом','plans here')+'" style="width:36px;height:36px"><div class="in">'+grp.length+'</div></div></div>',
            onClick:()=>map.flyTo([la,lo], Math.min(17, map.getZoom()+2), {duration:.45})};
        }
    });
    // Plans with no coordinates cannot be placed; keep them as one honest bubble on the city we do
    // know, and tapping it lists them rather than zooming into nothing.
    xClusters(src.filter(p=>!hasGeo(p))).forEach(a=>{
      if(!B.contains(a.ll)) return;
      const n=cityNode(a.key, a.plans.length, a.key===mine, a.label, a.ll);
      n.onClick=()=>{ if(a.ck!==undefined||cityKey(a.label)) focusArea(cityKey(a.label)||a.key); };
      want['c'+a.key]=n;
    });
  }
  // Don't stack the blue "you" dot on top of your own city's bubble — they share coordinates and the
  // dot just sits inside the coral disc. When your city has a bubble, the bubble wears the marker.
  const c=(mine&&CITY_LATLON[mine])
        ||((DATA.geo&&DATA.geo.coarseLat!=null)?[DATA.geo.coarseLat,DATA.geo.coarseLon]:null);
  if(c&&B.contains(c)&&!want['c'+mine]) want['me']={ll:c, size:[96,44], anchor:[48,10], zoff:900, noClick:true,
    sig:'me',
    html:'<div class="xhome"><div class="ring"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
       +' stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V21h13V9.5"/></svg></div>'
       +'<div class="cap">'+T('твой город','your city')+'</div></div>'};

  // Diff instead of clearLayers(): survivors keep their DOM node, so selection and the enter
  // animation are not destroyed on every pan.
  Object.keys(xMarkers).forEach(k=>{ if(!want[k]){ xLayer.removeLayer(xMarkers[k]); delete xMarkers[k]; } });
  // Selection used to be baked into the markup string, and this loop replaced innerHTML whenever the
  // string changed — so tapping a pin DESTROYED and rebuilt its node and the CSS transition never ran:
  // the pin jumped to its selected size. Diff on a cheap signature instead, and apply selection below
  // as a class toggle on the surviving node, which is what lets it animate at all.
  let born=0;
  Object.keys(want).forEach(k=>{
    const w=want[k], had=xMarkers[k];
    if(had){
      const elm=had.getElement&&had.getElement();
      if(elm && elm.dataset.sig!==w.sig){ elm.innerHTML=w.html; elm.dataset.sig=w.sig; }
      if(w.zoff!==undefined) had.setZIndexOffset(w.zoff);
      return;
    }
    const m=L.marker(w.ll,{icon:L.divIcon({className:'',iconSize:w.size,iconAnchor:w.anchor,html:w.html}),
                           zIndexOffset:w.zoff||0, interactive:!w.noClick});
    if(w.onClick){
      m.on('click',ev=>{ L.DomEvent.stopPropagation(ev); w.onClick(); });
      m.on('keypress',ev=>{ const key=ev.originalEvent&&ev.originalEvent.key;
        if(key==='Enter'||key===' '){ L.DomEvent.stop(ev); w.onClick(); } });
    }
    m.addTo(xLayer); xMarkers[k]=m;
    const node=m.getElement&&m.getElement();
    if(node) node.dataset.sig=w.sig;
    const pin=node&&node.querySelector('.xpin');
    // stagger the cascade so a city opening into its plans reads as a bloom, capped so 40 pins
    // never feel sluggish
    if(pin){ pin.style.setProperty('--pd', Math.min(born++*18,200)+'ms');
             pin.classList.add('new'); setTimeout(()=>pin.classList.remove('new'),260+Math.min(born*18,200)); }
  });
  // A card that outlived its pin: fly somewhere else and it kept sitting there describing a plan
  // off-screen (a Lagos meetup while looking at Copenhagen). Once the selected plan leaves the
  // viewport, let the card go.
  const sp=(xSel!==null)?PUBLIC_INTENTS[xSel]:null;
  if(sp && hasGeo(sp) && !B.contains([+sp.lat,+sp.lon])) xDeselect();
  else xPaintSelection();
}

async function joinGroup(i){
  const p=PUBLIC_INTENTS[i]; if(!p||!p.gid) return;
  if(p.mine){ toast(T('Ты уже в этой группе','You are already in')); return; }
  let r=null;
  try{
    r=await fetch('/api/agent/group-join',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({gid:p.gid, self:DATA.name||'', version:p.version,
                           idem:idemKey('gj:'+p.gid)})}).then(x=>x.json());
  }catch(e){ r=null; }
  if(!r){ toast(T('Нет связи — попробуй ещё раз','No connection — try again')); return; }
  if(!r.ok){
    toast(r.error==='NOT_ELIGIBLE' ? T('Не получится присоединиться','You cannot join this one')
        : r.error==='VERSION_CONFLICT' ? T('Группа изменилась — обнови','The group changed — refresh')
        : r.error==='CANCELLED' ? T('Группа отменена','This group was cancelled')
        : T('Не удалось присоединиться','Could not join'));
    exploreLoaded=false; loadExplore(); return;
  }
  toast(r.waitlisted ? T('Мест нет — ты в листе ожидания','Full — you are on the waitlist')
                     : T('Ты в группе','You are in'));
  addNotif('intent', r.waitlisted?T('Лист ожидания','Waitlist'):T('Ты в группе','You are in'),
           (p.title||'')+' · '+groupSeats(r.group||p), null);
  exploreLoaded=false; await loadExplore();
  if(cur==='search'){ xSyncList(); if(exploreMap) drawExploreMarkers(); }
  render(); saveState();
}
async function leaveGroup(gid){
  let r=null;
  try{
    r=await fetch('/api/agent/group-leave',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({gid, self:DATA.name||''})}).then(x=>x.json());
  }catch(e){ r=null; }
  if(!r||!r.ok){ toast(T('Не удалось выйти','Could not leave')); return; }
  toast(T('Ты вышел из группы','You left the group'));
  exploreLoaded=false; await loadExplore(); render(); saveState();
}
async function hostGroup(it){
  if(!it){ return; }
  let r=null;
  try{
    r=await fetch('/api/agent/group-create',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({host:DATA.name||'', title:it.title||'', topics:it.tags||it.topics||[],
        when:it.when||it.time||'', area:String(myArea()||'').split('·')[0].trim(), mode:it.mode||'offline',
        min_size:2, max_size:it.max_size||4,
        idem:idemKey('gc:'+(it.id||it.title||''))})}).then(x=>x.json());
  }catch(e){ r=null; }
  if(!r||!r.ok){ toast(T('Не удалось собрать группу','Could not open the group')); return; }
  toast(T('Группа открыта — люди могут присоединиться','Group is open — people can join'));
  exploreLoaded=false; await loadExplore(); render(); saveState();
}
async function joinPublic(i){
  // This used to only write a local notification claiming the host's agent had been asked.
  // Nothing was sent. Now it really asks their agent, and reports what actually happened.
  const p=PUBLIC_INTENTS[i]; if(!p) return;
  const who=p.who||p.name||'';
  if(!who){ toast(T('У этого плана нет владельца','This plan has no host')); return; }
  toast(T('Спрашиваю агента…','Asking their agent…'));
  let r=null;
  try{
    r=await fetch('/api/agent/negotiate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({intent:{topics:p.topics||[p.title||''],type:p.type||'social',
                                   time:p.when||'Flexible',mode:'offline',title:p.title||''},
                           profile:matchProfile(), candidates:[{name:who}]})}).then(x=>x.json());
  }catch(e){ r=null; }
  const v=(r&&r.candidates&&r.candidates[0])||null;
  if(!v){ toast(T('Не удалось связаться — попробуй позже','Could not reach them — try later')); return; }
  if(v.agree){
    addNotif('intent',T('Заявка принята','Request accepted')+': “'+(p.title||'')+'”',
             who+' — '+(v.reason||T('агент согласился','their agent agreed')), null);
    toast(T('Агент согласился','Their agent agreed'));
  } else {
    addNotif('intent',T('Пока отказ','Not this time')+': “'+(p.title||'')+'”',
             who+' — '+(v.reason||''), null);
    toast(v.reason||T('Пока не сложилось','Not this time'));
  }
  saveState(); render();
}

// Intents tab — rebuilt on the design system. It used to show raw percentages (which the spec
// forbids), English copy inside a Russian UI, and duplicate cards from repeated launches.
// ---- intents live on the server and are re-ranked on every load ----
// They used to be localStorage-only, holding a frozen candidate list from the moment of creation: a
// private note that never re-searched, while the requests and messages it drove were already shared.
async function loadIntents(){
  const me=(DATA.name||'').trim(); if(!me) return;
  try{
    const r=await fetch('/api/agent/intents',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({self:me, profile:matchProfile()})}).then(x=>x.json());
    const rows=(r&&r.intents)||[];
    DATA.intents=rows.map(it=>({
      id:it.id, title:it.title||(it.intent&&it.intent.title)||T('Без названия','Untitled'),
      tags:(it.intent&&it.intent.topics)||[], intent:it.intent||{}, launched:!!it.launched,
      candidates:it.candidates||[], server:true, error:it.error||null}));
    if(cur==='intents') render();
    saveState();
  }catch(e){}
}
// Opening a saved intent runs a FRESH search and lands in the same screens a new request does, so
// there is one visual language instead of two. It used to open `intentchat`, the older screen.
async function openIntentFlow(id){
  const it=(DATA.intents||[]).find(x=>x.id===id); if(!it) return;
  FLOW={text:it.title, request:it.title, msgs:[], intent:it.intent||{}, res:[], busy:true,
        summary:{request:it.title}, fromIntent:id};
  cur='searching'; render();
  await flowSearch();
  FLOW.busy=false;
  cur=(FLOW.res&&FLOW.res.length)?'bestfit':'fewmatches';
  render(); saveState();
}
async function deleteIntent(id){
  const me=(DATA.name||'').trim();
  try{ await fetch('/api/agent/intent-delete',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({self:me, id})}); }catch(e){}
  DATA.intents=(DATA.intents||[]).filter(x=>x.id!==id);
  render(); saveState(); toast(T('Интент удалён','Intent deleted'));
}
// Every launched request becomes a standing intent, so the tab reflects what Kleal is actually doing.
async function persistIntent(){
  const me=(DATA.name||'').trim(); if(!me||!FLOW||!FLOW.intent) return;
  try{
    await fetch('/api/agent/intent-save',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({self:me, id:FLOW.fromIntent||null,
        title:(FLOW.intent.title)||FLOW.request||'', intent:FLOW.intent, launched:true})});
  }catch(e){}
  loadIntents();
}
// Every request touching this account, both directions and all statuses — the Intents tab needs
// accepted (active), pending (proposals), archived and declined (archive) in one place. INBOX stays
// as the pending-only notifier it always was.
let REQS=[], _reqT=null, _reqGen=0;
// A poll that started BEFORE a local change lands after it and re-asserts the old status: pressing
// «В архив» left the card sitting in the active list until the next tick. Every mutation bumps the
// generation, and an in-flight poll whose generation is stale throws its answer away.
async function loadRequests(){
  const me=(DATA.name||'').trim(); if(!me) return;
  const gen=_reqGen;
  try{
    const [i,o]=await Promise.all([
      fetch('/api/agent/inbox?self='+encodeURIComponent(me)).then(x=>x.json()).catch(()=>null),
      fetch('/api/agent/outbox?self='+encodeURIComponent(me)).then(x=>x.json()).catch(()=>null)]);
    if(gen!==_reqGen) return;                    // superseded by a local change — discard
    const all=[...((i&&i.requests)||[]),...((o&&o.requests)||[])];
    const seen={}; REQS=all.filter(r=>r&&r.id&&!seen[r.id]&&(seen[r.id]=1));
    REQS.sort((a,b)=>(b.updated||0)-(a.updated||0));
    if(cur==='intents') render();
  }catch(e){}
  finally{ clearTimeout(_reqT); _reqT=setTimeout(loadRequests, 8000); }
}
async function archiveMeet(id){
  const me=(DATA.name||'').trim();
  _reqGen++;
  const r=REQS.find(x=>x.id===id); if(r) r.status='archived';   // optimistic, and now poll-proof
  render(); toast(T('Перенесено в архив','Moved to the archive'));
  try{ await fetch('/api/agent/request-archive',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id, self:me})}); }catch(e){}
  loadRequests();
}
// Open (or start) the conversation with the person from an active meetup. There was no way from a
// confirmed meetup to its chat; the Messages tab was the only door and you had to find the name.
function openMeetThread(name){
  const nm=String(name||'').trim(); if(!nm) return;
  DATA.messages=DATA.messages||[];
  let t=DATA.messages.find(x=>String(x.who||'').trim().toLowerCase()===nm.toLowerCase());
  if(!t){ t={who:nm, kleal:false, msgs:[], cand:{name:nm}, since:Date.now()/1000}; DATA.messages.unshift(t); }
  matchWith=t; matchWith.fromMessages=true; cur='matchchat'; render(); saveState();
}
let ARCHTAB='archived';
const TILE_SVG={"football":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"80\" cy=\"52\" r=\"26\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\"/><clipPath id=\"fb\"><circle cx=\"80\" cy=\"52\" r=\"26\"/></clipPath><g clip-path=\"url(#fb)\"><line x1=\"80.0\" y1=\"42.0\" x2=\"80.0\" y2=\"26.0\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\"/><path d=\"M80.0,33.0 L73.3,28.2 L75.9,20.3 L84.1,20.3 L86.7,28.2 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><line x1=\"89.51056516295154\" y1=\"48.90983005625053\" x2=\"104.727469423674\" y2=\"43.96555814625137\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\"/><path d=\"M98.1,46.1 L100.6,38.3 L108.8,38.3 L111.4,46.1 L104.7,51.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><line x1=\"85.87785252292473\" y1=\"60.09016994374947\" x2=\"95.2824165596043\" y2=\"73.03444185374863\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\"/><path d=\"M91.2,67.4 L99.4,67.4 L101.9,75.2 L95.3,80.0 L88.6,75.2 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><line x1=\"74.12214747707527\" y1=\"60.09016994374947\" x2=\"64.7175834403957\" y2=\"73.03444185374863\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\"/><path d=\"M68.8,67.4 L71.4,75.2 L64.7,80.0 L58.1,75.2 L60.6,67.4 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><line x1=\"70.48943483704846\" y1=\"48.90983005625053\" x2=\"55.272530576326005\" y2=\"43.965558146251375\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\"/><path d=\"M61.9,46.1 L55.3,51.0 L48.6,46.1 L51.2,38.3 L59.4,38.3 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/></g><path d=\"M80.0,42.0 L89.5,48.9 L85.9,60.1 L74.1,60.1 L70.5,48.9 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/></svg>","basketball":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"80\" cy=\"52\" r=\"25\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\"/><line x1=\"55\" y1=\"52\" x2=\"105\" y2=\"52\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\"/><line x1=\"80\" y1=\"27\" x2=\"80\" y2=\"77\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\"/><path d=\"M62 34 Q80 52 62 70\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M98 34 Q80 52 98 70\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","tennis":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><ellipse cx=\"72\" cy=\"62\" rx=\"15\" ry=\"20\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3.4\"/><line x1=\"72\" y1=\"44\" x2=\"58\" y2=\"30\" stroke=\"#181B22\" stroke-width=\"4.2\" stroke-linecap=\"round\"/><circle cx=\"56\" cy=\"28\" r=\"3\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"96\" cy=\"44\" r=\"13\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3.2\"/><path d=\"M96 33 Q90 44 96 55\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M96 33 Q102 44 96 55\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"66\" y1=\"50\" x2=\"66\" y2=\"74\" stroke=\"#181B22\" stroke-width=\"1.6\" stroke-linecap=\"round\"/><line x1=\"72\" y1=\"50\" x2=\"72\" y2=\"74\" stroke=\"#181B22\" stroke-width=\"1.6\" stroke-linecap=\"round\"/><line x1=\"78\" y1=\"50\" x2=\"78\" y2=\"74\" stroke=\"#181B22\" stroke-width=\"1.6\" stroke-linecap=\"round\"/><line x1=\"60\" y1=\"56\" x2=\"84\" y2=\"56\" stroke=\"#181B22\" stroke-width=\"1.6\" stroke-linecap=\"round\"/><line x1=\"60\" y1=\"64\" x2=\"84\" y2=\"64\" stroke=\"#181B22\" stroke-width=\"1.6\" stroke-linecap=\"round\"/></svg>","running":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"88\" cy=\"32\" r=\"6.5\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><path d=\"M84 39 L74 57\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M82 44 L94 49 L98 42\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M82 45 L70 40\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M74 57 L88 62 L90 78\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M74 57 L62 65 L56 78\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"44\" y1=\"44\" x2=\"54\" y2=\"44\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\"/><line x1=\"44\" y1=\"52\" x2=\"56\" y2=\"52\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\"/><line x1=\"44\" y1=\"60\" x2=\"58\" y2=\"60\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\"/></svg>","gym":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><line x1=\"58\" y1=\"52\" x2=\"102\" y2=\"52\" stroke=\"#181B22\" stroke-width=\"6\" stroke-linecap=\"round\"/><rect x=\"49\" y=\"40\" width=\"9\" height=\"24\" rx=\"3\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><rect x=\"102\" y=\"40\" width=\"9\" height=\"24\" rx=\"3\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><rect x=\"44\" y=\"44\" width=\"7\" height=\"16\" rx=\"2\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/><rect x=\"109\" y=\"44\" width=\"7\" height=\"16\" rx=\"2\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/></svg>","cycling":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"60\" cy=\"66\" r=\"14\" fill=\"none\" stroke=\"#181B22\" stroke-width=\"3.6\"/><circle cx=\"100\" cy=\"66\" r=\"14\" fill=\"none\" stroke=\"#181B22\" stroke-width=\"3.6\"/><path d=\"M60 66 L74 46 L94 46 M74 46 L86 66 L100 66 M74 46 L60 66\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"90\" y1=\"46\" x2=\"98\" y2=\"46\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\"/><circle cx=\"86\" cy=\"66\" r=\"2.5\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><path d=\"M92 40 q8 2 8 10\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","yoga":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"80\" cy=\"34\" r=\"7\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><path d=\"M80 41 L80 56\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M80 56 Q64 60 60 72 M80 56 Q96 60 100 72\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M80 48 Q66 52 62 60 M80 48 Q94 52 98 60\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M56 78 Q80 72 104 78\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3.2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","boxing":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M62 46 Q62 34 76 34 Q92 34 92 48 L92 64 Q92 74 80 74 L70 74 Q60 74 60 64 Z\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M62 48 Q56 48 56 56 Q56 64 62 64\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M92 50 L92 60\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><rect x=\"64\" y=\"72\" width=\"26\" height=\"6\" rx=\"3\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/></svg>","climbing":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M50.0,84.0 L74.0,44.0 L90.0,64.0 L102.0,50.0 L112.0,84.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M78.0,50.0 L84.0,50.0 L81.0,44.0 Z\" fill=\"#F5455C\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><line x1=\"78\" y1=\"44\" x2=\"78\" y2=\"58\" stroke=\"#F5455C\" stroke-width=\"2.4\" stroke-linecap=\"round\"/><circle cx=\"64\" cy=\"74\" r=\"2.2\" fill=\"#FFFFFF\" stroke=\"#FFFFFF\" stroke-width=\"0\"/><circle cx=\"92\" cy=\"72\" r=\"2.2\" fill=\"#FFFFFF\" stroke=\"#FFFFFF\" stroke-width=\"0\"/></svg>","swimming":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"84\" cy=\"40\" r=\"7\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><path d=\"M56 50 Q70 44 84 47 Q98 50 108 44\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M50 66 q8 -6 16 0 q8 6 16 0 q8 -6 16 0 q8 6 16 0\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M50 74 q8 -6 16 0 q8 6 16 0 q8 -6 16 0 q8 6 16 0\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","coffee":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M56 52 L60 82 Q60 86 66 86 L92 86 Q98 86 98 82 L102 52 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M98 58 Q112 58 110 70 Q108 78 98 76\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M72 34 q-5 6 0 12 q5 6 0 12\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M84 34 q-5 6 0 12 q5 6 0 12\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","dinner":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"80\" cy=\"58\" r=\"22\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\"/><circle cx=\"80\" cy=\"58\" r=\"13\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2\"/><line x1=\"48\" y1=\"52\" x2=\"48\" y2=\"78\" stroke=\"#181B22\" stroke-width=\"3.4\" stroke-linecap=\"round\"/><line x1=\"44\" y1=\"38\" x2=\"44\" y2=\"50\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\"/><line x1=\"48\" y1=\"38\" x2=\"48\" y2=\"50\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\"/><line x1=\"52\" y1=\"38\" x2=\"52\" y2=\"50\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\"/><path d=\"M44 50 Q48 54 52 50\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M112 38 Q116 46 112 54 L112 78\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","drinks":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M60.0,42.0 L100.0,42.0 L82.0,66.0 L78.0,66.0 Z\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linejoin=\"round\"/><line x1=\"80\" y1=\"66\" x2=\"80\" y2=\"82\" stroke=\"#181B22\" stroke-width=\"3.2\" stroke-linecap=\"round\"/><line x1=\"70\" y1=\"82\" x2=\"90\" y2=\"82\" stroke=\"#181B22\" stroke-width=\"3.2\" stroke-linecap=\"round\"/><circle cx=\"92\" cy=\"36\" r=\"4\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/><line x1=\"92\" y1=\"40\" x2=\"88\" y2=\"50\" stroke=\"#F5455C\" stroke-width=\"2.4\" stroke-linecap=\"round\"/></svg>","walk":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><ellipse cx=\"58\" cy=\"78\" rx=\"5\" ry=\"7\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"61\" cy=\"70\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><ellipse cx=\"74\" cy=\"66\" rx=\"5\" ry=\"7\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/><circle cx=\"77\" cy=\"58\" r=\"1.8\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/><ellipse cx=\"90\" cy=\"78\" rx=\"5\" ry=\"7\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"93\" cy=\"70\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><ellipse cx=\"106\" cy=\"66\" rx=\"5\" ry=\"7\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/><circle cx=\"109\" cy=\"58\" r=\"1.8\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/></svg>","gaming":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><ellipse cx=\"58\" cy=\"70\" rx=\"10\" ry=\"12\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><ellipse cx=\"102\" cy=\"70\" rx=\"10\" ry=\"12\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><rect x=\"56\" y=\"48\" width=\"48\" height=\"22\" rx=\"11\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><rect x=\"64\" y=\"56\" width=\"13\" height=\"4\" rx=\"2\" fill=\"#FFFFFF\" stroke=\"#FFFFFF\" stroke-width=\"0\"/><rect x=\"68.5\" y=\"51.5\" width=\"4\" height=\"13\" rx=\"2\" fill=\"#FFFFFF\" stroke=\"#FFFFFF\" stroke-width=\"0\"/><circle cx=\"94\" cy=\"55\" r=\"3.2\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/><circle cx=\"102\" cy=\"61\" r=\"3.2\" fill=\"#FFFFFF\" stroke=\"#FFFFFF\" stroke-width=\"0\"/></svg>","chess":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M78.0,82.0 L96.0,82.0 L93.0,75.0 L81.0,75.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M81 75 Q78 58 87 51 Q96 58 93 75 Z\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"87\" cy=\"45\" r=\"5\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><line x1=\"87\" y1=\"32\" x2=\"87\" y2=\"42\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\"/><line x1=\"82\" y1=\"36\" x2=\"92\" y2=\"36\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\"/><path d=\"M60.0,82.0 L74.0,82.0 L72.0,76.0 L62.0,76.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M63 76 Q60 65 67 61 Q74 65 71 76 Z\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"67\" cy=\"57\" r=\"4.2\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/></svg>","boardgames":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><rect x=\"58\" y=\"44\" width=\"26\" height=\"36\" rx=\"4\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\"/><g transform=\"rotate(12 92 60)\"><rect x=\"80\" y=\"44\" width=\"26\" height=\"36\" rx=\"4\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\"/><path d=\"M93.0,53.0 L100.0,60.0 L93.0,67.0 L86.0,60.0 Z\" fill=\"#F5455C\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/></g><path d=\"M71.0,55.0 L78.0,62.0 L71.0,69.0 L64.0,62.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/></svg>","cinema":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><rect x=\"52\" y=\"50\" width=\"56\" height=\"32\" rx=\"4\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><g transform=\"rotate(-8 52 50)\"><rect x=\"50\" y=\"42\" width=\"58\" height=\"10\" rx=\"2\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/></g><path d=\"M54.0,42.0 L60.0,42.0 L56.0,50.0 L50.0,50.0 Z\" fill=\"#FFFFFF\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M65.0,42.0 L71.0,42.0 L67.0,50.0 L61.0,50.0 Z\" fill=\"#FFFFFF\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M76.0,42.0 L82.0,42.0 L78.0,50.0 L72.0,50.0 Z\" fill=\"#FFFFFF\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M87.0,42.0 L93.0,42.0 L89.0,50.0 L83.0,50.0 Z\" fill=\"#FFFFFF\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M98.0,42.0 L104.0,42.0 L100.0,50.0 L94.0,50.0 Z\" fill=\"#FFFFFF\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M96 60 q8 3 8 12\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","art":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><rect x=\"56\" y=\"38\" width=\"48\" height=\"42\" rx=\"4\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3.2\"/><path d=\"M62.0,74.0 L76.0,54.0 L84.0,64.0 L92.0,50.0 L98.0,74.0 Z\" fill=\"#FBD5DB\" stroke=\"#FBD5DB\" stroke-width=\"0\" stroke-linejoin=\"round\"/><circle cx=\"74\" cy=\"50\" r=\"4\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/><line x1=\"56\" y1=\"80\" x2=\"104\" y2=\"80\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\"/></svg>","theatre":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M50 40 Q50 74 66 74 Q82 74 82 40 Q66 36 50 40 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"60\" cy=\"52\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"72\" cy=\"52\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><path d=\"M58 62 q8 6 16 0\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M82 44 Q82 78 98 78 Q114 78 114 44 Q98 40 82 44 Z\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"92\" cy=\"56\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"104\" cy=\"56\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><path d=\"M90 62 q8 -6 16 0\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","books":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><rect x=\"54\" y=\"58\" width=\"52\" height=\"10\" rx=\"2\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><rect x=\"58\" y=\"48\" width=\"44\" height=\"10\" rx=\"2\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\"/><rect x=\"62\" y=\"38\" width=\"36\" height=\"10\" rx=\"2\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\"/><line x1=\"66\" y1=\"43\" x2=\"94\" y2=\"43\" stroke=\"#181B22\" stroke-width=\"2\" stroke-linecap=\"round\"/></svg>","photography":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><rect x=\"50\" y=\"46\" width=\"60\" height=\"38\" rx=\"6\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><rect x=\"70\" y=\"40\" width=\"20\" height=\"8\" rx=\"3\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"80\" cy=\"65\" r=\"13\" fill=\"#FFF3EC\" stroke=\"#FFFFFF\" stroke-width=\"3\"/><circle cx=\"80\" cy=\"65\" r=\"7\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\"/><circle cx=\"100\" cy=\"52\" r=\"2.4\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/></svg>","startups":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M80 30 Q96 46 92 70 L68 70 Q64 46 80 30 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"80\" cy=\"50\" r=\"5\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"2.4\"/><path d=\"M68.0,64.0 L60.0,78.0 L72.0,72.0 Z\" fill=\"#F5455C\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M92.0,64.0 L100.0,78.0 L88.0,72.0 Z\" fill=\"#F5455C\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M74 74 q6 8 12 0\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","coding":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M66 42 L50 60 L66 78\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M94 42 L110 60 L94 78\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"86\" y1=\"40\" x2=\"74\" y2=\"80\" stroke=\"#F5455C\" stroke-width=\"3.4\" stroke-linecap=\"round\"/></svg>","design":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M80.0,34.0 L90.0,58.0 L80.0,52.0 L70.0,58.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><line x1=\"80\" y1=\"52\" x2=\"80\" y2=\"64\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\"/><circle cx=\"80\" cy=\"62\" r=\"2.4\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/><path d=\"M62 82 Q80 70 98 82\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","concert":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"66\" cy=\"74\" r=\"7\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"96\" cy=\"68\" r=\"7\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><line x1=\"73\" y1=\"74\" x2=\"73\" y2=\"42\" stroke=\"#181B22\" stroke-width=\"3.4\" stroke-linecap=\"round\"/><line x1=\"103\" y1=\"68\" x2=\"103\" y2=\"36\" stroke=\"#181B22\" stroke-width=\"3.4\" stroke-linecap=\"round\"/><line x1=\"73\" y1=\"42\" x2=\"103\" y2=\"36\" stroke=\"#181B22\" stroke-width=\"3.4\" stroke-linecap=\"round\"/><path d=\"M108 40 q8 2 8 10\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","guitar":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><ellipse cx=\"74\" cy=\"68\" rx=\"17\" ry=\"20\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"3\"/><circle cx=\"74\" cy=\"66\" r=\"6\" fill=\"#FFF3EC\" stroke=\"#181B22\" stroke-width=\"2.4\"/><line x1=\"80\" y1=\"54\" x2=\"104\" y2=\"30\" stroke=\"#181B22\" stroke-width=\"5\" stroke-linecap=\"round\"/><rect x=\"100\" y=\"24\" width=\"12\" height=\"10\" rx=\"2\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><line x1=\"78.5\" y1=\"54\" x2=\"102.5\" y2=\"30\" stroke=\"#FFF3EC\" stroke-width=\"0.8\" stroke-linecap=\"round\"/><line x1=\"81.5\" y1=\"54\" x2=\"105.5\" y2=\"30\" stroke=\"#FFF3EC\" stroke-width=\"0.8\" stroke-linecap=\"round\"/></svg>","dj":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M52 66 Q52 40 80 40 Q108 40 108 66\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><rect x=\"48\" y=\"64\" width=\"12\" height=\"18\" rx=\"4\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><rect x=\"100\" y=\"64\" width=\"12\" height=\"18\" rx=\"4\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/></svg>","karaoke":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><circle cx=\"80\" cy=\"44\" r=\"12\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\"/><rect x=\"74\" y=\"54\" width=\"12\" height=\"6\" rx=\"3\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><line x1=\"80\" y1=\"60\" x2=\"80\" y2=\"80\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\"/><line x1=\"72\" y1=\"80\" x2=\"88\" y2=\"80\" stroke=\"#181B22\" stroke-width=\"4\" stroke-linecap=\"round\"/><line x1=\"74\" y1=\"40\" x2=\"86\" y2=\"40\" stroke=\"#181B22\" stroke-width=\"1.4\" stroke-linecap=\"round\"/><line x1=\"74\" y1=\"46\" x2=\"86\" y2=\"46\" stroke=\"#181B22\" stroke-width=\"1.4\" stroke-linecap=\"round\"/></svg>","hiking":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M48.0,84.0 L76.0,40.0 L92.0,66.0 L104.0,48.0 L116.0,84.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M72.0,50.0 L80.0,44.0 L76.0,40.0 Z\" fill=\"#FFFFFF\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><circle cx=\"104\" cy=\"40\" r=\"6\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/></svg>","surfing":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><g transform=\"rotate(-32 80 58)\"><ellipse cx=\"80\" cy=\"58\" rx=\"10\" ry=\"34\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\"/><line x1=\"80\" y1=\"30\" x2=\"80\" y2=\"86\" stroke=\"#181B22\" stroke-width=\"2\" stroke-linecap=\"round\"/></g><path d=\"M46 84 q10 -8 20 0 q10 8 20 0 q10 -8 20 0\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","skiing":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M54 76 Q49 73 51 68 L104 50\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M58 80 Q53 77 55 72 L108 54\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"74\" y1=\"64\" x2=\"74\" y2=\"58\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\"/><line x1=\"88\" y1=\"60\" x2=\"88\" y2=\"54\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\"/><line x1=\"92.0\" y1=\"34.0\" x2=\"108.0\" y2=\"34.0\" stroke=\"#F5455C\" stroke-width=\"2.2\" stroke-linecap=\"round\"/><line x1=\"96.0\" y1=\"27.071796769724493\" x2=\"104.0\" y2=\"40.92820323027551\" stroke=\"#F5455C\" stroke-width=\"2.2\" stroke-linecap=\"round\"/><line x1=\"104.0\" y1=\"27.07179676972449\" x2=\"96.0\" y2=\"40.92820323027551\" stroke=\"#F5455C\" stroke-width=\"2.2\" stroke-linecap=\"round\"/></svg>","camping":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M80.0,36.0 L108.0,80.0 L52.0,80.0 Z\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linejoin=\"round\"/><path d=\"M80.0,44.0 L80.0,80.0 L70.0,80.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M80.0,44.0 L80.0,80.0 L90.0,80.0 Z\" fill=\"#F5455C\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><line x1=\"80\" y1=\"32\" x2=\"80\" y2=\"40\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\"/></svg>","travel":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M52 62 L104 50 Q112 48 112 54 Q112 60 104 62 L92 66 L84 82 L78 80 L82 64 L66 68 L60 76 L54 74 L58 62 Z\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"98\" cy=\"55\" r=\"2\" fill=\"#FFFFFF\" stroke=\"#FFFFFF\" stroke-width=\"0\"/></svg>","fishing":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M60 60 Q78 44 98 60 Q78 76 60 60 Z\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M58.0,60.0 L48.0,52.0 L48.0,68.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><circle cx=\"86\" cy=\"56\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><path d=\"M104 34 Q104 60 96 62\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"104\" cy=\"32\" r=\"2\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/></svg>","language":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M50 42 Q50 34 60 34 L86 34 Q96 34 96 42 L96 56 Q96 64 86 64 L64 64 L54 72 L56 64 Q50 62 50 56 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M74 54 Q74 46 84 46 L104 46 Q114 46 114 54 L114 66 Q114 74 104 74 L100 74 L106 82 L94 74 Q84 74 84 66\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"60\" y1=\"44\" x2=\"74\" y2=\"44\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\"/><line x1=\"60\" y1=\"52\" x2=\"70\" y2=\"52\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\"/></svg>","meditation":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><g transform=\"rotate(-58 80 68)\"><ellipse cx=\"80\" cy=\"52\" rx=\"7\" ry=\"16\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"2.4\"/></g><g transform=\"rotate(58 80 68)\"><ellipse cx=\"80\" cy=\"52\" rx=\"7\" ry=\"16\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"2.4\"/></g><g transform=\"rotate(-28 80 68)\"><ellipse cx=\"80\" cy=\"52\" rx=\"7\" ry=\"16\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"2.4\"/></g><g transform=\"rotate(28 80 68)\"><ellipse cx=\"80\" cy=\"52\" rx=\"7\" ry=\"16\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"2.4\"/></g><g transform=\"rotate(0 80 68)\"><ellipse cx=\"80\" cy=\"52\" rx=\"7\" ry=\"16\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"2.4\"/></g><path d=\"M56 72 Q80 80 104 72\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","cooking":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M58 54 Q58 38 80 38 Q102 38 102 54 Q110 54 110 62 L50 62 Q50 54 58 54 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><rect x=\"56\" y=\"62\" width=\"48\" height=\"8\" rx=\"2\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><path d=\"M80 44 q0 6 0 10\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M70 46 q0 5 0 8\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M90 46 q0 5 0 8\" fill=\"None\" stroke=\"#F5455C\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","pets":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><ellipse cx=\"80\" cy=\"66\" rx=\"9\" ry=\"7\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><ellipse cx=\"66\" cy=\"52\" rx=\"4.4\" ry=\"5.6\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><ellipse cx=\"76\" cy=\"46\" rx=\"4.4\" ry=\"5.6\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><ellipse cx=\"86\" cy=\"46\" rx=\"4.4\" ry=\"5.6\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><ellipse cx=\"96\" cy=\"52\" rx=\"4.4\" ry=\"5.6\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"80\" cy=\"66\" r=\"2.4\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/></svg>","dating":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M80 82 Q52 62 52 46 Q52 34 64 34 Q74 34 80 46 Q86 34 96 34 Q108 34 108 46 Q108 62 80 82 Z\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M68 46 Q70 42 74 42\" fill=\"None\" stroke=\"#FFFFFF\" stroke-width=\"2.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","fashion":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M80 40 Q76 36 80 33\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M80.0,42.0 L70.0,48.0 L90.0,48.0 Z\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linejoin=\"round\"/><path d=\"M72 48 L88 48 L84 60 L94 80 L66 80 L76 60 Z\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"76\" y1=\"60\" x2=\"84\" y2=\"60\" stroke=\"#F5455C\" stroke-width=\"3\" stroke-linecap=\"round\"/></svg>","wine":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M70 40 L90 40 Q90 56 80 58 Q70 56 70 40 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M71 48 Q80 53 89 48 Q88 55 80 58 Q72 55 71 48 Z\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"80\" y1=\"58\" x2=\"80\" y2=\"76\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\"/><ellipse cx=\"80\" cy=\"78\" rx=\"10\" ry=\"2.6\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/></svg>","festival":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M47 45 Q80 55 117 45\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M47.0,45.0 L61.0,45.0 L54.0,60.0 Z\" fill=\"#F5455C\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M61.0,48.0 L75.0,48.0 L68.0,63.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M75.0,49.0 L89.0,49.0 L82.0,64.0 Z\" fill=\"#F5455C\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M89.0,48.0 L103.0,48.0 L96.0,63.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M103.0,45.0 L117.0,45.0 L110.0,60.0 Z\" fill=\"#F5455C\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><path d=\"M80 26 l1.6 4.4 4.6 0 -3.7 2.9 1.4 4.5 -3.9 -2.8 -3.9 2.8 1.4 -4.5 -3.7 -2.9 4.6 0 z\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>","gardening":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M68.0,68.0 L92.0,68.0 L88.0,82.0 L72.0,82.0 Z\" fill=\"#181B22\" stroke=\"none\" stroke-width=\"0\" stroke-linejoin=\"round\"/><rect x=\"65\" y=\"63\" width=\"30\" height=\"6\" rx=\"2\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><line x1=\"80\" y1=\"64\" x2=\"80\" y2=\"50\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\"/><path d=\"M80 58 Q68 54 65 62 Q73 65 80 58 Z\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M80 54 Q92 50 95 58 Q87 61 80 54 Z\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"2.4\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"80\" cy=\"48\" r=\"4\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/></svg>","baking":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M66 62 L94 62 L90 82 L70 82 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><line x1=\"74\" y1=\"63\" x2=\"76\" y2=\"80\" stroke=\"#181B22\" stroke-width=\"1.8\" stroke-linecap=\"round\"/><line x1=\"80\" y1=\"63\" x2=\"80\" y2=\"80\" stroke=\"#181B22\" stroke-width=\"1.8\" stroke-linecap=\"round\"/><line x1=\"86\" y1=\"63\" x2=\"84\" y2=\"80\" stroke=\"#181B22\" stroke-width=\"1.8\" stroke-linecap=\"round\"/><path d=\"M64 62 Q64 50 74 50 Q76 42 84 46 Q95 45 93 56 Q100 58 96 62 Z\" fill=\"#FBD5DB\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"80\" cy=\"44\" r=\"4\" fill=\"#F5455C\" stroke=\"#F5455C\" stroke-width=\"0\"/></svg>","dnd":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M80.0,30.0 L102.5,43.0 L102.5,69.0 L80.0,82.0 L57.5,69.0 L57.5,43.0 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linejoin=\"round\"/><path d=\"M80.0,42.0 L64.0,66.0 L96.0,66.0 Z\" fill=\"None\" stroke=\"#181B22\" stroke-width=\"2.2\" stroke-linejoin=\"round\"/><line x1=\"80\" y1=\"42\" x2=\"80.0\" y2=\"30.0\" stroke=\"#181B22\" stroke-width=\"1.8\" stroke-linecap=\"round\"/><line x1=\"64\" y1=\"66\" x2=\"57.48333950160459\" y2=\"69.0\" stroke=\"#181B22\" stroke-width=\"1.8\" stroke-linecap=\"round\"/><line x1=\"96\" y1=\"66\" x2=\"102.51666049839541\" y2=\"69.0\" stroke=\"#181B22\" stroke-width=\"1.8\" stroke-linecap=\"round\"/><text x=\"80\" y=\"61\" text-anchor=\"middle\" font-family=\"Arial,sans-serif\" font-size=\"14\" font-weight=\"700\" fill=\"#F5455C\">20</text></svg>","social":"<svg viewBox=\"0 0 160 120\" xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"100%\" preserveAspectRatio=\"xMidYMid slice\"><rect x=\"0\" y=\"0\" width=\"160\" height=\"120\" fill=\"#FFF3EC\"/><ellipse cx=\"80\" cy=\"98\" rx=\"34\" ry=\"6\" fill=\"#F5455C\" opacity=\"0.14\"/><path d=\"M50 42 Q50 34 60 34 L82 34 Q92 34 92 42 L92 54 Q92 62 82 62 L64 62 L54 70 L56 62 Q50 60 50 54 Z\" fill=\"#FFFFFF\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><path d=\"M72 52 Q72 44 82 44 L104 44 Q114 44 114 52 L114 64 Q114 72 104 72 L100 72 L106 80 L94 72 Q82 72 82 64\" fill=\"#F5455C\" stroke=\"#181B22\" stroke-width=\"3\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/><circle cx=\"63\" cy=\"48\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"71\" cy=\"48\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/><circle cx=\"79\" cy=\"48\" r=\"1.8\" fill=\"#181B22\" stroke=\"#181B22\" stroke-width=\"0\"/></svg>"};
// Auto-pick a category illustration from an intent's topics/title. Ordered specific->generic so
// "boardgames"/"chess"/"dnd" win over the generic "game", "wine" over "bar", "baking" over "cook".
const _TILE_MATCH=[
 ['dnd',/\bdnd\b|d&d|dungeon|подземел/],['chess',/chess|шахмат/],
 ['boardgames',/boardgame|tabletop|\bcards\b|poker|настол|покер/],
 ['football',/football|soccer|футбол/],
 ['gaming',/dota|valorant|\bcs\b|league|apex|fortnite|fifa|overwatch|minecraft|roblox|pubg|warzone|gaming|\bgame|игр|катк/],
 ['wine',/\bwine\b|вино/],['drinks',/\bbar\b|drinks|\bpub\b|beer|nightlife|club|cocktail|бар|пив|коктейл|тусовк/],
 ['coffee',/coffee|\btea\b|brunch|cafe|кофе|\bчай/],['dinner',/dinner|lunch|\bfood\b|restaurant|dining|ужин|обед|ресторан|поесть/],
 ['baking',/baking|\bbake|выпеч|десерт|\bторт|кекс/],['cooking',/cook|готов|\bкухн/],
 ['festival',/festival|фестивал/],['concert',/concert|\bgig\b|концерт|\blive\b|музык|\bmusic/],
 ['guitar',/guitar|piano|drums|\bjam\b|\bband\b|producing|гитар|пианино/],
 ['dj',/\bdj\b|techno|edm|electronic|\brave\b|электрон|диджей/],['karaoke',/karaoke|singing|караоке/],
['basketball',/basketball|basket|баскет/],
 ['tennis',/tennis|padel|badminton|squash|теннис|падел/],['running',/\brun\b|running|\bjog|marathon|\bбег|пробеж/],
 ['gym',/\bgym\b|fitness|workout|crossfit|strength|качал|\bзал\b/],['cycling',/cycl|\bbike\b|biking|велос/],
 ['yoga',/\byoga\b|pilates|stretch|йог|пилат/],['boxing',/\bbox|\bmma\b|kickbox|бокс/],
 ['climbing',/climb|boulder|скалолаз/],['swimming',/swim|плав/],['walk',/\bwalk|stroll|\bhang|прогул|погул/],
 ['hiking',/\bhik|trek|\bnature\b|mountain|\btrail\b|outdoor|поход|хайк|\bгоры/],
 ['surfing',/surf|kayak|сёрф|серф|каяк/],['skiing',/\bski\b|skiing|snowboard|лыж|сноуборд/],
 ['camping',/\bcamp|кемпинг|палатк/],['travel',/travel|roadtrip|sightseeing|путешеств|поездк/],
 ['fishing',/fish|рыбал/],['cinema',/cinema|movie|\bfilm|series|\bкино|фильм|сериал/],
 ['theatre',/theatre|theater|opera|ballet|standup|стендап|театр|\bопер|балет/],
 ['art',/\bart\b|museum|gallery|paint|exhibition|искусств|музей|галере|живопис/],
 ['books',/\bbook|reading|literature|книг|\bчита|литератур/],['photography',/photo|фото/],
 ['fashion',/fashion|\bмода|стиль|одежд/],['gardening',/garden|\bсад\b|садов|растен|plant/],
 ['pets',/\bpet|\bdog|\bcat\b|питом|собак|кошк/],
 ['coding',/\bai\b|\bml\b|coding|programming|software|\bdata\b|\bcode|\btech\b|нейросет|программир|разработк/],
 ['startups',/startup|founder|entrepreneur|business|\bproduct\b|стартап|бизнес|основател/],

 ['design',/design|\bux\b|\bui\b|дизайн/],
 ['language',/language|spanish|english|french|german|italian|exchange|practice|язык|испанск|английск/],
 ['meditation',/meditat|\bzen\b|медитац|осознан/],['dating',/dating|\bdate\b|свидан|знаком/],
];
function tileKeyFor(words){ const s=String(words||'').toLowerCase();
  for(const m of _TILE_MATCH){ if(m[1].test(s)) return m[0]; } return 'social'; }
// The card illustration for an intent — derived from its own topics, so EXISTING intents get a
// picture too (nothing stored; it is computed at render).
function intentTile(it){
  // Topics are the authoritative signal — match them first so an «AI reading group» reads as coding,
  // not books. The title is a weaker fallback used only when the topics matched nothing.
  const topics=((it.tags||[]).concat(((it.intent||{}).topics)||[])).join(' ');
  let k=tileKeyFor(topics);
  if(k==='social') k=tileKeyFor(it.title||'');
  return '<div class="itile">'+(TILE_SVG[k]||TILE_SVG.social)+'</div>';
}

const NOT_ACCEPTED=['declined','expired','withdrawn','policy_revoked'];
function reqStatusLabel(st){
  return st==='accepted'      ? T('подтверждена','confirmed')
       : st==='declined'      ? T('не принято','not accepted')
       : st==='expired'       ? T('истекло','expired')
       : st==='withdrawn'     ? T('отозвано','withdrawn')
       : st==='policy_revoked'? T('отменено настройками','revoked by settings')
       :                        T('в архиве','archived');
}
function scr_intents(){
  if(!_intT){ _intT=1; loadIntents(); }
  if(!_reqT){ _reqT=1; loadRequests(); }
  const list=DATA.intents||[];
  const sec=(title,count,body)=>`<div style="display:flex;flex-direction:column;gap:12px">
    <div class="k-title">${esc(title)}${count?`<span style="color:var(--muted);font-weight:500"> · ${count}</span>`:''}</div>
    ${body}</div>`;
  const none=t=>`<div class="k-cap" style="color:var(--muted);padding:2px 2px 4px">${esc(t)}</div>`;
  const who=r=>((DATA.name||'').trim().toLowerCase()===String(r.to||'').trim().toLowerCase())?r.from:r.to;
  const line=r=>[locStr((r.intent&&r.intent.time)||''), locStr((r.intent&&r.intent.place)||'')].filter(Boolean).join(' · ');
  const meetCard=(r,acts)=>`<div class="icard">
    <div class="ihd"><div class="itl">${esc((r.intent&&r.intent.title)||r.note||T('Встреча','Meetup'))}</div>
      <span class="kbadge ${r.status==='accepted'?'ok':'mut'}">${esc(reqStatusLabel(r.status))}</span></div>
    <div class="ifoot"><span class="k-cap" style="color:var(--muted)">${esc(who(r))}</span>
      <span class="k-cap" style="color:var(--muted)">${esc(line(r))}</span></div>
    ${acts||''}</div>`;

  // 1. MY ACTIVE MEETUPS — requests both sides agreed to, either direction
  const active=REQS.filter(r=>r.status==='accepted');
  const s1=sec(T('Мои активные встречи','My active meetups'), active.length,
    active.length?active.map(r=>meetCard(r,`<div class="iacts">
        <button class="kbtn sec sm" data-act="meet-msg" data-who="${esc(who(r))}">${T('Написать','Message')}</button>
        <button class="kbtn sec sm" data-act="meet-archive" data-id="${esc(r.id)}">${T('В архив','Archive')}</button>
      </div>`)).join('')
      :none(T('Пока нет подтверждённых встреч.','No confirmed meetups yet.')));

  // 1b. MY GROUPS — real multi-person meetups (spec §15). Seats and state are facts from the
  // server, so nothing here is a guess: «3/4 · набирается» means exactly that.
  if(!GROUPS.length && !exploreLoaded && !exploreLoading) loadExplore();
  const myG=GROUPS.filter(g=>g.mine||g.waiting);
  const s1b=sec(T('Мои группы','My groups'), myG.length,
    myG.length?myG.map(g=>{
      const b=groupBadge(g), tags=(g.topics||[]).slice(0,4);
      return `<div class="icard">
        <div class="ihd"><div class="itl">${esc(g.title||T('Групповая встреча','Group meetup'))}</div>
          <span class="kbadge ${b[1]}">${esc(b[0])} · ${groupSeats(g)}</span></div>
        ${tags.length?`<div class="itags">${tags.map(t=>`<span class="ktag">${esc(locTopic(t))}</span>`).join('')}</div>`:''}
        <div class="ifoot"><span class="k-cap" style="color:var(--muted)">${esc(
            (g.hosting?T('ты организатор','you host'):T('организатор','host')+' · '+g.host)
            +(g.waiting?(' · '+T('лист ожидания','waitlist')):''))}</span>
          <span class="k-cap" style="color:var(--muted)">${esc([locStr(g.when||''),locStr(g.area||'')].filter(Boolean).join(' · '))}</span></div>
        <div class="iacts">
          <button class="kbtn sec sm" data-act="group-leave" data-gid="${esc(g.gid)}">${T('Выйти','Leave')}</button>
        </div></div>`; }).join('')
      :none(T('Ты пока не в группах. Открой «Обзор» — там видно, к чему можно присоединиться.',
              'You are not in any group yet. Open Explore to see what you can join.')));

  // 2. PROPOSALS FROM OTHER PEOPLE — the pending inbox
  const pend=REQS.filter(r=>r.status==='pending'&&String(r.to||'').trim().toLowerCase()===(DATA.name||'').trim().toLowerCase());
  const s2=sec(T('Предложения от других людей','Proposals from other people'), pend.length,
    pend.length?pend.map(r=>`<div class="icard">
      <div class="ihd"><div class="itl">${esc(r.from)}</div>
        <span class="kbadge warn">${T('ждёт ответа','awaiting you')}</span></div>
      <div class="k-cap" style="color:var(--muted)">${esc(r.note||((r.intent&&r.intent.title)||T('хочет встретиться','wants to meet')))}</div>
      <div class="iacts">
        <button class="kbtn pri sm" data-act="req-yes" data-id="${esc(r.id)}">${T('Принять','Accept')}</button>
        <button class="kbtn sec sm" data-act="req-no" data-id="${esc(r.id)}">${T('Отклонить','Decline')}</button>
      </div></div>`).join('')
      :none(T('Пока никто не предлагал встретиться.','Nobody has proposed a meetup yet.')));

  // 3. MY INTENTS — status is derived from facts, never guessed: whether a search has actually run
  // (server `launched`) and whether the live re-rank currently returns anyone.
  const istat=it=>!it.launched ? [T('поиск не начат','search not started'),'mut']
    : ((it.candidates||[]).length ? [T('нашли людей','people found'),'ok']
                                  : [T('поиск начат','searching'),'warn']);
  const s3=sec(T('Мои созданные интенты','My intents'), list.length,
    (list.length?list.map(it=>{
      const cs=it.candidates||[], st=istat(it), tags=(it.tags||[]).slice(0,4);
      return `<div class="icard" ${it.id?`data-savedintent="${it.id}"`:''}>
        ${intentTile(it)}
        <div class="ihd"><div class="itl">${esc(it.title||T('Без названия','Untitled'))}</div>
          <span class="kbadge ${st[1]}">${esc(st[0])}</span></div>
        ${tags.length?`<div class="itags">${tags.map(t=>`<span class="ktag">${esc(locTopic(t))}</span>`).join('')}</div>`:''}
        <div class="ifoot"><span class="k-cap" style="color:var(--muted)">${cs.length
            ? (cs.length+' '+plural(cs.length,T('кандидат','match'),T('кандидата','matches'),T('кандидатов','matches')))
            : T('пока никого','no one yet')}</span></div>
        <div class="iacts">
          <button class="kbtn sec sm" data-act="intent-open" data-id="${esc(it.id||'')}">${T('Открыть','Open')}</button>
          <button class="kbtn sec sm" data-act="group-host" data-id="${esc(it.id||'')}">${T('Собрать группу','Open a group')}</button>
          <button class="kbtn sec sm" data-act="intent-del" data-id="${esc(it.id||'')}">${T('Удалить','Delete')}</button>
        </div></div>`; }).join('')
      :none(T('Расскажи Kleal, чем хочешь заняться — он соберёт план и найдёт людей.','Tell Kleal what you would like to do — it will build the plan and find people.')))
    +`<button class="kbtn pri tall" data-act="createintent">${T('Создать интент','Create intent')}</button>`);

  // 4. ARCHIVE — archived by hand, plus a toggle for the ones that were never accepted
  // «Непринятые» means every terminal state that is not an acceptance — declined, expired,
  // withdrawn by the sender, or revoked because policy changed before the accept committed.
  const arch=REQS.filter(r=>r.status==='archived'), decl=REQS.filter(r=>NOT_ACCEPTED.indexOf(r.status)>=0);
  const shown=ARCHTAB==='declined'?decl:arch;
  const s4=sec(T('Архив встреч','Meetup archive'), shown.length,
    `<div class="kchips" style="margin-bottom:2px">
       <div class="kchip ${ARCHTAB!=='declined'?'on':''}" data-act="arch-tab" data-v="archived">${T('Прошедшие','Past')} · ${arch.length}</div>
       <div class="kchip ${ARCHTAB==='declined'?'on':''}" data-act="arch-tab" data-v="declined">${T('Непринятые','Not accepted')} · ${decl.length}</div>
     </div>`
    +(shown.length?shown.map(r=>meetCard(r)).join('')
      :none(ARCHTAB==='declined'?T('Непринятых предложений нет.','No unaccepted proposals.')
                                :T('Архив пуст.','The archive is empty.'))));

  return `<div class="stack fade" style="gap:28px">${s1}${s1b}${s2}${s3}${s4}</div>`;
}
function plural(n,one,few,many){
  const m10=n%10, m100=n%100;
  if(UILANG!=='ru') return n===1?one:few;
  if(m10===1&&m100!==11) return one;
  if(m10>=2&&m10<=4&&(m100<10||m100>=20)) return few;
  return many;
}


// ---- Explore search: real, client-side, drives the map AND the list from one source ----
// The pill used to be decorative (a "coming soon" toast). It is a live filter now: it matches the
// plan title, host, city and topics — including each topic's RUSSIAN label, so «кофе» finds a plan
// tagged "coffee". Both the pins and the sheet list read the same filtered list, so they can never
// disagree about what is on screen.
let XQ='', xSel=null, exploreCam=null, xQueried=null, xSearchT=null;
function xMatch(p,q){
  const hay=[p.title,p.who,p.area,(p.topics||[]).join(' ')].join(' ').toLowerCase();
  if(hay.indexOf(q)>=0) return true;
  return (p.topics||[]).some(t=>String(locTopic(t)).toLowerCase().indexOf(q)>=0);
}
function xVisiblePlans(){
  const q=XQ.trim().toLowerCase();
  return q ? (PUBLIC_INTENTS||[]).filter(p=>xMatch(p,q)) : (PUBLIC_INTENTS||[]);
}
// Rebuild just the sheet list + count badge, without re-rendering the screen (a re-render would tear
// the Leaflet map down and lose the camera).
function xSyncList(){
  const bd=document.getElementById('xsheetbd'); if(!bd) return;
  const list=xVisiblePlans();
  bd.innerHTML=xListHTML(list);
  bd.querySelectorAll('[data-act]').forEach(n=>n.onclick=ev=>{ ev.stopPropagation(); doAct(n.dataset.act,n.dataset); });
  const b=document.getElementById('xcount'); if(b) b.textContent=list.length;
  const cl=document.getElementById('xclr'); if(cl) cl.classList.toggle('on', !!XQ);
}
function xSearch(v){
  XQ=v||'';
  const cl=document.getElementById('xclr'); if(cl) cl.classList.toggle('on', !!XQ);
  clearTimeout(xSearchT);
  xSearchT=setTimeout(()=>{ xSyncList(); if(exploreMap) drawExploreMarkers(); }, 160);
}
// "Search this area" shows only once the camera moved meaningfully — 30% of the viewport or a full
// zoom level. Anything twitchier flickers the chip during inertia.
function xRedoCheck(){
  const el=document.getElementById('xredo'); if(!el||!exploreMap) return;
  if(!xQueried){ el.classList.remove('on'); return; }
  const b=exploreMap.getBounds();
  const span=exploreMap.distance(b.getNorthWest(), b.getNorthEast());
  const moved=exploreMap.distance(exploreMap.getCenter(), xQueried.c)>span*.30
           || Math.abs(exploreMap.getZoom()-xQueried.z)>=1;
  el.classList.toggle('on', moved);
}
function xRedo(){
  if(!exploreMap) return;
  xQueried={c:exploreMap.getCenter(), z:exploreMap.getZoom()};
  const el=document.getElementById('xredo'); if(el) el.classList.remove('on');
  const b=exploreMap.getBounds();
  const inView=(PUBLIC_INTENTS||[]).filter(p=>hasGeo(p)&&b.contains([+p.lat,+p.lon])).length;
  drawExploreMarkers(); xSyncList();
  toast(inView?T('В этой зоне: '+inView,'In this area: '+inView):T('В этой зоне пока никого','Nobody here yet'));
}
// The tapped-pin card. Injected outside render(), so its buttons are wired by hand.
// A group says how many seats are left and whether it is already happening. Never a percentage.
function groupSeats(p){ return (p.size||0)+'/'+(p.max_size||0); }
function groupBadge(p){
  return p.state==='full'      ? [T('мест нет','no seats'),'mut']
       : p.state==='confirmed' ? [T('состоится','happening'),'ok']
       :                         [T('набирается','forming'),'warn'];
}
function joinLabel(p){
  return p.mine    ? T('Ты в группе','You are in')
       : p.waiting ? T('Ты в листе ожидания','On the waitlist')
       : p.state==='full' ? T('В лист ожидания','Join waitlist')
       : T('Присоединиться','Join');
}
function showPlanCard(i){
  const p=PUBLIC_INTENTS[i], el=document.getElementById('xcard'); if(!p||!el) return;
  xSel=i;
  const tags=(p.topics||[]).slice(0,3);
  el.innerHTML='<div style="display:flex;align-items:flex-start;gap:10px">'
    +'<div style="flex:1;min-width:0"><div class="k-h3" style="margin-bottom:3px">'+esc(p.title)+'</div>'
    +'<div class="k-cap" style="color:var(--muted)">'+esc(p.who)+' · '+esc(locStr(p.when))+' · '+esc(planWhere(p))+'</div></div>'
    +'<span class="xclose" data-act="xcard-close">✕</span></div>'
    +(tags.length?'<div class="itags">'+tags.map(t=>'<span class="ktag">'+esc(locTopic(t))+'</span>').join('')+'</div>':'')
    +(p.gid?'<div class="ifoot"><span class="k-cap" style="color:var(--muted)">'+T('Участники','Members')+' · '+groupSeats(p)+'</span>'
        +'<span class="kbadge '+groupBadge(p)[1]+'">'+esc(groupBadge(p)[0])+'</span></div>':'')
    +'<button class="kbtn pri" data-act="join" data-pi="'+i+'"'+(p.mine?' disabled':'')+'>'+esc(joinLabel(p))+'</button>';
  el.classList.add('on');
  const w=document.querySelector('.xwrap'); if(w) w.classList.add('card-on');  // lifts .xctl clear of the card
  const m=document.getElementById('lmap'); if(m) m.classList.add('hasSel');    // dims the other pins
  el.querySelectorAll('[data-act]').forEach(n=>n.onclick=ev=>{ ev.stopPropagation(); doAct(n.dataset.act,n.dataset); });
  xPaintSelection();                            // class toggle -> the pin ANIMATES instead of jumping
  if(hasGeo(p)) xShowArea([+p.lat,+p.lon]);     // honest ±1.5 km area, in metres
  // lift the controls exactly clear of the real card height instead of a guessed 176px
  if(w) w.style.setProperty('--xlift', Math.round(el.offsetHeight+24)+'px');
  // Nudge the tapped pin out from behind the card — pan only; zooming on select disorients.
  if(exploreMap && hasGeo(p)){
    const pt=exploreMap.latLngToContainerPoint([+p.lat,+p.lon]);
    const safe=exploreMap.getSize().y-(el.offsetHeight+40);
    if(pt.y>safe) exploreMap.panBy([0, Math.round(pt.y-exploreMap.getSize().y*.38)],{animate:true,duration:.28});
  }
}
function xListHTML(P){
  const mineKey=cityKey(myArea());
  const groups={}, noCity=[];
  P.forEach(p=>{ const k=cityKey(p.area); if(k){ (groups[k]=groups[k]||[]).push(p); } else noCity.push(p); });
  const order=Object.keys(groups).sort((x,y)=>(x===mineKey?-1:y===mineKey?1:0)||groups[y].length-groups[x].length);
  const row=(p)=>{ const i=p._i, tags=(p.topics||[]).slice(0,4), isMine=cityKey(p.area)===mineKey;
    return '<div class="icard" data-public="'+i+'">'
      +'<div class="ihd"><div class="itl">'+esc(p.title)+'</div>'
      +(p.gid?'<span class="kbadge '+groupBadge(p)[1]+'">'+esc(groupBadge(p)[0])+' · '+groupSeats(p)+'</span>'
        :(p.verified?'<span class="kbadge ok">'+T('проверен','verified')+'</span>'
        :(isMine?'<span class="kbadge mut">'+T('твой город','your city')+'</span>':'')))+'</div>'
      +(tags.length?'<div class="itags">'+tags.map(t=>'<span class="ktag">'+esc(locTopic(t))+'</span>').join('')+'</div>':'')
      +'<div class="ifoot"><span class="k-cap" style="color:var(--muted)">'+esc(p.who)+' · '+esc(locStr(p.when))+'</span>'
      +'<span class="k-cap" style="color:var(--muted)">'+esc(planWhere(p))+'</span></div>'
      +'<div class="iacts"><button class="kbtn pri sm" data-act="join" data-pi="'+i+'"'+(p.mine?' disabled':'')
      +'>'+esc(joinLabel(p))+'</button></div></div>'; };
  if(!P.length){
    return XQ ? emptyState(T('Ничего не нашлось','Nothing found'),
                 T('Попробуй другое слово — например «кофе», «футбол» или город.','Try another word — «coffee», «football» or a city.'))
              : (exploreLoaded
                 ? emptyState(T('Пока рядом нет открытых планов','No open plans nearby yet'),
                              T('Создай интент — и Kleal предложит его людям вокруг.','Create an intent and Kleal will offer it to people around you.'))
                 : '<div class="stack" style="gap:16px"><div class="icard"><div class="k-cap" style="color:var(--muted)">'
                   +'<span class="typing3"><i></i><i></i><i></i></span> '+T('ищу планы рядом…','looking for plans nearby…')+'</div></div></div>');
  }
  return '<div class="stack" style="gap:16px">'+order.map(k=>'<div class="k-title" style="margin:16px 2px 8px">'+esc(cityLabel(k))
      +'<span style="color:var(--muted);font-weight:500"> · '+groups[k].length+'</span>'
      +(k===mineKey?'<span class="kbadge ok" style="margin-left:6px">'+T('твой город','your city')+'</span>':'')+'</div>'
    +groups[k].map(row).join('')).join('')
    + (noCity.length?'<div class="k-title" style="margin:14px 2px 6px">'+T('Город не указан','City not given')
      +'<span style="color:var(--muted);font-weight:500"> · '+noCity.length+'</span></div>'+noCity.map(row).join(''):'')
    + '</div>';
}
function scr_search(){
  // Full-screen map with floating chrome. The plan list lives in the «Планы» button and slides up as
  // a sheet, so the map keeps the whole screen. Everything is toggled imperatively (classList /
  // innerHTML), never through render(), because a re-render tears the Leaflet map down.
  const list=xVisiblePlans();
  return '<div class="xwrap fade">'
    +'<div id="lmap" class="xmap"></div>'
    +'<div class="xtop">'
      +'<div class="xpill grow">'+IC.nSearch
        +'<input id="xq" value="'+esc(XQ)+'" placeholder="'+T('Кофе, футбол, город…','Coffee, football, a city…')+'"'
        +' autocomplete="off" oninput="xSearch(this.value)">'
        +'<span class="xclr'+(XQ?' on':'')+'" id="xclr" data-act="x-clear">✕</span></div>'
      +'<div class="xpill" data-act="open-plans">'+IC.groups+'<b id="xcount">'+list.length+'</b></div></div>'
    +'<div class="xredo" id="xredo" data-act="x-redo">'+IC.nSearch+T('Искать в этой зоне','Search this area')+'</div>'
    +'<div class="xctl">'
      +'<div class="xzoom"><div class="xbtn" data-act="map-zin">+</div><div class="xbtn" data-act="map-zout">−</div></div>'
      +'<div class="xbtn acc" data-act="map-me">'+IC.compass+'</div></div>'
    +'<div class="xcard" id="xcard"></div>'
    +'<div class="xscrim" id="xscrim" data-act="close-plans"></div>'
    +'<div class="xsheet" id="xsheet"><div class="grab"></div>'
      +'<div class="hd"><span class="k-title">'+T('Планы поблизости','Plans nearby')+'</span>'
      +'<span class="xclose" data-act="close-plans">✕</span></div>'
      +'<div class="bd" id="xsheetbd">'+xListHTML(list)+'</div></div>'
    +'</div>';
}


// Conversations that exist on the SERVER, merged into the local list. Messages were delivered and
// stored correctly, but this tab only ever read local state — so the person who RECEIVED a message
// opened Messages and saw "Пока нет сообщений" while the message sat on the server addressed to them.
async function loadThreads(){
  const me=(DATA.name||'').trim(); if(!me) return;
  try{
    const r=await fetch('/api/agent/threads?self='+encodeURIComponent(me)).then(x=>x.json());
    let changed=false;
    ((r&&r.threads)||[]).forEach(t=>{
      const key=String(t.who||'').toLowerCase();
      let local=(DATA.messages||[]).find(m=>!m.kleal&&String(m.who||'').toLowerCase()===key);
      if(!local){
        local={who:t.who, kleal:false, msgs:[], cand:{name:t.who}, since:0};
        (DATA.messages=DATA.messages||[]).unshift(local); changed=true;
      }
      const prev=local.last;
      local.last=t.last; local.time=fmtTime((t.t||0)*1000)||'now';
      if(prev!==t.last) changed=true;
    });
    if(changed){ render(); saveState(); }
  }catch(e){}
  clearTimeout(_thT); _thT=setTimeout(loadThreads, 6000);
}
let _thT=null, _intT=null;
function scr_messages(){
  const list=DATA.messages||[];
  if(!list.length) return emptyState(T("Пока нет сообщений","No messages yet"),T("Когда Kleal устроит знакомство, переписки появятся здесь.","When Kleal lines up an intro, your chats show up here."));
  return `<div class="stack fade" style="padding-top:4px">${list.map((m,i)=>`<div class="card" style="padding:0">
    <div class="msgrow" data-msg="${i}"><div class="msgav ${m.kleal?'k':''}">${m.kleal?'K':esc(String(m.who||'?')[0])}</div>
    <div class="msgt"><div class="mn">${esc(m.who)}${m.kleal?'<span class="reddot"></span>':''}</div><div class="ml">${esc(m.last)}</div></div>
    <div class="msgtime">${esc(m.time)}</div></div></div>`).join('')}</div>`;
}

// Message polling must not depend on which screen is showing. Both pollers used to be kicked off from
// inside a screen's render, so a user sitting on Agent Home or Intents received nothing until they
// navigated into Messages — and after leaving a chat, not even then.
let _liveT=null;
function startLive(){
  if(_liveT) return;
  const tick=async()=>{
    const me=(DATA.name||'').trim();
    if(me){
      try{ await loadThreads(); }catch(e){}          // conversation list + previews
      if(cur==='matchchat' && matchWith){ try{ await pollThread(); }catch(e){} }
      try{ await loadInbox(); }catch(e){}            // incoming requests
    }
    _liveT=setTimeout(tick, 3000);
  };
  _liveT=setTimeout(tick, 300);
}
// ---- incoming requests from other accounts (the other half of delivery) ----
// Until this existed a request had nowhere to arrive: the sender saw «отправлено», the recipient saw
// nothing anywhere in the app.
let INBOX=[], _inboxT=null;
async function loadInbox(){
  const me=(DATA.name||'').trim(); if(!me) return;
  try{
    const r=await fetch('/api/agent/inbox?self='+encodeURIComponent(me)).then(x=>x.json());
    const next=(r&&r.requests||[]).filter(x=>x.status==='pending');   // expired/withdrawn drop out server-side
    const fresh=next.filter(n=>!INBOX.some(o=>o.id===n.id));
    INBOX=next;
    fresh.forEach(n=>addNotif('match', T('Запрос от ','Request from ')+n.from,
      n.note||((n.intent&&n.intent.title)||T('хочет встретиться','wants to meet')), null));
    if(fresh.length&&(cur==='agenthome'||cur==='messages'||cur==='notifs')) render();
  }catch(e){}
  clearTimeout(_inboxT); _inboxT=setTimeout(loadInbox, 15000);
}
const _idemKeys={};
function idemKey(k){ return (_idemKeys[k]=_idemKeys[k]||(k+'_'+Date.now().toString(36)+Math.random().toString(36).slice(2,8))); }
async function answerReq(id, decision){
  const me=(DATA.name||'').trim();
  const known=(INBOX.find(r=>r.id===id)||REQS.find(r=>r.id===id)||{});
  let res=null;
  try{
    // The key is stable per (request, decision), so a double tap or a retry after a dropped
    // connection resolves to the SAME answer instead of a second write.
    res=await fetch('/api/agent/respond',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id, decision, self:me, version:known.version,
                           idem:idemKey(id+':'+decision)})}).then(x=>x.json());
  }catch(e){ res=null; }
  if(!res){ toast(T('Нет связи — попробуй ещё раз','No connection — try again')); return; }
  INBOX=INBOX.filter(r=>r.id!==id);
  _reqGen++;                                     // same race as archiving — see loadRequests
  // The UI used to declare success no matter what came back. Now the server's state wins: an
  // acceptance that policy revoked, or one that expired, must not be shown as confirmed.
  const st=res.status||(decision==='accepted'?'accepted':'declined');
  const rq=REQS.find(x=>x.id===id); if(rq){ rq.status=st; rq.version=res.version||rq.version; }
  toast(res.ok ? (st==='accepted'?T('Принято — можно договариваться','Accepted — you can plan it')
                                 :T('Отклонено','Declined'))
     : res.error==='POLICY_CHANGED' ? T('Не получилось: настройки приватности изменились','Could not accept: privacy settings changed')
     : res.error==='EXPIRED'        ? T('Запрос истёк','This request has expired')
     : res.error==='ALREADY_RESOLVED'? T('На этот запрос уже ответили','This request was already answered')
     :                                 T('Не удалось ответить','Could not answer'));
  render(); saveState();
}
function inboxCards(){
  if(!INBOX.length) return '';
  return `<div style="display:flex;flex-direction:column;gap:10px;margin-bottom:16px">
    <div class="k-title">${T('Входящие запросы','Incoming requests')}</div>
    ${INBOX.map(r=>`<div class="card pad">
      <div class="k-h3" style="margin-bottom:2px">${esc(r.from)}</div>
      <div class="k-label" style="color:var(--muted)">${esc(r.note||((r.intent&&r.intent.title)||T('хочет встретиться','wants to meet')))}</div>
      <div class="iacts" style="margin-top:12px">
        <button class="kbtn pri sm" data-act="req-yes" data-id="${esc(r.id)}">${T('Принять','Accept')}</button>
        <button class="kbtn sec sm" data-act="req-no" data-id="${esc(r.id)}">${T('Отклонить','Decline')}</button>
      </div></div>`).join('')}</div>`;
}
// ================= Agent Home — the main landing after onboarding (Figma Flow 4) =================
// Agent Home — Figma 479:14518. Greeting, agent intro card, composer, four quick tiles and the
// "For you today" feed (real plans from /api/agent/explore, never invented ones).
// The category chip on an idea card. Derived from the SAME tile key the illustration uses, so the
// word and the picture can never disagree. «NEARBY» wins when we actually know the plan is close —
// it is a fact about distance, not a category, which is why it overrides.
const _CAT_LABEL={hiking:['ПРИРОДА','OUTDOORS'],camping:['ПРИРОДА','OUTDOORS'],walk:['ПРИРОДА','OUTDOORS'],
  surfing:['ПРИРОДА','OUTDOORS'],skiing:['ПРИРОДА','OUTDOORS'],fishing:['ПРИРОДА','OUTDOORS'],
  travel:['ПУТЕШЕСТВИЯ','TRAVEL'],art:['КУЛЬТУРА','CULTURE'],theatre:['КУЛЬТУРА','CULTURE'],
  cinema:['КУЛЬТУРА','CULTURE'],books:['КУЛЬТУРА','CULTURE'],photography:['КУЛЬТУРА','CULTURE'],
  concert:['МУЗЫКА','MUSIC'],guitar:['МУЗЫКА','MUSIC'],dj:['МУЗЫКА','MUSIC'],karaoke:['МУЗЫКА','MUSIC'],
  festival:['МУЗЫКА','MUSIC'],coffee:['КОФЕ','COFFEE'],dinner:['ЕДА','FOOD'],cooking:['ЕДА','FOOD'],
  baking:['ЕДА','FOOD'],wine:['НАПИТКИ','DRINKS'],drinks:['НАПИТКИ','DRINKS'],
  gaming:['ИГРЫ','GAMING'],chess:['ИГРЫ','GAMING'],boardgames:['ИГРЫ','GAMING'],dnd:['ИГРЫ','GAMING'],
  startups:['СТАРТАПЫ','STARTUPS'],coding:['ТЕХ','TECH'],design:['ДИЗАЙН','DESIGN'],
  language:['ЯЗЫКИ','LANGUAGE'],meditation:['ВЕЛНЕС','WELLNESS'],yoga:['ВЕЛНЕС','WELLNESS'],
  pets:['ПИТОМЦЫ','PETS'],fashion:['СТИЛЬ','FASHION'],dating:['ЗНАКОМСТВА','DATING']};
function ideaCat(p, key){
  // A real distance beats a category word: «рядом» is the thing a person actually acts on.
  const d=String(p.dist||'');
  const km=parseFloat(d);
  if(!isNaN(km) && km<=3) return [T('РЯДОМ','NEARBY'), true];
  const L=_CAT_LABEL[key];
  if(L) return [T(L[0],L[1]), false];
  return [T('СПОРТ','SPORT'), false];   // the tile atlas is sport-heavy; social is its own fallback
}
function ideaSub(p){
  const bits=[];
  if(p.when) bits.push(locStr(p.when));
  if(p.area) bits.push(p.area); else if(p.dist) bits.push(p.dist);
  return bits.join(' · ');
}
// Split a free-text "when" into a date part and a time part for the two-icon meta row. The matcher
// hands back whatever the host wrote ("Sat, 24 June · 9pm", "tonight", "this weekend"), so this is a
// best-effort split, not a parser: no recognisable time → the whole string sits after the calendar.
function ideaWhen(p){
  const raw=String(p.when||'').trim();
  if(!raw) return {date:T('Гибко','Flexible'), time:''};
  const s=locStr(raw);
  // Only an explicit clock time (13:00 / 9:00 PM / 8pm) is peeled into its own chip. Russian
  // time-of-day words (вечером, утром…) are left inline in the date phrase — matching them here
  // once split "сего·дня" apart, since «дня» is a substring of «сегодня».
  const m=s.match(/(\d{1,2}[:.]\d{2}\s*(?:AM|PM|am|pm)?|\d{1,2}\s*(?:AM|PM|am|pm))/);
  if(m){
    const time=m[0].trim();
    const date=s.slice(0,m.index).replace(/[·,\s]+$/,'').trim() || s;
    return {date, time};
  }
  return {date:s, time:''};
}
// The going pill: real `going` count with placeholder attendee glyphs (the product has no attendee
// photos — the neutral user glyph is the honest stand-in the mockup itself uses), overflow as +N.
function goingPill(n){
  n=parseInt(n,10)||0; if(n<=0) return '';
  const shown=Math.min(n,3), extra=n-shown;
  let a=''; for(let i=0;i<shown;i++) a+=`<span class="av">${IC.person}</span>`;
  if(extra>0) a+=`<span class="av ct">+${extra}</span>`;
  return `<div class="gpill"><div class="avg">${a}</div><span>${n} ${T('идут','going')}</span></div>`;
}
let IDEA_I=0;
// Placeholder feed shown while the matcher is being rebuilt and returns nothing yet — TEMPORARY demo
// content, replaced the moment real plans/invites arrive. Remove MOCK_* to go back to the empty state.
const MOCK_PLANS=[
  {title:'Sunset Rooftop Party', who:'Marco', when:'Sat, 24 June 9:00 PM', area:'Gràcia rooftop', topics:['music'], dist:'15 min', going:8},
  {title:'Утренний бег у моря', who:'Elena', when:'завтра 8:00', area:'Barceloneta', topics:['running'], dist:'2 км', going:5},
  {title:'Испанский за кофе', who:'Pau', when:'today 18:00', area:'El Born', topics:['language','coffee'], dist:'1.2 км', going:3},
];
const MOCK_INVITE={id:'mock1', from:'Anna', age:28, status:'pending', photo:'assets/match-anna.jpg',
  intent:{when:'Today 18:00', area:'Gràcia rooftop', title:'Coffee'}};
function scr_agenthome(){
  if(!exploreLoaded) loadExplore();          // real plans behind "New ideas for you"
  const nm=(DATA.name||'there').split(' ')[0];
  const plans=((DATA.plans&&DATA.plans.length)?DATA.plans:MOCK_PLANS).slice(0,5);
  if(IDEA_I>=plans.length) IDEA_I=0;
  const ideaCard=(p,i)=>{
    const key=tileKeyFor((p.topics||[]).join(' ')||String(p.title||''));
    const [cat,near]=ideaCat(p,key);
    const host=String(p.who||'').trim();
    // DATA.saved holds objects ({name, band, km…}), not strings — comparing to the raw name meant
    // the heart saved correctly and then never showed it.
    const saved=(DATA.saved||[]).some(x=>String((x&&x.name)||x)===host);
    const w=ideaWhen(p);
    const loc=[p.area, p.dist].filter(Boolean).join(' · ');
    const foot=goingPill(p.going) || (host
      ? `<div class="gpill"><span class="hav">${esc(host.slice(0,1).toUpperCase())}</span><span>${esc(host)} ${T('организует','is hosting')}</span></div>`
      : '');
    // Cover is a photo (Figma 1615-21279). The illustration atlas stays as the fallback for any
    // plan whose photo fails to load, so a card is never a blank grey box.
    return `<div class="idea ${i===IDEA_I?'on':''}" data-act="join-plan" data-pi="${i}">
      <div class="cov"><img src="assets/event-cover.jpg" alt="" onerror="this.remove()">${TILE_SVG[key]||TILE_SVG.social}
        <div class="bm ${saved?'on':''}" data-act="cand-save" data-n="${esc(host)}">${IC.bookmark}</div></div>
      <div class="bd">
        <div class="ti">${esc(p.title||'')}</div>
        <div class="mt">${IC.calen}<span>${esc(w.date)}</span>${w.time?`${IC.clock}<span>${esc(w.time)}</span>`:''}</div>
        ${loc?`<div class="mt">${IC.pin}<span>${esc(loc)}</span></div>`:''}
        ${foot?`<div class="ft">${foot}</div>`:''}
      </div></div>`;
  };
  const ideas = plans.length
    ? `<div class="icar" id="icar">${plans.map(ideaCard).join('')}</div>
       <div class="idots">${plans.map((_,i)=>`<i class="${i===IDEA_I?'on':''}"></i>`).join('')}</div>`
    : `<div class="k-cap" style="color:var(--muted);padding:4px 2px">${T(
        'Пока идей нет — опиши, чего хочешь, и я поищу.',"No ideas yet — tell me what you want and I'll look.")}</div>`;
  // The invite row shows the FIRST pending request; the rest stay in the full list behind it.
  // The first pending invite becomes the rich "match" card from Figma 1615-21279: photo, name+age,
  // green Match badge, when/where meta, "Review invite". The avatar binds to a real photo when the
  // person has one (the product has none yet), else an initial disc — never a stock face for everyone.
  const inv=(INBOX&&INBOX.length)?INBOX[0]:MOCK_INVITE;
  const ioi=(inv&&inv.intent)||{};
  const mWhen=inv?locStr(ioi.when||ioi.time||''):'';
  const mWhere=inv?(ioi.area||ioi.place||''):'';
  const mAge=(inv&&inv.age)?', '+inv.age:'';
  const mPhoto=(inv&&inv.photo)||'';
  const matchCard = inv ? `<div class="emeet" data-act="go-inbox">
      <div class="ava${mPhoto?'':' init'}">${mPhoto?`<img src="${esc(mPhoto)}" alt="">`:esc(String(inv.from||'?').slice(0,1).toUpperCase())}</div>
      <div class="mbd">
        <div class="mtop">
          <div class="mt-title">${esc(inv.from||'')}${mAge}</div>
          <div class="sbadge ok">${T('Мэтч','Match')}</div></div>
        ${(mWhen||mWhere)?`<div class="mmeta">${
          mWhen?`<span>${IC.clock}${esc(mWhen)}</span>`:''}${
          mWhere?`<span>${IC.pin}${esc(mWhere)}</span>`:''}</div>`
          :`<div class="mmeta"><span>${esc(String(inv.note||T('хочет встретиться','wants to meet')).slice(0,44))}</span></div>`}
        <button class="mbtn" data-act="go-inbox">${T('Посмотреть приглашение','Review invite')}</button>
      </div></div>` : '';
  return `<div class="ah2 fade">
    <div class="ahd"><div class="nm serif">${T('Привет','Hey')}, ${esc(nm)} 👋</div>
      <div class="bell" data-act="notif">${IC.bell}${unreadNotifs()?'<span class="dot"></span>':''}</div></div>
    <div class="body">
      ${IS_DEMO?`<div class="kinfo">${IC.info}<div>${T(
        'Это демо-профиль. Пройди онбординг, чтобы Kleal искал для тебя.',
        'This is a sample profile. Complete onboarding so Kleal searches for you.')}
        <span style="color:var(--primary);font-weight:600;cursor:pointer" data-act="go-onboarding"> ${T('Начать','Start')} →</span></div></div>`:''}
      <div style="flex:none;display:flex;flex-direction:column;gap:10px">
        <div class="seclbl2">${IC.spark}${T('Новые идеи для тебя','New ideas for you')}</div>
        ${ideas}
      </div>
      ${inv ? matchCard : ((PLAN&&PLAN.confirmed)?`<div class="emeet" data-act="meet-open">
        <div class="ava">${IC.coffee}</div>
        <div class="mbd">
          <div class="mtop">
            <div class="mt-title">${T('Кофе и разговор','Coffee & conversation')}</div>
            <div class="sbadge ok">${T('Подтверждено','Confirmed')}</div></div>
          <div class="mmeta">
            <span>${IC.clock}${esc(slotText())}</span>
            <span>${IC.pin}${esc(placeText())}</span></div>
          <button class="mbtn" data-act="meet-open">${T('Открыть детали','Open details')}</button>
        </div></div>`:'')}
    </div>
    <div class="bcard">
      <div class="brow">
        <div class="bav">${masc('primary')}</div>
        <div class="fld">
          <input id="ainput" placeholder="${T('Чем хочешь заняться?','What do you feel like doing?')}" autocomplete="off">
          <span class="mic">${IC.mic}</span></div>
      </div>
      <div class="hist" data-act="talk-buddy">${IC.chat}${T('Открыть историю разговоров','Open conversation history')} ››</div>
    </div>
  </div>`;
}

// Which card is centred — drives the dots and the raised/dimmed state. Scroll-driven, so it stays
// truthful when the user flicks rather than taps.
function wireIdeaCarousel(){
  const el=document.getElementById('icar'); if(!el) return;
  let t=null;
  el.onscroll=()=>{ clearTimeout(t); t=setTimeout(()=>{
    const cards=[...el.children]; if(!cards.length) return;
    const mid=el.scrollLeft+el.clientWidth/2;
    let best=0, bd=1e9;
    cards.forEach((c,i)=>{ const cm=c.offsetLeft+c.offsetWidth/2; const d=Math.abs(cm-mid);
      if(d<bd){ bd=d; best=i; } });
    if(best!==IDEA_I){ IDEA_I=best;
      cards.forEach((c,i)=>c.classList.toggle('on',i===best));
      const dots=document.querySelectorAll('.idots i');
      dots.forEach((d,i)=>d.classList.toggle('on',i===best)); }
  }, 60); };
}

// ---------------- flow logic: every step is backed by a real service ----------------
// composer  -> POST /api/buddy/intent-build   (understands free text, asks for what's missing)
// summary   -> the intent that build returned, shown for confirmation
// searching -> POST /api/agent/match          (the ranking engine)
// few       -> re-runs the search with the adjustment the user picked
function flowStart(text){
  flowInit(String(text||'').trim());
  cur='reqcomposer'; render();
  if(FLOW.text) flowSay(FLOW.text, true);
  else setTimeout(()=>{const e=document.getElementById('flowinp'); if(e)e.focus();},60);
}
// One back-navigation rule for every screen. The flow screens each render their own back button,
// and it used to call a handler that only knew the first five — on every later screen the button
// was inert. A single map plus a visited-stack fallback means back always goes somewhere sensible.
const BACK_MAP = {
  reqcomposer:'agenthome', clarify:'reqcomposer', summary:'clarify',
  searching:'summary', fewmatches:'summary',
  bestfit:'agenthome', options:'bestfit', candprofile:'bestfit',
  sendreq:'candprofile', waiting:'sendreq', mutual:'waiting', suggestion:'mutual',
  picktime:'suggestion', pickplace:'picktime', awaiting:'pickplace', planok:'awaiting',
  meetstate:'agenthome', mymeetup:'meetstate',
  notifs:'agenthome',
  help:'settings',
  persona:'social',        // the test carries its own back arrow (kbar) — send it home, not to agenthome
};
let NAVSTACK=[];
function navTo(next){ if(cur!==next){ NAVSTACK.push(cur); if(NAVSTACK.length>20) NAVSTACK.shift(); } cur=next; render(); }
function flowBack(){
  if(SHEET){ SHEET=null; render(); return; }
  if(cur==='reqcomposer') FLOW=null;
  if(cur==='candprofile') CAND=null;
  let prev=BACK_MAP[cur];
  // don't bounce to a screen that has nothing to show
  if((prev==='bestfit'||prev==='options')&&!(FLOW&&FLOW.res&&FLOW.res.length)) prev='agenthome';
  if(prev==='candprofile'&&!CAND) prev=(FLOW&&FLOW.res&&FLOW.res.length)?'bestfit':'agenthome';
  if(!prev) prev=NAVSTACK.pop()||'agenthome';
  cur=prev; render();
}
// The agent's reply arrives complete. It used to stream token by token over SSE, which showed the
// first token in ~0.2s instead of ~5-7s — but a bubble that rewrites itself while you are reading it
// is harder to read than a short wait, and the builder can discard a draft mid-flight and start over,
// so the text could visibly reset. The server still accepts stream:true; this client no longer asks.
// Null on any transport failure, so flowSay's existing "connection lost" branch fires unchanged.
// matchProfile() ships every interest, including used===false. For anything the user will READ BACK
// as a suggestion, the opt-out has to be honoured.
function matchProfileForHints(){
  const p=matchProfile(), off={};
  (DATA.interests||[]).forEach(i=>{ if(i&&i.used===false) off[i.name]=1; });
  p.interests=(p.interests||[]).filter(n=>!off[n]);
  return p;
}
async function intentBuild(messages, profile){
  try{
    const resp=await fetch('/api/buddy/intent-build',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({messages, profile})});
    if(!resp.ok) return null;
    return await resp.json();
  }catch(e){ return null; }
}
async function flowSay(text, fromSeed){
  text=String(text||'').trim(); if(!text||FLOW.busy) return;
  if(!fromSeed){ const el=document.getElementById('flowinp')||document.getElementById('flowinp2'); if(el)el.value=''; }
  FLOW.text=text;
  const meIdx=FLOW.msgs.push({who:'me',text:text,t:Date.now()})-1;
  FLOW.busy=true; render();
  let r=null;
  try{
    // Small talk must not reach the intent builder. Greeting Kleal and then asking it what dividends
    // are used to leave both turns in the history, so the builder read them as context and produced an
    // intent whose vibe was "bonds, finance, investing, economy". Turns already answered
    // conversationally carry `chat` and the SERVER hides them from the builder — but they are still
    // SENT, because they are the conversation. Dropping them here is what made every follow-up look
    // like a first message: "что такое X" then "расскажи детальнее" arrived alone, and Kleal greeted
    // the user again and asked what they meant (reproduced 4/4 on the pod, 0/4 with the history sent).
    const forBuilder=FLOW.msgs.map(m=>({role:m.who==='me'?'user':'assistant',content:m.text,chat:!!m.chat}));
    r=await intentBuild(forBuilder, matchProfileForHints());
  }catch(e){ r=null; }
  FLOW.busy=false;
  if(!r||!r.reply){ FLOW.lastFailed=true;
    FLOW.msgs.push({who:'ag',text:T('Связь пропала — повтори, пожалуйста.','I lost the connection — say that again?'),hints:[],t:Date.now()}); render(); return; }
  FLOW.lastFailed=false;
  if(r.conversational && FLOW.mode==='intent'){
    // This conversation exists to build an intent, so an off-topic turn is steered back once and then
    // pointed at the buddy chat, where conversation belongs.
    FLOW.msgs[meIdx].chat=true;
    const said=FLOW.msgs.filter(m=>m.chat&&m.who==='ag').length;
    FLOW.msgs.push({who:'ag',chat:true,hints:[],t:Date.now(),
      text: said===0
        ? T('Здесь я собираю интент. Напиши, чем хочешь заняться — например «сходить на джаз в пятницу».',
             "This chat builds an intent. Tell me what you'd like to do — e.g. \u201cgo to a jazz gig on Friday\u201d.")
        : T('Про остальное поговорим в обычном чате с Kleal. Здесь нужен план: чем, когда и с кем.',
             "For anything else, talk to Kleal in the normal chat — this one needs the plan: what, when and with whom.")});
    render(); return;
  }
  if(r.conversational){
    // Kleal is a companion you can actually talk to, so its conversational answer is shown as-is.
    // Steering every off-topic turn back to "describe a plan" turned the agent into a form; the way
    // into an intent is a signal in the conversation or the «+ Создать интент» button in the bar.
    // Marking the turn `chat` keeps it out of the builder's context — greeting Kleal and then asking
    // about bonds used to produce an intent whose vibe was "finance, economy".
    FLOW.msgs[meIdx].chat=true;
    FLOW.msgs.push({who:'ag',text:r.reply,chat:true,hints:okHints(r.hints),t:Date.now()});
    render(); return;
  }
  // the request is the first turn that actually asked for something — never the greeting that opened
  // the conversation, which is what used to end up quoted as «Запрос: привет»
  if(!FLOW.request) FLOW.request=text;
  FLOW.msgs.push({who:'ag',text:r.reply,hints:okHints(r.hints),t:Date.now()});
  if(r.ready&&r.intent){                       // enough detail -> one clarification, then the summary
    FLOW.intent=r.intent;
    intentPrefill();                           // a day named in the dialog must light its chip, not be re-asked
    // scr_summary already prefers s.title over the raw request — nothing ever put one there, so
    // the card was headed with the sentence the person typed. That reads fine for «хочу поиграть в
    // футбол», and not at all for «я хочу с кем-то об этом поговорить», which names nothing.
    FLOW.summary={request:FLOW.request||FLOW.text, title:r.intent.title||null, format:r.intent.format,
                  vibe:(r.intent.tags||[]).filter(t=>t!=='meet').join(', ')||null};
    // Only the district question is left when the dialog already gave both the day and the time of
    // day — and the district is optional, so there is nothing the clarify screen MUST ask. Skip it.
    cur='fmt';   // Figma flow: format -> group size -> details, before the summary
  }
  render();
}
function flowToSummary(){
  if(!FLOW.intent){ FLOW.intent={topics:[],type:'social',role:'meet',mode:'offline'}; }
  FLOW.summary=FLOW.summary||{request:FLOW.request||FLOW.text};
  cur='summary'; render();
}
// An online plan (dota, a call) has no district and no radius — it happens over the internet. The
// clarify screen, the summary and the search itself all key off this instead of always assuming a
// place. mode comes from the buddy (esports/online cues -> "online"); default is offline.
function flowOnline(){ return !!(FLOW && FLOW.intent && FLOW.intent.mode==='online'); }
// ---- age range: what the dial SHOWS vs what the search actually carries ----------------------
// These two were conflated and that is why the age filter did nothing. The dial displays 18-28 as
// a placeholder, but only the handle a person actually dragged was stored — so after moving one
// handle the screen read "25-28" while FLOW.ageB was still undefined, flowIntent()'s
// `if(ageA&&ageB)` was false, and the request went out with NO age filter at all. The dial showed
// a range the system did not have.
//
// ageEnds()  — the two numbers to DRAW (placeholders included), never a promise that a filter is set.
// ageRange() — the range actually chosen, or null. Null must stay possible: a dial nobody touched
//              must not silently impose 18-28 on the search.
function ageEnds(){
  const it=(FLOW&&FLOW.intent)||{};
  return [(FLOW&&FLOW.ageA)||it.minAge||18, (FLOW&&FLOW.ageB)||it.maxAge||28];
}
function ageRange(){
  if(FLOW&&FLOW.ageA&&FLOW.ageB) return [Math.min(FLOW.ageA,FLOW.ageB), Math.max(FLOW.ageA,FLOW.ageB)];
  const it=(FLOW&&FLOW.intent)||{};                 // re-opened saved intent: the range lives on it
  if(it.minAge&&it.maxAge) return [it.minAge, it.maxAge];
  return null;
}
function flowIntent(){
  // merge the clarification answers into the intent the buddy compiled
  const it=Object.assign({}, FLOW.intent||{});
  if(!it.topics||!it.topics.length) it.topics=(FLOW.text||'').split(/[,\s]+/).filter(w=>w.length>2).slice(0,4);
  // 'tonight'/'20-22' are the OLD chip keys; a state saved before the day/time split still carries them,
  // so they stay in these maps as aliases — dropping them would make a restored intent time undefined.
  const whenTxt={today:'today',tonight:'today',tomorrow:'tomorrow',weekend:'this weekend',pick:'Flexible'}[FLOW.when];
  const timeTxt={morning:'morning',afternoon:'afternoon',evening:'evening','20-22':'evening',late:'late evening'}[FLOW.time];
  it.time=[whenTxt,timeTxt].filter(Boolean).join(' ')||it.time||'Flexible';
  // The ranker HAS a minAge/maxAge gate and enforces it (verified against the live pool: 20-25
  // returns 21-25, 60-75 returns 61). It just never received a range, so it returned every age.
  const _age=ageRange();
  if(_age){ it.minAge=_age[0]; it.maxAge=_age[1]; }
  it.mode=it.mode||'offline';
  if(it.mode==='online'){
    it.place=T('Онлайн','Online');                       // no district, no radius — it's over the net
  } else {
    if(FLOW.district) it.place=labelOf(DIST_OPTS(),FLOW.district);
    if(FLOW.adjust==='radius') it.radiusKm=(it.radiusKm||15)+5;
    if(FLOW.adjust==='wide'){ it.radiusKm=(it.radiusKm||15)+15; it.broadConsent=true; it.adjacentAllowed=true; }
  }
  return it;
}
// ---- «люди не меняются» ----------------------------------------------------------------------
// The ranker is deterministic on purpose, so the top of its list was the same eight people every
// time, out of ~250 who qualified. We remember who this person has already been shown FOR THIS
// QUERY and send it along; the engine then pages down the same unchanged ranking instead of
// re-serving its head. Kept on the client because a search must not become a writer of matching's
// store, and because the client is the only side that knows what was actually rendered.
// Bounded hard: DATA rides into that store wholesale via saveState(), so this must not grow.
const SEEN_MAX_SIGS=40, SEEN_MAX_NAMES=200, SEEN_TTL=7*864e5;
function sigOf(it){
  it=it||{};
  // Only the fields that decide SCOPE. Not the wording: «кофе сегодня» and «выпить кофе сегодня»
  // normalise to the same topics and must continue the same paging, which is the reported case.
  const parts=[(it.topics||[]).map(t=>String(t).toLowerCase()).sort().join('+'),
    it.type||'', it.role||'', it.mode||'', it.time||'', it.format||'',
    (it.requiredLanguages||[]).map(String).sort().join('+'),
    it.radiusKm||'', it.minAge||'', it.maxAge||'', it.verifiedOnly?1:0, it.adjacentAllowed===false?0:1];
  const s=parts.join('|'); let h=0;
  for(let i=0;i<s.length;i++){ h=((h<<5)-h+s.charCodeAt(i))|0; }
  return 's'+(h>>>0).toString(36);
}
function seenPrune(){
  const m=DATA.seen&&typeof DATA.seen==='object'?DATA.seen:{}; const now=Date.now();
  Object.keys(m).forEach(k=>{ if(!m[k]||!m[k].t||now-m[k].t>SEEN_TTL) delete m[k]; });
  const keys=Object.keys(m).sort((a,b)=>(m[b].t||0)-(m[a].t||0));
  keys.slice(SEEN_MAX_SIGS).forEach(k=>delete m[k]);
  DATA.seen=m; return m;
}
function seenGet(sig){ const m=seenPrune(); return (m[sig]&&m[sig].n)||[]; }
function seenAdd(sig,names){
  const m=seenPrune(); const e=m[sig]||{n:[],t:Date.now()};
  (names||[]).forEach(n=>{ if(n&&e.n.indexOf(n)<0) e.n.push(n); });
  e.n=e.n.slice(-SEEN_MAX_NAMES); e.t=Date.now(); m[sig]=e; DATA.seen=m; saveState();
}
function seenClear(sig){ const m=seenPrune(); delete m[sig]; DATA.seen=m; saveState(); }

// A second, lighter fetch path: «показать ещё» appends in place. It deliberately skips the 2.6s
// search screen — that animation is right for starting a search and wrong for extending one.
async function flowMore(){
  const it=flowIntent(), sig=sigOf(it);
  FLOW.moreBusy=true; render();
  let r=null;
  try{
    r=await fetch('/api/agent/match',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({intent:it, profile:matchProfile(), ctx:{self:DATA.name||'', seen:seenGet(sig)}})}).then(x=>x.json());
  }catch(e){ r=null; }
  FLOW.moreBusy=false;
  const fresh=((r&&r.candidates)||[]).filter(c=>c&&c.name&&!(FLOW.res||[]).some(x=>x.name===c.name));
  FLOW.page=(r&&r.page)||FLOW.page||{};
  if(!fresh.length){ FLOW.page.exhausted=true; render(); return; }
  FLOW.res=(FLOW.res||[]).concat(fresh);
  seenAdd(sig, fresh.map(c=>c.name));
  if(curIntent){ curIntent.candidates=FLOW.res; saveCurIntent(); }
  render();
}
async function flowSearch(isRetry){
  FLOW.steps=0; cur='searching'; render();
  const _fsIntent=flowIntent(), _fsSig=sigOf(_fsIntent), _fsSeen=seenGet(_fsSig);
  const tick=setInterval(()=>{ if(FLOW.steps<3){ FLOW.steps++; render(); } }, 650);
  const minShow=new Promise(res=>setTimeout(res, 2600));   // the search screen is part of the design
  let r=null;
  try{
    r=await fetch('/api/agent/match',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({intent:_fsIntent, profile:matchProfile(), ctx:{self:DATA.name||'', seen:_fsSeen}})}).then(x=>x.json());
  }catch(e){ r=null; }
  await minShow;
  clearInterval(tick); FLOW.steps=4;
  let cands=(r&&r.candidates)||[];
  FLOW.page=(r&&r.page)||{};
  // Running the same search again is an explicit act — it is the exact thing that was reported as
  // broken — so it advances. If the engine has nobody new left, fall back to the head of the list
  // rather than showing an empty screen, and say so.
  if(_fsSeen.length && cands.length && cands.every(c=>_fsSeen.indexOf(c.name)>=0)){
    FLOW.page.exhausted=true;
  }
  FLOW.sig=_fsSig; FLOW.resumed=_fsSeen.length>0;
  // The exact search found nobody and the engine broadened to related activities. Say so honestly
  // on the results screen — never present broadened people as a match for what was asked.
  FLOW.broadened=!!(r&&r.broadened);
  const _fb=(r&&r.fallback)||{};
  FLOW.fbNote=_fb.note||_fb.note_ru||'';
  FLOW.fbRelated=(typeof _fb.relatedCount==='number')?_fb.relatedCount:null;
  if(cands.length) seenAdd(_fsSig, cands.map(c=>c.name));
  FLOW.res=cands;
  persistIntent();                 // the tab must show what Kleal is actually working on
  render();
  setTimeout(()=>{
    if(cands.length){                          // results -> the Figma results screens
      curIntent={ title:(FLOW.intent&&FLOW.intent.title)||FLOW.request||FLOW.text||T('Новый интент','New plan'),
                  tags:(flowIntent().topics||[]), query:FLOW.request||FLOW.text, intent:flowIntent(),
                  candidates:cands, confidence:cands[0]&&cands[0].score, spec:[], status:'searching' };
      saveCurIntent();
      cur=(cands.length>=3?'bestfit':'options'); render();
    } else {
      cur='fewmatches'; render();              // too few -> offer the adjustments from the design
      if(isRetry&&!cands.length) toast(T('Пока никого — попробуй расширить поиск','No one yet — try widening the search'));
    }
  }, 600);
}

// ================= Figma flow: Agent Home → request → clarification → summary → searching =========
// One shared state object; every screen reads and writes it, and each step talks to the real
// backend (buddy for language understanding, matching for the search itself).
let FLOW = null;
// One chat screen, two modes. 'buddy' is the companion you can talk to about anything; 'intent' is
// the dedicated intent-building conversation the «+ Создать интент» button opens. The button used to
// jump straight to the final summary form, skipping the conversation entirely.
function flowInit(seed, mode){
  FLOW = { text:seed||'', msgs:[], when:null, time:null, district:null, mode:mode||'buddy',
           intent:null, summary:null, steps:0, res:null, adjust:'radius', groups:true,
           hintSeed:(new Date()).getDate(), busy:false };
}
// «+ Создать интент» — a fresh conversation whose only job is to build one.
function intentStart(){
  flowInit('', 'intent');
  FLOW.msgs=[{who:'ag',t:Date.now(),text:T(
    'Давай соберём интент. Опиши, чем хочешь заняться — например «сходить на джаз в пятницу» или «найти напарника в зал».',
    "Let's build an intent. Tell me what you'd like to do — e.g. \u201cgo to a jazz gig on Friday\u201d or \u201cfind a gym partner\u201d.")}];
  cur='reqcomposer'; render();
  setTimeout(()=>{const e=document.getElementById('flowinp'); if(e)e.focus();},60);
}
const FLOW_HINTS = () => [
  T('Найти компанию для кофе и разговора','Find company for coffee & good talk'),
  T('Познакомиться с людьми из творческой среды','Meet new people from the creative field'),
  T('Спокойные встречи без суеты','Low-key meetups in a relaxed setting')];
// ---- Personal conversation hints ------------------------------------------------------------
// Layer 1 is the model's own, carried by the SAME turn that produced the reply — no second call, so
// a chip can never arrive seconds after the message it belongs to. Layers 2-4 are deterministic and
// exist because turn one has no call yet, transport fails, and the 70B drops keys. The row must
// never be short, never empty, never a loading state.
function okHints(v){
  const ru=(UILANG==='ru');
  return (Array.isArray(v)?v:[]).map(x=>String(x||'').trim())
    .filter(x=>x && x.length<=48 && (!ru || /[а-яё]/i.test(x))).slice(0,3);
}
// The interests a person actually carries, as coarse keys — so a chip can be about what they DO
// («поиграть в доту») rather than a category name («игры»).
const _HINT_KEYS=[
  ['dota',    /dota|дот/],
  ['games',   /\bgam|игр|valorant|counter|cs2|league|fifa|фифа|консол/],
  ['startup', /startup|стартап|\bai\b|\bии\b|tech|техно|product|продукт|business|бизнес|венчур/],
  ['coffee',  /coffee|кофе|cafe|кафе/],
  ['walk',    /walk|прогул|stroll|hik|поход/],
  ['run',     /run|jog|бег|марафон/],
  ['football',/football|soccer|футбол/],
  ['gym',     /gym|fitness|зал|тренир|фитнес/],
  ['music',   /music|музык|jazz|джаз|concert|концерт|гитар/],
  ['art',     /\bart|искус|design|дизайн|museum|музе|выстав|фото|photo/],
  ['books',   /book|книг|read|чтен|литерат/],
  ['lang',    /language|язык|spanish|испан|english|англ|serbian|серб|француз|french/],
  ['food',    /food|еда|dinner|ужин|cook|готов|ресторан|restaurant|бранч|brunch/],
  ['film',    /movie|film|кино|сериал|series/]];
// Recipes are ordered by how specific they are; a two-key recipe fires only when the person really
// has both, which is what turns «прогулки» + «кофе» into one natural plan instead of two chips.
const _HINT_RECIPES=()=>[
  [['walk','coffee'], T('Пройтись по городу и выпить кофе','Take a walk and grab a coffee')],
  [['run','coffee'],  T('Пробежаться утром и выпить кофе','Morning run, then coffee')],
  [['startup','coffee'],T('Обсудить стартапы за кофе','Talk startups over coffee')],
  [['dota'],          T('Поиграть в Доту вечером','Play some Dota tonight')],
  [['startup'],       T('Обсудить новые стартапы и технологии','Talk new startups and tech')],
  [['games'],         T('Собрать пати на вечер','Put a party together tonight')],
  [['coffee'],        T('Выпить кофе и поговорить','Grab a coffee and talk')],
  [['walk'],          T('Пройтись по городу и поговорить','Take a walk and talk')],
  [['run'],           T('Пробежаться вместе утром','Go for a morning run together')],
  [['football'],      T('Собрать игру в футбол','Get a football game together')],
  [['gym'],           T('Сходить в зал вместе','Hit the gym together')],
  [['music'],         T('Сходить на живую музыку','Go see some live music')],
  [['art'],           T('Сходить на выставку','Go to an exhibition')],
  [['books'],         T('Обсудить книгу за кофе','Talk books over coffee')],
  [['lang'],          T('Попрактиковать язык за ужином','Practise a language over dinner')],
  [['food'],          T('Поужинать в новом месте','Try dinner somewhere new')],
  [['film'],          T('Сходить в кино','Go see a film')]];
function hintKeys(){
  const names=(DATA.interests||[]).filter(i=>i&&i.name&&i.used!==false)
    .map(i=>String(i.name).toLowerCase());
  const have={}, order=[];
  names.forEach(n=>_HINT_KEYS.forEach(p=>{ if(p[1].test(n)&&!have[p[0]]){ have[p[0]]=n; order.push(p[0]); } }));
  return {have, order, names};
}
// Deterministic: no Math.random, so the row is stable across re-renders. Each key is spent once, so
// «кофе» cannot show up in three chips.
function seedHints(){
  const K=hintKeys();
  if(!Object.keys(K.have).length && !K.names.length) return [];
  const out=[], spent={};
  _HINT_RECIPES().forEach(r=>{
    if(out.length>=3) return;
    if(r[0].some(k=>!K.have[k]||spent[k])) return;
    r[0].forEach(k=>{ spent[k]=1; });
    out.push(r[1]);
  });
  // A free-typed interest we have no recipe for is still personal — name it plainly.
  K.names.forEach(n=>{ if(out.length<3 && !_HINT_KEYS.some(p=>p[1].test(n)))
    out.push(T('Найти людей, которым тоже интересно: '+locTopic(n),'Find people who are also into '+locTopic(n))); });
  return out;
}
function hintsFor(m){
  const out=[], seen={}, push=x=>{ x=String(x||'').trim(); if(x&&!seen[x]&&out.length<3){seen[x]=1;out.push(x);} };
  // The profile leads. These chips open the conversation, so they should name things this person
  // actually does; the model's own suggestions were true but generic («Хочу познакомиться»).
  seedHints().forEach(push);
  if(out.length<3) okHints(m&&m.hints).forEach(push);
  if(out.length<3) FLOW_HINTS().forEach(push);
  return out.slice(0,3);
}

// "Когда" is the DAY, "Время" is the time of day — they must be orthogonal. 'tonight' baked an
// evening into the day group, so "Сегодня вечером" sat above a "Утро" chip you could also pick.
// The evening shortcut is not lost: Сегодня + Вечер says the same thing and cannot contradict itself.
const WHEN_OPTS = () => [['today',T('Сегодня','Today')],['tomorrow',T('Завтра','Tomorrow')],
  ['weekend',T('На выходных','This weekend')],['pick',T('Выбрать дату…','Pick a date…')]];
// '20:00–22:00' was one exact clock range among three vague words; 'Вечер' matches its neighbours.
const TIME_OPTS = () => [['morning',T('Утро','Morning')],['afternoon',T('День','Afternoon')],
  ['evening',T('Вечер','Evening')],['late',T('Поздно','Late')]];
const DIST_OPTS = () => [['center',T('Центр','Center')],['west',T('Запад','West')],['east',T('Восток','East')],
  ['south',T('Юг','South')],['beach',T('Пляж','Beach')]];
const STEP_LABELS = () => [T('Проверяю время и район','Checking time & district'),
  T('Ищу подходящие форматы','Scanning matching formats'),
  T('Собираю лучшие варианты','Collecting the best options'),
  T('Проверяю доступность','Verifying availability')];

function kbar(cta){
  // In the buddy chat the pill OPENS the intent conversation; inside that conversation it becomes the
  // way to finish it, and only once there is something to finish.
  // `cta` is passed ONLY by the chat screen. The intent-mode branch used to ignore it, so the pill
  // appeared on all 16 screens that share this bar — clarify, summary, searching, results — where it
  // means nothing and duplicates their own buttons.
  const intentMode=(FLOW&&FLOW.mode==='intent');
  const show=!!cta && (!intentMode || (FLOW.msgs||[]).some(m=>m.who==='me'));
  // In intent mode the design puts «Все интенты» here — navigation to the list, not a finish button.
  // The way to finish is the conversation itself (the agent turns the request into a plan), so the
  // pill no longer competes with it. `flow-done` stays reachable from the summary screen's own CTA.
  if(intentMode) return `<div class="kbar" style="justify-content:space-between">
  <div class="kback" data-act="flow-back">${IC.back}</div>
  <div class="kbtn pri sm" data-act="go-intents" style="width:auto;padding:0 16px;gap:8px">${IC.nIntents}<span>${T('Все интенты','All intents')}</span></div></div>`;
  return `<div class="kbar" style="justify-content:space-between">
  <div class="kback" data-act="flow-back">${IC.back}</div>
  ${show?`<div class="kchip on" data-act="flow-finish" style="cursor:pointer;font-weight:600">${
    '+ '+T('Создать интент','Create Intent')}</div>`:''}</div>`; }
function kprompt(txt){ return `<div class="kprompt"><div class="av">${IC.person}</div>
  <div class="k-h3" style="flex:1;min-width:0">${esc(txt)}</div></div>`; }
function kcomposer(id,ph){ return `<div class="kcomp" style="padding:10px 16px;border-top:1px solid var(--border);background:var(--bg)">
  <div class="fld"><input id="${id}" placeholder="${esc(ph)}" autocomplete="off">${IC.mic}</div>
  <button class="snd" data-act="flow-send">${IC.send}</button></div>`; }

// ---- 1. Request composer (479:14582) ----
// The three openers shown on the create-intent screen. Same source as before (hintsFor: profile
// first, model second, generic last); `FLOW.roll` rotates through the pool so Regenerate returns a
// different three instead of redrawing the same card.
// ---- Create Intent: format (Figma «What format do you prefer?») ----
const FMT_OPTS=()=>[
  ['offline', IC.pin,        T('Офлайн','Offline'),  T('Вживую','In person')],
  ['online',  IC.globe,      T('Онлайн','Online'),   T('Видео / голос','Video / voice')],
  ['hybrid',  IC.plusCircle, T('Гибрид','Hybrid'),   T('И онлайн, и вживую','Both online & offline')]];
const SIZE_OPTS=()=>[
  ['1:1',   IC.person, T('1:1','1:1'),                 T('Один на один','One-on-one')],
  ['small', IC.users,  T('Малая группа','Small group'), T('2–5 человек','2–5 people')],
  ['party', IC.groups, T('Компания','Party'),           T('10+ человек','10+ people')]];
function chRows(opts, sel, act){
  return opts.map(o=>`<div class="chrow ${sel===o[0]?'on':''}" data-act="${act}" data-k="${o[0]}">
    <div class="ic">${o[1]}</div><div class="bd"><div class="ti">${esc(o[2])}</div><div class="su">${esc(o[3])}</div></div>
    <div class="ck">${IC.check}</div></div>`).join('');
}
function scr_fmt(){
  return `<div class="kflow fade">${kbar(true)}
    <div class="kcont">
      ${kprompt(T('В каком формате удобнее?','What format do you prefer?'))}
      <div style="margin-top:4px">${chRows(FMT_OPTS(), FLOW&&FLOW.fmt, 'flow-fmt')}</div>
      ${(FLOW&&FLOW.fmt)?`<div class="kbub ag" style="width:max-content">${T('Отлично!','Awesome!')}</div>`:''}
    </div>
    ${kcomposer('flowinp3',T('Сообщение…','Message…'))}</div>`;
}
function scr_gsize(){
  return `<div class="kflow fade">${kbar(true)}
    <div class="kcont">
      ${kprompt(T('Сколько вас будет?','How many people will there be?'))}
      <div style="margin-top:4px">${chRows(SIZE_OPTS(), FLOW&&FLOW.gsize, 'flow-gsize')}</div>
      ${(FLOW&&FLOW.gsize)?`<div class="kbub ag" style="width:max-content">${T('Отлично!','Awesome!')}</div>`:''}
    </div>
    ${kcomposer('flowinp4',T('Сообщение…','Message…'))}</div>`;
}
// ---- Create Intent: the 3-step detail card (Figma «To match you better, one thing») ----
// Step 3 is where the branches meet again: offline asks for a district + radius, online for a link,
// hybrid for both. That is the only difference between the three flows.
function dstep(){ return Math.min(3, Math.max(1, (FLOW&&FLOW.dstep)|0 || 1)); }
function dDates(){
  const out=[], now=new Date();
  const wd=[T('Вс','Sun'),T('Пн','Mon'),T('Вт','Tue'),T('Ср','Wed'),T('Чт','Thu'),T('Пт','Fri'),T('Сб','Sat')];
  const mo=[T('янв','Jan'),T('фев','Feb'),T('мар','Mar'),T('апр','Apr'),T('мая','May'),T('июн','Jun'),
            T('июл','Jul'),T('авг','Aug'),T('сен','Sep'),T('окт','Oct'),T('ноя','Nov'),T('дек','Dec')];
  for(let i=0;i<7;i++){ const d=new Date(now.getTime()+i*864e5);
    out.push([d.toISOString().slice(0,10), wd[d.getDay()]+' '+d.getDate()+' '+mo[d.getMonth()]]); }
  return out;
}
// One SVG ring used for both pickers: a single handle for time, two for the age range. The arc is
// the selected span, so the control reads the same way in both modes. Geometry is shared with
// wireDial()/redrawDial() so a drag can repaint the ring in place without a full screen re-render.
const RING_R=74, RING_C=90;
function ringPt(f){ const tau=Math.PI*2; return [RING_C+RING_R*Math.sin(f*tau), RING_C-RING_R*Math.cos(f*tau)]; }
function ringInner(frac, frac2, label){
  const R=RING_R, a=ringPt(frac), b=(frac2!=null)?ringPt(frac2):null;
  let arc='';
  if(frac2!=null){ const big=((frac2-frac+1)%1)>0.5?1:0;
    arc=`<path d="M${a[0]} ${a[1]} A${R} ${R} 0 ${big} 1 ${b[0]} ${b[1]}" fill="none" stroke="var(--primary)" stroke-width="3" stroke-linecap="round"/>`; }
  else { const big=frac>0.5?1:0; const z=ringPt(0);
    arc=`<path d="M${z[0]} ${z[1]} A${R} ${R} 0 ${big} 1 ${a[0]} ${a[1]}" fill="none" stroke="var(--primary)" stroke-width="3" stroke-linecap="round"/>`; }
  return `<circle cx="${RING_C}" cy="${RING_C}" r="${R}" fill="none" stroke="var(--border)" stroke-width="3"/>
    ${arc}
    <circle class="hand" data-h="0" cx="${a[0]}" cy="${a[1]}" r="9" fill="var(--primary)"/>
    ${b?`<circle class="hand" data-h="1" cx="${b[0]}" cy="${b[1]}" r="9" fill="var(--primary)"/>`:''}
    <text class="val" x="${RING_C}" y="${RING_C+11}" text-anchor="middle">${esc(label)}</text>`;
}
function ring(id, frac, frac2, label){
  return `<svg class="dial" id="${id}" width="180" height="180" viewBox="0 0 180 180" data-dial="${id}">${ringInner(frac,frac2,label)}</svg>`;
}
// Repaint a dial from the current FLOW state, in place (no re-render → the map/Leaflet isn't rebuilt).
function redrawDial(id){
  const svg=document.querySelector('svg.dial[data-dial="'+id+'"]'); if(!svg) return;
  if(id==='dialTime'){
    const t=(FLOW&&FLOW.tmin!=null)?FLOW.tmin:885;
    const lab=String(Math.floor(t/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0');
    svg.innerHTML=ringInner(t/1440, null, lab);
  } else {
    const e=ageEnds(), a0=e[0], a1=e[1];        // placeholders included — drawing is not choosing
    svg.innerHTML=ringInner((a0-16)/64, (a1-16)/64, a0+'-'+a1);
  }
}
// Make the dials draggable. Pointer events cover mouse + touch; .dial has touch-action:none so a
// drag doesn't scroll the card. The age dial has two handles — grab whichever is closer.
// Capture is taken on the SVG itself (setPointerCapture), NOT left to touch's implicit capture:
// redrawDial() replaces the SVG's innerHTML on every move, which would destroy the handle a touch
// had implicitly captured and kill the drag after one step — the exact reason it worked with a mouse
// (no implicit capture; window listeners) but not under a finger. Listeners live on the SVG, which
// survives the innerHTML swap, so the whole drag keeps flowing.
function wireDial(){
  document.querySelectorAll('svg.dial[data-dial]').forEach(function(svg){
    const id=svg.getAttribute('data-dial');
    let hand=0, dragging=false;
    function fracAt(e){
      const r=svg.getBoundingClientRect();
      const dx=e.clientX-(r.left+r.width/2), dy=e.clientY-(r.top+r.height/2);
      let f=Math.atan2(dx,-dy)/(Math.PI*2); if(f<0) f+=1; return f;
    }
    function apply(f){
      if(id==='dialTime'){
        let t=Math.round(f*1440/5)*5; if(t>=1440) t=0;
        FLOW.tmin=t; redrawDial(id);
      } else {
        let age=Math.round(16+f*64); if(age<16)age=16; if(age>80)age=80;
        // BOTH ends are committed the moment the dial is touched, not just the handle being
        // dragged. Storing only the dragged end is what broke the filter: the other end stayed
        // undefined, so the range was never complete and never sent. Touching the dial is the act
        // of choosing a range — after it, what the dial shows is exactly what the search carries.
        //
        // A crossed handle PUSHES the other one; it used to be clamped against it. Clamping was
        // invisible while no filter was ever sent, and wrong as soon as one was: dragging the
        // lower handle to 30 against the 28 placeholder silently produced 28, and dragging it to
        // 60 produced the range 28-28 — a filter for a single age nobody asked for. Pushing also
        // makes the result independent of the order the two handles are moved in.
        const e=ageEnds(), a0=e[0], a1=e[1];
        if(hand===0){ FLOW.ageA=age; FLOW.ageB=Math.max(a1, age); }
        else        { FLOW.ageB=age; FLOW.ageA=Math.min(a0, age); }
        redrawDial(id);
      }
    }
    svg.addEventListener('pointerdown', function(e){
      e.preventDefault(); dragging=true;
      try{ svg.setPointerCapture(e.pointerId); }catch(_e){}
      const f=fracAt(e);
      if(id==='dialAge'){ const _e=ageEnds(), fa=(_e[0]-16)/64, fb=(_e[1]-16)/64;
        hand = Math.abs(f-fa)<=Math.abs(f-fb) ? 0 : 1; }
      apply(f);
    });
    svg.addEventListener('pointermove', function(e){ if(dragging){ e.preventDefault(); apply(fracAt(e)); } });
    function end(e){ dragging=false; try{ svg.releasePointerCapture(e.pointerId); }catch(_e){} }
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);
  });
}
// The district map is a REAL map with the radius circle, not a placeholder box — same compact
// Leaflet setup the location sheet already uses. Drawn after render, because the container must
// exist and have a size before Leaflet measures it.
let dMap=null, dCircle=null;
function dMapDraw(){
  const el=document.getElementById('dmap'); if(!el||typeof L==='undefined') return;
  const g=(DATA&&DATA.geo)||{}; const c=[g.coarseLat||41.3874, g.coarseLon||2.1686];
  const km=(FLOW&&FLOW.dkm!=null)?FLOW.dkm:19;
  try{
    // Leaflet marks the container with _leaflet_id; re-initialising it without clearing that throws
    // "Map container is already initialized" — and because innerHTML was wiped first, the panes were
    // gone and the box silently stayed blank. Tear the old map down properly instead.
    if(dMap){ try{ dMap.remove(); }catch(_e){} dMap=null; }
    el.innerHTML=''; if(el._leaflet_id) el._leaflet_id=null;
    const map=L.map(el,{zoomControl:false,attributionControl:false,dragging:false,scrollWheelZoom:false,
                        doubleClickZoom:false,touchZoom:false,boxZoom:false,keyboard:false});
    map.setView(c, 11);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{maxZoom:19}).addTo(map);
    dCircle=L.circle(c,{radius:km*1000,color:'#F5455C',weight:2,fillColor:'#F5455C',fillOpacity:.12}).addTo(map);
    L.circleMarker(c,{radius:5,color:'#F5455C',fillColor:'#F5455C',fillOpacity:1,weight:2}).addTo(map);
    const fit=()=>{ try{ map.invalidateSize(); map.fitBounds(dCircle.getBounds(),{padding:[14,14]}); }catch(_e){} };
    fit(); setTimeout(fit,80); dMap=map;
  }catch(_e){}
}
function scr_detail(){
  const st=dstep(), fmt=(FLOW&&FLOW.fmt)||'offline';
  const tm=(FLOW&&FLOW.tmin!=null)?FLOW.tmin:885;                 // 14:45
  const hh=String(Math.floor(tm/60)).padStart(2,'0'), mm=String(tm%60).padStart(2,'0');
  const _ae=ageEnds(), a0=_ae[0], a1=_ae[1];
  const km=(FLOW&&FLOW.dkm!=null)?FLOW.dkm:19;
  let body='';
  if(st===1){
    body=`<div class="dsec">${IC.calen}<span>${T('Дата','Date')}</span></div>
      <div class="dchips">${dDates().map(d=>`<div class="c ${FLOW.date===d[0]?'on':''}" data-act="d-date" data-k="${d[0]}">${esc(d[1])}</div>`).join('')}</div>
      <div class="dsec">${IC.clock}<span>${T('Время','Time')}</span></div>
      ${ring('dialTime', tm/1440, null, hh+':'+mm)}`;
  } else if(st===2){
    const sexes=[['male',T('Мужчины','Male')],['female',T('Женщины','Female')],['any',T('Не важно','Any is fine')]];
    body=`<div class="dsec">${IC.person}<span>${T('Пол','Sex')}</span></div>
      <div class="seg">${sexes.map(x=>`<div class="o ${((FLOW.sex||'any')===x[0])?'on':''}" data-act="d-sex" data-k="${x[0]}">${esc(x[1])}</div>`).join('')}</div>
      <div class="dsec">${IC.users}<span>${T('Возраст','Age')}</span></div>
      ${ring('dialAge', (a0-16)/64, (a1-16)/64, a0+'-'+a1)}`;
  } else {
    const geo=`<div class="dsec">${IC.pin}<span>${T('Район','District')}</span></div>
      <div id="dmap" class="lmap" style="height:170px;border-radius:14px;overflow:hidden"></div>
      <div class="rowlbl"><span>${T('Насколько далеко готов ехать?','How far are you happy to go?')}</span><b>${km} ${T('км','km')}</b></div>
      <input class="krange" type="range" min="1" max="40" value="${km}" data-act="d-km" style="width:100%">
      <input class="tinput" id="daddr" placeholder="${T('Добавь адрес','Add your address')}" value="${esc((FLOW&&FLOW.addr)||'')}">`;
    const link=`<div class="dsec">${IC.globe}<span>${T('Ссылка','Link')}</span></div>
      <input class="tinput" id="dlink" placeholder="https://yourlink.com" value="${esc((FLOW&&FLOW.link)||'')}">
      <div class="disc">${IC.shieldSm||IC.shield}<span>${T('Ссылки добавляют сами пользователи. Открывать их или нет — решаешь ты. Kleal не отвечает за сторонний контент и действия.','External links are shared by users. You choose whether to open them. Kleal is not responsible for third-party content or actions.')}</span></div>`;
    body = (fmt==='online') ? link : (fmt==='hybrid' ? (geo+link) : geo);
  }
  const stp=`<div class="stepper">
    <div class="st ${st>=1?'on':''}">1</div><div class="ln ${st>=2?'on':''}"></div>
    <div class="st ${st>=2?'on':''}">2</div><div class="ln ${st>=3?'on':''}"></div>
    <div class="st ${st>=3?'on':''}">3</div></div>`;
  return `<div class="kflow fade">${kbar(true)}
    <div class="kcont">
      ${kprompt(T('Ещё одно — чтобы подобрать точнее','To match you better, one thing'))}
      <div class="kbub ag" style="width:max-content">${T('Когда и где удобнее?','When and where works best?')}</div>
      <div class="dcard">${stp}${body}
        <div class="kbtn pri" data-act="d-next">${T('Далее','Next')}</div></div>
    </div>
    ${kcomposer('flowinp5',T('Сообщение…','Message…'))}</div>`;
}
function suggList(){
  const pool=[];
  const push=a=>(a||[]).forEach(h=>{ if(h&&pool.indexOf(h)<0) pool.push(h); });
  push(hintsFor(null));
  const all=(FLOW&&FLOW.msgs)||[];
  for(let n=all.length-1;n>=0;n--){ if(all[n].who==='ag'){ push(hintsFor(all[n])); break; } }
  push(FLOW_HINTS());
  if(!pool.length) return [];
  const r=((FLOW&&FLOW.roll)|0)%pool.length;
  const out=[]; for(let i=0;i<Math.min(3,pool.length);i++) out.push(pool[(r+i)%pool.length]);
  return out;
}
function scr_reqcomposer(){
  const all=(FLOW&&FLOW.msgs)||[];
  // These chips are openers — a way IN while the person still hasn't said what they want. The test is
  // NOT "have they typed anything": «привет» is typing, and it is exactly the moment the openers are
  // most useful. The builder already draws that line for us — a turn it answers conversationally is
  // marked `chat`, so a user message WITHOUT that flag is the first real request. Before it: chips.
  // After it: silence, because a suggestion for what to want is noise once you have said it.
  const asked=all.some(m=>m.who==='me'&&!m.chat);
  let lastAg=-1; for(let n=all.length-1;n>=0;n--){ if(all[n].who==='ag'){ lastAg=n; break; } }
  const msgs=all.map((m,i)=>m.who==='me'
    ? `<div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end"><div class="kbub me">${esc(m.text)}</div><div class="ktime">${fmtTime(m.t)}</div></div>`
    : `<div style="display:flex;flex-direction:column;gap:4px"><div class="kbub ag">${esc(m.text)}</div><div class="ktime">${fmtTime(m.t)}</div>${
        ''
      }</div>`).join('');
  // The bar carries «+ Создать интент» (Figma): the way OUT of the dialog is always in reach, not
  // buried under the thread. It appears once there is something to build from.
  // Figma 1615:21018 — the openers are the primary way in: a titled card of full-width rows with a
  // regenerate control, not a chip row squeezed under a bubble. Same source (hintsFor), same rule for
  // WHEN they show; only the surface changed.
  const sugg = suggList();
  const suggBlock = (!asked && !FLOW.busy) ? `<div class="sugg">
        <div class="lbl">${T('Выбери из предложенных','Choose from the suggested options')}</div>
        <div class="card">${sugg.map(h=>
          `<div class="row" data-act="flow-hint" data-h="${esc(h)}">${esc(h)}</div>`).join('')}</div>
        <div class="kbtn pri sm" data-act="flow-regen" style="gap:8px">${IC.spark}<span>${
          T('Сгенерировать заново','Regenerate')}</span></div>
      </div>` : '';
  return `<div class="kflow fade">${kbar(true)}
    <div class="kcont">
      ${kprompt(FLOW.mode==='intent'?T('Что хочешь сделать?','What do you want to do?')
                                     :T('Чего бы тебе хотелось сегодня?','What would you like today?'))}
      ${(!asked&&!FLOW.busy)?`<div class="sugg hintline" style="padding:0">${
        T('Просто и коротко — кофе, матч, игра, прогулка или «не хочу сидеть дома».',
          'Keep it simple — coffee, a match, a game, a walk, or just “don’t feel like staying in.”')}</div>`:''}
      ${suggBlock}
      ${msgs}
      ${FLOW.busy?`<div class="kbub ag" style="width:64px"><span class="typing3"><i></i><i></i><i></i></span></div>`:''}
      ${/* A failure is not the moment for openers either: «Обсудить стартапы» is not a rephrasing of
             what the person just tried to say. Generic examples of PHRASING are, which is what this
             block always meant. */''}
      ${(all.length&&FLOW.lastFailed&&!FLOW.busy)?`<div style="display:flex;flex-direction:column;gap:12px">
        <div class="k-label" style="color:var(--muted)">${T('Попробуй сформулировать иначе','Try phrasing it differently')}</div>
        <div class="kchips">${FLOW_HINTS().map(h=>`<div class="kchip soft hint" data-act="flow-hint" data-h="${esc(h)}">${esc(h)}</div>`).join('')}</div>
      </div>`:''}
    </div>
    ${kcomposer('flowinp',T('Сообщение…','Message…'))}</div>`;
}

// The builder's free-text time («завтра», 'tomorrow evening', 'Гибко') mapped onto the clarify
// chips. It used to live only in FLOW.intent.time, which the clarify screen never read — so the day
// the user had already named in the dialog was asked again with the chip row dark. This was the
// «после ответа опять эти вопросы» bug. 'Гибко'/'Flexible' is the builder's own default for "never
// said", so it deliberately maps to nothing and the question is still asked.
function intentPrefill(){
  const t=String((FLOW.intent&&FLOW.intent.time)||'').toLowerCase();
  FLOW.knownWhen=false; FLOW.knownTime=false;
  if(!t) return;
  const day = /завтра|tomorrow/.test(t)?'tomorrow'
            : /сегодня|today|tonight/.test(t)?'today'
            : /выходн|weekend|суббот|воскрес|saturday|sunday/.test(t)?'weekend' : null;
  const tod = /утр|morning/.test(t)?'morning'
            : /дн[её]м|afternoon/.test(t)?'afternoon'
            : /вечер|evening|tonight/.test(t)?'evening'
            : /поздн|ноч|late|night/.test(t)?'late' : null;
  if(day){ FLOW.when=FLOW.when||day; FLOW.knownWhen=true; }
  if(tod){ FLOW.time=FLOW.time||tod; FLOW.knownTime=true; }
}

// ---- 2. One clarification (479:14610) ----
function scr_clarify(){
  const grp=(icon,title,opts,key)=>`<div class="kgrp"><div class="hd">${icon}${esc(title)}</div>
    <div class="kchips">${opts.map(o=>`<div class="kchip ${FLOW[key]===o[0]?'on':''}" data-act="flow-pick" data-k="${key}" data-v="${o[0]}">${esc(o[1])}</div>`).join('')}</div></div>`;
  // A group whose answer already came from the dialog is not re-asked; «Изменить» on the summary
  // (flow-edit) sets editAll and brings every group back for corrections.
  const online=flowOnline();     // an online plan never asks for a district
  const showWhen=FLOW.editAll||!FLOW.knownWhen, showTime=FLOW.editAll||!FLOW.knownTime;
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Чтобы точнее подобрать — один момент:','To match you better, one thing:'))}
      <div class="kbub ag">${
        showWhen?(online?T('Когда удобнее?','When works best?'):T('Когда и где удобнее?','When and where works best?'))
        :(showTime?(online?T('Понял, когда. Во сколько удобно?','Got the day. What time works?')
                          :T('Понял, когда. Время и район уточним?','Got the day. Time and district?'))
                  :T('Остался только район — уточним?','Only the district left — narrow it down?'))}</div>
      <div class="kplan">
        ${showWhen?grp(IC.calen,T('Когда','When'),WHEN_OPTS(),'when'):''}
        ${showTime?grp(IC.clock,T('Время','Time'),TIME_OPTS(),'time'):''}
        ${online?'':grp(IC.pin,T('Район','District'),DIST_OPTS(),'district')}
        <div class="kwhy">${T('Необязательно — можно пропустить или изменить позже.','Optional — skip it or change it later.')}</div>
        <div class="kcta">
          <button class="kbtn sec" data-act="flow-skip">${T('Пропустить','Skip')}</button>
          <button class="kbtn pri" data-act="flow-next">${T('Далее','Next')}</button>
        </div>
      </div>
    </div>
    ${kcomposer('flowinp2',T('Сообщение…','Message…'))}</div>`;
}

// ---- 3. Summary before search (479:14661) ----
// `dash||…` could never yield an empty string: the only caller that wants "show nothing" passes '',
// which is falsy, so it got the placeholder instead — and the summary rendered
// «Время: на твоё усмотрение — на твоё усмотрение», the same words joined to themselves.
// Time the user already stated in their own request, e.g. "…завтра". FLOW.when is only set when they
// tap a chip on the clarify screen, so without this the summary claimed "на твоё усмотрение" for a
// request that plainly said when.
const _WHEN_RU={tomorrow:['Завтра','Tomorrow'],today:['Сегодня','Today'],tonight:['Сегодня вечером','Tonight'],
  weekend:['В выходные','This weekend'],week:['На неделе','This week'],flexible:['на твоё усмотрение','flexible']};
function intentWhen(){
  const t=String((FLOW&&FLOW.intent&&FLOW.intent.time)||'').trim().toLowerCase();
  if(!t) return undefined;                       // undefined -> labelOf falls back to the placeholder
  const hit=_WHEN_RU[t]; if(hit) return T(hit[0],hit[1]);
  // compound times the table has no entry for ("tomorrow evening") still get their tokens localized
  return locStr((FLOW.intent.time||'').trim()) || undefined;
}
function labelOf(opts,v,dash){ const o=opts.find(x=>x[0]===v);
  return o?o[1]:(dash!==undefined?dash:T('на твоё усмотрение','flexible')); }
// "Kleal summary" = how Kleal READ the intent, not a generic promise. Prefer a real AI understanding
// from the backend (s.summary / intent.summary) when it lands; otherwise reflect the parsed pieces
// (activity + format + group + who) back as a short paraphrase, so the box always says what Kleal
// understood rather than what it will do.
function intentUnderstanding(){
  const s=FLOW.summary||{}, it=FLOW.intent||{};
  const given=String(s.summary||it.summary||'').trim();
  if(given) return given;
  // Quoting the person back is the friendliest lead — right up until their words point at the
  // conversation instead of naming anything: «Понял так: я хочу с кем-то об этом поговорить».
  // In that one case the compiled title is the only thing that actually says what this is.
  const req=String(s.request||FLOW.request||FLOW.text||'').trim();
  const pointsBack=/об\s+этом|про\s+это|это\s+обсуд|обсуд\w*\s+это|выше\s+писал|about\s+(this|that|it)\b|discuss\s+it\b|sobre\s+esto|de\s+esto/i.test(req);
  const lead=(pointsBack&&(s.title||it.title))||req
             || locTopicList(it.topics||[]) || T('встретиться','meet up');
  const fmt=FLOW.fmt||(flowOnline()?'online':'offline');
  const set=[
    {offline:T('вживую','in person'),online:T('онлайн','online'),hybrid:T('онлайн или вживую','online or in person')}[fmt],
    {'1:1':T('один на один','one-on-one'),small:T('в малой группе','in a small group'),party:T('компанией','with a group')}[FLOW.gsize||'']
  ].filter(Boolean);
  const sexL={male:T('парней','guys'),female:T('девушек','women'),any:''}[FLOW.sex||'any'];
  const _ar=ageRange(), ageL=_ar?(_ar[0]+'–'+_ar[1]):'';
  const who=[sexL,ageL].filter(Boolean).join(' ');
  let out=T('Понял так: ','Read it as: ')+lead;
  if(set.length) out+=' — '+set.join(', ');
  out+='.';
  if(who) out+=' '+T('Ищу ','Looking for ')+who+'.';
  return out;
}
function scr_summary(){
  // Full "Here's what I got" card (Figma 1688-26605): cover, title, date/time + location-or-link,
  // Category/Format/Personality rows, and a Kleal-summary box. Everything binds to what the flow
  // actually collected; the cover stays an honest category illustration (this is the user's OWN
  // intent preview, not a stock event photo).
  const s=FLOW.summary||{};
  const topics=(FLOW.intent&&FLOW.intent.topics)||[];
  const key=tileKeyFor(topics.join(' ')||String(s.request||FLOW.request||FLOW.text||''));
  const title=esc(s.title||s.request||FLOW.request||FLOW.text||T('Твой интент','Your intent'));
  // time — from the detail step (date chip + dial), with the clarify values as a fallback
  const dd=dDates().find(x=>x[0]===FLOW.date), dateLbl=dd?dd[1]:'';
  const t=(FLOW.tmin!=null)?(String(Math.floor(FLOW.tmin/60)).padStart(2,'0')+':'+String(FLOW.tmin%60).padStart(2,'0')):'';
  const when=labelOf(WHEN_OPTS(),FLOW.when, intentWhen()), tm=labelOf(TIME_OPTS(),FLOW.time,'');
  const dateTxt=dateLbl||[when,(tm||'')].filter(Boolean).join(' — ')||T('Гибко','Flexible');
  // location for offline, link for online, both for hybrid (the two Figma variants)
  const fmt=FLOW.fmt||(flowOnline()?'online':'offline');
  const place=(FLOW.addr||'').trim() || labelOf(DIST_OPTS(),FLOW.district,'') || FLOW.area || T('Район рядом','Nearby area');
  const travel=(FLOW.dkm!=null)?(' · '+FLOW.dkm+' '+T('км','km')):'';
  const link=(FLOW.link||'').trim();
  const mt=(icon,val)=>`<div class="mt">${icon}<span>${esc(val)}</span></div>`;
  let loc='';
  if(fmt!=='online') loc+=mt(IC.pin, place+travel);
  if(fmt!=='offline') loc+=mt(IC.chain, link||T('ссылка не добавлена','no link added'));
  // Category / Format / Personality
  const cats=locTopicList(topics.length?topics:(s.vibe||[]))||T('пока не задано','not set yet');
  const fmtL=(FMT_OPTS().find(o=>o[0]===FLOW.fmt)||[])[2]||'';
  const szL=(SIZE_OPTS().find(o=>o[0]===FLOW.gsize)||[])[2]||'';
  const format=[fmtL,szL].filter(Boolean).join(', ')||s.format||T('Встреча, неформально','Casual meetup');
  const sexL={male:T('Мужчины','Male'),female:T('Женщины','Female'),any:T('Не важно','Any')}[FLOW.sex||'any'];
  const _ar=ageRange(), ageL=_ar?(_ar[0]+'–'+_ar[1]):'';
  const persona=[sexL,ageL].filter(Boolean).join(', ');
  const summ=esc(intentUnderstanding());
  const kv=(k,v)=>v?`<div class="r"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`:'';
  return `<div class="kflow fade">${kbar(true)}
    <div class="kcont">
      ${kprompt(T('Вот что получилось',"Here's what I got"))}
      <div class="kbub ag">${T('Проверь — что-то можно поправить. Настроим поиск под твой профиль и этот интент.','Check it — edit anything if needed. We will tailor the search to your profile settings and this intent.')}</div>
      <div class="isumm">
        <div class="cov">${TILE_SVG[key]||TILE_SVG.social}</div>
        <div class="cnt">
          <div class="ti">${title}</div>
          <div class="meta">
            <div class="mt">${IC.calen}<span>${esc(dateTxt)}</span>${t?`${IC.clock}<span>${esc(t)}</span>`:''}</div>
            ${loc}
          </div>
          <div class="kv">
            ${kv(T('Категория','Category'), cats)}
            ${kv(T('Формат','Format'), format)}
            ${kv(T('Кто','Personality'), persona)}
          </div>
          <div class="why">
            <div class="ed" data-act="flow-edit">${IC.edit}</div>
            <div class="h">${T('Саммари Kleal:','Kleal summary:')}</div>
            <div class="tx">${summ}</div>
          </div>
        </div>
      </div>
    </div>
    <div class="kfoot">
      <button class="kbtn pri" data-act="flow-start">${T('Начать поиск','Start search')}</button>
      <button class="kbtn sec" data-act="flow-edit">${T('Изменить','Edit')}</button>
    </div></div>`;
}

// ---- 4. Searching (progress while matching runs) ----
function scr_searching(){
  const st=STEP_LABELS().map((lb,i)=>{
    const cls=i<FLOW.steps?'done':(i===FLOW.steps?'now':'');
    const bg=i<FLOW.steps?T('Готово','Done'):(i===FLOW.steps?T('Идёт','In progress'):T('Скоро','Soon'));
    return `<div class="kstep ${cls}"><div class="dot"></div><div class="tx">${esc(lb)}</div><div class="bg">${esc(bg)}</div></div>`;
  }).join('');
  return `<div class="kflow fade">${kbar()}
    <div class="ksearching">
      <div class="msc">${masc('searching')}</div>
      <div class="brand">Kleal</div>
      <div class="lead">${T('Ищу людей, группы и места для тебя','Finding people, groups and places for you')}</div>
      <div class="ksteps">${st}</div>
      <div class="k-cap" style="color:var(--muted)">${T('Это займёт мгновение.','This will take just a moment.')}</div>
    </div></div>`;
}

// ---- 5. Few matches → recommended adjustment ----
function scr_fewmatches(){
  const n=(FLOW.res||[]).length;
  // Nobody does this AND nothing adjacent exists (broaden already ran server-side and found none),
  // so widening the radius cannot help — the honest move is a standing intent. When the server said
  // there ARE related people, this screen is not reached (they are shown instead).
  const noSupply = (FLOW.fbRelated===0);
  const opt=(key,icon,ti,su)=>`<div class="kopt ${FLOW.adjust===key?'sel':''}" data-act="flow-adjust" data-k="${key}">
    <div class="ic">${icon}</div><div class="bd"><div class="ti">${esc(ti)}</div><div class="su">${esc(su)}</div></div>
    ${FLOW.adjust===key?`<div class="ck">${IC.check2||IC.chevR}</div>`:''}</div>`;
  const head = noSupply ? T('Пока рядом этим никто не занят','Nobody nearby is into this yet')
                        : T('Точных совпадений пока немного','Not many exact matches yet');
  const msg = FLOW.fbNote || T('По твоему запросу с текущими фильтрами вариантов мало.',
                              'For your request with the current filters, options are limited.');
  if(noSupply){
    return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(head)}
      <div class="kbub ag">${esc(msg)}</div>
      <div class="kplan tight" style="gap:4px">
        <div class="kopt sel" data-act="flow-save-intent"><div class="ic">${IC.spark||IC.check2||''}</div>
          <div class="bd"><div class="ti">${T('Создать интент','Create an intent')}</div>
            <div class="su">${T('Сохраню и подберу, как только кто-то появится','I will save it and match you the moment someone appears')}</div></div></div>
        ${opt('wide',IC.groups,T('Всё равно расширить радиус','Widen the radius anyway'),T('На случай, если кто-то есть чуть дальше','In case someone is a bit further out'))}
      </div>
    </div>
    <div class="kfoot"><button class="kbtn pri" data-act="flow-save-intent">${T('Создать интент','Create an intent')}</button></div></div>`;
  }
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(head)}
      <div class="kbub ag">${esc(msg)}</div>
      <div class="k-title">${T('Рекомендуемая настройка','Recommended adjustment')}</div>
      <div class="kplan tight" style="gap:4px">
        ${opt('wide',IC.groups,T('Расширить радиус поиска','Widen the search radius'),T('Люди и места за пределами района','Include places and people beyond your district'))}
        ${opt('radius',IC.radius,T('+5 км к радиусу','+5 km to radius'),T('Рядом появятся новые варианты','New options appear nearby'))}
        ${opt('keep',IC.homeSm,T('Оставить как есть','Keep it as is'),T('Искать только в текущем районе','Search only in the current district'))}
        <div class="kopt" style="cursor:default">
          <div class="bd"><div class="ti">${T('Также включить группы','Also include groups')}</div>
            <div class="su">${T('Откроет больше форматов встреч','Opens more formats of meeting people')}</div></div>
          <div class="ktog ${FLOW.groups?'on':''}" data-act="flow-groups"><i></i></div></div>
      </div>
      ${n?`<div class="k-cap" style="color:var(--muted)">${T('Сейчас найдено','Found so far')}: ${n}</div>`:''}
    </div>
    <div class="kfoot"><button class="kbtn pri" data-act="flow-apply">${T('Применить и обновить','Apply & refresh')}</button></div></div>`;
}

// ================= Figma batch 3: request → mutual → meetup plan → meetup day =================
// PLAN is the shared state for everything after "Interested": who, the request we send, the reply,
// the agreed slot/place and the live meetup status. Slots come from the intent's own time window;
// places come from the candidate's communities (no venue service exists yet, and inventing venue
// data would put fake addresses in front of users).
let PLAN=null;
function planInit(c){
  PLAN={ cand:c, sent:false, reply:null, mutual:false, slot:null, place:null,
         confirmed:false, gcal:false, acal:false, remind:true, status:null, here:false };
}
function planSlots(){
  // Slots are OUR suggestions built from the intent's time window. They must never be attributed
  // to the other person — the app has not asked them anything yet.
  const it=(FLOW&&flowIntent())||{};
  const sug=T('вариант Kleal','Kleal’s suggestion');
  const base=[[T('Сегодня','Today'),'16:00–17:00',sug],
              [T('Сегодня','Today'),'19:00–20:00',sug],
              [T('Завтра','Tomorrow'),'12:00–13:00',sug],
              [T('Завтра','Tomorrow'),'18:00–19:00',sug]];
  if(/morning|утр/i.test(it.time||'')) base.unshift([T('Завтра','Tomorrow'),'09:00–10:00',sug]);
  return base;
}
function planPlaces(){
  // There is no venue service yet: we can name the communities this person belongs to, but we
  // cannot know a venue's distance or walking time. Inventing them puts false facts on screen.
  const c=PLAN&&PLAN.cand, ents=(c&&c.entities)||[];
  const named=ents.slice(0,3).map(e=>{ const n=String(e);
    // don't repeat a word the name already carries ("Кофейное сообщество сообщество")
    const dup=/сообществ|community|club|клуб|scene|сцен/i.test(n);
    return {name:n, note: dup? T('место встреч этого сообщества','where this community meets')
                            : T('сообщество','community')}; });
  if(named.length) return named;
  return [{name:T('Выбрать место в чате','Agree on a place in the chat'), note:T('вы решите вместе','you’ll decide together')}];
}
function slotText(){ const s=PLAN&&PLAN.slot; return s?(s[0]+', '+s[1]):T('время не выбрано','time not picked'); }
function placeText(){ const p=PLAN&&PLAN.place; return p?p.name:T('место не выбрано','place not picked'); }

// ---- 1. What will be sent ----
function scr_sendreq(){
  const c=PLAN&&PLAN.cand; if(!c) return scr_options();
  const me=DATA.name||'', age=(DATA.age||snapRow&&'')||'';
  const ints=(DATA.interests||[]).map(i=>i.name).slice(0,3).join(', ');
  const it=(FLOW&&flowIntent())||{};
  const row=(icon,ti,su)=>`<div class="it"><div class="ic">${icon}</div><div class="bd">
      <div class="ti">${esc(ti)}</div><div class="su">${esc(su)}</div></div></div>`;
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Что будет отправлено','What will be sent'))}
      <div class="kbub ag">${T('Вот что я покажу','I will share this with')} ${esc(c.name)}:</div>
      <div class="kshare">
        ${row(IC.person,T('Твоё имя','Your name'), me+(age?(', '+age):''))}
        ${row(IC.heart||IC.spark,T('Твой интент','Your intent'), (it.title||FLOW&&FLOW.request||T('Познакомиться и встретиться вживую','Interested in meeting and connecting in person')))}
        ${row(IC.chat,T('Короткий контекст','Short context'), ints||T('Интересы пока не заполнены','No interests filled in yet'))}
      </div>
      <div class="knote">${IC.shieldSm}${T('Личные данные (телефон, адрес) не передаются.','Personal details (phone, address, etc.) won’t be shared.')}</div>
    </div>
    <div class="kfoot"><div class="kcta">
      <button class="kbtn sec" data-act="req-edit">${T('Изменить','Edit')}</button>
      <button class="kbtn pri" data-act="req-send">${T('Отправить запрос','Send request')}</button>
    </div></div></div>`;
}

// ---- 2. Waiting for reply ----
function scr_waiting(){
  const c=PLAN&&PLAN.cand; if(!c) return scr_options();
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      <div class="kstate"><div class="hero">${masc('thinking')}</div>
        <div class="ti">${T('Ждём ответа','Waiting for reply')}</div>
        <div class="su">${T('Мы отправили твой запрос','We sent your request to')} ${esc(c.name)}.<br>
          ${T('Она увидит только то, что ты одобрил(а).','They’ll only see what you approved.')}</div></div>
      <div class="kinfo">${IC.info}${T('Если ответа не будет — сообщим позже.','If there’s no reply, we’ll let you know later.')}</div>
      <div class="klist">
        <div class="row" data-act="req-edit"><div class="ic">${IC.edit}</div>
          <div class="bd"><div class="ti">${T('Изменить запрос','Change request')}</div></div><div class="ch">${IC.chevR}</div></div>
        <div class="row" data-act="go-options"><div class="ic">${IC.gear}</div>
          <div class="bd"><div class="ti">${T('Другие варианты','See other options')}</div></div><div class="ch">${IC.chevR}</div></div>
        ${PLAN.reqId?`<div class="row" data-act="req-withdraw"><div class="ic">${IC.close||IC.info}</div>
          <div class="bd"><div class="ti">${T('Отозвать запрос','Withdraw request')}</div></div><div class="ch">${IC.chevR}</div></div>`:''}
      </div>
    </div></div>`;
}

// ---- 3. Mutual interest ----
function scr_mutual(){
  const c=PLAN&&PLAN.cand; if(!c) return scr_options();
  const meInts=(DATA.interests||[]).map(i=>i.name).slice(0,2).join(', ');
  const theirs=(c.interests||[]).slice(0,2).join(', ');
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      <div class="kstate"><div class="hero sm">${masc('match')}</div>
        <div class="ti">${T('Взаимный интерес','It’s a mutual interest')}</div>
        <div class="su">${T('Вы понравились друг другу!','You like each other!')}</div></div>
      <div class="kpair">
        <div class="p"><div class="av">${IC.person}</div><div class="nm">${esc(DATA.name||'')}</div>
          <div class="su">${esc(meInts)}</div></div>
        <div class="p"><div class="av">${IC.person}</div><div class="nm">${esc(c.name)}${c.age?(', '+c.age):''}</div>
          <div class="su">${esc(theirs)}</div></div>
      </div>
      <div class="klist"><div class="row" style="cursor:default"><div class="ic">${IC.chat}</div>
        <div class="bd"><div class="su" style="font-size:13px;line-height:18px;color:var(--fg)">
          ${T('Откройте чат и договоритесь о времени, удобном обоим.','Open the chat and agree on a time that works for both?')}</div></div></div></div>
    </div>
    <div class="kfoot">
      <button class="kbtn pri tall" data-act="plan-open-chat">${T('Открыть чат','Open chat')}</button>
      <button class="kbtn sec" data-act="plan-later" style="background:transparent">${T('Не сейчас','Not now')}</button>
    </div></div>`;
}

// ---- 4. Suggestion from them ----
function scr_suggestion(){
  const c=PLAN&&PLAN.cand; if(!c) return scr_options();
  const s=PLAN.suggest||{};        // only rendered when their agent really replied
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Предложение от','Suggestion from')+' '+c.name)}
      <div class="kbub ag">${T('Предложение по первой встрече. Ни к чему не обязывает.','They suggested an option for the first meetup. No obligations')}</div>
      <div class="kplan tight">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
          <div class="k-h3">${esc(s.title)}</div><div class="ic" style="color:var(--muted)">${IC.calen}</div></div>
        ${s.time?`<div class="kplanrow"><div class="ic">${IC.clock}</div><div class="bd">
          <div class="su">${T('Время','Time')}</div><div class="ti" style="font-size:13px">${esc(locStr(s.time))}</div></div></div>`:''}
        ${s.place?`<div class="kplanrow"><div class="ic">${IC.pin}</div><div class="bd">
          <div class="su">${T('Место','District')}</div><div class="ti" style="font-size:13px">${esc(locStr(s.place))}</div></div></div>`:''}
        ${s.quote?`<div class="kquote">“${esc(s.quote)}” — ${esc(c.name)}</div>`:
          `<div class="kwhy">${T('Детали вы согласуете в чате.','You’ll agree on the details in the chat.')}</div>`}
      </div>
      <div class="knote">${IC.shieldSm}${T('Личные контакты не передаём, пока вы оба не будете готовы.','We don’t share personal contacts until you’re both ready.')}</div>
    </div>
    <div class="kfoot">
      <button class="kbtn pri tall" data-act="plan-accept">${T('Мне подходит','Works for me')}</button>
      <button class="kbtn sec" data-act="plan-pick-time">${T('Предложу своё','Suggest my own')}</button>
    </div></div>`;
}

// ---- 5. Pick a time ----
function scr_picktime(){
  const slots=planSlots();
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      <div style="display:flex;align-items:center;gap:8px">
        ${kprompt(T('Планируем встречу','Planning the meetup'))}
        <div class="kdraft">${IC.spark}${T('Черновик','Draft plan')}</div></div>
      <div class="kbub ag">${UILANG==='ru'?('Выбери время — предложим его '+esc((PLAN&&PLAN.cand&&PLAN.cand.name)||''))
        :('Pick a time — we’ll suggest it to '+esc((PLAN&&PLAN.cand&&PLAN.cand.name)||''))}</div>
      <div class="k-title">${T('Предложенные слоты','Suggested slots')}</div>
      <div style="display:flex;flex-direction:column;gap:8px">
        ${slots.map((s,i)=>`<div class="kslot ${PLAN&&PLAN.slot&&PLAN.slot[1]===s[1]&&PLAN.slot[0]===s[0]?'on':''}" data-act="pick-slot" data-i="${i}">
          <div class="ic">${IC.clock}</div>
          <div class="bd"><div class="d">${esc(s[0])}</div><div class="w">${esc(s[2])}</div></div>
          <div class="t">${esc(s[1])}</div>
          ${PLAN&&PLAN.slot&&PLAN.slot[1]===s[1]&&PLAN.slot[0]===s[0]?`<div class="ck">${IC.check2||IC.chevR}</div>`:''}</div>`).join('')}
      </div>
      <button class="kbtn sec" data-act="plan-own-time">${T('Предложить своё время','Suggest my own time')}</button>
    </div>
    ${PLAN&&PLAN.slot?`<div class="kfoot"><button class="kbtn pri tall" data-act="plan-pick-place">${T('Дальше — место','Next: pick a place')}</button></div>`:''}</div>`;
}

// ---- 6. Pick a place ----
function scr_pickplace(){
  const ps=planPlaces();
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      <div style="display:flex;align-items:center;gap:8px">
        ${kprompt(T('Планируем встречу','Planning the meetup'))}
        <div class="kdraft">${masc('map',' xs')}${T('Черновик','Draft plan')}</div></div>
      <div class="kbub ag">${UILANG==='ru'?('Выбери место — предложим его '+esc((PLAN&&PLAN.cand&&PLAN.cand.name)||''))
        :('Pick a place — we’ll suggest it to '+esc((PLAN&&PLAN.cand&&PLAN.cand.name)||''))}</div>
      <div class="kmap">${IC.photo}
        <span class="pin" style="left:30%;top:55%">${IC.pinDot}</span>
        <span class="pin" style="left:52%;top:28%">${IC.pinDot}</span>
        <span class="pin" style="left:70%;top:45%">${IC.pinDot}</span></div>
      <div class="k-title">${T('Рекомендуем рядом','Recommended nearby')}</div>
      <div style="display:flex;flex-direction:column;gap:8px">
        ${ps.map((p,i)=>`<div class="kplace ${PLAN&&PLAN.place&&PLAN.place.name===p.name?'on':''}" data-act="pick-place" data-i="${i}">
          <div class="ph"></div>
          <div class="bd"><div class="nm">${esc(p.name)}</div>
            ${p.note?`<div class="meta"><span class="mi">${IC.info}${esc(p.note)}</span></div>`:''}</div></div>`).join('')}
      </div>
      <button class="kbtn sec" data-act="plan-own-place">${IC.plusCircle} ${T('Предложить другое место','Suggest another place')}</button>
    </div>
    ${PLAN&&PLAN.place?`<div class="kfoot"><button class="kbtn pri tall" data-act="plan-send">${T('Отправить план','Send the plan')}</button></div>`:''}</div>`;
}

// ---- 7/8. Awaiting confirmation + confirmed ----
function participants(){
  const c=PLAN&&PLAN.cand;
  const st=PLAN&&PLAN.confirmed?T('Подтвердил(а)','Confirmed'):T('Ждём подтверждения','Awaiting confirmation');
  return `<div class="kpair">
    <div class="p"><div class="av">${IC.person}</div><div class="nm">${esc(DATA.name||'')}</div>
      <div class="su">${T('Организатор','Organiser')}</div></div>
    <div class="p"><div class="av">${IC.person}</div><div class="nm">${esc(c?c.name:'')}${c&&c.age?(', '+c.age):''}</div>
      <div class="su">${st}</div></div></div>`;
}
function planCardBlock(){
  const p=PLAN&&PLAN.place;
  return `<div class="kplan tight">
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
      <div class="k-title">${T('План встречи','Meetup plan')}</div>
      <div class="kdraft">${IC.spark}${T('Черновик','Draft plan')}</div></div>
    <div class="kplanrow"><div class="ic">${IC.calen}</div><div class="bd">
      <div class="ti">${esc((PLAN&&PLAN.slot&&PLAN.slot[1])||'')}</div>
      <div class="su">${esc((PLAN&&PLAN.slot&&PLAN.slot[0])||'')}</div></div></div>
    <div class="kplanrow"><div class="ic">${IC.pin}</div><div class="bd">
      <div class="ti">${esc(placeText())}</div>
      <div class="su">${p&&p.note?esc(p.note):''}</div></div></div>
  </div>`;
}
function scr_awaiting(){
  const c=PLAN&&PLAN.cand; if(!c) return scr_options();
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('План встречи','Meetup plan'))}
      <div class="kbub ag">${esc(c.name)} ${T('и ты согласовали план. Ждём подтверждения.','and you have agreed on the plan. We’re waiting for confirmation.')}</div>
      <div style="display:flex;align-items:flex-end;justify-content:space-between">
        <div class="k-title">${T('Участники','Participants')}</div><div class="k-label" style="color:var(--muted)">[2]</div></div>
      ${participants()}
      ${planCardBlock()}
      <div class="kwhy">${esc(c.name)} ${T('получит уведомление и сможет подтвердить или предложить изменения.','will get a notification and can confirm or suggest changes.')}</div>
    </div>
    <div class="kfoot"><button class="kbtn pri tall" data-act="plan-wait-done">${T('Понятно, жду','Got it, waiting')}</button></div></div>`;
}
function scr_planok(){
  const c=PLAN&&PLAN.cand; if(!c) return scr_options();
  const tog=(on,act,icon,label)=>`<div class="ktogrow"><div class="ic">${icon}</div><div class="tx">${esc(label)}</div>
    <div class="ktog ${on?'on':''}" data-act="${act}"><i></i></div></div>`;
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Детали встречи','Meetup details'))}
      <div class="kbub ag">${PLAN.confirmed?T('Подтверждено обеими сторонами 🎉','Confirmed by both sides 🎉')
        :T('План собран. Ждём подтверждения второй стороны.','The plan is set. Waiting for the other side to confirm.')}</div>
      <div style="display:flex;align-items:flex-end;justify-content:space-between">
        <div class="k-title">${T('Участники','Participants')}</div><div class="k-label" style="color:var(--muted)">[2]</div></div>
      ${participants()}
      ${planCardBlock()}
      <div class="kplan tight">
        <div class="k-title">${T('Календарь','Calendar')}</div>
        <button class="kbtn sec" data-act="cal-download">${IC.calAdd} ${T('Скачать .ics','Download .ics')}</button>
        <div class="k-cap" style="color:var(--muted)">${T('Файл откроется в Google, Apple или другом календаре.','Opens in Google, Apple or any other calendar.')}</div>
      </div>
      <div class="kplan tight">
        <div class="k-title">${T('Напомнить','Remind me')}</div>
        ${tog(PLAN.remind,'tog-remind',IC.bellSm,T('За час до встречи','1 hour before'))}
      </div>
    </div>
    <div class="kfoot">
      <button class="kbtn pri tall" data-act="plan-open-chat">${T('Открыть чат встречи','Open meetup chat')}</button>
      <button class="kbtn sec" data-act="plan-pick-time">${T('Изменить план','Edit plan')}</button>
    </div></div>`;
}

// ---- 10. How is it going (status) ----
function scr_meetstate(){
  const c=PLAN&&PLAN.cand; if(!c) return scr_agenthome();
  const opt=(key,cls,icon,ti,su)=>`<div class="kstatus ${cls} ${PLAN.status===key?'on':''}" data-act="meet-status" data-k="${key}">
    <div class="ic">${icon}</div><div class="bd"><div class="ti">${esc(ti)}</div><div class="su">${esc(su)}</div></div></div>`;
  return `<div class="kflow fade">
    <div class="kbar"><div class="kback" data-act="plan-back">${IC.back}</div>
      <div class="k-title" style="flex:1;text-align:center">${T('Статус встречи','Meeting state')}</div>
      <div style="width:44px"></div></div>
    <div class="kcont">
      <div class="ecard" style="cursor:default"><div class="ph"></div>
        <div class="bd"><div><div class="ti">${T('Кофе и разговор','Coffee & conversation')}</div>
          <div class="meta"><span class="mi">${IC.clock}${esc(slotText())}</span>
            <span class="mi">${IC.pin}${esc(placeText())}</span></div></div></div></div>
      <div><div class="k-title">${T('Выбери текущий статус','Select the current status')}</div>
        <div class="k-cap" style="color:var(--muted);margin-top:4px">${T('Видно только тебе. Можно поменять позже.','Visible only to you. You can change this later')}</div></div>
      <div style="display:flex;flex-direction:column;gap:12px">
        ${opt('otw','go',IC.bolt,T('Уже иду','On my way'),T('Выхожу','I’m heading out'))}
        ${opt('late','late',IC.clock,T('Опаздываю','Running late'),T('Скажу примерно на сколько','I’ll say roughly how long'))}
        ${opt('here','here',IC.pinDot,T('Я на месте','I’m here'),T('Уже в точке встречи','Already at the meeting spot'))}
      </div>
      <div class="kinfo">${IC.shieldSm}${T('Статус видит только твой собеседник. Его можно изменить в любой момент.','Only your companion sees the status. You can change it anytime.')}</div>
    </div></div>`;
}

// ---- 12. You're here ----
function scr_mymeetup(){
  const c=PLAN&&PLAN.cand; if(!c) return scr_agenthome();
  const row=(icon,ti,su,act)=>`<div class="row" data-act="${act}"><div class="ic">${icon}</div>
    <div class="bd"><div class="ti">${esc(ti)}</div><div class="su">${esc(su)}</div></div>
    <div class="ch">${IC.chevR}</div></div>`;
  return `<div class="kflow fade">
    <div class="kbar"><div class="kback" data-act="plan-back">${IC.back}</div>
      <div class="k-title" style="flex:1;text-align:center">${T('Моя встреча','My meetup')}</div>
      <div style="width:44px;cursor:pointer" data-act="security">${IC.dots}</div></div>
    <div class="kcont">
      <div class="ecard" style="cursor:default"><div class="ph"></div>
        <div class="bd"><div><div class="ti">${T('Кофе и разговор','Coffee & conversation')}</div>
          <div class="meta"><span class="mi">${IC.clock}${esc(slotText())}</span>
            <span class="mi">${IC.pin}${esc(placeText())}</span></div></div></div></div>
      <div class="kbanner"><div class="ic">${IC.checkCircle}</div>
        <div class="bd"><div class="ti">${T('Ты на месте','You’re here')}</div>
          <div class="su">${T('Встреча началась','Meetup started')} ${esc(PLAN.startedAt||'19:05')}</div></div>
        <div class="kbadge mut" data-act="meet-state">${T('Изменить','Edit')}</div></div>
      <div class="k-title">${T('Что дальше?','What’s next?')}</div>
      <div class="kacc">
        ${row(IC.clock,T('Опаздываю','Running late'),T('Сообщить, если время сдвигается','Tell them if the time shifts'),'meet-late')}
        ${row(IC.userLeave,T('Уже ушёл(ла)','Already left'),T('Отметить встречу завершённой','Mark the meetup as finished'),'meet-finish')}
        ${row(IC.help,T('Нужна помощь?','Need help?'),T('Поддержка и подсказки','Get support and tips'),'security')}
      </div>
      <div class="kinfo">${IC.shieldSm}${T('Эти действия видны только тебе и помогают чувствовать себя спокойно.','These actions are visible only to you and help you feel in control.')}</div>
    </div></div>`;
}

// ---- security bottom sheet (from the coordination chat) ----
function securitySheet(){
  if(SHEET!=='security') return '';
  const row=(icon,ti,su)=>`<div class="row"><div class="ic">${icon}</div>
    <div class="bd"><div class="ti">${esc(ti)}</div><div class="su">${esc(su)}</div></div>
    <div class="ch">${IC.chevR}</div></div>`;
  return `<div class="kscrim bot" data-act="sheet-close"><div class="ksheet bottom" onclick="event.stopPropagation()">
    <div class="kgrab"></div>
    <div style="display:flex;align-items:center;justify-content:space-between">
      <div class="k-h3">${T('Безопасность','Security')}</div>
      <div data-act="sheet-close" style="cursor:pointer;color:var(--muted)">${IC.ban}</div></div>
    <div class="kacc">
      ${row(IC.shield,T('Доверенный контакт','Trusted contact'),T('Сообщить близкому, что ты на встрече','Let someone know you’re at a meetup'))}
      ${row(IC.userLeave,T('Уйти спокойно','Leave quietly'),T('Подсказки и поддержка','Get prompts and support'))}
    </div>
  </div></div>`;
}

function openPlanChat(){
  // the coordination chat is the existing match chat, seeded with the agreed plan
  const c=PLAN&&PLAN.cand; if(!c) return;
  approveIntro({name:c.name, score:c.score, km:c.km, interests:c.interests, reasons:c.reasons},
               (FLOW&&flowIntent())||{});
  if(matchWith){ matchWith.plan={slot:slotText(), place:placeText()}; matchWith.fromPlan=true; }
  render();
}
function setMeetStatus(k){
  if(!PLAN) return;
  PLAN.status=k;
  if(k==='here'){
    PLAN.here=true;
    const d=new Date(); PLAN.startedAt=('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2);
    cur='mymeetup';
  }
  render();
  toast(k==='otw'?T('Отметили: уже идёшь','Marked: on your way')
       :k==='late'?T('Отметили: опаздываешь','Marked: running late')
       :T('Отметили: ты на месте','Marked: you’re here'));
}

// ---- saved people ----
function scr_saved(){
  const list=DATA.saved||[];
  if(!list.length) return `<div class="stack fade">${emptyState(T('Пока ничего не сохранено','Nothing saved yet'),
    T('Открой профиль человека и нажми на закладку, чтобы вернуться к нему позже.','Open someone’s profile and tap the bookmark to keep them for later.'))}</div>`;
  return `<div class="stack fade" style="gap:12px">
    ${list.map(x=>`<div class="prow" data-act="cand-open" data-n="${esc(x.name)}">
      <div class="ph">${IC.person}</div>
      <div class="bd"><div class="nm"><b>${esc(x.name)}</b>${x.band?`<span class="kbadge ${x.band==='especially_close'||x.band==='strong_option'?'ok':'mut'}">${esc(bandLabel(x))}</span>`:''}</div>
        ${(x.interests||[]).length?`<div class="meta">${(x.interests||[]).slice(0,3).map(i=>`<span class="ktag">${esc(locTopic(i))}</span>`).join('')}</div>`:''}</div>
      <div class="bm" data-act="cand-save" data-n="${esc(x.name)}">${IC.bookmark}</div></div>`).join('')}</div>`;
}

// ---- calendar: a real .ics file, not a switch that pretends ----
function icsStamp(d){ return d.toISOString().replace(/[-:]/g,'').split('.')[0]+'Z'; }
function downloadIcs(){
  if(!PLAN) return;
  const slot=(PLAN.slot&&PLAN.slot[1])||'';
  const m=String(slot).match(/(\d{1,2}):(\d{2})/);
  const start=new Date(); if(m){ start.setHours(+m[1], +m[2], 0, 0); }
  if(/завтра|tomorrow/i.test((PLAN.slot&&PLAN.slot[0])||'')) start.setDate(start.getDate()+1);
  const end=new Date(start.getTime()+60*60*1000);
  const title=T('Встреча в Kleal','Kleal meetup')+' — '+((PLAN.cand&&PLAN.cand.name)||'');
  const ics=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Kleal//EN','BEGIN:VEVENT',
    'UID:'+Date.now()+'@kleal','DTSTAMP:'+icsStamp(new Date()),
    'DTSTART:'+icsStamp(start),'DTEND:'+icsStamp(end),
    'SUMMARY:'+title,'LOCATION:'+placeText(),
    'DESCRIPTION:'+T('Встреча, назначенная через Kleal','A meetup arranged through Kleal'),
    'END:VEVENT','END:VCALENDAR'].join('\r\n');
  try{
    const blob=new Blob([ics],{type:'text/calendar'});
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='kleal-meetup.ics'; document.body.appendChild(a); a.click(); a.remove();
    toast(T('Файл календаря скачан','Calendar file downloaded'));
  }catch(e){ toast(T('Не удалось создать файл','Could not create the file')); }
}

// ---- candidate actions: open, explain, send interest ----
function openCand(name){
  CAND=candOf(name); if(!CAND) return;
  CTAB='profile'; cur='candprofile'; render();
}
async function loadWhy(){
  if(!CAND||CAND._trace||CAND._traceErr) return;   // _traceErr also stops the retry loop on failure
  try{
    const r=await fetch('/api/agent/explain',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({intent:(FLOW&&flowIntent())||{topics:[]}, profile:matchProfile(),
                           ctx:{self:DATA.name||''}, candidate:CAND.name})}).then(x=>x.json());
    if(r&&r.ok&&r.trace){ CAND._trace=r.trace; }
    else { CAND._traceErr=(r&&r.error)||'no explanation returned'; }
  }catch(e){ CAND._traceErr='network'; }
  render();   // ALWAYS re-render: on a failure the pane must stop pretending it is still working
}
function sendInterest(){                          // "Interested" -> review what gets shared
  if(!CAND) return;
  planInit(CAND); cur='sendreq'; render();
}
async function planSend(){
  if(!PLAN) return;
  PLAN.sent=true; cur='waiting'; render();
  try{                                            // record the decision the engine learns from
    await fetch('/api/agent/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:PLAN.cand.name, decision:'accepted', uid:DATA.name||'me'})});
  }catch(e){}
  // ACTUALLY deliver it. This used to only ask an LLM to role-play the recipient's agent, so the
  // screen said «мы отправили твой запрос <name>» while nothing reached that account — logging in as
  // them showed no request at all. The proposal is now stored server-side and they answer it
  // themselves; nothing here decides on their behalf.
  let sent=null;
  try{
    sent=await fetch('/api/agent/propose',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({from:DATA.name||'', to:PLAN.cand.name,
        intent:(FLOW&&flowIntent())||{topics:[]},
        note:(PLAN.note||''), idem:(PLAN._idem=PLAN._idem||idemKey('send:'+Date.now()+':'+PLAN.cand.name))})}).then(x=>x.json());
  }catch(e){ sent=null; }
  PLAN.reqId=(sent&&sent.id)||null;
  PLAN.delivered=!!(sent&&sent.ok);
  PLAN.reply=null; PLAN.mutual=false;             // only the real person can make this true
  if(cur==='waiting') render();
  pollReply();
  return;
}
async function withdrawReq(){
  if(!PLAN||!PLAN.reqId) return;
  let r=null;
  try{
    r=await fetch('/api/agent/withdraw',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:PLAN.reqId, self:DATA.name||'',
                           idem:idemKey('wd:'+PLAN.reqId)})}).then(x=>x.json());
  }catch(e){ r=null; }
  if(!r){ toast(T('Нет связи — попробуй ещё раз','No connection — try again')); return; }
  if(!r.ok && r.error==='ALREADY_RESOLVED'){ toast(T('На запрос уже ответили','It was already answered')); return; }
  clearTimeout(_pollT);
  PLAN.reqId=null; PLAN.delivered=false;
  _reqGen++;
  toast(T('Запрос отозван','Request withdrawn'));
  cur='options'; render(); saveState();
}
// The answer comes from the other account, so watch for it instead of generating one.
let _pollT=null;
function pollReply(){
  clearTimeout(_pollT);
  if(!PLAN||!PLAN.reqId) return;
  _pollT=setTimeout(async()=>{
    let rs=null;
    try{ rs=await fetch('/api/agent/outbox?self='+encodeURIComponent(DATA.name||'')).then(x=>x.json()); }catch(e){}
    const mine=((rs&&rs.requests)||[]).find(r=>r.id===PLAN.reqId);
    if(mine&&mine.status!=='pending'){
      PLAN.mutual=(mine.status==='accepted');
      PLAN.answered=mine.status;
      const gone=(mine.status==='expired');
      addNotif('match', PLAN.mutual?T('Согласие: ','Accepted: ')+PLAN.cand.name
                       :gone?T('Истёк запрос: ','Request expired: ')+PLAN.cand.name
                            :T('Отказ: ','Declined: ')+PLAN.cand.name,
               PLAN.mutual?T('Можно договариваться о встрече','You can plan the meetup')
                 :gone?T('Ответа не было — запрос закрылся','No reply — the request closed')
                      :T('В этот раз не сложилось','Not this time'), null);
      if(cur==='waiting'){ cur=PLAN.mutual?'mutual':'fewmatches'; }
      render(); saveState(); return;
    }
    pollReply();                                   // still pending — keep watching
  }, 4000);
}
// ============ Figma batch 2: results, best fit, candidate profile, why suggested ============
// Everything below renders REAL candidates from /api/agent/match; "Why suggested" is the
// engine's own decision trace (/api/agent/explain), not copy written for the mockup.
let CAND=null, CTAB='profile', OPTTAB='people', SHEET=null;
function candOf(name){ return (FLOW&&FLOW.res||[]).find(c=>c.name===name)||CAND; }
function bandBadge(c){
  const b=c&&c.band;
  const cls=(b==='especially_close'||b==='strong_option')?'ok':(b==='broader_option'?'warn':'mut');
  return `<span class="kbadge ${cls}">${esc(bandLabel(c)||T('Совпадение','Match'))}</span>`;
}
function candMeta(c){
  const bits=[];
  if(c.km!=null) bits.push(`<span class="mi">${IC.pin}${c.km} ${T('км','km')}</span>`);
  if(c.readiness==='open_now') bits.push(`<span class="mi">${IC.clock}${T('свободен(на) сейчас','Free now')}</span>`);
  else if(c.readiness_ru) bits.push(`<span class="mi">${IC.clock}${esc(UILANG==='ru'?c.readiness_ru:(c.readiness_en||''))}</span>`);
  return bits.join('');
}
// Recommendation card (Figma "Best fit for your request"): photo, name, role/location, tags, band
// badge, a Kleal-summary line, and an Invite CTA. Used both in the results list and the best-fit view.
function personRow(c,i,cls){
  const photo=c.photo||'assets/match-anna.jpg';                 // demo placeholder until real photos exist
  const tags=(c.interests||[]).slice(0,3).map(x=>`<span class="rtag">${esc(x)}</span>`).join('');
  const role=(c.tagline||c.about||'').trim();
  const loc=c.area||c.city||(c.km!=null?(c.km+' '+T('км','km')):'');
  return `<div class="rcard ${cls||''}">
    <div class="rtop" data-act="cand-open" data-n="${esc(c.name)}">
      <div class="rph"><img src="${esc(photo)}" alt="" onerror="this.style.display='none'"></div>
      <div class="rbd">
        <div class="rnm">${esc(c.name)}${c.age?(', '+c.age):''}</div>
        ${role?`<div class="rrole">${esc(role.slice(0,60))}</div>`:''}
        ${loc?`<div class="rloc">${IC.pin}<span>${esc(loc)}</span></div>`:''}
      </div>
      ${bandBadge(c)}
    </div>
    ${tags?`<div class="rtags">${tags}</div>`:''}
    <div class="rsum"><div class="h">${T('Саммари Kleal:','Kleal summary:')}</div>
      <div class="tx">${esc(candSummaryLine(c))}</div></div>
    <button class="rinv" data-act="cand-open" data-n="${esc(c.name)}">${T('Пригласить','Invite')}</button>
  </div>`;
}

// The footer that answers «а это все?». It prints the real remaining count, so «показать ещё»
// is never a promise the engine cannot keep, and it distinguishes «ты посмотрел всех, кто
// подходит» from «никто не подошёл» — which used to look identical from here.
function moreFooter(){
  const p=(FLOW&&FLOW.page)||{}, rem=p.remaining||0;
  if(FLOW&&FLOW.moreBusy) return `<div class="k-cap" style="color:var(--muted);padding:10px 2px">${T('Ищу ещё…','Looking for more…')}</div>`;
  if(rem>0) return `<div style="padding:10px 0"><button class="bigbtn" data-act="flow-more">${
    T('Показать ещё','Show more')} ${rem>50?'50+':rem}</button></div>`;
  if(p.exhausted) return `<div style="padding:10px 0;display:flex;flex-direction:column;gap:8px">
    <div class="k-cap" style="color:var(--muted)">${T('Ты посмотрел всех, кто подходит под этот запрос','You have seen everyone who fits this request')}${
      p.ranked?' — '+p.ranked+' '+T('человек','people'):''}.</div>
    <button class="bigbtn" data-act="flow-widen">${T('Расширить поиск','Widen the search')}</button>
    <button class="bigbtn dark" data-act="flow-restart">${T('Начать сначала','Start over')}</button></div>`;
  return '';
}

// ---- Your options (479:14751) — tabs + Recommended + Also for you ----
// Honest banner when the engine broadened past the exact request (no wrestlers -> the sport crowd).
function broadenBanner(){
  if(!(FLOW&&FLOW.broadened)) return '';
  const note=FLOW.fbNote||T('Точного совпадения по запросу рядом нет — вот кто занимается близкими активностями.',
                            'No exact match nearby — here are people doing related activities.');
  return `<div class="kbub ag" style="background:#FFF6E5;border-color:#F2D08A">${esc(note)}</div>`;
}
function scr_options(){
  const all=(FLOW&&FLOW.res)||[];
  // was slice(1,6): the server sends eight and the last two were fetched and silently dropped
  const top=all[0], rest=all.slice(1);
  const tabs=[['people',T('Люди','People')],['groups',T('Группы','Groups')],['events',T('События и места','Events & places')]];
  const body = OPTTAB!=='people'
    ? `<div class="k-cap" style="color:var(--muted);padding:8px 2px">${T('Здесь пока пусто — Kleal ищет только людей на этом этапе.','Nothing here yet — Kleal is matching people at this stage.')}</div>`
    : `${top?`<div style="display:flex;flex-direction:column;gap:12px">
          <div class="k-h3">${T('Рекомендуем','Recommended')}</div>${personRow(top,0,'top')}</div>`:''}
       ${rest.length?`<div style="display:flex;flex-direction:column;gap:12px">
          <div class="k-h3">${T('Также для тебя','Also for you')}</div>
          <div style="display:flex;flex-direction:column;gap:12px">${rest.map((c,i)=>personRow(c,i+1)).join('')}</div></div>`:''}
       ${moreFooter()}`;
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Твои варианты','Your options'))}
      ${broadenBanner()}
      <div class="kbub ag">${T('Лучшее под твой запрос. Переключай тип.','The best fits for your request. Switch between types.')}</div>
      <div class="ktabs">${tabs.map(t=>`<div class="kchip ${OPTTAB===t[0]?'on':''}" data-act="opt-tab" data-k="${t[0]}">${t[1]}</div>`).join('')}</div>
      ${body}
    </div></div>`;
}

// One label + icon per engine feature group (matching/core_v2 _REASON). Keyed, never positional —
// the engine returns reasons sorted by weight, so position says nothing about what a row is about.
const RSN_LABEL={
  semantic_activity:   {ic:'heart', t:()=>T('Совпадают интересы','Fits your interests')},
  time_feasibility:    {ic:'clock', t:()=>T('Подходит по времени','Matches your time')},
  location_feasibility:{ic:'pin',   t:()=>T('Рядом','Close by')},
  mode_format:         {ic:'coffee',t:()=>T('Комфортный формат','Comfortable format')},
  directed_preferences:{ic:'users', t:()=>T('Подходящая роль','Matching role')},
  social_context:      {ic:'spark', t:()=>T('Похожий вайб','Similar vibe')},
  domain_constraints:  {ic:'shield',t:()=>T('Совпадают условия','Conditions fit')},   // not IC.check — that one is white-on-badge
  _:                   {ic:'spark', t:()=>T('Почему подходит','Why it fits')},
};
// ---- Best fit (479:14790) — top candidate + three plain-language reasons ----
function scr_bestfit(){
  const c=(FLOW&&FLOW.res||[])[0]; if(!c){ return scr_options(); }
  const rs=(UILANG==='ru'?c.reasons_ru:c.reasons_en)||c.reasons||[];
  // Title each row from the feature group the engine actually matched on. These arrive weight-ordered,
  // so titling by POSITION printed a distance ("рядом (3.6 км)") under the label "Подходит по времени".
  const rows=rs.slice(0,3).map((r,i)=>{const m=RSN_LABEL[(c.reason_keys||[])[i]]||RSN_LABEL._;
    return `<div class="krsn"><div class="ic">${IC[m.ic]||IC.spark}</div>
    <div class="bd"><div class="ti">${esc(m.t())}</div>
      <div class="su">${esc(r)}</div></div></div>`;}).join('');
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(FLOW&&FLOW.broadened?T('Близкие по активности','Related activities'):T('Лучшее совпадение по запросу','Best fit for your request'))}
      ${broadenBanner()}
      <div class="kfused">${personRow(c,0,'top')}${rows}</div>
    </div>
    <div class="kfoot">
      <button class="kbtn pri tall" data-act="cand-open" data-n="${esc(c.name)}">${T('Открыть профиль','Open profile')}</button>
      <button class="kbtn sec" data-act="go-options">${T('Другие варианты','See other options')}</button>
    </div></div>`;
}

// The Kleal-summary line on a candidate profile = why the agent surfaced THIS person, in plain words.
// Prefer a real summary; else stitch the top match reasons; else an honest fallback.
function candSummaryLine(c){
  if(c.klealSummary && String(c.klealSummary).trim()) return String(c.klealSummary).trim();
  if(c.summary && String(c.summary).length>24) return String(c.summary).trim();
  const rs=(UILANG==='ru'?c.reasons_ru:c.reasons_en)||c.reasons||[];
  if(rs.length) return (c.name||T('Этот человек','This person'))+' — '+rs.slice(0,2).join('; ')+'.';
  return T('Kleal счёл этого человека сильным совпадением под твой запрос.','Kleal picked this person as a strong match for your request.');
}
function scr_candprofile(){
  const c=CAND; if(!c) return scr_options();
  const photo=c.photo||'assets/match-anna.jpg';                 // demo placeholder until real photos exist
  const tags=(c.interests||[]).slice(0,6).map(x=>`<span class="tg">${esc(x)}</span>`).join('');
  const langs=(c.langs||[]).join(', ');
  const loc=c.area||c.city||(c.km!=null?(c.km+' '+T('км','km')):'');
  const bio=esc(c.tagline||c.about||c.summary||'');
  return `<div class="kflow cpub fade">
    <div class="chero">
      <img src="${esc(photo)}" alt="" onerror="this.style.display='none'">
      <div class="cnav">
        <div class="cbtn" data-act="cand-back">${IC.back}</div>
        <div class="cbtn" data-act="cand-opts" data-n="${esc(c.name)}">${IC.dots}</div>
      </div>
    </div>
    <div class="cpb">
      <div class="chd">
        <div class="nm">${esc(c.name)}${c.age?(', '+c.age):''}${c.verified?`<span class="vf">${IC.verify}</span>`:''}</div>
        ${bio?`<div class="bio">${bio}</div>`:''}
        ${tags?`<div class="tgs">${tags}</div>`:''}
        ${langs?`<div class="meta">${IC.globe}<span>${esc(langs)}</span></div>`:''}
        ${loc?`<div class="meta">${IC.pin}<span>${esc(loc)}</span></div>`:''}
      </div>
      <div class="ksum">
        <div class="h">${T('Саммари Kleal','Kleal summary')}</div>
        <div class="tx">${esc(candSummaryLine(c))}</div>
      </div>
      <div class="cpriv">${IC.shield}<span>${T('Тебя видят только те, кого рекомендовал твой агент. Ты управляешь этим.',"Only people your agent recommended can see your profile. You're in control.")}</span></div>
    </div>
    <div class="cfoot">
      <button class="cinv" data-act="cand-interest">
        <span class="ck">${IC.check}</span>
        <span class="lb">${T('Пригласить','Invite')}</span>
        <span class="ch">${IC.chevR}${IC.chevR}${IC.chevR}</span></button>
    </div>
    <div class="bnav">${bnavHTML()}</div></div>`;
}
function dropCand(n){ if(n&&FLOW&&FLOW.res) FLOW.res=FLOW.res.filter(x=>x&&x.name!==n); }
// Profile-options bottom sheet (Not interested / Report / Block / Cancel). Report/block have no
// backend yet — they hide the person locally and acknowledge; wiring to a real safety endpoint is a
// backend task, flagged rather than faked as "done".
function candOptsSheet(){
  if(SHEET!=='candopts') return '';
  const nm=(CAND&&CAND.name)||'';
  const opt=(cls,icon,label,act,dn)=>`<button class="coptbtn ${cls}" data-act="${act}"${dn?` data-n="${esc(dn)}"`:''}>${icon?`<span class="i">${icon}</span>`:''}${esc(label)}</button>`;
  return `<div class="kscrim bot" data-act="sheet-close"><div class="ksheet bottom copts" onclick="event.stopPropagation()">
    <div class="kgrab"></div>
    <div class="chdr"><div class="k-h3">${T('Опции профиля','Profile options')}</div>
      <div data-act="sheet-close" class="x">${IC.ban}</div></div>
    ${opt('mute', IC.ban,      T('Не интересно','Not interested'),  'cand-notint', nm)}
    ${opt('warn', IC.flag,     T('Пожаловаться','Report profile'),  'cand-report', nm)}
    ${opt('warn', IC.userLock||IC.shield, T('Заблокировать','Block')+(nm?' '+nm:''), 'cand-block', nm)}
    ${opt('dark', '',          T('Отмена','Cancel'),                'sheet-close')}
  </div></div>`;
}
function candProfilePane(c){
  const ints=(c.interests||[]).map(x=>`<span class="kchip soft" style="height:32px">${esc(x)}</span>`).join('');
  const facts=[(c.vibe&&String(c.vibe).length>2)?T('Вайб: ','Vibe: ')+c.vibe:null, c.verified?T('Профиль подтверждён','Verified profile'):null,
               c.km!=null?(T('в ','')+c.km+' '+T('км от тебя','km away')):null,
               (c.langs||[]).length?T('Языки: ','Languages: ')+(c.langs||[]).join(', '):null].filter(Boolean);
  return `<div class="cprof"><div class="av">${IC.person}${c.readiness==='open_now'?'<i class="dot"></i>':''}</div>
      <div class="bd"><div class="k-h3">${esc(c.name)}${c.age?(', '+c.age):''}</div>
        ${bandBadge(c)}
        <div class="k-cap" style="color:var(--muted)">${esc((c.interests||[]).slice(0,2).join(' · '))}</div></div></div>
    <div class="kplan flat">
      <div class="kblk"><div class="hd">${T('О себе','About')}</div>
        <div class="tx">${esc(c.about||c.summary||T('Пока без описания — этот человек ещё не заполнил его.','No bio yet — this person hasn’t written one.'))}</div></div>
      ${ints?`<div class="kblk"><div class="hd">${T('Интересы','Interests')}</div>
        <div class="kchips">${ints}</div></div>`:''}
      ${facts.length?`<div class="kblk"><div class="hd">${T('Образ жизни','Lifestyle')}</div>
        <div class="kfacts">${facts.map(f=>`<div class="kfact"><i></i>${esc(f)}</div>`).join('')}</div></div>`:''}
      <div class="kblk">
        <div style="display:flex;gap:8px;align-items:center">
          <button class="kbtn pri sm" style="flex:1" data-act="cand-interest">${T('Интересно','Interested')}</button>
          <div class="kback" style="width:40px;height:40px" data-act="cand-save" data-n="${esc(c.name)}">${IC.bookmark}</div></div>
        <div class="k-cap" style="color:var(--muted)">${T('Kleal спросит','Kleal will ask')} ${esc(c.name)} ${T('перед тем, как открыть чат.','before opening the chat.')}</div></div>
    </div>`;
}
// the trace ships engine-side details ("open now", "3.6 km"); render them in the UI language,
// and drop values too short to mean anything to a human (a one-letter vibe helps nobody)
function whyDetail(f){
  let d=String(f.detail||'').trim();
  if(!d) return '';
  if(UILANG==='ru'){
    d=d.replace(/\bopen now\b/i,'свободен(на) сейчас').replace(/\bmay be busy\b/i,'может быть занят(а)')
       .replace(/\bsame community\b/i,'то же сообщество').replace(/ km\b/,' км');
  }
  if(f.group==='social_context'&&d.length<3) return '';
  return d;
}
function candWhyPane(c){
  const tr=CAND&&CAND._trace;
  // An explanation can genuinely fail — most often the candidate has left the matching store since the
  // search ran. Saying so beats a spinner that never resolves and implies work is still happening.
  if(!tr && CAND && CAND._traceErr) return `<div class="k-cap" style="color:var(--muted);padding:8px 2px">
    ${T('Не удалось получить объяснение — карточка могла устареть. Запусти поиск заново.',
        'Could not load the explanation — this card may be out of date. Try searching again.')}</div>`;
  if(!tr) return `<div class="k-cap" style="color:var(--muted);padding:8px 2px">${T('Считаю объяснение…','Working out the explanation…')}</div>`;
  // Same rule the engine applies to the card's reasons (core_v2._presentation): never claim availability
// that the readiness chip contradicts. The raw trace legitimately keeps 'open now' — feature states are
// computed before the receiving policy — but showing it here put «Время: свободен(на) сейчас» two rows
// above «Готовность: не сейчас — тихие часы» on the same screen. The admin lab still sees the full trace.
  const rdyOK=(tr.readiness||c.readiness)==='open_now';
  const good=(tr.features||[]).filter(f=>f.state==='known_match'&&whyDetail(f)
                                       &&(rdyOK||f.group!=='time_feasibility'));
  const miss=(tr.features||[]).filter(f=>f.state==='unknown');
  const card=(title,items,neg)=>items.length?`<div class="kwhycard">
      <div class="k-label">${esc(title)}</div>
      ${items.map(it=>`<div class="kbullet ${neg?'neg':''}"><div class="dot">${neg?'':IC.check}</div>
        <div class="tx">${esc(it)}</div></div>`).join('')}</div>`:'';
  return `<div class="k-h3" style="margin:4px 0">${T('Почему подобрал','Why suggested')}</div>
    ${card(T('Что совпало','What matched'), good.map(f=>(UILANG==='ru'?f.label_ru:f.label_en||f.label_ru)+': '+whyDetail(f)))}
    ${card(T('Уровень и готовность','Level and readiness'),
      [T('Уровень: ','Level: ')+(tr.band_ru||tr.band||''), T('Готовность: ','Readiness: ')+(tr.readiness_ru||tr.readiness||'')])}
    ${card(T('Пока не хватает данных','Still unknown'), miss.map(f=>(UILANG==='ru'?f.label_ru:f.label_en||f.label_ru)), true)}`;
}
function candVisPane(c){
  const items=[T('Твоё имя, возраст, город','Your name, age, city'),
    T('Короткое описание и интересы','Short bio and interests'),
    T('Что ты ищешь и образ жизни','What you’re looking for & lifestyle')];
  return `<div class="k-h3" style="margin:4px 0">${T('Что увидит другая сторона','What the other side will see')}</div>
    <div class="kwhycard">${items.map(i=>`<div class="kbullet"><div class="dot">${IC.check}</div><div class="tx">${esc(i)}</div></div>`).join('')}</div>
    <div class="kwhy">${T('Телефон, соцсети и точный адрес не показываются.','They won’t see your phone, socials or exact address.')}</div>`;
}
// ---- bottom edit sheets (Figma: Social formats PopUp / Location PopUp / basics / goal) ----
// Every card edit used to open the full-screen chat editor. Direct fields deserve a direct control:
// a bottom sheet with «Принять изменения», which writes DATA, mirrors the display row, and pushes
// the patch to the server row that matching actually reads. The chat editor stays for the fuzzy
// sections (interests, personality) — that is literally the Figma «Edit with Kleal».
let ESHEET=null;
// The Location sheet used to show a decorative CSS circle that grew by pixels — it carried no scale,
// so "32 км" meant nothing visually. It is a real Leaflet map now: the radius drawn over the actual
// city, the view always fitted to the circle, and a metric scale bar, so you can see how far it is.
let eshMap=null, eshCircle=null;
function locSheetCenter(area){
  const k=cityKey(area||'');                       // reuse the Explore map's city table
  if(k&&CITY_LATLON[k]) return CITY_LATLON[k];
  if(DATA.geo&&DATA.geo.coarseLat!=null) return [DATA.geo.coarseLat,DATA.geo.coarseLon];
  return null;
}
function initLocSheetMap(){
  const el=document.getElementById('eshMap'); if(!el) return;
  if(eshMap){ try{ eshMap.remove(); }catch(_e){} eshMap=null; eshCircle=null; }
  if(typeof L==='undefined') return;
  const d=(ESHEET&&ESHEET.draft)||{};
  const c=locSheetCenter(d.area);
  if(!c){                                          // unknown city: say so instead of drawing a fake map
    el.innerHTML=`<div class="k-cap" style="color:var(--muted);height:100%;display:flex;align-items:center;justify-content:center;text-align:center;padding:0 14px">${
      T('Не знаю такой город — радиус всё равно сохранится','City not recognised — the radius is still saved')}</div>`;
    return;
  }
  el.innerHTML='';
  const map=L.map(el,{zoomControl:false,attributionControl:false,dragging:false,scrollWheelZoom:false,
                      doubleClickZoom:false,touchZoom:false,boxZoom:false,keyboard:false});
  // A view MUST exist before layers are added: circle.getBounds() projects through the map, so
  // fitBounds on a view-less map throws and (inside the try/catch) silently left a blank container.
  map.setView(c, 11);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{maxZoom:19}).addTo(map);
  L.control.scale({metric:true,imperial:false,position:'bottomleft'}).addTo(map);
  eshCircle=L.circle(c,{radius:(+d.radiusKm||10)*1000,color:'#F5455C',weight:2,
                        fillColor:'#F5455C',fillOpacity:.12}).addTo(map);
  L.circleMarker(c,{radius:4,color:'#F5455C',fillColor:'#F5455C',fillOpacity:1,weight:2}).addTo(map);
  const fit=()=>{ try{ map.invalidateSize(); map.fitBounds(eshCircle.getBounds(),{padding:[16,16]}); }catch(_e){} };
  fit(); setTimeout(fit,80);
  eshMap=map;
}
// Live while dragging the slider: grow the circle and refit, so the zoom itself shows the distance.
function locSheetRadius(km){
  if(!eshMap||!eshCircle) return;
  eshCircle.setRadius((+km||10)*1000);
  try{ eshMap.fitBounds(eshCircle.getBounds(),{padding:[16,16]}); }catch(_e){}
}
const GENDER_OPTS=()=>[['Male',T('Мужчина','Male')],['Female',T('Женщина','Female')],['Other',T('Другое','Other')]];
const SHEET_LANGS=['en','es','ru','fr','de','it','ca','pt','sr','uk','pl','sv'];
function openSheet(kind, idx){
  if(kind==='location') ESHEET={kind, draft:{area:DATA.area||'', radiusKm:DATA.radiusKm||10}};
  else if(kind==='languages') ESHEET={kind, draft:(DATA.langsList||[]).slice()};
  else if(kind==='basics') ESHEET={kind, draft:{age:DATA.age||'', gender:DATA.gender||''}};
  // The section sheets (Figma: Interests Edit / Personality Edit / Safety). Each
  // drafts a COPY — nothing touches DATA until «Принять изменения».
  else if(kind==='interests') ESHEET={kind, draft:(DATA.interests||[]).map(i=>({name:i.name,used:i.used!==false})), add:''};
  else if(kind==='personality') ESHEET={kind, draft:{text:personalityText()}};
  else if(kind==='safety') ESHEET={kind, draft:Object.assign({}, DATA.safety||{})};
  else return;
  render();
}
function eSheetHTML(){
  const e=ESHEET; if(!e) return '';
  let title='', body='', extra='';
  if(e.kind==='location'){
    const km=+e.draft.radiusKm||10;
    const kmTxt=v=>v+' '+T('км','km');
    title=T('Локация','Location');
    body=`<input id="eshArea" class="kinput" value="${esc(e.draft.area)}" placeholder="${T('Город','City')}"
        onchange="ESHEET.draft.area=this.value;initLocSheetMap()">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-top:12px">
        <span class="k-small">${T('Как далеко готов(а) ехать?','How far are you happy to go?')}</span>
        <span class="k-small" id="eshKmL" style="color:var(--primary);font-weight:700">${kmTxt(km)}</span></div>
      <input id="eshKm" type="range" min="1" max="50" value="${km}" style="width:100%;accent-color:var(--primary)"
        oninput="ESHEET.draft.radiusKm=+this.value;document.getElementById('eshKmL').textContent=this.value+' ${T('км','km')}';locSheetRadius(this.value)">
      <div id="eshMap" class="eshmap"></div>`;
  } else if(e.kind==='languages'){
    title=T('Языки','Languages');
    body='<div class="kchips">'+SHEET_LANGS.map(c=>`<div class="kchip ${e.draft.includes(c)?'on':''}" data-act="esheet-lang" data-v="${c}">${esc(langName(c))}</div>`).join('')+'</div>';
  } else if(e.kind==='basics'){
    title=T('Основное','Basics');
    body=`<div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
        <div class="ava" style="width:64px;height:64px;flex:none;cursor:pointer${DATA.photo?`;background-image:url(${DATA.photo});background-size:cover;background-position:center`:''}" data-act="edit-photo">${DATA.photo?'':IC.person}</div>
        <button class="kbtn sec sm" style="width:auto;padding:0 16px" data-act="edit-photo">${DATA.photo?T('Сменить фото','Change photo'):T('Добавить фото','Add photo')}</button>
      </div>
      <div class="k-label" style="color:var(--muted)">${T('Возраст','Age')}</div>
      <input id="eshAge" class="kinput" inputmode="numeric" value="${esc(String(e.draft.age||''))}">
      <div class="k-label" style="color:var(--muted);margin-top:12px">${T('Пол','Gender')}</div>
      <div class="kchips">${GENDER_OPTS().map(g=>`<div class="kchip ${e.draft.gender===g[0]?'on':''}" data-act="esheet-gender" data-v="${g[0]}">${g[1]}</div>`).join('')}</div>`;
  } else if(e.kind==='interests'){
    title=T('Интересы','Interests');
    body=`<div class="k-small" style="color:var(--muted);margin-bottom:8px">${T('Отметь, что Kleal может использовать для подбора.','Pick what Kleal may use for matching.')}</div>`
      +(e.draft.length?e.draft.map((it,i)=>`<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 2px">
          <div style="font-size:14.5px;min-width:0;overflow:hidden;text-overflow:ellipsis">${esc(it.name)}</div>
          <div style="display:flex;align-items:center;gap:10px;flex:none">
            <div class="sw ${it.used?'on':''}" data-act="esheet-int" data-v="${i}"><i></i></div>
            <div style="cursor:pointer;color:var(--muted);padding:2px 4px" data-act="esheet-int-del" data-v="${i}">✕</div>
          </div></div>`).join('')
        :`<div class="k-cap" style="color:var(--muted)">${T('Пока нет интересов.','No interests yet.')}</div>`)
      +`<input id="eshAdd" class="kinput" style="margin-top:10px" placeholder="${T('Добавить интерес…','Add an interest…')}">
        <button class="kbtn sec sm" style="margin-top:8px;width:auto;padding:0 16px" data-act="esheet-int-add">${T('Добавить','Add')}</button>`;
  } else if(e.kind==='personality'){
    title=T('Моя личность по тесту Kleal','My personality by Kleal test');
    // The chips are the raw inputs behind the prose, so they belong on the same edit surface as the
    // prose — and the screen behind now belongs to the story.
    const sc=DATA.social||{vibe:[],depth:[]};
    const ch=(arr,act)=>`<div class="kchips" style="margin-top:8px">${arr.map((v,i)=>
      `<div class="kchip ${v[1]?'on':''}" data-act="${act}" data-v="${i}">${esc(locTopic(v[0]))}</div>`).join('')}</div>`;
    extra='';
    // Auto-grow rather than a scrollbar inside a scrollbar: the block should read as a paragraph,
    // not as a text field with its own hidden overflow.
    const rows=Math.max(5, Math.min(22, Math.ceil((e.draft.text||'').length/34)));
    body=`<textarea id="eshPers" class="pertx" rows="${rows}" spellcheck="false"
        oninput="ESHEET.draft.text=this.value;this.style.height='auto';this.style.height=this.scrollHeight+'px'"
        placeholder="${T('Kleal ещё не описал тебя — поговори с ним, и текст появится здесь.','Kleal has not described you yet — talk to it and the text will appear here.')}">${esc(e.draft.text||'')}</textarea>`
      +((sc.vibe&&sc.vibe.length)?`<div style="margin-top:18px">
          <div class="sumlbl">${T('Вайб','Vibe')}</div>
          <div class="seccap" style="margin:2px 0 0">${T('Отметь, что Kleal может использовать для подбора.','Pick what Kleal may use for matching.')}</div>
          ${ch(sc.vibe,'social-vibe')}
          ${(sc.depth&&sc.depth.length)?`<div class="sumlbl" style="margin-top:16px">${T('Глубина общения','Conversation depth')}</div>`+ch(sc.depth,'social-depth'):''}
        </div>`:'');
  } else if(e.kind==='safety'){
    title=T('Безопасность и приватность','Safety & Privacy');
    body=safetyGroups(e.draft).map(gr=>`<div style="margin-bottom:14px">
        <div class="k-label" style="color:var(--muted);margin-bottom:4px">${esc(gr.t||'')}</div>
        ${gr.items.filter(it=>it.k==='tog'||it.k==='choice'||it.k==='sub').map(it=>
          it.k==='choice'
            ? `<div class="crow2">${sTt(it.label,it.desc)}<div class="seg">${it.options.map((o,i)=>
                `<button class="${i===it.sel?'sel':''}" data-act="esheet-autonomy" data-v="${i}">${esc(o)}</button>`).join('')}</div></div>`
            : safetyRow(it,'esheet-sflag')).join('')}
      </div>`).join('');
  }
  return `<div class="kscrim bot" data-act="esheet-close"><div class="ksheet bottom${e.kind==='personality'?' tall':''}" onclick="event.stopPropagation()">
    <div class="kgrab"></div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
      <div class="k-h3">${title}</div><div style="cursor:pointer;padding:4px;color:var(--muted)" data-act="esheet-close">✕</div></div>
    <div class="esbody">${body}</div>
    <div class="iacts" style="margin-top:16px;flex:none">${extra}
      <button class="kbtn pri tall" style="flex:1" data-act="esheet-accept">${T('Принять изменения','Accept changes')}</button></div>
  </div></div>`;
}
function acceptSheet(){
  const e=ESHEET; if(!e) return;
  if(e.kind==='location'){
    const a=document.getElementById('eshArea'), km=document.getElementById('eshKm');
    if(a&&a.value.trim()) DATA.area=a.value.trim();
    if(km) DATA.radiusKm=+km.value;
    pushProfile({area:DATA.area, radiusKm:DATA.radiusKm});
  }
  else if(e.kind==='languages'){ DATA.langsList=e.draft.slice(); pushProfile({langs:DATA.langsList}); }
  else if(e.kind==='basics'){
    const ag=document.getElementById('eshAge'), v=ag?parseInt(ag.value,10):NaN;
    if(v>=18&&v<=120) DATA.age=v;
    if(e.draft.gender) DATA.gender=e.draft.gender;
    pushProfile({age:DATA.age, gender:DATA.gender});
  }
  else if(e.kind==='interests'){
    const by={}; (DATA.interests||[]).forEach(i=>by[i.name]=i);
    DATA.interests=e.draft.map(d=>Object.assign({}, by[d.name]||{name:d.name,icon:editIcon(d.name),conf:'Medium'}, {used:d.used}));
    DATA.matchingPaths=DATA.interests.filter(i=>i.used!==false).slice(0,3).map(i=>i.name);
    setSnap('Interests','spark',DATA.interests.map(i=>i.name).join(' · '));
    pushProfile({interests:DATA.interests.filter(i=>i.used!==false).map(i=>i.name)});
  }
  else if(e.kind==='personality'){
    const el=document.getElementById('eshPers');
    setPersonality(el?el.value:(e.draft.text||''));
    pushProfile({personality:DATA.personality});
    adaptSummary().then(ok=>{ if(ok) render(); });   // the summary follows the personality, not vice versa
  }
  else if(e.kind==='safety'){
    DATA.safety=Object.assign({}, DATA.safety||{}, e.draft);
    pushProfile({safety:{publicPlacesOnly:!!DATA.safety.publicFirst,
                         verifiedOnly:!!DATA.safety.preferVerified,
                         hideExactLocation:!DATA.safety.publicMap}});
  }
  const kind=e.kind;
  ESHEET=null; syncBasicsRows(); render(); saveState(); toast(T('Сохранено','Saved'));
  // The summary states these facts out loud, so it has to be rewritten when they change. Guarded by
  // _resumBusy, and adaptSummary already refuses a rewrite that would shorten or replace the text.
  if(['location','languages','basics','interests'].indexOf(kind)>=0)
    adaptSummary().then(okk=>{ if(okk) render(); });
}

// ---------------- Settings (Figma "Settings") ----------------
// Reached from the gear in the app bar on Agent Home / Overview. Rows are wired to the things that
// really exist in this app; the two the product has no backend for (auth, billing) are rendered
// visibly disabled rather than as live rows that lead nowhere.
function setRow(icon, label, opts){
  const o=opts||{};
  const right = o.tog!==undefined
      ? `<div class="sw ${o.tog?'on':''}" style="pointer-events:none"></div>`
      : (o.disabled ? '' : `<div style="color:var(--muted);flex:none">${IC.chevR}</div>`);
  const val = o.val ? `<div class="k-label" style="color:var(--muted);flex:none;margin-right:2px">${esc(o.val)}</div>` : '';
  return `<div class="card" style="padding:0;margin-bottom:10px;${o.disabled?'opacity:.45':''}">
    <div class="setrow" ${o.disabled?'':`data-act="${o.act}"`} style="${o.disabled?'cursor:default':'cursor:pointer'}">
      <div class="sic">${IC[icon]||IC.gear}</div>
      <div class="st"><div class="stt">${esc(label)}</div>
        ${o.sub?`<div class="sts">${esc(o.sub)}</div>`:''}</div>
      ${val}${right}</div></div>`;
}
function scr_settings(){
  const soon=T('появится позже','coming later');
  return `<div class="fade" style="padding-top:4px">
    ${setRow('edit',   T('Личные данные','Edit Personal Info'), {act:'set-personal'})}
    ${setRow('userLock',T('Смена пароля','Change Password'),    {disabled:true, sub:soon})}
    ${setRow('boxx',   T('Способ оплаты','Payment Method'),      {disabled:true, sub:soon})}
    ${setRow('bell',   T('Уведомления','Notifications'),         {act:'set-notifs', tog:notifsOn()})}
    ${setRow('globe',  T('Язык','Language'),                     {act:'set-language', val:(UILANG==='ru'?'Русский':'English')})}
    ${setRow('chat',   T('Помощь и поддержка','Help & Support'), {act:'set-help'})}
    ${setRow('shield', T('Приватность и безопасность','Privacy & Security'), {act:'set-privacy'})}
    ${setRow('moon',   T('Тёмная тема','Dark Mode'),
        {act:'set-dark', tog:darkOn(), sub:T('Тема пока не применяется','Theme not applied yet')})}
    <button class="bigbtn" style="background:var(--fg);color:#fff;margin-top:14px" data-act="set-logout">${T('Выйти','Log out')}</button>
  </div>`;
}
// Notifications is a REAL preference: addNotif() checks it, so turning it off actually stops Kleal
// writing to the notification list rather than only remembering a switch position.
function notifsOn(){ return ((DATA.prefs||{}).notifs)!==false; }
function darkOn(){ return !!((DATA.prefs||{}).dark); }
function twoFAOn(){ return !!((DATA.security||{}).twoFA); }
function bioOn(){ return !!((DATA.security||{}).biometric); }
// Privacy & Security settings screen. 2FA and biometrics are saved preferences, not yet enforced —
// there is no account/sign-in layer to enforce them (logout is just localStorage.clear). The copy
// says so plainly rather than implying the app is now protected. The account-level privacy controls
// that DO work (visibility, blocking, verified-only) already live in scr_safety and are linked below.
function scr_privacy(){
  const note=`<div class="kinfo" style="margin-bottom:12px">${IC.info}<div>${T(
    'Двухфакторная аутентификация и биометрия защитят вход, когда подключим аккаунты. Пока это сохранённые настройки — они включатся автоматически.',
    'Two-factor and biometrics will protect sign-in once accounts are connected. For now these are saved preferences that will switch on automatically.')}</div></div>`;
  return `<div class="fade" style="padding-top:4px">
    ${note}
    <div class="seclbl" style="margin:2px 2px 8px">${T('Вход в аккаунт','Account sign-in')}</div>
    ${setRow('userLock',T('Двухфакторная аутентификация','Two-factor authentication'),
        {act:'set-2fa', tog:twoFAOn(),
         sub:twoFAOn()?T('Код из приложения-аутентификатора при входе','Authenticator code on sign-in')
                      :T('Дополнительный код при каждом входе','A second code every time you sign in')})}
    ${setRow('faceScan',T('Биометрия (Face ID / отпечаток)','Biometrics (Face ID / fingerprint)'),
        {act:'set-biometric', tog:bioOn(),
         sub:bioOn()?T('Разблокировка приложения по лицу или отпечатку','Unlock the app with your face or fingerprint')
                    :T('Быстрый вход без пароля','Fast sign-in without a password')})}
    <div class="seclbl" style="margin:16px 2px 8px">${T('Приватность','Privacy')}</div>
    ${setRow('shield',T('Видимость, блокировки и данные','Visibility, blocking & data'), {act:'set-safety'})}
  </div>`;
}
function scr_help(){
  return `<div class="fade" style="padding-top:4px">
    <div class="card pad"><div class="seclbl">${T('Как работает Kleal','How Kleal works')}</div>
      <div class="sumtxt" style="font-size:13.5px;color:var(--muted);margin-top:6px">${T(
        'Опиши свободным текстом, кого или что ищешь. Kleal превращает это в запрос, находит людей с близкими интересами и сам договаривается с их агентами. Ты видишь только тех, кто тоже открыт к встрече.',
        'Describe in your own words who or what you are looking for. Kleal turns it into a request, finds people with close interests and talks to their agents for you. You only see people who are open to meeting too.')}</div></div>
    <div class="card pad" style="margin-top:10px"><div class="seclbl">${T('Что видят другие','What others see')}</div>
      <div class="sumtxt" style="font-size:13.5px;color:var(--muted);margin-top:6px">${T(
        'Имя, возраст, район города и общие интересы. Точное местоположение не показывается никогда. Фото открывается постепенно, по мере общения.',
        'Your name, age, city area and shared interests. Your exact location is never shown. Photos unblur gradually as you talk.')}</div></div>
    <div class="card pad" style="margin-top:10px"><div class="seclbl">${T('Если что-то не так','If something is wrong')}</div>
      <div class="sumtxt" style="font-size:13.5px;color:var(--muted);margin-top:6px">${T(
        'Настройки приватности и блокировки собраны в разделе «Приватность и безопасность». Канал поддержки ещё не подключён — он появится вместе с аккаунтами.',
        'Privacy controls and blocking live under Privacy & Security. A support channel is not connected yet — it arrives together with accounts.')}</div></div>
  </div>`;
}
const SCREENS={agenthome:scr_agenthome,overview:scr_overview,interests:scr_interests,social:scr_social,persona:scr_persona,
  safety:scr_safety,memory:scr_memory,knows:scr_knows,
  intents:scr_intents,search:scr_search,messages:scr_messages,
  notifs:scr_notifications,matchchat:scr_matchchat,
  reqcomposer:scr_reqcomposer,fmt:scr_fmt,gsize:scr_gsize,detail:scr_detail,clarify:scr_clarify,summary:scr_summary,searching:scr_searching,fewmatches:scr_fewmatches,
  options:scr_options,bestfit:scr_bestfit,candprofile:scr_candprofile,
  sendreq:scr_sendreq,waiting:scr_waiting,mutual:scr_mutual,suggestion:scr_suggestion,
  picktime:scr_picktime,pickplace:scr_pickplace,awaiting:scr_awaiting,planok:scr_planok,
  meetstate:scr_meetstate,mymeetup:scr_mymeetup,saved:scr_saved,
  settings:scr_settings,help:scr_help,privacy:scr_privacy};

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
  const titleFor = cur==='matchchat' ? ((matchWith&&((matchWith.cand&&matchWith.cand.name)||matchWith.who))||'Chat')
    : (cur==='overview'?T('Мой профиль Kleal','My Kleal Profile'):(TITLES()[cur]||meta[2]));
  document.getElementById('title').textContent= editSig? editSig.name : (detail? detail.name : titleFor);
  document.getElementById('back').style.visibility= (editSig||detail||!ROOTS.includes(cur))? 'visible' : 'hidden';
  // app-bar right icon: gear on Overview, refresh on drill-ins, nothing on the other root tabs
  const rgt=document.getElementById('bookmark');
  rgt.innerHTML = isHome ? IC.gear : IC.refresh;
  // no right icon on Intents/Search/Messages, nor on Settings/Help — there is nothing to refresh there
  rgt.style.visibility = ((isRoot && !isHome) || cur==='settings' || cur==='help') ? 'hidden' : 'visible';
  rgt.onclick = ()=> { if(isHome){ navTo('settings'); saveState(); }
    else toast(T('Kleal обновляет это','Kleal is refreshing this')); };
  // Every chat screen carries its OWN in-screen header (chd) and pinned composer, so hide the shared app bar
  // and the bottom nav on all of them — and treat them all the same way for layout.
  // the Figma request flow carries its own app bar + composer, exactly like the chat screens
  const chat=(cur==='matchchat'||cur==='persona'
              ||cur==='reqcomposer'||cur==='fmt'||cur==='gsize'||cur==='detail'
              ||cur==='clarify'||cur==='summary'||cur==='searching'||cur==='fewmatches'
              ||cur==='options'||cur==='bestfit'||cur==='candprofile'
              ||['sendreq','waiting','mutual','suggestion','picktime','pickplace','awaiting','planok','meetstate','mymeetup'].includes(cur));
  const bn=document.getElementById('bnav'); if(bn){ bn.style.display=chat?'none':'flex'; bn.innerHTML=bnavHTML(); }
  // The cloud sky is painted on the whole phone for the home screen only, so it bleeds behind the
  // status bar and the (now frosted) bottom nav — full-bleed, no white band.
  const ph=document.querySelector('.phone'); if(ph) ph.classList.toggle('homebg', cur==='agenthome');
  if(cur==='agenthome') setTimeout(wireIdeaCarousel,0);
  if(cur==='detail') setTimeout(()=>{
    dMapDraw();
    wireDial();
    const r=document.querySelector('input[data-act="d-km"]');
    if(r) r.oninput=()=>{ FLOW.dkm=+r.value;
      const lb=document.querySelector('.rowlbl b'); if(lb) lb.textContent=FLOW.dkm+' '+T('км','km');
      if(dCircle&&dMap){ try{ dCircle.setRadius(FLOW.dkm*1000); dMap.fitBounds(dCircle.getBounds(),{padding:[14,14]}); }catch(_e){} } };
  },0);
  // The Explore map is edge-to-edge: no app bar, no body padding, no page scroll.
  const mapfull=(cur==='search');
  const ab=document.querySelector('.appbar'); if(ab) ab.style.display=(cur==='agenthome'||chat||mapfull)?'none':'flex';
  if(editSig){ A.innerHTML=scr_editSignal(); }
  else if(detail){ A.innerHTML=scr_domain(detail); }
  else {
    // Guard: a flow screen without its state used to throw (back → FLOW=null → scr_clarify reads
    // FLOW.when → blank screen). Redirect instead of rendering a broken screen.
    startLive();                       // one live loop for the whole app, whatever screen is open
  const NEEDS_FLOW=['reqcomposer','clarify','summary','searching','fewmatches','bestfit','options'];
    const NEEDS_CAND=['candprofile'];
    const NEEDS_PLAN=['sendreq','waiting','mutual','suggestion','picktime','pickplace','awaiting','planok','meetstate','mymeetup'];
    if(NEEDS_FLOW.includes(cur)&&!FLOW) cur='agenthome';
    else if(NEEDS_CAND.includes(cur)&&!CAND) cur=(FLOW&&FLOW.res&&FLOW.res.length)?'bestfit':'agenthome';
    else if(NEEDS_PLAN.includes(cur)&&!(PLAN&&PLAN.cand)) cur=(FLOW&&FLOW.res&&FLOW.res.length)?'bestfit':'agenthome';
    try{ A.innerHTML=(SCREENS[cur]||scr_overview)(); }
    catch(err){ console.error('render failed on', cur, err); cur='agenthome'; A.innerHTML=scr_agenthome(); }
  }
  if(SHEET==='security') A.insertAdjacentHTML('beforeend', securitySheet());
  if(SHEET==='candopts') A.insertAdjacentHTML('beforeend', candOptsSheet());
  if(ESHEET) A.insertAdjacentHTML('beforeend', eSheetHTML());
  // the Location sheet carries a live Leaflet map; build it after its node exists, tear it down on close
  if(ESHEET&&ESHEET.kind==='location') setTimeout(initLocSheetMap,0);
  else if(eshMap){ try{ eshMap.remove(); }catch(_e){} eshMap=null; eshCircle=null; }
  // A chat owns the full height: the app area becomes a flex column so the thread scrolls INTERNALLY and the
  // composer stays pinned. Resetting scrollTop to 0 on every render is what made the intent chat jump — so
  // only non-chat screens reset, and chats auto-scroll their thread to the newest message.
  A.style.display=chat?'flex':''; A.style.flexDirection=chat?'column':'';
  A.style.overflowY=(chat||mapfull)?'hidden':''; A.style.padding=chat?'0 12px':(mapfull?'0':'');
  A.style.position=mapfull?'relative':'';    // containing block for the absolutely-filled map
  if(!chat) A.scrollTop=0;
  else { const bt=document.getElementById('bthread'); if(bt) bt.scrollTop=bt.scrollHeight; }
  // real Leaflet map on Explore; tear it down when leaving
  if(cur==='search'){ if(!exploreLoaded) loadExplore(); setTimeout(initExploreMap, 0); }
  else if(exploreMap){ try{ exploreMap.remove(); }catch(_e){} exploreMap=null; xLayer=null; xMarkers={}; }
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
  document.querySelectorAll('[data-msg]').forEach(el=>el.onclick=()=>openMsgThread(+el.dataset.msg));
  document.querySelectorAll('[data-savedintent]').forEach(el=>el.onclick=()=>openIntentFlow(el.dataset.savedintent));
  document.querySelectorAll('[data-notif]').forEach(el=>el.onclick=()=>openNotif(el.dataset.notif));
  document.querySelectorAll('[data-public]').forEach(el=>el.onclick=()=>{ const p=PUBLIC_INTENTS[+el.dataset.public]; if(p)toast(p.title+' — '+p.who+' · '+p.when); });
  document.querySelectorAll('[data-act]').forEach(el=>el.onclick=(ev)=>{ ev.stopPropagation(); doAct(el.dataset.act, el.dataset); });
  // Enter must do EXACTLY what the send button does. It used to call goToBuddy(), which dropped the
  // user into the old free-chat screen instead of the request flow — same field, two different apps.
  const ainput=document.getElementById('ainput'); if(ainput){ ainput.onkeydown=(e)=>{ if(e.key==='Enter'){ e.preventDefault(); flowStart(ainput.value); } }; }
  const mcin=document.getElementById('mcin'); if(mcin){ mcin.onkeydown=(e)=>{ if(e.key==='Enter')doAct('match-send',{}); }; setTimeout(()=>{try{mcin.focus();}catch(_e){}},40); }
  saveState();   // persist after every re-render (covers all doAct-driven edits)
}
// also persist after direct toggle/chip clicks that mutate state without a re-render, and on unload
A.addEventListener('click', ()=>setTimeout(saveState, 0));
window.addEventListener('beforeunload', saveState);
document.getElementById('back').onclick=()=>{ if(editSig){ editSig=null; render(); } else if(detail){ detail=null; render(); }
  else if(cur==='matchchat'){ cur=(matchWith&&matchWith.fromMessages)?'messages':'intents'; render(); }
  else if(cur==='notifs'){ cur='agenthome'; render(); }
  else if(!ROOTS.includes(cur)){ cur='overview'; render(); } };
// ---- toast + every button does something ----
function toast(msg){ let t=document.getElementById('toast');
  if(!t){ t=document.createElement('div'); t.id='toast'; t.className='toast'; document.querySelector('.phone').appendChild(t); }
  t.textContent=msg; t.classList.add('show'); clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('show'),1900); }
function doAct(act, ds){
  switch(act){
    case 'set-lang': setUILang(ds.lang); break;
    case 'set-avail': setAvail(ds.st); break;
    case 'editsum': editingSummary=true; render(); break;
    case 'cancelsum': editingSummary=false; render(); break;
    case 'savesum': { const el=document.getElementById('sumta'); setSummary(el?el.value:''); editingSummary=false; render(); toast('Summary saved'); break; }
    case 'editrow': {
      // «Личность» is a screen now, not a sheet: the story and the test live there, and the prose
      // sheet is the step AFTER it. Jumping the hub row straight into the sheet skipped the page
      // the section is actually about.
      if(ds.row==='social'){ setTab('social'); break; }
      const rt={'Basics':'basics','Location':'location','Languages':'languages',
        interests:'interests', safety:'safety'}[ds.row||''];
      openSheet(rt||'basics'); break; }
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
    case 'trusted-contact': toast(T('Доверенный контакт — скоро','Add a trusted contact — coming soon')); break;
    case 'review-memory': setTab('memory'); break;   // opens the agent-memory screen
    case 'verify-me': toast(T('Проверка фото и документов — скоро','Photo & ID verification — coming soon')); break;
    case 'blocked': toast('Your blocked list is empty'); break;
    case 'report': toast(T('Центр безопасности и жалобы — скоро','Safety centre & reporting — coming soon')); break;
    case 'export-data': toast('Preparing your data export — we’ll email you a copy'); break;
    case 'delete-account': toast('Delete account would ask you to confirm, then erase everything'); break;
    case 'createintent': flowStart(''); break;   // one chat screen; the bar carries «+ Создать интент»
    case 'intent-open': openIntentFlow(ds.id); break;
    case 'intent-del': deleteIntent(ds.id); break;
    case 'live': { const k=ds.kind||'voice'; addNotif('match',(k==='watch'?'Watch-together room opened':'Live voice room opened'),
      'Kleal is inviting nearby people to “'+((curIntent&&curIntent.title)||'your plan')+'”',null); saveState();
      toast((k==='watch'?'Watch room':'Voice room')+' created — inviting people'); break; }
    case 'broaden': broadenIntent(ds.kind); break;
    case 'resum': { if(SUMBUSY)break; SUMBUSY=true; render();
      adaptSummary().then(()=>{ SUMBUSY=false; render(); }); break; }
    case 'edit-photo': editPhoto(); break;
    case 'set-personal': openSheet('basics'); break;
    case 'set-privacy':  navTo('privacy'); break;
    case 'set-safety':   navTo('safety'); break;
    case 'set-2fa': { DATA.security=DATA.security||{}; DATA.security.twoFA=!twoFAOn(); render(); saveState();
      toast(twoFAOn()?T('2FA включится с аккаунтом','2FA turns on with your account'):T('2FA выключена','2FA off')); break; }
    case 'set-biometric': { DATA.security=DATA.security||{}; DATA.security.biometric=!bioOn(); render(); saveState();
      toast(bioOn()?T('Биометрия включится с аккаунтом','Biometrics turns on with your account'):T('Биометрия выключена','Biometrics off')); break; }
    case 'set-help':     cur='help'; render(); break;
    case 'set-language': setUILang(UILANG==='ru'?'en':'ru'); break;   // setUILang persists + re-renders
    case 'set-notifs': { DATA.prefs=DATA.prefs||{}; DATA.prefs.notifs=!notifsOn(); render(); saveState();
      toast(notifsOn()?T('Уведомления включены','Notifications on'):T('Уведомления выключены','Notifications off')); break; }
    case 'set-dark': { DATA.prefs=DATA.prefs||{}; DATA.prefs.dark=!darkOn(); render(); saveState();
      toast(T('Запомнил. Тёмная тема ещё не готова — вид не изменится.','Saved. Dark theme is not built yet — the look will not change.')); break; }
    case 'set-logout': {
      // Everything this app knows about the user lives in localStorage; clearing it IS the logout.
      if(!confirm(T('Выйти и очистить профиль на этом устройстве?','Log out and clear this profile on this device?'))) break;
      try{ localStorage.clear(); }catch(_e){}
      location.href='/'; break; }
    // ---- Explore map chrome: toggled by class/innerHTML so the Leaflet map survives ----
    case 'open-plans': { const sh=document.getElementById('xsheet'), sc=document.getElementById('xscrim');
      if(sh) sh.classList.add('on'); if(sc) sc.classList.add('on'); break; }
    case 'close-plans': { const sh=document.getElementById('xsheet'), sc=document.getElementById('xscrim');
      if(sh) sh.classList.remove('on'); if(sc) sc.classList.remove('on'); break; }
    case 'xcard-close': xDeselect(); break;
    case 'x-clear': { XQ=''; const f=document.getElementById('xq'); if(f){ f.value=''; f.focus(); }
      xSyncList(); if(exploreMap) drawExploreMarkers(); break; }
    case 'x-redo': xRedo(); break;
    case 'map-zin': if(exploreMap) exploreMap.zoomIn(); break;
    case 'map-zout': if(exploreMap) exploreMap.zoomOut(); break;
    case 'map-me': { const k=cityKey(myArea()), c=(k&&CITY_LATLON[k])||ME_LATLON;
      if(exploreMap) exploreMap.flyTo(c, 12, {duration:.6}); break; }
    case 'arch-tab': ARCHTAB=ds.v; render(); break;
    case 'meet-archive': archiveMeet(ds.id); break;
    case 'meet-msg': openMeetThread(ds.who); break;
    case 'req-yes': answerReq(ds.id,'accepted'); break;
    case 'req-no':  answerReq(ds.id,'declined'); break;
    case 'req-withdraw': withdrawReq(); break;
    case 'kleal-help': klealHelp(); break;
    case 'use-suggest': { const e=document.getElementById('mcin');
      if(e&&matchWith&&matchWith.suggest){ e.value=matchWith.suggest; e.focus(); } break; }
    case 'match-send': { const el=document.getElementById('mcin'); const t=(el&&el.value||'').trim(); if(!t||!matchWith)break;
      // The other side is a REAL person. Faking their reply (there used to be a canned list of
      // English one-liners) tells the user someone answered when nobody did — and until now the
      // opposite was just as wrong: the text was pushed into local state and never left the device,
      // so «отправлено» was shown for a message the recipient could never receive.
      matchWith.msgs.push({who:'me',text:t,t:Date.now()}); matchWith.last=t; matchWith.time='now';
      matchWith.awaiting=true; if(el) el.value='';
      render(); saveState();
      sendMsg(matchWith, t);
      break; }
    case 'join': { const p=PUBLIC_INTENTS[+ds.pi];
      if(p&&p.gid) joinGroup(+ds.pi); else joinPublic(+ds.pi); break; }
    case 'group-leave': leaveGroup(ds.gid); break;
    case 'group-host': hostGroup((DATA.intents||[]).find(x=>String(x.id)===String(ds.id))); break;
    case 'join-plan': joinPublic(+ds.pi); break;   // "Позвать" on a For-you-today card
    // Agent Home
    case 'notif': setTab('notifs'); break;
    case 'go-inbox': setTab('messages'); break;
    case 'go-onboarding': location.href='/'; break;
    // Both home entries open the buddy CHAT. Routing them straight into the intent builder turned a
    // friendly agent into a matching form: «привет» got a canned "tell me what you want to do".
    // Building an intent is a thing you ask for — by signalling it in the chat, or with the button.
    case 'agent-go': { const el=document.getElementById('ainput'); flowStart(el&&el.value||''); break; }
    // ---- Figma request flow ----
    case 'flow-back': flowBack(); break;
    case 'flow-send': { if(cur==='persona'){ const p=document.getElementById('ptestinp');
                          const v=p?p.value.trim():''; if(p) p.value=''; if(v) ptestAnswer(v); break; }
                        const el=document.getElementById('flowinp')||document.getElementById('flowinp2');
                        flowSay(el&&el.value||''); break; }
    case 'flow-hint': flowSay(ds.h||''); break;
    case 'flow-pick': { FLOW[ds.k]=(FLOW[ds.k]===ds.v?null:ds.v); render(); break; }
    case 'flow-skip': flowToSummary(); break;
    case 'flow-finish': intentStart(); break;    // opens the intent-building chat, not the final form
    case 'flow-done': flowToSummary(); break;    // inside that chat: finish and review
    case 'flow-next': flowToSummary(); break;
    case 'flow-edit': FLOW.editAll=true; cur='clarify'; render(); break;
    case 'flow-start': flowSearch(); break;
    case 'flow-adjust': FLOW.adjust=ds.k; render(); break;
    case 'flow-groups': FLOW.groups=!FLOW.groups; render(); break;
    case 'flow-apply': flowSearch(true); break;
    // Zero supply: no dead end. Save the request as a standing intent so it's matched when someone
    // with this interest appears, and drop the user into My Intents where it now lives.
    case 'flow-save-intent': {
      const it=flowIntent();
      curIntent={ title:(FLOW.intent&&FLOW.intent.title)||FLOW.request||FLOW.text||T('Новый интент','New plan'),
                  tags:(it.topics||[]), query:FLOW.request||FLOW.text, intent:it,
                  candidates:[], spec:[], status:'waiting' };
      saveCurIntent();
      toast(T('Интент сохранён — сообщу, как только кто-то появится','Saved — I will ping you when someone appears'));
      setTab('intents'); break; }
    // ---- Figma batch 2: results / candidate ----
    case 'opt-tab': OPTTAB=ds.k; render(); break;
    case 'go-options': cur='options'; render(); break;
    case 'flow-more': flowMore(); break;
    // Regenerate the openers. Rotating the pool (not re-asking the model) keeps it instant and
    // guarantees the card actually changes — a Regenerate that redraws the same three reads as broken.
    case 'flow-regen': FLOW.roll=((FLOW.roll|0)+3); render(); break;
    // Picking a format/size confirms with «Отлично!» and moves on — the design shows the answer
    // acknowledged in-place rather than a separate confirm tap.
    case 'flow-fmt': FLOW.fmt=ds.k; render(); setTimeout(()=>{ cur='gsize'; render(); }, 650); break;
    case 'flow-gsize': FLOW.gsize=ds.k; render(); setTimeout(()=>{ FLOW.dstep=1; cur='detail'; render(); }, 650); break;
    case 'd-date': FLOW.date=ds.k; render(); break;
    case 'd-km': break;   // handled live by the input listener wired after render
    case 'd-sex': FLOW.sex=ds.k; render(); break;
    case 'd-next': {
      const ad=document.getElementById('daddr'), lk=document.getElementById('dlink');
      if(ad) FLOW.addr=ad.value; if(lk) FLOW.link=lk.value;
      if(dstep()>=3) flowToSummary();
      else { FLOW.dstep=dstep()+1; render(); }
      break; }
    case 'go-intents': setTab('intents'); break;
    case 'flow-restart': seenClear(FLOW.sig||sigOf(flowIntent())); flowSearch(); break;
    // The widen controls already exist — they were only reachable when the slate came back EMPTY,
    // so a user with plenty of results could never broaden. Exhaustion is the other way in.
    case 'flow-widen': cur='fewmatches'; render(); break;
    case 'cand-open': openCand(ds.n); break;
    case 'cand-back': flowBack(); break;
    case 'cand-tab': CTAB=ds.k; render(); if(ds.k==='why') loadWhy(); break;
    case 'cand-save': { const n=ds.n||(CAND&&CAND.name); if(!n) break;
      DATA.saved=DATA.saved||[];
      const i=DATA.saved.findIndex(x=>x.name===n);
      if(i>=0){ DATA.saved.splice(i,1); toast(T('Убрано из сохранённых','Removed from saved')); }
      else { const c=candOf(n)||CAND; DATA.saved.unshift({name:n, band:c&&c.band, interests:(c&&c.interests)||[],
             km:c&&c.km, at:Date.now()}); toast(T('Сохранено','Saved')); }
      saveState(); render(); break; }
    case 'cand-interest': sendInterest(); break;
    case 'cand-opts': SHEET='candopts'; render(); break;
    case 'cand-notint': { const n=(CAND&&CAND.name)||ds.n; dropCand(n); SHEET=null;
      toast(T('Скрыто — больше не покажу','Hidden — you won’t see them again')); flowBack(); break; }
    case 'cand-report': { SHEET=null; render();
      toast(T('Спасибо. Центр безопасности посмотрит.','Thanks — our safety team will review.')); break; }
    case 'cand-block': { const n=(CAND&&CAND.name)||ds.n; dropCand(n); SHEET=null;
      toast(T('Заблокировано','Blocked')); flowBack(); break; }
    case 'sheet-close': SHEET=null; render(); break;
    case 'esheet-close': ESHEET=null; render(); break;
    case 'esheet-accept': acceptSheet(); break;
    case 'esheet-lang': { const d=ESHEET.draft, i=d.indexOf(ds.v); if(i>=0)d.splice(i,1); else d.push(ds.v); render(); break; }
    case 'esheet-gender': { const ag=document.getElementById('eshAge');
      if(ag) ESHEET.draft.age=ag.value;      // the chip tap re-renders the sheet — a typed age must survive it
      ESHEET.draft.gender=ds.v; render(); break; }
    case 'esheet-int': { const d=ESHEET.draft[+ds.v]; if(d) d.used=!d.used; render(); break; }
    case 'esheet-int-del': { ESHEET.draft.splice(+ds.v,1); render(); break; }
    case 'esheet-int-add': { const el=document.getElementById('eshAdd'), v=el?el.value.trim():'';
      if(v && !ESHEET.draft.some(x=>x.name.toLowerCase()===v.toLowerCase())) ESHEET.draft.push({name:v,used:true});
      render(); break; }
    // Vibe/depth moved out of the sheet onto the screen itself (the sheet is prose only now), so
    // they toggle DATA directly — and `vibe` is a whitelisted field, so the store follows.
    // These chips are DISPLAY only. They used to push on[0] — the first still-ticked chip in list
    // order, not the one you tapped — so with the seed defaults almost every row in the store claimed
    // vibe:'calm' whatever the user did, and unticking everything shipped ''. The engine's vibe now
    // has exactly one author: question 1 of the test.
    case 'social-vibe': { const v=(((DATA.social||{}).vibe)||[])[+ds.v];
      if(v){ v[1]=!v[1]; render(); saveState(); } break; }
    case 'social-depth': { const v=(((DATA.social||{}).depth)||[])[+ds.v];
      if(v){ v[1]=!v[1]; render(); saveState(); } break; }
    case 'esheet-sflag': { ESHEET.draft[ds.v]=!ESHEET.draft[ds.v]; render(); break; }
    case 'esheet-autonomy': { ESHEET.draft.autonomy=(+ds.v===1?'auto':'ask'); render(); break; }
    // ---- batch 3: request → mutual → plan → meetup day ----
    case 'req-edit': cur='candprofile'; render(); break;
    case 'req-send': planSend(); break;
    case 'plan-later': cur='options'; render(); break;
    case 'plan-open-chat': openPlanChat(); break;
    case 'plan-accept': PLAN.slot=PLAN.slot||planSlots()[1]; PLAN.place=PLAN.place||planPlaces()[0];
                        cur='awaiting'; render(); break;
    case 'plan-pick-time': cur='picktime'; render(); break;
    case 'pick-slot': PLAN.slot=planSlots()[+ds.i]; render(); break;
    case 'plan-own-time': toast(T('Свой вариант времени — скоро','Custom time is coming soon')); break;
    case 'plan-pick-place': cur='pickplace'; render(); break;
    case 'pick-place': PLAN.place=planPlaces()[+ds.i]; render(); break;
    case 'plan-own-place': toast(T('Своё место — скоро','Custom place is coming soon')); break;
    case 'plan-send': cur='awaiting'; render(); break;
    // This screen waits on the OTHER person. The old CTA here confirmed the plan "за обоих (демо)" —
    // the app putting words in a real person's mouth and jumping to a "confirmed" screen nobody agreed
    // to. Only their real answer can move this forward; the user just acknowledges and leaves.
    case 'plan-wait-done': cur='agenthome'; render(); saveState(); break;
    case 'plan-confirm': PLAN.confirmed=true; cur='planok'; render(); break;   // reached from a real confirmation
    case 'cal-download': downloadIcs(); break;
    case 'tog-remind': PLAN.remind=!PLAN.remind; render();
      toast(PLAN.remind?T('Напомним за час','We’ll remind you an hour before'):T('Напоминание выключено','Reminder off')); break;
    case 'plan-back': flowBack(); break;
    case 'meet-state': cur='meetstate'; render(); break;
    case 'meet-status': setMeetStatus(ds.k); break;
    case 'meet-late': setMeetStatus('late'); cur='meetstate'; render(); break;
    case 'meet-finish': if(PLAN){ PLAN.finished=true; PLAN.status='done'; }
      toast(T('Встреча отмечена завершённой','Meetup marked as finished')); cur='agenthome'; render(); break;
    case 'meet-open': cur=(PLAN&&PLAN.here)?'mymeetup':'meetstate'; render(); break;
    case 'security': SHEET='security'; render(); break;
    case 'chat-back': chatBack(); break;                     // generic chat back (match chat, etc.)
    case 'go-home': editSig=null; detail=null; cur='agenthome'; render(); break;   // center FAB -> agent home
    // This block sits directly above the composer and says the same thing ("опиши, кого ищешь"), so it
    // must open the same screen the composer does. It used to call openBuddy(), the pre-flow free-chat
    // screen — the same stale entry point the Enter key had. Kleal converses on the new screen now.
    case 'talk-buddy': flowStart(''); break;
    case 'see-all': setTab('search'); break;
    case 'add-interests': openSheet('interests'); break;
    case 'edit-personality': openSheet('personality'); break;
    // ---- Личность: the test, and the life story ----
    case 'start-persona': ptestInit(); navTo('persona'); break;
    case 'ptest-pick': ptestAnswer(ds.v||'', ds.i===undefined?-1:+ds.i); break;
    case 'ptest-retry': ptestFinish(); break;
    case 'ptest-take': ptestResolve(ds.f||''); break;
    case 'ptest-keep': ptestKeep(ds.f||''); break;
    case 'story-confirm': { const changed=saveStory();
      toast(changed?T('Сохранено','Saved'):T('Уже сохранено','Already saved'));
      setTab('overview'); break; }
    default: toast(T('Пока недоступно','Not available yet'));
  }
}
// Change/add the photo from the profile itself — tapping the avatar. Same downscale as onboarding, so
// this also rescues the case where the onboarding upload never happened.
function _downscalePhoto(dataURL, cb){
  const img=new Image();
  img.onload=function(){ const MAX=480; let w=img.width, h=img.height;
    if(w>=h && w>MAX){ h=Math.round(h*MAX/w); w=MAX; } else if(h>w && h>MAX){ w=Math.round(w*MAX/h); h=MAX; }
    try{ const c=document.createElement('canvas'); c.width=w; c.height=h;
      c.getContext('2d').drawImage(img,0,0,w,h); cb(c.toDataURL('image/jpeg',0.85)); }
    catch(_e){ cb(dataURL); } };
  img.onerror=function(){ cb(dataURL); };
  img.src=dataURL;
}
function editPhoto(){
  if(IS_DEMO){ toast(T('Это демо-профиль','This is a sample profile')); return; }
  let fi=document.getElementById('profphotoin');
  if(!fi){ fi=document.createElement('input'); fi.type='file'; fi.accept='image/*'; fi.id='profphotoin';
    fi.style.display='none'; document.body.appendChild(fi); }
  fi.onchange=()=>{ const f=fi.files[0]; if(!f) return;
    const r=new FileReader();
    r.onload=()=>{ _downscalePhoto(r.result, function(small){
      DATA.photo=small; try{ localStorage.setItem('kleal_photo', small); }catch(_e){}
      fi.value=''; render(); saveState(); toast(T('Фото обновлено','Photo updated')); }); };
    r.onerror=()=>{ fi.value=''; }; r.readAsDataURL(f); };
  fi.click();
}
// The profile photo arrives from onboarding through shared-origin localStorage — the ?p= hand-off
// can't carry a multi-MB dataURL, so it is delivered out of band. Read it into DATA once so the
// avatar can show it. Skipped for the sample (demo) profile, which is not the user's own.
if(!DATA.photo && !IS_DEMO){ try{ const _ph=localStorage.getItem('kleal_photo'); if(_ph) DATA.photo=_ph; }catch(_e){} }
render();
loadServerProfile();   // pull the shared profile row; localStorage alone must never be the truth
</script></body></html>'''

# escape "</" so a stray "</script>" inside data can never terminate the inline <script> early
HTML = HTML_HEAD.replace("__DATA__", json.dumps(DATA, ensure_ascii=False).replace("</", "<\\/"))

# ---------------------------------------------------------------- mascot artwork
# The five Kleal mascot poses, served from /assets/<name>.svg rather than inlined into the page.
# The SPA rebuilds screens with innerHTML on every render, so an inlined 3KB SVG would be re-parsed
# several times a second; as an <img> the browser decodes each pose once and caches it. Kept in this
# file because every service here is deliberately a single file with no static directory.
ASSETS = {
    'map': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="mapTitle mapDesc"> <title id="mapTitle">Kleal mascot — map planning pose</title> <desc id="mapDesc">Coral Kleal mascot holding a folded route map, based on the supplied reference pose.</desc> <defs> <linearGradient id="mapBody" x1="120" y1="61" x2="409" y2="449" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.55" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="mapFace" cx="0" cy="0" r="1" gradientTransform="translate(221 155) rotate(55) scale(164 155)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <linearGradient id="mapPaper" x1="133" y1="277" x2="328" y2="428" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF7"/> <stop offset="1" stop-color="#ECE7DC"/> </linearGradient> <radialGradient id="mapGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-map"> <ellipse cx="255" cy="451" rx="154" ry="24" fill="url(#mapGround)"/> <path d="M257 35C162 35 93 104 93 194c0 58 25 99 62 124-21 46-9 99 33 128 32 22 66 12 80-23 19 37 62 46 94 18 31-28 41-68 26-106 49-9 81-42 80-82-1-43-34-73-76-74C380 93 325 35 257 35Z" fill="url(#mapBody)"/> <path d="M399 209c52-2 79 26 71 65-8 35-39 50-73 40-28-8-36-31-22-52 10-16 27-22 43-17 15 5 20 17 14 28-6 11-18 13-30 7" stroke="#E84242" stroke-width="25" stroke-linecap="round"/> <ellipse cx="253" cy="190" rx="116" ry="110" fill="url(#mapFace)"/> <ellipse cx="214" cy="190" rx="12" ry="18" fill="#171920"/> <ellipse cx="292" cy="190" rx="12" ry="18" fill="#171920"/> <path d="M236 228c11 11 24 11 36 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M132 286 197 268 259 287 328 268 341 413 273 431 209 411 143 431Z" fill="url(#mapPaper)" stroke="#D8D1C4" stroke-width="4" stroke-linejoin="round"/> <path d="M197 268 209 411M259 287l14 144M328 268l13 145" stroke="#D8D1C4" stroke-width="3"/> <path d="M175 382c22-36 41-21 59-42 15-17 7-41 30-53" stroke="#2B2D33" stroke-width="6" stroke-linecap="round" stroke-dasharray="3 13"/> <path d="M280 302c0 17-20 37-20 37s-20-20-20-37a20 20 0 1 1 40 0Z" fill="#FF5B55"/> <circle cx="260" cy="302" r="7" fill="#FFF8EB"/> <circle cx="174" cy="383" r="9" fill="#FF5B55"/> <path d="M142 311c-30-5-54-24-57-48-2-20 10-36 28-38 16-2 28 8 29 23 2 13-6 23-19 28" stroke="url(#mapBody)" stroke-width="34" stroke-linecap="round"/> <path d="M349 316c20 1 34 13 38 30" stroke="url(#mapBody)" stroke-width="34" stroke-linecap="round"/> <ellipse cx="128" cy="313" rx="25" ry="20" transform="rotate(18 128 313)" fill="#E84242"/> <ellipse cx="354" cy="319" rx="25" ry="20" transform="rotate(-12 354 319)" fill="#E84242"/> <path d="M205 420c-5 22-16 37-32 48" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M307 422c6 22 17 36 34 47" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="164" cy="470" rx="31" ry="14" fill="#D9363C"/> <ellipse cx="350" cy="470" rx="31" ry="14" fill="#D9363C"/> </g> </svg>''',
    'match': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="matchTitle matchDesc"> <title id="matchTitle">Kleal mascot — match confirmed pose</title> <desc id="matchDesc">Kleal celebrates a mutual match with open arms and two connected route nodes.</desc> <defs> <linearGradient id="matchBody" x1="114" y1="66" x2="394" y2="447" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.55" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="matchFace" cx="0" cy="0" r="1" gradientTransform="translate(224 153) rotate(54) scale(170 160)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <radialGradient id="matchGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-match"> <ellipse cx="257" cy="451" rx="154" ry="24" fill="url(#matchGround)"/> <path d="M88 217c87-54 250-55 336 0" stroke="#FF5B55" stroke-width="6" stroke-linecap="round" stroke-dasharray="2 16"/> <path d="M257 35C161 35 91 105 91 195c0 56 24 95 61 121-23 44-15 94 23 126 30 25 70 18 87-21 20 39 64 44 95 15 31-29 41-70 24-108 49-11 78-46 75-85-3-43-36-70-78-69C374 91 323 35 257 35Z" fill="url(#matchBody)"/> <path d="M392 201c52-5 82 20 78 60-4 36-35 55-70 48-29-6-39-28-27-50 9-17 25-25 42-21 15 3 21 15 16 26-5 11-17 15-29 10" stroke="#E84242" stroke-width="25" stroke-linecap="round"/> <ellipse cx="255" cy="190" rx="118" ry="111" fill="url(#matchFace)"/> <path d="M200 191c9 11 20 11 29 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M281 191c9 11 20 11 29 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M230 227c17 21 36 21 53 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M160 307c-41-8-75-36-83-70" stroke="url(#matchBody)" stroke-width="37" stroke-linecap="round"/> <path d="M352 307c41-8 75-36 83-70" stroke="url(#matchBody)" stroke-width="37" stroke-linecap="round"/> <circle cx="72" cy="222" r="16" fill="#FFF8EB" stroke="#FF5B55" stroke-width="8"/> <circle cx="440" cy="222" r="16" fill="#FFF8EB" stroke="#FF5B55" stroke-width="8"/> <path d="M209 414c-5 22-16 38-33 50" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M306 414c5 22 17 38 34 50" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="166" cy="468" rx="31" ry="14" fill="#D9363C"/> <ellipse cx="350" cy="468" rx="31" ry="14" fill="#D9363C"/> <circle cx="114" cy="112" r="7" fill="#FF5B55"/> <path d="m398 105 7 12 13 2-10 9 3 13-13-6-12 6 2-13-9-9 13-2Z" fill="#FF5B55" opacity="0.72"/> </g> </svg>''',
    'primary': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="primaryTitle primaryDesc"> <title id="primaryTitle">Kleal mascot — primary welcome pose</title> <desc id="primaryDesc">Coral Kleal mascot facing forward and waving.</desc> <defs> <linearGradient id="primaryBody" x1="110" y1="62" x2="395" y2="448" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.55" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="primaryFace" cx="0" cy="0" r="1" gradientTransform="translate(219 155) rotate(55) scale(175 166)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <linearGradient id="primaryHighlight" x1="150" y1="62" x2="210" y2="315" gradientUnits="userSpaceOnUse"> <stop stop-color="white" stop-opacity="0.34"/> <stop offset="1" stop-color="white" stop-opacity="0"/> </linearGradient> <radialGradient id="primaryGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-primary"> <ellipse cx="256" cy="451" rx="159" ry="24" fill="url(#primaryGround)"/> <path d="M257 35C161 35 91 105 91 195c0 55 23 94 59 120-25 42-18 92 19 126 29 28 72 23 91-17 19 40 64 47 96 18 33-29 45-72 28-112 48-10 79-44 77-82-2-43-34-72-75-74C378 92 324 35 257 35Z" fill="url(#primaryBody)"/> <path d="M391 202c55-6 86 20 83 61-3 37-35 58-73 52-31-5-42-27-31-51 8-19 24-29 44-26 17 2 24 14 20 27-4 12-16 17-29 13" stroke="#E84242" stroke-width="26" stroke-linecap="round"/> <ellipse cx="255" cy="192" rx="118" ry="112" fill="url(#primaryFace)"/> <path d="M169 128c21-39 62-61 105-57" stroke="url(#primaryHighlight)" stroke-width="18" stroke-linecap="round" opacity="0.9"/> <ellipse cx="216" cy="191" rx="12" ry="18" fill="#171920"/> <ellipse cx="294" cy="191" rx="12" ry="18" fill="#171920"/> <path d="M237 229c12 13 26 13 38 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M153 307c-38-10-66-39-64-72 1-24 18-43 39-42 17 1 29 13 28 29-1 15-12 24-24 31" stroke="url(#primaryBody)" stroke-width="36" stroke-linecap="round"/> <path d="M356 314c32-4 58-26 67-55" stroke="url(#primaryBody)" stroke-width="38" stroke-linecap="round"/> <path d="M412 249c6-12 16-20 30-25" stroke="#FF6C62" stroke-width="12" stroke-linecap="round"/> <circle cx="444" cy="223" r="8" fill="#FFF8EB"/> <path d="M205 410c-4 23-14 39-31 52" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M310 412c5 23 17 39 35 51" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="166" cy="467" rx="32" ry="15" fill="#D9363C"/> <ellipse cx="355" cy="467" rx="32" ry="15" fill="#D9363C"/> <circle cx="378" cy="91" r="9" fill="#FFF8EB" opacity="0.55"/> </g> </svg>''',
    'searching': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="searchTitle searchDesc"> <title id="searchTitle">Kleal mascot — searching pose</title> <desc id="searchDesc">Kleal leans forward, looks to the right, and shades its eyes while searching for a good match.</desc> <defs> <linearGradient id="searchBody" x1="110" y1="70" x2="398" y2="445" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.56" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="searchFace" cx="0" cy="0" r="1" gradientTransform="translate(247 157) rotate(57) scale(163 153)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <radialGradient id="searchGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-searching" transform="rotate(-4 256 256)"> <ellipse cx="250" cy="451" rx="163" ry="24" fill="url(#searchGround)"/> <path d="M251 41C158 49 95 124 103 211c5 54 34 89 72 110-20 44-6 95 34 124 32 24 70 14 84-24 22 34 65 38 94 8 29-30 36-71 17-107 47-13 74-49 69-88-6-42-40-68-81-65-2-83-73-135-141-128Z" fill="url(#searchBody)"/> <path d="M403 198c51-8 82 15 81 54-1 36-30 57-66 53-29-3-41-25-31-48 8-17 23-27 40-25 16 2 23 13 20 25-3 11-14 17-27 14" stroke="#E84242" stroke-width="25" stroke-linecap="round"/> <ellipse cx="265" cy="193" rx="116" ry="109" transform="rotate(4 265 193)" fill="url(#searchFace)"/> <ellipse cx="237" cy="190" rx="12" ry="18" fill="#171920"/> <ellipse cx="312" cy="184" rx="12" ry="18" fill="#171920"/> <circle cx="241" cy="185" r="3.5" fill="white"/> <circle cx="316" cy="179" r="3.5" fill="white"/> <path d="M267 230c12 9 24 8 34-3" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M337 147c29-31 59-36 84-17" stroke="url(#searchBody)" stroke-width="34" stroke-linecap="round"/> <path d="M396 126c22-8 43-3 57 13" stroke="#FF7166" stroke-width="17" stroke-linecap="round"/> <path d="M395 126c13 12 20 27 21 45" stroke="#E84242" stroke-width="13" stroke-linecap="round"/> <path d="M164 317c-38-7-65-31-65-61 0-22 15-39 35-39 17 0 29 11 29 27 0 14-10 24-22 29" stroke="url(#searchBody)" stroke-width="35" stroke-linecap="round"/> <path d="M218 416c-17 22-38 35-63 39" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M315 414c20 19 43 29 68 29" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="143" cy="457" rx="33" ry="14" transform="rotate(-12 143 457)" fill="#D9363C"/> <ellipse cx="394" cy="444" rx="33" ry="14" transform="rotate(8 394 444)" fill="#D9363C"/> <circle cx="441" cy="92" r="8" fill="#FF5B55"/> <circle cx="470" cy="82" r="5" fill="#FF5B55" opacity="0.48"/> </g> </svg>''',
    'thinking': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="thinkTitle thinkDesc"> <title id="thinkTitle">Kleal mascot — thinking and waiting pose</title> <desc id="thinkDesc">Kleal sits calmly, looks upward, and pauses before the next suggestion.</desc> <defs> <linearGradient id="thinkBody" x1="112" y1="74" x2="393" y2="444" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.55" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="thinkFace" cx="0" cy="0" r="1" gradientTransform="translate(217 159) rotate(54) scale(164 155)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <radialGradient id="thinkGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-thinking"> <ellipse cx="256" cy="451" rx="164" ry="24" fill="url(#thinkGround)"/> <path d="M250 43C158 43 91 110 91 197c0 54 25 92 61 117-22 43-13 93 27 123 32 24 69 15 84-21 20 37 62 43 92 16 30-28 40-67 24-104 47-11 76-45 74-83-3-41-35-68-76-68-5-80-61-134-127-134Z" fill="url(#thinkBody)"/> <path d="M389 203c50-5 78 19 75 57-3 35-32 53-66 47-28-5-38-26-27-48 8-16 23-24 40-21 15 3 21 14 17 25-4 11-15 15-27 11" stroke="#E84242" stroke-width="24" stroke-linecap="round"/> <ellipse cx="248" cy="194" rx="114" ry="108" fill="url(#thinkFace)"/> <ellipse cx="214" cy="184" rx="11" ry="17" fill="#171920"/> <ellipse cx="286" cy="174" rx="11" ry="17" fill="#171920"/> <circle cx="217" cy="179" r="3" fill="white"/> <circle cx="289" cy="169" r="3" fill="white"/> <path d="M232 228c10 7 21 6 30-2" stroke="#171920" stroke-width="7" stroke-linecap="round"/> <path d="M159 316c-32-3-55-21-59-46-3-21 9-38 28-41 16-2 28 8 30 23 2 14-6 24-18 29" stroke="url(#thinkBody)" stroke-width="35" stroke-linecap="round"/> <path d="M346 311c-24 10-42 29-50 54" stroke="url(#thinkBody)" stroke-width="35" stroke-linecap="round"/> <ellipse cx="286" cy="368" rx="22" ry="18" transform="rotate(-25 286 368)" fill="#E84242"/> <path d="M201 408c-31 25-60 37-91 36" stroke="#E84242" stroke-width="36" stroke-linecap="round"/> <path d="M306 406c31 24 61 34 94 31" stroke="#E84242" stroke-width="36" stroke-linecap="round"/> <ellipse cx="94" cy="445" rx="34" ry="15" transform="rotate(-5 94 445)" fill="#D9363C"/> <ellipse cx="414" cy="438" rx="34" ry="15" transform="rotate(4 414 438)" fill="#D9363C"/> <path d="M74 443c94 24 267 23 367-4" stroke="#FF5B55" stroke-width="8" stroke-linecap="round" opacity="0.42"/> <circle cx="352" cy="112" r="8" fill="#171920" opacity="0.34"/> <circle cx="381" cy="91" r="6" fill="#171920" opacity="0.24"/> <circle cx="406" cy="72" r="4" fill="#171920" opacity="0.16"/> </g> </svg>''',
}

# ---------------------------------------------------------------- demo photographs
# Home mockup 1615-21279 uses real photos on the event covers and the match avatar. The product
# ships no photography, so these two are the designer's own demo images (downscaled + JPEG), kept
# inline like the mascot SVGs above so the service stays a single file. Served at /assets/<name>.jpg.
PHOTOS = {
    'event-cover': '''/9j/4AAQSkZJRgABAQAASABIAAD/4QD6RXhpZgAATU0AKgAAAAgABQESAAMAAAABAAEAAAExAAIAAAAiAAAASgE7AAIAAAAlAAAAbIKYAAIAAAApAAAAkodpAAQAAAABAAAAvAAAAABBZG9iZSBQaG90b3Nob3AgQ0MgMjAxOCBNYWNpbnRvc2gASi4gS29ucmFkIFNjaG1pZHQgKEJGRiBQcm9mZXNzaW9uYWwpAADik5IgSi4gS29ucmFkIFNjaG1pZHQgKEJGRiBQcm9mZXNzaW9uYWwpAAAABJAAAAcAAAAEMDIyMaABAAMAAAABAAEAAKACAAQAAAABAAACgKADAAQAAAABAAABqgAAAAD/4QymaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJYTVAgQ29yZSA2LjAuMCI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOmRjPSJodHRwOi8vcHVybC5vcmcvZGMvZWxlbWVudHMvMS4xLyIgeG1sbnM6SXB0YzR4bXBDb3JlPSJodHRwOi8vaXB0Yy5vcmcvc3RkL0lwdGM0eG1wQ29yZS8xLjAveG1sbnMvIiB4bWxuczpwaG90b3Nob3A9Imh0dHA6Ly9ucy5hZG9iZS5jb20vcGhvdG9zaG9wLzEuMC8iIHBob3Rvc2hvcDpDcmVkaXQ9IkouIEtvbnJhZCBTY2htaWR0IChCRkYgUHJvZmVzc2lvbmFsKSIgcGhvdG9zaG9wOkF1dGhvcnNQb3NpdGlvbj0iRGlwbC4gRm90b2Rlc2lnbmVyIiBwaG90b3Nob3A6Q291bnRyeT0iR2VybWFueS9FVSI+IDxkYzpjcmVhdG9yPiA8cmRmOlNlcT4gPHJkZjpsaT5KLiBLb25yYWQgU2NobWlkdCAoQkZGIFByb2Zlc3Npb25hbCk8L3JkZjpsaT4gPC9yZGY6U2VxPiA8L2RjOmNyZWF0b3I+IDxkYzpyaWdodHM+IDxyZGY6QWx0PiA8cmRmOmxpIHhtbDpsYW5nPSJ4LWRlZmF1bHQiPuKTkiBKLiBLb25yYWQgU2NobWlkdCAoQkZGIFByb2Zlc3Npb25hbCk8L3JkZjpsaT4gPC9yZGY6QWx0PiA8L2RjOnJpZ2h0cz4gPElwdGM0eG1wQ29yZTpDcmVhdG9yQ29udGFjdEluZm8gSXB0YzR4bXBDb3JlOkNpVGVsV29yaz0iKzQ5IDMwIDIxOTE2NzAwIiBJcHRjNHhtcENvcmU6Q2lBZHJDdHJ5PSJEZXV0c2NobGFuZCIgSXB0YzR4bXBDb3JlOkNpVXJsV29yaz0id3d3Lmprb25yYWRzY2htaWR0LmNvbSIgSXB0YzR4bXBDb3JlOkNpQWRyRXh0YWRyPSJSZWdlbnNidXJnZXIgU3RyLiA5IiBJcHRjNHhtcENvcmU6Q2lBZHJQY29kZT0iMTA3NzciIElwdGM0eG1wQ29yZTpDaUFkclJlZ2lvbj0iQmVybGluIiBJcHRjNHhtcENvcmU6Q2lBZHJDaXR5PSJCZXJsaW4iIElwdGM0eG1wQ29yZTpDaUVtYWlsV29yaz0iY29udGFjdEBqa29ucmFkc2NobWlkdC5jb20iLz4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgPD94cGFja2V0IGVuZD0idyI/PgD/7QDsUGhvdG9zaG9wIDMuMAA4QklNBAQAAAAAALQcAVoAAxslRxwCAAACAAIcAnQAKOKTkiBKLiBLb25yYWQgU2NobWlkdCAoQkZGIFByb2Zlc3Npb25h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''',
    'match-anna': '''/9j/4AAQSkZJRgABAQAASABIAAD/4QBMRXhpZgAATU0AKgAAAAgAAYdpAAQAAAABAAAAGgAAAAAAA6ABAAMAAAABAAEAAKACAAQAAAABAAAA3KADAAQAAAABAAAA3AAAAAD/4QqPaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJYTVAgQ29yZSA2LjAuMCI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnBob3Rvc2hvcD0iaHR0cDovL25zLmFkb2JlLmNvbS9waG90b3Nob3AvMS4wLyIgeG1sbnM6SXB0YzR4bXBFeHQ9Imh0dHA6Ly9pcHRjLm9yZy9zdGQvSXB0YzR4bXBFeHQvMjAwOC0wMi0yOS8iIHBob3Rvc2hvcDpDcmVkaXQ9Ik1hZGUgd2l0aCBHb29nbGUgQUkiIElwdGM0eG1wRXh0OkRpZ2l0YWxTb3VyY2VUeXBlPSJodHRwOi8vY3YuaXB0Yy5vcmcvbmV3c2NvZGVzL2RpZ2l0YWxzb3VyY2V0eXBlL3RyYWluZWRBbGdvcml0aG1pY01lZGlhIiBJcHRjNHhtcEV4dDpEaWdpdGFsU291cmNlRmlsZVR5cGU9Imh0dHA6Ly9jdi5pcHRjLm9yZy9uZXdzY29kZXMvZGlnaXRhbHNvdXJjZXR5cGUvdHJhaW5lZEFsZ29yaXRobWljTWVkaWEiLz4gPC9yZGY6UkRGPiA8L3g6eG1wbWV0YT4gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg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''',
    'clouds': '''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''',
}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] == "/":   # ignore ?p=<onboarding profile> query
            b = HTML.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            # The whole app — every line of JS — lives inside this one document, and it went out with
            # no cache directives at all. With none, a browser and the cloudflared tunnel in front of
            # it are both free to cache heuristically, so a phone kept running a build from before a
            # deploy: fixes were verified in the served bytes and still "not fixed" on the device.
            # Assets below keep their 24h cache; only the page that carries the code must be fresh.
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        elif self.path.startswith("/assets/") and self.path.endswith(".svg"):
            name = self.path[len("/assets/"):-len(".svg")]
            art = ASSETS.get(name)
            if not art:
                self.send_response(404); self.end_headers(); return
            b = art.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)
        elif self.path.startswith("/assets/") and self.path.endswith(".jpg"):
            name = self.path[len("/assets/"):-len(".jpg")]
            data = PHOTOS.get(name)
            if not data:
                self.send_response(404); self.end_headers(); return
            b = base64.b64decode(data)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print("Kleal Profile demo on http://127.0.0.1:%d" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
