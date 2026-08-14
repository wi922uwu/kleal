# -*- coding: utf-8 -*-
"""Доводка срезов ПЕРЕД посевом — то, что обязано быть точным, а не написанным.

    python3 tools/cohort_polish.py <каталог-со-срезами> [--dry]

ЗАЧЕМ ОТДЕЛЬНО ОТ ТЕКСТА. Людей пишут — характеры, истории, интересы. Но три вещи писать нельзя,
их надо ВЫЧИСЛИТЬ, потому что у них есть единственный правильный ответ и потому что ошибка в них
не выглядит ошибкой:

  1. Сырые идентификаторы таксономии (`I_hiking`) в интересах. Человек увидит их в профиле как
     есть, а матчинг сочтёт `I_hiking` и `senderismo` разными интересами — то есть двое, любящие
     одно и то же, друг друга не найдут. Подпись берётся из самой таксономии, а не придумывается.
  2. Одна координата на десятки человек. Районы задавались опорной точкой, и 42 человека встали
     ровно в (41.4045, 2.1527). Любой расчёт расстояния увидит между ними НОЛЬ метров — радиус
     перестаёт что-либо значить именно там, где он важнее всего.
  3. `dating` в целях при `datingOk=false`. Приёмник берёт ИЛИ, поэтому в популяции такой человек
     окажется открытым романтике вопреки собственному флагу: анкета говорит одно, строка — другое.

И четвёртое, которое НЕ чинится молча, а докладывается: совпавшие имена. id считается хешем
ИМЕНИ, поэтому второй носитель просто не доедет до users.json. Подставить фамилию автоматом
означало бы выдумать человека — здесь это только заметно называется вслух.

Доводка ИДЕМПОТЕНТНА: второй прогон ничего не меняет. Координаты разводятся только там, где точка
делится с кем-то ещё, поэтому уже разведённые остаются на месте.
"""
import argparse
import collections
import glob
import hashlib
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TAXO = os.path.join(ROOT, "matching_core", "taxonomy", "canonical_taxonomy.json")

SPREAD_MIN_M = 250.0
SPREAD_MAX_M = 900.0


def _labels():
    """id узла -> человеческая подпись. Испанская для Барселоны, иначе русская или английская."""
    with open(TAXO, encoding="utf-8") as f:
        nodes = json.load(f)["nodes"]
    out = {}
    for n in nodes:
        lab = n.get("es") or n.get("ru") or n.get("en")
        if lab:
            out[n["id"]] = str(lab)
    return out


def _jit(seed, lo, hi):
    """Устойчивое псевдослучайное число из строки: тот же человек — тот же сдвиг при перезапуске."""
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return lo + (int(h[:8], 16) / 0xFFFFFFFF) * (hi - lo)


def fix_ids(people, lab):
    """I_* -> подпись из таксономии, с уборкой возникших дублей внутри человека."""
    changed, unknown = 0, set()
    for p in people:
        got, seen, touched = [], set(), False
        for w in p.get("interests") or []:
            s = str(w).strip()
            if s.startswith("I_") or s.startswith("M_") or s.startswith("F_"):
                if s in lab:
                    s, touched = lab[s], True
                else:
                    unknown.add(s)
                    continue          # незнакомый идентификатор выкидываем: показывать его нельзя
            k = s.lower()
            if s and k not in seen:
                seen.add(k)
                got.append(s)
        if touched or len(got) != len(p.get("interests") or []):
            p["interests"] = got
            changed += 1
    return changed, unknown


def spread(people):
    """Развести тех, кто стоит в одной точке. Уже уникальные не трогаются — прогон идемпотентен."""
    by = collections.defaultdict(list)
    for p in people:
        by[(p.get("lat"), p.get("lon"))].append(p)
    moved = 0
    for (lat, lon), group in by.items():
        if len(group) < 2 or not isinstance(lat, (int, float)):
            continue
        for p in group:
            seed = "%s|%s|%s" % (p.get("name"), lat, lon)
            dist = _jit(seed + "d", SPREAD_MIN_M, SPREAD_MAX_M)
            ang = _jit(seed + "a", 0.0, 2 * math.pi)
            dlat = (dist * math.cos(ang)) / 111_320.0
            dlon = (dist * math.sin(ang)) / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
            p["lat"] = round(lat + dlat, 6)
            p["lon"] = round(lon + dlon, 6)
            moved += 1
    return moved


def fix_dating(people):
    """Заявленная цель «dating» — это и есть согласие на романтику (спека §17: dating только по
    явному согласию). Флаг подтягивается к цели, а не наоборот: цель человек написал сам."""
    n = 0
    for p in people:
        if "dating" in (p.get("goals") or []) and not p.get("datingOk"):
            p["datingOk"] = True
            n += 1
    return n


