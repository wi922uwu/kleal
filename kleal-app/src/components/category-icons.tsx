/**
 * Иконки категорий для колеса интересов.
 *
 * ПОЧЕМУ КОНТУРАМИ, А НЕ КАРТИНКАМИ И НЕ ЭМОДЗИ.
 *
 * Эмодзи стояли здесь первыми и выглядели чужеродно: у каждой платформы своя рисовка, свой вес и
 * своя палитра, поэтому ряд на кольце получался разноцветной мозаикой, которую не подчинить теме.
 * Загружать набор с CDN тоже нельзя — приложение обязано открываться без сети, а бандл не должен
 * зависеть от чужого хостинга. Поэтому то же решение, что и в icons.tsx: геометрия прямо в коде.
 *
 * Геометрия — по мотивам Lucide (lucide.dev, лицензия ISC, свободна в том числе для коммерческого
 * использования), приведённая к сетке 24×24 и толщине штриха проекта. Атрибуция — docs/IMAGE_CREDITS.
 *
 * ФОРМА ЭКСПОРТА. Каждая иконка возвращает <G> с содержимым в координатах 24×24 — БЕЗ обёртки <Svg>.
 * Колесо вставляет её внутрь своего единственного <Svg> и само ставит на место трансформацией
 * (translate → rotate → scale). Отдельный <Svg> на каждую иконку дал бы 24 вложенных полотна на
 * кольцо, а это уже заметно на слабом телефоне.
 */
import React from 'react';
import { G, Path, Circle, Line, Rect } from 'react-native-svg';

type IconFn = (c: string) => React.ReactElement;

/** Общие штриховые атрибуты — задаются на группе, дети их наследуют. */
const g = (children: React.ReactNode, c: string) => (
  <G fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    {children}
  </G>
);

