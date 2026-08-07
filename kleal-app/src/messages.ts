/**
 * «Сообщения» — копия и сборка строк списка. Кадры MSG.01–MSG.05.
 *
 * Список НЕ хранится: он каждый раз собирается из четырёх настоящих источников —
 * планы (/api/agent/mplans), входящие и исходящие приглашения (inbox/outbox), переписки
 * (/api/agent/threads). Пометки «без уведомлений / архив / покинул» — локальные (см. MsgPrefs
 * в state.ts): это отношение человека к списку, а не состояние разговора.
 */
import { T, getLang } from './i18n';
import type { MsgPrefs } from './state';

export const MSG = {
  title: () => T('Сообщения', 'Messages'),
  tabIntents: () => T('Интенты', 'Intents'),
  /** Договорились о времени и месте — пара уходит сюда, из «Интентов» она исчезает. */
  tabPlans: () => T('Планы', 'Plans'),
  tabPrivate: () => T('Личные', 'Private'),

  // MSG.01 — пустое состояние, дословно с кадра.
  emptyTitle: () => T('Пока никаких разговоров', 'No conversations yet'),
  emptyNote: () =>
    T(
      'Чаты появляются здесь, как только кто-то принимает твой интент или ты присоединяешься к плану. Kleal в любом случае остаётся сверху.',
      'Chats appear here the moment someone accepts your intent, or you join a plan. Kleal stays at the top either way.'
    ),
  createIntent: () => T('Создать интент', 'Create intent'),

  // Закреплённый ряд агента.
  kleal: () => 'Kleal',
  klealSub: () => T('Твой агент · всегда на связи', 'Your agent · always on'),
  klealTeaser: () => T('Скажи, чего хочется', 'Tell me what you feel like doing'),

  // Секции MSG.02/MSG.05.
  upcoming: () => T('Предстоящее', 'Upcoming'),
  forming: () => T('Собирается', 'Forming'),
  past: () => T('Прошло', 'Past'),
  muted: () => T('Без уведомлений', 'Muted'),
  archived: () => T('Архив', 'Archived'),

  // Подписи строк.
  waitingAnswer: () => T('ждёт ответа', 'waiting for an answer'),
  /** Приглашение принято, встречи ещё нет: пара договаривается в чате. */
  agreeing: () => T('договариваетесь', 'agreeing on details'),
  youWereInvited: (from: string) => T(`${from} зовёт`, `${from} invited you`),
  hoursLeft: (h: number) => T(`осталось ${h} ч`, `${h} h left`),
  ended: () => T('Закончилось', 'Ended'),
  calledOffShort: () => T('Отменилось', 'Called off'),
  rateTeaser: () => T('Как прошло? Нажми, чтобы оценить', 'How did it go? Tap to rate'),
  readOnly: () => T('Только чтение', 'Read-only'),
  mutedMark: () => T('Без уведомлений', 'Muted'),

  // MSG.03 — поиск.
  searchPlaceholder: () => T('Поиск', 'Search'),
  chats: () => T('Чаты', 'Chats'),
  messages: () => T('Сообщения', 'Messages'),
  /** Ищем по тому, что уже на экране: названия и последние реплики. Глубокого поиска по всей
   *  переписке на сервере нет — врать «ничего не найдено» про непросмотренное нельзя. */
  searchNote: () => T('Ищем по названиям и последним сообщениям.', 'Searches names and latest messages.'),
  nothingFound: () => T('Ничего не нашлось', 'Nothing found'),

  // MSG.04 — меню по долгому нажатию, подписи с кадра.
  muteAction: () => T('Без уведомлений', 'Mute notifications'),
  muteNote: () => T('Ты остаёшься в чате, он просто перестаёт жужжать.', 'You stay in the chat, it just stops buzzing.'),
  unmuteAction: () => T('Включить уведомления', 'Unmute'),
  archiveAction: () => T('В архив', 'Archive chat'),
  archiveNote: () => T('Уходит из списка, остаётся читаемым.', 'Moves out of the list, stays readable.'),
  unarchiveAction: () => T('Вернуть из архива', 'Unarchive'),
  leaveAction: () => T('Покинуть чат', 'Leave the chat'),
  leaveNote: () => T('Сообщения отсюда больше не приходят.', 'You stop getting messages from this plan.'),
  reportAction: () => T('Пожаловаться', 'Report this chat'),
  reportNote: () => T('Уйдёт человеку, не боту.', 'Goes to a human, not to a bot.'),
  reportSent: () => T('Жалоба отправлена', 'Report sent'),
  withdrawAction: () => T('Отозвать приглашение', 'Withdraw the invite'),
  withdrawNote: () => T('Человек больше не увидит его.', 'They will no longer see it.'),
};

/** Строка списка. kind решает, куда ведёт тап; key — стабильный ключ для пометок. */
export type Row = {
  key: string;
  kind: 'plan' | 'invite-in' | 'invite-out' | 'thread';
  title: string;
  sub: string;          // серым под заголовком: «сегодня 20:30 · …»
  teaser?: string;      // вторая строка: последняя реплика или подсказка
  who?: string;         // собеседник (для тапа в переписку/план)
  id?: string;          // rq_/mp_ для приглашений и планов
  photo?: string;
  t?: number;           // время последнего события — для сортировки и бейджа
  unread?: boolean;
  /** Число в красном кружке. Ставится только там, где оно настоящее: у переписок — сколько чужих
   *  реплик пришло после последнего открытия, у входящего приглашения — 1. Без числа бейдж — точка. */
  count?: number;
};

const norm = (s: string) => String(s || '').trim().toLowerCase();

/** Сколько часов осталось приглашению. Часы честные — из expires_at, а не из цифры на борде:
 *  сервер держит место 72 часа (KLEAL_PROPOSAL_TTL_S), борд рисовал 24. */
