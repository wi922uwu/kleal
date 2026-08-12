/**
 * «Моя активность» — копия и вывод состояний. Борд «My activity · my intents», кадр C.02.
 *
 * ЧЕМ ЭТА ВКЛАДКА ОТЛИЧАЕТСЯ ОТ «СООБЩЕНИЙ», хотя списки похожи до неразличимости.
 *
 * В «Сообщениях» любая строка открывает РАЗГОВОР — там показаны собеседники, сгруппированные по
 * тому, на какой стадии с ними дело. Здесь любая строка открывает САМУ ЗАТЕЮ: интент, план,
 * приглашение. Данные под ними общие, поэтому сборка строк не переписана заново, а взята из
 * src/messages.ts — разные у вкладок только назначение перехода и вид карточки.
 *
 * СОСТОЯНИЙ ИНТЕНТА НА СЕРВЕРЕ НЕТ. Хранится title, свободный объект intent, метки времени и
 * `launched`; поля status в ответе нет вовсе. Три чипа с кадра — «Searching», «N options ready»,
 * «Waiting for N replies» — выводятся здесь, из трёх настоящих признаков: была ли запущена
 * выдача, сколько кандидатов вернул пересчёт и сколько разосланных приглашений ещё без ответа.
 */
import { T, getLang, plural } from './i18n';
import { HOME, splitWhen, planWhere } from './home';
import { intentSummaryText } from './intent';

/** Ключ, которым интент помечает сам себя в отправленном приглашении. См. `pendingFor`. */
export const INTENT_ID_KEY = 'kleal_intent_id';

export const ACT = {
  title: () => T('Моя активность', 'My Activity'),

  tabIntents: () => T('Интенты', 'Intents'),
  tabPlans: () => T('Планы', 'Plans'),
  tabInvites: () => T('Приглашения', 'Invites'),
  tabHistory: () => T('История', 'History'),

  /** Чипы состояния поверх обложки. */
  chipSearching: () => T('Ищем', 'Searching'),
  chipOptions: (n: number) =>
    T(`${n} ${plural(n, 'вариант', 'варианта', 'вариантов')} готово`, `${n} option${n === 1 ? '' : 's'} ready`),
  chipWaiting: (n: number) =>
    T(`Ждём ${n} ${plural(n, 'ответ', 'ответа', 'ответов')}`, `Waiting for ${n} repl${n === 1 ? 'y' : 'ies'}`),

  /** Кнопка карточки. Её надпись — это и есть состояние, сказанное действием. */
  ctaSearching: () => T('Открыть поиск', 'View search'),
  ctaOptions: () => T('Посмотреть варианты', 'Review options'),
  ctaWaiting: () => T('Посмотреть ответы', 'Review responses'),

  /** Строка под названием на странице интента — кадры «States of My Intent page». */
  lineSearching: () => T('Kleal ищет людей рядом', 'Kleal is looking for people nearby'),
  lineOptions: () => T('Выбери, кого позвать', 'Pick who to invite'),
  lineWaiting: () => T('Ответы придут сюда', 'Replies will show up here'),

  edit: () => T('Изменить', 'Edit'),
  lookingNearby: () => T('Ищем людей рядом', 'Looking for nearby people'),

  emptyIntents: () => T('Затей пока нет', 'No intents yet'),
  emptyIntentsNote: () =>
    T(
      'Заведи затею — Kleal начнёт искать людей и покажет их здесь.',
      'Start something and Kleal will look for people, then show them here.'
    ),
  emptyPlans: () => T('Встреч пока нет', 'No plans yet'),
  emptyInvites: () => T('Приглашений нет', 'No invites'),
  emptyHistory: () => T('Здесь будет прошедшее', 'Past meetups will land here'),
  create: () => T('Создать интент', 'Create intent'),

  /**
   * Удаление затеи. «Выйти» из своей затеи нельзя — она твоя; из неё можно только уйти совсем,
   * и тогда её не должно остаться нигде: ни в списке, ни в поиске. Поэтому слово прямое.
   */
  removeTitle: () => T('Удалить затею?', 'Delete this intent?'),
  removeNote: () => T(
    'Она исчезнет из списка, и Kleal перестанет искать по ней людей. Уже отправленные приглашения останутся у тех, кому ты их послал.',
    'It disappears from the list and Kleal stops looking for people. Invites you already sent stay with the people you sent them to.'
  ),
  remove: () => T('Удалить', 'Delete'),
  keep: () => T('Оставить', 'Keep it'),
  removeFailed: () => T('Не удалось удалить. Попробуй ещё раз.', 'Could not delete. Try again.'),

  loadFailed: () => T('Не удалось загрузить.', 'Could not load.'),
  retry: () => T('Повторить', 'Retry'),
  /** Пересчёт одного интента упал: карточку не прячем — интент существует, просто без кандидатов. */
  rankFailed: () => T('Поиск по этой затее сейчас не отвечает', 'Search for this one is not responding'),
};

export type IntentState = 'searching' | 'options' | 'waiting';

