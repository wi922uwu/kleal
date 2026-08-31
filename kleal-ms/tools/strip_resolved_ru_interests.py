# -*- coding: utf-8 -*-
"""Убрать сырую нелатинскую формулировку там, где рядом уже лежит её канонический ключ.

ЗАЧЕМ. `_canon_interests` в services/onboarding дописывал английский ключ, но оставлял исходное
слово: человек с «смарт контракты» получал их рядом с `smart contracts`. Ранжирование сравнивает
канонические ключи буквально, поэтому русский двойник не участвует в подборе никогда, а на экране
профиля висит сырой строкой среди английских ручек. Писатель починен; этот скрипт разбирает то,
что успело накопиться.

ЧЕГО СКРИПТ НЕ ДЕЛАЕТ, И ЭТО ГЛАВНОЕ.

  — НЕ ТРОГАЕТ синтетику. Кириллица у `source=seed` и `source=loadtest` заведена НАМЕРЕННО:
    seed_barcelona.py держит русский блок «because a chunk of the real sign-ups arrive in it»,
    gen_test_users.py прямо перечисляет «off-taxonomy and Russian-language interests» среди того,
    что обязан покрывать. Это корпус, на котором проверяют, что матчинг переваривает грязный ввод.
    Вычистить его значит сломать проверку ровно того случая, ради которого он написан.

  — НЕ УДАЛЯЕТ то, чему не нашлось замены. Убираем строку ТОЛЬКО когда её канонический ключ уже
    лежит в том же профиле. «Реабилитация плеча» и «найти компанию» остаются как есть: канона у них
    нет, и без сырой строки от интереса не осталось бы ничего.

  — НЕ ХОДИТ В СЕТЬ. Соответствие «сырое -> ключ» спрашивается у фильтрации, и если она молчит,
    строка остаётся. Молчание сервиса не повод стирать данные человека.

Запуск (по умолчанию только показывает, ничего не пишет):
    python3 tools/strip_resolved_ru_interests.py --users users.json
    python3 tools/strip_resolved_ru_interests.py --users users.json --apply
"""
import argparse
import json
import os
import shutil
import sys
import time
import urllib.request

FILTER_URL = os.environ.get("FILTER_URL", "http://127.0.0.1:7076")
GENERIC = {"sport", "sports", "exercise", "activity", "activities", "hobby", "hobbies", "fun",
           "leisure", "beverage", "drink", "drinks", "food", "social", "socializing", "people",
           "meeting", "meetup", "friends", "community", "culture", "tradition", "lifestyle",
           "wellness", "entertainment", "game", "games", "play", "event", "events", "health", "art"}
# Правим только тех, кто пришёл сам. Всё остальное — фикстуры, см. шапку.
LIVE_SOURCE = "onboarding"


def non_latin(word):
    w = str(word or "")
    return bool(w) and not any(("a" <= c <= "z") or ("A" <= c <= "Z") for c in w)


def topics_for(word):
    """Канонические темы для строки. Пустой список = фильтрация не ответила или ответила мусором."""
    try:
        req = urllib.request.Request(FILTER_URL + "/api/filter/categorize",
                                     data=json.dumps({"text": word}).encode(),
                                     headers={"Content-Type": "application/json"})
        got = json.loads(urllib.request.urlopen(req, timeout=8).read().decode()).get("topics") or []
    except Exception as e:
        print("    фильтрация молчит (%s) — строку оставляем" % e.__class__.__name__)
        return []
    return [str(t).strip().lower() for t in got
            if str(t).strip().lower() and str(t).strip().lower() not in GENERIC]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", required=True)
    ap.add_argument("--apply", action="store_true", help="без него только показывает")
    a = ap.parse_args()

    raw = json.load(open(a.users, encoding="utf-8"))
    rows = raw["users"] if isinstance(raw, dict) and "users" in raw else raw
    if not isinstance(rows, list):
        sys.exit("не понял формат users.json")

    touched = 0
    dropped = 0
    kept = 0
    for u in rows:
        if (u.get("source") or "") != LIVE_SOURCE:
            continue
        ints = [i for i in (u.get("interests") or []) if isinstance(i, str)]
        bad = [i for i in ints if non_latin(i)]
        if not bad:
            continue
        low = {i.lower() for i in ints}
        out = list(ints)
        for w in bad:
            tp = topics_for(w)
            hit = [t for t in tp if t in low]
            if hit:
                out = [i for i in out if i != w]
                dropped += 1
                print("  − %-28s (канон уже есть: %s)" % (w, ", ".join(hit)))
            else:
                kept += 1
                print("  = %-28s (канона нет — оставляем)" % w)
        if out != ints:
            u["interests"] = out
            touched += 1

    print("\nпрофилей затронуто: %d, строк убрано: %d, оставлено: %d" % (touched, dropped, kept))
    if not a.apply:
        print("это был показ. Чтобы записать — тот же вызов с --apply")
        return
    if not touched:
        print("менять нечего")
        return
    # Резервная копия рядом с файлом, как у остальных миграций хранилища.
    bak = "%s.bak_%s" % (a.users, time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(a.users, bak)
    tmp = a.users + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    os.replace(tmp, a.users)
    print("записано. Резервная копия: %s" % bak)


if __name__ == "__main__":
    main()
