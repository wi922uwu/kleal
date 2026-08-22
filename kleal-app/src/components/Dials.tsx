/**
 * Круглые регуляторы мастера интента — кадры O.07 (время) и O.08 (возраст-диапазон).
 *
 * Оба построены на той же жестовой механике, что кольцо возраста онбординга (AgeDial), — она
 * выстрадана, а не выбрана: координаты относительно круга (locationX/locationY), без замера позиции
 * на странице, потому что e.currentTarget.measure на вебе падает; capture + отказ от termination +
 * блокировка нативного ответчика, потому что иначе кольцо крутится и вместе с ним едет вся лента.
 * Подробные комментарии — в AgeDial; здесь они не повторяются, чтобы не разъехались.
 *
 * TimeDial — одна ручка, полный круг = сутки, шаг 5 минут. На кадре 20:00 и ручка на ~300°, то
 * есть чтение «полный круг = 24 часа от полуночи сверху» совпадает с бордом.
 *
 * RangeDial — две ручки и дуга между ними (кадр: 18–28). Палец берёт БЛИЖАЙШУЮ ручку и держит её
 * до конца жеста: переключение ручек посреди движения выглядит как скачок и ощущается как поломка.
 * Ручки не перекрещиваются — минимум не заходит за максимум.
 */
import React, { useMemo, useRef } from 'react';
import { View, Text, StyleSheet, PanResponder, GestureResponderEvent } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';
import { hhmm } from '../intent';
import { color } from '../theme';

const SIZE = 208;
const STROKE = 6;
const R = (SIZE - STROKE * 2) / 2 - 8;
const CX = SIZE / 2;
const CY = SIZE / 2;

function angleOf(frac: number) {
  return -Math.PI / 2 + frac * Math.PI * 2;
}
function pointOf(frac: number) {
  const a = angleOf(frac);
  return { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) };
}
/** Доля круга 0..1 из точки касания; null — палец ровно в центре, направление не определено. */
function fracOfTouch(e: GestureResponderEvent): number | null {
  const { locationX, locationY } = e.nativeEvent;
  if (typeof locationX !== 'number' || typeof locationY !== 'number') return null;
  const dx = locationX - CX;
  const dy = locationY - CY;
  if (dx === 0 && dy === 0) return null;
  let a = Math.atan2(dy, dx) + Math.PI / 2;
  if (a < 0) a += Math.PI * 2;
  return a / (Math.PI * 2);
}
/** Круговое расстояние между долями — с учётом перехода через ноль. */
function circDist(a: number, b: number) {
  const d = Math.abs(a - b) % 1;
  return Math.min(d, 1 - d);
}

// ---------------------------------------------------------------- время (O.07)

export function TimeDial({
  minutes, onChange, onDragChange,
}: {
  /** Минуты от полуночи, 0..1435. */
  minutes: number;
  onChange: (m: number) => void;
  onDragChange?: (dragging: boolean) => void;
}) {
  const frac = (((minutes % 1440) + 1440) % 1440) / 1440;

  const changeRef = useRef(onChange);
  changeRef.current = onChange;
  const dragRef = useRef(onDragChange);
  dragRef.current = onDragChange;

  const setFromTouch = (e: GestureResponderEvent) => {
    const f = fracOfTouch(e);
    if (f == null) return;
    changeRef.current(Math.round((f * 1440) / 5) * 5 % 1440);
  };

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
  const large = frac > 0.5 ? 1 : 0;
  const arc = frac <= 0.001 ? '' : `M ${start.x} ${start.y} A ${R} ${R} 0 ${large} 1 ${handle.x} ${handle.y}`;

  return (
    <View style={s.wrap}>
      <View style={{ width: SIZE, height: SIZE }} {...pan.panHandlers}>
        <Svg width={SIZE} height={SIZE}>
          <Circle cx={CX} cy={CY} r={R} stroke={color.neutral100} strokeWidth={STROKE} fill="none" />
          {arc ? <Path d={arc} stroke={color.primary} strokeWidth={STROKE} fill="none" strokeLinecap="round" /> : null}
          <Circle cx={handle.x} cy={handle.y} r={9} fill={color.primary} />
        </Svg>
        <View style={s.center} pointerEvents="none">
          <Text style={s.value}>{hhmm(minutes)}</Text>
        </View>
      </View>
    </View>
  );
}

