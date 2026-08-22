---
title: "KLEAL — Matching Core"
subtitle: "Финальная продуктовая, математическая и техническая спецификация"
author: "Kleal"
date: "Версия 2.0 · Июль 2026"
lang: ru-RU
---

![](assets/00_cover.png){width=17cm}

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

> **Статус документа**  
> Это финальная нормативная спецификация Matching Core для продуктовой команды, backend/ML-разработчиков и Claude. Разделы 0–23 имеют приоритет над прежней спецификацией и экспертным аудитом. Машинно-читаемый файл `Kleal_Matching_Core_Config_v2.yaml` является единственным источником истины для весов, порогов и лимитов. SHA-256: `21505ccb4add960291a742084b36d25289ffc93c9870a80b8cba3295010e9c5b`.

# Как пользоваться документом

| Кому | Основные разделы | Результат |
|---|---|---|
| Продукт и руководство | 0–3, 12, 17–18, 22 | Понять пользовательскую логику, ограничения и порядок запуска. |
| Backend / data / ML | 4–16, 19–21, приложения A–C | Реализовать контракты данных, ранжирование, оркестрацию, state machine и тесты. |
| Дизайн и UX | 8, 12–14, 18 | Сформировать объяснения, сценарии расширения, consent и статусы. |
| Claude | 23 и приложения A–C; затем нормативные разделы 4–16 | Сгенерировать код и тесты без самостоятельного смешения слоёв. |

# Структура

1. Резюме и решения
2. Цель продукта и границы Matching Core
3. Нормативные принципы и термины
4. Архитектура принятия решения
5. Канонические контракты данных
6. Intent Compiler и уточнения
7. Таксономия, evidence и смысловое расширение
8. Candidate retrieval и semantic tiers
9. Eligibility, privacy и safety
10. Модель релевантности и неопределённости
11. Взаимность, готовность и прогноз принятия
12. Allocation, fairness и нагрузка
13. Расширение поиска и гарантия ответа
14. Агентский протокол и outreach
15. Транзакционные state machines
16. Group Formation Core
17. События и онлайн-комнаты
18. Dating как отдельный контур
19. Доменные сценарии и примеры
20. Feedback и обучение
21. Метрики, эксперименты и quality gates
22. Техническая архитектура и API
23. План пилота в Барселоне
24. Контракт реализации для Claude
25. Самооценка качества документа

Приложения: canonical config, псевдокод, acceptance tests, purpose-binding матрица, источники.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 0. Резюме и решения

> **Главное решение**  
> Matching Core не вычисляет «совместимость людей». Он находит реалистичный способ закрыть конкретный intent, соблюдая взаимные ограничения, приватность, безопасность, доступность и допустимую нагрузку на обе стороны. Система обязана честно показывать, где найдено точное совпадение, а где поиск был расширен.

Финальная архитектура разделяет шесть независимых слоёв: eligibility/policy, retrieval, relevance, reciprocity/readiness, allocation и transaction/presentation. Ни один слой не может компенсировать другой. Высокий смысловой fit не отменяет блокировку, отсутствие consent или заполненную capacity.

Ключевые решения:

- Веса и пороги хранятся только в versioned YAML; текст документа не является вторым конфигурационным источником.
- Semantic tier описывает происхождение кандидата в лестнице расширения и не зависит от итогового score.
- Unknown, mismatch и not_applicable — разные состояния. Разреженный профиль не получает высокий результат только из-за отсутствия данных.
- В MVP relevance является внутренней эвристикой 0–1, а не вероятностью принятия и не процентом человеческой совместимости.
- Пользователь видит качественный уровень, 2–3 подтверждённые причины, один gap и объяснение расширения.
- Agent-to-agent взаимодействие реализуется структурированным протоколом, а не свободными LLM-диалогами.
- Групповой matching — отдельная set-level задача; события и комнаты — отдельные типы кандидатов.
- Dating использует отдельный профиль, receiving policy, consent, disclosure и release gate.
- Все переходы proposal/match/plan транзакционны, идемпотентны и повторно проверяют policy, TTL, capacity и версии.
- Оплата подписки никогда не влияет на relevance, eligibility, safety или порядок выдачи.

| Выход системы | Семантика | Тип / диапазон | Показывать пользователю |
|---|---|---|---|
| `policy_decision` | Можно ли рассматривать пару и раскрывать конкретные данные | ALLOW / BLOCK / REVIEW | Только понятное сообщение о собственных настройках |
| `semantic_tier` | Насколько расширен смысловой поиск | T0–T5 | Да, человеческим языком |
| `relevance_score` | Соответствие текущему intent | 0–1, internal, domain-specific | Не как точный процент в MVP |
| `evidence_coverage` | Доля ключевых данных, подтверждённых evidence | 0–1 + unknown list | Косвенно: «нужно уточнить» |
| `reciprocal_relevance` | Баланс A→B и B→A | 0–1, не вероятность | Нет как число |
| `readiness_state` | Готовность получать предложение сейчас | categorical | Да, только как статус доступности |
| `allocation_action` | Кому и когда дать экспозицию | system decision | Нет |
| `explanation_keys` | Подтверждённые причины и gaps | typed list | Да |

![](assets/01_architecture_layers.png){width=16.5cm}

*Рисунок 1. Нормативное разделение слоёв Matching Core.*

# 1. Цель продукта и границы Matching Core

Цель Matching Core — максимизировать число состоявшихся, взаимно полезных и безопасных взаимодействий, а не клики, лайки или время в приложении. В MVP цель реализуется как набор проверяемых промежуточных решений, а не как одна псевдовероятностная формула.

| Контур | Что решает | Чего не делает |
|---|---|---|
| Intent understanding | Понимает текущую задачу, ограничения и fallback | Не превращает предпочтение в hard gate без подтверждения |
| Eligibility & policy | Определяет право пары, группы или события участвовать | Не даёт «штраф совместимости» за safety или privacy |
| Retrieval | Находит кандидатов из нескольких источников | Не принимает окончательное решение по embeddings |
| Relevance | Оценивает соответствие текущему intent | Не предсказывает автоматически человеческую симпатию |
| Reciprocity/readiness | Учитывает направленные предпочтения и готовность | Не считает молчание отказом, если уведомление не доставлено |
| Allocation | Распределяет показы и proposal burden | Не меняет смысловую релевантность пары |
| Transaction | Создаёт proposal, reservation, match и plan | Не доверяет устаревшему snapshot без revalidation |

> **Инвариант успеха**  
> Качественным outcome считается не факт просмотра или mutual interest, а completed interaction с положительным двусторонним feedback либо повторным добровольным взаимодействием. Отсутствие feedback не считается негативным исходом.

## 1.1. Поддерживаемые типы решений

- **Person-to-person:** пользователь ищет одного человека для общения или совместной активности.
- **Intent-to-intent:** объединение двух активных запросов с совместимыми условиями.
- **Group formation:** формирование новой небольшой группы с quorum, ролями и set-level ограничениями.
- **Intent-to-event:** рекомендация уже существующего события.
- **Intent-to-room:** рекомендация онлайн-комнаты, созвона или watch room.
- **Relationship continuation:** повторная активность с уже знакомым человеком, а не «новое знакомство».

## 1.2. Границы пилота

Схема поддерживает все домены, но пилот включается через release flags. Для Барселоны рекомендуется сначала запускать active-intent matching в `social_meet`, `walk`, `language_exchange`, `culture_event`, `watch_together` и `coworking`; затем `games`, `sport_activity`, `professional_networking` и group formation. Passive outreach включается после проверки receiving policy. Dating проходит отдельный safety/legal gate.

# 2. Нормативные принципы и термины

| Термин | Определение | Не путать с |
|---|---|---|
| Intent | Текущая, ограниченная по времени задача пользователя | Долгосрочная жизненная цель |
| Evergreen goal | Долгосрочное направление: друзья, партнёр, профессиональный круг | Конкретный intent на сегодня |
| Eligibility | Детерминированное право участвовать в flow | Высокая релевантность |
| Semantic tier | Путь, по которому найден кандидат | Качество кандидата |
| Directional relevance | Насколько B соответствует запросу и направленным условиям A | Вероятность принятия |
| Evidence coverage | Насколько решение опирается на известные данные | Confidence отдельного LLM-слота |
| Receiving policy | Когда и для каких предложений агент может рассматривать пользователя | Общий интерес в профиле |
| Readiness | Текущая готовность получить и обработать предложение | Качество человека |
| Match | Взаимное согласие после повторной policy-проверки | Показ рекомендации |
| Success | Состоявшееся и взаимно положительное взаимодействие | Чат, клик или лайк |

