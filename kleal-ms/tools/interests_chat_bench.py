# -*- coding: utf-8 -*-
"""Массовый прогон разговора об интересах: метрики вместо впечатлений.

Сценарий = вступительная фраза + короткие ответы, как отвечает живой человек: уточнение,
односложное «все», согласие, смена темы. Считаются шесть болезней, каждая — с живого экрана.
"""
import json, re, sys, threading, urllib.request
from queue import Queue

BASE = "https://aiopenware.com"
LOCK = threading.Lock()


def post(p, b, t=300):
    r = urllib.request.Request(BASE + p, data=json.dumps(b).encode(),
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=t) as x:
        return json.loads(x.read().decode())


OPENERS = [
    ("люблю в доту играть", "dota"), ("играю в шахматы", "chess"),
    ("люблю заниматься рыбалкой на солнце", "fishing"), ("хожу в горы по выходным", "hiking"),
    ("пью спешелти кофе", "coffee"), ("варю крафтовое пиво дома", "beer"),
    ("бегаю по утрам вдоль моря", "running"), ("занимаюсь йогой", "yoga"),
    ("читаю фантастику перед сном", "reading"), ("хожу в кино на артхаус", "cinema"),
    ("играю на гитаре", "guitar"), ("рисую акварелью", "painting"),
    ("учу испанский", "spanish"), ("хожу на стендап", "comedy"),
    ("катаюсь на велосипеде по городу", "cycling"), ("плаваю в бассейне", "swimming"),
    ("фотографирую улицы", "photography"), ("собираю настолки", "boardgames"),
    ("хожу на концерты", "music"), ("готовлю пасту", "cooking"),
    ("люблю пить воду диджей музыку", "dj"), ("смотрю аниме", "anime"),
    ("занимаюсь скалолазанием", "climbing"), ("хожу в театр", "theatre"),
    ("играю в падел", "padel"), ("вожусь с растениями на балконе", "plants"),
    ("инвестирую в акции", "investing"), ("пишу код по вечерам", "coding"),
    ("хожу на керамику", "ceramics"), ("гуляю с собакой в парке", "dogs"),
]
# Ответы, которыми человек реально отвечает: уточнение, пустое, согласие, новая тема.
# Ответы человека. Три набора: содержательный (место/частота), полупустой и совсем пустой —
# так меряется и уточнение, и поведение при молчании. Одинаковые ответы на ВСЕ интересы дают
# бессмыслицу вроде «кодинг с лодки», и это тоже полезно: показывает, приклеивает ли агент
# чужое обстоятельство к интересу.
FOLLOWUPS = [
    ["в парке", "по субботам", "с друзьями", "часто"],
    ["дома", "по вечерам", "не знаю", "все"],
    ["все", "да", "ну", "да"],
]

SCENES = []
for i, (op, tag) in enumerate(OPENERS):
    for j, fu in enumerate(FOLLOWUPS[:3]):     # три набора ответов на каждый интерес
        SCENES.append({"tag": "%s/%d" % (tag, j), "opener": op, "fu": fu})

MOVE_ON_RX = re.compile(r"(?i)(чем\s+ещё|что\s+ещё|кроме\s+этого|what\s+else|qué\s+más)")
# Вопросы, которых быть не должно. «С кем» — главный: человек пришёл сюда именно потому, что
# ему не с кем. Остальные не дают движку ничего и собираются на своих экранах.
BAD_Q = re.compile(
    r"(?i)(с\s+кем|вместе\s+с\s+кем|кто\s+с\s+тобой|who\s+(do\s+you|with)|con\s+qui[eé]n"
    r"|как\s+часто|how\s+often|почему\s+именно|why\s+(do\s+you|exactly)"
    r"|что\s+(тебе|вам)\s+(в\s+этом\s+)?нравится|what\s+do\s+you\s+like\s+about)")
BODILY = re.compile(r"(?i)(пить\s+вод|попить|спать|дышать|отдыхать|кушать|drink(ing)?\s+water|sleep)")
VERBISH = re.compile(r"(?i)(ю|ть|ться|ешь|ает|аю)$")


def words(t):
    return {w for w in re.findall(r"[\w]+", str(t or "").lower()) if len(w) > 2}