// ---------------------------------------------------------------- возраст-диапазон (O.08)

export function RangeDial({
  lo, hi, min = 18, max = 80, onChange, onDragChange,
}: {
  lo: number;
  hi: number;
  /** 18 — жёсткий гейт матчинга, ниже спрашивать бессмысленно. */
  min?: number;
  max?: number;
  onChange: (lo: number, hi: number) => void;
  onDragChange?: (dragging: boolean) => void;
}) {
  const span = Math.max(1, max - min);
  const fLo = Math.max(0, Math.min(1, (lo - min) / span));
  const fHi = Math.max(0, Math.min(1, (hi - min) / span));

  const changeRef = useRef(onChange);
  changeRef.current = onChange;
  const dragRef = useRef(onDragChange);
  dragRef.current = onDragChange;
  /** Какая ручка взята этим жестом. Живёт от grant до release — см. шапку файла. */
  const grabbed = useRef<'lo' | 'hi' | null>(null);
  const values = useRef({ lo, hi, fLo, fHi });
  values.current = { lo, hi, fLo, fHi };

  const move = (e: GestureResponderEvent) => {
    const f = fracOfTouch(e);
    if (f == null || !grabbed.current) return;
    const v = Math.round(min + f * span);
    const { lo: curLo, hi: curHi } = values.current;
    if (grabbed.current === 'lo') changeRef.current(Math.min(Math.max(min, v), curHi), curHi);
    else changeRef.current(curLo, Math.max(Math.min(max, v), curLo));
  };

  const pan = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onStartShouldSetPanResponderCapture: () => true,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
        onPanResponderGrant: (e) => {
          dragRef.current?.(true);
          const f = fracOfTouch(e);
          if (f == null) return;
          const { fLo: a, fHi: b } = values.current;
          grabbed.current = circDist(f, a) <= circDist(f, b) ? 'lo' : 'hi';
          move(e);
        },
        onPanResponderMove: move,
        onPanResponderRelease: () => { grabbed.current = null; dragRef.current?.(false); },
        onPanResponderTerminate: () => { grabbed.current = null; dragRef.current?.(false); },
      }),
    []
  );

  const pLo = pointOf(fLo);
  const pHi = pointOf(fHi);
  const delta = fHi - fLo;
  const large = delta > 0.5 ? 1 : 0;
  const arc = delta <= 0.001 ? '' : `M ${pLo.x} ${pLo.y} A ${R} ${R} 0 ${large} 1 ${pHi.x} ${pHi.y}`;

  return (
    <View style={s.wrap}>
      <View style={{ width: SIZE, height: SIZE }} {...pan.panHandlers}>
        <Svg width={SIZE} height={SIZE}>
          <Circle cx={CX} cy={CY} r={R} stroke={color.neutral100} strokeWidth={STROKE} fill="none" />
          {arc ? <Path d={arc} stroke={color.primary} strokeWidth={STROKE} fill="none" strokeLinecap="round" /> : null}
          <Circle cx={pLo.x} cy={pLo.y} r={9} fill={color.primary} />
          <Circle cx={pHi.x} cy={pHi.y} r={9} fill={color.primary} />
        </Svg>
        <View style={s.center} pointerEvents="none">
          <Text style={s.value}>{lo}-{hi}</Text>
        </View>
      </View>
    </View>
  );
}

// ============================================================ вид

const s = StyleSheet.create({
  wrap: { alignItems: 'center' },
  center: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
  value: { fontSize: 40, fontWeight: '700', color: color.fg, letterSpacing: -1 },
});
