#!/usr/bin/env python3
"""ЧИПЫ МЕРЯЮТСЯ ОТДЕЛЬНО ОТ ИМЕНИ.

ЗАЧЕМ ОТДЕЛЬНАЯ МЕРКА. Батарея судит НАЗВАНИЕ затеи: про то ли она, взяла ли отвергнутое, есть ли
предмет. Про чипы там одна узкая проверка — служебное слово из стоп-листа. Из-за этого беда, о
которой сообщили с телефона («походы потерялись», «movie рядом с Кино»), не ловилась НИЧЕМ, и
чинить её приходилось вслепую.

ЧТО СЧИТАЕТСЯ БЕДОЙ. Во всей системе интерес хранится английским ключом, подпись на языке человека
рисует клиент. Значит:

  НЕ КЛЮЧ      — чип, который не сводится к ключу таксономии. Клиенту его переводить нечем, и он
                 печатает слово сырым: русское «рынок» в английской базе, «movie» рядом с «Кино».
  ДУБЛЬ        — два чипа с одним ключом («movie» и «кино» — это один cinema).
  ПОТЕРЯН      — человек назвал занятие, которое таксономия ЗНАЕТ, а на карточке его нет.
  ГЛАГОЛ       — чип называет действие, а не вещь («любишь», «поиграть»).

Считаем на СОБРАННУЮ карточку и берём ПОСЛЕДНЮЮ за разговор — как и батарея после правки 17.09.
"""
import json, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/kleal/kleal-ms")
from services.buddy.app import norm_topic, _is_verbish        # noqa: E402

URL = "http://127.0.0.1:7075/buddy/chat"
WORD = re.compile(r"[^\w'-]+")


def post(payload, tries=2):
    for a in range(tries):
        try:
            req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
        except Exception:
            if a + 1 >= tries:
                return {}
    return {}


def walk(sc):
    """Досматриваем разговор до конца и берём последнюю карточку."""
    msgs, last = [], None
    for s in sc.get("says") or []:
        msgs.append({"role": "user", "content": s})
        r = post({"user_id": "chips-" + str(sc.get("label")), "messages": msgs,
                  "lang": sc.get("lang") or "ru", "profile": {}})
        if not r:
            return None
        msgs.append({"role": "assistant", "content": r.get("reply") or ""})
        if r.get("intent"):
            last = r["intent"]
    return last


def named_keys(sc):
    """Ключи, которые человек назвал сам, — по всем его репликам."""
    out = []
    for s in sc.get("says") or []:
        for w in WORD.split(str(s).lower()):
            k = norm_topic(w) if w else ""
            if k and k not in out:
                out.append(k)
    return out


def main():
    path = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    scen = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()][:n]

    done = [0]

    def one(sc):
        it = walk(sc)
        done[0] += 1
        print("  %3d/%d %s" % (done[0], len(scen), sc.get("label")), flush=True)
        return it

    with ThreadPoolExecutor(max_workers=4) as pool:
        cards = list(pool.map(one, scen))

    built = 0
    bad_key = dup = lost = verb = 0
    chips_total = 0
    examples = {"НЕ КЛЮЧ": [], "ДУБЛЬ": [], "ПОТЕРЯН": [], "ГЛАГОЛ": []}
    for sc, it in zip(scen, cards):
        if not it:
            continue
        built += 1
        tags = [str(t).strip().lower() for t in (it.get("tags") or []) if str(t).strip()]
        chips_total += len(tags)
        keys = [norm_topic(t) for t in tags]
        title = it.get("title") or ""
        nk = [t for t, k in zip(tags, keys) if k != t]           # сырое слово, а не ключ
        if nk:
            bad_key += 1
            if len(examples["НЕ КЛЮЧ"]) < 6:
                examples["НЕ КЛЮЧ"].append("%s «%s»: %s" % (sc["label"], title, nk))
        seen, d = set(), []
        for t, k in zip(tags, keys):
            kk = k or t
            if kk in seen:
                d.append(t)
            seen.add(kk)
        if d:
            dup += 1
            if len(examples["ДУБЛЬ"]) < 6:
                examples["ДУБЛЬ"].append("%s «%s»: %s из %s" % (sc["label"], title, d, tags))
        v = [t for t in tags if _is_verbish(t)]
        if v:
            verb += 1
            if len(examples["ГЛАГОЛ"]) < 6:
                examples["ГЛАГОЛ"].append("%s «%s»: %s" % (sc["label"], title, v))
        want = named_keys(sc)
        miss = [k for k in want if k not in set(keys) | set(tags)]
        if miss:
            lost += 1
            if len(examples["ПОТЕРЯН"]) < 6:
                examples["ПОТЕРЯН"].append("%s «%s»: нет %s, есть %s" % (sc["label"], title, miss, tags))

    print("ЧИПЫ: сценариев %d, собралось %d, чипов всего %d (%.2f на карточку)"
          % (len(scen), built, chips_total, chips_total / max(built, 1)))
    for name, cnt in (("НЕ КЛЮЧ", bad_key), ("ДУБЛЬ", dup), ("ГЛАГОЛ", verb), ("ПОТЕРЯН", lost)):
        print("   %-10s %4d  (%.3f на собранную)" % (name, cnt, cnt / max(built, 1)))
    for name in examples:
        for e in examples[name]:
            print("     %-8s %s" % (name, e))


if __name__ == "__main__":
    main()
