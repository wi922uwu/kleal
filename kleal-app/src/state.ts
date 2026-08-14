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
  /** Страна отдельным полем: в `city` теперь лежит город, и смешивать их нельзя — поиск читает
   *  именно город (§5.3, location_block.city). */
  country?: string;
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
  /** Часовой пояс именем зоны (Europe/Madrid). Спрашивать нечего — устройство знает сам. */
  tz?: string;
  permissions?: {
    useProfileForMatching?: boolean;
    allowAdjacentMatches?: boolean;
    rememberPreferences?: boolean;
  };
};

/**
 * Пометки экрана «Сообщения», СВОИ для этого устройства: без уведомлений, архив, «покинул чат»,
 * когда тред открывали в последний раз (для бейджей), спрятанные подсказки и карточки.
 * На сервере их нет намеренно: это отношение человека к списку, а не состояние разговора.
 */
export type MsgPrefs = {
  muted?: string[];
  archived?: string[];
  left?: string[];
  seen?: Record<string, number>;
  noNudge?: string[];
  hiddenInvites?: string[];
};

export type OnbState = {
  slide: number;
  step: number;            // индекс в SCRIPT; -1 = ещё не начали
  login: string | null;
  authMethod: string | null;
  msg?: MsgPrefs;
  /**
   * Онбординг пройден и профиль записан на сервере.
   *
   * Отдельный флаг, а не «у профиля всё заполнено»: по заполненности не отличить того, кто
   * закончил, от того, кто дошёл до последнего шага и закрыл приложение. Разница видна человеку —
   * первого при следующем запуске надо пускать в приложение, а не в анкету.
   */
  done: boolean;
  profile: Profile;
};

const KEY = 'kleal.onboarding';

const empty = (): OnbState => ({ slide: 0, step: -1, login: null, authMethod: null, done: false, profile: {} });

let state: OnbState = empty();
const listeners = new Set<(s: OnbState) => void>();

/**
 * Пока restore() не дочитал диск, писать на него нельзя: экран, успевший тронуть состояние в
 * первые миллисекунды (markSeen из переписки), сохранял ПУСТОЙ стор поверх настоящего — пропадали
 * пометки сообщений, а в худшей гонке мог пропасть и профиль. Память обновляется всегда; диск
 * догоняет первой записью после восстановления.
 */
let restored = false;

function emit() {
  state = { ...state };
  listeners.forEach((fn) => fn(state));
  if (restored) AsyncStorage.setItem(KEY, JSON.stringify(state)).catch(() => {});
}

export function getState(): OnbState {
  return state;
}

/**
 * Подписка на состояние ВНЕ React — для того, что живёт дольше экрана.
 *
 * Тем же набором слушателей, что и useOnb: сторож сводки должен видеть правку независимо от того,
 * с какого экрана она пришла и открыт ли вообще профиль.
 */
export function subscribe(fn: (s: OnbState) => void): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
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
  } finally {
    restored = true;
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

export function msgPrefs(): MsgPrefs {
  return state.msg || {};
}

/** Правка пометок сообщений одной функцией: setMsgPrefs((m) => ({ ...m, muted: [...] })). */
export function setMsgPrefs(fn: (m: MsgPrefs) => MsgPrefs) {
  state = { ...state, msg: fn(state.msg || {}) };
  emit();
}

/** Тред открыт — бейдж на нём гаснет. Зовётся из переписки, а не из списка: списку виднее нельзя. */
export function markSeen(who: string) {
  const key = String(who || '').trim().toLowerCase();
  if (!key) return;
  setMsgPrefs((m) => ({ ...m, seen: { ...(m.seen || {}), [key]: Date.now() / 1000 } }));
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

/**
 * Слить профиль, вернувшийся от модели, с тем, что уже собрано.
 *
 * Модель отдаёт профиль ЦЕЛИКОМ, собранный из истории разговора, — и раньше он писался поверх.
 * Пока разговор начинался со всех интересов сразу, это сходило с рук. Но «Добавить интересы» из
 * профиля намеренно заводит разговор только про НОВОЕ, чтобы не переспрашивать про уже
 * обсуждённое, — и профиль из такого разговора содержит одну йогу. Проверено: кофе, футбол и
 * испанский исчезали молча.
 *
 * Поэтому слияние, а не замена: скаляры модель уточняет, списки только пополняются. Убрать
 * что-либо из профиля можно на его же экране, явно, — но не побочным эффектом разговора.
 */
export function mergeProfile(cur: Profile, incoming: any): Profile {
  const uniq = (a: any[], b: any[]) => Array.from(new Set([...(a || []), ...(b || [])]));
  const out: any = { ...cur, ...(incoming || {}) };

  out.interests = {
    ...(cur.interests || {}),
    ...((incoming && incoming.interests) || {}),
    explicit: uniq(
      (cur.interests || {}).explicit || [],
      ((incoming && incoming.interests) || {}).explicit || []
    ),
    // Роли и опыт — словари по интересу: новые ключи добавляются, старые остаются.
    roles: { ...((cur.interests as any) || {}).roles, ...(((incoming || {}).interests || {}).roles) },
    experienceByInterest: {
      ...((cur.interests as any) || {}).experienceByInterest,
      ...(((incoming || {}).interests || {}).experienceByInterest),
    },
  };

  out.languages = {
    ...(cur.languages || {}),
    ...((incoming && incoming.languages) || {}),
    comfortable: uniq(
      (cur.languages || {}).comfortable || [],
      ((incoming && incoming.languages) || {}).comfortable || []
    ),
  };

  out.geo = { ...(cur.geo || {}), ...((incoming && incoming.geo) || {}) };
  out.safety = { ...(cur.safety || {}), ...((incoming && incoming.safety) || {}) };
  out.permissions = { ...(cur.permissions || {}), ...((incoming && incoming.permissions) || {}) };
  if (cur.photo) out.photo = cur.photo;          // фото модель не видит и вернуть не может

  return out as Profile;
}

/** Профиль для /api/onboarding/register — с фото. */
export function profileForRegister(): Profile {
  return { ...state.profile, tz: deviceTz() };
}

/** Профиль для привязки к логину — без фото: оно уже уехало в register и лежит файлом на сервере. */
export function profileForAttach(): Profile {
  const p: Profile = { ...state.profile, tz: deviceTz() };
  delete p.photo;
  return p;
}

/**
 * Часовой пояс устройства. Такая же функция есть в src/intent.ts, и импорт тут намеренно не
 * сделан: state.ts не тянет НИ ОДНОГО модуля приложения (только react и хранилище) — состояние
 * обязано подниматься раньше всего остального. Импорт ради трёх строк Intl тянул бы за собой
 * i18n со всеми словарями.
 */
function deviceTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  } catch {
    return '';
  }
}
