/**
 * Кандидаты и приглашение — кадры O.12 (список), O.13 (полная карточка), O.14 (окно «Invite …?»).
 *
 * UX-каркас: копия и разбор данных здесь, вид в app/results.tsx и app/candidate.tsx.
 *
 * Честность против кадра. На борде у карточки есть занятие («Language teacher · native Spanish»)
 * и город («London») — в данных кандидата НЕТ ни занятия, ни города: ранжирование отдаёт интересы,
 * языки не всегда, расстояние в км и причины совпадения. Показывается то, что есть: вместо занятия
 * — вайб или первый интерес, вместо города — километры. Выдумывать профессию человеку нельзя —
 * это карточка живого человека, а не макет.
 */
import { T } from './i18n';
import { acc, dat, gen, ins } from './names';

export const CANDS = {
  bestBadge: () => T('Лучший мэтч', 'Best match'),
  matchBadge: () => T('Мэтч', 'Match'),
  summaryLabel: () => T('Сводка Kleal:', 'Kleal summary:'),
  invite: () => T('Пригласить', 'Invite'),
  invited: () => T('Приглашение отправлено', 'Invite sent'),
  /** O.15: состояние карточки после отправки — две кнопки. */
  invitedShort: () => T('Отправлено', 'Invited'),
  cancel: () => T('Отменить', 'Cancel'),
  cancelFailed: () => T('Не получилось отменить. Попробуй ещё раз.', 'Couldn’t cancel. Try again.'),
  inviteFailed: () => T('Не отправилось. Попробуй ещё раз.', 'It didn’t send. Try again.'),

  /** Приписка приватности с кадра O.13, дословно. */
  privacyNote: () =>
    T(
      'Твой профиль видят только люди, которых предложил твой агент. Ты этим управляешь.',
      'Only people your agent recommended can see your profile. You’re in control.'
    ),

  /** Окно O.14. Текст с кадра; по-английски нейтральное they вместо she — имя бывает любым. */
  sheetTitle: (name: string) => T(`Пригласить ${acc(name)}?`, `Invite ${name}?`),
  sheetBody: (name: string) =>
    T(
      `${name} увидит твой интент и твой профиль. Если согласится — откроется чат; на бесплатном тарифе это единственный чат для этого интента.`,
      'They see your intent and your profile. If they join, a chat opens — on the free plan that is the one chat you get for this intent.'
    ),
  send: () => T('Отправить приглашение', 'Send the invite'),
  notYet: () => T('Пока нет', 'Not yet'),
};

/** Поля карточки, которые реально приходят из /api/agent/match. Всё остальное — не наше. */
export type Cand = {
  name?: string;
  age?: number;
  km?: number | null;
  photo?: string;
  vibe?: string;
  verified?: boolean;
  band?: string;
  band_ru?: string;
  band_en?: string;
  note?: string;
  why?: string;
  interests?: string[];
  reasons?: string[];
  reasons_ru?: string[];
  reasons_en?: string[];
  readiness_ru?: string;
  readiness_en?: string;
  profile_view?: any;
};

/** Подзаголовок карточки: вайб, а без него — первые интересы. Занятия в данных нет (см. шапку). */
export function candSubtitle(c: Cand, ru: boolean): string {
  const vibe = String(c.vibe || '').trim();
  if (vibe) return vibe;
  const ints = (c.interests || []).slice(0, 2).map(String);
  if (ints.length) return ints.map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(' · ');
  return String((ru ? c.band_ru : c.band_en) || '');
}

/**
 * Строка с меткой места: километры, когда они посчитаны. Города у кандидата нет.
 *
 * Один знак после запятой ВСЕГДА — иначе на одной карточке рядом стоят «0 km» под именем и
 * «рядом (0.0 km)» в сводке причин: ранжирование округляет само, а шаблон печатал число как есть.
 */
export function candWhere(c: Cand): string {
  return typeof c.km === 'number' && isFinite(c.km) ? `${c.km.toFixed(1)} km` : '';
}

/**
 * «Сводка Kleal» на карточке — причины совпадения словами. Их пишет ранжирование, не мы.
 *
 * Одно исправление на выходе: тему в причине ранжирование называет служебной формой — без
 * пробелов, как оно её сравнивает («настольныеигры», «boardgames»). Читателю это выглядит
 * опечаткой, поэтому склеенное слово подменяется тем, которое написал сам человек: интересы
 * кандидата приехали в этой же карточке, сверять есть с чем. Не нашли пары — оставляем как есть,
 * выдумывать написание нельзя.
 */
export function candSummary(c: Cand, ru: boolean): string {
  const reasons = (ru ? c.reasons_ru : c.reasons_en) || c.reasons || [];
  const glue = (s: string) => s.toLowerCase().replace(/\s+/g, '');
  const say = new Map((c.interests || []).map((i) => [glue(String(i)), String(i)]));
  // Подменяем только те слова, для которых у кандидата ЕСТЬ пара с пробелами: say собран из его
  // интересов, и промах оставляет слово нетронутым. Слов короче шести букв не трогаем — склеек
  // такой длины не бывает, а риск случайного совпадения выше.
  const human = (r: string) =>
    r.replace(/[\p{L}\p{N}]{6,}/gu, (w) => say.get(w.toLowerCase()) || w);
  const bits = reasons.filter(Boolean).map((r) => human(String(r)));
  if (bits.length) {
    const line = bits.join(', ');
    return line.charAt(0).toUpperCase() + line.slice(1) + '.';
  }
  return String(c.why || c.note || '');
}

