/**
 * «Сообщения» — копия и сборка строк списка. Кадры MSG.01–MSG.05.
 *
 * Список НЕ хранится: он каждый раз собирается из четырёх настоящих источников —
 * планы (/api/agent/mplans), входящие и исходящие приглашения (inbox/outbox), переписки
 * (/api/agent/threads). Пометки «без уведомлений / архив / покинул» — локальные (см. MsgPrefs
 * в state.ts): это отношение человека к списку, а не состояние разговора.
 */
import { T, getLang, dateLocale, use12h } from './i18n';
import type { MsgPrefs } from './state';
import { isMe, pidOf } from './api';
import { klealText, CHAT } from './chat';

/**
 * КЛЮЧ ЧЕЛОВЕКА — ПО id, ИМЯ ТОЛЬКО БЕЗ НЕГО (сверка 17.10, п. 5). Строки и превью сводились по имени, и
 * у двух «Анн» переписки склеивались в одну строку с чужим превью. Сервер отдаёт `who_id` — по нему.
 */
/** Ключ человека для пометок: `id:<id>`, имя — только у строк без id. Экспорт — для экранов, которые пишут пометки. */
export const personKey = (name: unknown, id?: unknown) => (id ? 'id:' + String(id) : norm(String(name || '')));

export const MSG = {
  title: () => T('Сообщения', 'Messages', 'Mensajes'),
  tabIntents: () => T('Интенты', 'Intents', 'Propuestas'),
  /** Договорились о времени и месте — пара уходит сюда, из «Интентов» она исчезает. */
  tabPlans: () => T('Планы', 'Plans', 'Planes'),
  tabPrivate: () => T('Личные', 'Private', 'Privado'),

  // MSG.01 — пустое состояние, дословно с кадра.
  emptyTitle: () => T('Пока никаких разговоров', 'No conversations yet', 'Todavía no hay conversaciones'),
  emptyNote: () =>
    T(
      'Чаты появляются здесь, как только кто-то принимает твой интент или ты присоединяешься к плану. Kleal в любом случае остаётся сверху.',
      'Chats appear here the moment someone accepts your intent, or you join a plan. Kleal stays at the top either way.'
    , 'Los chats aparecen aquí en cuanto alguien acepta tu propuesta o te unes a un plan. Kleal se queda arriba en cualquier caso.'),
  createIntent: () => T('Создать интент', 'Create intent', 'Crear propuesta'),

  // Закреплённый ряд агента.
  kleal: () => 'Kleal',
  klealSub: () => T('Твой агент · всегда на связи', 'Your agent · always on', 'Tu agente · siempre activo'),
  klealTeaser: () => T('Скажи, чего хочется', 'Tell me what you feel like doing', 'Dime qué te apetece hacer'),
  voiceMessage: () => T('Голосовое сообщение', 'Voice message', 'Mensaje de voz'),

  // Секции MSG.02/MSG.05.
  upcoming: () => T('Предстоящее', 'Upcoming', 'Próximos'),
  forming: () => T('Собирается', 'Forming', 'Formando'),
  past: () => T('Прошло', 'Past', 'Pasado'),
  muted: () => T('Без уведомлений', 'Muted', 'Silenciado'),
  archived: () => T('Архив', 'Archived', 'Archivado'),

  // Подписи строк.
  waitingAnswer: () => T('ждёт ответа', 'waiting for an answer', 'esperando una respuesta'),
  /** Приглашение принято, встречи ещё нет: пара договаривается в чате. */
  agreeing: () => T('договариваетесь', 'agreeing on details', 'acordando detalles'),
  youWereInvited: (from: string) => T(`${from} зовёт`, `${from} invited you`, `${from} te invitó`),
  hoursLeft: (h: number) => T(`осталось ${h} ч`, `${h} h left`, `${h === 1 ? 'Queda' : 'Quedan'} ${h} h`),
  ended: () => T('Закончилось', 'Ended', 'Finalizado'),
  calledOffShort: () => T('Отменилось', 'Called off', 'Cancelada'),
  /** Встреча была назначена, но никто так и не сказал, что с ней. Не «отменилось» — просто прошло. */
  wentBy: () => T('Прошло', 'Went by', 'Pasó'),
  /** Оба ответили «не состоялась» — это не отмена: отменяют заранее, а это уже после. */
  didntHappenShort: () => T('Не состоялась', 'Didn’t happen', 'No tuvo lugar'),
  rateTeaser: () => T('Как прошло? Нажми, чтобы оценить', 'How did it go? Tap to rate', '¿Cómo fue? Pulsa para calificar'),
  readOnly: () => T('Только чтение', 'Read-only', 'Solo lectura'),

  // MSG.03 — поиск.
  searchPlaceholder: () => T('Поиск', 'Search', 'Buscar'),
  chats: () => T('Чаты', 'Chats', 'Chats'),
  messages: () => T('Сообщения', 'Messages', 'Mensajes'),
  /** Ищем по тому, что уже на экране: названия и последние реплики. Глубокого поиска по всей
   *  переписке на сервере нет — врать «ничего не найдено» про непросмотренное нельзя. */
  searchNote: () => T('Ищем по названиям и последним сообщениям.', 'Searches names and latest messages.', 'Busca nombres y mensajes recientes.'),
  nothingFound: () => T('Ничего не нашлось', 'Nothing found', 'Nada encontrado'),

  // MSG.04 — меню по долгому нажатию, подписи с кадра.
  muteAction: () => T('Без уведомлений', 'Mute notifications', 'Silenciar notificaciones'),
  muteNote: () => T('Ты остаёшься в чате, он просто перестаёт жужжать.', 'You stay in the chat, it just stops buzzing.', 'Te quedas en la conversación, solo que deja de sonar.'),
  unmuteAction: () => T('Включить уведомления', 'Unmute', 'Activar sonido'),
  archiveAction: () => T('В архив', 'Archive chat', 'Archivar conversación'),
  archiveNote: () => T('Уходит из списка, остаётся читаемым.', 'Moves out of the list, stays readable.', 'Sale de la lista, pero sigue legible.'),
  unarchiveAction: () => T('Вернуть из архива', 'Unarchive', 'Desarchivar'),
  leaveAction: () => T('Покинуть чат', 'Leave the chat', 'Abandonar el chat'),
  leaveNote: () => T('Сообщения отсюда больше не приходят.', 'You stop getting messages from this plan.', 'Dejas de recibir mensajes de este plan.'),
  reportAction: () => T('Пожаловаться', 'Report this chat', 'Reportar este chat'),
  reportNote: () => T('Уйдёт человеку, не боту.', 'Goes to a human, not to a bot.', 'Va a un humano, no a un bot.'),
  reportSent: () => T('Жалоба отправлена', 'Report sent', 'Reporte enviado'),
  withdrawAction: () => T('Отозвать приглашение', 'Withdraw the invite', 'Retirar la invitación'),
  withdrawNote: () => T('Человек больше не увидит его.', 'They will no longer see it.', 'Ya no lo verán.'),

  // ===== Борд «Messages — new layout» (6873:170006), раздел A.
  searchChats: () => T('Поиск по чатам и сообщениям', 'Search chats and messages', 'Buscar chats y mensajes'),
  planning: () => T('Договариваемся', 'Planning', 'Planificando'),
  upcomingNew: () => T('Скоро', 'Upcoming', 'Próximos'),
  endedSec: () => T('Закончилось', 'Ended', 'Terminados'),
  // MSG.01a — пусто.
  noChats: () => T('Чатов пока нет', 'No chats yet', 'Aún no hay chats'),
  noChatsNote: () => T('Чат открывается, когда кто-то присоединяется к твоему интенту или ты — к чужому.',
    'A chat opens when someone joins your intent or you join theirs.',
    'Un chat se abre cuando alguien se une a tu propuesta o tú a la suya.'),
  talkToKleal: () => T('Поговорить с Kleal', 'Talk to Kleal', 'Hablar con Kleal'),
  /** Вкладка «Планы» пуста: ни одной встречи с назначенным временем. */
  noPlansYet: () => T('Планов пока нет', 'No plans yet', 'Aún no hay planes'),
  noPlansNote: () => T('Когда договоритесь о времени и месте, чат переедет сюда из «Интентов».',
    'Once you agree on a time and place, the chat moves here from Intents.',
    'Cuando acordéis hora y lugar, el chat se mueve aquí desde Propuestas.'),
  /** Вкладка «Интенты» пуста, а планы есть: всё уже договорено. */
  noIntentsOpen: () => T('Все договорились', 'Everything is agreed', 'Todo acordado'),
  noIntentsOpenNote: () => T('Здесь — чаты, где время и место ещё обсуждают. Готовые встречи — в «Планах».',
    'Chats where the time and place are still open live here. Agreed meetups are in Plans.',
    'Aquí están los chats en los que aún se habla de hora y lugar. Las quedadas acordadas están en Planes.'),
  // MSG.22a — «Личные» пусты. Вторая фраза кадра обещает «напиши из состава группы» — этого пути
  // ещё нет (личные запросы — сервер, OPEN_TASKS), поэтому пока без обещания.
  noPrivate: () => T('Личных чатов пока нет', 'No private chats yet', 'Aún no hay chats privados'),
  noPrivateNote: () => T('Здесь появятся личные переписки с людьми из твоих планов.',
    'Private chats with people from your plans will show up here.',
    'Aquí aparecerán los chats privados con gente de tus planes.'),
  // Строки списка.
  you: () => T('Ты', 'You', 'Tú'),
  inGroup: (n: number, min: number) => T(`${n}/${min} в группе`, `${n}/${min} in the group`, `${n}/${min} en el grupo`),
  makingPlan: () => T('составляем план', 'making the plan', 'haciendo el plan'),
  needMore: (n: number) => n === 1
    ? T('нужен ещё один', 'need one more', 'falta uno más')
    : T(`нужно ещё ${n}`, `need ${n} more`, `faltan ${n} más`),
  oneOnOne: (who: string) => T(`1:1 с ${who}`, `1:1 with ${who}`, `1:1 con ${who}`),
  planSentWaiting: (names: string) => T(`План отправлен · ждём ${names}`, `Plan sent · waiting for ${names}`, `Plan enviado · esperando a ${names}`),
  /** «you and Marc» — я в списке ждущих первым. */
  youAnd: (rest: string) => rest ? T(`тебя и ${rest}`, `you and ${rest}`, `ti y ${rest}`) : T('тебя', 'you', 'ti'),
  fewerLeft: () => T('Осталось меньше трёх', 'Fewer than three left', 'Quedáis menos de tres'),
  onCall: () => T('созвон', 'on a call', 'por videollamada'),
  metOn: (d: string) => d === T('вчера', 'yesterday', 'ayer')
    ? T('Встретились вчера', 'Met yesterday', 'Os visteis ayer')
    : T(`Встретились ${d}`, `Met on ${d}`, `Os visteis el ${d}`),
  closedBeforePlan: () => T('Закрыта до плана · только чтение', 'Closed before a plan · read-only', 'Cerrado antes del plan · solo lectura'),
  groupClosedOnly: (n: number, min: number) => n < min
    ? T(`Группа закрыта · собралось ${n} из ${min}`, `The group closed · only ${n} of ${min} joined`, `El grupo se cerró · solo ${n} de ${min} se unieron`)
    : T('Группа закрыта', 'The group closed', 'El grupo se cerró'),
  // MSG.04 — архив строкой внизу.
  archiveRow: () => T('Архив', 'Archive', 'Archivo'),
  chatsCount: (n: number) => T(`${n} ${n % 10 === 1 && n % 100 !== 11 ? 'чат' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 'чата' : 'чатов'}`,
    `${n} chat${n === 1 ? '' : 's'}`, `${n} chat${n === 1 ? '' : 's'}`),
  // MSG.05 — экран архива.
  archivedByYou: () => T('Убрано тобой', 'Archived by you', 'Archivados por ti'),
  archivedByYouNote: () => T('Открыты до 30 дней после встречи', 'Still open until 30 days after the meetup', 'Abiertos hasta 30 días después del encuentro'),
  readOnlySec: () => T('Только чтение', 'Read-only', 'Solo lectura'),
  readOnlySecNote: () => T('Ты вышел или тебя удалили, или прошло 30 дней после встречи', 'You left or were removed, or 30 days after the meetup', 'Saliste o te quitaron, o pasaron 30 días del encuentro'),
  openUntil: (d: string) => T(`открыт до ${d}`, `open until ${d}`, `abierto hasta el ${d}`),
  // MSG.02 / 02a — поиск.
  messageFrom: (who: string) => T(`Сообщение от ${who}`, `Message from ${who}`, `Mensaje de ${who}`),
  messageFromYou: () => T('Твоё сообщение', 'Message from you', 'Mensaje tuyo'),
  nothingFoundFor: (q: string) => T(`По «${q}» ничего не нашлось`, `Nothing found for “${q}”`, `No hay nada para «${q}»`),
  searchHint: () => T('Поиск идёт по названиям чатов, людям и сообщениям.', 'Search looks in chat names, people and messages.', 'La búsqueda mira nombres de chats, personas y mensajes.'),
  peopleAndYou: (names: string[]) => names.length
    ? T(`${names.join(', ')} и ты`, `${names.join(', ')} and you`, `${names.join(', ')} y tú`)
    : T('Только ты', 'Just you', 'Solo tú'),
  // MSG.03 / 03a — лист по долгому нажатию.
  muteNoteNew: () => T('Ты остаёшься в чате, он просто перестаёт жужжать', 'You stay in the chat, it just stops buzzing', 'Sigues en el chat, solo deja de sonar'),
  unmuteNew: () => T('Включить уведомления', 'Turn notifications on', 'Activar notificaciones'),
  unmuteNote: () => T('Счётчик и звук вернутся', 'The badge and sound come back', 'Vuelven el contador y el sonido'),
  archiveNoteNew: () => T('Уберёт из списка, чат останется открытым', 'Hides it from the list, the chat stays open', 'Lo quita de la lista, el chat sigue abierto'),
  unarchiveNew: () => T('Вернуть в список', 'Back to the list', 'Volver a la lista'),
  unarchiveNote: () => T('Чат снова стоит в своём разделе', 'The chat goes back to its section', 'El chat vuelve a su sección'),
  report: () => T('Пожаловаться', 'Report', 'Reportar'),
  reportNoteNew: () => T('Уйдёт человеку, не боту', 'Goes to a person, not a bot', 'Llega a una persona, no a un bot'),
  leaveGroup: () => T('Выйти из группы', 'Leave the group', 'Salir del grupo'),
  leaveGroupNote: (names: string[]) => names.length
    ? T(`${joinNames(names, 'и')} узнают, что ты вышел`, `${joinNames(names, 'and')} are told you left`, `${joinNames(names, 'y')} sabrán que saliste`)
    : T('Группа узнает, что ты вышел', 'The group is told you left', 'El grupo sabrá que saliste'),
  handOver: () => T('Передать роль', 'Hand the role over', 'Ceder el rol'),
  handOverNote: () => T('Организует другой, ты остаёшься', 'Someone else organises, you stay in', 'Otra persona organiza, tú sigues dentro'),
  endGroup: () => T('Закрыть группу', 'End the group', 'Cerrar el grupo'),
  endGroupNote: () => T('Чат закроется для всех', 'Closes the chat for everyone', 'Cierra el chat para todos'),
  // MSG.10a / 10b — меню участника и подтверждение выхода.
  reportGroup: () => T('Пожаловаться на группу', 'Report the group', 'Reportar el grupo'),
  whoAndPlan: () => T('Кто внутри и план', 'Who’s in and the plan', 'Quién está y el plan'),
  leaveAskTitle: (title: string) => title ? T(`Выйти из «${title}»?`, `Leave ${title}?`, `¿Salir de ${title}?`) : T('Выйти из группы?', 'Leave the group?', '¿Salir del grupo?'),
  cantUndo: () => T('Отменить это нельзя', 'You can’t undo this', 'No se puede deshacer'),
  /** Ушёл — и людей стало меньше минимума: план встаёт на паузу, организатор решает (gp_hold). */
  leaveDrops: (left: number, owner: string) => T(
    ` В плане останется ${left}, и ${owner} решит, что с ним делать.`,
    ` That drops the plan to ${left === 2 ? 'two' : left}, and ${owner} will have to choose what happens to it.`,
    ` El plan se queda con ${left} y ${owner} tendrá que decidir qué hacer.`),
  stay: () => T('Остаться', 'Stay', 'Quedarme'),
  // MSG.12 — плашка в заглушённом чате. Пушей у Kleal нет, глушится счётчик в списке.
  mutedBanner: () => T('Без уведомлений', 'Muted', 'Silenciado'),
  mutedBannerNote: () => T('Без звука и счётчика для сообщений. Изменения плана по-прежнему видны здесь.',
    'No sound or badge for messages. Plan changes still show up here.',
    'Sin sonido ni contador para los mensajes. Los cambios del plan siguen apareciendo aquí.'),
};

