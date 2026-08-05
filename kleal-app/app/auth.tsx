/**
 * Экран входа. Порт «rAuth».
 *
 * Apple и Google здесь пока НЕ настоящие — в вебовой версии они тоже просто помечают authMethod и
 * идут дальше. Оставлено ровно так же и подписано в коде, чтобы никто не принял их за рабочий вход:
 * настоящий OAuth — это отдельная задача этапа аутентификации, а не кнопка на этом экране.
 */
import React from 'react';
import { View, StyleSheet, Text, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { AUTH_TERMS } from '../src/onboarding';
import { useLang, T } from '../src/i18n';
import { patch, applyDefaults } from '../src/state';
import { Btn } from '../src/components/ui';
import { color, space, type } from '../src/theme';

export default function Auth() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const skipTo = (method: string) => {
    patch({ authMethod: method });
    applyDefaults();
    router.push('/chat');
  };

  return (
    <ScrollView
      contentContainerStyle={[s.wrap, { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 24 }]}
    >
      <View style={s.top}>
        <Text style={s.mark}>kleal</Text>
        <Text style={s.h}>{T('Найди своих', 'Meet your people')}</Text>
        <Text style={s.sub}>
          {T('Войди или создай аккаунт, чтобы начать.', 'Sign in or create your account to get started.')}
        </Text>
      </View>

      <View style={s.btns}>
        <Btn kind="dark" label={T('Продолжить с Apple', 'Continue with Apple')} onPress={() => skipTo('apple')} />
        <Btn kind="ghost" label={T('Продолжить с Google', 'Continue with Google')} onPress={() => skipTo('google')} />
        <Btn kind="primary" label={T('Продолжить по почте', 'Continue with email')} onPress={() => skipTo('email')} />
        <Btn kind="ghost" label={T('Логин и пароль', 'Login and password')} onPress={() => router.push('/login')} />
      </View>

      <Text style={s.terms}>{AUTH_TERMS()}</Text>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  wrap: { flexGrow: 1, paddingHorizontal: 24, backgroundColor: color.bg },
  top: { gap: space.sm, marginBottom: 32 },
  mark: { fontSize: 22, fontWeight: '700', color: color.primary, marginBottom: space.lg },
  h: { ...type.h2, color: color.fg } as any,
  sub: { ...type.body, color: color.muted } as any,
  btns: { gap: space.md },
  terms: { ...type.caption, color: color.muted, textAlign: 'center', marginTop: 'auto', paddingTop: 24 } as any,
});
