/**
 * Клиент к бекенду Kleal.
 *
 * Смотрит на ПРОД (`/root/kleal-ms`, порты 70xx через шлюз 7080) — по решению Ивана 2026-08-10.
 *
 * До этого здесь стоял изолированный стенд, и стояло намеренно: приложение в разработке пишет
 * живых людей в users.json, а прод считался боевым пулом. Проверено перед переключением — боевого
 * пула нет: на проде 604 профиля, из них 600 синтетических сидов и 4 тестовых. Пулы обоих контуров
 * одинаковы по природе, так что защищать было нечего.
 *
 * ЧТО ЭТО ЗНАЧИТ ТЕПЕРЬ: каждая регистрация с телефона идёт в прод-стор. Стенд (71xx) остался жив
 * и работает, но приложение с ним больше не разговаривает. Вернуться на него — переменной
 * EXPO_PUBLIC_API, не правкой этого файла:
 *
 *   EXPO_PUBLIC_API=https://<адрес-стенда> npx expo start
 *
 * Адрес ПОСТОЯННЫЙ. До 13 августа здесь стоял бесплатный trycloudflare, который Cloudflare
 * удаляет у себя через несколько часов: за один день адрес менялся дважды, и каждый раз это
 * выглядело как «приложение сломалось» — при живых процессах и целом коде.
 *
 * Теперь бэкенд живёт на своём сервере с доменом, и эта строка перестала быть расходником.
 * Модель осталась на поде: сервер ходит к ней по закрытому каналу, наружу она не смотрит.
 */

const DEFAULT_BASE = 'https://aiopenware.com';

/**
 * ТОКЕН СЕССИИ.
 *
 * Живёт здесь, а не в состоянии экрана: его должен подставлять КАЖДЫЙ запрос, а состояние знают
 * только экраны. Значение приходит из памяти телефона при запуске (см. restore в src/state.ts) и
 * меняется ровно в двух местах — вход и выход.
 *
 * В заголовке, а не в теле и не в строке запроса: в теле он оседает в логах прокси, в строке —
 * ещё и в referer.
 */
let SESSION = '';

export function setSession(token: string) {
  SESSION = String(token || '');
}

export function getSession(): string {
  return SESSION;
}

export const API_BASE: string =
  (process.env.EXPO_PUBLIC_API && String(process.env.EXPO_PUBLIC_API)) || DEFAULT_BASE;

/** Кружок. Расшифровки нет — подпись в списке ставит сервер, чтобы под именем не было пустоты. */
export type VideoPayload = {
  id: string;
  url: string;
  duration_ms: number;
  mime_type?: string;
};

export type VoicePayload = {
  id: string;
  url: string;
  duration_ms: number;
  transcript: string;
  mime_type: string;
  language?: string;
};

/**
 * Дописать базу к ОТНОСИТЕЛЬНОМУ пути картинки — и не тронуть всё остальное.
 *
 * Список пропуска был перечнем знакомых схем: http(s), file:, blob:. Всё прочее считалось
 * относительным путём. А своё фото в приложении — это `data:image/jpeg;base64,…` (его делает
 * `squarePhoto` в src/photo.ts), и оно получало базу спереди:
 *
 *     https://…trycloudflare.comdata:image/jpeg;base64,…
 *
 * Такой адрес не разбирается как URL. React Native падает на нём КРАСНЫМ ЭКРАНОМ «URI parsing
 * error» в нативном слое (`ImageManager::requestImage`), а не просто не грузит картинку — снято
 * на симуляторе 12 августа. Заодно этим же объясняется «аватарки в профиле нет»: там всегда
 * своё фото, то есть всегда data-URL.
 *
 * Поэтому проверка теперь не «знаю ли я эту схему», а «есть ли схема вообще»: абсолютный адрес
 * пропускается любой. Пустая строка остаётся пустой — иначе `<Image>` просил бы у сервера
 * главную страницу вместо картинки.
 */
export const mediaUrl = (url: string) =>
  !url || /^[a-z][a-z0-9+.-]*:/i.test(url) ? url : API_BASE + url;

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

