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
 *        происходит звонок (ссылка). Последний шаг зависит от типа: у офлайна вместо ссылки район и
 *        радиус (кадр прежнего борда OF.09 — в новом наборе офлайн-кадра нет).
 *
 *        ГИБРИД получает ОБА блока на одном шаге — кадр HY.09 «3 of 3 · place and link». Раньше он
 *        шёл по ветке ссылки: считалось, что место гибрид оставляет свободным. Борд говорит
 *        обратное и прямым текстом — HY.20a: «Anyone who can't come in person has no way to join
 *        until you add a link», HY.20b: «Anyone who wants to come in person has nowhere to go until
 *        you name a place — hybrid needs both».
 *
 * Тема сюда приходит ГОТОВОЙ из разговора создания (app/create.tsx): вопрос «что хочешь сделать?»
 * здесь не задаётся — человек на него только что ответил.
 *
 * Ключи (offline/online/hybrid, 1:1/group, коды районов) НЕ придуманы заново — совпадают с теми,
 * что уходят в /api/agent/plan и /api/agent/match.
 */
import { T, getLang, plural, dateLocale } from './i18n';
import { interestLabel } from './interest-label';

export type IntentStepId = 'how' | 'size' | 'capacity' | 'when' | 'who' | 'nature' | 'place' | 'link' | 'both' | 'summary';

// ---------------------------------------------------------------- общее

export const INTENT = {
  allIntents: () => T('Все интенты', 'All intents', 'Todas las propuestas'),
  awesome: () => T('Отлично!', 'Awesome!', '¡Genial!'),
  next: () => T('Дальше', 'Next', 'Siguiente'),
};

// ---------------------------------------------------------------- O.05 · тип встречи

export const STEP_HOW = {
  ask: () => T('Как хочешь встретиться?', 'How do you want to meet?', '¿Cómo quieres reunirte?'),
};

/** [ключ, EN, RU, подпись EN, подпись RU]. Подписи — с кадра, дословно. */
export const FORMATS: [string, string, string, string, string][] = [
  ['offline', 'Offline', 'Офлайн', 'In person', 'Вживую'],
  ['online', 'Online', 'Онлайн', 'Video / voice', 'Видео или голос'],
  ['hybrid', 'Hybrid', 'Гибрид', 'Both online & offline', 'И онлайн, и вживую'],
];
/**
 * «Presencial», не «Sin conexión»: offline у нас значит «встретиться вживую», а не «нет интернета».
 * Ровно этой подменой смысла модель испортила подпись формата при первом переводе.
 */
const FORMAT_ES: Record<string, [string, string]> = {
  offline: ['Presencial', 'En persona'],
  online: ['Online', 'Vídeo o voz'],
  hybrid: ['Híbrido', 'Online y presencial'],
};
export const formatLabel = (k: string) => {
  const f = FORMATS.find((x) => x[0] === k);
  return f ? T(f[2], f[1], FORMAT_ES[f[0]]?.[0]) : k;
};
export const formatSub = (k: string) => {
  const f = FORMATS.find((x) => x[0] === k);
  return f ? T(f[4], f[3], FORMAT_ES[f[0]]?.[1]) : '';
};

// ---------------------------------------------------------------- O.06 · сколько людей

