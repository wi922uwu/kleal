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
.bnav{flex:none;height:66px;display:flex;align-items:center;justify-content:space-around;position:relative;
  background:#fff;border-top:1px solid var(--line);padding-bottom:env(safe-area-inset-bottom)}
.bnav a{display:flex;flex-direction:column;align-items:center;gap:3px;font-size:11px;color:var(--muted);cursor:pointer;width:60px}
.bnav a.on{color:var(--primary)}
.bnav .fabgap{width:60px}
.fab{position:absolute;left:50%;top:-16px;transform:translateX(-50%);width:56px;height:56px;border-radius:50%;
  background:var(--card);border:4px solid var(--bg);display:flex;align-items:center;justify-content:center;
  cursor:pointer;box-shadow:0 8px 20px rgba(245,69,92,.35);overflow:hidden}
.fab svg{display:block}
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
.ah2{display:flex;flex-direction:column;height:100%}
.ah2 .ahd{display:flex;align-items:center;gap:4px;padding:8px 20px}
.ah2 .ahd .nm{flex:1;min-width:0}
.ah2 .bell{width:44px;height:44px;border:1px solid var(--border);border-radius:999px;display:flex;
  align-items:center;justify-content:center;flex:none;cursor:pointer;position:relative;background:var(--card)}
.ah2 .body{flex:1;min-height:0;overflow-y:auto;padding:0 20px 12px;display:flex;flex-direction:column;gap:20px}
.aintro2{display:flex;gap:12px;align-items:center;padding:12px 16px;border-radius:16px}
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
// ---- receiving policy (доступность): читаем/пишем свой статус через onboarding /api/v2/receiving ----
// RECV_ERR: the profile may not exist in the matching store at all — the demo identity never does, and
// a user who hasn't finished onboarding doesn't either. Without this the screen drew three availability
// buttons that silently could not work: none selected, nothing saved, no reason given.
let RECV=null, RECV_BUSY=false, RECV_ERR=null;
function loadRecv(){ if(RECV||RECV_ERR||RECV_BUSY||!(DATA&&DATA.name)) return; RECV_BUSY=true;
  fetch('/api/v2/receiving',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:DATA.name})}).then(x=>x.json())
    .then(r=>{ RECV_BUSY=false; if(r&&r.ok){ RECV=r.receiving; } else { RECV_ERR=(r&&r.error)||'unavailable'; } render(); })
    .catch(()=>{ RECV_BUSY=false; RECV_ERR='network'; render(); }); }
function setAvail(st){ if(!(DATA&&DATA.name)) return;
  fetch('/api/v2/receiving',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:DATA.name,receiving:{status:st}})}).then(x=>x.json())
    .then(r=>{ if(r&&r.ok){ RECV=r.receiving; toast(T('Доступность обновлена','Availability updated')); }
               else toast(T('Не удалось сохранить','Could not save')); render(); })
    .catch(()=>toast(T('Не удалось сохранить','Could not save'))); }
function readinessChip(c){ if(!c||!c.readiness||c.readiness==='open_now') return null;
  return (UILANG==='ru'?(c.readiness_ru||c.readiness):(c.readiness_en||c.readiness)); }
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
  return '<div class="fab" data-act="go-home">'+IC.peek+'</div>'+
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

