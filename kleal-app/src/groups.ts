/**
 * Групповой набор — выдача, приглашения, кап. Кадры GR.14–GR.17 борда «Groups · Offline».
 *
 * UX-каркас: копия и правила здесь, вид — в app/results.tsx (групповой режим той же выдачи).
 * Английские строки взяты с кадров ДОСЛОВНО, русские написаны, а не переведены машинно.
 *
 * Правила набора — они же серверные (см. GI_* в services/matching/app.py, теперь по борду):
 *  — приглашения уходят ПО ОДНОМУ, каждое через шит подтверждения (GR.16); батч-кнопки нет;
 *  — открытых приглашений не больше ТРЁХ (GR.15): дальше INVITE_CAP, выход — отменить одно;
 *  — «first 5 who accept are in»: места не резервируются, состав решает принятие;
 *  — список приглашённых видит ТОЛЬКО организатор (GR.17); приглашённому обещано «who is
 *    already in», а не «кого ещё позвали» (GR.16).
 */
import { T } from './i18n';
import { myId } from './api';
import { normalizeIntentSize } from './intent';
import type { Msg } from './chat';

/**
 * Групповой ли это интент. Мастер шлёт плоские format/groupSize; сервер в ответе может отдать их
 * же или §4.3-блок mode_format — читаем все три места, чтобы режим не зависел от того, чей объект
 * долетел до выдачи.
 */
export function isGroupIntent(intent: any): boolean {
  if (!intent || typeof intent !== 'object') return false;
  const flat = String(intent.format || '').toLowerCase();
  const block = String(intent.mode_format?.format || '').toLowerCase();
  return (normalizeIntentSize(flat, intent.groupSize) || normalizeIntentSize(block, intent.groupSize)) === 'group';
}

/** Заголовок группы для gintent-create: подпись человека, а не ключи поиска. */
export function groupTitleOf(intent: any, query = ''): string {
  const t = String(intent?.title || '').trim();
  if (t) return t;
  const q = String(query || '').trim();
  if (q) return q.slice(0, 120);
  const topics = Array.isArray(intent?.topics) ? intent.topics.filter(Boolean) : [];
  return topics.join(', ').slice(0, 120) || 'Meetup';
}

/**
 * Место в карточке затеи на страницах группы (GR.24, GR.42–44). Организатор видит ТОЧНЫЙ адрес —
 * заметки к GR.44 / GR.44h: «она организатор, видит точный адрес»; остальные — район до общего
 * согласия (строка «Exact spot after everyone confirms»). `area` — то, что было и раньше.
 * Адрес берётся, только если сервер его отдал (`address` или `intent.address`); решать, кому его
 * отдавать, — серверу, клиент лишь не показывает его не-организатору.
 */
export function groupPlace(g: any, me = ''): string {
  // GR.44f / 44l: тот, кто передал роль, по-прежнему видит точный адрес — он его и назначал.
  // Сервер отдаёт role_from {who, how, at} без id (сверено с боевым app.py 06.10) — сверяем по имени.
  const rf = g?.role_from || {};
  const norm = (s: any) => String(s || '').trim().toLowerCase();
  const wasOwner = rf.who_id ? rf.who_id === myId() : !!norm(me) && norm(rf.who) === norm(me);
  const exact = g?.i_am_owner || wasOwner ? String(g?.address || g?.intent?.address || '').trim() : '';
  return exact || String(g?.area || '').trim();
}

/** Онлайн-группа (борд «GR · Online»): место на карточке — ссылка на звонок. */
export const isOnlineGroup = (g: any) => String(g?.mode || g?.intent?.mode || '') === 'online';

/** GRO.24 / GRO.42 / GRO.56: «Video call · your link» / «Video call · Mateo’s link». */
export function groupCallLine(g: any, me = ''): string {
  const norm = (s: any) => String(s || '').trim().toLowerCase();
  const mine = !!g?.i_am_owner || (!!norm(me) && norm(g?.owner) === norm(me));
  const owner = String(g?.owner || '').trim();
  return mine ? T('Звонок · твоя ссылка', 'Video call · your link', 'Videollamada · tu enlace')
    : owner ? T(`Звонок · ссылка ${owner}`, `Video call · ${owner}’s link`, `Videollamada · enlace de ${owner}`)
    : T('Звонок', 'Video call', 'Videollamada');
}

export const GROUP = {
  /** Шапка выдачи в групповом режиме — GR.14, дословно. */
  header: () => T('Кто подходит твоей группе', 'Who fits your group', '¿Quién encaja en tu grupo?'),
  /** После первого отправленного приглашения тот же список становится GR.17. */
  invitesSent: () => T('Приглашения отправлены', 'Invites sent', 'Invitaciones enviadas'),

  /**
   * Строка регламента под шапкой — GR.14. Числа живые: минимум и потолок приходят с группы,
   * кап приглашений — тоже, чтобы строка не разошлась с сервером при смене тарифа.
   */
  regime: (min: number, max: number, cap: number) =>
    T(
      `Группа · ${min}–${max} человек · не больше ${cap} приглашений разом · кто первым согласится, тот в группе`,
      `Group · ${min}–${max} people · ${cap} open invites at a time on Free · first ${max} who accept are in`
    , `Grupo · ${min}–${max} personas · ${cap} invitaciones abiertas al mismo tiempo en Free · las primeras ${max} que acepten entrarán`),

  /**
   * Счётчик набора — GR.17: «2 of 5 joined · 3 invites still open · a plan needs 3».
   * Присоединившиеся считаются ВМЕСТЕ с организатором — так же, как считает сервер.
   */
  counter: (joined: number, max: number, open: number, min: number) =>
    T(
      `В группе ${joined} из ${max} · открытых приглашений: ${open} · для плана нужно ${min}`,
      `${joined} of ${max} joined · ${open} invite${open === 1 ? '' : 's'} still open · a plan needs ${min}`
    , `${joined} de ${max} dentro · ${open} invitación${open === 1 ? '' : 'es'} sin responder · para un plan hacen falta ${min}`),

  /** Кнопка и состояния строки кандидата — GR.14/GR.17. */
  joined: () => T('В группе', 'Joined', 'Unido'),

  /** Шит подтверждения — GR.16, дословно с кадра. */
  askTitle: (name: string) => T(`Пригласить ${name} в группу?`, `Invite ${name} to the group?`, `¿Invitar a ${name} al grupo?`),
  askBody: (name: string) =>
    T(
      `${name} увидит интент и кто уже внутри. Согласие сразу ведёт в общий чат группы — личной переписки с тобой здесь нет.`,
      'She sees the intent and who is already in. If she accepts she joins the shared group chat straight away — there is no private chat with you.'
    , 'Ella ve la propuesta y quién está ya dentro. Si acepta, entra directamente al chat de grupo — no hay chat privado contigo.'),
  askSend: () => T('Отправить приглашение', 'Send the invite', 'Enviar la invitación'),
  askNot: () => T('Пока нет', 'Not yet', 'Todavía no'),

  /** Шит капа — GR.15, дословно. Plus в продукте нет — его строка честно выключена (правило каркаса). */
  capTitle: () => T('Три приглашения уже в воздухе', 'Three invites are already open', 'Ya hay tres invitaciones abiertas'),
  capBody: () =>
    T(
      'Три приглашения ждут ответа. Kleal держит планку в три, чтобы никому не прилетал веер заявок. Отмени одно или дождись ответа — Plus поднимет планку.',
      'You have 3 invites still waiting for an answer. Kleal holds them at three so nobody gets a fan-out of requests. Cancel one, or wait — Plus raises it.'
    , 'Tienes 3 invitaciones aún esperando una respuesta. Kleal las mantiene en tres para que nadie reciba un montón de solicitudes. Cancela una, o espera — Plus la aumenta.'),

  /** Отказы сервера — по имени, как он их называет. */
  full: () => T('Группа уже собралась — мест нет.', 'The group is already full.', 'El grupo ya está lleno.'),
  sendFailed: () => T('Приглашение не ушло. Попробуй ещё раз.', 'The invite didn’t go out. Try again.', 'La invitación no se envió. Inténtalo de nuevo.'),
};

/**
 * Местоимение для английских строк борда: «when she answers» у Jane, «when he answers» у Marc.
 * Пол берётся из карточки, если сервер его прислал; нет — «they», а не догадка по имени.
 * Русская и испанская копии построены без местоимений и рода — им это не нужно.
 */
export type Pron = 'she' | 'he' | 'they';
export function pronOf(c: any): Pron {
  const v = String(c?.sex || c?.gender || c?.profile_view?.sex || c?.profile_view?.gender || '').toLowerCase();
  if (v === 'female' || v === 'f' || v === 'woman') return 'she';
  if (v === 'male' || v === 'm' || v === 'man') return 'he';
  return 'they';
}
const P = (p: Pron) => ({
  subj: p === 'she' ? 'she' : p === 'he' ? 'he' : 'they',
  Subj: p === 'she' ? 'She' : p === 'he' ? 'He' : 'They',
  poss: p === 'she' ? 'her' : p === 'he' ? 'his' : 'their',
  Poss: p === 'she' ? 'Her' : p === 'he' ? 'His' : 'Their',
  /** «she answers» / «they answer» — согласование глагола. */
  s: p === 'they' ? '' : 's',
  has: p === 'they' ? 'have' : 'has',
});

/**
 * OFP — «выбор из ответивших» у приглашений один на один (борд «1:1 · Offline», OF.12–OF.15).
 * Лежит здесь, а не в candidates.ts: текстам нужны местоимения (`P`).
 */
