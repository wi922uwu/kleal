/**
 * Настройки — кадры B.10–B.12.
 *
 * UX-каркас: копия и правила здесь, вид в app/settings/*.
 *
 * Половина строк на кадре — это то, чего в продукте ещё нет: платёжного метода, смены пароля,
 * уведомлений и тёмной темы не существует ни на сервере, ни в приложении. Они показаны
 * приглушёнными и не нажимаются — по тому же правилу, что и вкладки нижней панели: строка,
 * которая выглядит рабочей и молча ничего не делает, хуже честно выключенной.
 */
import { T } from './i18n';

export const SETTINGS = {
  title: () => T('Настройки', 'Settings'),
  logout: () => T('Выйти', 'Log out'),
  soon: () => T('скоро', 'coming soon'),
};

export type SettingId =
  | 'personal' | 'password' | 'payment' | 'notifications'
  | 'language' | 'help' | 'privacy' | 'dark';

export type SettingRow = {
  id: SettingId;
  title: () => string;
  /** Куда ведёт. Пусто — строка есть на кадре, но за ней ничего нет. */
  to?: string;
  /** Не переход, а переключатель прямо в строке. */
  control?: 'lang' | 'dark';
};

export const SETTING_ROWS: SettingRow[] = [
  { id: 'personal',      title: () => T('Личные данные', 'Edit Personal Info') },
  { id: 'password',      title: () => T('Сменить пароль', 'Change Password') },
  { id: 'payment',       title: () => T('Способ оплаты', 'Payment Method') },
  { id: 'notifications', title: () => T('Уведомления', 'Notifications') },
  { id: 'language',      title: () => T('Язык', 'Language'), control: 'lang' },
  { id: 'help',          title: () => T('Помощь и поддержка', 'Help & Support') },
  { id: 'privacy',       title: () => T('Приватность и безопасность', 'Privacy & Security'), to: '/profile/safety' },
  { id: 'dark',          title: () => T('Тёмная тема', 'Dark Mode'), control: 'dark' },
];

export const BLOCKED = {
  title: () => T('Заблокированные', 'Blocked people'),
  row: (n: number) =>
    n === 1 ? T('1 человек · он об этом не знает', '1 person · they are not told')
            : T(`${n} человека · они об этом не знают`, `${n} people · they are not told`),
  none: () => T('Никого', 'Nobody'),
  lead: () =>
    T(
      'Заблокированный не может тебе написать и не видит твоих интентов. Ему об этом не сообщают.',
      'A blocked person can’t message you and can’t see your intents. They are not told about it.',
    ),
  empty: () => T('Ты никого не блокировал.', 'You haven’t blocked anyone.'),
  unblock: () => T('Разблокировать', 'Unblock'),
  /**
   * Даты рядом с именем не будет. Сервер хранит список блокировок именами и ничем больше — ни
   * когда, ни возраст. На кадре «Blocked 24 July» стоит как заполнитель; написать сюда любую дату
   * значит показать человеку выдуманный факт о его собственном решении.
   */
  since: () => '',
};
