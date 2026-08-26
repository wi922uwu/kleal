/**
 * Профиль — перенос с работающей веб-версии (kleal-ms/services/profile/app.py).
 *
 * Борд профиля вычитать не удалось: квота Figma на View-месте исчерпана. Источником взята живая
 * реализация — по прямому решению, после того как это было названо риском.
 *
 * Здесь derive и копия; экраны лежат в app/profile/. Устройство то же, что в вебе: хаб и три
 * раздела — интересы, личность, безопасность.
 *
 * Главное, что переносится не как верстка, а как смысл: profileData() повторяет mapOnboarding() из
 * веба, потому что из неё живут ВСЕ четыре экрана сразу. Пока derive один, карточка «Языки» на
 * хабе и строка «Общается на …» в памяти не могут разойтись между собой.
 */
import { T, getLang, replyLang } from './i18n';
import { sexLabel, hobbyPlain } from './onboarding';
import { langPlainName } from './languages';
import type { Profile } from './state';
import { getState, set, subscribe, profileForAttach } from './state';
import { buddy, profile as profileApi } from './api';
import { patchFor } from './fields';
import { interestLabel, interestLabels } from './interest-label';

// ---------------------------------------------------------------- разделы

export type SectionId = 'interests' | 'personality' | 'safety';

export const PROFILE_TITLE = () => T('Мой профиль Kleal', 'My Kleal Profile');

export const SECTIONS: { id: SectionId; title: () => string; sub: () => string }[] = [
  {
    id: 'interests',
    title: () => T('Интересы', 'Interests'),
    sub: () => T('Чем ты любишь заниматься с людьми', 'What you like doing with people'),
  },
  {
    id: 'personality',
    title: () => T('Твоя личность', 'Your personality'),
    sub: () => T('Как ты воспринимаешься', 'How you come across'),
  },
  {
    id: 'safety',
    title: () => T('Безопасность и приватность', 'Safety & Privacy'),
    sub: () => T('Что Kleal может использовать и твои границы', 'What Kleal can use, and your limits'),
  },
];

export const HUB = {
  confidence: () => T('Наполненность профиля', 'Profile confidence'),
  summaryLabel: () => T('Сводка Kleal', "Kleal's summary"),
  edit: () => T('Изменить', 'Edit'),
  rewrite: () => T('Пересобрать', 'Rewrite'),
  save: () => T('Сохранить', 'Save'),
  cancel: () => T('Отмена', 'Cancel'),
  createIntent: () => T('Создать интент', 'Create intent'),
  lang: () => T('Язык интерфейса', 'Interface language'),
  avail: () => T('Доступность', 'Availability'),
  writing: () => T('Kleal составляет описание…', 'Kleal is writing your summary…'),
  empty: () =>
    T('Kleal опишет тебя здесь по мере знакомства.', 'Kleal will summarise you here as it learns more.'),
};

/**
 * Пересобрать сводку под изменившийся профиль.
 *
 * Сводка проговаривает факты вслух — «живёт в Барселоне», «говорит по-русски и по-английски», — и
 * после правки локации или языков она начинает врать. В вебе это давно так и устроено: правка
 * location / languages / basics / interests тянет за собой adaptSummary(). В переносе этого не
 * было, и человек, сменивший страну на Италию, продолжал читать про Барселону.
 *
 * Две защиты, обе из веба и обе не теоретические:
 *
 *  — Один запрос за раз. Иначе быстрые правки подряд (сменил язык, сразу страну) запускают две
 *    пересборки, и выигрывает та, что вернулась позже, — то есть, возможно, более старая.
 *  — Ответ отвергается, если он подозрительно короче прежнего или совпал с текстом личности.
 *    «Сводка ещё не догнала» — поправимо, «сводку затёрло» — нет.
 *
 * Возвращает true, если текст действительно сменился.
 */
let _resumBusy = false;
/** Кто хочет знать, идёт ли пересборка прямо сейчас: экран профиля рисует этим «обновляю…». */
const _busySubs = new Set<(b: boolean) => void>();
function setBusy(b: boolean) {
  _resumBusy = b;
  _busySubs.forEach((f) => f(b));
}
export function onSummaryBusy(cb: (b: boolean) => void): () => void {
  _busySubs.add(cb);
  cb(_resumBusy);
  return () => { _busySubs.delete(cb); };
}

/**
 * Отправить интересы на сервер, если они разошлись с тем, что уже отправлено.
 *
 * ЗАЧЕМ. Интересы, дописанные ПОСЛЕ онбординга, не доезжали до сервера вовсе. Путь «Профиль →
 * Интересы → Добавить» ведёт в разговор (`/chat?step=hobbies&back=…`), там `/api/onboarding/chat`
 * возвращает профиль клиенту и САМ в стор ничего не пишет, а выход из разговора просто
 * переключает экран. Записывал интересы только тумблер «учитывать при подборе» и удаление.
 *
 * Получалось хуже, чем просто «не сохранилось»: сторож сводки правку замечал и отправлял на сервер
 * СВОДКУ, в которой новое увлечение упомянуто. В строке оставался рассказ про настолки и список
 * интересов без настолок — а ранжирование читает список. Человек видел интерес у себя на экране и
 * был по нему невидим.
 *
 * Отпечаток, а не флаг: канонизация на сервере дёргает фильтрацию по каждому интересу, и слать
 * одно и то же на каждый заход на экран незачем. Первый заход после запуска отправляет всегда —
 * что лежит в строке, приложение не знает, и лишняя сверка дешевле молчаливого расхождения.
 */
let _sentInterests: string | null = null;

export async function pushInterests(): Promise<boolean> {
  const st = getState();
  const name = st.profile.name;
  if (!name || !st.done) return false;          // до регистрации всё уедет одним register()
  try {
    // patchFor внутри try намеренно: он БРОСАЕТ, если поля нет в реестре. Снаружи это стало бы
    // необработанным отказом промиса внутри эффекта фокуса — то есть опять тишиной.
    const patch = patchFor(['interests']);
    const sig = JSON.stringify(patch);
    if (sig === _sentInterests) return false;
    const r: any = await profileApi.update(name, patch);
    if (r && r.ok === false) return false;      // сервер отказал — пробуем на следующем заходе
    _sentInterests = sig;
    return true;
  } catch {
    return false;                                // сеть отвалилась — отпечаток не трогаем
  }
}

/**
 * Подтянуть подписи интересов на языке интерфейса.
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ ВЫЗОВ. Интересы хранятся английскими ключами, а переводы живут в серверном
 * словаре и приезжают рядом с ответом `/api/onboarding/profile`. Вызывать эту ручку было НЕКОМУ:
 * экран профиля берёт строку из состояния устройства, и до сервера за подписями никто не ходил —
 * поэтому в русском интерфейсе среди своих же чипов светились `podcasts` и `dancing`, а рядом
 * стояли «Бег» и «Йога» (те попадали в лесенку из словаря колеса).
 *
 * Отпечаток по набору ключей и языку: перерисовка экрана не должна дёргать сеть, а смена языка —
 * должна, иначе после переключения останутся подписи прошлого языка.
 */
let _labelSig: string | null = null;