export const OFP = {
  /** OF.12 */
  lead: (n: number, short: string, cap: number) => T(
    `Kleal подобрал для «${short}» ${n} чел. Зови одного или нескольких — на Free до ${cap} открытых приглашений. Ты выбираешь одного из тех, кто скажет «да».`,
    `Kleal picked ${n} ${n === 1 ? 'person' : 'people'} for your ${short}. Invite one or several — up to ${cap} open invites on Free. You pick one from those who say yes.`,
    `Kleal eligió ${n} ${n === 1 ? 'persona' : 'personas'} para tu ${short}. Invita a una o a varias — hasta ${cap} invitaciones abiertas en Free. Eliges a una de las que digan que sí.`),
  /** OF.12e */
  leadPicked: (name: string, others: string) => T(
    `Ты выбрал(а) ${name}. Чат открыт${others ? ` — ${others} получили уведомление` : ''}.`,
    `You picked ${name}. The chat is open${others ? ` — ${others} got a note` : ''}.`,
    `Elegiste a ${name}. El chat está abierto${others ? ` — ${others} recibieron un aviso` : ''}.`),
  /** O.12 / O.14 / O.14a — у звонка вместо короткого названия затеи слово «call». */
  callWord: () => T('звонок', 'call', 'llamada'),
  callLine: () => T('Видеозвонок · ссылка придёт с планом', 'Video call · link comes with the plan', 'Videollamada · el enlace llega con el plan'),
  askNoteCall: (p: Pron) => T(
    'Человек увидит твою затею и профиль. Ссылка на звонок придёт только с планом. Если ответит «да», ты выберешь, с кем поговорить, из всех ответивших.',
    `${P(p).Subj} see${P(p).s} your intent and your profile. The call link comes only with the plan. If ${P(p).subj} say${P(p).s} yes, you pick who you talk to from everyone who did.`,
    'Verá tu plan y tu perfil. El enlace de la llamada llega solo con el plan. Si dice que sí, eliges con quién hablar entre quienes lo hicieron.'),
  pickTitleCall: () => T('Выбери, с кем поговоришь', 'Pick who you’ll talk to', 'Elige con quién hablas'),
  /** OF.14 */
  askLead: (name: string, short: string) => T(
    `Позвать ${name} на «${short}»?`, `Invite ${name} to your ${short}?`, `¿Invitar a ${name} a tu ${short}?`),
  askNote: (p: Pron) => T(
    'Человек увидит твою затею и профиль — район, а не точное место. Если ответит «да», ты выберешь, с кем встретиться, из всех ответивших.',
    `${P(p).Subj} see${P(p).s} your intent and your profile — the area, not the exact spot. If ${P(p).subj} say${P(p).s} yes, you pick who you meet from everyone who did.`,
    'Verá tu plan y tu perfil — la zona, no el punto exacto. Si dice que sí, eliges con quién quedar entre quienes lo hicieron.'),
  /** HY.14 — гибрид: человек может прийти или подключиться. */
  askNoteHybrid: (p: Pron) => T(
    'Человек увидит твою затею и профиль — район, а не точное место. Он может прийти вживую или подключиться к звонку. Если ответит «да», ты выберешь, с кем встретиться, из всех ответивших.',
    `${P(p).Subj} see${P(p).s} your intent and your profile — the area, not the exact spot. ${P(p).Subj} can come in person or join the call. If ${P(p).subj} say${P(p).s} yes, you pick who you meet from everyone who did.`,
    'Verá tu plan y tu perfil — la zona, no el punto exacto. Puede venir en persona o unirse a la llamada. Si dice que sí, eliges con quién quedar entre quienes lo hicieron.'),
  callLineHybrid: () => T('Ссылка на звонок придёт с планом', 'Call link comes with the plan', 'El enlace de llamada llega con el plan'),
  /** OF.12a */
  sentNote: (name: string, p: Pron) => T(
    `${name} видит твою затею и профиль. Пуш придёт, как только будет ответ.`,
    `${name} sees your intent and your profile. You’ll get a push when ${P(p).subj} answer${P(p).s}.`,
    `${name} ve tu plan y tu perfil. Te llegará un aviso cuando responda.`),
  /** OF.12d */
  yes: () => T('Ответ «да»', 'Said yes', 'Dijo que sí'),
  yesNote: (name: string, p: Pron) => T(
    `${name} ответил(а) «да». Выбери — и откроется чат, остальные получат уведомление.`,
    `${name} said yes. Pick ${p === 'she' ? 'her' : p === 'he' ? 'him' : 'them'} and the chat opens — the others get a note.`,
    `${name} dijo que sí. Elígele y se abre el chat — los demás reciben un aviso.`),
  pick: (name: string) => T(`Выбрать ${name}`, `Pick ${name}`, `Elegir a ${name}`),
  pickFailed: () => T('Не удалось выбрать. Попробуй ещё раз.', 'Could not pick. Try again.', 'No se pudo elegir. Inténtalo de nuevo.'),
  /** OF.12e */
  picked: () => T('Выбран(а)', 'Picked', 'Elegido'),
  pickedNote: (name: string) => T(
    `Ты выбрал(а) ${name}. Чат открыт.`, `You picked ${name}. The chat is open.`, `Elegiste a ${name}. El chat está abierto.`),
  closedNote: (picked: string, name: string, p: Pron) => T(
    `Ты выбрал(а) ${picked}, поэтому приглашение для ${name} закрыто. Уведомление уже ушло.`,
    `You picked ${picked}, so ${name}’s invite closed. ${P(p).Subj} got a note.`,
    `Elegiste a ${picked}, así que la invitación de ${name} se cerró. Le llegó un aviso.`),
  closedPlain: (name: string, p: Pron) => T(
    `Приглашение для ${name} закрыто. Уведомление уже ушло.`,
    `${name}’s invite closed. ${P(p).Subj} got a note.`,
    `La invitación de ${name} se cerró. Le llegó un aviso.`),
  /** OF.14b — обзор, когда приглашены все из списка. */
  sentLead: (names: string) => T(
    `${names} видят твою затею. Ты выберешь одного из тех, кто скажет «да», — и с ним откроется чат.`,
    `${names} see your intent. You pick one from those who say yes — then the chat opens with them.`,
    `${names} ven tu plan. Eliges a una de las personas que digan que sí — y se abre el chat con ella.`),
  /** OF.16 */
  declinedLead: (wait: string, name: string) => T(
    `${wait ? `${wait} ещё могут ответить. ` : ''}На место ${name} можно позвать кого-то ещё.`,
    `${wait ? `${wait} can still answer. ` : ''}You can invite someone else in ${name}’s place.`,
    `${wait ? `${wait} aún pueden responder. ` : ''}Puedes invitar a otra persona en lugar de ${name}.`),
  /** OF.14a */
  expiredTitle: () => T('Никто не ответил вовремя', 'Nobody answered in time', 'Nadie respondió a tiempo'),
  expiredLead: (names: string, short: string) => T(
    `${names} не ответили в срок, приглашения закрыты. У Kleal есть новые люди для «${short}».`,
    `${names} didn’t answer in time, so the invites closed. Kleal has new people for your ${short}.`,
    `${names} no respondieron a tiempo y las invitaciones se cerraron. Kleal tiene nuevas personas para tu ${short}.`),
  didntAnswer: () => T('Не ответил(а)', 'Didn’t answer', 'No respondió'),
  /** OF.15 */
  pickTitle: () => T('Выбери, с кем встретишься', 'Pick who you’ll meet', 'Elige con quién quedas'),
  pickLead: (names: string, many: boolean) => T(
    `${names} ответил${many ? 'и' : '(а)'} «да». Выбери одного — с ним откроется чат, а остальным Kleal сообщит, что приглашение закрыто.`,
    `${names} said yes. Pick one — the chat opens with them, and Kleal lets the others know the invite is closed.`,
    `${names} ${many ? 'dijeron' : 'dijo'} que sí. Elige a una persona — se abre el chat con ella y Kleal avisa a las demás de que la invitación se cerró.`),
  /** Счётчик OF.12a: «Answered 0 of 1». */
  answered: () => T('Ответили', 'Answered', 'Respondieron'),
};

/** Перечень имён: «Jane», «Jane and Marc», «Jane, Marc and Elly». */
export function namesList(names: string[]): string {
  const n = names.filter(Boolean);
  const and = T(' и ', ' and ', ' y ');
  if (n.length <= 1) return n[0] || '';
  return `${n.slice(0, -1).join(', ')}${and}${n[n.length - 1]}`;
}

const WORD_EN = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight'];
const WORD_RU = ['ноль', 'один', 'двое', 'трое', 'четверо', 'пятеро', 'шестеро', 'семеро', 'восьмеро'];
const WORD_ES = ['cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho'];
const word = (n: number) => T(WORD_RU[n] || String(n), WORD_EN[n] || String(n), WORD_ES[n] || String(n));

/**
 * Короткое имя затеи для фраз «for your BBQ», «Invite Jane to your BBQ?». Борд режет «BBQ by the
 * beach» до «BBQ»: берём часть до первого английского предлога места или компании. Не нашлось — всё
 * название целиком: обрезать русскую фразу по догадке хуже, чем сказать её полностью.
 */
export function shortTitle(title: string): string {
  const t = String(title || '').trim();
  const m = t.match(/^(.{2,}?)\s+(?:by|at|in|on|near|with|for|around)\s+/i);
  return (m ? m[1] : t) || t;
}

/**
 * Выдача в групповом режиме — борд «0 · Create the intent» (Figma 6864:119674), кадры GR.14–GR.17a.
 * Текст дословно с кадров; числа — живые (размер группы, кап приглашений, кто уже ответил).
 */
