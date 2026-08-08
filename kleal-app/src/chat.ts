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
import { T } from './i18n';
import { acc, dat, gen, ins } from './names';

/** Статус заявки: как его называет сервер (см. §14.1). */
export type ReqStatus = 'pending' | 'accepted' | 'declined' | 'withdrawn' | 'expired';

export const CHAT = {
  /** O.16 — приглашение отклонили. */
  declined: () => T('Отклонено', 'Declined'),
  remove: () => T('Убрать', 'Remove'),

  /** O.17 — приглашение приняли. */
  openChat: () => T('Открыть чат', 'Open chat'),
  continueChat: () => T('Продолжить чат', 'Continue chat'),

  /** Окно бесплатного тарифа, текст с кадра O.17. */
  busyTitle: (name: string) => T(`Ты уже переписываешься с ${ins(name)}`, `You're already chatting with ${name}`),
  busyBody: () =>
    T(
      'На бесплатном тарифе можно вести переписку только с одним мэтчем за раз. Закончи текущую, чтобы начать с другим, или подключи Kleal Plus — тогда доступны все три.',
      'On the Free plan, you can chat with only one match at a time. End your current chat to start one with another match, or upgrade to Kleal Plus to chat with all three.'
    ),
  getPlus: () => T('Подключить Kleal Plus', 'Get Kleal Plus'),
  plusPrice: () => T('€6,99 в месяц · переписка со всеми · отмена в любой момент',
                     '€6.99 / month · Chat with all matches · Cancel any time'),
  endChatWith: (name: string) => T(`Закончить переписку с ${ins(name)}`, `End chat with ${name}`),

  /** O.18 — сам чат. */
  placeholder: () => T('Сообщение…', 'Message…'),
  /** Композер MSG.06 обращается по имени: «Message Jane». */
  placeholderTo: (name: string) => T(`Написать ${dat(name)}…`, `Message ${name}`),
  /**
   * Пустая переписка. Ролей ДВЕ, и текст обязан их различать: раньше обеим сторонам показывалось
   * «X принял(а) приглашение», и человек, который сам только что нажал «Присоединиться», читал,
   * что приглашение принял собеседник. Кто кого позвал — знает экран, а не эта строка.
   */
  empty: (name: string, theyAccepted: boolean) =>
    theyAccepted
      ? T(`${name} принял(а) приглашение. Напиши первым — это ваш общий разговор про интент.`,
          `${name} accepted your invite. Say hello — this chat belongs to your intent.`)
      : T(`Ты принял(а) приглашение от ${gen(name)}. Напиши первым — это ваш общий разговор про интент.`,
          `You accepted ${name}’s invite. Say hello — this chat belongs to your intent.`),
  offline: () => T('Сообщение не ушло. Проверь связь.', 'The message didn’t send. Check your connection.'),

  /** O.19 — лист действий. */
  actionsTitle: () => T('Действия с разговором', 'Conversation Actions'),
  createPlan: () => T('Создать план', 'Create Plan'),
  endConversation: () => T('Закончить разговор', 'End Conversation'),
  viewIntent: () => T('Открыть интент', 'View intent'),
  keepChatting: () => T('Продолжить разговор', 'Keep Chatting'),
  endAsk: (name: string) =>
    T(`Закончить разговор с ${ins(name)}? Переписка закроется, а место освободится для другого мэтча.`,
      `End the chat with ${name}? The conversation closes and frees the slot for another match.`),

  /** O.20 — план отправлен. */
  sentTo: (name: string) => T(`Отправлено: ${name}`, `Sent to ${name}`),
  /** У звонка нет «места» — обещать его в записке к онлайн-плану было просто неправдой. */
  sentNote: (name: string) =>
    T(
      `${name} видит время и то, что это звонок. Пока не подтвердит — ничего не забронировано ни у кого из вас.`,
      `${name} sees the time and that it is a call. Until they confirm, nothing is booked for either of you.`
    ),
  notAnswered: () => T('Ещё не ответил(а)', 'Hasn’t answered yet'),
  youProposed: () => T('Это предложил(а) ты', 'You proposed this'),
  youProposedShort: () => T('твой план', 'your plan'),
  confirmed: () => T('Подтвердил(а)', 'Confirmed'),
  declinedPlan: () => T('Отказался(ась)', 'Declined'),
  changePlan: () => T('Поправить план', 'Change the plan'),
  videoCall: () => T('Видеозвонок · ссылка сохранена', 'Video call · link saved'),
  planFailed: () => T('План не отправился. Попробуй ещё раз.', 'The plan didn’t send. Try again.'),
  /** Сервер отказывает, если человек ещё не принял приглашение, — говорим об этом словами. */
  notMatched: () => T('План можно отправить только тому, кто принял приглашение.',
                      'A plan can only go to someone who accepted your invite.'),
  inThePast: () => T('Это время уже прошло. Выбери другое.', 'That time has already passed. Pick another.'),
  /** У пары может быть только одна живая встреча — сервер не даст завести вторую. */
  planExists: () => T('С этим человеком уже есть встреча. Поправь её, а не заводи вторую.',
                      'You already have a meetup with this person. Change that one instead.'),
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
  confirmed: () => T('Подтверждено', 'Confirmed'),

  /** O.20 — шапка формы. Режим приходит из интента, и форма его НАЗЫВАЕТ, а не намекает полями. */
  formMode: (mode: 'offline' | 'online' | 'hybrid', name: string) =>
    mode === 'online'
      ? T(`Звонок с ${ins(name)} — по интенту вы договорились встретиться онлайн`,
          `A call with ${name} — your intent was to meet online`)
      : mode === 'hybrid'
        ? T(`Встреча с ${ins(name)} — по интенту можно и онлайн, и вживую`,
            `Meeting ${name} — your intent allows both online and in person`)
        : T(`Встреча с ${ins(name)} вживую — по интенту вы договорились увидеться`,
            `Meeting ${name} in person — your intent was to meet up`),
  /** Ссылку можно донести потом, но второй до этого видит «ссылка будет» — об этом честно сразу. */
  linkLaterNote: (name: string) =>
    T(`Можно оставить пустым и прислать позже — до этого ${name} видит «ссылка будет».`,
      `You can leave this empty and add it later — until then ${name} sees “link coming”.`),
  /** Что случится по «Создать план». Кнопка отправляет предложение, а не бронирует вечер. */
  formSendNote: (name: string) =>
    T(`${name} получит это предложением и подтвердит со своей стороны. Пока не подтвердит — ничего не назначено.`,
      `${name} gets this as a proposal and confirms on their side. Nothing is booked until they do.`),
  /**
   * На кадре здесь названы обе стороны и оба часовых пояса. Пояс собеседника мы не храним — ни в
   * профиле, ни в плане, — поэтому время показывается ОДНО, своё, и подписано своим поясом.
   * Выдумывать «19:00 в Лондоне» для человека, чей пояс никто не спрашивал, нельзя.
   */
  linkOpensAt: (hhmmStr: string) =>
    T(`Ссылка откроется в ${hhmmStr}, не раньше.`, `The link opens at ${hhmmStr}, not now.`),
  linkSaved: () => T('Видеозвонок · ссылка сохранена', 'Video call · link saved'),
  linkOpensLabel: (hhmmStr: string) =>
    T(`Видеозвонок · ссылка откроется в ${hhmmStr}`, `Video call · link opens ${hhmmStr}`),
  /** Формат без обещаний про ссылку — для встречи, которая уже позади или отменена. */
  modeOnline: () => T('Видеозвонок', 'Video call'),

  /** Всё согласовано и место известно — конец переговоров, сказанный вслух. */
  allSetTitle: () => T('Всё готово', 'You’re all set'),
  allSetNote: (when: string, offline: boolean, name: string, place: string) =>
    offline
      ? T(
          `${when}${place ? `, ${place}` : ''}. Адрес есть у вас обоих — договариваться больше не о чем.`,
          `${when}${place ? `, ${place}` : ''}. You both have the address — nothing left to agree.`
        )
      : T(
          `${when}. Ссылка сохранена и откроется за 10 минут до начала — ${name} тоже её увидит.`,
          `${when}. The link is saved and opens 10 minutes before — ${name} sees it too.`
        ),

  startsIn: (min: number) => T(`Начало через ${min} мин`, `Starts in ${min} minutes`),
  startsNow: () => T('Время звонка', 'Your call is now'),
  linkOpenNow: () => T('Ссылка открыта', 'Your link is now open'),
  linkNote: () =>
    T(
      'Звонок проходит по этой ссылке — Kleal хранит только её и время.',
      'The call happens on this link — Kleal only keeps the link and the time.'
    ),
  openLink: () => T('Открыть ссылку', 'Open link'),
  leavesKleal: () => T('Откроется вне Kleal', 'Opens outside Kleal'),
  outsideNote: () =>
    T(
      'Звонок идёт вне Kleal. Мы его не видим и ничего о нём не записываем. Потом спросим у обоих, состоялся ли он.',
      'The call happens outside Kleal. We can’t see it and nothing about it is recorded here. Afterwards we’ll ask you both whether it happened.'
    ),
  messageThem: (name: string) => T(`Написать ${dat(name)}`, `Message ${name}`),
  cantMakeIt: () => T('Не смогу', 'I can’t make it'),
  suggestAnother: () => T('Предложить другое время', 'Suggest another time'),

  /**
   * Отмена встречи заранее. Её не было вовсе: отказаться можно было только за десять минут до
   * начала, а до того ни автор плана, ни приглашённый не имели способа сказать «не смогу».
   */
  callOff: () => T('Отменить встречу', 'Call the meetup off'),
  callOffAsk: (name: string) => T(`Отменить встречу с ${ins(name)}?`, `Call off the meetup with ${name}?`),
  callOffNote: (name: string) =>
    T(
      `${name} сразу увидит отмену. Вернуть эту встречу нельзя — можно назначить новую, чат остаётся открытым.`,
      `${name} sees it straight away. This meetup can’t be restored — you can set a new one, and your chat stays open.`
    ),
  callOffYes: () => T('Да, отменить', 'Yes, call it off'),
  callOffNo: () => T('Оставить как есть', 'Leave it as it is'),

  /** O.24. Формулировка с кадра: спрашивают обоих, и до ответа обоих никому ничего не засчитывают. */
  didItHappen: () => T('Встреча состоялась?', 'Did it happen?'),
  didItNote: (name: string) =>
    T(
      `Kleal не видит, что происходит вне приложения, поэтому спрашивает. ${name} получит тот же вопрос. Пока не ответите оба, никому ничего не засчитывается.`,
      `Kleal can’t see outside the app, so we have to ask. ${name} gets the same question. Nothing is recorded against anyone until you both answer.`
    ),
  yesWeTalked: () => T('Да, встретились', 'Yes, we talked'),
  noItDidnt: () => T('Нет, не состоялась', 'No, it didn’t happen'),
  waitingBoth: () => T('Ждём ответа обоих', 'Waiting on both answers'),
  youAnswered: () => T('Ты ответил(а)', 'You answered'),
  theyNotAnswered: (name: string) => T(`${name} ещё не ответил(а)`, `${name} hasn’t answered yet`),

  /** O.25. */
  howWasIt: () => T('Как прошло?', 'How was it?'),
  optional: () =>
    T(
      'Необязательно — это помогает агенту подбирать лучше в следующий раз.',
      'Optional — it helps your agent find better matches next time.'
    ),
  great: () => T('Отлично', 'Great'),
  fine: () => T('Нормально', 'Fine'),
  notGreat: () => T('Так себе', 'Not great'),
  send: () => T('Отправить', 'Send'),
  reportProblem: () => T('Сообщить о проблеме', 'Report a problem'),
  thanks: () => T('Спасибо — это поможет подбирать точнее.', 'Thank you — this helps us match you better.'),

  /** O.20a — согласованный онлайн-план без ссылки. Времена на кадре — примеры борда; пояс
   *  собеседника мы не храним (см. linkOpensAt), поэтому время здесь одно, своё. */
  addLinkTitle: () => T('Добавь ссылку на звонок', 'Add the call link'),
  addLinkNote: (when: string, name: string) =>
    T(
      `Встреча (${when}) согласована. ${name} видит «ссылка будет», пока ты её не вставишь — добавь заранее, чтобы к началу никто не ждал.`,
      `${when} is agreed. ${name} sees “link coming” until you paste one — add it ahead of time so nobody is waiting on it.`
    ),
  noLinkYet: () => T('Онлайн · ссылки пока нет', 'Online · no link yet'),
  pasteLink: () => T('Вставь ссылку Zoom, Meet — любую', 'Paste a Zoom, Meet or any link'),
  saveLink: () => T('Сохранить ссылку', 'Save the link'),
  askHost: (name: string) => T(`Попросить ${acc(name)} создать звонок`, `Ask ${name} to host instead`),
  /** Уходит настоящим сообщением в чат — просьба должна дойти, а не остаться нажатой кнопкой. */
  askHostMsg: () =>
    T(
      'Создашь ссылку на звонок со своей стороны? У меня не выходит — пришли её сюда.',
      'Could you host the call and share the link here?'
    ),
  linkComing: () => T('Онлайн · ссылка будет', 'Online · link coming'),

  /** O.21b — новое время отправлено; старое действует, пока встречное не принято. */
  newTimeSent: (name: string) => T(`Новое время отправлено ${dat(name)}`, `New time sent to ${name}`),
  newTimeNote: (name: string) =>
    T(
      `${name} увидит новое время и подтвердит его заново. До этого действует старое — ничего не отменено, и никому ничего делать не нужно.`,
      `${name} sees the new time and confirms again. Until then the old time still stands — nothing is cancelled and nobody has to do anything.`
    ),
  newPrefix: (when: string) => T(`Новое: ${when}`, `New: ${when}`),
  notAnsweredNewTime: () => T('Ещё не ответил(а) на новое время', 'Hasn’t answered the new time'),
  waitingOldTime: () => T('Ждёшь · старое время в силе', 'Waiting · old time still stands'),
  takeItBack: () => T('Забрать предложение', 'Take it back'),
  /** Принимающая сторона встречного времени (OF.C5): кадра в пачке нет, кнопки — по контракту сервера. */
  newTimeToYou: (name: string) => T(`${name} предлагает другое время`, `${name} suggests a new time`),
  acceptNewTime: () => T('Принять новое время', 'Accept the new time'),
  keepOldTime: () => T('Оставить как было', 'Keep the old time'),
  /** OF.C5 дословно: спешки нет, отказ ничего не отменяет. */
  oldTimeHolds: () =>
    T(
      'Старое время в силе, пока ты не ответишь, — спешки нет, и отказ ничего не отменяет.',
      'The old time holds until you answer, so there is no rush and nothing is lost if you say no.'
    ),
  hostAskedNote: () => T('Просьба отправлена в чат', 'Asked in chat'),
  sendNewTime: () => T('Отправить новое время', 'Send the new time'),

  /** O.C3 — план прислали мне; подтверждение закрепляет время за обоими. */
  sentPlan: (name: string) => T(`${name} прислал(а) план`, `${name} sent a plan`),
  sentPlanNote: () =>
    T(
      'Подтверди — и время закреплено за вами обоими. Ссылка откроется за 10 минут, не сейчас.',
      'Confirm and it is set for both of you. The link opens 10 minutes before, not now.'
    ),
  confirmAction: () => T('Подтвердить', 'Confirm'),
  yourTurn: () => T('Твой ход', 'Your turn'),
  confirmedAt: (t: string) => T(`Подтвердил(а) · ${t}`, `Confirmed · ${t}`),

  /** O.C5 — встречное время пришло мне: заголовок называет час, кнопки — оба часа. */
  suggestsTime: (name: string, t: string) => T(`${name} предлагает ${t}`, `${name} suggests ${t}`),
  moveNote: (name: string) =>
    T(
      `${name} хочет перенести встречу. Старое время в силе, пока ты не ответишь, — спешки нет, и отказ ничего не отменяет.`,
      `${name} wants to move it. The old time holds until you answer, so there is no rush and nothing is lost if you say no.`
    ),
  suggestedNewTime: () => T('Предложил(а) новое время', 'Suggested the new time'),
  confirmTime: (t: string) => T(`Подтвердить ${t}`, `Confirm ${t}`),
  keepTime: (t: string) => T(`Оставить ${t}`, `Keep ${t}`),

  /** OF.20 — офлайн-план отправлен: район виден сразу, адрес — только после её «да». */
  sentNoteOffline: (name: string) =>
    T(
      `${name} видит район и время. Точный адрес откроется только после подтверждения.`,
      `${name} sees the district and the time. The exact address opens for them only when they confirm.`
    ),
  /** OF.21 — подтверждено, адрес открыт обоим. */
  addressOpenNote: (name: string) =>
    T(`У ${name} теперь есть точный адрес.`, `${name} has the exact address now.`),
  /** OF.C3, сторона без подтверждения: адрес придёт после «да». */
  addressAfterConfirm: () =>
    T('Адрес откроется после твоего подтверждения.', 'The address opens once you confirm.'),
  districtOnly: (d: string) => T(`${d} · адрес после подтверждения`, `${d} · address after you both confirm`),

  /** OF.20a — согласовано, а точного места нет: выбрать до начала. */
  pickPlaceTitle: () => T('Выбери точное место', 'Pick the exact place'),
  pickPlaceNote: (when: string, name: string) =>
    T(
      `Встреча (${when}) согласована. ${name} видит только район, пока ты не назовёшь место — выбери заранее, чтобы можно было спланировать дорогу.`,
      `${when} is agreed. ${name} only sees the district until you name a place — pick one ahead so they can plan the trip.`
    ),
  placePlaceholder: () => T('Кафе, бар или парк…', 'Search for a café, bar or park'),
  savePlace: () => T('Сохранить место', 'Save the place'),
  askChoose: (name: string) => T(`Пусть выберет ${name}`, `Ask ${name} to choose`),
  askChooseMsg: () =>
    T('Выберешь место со своей стороны? Кафе, бар или парк — что удобнее.', 'Could you pick the place? A café, bar or park — whatever works.'),
  noPlaceYet: () => T('Место пока не выбрано', 'No place yet'),

  /** OF.22 — скоро начало: маршрут и честное «я опаздываю». */
  startsInLong: (min: number) => T(`Начало через ${min} мин`, `Starts in ${min} minutes`),
  openRoute: () => T('Открыть маршрут', 'Open the route'),
  imLate: () => T('Я опаздываю', 'I’m running late'),
  onMyWay: () => T('Уже иду', 'On my way'),
  imHere: () => T('Я на месте', 'I’m here'),
  /** OF.22, подзаголовок: опоздание не страшно, если о нём сказать. */
  lateHint: (name: string) =>
    T(
      `Если опаздываешь — скажи ${name}: он(а) будет ждать у того же места.`,
      `If you’re running late, tell ${name} — they wait at the same place.`
    ),
  /** OF.22a, заголовок. */
  lateKnows: (name: string) => T(`${name} знает, что ты опаздываешь`, `${name} knows you’re late`),
  /** OF.C3, приёмная сторона офлайна: подтверждение открывает адрес — в обе стороны. */
  sentPlanNoteOffline: () =>
    T(
      'Подтверди — и точный адрес откроется тебе. До этого виден только район, и это работает в обе стороны.',
      'Confirm and the exact address opens for you. Until then you only see the district — that works both ways.'
    ),
  /** OF.22a — опоздание сказано; никто не сидит в неведении. */
  lateSentNote: (name: string) =>
    T(
      `${name} знает, что ты опаздываешь. Ты ничего не отменял(а) — встреча в силе, просто ${name} не ждёт в неведении.`,
      `${name} knows you’re late. You didn’t cancel anything — the meetup is still on, they just aren’t waiting in the dark.`
    ),
  /** OF.C4 — опаздывает СОБЕСЕДНИК. */
  theyLate: (name: string) => T(`${name} опаздывает`, `${name} is running late`),
  theyLateNote: (name: string) =>
    T(
      `${name} уже в пути. Ничего не отменено — займи столик, он(а) будет.`,
      `${name} is on the way. Nothing is cancelled — grab a table, they’ll be there.`
    ),
  cantWait: () => T('Не могу ждать', 'I can’t wait'),
  /** Живые статусы участников (OF.22/OF.22a/OF.23). */
  liveOtw: () => T('В пути', 'On the way'),
  liveLate: () => T('Опаздывает', 'Running late'),
  liveHere: () => T('На месте', 'At the place'),
  liveLateMine: () => T('Опаздываешь', 'Running late'),
  /** OF.23 — встреча сейчас, офлайн. */
  meetupNow: () => T('Встреча сейчас', 'Your meetup is now'),
  meetupBlindNote: () =>
    T(
      'Kleal не видит встречу. Здесь ничего о ней не записывается. Потом мы спросим у обоих, состоялась ли она.',
      'Kleal can’t see the meetup. Nothing about it is recorded here. Afterwards we’ll ask you both whether it happened.'
    ),

  /** OF.21a — «предложить другое время» листом: быстрые часы и своё время. */
  suggestSheetTitle: () => T('Предложить другое время', 'Suggest another time'),
  insteadOf: (t: string) => T(`Вместо ${t}`, `Instead of ${t}`),
  orSetYour: () => T('или поставь своё', 'or set your time'),
  suggestSheetNote: (name: string) =>
    T(
      `${name} подтвердит заново. Текущее время держится, пока он(а) не ответит, — ничего не отменено.`,
      `${name} confirms again after this. The current time stays until they do — nothing is cancelled.`
    ),

  /** OF.24a — «не состоялась»: причина. Ответ другим не показывается. */
  whatHappened: () => T('Что случилось?', 'What happened?'),
  whatHappenedNote: () =>
    T(
      'Нужно, чтобы планы оставались честными. Твой ответ другим не показывается.',
      'Used to keep plans honest. Your answer is not shown to the others.'
    ),
  reasonNoShow: (name: string) => T(`${name} не пришёл(шла)`, `${name} didn’t show up`),
  reasonCouldnt: () => T('Не смог(ла) я', 'I couldn’t make it'),
  reasonClosed: () => T('Место было закрыто', 'The place was closed'),
  reasonMoved: () => T('Договорились перенести', 'We agreed to move it'),
  reasonOther: () => T('Другое', 'Something else'),
  skip: () => T('Пропустить', 'Skip'),

  /** OF.C4 — отменили офлайн-встречу: ждать за столиком, а не в звонке. */
  toldYouNoteOffline: (name: string) =>
    T(
      `${name} предупредил(а), а не оставил(а) тебя ждать за столиком. Никому ничего не засчитано — чат открыт, и новое время может предложить любой из вас.`,
      `${name} told you rather than leaving you at the table. Nothing is held against you — your chat stays open and either of you can suggest a new time.`
    ),
  /** OF.23a — своя отмена офлайна. */
  nobodyWaitingOffline: (name: string) =>
    T(
      `Никто не ждёт зря. ${name} уже видит отмену и не сидит за столиком в одиночку. Чат открыт — договориться о новом времени можно там.`,
      `Nobody is left waiting. ${name} sees it now, so they aren’t sitting at a table alone. Your chat stays open — you can agree a new time there.`
    ),

  /** O.C4 — отменили мне; никто ничего не должен. */
  toldYouNote: (name: string) =>
    T(
      `${name} предупредил(а), а не оставил(а) тебя в звонке в одиночестве. Никому ничего не засчитано — чат открыт, и новое время может предложить любой из вас.`,
      `${name} told you rather than leaving you on the call alone. Nothing is held against you — your chat stays open and either of you can suggest a new time.`
    ),
  nothingToAnswer: () => T('Отвечать нечего', 'Nothing to answer'),
  calledOff: () => T('Видеозвонок · отменён', 'Video call · called off'),

  /** O.23a — создатель отменил встречу. */
  youToldCantMake: (name: string) =>
    T(`Ты сказал(а) ${dat(name)}, что не сможешь`, `You told ${name} you can’t make it`),
  theyCantMake: (name: string) => T(`${name} не сможет прийти`, `${name} can’t make it`),
  calledOffByYou: () => T('Отменено тобой', 'Called off by you'),
  calledOffBy: (name: string) => T(`Отменил(а) ${name}`, `Called off by ${name}`),
  anotherTime: () => T('Другое время', 'Another time'),
  cantMakeStatus: () => T('Не сможет прийти', 'Can’t make it'),
  toldJustNow: () => T('Узнал(а) только что', 'Told just now'),
  nobodyWaiting: (name: string) =>
    T(
      `Никто не ждёт зря. ${name} уже видит отмену и не сидит в звонке в одиночку. Чат открыт — договориться о новом времени можно там.`,
      `Nobody is left waiting. ${name} sees it now, so they aren’t sitting on a call alone. Your chat stays open — you can agree a new time there.`
    ),
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
      ? { label: T('Новое время отправлено — ждём ответа', 'New time sent — waiting for an answer'), warn: false }
      : { label: T('Предложено другое время — твой ход', 'Another time suggested — your turn'), warn: true };
  }
  if (plan?.state === 'confirmed') {
    // Согласовано, но идти некуда: у звонка нет ссылки, у встречи — места.
    if (!plan?.address_set) {
      return plan?.mode === 'online'
        ? { label: T('Подтверждено · ссылки пока нет', 'Confirmed · no link yet'), warn: true }
        : { label: T('Подтверждено · место пока не выбрано', 'Confirmed · no place yet'), warn: true };
    }
    return { label: T('Подтверждено обоими', 'Confirmed by both'), warn: false };
  }
  if (!iConfirmed) return { label: T('Ждёт твоего подтверждения', 'Waiting for you to confirm'), warn: true };
  return { label: T('Отправлено · ждём ответа', 'Sent · waiting for an answer'), warn: false };
}

