/**
 * Карта с кругом радиуса — нативная половина.
 *
 * Разделено по платформам суффиксом файла, а не проверкой Platform.OS внутри одного модуля:
 * условный require всё равно попадает в веб-бандл, и Metro падает на нативном модуле
 * («Importing native-only module … codegenNativeCommands on web»). Суффикс решает это на уровне
 * разрешения путей — веб про этот файл просто не узнаёт.
 *
 * Точку можно двигать (OF.09). Раньше карта висела с `pointerEvents="none"` — то есть была
 * картинкой: круг рисовался вокруг координат профиля, и человек, который сегодня не дома, никак
 * не мог сказать «ищи вон там». Теперь булавка перетаскивается, а тап по карте переносит её.
 *
 * Прокрутка. Карта живёт внутри ScrollView, и жест у них общий: без onDragChange родительский
 * список забирает вертикальное движение себе, и булавка дёргается на месте. Родитель обязан
 * выключить свою прокрутку на время касания — в мастере интента для этого уже есть `dragging`.
 */
import React, { useEffect, useRef } from 'react';
import { StyleSheet } from 'react-native';
import MapView, { Circle, Marker, MapPressEvent, MarkerDragStartEndEvent } from 'react-native-maps';

export function RadiusMap({
  lat, lon, km, onMove, onDragChange,
}: {
  lat: number; lon: number; km: number;
  onMove?: (lat: number, lon: number) => void;
  onDragChange?: (dragging: boolean) => void;
}) {
  const ref = useRef<MapView>(null);
  const lastKm = useRef(km);
  const delta = Math.max(0.05, (km / 111) * 2.6);   // ~110 км в градусе, плюс поля вокруг круга
  const region = { latitude: lat, longitude: lon, latitudeDelta: delta, longitudeDelta: delta };

  // Подгоняем вид ТОЛЬКО когда изменился радиус. Гнаться за каждой новой координатой нельзя:
  // человек тащит булавку, а карта под ней уезжает к её новому центру — точка убегает из-под пальца.
  useEffect(() => {
    if (lastKm.current === km) return;
    lastKm.current = km;
    ref.current?.animateToRegion(region, 350);
  }, [km]);

  const move = (e: MapPressEvent | MarkerDragStartEndEvent) => {
    const c = e.nativeEvent?.coordinate;
    if (c && onMove) onMove(c.latitude, c.longitude);
  };

  return (
    <MapView
      ref={ref}
      style={StyleSheet.absoluteFill}
      initialRegion={region}
      // Без onMove это по-прежнему просто картинка (профиль, онбординг) — там жесты только мешают.
      scrollEnabled={!!onMove}
      zoomEnabled={!!onMove}
      rotateEnabled={false}
      pitchEnabled={false}
      onTouchStart={() => onDragChange?.(true)}
      onTouchEnd={() => onDragChange?.(false)}
      onTouchCancel={() => onDragChange?.(false)}
      onPress={onMove ? move : undefined}
    >
      <Circle
        center={{ latitude: lat, longitude: lon }}
        radius={km * 1000}
        strokeColor="rgba(241,58,89,0.55)"
        fillColor="rgba(241,58,89,0.18)"
      />
      <Marker
        coordinate={{ latitude: lat, longitude: lon }}
        draggable={!!onMove}
        onDragStart={() => onDragChange?.(true)}
        onDragEnd={(e) => { move(e); onDragChange?.(false); }}
      />
    </MapView>
  );
}
