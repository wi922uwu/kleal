# -*- coding: utf-8 -*-
"""Интересы: английский ключ в хранилище, подписи на языках интерфейса — в общем словаре.

ЗАЧЕМ. Интересы писались на языке ввода: «подлёдная рыбалка», «cata de café», «craft beer» — и
подбор был МЕЖЪЯЗЫКОВЫМ со всеми последствиями: мост тем, догадки канона по префиксам, дописанные
машиной ручки (market/design/exchange), которые трижды чистили миграциями. Теперь хранится ОДНА
английская форма — ключ, — а показ на русском и испанском живёт здесь, в словаре, общем на всю
популяцию: «craft beer» у семнадцати человек переводится один раз, а не семнадцать.

СЛОВАРЬ, А НЕ ПОЛЕ ПРОФИЛЯ. Форма `interests` не меняется — плоский список строк, только всегда
английских. Всё, что читает это поле (матчинг, админка, миграции, сторожа), продолжает работать
без правок. Тот же приём, что у phrase_topics.json: одна выученная запись на фразу.

СВОЁ СЛОВО НЕ ЗАТИРАЕТСЯ. Когда человек написал «рыбачить на море», ключом становится перевод
(«sea fishing»), а подписью для ЕГО языка — его собственная формулировка. Существующая подпись
никогда не перезаписывается сгенерированной: первая формулировка — почти всегда человеческая,
и лучше неё модель не скажет.

ТРИ ИСТОЧНИКА ПЕРЕВОДА, ПО УБЫВАНИЮ ДЕШЕВИЗНЫ:
  1. сам словарь (обратный поиск: известная подпись -> ключ);
  2. канон таксономии — 458 узлов с полными ru/en/es, но ТОЛЬКО при дословном совпадении с
     именем узла: алиас «подлёдная рыбалка» резолвится в узел «рыбалка», и взять перевод узла
     значило бы потерять «подлёдная» — специфичность дороже бесплатного перевода;
  3. модель (передаётся вызывающим как translate-функция; сюда сеть не встроена намеренно —
     миграция зовёт модель напрямую, онбординг через llm-service, а матчингу перевод не нужен).
"""
import json
import os
import re
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
PATH = os.environ.get("KLEAL_INTEREST_I18N", os.path.join(_ROOT, "interest_i18n.json"))

_LOCK = threading.Lock()
_CACHE = {"mtime": None, "data": {}, "rev": {}}
_CYR = re.compile(r"[а-яё]", re.I)
_ES_HINT = re.compile(r"[áéíóúñü¿¡]", re.I)
_LATINISH = re.compile(r"^[a-z0-9][a-z0-9 \-'&+/.]*$", re.I)


# ПРОМПТ ПЕРЕВОДА — ОДИН НА ВСЕХ. Онбординг переводит по одному слову в правке профиля, миграция —
# батчами по всей популяции; разойдись эти два текста, и один и тот же интерес получил бы разные
# ключи в зависимости от того, каким путём попал в базу.
#
# Два правила добавлены по итогам первого прогона на живых данных:
#   * ИМЕНА СОБСТВЕННЫЕ. «тарков по ночам» стал «night tarot» — модель приняла Escape from Tarkov
#     за карты таро. Ключ уходит в подбор, и человек начинает искать гадалок.
#   * НЕ ВЫДУМЫВАТЬ ИНТЕРЕС. «жду ноября» и «тепло, когда некому позвонить в воскресенье» — это
#     не увлечения, а строки о себе. Пустой ответ честнее: слово останется как написано, подбор по
#     нему всё равно бессмысленен, а выдуманный ключ ещё и уводит к чужим людям.
TRANSLATE_PROMPT = (
    "You translate personal interests for a social app. Input: one interest per line. "
    "Return a JSON array only — one object per input line, same order and count, no extra text.\n"
    "Each object: {\"en\",\"ru\",\"es\"} — a short natural interest phrase, max 4 words, in each language.\n"
    "RULES:\n"
    "1. Keep the SPECIFIC meaning: 'sea fishing', not 'fishing'.\n"
    "2. Proper nouns stay proper nouns: game titles, brands, places, bands. "
    "'тарков' is the game Escape from Tarkov -> 'escape from tarkov', never 'tarot'. "
    "Transliterate to Latin if needed; never translate their literal meaning.\n"
    "3. If a line is NOT an interest — a mood, a complaint, a personal note, a life circumstance "
    "('waiting for november', 'my son started school') — return {\"en\":\"\"} for that line. "
    "Do not invent an interest that is not there.\n"
    "4. If a line mixes a personal story with a real activity, keep the activity only: "
    "'обжариваю кофе дома на сковороде' -> 'home coffee roasting'."
)


def parse_translation(raw, batch):
    """Ответ модели -> список строк {"en","ru","es"} длиной с батч (или []).

    Батч из одного слова модель часто отдаёт голым объектом без массива — принимаем оба вида.
    На этом уже споткнулись: единственное новое слово в правке профиля молча оставалось сырым.
    """
    try:
        rows = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
        if isinstance(rows, list) and len(rows) == len(batch):
            return rows
    except Exception:
        pass
    try:
        one = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        if isinstance(one, dict) and len(batch) == 1:
            return [one]
    except Exception:
        pass
    return []


def _norm(s):
    return " ".join(str(s or "").strip().lower().split())


def lang_of(word):
    """Язык формулировки — только чтобы решить, чьей подписью станет своё слово."""
    w = str(word or "")
    if _CYR.search(w):
        return "ru"
    if _ES_HINT.search(w):
        return "es"
    return "en"


