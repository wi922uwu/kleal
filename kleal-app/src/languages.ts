/**
 * Языки для профиля — полный список с поиском.
 *
 * Семи языков с кадра A.07 хватает онбордингу: там это быстрый старт, а не полнота. В профиле
 * человек правит уже собранное, и «моего языка тут нет» — это тупик, потому что дописать его
 * некуда. Поэтому здесь список, а не выборка.
 *
 * Хранится АНГЛИЙСКОЕ имя — тем же, чем его пишет онбординг (`languages.comfortable`), иначе
 * профиль, собранный анкетой, и профиль, поправленный листом, разошлись бы формой. Код ISO нужен
 * отдельно: сервер держит `langs` двухбуквенными, и наивное `name[:2]` даёт для испанского «sp»
 * вместо «es» — то есть язык, которого не существует.
 *
 * Флаги стоят только там, где они есть на борде. У языка флага не бывает: на португальском говорят
 * и в Бразилии, на испанском — в двадцати странах, и раздать каждому по флажку значит выбрать за
 * человека, чей он. Семь с кадра оставлены, чтобы онбординг и профиль выглядели одинаково.
 */

import { getLang } from './i18n';

/** [английское имя, код ISO 639-1, русское имя, флаг (если есть на борде)] */
export type Lang = [string, string, string, string?];

export const ALL_LANGS: Lang[] = [
  ['English', 'en', 'Английский', '🇬🇧'],
  ['Spanish', 'es', 'Испанский', '🇪🇸'],
  ['German', 'de', 'Немецкий', '🇩🇪'],
  ['French', 'fr', 'Французский', '🇫🇷'],
  ['Italian', 'it', 'Итальянский', '🇮🇹'],
  ['Portuguese', 'pt', 'Португальский', '🇵🇹'],
  ['Russian', 'ru', 'Русский', '🇷🇺'],

  ['Afrikaans', 'af', 'Африкаанс'],
  ['Albanian', 'sq', 'Албанский'],
  ['Amharic', 'am', 'Амхарский'],
  ['Arabic', 'ar', 'Арабский'],
  ['Armenian', 'hy', 'Армянский'],
  ['Azerbaijani', 'az', 'Азербайджанский'],
  ['Basque', 'eu', 'Баскский'],
  ['Belarusian', 'be', 'Белорусский'],
  ['Bengali', 'bn', 'Бенгальский'],
  ['Bosnian', 'bs', 'Боснийский'],
  ['Bulgarian', 'bg', 'Болгарский'],
  ['Burmese', 'my', 'Бирманский'],
  ['Catalan', 'ca', 'Каталанский'],
  ['Chinese', 'zh', 'Китайский'],
  ['Croatian', 'hr', 'Хорватский'],
  ['Czech', 'cs', 'Чешский'],
  ['Danish', 'da', 'Датский'],
  ['Dutch', 'nl', 'Нидерландский'],
  ['Estonian', 'et', 'Эстонский'],
  ['Filipino', 'tl', 'Филиппинский'],
  ['Finnish', 'fi', 'Финский'],
  ['Galician', 'gl', 'Галисийский'],
  ['Georgian', 'ka', 'Грузинский'],
  ['Greek', 'el', 'Греческий'],
  ['Gujarati', 'gu', 'Гуджарати'],
  ['Hausa', 'ha', 'Хауса'],
  ['Hebrew', 'he', 'Иврит'],
  ['Hindi', 'hi', 'Хинди'],
  ['Hungarian', 'hu', 'Венгерский'],
  ['Icelandic', 'is', 'Исландский'],
  ['Indonesian', 'id', 'Индонезийский'],
  ['Irish', 'ga', 'Ирландский'],
  ['Japanese', 'ja', 'Японский'],
  ['Javanese', 'jv', 'Яванский'],
  ['Kannada', 'kn', 'Каннада'],
  ['Kazakh', 'kk', 'Казахский'],
  ['Khmer', 'km', 'Кхмерский'],
  ['Korean', 'ko', 'Корейский'],
  ['Kurdish', 'ku', 'Курдский'],
  ['Kyrgyz', 'ky', 'Киргизский'],
  ['Lao', 'lo', 'Лаосский'],
  ['Latvian', 'lv', 'Латышский'],
  ['Lithuanian', 'lt', 'Литовский'],
  ['Macedonian', 'mk', 'Македонский'],
  ['Malay', 'ms', 'Малайский'],
  ['Malayalam', 'ml', 'Малаялам'],
  ['Maltese', 'mt', 'Мальтийский'],
  ['Marathi', 'mr', 'Маратхи'],
  ['Mongolian', 'mn', 'Монгольский'],
  ['Nepali', 'ne', 'Непальский'],
  ['Norwegian', 'no', 'Норвежский'],
  ['Pashto', 'ps', 'Пушту'],
  ['Persian', 'fa', 'Персидский'],
  ['Polish', 'pl', 'Польский'],
  ['Punjabi', 'pa', 'Панджаби'],
  ['Romanian', 'ro', 'Румынский'],
  ['Serbian', 'sr', 'Сербский'],
  ['Sinhala', 'si', 'Сингальский'],
  ['Slovak', 'sk', 'Словацкий'],
  ['Slovenian', 'sl', 'Словенский'],
  ['Somali', 'so', 'Сомалийский'],
  ['Swahili', 'sw', 'Суахили'],
  ['Swedish', 'sv', 'Шведский'],
  ['Tajik', 'tg', 'Таджикский'],
  ['Tamil', 'ta', 'Тамильский'],
  ['Telugu', 'te', 'Телугу'],
  ['Thai', 'th', 'Тайский'],
  ['Turkish', 'tr', 'Турецкий'],
  ['Turkmen', 'tk', 'Туркменский'],
  ['Ukrainian', 'uk', 'Украинский'],
  ['Urdu', 'ur', 'Урду'],
  ['Uzbek', 'uz', 'Узбекский'],
  ['Vietnamese', 'vi', 'Вьетнамский'],
  ['Welsh', 'cy', 'Валлийский'],
  ['Yiddish', 'yi', 'Идиш'],
  ['Yoruba', 'yo', 'Йоруба'],
  ['Zulu', 'zu', 'Зулу'],
];

