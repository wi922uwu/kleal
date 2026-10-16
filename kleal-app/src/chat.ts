/**
 * Переписка и план встречи — кадры O.16–O.20.
 *
 * UX-каркас: копия и разбор ответов здесь, экраны в app/conversation.tsx и app/plan.tsx.
 *
 * Что описывают кадры:
 *
 *  O.16  Приглашение отклонили — на карточке «Отклонено» и «Убрать».
 *  O.17  Приглашение приняли — «Открыть чат» и «Отменить». Плюс окно бесплатного тарифа: чат
 *        можно вести с одним мэтчем за раз, второй просит закончить первый или взять Plus.
 *  O.18  Сам чат: шапка с названием интента, лента, композер.
 *  O.19  Лист действий: создать план, закончить разговор, открыть интент, продолжить.
 *  O.20  План отправлен и ждёт ответа: карточка плана, статусы обоих, «Открыть чат» и «Поправить».
 *
 * Про тариф. Ограничение «один чат на интент» — продуктовое правило с кадра O.17, и на сервере его
 * НЕТ: он позволяет писать любому, кто принял приглашение. Здесь оно живёт как правило клиента, и
 * это честно помечено — когда тариф появится на сервере, проверку надо будет перенести туда, иначе
 * ограничение обходится любым другим клиентом.
 */
import { T, dateLocale, use12h } from './i18n';
import { acc, dat, gen, ins } from './names';
import { isMe } from './api';

/** Статус заявки: как его называет сервер (см. §14.1). */
/**
 * `answered` и `not_picked` — путь «выбор из ответивших» (борд «1:1 · Offline», OF.12d–OF.15):
 * «да» приглашённого чата не открывает, организатор выбирает одного, остальным — `not_picked`.
 */
export type ReqStatus = 'pending' | 'answered' | 'accepted' | 'not_picked' | 'declined' | 'withdrawn' | 'expired';

export const CHAT = {
  /** Подпись над ответом модерации: это продукт, а не собеседник. */
  fromKleal: () => T('Ответ Kleal', 'From Kleal', 'Respuesta de Kleal'),
  /** В этой переписке отвечать некому: письмо пришло от продукта. */
  klealNoReply: () =>
    T('Это ответ от Kleal. Отвечать сюда нельзя — напиши в поддержку из настроек.',
      'This is a reply from Kleal. You cannot answer here — write to support from settings.',
      'Es una respuesta de Kleal. Aquí no se contesta — escribe a soporte desde ajustes.'),
  /** O.16 — приглашение отклонили. */
  /** O.14a: приглашение стояло до конца срока и не дождалось ответа. Не отказ — молчание. */
  expired: () => T('Без ответа · истекло', 'No answer · expired', 'Sin respuesta · caducado'),
  /** O.14a: молчание — не отказ, и позвать можно снова. Сервер истёкшую заявку не считает помехой. */
  inviteAgain: () => T('Позвать снова', 'Invite again', 'Invita de nuevo'),
  declined: () => T('Отклонено', 'Declined', 'Rechazado'),
  remove: () => T('Убрать', 'Remove', 'Eliminar'),

  /** O.17 — приглашение приняли. */
  openChat: () => T('Открыть чат', 'Open chat', 'Abrir chat'),

  /** Окно бесплатного тарифа, текст с кадра O.17. */
  busyTitle: (name: string) => T(`Ты уже переписываешься с ${ins(name)}`, `You're already chatting with ${name}`, `Ya estás charlando con ${name}`),
  busyBody: () =>
    T(
      'На бесплатном тарифе можно вести переписку только с одним мэтчем за раз. Закончи текущую, чтобы начать с другим, или подключи Kleal Plus — тогда доступны все три.',
      'On the Free plan, you can chat with only one match at a time. End your current chat to start one with another match, or upgrade to Kleal Plus to chat with all three.'
    , 'En el plan gratuito, solo puedes chatear con una coincidencia a la vez. Finaliza tu conversación actual para empezar una con otra coincidencia, o actualiza a Kleal Plus para chatear con las tres.'),
  getPlus: () => T('Подключить Kleal Plus', 'Get Kleal Plus', 'Obtén Kleal Plus'),
  plusPrice: () => T('€6,99 в месяц · переписка со всеми · отмена в любой момент',
                     '€6.99 / month · Chat with all matches · Cancel any time', '€6,99 / mes · Chatear con todas las coincidencias · Cancelar en cualquier momento'),
  endChatWith: (name: string) => T(`Закончить переписку с ${ins(name)}`, `End chat with ${name}`, `Finalizar conversación con ${name}`),
  /** Лист лимита: кнопка и правда заканчивает разговор, поэтому спрашивает — он закроется у ДВОИХ. */
  endAskTitle: (who: string) => T(`Закончить разговор с ${who}?`, `End your chat with ${who}?`, `¿Finalizar tu conversación con ${who}?`),
  endAskBody: () => T(
    'Переписка закроется у вас обоих, и место освободится для другого мэтча. История останется — её можно перечитать.',
    'The chat closes for both of you and the slot frees up for another match. The history stays — you can read it back.'
  , 'El chat se cierra para ambos y el hueco se libera para otra coincidencia. El historial queda — puedes leerlo de nuevo.'),
  endAskYes: () => T('Закончить', 'End it', 'Finalizar'),
  endAskNo: () => T('Не надо', 'Keep it', 'Manténlo'),
  endFailed: () => T('Не вышло закончить разговор. Попробуй ещё раз.', 'Couldn’t end the chat. Try again.', 'No se pudo finalizar la conversación. Inténtalo de nuevo.'),


  /** O.18 — сам чат. */
  /** Композер MSG.06 обращается по имени: «Message Jane». */
  placeholderTo: (name: string) => T(`Написать ${dat(name)}…`, `Message ${name}`, `Mensaje a ${name}`),

  /**
   * Подпись поля, пока писать нельзя.
   *
   * Правило канала держит сервер (`NOT_MATCHED`), и держит верно. Врал экран: он звал писать,
   * рисовал пузырь отправленным и подписывал его «Нажми, чтобы отправить ещё раз» — повтор, который
   * не мог удаться никогда. Снято с телефона 4 сентября 2026. Ровно так же уже поступили с планом
   * (`canPlan` в conversation.tsx): причину называем ДО действия, а не после.
   */
  lockedTo: (name: string) => T(`Написать ${dat(name)} можно после согласия`,
                                `You can write to ${name} once they accept`, `Puedes escribirle a ${name} una vez que acepte`),
  /**
   * Пустая переписка. Состояний ЧЕТЫРЕ, и текст обязан их различать.
   *
   * Сначала строка была одна — «X принял(а) приглашение» — и человек, сам нажавший
   * «Присоединиться», читал, что принял собеседник. Теперь в чат ведут ВСЕ строки «Сообщений»,
   * включая неотвеченные приглашения, и та же строка врала бы ещё грубее: приглашение висит,
   * а чат сообщает, что его приняли.
   */
  empty: (name: string, st: 'they-accepted' | 'i-accepted' | 'sent' | 'invited-me' | 'none') => {
    switch (st) {
      case 'they-accepted':
        return T(`${name} принял(а) приглашение. Напиши первым — это ваш общий разговор про интент.`,
                 `${name} accepted your invite. Say hello — this chat belongs to your intent.`, `${name} aceptó tu invitación. ¡Saluda! — este chat pertenece a tu propuesta.`);
      case 'i-accepted':
        return T(`Ты принял(а) приглашение от ${gen(name)}. Напиши первым — это ваш общий разговор про интент.`,
                 `You accepted ${name}’s invite. Say hello — this chat belongs to your intent.`, `Aceptaste la invitación de ${name}. ¡Saluda! — este chat pertenece a tu propuesta.`);
      case 'sent':
        return T(`Приглашение отправлено — ${name} ещё не ответил(а). Написать можно будет, когда согласится.`,
                 `Your invite is sent — ${name} hasn’t answered yet. You can write once they accept.`, `Tu invitación ha sido enviada — ${name} aún no ha respondido. Puedes escribir cuando acepte.`);
      case 'invited-me':
        return T(`${name} зовёт тебя. Ответь на приглашение выше — переписка откроется после согласия.`,
                 `${name} invited you. Answer the invite above — the chat opens once you accept.`, `${name} te ha invitado. Responde a la invitación de arriba — la conversación se abre una vez que aceptes.`);
      default:
        return T('Здесь пока пусто. Напиши первым.', 'Nothing here yet. Say hello.', 'Todavía no hay nada. ¡Hola!');
    }
  },
  offline: () => T('Сообщение не ушло. Проверь связь.', 'The message didn’t send. Check your connection.', 'El mensaje no se envió. Comprueba tu conexión.'),
  /**
   * Отказ сервера, а не обрыв связи. Раньше он показывался как «проверь связь» — и это была ложь
   * ровно того же сорта, что и для заблокированного: человек переподключался и писал снова, а
   * причина была не в сети. Поймано на живом телефоне: приглашение отклонили, переписка на экране
   * осталась, и каждая попытка написать говорила про связь.
   */
  writeNotMatched: () => T('Пока нельзя написать: приглашение не принято.',
                           'You can’t write yet — the invitation hasn’t been accepted.', 'Aún no puedes escribir — la invitación no ha sido aceptada.'),
  /**
   * Отказ отказу рознь, и говорить о нём одной фразой нельзя: заблокированный человек слышал
   * «проверь связь» и шёл переподключаться, хотя связь была ни при чём.
   */
  blocked: () => T('Этот человек больше не получает от тебя сообщений.', 'This person no longer receives your messages.', 'Esta persona ya no recibe tus mensajes.'),
  retry: () => T('Нажми, чтобы отправить ещё раз', 'Tap to try again', 'Pulsa para intentarlo de nuevo'),
  copy: () => T('Копировать', 'Copy', 'Copiar'),
  copied: () => T('Скопировано', 'Copied', 'Copiado'),
  reply: () => T('Ответить', 'Reply', 'Respuesta'),
  replyTo: (name: string) => T(`Ответ ${dat(name)}`, `Replying to ${name}`, `Respondiendo a ${name}`),
  deleteMsg: () => T('Удалить у всех', 'Delete for everyone', 'Borrar para todos'),
  deleteNote: () => T('Останется строка «Сообщение удалено».', 'A “message deleted” line stays.', 'Una línea de «mensaje eliminado» permanece.'),
  deleted: () => T('Сообщение удалено', 'Message deleted', 'Mensaje eliminado'),
  sendFailed: () => T('Не отправилось', 'Not sent', 'No enviado'),
  // Борд «Messages — new layout», разделы B/D: лист реплики и строки вместо неё.
  copyText: () => T('Скопировать текст', 'Copy text', 'Copiar texto'),
  yourMsgAt: (at: string) => T(`Твоё сообщение · ${at}`, `Your message · ${at}`, `Tu mensaje · ${at}`),
  theirMsgAt: (who: string, at: string) => T(`Сообщение ${who} · ${at}`, `${who}’s message · ${at}`, `Mensaje de ${who} · ${at}`),
  /** MSG.08: кому видно, что удалено. */
  deleteSeenBy: (names: string) => names
    ? T(`${names} увидят, что оно удалено`, `${names} see it was deleted`, `${names} verán que se borró`)
    : T('Все увидят, что оно удалено', 'Everyone sees it was deleted', 'Todos verán que se borró'),
  /** MSG.09: строка вместо удалённой реплики. */
  deletedBy: (who: string, mine: boolean) => mine
    ? T('Ты удалил сообщение', 'You deleted a message', 'Borraste un mensaje')
    : T(`${who} удалил сообщение`, `${who} deleted a message`, `${who} borró un mensaje`),
  /** MSG.14b: автор заблокирован. */
  hiddenFrom: (who: string) => T(`Сообщение ${who} скрыто`, `${who}’s message is hidden`, `El mensaje de ${who} está oculto`),
  reportMsg: () => T('Пожаловаться на сообщение', 'Report message', 'Reportar mensaje'),
  reportMsgNote: () => T('Уйдёт человеку, не боту', 'Goes to a person, not a bot', 'Llega a una persona, no a un bot'),
  blockWho: (who: string) => T(`Заблокировать ${who}`, `Block ${who}`, `Bloquear a ${who}`),
  blockWhoNote: () => T('Его сообщения скроются у тебя', 'Their messages are hidden for you', 'Sus mensajes se ocultan para ti'),
  blockAsk: (who: string) => T(`Заблокировать ${who}?`, `Block ${who}?`, `¿Bloquear a ${who}?`),
  blockAskLead: () => T('Ему не сообщат', 'They aren’t told', 'No se le avisa'),
  /** Сервер при блокировке закрывает всё открытое между двумя (block_user): приглашения и планы 1:1. */
  blockAskNote: (group: string) => T(
    `Его сообщения скроются у тебя во всех группах, и Kleal больше не сведёт вас. Приглашение или план один на один между вами отменятся — он увидит отмену, но не причину. Вы оба остаётесь в «${group}». Разблокировать можно в настройках.`,
    `Their messages are hidden for you in every group, and Kleal won’t match you again. Any one-on-one invite or plan between you is cancelled — they see it was cancelled, not why. You both stay in ${group}. Unblock any time in Settings.`,
    `Sus mensajes se ocultan para ti en todos los grupos y Kleal no os volverá a juntar. Cualquier invitación o plan uno a uno entre vosotros se cancela: verá la cancelación, no el motivo. Los dos seguís en ${group}. Puedes desbloquear en Ajustes.`),
  notNow: () => T('Не сейчас', 'Not now', 'Ahora no'),

  /** O.19 — лист действий. */
  actionsTitle: () => T('Действия с разговором', 'Conversation Actions', 'Acciones de conversación'),
  createPlan: () => T('Создать план', 'Create Plan', 'Crear plan'),
  /**
   * Когда план у пары УЖЕ есть, лист действий обязан вести к нему, а не предлагать второй.
   * Раньше обе стороны видели «Создать план» и после чужого предложения: один звал
   * договариваться о том, что уже назначено, второй получал отказ сервера «встреча уже
   * есть». Подтверждают план на его собственном экране — туда и ведём.
   */
  openPlan: () => T('Посмотреть план', 'View the plan', 'Ver el plan'),
  endConversation: () => T('Закончить разговор', 'End Conversation', 'Finalizar conversación'),
  viewIntent: () => T('Открыть интент', 'View intent', 'Ver la propuesta'),
  keepChatting: () => T('Продолжить разговор', 'Keep Chatting', 'Sigue charlando'),
  endAsk: (name: string) =>
    T(`Закончить разговор с ${ins(name)}? Переписка закроется, а место освободится для другого мэтча.`,
      `End the chat with ${name}? The conversation closes and frees the slot for another match.`, `¿Finalizar la conversación con ${name}? La conversación se cierra y libera el hueco para otra coincidencia.`),

  /** O.20 — план отправлен. */
  sentTo: (name: string) => T(`Отправлено: ${name}`, `Sent to ${name}`, `Enviado a ${name}`),
  /** У звонка нет «места» — обещать его в записке к онлайн-плану было просто неправдой. */
  sentNote: (name: string) =>
    T(
      `${name} видит время и то, что это звонок. Пока не подтвердит — ничего не забронировано ни у кого из вас.`,
      `${name} sees the time and that it is a call. Until they confirm, nothing is booked for either of you.`
    , `${name} ve la hora y que es una llamada. Hasta que confirme, nada está reservado para ninguno de los dos.`),
  notAnswered: () => T('Ещё не ответил(а)', 'Hasn’t answered yet', 'Todavía no ha respondido'),
  youProposed: () => T('Это предложил(а) ты', 'You proposed this', 'Tú lo propusiste'),
  youProposedShort: () => T('твой план', 'your plan', 'tu plan'),
  confirmed: () => T('Подтвердил(а)', 'Confirmed', 'Confirmado'),
  declinedPlan: () => T('Отказался(ась)', 'Declined', 'Rechazado'),
  planFailed: () => T('План не отправился. Попробуй ещё раз.', 'The plan didn’t send. Try again.', 'El plan no se envió. Inténtalo de nuevo.'),
  /** Сервер отказывает, если человек ещё не принял приглашение, — говорим об этом словами. */
  notMatched: () => T('План можно отправить только тому, кто принял приглашение.',
                      'A plan can only go to someone who accepted your invite.', 'Un plan solo puede ir a alguien que haya aceptado tu invitación.'),
  inThePast: () => T('Это время уже прошло. Выбери другое.', 'That time has already passed. Pick another.', 'Esa hora ya pasó. Elige otra.'),
  /** У пары может быть только одна живая встреча — сервер не даст завести вторую. */
  planExists: () => T('С этим человеком уже есть встреча. Поправь её, а не заводи вторую.',
                      'You already have a meetup with this person. Change that one instead.', 'Ya tienes una quedada con esta persona. Cambia esa en su lugar.'),
};

/**
 * Копия плана 1:1 вживую по доске «1:1 · Offline — new layout», разделы B и C (Figma 6873:146474 /
 * 6873:146885). Английский — дословно с кадров; русский и испанский — по смыслу. Онлайн и гибрид
 * живут на своих досках и этим блоком не трогаются.
 */
/**
 * День встречи и «после» у встречи один на один — борд «1:1 · Offline — new layout», разделы D и E
 * (OF.22–OF.24c). Пола собеседника в плане нет, поэтому «she'll wait» с кадра сказано без местоимения.
 */
/**
 * Местоимение собеседника по полу из плана 1:1 (`participants[].gender`, сервер отдаёт с 10.10).
 * Пол не указан — «they», как раньше.
 */
const pr = (g?: string) => {
  const v = String(g || '').trim().toLowerCase();
  const she = v === 'female' || v === 'f' || v === 'woman';
  const he = v === 'male' || v === 'm' || v === 'man';
  return {
    subj: she ? 'she' : he ? 'he' : 'they', Subj: she ? 'She' : he ? 'He' : 'They',
    obj: she ? 'her' : he ? 'him' : 'them', s: she || he ? 's' : '', nt: she || he ? 'doesn’t' : 'don’t',
  };
};

/**
 * ONB — план звонка один на один: раунды, фиксация, правка (борд «1:1 · Online — new layout»,
 * разделы B и C, O.19d–O.21e, O.C3–O.C6). Правила те же, что у встречи вживую (OFB); здесь только
 * то, что у звонка звучит иначе: вместо места — ссылка.
 */
export const ONB = {
  cardNoLink: () => T('Видеозвонок · ссылки пока нет', 'Video call · no link yet', 'Videollamada · aún sin enlace'),
  cardSaved: () => T('Видеозвонок · ссылка сохранена', 'Video call · link saved', 'Videollamada · enlace guardado'),
  cardTheirs: (name: string) => T(`Видеозвонок · ссылка от ${name}`, `Video call · ${name}’s link`, `Videollamada · enlace de ${name}`),
  cardOpens: (t: string) => T(`Видеозвонок · ссылка откроется в ${t}`, `Video call · link opens ${t}`, `Videollamada · el enlace se abre a las ${t}`),
  cardSame: () => T('Видеозвонок · та же ссылка', 'Video call · same link', 'Videollamada · mismo enlace'),
  cardCancelled: () => T('Видеозвонок · отменён', 'Video call · cancelled', 'Videollamada · cancelada'),
  cardDidnt: () => T('Видеозвонок · не состоялся', 'Video call · didn’t happen', 'Videollamada · no ocurrió'),
  proposedNote: () => T('Подтверди или предложи другое время. План начнётся, когда подтвердите оба; ссылка откроется за 10 минут до звонка.',
                        'Confirm it, or suggest another time. The plan starts when you both confirm; the link opens 10 minutes before the call.',
                        'Confirma o propón otra hora. El plan empieza cuando confirméis los dos; el enlace se abre 10 minutos antes de la llamada.'),
  hostLinkNote: (o: string, opens: string) => T(`У ${o} теперь есть ссылка. Она откроется вам обоим в ${opens}.`,
                                                `${o} has the link now. It opens for both of you at ${opens}.`,
                                                `${o} ya tiene el enlace. Se abre para los dos a las ${opens}.`),
  guestLinkNote: (o: string, t: string, opens: string) => T(`${o} подтвердил(а) ${t}. Ссылка откроется в ${opens} — за 10 минут до звонка.`,
                                                            `${o} confirmed ${t}. The link opens at ${opens} — 10 minutes before the call.`,
                                                            `${o} confirmó las ${t}. El enlace se abre a las ${opens} — 10 minutos antes de la llamada.`),
  changeTimeOrLink: () => T('Изменить время или ссылку', 'Change the time or link', 'Cambiar la hora o el enlace'),
  link: () => T('Ссылка', 'Link', 'Enlace'),
  yourLink: (svc: string) => svc ? T(`Твоя ссылка ${svc}`, `Your ${svc} link`, `Tu enlace de ${svc}`) : T('Твоя ссылка', 'Your link', 'Tu enlace'),
  theirLink: (name: string) => T(`Ссылка от ${name}`, `${name}’s link`, `Enlace de ${name}`),
  changeLink: () => T('Изменить ссылку', 'Change the link', 'Cambiar el enlace'),
  hostMyself: () => T('Провести звонок самому', 'Host the call myself', 'Organizar yo la llamada'),
  linkPh: () => T('Вставь ссылку Zoom, Meet или любую', 'Paste a Zoom, Meet or any link', 'Pega un enlace de Zoom, Meet u otro'),
  /** O.21e / O.C3e / O.22d — план согласован, ссылки нет. */
  stWaitLink: () => T('Ждёт ссылку', 'Waiting for the link', 'Esperando el enlace'),
  stAddLink: () => T('Добавь ссылку', 'Add the link', 'Añade el enlace'),
  stAskedYou: () => T('Просит тебя провести', 'Asked you to host', 'Te pidió que organices'),
  asksHostTitle: (o: string) => T(`${o} просит тебя провести звонок`, `${o} asks you to host`, `${o} te pide que organices`),
  asksHostNote: (o: string) => T(`План согласован, но ссылки пока нет. Добавь свою — Zoom, Meet или любую. ${o} увидит её сразу.`,
                                 `The plan is set, but there’s no link yet. Add your Zoom, Meet or any link — ${o} sees it right away.`,
                                 `El plan está fijado, pero aún no hay enlace. Añade el tuyo — Zoom, Meet u otro. ${o} lo ve enseguida.`),
  missingTitle: () => T('Ссылки всё ещё нет', 'The link is still missing', 'Sigue faltando el enlace'),
  missingNote: (o: string, min: number) => T(`Звонок через ${min} мин, а у ${o} всё ещё «ссылка скоро». Вставь любую ссылку или попроси провести.`,
                                             `The call starts in ${min} minutes and ${o} still sees “link coming”. Paste any link, or ask to host.`,
                                             `La llamada empieza en ${min} minutos y ${o} sigue viendo «enlace en camino». Pega un enlace o pide que organice.`),
  cantHost: () => T('Я не смогу провести', 'I can’t host', 'No puedo organizar'),
  stTheyAdd: () => T('Добавляет ссылку', 'Adding the link', 'Añade el enlace'),
  stAskedToHost: () => T('Ты попросил(а) провести', 'Asked to host', 'Le pediste que organice'),
  waitLinkTitle: () => T('Ждём ссылку', 'Waiting for the link', 'Esperando el enlace'),
  waitLinkNote: (o: string) => T(`Ссылку на звонок добавляет ${o}. Она появится здесь, как только её сохранят.`,
                                 `${o} adds the call link. You’ll see it here as soon as it’s saved.`,
                                 `${o} añade el enlace de la llamada. Lo verás aquí en cuanto lo guarde.`),
  cancelAsk: () => T('Отменить звонок?', 'Cancel the call?', '¿Cancelar la llamada?'),
  leaveAsk: () => T('Выйти из звонка?', 'Leave the call?', '¿Salir de la llamada?'),
  hostCancelledNote: (o: string) => T(`${o} отменил(а) звонок. Никаких последствий — ты можешь создать свою затею в любой момент.`,
                                      `${o} cancelled the call. Nothing is held against anyone — you can create your own intent any time.`,
                                      `${o} canceló la llamada. No cuenta contra nadie — puedes crear tu propuesta cuando quieras.`),
};

