/**
 * Вход по коду с почты — кадры A.03.1 … A.03.3.
 *
 * Копия отдельно от экранов по общему правилу проекта. Числа здесь не выдуманы: десять минут,
 * тридцать секунд и счётчик попыток стоят на кадрах, и менять их надо вместе с сервером —
 * там те же значения (CODE_TTL, RESEND_AFTER, CODE_ATTEMPTS в services/onboarding).
 */
import { T } from './i18n';

export const AUTH = {
  // ---- A.03.1 · адрес
  emailTitle: () => T('Какая у тебя почта?', 'What’s your email?', '¿Cuál es tu correo electrónico?'),
  emailNote: () =>
    T(
      'Пришлём код, чтобы войти — или создать аккаунт, если ты здесь впервые.',
      'We’ll send you a code to sign in or create your account if you’re new.'
    , 'Te enviaremos un código para iniciar sesión o crear tu cuenta si eres nuevo.'),
  emailLabel: () => T('Почта', 'Email', 'Correo'),
  emailPlaceholder: () => 'you@email.com',
  continue: () => T('Продолжить', 'Continue', 'Continuar'),
  /** A.03.1b — адрес не похож на адрес. Проверяем ДО отправки: письмо на «alex@@mail» не уйдёт. */
  badEmailTitle: () => T('Проверь адрес', 'Check the address', 'Comprueba la dirección'),
  badEmailNote: () =>
    T('Это не похоже на почту. Попробуй ещё раз.', 'That doesn’t look like an email. Try again.', 'Eso no parece un correo. Inténtalo de nuevo.'),
  /**
   * Кириллица до «@». Это правильный на вид адрес, на который письмо не дойдёт никогда:
   * почтовые провайдеры не доставляют на не-ASCII имена ящиков. Прежде такой адрес уходил на
   * сервер, провайдер отвечал 422, а экран говорил «попробуй через минуту» — и человек пробовал.
   * Домен кириллицей («почта.рф») — можно, его сервер кодирует сам.
   */
  latinEmailTitle: () => T('Адрес латиницей', 'Use Latin letters', 'Usa letras latinas'),
  latinEmailNote: () =>
    T('На имя ящика кириллицей письмо не дойдёт. Введи адрес латинскими буквами.',
      'Mail can’t be delivered to a mailbox name in Cyrillic. Type the address in Latin letters.', 'El correo no puede ser entregado a una dirección con caracteres cirílicos. Escribe la dirección en letras latinas.'),

  // ---- A.03.2 · код
  codeTitle: () => T('Введи код', 'Enter the code', 'Introduce el código'),
  codeNote: (email: string, minutes: number) =>
    T(
      `Мы отправили шестизначный код на ${email}. Он действует ${minutes} минут.`,
      `We sent a 6-digit code to ${email}. It expires in ${minutes} minutes.`
    , `Te enviamos un código de 6 dígitos a ${email}. Caduca en ${minutes} minutos.`),
  verify: () => T('Подтвердить', 'Verify', 'Verificar'),
  verifying: () => T('Проверяем код…', 'Checking the code…', 'Comprobando el código…'),
  resendIn: (sec: number) =>
    T(`Отправить ещё раз через 0:${sec < 10 ? '0' : ''}${sec}`,
      `Resend code in 0:${sec < 10 ? '0' : ''}${sec}`, `Reenviar código en 0:${sec < 10 ? '0' : ''}${sec}`),
  resend: () => T('Отправить ещё раз', 'Resend code', 'Reenviar código'),
  sendNew: () => T('Отправить новый код', 'Send a new code', 'Enviar un nuevo código'),
  otherEmail: () => T('Другая почта', 'Use a different email', 'Usa otro correo electrónico'),

  /**
   * A.03.2b — неверный код. Счётчик попыток показывается человеку намеренно: без него третья
   * ошибка выглядит как поломка, а не как исчерпанная попытка.
   */
  wrongTitle: () => T('Неверный код', 'Wrong code', 'Código incorrecto'),
  wrongNote: (left: number) =>
    T(
      `Проверь цифры и попробуй ещё раз. Осталось попыток: ${left}.`,
      `Check the digits and try again. ${left} attempt${left === 1 ? '' : 's'} left.`
    , `Comprueba los dígitos y vuelve a intentarlo. Quedan ${left} intento${left === 1 ? '' : 's'}.`),
  /** A.03.2c — код истёк ИЛИ попытки кончились: для человека это одно и то же — нужен новый. */
  expiredTitle: () => T('Код истёк', 'Code expired', 'Código expirado'),
  expiredNote: () =>
    T('Этот код больше не действует. Запроси новый.',
      'That code is no longer valid. Send yourself a new one.', 'Ese código ya no es válido. Envíate uno nuevo.'),

  sendFailedTitle: () => T('Письмо не ушло', 'We couldn’t send the email', 'No pudimos enviar el correo'),
  sendFailedNote: () =>
    T('Попробуй ещё раз через минуту.', 'Try again in a minute.', 'Inténtalo de nuevo en un minuto.'),
  /**
   * Отказ, который повтором не лечится: почтовый домен ещё не подтверждён у провайдера, и писать
   * он разрешает только на один адрес. Прежний текст «попробуй через минуту» в этом случае гонял
   * человека по кругу — минута ничего не меняет. Причину не называем внутренними словами: для
   * человека важно, что дело в адресе и что делать дальше.
   */
  notAllowedTitle: () => T('На этот адрес пока не пишем', 'We can’t write to that address yet', 'Todavía no podemos escribir a esa dirección'),
  notAllowedNote: () =>
    T(
      'Почта Kleal ещё настраивается. Попробуй другой адрес или напиши нам.',
      'Kleal’s email is still being set up. Try another address or write to us.'
    , 'El correo de Kleal aún se está configurando. Prueba otra dirección o escríbenos.'),
  tooManyTitle: () => T('Слишком много попыток', 'Too many attempts', 'Demasiados intentos'),
  tooManyNote: () =>
    T('Подожди час и попробуй снова.', 'Wait an hour and try again.', 'Espera una hora y vuelve a intentarlo.'),
  offline: () => T('Нет связи. Проверь интернет.', 'No connection. Check your internet.', 'Sin conexión. Comprueba tu conexión a internet.'),

  // ---- A.03.3 · вошёл
  doneTitle: () => T('Ты в деле', 'You’re in', '¡Estás dentro!'),
  doneNote: () =>
    T(
      'Соберём профиль, чтобы Kleal нашёл твоих людей и твои планы.',
      'Let’s build your profile so Kleal can find your people and your plans.'
    , 'Vamos a crear tu perfil para que Kleal pueda encontrar a tu gente y tus planes.'),
  setUp: () => T('Собрать профиль', 'Set up profile', 'Configurar perfil'),
};

