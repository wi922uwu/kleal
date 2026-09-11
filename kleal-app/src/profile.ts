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

export const PROFILE_TITLE = () => T('Мой профиль Kleal', 'My Kleal Profile', 'Mi perfil de Kleal');

export const SECTIONS: { id: SectionId; title: () => string; sub: () => string }[] = [
  {
    id: 'interests',
    title: () => T('Интересы', 'Interests', 'Intereses'),
    sub: () => T('Чем ты любишь заниматься с людьми', 'What you like doing with people', 'Lo que te gusta hacer con otras personas'),
  },
  {
    id: 'personality',
    title: () => T('Твоя личность', 'Your personality', 'Tu personalidad'),
    sub: () => T('Как ты воспринимаешься', 'How you come across', 'Cómo te presentas'),
  },
  {
    id: 'safety',
    title: () => T('Безопасность и приватность', 'Safety & Privacy', 'Seguridad y privacidad'),
    sub: () => T('Что Kleal может использовать и твои границы', 'What Kleal can use, and your limits', 'Lo que Kleal puede usar y tus límites'),
  },
];

export const HUB = {
  confidence: () => T('Наполненность профиля', 'Profile confidence', 'Confianza en el perfil'),
  summaryLabel: () => T('Сводка Kleal', "Kleal's summary", 'Resumen de Kleal'),
  edit: () => T('Изменить', 'Edit', 'Editar'),
  rewrite: () => T('Пересобрать', 'Rewrite', 'Reescribir'),
  save: () => T('Сохранить', 'Save', 'Guardar'),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),
  createIntent: () => T('Создать интент', 'Create intent', 'Crear propuesta'),
  lang: () => T('Язык интерфейса', 'Interface language', 'Idioma de la interfaz'),
  avail: () => T('Доступность', 'Availability', 'Disponibilidad'),
  writing: () => T('Kleal составляет описание…', 'Kleal is writing your summary…', 'Kleal escribe tu resumen…'),
  /** Лист правки сводки: что сейчас, что дописать, и чем это кончилось. */
  sumNow: () => T('Сейчас', 'Now', 'Ahora'),
  sumAdd: () => T('Что добавить', 'What to add', 'Qué añadir'),
  sumAddHint: () => T('Например: ещё я вожу мотоцикл и по субботам играю в падел',
                      'For example: I also ride a motorbike and play padel on Saturdays',
                      'Por ejemplo: también conduzco moto y juego al pádel los sábados'),
  sumFailed: () => T('Не получилось пересобрать. Попробуй ещё раз.',
                     'Could not rewrite it. Try again.',
                     'No se pudo reescribir. Inténtalo de nuevo.'),
  empty: () =>
    T('Kleal опишет тебя здесь по мере знакомства.', 'Kleal will summarise you here as it learns more.', 'Aquí Kleal te resumirá a medida que aprenda más.'),
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

/**
 * @param extra Слова человека, которые он дописал сам в листе правки. Пусто — обычная
 *              пересборка под изменившийся профиль, как её зовёт сторож.
 */
export async function adaptSummary(extra = ''): Promise<boolean> {
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
    const r: any = await buddy.resummary(profileForAttach(), cur, personality, replyLang(), extra);
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
  // A model-proposed label may repeat the grammatical case from the sentence ("в доту" ->
  // "доту"). Known taxonomy keys already have reviewed, nominative labels in the wheel, so those
  // always win. Free-form canonicals still use the server-normalized proposal label.
  const builtInLabel = interestLabel(key);
  const savedLabel = builtInLabel !== key ? builtInLabel : String(label || key).trim() || key;
  set('interests.explicit', [...have, key]);
  set('interests.labels', { ...((p.interests || {}).labels || {}), [key]: savedLabel });
  set('interests.confirmations', { ...((p.interests || {}).confirmations || {}), [key]: token });
  _sentInterests = null;
  return true;
}

