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
import { PLAN } from './chat';
import { subFor } from './covers';
import { isMe, pidOf } from './api';
import { GROUP_MIN_TOTAL, GROUP_SIZE, intentSummaryText, normalizeIntentSize } from './intent';

/** Ключ, которым интент помечает сам себя в отправленном приглашении. См. `pendingFor`. */
export const INTENT_ID_KEY = 'kleal_intent_id';

export const ACT = {
  title: () => T('Моя активность', 'My Activity', 'Mi actividad'),

  tabIntents: () => T('Интенты', 'Intents', 'Propuestas'),
  tabPlans: () => T('Планы', 'Plans', 'Planes'),
  tabInvites: () => T('Приглашения', 'Invites', 'Invitaciones'),
  tabHistory: () => T('История', 'History', 'Historial'),

  /** Чипы состояния поверх обложки. */
  chipSearching: () => T('Ищем', 'Searching', 'Buscando'),
  chipOptions: (n: number) =>
    T(`${n} ${plural(n, 'вариант', 'варианта', 'вариантов')} готово`, `${n} option${n === 1 ? '' : 's'} ready`, `${n} ${n === 1 ? 'opción lista' : 'opciones listas'}`),
  /*
    ОТВЕТИЛИ «ДА» — ВЫБИРАЙ (сверка 17.10, п. 12). Раньше карточка считала только неотвеченные: стоило
    всем ответить, как она переходила в «варианты», и срок выбора pick_by сгорал вместе со всеми «да».
  */
  chipPick: (n: number) =>
    T(`${n} ${plural(n, 'ответил', 'ответили', 'ответили')} «да»`, `${n} said yes`, `${n} ${n === 1 ? 'dijo' : 'dijeron'} que sí`),
  ctaPick: () => T('Выбрать из ответивших', 'Pick from who said yes', 'Elige entre quienes dijeron que sí'),
  linePick: () => T('Выбери, с кем встречаешься, — иначе приглашения закроются.',
    'Pick who you’re meeting — otherwise the invites close.', 'Elige con quién quedas; si no, las invitaciones se cierran.'),
  chipWaiting: (n: number) =>
    T(`Ждём ${n} ${plural(n, 'ответ', 'ответа', 'ответов')}`, `Waiting for ${n} repl${n === 1 ? 'y' : 'ies'}`, `Esperando ${n} respuesta${n === 1 ? '' : 's'}`),

  /** Кнопка карточки. Её надпись — это и есть состояние, сказанное действием. */
  ctaSearching: () => T('Открыть поиск', 'View search', 'Ver búsqueda'),
  ctaOptions: () => T('Посмотреть варианты', 'Review options', 'Revisar opciones'),
  ctaWaiting: () => T('Посмотреть ответы', 'Review responses', 'Revisar respuestas'),

  /** Строка под названием на странице интента — кадры «States of My Intent page». */
  lineSearching: () => T('Kleal ищет людей рядом', 'Kleal is looking for people nearby', 'Kleal busca personas cerca de ti'),
  lineOptions: () => T('Выбери, кого позвать', 'Pick who to invite', 'Elige a quién invitar'),
  lineWaiting: () => T('Ответы придут сюда', 'Replies will show up here', 'Las respuestas aparecerán aquí'),

  edit: () => T('Изменить', 'Edit', 'Editar'),
  lookingNearby: () => T('Ищем людей рядом', 'Looking for nearby people', 'Buscando personas cercanas'),

  emptyIntents: () => T('Затей пока нет', 'No intents yet', 'Aún no hay propuestas'),
  emptyIntentsNote: () =>
    T(
      'Заведи затею — Kleal начнёт искать людей и покажет их здесь.',
      'Start something and Kleal will look for people, then show them here.'
    , 'Empieza algo y Kleal buscará a la gente y la mostrará aquí.'),
  emptyPlans: () => T('Встреч пока нет', 'No plans yet', 'Todavía no hay planes'),
  emptyInvites: () => T('Приглашений нет', 'No invites', 'Sin invitaciones'),
  emptyHistory: () => T('Здесь будет прошедшее', 'Past meetups will land here', 'Las quedadas pasadas aparecerán aquí'),
  create: () => T('Создать интент', 'Create intent', 'Crear propuesta'),
  /** Борд «My activity — new layout» (C.01–C.04a). */
  titleNew: () => T('Моя активность', 'My activity', 'Mi actividad'),
  emptyIntentsTitle: () => T('Затей пока нет', 'No intents yet', 'Aún no hay propuestas'),
  emptyIntentsBoard: () => T('Расскажи Kleal, чего хочется. Он превратит желание в затею и найдёт твоих людей.',
                             'Tell Kleal what you feel like doing. It turns your wish into an intent and finds your people.',
                             'Cuéntale a Kleal qué te apetece. Convierte tu deseo en una propuesta y encuentra a tu gente.'),
  talkToKleal: () => T('Поговорить с Kleal', 'Talk to Kleal', 'Hablar con Kleal'),
  emptyPlansNote: () => T('Когда группа договорится о плане, он появится здесь.', 'When your group agrees on a plan, it shows up here.',
                          'Cuando tu grupo acuerde un plan, aparecerá aquí.'),
  emptyInvitesTitle: () => T('Приглашений сейчас нет', 'No invites right now', 'No hay invitaciones ahora'),
  emptyInvitesNote: () => T('Когда тебя позовут в план, он появится здесь. Kleal пришлёт и пуш.',
                            'When someone invites you to their plan, it shows up here. Kleal sends you a push too.',
                            'Cuando alguien te invite a su plan, aparecerá aquí. Kleal también te envía un aviso.'),
  emptyHistoryTitle: () => T('Здесь пока пусто', 'Nothing here yet', 'Aún no hay nada'),
  emptyHistoryNote: () => T('Прошедшие планы и закрытые затеи остаются здесь — их можно запланировать снова.',
                            'Past plans and closed intents stay here, so you can plan them again.',
                            'Los planes pasados y las propuestas cerradas se quedan aquí, para que puedas repetirlos.'),
  // карточки
  chipNew: () => T('Новое', 'New', 'Nuevo'),
  chipDone: () => T('Прошло', 'Done', 'Hecho'),
  chipClosed: () => T('Закрыто', 'Closed', 'Cerrado'),
  invitedYou: (who: string) => T(`${who} зовёт тебя`, `${who} invited you`, `${who} te invitó`),
  afterAccept: (area: string) => area
    ? T(`${area} · точное место после согласия`, `${area} · exact spot after you accept`, `${area} · sitio exacto al aceptar`)
    : T('Точное место после согласия', 'Exact spot after you accept', 'Sitio exacto al aceptar'),
  onCall: () => T('В звонке', 'On a call', 'En una llamada'),
  pickedYou: () => T('Kleal выбрал тебя для этой затеи', 'Kleal picked you for their intent', 'Kleal te eligió para su propuesta'),
  reviewInvite: () => T('Посмотреть приглашение', 'Review invite', 'Revisar invitación'),
  goToPlan: () => T('К плану', 'Go to plan', 'Ir al plan'),
  planFixedCall: () => T('План закреплён · ссылка откроется за 10 минут', 'The plan is fixed · the link opens 10 minutes before',
                         'El plan está fijado · el enlace se abre 10 minutos antes'),
  planFixed: () => T('План закреплён', 'The plan is fixed', 'El plan está fijado'),
  planAgreeing: () => T('План ещё согласуют', 'The plan is still being agreed', 'El plan aún se está acordando'),
  oneToOneNoFeedback: () => T('Один на один · отзыва ещё нет', 'One-on-one · no feedback yet', 'Uno a uno · aún sin opinión'),
  oneToOne: () => T('Один на один', 'One-on-one', 'Uno a uno'),
  leaveFeedback: () => T('Оставить отзыв', 'Leave feedback', 'Dejar opinión'),
  didntStart: (n: number, need: number) => T(`Пришли только ${n} из ${need}, поэтому план не начался`,
                                             `Only ${n} of ${need} joined, so the plan didn’t start`,
                                             `Solo se unieron ${n} de ${need}, así que el plan no empezó`),
  cancelledNote: () => T('План отменён', 'The plan was called off', 'El plan se canceló'),
  planAgain: () => T('Запланировать снова с Kleal', 'Plan it again with Kleal', 'Planearlo otra vez con Kleal'),

  /**
   * Удаление затеи. «Выйти» из своей затеи нельзя — она твоя; из неё можно только уйти совсем,
   * и тогда её не должно остаться нигде: ни в списке, ни в поиске. Поэтому слово прямое.
   */
  removeTitle: () => T('Удалить затею?', 'Delete this intent?', '¿Borrar esta propuesta?'),
  removeNote: () => T(
    'Она исчезнет из списка, и Kleal перестанет искать по ней людей. Уже отправленные приглашения останутся у тех, кому ты их послал.',
    'It disappears from the list and Kleal stops looking for people. Invites you already sent stay with the people you sent them to.'
  , 'Deja de aparecer en la lista y Kleal deja de buscar personas. Las invitaciones que ya enviaste siguen con las personas a las que se las enviaste.'),
  remove: () => T('Удалить', 'Delete', 'Borrar'),
  keep: () => T('Оставить', 'Keep it', 'Manténlo'),
  removeFailed: () => T('Не удалось удалить. Попробуй ещё раз.', 'Could not delete. Try again.', 'No se pudo borrar. Inténtalo de nuevo.'),

  loadFailed: () => T('Не удалось загрузить.', 'Could not load.', 'No se pudo cargar.'),
  retry: () => T('Повторить', 'Retry', 'Reintentar'),
  /** Пересчёт одного интента упал: карточку не прячем — интент существует, просто без кандидатов. */
  rankFailed: () => T('Поиск по этой затее сейчас не отвечает', 'Search for this one is not responding', 'La búsqueda para esto no responde'),
};

