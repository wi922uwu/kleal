/**
 * Групповой набор — выдача, приглашения, кап. Кадры GR.14–GR.17 борда «Groups · Offline».
 *
 * UX-каркас: копия и правила здесь, вид — в app/results.tsx (групповой режим той же выдачи).
 * Английские строки взяты с кадров ДОСЛОВНО, русские написаны, а не переведены машинно.
 *
 * Правила набора — они же серверные (см. GI_* в services/matching/app.py, теперь по борду):
 *  — приглашения уходят ПО ОДНОМУ, каждое через шит подтверждения (GR.16); батч-кнопки нет;
 *  — открытых приглашений не больше ТРЁХ (GR.15): дальше INVITE_CAP, выход — отменить одно;
 *  — «first 5 who accept are in»: места не резервируются, состав решает принятие;
 *  — список приглашённых видит ТОЛЬКО организатор (GR.17); приглашённому обещано «who is
 *    already in», а не «кого ещё позвали» (GR.16).
 */
import { T } from './i18n';
import type { Msg } from './chat';

/**
 * Групповой ли это интент. Мастер шлёт плоские format/groupSize; сервер в ответе может отдать их
 * же или §4.3-блок mode_format — читаем все три места, чтобы режим не зависел от того, чей объект
 * долетел до выдачи.
 */
export function isGroupIntent(intent: any): boolean {
  if (!intent || typeof intent !== 'object') return false;
  const flat = String(intent.format || '').toLowerCase();
  const block = String(intent.mode_format?.format || '').toLowerCase();
  return flat === 'group' || block === 'group' || Number(intent.groupSize || 0) >= 3;
}

/** Заголовок группы для gintent-create: подпись человека, а не ключи поиска. */
export function groupTitleOf(intent: any, query = ''): string {
  const t = String(intent?.title || '').trim();
  if (t) return t;
  const q = String(query || '').trim();
  if (q) return q.slice(0, 120);
  const topics = Array.isArray(intent?.topics) ? intent.topics.filter(Boolean) : [];
  return topics.join(', ').slice(0, 120) || 'Meetup';
}

export const GROUP = {
  /** Шапка выдачи в групповом режиме — GR.14, дословно. */
  header: () => T('Кто подходит твоей группе', 'Who fits your group'),
  /** После первого отправленного приглашения тот же список становится GR.17. */
  invitesSent: () => T('Приглашения отправлены', 'Invites sent'),

  /**
   * Строка регламента под шапкой — GR.14. Числа живые: минимум и потолок приходят с группы,
   * кап приглашений — тоже, чтобы строка не разошлась с сервером при смене тарифа.
   */
  regime: (min: number, max: number, cap: number) =>
    T(
      `Малая группа · ${min}–${max} человек · не больше ${cap} приглашений разом · кто первым согласится, тот в группе`,
      `Small group · ${min}–${max} people · ${cap} open invites at a time on Free · first ${max} who accept are in`
    ),

  /**
   * Счётчик набора — GR.17: «2 of 5 joined · 3 invites still open · a plan needs 3».
   * Присоединившиеся считаются ВМЕСТЕ с организатором — так же, как считает сервер.
   */
  counter: (joined: number, max: number, open: number, min: number) =>
    T(
      `В группе ${joined} из ${max} · открытых приглашений: ${open} · для плана нужно ${min}`,
      `${joined} of ${max} joined · ${open} invite${open === 1 ? '' : 's'} still open · a plan needs ${min}`
    ),

  /** Кнопка и состояния строки кандидата — GR.14/GR.17. */
  joined: () => T('В группе', 'Joined'),

  /** Шит подтверждения — GR.16, дословно с кадра. */
  askTitle: (name: string) => T(`Пригласить ${name} в группу?`, `Invite ${name} to the group?`),
  askBody: (name: string) =>
    T(
      `${name} увидит интент и кто уже внутри. Согласие сразу ведёт в общий чат группы — личной переписки с тобой здесь нет.`,
      'She sees the intent and who is already in. If she accepts she joins the shared group chat straight away — there is no private chat with you.'
    ),
  askSend: () => T('Отправить приглашение', 'Send the invite'),
  askNot: () => T('Пока нет', 'Not yet'),

  /** Шит капа — GR.15, дословно. Plus в продукте нет — его строка честно выключена (правило каркаса). */
  capTitle: () => T('Три приглашения уже в воздухе', 'Three invites are already open'),
  capBody: () =>
    T(
      'Три приглашения ждут ответа. Kleal держит планку в три, чтобы никому не прилетал веер заявок. Отмени одно или дождись ответа — Plus поднимет планку.',
      'You have 3 invites still waiting for an answer. Kleal holds them at three so nobody gets a fan-out of requests. Cancel one, or wait — Plus raises it.'
    ),

  /** Отказы сервера — по имени, как он их называет. */
  full: () => T('Группа уже собралась — мест нет.', 'The group is already full.'),
  sendFailed: () => T('Приглашение не ушло. Попробуй ещё раз.', 'The invite didn’t go out. Try again.'),
};

