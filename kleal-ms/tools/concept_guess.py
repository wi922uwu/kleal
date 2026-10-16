# -*- coding: utf-8 -*-
"""КАРТА ДОГАДОК: слово вне канона -> ближайший узел канона (никогда не «точно»).

Слово, которого канон не знает («мороженое», «воздушный змей», «пожонглировать», ключ реестра bowling),
делало всех людей T5 — поиск находил ноль. Раньше такие слова вписывали руками по одному; под живую
аудиторию это тупик. Теперь слово ставится к узлу канона ОДИН РАЗ, когда появляется, а не в поиске:
языковая модель одной строкой говорит, что слово значит, и выбирает СЕМЬЮ из всех семей канона (их 46 без
свиданий, список целиком с примерами — модель знает, что Catan это настолки, а векторы нет). Только семья:
конкретное занятие внутри семьи модель выбирала плохо (рамен, мороженое и хлеб — «пицца»), а для яруса
разницы нет — 2 и 3 оба второй ярус. Свидания исключены: свидание это тип затеи, а не интерес. Векторный
вариант (bge-m3 даёт 25 кандидатов, модель выбирает один) 30.09.2026 ставил Каркассон в пазлы, спайкбол в
гандбол, walk в прогулку-свидание — отброшен.
Поиск читает только файл (в сеть не ходит), уровень догадки не выше 3 — точное остаётся точным
(graph.similarity_detail, canonical.similarity_guess).

    python3 tools/concept_guess.py [--root=/opt/kleal/kleal-ms] [--backfill] [--limit=N]
Источники: интересы анкет (shared/db.load_users), ключи реестра, которых канон не знает, чипы и заголовки
карточек Буди из журнала (journalctl -u kleal@buddy; при --backfill с 24.09, иначе за последние 10 минут).
NONE тоже записывается — одно слово модель видит один раз.
"""
import datetime, fcntl, io, json, os, re, subprocess, sys

ROOT = os.environ.get("KLEAL_ROOT") or "/opt/kleal/kleal-ms"
LIMIT, BACKFILL, COUNT, ONLY = 250, False, False, None
for a in sys.argv[1:]:
    if a.startswith("--root="):
        ROOT = a.split("=", 1)[1]
    elif a.startswith("--limit="):
        LIMIT = int(a.split("=", 1)[1])
    elif a == "--backfill":
        BACKFILL = True
    elif a == "--count":
        COUNT = True
    elif a.startswith("--words="):                     # только эти слова (проверка, ручная правка)
        ONLY = [x.strip() for x in a.split("=", 1)[1].split("|") if x.strip()]
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))
from matching_core.taxonomy import canonical as C  # noqa: E402

MAP = os.environ.get("KLEAL_GUESS_FILE") or "/var/lib/kleal/canonical_guess.json"      # тот же путь читает canonical.py


# Свидание — тип затеи, а не интерес: такие слова в карту не ставятся никогда, что бы ни ответила модель. 30.09.2026
# модель поставила «свидание» в «неформальное общение» — оно потянуло бы людей со свиданиями в дружеский поиск.
_DATING = re.compile(r"свидан|романт|любов|флирт|секс|интим|знакомств|девушк|\bпарн(ем|я|ю|и|ей)?\b|"
                     r"\bdat(e|es|ing)\b|\blove\b|romanc|romant|flirt|\bsex(?!tet)|hook ?up|girlfriend|boyfriend|одн(у|ой|а) ноч|"
                     r"\bone night\b|\bfwb\b|nudes|porn|\bcitas?\b|\bligar\b|\bnovi[oa]s?\b|\bpareja\b|\bamor\b", re.I)


# Зонтики не ставятся: слово-область само по себе «льстит» любому запросу своей области и врёт через границу
# областей (tools/concepts_smoke.py «зонтики не резолвятся», «зонтик не роднит»; тот же список в graph._wshare).
# 30.09.2026 «exchange» из карточки про языковой обмен ушло в языковой обмен — и роднило бы биржу с языками.
_UMBRELLA = {"market", "mercado", "рынок", "project", "проект", "exchange", "intercambio", "обмен", "game", "games",
             "игра", "игры", "juego", "juegos", "role", "playing", "роль", "business", "бизнес", "negocio", "tech",
             "technology", "технологии", "product", "продукт", "language", "languages", "язык", "языки", "idioma",
             "idiomas", "sport", "sports", "спорт", "deporte", "deportes", "music", "музыка", "música", "art", "arts",
             "искусство", "arte", "food", "еда", "comida", "design", "дизайн", "diseño", "hobby", "hobbies", "хобби",
             "activity", "activities", "занятие", "actividad", "fun", "развлечения", "diversión"}


def never(w):
    """Слово, которое карта не ставит никогда: свидания и зонтики."""
    return bool(_DATING.search(w or "")) or C._norm(w) in _UMBRELLA


def load_map():
    try:
        with io.open(MAP, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("words", {})
        return d
    except Exception:
        return {"version": 1, "words": {}}


def save_map(d):
    tmp = MAP + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=True)
        f.write("\n")
    os.replace(tmp, MAP)                      # атомарно: поиск перечитывает файл по времени изменения