/** O.19a/O.19b — полоса отсчёта внизу чата: действие случится через 4 секунды, если не отменить. */
export const UNDO_BAR = {
  creating: (name: string) => T(`Создаю план с ${ins(name)}`, `Creating the plan with ${name}`),
  ending: () => T('Завершаю чат. Можно вернуться снова', 'Ending chat. You can pick again'),
  undo: (n: number) => T(`Отменить · ${n}`, `Undo · ${n}`),
};

/**
 * Тред — кадры MSG.06–MSG.11 и карточки приглашений MSG.18–MSG.21.
 * Подзаголовок шапки, закреплённый план, записка «отправлено как предложение», подсказка Kleal
 * и лист интента. Всё считается из настоящих данных; чего у сервера нет (присутствие «online
 * now», календарь занятости) — здесь и не обещается.
 */
export const THREAD = {
  planSet: (when: string) => T(`План: ${when}`, `Plan set · ${when}`),
  proposalSent: () => T('Предложение отправлено · ждём', 'Proposal sent · waiting'),
  planFromThem: () => T('Тебе прислали план', 'They sent you a plan'),
  talkingSince: (day: string) => T(`Общаетесь с ${day}`, `Talking since ${day}`),
  /** Разговор начался сегодня — «с субботы» про сегодняшний день читается как «давно». */
  talkingToday: () => T('Общаетесь сегодня', 'Talking since today'),
  /** «с четверга», а не «с четверг»: подзаголовку нужен родительный падеж. */
  weekdayGen: (dayIndex: number) =>
    ['воскресенья', 'понедельника', 'вторника', 'среды', 'четверга', 'пятницы', 'субботы'][dayIndex] || '',
  matchedOn: (title: string) => T(`Мэтч по «${title}»`, `Matched on “${title}”`),

  /** MSG.09 — под предложением, дословно: ничего не забронировано до «да». */
  sentAsProposal: (name: string) => T(`Отправлено ${name} как предложение`, `Sent to ${name} as a proposal`),
  nothingBooked: (name: string) =>
    T(`Ничего не забронировано, пока ${name} не скажет «да».`, `Nothing is booked until ${name} says yes.`),

  /** MSG.08 — подсказка Kleal. Счёт сообщений настоящий; свободные часы не обещаем: календарей
   *  у Kleal нет, и «в четверг свободно у обоих» было бы выдумкой. */
  nudge: (n: number, name: string) =>
    T(
      `Вы обменялись ${n} сообщениями, а время так и не назначено. Хочешь, предложу ${name} встретиться?`,
      `You two have swapped ${n} messages and no time. Want me to put a plan to ${name}?`
    ),
  nudgeYes: () => T('Да, предложи', 'Yes, propose it'),
  nudgeOther: () => T('Другой день', 'Another day'),
  nudgeNot: () => T('Пока нет', 'Not yet'),

  /** MSG.10 — лист интента. */
  intentMode: () => T('Режим', 'Mode'),
  intentWhen: () => T('Когда', 'When'),
  intentWhere: () => T('Где', 'Where'),
  intentWho: () => T('Кто', 'Who'),
  intentStatus: () => T('Статус', 'Status'),
  offlineInPerson: () => T('Оффлайн · вживую', 'Offline · in person'),
  onlineMode: () => T('Онлайн', 'Online'),
  whereAfterConfirm: () => T('Точное место — после подтверждения обоих', 'Exact place after you both confirm'),
  whereLink: () => T('Ссылка — после подтверждения', 'Link after you confirm'),
  matchedAgo: (name: string, days: number) =>
    days <= 0
      ? T(`Мэтч с ${ins(name)} · сегодня`, `Matched with ${name} · today`)
      : T(`Мэтч с ${ins(name)} · ${days} дн. назад`, `Matched with ${name} · ${days} days ago`),
  statusWaiting: () => T('Ждёт ответа', 'Waiting for an answer'),

  /** MSG.18–MSG.21 — приглашение как карточка в треде. */
  hoursToAnswer: (h: number) => T(`осталось ${h} ч на ответ`, `${h} h left to answer`),
  reviewInvite: () => T('Открыть приглашение', 'Review invite'),
  youDeclined: () => T('Ты отказал(ся/ась)', 'You declined'),
  declinedClear: (name: string) =>
    T(`${name} видит ясное «нет», а не «может быть».`, `${name} sees a clear no, not a maybe.`),
  inviteExpired: () => T('Истекло · без ответа', 'Expired · no reply'),
  /** Часы — настоящие, из самой заявки (created→expires_at): сервер держит место 72 часа,
   *  а не 24 с борда. */
  expiredNote: (h: number) =>
    T(
      `Приглашение держит место ${h} ч, чтобы никто не ждал в неведении.`,
      `Invites hold a seat for ${h} hours so nobody is blocked waiting.`
    ),
  dismiss: () => T('Скрыть', 'Dismiss'),
  joined: (title: string) => T(`Приглашение принято · ${title}`, `You joined · ${title}`),
};

