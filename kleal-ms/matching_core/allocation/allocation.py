# -*- coding: utf-8 -*-
"""§11 Allocation, fairness и рыночная ликвидность.

Allocation определяет, кому/сколько экспозиции дать ПОСЛЕ eligibility и relevance. Он НЕ меняет смысл
релевантности пары (§11). payment_status ЗАПРЕЩЁН как feature (§11.3, §23.2 п.14). Порядок rerank — §11.2.
"""
import zlib
from ..reciprocity_readiness.readiness import READINESS_RANK

# Аудит #11 — quality floor: сортировать сначала по классу решения (качество+право на outreach), затем
# по reciprocal, и лишь потом по readiness (исполнимость, НЕ качество человека).
DCLASS_RANK = {"strong_personal": 0, "usable_personal": 1, "discovery_only": 2, "clarification": 3, "no_outreach": 4}

TOP_N = 8
PER_BUCKET = 3                                    # diversity ось 1: интерес-bucket
PER_TIER = 4                                      # diversity ось 2: semantic tier (§11.2)
PER_SOURCE = 5                                    # diversity ось 3: retrieval source / intent interpretation
POPULARITY_CAP = 3                                # popularity concentration guard
EXPOSURE_CAP_DEFAULT = 50                         # per-user exposure cap за окно
EXPLORATION_QUOTA = 2                             # квота exploration-позиций (не один слот)
EXPLORATION_MIN_LCB = 0.4                         # Аудит #12: quality floor — не ниже min relevance…
EXPLORATION_MIN_COVERAGE = 0.4                    # …и min coverage (переопределяется доменным floor из ctx)
AREA_CAP_DEFAULT = 4                              # city/area supply balancing: не более N из одной зоны


class MonetizationViolation(Exception):
    pass


def exploration_eligible(item, min_lcb=EXPLORATION_MIN_LCB, min_coverage=EXPLORATION_MIN_COVERAGE):
    """Аудит #12 — quality floor для exploration. exploration может лишь ПЕРЕСТАВИТЬ позицию, поэтому
    кандидат допустим только если: не ниже min relevance (lcb) и min coverage floor И не `no_outreach`.
    policy/consent/tier/decision_class при этом НЕ меняются (переносятся as-is вызывающим _take)."""
    return (float(item.get("lcb") or 0) >= float(min_lcb)
            and float(item.get("coverage") or 0) >= float(min_coverage)
            and item.get("decision_class") != "no_outreach")


def assert_no_payment_feature(item):
    """§11.3: payment_status/subscription не может быть relevance/reciprocity/safety/allocation feature."""
    for k in ("payment_status", "subscription", "is_premium", "paid_boost"):
        if k in (item.get("_allocation_features") or {}):
            raise MonetizationViolation("payment feature in allocation: %s" % k)
    return True


NEAR_DUP_CAP = 2                                  # Вердикт#16: не более N почти-одинаковых результатов


def _dup_key(it):
    """Вердикт#16: ключ near-duplicate — bucket+tier+band+район+набор причин почти идентичны для UX."""
    c = it["cand"]
    return (it.get("bucket") or "other", it.get("tier") or "?", it.get("band"),
            str(c.get("area") or c.get("zone") or c.get("coarse_cell") or ""),
            tuple(it.get("reasons") or ()))


def _rotation_rank(it, seed):
    """Вердикт#16: controlled rotation при РАВНЫХ score — детерминированный crc32 (стабилен между
    процессами), стабильный внутри одного request (seed), но разный порядок между запросами/днями.
    seed='static' -> 0 (rotation выключена, тай-брейк падает на имя — обратная совместимость)."""
    if seed == "static":
        return 0
    nm = str(it["cand"].get("name", "")).strip().lower()
    return zlib.crc32(("%s|%s" % (seed, nm)).encode("utf-8")) & 0xffffffff


