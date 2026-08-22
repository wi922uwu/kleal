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
  voiceMessage: () => T('Голосовое сообщение', 'Voice message'),

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
  kind: 'plan' | 'invite-in' | 'invite-out' | 'thread' | 'group' | 'ginvite-in';
  /** Группам собеседника нет — их открывает gid, а не имя. */
  gid?: string;
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

/** Свежее сверху. Правило одно на весь список — и в секциях, и при слиянии парного с групповым. */
export const newestFirst = (a: { t?: number }, b: { t?: number }) => (b.t || 0) - (a.t || 0);

/** Сколько часов осталось приглашению. Часы честные — из expires_at, а не из цифры на борде:
 *  сервер держит место 72 часа (KLEAL_PROPOSAL_TTL_S), борд рисовал 24. */
export function inviteHoursLeft(row: any, nowS = Date.now() / 1000): number {
  const e = Number(row?.expires_at || 0);
  return e > nowS ? Math.max(1, Math.round((e - nowS) / 3600)) : 0;
}

function otherOf(plan: any, me: string): string {
  return String(plan?.other || '') ||
    String(((plan?.participants || []).find((p: any) => norm(p?.name) !== norm(me)) || {}).name || '');
}

/**
 * Вкладка «Интенты»: то, что ещё НЕ стало встречей — приглашения в обе стороны и пары, которые
 * уже согласились и договариваются. Как только появился план (у пары есть время и место),
 * строка уходит на вкладку «Планы» — см. planRows. Один и тот же человек не должен стоять в двух
 * местах: пока встреча живая, ей место среди планов, а не среди намерений.
 */
export function intentRows(me: string, plans: any[], inbox: any[], outbox: any[]) {
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
  upcoming.sort(newestFirst); forming.sort(newestFirst); past.sort(newestFirst);
  return { upcoming, forming, past };
}

/**
 * Вкладка «Личные»: переписки как они есть.
 *
 * Последней строкой вполне может оказаться СОБЫТИЕ плана («План подтверждён»), а у события пустой
 * текст — под именем зияла бы пустота. Поэтому превью собирается той же функцией, что и лента.
 */
export function threadRows(threads: any[], me = '', ru = true, line?: (sys: any, me: string, ru: boolean) => string): Row[] {
  return (threads || []).map((t: any) => ({
    key: 'th:' + norm(t.who), kind: 'thread' as const, who: t.who,
    title: String(t.who || ''), sub: '',
    teaser: t.kind === 'voice'
      ? MSG.voiceMessage()
      : String(t.last || '') || (t.sys && line ? line(t.sys, me, ru) : ''),
    photo: t.photo, t: Number(t.t || 0),
  })).sort(newestFirst);
}

/**
 * Групповые строки — комнаты, где я уже состою, и входящие групповые приглашения.
 *
 * Живут во вкладке «Интенты» рядом с одиночными: для человека это одна и та же затея, просто
 * людей больше. Собеседника у строки нет — открывается она по gid, поэтому `who` пустой, а
 * `open()` в экране разводит переход по kind.
 */
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
        ? (ru ? 'Группа · Только чтение' : 'Group · Read-only')
        : (ru ? `Группа · ${n} из ${min}` : `Group · ${n} of ${min}`),
      // Подсказка говорит то, что человеку нужно решить прямо сейчас: добрать людей или уже
      // планировать. Пересказывать последнюю реплику здесь нечем — сервер её в списке не отдаёт.
      teaser: g.read_only
        ? (ru ? 'Вы больше не состоите в этой группе' : 'You are no longer in this group')
        : need
        ? (ru ? `Нужен(ы) ещё ${need}` : `Need ${need} more`)
        : (ru ? 'Людей достаточно — можно делать план' : 'Enough people — you can make a plan'),
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
      sub: ru ? 'Приглашение в группу' : 'Group invite',
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
      sub: `${ru ? 'Группа' : 'Group'} · ${when(p)}${n ? ` · ${n} ${ru ? 'идут' : 'going'}` : ''}`,
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
          ? (ru ? `Ждём ещё ${need}` : `Waiting for ${need} more`)
          : (ru ? 'Ждём подтверждений' : 'Waiting for confirmations'),
      });
    } else if (p.state === 'below_quorum') {
      forming.push({ ...row(p), teaser: ru ? 'Осталось меньше трёх' : 'Fewer than three left' });
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
    if (n > 0) out[norm(t.who)] = n;
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
export function bucketOf(r: Row, prefs: MsgPrefs): 'left' | 'archived' | 'muted' | 'normal' {
  const keys = [r.key, norm(r.who || '')];
  if ((prefs.left || []).some((k) => keys.includes(k))) return 'left';
  if ((prefs.archived || []).some((k) => keys.includes(k))) return 'archived';
  if ((prefs.muted || []).some((k) => keys.includes(k))) return 'muted';
  return 'normal';
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
