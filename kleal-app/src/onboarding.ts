/**
 * Данные онбординга — по борду Figma «A. Profile chat», кадры A.04–A.15.
 *
 * Первая версия была собрана по живой веб-реализации и оказалась не тем: борд отличается и
 * набором шагов, и интерфейсом, и главное — тем, что агент там РАЗГОВАРИВАЕТ. На каждом кадре
 * внизу есть строка «Message…»: человек может ответить своими словами вместо нажатия на чип,
 * и ответ разбирает модель (/api/onboarding/chat). Виджеты — это ускорение, а не единственный путь.
 *
 * Английские строки взяты с кадров дословно, включая опечатки борда (см. STEP_START).
 * Русские написаны, а не переведены машинно.
 */
import { T } from './i18n';

// ---------------------------------------------------------------- интро (кадры до A.04)

export type Slide = { title: string; sub: string; art: 'primary' | 'searching' | 'match' };

export const SLIDES: () => Slide[] = () => [
  {
    title: T('Скажи Kleal,\nчем хочешь заняться', 'Tell Kleal what you\nwant to do'),
    sub: T(
      'Кофе, партия, игра, прогулка, языковая практика — или просто «хочу куда-нибудь».',
      'Coffee, a match, a game, a walk, language practice, or just something spontaneous.'
    ),
    art: 'primary',
  },
  {
    title: T('Ищем людей под план,\nа не анкеты для листания', 'Find people for the plan,\nnot profiles to scroll'),
    sub: T(
      'Kleal подбирает людей, комнаты, группы и события по настроению, времени, месту и интересам.',
      'Kleal looks for the right people, rooms, groups or events from your mood, time, place and interests.'
    ),
    art: 'searching',
  },
  {
    title: T('Меньше переписки.\nБольше живых встреч', 'Less social admin.\nMore real plans'),
    sub: T(
      'Kleal находит, кому это интересно, проверяет совпадение и приносит варианты. Каждый шаг подтверждаешь ты.',
      'Kleal finds who is interested, checks the fit, and brings you options. You confirm every step.'
    ),
    art: 'match',
  },
];

export const AUTH_TERMS = () =>
  T(
    'Продолжая, ты соглашаешься с Условиями и Политикой конфиденциальности.',
    'By continuing you agree to our Terms and Privacy Policy.'
  );

// ---------------------------------------------------------------- шаги профиля

export type StepId =
  | 'start'      // A.04 — согласие + имя
  | 'basics'     // A.05 — возраст (кольцо) + пол
  | 'area'       // A.06 — страна, радиус, карта
  | 'languages'  // A.07 — языки с флагами
  | 'hobbies'    // A.08 — увлечения с эмодзи
  | 'funnel'     // A.08 продолжение — разговор про интересы, ведёт модель
  | 'photo';     // A.09–A.13 — фото

/**
 * Процент в шапке. На борде он местами непоследователен (кадры фото показывают 32 %, 70 %, 80 %,
 * 15 % подряд) — это явно черновые значения, а не замысел: полоса, которая едет назад, читается
 * как сбой. Взята монотонная последовательность по тем кадрам, где она осмысленна.
 */
export const STEP_PROGRESS: Record<StepId, number> = {
  start: 0,
  basics: 10,
  area: 30,
  languages: 45,
  hobbies: 60,
  funnel: 70,
  photo: 80,
};

export const HEADER_TITLE = () => T('Профиль', 'Creating Profile');
export const SUMMARY_TITLE = () => T('Что Kleal знает о тебе', 'What Kleal knows about you');

// A.04. «We've go!» и «HMay I know your name?» — опечатки НА БОРДЕ. Здесь исправлены: копировать
// опечатку в продукт нельзя, а править молча борд тоже нельзя — поэтому написано тут.
export const STEP_START = {
  ask: () => T('Расскажешь пару деталей о себе?', 'Would you be willing to fill in a few details about yourself?'),
  hint: () => T('Выбери вариант или напиши своё', 'Pick some or write your own'),
  why: () => T('Зачем это нужно?', 'Why do you need this?'),
  go: () => T('Поехали!', "Let's go!"),
  whyAnswer: () =>
    T(
      'Чтобы искать не всех подряд, а тех, с кем тебе правда будет о чём поговорить. Чем больше я знаю, тем точнее подбираю.',
      'So I look for people you would actually have something to talk about with, not just anyone. The more I know, the better I match.'
    ),
  askName: () => T('Отлично! Как тебя зовут?', 'We’re on! May I know your name?'),
};

export const STEP_BASICS = {
  bot: () => T('Супер! Сначала немного о тебе.', 'Awesome!\nFirst, a little bit about you.'),
  ageLabel: () => T('Твой возраст', 'Your age'),
  sexLabel: () => T('Пол', 'Sex'),
  cta: () => T('Продолжаем', 'Keep going'),
};

