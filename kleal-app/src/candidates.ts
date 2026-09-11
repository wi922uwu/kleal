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
import { T, getLang } from './i18n';
import { acc, dat, gen, ins } from './names';
import { interestLabels } from './interest-label';

export const CANDS = {
  bestBadge: () => T('Лучший мэтч', 'Best match', 'Mejor coincidencia'),
  matchBadge: () => T('Мэтч', 'Match', 'Coincidencia'),
  summaryLabel: () => T('Сводка Kleal:', 'Kleal summary:', 'Resumen de Kleal:'),
  /**
   * O.13 — языки на карточке. Их не было ни строкой, ни значком, хотя приложение спрашивает про
   * языки в онбординге и хранит их. Человек решал, писать ли незнакомому, не зная, поймут ли его.
   */
  speaksLabel: () => T('Говорит: ', 'Speaks: ', 'Habla: '),
  invite: () => T('Пригласить', 'Invite', 'Invitar'),
  invited: () => T('Приглашение отправлено', 'Invite sent', 'Invitación enviada'),
  /** O.15: состояние карточки после отправки — две кнопки. */
  invitedShort: () => T('Отправлено', 'Invited', 'Invitado'),
  cancel: () => T('Отменить', 'Cancel', 'Cancelar'),
  cancelFailed: () => T('Не получилось отменить. Попробуй ещё раз.', 'Couldn’t cancel. Try again.', 'No se pudo cancelar. Inténtalo de nuevo.'),
  /** Отзывать нечего: ответили раньше, чем нажали. Это не сбой, и говорить о нём как о сбое нельзя. */
  cancelTooLate: () => T('Уже ответили — отзывать нечего.', 'They already answered — nothing to withdraw.', 'Ya respondieron — no hay nada que retirar.'),
  inviteFailed: () => T('Не отправилось. Попробуй ещё раз.', 'It didn’t send. Try again.', 'No se envió. Inténtalo de nuevo.'),

  /** Приписка приватности с кадра O.13, дословно. */
  privacyNote: () =>
    T(
      'Твой профиль видят только люди, которых предложил твой агент. Ты этим управляешь.',
      'Only people your agent recommended can see your profile. You’re in control.'
    , 'Solo las personas que te recomiende tu agente podrán ver tu perfil. Tú estás al mando.'),

  /** Окно O.14. Текст с кадра; по-английски нейтральное they вместо she — имя бывает любым. */
  sheetTitle: (name: string) => T(`Пригласить ${acc(name)}?`, `Invite ${name}?`, `¿Invitar a ${name}?`),
  sheetBody: (name: string) =>
    T(
      `${name} увидит твой интент и твой профиль. Если согласится — откроется чат; на бесплатном тарифе это единственный чат для этого интента.`,
      'They see your intent and your profile. If they join, a chat opens — on the free plan that is the one chat you get for this intent.'
    , 'Ven tu propuesta y tu perfil. Si se unen, se abre un chat — en el plan gratuito es el único chat que tienes para esta propuesta.'),
  send: () => T('Отправить приглашение', 'Send the invite', 'Enviar la invitación'),
  notYet: () => T('Пока нет', 'Not yet', 'Todavía no'),
};

/** Поля карточки, которые реально приходят из /api/agent/match. Всё остальное — не наше. */
/**
 * КОГО БОЛЬШЕ НЕ ПОКАЗЫВАТЬ В ЭТОЙ ВЫДАЧЕ.
 *
 * «Не интересно» и «Заблокировать» закрывали карточку профиля и возвращали человека в тот же
 * список — с живой кнопкой «Пригласить». Нажатие уходило на сервер, тот отвечал BLOCKED, и
 * человеку показывалось общее «Не отправилось, попробуй ещё раз»: блокировка выглядела как сбой
 * связи. Кадр O.13b обещает обратное — это безопасность ДО контакта.
 *
 * Блокировка живёт на сервере и переживает перезапуск; «не интересно» — это про ЭТУ выдачу, и
 * хранить его на сервере незачем. Поэтому здесь короткая память на время экрана, а блокировки
 * подтягиваются отдельно из /api/agent/safety.
 */
const hidden = new Set<string>();

export const hideCandidate = (name: string) => {
  const k = String(name || '').trim().toLowerCase();
  if (k) hidden.add(k);
};