/**
 * Тот же признак, что и на сервере, и на кадре A.03.1b.
 *
 * Нарочно простая: задача — отсечь опечатку вроде «alex@@mail», а не решить, существует ли
 * ящик. Это выясняется только доставкой письма, и притворяться, что мы знаем заранее, вредно.
 */
export const looksLikeEmail = (v: string) => /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(String(v || '').trim());
/** Имя ящика не латиницей — письмо не дойдёт; проверяем до отправки, чтобы не гонять по кругу. */
export const latinLocalPart = (v: string) => /^[\x00-\x7F]*$/.test(String(v || '').trim().split('@')[0]);

/** Сколько цифр в коде — одно число на экран, поле ввода и проверку. */
export const CODE_LEN = 6;

/**
 * Подпись к коду, показанному на экране.
 *
 * Он виден только пока на сервере включён KLEAL_SHOW_CODE — то есть пока почта не настроена на
 * произвольные адреса. Текст написан так, чтобы никто не принял это за возможность продукта:
 * прямо сказано, что это отладка и что в рабочем приложении кода здесь не будет.
 */
export const DEV_CODE = {
  title: () => T('Отладка: почта ещё не настроена', 'Debug: email isn’t set up yet', 'Depuración: el correo electrónico no está configurado aún'),
  /** Полоса свёрнута по умолчанию: письмо теперь доходит, и код нужен не всегда. */
  show: () => T('Показать код', 'Show the code', 'Mostrar el código'),
  hide: () => T('Скрыть', 'Hide', 'Ocultar'),
  note: () =>
    T(
      'Код показан здесь, потому что письмо на этот адрес пока не уходит. В рабочем приложении его тут не будет.',
      'The code is shown here because we can’t email this address yet. It will not be here in the real app.'
    , 'El código se muestra aquí porque no podemos enviarlo por correo a esta dirección aún. No estará aquí en la app real.'),
};