// The reason line usually already says "рядом (3.6 км)" — printing the distance again in the name row
// was pure duplication AND the thing that pushed the line into wrapping. Show it only if absent.
function candKm(c, sub){
  if(c==null||c.km==null) return '';
  if(String(sub||'').indexOf(String(c.km))>=0) return '';
  return `<span class="candkm">${c.km} ${T('км','km')}</span>`;
}
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
function scr_snapshot(){ if(!DATA.snapshot.length) return emptyState(T("Пока не по чему матчить","Nothing to match on yet"),T("Kleal заполнит это по мере знакомства.","Kleal fills this in as it learns about you."));
  return `<div class="stack fade">${DATA.snapshot.map(r=>summaryRow(r,true)).join('')}</div>`; }

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
function scr_places(){
  if(!DATA.availability.length && !DATA.places.length) return emptyState(T("Пока нет мест и времени","No places or times yet"),T("Kleal запомнит, где и когда тебе удобно встречаться.","Kleal will note where and when you like to meet."));
  return `<div class="fade"><div class="rowhead"><div class="seclbl">${T('Когда обычно свободен','Usual availability')}</div></div>
    <div class="stack">${DATA.availability.length?DATA.availability.map(r=>summaryRow(r,false)).join(''):`<div class="seccap">${T('Пока не задано — Kleal сам поймёт, когда тебе удобно.','Not set yet — Kleal will learn your usual times.')}</div>`}</div>
    <div class="rowhead"><div class="seclbl">${T('Места','Places')}</div></div>
    <div class="stack">${DATA.places.length?DATA.places.map(r=>summaryRow(r,false)).join(''):`<div class="seccap">${T('Пока не задано.','Not set yet.')}</div>`}</div></div>`;
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
let curIntent=null, intentLaunched=false, agentBusy=false;
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
// Buddy agent: free-text request -> real structured intent + ranked candidates (backend /api/agent/plan).
function intentSpec(it){ const s=it.spec||[]; return s.map((r,i)=>`<div class="specrow"><div class="spi">${IC[r[0]]||IC.spark}</div>
  <div class="sl">${esc(r[1])}</div><div class="sv">${esc(r[2])}</div></div>${i<s.length-1?'<div class="divider"></div>':''}`).join(''); }

// ===== Conversational "Create intent": Kleal collects the essentials + validates, THEN builds the card =====
// Replaces the old "any text -> instant card" behaviour: /api/buddy/intent-build runs a short dialogue
// (gibberish -> ask again; missing when/format -> ask; enough -> ready) and only then do we build a card.
async function buildIntentCard(intent){
  curIntent={pending:true, query:''}; render();
  let r; try{ r=await fetch('/api/agent/match',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({intent:intent, profile:matchProfile(), ctx:{self:DATA.name||''}})}).then(x=>x.json()); }catch(e){ r=null; }
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
    body:JSON.stringify({intent:(curIntent.intent||{topics:curIntent.tags||[],type:curIntent.type,role:curIntent.role,time:curIntent.time,mode:curIntent.mode}), profile:matchProfile(), ctx:{self:DATA.name||''}, candidates:curIntent.candidates||[]})}).then(x=>x.json()); }catch(e){ r=null; }
  const got=!!(r&&r.candidates&&r.candidates.length);
  if(got){ curIntent.candidates=r.candidates;
    curIntent.confidence=(r.candidates[0]&&r.candidates[0].score)||curIntent.confidence; }
  curIntent.negotiating=false;
  // Only claim the round happened if it actually did. On a failed request the candidates keep their
  // pre-negotiation shape (no `agree`, no `decided`), and marking negotiated=true made every real
  // person render as "отказ" — the app telling the user they were turned down by someone nobody asked.
  curIntent.negotiated=got; if(got) curIntent.status='matched';
  saveCurIntent(); render();
  if(!got){ toast(T('Не удалось связаться с агентами — попробуй ещё раз','Could not reach their agents — try again')); return; }
  const ag=(curIntent.candidates||[]).filter(c=>c.agree&&c.decided).length;
  toast(ag?T('Согласились: '+ag+' — одобри интро, чтобы связаться','Agreed: '+ag+' — approve an intro to connect')
          :T('Пока никто не подтвердил','Nobody has confirmed yet'));
}
// ---------- Phase 1: saved intents ----------
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
  const ORD=['Basics','Location','Languages'];
  rows.sort((a,b)=>{const x=ORD.indexOf(a.title),y=ORD.indexOf(b.title);return (x<0?9:x)-(y<0?9:y);});
}
function matchProfile(){
  const g=t=>{const r=snapRow(t);return r?String(r.value||''):'';};
  const langs=(DATA.langsList&&DATA.langsList.length)?DATA.langsList.slice()
    :(g('Languages').match(/[A-Za-zА-Яа-яё]+/g)||[]).map(s=>({'english':'en','английский':'en',
    'spanish':'es','испанский':'es','russian':'ru','русский':'ru','french':'fr','французский':'fr',
    'german':'de','немецкий':'de','catalan':'ca','italian':'it'}[s.toLowerCase()]||s.slice(0,2).toLowerCase()))
    .filter((v,i,a)=>v&&a.indexOf(v)===i);
  const vibeRow=((DATA.social||{}).rows||[])[0];
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
function candReasons(c){ return ((UILANG==='ru'?c.reasons_ru:c.reasons_en)||c.reasons||[]); }
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
  return { name:DATA.name||'', location:g('Location'), languages:g('Languages'),
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
const INTENT_STATUS = () => ({
  searching: [T('Идёт поиск','Searching'),'warn'],
  matched:   [T('Есть совпадения','Matches found'),'ok'],
  planned:   [T('Встреча назначена','Meetup planned'),'ok'],
  paused:    [T('На паузе','Paused'),'mut'],
  done:      [T('Завершён','Done'),'mut'],
});
function intentBest(it){                      // the honest headline: the best band, never a percent
  const cs=it.candidates||[];
  if(!cs.length) return null;
  const order={especially_close:0,strong_option:1,broader_option:2,needs_clarification:3};
  return cs.slice().sort((a,b)=>(order[a.band]??9)-(order[b.band]??9))[0];
}
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
function scr_agenthome(){
  if(!exploreLoaded) loadExplore();          // real plans for "For you today"
  const nm=(DATA.name||'there').split(' ')[0];
  // "For you today" was one unfinished card: an empty grey square, a lonely pin with nothing after
  // it, a raw username, a tap that toasted «скоро», and a dead bookmark. Now up to three real plans,
  // each with a topic icon in the tile, «host · area», the time, a working «Позвать» (joinPublic) and
  // a bookmark that actually saves. Whom+where varies, so the section no longer claims «сегодня».
  const plans=(DATA.plans||[]).slice(0,3);
  // Same auto-detected category illustration the intent cards use — topics first, title as fallback.
  const planIcon=p=>{ const k=tileKeyFor((p.topics||[]).join(' ')||String(p.title||''));
    return TILE_SVG[k]||TILE_SVG.social; };
  const planCard=(p,i)=>`<div class="ecard" style="cursor:default">
      <div class="ph">${planIcon(p)}</div>
      <div class="bd">
        <div class="ti">${esc(p.title)}</div>
        <div class="meta"><span class="mi">${IC.clock}${esc(locStr(p.when||''))}</span>
          ${(p.area||p.dist)?`<span class="mi">${IC.pin}${esc(p.area||p.dist)}</span>`:''}</div>
        ${(p.going||p.who)?`<div class="who">${p.going?`${p.going} ${T('участников','participants')}`:esc(p.who||'')}</div>`:''}
        <div class="pact">
          <button class="kbtn pri sm" data-act="join-plan" data-pi="${i}">${T('Позвать','Invite')}</button>
          <div class="pbm" data-act="cand-save" data-n="${esc(p.who||'')}">${IC.bookmark}</div>
        </div>
      </div></div>`;
  const card = plans.length
    ? `<div class="carousel">${plans.map(planCard).join('')}</div>`
    : `<div class="k-cap" style="color:var(--muted);padding:4px 2px">${T('Пока ничего не запланировано — опиши, чего хочешь, и я поищу.',"Nothing planned yet — tell me what you want and I'll look.")}</div>`;
  return `<div class="ah2 fade">
    <div class="ahd"><div class="nm k-h2">${T('Привет','Hey')}, ${esc(nm)} 👋</div>
      <div class="bell" data-act="notif">${IC.bell}${unreadNotifs()?`<span class="abadge">${unreadNotifs()}</span>`:''}</div></div>
    <div class="body">
      ${IS_DEMO?`<div class="kinfo" style="margin-bottom:4px">${IC.info}<div>${T(
        'Это демо-профиль. Пройди онбординг, чтобы Kleal искал для тебя.',
        'This is a sample profile. Complete onboarding so Kleal searches for you.')}
        <span style="color:var(--primary);font-weight:600;cursor:pointer" data-act="go-onboarding"> ${T('Начать','Start')} →</span></div></div>`:''}
      ${(PLAN&&PLAN.confirmed)?`<div>
        <div class="kbub ag" style="max-width:none;margin-bottom:12px">${T('Сегодня у тебя встреча','Today you have a meetup')}</div>
        <div class="kplan tight">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
            <div class="k-h3">${T('Кофе и разговор','Coffee & conversation')}</div>
            <div style="color:var(--muted)">${IC.calen}</div></div>
          <div class="kplanrow"><div class="ic">${IC.clock}</div><div class="bd">
            <div class="ti" style="font-size:13px">${esc(slotText())}</div></div></div>
          <div class="kplanrow"><div class="ic">${IC.pin}</div><div class="bd">
            <div class="ti" style="font-size:13px">${esc(placeText())}</div></div></div>
          <button class="kbtn pri" data-act="meet-open">${T('Открыть детали','Open details')}</button>
        </div></div>`:''}
      <div>
        <div class="aintro2" data-act="talk-buddy" style="cursor:pointer">
          <div class="msc">${masc('primary')}</div>
          <div class="txt">${T('Я Kleal, твой социальный AI-агент. Опиши, кого или что ищешь — подберу лучшее.',"I'm Kleal, your social AI agent. Describe who or what you're looking for — I'll find the best fit.")}</div>
        </div>
        <div class="kcomp"><div class="fld">
            <input id="ainput" placeholder="${T('Опиши, кого или что ищешь…',"Describe who or what you're look…")}" autocomplete="off">${IC.mic}</div>
          <button class="snd" data-act="agent-go">${IC.send}</button></div>
      </div>
      ${inboxCards()}
      <div style="display:flex;flex-direction:column;gap:32px">
        <div style="display:flex;flex-direction:column;gap:16px">
          <div style="display:flex;align-items:flex-end;justify-content:space-between">
            <span class="k-title">${T('Планы для тебя','Plans for you')}</span>
            <span class="k-label" style="color:var(--primary);cursor:pointer" data-act="see-all">${T('Все','See All')}</span></div>
          ${card}
        </div>
      </div>
    </div>
  </div>`;
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
  bestfit:'agenthome', options:'bestfit', recos:'options', candprofile:'bestfit',
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
    // conversationally are marked and excluded — a real multi-turn build is unmarked and still sent.
    const forBuilder=FLOW.msgs.filter(m=>!m.chat).map(m=>({role:m.who==='me'?'user':'assistant',content:m.text}));
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
    FLOW.summary={request:FLOW.request||FLOW.text, format:r.intent.format,
                  vibe:(r.intent.tags||[]).filter(t=>t!=='meet').join(', ')||null};
    // Only the district question is left when the dialog already gave both the day and the time of
    // day — and the district is optional, so there is nothing the clarify screen MUST ask. Skip it.
    cur=(FLOW.knownWhen&&FLOW.knownTime)?'summary':'clarify';
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
function flowIntent(){
  // merge the clarification answers into the intent the buddy compiled
  const it=Object.assign({}, FLOW.intent||{});
  if(!it.topics||!it.topics.length) it.topics=(FLOW.text||'').split(/[,\s]+/).filter(w=>w.length>2).slice(0,4);
  // 'tonight'/'20-22' are the OLD chip keys; a state saved before the day/time split still carries them,
  // so they stay in these maps as aliases — dropping them would make a restored intent time undefined.
  const whenTxt={today:'today',tonight:'today',tomorrow:'tomorrow',weekend:'this weekend',pick:'Flexible'}[FLOW.when];
  const timeTxt={morning:'morning',afternoon:'afternoon',evening:'evening','20-22':'evening',late:'late evening'}[FLOW.time];
  it.time=[whenTxt,timeTxt].filter(Boolean).join(' ')||it.time||'Flexible';
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
async function flowSearch(isRetry){
  FLOW.steps=0; cur='searching'; render();
  const tick=setInterval(()=>{ if(FLOW.steps<3){ FLOW.steps++; render(); } }, 650);
  const minShow=new Promise(res=>setTimeout(res, 2600));   // the search screen is part of the design
  let r=null;
  try{
    r=await fetch('/api/agent/match',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({intent:flowIntent(), profile:matchProfile(), ctx:{self:DATA.name||''}})}).then(x=>x.json());
  }catch(e){ r=null; }
  await minShow;
  clearInterval(tick); FLOW.steps=4;
  const cands=(r&&r.candidates)||[];
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
// Is there anything personal to build on at all? With no usable interest we do not invent one.
function hintsSignals(){
  return (DATA.interests||[]).filter(i=>i&&i.name&&i.used!==false).length;
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
  return `<div class="kbar" style="justify-content:space-between">
  <div class="kback" data-act="flow-back">${IC.back}</div>
  ${show?`<div class="kchip on" data-act="${intentMode?'flow-done':'flow-finish'}" style="cursor:pointer;font-weight:600">${
    intentMode?T('Готово','Done'):('+ '+T('Создать интент','Create Intent'))}</div>`:''}</div>`; }
function kprompt(txt){ return `<div class="kprompt"><div class="av">${IC.person}</div>
  <div class="k-h3" style="flex:1;min-width:0">${esc(txt)}</div></div>`; }
function kcomposer(id,ph){ return `<div class="kcomp" style="padding:10px 16px;border-top:1px solid var(--border);background:var(--bg)">
  <div class="fld"><input id="${id}" placeholder="${esc(ph)}" autocomplete="off">${IC.mic}</div>
  <button class="snd" data-act="flow-send">${IC.send}</button></div>`; }

// ---- 1. Request composer (479:14582) ----
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
        (i===lastAg&&!asked&&!FLOW.busy&&!FLOW.lastFailed)?`<div class="kchips" style="margin-top:2px">${hintsFor(m).map(h=>
          `<div class="kchip soft hint" data-act="flow-hint" data-h="${esc(h)}">${esc(h)}</div>`).join('')}</div>`:''
      }</div>`).join('');
  // The bar carries «+ Создать интент» (Figma): the way OUT of the dialog is always in reach, not
  // buried under the thread. It appears once there is something to build from.
  return `<div class="kflow fade">${kbar(true)}
    <div class="kcont">
      ${kprompt(FLOW.mode==='intent'?T('Собираем интент','Building an intent')
                                     :T('Чего бы тебе хотелось сегодня?','What would you like today?'))}
      ${msgs}
      ${FLOW.busy?`<div class="kbub ag" style="width:64px"><span class="typing3"><i></i><i></i><i></i></span></div>`:''}
      ${(!all.length&&!FLOW.busy)?`<div style="display:flex;flex-direction:column;gap:12px">
        <div class="k-label" style="color:var(--muted)">${T('Можно начать так','You could start with')}</div>
        <div class="kchips">${hintsFor(null).map(h=>`<div class="kchip soft hint" data-act="flow-hint" data-h="${esc(h)}">${esc(h)}</div>`).join('')}</div>
      </div>`:''}
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
function scr_summary(){
  const s=FLOW.summary||{};
  const row=(icon,lb,vl)=>`<div class="krow"><div class="lb">${icon}${esc(lb)}</div><div class="vl">${esc(vl)}</div></div>`;
  const when=labelOf(WHEN_OPTS(),FLOW.when, intentWhen()), tm=labelOf(TIME_OPTS(),FLOW.time,'');
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Вот что получилось',"Here's what I got"))}
      <div class="kbub ag">${T('Проверь — что-то можно поправить.','Check it — edit anything if needed.')}</div>
      <div class="kplan tight">
        <div class="ftile">${TILE_SVG[tileKeyFor(((FLOW.intent&&FLOW.intent.topics)||[]).join(' ')||String(s.request||FLOW.request||FLOW.text||''))]||TILE_SVG.social}</div>
        <div class="kreq"><div class="hd">${IC.binoc}${T('Запрос','Request')}</div>
          <div class="k-label">${esc(s.request||FLOW.request||FLOW.text)}</div></div>
        ${row(IC.clock,T('Время','Time'), when + (tm?(' — '+tm):''))}
        ${flowOnline()
          ? row(IC.globe, T('Где','Where'), T('Онлайн','Online'))
          : row(IC.pin, T('Район','District'), labelOf(DIST_OPTS(),FLOW.district,T('любой','any')))}
        ${row(IC.target,T('Формат','Format'), s.format||T('Встреча, неформально','Casual meetup'))}
        ${row(IC.diamond,T('Темы','Topics'), locTopicList(s.vibe)||T('пока не задано','not set yet'))}
        <div class="kwhy">${T('Формат и темы — мои предположения, их можно поменять.','Format and topics are my suggestions — tap to adjust.')}</div>
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
  const opt=(key,icon,ti,su)=>`<div class="kopt ${FLOW.adjust===key?'sel':''}" data-act="flow-adjust" data-k="${key}">
    <div class="ic">${icon}</div><div class="bd"><div class="ti">${esc(ti)}</div><div class="su">${esc(su)}</div></div>
    ${FLOW.adjust===key?`<div class="ck">${IC.check2||IC.chevR}</div>`:''}</div>`;
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Точных совпадений пока немного','Not many exact matches yet'))}
      <div class="kbub ag">${T('По твоему запросу с текущими фильтрами вариантов мало.','For your request with the current filters, options are limited.')}</div>
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
async function _planSendLegacy(){
  let r=null;
  try{
    r=await fetch('/api/agent/negotiate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({intent:(FLOW&&flowIntent())||{topics:[]}, profile:matchProfile(),
                           candidates:[PLAN.cand]})}).then(x=>x.json());
  }catch(e){ r=null; }
  const v=(r&&r.candidates&&r.candidates[0])||null;
  PLAN.reply=v; PLAN.mutual=!!(v&&v.agree);
  if(cur!=='waiting') return;                     // the user navigated away meanwhile
  if(PLAN.mutual){
    if(v&&v.reply) PLAN.suggest={title:T('Кофе в центре','Coffee in the city centre'),
      time:slotText()!==T('время не выбрано','time not picked')?slotText():((FLOW&&flowIntent().time)||''),
      place:T('Уютное место рядом','A cosy spot nearby'), quote:String(v.reply)};
    cur=PLAN.suggest?'suggestion':'mutual';
  } else {
    toast(((v&&v.reason)||T('Пока без ответа','No reply yet')));
  }
  render();
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
function personRow(c,i,cls){
  const ints=(c.interests||[]).slice(0,3).map(x=>`<span class="ktag">${esc(x)}</span>`).join('');
  return `<div class="prow ${cls||''}" data-act="cand-open" data-n="${esc(c.name)}">
    <div class="ph">${IC.person}</div>
    <div class="bd">
      <div class="nm"><b>${esc(c.name)}${c.age?(', '+c.age):''}</b>${bandBadge(c)}</div>
      ${(c.reasons_ru||c.reasons_en||[]).length?`<div class="sub">${esc((UILANG==='ru'?c.reasons_ru:c.reasons_en||[])[0]||'')}</div>`:''}
      <div class="meta">${candMeta(c)}</div>
      ${ints?`<div class="meta">${ints}</div>`:''}
    </div>
    <div class="bm" data-act="cand-save" data-n="${esc(c.name)}">${IC.bookmark}</div></div>`;
}

// ---- Your options (479:14751) — tabs + Recommended + Also for you ----
function scr_options(){
  const all=(FLOW&&FLOW.res)||[];
  const top=all[0], rest=all.slice(1,6);
  const tabs=[['people',T('Люди','People')],['groups',T('Группы','Groups')],['events',T('События и места','Events & places')]];
  const body = OPTTAB!=='people'
    ? `<div class="k-cap" style="color:var(--muted);padding:8px 2px">${T('Здесь пока пусто — Kleal ищет только людей на этом этапе.','Nothing here yet — Kleal is matching people at this stage.')}</div>`
    : `${top?`<div style="display:flex;flex-direction:column;gap:12px">
          <div class="k-h3">${T('Рекомендуем','Recommended')}</div>${personRow(top,0,'top')}</div>`:''}
       ${rest.length?`<div style="display:flex;flex-direction:column;gap:12px">
          <div class="k-h3">${T('Также для тебя','Also for you')}</div>
          <div style="display:flex;flex-direction:column;gap:12px">${rest.map((c,i)=>personRow(c,i+1)).join('')}</div></div>`:''}`;
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Твои варианты','Your options'))}
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
      ${kprompt(T('Лучшее совпадение по запросу','Best fit for your request'))}
      <div class="kfused">${personRow(c,0,'top')}${rows}</div>
    </div>
    <div class="kfoot">
      <button class="kbtn pri tall" data-act="cand-open" data-n="${esc(c.name)}">${T('Открыть профиль','Open profile')}</button>
      <button class="kbtn sec" data-act="go-options">${T('Другие варианты','See other options')}</button>
    </div></div>`;
}

// ---- Recommendations (479:14821) — grouped list ----
function scr_recos(){
  const all=(FLOW&&FLOW.res)||[];
  const rows=all.slice(0,5).map((c,i)=>personRow(c,i)).join('<div class="hr"></div>');
  return `<div class="kflow fade">${kbar()}
    <div class="kcont">
      ${kprompt(T('Лучшее совпадение по запросу','Best fit for your request'))}
      ${all.length?`<div class="kgroup">${rows}</div>`
        :`<div class="k-cap" style="color:var(--muted)">${T('Пока никого — попробуй расширить поиск.','No one yet — try widening the search.')}</div>`}
    </div></div>`;
}

// ---- Full profile + Why suggested (479:14967 / 15028) ----
function scr_candprofile(){
  const c=CAND; if(!c) return scr_options();
  const tabs=[['profile',T('Профиль','Profile')],['why',T('Почему','Why suggested')],['vis',T('Видимость','Visibility')]];
  return `<div class="kflow fade">
    <div class="kbar"><div class="kback" data-act="cand-back">${IC.back}</div>
      <div class="k-title" style="flex:1;text-align:center">${esc(c.name)}${c.age?(', '+c.age):''}</div>
      <div style="width:44px"></div></div>
    <div class="kcont">
      <div class="ktabs">${tabs.map(t=>`<div class="kchip ${CTAB===t[0]?'on':''}" data-act="cand-tab" data-k="${t[0]}">${t[1]}</div>`).join('')}</div>
      ${CTAB==='profile'?candProfilePane(c):CTAB==='why'?candWhyPane(c):candVisPane(c)}
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
const FORMAT_OPTS=()=>[
  ['1:1','1:1 · '+T('один на один','one-on-one')],
  ['small',T('Малая группа · 2–5','Small group · 2–5')],
  ['party',T('Компания · 10+','Party · 10+')],
  ['online',T('Онлайн','Online')],
  ['offline',T('Вживую','In person')],
  ['hybrid',T('Гибрид','Hybrid')],
  ['events',T('События и митапы','Events & meetups')]];
function fmtLabel(k){ const o=FORMAT_OPTS().find(x=>x[0]===k); return o?o[1]:String(k); }
const GENDER_OPTS=()=>[['Male',T('Мужчина','Male')],['Female',T('Женщина','Female')],['Other',T('Другое','Other')]];
const SHEET_LANGS=['en','es','ru','fr','de','it','ca','pt','sr','uk','pl','sv'];
function openSheet(kind, idx){
  if(kind==='formats') ESHEET={kind, draft:(DATA.formats||[]).slice()};
  else if(kind==='location') ESHEET={kind, draft:{area:DATA.area||'', radiusKm:DATA.radiusKm||10}};
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
  const row=(on,label,act,v)=>`<div style="display:flex;align-items:center;gap:10px;padding:10px 2px;cursor:pointer" data-act="${act}" data-v="${esc(v)}">
      <div class="cbx ${on?'on':''}">${on?IC.check:''}</div><div style="font-size:14.5px">${esc(label)}</div></div>`;
  let title='', body='', extra='';
  if(e.kind==='formats'){
    title=T('Формат встреч','Social formats');
    body='<div>'+FORMAT_OPTS().map(o=>row(e.draft.includes(o[0]),o[1],'esheet-fmt',o[0])).join('')+'</div>';
  } else if(e.kind==='location'){
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
  if(e.kind==='formats'){ DATA.formats=e.draft.slice(); pushProfile({formats:DATA.formats}); }
  else if(e.kind==='location'){
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
  ESHEET=null; syncBasicsRows(); render(); saveState(); toast(T('Сохранено','Saved'));
}

// ---- Interest sent (479:15090) ----
function sheetHTML(){
  if(SHEET!=='interest') return '';
  const n=(CAND&&CAND.name)||'';
  return `<div class="kscrim" data-act="sheet-close"><div class="ksheet" onclick="event.stopPropagation()">
    <div class="kmedal">${IC.send}</div>
    <div style="display:flex;flex-direction:column;gap:8px">
      <div class="k-h3">${T('Интерес отправлен','Interest sent')}</div>
      <div class="k-small" style="color:var(--muted)">${T('Kleal спросит','Kleal will ask')} ${esc(n)}, ${T('готов(а) ли пообщаться.','if they’d like to chat with you.')}<br>${T('Сообщим, если интерес взаимный.','We’ll let you know if the interest is mutual.')}</div>
    </div>
    <button class="kbtn pri tall" style="width:100%" data-act="sheet-close">${T('Понятно','Got it')}</button>
  </div></div>`;
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
const SCREENS={agenthome:scr_agenthome,overview:scr_overview,snapshot:scr_snapshot,interests:scr_interests,social:scr_social,persona:scr_persona,
  places:scr_places,safety:scr_safety,memory:scr_memory,knows:scr_knows,
  intents:scr_intents,search:scr_search,messages:scr_messages,
  notifs:scr_notifications,matchchat:scr_matchchat,
  reqcomposer:scr_reqcomposer,clarify:scr_clarify,summary:scr_summary,searching:scr_searching,fewmatches:scr_fewmatches,
  options:scr_options,bestfit:scr_bestfit,recos:scr_recos,candprofile:scr_candprofile,
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
  const titleFor = false ? ''
    : cur==='matchchat' ? ((matchWith&&((matchWith.cand&&matchWith.cand.name)||matchWith.who))||'Chat')
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
              ||cur==='reqcomposer'||cur==='clarify'||cur==='summary'||cur==='searching'||cur==='fewmatches'
              ||cur==='options'||cur==='bestfit'||cur==='recos'||cur==='candprofile'
              ||['sendreq','waiting','mutual','suggestion','picktime','pickplace','awaiting','planok','meetstate','mymeetup'].includes(cur));
  const bn=document.getElementById('bnav'); if(bn){ bn.style.display=chat?'none':'flex'; bn.innerHTML=bnavHTML(); }
  // The Explore map is edge-to-edge: no app bar, no body padding, no page scroll.
  const mapfull=(cur==='search');
  const ab=document.querySelector('.appbar'); if(ab) ab.style.display=(cur==='agenthome'||chat||mapfull)?'none':'flex';
  if(editSig){ A.innerHTML=scr_editSignal(); }
  else if(detail){ A.innerHTML=scr_domain(detail); }
  else {
    // Guard: a flow screen without its state used to throw (back → FLOW=null → scr_clarify reads
    // FLOW.when → blank screen). Redirect instead of rendering a broken screen.
    startLive();                       // one live loop for the whole app, whatever screen is open
  const NEEDS_FLOW=['reqcomposer','clarify','summary','searching','fewmatches','bestfit','options','recos'];
    const NEEDS_CAND=['candprofile'];
    const NEEDS_PLAN=['sendreq','waiting','mutual','suggestion','picktime','pickplace','awaiting','planok','meetstate','mymeetup'];
    if(NEEDS_FLOW.includes(cur)&&!FLOW) cur='agenthome';
    else if(NEEDS_CAND.includes(cur)&&!CAND) cur=(FLOW&&FLOW.res&&FLOW.res.length)?'bestfit':'agenthome';
    else if(NEEDS_PLAN.includes(cur)&&!(PLAN&&PLAN.cand)) cur=(FLOW&&FLOW.res&&FLOW.res.length)?'bestfit':'agenthome';
    try{ A.innerHTML=(SCREENS[cur]||scr_overview)(); }
    catch(err){ console.error('render failed on', cur, err); cur='agenthome'; A.innerHTML=scr_agenthome(); }
  }
  if(SHEET==='interest') A.insertAdjacentHTML('beforeend', sheetHTML());
  if(SHEET==='security') A.insertAdjacentHTML('beforeend', securitySheet());
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
    case 'askwhy': toast('Kleal built this from what you shared during onboarding. Every detail is editable.'); break;
    case 'editbasics': openSheet('basics'); break;
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
    case 'autonomy': break;   // handled by data-schoice
    case 'trusted-contact': toast(T('Доверенный контакт — скоро','Add a trusted contact — coming soon')); break;
    case 'review-memory': setTab('memory'); break;   // opens the agent-memory screen
    case 'verify-me': toast(T('Проверка фото и документов — скоро','Photo & ID verification — coming soon')); break;
    case 'blocked': toast('Your blocked list is empty'); break;
    case 'report': toast(T('Центр безопасности и жалобы — скоро','Safety centre & reporting — coming soon')); break;
    case 'export-data': toast('Preparing your data export — we’ll email you a copy'); break;
    case 'delete-account': toast('Delete account would ask you to confirm, then erase everything'); break;
    case 'nav': setTab(ds.tab||'overview'); break;
    case 'fab': case 'createintent': flowStart(''); break;   // one chat screen; the bar carries «+ Создать интент»
    case 'intent-open': openIntentFlow(ds.id); break;
    case 'intent-del': deleteIntent(ds.id); break;
    case 'launch-intent': intentLaunched=true; render(); negotiateIntent(); break;
    case 'intro': { const i=+ds.ci; approveIntro((curIntent&&curIntent.candidates||[])[i], curIntent); break; }
    case 'pass': { const i=+ds.ci; const c=(curIntent&&curIntent.candidates||[])[i]; if(!c)break;
      postFeedback(c.name,'rejected'); c.passed=true; c.agree=false; render(); saveState();
      toast('Kleal will remember you passed on '+c.name); break; }
    case 'live': { const k=ds.kind||'voice'; addNotif('match',(k==='watch'?'Watch-together room opened':'Live voice room opened'),
      'Kleal is inviting nearby people to “'+((curIntent&&curIntent.title)||'your plan')+'”',null); saveState();
      toast((k==='watch'?'Watch room':'Voice room')+' created — inviting people'); break; }
    case 'broaden': broadenIntent(ds.kind); break;
    case 'editsum': editingSummary=true; render(); break;
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
    case 'area-clear': AREAFILTER=null; render(); break;
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
    case 'edit-intent': if(curIntent){ FLOW=FLOW||{}; FLOW.request=curIntent.query||curIntent.title;
        FLOW.intent=curIntent.intent||null; FLOW.summary={request:FLOW.request}; cur='clarify'; render(); }
      else toast(T('Нечего изменять','Nothing to edit')); break;
    case 'search-area': loadExplore(); toast(T('Обновляю карту…','Refreshing the map…')); break;
    case 'filter': toast(T('Фильтры — скоро','Filters are coming soon')); break;
    case 'join': { const p=PUBLIC_INTENTS[+ds.pi];
      if(p&&p.gid) joinGroup(+ds.pi); else joinPublic(+ds.pi); break; }
    case 'group-leave': leaveGroup(ds.gid); break;
    case 'group-host': hostGroup((DATA.intents||[]).find(x=>String(x.id)===String(ds.id))); break;
    case 'join-plan': joinPublic(+ds.pi); break;   // "Позвать" on a For-you-today card
    // Agent Home
    case 'notif': setTab('notifs'); break;
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
    // ---- Figma batch 2: results / candidate ----
    case 'opt-tab': OPTTAB=ds.k; render(); break;
    case 'go-options': cur='options'; render(); break;
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
    case 'sheet-close': SHEET=null; render(); break;
    case 'esheet-close': ESHEET=null; render(); break;
    case 'esheet-accept': acceptSheet(); break;
    case 'esheet-fmt': { const d=ESHEET.draft, i=d.indexOf(ds.v); if(i>=0)d.splice(i,1); else d.push(ds.v); render(); break; }
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


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] == "/":   # ignore ?p=<onboarding profile> query
            b = HTML.encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
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
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print("Kleal Profile demo on http://127.0.0.1:%d" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