export async function syncInterestLabels(): Promise<boolean> {
  const st = getState();
  const name = st.profile.name;
  if (!name) return false;
  const keys = explicitInterests(st.profile);
  if (!keys.length) return false;
  const sig = getLang() + '|' + keys.join('|');
  if (sig === _labelSig) return false;
  try {
    await profileApi.get(name);        // сам сгружает interestLabels в реестр — см. src/api.ts
    _labelSig = sig;
    return true;
  } catch {
    return false;                       // сеть отвалилась — отпечаток не трогаем, попробуем позже
  }
}

export async function adaptSummary(): Promise<boolean> {
  if (_resumBusy) return false;
  setBusy(true);
  try {
    const st = getState();
    // Отпечаток профиля, ПО КОТОРОМУ собираем. Нужен сторожу: без него его отложенный запуск
    // повторял бы то, что экран уже попросил сам (кнопка «Пересобрать» + правка = два ответа
    // модели на одну правку). См. startSummaryWatch.
    const sigNow = summarySignature(st.profile);
    const cur = String((st.profile as any).summary || '');
    const personality = String((st.profile as any).personality || '');
    const r: any = await buddy.resummary(profileForAttach(), cur, personality, replyLang());
    _builtSig = sigNow;           // модель ответила — этот профиль считается разобранным
    const woven = String(r?.summary || '').trim();
    const norm = (x: string) => x.toLowerCase().replace(/\s+/g, ' ').trim();
    if (!woven) return false;
    if (personality && norm(woven) === norm(personality)) return false;
    // Сторож против ОБРЫВКА, а не против укорачивания. Прежний порог — «короче половины
    // старой» — отвергал ровно тот случай, ради которого пересборку и зовут: человек убрал
    // несколько интересов, сводка честно стала короче, и её отбрасывали, оставляя на экране
    // рассказ про увлечения, которых уже нет.
    if (woven.length < 40) return false;

    set('summary', woven);
    set('summaryUpdated', Date.now());
    const name = st.profile.name;
    if (name) await profileApi.update(name, { summary: woven }).catch(() => {});
    return true;
  } catch {
    return false;                 // сеть отвалилась — на экране остаётся прежний текст
  } finally {
    setBusy(false);
  }
}

/**
 * СТОРОЖ СВОДКИ: пересобирает её сам, как только профиль изменился.
 *
 * Раньше каждый экран звал adaptSummary() у себя — три листа на хабе, интересы, тест. Это работает
 * ровно до первого забытого места, и такое место было: история «своими словами» меняла профиль и
 * не трогала сводку вовсе, пока туда не поставили отдельную кнопку. Любой новый экран наследовал
 * бы ту же ловушку.
 *
 * Здесь один вход и одно правило: смотрим не на экраны, а на САМ ПРОФИЛЬ. Считаем отпечаток полей,
 * которые сводка описывает; изменился — пересобираем.
 *
 * Что в отпечаток НЕ входит и почему:
 *  — сама summary: иначе пересборка запускала бы пересборку, и это кольцо;
 *  — фото, безопасность, разрешения, радиус: сводке про них говорить запрещено (SUMMARY_PROMPT),
 *    так что их правка ничего в тексте не меняет и гонять модель незачем;
 *  — пометки «Сообщений» и прочее состояние устройства — они не про человека.
 */
function summarySignature(p: any): string {
  const list = (v: any) => (Array.isArray(v) ? v.map(String).slice().sort().join('|') : '');
  return [
    p?.name, p?.age, p?.gender, p?.city, p?.country,
    list(p?.languages?.comfortable),
    // Через общий помощник: с сервера интересы приходят ПЛОСКИМ списком, и прямое чтение
    // `.explicit` давало здесь пустоту. Отпечаток от этого не менялся при правке интересов —
    // то есть сводка не пересобиралась вовсе и продолжала рассказывать про старые увлечения.
    list(explicitInterests(p)),
    list(p?.interests?.unused),
    p?.personality, p?.story,
  ].map((x) => String(x ?? '')).join('\u0001');
}

let _watching = false;
/** Отпечаток профиля, по которому сводка уже собиралась, кем бы ни был вызван adaptSummary. */
let _builtSig = '';

/**
 * Включается один раз на всё приложение (app/_layout.tsx).
 *
 * Задержка — не косметика: один шаг человека часто пишет несколько полей подряд (тест кладёт и
 * `personality`, и `persona`; лист локации — город, координаты и радиус), и без неё модель
 * дёргалась бы на каждое поле. Полторы секунды тишины — и один запрос на всю правку.
 *
 * Пока онбординг не закончен, сторож молчит: там профиль меняется каждым шагом, а свою сводку
 * анкета пишет сама в самом конце.
 */
export function startSummaryWatch(): void {
  if (_watching) return;
  _watching = true;
  let last = summarySignature(getState().profile);
  let timer: ReturnType<typeof setTimeout> | null = null;

  const run = async () => {
    timer = null;
    // Занято — ждём и приходим снова. Именно ждём, а не «поставим флажок»: пересборку мог
    // запустить экран (кнопка «Пересобрать» на личности), и тогда флажок некому было бы снять.
    if (_resumBusy) { schedule(); return; }
    if (summarySignature(getState().profile) === _builtSig) return;   // экран уже успел сам
    await adaptSummary();
  };
  const schedule = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(run, 1500);
  };

  subscribe((st) => {
    if (!st.done) { last = summarySignature(st.profile); return; }
    const sig = summarySignature(st.profile);
    if (sig === last) return;
    last = sig;
    schedule();
  });
}

/** Статусы приёма — те же три, что понимает /api/onboarding/receiving. */
/**
 * Выход.
 *
 * Показывается ВСЕГДА, а не только при заведённом логине. Быстрый вход (app/auth.tsx) логина не
 * создаёт вовсе — он ставит только способ входа и уводит в анкету, — так что привязка кнопки к
 * логину прятала её ровно от тех, у кого другого выхода нет.
 *
 * Отсюда и два текста подтверждения. С логином профиль лежит на сервере и вернётся при входе. Без
 * логина возвращать его нечем: он записан по имени, но ключа к нему нет, и стирание устройства
 * действительно означает потерю. Об этом надо сказать прямо, а не одной формулировкой на оба
 * случая.
 */
/**
 * Строки профиля — кадр B.01, нижняя часть.
 *
 * Один общий список из пяти, а не два разных: на кадре все пять выглядят одинаково — круглая
 * иконка, заголовок, подпись, карандаш справа. Отличаются они только тем, что открывают: первые
 * три — экран вглубь, последние две — лист правки поверх профиля.
 *
 * «Основного» (пол и возраст) в этом списке нет — его нет и на кадре. Заводить строку, которой
 * дизайн не предусмотрел, значит решать за дизайн.
 */
export type RowKind = 'screen' | 'sheet';
export type HubRow = {
  id: 'interests' | 'personality' | 'safety' | 'languages' | 'location';
  kind: RowKind;
  title: () => string;
  sub: (p: any) => string;
};

