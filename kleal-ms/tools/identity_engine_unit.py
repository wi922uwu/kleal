# -*- coding: utf-8 -*-
"""Тёзки в подборе и переговорах — разные люди (18.10.2026, шаг 1 плана «личность по id»).

    python3 tools/identity_engine_unit.py

Без сети и без базы: временные файлы людей и стора, функции matching напрямую.

ЗАЧЕМ. Хранилище переведено на id 26.09, а слой подбора — нет: карточка выдачи не несла id, и всё,
что шло от неё, держалось за имя. Усталость и бюджет двух «Иванов» складывались, переговоры брали
первую попавшуюся строку тёзки, а раскрытие точного места проверяло взаимность по подписи.
Сторож держит:
  — карточки выдачи несут id, тёзки — две разные карточки;
  — журналы подбора (бюджет, усталость, исходы) ведутся по id;
  — переговоры: карточка без id при тёзках — отказ AMBIGUOUS_PERSON, с id — живая строка этого человека;
  — точное место: совпадение у одного «Ивана» не открывает адрес другому;
  — допуск (_policy_ok_now) видит блок пары по id, а не общую корзину;
  — перевод старых журналов: однозначное имя -> id, тёзки и неизвестные отброшены.
"""
import importlib.util
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ok = bad = 0


def check(name, cond, extra=""):
    global ok, bad
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        bad += 1
        print("  FAIL %s   %s" % (name, str(extra)[:300]))


tmp = tempfile.mkdtemp(prefix="kleal_identity_engine_")
users_p, acc_p, store_p = (os.path.join(tmp, n) for n in ("users.json", "accounts.json", "kleal_store.json"))
os.environ.update({"KLEAL_DB": "json", "KLEAL_USERS": users_p, "KLEAL_ACCOUNTS": acc_p, "KLEAL_STORE": store_p,
                   "KLEAL_MQ": "none", "MATCH_URL": "http://127.0.0.1:9", "LLM_URL": "http://127.0.0.1:9",
                   "KLEAL_REPORT_EVIDENCE_DIR": os.path.join(tmp, "ev")})
base = {"age": 30, "city": "Barcelona", "lat": 41.39, "lon": 2.17, "interests": ["coffee", "chess"],
        "langs": ["ru", "en"], "source": "onboarding", "open": True, "vibe": "chill"}
users = [dict(base, id="on_anna", name="Анна", owner="anna@example.com"),
         dict(base, id="on_ivan_a", name="Иван", owner="ivan-a@example.com"),
         dict(base, id="on_ivan_b", name="Иван", owner="ivan-b@example.com", lat=41.40),
         dict(base, id="on_marta", name="Марта", owner="marta@example.com")]
json.dump({"users": users}, open(users_p, "w"), ensure_ascii=False)
json.dump({}, open(acc_p, "w"))
now = time.time()
json.dump({
    # старые журналы по имени — их переводит _migrate_engine_ids_v3
    "_exposure": {"марта": [now - 60], "иван": [now - 50], "on_ivan_a": [now - 40], "призрак": [now - 30]},
    "_proposals": {"марта": [now - 60], "иван": [now - 50]},
    "_outcomes": [{"name": "марта", "stage": "proposed", "ts": now - 60, "uid": "on_anna"},
                  {"name": "иван", "stage": "proposed", "ts": now - 50, "uid": "on_anna"}],
    "_matches": {"иван": {"name": "иван", "matched_ts": now - 50, "completed_ts": None}},
    "on_anna": {"feedback": {"Марта": "accepted", "Иван": "rejected", "Марта::dating": "rejected"}},
}, open(store_p, "w"), ensure_ascii=False)

