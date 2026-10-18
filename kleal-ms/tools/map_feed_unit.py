# -*- coding: utf-8 -*-
"""Лента карты и «Онлайна»: порядок, обрезка и прошедшие встречи (17.10.2026).

    python3 tools/map_feed_unit.py

Без сети и без стора: подставные строки в том виде, в каком их пишут intent-save и gintent-create,
через настоящие collect_sources + build_feed. Время зафиксировано (`now`), поэтому тест не зависит
от того, когда его запускают.

ЗАЧЕМ. Лента собиралась «все группы, потом затеи в порядке записи» и резалась на limit=60 без
сортировки: при сотне групп свежая затея на карту не попадала вовсе, а окно затеи писало
«intent is no longer visible». И встречи, чьё время давно прошло, висели на карте вечно.
Проверяется:
  — свежая затея (и со временем, и без) попадает в limit=60 при ста группах — на обоих видах;
  — группы не пропали: в первые 60 попадают самые свежие из них;
  — встреча со временем идёт раньше затей без времени, ближайшая — первой;
  — прошедшая больше чем на 3 часа встреча пропала, идущая сейчас — осталась;
  — пояс автора учитывается; неизвестный пояс не прячет встречу раньше времени;
  — затея без времени (и с кривым dateKey) осталась;
  — группа побеждает свою поисковую копию, даже если копия свежее;
  — want_id держит нужную строку в ответе, но фильтров не обходит;
  — свидания на карту по-прежнему не попадают; пояс автора наружу не едет.

Путь к модулю можно подменить: MAP_FEED_SRC=<папка с intent_map_feed.py> — так тот же тест
гоняется по старой версии и показывает, что он ловит баг.
"""
import datetime
import inspect
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("MAP_FEED_SRC") or os.path.join(HERE, "..", "services", "matching"))
import intent_map_feed as imf

ok = bad = 0


def check(name, cond, extra=""):
    global ok, bad
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        bad += 1
        print("  FAIL %s   %s" % (name, str(extra)[:300]))


UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 17, 12, 0, tzinfo=UTC).timestamp()   # 14:00 Мадрид, 05:00 Лос-Анджелес
DAY = 86400


def day_key(offset_days):
    return (datetime.datetime.fromtimestamp(NOW, UTC) + datetime.timedelta(days=offset_days)).strftime("%Y-%m-%d")


# ── люди ─────────────────────────────────────────────────────────────────────────────────
users = [{"id": "u_me", "name": "Смотрящий", "source": "onboarding", "tz": "Europe/Madrid"}]
for i in range(100):
    users.append({"id": "u_g%d" % i, "name": "Орг%d" % i, "source": "onboarding", "open": True,
                  "country": "Spain", "countryCode": "ES", "tz": "Europe/Madrid"})
for pid, name, tz in (("u_ana", "Ana", "Europe/Madrid"), ("u_bob", "Bob", "America/Los_Angeles"),
                      ("u_nul", "Nul", ""), ("u_bad", "Bad", "Mars/Olympus"), ("u_org", "Org", "Europe/Madrid")):
    users.append({"id": pid, "name": name, "source": "onboarding", "open": True,
                  "country": "Spain", "countryCode": "ES", "tz": tz})

VENUE = {"address": "Plaça Reial, Barcelona", "lat": 41.3801, "lon": 2.1753}

# ── сто групп: гибрид, без времени, созданы от 100 до 1 дня назад ─────────────────────────────
groups = []
for i in range(100):
    groups.append({
        "id": "gi_%03d" % i, "owner": "Орг%d" % i, "owner_id": "u_g%d" % i,
        "title": "Группа %d" % i, "mode": "hybrid", "state": "searching",
        "intent": dict(VENUE, title="Группа %d" % i, topics=["board games"], mode="hybrid", format="group"),
        "members": [{"name": "u_g%d" % i, "state": "joined"}],
        "created": NOW - (100 - i) * DAY, "updated": NOW - (100 - i) * DAY,
    })
