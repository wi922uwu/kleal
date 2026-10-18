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
import { T, plural, dateLocale } from './i18n';
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
  plusLimit: () => T('Вместимость группы пока до 5 человек', 'Groups currently hold up to 5 people', 'Los grupos admiten hasta 5 personas'),
  plusTitle: () => T('Вместимость группы', 'Group capacity', 'Capacidad del grupo'),
  plusBody: () => T(
    'В группе до 5 человек. Вместимость и качество подбора не зависят от тарифа.',
    'Groups hold up to 5 people. Capacity and matching quality do not depend on your plan.'
  , 'Hasta 5 personas por grupo. La capacidad y calidad de las coincidencias no dependen del plan.'),
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
      key: dayKey(d),
      label: d.toLocaleDateString(loc, { weekday: 'short', month: 'short', day: 'numeric' }),
    });
  }
  return out;
}

/**
 * Ключ дня по МЕСТНЫМ частям даты. Вынесен сюда, потому что таких мест два — чипы дат и строка
 * запроса, — и они разъехались: чипы считали местный день, а запрос сравнивал его с UTC-днём.
 */
const dayKey = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

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
  // СРАВНИВАЕМ МЕСТНЫЕ ДНИ. Здесь стоял `toISOString()`, то есть UTC: тот же капкан, что уже
  // ловили на чипах дат, только с обратной стороны. Вечером в Америке (по UTC уже завтра) слово
  // «today» терялось и запрос ранжировался как «когда-нибудь»; восточнее UTC после местной
  // полуночи было хуже — поиск на сегодняшний вечер уезжал как «tomorrow», то есть на другой день.
  if (dateKey === dayKey(from)) return `today ${t}`;
  const tomorrow = new Date(from);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (dateKey === dayKey(tomorrow)) return `tomorrow ${t}`;
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

/**
 * ВРЕМЯ СОБЕСЕДНИКА — ОТДЕЛЬНОЙ ФРАЗОЙ С ЕГО ИМЕНЕМ. Раньше к своему часу дописывалось «· 20:00
 * Moscow», и строка «22:00 · 20:00 Moscow» читалась как «с 22 до 20» — непонятно, чьё время
 * (тестировщики 17.10.2026). Главное время на экране всегда МОЁ (пояс устройства), а чужое —
 * пояснением: «У ИВАНН это 20:00 (Moscow)». Пусто, если пояса совпали или чужой неизвестен.
 */
