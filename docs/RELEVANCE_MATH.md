# Kleal — математическая модель relevance/evidence/uncertainty (§9)

**§9.1–9.5 реализованы ТОЧНО** в sha-пиннутом `services/matching/core_v2.py` — это ядро движка. §9 почти
целиком «уже сделано»; на orchestration-слое добавлены только CI-валидаторы (§9.5) и read-only ярлык
решения (§9.6). Проверено формула-за-формулой (тесты `C9-*`).

## §9.1 Четыре состояния признака — EXACT (`build_features` + `directional_score`)
`known_match`/`known_mismatch` (0..1) участвуют в relevance и повышают coverage; `unknown` → prior и
**понижает** coverage (не добавляется в `kw`); `not_applicable` — `continue` до `tw += w`, т.е. исключён из
знаменателя. Разреженный профиль не обгоняет заполненный (тест `C1`, `C9-NA-EXCLUDED`).

## §9.2 Нормализация наблюдения — EXACT, кроме `confidence_k`
`unknown → prior`, `NA → вес 0`, все значения в [0,1] — точно. **Единственное упрощение:** формула
`adjusted = confidence_k·observed + (1−confidence_k)·prior` свёрнута к `confidence_k = 1.0` (известное
значение входит сырым: `acc += w·v`, `core_v2.py:344`). Per-observation confidence не моделируется →
**blocked_sha_pinned** (в запечатанном движке; и требует данных confidence).

## §9.3 R_mean / Coverage / R_lcb — EXACT (`directional_score:348-349`)
`R_mean = Σ(w·adj)/Σw`, `Coverage = Σ(w·known)/Σw`, `R_lcb = clamp(R_mean − λ_domain·(1−Coverage), 0, 1)`.
`λ_domain` — из config (выше для dating 0.35). Тест `C9-FORMULA` пересчитывает вручную и сверяет байт-в-байт.

## §9.4 Направленное + двустороннее — EXACT (`reciprocal_score:352-355`)
`R_A→B` и `R_B→A` считаются раздельно; `R_reciprocal = 0.70·min + 0.30·mean`, ограничено [0,1] (тест
`C9-RECIP`). **Это НЕ вероятность принятия** — инвариант соблюдён: `P_accept/P_response/P_completion`
нигде не вычисляются (тест `C9-NO-PACCEPT`). Их введение → **blocked_calibration** (нужны данные калибровки
+ версия модели).

## §9.5 Канонические веса + CI — веса только в config; CI расширен
Веса живут ТОЛЬКО в sha-пиннутом `Kleal_Matching_Core_Config_v2.yaml` (в коде — только observed-value
anchors §6, не веса). `core_v2.load_config` уже проверяет: сумма весов = 1.0, нет неизвестных feature keys,
диапазоны priors/λ/floors. **Добавлено** (`app._validate_math_config`, read-only, НЕ мутирует config, НЕ
трогает `_sha256`): (a) **уникальность evidence_id** внутри feature groups (guard active — сегодня 0 ids;
таксономия alias_id/edge_id/node_id уникальны — 1249/560/405); (b) **совместимость версий**
config↔policy↔engine по MAJOR + schema_version в allowlist; (c) диапазоны band-cut. Видно в
`GET /api/agent/weights.config_ci`. Тесты `C9-CI-*` (positive + non-mutation + 4 negative controls).

## §9.6 Пороги решений пилота — read-only ярлык `decision_class`
`_decision_class(card)` — 5-way ярлык, **производный** из уже принятых движком решений
{policy, tier, band, can_outreach, why_no_outreach}, НИЧЕГО не пере-порогует (плоские 0.72/0.58/0.45 из
спеки — иллюстративны; РЕАЛЬНЫЕ per-domain floors в sha-пиннутом config уже свёрнуты в `can_outreach`/`band`).
Приоритет (тотальная функция, все чтения через `.get()`):
1. `REVIEW` → **no_personal_outreach** (held for safety track; до clarification — probe не переворачивает REVIEW);
2. `can_outreach` + T0/T1 + `especially_close` → **strong_personal_candidate**;
3. `can_outreach` (иначе) → **usable_personal_candidate** (включая T2+consent);
4. «broad consent» в why → **no_personal_outreach** (T2 без consent — НЕ discovery);
5. T3/T4 или «discovery only»/«below outreach floor» → **discovery_only**;
6. `needs_clarification` → **clarification**;
7. иначе → **no_personal_outreach**.
Аддитивно (`_apply_policy` slate + `explain_match`); band/tier/lcb/can_outreach + порядок slate
byte-identical (PARITY зелёный). `explain` также отдаёт `probe_unknowns` (top-1-3 unknown по весу).

## §9.7 Что показывается — EXACT
Никаких «92% совместимости» — только качественные band'ы (`assign_band` + фикс percent→band уже отгружен).

## Статус (честно): **done_core_v2 15 · done 4 · partial 8 · blocked_sha_pinned 1 · blocked_calibration 1**
- **done_core_v2:** вся математика §9.1/§9.3/§9.4 + веса-в-config + «не вероятность» + 3.5 CI-проверки load_config.
- **done (в §9):** evidence_id-uniqueness + version-compat + band-cut CI; decision_class 5-way; math-инвариант тесты.
- **partial:** decision_class на slate-пути консервативен (без `why_no_outreach` → падает в no_personal_outreach;
  полная точность в `explain`); band-cut CI дублирует schema.json статически.
- **blocked_sha_pinned:** `confidence_k`-blend. **blocked_calibration:** `P_accept/P_response/P_completion`.

Тесты: `services/matching/test_core_v2.py` — `C9-*` (17 проверок).
