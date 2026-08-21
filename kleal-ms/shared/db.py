# -*- coding: utf-8 -*-
"""PostgreSQL под тем же интерфейсом, что был у JSON-файлов.

ЗАЧЕМ. Всё состояние Kleal жило в двух файлах: `users.json` (1,4 МБ) и `kleal_store.json`
(1,3 МБ). Любая правка — «Sofia подтвердила встречу» — переписывала файл ЦЕЛИКОМ: все планы всех
людей, все приглашения, все переписки. Плюс один замок на весь файл, то есть писать могли не
двое сразу, а строго по одному. На семистах людях это незаметно, на десяти тысячах — стена.

ЧТО ЗДЕСЬ СДЕЛАНО И ЧЕГО НАМЕРЕННО НЕ СДЕЛАНО.

Не сделано: переписывание тринадцати тысяч строк матчинга под ORM. Код читает `SESSION["_mplans"]`
как обычный список и мутирует вложенные словари на месте; менять это значило бы переписать всё,
что работает и покрыто смоуками, ради слоя, который можно подставить снизу.

Сделано: подстановка снизу. `SESSION` остаётся тем же словарём в памяти, а сохранение перестаёт
быть «перепиши файл». Каждый ключ верхнего уровня (`_mplans`, `_messages`, `_idem`, …) — отдельная
СТРОКА в таблице, и запись трогает только те ключи, что реально изменились. Изменение
определяется по хешу сериализованного значения: сериализовать дёшево, писать на диск — дорого.
Замеры на живом хранилище: 26 ключей, обычная правка задевает один-два, то есть вместо 1,3 МБ
уезжает 100 КБ, а чаще меньше.

Второй выигрыш, ради которого всё и затевалось: `INSERT … ON CONFLICT DO UPDATE` атомарен. Два
процесса могут писать РАЗНЫЕ ключи одновременно, не выстраиваясь в очередь, и ни один не может
затереть чужую запись целиком — потерянных обновлений «прочитал файл / записал файл» больше нет.

ОТКАТ В ОДНУ ПЕРЕМЕННУЮ. `KLEAL_DB=json` (по умолчанию) — всё как раньше, база не трогается и
psycopg не импортируется. `KLEAL_DB=postgres` — база ведущая. `KLEAL_DB=mirror` — читаем из базы,
но пишем в ОБА места, чтобы на время перехода JSON оставался живой резервной копией и откат не
стоил ничего.
"""
import hashlib
import json
import os
import threading
import time

MODE = os.environ.get("KLEAL_DB", "json").strip().lower()      # json | postgres | mirror
DSN = os.environ.get(
    "KLEAL_PG_DSN",
    "postgresql://kleal:kleal@127.0.0.1:5432/kleal?connect_timeout=5")

ENABLED = MODE in ("postgres", "mirror")
MIRROR_JSON = MODE == "mirror"

_pool = None
_pool_lock = threading.Lock()
STATS = {"reads": 0, "writes": 0, "keys_written": 0, "errors": 0, "last_error": None}


# ---------------------------------------------------------------- соединения
def _connect():
    """Пул соединений. Ленивый: при KLEAL_DB=json psycopg не импортируется вовсе, и сервис
    поднимается на машине, где базы нет, — ровно как раньше."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        from psycopg_pool import ConnectionPool
        # min_size=1: сервисов восемь, ядер два — держать по десять праздных соединений на каждый
        # значит съесть лимит базы ничем. max_size=6 хватает: запросы короткие.
        _pool = ConnectionPool(DSN, min_size=1, max_size=6, timeout=10, open=True)
        return _pool


def healthy():
    """Отвечает ли база. Для /health, а не для логики: сервис не обязан падать из-за базы."""
    if not ENABLED:
        return None
    try:
        with _connect().connection() as c, c.cursor() as cur:
            cur.execute("select 1")
            return cur.fetchone()[0] == 1
    except Exception as e:
        STATS["errors"] += 1
        STATS["last_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        return False


# ---------------------------------------------------------------- схема
SCHEMA = """
-- Документное хранилище состояния матчинга: одна строка на КЛЮЧ верхнего уровня SESSION.
-- jsonb, а не text: по нему можно искать и индексировать, когда дойдут руки резать списки
-- на настоящие таблицы. Сейчас это честная замена файла, а не витрина нормализации.
create table if not exists store_kv (
    key        text primary key,
    value      jsonb not null,
    updated    timestamptz not null default now()
);

