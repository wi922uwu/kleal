import type React from 'react';
import type { ExplorePin } from '../explore';

// Объявление на оба варианта: реализация выбирается суффиксом файла (.native / .web) — так же,
// как у RadiusMap. Тип общий, иначе TypeScript не находит модуль без расширения.
export declare function ExploreMap(props: {
  pins: ExplorePin[];
  /** Куда смотреть при открытии. Если не передать — карта соберёт центр по самим пинам. */
  center?: { lat: number; lon: number } | null;
  /** Наклон камеры в градусах. Ради него всё и затевалось: дома объёмные только под углом. */
  pitch?: number;
  /** Нажали на пин. */
  onPick?: (pin: ExplorePin) => void;
  /** Сколько интентов стоит в той же точке — подпись «ещё N» на кучке. */
  stacks?: Map<string, number>;
  /** Показывать ли синюю точку «я здесь». Требует выданного разрешения на геопозицию. */
  showMe?: boolean;
  /** Внешняя команда «верни камеру ко мне»: меняется число — камера едет. */
  recenter?: number;
  /** Выбранный пин: он крупнее, в красном кольце и с красным хвостом (кадр «Pin selected»). */
  selectedId?: string | null;
  /** «planet» — карта сворачивается в планету («Онлайн»); «city» — разворачивается обратно в город. */
  mode?: 'city' | 'planet';
  /** Страны с интентами: плашки на планете. */
  countries?: { code: string; lat: number; lon: number; count: number; w?: number }[] | null;
  /** Буди думает над вопросом шару — ореолы стран бегут волной. */
  scanning?: boolean;
  /** Выбранная страна: её плашка подсвечена, планета к ней довёрнута. */
  selectedCountry?: string | null;
  /** Нажали на плашку страны на планете. */
  onPickCountry?: (code: string) => void;
  /** Сколько пикселей снизу закрыто листом интентов. */
  reserveBottom?: number;
  /** Подвезти камеру к пину: меняется счётчик — камера едет. */
  focusPin?: { lat: number; lon: number; n: number } | null;
}): React.ReactElement;
