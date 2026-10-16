# -*- coding: utf-8 -*-
"""Правила сделки 1:1 — одна таблица вместо девяти копий проверок в ручках `mp_*`.

До таблицы каждая ручка плана держала собственный список условий: семь раз «план открыт?», пять
раз «не заморозка ли?», и у каждой — свой порядок. Порядок расходился (адрес проверял заморозку
раньше состояния, просьба — позже), заморозка у «уже иду» и «переходим в звонок» не проверялась
намеренно, а у «не смогу» превращала отказ в статус — и всё это было видно только тому, кто читал
все девять ручек подряд. Экран при этом выводил те же правила заново из восьми полей проекции
(`locked`, `pending`, `waiting_on`, …) и расходился с сервером молча: кнопку «Подтвердить» он
прятал в заморозке, хотя спека и сервер её разрешают («в заморозке живут только ответы»).

Один порядок для всех: закрытый план → заморозка → условия. Из-за него две ручки отвечают иначе,
чем отвечали: `mp_side` и `mp_move_to_call` на отменённом плане не того вида раньше говорили
NOT_HYBRID, а теперь NOT_OPEN. Закрытый план закрыт независимо от вида встречи — так честнее.

Здесь правила лежат в одном месте и в одном виде, а модуль ЧИСТЫЙ: ни стора, ни часов, ни знания
о том, как устроен словарь плана. Ручка собирает ФАКТЫ (`_mp_facts` в app.py), спрашивает
`refusal(action, facts)` и получает либо None, либо готовый ответ с тем же кодом, который она
отдавала и раньше — коды читают смоук и клиент, менять их нельзя. Проекция `_mp_public` кладёт
`offered(facts)` в поле `actions`, и экран показывает кнопки по нему, а не по своей копии правил.

Факты (все — булевы или короткие строки, считает ручка):
  state         proposed | confirmed | cancelled | done   — как хранится, без переименований
  frozen        окно T−2ч … T+24ч (`_mp_frozen`)
  pending       висит встречное время
  pending_mine  его предложил я
  mode          offline | online | hybrid
  link, place   ссылка / место уже названы
  my_answer     мой ответ на ТЕКУЩУЮ версию: confirmed | declined | None
  is_host       я — тот, кто предложил план (host)
  round         номер раунда до подтверждения (1 — исходный план; нет поля — 1)
  max_rounds    потолок раундов (3; нет поля — 3)
  final         хозяин зафиксировал финальную версию и ждёт ответа гостя (OF.20c → OF.C3d)

Раунды (борд «1:1 · Offline — new layout», разделы B/C, 06.10.2026): пока план не подтверждён,
каждое встречное время — новый раунд, их не больше трёх, на ответ — 6 ч. После третьего встречное
больше не предлагается: хозяин выбирает финальную версию из всех раундов (`fix`), гость остаётся
(`stay`) или выходит без последствий (`leave`). После подтверждения встречное — это перенос, раунды
его не ограничивают.

Молчание (решение владельца 06.10.2026): до подтверждения на каждый ход — 6 ч; не ответил — план
закрывается как «не ответил(а)» без последствий (это делает время, а не действие — `_mp_sweep` в
app.py). После подтверждения молчание ничего не ломает: непринятый перенос снимается, встреча стоит.

Хранимые состояния сознательно не переименованы под спеку §14 (`kleal_states`, машина «plan»):
их читает клиент. Соответствие записано в SPEC_STATE, а TRANSITIONS — это все переходы, которые
ручки на самом деле совершают; тест сверяет каждый с рёбрами машины спеки. Встречное время —
не состояние, а наложение поверх живого плана (борд OF.21a/b: «старое время остаётся, ничего не
отменено»), в терминах спеки это CHANGED, который не двигает `state`.
"""
from collections import namedtuple

OPEN = ("proposed", "confirmed")

# states — в каких состояниях действие вообще возможно; closed — код отказа вне их;
# in_freeze — разрешено ли в окне T−2ч; needs — дополнительные условия, по порядку.
Rule = namedtuple("Rule", "states closed in_freeze needs")

