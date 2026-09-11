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
import { T, plural } from './i18n';

// ---------------------------------------------------------------- интро (кадры до A.04)

export type Slide = { title: string; sub: string; art: 'primary' | 'searching' | 'match' };

/**
 * ПОДПИСЬ НА ЗАНАВЕСЕ ЭКРАНА ПОЛЬЗЫ — одна, потому что и занавес теперь один.
 *
 * Сначала «Начать» стояло на всех трёх кадрах, а нажатие на первых двух просто листало: человек
 * жал «Начать» трижды и только на третий раз попадал куда обещано. Первой правкой подпись сделали
 * честной («Дальше» / «Начать»), но верным оказалось другое: занавес — это ПУСК, и на кадрах,
 * которые ещё не пускают, ему нечего делать. Первые два листаются пальцем вбок, занавес приходит
 * на последнем и означает ровно одно.
 */
export const INTRO_CTA = {
  start: () => T('Начать', "Let's Start", '¡Vamos a empezar!'),
  hint: () => T('Нажми дважды, чтобы продолжить к входу.', 'Double tap to continue to sign-in.', 'Doble toque para continuar con el inicio de sesión.'),
  slide: (n: number, total: number) => T(`Слайд ${n} из ${total}`, `Slide ${n} of ${total}`, `Diapositiva ${n} de ${total}`),
  next: () => T('Следующий слайд', 'Next slide', 'Siguiente diapositiva'),
  previous: () => T('Предыдущий слайд', 'Previous slide', 'Diapositiva anterior'),
};

export const SLIDES: () => Slide[] = () => [
  {
    title: T('Ищем людей под план,\nа не анкеты для листания', 'Find people for the plan,\nnot profiles to scroll', `Encuentra personas para el plan,
no perfiles para desplazar`),
    sub: T(
      'Kleal подбирает людей, комнаты, группы и события по настроению, времени, месту и интересам.',
      'Kleal looks for the right people, rooms, groups or events from your mood, time, place and interests.'
    , 'Kleal busca a las personas, habitaciones, grupos o eventos adecuados según tu estado de ánimo, hora, lugar e intereses.'),
    art: 'searching',
  },
  {
    title: T('Скажи Kleal,\nчем хочешь заняться', 'Tell Kleal\nwhat you want to do', `Dile a Kleal
qué quieres hacer`),
    sub: T(
      'Кофе, футбол, языковая практика, игра, прогулка — или просто что-нибудь спонтанное',
      'Coffee, football, language practice, a game, a walk, or just something spontaneous'
    , 'Café, fútbol, práctica de idiomas, un juego, un paseo o algo espontáneo'),
    art: 'primary',
  },
  {
    title: T('Меньше переписки.\nБольше живых встреч', 'Less social admin.\nMore real plans', `Menos administración social.
Más planes reales`),
    sub: T(
      'Kleal находит, кому это интересно, проверяет совпадение и приносит варианты. Каждый шаг подтверждаешь ты.',
      'Kleal finds who is interested, checks the fit, and brings you options. You confirm every step.'
    , 'Kleal busca a quienes estén interesados, comprueba la compatibilidad y te ofrece opciones. Confirmarás cada paso.'),
    art: 'match',
  },
];

/**
 * Экран входа A.03. Заголовок — обещание продукта, а не приветствие: борд ставит его крупно
 * над логотипом, и это первое, что человек читает про Kleal.
 */
