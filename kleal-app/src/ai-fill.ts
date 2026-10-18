/**
 * «ЗАПОЛНИТЬ ЧЕРЕЗ ChatGPT» — копия, вызовы и разбор черновика (поручение Ивана через ЛОГИКУ,
 * 18.10.2026: «реализуй полностью автономно… согласуй с агентами дизайна»).
 *
 * Человек добавляет в ChatGPT нашу личную ссылку-коннектор (MCP, веб-ChatGPT в режиме разработчика)
 * и пишет «заполни мой профиль в Kleal» — ChatGPT присылает анкету ЧЕРНОВИКОМ. Запасной путь для
 * всех: спросить ChatGPT обычным чатом, скопировать ответ и вставить его сюда (ai-paste). Ни один
 * путь ничего не сохраняет сам: черновик показывается листом, человек убирает лишнее и подтверждает,
 * слияние с анкетой делает экран (сессия ДИЗАЙН).
 *
 * Контракт сервера (ЛОГИКА): POST /api/onboarding/ai-link → {url, expires_at, prompt{ru,en,es}};
 * POST /api/onboarding/ai-draft {action:get|discard} → {draft}; POST /api/onboarding/ai-paste
 * {text, lang} → {draft}. Имя, возраст, пол, свидания и безопасность в черновик не входят никогда.
 *
 * Компоненты — src/components/AiFill.tsx; здесь только слова и данные, как принято в проекте.
 */
import { api } from './api';
import { T, replyLang } from './i18n';
import { interestLabel } from './interest-label';
import { VIBE_LABEL } from './profile';

/** Поля анкеты онбординга, которые ChatGPT вправе предложить. */
export type AiProfile = {
  city?: string;
  country?: string;
  aboutMe?: string;
  languages?: { comfortable?: string[] };
  interests?: { explicit?: string[] };
  goals?: { primary?: string | string[] };
  vibe?: { primary?: string | string[] };
  format?: { modePreference?: string };
};

export type AiDraft = { source: 'mcp' | 'paste' | string; at: number; profile: AiProfile };
export type AiLink = { url: string; expiresAt: number; prompt: string; pastePrompt: string };

// ===== сеть

export async function aiLink(): Promise<AiLink> {
  const r: any = await api.post('/api/onboarding/ai-link', {});
  const lang = replyLang();
  const pick = (o: any) => String((o || {})[lang] || (o || {}).en || (o || {}).ru || '');
  return {
    url: String(r?.url || ''),
    // Сервер отдаёт целые секунды Unix (ЛОГИКА 18.10).
    expiresAt: Number(r?.expires_at || 0) * 1000,
    prompt: pick(r?.prompt),
    pastePrompt: pick(r?.paste_prompt) || pick(r?.prompt),
  };
}

export async function aiDraft(action: 'get' | 'discard' = 'get'): Promise<AiDraft | null> {
  const r: any = await api.post('/api/onboarding/ai-draft', { action });
  return r?.draft && typeof r.draft === 'object' ? r.draft as AiDraft : null;
}

/** Предел сервера для вставки — 6000 знаков. */
export const PASTE_MAX = 6000;

/** Черновик или код ошибки сервера: empty_text, too_long, rate_limited, extract_failed. */
export async function aiPaste(text: string): Promise<{ draft: AiDraft | null; error?: string }> {
  const r: any = await api.post('/api/onboarding/ai-paste', { text: String(text || '').slice(0, PASTE_MAX), lang: replyLang() });
  if (r?.draft && typeof r.draft === 'object') return { draft: r.draft as AiDraft };
  return { draft: null, error: String(r?.error || 'extract_failed') };
}

// ===== черновик → пункты листа

/** Один пункт листа «Вот что прислал ChatGPT». `key` — путь поля; у чипов — ещё и значение. */
export type AiItem = { key: string; group: AiGroup; label: string; value?: string };
export type AiGroup = 'city' | 'languages' | 'interests' | 'about' | 'goals' | 'vibe' | 'format';

