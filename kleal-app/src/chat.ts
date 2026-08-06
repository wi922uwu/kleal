/**
 * Переписка и план встречи — кадры O.16–O.20.
 *
 * UX-каркас: копия и разбор ответов здесь, экраны в app/conversation.tsx и app/plan.tsx.
 *
 * Что описывают кадры:
 *
 *  O.16  Приглашение отклонили — на карточке «Отклонено» и «Убрать».
 *  O.17  Приглашение приняли — «Открыть чат» и «Отменить». Плюс окно бесплатного тарифа: чат
 *        можно вести с одним мэтчем за раз, второй просит закончить первый или взять Plus.
 *  O.18  Сам чат: шапка с названием интента, лента, композер.
 *  O.19  Лист действий: создать план, закончить разговор, открыть интент, продолжить.
 *  O.20  План отправлен и ждёт ответа: карточка плана, статусы обоих, «Открыть чат» и «Поправить».
 *
 * Про тариф. Ограничение «один чат на интент» — продуктовое правило с кадра O.17, и на сервере его
 * НЕТ: он позволяет писать любому, кто принял приглашение. Здесь оно живёт как правило клиента, и
 * это честно помечено — когда тариф появится на сервере, проверку надо будет перенести туда, иначе
 * ограничение обходится любым другим клиентом.
 */
import { T } from './i18n';

/** Статус заявки: как его называет сервер (см. §14.1). */
export type ReqStatus = 'pending' | 'accepted' | 'declined' | 'withdrawn' | 'expired';

export const CHAT = {
  /** O.16 — приглашение отклонили. */
  declined: () => T('Отклонено', 'Declined'),
  remove: () => T('Убрать', 'Remove'),

  /** O.17 — приглашение приняли. */
  openChat: () => T('Открыть чат', 'Open chat'),
  continueChat: () => T('Продолжить чат', 'Continue chat'),

  /** Окно бесплатного тарифа, текст с кадра O.17. */
  busyTitle: (name: string) => T(`Ты уже переписываешься с ${name}`, `You're already chatting with ${name}`),
  busyBody: () =>
    T(
      'На бесплатном тарифе можно вести переписку только с одним мэтчем за раз. Закончи текущую, чтобы начать с другим, или подключи Kleal Plus — тогда доступны все три.',
      'On the Free plan, you can chat with only one match at a time. End your current chat to start one with another match, or upgrade to Kleal Plus to chat with all three.'
    ),
  getPlus: () => T('Подключить Kleal Plus', 'Get Kleal Plus'),
  plusPrice: () => T('€6,99 в месяц · переписка со всеми · отмена в любой момент',
                     '€6.99 / month · Chat with all matches · Cancel any time'),
  endChatWith: (name: string) => T(`Закончить переписку с ${name}`, `End chat with ${name}`),

  /** O.18 — сам чат. */
  placeholder: () => T('Сообщение…', 'Message…'),
  empty: (name: string) =>
    T(`${name} принял(а) приглашение. Напиши первым — это ваш общий разговор про интент.`,
      `${name} accepted your invite. Say hello — this chat belongs to your intent.`),
  offline: () => T('Сообщение не ушло. Проверь связь.', 'The message didn’t send. Check your connection.'),

  /** O.19 — лист действий. */
  actionsTitle: () => T('Действия с разговором', 'Conversation Actions'),
  createPlan: () => T('Создать план', 'Create Plan'),
  endConversation: () => T('Закончить разговор', 'End Conversation'),
  viewIntent: () => T('Открыть интент', 'View intent'),
  keepChatting: () => T('Продолжить разговор', 'Keep Chatting'),
  endAsk: (name: string) =>
    T(`Закончить разговор с ${name}? Переписка закроется, а место освободится для другого мэтча.`,
      `End the chat with ${name}? The conversation closes and frees the slot for another match.`),

  /** O.20 — план отправлен. */
  sentTo: (name: string) => T(`Отправлено: ${name}`, `Sent to ${name}`),
  sentNote: (name: string) =>
    T(
      `${name} видит время, место и ссылку. Пока не подтвердит — ничего не забронировано ни у кого из вас.`,
      'They see the time, the place and the link. Until they confirm, nothing is booked for either of you.'
    ),
  notAnswered: () => T('Ещё не ответил(а)', 'Hasn’t answered yet'),
  youProposed: () => T('Это предложил(а) ты', 'You proposed this'),
  confirmed: () => T('Подтвердил(а)', 'Confirmed'),
  declinedPlan: () => T('Отказался(ась)', 'Declined'),
  changePlan: () => T('Поправить план', 'Change the plan'),
  videoCall: () => T('Видеозвонок · ссылка сохранена', 'Video call · link saved'),
  planFailed: () => T('План не отправился. Попробуй ещё раз.', 'The plan didn’t send. Try again.'),
  /** Сервер отказывает, если человек ещё не принял приглашение, — говорим об этом словами. */
  notMatched: () => T('План можно отправить только тому, кто принял приглашение.',
                      'A plan can only go to someone who accepted your invite.'),
  inThePast: () => T('Это время уже прошло. Выбери другое.', 'That time has already passed. Pick another.'),
};

