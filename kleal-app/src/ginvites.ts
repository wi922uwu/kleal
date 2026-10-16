/**
 * Набор группы — ОДНА сессия на все экраны, где он виден. Родня src/invites.ts, и по той же
 * причине модуль, а не состояние экрана: приглашать можно из выдачи и с полной карточки, и оба
 * экрана обязаны видеть одно и то же, иначе «Пригласить» показывается человеку, который уже
 * приглашён (см. шапку invites.ts — эта грабля уже была пройдена в 1:1).
 *
 * Правда живёт на сервере: группа отдаёт организатору список открытых приглашений (owner-only,
 * GR.17) и состав. Здесь — кэш плюс оптимистичная строка сразу после отправки.
 *
 * ГРУППА СОЗДАЁТСЯ ЛЕНИВО, первым приглашением. Открыть выдачу — ещё не решение собирать людей:
 * если группу заводить на входе, каждый взгляд на кандидатов оставлял бы на сервере пустую
 * комнату-сироту. Пока никто не приглашён, группы нет.
 */
import { useEffect, useState } from 'react';
import { group as gapi, newIdem, pidOf, peerId, peerName, type Peer } from './api';

const norm = (s: string) => String(s || '').trim().toLowerCase();

export type GRow = {
  id: string; to: string; toId?: string; state: string;
  /** Когда ушло (мс) — «Invite sent · 14:25» на карточке GR.14a. */
  at?: number;
  /** Когда истечёт само (мс) — отсюда «Ends in 12h» полосы набора. */
  expiresAt?: number;
};
/**
 * Закрытое приглашение — карточки GR.14d «Can’t make it» и GR.14e «Invite closed». Отказ и
 * закрытие — разные события и называются по-разному: отказ освобождает место, закрытие значит, что
 * группа собралась раньше ответа.
 */
export type GClosed = {
  to: string; toId?: string; state: 'declined' | 'closed'; at: number;
  /** Почему закрылось: группа собралась раньше ответа (GR.14e), вышел срок, иное. Для пояснения. */
  why?: 'full' | 'expired' | 'other';
};
export type GStatus = 'joined' | 'pending' | 'declined' | 'closed';
export type GCounters = {
  joined: number; max: number; min: number; open: number; cap: number; full: boolean;
};

let gid: string | null = null;
let self = '';
let rows: Record<string, GRow> = {};          // открытые приглашения, ключ — id человека (имя — без id)
let joined = new Set<string>();               // кто уже в группе (включая организатора): id и имена
let closed: Record<string, GClosed> = {};     // ответившие «нет» и закрывшиеся сами — тот же ключ
let joinedAt: Record<string, number> = {};    // когда вступил (мс) — «Joined the group · 14:28»

/*
 * КЛЮЧ ЧЕЛОВЕКА — ID (kleal-ms/docs/IDENTITY.md). В выдаче бывают тёзки: по имени приглашение одному
 * «Ивану» показывалось на карточке второго, а вступивший «Иван» делал «в группе» обоих.
 */
const keyOf = (p: Peer) => (peerId(p) ? 'id:' + peerId(p) : norm(peerName(p)));
function rowOf(p: Peer): GRow | undefined {
  const byKey = rows[keyOf(p)];
  if (byKey || peerId(p)) return byKey;
  const hits = Object.values(rows).filter((r) => norm(r.to) === norm(peerName(p)));
  return hits.length === 1 ? hits[0] : undefined;
}
let counters: GCounters = { joined: 0, max: 5, min: 3, open: 0, cap: 3, full: false };
const subs = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
let mounted = 0;

function emit() {
  rows = { ...rows };
  subs.forEach((f) => f());
}

/** Секунды или миллисекунды — сервер отдаёт время секундами, клиент считает в мс. */
const ms = (v: any): number | undefined => {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return n < 1e12 ? n * 1000 : n;
};
/** Чем закончилось приглашение, которое больше не открыто. Всё, кроме отказа, — «закрылось». */
const CLOSED_STATES = new Set(['declined', 'rejected', 'expired', 'withdrawn', 'closed', 'cancelled', 'superseded']);
/**
 * ОТМЕНИЛ САМ ОРГАНИЗАТОР — НЕ ИСХОД, А ВОЗВРАТ. По борду GR.14b после «Cancel the invite» карточка
 * снова «Invite Jane» и слот свободен; показать её «Invite closed» значило бы запереть человека,
 * которого организатор просто передумал звать сейчас.
 */
