"""Банк примеров для сборщика — из СОБСТВЕННЫХ выверенных разговоров.

ЗАЧЕМ. Промпт объясняет правила словами, и модель их держит через раз. Пример держится лучше
правила: батарея каждый круг производит разговоры, про которые механические проверки сказали
«тут всё верно», — их и показываем. Берём только `good`, предпочитая трудные формы (передумал,
полная просьба одной строкой), по три на язык. Файл читает сборщик; пересобирать можно в любой
момент, продукт перезапуска не требует.
"""
import io, json, collections, sys, importlib.util

# Пример должен быть ОБРАЗЦОВЫМ, а не просто без помеченных бед. Первый прогон это показал:
# в банк просились «сходим» и «Пиво» — механические проверки на них не сработали, а учить такому
# нельзя. Берём только те, где предмет сводится к ключу таксономии: это ровно «настоящее занятие».
sys.path.insert(0, "/opt/kleal/kleal-ms")
_sp = importlib.util.spec_from_file_location("b", "/opt/kleal/kleal-ms/services/buddy/app.py")
_B = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(_B)

DATA = "/root/kleal-archive/dataset.jsonl"
OUT = "/root/kleal-archive/exemplars.json"
PER_LANG = 4          # два «передумал» и два «отказался» на язык
PER_LANG_REFUSAL = 2

rows = []
for line in io.open(DATA, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        r = json.loads(line)
    except Exception:
        continue
    if not r.get("good"):
        continue
    it = r.get("intent") or {}
    act = str(it.get("subject") or "").strip()
    says = [s for s in (r.get("says") or []) if str(s).strip()]
    if not act or not says or len(" | ".join(says)) > 110:
        continue
    if not _B.norm_topic(act):
        continue
    # Образец обязан выглядеть образцом: подпись реестра всегда с заглавной, а «study» строчными —
    # это слово человека, проскочившее сквозь проверки. В примерах такому не место.
    if len(act) < 4 or not act[:1].isupper():
        continue
    rows.append(r)

# Трудное вперёд: передумал (hard 3) и однострочная полная просьба.
def rank(r):
    return (0 if r.get("hard") == 3 else 1 if r.get("shape") == "full" else 2, len(" | ".join(r["says"])))


# ОТКАЗ — ОТДЕЛЬНАЯ КВОТА. «Взял отвергнутое» держится на 0,12 и своими примерами не лечится:
# «передумал» и «отказался» — разные вещи. Человек может назвать занятие и тут же отвергнуть
# СОСЕДНЕЕ («хочу падел, но я новичок», «или бег, или кофе — давай кофе»), и затея обязана быть
# про выбранное. В складе таких выверенных пар 250 на 17.09.2026 — берём по две на язык.
def _short(r):
    return len(" | ".join(r["says"]))


# Один и тот же сценарий попадает в склад каждый круг, поэтому дубли отсекаем сразу: без этого
# в банк дважды попало «хочу поиграть в тенис | по вечерам».
pick = collections.defaultdict(list)
_seen = set()
for r in sorted([x for x in rows if x.get("never")], key=_short):
    lang = r.get("lang")
    key = (lang, " | ".join(r["says"]))
    if key in _seen:
        continue
    if len(pick[lang]) < PER_LANG_REFUSAL:
        _seen.add(key)
        pick[lang].append({"lang": lang, "says": r["says"],
                           "activity": str((r.get("intent") or {}).get("subject") or "")})
for r in sorted(rows, key=rank):
    lang = r.get("lang")
    key = (lang, " | ".join(r["says"]))
    if key in _seen:
        continue
    if len(pick[lang]) < PER_LANG:
        _seen.add(key)
        pick[lang].append({"lang": lang, "says": r["says"],
                           "activity": str((r.get("intent") or {}).get("subject") or "")})
out = [x for lang in ("ru", "en", "es") for x in pick.get(lang, [])]
io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
print("годных пар в складе:", len(rows), "| в банк взято:", len(out))
for x in out:
    print("   %-3s %-64s -> %s" % (x["lang"], " | ".join(x["says"])[:64], x["activity"]))