/**
 * OND — день звонка и «после» у звонка один на один (борд «1:1 · Online — new layout», разделы D и E,
 * O.22–O.26). Те же состояния, что у встречи вживую (OFD), но про звонок: вместо адреса — карточка
 * со ссылкой, вместо «не придёт» — «не сможет». `svc` — сервис по ссылке («Zoom», «Meet»); пусто,
 * если по ссылке его не узнать, — тогда тексты говорят просто «звонок».
 */
export const OND = {
  soonNote: (mine: boolean, name: string, svc: string) => {
    const w = svc ? `${svc} ` : '';
    const where = svc || T('по ссылке', 'outside Kleal', 'fuera de Kleal');
    return mine
      ? T(`Твоя ссылка ${w}уже открыта. Звонок идёт ${svc ? 'в ' + svc : 'по ссылке'} — Kleal хранит только ссылку и время.`,
          `Your ${w}link is open now. The call happens ${svc ? 'in ' + svc : where} — Kleal only keeps the link and the time.`,
          `Tu enlace ${w}ya está abierto. La llamada es ${svc ? 'en ' + svc : where} — Kleal solo guarda el enlace y la hora.`)
      : T(`Ссылка ${w}от ${name} уже открыта. Звонок идёт ${svc ? 'в ' + svc : 'по ссылке'} — Kleal хранит только ссылку и время.`,
          `${name}’s ${w}link is open now. The call happens ${svc ? 'in ' + svc : where} — Kleal only keeps the link and the time.`,
          `El enlace ${w}de ${name} ya está abierto. La llamada es ${svc ? 'en ' + svc : where} — Kleal solo guarda el enlace y la hora.`);
  },
  cardLink: (mine: boolean, name: string, svc: string) => {
    const head = svc || T('Видеозвонок', 'Video call', 'Videollamada');
    return mine ? T(`${head} · твоя ссылка`, `${head} · your link`, `${head} · tu enlace`)
      : T(`${head} · ссылка от ${name}`, `${head} · ${name}’s link`, `${head} · enlace de ${name}`);
  },
  cardNow: (svc: string) => `${svc || T('Видеозвонок', 'Video call', 'Videollamada')} · ${T('начинается', 'starts now', 'empieza ahora')}`,
  cardOff: (svc: string) => `${svc || T('Видеозвонок', 'Video call', 'Videollamada')} · ${T('отменён', 'called off', 'cancelada')}`,
  leaves: (svc: string) => svc
    ? T(`Откроется в ${svc} · уйдёшь из Kleal`, `Opens in ${svc} · leaves Kleal`, `Se abre en ${svc} · sales de Kleal`)
    : T('Откроется вне Kleal', 'Opens outside Kleal', 'Se abre fuera de Kleal'),
  openLink: () => T('Открыть ссылку', 'Open link', 'Abrir enlace'),
  illBeLate: () => T('Я опоздаю', 'I’ll be late', 'Llegaré tarde'),
  lateAsk: (name: string) => T(`Сказать ${name}, что опоздаешь?`, `Tell ${name} you’ll be late?`, `¿Avisar a ${name} de que llegarás tarde?`),
  theyLateNote: (min: number) => min > 0
    ? T(`Примерно на ${min} минут. Звонок в силе — ничего не отменено.`, `About ${min} minutes. The call is still on — nothing is cancelled.`,
        `Unos ${min} minutos. La llamada sigue en pie — no se cancela nada.`)
    : T('Звонок в силе — ничего не отменено.', 'The call is still on — nothing is cancelled.', 'La llamada sigue en pie — no se cancela nada.'),
  nowTitle: () => T('Твой звонок сейчас', 'Your call is now', 'Tu llamada es ahora'),
  blindTitle: (svc: string) => svc ? T(`Звонок идёт в ${svc}`, `The call is in ${svc}`, `La llamada es en ${svc}`)
    : T('Звонок идёт вне Kleal', 'The call is outside Kleal', 'La llamada es fuera de Kleal'),
  blindNote: () => T('Kleal не видит звонок, поэтому здесь о нём ничего не записывается. Потом спросим вас обоих, состоялся ли он.',
                     'Kleal can’t see the call, so nothing about it is recorded here. Afterwards we’ll ask you both whether it happened.',
                     'Kleal no ve la llamada, así que aquí no se registra nada. Después os preguntaremos a los dos si ocurrió.'),
  cantLead: () => T('Звонок идёт сейчас', 'The call is now', 'La llamada es ahora'),
  cantNote: (name: string) => T(`${name} увидит это сразу, и звонок отменится. Вернуть нельзя.`,
                                `${name} sees it straight away and the call is cancelled. You can’t undo this.`,
                                `${name} lo ve enseguida y la llamada se cancela. No se puede deshacer.`),
  theyCantTitle: (name: string) => T(`${name} не сможет`, `${name} can’t make it`, `${name} no puede`),
  theyCantNoteHost: (g?: string) => T('Только что стало известно — звонка не будет. Это никому не засчитывается, твоя затея снова открыта.',
    `${pr(g).Subj} just told you, so the call is off. Nothing is held against either of you — your intent is open again.`,
    'Te lo acaba de decir, así que no hay llamada. No cuenta contra nadie — tu propuesta vuelve a estar abierta.'),
  theyCantNoteGuest: (g?: string) => T('Только что стало известно — звонка не будет. Тебе это не засчитывается — создай новую затею в любой момент.',
    `${pr(g).Subj} just told you, so the call is off. Nothing is held against you — create a new intent any time.`,
    'Te lo acaba de decir, así que no hay llamada. No cuenta contra ti — crea una nueva propuesta cuando quieras.'),
  youCantTitle: (name: string) => T(`Ты сказал(а) ${name}, что не сможешь`, `You told ${name} you can’t make it`, `Le dijiste a ${name} que no puedes`),
  youCantNote: () => T('Звонок отменён. Тебя никто не ждёт.', 'The call is cancelled. Nobody is waiting for you.', 'La llamada está cancelada. Nadie te espera.'),
  /** O.23c — ссылка была открыта 15 минут, никто не вошёл. Пометка сервера `nobody_joined`. */
  nobodyTitle: () => T('Никто не вышел на связь', 'Nobody joined the call', 'Nadie se unió a la llamada'),
  nobodyNote: () => T('Ссылка была открыта пятнадцать минут, и никто из вас не вошёл. Kleal ничего не записывает, пока вы оба не скажете, что случилось.',
                      'The link stayed open for fifteen minutes and neither of you came in. Kleal writes nothing down until you both say what happened.',
                      'El enlace estuvo abierto quince minutos y ninguno entró. Kleal no anota nada hasta que los dos digáis qué pasó.'),
  cardNobody: (svc: string, t: string) => `${svc || T('Видеозвонок', 'Video call', 'Videollamada')} · ${t} ${T('сегодня', 'today', 'hoy')}`,
  nobodySub: () => T('Никто не вошёл', 'Nobody joined', 'Nadie se unió'),
  stDidntJoin: () => T('Не вышел(ла) на связь', 'Didn’t join', 'No se unió'),
  replyBy: (when: string) => T(`Ответить до ${when}`, `Reply by ${when}`, `Responde antes de ${when}`),
  /** Раздел E */
  didHappen: () => T('Звонок состоялся?', 'Did the call happen?', '¿Hubo llamada?'),
  didNote: (name: string, svc: string) => T(
    `Kleal не видит, что происходит ${svc ? 'в ' + svc : 'в звонке'}, поэтому спрашивает. ${name} получит тот же вопрос — итог сохранится, когда ответите оба.`,
    `Kleal can’t see inside ${svc || 'the call'}, so we ask. ${name} gets the same question — nothing is saved until you both answer.`,
    `Kleal no ve dentro de ${svc || 'la llamada'}, así que preguntamos. ${name} recibe la misma pregunta — no se guarda nada hasta que respondáis los dos.`),
  afterCard: (svc: string) => svc ? T(`Видеозвонок · ${svc}`, `Video call · ${svc}`, `Videollamada · ${svc}`)
    : T('Видеозвонок', 'Video call', 'Videollamada'),
  yesTalked: () => T('Да, поговорили', 'Yes, we talked', 'Sí, hablamos'),
  reasonNoJoin: (name: string) => T(`${name} не вышел(ла) на связь`, `${name} didn’t join the call`, `${name} no se unió a la llamada`),
  reasonLink: () => T('Ссылка не сработала', 'The link didn’t work', 'El enlace no funcionó'),
  bothNoNoteHost: () => T('Это никому не засчитывается. Затею можно открыть снова, если звонок всё ещё нужен.',
                          'Nothing is held against either of you. Your intent can open again if you still want the call.',
                          'No cuenta contra nadie. Tu propuesta puede abrirse de nuevo si aún quieres la llamada.'),
};

/**
 * HYB — встреча «и так, и так» один на один: место и ссылка сразу, сторону каждый выбирает сам
 * (борд «1:1 · Hybrid — new layout», HY.19d–HY.26). Правила раундов, отмены и ответа «состоялась ли»
 * те же, что у встречи вживую (OFB / OFD); здесь только то, что у гибрида звучит иначе.
 */
export const HYB = {
  // ---- карточка плана: строка ссылки
  linkSaved: () => T('Ссылка на звонок сохранена', 'Call link saved', 'Enlace de llamada guardado'),
  linkFrom: (name: string) => T(`Ссылка на звонок от ${name}`, `Call link from ${name}`, `Enlace de llamada de ${name}`),
  linkOpens: (t: string) => T(`Ссылка на звонок · откроется в ${t}`, `Call link · opens ${t}`, `Enlace de llamada · se abre a las ${t}`),
  linkNone: () => T('Ссылки на звонок пока нет', 'No call link yet', 'Aún no hay enlace de llamada'),
  linkSame: () => T('Та же ссылка на звонок', 'Same call link', 'Mismo enlace de llamada'),
  linkCancelled: () => T('Ссылка на звонок · отменено', 'Call link · cancelled', 'Enlace de llamada · cancelado'),
  linkClosed: () => T('Ссылка на звонок · закрыта', 'Call link · closed', 'Enlace de llamada · cerrado'),
  placeNone: () => T('Места пока нет', 'No place yet', 'Aún no hay lugar'),
  // ---- раздел B
  proposedNote: () => T('Подтверди и выбери, как участвуешь — вживую или в звонке. Точный адрес откроется, только если придёшь вживую.',
                        'Confirm and choose how you join — in person or on the call. The exact address opens only if you come in person.',
                        'Confirma y elige cómo participas — en persona o en la llamada. La dirección exacta solo se abre si vienes en persona.'),
  comeInPerson: () => T('Приду вживую', 'I’ll come in person', 'Iré en persona'),
  joinCall: () => T('Буду в звонке', 'I’ll join the call', 'Me uniré a la llamada'),
  confirmedBoth: () => T('Подтверждено · оба входа открыты', 'Confirmed · both ways open', 'Confirmado · las dos vías abiertas'),
  hostBothNote: (o: string, g?: string) => T(
    `${o} придёт вживую, и точный адрес уже открыт. Ссылка всё равно остаётся живой — любой из вас может сменить сторону без отмены.`,
    `${o} is coming in person and has the exact spot now. The link stays live anyway — either of you can switch sides without cancelling.`,
    `${o} viene en persona y ya tiene el lugar exacto. El enlace sigue activo — cualquiera puede cambiar de lado sin cancelar.`),
  hostBothCallNote: (o: string, opens: string) => T(
    `${o} будет в звонке. Ссылка откроется в ${opens}; место остаётся — можно прийти и подключиться оттуда.`,
    `${o} joins on the call. The link opens at ${opens}; the place still stands — you can go there and join from it.`,
    `${o} se une a la llamada. El enlace se abre a las ${opens}; el lugar sigue en pie.`),
  guestInPersonNote: (o: string, t: string, addr: string) => T(
    `${o} подтвердил(а) ${t}. Ты придёшь вживую, поэтому точный адрес открыт — ${addr}. Ссылка на звонок остаётся живой, если передумаешь.`,
    `${o} confirmed ${t}. You’re coming in person, so the exact spot is open — ${addr}. The call link stays live if you switch.`,
    `${o} confirmó las ${t}. Vienes en persona, así que el lugar exacto está abierto — ${addr}. El enlace sigue activo si cambias.`),
  guestCallNote: (o: string, t: string, opens: string) => T(
    `${o} подтвердил(а) ${t}. Ты будешь в звонке — ссылка откроется в ${opens}. Прийти вживую можно в любой момент.`,
    `${o} confirmed ${t}. You’re joining the call — the link opens at ${opens}. You can still come in person.`,
    `${o} confirmó las ${t}. Te unes a la llamada — el enlace se abre a las ${opens}. Aún puedes ir en persona.`),
  changeAll: () => T('Изменить время, место или ссылку', 'Change the time, place or link', 'Cambiar la hora, el lugar o el enlace'),
  changePlaceOrLink: () => T('Изменить место или ссылку', 'Change place or link', 'Cambiar lugar o enlace'),
  stInPerson: () => T('Подтвердил(а) · вживую', 'Confirmed · in person', 'Confirmado · en persona'),
  stOnCall: () => T('Подтвердил(а) · в звонке', 'Confirmed · on the call', 'Confirmado · en la llamada'),
  // ---- HY.21e / 21f / 21g: не хватает входа
  needLinkNote: (when: string, place: string) => T(
    `${when}${place ? ', ' + place : ''} — согласовано. Тому, кто не сможет прийти, не к чему подключиться, пока нет ссылки — гибриду нужно и то, и другое.`,
    `${when}${place ? ' at ' + place : ''} is set. Anyone who can’t come in person has no way to join until you add a link — hybrid needs both.`,
    `${when}${place ? ' en ' + place : ''} está fijado. Quien no pueda venir no tiene cómo unirse hasta que añadas un enlace — el híbrido necesita ambos.`),
  needPlaceTitle: () => T('Выбери место', 'Pick the place', 'Elige el lugar'),
  needPlaceNote: (when: string) => T(
    `${when} и ссылка согласованы. Тому, кто хочет прийти вживую, некуда идти, пока нет места — гибриду нужно и то, и другое.`,
    `${when} and the link are set. Anyone who wants to come in person has nowhere to go until you name a place — hybrid needs both.`,
    `${when} y el enlace están fijados. Quien quiera venir en persona no tiene adónde ir hasta que elijas un lugar — el híbrido necesita ambos.`),
  needBothNote: () => T(
    'Согласовано только время. Гибриду нужны и место, и ссылка — без них никто не знает, как до тебя добраться: ни вживую, ни в звонке.',
    'Only the time is agreed. Hybrid needs both a place and a link — without them nobody knows how to reach you, in person or on the call.',
    'Solo está acordada la hora. El híbrido necesita lugar y enlace — sin ellos nadie sabe cómo llegar a ti, ni en persona ni en la llamada.'),
  stWaitPlace: () => T('Ждёт место', 'Waiting for the place', 'Esperando el lugar'),
  stWaitDetails: () => T('Ждёт детали', 'Waiting for the details', 'Esperando los detalles'),
  stAddPlace: () => T('Добавь место', 'Add the place', 'Añade el lugar'),
  stAddBoth: () => T('Добавь оба', 'Add both', 'Añade ambos'),
  stTheyAddPlace: () => T('Выбирает место', 'Picking the place', 'Elige el lugar'),
  stTheyAddBoth: () => T('Добавляет детали', 'Adding the details', 'Añade los detalles'),
  // ---- раздел D
  soonNote: (opens: string) => T(
    `Не успеваешь дойти? Подключись к звонку — отменять не нужно. Ссылка откроется в ${opens}.`,
    `Can’t get there? Join the call instead — no need to cancel. The link opens at ${opens}.`,
    `¿No llegas? Únete a la llamada — no hace falta cancelar. El enlace se abre a las ${opens}.`),
  soonNoteCall: (opens: string) => T(`Ты участвуешь в звонке. Ссылка откроется в ${opens}.`, `You’re joining by call. The link opens at ${opens}.`,
                                    `Te unes por llamada. El enlace se abre a las ${opens}.`),
  cardCallLink: () => T('Ссылка на звонок', 'Call link', 'Enlace de llamada'),
  opensAt: (t: string) => T(`Откроется в ${t}`, `Opens ${t}`, `Se abre a las ${t}`),
  openNow: () => T('Уже открыта', 'Open now', 'Abierto ahora'),
  closedRightNow: () => T('Сейчас закрыто', 'Closed right now', 'Cerrado ahora'),
  cancelled: () => T('Отменено', 'Cancelled', 'Cancelado'),
  whoInPerson: (who: string) => T(`${who} · вживую`, `${who} · in person`, `${who} · en persona`),
  whoOpens: (who: string, t: string) => T(`${who} · откроется в ${t}`, `${who} · opens ${t}`, `${who} · se abre a las ${t}`),
  whoOnCall: (who: string) => T(`${who} · в звонке`, `${who} · on the call`, `${who} · en la llamada`),
  linkOpensBtn: (t: string) => T(`Ссылка откроется в ${t}`, `Link opens at ${t}`, `El enlace se abre a las ${t}`),
  lateToldNote: (g?: string) => T(
    'Это уже видно. Ничего не отменяется, и это не считается неявкой — если ждать неудобно, можно обоим перейти в звонок.',
    `${pr(g).Subj} see${pr(g).s} it now. Nothing is cancelled and it isn’t counted as a no-show — if waiting doesn’t suit ${pr(g).obj}, you can both move to the call.`,
    'Ya lo ve. No se cancela nada y no cuenta como ausencia — si esperar no le viene bien, podéis pasar a la llamada.'),
  lateAskNote: (name: string) => T(
    `${name} увидит это сразу и решит, ждать или перейти в звонок. Ничего не отменяется, и это не считается неявкой.`,
    `${name} sees it straight away and decides whether to wait or move to the call. Nothing is cancelled and it isn’t counted as a no-show.`,
    `${name} lo ve enseguida y decide si esperar o pasar a la llamada. No se cancela nada y no cuenta como ausencia.`),
  theyLateNote: (min: number, g?: string) => T(
    `${min > 0 ? `Примерно на ${min} минут. ` : ''}Встреча в силе — подожди или перейдите оба в звонок.`,
    `${min > 0 ? `About ${min} minutes. ` : ''}The meetup is still on — wait for ${pr(g).obj}, or both move to the call.`,
    `${min > 0 ? `Unos ${min} minutos. ` : ''}La quedada sigue en pie — espera o pasad los dos a la llamada.`),
  youCallTitle: () => T('Ты участвуешь в звонке', 'You’re joining by call', 'Te unes por llamada'),
  youCallNote: (o: string, opens: string, g?: string) => T(
    `${o} знает и всё равно придёт вживую — встреча в силе, ты подключишься по видео. Ссылка откроется в ${opens}.`,
    `${o} knows. ${pr(g).Subj}’${pr(g).subj === 'they' ? 're' : 's'} still coming in person, so the meetup is on — you join ${pr(g).obj} by video. The link opens at ${opens}.`,
    `${o} lo sabe y viene en persona igualmente — te unes por vídeo. El enlace se abre a las ${opens}.`),
  theyCallTitle: (o: string) => T(`${o} перешёл(ла) в звонок`, `${o} switched to the call`, `${o} pasó a la llamada`),
  theyCallNote: (place: string, opens: string, g?: string) => T(
    `Подключится по видео, так что встреча в силе. Иди в ${place} и подключись оттуда или подключись откуда удобно. Ссылка откроется в ${opens}.`,
    `${pr(g).Subj}’ll join by video, so the meetup is still on. Go to ${place} and join from there, or join from wherever you are. The link opens at ${opens}.`,
    `Se unirá por vídeo, así que la quedada sigue en pie. Ve a ${place} y únete desde allí, o desde donde estés. El enlace se abre a las ${opens}.`),
  /** После HY.23c: место закрыто, оба переведены в звонок. */
  movedNote: () => T('Место оказалось закрыто, поэтому вы оба перешли в звонок. Ссылка уже открыта.',
                     'The place was closed, so you both moved to the call. The link is already open.',
                     'El lugar estaba cerrado, así que los dos pasasteis a la llamada. El enlace ya está abierto.'),
  bothCallNote: (opens: string) => T(`Вы оба в звонке. Ссылка откроется в ${opens}.`, `You’re both on the call. The link opens at ${opens}.`,
                                    `Los dos estáis en la llamada. El enlace se abre a las ${opens}.`),
  nowNote: (place: string, name: string, g?: string) => T(
    `Уже начинается — в ${place} или в звонке. Если не сможешь совсем, скажи ${name}, чтобы тебя не ждали.`,
    `It’s starting now — at ${place} or on the call. If you can’t make it at all, tell ${name} so ${pr(g).subj} ${pr(g).nt} wait.`,
    `Empieza ahora — en ${place} o en la llamada. Si no puedes de ningún modo, avisa a ${name} para que no espere.`),
  twoWaysTitle: () => T('Два входа, одна встреча', 'Two ways in, one meetup', 'Dos vías, una quedada'),
  twoWaysNote: (place: string) => T(
    `Встречайтесь в ${place} или в звонке. Kleal не видит ни то, ни другое, поэтому потом спросит вас обоих, состоялась ли встреча.`,
    `Meet at ${place} or on the call. Kleal can’t see either one, so afterwards we’ll ask you both whether it happened.`,
    `Quedad en ${place} o en la llamada. Kleal no ve ninguna de las dos, así que después os preguntaremos si ocurrió.`),
  closedTitle: () => T('Место закрыто', 'The place is closed', 'El lugar está cerrado'),
  closedNote: () => T('Вы оба на месте, но дверь закрыта. У гибрида есть выход — перейдите в звонок, ссылка уже открыта.',
                      'You’re both there, but the door is shut. Hybrid gives you a way out — move to the call, the link is already open.',
                      'Los dos estáis allí, pero la puerta está cerrada. El híbrido os da una salida — pasad a la llamada, el enlace ya está abierto.'),
  cantNote: (name: string) => T(
    `Это отменит встречу для вас обоих, и ${name} увидит это сразу. Если просто не успеваешь дойти — подключись к звонку.`,
    `This cancels the meetup for both of you, and ${name} sees it straight away. If you just can’t get there, join the call instead.`,
    `Esto cancela la quedada para los dos, y ${name} lo ve enseguida. Si simplemente no llegas, únete a la llamada.`),
  // ---- раздел E
  afterCard: (place: string) => place
    ? T(`${place} или звонок`, `${place} or the call`, `${place} o la llamada`)
    : T('Место или звонок', 'In person or the call', 'En persona o la llamada'),
  didNote: (name: string) => T(
    `Гибрид мог пойти любым путём, поэтому мы спрашиваем, а не гадаем. ${name} получит тот же вопрос — итог сохранится, когда ответите оба.`,
    `Hybrid can go either way, so we ask instead of guessing. ${name} gets the same question — nothing is saved until you both answer.`,
    `El híbrido puede ir de cualquier manera, así que preguntamos en vez de adivinar. ${name} recibe la misma pregunta — no se guarda nada hasta que respondáis los dos.`),
  reasonNoShow: (name: string) => T(`${name} не пришёл(ла) и не подключился(ась)`, `${name} didn’t come or join`, `${name} no vino ni se unió`),
  reasonBroken: () => T('Место или ссылка не сработали', 'The place or link didn’t work', 'El lugar o el enlace no funcionó'),
  howMet: () => T('Как вы встретились?', 'How did you meet?', '¿Cómo quedasteis?'),
  howInPerson: () => T('Вживую', 'In person', 'En persona'),
  howCall: () => T('В звонке', 'On the call', 'En la llamada'),
  howBoth: () => T('И так, и так', 'A bit of both', 'Un poco de ambos'),
  howNote: () => T('Твои ответы видит только Kleal, и любой формат считается встречей. Если что-то пошло не так — лучше пожалуйся.',
                   'Only Kleal sees your answers, and any format counts as a meetup. If something went wrong, report it instead.',
                   'Solo Kleal ve tus respuestas, y cualquier formato cuenta como quedada. Si algo fue mal, mejor denúncialo.'),
  reportReason: () => T('Опасное поведение на встрече или в звонке', 'Unsafe behaviour at the meetup or on the call', 'Comportamiento peligroso en la quedada o en la llamada'),
};