export const HUB_ROWS: HubRow[] = [
  {
    id: 'interests', kind: 'screen',
    title: () => T('Интересы', 'Interests', 'Intereses'),
    sub: (p) => {
      const list = interestLabels(explicitInterests(p));
      return list.length ? list.join(' · ') : T('Пока не заполнено', 'Not set yet', 'Aún sin rellenar');
    },
  },
  {
    id: 'personality', kind: 'screen',
    title: () => T('Твоя личность', 'Your personality', 'Tu personalidad'),
    sub: (p) =>
      String(p?.personality || '').trim()
        ? String(p.personality).trim()
        : T('Пройди тест — Kleal опишет, как ты воспринимаешься', 'Take the test and Kleal will describe how you come across', 'Haz la prueba y Kleal describirá cómo te perciben'),
  },
  {
    id: 'safety', kind: 'screen',
    title: () => T('Безопасность и приватность', 'Safety & Privacy', 'Seguridad y privacidad'),
    sub: () => T('Что Kleal может использовать и твои границы', 'What Kleal can use, and your limits', 'Lo que Kleal puede usar y tus límites'),
  },
  {
    id: 'languages', kind: 'sheet',
    title: () => T('Языки', 'Languages', 'Idiomas'),
    sub: (p) => {
      const list = (p?.languages?.comfortable || []).map((k: string) => langPlainName(k, getLang() === 'ru'));
      return list.length ? list.join(' · ') : T('Пока не заполнено', 'Not set yet', 'Aún sin rellenar');
    },
  },
  {
    id: 'location', kind: 'sheet',
    title: () => T('Локация', 'Location', 'Ubicación'),
    sub: (p) => {
      const city = String(p?.city || '').trim();
      const km = p?.geo?.maxDistanceKm;
      const bits = [city, km ? T(`до ${km} км`, `up to ${km} km`, `hasta ${km} km`) : ''].filter(Boolean);
      return bits.length ? bits.join(' · ') : T('Пока не заполнено', 'Not set yet', 'Aún sin rellenar');
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
  title: () => T('Кто ты', 'About you', 'Sobre ti'),
  name: () => T('Имя', 'Name', 'Nombre'),
  /**
   * Имя стоит в шапке чужой переписки и в карточке кандидата, поэтому адрес почты здесь —
   * не опечатка, а утечка. Живой случай был ровно такой: человек ходил по приложению под
   * собственным адресом, и его читали посторонние.
   */
  nameBad: () =>
    T('Так тебя увидят другие. Адрес почты, ссылка или номер именем не будут.',
      'This is what other people see. An email, link or number can’t be a name.', 'Esto es lo que ven otras personas. Un correo, enlace o número no puede ser un nombre.'),
  surname: () => T('Фамилия', 'Surname', 'Apellido'),
  /** Фамилия не обязательна: людям, которые не хотят её называть, нельзя закрывать регистрацию. */
  surnameNote: () =>
    T('Не обязательно. Помогает не спутать двух тёзок в группе.',
      'Optional. Helps tell two people with the same first name apart.', 'Opcional. Ayuda a diferenciar a dos personas con el mismo nombre.'),
  age: () => T('Возраст', 'Age', 'Edad'),
  photo: () => T('Фото', 'Photo', 'Foto'),
  changePhoto: () => T('Сменить фото', 'Change photo', 'Cambia la foto'),
  removePhoto: () => T('Убрать фото', 'Remove photo', 'Eliminar foto'),
  /** Снимок выбран, а подготовить его не вышло. Молчать тут нельзя — человек ждёт фото на экране. */
  photoFailed: () =>
    T('Не получилось подготовить снимок. Попробуй другой.',
      'Could not prepare that photo. Try another one.', 'No se pudo preparar esa foto. Prueba con otra.'),
  nameNote: () =>
    T(
      'Имя видно людям в поиске и в приглашениях.',
      'Your name is what people see in search and invitations.'
    , 'Tu nombre es lo que ven las personas en la búsqueda y en las invitaciones.'),
};

/** Листы правки поверх профиля — кадры со «Accept changes». */
export const SHEETS = {
  languages: () => T('Языки', 'Languages', 'Idiomas'),
  location: () => T('Локация', 'Location', 'Ubicación'),
  accept: () => T('Принять изменения', 'Accept changes', 'Aceptar cambios'),
  search: () => T('Найти язык', 'Find a language', 'Buscar un idioma'),
  nothing: () => T('Ничего не нашлось', 'Nothing found', 'Nada encontrado'),
  /** Языков восемьдесят четыре. Показываем ходовые, остальное — поиском. */
  moreLangs: (n: number) =>
    T(`Ещё ${n} языков — найди поиском`, `${n} more languages — use the search`, `${n} idiomas más: usa la búsqueda`),
  chosen: () => T('Выбрано', 'Selected', 'Seleccionado'),
  close: () => T('Закрыть', 'Close', 'Cerrar'),
};

export const SIGNOUT = {
  label: (hasLogin: boolean) =>
    hasLogin ? T('Выйти из аккаунта', 'Sign out', 'Cerrar sesión') : T('Выйти и начать заново', 'Sign out and start over', 'Cerrar sesión y empezar de nuevo'),
  ask: (hasLogin: boolean) =>
    hasLogin
      ? T(
          'Выйти из аккаунта? Профиль останется на сервере и вернётся при следующем входе.',
          'Sign out? Your profile stays on the server and comes back when you sign in.'
        , '¿Cerrar sesión? Tu perfil permanece en el servidor y vuelve cuando inicies sesión.')
      : T(
          'У этого профиля нет логина, поэтому вернуть его будет нечем — он сотрётся вместе со всем, что собрано на этом телефоне. Выйти?',
          'This profile has no login, so there is nothing to restore it with — it will be erased along with everything collected on this phone. Sign out?'
        , 'Este perfil no tiene inicio de sesión, así que no hay nada con lo que restaurarlo — se eliminará junto con todo lo recopilado en este teléfono. ¿Cerrar sesión?'),
  yes: () => T('Выйти', 'Sign out', 'Cerrar sesión'),
  no: () => T('Отмена', 'Cancel', 'Cancelar'),
  who: (login: string | null) =>
    login ? T(`Вход выполнен как ${login}`, `Signed in as ${login}`, `Iniciado como ${login}`)
          : T('Аккаунт не подключён', 'No account connected', 'No hay cuenta conectada'),
};

export const AVAIL: [string, () => string][] = [
  ['active', () => T('Открыт', 'Open', 'Abrir')],
  ['busy', () => T('Занят', 'Busy', 'Ocupado')],
  ['paused', () => T('Пауза', 'Pause', 'Pausa')],
];

/**
 * «Обновлено сегодня» и далее. Метка приходит из локального времени устройства: в хранилище такой
 * колонки нет, и веб делает ровно так же. Без метки времени строку не рисуем вовсе — это честнее,
 * чем «обновлено сегодня» о тексте, написанном месяц назад.
 */
export function fmtUpdated(ts?: number | null): string {
  if (!ts) return '';
  const d = Math.floor((Date.now() - ts) / 864e5);
  if (d <= 0) return T('Обновлено сегодня', 'Updated today', 'Actualizado hoy');
  if (d === 1) return T('Обновлено вчера', 'Updated yesterday', 'Actualizado ayer');
  if (d < 7) return T(`Обновлено ${d} дн. назад`, `Updated ${d} days ago`, `Actualizado hace ${d} días`);
  const dt = new Date(ts);
  return T(
    'Обновлено ' + dt.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
    'Updated ' + dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }),
    'Actualizado el ' + dt.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
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
    if (r) kv.push([T('Роль', 'Role', 'Rol'), arr(r).map(cap).join(' / ')]);
    if (e) kv.push([T('Опыт', 'Experience', 'Experiencia'), String(e)]);
    if (inList(games.gamesList, name) || /dota|valorant|league|\bcs\b|apex|game/.test(n)) {
      const p = pickBy(games.platformsByGame, name);
      if (p) kv.push([T('Платформа', 'Platform', 'Plataforma'), String(p)]);
      const rk = pickBy(games.rankByGame, name);
      if (rk) kv.push([T('Ранг / уровень', 'Rank / level', 'Ranking / nivel'), String(rk)]);
    }
    if (inList(sport.sportsList, name)) {
      const lv = pickBy(sport.skillLevelBySport, name);
      if (lv) kv.push([T('Уровень', 'Skill level', 'Nivel de habilidad'), cap(String(lv))]);
      const tm = pickBy(sport.favoriteTeams, name) ||
        (Array.isArray(sport.favoriteTeams) ? sport.favoriteTeams.join(', ') : null);
      if (tm) kv.push([T('Команда', 'Team', 'Equipo'), String(tm)]);
    }
    if (/language|spanish|english|french|german|italian|practice/.test(n)) {
      if (langd.targetLanguage) kv.push([T('Язык', 'Language', 'Idioma'), String(langd.targetLanguage)]);
      if (langd.targetLevel) kv.push([T('Уровень', 'Level', 'Nivel'), String(langd.targetLevel)]);
    }
    if (/network|startup|business|career|founder/.test(n)) {
      if (net.industry) kv.push([T('Отрасль', 'Industry', 'Industria'), String(net.industry)]);
      if (net.goal) kv.push([T('Цель', 'Goal', 'Objetivo'), String(net.goal)]);
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
      title: T('Основное', 'Basics', 'Datos básicos'),
      value: [op.gender ? sexLabel(String(op.gender)) : '', op.age].filter(Boolean).join(' · ') || '—',
    });
  }
  if (areas.length || city) {
    basics.push({
      title: T('Локация', 'Location', 'Ubicación'),
      value: [areas.join(', ') || city, km ? T(`до ${km} км`, `Max ${km} km`, `Máx. ${km} km`) : null].filter(Boolean).join(' · '),
    });
  }
  if (langs.length) basics.push({ title: T('Языки', 'Languages', 'Idiomas'), value: langs.join(' · ') });

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

  return { name: op.name || T('Ты', 'You', 'Tú'), verified: !!(op as any).verified, confidence, basics, interests, safety };
}

