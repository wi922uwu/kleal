/**
 * Смена организатора группы — кадры GR.42–GR.44 борда «GR · Offline — new layout» (5828:9353).
 *
 * Два пути, оба до плана:
 *   — перехват по голосованию: организатор молчит 12 ч, участник предлагает себя, голосуют
 *     остальные (кроме организатора и кандидата) 6 ч, решают ответившие; организатор может
 *     вернуться и оставить роль или отдать её сразу;
 *   — передача роли: организатор предлагает её одному участнику, 24 ч на ответ.
 *
 * Правила считает сервер (services/matching/app.py, «СМЕНА ОРГАНИЗАТОРА»). Здесь — какой кадр
 * видит смотрящий (`roleView`) и слова кадров. Английские строки — с борда дословно.
 */
import { T } from './i18n';

export type Takeover = {
  id?: string; by?: string; by_id?: string; state?: 'open' | 'passed' | 'failed' | 'stopped' | 'withdrawn' | 'handed' | string;
  started?: number; closes_at?: number; resolved?: number;
  voters?: number; voted?: number; waiting?: string[]; my_vote?: boolean | null; i_vote?: boolean;
  result?: { yes?: number; no?: number; silent?: number }; why?: string; silent_h?: number;
};
export type RoleOffer = {
  to?: string; to_id?: string; by?: string; by_id?: string; state?: 'open' | 'accepted' | 'declined' | 'expired' | 'withdrawn' | 'closed' | string;
  at?: number; expires_at?: number; closed_at?: number; declined?: string[];
};
export type RoleFrom = { who?: string; who_id?: string; how?: 'vote' | 'handed' | 'offer' | string; at?: number };

/** Кадр страницы роли глазами смотрящего. */
export type RoleView =
  | 'silent'          // GR.42 / 42c — организатор молчит, можно предложить себя
  | 'candidate'       // GR.43 — ты предложил(а) себя, идёт голосование
  | 'voteNeeded'      // GR.43d — тебе голосовать
  | 'voted'           // GR.43k — ты проголосовал(а)
  | 'ownerBack'       // GR.42a — организатор вернулся посреди голосования
  | 'youOrganiser'    // GR.44 / 44h — роль теперь у тебя
  | 'formerOwner'     // GR.44f / 44l — роль ушла от тебя
  | 'otherPassed'     // GR.43m — роль перешла, ты третий
  | 'failedCand'      // GR.43j — твоё предложение не прошло
  | 'failedOther'     // GR.43o — предложение не прошло
  | 'stoppedCand'     // GR.43g — организатор вернулся, твоё предложение закрыто
  | 'stoppedOther'    // GR.43b — организатор вернулся
  | 'withdrewCand'    // GR.43h — ты снял(а) предложение
  | 'withdrewOther'   // GR.43o с лидом «X withdrew her offer»
  | 'pick'            // GR.44b — выбрать, кому предложить роль
  | 'offerSent'       // GR.44d — предложение ушло, ждём
  | 'offerToMe'       // GR.44c — тебе предложили роль
  | 'offerDeclined'   // GR.44e — отказались, роль твоя
  | 'offerExpired'    // GR.44g — не ответили за 24 ч
  | 'offerPassedMine' // GR.44j — ты отказался(ась) от роли
  | 'offerClosedMine' // как GR.44j: предложение тебе отозвали или оно истекло (аннотация к GR.44c)
  | 'none';

const eq = (a?: string, b?: string) => !!String(a || '').trim() && String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
/** Итог помним сутки: дольше это уже не новость, а история группы. */
const RECENT = 24 * 3600;
const recent = (t?: number) => !!t && Date.now() / 1000 - Number(t) < RECENT;