export const GR14 = {
  title: () => T('Кто лучше подходит твоей группе', 'Best fit for your group', 'Quién encaja mejor en tu grupo'),
  /** GR.14: «Kleal picked 3 people for your BBQ. Invite them one by one — up to 3 open invites on Free. The first two who say yes join the group.» */
  lead: (n: number, short: string, cap: number, take: number) => T(
    `Kleal подобрал для «${short}» ${n} чел. Приглашай по одному — на Free до ${cap} открытых приглашений. Первые ${word(take)}, кто скажет «да», попадут в группу.`,
    `Kleal picked ${n} ${n === 1 ? 'person' : 'people'} for your ${short}. Invite them one by one — up to ${cap} open invites on Free. The first ${word(take)} who say yes join the group.`,
    `Kleal eligió ${n} ${n === 1 ? 'persona' : 'personas'} para tu ${short}. Invítalas una a una — hasta ${cap} invitaciones abiertas en Free. Las primeras ${word(take)} que digan que sí entran al grupo.`),
  /** GR.14e: группа собралась. Хвост про закрывшиеся — только если такие есть. */
  leadFull: (yes: string, closedNames: string, many: boolean) => T(
    `${yes} — «да», и группа собрана.${closedNames ? ` ${many ? 'Приглашения' : 'Приглашение'} ${closedNames} ${many ? 'закрылись' : 'закрылось'} сами.` : ''}`,
    `${yes} said yes, so your group is complete.${closedNames ? ` ${closedNames}’s invite${many ? 's' : ''} closed on ${many ? 'their' : 'its'} own.` : ''}`,
    `${yes} dijeron que sí, así que tu grupo está completo.${closedNames ? ` ${many ? 'Las invitaciones' : 'La invitación'} de ${closedNames} se ${many ? 'cerraron' : 'cerró'} sola${many ? 's' : ''}.` : ''}`),

  /** Полоса набора «Round Indicator»: Joined · 1 of 2 · Ends in 11h 54m. */
  joined: () => T('В группе', 'Joined', 'Dentro'),
  of: (n: number) => T(`из ${n}`, `of ${n}`, `de ${n}`),
  endsIn: (left: number) => {
    const mins = Math.max(0, Math.round(left / 60000));
    const h = Math.floor(mins / 60), m = mins % 60;
    const hh = T(`${h} ч`, `${h}h`, `${h} h`), mm = T(`${m} мин`, `${m}m`, `${m} min`);
    const span = h && m ? `${hh} ${mm}` : h ? hh : mm;
    return T(`Осталось ${span}`, `Ends in ${span}`, `Termina en ${span}`);
  },

  invite: (name: string) => T(`Пригласить ${name}`, `Invite ${name}`, `Invitar a ${name}`),
  cancelInvite: () => T('Отменить приглашение', 'Cancel invite', 'Cancelar invitación'),
  openChat: () => T('Открыть чат группы', 'Open the group chat', 'Abrir el chat del grupo'),
  seeNew: () => T('Показать новых людей', 'See new candidates', 'Ver nuevas personas'),

  /** Блок состояния на карточке — GR.14a / 14c / 14d / 14e. */
  sent: () => T('Приглашение отправлено', 'Invite sent', 'Invitación enviada'),
  sentNote: (name: string, p: Pron) => T(
    `${name} видит твою затею и тех, кто уже внутри. Пуш придёт, как только будет ответ.`,
    `${name} sees your intent and who’s already in. You’ll get a push when ${P(p).subj} answer${P(p).s}.`,
    `${name} ve tu plan y quién está ya dentro. Te llegará un aviso cuando responda.`),
  joinedTitle: () => T('В группе', 'Joined the group', 'Se unió al grupo'),
  joinedNote: (name: string, left: number) => T(
    `${name} уже в чате группы. ${left <= 0 ? 'Группа собрана.' : left === 1 ? 'Ещё одно «да» — и группа собрана.' : `Ещё ${left} «да» — и группа собрана.`}`,
    `${name} is in the group chat. ${left <= 0 ? 'The group is complete.' : left === 1 ? 'One more yes and the group is complete.' : `${WORD_EN[left] ? WORD_EN[left].charAt(0).toUpperCase() + WORD_EN[left].slice(1) : left} more yeses and the group is complete.`}`,
    `${name} ya está en el chat del grupo. ${left <= 0 ? 'El grupo está completo.' : left === 1 ? 'Un sí más y el grupo estará completo.' : `${left} síes más y el grupo estará completo.`}`),
  declined: () => T('Не сможет', 'Can’t make it', 'No puede'),
  declinedNote: (name: string) => T(
    `${name} в этот раз отказывается. Место для приглашения снова свободно.`,
    `${name} said no this time. Your invite slot is free again.`,
    `${name} dijo que no esta vez. Tu hueco de invitación vuelve a estar libre.`),
  closed: () => T('Приглашение закрыто', 'Invite closed', 'Invitación cerrada'),
  closedNote: (name: string, p: Pron) => T(
    `Группа собралась раньше, чем пришёл ответ от ${name}. Приглашение закрыто — уведомление уже ушло.`,
    `The group filled up before ${name} answered. ${P(p).Subj} got a note that the invite is closed.`,
    `El grupo se llenó antes de que ${name} respondiera. Le llegó un aviso de que la invitación está cerrada.`),

  /** Закрылось без ответа, но не из-за полной группы: вышел срок или иное (сервер, invites_closed). */
  closedExpiredNote: (name: string) => T(
    `Ответа от ${name} не было вовремя — приглашение закрылось само. Место снова свободно.`,
    `${name} didn’t answer in time, so the invite closed on its own. The slot is free again.`,
    `${name} no respondió a tiempo, así que la invitación se cerró sola. El hueco vuelve a estar libre.`),
  closedOtherNote: (name: string) => T(
    `Приглашение для ${name} закрыто.`, `${name}’s invite is closed.`, `La invitación de ${name} está cerrada.`),

  /** Лист GR.16 «Invite Jane». */
  askTitle: (name: string) => T(`Пригласить ${name}`, `Invite ${name}`, `Invitar a ${name}`),
  askLead: (name: string, short: string) => T(
    `Пригласить ${name} на «${short}»?`, `Invite ${name} to your ${short}?`, `¿Invitar a ${name} a tu ${short}?`),
  askNote: (p: Pron) => T(
    'Человек увидит твою затею и тех, кто уже внутри, — район, а не точное место. Если согласится, сразу попадёт в чат группы.',
    `${P(p).Subj} see${P(p).s} your intent and who’s already in — the area, not the exact spot. If ${P(p).subj} say${P(p).s} yes, ${P(p).subj} join${P(p).s} the group chat right away.`,
    'Verá tu plan y quién está ya dentro — la zona, no el sitio exacto. Si dice que sí, entra al chat del grupo enseguida.'),
  /** GRH.16 — гибридная группа: район и то, что есть звонок. */
  askNoteHybrid: (p: Pron) => T(
    'Человек увидит твою затею и тех, кто уже внутри, — район, а не точное место, и то, что есть звонок. Если согласится, сразу попадёт в чат группы.',
    `${P(p).Subj} see${P(p).s} your intent and who’s already in — the area, not the exact spot, and that there’s a call. If ${P(p).subj} say${P(p).s} yes, ${P(p).subj} join${P(p).s} the group chat right away.`,
    'Verá tu plan y quién está ya dentro — la zona, no el sitio exacto, y que hay una llamada. Si dice que sí, entra al chat del grupo enseguida.'),
  /** GRO.16: онлайн — вместо района говорим про ссылку. */
  askNoteCall: (p: Pron) => T(
    'Человек увидит твою затею и тех, кто уже внутри. Ссылка на звонок придёт вместе с планом. Если согласится, сразу попадёт в чат группы.',
    `${P(p).Subj} see${P(p).s} your intent and who’s already in. The call link comes with the plan. If ${P(p).subj} say${P(p).s} yes, ${P(p).subj} join${P(p).s} the group chat right away.`,
    'Verá tu plan y quién está ya dentro. El enlace de la llamada llega con el plan. Si dice que sí, entra al chat del grupo enseguida.'),
  askSend: () => T('Отправить приглашение', 'Send the invite', 'Enviar la invitación'),
  askNot: () => T('Пока нет', 'Not yet', 'Todavía no'),

  /** Лист GR.14b «Cancel invite». */
  cancelTitle: () => T('Отменить приглашение', 'Cancel invite', 'Cancelar invitación'),
  cancelLead: (name: string) => T(
    `Отменить приглашение для ${name}?`, `Cancel ${name}’s invite?`, `¿Cancelar la invitación de ${name}?`),
  cancelNote: (p: Pron) => T(
    'Человеку придёт пуш, что приглашение закрыто. Место освободится — можно позвать кого-то ещё.',
    `${P(p).Subj} get${P(p).s} a push that the invite is closed. ${P(p).Poss} slot frees up, and you can invite someone else.`,
    'Le llegará un aviso de que la invitación está cerrada. Su hueco se libera y puedes invitar a otra persona.'),
  cancelYes: () => T('Отменить приглашение', 'Cancel the invite', 'Cancelar la invitación'),
  keep: () => T('Оставить', 'Keep it', 'Mantenerla'),

  /** Лист GR.15 — кап открытых приглашений. Plus в продукте нет: кнопка честно выключена. */
  /** Подпись для озвучки и тестов. На экране — «Kleal Plus+» с коралловым «Plus+» (имя тарифа не переводится). */
  capTitle: () => 'Kleal Plus+',
  capLead: (n: number) => T(`У тебя ${n} открытых приглашения`, `You have ${n} open invites`, `Tienes ${n} invitaciones abiertas`),
  capNote: (cap: number, max: number) => T(
    `На Free открыто не больше ${cap} приглашений разом, а в группе до ${max} человек. С Kleal Plus зови сколько хочешь — €6,99 в месяц, отмена в любой момент.`,
    `On Free you can keep ${cap} invites open at a time, and a group is up to ${max} people. With Kleal Plus you invite as many people as you like — €6.99 a month, cancel any time.`,
    `En Free puedes tener ${cap} invitaciones abiertas a la vez, y un grupo es de hasta ${max} personas. Con Kleal Plus invitas a tantas personas como quieras — €6,99 al mes, cancela cuando quieras.`),
  getPlus: () => T('Подключить Kleal Plus', 'Get Kleal Plus', 'Obtén Kleal Plus'),
  notNow: () => T('Не сейчас', 'Not now', 'Ahora no'),

  /** Обзор GR.17 / GR.17a — все приглашены. */
  sentTitle: () => T('Приглашения отправлены', 'Invites sent', 'Invitaciones enviadas'),
  sentLead: (names: string, take: number) => T(
    `${names} видят твою затею. Первые ${word(take)}, кто скажет «да», попадут в группу — чат откроется с первым.`,
    `${names} see your intent. The first ${word(take)} who say yes join the group — the chat opens with the first one.`,
    `${names} ven tu plan. Las primeras ${word(take)} que digan que sí entran al grupo — el chat se abre con la primera.`),
  /** Тот же обзор, когда кто-то уже вступил: мест меньше, и фраза «первые двое» стала бы неправдой. */
  sentLeadIn: (yes: string, names: string, left: number) => T(
    `${yes} уже в группе. ${names} видят твою затею — ${left === 1 ? 'первое «да» соберёт группу' : `ещё ${left} «да» — и группа собрана`}.`,
    `${yes} ${yes.includes(' and ') ? 'are' : 'is'} in. ${names} see your intent — ${left === 1 ? 'the first one to say yes completes the group' : `${left} more yeses and the group is complete`}.`,
    `${yes} ya ${yes.includes(' y ') ? 'están' : 'está'} dentro. ${names} ven tu plan — ${left === 1 ? 'el primer sí completa el grupo' : `${left} síes más y el grupo estará completo`}.`),
  declinedTitle: (name: string) => T(`${name} не сможет`, `${name} can’t make it`, `${name} no puede`),
  declinedLead: (yes: string, waiting: string, name: string) => T(
    `${[yes ? `${yes} уже в группе` : '', waiting ? `${waiting} ещё может ответить` : ''].filter(Boolean).join(', ')}${yes || waiting ? '. ' : ''}Вместо ${name} можно позвать кого-то ещё.`,
    `${[yes ? `${yes} ${yes.includes(' and ') ? 'are' : 'is'} in` : '', waiting ? `${waiting} can still answer` : ''].filter(Boolean).join(' and ')}${yes || waiting ? '. ' : ''}You can invite someone else in ${name}’s place.`,
    `${[yes ? `${yes} ya está dentro` : '', waiting ? `${waiting} aún puede responder` : ''].filter(Boolean).join(' y ')}${yes || waiting ? '. ' : ''}Puedes invitar a otra persona en lugar de ${name}.`),
  rowPending: () => T('Ответа пока нет', 'Hasn’t answered yet', 'Aún no ha respondido'),
  you: () => T('Ты', 'You', 'Tú'),
  organiser: () => T('организатор', 'organiser', 'organizador'),
  created: () => T('Автор затеи', 'Created the intent', 'Creaste el plan'),
  inviteMore: () => T('Позвать ещё людей', 'Invite more people', 'Invitar a más personas'),
  inviteElse: () => T('Позвать кого-то ещё', 'Invite someone else', 'Invitar a otra persona'),

  /** Меню «···» — GR.14f. Правка после приглашений меняет затею у приглашённых: это сервер. */
  menuChange: () => T('Изменить', 'Change it', 'Cambiarlo'),
  menuChangeNote: () => T('Поправить самому или сказать Kleal', 'Edit it yourself or tell Kleal', 'Edítalo tú o díselo a Kleal'),
  menuClose: () => T('Закрыть затею', 'Close the intent', 'Cerrar el plan'),
  menuCloseNote: () => T('Открытые приглашения закроются · приглашённым придёт пуш', 'Open invites close · invitees get a push', 'Las invitaciones abiertas se cierran · los invitados reciben un aviso'),
  /** GR.14j: после первого «да» группа уже есть — пункт становится «End the group» (решение 01.10). */
  menuEndNote: (names: string) => T(
    `${names}: придёт пуш · открытые приглашения закроются`,
    `${names} ${names.includes(' and ') ? 'get' : 'gets'} a push · open invites close`,
    `${names} recibe${names.includes(' y ') ? 'n' : ''} un aviso · las invitaciones abiertas se cierran`),
  closeLead: () => T('Закрыть затею?', 'Close the intent?', '¿Cerrar el plan?'),
  closeNote: () => T(
    'Открытые приглашения закроются, а всем приглашённым придёт пуш. Отменить это нельзя.',
    'Open invites close and everyone you invited gets a push. This can’t be undone.',
    'Las invitaciones abiertas se cierran y todas las personas invitadas reciben un aviso. No se puede deshacer.'),
  closeFailed: () => T('Не получилось закрыть. Попробуй ещё раз.', 'Couldn’t close it. Try again.', 'No se pudo cerrar. Inténtalo de nuevo.'),
};

