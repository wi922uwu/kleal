/**
 * ВСТРЕЧА В КАЛЕНДАРЬ (владелец 18.10.2026: «на этапе создания плана между людьми запись в гугл или
 * встроенный календарь, кнопку»).
 *
 * Два пути, оба без доступа к календарю человека:
 *   • системный — родное окно «Новое событие» (iPhone — Календарь, Android — календарь по умолчанию),
 *     человек сам жмёт «Добавить». Модуль `expo-calendar/legacy`: новый объектный API в Expo Go
 *     не собран (там заглушка ExpoGoCalendarNextStub), а окно из legacy работает и в Expo Go.
 *   • Google — ссылка на форму события Google Календаря (приложение или сайт).
 *
 * Адрес и ссылку на звонок сюда не кладём, пока их не открыл сервер: в календарь уходит то, что
 * человек уже видит на экране плана (район, а не точный адрес до подтверждения).
 */
import { Linking } from 'react-native';
import * as Calendar from 'expo-calendar/legacy';
import { T } from './i18n';

export type CalEvent = {
  title: string;
  startMs: number;
  endMs: number;
  location?: string;
  notes?: string;
};

/** Длительность, когда сервер её не прислал: встреча «на вечер», а не на весь день. */
export const DEFAULT_MINUTES = 90;

export const CAL = {
  add: () => T('В календарь', 'Add to calendar', 'Al calendario'),
  added: () => T('В календаре', 'In your calendar', 'En el calendario'),
  google: () => T('Google', 'Google', 'Google'),
  failed: () => T('Не открылся календарь', "Couldn't open the calendar", 'No se abrió el calendario'),
  title: (what: string, who: string) => T(`${what} · ${who}`, `${what} · ${who}`, `${what} · ${who}`),
  notes: () => T('Встреча из Kleal. Адрес и ссылка — в приложении.', 'A Kleal meetup. Address and link are in the app.',
    'Quedada de Kleal. La dirección y el enlace están en la app.'),
};

/** «20261018T183000Z» — время Google в UTC. */
const gStamp = (ms: number) => new Date(ms).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');

export function googleCalendarUrl(e: CalEvent): string {
  const q = new URLSearchParams({
    action: 'TEMPLATE',
    text: e.title,
    dates: `${gStamp(e.startMs)}/${gStamp(e.endMs)}`,
    ...(e.location ? { location: e.location } : {}),
    ...(e.notes ? { details: e.notes } : {}),
  });
  return `https://calendar.google.com/calendar/render?${q.toString()}`;
}

/** Системное окно. `saved` — iPhone подтвердил; Android всегда отвечает `done`, считаем добавленным. */
export async function addToSystemCalendar(e: CalEvent): Promise<'saved' | 'canceled' | 'failed'> {
  try {
    const r = await Calendar.createEventInCalendarAsync({
      title: e.title,
      startDate: new Date(e.startMs),
      endDate: new Date(e.endMs),
      ...(e.location ? { location: e.location } : {}),
      ...(e.notes ? { notes: e.notes } : {}),
      // Напоминание за час: без него событие молча лежит в календаре, а встречу забывают.
      alarms: [{ relativeOffset: -60 }],
    });
    return r.action === 'canceled' || r.action === 'deleted' ? 'canceled' : 'saved';
  } catch {
    return 'failed';
  }
}

export async function openGoogleCalendar(e: CalEvent): Promise<boolean> {
  try { await Linking.openURL(googleCalendarUrl(e)); return true; } catch { return false; }
}
