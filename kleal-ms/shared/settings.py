# -*- coding: utf-8 -*-
"""Живые настройки — то, что раньше было константой в коде, а теперь правится из панели.

ЗАЧЕМ. Каждый промпт продукта был модульной константой Python: чтобы поменять запятую в
BUDDY_PROMPT, надо было править файл на боевом боксе и перезапускать сервис. Температура вообще
не была настройкой — два десятка чисел россыпью по четырём сервисам. Модель выбиралась
переменной окружения, то есть тоже перезапуском. Панель при этом не знала ни об одном из них.

КАК УСТРОЕНО. Одна строка в `store_kv` (`_settings`) — тот же Postgres, что и всё остальное.
Код по-прежнему НЕСЁТ значение по умолчанию и передаёт его сюда: настройка — это поправка к
коду, а не замена ему. Нет базы, нет строки, пустое значение, база упала — возвращается ровно
то, что написано в коде, и продукт работает как работал. Это главное свойство: панель не может
сломать сервис тем, что кто-то стёр поле.

ПОЧЕМУ КЭШ НА НЕСКОЛЬКО СЕКУНД. Промпт читается на каждый запрос к модели, а поход в базу за
ним стоил бы дороже самого разговора. Тот же приём уже проверен на словаре интересов
(shared/interest_i18n.py): читаем редко, применяем сразу — правка доезжает за секунды и БЕЗ
перезапуска сервиса.
"""
import json
import os
import threading
import time

try:
    import db
except Exception:                                    # сервис может импортироваться без базы
    db = None

KEY = "_settings"
CATALOG = "_settings_catalog"
TTL = float(os.environ.get("KLEAL_SETTINGS_TTL", "5"))

_lock = threading.Lock()
_cache = {"at": 0.0, "data": {}}
_seen = {}                                           # имя → что написано в коде этого сервиса
_seen_at = [0.0]


# ------------------------------------------------------------------ чтение
def all():
    """Весь слепок настроек. Пустой словарь — нормальный ответ: значит всё берётся из кода."""
    now = time.time()
    with _lock:
        if now - _cache["at"] < TTL:
            return _cache["data"]
    data = {}
    try:
        if db is not None and getattr(db, "ENABLED", False):
            got = db.kv_get(KEY)
            if isinstance(got, dict):
                data = got
    except Exception:
        data = _cache["data"]                         # база моргнула — живём на прошлом слепке
    with _lock:
        _cache["at"] = now
        _cache["data"] = data
    return data


def _get(section, name):
    d = all().get(section)
    return d.get(name) if isinstance(d, dict) else None


def invalidate():
    """Сбросить кэш — зовётся сразу после записи, чтобы своя же правка была видна немедленно."""
    with _lock:
        _cache["at"] = 0.0


# ------------------------------------------------------------------ каталог
# ПОЧЕМУ КОД САМ СЕБЯ ОПИСЫВАЕТ. Панель обязана показать ВСЕ промпты продукта, но они лежат
# константами внутри четырёх чужих процессов: импортировать их к себе — значит поднять пол-стека
# в админке, а держать список руками — значит однажды забыть новый промпт и не заметить этого.
# Поэтому каждый сервис, читая свой промпт, сообщает, как тот выглядит В КОДЕ. Панель читает
# один ключ и видит полную картину: что есть, что переопределено и чем именно.
def _register(name, default):
    if _seen.get(name) == default:
        return
    _seen[name] = default
    now = time.time()
    if now - _seen_at[0] < 30:                       # не чаще раза в полминуты на процесс
        return
    _seen_at[0] = now
    try:
        if db is None or not getattr(db, "ENABLED", False):
            return
        cat = db.kv_get(CATALOG) or {}
        if not isinstance(cat, dict):
            cat = {}
        changed = False
        for n, text in _seen.items():
            row = cat.get(n) or {}
            if row.get("default") != text:
                cat[n] = {"default": text, "service": n.split(".")[0], "seen": now,
                          "chars": len(text or "")}
                changed = True
        if changed:
            db.kv_set(CATALOG, cat)
    except Exception:
        pass                                         # каталог — удобство, а не условие работы


