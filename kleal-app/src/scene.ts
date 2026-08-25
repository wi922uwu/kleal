/**
 * Ветка «помоги разобраться»: разбор хода опросника и сбор ответа.
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ. `app/chat.tsx` — самый большой экран приложения, и складывать в него ещё
 * и разбор второго конверта значило бы окончательно потерять его читаемость. Здесь только формы и
 * правила; ни одного элемента разметки.
 *
 * ОТВЕТ ЧЕЛОВЕКА — ОБЫЧНАЯ РЕПЛИКА. Тап по карточке кладёт в историю её текст, будто он его
 * написал. Отдельного канала для ответов нет намеренно: агент импровизирует по истории, и связная
 * лента ему нужнее, чем поток идентификаторов. Заодно человек в любой момент может перестать
 * тапать и написать словами — обе ветки живут в одной ленте.
 */

/** Виджет сцены. Набор закрытый: что не из него — рисуется карточками. */
export type SceneWidget = 'cards' | 'pair' | 'multi';

export type SceneOption = { id: string; label: string };
export type Scene = { widget: SceneWidget; options: SceneOption[] };

/** Итог опросника: интерес плюс строка «почему», опирающаяся на реальный ответ человека. */
export type Suggestion = { key: string; label: string; why: string };

export type DiscoverTurn = {
  reply: string;
  scene?: Scene;
  suggest?: Suggestion[];
  /** Ход не прошёл серверных сторожей и подменён заготовленной сценой. */
  fallback?: boolean;
};

const WIDGETS: SceneWidget[] = ['cards', 'pair', 'multi'];

/**
 * Конверт сервера -> ход опросника. Всё, что не разобралось, становится `null`: экран тогда
 * показывает реплику как обычный текст, и разговор не ломается.
 */
export function parseTurn(raw: any): DiscoverTurn | null {
  if (!raw || typeof raw !== 'object') return null;
  const reply = String(raw.reply || '').trim();

  const sug = Array.isArray(raw.suggest) ? raw.suggest : null;
  if (sug?.length) {
    const out: Suggestion[] = [];
    for (const it of sug) {
      const key = String(it?.key || '').trim();
      const label = String(it?.label || '').trim() || key;
      const why = String(it?.why || '').trim();
      if (key && why && !out.some((x) => x.key === key)) out.push({ key, label, why });
    }
    if (out.length) return { reply, suggest: out };
  }

  const sc = raw.scene;
  if (sc && typeof sc === 'object' && Array.isArray(sc.options)) {
    const widget: SceneWidget = WIDGETS.includes(sc.widget) ? sc.widget : 'cards';
    const options: SceneOption[] = [];
    for (const o of sc.options) {
      const label = String(o?.label || '').trim();
      if (label && !options.some((x) => x.label === label)) {
        options.push({ id: String(o?.id || `o${options.length + 1}`), label });
      }
    }
    if (options.length >= 2) {
      return { reply, scene: { widget, options }, fallback: !!raw.fallback };
    }
  }
  return reply ? { reply } : null;
}

/**
 * Выбранное -> текст реплики человека. Несколько ответов `multi` склеиваются запятой: агент
 * читает историю как разговор, и «Гулял без цели, Готовил дольше, чем ел» он поймёт, а список
 * идентификаторов — нет.
 */
export function answerText(picked: SceneOption[]): string {
  return picked.map((p) => p.label).join(', ');
}
