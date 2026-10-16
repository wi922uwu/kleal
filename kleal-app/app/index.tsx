/**
 * A.01 · Welcome — первый кадр приложения.
 *
 * Здесь нет ни одной кнопки, и это не упущение борда: кадр держится ровно столько, сколько нужно,
 * чтобы прочитать логотип, и сам уходит на экран пользы. Тап ускоряет — ждать бренд-заставку
 * никто не обязан.
 *
 * ГЕЙТ ЖИВЁТ ЗДЕСЬ, потому что это самый первый экран. Кто уже в аккаунте и прошёл онбординг —
 * тот сразу в приложении и заставки не видит. Проверка ОДНОКРАТНАЯ, на монтировании: раньше она
 * была подпиской на состояние, и в момент, когда сводка дописывала профиль, интро из-под низа
 * делало replace('/home') поверх уже открытого экрана. Тот же разбор — в комментарии к прежней
 * версии этого гейта.
 */
import React, { useEffect, useRef } from 'react';
import { Image, Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Animated, { Easing, FadeIn, FadeInDown, useReducedMotion } from 'react-native-reanimated';
import { Ambient, GLOW_WELCOME } from '../src/components/Ambient';
import { Blob } from '../src/components/Blob';
import { WELCOME_A11Y } from '../src/onboarding';
import { useLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { font, space } from '../src/theme';

/** Сколько держится заставка, если её не торопить. */
const HOLD_MS = 1800;

export default function Welcome() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const reduced = useReducedMotion();

  // Имя `gated` — не вкусовщина: на него смотрит сторож в tools/regressions_test.js, который
  // держит правило «переход одноразовый». Переименование тихо снимет проверку.
  const gated = useRef(false);
  const go = () => {
    if (gated.current) return;
    gated.current = true;
    // replace: заставка не должна оставаться в истории позади онбординга — «назад» с экрана
    // пользы означает выход из приложения, а не возврат к логотипу.
    /*
      ВОШЁЛ, НО АНКЕТУ НЕ ЗАКОНЧИЛ — прямо в анкету, а не на вступление. Раньше такой человек после
      перезапуска попадал на экран пользы и снова ко входу, вводил почту заново — и если вводил
      ДРУГУЮ, получал анкету прежнего аккаунта (владелец, 27.09). Черновик теперь привязан к
      аккаунту (state.ts, `signedIn`), а сюда — только тот, чья сессия жива.
    */
    router.replace(st.login && st.done ? '/home' : st.login && st.session ? '/chat' : '/intro');
  };

  useEffect(() => {
    const t = setTimeout(go, HOLD_MS);
    return () => clearTimeout(t);
  }, []);

  return (
    <Pressable accessibilityRole="button" accessibilityLabel={WELCOME_A11Y()} onPress={go} style={s.wrap}>
      <Ambient glows={GLOW_WELCOME} bleed={0.42} />
      {/*
        ЛОГОТИП МАКЕТА: капля и слово «kleal» набраны, а не картинкой. Слово — TASA Orbiter 48, как в
        кадре; капля живая (изредка моргает). Знак проявляется тихо, одним движением.
      */}
      <View style={[s.mark, { marginTop: insets.top + height * 0.13 }]}>
        <Animated.View entering={reduced ? undefined : FadeIn.duration(500)}>
          <Blob size={58} />
        </Animated.View>
        <Animated.Text
          entering={reduced ? undefined : FadeIn.delay(120).duration(500)}
          style={s.word}
          accessibilityElementsHidden
        >
          kleal
        </Animated.Text>
      </View>
      {/*
        Рука выходит СНИЗУ и обрезается краем экрана — так в борде. Прибита к низу: при любой высоте
        экрана обрезается низ запястья, а не пальцы. Поднимается один раз и плавно замедляется —
        главное движение экрана, «привет» от продукта; отскока нет.
      */}
      <Animated.View
        style={s.handBox}
        entering={reduced ? FadeIn : FadeInDown.delay(240).duration(800).easing(Easing.out(Easing.cubic)).withInitialValues({ transform: [{ translateY: 120 }] })}
      >
        <Image source={require('../assets/art/welcome-hand.png')} style={s.hand} resizeMode="contain" />
      </Animated.View>
    </Pressable>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, alignItems: 'center' },
  mark: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  word: { fontFamily: font.display, fontSize: 48, lineHeight: 52, letterSpacing: -0.72, color: '#000000' },
  handBox: { position: 'absolute', bottom: 0, width: 212, height: 548 },
  hand: { width: 212, height: 548 },
});
