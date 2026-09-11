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

/** Статус заявки: как его называет сервер (см. §14.1). */
export type ReqStatus = 'pending' | 'accepted' | 'declined' | 'withdrawn' | 'expired';

export const CHAT = {
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
};

/**
 * Тред — кадры MSG.06–MSG.11 и карточки приглашений MSG.18–MSG.21.
 * Подзаголовок шапки, закреплённый план, записка «отправлено как предложение», подсказка Kleal
 * и лист интента. Всё считается из настоящих данных; чего у сервера нет (присутствие «online
 * now», календарь занятости) — здесь и не обещается.
 */
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
  if (minsToStart <= LINK_LEAD_MIN) return 'soon';
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
export function sysLine(sys: SysMsg | undefined, me: string, ru: boolean): string {
  if (!sys?.code) return '';
  const by = String(sys.by || '').trim();
  const mine = !!by && by.toLowerCase() === String(me || '').trim().toLowerCase();
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
    case 'plan_proposed':
      return mine
        ? T(`Ты предложил(а) встречу${when ? ' — ' + when : ''}`, `You proposed a meetup${when ? ' — ' + when : ''}`, `Propusiste una quedada${when ? ' — ' + when : ''}`)
        : T(`${by} предложил(а) встречу${when ? ' — ' + when : ''}`, `${by} proposed a meetup${when ? ' — ' + when : ''}`, `${by} propuso una quedada${when ? ' — ' + when : ''}`);
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
    case 'plan_cant_make_it':
      // Внутри двухчасовой заморозки «не смогу» встречу НЕ отменяет (спека OF): она остаётся,
      // и второй должен понять именно это, иначе прочитает как отмену и никуда не пойдёт.
      return mine
        ? T('Ты предупредил(а), что не придёшь. Встреча не отменена', 'You said you cannot make it. The meetup still stands', 'Dijiste que no podrías ir. La quedada sigue adelante')
        : T(`${by} не сможет прийти. Встреча не отменена — решай сам(а)`,
            `${by} cannot make it. The meetup still stands — it is your call`, `${by} no puede venir. La quedada sigue en pie — es tu decisión`);
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
