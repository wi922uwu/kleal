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

export type Lang = 'ru' | 'en';

const KEY = 'kleal.lang';
let current: Lang = 'en';
const listeners = new Set<(l: Lang) => void>();

export function T(ru: string, en: string): string {
  return current === 'ru' ? ru : en;
}

export function getLang(): Lang {
  return current;
}

export function setLang(l: Lang) {
  if (l === current) return;
  current = l;
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
  } else {
    // Русский только при явно русской локали; всё остальное — английский.
    const tag = String(Localization.getLocales?.()[0]?.languageCode || 'en').toLowerCase();
    current = tag === 'ru' ? 'ru' : 'en';
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
