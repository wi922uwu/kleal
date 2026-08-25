/**
 * Разговор с Бадди и создание интента — кадры O.01–O.04.
 *
 * ЭТО UX-КАРКАС. Вид поверх него будет натянут отдельно, поэтому здесь нет ни одного стиля: только
 * текст, правила и разбор ответов сервера. Всё, что видно глазом, живёт в app/buddy.tsx и
 * app/create.tsx и держится на токенах темы — заменить оформление можно, не трогая эти правила.
 *
 * Устройство потока:
 *
 *  O.02  Бадди — просто собеседник. Написанное ему НЕ превращается в интент само по себе.
 *  O.03  Интент заводится двумя путями, и оба ведут в одно и то же окно выбора:
 *          — кнопка «Создать» в правом верхнем углу;
 *          — сказанное словами, в котором сервер распознал план (поле `intent` в ответе /chat).
 *        Окно спрашивает, что делать дальше: создавать интент или продолжить разговор. Само по
 *        себе распознавание ничего не запускает — решает человек.
 *  O.04  Создание интента — ОТДЕЛЬНЫЙ разговор. Он начинается с вариантов, собранных по профилю,
 *        и уточняет только ТЕМУ: два-три вопроса про суть затеи. Время, место, пол и размер
 *        компании тут не спрашиваются намеренно — это ставится руками на следующих экранах.
 */
import { T } from './i18n';
import { topicAcc } from './names';

export const BUDDY = {
  title: () => T('Kleal', 'Kleal'),
  create: () => T('Создать', 'Create'),
  placeholder: () => T('Сообщение…', 'Message…'),
  /** Первая реплика, когда человек пришёл без текста. */
  hello: (name: string) =>
    name ? T(`Привет, ${name}. О чём поговорим?`, `Hey ${name}. What's on your mind?`)
         : T('Привет. О чём поговорим?', "Hey. What's on your mind?"),
  offline: () => T('Связь пропала. Повторишь?', 'I lost the connection. Say that again?'),
};

/** Всплывающее окно O.03. Появляется и по кнопке, и по распознанному триггеру — оно одно. */
export const SHEET = {
  title: () => T('С чего начнём?', 'Get started'),
  create: () => T('Создать интент', 'Create Intent'),
  keep: () => T('Продолжить разговор', 'Keep chatting'),
  close: () => T('Закрыть', 'Close'),
};

/**
 * Что именно, по мнению Kleal, человек затевает — ФРАЗОЙ, а не подписью под карточкой.
 *
 * Раньше окно говорило «Похоже, ты хочешь «Jesus — разговор».»: в кавычки подставлялся готовый
 * заголовок карточки, а он существительное с суффиксом, и после «ты хочешь» получалась не речь, а
 * ярлык. Сервер теперь отдаёт предмет и роль по отдельности (intent.subject, intent.role), и фраза
 * собирается здесь — по-русски глаголом, как человек и сказал бы.
 *
 * Предмета нет (сервер не смог назвать тему) — говорим общо, но по-прежнему предложением.
 */
export function intentPhrase(res: any, fallback = ''): string {
  const i = (res && res.intent) || {};
  const role = String(i.role || '').toLowerCase();
  const subject = String(i.subject || '').trim()
    || String(fallback || '').trim();
  if (!subject) {
    return role === 'discuss' ? T('поговорить с кем-нибудь', 'to talk to someone')
         : role === 'watch' ? T('посмотреть что-нибудь вместе', 'to watch something together')
         : T('с кем-нибудь встретиться', 'to meet someone');
  }
  // Винительный для русской темы, латиница как есть — см. topicAcc.
  const s = topicAcc(subject);
  const en = subject.toLowerCase();
  switch (role) {
    case 'discuss':  return T(`поговорить про ${s}`, `to talk about ${en}`);
    case 'watch':    return T(`посмотреть ${s} с кем-нибудь`, `to watch ${en} with someone`);
    case 'practise': return T(`попрактиковать ${s} с кем-нибудь`, `to practise ${en} with someone`);
    default:         return T(`найти компанию: ${subject}`, `to find someone for ${en}`);
  }
}

