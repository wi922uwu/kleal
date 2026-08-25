# -*- coding: utf-8 -*-
"""Пул для КАЛИБРОВКИ подбора: систематический разброс по возрасту, полу, характеру и интересам.

ЗАЧЕМ ОТДЕЛЬНЫЙ ПУЛ. `gen_test_users.py` строит пул под золотую батарею: он проверяет сценарии,
а не оси. Возраст там лежит в трёх окнах (нет возраста / 16-17 / 20-44), а пола нет вовсе — на
таком пуле нельзя ни увидеть, как ведёт себя возрастное окно, ни проверить, что пол не течёт из
свиданий в дружбу. Здесь наоборот: сценариев нет, есть решётка.

РЕШЁТКА, А НЕ СЛУЧАЙНОСТЬ. Каждый человек — точка в произведении осей, и по каждой оси есть
известное число людей. Тогда любое утверждение вида «в окне 25-30 обязано найтись N человек»
проверяемо арифметикой, а не наблюдением.

    возраст   18..70, полосами по 4 года          -> 13 полос
    пол       male / female / nonbinary / нет      -> как в живой базе, включая ОТСУТСТВИЕ
    характер  persona.axes по пяти осям мастера    -> есть у ~74%, как в живой базе
    интересы  20 кластеров с переводами на ru/es

ЗНАЧЕНИЯ БЕРУТСЯ ИЗ ЖИЗНИ, А НЕ ИЗ ГОЛОВЫ. Первая версия этого пула раздавала пол как `f`/`m`/`x`
и вайб как `chill`/`party` — и проверяла то, чего в продукте нет. Мастер интента шлёт
`sex: Male|Female`, характер уходит как `wantPersona` по осям energy/depth/pace/planning/give, а
у четверти людей пола нет вовсе и у четверти нет пройденного теста. Пул обязан это повторять,
иначе калибруется воображаемая система.

ТЕГИ несут ось в имени: `age_25_28`, `gen_f`, `vibe_chill`, `int_coffee`. Проверка ищет по тегу и
не зависит от имён, которые генератор может перетасовать.

    python3 tools/gen_calib_pool.py --out pool.json --index index.json [--seed 11]
"""
import argparse
import hashlib
import json
import random

# ---------------------------------------------------------------- оси
AGE_BANDS = [(a, a + 3) for a in range(18, 71, 4)]          # 18-21, 22-25, ... 66-69
# Пол — как в живой базе: male/female примерно поровну, nonbinary редко, у четверти НЕТ поля.
# Отсутствие важнее всего: гейт пола отбрасывает таких людей молча, и это надо видеть.
# Доли примерно как в живой базе: male ~31%, female ~31%, nonbinary ~6%, без поля ~31%.
GENDERS = ("male", "female", None, "male", "female", None, "male", "female",
           None, "male", "female", None, "male", "female", None, "nonbinary")
VIBES = ("chill", "party", "calm", "energetic", "introvert", "extrovert", "competitive")

# Оси характера, которые умеет спросить мастер интента (_NATURE_SAY в services/matching/app.py).
# В базе осей десять, но спросить можно про эти пять — остальные собираются и не используются.
PERSONA_AXES = {
    "energy": ("energised", "drained"),
    "depth": ("deep", "light"),
    "pace": ("fast", "slow"),
    "planning": ("advance", "spontaneous"),
    "give": ("listen", "instigate"),
}
PERSONA_SHARE = 0.74          # доля людей с пройденным тестом — как в живой базе

# Кластеры интересов: (ключ, en, ru, es). Ключ — то, что ляжет в профиль и по чему ищет движок.
CLUSTERS = [
    ("coffee",        "coffee",            "кофе",                "café"),
    ("sea fishing",   "sea fishing",       "рыбалка на море",     "pesca en el mar"),
    ("chess",         "chess",             "шахматы",             "ajedrez"),
    ("padel",         "padel",             "падел",               "pádel"),
    ("running",       "running",           "бег",                 "correr"),
    ("hiking",        "hiking",            "поход",               "senderismo"),
    ("yoga",          "yoga",              "йога",                "yoga"),
    ("photography",   "photography",       "фотография",          "fotografía"),
    ("board games",   "board games",       "настольные игры",     "juegos de mesa"),
    ("dota 2",        "dota 2",            "дота 2",              "dota 2"),
    ("craft beer",    "craft beer",        "крафтовое пиво",      "cerveza artesana"),
    ("cinema",        "cinema",            "кино",                "cine"),
    ("reading",       "reading",           "чтение",              "lectura"),
    ("investing",     "investing",         "инвестиции",          "inversiones"),
    ("software development", "software development", "разработка по", "desarrollo de software"),
    ("language exchange", "language exchange", "языковой обмен",  "intercambio de idiomas"),
    ("swimming",      "swimming",          "плавание",            "natación"),
    ("cycling",       "cycling",           "велоспорт",           "ciclismo"),
    ("stand up",      "stand up",          "стендап",             "monólogos"),
    ("cooking",       "cooking",           "готовка",             "cocina"),
]

