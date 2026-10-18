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

С 02.10.2026 (вторая версия) сравниваются ОПРЕДЕЛЕНИЯ, а не слова: модель один раз пишет каждому слову и каждому
интересу людей, что это («pop-it: toy, silicone bubbles to press», «electronic club: dance music night») — созвучия
(«электроника» ~ electronic music, «таро» ~ tai chi, «попыт» ~ practice) расходятся. Ещё:
  "grade": {слово: {интерес: 3|2}} — сила близости от модели (3 почти то же, 2 родственное); "ok" = её ключи;
  "branch": {слово: M_*} — «тот же мир» для слов без близких: один из разделов канона (бонсай -> природа).
  "defs":  {слово или интерес: определение}.

    python3 tools/meaning_near.py [--root=...] [--full] [--words=a|b]
Слова: интересы людей, ключи реестра (tree + extended), чипы карточек Буди из журнала (10 мин; --full — с 24.09),
слова карты догадок. Интересы людей сменились -> пересчёт всех слов (пачками), иначе только новые.
Свидания, наркотики и зонтики не считаются никогда (tools/concept_guess.never).
"""
import fcntl, hashlib, io, json, os, re, subprocess, sys, time

ROOT = os.environ.get("KLEAL_ROOT") or "/opt/kleal/kleal-ms"
FULL, ONLY, K, ASK_LIMIT, FIRST, DEF_LIMIT = False, None, 40, 60, None, 400
for a in sys.argv[1:]:
    if a.startswith("--root="):
        ROOT = a.split("=", 1)[1]
    elif a == "--full":
        FULL = True
    elif a.startswith("--def-limit="):               # сколько определений писать за прогон
        DEF_LIMIT = int(a.split("=", 1)[1])
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


_DEF = ("For each item a person listed as an interest or something they like to do, write in plain English what it is, "
        "at most 10 words, starting with the kind of thing (sport:, game:, toy:, craft:, music genre:, food:, drink:, "
        "place:, tech:, practice:, topic:, other:). Keep slang and brand meaning (pop-it is a toy, Arduino is electronics "
        "boards, tarot is card reading). If unsure, write UNKNOWN.\nAnswer exactly one line per item: <number>. <text>\n\n%s")

_ASK = ("Someone wants to do «%s» (%s) with other people.\n"
        "Below are interests other people listed, with what each is. Rate the ones worth meeting over:\n"
        "3 = the same activity or practically the same;\n"
        "2 = a closely related activity — the two would enjoy doing it together (electronics ~ robotics, soldering, "
        "computer hardware; skydiving ~ paragliding, base jumping);\n"
        "skip everything else, ESPECIALLY things that only share a word, a sound or a setting (electronics is not "
        "electronic music, tarot is not tai chi, pop-it is not practice).\n"
        "Answer as number:grade, comma separated (like 4:3, 9:2), or NONE.\n\n%s")

_BRANCH = ("Someone wants to do «%s» (%s) with other people. Which ONE of these areas is it part of? Answer with the id, "
           "or NONE if it is not an activity people share, or it is about dating, sex or drugs.\n\n%s")


def defs_for(words, ask):
    """{слово: определение} пачками по 25; UNKNOWN -> пустая строка (сравнивается само слово)."""
    out = {}
    for i in range(0, len(words), 25):
        part = words[i:i + 25]
        a = ask("You explain hobbies and interests briefly.",
                _DEF % "\n".join("%d. %s" % (n + 1, w) for n, w in enumerate(part)))
        for line in a.splitlines():
            m = re.match(r"\s*(\d{1,2})\.\s*(.+)$", line)
            if m and 1 <= int(m.group(1)) <= len(part):
                t = m.group(2).strip()
                out[part[int(m.group(1)) - 1]] = "" if "UNKNOWN" in t.upper() else t[:120]
    return out


def approve(word, wdef, cands, ask):
    """-> {кандидат: 3|2}"""
    lines = "\n".join("%d. %s — %s" % (i + 1, c, dd or "?") for i, (c, dd) in enumerate(cands))
    a = ask("You match hobbies between people.", _ASK % (word, wdef or word, lines))
    out = {}
    for n, g in re.findall(r"\b(\d{1,2})\s*:\s*([23])\b", a):
        i = int(n) - 1
        if 0 <= i < len(cands):
            out[cands[i][0]] = max(out.get(cands[i][0], 0), int(g))
    return out


_VERIFY = ("Someone loves «%s» (%s). Below are people's interests that were suggested as close to it.\n"
           "Keep ONLY those where the two people would genuinely enjoy meeting to do or talk about THIS activity together. "
           "Reject anything that merely shares a broad area (water, money, crafts, sport, tech, outdoors), a material, "
           "a tool, a word or a sound (aquarium is not swimming, coins are not finance, juggling is not pottery).\n"
           "Answer with the numbers to keep, comma separated, or NONE.\n\n%s")


def verify(word, wdef, graded, defs_of, ask):
    """Вторая проверка отобранного: отборщик щедр на «родственное» (аквариум ~ плавание, нумизматика ~ финансы)."""
    items = sorted(graded, key=lambda x: -graded[x])
    if not items:
        return {}
    lines = "\n".join("%d. %s — %s" % (i + 1, x, defs_of(x) or "?") for i, x in enumerate(items))
    a = ask("You check hobby matches strictly.", _VERIFY % (word, wdef or word, lines))
    if re.search(r"\bNONE\b", a) and not re.search(r"\d", a):
        return {}
    keep = {items[int(n) - 1] for n in re.findall(r"\b(\d{1,2})\b", a) if 1 <= int(n) <= len(items)}
    return {x: g for x, g in graded.items() if x in keep}


def pick_branch(word, wdef, ask):
    N = C.NODES
    ms = [m for m in N if m.startswith("M_") and m != "M_dating"]
    lst = "\n".join("%s — %s: %s" % (m, N[m].get("en"), ", ".join(N[f].get("en") or "" for f in N
                     if f.startswith("F_") and N[f].get("macro") == m)) for m in ms)
    a = ask("You sort activities into areas.", _BRANCH % (word, wdef or word, lst))
    got = [x for x in re.findall(r"\b(M_[a-z_]+)\b", a) if x in ms]
    return got[0] if got and not re.search(r"\bNONE\b", a) else None


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
    d.setdefault("defs", {}); d.setdefault("ok", {}); d.setdefault("grade", {}); d.setdefault("branch", {})
    d.setdefault("asked", {})
    if d.get("v") != 3:                               # прежние версии сравнивали иначе — векторы и отбор заново
        d.update({"v": 3, "near": {}, "ok": {}, "grade": {}, "branch": {}, "asked": {}, "people": ""})
    pv = people_vocab()
    keys = sorted(pv)
    qw = query_words(pv)
    first_words = [w.strip() for w in io.open(FIRST, encoding="utf-8").read().split("|") if w.strip()] if FIRST else []
    for w in (ONLY or []) + first_words:
        if not banned(w):
            qw.setdefault(C._norm(w), w)
    first = [C._norm(w) for w in first_words + (ONLY or [])]
    import config, llm_client
    model = getattr(config, "MODEL_ID", None)

    def ask(system, user):
        return llm_client.llm_complete(model, [{"role": "system", "content": system},
                                               {"role": "user", "content": user}], temperature=0.0, tag="meaning_near") or ""
    defs = d["defs"]
    # 1) определения: сначала интересы людей (без них индекс неполон), потом важные слова, потом остальные
    need = [k for k in keys if k not in defs]
    need += [k for k in first if k in qw and k not in defs and k not in need]
    need += [k for k in sorted(qw) if k not in defs and k not in need]
    need = need[:DEF_LIMIT] if [k for k in keys if k not in defs] == [] else need[:max(DEF_LIMIT, len([k for k in keys if k not in defs]))]
    t0 = time.time()
    if need:
        txt = {k: (pv.get(k) or qw.get(k) or k) for k in need}
        got = defs_for([txt[k] for k in need], ask)
        for k in need:
            defs[k] = got.get(txt[k], "")
        save(d)
        print("определения: %d за %.0f с (всего %d)" % (len(need), time.time() - t0, len(defs)))
    if any(k not in defs for k in keys):
        print("определения интересов людей ещё не готовы — векторы в следующий прогон"); return 0
    # В векторы — само слово и суть определения БЕЗ пометки вида: «practice: beekeeping» тянуло «apicultura» к
    # «práctica», «toy:» — к игрушкам вообще. Пометка остаётся отборщику.
    body = lambda dd: re.sub(r"^[a-z][a-z /-]{1,20}:\s*", "", dd or "").strip()
    text = lambda k, raw: ("%s: %s" % (raw, body(defs[k]))) if body(defs.get(k)) else raw
    sig = hashlib.md5("\n".join(text(k, pv[k]) for k in keys).encode("utf-8")).hexdigest()
    ready = [k for k in qw if k in defs]
    redo = sig != d.get("people")
    todo = sorted(ready) if redo else sorted(k for k in ready if k not in d["near"])
    near = {} if redo else d["near"]
    if todo:
        name = "pdef-" + sig[:16]
        t0 = time.time()
        for attempt in (0, 1):
            try:
                call("/nearest", {"index": name, "queries": ["x"], "k": 1}, wait=30)
                break
            except Exception as e:
                if attempt or getattr(e, "code", None) != 404:
                    print("смысл недоступен:", str(e)[:120]); return 1
                call("/index", {"name": name, "candidates": [text(k, pv[k]) for k in keys]}, wait=600)
        for i in range(0, len(todo), 200):
            part = todo[i:i + 200]
            hits = call("/nearest", {"index": name, "queries": [text(k, qw[k]) for k in part], "k": K}, wait=300)["hits"]
            for k, hs in zip(part, hits):
                near[k] = [[keys[int(j)], round(float(s), 3)] for j, s in hs if keys[int(j)] != k]
        d["near"], d["people"], d["at"] = near, sig, time.strftime("%FT%TZ", time.gmtime())
        save(d)
        print("векторы: слов %d за %.0f с; в файле %d, интересов людей %d" % (len(todo), time.time() - t0, len(near), len(keys)))
    # 2) отбор с силой близости и «тот же мир» — только для незнакомых поиску слов
    ok, grade, branch, asked = d["ok"], d["grade"], d["branch"], d["asked"]
    n, t1 = 0, time.time()
    for k in [x for x in first if x in qw] + sorted(qw):
        if n >= ASK_LIMIT:
            break
        top = [x for x, _ in near.get(k, [])[:25]]
        if not top or not unknown(qw[k]) or (k in asked and set(top[:10]) <= set(asked[k])):
            continue
        try:
            g = approve(qw[k], defs.get(k, ""), [(pv.get(x, x), defs.get(x, "")) for x in top], ask)
            g = verify(qw[k], defs.get(k, ""), g, lambda x: defs.get(C._norm(x), ""), ask)
            g = {C._norm(x): v for x, v in g.items()}
            grade[k], ok[k] = g, sorted(g)
            if not g:
                b = pick_branch(qw[k], defs.get(k, ""), ask)
                if b:
                    branch[k] = b
                else:
                    branch.pop(k, None)
            else:
                branch.pop(k, None)
        except Exception as e:
            print("модель не ответила:", str(e)[:100]); break
        asked[k] = top
        n += 1
        if n % 50 == 0:
            save(d)
    save(d)
    print("отбор: слов %d за %.0f с; с близкими %d, только «тот же мир» %d"
          % (n, time.time() - t1, sum(1 for v in grade.values() if v), len(branch)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
