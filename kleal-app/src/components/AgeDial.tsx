/**
 * Кольцевой выбор возраста — кадр A.05.
 *
 * Кольцо со значением в центре и ручкой, которую тянут пальцем. Реализовано на PanResponder из
 * стандартной поставки, без жестовых библиотек: одна ручка и один круг того не стоят.
 *
 * Про соответствие борду. На кадре видно кольцо, число 28 в центре, красную дугу и две точки —
 * сверху и снизу. Какому диапазону соответствует такая дуга, из статичного кадра не выводится:
 * это может быть и «от 18 сверху по часовой», и «дуга от 12 до 6 часов». Сделано самое обычное
 * чтение — полный круг от 12 часов по часовой стрелке, диапазон MIN..MAX, — и это место надо
 * сверить с бордом, когда вернётся квота Figma. Отмечено, а не выдано за точное совпадение.
 */
import React, { useMemo, useRef } from 'react';
import { View, Text, StyleSheet, PanResponder, GestureResponderEvent } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';
import { color, radius as rad, type } from '../theme';

const MIN = 18;
const MAX = 80;
const SIZE = 208;
const STROKE = 6;
const R = (SIZE - STROKE * 2) / 2 - 8;
const CX = SIZE / 2;
const CY = SIZE / 2;

/** Угол в радианах для доли 0..1, начиная с 12 часов и по часовой стрелке. */
function angleOf(frac: number) {
  return -Math.PI / 2 + frac * Math.PI * 2;
}
function pointOf(frac: number) {
  const a = angleOf(frac);
  return { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) };
}

export function AgeDial({
  value, onChange, onDragChange,
}: {
  value: number;
  onChange: (v: number) => void;
  /** Пока крутят кольцо, лента под ним должна стоять. Подробнее — у PanResponder ниже. */
  onDragChange?: (dragging: boolean) => void;
}) {
  const frac = Math.max(0, Math.min(1, (value - MIN) / (MAX - MIN)));

  // Координаты берём ОТНОСИТЕЛЬНО самого круга (locationX/locationY), а не через замер его позиции
  // на странице. Первая версия мерила позицию в onLayout через e.currentTarget.measure — на вебе
  // currentTarget там undefined, и экран падал. Относительные координаты не требуют замера вообще,
  // поэтому не зависят ни от прокрутки, ни от платформы.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const setFromTouch = (e: GestureResponderEvent) => {
    const { locationX, locationY } = e.nativeEvent;
    if (typeof locationX !== 'number' || typeof locationY !== 'number') return;
    const dx = locationX - CX;
    const dy = locationY - CY;
    if (dx === 0 && dy === 0) return;
    // atan2 даёт угол от оси X; сдвигаем на четверть, чтобы ноль был сверху, и нормализуем в 0..1
    let a = Math.atan2(dy, dx) + Math.PI / 2;
    if (a < 0) a += Math.PI * 2;
    const f = a / (Math.PI * 2);
    onChangeRef.current(Math.round(MIN + f * (MAX - MIN)));
  };

  const dragRef = useRef(onDragChange);
  dragRef.current = onDragChange;

  /**
   * Кольцо живёт внутри прокручиваемой ленты, и по умолчанию лента жест отбирает: палец идёт вниз —
   * RN спрашивает у текущего «ответчика», отдаст ли он жест прокрутке, и ответ по умолчанию «да».
   * Получалось, что кольцо крутится и вместе с ним едет весь экран.
   *
   * Отсюда три вещи сразу. Capture — забрать жест до детей. TerminationRequest false — не отдавать
   * его ленте. onShouldBlockNativeResponder — то же самое для нативной прокрутки на Android, где
   * одного JS-ответчика не хватает. И вдобавок лента на время выключается совсем: это единственное,
   * что не зависит от версии RN.
   */
  const pan = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onStartShouldSetPanResponderCapture: () => true,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
        onPanResponderGrant: (e) => { dragRef.current?.(true); setFromTouch(e); },
        onPanResponderMove: setFromTouch,
        onPanResponderRelease: () => dragRef.current?.(false),
        onPanResponderTerminate: () => dragRef.current?.(false),
      }),
    []
  );

  const handle = pointOf(frac);
  const start = pointOf(0);
  // Дуга от 12 часов до текущего значения. large-arc нужен, когда прошли больше половины круга.
  const large = frac > 0.5 ? 1 : 0;
  const arc =
    frac <= 0.001
      ? ''
      : `M ${start.x} ${start.y} A ${R} ${R} 0 ${large} 1 ${handle.x} ${handle.y}`;

  return (
    <View style={s.wrap}>
      <View style={{ width: SIZE, height: SIZE }} {...pan.panHandlers}>
        <Svg width={SIZE} height={SIZE}>
          <Circle cx={CX} cy={CY} r={R} stroke={color.neutral100} strokeWidth={STROKE} fill="none" />
          {arc ? (
            <Path d={arc} stroke={color.primary} strokeWidth={STROKE} fill="none" strokeLinecap="round" />
          ) : null}
          <Circle cx={start.x} cy={start.y} r={7} fill={color.primary} />
          <Circle cx={handle.x} cy={handle.y} r={9} fill={color.primary} />
        </Svg>
        <View style={s.center} pointerEvents="none">
          <Text style={s.value}>{value}</Text>
        </View>
      </View>

      <View style={s.pill}>
        <Text style={s.pillText}>{value}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { alignItems: 'center', gap: 14 },
  center: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
  value: { fontSize: 44, fontWeight: '700', color: color.fg, letterSpacing: -1 },
  pill: {
    minWidth: 78,
    height: 40,
    borderRadius: rad.full,
    backgroundColor: color.neutral100,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 18,
  },
  pillText: { ...type.body, color: color.fg } as any,
});
