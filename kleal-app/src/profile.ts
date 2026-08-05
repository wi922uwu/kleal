/**
 * Профиль — перенос с работающей веб-версии (kleal-ms/services/profile/app.py).
 *
 * Борд профиля вычитать не удалось: квота Figma на View-месте исчерпана. Источником взята живая
 * реализация — по прямому решению, после того как это было названо риском.
 *
 * Здесь derive и копия; экраны лежат в app/profile/. Устройство то же, что в вебе: хаб и три
 * раздела — интересы, личность, безопасность.
 *
 * Главное, что переносится не как верстка, а как смысл: profileData() повторяет mapOnboarding() из
 * веба, потому что из неё живут ВСЕ четыре экрана сразу. Пока derive один, карточка «Языки» на
 * хабе и строка «Общается на …» в памяти не могут разойтись между собой.
 */
import { T, getLang } from './i18n';
import { sexLabel, hobbyPlain } from './onboarding';
import type { Profile } from './state';

// ---------------------------------------------------------------- разделы

export type SectionId = 'interests' | 'personality' | 'safety';

export const PROFILE_TITLE = () => T('Мой профиль Kleal', 'My Kleal Profile');

export const SECTIONS: { id: SectionId; title: () => string; sub: () => string }[] = [
  {
    id: 'interests',
    title: () => T('Интересы', 'Interests'),
    sub: () => T('Чем ты любишь заниматься с людьми', 'What you like doing with people'),
  },
  {
    id: 'personality',
    title: () => T('Твоя личность', 'Your personality'),
    sub: () => T('Как ты воспринимаешься', 'How you come across'),
  },
  {
    id: 'safety',
    title: () => T('Безопасность и приватность', 'Safety & Privacy'),
    sub: () => T('Что Kleal может использовать и твои границы', 'What Kleal can use, and your limits'),
  },
];

export const HUB = {
  confidence: () => T('Наполненность профиля', 'Profile confidence'),
  summaryLabel: () => T('Сводка Kleal', "Kleal's summary"),
  edit: () => T('Изменить', 'Edit'),
  rewrite: () => T('Пересобрать', 'Rewrite'),
  save: () => T('Сохранить', 'Save'),
  cancel: () => T('Отмена', 'Cancel'),
  createIntent: () => T('Создать интент', 'Create intent'),
  lang: () => T('Язык интерфейса', 'Interface language'),
  avail: () => T('Доступность', 'Availability'),
  writing: () => T('Kleal составляет описание…', 'Kleal is writing your summary…'),
  empty: () =>
    T('Kleal опишет тебя здесь по мере знакомства.', 'Kleal will summarise you here as it learns more.'),
};

/** Статусы приёма — те же три, что понимает /api/onboarding/receiving. */
/**
 * Выход.
 *
 * Показывается ВСЕГДА, а не только при заведённом логине. Быстрый вход (app/auth.tsx) логина не
 * создаёт вовсе — он ставит только способ входа и уводит в анкету, — так что привязка кнопки к
 * логину прятала её ровно от тех, у кого другого выхода нет.
 *
 * Отсюда и два текста подтверждения. С логином профиль лежит на сервере и вернётся при входе. Без
 * логина возвращать его нечем: он записан по имени, но ключа к нему нет, и стирание устройства
 * действительно означает потерю. Об этом надо сказать прямо, а не одной формулировкой на оба
 * случая.
 */
export const SIGNOUT = {
  label: (hasLogin: boolean) =>
    hasLogin ? T('Выйти из аккаунта', 'Sign out') : T('Выйти и начать заново', 'Sign out and start over'),
  ask: (hasLogin: boolean) =>
    hasLogin
      ? T(
          'Выйти из аккаунта? Профиль останется на сервере и вернётся при следующем входе.',
          'Sign out? Your profile stays on the server and comes back when you sign in.'
        )
      : T(
          'У этого профиля нет логина, поэтому вернуть его будет нечем — он сотрётся вместе со всем, что собрано на этом телефоне. Выйти?',
          'This profile has no login, so there is nothing to restore it with — it will be erased along with everything collected on this phone. Sign out?'
        ),
  yes: () => T('Выйти', 'Sign out'),
  no: () => T('Отмена', 'Cancel'),
  who: (login: string | null) =>
    login ? T(`Вход выполнен как ${login}`, `Signed in as ${login}`)
          : T('Аккаунт не подключён', 'No account connected'),
};

