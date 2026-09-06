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
  emailTitle: () => T('Какая у тебя почта?', 'What’s your email?'),
  emailNote: () =>
    T(
      'Пришлём код, чтобы войти — или создать аккаунт, если ты здесь впервые.',
      'We’ll send you a code to sign in or create your account if you’re new.'
    ),
  emailLabel: () => T('Почта', 'Email'),
  emailPlaceholder: () => 'you@email.com',
  continue: () => T('Продолжить', 'Continue'),
  /** A.03.1b — адрес не похож на адрес. Проверяем ДО отправки: письмо на «alex@@mail» не уйдёт. */
  badEmailTitle: () => T('Проверь адрес', 'Check the address'),
  badEmailNote: () =>
    T('Это не похоже на почту. Попробуй ещё раз.', 'That doesn’t look like an email. Try again.'),

  // ---- A.03.2 · код
  codeTitle: () => T('Введи код', 'Enter the code'),
  codeNote: (email: string, minutes: number) =>
    T(
      `Мы отправили шестизначный код на ${email}. Он действует ${minutes} минут.`,
      `We sent a 6-digit code to ${email}. It expires in ${minutes} minutes.`
    ),
  verify: () => T('Подтвердить', 'Verify'),
  verifying: () => T('Проверяем код…', 'Checking the code…'),
  resendIn: (sec: number) =>
    T(`Отправить ещё раз через 0:${sec < 10 ? '0' : ''}${sec}`,
      `Resend code in 0:${sec < 10 ? '0' : ''}${sec}`),
  resend: () => T('Отправить ещё раз', 'Resend code'),
  sendNew: () => T('Отправить новый код', 'Send a new code'),
  otherEmail: () => T('Другая почта', 'Use a different email'),

  /**
   * A.03.2b — неверный код. Счётчик попыток показывается человеку намеренно: без него третья
   * ошибка выглядит как поломка, а не как исчерпанная попытка.
   */
  wrongTitle: () => T('Неверный код', 'Wrong code'),
  wrongNote: (left: number) =>
    T(
      `Проверь цифры и попробуй ещё раз. Осталось попыток: ${left}.`,
      `Check the digits and try again. ${left} attempt${left === 1 ? '' : 's'} left.`
    ),
  /** A.03.2c — код истёк ИЛИ попытки кончились: для человека это одно и то же — нужен новый. */
  expiredTitle: () => T('Код истёк', 'Code expired'),
  expiredNote: () =>
    T('Этот код больше не действует. Запроси новый.',
      'That code is no longer valid. Send yourself a new one.'),

  sendFailedTitle: () => T('Письмо не ушло', 'We couldn’t send the email'),
  sendFailedNote: () =>
    T('Попробуй ещё раз через минуту.', 'Try again in a minute.'),
  /**
   * Отказ, который повтором не лечится: почтовый домен ещё не подтверждён у провайдера, и писать
   * он разрешает только на один адрес. Прежний текст «попробуй через минуту» в этом случае гонял
   * человека по кругу — минута ничего не меняет. Причину не называем внутренними словами: для
   * человека важно, что дело в адресе и что делать дальше.
   */
  notAllowedTitle: () => T('На этот адрес пока не пишем', 'We can’t write to that address yet'),
  notAllowedNote: () =>
    T(
      'Почта Kleal ещё настраивается. Попробуй другой адрес или напиши нам.',
      'Kleal’s email is still being set up. Try another address or write to us.'
    ),
  tooManyTitle: () => T('Слишком много попыток', 'Too many attempts'),
  tooManyNote: () =>
    T('Подожди час и попробуй снова.', 'Wait an hour and try again.'),
  offline: () => T('Нет связи. Проверь интернет.', 'No connection. Check your internet.'),

  // ---- A.03.3 · вошёл
  doneTitle: () => T('Ты в деле', 'You’re in'),
  doneNote: () =>
    T(
      'Соберём профиль, чтобы Kleal нашёл твоих людей и твои планы.',
      'Let’s build your profile so Kleal can find your people and your plans.'
    ),
  setUp: () => T('Собрать профиль', 'Set up profile'),
};

/**
 * Тот же признак, что и на сервере, и на кадре A.03.1b.
 *
 * Нарочно простая: задача — отсечь опечатку вроде «alex@@mail», а не решить, существует ли
 * ящик. Это выясняется только доставкой письма, и притворяться, что мы знаем заранее, вредно.
 */
export const looksLikeEmail = (v: string) => /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(String(v || '').trim());

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
  title: () => T('Отладка: почта ещё не настроена', 'Debug: email isn’t set up yet'),
  /** Полоса свёрнута по умолчанию: письмо теперь доходит, и код нужен не всегда. */
  show: () => T('Показать код', 'Show the code'),
  hide: () => T('Скрыть', 'Hide'),
  note: () =>
    T(
      'Код показан здесь, потому что письмо на этот адрес пока не уходит. В рабочем приложении его тут не будет.',
      'The code is shown here because we can’t email this address yet. It will not be here in the real app.'
    ),
};
