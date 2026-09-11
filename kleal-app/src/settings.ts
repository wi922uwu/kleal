/**
 * Настройки.
 *
 * ЧТО ЗДЕСЬ ИЗМЕНИЛОСЬ И ПОЧЕМУ. Прежний экран показывал восемь строк, из которых пять вели в
 * никуда: «Сменить пароль» (пароля в продукте нет вовсе — вход по коду на почту), «Способ оплаты»
 * (платежей нет), «Уведомления» (пушей в проекте нет — в package.json нет даже expo-notifications),
 * «Помощь и поддержка» (за строкой ничего) и «Тёмная тема» (в src/theme.ts одна палитра). Они
 * стояли приглушёнными и не нажимались, и это было честнее, чем врать, — но строка, которой не
 * будет, всё равно занимает место и обещает.
 *
 * За переключателями безопасности было хуже. Их было пятнадцать, и сверка с боевым кодом показала:
 * девять не читает НИКТО и НИГДЕ (confirmShare, lateNight, avoidAlcohol, sharePlan, noSensitive,
 * excludeKnown, rememberPreferences, publicMap, datingMode), ещё три пишет онбординг, но подбор их
 * не смотрит. Даже флагманская «пауза» уходила в `safety.paused` — поле, которого не читает ни одна
 * служба, тогда как подбор смотрит на `receiving.status`. Человек двигал ползунок «остановить новые
 * знакомства», и не менялось ничего.
 *
 * ЧТО ВЗАМЕН. Ровно то, что движок подбора умеет исполнять, — и ничего сверх. У сервера уже была
 * готовая политика приёма (`/api/onboarding/receiving`, спека Matching Core §4.4): статус, приём
 * предложений, разрешённые виды встреч, тихие часы, пауза до даты. Подбор читает её в двух десятках
 * мест. Экрана к ней не было ни одного.
 */
import { T } from './i18n';

export const SETTINGS = {
  title: () => T('Настройки', 'Settings', 'Ajustes'),
  logout: () => T('Выйти', 'Log out', 'Cerrar sesión'),
};

export type SettingId =
  | 'personal' | 'visibility' | 'availability' | 'blocked'
  | 'language' | 'privacy' | 'account';

export type SettingRow = {
  id: SettingId;
  title: () => string;
  /** Подпись под строкой: что человек тут решает. Без неё список — просто набор слов. */
  sub: () => string;
  to?: string;
  control?: 'lang';
};

export const SETTING_ROWS: SettingRow[] = [
  { id: 'personal', to: '/profile',
    title: () => T('Профиль', 'Profile', 'Perfil'),
    sub: () => T('Имя, интересы, языки, район', 'Name, interests, languages, area', 'Nombre, intereses, idiomas, zona') },
  { id: 'visibility', to: '/settings/visibility',
    title: () => T('Кто меня видит', 'Who can find me', '¿Quién puede encontrarme?'),
    sub: () => T('Показываться в поиске или уйти с радаров', 'Appear in search, or go off the radar', 'Aparecer en la búsqueda o salir del radar') },
  { id: 'availability', to: '/settings/availability',
    title: () => T('Когда меня можно звать', 'When I can be invited', 'Cuándo se me puede invitar'),
    sub: () => T('Виды встреч и часы тишины', 'Kinds of meetups and quiet hours', 'Tipos de quedadas y horas tranquilas') },
  { id: 'blocked', to: '/settings/blocked',
    title: () => T('Заблокированные', 'Blocked people', 'Personas bloqueadas'),
    sub: () => T('Они не напишут и не увидят твои интенты', 'They can’t write to you or see your intents', 'No pueden escribirte ni ver tus propuestas') },
  { id: 'language', control: 'lang',
    title: () => T('Язык', 'Language', 'Idioma'),
    sub: () => T('Язык приложения', 'Interface language', 'Idioma de la interfaz') },
  { id: 'privacy', to: '/settings/privacy',
    title: () => T('Данные и приватность', 'Data and privacy', 'Datos y privacidad'),
    sub: () => T('Что хранится и что с этим можно сделать', 'What is stored and what you can do about it', 'Qué se almacena y qué puedes hacer al respecto') },
  { id: 'account', to: '/settings/account',
    title: () => T('Аккаунт', 'Account', 'Cuenta'),
    sub: () => T('Вход и удаление аккаунта', 'Sign-in and deleting your account', 'Iniciar sesión y eliminar tu cuenta') },
];

