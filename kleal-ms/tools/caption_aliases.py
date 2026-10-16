"""Собрать словарь «подпись -> ключ» для тех подписей, которые сами ни во что не сводятся.

ЗАЧЕМ: подпись — это то, что человек видит на экране. Если он повторит её словами, сервис обязан
её понять. Замер 17.09.2026: половина подписей не понималась. Занятое имя не перебивается.
"""
import io, json, sys, importlib.util
sys.path.insert(0, "/opt/kleal/kleal-ms")
spec = importlib.util.spec_from_file_location("b", "/opt/kleal/kleal-ms/services/buddy/app.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
OUT = "/opt/kleal/kleal-ms/services/buddy/caption_aliases.json"
try:
    cur = json.load(io.open(OUT, encoding="utf-8"))
except Exception:
    cur = {}
added = 0
for key in sorted(m.BROAD_OF):
    for lang in ("ru", "en", "es"):
        cap = str(m.subject_word(key, lang) or "").strip().lower()
        if not cap or cap in cur:
            continue
        if m.norm_topic(cap):
            continue
        cur[cap] = key
        added += 1
io.open(OUT, "w", encoding="utf-8").write(json.dumps(cur, ensure_ascii=False, indent=1, sort_keys=True))
print("подписей в словаре:", len(cur), "| дописано:", added)