export const STEP_SIZE = {
  ask: () => T('Сколько вас будет?', 'How many people will there be?', '¿Cuántas personas habrá?'),
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
export const GROUP_FREE_MAX_TOTAL = 5;
export const GROUP_PLUS_MAX_TOTAL = 20;
export type IntentSize = '1:1' | 'group';
export const SIZES: [string, string, string, string, string][] = [
  ['1:1', '1:1', '1:1', 'Just the two of us', 'Только вы вдвоём'],
  ['group', 'Group', 'Группа', 'Choose the number of people next', 'Размер выберешь на следующем шаге'],
];

/**
 * Старые deep links и сохранённые черновики называли один и тот же групповой flow по-разному.
 * Ни один групповой legacy-токен не должен проваливаться в 1:1 из-за незнакомой строки.
 */
export function normalizeIntentSize(value: unknown, groupSize?: unknown): IntentSize | undefined {
  const raw = String(value ?? '').trim().toLowerCase().replace(/[\s_]+/g, '-');
  if (['1:1', '1-to-1', 'one-to-one', 'one-on-one', 'oneonone', 'pair', 'solo'].includes(raw)) return '1:1';
  if ([
    'group', 'group-plus', 'small', 'large', 'small-group', 'large-group',
    'smallgroup', 'largegroup', 'party', 'crowd',
  ].includes(raw)) return 'group';
  const total = Number(groupSize);
  return Number.isFinite(total) && total >= GROUP_MIN_TOTAL ? 'group' : undefined;
}

/** Legacy large/group-plus starts at its old lower bound; all other group links start at three. */
export function initialGroupSize(value: unknown, groupSize?: unknown): number {
  const parsed = Number(groupSize);
  if (Number.isFinite(parsed)) {
    return Math.max(GROUP_MIN_TOTAL, Math.min(GROUP_PLUS_MAX_TOTAL, Math.round(parsed)));
  }
  const raw = String(value ?? '').trim().toLowerCase().replace(/[\s_]+/g, '-');
  return ['large', 'large-group', 'largegroup', 'group-plus', 'crowd'].includes(raw)
    ? GROUP_FREE_MAX_TOTAL + 1
    : GROUP_MIN_TOTAL;
}
const SIZE_ES: Record<string, [string, string]> = {
  '1:1': ['1:1', 'Solo vosotros dos'],
  group: ['Grupo', 'El tamaño lo eliges en el siguiente paso'],
};
export const sizeLabel = (k: string) => {
  const s = SIZES.find((x) => x[0] === normalizeIntentSize(k));
  return s ? T(s[2], s[1], SIZE_ES[s[0]]?.[0]) : k;
};
export const sizeSub = (k: string) => {
  const s = SIZES.find((x) => x[0] === normalizeIntentSize(k));
  return s ? T(s[4], s[3], SIZE_ES[s[0]]?.[1]) : '';
};

/** Размер — отдельный шаг единого Group-flow; тариф не превращается в третий формат. */
export const GROUP_SIZE = {
  ask: () => T('Сколько человек будет в группе?', 'How many people will be in the group?', '¿Cuántas personas habrá en el grupo?'),
  sub: () => T('Включая тебя. Минимум 3 человека.', 'Including you. At least 3 people.', 'Incluyendo a ti. Al menos 3 personas.'),
  row: () => T('Размер группы', 'Group size', 'Tamaño del grupo'),
  people: (n: number) => T(`${n} ${plural(n, 'человек', 'человека', 'человек')}`, `${n} people`, `${n} personas`),
  freeLimit: () => T('До 5 человек — бесплатно', 'Up to 5 people is free', 'Hasta 5 personas es gratis'),
  plusLimit: () => T('6–20 человек доступны с Kleal Plus', '6–20 people are available with Kleal Plus', '6–20 personas disponibles con Kleal Plus'),
  plusTitle: () => T('Большие группы — с Plus', 'Bigger groups are with Plus', 'Grupos más grandes con Plus'),
  plusBody: () => T(
    'В бесплатной группе может быть до 5 человек. Plus поднимает предел до 20 и позволяет запускать несколько интентов одновременно. Качество ранжирования не зависит от тарифа.',
    'Free groups go up to 5 people. Plus raises the ceiling to 20 and lets you run several intents at once. Matches are ranked the same either way.'
  , 'Los grupos gratuitos llegan hasta 5 personas. Plus sube el límite a 20 y te deja tener varias propuestas a la vez. Las coincidencias se ordenan igual en ambos casos.'),
  getPlus: () => T('Подключить Kleal Plus', 'Get Kleal Plus', 'Obtén Kleal Plus'),
  keepAtFive: () => T('Оставить максимум 5', 'Keep it at 5', 'Manténlo en 5'),
};

// ---------------------------------------------------------------- O.07–O.09 · детали

/**
 * Черты, которые можно попросить в другом человеке. Это ТЕ ЖЕ оси, что заполняет тест личности
 * (src/profile.ts, AXIS_VALUE), — иначе просить было бы нечего: у кандидата в профиле лежат
 * именно они.
 *
 * Взяты не все десять: спрашивать «что он приносит» и «что делает, когда отменили» на этапе
 * поиска рано — человек этого про незнакомца не выбирает. Осталось то, что решает, сойдётесь ли
 * вы за первый вечер: темп, глубина, энергия, планирование и одна черта про то, что он даёт.
 *
 * Внутри оси выбор ОДИН: «спокойный» и «заводной» — это две стороны одной оси, и отметить обе
 * значит не отметить ничего. Экран так и ведёт себя — второй выбор заменяет первый.
 */
export type NatureTrait = { axis: string; token: string; label: () => string };

export const NATURE_TRAITS: NatureTrait[] = [
  { axis: 'energy', token: 'energised', label: () => T('Заводной', 'High-energy', 'Con energía') },
  { axis: 'energy', token: 'drained', label: () => T('Спокойный', 'Low-key', 'Tranquilo') },
  { axis: 'depth', token: 'deep', label: () => T('Говорит по душам', 'Goes deep', 'Habla a fondo') },
  { axis: 'depth', token: 'light', label: () => T('Лёгкий, с юмором', 'Light and funny', 'Ligero, con humor') },
  { axis: 'pace', token: 'fast', label: () => T('Открывается сразу', 'Opens up fast', 'Se abre enseguida') },
  { axis: 'pace', token: 'slow', label: () => T('Сначала присматривается', 'Takes their time', 'Se lo toma con calma') },
  { axis: 'planning', token: 'advance', label: () => T('Договаривается заранее', 'Plans ahead', 'Queda con antelación') },
  { axis: 'planning', token: 'spontaneous', label: () => T('Спонтанный', 'Spontaneous', 'Espontáneo') },
  { axis: 'give', token: 'listen', label: () => T('Умеет слушать', 'A good listener', 'Un buen oyente') },
  { axis: 'give', token: 'instigate', label: () => T('Вытащит из дома', 'Gets you out', 'Te saca de casa') },
];

/** Сколько черт имеет смысл просить. Больше — сужение без выигрыша, и об этом сказано вслух. */
export const NATURE_MAX = 3;

export const DETAILS = {
  title: () => T('Пара деталей — и я ищу', "A few details, and I'll search", 'Un par de detalles y buscaré'),
  subWhen: () => T('Когда и где удобно?', 'When and where works best?', '¿Cuándo y dónde te viene mejor?'),
  subWho: () => T('Кого ты ищешь?', 'Who are you looking for?', '¿A quién estás buscando?'),
  subNature: () => T('Какой человек тебе подойдёт?', 'What kind of person suits you?', '¿Qué tipo de persona te encaja?'),
  subLink: () => T('Где пройдёт звонок?', 'Where does the call happen?', '¿Dónde se hará la llamada?'),
  /** HY.09 — «place and link». Гибриду нужны оба, и на HY.20a/20b борд говорит это словами. */
  subBoth: () => T('И место, и ссылка — гибриду нужны оба.',
                   'Both the place and the link — hybrid needs both.', 'Tanto el lugar como el enlace — lo híbrido necesita ambos.'),
  /** Строка листа правки у гибрида: один шаг, поэтому и строка одна. */
  bothRow: () => T('Место и ссылка', 'Place and link', 'Lugar y enlace'),
  subPlace: () => T('Где удобно встретиться?', 'Where works best to meet?', '¿Dónde te viene mejor reunirse?'),

  date: () => T('Дата', 'Date', 'Fecha'),
  time: () => T('Время', 'Time', 'Hora'),
  timeZone: () => T('Часовой пояс', 'Time Zone', 'Zona horaria'),

  audience: () => T('Аудитория', 'Audience', 'Público'),
  age: () => T('Возраст', 'Age', 'Edad'),

  nature: () => T('Характер', 'Character', 'Carácter'),
  natureHint: () =>
    T('Необязательно. Отметь то, что важно, — Kleal поднимет таких людей выше, но не спрячет остальных.',
      'Optional. Mark what matters — Kleal lifts those people higher, it does not hide the rest.', 'Opcional. Marca lo que importa — Kleal eleva a esas personas, no oculta al resto.'),
  natureLimit: () => T('Больше трёх не нужно — сузит выдачу без пользы.',
                       'Three is enough — more narrows the results without helping.', 'Tres es suficiente — más resultados estrechan la búsqueda sin ayudar.'),
  natureSkip: () => T('Мне не принципиально', 'No preference', 'Sin preferencia'),

  link: () => T('Ссылка', 'Link', 'Enlace'),
  linkPlaceholder: () => 'https://yourlink.com',
  /** Дисклеймер с кадра O.09, дословно. */
  linkNote: () =>
    T(
      'Ссылками делятся сами люди. Открывать её или нет — решаешь ты. Kleal не отвечает за сторонний контент и действия.',
      'External links are shared by users. You choose whether to open them. Kleal isn’t responsible for third-party content or actions.'
    , 'Los enlaces externos son compartidos por usuarios. Tú decides si los abres. Kleal no es responsable del contenido o acciones de terceros.'),

  district: () => T('Район', 'District', 'Distrito'),
  /** OF.09: двигают КАРТУ, булавка стоит в центре — см. RadiusMap.native, там про долгое нажатие. */
  dragPin: () => T('Ищешь не от дома? Подвинь карту под булавку.',
                   'Searching from somewhere else? Move the map under the pin.', '¿Buscar desde otro lugar? Mueve el mapa debajo del pin.'),
  centerMoved: () => T('Ищем вокруг этой точки.', 'We’ll search around this spot.', 'Buscaremos alrededor de este lugar.'),
  backHome: () => T('Вернуть к дому', 'Back to home', 'Volver a inicio'),
  radius: () => T('Как далеко готов(а) ехать?', 'How far are you happy to go?', '¿A qué distancia estás dispuesto a ir?'),
  /** OF.09: точное место — опционально уже на создании; чужим его не видно до взаимного «да». */
  exactAddress: () => T('Точный адрес', 'Exact address', 'Dirección exacta'),
  exactAddressPlaceholder: () => T('Кафе, бар или парк…', 'Search for a café, bar or park', 'Buscar un café, bar o parque'),
  exactAddressNote: () =>
    T(
      'Пока идёт подбор, виден только район. Точным местом вы делитесь после того, как оба согласитесь встретиться.',
      'Only the district is shown while you’re matching. You share the exact spot after you both agree to meet.'
    , 'Mientras te estés emparejando, solo se muestra el distrito. Compartes el lugar exacto después de que ambos acepten quedar.'),

  /** O.10a: правку с битой ссылкой не применяем — на шаге мастера её так же не пускает «Дальше».
   *  Молча отключённая кнопка читается как поломка листа, поэтому причина названа словами. */
  linkBad: () => T('Ссылка не похожа на ссылку — поправь её, иначе применить нечего.',
                   'That doesn’t look like a link — fix it before applying.', 'Eso no parece un enlace — corrige antes de aplicar.'),
  groupLinkRequired: () => T(
    'Добавь ссылку на звонок — без неё участникам онлайн-группы некуда подключиться.',
    'Add the call link — without it the online group has nowhere to join.'
  , 'Añade el enlace de la llamada — sin él el grupo en línea no tiene a dónde unirse.'),

  // O.07a — лист выбора пояса. Заголовок с кадра дословно.
  tzSheetTitle: () => T('Часовой пояс GMT', 'Time Zone GMT', 'Zona horaria GMT'),
  apply: () => T('Применить', 'Apply', 'Aplicar'),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),
};

