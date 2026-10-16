# -*- coding: utf-8 -*-
"""Генератор сценариев для батареи: python3 tools/scenario_gen.py [сколько] [язык]

Сценарии пишет НАША нейронка на поде — не потому что так дешевле, а потому что человек, пишущий
сценарии руками, пишет их по своему образу: одинаковой длины, с одинаковыми оборотами. Модель даёт
разброс, которого рукой не добьёшься, а механическая проверка ниже не даёт ей нафантазировать.

Пул лежит в /root/kleal-archive/scenarios.jsonl, дописывается, повторы отсекаются по отпечатку
реплик. Каждая строка:
    {"label", "lang", "hard": 1..3, "says": [...], "expect": [...], "never": [...], "src": "gen"}

ЧТО ПРОВЕРЯЕТСЯ МЕХАНИЧЕСКИ (модели верить нельзя, она выдумывает охотно):
  • от двух до пяти реплик, каждая непустая и короче 120 знаков;
  • язык реплик совпадает с заявленным (кириллица/латиница, испанские приметы);
  • `expect` непуст, каждое слово встречается ХОТЯ БЫ В ОДНОЙ реплике — иначе это ожидание из
    воздуха, и батарея будет ругаться на верную затею;
  • `never` не пересекается с `expect`;
  • отпечаток реплик не повторяет уже лежащее в пуле.
"""
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.request

POOL = "/root/kleal-archive/scenarios.jsonl"
LLM = os.environ.get("KLEAL_LLM_URL", "http://127.0.0.1:17071")
MODEL = os.environ.get("KLEAL_GEN_MODEL", "qwen3_self")
WANT = int(sys.argv[1]) if len(sys.argv) > 1 else 12
ONLY_LANG = sys.argv[2] if len(sys.argv) > 2 else ""

CYR = re.compile(r"[а-яёА-ЯЁ]")
ES_MARK = re.compile(r"(?iu)[ñáéíóú¿¡]|\b(quiero|vamos|gente|juegos|tomar|hablar|salir|tarde|noche)\b")

PROMPT = '''Ты пишешь сценарии для проверки разговорного помощника. Помощник помогает человеку
собрать «затею» — план чем заняться с другими людьми — и должен правильно понять, ЧЕГО человек
хочет в ИТОГЕ разговора.

С КЕМ РАЗГОВАРИВАЕТ ЧЕЛОВЕК. Он пишет ПОМОЩНИКУ, который ищет ему живых людей для встречи.
Помощник — не приятель и не участник затеи: он никуда не идёт сам, он находит того, кто пойдёт.
Поэтому реплики — это ПРОСЬБЫ И РАССКАЗ О СЕБЕ, а не приглашения помощнику: «хочу на пикник»,
«кто тут катается на сапах?», «ищу компанию в горы» — да; «пошли со мной на пикник», «давай
сыграем с тобой», «приходи в семь» — нет, это обращение к самому помощнику.

Одно исключение, и его надо делать НАРОЧНО в каждом пятом разговоре: человек по привычке пишет
помощнику как приятелю — «пошли на пикник», «го в кино». Помощник обязан понять это как ЖЕЛАНИЕ
человека, а не как приглашение себе. Помечай такие сценарии полем "addressed":"agent".

Придумай %d РАЗНЫХ коротких разговоров на языке: %s. Каждый — реплики ТОЛЬКО ЧЕЛОВЕКА, от 2 до 5,
как пишут в мессенджере: коротко, со строчной, иногда с опечаткой или сленгом.

ФОРМА РАЗГОВОРА — поле "shape", и две из трёх форм надо делать НАРОЧНО:
  "plain" — обычный разговор, как описано ниже (три четверти всех).
  "full"  — ОДНА реплика, в которой сказано ВСЁ: занятие, когда и где. «хочу в падель в субботу
            в Грасии», «looking for someone to grab coffee tomorrow morning in Eixample». Таких
            делай каждый пятый: человек, который пишет всё сразу, спрашивать себя не должен.
  "chip"  — человек называет занятие ровно тем словом, каким оно подписано в приложении:
            «настолки», «выпечка», «видеоигры», «сауна», «board games», «videojuegos»,
            «senderismo». Таких делай каждый десятый: люди повторяют то, что видят на экране.

Сложность 1 — человек сразу называет занятие.
Сложность 2 — называет не сразу: сперва настроение, намёк, вопрос, или перечисляет несколько вещей.
Сложность 3 — меняет решение посреди разговора, ставит условие, отказывается от названного раньше.

Разнообразь занятия: спорт, еда и напитки, игры, музыка, кино, книги, учёба, языки, прогулки,
ремёсла, техника, животные, путешествия, вечеринки, тишина. Не повторяй одно и то же занятие.

Верни ТОЛЬКО JSON-массив, без пояснений:
[{"hard":1|2|3,"shape":"plain"|"full"|"chip","addressed":"assistant"|"agent","says":["...","..."],"expect":["корень"],"never":["корень"]}]

expect — один-два КОРНЯ слов (без окончаний), про которые затея обязана быть В ИТОГЕ разговора.
Каждый такой корень ОБЯЗАН встречаться в репликах человека.
never — корни того, что человек отверг или что было промежуточным; пусто, если ничего не отвергал.
'''