def rerank(items, intent, cfg=None, ctx=None):
    """§11.2 порядок: (1) убрать BLOCK/expired/capacity + near-dup; (2) сорт по reciprocal + readiness class
    (+ rotation при равенстве); (3) diversity; (4) exposure/fatigue caps; (5) exploration; (6) propensity.
    items[i] = {cand, tier, source, reciprocal, lcb, coverage, readiness, bucket, band, policy, exposure}."""
    ctx = ctx or {}
    cooldown = set(ctx.get("cooldown_pairs") or [])
    ignored = set(ctx.get("ignored_pairs") or [])               # Вердикт#16: cooldown после игнорирования
    exposure_ledger = ctx.get("exposure") or {}
    exposure_cap = int(ctx.get("exposure_cap", EXPOSURE_CAP_DEFAULT))
    reservation_full = set(ctx.get("reservation_full") or [])   # ресурсы (группа/событие) без capacity
    area_of = ctx.get("area_of") or {}                          # name -> зона (city/area supply balancing)
    area_cap = int(ctx.get("area_cap", AREA_CAP_DEFAULT))
    rotation_seed = ctx.get("request_id") or ctx.get("rotation_seed") or "static"   # Вердикт#16 rotation
    dedup_on = bool(ctx.get("dedup_near_duplicates"))            # Вердикт#16 near-dup (opt-in)

    # (1) убрать неподходящих: BLOCK/expired/capacity/cooldown/ignored/exposure/reservation-full
    live = []
    for it in items:
        assert_no_payment_feature(it)
        if it.get("policy") == "BLOCK" or it.get("expired") or it.get("capacity_exceeded"):
            continue
        nm = str(it["cand"].get("name", "")).strip().lower()
        if nm in cooldown or nm in ignored:
            continue                                # cooldown повторной/проигнорированной пары
        if exposure_ledger.get(nm, 0) >= exposure_cap:
            continue                                # per-user exposure cap
        if it.get("resource") in reservation_full:
            continue                                # reservation capacity исчерпана (§11.1)
        live.append(it)

    # (2) сорт (Аудит #11): quality floor (decision_class) -> reciprocal relevance -> readiness -> relevance
    # -> coverage -> rotation -> name. readiness — ИСПОЛНИМОСТЬ, а не качество: «open_now» больше не делает
    # посредственного кандидата лучшим. rotation — тай-брейк при равенстве (стабилен внутри request).
    live.sort(key=lambda x: (DCLASS_RANK.get(x.get("decision_class"), 5),
                             -float(x.get("reciprocal") or 0),
                             READINESS_RANK.get(x.get("readiness", "unknown"), 2),
                             -float(x.get("lcb") or 0), -float(x.get("coverage") or 0),
                             _rotation_rank(x, rotation_seed), str(x["cand"].get("name", ""))))

    # near-dup dedup — ПОСЛЕ сортировки (Вердикт#16), чтобы оставались ЛУЧШИЕ представители группы, а не
    # первые по входному порядку (retriever-порядок = source/best, НЕ reciprocal).
    if dedup_on:
        seen_dup, deduped = {}, []
        for it in live:
            dk = _dup_key(it)
            if seen_dup.get(dk, 0) >= NEAR_DUP_CAP:
                continue
            seen_dup[dk] = seen_dup.get(dk, 0) + 1
            deduped.append(it)
        live = deduped

    # (3)+(4) diversity ПО 3 ОСЯМ (bucket/tier/source) + popularity + area-balancing + top_n (§11.2)
    buckets = {it.get("bucket") or "other" for it in live}
    bcap = PER_BUCKET if len(buckets) > 2 else TOP_N
    seen_b, seen_t, seen_s, seen_area, seen_pop, out = {}, {}, {}, {}, {}, []

    def _passes(it):
        nm = str(it["cand"].get("name", "")).strip().lower()
        b, t, s = it.get("bucket") or "other", it.get("tier") or "?", it.get("source") or 0
        ar = area_of.get(nm)
        if seen_b.get(b, 0) >= bcap or seen_t.get(t, 0) >= PER_TIER or seen_s.get(s, 0) >= PER_SOURCE:
            return False
        if ar is not None and seen_area.get(ar, 0) >= area_cap:
            return False
        if exposure_ledger.get(nm, 0) > 0 and seen_pop.get("hot", 0) >= POPULARITY_CAP:
            return False
        return True

    def _take(it, exploration=False):
        nm = str(it["cand"].get("name", "")).strip().lower()
        b, t, s = it.get("bucket") or "other", it.get("tier") or "?", it.get("source") or 0
        ar = area_of.get(nm)
        seen_b[b] = seen_b.get(b, 0) + 1; seen_t[t] = seen_t.get(t, 0) + 1; seen_s[s] = seen_s.get(s, 0) + 1
        if ar is not None:
            seen_area[ar] = seen_area.get(ar, 0) + 1
        if exposure_ledger.get(nm, 0) > 0:
            seen_pop["hot"] = seen_pop.get("hot", 0) + 1
        if exploration:
            it = dict(it); it["exploration"] = True
        out.append(it)

    # review#C: РЕЗЕРВИРУЕМ EXPLORATION_QUOTA слотов — главный цикл берёт до (TOP_N - QUOTA), оставляя
    # место exploration'у. Так exploration реально срабатывает, НЕ ослабляя diversity-caps (_passes),
    # т.е. tier/bucket/area инварианты сохраняются; backfill ниже добивает слейт до TOP_N без потери длины.
    main_cap = max(0, TOP_N - EXPLORATION_QUOTA)
    for it in live:
        if len(out) >= main_cap:
            break
        if _passes(it):
            _take(it)

    # (5) exploration QUOTA + QUALITY FLOOR (Аудит #12). exploration ТОЛЬКО переставляет: кандидаты уже из
    # `live` (policy-eligible + present-permitted), tier/decision_class переносятся as-is (не повышаются, не
    # промоутятся в personal), и НЕ ниже min relevance/coverage floor; no_outreach не берём.
    expl_lcb = float(ctx.get("exploration_min_lcb", EXPLORATION_MIN_LCB))
    expl_cov = float(ctx.get("exploration_min_coverage", EXPLORATION_MIN_COVERAGE))
    if len(out) < TOP_N:
        chosen = {id(x) for x in out}
        explored = 0
        for it in live:
            if explored >= EXPLORATION_QUOTA or len(out) >= TOP_N:
                break
            if id(it) in chosen:
                continue
            nm = str(it["cand"].get("name", "")).strip().lower()
            if exposure_ledger.get(nm, 0) == 0 and exploration_eligible(it, expl_lcb, expl_cov) and _passes(it):
                _take(it, exploration=True); explored += 1

    # backfill: если exploration не заполнил зарезервированные слоты (нет свежих кандидатов), добираем
    # слейт до TOP_N обычными (не-exploration) кандидатами — резерв НЕ укорачивает результат.
    if len(out) < TOP_N:
        chosen = {id(x) for x in out}
        for it in live:
            if len(out) >= TOP_N:
                break
            if id(it) in chosen:
                continue
            if _passes(it):
                _take(it)

    # (6) propensity + причины
    for pos, it in enumerate(out):
        it["allocation"] = {"position": pos, "exploration": bool(it.get("exploration")),
                            "propensity": round(1.0 / (pos + 1), 4),
                            "reason": "diversity(bucket/tier/source)+readiness+area-balanced slate"}
    return out