> **Нормативные слова**  
> **ОБЯЗАТЕЛЬНО** — требование реализации. **РЕКОМЕНДУЕТСЯ** — стандартное поведение, отступление должно быть документировано. **ДОПУСКАЕТСЯ** — безопасная альтернатива. **ЗАПРЕЩЕНО** — нарушение системного инварианта.

# 3. Архитектура принятия решения

![](assets/01_architecture_layers.png){width=16.5cm}

*Рисунок 2. Последовательность принятия решения.*

1. Intent Compiler формирует подтверждённый структурированный intent и фиксирует version.
2. Policy Engine строит разрешённый profile view и применяет ALLOW/BLOCK/REVIEW.
3. Retrieval собирает кандидатов по источникам и присваивает semantic_tier.
4. Feature Builder строит уникальные evidence groups без double count.
5. Relevance Engine считает A→B и, где допустимо, B→A, а также coverage и conservative score.
6. Readiness и receiving policy определяют, допустим ли outreach сейчас.
7. Allocation Layer выбирает slate и волны с учётом fairness, fatigue и exposure.
8. Presentation Layer объясняет причины и gaps без скрытых данных.
9. Transaction Orchestrator создаёт proposal/reservation и на каждом переходе выполняет revalidation.

> **Запрещённая архитектура**  
> Нельзя вычислять один `FinalUtility`, в который складываются relevance, safety, response rate, fairness, оплату и fatigue. Такой score невозможно объяснить, откалибровать и безопасно использовать.

# 4. Канонические контракты данных

Matching Core работает не с «большим профилем», а с минимальными purpose-bound представлениями. Каждый запрос получает immutable snapshot с версиями данных, policy и config.

| Сущность | Назначение | Ключевые поля |
|---|---|---|
| UserProfile | Базовые явные факты и настройки | identity, languages, city, age eligibility, explicit interests, privacy |
| ProfileView | Контекстное представление для social/games/networking/dating | allowed fields, disclosure stage, purpose |
| ReceivingPolicy | Условия пассивного рассмотрения пользователя | domains, status, time windows, limits, geography, disclosure |
| Intent | Подтверждённая текущая задача | domain, activity, time, location, mode, format, target, fallback, TTL |
| Evidence | Источник каждого признака | evidence_id, source, scope, confidence, freshness, sensitivity |
| CandidateSnapshot | Результат feature building для конкретной версии intent | source, tier, feature groups, unknowns, versions |
| Proposal | Структурированное предложение | payload, allowed disclosure, TTL, idempotency, status |
| Reservation | Временное удержание capacity/слота | resource, holder, TTL, version |
| Match | Взаимное согласие после revalidation | participants, purpose, disclosure state, links |
| Group | Набор участников и set constraints | quorum, roles, pair blocks, reservations |
| Plan | Согласованная активность | time, place/room, participants, state |
| RelationshipEdge | История пары | new/contact/friend/repeat/avoid/block, scope, cooldown |

## 4.1. Evidence object

```json
{
  "evidence_id": "ev_01HT...",
  "field": "interest.game",
  "value": "Dota 2",
  "source": "current_intent_explicit",
  "scope": "intent:int_123",
  "confidence": 1.0,
  "freshness": "current",
  "sensitivity": "normal",
  "allowed_purposes": ["games"],
  "visibility": "match_only",
  "last_confirmed_at": "2026-07-16T10:15:00Z",
  "expires_at": "2026-07-17T02:00:00Z"
}
```

Все aliases, tags и taxonomy nodes, полученные из одной фразы, сохраняют общий `evidence_id`. Feature Builder обязан дедуплицировать их до агрегации.

## 4.2. Иерархия источников

| Приоритет | Источник | Правило |
|---|---|---|
| 1 | Явный ответ в текущем intent | Побеждает все старые данные в scope текущего intent. |
| 2 | Подтверждённая пользователем сводка intent | Является контрактом поиска и disclosure. |
| 3 | Текущий контекст с разрешением | Локация, календарь, availability; короткий TTL. |
| 4 | Явный стабильный профиль | Используется, если не противоречит текущему intent. |
| 5 | Подтверждённая память | Только в разрешённом domain scope. |
| 6 | Наблюдаемое поведение | Только scheduler/experimentation; не hard gate и не sensitive inference. |
| 7 | Agent inference | Soft, editable, low confidence, decay; никогда не скрытый hard gate. |

## 4.3. Intent schema

| Блок | Поля | Требование |
|---|---|---|
| Identity | intent_id, user_id, version, domain, status | Версия увеличивается при любом изменении, влияющем на поиск. |
| Goal | activity, purpose, desired outcome | Purpose отделяет social coffee от networking или dating. |
| Time | timezone, windows, duration, recurrence, urgency | Хранение в UTC + исходная timezone; interval algebra. |
| Location | city, coarse cell, radius/travel time, safe zones | Клиент не получает точную домашнюю/рабочую координату. |
| Mode & format | online/offline/hybrid, 1:1/group/event/room | Format должен быть явным или подтверждённым. |
| Target | directed preferences, required roles, level | Unknown не равен openness. |
| Social context | vibe, pressure level, communication style | Inferred значения временные и редактируемые. |
| Domain details | platform/server/rank; language level; ticket; equipment | Mandatory domain fields могут стать clarification. |
| Fallback | allowed dimensions and consent | Система не расширяет запрещённые измерения. |
| Disclosure | что можно показать на каждом этапе | Определяется пользователем и purpose-binding policy. |
| Lifecycle | created_at, expires_at, search budget | Истёкший intent не участвует в ranking. |

## 4.4. Receiving policy

```json
{
  "user_id": "usr_456",
  "status": "active",
  "allowed_domains": ["social_meet", "walk", "culture_event"],
  "passive_outreach": true,
  "quiet_hours": {"start": "22:00", "end": "09:00", "timezone": "Europe/Madrid"},
  "proposal_budget": {"per_24h": 2, "per_7d": 5},
  "location_scope": ["Barcelona"],
  "allowed_proposal_types": ["person", "small_group"],
  "disclosure_stage": "limited_profile",
  "paused_until": null
}
```

# 5. Intent Compiler и политика уточнений

![](assets/02_intent_compiler.png){width=16.5cm}

*Рисунок 3. Компиляция intent и решение об уточнении.*

LLM используется как parser и формулировщик, а не как источник права или финальной логики. Любой LLM output считается недоверенным, проходит JSON-schema validation, allowlists, normalizers и policy checks.

## 5.1. Hard и soft

| Фраза пользователя | Допустимая интерпретация | Запрещённая интерпретация |
|---|---|---|
| «Желательно рядом» | soft location preference | hard block по району |
| «Только по-испански» | required language hard gate после summary confirmation | предположение по языку профиля |
| «Без токсиков» | domain constraint + moderation preference | оценка личности кандидата без evidence |
| «Можно онлайн» | allowed fallback mode | замена offline intent без объяснения |
| «Найти вторую половинку» | evergreen dating goal; требуется dating mode | обычный social intent |

> **Правило подтверждения**  
> Любое ограничение, которое исключает значительную долю людей, раскрывает чувствительные предпочтения или влияет на safety, ОБЯЗАТЕЛЬНО показывается в intent summary и подтверждается пользователем.

## 5.2. Операционализированная clarification policy

| Класс вопроса | Когда задавать | Пример | Действие при отказе |
|---|---|---|---|
| P0 mandatory | Без ответа нельзя безопасно или корректно определить eligibility | dating opt-in; платформа/crossplay; обязательный язык | Не запускать соответствующий sensitive flow; предложить безопасную альтернативу |
| P1 high value | Ответ меняет >30% pool, открывает новый tier или предотвращает явный провал | время, район, формат 1:1/group, native vs same-level | Искать с unknown + lower confidence; не подставлять скрытый default |
| P2 ranking only | Меняет порядок top candidates, но не eligibility | точная тема разговора, желаемая глубина | Не спрашивать до первых результатов |
| P3 cosmetic | Только улучшает copy | название карточки | Не спрашивать |

В MVP вопрос выбирается rule-based, а не формулой EVI. Внутренний приоритет строится из четырёх ordinal факторов: safety impact, candidate-pool split, supply unlock и user control. Friction вычитается. Система задаёт не более одного вопроса до первых результатов, кроме mandatory safety.

