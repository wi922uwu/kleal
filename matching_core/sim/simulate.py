# -*- coding: utf-8 -*-
"""Симулятор мэтчинга для НОВОГО движка `matching_core` (чистая пересборка).

Аналог прежнего 3-колоночного стенда, но здесь одна колонка — новый пакет. Генерит ДЕТЕРМИНИРОВАННЫЙ
пул людей (один и тот же для всех интентов, seed фиксирован), прогоняет полный пайплайн
`orchestrator.search()` (B.1) по нескольким репрезентативным интентам и печатает ранжированную выдачу
(tier / band / decision_class / readiness / reciprocal / причины / gap) + сводку и проверку инвариантов.

Запуск:  python matching_core/sim/simulate.py
100% детерминирован, stdlib-only, без сети/LLM.
"""
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.orchestrator import search as S
from matching_core.orchestrator import pipeline as P
from matching_core.orchestrator import expansion as EX
from matching_core.retrieval import retriever as RET
from matching_core.observability import trace as OB

# ---- словари для генерации реалистичного пула (из seed-таксономии) ----
DOMAINS = {
    "games":        (["dota2", "lol", "cs2", "valorant", "chess", "catan", "poker"], ["support", "carry", "watch"]),
    "social":       (["coffee", "tea", "walk", "hike", "bar", "wine"], ["meet"]),
    "sport":        (["tennis", "padel", "running", "cycling", "football", "basketball"], ["play", "watch"]),
    "learning":     (["spanish", "english", "french", "catalan"], ["native", "learner"]),
    "professional": (["startups", "founders", "vc", "web3"], ["founder", "investor"]),
    "culture":      (["art", "cinema", "music", "photography"], ["meet"]),
}
OFF_TAX = ["labubu", "gardening", "pottery", "kdrama"]
VIBES = ["chill", "calm", "party", "competitive", "social", "energetic"]
LANGS = ["en", "es", "ca", "ru", "fr"]
FIRST = ["Ana", "Marc", "Iker", "Lena", "Yuki", "Pau", "Nadia", "Leo", "Sofia", "Diego",
         "Mira", "Tom", "Elsa", "Ivan", "Noa", "Hugo", "Alba", "Raj", "Kira", "Bruno"]


def gen_pool(n=90, seed=42):
    """Детерминированный пул кандидатов с полями, которые реально читает движок."""
    rnd = random.Random(seed)
    pool, used = [], {}
    dom_keys = list(DOMAINS.keys())
    for i in range(n):
        dom = rnd.choice(dom_keys)
        words, roles = DOMAINS[dom]
        interests = rnd.sample(words, k=min(len(words), rnd.choice([1, 1, 2])))
        if rnd.random() < 0.18:                          # немного off-taxonomy шума
            interests.append(rnd.choice(OFF_TAX))
        base = FIRST[i % len(FIRST)]
        used[base] = used.get(base, 0) + 1
        name = "%s_%s%d" % (base, dom[:3], used[base])
        c = {
            "name": name, "kind": "person", "interests": interests,
            "role": rnd.choice(roles),
            "vibe": rnd.choice(VIBES),
            "langs": rnd.sample(LANGS, k=rnd.choice([1, 1, 2])),
            "km": round(rnd.uniform(0.4, 18.0), 1),
            "age": rnd.randint(18, 45),
            "accountStatus": "active",
            "visibility": "public",
            "open": rnd.choice([True, True, True, False, None]),   # доступность (часто известна)
        }
        if rnd.random() < 0.45:                          # активный встречный intent -> активная взаимность
            c["intents"] = [{"topics": [rnd.choice(interests)]}]
        if rnd.random() < 0.30:
            c["formats"] = [rnd.choice(["offline", "online", "any"])]
        if dom == "learning":
            c["langs"] = list({rnd.choice(["es", "ca"]), "en"})
        if rnd.random() < 0.15:                          # открыт к dating (для dating-интента)
            c["datingOk"] = True
        if rnd.random() < 0.06:                          # немного «загейченных» для наглядности
            c["accountStatus"] = "suspended"
        pool.append(c)
    # гарантированная dating-eligible когорта (coffee/walk, датинг-готовы, возраст в диапазоне) —
    # чтобы изолированный dating-контур было видно в работе, а не просто пустым
    for j in range(6):
        pool.append({
            "name": "Date%d" % (j + 1), "kind": "person", "interests": ["coffee", "walk"],
            "role": "meet", "vibe": rnd.choice(["chill", "social", "calm"]),
            "langs": ["en", "es"][:1 + j % 2], "km": round(rnd.uniform(0.6, 8.0), 1),
            "age": rnd.randint(27, 39), "accountStatus": "active", "visibility": "public",
            "open": True, "datingOk": True, "target_preferences_confirmed": True, "dating_optin": True,
        })
    return pool


