/**
 * Финал онбординга — кадр A.15.
 *
 * Только поздравление: главный экран теперь свой (app/home.tsx), и сюда попадают ровно один раз —
 * сразу после того, как профиль записан. Нижняя панель показана потому же, почему и на борде:
 * человек должен увидеть, куда попал, ещё до первого действия.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { IconImagePlaceholder } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { useLang } from '../src/i18n';
import { DONE_SCREEN } from '../src/onboarding';
import { color, radius as rad, type } from '../src/theme';

export default function Done() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={[s.wrap, { paddingTop: insets.top }]}>
      <View style={s.body}>
        <View style={s.circle}>
          {/* Тот же значок-заглушка изображения, что на борде */}
          <IconImagePlaceholder size={64} />
        </View>
        <Text style={s.title}>{DONE_SCREEN.title()}</Text>
      </View>

      <View style={s.ctaWrap}>
        {/* Кнопка обещает создание интента — и открывает именно его. Главная подкладывается ВНИЗ,
            чтобы «назад» из создания вело на неё, а не обратно в поздравление. */}
        <Pressable
          accessibilityRole="button"
          style={s.cta}
          onPress={() => { router.replace('/home'); router.push('/create'); }}
        >
          <Text style={s.ctaText}>{DONE_SCREEN.cta()}</Text>
        </Pressable>
      </View>

      <BottomNav />
    </View>
  );
}


const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 30, paddingHorizontal: 28 },
  circle: {
    width: 190, height: 190, borderRadius: rad.full, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  title: { fontSize: 26, lineHeight: 34, fontWeight: '700', color: color.fg, textAlign: 'center' },
  ctaWrap: { paddingHorizontal: 20, marginBottom: 46 },
  cta: { height: 54, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,

});
