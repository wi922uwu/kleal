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
  mode?: 'offline' | 'online' | string;
  link?: string;
  needs_link?: boolean;
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
      ? T('Звонок · ссылка сохранена', 'Video call · link saved')
      : T('Звонок · ссылки пока нет', 'Video call · no link yet');
  }
  return String(p.place || '').trim() || T('Место не указано', 'No place yet');
}

/** Часы до момента, словами. Для «closes in 4h» (GR.36) и «It’s your call» без обратного отсчёта. */
export function hoursLeft(at?: number): number {
  if (!at) return 0;
  return Math.max(0, Math.ceil((Number(at) * 1000 - Date.now()) / 3600000));
}

export const GPLAN = {
  // ---- GR.25 / GRO.25: создание -----------------------------------------
  createTitle: (online: boolean) =>
    online ? T('Назначь время', 'Set the time') : T('Назначь время и место', 'Set the time and place'),
  createNote: () =>
    T(
      'Каждый сможет подтвердить или предложить своё, прежде чем это станет планом.',
      'Everyone gets to confirm or suggest a change before this becomes a plan.'
    ),
  placePh: () => T('Место — район и заведение', 'Place — area and venue'),
  send: () => T('Отправить группе', 'Send to the group'),
  back: () => T('Назад', 'Back'),
  /** Сервер отказывает по времени: план внутри двухчасового окна подтвердить некому. */
  tooLate: () =>
    T(
      'До встречи меньше двух часов — такой план уже никто не успеет подтвердить. Выбери время подальше.',
      'That starts in under two hours — nobody could confirm it in time. Pick something later.'
    ),
  needThree: (n: number) =>
    T(`Для плана нужно трое. Не хватает ${n}.`, `A plan needs three. ${n} more to go.`),
  planExists: () => T('План у этой группы уже есть.', 'This group already has a plan.'),
  createFailed: () => T('План не ушёл. Попробуй ещё раз.', 'The plan didn’t go out. Try again.'),

  // ---- GR.26 / GR.28 / GR.29: согласование ------------------------------
  waitingTitle: () => T('Ждём всех', 'Waiting for everyone'),
  /** GR.26 дословно, но с живым числом: «all three» на борде — потому что там их трое. */
  waitingNote: (n: number) =>
    T(
      `План начнётся, когда подтвердят все ${n}. Вместо этого можно предложить своё.`,
      `The plan starts when all ${n} confirm. Anyone can suggest a change instead.`
    ),
  /** GR.28: кто-то предложил своё, и круг пошёл заново. */
  counteredTitle: (who: string) => T(`${who} предлагает другое`, `${who} suggested a change`),
  counteredNote: (when: string) =>
    T(
      `Теперь предлагают ${when}. Подтверждают заново все.`,
      `Now it’s ${when} instead. Everyone confirms again.`
    ),
  /** GR.29: последний раунд — сказать об этом надо ДО того, как человек потратит его впустую. */
  lastRoundNote: (owner: string) =>
    T(
      `Это последний раунд. После него ${owner} закрепит план, и меняться он перестанет.`,
      `This is the last round. After it ${owner} fixes the plan and it stops changing.`
    ),
  round: (n: number, max: number) => T(`Раунд ${n} из ${max}`, `Round ${n} of ${max}`),
  lastRound: () =>
    T('Последний раунд · дальше план закрепляет организатор',
      'Last round · after this the organiser fixes the plan'),
  confirm: () => T('Подтвердить', 'Confirm'),
  suggest: () => T('Предложить другое', 'Suggest a change'),
  /** Подтвердил и ждёшь остальных — кнопки «Confirm» на кадре у тебя уже нет. */
  youConfirmed: (left: number) =>
    left > 0
      ? T(`Ты подтвердил(а). Ждём ещё ${left}.`, `You’ve confirmed. Waiting for ${left} more.`)
      : T('Ты подтвердил(а).', 'You’ve confirmed.'),

  // ---- GR.27: своё предложение ------------------------------------------
  suggestTitle: () => T('Предложи своё', 'Suggest a change'),
  suggestNote: (left: number) =>
    T(
      `Твоё предложение заменит нынешнее, и подтверждать будут заново все. После него останется раундов: ${left}.`,
      `Your suggestion replaces the current one and everyone confirms again. ${left} round${left === 1 ? '' : 's'} left after this.`
    ),
  suggestSend: () => T('Отправить предложение', 'Send the suggestion'),
  cancel: () => T('Отмена', 'Cancel'),
  roundsUsedUp: () =>
    T('Раунды кончились — дальше решает организатор.', 'Rounds are used up — the organiser decides now.'),

  // ---- GR.30: организатор закрепляет ------------------------------------
  fixTitle: (yes: number, no: number) =>
    T(
      `Подтвердили ${yes}, не подтвердили ${no}`,
      `${yes} confirmed, ${no} didn’t`
    ),
  fixNote: (when: string, who: string) =>
    T(
      `Раунды кончились. Можно закрепить ${when} как план — ${who} спросят, остаётся он или выходит.`,
      `Rounds are used up. You can fix ${when} as the plan — ${who} will be asked to stay or leave.`
    ),
  fix: () => T('Закрепить план', 'Fix the plan'),
  moreTime: () => T('Дать ещё время', 'Give it more time'),
  fixNeedThree: () =>
    T('Согласных меньше трёх — закреплять нечего.', 'Fewer than three agreed — there is no plan to fix.'),

  // ---- GR.31: остаться или выйти ----------------------------------------
  fixedTitle: (who: string) => T(`${who} закрепил(а) план`, `${who} fixed the plan`),
  fixedNote: (when: string, where: string) =>
    T(
      `${when}, ${where}. Ты этот вариант не подтверждал(а) — можешь всё равно прийти, а можешь выйти из плана.`,
      `${when} at ${where}. You didn’t confirm this one — you can still come, or leave the plan.`
    ),
  stay: () => T('Остаться в плане', 'Stay in the plan'),
  leavePlan: () => T('Выйти из плана', 'Leave the plan'),

  // ---- GR.34: план утверждён --------------------------------------------
  setTitle: () => T('План назначен', 'The plan is set'),
  setNote: () =>
    T(
      'Удалить из группы больше нельзя. Выйти можно, и любой может попросить группу изменить план.',
      'Nobody can be removed now. Participants can still leave, and anyone can ask the group to change it.'
    ),
  openChat: () => T('Открыть чат группы', 'Open group chat'),
  changeOrCancel: () => T('Изменить или отменить план', 'Change or cancel the plan'),
  locked: () =>
    T('До встречи меньше двух часов — план больше не меняется.',
      'Under two hours to go — the plan doesn’t change any more.'),
  /** GR.40. План НА ПАУЗЕ, а не отменён: решение за организатором, и оно ещё не принято. */
  belowTitle: () => T('Вас осталось двое', 'You’re down to two'),
  belowNote: () => T(
    'Групповому плану нужны трое. Пока ты не решишь, ничего не происходит — план на паузе, а не отменён.',
    'A group plan needs three. Nothing happens until you choose — the plan is on hold, not cancelled.'
  ),
  inviteMore: () => T('Позвать ещё людей', 'Invite more people'),
  cancelPlan: () => T('Отменить план', 'Cancel the plan'),

  cancelled: () => T('План отменён.', 'The plan is cancelled.'),

  // ---- GR.35: попросить группу ------------------------------------------
  askTitle: () => T('Попросить группу изменить план?', 'Ask the group to change this plan?'),
  /**
   * Кто решит в итоге — организатор. Но если организатор ЭТО ТЫ, называть тебя по имени нельзя:
   * «решает ИванГ» человек про себя не читает, он читает про кого-то третьего. Поэтому у каждой
   * строки про совещательность есть вторая версия, от первого лица.
   */
  askNote: (owner: string) =>
    T(
      `У каждого будет 6 часов на ответ. Результат — совет: последнее слово за ${owner}.`,
      `Everyone gets 6 hours to answer. The result is advice — ${owner} makes the final call.`
    ),
  askNoteMine: () =>
    T(
      'У каждого будет 6 часов на ответ. Результат — совет: решать всё равно тебе.',
      'Everyone gets 6 hours to answer. The result is advice — the final call is yours.'
    ),
  askMove: () => T('Предложить перенос', 'Suggest moving it'),
  askCancel: () => T('Предложить отменить', 'Suggest cancelling it'),
  startVote: () => T('Начать голосование', 'Start the vote'),
  notNow: () => T('Не сейчас', 'Not now'),
  voteExists: () => T('Голосование уже идёт.', 'A vote is already open.'),

  // ---- GR.36: голосование идёт ------------------------------------------
  voteOpenTitle: (who: string, kind: string) =>
    kind === 'cancel'
      ? T(`${who} предлагает отменить встречу`, `${who} wants to cancel the plan`)
      : T(`${who} предлагает перенести встречу`, `${who} wants to move the plan`),
  voteOpenNote: (h: number, owner: string) =>
    T(
      `Голосование закроется через ${h} ч. Твой ответ — совет: решает ${owner}.`,
      `The vote closes in ${h}h. Your answer is advice — ${owner} makes the final call.`
    ),
  voteOpenNoteMine: (h: number) =>
    T(
      `Голосование закроется через ${h} ч. Это совет группы — решать тебе.`,
      `The vote closes in ${h}h. It’s the group’s advice — the final call is yours.`
    ),
  voteBadge: (h: number) => T(`Голосование · ${h} ч`, `Vote open · closes in ${h}h`),
  openVote: () => T('Открыть голосование', 'Open the vote'),
  voteSheetTitle: (h: number, kind: string) =>
    kind === 'cancel'
      ? T(`Отменить план? ${h} ч`, `Cancel the plan? ${h}h left`)
      : T(`Изменить план? ${h} ч`, `Change the plan? ${h}h left`),
  voteSheetNote: (who: string, what: string, owner: string) =>
    T(
      `${who} предлагает ${what}. Твой голос — совет: решает ${owner}.`,
      `${who} suggests ${what} instead. Your vote is advice — ${owner} makes the final call.`
    ),
  voteYes: (kind: string) =>
    kind === 'cancel' ? T('Да, отменить', 'Yes, cancel it') : T('Да, изменить', 'Yes, change it'),
  voteNo: () => T('Нет, оставить', 'No, keep it'),
  voted: () => T('Твой голос учтён. Ждём остальных.', 'Your answer is in. Waiting for the others.'),

  // ---- GR.37: организатор решает ----------------------------------------
  closedTitle: () => T('Голосование закрыто', 'The vote is closed'),
  closedNoteOwner: (yes: number, no: number, silent: number) =>
    T(
      `За — ${yes}, против — ${no}, не ответили — ${silent}. Решать тебе.`,
      `${yes} asked to change it, ${no} against, ${silent} didn’t answer. It’s your call.`
    ),
  decide: () => T('Посмотреть числа и решить', 'See the numbers and decide'),
  tally: (yes: number, no: number, silent: number) =>
    T(
      `${yes} за · ${no} против · ${silent} не голосовали`,
      `${yes} for · ${no} against · ${silent} didn’t vote`
    ),
  decideNote: () =>
    T(
      'Голосование закрыто. Решать тебе — группа попросила, ты решаешь.',
      'The vote is closed. It’s your call — the group asked, you decide.'
    ),
  applyChange: () => T('Изменить план', 'Change the plan'),
  applyCancel: () => T('Отменить встречу', 'Cancel the meetup'),
  keepIt: () => T('Оставить как есть', 'Keep it as it is'),

  // ---- GR.38: участнику объявили итог -----------------------------------
  keptTitle: (owner: string) => T(`${owner} оставил(а) план как есть`, `${owner} kept the plan as it is`),
  keptNote: (when: string, yes: number, of: number) =>
    T(
      `${when} остаётся. Перенести просили ${yes} из ${of} — на Kleal решает организатор.`,
      `${when} stays. ${yes} of ${of} asked to move it — on Kleal the organiser decides.`
    ),
  waitingDecision: (owner: string) =>
    T(`Голоса посчитаны. Ждём решения: ${owner}.`, `The votes are counted. Waiting on ${owner} to decide.`),
  gotIt: () => T('Понятно', 'Got it'),

  // ---- GR.32 / GRO.32: организатор правит план --------------------------
  updateTitle: () => T('Изменить время или место', 'Change the time or place'),
  updateNote: (from: string, to: string) =>
    T(
      `Ты переносишь с ${from} на ${to}. Каждый, кто уже согласился, заново примет или выйдет, а открытое приглашение обновится на новое время.`,
      `You’re moving it from ${from} to ${to}. Everyone who already joined has to accept or leave, and the open invite is updated to the new time.`
    ),
  wasLine: (was: string) => T(`было ${was}`, `was ${was}`),
  unchanged: () => T('без изменений', 'unchanged'),
  sendUpdate: () => T('Отправить изменение', 'Send the update'),
  keepTerms: () => T('Оставить как есть', 'Keep current terms'),

  // ---- GR.33 / GRO.33: участнику пришла правка --------------------------
  changedTitle: (who: string) => T(`${who} изменил(а) план`, `${who} changed the plan`),
  changedNote: (from: string, to: string) =>
    T(
      `С ${from} на ${to}. Прими, чтобы остаться в группе, или выйди — группа продолжится в любом случае.`,
      `From ${from} to ${to}. Accept to stay in the group, or leave — the group carries on either way.`
    ),
  accept: () => T('Принять изменение', 'Accept the change'),
  leaveGroup: () => T('Выйти из группы', 'Leave the group'),

  // ---- GRO.25a: онлайн без ссылки ---------------------------------------
  linkTitle: () => T('Добавь ссылку на звонок', 'Add the call link'),
  linkNote: (when: string) =>
    T(
      `${when} согласовано. Пока ссылки нет, группа видит «ссылка будет» — интент завели без неё, и без ссылки подключиться некуда.`,
      `${when} is agreed. The group sees “link coming” until you paste one — the intent had no link, so nobody can join without it.`
    ),
  linkPh: () => T('Вставь ссылку на Zoom, Meet — любую', 'Paste a Zoom, Meet or any link'),
  saveLink: () => T('Сохранить ссылку', 'Save the link'),
  askHost: () => T('Попросить кого-то другого стать хостом', 'Ask the group to host instead'),
  /** Сообщение в чат, которым «попросить хоста» и делается: отдельной сущности у этого нет. */
  askHostMsg: () =>
    T('Нужна ссылка на звонок — может кто-то поднять её у себя?',
      'We need a call link — can someone host it?'),
  badLink: () => T('Это не похоже на ссылку.', 'That doesn’t look like a link.'),
  linkComing: () => T('Ссылка будет', 'Link coming'),
  openLink: () => T('Открыть звонок', 'Open the call'),

  // ---- роли и состояния в составе ---------------------------------------
  roleOrganiser: () => T('Организатор', 'Organiser'),
  stConfirmed: () => T('Подтвердил(а)', 'Confirmed'),
  stOrganiserConfirmed: () => T('Организатор · подтвердил(а)', 'Organiser · confirmed'),
  stSuggested: () => T('Предложил(а) это · подтвердил(а)', 'Suggested this · confirmed'),
  stWaiting: () => T('Пока не ответил(а)', 'Hasn’t answered yet'),
  stYourTurn: () => T('Твой ход', 'Your turn'),
  stDidnt: () => T('Не подтвердил(а)', 'Didn’t confirm'),
  stWillAccept: () => T('Ответит на изменение', 'Will be asked to accept'),
  stChanging: () => T('Организатор · меняет', 'Organiser · changing it'),
  stChanged: () => T('Организатор · изменил(а)', 'Organiser · changed it'),
  stInGroup: () => T('В группе', 'In the group'),
  you: () => T('Ты', 'You'),

  // ---- общие отказы ------------------------------------------------------
  failed: () => T('Не получилось. Попробуй ещё раз.', 'That didn’t go through. Try again.'),
  notOrganiser: () => T('Это может только организатор.', 'Only the organiser can do that.'),
  gone: () => T('Этого плана больше нет.', 'This plan is gone.'),
};

/**
 * Подпись под именем в составе — та самая колонка, где на борде стоит «Organiser · confirmed»,
 * «Hasn’t answered yet», «Your turn». Собрана в одном месте, потому что состояний семь, и
 * разложенные по экрану они разъезжаются: на GR.27 «Will confirm again», на GR.32 «Will be asked
 * to accept» — это одна и та же мысль в разных фазах, и путать их нельзя.
 */
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

  if (confirmed) {
    if (p.update && eq(name, p.update.by)) return { text: GPLAN.stChanged(), done: true };
    if (eq(name, opts.proposer) && !isOwner) return { text: GPLAN.stSuggested(), done: true };
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
