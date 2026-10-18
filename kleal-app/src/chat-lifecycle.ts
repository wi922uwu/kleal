/** Server evidence about a pair. Reading/arming the composer never opens a session. */
export type ChatLifecycle = {
  peerId: string;
  state: 'new' | 'active' | 'closed' | 'legacy';
  sessionId: string | null; // the current active session; closed history has no current session
  blocked: boolean;
  serverTime: number;
};

export function chatLifecycle(value: unknown, peerId?: string): ChatLifecycle | null {
  const r = value as ChatLifecycle | undefined;
  if (!r || typeof r.peerId !== 'string' || !r.peerId || (peerId && r.peerId !== peerId)
      || !['new', 'active', 'closed', 'legacy'].includes(r.state)
      || typeof r.blocked !== 'boolean' || !Number.isFinite(r.serverTime)
      || (r.sessionId !== null && typeof r.sessionId !== 'string')
      || (r.state !== 'active' && r.sessionId !== null)
      || (r.state === 'active' && !r.sessionId)) return null;
  return r;
}

export function canComposeChat(chat: ChatLifecycle | null, resumeArmed: boolean): boolean {
  return !!chat && !chat.blocked && (chat.state !== 'closed' || resumeArmed);
}