/** «Похоже, ты хочешь …» — предложение целиком, с точкой. */
export const sheetWhat = (phrase: string) =>
  T(`Похоже, ты хочешь ${phrase}.`, `Looks like you want ${phrase}.`);

/** Ответ на «продолжим общаться»: Kleal называет, что понял, и отдаёт ход человеку. */
export const sheetKept = (phrase: string) =>
  T(
    `Слушай, я думал, ты хочешь ${phrase}. Может, имелось в виду другое — или просто болтаем дальше?`,
    `I thought you wanted ${phrase}. Did you mean something else — or shall we just keep talking?`
  );

/** Как назвать распознанную затею КАРТОЧКОЙ — заголовок для экранов, где нужна подпись, а не речь. */
export function intentLabel(res: any, fallback = ''): string {
  const i = (res && res.intent) || {};
  const title = String(i.title || i.activity || '').trim();
  if (title) return title;
  const topics = Array.isArray(i.topics) ? i.topics.filter(Boolean).map(String) : [];
  return topics.length ? topics.join(', ') : String(fallback || '').trim();
}

/**
 * Что написано, пока агент думает.
 *
 * ТРИ ШАГА, И ОНИ НЕ ПОВТОРЯЮТСЯ. «Слушаю» — пока разбирает сказанное, «Собираю» — пока строит
 * затею, «Почти» — когда ждать уже дольше обычного. По кругу не крутятся: вернувшееся начало
 * означало бы, что всё пошло заново, а это неправда.
 *
 * СРОКОВ НЕ ОБЕЩАЕМ. «Ещё пару секунд» звучит вежливо ровно до третьей секунды, после чего
 * читается как враньё, — а сколько на самом деле займёт ответ модели, не знает никто.
 */
export const THINKING = () => [
  T('Слушаю', 'Listening'),
  T('Собираю затею', 'Putting it together'),
  T('Почти', 'Almost there'),
];

export const CREATE = {
  title: () => T('Все интенты', 'All intents'),
  ask: () => T('Что хочешь сделать?', 'What do you want to do?'),
  sub: () =>
    T(
      'Без сложностей — кофе, партия, игра, прогулка или просто «не хочу сидеть дома».',
      'Keep it simple — coffee, a match, a game, a walk, or just “don’t feel like staying in.”'
    ),
  suggestions: () => T('Варианты', 'Suggestions'),
  choose: () => T('Выбери из предложенного', 'Choose from the suggested options'),
  regenerate: () => T('Ещё варианты', 'Regenerate'),
  empty: () =>
    T('Вариантов пока нет — напиши своими словами.', 'No suggestions yet — say it in your own words.'),
  /**
   * Тема собрана — кнопка под сводкой.
   *
   * НА НЕЙ НЕТ СЛОВА «ИНТЕНТ». Оно внутреннее: человеку приходится его переводить ровно в тот
   * момент, когда от него ждут одного движения, а не понимания устройства системы. Осталось само
   * движение. Уточнил детали ещё раз — снова сводка и снова эта кнопка.
   *
   * Слово «интент» осталось там, где оно называет РАЗДЕЛ, а не действие: «Все интенты» в шапке,
   * вкладка, история. Там оно уже знакомо по названию места, и переводить его не нужно.
   */
  ready: () => T('Нажми', 'Tap'),
  /** Заголовок сводки над кнопкой: что именно сейчас будет создано. */
  summaryLabel: () => T('Вот что получилось', 'Here is what we have'),
  readyNote: () =>
    T(
      'Время, место и с кем — на следующем шаге, там это выставляется вручную.',
      'When, where and who comes next — you set those by hand.'
    ),
  /** Разбор правок в развёрнутой сводке: уточнение вслепую — это уточнение без обратной связи. */
  changed: () => T('Что изменилось', 'What changed'),
  wasCalled: (was: string) => T(`Было: ${was}`, `Was: ${was}`),
  added: (list: string) => T(`Добавилось: ${list}`, `Added: ${list}`),
  dropped: (list: string) => T(`Ушло: ${list}`, `Dropped: ${list}`),
};