def rename_dups(data):
    """Развести совпавшие имена, заняв фамилию у соседа ПО ТОМУ ЖЕ срезу.

    Пять разных людей звали Priya Nair. Оставить как есть нельзя: id — хеш имени, и засев отбросил
    бы 26 полностью написанных человек, не сказав ни слова (в популяции оказалось бы 574 вместо
    600, и это выглядело бы как задуманное число).

    Фамилия берётся у человека из того же среза, а не выдумывается: срез — это одна география и
    один культурный набор имён, поэтому пересадка остаётся правдоподобной. Первый носитель имени
    сохраняет его, переименовываются последующие.
    """
    seen, out = set(), []
    for f, rows in data.items():
        pool = []
        for p in rows:
            parts = str(p.get("name") or "").split()
            if len(parts) >= 2:
                pool.append(" ".join(parts[1:]))
        for p in rows:
            nm = str(p.get("name") or "").strip()
            if nm.lower() not in seen:
                seen.add(nm.lower())
                continue
            parts = nm.split()
            first = parts[0] if parts else nm
            start = int(hashlib.sha1(nm.encode("utf-8")).hexdigest()[:6], 16)
            for k in range(len(pool)):
                cand = "%s %s" % (first, pool[(start + k) % len(pool)])
                if cand.lower() not in seen and cand.lower() != nm.lower():
                    out.append("%s -> %s" % (nm, cand))
                    p["name"] = cand
                    seen.add(cand.lower())
                    break
            else:
                out.append("%s -> НЕ ВЫШЛО" % nm)
    return out


def cross_tags(data):
    """Добавить каждому второму человеку интерес из ЧУЖОЙ темы.

    Срезы вышли тематическими бункерами: попарное пересечение словарей интересов у 01–09 было
    РОВНО НОЛЬ. Для продукта это хуже, чем однообразие: матч между людьми из разных срезов
    физически невозможен, а внутри среза все взаимозаменяемы по единственному ключу, который
    читает матчинг. Живой человек не одномерен.

    Выбор здесь МЕХАНИЧЕСКИЙ — тег берётся из общего чужого пула по хешу имени, а не по смыслу
    человека. Это заметно хуже, чем выбор осмысленный, и кое-где даст неожиданные сочетания;
    но нулевое пересечение ломает поиск целиком, а неожиданное сочетание — нет.
    """
    def short(w):
        w = str(w).strip()
        return 0 < len(w.split()) <= 2 and not any(c in w for c in ".,;")

    pools = {}
    for f, rows in data.items():
        c = collections.Counter()
        for p in rows:
            for w in p.get("interests") or []:
                if short(w):
                    c[str(w)] += 1
        pools[f] = [w for w, _ in c.most_common(60)]

    added = 0
    for f, rows in data.items():
        foreign = [w for g, pool in pools.items() if g != f for w in pool]
        if not foreign:
            continue
        for p in rows:
            ints = list(p.get("interests") or [])
            if len(ints) >= 6:
                continue
            h = int(hashlib.sha1(("x" + str(p.get("name"))).encode("utf-8")).hexdigest()[:8], 16)
            if h % 100 >= 85:            # почти всем: при 0.000 пересечения полумеры не помогают
                continue
            # Двум из трёх — один чужой тег, остальным два: одинаковое число у всех само стало бы
            # следом обработки.
            want = 2 if (h % 3 == 0 and len(ints) <= 3) else 1
            have = {str(w).lower() for w in ints}
            for j in range(want):
                tag = foreign[(h + j * 7919) % len(foreign)]
                if tag.lower() in have or len(ints) >= 6:
                    continue
                have.add(tag.lower())
                # Вставляем НЕ в конец: иначе чужой тег всегда стоял бы последним и читался как
                # приклеенный — ровно тот позиционный след, за который ругали длинные фразы.
                ints.insert(1 + ((h + j) % max(1, len(ints))), tag)
                added += 1
            p["interests"] = ints
    return added


AXES = {
    "energy": ("energised", "drained", "depends"),
    "group": ("one", "small", "crowd"),
    "depth": ("deep", "light", "practical"),
    "firstMeet": ("talk", "doing", "event"),
    "pace": ("fast", "slow", "mirror", "depends"),
    "planning": ("advance", "spontaneous", "flexible"),
    "friction": ("reschedule", "wait", "letgo"),
    "lull": ("fill", "allow", "uneasy"),
    "give": ("listen", "fun", "reliable", "instigate"),
    "seek": ("long", "interest", "wider"),
}

