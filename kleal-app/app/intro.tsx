/**
 * A.02 · What Kleal is for — три слайда пользы.
 *
 * Кадр борда: фотография во весь экран, белый лист снизу с заголовком и подписью, полосный
 * индикатор и тёмная волна с кнопкой. Волна перешла сюда из прежнего интро без изменений —
 * это узнаваемая часть экрана, и в борде она такая же.
 *
 * ЛИСТ ЛЕЖИТ ПОВЕРХ ФОТО, а не под ним: фото занимает весь кадр, лист наезжает снизу и обрезает
 * его. Поэтому фото — абсолютная подложка, а не первый элемент потока.
 *
 * ИНДИКАТОР — ПОЛОСКИ, а не точки: 28×2, активная фирменным красным. Точки были в прежней
 * версии и заметно меняли характер экрана.
 */
import React, { useMemo, useRef } from 'react';
import {
  Animated,
  Image,
  PanResponder,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Svg, { Path } from 'react-native-svg';
import { SLIDES } from '../src/onboarding';
import { useLang, T } from '../src/i18n';
import { useOnb, patch } from '../src/state';
import { color, displayFamily, font, radius, space, type } from '../src/theme';

export default function Intro() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const { width, height } = useWindowDimensions();

  const slides = SLIDES();
  const i = Math.min(st.slide, slides.length - 1);
  const sl = slides[i];
  const last = i === slides.length - 1;

  const next = () => (last ? router.navigate('/auth') : patch({ slide: i + 1 }));

  /**
   * ПАНЕЛЬ ТЯНЕТСЯ ПАЛЬЦЕМ И УЛЕТАЕТ НА ВЕСЬ ЭКРАН.
   *
   * Чёрное поле — не часть листа, а отдельный слой поверх всего экрана: лист его обрезал бы
   * (`overflow: hidden`), и дальше своей границы оно уехать не могло. Теперь оно выше листа в
   * разметке и ограничено только экраном.
   *
   * ДВИЖЕНИЕ — `translateY`, а не высота. Высоту нативный драйвер анимировать не умеет, всё шло
   * через JS-поток и дёргалось на быстром жесте; сдвиг же считается на стороне UI и держит
   * шестьдесят кадров даже во время навигации.
   *
   * ГЕОМЕТРИЯ. Слой высотой во весь экран плюс кривая сверху. В покое он сдвинут вниз так, что
   * видна только волна; полностью поднятый уводит кривую за верхний край, и остаётся ровная
   * чёрная заливка — иначе на «закрытом» экране торчал бы гребень с白 плечами по бокам.
   *
   * РЕЗИНА ВНИЗ. Тянуть панель ниже покоя незачем, но обрывать палец жёстко — не по-эппловски:
   * движение вниз идёт с сопротивлением и само возвращается. Это то же поведение, что у списков
   * iOS на границе прокрутки.
   */
  /** Сколько чёрного видно в покое. */
  const restH = Math.max(CURVE_H, height * WAVE_SHARE);
  const REST_Y = height - restH;          // в покое видна только волна
  const OPEN_Y = -CURVE_H;                // поднят полностью: кривая ушла за верхний край
  const y = useRef(new Animated.Value(REST_Y)).current;
  const busy = useRef(false);
  /** Подпись гаснет на первой трети подъёма — дальше занавес идёт чистым. */
  const labelFade = y.interpolate({
    inputRange: [REST_Y - 120, REST_Y],
    outputRange: [0, 1],
    extrapolate: 'clamp',
  });

  const settle = (toValue: number, velocity: number, after?: () => void) =>
    Animated.spring(y, {
      toValue,
      velocity,
      useNativeDriver: true,
      // Пружина без раскачки на подъёме и с лёгким отскоком на возврате — см. вызовы ниже.
      damping: 26,
      stiffness: 220,
      mass: 0.9,
    }).start(({ finished }) => finished && after?.());

  const pan = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => !busy.current,
        onMoveShouldSetPanResponder: (_e, g) =>
          !busy.current && Math.abs(g.dy) > 4 && Math.abs(g.dy) > Math.abs(g.dx),
        onPanResponderMove: (_e, g) => {
          const raw = REST_Y + g.dy;
          // Вверх — свободно до края, вниз — с сопротивлением: палец уходит втрое дальше пикселя.
          y.setValue(raw < REST_Y ? Math.max(raw, OPEN_Y) : REST_Y + g.dy / 3);
        },
        onPanResponderRelease: (_e, g) => {
          const tapped = Math.abs(g.dy) < 6 && Math.abs(g.dx) < 6;
          const flung = g.vy < -0.55;
          const far = g.dy < -PULL_DONE;
          if (tapped || flung || far) {
            busy.current = true;
            // Сначала занавес закрывает экран, потом под ним меняется слайд, потом занавес
            // уходит вниз с лёгким отскоком — переход читается как одно движение, а не как
            // подмена кадра.
            settle(OPEN_Y, g.vy, () => {
              next();
              if (last) return;           // экран уходит целиком — открывать нечего
              Animated.spring(y, {
                toValue: REST_Y,
                useNativeDriver: true,
                damping: 18,              // мягче: тут и живёт тот самый отскок
                stiffness: 170,
                mass: 1,
              }).start(() => {
                busy.current = false;
              });
            });
            return;
          }
          settle(REST_Y, g.vy);
        },
        onPanResponderTerminate: () => settle(REST_Y, 0),
      }),
    [y, REST_Y, OPEN_Y, i, last]
  );

  return (
    <View style={s.wrap}>
      <Image
        accessibilityIgnoresInvertColors
        source={require('../assets/art/usp-friends-v2.jpg')}
        style={s.photo}
        resizeMode="cover"
      />

      <View style={[s.sheet, { paddingBottom: restH }]}>
        {/* Гарнитура заголовка зависит от языка — см. displayFamily: в шрифте борда нет кириллицы. */}
        <Text style={[s.h, { fontFamily: displayFamily(lang) }]}>{sl.title}</Text>
        <Text style={s.sub}>{sl.sub}</Text>

        <View style={s.bars}>
          {slides.map((_, n) => (
            <View key={n} style={[s.bar, n === i && s.barOn]} />
          ))}
        </View>

      </View>

      {/*
        ЗАНАВЕС ПОВЕРХ ВСЕГО — брат листа, а не его ребёнок: внутри листа он упирался в его край.
        Высота — экран плюс кривая, чтобы в поднятом виде гребень ушёл за верхнюю границу.
      */}
      <Animated.View
        {...pan.panHandlers}
        accessibilityRole="button"
        accessibilityLabel={T('Начать', "Let's Start")}
        style={[s.wave, { height: height + CURVE_H, transform: [{ translateY: y }] }]}
      >
        {/*
          Кривая держит СВОИ пропорции (390×160) и стоит вверху слоя, всё под ней — сплошная
          заливка. Растягивать сам путь нельзя: гребень превращался в шпиль.
        */}
        <Svg width={width} height={CURVE_H} viewBox="0 0 390 160" preserveAspectRatio="none">
          <Path
            d="M0 132 C 78 132 120 20 195 20 C 270 20 312 132 390 132 L390 160 L0 160 Z"
            fill={color.ink}
          />
        </Svg>
        <View style={s.waveFill} />
      </Animated.View>

      {/*
        ПОДПИСЬ — ОТДЕЛЬНО ОТ ЗАНАВЕСА и прибита к низу ЭКРАНА.
        Ребёнком слоя она ехала бы вместе с ним и на поднятом занавесе оказывалась бы у верхней
        кромки — надпись «Начать» посреди закрывающегося экрана. Поэтому она стоит на месте и
        гаснет по мере подъёма: к середине пути её уже нет, и занавес закрывает экран чистым.
        `pointerEvents=none` — чтобы касание доставалось занавесу, а не ей.
      */}
      <Animated.View
        pointerEvents="none"
        style={[s.cta, { bottom: Math.max(insets.bottom, space.lg), opacity: labelFade }]}
      >
        <Text style={s.btnText}>{T('Начать', "Let's Start")}</Text>
      </Animated.View>
    </View>
  );
}