/** Названия частых языков: в Hermes нет Intl.DisplayNames, и вместо «Испанский» вышло бы «Es». */
const LANGS: Record<string, [string, string, string]> = {
  en: ['английский', 'English', 'inglés'], es: ['испанский', 'Spanish', 'español'], ru: ['русский', 'Russian', 'ruso'],
  de: ['немецкий', 'German', 'alemán'], fr: ['французский', 'French', 'francés'], it: ['итальянский', 'Italian', 'italiano'],
  pt: ['португальский', 'Portuguese', 'portugués'], uk: ['украинский', 'Ukrainian', 'ucraniano'], ca: ['каталанский', 'Catalan', 'catalán'],
  zh: ['китайский', 'Chinese', 'chino'], ja: ['японский', 'Japanese', 'japonés'], ko: ['корейский', 'Korean', 'coreano'],
  ar: ['арабский', 'Arabic', 'árabe'], tr: ['турецкий', 'Turkish', 'turco'], pl: ['польский', 'Polish', 'polaco'],
  nl: ['нидерландский', 'Dutch', 'neerlandés'], he: ['иврит', 'Hebrew', 'hebreo'], hi: ['хинди', 'Hindi', 'hindi'],
};
const langName = (code: string) => {
  const c = String(code || '').trim().toLowerCase().split(/[-_]/)[0];
  const row = LANGS[c];
  if (row) return T(row[0], row[1], row[2]);
  try { return new Intl.DisplayNames([replyLang()], { type: 'language' }).of(code) || code; } catch { return code; }
};
const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const list = (v: unknown): string[] => (Array.isArray(v) ? v : v ? [v] : []).map((x) => String(x || '').trim()).filter(Boolean);

export function draftItems(p: AiProfile): AiItem[] {
  const out: AiItem[] = [];
  const place = [p.city, p.country].map((x) => String(x || '').trim()).filter(Boolean).join(', ');
  if (place) out.push({ key: 'city', group: 'city', label: place });
  for (const l of list(p.languages?.comfortable)) out.push({ key: 'languages', group: 'languages', label: cap(langName(l)), value: l });
  for (const k of list(p.interests?.explicit)) {
    // Ключа нет в реестре — interestLabel вернёт его как есть («board_games»): показываем словами.
    const l = interestLabel(k);
    out.push({ key: 'interests', group: 'interests', label: l && l !== k ? l : cap(k.replace(/_/g, ' ')), value: k });
  }
  const about = String(p.aboutMe || '').trim();
  if (about) out.push({ key: 'aboutMe', group: 'about', label: about });
  for (const g of list(p.goals?.primary)) out.push({ key: 'goals', group: 'goals', label: AI.goal(g), value: g });
  for (const v of list(p.vibe?.primary)) out.push({ key: 'vibe', group: 'vibe', label: AI.vibe(v), value: v });
  const fmt = String(p.format?.modePreference || '').trim();
  if (fmt) out.push({ key: 'format', group: 'format', label: AI.format(fmt), value: fmt });
  return out;
}

/** Черновик без убранных пунктов — то, что экран сольёт с анкетой. */
export function keepOnly(p: AiProfile, removed: Set<string>): AiProfile {
  const gone = (key: string, value?: string) => removed.has(key + ':' + (value ?? ''));
  const out: AiProfile = {};
  if (!gone('city') && (p.city || p.country)) { if (p.city) out.city = p.city; if (p.country) out.country = p.country; }
  const langs = list(p.languages?.comfortable).filter((l) => !gone('languages', l));
  if (langs.length) out.languages = { comfortable: langs };
  const ints = list(p.interests?.explicit).filter((k) => !gone('interests', k));
  if (ints.length) out.interests = { explicit: ints };
  if (p.aboutMe && !gone('aboutMe')) out.aboutMe = p.aboutMe;
  const goals = list(p.goals?.primary).filter((g) => !gone('goals', g));
  if (goals.length) out.goals = { primary: Array.isArray(p.goals?.primary) ? goals : goals[0] };
  const vibes = list(p.vibe?.primary).filter((v) => !gone('vibe', v));
  if (vibes.length) out.vibe = { primary: Array.isArray(p.vibe?.primary) ? vibes : vibes[0] };
  if (p.format?.modePreference && !gone('format', p.format.modePreference)) out.format = { modePreference: p.format.modePreference };
  return out;
}

export const itemId = (it: AiItem) => it.key + ':' + (it.value ?? '');

// ===== слова