/**
 * Комната — общий чат группы. Кадры GR.18 (двое, набор не закончен) и GR.21 (трое, план доступен).
 *
 * Экран ОДИН на оба состояния: на борде это один и тот же чат с другой подписью в шапке и другой
 * кнопкой внизу. Разводить их по маршрутам значило бы, что человек, глядя на свою же группу,
 * оказывается то тут, то там — та же ошибка, которой избегает один экран плана в 1:1.
 */
export const ROOM = {
  /** Выход не удался. Раньше экран уходил назад в любом случае — и неудача выглядела как удача. */
  leaveFailed: () => T('Не удалось выйти. Попробуй ещё раз.', 'Could not leave. Try again.', 'No se pudo salir. Inténtalo de nuevo.'),
  /** Подзаголовок шапки — GR.18/GR.21 дословно. При полном составе он же и зовёт делать план. */
  headCount: (n: number, min: number) =>
    n >= min
      ? T(`${n}/${min} в группе — можно делать план!`, `${n}/${min} in the Group — Make the plan now!`, `${n}/${min} en el Grupo — ¡Haz el plan ahora!`)
      : T(`${n}/${min} в группе`, `${n}/${min} in the Group`, `${n}/${min} en el Grupo`),

  /**
   * Строка состава под шапкой — GR.18: «Jane and you», ниже «2 of 3 · need 1 more».
   * Имена, а не число: человек узнаёт свою группу по тем, кто в ней, а не по счётчику.
   */
  who: (names: string[]) => {
    const you = T('ты', 'you', 'tú');
    const list = [...names];
    if (!list.length) return you;
    if (list.length === 1) return T(`${list[0]} и ${you}`, `${list[0]} and ${you}`, `${list[0]} y ${you}`);
    const last = list.pop() as string;
    return T(`${list.join(', ')}, ${last} и ${you}`, `${list.join(', ')}, ${last} and ${you}`, `${list.join(', ')}, ${last} y ${you}`);
  },
  need: (n: number, min: number) =>
    n >= min
      ? T(`${n} из ${min} · состав собран`, `${n} of ${min} · ready`, `${n} de ${min} · listo`)
      : T(`${n} из ${min} · нужен(ы) ещё ${min - n}`, `${n} of ${min} · need ${min - n} more`, `${n} de ${min} · necesitas ${min - n} más`),

  /** Системные строки ленты — GR.18/GR.21. Их пишет сервер по-английски; здесь перевод для показа. */
  sysJoined: (who: string) => T(`${who} в группе`, `${who} joined the group`, `${who} se ha unido al grupo`),
  sysLeft: (who: string) => T(`${who} вышел(ла) из группы`, `${who} left the group`, `${who} ha abandonado el grupo`),
  sysEnough: () => T('Людей достаточно — можно делать план.', 'You have enough people to make a plan.', 'Tienes suficiente gente para hacer un plan.'),
  sysRemoved: (who: string) => T(`${who} больше не в группе`, `${who} is no longer in the group`, `${who} ya no está en el grupo`),
  /**
   * Системные строки ленты — ПО КОДУ СОБЫТИЯ, а не по разбору английской фразы.
   *
   * Пять строк ниже (sysJoined и соседи) остались от прежнего способа: сервер писал предложение
   * по-английски, клиент узнавал его регуляркой. Из двадцати семи событий так узнавались пять, а
   * промах был не виден — строка про смену организатора («X left. Y is now the organiser») не
   * подходила под шаблон «X left the group» и приезжала на русский экран по-английски.
   */
  sysCantMakeIt: (who: string) => T(`${who} не сможет прийти`, `${who} can’t make it`, `${who} no puede venir`),
  sysConvertAsked: (who: string) =>
    T(`${who} предлагает перейти в один на один`, `${who} asked to switch to one-on-one`, `${who} pidió cambiar a una reunión uno a uno`),
  sysConvertDeclined: (who: string) => T(`${who} хочет оставить группу`, `${who} wants to keep the group`, `${who} quiere mantener el grupo`),
  sysConverted: () => T('Группа стала перепиской один на один.', 'The group is now a one-on-one.', 'El grupo ahora es uno a uno.'),
  sysGroupClosed: (who: string, title: string) => T(
    `${who} закрыл(а) «${title}» до назначения плана. Ты ни при чём. Чат останется архивом только для чтения, а остальные твои интенты не затронуты.`,
    `${who} closed ${title} before a plan was set. Nothing you did. The chat stays as a read-only archive, and your other intents aren’t affected.`
  , `${who} cerró ${title} antes de fijar un plan. Nada que hicieras tú. El chat queda como archivo de solo lectura, y tus otras propuestas no se ven afectadas.`),
  /** Роль перешла не по своей воле — говорим обоих поимённо, иначе группа не понимает, к кому идти. */
  sysLeftHeir: (who: string, heir: string) =>
    T(`${who} вышел(ла). Теперь организатор — ${heir}`, `${who} left. ${heir} is now the organiser`, `${who} ha abandonado. ${heir} es ahora el organizador`),
  sysQuorumBack: () => T('Снова трое — план в силе. Подтвердите ещё раз.',
                         'Three again — the plan is back on. Everyone confirms once more.', 'Tres veces más — el plan vuelve a estar activo. Todos confirman una vez más.'),
  sysBelowQuorum: () => T('Для группового плана нужны трое. Пока вы не решите, ничего не произойдёт.',
                          'A group plan needs three. Nothing happens until you choose.', 'Un plan de grupo necesita a tres personas. Nada ocurre hasta que tú lo elijas.'),
  sysPlanLocked: () => T('План закреплён — до встречи меньше двух часов.',
                         'The plan is locked — it starts in less than two hours.', 'El plan está bloqueado — empieza en menos de dos horas.'),
  sysPlanReady: () => T('Групповой план готов. Подтвердите, чтобы участвовать.',
                        'A group plan is ready. Confirm to join it.', 'Un plan de grupo está listo. Confirma para unirte.'),
  sysPlanDeclined: (who: string) => T(`${who} не пойдёт по этому плану`, `${who} will not join this plan`, `${who} no se unirá a este plan`),
  sysPlanConfirmed: (names: string) =>
    T(`Все подтвердили. План назначен: ${names}.`, `Everyone confirmed. The plan is set: ${names}.`, `Todos confirmaron. El plan está decidido: ${names}.`),
  sysChangeAccepted: () => T('Изменение приняли все.', 'Everyone accepted the change.', 'Todos aceptaron el cambio.'),
  sysPlanCancelledGroupStays: (who: string) =>
    T(`${who} отменил(а) план. Группа остаётся.`, `${who} cancelled the plan. The group is still here.`, `${who} canceló el plan. El grupo sigue ahí.`),
  sysPlanCancelled: (who: string) => T(`${who} отменил(а) план`, `${who} cancelled the plan`, `${who} canceló el plan`),
  /** GR.45b. Опоздание НИЧЕГО не отменяет — строка обязана это показывать, иначе её читают как отказ. */
  sysRunningLate: (who: string, eta: number) =>
    eta > 0
      ? T(`${who} опаздывает примерно на ${eta} мин — встреча в силе`,
          `${who} is running late by about ${eta} min — the meetup is still on`, `${who} llega tarde unos ${eta} min — la quedada sigue igual`)
      : T(`${who} опаздывает — встреча в силе`, `${who} is running late — the meetup is still on`, `${who} llega tarde — la quedada sigue igual`),
  sysArrived: (who: string) => T(`${who} на месте`, `${who} is there`, `${who} ya está allí`),
  // Текст взят С БОКСА как есть: он там уже написан вторым агентом, и своя вторая копия
  // означала бы две разных фразы на один код — тот же дубль, из-за которого файл не собрался.
  sysFeedbackReminder: (title: string) => T(
    `Прошло два дня после «${title || 'звонка'}». Он состоялся? Один ответ — и я больше не буду спрашивать. Завтра вопрос закроется сам.`,
    `Two days since ${title || 'the call'} — did it happen? One tap, and I’ll stop asking. It closes on its own tomorrow either way.`
  , `Dos días desde ${title || 'the call'} — ¿se hizo? Un toque y dejaré de preguntar. Se cierra solo mañana de todas formas.`),
  sysLinkSaved: () => T('Ссылка на звонок сохранена.', 'The call link is saved.', 'El enlace de la llamada se guardó.'),
  sysPlaceSaved: () => T('Место встречи сохранено.', 'The meeting place is saved.', 'El lugar de la reunión se guardó.'),
  sysAttendanceSide: (who: string, side: string) =>
    side === 'call'
      ? T(`${who} подключится по звонку.`, `${who} will join the call.`, `${who} se unirá a la llamada.`)
      : T(`${who} придёт лично.`, `${who} will join in person.`, `${who} se unirá en persona.`),
  sysPlanModeChanged: (who: string, mode: string) =>
    mode === 'online'
      ? T(`${who} оставил(а) для этого плана только звонок.`, `${who} made this plan online only.`, `${who} ha hecho este plan solo para reunirse online.`)
      : T(`${who} оставил(а) для этого плана только встречу вживую.`, `${who} made this plan offline only.`, `${who} ha hecho este plan solo para reunirse en persona.`),
  hybridHead: (total: number, atPlace: number, onCall: number) =>
    T(`${total} в группе · ${atPlace} лично · ${onCall} по звонку`,
      `${total} in the group · ${atPlace} coming · ${onCall} on the call`, `${total} en el grupo · ${atPlace} vienen · ${onCall} en la llamada`),
  sideLabel: (side: string) => side === 'call' ? T('по звонку', 'on the call', 'en la llamada') : T('лично', 'in person', 'en persona'),
  sysVoteKept: (who: string) => T(`${who} оставил(а) план как есть`, `${who} kept the plan as it is`, `${who} ha mantenido el plan igual`),
  sysPlanCountered: (who: string, when: string) =>
    T(`${who} предлагает изменить: ${when}. Все подтверждают заново.`,
      `${who} suggested a change: ${when}. Everyone confirms again.`, `${who} ha propuesto un cambio: ${when}. Todos confirman de nuevo.`),
  sysPlanFixed: (who: string, when: string) =>
    T(`${who} зафиксировал(а) план: ${when}.`, `${who} fixed the plan: ${when}.`, `${who} ha fijado el plan: ${when}.`),
  sysPlanUpdated: (who: string, when: string) =>
    T(`${who} изменил(а) план: ${when}. Примите, чтобы остаться, или выйдите.`,
      `${who} changed the plan: ${when}. Accept to stay in the group, or leave.`, `${who} cambió el plan: ${when}. Acepta para seguir en el grupo, o abandónalo.`),
  sysSilentStayOrLeave: (names: string) =>
    T(`${names} в этот раз не подтвердил(и) — можно остаться или выйти.`,
      `${names} did not confirm this time and can stay or leave.`, `${names} no confirmó esta hora y puede quedarse o salir.`),
  sysVoteOpened: (who: string, kind: string) =>
    T(`${who} просит группу проголосовать: ${kind === 'edit' ? 'менять' : 'отменять'} ли план.`,
      `${who} asked the group to ${kind === 'edit' ? 'change' : 'cancel'} the plan. Please vote.`, `${who} ha pedido al grupo ${kind === 'edit' ? 'cambiar' : 'cancelar'} el plan. Vota, por favor.`),
  sysVoteClosed: (yes: number, no: number, silent: number, owner: string, what: string) =>
    T(`Голосование закрыто: ${yes} за, ${no} против, ${silent} не ответили. Решает ${owner}.`,
      `The vote is closed: ${yes} for, ${no} against, ${silent} didn’t answer. It’s ${owner}’s call.`, `La votación está cerrada: ${yes} a favor, ${no} en contra, ${silent} no respondieron. Es la decisión de ${owner}.`),
  sysFull: () => T('Группа заполнена. Открытые приглашения закрыты.',
                   'This group is full. Pending invites are no longer available.', 'Este grupo está lleno. Las invitaciones pendientes ya no están disponibles.'),

  /** Нижняя кнопка. До минимума — GR.18, с минимума — GR.21 («Make the plan», дословно). */
  createPlan: () => T('Составить план', 'Make the plan', 'Hacer el plan'),
  /** У группы бывает ровно один план. Когда он есть, «создать» было бы враньём — там открывают. */
  openPlan: () => T('Открыть план', 'Open the plan', 'Abre el plan'),
  switchTo1to1: () => T('Перейти в один на один', 'Switch to one-on-one', 'Cambiar a conversación individual'),
  /**
   * Кнопка видна только когда переход ВОЗМОЖЕН: их двое, плана ещё нет, группа жива. Это решает
   * сервер (`can_convert`), а не экран, — иначе клиент и сервер разошлись бы на первом же условии.
   */
  switchWhy: () => T(
    'Группа не собралась. Можно продолжить вдвоём — если собеседник согласится.',
    'The group didn’t fill up. You can keep going as two — if the other person agrees.'
  , 'El grupo no se llenó. Podéis seguir los dos — si la otra persona está de acuerdo.'),

  // ---- GR.19: организатор спрашивает --------------------------------------
  askTitle: (who: string) => T(`Перейти в один на один с ${who}?`, `Switch to one-on-one with ${who}?`, `¿Cambiar a una conversación uno a uno con ${who}?`),
  askNote: (who: string) => T(
    `${who} тоже должен согласиться. Если согласится, открытые приглашения отменятся, и позванным об этом скажут.`,
    `${who} has to agree too. If they do, your open invites are cancelled and those people are told.`
  , `${who} también tiene que aceptar. Si lo hace, las invitaciones abiertas se cancelan y se lo comunican a esas personas.`),
  askSend: (who: string) => T(`Спросить ${who}`, `Ask ${who} to switch`, `Pide a ${who} que cambie`),
  keepGroup: () => T('Оставить группу', 'Keep the group', 'Mantén el grupo'),
  askSent: (who: string) => T(`Спросили ${who} — ждём ответа.`, `Asked ${who} — waiting for an answer.`, `Se lo has preguntado a ${who} — esperando respuesta.`),

  // ---- GR.20: спрашивают тебя ---------------------------------------------
  answerTitle: (who: string) => T(`${who} предлагает перейти в один на один`, `${who} wants to switch to one-on-one`, `${who} quiere pasar a uno a uno`),
  answerNote: () => T(
    'Группа не собралась. Если согласишься, она закроется, и вы продолжите вдвоём.',
    'The group didn’t fill up. If you agree, the group closes and the two of you keep going one-on-one.'
  , 'El grupo no se llenó. Si estás de acuerdo, el grupo se cierra y los dos seguís uno a uno.'),
  agree: () => T('Согласиться', 'Agree', 'De acuerdo'),
  switchFailed: () => T('Не получилось. Попробуй ещё раз.', 'That didn’t work. Try again.', 'Eso no funcionó. Inténtalo de nuevo.'),

  composer: () => T('Сообщение…', 'Message…', 'Mensaje…'),
  offline: () => T('Сообщение не ушло. Проверь связь.', 'The message didn’t send. Check your connection.', 'El mensaje no se envió. Comprueba tu conexión.'),
  gone: () => T('Этой группы больше нет.', 'This group is gone.', 'Este grupo ya no existe.'),
  notMember: () => T('Ты больше не в этой группе.', 'You’re not in this group any more.', 'Ya no estás en este grupo.'),

  // ---- S9 / GR.51: organiser removes a joined member ---------------------
  removeMember: () => T('Удалить', 'Remove', 'Eliminar'),
  removeTitle: (who: string) => T(`Почему ты удаляешь ${who}?`, `Why are you removing ${who}?`, `¿Por qué eliminas a ${who}?`),
  removeConfirm: (who: string) => T(`Удалить ${who}`, `Remove ${who}`, `Eliminar a ${who}`),
  removeFailed: () => T('Не получилось удалить участника. Попробуй ещё раз.',
                         'Couldn’t remove this member. Try again.', 'No se pudo eliminar a este miembro. Inténtalo de nuevo.'),
  removalReasons: () => [
    { code: 'inappropriate_messages_or_photos' as const,
      label: T('Неуместные сообщения или фотографии', 'Inappropriate messages or photos', 'Mensajes o fotos inapropiados') },
    { code: 'suspected_fake_or_stolen_profile' as const,
      label: T('Подозрение на поддельный или украденный профиль', 'Suspected fake or stolen profile', 'Perfil sospechoso de falso o robado') },
    { code: 'not_responding' as const, label: T('Не отвечает', 'Not responding', 'Sin responder') },
    { code: 'doesnt_fit_meetup' as const,
      label: T('Не подходит для этой встречи', "Doesn't fit this meetup", 'No encaja con esta quedada') },
    { code: 'something_else' as const, label: T('Другая причина', 'Something else', 'Otra cosa') },
  ],

  // ---- S9 / GR.52: removed person's view ---------------------------------
  removedNotice: (title: string) => T(
    `Тебя удалили из группы «${title}». Я не могу раскрыть причину. Остальные твои интенты не затронуты.`,
    `You were removed from ${title}. I can’t share the reason. Your other intents aren’t affected.`
  , `Te han quitado de ${title}. No puedo decirte el motivo. Tus otras propuestas no se ven afectadas.`),
  readOnlyHistory: () => T('История доступна только для чтения', 'History is read-only', 'El historial es de solo lectura'),

  // ---- S10 / GR.53-55: organiser closes the group before a plan exists --
  endGroup: () => T('Завершить группу', 'End the group', 'Finalizar el grupo'),
  endTitle: (title: string) => T(`Завершить «${title}»?`, `End ${title}?`, `¿Finalizar ${title}?`),
  endBody: (members: string) => T(
    `${members} узнают, что группа закрыта. Чат останется архивом только для чтения, а открытые приглашения отменятся. Следующие 30 дней встреча один на один всё ещё требует согласия обоих и использует план 1:1.`,
    `${members} are told the group is closed. The chat stays as a read-only archive and the open invites are cancelled. For the next 30 days, meeting either of them one-on-one still needs their agreement and uses a 1:1 plan.`
  , `${members} se les ha informado que el grupo está cerrado. El chat permanece como un archivo de solo lectura y las invitaciones abiertas se cancelan. Durante los próximos 30 días, reunirse con alguno de ellos de forma individual aún requiere su acuerdo y usa un plan 1:1.`),
  keepGoing: () => T('Продолжить', 'Keep it going', 'Sigue así'),
  endConfirm: () => T('Завершить группу', 'End the group', 'Finalizar el grupo'),
  endFailed: () => T('Не получилось завершить группу. Попробуй ещё раз.',
                      'Couldn’t end the group. Try again.', 'No se pudo finalizar el grupo. Inténtalo de nuevo.'),
  closedNotice: (owner: string, title: string) => T(
    `${owner} закрыл(а) «${title}» до назначения плана. Ты ни при чём. Чат останется архивом только для чтения, а остальные твои интенты не затронуты.`,
    `${owner} closed ${title} before a plan was set. Nothing you did. The chat stays as a read-only archive, and your other intents aren’t affected.`
  , `${owner} cerró ${title} antes de fijar un plan. No fue por nada que hicieras tú. El chat queda como archivo de solo lectura, y tus otras propuestas no se ven afectadas.`),

  // ---- «GR · Offline — new layout» (5828:9353): карточка затеи, шапка, меню, листы ----------

  /** Счёт в карточке затеи — «2/3 in the group»: до минимума от минимума, дальше от потолка. */
  barCount: (n: number, min: number, max: number) => {
    const of = n >= min ? max : min;
    return T(`${n}/${of} в группе`, `${n}/${of} in the group`, `${n}/${of} en el grupo`);
  },
  /** Зелёный призыв рядом со счётом — GR.21. */
  barMakePlan: () => T('Пора составить план', 'Make the plan now', 'Haced el plan ya'),
  barPlanOn: () => T('План в работе', 'Plan in progress', 'Plan en marcha'),
  barEnded: () => T('Группа закрыта', 'Group ended', 'Grupo cerrado'),
  barOneOnOne: (who: string) => T(`Один на один с ${who}`, `One-on-one with ${who}`, `Uno a uno con ${who}`),
  /** Янтарная метка в шапке — GR.18: «need one more». При полном составе меток нет (GR.21). */
  needMore: (k: number) =>
    k === 1 ? T('нужен ещё один', 'need one more', 'falta uno más')
    : T(`нужно ещё ${k}`, `need ${k} more`, `faltan ${k} más`),
  /** «Ты» в системной строке — выделяется серым полужирным, как «You» на GR.18. */
  youWord: () => T('Ты', 'You', 'Tú'),
  /** GR.18 «created BBQ by the beach meetup»; онлайн (GRO.18) — без «meetup»: «created Book club». */
  sysCreated: (who: string, title: string, mine: boolean, online = false) => online
    ? (mine ? T(`Ты создал(а) «${title}»`, `You created ${title}`, `Creaste ${title}`)
       : T(`${who} создал(а) «${title}»`, `${who} created ${title}`, `${who} creó ${title}`))
    : mine ? T(`Ты создал(а) встречу «${title}»`, `You created ${title} meetup`, `Creaste la quedada ${title}`)
    : T(`${who} создал(а) встречу «${title}»`, `${who} created ${title} meetup`, `${who} creó la quedada ${title}`),
  sysJoinedMe: () => T('Ты в группе', 'You joined the group', 'Te uniste al grupo'),
  /** GR.19a: кто спросил и кого — оба по имени. */
  sysAsked: (who: string, whom: string, mine: boolean, toMe: boolean) =>
    mine ? T(`Ты предложил(а) ${whom} перейти в один на один`, `You asked ${whom} to switch to one-on-one`, `Le pediste a ${whom} pasar a uno a uno`)
    : toMe ? T(`${who} предлагает тебе перейти в один на один`, `${who} asked you to switch to one-on-one`, `${who} te pidió pasar a uno a uno`)
    : T(`${who} предлагает ${whom} перейти в один на один`, `${who} asked ${whom} to switch to one-on-one`, `${who} le pidió a ${whom} pasar a uno a uno`),
  /** GR.19b: «Jane agreed · this is now a one-on-one». */
  sysAgreed: (who: string, mine: boolean) =>
    mine ? T('Ты согласил(ась/ся) · теперь это один на один', 'You agreed · this is now a one-on-one', 'Aceptaste · ahora es uno a uno')
    : T(`${who} согласил(ась/ся) · теперь это один на один`, `${who} agreed · this is now a one-on-one`, `${who} aceptó · ahora es uno a uno`),
  sysKeepMe: () => T('Ты оставил(а) группу', 'You kept the group', 'Mantuviste el grupo'),
  /** GR.51a: «You removed Jane». Удаляет только организатор — он и назван. */
  sysRemovedBy: (owner: string, who: string, mine: boolean) =>
    mine ? T(`Ты удалил(а) ${who}`, `You removed ${who}`, `Quitaste a ${who}`)
    : T(`${owner} удалил(а) ${who}`, `${owner} removed ${who}`, `${owner} quitó a ${who}`),
  /** GR.24c: две строки — кто закрыл и что чат теперь только для чтения. */
  sysEnded: (who: string, mine: boolean) =>
    mine ? T('Ты закрыл(а) группу', 'You ended the group', 'Cerraste el grupo')
    : T(`${who} закрыл(а) группу`, `${who} ended the group`, `${who} cerró el grupo`),
  sysReadOnly: () => T('Теперь чат только для чтения', 'The chat is read-only now', 'Ahora el chat es de solo lectura'),

  /** Меню «⋮» — GR.18a / GR.21a. */
  optionsTitle: () => T('Действия с группой', 'Group options', 'Opciones del grupo'),
  optInfo: () => T('О группе', 'Group info', 'Info del grupo'),
  optInfoNote: (hasInvites: boolean) => hasInvites
    ? T('Кто в группе и какие приглашения открыты', 'Who’s in and which invites are open', 'Quién está y qué invitaciones siguen abiertas')
    : T('Кто в группе', 'Who’s in the group', 'Quién está en el grupo'),
  optInviteNote: (spots: number) =>
    T(`Осталось мест: ${spots} · займёт тот, кто первым согласится`,
      `${spots} spot${spots === 1 ? '' : 's'} left · the first to accept gets it`,
      `${spots} plaza${spots === 1 ? '' : 's'} libre${spots === 1 ? '' : 's'} · la ocupa quien acepte primero`),
  optSwitchNote: (who: string) =>
    T(`Только с ${who} · тратит один из твоих планов 1:1`, `Only with ${who} · uses one of your 1:1 plans`,
      `Solo con ${who} · usa uno de tus planes 1:1`),
  optRemove: () => T('Удалить участника', 'Remove someone', 'Quitar a alguien'),
  optRemoveNote: () => T('Только пока план не назначен', 'Only before the plan is set', 'Solo antes de fijar el plan'),
  optEndNote: () => T('Закрывает чат для всех', 'Closes the chat for everyone', 'Cierra el chat para todos'),
  optLeaveNote: () => T('Чат пропадёт у тебя, остальные останутся', 'The chat goes away for you, the others stay',
                        'El chat desaparece para ti, los demás siguen'),
  optReport: () => T('Сообщить о проблеме', 'Report a problem', 'Reportar un problema'),
  optReportNote: () => T('Увидит только модерация', 'Only moderation sees it', 'Solo lo ve moderación'),

  /** GR.19 — лист перехода, три яруса: заголовок, вопрос, пояснение. */
  switchTitle: () => T('Один на один', 'Switch to one-on-one', 'Pasar a uno a uno'),
  switchNote: (who: string, invites: number) => invites > 0
    ? T(`${who} тоже должен(на) согласиться. Если согласится, открытые приглашения (${invites}) отменятся, и позванным об этом скажут, — а ещё это займёт один из твоих планов 1:1.`,
        `${who} has to agree too. If ${who} does, your ${invites} open invite${invites === 1 ? ' is' : 's are'} cancelled and those people are told — and this uses one of your 1:1 plans.`,
        `${who} también tiene que aceptar. Si acepta, tus ${invites} invitaciones abiertas se cancelan y se avisa a esas personas — y esto usa uno de tus planes 1:1.`)
    : T(`${who} тоже должен(на) согласиться. Если согласится, это займёт один из твоих планов 1:1.`,
        `${who} has to agree too. If ${who} does, this uses one of your 1:1 plans.`,
        `${who} también tiene que aceptar. Si acepta, esto usa uno de tus planes 1:1.`),
  /** GR.20 — сторона того, кого спросили. */
  answerNote2: () => T(
    'Группа ещё не собралась. Если согласишься, она закроется, и вы продолжите вдвоём. Это займёт один из твоих планов 1:1.',
    'The group hasn’t filled up yet. If you agree, the group closes and the two of you keep going one-on-one. This uses one of your 1:1 plans.',
    'El grupo aún no se ha llenado. Si aceptas, el grupo se cierra y los dos seguís uno a uno. Esto usa uno de tus planes 1:1.'),

  /** GR.24a — кого убрать. */
  removeWhoTitle: () => T('Удалить участника', 'Remove someone', 'Quitar a alguien'),
  removeWhoLead: () => T('Кто уходит из группы?', 'Who leaves the group?', '¿Quién sale del grupo?'),
  removeWhoNote: () => T(
    'Ему(ей) напишет Kleal, причину не покажут. Можно только пока план не назначен.',
    'They get a message from Kleal, no reason shown. Possible only until the plan is set.',
    'Recibe un mensaje de Kleal, sin motivo. Solo es posible hasta fijar el plan.'),
  removeGo: () => T('Удалить', 'Remove', 'Quitar'),
  /** GR.51 — причина. */
  removeReasonLead: () => T('Выбери причину', 'Pick a reason', 'Elige un motivo'),
  removeReasonNote: (who: string) => T(
    `${who} узнает, что его(её) удалили. Причину ${who} не увидит — она уходит только модерации.`,
    `${who} is told they were removed. They never see the reason — it goes to moderation only.`,
    `A ${who} se le avisa de que ha salido. Nunca ve el motivo — solo lo recibe moderación.`),
  /** Пояснение под «Who's in» — GR.24: сколько в группе, открыты ли приглашения, можно ли удалять. */
  whoNote: (n: number, max: number, open: number, canRemove: boolean) => {
    const inv = open === 0
      ? T('открытых приглашений нет', 'no invites open', 'ninguna invitación abierta')
      : T(`открытых приглашений: ${open}`, `${open} invite${open === 1 ? '' : 's'} open`, `${open} invitación${open === 1 ? '' : 'es'} abierta${open === 1 ? '' : 's'}`);
    const head = T(`В группе ${n} из ${max}, ${inv}.`, `${n} of ${max} joined, ${inv}.`, `${n} de ${max} dentro, ${inv}.`);
    return canRemove
      ? head + ' ' + T('Удалить человека можно, пока план не назначен.', 'You can remove someone until the plan is set.', 'Puedes quitar a alguien hasta fijar el plan.')
      : head;
  },
  /** GR.25 — лист «Send the plan?» над чатом: время и место из затеи, одна кнопка отправки. */
  sendTitle: () => T('Отправить план?', 'Send the plan?', '¿Enviar el plan?'),
  sendNote: (who: string) => T(`${who} получат его и смогут подтвердить или предложить своё.`,
                               `${who} will get it and can confirm or suggest a change.`,
                               `${who} lo recibirán y podrán confirmarlo o proponer un cambio.`),
  sendGo: () => T('Отправить группе', 'Send to group', 'Enviar al grupo'),
  sendChange: () => T('Изменить', 'Change', 'Cambiar'),
  sendNoTime: () => T('У затеи нет точного времени — выбери его.', 'This has no exact time yet — pick one.',
                      'Aún no hay hora exacta — elige una.'),
  /** GR.54 — закрытая группа глазами участника. */
  closedPageTitle: () => T('Группа закрыта', 'This group is closed', 'Este grupo está cerrado'),
  closedPageNote: (owner: string, title: string) =>
    T(`${owner} закрыл(а) «${title}» до назначения плана. Ты ни при чём. Чат остаётся архивом только для чтения.`,
      `${owner} closed ${title} before a plan was set. Nothing you did. The chat stays as a read-only archive.`,
      `${owner} cerró ${title} antes de fijar un plan. No fue por ti. El chat queda como archivo de solo lectura.`),
  closedTheGroup: () => T('Закрыл(а) группу', 'Closed the group', 'Cerró el grupo'),
  wasInGroup: () => T('Был(а) в группе', 'Was in the group', 'Estuvo en el grupo'),
  /** «Jane, 28» — строка участника. */
  nameAge: (name: string, age?: number) => (age ? `${name}, ${age}` : name),
  memberSince: () => T('В группе с', 'In the group since', 'En el grupo desde'),
  createdGroup: () => T('Создал(а) группу', 'Created the group', 'Creó el grupo'),

  /** GR.24b / GR.53 — закрыть группу. */
  endLead: (title: string) => T(`Закрыть «${title}»?`, `End ${title}?`, `¿Cerrar ${title}?`),
  endNote: (members: string) => T(
    `${members} узнают, что группа закрыта. Чат останется архивом только для чтения. Следующие 30 дней встреча с любым из них один на один всё равно требует его(её) согласия и занимает план 1:1.`,
    `${members} are told the group is closed. The chat stays as a read-only archive. For the next 30 days, meeting either of them one-on-one still needs their agreement and uses a 1:1 plan.`,
    `A ${members} se les avisa de que el grupo está cerrado. El chat queda como archivo de solo lectura. Durante 30 días, quedar uno a uno con cualquiera de ellos sigue necesitando su acuerdo y usa un plan 1:1.`),
  /** «Jane and Marc», «Jane, Marc and Elly» — список для текстов. */
  andList: (names: string[]) => {
    if (names.length <= 1) return names.join('');
    const last = names[names.length - 1];
    const head = names.slice(0, -1).join(', ');
    return T(`${head} и ${last}`, `${head} and ${last}`, `${head} y ${last}`);
  },

  /** Экран состава — GR.24. */
  infoTitle: () => T('Кто в группе', 'Who’s in', 'Quién está en el grupo'),
  /** Сведения о самой затее — то, ради чего группа собралась. Нажатие на заголовок ведёт сюда. */
  aboutTitle: () => T('О затее', 'About this', 'Sobre esto'),
  aboutTopics: () => T('Про что', 'What it’s about', 'De qué se trata'),
  aboutWhen: () => T('Когда', 'When', 'Cuándo'),
  aboutWhere: () => T('Где', 'Where', 'Dónde'),
  aboutMode: (mode: string) =>
    mode === 'online' ? T('Онлайн', 'Online', 'Online')
    : mode === 'hybrid' ? T('Онлайн или вживую', 'Online or in person', 'Online o presencial')
    : T('Вживую', 'In person', 'Presencial'),
  aboutSize: (min: number, max: number) =>
    T(`От ${min} до ${max} человек`, `${min} to ${max} people`, `${min} a ${max} personas`),
  aboutOwner: (who: string) => T(`Затеял(а) ${who}`, `Started by ${who}`, `Iniciado por ${who}`),
  /** Пустое поле не выдумываем: «когда» и «где» на групповой затее часто не заданы вовсе. */
  aboutUnset: () => T('не задано', 'not set', 'no establecido'),
  infoNote: (joined: number, max: number, open: number) =>
    T(
      `В группе ${joined} из ${max}, открытых приглашений: ${open}. Удалить человека можно, пока план не назначен. После этого — нельзя; участник может выйти сам.`,
      `${joined} of ${max} joined, ${open} invite${open === 1 ? '' : 's'} still open. You can remove someone until the plan is set. After that nobody can be removed — participants can leave.`
    , `${joined} de ${max} dentro, ${open} invitación${open === 1 ? '' : 'es'} sin responder. Puedes sacar a alguien hasta que el plan esté fijado. Después ya no se puede sacar a nadie — cada uno puede irse por su cuenta.`),
  roleOrganiser: () => T('Организатор', 'Organiser', 'Organizador'),
  roleMember: () => T('В группе', 'In the group', 'En el grupo'),
  inviteMore: () => T('Позвать ещё людей', 'Invite more people', 'Invita a más personas'),
  leave: () => T('Выйти из группы', 'Leave the group', 'Abandonar el grupo'),
  leaveAsk: () => T('Выйти из группы?', 'Leave the group?', '¿Abandonar el grupo?'),
  leaveBody: () =>
    T('Ты выйдешь из чата и перестанешь его видеть. Остальные останутся — это не отменяет встречу.',
      'You’ll leave the chat and stop seeing it. The others stay — this doesn’t cancel anything.', 'Dejarás el chat y dejarás de verlo. Los demás siguen — esto no cancela nada.'),
  leaveYes: () => T('Да, выйти', 'Yes, leave', 'Sí, salir'),
  cancelBtn: () => T('Отмена', 'Cancel', 'Cancelar'),
};

