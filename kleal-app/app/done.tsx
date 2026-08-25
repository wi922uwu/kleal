/**
 * Финал онбординга — кадр A.15.
 *
 * Только поздравление: главный экран теперь свой (app/home.tsx), и сюда попадают ровно один раз —
 * сразу после того, как профиль записан. Нижняя панель показана потому же, почему и на борде:
 * человек должен увидеть, куда попал, ещё до первого действия.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { BlurView } from 'expo-blur';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { IconImagePlaceholder } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { Ambient, GLOW_DONE } from '../src/components/Ambient';
import { GlassPill } from '../src/components/Glass';
import { useLang } from '../src/i18n';
import { DONE_SCREEN } from '../src/onboarding';
import { color, displayFamily, glass, radius as rad, space, type } from '../src/theme';

export default function Done() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={s.wrap}>
      {/* Тот же тёплый фон, что на «Ты в деле»: оба кадра — исходы, а не шаги. */}
      <Ambient glows={GLOW_DONE} />
      <View style={[s.page, { paddingTop: insets.top }]}>
        <View style={s.body}>
          <View style={s.circle}>
            <BlurView intensity={glass.blur} tint="light" style={StyleSheet.absoluteFill} />
            <View
              style={[StyleSheet.absoluteFill, { backgroundColor: color.glassLight, opacity: glass.lightAlpha }]}
            />
            {/* Тот же значок-заглушка изображения, что на борде */}
            <IconImagePlaceholder size={55} />
          </View>
          {/* Гарнитура заголовка зависит от языка — см. displayFamily. */}
          <Text style={[s.title, { fontFamily: displayFamily(lang) }]}>{DONE_SCREEN.title()}</Text>
        </View>

        <View style={s.ctaWrap}>
          {/* Кнопка обещает создание интента — и открывает именно его. Главная подкладывается ВНИЗ,
              чтобы «назад» из создания вело на неё, а не обратно в поздравление. */}
          <GlassPill
            tone="brand"
            label={DONE_SCREEN.cta()}
            style={s.cta}
            onPress={() => { router.dismissTo('/home'); router.navigate('/create'); }}
          />
        </View>

        <BottomNav />
      </View>
    </View>
  );
}


const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  page: { flex: 1 },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 28, paddingHorizontal: 20 },
  /** Круг 200 и значок 55 внутри — размеры из кадра. */
  circle: {
    width: 200, height: 200, borderRadius: rad.full, overflow: 'hidden',
    alignItems: 'center', justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth, borderColor: '#FFFFFF88',
  },
  title: { ...type.display, color: color.fg, textAlign: 'center' } as any,
  ctaWrap: { paddingHorizontal: 20, marginBottom: space.lg },
  /** Кнопка финала ниже входной: 52 против 56 — так в кадре. */
  cta: { height: 52 },
});
