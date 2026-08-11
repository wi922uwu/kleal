/**
 * Дерево интересов для колеса на шаге A.08 — данные и правила, БЕЗ вида.
 *
 * Колесо ступенчатое, как шифровальный диск: внешнее кольцо — восемь широких областей, каждое
 * следующее к центру уточняет выбранное. Остановиться можно на любом уровне: «Спорт» — законный
 * интерес, «Спорт → Ракетки → Падел» — просто более точный.
 *
 * ВОСЕМЬ КОРНЕЙ, А НЕ ТРИДЦАТЬ СЕМЬ (решение Ивана, 2026-08-10). Широкое первое кольцо пробовали:
 * тридцать семь секций дают сегмент в десять градусов, значок в нём — тринадцать пикселей, и ряд
 * читается как рябь. Первое касание должно предлагать выбор из немногого, а подробности приходить
 * по мере углубления — их тут больше трёхсот, и все они на месте, просто уровнем ниже.
 *
 * КЛЮЧИ ВЗЯТЫ ИЗ СЕРВЕРНОЙ ТАКСОНОМИИ, а не придуманы. Восемь корней — это ровно её восемь
 * разделов (TAXONOMY в services/matching/app.py: sports, social, games, culture, tech, music,
 * outdoors, learning), второй уровень — её подгруппы, листья — её слова. Ранжирование сравнивает
 * ключи БУКВАЛЬНО, поэтому выдуманное слово означало бы интерес, по которому человека не найдёт
 * никто. Подписи для глаз живут рядом и переводятся через T().
 *
 * В профиль уходит ЛИСТ + РОДИТЕЛИ (решение Ивана, 2026-08-10): выбравшего падел находят и те,
 * кто искал просто «спорт». В затравку разговора при этом идут только самые точные ключи —
 * расспрашивать «чем тебе нравится спорт» после «падел» значило бы не услышать ответа.
 */
import { T } from './i18n';

export type WheelNode = {
  /** Канонический английский ключ — то, что ложится в interests и по чему ищет матчинг. */
  key: string;
  ru: string;
  en: string;
  /** Только у первого уровня — имя контурной иконки из components/category-icons. */
  icon?: string;
  kids?: WheelNode[];
};

const N = (key: string, ru: string, en: string, kids?: WheelNode[]): WheelNode => ({ key, ru, en, kids });
const TOP = (key: string, ru: string, en: string, icon: string, kids: WheelNode[]): WheelNode =>
  ({ key, ru, en, icon, kids });

