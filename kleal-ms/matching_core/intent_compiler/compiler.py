# -*- coding: utf-8 -*-
"""§5 Intent Compiler — LLM как parser/формулировщик, НЕ источник права/финальной логики.

Любой LLM output недоверенный: проходит JSON-schema validation, allowlists, normalizers, policy checks
(§5, §23.2 п.6 — LLM не обходит hard gates). Компилятор ДЕТЕРМИНИРОВАН: на вход — уже распарсенные слоты
(граница LLM снаружи), на выход — canonical draft intent + confidence + hard/soft + clarification.
"""
from ..contracts import intent as IC

ALLOWED_MODES = ("offline", "online", "hybrid")
ALLOWED_FORMATS = ("1:1", "small_group", "group", "event", "room")

# §5.1 hard vs soft. Маркеры мягкости/жёсткости во фразах пользователя.
_SOFT_MARKERS = ("желательно", "preferably", "рядом", "ideally", "можно")
_HARD_MARKERS = ("только", "only", "must", "обязательно", "строго")

# Ограничения, исключающие значительную долю людей / раскрывающие sensitive / влияющие на safety —
# ОБЯЗАТЕЛЬНО в summary + подтверждение пользователем (§5.1 «Правило подтверждения»).
_NEEDS_CONFIRM = ("requiredLanguages", "dating", "minAge", "maxAge", "verifiedOnly")


def _normalize_slots(slots):
    """Allowlists + нормализация недоверенного ввода (§5). Неизвестные значения не подставляются скрытно."""
    s = dict(slots or {})
    s["topics"] = [str(t).strip().lower() for t in (s.get("topics") or []) if str(t).strip()]
    mode = str(s.get("mode") or "offline").lower()
    s["mode"] = mode if mode in ALLOWED_MODES else "offline"
    fmt = str(s.get("format") or "1:1")
    s["format"] = fmt if fmt in ALLOWED_FORMATS else "1:1"
    s["requiredLanguages"] = [str(l)[:2].lower() for l in (s.get("requiredLanguages") or [])]
    return s


def classify_constraints(slots):
    """§5.1: разнести ограничения на hard / soft. Возвращает (hard[], soft[], needs_confirm[])."""
    hard, soft, confirm = [], [], []
    text = " ".join(str(v) for v in slots.values() if isinstance(v, str)).lower()
    # локация: «желательно рядом» -> soft; явный radius без soft-маркера -> hard-ish
    if slots.get("location_preference") == "soft" or any(m in text for m in _SOFT_MARKERS):
        soft.append("location")
    if slots.get("requiredLanguages"):
        hard.append("requiredLanguages"); confirm.append("requiredLanguages")
    if slots.get("type") == "dating":
        hard.append("dating_mode"); confirm.append("dating")
    for k in ("minAge", "maxAge", "verifiedOnly"):
        if slots.get(k):
            confirm.append(k)
    if slots.get("mode") == "online":
        soft.append("mode_online_fallback")
    return hard, soft, sorted(set(confirm))


# §5: типовая (JSON-schema-подобная) валидация недоверенного LLM-вывода, stdlib-only (без jsonschema).
_SLOT_SCHEMA = {"topics": list, "type": str, "mode": str, "format": str, "requiredLanguages": list,
                "radiusKm": (int, float), "minAge": (int, float), "maxAge": (int, float), "city": str}


def validate_schema(slots):
    """§5: LLM output недоверенный -> проверка типов по схеме. Возвращает (ok, errors[]). LLM это не обходит."""
    errs = []
    for k, typ in _SLOT_SCHEMA.items():
        v = (slots or {}).get(k)
        if v is not None and not isinstance(v, typ):
            errs.append("%s: expected %s, got %s" % (k, getattr(typ, "__name__", typ), type(v).__name__))
    return (len(errs) == 0, errs)


def blocking_clarifications(compiled, domain):
    """§5: незаполненные КАНОНИЧЕСКИЕ hard-слоты с unknown_behavior∈{ask,reject_if_false} блокируют запуск
    (needs_confirmation теперь ПОТРЕБЛЯЕТСЯ). Возвращает список slot-имён (пусто -> запуск разрешён)."""
    from ..taxonomy import canonical as CANON
    f = compiled["flat"]
    filled = {
        "purpose": bool(f.get("purpose") or f.get("activity") or f.get("topics")),
        "time.window": bool((f.get("time") or {}).get("windows")),
        "location.area_or_online": bool((f.get("location") or {}).get("city") or f.get("mode") == "online"),
    }
    blockers = []
    for s in CANON.hard_slots(domain):
        name, unk = s.get("slot"), s.get("unknown")
        if unk in ("ask", "reject_if_false") and name in filled and not filled[name]:
            blockers.append(name)
    return blockers


def confidence(slots):
    """Простой детерминированный confidence 0..1 по заполненности ключевых слотов (не LLM-число)."""
    keys = ("topics", "type", "mode", "time", "location")
    have = sum(1 for k in keys if slots.get(k))
    return round(have / len(keys), 3)


# Вердикт#3: LLM формирует СТРУКТУРИРОВАННЫЙ вход детерминированного движка — качество компиляции критично.
# Поэтому по каждому полю храним происхождение и уверенность.
PROVENANCE = ("explicit", "inferred", "defaulted")
HARD_CONFIDENCE_MIN = 0.6                              # порог обязательного уточнения по hard-полям