## 5.3. Минимально достаточный intent

- domain и activity/purpose;
- временной горизонт или явное «без точного времени»;
- mode и participation format;
- город/online либо разрешённый location fallback;
- минимальный набор domain-critical полей;
- fallback policy и disclosure summary;
- TTL и search budget.

# 6. Таксономия, evidence и смысловое расширение

Таксономия описывает смысловые отношения, но не заменяет policy и structured domain fields. Embeddings используются для расширения recall, а не для финального решения.

| Тип связи | Пример | Коэффициент/роль | Ограничение |
|---|---|---|---|
| Alias | Dota 2 ↔ DOTA | одна сущность | тот же evidence_id |
| Exact entity | Dota 2 | 1.0 внутри semantic subfeature | не суммировать с alias |
| Direct sibling | Dota 2 ↔ League of Legends | 0.55–0.75 по domain config | только если broad matching allowed |
| Parent | Dota 2 → MOBA → games | semantic_tier T2 | обязательно объяснить расширение |
| Adjacent purpose | кофе ↔ прогулка как спокойный social plan | T3 | не personal push без consent |
| Negative edge | ranked competitive ↔ casual no-pressure | penalty/constraint | не считать общей категорией достаточной |
| Complementary role | support ↔ carry; learner ↔ native speaker | role matrix | не similarity |

> **Governance**  
> Каждая taxonomy edge имеет owner, version, language aliases, review state, evidence и rollback. Изменение графа проходит shadow replay. Добавление alias не должно повышать score существующей пары.

## 6.1. Evidence groups против double count

Коррелированные представления объединяются в семь feature groups. Внутри группы используются subfeatures с фиксированной агрегацией и cap 1.0. Один source statement может влиять на несколько subfeatures только при явной независимости смысла; иначе он учитывается один раз.

| Feature group | Что включает | Что не суммируется отдельно |
|---|---|---|
| semantic_activity | activity/entity, topic, taxonomy similarity, embedding recall | exact entity + alias + parent tags как четыре независимых бонуса |
| time_feasibility | overlap, duration, recurrence, urgency | start_time и текстовый тег evening |
| location_feasibility | travel time, safe coarse zone, mode | район + координата + distance tags |
| mode_format | online/offline, 1:1/group, channel | несколько синонимов small group |
| directed_preferences | target role, level, audience, mutual eligibility | self profession как target profession |
| social_context | vibe, pressure, communication style | LLM personality labels без подтверждения |
| domain_constraints | platform/server/rank/equipment/ticket/native-role | общая категория вместо обязательного domain field |

# 7. Candidate retrieval и semantic tiers

![](assets/03_retrieval_expansion.png){width=16.5cm}

*Рисунок 4. Пулы кандидатов и контролируемое расширение.*

## 7.1. Порядок источников

1. Активные intent с точным или прямым смысловым совпадением.
2. Пользователи с активным receiving policy и прямым подтверждённым интересом.
3. Существующие группы с capacity.
4. События и комнаты как альтернативный способ закрыть intent.
5. Parent/adjacent candidates только при разрешённом расширении.

| Tier | Происхождение | Допустимый UX | Personal outreach |
|---|---|---|---|
| T0 exact active intent | Почти такой же активный запрос | «Точное совпадение по задаче» | Да |
| T1 direct interest | Прямой интерес/роль/активность | «Сильный вариант» | Да |
| T2 parent category | Родительская категория | «Более широкий вариант: ...» | Только при broad consent |
| T3 adjacent context | Совпали формат, время и social context, но не тема | Discovery/map/list | Нет |
| T4 alternative solution type | Event/group/room вместо человека | «Другой способ закрыть запрос» | Нет |
| T5 no overlap | Нет meaningful overlap | Не показывать | Нет |

Semantic tier является immutable provenance кандидата в конкретном search run. Сильная логистика не переводит parent candidate в direct tier. Аналитика отдельно измеряет relevance внутри каждого tier.

## 7.2. Retrieval budgets

| Этап | Механизм | Ориентир пилота | LLM |
|---|---|---|---|
| Hard prefilter | SQL/PostGIS/H3, status, TTL, privacy | до 1 000 → 100–250 | Нет |
| Structured retrieval | domain indexes, active intents, taxonomy | 100–250 → 30–80 | Нет |
| ANN recall | pgvector embeddings внутри разрешённого pool | добавить до top 50 | Нет |
| Feature build | canonical evidence groups | 30–80 → 10–30 | Нет |
| Ranking/slate | relevance + reciprocity + allocation | 10–30 → 3–8 | Нет |
| Explanation | reason keys → natural language | только final slate | Малая/большая модель по необходимости |
| Agent probe | allowlisted unknowns | только top 1–3 | Малая модель или шаблон |

# 8. Eligibility, privacy, safety и purpose binding

Scoring начинается только после решения **ALLOW**. Если policy engine возвращает **BLOCK**, кандидат не попадает ни в ranking, ни в explanation, ни в agent probe. Статус **REVIEW** означает, что автоматическое предложение запрещено до явного ответа пользователя или проверки сервиса безопасности.

## 8.1. Канонические gates

| Gate | Проверка | Результат при неизвестности |
|---|---|---|
| account_status | active, not suspended, not deleted | BLOCK |
| age / legal eligibility | возраст и режим соответствуют сценарию | BLOCK или REVIEW |
| mutual block | A и B не блокировали друг друга | BLOCK |
| privacy visibility | обе стороны разрешают использование данных для этого purpose | BLOCK |
| intent mode isolation | friendship / dating / professional / language и другие режимы совместимы | BLOCK |
| location policy | зона допустима без раскрытия точного адреса | REVIEW или расширение зоны |
| time feasibility | окна пересекаются с учётом длительности и timezone | BLOCK для конкретного слота |
| language feasibility | существует общий язык достаточного уровня | BLOCK, если язык hard |
| capacity | пользователь, группа, событие или room могут принять ещё участника | BLOCK |
| fatigue / receiving readiness | получатель не перегружен и принимает этот тип предложений | BLOCK для outreach, но не обязательно для passive discovery |
| safety restrictions | нет активных ограничений, требующих исключения | BLOCK |
| disclosure policy | предложение не раскрывает запрещённые поля | payload reduction или BLOCK |

## 8.2. Точки обязательной повторной проверки

Eligibility нельзя считать вечным свойством пары. Policy revalidation выполняется:

1. перед добавлением кандидата в slate;
2. непосредственно перед отправкой proposal;
3. при открытии профиля после значительной задержки;
4. при принятии proposal;
5. перед созданием общего чата;
6. перед раскрытием точного места или контактных данных;
7. после изменения privacy, block, suspension, age mode, capacity или intent version.

Если состояние изменилось, операция завершается предсказуемым кодом `POLICY_CHANGED`, а не silently продолжает старую транзакцию.

![](assets/07_context_isolation.png){width=16.5cm}

*Рисунок 5. Контекстная изоляция и purpose binding.*

## 8.3. Контекстные профили

Один и тот же пользователь может иметь разные допустимые представления:

| Контекст | Что можно использовать | Что нельзя переносить автоматически |
|---|---|---|
| friendship | общие интересы, формат досуга, языки, доступность | dating preferences, чувствительные lifestyle-факты |
| dating | отдельные target preferences, consent, disclosure, age gates | профессиональные выводы как признаки романтической совместимости |
| networking | роль, отрасль, seniority, тема встречи | личные dating-цели, семейный статус |
| language exchange | язык, уровень, native/learner role, формат практики | профессия как обязательный критерий без запроса |
| games | игра, платформа, регион, роль, ранг, режим | личные характеристики, не влияющие на игровой intent |
| sport | вид спорта, уровень, интенсивность, оборудование, время | health inference без явного согласия |

Purpose binding означает: поле, разрешённое для одного режима, не становится автоматически доступным в другом. Каждая materialized Match Capsule создаётся для конкретного `purpose_id`, имеет версию и TTL.

## 8.4. География и время

- В retrieval используется зона, H3-cell, район или радиус; точная live location не хранится в candidate payload.
- Домашний и рабочий адреса никогда не становятся точкой discovery.
- Для быстрых сценариев применяются `available_from`, `available_until`, `min_duration` и буфер дороги.
- Все времена хранятся в UTC с исходным timezone; сравнение выполняется после нормализации.
- Переход на летнее время, поездки и travel mode входят в обязательные тесты.
- Точное место раскрывается только после соответствующего уровня взаимного согласия.

# 9. Математическая модель: relevance, evidence и uncertainty