/** `pick` — кто-то ответил «да» и ждёт выбора организатора (status answered, срок pick_by). */
export type IntentState = 'searching' | 'options' | 'waiting' | 'pick';

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
/** Сколько по этой затее ответили «да» и ждут выбора (answered) — им важнее всего ответ. */
export function answeredFor(intentId: string, outbox: any[]): number {
  const id = String(intentId || '');
  if (!id) return 0;
  return (outbox || []).filter(
    (r) => r && r.status === 'answered' && String(r.intent?.[INTENT_ID_KEY] || '') === id
  ).length;
}

export function intentState(row: IntentRow, outbox: any[]): IntentState {
  // «Да» уже пришло — решение за организатором, и это главнее ожидания остальных.
  if (answeredFor(row.id, outbox) > 0) return 'pick';
  if (pendingFor(row.id, outbox) > 0) return 'waiting';
  if ((row.candidates || []).length > 0) return 'options';
  return 'searching';
}

export function chipLabel(state: IntentState, row: IntentRow, outbox: any[]): string {
  if (state === 'pick') return ACT.chipPick(answeredFor(row.id, outbox));
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
  pick: 'success',
};

export function ctaLabel(state: IntentState): string {
  return state === 'pick' ? ACT.ctaPick() : state === 'waiting' ? ACT.ctaWaiting() : state === 'options' ? ACT.ctaOptions() : ACT.ctaSearching();
}