# Зовём модель ТОЙ ЖЕ дорогой, что и службы: `shared/llm_client.llm_complete`. Своей копией
# протокола обзаводиться нельзя — у llm-service ручка не openai-совместимая, и прямой запрос к
# /v1/chat/completions отвечает 404. Одна дорога к модели на весь проект.
sys.path.insert(0, "/opt/kleal/kleal-ms/shared")
# Адрес модели живёт в окружении СЛУЖБЫ (`systemctl show kleal@buddy -p Environment`), а не в общем
# /etc/kleal-infra.env, и умолчание клиента (7071) отвечает 502: живая llm-service слушает 17071.
# Ставим до импорта — клиент читает переменную один раз, при загрузке.
os.environ.setdefault("LLM_URL", "http://127.0.0.1:17071")
from llm_client import llm_complete            # noqa: E402
# МОДЕЛЬ — ТОЛЬКО ЖИВАЯ. Общий конфиг называет `llama_self`, ручка /llm/models перечисляет
# `qwen3_30b` и `mistral32` — и все три отвечают 502. Реально отвечает ОДНА: `qwen3_self`.
# Список моделей у службы и список работающих моделей — разные вещи; проверено запросом.
# Сменить: `KLEAL_GEN_MODEL`.


def ask(n, lang):
    return llm_complete(MODEL, [{"role": "user", "content": PROMPT % (
        n, {"ru": "русском", "en": "английском", "es": "испанском"}[lang])}], 0.9, tag="battery.gen")


def parse(raw):
    m = re.search(r"\[.*\]", str(raw or ""), re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []


def lang_ok(says, lang):
    txt = " ".join(says)
    if lang == "ru":
        return bool(CYR.search(txt))
    if CYR.search(txt):
        return False
    return bool(ES_MARK.search(txt)) if lang == "es" else True


def fingerprint(says):
    return hashlib.sha1("|".join(s.strip().lower() for s in says).encode("utf-8")).hexdigest()[:16]


def valid(sc, lang, seen):
    says = [str(x).strip() for x in (sc.get("says") or []) if str(x).strip()]
    exp = [str(x).strip().lower() for x in (sc.get("expect") or []) if str(x).strip()]
    nev = [str(x).strip().lower() for x in (sc.get("never") or []) if str(x).strip()]
    shape = sc.get("shape")
    shape = shape if shape in ("plain", "full", "chip") else ""
    # ФОРМУ ОПРЕДЕЛЯЕМ САМИ, КОГДА МОДЕЛЬ ЕЁ ЗАБЫЛА. В первом же прогоне 13 сценариев из 60
    # отбросилось как «реплик не 2-5»: это были как раз однострочные полные просьбы, а поле `shape`
    # модель не проставила. Форма видна по самому сценарию — одна реплика и есть «full».
    if not shape:
        shape = "full" if len(says) == 1 else "plain"
    # «Полная просьба» — это ОДНА реплика: в ней уже сказано всё, и второй ход означал бы, что
    # чего-то не хватало. Остальные формы по-прежнему 2-5 реплик.
    _lo = 1 if shape == "full" else 2
    if not (_lo <= len(says) <= 5) or any(len(s) > 120 for s in says):
        return None, "реплик не %d-5 или слишком длинные" % _lo
    if not lang_ok(says, lang):
        return None, "язык не тот"
    if not exp or len(exp) > 3:
        return None, "expect пуст или длиннее трёх"
    low = " ".join(says).lower()
    missing = [e for e in exp if e not in low]
    if missing:
        return None, "ожидание из воздуха: %s" % missing
    if set(exp) & set(nev):
        return None, "expect и never пересекаются"
    fp = fingerprint(says)
    if fp in seen:
        return None, "повтор"
    hard = sc.get("hard")
    hard = hard if hard in (1, 2, 3) else 2
    addressed = sc.get("addressed")
    addressed = addressed if addressed in ("assistant", "agent") else "assistant"
    return {"label": "gen-%s-%s" % (lang, fp[:6]), "lang": lang, "hard": hard,
            "says": says, "expect": exp, "never": nev[:3], "src": "gen",
            "addressed": addressed, "shape": shape}, ""


seen = set()
if os.path.exists(POOL):
    for line in open(POOL, encoding="utf-8"):
        try:
            seen.add(fingerprint(json.loads(line)["says"]))
        except Exception:
            pass

langs = [ONLY_LANG] if ONLY_LANG else ["ru", "en", "es"]
added, rejected = 0, {}
with open(POOL, "a", encoding="utf-8") as out:
    for lang in langs:
        try:
            raw = ask(max(4, WANT // len(langs)), lang)
        except Exception as e:
            rejected["нейронка: %s" % str(e)[:40]] = rejected.get("нейронка", 0) + 1
            continue
        for sc in parse(raw):
            good, why = valid(sc if isinstance(sc, dict) else {}, lang, seen)
            if not good:
                rejected[why] = rejected.get(why, 0) + 1
                continue
            seen.add(fingerprint(good["says"]))
            out.write(json.dumps(good, ensure_ascii=False) + "\n")
            added += 1

print("добавлено %d, всего в пуле %d" % (added, len(seen)))
if rejected:
    print("отброшено: %s" % ", ".join("%s×%d" % (k, v) for k, v in sorted(rejected.items(), key=lambda x: -x[1])[:5]))
