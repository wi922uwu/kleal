/**
 * История разговоров с Kleal — на этом устройстве.
 *
 * ПОЧЕМУ НА УСТРОЙСТВЕ, А НЕ НА СЕРВЕРЕ. Сервер хранит тред только для «тонкого» режима
 * (`{user_id, message}`), а приложение разговаривает в режиме без состояния: оно само шлёт всю
 * переписку каждым ходом и само её держит. Ручки «дай список моих разговоров» у сервиса нет, и
 * заводить её значило бы править чужой файл, который сегодня уже дважды правили встречно. Здесь
 * тот же приём, что у пометок экрана «Сообщения»: отношение человека к своей переписке живёт на
 * телефоне (см. `MsgPrefs` в state.ts).
 *
 * ЧТО ЭТО ЗНАЧИТ ЧЕСТНО: переустановил приложение — история пропала. Это записано и на самом
 * экране, чтобы человек не считал её резервной копией.
 *
 * ОДИН ЗАХОД — ОДНА ЗАПИСЬ. Разговор кончается, когда с экрана ушли: следующий заход начинается
 * с чистой ленты, значит и в истории это другой разговор. Резать по времени было бы неправдой —
 * человек может думать над ответом три минуты, и это тот же разговор.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getState } from './state';

const KEY = 'kleal.history';
/** Сколько разговоров держим. Дальше — старое вытесняется: это история, а не архив. */
const CAP = 50;
/** Короче этого — не разговор, а случайный заход: открыл и вышел. */
const MIN_LINES = 2;

export type HistoryLine = { who: 'bot' | 'me'; text: string; at: string; hello?: boolean };
export type HistoryItem = {
  id: string;
  /**
   * Чья это запись. Обязательное поле, и появилось оно после настоящей утечки: история лежала под
   * одним ключом без владельца, и человек, вошедший под другим профилем, видел ЧУЖИЕ разговоры.
   * Сообщено с телефона. Ключ хранилища один, а принадлежность решается здесь.
   */
  owner: string;
  /** Метка времени начала, миллисекунды. По ней и сортируем. */
  startedAt: number;
  /** Чем занимались: шаг онбординга или свободный разговор. Показываем как подзаголовок. */
  topic: string;
  lines: HistoryLine[];
  /*
    ВОССТАНОВЛЕНИЕ РАЗГОВОРА (18.10.2026, Иван: «я должен уметь восстановить диалог»). Раньше запись
    хранила только текст пузырей — открыть её можно было лишь для чтения. Теперь рядом лежит всё, что
    нужно, чтобы продолжить: ходы для модели (тот же контекст), что распознал Kleal (окно затеи) и
    было ли окно открыто. Старые записи без этих полей открываются тоже: ходы собираются из реплик.
  */
  /** Последнее изменение, мс — по нему сортируем и подписываем дату. */
  updatedAt?: number;
  /** Ходы для модели в том виде, в каком их шлёт экран (role/content). */
  turns?: { role: string; content: string }[];
  /** Что распознал Kleal: фраза, заголовок и описание затеи, тема. */
  intent?: { what: string; seen: { title: string; desc: string } | null; topic: string; sheet: boolean };
  /** Из разговора ушли создавать затею. */
  created?: boolean;
  /** Откуда разговор: 'buddy' — чат с Kleal (его можно продолжить); без поля — старые записи. */
  source?: 'buddy' | 'onboarding';
};

let cache: HistoryItem[] | null = null;

/**
 * Кто сейчас в приложении. Логин, если вошли по почте; иначе токен сессии — он тоже свой у каждого.
 * Пусто — значит ещё никто: до входа история не показывается вовсе, и это правильнее, чем показать
 * её «ничьей».
 */
function owner(): string {
  const st: any = getState();
  return String(st?.login || st?.session || '').trim();
}

/** ВСЕ записи с диска, включая чужие. Только для внутреннего употребления — наружу не отдаётся. */
async function all(): Promise<HistoryItem[]> {
  if (cache) return cache;
  try {
    const raw = await AsyncStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    cache = Array.isArray(parsed) ? parsed : [];
  } catch {
    cache = [];
  }
  return cache;
}

/** История ТЕКУЩЕГО человека. Чужие записи не отдаём никогда, даже если они лежат рядом. */
export async function loadHistory(): Promise<HistoryItem[]> {
  const me = owner();
  if (!me) return [];
  return (await all()).filter((x) => x.owner === me);
}

/**
 * Дописать разговор. Пустые и совсем короткие не сохраняем: список из десяти «Привет, я Kleal»
 * без единого ответа — не история, а шум, среди которого не найти настоящий разговор.
 *
 * Повтор по `id` ЗАМЕНЯЕТ запись, а не добавляет вторую: экран может сохраниться дважды (уход и
 * размонтирование), и без замены каждый разговор двоился бы.
 */
export async function saveConversation(item: Omit<HistoryItem, 'owner'>): Promise<void> {
  if (!item?.id || (item.lines || []).length < MIN_LINES) return;
  const me = owner();
  if (!me) return;                    // некому принадлежать — не сохраняем
  const rows = await all();
  // Ограничение в CAP считается ПО ВЛАДЕЛЬЦУ: чужие записи не должны вытеснять мои и наоборот.
  const mine = [{ ...item, owner: me }, ...rows.filter((x) => x.owner === me && x.id !== item.id)]
    .sort((a, b) => (b.updatedAt || b.startedAt) - (a.updatedAt || a.startedAt))
    .slice(0, CAP);
  const next = [...mine, ...rows.filter((x) => x.owner !== me)];
  cache = next;
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Не сохранилось — не беда: история удобство, а не данные, ради которых стоит падать.
  }
}

/** Один разговор текущего человека — для восстановления. Чужой не отдаём. */
export async function getConversation(id: string): Promise<HistoryItem | null> {
  return (await loadHistory()).find((x) => x.id === id) || null;
}

/** Удалить один разговор текущего человека. */
export async function deleteConversation(id: string): Promise<void> {
  const me = owner();
  if (!me) return;
  const rows = (await all()).filter((x) => !(x.owner === me && x.id === id));
  cache = rows;
  try { await AsyncStorage.setItem(KEY, JSON.stringify(rows)); } catch { /* см. ниже */ }
}

/** Ходы для модели из реплик — для старых записей, где ходы не сохранялись. */
export function turnsOf(item: HistoryItem): { role: string; content: string }[] {
  if (item.turns && item.turns.length) return item.turns;
  return item.lines.map((l) => ({ role: l.who === 'me' ? 'user' : 'assistant', content: l.text }));
}

/** Стереть историю ТЕКУЩЕГО человека. Чужие записи не трогаем — они не наши, чтобы их удалять. */
export async function clearHistory(): Promise<void> {
  const me = owner();
  const rows = (await all()).filter((x) => x.owner !== me);
  cache = rows;
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(rows));
  } catch {
    /* см. выше */
  }
}

/**
 * Выход из аккаунта: стереть записи этого человека С УСТРОЙСТВА.
 *
 * Отбора по владельцу мало. Он закрывает показ, но переписка продолжает лежать на диске — а выход
 * из аккаунта человек понимает как «моих следов здесь не осталось». Зовётся из тех же мест, где
 * зовут `reset()`.
 */
export async function forgetOwner(who?: string): Promise<void> {
  const me = String(who || owner() || '').trim();
  if (!me) return;
  const rows = (await all()).filter((x) => x.owner !== me);
  cache = rows;
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(rows));
  } catch {
    /* см. выше */
  }
}
