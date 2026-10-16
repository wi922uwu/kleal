/** Existing 1:1 plan -> existing conversation. No invitation, message or plan writes. */
import { isMe, pidOf, type Peer } from './api';

type Plan = { id?: unknown; other?: unknown; other_id?: unknown; title?: unknown;
              participants?: { name?: unknown; name_id?: unknown; id?: unknown }[] };
const name = (v: unknown) => typeof v === 'string' ? v.trim() : '';
const norm = (v: unknown) => name(v).toLowerCase();
const NOBODY = { name: '', id: '' };

/**
 * Второй участник плана 1:1 — подписью И id (kleal-ms/docs/IDENTITY.md). Участники различаются по
 * id: у встречи двух тёзок подписи одинаковы, и по подписи план выглядел как встреча с самим собой.
 */
export function planChatPeerRef(plan: Plan | null, self: string): { name: string; id: string } {
  if (!plan?.id || !norm(self)) return NOBODY;
  if (Array.isArray(plan.participants) && plan.participants.length) {
    const all = plan.participants.map((p) => ({ name: name(p?.name), id: pidOf(p, 'name') }));
    const people = [...new Map(all.map((p) => [p.id || norm(p.name), p] as const)).values()]
      .filter((p) => p.name);
    // Never treat a group, non-member or malformed plan as a guessed 1:1 conversation.
    if (plan.participants.length !== 2 || people.length !== 2) return NOBODY;
    const mine = people.filter((p) => isMe(p.name, p.id, self));
    if (mine.length !== 1) return NOBODY;
    return people.find((p) => p !== mine[0]) || NOBODY;
  }
  // Compatibility with older plan responses that exposed only `other`.
  return norm(plan.other) !== norm(self) ? { name: name(plan.other), id: name(plan.other_id) } : NOBODY;
}

export function planChatPeer(plan: Plan | null, self: string): string {
  return planChatPeerRef(plan, self).name;
}

export async function preparePlanChat(
  plan: Plan | null, self: string,
  readThread: (self: string, other: Peer) => Promise<unknown>,
) {
  const who = planChatPeerRef(plan, self);
  if (!who.name) throw new Error('CHAT_UNAVAILABLE');
  const response = await readThread(self, who) as { ok?: boolean; error?: unknown; messages?: unknown } | null;
  if (!response || response.ok === false || response.error || !Array.isArray(response.messages)) {
    throw new Error('CHAT_UNAVAILABLE');
  }
  // An accepted, empty conversation is valid. Opening it must not create its first message.
  return { pathname: '/conversation' as const, params: { who: who.name, who_id: who.id, title: name(plan?.title) } };
}

export function planChatCopy(locale: string) {
  if (locale === 'ru') return {
    open: 'В чат', loading: 'Открываем чат…',
    unavailable: 'Не удалось открыть чат. Встреча не изменилась. Попробуй ещё раз.',
  };
  if (locale === 'es') return {
    open: 'Ir al chat', loading: 'Abriendo el chat…',
    unavailable: 'No se pudo abrir el chat. La quedada no ha cambiado. Inténtalo de nuevo.',
  };
  return {
    open: 'Go to chat', loading: 'Opening chat…',
    unavailable: 'Could not open the chat. Your meetup has not changed. Try again.',
  };
}