/** «Any is fine» — это НЕ «другое»: человек говорит, что пол ему не важен. */
export const SEXES: [string, string, string][] = [
  ['Male', 'Male', 'Мужской'],
  ['Female', 'Female', 'Женский'],
  ['Any', 'Any is fine', 'Не важно'],
];
export const sexLabel = (k: string) => {
  const s = SEXES.find((x) => x[0] === k);
  return s ? T(s[2], s[1]) : k;
};

export const STEP_AREA = {
  bot: () => T('Класс! Где ты обычно бываешь?', 'Cool!\nWhere do you usually hang out?'),
  radiusLabel: () => T('Как далеко готов(а) ехать?', 'How far are you happy to go?'),
  detect: () => T('Определить моё местоположение', 'Detect my location'),
  cta: () => T('Почти закончили', 'We’re almost done'),
};

export const STEP_LANGUAGES = {
  bot: () =>
    T('Отлично. На каких языках тебе комфортно общаться?', 'Great. What languages are you comfortable communicating in?'),
  hint: () => T('Выбери варианты или напиши свой', 'Pick some or write your own'),
  own: () => T('Свой вариант', 'Your option'),
  cta: () => T('Дальше', 'Next'),
};

/** Порядок и флаги — с кадра A.07. */
export const LANGS: [string, string, string][] = [
  ['English', '🇬🇧', 'Английский'],
  ['Spanish', '🇪🇸', 'Испанский'],
  ['German', '🇩🇪', 'Немецкий'],
  ['French', '🇫🇷', 'Французский'],
  ['Italian', '🇮🇹', 'Итальянский'],
  ['Portuguese', '🇵🇹', 'Португальский'],
  ['Russian', '🇷🇺', 'Русский'],
];
export const langLabel = (k: string) => {
  const l = LANGS.find((x) => x[0] === k);
  return l ? `${T(l[2], l[0])} ${l[1]}` : k;
};
export const langPlain = (k: string) => {
  const l = LANGS.find((x) => x[0] === k);
  return l ? T(l[2], l[0]) : k;
};

export const STEP_HOBBIES = {
  bot: () => T('Класс! Чем увлекаешься?', 'Cool!\nWhat are your hobbies?'),
  hint: () =>
    T('Выбери из готовых или напиши своё', 'Choose from the pre-written options or write your own'),
  own: () => T('Добавить своё', 'Add your own'),
  cta: () => T('Дальше', 'Next'),
};

/** Порядок и эмодзи — с кадра A.08. Ключи те же, что понимает матчинг. */
export const HOBBIES: [string, string, string][] = [
  ['coding', '💻', 'Код'],
  ['hiking', '🥾', 'Походы'],
  ['gaming', '🎮', 'Видеоигры'],
  ['yoga', '🧘', 'Йога'],
  ['cooking', '🍳', 'Готовка'],
  ['music', '🎵', 'Музыка'],
  ['coffee', '☕', 'Кофе'],
  ['photography', '📷', 'Фото'],
  ['travel', '✈️', 'Путешествия'],
  ['football', '⚽', 'Футбол'],
];
const HOBBY_EN: Record<string, string> = {
  coding: 'Coding', hiking: 'Hiking', gaming: 'Video games', yoga: 'Yoga', cooking: 'Cooking',
  music: 'Music', coffee: 'Coffee', photography: 'Photography', travel: 'Travel', football: 'Football',
};
export const hobbyLabel = (k: string) => {
  const h = HOBBIES.find((x) => x[0] === k);
  return h ? `${T(h[2], HOBBY_EN[k])} ${h[1]}` : k;   // своё написанное показывается как есть
};
export const hobbyPlain = (k: string) => {
  const h = HOBBIES.find((x) => x[0] === k);
  return h ? T(h[2], HOBBY_EN[k]) : k;
};

/**
 * Разговор про интересы — то, ради чего онбординг вообще чат, а не анкета.
 *
 * Чипы говорят ЧТО человек выбрал, и на этом всё. «Футбол» — играет или смотрит? «Испанский» —
 * какой уровень? «Игры» — на чём и в чём. Матчинг ранжирует именно по этому, поэтому после выбора
 * агент коротко расспрашивает: не больше двух вопросов на интерес, вопросы задаёт модель
 * (/api/onboarding/chat), она же дописывает профиль. Выход из разговора доступен всегда.
 *
 * Первые две реплики истории — затравка, слово в слово как в работающей веб-версии: сервер по ней
 * понимает, что шаг именно про интересы, и с какими.
 */
export const FUNNEL = {
  seedBot: 'Nice picks.',
  seedUser: (picks: string[]) => "I'm into " + picks.join(', '),
  /** Предохранитель: два вопроса на интерес плюс запас на уточнения. */
  cap: (n: number) => n * 2 + 4,
  compose: () => T('Расскажи Kleal больше…', 'Tell Kleal more…'),
  done: () => T('Это всё', "That's enough"),
  cont: () => T('Продолжить', 'Continue'),
};