const BY_NAME = new Map(ALL_LANGS.map((l) => [l[0].toLowerCase(), l]));
/**
 * И по КОДУ тоже. Профиль хранит английское имя («Spanish»), а матчинг отдаёт кандидата с
 * двухбуквенным `langs: ['es','ca']` — те же языки, записанные иначе. Поиск только по имени
 * возвращал бы «es» как есть, и карточка говорила бы «Говорит: es, ca».
 *
 * Имя выигрывает у кода при совпадении ключа: столкновений между полными именами и кодами ISO
 * нет (имя всегда длиннее двух букв), но порядок задан явно, чтобы это не зависело от списка.
 */
const BY_CODE = new Map(ALL_LANGS.map((l) => [l[1].toLowerCase(), l]));
const lookup = (key: string) => {
  const k = String(key).trim().toLowerCase();
  return BY_NAME.get(k) || BY_CODE.get(k);
};

/**
 * ИСПАНСКИЕ ИМЕНА — ОТДЕЛЬНОЙ КАРТОЙ ПО КОДУ ISO, а не четвёртым столбцом кортежа: кортеж читают и
 * другие места, и расширять его ради подписи значит трогать их все.
 */
const LANG_ES: Record<string, string> = {
  af: 'afrikáans', am: 'amárico', ar: 'árabe', az: 'azerí',
  be: 'bielorruso', bg: 'búlgaro', bn: 'bengalí', bs: 'bosnio',
  ca: 'catalán', cs: 'checo', cy: 'galés', da: 'danés',
  de: 'alemán', el: 'griego', en: 'inglés', es: 'español',
  et: 'estonio', eu: 'vasco', fa: 'persa', fi: 'finés',
  fr: 'francés', ga: 'irlandés', gl: 'gallego', gu: 'gujarati',
  ha: 'hausa', he: 'hebreo', hi: 'hindi', hr: 'croata',
  hu: 'húngaro', hy: 'armenio', id: 'indonesio', is: 'islandés',
  it: 'italiano', ja: 'japonés', jv: 'javanés', ka: 'georgiano',
  kk: 'kazajo', km: 'jemer', kn: 'kannada', ko: 'coreano',
  ku: 'kurdo', ky: 'kirguís', lo: 'lao', lt: 'lituano',
  lv: 'letón', mk: 'macedonio', ml: 'malayalam', mn: 'mongol',
  mr: 'maratí', ms: 'malayo', mt: 'maltés', my: 'birmano',
  ne: 'nepalí', nl: 'neerlandés', no: 'noruego', pa: 'punjabi',
  pl: 'polaco', ps: 'pastún', pt: 'portugués', ro: 'rumano',
  ru: 'ruso', si: 'cingalés', sk: 'eslovaco', sl: 'esloveno',
  so: 'somalí', sq: 'albanés', sr: 'serbio', sv: 'sueco',
  sw: 'suajili', ta: 'tamil', te: 'telugu', tg: 'tayiko',
  th: 'tailandés', tk: 'turcomano', tl: 'filipino', tr: 'turco',
  uk: 'ucraniano', ur: 'urdu', uz: 'uzbeko', vi: 'vietnamita',
  yi: 'yidis', yo: 'yoruba', zh: 'chino', zu: 'zulú',
};

