/** Existing 1:1 plan -> existing conversation. No invitation, message or plan writes. */
type Plan = { id?: unknown; other?: unknown; title?: unknown; participants?: { name?: unknown }[] };
const name = (v: unknown) => typeof v === 'string' ? v.trim() : '';
const norm = (v: unknown) => name(v).toLowerCase();

export function planChatPeer(plan: Plan | null, self: string): string {
  if (!plan?.id || !norm(self)) return '';
  if (Array.isArray(plan.participants) && plan.participants.length) {
    const people = [...new Map(plan.participants.map((p) => [norm(p?.name), name(p?.name)] as const)).values()].filter(Boolean);
    // Never treat a group, non-member or malformed plan as a guessed 1:1 conversation.
    if (plan.participants.length !== 2 || people.length !== 2 || !people.some((p) => norm(p) === norm(self))) return '';
    return people.find((p) => norm(p) !== norm(self)) || '';
  }
  // Compatibility with older plan responses that exposed only `other`.
  return norm(plan.other) !== norm(self) ? name(plan.other) : '';
}

export async function preparePlanChat(
  plan: Plan | null, self: string,
  readThread: (self: string, other: string) => Promise<unknown>,
) {
  const who = planChatPeer(plan, self);
  if (!who) throw new Error('CHAT_UNAVAILABLE');
  const response = await readThread(self, who) as { ok?: boolean; error?: unknown; messages?: unknown } | null;
  if (!response || response.ok === false || response.error || !Array.isArray(response.messages)) {
    throw new Error('CHAT_UNAVAILABLE');
  }
  // An accepted, empty conversation is valid. Opening it must not create its first message.
  return { pathname: '/conversation' as const, params: { who, title: name(plan?.title) } };
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