export const OFD = {
  lateHint: (name: string, g?: string) => T(`Если опаздываешь, скажи ${dat(name)} — тебя подождут на том же месте.`,
                                `If you’re running late, tell ${name} — ${pr(g).subj}’ll wait at the same place.`,
                                `Si llegas tarde, avisa a ${name} — te esperará en el mismo sitio.`),
  lateToldNote: (g?: string) => T('Это уже видно. Ничего не отменяется, и это не считается неявкой.',
                        `${pr(g).Subj} see${pr(g).s} it now. Nothing is cancelled, and it isn’t counted as a no-show.`,
                        'Ya lo ve. No se cancela nada y no cuenta como no presentarse.'),
  theyLateNote: (min: number) => min > 0
    ? T(`Примерно на ${min} минут. Встреча в силе — ничего не отменено.`, `About ${min} minutes. The meetup is still on — nothing is cancelled.`,
        `Unos ${min} minutos. La quedada sigue en pie — no se cancela nada.`)
    : T('Встреча в силе — ничего не отменено.', 'The meetup is still on — nothing is cancelled.', 'La quedada sigue en pie — no se cancela nada.'),
  nowNote: (name: string, g?: string) => T(`Уже начинается. Если не сможешь прийти, скажи ${dat(name)}, чтобы тебя не ждали.`,
                               `It’s starting now. If you can’t make it, tell ${name} so ${pr(g).subj} ${pr(g).nt} wait.`,
                               `Ya empieza. Si no puedes ir, avisa a ${name} para que no espere.`),
  startsNow: () => T('Начинается сейчас', 'Starts now', 'Empieza ahora'),
  blindTitle: () => T('Kleal не видит встречу', 'Kleal can’t see the meetup', 'Kleal no ve la quedada'),
  blindNote: () => T('Здесь о ней ничего не записывается. Потом спросим вас обоих, состоялась ли она.',
                     'Nothing about it is recorded here. Afterwards we’ll ask both of you whether it happened.',
                     'Aquí no se registra nada. Después os preguntaremos a los dos si ocurrió.'),
  openChat: () => T('Открыть чат', 'Open chat', 'Abrir chat'),
  /** OF.22c — лист «опаздываю»: на сколько. */
  lateAsk: (name: string) => T(`Сказать ${dat(name)}, что опаздываешь?`, `Tell ${name} you’re running late?`, `¿Avisar a ${name} de que llegas tarde?`),
  lateAskNote: (name: string) => T(`${name} увидит это сразу. Ничего не отменяется, и это не считается неявкой.`,
                                   `${name} sees it straight away. Nothing is cancelled and it isn’t counted as a no-show.`,
                                   `${name} lo ve al instante. No se cancela nada y no cuenta como no presentarse.`),
  howLate: () => T('На сколько?', 'How late?', '¿Cuánto?'),
  mins: (n: number) => T(`${n} мин`, `${n} min`, `${n} min`),
  tell: (name: string) => T(`Сказать ${dat(name)}`, `Tell ${name}`, `Avisar a ${name}`),
  neverMind: () => T('Не надо', 'Never mind', 'Déjalo'),
  stLate: (min: number) => min > 0 ? T(`Опаздывает · ${min} мин`, `Running late · ${min} min`, `Llega tarde · ${min} min`)
                                   : T('Опаздывает', 'Running late', 'Llega tarde'),
  stCantJustNow: () => T('Не придёт · только что', 'Can’t make it · just now', 'No puede ir · ahora mismo'),
  stCantTold: (g?: string) => T('Не придёт · сказано', `Can’t make it · told ${pr(g).obj}`, 'No puede ir · avisó'),
  /** OF.23b — «не смогу» в день встречи: один на один это отмена. */
  cantAsk: (name: string) => T(`Сказать ${dat(name)}, что не придёшь?`, `Tell ${name} you can’t come?`, `¿Avisar a ${name} de que no puedes ir?`),
  cantLead: () => T('Встреча идёт сейчас', 'It’s happening now', 'Está ocurriendo ahora'),
  cantLeadSoon: (min: number) => T(`Начало через ${min} мин`, `Starts in ${min} minutes`, `Empieza en ${min} minutos`),
  cantNote: (name: string) => T(`${name} увидит это сразу, и встреча отменится. Вернуть нельзя.`,
                                `${name} sees it straight away and the meetup is cancelled. You can’t undo this.`,
                                `${name} lo ve al instante y la quedada se cancela. No se puede deshacer.`),
  cantYes: () => T('Я не смогу', 'I can’t make it', 'No puedo ir'),
  /** OF.23d / OF.C9 — второй не придёт. */
  theyCantTitle: (name: string) => T(`${name} не придёт`, `${name} can’t come`, `${name} no puede venir`),
  theyCantNoteHost: (g?: string) => T('Только что стало известно — встречи не будет. Это никому не засчитывается, твоя затея снова открыта.',
                            `${pr(g).Subj} just told you, so the meetup is off. Nothing is held against either of you — your intent is open again.`,
                            'Te lo acaba de decir, así que no hay quedada. No cuenta contra ninguno — tu propuesta vuelve a estar abierta.'),
  theyCantNoteGuest: (g?: string) => T('Только что стало известно — встречи не будет. Тебе это не засчитывается — создай новую затею в любой момент.',
                             `${pr(g).Subj} just told you, so the meetup is off. Nothing is held against you — create a new intent any time.`,
                             'Te lo acaba de decir, así que no hay quedada. No cuenta contra ti — crea una propuesta cuando quieras.'),
  youCantTitle: (name: string) => T(`Ты сказал(а) ${dat(name)}, что не придёшь`, `You told ${name} you can’t come`, `Le dijiste a ${name} que no puedes ir`),
  youCantNote: () => T('Встреча отменена. Тебя никто не ждёт.', 'The meetup is cancelled. Nobody is waiting for you.', 'La quedada está cancelada. Nadie te espera.'),
  reopenIntent: () => T('Снова открыть мою затею', 'Reopen my intent', 'Reabrir mi propuesta'),
  /** OF.23c — оба на месте, а место закрыто. */
  spotClosedBtn: () => T('Место закрыто', 'The spot is closed off', 'El sitio está cerrado'),
  spotClosedTitle: () => T('Место закрыто', 'The spot is closed off', 'El sitio está cerrado'),
  spotClosedNote: () => T('Вы оба на месте, но точка встречи закрыта. Kleal план не двигает — договоритесь в чате о месте рядом.',
                          'You’re both there, but the meeting point is closed off. Kleal doesn’t move the plan — agree on a spot nearby in the chat.',
                          'Estáis los dos, pero el punto de encuentro está cerrado. Kleal no mueve el plan — acordad un sitio cercano en el chat.'),
  didntHappen: () => T('Не состоялась', 'It didn’t happen', 'No ocurrió'),

  // ---- Раздел E: после встречи (OF.24–OF.25, OF.C10) ------------------------------------------
  didYouMeet: () => T('Вы встретились?', 'Did you meet?', '¿Os visteis?'),
  didYouMeetNote: (name: string) => T(`${name} получит тот же вопрос. Итог сохраним, когда ответите оба.`,
                                      `${name} gets the same question. We only save the result once you both answer.`,
                                      `${name} recibe la misma pregunta. Guardamos el resultado cuando respondáis los dos.`),
  yesMet: () => T('Да, встретились', 'Yes, we met', 'Sí, nos vimos'),
  answered: () => T('Ответили', 'Answered', 'Respondieron'),
  stAnswered: () => T('Ответил(а)', 'Answered', 'Respondió'),
  stHasnt: () => T('Ещё не ответил(а)', 'Hasn’t answered', 'No ha respondido'),
  stNeeded: () => T('Нужен твой ответ', 'Your answer needed', 'Falta tu respuesta'),
  savedTitle: () => T('Твой ответ сохранён', 'Your answer is saved', 'Tu respuesta está guardada'),
  savedNote: (name: string, g?: string) => T(`Итог сохранится, когда ответит и ${name}. Твой ответ ${dat(name)} не виден.`,
                                 `The result is saved once ${name} answers too. ${pr(g).Subj} ${pr(g).nt} see your answer.`,
                                 `El resultado se guarda cuando ${name} también responda. No ve tu respuesta.`),
  bothDoneNote: () => T('Вы оба ответили — итог сохранён.', 'You both answered — the result is saved.', 'Habéis respondido los dos — el resultado está guardado.'),
  bothNoTitle: () => T('Вы оба сказали, что встречи не было', 'You both said it didn’t happen', 'Los dos dijisteis que no ocurrió'),
  bothNoNoteHost: () => T('Это никому не засчитывается. Затею можно открыть снова, если встреча всё ещё нужна.',
                          'Nothing is held against either of you. Your intent can open again if you still want it.',
                          'No cuenta contra ninguno. Tu propuesta puede abrirse de nuevo si aún la quieres.'),
  bothNoNote: () => T('Это никому не засчитывается.', 'Nothing is held against either of you.', 'No cuenta contra ninguno.'),
  /** OF.24a — лист причины. */
  reasonLead: (name: string) => T(`${name} не видит твой ответ`, `${name} doesn’t see your answer`, `${name} no ve tu respuesta`),
  reasonSpot: () => T('Место было закрыто', 'The spot was closed off', 'El sitio estaba cerrado'),
  reasonCaption: () => T('Нужно, чтобы планы оставались честными.', 'Used to keep plans honest.', 'Sirve para que los planes sean honestos.'),
  skip: () => T('Пропустить', 'Skip', 'Omitir'),
  /** OF.25 — лист «как прошло». */
  howWas: () => T('Как прошло?', 'How was it?', '¿Qué tal fue?'),
  howWasLead: () => T('Необязательно — это помогает Kleal подбирать точнее', 'Optional — it helps Kleal find better matches', 'Opcional — ayuda a Kleal a encontrar mejores coincidencias'),
  howWasNote: () => T('Ответ видит только Kleal. Если что-то пошло не так — лучше сообщи о проблеме.',
                      'Only Kleal sees your answer. If something went wrong, report it instead.',
                      'Solo Kleal ve tu respuesta. Si algo fue mal, mejor repórtalo.'),
  pastDay: (day: string, time: string) => `${day}, ${time}`,
};

