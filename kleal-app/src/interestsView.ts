/**
 * Какой вид интересов показывать на шаге увлечений: v1 — карта (по умолчанию с 18.10.2026, Иван:
 * «сделать map основной вместо helix»), v2 — спираль.
 *
 * Хранится на телефоне отдельным ключом, а НЕ в профиле: профиль уезжает на сервер при
 * регистрации, а это только выбор вида — серверу он ни к чему.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

export type InterestsView = 'v1' | 'v2';
// Ключ новый: прежний выбор «спираль», запомненный, когда она была по умолчанию, не должен
// перебивать новое решение — у всех стартует карта, а дальше телефон помнит выбор человека.
const KEY = 'kleal.ui.interestsView.2';

export async function loadInterestsView(): Promise<InterestsView> {
  try {
    const v = await AsyncStorage.getItem(KEY);
    return v === 'v2' ? 'v2' : 'v1';
  } catch {
    return 'v1';
  }
}

export function saveInterestsView(v: InterestsView): void {
  AsyncStorage.setItem(KEY, v).catch(() => {});
}
