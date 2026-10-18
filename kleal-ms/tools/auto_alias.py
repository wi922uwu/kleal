# -*- coding: utf-8 -*-
"""АВТОСИНОНИМЫ: слово, которого не знает словарь поиска, сама система ставит синонимом к занятию словаря.

Зачем (17.10.2026, разбор «грибы»): Буди пишет ключ реестра `mushroom picking`, люди в анкетах — «porcini mushrooms»,
«lisichki», «white mushrooms», а словарь поиска знает только узел I_mushroom_foraging и пару его алиасов. Карта догадок
(concept_guess) ставит такие слова лишь в СЕМЬЮ «природа» — уровень 2, как у любого походника, и грибники тонули на
46–48 местах. Вписывать слова руками владелец запретил: «нужно автоматизировать».

Как: для каждого незнакомого слова (интересы людей, ключи реестра, чипы Буди, слова карты догадок)
  1) модель пишет, что это, одной строкой по-английски (пачками по 25);
  2) bge-m3 (под, туннель 17078) даёт 20 ближайших ЗАНЯТИЙ словаря (узлы I_*) по этому описанию;
  3) модель выбирает узел, если слово — ТО ЖЕ занятие или его разновидность («porcini mushrooms» → сбор грибов), иначе NONE;
  4) отдельный вопрос да/нет перепроверяет выбор строго («вино» ≠ «дегустация вина», «кофе» ≠ «кофе-свидание»).
Принятое пишется в /var/lib/kleal/canonical_auto.json (KLEAL_AUTO_FILE); canonical.py читает файл раз в 30 с и
считает слово точным алиасом узла. NONE тоже записывается — слово спрашивается один раз (переспрос — удалить ключ).
Свидания, наркотики, зонтики — никогда (tools/concept_guess.never).

Строже с 17.10.2026 (вечер): после «да» проверки модель ещё называет вид связи (_REL), и «шире» (B) снимает привязку:
«chinesefood» → дим-сам, «outdoors» → поход, «travel» → планирование поездок. Мерили на 874 привязках первого прохода:
из других видов связи и из вопросов «группой», «устойчивость выбора», «сколько из 10» ни один не отделял ошибки без
потери 10–25% верных (снимались и сами грибы), поэтому принимается только признак «шире». Мухоморы — в запретах.
Синонимы реестра (shared/interests.json → synonyms) привязываются без модели — к узлу своего ключа, если поиск его знает.

    python3 tools/auto_alias.py [--root=…] [--limit=N] [--backfill] [--first=файл] [--words=a|b]
"""
import datetime, fcntl, hashlib, importlib.util, io, json, os, re, subprocess, sys, time

ROOT = os.environ.get("KLEAL_ROOT") or "/opt/kleal/kleal-ms"
LIMIT, BACKFILL, FIRST, ONLY, RECHECK = 40, False, None, [], False
for a in sys.argv[1:]:
    if a.startswith("--root="):
        ROOT = a.split("=", 1)[1]
    elif a.startswith("--limit="):
        LIMIT = int(a.split("=", 1)[1])
    elif a == "--recheck":                           # перепроверить уже привязанные текущим вопросом проверки
        RECHECK = True
    elif a == "--backfill":
        BACKFILL = True
    elif a.startswith("--first="):
        FIRST = a.split("=", 1)[1]
    elif a.startswith("--words="):
        ONLY = [x.strip() for x in a.split("=", 1)[1].split("|") if x.strip()]
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))
from matching_core.taxonomy import canonical as C  # noqa: E402

OUT = os.environ.get("KLEAL_AUTO_FILE") or "/var/lib/kleal/canonical_auto.json"
GUESS = os.environ.get("KLEAL_GUESS_FILE") or "/var/lib/kleal/canonical_guess.json"
BASE = os.environ.get("KLEAL_MEANING_URL") or "http://127.0.0.1:17078"


def _never_fn():
    src = io.open(os.path.join(ROOT, "tools", "concept_guess.py"), encoding="utf-8").read()
    ns = {"re": re, "C": C}
    i, j = src.index("_DATING = re.compile"), src.index("def load_map")
    exec(src[i:j], ns)                                  # только запреты, без разбора аргументов файла
    return ns["never"]