GEO_BCN = (41.3874, 2.1686)
LANG_SETS = (("ru", "en"), ("es", "en"), ("en",), ("ru",), ("es", "ca"), ("ru", "es", "en"))


def build(n, seed):
    rnd = random.Random(seed)
    users, index = [], {}

    def tag(t, nm):
        index.setdefault(t, []).append(nm)

    i = 0
    # Полный обход решётки: полоса возраста x пол x кластер интереса. Характер и язык
    # раздаются по кругу — их независимость от остальных осей нужна, чтобы вайб-проверки
    # не оказались привязаны к возрасту.
    for bi, (lo, hi) in enumerate(AGE_BANDS):
        for gi in range(3):              # три места в полосе; пол берётся из GENDERS отдельно
            for ci, (key, en, ru, es) in enumerate(CLUSTERS):
                if len(users) >= n:
                    break
                i += 1
                nm = "Calib%03d" % i
                vibe = VIBES[(bi + gi + ci) % len(VIBES)]
                g = GENDERS[(bi * 3 + gi + ci) % len(GENDERS)]
                langs = list(LANG_SETS[(gi + ci) % len(LANG_SETS)])
                age = lo + ((ci + gi) % (hi - lo + 1))
                # Свои слова человека — на языке, который у него первый: так проверяется, что
                # подбор находит его и по переводу, а не только по английскому ключу.
                own = {"ru": ru, "es": es}.get(langs[0], en)
                # Характер: детерминированно от порядкового номера, чтобы прогон был
                # повторяемым, и ровно у PERSONA_SHARE людей — как в живой базе.
                # Оси выводятся из ХЭША ИМЕНИ, а не из порядкового номера. Номер шагает вместе с
                # кластером интересов (шаг 20), и по чётности внутри одного кластера у всех
                # получался ОДИН И ТОТ ЖЕ характер: замер показывал то «совпали все», то «ни
                # одного», и выглядело это как мёртвый рычаг в движке. Оси обязаны быть
                # независимы от остальных осей решётки, иначе решётка не решётка.
                axes = {}
                h = hashlib.sha1(nm.encode()).digest()
                if h[0] < int(PERSONA_SHARE * 256):
                    for ai, (axis, toks) in enumerate(sorted(PERSONA_AXES.items())):
                        axes[axis] = toks[h[ai + 1] % 2]
                tags = ["age_%d_%d" % (lo, hi), "vibe_" + vibe,
                        "int_" + key.replace(" ", "_")]
                tags.append("gen_" + (g or "none"))
                for axis, tok in axes.items():
                    tags.append("nat_%s_%s" % (axis, tok))
                u = {
                    "id": "cal" + hashlib.sha1(nm.encode()).hexdigest()[:8],
                    "name": nm, "age": age, "vibe": vibe, "langs": langs,
                    "interests": [key] if own == en else [own, key],
                    "source": "calib", "tags": tags,
                    "verified": True, "datingOk": (ci % 3 == 0), "role": "meet",
                    "pending": 0, "blocksMe": False, "paused": False, "open": True,
                    "lastActiveDays": rnd.randint(0, 3), "declinedOwnerDaysAgo": None,
                    "intents": [], "entities": [], "dealBreakers": [],
                    "geo": {"coarseLat": round(GEO_BCN[0] + (rnd.random() - .5) * .02, 5),
                            "coarseLon": round(GEO_BCN[1] + (rnd.random() - .5) * .02, 5)},
                    "receiving": {"status": "active", "allowed_domains": None,
                                  "passive_outreach": True,
                                  "quiet_hours": {"start": "00:00", "end": "00:00",
                                                  "tz_offset_min": 120},
                                  "paused_until": None},
                }
                if g:
                    u["gender"] = g          # отсутствие пола — тоже значение, поле просто не заводится
                if axes:
                    u["persona"] = {"v": 1, "axes": axes}
                users.append(u)
                for t in u["tags"]:
                    tag(t, nm)
    return users, index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=780)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default="calib_pool.json")
    ap.add_argument("--index", default="calib_index.json")
    a = ap.parse_args()
    users, index = build(a.n, a.seed)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False)
    with open(a.index, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    print("людей: %d" % len(users))
    print("полос возраста: %d | полов: %d | характеров: %d | кластеров: %d"
          % (len(AGE_BANDS), len(GENDERS), len(VIBES), len(CLUSTERS)))
    for ax in ("age_", "gen_", "vibe_", "int_", "nat_"):
        ks = [k for k in index if k.startswith(ax)]
        sizes = sorted({len(index[k]) for k in ks})
        print("   %-6s тегов %2d, размеры %s" % (ax, len(ks), sizes[:5]))


if __name__ == "__main__":
    main()
