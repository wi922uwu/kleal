/**
 * Нижняя панель сворачивается при прокрутке — борд «Navigation V2 · Scroll — pilot» (Figma 7145:124875):
 * NAV.S1 «top · Expanded» и NAV.S2 «scrolled · Minimized».
 *
 * Одно общее значение на всё приложение: 0 — развёрнута, 1 — свёрнута. Экран со списком вешает на
 * свой ScrollView `onScroll` из `useNavCollapse()`, панель (src/components/BottomNav.tsx) только
 * читает значение. Так панели не нужно знать, на каком она экране и что там прокручивается.
 *
 * ПРАВИЛО — как у системной панели iOS 26: вниз (читаешь дальше) — свернуть, вверх (ищешь, куда
 * уйти) — развернуть, у верха списка — всегда развёрнута. Небольшой порог (`DEAD`) гасит дрожь
 * пальца: без него панель мигала бы на каждом микродвижении.
 */
import { useRef } from 'react';
import { Animated, type NativeScrollEvent, type NativeSyntheticEvent } from 'react-native';

export const navMin = new Animated.Value(0);
let minimized = false;
const listeners = new Set<(min: boolean) => void>();

/** Свёрнута ли панель прямо сейчас — для расчёта зон касания в BottomNav. */
export const isNavMinimized = () => minimized;

export function onNavMinimized(fn: (min: boolean) => void): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

export function setNavMinimized(min: boolean) {
  if (min === minimized) return;
  minimized = min;
  Animated.spring(navMin, { toValue: min ? 1 : 0, useNativeDriver: true, damping: 22, stiffness: 260, mass: 0.7 }).start();
  listeners.forEach((fn) => fn(min));
}

/** Ниже этого смещения от верха панель не сворачивается: первый экран списка — «top · Expanded». */
const TOP = 40;
/** Сколько надо пройти в одну сторону, чтобы панель отозвалась. */
const DEAD = 6;

/** `onScroll` для вертикального списка экрана. Вместе с ним нужен `scrollEventThrottle={16}`. */
export function useNavCollapse() {
  const last = useRef(0);
  return (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const y = e.nativeEvent.contentOffset.y;
    const dy = y - last.current;
    if (y <= TOP) { setNavMinimized(false); last.current = y; return; }
    if (Math.abs(dy) < DEAD) return;
    setNavMinimized(dy > 0);
    last.current = y;
  };
}
