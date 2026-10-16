# -*- coding: utf-8 -*-
"""ТРАНСЛИТ ВМЕСТО АНГЛИЙСКОГО КЛЮЧА: найти, спросить модель, записать в реестр.

ЗАЧЕМ. В базе всё по-английски, и по этим ключам люди встречаются. Слово, записанное латиницей с
русского — `slon`, `zabor`, `gazon`, `shashlik`, `plov`, `velotrek`, — хуже обоих вариантов: оно не
английское и не русское, и не совпадёт ни с кем никогда. Владелец 22.09.2026: «нужно, чтобы таких
проблем в принципе не было с другими словами, а не только чинить то, что я присылаю».

КАК ОТЛИЧИТЬ ТРАНСЛИТ ОТ ЗАИМСТВОВАНИЯ. Один признак не годится: `lego`, `barista`, `darts`,
`salad`, `pinball` — тоже похожи на транслит русского, но это НАСТОЯЩИЕ английские слова, и
выбрасывать их нельзя. Английского словаря на боксе нет, spellcheck-модулей тоже. Поэтому признак
двойной: (1) кандидат есть транслитерация кириллического слова ИЗ ТОЙ ЖЕ реплики; (2) модель
подтверждает, что английского слова с таким написанием нет, и называет правильное.

Ответ модели кладётся в синонимы реестра НАВСЕГДА — второй раз про это слово никто не спросит.

    python3 tools/translit_keys.py [--apply] [--limit 40]
"""
import argparse, collections, io, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shared"))
sys.path.insert(0, os.path.join(HERE, "..", "services", "buddy"))
import app as B
from llm_client import llm_complete
МОДЕЛЬ = os.environ.get("V2_MODEL", "qwen3_self")
ЖУРНАЛ = "/root/kleal-archive/card-model.jsonl"
РЕЕСТР = os.path.join(HERE, "..", "shared", "interests.json")
ТАБЛ = {u"а":"a",u"б":"b",u"в":"v",u"г":"g",u"д":"d",u"е":"e",u"ё":"e",u"ж":"zh",u"з":"z",u"и":"i",
        u"й":"y",u"к":"k",u"л":"l",u"м":"m",u"н":"n",u"о":"o",u"п":"p",u"р":"r",u"с":"s",u"т":"t",
        u"у":"u",u"ф":"f",u"х":"h",u"ц":"ts",u"ч":"ch",u"ш":"sh",u"щ":"sch",u"ъ":"",u"ы":"y",
        u"ь":"",u"э":"e",u"ю":"yu",u"я":"ya"}


def лат(w):
    return "".join(ТАБЛ.get(c, c) for c in str(w or "").lower())


def похоже_на_транслит(k, реплики):
    """Кандидат латиницей и кириллическое слово из той же речи дают одно написание."""
    # ТОЛЬКО ОДНО СЛОВО. Транслитерация русского слова — это всегда один латинский токен.
    # Словосочетания цеплялись префиксом и давали вредные предложения: «park walk» из «парке»
    # (и модель предлагала сократить до «park»), «retro video games» из «ретро» (сократить до
    # «retro» — то есть потерять смысл). Проверено на сухом прогоне 22.09.2026.
    if len(k) < 4 or " " in k or "-" in k or re.search(r"[а-яё]", k):
        return ""
    for x in (реплики or []):
        for c in re.findall(r"[а-яё]{4,}", str(x).lower()):
            l = лат(c)
            if l.startswith(k) or k.startswith(l[:max(4, len(l) - 2)]):
                return c
    return ""


ВОПРОС = (u"Слово «%s» написано латиницей. Это настоящее английское слово или транслитерация "
          u"русского «%s»?\nОтветь одной строкой: либо ENGLISH, либо правильное английское слово "
          u"для «%s» одним словом, без пояснений.")


def спросить(к, рус):
    o = llm_complete(МОДЕЛЬ, [{"role": "user", "content": ВОПРОС % (к, рус, рус)}], temperature=0.0)
    o = str(o or "").strip().strip('".«»').split("\n")[0].strip()
    if not o or o.upper().startswith("ENGLISH"):
        return ""
    o = o.lower()
    return o if re.match(r"^[a-z][a-z \-]{2,24}$", o) and o != к else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    # ПОРОГ ЧАСТОТЫ. Сухой прогон 22.09.2026 показал, на чём модель ошибается: на РЕДКИХ словах.
    # «sokol» она перевела как falcon (а это скорее район), «sapr» — как sapper (а «сапры» это
    # сапборды, и `sup` в реестре есть), «taburetka» и «taburets» получили stool и chair, то есть
    # разошлись между собой. Все они встретились один-два раза. Повторяющееся же разобрано верно:
    # velotrek/velotrack -> velodrome (32 вхождения), plov -> pilaf (14).
    ap.add_argument("--min", type=int, default=3, help="сколько раз слово должно встретиться")
    a = ap.parse_args()
    счёт, источник = collections.Counter(), {}
    for l in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace").readlines()[-25000:]:
        try: r = json.loads(l)
        except Exception: continue
        says = [str(x) for x in (r.get("says") or [])]
        g = r.get("got") or {}
        for k in ([str(x).strip().lower() for x in (r.get("was") or [])]
                  + [str(x).strip().lower() for x in (g.get("chips") or [])]
                  + [str(g.get("key") or "").lower()]):
            if not k or B.norm_topic(k):
                continue
            рус = похоже_на_транслит(k, says)
            if рус:
                счёт[k] += 1
                источник.setdefault(k, рус)
    канд = [w for w, c in счёт.most_common(a.limit) if c >= a.min]
    print("подозрений на транслит: %d слов, %d вхождений" % (len(счёт), sum(счёт.values())))
    решения = {}
    for w in канд:
        try: англ = спросить(w, источник[w])
        except Exception as e: англ = ""
        решения[w] = англ
        print("   %-14s (из «%s», ×%d) -> %s" % (w, источник[w], счёт[w], англ or "ENGLISH, не трогаем"))
    правки = {w: v for w, v in решения.items() if v}
    print("к записи синонимов: %d" % len(правки))
    if not a.apply or not правки:
        print("НИЧЕГО НЕ ИЗМЕНЕНО." if not a.apply else "нечего записывать")
        return 0
    import shutil, time
    reg = json.load(io.open(РЕЕСТР, encoding="utf-8"))
    arc = "/root/kleal-archive/translit-keys-" + time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(arc, exist_ok=True); shutil.copy2(РЕЕСТР, arc + "/interests.json")
    syn = reg.setdefault("synonyms", {})
    легло = 0
    for w, v in правки.items():
        if B.norm_topic(v):                      # цель сводится — можно вести прямо к ней
            syn[w] = B.norm_topic(v); легло += 1
        else:
            syn[w] = v; легло += 1               # новое английское слово: пусть хотя бы оно, не транслит
    io.open(РЕЕСТР, "w", encoding="utf-8").write(json.dumps(reg, ensure_ascii=False, indent=1))
    print("АРХИВ: %s | записано %d" % (arc, легло))
    return 0


if __name__ == "__main__":
    sys.exit(main())
