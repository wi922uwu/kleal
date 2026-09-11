/**
 * Профиль собеседника — копия для app/person.tsx.
 *
 * Здесь только отказы: саму карточку рисует `app/candidate.tsx` (кадр O.13), тот же экран, что и
 * в поиске. Своих подписей к разделам тут нет намеренно — они жили бы второй копией рядом с
 * `src/candidates.ts` и разошлись бы с ней при первой правке.
 */
import { T } from './i18n';

export const PERSON = {

  /**
   * Отказ сервера словами человека. `NOT_MATCHED` значит «вы ещё не договорились» — а не поломку,
   * и предлагать «попробуй ещё раз» здесь неправильно: повтор ничего не изменит.
   */
  notMatched: (name: string) =>
    T(`Профиль откроется, когда ${name} примет приглашение.`,
      `Their profile opens once ${name} accepts your invite.`, `Su perfil se abre cuando ${name} acepta tu invitación.`),
  failed: () => T('Не получилось открыть профиль.', 'Couldn’t open this profile.', 'No se pudo abrir este perfil.'),
  offline: () => T('Нет связи. Проверь интернет.', 'No connection. Check your internet.', 'Sin conexión. Comprueba tu conexión a internet.'),
};