export function peerTimeNote(startsAt?: number | null, peerTz?: string, name = '', ru = true): string {
  const t = peerLocalTime(startsAt, peerTz, ru);
  if (!t) return '';
  const i = t.indexOf(' ');
  const time = i > 0 ? t.slice(0, i) : t;
  const city = i > 0 ? t.slice(i + 1) : '';
  const who = String(name || '').trim();
  const where = city ? ` (${city})` : '';
  return who
    // Те же слова, что у переноса (PLAN.theirTimeNote в chat.ts), плюс город — один голос на экране.
    ? T(`У ${who} это ${time}${where}`, `That’s ${time} for ${who}${where}`, `Eso es ${time} para ${who}${where}`)
    : T(`У собеседника это ${time}${where}`, `That’s ${time} for them${where}`, `Eso es ${time} para la otra persona${where}`);
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
/**
 * Категория фильтратора словами (сводка GR.12 «Category»). Фильтратор отвечает кодом из 24 слов —
 * «food_drink», «film_tv»; на карточке это читалось как «Food_drink». Незнакомый код — с заглавной
 * и без подчёркиваний.
 */
const CATEGORY_WORDS: Record<string, [string, string, string]> = {
  sports: ['Спорт', 'Sports', 'Deportes'], gaming: ['Игры', 'Gaming', 'Videojuegos'],
  esports: ['Киберспорт', 'Esports', 'Esports'], tabletop: ['Настольные игры', 'Board games', 'Juegos de mesa'],
  music: ['Музыка', 'Music', 'Música'], film_tv: ['Кино и сериалы', 'Film & TV', 'Cine y TV'],
  art_culture: ['Искусство и культура', 'Art & Culture', 'Arte y cultura'], books: ['Книги', 'Books', 'Libros'],
  food_drink: ['Еда и напитки', 'Food & Drinks', 'Comida y bebida'], coffee: ['Кофе', 'Coffee', 'Café'],
  nightlife: ['Ночная жизнь', 'Nightlife', 'Vida nocturna'], outdoors: ['На природе', 'Outdoors', 'Aire libre'],
  travel: ['Путешествия', 'Travel', 'Viajes'], tech: ['Технологии', 'Tech', 'Tecnología'],
  startups: ['Стартапы', 'Startups', 'Startups'], career: ['Карьера', 'Career', 'Carrera'],
  languages: ['Языки', 'Languages', 'Idiomas'], wellness: ['Здоровье', 'Wellness', 'Bienestar'],
  fashion: ['Мода', 'Fashion', 'Moda'], toys_collectibles: ['Коллекции', 'Collectibles', 'Coleccionismo'],
  pets: ['Питомцы', 'Pets', 'Mascotas'], photography: ['Фотография', 'Photography', 'Fotografía'],
  dating: ['Свидания', 'Dating', 'Citas'], social: ['Общение', 'Social', 'Social'], other: ['Другое', 'Other', 'Otro'],
};
export function categoryLabel(code: string): string {
  const k = String(code || '').trim().toLowerCase().replace(/\s*&\s*/g, '_').replace(/\s+/g, '_');
  const w = CATEGORY_WORDS[k];
  if (w) return T(w[0], w[1], w[2]);
  const t = String(code || '').trim().replace(/_/g, ' ');
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : '';
}

/**
 * Похоже ли на ссылку. Схема не обязательна: на борде (GRO.11) ссылку вставляют как
 * «meet.google.com/bkc-lub-thu», и сервер принимает голый домен. `withScheme` дописывает https://.
 */
export function looksLikeUrl(s: string): boolean {
  const v = String(s || '').trim();
  return /^https?:\/\/\S+\.\S+/.test(v) || /^[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}(\/\S*)?$/i.test(v);
}

export function withScheme(s: string): string {
  const v = String(s || '').trim();
  return !v || /^https?:\/\//i.test(v) ? v : `https://${v}`;
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
  /**
   * GR.13: «Finding people for you». Только люди — заметка борда: «Kleal ищет только людей»; прежнее
   * «people, groups and places» обещало то, чего поиск не делает.
   */
  title: () => T('Ищу людей для тебя', 'Finding people for you', 'Buscando personas para ti'),
  /** «Scanning who’s free on Thursday» — день берётся из затеи; сегодня и завтра называются словом. */
  step: (dateKey?: string) => {
    if (!dateKey) return T('Смотрю, кто свободен', 'Scanning who’s free', 'Mirando quién está libre');
    const d = new Date(dateKey + 'T12:00:00');
    const today = new Date(); today.setHours(12, 0, 0, 0);
    const days = Math.round((d.getTime() - today.getTime()) / 86400000);
    if (days === 0) return T('Смотрю, кто свободен сегодня', 'Scanning who’s free today', 'Mirando quién está libre hoy');
    if (days === 1) return T('Смотрю, кто свободен завтра', 'Scanning who’s free tomorrow', 'Mirando quién está libre mañana');
    const wd = d.toLocaleDateString(dateLocale(), { weekday: 'long' });
    return T(`Смотрю, кто свободен: ${wd}`, `Scanning who’s free on ${wd}`, `Mirando quién está libre el ${wd}`);
  },
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
  /*
    СЛОВО «РАЗГОВОР» — НЕ ПРЕДМЕТ ЗАТЕИ, даже когда словарь его знает.

    Снято с живого сервера: затея про World of Warcraft называлась «Разговор: кто со мной?». Темы
    пришли `['world of warcraft', 'pvp', 'talk']`, WoW и pvp словарь приложения не знает, а «talk»
    знает как «Разговор» — и кости построили имя ровно по тому слову, которое не говорит ничего.
    Такие слова стоят почти в каждом наборе тем, потому что фильтрация вытаскивает их из любой
    фразы про «поговорить», — значит без сита они выигрывают тем чаще, чем реже словарь знает
    настоящий предмет.

    Список короткий и живёт ЗДЕСЬ, а не сверяется с сервером: это правило показа (что вынести в
    заголовок), а не правило поиска. Серверные списки решают другую задачу — что вообще считать
    занятием при ранжировании, — и сводить их в один нельзя: у них разные хозяева и разная цена
    ошибки. Если предмета не осталось вовсе, кости просто не предлагаются: кнопка, которой нечего
    сказать, хуже её отсутствия (см. вызов на экране сводки).
  */
  const NOT_A_SUBJECT = new Set([
    'talk', 'talking', 'chat', 'chatting', 'conversation', 'conversations', 'discussion',
    'discussions', 'discuss', 'meet', 'meeting', 'meetup', 'hangout', 'company', 'people',
    'friends', 'friendship', 'social', 'socializing', 'socialising', 'communication',
    'общение', 'разговор', 'разговоры', 'встреча', 'компания', 'компании',
  ]);
  const named = (topics || [])
    .map((t) => String(t || '').trim())
    .filter(Boolean)
    .filter((k) => !NOT_A_SUBJECT.has(k.toLowerCase()))
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

// ---------------------------------------------------------------- мастер «Creating intent» (GR.05–GR.12)
//
// Копия борда «0 · Create the intent» (Figma 6864:119674). Отдельным блоком, а не правкой прежних
// STEP_HOW / GROUP_SIZE / SUMMARY_O10: те же строки читают экраны плана, активности и группового
// плана, и смена формулировки мастера не должна менять их подписи мимоходом.

export const WIZ = {
  howAsk: () => T('Как хочешь встретиться?', 'How do you want to meet?', '¿Cómo quieres quedar?'),
  howCaption: () => T('Один формат на интент — от него зависит, как люди присоединяются',
                      'One format per intent — it decides how people join',
                      'Un formato por propuesta: decide cómo se une la gente'),
  /** Пояснения строк в скобках — слово в слово с кадра, со строчной. */
  formatSub: (k: string) =>
    k === 'offline' ? T('вживую', 'in person', 'en persona')
    : k === 'online' ? T('видео / голос', 'video / voice', 'vídeo / voz')
    // HY.05 / GRH.05: «Hybrid (in person and on a call)».
    : T('вживую и в звонке', 'in person and on a call', 'en persona y en una llamada'),

  sizeAsk: () => T('Только вы вдвоём или компания?', 'Just the two of you, or a group?', '¿Solo vosotros dos o un grupo?'),
  sizeCaption: () => T('В группе минимум 3 человека, включая тебя', 'A group needs at least 3 people, you included',
                       'Un grupo necesita al menos 3 personas, contándote'),
  /** OF.06: выбрано «вдвоём» — подпись говорит правило выбора, а не про группу. */
  sizeCaptionSolo: () => T('Один человек — ты выбираешь, с кем встретиться, из тех, кто скажет «да»',
                           'One person — you pick who you meet from those who say yes',
                           'Una persona — eliges con quién quedar entre quienes digan que sí'),
  /** Границы — из констант: бесплатный потолок может поменяться, и подпись обязана поменяться с ним. */
  sizeSub: (k: string) => {
    const lo = GROUP_MIN_TOTAL, hi = GROUP_FREE_MAX_TOTAL, plus = GROUP_FREE_MAX_TOTAL + 1;
    return k === '1:1'
      ? T('только вы вдвоём', 'just the two of us', 'solo vosotros dos')
      : T(`${lo}–${hi} человек`, `${lo}–${hi} people`, `${lo}–${hi} personas`);
  },
  howMany: () => T('Сколько вас, включая тебя', 'How many, you included', 'Cuántos, contándote'),
  freeNote: () => T('В группе до 5 человек. Вместимость одинакова для всех тарифов.',
                    'Groups hold up to 5 people on every plan.',
                    'Hasta 5 personas por grupo en todos los planes.'),

  /** GR.08 — общий лимит вместимости после «6+». */
  plusTitle: () => T('Вместимость группы', 'Group capacity', 'Capacidad del grupo'),
  plusLead: () => T('Выбери до 5 человек', 'Choose up to 5 people', 'Elige hasta 5 personas'),
  plusNote: () => T(
    'В группе до 5 человек, включая тебя. Вместимость группы и ограничения приглашений одинаковы для Free и Plus.',
    'A group holds up to 5 people, including you. Group capacity and invitation limits are the same for Free and Plus.',
    'Un grupo admite hasta 5 personas, incluyéndote. La capacidad y los límites de invitaciones son iguales en Free y Plus.'),
  getPlus: () => T('Подключить Kleal Plus', 'Get Kleal Plus', 'Obtén Kleal Plus'),
  keepFive: () => T('Оставить 5', 'Keep it at 5', 'Mantener en 5'),

  whenAsk: () => T('Когда тебе удобно?', 'When works for you?', '¿Cuándo te viene bien?'),
  whenCaption: () => T('Выбери день и время — они попадут в план', 'Pick a day and a time — they go into the plan',
                       'Elige un día y una hora: irán al plan'),
  whenStep: () => T('Когда', 'When', 'Cuándo'),
  day: () => T('День', 'Day', 'Día'),
  time: () => T('Время', 'Time', 'Hora'),
  timeZone: () => T('Часовой пояс', 'Time zone', 'Zona horaria'),
  /** GR.09a — лист пояса. */
  tzTitle: () => T('Часовой пояс', 'Time zone', 'Zona horaria'),
  tzLead: () => T('Выбери часовой пояс', 'Pick a time zone', 'Elige una zona horaria'),
  done: () => T('Готово', 'Done', 'Listo'),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),

  whoAsk: () => T('С кем хочешь встретиться?', 'Who would you like to meet?', '¿A quién te gustaría conocer?'),
  whoCaption: () => T('Kleal предложит только тех, кто подходит', 'Kleal only suggests people who fit',
                      'Kleal solo sugiere a quien encaja'),
  whoStep: () => T('Кто', 'Who', 'Quién'),
  whoPref: () => T('С кем хочешь встретиться', 'Who you’d like to meet', 'A quién te gustaría conocer'),
  /** Женщины / Мужчины / Все — ключи те же, что у SEXES: Female / Male / Any. */
  sexChip: (k: string) =>
    k === 'Female' ? T('Женщины', 'Women', 'Mujeres')
    : k === 'Male' ? T('Мужчины', 'Men', 'Hombres')
    : T('Все', 'Anyone', 'Cualquiera'),
  age: () => T('Возраст', 'Age', 'Edad'),
  anyAge: () => T('Любой', 'Any age', 'Cualquier edad'),

  whereAsk: () => T('Где это будет?', 'Where should it happen?', '¿Dónde debería ser?'),
  whereStep: () => T('Где', 'Where', 'Dónde'),
  linkAsk: () => T('Где пройдёт звонок?', 'Where does the call happen?', '¿Dónde será la llamada?'),
  /** GRO.11: онлайн-группа — вопрос и подсказка со ссылкой. */
  linkAskGroup: () => T('Где встречаетесь? Вставь ссылку на звонок — Zoom, Meet или любую другую.',
                        'Where do you meet? Paste your call link — Zoom, Meet or any other.',
                        '¿Dónde os veis? Pega el enlace de la llamada — Zoom, Meet u otro.'),
  linkHintGroup: () => T('Ссылка придёт вместе с планом и откроется за 10 минут до звонка. Её получат только участники плана.',
                         'The link comes with the plan and opens 10 minutes before the call. Only people in the plan get it.',
                         'El enlace llega con el plan y se abre 10 minutos antes de la llamada. Solo lo reciben quienes están en el plan.'),
  /** O.09 — звонок один на один: ссылку получит только тот, кого выберешь. */
  linkHintSolo: () => T('Ссылка придёт вместе с планом и откроется за 10 минут до звонка. Её получит только тот, кого ты выберешь.',
                        'The link comes with the plan and opens 10 minutes before the call. Only the person you pick gets it.',
                        'El enlace llega con el plan y se abre 10 minutos antes de la llamada. Solo lo recibe la persona que elijas.'),
  /** Ссылку можно не давать сразу — у звонка и у гибрида её добавляют в плане («Add the call link», O.21e / HY.21e / GRO.25a). */
  linkLater: () => T('Можно оставить пустым — ссылку добавишь позже, в плане.', 'You can leave it empty — add the link later, in the plan.',
                     'Puedes dejarlo vacío — añade el enlace más tarde, en el plan.'),
  linkLaterLine: () => T('Звонок · ссылка позже', 'Video call · link later', 'Videollamada · enlace más tarde'),
  linkPhGroup: () => T('Вставь ссылку Zoom, Meet или любую другую', 'Paste a Zoom, Meet or any link', 'Pega un enlace de Zoom, Meet o cualquiera'),
  linkStep: () => T('Ссылка', 'Link', 'Enlace'),
  bothAsk: () => T('Где встречаемся и где звонок?', 'Where to meet, and where’s the call?', '¿Dónde quedamos y dónde es la llamada?'),
  /** HY.09 / GRH.11 — третий шаг гибрида: место и ссылка сразу. */
  bothAskSolo: () => T('Где встречаетесь? Выбери место и вставь ссылку на звонок — на случай, если человек подключится удалённо.',
                       'Where do you meet? Pick the place and paste a call link in case they join remotely.',
                       '¿Dónde quedáis? Elige el lugar y pega un enlace de llamada por si se une en remoto.'),
  bothAskGroup: () => T('Где встречаетесь? Выбери место и вставь ссылку на звонок для тех, кто подключится удалённо.',
                        'Where do you meet? Pick the place and paste a call link for anyone joining remotely.',
                        '¿Dónde quedáis? Elige el lugar y pega un enlace de llamada para quien se una en remoto.'),
  bothHint: () => T('Точное место видишь только ты, пока не подтвердят. Ссылка на звонок придёт вместе с планом и откроется за 10 минут.',
                    'Only you see the exact spot until it’s confirmed. The call link comes with the plan and opens 10 minutes before.',
                    'Solo tú ves el sitio exacto hasta que se confirme. El enlace llega con el plan y se abre 10 minutos antes.'),
  modeHybrid: () => T('Гибрид · вживую или в звонке', 'Hybrid · in person or on a call', 'Híbrido · en persona o en llamada'),
  bothStep: () => T('Место и ссылка', 'Place & link', 'Lugar y enlace'),
  radius: () => T('Откуда люди готовы приехать?', 'How far can people come from?', '¿Desde qué distancia puede venir la gente?'),
  exactPlaceholder: () => T('Точное место (необязательно)', 'Exact spot (optional)', 'Lugar exacto (opcional)'),
  exactNote: (area: string) => area
    ? T(`Точное место видишь только ты. Остальные видят «${area}», пока все не подтвердят.`,
        `Only you see the exact spot. Others see ${area} until everyone confirms.`,
        `Solo tú ves el lugar exacto. Los demás ven ${area} hasta que todos confirmen.`)
    : T('Точное место видишь только ты. Остальные видят район, пока все не подтвердят.',
        'Only you see the exact spot. Others see the area until everyone confirms.',
        'Solo tú ves el lugar exacto. Los demás ven la zona hasta que todos confirmen.'),
  expandMap: () => T('Развернуть карту', 'Expand the map', 'Ampliar el mapa'),

  /** GR.11a — лист «Pick the exact spot». */
  spotTitle: () => T('Выбери точное место', 'Pick the exact spot', 'Elige el lugar exacto'),
  spotSub: () => T('Двигай карту, чтобы булавка встала на место.', 'Move the map to put the pin on the spot.',
                   'Mueve el mapa para poner el pin en el lugar.'),
  spotSearch: () => T('Найти место или адрес', 'Search for a place or address', 'Busca un lugar o dirección'),
  useSpot: () => T('Выбрать это место', 'Use this spot', 'Usar este lugar'),
  back: () => T('Назад', 'Back', 'Atrás'),
  findMe: () => T('Найти меня', 'Find me', 'Encontrarme'),
  collapse: () => T('Свернуть', 'Collapse', 'Contraer'),

  sumAsk: () => T('Вот что получилось — проверь. Чтобы что-то поменять, просто скажи мне.',
                  'Here’s what I got — check it.  To change anything, just tell me.',
                  'Esto es lo que tengo, revísalo. Para cambiar algo, solo dímelo.'),
  sumCaption: () => T('Kleal ищет по этим деталям', 'Kleal searches with these details', 'Kleal busca con estos detalles'),
  mode: () => T('Тип', 'Mode', 'Modo'),
  format: () => T('Формат', 'Format', 'Formato'),
  category: () => T('Категория', 'Category', 'Categoría'),
  audience: () => T('Аудитория', 'Audience', 'Público'),
  kleal: () => T('Сводка Kleal', 'Kleal summary', 'Resumen de Kleal'),
  groupOf: (n: number) => T(`Группа из ${n}`, `Group of ${n}`, `Grupo de ${n}`),
  oneToOne: () => '1:1',
  start: () => T('Начать поиск', 'Start search', 'Iniciar búsqueda'),
  changeIt: () => T('Изменить', 'Change it', 'Cambiarlo'),

  /** GR.12a — Kleal предлагает два пути правки. */
  changeAsk: () => T('Конечно. Поменяй сам или просто скажи мне, что изменить — время, место или кого ищешь.',
                     'Sure. Change it yourself, or just tell me what to change — the time, the place or who you’re looking for.',
                     'Claro. Cámbialo tú o dime qué cambiar: la hora, el lugar o a quién buscas.'),
  /** GRO.12a: онлайн — «the time, the link or who». */
  changeAskOnline: () => T('Конечно. Поменяй сам или просто скажи мне, что изменить — время, ссылку или кого ищешь.',
                           'Sure. Change it yourself, or just tell me what to change — the time, the link or who you’re looking for.',
                           'Claro. Cámbialo tú o dime qué cambiar: la hora, el enlace o a quién buscas.'),
  changeCaption: () => T('Kleal обновит сводку по ходу', 'Kleal updates the summary as you go', 'Kleal actualiza el resumen sobre la marcha'),
  editMyself: () => T('Поменяю сам', 'Edit it myself', 'Lo cambio yo'),

  /** GR.12b — строки аккордеона «What do you want to change?». */
  rowWhat: () => T('Что', 'What', 'Qué'),
  rowHow: () => T('Как встречаемся', 'How you meet', 'Cómo quedáis'),
  rowHowMany: () => T('Сколько', 'How many', 'Cuántos'),
  rowWhen: () => T('Когда', 'When', 'Cuándo'),
  rowWho: () => T('Кто', 'Who', 'Quién'),
  rowWhere: () => T('Где', 'Where', 'Dónde'),
  whatPlaceholder: () => T('Название интента', 'Intent name', 'Nombre de la propuesta'),
  ideas: () => T('Или выбери из идей Kleal', 'Or pick one of Kleal’s ideas', 'O elige una idea de Kleal'),
  oneToOneLocked: () => T('Это интент на двоих — сделать из него группу здесь нельзя.',
                          'This is a one-to-one intent — it can’t become a group here.',
                          'Es una propuesta para dos: aquí no puede convertirse en grupo.'),
  /** GR.12j — ответ Kleal после «Apply». */
  updatedWhen: (when: string) => T(`Готово — теперь ${when}. Проверь и запускай поиск.`,
                                    `Done — it’s ${when} now. Check it and start the search.`,
                                    `Hecho: ahora es ${when}. Revísalo y empieza la búsqueda.`),
  /** GR.12a словами: что именно поменялось — «Sun 5 October, 20:00 · Women, 25–30». */
  updatedTalk: (what: string) => T(`Готово — ${what}. Проверь и запускай поиск.`,
                                   `Done — ${what}. Check it and start the search.`,
                                   `Hecho: ${what}. Revísalo y empieza la búsqueda.`),
  /** Не понял: что можно сказать словами, и что место проще поправить на карте. */
  talkUnclear: () => T(
    'Не понял, что поменять. Скажи, например: «в субботу в 20:00», «девушки 25–30», «на 4 человека» или «в радиусе 5 км». Место проще поправить на карте — «Поменяю сам».',
    'I didn’t catch what to change. Try “Saturday at 20:00”, “women 25–30”, “4 people” or “within 5 km”. The place is easier on the map — tap Edit it myself.',
    'No entendí qué cambiar. Prueba con «el sábado a las 20:00», «chicas 25–30», «4 personas» o «a 5 km». El lugar es más fácil en el mapa: toca Lo cambio yo.'),
  talkPast: () => T('Это время уже прошло — назови другое.', 'That time has already passed — pick another one.', 'Esa hora ya pasó: elige otra.'),
  talkPlus: (max: number) => T(`В группе до ${max} человек на любом тарифе.`,
                               `Groups hold up to ${max} people on every plan.`,
                               `Hasta ${max} personas por grupo en todos los planes.`),
  talkFormat: () => T('Формат встречи здесь не меняется — другой формат значит новый интент.',
                      'The format stays — a different format means a new intent.',
                      'El formato no cambia aquí: otro formato significa un plan nuevo.'),
  talkSame: () => T('Так уже и стоит — ничего менять не нужно.', 'It’s already like that — nothing to change.', 'Ya está así, no hay nada que cambiar.'),
  updatedOther: () => T('Готово — обновил. Проверь и запускай поиск.',
                        'Done — I’ve updated it. Check it and start the search.',
                        'Hecho, lo he actualizado. Revísalo y empieza la búsqueda.'),
};

/** Возрастные чипы GR.10: три диапазона и «любой» ([0, 0] — без рамки, поиск не отсекает никого). */
export const AGE_PRESETS: [number, number][] = [[18, 25], [25, 35], [35, 45], [0, 0]];
export const agePresetLabel = ([lo, hi]: [number, number]) => (lo || hi ? `${lo}–${hi}` : WIZ.anyAge());

/**
 * Дни для ряда GR.09: 14 дней от сегодня — «Today», «Tue 21» … «Sat 1 Aug». Месяц дописывается,
 * только когда он уже не текущий: в пределах месяца он шум, на границе — без него «Sat 1» читается
 * как «первое этого месяца, уже прошедшее».
 */
export function dayChips(n = 14, from = new Date()): { key: string; label: string }[] {
  const loc = dateLocale();
  const out: { key: string; label: string }[] = [];
  for (let i = 0; i < n; i++) {
    const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + i, 12);
    const wd = d.toLocaleDateString(loc, { weekday: 'short' }).replace(/\.$/, '');
    const wdCap = wd.charAt(0).toUpperCase() + wd.slice(1);
    const mon = d.getMonth() !== from.getMonth()
      ? ' ' + d.toLocaleDateString(loc, { month: 'short' }).replace(/\.$/, '') : '';
    out.push({
      key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`,
      label: i === 0 ? T('Сегодня', 'Today', 'Hoy') : `${wdCap} ${d.getDate()}${mon}`,
    });
  }
  return out;
}

/** Время для ряда GR.09: каждые 30 минут, 00:00–23:30, всегда 24-часовое (заметка к GR.09). */
export const TIME_SLOTS: number[] = Array.from({ length: 48 }, (_, i) => i * 30);

/** «Thu 23 July» — дата карточки сводки, как на кадре GR.12: без запятой, месяц полностью. */
export function cardDate(dateKey: string): string {
  const loc = dateLocale();
  const d = new Date(dateKey + 'T12:00:00');
  const wd = d.toLocaleDateString(loc, { weekday: 'short' }).replace(/\.$/, '');
  const wdCap = wd.charAt(0).toUpperCase() + wd.slice(1);
  const month = d.toLocaleDateString(loc, { month: 'long' });
  // По-русски месяц в родительном падеже даёт сама локаль только вместе с днём.
  const dm = loc === 'ru-RU' ? d.toLocaleDateString(loc, { day: 'numeric', month: 'long' }) : `${d.getDate()} ${month}`;
  return `${wdCap} ${dm}`;
}

/**
 * Пояс строкой выбора GR.09/GR.09a: «Madrid, Spain (GMT+2)».
 *
 * Город — столица пояса, а не город анкеты: на кадре у Mateo «Barcelona», но пояс телефона и город
 * анкеты совпадают не всегда (телефон в Москве, анкета барселонская — и выходило «Barcelona,
 * Russia»). Смещение считается здесь же, а не через Intl `shortOffset`: Hermes его не отдаёт.
 */
const TZ_PLACE: Record<string, [string, string, string]> = {
  'Europe/Madrid': ['Madrid', 'Spain', 'Испания'],
  'Europe/London': ['London', 'United Kingdom', 'Великобритания'],
  'Europe/Lisbon': ['Lisbon', 'Portugal', 'Португалия'],
  'Europe/Athens': ['Athens', 'Greece', 'Греция'],
  'Europe/Berlin': ['Berlin', 'Germany', 'Германия'],
  'Europe/Paris': ['Paris', 'France', 'Франция'],
  'Europe/Moscow': ['Moscow', 'Russia', 'Россия'],
  'America/New_York': ['New York', 'United States', 'США'],
};
/** «GMT+2», «GMT−4», «GMT» — по разнице местных часов пояса и UTC в эту минуту. */
export function gmtOffset(tz: string, at = new Date()): string {
  try {
    const p = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric',
    }).formatToParts(at);
    const g = (t: string) => Number(p.find((x) => x.type === t)?.value);
    const local = Date.UTC(g('year'), g('month') - 1, g('day'), g('hour') % 24, g('minute'));
    const mins = Math.round((local - Date.UTC(at.getUTCFullYear(), at.getUTCMonth(), at.getUTCDate(),
      at.getUTCHours(), at.getUTCMinutes())) / 60000);
    if (!Number.isFinite(mins)) return '';
    if (!mins) return 'GMT';
    const h = Math.floor(Math.abs(mins) / 60), m = Math.abs(mins) % 60;
    return `GMT${mins > 0 ? '+' : '−'}${h}${m ? ':' + String(m).padStart(2, '0') : ''}`;
  } catch {
    return '';
  }
}
export function tzPlace(tz: string): string {
  const p = TZ_PLACE[tz];
  const off = gmtOffset(tz);
  const country = p ? T(p[2], p[1], p[1]) : '';
  return `${p ? p[0] : tzCity(tz)}${country ? ', ' + country : ''}${off ? ` (${off})` : ''}`;
}
/** Пояса листа GR.09a: свой первым, дальше ходовые — как на кадре. */
export function tzChoices(): string[] {
  const base = [deviceTz(), 'America/New_York', 'Europe/Lisbon', 'Europe/London', 'Europe/Athens',
                'Europe/Madrid', 'Europe/Berlin', 'Europe/Moscow'];
  return base.filter((v, i) => base.indexOf(v) === i);
}

/**
 * «Kleal summary» карточки GR.12 — одно-два предложения о том, как пойдёт поиск, а не пересказ
 * полей (они и так стоят строками выше). Без возраста: «любой» — это 0–0, и в тексте ему не место.
 */
export function wizSummary(o: { size?: string; groupSize?: number; when: string; online?: boolean; hybrid?: boolean }): string {
  if (normalizeIntentSize(o.size, o.groupSize) === 'group') {
    const n = o.groupSize || GROUP_MIN_TOTAL;
    return T(
      `${n} ${plural(n, 'человек', 'человека', 'человек')}, ${o.when}${o.hybrid ? ', со звонком для тех, кто далеко' : ''}. Kleal ищет, пока не подтвердит третий, — меньше трёх план не начнётся.`,
      `${n} people, ${o.when}${o.hybrid ? ', with a call for anyone far away' : ''}. Kleal keeps looking until the third person confirms — below three the plan doesn’t start.`,
      `${n} personas, ${o.when}. Kleal sigue buscando hasta que confirme la tercera; con menos de tres el plan no empieza.`,
    );
  }
  // HY.10: у гибрида — за столом или в звонке.
  if (o.hybrid) {
    return T(
      `Один человек, ${o.when} — вживую или в звонке. Kleal предложит тех, кто подходит, а ты выберешь, с кем встретиться.`,
      `One person, ${o.when} — at a table or on a call. Kleal suggests people who fit and you pick who you meet.`,
      `Una persona, ${o.when} — en persona o en llamada. Kleal te sugiere a quien encaja y tú eliges con quién quedar.`,
    );
  }
  // O.10: у звонка — «с кем поговорить».
  if (o.online) {
    return T(
      `Один человек, ${o.when}. Kleal предложит тех, кто подходит, а ты выберешь, с кем поговорить.`,
      `One person, ${o.when}. Kleal suggests people who fit and you pick who you talk to.`,
      `Una persona, ${o.when}. Kleal te sugiere a quien encaja y tú eliges con quién hablar.`,
    );
  }
  return T(
    `Один человек, ${o.when}. Kleal предложит тех, кто подходит, а ты выберешь, с кем встретиться.`,
    `One person, ${o.when}. Kleal suggests people who fit and you pick who you meet.`,
    `Una persona, ${o.when}. Kleal te sugiere a quien encaja y tú eliges con quién quedar.`,
  );
}
