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
  reply = l;                       // выбрал язык интерфейса — на нём же отвечает и агент
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
  if (saved === 'ru' || saved === 'en') {
    current = saved;
    reply = saved;
  } else {
    // Русский только при явно русской локали; всё остальное — английский.
    const tag = String(Localization.getLocales?.()[0]?.languageCode || 'en').toLowerCase();
    current = tag === 'ru' ? 'ru' : 'en';
    // Испанскую систему интерфейс показать не может, а агент — может, и должен.
    reply = tag === 'ru' ? 'ru' : tag === 'es' ? 'es' : 'en';
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