/**
 * Входящее групповое приглашение, сторона гостя.
 *
 * Отдельного кадра у борда НЕТ — но GR.16 описывает его содержимое словами, от лица отправителя:
 * «She sees the intent and who is already in. If she accepts she joins the shared group chat
 * straight away — there is no private chat with you». Экран построен ровно по этому обещанию, а
 * раскладка взята у 1:1-приглашения (O.C1, app/invite.tsx) — там та же задача.
 *
 * Отдельно назван случай GR.22: пока человек думал, места кончились. Об этом говорится прямо и
 * снимается вина — «Nothing you did».
 */
export const GINVITE = {
  title: (who: string, title: string) =>
    T(`${who} зовёт тебя в «${title}»`, `${who} invites you to ${title}`, `${who} te invita a ${title}`),
  /** Обещание GR.16 дословно: общий чат сразу, личной переписки нет. */
  note: () =>
    T(
      'Если согласишься, сразу откроется общий чат группы — личной переписки с приглашающим здесь нет.',
      'If you accept, the shared group chat opens straight away — there is no private chat with the person who invited you.'
    , 'Si aceptas, el grupo compartido se abre directamente — no hay chat privado con la persona que te invitó.'),
  whosIn: () => T('Кто уже внутри', 'Who is already in', 'Quién ya está dentro'),
  seats: (joined: number, max: number, min: number) =>
    T(
      `${joined} из ${max} · для плана нужно ${min}`,
      `${joined} of ${max} · a plan needs ${min}`
    , `${joined} de ${max} · un plan necesita ${min}`),
  join: () => T('Присоединиться', 'Join', 'Únete'),
  notThisTime: () => T('Не в этот раз', 'Not this time', 'No esta vez'),
  declined: () => T('Ты отказал(ась/ся). Приглашение закрыто.', 'You passed. The invite is closed.', 'Has dicho que no. La invitación está cerrada.'),
  gone: () => T('Приглашение больше не действует.', 'This invite is no longer live.', 'Esta invitación ya no está activa.'),
  /** GR.22, дословно по смыслу: группа заполнилась, пока ты думал(а), и твоей вины в этом нет. */
  full: (title: string, max: number) =>
    T(
      `«${title}» заполнилась — ${max} человек согласились раньше. Твоей вины тут нет.`,
      `${title} filled up — ${max} people joined before you. Nothing you did.`
    , `${title} se llenó — ${max} personas se unieron antes que tú. No fue por algo que tú hicieras.`),
  /** Принял, когда план уже начали: вход через апрув организатора (правило сервера). */
  awaiting: () =>
    T(
      'Ты согласился(ась), но план уже обсуждают — организатор подтвердит твой вход.',
      'You’re in as soon as the organiser approves — the group has already started planning.'
    , 'Te aceptan en cuanto el organizador lo apruebe — el grupo ya está planificando.'),
  failed: () => T('Не получилось ответить. Попробуй ещё раз.', 'Couldn’t answer. Try again.', 'No se pudo responder. Inténtalo de nuevo.'),

  // ---- GR.56 / GR.56a (борд «GR · Offline — new layout») -------------------------------------
  invitedYou: (who: string) => T(`${who} зовёт тебя`, `${who} invited you`, `${who} te invitó`),
  inviteNote2: (what: string, inWho: string, spots: number) =>
    T(`${what}. ${inWho} уже в группе, свободных мест: ${spots} — присоединись, и откроется общий чат.`,
      `${what}. ${inWho} ${inWho.includes(' and ') ? 'are' : 'is'} in and ${spots} spot${spots === 1 ? ' is' : 's are'} open — join and the group chat opens.`,
      `${what}. ${inWho} ya ${inWho.includes(' y ') ? 'están' : 'está'} dentro y quedan ${spots} plaza${spots === 1 ? '' : 's'} — únete y se abre el chat del grupo.`),
  inviteWhat: (title: string, area: string, day: string, people: number) =>
    T(`${title}${area ? ` · ${area}` : ''}${day ? `, ${day}` : ''}, ${people} чел.`,
      `${title}${area ? ` at ${area}` : ''}${day ? ` on ${day}` : ''}, ${people} people`,
      `${title}${area ? ` en ${area}` : ''}${day ? ` el ${day}` : ''}, ${people} personas`),
  closedTitle: () => T('Приглашение закрыто', 'This invite is closed', 'Esta invitación está cerrada'),
  closedNote: (why: string, title: string, owner: string) =>
    why === 'full' ? T(`«${title}» заполнилась, пока ты думал(а). Ты ни при чём — твоя затея остаётся открытой.`,
                       `${title} filled up before you answered. Nothing you did — your intent stays open.`,
                       `${title} se llenó antes de que respondieras. No fue por ti — tu propuesta sigue abierta.`)
    : why === 'converted' ? T(`«${title}» стала встречей один на один. Ты ни при чём — твоя затея остаётся открытой.`,
                              `${title} turned into a one-on-one. Nothing you did — your intent stays open.`,
                              `${title} pasó a ser uno a uno. No fue por ti — tu propuesta sigue abierta.`)
    : why === 'closed' ? T(`${owner} закрыл(а) «${title}» до назначения плана. Ты ни при чём — чат остаётся архивом.`,
                           `${owner} closed ${title} before a plan was set. Nothing you did — the chat stays as a read-only archive.`,
                           `${owner} cerró ${title} antes de fijar un plan. No fue por ti — el chat queda como archivo.`)
    /* GR.56a, четвёртая причина: организатор отозвал именно это приглашение (GR.14b). Сервер
       называет это withdrawn/cancelled — оба читаются одинаково. */
    : why === 'withdrawn' || why === 'cancelled' ? T(`${owner} отменил(а) твоё приглашение в «${title}» до твоего ответа. Ты ни при чём — твоя затея остаётся открытой.`,
                           `${owner} closed your invite to ${title} before you answered. Nothing you did — your intent stays open.`,
                           `${owner} cerró tu invitación a ${title} antes de que respondieras. No fue por ti — tu propuesta sigue abierta.`)
    : T('Приглашение больше не действует. Ты ни при чём — твоя затея остаётся открытой.',
        'This invite is no longer open. Nothing you did — your intent stays open.',
        'Esta invitación ya no está abierta. No fue por ti — tu propuesta sigue abierta.'),
  exactSpot: () => T('Точное место — когда все подтвердят', 'Exact spot after everyone confirms', 'Sitio exacto cuando todos confirmen'),
  /** Онлайн-вариант той же строки (GRO.42, GRO.56). */
  linkOpens: () => T('Ссылка откроется за 10 минут до звонка', 'The link opens 10 minutes before the call', 'El enlace se abre 10 minutos antes de la llamada'),
  /** GRO.56: «… on a call on Thu 23 July, 3 people». */
  inviteWhatCall: (title: string, day: string, people: number) =>
    T(`${title} · звонок${day ? `, ${day}` : ''}, ${people} чел.`,
      `${title} on a call${day ? ` on ${day}` : ''}, ${people} people`,
      `${title} por llamada${day ? ` el ${day}` : ''}, ${people} personas`),
  stInvitedYou: () => T('Позвал(а) тебя', 'Invited you', 'Te invitó'),
  stAnswerNeeded: () => T('Нужен твой ответ', 'Your answer needed', 'Falta tu respuesta'),
  stDidntAnswer: () => T('Не ответил(а)', 'Didn’t answer', 'No respondiste'),
  gotIt: () => T('Понятно', 'Got it', 'Entendido'),
};