// ─────────────────────────────────────────────────────────────────── кто меня видит

/**
 * Три статуса приёма — ровно те, что понимает сервер (`_RECV_STATUSES`).
 *
 * Подписи говорят о ПОСЛЕДСТВИИ, а не о названии. «Пауза» сама по себе не объясняет, исчезнешь ли
 * ты из чужого поиска или просто перестанешь искать сам; человеку надо знать именно это.
 */
export const RECV_STATUS: { id: 'active' | 'busy' | 'paused'; label: () => string; what: () => string }[] = [
  { id: 'active', label: () => T('Открыт', 'Open', 'Abierto'),
    what: () => T('Тебя находят в поиске и могут позвать.', 'People find you in search and can invite you.', 'Las personas te encontrarán en la búsqueda y te pueden invitar.') },
  { id: 'busy', label: () => T('Занят', 'Busy', 'Ocupado'),
    what: () => T('Тебя ещё находят, но Kleal реже предлагает тебя другим.',
                  'You are still findable, but Kleal offers you to others less often.', 'Todavía eres visible, pero Kleal te ofrecerá menos a otros.') },
  { id: 'paused', label: () => T('Пауза', 'Pause', 'Pausa'),
    what: () => T('Тебя не находит никто. Профиль, интересы и переписки остаются на месте.',
                  'Nobody can find you. Your profile, interests and chats stay untouched.', 'Nadie te podrá encontrar. Tu perfil, intereses y chats permanecerán intactos.') },
];

export const VISIBILITY = {
  title: () => T('Кто меня видит', 'Who can find me', '¿Quién puede encontrarme?'),
  statusTitle: () => T('Меня можно найти', 'Findable', 'Encontrable'),
  /** Слово «сейчас» существенно: статус меняется одним тапом и действует до следующего. */
  statusLead: () =>
    T('Это решает, показывать ли тебя другим прямо сейчас.',
      'This decides whether other people see you right now.', 'Esto decide si otras personas te ven ahora mismo.'),
  outreachTitle: () => T('Приглашения от незнакомых', 'Invites from people you don’t know', 'Invitaciones de personas que no conoces'),
  outreachDesc: () =>
    T('Выключишь — звать тебя смогут только те, с кем вы уже знакомы. Искать самому это не мешает.',
      'Turn this off and only people you already know can invite you. You can still search yourself.', 'Deshabilita esto y solo las personas que ya conoces podrán invitarte. Tú aún puedes buscar tú mismo.'),
  /*
   * «Только подтверждённые» здесь НЕТ намеренно. Подбор читает `verifiedOnly` из ИНТЕНТА, а буди
   * ставит его лишь для свиданий (`bool(dating)`) — настройка профиля туда не доезжает. Чтобы
   * тумблер что-то значил, подбор должен брать умолчание из профиля ищущего; пока этого нет,
   * рисовать его — значит завести шестнадцатый мёртвый переключатель вместо пятнадцати снятых.
   */
  pausedNote: () =>
    T('Пока стоит пауза, новых знакомств не будет. Уже начатые переписки продолжаются.',
      'While paused you get no new introductions. Conversations already started keep working.', 'Mientras esté pausado no recibirás nuevas introducciones. Las conversaciones ya iniciadas seguirán funcionando.'),
  saved: () => T('Сохранено', 'Saved', 'Guardado'),
  failed: () => T('Не сохранилось. Проверь связь.', 'Didn’t save. Check your connection.', 'No se guardó. Comprueba tu conexión.'),
};

// ─────────────────────────────────────────────────────────────── когда меня можно звать

