#!/usr/bin/env python3
"""Генератор подписей предметов затей — ru / en / es — нашей нейронкой (Qwen3-32B, self-hosted).

Для 55 ключей без подписи запрашивает модель пакетами по 10 и сохраняет
прошедшие механическую проверку в services/buddy/subject_words.json.

Запуск (с нужными переменными окружения):
    LLM_URL=http://127.0.0.1:17071 V2_MODEL=qwen3_self python3 tools/gen_subject_words.py
"""
import os, sys, json, time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)   # kleal-ms/

for _p in (
    os.path.join(_ROOT, "shared"),
    os.path.join(_ROOT, "services", "buddy"),
):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import llm_client
import config

MODEL_ID = config.MODEL_ID
llm_complete = llm_client.llm_complete

print(f"Модель: {MODEL_ID}  |  LLM_URL: {llm_client.LLM_URL}")

# Все 55 ключей без подписи в _TOPIC_RU и таксономии (измерено 17.09.2026)
KEYS = [
    "accessories", "barcelona", "beach", "bike ride", "boat", "children", "coach",
    "collaborative programmin", "cryptocurrencies", "cryptocurrency", "development",
    "drawing", "dry pool", "exit strategies", "exotic fruits", "funding", "girl",
    "harry potter", "hiking trails", "hip hop", "japan", "listen", "market", "moms",
    "need", "options", "over", "parties", "personal projects", "podcasts", "pool",
    "project", "projects", "prosecco", "pvp", "ride", "sea", "shisha", "smart",
    "smart contract", "smart contracts", "socializing", "street", "technology",
    "themed evening", "trails", "training technique", "typescript", "umbrella",
    "white wine", "wine tasting", "work", "world of warcraft", "year", "компании"
]

SYSTEM = """\
You label topic keywords for a social meetup app. Each keyword names the topic of a meetup intent.
Labels appear in phrases: Russian «Поговорить про X», English «Talk about X», Spanish «Hablar de X».

Label rules:
- "ru", "en", "es": 1-2 words (3-4 only for well-known proper nouns like "World of Warcraft")
- Noun or noun phrase, title case
- Proper nouns (brands, game titles, franchises): keep standard international spelling in all three languages (TypeScript stays TypeScript; PvP stays PvP; Prosecco stays Prosecco in all three)
- "ru" MUST use Cyrillic UNLESS the term is a proper noun that conventionally stays Latin (then ru may equal en exactly)
- "subject": true  — a real activity, hobby, interest, place, or recognisable proper noun
- "subject": false — person type (girl, moms, children), bare verb (work, listen, need), time/quantity word (year, over), truncated/corrupted word (collaborative programmin), standalone adjective without context (smart), or Russian generic word (компании)

Return ONLY valid JSON — no markdown fences, no prose, no comments:
{"keyword": {"ru": "...", "en": "...", "es": "...", "subject": true}, ...}
"""

def ask_model(keys):
    user_msg = "Provide labels for these topic keywords:\n" + json.dumps(keys, ensure_ascii=False)
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": user_msg},
    ]
    try:
        raw = str(llm_complete(MODEL_ID, msgs, 0.2) or "")
    except Exception as e:
        return None, f"llm error: {e}"
    start = raw.find('{')
    end   = raw.rfind('}') + 1
    if start < 0 or end <= start:
        return None, f"no JSON in: {raw[:200]!r}"
    try:
        return json.loads(raw[start:end]), None
    except json.JSONDecodeError as e:
        return None, f"JSON parse: {e}: {raw[start:end][:300]!r}"

def validate(key, entry):
    if not isinstance(entry, dict):
        return False, "not a dict"
    if not entry.get("subject", True):
        return False, "subject=false"
    for lang in ("ru", "en", "es"):
        v = str(entry.get(lang, "")).strip()
        if not v:
            return False, f"{lang} empty"
        if len(v.split()) > 3:
            return False, f"{lang} too long: {v!r}"
        if any(c in v for c in (".", ",", '"', "'")):
            return False, f"{lang} has punctuation: {v!r}"
    ru = str(entry.get("ru", "")).strip()
    en = str(entry.get("en", "")).strip()
    has_cyr = any('а' <= c.lower() <= 'я' or c == 'ё' for c in ru)
    if not has_cyr and ru.lower() != en.lower():
        return False, f"ru без кириллицы и != en: ru={ru!r} en={en!r}"
    if ru.lower() == key.lower():
        return False, f"ru = ключ: {ru!r}"
    return True, ""

def run():
    batch_size = 10
    results  = {}
    discarded = {}
    batches = [KEYS[i:i+batch_size] for i in range(0, len(KEYS), batch_size)]

    for i, batch in enumerate(batches):
        print(f"\n--- Пачка {i+1}/{len(batches)}: {batch}")
        data, err = ask_model(batch)
        if data is None:
            print(f"  ERR1: {err}. Повтор через 3с...")
            time.sleep(3)
            data, err2 = ask_model(batch)
            if data is None:
                print(f"  ERR2: {err2}. Пачка пропущена.")
                for k in batch:
                    discarded[k] = f"model error: {err2}"
                continue

        for key in batch:
            entry = data.get(key)
            if entry is None:
                discarded[key] = "нет в ответе"
                print(f"  SKIP {key!r}: нет в ответе")
                continue
            ok, reason = validate(key, entry)
            if ok:
                results[key] = {
                    "ru": entry["ru"].strip(),
                    "en": entry["en"].strip(),
                    "es": entry["es"].strip(),
                }
                print(f"  OK   {key!r}: ru={entry['ru']!r}  en={entry['en']!r}  es={entry['es']!r}")
            else:
                discarded[key] = reason
                print(f"  SKIP {key!r}: {reason}")

        if i < len(batches) - 1:
            time.sleep(1)

    out_path = os.path.join(_ROOT, "services", "buddy", "subject_words.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, sort_keys=True)

    print(f"\n=== ИТОГ ГЕНЕРАЦИИ ===")
    print(f"Принято : {len(results)}/{len(KEYS)}")
    print(f"Отброшено: {len(discarded)}")
    for k, r in sorted(discarded.items()):
        print(f"  DISCARD {k!r}: {r}")
    print(f"Файл: {out_path}")
    return results, discarded

if __name__ == "__main__":
    run()
