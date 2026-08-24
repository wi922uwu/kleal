/**
 * Фирменный фон «Ambient · glass pilot» — общий слой входных экранов A.01–A.03.
 *
 * В борде это ОДИН компонент, положенный под welcome, под экран пользы и под вход: кремовая
 * подложка и три цветных пятна поверх. Здесь он тоже один — иначе три экрана разъехались бы в
 * оттенках при первой же правке, а заметить это можно только листая их подряд.
 *
 * ПОЧЕМУ SVG, А НЕ expo-linear-gradient. Пятна РАДИАЛЬНЫЕ, а `expo-linear-gradient` радиальных
 * не умеет вовсе — только линейные. `react-native-svg` уже стоит в проекте (им нарисована волна
 * на интро) и умеет оба вида, поэтому новой зависимости не понадобилось.
 *
 * Каждый экран задаёт СВОЮ силу пятен: на welcome снизу горит красный, на входе — розовый с
 * янтарём. Цвета при этом общие, из токенов.
 */
import React from 'react';
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import Svg, { Defs, Ellipse, RadialGradient, Rect, Stop, LinearGradient } from 'react-native-svg';
import { color } from '../theme';

/** Одно пятно: цвет, центр и радиусы в долях экрана, сила в центре. */
export type Glow = { c: string; x: number; y: number; rx: number; ry: number; a: number };

/** Пятна экрана A.01 · Welcome: кремовый верх, фирменный красный к низу. */
export const GLOW_WELCOME: Glow[] = [
  { c: color.ambientPink, x: 0.5, y: 0.86, rx: 0.95, ry: 0.5, a: 0.6 },
  { c: color.ambientViolet, x: 0.15, y: 0.62, rx: 0.7, ry: 0.4, a: 0.22 },
  { c: color.ambientAmber, x: 0.88, y: 0.72, rx: 0.6, ry: 0.35, a: 0.3 },
];

/** Пятна экрана A.03 · Sign in: розовое поле с янтарным углом. */
export const GLOW_SIGNIN: Glow[] = [
  { c: color.ambientPink, x: 0.42, y: 0.42, rx: 1.05, ry: 0.62, a: 0.5 },
  { c: color.ambientAmber, x: 0.92, y: 0.12, rx: 0.62, ry: 0.34, a: 0.45 },
  { c: color.ambientViolet, x: 0.08, y: 0.28, rx: 0.55, ry: 0.3, a: 0.16 },
];

export function Ambient({
  glows = GLOW_WELCOME,
  /** Нижняя заливка фирменным красным — только на welcome, где рука выходит из цвета. */
  bleed = 0,
}: {
  glows?: Glow[];
  bleed?: number;
}) {
  const { width: w, height: h } = useWindowDimensions();
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      <Svg width={w} height={h}>
        <Defs>
          {glows.map((g, i) => (
            <RadialGradient key={`g${i}`} id={`g${i}`}>
              <Stop offset="0" stopColor={g.c} stopOpacity={g.a} />
              <Stop offset="1" stopColor={g.c} stopOpacity={0} />
            </RadialGradient>
          ))}
          <LinearGradient id="bleed" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color.primary} stopOpacity={0} />
            <Stop offset="1" stopColor={color.primary} stopOpacity={1} />
          </LinearGradient>
        </Defs>
        <Rect x={0} y={0} width={w} height={h} fill={color.ambientBase} />
        {glows.map((g, i) => (
          <Ellipse
            key={`e${i}`}
            cx={g.x * w}
            cy={g.y * h}
            rx={g.rx * w}
            ry={g.ry * h}
            fill={`url(#g${i})`}
          />
        ))}
        {bleed > 0 && (
          <Rect x={0} y={h * (1 - bleed)} width={w} height={h * bleed} fill="url(#bleed)" />
        )}
      </Svg>
    </View>
  );
}
