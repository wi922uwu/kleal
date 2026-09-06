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
import React from 'react';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { AUTH_COPY, AUTH_EMOJI_ROWS, AUTH_TERMS } from '../src/onboarding';
import { useLang } from '../src/i18n';
import { patch, applyDefaults } from '../src/state';
import { Ambient, GLOW_SIGNIN } from '../src/components/Ambient';
import { GlassPill } from '../src/components/Glass';
import { EmojiTicker } from '../src/components/EmojiTicker';
import { LogoMark } from '../src/components/Logo';
import { color, displayFamily, font, space, type } from '../src/theme';

/** Кнопка провайдера с пометкой «скоро» в углу. Пометка — тот же приём, что у строк настроек. */
function Soon({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={s.soonWrap}>
      {children}
      <Text style={s.soon} pointerEvents="none">{label}</Text>
    </View>
  );
}

export default function Auth() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const c = AUTH_COPY();


  return (
    <View style={s.wrap}>
      <Ambient glows={GLOW_SIGNIN} />
      <ScrollView
        contentContainerStyle={[
          s.scroll,
          { paddingTop: insets.top + 40, paddingBottom: insets.bottom + space.xl },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Гарнитура заголовка зависит от языка — см. displayFamily. */}
        <Text style={[s.h, { fontFamily: displayFamily(lang) }]}>{c.title}</Text>

        <View style={s.hero}>
          {/* Строки эмодзи и капля стоят в одной стопке: капля перекрывает середину строк. */}
          <EmojiTicker rows={AUTH_EMOJI_ROWS} />
          <LogoMark width={186} />
        </View>

        <View style={s.btns}>
          <Soon label={c.soon()}>
            <GlassPill
              tone="dark"
              label={c.apple}
              disabled
              icon={
                <Image
                  accessibilityIgnoresInvertColors
                  source={require('../assets/art/icon-apple.png')}
                  style={s.gIcon}
                  resizeMode="contain"
                />
              }
            />
          </Soon>
          <Soon label={c.soon()}>
            <GlassPill
              label={c.google}
              disabled
              icon={
                <Image
                  accessibilityIgnoresInvertColors
                  source={require('../assets/art/icon-google.png')}
                  style={s.gIcon}
                  resizeMode="contain"
                />
              }
            />
          </Soon>
          {/* Почта отделена промежутком — в борде она в своей области внизу, а не в ряду провайдеров. */}
          <GlassPill label={c.email} onPress={() => router.navigate('/auth-email')} style={s.email} />
          <Text style={s.note}>{c.emailNote}</Text>
        </View>

        <Text style={s.terms}>{AUTH_TERMS()}</Text>
      </ScrollView>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1 },
  scroll: { flexGrow: 1, paddingHorizontal: space.xl },
  h: { ...type.display, color: color.fg, textAlign: 'center' } as any,
  /*
    ВЫСОТА ПОЛЯ ЗАДАНА И ОБРЕЗАНА. Пять рядов эмодзи с шагом 52 занимают 208 точек — больше, чем
    капля (167), и без своей высоты поле распирало содержимым: ряды вылезали вверх и наезжали на
    заголовок. `overflow: hidden` здесь не украшение, а край кадра: в борде ряды тоже уходят за
    границу экрана, а не переносятся.
  */
  hero: {
    height: 210,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 28,
    marginBottom: 36,
    overflow: 'hidden',
  },
  btns: { gap: space.md },
  email: { marginTop: 28 },
  gIcon: { width: 20, height: 20 },
  /** Обёртка кнопки провайдера: пометка стоит поверх правого края, не сдвигая саму кнопку. */
  soonWrap: { position: 'relative', justifyContent: 'center' },
  soon: {
    ...type.caption,
    position: 'absolute',
    right: space.lg,
    color: color.muted,
  } as any,
  /** Объяснение под кнопкой почты: почему единственная рабочая дверь именно она. */
  note: { ...type.caption, color: color.muted, textAlign: 'center', paddingHorizontal: space.md },
  terms: {
    fontFamily: font.text,
    fontSize: 12,
    lineHeight: 16,
    color: color.muted,
    textAlign: 'center',
    marginTop: 'auto',
    paddingTop: space.xl,
  },
});
