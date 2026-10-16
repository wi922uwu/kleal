# -*- coding: utf-8 -*-
"""ТРИ СЕМЬИ СЦЕНАРИЕВ, КОТОРЫХ БАТАРЕЕ НЕ ХВАТАЛО.

ЗАЧЕМ. Замер покрытия 22.09.2026 по 3232 живым репликам: правка готовой затеи («убери», «удали») —
0 реплик, деньги и биржа — 0, русское слово латиницей — 0, опечатки — 1, два интереса подряд — 4,
работа руками — 4. Словарь батареи: 142 ключа из 437. При этом ровно на этих местах продукт и
ломался: второй интерес терялся в 0,928 разговоров, «убери крипту» не распознавалось вовсе,
транслит дал 273 вхождения — и НИ ОДНУ из этих бед батарея не показала, все três пришли со
скриншотов владельца.

ПОЧЕМУ МЕТКИ ЗДЕСЬ ВЕРНЫ ПО ПОСТРОЕНИЮ. Генератор сценариев пишет `never` моделью, и треть его
меток оказалась неверной (разбор 22.09.2026). Здесь запрещённое слово — это то, что человек ЯВНО
отменил и больше не называл, а ожидаемое — то, что он назвал последним. Ошибиться тут нечем.

ЭТАЛОН НЕ ТРОГАЕМ. Дописываем только в живой пул `scenarios.jsonl`; замороженный `bench-500.jsonl`
остаётся прежним, иначе потеряется сравнимость со всеми прошлыми кругами.

    python3 tools/scen_extend.py [--apply] [--per 300]
"""
import argparse, io, json, os, random, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "services", "buddy"))
import app as B
ПУЛ = "/root/kleal-archive/scenarios.jsonl"
ТАБЛ = {u"а":"a",u"б":"b",u"в":"v",u"г":"g",u"д":"d",u"е":"e",u"ё":"e",u"ж":"zh",u"з":"z",u"и":"i",
        u"й":"y",u"к":"k",u"л":"l",u"м":"m",u"н":"n",u"о":"o",u"п":"p",u"р":"r",u"с":"s",u"т":"t",
        u"у":"u",u"ф":"f",u"х":"h",u"ц":"ts",u"ч":"ch",u"ш":"sh",u"щ":"sch",u"ъ":"",u"ы":"y",
        u"ь":"",u"э":"e",u"ю":"yu",u"я":"ya"}
ХОЧУ = {"ru": [u"хочу %s", u"давай %s", u"ищу компанию: %s", u"есть желание %s"],
        "en": ["i want %s", "looking for company: %s", "let's do %s", "anyone up for %s"],
        "es": ["quiero %s", "busco compañía: %s", "vamos a %s", "¿alguien para %s?"]}
ЕЩЁ = {"ru": [u"и ещё %s", u"а также %s", u"и %s тоже"],
       "en": ["and also %s", "plus %s", "and %s too"],
       "es": ["y también %s", "además %s", "y %s también"]}
УБЕРИ = {"ru": [u"убери %s", u"удали %s, оставь остальное"],
         "en": ["remove %s", "delete %s, keep the rest"],
         "es": ["quita %s", "elimina %s, deja el resto"]}
ВМЕСТО = {"ru": [u"нет, лучше %s", u"а нет, давай %s"],
          "en": ["actually no, let's do %s", "no, better %s"],
          "es": ["no, mejor %s", "de hecho, mejor %s"]}


def подпись(k, lang):
    try: return (B._display_topic(k, lang) or k).lower()
    except Exception: return k


def основы(k, lang):
    """Куски, по которым батарея узнает занятие в карточке: английский ключ и местная подпись."""
    out = {k[:6].lower()}
    p = подпись(k, lang)
    if p and p != k: out.add(re.sub(r"[^\w]", "", p)[:6].lower())
    return sorted(x for x in out if len(x) >= 3)


def опечатка(w):
    """Живой человек промахивается мимо клавиши: пропуск буквы или удвоение."""
    if len(w) < 5: return w
    i = len(w) // 2
    return w[:i] + w[i + 1:] if len(w) % 2 else w[:i] + w[i] + w[i:]


