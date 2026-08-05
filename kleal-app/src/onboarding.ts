/**
 * Данные онбординга: слайды, сценарий шагов и справочники.
 *
 * Всё перенесено ДОСЛОВНО из живой реализации (kleal-ms/services/onboarding/app.py) — это текущая
 * правда продукта, проверенная на людях. Новый борд онбординга в Figma выгрузить не удалось
 * (кончилась квота MCP), поэтому источником взята работающая версия; когда квота вернётся,
 * строки надо сверить с бордом, а не переписать по памяти.
 */
import { T } from './i18n';

// ---------------------------------------------------------------- интро

export type Slide = { title: string; sub: string; art: 'primary' | 'searching' | 'match' };

/** Английский здесь — оригинал из Figma. Русский написан, а не переведён машинно. */
export const SLIDES: () => Slide[] = () => [
  {
    title: T('Скажи Kleal,\nчем хочешь заняться', 'Tell Kleal what you\nwant to do'),
    sub: T(
      'Кофе, партия, игра, прогулка, языковая практика — или просто «хочу куда-нибудь».',
      'Coffee, a match, a game, a walk, language practice, or just something spontaneous.'
    ),
    art: 'primary',
  },
  {
    title: T('Ищем людей под план,\nа не анкеты для листания', 'Find people for the plan,\nnot profiles to scroll'),
    sub: T(
      'Kleal подбирает людей, комнаты, группы и события по настроению, времени, месту и интересам.',
      'Kleal looks for the right people, rooms, groups or events from your mood, time, place and interests.'
    ),
    art: 'searching',
  },
  {
    title: T('Меньше переписки.\nБольше живых встреч', 'Less social admin.\nMore real plans'),
    sub: T(
      'Kleal находит, кому это интересно, проверяет совпадение и приносит варианты. Каждый шаг подтверждаешь ты.',
      'Kleal finds who is interested, checks the fit, and brings you options. You confirm every step.'
    ),
    art: 'match',
  },
];

export const AUTH_TERMS = () =>
  T(
    'Продолжая, ты соглашаешься с Условиями и Политикой конфиденциальности.',
    'By continuing you agree to our Terms and Privacy Policy.'
  );

// ---------------------------------------------------------------- справочники

export const GENDERS: [string, string][] = [
  ['Male', 'Мужчина'],
  ['Female', 'Женщина'],
  ['Other', 'Другое'],
];
export const genderLabel = (v: string) => {
  const g = GENDERS.find((x) => x[0] === v);
  return g ? T(g[1], g[0]) : String(v || '');
};

export const LANGS = ['English', 'Spanish', 'German', 'French', 'Portuguese', 'Italian', 'Russian'];
const LANG_RU: Record<string, string> = {
  English: 'Английский',
  Spanish: 'Испанский',
  German: 'Немецкий',
  French: 'Французский',
  Portuguese: 'Португальский',
  Italian: 'Итальянский',
  Russian: 'Русский',
};
export const langLabel = (v: string) => (LANG_RU[v] ? T(LANG_RU[v], v) : String(v || ''));

/**
 * Десять интересов — и ровно те, что реально есть у людей в пуле (число в комментарии — сколько
 * человек его несёт). Длинное меню не даёт больше выбора: чего нет, пишется в «своё», а свободный
 * текст всё равно проходит матчинг буквальным словом.
 */
export const INTERESTS: [string, string][] = [
  ['coding', 'Код'],           // 568
  ['hiking', 'Походы'],        // 519
  ['gaming', 'Видеоигры'],     // 469
  ['yoga', 'Йога'],            // 445
  ['cooking', 'Готовка'],      // 433
  ['music', 'Музыка'],         // 376
  ['coffee', 'Кофе'],          // 326
  ['photography', 'Фото'],     // 305
  ['travel', 'Путешествия'],   // 303
  ['football', 'Футбол'],      // 257
];
export const intLabel = (v: string) => {
  const k = String(v || '').toLowerCase();
  const it = INTERESTS.find((x) => x[0] === k);
  return it ? T(it[1], it[0]) : String(v || ''); // свободный интерес показывается как написан
};

// ---------------------------------------------------------------- сценарий

export type StepId = 'ready' | 'name' | 'basics' | 'location' | 'language' | 'interests' | 'photo';

export type Step = {
  id: StepId;
  /** Реплики агента: приходят по одной, как в чате. */
  bot: (ctx: { name?: string }) => string[];
  hint?: () => string;
};

export const SCRIPT: Step[] = [
  {
    id: 'ready',
    bot: () => [T('Расскажешь пару деталей о себе?', 'Would you be willing to fill in a few details about yourself?')],
    hint: () => T('Выбери вариант или напиши своё', 'Pick some or write your own'),
  },
  {
    id: 'name',
    bot: () => [T('Отлично! Как тебя зовут?', "We're on! May I know your name?")],
  },
  {
    id: 'basics',
    bot: () => [T('Супер! Сначала немного о тебе.', 'Awesome! First, a little bit about you.')],
  },
  {
    id: 'location',
    bot: () => [T('Класс! Где ты обычно бываешь?', 'Cool! Where do you usually hang out?')],
  },
  {
    id: 'language',
    bot: () => [T('Отлично. На каких языках тебе комфортно общаться?', 'Great. What languages are you comfortable communicating in?')],
    hint: () => T('Выбери варианты или напиши свой', 'Pick some or write your own'),
  },
  {
    id: 'interests',
    bot: () => [T('Класс! Чем увлекаешься?', 'Cool! What are your hobbies?')],
    hint: () => T('Выбери из готовых или напиши своё', 'Choose from the pre-written options or write your own'),
  },
  {
    id: 'photo',
    bot: (ctx) => [
      T('Рад знакомству, ' + (ctx.name || '') + '!', 'Nice to meet you, ' + (ctx.name || '') + '!'),
      T(
        'Давай добавим фото профиля, чтобы тебя узнавали на встречах.',
        "Let's add a profile photo so people recognize you at meetups."
      ),
    ],
    hint: () => T('Добавь фото', 'Add a photo'),
  },
];