/**
 * Виды встреч — ключи ровно из серверного `_RECV_DOMAINS`. Незнакомый ключ сервер молча выбросит,
 * поэтому список здесь не «примерно такой», а буквально тот же.
 *
 * `dating` намеренно последним и отделён: он один меняет смысл знакомства, а не его формат.
 */
export const RECV_DOMAINS: { id: string; label: () => string }[] = [
  { id: 'social_meet', label: () => T('Просто встретиться', 'Just meet up', 'Solo quedar') },
  { id: 'walk', label: () => T('Прогулка', 'A walk', 'Un paseo') },
  { id: 'games', label: () => T('Игры', 'Games', 'Juegos') },
  { id: 'language_exchange', label: () => T('Языковой обмен', 'Language exchange', 'Intercambio de idiomas') },
  { id: 'sport_activity', label: () => T('Спорт', 'Sport', 'Deporte') },
  { id: 'culture_event', label: () => T('Культура и события', 'Culture and events', 'Cultura y eventos') },
  { id: 'watch_together', label: () => T('Смотреть вместе', 'Watch together', 'Ver juntos') },
  { id: 'coworking', label: () => T('Поработать рядом', 'Coworking', 'Coworking') },
  { id: 'professional_networking', label: () => T('Профессиональное', 'Professional', 'Profesional') },
  { id: 'dating', label: () => T('Свидания', 'Dating', 'Citas') },
];

export const AVAILABILITY = {
  title: () => T('Когда меня можно звать', 'When I can be invited', 'Cuándo se me puede invitar'),
  domainsTitle: () => T('Виды встреч', 'Kinds of meetups', 'Tipos de quedadas'),
  domainsLead: () =>
    T('Зовут только на то, что здесь отмечено. Снятое не предложат вовсе.',
      'You only get invited to what is ticked here. Unticked kinds are never offered.', 'Solo te invitan a lo que esté marcado aquí. Los tipos no marcados nunca se ofrecen.'),
  domainsEmpty: () =>
    T('Не отмечено ничего — значит не позовут никуда. Отметь хотя бы одно.',
      'Nothing is ticked, so nobody can invite you anywhere. Tick at least one.', 'Nada seleccionado, así que nadie puede invitarte a ningún sitio. Selecciona al menos uno.'),
  quietTitle: () => T('Часы тишины', 'Quiet hours', 'Horas silenciosas'),
  quietLead: () =>
    T('В эти часы Kleal не станет предлагать тебе встречи. Время местное.',
      'Kleal won’t propose plans during these hours. Local time.', 'Kleal no propondrá planes durante estas horas. Hora local.'),
  quietFrom: () => T('С', 'From', 'Desde'),
  quietTo: () => T('До', 'Until', 'Hasta'),
  untilTitle: () => T('Пауза до даты', 'Pause until a date', 'Pausa hasta una fecha'),
  untilLead: () =>
    T('Уехал, занят, надо выдохнуть — Kleal сам вернёт тебя в поиск в этот день.',
      'Away, busy, need a break — Kleal puts you back in search on that day.', 'Fuera, ocupado, necesitas un descanso — Kleal te vuelve a poner en búsqueda ese día.'),
  untilNone: () => T('Не задана', 'Not set', 'No establecido'),
  untilClear: () => T('Убрать', 'Clear', 'Borrar'),
  untilSet: (d: string) => T(`Вернёшься в поиск ${d}`, `You return to search on ${d}`, `Vuelves a buscar en ${d}`),
};

// ─────────────────────────────────────────────────────────────────── данные и приватность

/**
 * Политика — своим текстом и по делу.
 *
 * Прежняя строка «Приватность и безопасность» вела на экран переключателей, а собственно политики
 * в продукте не было ни строчки. Здесь написано только то, что правда и что можно проверить по
 * коду: какие поля хранятся, куда уходит текст разговора, что видно другим и что человек может с
 * этим сделать. Ни одного обещания, которого продукт не выполняет.
 */
