# -*- coding: utf-8 -*-
"""Дописать ключи в общий реестр — рядом с их ближайшим существующим соседом.

ЗАЧЕМ ОТДЕЛЬНЫЙ ИНСТРУМЕНТ. `tools/new_keys.py` спрашивает модель, куда положить слово, и это
правильно для сбора. Но 18.09.2026 модель на «lawn mowing» ответила `outdoors/hiking` — к походам, —
а рядом, в `outdoors/naturelife`, уже лежит `gardening`; финансы она отправила в `learning/academic`,
хотя `investing` и `finance` давно живут в `tech/career`. Владелец сформулировал правило точнее:
магнитить К БЛИЖАЙШЕМУ СУЩЕСТВУЮЩЕМУ КЛЮЧУ. Этот инструмент кладёт слово именно туда, куда сказано,
и не даёт сделать это тихо и неправильно.

ЧТО НЕ ПРОПУСКАЕТ И ПОЧЕМУ:
  уже сводится   слово, которое norm_topic и так понимает. Перекладывать его значит переставлять
                 чужие пары, посчитанные до нас, — ровно то, от чего заведён сторож таксономии.
  чужой узел     узла нет в дереве: слово останется без семьи, то есть незаметно бесполезным.
  короткое       меньше трёх букв склеит что угодно.
  дубль          слово уже лежит в другом узле: два дома у одного слова — это тихий конфликт.

Использование:
    python3 tools/add_keys.py "construction=culture/craft" "lawn mowing=outdoors/naturelife" [--apply]
"""
import io, json, os, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(HERE, "..", "shared", "interests.json")
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "services", "buddy"))


def main():
    args = [a for a in sys.argv[1:] if a != "--apply"]
    apply_it = "--apply" in sys.argv[1:]
    if not args:
        print(__doc__); return 2
    import app as B
    reg = json.load(io.open(REG, encoding="utf-8"))
    tree = reg.get("tree") or {}
    места = {"%s/%s" % (b, s) for b, subs in tree.items() for s in (subs or {})}
    дома = {}
    for b, subs in tree.items():
        for s, ws in (subs or {}).items():
            for w in (ws or []):
                дома[str(w).strip().lower()] = "%s/%s" % (b, s)

    # СИНОНИМ, А НЕ НОВЫЙ КЛЮЧ. В базе всё по-английски, а человек говорит «кальян», «серия»,
    # «выпечка», «exposición». Сделать из них ключи значит развести по разным углам то, что одно и
    # то же: искавший hookah не встретит искавшего кальян. Поверхностная форма обязана вести к
    # английскому ключу, и проверяется это тем, что ключ САМ сводится.
    синонимы, берём, мимо = [], [], []
    for a in list(args):
        if "->" not in a:
            continue
        args.remove(a)
        w, куда = a.split("->", 1)
        w = w.strip().lower(); куда = куда.strip().lower()
        if len(w) < 3:
            мимо.append((w, "короткое")); continue
        if B.norm_topic(w):
            мимо.append((w, "уже сводится в %r" % B.norm_topic(w))); continue
        if not B.norm_topic(куда):
            мимо.append((w, "цель %r сама не сводится" % куда)); continue
        синонимы.append((w, B.norm_topic(куда)))

    for a in args:
        if "=" not in a:
            мимо.append((a, "нет знака =")); continue
        w, куда = a.split("=", 1)
        w = w.strip().lower(); куда = куда.strip()
        if len(w) < 3:
            мимо.append((w, "короткое")); continue
        if куда not in места:
            мимо.append((w, "чужой узел %s" % куда)); continue
        if w in дома:
            мимо.append((w, "уже лежит в %s" % дома[w])); continue
        if B.norm_topic(w):
            мимо.append((w, "уже сводится в %r" % B.norm_topic(w))); continue
        берём.append((w, куда))

    for w, куда in синонимы:
        print("  синоним %-19s -> %s" % (w, куда))
    for w, куда in берём:
        print("  беру   %-20s -> %s" % (w, куда))
    for w, why in мимо:
        print("  мимо   %-20s %s" % (w, why))
    if not берём and not синонимы:
        print("нечего дописывать"); return 1
    if not apply_it:
        print("НИЧЕГО НЕ ИЗМЕНЕНО. Повторить с --apply"); return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    arc = "/root/kleal-archive/add-keys-" + stamp
    os.makedirs(arc, exist_ok=True)
    shutil.copy2(REG, os.path.join(arc, "interests.json"))
    for w, куда in берём:
        b, s = куда.split("/", 1)
        tree[b][s] = list(tree[b][s]) + [w]
    if синонимы:
        reg.setdefault("synonyms", {})
        for w, ключ in синонимы:
            reg["synonyms"][w] = ключ
    слов = sum(len(ws or []) for subs in tree.values() for ws in (subs or {}).values())
    # Сторож целости: матчинг откажется стартовать на обеднённом реестре, и лучше узнать это здесь.
    if len(tree) < 5 or слов < 300 or len(reg.get("synonyms") or {}) < 40:
        print("СТОРОЖ: реестр вышел обеднённым, не пишу"); return 3
    io.open(REG, "w", encoding="utf-8").write(json.dumps(reg, ensure_ascii=False, indent=1))
    print("АРХИВ: %s | ключей %d, синонимов %d, всего слов %d"
          % (arc, len(берём), len(синонимы), слов))
    return 0


if __name__ == "__main__":
    sys.exit(main())
