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
import { Ambient, GLOW_WELCOME } from '../src/components/Ambient';
import { Wordmark } from '../src/components/Logo';
import { WELCOME_A11Y } from '../src/onboarding';
import { useLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { space } from '../src/theme';

/** Сколько держится заставка, если её не торопить. */
const HOLD_MS = 1800;

export default function Welcome() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();

  // Имя `gated` — не вкусовщина: на него смотрит сторож в tools/regressions_test.js, который
  // держит правило «переход одноразовый». Переименование тихо снимет проверку.
  const gated = useRef(false);
  const go = () => {
    if (gated.current) return;
    gated.current = true;
    // replace: заставка не должна оставаться в истории позади онбординга — «назад» с экрана
    // пользы означает выход из приложения, а не возврат к логотипу.
    router.replace(st.login && st.done ? '/home' : '/intro');
  };

  useEffect(() => {
    const t = setTimeout(go, HOLD_MS);
    return () => clearTimeout(t);
  }, []);

  return (
    <Pressable accessibilityRole="button" accessibilityLabel={WELCOME_A11Y()} onPress={go} style={s.wrap}>
      <Ambient glows={GLOW_WELCOME} bleed={0.42} />
      <View style={[s.mark, { marginTop: insets.top + height * 0.22 }]}>
        <Wordmark width={190} />
      </View>
      {/*
        Рука выходит СНИЗУ и обрезается краем экрана — так в борде. Поэтому она не вписывается в
        поток, а прибита к низу: при любой высоте экрана обрезается низ запястья, а не пальцы.
      */}
      <Image source={require('../assets/art/welcome-hand.png')} style={s.hand} resizeMode="contain" />
    </Pressable>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, alignItems: 'center' },
  mark: { alignItems: 'center', marginBottom: space.xl },
  hand: {
    position: 'absolute',
    bottom: 0,
    width: 212,
    height: 548,
  },
});