/**
 * Комната — общий чат группы. Кадры GR.18 (двое, набор не закончен) и GR.21 (трое, план доступен).
 *
 * Экран ОДИН на оба состояния: на борде это один и тот же чат с другой подписью в шапке и другой
 * кнопкой внизу. Разводить их по маршрутам значило бы, что человек, глядя на свою же группу,
 * оказывается то тут, то там — та же ошибка, которой избегает один экран плана в 1:1.
 */
export const ROOM = {
  /** Выход не удался. Раньше экран уходил назад в любом случае — и неудача выглядела как удача. */
  leaveFailed: () => T('Не удалось выйти. Попробуй ещё раз.', 'Could not leave. Try again.'),
  /** Подзаголовок шапки — GR.18/GR.21 дословно. При полном составе он же и зовёт делать план. */
  headCount: (n: number, min: number) =>
    n >= min
      ? T(`${n}/${min} в группе — можно делать план!`, `${n}/${min} in the Group — Make the plan now!`)
      : T(`${n}/${min} в группе`, `${n}/${min} in the Group`),

  /**
   * Строка состава под шапкой — GR.18: «Jane and you», ниже «2 of 3 · need 1 more».
   * Имена, а не число: человек узнаёт свою группу по тем, кто в ней, а не по счётчику.
   */
  who: (names: string[]) => {
    const you = T('ты', 'you');
    const list = [...names];
    if (!list.length) return you;
    if (list.length === 1) return T(`${list[0]} и ${you}`, `${list[0]} and ${you}`);
    const last = list.pop() as string;
    return T(`${list.join(', ')}, ${last} и ${you}`, `${list.join(', ')}, ${last} and ${you}`);
  },
  need: (n: number, min: number) =>
    n >= min
      ? T(`${n} из ${min} · состав собран`, `${n} of ${min} · ready`)
      : T(`${n} из ${min} · нужен(ы) ещё ${min - n}`, `${n} of ${min} · need ${min - n} more`),

  /** Системные строки ленты — GR.18/GR.21. Их пишет сервер по-английски; здесь перевод для показа. */
  sysJoined: (who: string) => T(`${who} в группе`, `${who} joined the group`),
  sysLeft: (who: string) => T(`${who} вышел(ла) из группы`, `${who} left the group`),
  sysEnough: () => T('Людей достаточно — можно делать план.', 'You have enough people to make a plan.'),
  sysRemoved: (who: string) => T(`${who} больше не в группе`, `${who} is no longer in the group`),
  /**
   * Системные строки ленты — ПО КОДУ СОБЫТИЯ, а не по разбору английской фразы.
   *
   * Пять строк ниже (sysJoined и соседи) остались от прежнего способа: сервер писал предложение
   * по-английски, клиент узнавал его регуляркой. Из двадцати семи событий так узнавались пять, а
   * промах был не виден — строка про смену организатора («X left. Y is now the organiser») не
   * подходила под шаблон «X left the group» и приезжала на русский экран по-английски.
   */
  sysCantMakeIt: (who: string) => T(`${who} не сможет прийти`, `${who} can’t make it`),
  sysConvertAsked: (who: string) =>
    T(`${who} предлагает перейти в один на один`, `${who} asked to switch to one-on-one`),
  sysConvertDeclined: (who: string) => T(`${who} хочет оставить группу`, `${who} wants to keep the group`),
  sysConverted: () => T('Группа стала перепиской один на один.', 'The group is now a one-on-one.'),
  sysGroupClosed: (who: string, title: string) => T(
    `${who} закрыл(а) «${title}» до назначения плана. Ты ни при чём. Чат останется архивом только для чтения, а остальные твои интенты не затронуты.`,
    `${who} closed ${title} before a plan was set. Nothing you did. The chat stays as a read-only archive, and your other intents aren’t affected.`
  ),
  /** Роль перешла не по своей воле — говорим обоих поимённо, иначе группа не понимает, к кому идти. */
  sysLeftHeir: (who: string, heir: string) =>
    T(`${who} вышел(ла). Теперь организатор — ${heir}`, `${who} left. ${heir} is now the organiser`),
  sysQuorumBack: () => T('Снова трое — план в силе. Подтвердите ещё раз.',
                         'Three again — the plan is back on. Everyone confirms once more.'),
  sysBelowQuorum: () => T('Для группового плана нужны трое. Пока вы не решите, ничего не произойдёт.',
                          'A group plan needs three. Nothing happens until you choose.'),
  sysPlanLocked: () => T('План закреплён — до встречи меньше двух часов.',
                         'The plan is locked — it starts in less than two hours.'),
  sysPlanReady: () => T('Групповой план готов. Подтвердите, чтобы участвовать.',
                        'A group plan is ready. Confirm to join it.'),
  sysPlanDeclined: (who: string) => T(`${who} не пойдёт по этому плану`, `${who} will not join this plan`),
  sysPlanConfirmed: (names: string) =>
    T(`Все подтвердили. План назначен: ${names}.`, `Everyone confirmed. The plan is set: ${names}.`),
  sysChangeAccepted: () => T('Изменение приняли все.', 'Everyone accepted the change.'),
  sysPlanCancelledGroupStays: (who: string) =>
    T(`${who} отменил(а) план. Группа остаётся.`, `${who} cancelled the plan. The group is still here.`),
  sysPlanCancelled: (who: string) => T(`${who} отменил(а) план`, `${who} cancelled the plan`),
  /** GR.45b. Опоздание НИЧЕГО не отменяет — строка обязана это показывать, иначе её читают как отказ. */
  sysRunningLate: (who: string, eta: number) =>
    eta > 0
      ? T(`${who} опаздывает примерно на ${eta} мин — встреча в силе`,
          `${who} is running late by about ${eta} min — the meetup is still on`)
      : T(`${who} опаздывает — встреча в силе`, `${who} is running late — the meetup is still on`),
  sysArrived: (who: string) => T(`${who} на месте`, `${who} is there`),
  // Текст взят С БОКСА как есть: он там уже написан вторым агентом, и своя вторая копия
  // означала бы две разных фразы на один код — тот же дубль, из-за которого файл не собрался.
  sysFeedbackReminder: (title: string) => T(
    `Прошло два дня после «${title || 'звонка'}». Он состоялся? Один ответ — и я больше не буду спрашивать. Завтра вопрос закроется сам.`,
    `Two days since ${title || 'the call'} — did it happen? One tap, and I’ll stop asking. It closes on its own tomorrow either way.`
  ),
  sysLinkSaved: () => T('Ссылка на звонок сохранена.', 'The call link is saved.'),
  sysPlaceSaved: () => T('Место встречи сохранено.', 'The meeting place is saved.'),
  sysAttendanceSide: (who: string, side: string) =>
    side === 'call'
      ? T(`${who} подключится по звонку.`, `${who} will join the call.`)
      : T(`${who} придёт лично.`, `${who} will join in person.`),
  hybridHead: (total: number, atPlace: number, onCall: number) =>
    T(`${total} в группе · ${atPlace} лично · ${onCall} по звонку`,
      `${total} in the group · ${atPlace} coming · ${onCall} on the call`),
  sideLabel: (side: string) => side === 'call' ? T('по звонку', 'on the call') : T('лично', 'in person'),
  sysVoteKept: (who: string) => T(`${who} оставил(а) план как есть`, `${who} kept the plan as it is`),
  sysPlanCountered: (who: string, when: string) =>
    T(`${who} предлагает изменить: ${when}. Все подтверждают заново.`,
      `${who} suggested a change: ${when}. Everyone confirms again.`),
  sysPlanFixed: (who: string, when: string) =>
    T(`${who} зафиксировал(а) план: ${when}.`, `${who} fixed the plan: ${when}.`),
  sysPlanUpdated: (who: string, when: string) =>
    T(`${who} изменил(а) план: ${when}. Примите, чтобы остаться, или выйдите.`,
      `${who} changed the plan: ${when}. Accept to stay in the group, or leave.`),
  sysSilentStayOrLeave: (names: string) =>
    T(`${names} в этот раз не подтвердил(и) — можно остаться или выйти.`,
      `${names} did not confirm this time and can stay or leave.`),
  sysVoteOpened: (who: string, kind: string) =>
    T(`${who} просит группу проголосовать: ${kind === 'edit' ? 'менять' : 'отменять'} ли план.`,
      `${who} asked the group to ${kind === 'edit' ? 'change' : 'cancel'} the plan. Please vote.`),
  sysVoteClosed: (yes: number, no: number, silent: number, owner: string, what: string) =>
    T(`Голосование закрыто: ${yes} за, ${no} против, ${silent} не ответили. Решает ${owner}.`,
      `The vote is closed: ${yes} for, ${no} against, ${silent} didn’t answer. It’s ${owner}’s call.`),
  sysFull: () => T('Группа заполнена. Открытые приглашения закрыты.',
                   'This group is full. Pending invites are no longer available.'),

  /** Нижняя кнопка. До минимума — GR.18, с минимума — GR.21. */
  createPlan: () => T('Создать план', 'Create plan'),
  /** У группы бывает ровно один план. Когда он есть, «создать» было бы враньём — там открывают. */
  openPlan: () => T('Открыть план', 'Open the plan'),
  switchTo1to1: () => T('Перейти в один на один', 'Switch to one-on-one'),
  /**
   * Кнопка видна только когда переход ВОЗМОЖЕН: их двое, плана ещё нет, группа жива. Это решает
   * сервер (`can_convert`), а не экран, — иначе клиент и сервер разошлись бы на первом же условии.
   */
  switchWhy: () => T(
    'Группа не собралась. Можно продолжить вдвоём — если собеседник согласится.',
    'The group didn’t fill up. You can keep going as two — if the other person agrees.'
  ),

  // ---- GR.19: организатор спрашивает --------------------------------------
  askTitle: (who: string) => T(`Перейти в один на один с ${who}?`, `Switch to one-on-one with ${who}?`),
  askNote: (who: string) => T(
    `${who} тоже должен согласиться. Если согласится, открытые приглашения отменятся, и позванным об этом скажут.`,
    `${who} has to agree too. If they do, your open invites are cancelled and those people are told.`
  ),
  askSend: (who: string) => T(`Спросить ${who}`, `Ask ${who} to switch`),
  keepGroup: () => T('Оставить группу', 'Keep the group'),
  askSent: (who: string) => T(`Спросили ${who} — ждём ответа.`, `Asked ${who} — waiting for an answer.`),

  // ---- GR.20: спрашивают тебя ---------------------------------------------
  answerTitle: (who: string) => T(`${who} предлагает перейти в один на один`, `${who} wants to switch to one-on-one`),
  answerNote: () => T(
    'Группа не собралась. Если согласишься, она закроется, и вы продолжите вдвоём.',
    'The group didn’t fill up. If you agree, the group closes and the two of you keep going one-on-one.'
  ),
  agree: () => T('Согласиться', 'Agree'),
  switchFailed: () => T('Не получилось. Попробуй ещё раз.', 'That didn’t work. Try again.'),

  composer: () => T('Сообщение…', 'Message…'),
  offline: () => T('Сообщение не ушло. Проверь связь.', 'The message didn’t send. Check your connection.'),
  gone: () => T('Этой группы больше нет.', 'This group is gone.'),
  notMember: () => T('Ты больше не в этой группе.', 'You’re not in this group any more.'),

  // ---- S9 / GR.51: organiser removes a joined member ---------------------
  removeMember: () => T('Удалить', 'Remove'),
  removeTitle: (who: string) => T(`Почему ты удаляешь ${who}?`, `Why are you removing ${who}?`),
  removeConfirm: (who: string) => T(`Удалить ${who}`, `Remove ${who}`),
  removeFailed: () => T('Не получилось удалить участника. Попробуй ещё раз.',
                         'Couldn’t remove this member. Try again.'),
  removalReasons: () => [
    { code: 'inappropriate_messages_or_photos' as const,
      label: T('Неуместные сообщения или фотографии', 'Inappropriate messages or photos') },
    { code: 'suspected_fake_or_stolen_profile' as const,
      label: T('Подозрение на поддельный или украденный профиль', 'Suspected fake or stolen profile') },
    { code: 'not_responding' as const, label: T('Не отвечает', 'Not responding') },
    { code: 'doesnt_fit_meetup' as const,
      label: T('Не подходит для этой встречи', "Doesn't fit this meetup") },
    { code: 'something_else' as const, label: T('Другая причина', 'Something else') },
  ],

  // ---- S9 / GR.52: removed person's view ---------------------------------
  removedNotice: (title: string) => T(
    `Тебя удалили из группы «${title}». Я не могу раскрыть причину. Остальные твои интенты не затронуты.`,
    `You were removed from ${title}. I can’t share the reason. Your other intents aren’t affected.`
  ),
  readOnlyHistory: () => T('История доступна только для чтения', 'History is read-only'),

  // ---- S10 / GR.53-55: organiser closes the group before a plan exists --
  endGroup: () => T('Завершить группу', 'End the group'),
  endTitle: (title: string) => T(`Завершить «${title}»?`, `End ${title}?`),
  endBody: (members: string) => T(
    `${members} узнают, что группа закрыта. Чат останется архивом только для чтения, а открытые приглашения отменятся. Следующие 30 дней встреча один на один всё ещё требует согласия обоих и использует план 1:1.`,
    `${members} are told the group is closed. The chat stays as a read-only archive and the open invites are cancelled. For the next 30 days, meeting either of them one-on-one still needs their agreement and uses a 1:1 plan.`
  ),
  keepGoing: () => T('Продолжить', 'Keep it going'),
  endConfirm: () => T('Завершить группу', 'End the group'),
  endFailed: () => T('Не получилось завершить группу. Попробуй ещё раз.',
                      'Couldn’t end the group. Try again.'),
  closedNotice: (owner: string, title: string) => T(
    `${owner} закрыл(а) «${title}» до назначения плана. Ты ни при чём. Чат останется архивом только для чтения, а остальные твои интенты не затронуты.`,
    `${owner} closed ${title} before a plan was set. Nothing you did. The chat stays as a read-only archive, and your other intents aren’t affected.`
  ),

  /** Экран состава — GR.24. */
  infoTitle: () => T('Кто в группе', 'Who’s in'),
  /** Сведения о самой затее — то, ради чего группа собралась. Нажатие на заголовок ведёт сюда. */
  aboutTitle: () => T('О затее', 'About this'),
  aboutTopics: () => T('Про что', 'What it’s about'),
  aboutWhen: () => T('Когда', 'When'),
  aboutWhere: () => T('Где', 'Where'),
  aboutMode: (mode: string) =>
    mode === 'online' ? T('Онлайн', 'Online')
    : mode === 'hybrid' ? T('Онлайн или вживую', 'Online or in person')
    : T('Вживую', 'In person'),
  aboutSize: (min: number, max: number) =>
    T(`От ${min} до ${max} человек`, `${min} to ${max} people`),
  aboutOwner: (who: string) => T(`Затеял(а) ${who}`, `Started by ${who}`),
  /** Пустое поле не выдумываем: «когда» и «где» на групповой затее часто не заданы вовсе. */
  aboutUnset: () => T('не задано', 'not set'),
  infoNote: (joined: number, max: number, open: number) =>
    T(
      `В группе ${joined} из ${max}, открытых приглашений: ${open}. Удалить человека можно, пока план не назначен. После этого — нельзя; участник может выйти сам.`,
      `${joined} of ${max} joined, ${open} invite${open === 1 ? '' : 's'} still open. You can remove someone until the plan is set. After that nobody can be removed — participants can leave.`
    ),
  roleOrganiser: () => T('Организатор', 'Organiser'),
  roleMember: () => T('В группе', 'In the group'),
  inviteMore: () => T('Позвать ещё людей', 'Invite more people'),
  leave: () => T('Выйти из группы', 'Leave the group'),
  leaveAsk: () => T('Выйти из группы?', 'Leave the group?'),
  leaveBody: () =>
    T('Ты выйдешь из чата и перестанешь его видеть. Остальные останутся — это не отменяет встречу.',
      'You’ll leave the chat and stop seeing it. The others stay — this doesn’t cancel anything.'),
  leaveYes: () => T('Да, выйти', 'Yes, leave'),
  cancelBtn: () => T('Отмена', 'Cancel'),
};

