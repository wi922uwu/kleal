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
   * ПАНЕЛЬ ТЯНЕТСЯ ПАЛЬЦЕМ. Едет за рукой вверх и на достаточном замахе делает то же, что тап по
   * «Начать»; не дотянул — возвращается пружиной на место.
   *
   * PanResponder, а не жесты из отдельной библиотеки: в проекте так же сделаны диски возраста и
   * свайп-ответ, и ставить ради одного экрана gesture-handler значило бы завести второй способ
   * читать те же касания.
   *
   * ТАП ЖИВЁТ ЗДЕСЬ ЖЕ. Обычный Pressable под панорамой не получил бы касание вовсе, поэтому
   * короткое движение без замаха считается нажатием — иначе кнопка перестала бы работать у тех,
   * кто просто жмёт.
   */
  const restH = Math.max(CURVE_H, height * WAVE_SHARE);
  const waveH = useRef(new Animated.Value(restH)).current;
  const pan = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        // Перехватываем только ВЕРТИКАЛЬ и только вверх: горизонтальные смахивания и случайные
        // дрожания пальца панель двигать не должны.
        onMoveShouldSetPanResponder: (_e, g) => g.dy < -4 && Math.abs(g.dy) > Math.abs(g.dx),
        onPanResponderMove: (_e, g) => {
          if (g.dy < 0) waveH.setValue(restH + Math.min(-g.dy, PULL_MAX));
        },
        onPanResponderRelease: (_e, g) => {
          const pulled = g.dy < -PULL_DONE || g.vy < -0.6;
          const tapped = Math.abs(g.dy) < 6 && Math.abs(g.dx) < 6;
          if (pulled || tapped) {
            // Возврат к покою ДО перехода: следующий слайд рисуется на месте, а не приезжает
            // растянутым — иначе первый кадр нового слайда виден задранным вверх.
            waveH.setValue(restH);
            next();
            return;
          }
          Animated.spring(waveH, { toValue: restH, useNativeDriver: false, bounciness: 6 }).start();
        },
        onPanResponderTerminate: () => {
          Animated.spring(waveH, { toValue: restH, useNativeDriver: false }).start();
        },
      }),
    [waveH, restH, i, last]
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

        {/*
          Волна и кнопка — одна нажимаемая область: в борде подпись стоит на гребне волны, и
          попадать надо по волне, а не по невидимому прямоугольнику вокруг текста.
        */}
        {/*
          ВЫСОТА ЧЁРНОГО ПОЛЯ ЗАДАНА ДОЛЕЙ ЭКРАНА, а не остатком места.
          Через `flexGrow` не вышло: лист обнимает содержимое, и свободного места, в которое можно
          расти, там ровно ноль — волна оставалась полосой в 160 точек, а между индикатором и
          чёрным зиял белый провал. Доля же поднимает гребень на любом экране предсказуемо.
        */}
        {/*
          ЧЁРНОЕ ПРИБИТО К НИЗУ ЛИСТА И РАСТЁТ ВВЕРХ, наползая на белое. Двигать сам лист нельзя:
          он уезжал от нижнего края, и под ним показывалась фотография — панель отрывалась от дна
          экрана. Поэтому анимируется ВЫСОТА чёрного блока, а лист стоит на месте; его нижний
          отступ равен высоте покоя, чтобы текст не оказался под волной.
        */}
        <Animated.View
          {...pan.panHandlers}
          accessibilityRole="button"
          accessibilityLabel={T('Начать', "Let's Start")}
          style={[s.wave, { height: waveH }]}
        >
          {/*
            Кривая держит СВОИ пропорции (390×160) и стоит вверху блока, а всё под ней — сплошная
            заливка. Растягивать сам путь нельзя: при `height="100%"` на высоком экране гребень
            превращался в шпиль. Растёт чёрное поле, а не форма волны.
          */}
          <Svg width={width} height={CURVE_H} viewBox="0 0 390 160" preserveAspectRatio="none">
            <Path
              d="M0 132 C 78 132 120 20 195 20 C 270 20 312 132 390 132 L390 160 L0 160 Z"
              fill={color.ink}
            />
          </Svg>
          <View style={s.waveFill} />
          <View style={[s.btnWrap, { bottom: Math.max(insets.bottom, space.lg) }]}>
            <Text style={s.btnText}>{T('Начать', "Let's Start")}</Text>
          </View>
        </Animated.View>
      </View>
    </View>
  );
}

// ===== вид
/** Высота самой кривой — её пропорции из борда, они не меняются. */
const CURVE_H = 160;
/** Какую долю экрана занимает чёрное поле в покое. Тянется оно жестом, поэтому крупным быть не должно. */
const WAVE_SHARE = 0.24;
/** Насколько далеко панель уезжает за пальцем. */
const PULL_MAX = 220;
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
  wave: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  /** Чёрное под кривой: на высоком экране оно и растёт, поднимая гребень выше. */
  waveFill: { flex: 1, backgroundColor: color.ink },
  btnWrap: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  btnText: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.onPrimary },
});