export const AVAIL: [string, () => string][] = [
  ['active', () => T('Открыт', 'Open')],
  ['busy', () => T('Занят', 'Busy')],
  ['paused', () => T('Пауза', 'Pause')],
];

/**
 * «Обновлено сегодня» и далее. Метка приходит из локального времени устройства: в хранилище такой
 * колонки нет, и веб делает ровно так же. Без метки времени строку не рисуем вовсе — это честнее,
 * чем «обновлено сегодня» о тексте, написанном месяц назад.
 */
export function fmtUpdated(ts?: number | null): string {
  if (!ts) return '';
  const d = Math.floor((Date.now() - ts) / 864e5);
  if (d <= 0) return T('Обновлено сегодня', 'Updated today');
  if (d === 1) return T('Обновлено вчера', 'Updated yesterday');
  if (d < 7) return T(`Обновлено ${d} дн. назад`, `Updated ${d} days ago`);
  const dt = new Date(ts);
  return T(
    'Обновлено ' + dt.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
    'Updated ' + dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  );
}

// ---------------------------------------------------------------- derive

export type KV = [string, string];
/**
 * `name` — то, что лежит в профиле и уходит в матчинг (coffee, football). `label` — то, что видит
 * человек («Кофе»). Раздельно намеренно: онбординг хранит канонические ключи, иначе по интересам
 * не совпадёт никто, а показывать человеку ключ из базы — значит показывать ему внутренности.
 * Своё, написанное руками, hobbyPlain возвращает как есть.
 */
export type Interest = { name: string; label: string; conf: 'High' | 'Medium' | 'Low'; used: boolean; kv: KV[] };
export type Row = { title: string; value: string };

export type SafetyFlags = {
  autonomy: 'ask' | 'auto';
  confirmShare: boolean;
  paused: boolean;
  publicFirst: boolean;
  noLateNight: boolean;
  avoidAlcohol: boolean;
  sharePlan: boolean;
  useInterestsArea: boolean;
  useFeedback: boolean;
  inferNew: boolean;
  noSensitive: boolean;
  suggestBeyond: boolean;
  publicMap: boolean;
  datingMode: boolean;
  preferVerified: boolean;
  excludeKnown: boolean;
};

export type ProfileData = {
  name: string;
  confidence: number;
  basics: Row[];
  interests: Interest[];
  safety: SafetyFlags;
};

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const arr = (v: any): any[] => (Array.isArray(v) ? v : v != null && v !== '' ? [v] : []);
const lc = (s: any) => String(s == null ? '' : s).toLowerCase();

/** Мягкий поиск по ключам словаря: «Кофе» находит и «кофе», и «specialty coffee». */
function pickBy(m: any, name: string): any {
  if (!m || typeof m !== 'object') return null;
  const k = lc(name);
  for (const key of Object.keys(m)) {
    const kl = lc(key);
    if (kl === k || kl.includes(k) || k.includes(kl)) return m[key];
  }
  return null;
}

/** Роли лежат вложенным объектом произвольной глубины — разворачиваем в плоский поиск по имени. */
function roleOf(rolesRaw: any, name: string, only: string[]): any {
  const flat: Record<string, any> = {};
  (function eat(d: any) {
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      for (const k of Object.keys(d)) {
        const v = d[k];
        if (v && typeof v === 'object' && !Array.isArray(v)) eat(v);
        else if (v) flat[lc(k)] = v;
      }
    }
  })(rolesRaw);
  const k = lc(name);
  for (const kk of Object.keys(flat)) if (kk === k || kk.includes(k) || k.includes(kk)) return flat[kk];
  // Единственный интерес и роль строкой — значит роль его и есть, как бы её ни назвали.
  if ((typeof rolesRaw === 'string' || Array.isArray(rolesRaw)) && only.length === 1) return rolesRaw;
  return null;
}

