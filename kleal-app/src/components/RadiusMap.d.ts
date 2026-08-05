import type React from 'react';
// Объявление на оба варианта: реализация выбирается суффиксом файла (.native / .web),
// а тип у них общий — TypeScript иначе не находит модуль без расширения.
export declare function RadiusMap(props: { lat: number; lon: number; km: number }): React.ReactElement;