async function request<T = Json>(
  path: string,
  init?: RequestInit,
  timeoutMs = 30000,
  /** Отмена снаружи: экран поиска даёт человеку выйти, не дожидаясь срока. */
  external?: AbortSignal,
): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const relay = () => ctrl.abort();
  if (external) {
    if (external.aborted) ctrl.abort();
    else external.addEventListener('abort', relay);
  }
  try {
    const res = await fetch(API_BASE + path, {
      ...init,
      signal: ctrl.signal,
      // Токен подставляется ЗДЕСЬ, в одном месте на все запросы. Разложить его по вызывающим
      // значило бы гарантированно забыть в паре из полусотни.
      headers: {
        'Content-Type': 'application/json',
        ...(SESSION ? { Authorization: `Bearer ${SESSION}` } : {}),
        ...(init?.headers || {}),
      },
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

async function multipart<T = Json>(path: string, body: FormData, headers: Record<string, string> = {}): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), LLM_TIMEOUT_MS);
  try {
    const res = await fetch(API_BASE + path, { method: 'POST', body, headers, signal: ctrl.signal });
    const text = await res.text();
    let payload: any = null;
    try { payload = text ? JSON.parse(text) : null; } catch { payload = text; }
    if (!res.ok) throw new ApiError('HTTP ' + res.status, res.status, payload);
    return payload as T;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Тридцати секунд хватает всему, кроме разговора с моделью: 70B под нагрузкой отвечает и минуту,
 * а обрыв по таймауту человек читает как «связь пропала» и упирается в тупик. Поэтому у вызовов,
 * за которыми стоит генерация, свой срок — он не делает приложение медленнее, он лишь не сдаётся
 * раньше самой модели.
 */
const LLM_TIMEOUT_MS = 120000;

/**
 * За моделью стоят только эти три. `agent/match` и `agent/expand` — НЕ они.
 *
 * Раньше ранжирование лежало в этом же списке и ждало две минуты. А это детерминированный подбор:
 * замерено на живом стенде — match 1.0–1.8 с, expand 1.5 с, и так же из самого приложения. То есть
 * запрос, который в норме занимает полторы секунды, при любой заминке держал экран поиска
 * ДВЕ МИНУТЫ — без отмены и без единого слова о том, что что-то идёт не так. Снаружи это
 * неотличимо от «ищет бесконечно», и именно так это и было названо.
 *
 * Двадцать пять секунд — с запасом в пятнадцать раз к измеренному, и всё равно в пределах
 * человеческого терпения.
 */
const RANK_TIMEOUT_MS = 25000;
const LLM_PATHS = /\/api\/(buddy|onboarding\/chat|agent\/plan)/;
const RANK_PATHS = /\/api\/agent\/(match|expand)/;

const timeoutFor = (path: string) =>
  LLM_PATHS.test(path) ? LLM_TIMEOUT_MS : RANK_PATHS.test(path) ? RANK_TIMEOUT_MS : undefined;

/**
 * ЧТЕНИЕ ОТВЕТА ПО МЕРЕ ПОЯВЛЕНИЯ (SSE).
 *
 * Измерено на живом сервере: сама модель и канал быстрые — тривиальный вызов 0,27 с. Всё время
 * съедает ГЕНЕРАЦИЯ: ответ в 1537 символов пишется 15,5 с, потому что токены выходят по одному.
 * Сократить это нельзя — можно только перестать ждать конца. С потоком первые слова появляются
 * через полторы секунды вместо пятнадцати, и это разница между «приложение думает» и «приложение
 * отвечает».
 *
 * Почему XMLHttpRequest, а не fetch. В React Native у fetch нет потокового тела: `response.body`
 * либо отсутствует, либо приходит целиком по завершении — то есть fetch отдал бы ровно то же
 * ожидание, только сложнее. У XHR есть `onprogress`, где `responseText` растёт по мере прихода;
 * это штатный способ читать SSE в RN.
 *
 * Разбор простой намеренно: сервер шлёт только «event: имя\ndata: {json}\n\n». Хвост, не
 * оканчивающийся пустой строкой, остаётся в буфере до следующего куска — иначе половина события
 * разобралась бы как целое и потерялась.
 */
export function sse(
  path: string,
  body: Json,
  on: { delta?: (t: string) => void; done?: (o: any) => void; error?: (e: string) => void },
): () => void {
  const xhr = new XMLHttpRequest();
  let seen = 0;
  let buf = '';
  let finished = false;

  const flush = () => {
    let cut: number;
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      let event = 'message';
      let data = '';
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (!data) continue;
      let obj: any;
      try { obj = JSON.parse(data); } catch { continue; }
      if (event === 'delta' && obj?.t) on.delta?.(String(obj.t));
      else if (event === 'done') { finished = true; on.done?.(obj); }
      else if (event === 'error') { finished = true; on.error?.(String(obj?.error || 'stream failed')); }
    }
  };

  xhr.open('POST', API_BASE + path);
  xhr.setRequestHeader('Content-Type', 'application/json');
  // Без этого заголовка посредники (и прокси мобильного оператора в том числе) охотно буферизуют
  // ответ целиком, и поток перестаёт быть потоком — а на телефоне это выглядело как обрыв связи.
  xhr.setRequestHeader('Accept', 'text/event-stream');
  xhr.setRequestHeader('Cache-Control', 'no-cache');
  xhr.onprogress = () => {
    const t = xhr.responseText || '';
    buf += t.slice(seen);
    seen = t.length;
    flush();
  };
  xhr.onload = () => {
    const t = xhr.responseText || '';
    buf += t.slice(seen);
    seen = t.length;
    flush();
    // Поток закончился, а «done» не пришло — это обрыв, а не ответ. Молчать нельзя: экран
    // остался бы с половиной фразы и вечным индикатором.
    if (!finished) on.error?.('stream ended without done');
  };
  xhr.onerror = () => { if (!finished) on.error?.('network'); };
  xhr.ontimeout = () => { if (!finished) on.error?.('timeout'); };
  xhr.timeout = 200000;
  xhr.send(JSON.stringify(body));

  return () => { try { xhr.abort(); } catch { /* уже закрыт */ } };
}

export const api = {
  get: <T = Json>(path: string, signal?: AbortSignal) =>
    request<T>(path, undefined, timeoutFor(path), signal),
  post: <T = Json>(path: string, body: Json, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }, timeoutFor(path), signal),
};

/**
 * Кружки. Ручка СВОЯ, а не голосовая: у видео нет расшифровки, нет распознавания и другой предел
 * размера — вешать его на `/api/speech/*` значило бы называть видео речью.
 */
