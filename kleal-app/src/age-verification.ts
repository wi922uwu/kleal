import { API_BASE, getSession } from './api';
import { getLang, T } from './i18n';

export type AgeStatus = 'not_started' | 'pending' | 'review' | 'approved' | 'declined' | 'cancelled' | 'expired' | 'legacy_exempt';
export type AgeResult = { ok: true; status: AgeStatus; over18: boolean; admitted: boolean; onboarded: boolean;
  canStart: boolean; retryAfter: number; sessionId: string | null; url?: string; developmentDemo?: boolean };
const statuses = new Set<AgeStatus>(['not_started', 'pending', 'review', 'approved', 'declined', 'cancelled', 'expired', 'legacy_exempt']);

export function validAgeResult(value: any): value is AgeResult {
  return value?.ok === true && statuses.has(value.status) && typeof value.admitted === 'boolean'
    && typeof value.over18 === 'boolean' && typeof value.onboarded === 'boolean'
    && typeof value.canStart === 'boolean' && Number.isFinite(value.retryAfter) && value.retryAfter >= 0
    && (value.sessionId === null || typeof value.sessionId === 'string')
    && (value.url === undefined || typeof value.url === 'string')
    && (value.developmentDemo === undefined || typeof value.developmentDemo === 'boolean')
    && (value.admitted === false || value.status === 'legacy_exempt' || (value.status === 'approved' && value.over18 === true));
}

export function isHostedVerificationURL(value: string): boolean {
  try { const u = new URL(value); return u.protocol === 'https:' && u.host === 'verify.didit.me'
    && !u.username && !u.password && u.pathname.length > 1 && !u.pathname.startsWith('/u/'); } catch { return false; }
}

export class AgeRequestError extends Error {
  constructor(code: string, public readonly status: number = 503) { super(code); }
}

export class AgeSessionRequiredError extends AgeRequestError {
  constructor() { super('sign_in_required', 401); }
}

export async function ageRequest(action: 'status' | 'refresh' | 'session'): Promise<AgeResult> {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 15000);
  try {
    const response = await fetch(`${API_BASE}/api/onboarding/age-verification/${action}`, {
      method: action === 'status' ? 'GET' : 'POST', signal: abort.signal,
      headers: { Authorization: `Bearer ${getSession()}`, 'Content-Type': 'application/json' },
      ...(action === 'session' ? { body: JSON.stringify({ language: getLang() }) } : {}),
    });
    // A proxy may return an empty/HTML body. Authentication is an HTTP fact,
    // never dependent on JSON parsing or an untrusted error-message string.
    if (response.status === 401) throw new AgeSessionRequiredError();
    const result = await response.json();
    if (!response.ok || !validAgeResult(result)) {
      const code = String(result?.error || 'service');
      const safeCode = code === 'sign_in_required' || (code === 'onboarding_required' && response.status !== 409) ? 'service' : code;
      throw new AgeRequestError(safeCode, response.status);
    }
    return result;
  } finally { clearTimeout(timer); }
}