export const AUTH_COPY = () => ({
  title: T('Никаких свайпов.\nТолько живые планы', 'No swipes.\nJust real plans', 'Sin deslizamientos.\nSolo planes reales'),
  apple: T('Продолжить с Apple', 'Continue with Apple', 'Continuar con Apple'),
  google: T('Продолжить с Google', 'Continue with Google', 'Continuar con Google'),
  email: T('Продолжить по почте', 'Continue with Email', 'Continuar con Email'),
  /**
   * Пометка на кнопках провайдеров. Настоящего OAuth у нас нет — он требует собственного
   * идентификатора приложения, которого у Expo Go не бывает, — и до сих пор эти кнопки молча
   * заводили профиль БЕЗ логина. Человек узнавал об этом только на выходе, где ему сообщали, что
   * «вернуть профиль будет нечем». Обещание входа, за которым нет входа, — худший вид молчания.
   */
  soon: () => T('скоро', 'soon', 'pronto'),
  /** Почему почта, а не кнопка провайдера: сказано прямо, чтобы выбор не выглядел случайным. */
  emailNote: T('Вход по почте — чтобы профиль можно было вернуть на другом телефоне.',
               'Email sign-in keeps your profile recoverable on another phone.', 'Iniciar sesión con correo electrónico mantiene tu perfil recuperable en otro teléfono.'),
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
export const WELCOME_A11Y = () => T('Kleal', 'Kleal', 'Kleal');

export const AUTH_TERMS = () =>
  T(
    'Продолжая, ты соглашаешься с Условиями и Политикой конфиденциальности.',
    'By continuing you agree to our Terms and Privacy Policy.'
  , 'Al continuar, aceptas nuestros Términos y Política de privacidad.');

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

export const HEADER_TITLE = () => T('Профиль', 'Creating Profile', 'Creando perfil');
export const SUMMARY_TITLE = () => T('Что Kleal знает о тебе', 'What Kleal knows about you', 'Lo que Kleal sabe sobre ti');

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
    , '¡Hola! Soy Kleal — tu agente. Tú me dices lo que te apetece hacer: tomar un café, patear un balón, practicar español — y yo encuentro a alguien que quiera lo mismo, y luego te presento una vez que los dos estéis de acuerdo.'),
  /** Вторая реплика: почему сейчас будут вопросы. */
  ask: () => T('Расскажешь пару деталей о себе? Так я пойму, кого искать.',
                'Tell me a couple of things about yourself? That’s how I know who to look for.', 'Dime un par de cosas sobre ti. Así sé a quién buscar.'),
  hint: () => T('Выбери вариант или напиши своё', 'Pick some or write your own', 'Elige algunos o escribe la tuya'),
  why: () => T('Зачем это нужно?', 'Why do you need this?', '¿Por qué necesitas esto?'),
  go: () => T('Поехали!', "Let's go!", '¡Vamos!'),
  whyAnswer: () =>
    T(
      'Чтобы искать не всех подряд, а тех, с кем тебе правда будет о чём поговорить. Чем больше я знаю, тем точнее подбираю.',
      'So I look for people you would actually have something to talk about with, not just anyone. The more I know, the better I match.'
    , 'Así busco a personas con las que realmente tengas algo de qué hablar, no a cualquiera. Cuanto más sepa, mejor será la coincidencia.'),
  askName: () => T('Как тебя зовут?', 'What should I call you?', '¿Cómo quieres que te llame?'),
  /**
   * Ответ, который именем быть не может: адрес, ссылка, номер. Раньше такой ответ ПРОХОДИЛ — и
   * человек ходил по приложению под своим адресом почты. Называем причину и говорим, чем это
   * важно: имя тут не для нас, его читают те, кого Kleal приведёт.
   */
  notAName: () => T('Это не похоже на имя, а его увидят те, с кем ты встретишься. Как тебя зовут?',
                    'That doesn’t look like a name — and the people you meet will see it. What should I call you?', 'Eso no parece un nombre — y la gente que conoces lo verá. ¿Cómo te llamo?'),
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

/**
 * ЧТО ИМЕНЕМ БЫТЬ НЕ МОЖЕТ.
 *
 * Имя видят ДРУГИЕ ЛЮДИ: оно стоит в шапке переписки, в карточке кандидата, в приглашении. Адрес
 * почты в этом поле — не опечатка, а утечка: посторонний читает почту человека, не спросив его.
 *
 * Ровно это и случилось на живом аккаунте. Человек ответил своим адресом на «Как тебя зовут?»,
 * разбор ниже отбросил его как «не слово» и вернул набранное ДОСЛОВНО, анкета записала адрес
 * именем, привязка увезла его в аккаунт — и с тех пор он же приезжал обратно при каждом входе,
 * переживая переустановку. Улика, по которой это доказано: заглавная K. Почту сервер приводит к
 * нижнему регистру, а в имени она осталась такой, какой её НАБРАЛИ.
 *
 * Отсекаем то, чем имя не бывает: собаку и косые (адрес, ссылка), три цифры подряд (номер), и
 * требуем хотя бы одну букву. Всё остальное — имя: «Ли», «van Dijk», «Анна-Мария» проходят.
 */
const NOT_A_NAME = /[@/\\]|https?:|\d{3,}/u;

export function isName(value: any): boolean {
  const s = String(value || '').trim();
  return !!s && s.length <= 40 && !NOT_A_NAME.test(s) && /\p{L}/u.test(s);
}

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
  // Запасная ветка отдаёт набранное ДОСЛОВНО — ради имён, которые разбор не считает словами.
  // Она же пропускала адрес почты: у него нет ни одного «слова», и он проезжал целиком.
  if (!words.length || words[0].length > 40) {
    const asIs = text.slice(0, 40);
    return isName(asIs) ? { name: asIs, surname: '' } : { name: '', surname: '' };
  }

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
                'How old are you, and what’s your gender? I use both to rule out who won’t fit.', '¿Cuántos años tienes y cuál es tu género? Los uso para descartar a quienes no se ajusten.'),
  ageLabel: () => T('Твой возраст', 'Your age', 'Tu edad'),
  sexLabel: () => T('Пол', 'Sex', 'Sexo'),
  cta: () => T('Продолжаем', 'Keep going', 'Sigue adelante'),
};