def _load():
    """Словарь с диска, с перечитыванием по mtime: миграция и сервисы живут в разных процессах,
    и сервис обязан увидеть дописанное без рестарта."""
    try:
        m = os.path.getmtime(PATH)
    except OSError:
        _CACHE.update(mtime=None, data={}, rev={})
        return _CACHE["data"]
    if _CACHE["mtime"] == m:
        return _CACHE["data"]
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
    except Exception:
        return _CACHE["data"]            # битый файл не должен ронять чтение — живём на старом
    rev = {}
    for k, v in data.items():
        rev[_norm(k)] = k
        for lng in ("ru", "es"):
            lab = _norm((v or {}).get(lng))
            if lab:
                rev.setdefault(lab, k)
    _CACHE.update(mtime=m, data=data, rev=rev)
    return data


def key_of(word):
    """Известный ключ для слова: само слово-ключ или любая его известная подпись."""
    _load()
    return _CACHE["rev"].get(_norm(word))


def _display(label):
    """Подпись для экрана: с заглавной буквы.

    Регистр приходит от модели как придётся, и в ряду чипов это видно сразу: «Крипта», «Бег» —
    с большой, «йога», «танцы» — с маленькой. Приводим при ЧТЕНИИ, а не при записи: правило
    касается показа, данные переписывать незачем, и правка чинит все уже накопленные подписи
    разом. Слова с внутренними заглавными («iPhone», «UX») не трогаем — там регистр осмысленный.
    """
    t = str(label or "")
    if not t or t[1:2].isupper() or not t[0].islower():
        return t
    return t[0].upper() + t[1:]


def labels_for(words, lang):
    """Подписи для списка слов на языке lang ('ru'|'es'). Возвращает только известные и только
    отличающиеся от ключа — по-английски ключ и есть подпись."""
    if lang not in ("ru", "es"):
        return {}
    data = _load()
    out = {}
    for w in words or ():
        k = key_of(w) or str(w)
        lab = (data.get(k) or {}).get(lang)
        if lab and _norm(lab) != _norm(w):
            out[str(w)] = _display(lab)
    return out


def learn(en, ru=None, es=None):
    """Дописать переводы ключа. Существующая подпись НЕ перезаписывается — см. шапку."""
    k = _norm(en)
    if not k:
        return False
    with _LOCK:
        data = dict(_load())
        row = dict(data.get(k) or {})
        changed = False
        for lng, val in (("ru", ru), ("es", es)):
            v = " ".join(str(val or "").split())
            if v and not row.get(lng) and _norm(v) != k:
                row[lng] = v
                changed = True
        if not changed and k in data:
            return False
        data[k] = row
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0, sort_keys=True)
        os.replace(tmp, PATH)
        _CACHE["mtime"] = None           # перечитать на следующем чтении
    return True


def _canon_faithful(word):
    """Перевод из канона — только при ДОСЛОВНОМ совпадении с именем узла на любом из трёх языков.
    Алиасы не годятся: «подлёдная рыбалка» -> узел «рыбалка» теряет «подлёдная»."""
    try:
        import sys
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        from matching_core.taxonomy import canonical as C
        nid = C.resolve_node(word)
        if not nid:
            return None
        n = C.NODES.get(nid) or {}
        w = _norm(word)
        if w in (_norm(n.get("ru")), _norm(n.get("en")), _norm(n.get("es"))):
            return {"en": _norm(n.get("en")), "ru": n.get("ru"), "es": n.get("es")}
    except Exception:
        pass
    return None


def to_en(words, translate=None):
    """Список формулировок -> список английских ключей; словарь пополняется по дороге.

    `translate(batch) -> [{"en","ru","es"}, ...]` зовётся ОДНИМ вызовом на всё непереводимое
    дёшево; не передан или упал — слово остаётся как есть (не хуже, чем было). Порядок и
    оригинальная капитализация ключей не сохраняются намеренно: ключ — идентификатор, не текст.
    """
    keys, slots = [], {}                 # slots: индекс места -> исходное слово, ждущее перевода
    for w in words or ():
        w = " ".join(str(w or "").split())
        if not w:
            continue
        k = key_of(w)
        if k:
            keys.append(k)
            continue
        c = _canon_faithful(w)
        if c:
            learn(c["en"], ru=(w if lang_of(w) == "ru" else c.get("ru")),
                  es=(w if lang_of(w) == "es" else c.get("es")))
            keys.append(c["en"])
            continue
        if lang_of(w) == "en" and _LATINISH.match(w):
            keys.append(_norm(w))        # уже английское: ключом становится само слово
            continue
        slots[len(keys)] = w
        keys.append(None)                # место под перевод
    if slots and callable(translate):
        idxs = sorted(slots)
        try:
            rows = translate([slots[i] for i in idxs]) or []
        except Exception:
            rows = []
        if len(rows) == len(idxs):
            for i, row in zip(idxs, rows):
                en = _norm((row or {}).get("en"))
                if en:
                    src = lang_of(slots[i])
                    learn(en,
                          ru=(slots[i] if src == "ru" else (row or {}).get("ru")),
                          es=(slots[i] if src == "es" else (row or {}).get("es")))
                    keys[i] = en
    # непереведённое остаётся своим словом; дубли схлопываются с сохранением порядка
    out, seen = [], set()
    for i, k in enumerate(keys):
        if k is None:
            k = _norm(slots[i])
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out