export const PRIVACY = {
  title: () => T('Данные и приватность', 'Data and privacy', 'Datos y privacidad'),
  updated: () => T('Обновлено 4 сентября 2026', 'Updated 4 September 2026', 'Actualizado el 4 de septiembre de 2026'),
  sections: [
    {
      h: () => T('Что мы храним', 'What we store', 'Lo que almacenamos'),
      b: () => T(
        'Имя, возраст, район города, языки, интересы и ответы теста характера — то, что ты сам ввёл в анкете. Переписки с людьми и разговоры с агентом. Приглашения и планы встреч.',
        'Your name, age, city area, languages, interests and personality answers — what you entered yourself. Your chats with people and with the agent. Invitations and meeting plans.', 'Tu nombre, edad, área urbana, idiomas, intereses y respuestas de personalidad — lo que tú mismo introdujiste. Tus chats con personas y con el agente. Invitaciones y planes de reunión.'),
    },
    {
      h: () => T('Чего мы не храним', 'What we don’t store', 'Lo que no almacenamos'),
      b: () => T(
        'Точное местоположение. Kleal знает район города и расстояние в километрах, а не координаты твоего дома. Ни платёжных данных, ни паролей: вход устроен по коду на почту, пароля у тебя просто нет.',
        'Your exact location. Kleal knows your city area and a distance in kilometres, not your home coordinates. No payment details and no passwords: sign-in works by an emailed code, so you have no password at all.', 'Tu ubicación exacta. Kleal conoce tu área urbana y una distancia en kilómetros, no tus coordenadas de casa. No se guardan datos de pago ni contraseñas: el inicio de sesión se hace con un código por correo, así que no tienes contraseña en absoluto.'),
    },
    {
      h: () => T('Что видят другие', 'What other people see', 'Lo que ven otras personas'),
      b: () => T(
        'Имя, фото, район, интересы и то, чем ты предложил заняться. Возраст показывается, расстояние — примерное. Переписку видит только собеседник. Заблокированному не показывают ничего, и о блокировке ему не сообщают.',
        'Your name, photo, area, interests and what you proposed doing. Your age is shown; distance is approximate. Your chat is visible only to the other person. A blocked person sees nothing, and is never told they were blocked.', 'Tu nombre, foto, área, intereses y lo que proponiste hacer. Se muestra tu edad; la distancia es aproximada. Tu chat es visible solo para la otra persona. Una persona bloqueada no ve nada y nunca se le dice que fue bloqueada.'),
    },
    {
      h: () => T('Зачем нужна модель', 'Why there is a model', 'Por qué hay un modelo'),
      b: () => T(
        'Разговор с агентом обрабатывает языковая модель — она вытаскивает из твоих слов интересы и собирает затею. Модель работает на нашем сервере, а не в чужом облаке.',
        'Your conversation with the agent is processed by a language model, which turns your words into interests and builds the plan. The model runs on our own server, not in someone else’s cloud.', 'Tu conversación con el agente es procesada por un modelo de lenguaje, que convierte tus palabras en intereses y construye el plan. El modelo corre en nuestro propio servidor, no en la nube de otra persona.'),
    },
    {
      h: () => T('Что ты можешь сделать', 'What you can do', 'Lo que puedes hacer'),
      b: () => T(
        'Уйти из поиска одним тапом — «Кто меня видит». Заблокировать кого угодно, без объяснений. Удалить аккаунт: строка стирается и из файла, и из базы, вместе с почтой и всеми сессиями. Это не пометка «удалён», а настоящее удаление, и вернуть его нельзя.',
        'Leave search with one tap — “Who can find me”. Block anyone, no explanation needed. Delete your account: your row is erased from both the file and the database, along with your email and every session. It is real deletion, not a “deleted” flag, and it cannot be undone.', 'Abandona la búsqueda con un toque — “¿Quién puede encontrarme?”. Bloquea a cualquiera, sin necesidad de explicación. Elimina tu cuenta: tu fila se borra tanto del archivo como de la base de datos, junto con tu correo y cada sesión. Es una eliminación real, no un “eliminado”, y no se puede deshacer.'),
    },
  ],
};