export function stateLine(state: IntentState): string {
  return state === 'pick' ? ACT.linePick() : state === 'waiting' ? ACT.lineWaiting() : state === 'options' ? ACT.lineOptions() : ACT.lineSearching();
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
  return T('Без названия', 'Untitled', 'Sin título');
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
  push(T('Формат', 'Mode', 'Modo'), i.mode === 'online' ? T('Онлайн', 'Online', 'Online')
    : i.mode === 'hybrid' ? T('Гибрид', 'Hybrid', 'Híbrido')
    : i.mode === 'offline' ? T('Вживую', 'Offline', 'Presencial') : '');
  const normalizedSize = normalizeIntentSize(i.format || i.size, i.groupSize);
  push(T('Состав', 'Format', 'Formato'), normalizedSize === 'group' ? T('Группа', 'Group', 'Grupo')
    : normalizedSize === '1:1' ? T('Один на один', '1:1', '1:1') : '');
  if (normalizedSize === 'group') {
    push(GROUP_SIZE.row(), GROUP_SIZE.people(Number(i.groupSize) || GROUP_MIN_TOTAL));
  }
  push(T('Тема', 'Category', 'Categoría'), i.topics);
  /**
   * Пол и возраст читаются ТЕМИ ЖЕ ключами, какими их пишет мастер: `sex` из SEXES («Male» /
   * «Female» / «Any», с большой буквы) и `minAge` / `maxAge`. Сравнение в нижнем регистре и
   * `min_age` через подчёркивание — ровно то, на чём паспорт затеи показывал «Аудитория: Любой»
   * при сохранённых «Female, 22–34»: поля были на месте, а прочитать их было нечем.
   */
  const sex = i.sex === 'Female' ? T('Женщины', 'Female', 'Mujer')
    : i.sex === 'Male' ? T('Мужчины', 'Male', 'Hombre')
    : T('Любой', 'Any is fine', 'Cualquiera vale');
  const age = i.minAge && i.maxAge ? `${i.minAge}–${i.maxAge}` : '';
  push(T('Аудитория', 'Audience', 'Público'), [sex, age].filter(Boolean).join(ru ? ', ' : ', '));
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
    size: normalizeIntentSize(i.format || i.size, i.groupSize),
    groupSize: Number(i.groupSize) || undefined,
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
  /**
   * Название затеи, как его хранит план, без подстановок. `title` для карточки падает на имя
   * собеседника или «Встреча» — такой фразой мастер затеи не засеешь; «Plan it again» берёт это поле.
   */
  topic: string;
  date: string;
  time: string;
  where: string;
  chip: string;
  tone: 'warn' | 'success' | 'info';
  faces: string[];
  gid?: string;
  id?: string;
  who?: string;
  /** id собеседника — переход в план и в чат зовёт его по id (тёзки). */
  whoId?: string;
  /** Подгруппа таксономии — по ней карточка берёт обложку (см. src/covers.ts). */
  sub: string;
  /** Борд «My activity»: формат, состояние и итоги — для строки под местом и кнопки. */
  mode: string;
  state: string;
  past: boolean;
  /** Мой ответ «состоялась ли» уже записан. */
  answered: boolean;
  /** Сколько людей в плане и сколько нужно, чтобы он начался (у группы). */
  count: number;
  need: number;
};