def field_provenance(slots, provenance=None, field_confidence=None):
    """Вердикт#3: пометить каждое поле explicit | inferred | defaulted + confidence 0..1.
      explicit  — пользователь сказал явно; inferred — LLM вывел; defaulted — подставлено по умолчанию.
    provenance/field_confidence — опциональные подсказки от LLM-границы (снаружи); при отсутствии —
    эвристика: заполненное поле → explicit(1.0), пустое → defaulted(0.5)."""
    prov, conf = provenance or {}, field_confidence or {}
    out = {}
    for k, v in (slots or {}).items():
        src = prov.get(k)
        if src not in PROVENANCE:
            src = "explicit" if v not in (None, [], "", {}) else "defaulted"
        c = conf.get(k)
        out[k] = {"value": v, "source": src,
                  "confidence": float(c if c is not None else (1.0 if src == "explicit" else 0.5))}
    return out


# hard-токен (из classify_constraints) -> имя слота в provenance-карте (Вердикт#3): напр. dating -> 'type'.
_HARD_TOKEN_FIELD = {"dating_mode": "type"}

# Аудит #13 — НЕТ единого универсального порога для всех hard-слотов. Правило на поле:
#   "explicit" — принимать только explicit (inferred/defaulted при ЛЮБОй уверенности -> уточнение);
#   float      — explicit ИЛИ confidence >= порог.
DEFAULT_HARD_CONFIDENCE = HARD_CONFIDENCE_MIN            # 0.6 для неперечисленных hard-полей
FIELD_CONFIDENCE_RULE = {
    "dating_mode": "explicit",          # dating -> explicit only
    "type": "explicit",                 # purpose/тип режима -> explicit
    "purpose": 0.9,                     # purpose -> explicit / очень высокая уверенность
    "verifiedOnly": "explicit",         # safety -> explicit / rule-derived only
    "minAge": "explicit", "maxAge": "explicit",   # sensitive preference -> explicit only
    "gender": "explicit", "orientation": "explicit",
    "requiredLanguages": 0.8,           # hard exclusionary language -> высокий порог
    "format": 0.8,                      # exact format
    "activity": 0.65,                   # activity subtype
    "role": 0.65,
}


def _field_ok(source, confidence, rule):
    """Аудит #13: проходит ли поле по своему правилу. explicit — всегда; иначе по порогу/или запрещено."""
    if source == "explicit":
        return True
    if rule == "explicit":
        return False
    return float(confidence) >= float(rule)


def low_confidence_hard_fields(fields, hard, *, rules=None):
    """Аудит #13 (+Вердикт#3): field-specific обязательное уточнение по HARD-полям. Для каждого hard-токена
    берётся его правило (explicit-only / порог), а не один общий 0.6. hard-токен резолвится в реальный слот
    (dating_mode -> type). Заявленное-но-неуверенное inferred поле -> уточнение; отсутствующее -> это missing
    (blocking_clarifications), здесь не флагаем."""
    rules = rules or FIELD_CONFIDENCE_RULE
    out = []
    for k in hard:
        field_name = _HARD_TOKEN_FIELD.get(k, k)
        f = fields.get(field_name)
        if f is None:
            continue
        rule = rules.get(k, rules.get(field_name, DEFAULT_HARD_CONFIDENCE))
        if not _field_ok(f.get("source", "defaulted"), f.get("confidence", 0.0), rule):
            out.append(k)
    return out


def compile_intent(slots, *, intent_id, user_id, created_at=None, expires_at=None, ttl_sec=None,
                   raw_text=None, taxonomy_version=None, provenance=None, field_confidence=None):
    """§5 + Вердикт#3: собрать canonical draft intent из недоверенных слотов. Возвращает
    {intent, flat, confidence, hard, soft, needs_confirmation, schema_ok/errors, fields, raw_text,
    taxonomy_version, low_confidence_hard} — с сохранением исходного текста и версии таксономии."""
    schema_ok, schema_errors = validate_schema(slots)     # §5: недоверенный вход валидируется по схеме
    s = _normalize_slots(slots)
    hard, soft, confirm = classify_constraints(s)
    fields = field_provenance(slots, provenance, field_confidence)   # Вердикт#3 per-field provenance
    low_conf_hard = low_confidence_hard_fields(fields, hard)
    exp = expires_at if expires_at is not None else ((float(created_at) + ttl_sec) if (created_at is not None and ttl_sec) else None)
    it = IC.build_intent(
        intent_id, user_id, s.get("type") or "social_meet",
        activity=s.get("activity"), purpose=s.get("purpose"), topics=s.get("topics"),
        time=s.get("time_block") or ({"windows": s["time"]} if isinstance(s.get("time"), list) else s.get("time")),
        location={"city": s.get("city"), "radiusKm": s.get("radiusKm"), "coarse_cell": s.get("coarse_cell"), "safe_zones": []},
        mode=s["mode"], fmt=s["format"],
        target={"required_roles": s.get("role"), "level": s.get("level"), "directed_preferences": s.get("target")},
        domain_details={"requiredLanguages": s.get("requiredLanguages")},
        fallback={"allowed_dimensions": s.get("fallback_dimensions") or [], "consent": s.get("fallback_consent") or {}},
        created_at=created_at, expires_at=exp,
    )
    # Вердикт#3: сохранить исходный текст + версию таксономии в самом интенте (для decision trace / аудита)
    it["provenance"] = {"raw_text": raw_text, "taxonomy_version": taxonomy_version, "fields": fields}
    return {"intent": it, "flat": IC.flat(it), "confidence": confidence(s),
            "hard": hard, "soft": soft, "needs_confirmation": confirm,
            "schema_ok": schema_ok, "schema_errors": schema_errors,
            "fields": fields, "raw_text": raw_text, "taxonomy_version": taxonomy_version,
            "low_confidence_hard": low_conf_hard,
            "requires_clarification": bool(low_conf_hard)}
