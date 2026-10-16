/**
 * Что делает агент — для Kleal в нижней панели (артефакт «Kleal Agent States», 09.10.2026).
 *
 * ДУМАЕТ — пока идёт поиск людей или разбор желания (`agent.match` / `agent.plan` в src/api.ts
 * зовут `beginThinking` / `endThinking`). Счётчик, а не флаг: два поиска подряд не должны гасить
 * друг друга.
 *
 * НОВОЕ — непрочитанные переписки (→ Messages) и входящие приглашения (→ Intents). Источник —
 * сервер: `agent.threads` (поле `unread`) и `agent.homeInvites`. Опрос раз в 30 секунд и при
 * возвращении в приложение. Точка на вкладке гаснет, когда раздел открыли: запоминаем, ЧТО уже
 * видели (подпись набора), и загораемся снова, только если пришло что-то ещё.
 */
import { AppState } from 'react-native';
import { agent } from './api';

export type NewsTab = 'messages' | 'intents';
type News = Record<NewsTab, boolean>;

export { isThinking, onThinking, beginThinking, endThinking, whileThinking } from './thinking';

// ---- новое ----------------------------------------------------------------------------------

let news: News = { messages: false, intents: false };
/** Что сейчас лежит на сервере (подпись набора) и что человек уже видел. */
const current: Record<NewsTab, string> = { messages: '', intents: '' };
const seen: Record<NewsTab, string> = { messages: '', intents: '' };
const newsSubs = new Set<(n: News) => void>();
/** «Пришло новое» — для анимации: Kleal поворачивается к вкладке и подпрыгивает. */
const announceSubs = new Set<(tab: NewsTab) => void>();

export const getNews = () => news;

export function onNews(fn: (n: News) => void): () => void {
  newsSubs.add(fn);
  return () => { newsSubs.delete(fn); };
}

export function onAnnounce(fn: (tab: NewsTab) => void): () => void {
  announceSubs.add(fn);
  return () => { announceSubs.delete(fn); };
}

function publish(tab: NewsTab) {
  const on = !!current[tab] && current[tab] !== seen[tab];
  if (on === news[tab]) return;
  news = { ...news, [tab]: on };
  newsSubs.forEach((f) => f(news));
  if (on) announceSubs.forEach((f) => f(tab));
}

/** Раздел открыт — то, что в нём сейчас, увидено. */
export function markSeen(tab: NewsTab) {
  seen[tab] = current[tab];
  publish(tab);
}

let me = '';
let timer: ReturnType<typeof setInterval> | null = null;
let busy = false;

async function poll() {
  if (!me || busy) return;
  busy = true;
  try {
    const [t, i] = await Promise.all([
      agent.threads(me).catch(() => null),
      agent.homeInvites(me).catch(() => null),
    ]);
    if (t) {
      const sig = ((t as any).threads || [])
        .filter((x: any) => Number(x?.unread || 0) > 0)
        .map((x: any) => `${x.id || x.who}:${x.unread}`)
        .sort().join('|');
      current.messages = sig;
      publish('messages');
    }
    if (i) {
      const sig = ((i as any).invites || [])
        .map((x: any) => String(x?.id || ''))
        .filter(Boolean).sort().join('|');
      current.intents = sig;
      publish('intents');
    }
  } finally {
    busy = false;
  }
}

/** Запустить опрос для этого человека. Повторный вызов с тем же именем ничего не делает. */
export function watchNews(self: string) {
  const name = String(self || '').trim();
  if (!name) return;
  if (name !== me) {
    me = name;
    current.messages = current.intents = seen.messages = seen.intents = '';
    news = { messages: false, intents: false };
    newsSubs.forEach((f) => f(news));
  }
  if (!timer) {
    timer = setInterval(poll, 30_000);
    AppState.addEventListener('change', (s) => { if (s === 'active') poll(); });
  }
  poll();
}