export const OFB = {
  waitingTitle: (o: string) => T(`Ждём ответа ${o}`, `Waiting for ${o}`, `Esperando a ${o}`),
  waitingNote: (o: string) => T(`План начнётся, когда ${o} подтвердит, — или предложит другое время.`,
    `The plan starts when ${o} confirms — or suggests another time instead.`,
    `El plan empieza cuando ${o} confirme, o proponga otra hora.`),
  proposedTitle: (o: string) => T(`${o} предлагает план`, `${o} proposed a plan`, `${o} propuso un plan`),
  proposedNote: () => T('Подтверди или предложи другое время. План начнётся, когда подтвердите оба.',
    'Confirm it, or suggest another time. The plan starts when you both confirm.',
    'Confírmalo o propón otra hora. El plan empieza cuando confirméis los dos.'),
  confirmedTitle: () => T('Подтверждено', 'Confirmed', 'Confirmado'),
  hostSpotNote: (o: string, addr: string) => T(`У ${o} теперь есть точный адрес — ${addr}.`,
    `${o} has the exact spot now — ${addr}.`, `${o} ya tiene el sitio exacto: ${addr}.`),
  guestSpotNote: (o: string, t: string, addr: string) => T(`${o} подтвердил(а) ${t}. Точный адрес теперь открыт тебе — ${addr}.`,
    `${o} confirmed ${t}. The exact spot is open for you now — ${addr}.`,
    `${o} confirmó las ${t}. El sitio exacto ya está abierto para ti: ${addr}.`),
  updateSentTitle: () => T('Изменение отправлено', 'Update sent', 'Cambio enviado'),
  updateSentNote: (o: string, old: string) => T(`${o} подтвердит новое время или оставит ${old}. Пока нет ответа, в силе ${old} — ничего не отменено.`,
    `${o} confirms the new time or keeps ${old}. Until then, ${old} still stands — nothing is cancelled.`,
    `${o} confirma la nueva hora o mantiene las ${old}. Hasta entonces sigue en pie a las ${old}: no se cancela nada.`),
  suggestsNote: (old: string) => T(`${old} в силе, пока ты не ответишь, — ничего не потеряешь, если оставишь.`,
    `${old} still stands until you answer — nothing is lost if you keep it.`,
    `Las ${old} siguen en pie hasta que respondas: no pierdes nada si lo mantienes.`),
  stProposed: () => T('Предложил(а) это', 'Proposed this', 'Lo propuso'),
  stNotAnswered: () => T('Пока не ответил(а)', 'Hasn’t answered yet', 'Aún no ha respondido'),
  stYourAnswer: () => T('Нужен твой ответ', 'Your answer needed', 'Falta tu respuesta'),
  stChanged: () => T('Изменил(а)', 'Changed it', 'Lo cambió'),
  changePlan: () => T('Изменить план', 'Change the plan', 'Cambiar el plan'),
  changeTimeOrPlace: () => T('Изменить время или место', 'Change the time or place', 'Cambiar la hora o el lugar'),
  askToChange: () => T('Попросить изменить план', 'Ask to change the plan', 'Pedir cambiar el plan'),
  accept: (t: string) => T(`Принять ${t}`, `Accept ${t}`, `Aceptar ${t}`),
  /** Лист встречного времени — OF.C3a / OF.21a / OF.C5a. */
  changeTimeTitle: () => T('Изменить время', 'Change the time', 'Cambiar la hora'),
  insteadOfDay: (d: string) => T(`Вместо ${d},`, `Instead of ${d},`, `En lugar de ${d},`),
  date: () => T('День', 'Date', 'Fecha'),
  time: () => T('Время', 'Time', 'Hora'),
  orSetYour: () => T('или своё время', 'or set your time', 'o pon tu hora'),
  place: () => T('Место', 'Place', 'Lugar'),
  changePlace: () => T('Изменить место', 'Change place', 'Cambiar lugar'),
  placePh: () => T('Район или место', 'District or spot', 'Barrio o sitio'),
  sendTo: (o: string) => T(`Отправить ${o}`, `Send to ${o}`, `Enviar a ${o}`),
  sendUpdate: () => T('Отправить изменение', 'Send the update', 'Enviar el cambio'),
  /** Встречное время ДО подтверждения плана — раунды (OF.20b, OF.C3b). */
  youSuggested: (t: string) => T(`Ты предложил(а) ${t}`, `You suggested ${t}`, `Propusiste las ${t}`),
  /** Последний раунд: встречного больше нет — второй подтверждает, иначе хозяин закрепляет (OF.20c). */
  youSuggestedLastNote: (o: string, round: number, iHost: boolean) => T(
    `Раунд ${round} — последний. ${o} может подтвердить${iHost ? ', иначе ты закрепишь план' : ', иначе план закрепит организатор'}.`,
    `Round ${round} is the last one. ${o} can confirm${iHost ? ' — otherwise you fix the plan' : ' — otherwise the organiser fixes the plan'}.`,
    `La ronda ${round} es la última. ${o} puede confirmar${iHost ? '; si no, fijas tú el plan' : '; si no, el organizador fija el plan'}.`),
  youSuggestedNote: (o: string, round?: number) => T(
    `${round ? `Начался раунд ${round}. ` : ''}План закрепится, когда ${o} подтвердит, — или предложит другое время.`,
    `${round ? `Round ${round} started. ` : ''}The plan is set when ${o} confirms — or suggests another time.`,
    `${round ? `Empezó la ronda ${round}. ` : ''}El plan queda fijado cuando ${o} confirme, o proponga otra hora.`),
  suggestedChange: (o: string) => T(`${o} предлагает изменение`, `${o} suggested a change`, `${o} propuso un cambio`),
  suggestedChangeNote: (day: string, t: string, old: string, last?: boolean, online?: boolean, hybrid?: boolean) => T(
    `${day} в ${t} вместо ${old}, ${hybrid ? 'то же место и та же ссылка' : online ? 'та же ссылка' : 'то же место'}. ${last ? 'Это последний раунд — после него план закрепляешь ты.' : 'Подтверди — и план закреплён.'}`,
    `${day} at ${t} instead of ${old}, ${hybrid ? 'same place, same link' : online ? 'same link' : 'same place'}. ${last ? 'This is the last round — after it you fix the plan.' : 'Confirm and the plan is set.'}`,
    `${day} a las ${t} en lugar de las ${old}, ${hybrid ? 'mismo sitio y mismo enlace' : online ? 'mismo enlace' : 'mismo sitio'}. ${last ? 'Es la última ronda: después fijas tú el plan.' : 'Confirma y el plan queda fijado.'}`),
  stSuggested: () => T('Предложил(а) это', 'Suggested this', 'Lo propuso'),
  stConfirmedSuggested: () => T('Подтвердил(а) · предложил(а) это', 'Confirmed · Suggested this', 'Confirmó · Lo propuso'),
  stYourTurn: () => T('Твой ход', 'Your turn', 'Te toca'),
  editSuggestion: () => T('Изменить предложение', 'Edit the suggestion', 'Editar la propuesta'),
  /** OF.20c — хозяин после трёх раундов закрепляет финальную версию. */
  fixPlan: () => T('Закрепить план', 'Fix the plan', 'Fijar el plan'),
  pickFinal: () => T('Выбери финальную версию', 'Pick the final version', 'Elige la versión final'),
  roundLabel: (n: number) => T(`Раунд ${n}`, `Round ${n}`, `Ronda ${n}`),
  yourPlan: () => T('Твой план', 'Your plan', 'Tu plan'),
  theirSuggestion: (o: string) => T(`Предложение ${o}`, `${o}’s suggestion`, `Propuesta de ${o}`),
  fixNote: (o: string) => T(`После этого план больше не меняется. ${o} решит, остаться или выйти.`,
    `The plan stops changing after this. ${o} will be asked to stay or leave.`,
    `El plan deja de cambiar después de esto. ${o} decidirá si se queda o sale.`),
  fixThis: () => T('Закрепить этот план', 'Fix this plan', 'Fijar este plan'),
  back: () => T('Назад', 'Back', 'Atrás'),
  /** OF.C3d — гость после фиксации. */
  fixedTitle: (o: string) => T(`${o} закрепил(а) план`, `${o} fixed the plan`, `${o} fijó el plan`),
  fixedNote: () => T('Это финальная версия после трёх раундов. Останься или выйди из плана — никаких последствий.',
    'This is the final version after three rounds. Stay in, or leave the plan — nothing is held against you.',
    'Es la versión final tras tres rondas. Quédate o sal del plan: no hay consecuencias.'),
  stFixed: () => T('Закрепил(а) финальную версию', 'Fixed the final version', 'Fijó la versión final'),
  stayIn: () => T('Остаюсь', 'Stay in', 'Me quedo'),
  leavePlan: () => T('Выйти из плана', 'Leave the plan', 'Salir del plan'),
  /** Хозяин после фиксации ждёт ответа гостя. */
  fixedWaitTitle: (o: string) => T(`Ждём ответа ${o}`, `Waiting for ${o}`, `Esperando a ${o}`),
  fixedWaitNote: (o: string) => T(`План закреплён. ${o} решит, остаться или выйти.`, `The plan is fixed. ${o} decides to stay in or leave.`, `El plan está fijado. ${o} decide si se queda o sale.`),
  /** OF.19c — гость вышел; затея снова открыта. */
  leftTitle: (o: string) => T(`${o} вышел(ла) из плана`, `${o} left the plan`, `${o} salió del plan`),
  leftNote: () => T('План отменён — никаких последствий ни для кого. Твоя затея снова открыта: можно выбрать другого человека.',
    'The plan is cancelled — nothing is held against anyone. Your intent is open again, so you can pick someone else.',
    'El plan está cancelado, sin consecuencias para nadie. Tu propuesta vuelve a estar abierta: puedes elegir a otra persona.'),
  stLeft: () => T('Вышел(ла) из плана', 'Left the plan', 'Salió del plan'),
  stIntentOpen: () => T('Затея снова открыта', 'Intent open again', 'Propuesta abierta de nuevo'),
  pickElse: () => T('Выбрать другого', 'Pick someone else', 'Elegir a otra persona'),
  /** OF.21d — хозяин отменяет план; OF.C5b — гость выходит. */
  cancelPlan: () => T('Отменить план', 'Cancel the plan', 'Cancelar el plan'),
  cancelAsk: () => T('Отменить встречу?', 'Cancel the meetup?', '¿Cancelar la quedada?'),
  cancelNote: (o: string) => T(`${o} узнает, что план отменён. Никаких последствий ни для кого, а твоя затея снова откроется.`,
    `${o} is told the plan is cancelled. Nothing is held against either of you, and your intent opens again.`,
    `${o} sabrá que el plan se canceló. Sin consecuencias para nadie, y tu propuesta vuelve a abrirse.`),
  keepIt: () => T('Оставить', 'Keep it', 'Mantenerlo'),
  leaveAsk: () => T('Выйти из встречи?', 'Leave the meetup?', '¿Salir de la quedada?'),
  cantUndo: () => T('Это нельзя отменить', 'You can’t undo this', 'No se puede deshacer'),
  leaveNote: (o: string) => T(`${o} узнает, что ты вышел(ла), и план отменится. Никаких последствий.`,
    `${o} is told you left, and the plan is cancelled. Nothing is held against you.`,
    `${o} sabrá que saliste y el plan se cancela. Sin consecuencias.`),
  stay: () => T('Остаться', 'Stay', 'Quedarme'),
  /** OF.C6 — организатор отменил план, вид гостя. */
  hostCancelledTitle: () => T('План отменён', 'The plan is cancelled', 'El plan está cancelado'),
  hostCancelledNote: (o: string) => T(`${o} отменил(а) встречу. Никаких последствий — ты можешь создать свою затею в любой момент.`,
    `${o} cancelled the meetup. Nothing is held against anyone — you can create your own intent any time.`,
    `${o} canceló la quedada. Sin consecuencias: puedes crear tu propia propuesta cuando quieras.`),
  youCancelledTitle: () => T('Ты отменил(а) план', 'You cancelled the plan', 'Cancelaste el plan'),
  youCancelledNote: () => T('Никаких последствий ни для кого. Твоя затея снова открыта: можно выбрать другого человека.',
    'Nothing is held against anyone. Your intent is open again, so you can pick someone else.',
    'Sin consecuencias para nadie. Tu propuesta vuelve a estar abierta: puedes elegir a otra persona.'),
  /** Молчание до подтверждения: план закрыт (cancel_kind expired_no_answer). */
  silentTitle: (o: string) => T(`${o} не ответил(а)`, `${o} didn’t answer`, `${o} no respondió`),
  silentHostNote: () => T('План закрыт — никаких последствий. Твоя затея снова открыта: можно выбрать другого человека.',
    'The plan is closed — nothing is held against anyone. Your intent is open again, so you can pick someone else.',
    'El plan se cerró, sin consecuencias. Tu propuesta vuelve a estar abierta: puedes elegir a otra persona.'),
  silentGuestNote: () => T('План закрыт — никаких последствий. Ты можешь создать свою затею в любой момент.',
    'The plan is closed — nothing is held against you. You can create your own intent any time.',
    'El plan se cerró, sin consecuencias. Puedes crear tu propia propuesta cuando quieras.'),
  youSilentTitle: () => T('План закрыт', 'The plan is closed', 'El plan está cerrado'),
  youSilentNote: () => T('Ты не ответил(а) за 6 часов. Никаких последствий — можно создать свою затею в любой момент.',
    'You didn’t answer within 6 hours. Nothing is held against you — you can create your own intent any time.',
    'No respondiste en 6 horas. Sin consecuencias: puedes crear tu propia propuesta cuando quieras.'),
  stNoAnswer: () => T('Не ответил(а)', 'Didn’t answer', 'No respondió'),
  stCancelled: () => T('Отменил(а) план', 'Cancelled the plan', 'Canceló el plan'),
  stWasGoing: () => T('Собирался(ась) пойти', 'Was going', 'Iba a ir'),
  createIntent: () => T('Создать свою затею', 'Create your intent', 'Crear tu propuesta'),
  youLeftTitle: () => T('Ты вышел(ла) из плана', 'You left the plan', 'Saliste del plan'),
  youLeftNote: (o: string) => T(`Никаких последствий. ${o} может выбрать другого человека, а ты — создать свою затею.`,
    `Nothing is held against you. ${o} can pick someone else, and you can start your own intent any time.`,
    `Sin consecuencias. ${o} puede elegir a otra persona y tú puedes crear tu propia propuesta cuando quieras.`),
  /** OF.19e — кого выбрать вместо вышедшего. */
  pickNote: (names: string[]) => names.length
    ? T(`${names.join(', ')} уже сказал(и) «да» на эту затею. Выбери — и сразу откроется чат.`,
        `${names.join(', ')} said yes to this intent earlier. Pick and the chat opens right away.`,
        `${names.join(', ')} ya dijo que sí a esta propuesta. Elige y el chat se abre enseguida.`)
    : T('Пока никто больше не сказал «да» на эту затею. Посмотри, кого Kleal нашёл.',
        'Nobody else has said yes to this intent yet. See who Kleal found.',
        'Nadie más ha dicho que sí todavía. Mira a quién encontró Kleal.'),
  saidYes: () => T('Сказал(а) «да»', 'Said yes', 'Dijo que sí'),
  stillFree: (o: string) => T(`${o} свободен(на). Выбери — и откроется чат.`, `${o} is still free. Pick them and the chat opens.`, `${o} sigue libre. Elígela y se abre el chat.`),
  busyNow: (o: string) => T(`У ${o} уже есть план с тобой.`, `${o} already has a plan with you.`, `${o} ya tiene un plan contigo.`),
  pickName: (o: string) => T(`Выбрать ${o}`, `Pick ${o}`, `Elegir a ${o}`),
  seeOthers: () => T('Посмотреть, кого нашёл Kleal', 'See who Kleal found', 'Ver a quién encontró Kleal'),
};

/**
 * Кадры O.21–O.25 — жизнь плана после отправки.
 *
 *  O.21  Подтверждён: время, отметка, что ссылка откроется за десять минут, «Открыть чат» и
 *        «Предложить другое время».
 *  O.22  За десять минут до звонка ссылка открывается.
 *  O.23  Время пришло.
 *  O.24  После: «состоялось ли». Спрашивают обоих, и до ответа обоих никому ничего не засчитывают.
 *  O.25  Отзыв — необязательный.
 *
 * Про десять минут. Сервер отдаёт ссылку тому, кто ПОДТВЕРДИЛ встречу (OF.C3), и времени в этом
 * правиле нет. «Открывается за десять минут» — правило показа, и живёт оно в клиенте: ссылка уже
 * пришла, экран просто не делает её кнопкой раньше срока. Это не защита, а фокус — в отличие от
 * адреса, который сервер действительно скрывает.
 */