/**
 * Входящее групповое приглашение, сторона гостя.
 *
 * Отдельного кадра у борда НЕТ — но GR.16 описывает его содержимое словами, от лица отправителя:
 * «She sees the intent and who is already in. If she accepts she joins the shared group chat
 * straight away — there is no private chat with you». Экран построен ровно по этому обещанию, а
 * раскладка взята у 1:1-приглашения (O.C1, app/invite.tsx) — там та же задача.
 *
 * Отдельно назван случай GR.22: пока человек думал, места кончились. Об этом говорится прямо и
 * снимается вина — «Nothing you did».
 */
export const GINVITE = {
  title: (who: string, title: string) =>
    T(`${who} зовёт тебя в «${title}»`, `${who} invites you to ${title}`),
  /** Обещание GR.16 дословно: общий чат сразу, личной переписки нет. */
  note: () =>
    T(
      'Если согласишься, сразу откроется общий чат группы — личной переписки с приглашающим здесь нет.',
      'If you accept, the shared group chat opens straight away — there is no private chat with the person who invited you.'
    ),
  whosIn: () => T('Кто уже внутри', 'Who is already in'),
  seats: (joined: number, max: number, min: number) =>
    T(
      `${joined} из ${max} · для плана нужно ${min}`,
      `${joined} of ${max} · a plan needs ${min}`
    ),
  join: () => T('Присоединиться', 'Join'),
  notThisTime: () => T('Не в этот раз', 'Not this time'),
  declined: () => T('Ты отказал(ась/ся). Приглашение закрыто.', 'You passed. The invite is closed.'),
  gone: () => T('Приглашение больше не действует.', 'This invite is no longer live.'),
  /** GR.22, дословно по смыслу: группа заполнилась, пока ты думал(а), и твоей вины в этом нет. */
  full: (title: string, max: number) =>
    T(
      `«${title}» заполнилась — ${max} человек согласились раньше. Твоей вины тут нет.`,
      `${title} filled up — ${max} people joined before you. Nothing you did.`
    ),
  /** Принял, когда план уже начали: вход через апрув организатора (правило сервера). */
  awaiting: () =>
    T(
      'Ты согласился(ась), но план уже обсуждают — организатор подтвердит твой вход.',
      'You’re in as soon as the organiser approves — the group has already started planning.'
    ),
  failed: () => T('Не получилось ответить. Попробуй ещё раз.', 'Couldn’t answer. Try again.'),
};

