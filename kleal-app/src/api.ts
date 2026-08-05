/**
 * Клиент к бекенду Kleal.
 *
 * По умолчанию смотрит на ИЗОЛИРОВАННЫЙ СТЕНД, а не на прод: приложение в разработке пишет живых
 * людей в users.json, и указать сюда прод — значит однажды случайно зарегистрировать тестовые
 * профили в боевом пуле. Переключение — через EXPO_PUBLIC_API (app.json → extra или .env).
 *
 * Адрес стенда эфемерный (бесплатный trycloudflare) и меняется при перезапуске туннеля.
 * Актуальный: ops/dev-stack.sh tunnel
 */

const DEFAULT_BASE = 'https://thousands-developmental-bonus-calculation.trycloudflare.com';

export const API_BASE: string =
  (process.env.EXPO_PUBLIC_API && String(process.env.EXPO_PUBLIC_API)) || DEFAULT_BASE;

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

type Json = Record<string, any>;

async function request<T = Json>(path: string, init?: RequestInit, timeoutMs = 30000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(API_BASE + path, {
      ...init,
      signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    });
    const text = await res.text();
    let body: any = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = text;
    }
    if (!res.ok) throw new ApiError('HTTP ' + res.status, res.status, body);
    return body as T;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  get: <T = Json>(path: string) => request<T>(path),
  post: <T = Json>(path: string, body: Json) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
};

// ---------------------------------------------------------------- онбординг

export type SignupResult = { ok?: boolean; error?: string; login?: string };

export const onboarding = {
  /** Создать логин. Пароль уходит один раз и на сервере лежит только PBKDF2-хеш. */
  signup: (login: string, password: string, name = '') =>
    api.post<SignupResult>('/api/onboarding/signup', { login, password, name }),

  signin: (login: string, password: string) =>
    api.post<SignupResult>('/api/onboarding/signin', { login, password }),

  /** Привязать собранный профиль к логину, чтобы следующий вход вёл в приложение, а не сюда же. */
  attach: (login: string, name: string, profile: Json) =>
    api.post('/api/onboarding/attach', { login, name, profile }),

  /**
   * Записать собранный профиль. Это единственный писатель users.json — намеренно: пока запись
   * идёт одним путём, профиль не может разойтись сам с собой.
   */
  register: (profile: Json) => api.post('/api/onboarding/register', { profile }),

  /** Текст сводки от агента по собранному профилю. */
  summary: (profile: Json) => api.post('/api/onboarding/summary', { profile }),

  /** Реплика агента на шаге интересов — единственный шаг, где отвечает модель. */
  chat: (payload: Json) => api.post('/api/onboarding/chat', payload),

  photoUrl: (uid: string) => `${API_BASE}/api/onboarding/photo/${encodeURIComponent(uid)}.jpg`,
};

// ---------------------------------------------------------------- профиль

export const profile = {
  /** Прочитать сохранённую строку профиля. Ключ — имя: другого идентификатора у хранилища нет. */
  get: (name: string) => api.post<{ user: Json | null }>('/api/onboarding/profile', { name }),

  /**
   * Изменить профиль. Сервер принимает только поля из своего белого списка (_PATCH_FIELDS) и молча
   * выбрасывает остальные — то есть отправить сюда что попало не выйдет, но и узнать об этом можно
   * только по ответу: {ok:false,"no editable fields in patch"}.
   */
  update: (name: string, patch: Json) =>
    api.post<{ ok?: boolean; error?: string }>('/api/onboarding/profile-update', { name, patch }),

  /** Доступность (§4.4 receiving policy). Без `receiving` — просто чтение текущего статуса. */
  receiving: (name: string, receiving: Json = {}) =>
    api.post<{ ok?: boolean; status?: string; error?: string }>('/api/onboarding/receiving', { name, receiving }),
};

export const buddy = {
  /**
   * Переписать сводку под изменившийся профиль — адаптировать, а не дописать в конец.
   * `personality` уезжает как материал, но НЕ как текст для копирования: это отдельное поле со
   * своим владельцем (тест Kleal), и слипание этих двух текстов уже однажды съедало сводку.
   */
  resummary: (prof: Json, current: string, personality = '', lang = 'ru') =>
    api.post<{ summary?: string }>('/api/buddy/resummary', { profile: prof, current, personality, lang }),

  /** Итог теста личности: один вызов на все восемь ответов. */
  persona: (payload: Json) => api.post<Json>('/api/buddy/persona', payload),
};

// ---------------------------------------------------------------- интенты и поиск

export const agent = {
  /**
   * Свободный текст → интент + кандидаты. Разбирает модель, поэтому это единственный вход,
   * которому можно отдать «хочу посмотреть футбол вечером» как есть.
   */
  plan: (query: string, profile: Json, ctx: Json = {}, override?: Json) =>
    api.post('/api/agent/plan', { query, profile, ctx, override }),

  /** Уже собранный интент → кандидаты, без разбора текста. */
  match: (intent: Json, profile: Json, ctx: Json = {}) =>
    api.post('/api/agent/match', { intent, profile, ctx }),

  /**
   * §12 лестница расширения: на шаг шире по ОДНОЙ оси, а не «показать всех».
   *
   * axis обязателен по смыслу, хотя сервер и обходится без него: без параметра он молча берёт
   * первую ось, и второе нажатие «Расширить поиск» возвращает ту же выдачу. Ступень выбирает
   * клиент — он один знает, что уже пробовали.
   */
  expand: (intent: Json, profile: Json, axis: string, ctx: Json = {}) =>
    api.post('/api/agent/expand', { intent, profile, axis, ctx }),
};
