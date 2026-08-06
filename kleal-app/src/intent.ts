/**
 * Мастер интента — новый борд «1:1 Online», кадры O.05–O.09.
 *
 * UX-каркас: копия и правила здесь, вид в app/intent.tsx. Английские строки взяты с кадров
 * ДОСЛОВНО, русские написаны, а не переведены машинно.
 *
 * Устройство по борду:
 *
 *  O.05  «How do you want to meet?» — строки Offline / Online / Hybrid с галочкой. Кнопки «Дальше»
 *        нет: выбор строки сам ведёт дальше, агент коротко отвечает «Awesome!».
 *  O.06  «How many people will there be?» — 1:1 или группа, устроено так же.
 *  O.07–O.09  «A few details, and I'll search» — три шага под степпером 1–2–3: когда (дата,
 *        круглый циферблат времени, часовой пояс) → кого (аудитория и кольцо возраста) → где
 *        происходит звонок (ссылка). Третий шаг зависит от типа: у офлайна вместо ссылки район и
 *        радиус (кадр прежнего борда OF.09 — в новом наборе офлайн-кадра нет). Гибрид получает шаг
 *        ссылки: онлайн-часть встречи без ссылки не существует, а место гибрид по определению
 *        оставляет свободным. Кадра под гибрид на борде нет — это осознанное допущение, не факт.
 *
 * Тема сюда приходит ГОТОВОЙ из разговора создания (app/create.tsx): вопрос «что хочешь сделать?»
 * здесь не задаётся — человек на него только что ответил.
 *
 * Ключи (offline/online/hybrid, 1:1/group, коды районов) НЕ придуманы заново — совпадают с теми,
 * что уходят в /api/agent/plan и /api/agent/match.
 */
import { T, getLang } from './i18n';

export type IntentStepId = 'how' | 'size' | 'when' | 'who' | 'place' | 'link' | 'summary';

// ---------------------------------------------------------------- общее

export const INTENT = {
  allIntents: () => T('Все интенты', 'All intents'),
  awesome: () => T('Отлично!', 'Awesome!'),
  next: () => T('Дальше', 'Next'),
};

// ---------------------------------------------------------------- O.05 · тип встречи

export const STEP_HOW = {
  ask: () => T('Как хочешь встретиться?', 'How do you want to meet?'),
};

/** [ключ, EN, RU, подпись EN, подпись RU]. Подписи — с кадра, дословно. */
export const FORMATS: [string, string, string, string, string][] = [
  ['offline', 'Offline', 'Офлайн', 'In person', 'Вживую'],
  ['online', 'Online', 'Онлайн', 'Video / voice', 'Видео или голос'],
  ['hybrid', 'Hybrid', 'Гибрид', 'Both online & offline', 'И онлайн, и вживую'],
];
export const formatLabel = (k: string) => {
  const f = FORMATS.find((x) => x[0] === k);
  return f ? T(f[2], f[1]) : k;
};
export const formatSub = (k: string) => {
  const f = FORMATS.find((x) => x[0] === k);
  return f ? T(f[4], f[3]) : '';
};

// ---------------------------------------------------------------- O.06 · сколько людей

export const STEP_SIZE = {
  ask: () => T('Сколько вас будет?', 'How many people will there be?'),
};

/**
 * «Минимум 3» в подписи группы — то же GROUP_MIN_TOTAL, из которого собран групповой слой сервера:
 * группа — это три человека и больше, включая тебя.
 *
 * Ключи совпадают с ALLOWED_FORMATS матчинга (matching_core/intent_compiler/compiler.py) и уходят
 * в intent.format НАПРЯМУЮ. Это не косметика: §5.3 считает интент достаточно описанным только когда
 * заполнены и mode, и format. Проверено на стенде — без format ответ приходит с
 * minimally_sufficient.ok = false, то есть поиск идёт по недосказанному запросу.
 */
export const GROUP_MIN_TOTAL = 3;
export const SIZES: [string, string, string, string, string][] = [
  ['1:1', '1:1', '1:1', 'Just the two of us', 'Только вы вдвоём'],
  ['group', 'Group', 'Группа', '3–5 people · free · needs at least 3', '3–5 человек · бесплатно · нужно минимум 3'],
];
export const sizeLabel = (k: string) => {
  const s = SIZES.find((x) => x[0] === k);
  return s ? T(s[2], s[1]) : k;
};
export const sizeSub = (k: string) => {
  const s = SIZES.find((x) => x[0] === k);
  return s ? T(s[4], s[3]) : '';
};

