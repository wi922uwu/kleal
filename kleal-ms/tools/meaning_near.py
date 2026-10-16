# -*- coding: utf-8 -*-
"""БЛИЗКИЕ ПО СМЫСЛУ: для каждого слова, которое ищут, — ближайшие по смыслу интересы людей (bge-m3 на поде).

Зачем (02.10.2026): поиск знает слово только через словарь (канон + карта догадок). Незнакомое занятие —
«электроника», «паяльник», «попыт» — ни на кого не похоже, и человек не находит никого. Здесь каждое такое слово
заранее сравнивается по смыслу со ВСЕМИ интересами людей (их ~1,5 тыс. разных), и поиск читает готовый файл:
сам он в сеть не ходит. Слово появляется -> через ≤1 мин у него есть соседи.

Файл /var/lib/kleal/meaning_near.json (KLEAL_NEAR_FILE):
  "near": {слово: [[интерес, сходство], ...]} — до K соседей по векторам, без порога (порядок последней ступени);
  "ok":   {слово: [интерес, ...]} — из 25 ближайших языковая модель отобрала те, с кем правда стоит встретиться.
Векторы одни путаются («electronics» -> электронная музыка, «pizza» -> piano; замер 30.09: 50% верно), выбор модели
из 25 — 73%. Поэтому ступень «близко по смыслу» (уровень 1) берёт только "ok", и только для слов, которых не знают
ни канон, ни карта догадок: известные слова решает прежняя лестница.

    python3 tools/meaning_near.py [--root=...] [--full] [--words=a|b]
Слова: интересы людей, ключи реестра (tree + extended), чипы карточек Буди из журнала (10 мин; --full — с 24.09),
слова карты догадок. Интересы людей сменились -> пересчёт всех слов (пачками), иначе только новые.
Свидания, наркотики и зонтики не считаются никогда (tools/concept_guess.never).
"""
import fcntl, hashlib, io, json, os, re, subprocess, sys, time

ROOT = os.environ.get("KLEAL_ROOT") or "/opt/kleal/kleal-ms"
FULL, ONLY, K, ASK_LIMIT, FIRST = False, None, 40, 60, None
for a in sys.argv[1:]:
    if a.startswith("--root="):
        ROOT = a.split("=", 1)[1]
    elif a == "--full":
        FULL = True
    elif a.startswith("--ask-limit="):               # сколько слов отбирать моделью за прогон (таймер — раз в минуту)
        ASK_LIMIT = int(a.split("=", 1)[1])
    elif a.startswith("--first="):                   # файл со словами (через |), которые отбирать в первую очередь
        FIRST = a.split("=", 1)[1]
    elif a.startswith("--words="):                    # добавить слова к источникам (проверка, пробы)
        ONLY = [x.strip() for x in a.split("=", 1)[1].split("|") if x.strip()]
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))
from matching_core.taxonomy import canonical as C  # noqa: E402

OUT = os.environ.get("KLEAL_NEAR_FILE") or "/var/lib/kleal/meaning_near.json"
GUESS = os.environ.get("KLEAL_GUESS_FILE") or "/var/lib/kleal/canonical_guess.json"
BASE = os.environ.get("KLEAL_MEANING_URL") or "http://127.0.0.1:17078"

_BAN = re.compile(r"свидан|романт|флирт|секс|интим|\bdat(e|es|ing)\b|romanc|flirt|\bsex(?!tet)|hook ?up|одн(у|ой|а) ноч|"
                  r"\bone night\b|\bfwb\b|nudes|porn|\bcitas?\b|наркот|травк|марихуан|кокаин|закладк|\bdrugs?\b|"
                  r"\bweed\b|cannabis|cocaine|\bdrogas?\b|\bporros?\b", re.I)


def banned(w):
    return bool(_BAN.search(w or ""))


def call(path, body, wait=60):
    import urllib.request
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=wait))


def people_vocab():
    import db
    v = {}
    for u in db.load_users() or []:
        for i in (u.get("interests") or []) if isinstance(u, dict) else []:
            s = str(i or "").strip()
            k = C._norm(s)
            if k and len(k) >= 2 and not banned(s):
                v.setdefault(k, s)
    return v