export const video = {
  upload: (body: FormData, durationMs: number) =>
    multipart<{ ok?: boolean; error?: string } & VideoPayload>(
      '/api/agent/video', body, { 'X-Video-Duration-Ms': String(Math.round(durationMs)) }
    ),
};

export const speech = {
  transcribe: (body: FormData) => multipart<{ ok?: boolean; text?: string; language?: string }>(
    '/api/speech/transcribe', body
  ),
  uploadVoice: (body: FormData, durationMs: number) => multipart<VoicePayload & { ok?: boolean; text?: string }>(
    '/api/speech/voice', body, { 'X-Voice-Duration-Ms': String(Math.round(durationMs)) }
  ),
};

/** Отменённый людьми запрос — не ошибка связи, и говорить о нём как об ошибке нельзя. */
export function isAbort(e: unknown): boolean {
  const name = (e as any)?.name;
  return name === 'AbortError' || String((e as any)?.message || '').includes('Aborted');
}

// ---------------------------------------------------------------- онбординг

export type SignupResult = { ok?: boolean; error?: string; login?: string };

export const auth = {
  /**
   * A.03.1 «Continue» — просим код. Ответ одинаков для знакомого и незнакомого адреса.
   *
   * `dev_code` приходит ТОЛЬКО при включённом на сервере KLEAL_SHOW_CODE и существует, пока
   * почтовый домен не подтверждён у провайдера: без него нельзя завести второй аккаунт для
   * проверки, потому что писать он разрешает на один-единственный адрес.
   */
  requestCode: (email: string, lang: string) =>
    api.post<{ ok?: boolean; error?: string; resend_in?: number; sent?: boolean;
               dev_code?: string; mail_error?: string }>(
      '/api/auth/code/request', { email, lang }
    ),

  /** A.03.2 «Verify». Отказ приходит с причиной: wrong (со счётчиком попыток) или expired. */
  verifyCode: (email: string, code: string, lang: string) =>
    api.post<{
      ok?: boolean; error?: string; attempts_left?: number;
      token?: string; login?: string; email?: string; name?: string;
      profile?: Json | null; isNew?: boolean; hasProfile?: boolean;
    }>('/api/auth/code/verify', { email, code, lang }),

  /** «Кто я» по токену: сессия могла истечь или быть погашена с другого устройства. */
  session: () =>
    api.post<{ ok?: boolean; login?: string; email?: string; name?: string;
               profile?: Json | null; hasProfile?: boolean }>('/api/auth/session', {}),

  signOut: () => api.post<{ ok?: boolean }>('/api/auth/signout', {}),
};