RULES = {
    # Подтвердить нельзя, пока висит встречное время: двое жмут почти одновременно «Подтвердить»
    # и «Другое время», версию поднимает только accept_change — и план выходил подтверждённым на
    # 19:00 с живым предложением на 20:00. Ответ на висящий перенос — только accept/reject_change.
    "confirm":        Rule(OPEN, "NOT_OPEN", True,  ("no_pending",)),
    # В заморозке «не смогу» — не отказ, а живой статус рядом с планом (ручка ветвится сама).
    "decline":        Rule(OPEN, "NOT_OPEN", True,  ()),
    "counter":        Rule(OPEN, "NOT_OPEN", False, ("rounds_left",)),
    # Своё же предложение принять нельзя — это не согласие второго; забрать (reject) — можно.
    "accept_change":  Rule(OPEN, "NOT_OPEN", False, ("pending", "not_mine")),
    "reject_change":  Rule(OPEN, "NOT_OPEN", False, ("pending",)),      # чужому — отказ, своё — забрать
    "address":        Rule(OPEN, "NOT_OPEN", False, ()),
    "ask_place":      Rule(OPEN, "NOT_OPEN", False, ("no_place",)),
    "ask_link":       Rule(OPEN, "NOT_OPEN", False, ("no_link",)),
    # Отмена — правка в смысле спеки, в заморозке закрыта: тому, кто уже вышел из дома, встречу
    # отменять поздно; остаётся «не смогу», и оно встречу не отменяет.
    "cancel":         Rule(OPEN, "NOT_OPEN", False, ()),
    # У закрытой двери и в звонке заморозка не мешает: это действия В МОМЕНТ встречи.
    "move_to_call":   Rule(OPEN, "NOT_OPEN", True,  ("hybrid", "link")),
    "side_call":      Rule(OPEN, "NOT_OPEN", True,  ("hybrid", "link")),
    "side_in_person": Rule(OPEN, "NOT_OPEN", True,  ("hybrid", "place")),
    "status":         Rule(("confirmed",), "NOT_CONFIRMED", True, ()),
    "feedback":       Rule(("confirmed", "done"), "NOT_YET", True, ()),
    # OF.20c «Fix the plan»: после последнего раунда без согласия выбирает хозяин. Правка — значит,
    # в заморозке закрыта, как и встречное время.
    "fix":            Rule(("proposed",), "NOT_OPEN", False, ("host", "rounds_done", "not_final")),
    # OF.C3d: гость отвечает на зафиксированный план — остаться (= подтвердить) или выйти без
    # последствий. Это ответы, не правки: в заморозке живут.
    "stay":           Rule(("proposed",), "NOT_OPEN", True, ("final", "not_host")),
    "leave":          Rule(("proposed",), "NOT_OPEN", True, ("final", "not_host")),
}

# условие → (проверка по фактам, код отказа)
NEEDS = {
    "no_pending": (lambda f: not f.get("pending"), "PENDING_CHANGE"),
    "pending":    (lambda f: bool(f.get("pending")), "NO_PENDING_CHANGE"),
    "not_mine":   (lambda f: not f.get("pending_mine"), "YOUR_OWN_CHANGE"),
    "no_place":   (lambda f: not f.get("place"), "ALREADY_SET"),
    "no_link":    (lambda f: not f.get("link"), "ALREADY_SET"),
    "hybrid":     (lambda f: f.get("mode") == "hybrid", "NOT_HYBRID"),
    "link":       (lambda f: bool(f.get("link")), "NO_LINK"),
    "place":      (lambda f: bool(f.get("place")), "NO_PLACE"),
    # Нет полей раунда (старый план, старые факты) — раунды не мешают ничему.
    "rounds_left": (lambda f: f.get("state") != "proposed"
                    or int(f.get("round") or 1) < int(f.get("max_rounds") or 3), "NO_ROUNDS_LEFT"),
    "rounds_done": (lambda f: int(f.get("round") or 1) >= int(f.get("max_rounds") or 3), "ROUNDS_NOT_DONE"),
    "host":        (lambda f: bool(f.get("is_host")), "HOST_ONLY"),
    "not_host":    (lambda f: not f.get("is_host"), "GUEST_ONLY"),
    "final":       (lambda f: bool(f.get("final")), "NOT_FIXED"),
    # Выбрал — ждёт гостя: перевыбирать, пока тот решает, нельзя (кнопка гаснет сразу после fix).
    "not_final":   (lambda f: not f.get("final"), "ALREADY_FIXED"),
}

