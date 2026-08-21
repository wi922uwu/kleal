/**
 * A.03.1 — «Какая у тебя почта?».
 *
 * Первый из двух экранов входа по коду. Здесь только адрес: код спрашивает следующий.
 *
 * ПОЧЕМУ ПРОВЕРКА АДРЕСА ЗДЕСЬ, А НЕ ТОЛЬКО НА СЕРВЕРЕ. Кадр A.03.1b показывает ошибку рядом с
 * полем, до всякой отправки. Человек, опечатавшийся в «alex@@mail», должен узнать об этом сразу,
 * а не через секунду ожидания и не письмом, которого не будет. Сервер проверяет то же самое —
 * потому что клиенту верить нельзя, — но это второй рубеж, а не первый.
 */
import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, Pressable, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { auth } from '../src/api';
import { AUTH, looksLikeEmail } from '../src/auth';
import { AUTH_TERMS } from '../src/onboarding';
import { useLang, T, replyLang } from '../src/i18n';
import { color, radius as rad, space, type } from '../src/theme';

export default function AuthEmail() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<{ title: string; note: string } | null>(null);

  const ok = looksLikeEmail(email);

  const go = async () => {
    if (busy) return;
    // Кадр A.03.1b: кнопка выключена, пока адрес не похож на адрес, но по нажатию на выключенную
    // ничего не происходит — поэтому ошибку показываем и здесь, если человек всё-таки дожал.
    if (!ok) { setErr({ title: AUTH.badEmailTitle(), note: AUTH.badEmailNote() }); return; }
    setBusy(true);
    setErr(null);
    try {
      const r: any = await auth.requestCode(email.trim(), replyLang());
      if (r?.ok) {
        // `dev_code` приходит только при включённом на сервере рубильнике отладки; в обычной
        // работе его в ответе нет, и параметр уезжает пустым.
        router.navigate({
          pathname: '/auth-code',
          params: { email: email.trim(), dev: String(r?.dev_code || '') },
        });
        return;
      }
      if (r?.error === 'bad email') setErr({ title: AUTH.badEmailTitle(), note: AUTH.badEmailNote() });
      else if (r?.error === 'too many') setErr({ title: AUTH.tooManyTitle(), note: AUTH.tooManyNote() });
      // Повтор здесь не поможет никогда — и говорить «через минуту» значит гонять по кругу.
      else if (r?.error === 'not allowed') setErr({ title: AUTH.notAllowedTitle(), note: AUTH.notAllowedNote() });
      else setErr({ title: AUTH.sendFailedTitle(), note: AUTH.sendFailedNote() });
    } catch {
      setErr({ title: AUTH.sendFailedTitle(), note: AUTH.offline() });
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: color.bg }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={[s.wrap, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 16 }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={T('Назад', 'Back')}
          style={s.back}
          onPress={() => (router.canGoBack() ? router.back() : router.replace('/auth'))}
        >
          <Text style={s.backGlyph}>‹</Text>
        </Pressable>

        <Text style={s.h}>{AUTH.emailTitle()}</Text>
        <Text style={s.note}>{AUTH.emailNote()}</Text>

        <Text style={s.label}>{AUTH.emailLabel()}</Text>
        <TextInput
          style={[s.input, err && s.inputBad]}
          value={email}
          onChangeText={(v) => { setEmail(v); if (err) setErr(null); }}
          placeholder={AUTH.emailPlaceholder()}
          placeholderTextColor={color.neutral400}
          keyboardType="email-address"
          inputMode="email"
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          textContentType="emailAddress"
          returnKeyType="go"
          onSubmitEditing={go}
          autoFocus
          accessibilityLabel={AUTH.emailLabel()}
        />

        {err ? (
          <View style={s.errBox}>
            <Text style={s.errTitle}>{err.title}</Text>
            <Text style={s.errNote}>{err.note}</Text>
          </View>
        ) : null}

        <View style={{ flex: 1 }} />

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: !ok || busy, busy }}
          disabled={!ok || busy}
          style={[s.cta, (!ok || busy) && s.ctaOff]}
          onPress={go}
        >
          {busy ? <ActivityIndicator color={color.onPrimary} />
                : <Text style={s.ctaText}>{AUTH.continue()}</Text>}
        </Pressable>
        <Text style={s.terms}>{AUTH_TERMS()}</Text>
      </View>
    </KeyboardAvoidingView>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, paddingHorizontal: 24 },
  back: { width: 44, height: 44, borderRadius: 22, backgroundColor: color.card,
          alignItems: 'center', justifyContent: 'center', marginBottom: space.lg },
  backGlyph: { fontSize: 24, lineHeight: 26, color: color.fg, marginTop: -2 },
  h: { ...type.h2, color: color.fg } as any,
  note: { ...type.body, color: color.muted, marginTop: space.sm } as any,
  label: { ...type.caption, color: color.muted, marginTop: space.xl, marginBottom: 6 } as any,
  input: {
    height: 56, borderRadius: rad.lg, backgroundColor: color.card, paddingHorizontal: 16,
    ...type.body, color: color.fg, borderWidth: 1, borderColor: color.line,
  } as any,
  inputBad: { borderColor: color.danger },
  errBox: { marginTop: space.md, padding: space.md, borderRadius: rad.lg, backgroundColor: color.dangerBg },
  errTitle: { ...type.labelMedium, color: color.danger, fontWeight: '700' } as any,
  errNote: { ...type.bodySmall, color: color.danger, marginTop: 2 } as any,
  cta: { height: 56, borderRadius: rad.full, backgroundColor: color.primary,
         alignItems: 'center', justifyContent: 'center' },
  ctaOff: { opacity: 0.45 },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  terms: { ...type.caption, color: color.muted, textAlign: 'center', marginTop: space.md } as any,
});
