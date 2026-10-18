/**
 * Размер слоя «во весь экран» — для фонов, которые рисуются картинкой или SVG под всем экраном.
 *
 * На Android 14 и ниже `useWindowDimensions()` в Expo Go отдаёт окно БЕЗ строки состояния и панели
 * навигации (флаг edge-to-edge в RN ставится только с Android 15, см. src/keyboard.ts). С 18.10.2026
 * приложение рисует под строкой состояния (app/_layout.tsx), и фон высотой «окна» не доставал до низа:
 * под навбаром оставалась кремовая полоса ровно в высоту строки состояния (снято на эмуляторе).
 * Берём большее из окна и экрана — лишнее срежет сам экран.
 */
import { Dimensions, useWindowDimensions } from 'react-native';

export function useFullScreenSize() {
  const win = useWindowDimensions();
  const scr = Dimensions.get('screen');
  return { width: Math.max(win.width, scr.width), height: Math.max(win.height, scr.height) };
}