/**
 * Интересы человека — из ЛЮБОЙ из двух форм, в которых они приходят.
 *
 * Пока идёт онбординг, профиль лежит в состоянии устройства объектом: `interests.explicit`.
 * А сервер хранит и отдаёт ПЛОСКИЙ список — проверено на живом проде:
 * `{"interests": ["sports","team","rugby",…]}`. После «Выйти → Войти» профиль приезжает с
 * сервера, и чтение `interests.explicit` давало undefined: экран писал «Пока не заполнено»
 * человеку с восемью интересами.
 *
 * Функция ОДНА на оба места, где это читается (строка хаба и `profileData`). Двумя копиями
 * это и было: первую я починил, вторая осталась врать — и именно её видно на экране.
 */
export function explicitInterests(p: any): string[] {
  const raw = p && p.interests;
  const list = Array.isArray(raw) ? raw : (raw && raw.explicit);
  return Array.isArray(list) ? list.filter(Boolean).map(String) : [];
}

/**
 * Добавить интересы, которые человек ПОДТВЕРДИЛ.
 *
 * Пишется и в состояние, и на сервер: матчинг читает строку кандидата, а не то, что лежит на
 * устройстве. Повторы отсекаются по нижнему регистру — «Хлеб» и «хлеб» это одно и то же, а два
 * почти одинаковых чипа в профиле выглядят как сбой.
 */
export async function addInterests(keys: string[]): Promise<boolean> {
  const p = getState().profile as any;
  const have = explicitInterests(p);
  const lower = new Set(have.map((x) => x.toLowerCase()));
  const add = keys.map(String).filter((k) => k.trim() && !lower.has(k.trim().toLowerCase()));
  if (!add.length) return false;
  set('interests.explicit', [...have, ...add]);
  // Отпечаток сбрасываем: без этого pushInterests сочтёт, что уже отправлял это, и правка
  // осталась бы только на телефоне — то есть невидимой для поиска.
  _sentInterests = null;
  return pushInterests();
}

/** Apply only a server-validated proposal after the person tapped its confirmation button. */
export function addConfirmedInterest(canonical: string, label: string, token: string): boolean {
  const key = String(canonical || '').trim().toLowerCase();
  if (!key || !token) return false;
  const p = getState().profile as any;
  const have = explicitInterests(p);
  if (have.some((x) => x.trim().toLowerCase() === key)) return false;
  set('interests.explicit', [...have, key]);
  set('interests.labels', { ...((p.interests || {}).labels || {}), [key]: String(label || key).trim() || key });
  set('interests.confirmations', { ...((p.interests || {}).confirmations || {}), [key]: token });
  _sentInterests = null;
  return true;
}

export const HUB_ROWS: HubRow[] = [
  {
    id: 'interests', kind: 'screen',
    title: () => T('Интересы', 'Interests'),
    sub: (p) => {
      const list = interestLabels(explicitInterests(p));
      return list.length ? list.join(' · ') : T('Пока не заполнено', 'Not set yet');
    },
  },
  {
    id: 'personality', kind: 'screen',
    title: () => T('Твоя личность', 'Your personality'),
    sub: (p) =>
      String(p?.personality || '').trim()
        ? String(p.personality).trim()
        : T('Пройди тест — Kleal опишет, как ты воспринимаешься', 'Take the test and Kleal will describe how you come across'),
  },
  {
    id: 'safety', kind: 'screen',
    title: () => T('Безопасность и приватность', 'Safety & Privacy'),
    sub: () => T('Что Kleal может использовать и твои границы', 'What Kleal can use, and your limits'),
  },
  {
    id: 'languages', kind: 'sheet',
    title: () => T('Языки', 'Languages'),
    sub: (p) => {
      const list = (p?.languages?.comfortable || []).map((k: string) => langPlainName(k, getLang() === 'ru'));
      return list.length ? list.join(' · ') : T('Пока не заполнено', 'Not set yet');
    },
  },
  {
    id: 'location', kind: 'sheet',
    title: () => T('Локация', 'Location'),
    sub: (p) => {
      const city = String(p?.city || '').trim();
      const km = p?.geo?.maxDistanceKm;
      const bits = [city, km ? T(`до ${km} км`, `up to ${km} km`) : ''].filter(Boolean);
      return bits.length ? bits.join(' · ') : T('Пока не заполнено', 'Not set yet');
    },
  },
];

/**
 * Лист «Кто ты»: имя, возраст, фото.
 *
 * Про имя. На сервере строка пользователя ключуется ИМЕНЕМ — другого идентификатора у хранилища
 * нет, и белый список profile-update имени не принимает (см. shared/fields.json, name.patchable
 * = false). Поэтому переименование меняет профиль на устройстве и привязку логина, но СТРОКА на
 * сервере остаётся под прежним именем, пока профиль не зарегистрируют заново. Это известный
 * разрыв, а не оплошность: молча создавать вторую строку под новым именем — значит раздвоить
 * человека в поиске.
 */
export const WHOAMI = {
  title: () => T('Кто ты', 'About you'),
  name: () => T('Имя', 'Name'),
  surname: () => T('Фамилия', 'Surname'),
  /** Фамилия не обязательна: людям, которые не хотят её называть, нельзя закрывать регистрацию. */
  surnameNote: () =>
    T('Не обязательно. Помогает не спутать двух тёзок в группе.',
      'Optional. Helps tell two people with the same first name apart.'),
  age: () => T('Возраст', 'Age'),
  photo: () => T('Фото', 'Photo'),
  changePhoto: () => T('Сменить фото', 'Change photo'),
  removePhoto: () => T('Убрать фото', 'Remove photo'),
  /** Снимок выбран, а подготовить его не вышло. Молчать тут нельзя — человек ждёт фото на экране. */
  photoFailed: () =>
    T('Не получилось подготовить снимок. Попробуй другой.',
      'Could not prepare that photo. Try another one.'),
  nameNote: () =>
    T(
      'Имя видно людям в поиске и в приглашениях.',
      'Your name is what people see in search and invitations.'
    ),
};

/** Листы правки поверх профиля — кадры со «Accept changes». */
export const SHEETS = {
  languages: () => T('Языки', 'Languages'),
  location: () => T('Локация', 'Location'),
  accept: () => T('Принять изменения', 'Accept changes'),
  search: () => T('Найти язык', 'Find a language'),
  nothing: () => T('Ничего не нашлось', 'Nothing found'),
  chosen: () => T('Выбрано', 'Selected'),
  close: () => T('Закрыть', 'Close'),
};

export const SIGNOUT = {
  label: (hasLogin: boolean) =>
    hasLogin ? T('Выйти из аккаунта', 'Sign out') : T('Выйти и начать заново', 'Sign out and start over'),
  ask: (hasLogin: boolean) =>
    hasLogin
      ? T(
          'Выйти из аккаунта? Профиль останется на сервере и вернётся при следующем входе.',
          'Sign out? Your profile stays on the server and comes back when you sign in.'
        )
      : T(
          'У этого профиля нет логина, поэтому вернуть его будет нечем — он сотрётся вместе со всем, что собрано на этом телефоне. Выйти?',
          'This profile has no login, so there is nothing to restore it with — it will be erased along with everything collected on this phone. Sign out?'
        ),
  yes: () => T('Выйти', 'Sign out'),
  no: () => T('Отмена', 'Cancel'),
  who: (login: string | null) =>
    login ? T(`Вход выполнен как ${login}`, `Signed in as ${login}`)
          : T('Аккаунт не подключён', 'No account connected'),
};