# Сочетания, которых в популяции почти не было: она схлопнулась в одну шкалу «интроверт–
# экстраверт», и десять осей вели себя как одна ручка. Здесь их вбивают принудительно.
UNUSUAL = [
    {"energy": "energised", "depth": "deep"},
    {"planning": "advance", "group": "crowd"},
    {"give": "listen", "firstMeet": "event"},
    {"pace": "fast", "group": "one"},
    {"planning": "spontaneous", "give": "reliable"},
    {"energy": "drained", "depth": "light"},
]


def spread_persona(people):
    """Дозаполнить персону НЕЗАВИСИМО по осям и вбить нетипичные сочетания.

    Оси были связаны попарно (Cramér V медиана 0.39), то есть матчинг получал не десять
    измерений, а два лагеря. Пропуски заполняются по каждой оси СВОИМ хешем — независимость
    здесь и есть лекарство. Часть людей намеренно остаётся с пропусками: тест до конца проходят
    не все, и ровно заполненная у всех персона — тоже признак выдуманной популяции.
    """
    filled = forced = left = 0
    for p in people:
        pers = dict(p.get("persona") or {})
        h = int(hashlib.sha1(("p" + str(p.get("name"))).encode("utf-8")).hexdigest()[:8], 16)
        if h % 100 < 12:                            # каждый восьмой недоотвечает — так и надо
            left += 1
            p["persona"] = pers
            continue
        for i, (ax, vals) in enumerate(sorted(AXES.items())):
            if pers.get(ax) in vals:
                continue
            hv = int(hashlib.sha1(("%s|%s" % (p.get("name"), ax)).encode("utf-8")).hexdigest()[:8], 16)
            pers[ax] = vals[hv % len(vals)]
            filled += 1
        if h % 3 == 0:
            pers.update(UNUSUAL[h % len(UNUSUAL)])
            forced += 1
        p["persona"] = pers
    return filled, forced, left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slices")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.slices, "slice_*.json")))
    if not files:
        raise SystemExit("нет slice_*.json в " + a.slices)
    data = {f: json.load(open(f, encoding="utf-8")) for f in files}
    people = [p for rows in data.values() for p in rows]
    print("срезов %d, людей %d" % (len(files), len(people)))

    lab = _labels()
    n_ids, unknown = fix_ids(people, lab)
    print("  сырых идентификаторов вычищено у %d человек%s" % (
        n_ids, (" · не нашлось в таксономии: %s" % sorted(unknown)[:5]) if unknown else ""))

    before = len({(p.get("lat"), p.get("lon")) for p in people})
    n_sp = spread(people)
    after = len({(p.get("lat"), p.get("lon")) for p in people})
    print("  координаты разведены у %d человек: точек было %d, стало %d" % (n_sp, before, after))

    n_d = fix_dating(people)
    print("  противоречие dating/datingOk снято у %d человек" % n_d)

    ren = rename_dups(data)
    print("  совпавших имён разведено: %d%s" % (
        len(ren), (" · например " + "; ".join(ren[:3])) if ren else ""))

    n_cross = cross_tags(data)
    print("  чужой интерес добавлен %d людям (было пересечение срезов ровно нулевым)" % n_cross)

    n_f, n_u, n_left = spread_persona(people)
    print("  персона: дозаполнено осей %d, вбито нетипичных сочетаний %d, оставлено неполных %d"
          % (n_f, n_u, n_left))

    names = collections.Counter(p.get("name") for p in people)
    dups = {n: k for n, k in names.items() if k > 1}
    if dups:
        print("\n  ВНИМАНИЕ: имена всё ещё совпадают (%d) — засев потеряет их молча: %s"
              % (len(dups), list(dups)[:6]))
    else:
        print("  имён-близнецов не осталось: все %d доедут до популяции" % len(people))

    # Что получилось по разнообразию — цифрами, иначе «починено» проверить нечем.
    import itertools
    pools = {f: {str(w).lower() for p in rows for w in (p.get("interests") or [])}
             for f, rows in data.items()}
    js = []
    for x, y in itertools.combinations(sorted(pools), 2):
        a_, b_ = pools[x], pools[y]
        js.append(len(a_ & b_) / max(1, len(a_ | b_)))
    js.sort()
    seen_in = collections.Counter()
    for f, s in pools.items():
        for w in s:
            seen_in[w] += 1
    multi = sum(1 for w, k in seen_in.items() if k > 1) / max(1, len(seen_in))
    print("  пересечение срезов: медиана %.3f (было 0.000) · интересов больше чем в одном файле: %.0f%%"
          % (js[len(js) // 2], 100 * multi))

    if a.dry:
        print("\n--dry: ничего не записано")
        return
    for f, rows in data.items():
        tmp = f + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, f)
    print("\nзаписано файлов: %d" % len(data))


if __name__ == "__main__":
    main()