never = _never_fn()
_DRUGS = re.compile(r"наркот|травк|мухомор|agaric|amanita|псилоц|марихуан|кокаин|закладк|грибы\s+(?:псило|галлюц)|псилоцив|psilocyb|magic\s+mushroom|"
                    r"microdos|микродоз|\bdrugs?\b|\bweed\b|cannabis|cocaine|\blsd\b|mdma|\bdrogas?\b|\bporros?\b", re.I)


def banned(w):
    return never(w) or bool(_DRUGS.search(w or ""))


def unknown(w):
    try:
        return C._resolve(w)[0] is None
    except Exception:
        return False


def call(path, body, wait=60):
    import urllib.request
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=wait))


def sources():
    out = {}

    def add(w):
        w = str(w or "").strip()
        k = C._norm(w)
        if k and 3 <= len(k) <= 60 and k not in out and not banned(w) and unknown(w):
            out[k] = w
    try:
        import db
        for u in db.load_users() or []:
            for i in (u.get("interests") or []) if isinstance(u, dict) else []:
                add(i)
    except Exception as e:
        print("анкеты не прочитались:", str(e)[:100])
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
    since = "2026-09-24" if BACKFILL else "-15 min"
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
    try:
        for v in (json.load(io.open(GUESS, encoding="utf-8")).get("words") or {}).values():
            add(v.get("text"))
    except Exception:
        pass
    return out


_DEF = ("For each item a person listed as an interest or as something they want to do with others, write in plain English "
        "what it is, at most 10 words. Keep slang, brands and transliterated words meaningful (lisichki = chanterelle "
        "mushrooms, pop-it = fidget toy). If unsure, write UNKNOWN.\nOne line per item: <number>. <text>\n\n%s")
_PICK = ("A person listed «%s» (%s) as an interest.\nBelow are activities from our catalog. Pick the ONE that is the SAME interest "
         "as «%s». It counts when «%s» is that activity, a specific kind of it (bouldering -> climbing), or the THING that "
         "activity is about when people have it as a hobby (porcini, chanterelles, mushrooms -> mushroom foraging; birds -> "
         "birdwatching; bonsai -> gardening of that kind).\n"
         "Do NOT pick a broader area, a merely related activity, a setting, or an activity for a thing that has many different "
         "uses (wine is not wine tasting, coffee is not a coffee date, food is not a food market, books are not a book club, "
         "hiking is not mushroom foraging). If «%s» is vague or generic on its own (body, care, chill, fun, adventure, "
         "amusement, business, logistics), answer NONE.\nAnswer with the id only, or NONE.\n\n%s")
_CHECK = ("Two people use a social app. One wrote «%s» (%s) as their interest. The other searches for company for «%s» (%s).\n"
          "Is it the SAME interest — would the first person, by writing this, almost certainly be into exactly that activity? "
          "YES if it is that activity, a specific kind of it, or the thing it is about when people do it as a hobby "
          "(porcini mushrooms -> mushroom foraging). NO if it is only related, broader, a setting, or a thing with many other "
          "uses (wine -> wine tasting: NO; coffee -> coffee date: NO), or if the first is vague or generic on its own "
          "(body, care, chill, fun, adventure, amusement, business: NO). Answer YES or NO.")


_SPECIFIC = ("Classify the word «%s» (%s) as a person's interest.\n"
             "A — it names one concrete thing to do or enjoy: a hobby, sport, game, craft, dish, drink, music style, instrument, "
             "language, plant or animal people collect or watch (examples: choir, bbq, bjj, chanterelles, грибы, ableton, catan, "
             "balalaika, ceramica, arabic).\n"
             "B — it is a general word that could mean many different things (examples: care, help, body, board, chill, casual, "
             "adventurers, amusement, alternative, artisanal, carnival, business, archives).\nAnswer A or B.")