export const AVAIL: [string, () => string][] = [
  ['active', () => T('Открыт', 'Open')],
  ['busy', () => T('Занят', 'Busy')],
  ['paused', () => T('Пауза', 'Pause')],
];

/**
 * «Обновлено сегодня» и далее. Метка приходит из локального времени устройства: в хранилище такой
 * колонки нет, и веб делает ровно так же. Без метки времени строку не рисуем вовсе — это честнее,
 * чем «обновлено сегодня» о тексте, написанном месяц назад.
 */
export function fmtUpdated(ts?: number | null): string {
  if (!ts) return '';
  const d = Math.floor((Date.now() - ts) / 864e5);
  if (d <= 0) return T('Обновлено сегодня', 'Updated today');
  if (d === 1) return T('Обновлено вчера', 'Updated yesterday');
  if (d < 7) return T(`Обновлено ${d} дн. назад`, `Updated ${d} days ago`);
  const dt = new Date(ts);
  return T(
    'Обновлено ' + dt.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
    'Updated ' + dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  );
}

// ---------------------------------------------------------------- derive

export type KV = [string, string];
/**
 * `name` — то, что лежит в профиле и уходит в матчинг (coffee, football). `label` — то, что видит
 * человек («Кофе»). Раздельно намеренно: онбординг хранит канонические ключи, иначе по интересам
 * не совпадёт никто, а показывать человеку ключ из базы — значит показывать ему внутренности.
 * Своё, написанное руками, hobbyPlain возвращает как есть.
 */
export type Interest = { name: string; label: string; conf: 'High' | 'Medium' | 'Low'; used: boolean; kv: KV[] };
export type Row = { title: string; value: string };

export type SafetyFlags = {
  autonomy: 'ask' | 'auto';
  confirmShare: boolean;
  paused: boolean;
  publicFirst: boolean;
  noLateNight: boolean;
  avoidAlcohol: boolean;
  sharePlan: boolean;
  useInterestsArea: boolean;
  useFeedback: boolean;
  inferNew: boolean;
  noSensitive: boolean;
  suggestBeyond: boolean;
  publicMap: boolean;
  datingMode: boolean;
  preferVerified: boolean;
  excludeKnown: boolean;
};

export type ProfileData = {
  name: string;
  /** Подтверждён ли профиль. Печать рядом с именем рисуется только по нему. */
  verified: boolean;
  confidence: number;
  basics: Row[];
  interests: Interest[];
  safety: SafetyFlags;
};

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const arr = (v: any): any[] => (Array.isArray(v) ? v : v != null && v !== '' ? [v] : []);
const lc = (s: any) => String(s == null ? '' : s).toLowerCase();

/** Мягкий поиск по ключам словаря: «Кофе» находит и «кофе», и «specialty coffee». */
function pickBy(m: any, name: string): any {
  if (!m || typeof m !== 'object') return null;
  const k = lc(name);
  for (const key of Object.keys(m)) {
    const kl = lc(key);
    if (kl === k || kl.includes(k) || k.includes(kl)) return m[key];
  }
  return null;
}

/** Роли лежат вложенным объектом произвольной глубины — разворачиваем в плоский поиск по имени. */
function roleOf(rolesRaw: any, name: string, only: string[]): any {
  const flat: Record<string, any> = {};
  (function eat(d: any) {
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      for (const k of Object.keys(d)) {
        const v = d[k];
        if (v && typeof v === 'object' && !Array.isArray(v)) eat(v);
        else if (v) flat[lc(k)] = v;
      }
    }
  })(rolesRaw);
  const k = lc(name);
  for (const kk of Object.keys(flat)) if (kk === k || kk.includes(k) || k.includes(kk)) return flat[kk];
  // Единственный интерес и роль строкой — значит роль его и есть, как бы её ни назвали.
  if ((typeof rolesRaw === 'string' || Array.isArray(rolesRaw)) && only.length === 1) return rolesRaw;
  return null;
}

const inList = (list: any, name: string) =>
  arr(list).some((x) => {
    const a = lc(x);
    const b = lc(name);
    return a === b || a.includes(b) || b.includes(a);
  });

export function profileData(op: Profile | any): ProfileData {
  op = op || {};
  const langs = arr(op.languages && (op.languages.comfortable || op.languages.fluent));
  const areas = arr(op.geo && op.geo.comfortableAreas);
  const city = areas[0] || op.city || '';
  const km = op.geo && op.geo.maxDistanceKm;
  // Интересы приходят В ДВУХ ФОРМАХ, и читать надо обе.
  //
  // Пока человек проходит онбординг, профиль лежит в состоянии устройства объектом:
  // `interests.explicit`. А сервер хранит и отдаёт ПЛОСКИЙ список — проверено на живом проде:
  // `{"interests": ["sports","team","rugby",…]}`. Значит после «Выйти → Войти» (когда профиль
  // приезжает с сервера) экран читал `interests.explicit` у массива, получал undefined — и писал
  // «Интересы · Пока не заполнено» человеку, у которого их восемь.
  //
  // Тот же класс ошибки, что с `languages`: одно поле, две формы, и молчаливо пустой результат
  // вместо ошибки. Поэтому здесь не «какая форма правильная», а «понимаем обе».
  const ints = explicitInterests(op);
  const interestLabelsByKey = (!Array.isArray(op.interests) && op.interests?.labels) || {};
  const rolesRaw = (op.interests && op.interests.roles) || {};
  const exp = (op.interests && op.interests.experienceByInterest) || {};
  const games = (op.domains && op.domains.games) || {};
  const sport = (op.domains && op.domains.sport) || {};
  const langd = (op.domains && op.domains.language) || {};
  const net = (op.domains && op.domains.networking) || {};
  const sf = op.safety || {};
  const pm = op.permissions || {};

  const interests: Interest[] = ints.map((name, i) => {
    const kv: KV[] = [];
    const n = lc(name);
    const r = roleOf(rolesRaw, name, ints);
    const e = pickBy(exp, name);
    if (r) kv.push([T('Роль', 'Role'), arr(r).map(cap).join(' / ')]);
    if (e) kv.push([T('Опыт', 'Experience'), String(e)]);
    if (inList(games.gamesList, name) || /dota|valorant|league|\bcs\b|apex|game/.test(n)) {
      const p = pickBy(games.platformsByGame, name);
      if (p) kv.push([T('Платформа', 'Platform'), String(p)]);
      const rk = pickBy(games.rankByGame, name);
      if (rk) kv.push([T('Ранг / уровень', 'Rank / level'), String(rk)]);
    }
    if (inList(sport.sportsList, name)) {
      const lv = pickBy(sport.skillLevelBySport, name);
      if (lv) kv.push([T('Уровень', 'Skill level'), cap(String(lv))]);
      const tm = pickBy(sport.favoriteTeams, name) ||
        (Array.isArray(sport.favoriteTeams) ? sport.favoriteTeams.join(', ') : null);
      if (tm) kv.push([T('Команда', 'Team'), String(tm)]);
    }
    if (/language|spanish|english|french|german|italian|practice/.test(n)) {
      if (langd.targetLanguage) kv.push([T('Язык', 'Language'), String(langd.targetLanguage)]);
      if (langd.targetLevel) kv.push([T('Уровень', 'Level'), String(langd.targetLevel)]);
    }
    if (/network|startup|business|career|founder/.test(n)) {
      if (net.industry) kv.push([T('Отрасль', 'Industry'), String(net.industry)]);
      if (net.goal) kv.push([T('Цель', 'Goal'), String(net.goal)]);
    }
    // Уверенность как в вебе: первые два интереса человек назвал сам и осознанно, дальше — по тому,
    // рассказал ли он о них хоть что-то сверх названия.
    const conf: Interest['conf'] = i < 2 ? 'High' : kv.length ? 'Medium' : 'Low';
    const used = !(op.interests && op.interests.unused && op.interests.unused.includes(name));
    return { name, label: String(interestLabelsByKey[name] || interestLabel(name)), conf, used, kv };
  });

  const basics: Row[] = [];
  if (op.gender || op.age) {
    // Пол показываем подписью, а не хранимым ключом. В вебе здесь просто `cap(gender)`, и на
    // русском экране это «Male» — то есть значение из базы, показанное человеку как есть.
    basics.push({
      title: T('Основное', 'Basics'),
      value: [op.gender ? sexLabel(String(op.gender)) : '', op.age].filter(Boolean).join(' · ') || '—',
    });
  }
  if (areas.length || city) {
    basics.push({
      title: T('Локация', 'Location'),
      value: [areas.join(', ') || city, km ? T(`до ${km} км`, `Max ${km} km`) : null].filter(Boolean).join(' · '),
    });
  }
  if (langs.length) basics.push({ title: T('Языки', 'Languages'), value: langs.join(' · ') });

  // Наполненность — доля из шести признаков, ровно как в вебе. Не «красивое число»: полоса,
  // которая всегда 74 %, не сообщает ничего.
  const have = [op.name, langs.length, areas.length || city, ints.length, op.summary,
                pm.useProfileForMatching !== undefined];
  const confidence = Math.round((100 * have.filter(Boolean).length) / 6);

  const consent = pm.useProfileForMatching !== false;
  const remember = !!pm.rememberPreferences;
  const safety: SafetyFlags = {
    autonomy: sf.autonomy === 'auto' ? 'auto' : 'ask',
    confirmShare: sf.confirmShare !== false,
    paused: !!sf.paused,
    publicFirst: sf.publicPlacesOnly !== false,
    noLateNight: sf.lateNight !== false,
    avoidAlcohol: !!sf.avoidAlcohol,
    sharePlan: !!sf.sharePlan,
    useInterestsArea: consent,
    useFeedback: remember,
    inferNew: remember,
    noSensitive: sf.noSensitive !== false,
    suggestBeyond: pm.allowAdjacentMatches !== false,
    publicMap: !!pm.publicMap,
    datingMode: !!pm.datingMode,
    preferVerified: !!sf.verifiedOnly,
    excludeKnown: sf.excludeKnown !== false,
  };

  return { name: op.name || T('Ты', 'You'), verified: !!(op as any).verified, confidence, basics, interests, safety };
}

