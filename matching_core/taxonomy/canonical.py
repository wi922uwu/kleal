# -*- coding: utf-8 -*-
"""§6 Каноническая таксономия — загрузка Kleal_Global_Context_Profiles_Intent_Taxonomy_RU_v1
(405 нод · 1249 алиасов ru/en/es · 560 типизированных рёбер · 139 доменных слотов · 65 контекст-профилей).

Извлечено в `canonical_taxonomy.json` (stdlib json, БЕЗ openpyxl в рантайме — проект stdlib-only).
Даёт data-driven: negative-рёбра (`blocked_cross_purpose` → purpose isolation §8.1/§17.2), complementary
(`role_complementarity`/`language_pair`/`team_role`/… → C#16), adjacency (§6/§12), и доменные слоты с
hard/soft + unknown_behavior + compare_operator (§5/§8.1). Аддитивно к seed-графу (не заменяет similarity).
"""
import os
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_JSON = os.path.join(_HERE, "canonical_taxonomy.json")

AVAILABLE = False
NODES = {}                 # node_id -> {parent,type,domain,ru,en,es,family,macro}
_TYPE = {}
_PARENT = {}
ALIAS = {}                 # нормализованный алиас -> node_id
ADJACENT = {}              # node_id -> set(соседей) из adjacent-рёбер
COMPLEMENTARY = set()      # {(node_a, node_b)} из role/pair-рёбер (симметрично)
BLOCKED_NODES = set()      # {(family_a, family_b)} из blocked_cross_purpose
SLOTS_BY_DOMAIN = {}       # domain -> [slot spec, ...]
FAMILY_PURPOSE = {}        # family_id -> purpose (из контекст-профилей)
PURPOSE_BLOCKS = set()     # {(purpose_a, purpose_b)} выведено из blocked_cross_purpose
_COMPLEMENT_RELS = {"role_complementarity", "language_pair", "team_role", "game_role",
                    "slot_complementarity", "project_role"}


def _norm(s):
    return str(s or "").strip().lower().replace(" ", "")


def _load():
    global AVAILABLE
    try:
        data = json.load(open(_JSON, encoding="utf-8"))
    except Exception:
        AVAILABLE = False
        return
    for n in data.get("nodes", []):
        NODES[n["id"]] = n
        _TYPE[n["id"]] = n.get("type")
        if n.get("parent"):
            _PARENT[n["id"]] = n["parent"]
    # ancestors -> family/macro на каждой ноде
    for nid, n in NODES.items():
        n["family"] = _ancestor(nid, "family")
        n["macro"] = _ancestor(nid, "macro")
    for a in data.get("aliases", []):
        ALIAS[_norm(a["alias"])] = a["node"]
    for nid, n in NODES.items():
        for key in ("en", "ru", "es"):
            if n.get(key):
                ALIAS.setdefault(_norm(n[key]), nid)
    for e in data.get("edges", []):
        rel, s, d = e.get("rel"), e.get("src"), e.get("dst")
        if rel == "adjacent":
            ADJACENT.setdefault(s, set()).add(d)
            ADJACENT.setdefault(d, set()).add(s)
        elif rel == "blocked_cross_purpose":
            BLOCKED_NODES.add((s, d))
        elif rel in _COMPLEMENT_RELS:
            COMPLEMENTARY.add((s, d)); COMPLEMENTARY.add((d, s))
    for s in data.get("slots", []):
        SLOTS_BY_DOMAIN.setdefault(s.get("domain"), []).append(s)
    for p in data.get("profiles", []):
        if p.get("family") and p.get("purpose"):
            for fam in str(p["family"]).split("|"):
                FAMILY_PURPOSE.setdefault(_bare(fam.strip()), p["purpose"])
    # purpose-blocks из family-blocks (профили дают bare-family 'casual_social', ноды — 'F_casual_social')
    for (a, b) in BLOCKED_NODES:
        pa, pb = FAMILY_PURPOSE.get(_bare(_family_id(a))), FAMILY_PURPOSE.get(_bare(_family_id(b)))
        if pa and pb and pa != pb:
            PURPOSE_BLOCKS.add((pa, pb)); PURPOSE_BLOCKS.add((pb, pa))
    AVAILABLE = True


def _bare(x):
    return x[2:] if x and str(x).startswith("F_") else x


def _ancestor(nid, want_type):
    cur, seen = nid, set()
    while cur and cur not in seen:
        seen.add(cur)
        if _TYPE.get(cur) == want_type:
            return cur
        cur = _PARENT.get(cur)
    return None


def _family_id(nid):
    return _ancestor(nid, "family") or nid


# --------------------------------------------------------------- публичный API
def resolve_node(text):
    """Строка интереса/темы -> node_id: точный алиас, затем СТРОГИЙ морфологический префикс.
    review#A: короткие алиасы (len<5: 'remo','surf','lol') больше НЕ матчат несвязанные длинные слова
    ('remote'→rowing, 'surface'→surfing, 'lollipop'→league) — иначе canonical давал ложный EXACT (уровень 4)."""
    w = _norm(text)
    if w in ALIAS:
        return ALIAS[w]                                       # точный алиас
    for alias, nid in ALIAS.items():
        if len(alias) >= 5 and len(w) >= 4 and (alias.startswith(w) or w.startswith(alias)):
            return nid                                        # морфологический вариант (оба достаточно длинные)
    return None


def similarity_nodes(a_text, b_text):
    """Уровень близости по КАНОНИЧЕСКОЙ иерархии: 4 exact, 3 sibling(family), 2 parent(macro), 1 adjacent, 0."""
    na, nb = resolve_node(a_text), resolve_node(b_text)
    if not na or not nb:
        return None                      # не резолвится в каноне -> пусть решает seed-граф
    if na == nb:
        return 4
    if NODES[na].get("family") and NODES[na]["family"] == NODES[nb].get("family"):
        return 3
    if NODES[na].get("macro") and NODES[na]["macro"] == NODES[nb].get("macro"):
        return 2
    if nb in ADJACENT.get(na, set()) or na in ADJACENT.get(nb, set()):
        return 1
    return 0


def purpose_blocked(purpose_a, purpose_b):
    """§8.1/§17.2: разные purpose с blocked_cross_purpose ребром нельзя смешивать."""
    return (str(purpose_a), str(purpose_b)) in PURPOSE_BLOCKS


def is_complementary_nodes(a_text, b_text):
    """§6/C#16: complementary по каноническим ребрам (language_pair/role_complementarity/…)."""
    na, nb = resolve_node(a_text), resolve_node(b_text)
    return bool(na and nb and ((na, nb) in COMPLEMENTARY or (nb, na) in COMPLEMENTARY))


def slots_for_domain(domain):
    return SLOTS_BY_DOMAIN.get(domain, [])


def slot_spec(domain, slot_name):
    for s in SLOTS_BY_DOMAIN.get(domain, []):
        if s.get("slot") == slot_name:
            return s
    return None


def hard_slots(domain):
    return [s for s in SLOTS_BY_DOMAIN.get(domain, []) if s.get("imp") == "hard"]


_load()