export const PLAN_STATE = {
  proposed: () => T('Согласовывают', 'Being agreed', 'En acuerdo'),
  confirmed: () => T('Подтверждён', 'Confirmed', 'Confirmado'),
  locked: () => T('Закреплён', 'Locked', 'Bloqueado'),
  below: () => T('На паузе', 'On hold', 'En espera'),
  done: () => T('Прошло', 'Ended', 'Finalizado'),
  cancelled: () => T('Отменён', 'Called off', 'Cancelada'),
  open: () => T('Открыть план', 'Open the plan', 'Abre el plan'),
  /** Вторая дверь из прошедшей встречи: к тому, с кем встречался. */
  openChat: () => T('Открыть чат', 'Open chat', 'Abrir el chat'),
};

/**
 * Строка места на карточке.
 *
 * Раньше здесь стояли только venue/district/place — а у звонка нет ни одного из трёх, и карточка
 * писала «место не указано» про встречу, у которой места и не предполагалось. Формат знает сам
 * план, и он же решает, что писать: у звонка это «Видеозвонок», а не отсутствующий адрес.
 */
function cardWhere(p: any): string {
  const mode = String(p?.mode || '');
  const area = String(p?.venue || p?.district || p?.place || '').trim();
  if (mode === 'online') return PLAN.modeOnline();
  if (mode === 'hybrid') return area ? `${PLAN.modeHybrid()} · ${area}` : PLAN.modeHybrid();
  return planWhere(area, '', '');
}

/**
 * Один разбор на парные и групповые планы: для человека это одна и та же встреча.
 *
 * `past` — карточка из истории. Это ЗНАНИЕ ВЫЗЫВАЮЩЕГО, а не признак в ответе: план попадает в
 * историю и просто по возрасту, оставаясь в состоянии «подтверждён», и тогда карточка в «Истории»
 * светила зелёным «Подтверждён» про встречу, которая давно прошла.
 */
export function planCard(p: any, me = '', past = false): PlanCard {
  const st = String(p?.state || '');
  const tone: PlanCard['tone'] =
    past || st === 'below_quorum' || st === 'cancelled' ? 'info'
    : st === 'confirmed' || st === 'locked' ? 'success' : 'warn';
  const chip =
    st === 'cancelled' ? PLAN_STATE.cancelled()
    : past || st === 'done' ? PLAN_STATE.done()
    : st === 'confirmed' ? PLAN_STATE.confirmed()
    : st === 'locked' ? PLAN_STATE.locked()
    : st === 'below_quorum' ? PLAN_STATE.below()
    : PLAN_STATE.proposed();
  // Другие участники — «не я» по id (kleal-ms/docs/IDENTITY.md): у встречи тёзок подписи равны.
  const others = (p?.participants || [])
    .filter((x: any) => String(x?.name || '') && !isMe(x?.name, pidOf(x, 'name'), me));
  const who = others.map((x: any) => String(x?.name || ''));
  const when = splitWhen(String(p?.when || ''));
  return {
    key: (p?.gid ? 'gp:' : 'mp:') + String(p?.id || p?.gid || ''),
    title: String(p?.title || who[0] || T('Встреча', 'Meetup', 'Quedada')).trim(),
    topic: String(p?.title || '').trim(),
    date: when.date,
    time: when.time,
    where: cardWhere(p),
    chip,
    tone,
    faces: (p?.participants || []).map((x: any) => String(x?.photo || '')).filter(Boolean).slice(0, 3),
    gid: p?.gid ? String(p.gid) : undefined,
    id: p?.id ? String(p.id) : undefined,
    who: who[0],
    whoId: others[0] ? pidOf(others[0], 'name') : undefined,
    // Тем у плана нет — он знает только название и формат, — поэтому подгруппа ищется по словам
    // названия. «Падел в субботу» находит падел; не нашлось ничего — будет общая обложка.
    sub: subFor(p),
    mode: String(p?.mode || ''),
    state: st,
    past,
    answered: p?.my_feedback !== undefined && p?.my_feedback !== null && p?.my_feedback !== false,
    count: (p?.participants || []).length,
    need: Number(p?.min_total || p?.need || 3),
  };
}

/** Счётчик на сегменте «Приглашения» — столько же, сколько строк в стопке на главной. */
export const inviteBadge = (invites: any[]) => (invites || []).length;

/** Подпись «N идут» на карточке берём из главной: согласование там уже написано. */
export const goingLabel = HOME.going;
