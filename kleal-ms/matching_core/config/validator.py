# -*- coding: utf-8 -*-
"""§9.5 / §21.4 — Canonical configuration validator.

Единственный источник весов/приоров/порогов — sha-pinned `config/matching-core.yaml` (§23.2 п.11).
Загрузка проверяет sha256 и валидирует структуру; при ЛЮБОМ рассогласовании бросает `ConfigError`
(§21.4: config/taxonomy mismatch → stop, не смешивать версии). Парсер — детерминированный мини-YAML
(ограниченное подмножество), чтобы не тянуть PyYAML и не словить YAML-1.1 сюрприз (неквотированный
`09:00` иначе читается как 540).

CI-проверки (§9.5):
  - сумма весов домена = 1.0;
  - отсутствие неизвестных feature keys;
  - диапазоны priors / lambda / thresholds ∈ [0,1];
  - наличие обязательных секций (feature_groups, domains, semantic_tiers, user_facing_bands);
  - наличие config_version (совместимость версий проверяется вызывающим слоем).
"""
import os
import hashlib

# sha256 канонического конфига — ЖИВОГО файла config/Kleal_Matching_Core_Config_v2.yaml, а не
# исходного пина Приложения A (21505ccb…). 22.07 веса social_meet были осознанно перевешены
# (semantic_activity 0.18 -> 0.30, коммит «Больше тем = выше»), и core_v2 тогда перепиновали вместе
# с ними. Пакет matching_core собирался «начисто по спеке» и взял sha ИЗ ДОКУМЕНТА, то есть
# доретюнинговый. С этого момента sha-проверка падала на живом конфиге, оба движка уходили в
# fail-safe (§21.4) и ранжировал легаси-скорер v1 — то есть перевес, ради которого всё делалось,
# не действовал ни дня. Пин обязан следовать за конфигом, иначе он ловит не дрейф, а сам себя.
PINNED_SHA = "d804df8e2d14c0b306263d5178eb39d98f284335a2fb671bbd413b49435cb197"

# 7 канонических feature groups (§6.1 / §9.1) — единственно допустимые ключи весов домена.
FEATURE_KEYS = ("semantic_activity", "time_feasibility", "location_feasibility", "mode_format",
                "directed_preferences", "social_context", "domain_constraints")

_HERE = os.path.dirname(os.path.abspath(__file__))
# ОДИН файл на весь проект. Здесь лежала вторая копия (matching-core.yaml), отличавшаяся ровно
# шестью весами social_meet: app.py грузил канонический, а load_config() без аргумента — локальный,
# так что «единственный источник истины» существовал в двух экземплярах с разными числами.
DEFAULT_CONFIG_PATH = os.path.join(_HERE, "..", "..", "config", "Kleal_Matching_Core_Config_v2.yaml")


class ConfigError(Exception):
    """Любая проблема загрузки/валидации конфига. Вызывающий слой обязан fail-closed (§21.4)."""