export const onboarding = {
  /** Создать логин. Пароль уходит один раз и на сервере лежит только PBKDF2-хеш. */
  signup: (login: string, password: string, name = '') =>
    api.post<SignupResult>('/api/onboarding/signup', { login, password, name }),

  signin: (login: string, password: string) =>
    api.post<SignupResult>('/api/onboarding/signin', { login, password }),

  /**
   * Привязать собранный профиль к аккаунту, чтобы следующий вход вёл в приложение, а не сюда же.
   *
   * Личность сервер берёт ИЗ СЕССИИ — `login` остаётся только ради старых сборок на телефонах,
   * которые про сессии не знают. Раньше привязка шла только по логину, а его выставлял
   * единственный экран «Логин и пароль»: всякий, кто входил иначе, доходил до конца анкеты с
   * login = null, и профиль оставался лежать только на телефоне.
   */
  attach: (login: string, name: string, profile: Json) =>
    api.post('/api/onboarding/attach', { login, name, profile }),

  /**
   * Записать собранный профиль. Это единственный писатель users.json — намеренно: пока запись
   * идёт одним путём, профиль не может разойтись сам с собой.
   */
  register: (profile: Json) => api.post('/api/onboarding/register', { profile }),

  /** Текст сводки от агента по собранному профилю. Язык обязателен: без него сервер молча
   *  писал по-русски, и человек с английской системой читал рассказ о себе не на своём языке. */
  summary: (profile: Json, lang: string) => api.post('/api/onboarding/summary', { profile, lang }),

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
  /**
   * Что человек ДЕЛАЕТ — вычитанное из его истории жизни.
   *
   * Возвращает ПРЕДЛОЖЕНИЕ, а не правку: интересы, проставленные за человека, это ярлыки,
   * которых он не выбирал, и найдут его по ним не те люди. У каждого пункта есть цитата из
   * истории — иначе предложение нечем проверить.
   */
  storyInterests: (story: string, have: string[], lang: string) =>
    api.post<{ interests?: { key: string; label: string; why: string }[] }>(
      '/api/buddy/story-interests', { story, have, lang }
    ),

  resummary: (prof: Json, current: string, personality = '', lang = 'ru') =>
    api.post<{ summary?: string }>('/api/buddy/resummary', { profile: prof, current, personality, lang }),

  /** Итог теста личности: один вызов на все восемь ответов. */
  persona: (payload: Json) => api.post<Json>('/api/buddy/persona', payload),

  /**
   * Разговор с Бадди — просто общение. Интент отсюда НЕ создаётся: сервер лишь сообщает, что
   * распознал в сказанном план (поле `intent`), а решение принимает человек во всплывающем окне.
   */
  /**
   * Тот же чат, но ответ приходит по мере написания.
   *
   * Измерено: первые буквы через 1,9 с вместо 7,5 — и это не ускорение модели, а отказ ждать её
   * конца. Полный ответ по-прежнему пишется 15 секунд; разница в том, что человек их не сидит
   * перед пустым экраном.
   *
   * `done` несёт весь разбор — signals, match, кандидатов: он существует только когда конверт
   * дочитан целиком. Экран показывает текст по дороге, а ветвится по `done`.
   */
  chatStream: (messages: Json[], prof: Json,
               on: { delta?: (t: string) => void; done?: (o: any) => void; error?: (e: string) => void },
               signals: Json = {}) =>
    sse('/api/buddy/chat', { messages, profile: prof, signals, stream: true }, on),

  chat: (messages: Json[], prof: Json, signals: Json = {}) =>
    api.post<{ reply?: string; intent?: Json | null; signals?: Json; lang?: string }>(
      '/api/buddy/chat', { messages, profile: prof, signals }
    ),

  /**
   * Построитель интента: уточняет ТЕМУ и ничего больше. Время, место, пол и размер компании он не
   * спрашивает намеренно — их человек ставит руками на следующих экранах, и переспрашивать
   * значило бы заставить отвечать дважды. Это правило живёт в системном промпте сервера.
   */
  /**
   * Сборка интента, но ответ приходит по мере написания. Измерено: обычный путь 5,2 с — это
   * дольше, чем разговор с Бадди, потому что построитель ещё и разбирает сказанное.
   *
   * `done` несёт весь разбор — ready, topics, подсказки: он существует только когда конверт
   * дочитан целиком. Экран показывает текст по дороге, а ветвится по `done`.
   */
  intentBuildStream: (messages: Json[], prof: Json,
                      on: { delta?: (t: string) => void; done?: (o: any) => void; error?: (e: string) => void }) =>
    sse('/api/buddy/intent-build', { messages, profile: prof, stream: true }, on),

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
  plan: (query: string, profile: Json, ctx: Json = {}, override?: Json, signal?: AbortSignal) =>
    api.post('/api/agent/plan', { query, profile, ctx, override }, signal),

  /** Уже собранный интент → кандидаты, без разбора текста. */
  /** `signal` — чтобы экран поиска мог отменить запрос по кнопке, а не ждать срока. */
  /**
   * `limit` — сколько человек показать. Без него сервер отвечает как всегда: первой восьмёркой.
   *
   * Восемь — это ПЕРВАЯ страница, а не весь ответ. С `limit` сервер отдаёт продолжение того же
   * ранжирования (девятый после восьмого) и в `has_more` говорит, осталось ли что показывать —
   * без этого кнопка «показать ещё» жила бы вечно и однажды снова нажималась бы впустую.
   */
  match: (intent: Json, profile: Json, ctx: Json = {}, signal?: AbortSignal, limit?: number) =>
    api.post('/api/agent/match', limit ? { intent, profile, ctx, limit } : { intent, profile, ctx }, signal),

  /**
   * §12 лестница расширения: на шаг шире по ОДНОЙ оси, а не «показать всех».
   *
   * axis обязателен по смыслу, хотя сервер и обходится без него: без параметра он молча берёт
   * первую ось, и второе нажатие «Расширить поиск» возвращает ту же выдачу. Ступень выбирает
   * клиент — он один знает, что уже пробовали.
   */
  expand: (intent: Json, profile: Json, axis: string, ctx: Json = {}) =>
    api.post('/api/agent/expand', { intent, profile, axis, ctx }),

  /**
   * МОИ ИНТЕНТЫ — то, из чего состоит вкладка «Моя активность» (борд C.02).
   *
   * Ручки на сервере были всё это время, а звал их из приложения НИКТО: интент жил ровно столько,
   * сколько открыт мастер, уходил в матчинг и нигде не оставался. Поэтому списку своих затей было
   * неоткуда взяться — он пуст не потому, что человек ничего не завёл, а потому, что заводить
   * было некуда.
   *
   * `live` не передаём: по умолчанию сервер пересчитывает кандидатов на каждый запрос, и «3
   * варианта готовы» на карточке означает состояние СЕЙЧАС, а не слепок на момент создания.
   */
  intents: (self: string, prof: Json) =>
    api.post<{ intents?: Json[] }>('/api/agent/intents', { self, profile: prof }),

  /**
   * Сохранить или обновить. Без `id` сервер сам склеит повтор по теме и роли — одна и та же
   * затея, заведённая дважды, не должна лечь двумя карточками.
   *
   * `launched` — «поиск по этому интенту уже запускали». Обратно в «ещё не искали» он не
   * отыгрывается, и это правило сервера, а не экрана.
   */
  intentSave: (self: string, intent: Json, title: string, id?: string, launched = false) =>
    api.post<{ ok?: boolean; id?: string; merged?: boolean; error?: string }>(
      '/api/agent/intent-save', { self, intent, title, id, launched }
    ),

  intentDelete: (self: string, id: string) =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/intent-delete', { self, id }),

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
  report: (self: string, name: string, reason: string, text = '', idem?: string,
           messageId?: string, threadType?: string, threadId?: string) =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/report', {
      self, name, reason, text, idem, message_id: messageId,
      thread_type: threadType, thread_id: threadId,
    }),

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
  /**
   * `clientId` — ключ отправителя, и он делает две вещи сразу.
   *
   * Повтор. Сервер идемпотентен по нему: нажать «отправить ещё раз» после неясного сбоя
   * (сообщение записалось, а ответ не доехал) безопасно — вернётся тот же ответ, а не вторая
   * реплика у собеседника.
   *
   * Узнавание. Свой пузырь показывается сразу, до ответа сервера, и опрос приносит его же
   * обратно. Раньше экран узнавал его по ТЕКСТУ — а у голосового локальный текст пустой, тогда
   * как сервер кладёт туда расшифровку, и голосовое двоилось в ленте. По ключу узнаётся любое.
   */
  message: (from: string, to: string, text: string, voice?: VoicePayload, clientId?: string,
            replyTo?: string, video?: VideoPayload) =>
    api.post<{ ok?: boolean; error?: string; id?: string; t?: number; cid?: string }>(
      '/api/agent/message',
      { from, to, text, voice, client_id: clientId, reply_to: replyTo, video }),

  /** Реакция переключается: то же нажатие второй раз её снимает. Набор закрыт — см. REACTIONS. */
  react: (self: string, id: string, emoji: string) =>
    api.post<{ ok?: boolean; error?: string; r?: Record<string, string[]> }>(
      '/api/agent/message-react', { self, id, emoji }),

  /** Удаление мягкое: строка остаётся и говорит о себе «удалено». Жёсткое второму не доедет. */
  deleteMessage: (self: string, id: string) =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/message-delete', { self, id }),

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

  /**
   * Место встречи И ссылка на звонок — ДВА РАЗНЫХ поля, а не одно по очереди.
   *
   * Раньше ручка была одна на оба, и у ГИБРИДА второй вход молча пропадал: экран отправлял
   * «ссылка, а если её нет — место». Борд HY.20a/20b/20c держится ровно на том, что входа два и
   * заполняются они независимо: без ссылки не войдёт половина, без места второй половине некуда
   * идти. Групповой план так умел давно (`gplan-link`), одиночный — нет.
   *
   * Оба открываются только подтвердившим (OF.C3). venue — человеческое имя места («Nømad»),
   * address — куда идти.
   */
  planAddress: (id: string, self: string, address: string, venue?: string, link?: string) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/mplan-address', { id, self, address, venue, link }
    ),

  /**
   * HY.22 — с какой стороны придёшь: за столик или в звонок. Только у гибрида.
   *
   * Это НЕ отмена и не статус. Кадр HY.23b говорит прямым текстом: отмена заканчивает встречу для
   * обоих, а смена стороны её не трогает — человек просто входит другим входом. И это обратимо:
   * на HY.22a стоит «Go in person after all».
   *
   * Сервер откажет, если стороны, которую выбирают, ещё не существует (нет ссылки или нет места):
   * уйти в звонок, которого нет, значит не прийти вовсе.
   */
  planSide: (id: string, self: string, side: 'in_person' | 'call') =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/mplan-side', { id, self, side }
    ),

  /**
   * HY.23c — «место закрыто, уходим в звонок»: перевести ОБОИХ, а не только себя.
   *
   * По одному переводить нельзя: пока второй не догадается сделать то же, он ждёт у той же
   * закрытой двери или сидит в звонке один. И это не отмена — у гибрида ссылка уже открыта, в том
   * и разница со встречей вживую.
   */
  planMoveToCall: (id: string, self: string) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/mplan-move-to-call', { id, self }
    ),

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
  /** `with` — собеседник, ради его часового пояса: на форме плана самого плана ещё нет. */
  plans: (self: string, withWhom?: string) =>
    api.get<{ plans?: Json[]; history?: Json[]; peer_tz?: string }>(
      `/api/agent/mplans?self=${encodeURIComponent(self)}` +
      (withWhom ? `&with=${encodeURIComponent(withWhom)}` : '')
    ),

  /** Входящие приглашения. Просроченные и отозванные сервер отсекает сам. */
  inbox: (self: string) =>
    api.get<{ requests?: Json[] }>(`/api/agent/inbox?self=${encodeURIComponent(self)}`),

  /** Единая лента входящих 1:1 и групповых приглашений для главного экрана. */
  homeInvites: (self: string) =>
    api.get<{ invites?: Json[] }>(`/api/agent/home-invites?self=${encodeURIComponent(self)}`),

  /** Ответ получателя на приглашение (O.C1). Сервер пере-проверяет политику на момент ответа:
   *  между отправкой и согласием человек мог заблокировать или закрыть направление. */
  respondInvite: (id: string, self: string, decision: 'accept' | 'decline', version?: number) =>
    api.post<{ ok?: boolean; error?: string; status?: string }>(
      '/api/agent/respond', { id, self, decision, version }
    ),

  /** «Я открыл эту переписку» — из этой отметки у второй стороны получаются двойные галочки
   *  (MSG.11). Отметка одна на пару, по-сообщенного статуса нет намеренно. */
  /** Закрыть переписку так, чтобы об этом узнал второй: сервер пишет строку в общую ленту. */
  threadEnd: (self: string, other: string) =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/thread-end', { self, with: other }),

  threadRead: (self: string, other: string) =>
    api.post<{ ok?: boolean }>('/api/agent/thread-read', { self, with: other }),
};