/**
 * Те же слова, по которым сервер узнаёт «я закончил». Нужны здесь, чтобы не печатать свой выход
 * рядом с точно таким же от модели: на закрывающем ходу она сама предлагает «Это всё».
 */
export const FUNNEL_OUT_RE =
  /that'?s all|that'?s enough|that is all|\bfinish|\bdone\b|no more|nothing else|all set|это вс[её]|больше нет|хватит|достаточно/i;

export const STEP_PHOTO = {
  greet: (name: string) => T('Рад знакомству, ' + name + '!', 'Nice to meet you, ' + name + '!'),
  ask: () =>
    T(
      'Давай добавим фото профиля, чтобы тебя узнавали на встречах.',
      'Let’s add a profile photo so people recognize you at meetups.'
    ),
  hint: () => T('Добавь фото', 'Add a photo'),
  take: () => T('Сделать фото', 'Take photo'),
  upload: () => T('Загрузить фото', 'Upload photo'),
  skip: () => T('Пропустить', 'Skip'),
  selfieTitle: () => T('Сделай селфи', 'Take a selfie'),
  cancel: () => T('Отмена', 'Cancel'),
  praise: () => T('Отлично вышло! Идеальное фото для профиля.', 'Wow — you look great!\nThat’s a perfect profile photo.'),
  pickHint: () => T('Выбери, нажав на вариант', 'Select an option by tap'),
  use: () => T('Оставить', 'Use it'),
  retake: () => T('Переснять', 'Retake'),
  confirmed: () => T('Отлично — теперь это твоё фото профиля.', 'Love it — that’s your profile photo now.'),
  cardTitle: () => T('Фото профиля установлено', 'Profile photo set'),
  cardSub: (name: string) => T('Выглядишь отлично, ' + name, 'Looking sharp, ' + name),
  next: () => T('Теперь найдём твоих людей.\nКогда будешь готов(а).', 'Now let’s find your people.\nReady when you are.'),
  cta: () => T('Поехали', 'Let’s go'),
};

export const SUMMARY = {
  confidence: () => T('Точность профиля', 'Profile confidence'),
  klealSummary: () => T('Что понял Kleal', 'Kleal’s summary'),
  updatedToday: () => T('Обновлено сегодня', 'Updated today'),
  viewAll: () => T('Все настройки профиля', 'View all profile settings'),
  planTitle: () => T('План обновлён', 'Plan updated'),
  planBody: () =>
    T(
      'Чем больше Kleal о тебе знает, тем лучше понимает твои намерения и точнее сводит с нужными людьми.',
      'The more Kleal knows about you, the better it can understand your intentions and connect you with the right people.'
    ),
  done: () => T('Готово', 'Done'),
};

/**
 * Кадр A.15 — и он же пока главный экран приложения.
 *
 * Поздравление говорится РОВНО один раз — сюда попадают сразу после записи профиля. Приветствие
 * при каждом запуске живёт на главном экране, у него своё (src/home.ts).
 */
export const DONE_SCREEN = {
  title: () => T('Поздравляем!\nТы в игре!', 'Congratulations!\nYou are on the board!'),
  cta: () => T('Создать интент', 'Create Intent'),
};

export const COMPOSER_PLACEHOLDER = () => T('Сообщение…', 'Message…');

export const NAV = () => [
  T('Интенты', 'My Intents'),
  T('Поиск', 'Search'),
  T('Сообщения', 'Messages'),
  T('Профиль', 'Profile'),
];

/**
 * На каком шаге продолжать. Онбординг можно закрыть на середине — телефон разрядился, отвлекли, —
 * и вернувшись человек должен попасть туда, где остановился, а не в начало и уж точно не в тупик.
 *
 * Первая версия делала именно тупик: чипы первого шага прятались, если имя уже сохранено, а сам шаг
 * оставался первым. На экране висел вопрос и ни одной кнопки под ним.
 */
export function resumeStep(p: any): StepId {
  if (!p || !p.name) return 'start';
  if (!p.age || !p.gender) return 'basics';
  if (!p.city) return 'area';
  if (!(p.languages?.comfortable || []).length) return 'languages';
  if (!(p.interests?.explicit || []).length) return 'hobbies';
  return 'photo';
}

/** Есть ли вообще что продолжать. */
export function hasProgress(p: any): boolean {
  return !!(p && p.name);
}

export const RESUME = {
  line: (name: string) => T('С возвращением, ' + name + '! Продолжим с того места.', 'Welcome back, ' + name + '! Let’s pick up where we left off.'),
  restart: () => T('Начать заново', 'Start over'),
  restartAsk: () => T('Начать онбординг заново? Всё, что уже введено, сотрётся.', 'Start onboarding over? Everything you have entered will be erased.'),
  restartYes: () => T('Да, заново', 'Yes, start over'),
  restartNo: () => T('Отмена', 'Cancel'),
};
