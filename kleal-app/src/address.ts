/**
 * Копия поля адреса — общего для интента, плана и группового плана (src/components/AddressField).
 * Здесь, а не в компоненте: копия живёт в src/*.ts, компоненты её только читают.
 */
import { T } from './i18n';

export const ADDRESS = {
  /** Строка-подсказка первой в списке и подпись у булавки справа от поля. */
  myLocation: () => T('Моё местоположение', 'My location', 'Mi ubicación'),
  locating: () => T('Определяем…', 'Locating…', 'Localizando…'),
  /** Отказ в доступе — не ошибка приложения: говорим, что делать дальше, а не что «не удалось». */
  denied: () =>
    T('Нет доступа к геолокации — впиши адрес руками.',
      'No location access — type the address instead.',
      'Sin acceso a la ubicación: escribe la dirección.'),
  failed: () =>
    T('Не удалось определить место — впиши адрес руками.',
      'Couldn’t detect the location — type the address instead.',
      'No se pudo detectar la ubicación: escribe la dirección.'),
};
