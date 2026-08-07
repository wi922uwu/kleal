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

  /**
   * Разговор с Бадди — просто общение. Интент отсюда НЕ создаётся: сервер лишь сообщает, что
   * распознал в сказанном план (поле `intent`), а решение принимает человек во всплывающем окне.
   */
  chat: (messages: Json[], prof: Json, signals: Json = {}) =>
    api.post<{ reply?: string; intent?: Json | null; signals?: Json; lang?: string }>(
      '/api/buddy/chat', { messages, profile: prof, signals }
    ),

  /**
   * Построитель интента: уточняет ТЕМУ и ничего больше. Время, место, пол и размер компании он не
   * спрашивает намеренно — их человек ставит руками на следующих экранах, и переспрашивать
   * значило бы заставить отвечать дважды. Это правило живёт в системном промпте сервера.
   */
  intentBuild: (messages: Json[], prof: Json) =>
    api.post<{ reply?: string; valid?: boolean; ready?: boolean; intent?: Json | null; hints?: string[] }>(
      '/api/buddy/intent-build', { messages, profile: prof }
    ),

  /** Три варианта из профиля для пустого экрана создания. `seed` меняет выборку для «Ещё варианты». */
  intentSuggest: (prof: Json, lang: string, seed = '') =>
    api.post<{ suggestions?: string[] }>('/api/buddy/intent-suggest', { profile: prof, lang, seed }),
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

  /** Группы, к которым можно присоединиться. Это планы, а не «люди с похожими интересами». */
  groups: (self: string, limit = 60) =>
    api.get<{ groups?: Json[] }>(
      `/api/agent/groups?limit=${limit}&self=${encodeURIComponent(self)}`
    ),

  /** Открытые планы вокруг. GET — общий список, без учёта профиля. */
  explore: (self: string, limit = 60) =>
    api.get<{ plans?: Json[] }>(
      `/api/agent/explore?limit=${limit}&self=${encodeURIComponent(self)}`
    ),

  /**
   * То же, но с профилем: сервер отбирает только совместимые интенты. Главный экран строже
   * обзора — там показываются люди, к которым есть смысл обращаться, а не все подряд.
   */
  forYou: (self: string, prof: Json, limit = 30) =>
    api.post<{ plans?: Json[] }>('/api/agent/explore', { limit, self, profile: prof }),

  /**
   * Приглашение (O.14): человек увидит интент и профиль отправителя. Одно открытое приглашение на
   * пару в одну сторону — повторная отправка обновляет его, а не плодит копии; это правило сервера.
   */
  propose: (from: string, to: string, intent: Json, note = '') =>
    api.post<{ ok?: boolean; id?: string; error?: string }>(
      '/api/agent/propose', { from, to, intent, note }
    ),

  /**
   * «Не интересно» (O.13b): решение уходит ранжированию как обратная связь — этого человека
   * больше не предлагать первым. Это не блокировка: написать он по-прежнему может.
   */
  feedback: (name: string, decision: 'accept' | 'reject', uid: string) =>
    api.post<{ ok?: boolean }>('/api/agent/feedback', { name, decision, uid }),

  /**
   * Жалоба (O.13b). Причина — из словаря сервера (fake/harassment/spam/unsafe/underage/other):
   * «Спасибо, посмотрим» обязано соответствовать строке, которую кто-то реально откроет.
   */
  report: (self: string, name: string, reason: string, text = '') =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/report', { self, name, reason, text }),

  /** Отозвать НЕотвеченное приглашение (O.15 «Cancel»). Отозвать может только отправитель. */
  withdraw: (id: string, self: string) =>
    api.post<{ ok?: boolean; status?: string; error?: string }>('/api/agent/withdraw', { id, self }),

  /**
   * Категория темы для сводки O.10 («Category: Languages»). Это отдельный агент фильтрации;
   * пустой ответ — не ошибка, строка категории тогда просто не показывается.
   */
  categorize: (text: string) =>
    api.post<{ category?: string; topics?: string[] }>('/api/filter/categorize', { text }),

  /** Кого этот человек заблокировал, плюс его же жалобы. */
  safety: (self: string) =>
    api.get<{ blocked?: string[]; reports?: Json[] }>(
      `/api/agent/safety?self=${encodeURIComponent(self)}`
    ),

  /**
   * Заблокировать или разблокировать. `on: false` — снять блокировку.
   *
   * Себя сервер называет `self`, а не `who`: с `who` он молча отвечает TWO_PEOPLE_REQUIRED,
   * потому что видит пустого отправителя. Проверено на живом стенде.
   */
  block: (self: string, name: string, on: boolean) =>
    api.post<{ ok?: boolean; blocked?: string[] }>('/api/agent/block', { self, name, on }),

  /** Исходящие приглашения — по ним карточка выдачи знает, приняли её или отклонили. */
  outbox: (self: string) =>
    api.get<{ requests?: Json[] }>(`/api/agent/outbox?self=${encodeURIComponent(self)}`),

  /**
   * Последнее сообщение в каждой переписке. Одним запросом отвечает на вопрос «а с кем разговор
   * реально идёт» — принятое приглашение это ещё не переписка.
   */
  threads: (self: string) =>
    api.get<{ threads?: Json[] }>(`/api/agent/threads?self=${encodeURIComponent(self)}`),

  /** Переписка с одним человеком, старые сверху. `since` — чтобы дотягивать только новое. */
  thread: (self: string, other: string, since = 0) =>
    api.get<{ messages?: Json[] }>(
      `/api/agent/thread?self=${encodeURIComponent(self)}&with=${encodeURIComponent(other)}&since=${since}`
    ),

  /** Отправить сообщение. Доставка настоящая — сообщение появится и у собеседника. */
  message: (from: string, to: string, text: string) =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/message', { from, to, text }),

  /**
   * Предложить встречу (O.20). Сервер откажет, если человек ещё не принял приглашение
   * (NOT_MATCHED) или если время уже прошло (IN_THE_PAST) — оба случая называются на экране.
   */
  planPropose: (self: string, to: string, p: Json) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      // Ответ отдаёт план целиком в `plan`, id лежит ВНУТРИ него — сверху `id` нет.
      // Ещё один отказ, о котором стоит знать: PLAN_EXISTS, у пары может быть только одна встреча.
      '/api/agent/mplan-propose', { self, to, ...p }
    ),

  /**
   * Ответ на план: confirm | decline | counter | accept_change | reject_change.
   *
   * Контрпредложение (counter) НЕ отменяет встречу — оно паркуется рядом, а старое время
   * продолжает действовать, пока второй не ответит. Это правило борда, и оно живёт на сервере.
   */
  planRespond: (id: string, self: string, action: string, extra: Json = {}) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/mplan-respond', { id, self, action, ...extra }
    ),

  /** Место встречи или ссылка на звонок. Сервер открывает её только подтвердившим (OF.C3).
   *  venue — человеческое имя места («Nømad»), address — куда идти. */
  planAddress: (id: string, self: string, address: string, venue?: string) =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/mplan-address', { id, self, address, venue }),

  /** OF.22/OF.22a/OF.23 — «уже иду» / «опаздываю» / «я на месте». Видит только собеседник,
   *  и только у подтверждённого плана: сервер отклонит статус к встрече, которой ещё нет. */
  planStatus: (id: string, self: string, status: 'otw' | 'late' | 'here', eta_min?: number) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/mplan-status', { id, self, status, eta_min }
    ),

  /**
   * «Состоялось ли» и отзыв — ОДНА запись: второй вызов дописывается в первый, а не заменяет его.
   * Иначе оценка встречи стёрла бы ответ на вопрос, была ли она вообще.
   */
  planFeedback: (id: string, self: string, v: Json) =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/mplan-feedback', { id, self, ...v }),

  /** Планы этого человека: живые и прошедшие. */
  plans: (self: string) =>
    api.get<{ plans?: Json[]; history?: Json[] }>(`/api/agent/mplans?self=${encodeURIComponent(self)}`),

  /** Входящие приглашения. Просроченные и отозванные сервер отсекает сам. */
  inbox: (self: string) =>
    api.get<{ requests?: Json[] }>(`/api/agent/inbox?self=${encodeURIComponent(self)}`),

  /** Ответ получателя на приглашение (O.C1). Сервер пере-проверяет политику на момент ответа:
   *  между отправкой и согласием человек мог заблокировать или закрыть направление. */
  respondInvite: (id: string, self: string, decision: 'accept' | 'decline', version?: number) =>
    api.post<{ ok?: boolean; error?: string; status?: string }>(
      '/api/agent/respond', { id, self, decision, version }
    ),

  /** «Я открыл эту переписку» — из этой отметки у второй стороны получаются двойные галочки
   *  (MSG.11). Отметка одна на пару, по-сообщенного статуса нет намеренно. */
  threadRead: (self: string, other: string) =>
    api.post<{ ok?: boolean }>('/api/agent/thread-read', { self, with: other }),
};
