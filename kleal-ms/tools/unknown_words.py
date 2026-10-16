# -*- coding: utf-8 -*-
"""ЧТО ЛЮДИ ГОВОРЯТ, А У НАС НЕТ — сводка журнала «[v2-слово]» Буди V2.

ЗАЧЕМ. Словарь интересов не угадать заранее (24.09.2026, владелец: «ты не можешь понять, какие ключи
будут использовать люди»). V2 оставляет чипом слово человека, если ключа нет, и пишет его в журнал
вместе с тремя ближайшими ключами по смыслу (bge-m3). Здесь это собирается в список по частоте:
что добавить синонимом к существующему ключу (tools/add_keys.py "слово->ключ" --apply), а что —
новым ключом (решение владельца: это ещё и пузырь на карте и перезапуск поиска).

python3 tools/unknown_words.py [дней=7] [--min N]
"""
import collections, json, subprocess, sys

дней = next((int(a) for a in sys.argv[1:] if a.isdigit()), 7)
мин = int(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 1
лог = subprocess.run(["journalctl", "-u", "kleal@buddy", "--since", "%d days ago" % дней, "--no-pager", "-o", "cat"],
                     capture_output=True, text=True).stdout
счёт, язык, подсказки = collections.Counter(), collections.defaultdict(collections.Counter), {}
for строка in лог.splitlines():
    i = строка.find("[v2-слово] ")
    if i < 0:
        continue
    try:
        z = json.loads(строка[i + len("[v2-слово] "):])
    except Exception:
        continue
    w = str(z.get("w") or "").strip()
    if not w:
        continue
    счёт[w] += 1
    язык[w][z.get("lang") or "?"] += 1
    подсказки[w] = z.get("top") or []
print("непонятых слов за %d дн.: %d разных, %d раз" % (дней, len(счёт), sum(счёт.values())))
print("%5s  %-26s %-8s %s" % ("раз", "слово", "язык", "ближе всего по смыслу"))
for w, n in счёт.most_common():
    if n < мин:
        break
    print("%5d  %-26s %-8s %s" % (n, w, ",".join(язык[w]), "; ".join("%s %.2f" % (k, v) for k, v in подсказки[w])))
