/**
 * «Просто скажи, что изменить» — второй путь правки сводки, кадр GR.12a борда «0 · Create the intent»
 * (Figma 6864:119674): «Change it yourself, or just tell me what to change — the time, the place or
 * who you’re looking for». Заметка к кадру: «написать, что поменять, и Kleal обновит сводку GR.12».
 *
 * РАЗБОР ЗДЕСЬ, НА УСТРОЙСТВЕ, И ОН УЗКИЙ НАМЕРЕННО. Ни одна ручка сервера не превращает фразу
 * в поля сводки: построитель интента уточняет только тему (см. buddy.intentBuild), а /api/agent/plan
 * сразу ищет людей. Поэтому понимаются ровно те правки, которые читаются однозначно, — день, время,
 * пол и возраст, размер группы, радиус и название, — на трёх языках интерфейса. Всё остальное Kleal
 * честно называет непонятым и предлагает поправить руками; угадывать за человека нельзя.
 *
 * Место словами не правится: адрес без карты — это догадка геокодера, и ошибиться на ней легко.
 * Для места есть карта в «Edit it myself».
 */

export type TalkDraft = {
  size?: '1:1' | 'group';
  groupSize?: number;
  date: string;
  minutes: number;
  sex?: string;
  minAge: number;
  maxAge: number;
  radiusKm: number;
};

export type TalkResult = {
  /** Что поменять в черновике. Пусто — менять нечего (см. `problem`). */
  patch: Partial<TalkDraft>;
  /** Новое название затеи, если его назвали. */
  title?: string;
  /** Какие части тронуты — для ответа Kleal. */
  touched: ('when' | 'who' | 'size' | 'where' | 'what')[];
  /**
   * Понятно, но выполнить нельзя: время прошло, группа больше бесплатного предела, формат
   * меняется только новым интентом. Тогда `patch` пуст, а Kleal говорит, почему.
   */
  problem?: 'past' | 'plus' | 'format';
};

const pad = (n: number) => String(n).padStart(2, '0');
export const dateKeyOf = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const dayOf = (key: string) => new Date(key + 'T12:00:00');

// ------------------------------------------------------------------ словари

/** Дни недели по номеру getDay(): 0 — воскресенье. Русские — в обоих падежах («в пятницу»). */
const WEEKDAYS: [RegExp, number][] = [
  [/\b(sunday|sun)\b|воскресень|\bdomingo\b/, 0],
  [/\b(monday|mon)\b|понедельник|\blunes\b/, 1],
  [/\b(tuesday|tue|tues)\b|вторник|\bmartes\b/, 2],
  [/\b(wednesday|wed)\b|сред[уаы]|mi[eé]rcoles/, 3],
  [/\b(thursday|thu|thurs)\b|четверг|\bjueves\b/, 4],
  [/\b(friday|fri)\b|пятниц|\bviernes\b/, 5],
  [/\b(saturday|sat)\b|суббот|s[aá]bado/, 6],
];

const MONTHS: [RegExp, number][] = [
  [/\b(january|jan)\b|январ|\benero\b/, 0],
  [/\b(february|feb)\b|феврал|\bfebrero\b/, 1],
  [/\b(march|mar)\b|март|\bmarzo\b/, 2],
  [/\b(april|apr)\b|апрел|\babril\b/, 3],
  [/\bmay\b|ма[яй](?![а-я])|\bmayo\b/, 4],
  [/\b(june|jun)\b|июн|\bjunio\b/, 5],
  [/\b(july|jul)\b|июл|\bjulio\b/, 6],
  [/\b(august|aug)\b|август|\bagosto\b/, 7],
  [/\b(september|sept|sep)\b|сентябр|\bse?ptiembre\b/, 8],
  [/\b(october|oct)\b|октябр|\boctubre\b/, 9],
  [/\b(november|nov)\b|ноябр|\bnoviembre\b/, 10],
  [/\b(december|dec)\b|декабр|\bdiciembre\b/, 11],
];

/** Время словами — среднее значение части дня; уточнят числом, если нужно другое. */
const PARTS: [RegExp, number][] = [
  [/\bnoon\b|\bmidday\b|полдень|mediod[ií]a/, 12 * 60],
  [/\bmorning\b|утром|утро|por la ma[nñ]ana/, 10 * 60],
  [/\bafternoon\b|днём|днем|por la tarde/, 15 * 60],
  [/\btonight\b|\bevening\b|вечером|вечер|por la noche|esta noche/, 19 * 60],
];

/*
  КИРИЛЛИЦА И \b НЕ ДРУЖАТ: без флага u граница слова видит только латиницу, и «\bв\b» не находит
  предлог «в» вовсе. Поэтому у русских слов граница — пробел или начало строки, а не \b.
*/
const FEMALE = /\b(women|woman|girls?|female|ladies)\b|девушк|женщин|женск|\bchicas?\b|\bmujer(es)?\b/;
const MALE = /\b(men|man|guys?|male|boys?)\b|парн|мужчин|мужск|\bchicos?\b|\bhombres?\b/;
const ANY_SEX = /\b(anyone|anybody|any gender|everyone)\b|кто угодно|любого пола|любой пол|без разницы|cualquiera|da igual/;
const ANY_AGE = /\bany age\b|любой возраст|любого возраста|cualquier edad/;

