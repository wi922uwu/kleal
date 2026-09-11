/**
 * Групповой план — кадры GR.25–GR.39 борда «Groups · Offline» (2247:44703) и их онлайн-двойники
 * GRO.25–GRO.35 (2328:66035).
 *
 * ЭКРАН ОДИН. Онлайн-борд повторяет офлайновый кадр в кадр, и отличается ровно строкой места:
 * «Gràcia · Nømad» против «Video call · link saved», плюс пояс у времени. Поэтому здесь нет двух
 * наборов копии — есть `venue()`, который разводит эту одну строку. Два экрана разошлись бы на
 * первой же правке, как уже расходились place/link в мастере 1:1.
 * Разбор расхождений борда и бекенда — kleal-ms/docs/GROUP_PLAN_BOARD_VS_BACKEND.md.
 *
 * Три правила, которые тут легко потерять, потому что в 1:1 они ДРУГИЕ:
 *  — подтверждают ВСЕ (GR.26 «Waiting for everyone»), а не сколько-то; молчащего ждут;
 *  — раундов согласования три (GR.28/29), после них слово за организатором (GR.30);
 *  — голосование СОВЕЩАТЕЛЬНОЕ (GR.35 «The result is advice — Marc makes the final call»):
 *    группа считает голоса, решает организатор, и он вправе не послушать большинство (GR.38).
 *
 * Английские строки взяты с кадров дословно; русские написаны, а не переведены машинно.
 */
import { T } from './i18n';

/** То, что экран получает от сервера (`_gp_public` в services/matching/app.py). */
export type GPlan = {
  id?: string;
  gid?: string;
  when?: string;
  place?: string;
  note?: string;
  starts_at?: number;
  state?: 'proposed' | 'confirmed' | 'locked' | 'below_quorum' | 'cancelled' | 'done' | string;
  /** Кто внёс нынешнее предложение. Раньше выводилось догадкой — см. `proposer` в app/gplan.tsx. */
  proposed_by?: string;
  mode?: 'offline' | 'online' | 'hybrid' | string;
  link?: string;
  needs_link?: boolean;
  needs_place?: boolean;
  details_ready?: boolean;
  sides?: Record<string, { side?: 'in_person' | 'call'; t?: number }>;
  my_side?: 'in_person' | 'call' | null;
  side_counts?: { in_person?: number; call?: number; undecided?: number } | null;
  live?: Record<string, { status?: 'otw' | 'late' | 'here' | 'cant_make_it' | string; eta_min?: number; t?: number }>;
  my_live?: { status?: 'otw' | 'late' | 'here' | 'cant_make_it' | string; eta_min?: number; t?: number } | null;
  confirmed?: string[];
  confirmed_count?: number;
  waiting?: string[];
  declined?: string[];
  my_response?: string;
  needs?: number;
  round?: number;
  max_rounds?: number;
  rounds_used_up?: boolean;
  can_fix?: boolean;
  fixed_by?: string;
  stay_or_leave?: boolean;
  update?: { by?: string; at?: number; was?: { when?: string; place?: string } } | null;
  accept_or_leave?: boolean;
  editable?: boolean;
  locked?: boolean;
  version?: number;
  title?: string;
  my_feedback?: { happened?: boolean; reason?: string; text?: string; rating?: number; t?: number } | null;
  feedback_due?: boolean;
  feedback_expires_at?: number | null;
  feedback_reminder?: boolean;
  feedback_outcome?: {
    state?: 'held' | 'not_held' | 'pending' | string;
    yes?: number;
    no?: number;
    answered?: number;
    of?: number;
  };
};

export type GVote = {
  id?: string;
  plan_id?: string;
  kind?: 'edit' | 'cancel' | string;
  state?: 'open' | 'closed' | string;
  by?: string;
  organiser?: string;
  yes?: number;
  no?: number;
  waiting?: string[];
  my_vote?: boolean | null;
  closes_at?: number;
  advice?: 'change' | 'keep' | string;
  decided?: 'applied' | 'kept' | string;
  awaiting_decision?: boolean;
  i_decide?: boolean;
  proposal?: { when?: string; place?: string; note?: string; starts_at?: number };
};

/**
 * Строка места. ЕДИНСТВЕННОЕ, чем онлайн-кадр отличается от офлайнового, — поэтому здесь, в одной
 * функции, а не в двух экранах. «link saved» — а не сама ссылка: на карточке плана её показывать
 * незачем, открывают её кнопкой, и в чужой руке она бесполезна.
 */
export function venue(p: GPlan): string {
  if ((p.mode || 'offline') === 'online') {
    return p.link
      ? T('Звонок · ссылка сохранена', 'Video call · link saved', 'Video llamada · enlace guardado')
      : T('Звонок · ссылки пока нет', 'Video call · no link yet', 'Video llamada · sin enlace aún');
  }
  return String(p.place || '').trim() || T('Место не указано', 'No place yet', 'Todavía no hay lugar');
}

