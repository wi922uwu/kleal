/**
 * ОБЛОЖКА ЗАТЕИ — картинка, подходящая её теме.
 *
 * До этого на всех шести экранах, где у карточки есть широкая полоса сверху, стоял плоский
 * прямоугольник со значком-заглушкой: у затеи про падел и у затеи про настолки он был одинаковый.
 * Теперь у каждой из 51 подгруппы таксономии своя фотография.
 *
 * КАК ВЫБИРАЕТСЯ. Тема интента — ключ из той же таксономии, по которой ищет матчинг («padel»,
 * «boardgames», «vinyl»), поэтому подгруппа находится точным поиском по сгенерированной таблице:
 * ни модели, ни запроса к серверу. Если тем нет, в ход идёт категория фильтратора, потом тип
 * встречи, и только потом общая обложка. Врать картинкой нельзя: неизвестная тема получает
 * нейтральное «люди вместе», а не случайную фотографию чужого занятия.
 *
 * ГДЕ ЛЕЖАТ. На нашем сервере, `/covers/<подгруппа>.jpg`, 1200×675. Имя файла не меняется,
 * поэтому раздача разрешает кэшировать их на месяц: телефон скачивает каждую один раз.
 * Источник — Pexels (лицензия разрешает использование в продукте без указания авторства);
 * опись с авторами и ссылками лежит в kleal-ms/tools/covers_manifest.json.
 */
import { API_BASE } from './api';
import { LABEL_SUB, ROOT_SUB, TOPIC_SUB } from './covers.generated';

/** Обложка по умолчанию: люди вместе, без занятия. Ею закрывается всё неизвестное. */
const FALLBACK = 'casual';

/**
 * Категория фильтратора → подгруппа. Фильтратор отвечает одним из двадцати четырёх слов, и они
 * НЕ совпадают с ключами таксономии: «coffee» есть в обеих, а «esports» у фильтратора один, а в
 * таксономии их два (esports и console). Поэтому таблица явная, а не догадка по имени.
 */
const CATEGORY_SUB: Record<string, string> = {
  sports: 'team', gaming: 'console', esports: 'esports', tabletop: 'tabletop',
  music: 'listening', film_tv: 'screen', art_culture: 'visual', books: 'reading',
  food_drink: 'dining', coffee: 'coffee', nightlife: 'nightlife', outdoors: 'hiking',
  travel: 'travel', tech: 'engineering', startups: 'startups', career: 'career',
  languages: 'language', wellness: 'wellness', fashion: 'design',
  toys_collectibles: 'tabletop', pets: 'pets', photography: 'visual',
  dating: 'casual', social: 'casual', other: 'casual',
};

/** Тип встречи у матчинга — последняя зацепка перед общей обложкой. */
const TYPE_SUB: Record<string, string> = {
  sport: 'team', gaming: 'console', networking: 'career', language: 'language',
  dating: 'casual', social: 'casual', other: 'casual',
};

const norm = (v: unknown) => String(v || '').trim().toLowerCase();

/**
 * Подгруппа по одному слову.
 *
 * Три попытки, и вторая здесь главная: ключ реестра («padel»), подпись на языке человека
 * («Консоли», «Juegos de mesa») и корень без уточнения («sports»). Без подписей русское название
 * затеи не находило ничего и получало общую обложку.
 */
function subOfWord(word: string, allowRoot = true): string | null {
  const k = norm(word);
  const ascii = k.replace(/[^a-z0-9]+/g, '');
  const letters = k.replace(/[^0-9a-zа-яё]+/g, '');
  return (ascii && TOPIC_SUB[ascii])
    || (letters && LABEL_SUB[letters])
    || (allowRoot && ascii && ROOT_SUB[ascii])
    || null;
}

/**
 * Подгруппа по НАЗВАНИЮ целиком.
 *
 * Сперва вся фраза, потом куски по три и по два слова, и только в конце отдельные слова — потому
 * что подписи бывают из нескольких слов, а первое слово в них самое общее. «Juegos de mesa» это
 * настолки; ловясь на слове «Juegos», оно превращалось в «игры вообще» и получало картинку
 * киберспорта. Корень («игры», «спорт») пробуется в самую последнюю очередь по той же причине.
 */
function subOfTitle(title: string): string | null {
  const words = String(title || '').split(/[\s,.;:!?()"'«»—-]+/).filter(Boolean);
  if (!words.length) return null;
  for (let n = Math.min(4, words.length); n >= 2; n--) {
    for (let i = 0; i + n <= words.length; i++) {
      const s = subOfWord(words.slice(i, i + n).join(''), false);
      if (s) return s;
    }
  }
  for (const w of words) {
    const s = subOfWord(w, false);
    if (s) return s;
  }
  for (const w of words) {
    const s = subOfWord(w, true);
    if (s) return s;
  }
  return null;
}

/**
 * Подгруппа затеи. Порядок намеренный: своё точнее общего.
 * темы → категория → тип → слова названия → общая.
 */
export function subFor(intent: any): string {
  const i = intent?.intent && typeof intent.intent === 'object' ? intent.intent : intent;
  if (!i) return FALLBACK;

  const topics = Array.isArray(i.topics) ? i.topics : [];
  for (const t of topics) {
    const s = subOfWord(t);
    if (s) return s;
  }
  const cat = norm(i.category);
  if (cat && CATEGORY_SUB[cat]) return CATEGORY_SUB[cat];
  // Категория могла прийти и ключом реестра — тогда она точнее таблицы выше.
  const catSub = subOfWord(i.category);
  if (catSub) return catSub;

  // Название — последняя попытка перед общей обложкой: «Падел в субботу» находит падел.
  const byTitle = subOfTitle(String(i.title || i.subject || ''));
  if (byTitle) return byTitle;
  const type = norm(i.type);
  if (type && TYPE_SUB[type]) return TYPE_SUB[type];
  return FALLBACK;
}

/** Готовый адрес картинки для <Image source={{ uri }}>. */
export function coverFor(intent: any): string {
  return `${API_BASE}/covers/${subFor(intent)}.jpg`;
}

/** Адрес по известной подгруппе — для мест, где интента нет, а тема известна. */
export function coverOfSub(sub: string): string {
  const s = norm(sub);
  return `${API_BASE}/covers/${s && TOPIC_SUB[s] ? TOPIC_SUB[s] : s || FALLBACK}.jpg`;
}