/**
 * Лист «Изменить условия поиска» — кадр O.11a. Показывается, когда точных совпадений нет:
 * человек сам решает, чем поступиться — полом, возрастом или расстоянием.
 *
 * Его открывают, когда никого не нашлось, — значит каждая строчка здесь должна уметь
 * УБИРАТЬ условие, а не только менять его. Отсюда «Любой» у возраста и «Не важно» у пола: без них
 * лист умел лишь переставить рамку, но не снять её, и «Начать поиск» с нетронутыми значениями
 * сужал выдачу вместо того, чтобы расширить.
 *
 * Гибкости по времени здесь больше нет. Матчинг поля `timeFlexHours` не читает нигде — это был
 * ползунок, который ничего не менял; вместо него расстояние, которое читается (гейт радиуса).
 */
export const PREFS = {
  noMatches: () => T('Точных совпадений пока нет', 'No exact matches yet'),
  title: () => T('Изменить условия поиска', 'Change search preferences'),
  lead: () => T('Чем меньше условий, тем больше людей. Сними то, что не принципиально.',
                'The fewer the conditions, the more people. Drop whatever is not essential.'),
  sex: () => T('Пол', 'Sex'),
  age: () => T('Возраст', 'Age'),
  anyAge: () => T('Любой', 'Any'),
  ageFrom: () => T('Не моложе', 'From'),
  ageTo: () => T('Не старше', 'To'),
  dist: () => T('Расстояние', 'Distance'),
  distVal: (km: number) => T(`до ${km} км`, `within ${km} km`),
  start: () => T('Начать поиск', 'Start search'),
  cancel: () => T('Отмена', 'Cancel'),
  /** Что в итоге ушло в поиск. Ступень лестницы §12 называет себя вслух — этот лист молчал. */
  applied: (conds: string) => T(`Ищу по условиям: ${conds}.`, `Searching with: ${conds}.`),
  anySex: () => T('любой пол', 'any sex'),
  ageAny: () => T('любой возраст', 'any age'),
  ageBand: (lo: number, hi: number) => T(`возраст ${lo}–${hi}`, `age ${lo}–${hi}`),
};

/**
 * Лист «Profile options» — кадр O.13b.
 *
 * У «Не интересно» и «Заблокировать» есть 4-секундный обратный отсчёт с отменой — это НА БОРДЕ
 * (аннотация кадра), не выдумка: оба действия меняют, кого человек увидит, и случайное нажатие
 * должно быть обратимым, пока не поздно.
 */
export const OPTIONS = {
  title: () => T('Действия с профилем', 'Profile options'),
  notInterested: () => T('Не интересно', 'Not interested'),
  report: () => T('Пожаловаться на профиль', 'Report profile'),
  block: (name: string) => T(`Заблокировать ${acc(name)}`, `Block ${name}`),
  cancel: () => T('Отмена', 'Cancel'),
  /** Строка отсчёта: действие названо, секунды идут, отмена в одно касание. */
  pending: (what: string, n: number) => T(`${what} через ${n}…`, `${what} in ${n}…`),
  undo: () => T('Отменить', 'Undo'),
  reportSent: () => T('Жалоба отправлена. Спасибо — её посмотрят.', 'Report sent. Thank you — it will be reviewed.'),
  failed: () => T('Не получилось. Попробуй ещё раз.', 'That didn’t work. Try again.'),
};

/** Причины жалобы — словарь сервера (REPORT_REASONS). Подписи локальные, ключи его. */
/**
 * MSG.22 — потолок открытых приглашений. Правило КЛИЕНТСКОЕ: сервер шлёт сколько угодно, и когда
 * потолок станет тарифом, проверку надо перенести туда — иначе любой другой клиент её обходит.
 */
export const CAP = {
  limit: 3,
  title: (n: number) => T(`Уже ${n} открытых приглашения`, `${n} open invites already`),
  note: () =>
    T(
      'Kleal держит не больше трёх разом, чтобы никто не получал веер заявок. Отмени одно или дождись ответа — Plus поднимает потолок до пяти.',
      'Kleal holds them at three so nobody gets a fan-out of requests. Cancel one, or wait for an answer — Plus raises it to five.'
    ),
  cancelOne: () => T('Отменить одно', 'Cancel one instead'),
  withdraw: () => T('Отозвать', 'Withdraw'),
};

export const REPORT_REASONS: [string, string, string][] = [
  ['fake', 'Фейковый профиль', 'Fake profile'],
  ['harassment', 'Оскорбления или преследование', 'Harassment'],
  ['spam', 'Спам', 'Spam'],
  ['unsafe', 'Небезопасное поведение', 'Unsafe behaviour'],
  ['underage', 'Похоже, несовершеннолетний', 'Looks underage'],
  ['other', 'Другое', 'Other'],
];
