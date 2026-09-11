/**
 * Обратное геокодирование: координаты → человеческий адрес.
 *
 * Нужно ровно в одном месте продукта и по одной причине: точку на карте человек ставит рукой, и
 * пока строка над картой говорила «Barcelona», а булавка стояла в Жироне, экран врал. Подпись
 * должна называть то место, куда её поставили.
 *
 * ЧЕМ ГЕОКОДИРУЕМ И ПОЧЕМУ ИМЕННО ИМ.
 *
 * Nominatim (OpenStreetMap) — бесплатный, без ключа, работает на всех трёх платформах, включая веб,
 * на котором эти экраны и проверяются.
 *
 * Рассматривался и отвергнут `Location.reverseGeocodeAsync` из expo-location, который уже стоит в
 * проекте: на Android он требует РАЗРЕШЕНИЯ НА ГЕОЛОКАЦИЮ. Просить доступ к местоположению ради
 * того, чтобы назвать точку, которую человек только что сам ткнул пальцем, — плохой обмен: люди
 * отказывают, и подпись пропадает у всех, кто отказал.
 *
 * ЧЕГО ЭТО СТОИТ. У Nominatim жёсткая политика: не больше запроса в секунду, обязательный
 * User-Agent, никакой массовой выгрузки. Здесь всё это соблюдено — запрос уходит только после
 * того, как карту отпустили, результат кэшируется по округлённым координатам, и очередь не даёт
 * двум запросам уйти чаще раза в секунду. Для продакшена с реальным трафиком этого мало: там нужен
 * либо платный геокодер, либо свой Nominatim. Помечено в ROADMAP.
 */
import { Platform } from 'react-native';

export type Place = {
  /** Что показать человеку: «Carrer de Verdi 12, Gràcia» или «Girona». */
  label: string;
  /** Город — он уезжает в profile.city и в ctx.city поиска (§5.3). Пусто — не определился. */
  city: string;
  /** Район («Gràcia») — для полей, где спрашивают район, а не адрес. Пусто — не определился. */
  district: string;
};

const ENDPOINT = 'https://nominatim.openstreetmap.org/reverse';
/** Политика Nominatim требует назвать себя. Без этого они вправе просто перестать отвечать. */
const UA = 'Kleal/1.0 (social matching app; contact: hello@kleal.app)';

/** Кэш по округлённым координатам: 3 знака — это ~110 м, мельче человеку и не покажешь. */
const cache = new Map<string, Place | null>();
const key = (lat: number, lon: number, lang: string) =>
  `${lat.toFixed(3)},${lon.toFixed(3)},${lang}`;

/** Очередь: не чаще одного запроса в секунду — это их правило, а не наша осторожность. */
let lastCall = 0;
async function throttle() {
  const wait = 1100 - (Date.now() - lastCall);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  lastCall = Date.now();
}

/**
 * Собрать подпись из частей адреса. Порядок — от того, что человек назвал бы первым: улица с
 * домом, иначе район, иначе сам город. Город приписывается справа, если он ещё не сказан.
 */
function labelOf(a: any, fallback: string): string {
  const city = String(a?.city || a?.town || a?.village || a?.municipality || '').trim();
  const road = String(a?.road || a?.pedestrian || a?.footway || '').trim();
  const house = String(a?.house_number || '').trim();
  const area = String(a?.neighbourhood || a?.suburb || a?.quarter || a?.city_district || '').trim();
  const head = road ? (house ? `${road} ${house}` : road) : area || city;
  if (!head) return fallback;
  return city && head !== city ? `${head}, ${city}` : head;
}

/**
 * Адрес точки или null. null — это «не узнали», и экран обязан показать что-то честное вместо
 * выдуманного адреса: пустой ответ, отвалившаяся сеть и таймаут здесь неотличимы и все означают
 * одно и то же.
 */