// ─────────────────────────────────────────────────────────────────────────── аккаунт

export const ACCOUNT = {
  title: () => T('Аккаунт', 'Account', 'Cuenta'),
  signedAs: (login: string) => T(`Вход выполнен как ${login}`, `Signed in as ${login}`, `Iniciado como ${login}`),
  noLogin: () => T('Аккаунт не подключён', 'No account connected', 'No hay cuenta conectada'),
  noLoginWhy: () =>
    T('Профиль живёт только на этом устройстве. Подключи почту, чтобы он вернулся после переустановки.',
      'Your profile lives on this device only. Connect an email so it survives a reinstall.', 'Tu perfil vive solo en este dispositivo. Conecta un correo para que sobreviva a una reinstalación.'),
  deleteTitle: () => T('Удалить аккаунт', 'Delete account', 'Borrar cuenta'),
  deleteDesc: () =>
    T('Профиль, интересы, переписки и почта стираются насовсем. Отменить нельзя.',
      'Your profile, interests, chats and email are erased for good. This cannot be undone.', 'Tu perfil, intereses, chats y correo se eliminarán para siempre. Esto no se puede deshacer.'),
  /** Спрашиваем ДВАЖДЫ: первый вопрос — о намерении, второй — о необратимости. */
  ask1: () => T('Удалить аккаунт?', 'Delete your account?', '¿Borrar tu cuenta?'),
  ask1Body: () =>
    T('Профиль, интересы, переписки и приглашения будут стёрты.',
      'Your profile, interests, chats and invitations will be erased.', 'Tu perfil, intereses, chats e invitaciones se borrarán.'),
  ask2: () => T('Это уже нельзя отменить', 'This cannot be undone', 'Esto no se puede deshacer'),
  ask2Body: () =>
    T('Восстановить будет нечем: строка удаляется из базы, а не помечается. Точно удалить?',
      'There will be nothing to restore: the row is deleted from the database, not flagged. Delete for good?', 'No habrá nada que restaurar: la fila se ha borrado de la base de datos, no marcada. ¿Eliminar definitivamente?'),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),
  confirm: () => T('Удалить', 'Delete', 'Borrar'),
  deleting: () => T('Удаляю…', 'Deleting…', 'Borrando…'),
  failed: () => T('Не получилось удалить. Попробуй ещё раз.', 'Couldn’t delete. Please try again.', 'No se pudo eliminar. Inténtalo de nuevo.'),
  needSignIn: () =>
    T('Удалять нечего: аккаунт не подключён. Выход сотрёт профиль с этого устройства.',
      'Nothing to delete: no account is connected. Logging out erases the profile from this device.', 'Nada que borrar: no hay cuenta conectada. Cerrar sesión eliminará el perfil de este dispositivo.'),
};

// ─────────────────────────────────────────────────────────────────── заблокированные

export const BLOCKED = {
  title: () => T('Заблокированные', 'Blocked people', 'Personas bloqueadas'),
  row: (n: number) =>
    n === 1 ? T('1 человек · он об этом не знает', '1 person · they are not told', '1 persona · no se le ha informado')
            : T(`${n} человека · они об этом не знают`, `${n} people · they are not told`, `${n} personas · no están informadas`),
  none: () => T('Никого', 'Nobody', 'Nadie'),
  lead: () =>
    T(
      'Заблокированный не может тебе написать и не видит твоих интентов. Ему об этом не сообщают.',
      'A blocked person can’t message you and can’t see your intents. They are not told about it.',
    ),
  empty: () => T('Ты никого не блокировал.', 'You haven’t blocked anyone.', 'No has bloqueado a nadie.'),
  unblock: () => T('Разблокировать', 'Unblock', 'Desbloquear'),
  /**
   * Даты рядом с именем не будет. Сервер хранит список блокировок именами и ничем больше — ни
   * когда, ни возраст. На кадре «Blocked 24 July» стоит как заполнитель; написать сюда любую дату
   * значит показать человеку выдуманный факт о его собственном решении.
   */
  since: () => '',
};