// ---------------------------------------------------------------- интересы

export const INTERESTS_SCREEN = {
  hint: () =>
    T(
      'Если переключатель включён, Kleal учитывает этот интерес при подборе.',
      'When a toggle is on, Kleal uses that interest for matching.'
    , 'Cuando un interruptor está encendido, Kleal usa ese interés para hacer coincidencias.'),
  summary: (name: string) =>
    T(`Kleal ещё разбирается, что для тебя значит ${name}.`, `Kleal is still learning about your ${name}.`, `Kleal aún está aprendiendo sobre tu ${name}.`),
  emptyTitle: () => T('Пока нет интересов', 'No interests yet', 'Todavía no hay intereses'),
  emptySub: () =>
    T(
      'Расскажи Kleal, чем увлекаешься — и они появятся здесь.',
      "Tell Kleal what you're into and they'll show up here."
    , 'Dile a Kleal lo que te interesa y aparecerán aquí.'),
  add: () => T('Добавить интересы', 'Add interests', 'Añade intereses'),
  remove: () => T('Удалить', 'Remove', 'Eliminar'),
  confLabel: (c: string) =>
    c === 'High' ? T('высокая', 'high', 'alto') : c === 'Medium' ? T('средняя', 'medium', 'medio') : T('низкая', 'low', 'bajo'),
};

