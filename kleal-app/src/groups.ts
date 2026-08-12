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
  sysFull: () => T('Группа заполнена. Открытые приглашения закрыты.',
                   'This group is full. Pending invites are no longer available.'),

  /** Нижняя кнопка. До минимума — GR.18, с минимума — GR.21. */
  createPlan: () => T('Создать план', 'Create plan'),
  /** У группы бывает ровно один план. Когда он есть, «создать» было бы враньём — там открывают. */
  openPlan: () => T('Открыть план', 'Open the plan'),
  switchTo1to1: () => T('Перейти в один на один', 'Switch to one-on-one'),
  /**
   * Конверсии в 1:1 на сервере НЕТ: `converted_1to1` — только строка в гвардах, ручки под неё не
   * существует (слой 3). Кнопка с кадра поэтому выключена и подписана — по тому же правилу, что
   * нижняя панель и настройки: строка, которая выглядит рабочей и молча ничего не делает, хуже
   * честно выключенной.
   */
  switchSoon: () => T('Переход в один на один пока не сделан', 'Switching to one-on-one isn’t built yet'),

  composer: () => T('Сообщение…', 'Message…'),
  offline: () => T('Сообщение не ушло. Проверь связь.', 'The message didn’t send. Check your connection.'),
  gone: () => T('Этой группы больше нет.', 'This group is gone.'),
  notMember: () => T('Ты больше не в этой группе.', 'You’re not in this group any more.'),

  /** Экран состава — GR.24. */
  infoTitle: () => T('Кто в группе', 'Who’s in'),
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
export function groupSysLine(text: string): string {
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