const inList = (list: any, name: string) =>
  arr(list).some((x) => {
    const a = lc(x);
    const b = lc(name);
    return a === b || a.includes(b) || b.includes(a);
  });

export function profileData(op: Profile | any): ProfileData {
  op = op || {};
  const langs = arr(op.languages && (op.languages.comfortable || op.languages.fluent));
  const areas = arr(op.geo && op.geo.comfortableAreas);
  const city = areas[0] || op.city || '';
  const km = op.geo && op.geo.maxDistanceKm;
  const ints = arr(op.interests && op.interests.explicit).map(String);
  const rolesRaw = (op.interests && op.interests.roles) || {};
  const exp = (op.interests && op.interests.experienceByInterest) || {};
  const games = (op.domains && op.domains.games) || {};
  const sport = (op.domains && op.domains.sport) || {};
  const langd = (op.domains && op.domains.language) || {};
  const net = (op.domains && op.domains.networking) || {};
  const sf = op.safety || {};
  const pm = op.permissions || {};

  const interests: Interest[] = ints.map((name, i) => {
    const kv: KV[] = [];
    const n = lc(name);
    const r = roleOf(rolesRaw, name, ints);
    const e = pickBy(exp, name);
    if (r) kv.push([T('Роль', 'Role'), arr(r).map(cap).join(' / ')]);
    if (e) kv.push([T('Опыт', 'Experience'), String(e)]);
    if (inList(games.gamesList, name) || /dota|valorant|league|\bcs\b|apex|game/.test(n)) {
      const p = pickBy(games.platformsByGame, name);
      if (p) kv.push([T('Платформа', 'Platform'), String(p)]);
      const rk = pickBy(games.rankByGame, name);
      if (rk) kv.push([T('Ранг / уровень', 'Rank / level'), String(rk)]);
    }
    if (inList(sport.sportsList, name)) {
      const lv = pickBy(sport.skillLevelBySport, name);
      if (lv) kv.push([T('Уровень', 'Skill level'), cap(String(lv))]);
      const tm = pickBy(sport.favoriteTeams, name) ||
        (Array.isArray(sport.favoriteTeams) ? sport.favoriteTeams.join(', ') : null);
      if (tm) kv.push([T('Команда', 'Team'), String(tm)]);
    }
    if (/language|spanish|english|french|german|italian|practice/.test(n)) {
      if (langd.targetLanguage) kv.push([T('Язык', 'Language'), String(langd.targetLanguage)]);
      if (langd.targetLevel) kv.push([T('Уровень', 'Level'), String(langd.targetLevel)]);
    }
    if (/network|startup|business|career|founder/.test(n)) {
      if (net.industry) kv.push([T('Отрасль', 'Industry'), String(net.industry)]);
      if (net.goal) kv.push([T('Цель', 'Goal'), String(net.goal)]);
    }
    // Уверенность как в вебе: первые два интереса человек назвал сам и осознанно, дальше — по тому,
    // рассказал ли он о них хоть что-то сверх названия.
    const conf: Interest['conf'] = i < 2 ? 'High' : kv.length ? 'Medium' : 'Low';
    const used = !(op.interests && op.interests.unused && op.interests.unused.includes(name));
    return { name, label: hobbyPlain(name), conf, used, kv };
  });

  const basics: Row[] = [];
  if (op.gender || op.age) {
    // Пол показываем подписью, а не хранимым ключом. В вебе здесь просто `cap(gender)`, и на
    // русском экране это «Male» — то есть значение из базы, показанное человеку как есть.
    basics.push({
      title: T('Основное', 'Basics'),
      value: [op.gender ? sexLabel(String(op.gender)) : '', op.age].filter(Boolean).join(' · ') || '—',
    });
  }
  if (areas.length || city) {
    basics.push({
      title: T('Локация', 'Location'),
      value: [areas.join(', ') || city, km ? T(`до ${km} км`, `Max ${km} km`) : null].filter(Boolean).join(' · '),
    });
  }
  if (langs.length) basics.push({ title: T('Языки', 'Languages'), value: langs.join(' · ') });

  // Наполненность — доля из шести признаков, ровно как в вебе. Не «красивое число»: полоса,
  // которая всегда 74 %, не сообщает ничего.
  const have = [op.name, langs.length, areas.length || city, ints.length, op.summary,
                pm.useProfileForMatching !== undefined];
  const confidence = Math.round((100 * have.filter(Boolean).length) / 6);

  const consent = pm.useProfileForMatching !== false;
  const remember = !!pm.rememberPreferences;
  const safety: SafetyFlags = {
    autonomy: sf.autonomy === 'auto' ? 'auto' : 'ask',
    confirmShare: sf.confirmShare !== false,
    paused: !!sf.paused,
    publicFirst: sf.publicPlacesOnly !== false,
    noLateNight: sf.lateNight !== false,
    avoidAlcohol: !!sf.avoidAlcohol,
    sharePlan: !!sf.sharePlan,
    useInterestsArea: consent,
    useFeedback: remember,
    inferNew: remember,
    noSensitive: sf.noSensitive !== false,
    suggestBeyond: pm.allowAdjacentMatches !== false,
    publicMap: !!pm.publicMap,
    datingMode: !!pm.datingMode,
    preferVerified: !!sf.verifiedOnly,
    excludeKnown: sf.excludeKnown !== false,
  };

  return { name: op.name || T('Ты', 'You'), confidence, basics, interests, safety };
}