// ---------------------------------------------------------------- O.07–O.09 · детали

export const DETAILS = {
  title: () => T('Пара деталей — и я ищу', "A few details, and I'll search"),
  subWhen: () => T('Когда и где удобно?', 'When and where works best?'),
  subWho: () => T('Кого ты ищешь?', 'Who are you looking for?'),
  subLink: () => T('Где пройдёт звонок?', 'Where does the call happen?'),
  subPlace: () => T('Где удобно встретиться?', 'Where works best to meet?'),

  date: () => T('Дата', 'Date'),
  time: () => T('Время', 'Time'),
  timeZone: () => T('Часовой пояс', 'Time Zone'),

  audience: () => T('Аудитория', 'Audience'),
  age: () => T('Возраст', 'Age'),

  link: () => T('Ссылка', 'Link'),
  linkPlaceholder: () => 'https://yourlink.com',
  /** Дисклеймер с кадра O.09, дословно. */
  linkNote: () =>
    T(
      'Ссылками делятся сами люди. Открывать её или нет — решаешь ты. Kleal не отвечает за сторонний контент и действия.',
      'External links are shared by users. You choose whether to open them. Kleal isn’t responsible for third-party content or actions.'
    ),

  district: () => T('Район', 'District'),
  radius: () => T('Как далеко готов(а) ехать?', 'How far are you happy to go?'),

  // O.07a — лист выбора пояса. Заголовок с кадра дословно.
  tzSheetTitle: () => T('Часовой пояс GMT', 'Time Zone GMT'),
  apply: () => T('Применить', 'Apply'),
  cancel: () => T('Отмена', 'Cancel'),
};

/**
 * O.10a — лист «что поменять» над сводкой. Подписи строк — с кадра; значения экран собирает из
 * черновика сам. Ключ каждой строки — шаг мастера, на который ведёт «Edit».
 */
export const EDIT_SHEET = {
  title: () => T('Что хочешь поменять?', 'What are you going change?'),
  theme: () => T('Тема интента', 'Theme of Intent'),
  mode: () => T('Режим встречи', 'Mode of meeting'),
  format: () => T('Формат', 'Format'),
  datetime: () => T('Дата и время', 'Date & Time'),
  audience: () => T('Аудитория и возраст', 'Audience & Age'),
  link: () => T('Ссылка', 'Link'),
  noData: () => T('Нет данных', 'No Data'),
  edit: () => T('Изменить', 'Edit'),
};

/** Город без пути и подчёркиваний: Europe/Buenos_Aires → «Buenos Aires». Строки листа O.07a. */
export function tzCity(tz: string): string {
  return String(tz || '').replace(/_/g, ' ').split('/').pop() || tz;
}

/**
 * Даты для чипов — от сегодня, как на кадре: «Wed Jul 22», по-русски «ср, 22 июл.». Интент живёт
 * часы-дни, календарь на месяц ему не нужен.
 */
export function dateChips(n = 8, from = new Date()): { key: string; label: string }[] {
  const out: { key: string; label: string }[] = [];
  const loc = getLang() === 'ru' ? 'ru-RU' : 'en-US';
  for (let i = 0; i < n; i++) {
    const d = new Date(from);
    d.setDate(d.getDate() + i);
    out.push({
      key: d.toISOString().slice(0, 10),
      label: d.toLocaleDateString(loc, { weekday: 'short', month: 'short', day: 'numeric' }),
    });
  }
  return out;
}