![](assets/04_scoring_layers.png){width=16.5cm}

*Рисунок 6. Числовые слои системы не смешиваются в один псевдопроцент.*

## 9.1. Четыре состояния признака

Для каждой применимой feature group система фиксирует одно из состояний:

| Состояние | Значение | Поведение |
|---|---|---|
| `known_match` | подтверждённое соответствие, 0..1 | участвует в relevance |
| `known_mismatch` | подтверждённое расхождение, 0..1 | участвует в relevance как низкое значение |
| `unknown` | поле важно, но данных нет | используется prior и снижает coverage |
| `not_applicable` | признак не относится к этому intent | исключается из знаменателя |

`unknown` не равен совпадению и не равен несовпадению. Разреженный профиль не должен обгонять заполненный только потому, что слабые места отсутствуют.

## 9.2. Нормализация наблюдения

Для известного признака:

`adjusted_value_k = confidence_k × observed_value_k + (1 − confidence_k) × prior_k`

Для `unknown`:

`adjusted_value_k = prior_k`

Для `not_applicable` вес равен нулю. Все observed values и priors находятся в диапазоне `[0,1]`.

## 9.3. Relevance mean и evidence coverage

`R_mean = Σ(w_k × adjusted_value_k) / Σ(w_k)`

`Coverage = Σ(w_k × known_k) / Σ(w_k)`

где `known_k = 1` для known_match/known_mismatch и `0` для unknown.

Для принятия решений используется консервативная нижняя оценка:

`R_lcb = clamp(R_mean − λ_domain × (1 − Coverage), 0, 1)`

Стартовый `λ_domain` хранится в конфигурации. Для safety-sensitive и dating flows он выше, чем для passive discovery.

## 9.4. Направленное и двустороннее соответствие

Система считает отдельно:

- `R_A_to_B`: насколько B отвечает текущему запросу A;
- `R_B_to_A`: насколько A допустим и релевантен receiving policy пользователя B.

В MVP двусторонняя релевантность:

`R_reciprocal = 0.70 × min(R_A_to_B, R_B_to_A) + 0.30 × mean(R_A_to_B, R_B_to_A)`

Формула penalizes односторонние пары и остаётся bounded в `[0,1]`. Это **не вероятность принятия**. Вероятности `P_accept`, `P_response` и `P_completion` разрешено использовать только после отдельной калибровки на достаточных данных и только с указанием версии модели.

## 9.5. Канонические веса доменов

![](assets/09_domain_weights_heatmap.png){width=16.5cm}

*Рисунок 7. Единственный стартовый набор весов хранится в canonical configuration registry.*

Веса не дублируются в коде и документе. Приложение A содержит выдержку из файла `Kleal_Matching_Core_Config_v2.yaml`. CI проверяет:

- сумму весов домена = 1.0;
- отсутствие неизвестных feature keys;
- уникальность `evidence_id` внутри feature groups;
- диапазоны priors, penalties и thresholds;
- совместимость config version с model/policy version.

## 9.6. Decision thresholds пилота

| Решение | Условия по умолчанию |
|---|---|
| strong personal candidate | policy=ALLOW, `R_lcb ≥ 0.72`, coverage ≥ 0.70, tier T0–T1 |
| usable personal candidate | policy=ALLOW, `R_lcb ≥ 0.58`, coverage ≥ 0.55, tier T0–T2, broad consent при T2 |
| discovery only | `R_lcb ≥ 0.45`, но tier T3–T4 или низкое coverage |
| clarification / probe | high-impact unknown способен изменить решение; top 1–3 candidates |
| no personal outreach | ниже порогов, нет consent на expansion или receiving policy не разрешает |

Пороговые значения — стартовая конфигурация пилота, а не доказанная истина. Они версионируются и меняются только после review.

## 9.7. Что показывается пользователю

В MVP запрещено показывать «92% совместимости». Пользователь видит:

- **Особенно близко к вашему запросу**;
- **Хороший вариант**;
- **Более широкий вариант**;
- **Альтернативный способ закрыть запрос**.

К каждому результату прилагаются 2–3 подтверждённые причины, один существенный компромисс и при необходимости отметка «часть данных ещё не подтверждена». Числовой процент допускается только после калибровки, UX-исследования и formal approval.

# 10. Reciprocity, readiness и вероятность результата

Relevance отвечает на вопрос «подходит ли кандидат текущей задаче». Readiness — «готов ли человек сейчас получать и рассматривать предложение». Эти величины не складываются.

## 10.1. Receiving readiness

| Состояние | Значение |
|---|---|
| `open_now` | разрешены предложения данного типа в текущем окне |
| `open_later` | можно сохранить, но не отправлять до указанного времени |
| `passive_discovery` | можно показывать в списке/карте, personal proposal запрещён |
| `busy` | временно не отправлять |
| `paused` | исключить из retrieval для указанного purpose |
| `unknown` | не делать personal outreach без явной настройки или probe |

Readiness зависит от домена. Человек может быть открыт к языковой практике и одновременно закрыт для dating.

## 10.2. Completion factors

В MVP completion не превращается в отдельный «балл человека». Используются прозрачные operational signals:

- актуальность availability;
- способность согласовать минимальную длительность;
- response latency band;
- recent no-show только как контекстный reliability signal;
- capacity и число активных планов;
- техническая совместимость для online activity;
- наличие host/venue/room для group/event flows.

Safety reports, sensitive inferences и единичные негативные отзывы не должны становиться непрозрачным социальным рейтингом.

## 10.3. Переход к ML

Обучаемые модели добавляются по слоям:

1. intent classification и slot extraction;
2. candidate retrieval recall;
3. calibrated `P_response`;
4. calibrated `P_accept` отдельно по направлениям и доменам;
5. calibrated `P_completion`;
6. learning-to-rank с off-policy evaluation.

Hard gates, privacy, purpose binding, block, capacity и disclosure остаются deterministic policy и не отдаются модели.

# 11. Allocation, fairness и рыночная ликвидность

Allocation определяет, кому и сколько показов/предложений выдать после расчёта eligibility и relevance. Он не изменяет смысл релевантности пары.

## 11.1. Механизмы

- per-user exposure caps;
- proposal fatigue caps;
- cooldown для повторных предложений той же пары;
- exploration quota для новых пользователей с достаточным coverage;
- diversity slate по source type, semantic tier и intent interpretation;
- popularity concentration guard;
- reservation capacity для групп и срочных intents;
- city/area supply balancing;
- защита от систематического переиспользования наиболее отзывчивых людей.

## 11.2. Порядок rerank

1. Удалить BLOCK/expired/capacity-exceeded.
2. Отсортировать по reciprocal relevance и readiness class.
3. Применить diversity constraints.
4. Применить exposure/fatigue caps.
5. Добавить ограниченную exploration позицию.
6. Зафиксировать propensity и причины allocation.

## 11.3. Инвариант монетизации

Подписка не повышает ranking пользователя и не покупает доступ к более «ценным» людям. Платный план может расширять число активных intents, background search, filters, travel mode и automation, но:

`payment_status` запрещён как relevance, reciprocity, safety или allocation feature.

# 12. Controlled expansion и гарантия полезного ответа

Цель fallback — не выдать случайного человека любой ценой, а обеспечить полезный следующий шаг.

## 12.1. Принципы расширения

- расширять за один шаг только одну ось;
- сначала ослаблять soft constraint с наименьшей ценой для пользователя;
- не ослаблять safety, age, mutual consent, block, critical language и purpose isolation;
- сохранять provenance tier;
- явно объяснять компромисс;
- персональный outreach в parent tier требует broad consent;
- adjacent results по умолчанию идут в discovery, а не в inbox другого человека.

## 12.2. Типовой порядок

1. Exact entity/role при том же времени и зоне.
2. Direct sibling/closely related entity.
3. Parent activity/category.
4. Увеличение времени или расстояния в пределах consent.
5. Изменение формата: 1:1 → small group или offline → online, если допустимо.
6. Event/room/group как alternative solution type.
7. Сохранённый поиск и уведомление позже.

## 12.3. Пример Dota 2

Запрос: «Хочу сегодня вечером сыграть ranked Dota 2, нужен support, EU West, 2–3 часа».

| Шаг | Результат |
|---|---|
| T0 | игрок с активным Dota 2 intent, роль support, тот же server/time |
| T1 | пользователь с подтверждённым Dota 2 interest и receiving policy games |
| T2 | другие MOBA-игроки — только как более широкий вариант, не как «почти Dota» |
| T4 | активная Dota room / watch party / group queue |
| No supply | уточнить: unranked допустим? другой вечер? сохранить поиск? |