// ---------------------------------------------------------------- интересы

export const INTERESTS_SCREEN = {
  hint: () =>
    T(
      'Если переключатель включён, Kleal учитывает этот интерес при подборе.',
      'When a toggle is on, Kleal uses that interest for matching.'
    ),
  summary: (name: string) =>
    T(`Kleal ещё разбирается, что для тебя значит ${name}.`, `Kleal is still learning about your ${name}.`),
  emptyTitle: () => T('Пока нет интересов', 'No interests yet'),
  emptySub: () =>
    T(
      'Расскажи Kleal, чем увлекаешься — и они появятся здесь.',
      "Tell Kleal what you're into and they'll show up here."
    ),
  add: () => T('Добавить интересы', 'Add interests'),
  remove: () => T('Удалить', 'Remove'),
  confLabel: (c: string) =>
    c === 'High' ? T('высокая', 'high') : c === 'Medium' ? T('средняя', 'medium') : T('низкая', 'low'),
};

// ---------------------------------------------------------------- личность

export const PERSONALITY = {
  title: () => T('Твоя личность', 'Your personality'),
  takeTest: () => T('Пройти тест от Kleal', 'Take your personality test'),
  empty: () =>
    T(
      'Пройди тест — и Kleal расскажет, как ты воспринимаешься со стороны и с кем тебе легко.',
      'Take the test and Kleal will describe how you come across and who you click with.'
    ),
  editWith: () => T('Изменить с Kleal', 'Edit with Kleal'),
  storyCap: () =>
    T(
      'Расскажи историю своей жизни в свободном формате (детство, обучение, интересы, профессия)',
      'Tell your life story in your own words — childhood, studies, interests, work'
    ),
  storyPlaceholder: () =>
    T('Пиши как получится — Kleal сам разберётся.', "Write it however it comes out — Kleal will make sense of it."),
  confirm: () => T('Сохранить и закрыть', 'Confirm & Close'),
  saved: () => T('Сохранено', 'Saved'),
};

/** Предел из update_user: STORY_MAX. Обрезаем здесь же, чтобы не отправлять заведомо лишнее. */
export const STORY_MAX = 4000;

export type TestQ = { k: string; q: () => string; o: (() => string)[]; m: (string | null)[]; free?: boolean };

/**
 * Тест Kleal — восемь вопросов на клиенте и РОВНО один вызов /api/buddy/persona в конце.
 * По одному обращению к модели на вопрос — это восемь шансов повиснуть там, где вопросы всё равно
 * заданы заранее.
 *
 * `m` — токен, который уходит в профиль. null означает «ответ есть, но в поля подбора он не ложится»
 * («зависит от людей» — это не значение оси, а отказ от неё), и на экране результата так и написано.
 */
