# -*- coding: utf-8 -*-
"""§18 доменные сценарии — end-to-end search() пайплайн (B.1) + C#15/#17 + детерминизм/traces/no-percent."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.orchestrator import search as S
from matching_core.observability import trace as OB

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def _by(slate, name):
    return next((s for s in slate if s["name"] == name), None)


def run():
    cfg = V.load_config()

    # ---------- §18.2 Dota 2: carry ищет support, EU West ----------
    intent = {"type": "games", "topics": ["dota2"], "mode": "online", "role": "support", "version": 1}
    me = {"name": "me", "interests": ["dota2"], "vibe": "calm", "langs": ["en"]}
    pool = [
        {"name": "p_dota", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}], "role": "support", "open": True, "langs": ["en"], "vibe": "calm"},
        {"name": "p_lol", "interests": ["lol"], "role": "support", "open": True, "langs": ["en"], "vibe": "calm"},
        {"name": "p_watch", "interests": ["dota2"], "role": "watch", "open": True, "langs": ["en"]},
    ]
    tl = OB.TraceLog()
    slate = S.search(intent, me, pool, cfg, purpose="games", trace_log=tl, search_id="dota")
    d = _by(slate, "p_dota"); l = _by(slate, "p_lol")
    check("D1 Dota reciprocal -> T0", d and d["tier"] == "T0")
    # Вердикт-review#1 регресс: сильный T0-мэтч (без опциональных formats/entities) НЕ должен молча уходить
    # в 'clarification' из-за high_impact_unknown — personal outreach обязан быть достижим end-to-end.
    check("D1b сильный T0 достигает personal outreach (не 'clarification')",
          d and d["decision_class"] in ("strong_personal", "usable_personal"))
    check("D2 LoL -> T2 (parent/sibling)", l and l["tier"] == "T2")
    # C#15: Dota intent НЕ идёт LoL player без broad consent (T2 -> не personal outreach)
    check("C#15 LoL(T2) без consent -> не personal", l and l["decision_class"] not in ("strong_personal", "usable_personal"))
    from matching_core.relevance_engine import decision as DE
    gd = cfg["domains"]["games"]
    check("C#15 механизм: T2 unlock только с broad consent",
          DE.decision_class(0.9, 0.9, "T2", gd, broad_consent=False) not in ("strong_personal", "usable_personal")
          and DE.decision_class(0.9, 0.9, "T2", gd, broad_consent=True) == "usable_personal")
    check("D3 decision traces записаны", len(tl.all()) >= 2)
    check("D4 нет процентов в slate", all("%" not in str(s.get("band_label", "")) for s in slate))
    check("D5 band — текстовый уровень (§9.7)", d and d["band_label"] in ("Especially close to your request", "Strong option", "Broader option", "Needs clarification"))

    # детерминизм: два прогона идентичны
    s1 = S.search(intent, me, pool, cfg, purpose="games")
    s2 = S.search(intent, me, pool, cfg, purpose="games")
    check("D6 детерминизм: два прогона идентичны", [x["name"] for x in s1] == [x["name"] for x in s2]
          and [x["reciprocal"] for x in s1] == [x["reciprocal"] for x in s2])

    # ---------- §18.4 испанский: комплементарность native↔learner ----------
    lang_intent = {"type": "language", "topics": ["spanish"], "mode": "offline", "role": "native", "version": 1,
                   "requiredLanguages": ["es"]}
    lang_me = {"name": "me", "interests": ["spanish"], "langs": ["en", "es"], "vibe": "chill"}
    lang_pool = [
        {"name": "native", "interests": ["spanish"], "role": "native", "langs": ["es", "en"], "open": True, "km": 2, "vibe": "chill"},
        {"name": "learner", "interests": ["spanish"], "role": "learner", "langs": ["es", "en"], "open": True, "km": 2, "vibe": "chill"},
    ]
    ls = S.search(lang_intent, lang_me, lang_pool, cfg, purpose="language")
    nat, lrn = _by(ls, "native"), _by(ls, "learner")
    # native (комплементарен ищущему-native? role=native ищет... ) — комплементарность даёт роль-match выше
    check("L1 native выше learner (комплементарность важнее similarity §18.4)",
          nat and lrn and ls.index(nat) < ls.index(lrn))

    # ---------- §18.5 фаундеры: target проверяется по роли кандидата, НЕ по self profession (C#17) ----------
    net_intent = {"type": "networking", "topics": ["startups"], "mode": "offline", "role": "founder", "version": 1}
    net_me = {"name": "me", "interests": ["startups"], "profession": "student", "langs": ["en"], "vibe": "social"}
    net_pool = [{"name": "founder_x", "interests": ["startups"], "role": "founder", "open": True, "langs": ["en"], "km": 3, "vibe": "social"}]
    ns = S.search(net_intent, net_me, net_pool, cfg, purpose="networking")
    fx = _by(ns, "founder_x")
    check("C#17 founder target матчится по роли кандидата (self profession не мешает)",
          fx is not None and fx["tier"] in ("T0", "T1", "T2"))

    print("\n§18 domain scenarios: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
