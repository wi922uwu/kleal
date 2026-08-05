/**
 * Финал онбординга — кадр A.15.
 *
 * Нижняя панель здесь появляется впервые и это не декорация: борд показывает её именно на этом
 * кадре, чтобы человек увидел, куда он попал, ещё до первого действия. Сами вкладки — следующий
 * этап переноса; «Создать интент» уже ведёт в мастер OF.04–OF.10.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { IconIntents, IconSearch, IconMessages, IconProfile, IconSpark, IconImagePlaceholder } from '../src/components/icons';
import { useLang } from '../src/i18n';
import { DONE_SCREEN, NAV } from '../src/onboarding';
import { color, radius as rad, type } from '../src/theme';

export default function Done() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const nav = NAV();

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
        <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.push('/intent')}>
          <Text style={s.ctaText}>{DONE_SCREEN.cta()}</Text>
        </Pressable>
      </View>

      <View style={[s.nav, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <View style={s.navBar}>
          <NavItem label={nav[0]} Icon={IconIntents} />
          <NavItem label={nav[1]} Icon={IconSearch} />
          <View style={{ width: 64 }} />
          <NavItem label={nav[2]} Icon={IconMessages} />
          {/* Из четырёх вкладок пока ведёт куда-то одна — остальные экраны ещё не перенесены.
              Нажатие на нарисованную вкладку, которая молчит, читается как поломка, поэтому
              работающая отличается цветом, а не только тем, что срабатывает. */}
          <NavItem label={nav[3]} Icon={IconProfile} onPress={() => router.push('/profile')} />
        </View>
        <Pressable accessibilityRole="button" style={s.fab} onPress={() => router.push('/intent')}>
          <IconSpark size={28} />
        </Pressable>
      </View>
    </View>
  );
}

function NavItem({
  label, Icon, onPress,
}: {
  label: string;
  Icon: (p: any) => React.ReactElement;
  onPress?: () => void;
}) {
  const live = !!onPress;
  return (
    <Pressable
      accessibilityRole={live ? 'button' : undefined}
      accessibilityState={{ disabled: !live }}
      onPress={onPress}
      style={({ pressed }) => [s.navItem, pressed && live && { opacity: 0.7 }]}
    >
      <Icon size={24} c={live ? color.fg : color.muted} />
      <Text style={[s.navLabel, live && { color: color.fg }]}>{label}</Text>
    </Pressable>
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

  nav: { paddingTop: 0, paddingHorizontal: 14 },
  navBar: {
    height: 68, borderRadius: 34, backgroundColor: color.card,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around',
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 3,
  },
  navItem: { alignItems: 'center', gap: 3, width: 58 },
  navLabel: { fontSize: 10, lineHeight: 14, color: color.muted, fontWeight: '500' },
  fab: {
    position: 'absolute', alignSelf: 'center', top: -14,
    width: 62, height: 62, borderRadius: 31, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: color.primary, shadowOpacity: 0.45, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 8,
  },
});
