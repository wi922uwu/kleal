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
  /** Когда организатор зафиксировал план — начало окна «Staying» (полоса GR.30/31). */
  fixed_at?: number | null;
  /** Версии по раундам — лист «Pick the final version» (GR.29a). */
  rounds_log?: { round?: number; by?: string; by_id?: string; when?: string; place?: string; starts_at?: number }[];
  /** Пауза «вас двое» (GR.40–40f): 12 ч паузы, потом вопрос обоим до двух часов до встречи. */
  hold?: {
    since?: number; ends_at?: number; ask?: boolean; ask_at?: number | null; until?: number | null;
    answered?: number; of?: number; my_answer?: 'one_on_one' | 'let_go' | null;
    answered_by?: string[]; one_on_one_by?: string[]; let_go_by?: string[];
    closed?: number | null; why?: 'expired' | 'let_go' | null;
  } | null;
  stay_or_leave?: boolean;
  update?: { by?: string; at?: number; was?: { when?: string; place?: string; link?: string } } | null;
  accept_or_leave?: boolean;
  editable?: boolean;
  locked?: boolean;
  version?: number;
  title?: string;
  my_feedback?: { happened?: boolean; reason?: string; text?: string; rating?: number; t?: number } | null;
  /** Кто уже ответил на «Did you meet?» — только факт, без ответа (GR.47/GR.50). */
  feedback_answered?: string[];
  started?: boolean;
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