export function callVenue(p: GPlan): string {
  return p.link
    ? T('Звонок · ссылка сохранена', 'Video call · link saved', 'Video llamada · enlace guardado')
    : T('Звонок · ссылки пока нет', 'Video call · no link yet', 'Video llamada · sin enlace aún');
}

/** Часы до момента, словами. Для «closes in 4h» (GR.36) и «It’s your call» без обратного отсчёта. */
export function hoursLeft(at?: number): number {
  if (!at) return 0;
  return Math.max(0, Math.ceil((Number(at) * 1000 - Date.now()) / 3600000));
}

export const GPLAN = {
  // ---- GR.25 / GRO.25: создание -----------------------------------------
  createTitle: (online: boolean, hybrid = false) =>
    hybrid ? T('Назначь время, место и ссылку', 'Set the time, the place and the link', 'Establecer la hora, el lugar y el enlace')
    : online ? T('Назначь время', 'Set the time', 'Establecer la hora') : T('Назначь время и место', 'Set the time and place', 'Establecer hora y lugar'),
  createNote: () =>
    T(
      'Каждый сможет подтвердить или предложить своё, прежде чем это станет планом.',
      'Everyone gets to confirm or suggest a change before this becomes a plan.'
    , 'Todos pueden confirmar o sugerir un cambio antes de que esto se convierta en un plan.'),
  placePh: () => T('Место — район и заведение', 'Place — area and venue', 'Lugar — zona y local'),
  hybridMissingPlace: () => T('Ссылка сохранена. Осталось добавить место.', 'The link is set. Add the place.', 'El enlace está listo. Añade el lugar.'),
  hybridMissingLink: () => T('Место сохранено. Осталось добавить ссылку.', 'The place is set. Add the call link.', 'El lugar está establecido. Añade el enlace de la llamada.'),
  hybridIncomplete: () => T('Сначала добавь место и ссылку на звонок.', 'Add both the place and the call link first.', 'Añade primero el lugar y el enlace de la llamada.'),
  hybridMissingNote: (needsPlace: boolean) => needsPlace
    ? T('После добавления места группа сможет подтвердить план.',
        'Once the place is added, the group can confirm the plan.', 'Una vez que se añada el lugar, el grupo podrá confirmar el plan.')
    : T('После добавления ссылки группа сможет подтвердить план.',
        'Once the call link is added, the group can confirm the plan.', 'Una vez que se añada el enlace de la llamada, el grupo podrá confirmar el plan.'),
  savePlace: () => T('Сохранить место', 'Save the place', 'Guardar el lugar'),
  chooseSide: () => T('Как ты присоединишься?', 'How are you joining?', '¿Cómo vas a participar?'),
  inPerson: () => T('Лично', 'In person', 'Presencial'),
  onCall: () => T('По звонку', 'On the call', 'En la llamada'),
  sideCounts: (atPlace: number, onCall: number) =>
    T(`${atPlace} придут · ${onCall} по звонку`, `${atPlace} coming · ${onCall} on the call`, `${atPlace} viniendo · ${onCall} en la llamada`),
  sideSaved: () => T('Формат участия обновлён', 'How you’re joining is updated', 'Se ha actualizado cómo participas'),
  joinCallInstead: () => T('Подключиться по звонку', 'Join the call instead', 'Únete a la llamada en su lugar'),
  send: () => T('Отправить группе', 'Send to the group', 'Enviar al grupo'),
  back: () => T('Назад', 'Back', 'Atrás'),
  /** Сервер отказывает по времени: план внутри двухчасового окна подтвердить некому. */
  tooLate: () =>
    T(
      'До встречи меньше двух часов — такой план уже никто не успеет подтвердить. Выбери время подальше.',
      'That starts in under two hours — nobody could confirm it in time. Pick something later.'
    , 'Empieza en menos de dos horas — nadie podría confirmarlo a tiempo. Elige algo más tarde.'),
  needThree: (n: number) =>
    T(`Для плана нужно трое. Не хватает ${n}.`, `A plan needs three. ${n} more to go.`, `Un plan necesita tres. ${n === 1 ? 'Falta uno' : 'Faltan ' + n}.`),
  planExists: () => T('План у этой группы уже есть.', 'This group already has a plan.', 'Este grupo ya tiene un plan.'),
  createFailed: () => T('План не ушёл. Попробуй ещё раз.', 'The plan didn’t go out. Try again.', 'El plan no salió. Inténtalo de nuevo.'),

  // ---- GR.26 / GR.28 / GR.29: согласование ------------------------------
  waitingTitle: () => T('Ждём всех', 'Waiting for everyone', 'Esperando a todos'),
  /** GR.26 дословно, но с живым числом: «all three» на борде — потому что там их трое. */
  waitingNote: (n: number) =>
    T(
      `План начнётся, когда подтвердят все ${n}. Вместо этого можно предложить своё.`,
      `The plan starts when all ${n} confirm. Anyone can suggest a change instead.`
    , `El plan empieza cuando todos los ${n} lo confirman. Cualquiera puede proponer un cambio.`),
  /** GR.28: кто-то предложил своё, и круг пошёл заново. */
  counteredTitle: (who: string) => T(`${who} предлагает другое`, `${who} suggested a change`, `${who} ha propuesto un cambio`),
  counteredNote: (when: string) =>
    T(
      `Теперь предлагают ${when}. Подтверждают заново все.`,
      `Now it’s ${when} instead. Everyone confirms again.`
    , `Ahora es ${when} en su lugar. Todos confirman de nuevo.`),
  /** GR.29: последний раунд — сказать об этом надо ДО того, как человек потратит его впустую. */
  lastRoundNote: (owner: string) =>
    T(
      `Это последний раунд. После него ${owner} закрепит план, и меняться он перестанет.`,
      `This is the last round. After it ${owner} fixes the plan and it stops changing.`
    , `Ésta es la última ronda. Tras ella, ${owner} fija el plan y deja de cambiar.`),
  round: (n: number, max: number) => T(`Раунд ${n} из ${max}`, `Round ${n} of ${max}`, `Ronda ${n} de ${max}`),
  lastRound: () =>
    T('Последний раунд · дальше план закрепляет организатор',
      'Last round · after this the organiser fixes the plan', 'Última ronda · después de esto el organizador fija el plan'),
  confirm: () => T('Подтвердить', 'Confirm', 'Confirmar'),
  suggest: () => T('Предложить другое', 'Suggest a change', 'Sugerir un cambio'),
  /** Подтвердил и ждёшь остальных — кнопки «Confirm» на кадре у тебя уже нет. */
  youConfirmed: (left: number) =>
    left > 0
      ? T(`Ты подтвердил(а). Ждём ещё ${left}.`, `You’ve confirmed. Waiting for ${left} more.`, `Has confirmado. Quedan ${left} más.`)
      : T('Ты подтвердил(а).', 'You’ve confirmed.', 'Lo has confirmado.'),

  // ---- GR.27: своё предложение ------------------------------------------
  suggestTitle: () => T('Предложи своё', 'Suggest a change', 'Sugerir un cambio'),
  suggestNote: (left: number) =>
    T(
      `Твоё предложение заменит нынешнее, и подтверждать будут заново все. После него останется раундов: ${left}.`,
      `Your suggestion replaces the current one and everyone confirms again. ${left} round${left === 1 ? '' : 's'} left after this.`
    , `Tu sugerencia reemplazará a la actual y todos confirmarán de nuevo. Quedan ${left} ronda${left === 1 ? '' : 's'} después de esta.`),
  suggestSend: () => T('Отправить предложение', 'Send the suggestion', 'Enviar la sugerencia'),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),
  roundsUsedUp: () =>
    T('Раунды кончились — дальше решает организатор.', 'Rounds are used up — the organiser decides now.', 'Se han agotado las rondas — ahora decide el organizador.'),

  // ---- GR.30: организатор закрепляет ------------------------------------
  fixTitle: (yes: number, no: number) =>
    T(
      `Подтвердили ${yes}, не подтвердили ${no}`,
      `${yes} confirmed, ${no} didn’t`
    , `${yes} confirmaron, ${no} no`),
  fixNote: (when: string, who: string) =>
    T(
      `Раунды кончились. Можно закрепить ${when} как план — ${who} спросят, остаётся он или выходит.`,
      `Rounds are used up. You can fix ${when} as the plan — ${who} will be asked to stay or leave.`
    , `Se han agotado las rondas. Puedes fijar ${when} como el plan — se preguntará a ${who} si quiere quedarse o irse.`),
  fix: () => T('Закрепить план', 'Fix the plan', 'Arreglar el plan'),
  moreTime: () => T('Дать ещё время', 'Give it more time', 'Dale más tiempo'),
  fixNeedThree: () =>
    T('Согласных меньше трёх — закреплять нечего.', 'Fewer than three agreed — there is no plan to fix.', 'Menos de tres acuerdos — no hay plan para arreglar.'),

  // ---- GR.31: остаться или выйти ----------------------------------------
  fixedTitle: (who: string) => T(`${who} закрепил(а) план`, `${who} fixed the plan`, `${who} ha fijado el plan`),
  fixedNote: (when: string, where: string) =>
    T(
      `${when}, ${where}. Ты этот вариант не подтверждал(а) — можешь всё равно прийти, а можешь выйти из плана.`,
      `${when} at ${where}. You didn’t confirm this one — you can still come, or leave the plan.`
    , `${when} en ${where}. No confirmaste este plan — aún puedes venir o dejarlo.`),
  stay: () => T('Остаться в плане', 'Stay in the plan', 'Quédate en el plan'),
  leavePlan: () => T('Выйти из плана', 'Leave the plan', 'Abandonar el plan'),

  // ---- GR.34: план утверждён --------------------------------------------
  setTitle: () => T('План назначен', 'The plan is set', 'El plan está establecido'),
  setNote: () =>
    T(
      'Удалить из группы больше нельзя. Выйти можно, и любой может попросить группу изменить план.',
      'Nobody can be removed now. Participants can still leave, and anyone can ask the group to change it.'
    , 'Ya no se puede eliminar a nadie. Los participantes aún pueden salir, y cualquiera puede pedir al grupo que lo cambie.'),
  openChat: () => T('Открыть чат группы', 'Open group chat', 'Abrir chat de grupo'),
  changeOrCancel: () => T('Изменить или отменить план', 'Change or cancel the plan', 'Modifica o cancela el plan'),
  locked: () =>
    T('До встречи меньше двух часов — план больше не меняется.',
      'Under two hours to go — the plan doesn’t change any more.', 'Menos de dos horas para que empiece — el plan ya no cambia.'),
  /** GR.40. План НА ПАУЗЕ, а не отменён: решение за организатором, и оно ещё не принято. */
  belowTitle: () => T('Вас осталось двое', 'You’re down to two', 'Solo quedáis dos'),
  belowNote: (who?: string) => T(
    'Групповому плану нужны трое. Пока ты не решишь, ничего не происходит — план на паузе, а не отменён.'
    + (who ? ` Переход в один на один требует согласия ${who} и тратит один из твоих планов 1:1.` : ''),
    'A group plan needs three. Nothing happens until you choose — the plan is on hold, not cancelled.'
    + (who ? ` Switching to one-on-one needs ${who}’s agreement and uses one of your 1:1 plans.` : ''),
    'Un plan de grupo necesita tres. No pasa nada hasta que decidas — el plan está en pausa, no cancelado.'
    + (who ? ` Pasar a uno a uno necesita el visto bueno de ${who} y gasta uno de tus planes 1:1.` : '')
  ),
  inviteMore: () => T('Позвать ещё людей', 'Invite more people', 'Invita a más personas'),
  /** Третий выход с GR.40. Он был описан в коде и не построен: кнопок рисовалось две. */
  switchTo1to1: () => T('Перейти в один на один', 'Switch to one-on-one', 'Cambiar a conversación individual'),
  cancelPlan: () => T('Отменить план', 'Cancel the plan', 'Cancela el plan'),
  /** Лист подтверждения — тот же смысл, что в чате группы: решает не организатор, а оба. */
  switchAskTitle: (who: string) => T(`Перейти в один на один с ${who}?`, `Switch to one-on-one with ${who}?`, `¿Cambiar a una conversación uno a uno con ${who}?`),
  switchAskNote: (who: string) => T(
    `${who} тоже должен согласиться. Если согласится, план закроется, а вы продолжите вдвоём.`,
    `${who} has to agree too. If they do, the plan closes and the two of you keep going.`
  , `${who} también tiene que aceptar. Si lo hace, el plan se cierra y los dos seguís adelante.`),
  switchAskSend: (who: string) => T(`Спросить ${who}`, `Ask ${who} to switch`, `Pide a ${who} que cambie`),
  switchKeep: () => T('Оставить группу', 'Keep the group', 'Mantén el grupo'),
  switchFailed: () => T('Не вышло предложить переход. Попробуй ещё раз.',
                        'Couldn’t offer the switch. Try again.', 'No se pudo proponer el cambio. Inténtalo de nuevo.'),

  /** GR.45: заперто — но сказать «не смогу» можно. Молча не прийти это не выход, а его отсутствие. */
  cantMakeIt: () => T('Не смогу прийти', 'I can’t make it', 'No puedo ir'),
  /** GR.45a: встреча идёт. */
  nowTitle: () => T('Встреча идёт', 'It’s happening now', 'Está sucediendo ahora'),
  nowNote: (who: string) => T(
    `Kleal не видит, что происходит за столом. Завтра спросим всех, состоялось ли${who ? `. Организатор — ${who}` : ''}.`,
    `Kleal can’t see what’s going on at the table. Tomorrow we’ll ask everyone whether it happened${who ? `. Organiser — ${who}` : ''}.`
  , `Kleal no ve lo que pasa en la mesa. Mañana preguntaremos a todos si la quedada salió${who ? `. Organiza: ${who}` : ''}.`),
  hybridNowNote: (atPlace: number, onCall: number) => T(
    `${atPlace} за столом, ${onCall} на звонке. Оба способа открыты — Kleal не видит ни один, поэтому завтра спросим всех.`,
    `${atPlace} are at the place, ${onCall} are on the call. Both ways are open — Kleal can’t see either, so tomorrow we’ll ask everyone.`
  , `${atPlace} están en el lugar, ${onCall} están en la llamada. Ambas opciones están abiertas — Kleal no puede ver ninguna, así que mañana preguntaremos a todos.`),
  imLate: () => T('Я опаздываю', 'I’m running late', 'Llego tarde'),
  tellLateTitle: () => T('Сказать группе, что опаздываешь?', 'Tell them you’re running late?', '¿Les digo que llegas tarde?'),
  tellLateNote: () => T(
    'Группа увидит это сразу. Если удобнее, можно подключиться к звонку.',
    'The group sees this right away. You can switch to the call instead.'
  , 'El grupo lo ve de inmediato. Puedes pasar a la llamada en su lugar.'),
  switchToCall: () => T('Подключиться к звонку', 'Switch to the call', 'Cambiar a la llamada'),
  cantMakeTitle: () => T('Сказать, что ты не придёшь?', 'Tell them you can’t come?', '¿Les dices que no puedes venir?'),
  cantMakeNote: () => T(
    'Встреча продолжится для остальных. Это не отменяет групповой план.',
    'The meetup stays on for everyone else. This does not cancel the group plan.'
  , 'La quedada sigue activa para los demás. Esto no cancela el plan del grupo.'),
  neverMind: () => T('Неважно', 'Never mind', 'No importa'),
  cantMakeConfirm: () => T('Я не смогу', 'I can’t make it', 'No puedo ir'),
  makeOffline: () => T('Оставить только встречу вживую', 'Make it offline only', 'Hazlo solo para reunirse en persona'),
  makeOnline: () => T('Оставить только звонок', 'Make it online only', 'Hazlo solo para reunirse online'),
  /** Второй раз говорить то же самое незачем: подпись сообщает, что группа уже знает. */
  lateSent: () => T('Группа знает, что ты опаздываешь', 'The group knows you’re late', 'El grupo sabe que llegas tarde'),

  cancelled: () => T('План отменён.', 'The plan is cancelled.', 'El plan está cancelado.'),

  // ---- GR.35: попросить группу ------------------------------------------
  askTitle: () => T('Попросить группу изменить план?', 'Ask the group to change this plan?', '¿Pides al grupo que cambie este plan?'),
  /**
   * Кто решит в итоге — организатор. Но если организатор ЭТО ТЫ, называть тебя по имени нельзя:
   * «решает ИванГ» человек про себя не читает, он читает про кого-то третьего. Поэтому у каждой
   * строки про совещательность есть вторая версия, от первого лица.
   */
  askNote: (owner: string) =>
    T(
      `У каждого будет 6 часов на ответ. Результат — совет: последнее слово за ${owner}.`,
      `Everyone gets 6 hours to answer. The result is advice — ${owner} makes the final call.`
    , `A todos se les dan 6 horas para responder. El resultado es una sugerencia — ${owner} tomará la decisión final.`),
  askNoteMine: () =>
    T(
      'У каждого будет 6 часов на ответ. Результат — совет: решать всё равно тебе.',
      'Everyone gets 6 hours to answer. The result is advice — the final call is yours.'
    , 'A todos se les da 6 horas para responder. El resultado es una sugerencia — la decisión final es tuya.'),
  askMove: () => T('Предложить перенос', 'Suggest moving it', 'Sugerir moverlo'),
  askCancel: () => T('Предложить отменить', 'Suggest cancelling it', 'Sugerir cancelarlo'),
  startVote: () => T('Начать голосование', 'Start the vote', 'Iniciar la votación'),
  notNow: () => T('Не сейчас', 'Not now', 'No ahora'),
  voteExists: () => T('Голосование уже идёт.', 'A vote is already open.', 'Ya hay una votación abierta.'),

  // ---- GR.36: голосование идёт ------------------------------------------
  voteOpenTitle: (who: string, kind: string) =>
    kind === 'cancel'
      ? T(`${who} предлагает отменить встречу`, `${who} wants to cancel the plan`, `${who} quiere cancelar el plan`)
      : T(`${who} предлагает перенести встречу`, `${who} wants to move the plan`, `${who} quiere cambiar el plan`),
  voteOpenNote: (h: number, owner: string) =>
    T(
      `Голосование закроется через ${h} ч. Твой ответ — совет: решает ${owner}.`,
      `The vote closes in ${h}h. Your answer is advice — ${owner} makes the final call.`
    , `La votación cierra en ${h}h. Tu respuesta es consejo — ${owner} toma la decisión final.`),
  voteOpenNoteMine: (h: number) =>
    T(
      `Голосование закроется через ${h} ч. Это совет группы — решать тебе.`,
      `The vote closes in ${h}h. It’s the group’s advice — the final call is yours.`
    , `La votación cierra en ${h}h. Es el consejo del grupo — la decisión final es tuya.`),
  voteBadge: (h: number) => T(`Голосование · ${h} ч`, `Vote open · closes in ${h}h`, `Votación abierta · cierra en ${h}h`),
  openVote: () => T('Открыть голосование', 'Open the vote', 'Abre la votación'),
  voteSheetTitle: (h: number, kind: string) =>
    kind === 'cancel'
      ? T(`Отменить план? ${h} ч`, `Cancel the plan? ${h}h left`, `¿Cancelar el plan? Faltan ${h}h`)
      : T(`Изменить план? ${h} ч`, `Change the plan? ${h}h left`, `¿Cambiar el plan? Faltan ${h}h`),
  voteSheetNote: (who: string, what: string, owner: string) =>
    T(
      `${who} предлагает ${what}. Твой голос — совет: решает ${owner}.`,
      `${who} suggests ${what} instead. Your vote is advice — ${owner} makes the final call.`
    , `${who} propone ${what} en su lugar. Tu voto es orientativo — ${owner} toma la decisión final.`),
  voteYes: (kind: string) =>
    kind === 'cancel' ? T('Да, отменить', 'Yes, cancel it', 'Sí, cancelar') : T('Да, изменить', 'Yes, change it', 'Sí, cambiarlo'),
  voteNo: () => T('Нет, оставить', 'No, keep it', 'No, déjalo así'),
  voted: () => T('Твой голос учтён. Ждём остальных.', 'Your answer is in. Waiting for the others.', 'Tu respuesta está hecha. Esperando a los demás.'),

  // ---- GR.37: организатор решает ----------------------------------------
  closedTitle: () => T('Голосование закрыто', 'The vote is closed', 'La votación está cerrada'),
  closedNoteOwner: (yes: number, no: number, silent: number) =>
    T(
      `За — ${yes}, против — ${no}, не ответили — ${silent}. Решать тебе.`,
      `${yes} asked to change it, ${no} against, ${silent} didn’t answer. It’s your call.`
    , `${yes} pidió cambiarlo, ${no} en contra, ${silent} no respondió. Es tu decisión.`),
  decide: () => T('Посмотреть числа и решить', 'See the numbers and decide', 'Ve los números y decide'),
  tally: (yes: number, no: number, silent: number) =>
    T(
      `${yes} за · ${no} против · ${silent} не голосовали`,
      `${yes} for · ${no} against · ${silent} didn’t vote`
    , `${yes} a favor · ${no} en contra · ${silent} no votó`),
  decideNote: () =>
    T(
      'Голосование закрыто. Решать тебе — группа попросила, ты решаешь.',
      'The vote is closed. It’s your call — the group asked, you decide.'
    , 'La votación está cerrada. Es tu decisión — el grupo preguntó, tú decides.'),
  applyChange: () => T('Изменить план', 'Change the plan', 'Modifica el plan'),
  applyCancel: () => T('Отменить встречу', 'Cancel the meetup', 'Cancela la quedada'),
  keepIt: () => T('Оставить как есть', 'Keep it as it is', 'Déjalo como está'),

  // ---- GR.38: участнику объявили итог -----------------------------------
  keptTitle: (owner: string) => T(`${owner} оставил(а) план как есть`, `${owner} kept the plan as it is`, `${owner} mantuvo el plan como estaba`),
  keptNote: (when: string, yes: number, of: number) =>
    T(
      `${when} остаётся. Перенести просили ${yes} из ${of} — на Kleal решает организатор.`,
      `${when} stays. ${yes} of ${of} asked to move it — on Kleal the organiser decides.`
    , `${when} se mantiene. ${yes} de ${of} pidieron cambiarlo — en Kleal el organizador decide.`),
  waitingDecision: (owner: string) =>
    T(`Голоса посчитаны. Ждём решения: ${owner}.`, `The votes are counted. Waiting on ${owner} to decide.`, `Se cuentan las votaciones. A la espera de que ${owner} decida.`),
  gotIt: () => T('Понятно', 'Got it', 'Entendido'),

  // ---- GR.32 / GRO.32: организатор правит план --------------------------
  updateTitle: () => T('Изменить время или место', 'Change the time or place', 'Modifica la hora o el lugar'),
  updateNote: (from: string, to: string) =>
    T(
      `Ты переносишь с ${from} на ${to}. Каждый, кто уже согласился, заново примет или выйдет, а открытое приглашение обновится на новое время.`,
      `You’re moving it from ${from} to ${to}. Everyone who already joined has to accept or leave, and the open invite is updated to the new time.`
    , `Estás moviéndolo de ${from} a ${to}. Todos los que ya se hayan unido deberán aceptar o salir, y la invitación abierta se actualizará a la nueva hora.`),
  wasLine: (was: string) => T(`было ${was}`, `was ${was}`, `era ${was}`),
  unchanged: () => T('без изменений', 'unchanged', 'sin cambios'),
  sendUpdate: () => T('Отправить изменение', 'Send the update', 'Enviar la actualización'),
  keepTerms: () => T('Оставить как есть', 'Keep current terms', 'Mantén los términos actuales'),

  // ---- GR.33 / GRO.33: участнику пришла правка --------------------------
  changedTitle: (who: string) => T(`${who} изменил(а) план`, `${who} changed the plan`, `${who} cambió el plan`),
  changedNote: (from: string, to: string) =>
    T(
      `С ${from} на ${to}. Прими, чтобы остаться в группе, или выйди — группа продолжится в любом случае.`,
      `From ${from} to ${to}. Accept to stay in the group, or leave — the group carries on either way.`
    , `De ${from} a ${to}. Acepta para quedarte en el grupo, o abandona — el grupo continúa de todas formas.`),
  accept: () => T('Принять изменение', 'Accept the change', 'Acepta el cambio'),
  leaveGroup: () => T('Выйти из группы', 'Leave the group', 'Abandonar el grupo'),

  // ---- GRO.25a: онлайн без ссылки ---------------------------------------
  linkTitle: () => T('Добавь ссылку на звонок', 'Add the call link', 'Añade el enlace de la llamada'),
  linkNote: (when: string) =>
    T(
      `${when} согласовано. Пока ссылки нет, группа видит «ссылка будет» — интент завели без неё, и без ссылки подключиться некуда.`,
      `${when} is agreed. The group sees “link coming” until you paste one — the intent had no link, so nobody can join without it.`
    , `${when} acordado. El grupo ve «enlace pendiente» hasta que pegues uno — la propuesta no tenía enlace, así que nadie puede unirse sin él.`),
  linkPh: () => T('Вставь ссылку на Zoom, Meet — любую', 'Paste a Zoom, Meet or any link', 'Pega un enlace de Zoom, Meet o cualquier otro'),
  saveLink: () => T('Сохранить ссылку', 'Save the link', 'Guardar el enlace'),
  askHost: () => T('Попросить кого-то другого стать хостом', 'Ask the group to host instead', 'Pide al grupo que lo organice'),
  /** Сообщение в чат, которым «попросить хоста» и делается: отдельной сущности у этого нет. */
  askHostMsg: () =>
    T('Нужна ссылка на звонок — может кто-то поднять её у себя?',
      'We need a call link — can someone host it?', 'Necesitamos un enlace para la llamada — ¿alguien puede organizarla?'),
  badLink: () => T('Это не похоже на ссылку.', 'That doesn’t look like a link.', 'Eso no parece un enlace.'),
  linkComing: () => T('Ссылка будет', 'Link coming', 'Enlace en camino'),
  openLink: () => T('Открыть звонок', 'Open the call', 'Abre la llamada'),

  // ---- роли и состояния в составе ---------------------------------------
  roleOrganiser: () => T('Организатор', 'Organiser', 'Organizador'),
  stConfirmed: () => T('Подтвердил(а)', 'Confirmed', 'Confirmado'),
  stOrganiserConfirmed: () => T('Организатор · подтвердил(а)', 'Organiser · confirmed', 'Organizador · confirmado'),
  stSuggested: () => T('Предложил(а) это · подтвердил(а)', 'Suggested this · confirmed', 'Lo sugirió · confirmado'),
  stWaiting: () => T('Пока не ответил(а)', 'Hasn’t answered yet', 'Todavía no ha respondido'),
  stYourTurn: () => T('Твой ход', 'Your turn', 'Es tu turno'),
  stDidnt: () => T('Не подтвердил(а)', 'Didn’t confirm', 'No confirmado'),
  stWillAccept: () => T('Ответит на изменение', 'Will be asked to accept', 'Se le pedirá que lo acepte'),
  /** GR.27: предложение внесено, и подтверждать его будут заново — включая того, кто уже успел. */
  stWillConfirmAgain: () => T('Подтвердит заново', 'Will confirm again', 'Volverá a confirmar'),
  /** GR.27: этот человек прямо сейчас набирает встречное предложение. */
  stSuggesting: () => T('Предлагает своё', 'Suggesting', 'Sugiriendo'),
  /** GR.29: предложил организатор — на борде это отдельная подпись, а не «Организатор · подтвердил». */
  stOrganiserSuggested: () => T('Организатор · предложил(а) это', 'Organiser · suggested this', 'Organizador · sugirió esto'),
  /** GR.39: вышедший остаётся в составе строкой — иначе непонятно, почему людей стало меньше. */
  stLeft: (ago: string) => T(`Вышел(а) · ${ago}`, `Left · ${ago}`, `Se fue · ${ago}`),
  /**
   * GR.39. Главное на кадре — не сам уход, а что встреча в силе. Человек, увидевший «кто-то
   * вышел», первым делом спрашивает «всё отменяется?», и ответ должен стоять в той же строке.
   */
  stillOn: (n: number) => T(
    `${n} ${n === 1 ? 'человек идёт' : n < 5 ? 'человека идут' : 'человек идут'} — встреча в силе.`,
    `${n} ${n === 1 ? 'person is' : 'people are'} still going, so the meetup is on.`
  , `${n === 1 ? '1 persona sigue apuntada' : n + ' personas siguen apuntadas'}, así que la quedada sigue en pie.`),
  stChanging: () => T('Организатор · меняет', 'Organiser · changing it', 'Organizador · lo está cambiando'),
  stChanged: () => T('Организатор · изменил(а)', 'Organiser · changed it', 'Organizador · lo cambió'),
  stInGroup: () => T('В группе', 'In the group', 'En el grupo'),
  stLate: () => T('Опаздывает', 'Running late', 'Llegando tarde'),
  stCantMakeIt: () => T('Не сможет прийти', 'Can’t make it', 'No puede asistir'),
  you: () => T('Ты', 'You', 'Tú'),

  // ---- общие отказы ------------------------------------------------------
  failed: () => T('Не получилось. Попробуй ещё раз.', 'That didn’t go through. Try again.', 'Eso no funcionó. Inténtalo de nuevo.'),
  notOrganiser: () => T('Это может только организатор.', 'Only the organiser can do that.', 'Solo el organizador puede hacerlo.'),
  gone: () => T('Этого плана больше нет.', 'This plan is gone.', 'Este plan ya no existe.'),
};

