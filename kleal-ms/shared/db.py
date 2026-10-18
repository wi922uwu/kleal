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
--
-- КЛЮЧ — ID ЧЕЛОВЕКА, А НЕ ИМЯ (с 26.09.2026). До этого первичным ключом был name_key, и база
-- физически не могла держать двух тёзок: второй «Иван» при регистрации делал upsert по имени и
-- молча затирал анкету первого, а все его интенты, планы и переписка становились общими. Имя —
-- подпись, она не уникальна и может меняться; личность — `id` строки. См. docs/IDENTITY.md.
-- name_key остался обычным индексом: по нему ищут человека по подписи (поиск, админка).
create table if not exists users (
    id         text primary key,
    name_key   text not null,
    name       text not null,
    row        jsonb not null,
    updated    timestamptz not null default now()
);
create index if not exists users_updated_idx on users (updated desc);
create index if not exists users_name_key_idx on users (name_key);

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
        for k, v in list(session.items()):      # снимок ключей: словарь могут дополнить на ходу
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


# ---------------------------------------------------------------- одна строка хранилища
# `load_store`/`save_store` работают ВСЕМ состоянием сразу: первый читает всё одним запросом на
# старте сервиса, второй принимает целый словарь и сверяет хэши, чтобы писать только изменившееся.
# Для настроек это не годится — их читает и пишет один ключ, часто и из другого процесса, а
# проталкивание его через save_store испортило бы учёт «грязных» ключей. Отсюда отдельная пара.

def kv_get(key):
    """Значение одного ключа или None. Без базы — None: зовущий обязан иметь значение по умолчанию."""
    if not ENABLED:
        return None
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute("select value from store_kv where key = %s", (key,))
        row = cur.fetchone()
    STATS["reads"] += 1
    return row[0] if row else None


def kv_set(key, value):
    """Записать один ключ. Хэш обновляем следом: иначе save_store решит, что ключ «грязный»,
    и перезапишет наше значение своей копией из памяти процесса."""
    if not ENABLED:
        raise RuntimeError("kv_set: база выключена (KLEAL_DB=%s)" % MODE)
    payload = json.dumps(value, ensure_ascii=False, default=str)
    with _connect().connection() as c:
        with c.cursor() as cur:
            cur.execute(
                "insert into store_kv (key, value, updated) values (%s, %s, now()) "
                "on conflict (key) do update set value = excluded.value, updated = now()",
                (key, payload))
        c.commit()
    with _HASH_LOCK:
        _HASHES[key] = _digest(value)
    STATS["writes"] += 1
    STATS["keys_written"] += 1
    return True


def kv_updated(key):
    """Когда ключ менялся в последний раз (epoch) — для «изменено N часов назад»."""
    if not ENABLED:
        return 0.0
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute("select extract(epoch from updated) from store_kv where key = %s", (key,))
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


# ---------------------------------------------------------------- люди
# ЛИЧНОСТЬ — ЭТО ID СТРОКИ, А НЕ ИМЯ. Все функции ниже пишут и удаляют людей ТОЛЬКО по `id`.
# Имя в строке — подпись: у двух людей она может совпасть, и это нормально.
#
# ПЕРЕХОДНЫЙ РЕЖИМ. Таблица, созданная до 26.09.2026, имеет первичный ключ по имени; её
# переводит `migrate_users_to_id()` (tools/migrate_users_to_id.py). Код ниже сам узнаёт, какая
# схема перед ним, поэтому его можно выложить и до миграции, и после — ничего не упадёт. В старой
# схеме он ведёт себя по-старому; в новой — только по id.
def _name_key(name):
    return " ".join(str(name or "").lower().split())


_KEYMODE = {"mode": None, "t": 0.0}


def users_keymode(force=False):
    """'id' — первичный ключ таблицы users по id (правильно); 'name' — старая схема по имени."""
    now = time.time()
    if not force and _KEYMODE["mode"] and now - _KEYMODE["t"] < 300:
        return _KEYMODE["mode"]
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute(
            "select a.attname from pg_index i join pg_attribute a "
            "on a.attrelid = i.indrelid and a.attnum = any(i.indkey) "
            "where i.indrelid = 'users'::regclass and i.indisprimary")
        cols = [r[0] for r in cur.fetchall()]
    mode = "id" if cols == ["id"] else "name"
    _KEYMODE.update(mode=mode, t=now)
    return mode


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


def _upsert_user(cur, row, mode):
    nm = str((row or {}).get("name") or "").strip()
    if not nm:
        return False
    body = json.dumps(row, ensure_ascii=False, default=str)
    if mode == "id":
        uid = str((row or {}).get("id") or "").strip()
        if not uid:
            # Строка без id — это человек без личности. Писать её по имени значило бы вернуть
            # ровно ту ошибку, от которой уходим: тёзка затёр бы тёзку.
            raise ValueError("users: у строки нет id (личность человека — только id)")
        cur.execute(
            "insert into users (id, name_key, name, row, updated) values (%s, %s, %s, %s, now()) "
            "on conflict (id) do update set name_key = excluded.name_key, name = excluded.name, "
            "row = excluded.row, updated = now()",
            (uid, _name_key(nm), nm, body))
    else:
        cur.execute(
            "insert into users (name_key, name, row, updated) values (%s, %s, %s, now()) "
            "on conflict (name_key) do update set name = excluded.name, "
            "row = excluded.row, updated = now()",
            (_name_key(nm), nm, body))
    return True