export const AGE_COPY = {
  developmentDemo: () => T('DEV · Общедоступный демо-аккаунт. Реальный результат Didit привязан к аккаунту, но не подтверждает личность каждого, кто вошёл в него.',
    'DEV · Shared demo account. The real Didit result is bound to this account, not proof of the identity of everyone who signs in.',
    'DEV · Cuenta demo compartida. El resultado real de Didit se vincula a esta cuenta; no acredita la identidad de cada persona que accede.'),
  title: () => T('Kleal — только для взрослых', 'Kleal is for adults', 'Kleal es solo para adultos'),
  privacy: () => T('Онбординг завершён. Чтобы пользоваться Kleal, подтвердите, что вам есть 18 лет. Didit проверит документ и селфи на своей защищённой странице. Kleal сохраняет только результат 18+, статус и ID проверки — не документ, селфи, ФИО или дату рождения.',
    'Onboarding is complete. Verify that you are 18 or older to use Kleal. Didit checks your document and selfie on its hosted page. Kleal retains only the 18+ result, status and verification ID — not your document, selfie, name or birth date.',
    'Has terminado el registro. Confirma que tienes 18 años o más para usar Kleal. Didit comprueba tu documento y selfie en su página. Kleal conserva solo el resultado 18+, el estado y el ID de verificación, no el documento, selfie, nombre ni fecha de nacimiento.'),
  camera: () => T('Didit откроется в браузере и запросит доступ к камере. После проверки вручную вернитесь в Kleal в Expo Go или в приложение Kleal. Статус обновится с сервера; если нет — нажмите «Проверить статус». Закрытие браузера не подтверждает 18+. Если камера заблокирована, разрешите её для Didit в настройках браузера.',
    'Didit opens in your browser and requests camera access. After verification, manually return to Kleal in Expo Go or the Kleal app. The server status refreshes; if not, tap Check status. Closing the browser does not verify 18+. If camera access is blocked, allow it for Didit in browser settings.',
    'Didit se abre en el navegador y solicita acceso a la cámara. Después vuelve manualmente a Kleal en Expo Go o a la app Kleal. Se actualizará el estado del servidor; si no, pulsa Consultar estado. Cerrar el navegador no confirma los 18+. Si la cámara está bloqueada, permítela para Didit en los ajustes del navegador.'),
  start: () => T('Пройти проверку', 'Verify my age', 'Verificar mi edad'),
  resume: () => T('Продолжить проверку', 'Resume verification', 'Reanudar verificación'),
  check: () => T('Проверить статус', 'Check status', 'Consultar estado'),
  signIn: () => T('Войти снова', 'Sign in again', 'Iniciar sesión de nuevo'),
  waiting: () => T('Проверяем статус…', 'Checking status…', 'Consultando estado…'),
  opening: () => T('Открываем защищённую страницу…', 'Opening the secure page…', 'Abriendo la página segura…'),
  startUnconfirmed: () => T('Уточняем, запустилась ли проверка. Не создавайте её повторно. Нажмите «Проверить статус». Если статус долго не меняется, обратитесь в поддержку.',
    'We are checking whether verification started. Do not start another verification. Tap Check status. If this status does not change for a while, contact support.',
    'Estamos comprobando si se ha iniciado la verificación. No inicies otra verificación. Pulsa Consultar estado. Si el estado no cambia durante un tiempo, contacta con soporte.'),
  notChecked: () => T('Статус пока не получен', 'Status not yet available', 'Estado aún no disponible'),
  sessionExpired: () => T('Нужно войти снова', 'Sign in again to continue', 'Inicia sesión de nuevo para continuar'),
  retryIn: (seconds: number) => T(`Новая попытка через ${seconds} с`, `New attempt in ${seconds}s`, `Nuevo intento en ${seconds}s`),
  status: (s: AgeStatus) => ({
    not_started: T('Проверка ещё не начата', 'Verification not started', 'Verificación sin iniciar'),
    pending: T('Проверка не завершена. Можно продолжить с того же места.', 'Verification is incomplete. You can resume it.', 'La verificación no ha terminado. Puedes reanudarla.'),
    review: T('Результат на рассмотрении. Новая проверка не нужна — вернитесь позже.', 'Your result is under review. No new verification is needed — check back later.', 'Tu resultado está en revisión. No necesitas otra verificación; vuelve más tarde.'),
    declined: T('Проверка не одобрена. Доступ пока закрыт. Если это ошибка, обратитесь в поддержку; повторная отправка автоматически не запускается.', 'Verification was not approved. Access remains restricted. If this is a mistake, contact support; a new submission will not start automatically.', 'La verificación no fue aprobada. El acceso sigue restringido. Si es un error, contacta con soporte; no se enviará otra solicitud automáticamente.'),
    cancelled: T('Проверка прервана. Доступ откроется только после подтверждения.', 'Verification was interrupted. Access requires confirmation.', 'La verificación se interrumpió. Se requiere confirmación para acceder.'),
    expired: T('Срок проверки истёк. Можно начать новую попытку.', 'Verification expired. You can start a new attempt.', 'La verificación caducó. Puedes iniciar otro intento.'),
    approved: T('18+ подтверждено', '18+ verified', '18+ verificado'),
    legacy_exempt: T('Проверка сейчас не требуется', 'Verification is not currently required', 'La verificación no es necesaria ahora'),
  })[s],
  error: (code: string) => code === 'browser_open'
    ? T('Не удалось открыть страницу проверки. Попробуйте ещё раз или проверьте настройки браузера. Доступ пока закрыт.',
      'Could not open the verification page. Try again or check your browser settings. Access remains restricted.',
      'No se pudo abrir la página de verificación. Inténtalo de nuevo o revisa los ajustes del navegador. El acceso sigue restringido.')
    : code === 'onboarding_required'
      ? T('Сначала сохраните профиль.', 'Save your profile first.', 'Guarda tu perfil primero.')
    : ['credits', 'configuration', 'service', 'provider_response', 'session_mismatch', 'environment_mismatch', 'verification_unavailable', 'age_verification_required'].includes(code)
    ? T('Проверка временно недоступна на стороне сервиса. Это не отказ по вашему документу. Попробуйте позже или обратитесь в поддержку.', 'Verification is temporarily unavailable. This is not a rejection of your document. Try later or contact support.', 'La verificación no está disponible temporalmente. No es un rechazo de tu documento. Inténtalo más tarde o contacta con soporte.')
    : code === 'cooldown' || code === 'rate_limit'
      ? T('Слишком частые попытки. Подождите минуту и повторите.', 'Too many attempts. Wait a minute and try again.', 'Demasiados intentos. Espera un minuto y vuelve a intentarlo.')
      : code === 'sign_in_required'
        ? T('Сессия истекла. Войдите снова; результат проверки хранится на сервере.', 'Your session expired. Sign in again; your result is stored on the server.', 'Tu sesión caducó. Inicia sesión de nuevo; tu resultado está en el servidor.')
        : T('Не удалось проверить статус. Проверьте интернет и повторите. Доступ не открывается по одному возврату из браузера.', 'Could not check the status. Check your connection and retry. Returning from the browser alone does not grant access.', 'No se pudo consultar el estado. Comprueba la conexión e inténtalo de nuevo. Volver del navegador no concede acceso.'),
};