/**
 * Подпись под именем в составе — та самая колонка, где на борде стоит «Organiser · confirmed»,
 * «Hasn’t answered yet», «Your turn». Собрана в одном месте, потому что состояний семь, и
 * разложенные по экрану они разъезжаются: на GR.27 «Will confirm again», на GR.32 «Will be asked
 * to accept» — это одна и та же мысль в разных фазах, и путать их нельзя.
 */
/**
 * «20 минут назад» под именем вышедшего. Часы и дни, а не точное время: на кадре важно НЕДАВНО
 * это случилось или давно, а не в какую минуту.
 */
export function leftAgo(ts?: number, nowS = Date.now() / 1000): string {
  const sec = Math.max(0, nowS - Number(ts || 0));
  const m = Math.floor(sec / 60);
  if (m < 1) return T('только что', 'just now', 'justo ahora');
  if (m < 60) return T(`${m} мин назад`, `${m} minutes ago`, `Hace ${m} ${m === 1 ? 'minuto' : 'minutos'}`);
  const h = Math.floor(m / 60);
  if (h < 24) return T(`${h} ч назад`, `${h} hours ago`, `Hace ${h} ${h === 1 ? 'hora' : 'horas'}`);
  return T(`${Math.floor(h / 24)} дн назад`, `${Math.floor(h / 24)} days ago`, `Hace ${Math.floor(h / 24)} ${Math.floor(h / 24) === 1 ? 'día' : 'días'}`);
}

