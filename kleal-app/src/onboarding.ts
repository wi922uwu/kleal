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
    title: T('Скажи Kleal,\nчем хочешь заняться', 'Tell Kleal\nwhat you want to do'),
    sub: T(
      'Кофе, футбол, языковая практика, игра,\nпрогулка — или просто что-нибудь спонтанное',
      'Coffee, football, language practice, a game,\na walk, or just something spontaneous'
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

/**
 * Экран входа A.03. Заголовок — обещание продукта, а не приветствие: борд ставит его крупно
 * над логотипом, и это первое, что человек читает про Kleal.
 */
export const AUTH_COPY = () => ({
  title: T('Никаких свайпов.\nТолько живые планы', 'No swipes.\nJust real plans'),
  apple: T('Продолжить с Apple', 'Continue with Apple'),
  google: T('Продолжить с Google', 'Continue with Google'),
  email: T('Продолжить по почте', 'Continue with Email'),
});

/**
 * Эмодзи-россыпь за логотипом на экране входа — из борда, пять строк.
 *
 * Это КАРТИНКА, набранная текстом: список занятий, которыми люди тут занимаются. Переводить
 * его не нужно, а держать в разметке — нельзя (правило: копия в src/*.ts), поэтому лежит здесь.
 */
export const AUTH_EMOJI_ROWS = [
  '⚽️ 🎮 ☕️ 🎨 🏃 🍕 🎬 🚴 🧩 🍸',
  '🎾 🍣 🏕️ 🎤 🧘 🥐 📸 🎳',
  '🎲 🍜 🏔️ 🎭 🏄 🍦 🎯',
  '🏓 ♟️ 🍔 🛶 🎧 🧗 🍰 🪩 🏸 🍿',
  '🏐 👾 🥟 🥾 🎟️ ⛷️ 🎶 🍹 🧺 🎱',
];

/** Подпись под логотипом на первом кадре — только для читающих экраном, на глаз её нет. */
export const WELCOME_A11Y = () => T('Kleal', 'Kleal');

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
  hobbies: 65,
  photo: 80,
};

export const HEADER_TITLE = () => T('Профиль', 'Creating Profile');
export const SUMMARY_TITLE = () => T('Что Kleal знает о тебе', 'What Kleal knows about you');

// A.04. «We've go!» и «HMay I know your name?» — опечатки НА БОРДЕ. Здесь исправлены: копировать
// опечатку в продукт нельзя, а править молча борд тоже нельзя — поэтому написано тут.
export const STEP_START = {
  /**
   * Первое, что человек читает в приложении. Раньше здесь сразу просили «пару деталей» — просьба
   * без объяснения, кто просит и зачем. Теперь Kleal сначала говорит, что он такое и чем отличается
   * от ленты знакомств: он не показывает людей, он ищет их под конкретную затею и знакомит, когда
   * совпало у обоих. Три предложения — дальше сразу вопрос, читать простыню никто не будет.
   */
  intro: () =>
    T(
      'Привет! Я Kleal — твой агент. Ты говоришь, чем хочешь заняться: сходить за кофе, погонять мяч, потренировать испанский, — а я ищу человека, которому хочется того же, и знакомлю вас, когда совпало у обоих.',
      'Hi! I’m Kleal — your agent. You tell me what you feel like doing: grabbing a coffee, kicking a ball around, practising Spanish — and I find someone who wants the same, then introduce you once you both agree.'
    ),
  /** Вторая реплика: почему сейчас будут вопросы. */
  ask: () => T('Расскажешь пару деталей о себе? Так я пойму, кого искать.',
                'Tell me a couple of things about yourself? That’s how I know who to look for.'),
  hint: () => T('Выбери вариант или напиши своё', 'Pick some or write your own'),
  why: () => T('Зачем это нужно?', 'Why do you need this?'),
  go: () => T('Поехали!', "Let's go!"),
  whyAnswer: () =>
    T(
      'Чтобы искать не всех подряд, а тех, с кем тебе правда будет о чём поговорить. Чем больше я знаю, тем точнее подбираю.',
      'So I look for people you would actually have something to talk about with, not just anyone. The more I know, the better I match.'
    ),
  askName: () => T('Как тебя зовут?', 'What should I call you?'),
};