/**
 * Флаг `ru` достался от времён двух языков и значит ровно «русский». Испанский он назвать не может,
 * поэтому спрашиваем язык интерфейса: нет испанского имени — остаётся английское, как и было.
 */
function plainName(l: Lang, ru: boolean): string {
  if (ru) return l[2];
  return (getLang() === 'es' && LANG_ES[l[1]]) || l[0];
}

/** Подпись языка на языке интерфейса, с флагом, если он у него есть. */
export function langName(key: string, ru: boolean): string {
  const l = lookup(key);
  if (!l) return key;                       // язык, дописанный человеком, показывается как есть
  const name = plainName(l, ru);
  return l[3] ? `${name} ${l[3]}` : name;
}

/** То же имя без флага — для строки профиля, где на борде флагов нет. */
export function langPlainName(key: string, ru: boolean): string {
  const l = lookup(key);
  return l ? plainName(l, ru) : key;
}

/**
 * Код ISO для сервера. Он держит `langs` двухбуквенными, и обрезать имя до двух символов нельзя:
 * Spanish → «sp», Ukrainian → «uk» случайно верно, а Estonian → «es», то есть испанский.
 * Незнакомое имя не превращается в код вовсе — лучше не отправить, чем отправить чужой язык.
 */
export function langCode(key: string): string | null {
  // Через тот же lookup: если на вход пришёл уже код («es»), вернуть его — это не «чужой язык»,
  // а тот же самый в другой записи, и терять его молча незачем.
  const l = lookup(key);
  return l ? l[1] : null;
}

/**
 * Поиск. Ищет и по русскому, и по английскому имени, и по коду: человек с русским интерфейсом
 * может набрать «swed» так же легко, как «швед».
 */
export function searchLangs(q: string): Lang[] {
  const s = q.trim().toLowerCase();
  if (!s) return ALL_LANGS;
  return ALL_LANGS.filter(
    (l) => l[0].toLowerCase().includes(s) || l[2].toLowerCase().includes(s) || l[1] === s
      // и по испанскому имени: чип подписан «alemán», значит и искать по «alem» должно находить
      || (LANG_ES[l[1]] || '').toLowerCase().includes(s)
  );
}