export const TEST_Q: TestQ[] = [
  { k: 'energy', q: () => T('После насыщенного дня с людьми ты скорее…', 'After a full day around people you usually feel…'),
    o: [() => T('Заряжен', 'Energised'), () => T('Вымотан', 'Drained'), () => T('Зависит от людей', 'Depends who they were')],
    m: ['energised', 'drained', null] },
  { k: 'group', q: () => T('Как тебе комфортнее знакомиться?', 'How do you prefer to meet people?'),
    o: [() => T('Один на один', 'One to one'), () => T('Небольшая группа, 3–5', 'A small group of 3–5'), () => T('Большая компания', 'A big crowd')],
    m: ['one', 'small', 'crowd'] },
  { k: 'depth', q: () => T('Какой разговор тебе ближе?', 'What kind of conversation suits you?'),
    o: [() => T('Глубокий, про смыслы', 'Deep, about what matters'), () => T('Лёгкий и весёлый', 'Light and funny'), () => T('Практичный, по делу', 'Practical, to the point')],
    m: ['deep', 'light', 'practical'] },
  { k: 'firstMeet', q: () => T('Идеальная первая встреча — это…', 'An ideal first meet is…'),
    o: [() => T('Кофе и разговор', 'Coffee and a talk'), () => T('Что-то делать вместе', 'Doing something together'), () => T('Событие или мероприятие', 'An event or a meetup')],
    m: ['talk', 'doing', 'event'] },
  { k: 'pace', q: () => T('Как ты сходишься с людьми?', 'How do you warm up to people?'),
    o: [() => T('Быстро и открыто', 'Fast and openly'), () => T('Постепенно, присматриваюсь', 'Slowly, I watch first'), () => T('Зависит от человека', 'Depends on the person')],
    m: ['fast', 'slow', null] },
  { k: 'planning', q: () => T('Планы или спонтанность?', 'Plans or spontaneity?'),
    o: [() => T('Договариваться заранее', 'Agree in advance'), () => T('Лучше спонтанно', 'Rather spontaneous'), () => T('Гибко', 'Flexible')],
    m: ['advance', 'spontaneous', null] },
  { k: 'seek', q: () => T('Что тебе сейчас важнее всего в новых знакомствах?', 'What matters most in new connections right now?'),
    o: [() => T('Друзья надолго', 'Friends for the long run'), () => T('Компания под интерес', 'Company for a specific interest'), () => T('Расширить круг', 'A wider circle')],
    m: ['long', 'interest', 'wider'] },
  { k: 'own', q: () => T('Что о тебе стоит знать, чтобы понять, с кем тебе легко?', 'What should Kleal know to understand who you click with?'),
    o: [], m: [], free: true },
];

export const TEST = {
  title: () => T('Тест от Kleal', 'Your Kleal test'),
  of: (i: number, n: number) => T(`Вопрос ${i} из ${n}`, `Question ${i} of ${n}`),
  skip: () => T('Пропустить', 'Skip'),
  placeholder: () => T('Своими словами…', 'In your own words…'),
  finish: () => T('Готово', 'Done'),
  working: () => T('Kleal обдумывает ответы…', 'Kleal is thinking it over…'),
  failed: () =>
    T('Не получилось собрать результат. Ответы сохранены — попробуй ещё раз.',
      'Could not put the result together. Your answers are saved — try again.'),
};

// ---------------------------------------------------------------- безопасность

export type SafetyItem =
  | { k: 'tog'; flag: keyof SafetyFlags; label: () => string; desc: () => string }
  | { k: 'choice'; label: () => string; desc: () => string; options: (() => string)[] }
  | { k: 'sub'; label: () => string };

export type SafetyGroup = { t: () => string; c: () => string; items: SafetyItem[] };

/**
 * Шесть групп — те же и в том же порядке, что в вебе. Подписи важны не меньше переключателей:
 * в каждой группе сказано, что означает «включено», потому что для одних тумблеров это «безопаснее»,
 * а для других — «шире охват», и по одному виду их не различить.
 */
