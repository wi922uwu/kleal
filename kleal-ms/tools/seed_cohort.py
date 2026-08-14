# -*- coding: utf-8 -*-
"""Засеять популяцию из готовых срезов, ОДНОЙ записью в users.json.

    python3 tools/seed_cohort.py <каталог-со-срезами> [--out users.json] [--dry]

ЗАЧЕМ НЕ ЧЕРЕЗ HTTP. Шестьсот вызовов /api/onboarding/register — это шестьсот перезаписей
users.json под блокировкой, каждая на весь файл целиком: O(n²) по объёму и минуты ожидания
на ровном месте. Здесь та же самая функция преобразования вызывается напрямую, а файл пишется
один раз.

ЗАЧЕМ НЕ СВОЯ СБОРКА СТРОКИ. Строка кандидата собирается ровно тем же `_profile_to_user`, что и
при настоящей регистрации, и интересы канонизируются тем же `_canon_interests`. Своя копия
разошлась бы с сервером при первой же правке схемы — и разошлась бы МОЛЧА: незнакомое поле не
роняет сервис, оно просто выбрасывается, и человек выглядит как «не заполнил».

ФОРМА ВХОДА — плоская, человекочитаемая (см. `_to_profile`): так срез можно и написать руками, и
прочитать глазами, не держа в голове вложенность онбординговой анкеты.

Метка source="seed" ставится намеренно: она отделяет посев от живых регистраций и позволяет снести
его одной строкой, не тронув тех, кто зарегистрировался сам.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "services", "onboarding"))
sys.path.insert(0, os.path.join(ROOT, "shared"))
import app as onb  # сервер стартует только под __main__, импорт безопасен


def _to_profile(p):
    """Плоский человек из среза -> анкета в той форме, которую ждёт _profile_to_user."""
    radius = p.get("radiusKm")
    district = str(p.get("district") or "").strip()
    return {
        "name": p.get("name"),
        "age": p.get("age"),
        "gender": p.get("gender") or "",
        # `city` уезжает в `area`, по нему матчинг ищет город. Район — в comfortableAreas:
        # если положить район в город, барселонцы из Gràcia и из Sants перестанут
        # находить друг друга, оставаясь при этом в одном городе.
        "city": p.get("city"),
        "country": p.get("country"),
        "geo": {
            "located": True,
            "coarseLat": p.get("lat"),
            "coarseLon": p.get("lon"),
            "comfortableAreas": [district] if district else [],
            "maxDistanceKm": radius,
        },
        "languages": {"comfortable": p.get("langs") or []},
        "interests": {"explicit": p.get("interests") or []},
        "goals": {"primary": p.get("goals") or []},
        "formats": p.get("formats") or [],
        "persona": p.get("persona") or None,
        "summary": p.get("summary") or "",
        "story": p.get("story") or "",
        "personality": p.get("personality") or "",
        "safety": p.get("safety") or {},
        "tz": p.get("tz") or "",
        "domains": {"dating": {"enabled": bool(p.get("datingOk"))}},
    }


def load_slices(path):
    """Читаются ТОЛЬКО slice_*.json.

    Было `*.json` — и любой оставленный рядом файл молча становился частью популяции. Ровно это и
    случилось: черновик `part1.json` сортируется раньше `slice_12.json`, поэтому в посев уехала бы
    ранняя версия, а чистовая — отброшена как «имя уже занято». Ни ошибки, ни предупреждения:
    в популяции просто оказались бы другие люди.
    """
    import glob as _glob
    people = []
    files = sorted(os.path.basename(f) for f in _glob.glob(os.path.join(path, "slice_*.json")))
    if not files:
        raise SystemExit("в %s нет ни одного slice_*.json" % path)
    skipped = [f for f in os.listdir(path)
               if f.endswith(".json") and f not in files]
    if skipped:
        print("  пропущено (не slice_*): %s" % ", ".join(sorted(skipped)[:8]))
    for f in files:
        with open(os.path.join(path, f), encoding="utf-8") as fh:
            rows = json.load(fh)
        if not isinstance(rows, list):
            raise SystemExit("%s: ожидался массив, пришло %s" % (f, type(rows).__name__))
        for r in rows:
            r["_slice"] = f
        people.extend(rows)
        print("  %-20s %d человек" % (f, len(rows)))
    return people


def warm_filtration(people, workers=8):
    """Прогреть кэш фильтрации ПАРАЛЛЕЛЬНО, до сборки строк.

    `_canon_interests` спрашивает у фильтрации английскую ручку для каждого интереса, а та
    спрашивает у модели — примерно секунда на новое слово. Шестьсот человек по четыре интереса
    подряд — это десятки минут, причём с таймаутом в шесть секунд на вызов: часть слов просто не
    успела бы и осталась без ручки. Здесь те же слова спрашиваются заранее и в несколько потоков,
    а дальше `_canon_interests` идёт обычным путём и попадает в уже тёплый кэш.

    Молча пропустить это нельзя: без ручек человек, написавший «senderismo», невидим для поиска,
    который ищет hiking, — и выглядит это не как ошибка, а как «никого не нашлось».
    """
    import json as _json
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor

    words = []
    seen = set()
    for p in people:
        for w in p.get("interests") or []:
            k = " ".join(str(w).lower().split())
            if k and k not in seen:
                seen.add(k)
                words.append(str(w))

    def ask(w):
        try:
            req = urllib.request.Request(
                onb.FILTER_URL + "/api/filter/categorize",
                data=_json.dumps({"text": w}).encode(),
                headers={"Content-Type": "application/json"})
            got = _json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
            return bool(got.get("topics"))
        except Exception:
            return False

    print("\nпрогрев фильтрации: %d разных интересов, потоков %d" % (len(words), workers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        got = list(ex.map(ask, words))
    ok = sum(1 for g in got if g)
    print("  ручки получены для %d из %d" % (ok, len(words)))
    if ok < len(words) * 0.5:
        print("  ВНИМАНИЕ: больше половины слов остались без ручки — проверь, жива ли модель")
    return ok, len(words)


def build(people):
    rows, dropped, seen = [], [], set()
    for p in people:
        nm = str(p.get("name") or "").strip()
        if not nm:
            dropped.append((p.get("_slice"), "", "без имени"))
            continue
        # Совпавшее имя — не мелочь: id считается хешем ИМЕНИ, и второй такой же человек
        # затирает первого, оставляя дыру вместо ошибки.
        if nm.lower() in seen:
            dropped.append((p.get("_slice"), nm, "имя уже занято"))
            continue
        seen.add(nm.lower())
        u = onb._profile_to_user(_to_profile(p))
        u["interests"] = onb._canon_interests(u.get("interests")) or u.get("interests")
        u["source"] = "seed"
        rows.append(u)
    return rows, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slices")
    ap.add_argument("--out", default=os.path.join(ROOT, "users.json"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--warm", type=int, default=8,
                    help="потоков прогрева фильтрации; 0 — не греть (ручек не будет)")
    a = ap.parse_args()

    print("срезы из %s:" % a.slices)
    people = load_slices(a.slices)
    if a.warm:
        warm_filtration(people, a.warm)
    rows, dropped = build(people)

    print("\nсобрано строк: %d (из %d)" % (len(rows), len(people)))
    if dropped:
        print("не взято: %d" % len(dropped))
        for s, nm, why in dropped[:20]:
            print("   %-20s %-24s %s" % (s, nm, why))

    # Что реально получилось — цифрами, а не на веру. Пустой пояс или один интерес на всех
    # выглядят как рабочий посев ровно до первого поиска.
    ints = {i for r in rows for i in (r.get("interests") or [])}
    print("\nразных интересов: %d" % len(ints))
    print("городов:          %d" % len({r.get("area") for r in rows}))
    print("часовых поясов:   %d" % len({r.get("tz") for r in rows if r.get("tz")}))
    print("с персоной:       %d" % sum(1 for r in rows if (r.get("persona") or {}).get("axes")))
    print("с историей:       %d" % sum(1 for r in rows if r.get("story")))
    print("открыты романтике:%d" % sum(1 for r in rows if r.get("datingOk")))

    if a.dry:
        print("\n--dry: ничего не записано")
        return

    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"users": rows}, f, ensure_ascii=False)
    os.replace(tmp, a.out)
    print("\nзаписано -> %s" % a.out)


if __name__ == "__main__":
    main()
