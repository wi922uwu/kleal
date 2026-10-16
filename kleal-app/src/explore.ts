/**
 * Открытые интенты вокруг — данные для экрана карты (кадр «Search · Map», node 1688-27392).
 *
 * Пин на карте — это НЕ человек, а его открытый интент: место встречи, которое он назвал сам.
 * Разница принципиальная, и на ней держится приватность экрана. Домашняя точка человека
 * клиенту не отдаётся вовсе (Вердикт#22, `matching_core/contracts/geo_privacy.py`), а место
 * мероприятия он публикует осознанно — иначе на встречу невозможно прийти.
 *
 * Поэтому здесь нет и не должно появиться поля «где живёт этот человек». Если такое поле
 * когда-нибудь приедет с сервера, его надо не рисовать, а убирать на сервере.
 */
import { T } from './i18n';

export type ExplorePin = {
  /** id интента — ключ списка и то, с чем открывается карточка. */
  id: string;
  /** Автор: имя приезжает в поле `who`, а не `name` — у ручки explore своя схема. */
  who: string;
  /** id автора: отклик зовёт его по id — у тёзок подписи равны (kleal-ms/docs/IDENTITY.md). */
  whoId?: string;
  photo?: string;
  age?: number;
  verified: boolean;
  /** О чём встреча — первым идёт то, что показывается на карточке. */
  topics: string[];
  title: string;
  when: string;
  /** Район словами. Точный адрес сюда НЕ приезжает и приезжать не должен. */
  area: string;
  lat: number;
  lon: number;
  /** Расстояние в км, как его посчитал сервер. Может отсутствовать. */
  dist?: number;
  /** Map-feed-only metadata. Legacy explore rows deliberately leave these undefined. */
  mode?: 'offline' | 'hybrid';
  kind?: 'one_to_one' | 'group';
  count?: number;
};

const num = (v: any): number | undefined => {
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
};

/**
 * Разбор ответа `/api/agent/explore`.
 *
 * Строки без координат отбрасываются молча: на карте им места нет, а показывать пин в нулевой
 * широте — это Гвинейский залив, куда никто не собирался. Такие интенты видны в списке.
 */
export function explorePins(rows: any[]): ExplorePin[] {
  const out: ExplorePin[] = [];
  for (const r of rows || []) {
    if (!r) continue;
    const lat = num(r.lat);
    const lon = num(r.lon);
    if (lat === undefined || lon === undefined) continue;
    if (lat === 0 && lon === 0) continue;
    const topics = Array.isArray(r.topics) ? r.topics.map(String).filter(Boolean) : [];
    out.push({
      id: String(r.intentId || r.id || `${r.who}-${lat}-${lon}`),
      who: String(r.who || r.name || ''),
      whoId: r.who_id ? String(r.who_id) : undefined,
      photo: r.photo ? String(r.photo) : undefined,
      age: num(r.age),
      verified: !!r.verified,
      topics,
      title: String(r.title || topics[0] || ''),
      when: String(r.when || ''),
      area: String(r.area || ''),
      lat,
      lon,
      dist: num(r.dist),
    });
  }
  return out;
}

/**
 * Сколько пинов стоят в одной точке.
 *
 * Нужно не для красоты: на живых данных девять интентов из двенадцати лежат на одной координате
 * (запасной центр города у профилей без гео), и без этого карта показывает один пин вместо девяти,
 * молча пряча остальные. Пусть лучше будет видно, что их много.
 */
export function stackedAt(pins: ExplorePin[]): Map<string, number> {
  const key = (p: ExplorePin) => `${p.lat.toFixed(5)},${p.lon.toFixed(5)}`;
  const m = new Map<string, number>();
  for (const p of pins) m.set(key(p), (m.get(key(p)) || 0) + 1);
  return m;
}

export const pinKey = (p: ExplorePin) => `${p.lat.toFixed(5)},${p.lon.toFixed(5)}`;

/** Центр всех точек — чтобы карта открылась там, где люди, а не там, где зашит город. */
/**
 * Откуда смотреть, если своей точки нет: не среднее всех пинов, а САМАЯ ПЛОТНАЯ их кучка.
 * Среднее двух пинов — в Испании и в Центральной Африке — это середина Сахары, где нет ничего.
 * Берётся пин, у которого больше всех соседей в радиусе ~50 км, и центр этой окрестности.
 */
