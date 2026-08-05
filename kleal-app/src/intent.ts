/**
 * Создание интента — кадры борда «1:1 Offline», OF.04–OF.10.
 *
 * Английские вопросы агента взяты с борда дословно (они же лежат в
 * kleal-ms/docs/board_1to1_structure.txt — там имена текстовых слоёв, а в Figma имя текстового
 * слоя и есть его содержимое). Варианты ответов внутри компонентов борда не выгружались, поэтому
 * взяты из работающей веб-версии: там они уже согласованы с тем, что понимает матчинг.
 *
 * Ключи (offline/online/hybrid, 1:1/group, коды районов) НЕ придуманы заново — совпадают с теми,
 * что уходят в /api/agent/plan и /api/agent/match.
 */
import { T } from './i18n';

export type IntentStepId = 'what' | 'how' | 'size' | 'when' | 'who' | 'where' | 'summary';

/** Порядок и проценты. Одна полоса на весь мастер, монотонно. */
export const INTENT_ORDER: IntentStepId[] = ['what', 'how', 'size', 'when', 'who', 'where', 'summary'];
export const INTENT_PROGRESS: Record<IntentStepId, number> = {
  what: 0, how: 15, size: 30, when: 50, who: 65, where: 80, summary: 100,
};

export const INTENT_TITLE = () => T('Новый интент', 'New intent');

/** OF.04. Подсказка под вопросом — тоже с борда, слово в слово. */
export const STEP_WHAT = {
  bot: () => T('Что хочешь сделать?', 'What do you want to do?'),
  hint: () =>
    T(
      'Без сложностей — кофе, партия, игра, прогулка или просто «не хочу сидеть дома».',
      'Keep it simple — coffee, a match, a game, a walk, language practice, or just “don’t feel like staying in.”'
    ),
  pick: () => T('Выбери из предложенного', 'Choose from the suggested options'),
  placeholder: () => T('Например: хочу посмотреть футбол вечером…', 'I want to watch football tonight…'),
};

/** Быстрые варианты. Ключи — обычные слова: матчинг разбирает темы буквально. */
export const WHAT_SUGGESTIONS: [string, string, string][] = [
  ['coffee', '☕', 'Кофе и разговор'],
  ['walk', '🚶', 'Прогулка'],
  ['football', '⚽', 'Футбол'],
  ['gaming', '🎮', 'Поиграть'],
  ['language', '🗣', 'Языковая практика'],
  ['dinner', '🍽', 'Поужинать'],
];
const WHAT_EN: Record<string, string> = {
  coffee: 'Coffee & a chat', walk: 'A walk', football: 'Football',
  gaming: 'Play something', language: 'Language practice', dinner: 'Dinner',
};
export const whatLabel = (k: string) => {
  const w = WHAT_SUGGESTIONS.find((x) => x[0] === k);
  return w ? `${T(w[2], WHAT_EN[k])} ${w[1]}` : k;
};
export const whatPlain = (k: string) => {
  const w = WHAT_SUGGESTIONS.find((x) => x[0] === k);
  return w ? T(w[2], WHAT_EN[k]) : k;
};

/** OF.05. */
export const STEP_HOW = {
  bot: () => T('Как хочешь встретиться?', 'How do you want to meet?'),
};
export const FORMATS: [string, string, string, string, string][] = [
  ['offline', '📍', 'Офлайн', 'Offline', 'Вживую'],
  ['online', '🌐', 'Онлайн', 'Online', 'Видео или голос'],
  ['hybrid', '➕', 'Гибрид', 'Hybrid', 'И так, и так'],
];
const FORMAT_SUB_EN: Record<string, string> = {
  offline: 'In person', online: 'Video / voice', hybrid: 'Both online & offline',
};
export const formatLabel = (k: string) => {
  const f = FORMATS.find((x) => x[0] === k);
  return f ? T(f[2], f[3]) : k;
};
export const formatSub = (k: string) => {
  const f = FORMATS.find((x) => x[0] === k);
  return f ? T(f[4], FORMAT_SUB_EN[k]) : '';
};

