/**
 * Черновик ChatGPT → анкета онбординга (встраивание, сессия ДИЗАЙН, 18.10.2026).
 *
 * Слова, вызовы и разбор черновика — src/ai-fill.ts (ведёт «ДИЗАЙН (fork)»). Здесь — куда
 * подтверждённое ложится:
 *   • «О себе», «Зачем ты здесь», «Настрой», «Как удобнее» — сразу в анкету: отдельного шага у них
 *     нет, а человек их только что подтвердил на листе;
 *   • город, языки, интересы — в `aiSuggest`: шаги анкеты открываются с ними ВЫБРАННЫМИ, и человек
 *     проходит шаг одним нажатием, видя, что именно уходит. Так черновик не может молча записать
 *     город без координат или интерес мимо правила подтверждения.
 */
import { patch, set, getState } from './state';
import { PLACES, DEFAULT_AREA, type Area } from './components/AreaPicker';
import { LANGS } from './onboarding';
import { mapPools } from './mindmap';
import { T } from './i18n';
import type { AiProfile } from './ai-fill';

const norm = (s: unknown) => String(s || '').trim().toLowerCase();
const list = (v: unknown): string[] => (Array.isArray(v) ? v : v ? [v] : []).map((x) => String(x || '').trim()).filter(Boolean);

/** Код языка → имя, как его хранит шаг «Языки» (LANGS: 'English', 'Spanish', …). */
const CODE: Record<string, string> = {
  en: 'English', es: 'Spanish', de: 'German', fr: 'French', it: 'Italian', pt: 'Portuguese', ru: 'Russian',
  uk: 'Ukrainian', ca: 'Catalan', nl: 'Dutch', pl: 'Polish', zh: 'Chinese', ja: 'Japanese', ar: 'Arabic',
};
function langOf(v: string): string {
  const known = LANGS.find(([en, , ru]) => norm(en) === norm(v) || norm(ru) === norm(v));
  if (known) return known[0];
  return CODE[norm(v).slice(0, 2)] && norm(v).length <= 5 ? CODE[norm(v).slice(0, 2)] : v;
}

/** Применить подтверждённый черновик. Возвращает, что легло в предложения шагам. */
export function applyAiDraft(p: AiProfile) {
  if (p.aboutMe) set('aboutMe', p.aboutMe);
  if (p.goals?.primary) set('goals.primary', p.goals.primary);
  if (p.vibe?.primary) set('vibe.primary', p.vibe.primary);
  if (p.format?.modePreference) set('format.modePreference', p.format.modePreference);
  const sug = {
    at: Date.now(),
    city: p.city || undefined,
    country: p.country || undefined,
    languages: [...new Set(list(p.languages?.comfortable).map(langOf))],
    interests: list(p.interests?.explicit),
  };
  patch({ aiSuggest: sug });
  return sug;
}

/**
 * КОРОТКИЙ ПУТЬ (18.10.2026, Иван после живой проверки: «ChatGPT уже заполнил мой профиль — зачем мне
 * ещё раз проходить онбординг»). Всё, что человек оставил на листе черновика, считается подтверждённым
 * там же и пишется в анкету СРАЗУ — шаги «Где ты», «Языки» и карта больше не открываются. Недостающее
 * спрашивает один экран app/ai-finish.tsx.
 *
 * Город: если он есть в списке городов — с координатами и районом, как после шага «Где ты»; если нет —
 * только название (сервер засчитывает «Area» и по городу). Языки — к именам шага (English, Spanish…).
 * Интересы — в interests.explicit, тем же путём, что выбранные на карте (onMapDone в app/chat.tsx).
 */
export function applyAiDraftFull(p: AiProfile) {
  if (p.aboutMe) set('aboutMe', p.aboutMe);
  if (p.goals?.primary) set('goals.primary', p.goals.primary);
  if (p.vibe?.primary) set('vibe.primary', p.vibe.primary);
  if (p.format?.modePreference) set('format.modePreference', p.format.modePreference);
  const city = String(p.city || '').trim();
  if (city) {
    let hit: { country: string; c: [string, number, number] } | null = null;
    for (const pl of PLACES) {
      const c = pl.cities.find(([n]) => norm(n) === norm(city));
      if (c) { hit = { country: pl.country, c }; break; }
    }
    set('city', hit ? hit.c[0] : city);
    set('country', hit ? hit.country : String(p.country || '').trim());
    set('geo.comfortableAreas', [hit ? hit.c[0] : city]);
    if (hit) {
      set('geo.located', true);
      set('geo.coarseLat', hit.c[1]);
      set('geo.coarseLon', hit.c[2]);
    }
  }
  const langs = [...new Set(list(p.languages?.comfortable).map(langOf))];
  if (langs.length) set('languages.comfortable', langs);
  const ints = list(p.interests?.explicit);
  if (ints.length) {
    const cur: string[] = getState().profile?.interests?.explicit || [];
    set('interests.explicit', [...cur, ...ints.filter((k) => !cur.includes(k))]);
  }
  patch({ aiSuggest: null });
}

/** Шаг «Где ты»: город из черновика, если он есть в списке городов; иначе — как обычно. */
export function suggestedArea(): Area {
  const s = getState().aiSuggest;
  const city = norm(s?.city);
  if (city) {
    for (const pl of PLACES) {
      const c = pl.cities.find(([n]) => norm(n) === city);
      if (c) return { ...DEFAULT_AREA, country: pl.country, city: c[0], pinCity: c[0], lat: c[1], lon: c[2] };
    }
  }
  return DEFAULT_AREA;
}

export const suggestedLangs = (): string[] => getState().aiSuggest?.languages || [];

/** Карта интересов: только ключи, которые на карте есть, — чужое слово выбранным не встанет. */
export function suggestedInterests(): string[] {
  const want = new Set(getState().aiSuggest?.interests || []);
  if (!want.size) return [];
  const pools = mapPools();
  const known = new Set<string>();
  for (const k of Object.keys(pools.leaves)) for (const it of pools.leaves[k] || []) known.add(it.key);
  return [...want].filter((k) => known.has(k));
}

/** Реплика агента после возврата с листа. */
export function aiAnnounce(s: { city?: string; languages?: string[]; interests?: string[] }): string {
  const bits: string[] = [];
  if (s.city) bits.push(s.city);
  const nl = (s.languages || []).length, ni = (s.interests || []).length;
  if (nl) bits.push(T(`языки: ${nl}`, `${nl} language${nl > 1 ? 's' : ''}`, `${nl} idioma${nl > 1 ? 's' : ''}`));
  if (ni) bits.push(T(`интересы: ${ni}`, `${ni} interest${ni > 1 ? 's' : ''}`, `${ni} interés${ni > 1 ? 'es' : ''}`));
  const got = bits.join(', ');
  return T(
    `Взял у ChatGPT${got ? ': ' + got : ''}. На следующих шагах всё уже выбрано — просто проверь. А пока: как тебя зовут?`,
    `Got it from ChatGPT${got ? ': ' + got : ''}. The next steps are pre-filled — just check them. First, what’s your name?`,
    `Recibido de ChatGPT${got ? ': ' + got : ''}. Los próximos pasos ya están rellenos: solo revísalos. Primero, ¿cómo te llamas?`,
  );
}