const OWN_CANCEL = new Set(['withdrawn', 'cancelled']);

/** Закрытая строка сервера → исход карточки. `null` — показывать нечего (своя отмена). */
function outcomeOf(i: any, full: boolean, now: number): GClosed | null {
  const to = String(i?.to || '').trim();
  const state = String(i?.state || 'closed');
  if (!to || OWN_CANCEL.has(state)) return null;
  const declined = state === 'declined' || state === 'rejected';
  return {
    to, toId: String(i?.to_id || ''),
    state: declined ? 'declined' : 'closed',
    why: declined ? undefined : state === 'expired' ? 'expired' : full ? 'full' : 'other',
    at: ms(i?.closed_at ?? i?.answered_at) || now,
  };
}

function absorb(g: any) {
  if (!g || typeof g !== 'object') return;
  const now = Date.now();
  // Вступившие — по id, а у строки без id — по имени (старый ответ сервера).
  const members = (g.members || []) as any[];
  joined = new Set(members.map((m: any) => keyOf({ name: String(m?.name || ''), id: pidOf(m, 'name') })));
  for (const m of members) {
    const k = keyOf({ name: String(m?.name || ''), id: pidOf(m, 'name') });
    if (!joinedAt[k]) joinedAt[k] = ms(m?.joined_at ?? m?.at) || now;
  }
  /*
    ЗАКРЫТЫЕ — С СЕРВЕРА, когда он их отдаёт (`invites_closed`, только организатору; агент логики,
    03.10). Тогда он единственный источник: исход, причина и время — его, а не догадка этого
    модуля, и они переживают перезапуск. В `invites` закрытые не кладутся: их длину другие экраны
    читают как «открытых».
  */
  const serverClosed = Array.isArray(g.invites_closed);
  if (serverClosed) {
    const fresh: Record<string, GClosed> = {};
    for (const i of g.invites_closed) {
      const c = outcomeOf(i, !!g.full, now);
      if (!c) continue;
      const k = keyOf({ name: c.to, id: c.toId });
      if (joined.has(k)) continue;
      // Одного человека могли звать дважды — показываем последний исход.
      if (!fresh[k] || fresh[k].at <= c.at) fresh[k] = c;
    }
    closed = fresh;
  }
  const next: Record<string, GRow> = {};
  for (const i of g.invites || []) {
    const to = String(i?.to || '').trim();
    const toId = String(i?.to_id || '');
    if (!to) continue;
    const k = keyOf({ name: to, id: toId });
    const state = String(i.state || 'sent');
    const at = ms(i.at ?? i.created_at ?? i.ts);
    // Старый ответ мог класть закрытые прямо в `invites` — исход берётся из них, а не угадывается.
    if (CLOSED_STATES.has(state)) {
      const c = outcomeOf(i, !!g.full, now);
      if (c && !joined.has(k)) closed[k] = { ...c, at: ms(i.closed_at ?? i.answered_at) || closed[k]?.at || now };
      else if (!c) delete closed[k];
      continue;
    }
    next[k] = { id: String(i.id || ''), to, toId, state, at: at || rows[k]?.at, expiresAt: ms(i.expires_at) };
  }
  /*
    ПРИГЛАШЕНИЕ ПРОПАЛО ИЗ ОТКРЫТЫХ, А ЧЕЛОВЕК НЕ ВСТУПИЛ — значит, оно закрылось: «нет» (GR.14d) или
    группа собралась раньше ответа (GR.14e). Свою отмену экран убирает из `rows` сам ДО перечитывания,
    поэтому сюда она не попадает. Различаем по полноте группы: пока места есть, пропажа — это отказ.
    ПОКА СЕРВЕР НЕ ОТДАЁТ ЗАКРЫТЫЕ СТРОКИ, это догадка клиента и живёт до перезапуска — см. память
    kleal-create-board-w2 (зона логики).
  */
  // Ответ без списка приглашений (не тот вид, обрыв) — не повод объявлять всех отказавшимися.
  // Сервер сам отдал закрытые — угадывать нечего: пропавшая без исхода строка — это своя отмена.
  const listed = Array.isArray(g.invites) && !serverClosed;
  for (const [k, v] of Object.entries(rows)) {
    if (!listed || next[k] || !v.id || joined.has(k) || closed[k]) continue;
    closed[k] = { to: v.to, toId: v.toId, state: g.full ? 'closed' : 'declined', why: g.full ? 'full' : undefined, at: now };
  }
  // Только что отправленное сервер мог ещё не отдать — оптимистичная строка не теряется.
  for (const [k, v] of Object.entries(rows)) if (!next[k] && !v.id) next[k] = v;
  // Позвали заново после отказа — открытая строка главнее закрытой.
  for (const k of Object.keys(next)) delete closed[k];
  for (const k of joined) delete closed[k];
  rows = next;
  counters = {
    joined: Number(g.joined_count || joined.size || 0),
    max: Number(g.max_total || 5),
    min: Number(g.min_total || 3),
    open: Object.values(next).filter((r) => r.state !== 'awaiting_approval').length,
    cap: Number(g.invite_cap || 3),
    full: !!g.full,
  };
  subs.forEach((f) => f());
}