/**
 * OF.06. Двa варианта, не три: «малой группы» в продукте больше нет — группа это три человека и
 * больше, включая тебя. Число GROUP_MIN_TOTAL — то же, из которого собран весь групповой слой.
 *
 * Ключи совпадают с ALLOWED_FORMATS матчинга (matching_core/intent_compiler/compiler.py) и уходят
 * в intent.format НАПРЯМУЮ. Это не косметика: §5.3 считает интент достаточно описанным только когда
 * заполнены и mode, и format. Проверено на стенде — без format ответ приходит с
 * minimally_sufficient.ok = false, то есть поиск идёт по недосказанному запросу.
 */
export const GROUP_MIN_TOTAL = 3;
export const STEP_SIZE = {
  bot: () => T('Сколько вас будет?', 'How many people will there be?'),
};
export const SIZES: [string, string, string, string, string][] = [
  ['1:1', '👤', 'Один на один', 'One-on-one', 'Только вы вдвоём'],
  ['group', '👥', 'Группа', 'Group', 'От трёх человек'],
];
const SIZE_SUB_EN: Record<string, string> = {
  '1:1': 'Just the two of you', group: '3 people or more',
};
export const sizeLabel = (k: string) => {
  const s = SIZES.find((x) => x[0] === k);
  return s ? T(s[2], s[3]) : k;
};
export const sizeSub = (k: string) => {
  const s = SIZES.find((x) => x[0] === k);
  return s ? T(s[4], SIZE_SUB_EN[k]) : '';
};

/**
 * OF.07–OF.09 делят на борде ОДНУ подсказку — «To match you better, one thing».
 *
 * В статичных кадрах это незаметно, а в живой ленте все три реплики стоят подряд, и агент три раза
 * повторяет одно и то же — так разговаривает не собеседник, а заевшая пластинка. Общая фраза
 * произносится один раз, на первом из трёх шагов; дальше — свои короткие вопросы.
 */
export const STEP_DETAIL = {
  bot: () => T('Ещё одно — чтобы подобрать точнее', 'To match you better, one thing'),
  who: () => T('А кого искать?', 'And who should I look for?'),
  where: () => T('И где тебе удобно?', 'And where suits you?'),
};

export const STEP_WHEN = {
  label: () => T('Когда', 'When'),
  timeLabel: () => T('Время', 'Time'),
};
/** Дни, а не календарь: интент живёт часы-дни, и «через месяц» ему не нужно. */
export const DAYS: [string, string, string][] = [
  ['today', 'Сегодня', 'Today'],
  ['tomorrow', 'Завтра', 'Tomorrow'],
  ['weekend', 'На выходных', 'This weekend'],
  ['flexible', 'Когда угодно', 'Flexible'],
];
export const dayLabel = (k: string) => {
  const d = DAYS.find((x) => x[0] === k);
  return d ? T(d[1], d[2]) : k;
};
export const PARTS: [string, string, string][] = [
  ['morning', 'Утро', 'Morning'],
  ['afternoon', 'День', 'Afternoon'],
  ['evening', 'Вечер', 'Evening'],
  ['late', 'Поздний вечер', 'Late evening'],
];
export const partLabel = (k: string) => {
  const p = PARTS.find((x) => x[0] === k);
  return p ? T(p[1], p[2]) : k;
};

/**
 * Строка времени, которая уходит В ЗАПРОС, — всегда английская, независимо от языка интерфейса.
 *
 * Срочность на той стороне определяется поиском слов в тексте: SOON_WORDS = today/tonight/evening/
 * tomorrow, _urgency() ищет now/asap/urgent/soon. Русских слов там нет ни одного. Отправить
 * «Сегодня Вечер» — значит получить urgency «none»: запрос на сегодняшний вечер ранжировался бы
 * как «когда-нибудь», и человек, пишущий по-русски, тихо терял бы всю срочность.
 */
export const timeQuery = (day?: string, part?: string) => {
  const D: Record<string, string> = {
    today: 'today', tomorrow: 'tomorrow', weekend: 'this weekend', flexible: 'flexible',
  };
  const P: Record<string, string> = {
    morning: 'morning', afternoon: 'afternoon', evening: 'evening', late: 'late evening',
  };
  return [day && D[day], part && P[part]].filter(Boolean).join(' ');
};

