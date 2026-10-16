# -*- coding: utf-8 -*-
"""Собрать canonical_extra.json из разобранных предложений — с отсевом всего сомнительного.

Вход: JSON вида {"aliases": [{word,node,why}], "new_nodes": [{id,parent,ru,en,es,words,why}]}.
Выход: matching_core/taxonomy/canonical_extra.json + отчёт, что принято и что отклонено и почему.

СЛИЯНИЕ, А НЕ ПЕРЕЗАПИСЬ. Принятое ДОПИСЫВАЕТСЯ к тому, что уже лежит в canonical_extra.json:
прежние узлы и алиасы остаются на месте байт в байт и в прежнем порядке, новые идут в конец.
Раньше файл переписывался целиком одними предложениями из входа — прогон на копии превратил
53 узла и 409 алиасов в 7 и 14, то есть молча стёр всё, что было добавлено до того. Повторный
прогон тех же предложений ничего не меняет: узлы уже есть, слова уже резолвятся.

Родитель может быть и НОВЫМ узлом из того же входа (новая семья и её дети), если он стоит в
списке раньше детей: при загрузке узлы клеятся по порядку, и висячий родитель был бы отброшен.

ЧТО ОТКЛОНЯЕТСЯ, И ПОЧЕМУ ИМЕННО ЭТО:

  занятое имя         алиас, чьё слово УЖЕ резолвится в каноне. Перебить его значит переставить
                      чужие пары, посчитанные до нас, — ровно то, от чего сторож и заведён.
  чужой родитель      родителя нет в каноне: `_ancestor` уйдёт в никуда, узел останется без семьи
                      и соседства, то есть бесполезным и незаметно.
  дубль id            два предложения на один id С РАЗНЫМИ родителями: чей родитель верен — неясно,
                      а молча победил бы последний. Если родители СОВПАДАЮТ, предложения сливаются
                      и слова объединяются: разные разборщики дошли до одного понятия независимо,
                      это подтверждение, а не конфликт.
  слово-понятие       market/business/product/language/group и прочие: они льстят любому запросу
                      своей области и уже причиняли вред (см. tools/strip_generic_handles.py).
  короткое слово      меньше трёх букв — склеит что угодно.
  конфликт            одно и то же слово ведёт в разные узлы у разных разборщиков.
  занятое имя узла    ru/en/es нового узла уже точно резолвится в другой узел: при загрузке имя
                      молча осталось бы за старым (ALIAS.setdefault), и узел был бы недостижим.

    python3 tools/apply_taxonomy_extra.py предложения.json [--dry-run]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from matching_core.taxonomy import canonical as C  # noqa: E402

OUT = os.path.join(ROOT, "matching_core", "taxonomy", "canonical_extra.json")

# Слова-понятия: см. стоп-лист в onboarding/_canon_interests и tools/strip_generic_handles.py.
BANNED = {
    "market", "business", "product", "language", "group", "talk", "quiet", "trip", "job",
    "activity", "activities", "hobby", "social", "people", "event", "events", "thing", "things",
    "meeting", "meetup", "session", "practice", "club", "community", "culture", "lifestyle",
    "experience", "weekend", "morning", "evening", "night", "day", "time", "place", "fun",
    "exchange", "care", "support", "help", "work", "study", "food", "drink", "drinks", "sport",
    "sports", "game", "games", "art", "music", "health", "wellness", "science", "technology",
}


def _norm(s):
    return " ".join(str(s or "").strip().lower().split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("proposals")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(a.proposals, encoding="utf-8") as f:
        p = json.load(f)

    existing = {"nodes": [], "aliases": []}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            existing = json.load(f)
    existing.setdefault("nodes", [])
    existing.setdefault("aliases", [])

    rejected = []
    # (1) сгруппировать предложения по id: согласные сливаем, расходящиеся отклоняем целиком
    grouped = {}
    for n in p.get("new_nodes") or []:
        grouped.setdefault(str(n.get("id") or ""), []).append(n)

    nodes, node_words, new_by_id, new_names = [], {}, {}, {}
    for nid, group in grouped.items():
        if not re.match(r"^I_[a-z0-9_]{2,40}$", nid) and not re.match(r"^F_[a-z0-9_]{2,40}$", nid):
            rejected.append(("узел", nid, "id не по форме I_snake_case")); continue
        if nid.startswith("F_") != any(str(g.get("type") or "") == "family" for g in group):
            rejected.append(("узел", nid, "семья — это id F_ и type family, одно без другого нельзя")); continue
        if nid in C.NODES:
            rejected.append(("узел", nid, "такой id уже есть в каноне")); continue
        parents = {str(g.get("parent") or "") for g in group}
        if len(parents) > 1:
            rejected.append(("узел", nid, "родители расходятся: %s" % ", ".join(sorted(parents)))); continue
        par = parents.pop()
        if par not in C.NODES and par not in new_by_id:
            rejected.append(("узел", nid, "родителя '%s' нет в каноне" % par)); continue
        base = next((g for g in group if all(_norm(g.get(k)) for k in ("ru", "en", "es"))), None)
        if base is None:
            rejected.append(("узел", nid, "нет всех трёх переводов")); continue
        taken = sorted({"%s->%s" % (_norm(base[k]), C._resolve(base[k])[0]) for k in ("ru", "en", "es")
                        if C._resolve(base[k])[1]}
                       | {"%s->%s" % (_norm(base[k]), new_names[C._norm(base[k])]) for k in ("ru", "en", "es")
                          if new_names.get(C._norm(base[k]), nid) != nid})
        if taken:
            rejected.append(("узел", nid, "имя узла занято: %s" % ", ".join(taken))); continue
        pnode = C.NODES.get(par) or new_by_id.get(par) or {}
        node = {"id": nid, "parent": par, "type": base.get("type") or "activity",
                "domain": base.get("domain") or (pnode.get("domain") or "social_meet"),
                "ru": _norm(base["ru"]), "en": _norm(base["en"]), "es": _norm(base["es"])}
        nodes.append(node)
        new_by_id[nid] = node
        for k in ("ru", "en", "es"):
            new_names.setdefault(C._norm(node[k]), nid)
        seen = []
        for g in group:                       # слова всех согласных предложений, без повторов
            for w in (g.get("words") or []):
                if _norm(w) and _norm(w) not in seen:
                    seen.append(_norm(w))
        node_words[nid] = seen

    # (2) слова новых узлов идут алиасами к ним же
    pending = [(w, nid) for nid, ws in node_words.items() for w in ws]
    pending += [(al.get("word"), al.get("node")) for al in (p.get("aliases") or [])]

    aliases, by_word = [], {}
    for w, nid in pending:
        w = _norm(w)
        if not w or not nid:
            continue
        if nid not in C.NODES and nid not in node_words:
            rejected.append(("алиас", w, "узла '%s' нет" % nid)); continue
        if len(w) < 3:
            rejected.append(("алиас", w, "слишком короткое слово")); continue
        if w in BANNED:
            rejected.append(("алиас", w, "слово-понятие: польстит всей области")); continue
        if C.resolve_node(w):
            rejected.append(("алиас", w, "уже резолвится в %s — не перебиваем" % C.resolve_node(w))); continue
        key = C._norm(w)                      # канон сравнивает без пробелов: «paddle board» = «paddleboard»
        if new_names.get(key, nid) != nid:
            rejected.append(("алиас", w, "имя нового узла %s" % new_names[key])); continue
        if key in by_word and by_word[key] != nid:
            rejected.append(("алиас", w, "конфликт: %s против %s" % (by_word[key], nid))); continue
        if key in by_word or new_names.get(key) == nid:
            continue                          # дубль или собственное имя узла — уже будет в ALIAS
        by_word[key] = nid
        aliases.append({"alias": w, "node": nid})

    print("в файле было: %d узлов, %d алиасов" % (len(existing["nodes"]), len(existing["aliases"])))
    print("принято: %d узлов, %d алиасов" % (len(nodes), len(aliases)))
    print("отклонено: %d" % len(rejected))
    by_reason = {}
    for kind, what, why in rejected:
        by_reason.setdefault(why.split(":")[0].split("'")[0].strip(), []).append(what)
    for why, items in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        print("   %-44s %3d  напр. %s" % (why[:44], len(items), ", ".join(map(str, items[:4]))[:52]))

    # СЛИЯНИЕ: прежнее содержимое целиком и в прежнем порядке, новое — в конец.
    have_ids = {n.get("id") for n in existing["nodes"]}
    have_words = {C._norm(x.get("alias")) for x in existing["aliases"]}
    merged = dict(existing)
    merged["nodes"] = list(existing["nodes"]) + [n for n in nodes if n["id"] not in have_ids]
    merged["aliases"] = list(existing["aliases"]) + [x for x in aliases if C._norm(x["alias"]) not in have_words]
    print("станет: %d узлов, %d алиасов" % (len(merged["nodes"]), len(merged["aliases"])))
    if a.dry_run:
        return 0
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, OUT)                      # атомарно: файл читается при каждом импорте канона
    print("\nзаписано: %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