export function roleView(g: any, me: string, meId: string, pick: boolean): RoleView {
  if (!g) return 'none';
  const same = (name?: string, id?: string) => (id && meId ? id === meId : eq(name, me));
  const iOwn = !!g.i_am_owner;
  const t: Takeover | undefined = g.takeover;
  const o: RoleOffer | undefined = g.role_offer;
  const rf: RoleFrom | undefined = g.role_from;
  if (o && o.state === 'open') {
    if (same(o.to, o.to_id)) return 'offerToMe';
    if (iOwn) return 'offerSent';
  }
  if (t && t.state === 'open') {
    if (iOwn) return 'ownerBack';
    if (same(t.by, t.by_id)) return 'candidate';
    if (t.i_vote) return t.my_vote === null || t.my_vote === undefined ? 'voteNeeded' : 'voted';
  }
  if (pick && g.can_hand_over) return 'pick';
  if (t && recent(t.resolved)) {
    const cand = same(t.by, t.by_id);
    if (t.state === 'passed' || t.state === 'handed') {
      if (iOwn && cand) return 'youOrganiser';
      if (rf && same(rf.who, rf.who_id)) return 'formerOwner';
      return 'otherPassed';
    }
    if (t.state === 'failed' && !iOwn) return cand ? 'failedCand' : 'failedOther';
    if (t.state === 'stopped' && !iOwn) return cand ? 'stoppedCand' : 'stoppedOther';
    if (t.state === 'withdrawn' && !iOwn) return cand ? 'withdrewCand' : 'withdrewOther';
  }
  if (o && recent(o.closed_at || o.at)) {
    if (o.state === 'accepted') {
      if (iOwn && same(o.to, o.to_id)) return 'youOrganiser';
      if (rf && same(rf.who, rf.who_id)) return 'formerOwner';
    }
    if (iOwn && o.state === 'declined') return 'offerDeclined';
    if (iOwn && o.state === 'expired') return 'offerExpired';
    if (o.state === 'declined' && same(o.to, o.to_id)) return 'offerPassedMine';
    if ((o.state === 'withdrawn' || o.state === 'expired') && same(o.to, o.to_id)) return 'offerClosedMine';
  }
  if (g.can_take_over) return 'silent';
  return 'none';
}

