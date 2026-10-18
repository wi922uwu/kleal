/**
 * Финал онбординга — кадр A.15.
 *
 * Только поздравление: главный экран теперь свой (app/home.tsx), и сюда попадают ровно один раз —
 * сразу после того, как профиль записан. Нижняя панель показана потому же, почему и на борде:
 * человек должен увидеть, куда попал, ещё до первого действия.
 */
import { View, StyleSheet, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Animated, { FadeIn, useReducedMotion } from 'react-native-reanimated';
import { BottomNav } from '../src/components/BottomNav';
import { Ambient, GLOW_SIGNIN } from '../src/components/Ambient';
import { GlassPill } from '../src/components/Glass';
import { riseIn } from '../src/components/LiquidGlass';
import { KlealMark, RibbonTile } from '../src/components/Ribbon';
import { useLang } from '../src/i18n';
import { DONE_SCREEN } from '../src/onboarding';
import { color, heading, space, type } from '../src/theme';

export default function Done() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const reduced = useReducedMotion();

  return (
    <View style={s.wrap}>
      {/*
        КАДР A.15: розово-сиреневое поле (тот же размытый цветной фон, что на входе A.03), коралловая
        лента со стеклянной плиткой и белым знаком Kleal — «нить» из A.03.3 довела до конца анкеты.
      */}
      <Ambient glows={GLOW_SIGNIN} />
      <View style={[s.page, { paddingTop: insets.top + 40 }]}>
        <View style={s.art}>
          <RibbonTile width={width} x={-65} tileTop={152}>
            <KlealMark size={70} />
          </RibbonTile>
        </View>
        <View style={s.body}>
          <Animated.Text
            entering={reduced ? undefined : FadeIn.delay(600).duration(420)}
            style={[s.title, heading(lang, type.hero)]}
          >
            {DONE_SCREEN.title()}
          </Animated.Text>
        </View>

        {/* Кнопка обещает создание интента — и открывает именно его. Главная подкладывается ВНИЗ,
            чтобы «назад» из создания вело на неё, а не обратно в поздравление. */}
        <Animated.View style={s.ctaWrap} entering={reduced ? undefined : riseIn(700, 6)}>
          <GlassPill
            tone="brand"
            label={DONE_SCREEN.cta()}
            onPress={() => { router.dismissTo('/home'); router.navigate('/create'); }}
          />
        </Animated.View>

        <BottomNav />
      </View>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  page: { flex: 1 },
  art: { alignItems: 'flex-start' },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 20 },
  title: { color: color.fg, textAlign: 'center' } as any,
  ctaWrap: { paddingHorizontal: 20, marginBottom: space.lg },
});