/** «Nuria and Paula», «Jane, Marc and Paula». */
export function joinNames(names: string[], and: string): string {
  if (names.length <= 1) return names.join('');
  return `${names.slice(0, -1).join(', ')} ${and} ${names[names.length - 1]}`;
}

/** Строка списка. kind решает, куда ведёт тап; key — стабильный ключ для пометок. */
export type Row = {
  key: string;
  kind: 'plan' | 'invite-in' | 'invite-out' | 'thread' | 'group' | 'ginvite-in';
  /** Группам собеседника нет — их открывает gid, а не имя. */
  gid?: string;
  title: string;
  sub: string;          // серым под заголовком: «сегодня 20:30 · …»
  teaser?: string;      // вторая строка: последняя реплика или подсказка
  who?: string;         // собеседник (для тапа в переписку/план)
  whoId?: string;       // его id: по нему сервер отличает тёзок (kleal-ms/docs/IDENTITY.md)
  id?: string;          // rq_/mp_ для приглашений и планов
  photo?: string;
  t?: number;           // время последнего события — для сортировки и бейджа
  unread?: boolean;
  /** Число в красном кружке. Ставится только там, где оно настоящее: у переписок — сколько чужих
   *  реплик пришло после последнего открытия, у входящего приглашения — 1. Без числа бейдж — точка. */
  count?: number;
  /** Борд «Messages — new layout»: раздел списка, люди чата (для поиска), права организатора. */
  sec?: 'planning' | 'upcoming' | 'ended';
  people?: string;
  others?: string[];
  owner?: boolean;
  canEnd?: boolean;
  canHandOver?: boolean;
  readOnly?: boolean;
  /** Когда встреча была/будет (сек) — для «open until» в архиве. */
  meetAt?: number;
};

