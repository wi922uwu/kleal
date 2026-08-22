# -*- coding: utf-8 -*-
"""Собрать canonical_extra.json из разобранных предложений — с отсевом всего сомнительного.

Вход: JSON вида {"aliases": [{word,node,why}], "new_nodes": [{id,parent,ru,en,es,words,why}]}.
Выход: matching_core/taxonomy/canonical_extra.json + отчёт, что принято и что отклонено и почему.

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

    rejected = []
    # (1) сгруппировать предложения по id: согласные сливаем, расходящиеся отклоняем целиком
    grouped = {}
    for n in p.get("new_nodes") or []:
        grouped.setdefault(str(n.get("id") or ""), []).append(n)

    nodes, node_words = [], {}
    for nid, group in grouped.items():
        if not re.match(r"^I_[a-z0-9_]{2,40}$", nid):
            rejected.append(("узел", nid, "id не по форме I_snake_case")); continue
        if nid in C.NODES:
            rejected.append(("узел", nid, "такой id уже есть в каноне")); continue
        parents = {str(g.get("parent") or "") for g in group}
        if len(parents) > 1:
            rejected.append(("узел", nid, "родители расходятся: %s" % ", ".join(sorted(parents)))); continue
        par = parents.pop()
        if par not in C.NODES:
            rejected.append(("узел", nid, "родителя '%s' нет в каноне" % par)); continue
        base = next((g for g in group if all(_norm(g.get(k)) for k in ("ru", "en", "es"))), None)
        if base is None:
            rejected.append(("узел", nid, "нет всех трёх переводов")); continue
        nodes.append({"id": nid, "parent": par, "type": base.get("type") or "activity",
                      "domain": base.get("domain") or (C.NODES[par].get("domain") or "social_meet"),
                      "ru": _norm(base["ru"]), "en": _norm(base["en"]), "es": _norm(base["es"])})
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
        if w in by_word and by_word[w] != nid:
            rejected.append(("алиас", w, "конфликт: %s против %s" % (by_word[w], nid))); continue
        if w in by_word:
            continue
        by_word[w] = nid
        aliases.append({"alias": w, "node": nid})

    print("принято: %d узлов, %d алиасов" % (len(nodes), len(aliases)))
    print("отклонено: %d" % len(rejected))
    by_reason = {}
    for kind, what, why in rejected:
        by_reason.setdefault(why.split(":")[0].split("'")[0].strip(), []).append(what)
    for why, items in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        print("   %-44s %3d  напр. %s" % (why[:44], len(items), ", ".join(map(str, items[:4]))[:52]))

    if a.dry_run:
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "aliases": aliases}, f, ensure_ascii=False, indent=1)
    print("\nзаписано: %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