// ---------------------------------------------------------------- личность

export const PERSONALITY = {
  title: () => T('Твоя личность', 'Your personality', 'Tu personalidad'),
  takeTest: () => T('Пройти тест от Kleal', 'Take your personality test', 'Haz la prueba de personalidad'),
  empty: () =>
    T(
      'Пройди тест — и Kleal расскажет, как ты воспринимаешься со стороны и с кем тебе легко.',
      'Take the test and Kleal will describe how you come across and who you click with.'
    , 'Haz la prueba y Kleal describirá cómo te perciben y con quién te llevas bien.'),
  editWith: () => T('Изменить с Kleal', 'Edit with Kleal', 'Edita con Kleal'),
  /** Оси теста на самом экране личности: они лежат в профиле, и прятать их от того, про кого они,
   *  незачем. Заодно видно, что тест засчитан, даже когда абзац не собрался. */
  axesTitle: () => T('Ответы теста', 'Your test answers', 'Tus respuestas de prueba'),
  retake: () => T('Пройти тест заново', 'Take the test again', 'Vuelve a hacer la prueba'),
  /** Предложение интересов из истории — GR/профиль. Подтверждает человек, а не приложение. */
  fromStoryTitle: () => T('Из твоей истории', 'From your story', 'Desde tu historia'),
  fromStoryNote: () => T(
    'Матчинг ищет по интересам, а не по тексту. Отметь, что добавить — остальное останется просто историей.',
    'Search runs on interests, not prose. Tap what to add — the rest stays just a story.'
  , 'La búsqueda se basa en intereses, no en prosa. Toca para añadir — el resto es solo una historia.'),
  fromStoryAdd: (n: number) =>
    n === 1 ? T('Добавить 1 интерес', 'Add 1 interest', 'Añade 1 interés') : T(`Добавить ${n}`, `Add ${n}`, `Añadir ${n}`),
  fromStoryAdded: () => T('Добавлено в интересы', 'Added to your interests', 'Añadido a tus intereses'),
  fromStoryNone: () => T('В истории пока не видно занятий — напиши, что ты делаешь и любишь.',
                         'No activities visible in the story yet — write what you do and enjoy.', 'Todavía no hay actividades visibles en la historia — escribe lo que haces y diviértete.'),

  storyCap: () =>
    T(
      'Расскажи историю своей жизни в свободном формате (детство, обучение, интересы, профессия)',
      'Tell your life story in your own words — childhood, studies, interests, work'
    , 'Cuéntanos tu vida con tus propias palabras — infancia, estudios, intereses, trabajo'),
  storyPlaceholder: () =>
    T('Пиши как получится — Kleal сам разберётся.', "Write it however it comes out — Kleal will make sense of it.", 'Escríbelo como te salga — Kleal lo entenderá.'),
  confirm: () => T('Сохранить и закрыть', 'Confirm & Close', 'Confirmar y cerrar'),
  saved: () => T('Сохранено', 'Saved', 'Guardado'),

  /** Явные кнопки под полем истории: применить написанное и увидеть, что из этого вышло. */
  apply: () => T('Сохранить историю', 'Save your story', 'Guarda tu historia'),
  applied: () => T('История сохранена', 'Story saved', 'Historia guardada'),
  rebuild: () => T('Пересобрать сводку Kleal', 'Rebuild Kleal’s summary', 'Vuelve a crear el resumen de Kleal'),
  rebuildNote: () =>
    T(
      'Kleal перечитает профиль вместе с твоей историей и перепишет сводку — ту, что стоит на главной профиля.',
      'Kleal re-reads your profile together with your story and rewrites the summary — the one on your profile home.'
    , 'Kleal vuelve a leer tu perfil junto con tu historia y reescribe el resumen — el que aparece en tu página principal.'),
  rebuiltLabel: () => T('Новая сводка Kleal', 'Your new Kleal summary', 'Tu nuevo resumen de Kleal'),
  rebuildFailed: () =>
    T('Не получилось пересобрать. Попробуй ещё раз.', 'Couldn’t rebuild it. Try again.', 'No se pudo reconstruirlo. Inténtalo de nuevo.'),
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
    scene: () => T('Суббота, ты весь день был среди людей.', 'Saturday, you have been around people all day.', 'Sábado, has estado rodeado de personas todo el día.'),
    q: () => T('Наступает вечер. Что с тобой происходит?', 'Evening comes. What happens to you?', 'Llega la noche. ¿Qué haces tú?'),
    o: [
      () => T('Ещё не наигрался — ищешь, куда поехать дальше', 'Still going — you look for where to head next', 'Aún con ganas — buscas dónde seguir'),
      () => T('Отключаешь телефон и никого не хочешь', 'You switch the phone off and want nobody', 'Apagas el teléfono y no quieres que nadie te moleste'),
      () => T('Хватает сил ровно на одного человека', 'You have exactly one person left in you', 'Tienes exactamente a una persona más en ti'),
    ],
    m: ['energised', 'drained', 'depends'],
  },
  {
    k: 'group',
    q: () => T('Вспомни последний разговор, из которого ты вышел довольным. Сколько вас было?',
               'Think of the last conversation you walked away happy from. How many of you were there?', 'Piensa en la última conversación de la que te fuiste feliz. ¿Cuántos de vosotros estabais ahí?'),
    o: [
      () => T('Двое', 'Two', 'Dos'),
      () => T('Стол на четверых-пятерых', 'A table of four or five', 'Una mesa de cuatro o cinco personas'),
      () => T('Много, и ты был в гуще', 'A lot of people, and you were in the middle of it', 'Mucha gente, y tú estabas en el centro de todo'),
    ],
    m: ['one', 'small', 'crowd'],
  },
  {
    k: 'depth',
    scene: () => T('Полчаса как познакомились, разговор пошёл.', 'Half an hour in, the conversation has caught.', 'Media hora después, la conversación ha cogido ritmo.'),
    q: () => T('О чём вы говорите, когда становится интересно?', 'What are you talking about when it gets good?', '¿De qué habláis cuando os lleváis bien?'),
    o: [
      () => T('О том, о чём обычно не говорят с незнакомыми', 'About things you normally do not say to strangers', 'Sobre cosas que normalmente no dices a desconocidos'),
      () => T('О ерунде, но так, что оба смеётесь', 'About nothing much, but you are both laughing', 'Sobre nada en concreto, pero los dos estáis riéndote'),
      () => T('О деле: кто что делает и как это устроено', 'About the work: who does what and how it is put together', 'Sobre el trabajo: quién hace qué y cómo se organiza'),
    ],
    m: ['deep', 'light', 'practical'],
  },
  {
    k: 'firstMeet',
    q: () => T('Первая встреча удалась. По чему ты это понял?',
               'A first meet went well. How do you know?', 'Una primera quedada fue bien. ¿Cómo lo sabes?'),
    o: [
      () => T('Просидели дольше, чем собирались', 'You stayed longer than you meant to', 'Te quedaste más tiempo del que querías'),
      () => T('Что-то сделали вместе, а не просто поговорили', 'You did something together, not just talked', 'Hiciste algo juntos, no solo hablasteis'),
      () => T('Вокруг что-то происходило, и вы это обсуждали', 'Something was going on around you and you had it to talk about', 'Pasaba algo a tu alrededor y tenías de qué hablar'),
    ],
    m: ['talk', 'doing', 'event'],
  },
  {
    k: 'pace',
    q: () => T('Когда новый человек узнаёт про тебя что-то настоящее?',
               'When does a new person learn something real about you?', '¿Cuándo una persona nueva aprende algo real sobre ti?'),
    o: [
      () => T('Почти сразу — ты не умеешь иначе', 'Almost straight away — you do not know another way', 'Casi de inmediato — no conoces otra manera'),
      () => T('Когда решишь, что ему можно', 'Once you have decided they can be trusted with it', 'Una vez que hayas decidido que pueden confiar en ello'),
      () => T('Когда он расскажет первым', 'Once they have gone first', 'Una vez que ellos hayan ido primero'),
    ],
    m: ['fast', 'slow', 'mirror'],
  },
  {
    k: 'planning',
    scene: () => T('Пятница, шесть вечера, планов нет.', 'Friday, six in the evening, nothing planned.', 'Viernes, seis de la tarde, nada planeado.'),
    q: () => T('Как так вышло?', 'How did that happen?', '¿Cómo ocurrió?'),
    o: [
      () => T('Не вышло — ты договорился ещё в среду', 'It did not — you sorted this out on Wednesday', 'No lo hizo — lo resolviste el miércoles'),
      () => T('Сейчас напишешь троим и куда-нибудь поедешь', 'You are about to message three people and go somewhere', 'Estás a punto de enviar un mensaje a tres personas y reunirte con ellas'),
      () => T('И хорошо: вечер дома тебя устраивает', 'And that is fine — an evening at home suits you', 'Y está bien — una noche en casa te va bien'),
    ],
    m: ['advance', 'spontaneous', 'flexible'],
  },
  {
    k: 'friction',
    scene: () => T('За час до встречи человек пишет: не смогу.', 'An hour before you meet, they message: I cannot make it.', 'Una hora antes de la quedada, te envían un mensaje: No puedo venir.'),
    q: () => T('Что ты делаешь?', 'What do you do?', '¿Qué haces?'),
    o: [
      () => T('Сразу предлагаешь другой день', 'You offer another day right away', 'Ofreces otro día de inmediato'),
      () => T('Отвечаешь «ок» и ждёшь, что предложит он', 'You reply “sure” and wait for them to offer one', 'Tú respondes “seguro” y esperas a que ellos ofrezcan uno'),
      () => T('Ничего. Значит, не сложилось', 'Nothing. It was not meant to happen', 'Nada. No estaba destinado a suceder'),
    ],
    m: ['reschedule', 'wait', 'letgo'],
  },
  {
    k: 'lull',
    scene: () => T('Разговор идёт хорошо, и вдруг оба замолчали.', 'The conversation is going well, and suddenly you both go quiet.', 'La conversación va bien, y de repente ambos se quedan en silencio.'),
    q: () => T('Что происходит внутри?', 'What is going on inside?', '¿Qué está pasando dentro de ti?'),
    o: [
      () => T('Ты уже придумываешь, чем её заполнить', 'You are already thinking of something to fill it with', 'Ya estás pensando en algo con lo que rellenarlo'),
      () => T('Ничего. Пауза — тоже часть разговора', 'Nothing. A pause is part of the conversation too', 'Nada. Una pausa también forma parte de la conversación'),
      () => T('Становится неловко и хочется закруглиться', 'It gets awkward and you want to wrap up', 'Se pone incómodo y quieres terminar'),
    ],
    m: ['fill', 'allow', 'uneasy'],
  },
  {
    k: 'give',
    q: () => T('За что тебя держат те, кто с тобой давно?',
               'What do the people who have stayed keep you around for?', '¿Qué es lo que mantiene a la gente que se queda a tu alrededor?'),
    o: [
      () => T('Ты слушаешь и помнишь', 'You listen, and you remember', 'Escuchas, y te acuerdas'),
      () => T('С тобой смешно', 'You make it funny', 'Haces que sea divertido'),
      () => T('На тебя можно рассчитывать', 'You can be counted on', 'Se puede contar contigo'),
      () => T('Ты вытаскиваешь их из дома', 'You get them out of the house', 'Tú los sacas de casa'),
    ],
    m: ['listen', 'fun', 'reliable', 'instigate'],
  },
  {
    k: 'seek',
    q: () => T('Чего тебе сейчас не хватает?', 'What are you short of right now?', '¿Qué te falta ahora mismo?'),
    o: [
      () => T('Двух-трёх своих людей', 'Two or three people of your own', 'Dos o tres personas tuyas'),
      () => T('Компании под конкретное занятие', 'Company for one specific thing', 'Compañía para algo concreto'),
      () => T('Просто больше жизни вокруг', 'Simply more life around you', 'Sólo más vida a tu alrededor'),
    ],
    m: ['long', 'interest', 'wider'],
  },
  {
    // Незаконченная фраза, а не открытый вопрос. «Что о тебе стоит знать?» человек читает как
    // просьбу презентовать себя и пишет резюме; допиши-фразу отвечают почти всегда конкретным
    // случаем, а модели именно конкретное и нужно.
    k: 'own',
    q: () => T('Последнее. Допиши фразу — как есть, без причёсывания.',
               'Last one. Finish the sentence — as it comes, unpolished.', 'Última. Acaba la frase — como venga, sin pulir.'),
    stem: () => T('Со мной легко, если…', 'I am easy to be around if…', 'Estoy fácil de trato si…'),
    o: [], m: [], free: true,
  },
];

