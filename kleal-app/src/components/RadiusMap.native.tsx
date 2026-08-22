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

  /**
   * МАСШТАБ ПРИНАДЛЕЖИТ ЧЕЛОВЕКУ, А НЕ РАДИУСУ.
   *
   * Здесь была поломка, из-за которой карта отъезжала сама: масштаб всегда считался от километров,
   * и эффект возвращал его при КАЖДОМ срабатывании. Пинч сдвигает центр на несколько десятков
   * метров → `onMove` → родитель меняет lat/lon → эффект видит «точка та же» → и анимирует назад
   * к масштабу от радиуса. Со стороны это ровно «приближаю, а оно отдаляется».
   *
   * Теперь то, что человек выставил пальцами, запоминается и переживает и смену точки, и правку
   * радиуса ползунком. Масштаб пересчитывается от километров только когда километры И ПРАВДА
   * поменялись — то есть когда человек тянет ползунок радиуса и ждёт, что круг впишется в экран.
   */
  const userZoom = useRef<{ latD: number; lonD: number } | null>(null);
  const lastKm = useRef(km);

  const fitDelta = Math.max(0.05, (km / 111) * 2.6);   // ~110 км в градусе, плюс поля вокруг круга
  const zoom = () => userZoom.current ?? { latD: fitDelta, lonD: fitDelta };
  const regionAt = (la: number, lo: number, z = zoom()): Region =>
    ({ latitude: la, longitude: lo, latitudeDelta: z.latD, longitudeDelta: z.lonD });

  /**
   * Карта следует за точкой, когда точку поменял НЕ жест по карте: другой город, «определить моё
   * местоположение», «вернуть к дому», другой радиус. Раньше здесь стояло условие «только когда
   * изменился радиус» — и выбор другого города не двигал карту вообще, потому что километры при
   * этом те же.
   */
  useEffect(() => {
    const moved = Math.abs(lat - reported.current.lat) > EPS || Math.abs(lon - reported.current.lon) > EPS;
    const kmChanged = km !== lastKm.current;

    // Ничего существенного не произошло — и трогать карту НЕЛЬЗЯ. Именно здесь стояла безусловная
    // анимация, съедавшая приближение.
    if (!moved && !kmChanged) return;

    if (kmChanged) {
      // Радиус тянут ползунком — человек ждёт, что круг впишется. Это единственный случай, когда
      // мы вправе назначить масштаб сами, и заодно единственный, когда его выбор сбрасывается.
      lastKm.current = km;
      userZoom.current = null;
      programmatic.current = true;
      ref.current?.animateToRegion(regionAt(lat, lon, { latD: fitDelta, lonD: fitDelta }), 250);
      return;
    }

    // Точку сменили снаружи — едем к ней, СОХРАНЯЯ масштаб: человек приблизился к своему двору,
    // и возвращать его на общий план только потому, что сменился город, незачем.
    reported.current = { lat, lon };
    programmatic.current = true;
    ref.current?.animateToRegion(regionAt(lat, lon), 350);
  }, [lat, lon, km]);

  /** Карту отпустили — точкой становится её центр. */
  const settle = (r: Region) => {
    onDragChange?.(false);
    // Масштаб запоминаем ВСЕГДА, даже после собственной анимации: иначе следующий переезд к
    // новой точке взял бы масштаб от радиуса и снова отдалил бы карту.
    userZoom.current = { latD: r.latitudeDelta, lonD: r.longitudeDelta };
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
    ref.current?.animateToRegion(regionAt(c.latitude, c.longitude), 250);
    reported.current = { lat: c.latitude, lon: c.longitude };
    programmatic.current = true;
    onMove(c.latitude, c.longitude);
  };

  return (
    <View style={StyleSheet.absoluteFill}>
      <MapView
        ref={ref}
        style={StyleSheet.absoluteFill}
        initialRegion={regionAt(lat, lon, { latD: fitDelta, lonD: fitDelta })}
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