/** Строка интента, как её отдаёт /api/agent/intents. */
export type IntentRow = {
  id: string;
  title?: string;
  intent?: any;
  created?: number;
  updated?: number;
  launched?: number | null;
  candidates?: any[];
  error?: string;
};

/**
 * Сколько разосланных по этой затее приглашений ещё без ответа.
 *
 * Сервер связи «заявка → интент» не хранит: propose кладёт в строку КОПИЮ объекта интента, но не
 * его id. Поэтому связь делает клиент — при отправке приглашения он помечает объект своим id
 * (`INTENT_ID_KEY`), и здесь метка находится обратно. Это точное совпадение, а не догадка по
 * теме и названию: две затеи с одинаковой темой не склеятся.
 *
 * Приглашения, отправленные до появления метки, сюда не попадут — и это честнее, чем считать их
 * приблизительно.
 */
export function pendingFor(intentId: string, outbox: any[]): number {
  const id = String(intentId || '');
  if (!id) return 0;
  return (outbox || []).filter(
    (r) => r && r.status === 'pending' && String(r.intent?.[INTENT_ID_KEY] || '') === id
  ).length;
}

/**
 * Состояние карточки. Порядок веток — не оформление, а смысл.
 *
 * Приглашения важнее вариантов: как только человек кого-то позвал, живой вопрос у него один —
 * ответят или нет. Показать в этот момент «3 варианта готовы» значит отвечать не на тот вопрос.
 */
export function intentState(row: IntentRow, outbox: any[]): IntentState {
  if (pendingFor(row.id, outbox) > 0) return 'waiting';
  if ((row.candidates || []).length > 0) return 'options';
  return 'searching';
}

export function chipLabel(state: IntentState, row: IntentRow, outbox: any[]): string {
  if (state === 'waiting') return ACT.chipWaiting(pendingFor(row.id, outbox));
  if (state === 'options') return ACT.chipOptions((row.candidates || []).length);
  return ACT.chipSearching();
}

/**
 * Тон чипа. На борде у трёх состояний три разных цвета, и это не украшение: карточки лежат
 * стопкой, и человек читает их состояние ЦВЕТОМ раньше, чем словом.
 *   ищем        — тёплый: работа идёт, от человека ничего не требуется;
 *   варианты    — зелёный: можно действовать, и это лучшая новость из трёх;
 *   ждём ответы — синий: мяч не на нашей стороне.
 * Фиолетового с борда в токенах нет, а заводить его ради одного чипа — плодить палитру;
 * «ждём» и «сведения» — одна и та же по смыслу спокойная синева.
 */
export const CHIP_TONE: Record<IntentState, 'warn' | 'success' | 'info'> = {
  searching: 'warn',
  options: 'success',
  waiting: 'info',
};

export function ctaLabel(state: IntentState): string {
  return state === 'waiting' ? ACT.ctaWaiting() : state === 'options' ? ACT.ctaOptions() : ACT.ctaSearching();
}

export function stateLine(state: IntentState): string {
  return state === 'waiting' ? ACT.lineWaiting() : state === 'options' ? ACT.lineOptions() : ACT.lineSearching();
}

/**
 * Название затеи для карточки. Сервер хранит `title` отдельно, но у старых интентов его нет —
 * тогда берём темы, а если и их нет, показываем прочерк, а не пустое место: карточка без имени
 * читается как поломка загрузки.
 */
export function intentTitle(row: IntentRow): string {
  const t = String(row.title || '').trim();
  if (t) return t;
  const topics = row.intent?.topics;
  if (Array.isArray(topics) && topics.length) return topics.join(', ');
  return T('Без названия', 'Untitled');
}

/** Две строки под названием: когда и где. Разбор общий с главной — там же и правило про километры. */
export function intentWhen(row: IntentRow): { date: string; time: string } {
  return splitWhen(String(row.intent?.when || ''));
}

export function intentWhere(row: IntentRow, myArea = ''): string {
  const i = row.intent || {};
  const area = String(i.area || i.district || i.address || '').trim();
  return planWhere(area, '', myArea);
}

/** Паспорт затеи на её странице — кадры C.02a–C.02d, левая колонка. */
export function intentFacts(row: IntentRow): { label: string; value: string }[] {
  const i = row.intent || {};
  const ru = getLang() === 'ru';
  const out: { label: string; value: string }[] = [];
  const push = (label: string, value: any) => {
    const v = Array.isArray(value) ? value.join(', ') : String(value || '').trim();
    if (v) out.push({ label, value: v });
  };
  push(T('Формат', 'Mode'), i.mode === 'online' ? T('Онлайн', 'Online')
    : i.mode === 'hybrid' ? T('Гибрид', 'Hybrid')
    : i.mode === 'offline' ? T('Вживую', 'Offline') : '');
  push(T('Состав', 'Format'), i.format === 'group' ? T('Группа', 'Group')
    : i.format === '1:1' ? T('Один на один', '1:1') : '');
  push(T('Тема', 'Category'), i.topics);
  /**
   * Пол и возраст читаются ТЕМИ ЖЕ ключами, какими их пишет мастер: `sex` из SEXES («Male» /
   * «Female» / «Any», с большой буквы) и `minAge` / `maxAge`. Сравнение в нижнем регистре и
   * `min_age` через подчёркивание — ровно то, на чём паспорт затеи показывал «Аудитория: Любой»
   * при сохранённых «Female, 22–34»: поля были на месте, а прочитать их было нечем.
   */
  const sex = i.sex === 'Female' ? T('Женщины', 'Female')
    : i.sex === 'Male' ? T('Мужчины', 'Male')
    : T('Любой', 'Any is fine');
  const age = i.minAge && i.maxAge ? `${i.minAge}–${i.maxAge}` : '';
  push(T('Аудитория', 'Audience'), [sex, age].filter(Boolean).join(ru ? ', ' : ', '));
  return out;
}