export const CATEGORY_ICON: Record<string, IconFn> = {
  // ---- спорт и тело
  sport: (c) => g(<>
    <Circle cx={12} cy={12} r={8.5} />
    <Path d="M12 3.5 14.8 8 12 12 9.2 8Z" />
    <Path d="M4.2 9.5 9.2 8M19.8 9.5 14.8 8M7 19l2.4-5M17 19l-2.4-5M9.4 14h5.2" />
  </>, c),
  fitness: (c) => g(<>
    <Path d="M6.5 9v6M17.5 9v6M4 10.5v3M20 10.5v3M9 12h6" />
  </>, c),
  mindbody: (c) => g(<>
    <Circle cx={12} cy={5} r={2} />
    <Path d="M12 8v5M12 13 8 20M12 13l4 7M6 10.5l6 1.2 6-1.2" />
  </>, c),

  // ---- игры
  boardgames: (c) => g(<>
    <Rect x={3} y={3} width={12} height={12} rx={2} />
    <Path d="M9 15v4a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-4" />
    <Circle cx={7} cy={7} r={1.1} fill={c} stroke="none" />
    <Circle cx={11} cy={11} r={1.1} fill={c} stroke="none" />
    <Circle cx={17} cy={17} r={1.1} fill={c} stroke="none" />
  </>, c),
  gaming: (c) => g(<>
    <Path d="M7.5 8h9a5 5 0 0 1 4.6 6.9l-1 2.4a2.2 2.2 0 0 1-3.8.5L15 16H9l-1.3 1.8a2.2 2.2 0 0 1-3.8-.5l-1-2.4A5 5 0 0 1 7.5 8Z" />
    <Path d="M7 11v2.4M5.8 12.2h2.4M16 11.6h.01M18 13.4h.01" />
  </>, c),

  // ---- еда и вечер
  coffee: (c) => g(<>
    <Path d="M4 8h13v5.5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V8Z" />
    <Path d="M17 9.5h1.6a2.4 2.4 0 0 1 0 4.8H17" />
    <Path d="M7.5 3.5c0 1-.9 1.3-.9 2.2M11 3.5c0 1-.9 1.3-.9 2.2M14.5 3.5c0 1-.9 1.3-.9 2.2" />
  </>, c),
  dining: (c) => g(<>
    <Path d="M6 3v8M6 11v10M4 3v4.5a2 2 0 0 0 4 0V3" />
    <Path d="M17 3c-2 1.5-2.6 4-2.6 6.2 0 1.6.9 2.4 2.6 2.6V21" />
  </>, c),
  nightlife: (c) => g(<>
    <Path d="M4.5 4.5h15L12 13Z" />
    <Path d="M12 13v6M8.5 19h7" />
  </>, c),
  wellness: (c) => g(<>
    <Path d="M12 20c-4 0-7-2.6-7-6 3 0 5 1 7 3 2-2 4-3 7-3 0 3.4-3 6-7 6Z" />
    <Path d="M12 17c0-4 1.5-7 4-9M12 17c0-4-1.5-7-4-9" />
  </>, c),

  // ---- культура
  cinema: (c) => g(<>
    <Rect x={3} y={6} width={18} height={13} rx={2} />
    <Path d="M3 10h18M7.5 6 6 10M12 6l-1.5 4M16.5 6 15 10" />
  </>, c),
  anime: (c) => g(<>
    <Circle cx={12} cy={12} r={8.5} />
    <Path d="M8.5 10.5c.6-1 1.7-1 2.3 0M13.2 10.5c.6-1 1.7-1 2.3 0" />
    <Path d="M9 15.2c1.8 1.2 4.2 1.2 6 0" />
  </>, c),
  visualart: (c) => g(<>
    <Path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.2 0 1.8-.8 1.8-1.7 0-1.4-1-1.7-1-2.7 0-.8.7-1.4 1.6-1.4h1.4A4.7 4.7 0 0 0 20.5 10c0-3.6-3.8-6.5-8.5-6.5Z" />
    <Circle cx={8} cy={10} r={1.1} fill={c} stroke="none" />
    <Circle cx={12} cy={7.6} r={1.1} fill={c} stroke="none" />
    <Circle cx={15.8} cy={9.6} r={1.1} fill={c} stroke="none" />
  </>, c),
  stage: (c) => g(<>
    <Path d="M4 4h7v6.5a3.5 3.5 0 0 1-7 0Z" />
    <Path d="M13 4h7v6.5a3.5 3.5 0 0 1-7 0Z" />
    <Path d="M7.5 14.5V20M16.5 14.5V20M4.5 20h6M13.5 20h6" />
  </>, c),
  books: (c) => g(<>
    <Path d="M4 4.5h5.5A2.5 2.5 0 0 1 12 7v12a2 2 0 0 0-2-2H4Z" />
    <Path d="M20 4.5h-5.5A2.5 2.5 0 0 0 12 7v12a2 2 0 0 1 2-2h6Z" />
  </>, c),
  crafts: (c) => g(<>
    <Circle cx={6.5} cy={7} r={2.5} />
    <Circle cx={6.5} cy={17} r={2.5} />
    <Path d="M8.7 8.4 20 17M8.7 15.6 20 7M11 12h.01" />
  </>, c),
  writing: (c) => g(<>
    <Path d="M4 20l1-4.2L16.2 4.6a2 2 0 0 1 2.8 2.8L7.8 18.6 4 20Z" />
    <Path d="M14.5 6.5 17.5 9.5" />
  </>, c),
  history: (c) => g(<>
    <Path d="M4 20h16M5.5 20V10M9.5 20V10M14.5 20V10M18.5 20V10" />
    <Path d="M3.5 10h17L12 4Z" />
  </>, c),

  // ---- музыка
  music: (c) => g(<>
    <Path d="M9 18V6.5l10-2V16" />
    <Circle cx={6.5} cy={18} r={2.5} />
    <Circle cx={16.5} cy={16} r={2.5} />
  </>, c),
  makingmusic: (c) => g(<>
    <Path d="M6 20a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
    <Path d="M9 17V7a3 3 0 0 1 3-3c3.5 0 3 4 6.5 4" />
    <Path d="M9 10.5c3.5 0 3-3.5 6.5-3.5" />
  </>, c),
  dance: (c) => g(<>
    <Circle cx={13} cy={4.5} r={2} />
    <Path d="M13 7v4l3.5 2M13 11l-3 3 1 6M10 14l-4 1" />
  </>, c),

  // ---- природа
  outdoors: (c) => g(<>
    <Path d="M12 3 5 13h3.5L4 20h16l-4.5-7H19Z" />
    <Path d="M12 20v-3" />
  </>, c),
  watersnow: (c) => g(<>
    <Path d="M3 16.5c1.8 0 1.8 1.6 3.6 1.6s1.8-1.6 3.6-1.6 1.8 1.6 3.6 1.6 1.8-1.6 3.6-1.6 1.8 1.6 3.6 1.6" />
    <Path d="M3 20.5c1.8 0 1.8 1.6 3.6 1.6" />
    <Path d="M12 3v9M8.5 5.5 12 3l3.5 2.5M8 9.5l4-2 4 2" />
  </>, c),
  travel: (c) => g(<>
    <Path d="M4 14.5 20 9.5M6 11l-2-4 2-.5 3.5 3M8.5 18l1.5-3.5M6.5 20l1.5-1M18 8.5c1.6-.5 2.6-.2 2.8.7.2.9-.6 1.6-2.2 2.1" />
    <Path d="M11 12.8 9 6.5l1.8-.5 4.4 5.3" />
  </>, c),
  nature: (c) => g(<>
    <Path d="M12 21v-8" />
    <Path d="M12 13c0-3.3 2.7-6 6-6 0 3.3-2.7 6-6 6Z" />
    <Path d="M12 16c0-3-2.4-5.4-5.4-5.4 0 3 2.4 5.4 5.4 5.4Z" />
  </>, c),
  adventure: (c) => g(<>
    <Path d="M3.5 9.5 12 4l8.5 5.5" />
    <Path d="M12 4v7M6 11l6 9 6-9" />
  </>, c),

  // ---- дело
  coding: (c) => g(<>
    <Path d="M8.5 8 4 12l4.5 4M15.5 8 20 12l-4.5 4M13.5 5.5l-3 13" />
  </>, c),
  startups: (c) => g(<>
    <Path d="M12 3c3.5 2.2 5.5 5.8 5.5 9.5L14 16h-4l-3.5-3.5C6.5 8.8 8.5 5.2 12 3Z" />
    <Circle cx={12} cy={10} r={2} />
    <Path d="M9 17c-1.5 1-2 2.5-2 4 1.5 0 3-.5 4-2M15 17c1.5 1 2 2.5 2 4-1.5 0-3-.5-4-2" />
  </>, c),
  design: (c) => g(<>
    <Circle cx={12} cy={12} r={8.5} />
    <Circle cx={12} cy={12} r={3} />
    <Path d="M12 3.5v5M12 15.5v5M3.5 12h5M15.5 12h5" />
  </>, c),
  crypto: (c) => g(<>
    <Circle cx={12} cy={12} r={8.5} />
    <Path d="M9.5 8h4a2.2 2.2 0 0 1 0 4.4h-4h4.4a2.2 2.2 0 0 1 0 4.4H9.5" />
    <Path d="M9.5 8V16.8M11.2 6.2v1.8M13.2 6.2v1.8M11.2 16.8v1.8M13.2 16.8v1.8" />
  </>, c),
  career: (c) => g(<>
    <Rect x={3} y={7.5} width={18} height={12} rx={2} />
    <Path d="M9 7.5V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1.5M3 12.5h18M12 12v2" />
  </>, c),

  // ---- люди и учёба
  languages: (c) => g(<>
    <Circle cx={12} cy={12} r={8.5} />
    <Path d="M3.5 12h17M12 3.5c2.2 2.4 3.4 5.4 3.4 8.5S14.2 18.1 12 20.5c-2.2-2.4-3.4-5.4-3.4-8.5S9.8 5.9 12 3.5Z" />
  </>, c),
  learning: (c) => g(<>
    <Path d="M12 4 2.5 8.5 12 13l9.5-4.5Z" />
    <Path d="M6.5 10.8V16c0 1.4 2.5 2.6 5.5 2.6s5.5-1.2 5.5-2.6v-5.2M21.5 8.5V14" />
  </>, c),
  pets: (c) => g(<>
    <Circle cx={7} cy={9} r={2} />
    <Circle cx={17} cy={9} r={2} />
    <Circle cx={9.5} cy={5.5} r={1.8} />
    <Circle cx={14.5} cy={5.5} r={1.8} />
    <Path d="M12 11c2.8 0 5 2.2 5 4.6 0 2-1.6 3.4-3.6 3.4h-2.8C8.6 19 7 17.6 7 15.6 7 13.2 9.2 11 12 11Z" />
  </>, c),
  community: (c) => g(<>
    <Circle cx={9} cy={8} r={3} />
    <Path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
    <Path d="M16 5.5a3 3 0 0 1 0 5.8M17.5 19a5.6 5.6 0 0 0-2.2-4.4" />
  </>, c),
  family: (c) => g(<>
    <Circle cx={8} cy={7} r={2.6} />
    <Circle cx={16.5} cy={8} r={2.2} />
    <Circle cx={12.5} cy={14.5} r={1.8} />
    <Path d="M3.5 18a4.8 4.8 0 0 1 9 0M14 18a3.6 3.6 0 0 1 6.6-2M9.8 20.5a3 3 0 0 1 5.4 0" />
  </>, c),
  walks: (c) => g(<>
    <Circle cx={13} cy={4.5} r={2} />
    <Path d="M13 7l-2 4.5 3 2 1 6.5M11 11.5 7.5 14l-.5 5M14 9.5l3.5 1.5" />
  </>, c),
  // ---- второй уровень: подкатегории
  racket: (c) => g(<>
    <Path d="M9.5 3.2c3.4-1.4 6.9.4 7.9 3.9 1 3.5-1 7.2-4.4 8.6s-6.9-.4-7.9-3.9 1-7.2 4.4-8.6Z" />
    <Path d="M6.6 13.4 4 16M4 16l-1.2 3.6a1.6 1.6 0 0 0 2 2L8.4 20.4M4 16l4.4 4.4" />
  </>, c),
  running: (c) => g(<>
    <Circle cx={15.5} cy={4.5} r={2} />
    <Path d="M14 7.5 10.5 10l1.5 3.5 3 1.5.5 5M12 13.5 8 16l-2.5-1M14 9.5l4 1.5.5 3" />
  </>, c),
  console: (c) => g(<>
    <Rect x={3} y={7} width={7.5} height={13} rx={2.6} />
    <Rect x={13.5} y={7} width={7.5} height={13} rx={2.6} />
    <Path d="M6.8 11v2.6M5.5 12.3h2.6M16.6 12h.01M18.4 14h.01M10.5 12h3" />
  </>, c),
  pc: (c) => g(<>
    <Rect x={2.5} y={4.5} width={19} height={12} rx={2} />
    <Path d="M8.5 20h7M12 16.5V20" />
  </>, c),
  mobile: (c) => g(<>
    <Rect x={6.5} y={2.5} width={11} height={19} rx={2.6} />
    <Path d="M10.5 5.5h3M12 18.5h.01" />
  </>, c),
  genres: (c) => g(<>
    <Path d="M4 14v4M8 10v8M12 5v13M16 9v9M20 12.5v5.5" />
  </>, c),
  electronic: (c) => g(<>
    <Rect x={2.5} y={5.5} width={19} height={13} rx={2} />
    <Circle cx={8} cy={12} r={2.6} />
    <Path d="M14 9.5h4.5M14 12h4.5M14 14.5h4.5M8 9.4v1.2" />
  </>, c),
  growth: (c) => g(<>
    <Path d="M3.5 17.5 9 12l3.5 3.5L20.5 7" />
    <Path d="M15.5 7h5v5" />
  </>, c),
  science: (c) => g(<>
    <Path d="M9.5 3v6.2L4.6 17.4A2 2 0 0 0 6.3 20.5h11.4a2 2 0 0 0 1.7-3.1L14.5 9.2V3" />
    <Path d="M8 3h8M7.4 14h9.2" />
  </>, c),
  speaking: (c) => g(<>
    <Path d="M3.5 9.5v5M7 8.5 15 4.5v15L7 15.5Z" />
    <Path d="M18.5 9c1.3 1.6 1.3 4.4 0 6M8.5 16v3.5" />
  </>, c),
};
/**
 * Иконка по ключу УЗЛА дерева — для второго кольца.
 *
 * Карта, а не поле в дереве: interests-wheel.ts — это данные (ключи, по которым ищет матчинг), и
 * иконка там была бы оформлением в файле, где оформления быть не должно. Сорок шесть подкатегорий
 * получают значок отсюда, ничего не зная о нём.
 *
 * Третий уровень намеренно НЕ покрыт: там уже не категории, а конкретные вещи — «Падел», «Джаз»,
 * «Катан», — и рисовать значок каждой из двухсот семидесяти значило бы либо врать формой, либо
 * получить ряд одинаковых кружков. Их называет подпись под колесом.
 */