const norm = (s: string) => String(s || '').trim().toLowerCase();

/** Свежее сверху. Правило одно на весь список — и в секциях, и при слиянии парного с групповым. */
export const newestFirst = (a: { t?: number }, b: { t?: number }) => (b.t || 0) - (a.t || 0);

/** Сколько часов осталось приглашению. Часы честные — из expires_at, а не из цифры на борде:
 *  сервер держит место 72 часа (KLEAL_PROPOSAL_TTL_S), борд рисовал 24. */
export function inviteHoursLeft(row: any, nowS = Date.now() / 1000): number {
  const e = Number(row?.expires_at || 0);
  return e > nowS ? Math.max(1, Math.round((e - nowS) / 3600)) : 0;
}

/** Второй участник плана — строка участника; «не я» решается по id (у тёзок подписи равны). */
function otherRowOf(plan: any, me: string): any {
  return (plan?.participants || []).find((p: any) => !isMe(p?.name, pidOf(p, 'name'), me)) || {};
}

function otherOf(plan: any, me: string): string {
  return String(plan?.other || '') || String(otherRowOf(plan, me).name || '');
}

/**
 * Вкладка «Интенты»: то, что ещё НЕ стало встречей — приглашения в обе стороны и пары, которые
 * уже согласились и договариваются. Как только появился план (у пары есть время и место),
 * строка уходит на вкладку «Планы» — см. planRows. Один и тот же человек не должен стоять в двух
 * местах: пока встреча живая, ей место среди планов, а не среди намерений.
 */
