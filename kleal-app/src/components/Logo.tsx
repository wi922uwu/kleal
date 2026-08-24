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
import { Image, StyleSheet } from 'react-native';

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

// ===== вид
const s = StyleSheet.create({
  img: { alignSelf: 'center' },
});
