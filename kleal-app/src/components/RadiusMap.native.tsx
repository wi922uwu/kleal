/**
 * Карта с кругом радиуса — нативная половина.
 *
 * Разделено по платформам суффиксом файла, а не проверкой Platform.OS внутри одного модуля:
 * условный require всё равно попадает в веб-бандл, и Metro падает на нативном модуле
 * («Importing native-only module … codegenNativeCommands on web»). Суффикс решает это на уровне
 * разрешения путей — веб про этот файл просто не узнаёт.
 *
 * ТОЧКУ ВЫБИРАЕТ КАРТА, А НЕ БУЛАВКА. Булавка нарисована поверх карты и намертво стоит в центре;
 * двигают саму карту, а точкой становится то, что оказалось под булавкой. Так устроены все экраны
 * «укажи место» в такси и доставке, и на телефоне это единственный работающий способ.
 *
 * Почему не перетаскиваемый Marker, как было сначала. У MapKit (и у Google Maps) draggable-метка
 * берётся только ДОЛГИМ НАЖАТИЕМ — обычный тап с протяжкой карта считает своим жестом и просто
 * прокручивается. Снаружи это выглядит ровно так, как и было сказано: «метка не перетаскивается».
 * Просить человека держать палец секунду, чтобы поставить точку, — не решение.
 *
 * Прокрутка. Карта живёт внутри ScrollView, и жест у них общий: без onDragChange родительский
 * список забирает вертикальное движение себе, и карта не двигается вовсе.
 */
import React, { useEffect, useRef } from 'react';
import { View, StyleSheet } from 'react-native';
import MapView, { Circle, MapPressEvent, Region } from 'react-native-maps';
import { color } from '../theme';

/** Насколько координаты должны разойтись, чтобы считать это переездом, а не дрожанием региона. */
const EPS = 0.0004;   // ~45 метров

export function RadiusMap({
  lat, lon, km, onMove, onDragChange,
}: {
  lat: number; lon: number; km: number;
  onMove?: (lat: number, lon: number) => void;
  onDragChange?: (dragging: boolean) => void;
}) {
  const ref = useRef<MapView>(null);
  /**
   * Регион, который мы поставили САМИ (выбрали город, нажали «определить», вернули к дому).
   * Ответный onRegionChangeComplete от собственной анимации надо проглотить, иначе получается
   * кольцо: мы двигаем карту → карта сообщает координаты → координаты приходят пропсами → мы
   * снова двигаем карту.
   */
  const programmatic = useRef(false);
  /** Последнее, что мы отдали наружу, — с чем сравнивать пришедшие пропсы. */
  const reported = useRef({ lat, lon });

  const delta = Math.max(0.05, (km / 111) * 2.6);   // ~110 км в градусе, плюс поля вокруг круга
  const region: Region = { latitude: lat, longitude: lon, latitudeDelta: delta, longitudeDelta: delta };

  /**
   * Карта следует за точкой, когда точку поменял НЕ жест по карте: другой город, «определить моё
   * местоположение», «вернуть к дому», другой радиус. Раньше здесь стояло условие «только когда
   * изменился радиус» — и выбор другого города не двигал карту вообще, потому что километры при
   * этом те же.
   */
  useEffect(() => {
    const moved = Math.abs(lat - reported.current.lat) > EPS || Math.abs(lon - reported.current.lon) > EPS;
    if (!moved) {
      // Радиус поменялся при той же точке — подгоняем масштаб, но это тоже наша анимация.
      programmatic.current = true;
      ref.current?.animateToRegion(region, 250);
      return;
    }
    reported.current = { lat, lon };
    programmatic.current = true;
    ref.current?.animateToRegion(region, 350);
  }, [lat, lon, km]);

  /** Карту отпустили — точкой становится её центр. */
  const settle = (r: Region) => {
    onDragChange?.(false);
    if (programmatic.current) { programmatic.current = false; return; }
    if (!onMove) return;
    if (Math.abs(r.latitude - reported.current.lat) < EPS
        && Math.abs(r.longitude - reported.current.lon) < EPS) return;
    reported.current = { lat: r.latitude, lon: r.longitude };
    onMove(r.latitude, r.longitude);
  };

  /** Тап по карте — то же самое, но одним движением: подъезжаем к точке, центр её и подхватит. */
  const jump = (e: MapPressEvent) => {
    const c = e.nativeEvent?.coordinate;
    if (!c || !onMove) return;
    ref.current?.animateToRegion({ ...region, latitude: c.latitude, longitude: c.longitude }, 250);
    reported.current = { lat: c.latitude, lon: c.longitude };
    programmatic.current = true;
    onMove(c.latitude, c.longitude);
  };

  return (
    <View style={StyleSheet.absoluteFill}>
      <MapView
        ref={ref}
        style={StyleSheet.absoluteFill}
        initialRegion={region}
        // Без onMove это просто картинка (профиль, онбординг «только посмотреть») — жесты мешают.
        scrollEnabled={!!onMove}
        zoomEnabled={!!onMove}
        rotateEnabled={false}
        pitchEnabled={false}
        onTouchStart={() => onDragChange?.(true)}
        onRegionChangeComplete={settle}
        onPress={onMove ? jump : undefined}
      >
        <Circle
          center={{ latitude: lat, longitude: lon }}
          radius={km * 1000}
          strokeColor="rgba(241,58,89,0.55)"
          fillColor="rgba(241,58,89,0.18)"
        />
      </MapView>

      {/*
        Булавка поверх карты, а не Marker внутри неё: Marker живёт в координатах и во время
        прокрутки уезжает вместе с картой, а нам нужна ровно обратная связь — точка стоит, мир
        едет. pointerEvents="none", иначе она перехватывает жест у карты под собой.
      */}
      <View style={s.pinWrap} pointerEvents="none">
        <View style={s.pinStem} />
        <View style={s.pinHead} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  pinWrap: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Головка на 11 пикселей выше центра, а ножка ровно на нём: остриё указывает на точку, а не
  // круг закрывает её собой.
  pinHead: {
    position: 'absolute',
    marginBottom: 22,
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: color.primary,
    borderWidth: 3, borderColor: '#fff',
  },
  pinStem: {
    position: 'absolute',
    marginBottom: 5,
    width: 2, height: 14,
    backgroundColor: color.primary,
  },
});