export function intentRows(me: string, plans: any[], inbox: any[], outbox: any[], history: any[] = []) {
  const forming: Row[] = [];

  for (const r of inbox || []) {
    if (r.status !== 'pending') continue;
    const h = inviteHoursLeft(r);
    forming.push({
      key: 'in:' + r.id, kind: 'invite-in', id: r.id, who: r.from, whoId: r.from_id, photo: r.photo,
      title: String(r.intent?.title || (r.intent?.topics || []).join(', ') || r.from),
      sub: `${MSG.youWereInvited(r.from)}${h ? ' · ' + MSG.hoursLeft(h) : ''}`,
      t: Number(r.updated || 0), unread: true, count: 1,
    });
  }

  for (const r of outbox || []) {
    if (r.status !== 'pending') continue;
    forming.push({
      key: 'out:' + r.id, kind: 'invite-out', id: r.id, who: r.to, whoId: r.to_id, photo: r.photo,
      title: String(r.intent?.title || (r.intent?.topics || []).join(', ') || r.to),
      sub: `${r.to} · ${MSG.waitingAnswer()}`,
      t: Number(r.updated || 0),
    });
  }

  // Приглашение принято, а встречи ещё нет — это и есть «собирается»: люди договариваются в чате.
  // Без этой ветки согласившаяся пара пропадала со вкладки «Интенты» до самого плана и жила только
  // в «Личных» — человек, зашедший посмотреть свои затеи, их там не находил.
  //
  // Прячем такую строку ТОЛЬКО когда с этим человеком есть ЖИВОЙ план: прошлая встреча в истории
  // не должна скрывать новую договорённость — иначе одна отменённая встреча навсегда закрывает
  // паре путь обратно в список.
  /*
   * СТРОКА «ДОГОВАРИВАЕТЕСЬ» ЖИВЁТ, ПОКА ЕСТЬ О ЧЁМ ДОГОВАРИВАТЬСЯ.
   *
   * Гасили её только живым планом, и вкладки начинали противоречить друг другу: встреча уже
   * прошла (в «Планах» — «Закончилось») или сорвалась («Отменилось»), а в «Интентах» та же затея
   * тем же названием значилась как «договариваетесь». Человек видел одно и то же в двух местах с
   * разными ответами на вопрос «что с этим сейчас».
   *
   * Но и прятать навсегда нельзя — одна отменённая встреча закрыла бы паре путь обратно. Поэтому
   * сравнение по ВРЕМЕНИ: согласие, которое УЖЕ вылилось в план, показывать незачем; согласие,
   * данное ПОСЛЕ последней встречи, — это новая затея, и её строка возвращается.
   */
  const planSeenAt = new Map<string, number>();
  const planPeerKey = (p: any) => personKey(otherOf(p, me), String(p.other_id || pidOf(otherRowOf(p, me), 'name') || ''));
  for (const p of [...(plans || []), ...(history || [])]) {
    const key = planPeerKey(p);
    if (!key) continue;
    const at = Number(p.updated || p.created || 0);
    planSeenAt.set(key, Math.max(planSeenAt.get(key) || 0, at));
  }
  const livePlanWith = new Set((plans || []).map(planPeerKey));
  // Заявка приезжает и во входящих, и в исходящих (сервер отдаёт обе стороны) — без ключа по
  // ЧЕЛОВЕКУ одна и та же пара вставала в список двумя одинаковыми строками.
  const already = new Set<string>();
  for (const r of [...(inbox || []), ...(outbox || [])]) {
    if (r.status !== 'accepted') continue;
    const mine = isMe(r.from, r.from_id, me);
    const who = mine ? r.to : r.from;
    const whoId = String((mine ? r.to_id : r.from_id) || '');
    const key = personKey(who, whoId);
    if (!key || livePlanWith.has(key) || already.has(key)) continue;
    // Согласие уже стало встречей — и встреча позади. Договариваться больше не о чем.
    if ((planSeenAt.get(key) || 0) >= Number(r.updated || 0)) continue;
    already.add(key);
    forming.push({
      // Ключ по человеку, а не по id заявки: пометки «без уведомлений» и «архив» ставятся на
      // собеседника и должны пережить новую заявку с тем же человеком.
      key: 'th:' + key, kind: 'thread', who, whoId, photo: r.photo,
      title: String(r.intent?.title || (r.intent?.topics || []).join(', ') || who),
      sub: `${who} · ${MSG.agreeing()}`,
      t: Number(r.updated || 0),
    });
  }

  // Прошедшие встречи живут на вкладке «Планы» вместе с живыми — см. planRows. Здесь остаётся
  // только «Собирается»: приглашения и пары, у которых встречи ещё нет.
  forming.sort(newestFirst);
  return { forming };
}

/**
 * Вкладка «Планы»: встречи, о которых уже договорились. Предстоящее — подтверждённые обеими
 * сторонами; Собирается — отправленные и ждущие ответа; Прошло — состоявшиеся и отменённые.
 */
export function planRows(me: string, plans: any[], history: any[], ru: boolean, planWhen: (p: any, ru: boolean) => string) {
  const upcoming: Row[] = [];
  const forming: Row[] = [];
  const past: Row[] = [];
  const row = (p: any): Row => {
    const other = otherOf(p, me);
    return {
      key: 'mp:' + p.id, kind: 'plan', id: p.id, who: other,
      whoId: String(p.other_id || pidOf(otherRowOf(p, me), 'name') || ''),
      title: String(p.title || other), sub: `${other} · ${planWhen(p, ru)}`,
      photo: (p.participants || []).find((x: any) => norm(x?.name) === norm(other))?.photo,
      t: Number(p.updated || p.created || 0),
    };
  };
  for (const p of plans || []) {
    if (p.state === 'confirmed') upcoming.push(row(p));
    else if (p.state === 'proposed') forming.push({ ...row(p), teaser: MSG.waitingAnswer() });
  }
  for (const p of history || []) {
    // «Закончилось» — про состоявшуюся встречу: сервер ставит done и когда пара ответила «не
    // состоялась», поэтому смотрим на исход, а не на состояние.
    /*
     * ПОДПИСЬ НАЗЫВАЕТ ТО, ЧТО БЫЛО. Здесь стояли ровно две: «Закончилось» и всё остальное —
     * «Отменилось». А в историю план уезжает ещё и ПО ВОЗРАСТУ, оставаясь подтверждённым: такую
     * встречу, которую просто никто не закрыл, экран объявлял отменённой. Человек читал, что
     * встречу отменили, хотя её никто не отменял.
     *
     * Четыре исхода и четыре слова: отменили заранее, состоялась, оба сказали «не состоялась»,
     * и просто прошла — никто не ответил.
     */
    const happened = p.outcome ? p.outcome.happened !== false : p.state === 'done';
    const done = p.state === 'done' && happened;
    const label =
      p.state === 'cancelled' ? MSG.calledOffShort()
      : done ? MSG.ended()
      : p.state === 'done' ? MSG.didntHappenShort()
      : MSG.wentBy();
    past.push({
      ...row(p),
      sub: `${label} · ${planWhen(p, ru)}`,
      teaser: done && !p.my_feedback ? MSG.rateTeaser() : undefined,
    });
  }
  upcoming.sort(newestFirst); forming.sort(newestFirst); past.sort(newestFirst);
  return { upcoming, forming, past };
}

/**
 * Вкладка «Личные»: переписки как они есть.
 *
 * Последней строкой вполне может оказаться СОБЫТИЕ плана («План подтверждён»), а у события пустой
 * текст — под именем зияла бы пустота. Поэтому превью собирается той же функцией, что и лента.
 */