/** O.C1 — входящее приглашение, сторона гостя. */
export const INVITE = {
  title: (name: string) => T(`${name} пригласил(а) тебя`, `${name} invited you`),
  note: (what: string, name: string) =>
    T(
      `${what ? what + '. ' : ''}Если присоединишься, откроется чат с ${ins(name)} — детали договорите там.`,
      `${what ? what + '. ' : ''}If you join, a chat with ${name} opens and you two agree the details there.`
    ),
  /** Ссылки в приглашении нет и не должно быть: она приходит позже, через план (OF.C3). */
  linkFrom: (name: string) => T(`Видеозвонок · ссылка у ${gen(name)}`, `Video call · link from ${name}`),
  inPerson: () => T('Встреча вживую', 'In person'),
  invitedYou: () => T('Пригласил(а) тебя', 'Invited you'),
  join: () => T('Присоединиться', 'Join'),
  notThisTime: () => T('Не в этот раз', 'Not this time'),
  declinedNote: () => T('Ты отказал(ась/ся). Приглашение закрыто.', 'You passed. The invite is closed.'),
  goneNote: () =>
    T('Приглашение больше не действует: истекло или уже решено.', 'This invite is no longer live: it expired or was already settled.'),
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
  return d.toLocaleTimeString(ru ? 'ru-RU' : 'en-US', { hour: '2-digit', minute: '2-digit', hour12: !ru });
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
  /** Время встречи в секундах — форматируется на языке читателя, не отправителя. */
  at?: number;
  was?: number;
  mode?: string;
  district?: string;
  kind?: string;
};