// ---------------------------------------------------------------- интересы

export const INTERESTS_SCREEN = {
  hint: () =>
    T(
      'Если переключатель включён, Kleal учитывает этот интерес при подборе.',
      'When a toggle is on, Kleal uses that interest for matching.'
    ),
  summary: (name: string) =>
    T(`Kleal ещё разбирается, что для тебя значит ${name}.`, `Kleal is still learning about your ${name}.`),
  emptyTitle: () => T('Пока нет интересов', 'No interests yet'),
  emptySub: () =>
    T(
      'Расскажи Kleal, чем увлекаешься — и они появятся здесь.',
      "Tell Kleal what you're into and they'll show up here."
    ),
  add: () => T('Добавить интересы', 'Add interests'),
  remove: () => T('Удалить', 'Remove'),
  confLabel: (c: string) =>
    c === 'High' ? T('высокая', 'high') : c === 'Medium' ? T('средняя', 'medium') : T('низкая', 'low'),
};

// ---------------------------------------------------------------- личность

export const PERSONALITY = {
  title: () => T('Твоя личность', 'Your personality'),
  takeTest: () => T('Пройти тест от Kleal', 'Take your personality test'),
  empty: () =>
    T(
      'Пройди тест — и Kleal расскажет, как ты воспринимаешься со стороны и с кем тебе легко.',
      'Take the test and Kleal will describe how you come across and who you click with.'
    ),
  editWith: () => T('Изменить с Kleal', 'Edit with Kleal'),
  /** Оси теста на самом экране личности: они лежат в профиле, и прятать их от того, про кого они,
   *  незачем. Заодно видно, что тест засчитан, даже когда абзац не собрался. */
  axesTitle: () => T('Ответы теста', 'Your test answers'),
  retake: () => T('Пройти тест заново', 'Take the test again'),
  /** Предложение интересов из истории — GR/профиль. Подтверждает человек, а не приложение. */
  fromStoryTitle: () => T('Из твоей истории', 'From your story'),
  fromStoryNote: () => T(
    'Матчинг ищет по интересам, а не по тексту. Отметь, что добавить — остальное останется просто историей.',
    'Search runs on interests, not prose. Tap what to add — the rest stays just a story.'
  ),
  fromStoryAdd: (n: number) =>
    n === 1 ? T('Добавить 1 интерес', 'Add 1 interest') : T(`Добавить ${n}`, `Add ${n}`),
  fromStoryAdded: () => T('Добавлено в интересы', 'Added to your interests'),
  fromStoryNone: () => T('В истории пока не видно занятий — напиши, что ты делаешь и любишь.',
                         'No activities visible in the story yet — write what you do and enjoy.'),

  storyCap: () =>
    T(
      'Расскажи историю своей жизни в свободном формате (детство, обучение, интересы, профессия)',
      'Tell your life story in your own words — childhood, studies, interests, work'
    ),
  storyPlaceholder: () =>
    T('Пиши как получится — Kleal сам разберётся.', "Write it however it comes out — Kleal will make sense of it."),
  confirm: () => T('Сохранить и закрыть', 'Confirm & Close'),
  saved: () => T('Сохранено', 'Saved'),

  /** Явные кнопки под полем истории: применить написанное и увидеть, что из этого вышло. */
  apply: () => T('Сохранить историю', 'Save your story'),
  applied: () => T('История сохранена', 'Story saved'),
  rebuild: () => T('Пересобрать сводку Kleal', 'Rebuild Kleal’s summary'),
  rebuildNote: () =>
    T(
      'Kleal перечитает профиль вместе с твоей историей и перепишет сводку — ту, что стоит на главной профиля.',
      'Kleal re-reads your profile together with your story and rewrites the summary — the one on your profile home.'
    ),
  rebuiltLabel: () => T('Новая сводка Kleal', 'Your new Kleal summary'),
  rebuildFailed: () =>
    T('Не получилось пересобрать. Попробуй ещё раз.', 'Couldn’t rebuild it. Try again.'),
};

/** Предел из update_user: STORY_MAX. Обрезаем здесь же, чтобы не отправлять заведомо лишнее. */
export const STORY_MAX = 4000;

export type TestQ = {
  k: string;
  /** Сцена, если она есть: одна строка обстановки перед самим вопросом. */
  scene?: () => string;
  q: () => string;
  o: (() => string)[];
  m: string[];
  free?: boolean;
  /** Незаконченная фраза: человек дописывает её, а не отвечает на открытый вопрос. */
  stem?: () => string;
};