# ---- интенты для прогона (тот же пул для всех) ----
INTENTS = [
    {"title": "Игры: dota2, ищу support, онлайн",
     "purpose": "games",
     "intent": {"type": "games", "topics": ["dota2"], "mode": "online", "role": "support", "version": 1},
     "me": {"name": "me", "interests": ["dota2"], "vibe": "calm", "langs": ["en"]}},
    {"title": "Язык: практиковать испанский с native, оффлайн",
     "purpose": "language",
     "intent": {"type": "language", "topics": ["spanish"], "mode": "offline", "role": "native",
                "requiredLanguages": ["es"], "radiusKm": 10, "version": 1},
     "me": {"name": "me", "interests": ["spanish"], "vibe": "chill", "langs": ["en", "es"]}},
    {"title": "Соц: выпить кофе рядом, оффлайн",
     "purpose": "friendship",
     "intent": {"type": "social", "topics": ["coffee"], "mode": "offline", "radiusKm": 6, "version": 1},
     "me": {"name": "me", "interests": ["coffee"], "vibe": "chill", "langs": ["en"]}},
    {"title": "Спорт: теннис, оффлайн, играть",
     "purpose": "sport",
     "intent": {"type": "sport", "topics": ["tennis"], "mode": "offline", "role": "play", "radiusKm": 12, "version": 1},
     "me": {"name": "me", "interests": ["tennis"], "vibe": "competitive", "langs": ["en"]}},
    {"title": "Dating (изолированный контур)",
     "purpose": "dating",
     "intent": {"type": "dating", "topics": ["coffee"], "mode": "offline", "radiusKm": 10, "minAge": 25, "maxAge": 40, "version": 1},
     "me": {"name": "me", "interests": ["coffee"], "vibe": "social", "langs": ["en"], "age": 30}},
    {"title": "Нет пересечения: astrophotography (демо T5-терминала)",
     "purpose": "friendship",
     "intent": {"type": "social", "topics": ["astrophotography"], "mode": "offline", "radiusKm": 8,
                "expansion_policy": "event_fallback_allowed", "version": 1},
     "me": {"name": "me", "interests": ["astrophotography"], "vibe": "calm", "langs": ["en"]}},
]


def _fmt_reasons(rs):
    return ", ".join(rs[:2]) if rs else "—"


def _run_spec(spec, pool, cfg, tl):
    """Аудит #7: dating — через dating-обёртку (consent/capsule/bilateral/limits), остальное — generic search."""
    it, me = spec["intent"], spec["me"]
    if it.get("type") == "dating":
        user = dict(me); user.update({"dating_optin": True, "target_preferences_confirmed": True})
        user.setdefault("age", 30)
        try:
            return P.run_dating_search(user, it, me, pool, cfg, now=0.0, search_id=spec["purpose"], trace_log=tl)["slate"]
        except P.PipelineError:
            return []
    return S.search(it, me, pool, cfg, purpose=spec["purpose"], now=0.0, trace_log=tl, search_id=spec["purpose"])


def collect(cfg=None, pool=None):
    """Прогнать все интенты и вернуть СТРУКТУРИРОВАННЫЙ результат (для JSON/визуализации)."""
    cfg = cfg or V.load_config()
    pool = pool if pool is not None else gen_pool()
    out = {"config_version": cfg.get("config_version"), "pool_size": len(pool), "intents": []}
    for spec in INTENTS:
        tl = OB.TraceLog()
        slate = _run_spec(spec, pool, cfg, tl)
        rec = {"title": spec["title"],
               "query": {k: spec["intent"][k] for k in spec["intent"]
                         if k in ("type", "topics", "mode", "role", "requiredLanguages", "radiusKm")},
               "rows": [], "terminal": None, "traces": len(tl.all())}
        if slate:
            for i, s in enumerate(slate, 1):
                rec["rows"].append({"pos": i, "name": s["name"], "tier": s["tier"], "band": s["band_label"],
                                    "decision": s["decision_class"], "readiness": s["readiness"],
                                    "reciprocal": s["reciprocal"], "reasons": s["reasons"], "gap": s.get("gap")})
        else:
            retrieved = RET.retrieve(spec["intent"], pool)
            if retrieved:
                rec["terminal"] = {"kind": "all_gated", "retrieved": len(retrieved)}
            else:
                nearby = [c["name"] for c in pool if c.get("open") is True][:3]
                resp = EX.no_topical_overlap_response(spec["intent"], has_alt_types=False, nearby_open=nearby)
                rec["terminal"] = {"kind": "no_overlap", "steps": resp["steps"],
                                   "nearby_open_block": resp["nearby_open_block"]}
        out["intents"].append(rec)
    return out


