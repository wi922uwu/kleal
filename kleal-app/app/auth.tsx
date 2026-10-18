/**
 * A.03 · Sign in — вход. Порт кадра борда поверх прежнего «rAuth».
 *
 * Apple и Google здесь НЕ настоящие: OAuth требует собственного идентификатора приложения,
 * которого у Expo Go нет, и это отдельная задача. Почта — единственная дверь, которая работает
 * по-настоящему.
 *
 * РАНЬШЕ ОНИ ВСЁ РАВНО ПУСКАЛИ ДАЛЬШЕ, и это был тихий капкан. `skipTo` помечал `authMethod`,
 * звал `applyDefaults()` и уходил в анкету — а `login` и `session` оставались пустыми. Человек
 * проходил весь онбординг, и профиль оказывался привязан ни к чему: узнавал он об этом только при
 * выходе, где ему сообщали, что «вернуть его будет нечем — он сотрётся вместе со всем, что собрано
 * на этом телефоне». В комментарии при этом было написано, что заглушка «подписана и на экране», —
 * на экране её не было.
 *
 * Теперь на кнопках стоит «скоро», и они не нажимаются. Заглушку видно ДО того, как человек
 * потратил на анкету десять минут, а не после.
 *
 * ЭМОДЗИ ЗА ЛОГОТИПОМ — не декор, а список занятий: пять строк, между ними стоит капля. В борде
 * строки шире экрана и обрезаются краями — это намеренно, поэтому здесь они НЕ переносятся и не
 * ужимаются, а выходят за края.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import Animated, { FadeIn, useReducedMotion } from 'react-native-reanimated';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { AUTH_COPY } from '../src/onboarding';
import { useLang } from '../src/i18n';
import { signedIn, applyDefaults } from '../src/state';
import { setSession } from '../src/api';
import { AUTH } from '../src/auth';
import { providerEnabled, signInWith, Provider } from '../src/oauth';
import { Ambient, GLOW_SIGNIN } from '../src/components/Ambient';
import { GlassPill } from '../src/components/Glass';
import { riseIn } from '../src/components/LiquidGlass';
import { Blob } from '../src/components/Blob';
import { InterestOrbit, useOrbitClock } from '../src/components/InterestOrbit';
import { color, heading, space, type } from '../src/theme';

/** Центр колец и капли от верха безопасной зоны — по кадру A.03 (центр капли на 291 от верха экрана). */
const RING_Y = 236;

/** Кнопка провайдера с пометкой «скоро» в углу. Пометка — тот же приём, что у строк настроек. */
function Soon({ label, children, dark }: { label: string; children: React.ReactNode; dark?: boolean }) {
  return (
    <View style={s.soonWrap}>
      {children}
      <Text style={[s.soon, dark && s.soonDark]} pointerEvents="none">{label}</Text>
    </View>
  );
}

