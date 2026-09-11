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
 * ЛИЦО КАРТЫ — ЭТО ТОН, А НЕ УНИКАЛЬНАЯ ВЁРСТКА. Сорок четыре по-настоящему разных макета
 * невозможно ни нарисовать, ни удержать в порядке: они разъедутся на второй же правке. Тон — один
 * из восьми, и по нему видно, о чём карта, ещё до чтения: зелёные про улицу, тёплые про еду, синие
 * про учёбу.
 *
 * ЗНАКОВ НА КАРТАХ НЕТ. Эмодзи тут были и ушли: на сорока четырёх карточках подряд они начинают
 * спорить с подписью — глаз цепляется за рисунок и читает слово вторым, а слово и есть ответ,
 * который уйдёт в разговор.
 */
import { T } from './i18n';

/** Имя тона. Сами цвета живут в theme.ts — здесь только выбор. */
export type DeckTone = 'rose' | 'amber' | 'lime' | 'teal' | 'indigo' | 'violet' | 'sand' | 'slate';

export type DeckCard = {
  key: string;
  /** Что уйдёт репликой в разговор, если свайпнуть влево. */
  label: string;
  tone: DeckTone;
};

/** Испанские подписи карточек — по тому же ключу, что уходит в интересы. */
const DECK_ES: Record<string, string> = {
  run: 'Correr', coffee: 'Café', boardgames: 'Juegos de mesa', hiking: 'Senderismo',
  cinema: 'Cine', swimming: 'Natación', cooking: 'Cocinar', books: 'Libros',
  gym: 'El gimnasio', concert: 'Música en directo', languages: 'Idiomas', cycling: 'Ciclismo',
  wine: 'Vino', museum: 'Museos', yoga: 'Yoga', breakfast: 'Desayunos',
  console: 'Videoconsola', sea: 'El mar', photography: 'Fotografía', tennis: 'Tenis',
  theatre: 'Teatro', 'food market': 'Mercados de comida', coding: 'Programar', dancing: 'Bailar',
  mountains: 'Montaña', quiz: 'Quizzes', football: 'Fútbol', podcasts: 'Podcasts',
  streetfood: 'Comida callejera', exhibition: 'Exposiciones', climbing: 'Escalada',
  karaoke: 'Karaoke', walk: 'Paseos por la ciudad', chess: 'Ajedrez', picnic: 'Picnics',
  series: 'Series', billiards: 'Billar', spa: 'Spa', camping: 'Camping', course: 'Cursos',
  bowling: 'Bolos', vinyl: 'Vinilos', dogwalk: 'Pasear al perro', meditation: 'Meditación',
};

const card = (key: string, ru: string, en: string, tone: DeckTone): DeckCard => ({
  key,
  label: T(ru, en, DECK_ES[key]),
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
  card('run', 'Бег', 'Running', 'lime'),
  card('coffee', 'Кофе', 'Coffee', 'sand'),
  card('boardgames', 'Настольные игры', 'Board games', 'violet'),
  card('hiking', 'Походы', 'Hiking', 'teal'),
  card('cinema', 'Кино', 'Cinema', 'slate'),
  card('swimming', 'Плавание', 'Swimming', 'teal'),
  card('cooking', 'Готовка', 'Cooking', 'amber'),
  card('books', 'Книги', 'Books', 'sand'),
  card('gym', 'Тренажёрный зал', 'The gym', 'slate'),
  card('concert', 'Концерты', 'Live music', 'rose'),
  card('languages', 'Языки', 'Languages', 'indigo'),
  card('cycling', 'Велосипед', 'Cycling', 'lime'),
  card('wine', 'Вино', 'Wine', 'rose'),
  card('museum', 'Музеи', 'Museums', 'slate'),
  card('yoga', 'Йога', 'Yoga', 'violet'),
  card('breakfast', 'Завтраки', 'Breakfasts', 'amber'),
  card('console', 'Приставка', 'Console games', 'indigo'),
  card('sea', 'Море', 'The sea', 'teal'),
  card('photography', 'Фотография', 'Photography', 'sand'),
  card('tennis', 'Теннис', 'Tennis', 'lime'),
  card('theatre', 'Театр', 'Theatre', 'violet'),
  card('food market', 'Рынки', 'Food markets', 'amber'),
  card('coding', 'Программирование', 'Coding', 'indigo'),
  card('dancing', 'Танцы', 'Dancing', 'rose'),
  card('mountains', 'Горы', 'Mountains', 'teal'),
  card('quiz', 'Квизы', 'Quiz nights', 'violet'),
  card('football', 'Футбол', 'Football', 'lime'),
  card('podcasts', 'Подкасты', 'Podcasts', 'indigo'),
  card('streetfood', 'Стритфуд', 'Street food', 'amber'),
  card('exhibition', 'Выставки', 'Exhibitions', 'slate'),
  card('climbing', 'Скалолазание', 'Climbing', 'lime'),
  card('karaoke', 'Караоке', 'Karaoke', 'rose'),
  card('walk', 'Прогулки по городу', 'City walks', 'sand'),
  card('chess', 'Шахматы', 'Chess', 'slate'),
  card('picnic', 'Пикник', 'Picnics', 'lime'),
  card('series', 'Сериалы', 'Series', 'indigo'),
  card('billiards', 'Бильярд', 'Pool', 'violet'),
  card('spa', 'Спа', 'Spa', 'rose'),
  card('camping', 'Кемпинг', 'Camping', 'teal'),
  card('course', 'Курсы', 'Courses', 'indigo'),
  card('bowling', 'Боулинг', 'Bowling', 'violet'),
  card('vinyl', 'Винил', 'Vinyl', 'sand'),
  card('dogwalk', 'Прогулки с собакой', 'Dog walks', 'lime'),
  card('meditation', 'Медитация', 'Meditation', 'slate'),
];

/**
 * Колода для шага: сначала подсказки агента, потом каталог.
 *
 * Подсказки приходят строками и своего оформления не имеют — им достаётся розовый тон: он же у
 * действия во всём приложении, и личное предложение выделяется тем, каким цветом светится.
 *
 * ВТОРОЙ СПИСОК — УЖЕ РЕШЁННОЕ. Колода пересобирается после каждого захода: агент отвечает и
 * предлагает новое, а карточки, по которым человек уже провёл пальцем, обязаны исчезнуть — иначе
 * следующий заход начнётся с того же «Бега», по которому только что свайпнули.
 *
 * Совпадения выбрасываются по подписи: если агент предложил «Бег», второй такой же карты из
 * каталога быть не должно — человек решит, что его не услышали.
 */
export const deckFor = (suggestions: string[] = [], done: string[] = []): DeckCard[] => {
  const norm = (s: string) => s.trim().toLowerCase();
  const seen = new Set(done.filter(Boolean).map(norm));

  const own = suggestions
    .filter(Boolean)
    .filter((label) => !seen.has(norm(label)))
    .map((label, i) => ({ key: `own-${i}`, label, tone: 'rose' as DeckTone }));

  own.forEach((c) => seen.add(norm(c.label)));
  return [...own, ...DECK().filter((c) => !seen.has(norm(c.label)))];
};