export const ROLE = {
  // ---- заголовки и пояснения кадров --------------------------------------
  silentTitle: (owner: string) => T(`${owner} не отвечает`, `${owner} hasn’t answered`, `${owner} no ha respondido`),
  silentNote: (owner: string, h: number) => T(
    `Группа собрана уже ${h} ч, а ${owner} так и не составил(а) план. Можно предложить себя на роль организатора.`,
    `The group has been ready for ${h} hours and ${owner} hasn’t made the plan. You can offer to take over.`,
    `El grupo lleva ${h} horas listo y ${owner} no ha hecho el plan. Puedes ofrecerte a tomar el relevo.`),
  candTitle: () => T('Ты предложил(а) себя', 'You offered to take over', 'Te ofreciste a tomar el relevo'),
  candNote: (owner: string, voters: string) => T(
    `${owner} молчит 12 ч, и ты предложил(а) себя. Сейчас голосует ${voters} — голосование решает само. ${owner} может остановить его, вернувшись.`,
    `${owner} has been silent for 12 hours, so you put yourself forward. ${voters} ${voters.includes(' and ') ? 'are' : 'is'} voting now — it decides by itself. ${owner} can stop it by coming back.`,
    `${owner} lleva 12 horas en silencio, así que te propusiste. Ahora vota ${voters} — se decide solo. ${owner} puede pararlo si vuelve.`),
  offeredTitle: (who: string) => T(`${who} предлагает себя`, `${who} offered to take over`, `${who} se ofreció a tomar el relevo`),
  voterNote: (owner: string, who: string) => T(
    `${owner} молчит 12 ч, и ${who} предложил(а) себя. Решает твой голос — ${owner} ещё может остановить это, вернувшись.`,
    `${owner} has been silent for 12 hours, so ${who} put herself forward. Your vote decides it — ${owner} can still stop it by coming back.`,
    `${owner} lleva 12 horas en silencio, así que ${who} se propuso. Tu voto lo decide — ${owner} aún puede pararlo si vuelve.`),
  votedTitle: (yes: boolean) => yes ? T('Ты проголосовал(а) «за»', 'You voted yes', 'Votaste sí') : T('Ты проголосовал(а) «против»', 'You voted no', 'Votaste no'),
  votedNote: (owner: string) => T(`Решает большинство ответивших. ${owner} ещё может остановить это, вернувшись.`,
    `It passes on a majority of those who answer. ${owner} can still stop it by coming back.`,
    `Se aprueba por mayoría de quienes respondan. ${owner} aún puede pararlo si vuelve.`),
  backNote: (who: string) => T(`Ты не отвечал(а) 12 ч, и ${who} предложил(а) себя. Группа голосует.`,
    `You haven’t answered for 12 hours, so ${who} put herself forward. The group is voting on it.`,
    `No has respondido en 12 horas, así que ${who} se propuso. El grupo está votando.`),
  youOrgTitle: () => T('Теперь организатор — ты', 'You’re the organiser now', 'Ahora organizas tú'),
  youOrgVoteNote: (owner: string) => T(`Голосование прошло, а ${owner} не вернулся(ась) вовремя. Теперь план составляешь и меняешь ты.`,
    `The vote passed and ${owner} didn’t come back in time. You can now make the plan and change it.`,
    `La votación salió y ${owner} no volvió a tiempo. Ahora puedes hacer el plan y cambiarlo.`),
  youOrgHandNote: (owner: string) => T(`${owner} передал(а) тебе роль. Теперь план составляешь и меняешь ты.`,
    `${owner} handed the role over to you. You can now make the plan and change it.`,
    `${owner} te pasó el rol. Ahora puedes hacer el plan y cambiarlo.`),
  isOrgTitle: (who: string) => T(`Теперь организатор — ${who}`, `${who} is the organiser now`, `Ahora organiza ${who}`),
  formerOfferNote: (who: string) => T(`${who} взял(а) роль. Ты остаёшься в группе — план теперь составляет ${who}.`,
    `${who} took the role. You’re still in the group — she makes the plan now.`,
    `${who} tomó el rol. Sigues en el grupo — ahora hace el plan ${who}.`),
  formerVoteNote: (who: string) => T(`Голосование прошло, а ты не вернулся(ась) вовремя. Дальше план составляет ${who} — ты остаёшься в группе.`,
    `The vote passed and you didn’t come back in time. ${who} makes the plan from here — you’re still in the group.`,
    `La votación salió y no volviste a tiempo. Desde ahora el plan lo hace ${who} — sigues en el grupo.`),
  otherPassedNote: (who: string, owner: string) => T(`Голосование прошло, так что дальше план составляет ${who}. ${owner} остаётся в группе.`,
    `The vote passed, so ${who} makes the plan from here. ${owner} stays in the group.`,
    `La votación salió, así que desde ahora el plan lo hace ${who}. ${owner} sigue en el grupo.`),
  failedCandTitle: () => T('Твоё предложение не прошло', 'Your offer didn’t pass', 'Tu propuesta no salió'),
  failedCandNote: (yes: number, no: number, owner: string, none: boolean) => none
    ? T(`Никто не проголосовал до закрытия, так что ${owner} остаётся организатором. Тебе это ничем не грозит — можно предложить себя снова, если молчание продолжится.`,
        `Nobody voted before it closed, so ${owner} stays the organiser. Nothing is held against you — you can offer again if he stays silent.`,
        `Nadie votó antes del cierre, así que ${owner} sigue organizando. No pasa nada — puedes volver a ofrecerte si sigue en silencio.`)
    : T(`Голосование закрылось: ${yes} за · ${no} против, так что ${owner} остаётся организатором. Тебе это ничем не грозит — можно предложить себя снова, если молчание продолжится.`,
        `The vote closed ${yes} Yes · ${no} No, so ${owner} stays the organiser. Nothing is held against you — you can offer again if he stays silent.`,
        `La votación cerró ${yes} sí · ${no} no, así que ${owner} sigue organizando. No pasa nada — puedes volver a ofrecerte si sigue en silencio.`),
  staysTitle: (owner: string) => T(`${owner} остаётся организатором`, `${owner} stays the organiser`, `${owner} sigue organizando`),
  failedOtherNote: (who: string, owner: string) => T(`Предложение ${who} не прошло, так что ничего не меняется — план по-прежнему составляет ${owner}.`,
    `${who}’s offer didn’t pass, so nothing changes — the plan is still ${owner}’s to make.`,
    `La propuesta de ${who} no salió, así que nada cambia — el plan sigue siendo cosa de ${owner}.`),
  withdrewOtherNote: (who: string, owner: string) => T(`${who} сняла своё предложение, так что ${owner} остаётся организатором.`,
    `${who} withdrew her offer, so ${owner} stays the organiser.`,
    `${who} retiró su propuesta, así que ${owner} sigue organizando.`),
  keptTitle: (owner: string) => T(`${owner} оставил(а) роль за собой`, `${owner} kept the role`, `${owner} mantuvo el rol`),
  keptCandNote: () => T('Организатор вернулся до конца голосования, так что твоё предложение закрыто. Тебе это ничем не грозит — план по-прежнему составляет он.',
    'He came back before the vote closed, so your offer is closed. Nothing is held against you — the plan is still his to make.',
    'Volvió antes del cierre, así que tu propuesta se cerró. No pasa nada — el plan sigue siendo cosa suya.'),
  keptOtherNote: (who: string) => T(`Организатор вернулся до конца голосования, так что предложение ${who} закрыто. Больше ничего не меняется — план по-прежнему составляет он.`,
    `He came back before the vote closed, so ${who}’s offer is closed. Nothing else changes — the plan is still his to make.`,
    `Volvió antes del cierre, así que la propuesta de ${who} se cerró. Nada más cambia — el plan sigue siendo cosa suya.`),
  withdrewTitle: () => T('Ты снял(а) предложение', 'You withdrew your offer', 'Retiraste tu propuesta'),
  withdrewNote: (owner: string) => T(`Голосование закрыто, ${owner} остаётся организатором. Можно предложить себя позже, если молчание продолжится.`,
    `The vote is closed and ${owner} stays the organiser. You can offer again later if he stays silent.`,
    `La votación se cerró y ${owner} sigue organizando. Puedes volver a ofrecerte si sigue en silencio.`),
  pickTitle: () => T('Передать роль', 'Hand the role over', 'Pasar el rol'),
  pickNote: () => T('Ты останешься в группе в любом случае — просто перестанешь быть организатором. Выбери человека, и он решит, брать ли роль. Пока не взял — ничего не меняется.',
    'You stay in the group either way — you just stop being the organiser. Pick someone and they decide whether to take it. Until they accept, nothing changes.',
    'Sigues en el grupo pase lo que pase — solo dejas de organizar. Elige a alguien y decide si lo acepta. Hasta que acepte, nada cambia.'),
  sentTitle: (who: string) => T(`Предложение отправлено: ${who}`, `Offer sent to ${who}`, `Propuesta enviada a ${who}`),
  sentNote: (who: string) => T(`Пока ${who} не возьмёт роль, организатор — ты. Если откажется или не ответит, роль останется у тебя.`,
    `Until ${who} takes it, you’re still the organiser. If she says no or doesn’t answer, the role stays with you.`,
    `Hasta que ${who} lo acepte, sigues organizando. Si dice que no o no responde, el rol sigue contigo.`),
  toMeTitle: (owner: string) => T(`${owner} предлагает тебе роль`, `${owner} offered you the role`, `${owner} te ofreció el rol`),
  toMeNote: () => T('Он(а) остаётся в группе и просто перестаёт организовывать. Возьмёшь — план составляешь ты; нет — роль остаётся у него(неё).',
    'He stays in the group and just stops organising. Take it and you make the plan — or it stays with him.',
    'Sigue en el grupo y solo deja de organizar. Acéptalo y haces tú el plan — o se queda con él.'),
  saidNoTitle: (who: string) => T(`${who} отказался(ась)`, `${who} said no`, `${who} dijo que no`),
  saidNoNote: (next: string) => next
    ? T(`Роль остаётся у тебя, план не изменился. Можно предложить её ${next} или организовывать дальше самому.`,
        `The role stays with you and nothing about the plan changed. You can offer it to ${next}, or keep organising yourself.`,
        `El rol sigue contigo y el plan no ha cambiado. Puedes ofrecérselo a ${next} o seguir organizando.`)
    : T('Роль остаётся у тебя, план не изменился.', 'The role stays with you and nothing about the plan changed.', 'El rol sigue contigo y el plan no ha cambiado.'),
  expiredTitle: () => T('Роль никто не взял', 'Nobody took the role', 'Nadie tomó el rol'),
  // Борд GR.44g — без хвоста «можно предложить X»: это уже говорит кнопка «Offer it to Marc».
  expiredNote: (who: string) =>
    T(`${who} не ответил(а) за 24 часа, предложение истекло. Роль остаётся у тебя, план не изменился.`,
      `${who} didn’t answer within 24 hours, so the offer expired. The role stays with you and nothing about the plan changed.`,
      `${who} no respondió en 24 horas, así que la propuesta caducó. El rol sigue contigo y el plan no cambió.`),
  // «The offer is closed» — лид по причине (аннотация борда к GR.44c).
  closedWithdrawnNote: (owner: string) => T(`${owner} отозвал(а) предложение. Больше ничего не меняется — ты в группе, а план составляет ${owner}.`,
    `${owner} withdrew the offer, so it’s closed. Nothing else changes — you stay in the group, and the plan is still ${owner}’s to make.`,
    `${owner} retiró la propuesta, así que se cerró. Nada más cambia — sigues en el grupo y el plan sigue siendo cosa de ${owner}.`),
  closedExpiredNote: (owner: string) => T(`24 часа прошли, и предложение закрылось. Больше ничего не меняется — ты в группе, а план составляет ${owner}.`,
    `The 24 hours ran out, so the offer is closed. Nothing else changes — you stay in the group, and the plan is still ${owner}’s to make.`,
    `Pasaron las 24 horas, así que la propuesta se cerró. Nada más cambia — sigues en el grupo y el plan sigue siendo cosa de ${owner}.`),
  passedMineNote: () => T('Ты отказался(ась) от роли, предложение закрыто. Больше ничего не меняется — ты в группе, а план составляет организатор.',
    'You passed on the role, so the offer is closed. Nothing else changes — you stay in the group, and the plan is still his to make.',
    'Rechazaste el rol, así que la propuesta se cerró. Nada más cambia — sigues en el grupo y el plan sigue siendo cosa suya.'),

  // ---- статусы людей ------------------------------------------------------
  stSilent: (h: number) => T(`Молчит ${h} ч`, `Silent for ${h}h`, `En silencio ${h} h`),
  stInGroup: () => T('В группе', 'In the group', 'En el grupo'),
  stOffered: () => T('Предложил(а) себя', 'Offered to take over', 'Se ofreció'),
  stNotVoted: () => T('Ещё не голосовал(а)', 'Hasn’t voted yet', 'Aún no ha votado'),
  stVoted: () => T('Проголосовал(а)', 'Voted', 'Votó'),
  stVoteNeeded: () => T('Нужен твой голос', 'Your vote needed', 'Falta tu voto'),
  stVotedYes: () => T('Проголосовал(а) «за»', 'Voted yes', 'Votó sí'),
  stVotedNo: () => T('Проголосовал(а) «против»', 'Voted no', 'Votó no'),
  stBack: () => T('Вернулся(ась)', 'Back now', 'Ha vuelto'),
  stTookFrom: (who: string) => T(`Принял(а) роль от ${who}`, `Took over from ${who}`, `Relevó a ${who}`),
  stTookFromYou: () => T('Принял(а) роль от тебя', 'Took over from you', 'Te relevó'),
  stTookRole: () => T('Взял(а) роль', 'Took the role', 'Tomó el rol'),
  stHanded: (who: string) => T(`Передал(а) роль: ${who}`, `Handed the role to ${who}`, `Pasó el rol a ${who}`),
  stSelected: () => T('Выбран(а)', 'Selected', 'Elegido'),
  stTapToOffer: () => T('Нажми, чтобы предложить роль', 'Tap to offer the role', 'Toca para ofrecer el rol'),
  stCreated: () => T('Создал(а) группу', 'Created the group', 'Creó el grupo'),
  stHanding: () => T('Передаёт роль', 'Handing it over', 'Pasando el rol'),
  stDeciding: () => T('Решает', 'Deciding', 'Decidiendo'),
  stYourCall: () => T('Решать тебе', 'Your call', 'Decides tú'),
  stSaidNo: () => T('Отказался(ась)', 'Said no', 'Dijo que no'),
  stNoAnswer: () => T('Не ответил(а)', 'Didn’t answer', 'No respondió'),
  stStillYours: () => T('Роль у тебя', 'Still yours', 'Sigue siendo tuyo'),
  stKept: () => T('Оставил(а) роль', 'Kept the role', 'Mantuvo el rol'),

  // ---- полосы и кнопки ----------------------------------------------------
  meterVote: () => T('Голоса', 'Vote', 'Votos'),
  meterOffer: () => T('Ответ', 'Offer', 'Oferta'),
  ended: () => T('Закончилось', 'Ended', 'Terminó'),
  stopped: () => T('Остановлено', 'Stopped', 'Parado'),
  offerTakeOver: () => T('Предложить себя', 'Offer to take over', 'Ofrecerme'),
  withdrawMine: () => T('Снять моё предложение', 'Withdraw my offer', 'Retirar mi propuesta'),
  vote: () => T('Проголосовать', 'Vote', 'Votar'),
  keepRole: () => T('Оставить роль', 'Keep the role', 'Mantener el rol'),
  handTo: (who: string) => T(`Отдать роль: ${who}`, `Hand it over to ${who}`, `Pasárselo a ${who}`),
  makePlan: () => T('Составить план', 'Make the plan', 'Hacer el plan'),
  openChat: () => T('Открыть чат группы', 'Open group chat', 'Abrir el chat del grupo'),
  leaveGroup: () => T('Выйти из группы', 'Leave the group', 'Salir del grupo'),
  offerTo: (who: string) => T(`Предложить: ${who}`, `Offer it to ${who}`, `Ofrecérselo a ${who}`),
  neverMind: () => T('Не надо', 'Never mind', 'Déjalo'),
  withdrawOffer: () => T('Отозвать предложение', 'Withdraw the offer', 'Retirar la propuesta'),
  takeRole: () => T('Взять роль', 'Take the role', 'Tomar el rol'),
  keepWith: (who: string) => T(`Нет, пусть остаётся у ${who}`, `No, keep it with ${who}`, `No, que siga con ${who}`),
  keepOrganising: () => T('Организовывать дальше', 'Keep organising', 'Seguir organizando'),
  gotIt: () => T('Понятно', 'Got it', 'Entendido'),

  // ---- листы --------------------------------------------------------------
  putTitle: () => T('Предложить себя', 'Offer to take over', 'Ofrecerme'),
  putLead: (owner: string, h = 12) => T(`${owner} не отвечает ${h} ч`, `${owner} hasn’t answered for ${h} hours`, `${owner} lleva ${h} horas sin responder`),
  putNote: (owner: string) => T(
    `Ты предлагаешь себя. В отличие от голосований по плану, это решает само: если большинство ответивших скажут «да», организатором станешь ты. ${owner} может остановить это, вернувшись до конца.`,
    `You are putting yourself forward. Unlike plan votes, this one decides by itself — if most of the people who answer say yes, you become the organiser. ${owner} can stop it by coming back before it closes.`,
    `Te propones tú. A diferencia de las votaciones del plan, esta se decide sola — si la mayoría de quienes respondan dice que sí, organizas tú. ${owner} puede pararlo si vuelve antes del cierre.`),
  putMe: () => T('Предложить меня', 'Put me forward', 'Proponerme'),
  notNow: () => T('Не сейчас', 'Not now', 'Ahora no'),
  withdrawTitle: () => T('Снять предложение?', 'Withdraw your offer?', '¿Retirar tu propuesta?'),
  withdrawLead: () => T('Голосование закроется сразу', 'The vote closes straight away', 'La votación se cierra al momento'),
  withdrawNote: (owner: string) => T(`${owner} остаётся организатором, больше ничего не меняется. Можно предложить себя позже, если молчание продолжится.`,
    `${owner} keeps the role and nothing else changes. You can offer again later if he stays silent.`,
    `${owner} mantiene el rol y nada más cambia. Puedes volver a ofrecerte si sigue en silencio.`),
  withdraw: () => T('Снять', 'Withdraw', 'Retirar'),
  keepMine: () => T('Оставить предложение', 'Keep my offer', 'Mantener mi propuesta'),
  voteTitle: (who: string) => T(`Сделать ${who} организатором?`, `Make ${who} the organiser?`, `¿Que organice ${who}?`),
  // Лист говорит словами (борд GR.43e «Closes in 6 hours»), полоса — сокращённо («Ends in 6h»).
  voteLead: (h: number) => T(`Закроется через ${h} ч`, `Closes in ${h} hour${h === 1 ? '' : 's'}`, `Se cierra en ${h} h`),
  voteNote: (owner: string) => T(`Решает большинство ответивших — молчание не считается ни «за», ни «против». Если ${owner} вернётся до конца, он(а) может это остановить.`,
    `It passes on a majority of the people who answer — silence counts as neither side. If ${owner} comes back before it closes, he can stop it.`,
    `Se aprueba por mayoría de quienes respondan — el silencio no cuenta. Si ${owner} vuelve antes del cierre, puede pararlo.`),
  voteYes: (who: string) => T(`Да, пусть организует ${who}`, `Yes, make ${who} organiser`, `Sí, que organice ${who}`),
  voteNo: (owner: string) => T(`Нет, оставить ${owner}`, `No, keep ${owner}`, `No, que siga ${owner}`),
  alreadyTitle: (who: string) => T(`${who} уже предлагает себя`, `${who} is already standing`, `${who} ya se ha ofrecido`),
  // Борд GR.44a: «…until hers closes. Vote on Jane now…» — кандидат бывает любым, поэтому по имени.
  alreadyNote: (who: string) => T(`Одно предложение за раз, так что твоё начнётся только после того, как закроется предложение ${who}. Проголосуй за ${who} сейчас или дождись итога.`,
    `One offer at a time, so yours can’t start until ${who}’s closes. Vote on ${who} now, or wait for the result.`,
    `Una propuesta a la vez, así que la tuya no empieza hasta que se cierre la de ${who}. Vota por ${who} ahora o espera el resultado.`),
  hoursLeftLead: (h: number) => T(`Осталось ${h} ч`, `${h} hour${h === 1 ? '' : 's'} left`, `Quedan ${h} h`),
  voteOn: (who: string) => T(`Проголосовать за ${who}`, `Vote on ${who}`, `Votar por ${who}`),
  waitResult: () => T('Дождаться итога', 'Wait for the result', 'Esperar el resultado'),
  keepWithTitle: (owner: string) => T(`Оставить роль у ${owner}?`, `Keep it with ${owner}?`, `¿Que siga con ${owner}?`),
  keepWithLead: () => T('Предложение закроется сразу', 'The offer closes straight away', 'La propuesta se cierra al momento'),
  keepWithNote: (owner: string) => T(`${owner} остаётся организатором, больше ничего не меняется — ты остаёшься в группе.`,
    `${owner} stays the organiser and nothing else changes — you stay in the group.`,
    `${owner} sigue organizando y nada más cambia — sigues en el grupo.`),
  keepWithBtn: (owner: string) => T(`Оставить у ${owner}`, `Keep it with ${owner}`, `Que siga con ${owner}`),
  goBack: () => T('Назад', 'Go back', 'Volver'),
  // итоговые листы
  youOrgSheetLead: (owner: string) => T(`Голосование прошло — ${owner} не вернулся(ась) вовремя`,
    `The vote passed — ${owner} didn’t come back in time`, `La votación salió — ${owner} no volvió a tiempo`),
  youOrgSheetNote: (owner: string) => T(`Теперь план составляешь и меняешь ты. ${owner} остаётся в группе.`,
    `You can now make the plan and change it. ${owner} stays in the group.`,
    `Ahora puedes hacer el plan y cambiarlo. ${owner} sigue en el grupo.`),
  failSheetNoteCand: (owner: string) => T(`${owner} остаётся организатором. Тебе это ничем не грозит — можно предложить себя снова, если молчание продолжится.`,
    `${owner} stays the organiser. Nothing is held against you — you can offer again if he stays silent.`,
    `${owner} sigue organizando. No pasa nada — puedes volver a ofrecerte si sigue en silencio.`),
  failSheetTitleOther: (who: string) => T(`Предложение ${who} не прошло`, `${who}’s offer didn’t pass`, `La propuesta de ${who} no salió`),
  failSheetNoteOther: (owner: string) => T(`${owner} остаётся организатором. Больше ничего не меняется.`,
    `${owner} stays the organiser. Nothing else changes.`, `${owner} sigue organizando. Nada más cambia.`),
  passSheetNoteOther: (who: string, owner: string) => T(`Дальше план составляет ${who}. ${owner} остаётся в группе.`,
    `${who} makes the plan from here. ${owner} stays in the group.`, `Desde ahora el plan lo hace ${who}. ${owner} sigue en el grupo.`),
  backSheetTitle: (owner: string) => T(`${owner} вернулся(ась) и оставил(а) роль`, `${owner} is back and kept the role`, `${owner} volvió y mantuvo el rol`),
  backSheetLeadCand: () => T('Твоё предложение закрыто', 'Your offer is closed', 'Tu propuesta se cerró'),
  backSheetLeadOther: (who: string) => T(`Предложение ${who} закрыто`, `${who}’s offer is closed`, `La propuesta de ${who} se cerró`),
  backSheetNoteCand: () => T('Он(а) вернулся(ась) до конца голосования. Тебе это ничем не грозит — план по-прежнему составляет он(а).',
    'He came back before the vote closed. Nothing is held against you — the plan is still his to make.',
    'Volvió antes del cierre. No pasa nada — el plan sigue siendo cosa suya.'),
  backSheetNoteOther: () => T('Он(а) вернулся(ась) до конца голосования. Больше ничего не меняется — план по-прежнему составляет он(а).',
    'He came back before the vote closed. Nothing else changes — the plan is still his to make.',
    'Volvió antes del cierre. Nada más cambia — el plan sigue siendo cosa suya.'),
  awayLead: () => T('Голосование прошло — ты не вернулся(ась) вовремя', 'The vote passed — you didn’t come back in time',
                    'La votación salió — no volviste a tiempo'),
  awayNote: (who: string) => T(`Дальше план составляет ${who}. Ты остаёшься в группе.`, `${who} makes the plan from here. You’re still in the group.`,
                               `Desde ahora el plan lo hace ${who}. Sigues en el grupo.`),

  // ---- лента и меню -------------------------------------------------------
  optHandOver: () => T('Передать роль', 'Hand the role over', 'Pasar el rol'),
  optHandOverNote: () => T('Организует другой, ты остаёшься', 'Someone else organises, you stay in', 'Organiza otra persona, tú sigues'),
  seeOffer: () => T('Посмотреть предложение', 'See the offer', 'Ver la propuesta'),
  seeVote: () => T('К голосованию', 'See the vote', 'Ver la votación'),
  sysSilent: (who: string, h: number) => T(`${who} не составляет план уже ${h} ч`, `${who} hasn’t made the plan for ${h}h`, `${who} lleva ${h} h sin hacer el plan`),
  sysOffered: (who: string, mine: boolean) => mine ? T('Ты предложил(а) себя организатором', 'You offered to take over', 'Te ofreciste a organizar')
    : T(`${who} предлагает себя организатором`, `${who} offered to take over`, `${who} se ofreció a organizar`),
  sysPassed: (who: string, mine: boolean) => mine ? T('Теперь организатор — ты', 'You’re the organiser now', 'Ahora organizas tú')
    : T(`Теперь организатор — ${who}`, `${who} is the organiser now`, `Ahora organiza ${who}`),
  sysFailed: (owner: string) => T(`${owner} остаётся организатором`, `${owner} stays the organiser`, `${owner} sigue organizando`),
  sysStopped: (owner: string) => T(`${owner} вернулся(ась) и оставил(а) роль`, `${owner} is back and kept the role`, `${owner} volvió y mantuvo el rol`),
  sysWithdrawn: (who: string) => T(`${who} снял(а) своё предложение`, `${who} withdrew the offer`, `${who} retiró su propuesta`),
  sysRoleOffered: (who: string, to: string, toMe: boolean) => toMe
    ? T(`${who} предлагает тебе роль организатора`, `${who} offered you the organiser role`, `${who} te ofreció el rol de organizador`)
    : T(`${who} предлагает роль организатора: ${to}`, `${who} offered ${to} the organiser role`, `${who} ofreció a ${to} el rol de organizador`),
  // Ответ на предложение роли: организатору — «Jane said no» (как его пуш GR.44e), отказавшемуся — о себе.
  sysRoleDeclined: (who: string, owner: string, mine: boolean, iOwn: boolean) => mine
    ? T(`Ты оставил(а) роль у ${owner}`, `You kept the role with ${owner}`, `Dejaste el rol a ${owner}`)
    : iOwn ? T(`${who} отказал(ась)`, `${who} said no`, `${who} dijo que no`)
      : T(`${who} отказал(ась) — организатор по-прежнему ${owner}`, `${who} said no — ${owner} stays the organiser`, `${who} dijo que no — ${owner} sigue organizando`),
};