/**
 * Распознал ли сервер в сказанном план.
 *
 * Единственный признак — поле `intent` в ответе /api/buddy/chat. Своих regexp по словам вроде
 * «хочу» здесь намеренно нет: «хочу спать» и «хочу понять, как это работает» ими ловятся тоже, и
 * окно выскакивало бы посреди обычного разговора.
 */
export function looksLikeIntent(res: any): boolean {
  const i = res && res.intent;
  if (!i || typeof i !== 'object') return false;
  const topics = Array.isArray(i.topics) ? i.topics.filter(Boolean) : [];
  return topics.length > 0 || !!i.activity || !!i.title;
}

/**
 * Из ответа построителя нужны ДВЕ РАЗНЫЕ вещи, и путать их нельзя.
 *
 *   intent.topics — ключи для поиска, всегда английские: ["coffee", "work"].
 *   intent.title  — подпись для человека, на его языке: «Кофе — разговор».
 *
 * Это не придирка к именам. Матчинг сравнивает темы БУКВАЛЬНО, и «Кофе — разговор» не совпадает
 * ни с одним человеком в базе: запрос возвращает не людей, а восемь «замен» с пометкой fallback.
 * Проверено на стенде — ключ coffee даёт 8 настоящих карточек, та же тема заголовком даёт 8 замен.
 * Промпт построителя пишет об этом прямо: «activity, time, format стоят в ENGLISH, потому что
 * фильтрация и матчинг понимают только английский».
 */

/** Ключи для поиска. Пусто — построитель ничего не извлёк, и звать матчинг темами незачем. */
export function topicsOf(res: any): string[] {
  const i = (res && res.intent) || {};
  const topics = Array.isArray(i.topics) ? i.topics.map(String).filter(Boolean) : [];
  if (topics.length) return topics;
  // Запасной путь: у построителя есть и плоское поле activity — оно тоже английское.
  const act = String(i.activity || res?.activity || '').trim();
  return act ? [act] : [];
}

/** Подпись для человека: заголовок, а без него — сказанное им самим. Никогда не идёт в поиск. */
export function titleOf(res: any, fallback = ''): string {
  const i = (res && res.intent) || {};
  return String(i.title || i.activity || res?.activity || fallback).trim();
}

export type Turn = { role: string; content: string };

/**
 * История разговора, которую создание интента получает вместе с темой.
 *
 * Без неё построитель видел одну последнюю фразу — а она сплошь и рядом ссылается назад: «я хочу
 * поговорить с кем-то ОБ ЭТОМ». Что такое «это», знает только предыдущий разговор, и агент честно
 * переспрашивал «о чём хочется поговорить?», забыв всё, что человек ему только что рассказал.
 *
 * Сервер к такому готов: intent_build распознаёт отсылку назад и достаёт предмет из истории. Ему
 * нужно только эту историю дать.
 *
 * Режется, потому что едет параметром маршрута: восемь последних реплик по 400 символов хватает,
 * чтобы «это» разрешилось, и не превращает переход в километровую ссылку.
 */
export function packHistory(turns: Turn[]): string {
  const tail = (turns || []).slice(-8).map((t) => ({
    role: String(t.role || 'user'),
    content: String(t.content || '').slice(0, 400),
  }));
  return tail.length ? JSON.stringify(tail) : '';
}

export function unpackHistory(raw: unknown): Turn[] {
  try {
    const v = JSON.parse(String(raw || '[]'));
    return Array.isArray(v) ? v.filter((t) => t && t.content) : [];
  } catch {
    return [];
  }
}