_REL = ("One person wrote «%s» (%s) in their profile as an interest. Another person searches for company for «%s» (%s).\n"
        "How is «%s» related to that activity? Answer with ONE letter:\n"
        "A — it IS that activity, a specific kind of it, or the thing that activity is about when people do it as a hobby "
        "(bouldering -> climbing; catan -> strategy board games; porcini -> mushroom foraging).\n"
        "B — it is BROADER: a general area that includes this activity and many others (sports -> tennis; music -> jazz; "
        "japanese food -> ramen).\n"
        "C — it is only RELATED: a setting, a tool, a step, a part, or a thing with many uses (beach -> surfing; guitar -> "
        "songwriting club; coffee -> coffee date).\n"
        "D — it is not a named interest: a vague or generic word, or a remark or sentence about the person's life, "
        "feelings or situation (fun; adventure; I moved here last year; my back hurts).\n"
        "E — it can be about drugs, getting high, sex or dating.\n"
        "F — it is a DIFFERENT activity.\nLetter only.")


def related(w, wd, n, ask):
    """Вид связи слова с узлом (буква _REL). Снимает только B — «шире»; остальные буквы модель ставит слишком шумно."""
    a = ask("You check interest matches strictly.", _REL % (w, wd or w, C.NODES[n].get("en"), node_text(n), w))
    m = re.search(r"\b([A-F])\b", a.strip().upper())
    return (m.group(1) if m else "?")


def registry_synonyms():
    """Синоним реестра -> узел его ключа, без модели (реестр составлен людьми)."""
    out = {}
    try:
        reg = json.load(io.open(os.path.join(ROOT, "shared", "interests.json"), encoding="utf-8"))
    except Exception:
        return out
    for s, key in (reg.get("synonyms") or {}).items():
        if not isinstance(key, str) or banned(s) or not unknown(s):
            continue
        n, exact = C._resolve(key)
        if n and exact and str(n).startswith("I_") and C.NODES.get(n, {}).get("macro") != "M_dating":
            out[C._norm(s)] = (s, n, key)
    return out


def specific(w, ask, defn=""):
    """Однословное — только если это само название занятия: «care» -> помощь пожилым, «board» -> скейтборд,
    «amusement» -> цирк проходили выбор и проверку (стенд 17.10.2026, 12 ошибок из 163 — все однословные)."""
    if len(str(w).split()) > 1:
        return True
    if len(C._norm(w)) < 4:
        return False                                   # обрывки вроде «cer»
    a = ask("You classify interest words.", _SPECIFIC % (w, defn or w))
    return bool(re.search(r"\bA\b", a)) and not re.search(r"\bB\b", a)


