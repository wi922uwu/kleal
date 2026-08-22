# -*- coding: utf-8 -*-
"""Закрытие partial — Батч 2: каноническая таксономия (§6 negative/complementary в скоринге,
§8.1 purpose-isolation data-driven, §5 канонические слоты + schema-валидация)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.taxonomy import canonical as CN
from matching_core.policy_engine import gates as G, engine as PE
from matching_core.intent_compiler import compiler as CO, clarification as CL
from matching_core.feature_builder import builder as FB

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    # ---- канон загружен ----
    check("CN1 канон доступен (405 нод, ~1200 алиасов, 560 рёбер)",
          CN.AVAILABLE and len(CN.NODES) == 405 and len(CN.ALIAS) > 1000)
    check("CN2 resolve alias -> node", CN.resolve_node("coffee") == "I_coffee_chat" and CN.resolve_node("dota") == "I_dota2")
    check("CN3 similarity по канон-иерархии (padel/tennis sibling)", CN.similarity_nodes("padel", "tennis") == 3)
    check("CN4 slots домена загружены", len(CN.slots_for_domain("social_meet")) >= 5)

    # ---- §8.1/§17.2 purpose isolation (data-driven из blocked_cross_purpose) ----
    check("CN5 purpose_blocked dating<->friendship", CN.purpose_blocked("dating", "friendship"))
    check("CN6 purpose_blocked games<->dating", CN.purpose_blocked("games", "dating"))
    check("CN7 не блокирует одинаковые", not CN.purpose_blocked("friendship", "friendship"))
    # гейт: intent games, кандидат объявил purpose=dating -> BLOCK
    v = G.intent_mode_isolation({"type": "games"}, {"purpose": "dating", "datingOk": True}, {})
    check("§8.1 purpose isolation в гейте -> BLOCK", v[0] == G.BLOCK and "isolation" in v[1])
    v2 = PE.evaluate({"type": "games"}, {"name": "x", "purpose": "dating", "datingOk": True, "age": 30, "langs": ["en"]}, {"blocked": set()})
    check("§8.1 через evaluate -> BLOCK", v2["decision"] == PE.BLOCK)
    # кандидат без purpose -> не блокируется (аддитивно, старое поведение)
    v3 = G.intent_mode_isolation({"type": "games"}, {"name": "y"}, {})
    check("§8.1 кандидат без purpose -> ALLOW (совместимость)", v3[0] == G.ALLOW)

    # ---- §6 complementary в СКОРИНГЕ ----
    check("CN8 is_complementary spanish<->english (language_pair)", CN.is_complementary_nodes("spanish", "english"))
    F = FB.build_features({"topics": ["spanish"], "requiredLanguages": []}, {"vibe": "chill"},
                          {"interests": ["english"], "langs": []}, "language_exchange")
    check("§6 complementary влияет на domain_constraints (было unused)",
          F["domain_constraints"][0] == FB.K_MATCH and F["domain_constraints"][2] == "complementary")

    # ---- §5 каноническая clarification + schema ----
    cat = CL.slots_catalog("social_meet")
    check("§5 slots_catalog из канона (hard/soft + вопросы)",
          any(c["klass"] == "P0" and c["question"] for c in cat))
    sel = CL.select_slot_question("social_meet", ["purpose", "time.window"])
    check("§5 select_slot_question выбирает P0", sel and sel["klass"] == "P0")
    ok, errs = CO.validate_schema({"topics": "not-a-list", "radiusKm": "abc"})
    check("§5 schema-валидация ловит неверные типы", (not ok) and len(errs) == 2)
    comp = CO.compile_intent({"topics": ["coffee"], "type": "social_meet"}, intent_id="i1", user_id="u1", created_at=0.0, ttl_sec=10)
    check("§5 compile несёт schema_ok", comp["schema_ok"] is True)
    # blocking clarifications: нет времени/локации -> блокеры (проверяем СОДЕРЖАНИЕ, не только тип)
    bl = CO.blocking_clarifications(comp, "social_meet")
    check("§5 needs_confirmation ПОТРЕБЛЯЕТСЯ (незаполненный hard-слот -> блокер)",
          isinstance(bl, list) and "location.area_or_online" in bl)

    print("\nБатч 2 (canonical taxonomy): %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
