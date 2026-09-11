import { COUNTRY_CENTROIDS, countryCentroid, type CountryCentroid } from './country-centroids';

/** Языки карты — те же три, что и у интерфейса (`Lang` в src/i18n.ts). Расходиться им нельзя:
 *  карта по-английски внутри испанского приложения читается как несработавший перевод. */
export type OnlineIntentLocale = 'ru' | 'en' | 'es';
export type OnlineIntentMode = 'online' | 'hybrid';
export type OnlineIntentFormat = '1:1' | 'group';

export type OnlineIntentItem = Readonly<{
  id: string;
  title: string;
  who: string;
  topics: string[];
  when: string;
  mode: OnlineIntentMode;
  format: OnlineIntentFormat;
  participantCount?: number;
  groupSize?: number;
  minTotal?: number;
  maxTotal?: number;
  countryCode?: string;
}>;

export type OnlineIntentCountryCluster = Readonly<{
  code: string;
  name: string;
  latitude: number;
  longitude: number;
  count: number;
  onlineCount: number;
  hybridCount: number;
  intents: OnlineIntentItem[];
}>;

export type OnlineIntentGlobeStats = Readonly<{
  total: number;
  countries: number;
  unknown: number;
  online: number;
  hybrid: number;
  oneToOne: number;
  groups: number;
}>;

export type OnlineIntentGlobeModel = Readonly<{
  locale: OnlineIntentLocale;
  countries: OnlineIntentCountryCluster[];
  unknown: OnlineIntentItem[];
  stats: OnlineIntentGlobeStats;
}>;

export type BuildOnlineIntentGlobeOptions = Readonly<{
  locale?: OnlineIntentLocale;
}>;

export type OnlineIntentGlobeStatus = 'loading' | 'ready' | 'error';

export type OnlineIntentGlobeInsets = Readonly<{
  top?: number;
  right?: number;
  bottom?: number;
  left?: number;
}>;

export type OnlineIntentGlobeProps = Readonly<{
  model: OnlineIntentGlobeModel;
  status: OnlineIntentGlobeStatus;
  onRetry?: () => void;
  onOpenIntent?: (intent: OnlineIntentItem) => void;
  /** Lets the owner reserve space for the shared Map/List switcher and BottomNav. */
  contentInsets?: OnlineIntentGlobeInsets;
  testID?: string;
}>;

type Row = Record<string, unknown>;

const INACTIVE = new Set([
  'archived', 'cancelled', 'canceled', 'closed', 'completed', 'declined', 'deleted', 'draft',
  'expired', 'failed', 'inactive', 'paused', 'removed', 'withdrawn',
]);

const MODE_ONLINE = new Set(['online', 'remote', 'virtual', 'video', 'voice']);
const MODE_HYBRID = new Set(['hybrid', 'mixed', 'online and offline', 'online offline']);
const FORMAT_GROUP = new Set(['group', 'small group', 'large group', 'small', 'large']);
const FORMAT_ONE = new Set(['1 1', 'one to one', 'one on one', 'pair', 'direct']);

const COUNTRY_ALIASES: Readonly<Record<string, string>> = Object.freeze({
  'great britain': 'GB',
  'russian federation': 'RU',
  'российская федерация': 'RU',
  'south korea': 'KR',
  'republic of korea': 'KR',
  'north korea': 'KP',
  'czech republic': 'CZ',
  'turkey': 'TR',
  'turkiye': 'TR',
  'türkiye': 'TR',
  'united states': 'US',
  'united states of america': 'US',
  'usa': 'US',
  'u s a': 'US',
  'uk': 'GB',
  'u k': 'GB',
  'ivory coast': 'CI',
  'cote d ivoire': 'CI',
  'cape verde': 'CV',
  'swaziland': 'SZ',
  'north macedonia': 'MK',
  'palestine': 'PS',
});

const rowOf = (value: unknown): Row =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Row : {};

const text = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number' ? String(value).trim() : '';

