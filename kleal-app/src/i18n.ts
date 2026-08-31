/**
 * Двуязычие. В вебовом прототипе это глобальная функция T(ru, en) — здесь ровно она же, чтобы
 * перенос строк был механическим и обе реализации нельзя было незаметно развести.
 *
 * Язык хранится вне React: T() зовут из мест, где хука нет (данные шагов, форматтеры), а
 * подписка нужна только экранам.
 */
import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Localization from 'expo-localization';

/**
 * Языки интерфейса — ru и en. Испанский пока живёт ОТДЕЛЬНО (см. replyLang): интерфейс на нём
 * не переведён, а вот агент и сводка на нём говорить обязаны — человеку с испанской системой
 * незачем читать рассказ о себе по-английски.
 */
export type Lang = 'ru' | 'en';

/** Язык, на котором отвечает агент и пишется сводка. Их три, и они настоящие. */
export type ReplyLang = 'ru' | 'en' | 'es';

let reply: ReplyLang = 'en';
/**
 * Язык, который даёт СИСТЕМА телефона. Хранится отдельно от выбранного и не затирается им.
 *
 * Без этого испанский агент гас навсегда. Испанцу интерфейс достаётся английским (перевода нет), а
 * агент — испанским. Стоило один раз тронуть переключатель языка, и `setLang` записывал `reply`
 * равным интерфейсу: испанский пропадал, сохранялся в память как «en», и при следующем запуске
 * `initLang` брал сохранённое и уже никогда не перечитывал систему. Вернуть можно было только
 * переустановкой.
 */
let systemReply: ReplyLang = 'en';

/** Что говорит система телефона. `ca-ES` и прочие испанские варианты тоже считаются испанскими. */
function localeReply(): ReplyLang {
  const l = Localization.getLocales?.()[0];
  const tag = String(l?.languageCode || 'en').toLowerCase();
  if (tag === 'ru') return 'ru';
  if (tag === 'es') return 'es';
  // Каталонский, галисийский и баскский телефоны — это Испания: агенту там уместнее испанский,
  // чем английский. Интерфейс от этого не меняется, он и так английский.
  const region = String((l as any)?.regionCode || '').toUpperCase();
  if (region === 'ES') return 'es';
  return 'en';
}

/**
 * Язык ответов агента. Отличается от языка интерфейса ровно в одном случае — испанская система:
 * кнопки останутся английскими (перевода ещё нет), но Kleal заговорит по-испански.
 */
export function replyLang(): ReplyLang {
  return reply;
}

export function setReplyLang(l: ReplyLang) {
  reply = l;
}

const KEY = 'kleal.lang';
let current: Lang = 'en';
const listeners = new Set<(l: Lang) => void>();

export function T(ru: string, en: string): string {
  return current === 'ru' ? ru : en;
}

export function getLang(): Lang {
  return current;
}

/**
 * Русское согласование с числом: «1 ответ», «2 ответа», «5 ответов».
 *
 * Живёт здесь, а не по месту, потому что арифметика у него всегда одна, а ошибиться в ней легко:
 * одиннадцать ведёт себя не как один, а сто двадцать один — как один. В проекте эта же выкладка
 * уже переписана от руки в HOME.invitesLeft и HOME.going; новые счётчики берут её отсюда, и туда
 * её можно свести тем же вызовом.
 */
export function plural(n: number, one: string, few: string, many: string): string {
  const t = n % 10, h = n % 100;
  if (t === 1 && h !== 11) return one;
  if (t >= 2 && t <= 4 && (h < 10 || h >= 20)) return few;
  return many;
}

export function setLang(l: Lang) {
  if (l === current) return;
  current = l;
  /*
    ВЫБОР ИНТЕРФЕЙСА НЕ ОТМЕНЯЕТ ЯЗЫК СИСТЕМЫ. Выбрал русский — агент говорит по-русски, это и
    правда выбор. А «английский» в этом переключателе означает не «говори по-английски», а «нет
    моего языка»: испанцу выбирать нечего, у него в списке только RU и EN. Поэтому на английском
    агент возвращается к системному языку, и испанский переживает переключение.
  */
  reply = l === 'ru' ? 'ru' : systemReply;
  AsyncStorage.setItem(KEY, l).catch(() => {});
  listeners.forEach((fn) => fn(l));
}

/** Прочитать сохранённый язык, иначе взять системный. Зовётся один раз при старте. */
export async function initLang(): Promise<Lang> {
  let saved: string | null = null;
  try {
    saved = await AsyncStorage.getItem(KEY);
  } catch {
    saved = null;
  }
  // Систему читаем ВСЕГДА, а не только когда сохранённого нет: язык агента выводится из неё, и
  // сохранённый выбор интерфейса его не заменяет.
  systemReply = localeReply();
  if (saved === 'ru' || saved === 'en') {
    current = saved;
    reply = saved === 'ru' ? 'ru' : systemReply;
  } else {
    // Русский только при явно русской локали; всё остальное — английский.
    current = systemReply === 'ru' ? 'ru' : 'en';
    // Испанскую систему интерфейс показать не может, а агент — может, и должен.
    reply = systemReply;
  }
  listeners.forEach((fn) => fn(current));
  return current;
}

/** Подписка для экранов: перерисоваться при смене языка. */
export function useLang(): Lang {
  const [l, setL] = useState<Lang>(current);
  useEffect(() => {
    listeners.add(setL);
    return () => {
      listeners.delete(setL);
    };
  }, []);
  return l;
}
