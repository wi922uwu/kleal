/**
 * «Агент думает» — пока идёт поиск (agent.match / agent.plan). Отдельный модуль без зависимостей:
 * его зовёт src/api.ts, а src/agentState.ts зовёт api — общий модуль замкнул бы их в кольцо.
 */
let thinking = 0;
const thinkSubs = new Set<(on: boolean) => void>();

export const isThinking = () => thinking > 0;

export function onThinking(fn: (on: boolean) => void): () => void {
  thinkSubs.add(fn);
  return () => { thinkSubs.delete(fn); };
}

export function beginThinking() {
  thinking += 1;
  if (thinking === 1) thinkSubs.forEach((f) => f(true));
}

export function endThinking() {
  if (thinking === 0) return;
  thinking -= 1;
  if (thinking === 0) thinkSubs.forEach((f) => f(false));
}

/** Обёртка для запроса: «думает», пока обещание не закончилось — чем бы ни закончилось. */
export function whileThinking<T>(p: Promise<T>): Promise<T> {
  beginThinking();
  return p.finally(endThinking);
}