/**
 * Тест Kleal — вопросы на клиенте и РОВНО один вызов /api/buddy/persona в конце.
 * По одному обращению к модели на вопрос — это столько же шансов повиснуть там, где вопросы всё
 * равно заданы заранее.
 *
 * ЧТО ЗДЕСЬ ИЗМЕНИЛОСЬ И ПОЧЕМУ. Прежние восемь вопросов спрашивали про ПРЕДПОЧТЕНИЯ («какой
 * разговор тебе ближе?»), и на такие вопросы человек отвечает тем, каким он себя видит, а не тем,
 * какой он есть: «глубокий, про смыслы» выбирают почти все. Характер видно в трёх других местах —
 * в поведении («что ты обычно делаешь»), в выборе с ценой (обе стороны чем-то жертвуют) и в
 * трении (отменили, повисла пауза, человек надоел). Отсюда сцена перед вопросом: она превращает
 * ответ из самооценки в припоминание.
 *
 * Три оси добавлены и раньше не спрашивались вовсе, а рассказывают больше остальных:
 *   friction — что человек делает, когда план рассыпался;
 *   lull     — что он делает с молчанием;
 *   give     — что он приносит другим, а не что хочет получить.
 *
 * Варианта «зависит / гибко» больше нет ни в одном вопросе. Он собирал тех, кто просто не хотел
 * выбирать, и — хуже — уходил в профиль как `null`, то есть не сохранялся ВООБЩЕ: человек отвечал,
 * а ось оставалась пустой. Не хочешь отвечать — «Пропустить», и это видно честно.
 *
 * `m[n]` — токен оси для профиля. Словарь закрыт на сервере (_PERSONA_AXES в onboarding):
 * незнакомый токен там отбрасывается, поэтому менять их парой с сервером, а не по одному.
 */
export const TEST_Q: TestQ[] = [
  {
    k: 'energy',
    scene: () => T('Суббота, ты весь день был среди людей.', 'Saturday, you have been around people all day.'),
    q: () => T('Наступает вечер. Что с тобой происходит?', 'Evening comes. What happens to you?'),
    o: [
      () => T('Ещё не наигрался — ищешь, куда поехать дальше', 'Still going — you look for where to head next'),
      () => T('Отключаешь телефон и никого не хочешь', 'You switch the phone off and want nobody'),
      () => T('Хватает сил ровно на одного человека', 'You have exactly one person left in you'),
    ],
    m: ['energised', 'drained', 'depends'],
  },
  {
    k: 'group',
    q: () => T('Вспомни последний разговор, из которого ты вышел довольным. Сколько вас было?',
               'Think of the last conversation you walked away happy from. How many of you were there?'),
    o: [
      () => T('Двое', 'Two'),
      () => T('Стол на четверых-пятерых', 'A table of four or five'),
      () => T('Много, и ты был в гуще', 'A lot of people, and you were in the middle of it'),
    ],
    m: ['one', 'small', 'crowd'],
  },
  {
    k: 'depth',
    scene: () => T('Полчаса как познакомились, разговор пошёл.', 'Half an hour in, the conversation has caught.'),
    q: () => T('О чём вы говорите, когда становится интересно?', 'What are you talking about when it gets good?'),
    o: [
      () => T('О том, о чём обычно не говорят с незнакомыми', 'About things you normally do not say to strangers'),
      () => T('О ерунде, но так, что оба смеётесь', 'About nothing much, but you are both laughing'),
      () => T('О деле: кто что делает и как это устроено', 'About the work: who does what and how it is put together'),
    ],
    m: ['deep', 'light', 'practical'],
  },
  {
    k: 'firstMeet',
    q: () => T('Первая встреча удалась. По чему ты это понял?',
               'A first meet went well. How do you know?'),
    o: [
      () => T('Просидели дольше, чем собирались', 'You stayed longer than you meant to'),
      () => T('Что-то сделали вместе, а не просто поговорили', 'You did something together, not just talked'),
      () => T('Вокруг что-то происходило, и вы это обсуждали', 'Something was going on around you and you had it to talk about'),
    ],
    m: ['talk', 'doing', 'event'],
  },
  {
    k: 'pace',
    q: () => T('Когда новый человек узнаёт про тебя что-то настоящее?',
               'When does a new person learn something real about you?'),
    o: [
      () => T('Почти сразу — ты не умеешь иначе', 'Almost straight away — you do not know another way'),
      () => T('Когда решишь, что ему можно', 'Once you have decided they can be trusted with it'),
      () => T('Когда он расскажет первым', 'Once they have gone first'),
    ],
    m: ['fast', 'slow', 'mirror'],
  },
  {
    k: 'planning',
    scene: () => T('Пятница, шесть вечера, планов нет.', 'Friday, six in the evening, nothing planned.'),
    q: () => T('Как так вышло?', 'How did that happen?'),
    o: [
      () => T('Не вышло — ты договорился ещё в среду', 'It did not — you sorted this out on Wednesday'),
      () => T('Сейчас напишешь троим и куда-нибудь поедешь', 'You are about to message three people and go somewhere'),
      () => T('И хорошо: вечер дома тебя устраивает', 'And that is fine — an evening at home suits you'),
    ],
    m: ['advance', 'spontaneous', 'flexible'],
  },
  {
    k: 'friction',
    scene: () => T('За час до встречи человек пишет: не смогу.', 'An hour before you meet, they message: I cannot make it.'),
    q: () => T('Что ты делаешь?', 'What do you do?'),
    o: [
      () => T('Сразу предлагаешь другой день', 'You offer another day right away'),
      () => T('Отвечаешь «ок» и ждёшь, что предложит он', 'You reply “sure” and wait for them to offer one'),
      () => T('Ничего. Значит, не сложилось', 'Nothing. It was not meant to happen'),
    ],
    m: ['reschedule', 'wait', 'letgo'],
  },
  {
    k: 'lull',
    scene: () => T('Разговор идёт хорошо, и вдруг оба замолчали.', 'The conversation is going well, and suddenly you both go quiet.'),
    q: () => T('Что происходит внутри?', 'What is going on inside?'),
    o: [
      () => T('Ты уже придумываешь, чем её заполнить', 'You are already thinking of something to fill it with'),
      () => T('Ничего. Пауза — тоже часть разговора', 'Nothing. A pause is part of the conversation too'),
      () => T('Становится неловко и хочется закруглиться', 'It gets awkward and you want to wrap up'),
    ],
    m: ['fill', 'allow', 'uneasy'],
  },
  {
    k: 'give',
    q: () => T('За что тебя держат те, кто с тобой давно?',
               'What do the people who have stayed keep you around for?'),
    o: [
      () => T('Ты слушаешь и помнишь', 'You listen, and you remember'),
      () => T('С тобой смешно', 'You make it funny'),
      () => T('На тебя можно рассчитывать', 'You can be counted on'),
      () => T('Ты вытаскиваешь их из дома', 'You get them out of the house'),
    ],
    m: ['listen', 'fun', 'reliable', 'instigate'],
  },
  {
    k: 'seek',
    q: () => T('Чего тебе сейчас не хватает?', 'What are you short of right now?'),
    o: [
      () => T('Двух-трёх своих людей', 'Two or three people of your own'),
      () => T('Компании под конкретное занятие', 'Company for one specific thing'),
      () => T('Просто больше жизни вокруг', 'Simply more life around you'),
    ],
    m: ['long', 'interest', 'wider'],
  },
  {
    // Незаконченная фраза, а не открытый вопрос. «Что о тебе стоит знать?» человек читает как
    // просьбу презентовать себя и пишет резюме; допиши-фразу отвечают почти всегда конкретным
    // случаем, а модели именно конкретное и нужно.
    k: 'own',
    q: () => T('Последнее. Допиши фразу — как есть, без причёсывания.',
               'Last one. Finish the sentence — as it comes, unpolished.'),
    stem: () => T('Со мной легко, если…', 'I am easy to be around if…'),
    o: [], m: [], free: true,
  },
];