/**
 * Как ось читается человеку. Тест сохраняет токены в профиль, а показать их было негде: экран
 * результата отсутствовал вовсе, и человек видел только абзац от модели. Тест, который что-то
 * узнал и не сказал что, — гадание, а не тест.
 */
export const AXIS_LABEL: Record<string, () => string> = {
  energy: () => T('Люди', 'People', 'Personas'),
  group: () => T('Формат', 'Format', 'Formato'),
  depth: () => T('Разговор', 'Conversation', 'Conversación'),
  firstMeet: () => T('Первая встреча', 'A first meet', 'Una primera quedada'),
  pace: () => T('Открытость', 'Opening up', 'Abriéndose'),
  planning: () => T('Планы', 'Plans', 'Planes'),
  friction: () => T('Когда отменяют', 'When plans fall through', 'Cuando los planes se caen'),
  lull: () => T('Пауза', 'Silence', 'Silencio'),
  give: () => T('Что приносишь', 'What you bring', 'Lo que aportas tú'),
  seek: () => T('Ищешь', 'Looking for', 'Buscando'),
};

export const AXIS_VALUE: Record<string, () => string> = {
  energised: () => T('заряжают', 'charge you up', 'te recargan'),
  drained: () => T('забирают силы', 'take it out of you', 'te agotan'),
  depends: () => T('по одному — да, толпой — нет', 'one at a time, not in a crowd', 'uno a la vez, no en grupo'),
  one: () => T('один на один', 'one to one', 'uno a uno'),
  small: () => T('небольшой стол', 'a small table', 'una mesa pequeña'),
  crowd: () => T('большая компания', 'a big crowd', 'un grupo numeroso'),
  deep: () => T('вглубь', 'goes deep', 'a fondo'),
  light: () => T('легко и смешно', 'light and funny', 'ligero y divertido'),
  practical: () => T('по делу', 'to the point', 'al punto'),
  talk: () => T('просидеть дольше, чем собирались', 'staying longer than planned', 'quedarse más tiempo del planeado'),
  doing: () => T('делать что-то вместе', 'doing something together', 'hacer algo juntos'),
  event: () => T('там, где что-то происходит', 'somewhere things are happening', 'algún lugar donde ocurren cosas'),
  fast: () => T('сразу настоящий', 'real from the start', 'real desde el principio'),
  slow: () => T('когда решишь, что можно', 'once you decide they can be trusted', 'una vez que decides que pueden ser de confianza'),
  mirror: () => T('в ответ на откровенность', 'in answer to theirs', 'en respuesta a la suya'),
  advance: () => T('заранее', 'agreed in advance', 'acordado con antelación'),
  spontaneous: () => T('спонтанно', 'on the spur', 'espontáneo'),
  flexible: () => T('вечер дома тоже вариант', 'an evening in is fine too', 'también está bien una noche en casa'),
  reschedule: () => T('предлагаешь другой день', 'you offer another day', 'tú propones otro día'),
  wait: () => T('ждёшь встречного шага', 'you wait for their move', 'tú esperas a que se muevan'),
  letgo: () => T('отпускаешь', 'you let it go', 'lo dejas ir'),
  fill: () => T('заполняешь', 'you fill it', 'lo llenas tú'),
  allow: () => T('даёшь ей побыть', 'you let it sit', 'lo dejas ahí'),
  uneasy: () => T('становится неловко', 'it makes you uneasy', 'te hace sentir incómodo'),
  listen: () => T('слушаешь и помнишь', 'you listen and remember', 'escuchas y recuerdas'),
  fun: () => T('с тобой смешно', 'you make it funny', 'tú lo haces divertido'),
  reliable: () => T('на тебя можно рассчитывать', 'you can be counted on', 'se puede contar contigo'),
  instigate: () => T('вытаскиваешь из дома', 'you get people out', 'sacas a la gente'),
  long: () => T('своих людей надолго', 'people of your own, long term', 'gente propia, a largo plazo'),
  interest: () => T('компанию под занятие', 'company for one thing', 'compañía para una cosa'),
  wider: () => T('больше жизни вокруг', 'more life around you', 'más vida a tu alrededor'),
};