// ---------------------------------------------------------------- группы

/**
 * Групповые интенты и групповые планы. Бекенд готов целиком и покрыт смоуками
 * (kleal-ms/tools/gintents_smoke.py, gplans_smoke.py) — формы ниже списаны с них и с раздатчика
 * маршрутов, не придуманы.
 *
 * Правила, которые НЕЛЬЗЯ перепутать с 1:1 — они противоположные, и это решения борда:
 *  — встречное предложение по групповому плану РВЁТ утверждение (версия++, подтверждения в ноль);
 *    в 1:1 оно паркуется рядом и старое время держится (OF.21a);
 *  — подтверждают ВСЕ (GR.26 «Waiting for everyone»); молчащего ждут, а не выбрасывают;
 *  — раундов согласования три (GR.28/29), дальше план закрепляет организатор (GR.30);
 *  — голосование СОВЕЩАТЕЛЬНОЕ (GR.35/38): группа считает голоса, решает организатор;
 *  — за два часа до встречи всё замирает (LOCKED): ни подтвердить, ни отменить, ни позвать.
 *
 * `idem` на каждом изменяющем вызове: сервер идемпотентен по ключу, и повтор того же нажатия
 * (двойной тап, ретрай после обрыва) не создаёт второй группы и не шлёт второе приглашение.
 * Ключ делает ЭКРАН на само действие (см. newIdem) — один на нажатие, не на запрос.
 */

