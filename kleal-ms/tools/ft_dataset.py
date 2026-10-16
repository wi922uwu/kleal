#!/usr/bin/env python3
"""СБОРКА НАБОРА ДЛЯ ДООБУЧЕНИЯ: разговор -> разбор карточки.

ЧТО УЧИМ. Одну узкую работу: по репликам человека сказать, ЧЕМ он в итоге хочет заняться и
какими словами он это назвал. Грамматику заголовка («Поиграть в настолки») строит прежний код —
он это умеет; модели отдаётся только решение, которое сейчас принимают два спорящих чтения.

    вход : реплики человека
    выход: {"key": "boardgames", "subject": "настолки", "role": "play",
            "chips": ["boardgames","cinema"], "dropped": ["cinema"]}

ОТКУДА ПРАВИЛЬНЫЙ ОТВЕТ. В каждой строке склада лежат `expect` (чем разговор должен кончиться) и
`never` (что брать нельзя) — их написал генератор, когда сочинял сценарий, ДО того как сборка
что-либо ответила. Это независимая от нас разметка, и её 28 851 строка.

ПОЧЕМУ ЧИСТИМ. Ручной аудит восемнадцати трудных строк 17.09.2026 нашёл 22% негодных меток:
  * «maybe a picnic or a movie?» — надо picnic, нельзя movie: человек НЕ ВЫБРАЛ, метка произвольна;
  * «quiero algo tranquilo y fresco» — надо `fresco`: это не занятие вовсе;
  * «salir a pasear … y tal vez probar comida nueva» — надо `pasear`, хотя разговор кончился едой.
И ещё 22% «бед» оказались слепотой мерки к синонимам (leer/libros, приставка/видеоигры) — если
строить цель по СЛОВУ, модель выучит эту слепоту. Поэтому цель всегда по КЛЮЧУ таксономии.
"""
import json, re, sys, collections
sys.path.insert(0, "/opt/kleal/kleal-ms")
import services.buddy.app as B

WORD = re.compile(r"[^\W\d_]{3,}", re.U)
# Связки «или/либо» — по ним видно, что человек предложил два варианта.
ALT = re.compile(r"(?iu)(^|\s)(или|либо|or|o)\s")


# Короткие слова сводятся во что попало: `norm_topic("go")` = "golang", и «maybe we can GO
# somewhere» давало затею про язык Go. Для разметки это яд — берём только слова от четырёх букв.
_TOO_SHORT = 4


def keys_of(text):
    """Ключи таксономии, названные в тексте, в порядке появления."""
    out = []
    for w in WORD.findall(str(text).lower()):
        if len(w) < _TOO_SHORT:
            continue
        k = B.norm_topic(w)
        if k and k not in out:
            out.append(k)
    return out


def own_word_for(key, says):
    """Слово САМОГО человека, которым он назвал это занятие."""
    for s in reversed(says):
        for w in WORD.findall(str(s).lower()):
            if B.norm_topic(w) == key:
                return w
    return ""


