# -*- coding: utf-8 -*-
"""§6 taxonomy + governance — unit + property (§23.3; §6 governance invariant)."""
import os
import sys
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.taxonomy import graph as TX, governance as GOV

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    check("TX1 resolve exact", TX.resolve("dota2") == ("games", "moba"))
    check("TX2 alias -> canonical", TX.norm("dota") == "dota2" and TX.resolve("dota") == ("games", "moba"))
    check("TX3 similarity exact=4", TX.similarity(["dota2"], ["dota"])[0] == 4)
    check("TX4 similarity sibling=3", TX.similarity(["dota2"], ["lol"])[0] == 3)
    check("TX5 similarity parent=2", TX.similarity(["dota2"], ["chess"])[0] == 2)
    check("TX6 similarity adjacent=1", TX.similarity(["coffee"], ["art"])[0] == 1)
    check("TX7 similarity none=0", TX.similarity(["coffee"], ["dota2"])[0] == 0)
    check("TX8 off-taxonomy literal", TX.similarity(["labubu"], ["labubu"])[0] == 4)
    check("TX9 negative edge", TX.is_negative("ranked", "casual"))
    check("TX10 complementary role (не similarity)", TX.is_complementary("support", "carry"))

    # Free-form canonicalization: compounds, languages and conservative domain boundaries.
    for left, right, level in (
        ("crypto", "trading forex", 3), ("blockchain", "forex", 3), ("web3", "nasdaq", 3),
        ("криптовалютами", "mercado de valores", 3), ("bitcoin", "инвестиции", 3),
        ("trail running", "ciclismo", 3), ("anime", "японская анимация", 4),
        ("language exchange", "practicar español", 3), ("street photography", "fotografía", 4),
    ):
        check("concept positive: %s / %s" % (left, right), TX.similarity([left], [right])[0] == level)
    for left, right in (
        ("stock market", "food market"), ("crypto", "software development"),
        ("gaming", "software engineering"), ("anime", "machine learning"),
        ("football", "financial markets"), ("language exchange", "currency exchange"),
        ("cryptography", "cryptocurrency"),
    ):
        check("concept negative: %s / %s" % (left, right), TX.similarity([left], [right])[0] == 0)

    # A request bridge must never leak into another worker thread.
    TX.set_bridge(lambda _x: True)
    child = []
    th = threading.Thread(target=lambda: child.append(TX.similarity(["alphafoo"], ["betabar"])[0]))
    th.start(); th.join()
    check("bridge is request-thread-local", child == [0])
    check("bridge remains active in owner thread", TX.similarity(["alphafoo"], ["betabar"])[0] == 3)
    TX.set_bridge(None)

    # --- §6 governance: добавление alias НЕ повышает existing pair (shadow replay) ---
    before = TX.similarity(["dota2"], ["chess"])[0]     # parent=2
    res_ok = GOV.add_alias("dota_ru", "dota2", owner="taxo-team")
    after = TX.similarity(["dota2"], ["chess"])[0]
    check("GOV1 валидный alias принят", res_ok["ok"])
    check("§6 alias НЕ повысил existing pair (dota2/chess)", after == before)
    check("GOV2 new alias резолвится", TX.norm("dota_ru") == "dota2")
    # alias на несуществующую сущность -> отклонён
    res_bad = GOV.add_alias("xyz", "nonexistent_entity", owner="t")
    check("GOV3 alias на неизвестную сущность отклонён", not res_bad["ok"])
    # governance-валидация: у ребра есть owner + review_state
    check("GOV4 governance metadata валидна", GOV.validate_governance() == [])
    check("GOV5 edge версионирован", GOV.EDGE_META[("alias", "dota_ru")]["version"] == 1)

    print("\n§6 taxonomy: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