def run(scene, out):
    prof = {"name": "Тест", "age": 30, "area": "Barcelona", "langs": ["ru"], "interests": []}
    msgs, chips, replies = [], [], []
    rec = {"tag": scene["tag"], "turns": 0, "repeat": 0, "bodily": 0, "dupe": 0,
           "long_label": 0, "verb_label": 0, "two_q": 0, "bad_q": 0, "chips": [], "asked": []}
    says = [scene["opener"]] + scene["fu"]
    for say in says:
        msgs.append({"role": "user", "content": say})
        try:
            d = post("/api/buddy/interests-chat",
                     {"messages": msgs, "profile": prof, "lang": "ru", "recorded": chips})
        except Exception as e:
            rec["error"] = str(e)[:80]
            break
        rec["turns"] += 1
        reply = str(d.get("reply") or "")
        msgs.append({"role": "assistant", "content": reply})
        rec["asked"].append(reply)
        # ПОВТОР ВОПРОСА — только среди вопросов. Завершающие и уводящие реплики («Хорошо,
        # записал», «А чем ещё занимаешься?») повторяются по замыслу: это конец темы, а не
        # застрявший вопрос. Считая их, первая версия метрики давала 59% на здоровом поведении.
        if reply.rstrip().endswith("?") and not MOVE_ON_RX.search(reply):
            for old in replies:
                ov = words(reply) & words(old)
                if ov and len(ov) / float(max(1, min(len(words(reply)), len(words(old))))) >= 0.72:
                    rec["repeat"] += 1
                    break
            replies.append(reply)
        if reply.count("?") > 1:
            rec["two_q"] += 1
        if BAD_Q.search(reply):
            rec["bad_q"] = rec.get("bad_q", 0) + 1
        for a in (d.get("added") or []):
            key, label, repl = a.get("key", ""), a.get("label", ""), a.get("replaces", "")
            if BODILY.search(key) or BODILY.search(label):
                rec["bodily"] += 1
            if len(label.split()) > 3:
                rec["long_label"] += 1
            if VERBISH.search(label.split()[0] if label.split() else ""):
                rec["verb_label"] += 1
            if repl:
                chips = [c for c in chips if c.get("key") != repl]
            elif any(c.get("key") == key for c in chips):
                continue
            else:
                # дубль по смыслу: новый ключ содержит старый или наоборот
                for c in chips:
                    ck = c.get("key", "")
                    if ck and (ck in key or key in ck):
                        rec["dupe"] += 1
                        break
            chips.append({"key": key, "label": label})
            prof["interests"] = [c["key"] for c in chips]
    rec["chips"] = [c["label"] for c in chips]
    with LOCK:
        out.append(rec)


def main():
    out, q = [], Queue()
    for s in SCENES:
        q.put(s)

    def worker():
        while True:
            try:
                s = q.get_nowait()
            except Exception:
                return
            run(s, out)
            with LOCK:
                sys.stderr.write("."); sys.stderr.flush()

    # Три потока, не шесть: на шести модель отваливалась по таймауту на каждом пятом
    # сценарии, и метрики считались по неполным данным.
    ts = [threading.Thread(target=worker) for _ in range(3)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    sys.stderr.write("\n")
    json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = len(out)
    turns = sum(r["turns"] for r in out)
    print("сценариев: %d, ходов: %d" % (n, turns))
    for k, ru in (("repeat", "повтор вопроса"), ("bad_q", "запретный вопрос (с кем / как часто)"),
                  ("two_q", "два вопроса в реплике"),
                  ("bodily", "записана телесная надобность"), ("dupe", "дубль чипа"),
                  ("long_label", "подпись длиннее трёх слов"), ("verb_label", "подпись глаголом")):
        tot = sum(r.get(k, 0) for r in out)
        bad = sum(1 for r in out if r.get(k, 0))
        print("   %-32s %3d случаев в %2d сценариях (%.0f%%)" % (ru, tot, bad, 100.0*bad/max(1, n)))
    avg = sum(len(r["chips"]) for r in out) / float(max(1, n))
    print("   %-32s %.2f" % ("чипов на сценарий", avg))


if __name__ == "__main__":
    main()