/**
 * СВОДКА KLEAL. Своя, если человек её правил; иначе — собранная из фактов затеи.
 *
 * Пустого места здесь быть не должно: на борде в этом блоке всегда есть текст, и он появляется
 * сам — ровно как на сводке перед поиском (O.10) и в профиле. Человек не пишет её с нуля, он
 * правит уже написанное, и лист правки поэтому открывается заполненным.
 *
 * Собирает её тот же `intentSummaryText`, что и мастер: две разные сводки об одной затее
 * разошлись бы на первой правке шаблона.
 */
export function intentSummary(row: IntentRow): string {
  const own = String(row.intent?.summary || '').trim();
  if (own) return own;
  const i = row.intent || {};
  const topics = Array.isArray(i.topics) ? i.topics.join(', ') : '';
  return intentSummaryText({
    topic: String(row.title || topics || '').trim(),
    size: i.format === 'group' ? 'group' : undefined,
    sex: i.sex,
    minAge: Number(i.minAge) || 18,
    maxAge: Number(i.maxAge) || 35,
    dateKey: String(i.dateKey || ''),
    minutes: Number(i.minutes) || 20 * 60,
  });
}

/**
 * Карточка ПЛАНА — тот же блок, что у затеи, а не строка переписки.
 *
 * Строкой с аватаркой план выглядел как чат, и это была неправда о том, куда ведёт нажатие: в
 * «Сообщениях» такая строка открывает разговор, здесь — саму встречу. Одинаковый вид у разных
 * вещей — худший сорт вранья интерфейса: он не ошибается в словах, он ошибается в ожидании.
 */
export type PlanCard = {
  key: string;
  title: string;
  date: string;
  time: string;
  where: string;
  chip: string;
  tone: 'warn' | 'success' | 'info';
  faces: string[];
  gid?: string;
  id?: string;
  who?: string;
};

export const PLAN_STATE = {
  proposed: () => T('Согласовывают', 'Being agreed'),
  confirmed: () => T('Подтверждён', 'Confirmed'),
  locked: () => T('Закреплён', 'Locked'),
  below: () => T('На паузе', 'On hold'),
  done: () => T('Прошло', 'Ended'),
  cancelled: () => T('Отменён', 'Called off'),
  open: () => T('Открыть план', 'Open the plan'),
};

/** Один разбор на парные и групповые планы: для человека это одна и та же встреча. */
export function planCard(p: any, me = ''): PlanCard {
  const st = String(p?.state || '');
  const tone: PlanCard['tone'] =
    st === 'confirmed' || st === 'locked' ? 'success'
    : st === 'below_quorum' || st === 'cancelled' ? 'info' : 'warn';
  const chip =
    st === 'confirmed' ? PLAN_STATE.confirmed()
    : st === 'locked' ? PLAN_STATE.locked()
    : st === 'below_quorum' ? PLAN_STATE.below()
    : st === 'done' ? PLAN_STATE.done()
    : st === 'cancelled' ? PLAN_STATE.cancelled()
    : PLAN_STATE.proposed();
  const who = (p?.participants || [])
    .map((x: any) => String(x?.name || ''))
    .filter((n: string) => n && n.toLowerCase() !== String(me).toLowerCase());
  const when = splitWhen(String(p?.when || ''));
  return {
    key: (p?.gid ? 'gp:' : 'mp:') + String(p?.id || p?.gid || ''),
    title: String(p?.title || who[0] || T('Встреча', 'Meetup')).trim(),
    date: when.date,
    time: when.time,
    where: planWhere(String(p?.venue || p?.district || p?.place || '').trim(), '', ''),
    chip,
    tone,
    faces: (p?.participants || []).map((x: any) => String(x?.photo || '')).filter(Boolean).slice(0, 3),
    gid: p?.gid ? String(p.gid) : undefined,
    id: p?.id ? String(p.id) : undefined,
    who: who[0],
  };
}

/** Счётчик на сегменте «Приглашения» — столько же, сколько строк в стопке на главной. */
export const inviteBadge = (invites: any[]) => (invites || []).length;

/** Подпись «N идут» на карточке берём из главной: согласование там уже написано. */
export const goingLabel = HOME.going;