/** «Any is fine» — это НЕ «другое»: человек говорит, что пол ему не важен. */
export const SEXES: [string, string, string][] = [
  ['Male', 'Male', 'Мужской'],
  ['Female', 'Female', 'Женский'],
  ['Any', 'Any is fine', 'Не важно'],
];
/** Испанские подписи отдельной картой по ключу — см. заголовок правки. */
const SEX_ES: Record<string, string> = {
  Male: 'Hombre', Female: 'Mujer', Any: 'Cualquiera vale',
};
export const sexLabel = (k: string) => {
  const s = SEXES.find((x) => x[0] === k);
  return s ? T(s[2], s[1], SEX_ES[s[0]]) : k;
};

export const STEP_AREA = {
  bot: () => T('Где ты бываешь? Дальше выбранного радиуса я никого предлагать не буду.',
                'Where do you spend your time? I won’t suggest anyone beyond the radius you set.', '¿Dónde pasas tu tiempo? No sugeriré a nadie más allá del radio que tú establezcas.'),
  /** Страна и город — две строки, а не одна: в профиль и в поиск уезжает ГОРОД. */
  country: () => T('Страна', 'Country', 'País'),
  city: () => T('Город', 'City', 'Ciudad'),
  /** Та же строка после того, как карту подвинули: там уже не город из списка, а место с карты. */
  address: () => T('Адрес', 'Address', 'Dirección'),
  naming: () => T('Определяем адрес…', 'Finding the address…', 'Buscando la dirección…'),
  radiusLabel: () => T('Как далеко готов(а) ехать?', 'How far are you happy to go?', '¿A qué distancia estás dispuesto a ir?'),
  detect: () => T('Определить моё местоположение', 'Detect my location', 'Detectar mi ubicación'),
  /** Поиск строкой — для тех, чьего города в коротком списке нет. */
  search: () => T('Найти город или адрес', 'Find a city or address', 'Buscar ciudad o dirección'),
  /**
   * Карта — единственный способ назвать место, которого нет в коротком списке городов.
   * Формулировка про КАРТУ, а не про булавку: булавка приколота к центру экрана и не двигается,
   * двигают карту под ней (см. RadiusMap.native — перетаскиваемая метка требует долгого нажатия).
   */
  pinHint: () => T('Нет своего города в списке? Подвинь карту — точка встанет под булавку.',
                   'Your town isn’t on the list? Move the map — the pin marks the spot.', '¿Tu ciudad no está en la lista? Mueve el mapa — el pin marca el lugar.'),
  pinMoved: () => T('Ищем вокруг этой точки.', 'We’ll search around this spot.', 'Buscaremos alrededor de este lugar.'),
  pinReset: (city: string) => T(`Вернуть к ${city}`, `Back to ${city}`, `Volver a ${city}`),
  cta: () => T('Почти закончили', 'We’re almost done', 'Casi terminamos'),
};