export function inviteHoursLeft(row: any, nowS = Date.now() / 1000): number {
  const e = Number(row?.expires_at || 0);
  return e > nowS ? Math.max(1, Math.round((e - nowS) / 3600)) : 0;
}

export function otherOf(plan: any, me: string): string {
  return String(plan?.other || '') ||
    String(((plan?.participants || []).find((p: any) => norm(p?.name) !== norm(me)) || {}).name || '');
}

/**
 * Вкладка «Интенты»: то, что ещё НЕ стало встречей — приглашения в обе стороны и пары, которые
 * уже согласились и договариваются. Как только появился план (у пары есть время и место),
 * строка уходит на вкладку «Планы» — см. planRows. Один и тот же человек не должен стоять в двух
 * местах: пока встреча живая, ей место среди планов, а не среди намерений.
 */
export function intentRows(me: string, plans: any[], history: any[], inbox: any[], outbox: any[], ru: boolean, planWhen: (p: any, ru: boolean) => string) {
  const forming: Row[] = [];

  for (const r of inbox || []) {
    if (r.status !== 'pending') continue;
    const h = inviteHoursLeft(r);
    forming.push({
      key: 'in:' + r.id, kind: 'invite-in', id: r.id, who: r.from, photo: r.photo,
      title: String(r.intent?.title || (r.intent?.topics || []).join(', ') || r.from),
      sub: `${MSG.youWereInvited(r.from)}${h ? ' · ' + MSG.hoursLeft(h) : ''}`,
      t: Number(r.updated || 0), unread: true, count: 1,
    });
  }

  for (const r of outbox || []) {
    if (r.status !== 'pending') continue;
    forming.push({
      key: 'out:' + r.id, kind: 'invite-out', id: r.id, who: r.to, photo: r.photo,
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
  const livePlanWith = new Set((plans || []).map((p: any) => norm(otherOf(p, me))));
  // Заявка приезжает и во входящих, и в исходящих (сервер отдаёт обе стороны) — без ключа по
  // ЧЕЛОВЕКУ одна и та же пара вставала в список двумя одинаковыми строками.
  const already = new Set<string>();
  for (const r of [...(inbox || []), ...(outbox || [])]) {
    if (r.status !== 'accepted') continue;
    const who = norm(r.from) === norm(me) ? r.to : r.from;
    const key = norm(who);
    if (!key || livePlanWith.has(key) || already.has(key)) continue;
    already.add(key);
    forming.push({
      // Ключ по человеку, а не по id заявки: пометки «без уведомлений» и «архив» ставятся на
      // собеседника и должны пережить новую заявку с тем же человеком.
      key: 'th:' + key, kind: 'thread', who, photo: r.photo,
      title: String(r.intent?.title || (r.intent?.topics || []).join(', ') || who),
      sub: `${who} · ${MSG.agreeing()}`,
      t: Number(r.updated || 0),
    });
  }

  // Прошедшие встречи живут на вкладке «Планы» вместе с живыми — см. planRows. Здесь остаётся
  // только «Собирается»: приглашения и пары, у которых встречи ещё нет.
  const byT = (a: Row, b: Row) => (b.t || 0) - (a.t || 0);
  forming.sort(byT);
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
    const happened = p.outcome ? p.outcome.happened !== false : p.state === 'done';
    const done = p.state === 'done' && happened;
    past.push({
      ...row(p),
      sub: `${done ? MSG.ended() : MSG.calledOffShort()} · ${planWhen(p, ru)}`,
      teaser: done && !p.my_feedback ? MSG.rateTeaser() : undefined,
    });
  }
  const byT = (a: Row, b: Row) => (b.t || 0) - (a.t || 0);
  upcoming.sort(byT); forming.sort(byT); past.sort(byT);
  return { upcoming, forming, past };
}

/** Вкладка «Личные»: переписки как они есть. */
export function threadRows(threads: any[]): Row[] {
  return (threads || []).map((t: any) => ({
    key: 'th:' + norm(t.who), kind: 'thread' as const, who: t.who,
    title: String(t.who || ''), sub: '', teaser: String(t.last || ''),
    photo: t.photo, t: Number(t.t || 0),
  })).sort((a, b) => (b.t || 0) - (a.t || 0));
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
export function bucketOf(r: Row, prefs: MsgPrefs): 'left' | 'archived' | 'muted' | 'normal' {
  const keys = [r.key, norm(r.who || '')];
  if ((prefs.left || []).some((k) => keys.includes(k))) return 'left';
  if ((prefs.archived || []).some((k) => keys.includes(k))) return 'archived';
  if ((prefs.muted || []).some((k) => keys.includes(k))) return 'muted';
  return 'normal';
}

/** Бейдж: последнее событие новее, чем когда тред открывали на этом устройстве. */
export function isUnread(r: Row, prefs: MsgPrefs): boolean {
  if (r.unread) return true;
  if (!r.t || !r.who) return false;
  const seen = (prefs.seen || {})[norm(r.who)] || 0;
  return r.t > seen;
}

/** «сегодня 19:42», «вт», «17/10» — короткая метка времени строки, как на кадрах. */
export function rowTime(t?: number): string {
  if (!t) return '';
  const d = new Date(t * 1000);
  const now = new Date();
  const ru = getLang() === 'ru';
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString(ru ? 'ru-RU' : 'en-US', { hour: '2-digit', minute: '2-digit', hour12: !ru });
  const days = (now.getTime() - d.getTime()) / 86400000;
  if (days < 7) return d.toLocaleDateString(ru ? 'ru-RU' : 'en-US', { weekday: 'short' });
  return d.toLocaleDateString(ru ? 'ru-RU' : 'en-US', { day: '2-digit', month: '2-digit' });
}