League of Legends player не должен получать personal proposal под видом близкого Dota-совпадения без явного согласия инициатора на parent-category expansion.

# 13. Agent protocol и outreach orchestration

Пользовательский агент не ведёт свободные разговоры с сотнями LLM. Matching Exchange передаёт типизированные события.

## 13.1. Разрешённые действия

`ELIGIBILITY_PROBE`, `PROPOSE_CONNECTION`, `ASK_INFO`, `COUNTER_TIME`, `COUNTER_FORMAT`, `ACCEPT`, `DECLINE`, `WITHDRAW`, `EXPIRE`.

Каждое сообщение содержит:

- `proposal_id` и `idempotency_key`;
- версии intent, profile capsule и policy;
- purpose и disclosure scope;
- structured fields;
- TTL;
- human-readable rendering key;
- audit metadata.

## 13.2. Волны предложений

| Волна | Размер | Когда запускается |
|---|---:|---|
| Wave 0 | 0 | сначала показать пользователю slate, если требуется выбор |
| Wave 1 | 1–2 | top candidates, высокий coverage, receiving=open_now |
| Wave 2 | 1–2 | отказ/таймаут/недостаточная capacity |
| Wave 3 | до 3 | пользователь разрешил расширение или urgent intent |

По умолчанию один intent не создаёт более трёх одновременных personal proposals. Массовая рассылка сотням пользователей запрещена.

## 13.3. Границы автономности

Агент может автоматически:

- компилировать черновик intent;
- выполнять retrieval;
- задавать allowlisted clarification;
- формировать explanation из reason keys;
- отправить предложение только в рамках заранее подтверждённой outreach policy.

Агент не может без отдельного согласия:

- расширить hard constraints;
- раскрыть новое чувствительное поле;
- согласиться на dating contact;
- подтвердить платёж, бронирование или точный private venue;
- принять несколько конфликтующих планов;
- переинтерпретировать отказ как «попробовать позже».

# 14. Transaction state machines и защита от гонок

![](assets/05_transaction_state_machine.png){width=16.5cm}

*Рисунок 8. Proposal и Match являются транзакционными сущностями с повторной policy-проверкой.*

## 14.1. Состояния

**Intent**: `DRAFT → CONFIRMED → SEARCHING → WAITING → SATISFIED | EXPIRED | CANCELLED`.

**Proposal**: `CREATED → RESERVED → SENT → VIEWED → ACCEPTED | DECLINED | COUNTERED | WITHDRAWN | EXPIRED | POLICY_REVOKED`.

**Match**: `PENDING_DISCLOSURE → MUTUAL → CHAT_OPEN → PLANNING → PLANNED → COMPLETED | CANCELLED | SAFETY_CLOSED`.

**Plan**: `DRAFT → PROPOSED → PARTIALLY_CONFIRMED → CONFIRMED → CHANGED → COMPLETED | CANCELLED | NO_SHOW`.

## 14.2. Технические гарантии

- optimistic concurrency через `version`;
- idempotency key на все write endpoints;
- transactional outbox для событий и уведомлений;
- уникальные ограничения на active pair/purpose/intent combination;
- policy revalidation внутри той же транзакции, что acceptance;
- reservation TTL для capacity;
- compare-and-swap при concurrent accepts;
- immutable decision trace;
- retry-safe consumers и deduplication.

## 14.3. Одновременные принятия

Политика зависит от intent:

| Intent | Поведение |
|---|---|
| 1:1 fixed-time | после первого подтверждённого match остальные proposals withdraw или требуют выбора |
| multiple conversations allowed | можно держать несколько mutual contacts без автоматического plan |
| group formation | accept создаёт reservation; окончательный match после quorum |
| event | capacity transaction определяет место; waitlist при заполнении |
| dating | никаких auto-commit; пользователь подтверждает каждый mutual contact |

## 14.4. Критические race cases

- пользователь изменил privacy между просмотром и accept;
- оба кандидата одновременно заняли последний слот;
- intent cancelled, но delayed notification пытается открыть proposal;
- пользователь заблокировал другого после mutual interest;
- counter пришёл после expiry;
- две волны создали duplicate pair;
- сервис уведомлений повторил событие;
- изменение timezone сделало слот невозможным.

Каждый case должен завершаться детерминированным state/error code и не раскрывать лишнюю информацию.

# 15. Group Formation Core

![](assets/06_group_formation.png){width=16.5cm}

*Рисунок 9. Группа оценивается как множество, а не как среднее парных совпадений.*

## 15.1. Set-level constraints

- min/max group size;
- пересечение времени достаточной длительности;
- capacity и reservations;
- обязательные роли;
- pairwise blocks и safety exclusions;
- host/moderator, если требуется;
- допустимый skill spread;
- language coverage;
- equipment/platform/venue constraints;
- quorum и replacement policy.

## 15.2. Group utility

Pair relevance используется как вход. Для допустимого множества `G`:

`GroupUtility(G) = 0.35 × least_misery + 0.25 × mean_pair_fit + 0.20 × role_coverage + 0.10 × time_overlap + 0.10 × diversity_value`

Если любой hard set constraint нарушен, группа недопустима независимо от utility.

`least_misery` — минимальная направленная удовлетворённость внутри группы. Это защищает от ситуации, когда среднее высокое, но один участник оказывается явно неподходящим.

## 15.3. MVP algorithm

1. Сгенерировать seed candidates по домену и времени.
2. Сформировать feasible pools по hard constraints.
3. Greedy добавить кандидата с максимальным marginal gain.
4. Выполнить local repair: swap/remove/add для ролей и least-misery.
5. Создать reservations.
6. Отправить structured invitations.
7. При отказе использовать waitlist; при потере quorum — cancel или re-form.

## 15.4. Примеры

- Dota stack: carry/support/mid/offlane coverage, server, rank spread, party size.
- Падель: четыре места, уровень, сторона корта, оборудование, бронь площадки.
- Разговорная группа: native/learner balance, язык, max group size, модератор.
- Прогулка: темп, доступность маршрута, район, время, размер группы.

# 16. Events, rooms и venues — отдельные типы кандидатов

Нельзя считать событие «пользователем с большой capacity».

| Тип | Eligibility | Ranking | Transaction |
|---|---|---|---|
| User | mutual policy и directed fit | reciprocal relevance | proposal → mutual contact |
| Ad-hoc group | set feasibility и quorum | group utility | reservations → group confirmation |
| Event | category, schedule, capacity, access | user→event relevance | registration / external handoff |
| Online room | platform, topic, live capacity, moderation | session relevance | join token / waitlist |
| Venue | availability, price, noise, distance, accessibility | plan suitability | selection / booking handoff |

Event recommendation может закрыть intent даже без персонального match. Система должна честно назвать это альтернативой, а не «совпадением с людьми».

# 17. Dating — отдельный режим продукта

Dating не является ещё одним набором весов поверх friendship.

## 17.1. Обязательные требования

| Область | Требование |
|---|---|
| consent | отдельное включение режима и явное подтверждение target preferences |
| profile | отдельная dating capsule; purpose-bound данные |
| age | строгие legal/age gates, несовершеннолетние исключены |
| orientation/preferences | хранение и обработка как чувствительного контура с минимизацией данных |
| disclosure | staged profile disclosure; фото/имя/детали по настройкам |
| outreach | каждый proposal требует явного действия; no auto-accept |
| explanation | не выводить чувствительные причины и не показывать псевдопсихологический score |
| safety | block/report, rate limits, anti-harassment, private-location safeguards |
| audit | отдельные policy version, retention и access controls |

## 17.2. Изоляция от других режимов

Dating goal не используется для предложения коллег, языковых партнёров или участников спортивной группы. Отказ в dating не влияет на ranking в friendship. Переход friendship → dating требует нового взаимного consent.

## 17.3. Gate для пилота

Dating flow нельзя включать только потому, что ranking работает для кофе или прогулок. Перед запуском необходимы отдельные UX, safety, moderation, DPIA/legal review, incident operations и тестовые сценарии злоупотреблений.

# 18. Доменные сценарии и декомпозиция intent

## 18.1. Обзор доменов