# Группа, у которой есть своя поисковая копия (копия свежее группы).
copy_intent = dict(VENUE, title="Настолки у Org", topics=["chess"], mode="offline", format="group")
groups.append({"id": "gi_copy", "owner": "Org", "owner_id": "u_org", "title": "Настолки у Org",
               "mode": "offline", "state": "searching", "intent": dict(copy_intent),
               "members": [{"name": "u_org", "state": "joined"}, {"name": "u_x", "state": "joined"}],
               "created": NOW - 200 * DAY, "updated": NOW - 200 * DAY})


def saved(iid, owner, owner_id, title, created, **intent):
    intent.setdefault("title", title)
    intent.setdefault("topics", ["coffee"])
    return {"id": iid, "owner": owner, "owner_id": owner_id, "title": title, "intent": intent,
            "created": created, "updated": created, "launched": created}


intents = []
# Тридцать старых затей без времени — записаны первыми, как в живом сторе.
for i in range(30):
    intents.append(saved("in_old_%02d" % i, "Ana", "u_ana", "Старая %d" % i, NOW - (300 - i) * DAY,
                         mode="offline", **VENUE))
intents += [
    saved("in_copy", "Org", "u_org", "Настолки у Org", NOW - 5,
          **{k: v for k, v in copy_intent.items() if k != "title"}),
    # Встреча вчера в 20:00 по Мадриду — давно прошла.
    saved("in_past", "Ana", "u_ana", "Вчерашний кофе", NOW - 3 * DAY, mode="hybrid",
          dateKey=day_key(-1), minutes=20 * 60, **VENUE),
    # Сегодня в 12:30 по Мадриду = 10:30 UTC: прошло полтора часа — встреча ещё идёт.
    saved("in_now", "Ana", "u_ana", "Идёт сейчас", NOW - 2 * DAY, mode="offline",
          dateKey=day_key(0), minutes=12 * 60 + 30, **VENUE),
    # Сегодня в 09:30 по Мадриду = 07:30 UTC: прошло 4,5 часа — больше запаса.
    saved("in_late", "Ana", "u_ana", "Утренний кофе", NOW - 2 * DAY, mode="offline",
          dateKey=day_key(0), minutes=9 * 60 + 30, **VENUE),
    # Пояс автора: 03:00 в Лос-Анджелесе = 10:00 UTC — ещё в запасе. Прочитанное как UTC, ушло бы.
    saved("in_la", "Bob", "u_bob", "Ночной звонок", NOW - 2 * DAY, mode="online",
          dateKey=day_key(0), minutes=3 * 60),
    # И в обратную сторону: 01:00 в Лос-Анджелесе = 08:00 UTC — запас вышел в 11:00 UTC. Без пояса
    # (UTC−12) она бы ещё висела, значит, пояс профиля действительно читается.
    saved("in_la_gone", "Bob", "u_bob", "Ранний звонок", NOW - 2 * DAY, mode="online",
          dateKey=day_key(0), minutes=60),
    # Пояс в самой затее важнее профиля: 03:00 по Мадриду = 01:00 UTC — давно прошло.
    saved("in_own_tz", "Bob", "u_bob", "Ночной звонок по Мадриду", NOW - 2 * DAY, mode="online",
          dateKey=day_key(0), minutes=3 * 60, tz="Europe/Madrid"),
    # Пояса нет: 00:30 сегодня не прячется раньше времени (считаем UTC−12).
    saved("in_notz", "Nul", "u_nul", "Без пояса сегодня", NOW - 2 * DAY, mode="offline",
          dateKey=day_key(0), minutes=30, **VENUE),
    # Пояса нет, но встреча позавчера — уходит и так.
    saved("in_notz_old", "Nul", "u_nul", "Без пояса позавчера", NOW - 4 * DAY, mode="offline",
          dateKey=day_key(-2), minutes=20 * 60, **VENUE),
    # Кривой пояс — не роняет ленту; прошлая неделя всё равно прошла.
    saved("in_badtz", "Bad", "u_bad", "Кривой пояс", NOW - 9 * DAY, mode="offline",
          dateKey=day_key(-7), minutes=20 * 60, **VENUE),
    # Без времени вовсе: только строка поиска. Старая — но не трогается.
    saved("in_untimed", "Ana", "u_ana", "Когда-нибудь", NOW - 400 * DAY, mode="offline",
          time="saturday 18:00", when="сб · 18:00", **VENUE),
    # Кривой dateKey — считается «без времени», затея остаётся.
    saved("in_badkey", "Ana", "u_ana", "Кривая дата", NOW - 401 * DAY, mode="offline",
          dateKey="2026-13-45", minutes=600, **VENUE),
    # Свидание — свежее, со временем завтра: на карту не попадает ни по типу, ни по названию.
    saved("in_date_type", "Ana", "u_ana", "Ужин", NOW - 1, mode="hybrid", type="dating",
          dateKey=day_key(1), minutes=20 * 60, **VENUE),
    saved("in_date_title", "Ana", "u_ana", "Сходить на свидание", NOW - 1, mode="hybrid", **VENUE),
    # Черновик (не запущен) — как и раньше, не виден.
    dict(saved("in_draft", "Ana", "u_ana", "Черновик", NOW - 1, mode="offline", **VENUE), launched=None),
    # СВЕЖИЕ — записаны последними, как в живом сторе.
    saved("in_fresh_dated", "Ana", "u_ana", "Кофе завтра", NOW - 120, mode="hybrid",
          dateKey=day_key(1), minutes=20 * 60, **VENUE),
    saved("in_fresh_off", "Ana", "u_ana", "Свежий офлайн", NOW - 60, mode="offline", **VENUE),
    saved("in_fresh_on", "Ana", "u_ana", "Свежий онлайн", NOW - 30, mode="online"),
    # Своя затея смотрящего — себе на карте не показывается.
    saved("in_mine", "Смотрящий", "u_me", "Моя затея", NOW - 1, mode="hybrid", **VENUE),
]

