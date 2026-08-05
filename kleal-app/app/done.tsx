/**
 * Финал онбординга — кадр A.15.
 *
 * Нижняя панель здесь появляется впервые и это не декорация: борд показывает её именно на этом
 * кадре, чтобы человек увидел, куда он попал, ещё до первого действия. Экраны за ней — следующий
 * этап переноса, поэтому кнопки пока не ведут никуда, и это видно по их состоянию.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Rect, Circle, Path } from 'react-native-svg';
import { useLang } from '../src/i18n';
import { DONE_SCREEN, NAV } from '../src/onboarding';
import { color, radius as rad, space, type } from '../src/theme';

export default function Done() {
  useLang();
  const insets = useSafeAreaInsets();
  const nav = NAV();

  return (
    <View style={[s.wrap, { paddingTop: insets.top }]}>
      <View style={s.body}>
        <View style={s.circle}>
          {/* Тот же значок-заглушка изображения, что на борде */}
          <Svg width={64} height={64} viewBox="0 0 24 24" fill="none" stroke={color.neutral400} strokeWidth={1.4}>
            <Rect x={3} y={4} width={18} height={16} rx={3} />
            <Circle cx={9} cy={10} r={2} />
            <Path d="M4 18l5.5-5 4 3.5L17 13l3 3" />
          </Svg>
        </View>
        <Text style={s.title}>{DONE_SCREEN.title()}</Text>
      </View>

      <View style={s.ctaWrap}>
        <Pressable accessibilityRole="button" style={s.cta}>
          <Text style={s.ctaText}>{DONE_SCREEN.cta()}</Text>
        </Pressable>
      </View>

      <View style={[s.nav, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <View style={s.navBar}>
          <NavItem label={nav[0]} glyph="≡" />
          <NavItem label={nav[1]} glyph="⌕" />
          <View style={{ width: 64 }} />
          <NavItem label={nav[2]} glyph="◌" />
          <NavItem label={nav[3]} glyph="☺" />
        </View>
        <View style={s.fab}>
          <Text style={s.fabGlyph}>✦</Text>
        </View>
      </View>
    </View>
  );
}

function NavItem({ label, glyph }: { label: string; glyph: string }) {
  return (
    <View style={s.navItem}>
      <Text style={s.navGlyph}>{glyph}</Text>
      <Text style={s.navLabel}>{label}</Text>
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
  ctaWrap: { paddingHorizontal: 20 },
  cta: { height: 54, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,

  nav: { paddingTop: space.lg, paddingHorizontal: 16 },
  navBar: {
    height: 68, borderRadius: 34, backgroundColor: color.card,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around',
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 3,
  },
  navItem: { alignItems: 'center', gap: 3, width: 58 },
  navGlyph: { fontSize: 18, color: color.muted },
  navLabel: { fontSize: 10, lineHeight: 14, color: color.muted, fontWeight: '500' },
  fab: {
    position: 'absolute', alignSelf: 'center', top: space.lg - 6,
    width: 58, height: 58, borderRadius: 29, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: color.primary, shadowOpacity: 0.45, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 8,
  },
  fabGlyph: { color: color.onPrimary, fontSize: 24 },
});