/**
 * Системную строку ленты сервер пишет ПО-АНГЛИЙСКИ и по-английски же хранит — она часть истории
 * группы, одна на всех, а язык интерфейса у каждого свой. Поэтому здесь не перевод текста, а
 * распознавание события: строка разбирается на «что случилось + с кем» и рисуется на языке
 * читающего. Не разобралось — показываем как есть, а не прячем: непонятная строка честнее пустоты.
 */
/** Строка ленты, пришедшая с сервера: `sys` с кодом и фактами, `text` — английский запасной. */
export type GroupSys = { code?: string; [k: string]: any };

/**
 * Показать событие на языке читающего.
 *
 * Первым делом смотрим КОД. Он приходит с фактами рядом (`who`, `heir`, `when`), и по нему строка
 * собирается на нужном языке. Разбор английского текста регуляркой остался ниже ЗАПАСНЫМ путём:
 * в ленте лежат старые сообщения, записанные до появления кодов, и терять их историю нельзя.
 */
export function groupSysLine(text: string, sys?: GroupSys): string {
  const c = sys && sys.code;
  const f = (sys || {}) as any;
  const S = (v: any) => String(v == null ? '' : v);
  if (c === 'joined') return ROOM.sysJoined(S(f.who));
  if (c === 'left') return ROOM.sysLeft(S(f.who));
  if (c === 'left_heir') return ROOM.sysLeftHeir(S(f.who), S(f.heir));
  if (c === 'removed') return ROOM.sysRemoved(S(f.who));
  if (c === 'cant_make_it') return ROOM.sysCantMakeIt(S(f.who));
  if (c === 'quorum_reached') return ROOM.sysEnough();
  if (c === 'group_full') return ROOM.sysFull();
  if (c === 'convert_asked') return ROOM.sysConvertAsked(S(f.who));
  if (c === 'convert_declined') return ROOM.sysConvertDeclined(S(f.who));
  if (c === 'converted') return ROOM.sysConverted();
  if (c === 'group_closed') return ROOM.sysGroupClosed(S(f.who), S(f.title));
  if (c === 'quorum_back') return ROOM.sysQuorumBack();
  if (c === 'below_quorum') return ROOM.sysBelowQuorum();
  if (c === 'plan_locked') return ROOM.sysPlanLocked();
  if (c === 'plan_ready') return ROOM.sysPlanReady();
  if (c === 'plan_declined') return ROOM.sysPlanDeclined(S(f.who));
  if (c === 'plan_confirmed') return ROOM.sysPlanConfirmed(S(f.names));
  if (c === 'change_accepted') return ROOM.sysChangeAccepted();
  if (c === 'plan_cancelled_group_stays') return ROOM.sysPlanCancelledGroupStays(S(f.who));
  if (c === 'plan_cancelled') return ROOM.sysPlanCancelled(S(f.who));
  if (c === 'running_late') return ROOM.sysRunningLate(S(f.who), Number(f.eta || 0));
  if (c === 'arrived') return ROOM.sysArrived(S(f.who));
  if (c === 'feedback_reminder') return ROOM.sysFeedbackReminder(S(f.title));
  if (c === 'link_saved') return ROOM.sysLinkSaved();
  if (c === 'place_saved') return ROOM.sysPlaceSaved();
  if (c === 'attendance_side') return ROOM.sysAttendanceSide(S(f.who), S(f.side));
  if (c === 'vote_kept') return ROOM.sysVoteKept(S(f.who));
  if (c === 'vote_opened') return ROOM.sysVoteOpened(S(f.who), S(f.kind));
  if (c === 'vote_closed')
    return ROOM.sysVoteClosed(Number(f.yes || 0), Number(f.no || 0), Number(f.silent || 0),
                              S(f.owner), S(f.what));
  if (c === 'plan_countered' || c === 'plan_fixed' || c === 'plan_updated') {
    const when = [S(f.when), S(f.place)].filter(Boolean).join(', ');
    if (c === 'plan_countered') return ROOM.sysPlanCountered(S(f.who), when);
    if (c === 'plan_fixed') return ROOM.sysPlanFixed(S(f.who), when);
    return ROOM.sysPlanUpdated(S(f.who), when);
  }
  if (c === 'silent_stay_or_leave') return ROOM.sysSilentStayOrLeave(S(f.names));

  const t = String(text || '').trim();
  let m = t.match(/^(.+?) joined the group\.?$/i);
  if (m) return ROOM.sysJoined(m[1]);
  m = t.match(/^(.+?) left the group\.?$/i);
  if (m) return ROOM.sysLeft(m[1]);
  m = t.match(/^(.+?) is no longer in the group\.?$/i);
  if (m) return ROOM.sysRemoved(m[1]);
  if (/enough people/i.test(t)) return ROOM.sysEnough();
  if (/group is full/i.test(t)) return ROOM.sysFull();
  return t;
}


/**
 * Привести реплику комнаты к общей форме ленты.
 *
 * Сервер зовёт автора `frm`, а в личной переписке он `from`; системную строку в комнате узнают по
 * пустому автору, а в паре — по полю `sys`. Из-за этих двух различий ленты и были написаны
 * дважды: разметка совпадала, а данные под ней — нет.
 *
 * Приводим здесь, на входе, а не ветвим показ: тогда обе ленты — один компонент, и всё, что
 * сделано для переписки, работает в комнате в тот же день.
 */
export function roomMsg(raw: any): Msg {
  const who = String(raw?.frm || '').trim();
  return {
    id: raw?.id,
    from: who,
    text: String(raw?.text || ''),
    t: Number(raw?.t || 0),
    cid: raw?.cid,
    voice: raw?.kind === 'voice' ? raw?.voice : undefined,
    video: raw?.kind === 'video' ? raw?.video : undefined,
    r: raw?.r,
    rt: raw?.rt,
    deleted: !!raw?.deleted,
    // Системная строка комнаты приходит английским текстом, а не кодом: `sys` тут — только метка
    // «это не чья-то реплика», перевод делает groupSysLine по самому тексту.
    sys: who ? undefined : ({ code: 'room' } as any),
  };
}