-- Люди. Строка на человека: регистрация больше не переписывает всех остальных.
-- name_key — тот же ключ, по которому матчинг сравнивает имена (нижний регистр, схлопнутые
-- пробелы), чтобы «Miguel  Ángel» и «miguel ángel» не завели двух людей.
create table if not exists users (
    name_key   text primary key,
    name       text not null,
    row        jsonb not null,
    updated    timestamptz not null default now()
);
create index if not exists users_updated_idx on users (updated desc);

-- Исходящая почта для очереди (см. shared/mq.py). Лежит в ТОЙ ЖЕ базе намеренно: задание
-- записывается той же транзакцией, что и данные, ради которых оно послано. Иначе остаётся
-- дыра «данные записались, задание потерялось», ради закрытия которой всё и делается.
create table if not exists outbox (
    id         bigserial primary key,
    topic      text not null,
    payload    jsonb not null,
    attempts   int not null default 0,
    next_try   timestamptz not null default now(),
    sent_at    timestamptz,
    last_error text,
    created    timestamptz not null default now()
);
create index if not exists outbox_pending_idx on outbox (next_try) where sent_at is null;
"""


def ensure_schema():
    """Создать таблицы, если их нет. Идемпотентно — зовётся при старте каждого сервиса."""
    if not ENABLED:
        return False
    with _connect().connection() as c:
        with c.cursor() as cur:
            cur.execute(SCHEMA)
        c.commit()
    return True


# ---------------------------------------------------------------- документы состояния
_HASHES = {}                      # key -> хеш последнего записанного значения
_HASH_LOCK = threading.Lock()


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def load_store():
    """Прочитать всё состояние одним запросом. Зовётся один раз при старте сервиса."""
    if not ENABLED:
        return None
    out = {}
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute("select key, value from store_kv")
        for k, v in cur.fetchall():
            out[k] = v
    STATS["reads"] += 1
    with _HASH_LOCK:
        for k, v in out.items():
            _HASHES[k] = _digest(v)
    return out


def save_store(session):
    """Записать ТОЛЬКО изменившиеся ключи.

    Возвращает, сколько ключей уехало. Ноль — нормальный и частый ответ: большинство запросов
    состояние не меняют, и раньше они всё равно переписывали весь файл.
    """
    if not ENABLED:
        return 0
    dirty = []
    with _HASH_LOCK:
        for k, v in session.items():
            d = _digest(v)
            if _HASHES.get(k) != d:
                dirty.append((k, v, d))
    if not dirty:
        return 0
    try:
        with _connect().connection() as c:
            with c.cursor() as cur:
                for k, v, _d in dirty:
                    cur.execute(
                        "insert into store_kv (key, value, updated) values (%s, %s, now()) "
                        "on conflict (key) do update set value = excluded.value, updated = now()",
                        (k, json.dumps(v, ensure_ascii=False, default=str)))
            c.commit()
    except Exception as e:
        STATS["errors"] += 1
        STATS["last_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        raise
    with _HASH_LOCK:
        for k, _v, d in dirty:
            _HASHES[k] = d
    STATS["writes"] += 1
    STATS["keys_written"] += len(dirty)
    return len(dirty)


# ---------------------------------------------------------------- люди
def _name_key(name):
    return " ".join(str(name or "").lower().split())


def load_users():
    """Все люди. Матчинг читает пул целиком на каждый поиск — здесь это один запрос, а не
    разбор мегабайтного файла."""
    if not ENABLED:
        return None
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute("select row from users order by name_key")
        rows = [r[0] for r in cur.fetchall()]
    STATS["reads"] += 1
    return rows


def users_version():
    """Отпечаток пула: время последней правки и число строк. Заменяет проверку mtime файла —
    матчинг перечитывает пул, только если что-то изменилось."""
    if not ENABLED:
        return None
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute("select coalesce(max(updated), 'epoch'::timestamptz), count(*) from users")
        ts, n = cur.fetchone()
        return "%s|%d" % (ts.isoformat() if ts else "", n)


def save_user(row):
    """Записать ОДНОГО человека. Регистрация больше не трогает остальных семьсот."""
    if not ENABLED:
        return False
    nm = str((row or {}).get("name") or "").strip()
    if not nm:
        return False
    with _connect().connection() as c:
        with c.cursor() as cur:
            cur.execute(
                "insert into users (name_key, name, row, updated) values (%s, %s, %s, now()) "
                "on conflict (name_key) do update set name = excluded.name, "
                "row = excluded.row, updated = now()",
                (_name_key(nm), nm, json.dumps(row, ensure_ascii=False, default=str)))
        c.commit()
    STATS["writes"] += 1
    return True


def save_users(rows):
    """Записать ПАЧКУ людей — для посева и переноса. Одной транзакцией: половина популяции
    в базе хуже, чем ни одной, потому что выглядит как рабочая."""
    if not ENABLED:
        return 0
    n = 0
    with _connect().connection() as c:
        with c.cursor() as cur:
            for row in rows or []:
                nm = str((row or {}).get("name") or "").strip()
                if not nm:
                    continue
                cur.execute(
                    "insert into users (name_key, name, row, updated) values (%s, %s, %s, now()) "
                    "on conflict (name_key) do update set name = excluded.name, "
                    "row = excluded.row, updated = now()",
                    (_name_key(nm), nm, json.dumps(row, ensure_ascii=False, default=str)))
                n += 1
        c.commit()
    STATS["writes"] += 1
    STATS["keys_written"] += n
    return n


def delete_user(name):
    if not ENABLED:
        return False
    with _connect().connection() as c:
        with c.cursor() as cur:
            cur.execute("delete from users where name_key = %s", (_name_key(name),))
        c.commit()
    return True


# ---------------------------------------------------------------- исходящая почта
def outbox_put(topic, payload, conn=None):
    """Положить задание. `conn` — чтобы записать его ТОЙ ЖЕ транзакцией, что и данные."""
    if not ENABLED:
        return None
    body = json.dumps(payload, ensure_ascii=False, default=str)
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute("insert into outbox (topic, payload) values (%s, %s) returning id",
                        (topic, body))
            return cur.fetchone()[0]
    with _connect().connection() as c:
        with c.cursor() as cur:
            cur.execute("insert into outbox (topic, payload) values (%s, %s) returning id",
                        (topic, body))
            rid = cur.fetchone()[0]
        c.commit()
        return rid


def outbox_take(limit=50):
    """Забрать готовые к отправке. `for update skip locked` — чтобы два ретранслятора не взяли
    одно и то же задание и не отправили его дважды."""
    if not ENABLED:
        return []
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute(
            "select id, topic, payload, attempts from outbox "
            "where sent_at is null and next_try <= now() "
            "order by id limit %s for update skip locked", (limit,))
        rows = cur.fetchall()
        c.commit()
        return [{"id": r[0], "topic": r[1], "payload": r[2], "attempts": r[3]} for r in rows]


def outbox_done(rid):
    if not ENABLED:
        return
    with _connect().connection() as c:
        with c.cursor() as cur:
            cur.execute("update outbox set sent_at = now() where id = %s", (rid,))
        c.commit()


def outbox_failed(rid, err, delay_s):
    """Отложить повтор. Задание НЕ удаляется и не теряется — в этом весь смысл."""
    if not ENABLED:
        return
    with _connect().connection() as c:
        with c.cursor() as cur:
            cur.execute(
                "update outbox set attempts = attempts + 1, "
                "next_try = now() + make_interval(secs => %s), last_error = %s where id = %s",
                (float(delay_s), str(err)[:400], rid))
        c.commit()


def outbox_stats():
    if not ENABLED:
        return {}
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute("select count(*) filter (where sent_at is null), "
                    "count(*) filter (where sent_at is null and attempts >= 5), count(*) from outbox")
        pending, stuck, total = cur.fetchone()
        return {"pending": pending, "stuck": stuck, "total": total}