export const PLAN = {
  confirmed: () => T('Подтверждено', 'Confirmed', 'Confirmado'),

  /** O.20 — шапка формы. Режим приходит из интента, и форма его НАЗЫВАЕТ, а не намекает полями. */
  formMode: (mode: 'offline' | 'online' | 'hybrid', name: string) =>
    mode === 'online'
      ? T(`Звонок с ${ins(name)} — по интенту вы договорились встретиться онлайн`,
          `A call with ${name} — your intent was to meet online`, `Una llamada con ${name} — tu propuesta era quedar online`)
      : mode === 'hybrid'
        ? T(`Встреча с ${ins(name)} — по интенту можно и онлайн, и вживую`,
            `Meeting ${name} — your intent allows both online and in person`, `Quedar con ${name} — tu propuesta permite online y en persona`)
        : T(`Встреча с ${ins(name)} вживую — по интенту вы договорились увидеться`,
            `Meeting ${name} in person — your intent was to meet up`, `Quedar con ${name} en persona — tu propuesta era veros`),
  /** Ссылку можно донести потом, но второй до этого видит «ссылка будет» — об этом честно сразу. */
  linkLaterNote: (name: string) =>
    T(`Можно оставить пустым и прислать позже — до этого ${name} видит «ссылка будет».`,
      `You can leave this empty and add it later — until then ${name} sees “link coming”.`, `Puedes dejarlo vacío y añadirlo después — hasta entonces ${name} ve "enlace pendiente".`),
  /** Что случится по «Создать план». Кнопка отправляет предложение, а не бронирует вечер. */
  formSendNote: (name: string) =>
    T(`${name} получит это предложением и подтвердит со своей стороны. Пока не подтвердит — ничего не назначено.`,
      `${name} gets this as a proposal and confirms on their side. Nothing is booked until they do.`, `${name} recibe esto como una propuesta y confirma por su parte. Nada se reserva hasta que lo haga.`),
  /**
   * На кадре здесь названы обе стороны и оба часовых пояса. Пояс собеседника мы не храним — ни в
   * профиле, ни в плане, — поэтому время показывается ОДНО, своё, и подписано своим поясом.
   * Выдумывать «19:00 в Лондоне» для человека, чей пояс никто не спрашивал, нельзя.
   */
  linkOpensAt: (hhmmStr: string) =>
    T(`Ссылка откроется в ${hhmmStr}, не раньше.`, `The link opens at ${hhmmStr}, not now.`, `El enlace se abre a las ${hhmmStr}, no ahora.`),
  linkSaved: () => T('Видеозвонок · ссылка сохранена', 'Video call · link saved', 'Video llamada · enlace guardado'),
  linkOpensLabel: (hhmmStr: string) =>
    T(`Видеозвонок · ссылка откроется в ${hhmmStr}`, `Video call · link opens ${hhmmStr}`, `Video llamada · enlace se abre ${hhmmStr}`),
  /** Формат без обещаний про ссылку — для встречи, которая уже позади или отменена. */
  modeOnline: () => T('Видеозвонок', 'Video call', 'Video llamada'),
  /**
   * Формат ГИБРИДА одной строкой. Раньше в этой строке у него стояло «Видеозвонок» — половина
   * правды, ровно та, из-за которой человек и решает не идти живьём.
   */
  modeHybrid: () => T('Вживую и на связи', 'In person and on the call', 'Presencial y en llamada'),

  /** Всё согласовано и место известно — конец переговоров, сказанный вслух. */
  allSetTitle: () => T('Всё готово', 'You’re all set', '¡Todo listo!'),
  /**
  * «Всё готово». У ГИБРИДА это отдельная фраза, а не одна из двух старых.
  *
  * Раньше признак был булев (offline или нет), гибрид попадал в онлайновую ветку, и она про место
  * не говорит ни слова. А строка места к этому моменту уже скрыта — её прячут ровно потому, что
  * «зелёная плашка назовёт место». В итоге у гибрида адрес пропадал с экрана совсем: и из строки,
  * и из плашки. Проверено на симуляторе.
  */
  allSetNote: (when: string, mode: 'offline' | 'online' | 'hybrid', name: string, place: string) =>
    mode === 'hybrid'
      ? T(
          `${when}${place ? `, ${place}` : ''}. Ссылка тоже открыта — можно и прийти, и подключиться.`,
          `${when}${place ? `, ${place}` : ''}. The link is live too — you can come or join the call.`
        , `${when}${place ? `, ${place}` : ''}. El enlace también está activo — puedes venir o unirte a la llamada.`)
      : mode === 'offline'
      ? T(
          `${when}${place ? `, ${place}` : ''}. Адрес есть у вас обоих — договариваться больше не о чем.`,
          `${when}${place ? `, ${place}` : ''}. You both have the address — nothing left to agree.`
        , `${when}${place ? `, ${place}` : ''}. Los dos tenéis la dirección — no queda nada por acordar.`)
      : T(
          `${when}. Ссылка сохранена и откроется за 10 минут до начала — ${name} тоже её увидит.`,
          `${when}. The link is saved and opens 10 minutes before — ${name} sees it too.`
        , `${when}. El enlace está guardado y se abre 10 minutos antes — ${name} también lo ve.`),

  /**
   * ХВОСТ «ВСЁ ГОТОВО» — БЕЗ ВРЕМЕНИ И МЕСТА.
   *
   * `allSetNote` выше склеивает всё в одну фразу, и на экране она набиралась тринадцатым кеглем —
   * самым мелким в приложении, тем же, что и заголовок плашки. Время и адрес, то есть ровно то,
   * ради чего плашку и открывают, лежали в середине предложения между успокоительными словами и
   * ничем от них не отличались. Сообщено с телефона: «информация оттуда не читается».
   *
   * Теперь факты рисуются отдельными строками с иконками — теми же, что и выше по экрану, — а
   * здесь остаётся только то, чего строкой не покажешь: что делать дальше и почему больше ничего
   * не нужно. `allSetNote` оставлен: он всё ещё верен и пригодится там, где строк нет (уведомление,
   * короткая карточка).
   */
  allSetTail: (mode: 'offline' | 'online' | 'hybrid', name: string) =>
    mode === 'hybrid'
      ? T('Ссылка тоже открыта — можно и прийти, и подключиться.',
          'The link is live too — you can come or join the call.', 'El enlace también está activo — puedes unirte o entrar en la llamada.')
      : mode === 'offline'
      ? T('Адрес есть у вас обоих — договариваться больше не о чем.',
          'You both have the address — nothing left to agree.', 'Los dos tenéis la dirección — no queda nada por acordar.')
      : T(`Ссылка откроется за 10 минут до начала — ${name} тоже её увидит.`,
          `The link opens 10 minutes before — ${name} sees it too.`, `El enlace se abre 10 minutos antes — ${name} lo ve también.`),

  startsIn: (min: number) => T(`Начало через ${min} мин`, `Starts in ${min} minutes`, `Empieza en ${min} ${min === 1 ? 'minuto' : 'minutos'}`),
  startsNow: () => T('Время звонка', 'Your call is now', 'Tu llamada es ahora'),
  linkOpenNow: () => T('Ссылка открыта', 'Your link is now open', 'Tu enlace está ahora abierto'),
  linkNote: () =>
    T(
      'Звонок проходит по этой ссылке — Kleal хранит только её и время.',
      'The call happens on this link — Kleal only keeps the link and the time.'
    , 'La llamada se hace en este enlace — Kleal solo guarda el enlace y la hora.'),
  openLink: () => T('Открыть ссылку', 'Open link', 'Abrir enlace'),
  leavesKleal: () => T('Откроется вне Kleal', 'Opens outside Kleal', 'Se abre fuera de Kleal'),
  /**
  * То же самое, но у ГИБРИДА, пока никуда не ушли.
  *
  * Строки про «звонок вне Kleal» писались для звонка, и до сих пор гибрид до них не доходил — у
  * него этот блок просто не рисовался. Теперь доходит, и «звонок идёт вне Kleal» на экране, где
  * человек сидит за столиком, — половина правды: встреча может идти обоими входами сразу.
  */
  outsideNoteHybrid: () =>
    T(
      'Встреча идёт вне Kleal — и за столиком, и по ссылке. Мы её не видим и ничего не записываем. Потом спросим у обоих, состоялась ли она.',
      'The meetup happens outside Kleal — at the table and on the link. We can’t see it and record nothing. Afterwards we ask you both whether it happened.'
    , 'La quedada tiene lugar fuera de Kleal — en la mesa y en el enlace. No podemos verla ni grabar nada. Después te preguntamos a ambos si tuvo lugar.'),
  hybridNote: () =>
    T(
      'Оба входа открыты: можно прийти на место, а можно подключиться по ссылке. Kleal хранит только их и время.',
      'Both ways in are open: come to the place or join on the link. Kleal only keeps those and the time.'
    , 'Ambas opciones están abiertas: venir al lugar o unirte con el enlace. Kleal solo guarda estos y la hora.'),
  outsideNote: () =>
    T(
      'Звонок идёт вне Kleal. Мы его не видим и ничего о нём не записываем. Потом спросим у обоих, состоялся ли он.',
      'The call happens outside Kleal. We can’t see it and nothing about it is recorded here. Afterwards we’ll ask you both whether it happened.'
    , 'La llamada ocurre fuera de Kleal. No podemos verla ni se graba nada sobre ella aquí. Después te preguntaremos a ambos si tuvo lugar.'),
  messageThem: (name: string) => T(`Написать ${dat(name)}`, `Message ${name}`, `Mensaje a ${name}`),
  cantMakeIt: () => T('Не смогу', 'I can’t make it', 'No puedo ir'),
  suggestAnother: () => T('Предложить другое время', 'Suggest another time', 'Sugerir otra hora'),
  /**
   * Замок за два часа до встречи. Кнопки «предложить другое время», «подтвердить/оставить» и
   * правка ссылки в этот момент перестают приниматься сервером — и раньше они всё равно
   * рисовались, а нажатие давало безымянную ошибку. Теперь вместо них стоит объяснение.
   */
  lockedNote: () => T(
    'До встречи меньше двух часов — время и ссылка больше не меняются. Если не сможешь прийти, скажи об этом: собеседник увидит.',
    'Under two hours to go — the time and the link don’t change any more. If you can’t make it, say so and they’ll see it.'
  , 'Menos de dos horas para que empiece — la hora y el enlace ya no cambian. Si no puedes venir, avísalo y ellos lo verán.'),

  /**
   * Отмена встречи заранее. Её не было вовсе: отказаться можно было только за десять минут до
   * начала, а до того ни автор плана, ни приглашённый не имели способа сказать «не смогу».
   */
  callOff: () => T('Отменить встречу', 'Call the meetup off', 'Cancelar la quedada'),
  callOffAsk: (name: string) => T(`Отменить встречу с ${ins(name)}?`, `Call off the meetup with ${name}?`, `¿Anular la quedada con ${name}?`),
  callOffNote: (name: string) =>
    T(
      `${name} сразу увидит отмену. Вернуть эту встречу нельзя — можно назначить новую, чат остаётся открытым.`,
      `${name} sees it straight away. This meetup can’t be restored — you can set a new one, and your chat stays open.`
    , `${name} lo ve de inmediato. Esta quedada no se puede recuperar — puedes proponer una nueva y tu conversación sigue abierta.`),
  /**
   * HY.23b — та же отмена, но у ГИБРИДА. Тут рядом стоит кнопка «уйду в звонок», и человек может
   * решить, что «не смогу» — это про неё, то есть про смену стороны. Кадр говорит прямым текстом,
   * что это не так: смена стороны встречу не трогает, а отмена заканчивает её для обоих.
   */
  callOffNoteHybrid: (name: string) =>
    T(
      `Это не смена стороны: встреча закончится для вас обоих. ${name} сразу увидит отмену. Вернуть её нельзя — можно назначить новую, чат остаётся открытым.`,
      `This is not switching sides — it ends the meetup for both of you. ${name} sees it straight away. This one cannot be brought back, but your chat stays open, so a new time is still possible.`
    , `Esto no es cambiar de bando — acaba la quedada para ambos. ${name} lo ve de inmediato. Esto no se puede deshacer, pero tu chat permanece abierto, así que aún es posible una nueva hora.`),
  callOffYes: () => T('Да, отменить', 'Yes, call it off', 'Sí, cancela la quedada'),
  callOffNo: () => T('Оставить как есть', 'Leave it as it is', 'Déjalo como está'),

  /** O.24. Формулировка с кадра: спрашивают обоих, и до ответа обоих никому ничего не засчитывают. */
  didItHappen: () => T('Встреча состоялась?', 'Did it happen?', '¿Sucedió?'),
  didItNote: (name: string) =>
    T(
      `Kleal не видит, что происходит вне приложения, поэтому спрашивает. ${name} получит тот же вопрос. Пока не ответите оба, никому ничего не засчитывается.`,
      `Kleal can’t see outside the app, so we have to ask. ${name} gets the same question. Nothing is recorded against anyone until you both answer.`
    , `Kleal no puede ver fuera de la app, así que tenemos que preguntar. ${name} recibe la misma pregunta. Nada se registra contra nadie hasta que los dos respondáis.`),
  /**
   * O.23c. Формулировка осторожная намеренно: приложение видит не звонок, а нажатие на ссылку.
   * «Никто не подключился» было бы утверждением о том, чего мы не знаем, — созвониться могли и
   * своим способом. Поэтому говорим ровно то, что видели.
   */
  nobodyJoined: () =>
    T(
      'Ссылку так никто и не открыл — похоже, звонок не состоялся.',
      'Nobody opened the link — it looks like the call didn’t happen.'
    , 'Nadie abrió el enlace — parece que la llamada no tuvo lugar.'),
  yesWeTalked: () => T('Да, встретились', 'Yes, we talked', 'Sí, ya hablamos'),
  noItDidnt: () => T('Нет, не состоялась', 'No, it didn’t happen', 'No, no pasó'),
  /** O.21b: чужой местный час у предложенного времени — «У Jane это 23:00». */
  theirTimeNote: (name: string, t: string) => T(`У ${name} это ${t}`, `That’s ${t} for ${name}`, `Eso es ${t} para ${name}`),
  waitingBoth: () => T('Ждём ответа обоих', 'Waiting on both answers', 'Esperando a ambas respuestas'),
  /**
   * O.24b — оба ответили «не состоялась».
   *
   * До этого экран говорил ровно «Спасибо» — то же самое, что и после «встретились». А это
   * ЕДИНСТВЕННЫЙ случай, когда сходятся оба ответа и встреча закрыта как несостоявшаяся; человек
   * должен видеть, чем всё кончилось, и куда идти дальше, а не гадать, дошёл ли его ответ.
   */
  didntHappenTitle: () => T('Встреча не состоялась', 'The meetup didn’t happen', 'La quedada no tuvo lugar'),
  didntHappenNote: (name: string) =>
    T(
      `Вы оба так ответили, поэтому встреча закрыта. Никаких пометок ни тебе, ни ${name} это не даёт — бывает.`,
      `You both said so, so it’s closed. Nothing is held against you or ${name} — it happens.`
    , `Los dos lo confirmasteis, así que está cerrado. Nada contra ti ni contra ${name} — ocurre.`),
  findElse: () => T('Найти кого-то ещё', 'Find someone else', 'Buscar a otra persona'),
  /**
   * «Ждём Jane» — когда я уже ответил.
   *
   * Кадр O.24 говорит «ждём обоих», а O.24a/O.25 (я ответил) — «ждём Jane»; в коде на оба случая
   * стояла одна строка. Разница не косметическая: человек, который только что ответил, читал
   * «ждём ответа обоих» и решал, что его ответ не записался.
   */
  waitingThem: (who: string) => T(`Ждём ответа: ${who}`, `Waiting on ${who}`, `Esperando a ${who}`),

  /** O.25. */
  howWasIt: () => T('Как прошло?', 'How was it?', '¿Cómo fue?'),
  optional: () =>
    T(
      'Необязательно — это помогает агенту подбирать лучше в следующий раз.',
      'Optional — it helps your agent find better matches next time.'
    , 'Opcional — ayuda a tu agente a encontrar mejores coincidencias la próxima vez.'),
  great: () => T('Отлично', 'Great', 'Genial'),
  fine: () => T('Нормально', 'Fine', 'Bien'),
  notGreat: () => T('Так себе', 'Not great', 'No muy bien'),
  send: () => T('Отправить', 'Send', 'Enviar'),
  reportProblem: () => T('Сообщить о проблеме', 'Report a problem', 'Reportar un problema'),
  thanks: () => T('Спасибо — это поможет подбирать точнее.', 'Thank you — this helps us match you better.', 'Gracias — esto nos ayuda a emparejarte mejor.'),

  /* ──────────────────────────────────────────────────────────────────────────────────────────
     ВСТРЕЧА ПОЗАДИ — ЭТО ЗАПИСЬ, А НЕ ОПРОС.
     Раньше у прошедшего плана не было своего вида вовсе: он открывался последним кадром опроса —
     «Спасибо — это поможет подбирать точнее», — а под ним стояли живые строки «Подтвердил(а)»,
     будто встреча ещё впереди. Человек приходил в историю посмотреть, что было, и не находил
     ничего: ни где встречались, ни что он сам ответил.
     Здесь ровно три вещи: что было, где было и что записано С ЕГО слов. Оценка второго человека
     сюда не попадает и попадать не должна — её не показывают тому, кого оценивали.
  ─────────────────────────────────────────────────────────────────────────────────────────── */
  pastHappened: () => T('Встреча состоялась', 'The meetup happened', 'La quedada tuvo lugar'),
  /** Ответы разошлись или никто не ответил: утверждать нечего, но встреча позади. */
  pastOver: () => T('Встреча прошла', 'This meetup is over', 'Esta quedada ya pasó'),

  pastWhereTitle: () => T('Где были', 'Where it was', 'Dónde fue'),
  pastAtPlace: (place: string) => T(`Встретились: ${place}`, `You met at ${place}`, `Quedasteis en ${place}`),
  pastOnCall: () => T('Прошло звонком', 'It was a video call', 'Fue una videollamada'),
  pastBothWays: () => T('Было и место, и звонок', 'There was a place and a call', 'Hubo lugar y llamada'),
  pastPlaceNever: () => T('Место так и не назвали', 'The place was never named', 'El lugar nunca se concretó'),

  pastRecordTitle: () => T('Что записано', 'What is on record', 'Lo que quedó registrado'),
  pastYouSaidYes: () => T('Ты ответил(а), что встретились', 'You said it happened', 'Dijiste que tuvo lugar'),
  pastYouSaidNo: () => T('Ты ответил(а), что встреча не состоялась', 'You said it didn’t happen', 'Dijiste que no tuvo lugar'),
  pastNoAnswer: () => T('Ты не сказал(а), состоялась ли она', 'You never said whether it happened', 'No dijiste si tuvo lugar'),
  pastRated: (label: string) => T(`Твоя оценка: ${label}`, `You rated it: ${label}`, `Tu valoración: ${label}`),
  pastNotRated: () => T('Оценку ты не оставил(а)', 'You left no rating', 'No dejaste valoración'),
  pastReason: (label: string) => T(`Причина: ${label}`, `Reason: ${label}`, `Motivo: ${label}`),
  pastHowMet: (label: string) => T(`Как встретились: ${label}`, `How you met: ${label}`, `Cómo quedasteis: ${label}`),
  /**
   * Прямо сказать, что чужих глаз здесь нет: иначе отвечают не то, что было, а то, что удобно.
   * Речь про ВЕСЬ ответ, а не только про оценку: причину «не состоялась» второй тоже не видит.
   */
  pastOnlyYou: (name: string) =>
    T(`Это видишь только ты — ${name} твой ответ не видит.`,
      `Only you see this — ${name} cannot see your answer.`,
      `Esto solo lo ves tú — ${name} no ve tu respuesta.`),
  /** Второй так и не сказал, состоялась ли встреча. Строкой, а не обрубком статуса. */
  pastTheyNever: (name: string) =>
    T(`${name} так и не ответил(а)`, `${name} never answered`, `${name} no llegó a responder`),

  /** Строки участников у прошедшей встречи — вместо «Подтвердил(а)», которое там ничего не значит. */
  pastAnswered: () => T('Ответил(а)', 'Answered', 'Respondió'),
  pastNotAnswered: () => T('Не ответил(а)', 'No answer', 'Sin respuesta'),

  /** O.20a — согласованный онлайн-план без ссылки. Времена на кадре — примеры борда; пояс
   *  собеседника мы не храним (см. linkOpensAt), поэтому время здесь одно, своё. */
  addLinkTitle: () => T('Добавь ссылку на звонок', 'Add the call link', 'Añade el enlace de la llamada'),
  /**
   * HY.20c — у гибрида не задано НИ ОДНОГО входа.
   *
   * Это отдельный кадр, а не «сперва одно, потом другое»: когда согласовано только время, человеку
   * надо сказать, что нужны обе вещи сразу, — иначе он донесёт ссылку, решит, что закончил, и
   * половина, собиравшаяся прийти живьём, останется без места.
   */
  addBothTitle: () => T('Добавь место и ссылку', 'Add a place and a link', 'Añade un lugar y un enlace'),
  /**
   * HY.22 / HY.22a / HY.22b / HY.C4 — СТОРОНА ВСТРЕЧИ.
   *
   * У гибрида два входа, и каждый идёт своим. Главное, что здесь надо сказать словами: это не
   * отмена. Человек, нажимающий «уйду в звонок», должен видеть, что встреча продолжается, а второй
   * — что его не бросили за столиком. На кадре 22b это сказано прямо: «она сказала заранее, и ты
   * не ждёшь того, кто не придёт».
   */
  joinCallInstead: () => T('Уйду в звонок', 'Join the call instead', 'Únete a la llamada en su lugar'),
  /**
   * HY.23c — «место закрыто».
   *
   * Выход, которого у встречи вживую нет: ссылка уже открыта. Кнопка переводит ОБОИХ, потому что
   * по одному это не работает — пока второй не догадается сделать то же, он стоит у той же двери.
   */
  placeClosedTitle: () => T('Место закрыто', 'The place is closed', 'El lugar está cerrado'),
  placeClosedNote: () =>
    T(
      'Дверь заперта, и вы оба снаружи. У гибрида есть выход, которого нет у встречи вживую: перевести всех в звонок — ссылка уже открыта.',
      'The door is shut and you are both outside. Hybrid gives you a way out that offline does not — move everyone to the call, the link is already open.'
    , 'La puerta está cerrada y ambos estáis fuera. Hybrid os da una salida que offline no tiene — pasad a todos a la llamada, el enlace ya está abierto.'),
  moveToCall: () => T('Уходим в звонок', 'Move to the call', 'Pasa a la llamada'),
  movedToCallTitle: () => T('Вы оба в звонке', 'You both moved to the call', 'Los dos os habéis movido a la llamada'),
  movedToCallNote: () =>
    T(
      'Место не сработало, встреча осталась. Ссылка открыта у обоих.',
      'The place didn’t work out, the meetup did. The link is open for both of you.'
    , 'El lugar no funcionó, pero la quedada sí. El enlace está abierto para ambos.'),
  /**
   * HY.25 — КАК встретились. Не оценка встречи: у гибрида два входа, и какой из них сработал —
   * подсказка агенту, что предлагать в следующий раз. «И так и так» стоит намеренно: это обычный
   * исход, когда один пришёл, второй подключился, а потом поменялись местами.
   */
  howMetTitle: () => T('Как встретились?', 'How did you meet?', '¿Cómo os conocisteis?'),
  howMetNote: () =>
    T(
      'Гибрид засчитывается в любом случае — это только чтобы агент понимал, какой формат тебе подходит.',
      'Hybrid counts either way — this only helps your agent suggest the right format next time.'
    , 'El formato híbrido cuenta de ambas formas — esto solo ayuda a tu agente a sugerir el formato adecuado la próxima vez.'),
  howInPerson: () => T('Вживую', 'In person', 'Presencial'),
  howCall: () => T('На звонке', 'On the call', 'En la llamada'),
  howBoth: () => T('И так и так', 'A bit of both', 'Un poco de ambos'),
  goInPersonAfterAll: () => T('Всё-таки приду живьём', 'Go in person after all', 'Al final, en persona'),
  sideSwitchedTitle: () => T('Ты уходишь в звонок', 'You switched to the call', 'Has pasado al modo llamada'),
  /**
   * Оба в звонке. Отдельная строка, потому что «ты уходишь в звонок» рядом с «Sofia по-прежнему
   * идёт на место» после HY.23c — прямая неправда: на место больше не идёт никто. Поймано на
   * симуляторе: заголовок остался от одиночной смены стороны.
   */
  sideBothCallTitle: () => T('Вы оба в звонке', 'You are both on the call', 'Los dos estáis en la llamada'),
  sideBothCallNote: (name: string) =>
    T(
      `Ни тебе, ни ${name} никуда идти не нужно — встреча пройдёт по ссылке.`,
      `Neither you nor ${name} has anywhere to go — the meetup happens on the link.`
    , `Ni tú ni ${name} tenéis a dónde ir — la quedada ocurre en el enlace.`),
  sideSwitchedNote: (name: string) =>
    T(
      `${name} это видит и по-прежнему идёт на место. Ссылка открыта для тебя — ничего не отменено, ты просто входишь другим входом.`,
      `${name} sees it and is still going to the place. The link is open for you — nothing is cancelled, you’re just joining the other way.`
    , `${name} lo ve y sigue yendo al lugar. El enlace sigue abierto para ti — nada se cancela, simplemente te estás uniendo de otra manera.`),
  theySwitchedTitle: (name: string) => T(`${name} уходит в звонок`, `${name} joined the call instead`, `${name} se ha unido a la llamada en lugar de ir en persona`),
  theySwitchedNote: (name: string) =>
    T(
      `${name} сказал(а) заранее — значит ты не ждёшь за столиком того, кто не придёт. Встреча в силе, просто вы с разных её сторон.`,
      `${name} told you before the time, so you are not waiting at the table for someone who isn’t coming. The meetup is on — they are simply on the other side of it.`
    , `${name} te lo dijo antes de la hora, así que no estás esperando en la mesa por alguien que no llegará. La quedada sigue adelante — simplemente están del otro lado.`),
  /** Строка участника: с какой стороны он придёт. */
  sideInPerson: () => T('Придёт живьём', 'Coming in person', 'Venir en persona'),
  sideInPersonMine: () => T('Придёшь живьём', 'Coming in person', 'Venir en persona'),
  sideCall: () => T('Будет на звонке', 'Joining the call', 'Entrando en la llamada'),
  sideCallMine: () => T('Будешь на звонке', 'Joining the call', 'Entrando en la llamada'),
  /** Отказ сервера: стороны, которую выбирают, ещё не существует. */
  sideNoLink: () => T('Ссылки ещё нет — сперва добавь её', 'No link yet — add one first', 'Todavía no hay enlace — añade uno primero'),
  sideNoPlace: () => T('Места ещё нет — сперва выбери его', 'No place yet — pick one first', 'Todavía no hay lugar — elige uno primero'),
  addBothNote: () =>
    T(
      'Согласовано только время. Гибриду нужны оба входа: без места некуда прийти, без ссылки не подключиться. Начни с места.',
      'Only the time is agreed. Hybrid needs both a place and a link — without them nobody knows how to reach you. Start with the place.'
    , 'Solo se ha acordado la hora. Para lo híbrido se necesita un lugar y un enlace — sin ellos nadie sabe cómo contactar contigo. Empieza por el lugar.'),
  addLinkNote: (when: string, name: string) =>
    T(
      `Встреча (${when}) согласована. ${name} видит «ссылка будет», пока ты её не вставишь — добавь заранее, чтобы к началу никто не ждал.`,
      `${when} is agreed. ${name} sees “link coming” until you paste one — add it ahead of time so nobody is waiting on it.`
    , `${when} acordado. ${name} ve «enlace pendiente» hasta que lo pegues — añádelo con antelación para que nadie tenga que esperar.`),
  noLinkYet: () => T('Онлайн · ссылки пока нет', 'Online · no link yet', 'Online · sin enlace aún'),
  pasteLink: () => T('Вставь ссылку Zoom, Meet — любую', 'Paste a Zoom, Meet or any link', 'Pega un enlace de Zoom, Meet o cualquier otro'),
  saveLink: () => T('Сохранить ссылку', 'Save the link', 'Guardar el enlace'),
  askHost: (name: string) => T(`Попросить ${acc(name)} создать звонок`, `Ask ${name} to host instead`, `Pide a ${name} que sea anfitrión`),
  /** Уходит настоящим сообщением в чат — просьба должна дойти, а не остаться нажатой кнопкой. */
  askHostMsg: () =>
    T(
      'Создашь ссылку на звонок со своей стороны? У меня не выходит — пришли её сюда.',
      'Could you host the call and share the link here?'
    , '¿Podrías organizar la llamada y compartir el enlace aquí?'),
  linkComing: () => T('Онлайн · ссылка будет', 'Online · link coming', 'Online · enlace en camino'),

  /** O.21b — новое время отправлено; старое действует, пока встречное не принято. */
  newTimeSent: (name: string) => T(`Новое время отправлено ${dat(name)}`, `New time sent to ${name}`, `Nuevo horario enviado a ${name}`),
  newTimeNote: (name: string) =>
    T(
      `${name} увидит новое время и подтвердит его заново. До этого действует старое — ничего не отменено, и никому ничего делать не нужно.`,
      `${name} sees the new time and confirms again. Until then the old time still stands — nothing is cancelled and nobody has to do anything.`
    , `${name} ve la nueva hora y confirma de nuevo. Hasta entonces la hora antigua sigue vigente — nada se cancela y nadie tiene que hacer nada.`),
  newPrefix: (when: string) => T(`Новое: ${when}`, `New: ${when}`, `Nuevo: ${when}`),
  notAnsweredNewTime: () => T('Ещё не ответил(а) на новое время', 'Hasn’t answered the new time', 'No ha respondido al nuevo horario'),
  waitingOldTime: () => T('Ждёшь · старое время в силе', 'Waiting · old time still stands', 'Esperando · la hora antigua sigue vigente'),
  takeItBack: () => T('Забрать предложение', 'Take it back', 'Retirar la propuesta'),
  /** Принимающая сторона встречного времени (OF.C5): кадра в пачке нет, кнопки — по контракту сервера. */
  /** OF.C5 дословно: спешки нет, отказ ничего не отменяет. */
  oldTimeHolds: () =>
    T(
      'Старое время в силе, пока ты не ответишь, — спешки нет, и отказ ничего не отменяет.',
      'The old time holds until you answer, so there is no rush and nothing is lost if you say no.'
    , 'La hora anterior se mantiene hasta que respondas, así que no hay prisa y no se pierde nada si dices que no.'),
  hostAskedNote: () => T('Просьба отправлена в чат', 'Asked in chat', 'Preguntado en el chat'),
  /** Передача выбора — как её видят обе стороны, пока просимое не названо. */
  askedThemPlace: (name: string) => T(`Попросил(а) ${acc(name)} выбрать — ждём`, `You asked ${name} to choose — waiting`, `Pediste a ${name} que elija: esperando`),
  askedThemLink: (name: string) => T(`Попросил(а) ${acc(name)} создать звонок — ждём`, `You asked ${name} to host — waiting`, `Pediste a ${name} que sea anfitrión: esperando`),
  askedMePlace: (name: string) => T(`${name} просит тебя выбрать место`, `${name} asks you to pick the place`, `${name} te pide que elijas el lugar`),
  askedMeLink: (name: string) => T(`${name} просит тебя создать ссылку на звонок`, `${name} asks you to host the call`, `${name} te pide que crees el enlace`),
  /** Замок за два часа закрывает и место, и ссылку: экран говорит это словами, а не серой ошибкой. */
  whereLockedNote: () => T(
    'До встречи меньше двух часов — место и ссылка больше не меняются. Договоритесь в чате.',
    'Under two hours to go — the place and the link don’t change any more. Sort it out in the chat.',
    'Quedan menos de dos horas: el lugar y el enlace ya no cambian. Acordadlo en el chat.'),
  /** «Не смогу» внутри замка: встреча НЕ отменяется — второй просто узнаёт. Лист говорит правду. */
  cantMakeAsk: (name: string) => T(`Не сможешь прийти? ${name} узнает сразу`, `Can’t make it? ${name} will know right away`, `¿No puedes ir? ${name} lo sabrá al momento`),
  cantMakeNote: (name: string) => T(
    `Встреча останется в силе — ${name} увидит, что ты не придёшь, и решит сам(а). Отменить её за два часа уже нельзя.`,
    `The meetup stays on — ${name} will see you can’t make it and decide. Calling it off this close is no longer possible.`,
    `La quedada sigue en pie: ${name} verá que no puedes ir y decidirá. Cancelarla tan cerca ya no es posible.`),
  cantMakeYes: () => T('Да, не смогу', 'Yes, I can’t make it', 'Sí, no puedo ir'),
  cantMakeMine: () => T('Предупредил(а), что не придёшь', 'You said you can’t make it', 'Avisaste de que no vendrás'),
  /** Ответ на устаревшую версию плана: не «не удалось», а что именно случилось. */
  changedMeanwhile: () => T('План только что изменился — смотри свежую версию.', 'The plan just changed — see the latest version.', 'El plan acaba de cambiar: mira la versión actual.'),
  sendNewTime: () => T('Отправить новое время', 'Send the new time', 'Enviar la nueva hora'),

  /** O.C3 — план прислали мне; подтверждение закрепляет время за обоими. */
  sentPlan: (name: string) => T(`${name} прислал(а) план`, `${name} sent a plan`, `${name} envió un plan`),
  sentPlanNote: () =>
    T(
      'Подтверди — и время закреплено за вами обоими. Ссылка откроется за 10 минут, не сейчас.',
      'Confirm and it is set for both of you. The link opens 10 minutes before, not now.'
    , 'Confirma y se establece para ambos. El enlace se abre 10 minutos antes, no ahora.'),
  confirmAction: () => T('Подтвердить', 'Confirm', 'Confirmar'),
  yourTurn: () => T('Твой ход', 'Your turn', 'Es tu turno'),
  confirmedAt: (t: string) => T(`Подтвердил(а) · ${t}`, `Confirmed · ${t}`, `Confirmado · ${t}`),

  /** O.C5 — встречное время пришло мне: заголовок называет час, кнопки — оба часа. */
  suggestsTime: (name: string, t: string) => T(`${name} предлагает ${t}`, `${name} suggests ${t}`, `${name} propone ${t}`),
  moveNote: (name: string) =>
    T(
      `${name} хочет перенести встречу. Старое время в силе, пока ты не ответишь, — спешки нет, и отказ ничего не отменяет.`,
      `${name} wants to move it. The old time holds until you answer, so there is no rush and nothing is lost if you say no.`
    , `${name} quiere cambiarlo. El horario antiguo sigue vigente hasta que respondas, así que no hay prisa y no se pierde nada si dices que no.`),
  suggestedNewTime: () => T('Предложил(а) новое время', 'Suggested the new time', 'Sugerido el nuevo horario'),
  confirmTime: (t: string) => T(`Подтвердить ${t}`, `Confirm ${t}`, `Confirmar ${t}`),
  keepTime: (t: string) => T(`Оставить ${t}`, `Keep ${t}`, `Mantener ${t}`),

  /** OF.20 — офлайн-план отправлен: район виден сразу, адрес — только после её «да». */
  sentNoteOffline: (name: string) =>
    T(
      `${name} видит район и время. Точный адрес откроется только после подтверждения.`,
      `${name} sees the district and the time. The exact address opens for them only when they confirm.`
    , `${name} ve el distrito y la hora. La dirección exacta se le muestra solo cuando confirme.`),
  /** OF.21 — подтверждено, адрес открыт обоим. */
  addressOpenNote: (name: string) =>
    T(`У ${name} теперь есть точный адрес.`, `${name} has the exact address now.`, `${name} tiene ya la dirección exacta.`),
  /** OF.C3, сторона без подтверждения: адрес придёт после «да». */
  addressAfterConfirm: () =>
    T('Адрес откроется после твоего подтверждения.', 'The address opens once you confirm.', 'La dirección se muestra una vez que confirmes.'),

  /** OF.20a — согласовано, а точного места нет: выбрать до начала. */
  pickPlaceTitle: () => T('Выбери точное место', 'Pick the exact place', 'Elige el lugar exacto'),
  pickPlaceNote: (when: string, name: string) =>
    T(
      `Встреча (${when}) согласована. ${name} видит только район, пока ты не назовёшь место — выбери заранее, чтобы можно было спланировать дорогу.`,
      `${when} is agreed. ${name} only sees the district until you name a place — pick one ahead so they can plan the trip.`
    , `${when} acordado. ${name} solo ve el distrito hasta que elijas un lugar — elige uno con antelación para que puedan planificar el trayecto.`),
  placePlaceholder: () => T('Кафе, бар или парк…', 'Search for a café, bar or park', 'Buscar un café, bar o parque'),
  savePlace: () => T('Сохранить место', 'Save the place', 'Guardar el lugar'),
  askChoose: (name: string) => T(`Пусть выберет ${name}`, `Ask ${name} to choose`, `Pide a ${name} que elija`),
  askChooseMsg: () =>
    T('Выберешь место со своей стороны? Кафе, бар или парк — что удобнее.', 'Could you pick the place? A café, bar or park — whatever works.', '¿Podrías elegir el lugar? Un café, bar o parque — lo que mejor te vaya.'),
  noPlaceYet: () => T('Место пока не выбрано', 'No place yet', 'Todavía no hay lugar'),

  /** OF.22 — скоро начало: маршрут и честное «я опаздываю». */
  openRoute: () => T('Открыть маршрут', 'Open the route', 'Abre la ruta'),
  imLate: () => T('Я опаздываю', 'I’m running late', 'Llego tarde'),
  imHere: () => T('Я на месте', 'I’m here', 'Estoy aquí'),
  /** OF.22, подзаголовок: опоздание не страшно, если о нём сказать. */
  lateHint: (name: string) =>
    T(
      `Если опаздываешь — скажи ${name}: он(а) будет ждать у того же места.`,
      `If you’re running late, tell ${name} — they wait at the same place.`
    , `Si estás retrasado, avísale a ${name} — ellos esperan en el mismo lugar.`),
  /** OF.22a, заголовок. */
  lateKnows: (name: string) => T(`${name} знает, что ты опаздываешь`, `${name} knows you’re late`, `${name} sabe que llegas tarde`),
  /** OF.C3, приёмная сторона офлайна: подтверждение открывает адрес — в обе стороны. */
  sentPlanNoteOffline: () =>
    T(
      'Подтверди — и точный адрес откроется тебе. До этого виден только район, и это работает в обе стороны.',
      'Confirm and the exact address opens for you. Until then you only see the district — that works both ways.'
    , 'Confirma y la dirección exacta se te mostrará. Hasta entonces solo verás el distrito — esto funciona de ambas formas.'),
  /** OF.22a — опоздание сказано; никто не сидит в неведении. */
  lateSentNote: (name: string) =>
    T(
      `${name} знает, что ты опаздываешь. Ты ничего не отменял(а) — встреча в силе, просто ${name} не ждёт в неведении.`,
      `${name} knows you’re late. You didn’t cancel anything — the meetup is still on, they just aren’t waiting in the dark.`
    , `${name} sabe que estás tarde. No has cancelado nada — la quedada sigue adelante, simplemente no está esperando en la oscuridad.`),
  /** OF.C4 — опаздывает СОБЕСЕДНИК. */
  theyLate: (name: string) => T(`${name} опаздывает`, `${name} is running late`, `${name} está llegando tarde`),
  theyLateNote: (name: string) =>
    T(
      `${name} уже в пути. Ничего не отменено — займи столик, он(а) будет.`,
      `${name} is on the way. Nothing is cancelled — grab a table, they’ll be there.`
    , `${name} está en camino. Nada se cancela — coge una mesa, ya llega.`),
  cantWait: () => T('Не могу ждать', 'I can’t wait', 'No puedo esperar'),
  /** Живые статусы участников (OF.22/OF.22a/OF.23). */
  liveOtw: () => T('В пути', 'On the way', 'De camino'),
  liveLate: () => T('Опаздывает', 'Running late', 'Llegando tarde'),
  liveHere: () => T('На месте', 'At the place', 'En el lugar'),
  liveLateMine: () => T('Опаздываешь', 'Running late', 'Llegando tarde'),
  /** OF.23 — встреча сейчас, офлайн. */
  meetupNow: () => T('Встреча сейчас', 'Your meetup is now', 'Tu quedada es ahora'),
  meetupBlindNote: () =>
    T(
      'Kleal не видит встречу. Здесь ничего о ней не записывается. Потом мы спросим у обоих, состоялась ли она.',
      'Kleal can’t see the meetup. Nothing about it is recorded here. Afterwards we’ll ask you both whether it happened.'
    , 'Kleal no puede ver la quedada. Nada sobre ella se registra aquí. Después te preguntaremos a ambos si tuvo lugar.'),

  /** OF.21a — «предложить другое время» листом: быстрые часы и своё время. */
  suggestSheetTitle: () => T('Предложить другое время', 'Suggest another time', 'Sugerir otra hora'),
  insteadOf: (t: string) => T(`Вместо ${t}`, `Instead of ${t}`, `En lugar de ${t}`),
  orSetYour: () => T('или поставь своё', 'or set your time', 'o establece tu hora'),
  suggestSheetNote: (name: string) =>
    T(
      `${name} подтвердит заново. Текущее время держится, пока он(а) не ответит, — ничего не отменено.`,
      `${name} confirms again after this. The current time stays until they do — nothing is cancelled.`
    , `${name} confirma de nuevo después de esto. La hora actual sigue vigente hasta que lo haga — nada se cancela.`),

  /** OF.24a — «не состоялась»: причина. Ответ другим не показывается. */
  whatHappened: () => T('Что случилось?', 'What happened?', '¿Qué pasó?'),
  whatHappenedNote: () =>
    T(
      'Нужно, чтобы планы оставались честными. Твой ответ другим не показывается.',
      'Used to keep plans honest. Your answer is not shown to the others.'
    , 'Se usa para mantener los planes honestos. Tu respuesta no se muestra a los demás.'),
  reasonNoShow: (name: string) => T(`${name} не пришёл(шла)`, `${name} didn’t show up`, `${name} no ha aparecido`),
  reasonCouldnt: () => T('Не смог(ла) я', 'I couldn’t make it', 'No pude ir'),
  reasonClosed: () => T('Место было закрыто', 'The place was closed', 'El lugar estaba cerrado'),
  /**
   * Причина для ЗВОНКА. Список был жёстко офлайновым, и человеку, у которого не открылась
   * ссылка, предлагали объяснить срыв «закрытым местом» — то есть выбрать заведомо неправду или
   * «другое». Причина у срыва звонка ровно одна типичная, и она должна быть названа.
   */
  reasonLink: () => T('Ссылка не сработала', 'The link didn’t work', 'El enlace no funcionó'),
  reasonMoved: () => T('Договорились перенести', 'We agreed to move it', 'Nos pusimos de acuerdo para moverlo'),
  reasonOther: () => T('Другое', 'Something else', 'Otra cosa'),
  skip: () => T('Пропустить', 'Skip', 'Saltar'),

  /** OF.C4 — отменили офлайн-встречу: ждать за столиком, а не в звонке. */
  toldYouNoteOffline: (name: string) =>
    T(
      `${name} предупредил(а), а не оставил(а) тебя ждать за столиком. Никому ничего не засчитано — чат открыт, и новое время может предложить любой из вас.`,
      `${name} told you rather than leaving you at the table. Nothing is held against you — your chat stays open and either of you can suggest a new time.`
    , `${name} te lo dijo en lugar de dejarte en la mesa. No se te echa en cara — tu chat sigue abierto y cualquiera de los dos puede proponer un nuevo momento.`),
  /** OF.23a — своя отмена офлайна. */
  nobodyWaitingOffline: (name: string) =>
    T(
      `Никто не ждёт зря. ${name} уже видит отмену и не сидит за столиком в одиночку. Чат открыт — договориться о новом времени можно там.`,
      `Nobody is left waiting. ${name} sees it now, so they aren’t sitting at a table alone. Your chat stays open — you can agree a new time there.`
    , `Nadie queda esperando. ${name} lo ve ahora, así que no está sentado solo en una mesa. Tu chat permanece abierto — podéis acordar un nuevo horario allí.`),

  /** O.C4 — отменили мне; никто ничего не должен. */
  toldYouNote: (name: string) =>
    T(
      `${name} предупредил(а), а не оставил(а) тебя в звонке в одиночестве. Никому ничего не засчитано — чат открыт, и новое время может предложить любой из вас.`,
      `${name} told you rather than leaving you on the call alone. Nothing is held against you — your chat stays open and either of you can suggest a new time.`
    , `${name} te lo dijo en lugar de dejarte solo en la llamada. No se te echa en cara — tu chat sigue abierto y cualquiera de los dos puede proponer un nuevo momento.`),
  nothingToAnswer: () => T('Отвечать нечего', 'Nothing to answer', 'Nada que responder'),
  calledOff: () => T('Видеозвонок · отменён', 'Video call · called off', 'Video llamada · cancelada'),

  /** O.23a — создатель отменил встречу. */
  youToldCantMake: (name: string) =>
    T(`Ты сказал(а) ${dat(name)}, что не сможешь`, `You told ${name} you can’t make it`, `Le dijiste a ${name} que no puedes ir`),
  theyCantMake: (name: string) => T(`${name} не сможет прийти`, `${name} can’t make it`, `${name} no puede asistir`),
  calledOffByYou: () => T('Отменено тобой', 'Called off by you', 'Cancelada por ti'),
  calledOffBy: (name: string) => T(`Отменил(а) ${name}`, `Called off by ${name}`, `Cancelada por ${name}`),
  anotherTime: () => T('Другое время', 'Another time', 'Otra vez'),
  cantMakeStatus: () => T('Не сможет прийти', 'Can’t make it', 'No puede asistir'),
  toldJustNow: () => T('Узнал(а) только что', 'Told just now', 'Acabas de decirlo'),
  nobodyWaiting: (name: string) =>
    T(
      `Никто не ждёт зря. ${name} уже видит отмену и не сидит в звонке в одиночку. Чат открыт — договориться о новом времени можно там.`,
      `Nobody is left waiting. ${name} sees it now, so they aren’t sitting on a call alone. Your chat stays open — you can agree a new time there.`
    , `Nadie queda esperando. ${name} lo ve ahora, así que no está en una llamada solo. Tu chat permanece abierto — podéis acordar un nuevo horario allí.`),
};