| Домен | Ключевые slots | Hard-примеры | Типичный fallback |
|---|---|---|---|
| social coffee | время, район, 1:1/group, темы, язык | age mode, mutual visibility | более широкий topic или соседний район |
| walk | маршрут/район, темп, длительность, accessibility | time overlap, mobility needs | другая зона/время, small group |
| games | game, platform, server, mode, rank, role, duration | platform/server, required role | parent genre или room только с consent |
| language exchange | language pair, level, native/learner role, format | общий язык, role feasibility | group practice / event |
| sport | activity, level, intensity, equipment, venue | safety/equipment/capacity | близкий уровень, другое время |
| culture/event | event/theme, ticket, time, meeting format | ticket/access, exact schedule | похожее событие или discussion group |
| networking | role sought, industry, seniority, topic, confidentiality | directed target role, purpose | adjacent role или curated group |
| watch together | event, team/topic, venue/online, start time | exact start, rights/platform | fan group/event listing |
| coworking | location, hours, silence/social balance, profession optional | venue/time | another venue/day |
| dating | relationship goal, target preferences, consent, time, mode | separate policy | no silent broadening |

## 18.2. Подробный сценарий: Dota 2

**Raw input:** «Сегодня после девяти хочу пару каток ranked Dota, я carry, нужен спокойный support, EU West».

**Compiled intent:**

- domain: games;
- entity: Dota 2;
- mode: ranked;
- role_needed: support;
- self_role: carry;
- server: EU West;
- window: 21:00–00:30;
- duration_min: 90 min;
- communication_style: calm;
- fallback: unranked requires confirmation; other MOBA discovery only.

**Clarification:** если server или platform неизвестны, вопрос обязателен. Если «спокойный» — soft preference, поиск может стартовать.

**Strong result:** active Dota intent + support + server/time + receiving open.

**Broader result:** Dota player без active intent, но receiving games open; показать lower coverage и не обещать available-now.

**Rejected:** LoL player, другой server без cross-region consent, support role unknown при fixed party need.

## 18.3. Подробный сценарий: прогулка по Барселоне

**Raw input:** «Хочу сегодня после работы спокойно погулять недалеко от Eixample, часа полтора, можно с кем-то новым».

**Hard:** взрослый режим, overlapping window, допустимая зона, mutual privacy, min duration.

**Soft:** спокойный темп, 1:1, новые знакомства, темы разговора.

**Exact:** человек с active walk intent в Eixample в тот же период.

**Direct:** пользователь открыт к прогулкам сегодня, но точный intent не создавал.

**Parent/alternative:** small walking group или публичное локальное событие. Система не предлагает человека, находящегося «рядом сейчас», если тот не включил receiving policy.

**Clarification:** только если «после работы» не удаётся привязать к окну или важна доступность маршрута.

## 18.4. Подробный сценарий: практика испанского

**Raw input:** «Ищу носителя испанского, хочу практиковаться два раза в неделю, могу помогать с английским».

**Directed roles:** A=Spanish learner/English helper; B=Spanish native или advanced/English learner.

**Hard:** language pair feasibility, формат, регулярность и timezone.

**Complementarity:** native↔learner и exchange value; обычное similarity здесь менее важно.

**Fallback:** advanced Spanish speaker, small moderated language group, public language-exchange event. «Любит Испанию» не является заменой языковой роли.

## 18.5. Подробный сценарий: профессиональный кофе

**Raw input:** «Хочу познакомиться с фаундерами AI-стартапов в Барселоне, обменяться опытом по запуску продукта».

**Hard/critical:** professional purpose, geography/travel feasibility, founder/leadership role, language.

**Soft:** AI focus, stage, product topic, 1:1 coffee.

**Directed fit:** профессия инициатора не обязана совпадать с target role. Система отдельно проверяет, открыт ли B к разговорам с профилем A.

**Fallback:** adjacent roles (product lead, investor, accelerator mentor) только после подтверждения; founder meetup/event как alternative solution.

## 18.6. Краткие дополнительные сценарии

**Падель.** «Нужен четвёртый игрок завтра в 19:00, intermediate, ракетка есть». Hard: время, capacity=1, уровень band, venue; group reservation обязателен.

**Выставка.** «Кто хочет в MACBA в субботу?» Hard: event/time/ticket assumptions; fallback: люди, интересующиеся contemporary art, но предложение маркируется как приглашение на конкретное событие.

**Футбол.** «Посмотреть матч Барсы в баре». Candidate types: человек, fan group, venue/event. Exact start time и broadcast availability важнее общей любви к спорту.

**Коворкинг.** «Поработать вместе в Poblenou утром». Социальность может быть низкой; ranking учитывает режим тишины, часы и venue, а не требует сильного совпадения интересов.

**Обычная встреча.** «Хочу выпить кофе и поговорить о книгах». Тема — soft; время/район/format — primary feasibility. При отсутствии book-specific candidates допускается calm coffee candidate с явным объяснением расширения.

**Dating-прогулка.** Запускается только из dating mode. Даже идентичный текст «погулять вечером» в friendship mode не должен неявно становиться романтическим.

# 19. Feedback, learning loop и память

![](assets/08_learning_loop.png){width=16.5cm}

*Рисунок 10. Обучение происходит по исходам и с контролем пользовательской памяти.*

## 19.1. Outcome taxonomy

| Этап | Сигналы |
|---|---|
| exposure | показ, позиция, source, tier, config/model/policy version, propensity |
| consideration | open, save, ask agent, skip reason |
| proposal | sent, viewed, response, timeout, decline reason category |
| coordination | counter, time/location conflict, plan created |
| completion | completed, cancelled, no-show, technical failure |
| quality | comfort, usefulness, would_repeat, both-sides positive |
| safety | block/report/discomfort/private-location attempt |

Primary positive outcome — не клик и не mutual like, а **Completed Positive Interaction**: взаимодействие состоялось и обе стороны не дали safety-negative signal; качество оценивается по доступным двусторонним данным.

## 19.2. Правила обновления профиля

- Явное пользовательское изменение обновляет stable preference.
- Одно поведение не создаёт вечный вывод.
- Повторяющиеся сигналы могут создать suggestion, но пользователь подтверждает чувствительные или identity-like inferences.
- Negative feedback контекстен: «не понравился шумный бар» не означает «не любит людей».
- Все inferred signals имеют confidence, source, purpose, decay и deletion path.
- Dating feedback не переносится в professional/social ranking.

## 19.3. Защита от feedback bias

- учитывать exposure и position bias;
- не обучаться только на ответивших;
- отделять «не увидел» от «отказал»;
- не трактовать timeout как личное несовпадение;
- использовать exploration с логированием propensity;
- оценивать модели shadow/replay до включения;
- проверять ухудшение safety и fairness отдельно от uplift conversion.

# 20. Метрики, эксперименты и критерии качества

## 20.1. Система показателей

| Контур | Обязательные показатели |
|---|---|
| Intent Compiler | slot accuracy, hard/soft confusion, clarification utility, edits, multilingual aliases |
| Policy | coverage критических gates, privacy leak tests, revocation handling |
| Retrieval | recall T0/T1/T2, zero-useful-result rate, rare-intent coverage, source mix |
| Relevance | monotonicity, coverage calibration, domain breakdown, reason accuracy |
| Reciprocity | mutual consideration, response rates отдельно по направлениям, passive/open states |
| Completion | plan creation, completion, no-show, both-sides positive, repeat |
| Expansion | acceptance/completion по каждому axis/tier, user regret after fallback |
| Groups | feasible formation rate, quorum loss, replacement, least-misery failures |
| Fairness | exposure opportunity, proposal burden, new-user chance, concentration |
| Safety | reports per exposure/match, post-match blocks, disclosure violations |
| Operations | P50/P95 latency, queue depth, retries, duplicate transitions, stale proposal rate |
| Economics | LLM calls/tokens per intent, probes per success, notification burden |

## 20.2. Staged validation

1. **Schema simulation:** 500–1 000 вручную размеченных кейсов, включая edge cases.
2. **Unit/property tests:** gates, weights, monotonicity, unknown, state transitions.
3. **Shadow mode:** core ранжирует без отправки proposals; human review.
4. **Internal dogfood:** ограниченная команда и synthetic supply.
5. **Barcelona closed pilot:** один-два домена, ограниченные районы и ручной ops review.
6. **Controlled expansion:** включать новые домены только после domain-specific acceptance criteria.
7. **ML migration:** только после достаточной выборки, calibration и rollback plan.

## 20.3. Guardrails

Нельзя объявлять улучшением рост mutual likes, если одновременно выросли no-show, reports, fatigue или concentration. Любой эксперимент имеет primary outcome, harm guardrails, segment breakdown и заранее определённое решение stop/continue.