/**
 * Личные переписки. `accepted` — люди, с которыми приглашение УЖЕ принято.
 *
 * ПЕРЕПИСКИ БЕЗ СОГЛАСИЯ ЗДЕСЬ БЫТЬ НЕ ДОЛЖНО. Сервер отдаёт тред, как только приглашение
 * отправлено, а список показывал всё подряд: человек отправлял заявку, уходил с поиска, находил
 * собеседника в «Личных», писал — и получал отказ «приглашение не принято». Чата, которого нет,
 * он и не должен был видеть. Отправленная заявка живёт во вкладке «Собирается» строкой
 * `invite-out` — там ей и место, пока второй не ответил.
 */
export function threadRows(threads: any[], me = '', ru = true, line?: (sys: any, me: string, ru: boolean) => string,
                           accepted?: Set<string>): Row[] {
  // Согласие — по id собеседника, если он есть (у тёзок имена равны); у строки без id — по имени.
  const agreed = (t: any) => (t.who_id ? accepted!.has('id:' + t.who_id) : accepted!.has(norm(t.who)));
  return (threads || []).filter((t: any) => !accepted || agreed(t)).map((t: any) => ({
    key: 'th:' + personKey(t.who, t.who_id), kind: 'thread' as const, who: t.who, whoId: t.who_id,
    title: String(t.who || ''), sub: '',
    // Последнее сообщение удалили — сервер отдаёт deleted: true и пустой last; без этой строки под
    // именем было пусто (сверка, сообщение логики 17.10).
    teaser: t.deleted ? CHAT.deleted() : t.kind === 'voice'
      ? MSG.voiceMessage()
      : klealText(t) || String(t.last || '') || (t.sys && line ? line(t.sys, me, ru) : ''),
    photo: t.photo, t: Number(t.t || 0),
    ...(Number(t.unread || 0) > 0 ? { unread: true, count: Number(t.unread) } : {}),
  })).sort(newestFirst);
}

/**
 * Групповые строки — комнаты, где я уже состою, и входящие групповые приглашения.
 *
 * Живут во вкладке «Интенты» рядом с одиночными: для человека это одна и та же затея, просто
 * людей больше. Собеседника у строки нет — открывается она по gid, поэтому `who` пустой, а
 * `open()` в экране разводит переход по kind.
 */
/** `ru` здесь больше не читается — язык решает T(). Оставлен ради общей формы с соседями. */
export function groupRows(groups: any[], invites: any[], ru: boolean): Row[] {
  const rows: Row[] = [];
  for (const g of groups || []) {
    const n = Number(g.joined_count || 0);
    const min = Number(g.min_total || 3);
    const need = Math.max(0, min - n);
    // Группа, у которой план УЖЕ ЖИВОЙ, — не намерение, а встреча: её строка живёт во вкладке
    // «Планы» (gplanRows). Здесь она пропускается, иначе одна и та же группа стояла бы в двух
    // вкладках, причём во второй с подписью «можно делать план» — про план, который уже сделан.
    // Список групп несёт состояние плана в `plan` (см. `_gi_public`), его просто никто не читал.
    const st = String((g.plan || {}).state || '');
    if (!g.read_only && (st === 'proposed' || st === 'confirmed' || st === 'locked' || st === 'below_quorum')) continue;
    rows.push({
      key: 'g:' + String(g.gid || ''),
      kind: 'group',
      gid: String(g.gid || ''),
      title: String(g.title || ''),
      sub: g.read_only
        ? T('Группа · Только чтение', 'Group · Read-only', 'Grupo · Solo lectura')
        : T(`Группа · ${n} из ${min}`, `Group · ${n} of ${min}`, `Grupo · ${n} de ${min}`),
      // Подсказка говорит то, что человеку нужно решить прямо сейчас: добрать людей или уже
      // планировать. Пересказывать последнюю реплику здесь нечем — сервер её в списке не отдаёт.
      teaser: g.read_only
        ? T('Вы больше не состоите в этой группе', 'You are no longer in this group',
           'Ya no estás en este grupo')
        : need
        ? T(`Нужен(ы) ещё ${need}`, `Need ${need} more`, `Faltan ${need}`)
        : T('Людей достаточно — можно делать план', 'Enough people — you can make a plan',
           'Ya sois suficientes — podéis hacer un plan'),
      t: Number(g.updated || g.created || 0),
    });
  }
  for (const i of invites || []) {
    rows.push({
      key: 'gi:' + String(i.id || ''),
      kind: 'ginvite-in',
      id: String(i.id || ''),
      gid: String(i.gid || ''),
      title: String(i.title || i.group_title || ''),
      sub: T('Приглашение в группу', 'Group invite', 'Invitación a un grupo'),
      teaser: String(i.from || i.owner || ''),
      t: Number(i.created || 0),
      unread: true,
      count: 1,
    });
  }
  return rows.sort(newestFirst);
}

/**
 * Групповые планы во вкладке «Планы» — рядом с планами один на один.
 *
 * Разводить их по вкладкам нельзя: для человека «план» — это встреча, на которую он идёт, и
 * сколько там людей, двое или пятеро, вопрос второй. Раньше сюда не попадали вовсе — экран
 * запрашивал только `mplans`, и созданный групповой план исчезал из списка планов.
 *
 * Собеседника у групповой строки нет, поэтому `who` пустой, а открывается она по gid — как и
 * строки комнат в `groupRows`.
 */
export function gplanRows(plans: any[], history: any[], ru: boolean,
                          when: (p: any) => string) {
  const upcoming: Row[] = [];
  const forming: Row[] = [];
  const past: Row[] = [];

  const row = (p: any): Row => {
    const n = (p.confirmed || []).length;
    return {
      key: 'gp:' + String(p.id || ''),
      kind: 'group',                 // открывается как группа: у плана свой экран внутри неё
      gid: String(p.gid || ''),
      id: String(p.id || ''),
      title: String(p.title || ''),
      // Число согласных — то, чем групповой план отличается от парного: он ещё может не собраться.
      sub: `${T('Группа', 'Group', 'Grupo')} · ${when(p)}${n ? ` · ${n} ${T('идут', 'going', 'van')}` : ''}`,
      t: Number(p.updated || p.created || 0),
    };
  };

  for (const p of plans || []) {
    if (p.state === 'confirmed' || p.state === 'locked') upcoming.push(row(p));
    else if (p.state === 'proposed') {
      // Сколько ещё ждём — это и есть повод открыть строку: возможно, ждут именно тебя.
      const need = Number(p.needs || 0);
      forming.push({
        ...row(p),
        teaser: need
          ? T(`Ждём ещё ${need}`, `Waiting for ${need} more`, `Faltan ${need} por confirmar`)
          : T('Ждём подтверждений', 'Waiting for confirmations', 'Esperando confirmaciones'),
      });
    } else if (p.state === 'below_quorum') {
      forming.push({ ...row(p), teaser: T('Осталось меньше трёх', 'Fewer than three left', 'Quedáis menos de tres') });
    }
  }
  for (const p of history || []) {
    const cancelled = p.state === 'cancelled';
    past.push({
      ...row(p),
      sub: `${cancelled ? MSG.calledOffShort() : MSG.ended()} · ${when(p)}`,
    });
  }
  return { upcoming, forming, past };
}