FREEZE_NOTE = "less than two hours before the meeting"


def refusal(action, facts):
    """Почему действие сейчас невозможно — готовый ответ ручки; None — можно.

    Порядок один для всех: закрытый план → заморозка → условия. Закрытый план закрыт независимо от
    времени, поэтому NOT_OPEN сильнее LOCKED."""
    rule = RULES.get(str(action or ""))
    if rule is None:
        return {"ok": False, "error": "BAD_ACTION", "allowed": list(RULES)}
    state = facts.get("state")
    if state not in rule.states:
        return {"ok": False, "error": rule.closed, "state": state}
    if facts.get("frozen") and not rule.in_freeze:
        return {"ok": False, "error": "LOCKED", "note": FREEZE_NOTE}
    for need in rule.needs:
        holds, code = NEEDS[need]
        if not holds(facts):
            err = {"ok": False, "error": code}
            if code == "NOT_HYBRID":
                err["mode"] = facts.get("mode")
            return err
    return None


# Чего у встречи этого вида не бывает: у офлайна нет ссылки на звонок, у звонка нет места.
# Это про ПОКАЗ, а не про право: сами ручки `mp_ask` и раньше не смотрели на вид встречи, и их
# ответы менять нельзя — а вот кнопка «пусть хостит он(а)» под офлайновой встречей бессмысленна.
_ASK_MODES = {"ask_place": ("offline", "hybrid"), "ask_link": ("online", "hybrid")}


def offered(facts):
    """Что стоит ПРЕДЛОЖИТЬ участнику на экране прямо сейчас — в порядке таблицы.

    Это `refusal` минус действия, которым нечего делать: повторное «Подтвердить» сервер примет
    (идемпотентно), но кнопка после своего же подтверждения — мусор; и минус просьбы, невозможные
    у этого вида встречи."""
    out = []
    for a in RULES:
        if refusal(a, facts) is not None:
            continue
        if a in _ASK_MODES and facts.get("mode") not in _ASK_MODES[a]:
            continue
        if a == "confirm" and facts.get("my_answer") == "confirmed":
            continue
        # Зафиксированный план гостю отвечают «Stay in» / «Leave the plan» (OF.C3d), а не общими
        # «Подтвердить» / «Не смогу»: сервер их примет, но кнопок две, а не четыре.
        if facts.get("final") and not facts.get("is_host") and a in ("confirm", "decline"):
            continue
        out.append(a)
    return out


# Соответствие хранимых состояний машине «plan» спеки §14 (`kleal_states.STATE_MACHINES`).
# Предложить план = подтвердить его самому, поэтому спековый PROPOSED (никто не подтвердил) у нас
# не встречается: наш `proposed` — это уже PARTIALLY_CONFIRMED. `done` с happened=False — по
# смыслу NO_SHOW, но хранится тем же словом; исход лежит в `outcome`.
SPEC_STATE = {"proposed": "PARTIALLY_CONFIRMED", "confirmed": "CONFIRMED",
              "cancelled": "CANCELLED", "done": "COMPLETED"}

# Все переходы `state`, которые совершают ручки (`mp_respond`, `mp_cancel`, `mp_feedback`,
# `block_user`). Новый переход добавлять сюда — тест сверит его с машиной спеки.
TRANSITIONS = (("proposed", "confirmed"), ("proposed", "cancelled"),
               ("confirmed", "cancelled"), ("confirmed", "done"))