def node_text(n):
    N = C.NODES[n]
    fam = C.NODES.get(N.get("family") or "", {})
    return "%s / %s (%s)" % (N.get("en") or "", N.get("ru") or "", fam.get("en") or "")


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    lock = open(OUT + ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("уже идёт другой прогон"); return 0
    try:
        d = json.load(io.open(OUT, encoding="utf-8"))
    except Exception:
        d = {"version": 1, "words": {}}
    words = d.setdefault("words", {})
    if RECHECK:
        import config, llm_client
        model = getattr(config, "MODEL_ID", None)
        n_drop = 0
        for k, v in words.items():
            n = v.get("node")
            if not n or n not in C.NODES:
                continue
            if v.get("check") == "registry":
                continue
            ask1 = lambda sy, us: llm_client.llm_complete(model, [{"role": "system", "content": sy}, {"role": "user", "content": us}],
                                                          temperature=0.0, tag="auto_alias") or ""
            rel = "ban" if banned(v["text"]) else related(v["text"], v.get("def") or "", n, ask1)
            if rel in ("B", "ban"):                     # модельное E не слушаем: она ставила его самим грибам
                v["node"], v["check"], v["cand"] = None, "no-recheck:" + rel, n; n_drop += 1
                print("снято:", v["text"], "->", n, rel)
        tmp = OUT + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=True)
        os.replace(tmp, OUT)
        print("перепроверка: снято %d" % n_drop)
        return 0
    n_reg = 0
    if not ONLY:
        for k, (s, n, key) in registry_synonyms().items():
            if (words.get(k) or {}).get("node") != n:
                words[k] = {"text": s, "node": n, "check": "registry", "def": "registry synonym of " + key,
                            "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
                n_reg += 1
    if n_reg:
        print("синонимов реестра привязано:", n_reg)
    src = {C._norm(w): w for w in ONLY} if ONLY else sources()
    first = [C._norm(w) for w in (io.open(FIRST, encoding="utf-8").read().split("|") if FIRST else []) if w.strip()]
    for k in first:
        src.setdefault(k, k)
    todo = [k for k in first if k in src and k not in words] + sorted(k for k in src if k not in words and k not in first)
    todo = todo[:LIMIT]
    if not todo:
        if n_reg:
            tmp = OUT + ".tmp"
            with io.open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=True)
            os.replace(tmp, OUT)
        print("новых слов нет (в файле %d, привязано %d)" % (len(words), sum(1 for v in words.values() if v.get("node"))))
        return 0
    import config, llm_client
    model = getattr(config, "MODEL_ID", None)

    def ask(system, user):
        return llm_client.llm_complete(model, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                                       temperature=0.0, tag="auto_alias") or ""
    nodes = [n for n in C.NODES if n.startswith("I_") and C.NODES[n].get("macro") != "M_dating"]
    texts = [node_text(n) for n in nodes]
    index = "nodes-" + hashlib.md5("\n".join(texts).encode("utf-8")).hexdigest()[:16]
    # 1) описания пачкой
    defs = {}
    for i in range(0, len(todo), 25):
        part = todo[i:i + 25]
        a = ask("You explain hobbies briefly.", _DEF % "\n".join("%d. %s" % (j + 1, src[k]) for j, k in enumerate(part)))
        for line in a.splitlines():
            m = re.match(r"\s*(\d{1,2})\.\s*(.+)$", line)
            if m and 1 <= int(m.group(1)) <= len(part):
                t = m.group(2).strip()
                defs[part[int(m.group(1)) - 1]] = "" if "UNKNOWN" in t.upper() else t[:120]
    # 2) ближайшие занятия
    q = [("%s: %s" % (src[k], defs[k])) if defs.get(k) else src[k] for k in todo]
    for attempt in (0, 1):
        try:
            hits = call("/nearest", {"index": index, "queries": q, "k": 20}, wait=120)["hits"]
            break
        except Exception as e:
            if attempt or getattr(e, "code", None) != 404:
                print("смысл недоступен:", str(e)[:120]); return 1
            call("/index", {"name": index, "candidates": texts}, wait=600)
    done = {"привязано": 0, "нет": 0, "отклонено проверкой": 0}
    for k, hs in zip(todo, hits):
        w, wd = src[k], defs.get(k, "")
        cand = [nodes[int(j)] for j, _ in hs]
        rec = {"text": w, "node": None, "def": wd, "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            a = ask("You map interests to a catalog.", _PICK % (w, wd or w, w, w, w, "\n".join("%s — %s" % (n, node_text(n)) for n in cand)))
            got = [x for x in re.findall(r"\b(I_[A-Za-z0-9_]+)\b", a) if x in cand]
            if got and not re.search(r"\bNONE\b", a):
                n = got[0]
                b = ask("You check interest matches strictly.", _CHECK % (w, wd or w, C.NODES[n].get("en"), node_text(n)))
                ok = bool(re.search(r"\bYES\b", b)) and not re.search(r"\bNO\b", b) and specific(w, ask, wd)
                rel = related(w, wd, n, ask) if ok else ""
                ok = ok and rel != "B"
                rec.update(cand=n, check="yes" if ok else ("no:B" if rel == "B" else "no"))
                if ok:
                    rec["node"] = n; done["привязано"] += 1
                else:
                    done["отклонено проверкой"] += 1
            else:
                done["нет"] += 1
        except Exception as e:
            print("модель не ответила:", str(e)[:100]); break
        words[k] = rec
    tmp = OUT + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, OUT)
    print("слов %d: %s; в файле %d, привязано всего %d" % (len(todo), done, len(words), sum(1 for v in words.values() if v.get("node"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
