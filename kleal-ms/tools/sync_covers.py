#!/usr/bin/env python3
"""
Пересобрать таблицу «тема → подгруппа» для приложения.

    python3 tools/sync_covers.py          # печатает путь и число ключей

ИСТОЧНИК ПРАВДЫ — TAXONOMY в services/matching/app.py: по ней же ищет матчинг. Держать второй
список в приложении руками нельзя — разойдётся молча, и обложка начнёт врать про занятие.

Что делает: разбирает TAXONOMY, строит «ключ листа → подгруппа» и переписывает
kleal-app/src/covers.generated.ts. Сами картинки лежат на сервере в /var/www/kleal/covers/<подгруппа>.jpg
и этим скриптом не трогаются: их опись — covers_manifest.json рядом.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent          # kleal-ms
APP = ROOT.parent / "kleal-app" / "src" / "covers.generated.ts"


def registry():
    """Общий с сервером реестр интересов: дерево, подписи на трёх языках и синонимы.

    Именно он — источник правды (см. шапку kleal-app/src/interests-wheel.ts): когда-то дерево
    жило ещё и литералом в приложении, списки разошлись на 128 ключей, и половину занятий нельзя
    было выбрать на экране. Второй копии здесь заводить нельзя по той же причине.
    """
    return json.loads((ROOT / "shared" / "interests.json").read_text())


def main():
    reg = registry()
    tree, labels, syn = reg["tree"], reg.get("labels", {}), reg.get("synonyms", {})

    leaf, sub_root, root_sub = {}, {}, {}
    for root, subs in tree.items():
        first = None
        for sub, leaves in (subs or {}).items():
            first = first or sub
            sub_root[sub] = root
            leaf.setdefault(sub, sub)              # сама подгруппа годится как тема
            for lf in leaves:
                k = str(lf).strip().lower()
                if k:
                    leaf.setdefault(k, sub)
        root_sub[root] = first                     # «sports» без уточнения → обложка первой подгруппы
    for a, k in syn.items():                       # «bike» → «cycling» → endurance
        s = leaf.get(str(k).strip().lower())
        if s:
            leaf.setdefault(str(a).strip().lower(), s)

    # ПОДПИСИ. Название затеи человек пишет словами и на своём языке: «Консоли», «Настолки»,
    # «Juegos de mesa». Без этой таблицы русское название не находило ничего и получало общую
    # обложку — что и было видно на экране: у затеи «Консоли» стояла картинка «люди болтают».
    norm = lambda s: re.sub(r"[^0-9a-zа-яё]+", "", str(s).lower())
    label = {}
    for key, tr in labels.items():
        sub = leaf.get(str(key).strip().lower()) or root_sub.get(str(key).strip().lower())
        if not sub or not isinstance(tr, dict):
            continue
        for lang in ("ru", "en", "es"):
            w = norm(tr.get(lang))
            if len(w) >= 3:
                label.setdefault(w, sub)

    key = lambda k: k if re.fullmatch(r"[a-z_][a-z0-9_]*", k) else f"'{k}'"
    out = ["/**",
           " * Обложка подкатегории: какая тема к какой подгруппе относится.",
           " *",
           " * СГЕНЕРИРОВАНО из общего реестра kleal-ms/shared/interests.json скриптом",
           " * kleal-ms/tools/sync_covers.py. РУКАМИ НЕ ПРАВИТЬ: разойдётся с тем, по чему ищет матчинг.",
           " *",
           " * Зачем таблица в приложении, а не поле в ответе. Тема интента — ключ из того же реестра",
           " * («padel», «boardgames», «vinyl»), и подгруппа по нему находится точным поиском. Значит",
           " * картинку можно выбрать мгновенно и без запроса: ни сервер, ни модель для этого не нужны.",
           " */", "",
           f"/** Ключ темы или синоним → подгруппа. {len(leaf)} ключей на {len(sub_root)} подгрупп. */",
           "export const TOPIC_SUB: Record<string, string> = {"]
    out += [f"  {key(k)}: '{leaf[k]}'," for k in sorted(leaf)]
    out += ["};", "",
            "/** Подпись на любом из трёх языков → подгруппа: название затеи пишут словами. */",
            "export const LABEL_SUB: Record<string, string> = {"]
    out += [f"  {key(k)}: '{label[k]}'," for k in sorted(label)]
    out += ["};", "",
            "/** Корень без уточнения → обложка его первой подгруппы. */",
            "export const ROOT_SUB: Record<string, string> = {"]
    out += [f"  {k}: '{root_sub[k]}'," for k in sorted(root_sub) if root_sub[k]]
    out += ["};", "",
            "/** Все подгруппы, у которых есть обложка. Список ровно тот, что лежит на сервере. */",
            "export const COVER_SUBS: readonly string[] = [",
            "  " + ", ".join(f"'{s}'" for s in sorted(sub_root)) + ",",
            "] as const;", ""]
    APP.write_text("\n".join(out))
    print(f"{APP}: {len(leaf)} ключей, {len(label)} подписей, {len(sub_root)} подгрупп")


if __name__ == "__main__":
    main()