records = imf.collect_sources(users, intents, groups, self_name="Смотрящий", self_id="u_me")


_NEW_API = "now" in inspect.signature(imf.build_feed).parameters


def feed(view, limit=60, now=NOW, **kw):
    if not _NEW_API:                  # прогон по старой версии: ни `now`, ни `want_id` у неё нет
        return imf.build_feed(records, view, limit=limit, geocoder=None, geocode_budget=0)
    return imf.build_feed(records, view, limit=limit, geocoder=None, geocode_budget=0, now=now, **kw)


def ids(f):
    return [str(i.get("id")) for i in f.get("items") or []]


off60, on60 = ids(feed("offline")), ids(feed("online"))
off_all, on_all = ids(feed("offline", 200)), ids(feed("online", 200))

print("-- обрезка на 60 при ста группах --")
check("офлайн: ровно 60", len(off60) == 60, len(off60))
check("онлайн: ровно 60", len(on60) == 60, len(on60))
check("офлайн: свежая затея без времени в первых 60", "in_fresh_off" in off60, off60[-5:])
check("онлайн: свежая онлайн-затея в первых 60", "in_fresh_on" in on60, on60[-5:])
check("оба вида: свежая встреча завтра в первых 60", "in_fresh_dated" in off60 and "in_fresh_dated" in on60)
check("старые затеи без времени срезаны, а не свежие", "in_old_00" not in off60 and "in_old_00" in off_all)

