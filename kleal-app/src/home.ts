/**
 * Главный экран — то, что в вебе называется Agent Home.
 *
 * Здесь только копия и разбор данных; сам экран в app/home.tsx. Всё, что показывается, приходит с
 * сервера: группы из /api/agent/groups, подходящие люди из POST /api/agent/explore (он строже
 * обычного обзора — отбирает по профилю), приглашения из /api/agent/inbox. Придуманных карточек на
 * этом экране нет и быть не должно: человек по ним нажимает.
 */
import { T, getLang } from './i18n';

export const HOME = {
  hello: (name: string) => T(`Привет, ${name} 👋`, `Hey ${name} 👋`),
  groups: () => T('Групповые мероприятия', 'Group events'),
  people: () => T('Подходящие люди', 'People who fit'),
  noGroups: () => T('Пока нет открытых групповых мероприятий.', 'No open group events yet.'),
  noPeople: () =>
    T(
      'Пока никого подходящего. Расскажи, чем хочешь заняться, — и Kleal поищет.',
      'Nobody fits yet. Tell Kleal what you feel like doing and it will look.'
    ),
  ask: () => T('Чем хочешь заняться?', 'What do you feel like doing?'),
  history: () => T('Открыть историю разговоров', 'Open conversation history'),
  match: () => T('Мэтч', 'Match'),
  fits: () => T('Подходит', 'Match'),
  review: () => T('Посмотреть приглашение', 'Review invite'),
  respond: () => T('Откликнуться', 'Respond'),
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

export type Person = {
  intentId?: string;
  who: string;
  age?: number;
  photo?: string;
  title: string;
  when: string;
  area: string;
  dist: string;
};

export type Invite = {
  id: string;
  from: string;
  age?: number;
  photo?: string;
  note?: string;
  intent?: { title?: string; when?: string; time?: string; area?: string; place?: string };
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

export function forYouPeople(rows: any[]): Person[] {
  return (rows || []).slice(0, 3).map((p) => ({
    intentId: p.intentId,
    who: String(p.who || ''),
    age: p.age,
    photo: String(p.photo || ''),
    title: String(p.title || p.who || ''),
    when: String(p.when || ''),
    area: String(p.area || ''),
    dist: distStr(p.dist),
  }));
}

export function pendingInvites(rows: any[]): Invite[] {
  return (rows || []).filter((r) => r && r.status === 'pending');
}
