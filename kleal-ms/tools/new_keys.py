#!/usr/bin/env python3
"""САМОДОПИСЫВАНИЕ КЛЮЧЕЙ: собрать кандидатов, спросить модель, предложить правку реестра.

ЗАЧЕМ. Фильтрация верно вытаскивает из речи английские слова — `construction`, `landscaping`,
`options`, `lawn mowing`. Таксономия их не знает, и они гибнут: не ищутся, не показываются чипами,
не попадают в имя затеи. Модель уже умеет их называть; не хватало места, куда записать.

ОТКУДА БЕРЁМ КАНДИДАТОВ. Только из ответов, где фильтрация отвечала СВОЕЙ МОДЕЛЬЮ. Отличить можно
по её пометке `note`: при срыве там стоит «keyword fallback», и темы — это просто слова человека
(«хочу», «поговорить», «ищу»). До 18.09.2026 она срывалась почти всегда, и журнал за тот период для
сбора непригоден — 646 «неизвестных английских слов», из которых верхушка `hoy`, `algo`, `wanna`.

ПОЧЕМУ НЕ ПРИНИМАЕМ ВСЁ ПОДРЯД. Ключ ценен тем, что он ОДИН НА ВСЕХ. Если каждый разговор чеканит
своё слово, один человек получит `lawn mowing`, другой `mowing`, третий `gardening` — и они никогда
не встретятся в поиске. Поэтому кандидат сперва проверяется вопросом «это то же, что уже есть?».

ПОРОГ ЧАСТОТЫ. Слово, сказанное один раз, ещё не ключ: «падик» встречается однажды и ключом быть не
должен. Берём то, что повторилось.

Ничего не записывает без --apply. Предложения складывает в JSON, чтобы их можно было прочитать
глазами до того, как они попадут в живой реестр.
"""
import argparse, collections, io, json, os, re, sys, urllib.request

sys.path.insert(0, "/opt/kleal/kleal-ms")
import services.buddy.app as B  # noqa: E402

LOG = "/root/kleal-archive/card-model.jsonl"
REG = "/opt/kleal/kleal-ms/shared/interests.json"
OUT = "/root/kleal-archive/new-keys-proposal.json"
LLM = "http://127.0.0.1:17071/llm/complete"
LATIN = re.compile(r"^[a-z][a-z '-]{2,28}$")

# СЛУЖЕБНОЕ СЛОВО КЛЮЧОМ НЕ БЫВАЕТ, И СПИСКИ ЭТИ У НАС УЖЕ ЕСТЬ.
# Первый прогон 18.09.2026 предложил в ключи `meet`, `fun`, `friends`, `go out`, `socializing`,
# `weather`, `drink` — всё это либо общие слова, либо чувства, либо погода. Спрашивать о них модель
# незачем: сборщик давно держит списки таких слов, и здесь они работают ровно так же.
_ОБЩЕЕ = set()
for _n in ("_GENERIC_TOPIC", "_NO_ACTIVITY", "_FILLER_TOPICS", "_RAW_STOP", "_BROAD_BUT_REAL"):
    _v = getattr(B, _n, None)
    if isinstance(_v, (set, frozenset, dict, list, tuple)):
        _ОБЩЕЕ |= {str(x).lower() for x in _v}
# ...и ещё горсть, которой в тех списках нет, но ключом она быть не может.
_ОБЩЕЕ |= {"meet", "meetup", "hang", "hangout", "go out", "going out", "friends", "friend",
           "people", "someone", "company", "weather", "fun", "funny", "cool", "nice", "good",
           "today", "tonight", "tomorrow", "weekend", "evening", "morning", "time", "idea",
           "something", "anything", "activity", "activities", "plan", "plans", "thing", "things"}