def unknown(w, words):
    k = C._norm(w)
    if not k or len(k) < 3 or k.isdigit() or k in words:
        return False
    try:
        return C._resolve(w)[0] is None
    except Exception:
        return False


def sources(words):
    """[(слово, контекст)] — только то, чего канон не знает и чего нет в карте."""
    out, seen = [], set()

    def add(w, ctx=""):
        w = str(w or "").strip()
        if len(w) > 60 or not unknown(w, words) or C._norm(w) in seen:
            return
        seen.add(C._norm(w))
        out.append((w, str(ctx or "")[:80]))
    # 1) чипы и заголовки карточек Буди из журнала — то, что люди ищут прямо сейчас
    since = "2026-09-24" if BACKFILL else "-10 min"
    try:
        log = subprocess.run(["journalctl", "-u", "kleal@buddy", "--since", since, "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=120).stdout
    except Exception:
        log = ""
    for line in log.splitlines():
        m = re.search(r"\[v2\] /\S+ .*?заголовок='([^']*)' чипы=(\[[^\]]*\])", line)
        if m:
            try:
                chips = json.loads(m.group(2).replace("'", '"'))
            except Exception:
                chips = []
            for c in chips:
                add(c, m.group(1))
        m = re.search(r'\[v2-слово\] \{"w": "([^"]+)"', line)
        if m:
            add(m.group(1))
    # 2) ключи реестра, которых канон не знает (телефон шлёт в поиск именно ключи)
    try:
        reg = json.load(io.open(os.path.join(ROOT, "shared", "interests.json"), encoding="utf-8"))
        labels = reg.get("labels") or {}

        def walk(x):
            if isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    if isinstance(v, str):
                        lab = labels.get(v) or {}
                        add(v, " / ".join(str(lab.get(k) or "") for k in ("ru", "en", "es") if lab.get(k)))
                    else:
                        walk(v)
        walk(reg.get("tree") or {})
    except Exception:
        pass
    # 3) интересы анкет — сторона людей: то, по чему их ищут
    try:
        import db
        for u in db.load_users() or []:
            for i in (u.get("interests") or []) if isinstance(u, dict) else []:
                add(i)
    except Exception as e:
        print("анкеты не прочитались:", str(e)[:120])
    return out


def main():
    os.makedirs(os.path.dirname(MAP), exist_ok=True)
    lock = open(MAP + ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("уже идёт другой прогон"); return 0
    d = load_map()
    words = d["words"]
    fixed = 0
    for v in words.values():                          # запрет действует и на поставленное раньше
        if v.get("node") and never(v.get("text")):
            v["node"], v["by"] = None, "guard"; fixed += 1
    if fixed:
        save_map(d); print("снято слов (свидания, зонтики): %d" % fixed)
    todo = [(w, "") for w in ONLY if unknown(w, words)] if ONLY else sources(words)
    if COUNT:
        print("новых слов %d (в карте %d): %s" % (len(todo), len(words), ", ".join(w for w, _ in todo[:40])))
        return 0
    todo = todo[:LIMIT]
    if not todo:
        print("новых слов нет (в карте %d)" % len(words)); return 0
    import config, llm_client
    model = getattr(config, "MODEL_ID", None)
    N = C.NODES
    fams = [f for f in N if f.startswith("F_") and N[f].get("macro") != "M_dating"]
    ex = {f: [N[i].get("ru") for i in N if i.startswith("I_") and N[i].get("family") == f and N[i].get("ru")][:5]
          for f in fams}
    fam_list = "\n".join("%s — %s / %s (%s)" % (f, N[f].get("ru") or "", N[f].get("en") or "", ", ".join(ex[f]))
                          for f in fams)

    def ask(system, user):
        return llm_client.llm_complete(model, [{"role": "system", "content": system},
                                               {"role": "user", "content": user}], temperature=0.0, tag="concept_guess") or ""
    done = 0
    for w, ctx in todo:
        plan = (" The plan it came with: «%s»." % ctx) if ctx else ""
        try:
            a = ask("You put a word into one family of a fixed list.",
                    "A person in a social app named this as an activity or interest they want to do with someone: «%s».%s\n"
                    "First line: what «%s» means here, in at most 8 words. Second line: the id of the family below it "
                    "belongs to, or NONE if it is not an activity or interest (a place, a person, an animal, a body part, "
                    "a feeling, a random word) or if it is about romance, dating or sex.\n\n%s" % (w, plan, w, fam_list))
        except Exception as e:
            print("модель не ответила:", str(e)[:120]); break
        ids = [x for x in re.findall(r"\b(F_[a-z0-9_]+)\b", a) if x in fams]
        fam = ids[-1] if ids and not never(w) else None
        node = fam
        meaning = (a.strip().splitlines() or [""])[0][:120]
        words[C._norm(w)] = {"text": w, "node": node, "meaning": meaning, "ctx": ctx, "by": "llm-family",
                             "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
        done += 1
        if done % 25 == 0:
            save_map(d)
    save_map(d)
    print("поставлено %d новых слов; в карте %d, из них с узлом %d"
          % (done, len(words), sum(1 for v in words.values() if v.get("node"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