/**
 * Состояние встречи одной строкой — для закреплённой карточки в переписке (MSG.07).
 *
 * `warn` означает «ход за тобой»: такая строка красится в акцент. Строка считается ЗДЕСЬ, а не в
 * экране, чтобы карточка в чате и заголовок на экране плана не разъехались в оценке одного и того
 * же состояния.
 */
export function planPinned(plan: any, me: string): { label: string; warn: boolean } {
  const norm = (v: any) => String(v || '').trim().toLowerCase();
  const meRow = (plan?.participants || []).find((p: any) => norm(p?.name) === norm(me));
  const iConfirmed = !!meRow?.confirmed;
  const pending = plan?.pending;
  if (pending) {
    return pending.mine
      ? { label: T('Новое время отправлено — ждём ответа', 'New time sent — waiting for an answer', 'Nuevo horario enviado — esperando respuesta'), warn: false }
      : { label: T('Предложено другое время — твой ход', 'Another time suggested — your turn', 'Otra hora propuesta — es tu turno'), warn: true };
  }
  if (plan?.state === 'confirmed') {
    // Согласовано, но идти некуда: у звонка нет ссылки, у встречи — места.
    if (!plan?.address_set) {
      return plan?.mode === 'online'
        ? { label: T('Подтверждено · ссылки пока нет', 'Confirmed · no link yet', 'Confirmado · sin enlace aún'), warn: true }
        : { label: T('Подтверждено · место пока не выбрано', 'Confirmed · no place yet', 'Confirmado · sin lugar aún'), warn: true };
    }
    return { label: T('Подтверждено обоими', 'Confirmed by both', 'Confirmado por ambos'), warn: false };
  }
  if (!iConfirmed) return { label: T('Ждёт твоего подтверждения', 'Waiting for you to confirm', 'Esperando que lo confirmes'), warn: true };
  return { label: T('Отправлено · ждём ответа', 'Sent · waiting for an answer', 'Enviado · esperando respuesta'), warn: false };
}

/** O.19a/O.19b — полоса отсчёта внизу чата: действие случится через 4 секунды, если не отменить. */
export const UNDO_BAR = {
  creating: (name: string) => T(`Создаю план с ${ins(name)}`, `Creating the plan with ${name}`, `Creando el plan con ${name}`),
  ending: () => T('Завершаю чат. Можно вернуться снова', 'Ending chat. You can pick again', 'Finalizando la conversación. Puedes elegir de nuevo'),
  undo: (n: number) => T(`Отменить · ${n}`, `Undo · ${n}`, `Deshacer · ${n}`),
  /** OF.19a — план уже собран листом «Send the plan?», уходит через 4 секунды. */
  sending: () => T('Отправляю план', 'Sending the plan', 'Enviando el plan'),
};

/** OF.19 / OF.19d — меню переписки и лист «Send the plan?». */
export const CHATMENU = {
  title: () => T('Действия в чате', 'Chat options', 'Opciones del chat'),
  makePlan: () => T('Составить план', 'Make the plan', 'Hacer el plan'),
  makePlanNote: (o: string) => T(`Отправить ${o} время и место`, `Send ${o} a time and place`, `Envía a ${o} una hora y un lugar`),
  openPlan: () => T('Открыть план', 'Open the plan', 'Abrir el plan'),
  openPlanNote: (o: string) => T(`Где вы с ${o} сейчас`, `Where you and ${o} are now`, `En qué punto estáis ${o} y tú`),
  intentInfo: () => T('О затее', 'Intent info', 'Sobre la propuesta'),
  intentInfoNote: () => T('Твой запрос и кого ты позвал(а)', 'Your request and who you invited', 'Tu solicitud y a quién invitaste'),
  endChat: () => T('Завершить чат', 'End the chat', 'Terminar el chat'),
  endChatNote: () => T('Закрывает чат для вас обоих', 'Closes the chat for both of you', 'Cierra el chat para los dos'),
  sendTitle: () => T('Отправить план?', 'Send the plan?', '¿Enviar el plan?'),
  sendNote: (o: string) => T(`${o} получит его и сможет подтвердить или предложить другое время. Точное место откроется, когда подтвердите оба.`,
    `${o} gets it and can confirm or suggest another time. The exact spot opens once you both confirm.`,
    `${o} lo recibe y puede confirmar o proponer otra hora. El sitio exacto se abre cuando confirméis los dos.`),
  sendTo: (o: string) => T(`Отправить ${o}`, `Send to ${o}`, `Enviar a ${o}`),
  change: () => T('Изменить', 'Change', 'Cambiar'),
};

/**
 * Тред — кадры MSG.06–MSG.11 и карточки приглашений MSG.18–MSG.21.
 * Подзаголовок шапки, закреплённый план, записка «отправлено как предложение», подсказка Kleal
 * и лист интента. Всё считается из настоящих данных; чего у сервера нет (присутствие «online
 * now», календарь занятости) — здесь и не обещается.
 */
/** Имя, под которым приходят ответы поддержки и модерации. Одно на клиент и сервер. */
export const KLEAL_SENDER = 'Kleal';

/**
 * Реплика Kleal по коду — на языке приложения, а не английским текстом сервера. GR.52: удалённому
 * из группы Kleal говорит, кто удалил, что причину не назовёт и что остальные интенты в силе.
 * Неизвестный код — null: показываем текст сервера как есть.
 */
export function klealText(m: { code?: string; by?: string; title?: string } | null | undefined): string | null {
  if (!m || !m.code) return null;
  if (m.code === 'group_removed') {
    const by = String(m.by || ''), title = String(m.title || '');
    return T(`${by} удалил(а) тебя из «${title}». Причину я назвать не могу. Остальные твои интенты в силе — я продолжаю искать похожее.`,
      `${by} removed you from ${title}. I can’t share the reason. Your other intents aren’t affected — I’m still looking for something close.`,
      `${by} te quitó de ${title}. No puedo decirte el motivo. Tus otras propuestas siguen en pie — sigo buscando algo parecido.`);
  }
  return null;
}

