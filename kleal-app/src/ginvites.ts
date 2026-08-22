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
import { group as gapi, newIdem } from './api';

const norm = (s: string) => String(s || '').trim().toLowerCase();

export type GRow = { id: string; to: string; state: string };
export type GCounters = {
  joined: number; max: number; min: number; open: number; cap: number; full: boolean;
};

let gid: string | null = null;
let self = '';
let rows: Record<string, GRow> = {};          // открытые приглашения, ключ — имя
let joined = new Set<string>();               // кто уже в группе (включая организатора)
let counters: GCounters = { joined: 0, max: 5, min: 3, open: 0, cap: 3, full: false };
const subs = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
let mounted = 0;

function emit() {
  rows = { ...rows };
  subs.forEach((f) => f());
}

function absorb(g: any) {
  if (!g || typeof g !== 'object') return;
  joined = new Set((g.members || []).map((m: any) => norm(m?.name)));
  const next: Record<string, GRow> = {};
  for (const i of g.invites || []) {
    const to = String(i?.to || '').trim();
    if (to) next[norm(to)] = { id: String(i.id || ''), to, state: String(i.state || 'sent') };
  }
  // Только что отправленное сервер мог ещё не отдать — оптимистичная строка не теряется.
  for (const [k, v] of Object.entries(rows)) if (!next[k] && !v.id) next[k] = v;
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

/** Состояние кандидата в наборе: в группе / приглашён / никак. */
export function groupStatusFor(name: string): 'joined' | 'pending' | undefined {
  const k = norm(name);
  if (joined.has(k)) return 'joined';
  if (rows[k]) return 'pending';
  return undefined;
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
export async function sendGroupInvite(who: string, to: string, intent: any, title: string): Promise<GSend> {
  const from = String(who || '').trim();
  const name = String(to || '').trim();
  if (!from || !name) return { ok: false, error: 'no name' };
  if (!gid) {
    const payload = {
      topics: intent?.topics || [], mode: intent?.mode,
      time: intent?.time, place: intent?.place || intent?.area,
      // Точное место не показывается приглашённым до согласия, но должно пережить набор группы:
      // сервер хранит его внутри интента и использует при создании плана.
      ...(intent?.address ? { address: intent.address } : {}),
      ...(intent?.radiusKm != null ? { radiusKm: intent.radiusKm } : {}),
    };
    const c: any = await gapi.create(from, title, payload, newIdem('gic')).catch(() => null);
    const g = c?.group;
    if (!c?.ok || !g?.gid) return { ok: false, error: String(c?.error || 'create failed') };
    gid = String(g.gid);
    self = from;
    absorb(g);
  }
  if (groupPending().length >= counters.cap && !rows[norm(name)]) return { ok: false, capped: true };
  const r: any = await gapi.invite(gid, from, name, newIdem('giv')).catch(() => null);
  if (r?.error === 'INVITE_CAP') return { ok: false, capped: true };
  if (r?.error === 'GROUP_FULL') return { ok: false, full: true };
  if (!r?.ok) return { ok: false, error: String(r?.error || 'invite failed') };
  rows[norm(name)] = { id: String((r.invite || {}).id || ''), to: name, state: 'sent' };
  emit();
  syncGroup(from);
  return { ok: true };
}

/** Отозвать открытое приглашение — Cancel строки GR.17. Ответившее отзовётся отказом сервера. */
export async function cancelGroupInvite(who: string, to: string): Promise<boolean> {
  const row = rows[norm(to)];
  if (!row?.id) return false;
  const r: any = await gapi.inviteCancel(row.id, String(who || '').trim(), newIdem('gcx')).catch(() => null);
  if (!r?.ok && r?.error !== 'WITHDRAWN') return false;
  delete rows[norm(to)];
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
  counters = { joined: 0, max: 5, min: 3, open: 0, cap: 3, full: false };
  subs.forEach((f) => f());
}
