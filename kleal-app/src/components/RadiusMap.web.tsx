/**
 * Веб-половина карты. Настоящей карты здесь нет: react-native-maps нативный, а веб-цель нужна
 * только для проверки экранов в браузере. Круг рисуется схематично, чтобы масштаб радиуса всё же
 * читался и экран не разваливался — но выдавать это за карту нельзя, поэтому и подписано.
 *
 * Булавка при этом двигается по-настоящему и считает настоящие координаты: пиксели переводятся в
 * километры по тому же кругу, который нарисован. Так проверяется вся проводка OF.09 — что точку
 * можно взять, что новые координаты доезжают до поиска, — не поднимая симулятор.
 */
import React, { useRef, useState } from 'react';
import { View, Text, StyleSheet, PanResponder } from 'react-native';
import { color, type } from '../theme';

/** Метры в градусе: широта почти постоянна, долгота сжимается к полюсам. */
const KM_PER_DEG_LAT = 110.57;
const kmPerDegLon = (lat: number) => 111.32 * Math.max(0.05, Math.cos((lat * Math.PI) / 180));

export function RadiusMap({
  lat, lon, km, onMove, onDragChange,
}: {
  lat: number; lon: number; km: number;
  onMove?: (lat: number, lon: number) => void;
  onDragChange?: (dragging: boolean) => void;
}) {
  // Диаметр круга пропорционален радиусу, чтобы «5 км» и «40 км» отличались на глаз.
  const size = Math.max(70, Math.min(210, 60 + km * 3));
  const pxPerKm = size / 2 / Math.max(1, km);
  /** Смещение булавки от центра, в пикселях. Копится за жест и в конце уходит координатами. */
  const [off, setOff] = useState({ x: 0, y: 0 });
  const offRef = useRef({ x: 0, y: 0 });
  const start = useRef({ x: 0, y: 0 });
  // PanResponder создаётся один раз, а масштаб и координаты меняются — свежие значения он берёт
  // из ref'ов, иначе жест до конца жизни экрана считал бы километры по первому радиусу.
  const live = useRef({ lat, lon, pxPerKm, onMove, onDragChange });
  live.current = { lat, lon, pxPerKm, onMove, onDragChange };

  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => !!live.current.onMove,
      onMoveShouldSetPanResponder: () => !!live.current.onMove,
      onPanResponderGrant: () => { start.current = { ...offRef.current }; live.current.onDragChange?.(true); },
      onPanResponderMove: (_e, g) => {
        offRef.current = { x: start.current.x + g.dx, y: start.current.y + g.dy };
        setOff(offRef.current);
      },
      onPanResponderRelease: () => {
        const { lat: baseLat, lon: baseLon, pxPerKm: scale, onMove: move, onDragChange: drag } = live.current;
        drag?.(false);
        const { x, y } = offRef.current;
        offRef.current = { x: 0, y: 0 };
        setOff(offRef.current);
        move?.(
          baseLat + (-y / scale) / KM_PER_DEG_LAT,      // экранный y растёт вниз
          baseLon + (x / scale) / kmPerDegLon(baseLat)
        );
      },
      onPanResponderTerminate: () => { live.current.onDragChange?.(false); },
    })
  ).current;

  return (
    <View style={s.wrap}>
      <View style={[s.circle, { width: size, height: size, borderRadius: size / 2 }]} />
      <View
        {...(onMove ? pan.panHandlers : {})}
        style={[s.pin, { transform: [{ translateX: off.x }, { translateY: off.y }] }]}
      >
        <View style={s.pinDot} />
      </View>
      {/* Честно про расхождение: здесь тащат точку, на устройстве — карту под неподвижной
          булавкой (перетаскиваемая метка у MapKit требует долгого нажатия, см. .native). */}
      <Text style={s.note}>{onMove ? 'схема · на устройстве двигается карта' : 'карта — только на устройстве'}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  circle: {
    backgroundColor: 'rgba(241,58,89,0.18)',
    borderWidth: 1,
    borderColor: 'rgba(241,58,89,0.55)',
  },
  pin: {
    position: 'absolute', width: 34, height: 34, borderRadius: 17,
    alignItems: 'center', justifyContent: 'center',
  },
  pinDot: {
    width: 18, height: 18, borderRadius: 9, backgroundColor: color.primary,
    borderWidth: 3, borderColor: '#fff',
  },
  note: { ...type.caption, color: color.neutral400, position: 'absolute', bottom: 8 } as any,
});
