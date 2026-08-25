# -*- coding: utf-8 -*-
"""Калибровочная батарея подбора: сотни запросов по четырём осям, с разбором по осям.

ЧЕМ ОТЛИЧАЕТСЯ ОТ ЗОЛОТОЙ БАТАРЕИ. `eval_matching.py` проверяет СЦЕНАРИИ — конкретные истории,
собранные руками, и отвечает «прошло/не прошло». Здесь проверяются ОСИ: возраст, интересы, пол,
характер. Сценарии не пишутся руками, а порождаются обходом решётки пула
(`gen_calib_pool.py`), поэтому их сотни и покрытие считается арифметикой, а не на глаз.

ЧТО ЭТО ДАЁТ ДЛЯ КАЛИБРОВКИ. Отчёт идёт ПО ОСЯМ: видно не «упало 37 тестов», а «возраст 100%,
интересы 92%, характер 61%» — то есть куда именно крутить веса и правила.

    python3 tools/calib_matching.py --pool P.json --index I.json [--only age] [--json out.json]
"""
import argparse
import collections
import json
import os
import sys

os.environ.setdefault("KLEAL_INCLUDE_LOADTEST", "1")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (ROOT, os.path.join(ROOT, "shared"), os.path.join(ROOT, "services", "matching")):
    if p not in sys.path:
        sys.path.insert(0, p)

NOW = 1_760_000_000
BASE_INTENT = {"type": "social_meet", "mode": "offline", "format": "1:1", "time": "today"}
BASE_PROF = {"name": "Калибратор", "age": 30, "gender": "x", "vibe": "chill",
             "geo": {"coarseLat": 41.3874, "coarseLon": 2.1686},
             "languages": {"comfortable": ["ru", "en", "es"]}, "interests": []}

# Оси пула — держим здесь, чтобы генератор сценариев не читал сам пул дважды.
AGE_BANDS = [(a, a + 3) for a in range(18, 71, 4)]
# Мастер интента шлёт ИМЕННО ЭТО: sex со значениями Male/Female (Any не отправляется вовсе),
# см. app/intent.tsx и SEXES в src/onboarding.ts. Гейт приводит обе стороны к нижнему регистру.
SEX_CHOICES = ("Male", "Female")
SEX_TO_STORED = {"Male": "male", "Female": "female"}
# Характер уходит как wantPersona по пяти осям — это ПОЖЕЛАНИЕ, не фильтр: никого не отсекает,
# только поднимает совпавших внутри их полосы (persona_order в services/matching/app.py).
PERSONA_AXES = {
    "energy": ("energised", "drained"), "depth": ("deep", "light"),
    "pace": ("fast", "slow"), "planning": ("advance", "spontaneous"),
    "give": ("listen", "instigate"),
}
VIBES = ("chill", "party", "calm", "energetic", "introvert", "extrovert", "competitive")
CLASH = {("chill", "party"), ("calm", "energetic"), ("introvert", "extrovert"),
         ("competitive", "chill"), ("calm", "competitive")}
CLUSTERS = [
    ("coffee", "кофе", "café"), ("sea fishing", "рыбалка на море", "pesca en el mar"),
    ("chess", "шахматы", "ajedrez"), ("padel", "падел", "pádel"),
    ("running", "бег", "correr"), ("hiking", "поход", "senderismo"),
    ("yoga", "йога", "yoga"), ("photography", "фотография", "fotografía"),
    ("board games", "настольные игры", "juegos de mesa"), ("dota 2", "дота 2", "dota 2"),
    ("craft beer", "крафтовое пиво", "cerveza artesana"), ("cinema", "кино", "cine"),
    ("reading", "чтение", "lectura"), ("investing", "инвестиции", "inversiones"),
    ("software development", "разработка по", "desarrollo de software"),
    ("language exchange", "языковой обмен", "intercambio de idiomas"),
    ("swimming", "плавание", "natación"), ("cycling", "велоспорт", "ciclismo"),
    ("stand up", "стендап", "monólogos"), ("cooking", "готовка", "cocina"),
]