export const THREAD = {
  planSet: (when: string) => T(`План: ${when}`, `Plan set · ${when}`, `Plan establecido · ${when}`),
  proposalSent: () => T('Предложение отправлено · ждём', 'Proposal sent · waiting', 'Propuesta enviada · esperando'),
  planFromThem: () => T('Тебе прислали план', 'They sent you a plan', 'Te han mandado un plan'),
  talkingSince: (day: string) => T(`Общаетесь с ${day}`, `Talking since ${day}`, `Hablando desde ${day}`),
  /** Разговор начался сегодня — «с субботы» про сегодняшний день читается как «давно». */
  talkingToday: () => T('Общаетесь сегодня', 'Talking since today', 'Hablando desde hoy'),
  /** «с четверга», а не «с четверг»: подзаголовку нужен родительный падеж. */
  weekdayGen: (dayIndex: number) =>
    ['воскресенья', 'понедельника', 'вторника', 'среды', 'четверга', 'пятницы', 'субботы'][dayIndex] || '',
  matchedOn: (title: string) => T(`Мэтч по «${title}»`, `Matched on “${title}”`, `Coincidencia por «${title}»`),
  /** Подпись закреплённой карточки интента: куда ведёт нажатие. */
  openIntent: () => T('Открыть интент', 'View the intent', 'Ver la propuesta'),

  /** MSG.09 — под предложением, дословно: ничего не забронировано до «да». */
  sentAsProposal: (name: string) => T(`Отправлено ${name} как предложение`, `Sent to ${name} as a proposal`, `Enviado a ${name} como propuesta`),
  nothingBooked: (name: string) =>
    T(`Ничего не забронировано, пока ${name} не скажет «да».`, `Nothing is booked until ${name} says yes.`, `Nada está reservado hasta que ${name} diga que sí.`),

  /** MSG.08 — подсказка Kleal. Счёт сообщений настоящий; свободные часы не обещаем: календарей
   *  у Kleal нет, и «в четверг свободно у обоих» было бы выдумкой. */
  nudge: (n: number, name: string) =>
    T(
      `Вы обменялись ${n} сообщениями, а время так и не назначено. Хочешь, предложу ${name} встретиться?`,
      `You two have swapped ${n} messages and no time. Want me to put a plan to ${name}?`
    , `Los dos habéis intercambiado ${n} mensajes y ninguna hora. ¿Quieres que proponga un plan a ${name}?`),
  nudgeYes: () => T('Да, предложи', 'Yes, propose it', 'Sí, proponerlo'),
  nudgeOther: () => T('Другой день', 'Another day', 'Otro día'),
  nudgeNot: () => T('Пока нет', 'Not yet', 'Todavía no'),

  /** MSG.10 — лист интента. */
  intentMode: () => T('Режим', 'Mode', 'Modo'),
  intentWhen: () => T('Когда', 'When', 'Cuándo'),
  intentWhere: () => T('Где', 'Where', 'Dónde'),
  intentWho: () => T('Кто', 'Who', 'Quién'),
  intentStatus: () => T('Статус', 'Status', 'Estado'),
  offlineInPerson: () => T('Оффлайн · вживую', 'Offline · in person', 'Presencial · en persona'),
  onlineMode: () => T('Онлайн', 'Online', 'Online'),
  whereAfterConfirm: () => T('Точное место — после подтверждения обоих', 'Exact place after you both confirm', 'Lugar exacto tras confirmar ambos'),
  whereLink: () => T('Ссылка — после подтверждения', 'Link after you confirm', 'Enlace después de confirmar'),
  matchedAgo: (name: string, days: number) =>
    days <= 0
      ? T(`Мэтч с ${ins(name)} · сегодня`, `Matched with ${name} · today`, `Coincidencia con ${name} · hoy`)
      : T(`Мэтч с ${ins(name)} · ${days} дн. назад`, `Matched with ${name} · ${days} days ago`, `Coincidencia con ${name} · hace ${days} ${days === 1 ? 'día' : 'días'}`),
  statusWaiting: () => T('Ждёт ответа', 'Waiting for an answer', 'Esperando una respuesta'),

  /** MSG.18–MSG.21 — приглашение как карточка в треде. */
  hoursToAnswer: (h: number) => T(`осталось ${h} ч на ответ`, `${h} h left to answer`, `Quedan ${h} h para responder`),
  reviewInvite: () => T('Открыть приглашение', 'Review invite', 'Revisar invitación'),
  youDeclined: () => T('Ты отказал(ся/ась)', 'You declined', 'Lo rechazaste'),
  declinedClear: (name: string) =>
    T(`${name} видит ясное «нет», а не «может быть».`, `${name} sees a clear no, not a maybe.`, `${name} ve claramente un no, no un quizás.`),
  inviteExpired: () => T('Истекло · без ответа', 'Expired · no reply', 'Caducado · sin respuesta'),
  /** Часы — настоящие, из самой заявки (created→expires_at): сервер держит место 72 часа,
   *  а не 24 с борда. */
  expiredNote: (h: number) =>
    T(
      `Приглашение держит место ${h} ч, чтобы никто не ждал в неведении.`,
      `Invites hold a seat for ${h} hours so nobody is blocked waiting.`
    , `Las invitaciones reservan un sitio durante ${h} horas para que nadie quede bloqueado esperando.`),
  dismiss: () => T('Скрыть', 'Dismiss', 'Rechazar'),
  joined: (title: string) => T(`Приглашение принято · ${title}`, `You joined · ${title}`, `Te uniste · ${title}`),
};

/** O.C1 — входящее приглашение, сторона гостя. */
export const INVITE = {
  title: (name: string) => T(`${name} пригласил(а) тебя`, `${name} invited you`, `${name} te ha invitado`),
  note: (what: string, name: string) =>
    T(
      `${what ? what + '. ' : ''}Если присоединишься, откроется чат с ${ins(name)} — детали договорите там.`,
      `${what ? what + '. ' : ''}If you join, a chat with ${name} opens and you two agree the details there.`
    , `${what ? what + '. ' : ''}Si te unes, se abre un chat con ${name} y los dos acordáis los detalles allí.`),
  /** Ссылки в приглашении нет и не должно быть: она приходит позже, через план (OF.C3). */
  linkFrom: (name: string) => T(`Видеозвонок · ссылка у ${gen(name)}`, `Video call · link from ${name}`, `Video llamada · enlace de ${name}`),
  inPerson: () => T('Встреча вживую', 'In person', 'Presencial'),
  /** OF.C1: «да» ещё не чат — организатор выбирает одного из ответивших. */
  notePick: (what: string, name: string) =>
    T(`${what ? what + '. ' : ''}Скажи «да» — если ${name} выберет тебя, откроется чат.`,
      `${what ? what + '. ' : ''}Say yes — if ${name} picks you, a chat opens.`,
      `${what ? what + '. ' : ''}Di que sí — si ${name} te elige, se abre un chat.`),
  /** HY.C1 — гибрид: прийти или подключиться, выбор в день встречи. */
  notePickHybrid: (what: string, name: string, area: string) =>
    T(`${what ? what + '. ' : ''}Приходи${area ? ' в ' + area : ''} или подключайся по видео — выберешь в день встречи. Скажи «да» — если ${name} выберет тебя, откроется чат.`,
      `${what ? what + '. ' : ''}Come${area ? ' to ' + area : ' in person'} or join by video — you choose on the day. Say yes — if ${name} picks you, a chat opens.`,
      `${what ? what + '. ' : ''}Ven${area ? ' a ' + area : ''} o únete por vídeo — eliges ese día. Di que sí — si ${name} te elige, se abre un chat.`),
  hybridWhere: () => T('Точное место — если придёшь вживую · ссылка — для звонка', 'Exact spot if you come in person · link for the call',
                       'Sitio exacto si vienes en persona · enlace para la llamada'),
  callLinkFrom: (name: string) => T(`Ссылка на звонок от ${name}`, `Call link from ${name}`, `Enlace de llamada de ${name}`),
  sayYes: () => T('Сказать «да»', 'Say yes', 'Decir que sí'),
  /** OF.C1a */
  saidYesTitle: () => T('Ты ответил(а) «да»', 'You said yes', 'Has dicho que sí'),
  saidYesNote: (name: string, online = false) =>
    T(`${name} позвал(а) нескольких человек и выбирает одного. Если выберет тебя — откроется чат, и Kleal даст знать.`,
      `${name} invited a few people and picks one to ${online ? 'talk to' : 'meet'}. If ${name} picks you, the chat opens and Kleal lets you know.`,
      `${name} invitó a varias personas y elige a una. Si te elige, se abre el chat y Kleal te avisa.`),
  picking: (online = false) => online
    ? T('Выбирает, с кем поговорить', 'Picking who to talk to', 'Eligiendo con quién hablar')
    : T('Выбирает, с кем встретиться', 'Picking who to meet', 'Eligiendo con quién quedar'),
  /** O.C1: вторая строка карточки у звонка. */
  linkOpensNote: () => T('Ссылка откроется за 10 минут до звонка', 'The link opens 10 minutes before the call', 'El enlace se abre 10 minutos antes de la llamada'),
  saidYes: () => T('Ответил(а) «да»', 'Said yes', 'Dijo que sí'),
  takeBack: () => T('Забрать своё «да»', 'Take back my yes', 'Retirar mi sí'),
  /** OF.N1 / OF.N2 */
  pickedOtherTitle: (name: string) => T(`${name} выбрал(а) другого человека`, `${name} picked someone else`, `${name} eligió a otra persona`),
  pickedOtherNote: () =>
    T('На эту встречу выбран другой человек — дело не в тебе. Создай свою затею или посмотри, кого Kleal подобрал тебе.',
      'Another person was chosen for this one — it’s nothing you did. Create your own plan, or see people Kleal picked for you.',
      'Se eligió a otra persona para esto — no es por ti. Crea tu propio plan o mira a quién eligió Kleal para ti.'),
  closedEarlyTitle: () => T('Приглашение закрыто', 'This invite is closed', 'Esta invitación está cerrada'),
  closedEarlyNote: (name: string) =>
    T(`${name} закрыл(а) приглашение раньше, чем ты ответил(а) — дело не в тебе. Создай свою затею или посмотри, кого Kleal подобрал тебе.`,
      `${name} closed the invite before you answered — it’s nothing you did. Create your own plan, or see people Kleal picked for you.`,
      `${name} cerró la invitación antes de que respondieras — no es por ti. Crea tu propio plan o mira a quién eligió Kleal para ti.`),
  didntAnswer: () => T('Не ответил(а)', 'Didn’t answer', 'No respondió'),
  seePeople: () => T('Люди для тебя', 'See people for you', 'Ver personas para ti'),
  invitedYou: () => T('Пригласил(а) тебя', 'Invited you', 'Te ha invitado'),
  join: () => T('Присоединиться', 'Join', 'Únete'),
  notThisTime: () => T('Не в этот раз', 'Not this time', 'No esta vez'),
  declinedNote: () => T('Ты отказал(ась/ся). Приглашение закрыто.', 'You passed. The invite is closed.', 'Has dicho que no. La invitación está cerrada.'),
  /**
   * Истёкшее и отозванное приглашение (O.C1).
   *
   * Обе эти ветки проваливались в «Подтвердил(а)» — экран говорил РОВНО ПРОТИВОПОЛОЖНОЕ правде и
   * не давал ни объяснения, ни выхода. У отказа объяснение было, у истёкшего — нет.
   *
   * Молчание — не вина: человек мог не открыть приложение, и говорить ему «ты отказался» нельзя.
   */
  expiredStatus: () => T('Срок вышел', 'Expired', 'Caducado'),
  expiredNote: () => T(
    'Ты не успел(а) ответить, и место освободилось. Это не отказ — просто срок вышел.',
    'You didn’t get to answer in time and the seat went. Not a refusal — the invite just ran out.'
  , 'No respondiste a tiempo y el sitio se ocupó. No es un rechazo — simplemente se acabó la invitación.'),
  /**
   * Любой ЗАКРЫТЫЙ статус, кроме сгоревшего и отозванного, — например `policy_revoked`, когда
   * приглашение снял сам сервис. Раньше все они попадали в «иначе» и читались как «Подтвердил(а)».
   * Причину не называем: она про решение сервиса или про третьего человека, и человеку тут важно
   * не «почему», а «этого больше нет — иди дальше».
   */
  closedStatus: () => T('Приглашение закрыто', 'Invitation closed', 'Invitación cerrada'),
  closedNote: () =>
    T(
      'Это приглашение больше не действует. Ничего страшного — есть и другие.',
      'This invitation is no longer open. That’s fine — there are others.'
    , 'Esta invitación ya no está abierta. Está bien — hay otras.'),
  withdrawnStatus: () => T('Отозвано', 'Withdrawn', 'Retirado'),
  withdrawnNote: () => T(
    'Приглашение отозвали до того, как ты ответил(а). Ты ни при чём.',
    'The invite was withdrawn before you answered. Nothing you did.'
  , 'La invitación se retiró antes de que respondieras. No fue por algo que hicieras tú.'),
  lookElse: () => T('Посмотреть другое', 'Find something else', 'Buscar otra cosa'),
  goneNote: () =>
    T('Приглашение больше не действует: истекло или уже решено.', 'This invite is no longer live: it expired or was already settled.', 'Esta invitación ya no está activa: caducó o ya se resolvió.'),
};

/** Оценки — те же три, что на кадре. Ключи английские: их читает сервер. */
/** Три чипа кадра O.25 и их значение на серверной шкале: mp_feedback принимает ТОЛЬКО int 1–5,
 *  строковый ключ он молча отбрасывает — оценка выглядела бы отправленной, но не сохранялась. */
export const RATINGS: [string, () => string, number][] = [
  ['great', PLAN.great, 5],
  ['fine', PLAN.fine, 3],
  ['not_great', PLAN.notGreat, 1],
];

/**
 * В каком состоянии план прямо сейчас. Одно место на все кадры O.20–O.25, чтобы экран не решал
 * это в трёх разных условиях и не разошёлся сам с собой.
 *
 * `LINK_LEAD_MIN` — те самые десять минут с кадра O.21.
 */
export const LINK_LEAD_MIN = 10;

export type PlanPhase = 'waiting' | 'confirmed' | 'soon' | 'now' | 'after' | 'cancelled';

export function planPhase(plan: any, nowMs = Date.now()): PlanPhase {
  const state = String(plan?.state || '');
  if (state === 'cancelled') return 'cancelled';
  // done — итоги уже подведены. Часам тут веры нет: сервер ставит done по факту ответов, и
  // показывать такому плану «ссылка откроется в …» значило бы звать на прошедшую встречу.
  if (state === 'done') return 'after';
  const startsMs = typeof plan?.starts_at === 'number' ? plan.starts_at * 1000 : 0;
  const bothConfirmed = (plan?.participants || []).every((p: any) => p?.confirmed);
  if (!bothConfirmed && state !== 'confirmed') return 'waiting';
  if (!startsMs) return 'confirmed';
  const minsToStart = (startsMs - nowMs) / 60000;
  // Встреча считается прошедшей через час после начала: до этого «состоялась ли» спрашивать рано.
  if (minsToStart < -60) return 'after';
  if (minsToStart <= 0) return 'now';
  // Встреча вживую «на носу» за полчаса (OF.22 «Starts in 30 minutes»): нужно успеть дойти и сказать
  // «опаздываю». Звонку хватает десяти минут — столько же, сколько до открытия ссылки.
  // У гибрида есть дорога к месту, поэтому «на носу» он тоже за полчаса (HY.22); ссылка открывается за десять минут.
  if (minsToStart <= (plan?.mode === 'online' ? LINK_LEAD_MIN : 30)) return 'soon';
  return 'confirmed';
}

/** Сколько минут осталось до начала — для строки «начало через N мин». */
export function minutesToStart(plan: any, nowMs = Date.now()): number {
  const startsMs = typeof plan?.starts_at === 'number' ? plan.starts_at * 1000 : 0;
  return startsMs ? Math.max(0, Math.round((startsMs - nowMs) / 60000)) : 0;
}

/** Время, когда откроется ссылка, — на десять минут раньше начала. */
export function linkOpensAt(plan: any, ru = true): string {
  const startsMs = typeof plan?.starts_at === 'number' ? plan.starts_at * 1000 : 0;
  if (!startsMs) return '';
  const d = new Date(startsMs - LINK_LEAD_MIN * 60000);
  return d.toLocaleTimeString(dateLocale(ru), { hour: '2-digit', minute: '2-digit', hour12: use12h(ru) });
}

/**
 * СОБЫТИЕ ПЛАНА в ленте переписки. Сервер кладёт код и факты, строку собираем здесь.
 *
 * Почему не готовым текстом с сервера: у двоих может быть разный язык интерфейса, и русская
 * фраза, склеенная на сервере, приезжала бы на английский экран. Поэтому едет `code` плюс то, из
 * чего строка складывается, а «Ты» против имени решается уже на месте — по тому, кто смотрит.
 *
 * Зачем это вообще. Раньше план жил только на своём экране: второй стороне карточка молча меняла
 * состояние — ни строки о том, что план отправлен, ни о том, что он подтверждён, ни о том, что
 * место наконец названо. Двое договаривались о встрече, читая два разных экрана.
 */
export type SysMsg = {
  code: string;
  by?: string;
  title?: string;
  /** Время встречи в секундах — форматируется на языке читателя, не отправителя. */
  at?: number;
  was?: number;
  mode?: string;
  district?: string;
  kind?: string;
  /** С какой стороны человек придёт у гибрида: 'in_person' | 'call' (событие plan_side). */
  side?: string;
  /** Что человек сообщил перед встречей: 'otw' | 'late' | 'here' | 'cant_make_it' (plan_status). */
  status?: string;
  /** Через сколько минут будет — у «выхожу» и «опаздываю». */
  eta?: number;
};

/**
 * Реплика ленты.
 *
 * `cid` — ключ, который придумал ОТПРАВИТЕЛЬ. По нему своя реплика, показанная сразу, узнаётся
 * в том, что принёс опрос. Раньше узнавание шло по ТЕКСТУ, и у голосового оно не работало вовсе:
 * локально текст пустой, а сервер кладёт туда расшифровку — голосовое показывалось дважды.
 *
 * `state` есть только у своей неподтверждённой реплики: `sending`, пока ответа нет, и `failed`,
 * если сервер отказал. У доставленных его нет — отсутствие и означает «дошло».
 */
export type Msg = {
  id?: string; from?: string; to?: string; text?: string; t?: number; sys?: SysMsg;
  cid?: string; state?: 'sending' | 'failed'; voice?: any; video?: any;
  /** Реакции: смайлик → кто его поставил. Пусто — реакций нет, поля просто не будет. */
  r?: Record<string, string[]>;
  /** Цитата: кусок того, на что отвечают. Едет РЯДОМ, а не ссылкой — см. сервер. */
  rt?: { id?: string; from?: string; text?: string; kind?: string };
  deleted?: boolean;
  /** Автор заблокирован — реплика скрыта только у меня (MSG.14b). */
  hidden?: boolean;
};

/**
 * Набор реакций — закрытый и маленький, тот же, что проверяет сервер.
 *
 * Открытый набор вернул бы в переписку произвольную картинку от постороннего: это уже не реакция,
 * а сообщение в обход всех проверок. Шесть штук покрывают то, ради чего реакция и нужна:
 * согласиться, обрадоваться, удивиться, посочувствовать.
 */
export const REACTIONS = ['❤️', '👍', '😂', '🔥', '😮', '😢'] as const;

/**
 * Разбить текст на куски: обычные и ссылки.
 *
 * Ссылка в пузыре была мёртвым серым текстом — не нажимается, не подсвечена, и скопировать её
 * тоже было нечем. При этом продукт сам подталкивает слать ссылку репликой: у онлайн-встречи
 * ссылка на созвон — это и есть место встречи.
 *
 * Ищем только то, в чём нельзя ошибиться: `http://`, `https://` и `www.`. Голые домены вроде
 * «увидимся в 19.00» распознавать нельзя — точка между цифрами превратила бы время во внешний
 * адрес, и человек ушёл бы из приложения, промахнувшись пальцем по собственному сообщению.
 *
 * Хвостовая пунктуация не входит в адрес: «зайди на example.com/x, там всё» — запятая тут от
 * предложения, а не от ссылки, и с ней адрес не откроется.
 */
const LINK_RE = /(https?:\/\/[^\s]+|www\.[^\s]+)/gi;
const TRAILING = /[.,;:!?)\]}»"']+$/;

export type TextPart = { text: string; href?: string };

export function linkParts(text: string): TextPart[] {
  const src = String(text || '');
  if (!src) return [];
  const out: TextPart[] = [];
  let last = 0;
  for (const m of src.matchAll(LINK_RE)) {
    const at = m.index ?? 0;
    let raw = m[0];
    const tail = raw.match(TRAILING);
    if (tail) raw = raw.slice(0, raw.length - tail[0].length);
    if (!raw) continue;
    if (at > last) out.push({ text: src.slice(last, at) });
    out.push({ text: raw, href: /^www\./i.test(raw) ? `https://${raw}` : raw });
    last = at + raw.length;
  }
  if (last < src.length) out.push({ text: src.slice(last) });
  return out.length ? out : [{ text: src }];
}

/**
 * Подряд идущие реплики одного человека — ОДНА серия: время под ней одно и хвостик один.
 *
 * Экран печатал время под каждым пузырём без исключения, и живая переписка превращалась в
 * столбик часов: три коротких реплики подряд давали три одинаковых «19:42». Борд (OF.18)
 * рисует их под одной меткой, и так делает любой мессенджер.
 *
 * Пять минут — не украшение: реплики, разделённые паузой, это уже другой заход в разговор, и
 * склеивать их в одну серию значит скрывать, что человек вернулся спустя время.
 */
export const SERIES_GAP_S = 300;

export function sameSeries(a?: Msg, b?: Msg): boolean {
  if (!a || !b || a.sys || b.sys) return false;
  const who = (m: Msg) => String(m.from || '').trim().toLowerCase();
  if (who(a) !== who(b)) return false;
  if (Math.abs((b.t || 0) - (a.t || 0)) > SERIES_GAP_S) return false;
  return new Date((a.t || 0) * 1000).toDateString() === new Date((b.t || 0) * 1000).toDateString();
}