def build(r):
    """Строка склада -> обучающая пара, либо (None, причина отказа)."""
    says = [str(s) for s in (r.get("says") or []) if str(s).strip()]
    if len(says) < 1:
        return None, "нет реплик"
    exp = [str(e).lower() for e in (r.get("expect") or []) if e]
    nev = [str(n).lower() for n in (r.get("never") or []) if n]

    # 1. Ожидание обязано быть ЗАНЯТИЕМ. «fresco», «sombr», «prошлый» — не занятия.
    want = [B.norm_topic(e) for e in exp]
    want = [k for k in want if k]
    if not want:
        return None, "ожидание не сводится в занятие"
    key = want[0]

    # 2. Неотвечаемая развилка: человек предложил варианты и НЕ выбрал. Признак — в последней
    #    реплике есть связка «или», названо больше одного занятия, и ни одно не запрещено.
    # Смотреть только последнюю реплику мало: «board games or a picnic? | what do you feel like?»
    # проскакивало, потому что связка стояла ходом раньше. Правило: если человек назвал два и
    # больше занятий и НИ ОДНО не отверг, выбора он не сделал — учить на такой строке нечему.
    all_keys = keys_of(" ".join(says))
    if len(all_keys) > 1 and not nev:
        return None, "человек не выбрал между вариантами"

    # 3. Отменённое — то, что человек называл и что попало в `never`.
    said_keys = keys_of(" ".join(says))
    dropped = [k for k in said_keys if any(B.norm_topic(n) == k or n in str(k) for n in nev)]

    # 4. Чипы: ключи, названные человеком, минус отменённое; ожидаемое идёт первым.
    # ЧИПЫ НЕ ДОЛЖНЫ СПОРИТЬ С ОТМЕНЁННЫМ. Раньше выбрасывали `reading`, а `books` оставляли —
    # это одно и то же занятие двумя ключами. Берём только то, что названо ПОСЛЕ последней
    # поправки: всё сказанное до неё человек уже пересмотрел.
    _cut = 0
    for _i, _s in enumerate(says):
        if B._RETRACT.search(str(_s)) or ALT.search(str(_s)):
            _cut = _i
    fresh_keys = keys_of(" ".join(says[_cut:]))
    chips = [key] + [k for k in fresh_keys if k != key and k not in dropped]
    chips = chips[:4]

    # РОЛЬ ИЗ ЦЕЛИ УБРАНА. Она считалась по ВСЕМУ разговору и хватала глагол из брошенной ветки:
    # «making a cake or maybe paint» -> роль `eat`, «quería ir a correr… mejor café» -> роль `run`.
    # Учить модель такому — учить ошибке. Роль прекрасно считает прежний код по выбранному занятию,
    # и она не то, ради чего затевалось дообучение.
    subj = own_word_for(key, says)
    if not subj:
        return None, "человек не называл это занятие своими словами"
    return {
        "says": says,
        "lang": r.get("lang") or "ru",
        "target": {"key": key, "subject": subj, "chips": chips, "dropped": dropped},
        "was_bad": bool(r.get("bad")),
    }, ""


def main():
    rows = []
    for l in open("/root/kleal-archive/dataset.jsonl", encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                rows.append(json.loads(l))
            except Exception:
                pass
    # Эталон-500 исключаем целиком: на нём мы экзаменуем, учиться на нём нельзя.
    bench = set()
    for l in open("/root/kleal-archive/bench-500.jsonl", encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                bench.add(str(json.loads(l).get("label")))
            except Exception:
                pass
    rows = [r for r in rows if str(r.get("label")) not in bench]

    out, why = [], collections.Counter()
    for r in rows:
        pair, reason = build(r)
        if pair:
            out.append(pair)
        else:
            why[reason] += 1

    # Уникальные разговоры: один и тот же сценарий встречается в складе много раз.
    seen, uniq = set(), []
    for p in out:
        k = "|".join(p["says"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)

    hard = [p for p in uniq if p["was_bad"]]
    easy = [p for p in uniq if not p["was_bad"]]
    print("строк склада (без эталона): %d" % len(rows))
    print("отброшено: %s" % dict(why))
    print("пар собрано: %d, уникальных разговоров: %d (трудных %d, лёгких %d)"
          % (len(out), len(uniq), len(hard), len(easy)))
    print("языки:", collections.Counter(p["lang"] for p in uniq).most_common())

    with open("/root/kleal-archive/ft-pairs.jsonl", "w", encoding="utf-8") as f:
        for p in uniq:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print("записано: /root/kleal-archive/ft-pairs.jsonl")

    print()
    print("=== ВОРОТА: двадцать трудных пар на ручную проверку ===")
    import random
    random.Random(23).shuffle(hard)
    for i, p in enumerate(hard[:20], 1):
        t = p["target"]
        print("%2d [%s] %s" % (i, p["lang"], " | ".join(p["says"])[:96]))
        print("     -> ключ=%-14s предмет=%-14r чипы=%-34s отменено=%s"
              % (t["key"], t["subject"], t["chips"], t["dropped"]))


if __name__ == "__main__":
    main()