sys.dont_write_bytecode = True
sys.path[:0] = [os.path.join(ROOT, "services", "matching"), os.path.join(ROOT, "shared")]
spec = importlib.util.spec_from_file_location("m_identity_engine", os.path.join(ROOT, "services", "matching", "app.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

print("-- перевод старых журналов --")
r = m._migrate_engine_ids_v3(apply=True)
check("перевод выполнен", r.get("applied"), r)
exp = m.SESSION.get("_exposure") or {}
check("однозначное имя -> id", "on_marta" in exp and "марта" not in exp, exp)
check("тёзки отброшены, не угаданы", "иван" not in exp and "on_ivan_b" not in exp, exp)
check("уже id — на месте", "on_ivan_a" in exp, exp)
check("неизвестное отброшено", "призрак" not in exp, exp)
check("бюджет переведён так же", set((m.SESSION.get("_proposals") or {}).keys()) == {"on_marta"}, m.SESSION.get("_proposals"))
check("исходы: только однозначные", [e["name"] for e in m.SESSION.get("_outcomes") or []] == ["on_marta"], m.SESSION.get("_outcomes"))
check("совпадения тёзок отброшены", not (m.SESSION.get("_matches") or {}), m.SESSION.get("_matches"))
fb = (m.SESSION.get("on_anna") or {}).get("feedback") or {}
check("оценки: по id, с режимом", fb == {"on_marta": "accepted", "on_marta::dating": "rejected"}, fb)
check("копия до перевода сохранена", "_exposure" in (m.SESSION.get("_premig_v3") or {}))
check("второй запуск — пропуск", m._migrate_engine_ids_v3(apply=True).get("skipped"))

print("\n-- выдача --")
cands = m.match_candidates({"topics": ["coffee"], "type": "social", "role": "meet", "mode": "offline"},
                           {"name": "Анна", "lat": 41.39, "lon": 2.17, "languages": {"comfortable": ["ru", "en"]}},
                           {"self": "Анна", "self_id": "on_anna"}) or []
ids = [c.get("id") for c in cands]
check("карточки несут id", cands and all(ids), ids)
check("тёзки — две карточки с разными id", {"on_ivan_a", "on_ivan_b"} <= set(ids), ids)
check("себя нет", "on_anna" not in ids, ids)
check("ключ карточки — id", all(m._ckey(c) == str(c["id"]).lower() for c in cands))
check("карточка без id — по подписи", m._ckey({"name": "Демо Человек"}) == "демо человек")

print("\n-- переговоры --")
intent = {"topics": ["coffee"], "title": "Coffee", "mode": "offline", "type": "social", "time": "saturday"}
send, decided = m._negotiate_precheck(intent, [{"name": "Иван", "tier": "T0", "can_outreach": True}])
amb = [d for d in decided if d.get("code") == "AMBIGUOUS_PERSON"]
check("тёзка без id — отказ AMBIGUOUS_PERSON", amb and not send, (send, decided))
send, decided = m._negotiate_precheck(intent, [{"id": "on_ivan_b", "name": "Иван", "tier": "T0", "can_outreach": True}])
picked = [c.get("id") for c in send + decided]
check("с id — именно этот человек", picked == ["on_ivan_b"] and not any(d.get("code") == "AMBIGUOUS_PERSON" for d in decided),
      (send, decided))
send, decided = m._negotiate_precheck(intent, [{"name": "Марта", "tier": "T0", "can_outreach": True}])
check("однозначное имя без id — живая строка по id", [c.get("id") for c in send + decided] == ["on_marta"], (send, decided))

m._log_proposal(m._ckey({"id": "on_ivan_a", "name": "Иван"}))
rec = m._proposals_received_24h()
check("бюджет — у одного Ивана, не у обоих", rec.get("on_ivan_a") == 1 and not rec.get("on_ivan_b") and "иван" not in rec, rec)

print("\n-- точное место --")
m.SESSION["_matches"] = {"on_ivan_a": {"name": "on_ivan_a", "matched_ts": now, "completed_ts": None}}
live_a = dict(users[1], receiving={"disclosure_stage": "full"})
live_b = dict(users[2], receiving={"disclosure_stage": "full"})
da = m._revalidate_disclosure(intent, live_a, "accept")
db_ = m._revalidate_disclosure(intent, live_b, "accept")
mutual_a = any("on_ivan_a" in [str(p).lower() for p in cap.get("participants") or []] for cap in m._match_capsules())
check("совпадение с Иваном A записано по id", mutual_a)
check("Ивану B адрес по совпадению A не открывается", not db_.get("exact_place_ok"), db_)
check("без id взаимности нет", not m._revalidate_disclosure(intent, {"name": "Иван", "receiving": {"disclosure_stage": "full"}},
                                                           "accept").get("exact_place_ok"))

print("\n-- допуск --")
m.SESSION["_blocks"] = {"on_marta": ["on_anna"]}
okp, why = m._policy_ok_now("on_anna", "on_marta")
check("блок пары по id виден допуску", not okp and why == "blocked", (okp, why))
okp, why = m._policy_ok_now("on_anna", "on_ivan_a")
check("чужой блок не мешает", okp, (okp, why))
m.SESSION["me"] = {"blocked": ["on_ivan_a"]}
okp, why = m._policy_ok_now("on_anna", "on_ivan_a")
check("общая корзина me больше не решает", okp, (okp, why))

print("\nитог: %d ok, %d FAIL" % (ok, bad))
sys.exit(1 if bad else 0)
