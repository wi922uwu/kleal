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
        st = os.stat(ACCOUNTS_PATH)
        m = (st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size)
    except OSError:
        _CACHE.update(mtime=None, data={})
        return {}
    if _CACHE["mtime"] != m:
        try:
            with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _CACHE["data"] = data if isinstance(data, dict) else {}
            _CACHE["mtime"] = m
        except Exception:
            # Never authenticate from a snapshot which we can no longer read.
            _CACHE.update(mtime=None, data={})
            return {}
    return _CACHE["data"]


_DBPOP = {"ver": None, "t": 0.0, "data": []}


class IdentityStorageUnavailable(RuntimeError):
    """Opt-in strict readers can distinguish an outage from no profile."""


def _population(force=False, *, strict=False):
    """Популяция: из БАЗЫ, когда она ведущая, иначе из файла. Кешируется.

    ИЗ БАЗЫ, А НЕ ИЗ ФАЙЛА (с 26.09.2026). Раньше здесь читался `users.json`, замороженный при
    переходе на Postgres 10.09, — и всех, кто завёлся позже, модуль не находил по владельцу и
    опознавал только по ИМЕНИ. То есть «кто прислал запрос» решала подпись, и тёзки становились
    одним человеком.

    КЕШ ОБЯЗАТЕЛЕН: звать это будет каждый запрос матчинга. Отпечаток базы (время последней правки
    и число строк) проверяется не чаще раза в две секунды; `force` — перечитать сейчас (новая
    регистрация, которой ещё нет в кеше).
    """
    try:
        import db as _db
        if _db.ENABLED:
            now = time.time()
            if force or now - _DBPOP["t"] > 2.0 or not _DBPOP["data"]:
                v = _db.users_version()
                if force or v != _DBPOP["ver"]:
                    rows = _db.load_users()
                    if not isinstance(rows, list):
                        raise ValueError("invalid authoritative population")
                    _DBPOP.update(ver=v, data=rows)
                _DBPOP["t"] = now
            return _DBPOP["data"]
    except Exception:
        # Failed refresh invalidates the old identity snapshot immediately,
        # including the next request inside the two-second cache interval.
        _DBPOP.update(ver=None, t=0.0, data=[])
        if strict:
            raise IdentityStorageUnavailable("identity storage unavailable") from None
        return []
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
        if not isinstance(acc, dict) or acc.get("deleting"):
            continue
        rec = ((acc or {}).get("sessions") or {}).get(h)
        if not isinstance(rec, dict):
            continue
        if int(rec.get("exp") or 0) < now:
            return ""                      # просрочена; удалять её — дело онбординга, см. правило 1
        return key
    return ""


def _norm(s):
    return " ".join(str(s or "").lower().split())


def person_for_account(key, users=None, _retry=True, *, strict_storage=False):
    """Строка человека, которой ВЛАДЕЕТ аккаунт `key`. None — у аккаунта ещё нет анкеты.

    ЛИЧНОСТЬ — ЭТО ID СТРОКИ, А НЕ ИМЯ (docs/IDENTITY.md). Источники, по убыванию надёжности:
      1. поле `owner` в самой строке — его пишет регистрация (с 28.08.2026);
      2. `person_id` в записи аккаунта — его пишет привязка анкеты (с 26.09.2026);
      3. только для старых строк БЕЗ владельца: имя, привязанное к аккаунту, и лишь если такая
         строка ровно одна. Строку, у которой уже есть владелец, по имени не берём никогда —
         иначе тёзка «становится» чужим человеком.
    """
    key = str(key or "").strip()
    if not key:
        return None
    rows = users if users is not None else _population(strict=strict_storage)
    owned = [u for u in rows or [] if isinstance(u, dict) and u.get("owner") == key]
    if owned:
        owned.sort(key=lambda u: str(u.get("updated") or u.get("created") or ""), reverse=True)
        return owned[0]
    acc = (_accounts() or {}).get(key) or {}
    pid = str(acc.get("person_id") or "").strip()
    if pid:
        hit = next((u for u in rows or [] if isinstance(u, dict) and str(u.get("id") or "") == pid), None)
        if hit is not None:
            return hit
    attached = _norm(acc.get("name"))
    if attached:
        legacy = [u for u in rows or [] if isinstance(u, dict) and not u.get("owner")
                  and _norm(u.get("name")) == attached]
        if len(legacy) == 1:
            return legacy[0]
    if _retry and users is None:
        # Только что зарегистрировался — в кеше его ещё нет. Перечитываем один раз.
        return person_for_account(key, _population(force=True, strict=strict_storage), _retry=False)
    return None


def caller_person(handler, users=None, *, strict_storage=False):
    """Строка человека, приславшего запрос (по сессии). None — сессии нет или анкеты нет."""
    return person_for_account(owner_key(handler), users, strict_storage=strict_storage)


def caller_id(handler, users=None):
    """ID человека, приславшего запрос. ЭТО и есть личность; имя — только подпись."""
    p = caller_person(handler, users)
    return str((p or {}).get("id") or "")


def caller_name(handler, users=None, *, strict_storage=False):
    """Подпись человека, приславшего запрос. Для показа и для старых мест, где ключ ещё имя;
    сравнивать людей по ней нельзя — для этого `caller_id`."""
    p = caller_person(handler, users, strict_storage=strict_storage)
    return str((p or {}).get("name") or "")


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
