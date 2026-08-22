/**
 * Доступ к полям профиля по реестру — единственный источник правды об именах.
 *
 * ЗАЧЕМ. Одна и та же вещь про человека называется в приложении и на сервере по-разному: то, что
 * здесь `city`, в строке пользователя `area`; `geo.coarseLat` там `lat`; `languages.comfortable` —
 * `langs`. Пока эти пары держались в голове, онбординг писал одно, профиль читал другое, и
 * расхождение находилось не при правке, а через неделю по жалобе.
 *
 * ПРАВИЛО. Ни один экран не пишет имя поля строкой. Экран называет ФАКТ («location.area»), а как он
 * называется здесь и как на сервере — знает реестр. Новое поле сначала описывается в
 * kleal-ms/shared/fields.json, потом появляется в коде, а не наоборот.
 *
 * Сам реестр лежит на стороне сервера и переносится сюда генератором (tools/sync_fields.py):
 * Metro не выпускает сборку за пределы каталога приложения, а копия, которую правят руками,
 * перестаёт быть копией в первый же день.
 */
import { FIELDS, FieldFact } from './fields.generated';
import { getState, set as setPath, get as getPath } from './state';
import { langCode } from './languages';

export type FactName = keyof typeof FIELDS & string;

function fact(name: string): FieldFact {
  const f = (FIELDS as any)[name];
  if (!f) {
    // Не молчим. Опечатка в имени факта иначе вернула бы undefined, и поле «просто не сохранилось»
    // — ровно тот класс расхождений, ради которого реестр и заведён.
    throw new Error(`поля «${name}» нет в реестре (kleal-ms/shared/fields.json)`);
  }
  return f;
}

/** Прочитать факт из профиля на устройстве. */
export function readFact<T = any>(name: FactName, fallback?: T): T {
  const f = fact(name);
  if (!f.app) return fallback as T;
  const v = getPath(f.app);
  return (v === undefined || v === null ? fallback : v) as T;
}

/** Записать факт в профиль на устройстве. Путь берётся из реестра, а не пишется на месте. */
export function writeFact(name: FactName, value: unknown): void {
  const f = fact(name);
  if (!f.app) throw new Error(`факт «${name}» приложение не хранит`);
  setPath(f.app, value);
}

/**
 * Преобразования «форма приложения → форма строки». Живут ЗДЕСЬ, в единственном месте, потому что
 * это и есть тот самый источник правды: реестр описывает форматы словами, а этот словарь — кодом.
 *
 *  — languages: приложение хранит полные названия (English), строка — коды ISO (en). Код берётся из
 *    справочника, а не обрезкой названия: Spanish дал бы «sp», Estonian — «es», то есть испанский.
 *  — interests: приложение хранит объект {explicit, unused, ...}, строка — плоский список НИЖНИМ
 *    регистром, без выключенных. Отправить объект как есть нельзя: update_user на сервере делает
 *    слепой row.update(), и строка получила бы вместо списка словарь — матчинг для этого человека
 *    сломался бы молча. Проверено по коду сервера, это не предположение.
 */
const TO_ROW: Record<string, (profile: any) => unknown> = {
  languages: (p) =>
    ((p.languages?.comfortable || []) as string[]).map(langCode).filter(Boolean),
  interests: (p) => {
    const off = new Set<string>((p.interests?.unused || []) as string[]);
    return ((p.interests?.explicit || []) as string[])
      .filter((x) => !off.has(x))
      .map((x) => String(x).trim().toLowerCase())
      .filter(Boolean);
  },
};

/**
 * Собрать патч для /api/onboarding/profile-update.
 *
 * Ключи — серверные, значения — из профиля на устройстве, форма — серверная (см. TO_ROW).
 * Непатчируемый факт сюда не пройдёт: сервер молча выбрасывает всё, чего нет в его белом списке,
 * и правка «применилась бы» только на экране.
 */
export function patchFor(names: FactName[]): Record<string, unknown> {
  const st = getState();
  const out: Record<string, unknown> = {};
  for (const name of names) {
    const f = fact(name);
    if (!f.patchable) throw new Error(`факт «${name}» не патчится через profile-update`);
    if (!f.row) continue;
    const conv = TO_ROW[name];
    const v = conv ? conv(st.profile) : f.app ? getPath(f.app) : undefined;
    if (v !== undefined && v !== null) out[f.row] = v;
  }
  return out;
}

/** Что поле молча делает с данными. Пусто — ничего неожиданного за ним не числится. */
export function quirks(name: FactName): string[] {
  return fact(name).quirks || [];
}

/** Имя человека — ключ, по которому сервер находит строку. Отдельно, потому что нужен почти везде. */
export function selfName(): string {
  return String(getState().profile.name || '');
}
