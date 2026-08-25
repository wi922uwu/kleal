/**
 * Колода интересов: сорок четыре карточки, каждая со своим лицом.
 *
 * ПОЧЕМУ КАТАЛОГ, А НЕ ТОЛЬКО ПОДСКАЗКИ АГЕНТА. Агент предлагает три-четыре штуки за ход — этого
 * хватало ряду чипов, но колода из четырёх карт заканчивается раньше, чем человек успевает войти
 * во вкус. Каталог даёт запас, по которому можно идти сколько хочется, а подсказки агента встают
 * ПЕРЕД ним: они личные, а каталог общий.
 *
 * ЧТО УХОДИТ В РАЗГОВОР — ПОДПИСЬ, А НЕ КЛЮЧ. Свайп влево равен тому, что человек сам написал бы
 * «бег»: реплика идёт в разговор, а ключ из неё достаёт агент. Поэтому здесь нет ни одного
 * английского ключа — попытка подсунуть его напрямую разошлась бы с тем, как интересы пишутся при
 * обычном ответе словами.
 *
 * ЛИЦО КАРТЫ — ЭТО ПАРА «ЗНАК + ТОН», А НЕ УНИКАЛЬНАЯ ВЁРСТКА. Сорок четыре по-настоящему разных
 * макета невозможно ни нарисовать, ни удержать в порядке: они разъедутся на второй же правке.
 * Зато знак у каждой свой, а тон — один из восьми, и по нему видно, о чём карта, ещё до чтения:
 * зелёные про улицу, тёплые про еду, синие про учёбу. Внутри тона карты всё равно не путаются —
 * их различает знак.
 */
import { T } from './i18n';

/** Имя тона. Сами цвета живут в theme.ts — здесь только выбор. */
export type DeckTone = 'rose' | 'amber' | 'lime' | 'teal' | 'indigo' | 'violet' | 'sand' | 'slate';

export type DeckCard = {
  key: string;
  /** Что уйдёт репликой в разговор, если свайпнуть влево. */
  label: string;
  emoji: string;
  tone: DeckTone;
};

const card = (key: string, ru: string, en: string, emoji: string, tone: DeckTone): DeckCard => ({
  key,
  label: T(ru, en),
  emoji,
  tone,
});

/**
 * Порядок НЕ случайный и НЕ по алфавиту: карты идут вперемешку по темам.
 *
 * Восемь подряд про спорт читаются как анкета в поликлинике — человек устаёт от одной темы и
 * начинает пропускать не глядя. Чередование тем держит внимание: следующая карта всегда про
 * другое, и каждая требует отдельного решения, а не продолжения предыдущего.
 */
export const DECK = (): DeckCard[] => [
  card('run', 'Бег', 'Running', '🏃', 'lime'),
  card('coffee', 'Кофе', 'Coffee', '☕️', 'sand'),
  card('boardgames', 'Настольные игры', 'Board games', '🎲', 'violet'),
  card('hiking', 'Походы', 'Hiking', '🏕', 'teal'),
  card('cinema', 'Кино', 'Cinema', '🎬', 'slate'),
  card('swimming', 'Плавание', 'Swimming', '🏊', 'teal'),
  card('cooking', 'Готовка', 'Cooking', '🍳', 'amber'),
  card('books', 'Книги', 'Books', '📚', 'sand'),
  card('gym', 'Тренажёрный зал', 'The gym', '🏋️', 'slate'),
  card('concerts', 'Концерты', 'Live music', '🎤', 'rose'),
  card('languages', 'Языки', 'Languages', '🗣', 'indigo'),
  card('cycling', 'Велосипед', 'Cycling', '🚴', 'lime'),
  card('wine', 'Вино', 'Wine', '🍷', 'rose'),
  card('museums', 'Музеи', 'Museums', '🏛', 'slate'),
  card('yoga', 'Йога', 'Yoga', '🧘', 'violet'),
  card('breakfast', 'Завтраки', 'Breakfasts', '🥐', 'amber'),
  card('console', 'Приставка', 'Console games', '🎮', 'indigo'),
  card('sea', 'Море', 'The sea', '🌊', 'teal'),
  card('photo', 'Фотография', 'Photography', '📸', 'sand'),
  card('tennis', 'Теннис', 'Tennis', '🎾', 'lime'),
  card('theatre', 'Театр', 'Theatre', '🎭', 'violet'),
  card('markets', 'Рынки', 'Food markets', '🧺', 'amber'),
  card('coding', 'Программирование', 'Coding', '👨‍💻', 'indigo'),
  card('dancing', 'Танцы', 'Dancing', '💃', 'rose'),
  card('mountains', 'Горы', 'Mountains', '🏔', 'teal'),
  card('quiz', 'Квизы', 'Quiz nights', '🧠', 'violet'),
  card('football', 'Футбол', 'Football', '⚽️', 'lime'),
  card('podcasts', 'Подкасты', 'Podcasts', '🎧', 'indigo'),
  card('streetfood', 'Стритфуд', 'Street food', '🌮', 'amber'),
  card('exhibitions', 'Выставки', 'Exhibitions', '🖼', 'slate'),
  card('climbing', 'Скалолазание', 'Climbing', '🧗', 'lime'),
  card('karaoke', 'Караоке', 'Karaoke', '🎙', 'rose'),
  card('citywalks', 'Прогулки по городу', 'City walks', '🚶', 'sand'),
  card('chess', 'Шахматы', 'Chess', '♟️', 'slate'),
  card('picnic', 'Пикник', 'Picnics', '🧃', 'lime'),
  card('series', 'Сериалы', 'Series', '📺', 'indigo'),
  card('billiards', 'Бильярд', 'Pool', '🎱', 'violet'),
  card('spa', 'Спа', 'Spa', '🧖', 'rose'),
  card('camping', 'Кемпинг', 'Camping', '⛺️', 'teal'),
  card('courses', 'Курсы', 'Courses', '🎓', 'indigo'),
  card('bowling', 'Боулинг', 'Bowling', '🎳', 'violet'),
  card('vinyl', 'Винил', 'Vinyl', '🎵', 'sand'),
  card('dogwalks', 'Прогулки с собакой', 'Dog walks', '🐕', 'lime'),
  card('meditation', 'Медитация', 'Meditation', '🌤', 'slate'),
];

/**
 * Колода для шага: сначала подсказки агента, потом каталог.
 *
 * Подсказки приходят строками и своего оформления не имеют — им достаётся розовый тон и звёздочка.
 * Это честно: они и правда особенные, потому что придуманы под конкретного человека, а не выбраны
 * из общего списка.
 *
 * Совпадения выбрасываются по подписи: если агент предложил «Бег», второй такой же карты из
 * каталога быть не должно — человек решит, что его не услышали.
 */
export const deckFor = (suggestions: string[] = []): DeckCard[] => {
  const own = suggestions.filter(Boolean).map((label, i) => ({
    key: `own-${i}`,
    label,
    emoji: '✨',
    tone: 'rose' as DeckTone,
  }));
  const taken = new Set(own.map((c) => c.label.trim().toLowerCase()));
  return [...own, ...DECK().filter((c) => !taken.has(c.label.trim().toLowerCase()))];
};