/** Порядок строк на экране результата — от «как с людьми» к «что делаешь, когда трудно». */
export const AXIS_ORDER = [
  'energy', 'group', 'depth', 'pace', 'firstMeet', 'planning', 'friction', 'lull', 'give', 'seek',
];

export const TEST = {
  title: () => T('Тест от Kleal', 'Your Kleal test', 'Tu prueba en Kleal'),
  of: (i: number, n: number) => T(`Вопрос ${i} из ${n}`, `Question ${i} of ${n}`, `Pregunta ${i} de ${n}`),
  skip: () => T('Пропустить', 'Skip', 'Saltar'),
  placeholder: () => T('Дальше своими словами…', 'Carry on in your own words…', 'Continúa con tus propias palabras...'),
  finish: () => T('Готово', 'Done', 'Hecho'),
  working: () => T('Kleal обдумывает ответы…', 'Kleal is thinking it over…', 'Kleal está pensándolo…'),
  failed: () =>
    T('Не получилось собрать результат. Ответы сохранены — попробуй ещё раз.',
      'Could not put the result together. Your answers are saved — try again.', 'No se pudo crear el resultado. Tus respuestas están guardadas — inténtalo de nuevo.'),

  /** Экран результата. Раньше тест просто закрывался, и человек не видел, что из него вышло. */
  resultTitle: () => T('Вот что получилось', 'Here is what came out', 'Esto es lo que ha salido'),
  axesTitle: () => T('Что Kleal записал', 'What Kleal wrote down', 'Lo que Kleal ha anotado'),
  axesNote: () => T('Это остаётся в профиле и видно только тебе.',
                    'This stays in your profile and only you see it.', 'Esto permanece en tu perfil y solo tú lo ves.'),
  skipped: () => T('Пропущено', 'Skipped', 'Saltado'),
  keep: () => T('Сохранить', 'Keep it', 'Manténlo'),
  again: () => T('Пройти заново', 'Take it again', 'Vuelve a hacerlo'),
  /** Честная строка, когда абзац не собрался, а ответы записались. */
  axesOnly: () =>
    T('Ответы сохранены — абзац Kleal напишет позже.', 'Your answers are saved — Kleal will write the paragraph later.', 'Tus respuestas se han guardado — Kleal escribirá el párrafo más tarde.'),
};