/**
 * Системную строку ленты сервер пишет ПО-АНГЛИЙСКИ и по-английски же хранит — она часть истории
 * группы, одна на всех, а язык интерфейса у каждого свой. Поэтому здесь не перевод текста, а
 * распознавание события: строка разбирается на «что случилось + с кем» и рисуется на языке
 * читающего. Не разобралось — показываем как есть, а не прячем: непонятная строка честнее пустоты.
 */
/** Строка ленты, пришедшая с сервера: `sys` с кодом и фактами, `text` — английский запасной. */
export type GroupSys = { code?: string; [k: string]: any };

/**
 * Показать событие на языке читающего.
 *
 * Первым делом смотрим КОД. Он приходит с фактами рядом (`who`, `heir`, `when`), и по нему строка
 * собирается на нужном языке. Разбор английского текста регуляркой остался ниже ЗАПАСНЫМ путём:
 * в ленте лежат старые сообщения, записанные до появления кодов, и терять их историю нельзя.
 */
export function groupSysLine(text: string, sys?: GroupSys): string {
  const c = sys && sys.code;
  const f = (sys || {}) as any;
  const S = (v: any) => String(v == null ? '' : v);
  if (c === 'joined') return ROOM.sysJoined(S(f.who));
  if (c === 'left') return ROOM.sysLeft(S(f.who));
  if (c === 'left_heir') return ROOM.sysLeftHeir(S(f.who), S(f.heir));
  if (c === 'removed') return ROOM.sysRemoved(S(f.who));
  if (c === 'cant_make_it') return ROOM.sysCantMakeIt(S(f.who));
  if (c === 'quorum_reached') return ROOM.sysEnough();
  if (c === 'group_full') return ROOM.sysFull();
  if (c === 'convert_asked') return ROOM.sysConvertAsked(S(f.who));
  if (c === 'convert_declined') return ROOM.sysConvertDeclined(S(f.who));
  if (c === 'converted') return ROOM.sysConverted();
  if (c === 'group_closed') return ROOM.sysGroupClosed(S(f.who), S(f.title));
  if (c === 'quorum_back') return ROOM.sysQuorumBack();
  if (c === 'below_quorum') return ROOM.sysBelowQuorum();
  if (c === 'plan_locked') return ROOM.sysPlanLocked();
  if (c === 'plan_ready') return ROOM.sysPlanReady();
  if (c === 'plan_declined') return ROOM.sysPlanDeclined(S(f.who));
  if (c === 'plan_confirmed') return ROOM.sysPlanConfirmed(S(f.names));
  if (c === 'change_accepted') return ROOM.sysChangeAccepted();
  if (c === 'plan_cancelled_group_stays') return ROOM.sysPlanCancelledGroupStays(S(f.who));
  if (c === 'plan_cancelled') return ROOM.sysPlanCancelled(S(f.who));
  if (c === 'running_late') return ROOM.sysRunningLate(S(f.who), Number(f.eta || 0));
  if (c === 'arrived') return ROOM.sysArrived(S(f.who));
  if (c === 'feedback_reminder') return ROOM.sysFeedbackReminder(S(f.title));
  if (c === 'link_saved') return ROOM.sysLinkSaved();
  if (c === 'place_saved') return ROOM.sysPlaceSaved();
  if (c === 'attendance_side') return ROOM.sysAttendanceSide(S(f.who), S(f.side));
  if (c === 'plan_mode_changed') return ROOM.sysPlanModeChanged(S(f.who), S(f.mode));
  if (c === 'vote_kept') return ROOM.sysVoteKept(S(f.who));
  if (c === 'vote_opened') return ROOM.sysVoteOpened(S(f.who), S(f.kind));
  if (c === 'vote_closed')
    return ROOM.sysVoteClosed(Number(f.yes || 0), Number(f.no || 0), Number(f.silent || 0),
                              S(f.owner), S(f.what));
  if (c === 'plan_countered' || c === 'plan_fixed' || c === 'plan_updated') {
    const when = [S(f.when), S(f.place)].filter(Boolean).join(', ');
    if (c === 'plan_countered') return ROOM.sysPlanCountered(S(f.who), when);
    if (c === 'plan_fixed') return ROOM.sysPlanFixed(S(f.who), when);
    return ROOM.sysPlanUpdated(S(f.who), when);
  }
  if (c === 'silent_stay_or_leave') return ROOM.sysSilentStayOrLeave(S(f.names));

  const t = String(text || '').trim();
  let m = t.match(/^(.+?) joined the group\.?$/i);
  if (m) return ROOM.sysJoined(m[1]);
  m = t.match(/^(.+?) left the group\.?$/i);
  if (m) return ROOM.sysLeft(m[1]);
  m = t.match(/^(.+?) is no longer in the group\.?$/i);
  if (m) return ROOM.sysRemoved(m[1]);
  if (/enough people/i.test(t)) return ROOM.sysEnough();
  if (/group is full/i.test(t)) return ROOM.sysFull();
  return t;
}