# ----------------------------------------------------------------- детерминированный мини-YAML
def _scalar(s):
    t = s.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        return t[1:-1]
    low = t.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", ""):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def parse_mini_yaml(text):
    """Ограниченное подмножество: вложенные map, списки скаляров, скаляры. Двухпробельные отступы."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        lines.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    pos = [0]

    def block(indent):
        _first_i, first_s = lines[pos[0]]
        if first_s.startswith("- "):
            out = []
            while pos[0] < len(lines):
                i, s = lines[pos[0]]
                if i != indent or not s.startswith("- "):
                    break
                out.append(_scalar(s[2:]))
                pos[0] += 1
            return out
        out = {}
        while pos[0] < len(lines):
            i, s = lines[pos[0]]
            if i < indent:
                break
            if i > indent:
                raise ConfigError("unexpected indent: %r" % s)
            if ":" not in s:
                raise ConfigError("bad line: %r" % s)
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            pos[0] += 1
            if v == "":
                nxt = pos[0] < len(lines) and (lines[pos[0]][0] > i or
                                               (lines[pos[0]][0] == i and lines[pos[0]][1].startswith("- ")))
                out[k] = block(lines[pos[0]][0]) if nxt else None
            else:
                out[k] = _scalar(v)
        return out

    return block(0) if lines else {}


# ----------------------------------------------------------------- загрузка + валидация
def _in_unit(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0


def validate(cfg):
    """§9.5 CI-проверки над разобранным конфигом. Бросает ConfigError при первом нарушении."""
    if not cfg.get("config_version"):
        raise ConfigError("config_version missing")
    fg = cfg.get("feature_groups") or {}
    for k in FEATURE_KEYS:
        p = (fg.get(k) or {}).get("unknown_prior")
        if not _in_unit(p):
            raise ConfigError("bad unknown_prior for feature group %r: %r" % (k, p))
    doms = cfg.get("domains") or {}
    if not doms:
        raise ConfigError("domains section missing/empty")
    for d, dc in doms.items():
        w = (dc or {}).get("weights") or {}
        extra = set(w) - set(FEATURE_KEYS)
        if extra:
            raise ConfigError("unknown feature keys in domain %r: %s" % (d, sorted(extra)))
        s = sum(float(w.get(k, 0) or 0) for k in FEATURE_KEYS)
        if abs(s - 1.0) > 1e-6:
            raise ConfigError("weights of domain %r sum to %.6f, must be 1.0" % (d, s))
        for t in ("uncertainty_lambda", "outreach_min_lcb", "discovery_min_lcb",
                  "outreach_min_coverage", "discovery_min_coverage"):
            if not _in_unit(dc.get(t)):
                raise ConfigError("bad %s in domain %r: %r" % (t, d, dc.get(t)))
    for req in ("semantic_tiers", "user_facing_bands"):
        if not isinstance(cfg.get(req), dict):
            raise ConfigError("required section %r missing" % req)
    # user_facing_bands: пороги в [0,1]
    for band, bc in (cfg.get("user_facing_bands") or {}).items():
        for key in ("min_lcb", "min_coverage", "max_coverage"):
            if key in (bc or {}) and not _in_unit(bc[key]):
                raise ConfigError("bad band threshold %s.%s: %r" % (band, key, bc[key]))
    return cfg


def load_config(path=None, expect_sha=PINNED_SHA):
    """Читает + sha-verify + parse + validate. Возвращает cfg с добавленными `_sha256` и `_path`.
    §21.4: несовпадение sha или невалидная структура → ConfigError (вызывающий fail-closed, не мешает версии)."""
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "rb") as f:
        blob = f.read()
    sha = hashlib.sha256(blob).hexdigest()
    if expect_sha and sha != expect_sha:
        raise ConfigError("config sha mismatch: got %s…, expected %s… (§21.4 stop, don't mix)"
                          % (sha[:12], expect_sha[:12]))
    cfg = parse_mini_yaml(blob.decode("utf-8"))
    validate(cfg)
    cfg["_sha256"] = sha
    cfg["_path"] = path
    return cfg


def config_health(path=None):
    """§21.4 деградация: неблокирующая проверка. Возвращает {ok, config_version, config_sha, error}."""
    try:
        cfg = load_config(path)
        return {"ok": True, "config_version": cfg.get("config_version"),
                "config_sha": cfg["_sha256"][:12], "error": None}
    except Exception as e:
        return {"ok": False, "config_version": None, "config_sha": None, "error": str(e)}


def _major(v):
    import re
    m = re.search(r"(\d+)", str(v or ""))
    return m.group(1) if m else None


def check_version_compat(cfg, *, model_version=None, policy_version=None, expected_config=None):
    """§9.5 CI: совместимость config_version с model/policy version. Major-версии обязаны совпадать
    (config matching-core-2.x ↔ pol-2.x ↔ model *-2*). Возвращает (ok, problems[])."""
    problems = []
    cv = cfg.get("config_version")
    if expected_config and cv != expected_config:
        problems.append("config_version %s != expected %s" % (cv, expected_config))
    cmaj = _major(cv)
    if policy_version and cmaj and _major(policy_version) and cmaj != _major(policy_version):
        problems.append("config major %s != policy major %s" % (cmaj, _major(policy_version)))
    if model_version and cmaj and _major(model_version) and cmaj != _major(model_version):
        problems.append("config major %s != model major %s" % (cmaj, _major(model_version)))
    return (len(problems) == 0, problems)


def check_evidence_id_uniqueness(feature_evidence):
    """§9.5 CI: один `evidence_id` не должен давать вес НЕСКОЛЬКИМ независимым feature groups (double-count
    guard, C#3). feature_evidence = {group: [evidence_id,...]}. Возвращает (ok, duplicates[])."""
    seen, dups = {}, []
    for group, ids in (feature_evidence or {}).items():
        for eid in ids:
            if eid in seen and seen[eid] != group:
                dups.append((eid, seen[eid], group))
            else:
                seen[eid] = group
    return (len(dups) == 0, dups)