export default function Auth() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const c = AUTH_COPY();
  const { width } = useWindowDimensions();
  const reduced = useReducedMotion();
  const orbitT = useOrbitClock();
  // Заголовок проявляется, кнопки встают одним блоком чуть позже — без лесенки и отскока.
  const up = (n: number) => (reduced ? undefined : FadeIn.delay(80 + n * 80).duration(400));
  // Кнопки — стекло: они появляются подъёмом, без прозрачности (см. riseIn).
  const rise = (_n: number) => (reduced ? undefined : riseIn(180, 6));

  /*
   * ВХОД ЧЕРЕЗ GOOGLE. Кнопка живая только когда сервер говорит, что ключи на месте: без них
   * `/api/auth/google/available` отвечает `enabled:false`, и пилюля остаётся прежней заглушкой
   * «скоро». Так экран не обещает того, чего нет.
   *
   * Дальше всё как у входа по коду: сервер отдаёт тот же ответ (там это одна и та же функция),
   * поэтому и здесь та же развилка — новому человеку анкета, вернувшемуся главная.
   */
  const [on, setOn] = useState<Record<string, boolean>>({ google: false, apple: false });
  const [going, setGoing] = useState<Provider | ''>('');
  const [gErr, setGErr] = useState('');

  useEffect(() => {
    let alive = true;
    (['google', 'apple'] as Provider[]).forEach((p) => {
      providerEnabled(p)
        .then((yes) => { if (alive) setOn((o) => ({ ...o, [p]: yes })); })
        .catch(() => {});
    });
    return () => { alive = false; };
  }, []);

  const enter = useCallback(async (provider: Provider, label: string) => {
    if (going) return;
    setGoing(provider);
    setGErr('');
    try {
      const r: any = await signInWith(provider);
      setSession(String(r.token || ''));
      // `signedIn`, а не `patch`: черновик анкеты сверяется с аккаунтом (см. state.ts).
      signedIn({
        login: r.login || r.email || '',
        authMethod: provider,
        session: String(r.token || ''),
        profile: r.profile || null,
        isNew: !!r.isNew,
        id: String(r.id || ''),
      });
      if (r.isNew) {
        applyDefaults();
        router.replace('/auth-done');
      } else {
        router.replace('/home');
      }
    } catch (e: any) {
      setGErr(AUTH.oauthFailed(String(e?.message || provider), label));
    } finally {
      setGoing('');
    }
  }, [going, router]);

  const appleIcon = (
    <Image
      accessibilityIgnoresInvertColors
      source={require('../assets/art/icon-apple.png')}
      style={s.gIcon}
      resizeMode="contain"
    />
  );
  const gIcon = (
    <Image
      accessibilityIgnoresInvertColors
      source={require('../assets/art/icon-google.png')}
      style={s.gIcon}
      resizeMode="contain"
    />
  );


  return (
    <View style={s.wrap}>
      <Ambient glows={GLOW_SIGNIN} />
      {/*
        КОЛЬЦА ВОКРУГ КАПЛИ — три окружности из макета (190, 328 и 468 точек), белые, тающие к краю.
        Капля стоит в центре «радара», и экран читается как «Kleal ищет».
      */}
      <Svg pointerEvents="none" style={StyleSheet.absoluteFill} width={width} height={insets.top + 520}>
        <Defs>
          <LinearGradient id="ringMid" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0} />
            <Stop offset="0.65" stopColor="#FFFFFF" stopOpacity={0.52} />
            <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
          </LinearGradient>
          <LinearGradient id="ringOut" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#FFFFFF" stopOpacity={1} />
            <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
          </LinearGradient>
        </Defs>
        <Circle cx={width / 2} cy={insets.top + RING_Y} r={95} stroke="#FFFFFF" strokeWidth={1} fill="none" />
        <Circle cx={width / 2} cy={insets.top + RING_Y} r={164} stroke="url(#ringMid)" strokeWidth={1} fill="none" />
        <Circle cx={width / 2} cy={insets.top + RING_Y} r={234} stroke="url(#ringOut)" strokeWidth={1} fill="none" />
      </Svg>
      {/* Картинки интересов на орбите вокруг капли (18.10.2026): задняя половина — под каплей. */}
      <InterestOrbit t={orbitT} layer="back" cx={width / 2} cy={insets.top + RING_Y} rx={Math.min(width / 2 - 44, 158)} ry={50} />
      <ScrollView
        contentContainerStyle={[
          s.scroll,
          { paddingTop: insets.top + RING_Y - 45, paddingBottom: insets.bottom + space.xl },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <Animated.View style={s.blob} entering={reduced ? undefined : FadeIn.duration(450)}>
          <Blob size={85} />
        </Animated.View>
        {/* Гарнитура и кегль заголовка зависят от языка — см. heading(). */}
        <Animated.Text entering={up(0)} style={[s.h, heading(lang, type.hero)]}>{c.title}</Animated.Text>

        <View style={s.btns}>
          <Animated.View entering={rise(1)}>
            {on.apple ? (
              <GlassPill
                onPress={() => enter('apple', 'Apple')}
                tone="dark"
                label={going === 'apple' ? AUTH.oauthGoing('Apple') : c.apple}
                disabled={!!going}
                icon={appleIcon}
              />
            ) : (
              <Soon label={c.soon()} dark>
                <GlassPill tone="dark" label={c.apple} disabled icon={appleIcon} />
              </Soon>
            )}
          </Animated.View>
          <Animated.View entering={rise(2)}>
            {on.google ? (
              <GlassPill
                label={going === 'google' ? AUTH.oauthGoing('Google') : c.google}
                onPress={() => enter('google', 'Google')}
                disabled={!!going}
                icon={gIcon}
              />
            ) : (
              <Soon label={c.soon()}>
                <GlassPill label={c.google} disabled icon={gIcon} />
              </Soon>
            )}
          </Animated.View>
          <Animated.View entering={rise(3)}>
            <GlassPill label={c.email} onPress={() => router.navigate('/auth-email')} />
          </Animated.View>
          {gErr ? <Text style={s.note}>{gErr}</Text> : null}
        </View>
      </ScrollView>
      {/* Передняя половина орбиты — над каплей. Касаний не ловит. */}
      <InterestOrbit t={orbitT} layer="front" cx={width / 2} cy={insets.top + RING_Y} rx={Math.min(width / 2 - 44, 158)} ry={50} />
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1 },
  scroll: { flexGrow: 1, paddingHorizontal: space.xl },
  blob: { alignSelf: 'center' },
  h: { color: color.fg, textAlign: 'center', marginTop: 74 },
  btns: { gap: space.md, marginTop: 'auto', paddingTop: space.xl },
  gIcon: { width: 20, height: 20 },
  /** Обёртка кнопки провайдера: пометка стоит поверх правого края, не сдвигая саму кнопку. */
  soonWrap: { position: 'relative', justifyContent: 'center' },
  soon: {
    ...type.caption,
    position: 'absolute',
    right: space.xl,
    color: color.muted,
  } as any,
  soonDark: { color: 'rgba(255,255,255,0.6)' },
  note: { ...type.caption, color: color.muted, textAlign: 'center', paddingHorizontal: space.md },
});
