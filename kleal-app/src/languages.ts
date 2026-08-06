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

/** Подпись языка на языке интерфейса, с флагом, если он у него есть. */
export function langName(key: string, ru: boolean): string {
  const l = BY_NAME.get(String(key).toLowerCase());
  if (!l) return key;                       // язык, дописанный человеком, показывается как есть
  const name = ru ? l[2] : l[0];
  return l[3] ? `${name} ${l[3]}` : name;
}

/** То же имя без флага — для строки профиля, где на борде флагов нет. */
export function langPlainName(key: string, ru: boolean): string {
  const l = BY_NAME.get(String(key).toLowerCase());
  return l ? (ru ? l[2] : l[0]) : key;
}

/**
 * Код ISO для сервера. Он держит `langs` двухбуквенными, и обрезать имя до двух символов нельзя:
 * Spanish → «sp», Ukrainian → «uk» случайно верно, а Estonian → «es», то есть испанский.
 * Незнакомое имя не превращается в код вовсе — лучше не отправить, чем отправить чужой язык.
 */
export function langCode(key: string): string | null {
  const l = BY_NAME.get(String(key).toLowerCase());
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
  );
}