/**
 * O.10a — лист «что поменять» над сводкой. Подписи строк — с кадра; значения экран собирает из
 * черновика сам.
 *
 * Строка РАСКРЫВАЕТСЯ и правится тут же. Раньше ключ строки был именем шага мастера, и «Изменить»
 * туда уводило — а у каждого шага своя кнопка «Дальше», ведущая ДАЛЬШЕ по цепочке: правка одной
 * даты стоила четырёх экранов. Теперь режим и формат тоже правятся здесь, с показом только
 * обязательной зависимости (размер группы и, для Group Online, ссылка). Темы интента нет:
 * её выбирают в разговоре создания, отдельного шага/контрола под неё в мастере не существует.
 */
export const EDIT_SHEET = {
  title: () => T('Что хочешь поменять?', 'What do you want to change?', '¿Qué es lo que quieres cambiar?'),
  mode: () => T('Тип встречи', 'Meeting mode', 'Modo reunión'),
  format: () => T('Формат', 'Format', 'Formato'),
  date: () => T('Дата', 'Date', 'Fecha'),
  time: () => T('Время', 'Time', 'Hora'),
  datetime: () => T('Дата и время', 'Date & Time', 'Fecha y hora'),
  timezone: () => T('Часовой пояс', 'Time zone', 'Zona horaria'),
  audience: () => T('Аудитория и возраст', 'Audience & Age', 'Público y edad'),
  link: () => T('Ссылка', 'Link', 'Enlace'),
  noData: () => T('Нет данных', 'No Data', 'Sin datos'),
  change: (label: string) => T(`Изменить: ${label}`, `Edit: ${label}`, `Editar: ${label}`),
  groupSizeNeeded: () => T(
    'Для группы выбери количество участников здесь же.',
    'Choose the number of participants here for the group.',
  ),
  groupOnlineLinkNeeded: () => T(
    'Для группового онлайн-интента нужна ссылка. Добавь её здесь — остальные параметры не изменятся.',
    'A group online intent needs a link. Add it here; the other settings will stay unchanged.',
  ),
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
  const loc = dateLocale();
  for (let i = 0; i < n; i++) {
    const d = new Date(from);
    d.setDate(d.getDate() + i);
    out.push({
      // Ключ — из ЛОКАЛЬНЫХ частей даты, не из toISOString(): та отдаёт UTC, и после местной
      // полуночи (пока UTC ещё вчера) чип «Пт, 7» носил ключ «-06» — план строился на вчера,
      // и сервер честно отвечал IN_THE_PAST. Поймано вживую в симуляторе в 02:58.
      key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`,
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

/**
 * Человеческая подпись времени интента: «сб, 8 авг. · 20:00». Едет рядом с английским `time`,
 * который читает сервер, — приглашённому показывается она, а не «today 20:00».
 */
export function planWhenLabel(dateKey: string, minutes: number): string {
  const loc = dateLocale();
  const d = new Date(dateKey + 'T12:00:00');
  const day = d.toLocaleDateString(loc, { weekday: 'short', day: 'numeric', month: 'short' });
  return `${day} · ${hhmm(minutes)}`;
}

/** Часовой пояс устройства — IANA-имя, оно же уходит в ctx.tz. */
/**
 * Чужое местное время — и ТОЛЬКО когда оно отличается от своего.
 *
 * Спека: «Таймзона в UI — только при расхождении. Иначе визуальный шум в 95 % случаев». До этого
 * пояс печатался всегда и всегда СВОЙ: чужого не было нигде, поэтому строку «20:00 Barcelona ·
 * 19:00 London» с кадров O.14/O.21/O.C3 показать было нечем.
 *
 * Пустая строка означает «показывать нечего»: либо пояс собеседника неизвестен, либо он тот же.
 * Выдумывать «19:00 в Лондоне» без данных нельзя — лучше не сказать ничего.
 */
export function peerLocalTime(startsAt?: number | null, peerTz?: string, ru = true): string {
  const at = Number(startsAt || 0);
  const tz = String(peerTz || '').trim();
  if (!at || !tz) return '';
  const mine = deviceTz();
  if (!mine || tz === mine) return '';
  try {
    const d = new Date(at * 1000);
    const fmt = (zone: string) =>
      new Intl.DateTimeFormat(dateLocale(ru, 'en-GB'),
        { hour: '2-digit', minute: '2-digit', timeZone: zone, hour12: false }).format(d);
    const theirs = fmt(tz);
    // Совпало по часам — расхождения для человека нет, даже если зоны названы по-разному.
    if (theirs === fmt(mine)) return '';
    // Город из имени зоны: «Europe/London» → «London». Он понятнее смещения в часах.
    const city = tz.split('/').pop()?.replace(/_/g, ' ') || tz;
    return `${theirs} ${city}`;
  } catch {
    return '';
  }
}

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
  title: () => T('Вот что получилось', "Here's what I got", 'Esto es lo que he encontrado'),
  /** Пузырь-примечание с кадра, дословно. */
  note: () =>
    T(
      'Проверь — поправить можно что угодно. Поиск мы подгоним под настройки твоего профиля и этот интент.',
      "Check it — edit anything if needed. We'll tailor the search to your profile settings and this intent."
    , 'Revísalo — edita lo que haga falta. Adaptaremos la búsqueda a los ajustes de tu perfil y a esta propuesta.'),
  mode: () => T('Тип', 'Mode', 'Modo'),
  format: () => T('Формат', 'Format', 'Formato'),
  category: () => T('Категория', 'Category', 'Categoría'),
  audience: () => T('Аудитория', 'Audience', 'Público'),
  summaryLabel: () => T('Сводка Kleal:', 'Kleal summary:', 'Resumen de Kleal:'),
  start: () => T('Начать поиск', 'Start search', 'Iniciar búsqueda'),
  edit: () => T('Поправить', 'Edit', 'Editar'),
  /** Кости у названия. Подпись только для озвучки — на экране стоит значок. */
  roll: () => T('Подобрать другое название', 'Suggest another name', 'Sugerir otro nombre'),
};

/** «Thu, 23 July» с кадра — дата сводки, на языке интерфейса. */
export function summaryDate(dateKey: string): string {
  const loc = dateLocale();
  const d = new Date(dateKey + 'T12:00:00');
  return d.toLocaleDateString(loc, { weekday: 'short', day: 'numeric', month: 'long' });
}

/** Смещение пояса для строки времени: «(GMT+2)». Вырезается из tzDisplay, чтобы не считать дважды. */
export function tzOffsetLabel(tz: string): string {
  const m = tzDisplay(tz).match(/\(([^)]+)\)/);
  return m ? `(${m[1]})` : '';
}

/**
 * Профиль для поисковых вызовов — match, plan, intents.
 *
 * Собирался вручную в трёх экранах сразу (мастер интента, создание, разговор с Бадди), и с
 * «Моей активностью» появилась бы четвёртая копия. Место опасное: `languages` сервер читает как
 * ОБЪЕКТ (`languages.comfortable`), и на плоском списке ранжирование падает целиком, не сказав ни
 * слова — эта ошибка уже случалась и стоила поиска, который «просто никого не находит».
 *
 * `override` — координаты, выбранные в мастере: человек мог указать не то место, где живёт.
 */
export function searchProfile(p: any, override?: { lat?: number; lon?: number }) {
  return {
    name: p?.name,
    age: p?.age,
    gender: p?.gender,
    city: p?.city,
    lat: override?.lat ?? p?.geo?.coarseLat,
    lon: override?.lon ?? p?.geo?.coarseLon,
    languages: p?.languages || {},
  };
}

/**
 * «Сводка Kleal» на O.10. На борде этот текст пишет модель («You want to speak Spanish, not study
 * it…») — серверной ручки под это пока нет, и в каркасе стоит детерминированный шаблон из
 * собранных фактов. Он не выдумывает ничего, чего человек не выбирал; умный пересказ — отдельная
 * работа на стороне buddy, помечено в ROADMAP.
 */
export function intentSummaryText(o: {
  topic: string; size?: string; groupSize?: number; sex?: string; minAge: number; maxAge: number;
  dateKey: string; minutes: number;
  /** Отмеченные черты одной строкой. Пусто — про характер в сводке не говорим вовсе. */
  nature?: string;
}): string {
  const who =
    normalizeIntentSize(o.size, o.groupSize) === 'group'
      ? (o.groupSize
          ? T(`группу из ${o.groupSize} человек`, `a group of ${o.groupSize}`, `un grupo de ${o.groupSize}`)
          : T('группу', 'a group', 'un grupo'))
      : T('одного человека', 'one person', 'una persona');
  const aud = o.sex && o.sex !== 'Any'
    ? (o.sex === 'Female' ? T('женщину', 'a woman', 'una mujer') : T('мужчину', 'a man', 'un hombre')) + ', '
    : '';
  const when = `${summaryDate(o.dateKey)} ${T('около', 'around', 'alrededor de')} ${hhmm(o.minutes)}`;
  // Характер — предпочтение, и сводка называет его именно так. Сказать «Kleal ищет спокойного»
  // значило бы пообещать фильтр, которого нет: ранжирование поднимает таких выше, но не прячет
  // остальных (см. wantPersona в app/intent.tsx).
  const nat = String(o.nature || '').trim()
    ? ' ' + T(`Из похожих подниму тех, кто ближе к «${o.nature!.toLowerCase()}».`,
              `Among the matches I'll lift those closer to "${o.nature!.toLowerCase()}".`, `Entre las coincidencias destacaré las más cercanas a "${o.nature!.toLowerCase()}".`)
    : '';
  return (o.topic
    ? T(
        `Ты хочешь: ${o.topic}. Kleal ищет ${who} — ${aud}${o.minAge}–${o.maxAge}, со свободным временем ${when}.`,
        `You're after: ${o.topic}. Kleal is looking for ${who} — ${aud}${o.minAge}–${o.maxAge}, free ${when}.`
      , `Buscas: ${o.topic}. Kleal busca a ${who} — ${aud}${o.minAge}–${o.maxAge}, libre ${when}.`)
    : T(
        `Kleal ищет ${who} — ${aud}${o.minAge}–${o.maxAge}, со свободным временем ${when}.`,
        `Kleal is looking for ${who} — ${aud}${o.minAge}–${o.maxAge}, free ${when}.`
      , `Kleal busca a ${who} — ${aud}${o.minAge}–${o.maxAge}, libre ${when}.`)) + nat;
}

// ---------------------------------------------------------------- районы (офлайн, прежний кадр OF.09)

export const DISTRICTS: [string, string, string][] = [
  ['center', 'Центр', 'Center'],
  ['west', 'Запад', 'West'],
  ['east', 'Восток', 'East'],
  ['south', 'Юг', 'South'],
  ['beach', 'Пляж', 'Beach'],
];
const DISTRICT_ES: Record<string, string> = {
  center: 'Centro', west: 'Oeste', east: 'Este', south: 'Sur', beach: 'Playa',
};
export const districtLabel = (k: string) => {
  const d = DISTRICTS.find((x) => x[0] === k);
  return d ? T(d[1], d[2], DISTRICT_ES[d[0]]) : k;
};
/** Район в запросе — канонически английский: он попадает в карточки и планы, которые видят оба. */
export const districtQuery = (k?: string) => {
  const d = DISTRICTS.find((x) => x[0] === k);
  return d ? d[2] : k || '';
};

// ---------------------------------------------------------------- поиск и выдача

/** OF.11. */
export const SEARCHING = {
  title: () => T('Ищу людей, группы\nи места для тебя', 'Finding people, groups\nand places for you', `Buscando personas, grupos
y lugares para ti`),
  step: () => T('Смотрю подходящие форматы', 'Scanning matching formats', 'Escaneando formatos coincidentes'),
  note: () => T('Это займёт пару секунд.', 'This will take just a moment.', 'Esto solo tomará un momento.'),
  /**
   * После шести секунд экран обязан заговорить. Подбор занимает полторы секунды; всё, что дольше,
   * — уже не «пара секунд», и молчащий кружок в этот момент читается как зависание.
   */
  slow: () => T('Дольше обычного — связь медленная. Ещё жду.',
                'Taking longer than usual — the connection is slow. Still waiting.', 'Tardando más de lo habitual — la conexión es lenta. Aún esperando.'),
  /** Выход есть всегда. Экран без выхода и есть то, что называют «висит». */
  cancel: () => T('Отменить', 'Cancel', 'Cancelar'),
  /** Отменил сам — это не сбой, и говорить о сбое нельзя. */
  cancelled: () => T('Поиск отменён.', 'Search cancelled.', 'Búsqueda cancelada.'),
  failed: () => T('Поиск не дошёл до сервера. Проверь связь и попробуй ещё раз.',
                  'The search never reached the server. Check your connection and try again.', 'La búsqueda no llegó al servidor. Comprueba tu conexión e inténtalo de nuevo.'),
};

/** OF.12 / OF.11a. */
export const RESULTS = {
  best: () => T('Лучшее совпадение по запросу', 'Best fit for your request', 'Mejor opción para tu petición'),
  empty: () => T('Пока никого по такому запросу', 'Nobody matches that yet', 'Todavía no hay coincidencias'),
  emptyNote: () =>
    T(
      'Можно расширить поиск — по расстоянию, времени или близким занятиям.',
      'We can widen the search — by distance, time, or related activities.'
    , 'Podemos ampliar la búsqueda — por distancia, hora o actividades relacionadas.'),
  widen: () => T('Расширить поиск', 'Widen the search', 'Ampliar la búsqueda'),
  /**
   * «Ещё» и «шире» — РАЗНОЕ, и путать их нельзя.
   *
   * «Показать ещё» отдаёт продолжение того же ранжирования: девятый после восьмого, запрос не
   * меняется. «Расширить поиск» ослабляет сам запрос и потому обязано объясняться словами.
   * Пока была только вторая кнопка, «покажи больше людей» было нечем выполнить: ослабление
   * условий впускает больше народу в отбор, но вперёд выходят те же лучшие восемь — проверено,
   * все четыре оси вернули ту же восьмёрку.
   */
  more: () => T('Показать ещё', 'Show more', 'Mostrar más'),
  allShown: (n: number) => T(`Это все — ${n}`, `That's everyone — ${n}`, `Ésta es toda la gente — ${n}`),
  exhausted: () =>
    T('Шире уже некуда — по этому запросу пока никого.', 'Nothing wider to try — nobody matches this yet.', 'No hay nada más amplio que probar — todavía no hay coincidencias con esto.'),
  found: (n: number) => T(`Нашлось: ${n}`, `Found ${n}`, `${n === 1 ? '1 encontrado' : n + ' encontrados'}`),
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
               'Added neighbouring activities, not just the one you named.', 'Se han añadido actividades cercanas, no solo la que mencionaste.');
    case 'exactness':
      return T('Перестала требовать точное совпадение.', 'Stopped requiring an exact match.', 'Dejado de exigir coincidencia exacta.');
    case 'parent':
      return T('Взяла категорию шире.', 'Went one category wider.', 'Se ha ampliado una categoría más.');
    case 'radius':
      return radiusKm
        ? T(`Расширила круг поиска до ${radiusKm} км.`, `Widened the search radius to ${radiusKm} km.`, `Ampliamos el radio de búsqueda a ${radiusKm} km.`)
        : T('Расширила круг поиска.', 'Widened the search radius.', 'Se ha ampliado el radio de búsqueda.');
  }
};

/**
 * ДРУГОЕ НАЗВАНИЕ ИНТЕНТА — то, что предлагают кости на сводке.
 *
 * ЗАЧЕМ. Название приходит из разговора создания, и оно не всегда удачное: модель называет интент
 * по первой фразе человека, а тот мог сказать длинно, косо или про другое. Переписать руками можно
 * всегда, но чаще человеку нужно не «своё», а «нормальное» — и быстрее ткнуть, чем печатать.
 *
 * ПОЧЕМУ БЕЗ МОДЕЛИ. Название складывается из того, что на этом же экране уже известно: тема,
 * формат, время. Запрос к модели стоил бы ожидания и сети на действии, которое человек нажмёт
 * пять раз подряд, перебирая. Здесь ответ мгновенный, работает без связи и ничего не может
 * придумать про интент такого, чего в интенте нет.
 *
 * ГЛАВНАЯ ТОНКОСТЬ — ПАДЕЖИ. Тема подставляется в рамку как есть, в именительном: «Кофе», «Йога»,
 * «Настольные игры». Поэтому рамки построены так, чтобы тема стояла отдельным словом и не требовала
 * склонения. «Сходить на {X}» звучало бы хорошо с кофе и футболом, но дало бы «сходить на йога» и
 * «сходить на настольные игры» — а тем в дереве три сотни, и проверить каждую нельзя. Все рамки
 * ниже безопасны для любой темы.
 */
const NAME_FRAMES = (x: string, two: boolean, evening: boolean): string[] => {
  const base = [
    T(`${x} — ищу компанию`, `${x} — looking for company`, `${x} — buscando compañía`),
    T(`Просто ${x.toLowerCase()}`, `Just ${x.toLowerCase()}`, `Solo ${x.toLowerCase()}`),
    T(`${x}: кто со мной?`, `${x}: anyone in?`, `${x}: ¿alguien dentro?`),
    T(`${x} и разговор`, `${x} and a chat`, `${x} y un chat`),
    T(`${x} без планов`, `${x}, no plans`, `${x}, sin planes`),
    // Здесь стояло «Хочу {x}» — и это была ровно та ошибка, от которой предостерегает комментарий
    // выше: «хотеть» требует падежа, и на живых подписях выходило «Хочу йога». Поймано прогоном по
    // десяти реальным темам. Замена ничего от темы не требует.
    T(`${x} — можно вместе`, `${x} — let's do it together`, `${x} — hagámoslo juntos`),
  ];
  // Рамки, привязанные к настройкам интента: их добавляем, только если настройка вправду такая.
  if (two) base.push(T(`${x} вдвоём`, `${x} for two`, `${x} para dos`));
  else base.push(T(`${x} компанией`, `${x} with a group`, `${x} con un grupo`));
  if (evening) base.push(T(`${x} вечером`, `${x} tonight`, `${x} esta noche`));
  return base;
};

/**
 * Кандидаты в название по теме и настройкам интента. Текущее имя исключено — кости, которые
 * возвращают то же самое, читаются как сломанные.
 *
 * `topics` — английские ключи; подпись берём через общий словарь, чтобы название было на языке
 * человека и совпадало с тем, как та же тема подписана везде в приложении.
 */
export function intentNameOptions(
  topics: string[],
  opts: { size?: string; minutes?: number },
  avoid = ''
): string[] {
  /*
    БЕРЁМ ТОЛЬКО ТЕ ТЕМЫ, КОТОРЫЕ СЛОВАРЬ УМЕЕТ НАЗВАТЬ, и это не придирка.

    `interestLabel` при промахе возвращает ключ КАК ЕСТЬ — это правильное поведение (своё слово
    лучше пустоты), но для названия оно давало смесь языков. Поймано на живом экране: темы пришли
    `['run', 'jogging']`, «run» словарь знает как «Бег», а «jogging» не знает ни дерево, ни колода —
    и получилось «Бег и jogging — можно вместе». Темы приходят из разговора создания, то есть с
    сервера, и совпадать со словарём приложения не обязаны.

    Признак «словарь знает» — подпись отличается от ключа. Для английского языка это тоже верно:
    там подпись у известного ключа всё равно своя («running» -> «Running»).
  */
  const named = (topics || [])
    .map((t) => String(t || '').trim())
    .filter(Boolean)
    .map((k) => ({ key: k, label: interestLabel(k) }))
    .filter((x) => x.label && x.label !== x.key);
  if (!named.length) return [];
  const first = named[0].label;
  // Две темы складываем в одну подпись: «Кофе и прогулка» точнее, чем просто «Кофе».
  const pair = named.length > 1 ? named[1].label : '';
  const subject = pair ? T(`${first} и ${pair.toLowerCase()}`, `${first} and ${pair.toLowerCase()}`, `${first} y ${pair.toLowerCase()}`) : first;

  const two = opts.size !== 'group';
  const evening = typeof opts.minutes === 'number' && opts.minutes >= 17 * 60;
  const seen = String(avoid || '').trim().toLowerCase();
  const out: string[] = [];
  for (const n of [...NAME_FRAMES(subject, two, evening), ...(pair ? NAME_FRAMES(first, two, evening) : [])]) {
    const clean = n.trim();
    if (clean && clean.toLowerCase() !== seen && !out.includes(clean)) out.push(clean);
  }
  return out;
}

/** Одно случайное имя из подходящих. Пусто — тем нет, и предлагать нечего. */
export function rollIntentName(
  topics: string[],
  opts: { size?: string; minutes?: number },
  avoid = ''
): string {
  const all = intentNameOptions(topics, opts, avoid);
  if (!all.length) return '';
  return all[Math.floor(Math.random() * all.length)];
}
