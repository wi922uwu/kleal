# -*- coding: utf-8 -*-
"""Кто прислал запрос. Один ответ на все сервисы.

ЗАЧЕМ ОБЩИЙ МОДУЛЬ, если сервисы намеренно самодостаточны. Самодостаточность здесь про бизнес-
логику: у каждого сервиса своя предметная область в одном файле. Инфраструктурные помощники давно
общие — `http_util`, `config`, `db`, `mq`, `llm_client`, `kleal_lib` импортируют все. Проверка
личности такой же помощник: скопировать её в шесть файлов значит гарантировать расхождение на
первой же правке срока жизни сессии или формата токена.

ПОЧЕМУ ЭТО ВООБЩЕ ПОНАДОБИЛОСЬ. До 28.08 человек определялся ИМЕНЕМ, которое сам же и присылал в
теле запроса. Проверено живьём: посторонний без токена читал и переписывал чужой профиль, а по
одному публичному адресу выгружалась вся популяция с координатами. Онбординг закрыт, остальные
сервисы — нет: у них `Authorization` уже лежит в заголовках (шлюз его пробрасывает, проверено), но
никто его не читает.

ЧЕТЫРЕ ПРАВИЛА, БЕЗ КОТОРЫХ МОДУЛЬ САМ СТАНЕТ АВАРИЕЙ:

  1. ТОЛЬКО ЧТЕНИЕ accounts.json. Онбординговый `session_owner` при обращении ПИШЕТ файл: чистит
     просроченное и обновляет отметку последнего входа. Второй писатель, работающий по схеме
     «прочитал — изменил — записал», потерял бы чужие сессии, появившиеся между чтением и записью.
     Здесь срок годности проверяется, но просроченная запись НЕ удаляется — это дело онбординга.

  2. КЕШ ПО ВРЕМЕНИ ПРАВКИ. Без него каждый запрос матчинга читал бы файл заново. Так же устроен
     кеш популяции в самом матчинге.

  3. ИМЯ ФАЙЛА НЕ ДОЛЖНО СОВПАСТЬ с модулем внутри services/*: там каталог сервиса стоит в путях
     ПЕРЕД `shared`, и локальный файл затеняет общий. На этом уже обжигались — матчинг месяцами
     грузил устаревшие копии `shared`. `auth.py` брать нельзя, `kleal_auth.py` свободно.

  4. ПУТЬ БЕРЁТСЯ ИЗ config. Собирать его руками значит однажды разойтись с сервисами и читать
     пустой файл, молча отвечая «не авторизован» всем подряд.
"""
import hashlib
import hmac
import json
import os
import time

try:
    import config
    ACCOUNTS_PATH = config.ACCOUNTS
except Exception:                       # pragma: no cover — на случай запуска вне дерева
    ACCOUNTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "accounts.json")

_CACHE = {"mtime": None, "data": {}}
_USERS = {"mtime": None, "data": []}


def _accounts():
    """Аккаунты из файла, перечитываются только при изменении. Ошибка чтения — пустой словарь:
    без аккаунтов никто не опознан, и это безопасный исход, а не падение сервиса."""
    try:
        m = os.path.getmtime(ACCOUNTS_PATH)
    except OSError:
        return {}
    if _CACHE["mtime"] != m:
        try:
            with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _CACHE["data"] = data if isinstance(data, dict) else {}
            _CACHE["mtime"] = m
        except Exception:
            return _CACHE["data"] or {}
    return _CACHE["data"]


def _population():
    """Популяция из файла, перечитывается только при изменении.

    КЕШ ЗДЕСЬ ОБЯЗАТЕЛЕН, а не желателен. Без него `caller_name` читал бы полтора мегабайта на
    КАЖДЫЙ запрос — а звать его будет матчинг, самый нагруженный сервис. Так же устроен его
    собственный кеш популяции: по времени правки файла.
    """
    try:
        import config as _c
        path = _c.USERS
        m = os.path.getmtime(path)
    except Exception:
        return _USERS["data"] or []
    if _USERS["mtime"] != m:
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            rows = raw.get("users") if isinstance(raw, dict) else raw
            _USERS["data"] = rows if isinstance(rows, list) else []
            _USERS["mtime"] = m
        except Exception:
            return _USERS["data"] or []
    return _USERS["data"]


def bearer(handler):
    """Токен из заголовка Authorization. Пусто — заголовка нет или он не Bearer."""
    raw = ""
    try:
        raw = handler.headers.get("Authorization") or ""
    except Exception:
        return ""
    raw = str(raw).strip()
    if raw[:7].lower() != "bearer ":
        return ""
    return raw[7:].strip()


def owner_key(handler):
    """Ключ аккаунта, которому принадлежит сессия запроса. Пусто — не опознан.

    Токен в файле лежит хешем, поэтому сравнивается хеш; сам токен на диск не попадает никогда.
    Просроченные сессии не считаются действующими, но и не удаляются — см. правило 1.
    """
    tok = bearer(handler)
    if not tok:
        return ""
    # Сессии лежат СЛОВАРЁМ ПО ХЕШУ токена — ровно так их кладёт онбординг (`sess[_sha(tok)] = …`).
    # Поэтому здесь прямое обращение по ключу, а не перебор записей: и быстрее, и совпадает с тем,
    # как это читает сам онбординг. Сам токен на диск не попадает никогда.
    h = hashlib.sha256(tok.encode("utf-8")).hexdigest()
    now = int(time.time())
    for key, acc in (_accounts() or {}).items():
        rec = ((acc or {}).get("sessions") or {}).get(h)
        if not isinstance(rec, dict):
            continue
        if int(rec.get("exp") or 0) < now:
            return ""                      # просрочена; удалять её — дело онбординга, см. правило 1
        return key
    return ""


def caller_name(handler, users=None):
    """Имя строки профиля, принадлежащей отправителю запроса. Пусто — нечего показывать.

    Два источника, оба про владельца, а не про то, как человек назвался в запросе:
      1. поле `owner` в самой строке — его пишет регистрация начиная с 28.08;
      2. `name` в записи аккаунта — его пишет привязка анкеты, и он существовал всегда.

    `users` можно передать снаружи: у матчинга популяция уже прочитана и кеширована, второй раз
    читать полтора мегабайта незачем.
    """
    key = owner_key(handler)
    if not key:
        return ""
    rows = users if users is not None else _population()
    for u in rows or []:
        if isinstance(u, dict) and u.get("owner") == key:
            return str(u.get("name") or "")
    attached = str(((_accounts() or {}).get(key) or {}).get("name") or "").strip()
    if not attached:
        return ""
    low = attached.lower()
    for u in rows or []:
        if isinstance(u, dict) and str(u.get("name") or "").strip().lower() == low:
            return str(u.get("name") or "")
    return ""


def admin_ok(handler):
    """Пришёл ли верный административный токен. Сравнение постоянного времени."""
    try:
        got = str(handler.headers.get("X-Admin-Token") or "")
    except Exception:
        return False
    if not got:
        return False
    want = os.environ.get("KLEAL_ADMIN_TOKEN") or ""
    if not want:
        try:
            import config as _c
            base = os.path.dirname(os.path.abspath(_c.ACCOUNTS))
            with open(os.path.join(base, "admin_token.txt"), "r", encoding="utf-8") as f:
                want = f.read().strip()
        except Exception:
            return False
    return bool(want) and hmac.compare_digest(got, want)
