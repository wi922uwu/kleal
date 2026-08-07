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
  /** Окно называет затею словами: человек соглашается на конкретное, а не на «создать интент». */
  what: (what: string) => T(`Похоже, ты хочешь «${what}».`, `Looks like you want to “${what}”.`),
  create: () => T('Создать интент', 'Create Intent'),
  keep: () => T('Продолжить разговор', 'Keep chatting'),
  close: () => T('Закрыть', 'Close'),
  /**
   * Ответ на «продолжим общаться». Kleal называет, что он понял, и отдаёт ход человеку: молча
   * закрыть окно значило бы, что распознавание случилось где-то за кадром и обсудить его нельзя.
   */
  keptChatting: (what: string) =>
    T(
      `Слушай, я думал, ты хочешь «${what}». Может, имелось в виду другое — или просто болтаем дальше?`,
      `I thought you wanted to “${what}”. Did you mean something else — or shall we just keep talking?`
    ),
};

/** Как назвать распознанную затею человеку: заголовок от модели, иначе темы, иначе его же слова. */
export function intentLabel(res: any, fallback = ''): string {
  const i = (res && res.intent) || {};
  const title = String(i.title || i.activity || '').trim();
  if (title) return title;
  const topics = Array.isArray(i.topics) ? i.topics.filter(Boolean).map(String) : [];
  return topics.length ? topics.join(', ') : String(fallback || '').trim();
}

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
  /** Тема собрана: дальше человек ставит время, место и компанию руками. */
  ready: () => T('Дальше', 'Next'),
  readyNote: () =>
    T(
      'Время, место и с кем — на следующем шаге, там это выставляется вручную.',
      'When, where and who comes next — you set those by hand.'
    ),
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
