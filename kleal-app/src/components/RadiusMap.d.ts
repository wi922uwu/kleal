import type React from 'react';
// Объявление на оба варианта: реализация выбирается суффиксом файла (.native / .web),
// а тип у них общий — TypeScript иначе не находит модуль без расширения.
export declare function RadiusMap(props: {
  lat: number;
  lon: number;
  km: number;
  /** Булавку передвинули. Без него карта только показывает — точка стоит там, где живёшь. */
  onMove?: (lat: number, lon: number) => void;
  /** Палец на карте: экран-родитель обязан на это время выключить свою прокрутку, иначе
   *  ScrollView перехватывает жест и точка не двигается. */
  onDragChange?: (dragging: boolean) => void;
}): React.ReactElement;