/**
 * Сколько непрочитанных с каждым человеком. Считает СЕРВЕР — он один знает, сколько чужих реплик
 * пришло после последнего открытия пары.
 *
 * Карта нужна, потому что одна и та же переписка стоит в двух вкладках: в «Интентах» как пара,
 * которая договаривается, и в «Личных» как переписка. Раньше число приклеивалось только ко
 * вторым, и один разговор показывал в двух местах разную правду — точку и цифру.
 */
export function unreadByPerson(threads: any[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const t of threads || []) {
    const n = Number(t?.unread || 0);
    if (n > 0) out[personKey(t.who, t.who_id)] = n;
  }
  return out;
}

/** MSG.03: фильтр по уже загруженному — названия отдельно, реплики отдельно. */
export function searchRows(rows: Row[], q: string): { chats: Row[]; messages: Row[] } {
  const needle = norm(q);
  if (!needle) return { chats: [], messages: [] };
  const chats = rows.filter((r) => norm(r.title).includes(needle) || norm(r.who || '').includes(needle));
  const messages = rows.filter((r) => !chats.includes(r) && norm(r.teaser || '').includes(needle));
  return { chats, messages };
}

/** Куда строка попадает с учётом локальных пометок. */
export function migrateLegacyMsgPrefs(prefs: MsgPrefs, peers: {name: string; id: string}[],
  proofs: {name:string;id:string;source:'saved_peer_id'}[]=[]): MsgPrefs {
  const matches = new Map<string,Set<string>>();
  for (const peer of peers) {
    const name=norm(peer.name); if (!name) continue;
    const ids=matches.get(name) || new Set<string>(); ids.add(peer.id); matches.set(name,ids);
  }
  const legacyPeers={...prefs.legacyPeers};
  const legacyProofs={...prefs.legacyProofs};
  // Only a stored ID tied to the original marker is proof. A partial inbox,
  // even one with a single matching name, is merely an observation.
  for (const proof of proofs) if (proof.id && proof.source==='saved_peer_id') legacyProofs[norm(proof.name)]={id:proof.id,source:proof.source};
  for (const [name,ids] of matches) {
    const id=ids.size===1 && !ids.has('') ? [...ids][0] : null;
    const prior=legacyPeers[name];
    const proven=prior===null || (prior && prior!==id) ? null : id;
    legacyPeers[name]=proven;
    if (!proven || legacyProofs[name]?.id!==proven) delete legacyProofs[name];
  }
  // Keep the original markers and provenance. Derived bindings never become
  // indistinguishable from an explicit ID preference and can be revoked safely.
  return JSON.stringify(legacyPeers)===JSON.stringify(prefs.legacyPeers || {})
    && JSON.stringify(legacyProofs)===JSON.stringify(prefs.legacyProofs || {})
    ? prefs : {...prefs,legacyPeers,legacyProofs};
}

export function bucketOf(r: Row, prefs: MsgPrefs): 'left' | 'archived' | 'muted' | 'normal' {
  // A legacy name marker cannot identify one of two people with the same name.
  const keys = [r.key, r.whoId ? 'id:' + r.whoId : norm(r.who || '')];
  for (const [name,proof] of Object.entries(prefs.legacyProofs || {})) {
    if (proof.source==='saved_peer_id' && proof.id===r.whoId && prefs.legacyPeers?.[name]===r.whoId) keys.push(name,'th:'+name);
  }
  if ((prefs.left || []).some((k) => keys.includes(k))) return 'left';
  if (r.whoId && prefs.chats?.[r.whoId]?.state === 'closed') return 'archived';
  if ((prefs.archived || []).some((k) => keys.includes(k))) return 'archived';
  if ((prefs.muted || []).some((k) => keys.includes(k))) return 'muted';
  return 'normal';
}

/** A local archive is a list preference, never evidence that sending is forbidden. */
export function archiveTeaser(r: Row, prefs: MsgPrefs): string | undefined {
  const chat = r.whoId ? prefs.chats?.[r.whoId] : undefined;
  if (chat?.blocked) return T('Переписка заблокирована', 'Messaging blocked', 'Mensajes bloqueados');
  if (chat?.state === 'closed') return T('Чат завершён · можно написать снова', 'Chat ended · you can write again', 'Chat finalizado · puedes volver a escribir');
  return r.teaser;
}

/**
 * Бейдж. У переписок его ставит СЕРВЕР — он один знает, сколько чужих реплик пришло после
 * последнего открытия. Локальная отметка `seen` остаётся запасным путём для строк, у которых
 * серверного счётчика нет: приглашения, планы, группы.
 *
 * Своё непрочитанным не бывает. Раньше точка загоралась и на собственном исходящем приглашении,
 * и на плане, который человек сам же поправил: сравнивалось «время события» с «когда заходил», а
 * кто это событие устроил — не спрашивалось.
 */
export function isUnread(r: Row, prefs: MsgPrefs): boolean {
  if (r.unread) return true;
  if (r.kind === 'thread') return false;      // у переписки правду говорит только счётчик сервера
  if (!r.t || !r.who) return false;
  const marks = prefs.seen || {};
  const seen = Math.max((r.whoId ? marks[personKey(r.who, r.whoId)] : 0) || 0, marks[norm(r.who)] || 0);
  return r.t > seen;
}

/** «сегодня 19:42», «вт», «17/10» — короткая метка времени строки, как на кадрах. */
export function rowTime(t?: number): string {
  if (!t) return '';
  const d = new Date(t * 1000);
  const now = new Date();
  const ru = getLang() === 'ru';
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString(dateLocale(ru), { hour: '2-digit', minute: '2-digit', hour12: use12h(ru) });
  const days = (now.getTime() - d.getTime()) / 86400000;
  if (days < 7) return d.toLocaleDateString(dateLocale(ru), { weekday: 'short' });
  return d.toLocaleDateString(dateLocale(ru), { day: '2-digit', month: '2-digit' });
}

// ============================================================ борд «Messages — new layout»

