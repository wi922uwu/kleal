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
import { useVideoPlayer, VideoView } from 'expo-video';
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

/**
 * Пятна экранов входа по коду (A.03.1–A.03.3).
 *
 * В борде фон этих кадров ЗАЛИВКА, а не поле пятен: человек читает подпись и набирает адрес, и
 * цветной фон под текстом мешал бы. Но обрывать фирменный слой на середине потока нельзя — до
 * этого было три цветных экрана подряд. Поэтому пятна те же, только едва различимые: узнаваемая
 * кремовая бумага с тёплым краем.
 */
export const GLOW_FORM: Glow[] = [
  { c: color.ambientPink, x: 0.5, y: 0.1, rx: 1.1, ry: 0.35, a: 0.14 },
  { c: color.ambientAmber, x: 0.95, y: 0.02, rx: 0.5, ry: 0.22, a: 0.16 },
];

/** A.03.3 · «Ты в деле»: одно тёплое пятно по центру — под иллюстрацией. */
export const GLOW_DONE: Glow[] = [
  { c: color.primary, x: 0.5, y: 0.42, rx: 0.95, ry: 0.45, a: 0.18 },
  { c: color.ambientAmber, x: 0.5, y: 0.6, rx: 0.7, ry: 0.3, a: 0.2 },
];

export function Ambient({
  glows = GLOW_WELCOME,
  /** Нижняя заливка фирменным красным — только на welcome, где рука выходит из цвета. */
  bleed = 0,
  /**
   * ЖИВАЯ ПОДЛОЖКА ВМЕСТО НАРИСОВАННОЙ. Ролик переливается сам, чего пятнами на SVG не сделать.
   *
   * Кладётся ПОВЕРХ нарисованной подложки, а не вместо неё, и это не лишняя работа: ролик десяти­
   * битный, и на части Android он может не раскодироваться вовсе. Тогда под ним остаётся ровно тот
   * фон, что был до сих пор, и экран выглядит как прежде, а не чёрным прямоугольником.
   *
   * Без звука и без органов управления: это фон, а не проигрыватель. Крутится по кругу.
   */
  video = false,
}: {
  glows?: Glow[];
  bleed?: number;
  video?: boolean;
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
      {video ? <AmbientVideo /> : null}
    </View>
  );
}

/**
 * Ролик заведён отдельным видом НАМЕРЕННО: `useVideoPlayer` — хук, и вызывать его в `Ambient`
 * значило бы заводить проигрыватель на каждом экране с фоном, включая те, где ролика нет.
 */
function AmbientVideo() {
  const player = useVideoPlayer(require('../../assets/video/ambient.mp4'), (p) => {
    p.loop = true;
    p.muted = true;
    p.play();
  });
  return (
    <VideoView
      style={StyleSheet.absoluteFill}
      player={player}
      contentFit="cover"
      nativeControls={false}
      pointerEvents="none"
    />
  );
}