/**
 * Как ось читается человеку. Тест сохраняет токены в профиль, а показать их было негде: экран
 * результата отсутствовал вовсе, и человек видел только абзац от модели. Тест, который что-то
 * узнал и не сказал что, — гадание, а не тест.
 */
export const AXIS_LABEL: Record<string, () => string> = {
  energy: () => T('Люди', 'People'),
  group: () => T('Формат', 'Format'),
  depth: () => T('Разговор', 'Conversation'),
  firstMeet: () => T('Первая встреча', 'A first meet'),
  pace: () => T('Открытость', 'Opening up'),
  planning: () => T('Планы', 'Plans'),
  friction: () => T('Когда отменяют', 'When plans fall through'),
  lull: () => T('Пауза', 'Silence'),
  give: () => T('Что приносишь', 'What you bring'),
  seek: () => T('Ищешь', 'Looking for'),
};

export const AXIS_VALUE: Record<string, () => string> = {
  energised: () => T('заряжают', 'charge you up'),
  drained: () => T('забирают силы', 'take it out of you'),
  depends: () => T('по одному — да, толпой — нет', 'one at a time, not in a crowd'),
  one: () => T('один на один', 'one to one'),
  small: () => T('небольшой стол', 'a small table'),
  crowd: () => T('большая компания', 'a big crowd'),
  deep: () => T('вглубь', 'goes deep'),
  light: () => T('легко и смешно', 'light and funny'),
  practical: () => T('по делу', 'to the point'),
  talk: () => T('просидеть дольше, чем собирались', 'staying longer than planned'),
  doing: () => T('делать что-то вместе', 'doing something together'),
  event: () => T('там, где что-то происходит', 'somewhere things are happening'),
  fast: () => T('сразу настоящий', 'real from the start'),
  slow: () => T('когда решишь, что можно', 'once you decide they can be trusted'),
  mirror: () => T('в ответ на откровенность', 'in answer to theirs'),
  advance: () => T('заранее', 'agreed in advance'),
  spontaneous: () => T('спонтанно', 'on the spur'),
  flexible: () => T('вечер дома тоже вариант', 'an evening in is fine too'),
  reschedule: () => T('предлагаешь другой день', 'you offer another day'),
  wait: () => T('ждёшь встречного шага', 'you wait for their move'),
  letgo: () => T('отпускаешь', 'you let it go'),
  fill: () => T('заполняешь', 'you fill it'),
  allow: () => T('даёшь ей побыть', 'you let it sit'),
  uneasy: () => T('становится неловко', 'it makes you uneasy'),
  listen: () => T('слушаешь и помнишь', 'you listen and remember'),
  fun: () => T('с тобой смешно', 'you make it funny'),
  reliable: () => T('на тебя можно рассчитывать', 'you can be counted on'),
  instigate: () => T('вытаскиваешь из дома', 'you get people out'),
  long: () => T('своих людей надолго', 'people of your own, long term'),
  interest: () => T('компанию под занятие', 'company for one thing'),
  wider: () => T('больше жизни вокруг', 'more life around you'),
};

/** Порядок строк на экране результата — от «как с людьми» к «что делаешь, когда трудно». */
export const AXIS_ORDER = [
  'energy', 'group', 'depth', 'pace', 'firstMeet', 'planning', 'friction', 'lull', 'give', 'seek',
];

export const TEST = {
  title: () => T('Тест от Kleal', 'Your Kleal test'),
  of: (i: number, n: number) => T(`Вопрос ${i} из ${n}`, `Question ${i} of ${n}`),
  skip: () => T('Пропустить', 'Skip'),
  placeholder: () => T('Дальше своими словами…', 'Carry on in your own words…'),
  finish: () => T('Готово', 'Done'),
  working: () => T('Kleal обдумывает ответы…', 'Kleal is thinking it over…'),
  failed: () =>
    T('Не получилось собрать результат. Ответы сохранены — попробуй ещё раз.',
      'Could not put the result together. Your answers are saved — try again.'),

  /** Экран результата. Раньше тест просто закрывался, и человек не видел, что из него вышло. */
  resultTitle: () => T('Вот что получилось', 'Here is what came out'),
  axesTitle: () => T('Что Kleal записал', 'What Kleal wrote down'),
  axesNote: () => T('Это остаётся в профиле и видно только тебе.',
                    'This stays in your profile and only you see it.'),
  skipped: () => T('Пропущено', 'Skipped'),
  keep: () => T('Сохранить', 'Keep it'),
  again: () => T('Пройти заново', 'Take it again'),
  /** Честная строка, когда абзац не собрался, а ответы записались. */
  axesOnly: () =>
    T('Ответы сохранены — абзац Kleal напишет позже.', 'Your answers are saved — Kleal will write the paragraph later.'),
};

// ---------------------------------------------------------------- безопасность

export type SafetyItem =
  | { k: 'tog'; flag: keyof SafetyFlags; label: () => string; desc: () => string }
  | { k: 'choice'; label: () => string; desc: () => string; options: (() => string)[] }
  | { k: 'sub'; label: () => string };

export type SafetyGroup = { t: () => string; c: () => string; items: SafetyItem[] };

/**
 * Шесть групп — те же и в том же порядке, что в вебе. Подписи важны не меньше переключателей:
 * в каждой группе сказано, что означает «включено», потому что для одних тумблеров это «безопаснее»,
 * а для других — «шире охват», и по одному виду их не различить.
 */