/** Ключ идемпотентности: один на человеческое действие. Дата+случайность, без библиотек. */
export function newIdem(tag: string): string {
  return `${tag}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export type GroupInfo = {
  gid?: string;
  title?: string;
  joined_count?: number;
  min_total?: number;
  max_total?: number;
  /** Скольких не хватает до минимума. 0 — можно планировать. */
  need_more?: number;
  planning_allowed?: boolean;
  can_remove?: boolean;
  can_end?: boolean;
  read_only?: boolean;
  read_only_reason?: string;
  removed_at?: number;
  removal_notice?: { code?: string; title?: string; other_intents_affected?: boolean };
  closure_notice?: { code?: string; title?: string; owner?: string; closed_at?: number; other_intents_affected?: boolean };
  [k: string]: any;
};

export type GroupRemovalReason =
  | 'inappropriate_messages_or_photos'
  | 'suspected_fake_or_stolen_profile'
  | 'not_responding'
  | 'doesnt_fit_meetup'
  | 'something_else';

export type GroupReportReason =
  | 'inappropriate_behaviour'
  | 'insults_or_humiliation'
  | 'harassment_or_threats'
  | 'fake_profile'
  | 'rule_violation';

export type ReportEvidence = {
  id: string;
  url: string;
  name: string;
  mime_type: string;
  size: number;
};

export type GroupReportResult = {
  ok?: boolean;
  error?: string;
  id?: string;
  case_no?: string;
  status?: string;
  at?: number;
  protective_measures?: string[];
  group?: GroupInfo;
};

export const group = {
  // ---- слой 1: комната -------------------------------------------------

  /** Создать групповой интент. Создатель сразу участник; min 3 — правило продукта, не поле формы. */
  create: (self: string, title: string, intent: Json, idem: string, opts: Json = {}) =>
    api.post<{ ok?: boolean; error?: string; group?: GroupInfo }>(
      '/api/agent/gintent-create', { self, title, intent, idem, ...opts }
    ),

  /**
   * Пригласить. `to` — имя ИЛИ список: организатор зовёт всю выдачу одним вызовом и получает
   * ответ ПО КАЖДОМУ (sent/refused с причинами), а не один вердикт на батч. Места приглашение
   * не резервирует — на последнее место может быть два живых приглашения, это по спеке (§20).
   */
  invite: (gid: string, self: string, to: string | string[], idem: string, note = '') =>
    api.post<{
      ok?: boolean; error?: string;
      invite?: Json;                       // одиночное приглашение
      sent?: Json[]; refused?: Json[];     // батч
    }>('/api/agent/gintent-invite', { gid, self, to, note, idem }),

  /** Отозвать ОТКРЫТОЕ приглашение — Cancel со строки GR.17 и выход из капа по GR.15. Только
   *  организатор, только неотвеченное: по принятому человек уже участник, по ожидающему апрува
   *  решает approve(accept=false). Приглашённому — тишина; попытка войти ответит WITHDRAWN. */
  inviteCancel: (id: string, self: string, idem: string) =>
    api.post<{ ok?: boolean; error?: string; invite?: Json; group?: GroupInfo }>(
      '/api/agent/gintent-invite-cancel', { id, self, idem }
    ),

  /** Ответ на групповое приглашение. Принял — сразу в общем чате; на этапе плана вместо этого
   *  приходит `awaiting_approval: true`, и человека впускает организатор. */
  respondInvite: (id: string, self: string, accept: boolean, idem: string) =>
    api.post<{ ok?: boolean; error?: string; group?: GroupInfo; awaiting_approval?: boolean }>(
      '/api/agent/ginvite-respond', { id, self, accept, idem }
    ),

  /** Recipient-scoped group invitation detail. Supports notification links that only carry id. */
  inviteDetail: (id: string, self: string) =>
    api.get<{ ok?: boolean; error?: string; invite?: Json; group?: GroupInfo }>(
      `/api/agent/ginvite?id=${encodeURIComponent(id)}&self=${encodeURIComponent(self)}`
    ),

  /** Апрув ожидающего (этап плана). Только организатор; accept: false — отказать во входе. */
  approve: (gid: string, self: string, who: string, idem: string, accept = true) =>
    api.post<{ ok?: boolean; error?: string; group?: GroupInfo }>(
      '/api/agent/gintent-approve', { gid, self, who, accept, idem }
    ),

  /** GR.51: удалить участника с одной причиной из закрытого списка. Произвольного текста нет. */
  remove: (gid: string, self: string, who: string, reasonCode: GroupRemovalReason, idem: string) =>
    api.post<{ ok?: boolean; error?: string; group?: GroupInfo }>(
      '/api/agent/gintent-remove', { gid, self, who, reason_code: reasonCode, idem }
    ),

  /** S10 / GR.53-55: organiser closes the group before a plan is set. */
  close: (gid: string, self: string, idem: string) =>
    api.post<{ ok?: boolean; error?: string; group?: GroupInfo }>(
      '/api/agent/gintent-close', { gid, self, idem }
    ),

  /** Выйти самому. Ниже минимума «Создать план» у оставшихся гаснет. */
  leave: (gid: string, self: string, idem: string) =>
    api.post<{ ok?: boolean; error?: string; group?: GroupInfo }>(
      '/api/agent/gintent-leave', { gid, self, idem }
    ),

  /** S11: optional evidence is uploaded first; the case itself remains a JSON action. */
  uploadReportEvidence: (body: FormData) =>
    multipart<{ ok?: boolean; error?: string } & Partial<ReportEvidence>>(
      '/api/agent/report-evidence', body
    ),

  report: (gid: string, self: string, reason: GroupReportReason, text: string,
           evidence: ReportEvidence[], idem: string) =>
    api.post<GroupReportResult>('/api/agent/gintent-report', {
      gid, self, reason, text, evidence, idem,
    }),

  /**
   * GR.19 — организатор ПРОСИТ второго перевести группу в один на один. Именно просит: группа
   * принадлежит обоим, и закрыть её единолично значит отнять у второго то, на что он согласился.
   */
  convertAsk: (gid: string, self: string, idem: string) =>
    api.post<{ ok?: boolean; error?: string; asked?: string; group?: GroupInfo }>(
      '/api/agent/gintent-convert', { gid, self, idem }
    ),

  /** GR.20 — ответ той стороны. Согласие закрывает группу и гасит её открытые приглашения. */
  convertRespond: (gid: string, self: string, agree: boolean, idem: string) =>
    api.post<{ ok?: boolean; error?: string; agreed?: boolean; group?: GroupInfo }>(
      '/api/agent/gintent-convert-respond', { gid, self, agree, idem }
    ),

  /** Сообщение в общий чат группы. */
  post: (gid: string, self: string, text: string, voice?: VoicePayload, clientId?: string,
         replyTo?: string, video?: VideoPayload) =>
    api.post<{ ok?: boolean; error?: string; message?: Json }>(
      '/api/agent/gintent-post',
      { gid, self, text, voice, client_id: clientId, reply_to: replyTo, video }),

  /** Реакция в комнате. Право — членство: кто в группе, тот и реагирует. */
  react: (gid: string, self: string, id: string, emoji: string) =>
    api.post<{ ok?: boolean; error?: string; r?: Record<string, string[]> }>(
      '/api/agent/gmsg-react', { gid, self, id, emoji }),

  deleteMessage: (gid: string, self: string, id: string) =>
    api.post<{ ok?: boolean; error?: string }>('/api/agent/gmsg-delete', { gid, self, id }),

  /** Чат группы, старые сверху. Активным — живая лента; удалённому — неизменяемая история до
   *  удаления с `read_only`. Постороннему по-прежнему NOT_A_MEMBER. */
  thread: (gid: string, self: string, since = 0) =>
    api.get<{ ok?: boolean; error?: string; group?: GroupInfo; messages?: Json[] }>(
      `/api/agent/gintent-thread?gid=${encodeURIComponent(gid)}&self=${encodeURIComponent(self)}&since=${since}`
    ),

  /** Одна группа целиком — состав, need_more, planning_allowed, ожидающие апрува. */
  get: (gid: string, self: string) =>
    api.get<{ ok?: boolean; group?: GroupInfo }>(
      `/api/agent/gintent?gid=${encodeURIComponent(gid)}&self=${encodeURIComponent(self)}`
    ),

  /** Мои группы и входящие групповые приглашения — для «Сообщений» и главной. */
  mine: (self: string) =>
    api.get<{ groups?: Json[]; invites?: Json[] }>(
      `/api/agent/gintents?self=${encodeURIComponent(self)}`
    ),

  // ---- слой 2: план ----------------------------------------------------

  /**
   * Предложить план. Только организатор и только при трёх в комнате (NEED_THREE). Предложивший
   * считается подтвердившим. Внутри двух часов до встречи план не заводится (TOO_LATE).
   * `starts_at` — unix-секунды точного начала: по нему сервер считает двухчасовой замок.
   */
  planBegin: (gid: string, self: string, p: { when: string; place?: string; link?: string; note?: string; starts_at?: number }, idem: string) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/gplan-begin', { gid, self, ...p, idem }
    ),

  /**
   * Ответ на план: confirm | counter. ГРУППОВОЕ правило: counter обнуляет прежние подтверждения
   * (согласие было на другой вечер), поднимает раунд и версию, план снова «на утверждении».
   * Раундов три (GR.28/29) — четвёртый вернёт ROUNDS_USED_UP. Подтвердили все — план встал сам.
   *
   * Тот же confirm служит ещё двум кнопкам борда, и это не совпадение, а одно и то же действие:
   * «Stay in the plan» (GR.31, после закрепления) и «Accept the change» (GR.33, после правки
   * организатора) — это «да, я в этом плане», сказанное в другой момент.
   */
  planRespond: (id: string, self: string, action: 'confirm' | 'counter', idem: string, extra: Json = {}) =>
    api.post<{ ok?: boolean; error?: string; countered?: boolean; plan?: Json }>(
      '/api/agent/gplan-respond', { id, self, action, idem, ...extra }
    ),

  /**
   * GR.40 «Cancel the plan» — организатор закрывает план, вставший на паузу.
   *
   * Появилась потому, что выхода из «ниже трёх» не было ВООБЩЕ: закрыть план можно было только
   * голосованием, а оно требует утверждённого плана — то есть ровно того состояния, из которого
   * план и выпал. Он висел вечно. Группа при этом остаётся: люди никуда не делись.
   */
  /** GR.45a: «уже иду» / «опаздываю» / «я на месте». Видит вся группа, а не один человек. */
  planStatus: (id: string, self: string, status: 'otw' | 'late' | 'here', idem: string, etaMin?: number) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/gplan-status', { id, self, status, idem, eta_min: etaMin }
    ),

  planCancel: (id: string, self: string, idem: string) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/gplan-cancel', { id, self, idem }
    ),

  /** GR.30 «Fix the plan» — организатор закрывает согласование, когда раунды кончились. Не
   *  выбрасывает молчавших: им предлагается остаться или выйти (GR.31, флаг stay_or_leave). */
  planFix: (id: string, self: string, idem: string) =>
    api.post<{ ok?: boolean; error?: string; fixed?: boolean; unconfirmed?: string[]; plan?: Json }>(
      '/api/agent/gplan-fix', { id, self, idem }
    ),

  /** GR/GRO.32 — организатор правит УТВЕРЖДЁННЫЙ план. Каждый участник после этого принимает
   *  заново или выходит (GR.33); встреча при этом не отменяется. */
  planUpdate: (id: string, self: string, p: { when?: string; place?: string; link?: string; starts_at?: number },
               idem: string) =>
    api.post<{ ok?: boolean; error?: string; updated?: boolean; plan?: Json }>(
      '/api/agent/gplan-update', { id, self, ...p, idem }
    ),

  /** GRO.25a / GRH.25a — ссылка на звонок для online/hybrid плана. */
  planLink: (id: string, self: string, link: string, idem: string) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/gplan-link', { id, self, link, idem }
    ),

  /** GRH.25a/25b: дозаполнить один из двух независимых входов гибридной встречи. */
  planDetails: (id: string, self: string, p: { place?: string; link?: string }, idem: string) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/gplan-details', { id, self, ...p, idem }
    ),

  /** GRH: участник выбирает, придет ли лично или подключится к звонку. */
  planSide: (id: string, self: string, side: 'in_person' | 'call', idem: string) =>
    api.post<{ ok?: boolean; error?: string; plan?: Json }>(
      '/api/agent/gplan-side', { id, self, side, idem }
    ),

  /** Открыть голосование: cancel — отменить встречу, edit — перенести (when/place/starts_at).
   *  Одновременно живёт одно (VOTE_IN_PROGRESS); созвавший уже «за». Живёт шесть часов. */
  voteOpen: (id: string, self: string, kind: 'cancel' | 'edit', idem: string, extra: Json = {}) =>
    api.post<{ ok?: boolean; error?: string; vote?: Json }>(
      '/api/agent/gplan-vote-open', { id, self, kind, idem, ...extra }
    ),

  /** Голос. Закрывается само, когда высказались все или вышли шесть часов. Закрытие СЧИТАЕТ
   *  голоса и на этом останавливается: план не меняется, пока организатор не решит (voteDecide). */
  vote: (id: string, self: string, yes: boolean, idem: string) =>
    api.post<{ ok?: boolean; error?: string; vote?: Json }>(
      '/api/agent/gplan-vote', { id, self, yes, idem }
    ),

  /** Закрыть голосование досрочно, не дожидаясь всех. Только организатор. */
  voteClose: (id: string, self: string, idem: string) =>
    api.post<{ ok?: boolean; error?: string; vote?: Json }>(
      '/api/agent/gplan-vote-close', { id, self, idem }
    ),

  /** GR.37 «It’s your call» — организатор решает, что делать с советом группы. apply: false —
   *  оставить план как есть, и это законный исход даже при большинстве за перенос (GR.38). */
  voteDecide: (id: string, self: string, apply: boolean, idem: string) =>
    api.post<{ ok?: boolean; error?: string; vote?: Json }>(
      '/api/agent/gplan-vote-decide', { id, self, apply, idem }
    ),

  /** «Состоялось?» и необязательная оценка — одна дозаписываемая приватная запись участника. */
  planFeedback: (id: string, self: string, v: { happened?: boolean; text?: string; reason?: string; rating?: number }, idem: string) =>
    api.post<{ ok?: boolean; error?: string; answered?: number; of?: number; plan?: Json }>(
      '/api/agent/gplan-feedback', { id, self, ...v, idem }
    ),

  /** Групповые планы этого человека: живые, история и голосования, которые ждут его или
   *  организатора. Закрытое, но нерешённое голосование тоже здесь — это и есть экран GR.37/38. */
  plans: (self: string) =>
    api.get<{ plans?: Json[]; history?: Json[]; votes?: Json[] }>(
      `/api/agent/gplans?self=${encodeURIComponent(self)}`
    ),
};