/** «Wed 8 July» — день встречи в подписи строки. */
export function dayLabel(sec?: number): string {
  if (!sec) return '';
  const ru = getLang() === 'ru';
  if (new Date(sec * 1000).toDateString() === new Date(Date.now() - 86400000).toDateString()) return T('вчера', 'yesterday', 'ayer');
  return new Date(sec * 1000).toLocaleDateString(dateLocale(ru, 'en-GB'), { weekday: 'short', day: 'numeric', month: 'long' })
    .replace(',', '');
}
/** «Today 20:30», «Tomorrow 19:00», дальше — как везде (planWhen). Так строка на кадре MSG.01. */
export function soonWhen(p: any, ru: boolean, planWhen: (p: any, ru: boolean) => string): string {
  const at = Number(p?.starts_at || 0);
  if (!at) return planWhen(p, ru);
  const d = new Date(at * 1000), now = new Date();
  const tm = d.toLocaleTimeString(dateLocale(ru), { hour: '2-digit', minute: '2-digit', hour12: use12h(ru) });
  if (d.toDateString() === now.toDateString()) return `${T('Сегодня', 'Today', 'Hoy')} ${tm}`;
  const tmr = new Date(now.getTime() + 86400000);
  if (d.toDateString() === tmr.toDateString()) return `${T('Завтра', 'Tomorrow', 'Mañana')} ${tm}`;
  return planWhen(p, ru);
}
/** «7 Aug» — короткая дата без дня недели. */
export function shortDay(sec?: number): string {
  if (!sec) return '';
  const ru = getLang() === 'ru';
  return new Date(sec * 1000).toLocaleDateString(dateLocale(ru, 'en-GB'), { day: 'numeric', month: 'short' }).replace('.', '');
}

/** Реплика группы так, как её отдаёт /gintent-thread. */
export type GMsg = { id?: string; frm?: string; frm_id?: string; text?: string; t?: number; kind?: string; sys?: any; deleted?: any };

/** Последняя реплика строкой превью: «Marc: Let’s do it», «You: …», событие — без имени. */
export function previewOf(m: { frm?: string; frm_id?: string; text?: string; kind?: string; sys?: any; mine?: boolean } | undefined,
                          me: string, sysLine: (m: any) => string): string {
  if (!m) return '';
  if (m.kind === 'system' || !m.frm && m.mine === undefined) return sysLine(m) || String(m.text || '');
  const mine = m.mine !== undefined ? m.mine : isMe(m.frm, m.frm_id, me);
  const text = String(m.text || '');
  if (!text) return '';
  return `${mine ? MSG.you() : m.frm}: ${text}`;
}

/** Сколько чужих реплик пришло после того, как группу открывали. Нет отметки — не считаем. */
export function groupUnread(msgs: GMsg[], me: string, seen?: number): number {
  if (!seen) return 0;
  return (msgs || []).filter((m) => m.kind !== 'system' && m.frm && !m.deleted && Number(m.t || 0) > seen
    && !isMe(m.frm, m.frm_id, me)).length;
}

const mOf = (p: any) => String(p?.mode || 'offline');

/**
 * Вкладка «Intents» нового вида (MSG.01): одной лентой и группы, и пары 1:1, по разделам
 * Planning / Upcoming / Ended. Приглашения сюда больше не попадают — им место в «My activity»
 * (вкладка Invites) и на главной: на борде в «Сообщениях» только чаты, которые уже открыты.
 */