def _tag(key):
    return "int_" + key.replace(" ", "_")


# ---------------------------------------------------------------- порождение сценариев
def cases():
    out = []

    def add(cid, axis, intent, expect, prof=None):
        out.append({"id": cid, "axis": axis, "intent": dict(BASE_INTENT, **intent),
                    "profile": dict(BASE_PROF, **(prof or {})), "expect": expect})

    # ---- ВОЗРАСТ: окно обязано держаться, и внутри него обязаны быть люди -----------------
    for lo, hi in AGE_BANDS:
        # Верхняя полоса решётки (70..73) в пуле пуста по построению — там людей нет,
        # и требовать от неё непустоту значило бы проверять генератор, а не движок.
        exp = {"all_age_within": [lo, hi]}
        if lo <= 66:
            exp["nonempty"] = True
        add("age_band_%d_%d" % (lo, hi), "возраст",
            {"topics": ["coffee"], "minAge": lo, "maxAge": hi}, exp)
        add("age_from_%d" % lo, "возраст",
            {"topics": ["coffee"], "minAge": lo},
            {"all_age_within": [lo, None]})
        add("age_to_%d" % hi, "возраст",
            {"topics": ["coffee"], "maxAge": hi},
            {"all_age_within": [None, hi]})
    # вырожденные и граничные
    # Перевёрнутое окно мастер прислать не может (там ползунок), но ручка публична: границы
    # обязаны обменяться, а не потерять верхнюю. Ждём результат ПОСЛЕ обмена.
    add("age_reversed_30_28", "возраст", {"topics": ["coffee"], "minAge": 30, "maxAge": 28},
        {"all_age_within": [28, 30], "note": "перевёрнутое окно обменивается"})
    add("age_reversed_40_25", "возраст", {"topics": ["coffee"], "minAge": 40, "maxAge": 25},
        {"all_age_within": [25, 40], "note": "перевёрнутое окно обменивается"})
    add("age_minor_block", "возраст", {"topics": ["coffee"], "minAge": 14, "maxAge": 17},
        {"empty": True, "note": "несовершеннолетние недоступны"})
    add("age_none", "возраст", {"topics": ["coffee"]}, {"nonempty": True})
    add("age_all_18_99", "возраст", {"topics": ["coffee"], "minAge": 18, "maxAge": 99},
        {"all_age_within": [18, 99], "nonempty": True})
    # окно поверх РАЗНЫХ интересов: гейт не имеет права зависеть от темы запроса
    for lo, hi in AGE_BANDS:
        for en, _ru, _es in CLUSTERS[:3]:
            add("age_%d_%s" % (lo, _tag(en)), "возраст",
                {"topics": [en], "minAge": lo, "maxAge": hi},
                {"all_age_within": [lo, hi]})

    # ---- ИНТЕРЕСЫ: свой кластер находится на трёх языках, чужой не занимает верх ----------
    for en, ru, es in CLUSTERS:
        t = _tag(en)
        add("int_en_%s" % t, "интересы", {"topics": [en], "phrase": en},
            {"include_tag": t, "nonempty": True})
        add("int_ru_%s" % t, "интересы", {"topics": [ru], "phrase": ru},
            {"include_tag": t, "note": "кросс-язык ru"})
        add("int_es_%s" % t, "интересы", {"topics": [es], "phrase": es},
            {"include_tag": t, "note": "кросс-язык es"})
        add("int_top_%s" % t, "интересы", {"topics": [en], "phrase": en},
            {"t1_all_tag": t, "note": "первый ярус только свои"})
    # ПОРЯДОК ПО СИЛЕ. Проверка «точное выше родственного» кусается только там, где точных
    # НЕ ХВАТАЕТ на выдачу и движку приходится добирать родственными. На полном пуле в каждом
    # кластере 39 человек, восьмёрка набирается своими, и проверка молчит — измерено: 0 из 40
    # срабатываний. Поэтому выборка сужается возрастным окном: в полосе кластер даёт единицы.
    for en, _ru, _es in CLUSTERS:
        add("ord_%s" % _tag(en), "интересы", {"topics": [en], "phrase": en},
            {"level_order": _tag(en), "note": "точное выше родственного (полный пул)"})
        for lo, hi in AGE_BANDS[:4]:
            add("ord_scarce_%d_%s" % (lo, _tag(en)), "интересы",
                {"topics": [en], "phrase": en, "minAge": lo, "maxAge": hi},
                {"level_order": _tag(en), "all_age_within": [lo, hi],
                 "note": "точных мало — добор обязан идти ПОСЛЕ них"})
    # чужой кластер не должен всплывать первым ярусом. Три разных «чужих» на кластер: одним
    # промахом можно ошибиться, тремя — уже видно систему.
    for i, (en, _ru, _es) in enumerate(CLUSTERS):
        for step in (7, 11, 13):
            other = CLUSTERS[(i + step) % len(CLUSTERS)][0]
            if other == en:
                continue
            add("int_not_%s_vs_%s" % (_tag(en), _tag(other)), "интересы",
                {"topics": [en], "phrase": en}, {"t1_not_tag": _tag(other)})

    # ---- ПОЛ: поле `sex`, значения мастера. Экран не шлёт «Any» — его отсутствие и есть «любой».
    for sx in SEX_CHOICES:
        st = SEX_TO_STORED[sx]
        add("sex_dating_%s" % st, "пол",
            {"topics": ["coffee"], "type": "dating", "sex": sx, "minAge": 18},
            {"all_gender": st, "note": "свидания: пол фильтрует"})
        add("sex_social_%s" % st, "пол", {"topics": ["coffee"], "sex": sx},
            {"all_gender": st, "note": "дружба: пол сейчас тоже фильтрует"})
        # Люди БЕЗ пола отбрасываются молча — четверть базы. Проверяем, что это видно.
        add("sex_drops_unknown_%s" % st, "пол", {"topics": ["coffee"], "sex": sx},
            {"none_without_gender": True, "note": "у кого пола нет — выпадают"})
    add("sex_absent", "пол", {"topics": ["coffee"]},
        {"mixed_gender": True, "note": "поля нет — не фильтр"})
    add("sex_any_word", "пол", {"topics": ["coffee"], "sex": "Any"},
        {"mixed_gender": True, "note": "«Any» обязано читаться как «не фильтровать»"})
    add("sex_nonbinary_unreachable", "пол", {"topics": ["coffee"], "sex": "nonbinary"},
        {"all_gender": "nonbinary", "note": "мастер такого не шлёт, но гейт обязан быть честным"})
    for en, _ru, _es in CLUSTERS[:12]:
        for sx in SEX_CHOICES:
            add("sex_%s_%s" % (SEX_TO_STORED[sx], _tag(en)), "пол",
                {"topics": [en], "sex": sx}, {"all_gender": SEX_TO_STORED[sx]})

    # ---- ХАРАКТЕР: wantPersona поднимает совпавших и НЕ отсекает никого ------------------
    for axis, toks in sorted(PERSONA_AXES.items()):
        for tok in toks:
            for en, _ru, _es in CLUSTERS[:8]:
                add("nat_%s_%s_%s" % (axis, tok, _tag(en)), "характер",
                    {"topics": [en], "wantPersona": {axis: tok}},
                    {"persona_lifts": (axis, tok), "no_shrink": True})
    # Пожелание не имеет права поднять человека из худшей полосы в лучшую.
    for axis, toks in sorted(PERSONA_AXES.items()):
        for en, _ru, _es in CLUSTERS[:4]:
            add("natband_%s_%s" % (axis, _tag(en)), "характер",
                {"topics": [en], "wantPersona": {axis: toks[0]}},
                {"persona_respects_band": True, "level_order": _tag(en)})
    # Две оси разом: совпавший по обеим обязан стоять выше совпавшего по одной.
    for en, _ru, _es in CLUSTERS[:6]:
        add("nat_two_%s" % _tag(en), "характер",
            {"topics": [en], "wantPersona": {"energy": "drained", "depth": "deep"}},
            {"persona_more_hits_first": True, "no_shrink": True})
    # Вайб как признак social_context — отдельная механика, проверяем, что клеш не наверху.
    # Вайб: на полном пуле столкновение до верхушки не доходило ни разу (0 из 28). Сужаем
    # возрастом — тогда выбирать не из кого, и признак social_context виден.
    for mv in VIBES:
        for en, _ru, _es in CLUSTERS[:4]:
            add("vibe_%s_%s" % (mv, _tag(en)), "характер", {"topics": [en]},
                {"no_clash_top": 3}, prof={"vibe": mv})
        for lo, hi in AGE_BANDS[:3]:
            add("vibe_scarce_%s_%d" % (mv, lo), "характер",
                {"topics": ["coffee"], "minAge": lo, "maxAge": hi},
                {"no_clash_top": 3, "all_age_within": [lo, hi]}, prof={"vibe": mv})

    # ---- КОМБИНАЦИИ ----------------------------------------------------------------------
    for lo, hi in AGE_BANDS[:10]:
        for en, _ru, _es in CLUSTERS[:6]:
            add("mix_age%d_%s" % (lo, _tag(en)), "сочетания",
                {"topics": [en], "minAge": lo, "maxAge": hi},
                {"all_age_within": [lo, hi]})
    for sx in SEX_CHOICES:
        for lo, hi in AGE_BANDS[:9]:
            add("mix_sex%s_age%d" % (SEX_TO_STORED[sx], lo), "сочетания",
                {"topics": ["coffee"], "sex": sx, "minAge": lo, "maxAge": hi, "type": "dating"},
                {"all_gender": SEX_TO_STORED[sx], "all_age_within": [lo, hi]})
    # Возраст + характер: пожелание не имеет права сузить окно.
    for lo, hi in AGE_BANDS[:6]:
        add("mix_age%d_nat" % lo, "сочетания",
            {"topics": ["coffee"], "minAge": lo, "maxAge": hi,
             "wantPersona": {"energy": "drained"}},
            {"all_age_within": [lo, hi], "no_shrink": True})
    return out