// ---------------------------------------------------------------- безопасность
//
// ЗДЕСЬ БЫЛО 133 СТРОКИ ПЕРЕКЛЮЧАТЕЛЕЙ, И ОНИ НИЧЕГО НЕ ПЕРЕКЛЮЧАЛИ.
//
// Пятнадцать флагов в пяти группах: «не встречаться поздно вечером», «избегать баров», «делиться
// планом с доверенным контактом», «никогда не делать выводов о чувствительном», «не сводить меня с
// теми, кого я могу знать», «показывать меня на карте», «режим знакомств» и другие. Сверка с
// боевым кодом (services/*/app.py, 4 сентября 2026): девять из пятнадцати не читает ни одна
// служба ни в одном месте, ещё три пишет онбординг, но подбор их не смотрит.
//
// Хуже всего была «пауза»: она писалась в `safety.paused`, тогда как жёсткий фильтр подбора
// смотрит на верхнее `paused`, а настоящий механизм паузы живёт в политике приёма
// (`receiving.status`). Главный рычаг безопасности не делал ничего.
//
// Взамен — два экрана над политикой приёма, которую подбор действительно исполняет:
// app/settings/visibility.tsx и app/settings/availability.tsx. Копия к ним в src/settings.ts.
// Тип SafetyFlags и `profileData().safety` оставлены: строку профиля они по-прежнему описывают.

export const langCode = () => getLang();