print("\n-- группы не потерялись --")
g_off = [x for x in off60 if x.startswith("gi_")]
check("офлайн: группы в первых 60 есть", len(g_off) >= 50, len(g_off))
check("онлайн: группы в первых 60 есть", len([x for x in on60 if x.startswith("gi_")]) >= 50)
check("в первых 60 — самые свежие группы", "gi_099" in off60 and "gi_000" not in off60)
check("все сто групп — при limit=200", sum(1 for x in off_all if x.startswith("gi_0")) == 100)

print("\n-- порядок --")
dated = [x for x in off_all if x in ("in_now", "in_notz", "in_fresh_dated")]
check("встречи со временем впереди затей без времени",
      off_all.index("in_fresh_dated") < off_all.index("in_fresh_off"), off_all[:6])
check("ближайшие встречи первыми: идёт сейчас → сегодня → завтра",
      dated == ["in_now", "in_notz", "in_fresh_dated"] and off_all[:3] == dated, off_all[:4])
check("без времени — свежие первыми", off_all.index("in_fresh_off") < off_all.index("gi_099") <
      off_all.index("gi_098") < off_all.index("in_old_29"), off_all[:8])

print("\n-- прошедшие встречи --")
check("вчерашняя встреча пропала (оба вида)", "in_past" not in off_all and "in_past" not in on_all)
check("встреча 1,5 ч назад ещё на карте", "in_now" in off60)
check("встреча 4,5 ч назад пропала", "in_late" not in off_all)
check("пояс автора: 03:00 в Лос-Анджелесе ещё идёт", "in_la" in on_all)
check("пояс автора: 01:00 в Лос-Анджелесе уже прошла", "in_la_gone" not in on_all)
check("пояс в самой затее важнее профиля", "in_own_tz" not in on_all)
check("без пояса — не прячется раньше времени", "in_notz" in off_all)
check("без пояса — позавчерашняя всё равно уходит", "in_notz_old" not in off_all)
check("кривой пояс не роняет ленту, прошлая неделя ушла", "in_badtz" not in off_all)
check("через двое суток уходит и завтрашняя",
      "in_fresh_dated" not in ids(feed("offline", 200, now=NOW + 2 * DAY + 4 * 3600)))

print("\n-- без времени не трогаем --")
check("затея без dateKey (только строка time) осталась", "in_untimed" in off_all)
check("затея с кривым dateKey осталась", "in_badkey" in off_all)
check("и через год они на месте", "in_untimed" in ids(feed("offline", 200, now=NOW + 365 * DAY)))

print("\n-- склейка группы с копией --")
check("группа победила свою свежую копию", "gi_copy" in off_all and "in_copy" not in off_all,
      [x for x in off_all if "copy" in x])

print("\n-- want_id --")
w = ids(feed("offline", want_id="gi_000"))
check("want_id: старая группа в ответе при limit=60", "gi_000" in w and len(w) == 60, len(w))
check("want_id: свежие на месте", "in_fresh_off" in w and "in_fresh_dated" in w)
check("want_id: прошедшую встречу не воскрешает", "in_past" not in ids(feed("offline", want_id="in_past")))
check("want_id: свидание не воскрешает", "in_date_type" not in ids(feed("offline", want_id="in_date_type")))
check("want_id: без него ответ прежний", ids(feed("offline", want_id="нет_такого")) == off60)

print("\n-- свидания и приватность --")
for v, all_ids in (("офлайн", off_all), ("онлайн", on_all)):
    check(v + ": свиданий нет", "in_date_type" not in all_ids and "in_date_title" not in all_ids)
check("черновик не виден", "in_draft" not in off_all)
check("своя затея себе не видна", "in_mine" not in off_all and "in_mine" not in on_all)
blob = json.dumps(feed("online", 200)) + json.dumps(feed("offline", 200))
check("пояс автора наружу не едет", "America/Los_Angeles" not in blob and '"tz"' not in blob)
check("created/updated наружу не едут", '"created"' not in blob and '"updated"' not in blob)

print("\nmap_feed_unit: %d ok, %d fail" % (ok, bad))
sys.exit(1 if bad else 0)