export const isHidden = (name: string) =>
  hidden.has(String(name || '').trim().toLowerCase());

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
  band_es?: string;
  note?: string;
  why?: string;
  interests?: string[];
  /** Языки, на которых человеку комфортно (O.13). Полные английские имена: 'English', 'Spanish'. */
  langs?: string[];
  reasons?: string[];
  reasons_ru?: string[];
  reasons_en?: string[];
  reasons_es?: string[];
  readiness_ru?: string;
  readiness_en?: string;
  readiness_es?: string;
  /** Сводка Kleal о человеке — тот же абзац, что он видит у себя в профиле. */
  summary?: string;
  profile_view?: any;
};

/** Подзаголовок карточки: вайб, а без него — первые интересы. Занятия в данных нет (см. шапку). */
/**
 * Подпись с сервера на языке интерфейса. Ранжирование пишет её на трёх языках (`*_ru`, `*_en`,
 * `*_es`); у старых ответов испанского поля нет — тогда английское, как и было.
 * Флаг `ru` в подписях ниже остаётся ради общей формы вызовов: язык теперь решает getLang().
 */
function pickLang<V>(ru: V | undefined, en: V | undefined, es: V | undefined): V | undefined {
  const l = getLang();
  return l === 'ru' ? ru : l === 'es' ? (es ?? en) : en;
}

export function candSubtitle(c: Cand, ru: boolean): string {
  const vibe = String(c.vibe || '').trim();
  if (vibe) return vibe;
  // Подпись, а не ключ: «Падел · Настолки», а не «padel · boardgames». Заглавную ставим уже
  // после перевода — иначе она поднималась бы у английского ключа, который человек не увидит.
  const ints = interestLabels(c.interests).slice(0, 2);
  if (ints.length) return ints.map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(' · ');
  return String(pickLang(c.band_ru, c.band_en, c.band_es) || '');
}

/**
 * Строка с меткой места: километры, когда они посчитаны. Города у кандидата нет.
 *
 * Один знак после запятой ВСЕГДА — иначе на одной карточке рядом стоят «0 km» под именем и
 * «рядом (0.0 km)» в сводке причин: ранжирование округляет само, а шаблон печатал число как есть.
 */
export function candWhere(c: Cand): string {
  if (typeof c.km !== 'number' || !isFinite(c.km)) return '';
  const km = c.km.toFixed(1);
  // Десятичная запятая: по-русски и по-испански «0,4», точка — только в английском.
  return `${getLang() === 'en' ? km : km.replace('.', ',')} km`;
}

/** Доступность человека сейчас — строка ранжирования на языке интерфейса. */
export function candReadiness(c: Cand): string {
  return String(pickLang(c.readiness_ru, c.readiness_en, c.readiness_es) || '');
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
  /*
    ЧЕЛОВЕЧЕСКИЙ ТЕКСТ, А НЕ РАЗБОР СОВПАДЕНИЯ. Под заголовком «Сводка Kleal» стояли причины
    ранжирования — «общее: coffee, совпадает формат» — то есть то, что человек и так видит по чипам
    и по тому, что карточка вообще выдана. Снято с телефона: «хотелось бы видеть человеческий текст,
    как у себя в профиле в сводке». Теперь здесь тот же абзац, который Kleal собрал о человеке для
    его профиля; причины остаются запасным путём для карточек без сводки.
  */
  const own = String(c.summary || '').trim();
  if (own) return own;
  const reasons: string[] = pickLang(c.reasons_ru, c.reasons_en, c.reasons_es) || c.reasons || [];
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
  noMatches: () => T('Точных совпадений пока нет', 'No exact matches yet', 'Todavía no hay coincidencias exactas'),
  title: () => T('Изменить условия поиска', 'Change search preferences', 'Cambia tus preferencias de búsqueda'),
  lead: () => T('Чем меньше условий, тем больше людей. Сними то, что не принципиально.',
                'The fewer the conditions, the more people. Drop whatever is not essential.', 'Mientras menos condiciones, más gente. Elimina lo que no sea esencial.'),
  sex: () => T('Пол', 'Sex', 'Sexo'),
  age: () => T('Возраст', 'Age', 'Edad'),
  anyAge: () => T('Любой', 'Any', 'Cualquiera'),
  ageFrom: () => T('Не моложе', 'From', 'Desde'),
  ageTo: () => T('Не старше', 'To', 'A'),
  dist: () => T('Расстояние', 'Distance', 'Distancia'),
  distVal: (km: number) => T(`до ${km} км`, `within ${km} km`, `dentro de ${km} km`),
  start: () => T('Начать поиск', 'Start search', 'Iniciar búsqueda'),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),
  /** Что в итоге ушло в поиск. Ступень лестницы §12 называет себя вслух — этот лист молчал. */
  applied: (conds: string) => T(`Ищу по условиям: ${conds}.`, `Searching with: ${conds}.`, `Buscando con: ${conds}.`),
  anySex: () => T('любой пол', 'any sex', 'cualquier sexo'),
  ageAny: () => T('любой возраст', 'any age', 'cualquier edad'),
  ageBand: (lo: number, hi: number) => T(`возраст ${lo}–${hi}`, `age ${lo}–${hi}`, `edad ${lo}–${hi}`),
};