def candidates(min_count):
    """Неизвестные английские темы из ответов, где фильтрация отвечала моделью."""
    seen, rows, skipped = collections.Counter(), 0, 0
    examples = collections.defaultdict(list)
    for line in io.open(LOG, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        note = str(r.get("note") or "")
        if not note:                      # запись сделана до того, как пометку стали писать
            skipped += 1
            continue
        if note == "keyword fallback":    # там не ключи, а слова человека
            skipped += 1
            continue
        rows += 1
        for t in (r.get("was") or []):
            t = str(t).strip().lower()
            if not LATIN.match(t) or B.norm_topic(t) or t in _ОБЩЕЕ:
                continue
            if all(p in _ОБЩЕЕ for p in t.split()):     # «go out», «outdoor activity» — из общих слов
                continue
            seen[t] += 1
            if len(examples[t]) < 2:
                examples[t].append(" | ".join(str(s) for s in (r.get("says") or []))[:70])
    return seen, rows, skipped, examples


def ask(prompt, tries=3):
    for a in range(tries):
        try:
            body = {"model": "qwen3_self", "temperature": 0, "max_tokens": 400,
                    "messages": [{"role": "user", "content": prompt}]}
            req = urllib.request.Request(LLM, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=120).read().decode()).get("content", "")
        except Exception:
            if a + 1 >= tries:
                return ""
    return ""