# ---------------------------------------------------------------- проверки
def judge(sc, cands, users, tags_of, prof):
    e, F = sc["expect"], []
    ages = [c.get("age") for c in cands]
    if e.get("nonempty") and not cands:
        F.append("пусто, а должны быть люди")
    if e.get("empty") and cands:
        F.append("должно быть пусто, пришло %d" % len(cands))
    w = e.get("all_age_within")
    if w:
        mn, mx = w
        bad = [(c.get("name"), c.get("age")) for c in cands
               if c.get("age") is None or (mn and c["age"] < mn) or (mx and c["age"] > mx)]
        if bad:
            F.append("вне окна %s: %d (%s)" % (w, len(bad),
                     ", ".join("%s:%s" % b for b in bad[:3])))
    g = e.get("all_gender")
    if g:
        bad = [c.get("name") for c in cands
               if str((users.get(c.get("name")) or {}).get("gender") or "") != g]
        if bad:
            F.append("чужой пол: %d (%s)" % (len(bad), ", ".join(map(str, bad[:3]))))
    if e.get("mixed_gender") and cands:
        gs = {str((users.get(c.get("name")) or {}).get("gender") or "") for c in cands}
        if len(gs) < 2:
            F.append("пол схлопнулся до %s, хотя фильтра нет" % (sorted(gs) or "—"))
    t = e.get("include_tag")
    if t and not any(t in tags_of.get(c.get("name"), ()) for c in cands):
        F.append("нет ни одного с тегом %s" % t)
    t = e.get("t1_all_tag")
    if t:
        bad = [c.get("name") for c in cands
               if c.get("tier") == "T1" and t not in tags_of.get(c.get("name"), ())]
        if bad:
            F.append("в T1 чужие: %d (%s)" % (len(bad), ", ".join(map(str, bad[:3]))))
    t = e.get("t1_not_tag")
    if t:
        bad = [c.get("name") for c in cands
               if c.get("tier") == "T1" and t in tags_of.get(c.get("name"), ())]
        if bad:
            F.append("чужой кластер %s в T1: %s" % (t, ", ".join(map(str, bad[:3]))))
    # ПОРЯДОК ПО СИЛЕ СОВПАДЕНИЯ. Состав мало что говорит: важно, что точное совпадение стоит
    # выше родственного. Без этой проверки батарея зелёная и при полностью перемешанной выдаче.
    t = e.get("level_order")
    if t and cands:
        exact = [i for i, c in enumerate(cands) if t in tags_of.get(c.get("name"), ())]
        other = [i for i, c in enumerate(cands) if t not in tags_of.get(c.get("name"), ())]
        if exact and other and min(other) < max(exact):
            F.append("родственный выше точного: чужой на %d, свои до %d"
                     % (min(other) + 1, max(exact) + 1))
    # ХАРАКТЕР НЕ ПЕРЕБИВАЕТ РЕЛЕВАНТНОСТЬ. persona_order сортирует ВНУТРИ полосы; если
    # совпавший по характеру поднялся из худшей полосы в лучшую — пожелание стало гейтом.
    if e.get("persona_respects_band") and cands:
        seen, order = [], {}
        for c in cands:
            b = str(c.get("band") or c.get("tier") or "")
            if b not in order:
                order[b] = len(order)
            seen.append(order[b])
        drops = [i for i in range(1, len(seen)) if seen[i] < seen[i - 1]]
        if drops:
            F.append("полоса ухудшилась и вернулась на месте %d (%s)" % (drops[0] + 1, seen[:6]))
    n = e.get("no_clash_top")
    if n and cands:
        # Столкновение наверху — сбой ТОЛЬКО если ниже стоял неконфликтный, которого обошли.
        # Требовать чистой верхушки безусловно нечестно: когда выбирать не из кого, показать
        # конфликтующего правильнее, чем не показать никого.
        mv = str(prof.get("vibe") or "")
        vib = lambda c: str((users.get(c.get("name")) or {}).get("vibe") or "")
        clash = lambda cv: (mv, cv) in CLASH or (cv, mv) in CLASH
        top_bad = [(i, c) for i, c in enumerate(cands[:n]) if clash(vib(c))]
        calm_below = [i for i, c in enumerate(cands) if i >= n and not clash(vib(c))]
        if top_bad and calm_below:
            F.append("конфликтующий на месте %d обошёл неконфликтного с места %d"
                     % (top_bad[0][0] + 1, calm_below[0] + 1))
    # Пожелание по характеру НЕ фильтрует: выдача не имеет права стать короче.
    if e.get("no_shrink") and sc.get("_base_n") is not None:
        if len(cands) < sc["_base_n"]:
            F.append("пожелание сузило выдачу: %d против %d без него" % (len(cands), sc["_base_n"]))
    pl = e.get("persona_lifts")
    if pl and cands:
        axis, tok = pl
        hit = [i for i, c in enumerate(cands)
               if ((users.get(c.get("name")) or {}).get("persona") or {}).get("axes", {}).get(axis) == tok]
        miss = [i for i, c in enumerate(cands)
                if ((users.get(c.get("name")) or {}).get("persona") or {}).get("axes", {}).get(axis)
                not in (None, tok)]
        if hit and miss and min(miss) < min(hit):
            F.append("несовпавший по характеру выше совпавшего (%d против %d)" % (min(miss), min(hit)))
    if e.get("persona_more_hits_first") and cands:
        hits = [int(c.get("persona_hits") or 0) for c in cands]
        drops = [i for i in range(1, len(hits)) if hits[i] > hits[i - 1]]
        if drops:
            F.append("порядок по совпадениям характера нарушен на месте %d (%s)"
                     % (drops[0] + 1, hits[:6]))
    if e.get("none_without_gender"):
        bad = [c.get("name") for c in cands
               if not str((users.get(c.get("name")) or {}).get("gender") or "")]
        if bad:
            F.append("прошли без пола: %s" % ", ".join(map(str, bad[:3])))
    pv = e.get("prefer_vibe")
    if pv and cands:
        same = [i for i, c in enumerate(cands)
                if str((users.get(c.get("name")) or {}).get("vibe") or "") == pv]
        clash = [i for i, c in enumerate(cands)
                 if ((pv, str((users.get(c.get("name")) or {}).get("vibe") or "")) in CLASH
                     or (str((users.get(c.get("name")) or {}).get("vibe") or ""), pv) in CLASH)]
        if same and clash and min(clash) < min(same):
            F.append("чужой характер выше своего (%d против %d)" % (min(clash), min(same)))
    return F


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--show", type=int, default=6)
    a = ap.parse_args()

    os.environ["KLEAL_USERS"] = os.path.abspath(a.pool)
    import app as M

    pool = json.load(open(a.pool, encoding="utf-8"))
    rows = pool.get("users") if isinstance(pool, dict) else pool
    users = {u["name"]: u for u in rows}
    index = json.load(open(a.index, encoding="utf-8"))
    tags_of = collections.defaultdict(set)
    for t, names in index.items():
        for n in names:
            tags_of[n].add(t)

    scs = cases()
    if a.only:
        scs = [s for s in scs if s["axis"].startswith(a.only) or s["id"].startswith(a.only)]
    print("сценариев: %d" % len(scs))

    per = collections.defaultdict(lambda: [0, 0])
    fails, results = [], []
    for sc in scs:
        try:
            # Для проверки «пожелание не сужает» нужен эталон без него — тот же запрос,
            # из которого убрано wantPersona. Считается только там, где проверка заявлена.
            if sc["expect"].get("no_shrink") and sc["intent"].get("wantPersona"):
                base_it = {k: v for k, v in sc["intent"].items() if k != "wantPersona"}
                sc["_base_n"] = len(M.match_candidates(base_it, dict(sc["profile"]),
                                    {"self": sc["profile"]["name"], "uid": "calib", "now": NOW}))
            cands = M.match_candidates(dict(sc["intent"]), dict(sc["profile"]),
                                       {"self": sc["profile"]["name"], "uid": "calib", "now": NOW})
        except Exception as ex:
            cands, F = [], ["ПАДЕНИЕ: %r" % ex]
        else:
            F = judge(sc, cands, users, tags_of, sc["profile"])
        per[sc["axis"]][1] += 1
        if not F:
            per[sc["axis"]][0] += 1
        else:
            fails.append((sc["id"], sc["axis"], F))
        results.append({"id": sc["id"], "axis": sc["axis"], "n": len(cands), "fail": F})

    print()
    print("%-12s %6s %6s  %s" % ("ось", "прошло", "всего", "доля"))
    print("-" * 44)
    tot_ok = tot = 0
    for ax in sorted(per):
        ok, n = per[ax]
        tot_ok += ok; tot += n
        print("%-12s %6d %6d  %5.0f%%" % (ax, ok, n, 100.0 * ok / max(1, n)))
    print("-" * 44)
    print("%-12s %6d %6d  %5.0f%%" % ("ИТОГО", tot_ok, tot, 100.0 * tot_ok / max(1, tot)))

    if fails:
        print("\nсбои по осям (первые %d в каждой):" % a.show)
        by = collections.defaultdict(list)
        for cid, ax, F in fails:
            by[ax].append((cid, F))
        for ax in sorted(by):
            print("  [%s] %d" % (ax, len(by[ax])))
            for cid, F in by[ax][:a.show]:
                print("     %-30s %s" % (cid[:30], "; ".join(F)[:96]))
    if a.json:
        json.dump(results, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