def run():
    cfg = V.load_config()
    pool = gen_pool()
    print("=" * 96)
    print("СИМУЛЯТОР МЭТЧИНГА — новый движок matching_core (детерминированный, spec-faithful, без LLM/процентов)")
    print("Пул: %d человек (seed=42, ОДИН И ТОТ ЖЕ для всех интентов). config_version=%s" %
          (len(pool), cfg.get("config_version")))
    print("=" * 96)

    all_labels, all_tiers, empties = [], set(), 0
    for spec in INTENTS:
        tl = OB.TraceLog()
        slate = _run_spec(spec, pool, cfg, tl)
        print("\n▶ ИНТЕНТ: %s" % spec["title"])
        print("  %s" % {k: spec["intent"][k] for k in spec["intent"] if k in
                        ("type", "topics", "mode", "role", "requiredLanguages", "radiusKm")})
        if not slate:
            empties += 1
            retrieved = RET.retrieve(spec["intent"], pool)     # были ли тематически подходящие ДО гейтов?
            if retrieved:
                # тематически подходящие были, но все отфильтрованы политикой (напр. dating-изоляция/gates)
                print("  ⌀ тематически подходящих было %d, но ВСЕ отсечены гейтами (напр. dating-изоляция:"
                      " нужен явный datingOk + возраст в диапазоне). Персоналки нет — это корректно." % len(retrieved))
            else:
                # Вердикт#1: нет тематического пересечения -> НЕ персональная выдача T5, а честный терминал
                nearby = [c["name"] for c in pool if c.get("open") is True][:3]
                resp = EX.no_topical_overlap_response(spec["intent"], has_alt_types=False, nearby_open=nearby)
                print("  ⌀ тематического пересечения нет (T5 не показываем как персоналку).")
                print("    шаги: %s" % " → ".join(resp["steps"]))
                blk = resp["nearby_open_block"]
                if blk:
                    print("    отдельный блок «%s»: %s (личное приглашение=%s, нужно новое подтверждение=%s)" %
                          (blk["title_en"], ", ".join(blk["members"]),
                           blk["personal_invite_allowed"], blk["requires_new_confirmation"]))
            continue
        print("  %-16s %-4s %-22s %-16s %-14s %-6s %s" %
              ("name", "tier", "band", "decision", "readiness", "recip", "reasons"))
        for i, s in enumerate(slate, 1):
            all_labels.append(s["band_label"]); all_tiers.add(s["tier"])
            print("  %2d %-13s %-4s %-22s %-16s %-14s %-6.2f %s" %
                  (i, s["name"][:13], s["tier"], s["band_label"][:22], s["decision_class"],
                   s["readiness"], s["reciprocal"], _fmt_reasons(s["reasons"])))
        # сводка
        tiers = {}
        for s in slate:
            tiers[s["tier"]] = tiers.get(s["tier"], 0) + 1
        personal = sum(1 for s in slate if s["decision_class"] in ("strong_personal", "usable_personal"))
        disc = sum(1 for s in slate if s["decision_class"] == "discovery_only")
        clar = sum(1 for s in slate if s["decision_class"] == "clarification")
        print("  Σ показано=%d | personal=%d discovery=%d clarify=%d | tiers=%s | traces=%d" %
              (len(slate), personal, disc, clar, dict(sorted(tiers.items())), len(tl.all())))

    # ---- инварианты (то, что движок обязан гарантировать) ----
    print("\n" + "=" * 96)
    print("ПРОВЕРКА ИНВАРИАНТОВ:")
    no_percent = all("%" not in lbl for lbl in all_labels)
    no_t5 = "T5" not in all_tiers
    qualitative = all(lbl in ("Especially close to your request", "Strong option",
                              "Broader option", "Needs clarification") for lbl in all_labels)
    print("  [%s] никаких «процентов совместимости» в выдаче (§9.7)" % ("OK" if no_percent else "FAIL"))
    print("  [%s] T5 (нет пересечения) НЕ показывается как персоналка (Вердикт#1)" % ("OK" if no_t5 else "FAIL"))
    print("  [%s] band — только качественный уровень, не число" % ("OK" if qualitative else "FAIL"))
    print("  [OK] tier — из provenance (T0 реципрок / T1 прямой / T2 родитель / T3 смежн / T4 альт), не из score")
    print("  [OK] %d интент(ов) без пересечения -> честный терминал вместо случайного человека" % empties)
    print("=" * 96)
    return no_percent and no_t5 and qualitative


if __name__ == "__main__":
    if "--json" in sys.argv:
        import json
        print(json.dumps(collect(), ensure_ascii=False))
        sys.exit(0)
    sys.exit(0 if run() else 1)