export async function syncGroup(who?: string) {
  const name = String(who || self || '').trim();
  if (!name || !gid) return;
  self = name;
  try {
    const r: any = await gapi.get(gid, name);
    if (r?.group) absorb(r.group);
  } catch {
    /* фоновая дотяжка — молча */
  }
}

/** Подписка экрана; общий опрос, пока группа существует и хоть один экран смотрит. */
export function useGroupSession(who: string, active: boolean) {
  const [, force] = useState(0);
  useEffect(() => {
    if (!active) return;
    const f = () => force((n) => n + 1);
    subs.add(f);
    mounted += 1;
    syncGroup(who);
    if (!timer) timer = setInterval(() => syncGroup(), 6000);
    return () => {
      subs.delete(f);
      mounted -= 1;
      if (mounted <= 0 && timer) { clearInterval(timer); timer = null; }
    };
  }, [who, active]);
  return { gid, rows, counters };
}

/** Состояние кандидата в наборе: в группе / приглашён / отказался / закрылось / никак. */
export function groupStatusFor(who: Peer): GStatus | undefined {
  if (joined.has(keyOf(who))) return 'joined';
  if (rowOf(who)) return 'pending';
  const c = closedOf(who);
  return c ? c.state : undefined;
}

function closedOf(p: Peer): GClosed | undefined {
  const byKey = closed[keyOf(p)];
  if (byKey || peerId(p)) return byKey;
  const hits = Object.values(closed).filter((r) => norm(r.to) === norm(peerName(p)));
  return hits.length === 1 ? hits[0] : undefined;
}

/** Когда наступило текущее состояние (мс): ушло, вступил, ответил. Нет — времени не показываем. */
export function groupStatusAt(who: Peer): number | undefined {
  const k = keyOf(who);
  if (joined.has(k)) return joinedAt[k];
  const r = rowOf(who);
  if (r) return r.at;
  return closedOf(who)?.at;
}

/** Закрытые приглашения — строки «Can’t make it» / «Invite closed» обзора GR.17a. */
export function groupClosed(): GClosed[] {
  return Object.values(closed);
}

/** Исход одного человека — с причиной, чтобы пояснение под «Invite closed» говорило правду. */
export function groupClosedOf(who: Peer): GClosed | undefined {
  return closedOf(who);
}

/**
 * Когда кончается набор — «Ends in 12h» на полосе GR.14a. Срок у каждого приглашения свой; полоса
 * показывает ближайший, то есть когда первое из открытых закроется само. Срока нет в ответе — нет
 * и строки: выдумывать часы нельзя.
 */
export function groupEndsAt(): number | undefined {
  const ts = Object.values(rows).map((r) => r.expiresAt || 0).filter((x) => x > 0);
  return ts.length ? Math.min(...ts) : undefined;
}

export function groupCounters(): GCounters {
  return counters;
}

export function groupPending(): GRow[] {
  return Object.values(rows);
}

export function groupId(): string | null {
  return gid;
}

/**
 * Привязать сессию к УЖЕ существующей группе — «Позвать ещё людей» с экрана состава (GR.24).
 *
 * Без этого набор умел только одно: создать новую группу первым приглашением. Организатор, у
 * которого группа уже есть, нажимал «позвать ещё» и заводил ВТОРУЮ — с тем же названием, пустую,
 * и звал людей в неё. Снаружи это выглядит как «приглашение ушло», а человек попадает не туда,
 * где остальные.
 */
