/**
 * КАПЛЯ KLEAL — маскот макета «First run» (Layer_1 в кадрах A.01, A.03, A.03.3 и шапке разговора).
 *
 * Устроена в макете из четырёх слоёв, и все четыре здесь: розовое свечение формы капли, шар
 * из фирменного красного в маджентовый, стеклянная оболочка поверх шара (белое 38% с кромкой) и
 * два глаза. Геометрия капли снята с Figma как есть (58×60), поэтому силуэт совпадает с бордом.
 *
 * ЖИВАЯ, НО СПОКОЙНАЯ. Капля изредка моргает — раз в несколько секунд, и всё. Парение (`float`)
 * выключено по умолчанию: покачивание на каждом экране читалось как суета. Глаза нарисованы
 * отдельными видами поверх SVG ровно ради моргания: сжать по вертикали вид дёшево, перерисовывать
 * SVG на каждый кадр — нет.
 * При «Уменьшить движение» капля стоит.
 */
import React, { useEffect } from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Path, RadialGradient, Stop } from 'react-native-svg';
import Animated, {
  Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withDelay, withRepeat, withSequence, withTiming,
} from 'react-native-reanimated';
import { color } from '../theme';

/** Силуэт капли из макета, 58×60. */
const DROP =
  'M28.9724 0C12.9657 0 0 12.4533 0 27.8133C0 42.56 12.0534 51.4933 25.6273 58.4267C27.4242 59.3333 ' +
  '28.5024 60 29 60C29.4976 60 30.5758 59.3333 32.3727 58.4267C45.9466 51.4933 57.9724 42.56 58 ' +
  '27.8133C58 12.4533 45.0343 0 29.0276 0L28.9724 0Z';

export function Blob({
  size = 58,
  float = false,
  blink = true,
  style,
}: {
  /** Ширина капли; высота выходит сама (60/58). */
  size?: number;
  float?: boolean;
  blink?: boolean;
  style?: ViewStyle;
}) {
  const reduced = useReducedMotion();
  const k = size / 58;
  const y = useSharedValue(0);
  const lid = useSharedValue(1);

  useEffect(() => {
    if (reduced) return;
    if (float) {
      y.value = withRepeat(
        withSequence(
          withTiming(-3 * k, { duration: 1700, easing: Easing.inOut(Easing.sin) }),
          withTiming(0, { duration: 1700, easing: Easing.inOut(Easing.sin) }),
        ),
        -1,
      );
    }
    if (blink) {
      lid.value = withRepeat(
        withSequence(
          withDelay(6200, withTiming(0.12, { duration: 80 })),
          withTiming(1, { duration: 140 }),
        ),
        -1,
      );
    }
  }, [reduced, float, blink, k, y, lid]);

  const body = useAnimatedStyle(() => ({ transform: [{ translateY: y.value }] }));
  const eyes = useAnimatedStyle(() => ({ transform: [{ scaleY: lid.value }] }));

  const eyeW = 7.74 * k;
  const eyeH = 9.07 * k;
  return (
    <Animated.View style={[{ width: size, height: size * (60 / 58) }, body, style]} pointerEvents="none">
      <Svg width={size} height={size * (60 / 58)} viewBox="0 0 58 60">
        <Defs>
          <RadialGradient id="bGlow" cx="0.5" cy="0.45" r="0.6">
            <Stop offset="0" stopColor="#F05153" stopOpacity={1} />
            <Stop offset="1" stopColor="#FFFFFF" stopOpacity={1} />
          </RadialGradient>
          <LinearGradient id="bBall" x1="0.25" y1="0.2" x2="0.85" y2="1.1">
            <Stop offset="0" stopColor={color.primary} />
            <Stop offset="1" stopColor={color.brandMagenta} />
          </LinearGradient>
          <LinearGradient id="bEdge" x1="0.2" y1="0" x2="0.8" y2="1">
            <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.75} />
            <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0.08} />
          </LinearGradient>
          <LinearGradient id="bShine" x1="0.5" y1="0" x2="0.5" y2="1">
            <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.55} />
            <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
          </LinearGradient>
        </Defs>
        <Path d={DROP} fill="url(#bGlow)" />
        <Circle cx={28.55} cy={25.6} r={24.55} fill="url(#bBall)" />
        {/* Стеклянная оболочка: белая плёнка и кромка — «вода» вокруг шара. */}
        <Path d={DROP} fill="#FFFFFF" fillOpacity={0.38} stroke="url(#bEdge)" strokeOpacity={0.66} strokeWidth={1} />
        {/* Блик по верхней кромке — внутренние тени борда (белое 60%/53%), нарисованные градиентом. */}
        <Path d="M10 14 C 16 4, 42 4, 48 14 C 40 9, 18 9, 10 14 Z" fill="url(#bShine)" />
      </Svg>
      <Animated.View style={[s.eyes, { top: 13.1 * k, left: 17.2 * k, gap: (33.2 - 17.2 - 7.74) * k }, eyes]}>
        <View style={[s.eye, { width: eyeW, height: eyeH, borderRadius: eyeW }]} />
        <View style={[s.eye, { width: eyeW, height: eyeH, borderRadius: eyeW }]} />
      </Animated.View>
    </Animated.View>
  );
}

// ===== вид
const s = StyleSheet.create({
  eyes: { position: 'absolute', flexDirection: 'row' },
  eye: { backgroundColor: '#000000' },
});