def flush_catalog():
    """Записать каталог немедленно, не дожидаясь окна троттлинга.

    Нужен ровно в одном месте — при старте сервиса, когда он одним махом объявляет все свои
    инструкции. Без этого в базу уехала бы только первая: остальные попали бы в окно «не чаще
    раза в полминуты», и панель показывала бы один промпт из десяти до первого разговора.
    """
    if not _seen:
        return 0
    try:
        if db is None or not getattr(db, "ENABLED", False):
            return 0
        cat = db.kv_get(CATALOG) or {}
        if not isinstance(cat, dict):
            cat = {}
        changed = False
        for n, text in _seen.items():
            if (cat.get(n) or {}).get("default") != text:
                cat[n] = {"default": text, "service": n.split(".")[0], "seen": time.time(),
                          "chars": len(text or "")}
                changed = True
        if changed:
            db.kv_set(CATALOG, cat)
        _seen_at[0] = time.time()
    except Exception:
        pass
    return len(_seen)


def announce(pairs):
    """Объявить все промпты сервиса разом: [(имя, текст), …]. Зовётся при старте."""
    for name, text in pairs:
        try:
            prompt(name, text)
        except Exception:
            pass
    try:
        flush_catalog()
    except Exception:
        pass


def catalog():
    """Что код умеет: имя промпта → {default, service, chars}. Читает панель."""
    try:
        if db is not None and getattr(db, "ENABLED", False):
            return db.kv_get(CATALOG) or {}
    except Exception:
        pass
    return {}


# ------------------------------------------------------------------ промпты
def prompt(name, default):
    """Текст промпта `name`; `default` — константа из кода и единственная правда при любом сбое.

    Пустая или слишком короткая строка настройкой НЕ считается: стёртое поле в панели не должно
    оставлять агента без инструкции — он начал бы отвечать как попало, и это выглядело бы как
    поломка модели, а не как пустое поле.
    """
    _register(name, default)
    v = _get("prompts", name)
    if isinstance(v, str) and len(v.strip()) >= 20:
        return v
    return default


# ------------------------------------------------------------------ модель
def temperature(tag, default):
    """Температура для места вызова `tag`.

    Три режима, и они не про удобство, а про смысл. `code` — как написано в коде: у каждого
    вызова своя температура, и лестница 0.35 → 0.2 → 0.1 в разговоре существует именно потому,
    что поиск при 0.6 перестаёт быть повторяемым (см. services/buddy/app.py:147). `fixed` —
    одно число на всё, для опытов. `scale` — умножить все на коэффициент, когда надо подкрутить
    продукт целиком, не трогая соотношений между вызовами.
    Точечная правка `by_tag[tag]` сильнее любого режима.
    """
    m = all().get("model") or {}
    try:
        by_tag = m.get("temperature_by_tag") or {}
        if tag and tag in by_tag:
            return max(0.0, min(2.0, float(by_tag[tag])))
        mode = str(m.get("temperature_mode") or "code")
        if mode == "fixed" and m.get("temperature") is not None:
            return max(0.0, min(2.0, float(m["temperature"])))
        if mode == "scale" and m.get("temperature_scale") is not None:
            return max(0.0, min(2.0, float(default) * float(m["temperature_scale"])))
    except Exception:
        pass
    return default


def model_id(default):
    v = (all().get("model") or {}).get("id")
    return v if isinstance(v, str) and v.strip() else default


def number(section, name, default):
    """Число из настроек с проверкой; всё непонятное — обратно к коду."""
    try:
        v = _get(section, name)
        return float(v) if v is not None else default
    except Exception:
        return default


# ------------------------------------------------------------------ запись (панель)
def save(patch, author="admin"):
    """Слить `patch` в настройки. Возвращает новый слепок.

    История ведётся тут же, в той же строке: последние 30 правок с временем и автором. Это не
    полноценный журнал, а то, ради чего он нужен на практике: увидеть, что менялось последним,
    когда продукт вдруг «поглупел», и вернуть как было одной кнопкой.
    """
    if db is None or not getattr(db, "ENABLED", False):
        raise RuntimeError("нет базы: настройки живут в store_kv")
    cur = db.kv_get(KEY) or {}
    if not isinstance(cur, dict):
        cur = {}
    hist = list(cur.get("_history") or [])
    for section, values in (patch or {}).items():
        if section.startswith("_"):
            continue
        if not isinstance(values, dict):
            continue
        box = dict(cur.get(section) or {})
        for k, v in values.items():
            was = box.get(k)
            if v is None:
                box.pop(k, None)                     # None значит «вернуть как в коде»
            else:
                box[k] = v
            hist.append({"t": time.time(), "who": author, "what": section + "." + k,
                         "was": _short(was), "now": _short(v)})
        cur[section] = box
    cur["_history"] = hist[-30:]
    cur["_updated"] = time.time()
    db.kv_set(KEY, cur)
    invalidate()
    return cur


def _short(v):
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s[:120] + ("…" if len(s) > 120 else "")