export const STEP_WHO = {
  sexLabel: () => T('Пол', 'Sex'),
  ageLabel: () => T('Возраст', 'Age'),
};

export const STEP_WHERE = {
  districtLabel: () => T('Район', 'District'),
  radiusLabel: () => T('Как далеко готов(а) ехать?', 'How far are you happy to go?'),
};
export const DISTRICTS: [string, string, string][] = [
  ['center', 'Центр', 'Center'],
  ['west', 'Запад', 'West'],
  ['east', 'Восток', 'East'],
  ['south', 'Юг', 'South'],
  ['beach', 'Пляж', 'Beach'],
];
export const districtLabel = (k: string) => {
  const d = DISTRICTS.find((x) => x[0] === k);
  return d ? T(d[1], d[2]) : k;
};
/** Район в запросе — канонически английский: он попадает в карточки и планы, которые видят оба. */
export const districtQuery = (k?: string) => {
  const d = DISTRICTS.find((x) => x[0] === k);
  return d ? d[2] : k || '';
};

/** OF.10. */
export const STEP_SUMMARY = {
  bot: () => T('Вот что получилось', 'Here’s what I got'),
  send: () => T('Искать людей', 'Find people'),
  edit: () => T('Поправить', 'Change something'),
};

/** OF.11. */
export const SEARCHING = {
  title: () => T('Ищу людей, группы\nи места для тебя', 'Finding people, groups\nand places for you'),
  step: () => T('Смотрю подходящие форматы', 'Scanning matching formats'),
  note: () => T('Это займёт пару секунд.', 'This will take just a moment.'),
};

/** OF.12 / OF.11a. */
export const RESULTS = {
  best: () => T('Лучшее совпадение по запросу', 'Best fit for your request'),
  empty: () => T('Пока никого по такому запросу', 'Nobody matches that yet'),
  emptyNote: () =>
    T(
      'Можно расширить поиск — по расстоянию, времени или близким занятиям.',
      'We can widen the search — by distance, time, or related activities.'
    ),
  widen: () => T('Расширить поиск', 'Widen the search'),
  exhausted: () =>
    T('Шире уже некуда — по этому запросу пока никого.', 'Nothing wider to try — nobody matches this yet.'),
  found: (n: number) => T(`Нашлось: ${n}`, `Found ${n}`),
};

/**
 * §12 лестница расширения.
 *
 * Оси — те же четыре, что понимает /api/agent/expand, и порядок здесь не произвольный: сначала
 * самые дешёвые (близкие занятия), в конце самая грубая (удвоить радиус). Сервер расширяет РОВНО
 * одну ось за раз и, если ось не передать, всегда берёт первую — то есть без этого списка кнопка
 * «Расширить поиск» на второе нажатие возвращала бы ровно то же самое.
 *
 * Подпись к каждой ступени — обычными словами, а не кодом оси: человек должен понимать, почему
 * выдача изменилась. Молчаливое расширение — это подмена его запроса своим.
 */
export type ExpandAxis = 'adjacent' | 'exactness' | 'parent' | 'radius';
export const EXPAND_LADDER: ExpandAxis[] = ['adjacent', 'exactness', 'parent', 'radius'];

export const axisExplain = (axis: ExpandAxis, radiusKm?: number) => {
  switch (axis) {
    case 'adjacent':
      return T('Добавила близкие занятия, не только то, что ты назвал(а).',
               'Added neighbouring activities, not just the one you named.');
    case 'exactness':
      return T('Перестала требовать точное совпадение.', 'Stopped requiring an exact match.');
    case 'parent':
      return T('Взяла категорию шире.', 'Went one category wider.');
    case 'radius':
      return radiusKm
        ? T(`Расширила круг поиска до ${radiusKm} км.`, `Widened the search radius to ${radiusKm} km.`)
        : T('Расширила круг поиска.', 'Widened the search radius.');
  }
};