/**
 * ВЫТАЩИТЬ ИМЯ ИЗ ЖИВОГО ОТВЕТА.
 *
 * На вопрос «Как тебя зовут?» отвечают не одним словом. Отвечают «называй меня Иван», «меня
 * зовут Иван Петров», «я Ваня», «just call me Vanya». Раньше в имя писалось ровно то, что
 * набрали, — и человек становился «называй меня иван»: так его видели в поиске, так к нему
 * обращался агент, так его имя ехало в приглашения (поймано 14 августа на живом телефоне).
 *
 * Разбор намеренно осторожный: если после срезки не осталось ничего похожего на имя,
 * возвращается исходный текст. Потерять имя хуже, чем оставить его неудобным.
 */
const NAME_LEADS: RegExp[] = [
  // Длинные раньше коротких: «меня зовут» обязано сработать прежде, чем «я» съест начало.
  /^(?:а\s+)?(?:можешь\s+)?(?:называй|зови)\s+меня\s+/iu,
  /^меня\s+зовут\s+/iu,
  /^зовут\s+/iu,
  /^мо[её]\s+имя\s*[—–-]?\s*/iu,
  /^имя\s*[—–:-]\s*/iu,
  /^я\s*[—–-]?\s+/iu,
  /^это\s+/iu,
  /^просто\s+/iu,
  /^(?:you\s+can\s+)?call\s+me\s+/iu,
  /^my\s+name\s+is\s+/iu,
  /^i\s*['’]?m\s+/iu,
  /^i\s+am\s+/iu,
  /^it\s*['’]?s\s+/iu,
  /^just\s+/iu,
  /^the\s+name\s*['’]?s\s+/iu,
];

/** Первую букву поднимаем, остальные не трогаем: «McDonald» и «van Dijk» должны выжить. */
const capFirst = (w: string) =>
  w && w === w.toLowerCase() ? w.charAt(0).toUpperCase() + w.slice(1) : w;

export function parseName(raw: string): { name: string; surname: string } {
  const text = String(raw || '').trim().replace(/[.!?,;:]+$/u, '').trim();
  if (!text) return { name: '', surname: '' };

  let s = text;
  // Обороты снимаются по кругу: «просто зови меня Ваня» — это два оборота подряд.
  for (let pass = 0; pass < 4; pass++) {
    let cut = false;
    for (const re of NAME_LEADS) {
      const next = s.replace(re, '');
      if (next !== s) { s = next.trim(); cut = true; }
    }
    if (!cut) break;
  }
  s = s.replace(/^[«"'`’]+|[»"'`’]+$/gu, '').trim();

  // Имя — это слова, а не предложение: всё, что не буква, дефис или апостроф, разбор отсекает.
  const words = s.split(/\s+/u).filter((w) => /^[\p{L}][\p{L}\-'’]*$/u.test(w));
  if (!words.length || words[0].length > 40) return { name: text.slice(0, 40), surname: '' };

  return {
    name: capFirst(words[0]),
    // Второе слово бывает фамилией, а бывает продолжением фразы. Берём его, только если
    // предложение на нём кончается: «Иван Петров» — да, «Иван и друзья» — нет.
    surname: words.length === 2 && words[1].length > 1 ? capFirst(words[1]) : '',
  };
}


/**
  * Реплики шагов — БЕЗ пустых похвал в начале.
  *
  * Было: «Отлично! Как тебя зовут?», «Супер! Сначала немного о тебе», «Класс! Где ты обычно
  * бываешь?», «Класс! Чем увлекаешься?» — четыре восклицания подряд, каждое хвалит ни за что и ни
  * одно не говорит, ЗАЧЕМ спрашивают. Тот же дефект, что вычищен из промпта воронки, только этот
  * жил в захардкоженных строках и мимо промпта прошёл.
  *
  * Стало: вопрос и одна строка про последствие — что именно этот ответ меняет в поиске. Возраст,
  * радиус и язык — жёсткие фильтры, и человеку честнее об этом знать, пока он отвечает.
  */
export const STEP_BASICS = {
  bot: () => T('Сколько тебе лет и какого ты пола? По ним я отсекаю тех, кто тебе не подойдёт.',
                'How old are you, and what’s your gender? I use both to rule out who won’t fit.'),
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
  bot: () => T('Где ты бываешь? Дальше выбранного радиуса я никого предлагать не буду.',
                'Where do you spend your time? I won’t suggest anyone beyond the radius you set.'),
  /** Страна и город — две строки, а не одна: в профиль и в поиск уезжает ГОРОД. */
  country: () => T('Страна', 'Country'),
  city: () => T('Город', 'City'),
  /** Та же строка после того, как карту подвинули: там уже не город из списка, а место с карты. */
  address: () => T('Адрес', 'Address'),
  naming: () => T('Определяем адрес…', 'Finding the address…'),
  radiusLabel: () => T('Как далеко готов(а) ехать?', 'How far are you happy to go?'),
  detect: () => T('Определить моё местоположение', 'Detect my location'),
  /**
   * Карта — единственный способ назвать место, которого нет в коротком списке городов.
   * Формулировка про КАРТУ, а не про булавку: булавка приколота к центру экрана и не двигается,
   * двигают карту под ней (см. RadiusMap.native — перетаскиваемая метка требует долгого нажатия).
   */
  pinHint: () => T('Нет своего города в списке? Подвинь карту — точка встанет под булавку.',
                   'Your town isn’t on the list? Move the map — the pin marks the spot.'),
  pinMoved: () => T('Ищем вокруг этой точки.', 'We’ll search around this spot.'),
  pinReset: (city: string) => T(`Вернуть к ${city}`, `Back to ${city}`),
  cta: () => T('Почти закончили', 'We’re almost done'),
};

export const STEP_LANGUAGES = {
  bot: () =>
    T('На каких языках тебе комфортно? Без общего языка встречи не выйдет — это жёсткий фильтр.',
      'Which languages are you comfortable in? Without a shared one a meetup can’t happen — it’s a hard filter.'),
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

/** Поле «своё увлечение» прямо в виджете — см. HobbyW в app/chat.tsx. */
export const OWN_INPUT = {
  hobbyPlaceholder: () => T('Своё увлечение', 'Your own hobby'),
  langPlaceholder: () => T('Свой язык', 'Your own language'),
  add: () => T('Добавить', 'Add'),
};

export const STEP_HOBBIES = {
  bot: () => T('Чем любишь заниматься? Расскажи своими словами — я запишу.',
                'What do you like doing? Tell me in your own words — I’ll write it down.'),
  hint: () =>
    T('Пиши как есть: «рыбачу на море по выходным»',
      'Just say it: “I fish at sea on weekends”'),
  /** Подпись над записанным. Появляется только когда есть что показать. */
  saved: () => T('Записал', 'Noted'),
  /** Пусто и человек молчит — подсказка вместо пустоты, а не ещё один вопрос. */
  empty: () => T('Пока ничего не записал — расскажи, чем занимаешься',
                 'Nothing noted yet — tell me what you’re into'),
  cta: () => T('Готово', 'Done'),
  /*
    КОЛОДА. Подписи на метках — глаголы, а не «да/нет»: карта задаёт вопрос про занятие, и ответ
    на него это действие, а не согласие. Подсказка под стопкой нужна ровно один раз, но убрать её
    после первой карты нельзя — человек может вернуться на шаг через день и не помнить, куда что
    тянуть.
  */
  deckAdd: () => T('Добавить', 'Add'),
  deckSkip: () => T('Пропустить', 'Skip'),
  deckHint: () => T('Влево — добавить, вправо — пропустить', 'Left to add, right to skip'),
  /**
   * РАЗВИЛКА ПЕРВЫМ ХОДОМ. Человек, нажавший «Добавить интерес», делится на двоих: один знает,
   * чего хочет, второму нужен вопрос. Второй ветке кнопка обязательна — пустой композер сам себя
   * вариантом не объявляет, и человек просто не узнает, что помощь существует.
   */
  forkBot: () => T('Расскажи, чем любишь заниматься. Или давай разберёмся вместе — задам несколько вопросов.',
                   'Tell me what you like doing. Or let us work it out together — I will ask a few questions.'),
  forkKnow: () => T('Знаю, чем', 'I know'),
  forkHelp: () => T('Помоги разобраться', 'Help me figure it out'),
  /**
   * ЧТО УХОДИТ РЕПЛИКОЙ, а не что написано на кнопке. «Помоги разобраться» модели ничего не
   * говорит: на живом прогоне она дважды ответила дежурным «а чем ещё занимаешься?», потому что
   * зацепиться было не за что. Реплика должна звучать как то, что человек сказал бы сам.
   */
  forkHelpSaid: () => T('Не знаю, с чего начать — спрашивай',
                        'I do not know where to start — ask me'),
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
  /**
   * «Это всё» заканчивает разговор про увлечения — а это единственный шаг, который наполняет
   * профиль по-настоящему. Раньше чип срабатывал мгновенно, наравне с обычными вариантами ответа,
   * и человек выходил из разговора, не поняв, что вышел. Теперь Kleal сначала говорит, что будет.
   */
  endAsk: () =>
    T(
      'Если закончим — про увлечения я больше не расспрашиваю, дальше только фото и всё. Чем больше расскажешь сейчас, тем точнее я ищу; добавить что-то потом можно будет в профиле.',
      'If we stop here I won’t ask about your interests again — after this it’s just the photo. The more you tell me now, the sharper I search; you can always add more later in your profile.'
    ),
  endYes: () => T('Да, закончить', 'Yes, finish'),
  endNo: () => T('Расскажу ещё', 'I’ll add more'),
  cont: () => T('Продолжить', 'Continue'),
  /** Разговор про интерес окончен: либо назад к чипам за следующим, либо дальше по анкете. */
  more: () => T('Добавить ещё', 'Add another'),
  finish: () => T('Завершить', 'Finish'),
  back: () => T('Что ещё тебе нравится?', 'What else are you into?'),
};

/**
 * Те же слова, по которым сервер узнаёт «я закончил». Нужны здесь, чтобы не печатать свой выход
 * рядом с точно таким же от модели: на закрывающем ходу она сама предлагает «Это всё».
 */
export const FUNNEL_OUT_RE =
  /that'?s all|that'?s enough|that is all|\bfinish|\bdone\b|no more|nothing else|all set|это вс[её]|больше нет|хватит|достаточно/i;

/**
 * Вариант «добавить ещё интерес», который модель предлагает сама.
 *
 * Такую кнопку нельзя отправлять в разговор как обычную реплику: она обещает вернуть к выбору
 * интересов, а на деле агент отвечал бы «какой ещё?» текстом, и чипы не возвращались бы никогда.
 * Здесь она распознаётся и ведёт туда, куда написано.
 */
export const FUNNEL_MORE_RE =
  /add another|another interest|add more|ещ[её] интерес|добавить ещ[её]|друг(ой|ое) интерес/i;

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
  /** Хвалить лицо человека агент не должен — говорим о том, что с фото делать дальше. */
  praise: () => T('Годится. Его увидят те, кому ты отправишь приглашение.',
                  'That works. The people you invite will see it.'),
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
