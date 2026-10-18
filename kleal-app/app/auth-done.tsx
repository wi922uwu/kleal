/**
 * A.03.3 — «Ты в деле».
 *
 * Показывается ТОЛЬКО новому. Борд разводит два исхода стрелками: новый аккаунт → A.03.3 → анкета
 * A.04; существующий → сразу на главную, и A.03.3 пропускается. Поэтому решение принимает экран
 * кода (по `isNew` с сервера), а не этот: сюда просто не приходят те, кому он не нужен.
 *
 * ЭТО ЕДИНСТВЕННЫЙ КАДР ПОТОКА БЕЗ ФОРМЫ — и в борде он единственный цветной: тёплое пятно во
 * весь центр и иллюстрация поверх него. Два предыдущих экрана намеренно бледные, потому что там
 * набирают текст; здесь набирать нечего, и цвет наконец можно вернуть.
 */
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Animated, { FadeIn, useReducedMotion } from 'react-native-reanimated';
import { AUTH } from '../src/auth';
import { useLang } from '../src/i18n';
import { Ambient, GLOW_DONE } from '../src/components/Ambient';
import { GlassPill } from '../src/components/Glass';
import { Blob } from '../src/components/Blob';
import { RibbonTile } from '../src/components/Ribbon';
import { riseIn } from '../src/components/LiquidGlass';
import { color, heading, space, type } from '../src/theme';

export default function AuthDone() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const reduced = useReducedMotion();
  // Главное движение экрана — лента; текст спокойно проявляется, когда она уже почти легла.
  const up = (n: number) => (reduced ? undefined : FadeIn.delay(600 + n * 80).duration(420));

  return (
    <View style={s.wrap}>
      <Ambient glows={GLOW_DONE} />
      <View style={[s.page, { paddingTop: insets.top + 45, paddingBottom: insets.bottom + space.lg }]}>
        {/*
          КАДР A.03.3: коралловая лента со стеклянной плиткой, из которой снизу выглядывает капля —
          «ты внутри». Лента во всю ширину экрана и шире, поэтому живёт вне боковых отступов.
        */}
        <View style={s.art}>
          <RibbonTile width={width} x={-72} tileTop={182}>
            <View style={s.peek}>
              <Blob size={61} float={false} />
            </View>
          </RibbonTile>
        </View>
        <View style={s.mid}>
          {/* Гарнитура и кегль заголовка зависят от языка — см. heading(). */}
          <Animated.Text entering={up(0)} style={[s.h, heading(lang, type.hero)]}>{AUTH.doneTitle()}</Animated.Text>
          <Animated.Text entering={up(1)} style={s.note}>{AUTH.doneNote()}</Animated.Text>
        </View>

        {/*
          `replace`, а не переход: назад отсюда возвращаться некуда и незачем — код уже погашен,
          сессия выдана, а экран ввода кода за спиной означал бы кнопку в никуда.
        */}
        <Animated.View entering={reduced ? undefined : riseIn(700, 6)}>
          <GlassPill
            tone="brand"
            label={AUTH.setUp()}
            onPress={() => router.replace('/chat')}
          />
        </Animated.View>
      </View>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  page: { flex: 1, paddingHorizontal: 24 },
  art: { marginHorizontal: -24 },
  /** Капля в плитке: видна верхняя часть, низ срезан краем плитки — она «выглядывает». */
  peek: { position: 'absolute', left: 17, top: 49, width: 61, height: 47, overflow: 'hidden' },
  mid: { flex: 1, alignItems: 'center', paddingTop: space.xl },
  h: { color: color.fg, textAlign: 'center' } as any,
  note: {
    fontFamily: 'Geist-400',
    fontSize: 17,
    lineHeight: 26,
    color: color.muted,
    textAlign: 'center',
    marginTop: space.xl,
    paddingHorizontal: space.md,
  } as any,
});
