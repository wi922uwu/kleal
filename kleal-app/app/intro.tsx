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
import React from 'react';
import { Image, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
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

  return (
    <View style={s.wrap}>
      <Image
        accessibilityIgnoresInvertColors
        source={require('../assets/art/usp-friends-v2.jpg')}
        style={s.photo}
        resizeMode="cover"
      />

      {/*
        Листу задаётся МИНИМАЛЬНАЯ доля экрана, а волне — весь остаток (flexGrow ниже). Без этого
        лист обнимал содержимое, волна оставалась полосой в 160 точек, и на высоких экранах между
        индикатором и чёрным полем зияла белая пустота. Теперь чёрное тянется вверх ровно настолько,
        насколько экран выше содержимого.
      */}
      <View style={[s.sheet, { minHeight: height * SHEET_SHARE }]}>
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
        <Pressable onPress={next} accessibilityRole="button" style={s.wave}>
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
        </Pressable>
      </View>
    </View>
  );
}

// ===== вид
/** Высота самой кривой — её пропорции из борда, они не меняются. */
const CURVE_H = 160;
/** Какую долю экрана лист занимает как минимум. В борде это 307 из 844. */
const SHEET_SHARE = 0.44;

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
  wave: { flexGrow: 1, minHeight: CURVE_H, alignSelf: 'stretch', marginTop: space.lg },
  /** Чёрное под кривой: на высоком экране оно и растёт, поднимая гребень выше. */
  waveFill: { flex: 1, backgroundColor: color.ink },
  btnWrap: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  btnText: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.onPrimary },
});
