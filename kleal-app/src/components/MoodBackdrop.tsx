/**
 * ФОН ГЛАВНОЙ, КОТОРЫЙ ИДЁТ ЗА КАРУСЕЛЬЮ (решение владельца 17.10.2026: «фон меняется с карточкой»).
 *
 * Фото цветка под главной «не наш стиль»: Kleal — про то, чем заняться с людьми, а не про цветы.
 * Поэтому у каждой карточки карусели свой СВЕТ — цвет её занятия за стеклом: вечер танцев
 * розово-фиолетовый, пробежка мятная, падел солнечный, приставка синяя, рынок красно-зелёный,
 * кофейня карамельная. Без частиц и рисунков (владелец 17.10: частицы — мимо).
 *
 * ФАКТУРА — ШЁЛК, ОДИН НА ВСЕ СЦЕНЫ. Чистый градиент «слишком простой» (владелец 17.10), нужна
 * фактура уровня прежнего фото, но спокойнее. Складки ткани рассчитаны кодом один раз (scratchpad
 * стенда `silk.py`, параметры в `silk.cmd`: рельеф складок, закрученный «лепестком», → свет по
 * нормалям; из четырёх видов владелец выбрал «лепестки», 17.10) и лежат ДВУМЯ слоями поверх цвета: тень
 * (assets/art/home/silk-shade.png) и свет с бликами (silk-light.png). Режимов наложения в RN нет,
 * поэтому фактура бесцветна — белое и тёплая тень с прозрачностью, — и цвет под ней даёт сцена:
 * одна и та же ткань становится розовой, мятной, солнечной.
 *
 * Сцены лежат стопкой, и прозрачность каждой считается ПРЯМО ИЗ СДВИГА ЛЕНТЫ — того же значения,
 * что двигает карточки (MoodCarousel `onTrack`). Палец тянет карточку — фон перетекает вместе с ней,
 * без отдельной анимации «после». Лента повторена трижды (COPIES в карусели), поэтому опорные
 * точки идут по всем копиям: карточка j показывает сцену j % n.
 *
 * Верх и низ каждой сцены светлые — на них тёмное «Привет» и строка ввода; цвет и движение
 * собраны за каруселью, где их и видно сквозь стекло.
 *
 * Двигается только прозрачность готовых SVG-слоёв, и только вслед за пальцем.
 */
import { useEffect, useMemo, useState } from 'react';
import { Animated as RNAnimated, Image, StyleSheet, View } from 'react-native';
import Svg, { Defs, RadialGradient, LinearGradient, Stop, Rect, Ellipse } from 'react-native-svg';
import { useFullScreenSize } from '../fullscreen';

/** Центр сцены — середина карточки карусели (доля высоты экрана, кадр GR.01). */
const CY = 0.31;
const COPIES = 3;

type Look = { top: string; bottom: string; a: string; aa: number; b: string; ba: number };

/** Палитра сцены: светлые верх/низ и два света за каруселью. */
const LOOK: Record<string, Look> = {
  disco: { top: '#FBE9F2', bottom: '#F5EAF4', a: '#FF3D8B', aa: 0.6, b: '#8E5CFF', ba: 0.5 },
  sneaker: { top: '#E8F6F0', bottom: '#EEF4FA', a: '#2FD39C', aa: 0.5, b: '#4FA8FF', ba: 0.45 },
  padel: { top: '#FCF7DD', bottom: '#F5F2E4', a: '#FFC928', aa: 0.65, b: '#A9DB3A', ba: 0.45 },
  gamepad: { top: '#EAEBFC', bottom: '#F0EDF9', a: '#4A63FF', aa: 0.55, b: '#B04DFF', ba: 0.5 },
  cherries: { top: '#FCEBE6', bottom: '#F4F1E5', a: '#FF3448', aa: 0.55, b: '#52C266', ba: 0.4 },
  laptop: { top: '#F8EEE3', bottom: '#F4EEE7', a: '#C7864F', aa: 0.5, b: '#F3BE85', ba: 0.55 },
  // Трендовые предметы (17.10.2026): свет — из цветов самого предмета.
  matcha: { top: '#EEF6E6', bottom: '#F3F4EA', a: '#7BC043', aa: 0.55, b: '#FF7A90', ba: 0.4 },
  camera: { top: '#EEF0F4', bottom: '#F4EFF2', a: '#9AA6BC', aa: 0.5, b: '#FF6F7F', ba: 0.45 },
  bracelets: { top: '#FBEAF3', bottom: '#F3ECF8', a: '#FF6FA8', aa: 0.55, b: '#B78CFF', ba: 0.5 },
  sunglasses: { top: '#F3EAF8', bottom: '#EEF0FB', a: '#C27BFF', aa: 0.55, b: '#7FA8FF', ba: 0.5 },
  keychain: { top: '#FCE8F0', bottom: '#F7EAF5', a: '#FF4F86', aa: 0.6, b: '#E256D8', ba: 0.5 },
  balloons67: { top: '#FBEDE6', bottom: '#F6ECEA', a: '#F29A7A', aa: 0.55, b: '#FF5C8A', ba: 0.45 },
};