export function centerOf(pins: ExplorePin[]): { lat: number; lon: number } | null {
  if (!pins.length) return null;
  const near = (a: ExplorePin, b: ExplorePin) => {
    const dLat = a.lat - b.lat;
    const dLon = (a.lon - b.lon) * Math.cos(((a.lat + b.lat) / 2) * Math.PI / 180);
    return dLat * dLat + dLon * dLon < 0.45 * 0.45;      // ~50 км в градусах широты
  };
  let best: ExplorePin[] = [];
  for (const p of pins) {
    const group = pins.filter((q) => near(p, q));
    if (group.length > best.length) best = group;
  }
  let la = 0;
  let lo = 0;
  for (const p of best) {
    la += p.lat;
    lo += p.lon;
  }
  return { lat: la / best.length, lon: lo / best.length };
}

/**
 * Переход «карта ↔ планета» — одно движение одной камеры, и его длительность общая для экрана
 * (проявление надписей) и страницы карты (морф по кадрам). Кривые движения живут на странице.
 */
export const MORPH = { total: 1650 } as const;

export const MAP = {
  nearby: (n: number) =>
    T(`${n} ${n % 10 === 1 && n % 100 !== 11 ? 'интент' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 'интента' : 'интентов'} рядом`,
      `${n} intent${n === 1 ? '' : 's'} nearby`, `${n} propuesta${n === 1 ? '' : 's'} cerca`),
  showAll: () => T('Показать все', 'Show all', 'Mostrar todo'),
  map: () => T('Карта', 'Map', 'Mapa'),
  list: () => T('Список', 'List', 'Lista'),
  online: () => T('Онлайн', 'Online', 'Online'),
  empty: () => T('Рядом пока никого', 'Nobody nearby yet', 'Todavía no hay nadie cerca'),
  emptyNote: () =>
    T('Открытые встречи появятся здесь, как только их кто-нибудь назначит поблизости.',
      'Open meetups show up here as soon as somebody plans one nearby.', 'Las quedadas abiertas aparecerán aquí en cuanto alguien planee una cerca de ti.'),
  failed: () => T('Не удалось загрузить', 'Could not load', 'No se pudo cargar'),
  retry: () => T('Ещё раз', 'Try again', 'Reintentar'),
  locate: () => T('Где я', 'Locate me', 'Ubicarme'),
  filters: () => T('Фильтры', 'Filters', 'Filtros'),
  search: () => T('Поиск', 'Search', 'Buscar'),
  nearbyList: () => T('Интенты рядом', 'Intents nearby', 'Propuestas cerca'),
  close: () => T('Закрыть', 'Close', 'Cerrar'),
  /** Первый вход в карту: пока грузятся дома и улицы, вместо серого пятна — тихая заставка. */
  loading: () => T('Собираем карту', 'Building the map', 'Preparando el mapa'),
  loadingNote: () => T('Улицы, дома и интенты рядом', 'Streets, buildings and intents nearby', 'Calles, edificios y propuestas cerca'),
  /** Подпись на кучке: сколько интентов стоят в этой же точке. */
  stack: (n: number) => T(`ещё ${n - 1}`, `+${n - 1} more`, `+${n - 1} más`),
  noGeo: () =>
    T('Не видно, где вы. Разрешите доступ к геопозиции, чтобы карта открывалась рядом с вами.',
      'We cannot see where you are. Allow location access so the map opens near you.', 'No podemos ver dónde estás. Permite el acceso a la ubicación para que el mapa se abra cerca tuyo.'),
  partial: (n: number) =>
    n > 0
      ? T(`${n} ${n === 1 ? 'интент пока без точки' : 'интента пока без точки'}`,
          `${n} intent${n === 1 ? '' : 's'} cannot be placed yet`, `${n} propuesta${n === 1 ? '' : 's'} todavía sin situar`)
      : T('Часть интентов пока без точки', 'Some intents cannot be placed yet', 'Algunas propuestas todavía no se pueden situar'),
  back: () => T('Назад', 'Back', 'Atrás'),
  intentDetails: () => T('Интент', 'Intent', 'Propuesta'),
  detailUnavailable: () => T('Интент недоступен', 'Intent unavailable', 'Propuesta no disponible'),
  detailUnavailableNote: () => T('Возможно, он уже закрыт или удалён.', 'It may have been closed or deleted.', 'Puede que haya sido cerrado o eliminado.'),
  someone: () => T('Участник Kleal', 'Kleal member', 'Miembro de Kleal'),
  offline: () => T('Офлайн', 'Offline', 'Presencial'),
  hybrid: () => T('Гибрид', 'Hybrid', 'Híbrido'),
  oneToOne: () => T('1:1', '1:1', '1:1'),
  group: (n: number) => T(`Группа · ${n}`, `Group · ${n}`, `Grupo · ${n}`),
  meetingPlace: () => T('Место встречи', 'Meeting place', 'Lugar de reunión'),
  country: () => T('Страна', 'Country', 'País'),
  openIntent: () => T('Открыть', 'Open', 'Abrir'),
  respond: () => T('Ответить', 'Respond', 'Responde'),
  notNow: () => T('Не сейчас', 'Not now', 'No ahora'),

  // ── Карточка чужого интента ───────────────────────────────────────────────────────────
  /**
   * Правило из шапки этого файла, сказанное человеку вслух: на карте стоит место ВСТРЕЧИ,
   * которое автор назвал сам, а не его дом. Без этой строки карточка с адресом читается как
   * «вот где он живёт».
   */
  placeNote: () => T(
    'Это место назвал сам автор. Где он живёт, Kleal не показывает.',
    'The author named this place themselves. Kleal never shows where they live.',
    'El lugar lo ha indicado la propia persona. Kleal nunca muestra dónde vive.'),
  /** У онлайн-встречи ссылки до согласия нет — и обещать её карточка не должна. */
  linkAfterYes: () => T('Ссылку пришлют после согласия',
    'You get the link once they agree', 'Te enviarán el enlace cuando acepten'),
  /** Своя затея на карте: менять её здесь нечем, для этого есть «Активность». */
  yours: () => T('Это твой интент', 'This is your intent', 'Esta es tu propuesta'),
  yoursNote: () => T(
    'Его видят на карте другие. Менять и закрывать — в «Активности».',
    'Other people see it on the map. You edit and close it in My Activity.',
    'Otras personas lo ven en el mapa. Lo editas y lo cierras en Mi actividad.'),
  /** Отклик уже ушёл: та же формулировка, что в переписке — состояние одно на всё приложение. */
  sentWaiting: () => T('Отправлено · ждём ответа',
    'Sent · waiting for an answer', 'Enviado · esperando respuesta'),
  // ── Паспорт затеи. Подписи слово в слово как в «Активности»: одна затея — одни слова. ──
  formatLabel: () => T('Формат', 'Mode', 'Modo'),
  sizeLabel: () => T('Состав', 'Format', 'Formato'),
  groupWord: () => T('Группа', 'Group', 'Grupo'),
  seatsLabel: () => T('Места', 'Seats', 'Plazas'),
  seatsValue: (left: number, max: number) =>
    T(`${left} из ${max} свободны`, `${left} of ${max} free`, `${left} de ${max} libres`),
  seatsTotal: (max: number) => T(`до ${max} человек`, `up to ${max} people`, `hasta ${max} personas`),

  /** У группы кнопка называется честно: это заявка автору, а не вход в комнату. */
  respondToAuthor: () => T('Написать автору', 'Message the author', 'Escribir a quien lo propone'),
  respondToAuthorNote: () => T(
    'Это заявка автору: звать в группу решает он.',
    'This is a request to the author: they decide who joins.',
    'Es una solicitud a quien lo propone: decide quién entra.'),
  respondFailed: () => T('Не удалось отправить', 'Could not send', 'No se pudo enviar'),
  /** Больше открытых откликов зараз держать нельзя — это правило OF.09, не ошибка связи. */
  respondCapped: () => T('Слишком много открытых откликов',
    'Too many open responses', 'Demasiadas respuestas abiertas'),
};