export type Msg = { id?: string; from?: string; to?: string; text?: string; t?: number; sys?: SysMsg };

/** «Пт, 8 авг · 20:00» из секунд. Пусто — времени нет, и выдумывать его нечем. */
function atLabel(at: any, ru: boolean): string {
  if (typeof at !== 'number' || !isFinite(at) || !at) return '';
  const d = new Date(at * 1000);
  const day = d.toLocaleDateString(ru ? 'ru-RU' : 'en-US', { weekday: 'short', day: 'numeric', month: 'short' });
  const hm = d.toLocaleTimeString(ru ? 'ru-RU' : 'en-US', { hour: '2-digit', minute: '2-digit', hour12: !ru });
  return `${day} · ${hm}`;
}

/** Час без даты — для переноса, где важен только сдвинутый час. */
function hourLabel(at: any, ru: boolean): string {
  if (typeof at !== 'number' || !isFinite(at) || !at) return '';
  return new Date(at * 1000).toLocaleTimeString(ru ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: !ru,
  });
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
  const hour = hourLabel(sys.at, ru);
  const wasHour = hourLabel(sys.was, ru);
  switch (sys.code) {
    case 'plan_proposed':
      return mine
        ? T(`Ты предложил(а) встречу${when ? ' — ' + when : ''}`, `You proposed a meetup${when ? ' — ' + when : ''}`)
        : T(`${by} предложил(а) встречу${when ? ' — ' + when : ''}`, `${by} proposed a meetup${when ? ' — ' + when : ''}`);
    // Та самая строка, которой не хватало: она приходит обоим и означает, что торг закончен.
    case 'plan_confirmed':
      return T(`План подтверждён${when ? ' — ' + when : ''}. Время закреплено за вами обоими.`,
               `The plan is confirmed${when ? ' — ' + when : ''}. The time is set for both of you.`);
    case 'plan_place':
      if (sys.kind === 'link') {
        return mine ? T('Ты добавил(а) ссылку на звонок', 'You added the call link')
                    : T(`${by} добавил(а) ссылку на звонок`, `${by} added the call link`);
      }
      return mine ? T('Ты назвал(а) место встречи', 'You named the place')
                  : T(`${by} назвал(а) место встречи`, `${by} named the place`);
    case 'plan_counter':
      return mine
        ? T(`Ты предложил(а) перенести${hour ? ' на ' + hour : ''} — до ответа в силе прежнее время`,
            `You suggested moving it${hour ? ' to ' + hour : ''} — the old time holds until they answer`)
        : T(`${by} предлагает${hour ? ' ' + hour : ' другое время'}${wasHour ? ' вместо ' + wasHour : ''}`,
            `${by} suggests${hour ? ' ' + hour : ' another time'}${wasHour ? ' instead of ' + wasHour : ''}`);
    case 'plan_change_ok':
      return T(`Новое время принято${when ? ' — ' + when : ''}`, `The new time is agreed${when ? ' — ' + when : ''}`);
    case 'plan_change_no':
      return mine ? T('Ты оставил(а) прежнее время', 'You kept the original time')
                  : T(`${by} оставил(а) прежнее время`, `${by} kept the original time`);
    case 'plan_change_pulled':
      return mine ? T('Ты забрал(а) предложение о переносе', 'You took back the time change')
                  : T(`${by} забрал(а) предложение о переносе`, `${by} took back the time change`);
    case 'plan_cancelled':
      return mine ? T('Ты отменил(а) встречу', 'You called the meetup off')
                  : T(`${by} отменил(а) встречу`, `${by} called the meetup off`);
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
export function activeChatWith(threads: { who?: string; t?: number }[]): string {
  const live = (threads || []).filter((t) => String(t.who || '').trim());
  live.sort((a, b) => (b.t || 0) - (a.t || 0));
  return String(live[0]?.who || '');
}

/** Время сообщения — часы и минуты, как на кадре. */
export function msgTime(t?: number, ru = true): string {
  if (!t) return '';
  return new Date(t * 1000).toLocaleTimeString(ru ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: !ru,
  });
}

/** Разделитель дня в ленте (MSG.06 «Today»): Сегодня / Вчера / короткая дата. */
export function msgDayLabel(t: number, ru = true, nowMs = Date.now()): string {
  const d = new Date(t * 1000);
  const now = new Date(nowMs);
  const yest = new Date(nowMs - 86400000);
  if (d.toDateString() === now.toDateString()) return T('Сегодня', 'Today');
  if (d.toDateString() === yest.toDateString()) return T('Вчера', 'Yesterday');
  return d.toLocaleDateString(ru ? 'ru-RU' : 'en-US', { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Строка «Сегодня · 20:00 Barcelona» из плана. Часовых поясов у обоих сервер не хранит. */
export function planWhen(p: any, ru = true): string {
  const sa = p?.starts_at;
  if (typeof sa === 'number' && isFinite(sa)) {
    const d = new Date(sa * 1000);
    const day = d.toLocaleDateString(ru ? 'ru-RU' : 'en-US', { weekday: 'short', day: 'numeric', month: 'short' });
    const hm = d.toLocaleTimeString(ru ? 'ru-RU' : 'en-US', { hour: '2-digit', minute: '2-digit', hour12: !ru });
    return `${day} · ${hm}`;
  }
  return String(p?.when || '');
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