/** Сервис звонка по ссылке — им подписаны карточки GRO.45–48 («Zoom · your link», «Video call · Zoom»). */
export function callService(link?: string): string {
  const l = String(link || '').toLowerCase();
  if (/zoom\.(us|com)/.test(l)) return 'Zoom';
  if (/meet\.google\./.test(l)) return 'Meet';
  if (/teams\.(microsoft|live)\./.test(l)) return 'Teams';
  if (/webex\./.test(l)) return 'Webex';
  if (/jit\.si|jitsi/.test(l)) return 'Jitsi';
  if (/whereby\./.test(l)) return 'Whereby';
  if (/discord\./.test(l)) return 'Discord';
  return '';
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
  /** Подпись полосы раундов в новой раскладке: слово слева, «1 / 3» по центру (кадр GR.26). */
  roundWord: () => T('Раунд', 'Round', 'Ronda'),
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
  fix: () => T('Закрепить план', 'Fix the plan', 'Arreglar el plan'),
  // ---- GR.29a: выбрать финальную версию ----------------------------------------------------
  pickFinal: () => T('Выбери финальную версию', 'Pick the final version', 'Elige la versión final'),
  pickFinalNote: () => T('После этого план больше не меняется. Каждого спросят, остаётся он или выходит.',
    'The plan stops changing after this. Everyone will be asked to stay or leave.',
    'El plan deja de cambiar después de esto. A todos se les preguntará si se quedan o se van.'),
  fixThis: () => T('Закрепить этот план', 'Fix this plan', 'Fijar este plan'),
  versionMeta: (who: string, round: number, mine: boolean, first: boolean) => first
    ? (mine ? T(`Твой план · раунд ${round}`, `Your plan · round ${round}`, `Tu plan · ronda ${round}`)
            : T(`План ${who} · раунд ${round}`, `${who}’s plan · round ${round}`, `Plan de ${who} · ronda ${round}`))
    : (mine ? T(`Твоё изменение · раунд ${round}`, `Your change · round ${round}`, `Tu cambio · ronda ${round}`)
            : T(`Предложение ${who} · раунд ${round}`, `${who}’s suggestion · round ${round}`, `Propuesta de ${who} · ronda ${round}`)),
  aloneVersion: () => T('Эту версию подтвердил только ты — закрепить её одному нельзя. Выбери другую.',
    'Only you agreed to this version, so it can’t be fixed on your own. Pick another.',
    'Solo tú aceptaste esta versión, así que no se puede fijar sola. Elige otra.'),
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

  // ---- «GR · Offline — new layout» (5828:13134): заголовки с именами ------------------------
  /** «Jane and Marc», «Jane, Marc and Elly». */
  names: (list: string[]) => {
    if (list.length <= 1) return list.join('');
    const last = list[list.length - 1];
    return T(`${list.slice(0, -1).join(', ')} и ${last}`, `${list.slice(0, -1).join(', ')} and ${last}`,
             `${list.slice(0, -1).join(', ')} y ${last}`);
  },
  /** GR.26 / GR.26a: организатор ждёт ответов. */
  waitingFor: (who: string) => T(`Ждём: ${who}`, `Waiting for ${who}`, `Esperando a ${who}`),
  waitingForNote: (who: string, many: boolean) => many
    ? T(`План начнётся, когда подтвердят ${who}. Любой может предложить своё.`,
        `The plan starts when ${who} confirm. Anyone can suggest a change instead.`,
        `El plan empieza cuando ${who} confirmen. Cualquiera puede proponer un cambio.`)
    : T(`План начнётся, когда подтвердит ${who}. Можно и предложить своё.`,
        `The plan starts when ${who} confirms. Anyone can suggest a change instead.`,
        `El plan empieza cuando ${who} confirme. Cualquiera puede proponer un cambio.`),
  waitingForNote2: (done: string, who: string) =>
    T(`${done}: подтверждено. План начнётся, когда подтвердит и ${who} — или предложит своё.`,
      `${done} confirmed. The plan starts when ${who} confirms too — or suggests a change.`,
      `${done} ha confirmado. El plan empieza cuando ${who} confirme también — o proponga un cambio.`),
  /** GR.26d: участнику пришло предложение. */
  proposedTitle: (who: string) => T(`${who} предлагает план`, `${who} proposed a plan`, `${who} ha propuesto un plan`),
  proposedNote: (others: string) => others
    ? T(`Подтверди или предложи своё. План начнётся, когда подтвердите ты и ${others}.`,
        `Confirm it, or suggest a change. The plan starts when you and ${others} both confirm.`,
        `Confírmalo o propón un cambio. El plan empieza cuando tú y ${others} confirméis.`)
    : T('Подтверди или предложи своё. План начнётся, когда подтвердишь ты.',
        'Confirm it, or suggest a change. The plan starts when you confirm.',
        'Confírmalo o propón un cambio. El plan empieza cuando confirmes.'),
  /** GR.27a: организатор сам поменял своё предложение. */
  youChangedTitle: () => T('Ты изменил(а) план', 'You changed the plan', 'Cambiaste el plan'),
  youChangedNote: (round: number, who: string) =>
    T(`Начался раунд ${round}. План встанет, когда подтвердят ${who} — или предложат своё.`,
      `Round ${round} started. It’s set when ${who} confirm — or they suggest a change.`,
      `Empezó la ronda ${round}. Queda fijado cuando ${who} confirmen — o propongan un cambio.`),
  /** GR.28 / GR.29: кто-то предложил своё. */
  suggestedNote: (when: string) =>
    T(`Теперь ${when}. Подтверждают заново все.`, `${when} now. Everyone confirms again.`, `Ahora ${when}. Todos confirman de nuevo.`),
  lastRoundMine: () => T(' Это последний раунд — после него план закрепляешь ты.',
                         ' This is the last round — after it you fix the plan.',
                         ' Es la última ronda — después la fijas tú.'),
  lastRoundOf: (owner: string) => T(` Это последний раунд — после него план закрепит ${owner}.`,
                                    ` This is the last round — after it ${owner} fixes the plan.`,
                                    ` Es la última ronda — después ${owner} fija el plan.`),
  changeThePlan: () => T('Изменить план', 'Change the plan', 'Cambiar el plan'),
  editTheChange: () => T('Поправить изменение', 'Edit the change', 'Editar el cambio'),
  /** GR.30: организатор закрепил — остальные решают. */
  fixedMineTitle: () => T('План закреплён', 'Plan fixed', 'Plan fijado'),
  fixedMineNote: (when: string, who: string) =>
    T(`Ты закрепил(а) ${when}. ${who} решают, остаться или выйти, — потом план запирается.`,
      `You fixed ${when}. ${who} decide to stay or leave — then the plan locks.`,
      `Fijaste ${when}. ${who} deciden si se quedan o salen — luego el plan se bloquea.`),
  fixedTitle2: () => T('План закреплён', 'The plan is fixed', 'El plan está fijado'),
  /** GR.34: утверждён — у организатора. */
  confirmedTitle: () => T('Подтверждено', 'Confirmed', 'Confirmado'),
  confirmedNote: (who: string, place: string) =>
    T(`Точное место теперь видят ${who}: ${place}.`, `${who} have the exact spot now: ${place}.`,
      `${who} ya tienen el sitio exacto: ${place}.`),
  changeTimeOrPlace: () => T('Изменить время или место', 'Change the time or place', 'Cambiar la hora o el lugar'),
  askToChange: () => T('Попросить изменить план', 'Ask to change the plan', 'Pedir cambiar el plan'),
  /** GR.32a / GR.33: правка организатора. */
  updateSentTitle: () => T('Изменение отправлено', 'Update sent', 'Cambio enviado'),
  updateSentNote: (who: string) =>
    T(`${who} должны принять новое время или выйти.`, `${who} have to accept the new time or leave.`,
      `${who} tienen que aceptar la nueva hora o salir.`),
  editTheUpdate: () => T('Поправить изменение', 'Edit the update', 'Editar el cambio'),
  timeChangedTitle: () => T('Время изменилось', 'The time changed', 'La hora ha cambiado'),
  placeChangedTitle: () => T('Место изменилось', 'The place changed', 'El lugar ha cambiado'),
  // ---- Онлайн-группа, раздел B (борд «GR · Online», GRO.31–34) ---------------------------
  /** GRO.31: «Friday 24 at 19:30 on the call. You didn’t confirm this one — you can still join…». */
  fixedNoteCall: (when: string) =>
    T(`${when}, по звонку. Ты этот вариант не подтверждал(а) — можешь всё равно подключиться, а можешь выйти из плана.`,
      `${when} on the call. You didn’t confirm this one — you can still join, or leave the plan.`,
      `${when} por llamada. No confirmaste este plan — aún puedes unirte o dejarlo.`),
  /** GRO.34: «Jane and Marc have the link now. It opens for everyone at 20:20.» */
  confirmedNoteCall: (who: string, opens: string) =>
    T(`Ссылку теперь видят ${who}. Она откроется для всех в ${opens}.`,
      `${who} have the link now. It opens for everyone at ${opens}.`,
      `${who} ya tienen el enlace. Se abre para todos a las ${opens}.`),
  /** GRO.32 / GRO.34: кнопка и заголовок листа правки. */
  changeTimeOrLink: () => T('Изменить время или ссылку', 'Change the time or link', 'Cambiar la hora o el enlace'),
  changedNote2: (from: string, to: string, samePlace: boolean, online = false, hybrid = false) =>
    // GRH.33: у гибрида неизменными остаются оба входа — «same place and link».
    hybrid ? T(`С ${from} на ${to}${samePlace ? ', место и ссылка прежние' : ''}. Прими, чтобы остаться в плане, или выйди — план идёт в любом случае.`,
               `From ${from} to ${to}${samePlace ? ', same place and link' : ''}. Accept to stay in the plan, or leave — the plan carries on either way.`,
               `De ${from} a ${to}${samePlace ? ', mismo sitio y enlace' : ''}. Acepta para seguir en el plan, o sal — el plan sigue igualmente.`) :
    online ? T(`С ${from} на ${to}${samePlace ? ', ссылка прежняя' : ''}. Прими, чтобы остаться в плане, или выйди — план идёт в любом случае.`,
               `From ${from} to ${to}${samePlace ? ', same link' : ''}. Accept to stay in the plan, or leave — the plan carries on either way.`,
               `De ${from} a ${to}${samePlace ? ', mismo enlace' : ''}. Acepta para seguir en el plan, o sal — el plan sigue igualmente.`) :
    T(`С ${from} на ${to}${samePlace ? ', место прежнее' : ''}. Прими, чтобы остаться в плане, или выйди — план идёт в любом случае.`,
      `From ${from} to ${to}${samePlace ? ', same place' : ''}. Accept to stay in the plan, or leave — the plan carries on either way.`,
      `De ${from} a ${to}${samePlace ? ', mismo sitio' : ''}. Acepta para seguir en el plan, o sal — el plan sigue igualmente.`),
  /** GR.36–38: голосование. */
  askedChangeTitle: (who: string, kind: string) => kind === 'cancel'
    ? T(`${who} просит отменить план`, `${who} asked to cancel the plan`, `${who} pidió cancelar el plan`)
    : T(`${who} просит изменить план`, `${who} asked to change the plan`, `${who} pidió cambiar el plan`),
  voteAdvice: (owner: string) => T(`Твой голос — совет: решает ${owner}.`, `Your vote is advice — ${owner} makes the final call.`,
                                   `Tu voto es un consejo — ${owner} decide.`),
  voteAdviceMine: () => T('Группа голосует. Это совет — решать тебе.', 'The group is voting. It’s advice — the final call is yours.',
                          'El grupo está votando. Es un consejo — decides tú.'),
  voteClosedNote: (moved: boolean) => moved
    ? T('Группа попросила перенести. Решать тебе.', 'The group asked to move it. It’s your call.', 'El grupo pidió moverlo. Decides tú.')
    : T('Группа хочет оставить как есть. Решать тебе.', 'The group wants to keep it. It’s your call.', 'El grupo quiere mantenerlo. Decides tú.'),
  keptNote2: (when: string) =>
    T(`${when} остаётся. Группа просила перенести — на Kleal решает организатор.`,
      `${when} stays. The group asked to move it — on Kleal the organiser decides.`,
      `${when} se mantiene. El grupo pidió moverlo — en Kleal decide el organizador.`),
  /** Полосы-счётчики под карточкой: «Staying 2 of 3 · Locks in 2h», «Vote 1 of 2 · Ends in 4h». */
  meterStaying: () => T('Остаются', 'Staying', 'Se quedan'),
  meterVote: () => T('Голоса', 'Vote', 'Votos'),
  meterAccepted: () => T('Приняли', 'Accepted', 'Aceptaron'),
  meterOf: (n: number) => T(`из ${n}`, `of ${n}`, `de ${n}`),
  locksIn: (s: string) => T(`Запрётся через ${s}`, `Locks in ${s}`, `Se bloquea en ${s}`),
  endsIn: (s: string) => T(`Закончится через ${s}`, `Ends in ${s}`, `Termina en ${s}`),
  /** Статусы людей по борду. */
  stProposedThis: () => T('Предложил(а) это', 'Proposed this', 'Lo propuso'),
  stConfirmedSuggested: () => T('Подтвердил(а) · предложил(а) это', 'Confirmed · Suggested this', 'Confirmado · lo propuso'),
  stChangedIt: () => T('Изменил(а)', 'Changed it', 'Lo cambió'),
  stChangingIt: () => T('Меняет', 'Changing it', 'Lo está cambiando'),
  stAnswerNeeded: () => T('Нужен твой ответ', 'Your answer needed', 'Falta tu respuesta'),
  stFixedThePlan: () => T('Закрепил(а) план', 'Fixed the plan', 'Fijó el plan'),
  stStaying: () => T('Остаётся', 'Staying', 'Se queda'),
  stDeciding: () => T('Решает', 'Deciding', 'Decidiendo'),
  stYourCall: () => T('Решать тебе', 'Your call', 'Decides tú'),
  stAccepted: () => T('Принял(а)', 'Accepted', 'Aceptó'),
  stAskedToChange: () => T('Просит изменить', 'Asked to change it', 'Pidió cambiarlo'),
  stVoteNeeded: () => T('Нужен твой голос', 'Your vote needed', 'Falta tu voto'),
  stVoted: () => T('Проголосовал(а)', 'Voted', 'Votó'),
  stLateTold: () => T('Опаздывает · группа знает', 'Running late · told them', 'Llega tarde · avisó'),

  // ---- День встречи (раздел D) и после (раздел E) --------------------------------------------
  startsIn: (min: number) => min < 60
    ? T(`Начало через ${min} мин`, `Starts in ${min} minutes`, `Empieza en ${min} minutos`)
    : T(`Начало через ${Math.floor(min / 60)} ч ${min % 60} мин`, `Starts in ${Math.floor(min / 60)}h ${min % 60}m`,
        `Empieza en ${Math.floor(min / 60)} h ${min % 60} min`),
  lateHint: (who: string) => T(`Если опаздываешь, скажи ${who} — они ждут в том же месте.`,
                               `If you’re running late, tell ${who} — they wait at the same place.`,
                               `Si llegas tarde, avisa a ${who} — esperan en el mismo sitio.`),
  lateToldTitle: () => T('Группа знает, что ты опаздываешь', 'The group knows you’re late', 'El grupo sabe que llegas tarde'),
  lateToldNote: (who: string) => T(`${who} уже видят это. Ничего не отменяется, и это не считается неявкой.`,
                                   `${who} see it now. Nothing is cancelled, and it isn’t counted as a no-show.`,
                                   `${who} ya lo ven. No se cancela nada y no cuenta como no presentarse.`),
  nowTitle2: () => T('Встреча сейчас', 'Your meetup is now', 'Tu quedada es ahora'),
  nowNote2: (who: string) => T(`Уже начинается. Если не сможешь прийти, скажи ${who} — для них встреча в силе.`,
                               `It’s starting now. If you can’t make it, tell ${who} — the meetup stays on for them.`,
                               `Ya empieza. Si no puedes venir, avisa a ${who} — para ellos la quedada sigue.`),
  cantToldTitle: () => T('Ты сказал(а), что не придёшь', 'You told them you can’t come', 'Les dijiste que no puedes ir'),
  cantToldNote: (who: string) => T(`${who} уже видят это. Для них встреча в силе — ты ничего не отменил(а).`,
                                   `${who} see it now. The meetup is still on for them — you didn’t cancel anything.`,
                                   `${who} ya lo ven. Para ellos la quedada sigue — no cancelaste nada.`),
  cantComeTitle: (who: string) => T(`${who} не придёт`, `${who} can’t come`, `${who} no puede venir`),
  cantComeNote: (rest: string) => T(`Только что сказал(а) группе. Для тебя и ${rest} встреча в силе — ничего не отменено и не на паузе.`,
                                    `They just told the group. The meetup is still on for you and ${rest} — nothing is cancelled or put on hold.`,
                                    `Acaba de avisar al grupo. Para ti y ${rest} la quedada sigue — nada se cancela ni se pausa.`),
  kleaBlind: () => T('Kleal не видит встречу', 'Kleal can’t see the meetup', 'Kleal no ve la quedada'),
  kleaBlindNote: (n: number) => T(`Здесь о ней ничего не записывается. Потом спросим всех ${n}, состоялась ли она.`,
                                  `Nothing about it is recorded here. Afterwards we’ll ask all ${n === 2 ? 'two' : n === 3 ? 'three' : n === 4 ? 'four' : n} of you whether it happened.`,
                                  `Aquí no se registra nada. Después os preguntaremos a los ${n} si ocurrió.`),
  openRoute: () => T('Открыть маршрут', 'Open the route', 'Abrir la ruta'),
  startsNow: () => T('Начинается сейчас', 'Starts now', 'Empieza ahora'),
  happeningNow: () => T('Идёт сейчас', 'Happening now', 'En curso'),
  tellLateTitle2: () => T('Сказать, что опаздываешь?', 'Tell them you’re running late?', '¿Avisar de que llegas tarde?'),
  tellLateNote2: (who: string) => T(`${who} увидят это сразу. Ничего не отменяется, и это не считается неявкой.`,
                                    `${who} see it straight away. Nothing is cancelled and it is not counted as a no-show.`,
                                    `${who} lo ven al instante. No se cancela nada y no cuenta como no presentarse.`),
  cantMakeTitle2: () => T('Сказать, что не придёшь?', 'Tell them you can’t come?', '¿Avisar de que no puedes ir?'),
  cantMakeNote2: (who: string) => T(`${who} увидят это сразу. Для них встреча в силе — это ничего не отменяет.`,
                                    `${who} see it straight away. The meetup stays on for them — this does not cancel anything.`,
                                    `${who} lo ven al instante. Para ellos la quedada sigue — esto no cancela nada.`),
  stCantTold: () => T('Не придёт · группа знает', 'Can’t make it · told them', 'No puede ir · avisó'),
  stCantJustNow: () => T('Не придёт · только что', 'Can’t make it · just now', 'No puede ir · ahora mismo'),
  // ---- Онлайн-группа: день звонка и после (борд «GR · Online», GRO.45–50) -------------------
  /** «Zoom · your link» / «Zoom · Mateo’s link». Ссылку в группе ставит только организатор. */
  linkWhose: (svc: string, owner: string, mine: boolean) =>
    `${svc || T('Звонок', 'Video call', 'Videollamada')} · ${mine ? T('твоя ссылка', 'your link', 'tu enlace')
      : T(`ссылка ${owner}`, `${owner}’s link`, `enlace de ${owner}`)}`,
  linkLeaves: (svc: string) => svc
    ? T(`Откроется в ${svc} · уйдёшь из Kleal`, `Opens in ${svc} · leaves Kleal`, `Se abre en ${svc} · sales de Kleal`)
    : T('Откроется вне Kleal', 'Opens outside Kleal', 'Se abre fuera de Kleal'),
  openLink2: () => T('Открыть ссылку', 'Open link', 'Abrir enlace'),
  /** GRO.47/48: после звонка карточка говорит, где он был, — «Video call · Zoom». */
  callPast: (svc: string) => `${T('Звонок', 'Video call', 'Videollamada')}${svc ? ' · ' + svc : ''}`,
  lateHintCall: (owner: string, mine: boolean, svc: string, who: string, open: boolean) => {
    const whose = mine ? T('Твоя ссылка', 'Your', 'Tu enlace') : T(`Ссылка ${owner}`, `${owner}’s`, `El enlace de ${owner}`);
    const s = svc ? ` ${svc}` : '';
    return open
      ? T(`${whose}${svc ? ' на' + s : ''} уже открыта. Если опоздаешь, скажи ${who} — они начнут без тебя, а ты подключишься, когда сможешь.`,
          `${whose}${s} link is open now. If you’ll be late, tell ${who} — they start without you and you join when you can.`,
          `${whose}${s} ya está abierto. Si llegas tarde, avisa a ${who} — empiezan sin ti y te unes cuando puedas.`)
      : T(`${whose}${svc ? ' на' + s : ''} откроется за 10 минут до звонка. Если опоздаешь, скажи ${who} — они начнут без тебя.`,
          `${whose}${s} link opens 10 minutes before the call. If you’ll be late, tell ${who} — they start without you.`,
          `${whose}${s} se abre 10 minutos antes de la llamada. Si llegas tarde, avisa a ${who} — empiezan sin ti.`);
  },
  imLateCall: () => T('Я опоздаю', 'I’ll be late', 'Llegaré tarde'),
  tellLateTitleCall: () => T('Сказать, что опоздаешь?', 'Tell them you’ll be late?', '¿Avisar de que llegarás tarde?'),
  lateToldNoteCall: (who: string) => T(`${who} уже видят это. Они начнут без тебя — ничего не отменяется, и это не считается неявкой.`,
                                       `${who} see it now. They start without you — nothing is cancelled, and it isn’t counted as a no-show.`,
                                       `${who} ya lo ven. Empiezan sin ti — no se cancela nada y no cuenta como no presentarse.`),
  nowTitleCall: () => T('Звонок сейчас', 'Your call is now', 'Tu llamada es ahora'),
  nowNoteCall: (who: string) => T(`Уже начинается. Если не сможешь подключиться, скажи ${who} — для них звонок в силе.`,
                                  `It’s starting now. If you can’t join, tell ${who} — the call stays on for them.`,
                                  `Ya empieza. Si no puedes unirte, avisa a ${who} — para ellos la llamada sigue.`),
  cantToldTitleCall: () => T('Ты сказал(а), что не подключишься', 'You told them you can’t join', 'Les dijiste que no puedes unirte'),
  cantToldNoteCall: (who: string) => T(`${who} уже видят это. Для них звонок в силе — ты ничего не отменил(а).`,
                                       `${who} see it now. The call is still on for them — you didn’t cancel anything.`,
                                       `${who} ya lo ven. Para ellos la llamada sigue — no cancelaste nada.`),
  cantComeTitleCall: (who: string) => T(`${who} не подключится`, `${who} can’t join`, `${who} no puede unirse`),
  cantComeNoteCall: (rest: string) => T(`Только что сказал(а) группе. Для тебя и ${rest} звонок в силе — ничего не отменено и не на паузе.`,
                                        `They just told the group. The call is still on for you and ${rest} — nothing is cancelled or put on hold.`,
                                        `Acaba de avisar al grupo. Para ti y ${rest} la llamada sigue — nada se cancela ni se pausa.`),
  kleaBlindCall: (svc: string) => svc
    ? T(`Звонок идёт в ${svc}`, `The call is in ${svc}`, `La llamada es en ${svc}`)
    : T('Kleal не видит звонок', 'Kleal can’t see the call', 'Kleal no ve la llamada'),
  kleaBlindNoteCall: (n: number) => T(`Kleal не видит звонок, поэтому здесь о нём ничего не записывается. Потом спросим всех ${n}, состоялся ли он.`,
                                      `Kleal can’t see the call, so nothing about it is recorded here. Afterwards we’ll ask all ${n === 2 ? 'two' : n === 3 ? 'three' : n === 4 ? 'four' : n} of you whether it happened.`,
                                      `Kleal no ve la llamada, así que aquí no se registra nada. Después os preguntaremos a los ${n} si ocurrió.`),
  cantMakeTitleCall: () => T('Сказать, что не подключишься?', 'Tell them you can’t join?', '¿Avisar de que no puedes unirte?'),
  cantMakeNoteCall: (who: string) => T(`${who} увидят это сразу. Для них звонок в силе — это ничего не отменяет.`,
                                       `${who} see it straight away. The call stays on for them — this does not cancel anything.`,
                                       `${who} lo ven al instante. Para ellos la llamada sigue — esto no cancela nada.`),
  didCallHappen: () => T('Звонок состоялся?', 'Did the call happen?', '¿Hubo llamada?'),
  didCallNote: (svc: string, who: string) => T(`Kleal не видит, что происходит в ${svc || 'звонке'}, поэтому спрашиваем. ${who} получат тот же вопрос — ничего не сохраняется, пока не ответят все.`,
                                                `Kleal can’t see inside ${svc || 'the call'}, so we ask. ${who} get the same question — nothing is saved until everyone answers.`,
                                                `Kleal no ve dentro de ${svc || 'la llamada'}, así que preguntamos. ${who} reciben la misma pregunta — no se guarda nada hasta que respondan todos.`),
  yesTalked: () => T('Да, поговорили', 'Yes, we talked', 'Sí, hablamos'),
  iDidntJoin: () => T('Я не подключился(ась)', 'I didn’t join', 'No me uní'),
  /** GRH.47: у гибрида два входа — «не пришёл и не подключился». */
  iDidntComeOrJoin: () => T('Я не пришёл(ла) и не подключился(ась)', 'I didn’t come or join', 'No fui ni me uní'),
  /** GRO.48a: причины онлайн-звонка — коды те же, что у общего попапа (PostCallPrompt). */
  reasonsCall: () => [
    { code: 'nobody_joined', label: T('Никто не подключился', 'Nobody joined', 'No se unió nadie') },
    { code: 'couldnt_make', label: T('Я не смог(ла) подключиться', 'I couldn’t make it', 'No pude unirme') },
    { code: 'others_didnt_join', label: T('Другие не подключились', 'Others didn’t join', 'Los demás no se unieron') },
    { code: 'link_failed', label: T('Ссылка не работала', 'The link didn’t work', 'El enlace no funcionó') },
    { code: 'other', label: T('Другое', 'Something else', 'Otra cosa') },
  ],
  /** GR.47–50: «Did you meet?». */
  didYouMeet: () => T('Встреча состоялась?', 'Did you meet?', '¿Os visteis?'),
  didYouMeetNote: (who: string) => T(`${who} получат тот же вопрос. Итог сохраним, когда ответят все.`,
                                     `${who} get the same question. We only save the result once everyone answers.`,
                                     `${who} reciben la misma pregunta. Guardamos el resultado cuando respondan todos.`),
  othersAnsweredNote: (who: string) => T(`${who} уже ответили. Итог сохранится, когда ответишь и ты.`,
                                         `${who} have answered. The result is saved once you answer too.`,
                                         `${who} ya han respondido. El resultado se guarda cuando respondas tú también.`),
  yesMet: () => T('Да, встретились', 'Yes, we met', 'Sí, nos vimos'),
  didntHappen: () => T('Не состоялась', 'It didn’t happen', 'No ocurrió'),
  iDidntGo: () => T('Я не пошёл(ла)', 'I didn’t go', 'No fui'),
  meterAnswered: () => T('Ответили', 'Answered', 'Respondieron'),
  replyBy: (when: string) => T(`Ответить до ${when}`, `Reply by ${when}`, `Responde antes de ${when}`),
  savedTitle: () => T('Ответ сохранён', 'Your answer is saved', 'Tu respuesta está guardada'),
  savedNote: () => T('Итог сохранится, когда ответят все. Твой ответ и причину никто не увидит.',
                     'The result is saved once everyone answers. Nobody sees your answer or your reason.',
                     'El resultado se guarda cuando respondan todos. Nadie ve tu respuesta ni tu motivo.'),
  stHasntAnswered: () => T('Пока не ответил(а)', 'Hasn’t answered', 'No ha respondido'),
  stAnswered: () => T('Ответил(а)', 'Answered', 'Respondió'),
  howWas: () => T('Как прошло?', 'How was it?', '¿Qué tal fue?'),
  howWasLead: () => T('Необязательно — это помогает Kleal подбирать лучше', 'Optional — it helps Kleal find better matches',
                      'Opcional — ayuda a Kleal a encontrar mejores coincidencias'),
  howWasNote: () => T('Твой ответ видит только Kleal. Если что-то пошло не так, лучше пожалуйся.',
                      'Only Kleal sees your answer. If something went wrong, report it instead.',
                      'Solo Kleal ve tu respuesta. Si algo fue mal, repórtalo.'),
  rateGreat: () => T('😄 Отлично', '😄 Great', '😄 Genial'),
  rateFine: () => T('🙂 Нормально', '🙂 Fine', '🙂 Bien'),
  rateBad: () => T('😕 Не очень', '😕 Not great', '😕 Regular'),
  sendAnswer: () => T('Отправить', 'Send', 'Enviar'),
  reportProblem: () => T('Сообщить о проблеме', 'Report a problem', 'Reportar un problema'),
  whatHappened: () => T('Что случилось?', 'What happened?', '¿Qué pasó?'),
  whatHappenedLead: () => T('Твой ответ остальным не показывают', 'Your answer is not shown to the others',
                            'Tu respuesta no se muestra a los demás'),
  whatHappenedNote: () => T('Нужно, чтобы планы оставались честными.', 'Used to keep plans honest.', 'Sirve para que los planes sean honestos.'),
  skip: () => T('Пропустить', 'Skip', 'Omitir'),
  /** Коды — те же, что у общего напоминателя (groupReasons в PostCallPrompt): одна причина — один код. */
  reasons: () => [
    { code: 'nobody_came', label: T('Никто не пришёл', 'Nobody came', 'No vino nadie') },
    { code: 'couldnt_make', label: T('Я не смог(ла) прийти', 'I couldn’t make it', 'No pude ir') },
    { code: 'others_didnt_come', label: T('Другие не пришли', 'Others didn’t come', 'Los demás no vinieron') },
    { code: 'place_closed', label: T('Место было закрыто', 'The place was closed', 'El sitio estaba cerrado') },
    { code: 'other', label: T('Другое', 'Something else', 'Otra cosa') },
  ],
  /** GR.40 / GR.40c: план на паузе. */
  belowNote2: () => T('Групповому плану нужны трое. План на паузе, а не отменён — выбери, что дальше.',
                      'A group plan needs three. The plan is on hold, not cancelled — choose what happens next.',
                      'Un plan de grupo necesita tres. El plan está en pausa, no cancelado — elige qué pasa ahora.'),
  onHoldTitle: () => T('План на паузе', 'The plan is on hold', 'El plan está en pausa'),
  // ---- GR.40a / 40d / 40b / 40e / 40f: конец паузы -----------------------------------------
  holdAskTitle: () => T('Прошло 12 часов', 'Twelve hours passed', 'Pasaron doce horas'),
  holdAskNote: (who: string) => who
    ? T(`${who} не выбрал(а). Перейдите в один на один, если согласны оба — это займёт один из ваших планов 1:1, — или отпустите план.`,
        `${who} didn’t choose. Switch to one-on-one if you both agree — it uses one of your 1:1 plans — or let the plan go.`,
        `${who} no eligió. Pasad a uno a uno si estáis de acuerdo los dos —usa uno de vuestros planes 1:1— o dejad el plan.`)
    : T('Ты не выбрал(а). Перейдите в один на один, если согласны оба — это займёт один из ваших планов 1:1, — или отпустите план.',
        'You didn’t choose. Switch to one-on-one if you both agree — it uses one of your 1:1 plans — or let the plan go.',
        'No elegiste. Pasad a uno a uno si estáis de acuerdo los dos —usa uno de vuestros planes 1:1— o dejad el plan.'),
  holdWaitNote: (who: string) => T(`Ты за один на один. Ждём ответа ${who} — если он не согласится, план закроется.`,
    `You want to switch to one-on-one. Waiting for ${who} — if they don’t agree, the plan closes.`,
    `Quieres pasar a uno a uno. Esperamos a ${who}; si no acepta, el plan se cierra.`),
  holdClosedTitle: () => T('План отменён', 'The plan is cancelled', 'El plan está cancelado'),
  holdClosedNote: () => T('Группа осталась вдвоём, и никто не согласился на один на один, поэтому план закрыт. Никто ни в чём не виноват. Твой интент снова ищет людей.',
    'The group stayed at two and nobody agreed to a one-on-one, so the plan is closed. Nothing is held against anyone. Your intent goes back to searching.',
    'El grupo se quedó en dos y nadie aceptó el uno a uno, así que el plan se cerró. Nadie tiene la culpa. Tu intención vuelve a buscar.'),
  holdLetGoNote: (who: string) => T(`${who} отпустил(а) план, поэтому он закрыт. Никто ни в чём не виноват. Твой интент снова ищет людей.`,
    `${who} let the plan go, so it’s closed. Nothing is held against anyone. Your intent goes back to searching.`,
    `${who} dejó el plan, así que se cerró. Nadie tiene la culpa. Tu intención vuelve a buscar.`),
  letPlanGo: () => T('Отпустить план', 'Let the plan go', 'Dejar el plan'),
  stHasntAnsweredYet: () => T('Ещё не ответил(а)', 'Hasn’t answered yet', 'Aún no respondió'),
  stYourAnswerNeeded: () => T('Нужен твой ответ', 'Your answer needed', 'Falta tu respuesta'),
  stWantsOneOnOne: () => T('За один на один', 'Wants one-on-one', 'Quiere uno a uno'),
  stLetItGo: () => T('Отпустил(а) план', 'Let the plan go', 'Dejó el plan'),
  stDidntAnswer: () => T('Не ответил(а)', 'Didn’t answer', 'No respondió'),
  stLeftPlan: () => T('Вышел(а) из плана', 'Left the plan', 'Dejó el plan'),
  findThirdTitle: () => T('Найти третьего?', 'Find a third person?', '¿Buscar a una tercera persona?'),
  findThirdLead: () => T('Открыто, пока план на паузе', 'Open while the plan is on hold', 'Abierto mientras el plan está en pausa'),
  findThirdNote: (left: string, other: string) => T(
    `Kleal предложит место${left ? ` ${left}` : ''} людям рядом, которые хотят того же. Они присоединятся к плану как есть — то же время и место. Если никто не придёт вовремя, Kleal спросит тебя${other ? ` и ${other}` : ''}.`,
    `Kleal offers ${left ? `${left}’s` : 'the'} spot to people nearby who want the same thing. They join the plan as it is — same time and place. If nobody joins in time, Kleal asks you${other ? ` and ${other}` : ''}.`,
    `Kleal ofrece el sitio${left ? ` de ${left}` : ''} a gente cercana que quiere lo mismo. Se unen al plan tal cual — misma hora y lugar. Si nadie llega a tiempo, Kleal os pregunta a ti${other ? ` y a ${other}` : ''}.`),
  openSpot: () => T('Открыть место', 'Open the spot', 'Abrir el sitio'),
  // Строки чата о конце паузы (коды сервера hold_*).
  sysHoldAsk: () => T('Прошло 12 часов — один на один или отпустить план', 'Twelve hours passed — switch to one-on-one or let the plan go', 'Pasaron doce horas — uno a uno o dejar el plan'),
  sysHoldOneOnOne: (who: string, mine: boolean) => mine ? T('Ты за один на один', 'You want to switch to one-on-one', 'Quieres pasar a uno a uno')
    : T(`${who} за один на один`, `${who} wants to switch to one-on-one`, `${who} quiere pasar a uno a uno`),
  sysHoldLetGo: (who: string, mine: boolean) => mine ? T('Ты отпустил(а) план', 'You let the plan go', 'Dejaste el plan')
    : T(`${who} отпустил(а) план`, `${who} let the plan go`, `${who} dejó el plan`),
  sysHoldExpired: () => T('План отменён — никто не согласился на один на один', 'The plan is cancelled — nobody agreed to a one-on-one', 'El plan se canceló — nadie aceptó el uno a uno'),
  onHoldNote: (owner: string) => T(`Вас осталось двое. ${owner} может позвать кого-то, перейти в один на один или отпустить план — пока ничего не отменено.`,
                                   `You’re down to two. ${owner} can add someone, go one-on-one or let it go — nothing is cancelled meanwhile.`,
                                   `Os quedáis dos. ${owner} puede añadir a alguien, pasar a uno a uno o dejarlo — mientras tanto no se cancela nada.`),
  meterOnHold: () => T('На паузе', 'On hold', 'En pausa'),
  /** GR.41: выйти из плана — подтверждение. */
  leaveLead: () => T('Это нельзя отменить', 'You can’t undo this', 'No se puede deshacer'),
  leaveAskTitle: (title: string) => T(`Выйти из «${title}»?`, `Leave ${title}?`, `¿Salir de ${title}?`),
  leaveNote: (who: string, owner: string, drops: boolean) => drops
    ? T(`${who} узнают, что ты вышел(ла). В плане останутся двое, и ${owner} решит, что с ним делать.`,
        `${who} are told you left. That drops the plan to two, and ${owner} will have to choose what happens to it.`,
        `A ${who} se les avisa de que saliste. El plan se queda en dos, y ${owner} tendrá que decidir qué pasa.`)
    : T(`${who} узнают, что ты вышел(ла). План продолжится без тебя.`, `${who} are told you left. The plan carries on without you.`,
        `A ${who} se les avisa de que saliste. El plan sigue sin ti.`),
  stayBtn: () => T('Остаться', 'Stay', 'Quedarme'),

  // ---- Листы голосования по борду (GR.35a–38a) ----------------------------------------------
  askSheetTitle: () => T('Попросить изменить план', 'Ask to change the plan', 'Pedir cambiar el plan'),
  voteSheetTitle2: (kind: string) => kind === 'cancel'
    ? T('Отменить план?', 'Cancel the plan?', '¿Cancelar el plan?') : T('Изменить план?', 'Change the plan?', '¿Cambiar el plan?'),
  hoursLeftLead: (h: number) => T(`Осталось ${h} ч`, `${h} hour${h === 1 ? '' : 's'} left`, `Quedan ${h} h`),
  suggestsInstead: (who: string, what: string, owner: string) =>
    T(`${who} предлагает вместо этого ${what}. Твой голос — совет: решает ${owner}.`,
      `${who} suggests ${what} instead. Your vote is advice — ${owner} makes the final call.`,
      `${who} propone ${what} en su lugar. Tu voto es un consejo — decide ${owner}.`),
  suggestsCancel: (who: string, owner: string) =>
    T(`${who} предлагает отменить встречу. Твой голос — совет: решает ${owner}.`,
      `${who} suggests cancelling it. Your vote is advice — ${owner} makes the final call.`,
      `${who} propone cancelarla. Tu voto es un consejo — decide ${owner}.`),
  tally2: (yes: number, no: number) => T(`${yes} за · ${no} против`, `${yes} for · ${no} against`, `${yes} a favor · ${no} en contra`),
  keptLead: (when: string) => T(`${when} остаётся`, `${when} stays`, `${when} se mantiene`),
  keptSheetNote: (yes: number, no: number) =>
    T(`Группа проголосовала: ${yes} за · ${no} против. На Kleal голосование — совет, решает организатор.`,
      `The group voted ${yes} for · ${no} against. On Kleal the vote is advice — the organiser decides.`,
      `El grupo votó ${yes} a favor · ${no} en contra. En Kleal el voto es un consejo — decide el organizador.`),
  changedByVote: (owner: string) => T(`${owner} изменил(а) план`, `${owner} changed the plan`, `${owner} cambió el plan`),

  sendChange: () => T('Отправить изменение', 'Send the change', 'Enviar el cambio'),
  placeNoteSuggest: (who: string) => T(`${who} видят только район, пока все не подтвердят.`,
                                       `${who} see only the district until everyone confirms.`,
                                       `${who} solo ven el barrio hasta que todos confirmen.`),
  placeNoteUpdate: (who: string) => T(`${who} получат новое место вместе с изменением.`,
                                      `${who} get the new spot together with the update.`,
                                      `${who} reciben el nuevo sitio junto con el cambio.`),
  lockedLine: () => T('Заперто · больше ничего не меняется', 'Locked · nothing can change now', 'Bloqueado · ya no cambia nada'),
  /** GR.39 — лист у организатора: кто-то вышел, людей стало двое. */
  leftSheetTitle: (who: string) => T(`${who} вышел(ла) из плана`, `${who} left the plan`, `${who} dejó el plan`),
  downToTwo: () => T('Вас осталось двое', 'You’re down to two', 'Os quedáis dos'),
  downToTwoNote: () => T('Групповому плану нужны трое. Ничего не отменено — что дальше, решаешь ты.',
                         'A group plan needs three. Nothing is cancelled — you choose what happens next.',
                         'Un plan de grupo necesita tres. No se cancela nada — tú eliges qué pasa.'),
  seeOptions: () => T('Посмотреть варианты', 'See your options', 'Ver opciones'),

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
  // Борд: «Left · 20 minutes ago», но «Left · 12h ago» — часы коротко (GR.40a).
  if (h < 24) return T(`${h} ч назад`, `${h}h ago`, `Hace ${h} h`);
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

/** Сколько окна [from, to] уже прошло, 0..1; окно неизвестно — undefined (полоса-заглушка). */
export function elapsed(from: number, to: number, now: number): number | undefined {
  if (!from || !to || to <= from) return undefined;
  return Math.max(0, Math.min(1, (now - from) / (to - from)));
}
