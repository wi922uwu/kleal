/**
 * ЛЕНТА И ПЛИТКА — иллюстрация кадров A.03.3 «You’re in» и A.15 «You are on the board».
 *
 * Коралловая лента (#F2526B, 8 точек) проходит через экран петлёй, на ней стеклянная плитка 96×96.
 * В A.03.3 из плитки выглядывает капля, в A.15 в ней белый знак Kleal. Контуры сняты с Figma как
 * есть: лента — это её обводка, развёрнутая в заливку, поэтому толщина и изгиб совпадают с бордом.
 *
 * ЛЕНТА РИСУЕТСЯ. Она открывается слева направо, а плитка всплывает, когда лента до неё дошла:
 * человек видит не картинку, а жест — «нить привела сюда». При «Уменьшить движение» всё сразу.
 */
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import Animated, {
  Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withDelay, withTiming,
} from 'react-native-reanimated';
import { GlassSurface } from './LiquidGlass';

const RIBBON = 'M494.5 119.8C496.7 119.5 498.2 117.5 497.9 115.3C497.7 113.1 495.7 111.6 493.5 111.8L494 115.8L494.5 119.8ZM179.7 163.5L175.7 163.5L179.7 163.5ZM1.2 201.5C-0.9 200.8 -3.1 202 -3.8 204.1C-4.5 206.2 -3.3 208.5 -1.2 209.1L0 205.3L1.2 201.5ZM347.8 4.1L349.6 7.6L349.6 7.6L347.8 4.1ZM179.7 163.5L183.7 163.5C183.7 149.2 182.9 139.2 180.9 132.9C179.9 129.7 178.5 127 176.2 125.2C173.8 123.2 170.9 122.8 168.1 123.5C165.5 124.1 163 125.5 160.5 127.3C158 129.1 155.4 131.4 152.6 134.1C147 139.3 140.4 146.3 133.2 153.6C103.5 183.4 60.2 220.7 1.2 201.5L0 205.3L-1.2 209.1C62.7 229.9 109.3 189 138.8 159.3C146.4 151.7 152.6 145 158.1 139.9C160.8 137.3 163.2 135.3 165.2 133.8C167.3 132.2 168.9 131.5 169.9 131.3C170.8 131.1 171 131.2 171.2 131.4C171.7 131.8 172.5 132.8 173.3 135.3C174.9 140.3 175.7 149.2 175.7 163.5L179.7 163.5ZM394.3 75.3L390.6 73.9C385.1 88.7 369.3 107.8 348.2 126.7C327.2 145.6 301.3 163.8 276.3 177C251 190.2 227.2 198 210.1 196.7C201.7 196.1 195.3 193.3 190.9 188.3C186.5 183.3 183.7 175.4 183.7 163.5L179.7 163.5L175.7 163.5C175.7 176.6 178.8 186.6 184.9 193.6C191 200.6 199.7 204 209.5 204.7C229 206.1 254.5 197.4 280 184C305.7 170.5 332.1 151.9 353.5 132.7C374.9 113.6 391.8 93.4 398.1 76.7L394.3 75.3ZM494 115.8L493.5 111.8C423.7 120.3 375.2 99.3 350.8 73.6C338.5 60.8 332.5 46.9 332.3 35.1C332.2 23.6 337.7 13.6 349.6 7.6L347.8 4.1L346 0.5C331.4 7.8 324.2 20.6 324.3 35.2C324.5 49.6 331.7 65.3 345 79.1C371.5 107 422.7 128.5 494.5 119.8L494 115.8ZM347.8 4.1L349.6 7.6C362.3 1.3 377.8 3.2 387.5 13.5C397.1 23.6 402 43.1 390.6 73.9L394.3 75.3L398.1 76.7C410.1 44.4 405.8 21.2 393.3 8C380.9 -5.1 361.5 -7.3 346 0.5L347.8 4.1Z';

