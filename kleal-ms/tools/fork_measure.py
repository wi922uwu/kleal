#!/usr/bin/env python3
"""РАЗВИЛКА БЕЗ ВЫБОРА: человек называет два занятия с условием, карточка не собирается.

Форма снята живым повтором устойчиво молчащих разговоров 17.09.2026: «если не получится», «si no»,
«or», «вместо того чтобы». Мерим долю разговоров БЕЗ карточки — отдельно для развилок и для
обычных просьб того же вида (сторож: если проседают и те и другие, дело не в развилке).
"""
import collections, json, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

PROF = {"ru": {"name": "Иван", "age": 30, "area": "Barcelona", "langs": ["ru"]},
        "en": {"name": "John", "age": 30, "area": "Barcelona", "langs": ["en"]},
        "es": {"name": "Juan", "age": 30, "area": "Barcelona", "langs": ["es"]}}

FORK = [
    ("ru", ["думаю поиграть в настолки", "но если не получится, можем потренироваться на скейте"]),
    ("ru", ["нужно чем-то заняться вечером", "возможно, кино или прогулка"]),
    ("ru", ["хочу сходить в бар", "а если не выйдет, то просто кофе"]),
    ("ru", ["давай в субботу на велике", "или, если дождь, в настолки"]),
    ("en", ["thought i'd try a new restaurant", "but changed my mind", "rather meet for coffee"]),
    ("en", ["maybe a concert tonight", "or if that's too loud, a quiet walk"]),
    ("en", ["i could go bouldering", "or otherwise just play chess"]),
    ("en", ["either a museum or a picnic", "whatever works"]),
    ("es", ["hoy me da por algo cultural", "una exposición, o un concierto pequeñito", "si no, también un museo"]),
    ("es", ["me apetece algo tranquilo, no salir a correr", "como leer o escuchar música"]),
    ("es", ["podemos jugar al pádel", "o si no, tomar un café"]),
    ("es", ["quizá cine", "o mejor una cena tranquila"]),
]
PLAIN = [
    ("ru", ["хочу поиграть в настолки в субботу"]),
    ("ru", ["давай сходим в кино вечером"]),
    ("ru", ["хочу побегать в парке"]),
    ("ru", ["ищу компанию выпить кофе"]),
    ("en", ["i want to play board games on saturday"]),
    ("en", ["looking for someone to grab coffee with"]),
    ("en", ["want to go for a run in the park"]),
    ("en", ["let's watch a movie tonight"]),
    ("es", ["quiero jugar a los juegos de mesa el sábado"]),
    ("es", ["busco alguien para tomar un café"]),
    ("es", ["quiero salir a correr por el parque"]),
    ("es", ["vamos al cine esta noche"]),
]


def walk(job):
    tag, i, lang, says = job
    msgs, last = [], ""
    for s in says:
        msgs.append({"role": "user", "content": s})
        try:
            req = urllib.request.Request("http://127.0.0.1:7080/api/buddy/chat",
                                         data=json.dumps({"messages": msgs, "lang": lang,
                                                          "profile": PROF[lang]}).encode(),
                                         headers={"Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=200).read().decode())
        except Exception:
            return (tag, i, "СЕТЬ", "", "")
        last = str(r.get("reply") or "")
        msgs.append({"role": "assistant", "content": last})
        it = r.get("intent") or {}
        if it.get("title") or it.get("activity"):
            return (tag, i, "ОК", str(it.get("title") or ""), "")
    return (tag, i, "МОЛЧИТ", "", last[:95])


RUNS = 2
jobs = ([("развилка", i, l, s) for i, (l, s) in enumerate(FORK) for _ in range(RUNS)] +
        [("обычный", i, l, s) for i, (l, s) in enumerate(PLAIN) for _ in range(RUNS)])
with ThreadPoolExecutor(max_workers=6) as p:
    res = list(p.map(walk, jobs))

for tag in ("развилка", "обычный"):
    rows = [r for r in res if r[0] == tag]
    ok = sum(1 for r in rows if r[2] == "ОК")
    mute = sum(1 for r in rows if r[2] == "МОЛЧИТ")
    net = sum(1 for r in rows if r[2] == "СЕТЬ")
    print("%-9s прогонов %2d: карточка %2d, МОЛЧИТ %2d, сеть %d  -> доля молчания %.3f"
          % (tag, len(rows), ok, mute, net, mute / max(len(rows) - net, 1)))
print()
seen = set()
for tag, i, v, title, reply in res:
    if v == "МОЛЧИТ" and (tag, i) not in seen:
        seen.add((tag, i))
        says = (FORK if tag == "развилка" else PLAIN)[i][1]
        print("  [%s] %s" % (tag, " | ".join(says)[:70]))
        print("       ответ: %s" % reply.replace("\n", " "))