export const SAFETY_GROUPS: SafetyGroup[] = [
  {
    t: () => T('Как Kleal действует за тебя', 'How Kleal acts for you'),
    c: () => T('Главные рычаги: насколько агент самостоятелен и пауза в один тап.',
               'The big levers — your agent’s autonomy and a one-tap pause.'),
    items: [
      { k: 'choice', label: () => T('Когда Kleal кого-то находит', 'When Kleal finds someone'),
        desc: () => T('Спрашивать перед тем, как написать, или пусть Kleal знакомит сам.',
                      'Ask before reaching out, or let Kleal introduce you automatically.'),
        options: [() => T('Сначала спросить', 'Ask me first'), () => T('Знакомить сам', 'Introduce automatically')] },
      { k: 'tog', flag: 'confirmShare',
        label: () => T('Спрашивать перед тем, как делиться моими данными', 'Confirm before sharing my details'),
        desc: () => T('Спрашивать, прежде чем показать твоё имя, фото или контакты — даже когда Kleal сам договаривается о встрече.',
                      'Ask before revealing your name, photo or contact — even when Kleal arranges plans for you.') },
      { k: 'tog', flag: 'paused',
        label: () => T('Поставить Kleal на паузу', 'Pause Kleal'),
        desc: () => T('Остановить новые подборы и знакомства. Профиль и память сохранятся.',
                      'Stop all new matching and outreach. Your profile and memory stay saved.') },
    ],
  },
  {
    t: () => T('Встречи вживую', 'Meeting in person'),
    c: () => T('Как Kleal делает встречи безопаснее. Здесь везде: включено = безопаснее.',
               'How Kleal keeps real-world plans safe. Every switch here: on = safer.'),
    items: [
      { k: 'tog', flag: 'publicFirst',
        label: () => T('Первые встречи — только в людных местах', 'Keep first meetups public'),
        desc: () => T('Первые встречи проходят в кафе, парках и других общественных местах.',
                      'First meets stay in cafes, parks and other public spots.') },
      { k: 'tog', flag: 'noLateNight',
        label: () => T('Никаких встреч один на один поздно вечером', 'No solo late-night meets'),
        desc: () => T('Kleal не будет предлагать встречи наедине поздним вечером.',
                      'Kleal avoids one-on-one plans late at night.') },
      { k: 'tog', flag: 'avoidAlcohol',
        label: () => T('Избегать мест, где всё вокруг алкоголя', 'Avoid alcohol-focused venues'),
        desc: () => T('Пропускать бары и подобные места для первых встреч.',
                      'Skip bars and heavy-drinking spots for first meets.') },
      { k: 'tog', flag: 'sharePlan',
        label: () => T('Делиться планом с доверенным контактом', 'Share my plan with a trusted contact'),
        desc: () => T('Автоматически отправлять близкому человеку, с кем, где и когда ты встречаешься.',
                      'Auto-send who, where and when to someone you choose.') },
    ],
  },
  {
    t: () => T('Что Kleal может использовать и запоминать', 'What Kleal may use & remember'),
    c: () => T('Твоё согласие на то, что Kleal читает и узнаёт. Включено = Kleal может это использовать.',
               'Your consent for what Kleal reads and learns. On = Kleal may use it.'),
    items: [
      { k: 'tog', flag: 'useInterestsArea',
        label: () => T('Подбирать по моим интересам и району', 'Match on my interests & area'),
        desc: () => T('Использовать твои увлечения и район города — но никогда точное местоположение.',
                      'Use what you like and your city area — never your exact location.') },
      { k: 'tog', flag: 'useFeedback',
        label: () => T('Учиться на моих оценках и действиях', 'Learn from my feedback & activity'),
        desc: () => T('Использовать твои оценки и то, какие планы ты принимаешь или отклоняешь.',
                      'Use your ratings and which plans you accept or decline.') },
      { k: 'tog', flag: 'inferNew',
        label: () => T('Разрешить Kleal делать выводы обо мне', 'Let Kleal infer new things about me'),
        desc: () => T('Разрешить догадки сверх того, что ты сказал напрямую — например, о любимых местах.',
                      'Allow guesses beyond what you stated, like preferred venues.') },
      { k: 'sub', label: () => T('Ограничения', 'Guardrails') },
      { k: 'tog', flag: 'noSensitive',
        label: () => T('Никогда не делать выводов о чувствительном', 'Never infer sensitive traits'),
        desc: () => T('Не хранить в памяти здоровье, религию, политику и ориентацию.',
                      'Keep health, religion, politics and orientation out of memory.') },
    ],
  },
  {
    t: () => T('Как тебя находят люди', 'How people find you'),
    c: () => T('Твой охват и видимость. Включено = больше охват, выключено = больше приватности.',
               'Your reach and visibility. On = more reach, off = more private.'),
    items: [
      { k: 'tog', flag: 'suggestBeyond',
        label: () => T('Предлагать людей за пределами привычного круга', 'Suggest people beyond my usual circles'),
        desc: () => T('Иногда предлагать людей со смежными интересами и планы вне привычного.',
                      'Occasionally propose friends-of-interests and plans outside your usuals.') },
      { k: 'tog', flag: 'publicMap',
        label: () => T('Показывать меня на карте', 'Show me on the discovery map'),
        desc: () => T('Другие смогут наткнуться на тебя на общей карте.',
                      'Let others come across you on the public map.') },
      { k: 'tog', flag: 'datingMode',
        label: () => T('Режим знакомств', 'Dating mode'),
        desc: () => T('По умолчанию выключен. Включи, чтобы Kleal предлагал и романтические знакомства.',
                      'Off by default. Turn on to let Kleal suggest dating intros too.') },
    ],
  },
  {
    t: () => T('Верификация и люди', 'Verification & people'),
    c: () => T('С кем Kleal будет тебя знакомить. Включено = осторожнее.',
               'Who Kleal will introduce you to. On = more protective.'),
    items: [
      { k: 'tog', flag: 'preferVerified',
        label: () => T('Предпочитать подтверждённых людей', 'Prefer verified people'),
        desc: () => T('Kleal будет отдавать предпочтение подтверждённым профилям.',
                      'Kleal favours verified profiles when it matches you.') },
      { k: 'tog', flag: 'excludeKnown',
        label: () => T('Не сводить меня с теми, кого я могу знать', 'Don’t match me with people I may know'),
        desc: () => T('Исключить коллег, бывших и контакты из телефона.',
                      'Exclude coworkers, exes and phone contacts from suggestions.') },
    ],
  },
];

