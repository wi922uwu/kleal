import re, sys, importlib.util, collections
sys.path.insert(0,"/opt/kleal/kleal-ms")
sp=importlib.util.spec_from_file_location("b","/opt/kleal/kleal-ms/services/buddy/app.py")
m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
import glob
LOG=sys.argv[1]
cnt=collections.Counter()
for line in open(LOG, encoding="utf-8", errors="replace"):
    if "ЗАТЕЯ НЕ ПРО ТО" not in line: continue
    mm=re.search(r"а разговор кончился на (.+)$", line.strip())
    if not mm: continue
    roots=[r.strip() for r in mm.group(1).split("/") if r.strip()]
    cnt["сводится" if any(m.norm_topic(r) for r in roots) else "НЕ сводится"]+=1
print("%s: всего %d, не сводится %d (%.0f%%)" % (LOG.split("/")[-1], sum(cnt.values()),
      cnt["НЕ сводится"], 100.0*cnt["НЕ сводится"]/max(sum(cnt.values()),1)))