export const WHEEL_TREE: WheelNode[] = [
  // ------------------------------------------------------------------ 1. спорт
  TOP('sports', 'Спорт', 'Sport', 'sport', [
    N('team', 'Командный', 'Team', [
      N('football', 'Футбол', 'Football'),
      N('basketball', 'Баскетбол', 'Basketball'),
      N('volleyball', 'Волейбол', 'Volleyball'),
      N('futsal', 'Мини-футбол', 'Futsal'),
      N('handball', 'Гандбол', 'Handball'),
      N('rugby', 'Регби', 'Rugby'),
      N('hockey', 'Хоккей', 'Hockey'),
    ]),
    N('racket', 'Ракетки', 'Racquets', [
      N('padel', 'Падел', 'Padel'),
      N('tennis', 'Теннис', 'Tennis'),
      N('badminton', 'Бадминтон', 'Badminton'),
      N('squash', 'Сквош', 'Squash'),
      N('pingpong', 'Настольный теннис', 'Ping-pong'),
      N('pickleball', 'Пиклбол', 'Pickleball'),
    ]),
    N('endurance', 'Выносливость', 'Endurance', [
      N('running', 'Бег', 'Running'),
      N('cycling', 'Вело', 'Cycling'),
      N('swimming', 'Плавание', 'Swimming'),
      N('triathlon', 'Триатлон', 'Triathlon'),
      N('marathon', 'Марафон', 'Marathon'),
      N('rowing', 'Гребля', 'Rowing'),
    ]),
    N('strength', 'Зал и сила', 'Gym & strength', [
      N('gym', 'Зал', 'Gym'),
      N('crossfit', 'Кроссфит', 'CrossFit'),
      N('calisthenics', 'Турники', 'Calisthenics'),
      N('powerlifting', 'Пауэрлифтинг', 'Powerlifting'),
      N('boxing', 'Бокс', 'Boxing'),
      N('mma', 'ММА', 'MMA'),
      N('bjj', 'Джиу-джитсу', 'BJJ'),
      N('climbing', 'Скалолазание', 'Climbing'),
      N('bouldering', 'Боулдеринг', 'Bouldering'),
    ]),
    N('mindbody', 'Тело и практики', 'Body & practice', [
      N('yoga', 'Йога', 'Yoga'),
      N('pilates', 'Пилатес', 'Pilates'),
      N('meditation', 'Медитация', 'Meditation'),
      N('breathwork', 'Дыхание', 'Breathwork'),
      N('stretching', 'Растяжка', 'Stretching'),
      N('taichi', 'Тайцзи', 'Tai chi'),
    ]),
  ]),

  // ------------------------------------------------------------------ 2. общение
  TOP('social', 'Общение', 'Social', 'coffee', [
    N('coffee', 'Кофе', 'Coffee', [
      N('cafe', 'По кофейням', 'Cafe hopping'),
      N('espresso', 'Эспрессо', 'Espresso'),
      N('matcha', 'Матча', 'Matcha'),
      N('tea', 'Чай', 'Tea'),
      N('brunch', 'Бранчи', 'Brunch'),
    ]),
    N('dining', 'Поесть', 'Eating out', [
      N('dinner', 'Ужины', 'Dinners'),
      N('restaurant', 'Рестораны', 'Restaurants'),
      N('cooking', 'Готовка', 'Cooking'),
      N('baking', 'Выпечка', 'Baking'),
      N('tapas', 'Тапас', 'Tapas'),
      N('sushi', 'Суши', 'Sushi'),
      N('ramen', 'Рамен', 'Ramen'),
      N('vegan', 'Веган', 'Vegan'),
      N('streetfood', 'Стритфуд', 'Street food'),
    ]),
    N('nightlife', 'Ночная жизнь', 'Nightlife', [
      N('bar', 'Бары', 'Bars'),
      N('wine', 'Вино', 'Wine'),
      N('beer', 'Пиво', 'Beer'),
      N('cocktails', 'Коктейли', 'Cocktails'),
      N('club', 'Клубы', 'Clubs'),
      N('party', 'Вечеринки', 'Parties'),
    ]),
    N('casual', 'Просто погулять', 'Just hang out', [
      N('walk', 'Прогулки', 'Walks'),
      N('park', 'Парки', 'Parks'),
      N('terrace', 'Террасы', 'Terraces'),
      N('picnic', 'Пикники', 'Picnics'),
      N('hangout', 'Поболтать', 'Hang out'),
    ]),
    N('wellness', 'Спа и забота', 'Spa & self-care', [
      N('spa', 'Спа', 'Spa'),
      N('sauna', 'Сауна', 'Sauna'),
      N('massage', 'Массаж', 'Massage'),
      N('selfcare', 'Забота о себе', 'Self-care'),
    ]),
    N('community', 'Волонтёрство', 'Volunteering', [
      N('volunteering', 'Помогать', 'Volunteering'),
      N('charity', 'Благотворительность', 'Charity'),
      N('sustainability', 'Экология', 'Sustainability'),
      N('activism', 'Активизм', 'Activism'),
      N('meetup', 'Митапы', 'Meetups'),
    ]),
    N('pets', 'Питомцы', 'Pets', [
      N('dogs', 'Собаки', 'Dogs'),
      N('dogwalk', 'Выгул вместе', 'Dog walks'),
      N('cats', 'Кошки', 'Cats'),
    ]),
    N('family', 'Семья и дети', 'Family & kids', [
      N('parenting', 'Родительство', 'Parenting'),
      N('kids', 'С детьми', 'With kids'),
      N('playdate', 'Плейдейты', 'Playdates'),
    ]),
  ]),

  // ------------------------------------------------------------------ 3. игры
  TOP('games', 'Игры', 'Games', 'gaming', [
    N('tabletop', 'Настолки', 'Board games', [
      N('boardgames', 'Настольные', 'Board games'),
      N('chess', 'Шахматы', 'Chess'),
      N('poker', 'Покер', 'Poker'),
      N('dnd', 'Ролевые', 'Tabletop RPG'),
      N('catan', 'Катан', 'Catan'),
      N('magic', 'Magic', 'Magic'),
      N('warhammer', 'Warhammer', 'Warhammer'),
      N('backgammon', 'Нарды', 'Backgammon'),
      N('trivia', 'Квизы', 'Trivia'),
      N('escaperoom', 'Квесты', 'Escape rooms'),
    ]),
    N('esports', 'Киберспорт', 'Esports', [
      N('dota', 'Dota', 'Dota'),
      N('cs', 'CS', 'CS'),
      N('valorant', 'Valorant', 'Valorant'),
      N('league', 'League of Legends', 'League of Legends'),
      N('apex', 'Apex', 'Apex'),
      N('overwatch', 'Overwatch', 'Overwatch'),
      N('rocketleague', 'Rocket League', 'Rocket League'),
      N('fifa', 'FIFA', 'FIFA'),
    ]),
    N('console', 'Консоли', 'Console', [
      N('playstation', 'PlayStation', 'PlayStation'),
      N('xbox', 'Xbox', 'Xbox'),
      N('nintendo', 'Nintendo', 'Nintendo'),
    ]),
    N('pc', 'PC', 'PC', [
      N('minecraft', 'Minecraft', 'Minecraft'),
      N('stardew', 'Stardew Valley', 'Stardew Valley'),
      N('valheim', 'Valheim', 'Valheim'),
      N('terraria', 'Terraria', 'Terraria'),
    ]),
    N('mobilegaming', 'Мобильные', 'Mobile', [
      N('pubg', 'PUBG', 'PUBG'),
      N('genshin', 'Genshin', 'Genshin'),
      N('clashroyale', 'Clash Royale', 'Clash Royale'),
    ]),
  ]),

  // ------------------------------------------------------------------ 4. культура
  TOP('culture', 'Культура', 'Culture', 'stage', [
    N('screen', 'Кино и сериалы', 'Films & series', [
      N('cinema', 'Кино', 'Films'),
      N('series', 'Сериалы', 'Series'),
      N('documentary', 'Документальное', 'Documentary'),
      N('sitcom', 'Ситкомы', 'Sitcoms'),
      N('marvel', 'Marvel', 'Marvel'),
    ]),
    N('anime', 'Аниме и Азия', 'Anime & Asia', [
      N('manga', 'Манга', 'Manga'),
      N('kdrama', 'К-дорамы', 'K-drama'),
      N('kpop', 'K-pop', 'K-pop'),
      N('cosplay', 'Косплей', 'Cosplay'),
    ]),
    N('visual', 'Искусство', 'Art', [
      N('museum', 'Музеи', 'Museums'),
      N('gallery', 'Галереи', 'Galleries'),
      N('exhibition', 'Выставки', 'Exhibitions'),
      N('photography', 'Фотография', 'Photography'),
      N('painting', 'Живопись', 'Painting'),
      N('sketching', 'Скетчинг', 'Sketching'),
      N('streetart', 'Стритарт', 'Street art'),
    ]),
    N('stage', 'Сцена', 'Stage', [
      N('standup', 'Стендап', 'Stand-up'),
      N('improv', 'Импров', 'Improv'),
      N('theatre', 'Театр', 'Theatre'),
      N('opera', 'Опера', 'Opera'),
      N('ballet', 'Балет', 'Ballet'),
      N('musical', 'Мюзиклы', 'Musicals'),
    ]),
    N('reading', 'Книги', 'Books', [
      N('books', 'Читать', 'Reading'),
      N('bookclub', 'Книжный клуб', 'Book club'),
      N('scifi', 'Фантастика', 'Sci-fi'),
      N('fantasy', 'Фэнтези', 'Fantasy'),
      N('nonfiction', 'Нон-фикшн', 'Non-fiction'),
      N('literature', 'Классика', 'Literature'),
    ]),
    N('craft', 'Рукоделие', 'Craft', [
      N('pottery', 'Керамика', 'Pottery'),
      N('knitting', 'Вязание', 'Knitting'),
      N('sewing', 'Шитьё', 'Sewing'),
      N('woodworking', 'Дерево', 'Woodworking'),
      N('calligraphy', 'Каллиграфия', 'Calligraphy'),
      N('diy', 'Своими руками', 'DIY'),
    ]),
    N('writing', 'Тексты', 'Writing', [
      N('poetry', 'Поэзия', 'Poetry'),
      N('journaling', 'Дневник', 'Journaling'),
      N('blogging', 'Блог', 'Blogging'),
    ]),
    N('history', 'История и город', 'History & city', [
      N('heritage', 'Наследие', 'Heritage'),
      N('archaeology', 'Археология', 'Archaeology'),
      N('architecture', 'Архитектура', 'Architecture'),
      N('urbanism', 'Урбанистика', 'Urbanism'),
    ]),
  ]),

  // ------------------------------------------------------------------ 5. музыка
  TOP('music', 'Музыка', 'Music', 'music', [
    N('listening', 'Концерты', 'Live music', [
      N('concert', 'Концерты', 'Concerts'),
      N('festival', 'Фестивали', 'Festivals'),
      N('gig', 'Небольшие площадки', 'Small gigs'),
      N('vinyl', 'Винил', 'Vinyl'),
      N('livemusic', 'Живая музыка', 'Live music'),
    ]),
    N('making', 'Играю сам', 'I play', [
      N('guitar', 'Гитара', 'Guitar'),
      N('piano', 'Пианино', 'Piano'),
      N('drums', 'Барабаны', 'Drums'),
      N('bass', 'Бас', 'Bass'),
      N('singing', 'Вокал', 'Singing'),
      N('dj', 'Диджеинг', 'DJing'),
      N('producing', 'Продакшн', 'Producing'),
      N('band', 'Группа', 'Band'),
      N('karaoke', 'Караоке', 'Karaoke'),
    ]),
    N('genres', 'Жанры', 'Genres', [
      N('indie', 'Инди', 'Indie'),
      N('rock', 'Рок', 'Rock'),
      N('jazz', 'Джаз', 'Jazz'),
      N('hiphop', 'Хип-хоп', 'Hip-hop'),
      N('classical', 'Классика', 'Classical'),
      N('metal', 'Метал', 'Metal'),
      N('funk', 'Фанк', 'Funk'),
      N('soul', 'Соул', 'Soul'),
    ]),
    N('electronic', 'Электроника', 'Electronic', [
      N('techno', 'Техно', 'Techno'),
      N('house', 'Хаус', 'House'),
      N('rave', 'Рейвы', 'Raves'),
      N('edm', 'EDM', 'EDM'),
    ]),
    N('dance', 'Танцы', 'Dance', [
      N('salsa', 'Сальса', 'Salsa'),
      N('bachata', 'Бачата', 'Bachata'),
      N('tango', 'Танго', 'Tango'),
      N('swing', 'Свинг', 'Swing'),
      N('ballroom', 'Бальные', 'Ballroom'),
      N('zumba', 'Зумба', 'Zumba'),
    ]),
  ]),

  // ------------------------------------------------------------------ 6. природа
  TOP('outdoors', 'Природа', 'Outdoors', 'outdoors', [
    N('hiking', 'Походы', 'Hiking', [
      N('trekking', 'Треккинг', 'Trekking'),
      N('mountains', 'Горы', 'Mountains'),
      N('trail', 'Тропы', 'Trails'),
      N('camping', 'Кемпинг', 'Camping'),
      N('backpacking', 'С рюкзаком', 'Backpacking'),
      N('trailrunning', 'Трейлраннинг', 'Trail running'),
    ]),
    N('watersnow', 'Вода и снег', 'Water & snow', [
      N('surfing', 'Сёрфинг', 'Surfing'),
      N('kayaking', 'Каяк', 'Kayaking'),
      N('sup', 'Сапборд', 'Paddleboard'),
      N('kitesurf', 'Кайт', 'Kitesurf'),
      N('scuba', 'Дайвинг', 'Scuba'),
      N('snorkeling', 'Снорклинг', 'Snorkeling'),
      N('skiing', 'Лыжи', 'Skiing'),
      N('snowboard', 'Сноуборд', 'Snowboard'),
    ]),
    N('travel', 'Путешествия', 'Travel', [
      N('roadtrip', 'Роудтрипы', 'Road trips'),
      N('sightseeing', 'По городу', 'Sightseeing'),
      N('cityhop', 'Города на выходные', 'City breaks'),
      N('vanlife', 'Ванлайф', 'Van life'),
      N('digitalnomad', 'Номадство', 'Digital nomad'),
      N('hostels', 'Хостелы', 'Hostels'),
    ]),
    N('naturelife', 'Сад и звёзды', 'Garden & stars', [
      N('gardening', 'Сад', 'Gardening'),
      N('plants', 'Растения', 'Plants'),
      N('birdwatching', 'Птицы', 'Birdwatching'),
      N('stargazing', 'Звёзды', 'Stargazing'),
      N('foraging', 'Травы и грибы', 'Foraging'),
      N('fishing', 'Рыбалка', 'Fishing'),
    ]),
    N('adventure', 'Адреналин', 'Adrenaline', [
      N('paragliding', 'Параплан', 'Paragliding'),
      N('skydiving', 'Парашют', 'Skydiving'),
      N('canyoning', 'Каньонинг', 'Canyoning'),
      N('caving', 'Спелео', 'Caving'),
    ]),
  ]),

  // ------------------------------------------------------------------ 7. дело
  TOP('tech', 'Дело', 'Work & tech', 'coding', [
    N('engineering', 'Код и ИИ', 'Code & AI', [
      N('coding', 'Программирование', 'Coding'),
      N('ai', 'ИИ', 'AI'),
      N('python', 'Python', 'Python'),
      N('javascript', 'JavaScript', 'JavaScript'),
      N('rust', 'Rust', 'Rust'),
      N('data', 'Данные', 'Data'),
      N('cybersecurity', 'Безопасность', 'Security'),
      N('opensource', 'Опенсорс', 'Open source'),
      N('devops', 'DevOps', 'DevOps'),
    ]),
    N('startups', 'Стартапы', 'Startups', [
      N('startup', 'Свой проект', 'Own project'),
      N('founder', 'Основателям', 'Founders'),
      N('product', 'Продукт', 'Product'),
      N('entrepreneur', 'Предпринимательство', 'Entrepreneurship'),
      N('business', 'Бизнес', 'Business'),
    ]),
    N('design', 'Дизайн', 'Design', [
      N('ux', 'UX', 'UX'),
      N('ui', 'UI', 'UI'),
      N('figma', 'Figma', 'Figma'),
      N('branding', 'Бренд', 'Branding'),
      N('typography', 'Типографика', 'Typography'),
      N('motion', 'Моушн', 'Motion'),
    ]),
    N('web3', 'Крипта', 'Crypto', [
      N('crypto', 'Криптовалюты', 'Crypto'),
      N('bitcoin', 'Биткоин', 'Bitcoin'),
      N('ethereum', 'Эфир', 'Ethereum'),
      N('defi', 'DeFi', 'DeFi'),
      N('nft', 'NFT', 'NFT'),
      N('dao', 'DAO', 'DAO'),
    ]),
    N('career', 'Карьера и связи', 'Career & network', [
      N('networking', 'Нетворкинг', 'Networking'),
      N('investing', 'Инвестиции', 'Investing'),
      N('finance', 'Финансы', 'Finance'),
      N('mentorship', 'Менторство', 'Mentorship'),
      N('freelance', 'Фриланс', 'Freelance'),
      N('remote', 'Удалёнка', 'Remote'),
      N('coworking', 'Коворкинг', 'Coworking'),
    ]),
    N('growth', 'Маркетинг', 'Marketing', [
      N('marketing', 'Маркетинг', 'Marketing'),
      N('sales', 'Продажи', 'Sales'),
      N('saas', 'SaaS', 'SaaS'),
      N('pm', 'Продакт-менеджмент', 'Product management'),
    ]),
  ]),

  // ------------------------------------------------------------------ 8. учёба
  TOP('learning', 'Учёба', 'Learning', 'learning', [
    N('language', 'Языки', 'Languages', [
      N('exchange', 'Языковой обмен', 'Language exchange'),
      N('spanish', 'Испанский', 'Spanish'),
      N('english', 'Английский', 'English'),
      N('french', 'Французский', 'French'),
      N('german', 'Немецкий', 'German'),
      N('italian', 'Итальянский', 'Italian'),
      N('portuguese', 'Португальский', 'Portuguese'),
      N('catalan', 'Каталанский', 'Catalan'),
      N('japanese', 'Японский', 'Japanese'),
      N('korean', 'Корейский', 'Korean'),
      N('mandarin', 'Китайский', 'Mandarin'),
      N('arabic', 'Арабский', 'Arabic'),
    ]),
    N('skills', 'Курсы и практика', 'Courses & practice', [
      N('course', 'Курсы', 'Courses'),
      N('workshop', 'Воркшопы', 'Workshops'),
      N('studygroup', 'Учебная группа', 'Study group'),
      N('bootcamp', 'Буткемпы', 'Bootcamps'),
      N('tutoring', 'Репетиторство', 'Tutoring'),
    ]),
    N('academic', 'Наука', 'Science', [
      N('psychology', 'Психология', 'Psychology'),
      N('neuroscience', 'Нейронаука', 'Neuroscience'),
      N('economics', 'Экономика', 'Economics'),
      N('science', 'Наука вообще', 'Science'),
    ]),
    N('personal', 'Навыки', 'Personal skills', [
      N('publicspeaking', 'Публичные выступления', 'Public speaking'),
      N('debate', 'Дебаты', 'Debate'),
      N('productivity', 'Продуктивность', 'Productivity'),
    ]),
  ]),
];