export type Msg = { from?: string; to?: string; text?: string; t?: number };
export type Req = {
  id?: string;
  from?: string;
  to?: string;
  status?: ReqStatus;
  photo?: string;
  intent?: any;
  updated?: number;
};

/** Заявки по имени собеседника — чтобы карточка выдачи знала своё состояние. */
export function byPerson(reqs: Req[]): Record<string, Req> {
  const out: Record<string, Req> = {};
  for (const r of reqs || []) {
    const who = String(r.to || '').trim();
    if (!who) continue;
    const prev = out[who];
    // Свежайшая заявка на человека выигрывает: сервер обновляет одну и ту же, но история бывает.
    if (!prev || (r.updated || 0) > (prev.updated || 0)) out[who] = r;
  }
  return out;
}

/**
 * С кем переписка ИДЁТ на самом деле — по последним сообщениям, а не по принятым приглашениям.
 *
 * Считать активным чатом любое принятое приглашение было ошибкой: принять — это ещё не начать
 * разговаривать, и человек с двумя принятыми не мог открыть НИ ОДИН чат — каждый просил закончить
 * другой. Разговор существует тогда, когда в нём есть сообщения; это и есть тот самый «один чат»
 * бесплатного тарифа.
 *
 * Пусто — не переписывается ни с кем, любой чат открывается свободно.
 */
export function activeChatWith(threads: { who?: string; t?: number }[]): string {
  const live = (threads || []).filter((t) => String(t.who || '').trim());
  live.sort((a, b) => (b.t || 0) - (a.t || 0));
  return String(live[0]?.who || '');
}

/** Время сообщения — часы и минуты, как на кадре. */
export function msgTime(t?: number, ru = true): string {
  if (!t) return '';
  return new Date(t * 1000).toLocaleTimeString(ru ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: !ru,
  });
}

/** Строка «Сегодня · 20:00 Barcelona» из плана. Часовых поясов у обоих сервер не хранит. */
export function planWhen(p: any, ru = true): string {
  const sa = p?.starts_at;
  if (typeof sa === 'number' && isFinite(sa)) {
    const d = new Date(sa * 1000);
    const day = d.toLocaleDateString(ru ? 'ru-RU' : 'en-US', { weekday: 'short', day: 'numeric', month: 'short' });
    const hm = d.toLocaleTimeString(ru ? 'ru-RU' : 'en-US', { hour: '2-digit', minute: '2-digit', hour12: !ru });
    return `${day} · ${hm}`;
  }
  return String(p?.when || '');
}

/** Подпись статуса участника плана — словами, а не кодом состояния. */
export function personStatus(p: any): string {
  if (p?.is_me) return CHAT.youProposed();
  const s = String(p?.status || 'pending');
  if (s === 'confirm' || p?.confirmed) return CHAT.confirmed();
  if (s === 'decline') return CHAT.declinedPlan();
  return CHAT.notAnswered();
}
