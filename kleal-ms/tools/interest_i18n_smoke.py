# -*- coding: utf-8 -*-
"""Смоук словаря интересов: ключи английские, подписи локальные, своё слово не затирается.

Офлайн-часть проверяет правила модуля на временном словаре — без сети и без модели.
Живая часть (передан URL) только читает: профиль и выдача отвечают словарём подписей.

    python3 tools/interest_i18n_smoke.py [https://aiopenware.com]
"""
import importlib
import json
import os
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAIL = []


def check(name, got, want):
    ok = got == want
    print("%s  %-52s %s (ждали %s)" % ("ok  " if ok else "СБОЙ", name, got, want))
    if not ok:
        FAIL.append(name)


# ---------------------------------------------------------------- офлайн: правила модуля
os.environ["KLEAL_INTEREST_I18N"] = os.path.join(tempfile.mkdtemp(), "i18n.json")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))
import interest_i18n as ii  # noqa: E402
importlib.reload(ii)


def fake(batch):
    t = {"рыбачить на море": {"en": "sea fishing", "ru": "сгенерированное", "es": "pesca en el mar"}}
    return [t.get(w, {}) for w in batch]


keys = ii.to_en(["рыбачить на море", "рыбалка", "craft beer", "рыбачить на море"], translate=fake)
check("перевод + канон + латиница + дедуп", keys, ["sea fishing", "fishing", "craft beer"])
check("своё слово стало подписью, не сгенерированное",
      ii.labels_for(["sea fishing"], "ru"), {"sea fishing": "рыбачить на море"})
check("канонный узел дал подписи бесплатно",
      (ii.labels_for(["fishing"], "ru"), ii.labels_for(["fishing"], "es")),
      ({"fishing": "рыбалка"}, {"fishing": "pesca"}))
check("обратный поиск: подпись -> ключ", ii.key_of("РЫБАЧИТЬ НА МОРЕ"), "sea fishing")
check("без переводчика слово остаётся своим", ii.to_en(["зюзюблик пятнистый"]), ["зюзюблик пятнистый"])
check("повторный прогон идемпотентен",
      ii.to_en(["рыбачить на море", "craft beer"]), ["sea fishing", "craft beer"])
ii.learn("sea fishing", ru="попытка затереть")
check("существующая подпись не перезаписана",
      ii.labels_for(["sea fishing"], "ru"), {"sea fishing": "рыбачить на море"})
check("подпись по-английски не выдумывается", ii.labels_for(["craft beer"], "en"), {})

# ---------------------------------------------------------------- живая часть: только чтение
BASE = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
if BASE:
    def post(path, body):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())

    d = post("/api/onboarding/profile", {"name": "Toni Bagués", "lang": "ru"})
    check("профиль отвечает словарём подписей", isinstance(d.get("interestLabels"), dict), True)
    m = post("/api/agent/match", {"intent": {"topics": ["chess"], "phrase": "шахматы",
                                             "mode": "offline", "format": "1:1", "time": "today"},
                                  "profile": {"name": "Смоук", "age": 30, "area": "Barcelona",
                                              "langs": ["ru"]},
                                  "ctx": {"self": "Смоук", "uid": "i18n-smoke"},
                                  "lang": "ru", "limit": 8})
    check("выдача отвечает словарём подписей", isinstance(m.get("interestLabels"), dict), True)
    print("     пример подписей: %s" % json.dumps(dict(list((m.get("interestLabels") or {}).items())[:3]),
                                                  ensure_ascii=False))

print()
if FAIL:
    print("СБОЕВ: %d" % len(FAIL))
    sys.exit(1)
print("словарь интересов: всё зелёное")