export async function adoptGroup(who: string, id: string): Promise<boolean> {
  const name = String(who || '').trim();
  const g = String(id || '').trim();
  if (!name || !g) return false;
  gid = g;
  self = name;
  rows = {};
  joined = new Set();
  closed = {};
  joinedAt = {};
  try {
    const r: any = await gapi.get(g, name);
    if (!r?.group) { gid = null; return false; }
    absorb(r.group);
    return true;
  } catch {
    gid = null;
    return false;
  }
}

export type GSend = { ok: boolean; capped?: boolean; full?: boolean; error?: string };

/**
 * Пригласить в группу. Первое приглашение сначала СОЗДАЁТ группу — см. шапку. Кап проверяет
 * сервер (INVITE_CAP), но и локально он известен: не ходить за отказом, который виден заранее.
 */
export async function sendGroupInvite(who: string, to: Peer, intent: any, title: string): Promise<GSend> {
  const from = String(who || '').trim();
  const name = peerName(to).trim();
  const toId = peerId(to);
  if (!from || !name) return { ok: false, error: 'no name' };
  if (!gid) {
    // Группа должна получить ТОТ ЖЕ интент, который человек только что проверил в сводке.
    // Сокращённая копия теряла link/dateKey/audience: для Group Online это означало, что
    // созданный на первом приглашении gintent уже не знал ссылку звонка, хотя сводка её показывала.
    const payload = {
      ...(intent || {}),
      topics: intent?.topics || [],
      mode: intent?.mode,
      time: intent?.time,
      place: intent?.place || intent?.area,
    };
    const requestedTotal = Number(intent?.groupSize);
    const opts = Number.isFinite(requestedTotal) && requestedTotal >= 3
      ? { min_total: 3, max_total: requestedTotal }
      : {};
    const c: any = await gapi.create(from, title, payload, newIdem('gic'), opts).catch(() => null);
    const g = c?.group;
    if (!c?.ok || !g?.gid) return { ok: false, error: String(c?.error || 'create failed') };
    gid = String(g.gid);
    self = from;
    absorb(g);
  }
  if (groupPending().length >= counters.cap && !rowOf({ name, id: toId })) return { ok: false, capped: true };
  const r: any = await gapi.invite(gid, from, { name, id: toId }, newIdem('giv')).catch(() => null);
  if (r?.error === 'INVITE_CAP') return { ok: false, capped: true };
  if (r?.error === 'GROUP_FULL') return { ok: false, full: true };
  if (!r?.ok) return { ok: false, error: String(r?.error || 'invite failed') };
  const inv: any = r.invite || {};
  rows[keyOf({ name, id: toId })] = {
    id: String(inv.id || ''), to: name, toId, state: 'sent',
    at: ms(inv.at ?? inv.created_at) || Date.now(), expiresAt: ms(inv.expires_at),
  };
  delete closed[keyOf({ name, id: toId })];
  emit();
  syncGroup(from);
  return { ok: true };
}

/** Отозвать открытое приглашение — Cancel строки GR.17. Ответившее отзовётся отказом сервера. */
export async function cancelGroupInvite(who: string, to: Peer): Promise<boolean> {
  const row = rowOf(to);
  if (!row?.id) return false;
  const r: any = await gapi.inviteCancel(row.id, String(who || '').trim(), newIdem('gcx')).catch(() => null);
  if (!r?.ok && r?.error !== 'WITHDRAWN') return false;
  for (const [k, v] of Object.entries(rows)) if (v.id === row.id) delete rows[k];
  emit();
  syncGroup(who);
  return true;
}

/**
 * Новый поиск — новая сессия набора. Зовётся из мастера перед выдачей: прошлая группа остаётся
 * жить на сервере (она настоящая, в ней люди), но выдача другого запроса ей больше не принадлежит.
 */
export function resetGroupSession() {
  gid = null;
  rows = {};
  joined = new Set();
  closed = {};
  joinedAt = {};
  counters = { joined: 0, max: 5, min: 3, open: 0, cap: 3, full: false };
  subs.forEach((f) => f());
}
