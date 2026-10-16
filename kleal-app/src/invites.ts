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
import { agent, newIdem, Peer, peerId, peerName } from './api';
import type { Req, ReqStatus } from './chat';
import { CAP } from './candidates';

const norm = (s: string) => String(s || '').trim().toLowerCase();

/**
 * Ключ человека в кэше — ID, а не имя (kleal-ms/docs/IDENTITY.md): в выдаче бывают два «Ивана»,
 * и по имени приглашение одному показывалось на карточке обоих. Имя — ключ только у строк без id
 * (старый ответ сервера или место вызова, куда id ещё не проведён).
 */
const keyOf = (p: Peer) => (peerId(p) ? 'id:' + peerId(p) : norm(peerName(p)));

/** Строка по человеку: по id; без id — по имени, но только если такая строка одна. */
function rowOf(p: Peer): Invite | undefined {
  const byKey = rows[keyOf(p)];
  if (byKey || peerId(p)) return byKey;
  const n = norm(peerName(p));
  const hits = Object.values(rows).filter((r) => norm(r.to) === n);
  return hits.length === 1 ? hits[0] : undefined;
}

/** Строка приглашения так, как её знает экран: id для отзыва, статус для вида кнопки. */
export type Invite = { id: string; to: string; status: ReqStatus; updated: number;
  /** id приглашённого — по нему строка узнаётся, когда в выдаче тёзки. */
  toId?: string;
  /** По какой затее отправлено. Пусто у старых заявок — они были заведены до опознавателя. */
  iid?: string;
  /**
   * Название затеи из самой заявки. Опознаватель `iid` в жизни почти всегда пуст — из 428 живых
   * заявок он есть у 14, потому что затея из разговора идентификатора не имеет вовсе. Название
   * есть всегда, и для вопроса «эта заявка про ТУ ЖЕ затею?» его достаточно.
   */
  title?: string;
  /** Путь «выбор из ответивших»: когда ответил «да», до какого времени организатор выбирает. */
  answeredAt?: number;
  pickBy?: number;
  /** Срок самого приглашения (сек). */
  expiresAt?: number;
  /** Причина закрытия из следа решения: `picked_other`, `changed_mind`, `host_silent`, `seat_taken`. */
  reason?: string };

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
    const toId = String((r as any).to_id || '');
    const k = keyOf({ name: to, id: toId });
    const row: Invite = {
      id: String(r.id || ''), to, toId,
      status: (r.status || 'pending') as ReqStatus,
      updated: Number(r.updated || 0),
      iid: String((r as any).iid || ''),
      title: String(((r as any).intent || {}).title || ''),
      answeredAt: Number((r as any).answered_at || 0) || undefined,
      pickBy: Number((r as any).pick_by || 0) || undefined,
      expiresAt: Number((r as any).expires_at || 0) || undefined,
      reason: String(((r as any).trace || {}).reason || '') || undefined,
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
/** Одна и та же это затея или разные. Пусто с любой стороны — считаем, что та же. */
function sameIntent(row: Invite, it: { id?: string; title?: string } | null | undefined): boolean {
  if (!it) return true;
  const rid = String(row.iid || '').trim();
  const iid = String(it.id || '').trim();
  if (rid && iid) return rid === iid;
  const a = norm(row.title || ''), b = norm(it.title || '');
  // Названия нет ни у одной стороны — сравнивать нечем, и объявлять затеи разными на пустом месте
  // нельзя: так «Открыть чат» превратилось бы в «Пригласить» у всех старых заявок разом.
  return !a || !b ? true : a === b;
}

/**
 * Что с приглашением этому человеку ПО ЭТОЙ затее.
 *
 * Без второго довода — как раньше, по человеку. С доводом — строго по затее, и это чинит поток,
 * который иначе не начинается вовсе: с тем, с кем ты когда-то согласился, карточка в выдаче
 * НАВСЕГДА показывала «Открыть чат» и «Отменить». То есть найти знакомого под новую затею было
 * можно, а позвать его на неё — нет: приглашение не уходило никуда, и новая затея не появлялась
 * ни в переписке, ни где-либо ещё.
 */
export function inviteTo(name: Peer, forIntent?: { id?: string; title?: string } | null): Invite | undefined {
  const row = rowOf(name);
  if (!row) return undefined;
  return sameIntent(row, forIntent) ? row : undefined;
}

/** Открытые (неотвеченные) приглашения — из них считается потолок MSG.22. */
/**
   * Открытые приглашения. `iid` — считать ПО ЗАТЕЕ, как требует спека («Открытых инвайтов на
   * интент — 3 · Plus 5»).
   *
   * Считалось по всем затеям сразу, и это било по человеку с двумя живыми затеями: третье
   * приглашение по второй затее упиралось в потолок, набранный первой. Заявки, заведённые до
   * появления опознавателя, `iid` не имеют — они считаются в общую кучу, как раньше: потерять
   * их из счёта хуже, чем посчитать грубо.
   */
export function openInvites(iid?: string): Invite[] {
  // Ответивший «да» место держит до выбора организатора — сервер считает так же (REQ_OPEN).
  const open = Object.values(rows).filter((r) => r.status === 'pending' || r.status === 'answered');
  const key = String(iid || '').trim();
  if (!key) return open;
  return open.filter((r) => !r.iid || r.iid === key);
}

export type SendResult = { ok: boolean; capped?: boolean; error?: string };

/** Отправка приглашения. Единственная на всё приложение — и правила OF.09/MSG.22 тоже. */
export async function sendInvite(who: string, to: Peer, intent: any): Promise<SendResult> {
  const from = String(who || '').trim();
  const name = peerName(to).trim();
  const toId = peerId(to);
  if (!from || !name) return { ok: false, error: 'no name' };
  const open = openInvites(String((intent || {}).id || ''));
  if (open.length >= CAP.limit && !open.some((r) => (toId && r.toId ? r.toId === toId : norm(r.to) === norm(name)))) {
    return { ok: false, capped: true };
  }
  // Правило 1 из шапки исполняет СЕРВЕР: он вырезает address на выходе получателю (inbox), а в
  // заявке место остаётся — оттуда его берёт форма плана автора, чтобы не спрашивать дважды.
  // Пока вырезал клиент, вместе с приватностью пропадал и собственный адрес отправителя.
  const r: any = await agent.propose(from, { name, id: toId }, intent || {});
  if (!r?.ok) return { ok: false, error: String(r?.error || 'propose failed') };
  self = from;
  rows[keyOf({ name, id: toId })] = { id: String(r.id || ''), to: name, toId, status: 'pending', updated: 0,
                       iid: String((intent || {}).id || ''), title: String((intent || {}).title || '') };
  emit();
  return { ok: true };
}

/**
 * Отзыв (O.15).
 *
 * ALREADY_RESOLVED — человек ответил, пока мы смотрели. Раньше это выдавалось за успех: строка
 * пропадала с экрана, вызывающий получал `true` и говорил «отозвано», хотя приглашение живо и
 * принято. Отсюда и «нажимаю Отменить — ничего не происходит»: происходило, но не то, и следующий
 * же опрос возвращал строку обратно.
 *
 * Теперь исход называется своим именем: `resolved` — не отказ связи, а «поздно, уже ответили»,
 * и решает вызывающий, что об этом сказать.
 */
export type WithdrawResult = { ok: boolean; resolved?: boolean; error?: string };

export async function withdrawInvite(who: string, to: Peer): Promise<WithdrawResult> {
  const row = inviteTo(to);
  if (!row?.id) return { ok: false, error: 'NOT_FOUND' };
  // СБОЙ СВЯЗИ — ТОЖЕ ИСХОД. `agent.withdraw` бросает на 404/500 и на обрыве сети, а оба места
  // вызова ждут результат БЕЗ try/catch: исключение улетало наверх, обработчик нажатия обрывался
  // до строки, показывающей ошибку, и «Отменить» выглядело как кнопка, которая ничего не делает.
  let r: any;
  try {
    r = await agent.withdraw(row.id, String(who || '').trim());
  } catch (e: any) {
    return { ok: false, error: String(e?.message || e || 'network') };
  }
  if (!r?.ok) {
    // Ответившее приглашение отзывать нечего — и стирать его со своей стороны тоже нельзя:
    // оно продолжает жить у собеседника, и опрос вернёт его обратно.
    if (r?.error === 'ALREADY_RESOLVED') { syncInvites(who); return { ok: false, resolved: true }; }
    return { ok: false, error: String(r?.error || 'withdraw failed') };
  }
  for (const [k, v] of Object.entries(rows)) if (v.id === row.id) delete rows[k];
  emit();
  syncInvites(who);
  return { ok: true };
}

/** Все заявки по этой затее — для счётчика «Answered 2 of 3» и заголовков выдачи. */
export function invitesFor(forIntent?: { id?: string; title?: string } | null): Invite[] {
  return Object.values(rows).filter((r) => sameIntent(r, forIntent));
}

/**
 * OF.12d «Pick Marta». Выбирает одного из ответивших: его заявка становится принятой (чат и план
 * открываются), остальные открытые по той же затее сервер закрывает как `not_picked`.
 */
export async function pickInvite(who: string, to: Peer): Promise<{ ok: boolean; error?: string }> {
  const row = inviteTo(to);
  if (!row?.id) return { ok: false, error: 'NOT_FOUND' };
  let r: any;
  try {
    r = await agent.requestPick(row.id, String(who || '').trim(), newIdem('pick'));
  } catch (e: any) {
    return { ok: false, error: String(e?.message || e || 'network') };
  }
  if (!r?.ok) { syncInvites(who); return { ok: false, error: String(r?.error || 'pick failed') }; }
  const closed = new Set<string>((r.closed || []).map(String));
  const now = Date.now() / 1000;
  for (const [k, v] of Object.entries(rows)) {
    if (v.id === row.id) rows[k] = { ...v, status: 'accepted', updated: now };
    else if (closed.has(v.id)) rows[k] = { ...v, status: 'not_picked', reason: 'picked_other', updated: now };
  }
  emit();
  syncInvites(who);
  return { ok: true };
}

/** Смена аккаунта: чужие приглашения на новом экране показывать нельзя. */
export function resetInvites() {
  rows = {};
  self = '';
  subs.forEach((f) => f());
}