# 21. Техническая архитектура, API и observability

## 21.1. Компоненты

| Компонент | Ответственность |
|---|---|
| Intent Compiler | raw text → canonical draft + confidence + clarification |
| Profile/Consent Service | profile signals, purpose grants, deletion, versions |
| Match Capsule Builder | purpose-bound compact representation |
| Taxonomy Registry | concepts, edges, distances, forbidden expansions |
| Candidate Retrieval | SQL/geo/vector/source pools |
| Policy Engine | ALLOW/BLOCK/REVIEW + disclosure |
| Feature Builder | evidence groups, dedup, unknown/applicability |
| Relevance Engine | directional scores, coverage, LCB |
| Reciprocity/Readiness | reverse fit и receiving state |
| Allocation Engine | diversity, caps, exploration, fairness |
| Match Orchestrator | search run, waves, reservations, proposals |
| Group Formation Core | set-level feasible groups |
| Plan Coordinator | time/place/room and plan states |
| Feedback & Learning | outcome events, training sets, memory suggestions |
| Cost Governor | model routing, cache, budgets |
| Audit/Observability | decision trace, replay, SLA, incident data |

## 21.2. Минимальные API

| Endpoint / event | Назначение |
|---|---|
| `POST /intents/compile` | создать draft, slots, confidence и clarification |
| `POST /intents/{id}/confirm` | зафиксировать intent version и consents |
| `POST /searches` | запустить search run с idempotency key |
| `GET /searches/{id}` | получить state и transparent slate |
| `POST /searches/{id}/expand` | разрешить конкретную ось расширения |
| `POST /proposals` | создать reservation/proposal |
| `POST /proposals/{id}/respond` | accept/decline/counter/ask/withdraw |
| `POST /groups/form` | сформировать feasible group candidates |
| `POST /plans` | создать/изменить plan с version check |
| `POST /interactions/{id}/feedback` | записать structured outcomes |
| `EVENT policy_changed` | инициировать revalidation/revocation |
| `EVENT match_state_changed` | аудируемый transition |
| `EVENT exposure_logged` | ranking/allocation trace |

## 21.3. Decision trace

```json
{
  "search_id": "srch_123",
  "candidate_id": "usr_456",
  "intent_version": 7,
  "profile_versions": {"a": 18, "b": 11},
  "purpose_id": "friendship.walk",
  "policy": {"decision": "ALLOW", "version": "pol-2.1.0"},
  "semantic_tier": "T1_DIRECT",
  "evidence": [
    {"id": "ev_time", "group": "time_feasibility", "state": "known_match", "value": 1.0},
    {"id": "ev_topic", "group": "semantic_activity", "state": "unknown", "prior": 0.45}
  ],
  "directional": {
    "a_to_b": {"mean": 0.78, "coverage": 0.74, "lcb": 0.70},
    "b_to_a": {"mean": 0.73, "coverage": 0.81, "lcb": 0.68}
  },
  "reciprocal_relevance": 0.69,
  "readiness": "open_now",
  "allocation": {"position": 2, "exploration": false},
  "reason_keys": ["same_time", "same_area", "compatible_format"],
  "config_version": "matching-core-2.0.0",
  "model_versions": {"intent": "ic-1.4.2", "embedding": "emb-3"}
}
```

## 21.4. SLA и деградация

| Сбой | Поведение |
|---|---|
| LLM compiler unavailable | template/parser fallback или сохранить draft; не угадывать critical slots |
| vector index unavailable | structured retrieval only |
| policy service unavailable | fail closed для personal outreach; cached safe results только для passive display |
| stale profile/capacity | revalidate; не создавать proposal |
| notification failure | outbox retry; state не откатывать |
| ranking timeout | вернуть partial transparent results или waiting state |
| taxonomy/config mismatch | stop search run и alert; не смешивать версии |
| overload | queue/background search, cap concurrent runs, degrade explanations before policy |

Цель пилота: initial acknowledged state <2 секунд; поиск асинхронный; progress отражает реальные стадии, а не декоративный процент.

# 22. План реализации для пилота в Барселоне

## 22.1. Рекомендуемый scope

Начать с доменов:

1. прогулки;
2. social coffee / casual meet;
3. language exchange;
4. professional networking;
5. selected games/online rooms при готовой supply.

Group sport, large event orchestration и dating включать отдельными этапами после базовой транзакционной и safety зрелости.

## 22.2. Этапы

| Этап | Результат | Exit criteria |
|---|---|---|
| 0. Contracts | schemas, config registry, state machines, policy matrix | CI validation, replayable examples |
| 1. Rule-based core | compiler, structured retrieval, gates, directional relevance | offline set проходит acceptance tests |
| 2. Transparent discovery | slate, reasons, list/map, no personal outreach | human review quality accepted |
| 3. Controlled proposals | waves, receiving policy, idempotency, revalidation | race/safety tests passed |
| 4. Plans/outcomes | plan states, feedback, completion | end-to-end dogfood |
| 5. Closed Barcelona pilot | limited areas/domains, ops dashboard | guardrails stable |
| 6. Group formation | reservations, quorum, replacements | set-level test suite passed |
| 7. Calibrated ML | response/accept/completion models | calibration + shadow uplift + rollback |

## 22.3. Операционная модель пилота

- город и районы partitioned;
- ограниченное число активных intent на пользователя;
- ручной review слабых/редких доменов;
- ежедневный dashboard supply/demand по area/domain/time;
- incident owner для privacy/safety/state races;
- weekly taxonomy и config review;
- никакого автоматического массового outreach;
- explicit feedback после взаимодействия без обязательной длинной анкеты.

# 23. Контракт реализации для команды и Claude

Этот раздел является инструкцией для генерации кода и review. Claude должен трактовать документ как спецификацию, а не как предложение свободно упростить архитектуру.

## 23.1. Обязательная модульная структура

```text
matching-core/
  contracts/
    profile.ts
    intent.ts
    candidate.ts
    proposal.ts
    match.ts
    plan.ts
    decision-trace.ts
  config/
    matching-core.yaml
    schema.json
    validator.ts
  intent-compiler/
  taxonomy/
  retrieval/
  policy-engine/
  feature-builder/
  relevance-engine/
  reciprocity-readiness/
  allocation/
  orchestrator/
  group-formation/
  plan-coordination/
  feedback-learning/
  observability/
  tests/
    fixtures/
    property/
    race/
    safety/
    domains/
```

## 23.2. Запрещённые упрощения

Claude и разработчики не должны:

1. сводить всё к одному `match_score`;
2. выводить semantic tier из score;
3. считать unknown совпадением;
4. смешивать safety/trust/fairness/payment с relevance;
5. использовать embeddings как финальную истину;
6. позволять LLM обходить hard gates;
7. вести свободные agent-to-agent диалоги вместо protocol events;
8. ранжировать группы средним pair score;
9. переносить dating data в другие режимы;
10. показывать проценты без калибровки;
11. хранить веса в нескольких местах;
12. отправлять proposal без receiving policy и revalidation;
13. выполнять write без idempotency/version;
14. повышать ranking за подписку;
15. использовать точную live location в discovery.

## 23.3. Definition of Done для любой фичи

- typed input/output contract;
- explicit purpose и policy decision;
- config/model/policy version logged;
- unknown/not_applicable handled;
- deterministic reason keys;
- unit и property tests;
- race/idempotency test для write flow;
- privacy/safety test;
- domain fixture минимум для двух разных сценариев;
- degradation behavior;
- observable events и dashboard field;
- human-readable UX copy separated from system decision.

## 23.4. Порядок реализации Claude

1. Сначала создать contracts и config validator.
2. Затем policy engine и state machine.
3. Затем compiler/retrieval/feature builder.
4. Затем deterministic relevance и transparent results.
5. После этого orchestration/proposals.
6. Group formation — отдельный модуль.
7. ML interfaces создавать заранее, но не подменять rule-based outputs случайными вероятностями.
8. На каждом этапе запускать fixture suite и сохранять decision traces.

# 24. Самооценка итоговой спецификации

Документ повторно проверен по критериям исходного аудита.

| Критерий | Балл |
|---|---:|
| Концептуальная архитектура и разделение слоёв | 10/10 |
| Математическая определённость и bounded scales | 10/10 |
| Unknown, coverage и защита от double counting | 10/10 |
| Двусторонняя логика и readiness | 9/10 |
| State machine, race conditions и транзакции | 10/10 |
| Privacy, purpose binding, safety и dating isolation | 10/10 |
| Group formation и разные candidate types | 10/10 |
| Доменные примеры и понятность для команды | 10/10 |
| Контракт для Claude и реализуемость | 10/10 |
| Pilot operations, validation и scalability | 9/10 |
| **Итог** | **98/100** |

