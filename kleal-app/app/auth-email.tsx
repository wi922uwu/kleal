/**
 * A.03.1 — «Какая у тебя почта?».
 *
 * Первый из двух экранов входа по коду. Здесь только адрес: код спрашивает следующий.
 *
 * ПОЧЕМУ ПРОВЕРКА АДРЕСА ЗДЕСЬ, А НЕ ТОЛЬКО НА СЕРВЕРЕ. Кадр A.03.1b показывает ошибку рядом с
 * полем, до всякой отправки. Человек, опечатавшийся в «alex@@mail», должен узнать об этом сразу,
 * а не через секунду ожидания и не письмом, которого не будет. Сервер проверяет то же самое —
 * потому что клиенту верить нельзя, — но это второй рубеж, а не первый.
 *
 * ВИД — ИЗ ТОГО ЖЕ НАБОРА, ЧТО ВХОД. Кремовая подложка, стеклянная кнопка «назад», стеклянное
 * поле, фирменная кнопка внизу. Экран стоит третьим подряд после welcome и входа, и обрывать на
 * нём фирменный слой значило бы уронить человека из продукта в системную форму.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, KeyboardAvoidingView, Platform } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { auth } from '../src/api';
import { AUTH, looksLikeEmail } from '../src/auth';
import { AUTH_TERMS } from '../src/onboarding';
import { useLang, T, replyLang } from '../src/i18n';
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { GlassBack, GlassInput } from '../src/components/GlassField';
import { GlassPill } from '../src/components/Glass';
import { color, displayFamily, space, type } from '../src/theme';

export default function AuthEmail() {
  const lang = useLang();
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
    <View style={s.wrap}>
      {/* Фон — ЗА клавиатурным контейнером: внутри него он сжимался бы вместе с формой. */}
      <Ambient glows={GLOW_FORM} />
      <KeyboardAvoidingView
        style={s.fill}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={[s.page, { paddingTop: insets.top + space.sm, paddingBottom: insets.bottom + space.lg }]}>
          <GlassBack
            label={T('Назад', 'Back')}
            onPress={() => (router.canGoBack() ? router.back() : router.replace('/auth'))}
          />

          {/* Гарнитура заголовка зависит от языка — см. displayFamily: в шрифте борда нет кириллицы. */}
          <Text style={[s.h, { fontFamily: displayFamily(lang) }]}>{AUTH.emailTitle()}</Text>
          <Text style={s.note}>{AUTH.emailNote()}</Text>

          <GlassInput
            style={s.field}
            label={AUTH.emailLabel()}
            bad={!!err}
            value={email}
            onChangeText={(v) => { setEmail(v); if (err) setErr(null); }}
            placeholder={AUTH.emailPlaceholder()}
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

          <View style={s.fill} />

          <GlassPill
            tone="brand"
            label={AUTH.continue()}
            disabled={!ok}
            busy={busy}
            onPress={go}
            style={s.cta}
          />
          <Text style={s.terms}>{AUTH_TERMS()}</Text>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  fill: { flex: 1 },
  page: { flex: 1, paddingHorizontal: 24 },
  h: { ...type.display, color: color.fg, marginTop: 28 } as any,
  note: { ...type.displaySub, color: color.muted, marginTop: space.sm } as any,
  field: { marginTop: 32 },
  errBox: { marginTop: space.md },
  errTitle: { ...type.fieldLabel, color: color.danger } as any,
  errNote: { ...type.fine, color: color.danger, marginTop: 2 } as any,
  // Кнопка входа выше стеклянных: у неё в борде своя высота, 56 против 52.
  cta: { height: 56 },
  terms: { ...type.fine, color: color.muted, textAlign: 'center', marginTop: space.md } as any,
});