export const STEP_LANGUAGES = {
  bot: () =>
    T('На каких языках тебе комфортно? Без общего языка встречи не выйдет — это жёсткий фильтр.',
      'Which languages are you comfortable in? Without a shared one a meetup can’t happen — it’s a hard filter.', '¿En qué idiomas te sientes cómodo/a? Sin uno compartido, no puede haber una quedada — es un filtro obligatorio.'),
  hint: () => T('Выбери варианты или напиши свой', 'Pick some or write your own', 'Elige algunos o escribe la tuya'),
  own: () => T('Свой вариант', 'Your option', 'Tu opción'),
  cta: () => T('Дальше', 'Next', 'Siguiente'),
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
const LANG_ES: Record<string, string> = {
  English: 'Inglés', Spanish: 'Español', German: 'Alemán', French: 'Francés',
  Italian: 'Italiano', Portuguese: 'Portugués', Russian: 'Ruso',
};
export const langLabel = (k: string) => {
  const l = LANGS.find((x) => x[0] === k);
  return l ? `${T(l[2], l[0], LANG_ES[l[0]])} ${l[1]}` : k;
};
export const langPlain = (k: string) => {
  const l = LANGS.find((x) => x[0] === k);
  return l ? T(l[2], l[0], LANG_ES[l[0]]) : k;
};

/** Поле «своё увлечение» прямо в виджете — см. HobbyW в app/chat.tsx. */
export const OWN_INPUT = {
  hobbyPlaceholder: () => T('Своё увлечение', 'Your own hobby', 'Tu propio hobby'),
  langPlaceholder: () => T('Свой язык', 'Your own language', 'Tu propio idioma'),
  add: () => T('Добавить', 'Add', 'Añadir'),
};

export const STEP_HOBBIES = {
  bot: () => T('Чем любишь заниматься? Расскажи своими словами — я запишу.',
                'What do you like doing? Tell me in your own words — I’ll write it down.', '¿Qué te gusta hacer? Dímelo con tus propias palabras — lo apuntaré.'),
  hint: () =>
    T('Пиши как есть: «рыбачу на море по выходным»',
      'Just say it: “I fish at sea on weekends”', 'Solo dilo: “Pescó en el mar los fines de semana”'),
  /** Подпись над записанным. Появляется только когда есть что показать. */
  saved: () => T('Записал', 'Noted', 'Notado'),
  /** Пусто и человек молчит — подсказка вместо пустоты, а не ещё один вопрос. */
  empty: () => T('Пока ничего не записал — расскажи, чем занимаешься',
                 'Nothing noted yet — tell me what you’re into', 'Todavía no hay nada notado — cuéntame qué te gusta'),
  cta: () => T('Готово', 'Done', 'Hecho'),
  /*
    КОЛОДА. Подписи на метках — глаголы, а не «да/нет»: карта задаёт вопрос про занятие, и ответ
    на него это действие, а не согласие. Подсказка под стопкой нужна ровно один раз, но убрать её
    после первой карты нельзя — человек может вернуться на шаг через день и не помнить, куда что
    тянуть.
  */
  deckAdd: () => T('Добавить', 'Add', 'Añadir'),
  deckSkip: () => T('Пропустить', 'Skip', 'Saltar'),
  deckHint: () => T('Влево — добавить, вправо — пропустить', 'Left to add, right to skip', 'Izquierda para añadir, derecha para saltar'),
  /**
   * ЗАХОД ЗАКАНЧИВАЕТ ЧЕЛОВЕК, А НЕ КАРТОЧКА. Раньше каждый свайп влево уходил репликой, и агент
   * отвечал вопросом на каждую — колода превращалась в допрос: карта, вопрос, карта, вопрос.
   * Теперь пальцем проходят сколько хочется, а разговор случается один раз, по кнопке. Число на
   * ней — то, сколько уйдёт разом; без него «записать» значит «записать что?».
   *
   * НЕ «ГОТОВО». Так называется выход со всего шага (`cta`), и две кнопки с одним словом рядом
   * читались как одна и та же, случайно продублированная. Здесь действие другое: не «я закончил»,
   * а «возьми вот эти» — тем же словом, каким шаг отвечает на записанное («Записал»).
   */
  deckSave: (n: number) => T(`Записать · ${n}`, `Save · ${n}`, `Guardar · ${n}`),
  /**
   * ВОЗВРАТ КОЛОДЫ — ПО ПРОСЬБЕ, А НЕ САМ СОБОЙ. После захода агент отвечает вопросом, и колода,
   * встающая обратно поверх этого вопроса, съедала его: человек нажимал «Записать», а на экране
   * снова оказывались карточки — будто нажатие не сработало. Теперь карточки возвращает он сам,
   * когда дочитал и захотел ещё.
   */
  deckMore: () => T('Ещё карточки', 'More cards', 'Más tarjetas'),
  /**
   * РАЗВИЛКА ПЕРВЫМ ХОДОМ. Человек, нажавший «Добавить интерес», делится на двоих: один знает,
   * чего хочет, второму нужен вопрос. Второй ветке кнопка обязательна — пустой композер сам себя
   * вариантом не объявляет, и человек просто не узнает, что помощь существует.
   */
  forkBot: () => T('Расскажи, чем любишь заниматься. Или давай разберёмся вместе — задам несколько вопросов.',
                   'Tell me what you like doing. Or let us work it out together — I will ask a few questions.', 'Dime qué te gusta hacer. O podemos pensarlo juntos — haré algunas preguntas.'),
  forkKnow: () => T('Знаю, чем', 'I know', 'Lo sé'),
  forkHelp: () => T('Помоги разобраться', 'Help me figure it out', 'Ayúdame a aclararlo'),
  /** Копия карты интересов — с борда (кадр «Pick what feels like you»). */
  mapTitle: () => T('Выбери, что про тебя', 'Pick what feels like you', 'Elige lo que te define'),
  /* Подсказка про нажатие, а не про жест: лупы и перетаскивания у карты больше нет. */
  mapHint: () => T('Нажми на тему — внутри занятия. Отметь хотя бы три.',
                   'Tap a topic to see what is inside. Pick at least three.',
                   'Toca un tema para ver qué hay dentro. Elige al menos tres.'),
  mapMin: (n: number) => T(`Выбери хотя бы ${n}`, `Choose at least ${n}`, `Elige al menos ${n}`),
  mapCount: (n: number) => T(`Выбрано ${n}`, `${n} selected`, `${n} seleccionados`),
  mapCta: () => T('Дальше', 'Continue', 'Continuar'),
  /** Второй выход с карты — в разговор: своё занятие называют словами, ключ ему подберёт агент. */
  mapOwn: () => T('Добавить своё', 'Add your own', 'Añadir lo tuyo'),
  ownAsk: () => T('Напиши своими словами, чем ещё увлекаешься, — подберу и запишу.',
                  'Tell me in your own words what else you are into — I will find it and add it.',
                  'Dime con tus palabras qué más te gusta: lo busco y lo anoto.'),
  /** Строка над картой. */
  mapAll: () => T('Все темы', 'All topics', 'Todos los temas'),
  mapTopics: (n: number) => T(`${n} тем`, `${n} topics`, `${n} temas`),
  mapPickedShort: (n: number) => T(`выбрано ${n}`, `${n} picked`, `${n} elegidos`),
  /** Первая реплика агента ПОСЛЕ карты: он видит выбранное и идёт от него, а не спрашивает заново. */
  /**
   * Закрывающая реплика по «Готово». Раньше шаг обрывался молча: человек нажимал кнопку и просто
   * оказывался на фото — без единого слова о том, что запись интересов на этом закончена и что
   * дальше с ними будет. Молчание в разговоре читается как сбой, а не как завершение.
   */
  done: (n: number) =>
    T('Записал ' + n + ' ' + plural(n, 'интерес', 'интереса', 'интересов') +
      '. Дальше искать буду по ним — дополнить или убрать всегда можно в профиле.',
      'Saved ' + n + (n === 1 ? ' interest' : ' interests') +
      '. That is what I will search by — you can add or remove them in your profile anytime.',
      'Apuntado: ' + n + (n === 1 ? ' interés' : ' intereses') +
      '. Buscaré por ellos — puedes añadir o quitar los que quieras en tu perfil.'),
  afterMap: () => T('Отметил. Расскажи про что-нибудь из этого подробнее — или добавь своё.',
                    'Noted. Tell me more about one of these — or add your own.', 'Notado. Cuéntame más sobre uno de ellos — o añade el tuyo propio.'),
  /**
   * ЧТО УХОДИТ РЕПЛИКОЙ, а не что написано на кнопке. «Помоги разобраться» модели ничего не
   * говорит: на живом прогоне она дважды ответила дежурным «а чем ещё занимаешься?», потому что
   * зацепиться было не за что. Реплика должна звучать как то, что человек сказал бы сам.
   */
  forkHelpSaid: () => T('Не знаю, с чего начать — спрашивай',
                        'I do not know where to start — ask me', 'No sé por dónde empezar — pregúntame'),
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
const HOBBY_ES: Record<string, string> = {
  coding: 'Programar', hiking: 'Senderismo', gaming: 'Videojuegos', yoga: 'Yoga', cooking: 'Cocinar',
  music: 'Música', coffee: 'Café', photography: 'Fotografía', travel: 'Viajar', football: 'Fútbol',
};
export const hobbyLabel = (k: string) => {
  const h = HOBBIES.find((x) => x[0] === k);
  return h ? `${T(h[2], HOBBY_EN[k], HOBBY_ES[k])} ${h[1]}` : k;   // своё написанное показывается как есть
};
export const hobbyPlain = (k: string) => {
  const h = HOBBIES.find((x) => x[0] === k);
  return h ? T(h[2], HOBBY_EN[k], HOBBY_ES[k]) : k;
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
  compose: () => T('Расскажи Kleal больше…', 'Tell Kleal more…', 'Dile a Kleal más…'),
  done: () => T('Это всё', "That's enough", 'Eso es suficiente'),
  /**
   * «Это всё» заканчивает разговор про увлечения — а это единственный шаг, который наполняет
   * профиль по-настоящему. Раньше чип срабатывал мгновенно, наравне с обычными вариантами ответа,
   * и человек выходил из разговора, не поняв, что вышел. Теперь Kleal сначала говорит, что будет.
   */
  endAsk: () =>
    T(
      'Если закончим — про увлечения я больше не расспрашиваю, дальше только фото и всё. Чем больше расскажешь сейчас, тем точнее я ищу; добавить что-то потом можно будет в профиле.',
      'If we stop here I won’t ask about your interests again — after this it’s just the photo. The more you tell me now, the sharper I search; you can always add more later in your profile.'
    , 'Si paramos aquí, no volveré a preguntar sobre tus intereses — después de esto solo quedará la foto. Cuanto más me digas ahora, más precisa será mi búsqueda; siempre puedes añadir más información después en tu perfil.'),
  endYes: () => T('Да, закончить', 'Yes, finish', 'Sí, terminar'),
  endNo: () => T('Расскажу ещё', 'I’ll add more', 'Añadiré más'),
  cont: () => T('Продолжить', 'Continue', 'Continuar'),
  /** Разговор про интерес окончен: либо назад к чипам за следующим, либо дальше по анкете. */
  more: () => T('Добавить ещё', 'Add another', 'Añade otro'),
  finish: () => T('Завершить', 'Finish', 'Finalizar'),
  back: () => T('Что ещё тебе нравится?', 'What else are you into?', '¿Qué más te interesa?'),
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

/**
 * ПОДТВЕРЖДЕНИЕ ПРИДУМАННОГО ИНТЕРЕСА.
 *
 * Сервер не записывает слово, которого нет в общей таксономии, пока человек его не подтвердил, —
 * и правильно делает: модель предлагает, решает человек. Раньше анкета этого не умела вовсе, и
 * придуманный интерес доживал до самого конца, где `register` отклонял ВЕСЬ профиль одной строкой
 * «Профиль не сохранился». Человек не мог закончить анкету и не понимал почему.
 */
export const CONFIRM_INTEREST = {
  ask: () => T('Записать как интерес?', 'Save as an interest?', '¿Guardar como interés?'),
  /** Подпись приходит с сервера — это слово человека, приведённое к именительному падежу. */
  yes: (label: string) => T('Да, «' + label + '»', 'Yes, “' + label + '”', 'Sí, «' + label + '»'),
  no: () => T('Не надо', 'Skip', 'Saltar'),
  /** Модель не смогла понять сказанное как интерес. Молчать нельзя: человек ждёт, что записали. */
  unclear: () => T('Это я не смог записать интересом — скажи иначе?',
                   'I could not turn that into an interest — say it another way?', 'No pude convertir eso en un interés — ¿lo expresas de otra manera?'),
};

export const STEP_PHOTO = {
  greet: (name: string) => T('Рад знакомству, ' + name + '!', 'Nice to meet you, ' + name + '!',
                             'Encantado de conocerte, ' + name + '.'),
  ask: () =>
    T(
      'Давай добавим фото профиля, чтобы тебя узнавали на встречах.',
      'Let’s add a profile photo so people recognize you at meetups.'
    , 'Añadamos una foto de perfil para que la gente te reconozca en las quedadas.'),
  hint: () => T('Добавь фото', 'Add a photo', 'Añade una foto'),
  take: () => T('Сделать фото', 'Take photo', 'Tomar foto'),
  upload: () => T('Загрузить фото', 'Upload photo', 'Subir foto'),
  skip: () => T('Пропустить', 'Skip', 'Saltar'),
  selfieTitle: () => T('Сделай селфи', 'Take a selfie', 'Hazte una selfie'),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),
  /** Хвалить лицо человека агент не должен — говорим о том, что с фото делать дальше. */
  praise: () => T('Годится. Его увидят те, кому ты отправишь приглашение.',
                  'That works. The people you invite will see it.', 'Perfecto. La gente que invites lo verá.'),
  pickHint: () => T('Выбери, нажав на вариант', 'Select an option by tap', 'Selecciona una opción tocándola'),
  use: () => T('Оставить', 'Use it', 'Usarla'),
  retake: () => T('Переснять', 'Retake', 'Repetir'),
  confirmed: () => T('Отлично — теперь это твоё фото профиля.', 'Love it — that’s your profile photo now.', 'Genial — ya es tu foto de perfil.'),
  cardTitle: () => T('Фото профиля установлено', 'Profile photo set', 'Foto de perfil establecida'),
  cardSub: (name: string) => T('Выглядишь отлично, ' + name, 'Looking sharp, ' + name,
                               'Te queda genial, ' + name),
  next: () => T('Теперь найдём твоих людей.\nКогда будешь готов(а).', 'Now let’s find your people.\nReady when you are.', 'Ahora busquemos a tus personas.\nListo cuando tú lo estés.'),
  cta: () => T('Поехали', 'Let’s go', 'Vamos'),
};

export const SUMMARY = {
  /*
   * ТРИ РАЗНЫЕ НЕУДАЧИ СОХРАНЕНИЯ, И ГОВОРИТЬ О НИХ НАДО ПО-РАЗНОМУ.
   *
   * Раньше на всё было одно «Профиль не сохранился. Проверь связь» — и люди чинили интернет вместо
   * интереса. Сервер при этом отвечал и называл причину прямо.
   *
   * Строки восстановлены после того, как я их СНЁС: выложил свою редакцию этого файла поверх
   * чужой, и `app/summary.tsx` остался звать функции, которых больше нет. Экран падал на вызове
   * `undefined` ровно там, где должен был объяснить человеку, что случилось.
   */
  /** Сервер назвал интересы, которых не знает. Их видно, и с ними можно что-то сделать. */
  saveRejectedInterests: (list: string) =>
    T('Профиль не сохранился: Kleal пока не знает такие интересы — ' + list +
      '. Убери их или назови привычнее.',
      'Your profile didn’t save: Kleal doesn’t know these interests yet — ' + list +
      '. Remove them or name them differently.',
      'Tu perfil no se guardó: Kleal todavía no conoce estos intereses — ' + list +
      '. Quítalos o llámalos de otra manera.'),
  /** Сервер отказал по другой причине и назвал её. Показываем как есть, не пряча. */
  /**
   * Нет сессии. Отдельный случай, и он не про ошибку: профиль теперь записывается только своему
   * аккаунту, а у человека его на этом устройстве нет — вошёл до появления сессий или вышел.
   * Повторять нажатие бессмысленно, поэтому здесь не «попробуй ещё», а дорога ко входу.
   */
  saveNeedsSignIn: () =>
    T('Чтобы сохранить профиль, нужно войти — так он не потеряется при смене телефона.',
      'Sign in to save your profile — that way it survives a change of phone.', 'Inicia sesión para guardar tu perfil, así se mantendrá aunque cambies de teléfono.'),
  saveGoSignIn: () => T('Войти', 'Sign in', 'Iniciar sesión'),
  /** Сервер не принял имя. Единственный отказ, который чинится прямо в анкете. */
  saveBadName: () =>
    T('Профиль не сохранился: в имени стоит адрес почты. Kleal спросит имя заново — его увидят другие люди.',
      'Your profile didn’t save: the name field holds an email address. Kleal will ask for your name again — other people see it.', 'Tu perfil no se guardó: el campo de nombre contiene una dirección de correo. Kleal te pedirá tu nombre de nuevo — los demás lo ven.'),
  saveFixName: () => T('Вписать имя', 'Enter my name', 'Escribe mi nombre'),
  saveRejected: (why: string) =>
    T('Профиль не сохранился: ' + why, 'Your profile didn’t save: ' + why,
      'Tu perfil no se guardó: ' + why),
  /** Настоящий обрыв: запрос не дошёл или ответ не разобрался. */
  saveOffline: () =>
    T('Профиль не сохранился. Проверь связь и попробуй ещё раз.',
      'Your profile didn’t save. Check your connection and try again.', 'Tu perfil no se guardó. Comprueba tu conexión e inténtalo de nuevo.'),
  /** Пока модель составляет описание. НЕ запасной перечень: тот только на случай отказа. */
  composing: () => T('Kleal составляет описание…', 'Kleal is writing your description…', 'Kleal escribe tu descripción…'),
  /** Выход из тупика: убрать названные интересы и сохранить. Разбор — в app/summary.tsx. */
  dropRejected: () => T('Убрать их и сохранить', 'Remove them and save', 'Elimínalos y guarda'),
  confidence: () => T('Точность профиля', 'Profile confidence', 'Confianza en el perfil'),
  klealSummary: () => T('Что понял Kleal', 'Kleal’s summary', 'Resumen de Kleal'),
  updatedToday: () => T('Обновлено сегодня', 'Updated today', 'Actualizado hoy'),
  viewAll: () => T('Все настройки профиля', 'View all profile settings', 'Ver todos los ajustes del perfil'),
  planTitle: () => T('План обновлён', 'Plan updated', 'Plan actualizado'),
  planBody: () =>
    T(
      'Чем больше Kleal о тебе знает, тем лучше понимает твои намерения и точнее сводит с нужными людьми.',
      'The more Kleal knows about you, the better it can understand your intentions and connect you with the right people.'
    , 'Cuanto más conozca Kleal sobre ti, mejor podrá entender tus intenciones y conectarte con las personas adecuadas.'),
  done: () => T('Готово', 'Done', 'Hecho'),
};

/**
 * Кадр A.15 — и он же пока главный экран приложения.
 *
 * Поздравление говорится РОВНО один раз — сюда попадают сразу после записи профиля. Приветствие
 * при каждом запуске живёт на главном экране, у него своё (src/home.ts).
 */
export const DONE_SCREEN = {
  title: () => T('Поздравляем!\nТы в игре!', 'Congratulations!\nYou are on the board!', '¡Enhorabuena!\nEstás en el tablón'),
  cta: () => T('Создать интент', 'Create Intent', 'Crear propuesta'),
};

export const COMPOSER_PLACEHOLDER = () => T('Сообщение…', 'Message…', 'Mensaje…');

export const NAV = () => [
  T('Интенты', 'My Intents', 'Mis propuestas'),
  T('Поиск', 'Search', 'Buscar'),
  T('Сообщения', 'Messages', 'Mensajes'),
  T('Профиль', 'Profile', 'Perfil'),
];

/**
 * На каком шаге продолжать. Онбординг можно закрыть на середине — телефон разрядился, отвлекли, —
 * и вернувшись человек должен попасть туда, где остановился, а не в начало и уж точно не в тупик.
 *
 * Первая версия делала именно тупик: чипы первого шага прятались, если имя уже сохранено, а сам шаг
 * оставался первым. На экране висел вопрос и ни одной кнопки под ним.
 */
/**
 * На каком шаге продолжить того, кто вышел и вернулся.
 *
 * ЛЕСЕНКА ПО ЗАПОЛНЕННОСТИ, а не запомненный номер шага, и это правильно: номер разошёлся бы с
 * профилем при первой же правке через «Профиль → Изменить», и человека возвращало бы на шаг,
 * который он давно прошёл.
 *
 * НО ПУСТОТА И ОТКАЗ — РАЗНЫЕ ВЕЩИ, и на этом лесенка спотыкалась. Фото можно пропустить, шаг
 * честно пишет `photoStatus: 'skipped'` — а лесенка смотрела только на само фото и возвращала на
 * тот же экран снова. Человек нажимал «Пропустить», выходил, возвращался и опять видел просьбу
 * добавить фото: отказ не сохранялся, потому что его никто не читал. Проверяем и то, и другое.
 */
export function resumeStep(p: any): StepId {
  if (!p || !p.name) return 'start';
  if (!p.age || !p.gender) return 'basics';
  if (!p.city) return 'area';
  if (!(p.languages?.comfortable || []).length) return 'languages';
  if (!(p.interests?.explicit || []).length) return 'hobbies';
  return 'photo';
}

/**
 * Анкета пройдена целиком — включая фото, которое могли и осознанно пропустить.
 *
 * Отдельной функцией, а не ступенью в `resumeStep`, потому что «всё заполнено» — это НЕ шаг: за
 * ним идёт сводка, у которой своя страница. Дописать 'summary' в `StepId` значило бы завести
 * седьмой шаг, которого нет ни в порядке `ORDER`, ни в проценте `STEP_PROGRESS`, ни в наборе
 * виджетов, — и каждый разбор по шагам пришлось бы чинить ради значения, которое там никогда не
 * появляется.
 *
 * Зачем это нужно: человек, дошедший до сводки и вышедший, не нажав «Готово», имел `done: false`
 * при полностью заполненном профиле. `resumeStep` возвращал ему 'photo' — единственную оставшуюся
 * ступень, — и он снова видел просьбу про фото, которое уже добавил или уже пропустил.
 */
export function onbComplete(p: any): boolean {
  if (resumeStep(p) !== 'photo') return false;
  return !!p.photo || p.photoStatus === 'skipped';
}

/** Есть ли вообще что продолжать. */
export function hasProgress(p: any): boolean {
  return !!(p && p.name);
}

export const RESUME = {
  line: (name: string) => T('С возвращением, ' + name + '! Продолжим с того места.',
                            'Welcome back, ' + name + '! Let’s pick up where we left off.',
                            '¡Bienvenido de nuevo, ' + name + '! Seguimos donde lo dejamos.'),
  restart: () => T('Начать заново', 'Start over', 'Volver a empezar'),
  /** Про вход сказано отдельно: раньше кнопка молча разлогинивала, и об этом не предупреждали. */
  restartAsk: () => T('Начать анкету заново? Всё, что ты рассказал, сотрётся. Вход останется — заново заходить не придётся.',
                      'Start the questionnaire over? Everything you told me will be erased. You stay signed in.', '¿Quieres volver a hacer la encuesta? Todo lo que me dijiste se borrará. Te quedas conectado.'),
  restartYes: () => T('Да, заново', 'Yes, start over', 'Sí, empezar de nuevo'),
  restartNo: () => T('Отмена', 'Cancel', 'Cancelar'),
};
