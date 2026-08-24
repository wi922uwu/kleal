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
 *
 * ЯЧЕЙКИ — ТО ЖЕ СТЕКЛО, что поле на предыдущем экране: `GlassPane` другой формы. Своя пара слоёв
 * здесь означала бы второе стекло в приложении, которое разойдётся с первым при первой правке.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, Pressable, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { auth, setSession } from '../src/api';
import { AUTH, CODE_LEN, DEV_CODE } from '../src/auth';
import { patch, applyDefaults } from '../src/state';
import { useLang, T, replyLang } from '../src/i18n';
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { GlassBack, GlassPane } from '../src/components/GlassField';
import { GlassPill } from '../src/components/Glass';
import { color, displayFamily, radius as rad, space, type } from '../src/theme';

const TTL_MIN = 10;          // столько же, сколько CODE_TTL на сервере
const RESEND = 30;           // «Resend code in 0:30»

export default function AuthCode() {
  const lang = useLang();
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
            onPress={() => (router.canGoBack() ? router.back() : router.replace('/auth-email'))}
          />

          {/* Гарнитура заголовка зависит от языка — см. displayFamily. */}
          <Text style={[s.h, { fontFamily: displayFamily(lang) }]}>{AUTH.codeTitle()}</Text>
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
                  // Кромка ячейки — единственное, что различает состояния: заливка у всех одна.
                  !!ch && s.cellFilled,
                  i === code.length && !busy && s.cellActive,
                  !!err && s.cellBad,
                ]}
              >
                <GlassPane radius={rad.lg} />
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

          <View style={s.fill} />

          <GlassPill
            tone="brand"
            label={dead ? AUTH.sendNew() : AUTH.verify()}
            disabled={!dead && !full}
            busy={busy}
            onPress={() => (dead ? resend() : verify(code))}
            style={s.cta}
          />
          {/* Вторая дверь — стеклянная, а не фирменная: уйти на другой адрес это отступление, а
              не то, ради чего человек сюда пришёл. */}
          <GlassPill
            label={AUTH.otherEmail()}
            onPress={() => router.replace('/auth-email')}
            style={s.second}
          />
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

  cells: { flexDirection: 'row', gap: space.sm, marginTop: 32 },
  cell: {
    flex: 1,
    height: 56,
    borderRadius: rad.lg,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF55',
  },
  cellFilled: { borderColor: color.neutral300 },
  cellActive: { borderWidth: 1, borderColor: color.primary },
  cellBad: { borderWidth: 1, borderColor: color.danger },
  cellText: { ...type.codeDigit, color: color.fg } as any,
  /** Поле лежит поверх ячеек и не видно: прозрачный текст, нулевая непрозрачность курсора. */
  hidden: { ...StyleSheet.absoluteFillObject, opacity: 0, color: 'transparent' } as any,

  /** Отладочная полоса: намеренно чужеродная в этом интерфейсе — её нельзя не заметить. */
  devBox: {
    marginTop: space.md, padding: space.md, borderRadius: rad.lg,
    backgroundColor: color.warnBg, borderWidth: 1, borderColor: color.warnText,
    borderStyle: 'dashed', gap: 4,
  },
  devTitle: { ...type.fine, color: color.warnText,
              textTransform: 'uppercase', letterSpacing: 0.6 } as any,
  devCode: { ...type.codeDigit, color: color.warnText, letterSpacing: 6 } as any,
  devNote: { ...type.fine, color: color.warnText } as any,

  resendRow: { marginTop: space.lg, alignItems: 'center' },
  resend: { ...type.fine, color: color.muted } as any,
  resendOn: { ...type.fieldLabel, color: color.primary } as any,

  errBox: { marginTop: space.lg, alignItems: 'center' },
  errTitle: { ...type.fieldLabel, color: color.danger } as any,
  errNote: { ...type.fine, color: color.danger, marginTop: 2, textAlign: 'center' } as any,

  // Кнопка входа выше стеклянных: у неё в борде своя высота, 56 против 52.
  cta: { height: 56 },
  second: { marginTop: space.md },
});
