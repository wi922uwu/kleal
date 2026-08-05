/**
 * Вход по логину и паролю. Порт «rAuthPw».
 *
 * Намеренно маленький, как и на вебе: ни сброса пароля, ни ограничения попыток, ни подтверждения
 * почты. Пароль не задерживается дальше запроса — сервер хранит PBKDF2-хеш с собственной солью,
 * в своём файле, отдельно от матчингового стора.
 */
import React, { useState } from 'react';
import { View, StyleSheet, Text, KeyboardAvoidingView, Platform, ScrollView } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { AUTH_TERMS } from '../src/onboarding';
import { useLang, T } from '../src/i18n';
import { patch, applyDefaults } from '../src/state';
import { onboarding } from '../src/api';
import { Btn, Field } from '../src/components/ui';
import { color, space, type } from '../src/theme';

export default function Login() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [login, setLogin] = useState('');
  const [pw, setPw] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState<'in' | 'up' | null>(null);

  const ok = login.trim().length >= 2 && pw.length >= 6;

  // Сервер отдаёт ошибку строкой, а не кодом. Разбираем ровно те строки, что он шлёт.
  //
  // Для входа он НАМЕРЕННО отвечает одинаково на неизвестный логин и на неверный пароль: разные
  // сообщения — это бесплатный способ узнать, какие логины существуют. Здесь это свойство
  // сохраняется: одна фраза на оба случая, и различать их на клиенте нельзя.
  const errorText = (e?: string) =>
    e === 'login taken' ? T('Такой логин уже занят', 'That login is taken')
    : e === 'login too short' ? T('Логин слишком короткий', 'That login is too short')
    : e === 'password too short' ? T('Пароль короче шести символов', 'Password is shorter than six characters')
    : e === 'wrong login or password' ? T('Неверный логин или пароль', 'Wrong login or password')
    : T('Не получилось. Попробуй ещё раз.', "That didn't work. Try again.");

  const run = async (mode: 'in' | 'up') => {
    setBusy(mode);
    setMsg('');
    try {
      const r = mode === 'in'
        ? await onboarding.signin(login.trim(), pw)
        : await onboarding.signup(login.trim(), pw);
      if (r && r.ok) {
        const res: any = r;
        // Сервер отдаёт вход ВМЕСТЕ с сохранённым профилем — «so the app can skip onboarding
        // entirely». Клиент это игнорировал, и человек, входящий на новом устройстве или после
        // выхода из аккаунта, проходил всю анкету заново поверх профиля, который уже лежит на
        // сервере. Теперь профиль забирается, и онбординг пропускается.
        if (res.hasProfile && res.profile && typeof res.profile === 'object') {
          patch({ login: login.trim(), done: true, profile: res.profile });
          router.replace('/home');
          return;
        }
        patch({ login: login.trim() });
        applyDefaults();
        router.push('/chat');
        return;
      }
      setMsg(errorText(r?.error));
    } catch {
      setMsg(T('Нет связи с сервером', 'No connection to the server'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[s.wrap, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}
      >
        <Text style={s.h}>{T('Вход по логину', 'Sign in')}</Text>
        <Text style={s.sub}>
          {T(
            'Войди, чтобы вернуться в свой профиль, или создай новый логин.',
            'Sign in to pick your profile back up, or create a new login.'
          )}
        </Text>

        <View style={{ gap: space.md, marginTop: 24 }}>
          <Field
            label={T('Логин', 'Login')}
            value={login}
            onChangeText={setLogin}
            autoCapitalize="none"
            autoCorrect={false}
            textContentType="username"
            placeholder={T('например, ivan', 'e.g. ivan')}
          />
          <Field
            label={T('Пароль', 'Password')}
            value={pw}
            onChangeText={setPw}
            secureTextEntry
            textContentType="password"
            placeholder={T('минимум 6 символов', 'at least 6 characters')}
          />
        </View>

        <Text style={s.err}>{msg}</Text>

        <View style={{ gap: space.md, marginTop: 'auto' }}>
          <Btn label={T('Войти', 'Sign in')} disabled={!ok} busy={busy === 'in'} onPress={() => run('in')} />
          <Btn
            kind="secondary"
            label={T('Создать логин', 'Create a login')}
            disabled={!ok}
            busy={busy === 'up'}
            onPress={() => run('up')}
          />
          <Text style={s.terms}>{AUTH_TERMS()}</Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  wrap: { flexGrow: 1, paddingHorizontal: 24, backgroundColor: color.bg },
  h: { ...type.h2, color: color.fg } as any,
  sub: { ...type.body, color: color.muted, marginTop: space.sm } as any,
  err: { ...type.bodySmall, color: color.primary, minHeight: 20, marginTop: space.md } as any,
  terms: { ...type.caption, color: color.muted, textAlign: 'center' } as any,
});
