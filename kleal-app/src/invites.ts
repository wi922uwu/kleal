/**
 * Приглашения — ОДНО состояние на все экраны, где они видны.
 *
 * Зачем модуль, а не состояние экрана. Пригласить человека можно из двух мест: со строки в выдаче
 * (O.12) и с его полной карточки (O.13). Пока каждый экран помнил отправку у себя, выходило вот что:
 * человек приглашал из списка, открывал карточку — и та, ничего не зная, показывала «Пригласить»
 * снова. Второе нажатие уходило на сервер: он держит одно открытое приглашение на пару и honestly
 * его обновляет, но у человека на глазах приглашение отправлялось ДВАЖДЫ, и отменить он мог только
 * то, про которое помнил его экран. Общий стор убирает и путаницу, и вторую отправку.
 *
 * Правда живёт на сервере (outbox), здесь только её кэш плюс оптимистичная строка сразу после
 * отправки: ждать полсекунды на собственном нажатии — значит выглядеть сломанным.
 *
 * Два правила, которые раньше жили в одном экране из двух и поэтому обходились через другой:
 *
 *   1. Точное место (intent.address) в приглашение НЕ уезжает. Под полем на OF.09 обещано, что его
 *      увидят только после взаимного «да», а заявка уходит человеку, который ещё ничего не решил.
 *      Выдача это вырезала, карточка кандидата — нет.
 *   2. Потолок открытых приглашений (MSG.22). Правило клиентское, см. CAP в candidates.ts; когда
 *      оно станет тарифом, его место на сервере.
 */
import { useEffect, useState } from 'react';
import { agent } from './api';
import type { Req, ReqStatus } from './chat';
import { CAP } from './candidates';

const norm = (s: string) => String(s || '').trim().toLowerCase();

/** Строка приглашения так, как её знает экран: id для отзыва, статус для вида кнопки. */
export type Invite = { id: string; to: string; status: ReqStatus; updated: number };

let rows: Record<string, Invite> = {};
let self = '';
const subs = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
let mounted = 0;

function emit() {
  rows = { ...rows };
  subs.forEach((f) => f());
}

/** Слить серверный outbox с кэшем. Оптимистичная строка живёт до первого ответа сервера про неё. */
function merge(list: Req[]) {
  const next: Record<string, Invite> = {};
  for (const r of list || []) {
    const to = String(r.to || '').trim();
    if (!to) continue;
    const k = norm(to);
    const row: Invite = {
      id: String(r.id || ''), to,
      status: (r.status || 'pending') as ReqStatus,
      updated: Number(r.updated || 0),
    };
    // Свежайшая заявка на человека выигрывает: сервер обновляет одну и ту же, но история бывает.
    if (!next[k] || row.updated >= next[k].updated) next[k] = row;
  }
  // Только что отправленное сервер мог ещё не отдать в этом ответе — своя строка не теряется.
  for (const [k, v] of Object.entries(rows)) if (!next[k] && v.updated === 0) next[k] = v;
  rows = next;
  subs.forEach((f) => f());
}

export async function syncInvites(who: string) {
  const name = String(who || '').trim();
  if (!name) return;
  self = name;
  try {
    const r: any = await agent.outbox(name);
    merge((r?.requests || []) as Req[]);
  } catch {
    /* тихо: это фоновая дотяжка, и ругаться на каждый неудавшийся опрос незачем */
  }
}

/**
 * Подписка экрана. Пока хоть один экран смотрит — идёт общий опрос; последний ушедший его гасит.
 * Счётчик, а не один таймер на экран: выдача и карточка живут одновременно, и два таймера
 * стучали бы в сервер вдвое чаще ради одних и тех же строк.
 */
export function useInvites(who: string) {
  const [, force] = useState(0);
  useEffect(() => {
    const f = () => force((n) => n + 1);
    subs.add(f);
    mounted += 1;
    syncInvites(who);
    if (!timer) timer = setInterval(() => syncInvites(self || who), 6000);
    return () => {
      subs.delete(f);
      mounted -= 1;
      if (mounted <= 0 && timer) { clearInterval(timer); timer = null; }
    };
  }, [who]);
  return rows;
}

/** Что с приглашением этому человеку прямо сейчас. undefined — не приглашали. */
export function inviteTo(name: string): Invite | undefined {
  return rows[norm(name)];
}

/** Открытые (неотвеченные) приглашения — из них считается потолок MSG.22. */
export function openInvites(): Invite[] {
  return Object.values(rows).filter((r) => r.status === 'pending');
}

export type SendResult = { ok: boolean; capped?: boolean; error?: string };

/** Отправка приглашения. Единственная на всё приложение — и правила OF.09/MSG.22 тоже. */
export async function sendInvite(who: string, to: string, intent: any): Promise<SendResult> {
  const from = String(who || '').trim();
  const name = String(to || '').trim();
  if (!from || !name) return { ok: false, error: 'no name' };
  const open = openInvites();
  if (open.length >= CAP.limit && !open.some((r) => norm(r.to) === norm(name))) {
    return { ok: false, capped: true };
  }
  // Правило 1 из шапки исполняет СЕРВЕР: он вырезает address на выходе получателю (inbox), а в
  // заявке место остаётся — оттуда его берёт форма плана автора, чтобы не спрашивать дважды.
  // Пока вырезал клиент, вместе с приватностью пропадал и собственный адрес отправителя.
  const r: any = await agent.propose(from, name, intent || {});
  if (!r?.ok) return { ok: false, error: String(r?.error || 'propose failed') };
  self = from;
  rows[norm(name)] = { id: String(r.id || ''), to: name, status: 'pending', updated: 0 };
  emit();
  return { ok: true };
}

/** Отзыв (O.15). ALREADY_RESOLVED — человек ответил, пока мы смотрели: отменять уже нечего. */
export async function withdrawInvite(who: string, to: string): Promise<boolean> {
  const row = inviteTo(to);
  if (!row?.id) return false;
  const r: any = await agent.withdraw(row.id, String(who || '').trim());
  if (!r?.ok && r?.error !== 'ALREADY_RESOLVED') return false;
  delete rows[norm(to)];
  emit();
  syncInvites(who);
  return true;
}

/** Смена аккаунта: чужие приглашения на новом экране показывать нельзя. */
export function resetInvites() {
  rows = {};
  self = '';
  subs.forEach((f) => f());
}
