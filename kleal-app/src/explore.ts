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
export function centerOf(pins: ExplorePin[]): { lat: number; lon: number } | null {
  if (!pins.length) return null;
  let la = 0;
  let lo = 0;
  for (const p of pins) {
    la += p.lat;
    lo += p.lon;
  }
  return { lat: la / pins.length, lon: lo / pins.length };
}

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
};
