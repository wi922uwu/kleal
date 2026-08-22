# -*- coding: utf-8 -*-
"""Give every stored interest an English handle the ranker can actually resolve.

The search side canonicalises: «пойти на senderismo» becomes hiking/outdoor/trail before matching
sees it. The CANDIDATE side never did — a person whose interest is literally "senderismo" or
«настолки» stayed invisible to exactly the search that was looking for them, because the ranker
resolves topics against an English taxonomy and matches the rest by literal word overlap.

This walks the shared store and APPENDS filtration's canonical English topics to each row, keeping
the person's own wording first: it is what their card shows, and it is the only handle a novel
interest ("labubu", "kintsugi") ever gets. Nothing is replaced and nothing is invented — an
interest filtration cannot place simply gains nothing.

Idempotent: re-running adds no duplicates. Safe to run against a live store (atomic replace).

  python3 tools/canonicalise_interests.py            # enrich in place
  python3 tools/canonicalise_interests.py --dry-run  # show what would change
"""
import concurrent.futures as cf
import json
import os
import sys
import urllib.request

FILTER_URL = os.environ.get("FILTER_URL", "http://127.0.0.1:7076") + "/api/filter/categorize"
USERS_PATH = os.environ.get(
    "KLEAL_USERS", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "users.json"))
MAX_INTERESTS = 8          # the row is read by the ranker; a bag of twenty dilutes every signal

# Concept-level words filtration hands back alongside the real answer. They are true but useless to
# match on: give everyone "sport" and everyone matches everyone.
GENERIC = {
    "sport", "sports", "exercise", "activity", "activities", "hobby", "hobbies", "fun", "leisure",
    "beverage", "drink", "drinks", "food", "social", "socializing", "socialising", "people",
    "meeting", "meetup", "friends", "community", "culture", "tradition", "lifestyle", "wellness",
    "entertainment", "game", "games", "play", "event", "events", "experience", "outdoor activities",
    "health", "art",  # 'art' is real but filtration attaches it to everything visual
    # Вторая волна: концептуальные слова, ускользнувшие от списка выше, — найдены по живой жалобе
    # («Акции» приводили гастрорынок первым тиром через дописанное обоим голое `market`).
    "market", "talk", "quiet", "business", "product", "trip", "language",
}


def canon(text, timeout=30):
    """Filtration's canonical topics for one raw interest, minus the generic filler."""
    try:
        req = urllib.request.Request(FILTER_URL, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
    except Exception:
        return []
    out = []
    for t in (d.get("topics") or []):
        w = str(t).strip().lower()
        if w and w not in GENERIC and w != str(text).strip().lower() and w not in out:
            out.append(w)
    return out[:3]


def main():
    dry = "--dry-run" in sys.argv
    with open(USERS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    users = data.get("users") if isinstance(data, dict) else data
    if not isinstance(users, list) or not users:
        print("store is empty — nothing to do")
        return

    uniq = sorted({str(w).strip().lower() for u in users for w in (u.get("interests") or []) if str(w).strip()})
    print("людей: %d | уникальных интересов: %d" % (len(users), len(uniq)))

    # One lookup per DISTINCT interest, not per person — filtration also caches confident answers.
    table = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for w, got in zip(uniq, ex.map(canon, uniq)):
            table[w] = got

    placed = sum(1 for w in uniq if table[w])
    print("канон найден для: %d/%d" % (placed, len(uniq)))

    changed = 0
    for u in users:
        cur = [str(w).strip() for w in (u.get("interests") or []) if str(w).strip()]
        low = {w.lower() for w in cur}
        # Round-robin: every interest gets its first English handle before any gets a second one.
        # Filling interest-by-interest let the cap eat the last one's handle entirely.
        add = []
        lists = [table.get(w.lower(), []) for w in cur]
        for depth in range(3):
            for lst in lists:
                if len(cur) + len(add) >= MAX_INTERESTS:
                    break
                if depth < len(lst) and lst[depth] not in low and lst[depth] not in add:
                    add.append(lst[depth])
        if not add:
            continue
        u["interests"] = (cur + add)[:MAX_INTERESTS]
        changed += 1

    print("обогащено строк: %d" % changed)
    if dry:
        for u in users[:5]:
            print("  ", u.get("name"), "->", u.get("interests"))
        return
    tmp = USERS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False)
    os.replace(tmp, USERS_PATH)
    print("записано в", USERS_PATH)


if __name__ == "__main__":
    main()
