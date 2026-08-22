/**
 * A.03.2 — «Введи код», со всеми четырьмя состояниями борда.
 *
 * ОДНО ПОЛЕ, А НЕ ШЕСТЬ. На кадре нарисованы шесть ячеек, и это вид, а не устройство ввода. Шесть
 * настоящих TextInput означают шесть точек, где может застрять фокус, ручной перенос курсора,
 * отдельная возня с Backspace на пустой ячейке и вставкой кода целиком — и всё это ломается на
 * автозаполнении из СМС и почты. Здесь одно невидимое поле на всю ширину, а ячейки нарисованы
 * поверх него: автозаполнение, вставка и удаление работают сами, потому что это обычный ввод.
 *
 * ЧЕТЫРЕ СОСТОЯНИЯ РАЗЛИЧАЮТСЯ ПО СМЫСЛУ, а не по тексту ошибки:
 *   A.03.2   — ждём ввода, счётчик до повторной отправки;
 *   A.03.2b  — неверный код, показываем ОСТАВШИЕСЯ попытки;
 *   A.03.2c  — код истёк или попытки кончились: главная кнопка меняется на «Отправить новый»;
 *   A.03.2d  — проверяем: кнопка занята, поле закрыто.
 * Истёкший и неверный — разные кадры именно потому, что делать в них надо разное.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, Pressable, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { auth, setSession } from '../src/api';
import { AUTH, CODE_LEN, DEV_CODE } from '../src/auth';
import { patch, applyDefaults } from '../src/state';
import { useLang, T, replyLang } from '../src/i18n';
import { color, radius as rad, space, type } from '../src/theme';

const TTL_MIN = 10;          // столько же, сколько CODE_TTL на сервере
const RESEND = 30;           // «Resend code in 0:30»

export default function AuthCode() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ email?: string; dev?: string }>();
  const email = String(params.email || '');
  /**
   * Код, показанный на экране. Существует, только пока на сервере включён KLEAL_SHOW_CODE —
   * то есть пока письмо на произвольный адрес не уходит и завести второй аккаунт нечем.
   * Обновляется при повторной отправке: там приходит НОВЫЙ код, а старый гаснет.
   */
  const [devCode, setDevCode] = useState(String(params.dev || ''));

  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(RESEND);
  const [err, setErr] = useState<{ title: string; note: string; dead?: boolean } | null>(null);
  const input = useRef<TextInput>(null);

  /** Счётчик до повторной отправки. Один таймер на экран, гаснет вместе с ним. */
  useEffect(() => {
    if (left <= 0) return;
    const id = setInterval(() => setLeft((v) => (v > 0 ? v - 1 : 0)), 1000);
    return () => clearInterval(id);
  }, [left]);

  const full = code.length === CODE_LEN;
  /** A.03.2c: код мёртв — вместо «Подтвердить» просим новый. */
  const dead = !!err?.dead;

  const verify = async (value: string) => {
    if (busy || value.length !== CODE_LEN) return;
    setBusy(true);
    setErr(null);
    try {
      const r: any = await auth.verifyCode(email, value, replyLang());
      if (r?.ok && r?.token) {
        setSession(r.token);
        // Личность и профиль приходят с сервера: у вернувшегося он уже есть, у нового — нет.
        patch({
          login: r.login || email,
          authMethod: 'code',
          session: r.token,
          ...(r.profile ? { profile: r.profile } : {}),
          ...(r.isNew ? {} : { done: true }),
        });
        if (r.isNew) {
          applyDefaults();
          router.replace('/auth-done');            // A.03.3 → анкета
        } else {
          router.dismissTo('/home');               // вернувшийся идёт сразу на главную
        }
        return;
      }
      if (r?.error === 'wrong') {
        setCode('');
        setErr({ title: AUTH.wrongTitle(), note: AUTH.wrongNote(Number(r?.attempts_left ?? 0)) });
        setTimeout(() => input.current?.focus(), 40);
      } else if (r?.error === 'expired') {
        setCode('');
        setErr({ title: AUTH.expiredTitle(), note: AUTH.expiredNote(), dead: true });
      } else {
        setErr({ title: AUTH.sendFailedTitle(), note: AUTH.sendFailedNote() });
      }
    } catch {
      setErr({ title: AUTH.sendFailedTitle(), note: AUTH.offline() });
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    if (busy || (left > 0 && !dead)) return;
    setBusy(true);
    setErr(null);
    setCode('');
    try {
      const r: any = await auth.requestCode(email, replyLang());
      setDevCode(String(r?.dev_code || ''));
      if (r?.error === 'too many') setErr({ title: AUTH.tooManyTitle(), note: AUTH.tooManyNote() });
      else if (r?.error === 'not allowed') setErr({ title: AUTH.notAllowedTitle(), note: AUTH.notAllowedNote() });
      else if (!r?.ok) setErr({ title: AUTH.sendFailedTitle(), note: AUTH.sendFailedNote() });
      setLeft(Number(r?.resend_in) > 0 ? Number(r.resend_in) : RESEND);
      setTimeout(() => input.current?.focus(), 40);
    } catch {
      setErr({ title: AUTH.sendFailedTitle(), note: AUTH.offline() });
    } finally {
      setBusy(false);
    }
  };

  const cells = useMemo(() => Array.from({ length: CODE_LEN }, (_, i) => code[i] || ''), [code]);

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
          onPress={() => (router.canGoBack() ? router.back() : router.replace('/auth-email'))}
        >
          <Text style={s.backGlyph}>‹</Text>
        </Pressable>

        <Text style={s.h}>{AUTH.codeTitle()}</Text>
        <Text style={s.note}>{AUTH.codeNote(email, TTL_MIN)}</Text>

        {/*
          Полоса отладки. Нарочно не в стиле приложения — жёлтая, с пунктиром и словом «отладка»:
          она обязана выглядеть как то, чего в продукте быть не должно. Появляется, только если
          сервер прислал код, а он присылает его лишь при явно включённом рубильнике.
        */}
        {devCode ? (
          <View style={s.devBox}>
            <Text style={s.devTitle}>{DEV_CODE.title()}</Text>
            <Text style={s.devCode} selectable>{devCode}</Text>
            <Text style={s.devNote}>{DEV_CODE.note()}</Text>
          </View>
        ) : null}

        <Pressable
          accessibilityRole="none"
          style={s.cells}
          onPress={() => input.current?.focus()}
        >
          {cells.map((ch, i) => (
            <View
              key={i}
              style={[
                s.cell,
                !!ch && s.cellFilled,
                i === code.length && !busy && s.cellActive,
                !!err && s.cellBad,
              ]}
            >
              <Text style={s.cellText}>{ch}</Text>
            </View>
          ))}
          {/* Настоящее поле — прозрачное и поверх ячеек: автозаполнение из письма приходит в него. */}
          <TextInput
            ref={input}
            style={s.hidden}
            value={code}
            onChangeText={(v) => {
              const digits = v.replace(/\D/g, '').slice(0, CODE_LEN);
              setCode(digits);
              if (err) setErr(null);
              if (digits.length === CODE_LEN) verify(digits);   // шестая цифра — сразу проверяем
            }}
            keyboardType="number-pad"
            inputMode="numeric"
            textContentType="oneTimeCode"
            autoComplete="one-time-code"
            maxLength={CODE_LEN}
            editable={!busy}
            autoFocus
            accessibilityLabel={AUTH.codeTitle()}
          />
        </Pressable>

        {err ? (
          <View style={s.errBox}>
            <Text style={s.errTitle}>{err.title}</Text>
            <Text style={s.errNote}>{err.note}</Text>
          </View>
        ) : (
          <Pressable
            accessibilityRole="button"
            disabled={left > 0 || busy}
            onPress={resend}
            style={s.resendRow}
          >
            <Text style={[s.resend, left <= 0 && !busy && s.resendOn]}>
              {left > 0 ? AUTH.resendIn(left) : AUTH.resend()}
            </Text>
          </Pressable>
        )}

        <View style={{ flex: 1 }} />

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: busy || (!dead && !full), busy }}
          disabled={busy || (!dead && !full)}
          style={[s.cta, (busy || (!dead && !full)) && s.ctaOff]}
          onPress={() => (dead ? resend() : verify(code))}
        >
          {busy
            ? <ActivityIndicator color={color.onPrimary} />
            : <Text style={s.ctaText}>{dead ? AUTH.sendNew() : AUTH.verify()}</Text>}
        </Pressable>

        <Pressable
          accessibilityRole="button"
          style={s.link}
          onPress={() => router.replace('/auth-email')}
        >
          <Text style={s.linkText}>{AUTH.otherEmail()}</Text>
        </Pressable>
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

  cells: { flexDirection: 'row', gap: space.sm, marginTop: space.xl },
  cell: {
    flex: 1, height: 56, borderRadius: rad.lg, backgroundColor: color.card,
    borderWidth: 1, borderColor: color.line, alignItems: 'center', justifyContent: 'center',
  },
  cellFilled: { borderColor: color.neutral400 },
  cellActive: { borderColor: color.primary },
  cellBad: { borderColor: color.danger },
  cellText: { ...type.h2, color: color.fg } as any,
  /** Поле лежит поверх ячеек и не видно: прозрачный текст, нулевая непрозрачность курсора. */
  hidden: { ...StyleSheet.absoluteFillObject, opacity: 0, color: 'transparent' } as any,

  /** Отладочная полоса: намеренно чужеродная в этом интерфейсе — её нельзя не заметить. */
  devBox: {
    marginTop: space.md, padding: space.md, borderRadius: rad.lg,
    backgroundColor: color.warnBg, borderWidth: 1, borderColor: color.warnText,
    borderStyle: 'dashed', gap: 4,
  },
  devTitle: { ...type.caption, color: color.warnText, fontWeight: '700',
              textTransform: 'uppercase', letterSpacing: 0.6 } as any,
  devCode: { ...type.h2, color: color.warnText, fontWeight: '700', letterSpacing: 6 } as any,
  devNote: { ...type.caption, color: color.warnText } as any,

  resendRow: { marginTop: space.md, alignItems: 'center' },
  resend: { ...type.bodySmall, color: color.muted } as any,
  resendOn: { color: color.primary, fontWeight: '700' },

  errBox: { marginTop: space.md, padding: space.md, borderRadius: rad.lg, backgroundColor: color.dangerBg },
  errTitle: { ...type.labelMedium, color: color.danger, fontWeight: '700' } as any,
  errNote: { ...type.bodySmall, color: color.danger, marginTop: 2 } as any,

  cta: { height: 56, borderRadius: rad.full, backgroundColor: color.primary,
         alignItems: 'center', justifyContent: 'center' },
  ctaOff: { opacity: 0.45 },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  link: { height: 48, alignItems: 'center', justifyContent: 'center' },
  linkText: { ...type.labelMedium, color: color.fg } as any,
});