/** Знак Kleal (вертушка) из кадра A.15, 70×70. */
const MARK = 'M13.9 27.3C25.4 21.6 34 34.6 28.4 40.1C26.1 42.4 24.6 45.3 24.1 48.5C23.7 51.7 24.3 54.9 26 57.7C32.3 69.4 46.7 67.4 46.7 67.4C32.7 73.8 14.5 67.8 6.9 55.1C6.8 55 -3.1 35.8 13.9 27.3ZM67.4 23.4C73.8 37.4 67.8 55.6 55.1 63.2C55 63.2 35.8 73.1 27.3 56.1C21.6 44.6 34.6 36.1 40.1 41.7C42.4 44 45.3 45.5 48.5 45.9C51.7 46.3 55 45.7 57.7 44.1C69.4 37.8 67.4 23.5 67.4 23.4ZM15 6.9C15 6.9 34.3 -3.1 42.8 13.9C48.5 25.4 35.5 34 29.9 28.4C27.7 26.1 24.7 24.6 21.5 24.2C18.3 23.7 15.1 24.4 12.3 26C0.6 32.3 2.6 46.6 2.6 46.7C-3.8 32.7 2.2 14.5 15 6.9ZM23.4 2.6C37.4 -3.8 55.6 2.2 63.2 14.9C63.3 15 73.2 34.2 56.2 42.7C44.7 48.4 36 35.4 41.7 29.9C44 27.6 45.5 24.7 45.9 21.5C46.3 18.4 45.7 15.1 44.1 12.4C37.8 0.6 23.4 2.7 23.4 2.6Z';

/** Ширина и высота ленты в координатах макета; рамка с запасом под толщину обводки. */
const RW = 521;
const RH = 240;

export function RibbonTile({
  width,
  children,
  x = -65,
  tileTop = 152,
}: {
  width: number;
  children: React.ReactNode;
  /** Левый край ленты в координатах макета: в A.03.3 это −72, в A.15 −65. */
  x?: number;
  /** Верх плитки от верха ленты: в A.03.3 182, в A.15 152. */
  tileTop?: number;
}) {
  const reduced = useReducedMotion();
  // Масштаб от макета (390 точек ширины). Лента шире экрана и уходит за оба края — так в борде.
  const k = width / 390;
  const reveal = useSharedValue(reduced ? 1 : 0);
  const pop = useSharedValue(reduced ? 1 : 0);

  useEffect(() => {
    if (reduced) return;
    reveal.value = withTiming(1, { duration: 1100, easing: Easing.inOut(Easing.cubic) });
    // Плитка проявляется, пока лента ещё тянется, — спокойно, без отскока.
    pop.value = withDelay(500, withTiming(1, { duration: 480, easing: Easing.out(Easing.cubic) }));
  }, [reduced, reveal, pop]);

  const clip = useAnimatedStyle(() => ({ width: (RW + 16) * k * reveal.value }));
  // Без прозрачности: стекло плитки под непрозрачностью < 1 не рисуется (ограничение UIKit).
  const tile = useAnimatedStyle(() => ({
    transform: [{ scale: 0.92 + pop.value * 0.08 }, { translateY: (1 - pop.value) * 6 }],
  }));

  return (
    <View style={{ width, height: Math.max(RH, tileTop + 96) * k + 8 }} pointerEvents="none">
      <Animated.View style={[s.clip, { left: (x - 8) * k, top: -8 * k, height: (RH + 16) * k }, clip]}>
        <Svg width={(RW + 16) * k} height={(RH + 16) * k} viewBox={`-8 -8 ${RW + 16} ${RH + 16}`}>
          <Path d={RIBBON} fill="#F2526B" />
        </Svg>
      </Animated.View>
      <Animated.View style={[s.tile, { left: 147 * k, top: tileTop * k }, tile]}>
        <GlassSurface tone="clear" radius={16} style={s.glass}>
          {children}
        </GlassSurface>
      </Animated.View>
    </View>
  );
}

/** Белый знак Kleal для плитки A.15. */
export function KlealMark({ size = 70 }: { size?: number }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 70 70">
      <Path d={MARK} fill="#FFFFFF" />
    </Svg>
  );
}

// ===== вид
const s = StyleSheet.create({
  clip: { position: 'absolute', overflow: 'hidden' },
  tile: {
    position: 'absolute',
    width: 96,
    height: 96,
    borderRadius: 16,
    shadowColor: '#F2526B',
    shadowOpacity: 0.25,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
  },
  glass: { flex: 1, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
});