const finite = (value: unknown): number | undefined => {
  if (value === null || value === undefined || value === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const firstText = (...values: unknown[]): string => {
  for (const value of values) {
    const out = text(value);
    if (out) return out;
  }
  return '';
};

/**
 * Comparison-only normalization. It does not guess a locale, region, city, or country.
 */
function token(value: unknown): string {
  return text(value)
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/&/g, ' and ')
    .replace(/[^a-zа-я0-9]+/gi, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

const NAME_TO_CODE: Readonly<Record<string, string>> = (() => {
  const names: Record<string, string> = { ...COUNTRY_ALIASES };
  for (const country of Object.values(COUNTRY_CENTROIDS)) {
    names[token(country.nameEn)] = country.code;
    names[token(country.nameRu)] = country.code;
    names[token(country.nameEs)] = country.code;
  }
  return Object.freeze(names);
})();

function modeOf(row: Row, intent: Row): OnlineIntentMode | undefined {
  const value = token(firstText(
    row.mode,
    row.meetingMode,
    row.meeting_mode,
    row.locationMode,
    row.location_mode,
    intent.mode,
    intent.meetingMode,
    intent.meeting_mode,
    intent.locationMode,
    intent.location_mode,
  ));
  if (MODE_ONLINE.has(value)) return 'online';
  if (MODE_HYBRID.has(value)) return 'hybrid';
  return undefined;
}

function isActive(row: Row, intent: Row): boolean {
  if (row.open === false || intent.open === false) return false;
  if (row.deleted === true || intent.deleted === true) return false;
  if (row.deletedAt != null || row.deleted_at != null || intent.deletedAt != null || intent.deleted_at != null) {
    return false;
  }
  const status = token(firstText(row.status, intent.status));
  return !status || !INACTIVE.has(status);
}

function formatOf(row: Row, intent: Row): OnlineIntentFormat {
  const value = token(firstText(row.format, row.kind, row.size, intent.format, intent.kind, intent.size));
  if (FORMAT_GROUP.has(value)) return 'group';
  if (FORMAT_ONE.has(value)) return '1:1';
  const groupSize = finite(row.groupSize ?? row.group_size ?? intent.groupSize ?? intent.group_size);
  const minTotal = finite(row.min_total ?? row.minTotal ?? intent.min_total ?? intent.minTotal);
  const maxTotal = finite(row.max_total ?? row.maxTotal ?? intent.max_total ?? intent.maxTotal);
  return Math.max(groupSize || 0, minTotal || 0, maxTotal || 0) >= 3 ? 'group' : '1:1';
}

function countryFrom(row: Row, intent: Row): CountryCentroid | undefined {
  const countryValue = row.country ?? intent.country;
  const countryObject = rowOf(countryValue);
  const explicitCode = firstText(
    row.countryCode,
    row.country_code,
    intent.countryCode,
    intent.country_code,
    countryObject.code,
    countryObject.countryCode,
  ).toUpperCase();

  // Only a strict ISO-like alpha-2 value from an explicit country field is accepted.
  // ipCountryCode, timezone, locale, city, area, lat and lon are intentionally never read.
  if (/^[A-Z]{2}$/.test(explicitCode)) {
    const byCode = countryCentroid(explicitCode);
    if (byCode) return byCode;
  }

  const explicitName = typeof countryValue === 'string'
    ? countryValue
    : firstText(countryObject.name, countryObject.label);
  const explicitNameCode = explicitName.trim().toUpperCase();
  if (/^[A-Z]{2}$/.test(explicitNameCode)) {
    const byNameCode = countryCentroid(explicitNameCode);
    if (byNameCode) return byNameCode;
  }
  const codeFromName = NAME_TO_CODE[token(explicitName)];
  return codeFromName ? countryCentroid(codeFromName) : undefined;
}

function topicsOf(row: Row, intent: Row): string[] {
  const raw = Array.isArray(row.topics) ? row.topics : Array.isArray(intent.topics) ? intent.topics : [];
  return raw.map(text).filter(Boolean).slice(0, 8);
}

function itemOf(row: Row, intent: Row, mode: OnlineIntentMode): OnlineIntentItem | undefined {
  const id = firstText(row.intentId, row.intent_id, row.id, intent.intentId, intent.intent_id, intent.id);
  if (!id) return undefined;
  const topics = topicsOf(row, intent);
  const title = firstText(row.title, intent.title, topics[0]);
  const format = formatOf(row, intent);
  const groupSize = finite(row.groupSize ?? row.group_size ?? intent.groupSize ?? intent.group_size);
  const minTotal = finite(row.min_total ?? row.minTotal ?? intent.min_total ?? intent.minTotal);
  const maxTotal = finite(row.max_total ?? row.maxTotal ?? intent.max_total ?? intent.maxTotal);
  const participantCount = finite(row.count ?? intent.count);
  const owner = rowOf(row.owner);
  return {
    id,
    title,
    who: firstText(row.who, row.name, owner.displayName, owner.name, intent.who, intent.name),
    topics,
    when: firstText(row.when, row.time, intent.when, intent.time),
    mode,
    format,
    ...(format === 'group' && participantCount !== undefined ? { participantCount } : {}),
    ...(format === 'group' && groupSize !== undefined ? { groupSize } : {}),
    ...(format === 'group' && minTotal !== undefined ? { minTotal } : {}),
    ...(format === 'group' && maxTotal !== undefined ? { maxTotal } : {}),
  };
}

const itemCompare = (a: OnlineIntentItem, b: OnlineIntentItem) =>
  a.title.localeCompare(b.title) || a.who.localeCompare(b.who) || a.id.localeCompare(b.id);

/**
 * Convert explore-like rows into the only data the online map is allowed to render.
 *
 * Accepted location inputs are deliberately narrow: top-level or nested-intent countryCode,
 * country_code, or country. Exact coordinates and IP-derived fields are ignored even when present.
 * A row with a valid Online/Hybrid mode and id but no supported explicit country remains visible in
 * `unknown`; it is never dropped and never placed on a fabricated point.
 */
export function buildOnlineIntentGlobeModel(
  rows: unknown[],
  options: BuildOnlineIntentGlobeOptions = {},
): OnlineIntentGlobeModel {
  const locale: OnlineIntentLocale =
    options.locale === 'ru' ? 'ru' : options.locale === 'es' ? 'es' : 'en';
  const clustered = new Map<string, { country: CountryCentroid; intents: OnlineIntentItem[] }>();
  const unknown: OnlineIntentItem[] = [];
  let online = 0;
  let hybrid = 0;
  let oneToOne = 0;
  let groups = 0;

  for (const raw of Array.isArray(rows) ? rows : []) {
    const row = rowOf(raw);
    if (!Object.keys(row).length) continue;
    const intent = rowOf(row.intent);
    const mode = modeOf(row, intent);
    if (!mode || !isActive(row, intent)) continue;
    const item = itemOf(row, intent, mode);
    if (!item) continue;
    const country = countryFrom(row, intent);
    const withCountry = country ? { ...item, countryCode: country.code } : item;

    if (mode === 'hybrid') hybrid += 1;
    else online += 1;
    if (item.format === 'group') groups += 1;
    else oneToOne += 1;

    if (!country) {
      unknown.push(withCountry);
      continue;
    }
    const group = clustered.get(country.code) || { country, intents: [] };
    group.intents.push(withCountry);
    clustered.set(country.code, group);
  }

  unknown.sort(itemCompare);
  const countries = Array.from(clustered.values()).map(({ country, intents }) => {
    intents.sort(itemCompare);
    return {
      code: country.code,
      name: locale === 'ru' ? country.nameRu
        : locale === 'es' ? country.nameEs : country.nameEn,
      latitude: country.latitude,
      longitude: country.longitude,
      count: intents.length,
      onlineCount: intents.filter((item) => item.mode === 'online').length,
      hybridCount: intents.filter((item) => item.mode === 'hybrid').length,
      intents,
    };
  }).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));

  const total = online + hybrid;
  return {
    locale,
    countries,
    unknown,
    stats: {
      total,
      countries: countries.length,
      unknown: unknown.length,
      online,
      hybrid,
      oneToOne,
      groups,
    },
  };
}

export type OnlineIntentGlobeCopy = Readonly<{
  loading: string;
  emptyTitle: string;
  emptyNote: string;
  errorTitle: string;
  errorNote: string;
  retry: string;
  worldSummary: (total: number, countries: number) => string;
  unknown: (count: number) => string;
  unknownTitle: string;
  unknownNote: string;
  countryMarker: (name: string, count: number) => string;
  countryHint: string;
  listTitle: (name: string, count: number) => string;
  online: string;
  hybrid: string;
  oneToOne: string;
  group: string;
  openIntent: string;
  close: string;
  webNote: string;
}>;

export function onlineIntentGlobeCopy(locale: OnlineIntentLocale): OnlineIntentGlobeCopy {
  if (locale === 'ru') {
    return {
      loading: 'Загружаем онлайн-интенты по миру',
      emptyTitle: 'Пока нет онлайн-встреч',
      emptyNote: 'Здесь появятся открытые Online и Hybrid интенты.',
      errorTitle: 'Не удалось загрузить карту',
      errorNote: 'Проверьте связь и попробуйте ещё раз.',
      retry: 'Ещё раз',
      worldSummary: (total, countries) => `${total} интентов · ${countries} стран`,
      unknown: (count) => `Страна не указана · ${count}`,
      unknownTitle: 'Страна не указана',
      unknownNote: 'Эти интенты доступны онлайн, но сервер не подтвердил страну. Мы не ставим их в случайную точку.',
      countryMarker: (name, count) => `${name}: ${count} интентов`,
      countryHint: 'Открыть интенты этой страны',
      listTitle: (name, count) => `${name} · ${count}`,
      online: 'Online',
      hybrid: 'Hybrid',
      oneToOne: '1:1',
      group: 'Группа',
      openIntent: 'Открыть интент',
      close: 'Закрыть',
      webNote: 'Схема мира · настоящая карта только на устройстве',
    };
  }
  if (locale === 'es') {
    return {
      loading: 'Cargando propuestas online de todo el mundo',
      emptyTitle: 'Aún no hay quedadas online',
      emptyNote: 'Aquí aparecerán las propuestas Online e Híbridas abiertas.',
      errorTitle: 'No se pudo cargar el mapa',
      errorNote: 'Comprueba tu conexión e inténtalo de nuevo.',
      retry: 'Reintentar',
      worldSummary: (total, countries) => `${total} ${total === 1 ? 'propuesta' : 'propuestas'} · ${countries} ${countries === 1 ? 'país' : 'países'}`,
      unknown: (count) => `País sin indicar · ${count}`,
      unknownTitle: 'País sin indicar',
      unknownNote: 'Estas propuestas están disponibles online, pero el servidor no confirmó el país. No las colocamos en un punto al azar.',
      countryMarker: (name, count) => `${name}: ${count} ${count === 1 ? 'propuesta' : 'propuestas'}`,
      countryHint: 'Ver las propuestas de este país',
      listTitle: (name, count) => `${name} · ${count}`,
      online: 'Online',
      hybrid: 'Híbrido',
      oneToOne: '1:1',
      group: 'Grupo',
      openIntent: 'Abrir la propuesta',
      close: 'Cerrar',
      webNote: 'Esquema del mundo · el mapa de verdad solo en el móvil',
    };
  }
  return {
    loading: 'Loading online intents around the world',
    emptyTitle: 'No online meetups yet',
    emptyNote: 'Open Online and Hybrid intents will appear here.',
    errorTitle: 'Could not load the map',
    errorNote: 'Check your connection and try again.',
    retry: 'Try again',
    worldSummary: (total, countries) => `${total} intents · ${countries} countries`,
    unknown: (count) => `Country not provided · ${count}`,
    unknownTitle: 'Country not provided',
    unknownNote: 'These intents are available online, but the server did not confirm a country. We never place them on a random point.',
    countryMarker: (name, count) => `${name}: ${count} intents`,
    countryHint: 'Open intents in this country',
    listTitle: (name, count) => `${name} · ${count}`,
    online: 'Online',
    hybrid: 'Hybrid',
    oneToOne: '1:1',
    group: 'Group',
    openIntent: 'Open intent',
    close: 'Close',
    webNote: 'World overview · the real map is available on device',
  };
}