export function inboxRows(a: {
  me: string; ru: boolean;
  plans: any[]; history: any[]; inbox: any[]; outbox: any[]; threads: any[];
  groups: any[]; gplans: any[]; ghistory: any[]; gmsgs: Record<string, GMsg[]>;
  seen: Record<string, number>;
  planWhen: (p: any, ru: boolean) => string;
  sysLine: (sys: any, me: string, ru: boolean) => string;
  gSysLine: (m: GMsg) => string;
}): Row[] {
  const { me, ru } = a;
  const rows: Row[] = [];
  const thr = new Map<string, any>();
  for (const t of a.threads || []) thr.set(personKey(t.who, t.who_id), t);
  const unread = unreadByPerson(a.threads);

  /** 1:1 — превью и время из переписки с этим человеком. */
  const withThread = (r: Row): Row => {
    const t = thr.get(personKey(r.who || '', r.whoId));
    if (!t) return r;
    const teaser = t.deleted ? CHAT.deleted() : t.kind === 'voice'
      ? `${t.mine ? MSG.you() + ': ' : ''}${MSG.voiceMessage()}`
      : klealText(t) || (t.sys ? a.sysLine(t.sys, me, ru) : previewOf({ frm: t.who, text: t.last, mine: !!t.mine }, me, () => ''));
    const n = unread[personKey(r.who || '', r.whoId)] || 0;
    return { ...r, teaser: teaser || r.teaser, t: Math.max(Number(r.t || 0), Number(t.t || 0)),
             ...(n ? { unread: true, count: n } : {}) };
  };
  const place1 = (p: any) => mOf(p) === 'online' ? MSG.onCall() : String(p.district || p.area || '');

  // Пары, которые согласились и договариваются, — Planning.
  for (const r of intentRows(me, a.plans, a.inbox, a.outbox, a.history).forming) {
    if (r.kind !== 'thread') continue;
    rows.push(withThread({ ...r, sec: 'planning', people: String(r.who || ''), others: [String(r.who || '')],
                           sub: `${MSG.oneOnOne(String(r.who || ''))} · ${MSG.makingPlan()}` }));
  }
  // Планы 1:1.
  const pr = planRows(me, a.plans, a.history, ru, a.planWhen);
  const byId = new Map<string, any>();
  for (const p of [...(a.plans || []), ...(a.history || [])]) byId.set(String(p.id), p);
  for (const r of pr.upcoming) {
    const p = byId.get(String(r.id)) || {};
    const where = place1(p);
    rows.push(withThread({ ...r, sec: 'upcoming', people: String(r.who || ''), others: [String(r.who || '')],
                           meetAt: Number(p.starts_at || 0) || undefined,
                           sub: `${soonWhen(p, ru, a.planWhen)}${where ? ' · ' + where : ''}` }));
  }
  for (const r of pr.forming) {
    const p = byId.get(String(r.id)) || {};
    const waiting: string[] = Array.isArray(p.waiting_on) ? p.waiting_on.map(String) : [];
    const waitingIds: string[] = Array.isArray(p.waiting_on_ids) ? p.waiting_on_ids.map(String) : [];
    const meWaits = waiting.some((w, i) => isMe(w, waitingIds[i], me));
    const who = String(r.who || '');
    rows.push(withThread({ ...r, sec: 'planning', people: who, others: [who], teaser: undefined,
                           meetAt: Number(p.starts_at || 0) || undefined,
                           sub: MSG.planSentWaiting(meWaits ? MSG.youAnd('') : who) }));
  }
  for (const r of pr.past) {
    const p = byId.get(String(r.id)) || {};
    const happened = p.outcome ? p.outcome.happened !== false : p.state === 'done';
    const met = p.state === 'done' && happened;
    const at = Number(p.starts_at || 0);
    rows.push(withThread({ ...r, sec: 'ended', people: String(r.who || ''), others: [String(r.who || '')],
                           meetAt: at || undefined,
                           sub: met && at ? MSG.metOn(dayLabel(at)) : r.sub }));
  }

  // Группы.
  const gById = new Map<string, any>();
  for (const g of a.groups || []) gById.set(String(g.gid || ''), g);
  const othersOf = (g: any) => (g?.members || []).filter((m: any) => m?.name && !isMe(m.name, m.id, me))
    .map((m: any) => String(m.name));
  const photoOf = (g: any, msgs: GMsg[]) => {
    const last = [...(msgs || [])].reverse().find((m) => m.frm && !isMe(m.frm, m.frm_id, me));
    const mem = (g?.members || []) as any[];
    const same = (m: any) => (last!.frm_id && m.id ? String(m.id) === String(last!.frm_id) : norm(m.name) === norm(last!.frm!));
    const pick = (last && mem.find(same)) || mem.find((m) => m.photo && !isMe(m.name, m.id, me));
    return pick?.photo ? String(pick.photo) : undefined;
  };
  const gRow = (gid: string, title: string, base: Partial<Row>): Row => {
    const g = gById.get(gid) || {};
    const msgs = a.gmsgs[gid] || [];
    const last = [...msgs].reverse().find((m) => !m.deleted);
    const others = othersOf(g);
    const n = groupUnread(msgs, me, a.seen['g:' + gid]);
    return {
      key: 'g:' + gid, kind: 'group', gid, title: title || String(g.title || ''), sub: '',
      teaser: previewOf(last, me, a.gSysLine),
      t: Math.max(Number(last?.t || 0), Number(g.updated || g.created || 0)),
      photo: photoOf(g, msgs), others, people: MSG.peopleAndYou(others),
      owner: !!g.i_am_owner, canEnd: !!g.can_end, canHandOver: !!g.can_hand_over,
      ...(n ? { unread: true, count: n } : {}),
      ...base,
    } as Row;
  };
  const planned = new Set<string>();
  for (const p of a.gplans || []) {
    const gid = String(p.gid || '');
    planned.add(gid);
    const g = gById.get(gid) || {};
    const members: any[] = (g.members || []).filter((m: any) => m?.name);
    const mem: string[] = members.map((m: any) => String(m.name));
    const conf = new Set((p.confirmed || []).map((x: any) => norm(x)));
    const confIds = new Set((p.confirmed_ids || []).map((x: any) => String(x)));
    const confirmed = (m: any) => (m.id && confIds.size ? confIds.has(String(m.id)) : conf.has(norm(m.name)));
    if (p.state === 'confirmed' || p.state === 'locked') {
      const where = mOf(p) === 'online' ? MSG.onCall() : String(p.area || g.area || '');
      rows.push(gRow(gid, String(p.title || ''), { sec: 'upcoming', meetAt: Number(p.starts_at || 0) || undefined,
        sub: `${soonWhen(p, ru, a.planWhen)}${where ? ' · ' + where : ''}` }));
    } else if (p.state === 'below_quorum') {
      rows.push(gRow(gid, String(p.title || ''), { sec: 'planning', sub: MSG.fewerLeft() }));
    } else {
      const waiting = members.filter((m) => !confirmed(m));
      const meWaits = waiting.some((m) => isMe(m.name, m.id, me));
      const rest = waiting.filter((m) => !isMe(m.name, m.id, me)).map((m) => String(m.name));
      const names = meWaits ? MSG.youAnd(joinNames(rest, T('и', 'and', 'y'))) : joinNames(rest, T('и', 'and', 'y'));
      rows.push(gRow(gid, String(p.title || ''), { sec: 'planning',
        sub: names ? MSG.planSentWaiting(names) : `${MSG.inGroup(mem.length, Number(g.min_total || 3))} · ${MSG.makingPlan()}` }));
    }
  }
  // Последний прошедший план группы — один на группу.
  const lastPast = new Map<string, any>();
  for (const p of a.ghistory || []) {
    const gid = String(p.gid || '');
    if (planned.has(gid)) continue;
    const cur = lastPast.get(gid);
    if (!cur || Number(p.starts_at || 0) > Number(cur.starts_at || 0)) lastPast.set(gid, p);
  }
  for (const [gid, p] of lastPast) {
    planned.add(gid);
    const at = Number(p.starts_at || 0);
    rows.push(gRow(gid, String(p.title || ''), { sec: 'ended', meetAt: at || undefined,
      sub: p.state === 'cancelled' ? `${MSG.calledOffShort()} · ${a.planWhen(p, ru)}` : at ? MSG.metOn(dayLabel(at)) : MSG.ended() }));
  }
  for (const g of a.groups || []) {
    const gid = String(g.gid || '');
    if (!gid || planned.has(gid)) continue;
    const st = String((g.plan || {}).state || '');
    if (!g.read_only && (st === 'proposed' || st === 'confirmed' || st === 'locked' || st === 'below_quorum')) continue;
    const n = Number(g.joined_count || 0), min = Number(g.min_total || 3);
    if (g.read_only) {
      rows.push(gRow(gid, '', { sec: 'ended', readOnly: true, unread: false, count: undefined,
        sub: MSG.closedBeforePlan(), teaser: MSG.groupClosedOnly(n, min) }));
    } else {
      const need = Math.max(0, min - n);
      rows.push(gRow(gid, '', { sec: 'planning',
        sub: `${MSG.inGroup(n, min)} · ${need ? MSG.needMore(need) : MSG.makingPlan()}` }));
    }
  }
  return rows.sort(newestFirst);
}

/**
 * MSG.02: поиск по обеим вкладкам. «Chats» — по названию и людям; «Messages» — по тексту реплик:
 * у групп по всей загруженной ленте, у пар 1:1 — по последней реплике (глубже список не знает).
 */
export function searchInbox(rows: Row[], gmsgs: Record<string, GMsg[]>, threads: any[], me: string, q: string) {
  const needle = norm(q);
  if (!needle) return { chats: [] as Row[], messages: [] as Row[] };
  const chats = rows.filter((r) => norm(r.title).includes(needle) || norm(r.people || r.who || '').includes(needle));
  const messages: Row[] = [];
  for (const r of rows) {
    if (r.kind === 'group' && r.gid) {
      for (const m of [...(gmsgs[r.gid] || [])].reverse()) {
        // Реплика находится и по тексту, и по автору: «marc» на кадре MSG.02 — это и «Message from Marc».
        if (m.kind === 'system' || m.deleted || !m.frm) continue;
        if (!norm(m.text || '').includes(needle) && !norm(m.frm).includes(needle)) continue;
        const mine = isMe(m.frm, m.frm_id, me);
        messages.push({ ...r, key: 'm:' + r.gid + ':' + (m.id || m.t), sub: mine ? MSG.messageFromYou() : MSG.messageFrom(m.frm),
                        teaser: String(m.text || ''), t: Number(m.t || 0), unread: false, count: undefined });
      }
    } else if (r.who) {
      const t = (threads || []).find((x: any) => personKey(x.who, x.who_id) === personKey(r.who!, r.whoId));
      if (t && t.kind !== 'voice' && t.last && (norm(t.last).includes(needle) || !t.mine && norm(t.who).includes(needle))) {
        messages.push({ ...r, key: 'm:' + r.key, sub: t.mine ? MSG.messageFromYou() : MSG.messageFrom(String(t.who)),
                        teaser: String(t.last || ''), t: Number(t.t || 0), unread: false, count: undefined });
      }
    }
  }
  messages.sort(newestFirst);
  return { chats, messages };
}
