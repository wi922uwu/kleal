/**
 * Опрос, который спит, когда на него никто не смотрит.
 *
 * У приложения нет постоянного соединения: и список «Сообщений», и лента переписки, и комната
 * группы просто спрашивают сервер по таймеру. Написан этот таймер везде одинаково —
 * `setInterval` в `useEffect` — и везде с одной и той же дырой: он не останавливается ни когда
 * экран ушёл в стек, ни когда приложение свернули. Открытая однажды переписка продолжала
 * дёргать сервер каждые четыре секунды из кармана, пока телефон лежал экраном вниз.
 *
 * Здесь это исправлено один раз для всех:
 *
 *   — таймер живёт, только пока экран В ФОКУСЕ (`useFocusEffect`) и приложение НА ПЕРЕДНЕМ ПЛАНЕ;
 *   — при возвращении опрос делается СРАЗУ, а не через интервал: человек вернулся посмотреть, что
 *     пришло, и ждать ещё четыре секунды перед первой попыткой — ровно то, за чем он не вернулся;
 *   — свежая `fn` берётся по ссылке. Иначе таймер, созданный один раз, навсегда замкнулся бы на
 *     первый рендер и опрашивал сервер функцией со старыми `me` и `other`.
 */
import { useCallback, useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from 'expo-router';

export function usePolling(fn: () => void, everyMs: number, enabled = true) {
  const latest = useRef(fn);
  latest.current = fn;

  useFocusEffect(
    useCallback(() => {
      if (!enabled) return;
      let timer: ReturnType<typeof setInterval> | undefined;
      const stop = () => { if (timer) { clearInterval(timer); timer = undefined; } };
      const start = () => {
        if (timer) return;
        latest.current();
        timer = setInterval(() => latest.current(), everyMs);
      };
      if (AppState.currentState === 'active') start();
      const sub = AppState.addEventListener('change', (s) => (s === 'active' ? start() : stop()));
      return () => { stop(); sub.remove(); };
    }, [everyMs, enabled])
  );
}

/**
 * Держать ленту прижатой к низу — но только если человек и так внизу.
 *
 * Пять экранов подряд делали `setTimeout(80) → scrollToEnd` на каждое изменение длины ленты, не
 * спрашивая, где человек находится. При опросе раз в четыре секунды чужая реплика выбрасывала
 * читающего старое сообщение обратно вниз, и дочитать переписку было физически невозможно.
 *
 * Восемьдесят миллисекунд — не суеверие: прокрутка идёт ПОСЛЕ того, как новый пузырь получил
 * размер, иначе она уедет к прежнему концу списка.
 */
export function useStickyScroll<T extends { scrollToEnd: (o?: { animated?: boolean }) => void }>(
  ref: React.RefObject<T | null>, dep: unknown, atBottom = true
) {
  useEffect(() => {
    if (!atBottom) return;
    const id = setTimeout(() => ref.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [ref, dep, atBottom]);
}