export function MoodBackdrop({ keys, x, pitch }: { keys: string[]; x: RNAnimated.Value | null; pitch: number }) {
  const n = keys.length;
  // Опорные точки по всем трём копиям ленты: у карточки j своя сцена j % n, у соседних — ноль.
  const op = useMemo(() => keys.map((_, k) => {
    if (!x || !pitch) return k === 0 ? 1 : 0;
    // На полпути между карточками обе сцены держатся на 0,8, а не на 0,5: при 0,5 + 0,5 сквозь
    // них просвечивала пустота, и середина жеста выцветала в белое.
    const inputRange: number[] = [], outputRange: number[] = [];
    for (let j = 0; j < n * COPIES; j++) {
      inputRange.push(j * pitch); outputRange.push(j % n === k ? 1 : 0);
      if (j < n * COPIES - 1) {
        inputRange.push((j + 0.5) * pitch);
        outputRange.push(j % n === k || (j + 1) % n === k ? 0.8 : 0);
      }
    }
    return x.interpolate({ inputRange, outputRange, extrapolate: 'clamp' });
  }), [keys.join(','), x, pitch]); // eslint-disable-line react-hooks/exhaustive-deps
  const { width: w, height: h } = useFullScreenSize();
  /*
   * СМОНТИРОВАНЫ ТОЛЬКО ТЕКУЩАЯ СЦЕНА И ДВЕ СОСЕДНИЕ (баг 17.10: «если быстро заходить, фон
   * багается наверху»). Раньше жили все сцены сразу, каждая — полноэкранный растр SVG; при
   * быстром входе iOS не дорисовывал часть слоёв, и сквозь них проступал кремовый фон экрана.
   * Видна в любой момент максимум пара соседних — их и держим; номер берётся из хода ленты.
   */
  const [at, setAt] = useState(0);
  useEffect(() => {
    if (!x || !pitch || !n) return;
    const pick = (v: number) => { const k = ((Math.round(v / pitch) % n) + n) % n; setAt((p) => (p === k ? p : k)); };
    pick((x as any).__getValue ? (x as any).__getValue() : 0);
    const id = x.addListener(({ value }) => pick(value));
    return () => x.removeListener(id);
  }, [x, pitch, n]);
  const near = (i: number) => { const d = Math.abs(i - at) % n; return Math.min(d, n - d) <= 1; };
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      {keys.map((k, i) => (
        <RNAnimated.View key={k} style={[StyleSheet.absoluteFill, { opacity: op[i] as any }]}>
          {near(i) ? <Scene kind={k} /> : null}
        </RNAnimated.View>
      ))}
      {/* Размер задан экраном, а не absoluteFill: Expo Go рисовал файл в пиксельном размере (см. home.tsx). */}
      <Image source={require('../../assets/art/home/silk-shade.png')} style={[s.tex, { width: w, height: h }]} resizeMode="cover" />
      <Image source={require('../../assets/art/home/silk-light.png')} style={[s.tex, { width: w, height: h }]} resizeMode="cover" />
    </View>
  );
}

function Scene({ kind }: { kind: string }) {
  const { width: w, height: h } = useFullScreenSize();
  const L = LOOK[kind] || LOOK.disco;
  const id = `mb_${kind}`;
  return (
    /*
      ПОЛОВИННОЕ РАЗРЕШЕНИЕ: в сцене только мягкие градиенты, разницы на глаз нет, а растр в
      четыре раза легче. Рисуем в половину экрана с полным viewBox и растягиваем вдвое.
    */
    <View style={{ position: 'absolute', left: w / 4, top: h / 4, width: w / 2, height: h / 2, transform: [{ scale: 2 }] }}>
      <Svg width={w / 2} height={h / 2} viewBox={`0 0 ${w} ${h}`}>
        <Defs>
          <LinearGradient id={`${id}_bg`} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={L.top} />
            <Stop offset="1" stopColor={L.bottom} />
          </LinearGradient>
          <RadialGradient id={`${id}_a`} cx="50%" cy="50%" r="50%">
            <Stop offset="0" stopColor={L.a} stopOpacity={L.aa} />
            <Stop offset="0.55" stopColor={L.a} stopOpacity={L.aa * 0.35} />
            <Stop offset="1" stopColor={L.a} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id={`${id}_b`} cx="50%" cy="50%" r="50%">
            <Stop offset="0" stopColor={L.b} stopOpacity={L.ba} />
            <Stop offset="1" stopColor={L.b} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Rect x={0} y={0} width={w} height={h} fill={`url(#${id}_bg)`} />
        {/* Два света за каруселью: главный по центру, второй смещён — цвет не стоит ровным пятном. */}
        <Ellipse cx={w * 0.5} cy={h * CY} rx={w * 0.95} ry={h * 0.36} fill={`url(#${id}_a)`} />
        <Ellipse cx={w * 0.85} cy={h * (CY + 0.2)} rx={w * 0.7} ry={h * 0.26} fill={`url(#${id}_b)`} />
        <Ellipse cx={w * 0.1} cy={h * (CY - 0.08)} rx={w * 0.55} ry={h * 0.2} fill={`url(#${id}_b)`} />
        {/* Низ экрана: без своего света он выцветал в пустой светлый лист (владелец 17.10: «внизу
            пустовато»). Свет слабее верхнего — под колодой и строкой ввода читается текст. */}
        <Ellipse cx={w * 0.15} cy={h * 0.8} rx={w * 1.0} ry={h * 0.26} fill={`url(#${id}_a)`} />
        <Ellipse cx={w * 0.7} cy={h * 0.68} rx={w * 0.7} ry={h * 0.18} fill={`url(#${id}_b)`} opacity={0.8} />
        <Ellipse cx={w * 0.95} cy={h * 0.98} rx={w * 0.9} ry={h * 0.24} fill={`url(#${id}_b)`} />
      </Svg>
    </View>
  );
}

const s = StyleSheet.create({
  tex: { position: 'absolute', left: 0, top: 0 },
});