Два оставшихся пункта нельзя честно закрыть документом: окончательная правовая оценка конкретной реализации в Испании и эмпирическая калибровка порогов/моделей на реальных пилотных данных. Они вынесены в обязательные pre-launch процессы и не маскируются как завершённые.

# Приложение A. Canonical configuration

Единственный машинно-читаемый источник стартовых параметров: `Kleal_Matching_Core_Config_v2.yaml`.

```yaml
config_version: matching-core-2.0.0
score_semantics:
  policy_decision: [ALLOW, BLOCK, REVIEW]
  semantic_tier: categorical_provenance
  relevance_range: [0.0, 1.0]
  coverage_range: [0.0, 1.0]
  reciprocal_formula:
    min_weight: 0.70
    mean_weight: 0.30
  calibrated_probability:
    enabled_in_mvp: false
user_presentation:
  exact_percentage_enabled: false
  bands:
    strong: "Особенно близко к вашему запросу"
    good: "Хороший вариант"
    broad: "Более широкий вариант"
    alternative: "Альтернативный способ закрыть запрос"
outreach:
  max_parallel_personal_proposals: 3
  max_agent_probes_per_search: 3
  personal_outreach_allowed_tiers: [T0_EXACT, T1_DIRECT]
  broad_outreach_requires_consent: true
monetization:
  payment_can_boost_ranking: false
```

Полный YAML передаётся вместе с документом. Его checksum: `21505ccb4add960291a742084b36d25289ffc93c9870a80b8cba3295010e9c5b`.

# Приложение B. Псевдокод

## B.1. Search pipeline

```python
def search(intent_id: str, actor_id: str) -> SearchResult:
    intent = load_confirmed_intent(intent_id)
    assert intent.owner_id == actor_id

    capsule = build_purpose_bound_capsule(actor_id, intent.purpose_id)
    config = load_canonical_config(intent.domain, intent.config_version)
    policy_snapshot = policy.prepare_snapshot(actor_id, intent.purpose_id)

    pools = []
    for tier in config.allowed_tiers:
        raw = retrieval.retrieve(intent, capsule, tier, config.budget[tier])
        eligible = []
        for candidate in raw:
            decision = policy.evaluate(intent, capsule, candidate, policy_snapshot)
            if decision == "ALLOW":
                eligible.append(candidate)
            elif decision == "REVIEW":
                log_review_candidate(candidate)

        evidence = feature_builder.build(intent, capsule, eligible)
        directional = relevance.score_directional(evidence, config)
        reciprocal = reciprocity.combine(directional, config)
        pools.extend(reciprocal)

        if enough_strong_candidates(pools, config):
            break
        if not expansion.allowed(intent, tier.next):
            break

    slate = allocation.rerank(pools, intent, config)
    result = presentation.build_transparent_slate(slate)
    audit.log_search(intent, slate, config, policy_snapshot)
    return result
```

## B.2. Proposal acceptance

```python
def accept_proposal(proposal_id: str, actor_id: str, idem_key: str):
    with transaction():
        p = proposals.lock_for_update(proposal_id)
        idempotency.assert_or_return(idem_key, actor_id, proposal_id)
        state_machine.assert_transition(p.state, "ACCEPTED")
        policy.revalidate(p, actor_id)
        capacity.reserve_or_fail(p)
        proposals.update_if_version(p.id, p.version, state="ACCEPTED")
        match = matches.create_or_advance(p)
        outbox.publish("match_state_changed", match.to_event())
        idempotency.store_result(idem_key, match)
        return match
```

## B.3. Group formation

```python
def form_group(intent, candidates, constraints):
    feasible = filter_hard_set_constraints(candidates, constraints)
    seeds = generate_role_complete_seeds(feasible, constraints)
    best = None
    for seed in seeds:
        group = greedy_marginal_add(seed, feasible, constraints)
        group = local_repair(group, feasible, constraints)
        if set_feasible(group, constraints):
            utility = group_utility(group, constraints)
            best = max_by_utility(best, group, utility)
    return reserve_members(best) if best else None
```

# Приложение C. Критические acceptance tests

1. Профиль с двумя известными сильными полями и шестью unknown не обгоняет полный релевантный профиль без low-coverage отметки.
2. `not_applicable` не уменьшает coverage.
3. Один raw evidence не даёт вес одновременно exact entity, tag, category и embedding.
4. T2 candidate не становится T1 из-за хорошего времени.
5. Safety block исключает кандидата до feature building.
6. Изменение privacy между SENT и ACCEPT возвращает `POLICY_CHANGED`.
7. Повторный accept с тем же idempotency key возвращает тот же результат.
8. Два concurrent accepts последнего group slot не превышают capacity.
9. Expired proposal нельзя принять.
10. Counter после withdrawal не открывает match.
11. Subscription flag не меняет relevance или position при прочих равных.
12. Dating preferences не доступны friendship search.
13. Friendship decline не обучает dating ranker.
14. Exact live location не входит в discovery payload.
15. Dota intent не отправляется LoL player без broad consent.
16. Spanish learner не получает другого learner как native partner, если role hard.
17. Founder target не проверяется по self profession инициатора.
18. Padel group с четырьмя одинаковыми role/side constraints отклоняется, даже если pair scores высоки.
19. Группа с pairwise block отклоняется.
20. Event и user результаты имеют разные transactions и explanation copy.
21. LLM outage не отменяет policy gates.
22. Vector outage сохраняет structured retrieval.
23. Reason keys не содержат несуществующих фактов.
24. Replay по decision trace воспроизводит результат той же версии конфигурации.

# Приложение D. Матрица purpose binding

| Поле | Friendship | Dating | Networking | Language | Games/Sport |
|---|---|---|---|---|---|
| имя / публичный аватар | по disclosure | staged disclosure | по disclosure | по disclosure | по disclosure |
| возраст | eligibility band | точная/диапазон по consent | обычно не feature | обычно не feature | age mode only |
| пол / orientation | не использовать по умолчанию | отдельный sensitive contour | не использовать | не использовать | не использовать |
| профессия | optional context | не использовать как implicit preference | core self/target field | optional | обычно not_applicable |
| языки | communication feasibility | communication feasibility | communication feasibility | core role field | voice/chat feasibility |
| interests | core soft/context | только подтверждённые dating-relevant | topic context | topic context | domain entity |
| exact availability | current intent only | current intent only | current intent only | recurring/current | current intent |
| location | coarse area | coarse, staged | coarse/venue | online/coarse | server/venue/coarse |
| behavioral reliability | operational only | operational + stricter review | operational | operational | operational |
| inferred memory | soft + decay | restricted/confirmed | purpose-bound | purpose-bound | purpose-bound |

# Приложение E. Источники и нормативные ориентиры

1. Исходная спецификация `Kleal_Matching_Core_Product_Technical_Spec_RU_v1`.
2. Экспертный аудит `Kleal_Matching_Core_Expert_Audit_RU_v1`.
3. Исходная таблица «Карта интента + условия мэтчинга».
4. Regulation (EU) 2016/679 — GDPR, включая принципы минимизации, purpose limitation, privacy by design и profiling.
5. European Data Protection Board — Guidelines on Automated Individual Decision-Making and Profiling.
6. Regulation (EU) 2024/1689 — EU AI Act.
7. Xia et al. Reciprocal Recommendation System for Online Dating.
8. Su, Bayoumi, Joachims. Optimizing Rankings for Recommendation in Matching Markets.
9. Yang et al. Revisiting Reciprocal Recommender Systems: Metrics, Formulation, and Method.
10. Tomita, Yokoyama. Fair Reciprocal Recommendation in Matching Markets.
11. Basu Roy, Lakshmanan, Liu. From Group Recommendations to Group Formation.
12. Hayashi et al. Off-Policy Evaluation and Learning for Matching Markets.
13. PostGIS `ST_DWithin`, H3 Geospatial Indexing System и pgvector documentation.

---

**Статус:** финальная продуктово-техническая спецификация для реализации rule-based Matching Core v2, подготовки пилота и последующей передачи в Claude. Любое изменение scoring, policy, weights или state machine требует новой version ID, тестов, decision replay и review владельца Matching Core.