// ===== вид
/** Высота самой кривой — её пропорции из борда, они не меняются. */
const CURVE_H = 160;
/** Какую долю экрана занимает чёрное поле в покое. Тянется оно жестом, поэтому крупным быть не должно. */
const WAVE_SHARE = 0.24;
/** С какого замаха отпускание считается «увести дальше», а не «вернуть на место». */
const PULL_DONE = 70;

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ink, justifyContent: 'flex-end' },
  /*
    Растяжка задана ЯВНО, а не через StyleSheet.absoluteFill: с ним картинка рисовалась в своём
    натуральном размере, прижатая к левому верхнему углу, и `resizeMode` не применялся вовсе —
    на экране был увеличенный левый верхний угол фотографии вместо кадра целиком.
  */
  photo: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, width: undefined, height: undefined },
  sheet: {
    backgroundColor: color.card,
    borderTopLeftRadius: radius.xxl,
    borderTopRightRadius: radius.xxl,
    paddingTop: 40,
    alignItems: 'center',
    overflow: 'hidden',
  },
  h: { ...type.display, color: color.fg, textAlign: 'center' } as any,
  sub: {
    ...type.displaySub,
    color: color.muted,
    textAlign: 'center',
    marginTop: space.lg,
    paddingHorizontal: space.xl,
  } as any,
  bars: { flexDirection: 'row', gap: 6, marginTop: 32 },
  bar: { width: 28, height: 2, borderRadius: radius.full, backgroundColor: color.neutral300 },
  barOn: { backgroundColor: color.primary },
  wave: { position: 'absolute', left: 0, right: 0, top: 0 },
  /** Чёрное под кривой: на высоком экране оно и растёт, поднимая гребень выше. */
  waveFill: { flex: 1, backgroundColor: color.ink },
  cta: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  btnText: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.onPrimary },
});