export async function reverseGeocode(lat: number, lon: number, lang = 'ru'): Promise<Place | null> {
  const k = key(lat, lon, lang);
  if (cache.has(k)) return cache.get(k) || null;
  try {
    await throttle();
    const url = `${ENDPOINT}?format=jsonv2&zoom=16&addressdetails=1`
      + `&lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}&accept-language=${encodeURIComponent(lang)}`;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    // User-Agent из браузера поставить нельзя — там его подставляет сам браузер, и это законно:
    // политика Nominatim просит идентифицировать приложение, а веб-сборка это тестовый стенд.
    const headers: Record<string, string> = Platform.OS === 'web' ? {} : { 'User-Agent': UA };
    const res = await fetch(url, { headers, signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const j: any = await res.json();
    const a = j?.address || {};
    const city = String(a.city || a.town || a.village || a.municipality || a.county || '').trim();
    const district = String(a.neighbourhood || a.suburb || a.quarter || a.city_district || '').trim();
    const place: Place = { label: labelOf(a, String(j?.name || j?.display_name || '').split(',')[0] || ''), city, district };
    if (!place.label && !place.city) throw new Error('empty');
    cache.set(k, place);
    return place;
  } catch {
    // Отрицательный ответ НЕ кэшируем: сеть моргнула — на следующем движении попробуем снова.
    return null;
  }
}

/* ============================================================================================
   ПРЯМОЙ ПОИСК: строка → варианты адресов с координатами.

   Зачем отдельно от обратного. Обратное отвечает на «что за точка под булавкой», прямое — на «где
   находится то, что человек печатает». Второе нужно для точного адреса офлайн-затеи: пока поле
   было простой строкой, интент уезжал с координатами ДОМА автора, и встреча на карте оказывалась
   не там, где её назначили.

   ПОЧЕМУ ВАРИАНТЫ, А НЕ ОДИН ОТВЕТ. «Verdi 12» в Барселоне есть на нескольких улицах, а без
   подсказки человек не узнает, что попал не туда, — узнает тот, кто придёт не по адресу. Выбор
   делает человек, приложение только показывает, что нашлось.

   ПОЧЕМУ ТОЛЬКО ИСПАНИЯ. `countrycodes=es` — запуск идёт по испанским городам, а без ограничения
   «Gran Via» находится в пяти странах и первым идёт не тот. Появятся другие страны — снимать этот
   параметр надо вместе с городом профиля, а не просто так.
   ============================================================================================ */

export type AddressHit = {
  /** Что показать в списке: «Carrer de Verdi, 12, Gràcia, Barcelona». */
  label: string;
  city: string;
  lat: number;
  lon: number;
};

const SEARCH = 'https://nominatim.openstreetmap.org/search';
/** Меньше пяти — не выбор, больше — список, который не читают. */
const LIMIT = 5;
/** Короче этого искать бессмысленно: «ба» найдёт пол-Испании и потратит запрос из лимита. */
const MIN_Q = 3;

const hits = new Map<string, AddressHit[]>();

/**
 * Найти адреса по строке. Пустой список — ничего не нашлось ИЛИ сеть молчит; для поля это одно и
 * то же: подсказать нечего, человек допишет руками.
 *
 * Тот же троттлинг, что у обратного геокодирования, — политика Nominatim одна на оба вызова, и
 * очередь у них общая.
 */
export async function suggestAddress(
  query: string, lang = 'ru', near?: { lat: number; lon: number } | null,
): Promise<AddressHit[]> {
  const q = String(query || '').trim();
  if (q.length < MIN_Q) return [];
  const k = q.toLowerCase() + '|' + lang + '|' + (near ? `${near.lat.toFixed(1)},${near.lon.toFixed(1)}` : '');
  const cached = hits.get(k);
  if (cached) return cached;
  try {
    await throttle();
    /*
      СМЕЩЕНИЕ К ТОЧКЕ ВМЕСТО СТРАНЫ. Есть точка — живая, только что определённая, или из профиля
      — ищем вокруг неё: `viewbox` без `bounded` это предпочтение, а не граница, за рамкой тоже
      найдётся, но позже. Нет точки — прежнее ограничение страной запуска.
    */
    const where = near
      ? `&viewbox=${(near.lon - 0.35).toFixed(3)},${(near.lat + 0.25).toFixed(3)},`
        + `${(near.lon + 0.35).toFixed(3)},${(near.lat - 0.25).toFixed(3)}`
      : '&countrycodes=es';
    const url = `${SEARCH}?format=jsonv2&addressdetails=1&limit=${LIMIT}`
      + `${where}&accept-language=${encodeURIComponent(lang)}`
      + `&q=${encodeURIComponent(q)}`;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 8000);
    const headers: Record<string, string> = Platform.OS === 'web' ? {} : { 'User-Agent': UA };
    const res = await fetch(url, { headers, signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const rows: any[] = await res.json();
    const out: AddressHit[] = [];
    for (const r of rows || []) {
      const lat = Number(r?.lat);
      const lon = Number(r?.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
      const a = r?.address || {};
      const city = String(a.city || a.town || a.village || a.municipality || '').trim();
      // Берём первые три части `display_name`: улица, дом, район. Дальше идут город, провинция и
      // страна — они одинаковы у всех вариантов и только мешают их различать.
      const label = String(r?.display_name || '').split(',').slice(0, 3).map((x) => x.trim())
        .filter(Boolean).join(', ');
      if (!label) continue;
      out.push({ label, city, lat, lon });
    }
    hits.set(k, out);
    return out;
  } catch {
    return [];                          // не кэшируем: сеть моргнула — на следующей букве попробуем
  }
}