/** «Пт, 8 авг · 20:00» из секунд. Пусто — времени нет, и выдумывать его нечем. */
function atLabel(at: any, ru: boolean): string {
  if (typeof at !== 'number' || !isFinite(at) || !at) return '';
  const d = new Date(at * 1000);
  const day = d.toLocaleDateString(dateLocale(ru), { weekday: 'short', day: 'numeric', month: 'short' });
  const hm = d.toLocaleTimeString(dateLocale(ru), { hour: '2-digit', minute: '2-digit', hour12: use12h(ru) });
  return `${day} · ${hm}`;
}

/**
 * Строка события для ленты. `me` — кто смотрит: свои действия называются «ты», чужие — именем.
 * Неизвестный код возвращает пустую строку: показать сырой код человеку хуже, чем не показать
 * ничего, а новый код доедет со следующей версией клиента.
 */
/**
 * ПОДПИСИ КНОПОК ПОД СОБЫТИЕМ ПЛАНА.
 *
 * Событие в ленте рассказывает, что случилось; кнопка даёт на это ответить, не уходя с переписки.
 * Просьба владельца дословно: «чтобы, когда я создал план, у человека в чат пришло сообщение
 * подтвердить план — такую коралловую, красивую кнопочку „подтвердить план“».
 *
 * Кнопка появляется только там, где от человека ЖДУТ ответа. Событие-факт («я на месте»,
 * «встреча отменена») кнопки не получает: отвечать на него нечем, а лишняя кнопка в ленте хуже
 * её отсутствия.
 */
export const SYS_ACT = {
  confirmPlan: () => T('Подтвердить план', 'Confirm the plan', 'Confirmar el plan'),
  acceptTime: (hour: string) => T(`Подтвердить ${hour}`, `Confirm ${hour}`, `Confirmar ${hour}`),
  keepTime: (hour: string) => T(`Оставить ${hour}`, `Keep ${hour}`, `Mantener ${hour}`),
  pickPlace: () => T('Выбрать место', 'Pick the place', 'Elegir el lugar'),
  addLink: () => T('Добавить ссылку', 'Add the link', 'Añadir el enlace'),
  openCall: () => T('Открыть звонок', 'Open the call', 'Abrir la llamada'),
  openIntent: () => T('Открыть затею', 'Open the intent', 'Abrir la propuesta'),
};

export function sysLine(sys: SysMsg | undefined, me: string, ru: boolean): string {
  if (!sys?.code) return '';
  const by = String(sys.by || '').trim();
  // «Это сделал я» — по id (`by_id`), по подписи только без него: у тёзок подписи равны.
  const mine = !!by && isMe(by, (sys as any).by_id, me);
  const when = atLabel(sys.at, ru);
  const hour = msgTime(sys.at, ru);
  const wasHour = msgTime(sys.was, ru);
  switch (sys.code) {
    // O.19c: разговор закрыли с той стороны. Раньше второй об этом не узнавал вовсе и продолжал
    // ждать ответа в открытой переписке.
    case 'chat_ended':
      return mine
        ? T('Ты завершил(а) разговор', 'You ended the chat', 'Tú terminaste la conversación')
        : T(`${by} завершил(а) разговор. Можно выбрать другого.`,
            `${by} ended the chat. You can pick again.`, `${by} terminó el chat. Puedes elegir de nuevo.`);
    // Переписка началась не с нуля: эти двое уже говорили в группе, которая не собралась.
    // Без этой строки личный чат открывается пустым, и непонятно, откуда он взялся.
    case 'converted_from_group':
      return T('Группа не собралась — вы продолжаете вдвоём. Переписка здесь.',
               'The group didn’t fill up — the two of you carry on. The chat is here.', 'El grupo no se llenó — los dos seguís igual. El chat está aquí.');
    case 'group_closed_invite':
      return T(
        `${by} закрыл(а) «${String(sys.title || 'группу')}» до назначения плана, поэтому приглашение больше не действует. Ты ни при чём. Я продолжу искать что-то похожее.`,
        `${by} closed ${String(sys.title || 'the group')} before a plan was set, so your invite is gone. Nothing you did. I’m still looking for something close.`
      , `${by} cerró ${String(sys.title || 'el grupo')} antes de fijar un plan, así que tu invitación ya no existe. No fue por nada que hicieras tú. Sigo buscando algo parecido.`);
    /*
     * ВТОРАЯ ЗАТЕЯ К ТОМУ, С КЕМ УЖЕ ГОВОРИМ. Раньше она приходила молча: на сервере появлялась
     * новая заявка, а в переписке не менялось ничего — закреплённая полоса сверху занята живым
     * планом по ПРЕЖНЕЙ затее, и другого входа в карточку с этого экрана нет. Проверено живым
     * опытом: у пары встреча по «Поиграть в падель», приходит «Сходить в кино» — и про кино в
     * ленте нет ни строки.
     */
    case 'intent_new': {
      const what = String(sys.title || '').trim();
      if (!what) {
        return mine ? T('Ты предложил(а) ещё одну затею', 'You suggested another intent', 'Has propuesto otra idea')
                    : T(`${by} предлагает ещё одну затею`, `${by} suggests another intent`, `${by} propone otra idea`);
      }
      return mine
        ? T(`Ты предложил(а) ещё одну затею: «${what}»`,
            `You suggested another intent: “${what}”`, `Has propuesto otra idea: «${what}»`)
        : T(`${by} предлагает ещё одну затею: «${what}»`,
            `${by} suggests another intent: “${what}”`, `${by} propone otra idea: «${what}»`);
    }
    case 'plan_proposed': {
      /*
       * Сервер кладёт в событие и режим, и район, а строка их не показывала — человек читал
       * «предложил встречу» и шёл на экран плана выяснять, где и как. Раз факты уже приехали,
       * пусть они и будут в строке: тогда второй решает, не уходя из переписки.
       */
      const online = String(sys.mode || '') === 'online';
      const spot = online ? T('онлайн', 'online', 'en línea')
                         : String(sys.district || '').trim();
      const tail = [when, spot].filter(Boolean).join(', ');
      const tl = tail ? ' — ' + tail : '';
      return mine
        ? T(`Ты предложил(а) встречу${tl}`, `You proposed a meetup${tl}`, `Propusiste una quedada${tl}`)
        : T(`${by} предложил(а) встречу${tl}`, `${by} proposed a meetup${tl}`, `${by} propuso una quedada${tl}`);
    }
    // Та самая строка, которой не хватало: она приходит обоим и означает, что торг закончен.
    case 'plan_confirmed':
      return T(`План подтверждён${when ? ' — ' + when : ''}. Время закреплено за вами обоими.`,
               `The plan is confirmed${when ? ' — ' + when : ''}. The time is set for both of you.`, `El plan está confirmado${when ? ' — ' + when : ''}. La hora está fijada para ambos.`);
    case 'plan_place':
      if (sys.kind === 'link') {
        return mine ? T('Ты добавил(а) ссылку на звонок', 'You added the call link', 'Añadiste el enlace de la llamada')
                    : T(`${by} добавил(а) ссылку на звонок`, `${by} added the call link`, `${by} añadió el enlace de la llamada`);
      }
      return mine ? T('Ты назвал(а) место встречи', 'You named the place', 'Tú elegiste el lugar')
                  : T(`${by} назвал(а) место встречи`, `${by} named the place`, `${by} eligió el lugar`);
    case 'plan_counter':
      return mine
        ? T(`Ты предложил(а) перенести${hour ? ' на ' + hour : ''} — до ответа в силе прежнее время`,
            `You suggested moving it${hour ? ' to ' + hour : ''} — the old time holds until they answer`, `Propusiste cambiarlo${hour ? ' a las ' + hour : ''} — la hora anterior sigue en pie hasta que responda`)
        : T(`${by} предлагает${hour ? ' ' + hour : ' другое время'}${wasHour ? ' вместо ' + wasHour : ''}`,
            `${by} suggests${hour ? ' ' + hour : ' another time'}${wasHour ? ' instead of ' + wasHour : ''}`, `${by} propone${hour ? ' las ' + hour : ' otra hora'}${wasHour ? ' en vez de las ' + wasHour : ''}`);
    // Раунды плана 1:1 (доска «1:1 · Offline — new layout», OF.20c / OF.C3d; сервер 06.10.2026).
    case 'plan_fixed':
      return mine
        ? T(`Ты закрепил(а) финальную версию${when ? ' — ' + when : ''}`, `You fixed the final version${when ? ' — ' + when : ''}`, `Fijaste la versión final${when ? ' — ' + when : ''}`)
        : T(`${by} закрепил(а) план${when ? ' — ' + when : ''}. Останься или выйди — без последствий.`,
            `${by} fixed the plan${when ? ' — ' + when : ''}. Stay in or leave — nothing is held against you.`,
            `${by} fijó el plan${when ? ' — ' + when : ''}. Quédate o sal: sin consecuencias.`);
    case 'plan_left':
      return mine ? T('Ты вышел(ла) из плана', 'You left the plan', 'Saliste del plan')
                  : T(`${by} вышел(ла) из плана — без последствий`, `${by} left the plan — nothing held against anyone`, `${by} salió del plan, sin consecuencias`);
    // Молчание до подтверждения закрывает план без последствий (правило владельца 06.10.2026).
    case 'plan_expired':
      return mine
        ? T('Ты не ответил(а) за 6 ч — план закрыт. Никаких последствий.', 'You didn’t answer in 6h — the plan is closed. Nothing is held against you.', 'No respondiste en 6 h: el plan se cerró. Sin consecuencias.')
        : T(`${by || 'Собеседник'} не ответил(а) за 6 ч — план закрыт. Никаких последствий.`,
            `${by || 'They'} didn’t answer in 6h — the plan is closed. Nothing is held against anyone.`,
            `${by || 'La otra persona'} no respondió en 6 h: el plan se cerró. Sin consecuencias.`);
    case 'plan_change_expired':
      return T(`Ответа на новое время не было за 6 ч — остаётся ${wasHour || 'прежнее время'}`,
               `No answer to the new time in 6h — ${wasHour || 'the original time'} stays`,
               `Sin respuesta a la nueva hora en 6 h — se queda ${wasHour || 'la hora original'}`);
    case 'plan_change_ok':
      return T(`Новое время принято${when ? ' — ' + when : ''}`, `The new time is agreed${when ? ' — ' + when : ''}`, `La nueva hora está acordada${when ? ' — ' + when : ''}`);
    case 'plan_change_no':
      return mine ? T('Ты оставил(а) прежнее время', 'You kept the original time', 'Tú mantuviste la hora original')
                  : T(`${by} оставил(а) прежнее время`, `${by} kept the original time`, `${by} mantuvo la hora original`);
    case 'plan_change_pulled':
      return mine ? T('Ты забрал(а) предложение о переносе', 'You took back the time change', 'Has revertido el cambio de hora')
                  : T(`${by} забрал(а) предложение о переносе`, `${by} took back the time change`, `${by} revocó el cambio de hora`);
    case 'plan_cancelled':
      return mine ? T('Ты отменил(а) встречу', 'You called the meetup off', 'Has cancelado la quedada')
                  : T(`${by} отменил(а) встречу`, `${by} called the meetup off`, `${by} canceló la quedada`);
    /*
     * ТРИ СОБЫТИЯ, КОТОРЫЕ СЕРВЕР СЛАЛ В ПУСТОТУ. `sysLine` отдаёт пустую строку на незнакомый
     * код, а пустая строка в ленте не рисуется ничем — то есть событие уходило и исчезало.
     * Каждое из трёх обещано в коде сервера словами «второму говорят СРАЗУ и в ленту».
     */
    case 'plan_ask':
      // Просьба передать выбор — теперь событие плана, а не реплика: оба читают её на своём языке.
      if (sys.kind === 'link') {
        return mine ? T(`Ты попросил(а) ${by} создать ссылку на звонок`, `You asked ${by} to host the call`, `Pediste a ${by} que cree el enlace`)
                    : T(`${by} просит тебя создать ссылку на звонок`, `${by} asks you to host the call`, `${by} te pide que crees el enlace de la llamada`);
      }
      return mine ? T(`Ты попросил(а) ${by} выбрать место`, `You asked ${by} to pick the place`, `Pediste a ${by} que elija el lugar`)
                  : T(`${by} просит тебя выбрать место`, `${by} asks you to pick the place`, `${by} te pide que elijas el lugar`);
    // Просьбу сняли: попросивший забрал её или попрошенный отказался (O.C3e «I can’t host»).
    case 'plan_ask_pulled':
      if (sys.kind === 'link') {
        return mine ? T('Ты забрал(а) просьбу провести звонок', 'You took back the ask to host', 'Retiraste la petición de organizar')
                    : T(`${by} забрал(а) просьбу провести звонок`, `${by} took back the ask to host`, `${by} retiró la petición de organizar`);
      }
      return mine ? T('Ты забрал(а) просьбу выбрать место', 'You took back the ask to pick the place', 'Retiraste la petición de elegir el lugar')
                  : T(`${by} забрал(а) просьбу выбрать место`, `${by} took back the ask to pick the place`, `${by} retiró la petición de elegir el lugar`);
    case 'plan_ask_declined':
      if (sys.kind === 'link') {
        return mine ? T('Ты не сможешь провести звонок', 'You can’t host the call', 'No puedes organizar la llamada')
                    : T(`${by} не сможет провести звонок`, `${by} can’t host the call`, `${by} no puede organizar la llamada`);
      }
      return mine ? T('Ты не сможешь выбрать место', 'You can’t pick the place', 'No puedes elegir el lugar')
                  : T(`${by} не сможет выбрать место`, `${by} can’t pick the place`, `${by} no puede elegir el lugar`);
    case 'plan_cant_make_it':
      // Внутри двухчасовой заморозки «не смогу» встречу НЕ отменяет (спека OF): она остаётся,
      // и второй должен понять именно это, иначе прочитает как отмену и никуда не пойдёт.
      return mine
        ? T('Ты предупредил(а), что не придёшь. Встреча не отменена', 'You said you cannot make it. The meetup still stands', 'Dijiste que no podrías ir. La quedada sigue adelante')
        : T(`${by} не сможет прийти. Встреча не отменена — решай сам(а)`,
            `${by} cannot make it. The meetup still stands — it is your call`, `${by} no puede venir. La quedada sigue en pie — es tu decisión`);
    /*
     * СТАТУС ПЕРЕД ВСТРЕЧЕЙ. Он лежал только в плане, и второй узнавал о нём, лишь если сам
     * открывал экран плана. В переписку не приходило ничего — сообщено владельцем с телефона:
     * «говорю, что я на месте… часть сообщений не приходит вообще».
     *
     * «Не смогу» здесь тот же код, что и `plan_cant_make_it` у ответа на план: человеку всё равно,
     * какой кнопкой это сказано, а встреча в обоих случаях остаётся в силе — решать второму.
     */
    case 'plan_status': {
      const eta = Number(sys.eta) > 0 ? Number(sys.eta) : 0;
      const inMin = eta ? T(`, будет через ${eta} мин`, `, ${eta} min away`, `, llega en ${eta} min`) : '';
      switch (String(sys.status || '')) {
        case 'here':
          return mine ? T('Ты на месте', 'You are there', 'Ya estás allí')
                      : T(`${by} на месте`, `${by} is there`, `${by} ya está allí`);
        case 'otw':
          return mine ? T(`Ты в пути${inMin}`, `You are on your way${inMin}`, `Vas de camino${inMin}`)
                      : T(`${by} в пути${inMin}`, `${by} is on the way${inMin}`, `${by} va de camino${inMin}`);
        case 'late':
          return mine ? T(`Ты предупредил(а), что опаздываешь${inMin}`, `You said you are running late${inMin}`, `Avisaste de que llegas tarde${inMin}`)
                      : T(`${by} опаздывает${inMin}`, `${by} is running late${inMin}`, `${by} llega tarde${inMin}`);
        case 'cant_make_it':
          return mine
            ? T('Ты предупредил(а), что не придёшь. Встреча не отменена', 'You said you cannot make it. The meetup still stands', 'Dijiste que no podrías ir. La quedada sigue adelante')
            : T(`${by} не сможет прийти. Встреча не отменена — решай сам(а)`,
                `${by} cannot make it. The meetup still stands — it is your call`,
                `${by} no puede venir. La quedada sigue en pie — es tu decisión`);
        default:
          return '';
      }
    }
    case 'moved_to_call':
      return T('Встреча переехала в звонок', 'The meetup moved to a call', 'La quedada pasó a una llamada');
    case 'plan_side':
      return sys.side === 'call'
        ? (mine ? T('Ты придёшь звонком', 'You are joining by call', 'Te unirás por llamada')
                : T(`${by} придёт звонком`, `${by} is joining by call`, `${by} se une por llamada`))
        : (mine ? T('Ты придёшь лично', 'You are coming in person', 'Vendrás en persona')
                : T(`${by} придёт лично`, `${by} is coming in person`, `${by} viene en persona`));
    default:
      return '';
  }
}
export type Req = {
  id?: string;
  from?: string;
  to?: string;
  status?: ReqStatus;
  photo?: string;
  intent?: any;
  updated?: number;
};

// byPerson жил здесь и раскладывал outbox по именам для карточек выдачи. Теперь это делает общий
// стор приглашений (src/invites.ts) — он же владеет отправкой, отзывом и потолком, потому что
// «Пригласить» есть на двух экранах и состояние у них обязано быть одно.

/**
 * С кем переписка ИДЁТ на самом деле — по последним сообщениям, а не по принятым приглашениям.
 *
 * Считать активным чатом любое принятое приглашение было ошибкой: принять — это ещё не начать
 * разговаривать, и человек с двумя принятыми не мог открыть НИ ОДИН чат — каждый просил закончить
 * другой. Разговор существует тогда, когда в нём есть сообщения; это и есть тот самый «один чат»
 * бесплатного тарифа.
 *
 * Пусто — не переписывается ни с кем, любой чат открывается свободно.
 */
export function activeChatWith(
  threads: { who?: string; t?: number; sys?: { code?: string } }[],
): string {
  /**
   * ЗАКРЫТЫЙ РАЗГОВОР СЛОТ НЕ ЗАНИМАЕТ.
   *
   * Кадр O.17 обещает прямо: «End your current chat to start one with another match». Завершение
   * до сервера доходило — он пишет в ленту пары системную строку `chat_ended`, — но здесь она не
   * читалась, и слот считался занятым по САМОМУ СВЕЖЕМУ треду. А свежайшим после завершения
   * становилась ровно эта строка.
   *
   * Итог: человек закрывал переписку и не мог открыть НИ ОДНУ другую — окно «Ты уже переписываешься
   * с Jane» висело на всех карточках, и выхода из него не было вовсе. Продукт кончался после
   * первого же разговора.
   *
   * Признак — последнее сообщение пары. Если после «разговор закрыт» кто-то написал снова, тред
   * снова живой: закрыть и передумать — обычное дело, и запрещать это нечем.
   */
  const live = (threads || []).filter(
    (t) => String(t.who || '').trim() && t.sys?.code !== 'chat_ended',
  );
  live.sort((a, b) => (b.t || 0) - (a.t || 0));
  return String(live[0]?.who || '');
}

/** Время сообщения — часы и минуты, как на кадре. */
export function msgTime(t?: number, ru = true): string {
  if (typeof t !== 'number' || !isFinite(t) || !t) return '';
  return new Date(t * 1000).toLocaleTimeString(dateLocale(ru), {
    hour: '2-digit', minute: '2-digit', hour12: use12h(ru),
  });
}

/** Разделитель дня в ленте (MSG.06 «Today»): Сегодня / Вчера / короткая дата. */
export function msgDayLabel(t: number, ru = true, nowMs = Date.now()): string {
  const d = new Date(t * 1000);
  const now = new Date(nowMs);
  const yest = new Date(nowMs - 86400000);
  if (d.toDateString() === now.toDateString()) return T('Сегодня', 'Today', 'Hoy');
  if (d.toDateString() === yest.toDateString()) return T('Вчера', 'Yesterday', 'Ayer');
  return d.toLocaleDateString(dateLocale(ru), { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Строка «Сегодня · 20:00 Barcelona» из плана. Часовых поясов у обоих сервер не хранит. */
export function planWhen(p: any, ru = true): string {
  return atLabel(p?.starts_at, ru) || String(p?.when || '');
}

/**
 * Подпись статуса участника плана — словами, а не кодом состояния.
 *
 * Подтверждение важнее авторства. Своя строка сначала говорила «это предложил(а) ты» и умалчивала
 * о том, что предложивший УЖЕ подтверждён — на сервере предложить и значит согласиться. Рядом со
 * строкой собеседника «Подтвердил(а)» это читалось так, будто согласился только он.
 */
export function personStatus(p: any): string {
  const s = String(p?.status || 'pending');
  if (s === 'decline') return CHAT.declinedPlan();
  // «Твой план» — про авторство, а не про то, чей это экран: план предлагает хост. Пока is_me
  // подменяло роль, ГОСТЬ после подтверждения чужого плана читал у себя «твой план».
  const meHost = !!p?.is_me && String(p?.role || '') === 'host';
  if (s === 'confirm' || s === 'confirmed' || p?.confirmed) {
    return meHost ? `${CHAT.confirmed()} · ${CHAT.youProposedShort()}` : CHAT.confirmed();
  }
  return meHost ? CHAT.youProposed() : CHAT.notAnswered();
}
