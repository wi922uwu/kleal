/**
 * Главный экран — то, что в вебе называется Agent Home.
 *
 * Здесь только копия и разбор данных; сам экран в app/home.tsx. Всё, что показывается, приходит с
 * сервера: группы из /api/agent/groups и адресованные пользователю приглашения из
 * /api/agent/home-invites. Потенциальные совпадения без явного приглашения сюда не попадают.
 */
import { T, getLang } from './i18n';

export const HOME = {
  /*
    ВОПРОС, А НЕ ПРИВЕТСТВИЕ. «Привет, друг 👋» — вежливая пустота: она ничего не спрашивает и
    ничего не предлагает, а под ней сразу колесо занятий и строка «Чем хочешь заняться?». Шапка
    теперь задаёт тот же вопрос первой, и весь экран читается как ответ на него.
    Имя из шапки ушло: у большинства оно не заполнено, и «Привет, друг» звучало как обращение к
    незнакомому — ровно наоборот тому, чего от приветствия ждут.
  */
  hello: () => T('Что сегодня?', 'What’s today?'),
  groups: () => T('Групповые мероприятия', 'Group events'),
  invites: () => T('Приглашения', 'Invitations'),
  /**
   * Кадр O.01, блок Activity: ближайшая встреча стоит на главной первой строкой. Её не было —
   * рисовались только группы и приглашения, а дойти до собственной встречи можно было лишь через
   * вкладку. Главная обязана отвечать на вопрос «что у меня сегодня» без переходов.
   */
  next: () => T('Ближайшая встреча', 'Next meetup'),
  goToPlan: () => T('К плану', 'Go to plan'),
  onCall: () => T('созвон', 'on a call'),
  /** Стопка приглашений разобрана. Их немного — это норма, а не поломка. */
  invitesAllSeen: () => T('Это все приглашения.', 'That’s every invite.'),
  /* Карточка «пока пусто» на главной — кадр «Home Card · Empty». Заголовок говорит, ЧЕГО нет, а
     строка под ним — что это не поломка, а ожидание: приглашения приходят, а не ищутся руками. */
  noInvites: () => T('Приглашений пока нет', 'No invites yet'),
  /* Заголовок пустого пузыря уведомлений. Короче, чем на карточке: там он объясняет пустой экран,
     здесь — отвечает на нажатие, и длинная фраза в маленьком окне читается как оправдание. */
  bellQuiet: () => T('Пока тихо', 'All quiet'),
  noInvitesNote: () => T('Они появятся здесь.', 'Invitations will appear here.'),
  discover: () => T('Найти людей', 'Search & Discover'),
  /**
   * Сколько ещё в стопке. С существительным: голое «Ещё 1» по-русски обрывок — ещё один чего?
   * Согласование то же, что у HOME.peopleCount, и живёт здесь, а не в компоненте: копия в src/*.ts.
   */
  invitesLeft: (n: number) => {
    const ten = n % 10, hundred = n % 100;
    const word = ten === 1 && hundred !== 11 ? 'приглашение'
      : ten >= 2 && ten <= 4 && (hundred < 10 || hundred >= 20) ? 'приглашения'
      : 'приглашений';
    return T(`Ещё ${n} ${word}`, `${n} more invite${n === 1 ? '' : 's'}`);
  },
  invitesNext: () => T('Дальше', 'Next'),
  inviteStatus: () => T('Приглашение', 'Invitation'),
  /**
   * Бейдж на карточке приглашения. На кадре GR.01 он короткий — «Match», 53 пункта, — потому что
   * стоит В ОДНОЙ СТРОКЕ с названием и отнимает у него место. Слово «Приглашение» длиннее вдвое, и
   * «Книжный клуб» превращался в «Книжный…»; вдобавок оно дословно повторяет заголовок секции, под
   * которым карточка и лежит. Здесь полезно другое: что зовут в ГРУППУ, а не один на один — в
   * стопке лежат и те и другие.
   */
  inviteKindGroup: () => T('Группа', 'Group'),
  inviteLoadFailed: () => T('Не удалось загрузить приглашения.', 'Invitations could not be loaded.'),
  retry: () => T('Повторить', 'Retry'),
  ask: () => T('Чем хочешь заняться?', 'What do you feel like doing?'),
  history: () => T('Открыть историю разговоров', 'Open conversation history'),
  match: () => T('Мэтч', 'Match'),
  fits: () => T('Подходит', 'Match'),
  review: () => T('Посмотреть приглашение', 'Review invite'),
  wantsToMeet: () => T('хочет встретиться', 'wants to meet'),
  hosting: (who: string) => T(`${who} организует`, `${who} is hosting`),
  /**
   * «Идут» согласуется с числом. Русский требует трёх форм, и «1 идут» на карточке читается как
   * недоделка — а это первое, что видно на главном экране.
   */
  going: (n: number) => {
    const t = n % 10, h = n % 100;
    const ru = t === 1 && h !== 11 ? 'идёт' : 'идут';
    return T(`${n} ${ru}`, `${n} going`);
  },
  peopleCount: (n: number, max?: number) => {
    const total = max && max > n ? `${n}/${max}` : String(n);
    return T(`${total} участников`, `${total} participants`);
  },
  flexible: () => T('Гибко', 'Flexible'),
  noArea: () => T('место не указано', 'area not set'),
};

