/**
 * Экран успеха. Порт «Profile Success»: поздравление и сразу переход к созданию первого интента —
 * онбординг заканчивается не словами, а следующим действием.
 */
import React from 'react';
import { View, StyleSheet, Text } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLang, T } from '../src/i18n';
import { Btn } from '../src/components/ui';
import { color, radius, space, type } from '../src/theme';

export default function Done() {
  useLang();
  const insets = useSafeAreaInsets();
  return (
    <View style={[s.wrap, { paddingTop: insets.top }]}>
      <View style={s.body}>
        <View style={s.circle} />
        <Text style={s.h}>{T('Поздравляем!\nТы в игре!', 'Congratulation!\nYou are on the board!')}</Text>
      </View>
      <View style={[s.foot, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        {/* Ведёт в создание интента — экран следующего этапа переноса, поэтому пока заглушка. */}
        <Btn label={T('Создать интент', 'Create Intent')} disabled />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 22, paddingHorizontal: 28 },
  circle: { width: 170, height: 170, borderRadius: radius.full, backgroundColor: color.neutral100 },
  h: { ...type.h2, color: color.fg, textAlign: 'center' } as any,
  foot: { paddingHorizontal: 20, paddingTop: space.md },
});
