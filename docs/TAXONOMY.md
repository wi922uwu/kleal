# Kleal — governed taxonomy / evidence / expansion (§6)

Модуль [`shared/kleal_taxonomy.py`](../shared/kleal_taxonomy.py) (`kt`) — **строго read-only** нарратор и
governor над запечатанным скорером. Он **никогда** не пересчитывает tier/score: движок (`core_v2.assign_tier`
/ `SEM_VALUE` / `directional_score`, `app.topical`) остаётся единственным источником истины. Всё, что даёт
§6 — аддитивные метаданные на карточке (`taxonomy_edge` / `expansion_chain` / `complementary`), governance и
фальсифицируемые доказательства. PARITY-гард и все C/R/RCV/NEG/C4/C5 тесты остаются зелёными, потому что ни
один выход не трогает `band/tier/lcb/can_outreach/reciprocal/readiness/trace`.

## Почему это отдельный слой, а не правка движка
Бо́льшая часть §6 (коэффициенты `SEM_VALUE {4:1.0,3:0.65,2:0.45,1:0.25}`, пороги `assign_tier`, in-engine
дедуп до одной subfeature, `VIBE_CLASH`/`GEO_BANDS`, веса/priors/λ/floors в YAML) живёт внутри
**sha-пиннутого** `core_v2.py` + конфига (`PINNED_SHA 21505ccb`). Их нельзя менять без координированного
version-bump с Dev B — правка даже пробела в YAML валит `load_config`'s sha-gate и роняет сервис на legacy.
Поэтому §6 реализован как **governed enrichment layer**, а не как правка скоринга.

## Инъекция (без циклов, без FS на импорте)
`kt` не импортирует `app`. `app.py` вызывает `kt.bind_engine(topical, norm, cat_of, same_topic, TAXONOMY,
SYNONYMS, ADJACENCY, graph_txn)` — kt narrates то же решение, что принимает движок. Онтология
(`data/taxonomy/*.json`) грузится **лениво**, mtime-кэшируется, каждый read guarded → при любой ошибке
онтология пуста и слой работает на in-code нарративе. **На поде data/taxonomy не деплоится** (честный
data-absent дефолт: карточки несут edge/chain из движка, но кураторский RU/EN-текст объяснения пуст).

## Типизированные рёбра (`edge_type`, `edge_for`)
Классификация через тот же движковый reducer `topical → best`, затем метка:
best 4 → `exact_entity` (идентичная форма) / `alias` (разная форма, один канон через SYNONYMS) /
`literal_token_share` (off-taxonomy, НЕ выдуманное exact-ребро); 3 → `direct_sibling`; 2 → `parent`;
1 → `adjacent_purpose`; 0 → `none`. `semantic_tier` — advisory-зеркало `assign_tier` (T2 сворачивает
sibling+parent; **T4 никогда** не эмитится). `sem_value_echo` — read-only зеркало `SEM_VALUE`, не
авторитетно. При расхождении онтологии и движка — `governance_finding`, предпочитается движок.

## Объяснение расширения (`expand`) — §6 «обязательно объяснить»
`expand(topic)` → цепочка interest → sub → broad (in-code, авторитетно), обогащённая онтологической цепочкой
`interests.json.parent_id` + `edges.json.explanation`. На карточку `expansion_chain` кладётся для
parent/sibling (best 2/3).

## Комплементарные роли (`complementary`) — МАТРИЦА, не similarity
`complementary(role_a, role_b)` → типизированное ребро (support↔carry, learner↔native, tank↔healer,
cofounder↔engineer…) из hardcoded-матрицы + `edges.json` role/team/game/project/language edges. `similarity:
False`. `play↔watch` — это конфликт (`ROLE_CONFLICT`), НЕ комплемент → None. Метаданные, в скоринг не идут.

## Governance (`governance_of`, `validate`) — §6 blockquote
Каждое ребро несёт 6 полей: `owner` (`matching-engine@app.py` для in-code, `ontology@data/taxonomy` для JSON),
`version` (`matching-core-2.0.0` / MANIFEST), `language_aliases` (ru/en/es из `aliases.json`), `review_state`
(`in_code`/`active`), `evidence` (`kc.build_evidence` keyed на **канонический узел** → alias+канон = один
`evidence_id`), `rollback` (`sha-pinned:21505ccb — Dev-B version bump` / drop-edge-row). `validate()` —
read-only.

## Фальсифицируемые доказательства (TEST-ONLY, через `graph_txn`)
- **`alias_invariant`** — §6 «добавление alias не должно повышать score существующей пары»: пишет
  `best_before`, транзакционно добавляет alias в **живой** граф через `graph_txn` (под Lock, restore в
  `finally`), пишет `best_after`, требует `after ≤ before` для всех пар. **Negative control**: alias
  `dota→coffee` поднимает `coffee~dota` 0→4 — инвариант это ловит (`ok=False`).
- **`shadow_replay`** — §6 «изменение графа проходит shadow replay»: Mode A (data-edit → additive-only,
  4 gate-поля byte-identical; negative control ловит diff) + Mode B (in-code граф-правка через `graph_txn` →
  реальный гейт над живым скорером; negative control). `graph_txn` — **только оффлайн/тесты**, никогда в
  живом хендлере (транзиентно меняет реальный score).

## Статус (честно) — было ✅3·🟡13·⬜2 → стало ✅13 · ⬜0 · blocked_sha_pinned 6
Закрыты оба ⬜ (комплементарная матрица + governance) + типизированные рёбра + объяснение расширения.
**blocked_sha_pinned (6)** — требуют Dev-B version-bump `core_v2`/конфига, не отдаётся этим слоем:
SEM_VALUE-как-config-параметр, sibling 0.55–0.75 из domain config, negative-edge как новый штраф скоринга,
богатые per-group subfeatures, embedding recall, per-group внутренности 6 групп.

Тесты: `services/matching/test_core_v2.py` — `C6-*` (18 проверок, включая negative-controls для
alias-invariant и shadow-replay, EVID-ONE-ID, и **PARITY-ENRICH** — 4 gate-поля byte-identical enrichment
ON vs OFF).