/**
 * Лист «Profile options» — кадр O.13b.
 *
 * У «Не интересно» и «Заблокировать» есть 4-секундный обратный отсчёт с отменой — это НА БОРДЕ
 * (аннотация кадра), не выдумка: оба действия меняют, кого человек увидит, и случайное нажатие
 * должно быть обратимым, пока не поздно.
 */
export const OPTIONS = {
  title: () => T('Действия с профилем', 'Profile options', 'Opciones del perfil'),
  notInterested: () => T('Не интересно', 'Not interested', 'No interesado'),
  report: () => T('Пожаловаться на профиль', 'Report profile', 'Reportar perfil'),
  block: (name: string) => T(`Заблокировать ${acc(name)}`, `Block ${name}`, `Bloquear a ${name}`),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),
  /** Строка отсчёта: действие названо, секунды идут, отмена в одно касание. */
  pending: (what: string, n: number) => T(`${what} через ${n}…`, `${what} in ${n}…`, `${what} en ${n}…`),
  undo: () => T('Отменить', 'Undo', 'Deshacer'),
  reportSent: () => T('Жалоба отправлена. Спасибо — её посмотрят.', 'Report sent. Thank you — it will be reviewed.', 'Reporte enviado. Gracias — será revisado.'),
  failed: () => T('Не получилось. Попробуй ещё раз.', 'That didn’t work. Try again.', 'Eso no funcionó. Inténtalo de nuevo.'),
};

/** Причины жалобы — словарь сервера (REPORT_REASONS). Подписи локальные, ключи его. */
/**
 * MSG.22 — потолок открытых приглашений. Правило КЛИЕНТСКОЕ: сервер шлёт сколько угодно, и когда
 * потолок станет тарифом, проверку надо перенести туда — иначе любой другой клиент её обходит.
 */
export const CAP = {
  limit: 3,
  title: (n: number) => T(`Уже ${n} открытых приглашения`, `${n} open invites already`, `${n} invitaciones abiertas ya`),
  note: () =>
    T(
      'Kleal держит не больше трёх разом, чтобы никто не получал веер заявок. Отмени одно или дождись ответа — Plus поднимает потолок до пяти.',
      'Kleal holds them at three so nobody gets a fan-out of requests. Cancel one, or wait for an answer — Plus raises it to five.'
    , 'Kleal las mantiene en tres para que nadie reciba una avalancha de solicitudes. Cancela una, o espera una respuesta — Plus la eleva a cinco.'),
  cancelOne: () => T('Отменить одно', 'Cancel one instead', 'Cancela una en su lugar'),
  withdraw: () => T('Отозвать', 'Withdraw', 'Retirar'),
};

/** Испанские подписи причин — картой по ключу; кортеж и его читатели остаются как были. */
export const REPORT_REASON_ES: Record<string, string> = {
  fake: 'Perfil falso',
  harassment: 'Acoso',
  spam: 'Spam',
  unsafe: 'Comportamiento peligroso',
  underage: 'Parece menor de edad',
  other: 'Otro',
};
export const REPORT_REASONS: [string, string, string][] = [
  ['fake', 'Фейковый профиль', 'Fake profile'],
  ['harassment', 'Оскорбления или преследование', 'Harassment'],
  ['spam', 'Спам', 'Spam'],
  ['unsafe', 'Небезопасное поведение', 'Unsafe behaviour'],
  ['underage', 'Похоже, несовершеннолетний', 'Looks underage'],
  ['other', 'Другое', 'Other'],
];
