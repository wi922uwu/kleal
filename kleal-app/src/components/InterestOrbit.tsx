/**
 * Картинки интересов на орбите вокруг капли — экран входа.
 *
 * 18.10.2026, вторая версия. Первая (картинки на трёх кольцах «радара», каждая качалась и
 * наклонялась сама по себе, внешние уходили за край экрана, у заголовка таяли) Иван назвал
 * «ужасно и очень ИИшно» и попросил «пустить их по круговой оси, как по орбите». Теперь:
 *
 *   ОДНА ОРБИТА, ВИДНАЯ В ПЕРСПЕКТИВЕ — круг, наклонённый от зрителя (эллипс с лёгким креном),
 *   тонкой линией. Предметы стоят на нём через равные промежутки и идут по нему ровно, без
 *   рывков и покачиваний — как планеты.
 *   ГЛУБИНА ЧЕСТНАЯ: спереди предмет крупнее и ярче, сзади меньше и бледнее и уходит ЗА каплю
 *   (слой `back` рисуется под каплей, `front` — над ней).
 *   В ЭКРАН ПОМЕЩАЕТСЯ ЦЕЛИКОМ и не доходит до заголовка — ничего не обрезается и не тает.
 *
 * Один счётчик на UI-потоке (Reanimated). Экран не в фокусе — стоит. «Уменьшить движение» —
 * предметы стоят на своих местах орбиты. Картинки — облегчённые копии колеса (assets/art/orbit).
 */
import { useEffect } from 'react';
import { Image, StyleSheet, View, type ImageSourcePropType } from 'react-native';
import Animated, {
  cancelAnimation, Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withRepeat, withTiming,
  type SharedValue,
} from 'react-native-reanimated';
import Svg, { Ellipse } from 'react-native-svg';
import { useIsFocused } from 'expo-router';

/** Один оборот. Спокойно, но движение видно сразу. */
const TURN_MS = 40000;
/** Крен орбиты (рад): чуть наклонена — не плоская «тарелка». */
const TILT = -0.16;
/** Размер предмета спереди; сзади — `BACK_SCALE` от него. */
const SIZE = 64;
const BACK_SCALE = 0.56;

const ITEMS: ImageSourcePropType[] = [
  require('../../assets/art/orbit/disco.webp'),
  require('../../assets/art/orbit/sneaker.webp'),
  require('../../assets/art/orbit/matcha.webp'),
  require('../../assets/art/orbit/camera.webp'),
  require('../../assets/art/orbit/gamepad.webp'),
  require('../../assets/art/orbit/cherries.webp'),
];

type Geo = { cx: number; cy: number; rx: number; ry: number };

/** Общий счётчик орбиты: живёт на экране, оба слоя читают один и тот же. */
export function useOrbitClock() {
  const reduced = useReducedMotion();
  const focused = useIsFocused();
  const t = useSharedValue(0);
  useEffect(() => {
    if (reduced || !focused) { cancelAnimation(t); return; }
    const from = t.value % 1;
    t.value = from;
    t.value = withRepeat(withTiming(from + 1, { duration: TURN_MS, easing: Easing.linear }), -1, false);
    return () => cancelAnimation(t);
  }, [reduced, focused, t]);
  return t;
}

/**
 * Слой орбиты. `back` — под каплей (там же линия орбиты), `front` — над ней.
 * `rx`/`ry` — полуоси эллипса орбиты.
 */
export function InterestOrbit({ t, layer, cx, cy, rx, ry }: Geo & { t: SharedValue<number>; layer: 'back' | 'front' }) {
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {layer === 'back' ? (
        <Svg style={StyleSheet.absoluteFill}>
          <Ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#FFFFFF" strokeOpacity={0.7} strokeWidth={1}
                   transform={`rotate(${(TILT * 180) / Math.PI} ${cx} ${cy})`} />
        </Svg>
      ) : null}
      {ITEMS.map((src, i) => (
        <Moon key={i} src={src} t={t} layer={layer} cx={cx} cy={cy} rx={rx} ry={ry}
              base={(i / ITEMS.length) * Math.PI * 2} />
      ))}
    </View>
  );
}

function Moon({ src, t, layer, cx, cy, rx, ry, base }: Geo & {
  src: ImageSourcePropType; t: SharedValue<number>; layer: 'back' | 'front'; base: number;
}) {
  const style = useAnimatedStyle(() => {
    const a = base + t.value * Math.PI * 2;
    // Точка на эллипсе, потом крен всей орбиты.
    const ex = Math.cos(a) * rx;
    const ey = Math.sin(a) * ry;
    const x = cx + ex * Math.cos(TILT) - ey * Math.sin(TILT);
    const y = cy + ex * Math.sin(TILT) + ey * Math.cos(TILT);
    // Глубина: sin(a) = 1 — ближе всего (низ эллипса), −1 — дальше всего (за каплей).
    const depth = (Math.sin(a) + 1) / 2;
    const front = Math.sin(a) > 0;
    const k = BACK_SCALE + (1 - BACK_SCALE) * depth;
    return {
      opacity: (layer === 'front') === front ? 0.62 + 0.38 * depth : 0,
      zIndex: Math.round(depth * 100),
      transform: [{ translateX: x - SIZE / 2 }, { translateY: y - SIZE / 2 }, { scale: k }],
    };
  });
  return (
    <Animated.View style={[s.moon, style]}>
      <Image accessibilityIgnoresInvertColors source={src} style={s.img} resizeMode="contain" />
    </Animated.View>
  );
}

// ===== вид
const s = StyleSheet.create({
  moon: { position: 'absolute', left: 0, top: 0, width: SIZE, height: SIZE },
  img: { width: '100%', height: '100%' },
});
