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
import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, KeyboardAvoidingView, Platform, TextInput } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { useNavigation, useRouter } from 'expo-router';
import { auth } from '../src/api';
import { AUTH, looksLikeEmail } from '../src/auth';
import { AUTH_TERMS } from '../src/onboarding';
import { useLang, T, replyLang } from '../src/i18n';
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { GlassBack, GlassInput } from '../src/components/GlassField';
import { GlassPill, GlassToast } from '../src/components/Glass';
import { color, displayFamily, space, type } from '../src/theme';
import { hFail } from '../src/haptics';

export default function AuthEmail() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх экрана — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const nav = useNavigation();
  const input = useRef<TextInput>(null);
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<{ title: string; note: string } | null>(null);

  const ok = looksLikeEmail(email);

  /**
   * КЛАВИАТУРА ПОДНИМАЕТСЯ ПОСЛЕ ТОГО, КАК ЭКРАН ДОЕХАЛ, А НЕ ВМЕСТЕ С НИМ.
   *
   * `autoFocus` ставит фокус в момент монтирования — то есть в тот самый момент, когда начинается
   * переход. Дальше на одном кадре сходятся три движения: сам переход (его ведёт система),
   * подъём клавиатуры (его ведёт iOS) и подгонка разметки под клавиатуру, которую
   * `KeyboardAvoidingView` считает в JS-потоке и на каждом кадре пересчитывает высоту. Третье
   * упирается в главный поток, и переход теряет кадры — со стороны он «троит».
   *
   * `transitionEnd` — событие самого стека: оно приходит ровно тогда, когда анимация закончилась.
   * `closing` отсекает обратный переход: уходя с экрана, поднимать клавиатуру незачем.
   *
   * ЗАПАСНОЙ ПУТЬ ОБЯЗАТЕЛЕН. Экран можно открыть и без перехода вовсе — по ссылке снаружи или
   * первым в стопке. Тогда события не будет никогда, и без таймера поле осталось бы без фокуса, а
   * человек — перед клавиатурой, которую надо вызывать руками. Задержка заведомо больше перехода,
   * чтобы в обычном случае сработало событие, а не она.
   */
  useEffect(() => {
    let done = false;
    const focus = () => {
      if (done) return;
      done = true;
      input.current?.focus();
    };
    const off = nav.addListener('transitionEnd' as any, (e: any) => {
      if (!e?.data?.closing) focus();
    });
    const t = setTimeout(focus, 700);
    return () => {
      off();
      clearTimeout(t);
    };
  }, [nav]);


  const go = async () => {
    if (busy) return;
    // Кадр A.03.1b: кнопка выключена, пока адрес не похож на адрес, но по нажатию на выключенную
    // ничего не происходит — поэтому ошибку показываем и здесь, если человек всё-таки дожал.
    if (!ok) { hFail(); setErr({ title: AUTH.badEmailTitle(), note: AUTH.badEmailNote() }); return; }
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
      hFail();
      if (r?.error === 'bad email') setErr({ title: AUTH.badEmailTitle(), note: AUTH.badEmailNote() });
      else if (r?.error === 'too many') setErr({ title: AUTH.tooManyTitle(), note: AUTH.tooManyNote() });
      // Повтор здесь не поможет никогда — и говорить «через минуту» значит гонять по кругу.
      else if (r?.error === 'not allowed') setErr({ title: AUTH.notAllowedTitle(), note: AUTH.notAllowedNote() });
      else setErr({ title: AUTH.sendFailedTitle(), note: AUTH.sendFailedNote() });
    } catch {
      hFail();
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
        <View style={[s.page, { paddingTop: insets.top + space.sm,
                                paddingBottom: dockBottom(insets.bottom + space.lg, kb) }]}>
          <GlassBack
            label={T('Назад', 'Back')}
            onPress={() => (router.canGoBack() ? router.back() : router.replace('/auth'))}
          />

          {/* Гарнитура заголовка зависит от языка — см. displayFamily: в шрифте борда нет кириллицы. */}
          <Text style={[s.h, { fontFamily: displayFamily(lang) }]}>{AUTH.emailTitle()}</Text>
          <Text style={s.note}>{AUTH.emailNote()}</Text>

          <GlassInput
            ref={input}
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
            accessibilityLabel={AUTH.emailLabel()}
          />

          {/* Та же плашка, что на экране кода: ошибка входа выглядит одинаково на обоих шагах. */}
          {err ? <GlassToast title={err.title} note={err.note} style={s.toast} /> : null}

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
  toast: { marginTop: space.md },
  // Кнопка входа выше стеклянных: у неё в борде своя высота, 56 против 52.
  cta: { height: 56 },
  terms: { ...type.fine, color: color.muted, textAlign: 'center', marginTop: space.md } as any,
});