// ------------------------------------------------------------------ разбор

/**
 * Разобрать реплику. `null` — не понято ничего: Kleal скажет, что можно попросить, и предложит
 * поправить руками. `now` передаётся явно, чтобы разбор проверялся без часов устройства.
 */
export function parseIntentChange(text: string, draft: TalkDraft, now = new Date(), freeMax = 5): TalkResult | null {
  let t = ' ' + String(text || '').toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, ' ') + ' ';
  const patch: Partial<TalkDraft> = {};
  const touched = new Set<TalkResult['touched'][number]>();
  let title: string | undefined;
  let problem: TalkResult['problem'];

  // --- название: «call it …», «назови …», «llámalo …» — забирает остаток фразы целиком
  const named = String(text || '').match(
    /(?:call it|rename it to|rename to|name it|назови(?:\s+её|\s+ее|\s+это)?|переименуй в|пусть называется|ll[aá]malo|ponle de nombre)\s*[:«"“]?\s*([^»"”]+)[»"”]?\s*$/i,
  );
  if (named && named[1].trim().length >= 2) {
    title = named[1].trim().replace(/[.!]+$/, '');
    title = title.charAt(0).toUpperCase() + title.slice(1);
    touched.add('what');
    // Остаток фразы — название целиком; разбирать в нём дни и числа нельзя («назови Пятничный бег»).
    t = ' ' + String(text || '').slice(0, named.index || 0).toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, ' ') + ' ';
  }

  // --- день
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
  let day: Date | null = null;
  let m: RegExpMatchArray | null;
  if (/day after tomorrow|послезавтра|pasado ma[nñ]ana/.test(t)) {
    day = new Date(today.getTime() + 2 * 864e5);
    t = t.replace(/day after tomorrow|послезавтра|pasado ma[nñ]ana/, ' ');
  } else if (/\btomorrow\b|завтра|\bma[nñ]ana\b(?! por)/.test(t.replace(/por la ma[nñ]ana/, ''))) {
    day = new Date(today.getTime() + 864e5);
  } else if (/\btoday\b|\btonight\b|сегодня|\bhoy\b|esta noche/.test(t)) {
    day = today;
  }
  // число и месяц: «24 july», «july 24», «24 июля», «24 de julio»
  if (!day) {
    for (const [re, mon] of MONTHS) {
      const mm = t.match(new RegExp(`(\\d{1,2})\\s*(?:de\\s+)?(?:${re.source})|(?:${re.source})\\s*(\\d{1,2})\\b`));
      if (mm) {
        const dnum = Number(mm.slice(1).find((x) => x && /^\d{1,2}$/.test(x)));
        if (dnum >= 1 && dnum <= 31) {
          day = new Date(now.getFullYear(), mon, dnum, 12);
          if (day < today) day = new Date(now.getFullYear() + 1, mon, dnum, 12);
          t = t.replace(mm[0], ' ');
        }
        break;
      }
    }
  }
  /*
    «24/07» и «24.07». Через точку пишут и время («в 19.30»), поэтому точка читается датой, только
    если вторая часть — месяц (≤ 12) и перед числом нет предлога времени («в», «at», «a las»).
  */
  if (!day && (m = t.match(/(^|\s)(в|at|a las?|к)?\s*(\d{1,2})([./])(\d{1,2})(?![\d:])(?!\s*(?:am|pm|a\.m|p\.m|ч))/))) {
    const dn = Number(m[3]), mn = Number(m[5]);
    const timey = m[4] === '.' && !!m[2];
    if (!timey && dn >= 1 && dn <= 31 && mn >= 1 && mn <= 12) {
      day = new Date(now.getFullYear(), mn - 1, dn, 12);
      if (day < today) day = new Date(now.getFullYear() + 1, mn - 1, dn, 12);
      t = t.replace(m[0], ' ' + (m[2] || '') + ' ');
    }
  }
  if (!day) {
    for (const [re, wd] of WEEKDAYS) {
      if (re.test(t)) {
        const next = /\bnext\b|следующ|pr[oó]xim/.test(t);
        let add = (wd - today.getDay() + 7) % 7;
        if (next && add === 0) add = 7;
        else if (next && add < 7 && /\bnext week\b/.test(t)) add += 7;
        day = new Date(today.getTime() + add * 864e5);
        break;
      }
    }
  }

  // --- время
  let minutes: number | null = null;
  const pm = (h: number, mark: string) => {
    const s = mark.toLowerCase();
    if (/p\.?m|вечера|дня|de la tarde|de la noche/.test(s) && h < 12) return h + 12;
    if (/a\.?m|утра|de la ma/.test(s) && h === 12) return 0;
    if (/ночи/.test(s) && h === 12) return 0;
    return h;
  };
  if ((m = t.match(/\b([01]?\d|2[0-3])\s*[:.h]\s*([0-5]\d)\s*(a\.?m\.?|p\.?m\.?|утра|вечера|дня|ночи|de la (?:ma[nñ]ana|tarde|noche))?/))) {
    minutes = pm(Number(m[1]), m[3] || '') * 60 + Number(m[2]);
  } else if ((m = t.match(/\b(1[0-2]|0?[1-9])\s*(a\.?m\.?|p\.?m\.?)(?=\W)/))) {
    minutes = pm(Number(m[1]), m[2]) * 60;
  } else if ((m = t.match(/(?:\bat\b|\sв|\sк|\ba las?\b|\baround\b)\s+([01]?\d|2[0-3])(?![\d.:/])\s*(утра|вечера|дня|ночи|de la (?:ma[nñ]ana|tarde|noche)|o'?clock|час[а-я]*)?/))) {
    let h = pm(Number(m[1]), m[2] || '');
    // «в 7» без уточнения — вечер: встречи в семь утра бывают, но реже, чем «в 7» вечера
    if (!m[2] && h >= 1 && h <= 7) h += 12;
    minutes = h * 60;
  } else if ((m = t.match(/(\d{1,2})\s*(?:вечера|утра|дня|ночи)/))) {
    minutes = pm(Number(m[1]), m[0]) * 60;
  } else {
    for (const [re, mins] of PARTS) if (re.test(t)) { minutes = mins; break; }
  }

  if (day || minutes != null) {
    const dk = day ? dateKeyOf(day) : draft.date;
    const mins = minutes != null ? minutes : draft.minutes;
    const when = dayOf(dk);
    when.setHours(Math.floor(mins / 60), mins % 60, 0, 0);
    if (when.getTime() < now.getTime()) {
      problem = 'past';
    } else {
      if (dk !== draft.date) patch.date = dk;
      if (mins !== draft.minutes) patch.minutes = mins;
      touched.add('when');
    }
  }

  // --- кого ищем
  const fem = FEMALE.test(t), mal = MALE.test(t);
  if (ANY_SEX.test(t) || (fem && mal)) { patch.sex = 'Any'; touched.add('who'); }
  else if (fem) { patch.sex = 'Female'; touched.add('who'); }
  else if (mal) { patch.sex = 'Male'; touched.add('who'); }
  if (ANY_AGE.test(t)) { patch.minAge = 0; patch.maxAge = 0; touched.add('who'); }
  else if ((m = t.match(/(?:^|[^\d:.])(1[89]|[2-7]\d)\s*(?:-|–|—|to|до|a|y|and)\s*(1[89]|[2-8]\d)(?![\d:.])/))) {
    const lo = Number(m[1]), hi = Number(m[2]);
    if (lo < hi) { patch.minAge = lo; patch.maxAge = hi; touched.add('who'); }
  } else if ((m = t.match(/(?:over|older than|старше|m[aá]s de|mayores de)\s*(1[89]|[2-7]\d)(?!\d)/))) {
    patch.minAge = Number(m[1]); patch.maxAge = 80; touched.add('who');
  } else if ((m = t.match(/(?:under|younger than|младше|menos de|menores de)\s*(1[89]|[2-8]\d)(?!\d)/))) {
    patch.minAge = 18; patch.maxAge = Number(m[1]); touched.add('who');
  }

  // --- сколько человек: формат (1:1 ↔ группа) отсюда не меняется — это новый интент (GR.12b)
  if (/one[- ]on[- ]one|\b1:1\b|один на один|вдвоём|вдвоем|uno a uno|a solas/.test(t) && draft.size === 'group') {
    problem = problem || 'format';
  } else if ((m = t.match(/(?:group of|grupo de)\s*(\d{1,2})(?!\d)|(\d{1,2})\s*(?:people|persons|человек|чел|personas)/))) {
    const n = Number(m[1] || m[2]);
    if (draft.size === 'group' && n >= 3) {
      if (n > freeMax) problem = problem || 'plus';
      else if (n !== draft.groupSize) { patch.groupSize = n; touched.add('size'); }
      else touched.add('size');
    } else if (draft.size !== 'group' && n >= 3) {
      problem = problem || 'format';
    }
  }

  // --- радиус
  if ((m = t.match(/(?:^|[^\d])(\d{1,3})\s*(?:km|км|kil[oó]metros?|километр)(?![a-z])/))) {
    const km = Math.max(1, Math.min(50, Number(m[1])));
    if (km !== draft.radiusKm) patch.radiusKm = km;
    touched.add('where');
  }

  if (!touched.size && !problem) return null;
  return { patch, title, touched: [...touched], problem: Object.keys(patch).length || title ? undefined : problem };
}