/**
 * Разбить свободное «когда» на дату и время.
 *
 * Организатор пишет как хочет («Sat, 24 June · 9pm», «сегодня вечером», «на выходных»), поэтому
 * это не парсер, а разделение по явному времени на часах. Русские слова времени суток намеренно
 * остаются внутри даты: попытка ловить их регуляркой однажды разрезала «сегодня» пополам, потому
 * что «дня» — часть этого слова.
 */
export function splitWhen(raw: string): { date: string; time: string } {
  const s = String(raw || '').trim();
  if (!s) return { date: HOME.flexible(), time: '' };
  const m = s.match(/(\d{1,2}[:.]\d{2}\s*(?:AM|PM|am|pm)?|\d{1,2}\s*(?:AM|PM|am|pm))/);
  if (!m || m.index == null) return { date: s, time: '' };
  const time = m[0].trim();
  const date = s.slice(0, m.index).replace(/[·,\s]+$/, '').trim() || s;
  return { date, time };
}

/**
 * Где встреча.
 *
 * Расстояние показывается ТОЛЬКО когда оно что-то значит. Оно измерено до фиксированной точки, и
 * для человека из другого города выходит «Москва · 2.6 км» — противоречие в одной строке. Если
 * районы разные, честнее назвать район и промолчать про километры.
 */
export function planWhere(area: string, dist: string, myArea: string): string {
  const a = String(area || '').trim();
  const mine = String(myArea || '').trim();
  const same =
    !a || !mine ? null
    : a.toLowerCase() === mine.toLowerCase()
      || a.toLowerCase().includes(mine.toLowerCase())
      || mine.toLowerCase().includes(a.toLowerCase());
  const d = dist && same !== false ? dist : '';
  return a && d ? `${a} · ${d}` : a || d || HOME.noArea();
}

/** Строка расстояния. Пусто, если сервер его не посчитал, — «0 км» было бы неправдой. */
export function distStr(dist: unknown): string {
  const n = typeof dist === 'number' ? dist : parseFloat(String(dist ?? ''));
  if (!isFinite(n)) return '';
  return `${n} ${getLang() === 'ru' ? 'км' : 'km'}`;
}

export type Group = {
  gid: string;
  title: string;
  host: string;
  topics: string[];
  when: string;
  area: string;
  size: number;
  max_size: number;
  state: string;
  mine?: boolean;
  waiting?: boolean;
};

export type HomeInvite = {
  id: string;
  type: 'one_to_one' | 'group';
  created_at?: string;
  from: { name: string; age?: number; photo?: string };
  note?: string;
  intent: { id?: string; title?: string; when?: string; mode?: string; area?: string };
  group?: {
    gid: string;
    cover?: string;
    participants: { name: string; photo?: string }[];
    participant_count: number;
    max_size?: number;
  };
};

/** Группы, к которым имеет смысл предлагать присоединиться: чужие, не набранные, не ожидающие. */
export function joinableGroups(rows: any[]): Group[] {
  return (rows || [])
    .filter((g) => g && g.gid && !g.mine && !g.waiting && g.state !== 'full')
    .slice(0, 5)
    .map((g) => ({
      gid: String(g.gid),
      title: String(g.title || ''),
      host: String(g.host || ''),
      topics: Array.isArray(g.topics) ? g.topics.map(String) : [],
      when: String(g.when || ''),
      area: String(g.area || ''),
      size: Number(g.size || 0),
      max_size: Number(g.max_size || 0),
      state: String(g.state || ''),
    }));
}

export function homeInvites(rows: any[]): HomeInvite[] {
  return (rows || [])
    .filter((row) => row && row.id && (row.type === 'one_to_one' || row.type === 'group'))
    .map((row) => ({
      id: String(row.id),
      type: row.type,
      created_at: String(row.created_at || ''),
      from: {
        name: String(row.from?.name || row.from || ''),
        age: row.from?.age == null ? undefined : Number(row.from.age),
        photo: String(row.from?.photo || ''),
      },
      note: String(row.note || ''),
      intent: {
        id: String(row.intent?.id || ''),
        title: String(row.intent?.title || ''),
        when: String(row.intent?.when || ''),
        mode: String(row.intent?.mode || ''),
        area: String(row.intent?.area || ''),
      },
      group: row.group ? {
        gid: String(row.group.gid || ''),
        cover: String(row.group.cover || ''),
        participants: Array.isArray(row.group.participants)
          ? row.group.participants.map((p: any) => ({ name: String(p?.name || ''), photo: String(p?.photo || '') }))
          : [],
        participant_count: Number(row.group.participant_count || 0),
        max_size: row.group.max_size == null ? undefined : Number(row.group.max_size),
      } : undefined,
    }));
}
