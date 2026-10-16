/**
 * Какой вид интересов показывать на шаге увлечений: v2 — спираль (по умолчанию), v1 — карта.
 *
 * Хранится на телефоне отдельным ключом, а НЕ в профиле: профиль уезжает на сервер при
 * регистрации, а это только выбор вида — серверу он ни к чему.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

export type InterestsView = 'v1' | 'v2';
const KEY = 'kleal.ui.interestsView';

export async function loadInterestsView(): Promise<InterestsView> {
  try {
    const v = await AsyncStorage.getItem(KEY);
    return v === 'v1' ? 'v1' : 'v2';
  } catch {
    return 'v2';
  }
}

export function saveInterestsView(v: InterestsView): void {
  AsyncStorage.setItem(KEY, v).catch(() => {});
}