export function memberState(
  name: string,
  p: GPlan,
  opts: { owner?: string; me?: string; proposer?: string }
): { text: string; done: boolean } {
  const eq = (a?: string, b?: string) =>
    String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const isOwner = eq(name, opts.owner);
  const isMe = eq(name, opts.me);
  const confirmed = (p.confirmed || []).some((c) => eq(c, name));
  const live = Object.entries(p.live || {}).find(([key]) => eq(key, name))?.[1];

  if (live?.status === 'cant_make_it') return { text: GPLAN.stCantMakeIt(), done: false };
  if (live?.status === 'late') return { text: GPLAN.stLate(), done: false };

  if (confirmed) {
    if (p.update && eq(name, p.update.by)) return { text: GPLAN.stChanged(), done: true };
    // Предложил организатор — на борде GR.29 у него своя подпись, а не общая «Организатор ·
    // подтвердил(а)»: иначе из состава не видно, чьё предложение сейчас на столе.
    if (eq(name, opts.proposer)) {
      return { text: isOwner ? GPLAN.stOrganiserSuggested() : GPLAN.stSuggested(), done: true };
    }
    if (isOwner) return { text: GPLAN.stOrganiserConfirmed(), done: true };
    return { text: GPLAN.stConfirmed(), done: true };
  }
  // Не подтвердил. Что именно от него ждут — зависит от фазы, и на борде это разные слова.
  // «Не подтвердил» вместо «пока не ответил» — уже на последнем раунде (GR.30 показывает эту
  // подпись ДО закрепления): когда раундов больше нет, «пока» обещает время, которого не осталось.
  if (p.fixed_by || (p.rounds_used_up && p.state === 'proposed')) {
    return { text: GPLAN.stDidnt(), done: false };
  }
  if (p.update) return { text: isMe ? GPLAN.stYourTurn() : GPLAN.stWillAccept(), done: false };
  if (isOwner) return { text: GPLAN.roleOrganiser(), done: false };
  return { text: isMe ? GPLAN.stYourTurn() : GPLAN.stWaiting(), done: false };
}
