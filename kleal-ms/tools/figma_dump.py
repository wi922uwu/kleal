# -*- coding: utf-8 -*-
"""Дамп структуры борда Figma в текст — тем же форматом, что docs/board_1to1_structure.txt.

    python3 tools/figma_dump.py <fileKey> <nodeId> [out.txt]
    python3 tools/figma_dump.py 6VuVJdvfsMlQuzlzZ2RD3l 2247:44703 docs/board_group_structure.txt

ЗАЧЕМ ЭТОТ СКРИПТ. Борд — источник копирайта и порядка экранов, а доступ к нему рвался уже
трижды: сначала кончалась квота Dev Mode seat у MCP-коннектора (июль), потом MCP требовал
десктопную Figma, которой на машине нет. REST API с персональным токеном не зависит ни от того,
ни от другого, и у чтения файлов нет той квоты. Токен лежит в ~/.figma_token (chmod 600) или в
FIGMA_TOKEN; в репозиторий он не попадает.

Формат вывода намеренно совпадает со старым дампом 1:1: имена ТЕКСТОВЫХ СЛОЁВ — это и есть
копирайт кадров, поэтому text-узлы печатаются с содержимым дословно. Один запрос на секцию:
/v1/files/:key/nodes?ids=:id отдаёт всё поддерево целиком.
"""
import json
import os
import sys
import urllib.request

def token():
    t = os.environ.get("FIGMA_TOKEN", "").strip()
    if t:
        return t
    p = os.path.expanduser("~/.figma_token")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    sys.exit("нет токена: положи его в ~/.figma_token или в FIGMA_TOKEN")

def fetch(file_key, node_id):
    url = "https://api.figma.com/v1/files/%s/nodes?ids=%s" % (file_key, node_id.replace(":", "%3A"))
    req = urllib.request.Request(url, headers={"X-Figma-Token": token()})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))

# Служебный хром кадров: рисовать его в дампе — только шуметь. Ровно как в старом дампе,
# где Status Bar помечен «(chrome, omitted)».
CHROME = {"Status Bar", "Home Indicator", "status bar", "home indicator"}

def line(node, depth, out):
    t = node.get("type", "?").lower()
    name = str(node.get("name", ""))
    box = node.get("absoluteBoundingBox") or {}
    size = ""
    if box.get("width") is not None:
        size = "   [%dx%d]" % (round(box["width"]), round(box["height"]))
    pad = "  " * depth
    if name in CHROME:
        out.append(pad + "[%s]  (chrome, omitted)" % name)
        return False                      # внутрь хрома не ходим
    if t == "text":
        chars = str(node.get("characters", "")).replace("\n", "\\n")
        out.append(pad + 'text: "%s"%s' % (chars, size))
        return False                      # у текста нет интересных детей
    label = {"frame": "frame", "instance": "instance", "component": "component",
             "component_set": "component-set", "group": "group", "section": "section",
             "rectangle": "rectangle", "rounded_rectangle": "rounded-rectangle",
             "vector": "vector", "line": "line", "ellipse": "ellipse"}.get(t, t)
    out.append(pad + "%s %s%s" % (label, name, size))
    return True

def walk(node, depth, out, top=False):
    for ch in node.get("children") or []:
        if ch.get("visible") is False:
            continue
        if top:
            # Кадры верхнего уровня отбиваются линейкой — по ним глаз ищет экраны.
            out.append("")
            out.append("=" * 78)
            nm = str(ch.get("name", ""))
            box = ch.get("absoluteBoundingBox") or {}
            size = "   [%dx%d]" % (round(box.get("width", 0)), round(box.get("height", 0)))
            out.append("frame %s%s" % (nm, size))
            walk(ch, 1, out)
            continue
        if line(ch, depth, out):
            walk(ch, depth + 1, out)

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    file_key, node_id = sys.argv[1], sys.argv[2]
    data = fetch(file_key, node_id)
    node = (data.get("nodes") or {}).get(node_id, {}).get("document")
    if not node:
        sys.exit("узел %s не найден: %s" % (node_id, str(data)[:200]))
    out = ["Секция: %s · файл %s" % (node.get("name", node_id), file_key)]
    walk(node, 0, out, top=True)
    text = "\n".join(out) + "\n"
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", encoding="utf-8") as f:
            f.write(text)
        print("кадров: %d, строк: %d -> %s" % (text.count("=" * 78), len(out), sys.argv[3]))
    else:
        print(text)

if __name__ == "__main__":
    main()
