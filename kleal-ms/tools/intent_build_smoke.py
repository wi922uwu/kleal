# -*- coding: utf-8 -*-
"""Смоук сборки интента: путь «разговор -> интент» жив на НАСТОЯЩЕМ профиле.

ЗАЧЕМ ИМЕННО НАСТОЯЩИЙ. Сборка ломалась только на профилях из хранилища, а на выдуманном
минимальном работала: `goals` в хранилище лежит списком, а читатель ждал словарь, и
`(p.get("goals") or {}).get("primary")` падал с AttributeError внутри `_baseline_signals`.
Исключение проглатывалось, человек получал «Что-то я подвис — повтори, пожалуйста?», повтор давал
то же самое. Интент не собирался НИ У КОГО из 766 человек, и ни один тест этого не видел, потому
что все они ходили с профилем, собранным в самом тесте.

Поэтому смоук берёт профиль из живого хранилища и требует именно готовности, а не «сервис ответил».

    python3 tools/intent_build_smoke.py [https://aiopenware.com]
"""
import json
import sys
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://aiopenware.com").rstrip("/")
FAIL = []


def post(path, body, timeout=240):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def check(name, got, want):
    ok = got == want
    print("%s  %-46s %s (ждали %s)" % ("ok  " if ok else "СБОЙ", name, got, want))
    if not ok:
        FAIL.append(name)


# Форма goals — та самая, на которой всё падало. Проверяется первой и без модели.
for shape, tag in (({"goals": ["friends", "networking"]}, "список"),
                   ({"goals": {"primary": ["dating"]}}, "словарь"),
                   ({"goals": "friends"}, "строка"),
                   ({}, "нет поля")):
    try:
        r = post("/api/buddy/persona", dict(shape, name="Форма Целей", profile=dict(shape)))
        alive = isinstance(r, dict)
    except Exception as e:
        alive = "%s" % type(e).__name__
    check("профиль с goals-%s не роняет сервис" % tag, alive, True)

WHO = "Toni Bagués"
prof = (post("/api/onboarding/profile", {"name": WHO}) or {}).get("user")
check("профиль из хранилища найден", bool(prof), True)
check("goals лежит списком (как в проде)", isinstance((prof or {}).get("goals"), list), True)

msgs = [{"role": "user", "content": "хочу играть в шахматы в парке по субботам"},
        {"role": "assistant", "content": "Понял. С кем именно хочешь играть?"},
        {"role": "user", "content": "с кем-то примерно моего уровня"},
        {"role": "assistant", "content": "Хорошо. Где удобнее?"},
        {"role": "user", "content": "в парке сьютаделья"}]
d = post("/api/buddy/intent-build", {"messages": msgs, "profile": prof})
print("     ответ построителя: %s" % str(d.get("reply"))[:90])
check("интент готов на настоящем профиле", bool(d.get("ready")), True)
check("темы извлечены", bool(((d.get("intent") or {}).get("topics"))), True)

if d.get("ready"):
    intent = dict(d.get("intent") or {})
    intent.setdefault("mode", "offline")
    intent.setdefault("format", "1:1")
    m = post("/api/agent/match", {"intent": intent, "profile": prof,
                                  "ctx": {"self": WHO, "uid": "smoke"}, "limit": 8})
    cs = m.get("candidates") or []
    print("     поиск по собранному интенту: %d человек, ярусы %s" % (
        len(cs), sorted(set(c.get("tier") for c in cs))))
    check("по собранному интенту кто-то находится", bool(cs), True)

# ---------------------------------------------------------------- вопросы не про логистику
# Построитель уточняет ТОЛЬКО тему. Время, место, район и размер компании человек ставит
# ползунками на следующем экране, и спросить их здесь — заставить ответить дважды. Промпт это
# запрещает прямым перечислением, но 70B правило нарушал: на живом экране спрашивал «один или с
# компанией?», а воспроизведение дало ещё «где — в парке или по набережной?» и «утром или
# вечером?». Сторож `asks_logistics` в services/buddy/app.py ловит это детерминированно.
import re  # noqa: E402

BAD_Q = re.compile(
    r"(?i)(когда\b|во\s*сколько|утром\s+или|вечером\s+или|какой\s+день|\bгде\b"
    r"|в\s*каком\s+районе|сколько\s+человек|один\s+или\s+с\s+компанией|вдвоём\s+или"
    r"|одному\s+или|наедине\s+или)")

for say in ("хочу бегать", "побегать", "хочу найти с кем бегать", "хочу гулять"):
    d = post("/api/buddy/intent-build", {"messages": [{"role": "user", "content": say}],
                                         "profile": prof})
    r = str(d.get("reply") or "")
    asked = bool("?" in r and BAD_Q.search(r))
    check("«%s» — не спрашивает логистику" % say, asked, False)
    if asked:
        print("     спросил: %s" % r[:80])

# ...но уточнить ТЕМУ по-прежнему должен, иначе сторож задушил бы полезное
_vague = post("/api/buddy/intent-build",
              {"messages": [{"role": "user", "content": "хочу кофе"}], "profile": prof})
check("широкий запрос всё ещё уточняется", "?" in str(_vague.get("reply") or ""), True)
print("     спросил: %s" % str(_vague.get("reply"))[:80])
# Подсказки к вопросу обязаны быть ОТВЕТАМИ на него, а не случайными фразами.
_h = _vague.get("hints") or []
check("подсказки к вопросу есть", len(_h) == 3, True)

print()
if FAIL:
    print("СБОЕВ: %d" % len(FAIL))
    sys.exit(1)
print("сборка интента: всё зелёное")
