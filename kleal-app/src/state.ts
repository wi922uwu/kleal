/**
 * Состояние онбординга.
 *
 * Живёт вне React по той же причине, что и язык: его пишут обработчики шагов, а подписка нужна
 * только экранам. Профиль собирается по точечным путям (`set('geo.coarseLat', …)`) — ровно как в
 * вебовой реализации, чтобы форма объекта, которую ждёт /api/onboarding/register, не разошлась.
 */
import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

export type Profile = {
  name?: string;
  age?: number;
  gender?: string;
  city?: string;
  photo?: string;          // data URL, уходит в register и обратно не читается
  photoStatus?: string;
  geo?: {
    located?: boolean;
    coarseLat?: number;
    coarseLon?: number;
    comfortableAreas?: string[];
    maxDistanceKm?: number;
  };
  languages?: { comfortable?: string[] };
  interests?: { explicit?: string[] };
  safety?: { publicPlacesOnly?: boolean; hideExactLocation?: boolean; verifiedOnly?: boolean };
  permissions?: {
    useProfileForMatching?: boolean;
    allowAdjacentMatches?: boolean;
    rememberPreferences?: boolean;
  };
};

export type OnbState = {
  slide: number;
  step: number;            // индекс в SCRIPT; -1 = ещё не начали
  login: string | null;
  authMethod: string | null;
  profile: Profile;
};

const KEY = 'kleal.onboarding';

const empty = (): OnbState => ({ slide: 0, step: -1, login: null, authMethod: null, profile: {} });

let state: OnbState = empty();
const listeners = new Set<(s: OnbState) => void>();

function emit() {
  state = { ...state };
  listeners.forEach((fn) => fn(state));
  AsyncStorage.setItem(KEY, JSON.stringify(state)).catch(() => {});
}

export function getState(): OnbState {
  return state;
}

export function useOnb(): OnbState {
  const [s, setS] = useState(state);
  useEffect(() => {
    listeners.add(setS);
    return () => {
      listeners.delete(setS);
    };
  }, []);
  return s;
}

export async function restore(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (raw) state = { ...empty(), ...JSON.parse(raw) };
  } catch {
    /* повреждённое состояние — начинаем заново, это онбординг, терять нечего */
  }
  emit();
}

export function reset() {
  state = empty();
  emit();
}

export function patch(p: Partial<OnbState>) {
  state = { ...state, ...p };
  emit();
}

/** Точечная запись в профиль: set('geo.coarseLat', 41.4). Создаёт промежуточные объекты. */
export function set(path: string, value: unknown) {
  const parts = path.split('.');
  const next: any = { ...state.profile };
  let node = next;
  for (let i = 0; i < parts.length - 1; i++) {
    node[parts[i]] = { ...(node[parts[i]] || {}) };
    node = node[parts[i]];
  }
  node[parts[parts.length - 1]] = value;
  state = { ...state, profile: next };
  emit();
}

export function get(path: string): any {
  return path.split('.').reduce<any>((o, k) => (o == null ? undefined : o[k]), state.profile);
}

/**
 * Значения, которые ставились экраном «Твоя безопасность». Экрана больше нет, а значения нужны:
 * это были ЕДИНСТВЕННЫЕ писатели safety.publicPlacesOnly и permissions.useProfileForMatching, а
 * критерии готовности профиля читают именно их — без них полоса навсегда не доходила бы до конца.
 *
 * allowAdjacentMatches пишется явным true намеренно: все потребители читают его как `!== false`,
 * то есть «не задано» для них включено, — а переключатель рисовал `!!value`, то есть выключено.
 * Тумблер показывал человеку обратное тому, что делала система; тумблера нет, расхождения тоже.
 */
export function applyDefaults() {
  set('safety.publicPlacesOnly', true);       // собственная рекомендация Kleal, включена по умолчанию
  set('safety.hideExactLocation', false);
  set('safety.verifiedOnly', false);
  set('permissions.useProfileForMatching', true);
  set('permissions.allowAdjacentMatches', true);
  set('permissions.rememberPreferences', false);
}

/** Профиль для /api/onboarding/register — с фото. */
export function profileForRegister(): Profile {
  return { ...state.profile };
}

/** Профиль для привязки к логину — без фото: оно уже уехало в register и лежит файлом на сервере. */
export function profileForAttach(): Profile {
  const p: Profile = { ...state.profile };
  delete p.photo;
  return p;
}
