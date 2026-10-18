# -*- coding: utf-8 -*-
"""Сторож автосинонимов: файл подхватывается, ручной алиас важнее, свидания не принимаются, битый файл не ломает.
    python3 tools/auto_alias_smoke.py [--root=...]"""
import io, json, os, sys, tempfile, time
ROOT = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--root=")), os.environ.get("KLEAL_ROOT") or "/opt/kleal/kleal-ms")
fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
os.environ["KLEAL_AUTO_FILE"] = path
sys.path.insert(0, ROOT)
from matching_core.taxonomy import canonical as C, graph as G
fails = []
def check(name, ok, extra=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> " + str(extra)))
    if not ok: fails.append(name)
def write(words):
    json.dump({"version": 1, "words": words}, io.open(path, "w", encoding="utf-8"))
    C._AUTO["t"] = -1e9; os.utime(path, (time.time() + len(fails) + 1, time.time() + len(fails) + 1))
fam = next(n for n in C.NODES if n.startswith("I_") and C.NODES[n].get("macro") != "M_dating")
dating = next((n for n in C.NODES if n.startswith("I_") and C.NODES[n].get("macro") == "M_dating"), None)
manual = next(iter(C.ALIAS))
before = C._resolve("zzqx foraging thing")
check("незнакомое без файла — None", before[0] is None, before)
write({C._norm("zzqx foraging thing"): {"node": fam, "text": "zzqx foraging thing"},
       C._norm(manual): {"node": fam, "text": manual},
       C._norm("zzqx date thing"): {"node": dating, "text": "zzqx date thing"},
       C._norm("zzqx none"): {"node": None, "text": "zzqx none"}})
r = C._resolve("zzqx foraging thing")
check("автосиноним подхвачен как точный", r == (fam, True), r)
check("ручной алиас важнее автосинонима", C._resolve(manual)[0] == C.ALIAS[manual], C._resolve(manual))
check("узел свиданий не принимается", C._resolve("zzqx date thing")[0] is None, C._resolve("zzqx date thing"))
check("NONE не привязывает", C._resolve("zzqx none")[0] is None)
check("уровень 4 с самим узлом", G.similarity_detail([C.NODES[fam]["en"]], ["zzqx foraging thing"])[0] == 4,
      G.similarity_detail([C.NODES[fam]["en"]], ["zzqx foraging thing"]))
io.open(path, "w").write("{битый"); C._AUTO["t"] = -1e9; os.utime(path, (time.time() + 99, time.time() + 99))
check("битый файл — прежняя таблица", C._resolve("zzqx foraging thing")[0] == fam)
os.remove(path); C._AUTO["t"] = -1e9
check("файл удалён — автосинонимов нет", C._resolve("zzqx foraging thing")[0] is None)
# запреты и синонимы реестра в самом auto_alias (17.10.2026, вечер)
import importlib.util
_argv = sys.argv; sys.argv = ["auto_alias.py", "--root=" + ROOT]
_sp = importlib.util.spec_from_file_location("auto_alias", os.path.join(ROOT, "tools", "auto_alias.py"))
AA = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(AA); sys.argv = _argv
for w in ("fly agaric mushrooms", "мухоморы", "amanita muscaria", "magic mushrooms"):
    check("запрет: " + w, AA.banned(w))
for w in ("mushroom picking", "porcini mushrooms", "грибы", "лисички", "chanterelles"):
    check("не запрет: " + w, not AA.banned(w))
check("вид связи: буква из ответа", AA.related("x", "", fam, lambda s, u: " b ") == "B")
_reg = AA.registry_synonyms()
check("синонимы реестра: все к узлам I_", all(str(n).startswith("I_") for _, n, _k in _reg.values()), list(_reg.values())[:3])
print("\nСБОЕВ: %d" % len(fails)); sys.exit(1 if fails else 0)