/**
 * Привести реплику комнаты к общей форме ленты.
 *
 * Сервер зовёт автора `frm`, а в личной переписке он `from`; системную строку в комнате узнают по
 * пустому автору, а в паре — по полю `sys`. Из-за этих двух различий ленты и были написаны
 * дважды: разметка совпадала, а данные под ней — нет.
 *
 * Приводим здесь, на входе, а не ветвим показ: тогда обе ленты — один компонент, и всё, что
 * сделано для переписки, работает в комнате в тот же день.
 */
export function roomMsg(raw: any): Msg {
  const who = String(raw?.frm || '').trim();
  return {
    id: raw?.id,
    from: who,
    text: String(raw?.text || ''),
    t: Number(raw?.t || 0),
    cid: raw?.cid,
    voice: raw?.kind === 'voice' ? raw?.voice : undefined,
    video: raw?.kind === 'video' ? raw?.video : undefined,
    r: raw?.r,
    rt: raw?.rt,
    deleted: !!raw?.deleted,
    // Системная строка комнаты несёт КОД и факты (`sys` от _gi_say) — он и едет дальше: по нему
    // groupSysLine собирает строку на языке читающего. Раньше код здесь выбрасывался и заменялся
    // меткой «room», и узнавались только пять английских фраз регуляркой — «X asked to switch» или
    // «X closed the group» приезжали на русский экран по-английски. Старые строки без кода
    // по-прежнему получают метку и разбираются по тексту.
    sys: who ? undefined : ((raw?.sys && raw.sys.code ? raw.sys : { code: 'room' }) as any),
  };
}