def propose(words, reg):
    """Спросить модель: это уже известное занятие или новое, и куда его поселить."""
    tree = reg.get("tree") or {}
    места = []
    for b, subs in tree.items():
        for s in (subs or {}):
            места.append("%s/%s" % (b, s))
    known = sorted({w for subs in tree.values() for ws in subs.values() for w in ws})
    p = (
        "Ты ведёшь справочник увлечений приложения для знакомств по интересам.\n"
        "Существующие ветки (широкая/подгруппа):\n%s\n\n"
        "Существующие слова (фрагмент): %s\n\n"
        "Вот слова, которые встретились в живых разговорах, но справочнику неизвестны:\n%s\n\n"
        "Для КАЖДОГО ответь одной строкой JSON в массиве:\n"
        '{"word":"...","same_as":"<существующее слово или пусто>","branch":"<широкая/подгруппа>",'
        '"reason":"<до 8 слов>"}\n'
        "Правила: если слово означает ТО ЖЕ, что уже есть — заполни same_as и оставь branch пустым.\n"
        "Если это отдельное занятие — заполни branch ИЗ СПИСКА ВЕТОК, не выдумывая новых.\n"
        "Если это вообще не занятие (служебное слово, чувство, время) — branch и same_as оба пустые.\n"
        "Ответь ТОЛЬКО массивом JSON."
    ) % ("\n".join(sorted(места)), ", ".join(known[:120]), "\n".join(words))
    raw = ask(p)
    i, j = raw.find("["), raw.rfind("]")
    if i < 0 or j <= i:
        return []
    try:
        return json.loads(raw[i:j + 1])
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=3, help="сколько раз слово должно повториться")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--apply", action="store_true", help="записать предложенное в реестр")
    ap.add_argument("--words", default="", help="разобрать именно эти слова через запятую, минуя корпус")
    a = ap.parse_args()

    # СЛОВА СПИСКОМ, А НЕ ИЗ КОРПУСА. Порог частоты защищает от случайного слова, но он же прячет
    # верное: 18.09.2026 владелец показал разговор про стройку, газон и заборы — фильтрация назвала
    # их правильно (`construction`, `lawn mowing`, `fence painting`), а в корпусе батареи про это
    # говорят 1–2 раза за сутки, потому что её 500 сценариев про другое. Такие слова приносят
    # руками, а разбирает и отсеивает их та же модель и тот же скептик — иначе смысла нет.
    if a.words:
        good = [(w.strip().lower(), 0) for w in a.words.split(",") if w.strip()]
        examples = {w: [""] for w, _ in good}
        print("слов принесено списком: %d" % len(good))
    else:
        seen, rows, skipped, examples = candidates(a.min)
        print("записей с пометкой модели: %d (пропущено без пометки/в запасном режиме: %d)" % (rows, skipped))
        good = [(w, c) for w, c in seen.most_common() if c >= a.min][:a.top]
        print("кандидатов (повторились >= %d раз): %d" % (a.min, len(good)))
    for w, c in good:
        print("   %-22s ×%-3d  %s" % (w, c, (examples[w] or [""])[0]))
    if not good:
        print("нечего предлагать")
        return

    reg = json.load(io.open(REG, encoding="utf-8"))
    plan = propose([w for w, _ in good], reg)
    print()
    print("=== что предлагает модель ===")
    add, alias, drop = [], [], []
    места = {"%s/%s" % (b, s) for b, subs in (reg.get("tree") or {}).items() for s in (subs or {})}
    known = {w for subs in (reg.get("tree") or {}).values() for ws in subs.values() for w in ws}
    for r in plan:
        w = str(r.get("word") or "").strip().lower()
        sa = str(r.get("same_as") or "").strip().lower()
        br = str(r.get("branch") or "").strip().lower()
        if not w:
            continue
        if sa and sa in known:
            alias.append((w, sa, r.get("reason", "")))
        elif br in места:
            add.append((w, br, r.get("reason", "")))
        else:
            drop.append((w, r.get("reason", "")))
    for w, sa, why in alias:
        print("   синоним:  %-20s -> %-18s %s" % (w, sa, why))
    for w, br, why in add:
        print("   новый:    %-20s в %-18s %s" % (w, br, why))
    for w, why in drop:
        print("   не ключ:  %-20s %s" % (w, why))

    # ВТОРАЯ ПРОВЕРКА, СКЕПТИЧЕСКАЯ. Первый прогон показал, почему она нужна: модель отправила
    # `action` (из испанского «prefiero algo de acción» про КИНО) в ветку игр. Один и тот же
    # спрашивающий подтверждает собственную догадку, поэтому проверяет отдельный вопрос, которому
    # велено искать возражение, и при сомнении отвечать «нет».
    def _годится(вид, слово, куда, пример):
        q = ("Слово «%s» встретилось в живом разговоре: «%s».\n"
             "Предлагается %s.\n"
             "Ответь ОДНИМ словом: ДА если предложение верно и слово действительно называет "
             "занятие, которым люди занимаются ВМЕСТЕ; НЕТ если это служебное слово, чувство, "
             "время, погода, общее понятие, или если предложенное место не подходит по смыслу.\n"
             "При любом сомнении отвечай НЕТ." % (слово, пример, куда))
        return "ДА" in (ask(q) or "").upper()[:20]

    alias = [(w, sa, why) for w, sa, why in alias
             if _годится("синоним", w, "считать это тем же, что «%s»" % sa, (examples[w] or [""])[0])]
    add = [(w, br, why) for w, br, why in add
           if _годится("новый", w, "завести новым ключом в ветке «%s»" % br, (examples[w] or [""])[0])]
    print()
    print("после скептической проверки: синонимов %d, новых ключей %d" % (len(alias), len(add)))
    for w, sa, _ in alias:
        print("   синоним:  %-20s -> %s" % (w, sa))
    for w, br, _ in add:
        print("   новый:    %-20s в %s" % (w, br))

    json.dump({"alias": alias, "add": add, "drop": drop}, io.open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print()
    print("предложение записано:", OUT)
    if not a.apply:
        print("НИЧЕГО НЕ ИЗМЕНЕНО. Прочитать глазами, потом запустить с --apply")
        return

    for w, sa, _ in alias:
        reg.setdefault("synonyms", {})[w] = sa
    for w, br, _ in add:
        b, s = br.split("/", 1)
        reg.setdefault("tree", {}).setdefault(b, {}).setdefault(s, [])
        if w not in reg["tree"][b][s]:
            reg["tree"][b][s].append(w)
    json.dump(reg, io.open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("РЕЕСТР ОБНОВЛЁН: синонимов +%d, слов +%d. Перезапустить kleal@matching и kleal@buddy,"
          " затем прогнать эталон." % (len(alias), len(add)))


if __name__ == "__main__":
    main()