export const nodeLabel = (n: WheelNode) => T(n.ru, n.en);

/** Подпись по ключу — для чипов собранного. Не нашли в дереве — значит слово человека, как есть. */
export function labelOf(key: string): string {
  const walk = (list: WheelNode[]): string | null => {
    for (const n of list) {
      if (n.key === key) return nodeLabel(n);
      const deep = n.kids ? walk(n.kids) : null;
      if (deep) return deep;
    }
    return null;
  };
  return walk(WHEEL_TREE) || key;
}

/**
 * Из добавленных ключей — те, про которые стоит РАЗГОВАРИВАТЬ: без предков более точного выбора.
 * «sports, racket, padel» → разговор про падел; спрашивать «чем тебе нравится спорт» после этого —
 * значит показать, что ответа не услышали. Ключ, добавленный БЕЗ уточнения («Спорт» и всё),
 * остаётся: это и есть выбор человека.
 */
export function funnelWorthy(keys: string[]): string[] {
  const anc = new Set<string>();
  const walk = (list: WheelNode[], path: string[]) => {
    for (const n of list) {
      if (keys.includes(n.key)) path.forEach((p) => anc.add(p));
      if (n.kids) walk(n.kids, [...path, n.key]);
    }
  };
  walk(WHEEL_TREE, []);
  return keys.filter((k) => !anc.has(k));
}

export const WHEEL_COPY = {
  hint: () =>
    T('Крути кольцо — что под стрелкой, то и выбрано. Нажми в середину, чтобы раскрыть подробнее; остановиться можно на любом уровне.',
      'Spin the ring — the pointer picks. Tap the middle to open it up; you can stop at any level.'),
  add: () => T('Добавить', 'Add it'),
  /** «Уточнить» — раскрыть выбранное следующим кольцом. Тот же шаг делает и нажатие на середину. */
  refine: () => T('Уточнить', 'Refine'),
  /** Подпись до первого касания: колесо ещё ничего не выбрало ЗА человека. */
  empty: () => T('Крутани колесо', 'Give it a spin'),
};