const SUB_ICON: Record<string, string> = {
  // спорт
  team: 'sport', racket: 'racket', endurance: 'running', strength: 'fitness', mindbody: 'mindbody',
  // общение
  coffee: 'coffee', dining: 'dining', nightlife: 'nightlife', casual: 'walks',
  wellness: 'wellness', community: 'community', pets: 'pets', family: 'family',
  // игры
  tabletop: 'boardgames', esports: 'gaming', console: 'console', pc: 'pc', mobilegaming: 'mobile',
  // культура
  screen: 'cinema', anime: 'anime', visual: 'visualart', stage: 'stage',
  reading: 'books', craft: 'crafts', writing: 'writing', history: 'history',
  // музыка
  listening: 'music', making: 'makingmusic', genres: 'genres', electronic: 'electronic', dance: 'dance',
  // природа
  hiking: 'outdoors', watersnow: 'watersnow', travel: 'travel', naturelife: 'nature', adventure: 'adventure',
  // дело
  engineering: 'coding', startups: 'startups', design: 'design', web3: 'crypto',
  career: 'career', growth: 'growth',
  // учёба
  language: 'languages', skills: 'learning', academic: 'science', personal: 'speaking',
};

/** Есть ли у этого узла значок вообще. Нет — кольцо рисует точку, а не выдуманную форму. */
export const iconNameFor = (nodeKey: string, own?: string): string =>
  own || SUB_ICON[nodeKey] || '';

/** Иконка по ключу категории; неизвестный ключ рисуется точкой — врать формой нельзя. */
export const categoryIcon = (key: string, c: string): React.ReactElement =>
  (CATEGORY_ICON[key] || ((cc: string) => g(<Circle cx={12} cy={12} r={3.2} fill={cc} stroke="none" />, cc)))(c);
