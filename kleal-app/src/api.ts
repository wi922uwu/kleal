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