export const SAFETY_LEAD = {
  title: () => T('Всё под твоим контролем', 'You’re in control'),
  body: () =>
    T(
      'Kleal ничего не делает без твоего согласия. Он показывает район города, а не точное место, узнаёт только то, что ты разрешил, и всё здесь можно откатить в любой момент.',
      'Kleal never acts without your say-so. It shares your city area, never your exact location, learns only what you allow, and everything here is reversible anytime.'
    ),
};

/**
 * Обратное отображение флагов экрана в поля профиля.
 *
 * Нужно ровно потому, что profileData() их СВОДИТ: `useFeedback` и `inferNew` оба приходят из
 * одного `permissions.rememberPreferences`, а `useInterestsArea` — из `useProfileForMatching`.
 * Без этой таблицы переключатель на экране менял бы что-то своё, а профиль — своё.
 */
export const SAFETY_PATH: Record<string, string> = {
  confirmShare: 'safety.confirmShare',
  paused: 'safety.paused',
  publicFirst: 'safety.publicPlacesOnly',
  noLateNight: 'safety.lateNight',
  avoidAlcohol: 'safety.avoidAlcohol',
  sharePlan: 'safety.sharePlan',
  noSensitive: 'safety.noSensitive',
  preferVerified: 'safety.verifiedOnly',
  excludeKnown: 'safety.excludeKnown',
  useInterestsArea: 'permissions.useProfileForMatching',
  useFeedback: 'permissions.rememberPreferences',
  inferNew: 'permissions.rememberPreferences',
  suggestBeyond: 'permissions.allowAdjacentMatches',
  publicMap: 'permissions.publicMap',
  datingMode: 'permissions.datingMode',
};

export const langCode = () => getLang();