def query_words(pv):
    out = dict(pv)                                   # человек ищет и то, что у других в анкете

    def add(w):
        w = str(w or "").strip()
        k = C._norm(w)
        if k and 2 <= len(k) <= 60 and not banned(w):
            out.setdefault(k, w)
    try:
        reg = json.load(io.open(os.path.join(ROOT, "shared", "interests.json"), encoding="utf-8"))

        def walk(x):
            if isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    add(v) if isinstance(v, str) else walk(v)
        walk(reg.get("tree") or {}); walk(reg.get("extended") or {})
    except Exception as e:
        print("реестр не прочитался:", str(e)[:100])
    try:
        for v in (json.load(io.open(GUESS, encoding="utf-8")).get("words") or {}).values():
            add(v.get("text"))
    except Exception:
        pass
    since = "2026-09-24" if FULL else "-10 min"
    try:
        log = subprocess.run(["journalctl", "-u", "kleal@buddy", "--since", since, "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=120).stdout
    except Exception:
        log = ""
    for line in log.splitlines():
        m = re.search(r"\[v2\] /\S+ .*?чипы=(\[[^\]]*\])", line)
        if m:
            try:
                for c in json.loads(m.group(1).replace("'", '"')):
                    add(c)
            except Exception:
                pass
    return out


_ASK = ("Someone wants to do «%s» with other people.\n"
        "Below are interests that other people listed. Which of them are close enough that the two would enjoy meeting "
        "over it — the same activity or a closely related one (electronics ~ robotics, soldering, computers; skydiving ~ "
        "paragliding, climbing)? Do NOT pick things that only share a word, a sound or a setting (electronics is not "
        "electronic music, pizza is not piano). Answer with the numbers, comma separated, or NONE.\n\n%s")


def approve(word, cands, ask):
    lines = "\n".join("%d. %s" % (i + 1, c) for i, c in enumerate(cands))
    a = ask("You match hobbies between people.", _ASK % (word, lines))
    if re.search(r"\bNONE\b", a) and not re.search(r"\d", a):
        return []
    out = []
    for n in re.findall(r"\b(\d{1,2})\b", a):
        i = int(n) - 1
        if 0 <= i < len(cands) and cands[i] not in out:
            out.append(cands[i])
    return out


def unknown(w):
    try:
        return C._resolve(w)[0] is None and not C.guess_node(w)
    except Exception:
        return False


def load():
    try:
        d = json.load(io.open(OUT, encoding="utf-8"))
        d.setdefault("near", {})
        return d
    except Exception:
        return {"version": 1, "near": {}, "people": ""}


def save(d):
    tmp = OUT + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, OUT)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    lock = open(OUT + ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("уже идёт другой прогон"); return 0
    d = load()
    pv = people_vocab()
    keys = sorted(pv)
    sig = hashlib.md5("\n".join(keys).encode("utf-8")).hexdigest()
    qw = query_words(pv)
    first_words = [w.strip() for w in io.open(FIRST, encoding="utf-8").read().split("|") if w.strip()] if FIRST else []
    for w in (ONLY or []) + first_words:
        if not banned(w):
            qw.setdefault(C._norm(w), w)
    redo = sig != d.get("people")
    todo = sorted(qw) if redo else sorted(k for k in qw if k not in d["near"])
    near = {} if redo else d["near"]
    if todo:
        name = "people-" + sig[:16]
        texts = [pv[k] for k in keys]
        t0 = time.time()
        for attempt in (0, 1):
            try:
                call("/nearest", {"index": name, "queries": ["x"], "k": 1}, wait=30)
                break
            except Exception as e:
                if attempt or getattr(e, "code", None) != 404:
                    print("смысл недоступен:", str(e)[:120]); return 1
                call("/index", {"name": name, "candidates": texts}, wait=600)
        for i in range(0, len(todo), 200):
            part = todo[i:i + 200]
            hits = call("/nearest", {"index": name, "queries": [qw[k] for k in part], "k": K}, wait=300)["hits"]
            for k, hs in zip(part, hits):
                near[k] = [[keys[int(j)], round(float(s), 3)] for j, s in hs if keys[int(j)] != k]
        if redo:
            for k, v in d["near"].items():            # слова, которых сейчас нет в источниках, не теряем —
                near.setdefault(k, v)                   # пересчитаются при следующей смене людей
        d["near"], d["people"], d["at"] = near, sig, time.strftime("%FT%TZ", time.gmtime())
        save(d)
        print("векторы: слов %d за %.0f с; в файле %d, интересов людей %d" % (len(todo), time.time() - t0, len(near), len(keys)))
    # отбор моделью — только для незнакомых поиску слов; переспрос, если в 25 ближайших появилось новое
    import config, llm_client
    model = getattr(config, "MODEL_ID", None)

    def ask(system, user):
        return llm_client.llm_complete(model, [{"role": "system", "content": system},
                                               {"role": "user", "content": user}], temperature=0.0, tag="meaning_near") or ""
    ok, asked = d.setdefault("ok", {}), d.setdefault("asked", {})
    n, t1 = 0, time.time()
    first = [C._norm(w) for w in first_words + (ONLY or [])]
    for k in [x for x in first if x in qw] + sorted(qw):
        if n >= ASK_LIMIT:
            break
        top = [x for x, _ in near.get(k, [])[:25]]
        if not top or not unknown(qw[k]) or (k in asked and set(top[:10]) <= set(asked[k])):
            continue
        try:
            ok[k] = approve(qw[k], [pv.get(x, x) for x in top], ask)
        except Exception as e:
            print("модель не ответила:", str(e)[:100]); break
        ok[k] = [C._norm(x) for x in ok[k]]
        asked[k] = top
        n += 1
        if n % 50 == 0:
            save(d)
    save(d)
    print("отбор моделью: слов %d за %.0f с; с соседями %d" % (n, time.time() - t1, sum(1 for v in ok.values() if v)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
