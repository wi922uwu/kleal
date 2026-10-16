/**
 * Вход через чужой сервис — Google и Apple. Один код на оба: различается только слово в адресе.
 *
 * ПОЧЕМУ ЧЕРЕЗ БРАУЗЕР, А НЕ НАТИВНОЙ КНОПКОЙ. Приложение живёт в Expo Go, а и Google, и Apple
 * принимают адресом возврата только https или схему, зарегистрированную на СВОЙ идентификатор
 * приложения. У Expo Go идентификатор чужой (`host.exp.Exponent`), адрес возврата — `exp://…`,
 * и такой ни один из них не примет. Поэтому телефон открывает системный браузер на НАШЕЙ ручке,
 * сервис возвращается на НАШ https-адрес, сервер меняет код на почту и уводит браузер обратно в
 * приложение по его собственной ссылке — с одноразовой меткой вместо токена
 * (`services/onboarding/google_auth.py`, `apple_auth.py`, общее — `oauth_common.py`).
 *
 * Здесь нет ни одного нового пакета: ссылку открывает `Linking`, он же ловит возврат.
 * `expo-auth-session` и нативный вход потребовали бы дев-сборки, а она отменяет Expo Go — AGENTS.md.
 *
 * Модуль НИЧЕГО не знает про состояние приложения: он отдаёт ровно тот же ответ, что и вход по
 * почтовому коду, а класть его в профиль и сессию — дело экрана.
 */
import * as Linking from 'expo-linking';
import { API_BASE, auth } from './api';

/** Ответ сервера — тот же, что у `/api/auth/code/verify`: на сервере это одна функция. */
export type AuthResult = {
  ok?: boolean;
  error?: string;
  token?: string;
  login?: string;
  email?: string;
  name?: string;
  profile?: any;
  isNew?: boolean;
  hasProfile?: boolean;
};

/** Сколько ждём возврата из браузера, прежде чем снять слушателя. Человек может уйти из браузера
 *  и не вернуться — вечный слушатель остался бы висеть и сработал бы на чужой ссылке. */
const WAIT_MS = 5 * 60 * 1000;

/** Какие входы бывают. Слово совпадает с адресом ручки — `/api/auth/<provider>/start`. */
export type Provider = 'google' | 'apple';

/** Настроен ли вход на сервере: ключи живут в окружении службы, и без них ручка отвечает
 *  `enabled:false`. Кнопка, которая на нажатие говорит «не настроено», хуже отсутствующей. */
export async function providerEnabled(provider: Provider): Promise<boolean> {
  try {
    const r: any = await auth.oauthEnabled(provider);
    return !!r?.enabled;
  } catch {
    return false;
  }
}

/**
 * Открыть вход и дождаться возврата. Обещание выполняется ответом сервера (та же форма, что у
 * входа по коду) или отклоняется коротким словом: `denied` — человек закрыл окно сервиса,
 * `expired` — метка протухла, `google`/`apple` — сервис отказал, `timeout` — из браузера не
 * вернулись.
 */
export function signInWith(provider: Provider): Promise<AuthResult> {
  // `createURL` сам подставит верную схему: `exp://…/--/auth` в Expo Go и `kleal://auth` в сборке.
  const back = Linking.createURL('auth');
  const url = API_BASE + `/api/auth/${provider}/start?redirect=` + encodeURIComponent(back);

  return new Promise<AuthResult>((resolve, reject) => {
    let done = false;
    const finish = (fn: () => void) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      sub.remove();
      fn();
    };

    const onUrl = async ({ url: incoming }: { url: string }) => {
      let q: Record<string, unknown> = {};
      try {
        q = (Linking.parse(incoming).queryParams || {}) as Record<string, unknown>;
      } catch {
        return;
      }
      const ticket = String(q.ticket || '');
      const err = String(q.error || '');
      if (!ticket && !err) return;                    // чужая ссылка — не наш возврат, ждём дальше
      if (err) return finish(() => reject(new Error(err)));
      try {
        const r: AuthResult = (await auth.oauthExchange(ticket)) as AuthResult;
        if (r && r.ok) finish(() => resolve(r));
        else finish(() => reject(new Error(String((r && r.error) || 'expired'))));
      } catch (e) {
        finish(() => reject(e instanceof Error ? e : new Error('network')));
      }
    };

    const sub = Linking.addEventListener('url', onUrl);
    const timer = setTimeout(() => finish(() => reject(new Error('timeout'))), WAIT_MS);

    Linking.openURL(url).catch((e) => finish(() => reject(e instanceof Error ? e : new Error('browser'))));
  });
}
