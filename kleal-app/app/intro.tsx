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
import React, { useCallback, useMemo, useRef } from 'react';
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
import { useFocusEffect, useRouter } from 'expo-router';
import Svg, { Path } from 'react-native-svg';
import { SLIDES, INTRO_CTA } from '../src/onboarding';
import { useLang, T } from '../src/i18n';
import { useOnb, patch } from '../src/state';
import { color, displayFamily, font, radius, space, type } from '../src/theme';
import { makePull } from '../src/haptics';

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
  /** Сдвиг листа при листании вбок. Ноль — кадр на месте. */
  const slideX = useRef(new Animated.Value(0)).current;
  /**
   * Сменить кадр: текущий доводится до края, кадр подменяется, новый приходит с другой стороны.
   * Без этого подмена читалась бы как мигание, а не как листание.
   */
  const step = (to: number, out: number) => {
    busy.current = true;
    Animated.timing(slideX, { toValue: out, duration: 150, useNativeDriver: true }).start(() => {
      patch({ slide: to });
      slideX.setValue(-out);
      Animated.spring(slideX, { toValue: 0, useNativeDriver: true,
                                damping: 22, stiffness: 200, mass: 0.9 })
        .start(() => { busy.current = false; });
    });
  };
  const busy = useRef(false);
  /**
   * ДЛИННЫЙ ТАКТИЛЬНЫЙ ОТКЛИК НА ПРОТЯЖКЕ. Панель тянут пальцем, и без отклика это единственный
   * жест в приложении, где рука не получает ничего: кнопка щёлкает, поле щёлкает, а тут тянешь
   * вслепую. Дробь засечек по ходу, средний удар на точке невозврата и тяжёлый на пуске — устройство
   * дроби и почему она не одно длинное событие описано в src/haptics.ts.
   */
  const pull = useRef(makePull()).current;
  /** Подпись гаснет на первой трети подъёма — дальше занавес идёт чистым. */
  const labelFade = y.interpolate({
    inputRange: [REST_Y - 120, REST_Y],
    outputRange: [0, 1],
    extrapolate: 'clamp',
  });

  /**
   * ВОЗВРАТ НА ЭТОТ ЭКРАН ПОДНИМАЕТ ЗАНАВЕС ОБРАТНО.
   *
   * На последнем слайде занавес уезжает вверх и НЕ возвращается: экран уходит целиком, опускать
   * нечего. Но уходит он не насовсем — переход на вход это `navigate`, интро остаётся в стопке, и
   * протяжка от левого края возвращает сюда. А возвращает она экран в том виде, в каком он остался:
   * занавес поднят во весь рост, `busy` взведён — то есть сплошная чёрная заливка, которая не
   * отвечает ни на нажатие, ни на жест, потому что `busy` глушит сам обработчик. Тупик без выхода,
   * из которого можно только убить приложение.
   *
   * Поэтому состояние сбрасывается не после ухода, а при КАЖДОМ появлении: каким бы путём сюда ни
   * вернулись, экран открывается в покое. Первый вызов на монтировании ничего не меняет — там уже
   * стоят ровно эти значения.
   */
  useFocusEffect(
    useCallback(() => {
      y.setValue(REST_Y);
      busy.current = false;
    }, [y, REST_Y])
  );

  /**
   * ГОРИЗОНТАЛЬНОЕ ЛИСТАНИЕ ПЕРВЫХ ДВУХ КАДРОВ.
   *
   * Чёрный занавес — это ПУСК, а не «дальше». Пока он стоял на всех трёх кадрах, он и означал на
   * них разное: дважды листал, на третий раз запускал. Теперь его на первых двух нет вовсе, а
   * кадры листаются пальцем вбок — тем жестом, который для карусели и ожидают.
   *
   * Порог в сорок точек и требование, чтобы горизонталь была больше вертикали: иначе лист
   * перелистывался бы от случайного косого движения при попытке потянуть занавес.
   */
  const swipe = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_e, g) =>
          !busy.current && Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy) * 1.4,
        onPanResponderMove: (_e, g) => {
          // Кадр едет за пальцем, но с сопротивлением на краях: за первым и последним двигаться
          // некуда, и упругость честнее, чем мёртвая остановка.
          const edge = (g.dx > 0 && i === 0) || (g.dx < 0 && last);
          slideX.setValue(edge ? g.dx / 4 : g.dx);
        },
        onPanResponderRelease: (_e, g) => {
          const go = Math.abs(g.dx) > 40 || Math.abs(g.vx) > 0.5;
          const fwd = g.dx < 0;
          if (go && fwd && !last) return step(i + 1, -width);
          if (go && !fwd && i > 0) return step(i - 1, width);
          Animated.spring(slideX, { toValue: 0, useNativeDriver: true,
                                    damping: 22, stiffness: 200, mass: 0.9 }).start();
        },
        onPanResponderTerminate: () => {
          Animated.spring(slideX, { toValue: 0, useNativeDriver: true,
                                    damping: 22, stiffness: 200, mass: 0.9 }).start();
        },
      }),
    [i, last, width, slideX]
  );

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
        onPanResponderGrant: () => pull.grab(),
        onPanResponderMove: (_e, g) => {
          const raw = REST_Y + g.dy;
          // Вверх — свободно до края, вниз — с сопротивлением: палец уходит втрое дальше пикселя.
          y.setValue(raw < REST_Y ? Math.max(raw, OPEN_Y) : REST_Y + g.dy / 3);
          // Засечки считаются от ПРОТЯНУТОГО, а не от смещения панели: ниже покоя панель идёт
          // втрое медленнее пальца, и по её ходу дробь там оказалась бы втрое реже.
          pull.move(Math.max(0, -g.dy), -g.dy >= PULL_DONE);
        },
        onPanResponderRelease: (_e, g) => {
          const tapped = Math.abs(g.dy) < 6 && Math.abs(g.dx) < 6;
          const flung = g.vy < -0.55;
          const far = g.dy < -PULL_DONE;
          pull.release(tapped || flung || far);
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
        onPanResponderTerminate: () => {
          pull.release(false);
          settle(REST_Y, 0);
        },
      }),
    [y, REST_Y, OPEN_Y, i, last, pull]
  );

  return (
    <View style={s.wrap} {...swipe.panHandlers}>
      <Image
        accessibilityIgnoresInvertColors
        source={require('../assets/art/usp-friends-v2.jpg')}
        style={s.photo}
        resizeMode="cover"
      />

      {/*
        ОТСТУП СНИЗУ ЗАВИСИТ ОТ КАДРА: на первых двух занавеса нет, и держать под него место
        значило бы оставить внизу пустую белую полосу в четверть экрана.
      */}
      <Animated.View
        style={[s.sheet, { paddingBottom: last ? restH : space.xl + insets.bottom },
                { transform: [{ translateX: slideX }] }]}
      >
        {/* Гарнитура заголовка зависит от языка — см. displayFamily: в шрифте борда нет кириллицы. */}
        <Text style={[s.h, { fontFamily: displayFamily(lang) }]}>{sl.title}</Text>
        <Text style={s.sub}>{sl.sub}</Text>

        <View style={s.bars}>
          {slides.map((_, n) => (
            <View key={n} style={[s.bar, n === i && s.barOn]} />
          ))}
        </View>

      </Animated.View>

      {/*
        ЗАНАВЕС ПОВЕРХ ВСЕГО — брат листа, а не его ребёнок: внутри листа он упирался в его край.
        Высота — экран плюс кривая, чтобы в поднятом виде гребень ушёл за верхнюю границу.
      */}
      {last ? (
      <Animated.View
        {...pan.panHandlers}
        accessibilityRole="button"
        accessibilityLabel={INTRO_CTA.start()}
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
      ) : null}

      {/*
        ПОДПИСЬ — ОТДЕЛЬНО ОТ ЗАНАВЕСА и прибита к низу ЭКРАНА.
        Ребёнком слоя она ехала бы вместе с ним и на поднятом занавесе оказывалась бы у верхней
        кромки — надпись «Начать» посреди закрывающегося экрана. Поэтому она стоит на месте и
        гаснет по мере подъёма: к середине пути её уже нет, и занавес закрывает экран чистым.
        `pointerEvents=none` — чтобы касание доставалось занавесу, а не ей.
      */}
      {last ? (
      <Animated.View
        pointerEvents="none"
        style={[s.cta, { bottom: Math.max(insets.bottom, space.lg), opacity: labelFade }]}
      >
        <Text style={s.btnText}>{INTRO_CTA.start()}</Text>
      </Animated.View>
      ) : null}
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
