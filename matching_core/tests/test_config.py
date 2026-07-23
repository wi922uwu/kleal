# -*- coding: utf-8 -*-
"""§9.5 config validator — unit + property tests (§23.3 DoD)."""
import os
import sys
import copy

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    # --- load: sha совпадает, конфиг валиден ---
    cfg = V.load_config()
    check("CFG1 load_config ok", isinstance(cfg, dict))
    check("CFG2 sha pinned", cfg["_sha256"] == V.PINNED_SHA)
    check("CFG3 config_version present", bool(cfg.get("config_version")))

    # --- property: у КАЖДОГО домена сумма весов = 1.0, ключи ⊆ 7 канонических (§9.5) ---
    ok_sum = ok_keys = True
    for d, dc in cfg["domains"].items():
        w = dc["weights"]
        if abs(sum(float(w.get(k, 0) or 0) for k in V.FEATURE_KEYS) - 1.0) > 1e-6:
            ok_sum = False
        if set(w) - set(V.FEATURE_KEYS):
            ok_keys = False
    check("CFG4 property: все веса домена = 1.0", ok_sum)
    check("CFG5 property: только канонические feature keys", ok_keys)

    # --- fail-closed: неверный sha -> ConfigError (§21.4) ---
    try:
        V.load_config(expect_sha="deadbeef" * 8)
        check("CFG6 sha mismatch -> raise", False)
    except V.ConfigError:
        check("CFG6 sha mismatch -> raise (§21.4)", True)

    # --- validate ловит битые конфиги (веса != 1.0) ---
    bad = copy.deepcopy(cfg)
    first_dom = next(iter(bad["domains"]))
    bad["domains"][first_dom]["weights"]["semantic_activity"] += 0.5
    try:
        V.validate(bad)
        check("CFG7 сумма весов != 1.0 -> raise", False)
    except V.ConfigError:
        check("CFG7 сумма весов != 1.0 -> raise", True)

    # --- validate ловит неизвестный feature key ---
    bad2 = copy.deepcopy(cfg)
    bad2["domains"][first_dom]["weights"]["bogus_feature"] = 0.0
    try:
        V.validate(bad2)
        check("CFG8 неизвестный feature key -> raise", False)
    except V.ConfigError:
        check("CFG8 неизвестный feature key -> raise", True)

    # --- validate ловит prior вне [0,1] ---
    bad3 = copy.deepcopy(cfg)
    bad3["feature_groups"]["semantic_activity"]["unknown_prior"] = 1.5
    try:
        V.validate(bad3)
        check("CFG9 prior вне [0,1] -> raise", False)
    except V.ConfigError:
        check("CFG9 prior вне [0,1] -> raise", True)

    # --- config_health: неблокирующая деградация ---
    h = V.config_health()
    check("CFG10 config_health ok", h["ok"] and h["config_sha"] == V.PINNED_SHA[:12])
    hbad = V.config_health(path=os.path.abspath(__file__))  # не-yaml файл
    check("CFG11 config_health на битом -> ok:false, не бросает", hbad["ok"] is False)

    print("\nconfig validator: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
