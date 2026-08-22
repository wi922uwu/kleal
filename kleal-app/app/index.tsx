/**
 * Интро — три слайда. Порт «rSplash» из вебовой реализации.
 *
 * Волна снизу и тёмная кнопка на ней — узнаваемая часть экрана, поэтому нарисована фигурой, а не
 * заменена на обычную кнопку: та же кривая, что в SVG прототипа.
 */
import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Pressable, Text, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Svg, { Path } from 'react-native-svg';
import { SLIDES } from '../src/onboarding';
import { useLang, T } from '../src/i18n';
import { useOnb, patch } from '../src/state';
import { color, radius, space, type } from '../src/theme';

export default function Splash() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();

  /**
   * Кто уже в аккаунте и прошёл онбординг — сразу в приложение, минуя интро и анкету.
   *
   * replace, а не push: интро не должно оставаться в истории позади главного экрана.
   *
   * ОДИН РАЗ, НА ЗАПУСКЕ. Это правило старта, а не живое наблюдение за `done`. Раньше эффект
   * следил за ним постоянно — а интро при этом остаётся ЖИВЫМ в стеке под всеми экранами
   * онбординга, потому что дальше идут через push. И в момент, когда сводка дописывала профиль и
   * ставила `done: true`, интро из-под низа делало replace('/home') поверх только что открытого
   * профиля: человек жал «Все настройки профиля», а попадал на главный экран (сообщено с
   * телефона). Кнопка при этом была совершенно исправна — уводило её чужое правило.
   *
   * Читать состояние на монтировании безопасно: корневой макет не рисует ни одного экрана, пока
   * restore() не поднимет сохранённое.
   */
  const gated = useRef(false);
  useEffect(() => {
    if (gated.current) return;
    gated.current = true;
    if (st.login && st.done) router.replace('/home');
  }, []);

  const slides = SLIDES();
  const i = Math.min(st.slide, slides.length - 1);
  const sl = slides[i];
  const last = i === slides.length - 1;

  const next = () => (last ? router.navigate('/auth') : patch({ slide: i + 1 }));

  const waveH = 160;
  return (
    <View style={[s.wrap, { paddingTop: insets.top }]}>
      <View style={s.body}>
        <View style={s.illus} />
        <Text style={s.h}>{sl.title}</Text>
        <Text style={s.sub}>{sl.sub}</Text>
        <View style={s.dots}>
          {slides.map((_, n) => (
            <View key={n} style={[s.dot, n === i && s.dotOn]} />
          ))}
        </View>
      </View>

      <Pressable onPress={next} accessibilityRole="button" style={s.wave}>
        <Svg width={width} height={waveH} viewBox="0 0 390 160" preserveAspectRatio="none">
          <Path d="M0 132 C 78 132 120 20 195 20 C 270 20 312 132 390 132 L390 160 L0 160 Z" fill={color.ink} />
        </Svg>
        <View style={[s.btnWrap, { bottom: Math.max(insets.bottom, 16) }]}>
          <Text style={s.btnText}>{T('Начать', "Let's Start")}</Text>
        </View>
      </Pressable>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  body: { flex: 1, paddingHorizontal: 28, alignItems: 'center', justifyContent: 'center', gap: space.lg },
  illus: {
    width: 190,
    height: 190,
    borderRadius: radius.full,
    backgroundColor: color.neutral100,
    marginBottom: space.sm,
  },
  h: { ...type.h2, color: color.fg, textAlign: 'center' } as any,
  sub: { ...type.body, color: color.muted, textAlign: 'center' } as any,
  dots: { flexDirection: 'row', gap: 6, marginTop: space.sm },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: color.neutral300 },
  dotOn: { width: 18, backgroundColor: color.primary },
  wave: { height: 160, justifyContent: 'flex-end' },
  btnWrap: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  btnText: { ...type.button, color: color.onPrimary } as any,
});
