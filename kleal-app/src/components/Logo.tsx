/**
 * Логотип Kleal в двух видах, как в борде.
 *
 * `Wordmark` — капля и слово рядом (A.01, 190×61). `LogoMark` — одна капля крупно (A.03, 186×167).
 *
 * ОБА — ЭКСПОРТ ИЗ FIGMA, а не нарисованные заново. У капли внутри радиальный градиент, стеклянная
 * плёнка с размытием подложки, падающая и внутренняя тени; слово набрано вектором, а не шрифтом.
 * Повторить это на SVG в RN можно, но результат отличался бы — а логотип это ровно то место, где
 * «почти похоже» читается как ошибка. Поэтому картинка.
 *
 * Пропорции зашиты константами: у обоих знаков они постоянные, и вызывающему достаточно задать
 * ширину. Растягивать логотип по месту нельзя, поэтому высота считается, а не принимается.
 */
import React from 'react';
import { Image, StyleSheet, View } from 'react-native';
import Svg, { Defs, Ellipse, LinearGradient, Stop } from 'react-native-svg';
import { color } from '../theme';

/** Пропорции из борда: 190×61 и 186×167. */
const WORDMARK_RATIO = 61 / 190;
const MARK_RATIO = 167 / 186;

export function Wordmark({ width = 190 }: { width?: number }) {
  return (
    <Image
      accessibilityIgnoresInvertColors
      source={require('../../assets/art/logo-wordmark.png')}
      style={[s.img, { width, height: width * WORDMARK_RATIO }]}
      resizeMode="contain"
    />
  );
}

export function LogoMark({ width = 186 }: { width?: number }) {
  return (
    <Image
      accessibilityIgnoresInvertColors
      source={require('../../assets/art/logo-mark.png')}
      style={[s.img, { width, height: width * MARK_RATIO }]}
      resizeMode="contain"
    />
  );
}

/**
 * Мордочка Бадди в шапке разговора (кадры A.04–A.13).
 *
 * ЗДЕСЬ РИСУНОК, А НЕ КАРТИНКА — в отличие от логотипа. В шапке это не капля с бликом и тенью, а
 * простой круг с двумя глазами: заливка градиентом из фирменного красного в маджентовый и два
 * чёрных овала. Экспортировать такое файлом значит везти лишние килобайты и потерять чёткость на
 * маленьком размере — а тут знак ровно 49 точек, и вектор на нём выигрывает у растра заметно.
 *
 * Пропорции глаз из борда: два овала 7,7×9,2 с общим размахом 23,6 — то есть они узкие и высокие,
 * а не круглые. Круглые дают другое выражение, и это видно.
 */
export function LogoFace({ size = 49 }: { size?: number }) {
  const eyeW = (size * 7.7) / 49;
  const eyeH = (size * 9.2) / 49;
  const gap = (size * 23.6) / 49;                 // размах между центрами крайних точек
  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size} viewBox="0 0 100 100">
        <Defs>
          <LinearGradient id="face" x1="0.3" y1="0.39" x2="0.73" y2="1.4">
            <Stop offset="0" stopColor={color.primary} />
            <Stop offset="1" stopColor={color.brandMagenta} />
          </LinearGradient>
        </Defs>
        <Ellipse cx={50} cy={50} rx={50} ry={50} fill="url(#face)" />
        <Ellipse
          cx={50 - (gap / 2 - eyeW / 2) * (100 / size)}
          cy={48}
          rx={(eyeW / 2) * (100 / size)}
          ry={(eyeH / 2) * (100 / size)}
          fill={color.ink}
        />
        <Ellipse
          cx={50 + (gap / 2 - eyeW / 2) * (100 / size)}
          cy={48}
          rx={(eyeW / 2) * (100 / size)}
          ry={(eyeH / 2) * (100 / size)}
          fill={color.ink}
        />
      </Svg>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  img: { alignSelf: 'center' },
});