export const AI = {
  cardTitle: () => T('Заполнить через ChatGPT', 'Fill in with ChatGPT', 'Rellenar con ChatGPT'),
  cardSub: () => T('Он уже знает тебя — пусть расскажет за тебя. Ты всё проверишь.',
    'It already knows you — let it answer for you. You review everything.',
    'Ya te conoce: deja que responda por ti. Tú lo revisas todo.'),
  cardBadge: () => T('2 минуты', '2 minutes', '2 minutos'),

  guideTitle: () => T('Подключи Kleal к ChatGPT', 'Connect Kleal to ChatGPT', 'Conecta Kleal a ChatGPT'),
  guideSub: () => T('Один раз, на chatgpt.com с компьютера. Нужен Plus или Pro.',
    'Once, on chatgpt.com on a computer. Needs Plus or Pro.',
    'Una vez, en chatgpt.com desde el ordenador. Necesitas Plus o Pro.'),
  step: (n: number) => T(`Шаг ${n}`, `Step ${n}`, `Paso ${n}`),
  steps: () => [
    { t: T('Открой настройки', 'Open Settings', 'Abre Ajustes'), d: T('Аватар внизу слева → Settings', 'Avatar bottom left → Settings', 'Avatar abajo a la izquierda → Settings') },
    { t: T('Apps & Connectors → Advanced settings', 'Apps & Connectors → Advanced settings', 'Apps & Connectors → Advanced settings'),
      d: T('Включи Developer mode. Если пункта нет — он может быть в Settings → Security.', 'Turn on Developer mode. Can’t find it? It may be under Settings → Security.', 'Activa Developer mode. ¿No lo ves? Puede estar en Settings → Security.') },
    { t: T('Create — новый коннектор', 'Create a connector', 'Create — nuevo conector'), d: T('Name: Kleal, MCP Server URL — твоя ссылка, Authentication: No authentication', 'Name: Kleal, MCP Server URL — your link, Authentication: No authentication', 'Name: Kleal, MCP Server URL — tu enlace, Authentication: No authentication') },
    { t: T('Напиши в ChatGPT: «@Kleal заполни мой профиль»', 'In ChatGPT, write “@Kleal fill in my profile”', 'En ChatGPT, escribe «@Kleal rellena mi perfil»'),
      d: T('Пришлёт ссылку — открой её и нажми «Сохранить», черновик появится здесь. Без ссылки: «+» → Developer mode → Kleal.',
        'If it sends a link, open it and tap “Save” — the draft shows up here. Without the link: “+” → Developer mode → Kleal.',
        'Si envía un enlace, ábrelo y pulsa «Guardar»: el borrador aparecerá aquí. Sin enlace: «+» → Developer mode → Kleal.') },
  ],
  link: () => T('Твоя ссылка', 'Your link', 'Tu enlace'),
  phrase: () => T('Фраза для чата', 'Phrase for the chat', 'Frase para el chat'),
  copyLink: () => T('Скопировать ссылку', 'Copy link', 'Copiar enlace'),
  copyPhrase: () => T('Скопировать фразу', 'Copy phrase', 'Copiar frase'),
  copied: () => T('Скопировано', 'Copied', 'Copiado'),
  expiresIn: (min: number) => T(`Ссылка действует ещё ${min} мин`, `Link works for ${min} more min`, `El enlace vale ${min} min más`),
  personal: () => T('Ссылка личная — не пересылай её.', 'The link is personal — don’t share it.', 'El enlace es personal: no lo compartas.'),

  pasteTitle: () => T('Или вставь ответ ChatGPT', 'Or paste ChatGPT’s answer', 'O pega la respuesta de ChatGPT'),
  pasteSub: () => T('Спроси в любом чате ChatGPT фразой выше, скопируй ответ целиком.',
    'Ask ChatGPT in any chat with the phrase above and copy the whole answer.',
    'Pregunta a ChatGPT en cualquier chat con la frase de arriba y copia la respuesta entera.'),
  pastePlaceholder: () => T('Вставь сюда ответ ChatGPT', 'Paste ChatGPT’s answer here', 'Pega aquí la respuesta de ChatGPT'),
  fromClipboard: () => T('Вставить из буфера', 'Paste from clipboard', 'Pegar del portapapeles'),
  pasteGo: () => T('Разобрать', 'Read it', 'Leer'),

  draftTitle: () => T('Вот что прислал ChatGPT', 'Here’s what ChatGPT sent', 'Esto es lo que envió ChatGPT'),
  draftSub: () => T('Убери то, что не про тебя. В профиль попадёт только оставшееся.',
    'Remove anything that isn’t you. Only what’s left goes into your profile.',
    'Quita lo que no sea tuyo. Solo lo que quede irá a tu perfil.'),
  group: (g: AiGroup) => ({
    city: T('Город', 'City', 'Ciudad'),
    languages: T('Языки', 'Languages', 'Idiomas'),
    interests: T('Интересы', 'Interests', 'Intereses'),
    about: T('О себе', 'About me', 'Sobre mí'),
    goals: T('Зачем ты здесь', 'What you’re here for', 'A qué vienes'),
    vibe: T('Настрой', 'Vibe', 'Rollo'),
    format: T('Как удобнее', 'How you like to meet', 'Cómo prefieres quedar'),
  }[g]),
  format: (v: string) => ({
    offline_first: T('Лучше вживую', 'In person first', 'Mejor en persona'),
    online_first: T('Лучше онлайн', 'Online first', 'Mejor online'),
    hybrid: T('И так, и так', 'Either way', 'De las dos formas'),
    online: T('Онлайн', 'Online', 'Online'),
    offline: T('Вживую', 'In person', 'En persona'),
  } as Record<string, string>)[v] || cap(v.replace(/_/g, ' ')),
  goal: (v: string) => ({
    friends: T('Новые друзья', 'New friends', 'Nuevos amigos'),
    games: T('Поиграть вместе', 'Play together', 'Jugar juntos'),
    language: T('Практика языка', 'Language practice', 'Practicar idiomas'),
    networking: T('Полезные знакомства', 'Networking', 'Contactos'),
    watch: T('Смотреть вместе', 'Watch together', 'Ver juntos'),
    sport: T('Спорт', 'Sport', 'Deporte'),
    city_explore: T('Открывать город', 'Explore the city', 'Descubrir la ciudad'),
  } as Record<string, string>)[v] || cap(v.replace(/_/g, ' ')),
  vibe: (v: string) => cap(VIBE_LABEL[v]?.() || ({ curious: T('любопытный', 'curious', 'curioso') } as Record<string, string>)[v] || v),
  pasteError: (code: string) => ({
    empty_text: T('Вставь ответ ChatGPT целиком.', 'Paste ChatGPT’s whole answer.', 'Pega la respuesta entera de ChatGPT.'),
    too_long: T('Слишком длинно — до 6000 знаков.', 'Too long — up to 6000 characters.', 'Demasiado largo: hasta 6000 caracteres.'),
    rate_limited: T('Слишком часто. Попробуй через час.', 'Too many tries. Try again in an hour.', 'Demasiados intentos. Prueba en una hora.'),
    extract_failed: T('Не вышло разобрать ответ. Попроси ChatGPT ответить ещё раз.', 'Couldn’t read that answer. Ask ChatGPT again.', 'No pude leer la respuesta. Pídeselo otra vez a ChatGPT.'),
    'sign in required': T('Сначала войди в Kleal.', 'Sign in to Kleal first.', 'Primero inicia sesión en Kleal.'),
  } as Record<string, string>)[code] || T('Не получилось. Попробуй ещё раз.', 'That didn’t work. Try again.', 'No ha funcionado. Inténtalo de nuevo.'),
  remove: () => T('Убрать', 'Remove', 'Quitar'),
  restore: () => T('Вернуть', 'Bring back', 'Recuperar'),
  confirm: (n: number) => T(`Добавить в профиль · ${n}`, `Add to profile · ${n}`, `Añadir al perfil · ${n}`),
  discard: () => T('Не надо', 'Not now', 'Ahora no'),
  nothing: () => T('ChatGPT ничего не прислал о тебе', 'ChatGPT sent nothing about you', 'ChatGPT no envió nada sobre ti'),
  fromMcp: () => T('Из ChatGPT · коннектор', 'From ChatGPT · connector', 'De ChatGPT · conector'),
  fromPaste: () => T('Из ответа ChatGPT', 'From ChatGPT’s answer', 'De la respuesta de ChatGPT'),

  waitingTitle: () => T('Ждём ChatGPT…', 'Waiting for ChatGPT…', 'Esperando a ChatGPT…'),
  waitingSub: () => T('Как только он заполнит анкету, она появится здесь.', 'As soon as it fills the form, it shows up here.', 'En cuanto rellene el formulario, aparecerá aquí.'),
  arrivedTitle: () => T('Черновик пришёл', 'Your draft is here', 'Ha llegado tu borrador'),
  arrivedSub: () => T('Посмотри и оставь то, что про тебя.', 'Have a look and keep what’s you.', 'Échale un vistazo y quédate con lo tuyo.'),
  review: () => T('Посмотреть', 'Review', 'Revisar'),
  errorTitle: () => T('Не получилось', 'That didn’t work', 'No ha funcionado'),
  errorSub: () => T('Проверь связь и попробуй ещё раз.', 'Check your connection and try again.', 'Revisa la conexión e inténtalo de nuevo.'),
  retry: () => T('Ещё раз', 'Try again', 'Otra vez'),
  expiredTitle: () => T('Ссылка истекла', 'The link expired', 'El enlace caducó'),
  expiredSub: () => T('Сделаем новую — старую в ChatGPT нужно заменить.', 'We’ll make a new one — replace the old one in ChatGPT.', 'Haremos uno nuevo: sustituye el antiguo en ChatGPT.'),
  newLink: () => T('Новая ссылка', 'New link', 'Nuevo enlace'),
  mobileTitle: () => T('На телефоне так не выйдет', 'This won’t work on a phone', 'En el móvil no funciona'),
  mobileSub: () => T('Режим разработчика есть только на chatgpt.com с компьютера. Открой его там — или вставь ответ ChatGPT сюда.',
    'Developer mode is only on chatgpt.com on a computer. Open it there — or paste ChatGPT’s answer here.',
    'El modo desarrollador solo está en chatgpt.com desde el ordenador. Ábrelo allí o pega aquí la respuesta de ChatGPT.'),
  pasteInstead: () => T('Вставить ответ', 'Paste the answer', 'Pegar la respuesta'),
};
