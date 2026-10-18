/**
 * КОРАЛЛОВАЯ КАПЛЯ ЖИДКОГО СТЕКЛА — кнопка отправки и капля, которая от неё отрывается.
 *
 * Решение владельца 17.10.2026: из трёх направлений движения отправки («из поля», «желе»,
 * «жидкость») — «жидкость», и «дай ей эффект liquid glass». Прежняя стрелка была коралловым значком
 * в почти невидимой выемке: «иишно и не насыщенно».
 *
 * СТЕКЛО НАРИСОВАНО, А НЕ СИСТЕМНОЕ. Кнопка лежит внутри стеклянного поля, а системное стекло внутри
 * стекла iOS рисует мутным двойным слоем (см. SendArrow). Поэтому у капли свой «материал» из трёх
 * слоёв, как у настоящего жидкого стекла: тело — коралл, к низу гуще (толща); блик — мягкое белое
 * пятно сверху слева (свет падает сверху); кромка — тонкая светлая обводка по верху и тёплое
 * свечение снизу (свет, прошедший сквозь каплю). Без блика коралловый круг читается плоской
 * наклейкой, с бликом — объёмом.
 *
 * Отлетающую от кнопки каплю (шлейф, всплеск) владелец 17.10.2026 убрал — «убери вылетающую каплю».
 */
import { StyleSheet } from 'react-native';
import Svg, { Circle, Defs, Ellipse, LinearGradient, RadialGradient, Stop } from 'react-native-svg';
import { Easing, withSequence, withTiming } from 'react-native-reanimated';

/** Тело и свет капли. `id` — у каждого рисунка свои градиенты, иначе SVG путает одноимённые. */
export function DropGlass({ size, id, dim = false }: { size: number; id: string; dim?: boolean }) {
  const r = size / 2;
  return (
    <Svg width={size} height={size} style={StyleSheet.absoluteFill} pointerEvents="none">
      <Defs>
        <LinearGradient id={`${id}b`} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={dim ? '#C9CED8' : '#FF6A85'} />
          <Stop offset="0.55" stopColor={dim ? '#B4BAC6' : '#FF385C'} />
          <Stop offset="1" stopColor={dim ? '#A6ADBB' : '#E0193F'} />
        </LinearGradient>
        <RadialGradient id={`${id}h`} cx="0.36" cy="0.26" rx="0.42" ry="0.3">
          <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.85} />
          <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
        </RadialGradient>
        <RadialGradient id={`${id}g`} cx="0.5" cy="0.95" rx="0.5" ry="0.35">
          <Stop offset="0" stopColor="#FFC2CD" stopOpacity={dim ? 0 : 0.7} />
          <Stop offset="1" stopColor="#FFC2CD" stopOpacity={0} />
        </RadialGradient>
        <LinearGradient id={`${id}k`} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.75} />
          <Stop offset="0.5" stopColor="#FFFFFF" stopOpacity={0.05} />
          <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0.35} />
        </LinearGradient>
      </Defs>
      <Circle cx={r} cy={r} r={r} fill={`url(#${id}b)`} />
      <Circle cx={r} cy={r} r={r} fill={`url(#${id}g)`} />
      <Ellipse cx={r * 0.78} cy={r * 0.55} rx={r * 0.55} ry={r * 0.32} fill={`url(#${id}h)`} />
      <Circle cx={r} cy={r} r={r - 0.75} fill="none" stroke={`url(#${id}k)`} strokeWidth={1.5} />
    </Svg>
  );
}

// ============================================================ появление и уход кнопки

/**
 * Капля вытекает из поля: из точки, ширина и высота пружинят в противофазе — желе, а не масштаб.
 * Только масштаб: прозрачность здесь не нужна, а вне стекла она и не запрещена.
 */
export function dropIn() {
  return () => {
    'worklet';
    const k = (to: number, ms: number) => withTiming(to, { duration: ms, easing: Easing.out(Easing.quad) });
    return {
      initialValues: { transform: [{ scaleX: 0.15 }, { scaleY: 0.15 }] },
      animations: {
        transform: [
          { scaleX: withSequence(k(1.22, 150), k(0.9, 110), k(1.05, 100), k(1, 120)) },
          { scaleY: withSequence(k(0.82, 150), k(1.12, 110), k(0.97, 100), k(1, 120)) },
        ],
      },
    };
  };
}

/** Поле опустело — капля растекается обратно в поле: шире и ниже, пока не исчезнет. */
export function dropOut() {
  return () => {
    'worklet';
    const t = { duration: 200, easing: Easing.in(Easing.quad) };
    return {
      initialValues: { opacity: 1, transform: [{ scaleX: 1 }, { scaleY: 1 }] },
      animations: {
        opacity: withTiming(0, t),
        transform: [{ scaleX: withTiming(1.3, t) }, { scaleY: withTiming(0.2, t) }],
      },
    };
  };
}