/** Минуты суток → «20:00». Одно место, чтобы циферблат, поля и запрос не разошлись в формате. */
export function hhmm(minutes: number): string {
  const m = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

/**
 * Строка времени, которая уходит В ЗАПРОС, — всегда английская, независимо от языка интерфейса.
 *
 * Срочность на той стороне определяется поиском слов в тексте: SOON_WORDS = today/tonight/evening/
 * tomorrow. Русских слов там нет ни одного. Отправить «сегодня 20:00» — значит получить urgency
 * «none»: запрос на сегодняшний вечер ранжировался бы как «когда-нибудь».
 */
export function timeQueryFromDate(dateKey: string, minutes: number, from = new Date()): string {
  const t = hhmm(minutes);
  const today = from.toISOString().slice(0, 10);
  const tomorrow = new Date(from);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (dateKey === today) return `today ${t}`;
  if (dateKey === tomorrow.toISOString().slice(0, 10)) return `tomorrow ${t}`;
  const d = new Date(dateKey + 'T12:00:00');
  return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} ${t}`;
}

/** Часовой пояс устройства — IANA-имя, оно же уходит в ctx.tz. */
export function deviceTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/** Подпись пояса в духе кадра («Barcelona, Spain (GMT+2)») — имя зоны плюс смещение. */
export function tzDisplay(tz: string): string {
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'shortOffset' })
      .formatToParts(new Date());
    const off = parts.find((p) => p.type === 'timeZoneName')?.value || '';
    return `${tz.replace(/_/g, ' ').split('/').pop()} (${off})`;
  } catch {
    return tz;
  }
}

/**
 * Зоны для выпадающего списка: устройство первым, дальше несколько ходовых. Список короткий
 * намеренно — это выбор «я сейчас не там, где телефон думает», а не справочник всех зон мира.
 */
export function tzOptions(): string[] {
  const base = [deviceTz(), 'Europe/Madrid', 'Europe/London', 'Europe/Berlin', 'Europe/Moscow', 'UTC'];
  return base.filter((v, i) => base.indexOf(v) === i);
}

/**
 * Наивная проверка ссылки. Не валидатор: по дисклеймеру борда ссылка — ответственность человека,
 * здесь отсекается только то, что заведомо не откроется.
 */
export function looksLikeUrl(s: string): boolean {
  return /^https?:\/\/\S+\.\S+/.test(String(s || '').trim());
}

// ---------------------------------------------------------------- O.10 · сводка перед поиском

export const SUMMARY_O10 = {
  title: () => T('Вот что получилось', "Here's what I got"),
  /** Пузырь-примечание с кадра, дословно. */
  note: () =>
    T(
      'Проверь — поправить можно что угодно. Поиск мы подгоним под настройки твоего профиля и этот интент.',
      "Check it — edit anything if needed. We'll tailor the search to your profile settings and this intent."
    ),
  mode: () => T('Тип', 'Mode'),
  format: () => T('Формат', 'Format'),
  category: () => T('Категория', 'Category'),
  audience: () => T('Аудитория', 'Audience'),
  summaryLabel: () => T('Сводка Kleal:', 'Kleal summary:'),
  start: () => T('Начать поиск', 'Start search'),
  edit: () => T('Поправить', 'Edit'),
};

/** «Thu, 23 July» с кадра — дата сводки, на языке интерфейса. */
export function summaryDate(dateKey: string): string {
  const loc = getLang() === 'ru' ? 'ru-RU' : 'en-US';
  const d = new Date(dateKey + 'T12:00:00');
  return d.toLocaleDateString(loc, { weekday: 'short', day: 'numeric', month: 'long' });
}

/** Смещение пояса для строки времени: «(GMT+2)». Вырезается из tzDisplay, чтобы не считать дважды. */
export function tzOffsetLabel(tz: string): string {
  const m = tzDisplay(tz).match(/\(([^)]+)\)/);
  return m ? `(${m[1]})` : '';
}

/**
 * «Сводка Kleal» на O.10. На борде этот текст пишет модель («You want to speak Spanish, not study
 * it…») — серверной ручки под это пока нет, и в каркасе стоит детерминированный шаблон из
 * собранных фактов. Он не выдумывает ничего, чего человек не выбирал; умный пересказ — отдельная
 * работа на стороне buddy, помечено в ROADMAP.
 */
export function intentSummaryText(o: {
  topic: string; size?: string; sex?: string; minAge: number; maxAge: number;
  dateKey: string; minutes: number;
}): string {
  const who =
    o.size === 'group'
      ? T('компанию из 3–5 человек', 'a small group of 3–5')
      : T('одного человека', 'one person');
  const aud = o.sex && o.sex !== 'Any'
    ? (o.sex === 'Female' ? T('женщину', 'a woman') : T('мужчину', 'a man')) + ', '
    : '';
  const when = `${summaryDate(o.dateKey)} ${T('около', 'around')} ${hhmm(o.minutes)}`;
  return o.topic
    ? T(
        `Ты хочешь: ${o.topic}. Kleal ищет ${who} — ${aud}${o.minAge}–${o.maxAge}, со свободным временем ${when}.`,
        `You're after: ${o.topic}. Kleal is looking for ${who} — ${aud}${o.minAge}–${o.maxAge}, free ${when}.`
      )
    : T(
        `Kleal ищет ${who} — ${aud}${o.minAge}–${o.maxAge}, со свободным временем ${when}.`,
        `Kleal is looking for ${who} — ${aud}${o.minAge}–${o.maxAge}, free ${when}.`
      );
}

// ---------------------------------------------------------------- районы (офлайн, прежний кадр OF.09)

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

// ---------------------------------------------------------------- поиск и выдача

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