export const SAFETY_GROUPS: SafetyGroup[] = [
  {
    t: () => T('Как Kleal действует за тебя', 'How Kleal acts for you'),
    c: () => T('Главные рычаги: насколько агент самостоятелен и пауза в один тап.',
               'The big levers — your agent’s autonomy and a one-tap pause.'),
    items: [
      { k: 'choice', label: () => T('Когда Kleal кого-то находит', 'When Kleal finds someone'),
        desc: () => T('Спрашивать перед тем, как написать, или пусть Kleal знакомит сам.',
                      'Ask before reaching out, or let Kleal introduce you automatically.'),
        options: [() => T('Сначала спросить', 'Ask me first'), () => T('Знакомить сам', 'Introduce automatically')] },
      { k: 'tog', flag: 'confirmShare',
        label: () => T('Спрашивать перед тем, как делиться моими данными', 'Confirm before sharing my details'),
        desc: () => T('Спрашивать, прежде чем показать твоё имя, фото или контакты — даже когда Kleal сам договаривается о встрече.',
                      'Ask before revealing your name, photo or contact — even when Kleal arranges plans for you.') },
      { k: 'tog', flag: 'paused',
        label: () => T('Поставить Kleal на паузу', 'Pause Kleal'),
        desc: () => T('Остановить новые подборы и знакомства. Профиль и память сохранятся.',
                      'Stop all new matching and outreach. Your profile and memory stay saved.') },
    ],
  },
  {
    t: () => T('Встречи вживую', 'Meeting in person'),
    c: () => T('Как Kleal делает встречи безопаснее. Здесь везде: включено = безопаснее.',
               'How Kleal keeps real-world plans safe. Every switch here: on = safer.'),
    items: [
      { k: 'tog', flag: 'publicFirst',
        label: () => T('Первые встречи — только в людных местах', 'Keep first meetups public'),
        desc: () => T('Первые встречи проходят в кафе, парках и других общественных местах.',
                      'First meets stay in cafes, parks and other public spots.') },
      { k: 'tog', flag: 'noLateNight',
        label: () => T('Никаких встреч один на один поздно вечером', 'No solo late-night meets'),
        desc: () => T('Kleal не будет предлагать встречи наедине поздним вечером.',
                      'Kleal avoids one-on-one plans late at night.') },
      { k: 'tog', flag: 'avoidAlcohol',
        label: () => T('Избегать мест, где всё вокруг алкоголя', 'Avoid alcohol-focused venues'),
        desc: () => T('Пропускать бары и подобные места для первых встреч.',
                      'Skip bars and heavy-drinking spots for first meets.') },
      { k: 'tog', flag: 'sharePlan',
        label: () => T('Делиться планом с доверенным контактом', 'Share my plan with a trusted contact'),
        desc: () => T('Автоматически отправлять близкому человеку, с кем, где и когда ты встречаешься.',
                      'Auto-send who, where and when to someone you choose.') },
    ],
  },
  {
    t: () => T('Что Kleal может использовать и запоминать', 'What Kleal may use & remember'),
    c: () => T('Твоё согласие на то, что Kleal читает и узнаёт. Включено = Kleal может это использовать.',
               'Your consent for what Kleal reads and learns. On = Kleal may use it.'),
    items: [
      { k: 'tog', flag: 'useInterestsArea',
        label: () => T('Подбирать по моим интересам и району', 'Match on my interests & area'),
        desc: () => T('Использовать твои увлечения и район города — но никогда точное местоположение.',
                      'Use what you like and your city area — never your exact location.') },
      { k: 'tog', flag: 'useFeedback',
        label: () => T('Учиться на моих оценках и действиях', 'Learn from my feedback & activity'),
        desc: () => T('Использовать твои оценки и то, какие планы ты принимаешь или отклоняешь.',
                      'Use your ratings and which plans you accept or decline.') },
      { k: 'tog', flag: 'inferNew',
        label: () => T('Разрешить Kleal делать выводы обо мне', 'Let Kleal infer new things about me'),
        desc: () => T('Разрешить догадки сверх того, что ты сказал напрямую — например, о любимых местах.',
                      'Allow guesses beyond what you stated, like preferred venues.') },
      { k: 'sub', label: () => T('Ограничения', 'Guardrails') },
      { k: 'tog', flag: 'noSensitive',
        label: () => T('Никогда не делать выводов о чувствительном', 'Never infer sensitive traits'),
        desc: () => T('Не хранить в памяти здоровье, религию, политику и ориентацию.',
                      'Keep health, religion, politics and orientation out of memory.') },
    ],
  },
  {
    t: () => T('Как тебя находят люди', 'How people find you'),
    c: () => T('Твой охват и видимость. Включено = больше охват, выключено = больше приватности.',
               'Your reach and visibility. On = more reach, off = more private.'),
    items: [
      { k: 'tog', flag: 'suggestBeyond',
        label: () => T('Предлагать людей за пределами привычного круга', 'Suggest people beyond my usual circles'),
        desc: () => T('Иногда предлагать людей со смежными интересами и планы вне привычного.',
                      'Occasionally propose friends-of-interests and plans outside your usuals.') },
      { k: 'tog', flag: 'publicMap',
        label: () => T('Показывать меня на карте', 'Show me on the discovery map'),
        desc: () => T('Другие смогут наткнуться на тебя на общей карте.',
                      'Let others come across you on the public map.') },
      { k: 'tog', flag: 'datingMode',
        label: () => T('Режим знакомств', 'Dating mode'),
        desc: () => T('По умолчанию выключен. Включи, чтобы Kleal предлагал и романтические знакомства.',
                      'Off by default. Turn on to let Kleal suggest dating intros too.') },
    ],
  },
  {
    t: () => T('Верификация и люди', 'Verification & people'),
    c: () => T('С кем Kleal будет тебя знакомить. Включено = осторожнее.',
               'Who Kleal will introduce you to. On = more protective.'),
    items: [
      { k: 'tog', flag: 'preferVerified',
        label: () => T('Предпочитать подтверждённых людей', 'Prefer verified people'),
        desc: () => T('Kleal будет отдавать предпочтение подтверждённым профилям.',
                      'Kleal favours verified profiles when it matches you.') },
      { k: 'tog', flag: 'excludeKnown',
        label: () => T('Не сводить меня с теми, кого я могу знать', 'Don’t match me with people I may know'),
        desc: () => T('Исключить коллег, бывших и контакты из телефона.',
                      'Exclude coworkers, exes and phone contacts from suggestions.') },
    ],
  },
];

export const SAFETY_LEAD = {
  title: () => T('Всё под твоим контролем', 'You’re in control'),
  body: () =>
    T(
      'Kleal ничего не делает без твоего согласия. Он показывает район города, а не точное место, узнаёт только то, что ты разрешил, и всё здесь можно откатить в любой момент.',
      'Kleal never acts without your say-so. It shares your city area, never your exact location, learns only what you allow, and everything here is reversible anytime.'
    ),
};

/**
 * Обратное отображение флагов экрана в поля профиля.
 *
 * Нужно ровно потому, что profileData() их СВОДИТ: `useFeedback` и `inferNew` оба приходят из
 * одного `permissions.rememberPreferences`, а `useInterestsArea` — из `useProfileForMatching`.
 * Без этой таблицы переключатель на экране менял бы что-то своё, а профиль — своё.
 */
export const SAFETY_PATH: Record<string, string> = {
  confirmShare: 'safety.confirmShare',
  paused: 'safety.paused',
  publicFirst: 'safety.publicPlacesOnly',
  noLateNight: 'safety.lateNight',
  avoidAlcohol: 'safety.avoidAlcohol',
  sharePlan: 'safety.sharePlan',
  noSensitive: 'safety.noSensitive',
  preferVerified: 'safety.verifiedOnly',
  excludeKnown: 'safety.excludeKnown',
  useInterestsArea: 'permissions.useProfileForMatching',
  useFeedback: 'permissions.rememberPreferences',
  inferNew: 'permissions.rememberPreferences',
  suggestBeyond: 'permissions.allowAdjacentMatches',
  publicMap: 'permissions.publicMap',
  datingMode: 'permissions.datingMode',
};

export const langCode = () => getLang();
