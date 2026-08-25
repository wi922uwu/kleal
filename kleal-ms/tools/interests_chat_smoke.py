# -*- coding: utf-8 -*-
"""Смоук разговора об интересах: шесть болезней, каждая — с живого экрана.

Все шесть найдены не рассуждением, а прогоном в 450 ходов (tools/bench — в scratchpad) и
скриншотами от человека. Здесь по одному короткому сценарию на каждую, чтобы поломка всплывала
за минуту, а не через неделю на пользователе.

    python3 tools/interests_chat_smoke.py [https://aiopenware.com]
"""
import json
import re
import sys
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://aiopenware.com").rstrip("/")
FAIL = []


def post(path, body, timeout=300):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def check(name, got, want):
    ok = got == want
    print("%s  %-52s %s (ждали %s)" % ("ok  " if ok else "СБОЙ", name, got, want))
    if not ok:
        FAIL.append(name)


def talk(says):
    """Провести разговор, вернуть (реплики, чипы)."""
    prof = {"name": "Смоук", "age": 30, "area": "Barcelona", "langs": ["ru"], "interests": []}
    msgs, chips, replies = [], [], []
    for say in says:
        msgs.append({"role": "user", "content": say})
        d = post("/api/buddy/interests-chat",
                 {"messages": msgs, "profile": prof, "lang": "ru", "recorded": chips})
        reply = str(d.get("reply") or "")
        msgs.append({"role": "assistant", "content": reply})
        replies.append(reply)
        for a in (d.get("added") or []):
            old = str(a.get("replaces") or "")
            if old:
                chips = [c for c in chips if c.get("key") != old]
            if not any(c.get("key") == a.get("key") for c in chips):
                chips.append({"key": a.get("key"), "label": a.get("label")})
            prof["interests"] = [c["key"] for c in chips]
    return replies, chips


# 1. Уточнение ЗАМЕНЯЕТ, а не плодит второй чип про то же самое.
#    Было: «рыбалкой на солнце» + «рыбачить с лодки на море» — два чипа про одну рыбалку.
replies, chips = talk(["люблю заниматься рыбалкой на солнце", "на море", "с лодки"])
print("     чипы: %s" % [c["label"] for c in chips])
check("уточнение не плодит чипы", len(chips), 1)

# 2. Подпись — короткое имя занятия, а не цитата и не глагол.
lab = (chips[0]["label"] if chips else "")
check("подпись не длиннее трёх слов", len(lab.split()) <= 3, True)
check("подпись не начинается с «люблю»", bool(re.match(r"(?i)^(я\s+)?люблю", lab)), False)

# 3. Обстоятельство не приклеивается к чужому интересу.
#    Было: «пишу код» + «с лодки» -> «Кодинг с лодки».
_, chips2 = talk(["пишу код по вечерам", "с лодки"])
glued = [c for c in chips2 if "лодк" in str(c.get("label", "")).lower()
         or "boat" in str(c.get("key", "")).lower()]
check("чужое обстоятельство не приклеено", glued, [])

# 4. Телесная надобность не записывается, а настоящий интерес из той же реплики — записывается.
#    Было: записано «пить воду», диджей-музыка потеряна.
_, chips3 = talk(["люблю пить воду диджей музыку"])
labels3 = " ".join(str(c.get("label", "")) + str(c.get("key", "")) for c in chips3).lower()
check("«пить воду» не интерес", bool(re.search(r"пить\s+вод|drink", labels3)), False)

# 5. Два вопроса на интерес, потом смена темы. Было: пять переформулировок одного вопроса.
replies5, _ = talk(["играю в шахматы", "в парке", "по субботам", "с друзьями"])
move_on = re.compile(r"(?i)(чем\s+ещё|что\s+ещё|кроме\s+этого|записал|ок\b|понял)")
check("после двух вопросов уходит с темы",
      any(move_on.search(r) for r in replies5[2:]), True)

# 6. НЕ СПРАШИВАЕТ «С КЕМ». Человек пришёл сюда именно потому, что ему не с кем — вопрос либо
#    бессмысленный, либо болезненный, и движку он ничего не даёт. Заодно проверяются остальные
#    пустые оси: частота, «почему», «что тебе нравится». Время, место, размер компании и пол
#    собираются на своих экранах, здесь их спрашивать незачем.
BAD_Q = re.compile(
    r"(?i)(с\s+кем|вместе\s+с\s+кем|кто\s+с\s+тобой|как\s+часто|почему\s+именно"
    r"|что\s+(тебе|вам)\s+(в\s+этом\s+)?нравится)")
bad = []
for says in (["играю в шахматы", "в парке"], ["бегаю по утрам", "вдоль моря"],
             ["собираю настолки", "дома"]):
    reps, _ = talk(says)
    bad += [r for r in reps if BAD_Q.search(r)]
check("не спрашивает «с кем» и прочее пустое", bad, [])

# 7. Пустые ответы не превращаются в допрос.
replies6, _ = talk(["хожу в театр", "все", "да", "ну"])
qs = [r for r in replies6[1:] if r.rstrip().endswith("?")]
check("на пустые ответы не давит вопросами", len(qs) <= 1, True)

print()
if FAIL:
    print("СБОЕВ: %d" % len(FAIL))
    sys.exit(1)
print("разговор об интересах: всё зелёное")
