/**
 * A.03.3 — «Ты в деле».
 *
 * Показывается ТОЛЬКО новому. Борд разводит два исхода стрелками: новый аккаунт → A.03.3 → анкета
 * A.04; существующий → сразу на главную, и A.03.3 пропускается. Поэтому решение принимает экран
 * кода (по `isNew` с сервера), а не этот: сюда просто не приходят те, кому он не нужен.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { AUTH } from '../src/auth';
import { useLang } from '../src/i18n';
import { IconSpark } from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

export default function AuthDone() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 16 }]}>
      <View style={s.mid}>
        <View style={s.badge}><IconSpark size={40} /></View>
        <Text style={s.h}>{AUTH.doneTitle()}</Text>
        <Text style={s.note}>{AUTH.doneNote()}</Text>
      </View>

      {/*
        `replace`, а не переход: назад отсюда возвращаться некуда и незачем — код уже погашен,
        сессия выдана, а экран ввода кода за спиной означал бы кнопку в никуда.
      */}
      <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.replace('/chat')}>
        <Text style={s.ctaText}>{AUTH.setUp()}</Text>
      </Pressable>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, paddingHorizontal: 24, backgroundColor: color.bg },
  mid: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.md },
  badge: {
    width: 96, height: 96, borderRadius: 48, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginBottom: space.lg,
  },
  h: { ...type.h2, color: color.fg, textAlign: 'center' } as any,
  note: { ...type.body, color: color.muted, textAlign: 'center', paddingHorizontal: 12 } as any,
  cta: { height: 56, borderRadius: rad.full, backgroundColor: color.primary,
         alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
});