def save_user(row):
    """Записать ОДНОГО человека — по его id. Регистрация больше не трогает остальных."""
    if not ENABLED:
        return False
    for attempt in (0, 1):
        mode = users_keymode(force=bool(attempt))
        try:
            with _connect().connection() as c:
                with c.cursor() as cur:
                    ok = _upsert_user(cur, row, mode)
                c.commit()
            break
        except ValueError:
            raise
        except Exception:
            if attempt:
                raise
            # Схема могла смениться между проверкой и записью (миграция) — узнаём заново и
            # повторяем один раз.
    STATS["writes"] += 1
    return bool(ok)


def save_users(rows):
    """Записать ПАЧКУ людей — для посева и переноса. Одной транзакцией: половина популяции
    в базе хуже, чем ни одной, потому что выглядит как рабочая."""
    if not ENABLED:
        return 0
    mode = users_keymode(force=True)
    n = 0
    with _connect().connection() as c:
        with c.cursor() as cur:
            for row in rows or []:
                if _upsert_user(cur, row, mode):
                    n += 1
        c.commit()
    STATS["writes"] += 1
    STATS["keys_written"] += n
    return n


def delete_user(uid=None, name=None):
    """Удалить ОДНОГО человека — по id. Удаление по имени стирало заодно всех его тёзок, поэтому
    в новой схеме имя без id не принимается вовсе."""
    if not ENABLED:
        return False
    mode = users_keymode(force=True)
    with _connect().connection() as c:
        with c.cursor() as cur:
            if mode == "id":
                if not str(uid or "").strip():
                    raise ValueError("delete_user: нужен id — по имени удалять нельзя")
                import monetization_admin
                monetization_admin.begin_delete(c,str(uid).strip())
                cur.execute("delete from users where id = %s", (str(uid).strip(),))
            else:
                if uid:
                    cur.execute("delete from users where row->>'id' = %s", (str(uid).strip(),))
                else:
                    cur.execute("delete from users where name_key = %s", (_name_key(name),))
        c.commit()
    return True


def migrate_users_to_id(apply=False):
    """Перевести таблицу users с ключа по имени на ключ по id. Одна транзакция, идемпотентно.

    Строкам без id выдаётся устойчивый `nm` + md5(name_key)[:12] и он же вписывается в саму строку.
    Если id повторяется — ОТКАЗ без изменений: склеивать двух людей молча нельзя.
    Возвращает отчёт; при apply=False ничего не меняет.
    """
    if not ENABLED:
        return {"ok": False, "error": "db disabled"}
    rep = {"mode_before": users_keymode(force=True)}
    with _connect().connection() as c:
        with c.cursor() as cur:
            cur.execute("lock table users in exclusive mode")
            cur.execute("select count(*) from users")
            rep["rows"] = cur.fetchone()[0]
            cur.execute("alter table users add column if not exists id text")
            cur.execute("update users set id = nullif(row->>'id', '') where id is null")
            cur.execute("select count(*) from users where id is null")
            rep["without_id"] = cur.fetchone()[0]
            cur.execute("update users set id = 'nm' || substr(md5(name_key), 1, 12) where id is null")
            cur.execute("update users set row = jsonb_set(row, '{id}', to_jsonb(id)) "
                        "where coalesce(row->>'id', '') <> id")
            cur.execute("select id, count(*) from users group by id having count(*) > 1")
            dups = cur.fetchall()
            rep["dup_ids"] = [[d[0], d[1]] for d in dups]
            if dups or not apply:
                c.rollback()
                rep["ok"] = not dups
                rep["applied"] = False
                return rep
            if rep["mode_before"] != "id":
                cur.execute("alter table users drop constraint if exists users_pkey")
                cur.execute("alter table users add constraint users_pkey primary key (id)")
            cur.execute("alter table users alter column name_key set not null")
            cur.execute("create index if not exists users_name_key_idx on users (name_key)")
        c.commit()
    rep["mode_after"] = users_keymode(force=True)
    rep["ok"] = rep["mode_after"] == "id"
    rep["applied"] = True
    return rep


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
            # Matching consumes this local durable job itself, without RabbitMQ.
            "where sent_at is null and next_try <= now() and topic not in ('monetization.search.launch','monetization.media.cleanup') "
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


def outbox_prune(keep_days=7, batch=20000):
    """Удалить ОТПРАВЛЕННЫЕ задания старше `keep_days` (18.10.2026). Неотправленные не трогаются.

    Отправленные строки после `sent_at` никто не читает — только счёт в outbox_stats. Чистки не было
    вовсе, и к 18.10 таблица держала 2,78 млн отправленных строк (572 МБ из 587 МБ базы). Порциями,
    чтобы не держать таблицу одной долгой транзакцией. Возвращает, сколько удалено."""
    if not ENABLED:
        return 0
    gone = 0
    with _connect().connection() as c:
        while True:
            with c.cursor() as cur:
                cur.execute(
                    "delete from outbox where id in (select id from outbox where sent_at is not null "
                    "and sent_at < now() - make_interval(days => %s) limit %s)", (int(keep_days), int(batch)))
                n = cur.rowcount or 0
            c.commit()
            gone += n
            if n < batch:
                return gone


def outbox_stats():
    if not ENABLED:
        return {}
    with _connect().connection() as c, c.cursor() as cur:
        cur.execute("select count(*) filter (where sent_at is null), "
                    "count(*) filter (where sent_at is null and attempts >= 5), count(*) from outbox")
        pending, stuck, total = cur.fetchone()
        return {"pending": pending, "stuck": stuck, "total": total}