def транслит(w):
    return "".join(ТАБЛ.get(c, c) for c in str(w or "").lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--per", type=int, default=300)
    a = ap.parse_args()
    random.seed(20260922)
    reg = json.load(io.open(os.path.join(HERE, "..", "shared", "interests.json"), encoding="utf-8"))
    ключи = [str(w).lower() for subs in (reg.get("tree") or {}).values()
             for ws in (subs or {}).values() for w in (ws or [])]
    ключи = [k for k in ключи if B.norm_topic(k) == k and " " not in k]

    def односложный(k):
        """Ключи с составной подписью в сценарии не годятся: «и ещё на открытом воздухе» — не речь
        человека, а огрызок основы («наоткр») ничего не проверяет. Замечено на сухом прогоне."""
        for lang in ("ru", "en", "es"):
            p_ = подпись(k, lang)
            if not p_ or " " in p_ or len(p_) > 16:
                return False
        return True
    ключи = [k for k in ключи if односложный(k)]
    # какие ключи батарея уже гоняет — новые берём ПРЕИМУЩЕСТВЕННО из остальных
    видел = set()
    try:
        for l in io.open("/root/kleal-archive/battery-live.jsonl", encoding="utf-8", errors="replace"):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("kind") != "human": continue
            for w in re.findall(r"[^\W\d_]{4,}", str(r.get("text") or "").lower(), re.UNICODE):
                n = B.norm_topic(w)
                if n: видел.add(n)
    except Exception: pass
    свежие = [k for k in ключи if k not in видел] or ключи
    print("ключей всего %d, батарея видела %d, свежих %d" % (len(ключи), len(видел), len(свежие)))
    новые = []

    def добавь(lang, says, expect, never, вид):
        новые.append({"label": "ext-%s-%s-%04d" % (вид, lang, len(новые)), "lang": lang, "hard": 2,
                      "says": says, "expect": expect, "never": never, "src": "ext-" + вид})

    # 1. ПРАВКА ГОТОВОЙ ЗАТЕИ: добавить, убрать, заменить.
    for i in range(a.per):
        lang = ("ru", "en", "es")[i % 3]
        A, Bk = random.sample(ключи, 2)
        pa, pb = подпись(A, lang), подпись(Bk, lang)
        вид = i % 3
        if вид == 0:                                   # добавили второе — оно обязано доехать
            добавь(lang, [random.choice(ХОЧУ[lang]) % pa, random.choice(ЕЩЁ[lang]) % pb],
                   основы(Bk, lang), [], "add")
        elif вид == 1:                                 # убрали первое — его быть не должно
            добавь(lang, [random.choice(ХОЧУ[lang]) % pa, random.choice(ЕЩЁ[lang]) % pb,
                          random.choice(УБЕРИ[lang]) % pa],
                   основы(Bk, lang), основы(A, lang), "del")
        else:                                          # заменили — прежнего быть не должно
            добавь(lang, [random.choice(ХОЧУ[lang]) % pa, random.choice(ВМЕСТО[lang]) % pb],
                   основы(Bk, lang), основы(A, lang), "swap")

    # 2. ШУМ ЖИВОГО ЧЕЛОВЕКА: опечатка, транслит, смешение языков.
    for i in range(a.per):
        k = random.choice(ключи)
        вид = i % 3
        if вид == 0:
            lang = ("ru", "en", "es")[i % 3]
            добавь(lang, [random.choice(ХОЧУ[lang]) % опечатка(подпись(k, lang))],
                   основы(k, lang), [], "typo")
        elif вид == 1:                                  # русское слово латиницей — как «slon»
            добавь("ru", [u"хочу %s" % транслит(подпись(k, "ru"))], основы(k, "ru"), [], "translit")
        else:                                           # английский ключ внутри русской фразы
            добавь("ru", [u"хочу %s с кем-нибудь" % k], основы(k, "ru"), [], "mixed")

    # 3. СЛОВАРЬ: занятия, которых батарея не пробовала.
    for i in range(a.per):
        lang = ("ru", "en", "es")[i % 3]
        k = свежие[i % len(свежие)]
        добавь(lang, [random.choice(ХОЧУ[lang]) % подпись(k, lang),
                      {"ru": u"когда удобно?", "en": "when works?", "es": "¿cuándo?"}[lang]],
               основы(k, lang), [], "vocab")

    print("сочинено сценариев: %d" % len(новые))
    for x in новые[:6] + новые[a.per:a.per + 4] + новые[2 * a.per:2 * a.per + 3]:
        print("   %-18s %s | ждём %s | нельзя %s" % (x["src"], " / ".join(x["says"])[:58],
                                                     x["expect"], x["never"]))
    if not a.apply:
        print("НИЧЕГО НЕ ЗАПИСАНО. Повторить с --apply"); return 0
    import shutil, time
    shutil.copy2(ПУЛ, "/root/kleal-archive/scenarios-before-ext-%s.jsonl" % time.strftime("%Y%m%d_%H%M%S"))
    with io.open(ПУЛ, "a", encoding="utf-8") as f:
        for x in новые:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("дописано в пул: %d, теперь строк %d"
          % (len(новые), sum(1 for _ in io.open(ПУЛ, encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
