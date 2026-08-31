/**
 * Карта открытых интентов — нативная половина (кадры «Search · Map» и «Pin selected»).
 *
 * ПОЧЕМУ react-native-maps, А НЕ MapLibre.
 * MapLibre пробовали: он даёт и точный стиль макета, и объёмные дома на бесплатных тайлах
 * OpenFreeMap (слой `building` там несёт `render_height`). Но это НАТИВНЫЙ модуль, которого нет
 * в Expo Go, а проект намеренно сидит на SDK 54 ровно ради Expo Go — см. AGENTS.md. Поставить
 * MapLibre значит в тот же день перевести всех на dev build. Поэтому здесь то, что уже встроено
 * в Expo Go и уже стоит в проекте.
 *
 * 3D ПРИ ЭТОМ ОСТАЁТСЯ. Наклон камеры — `camera.pitch`, объёмные дома — `showsBuildings`; и то и
 * другое рисует системная карта: Apple на iOS, Google на Android. Обе умеют это в Expo Go.
 *
 * ЧТО ТЕРЯЕТСЯ. Подложку под макет можно подогнать ТОЛЬКО на Android: `customMapStyle` работает
 * лишь у Google. На iOS карта останется стандартной эппловской — светло-серую схему с крупными
 * названиями районов там задать нечем. Это цена за Expo Go, и она видна глазом: расхождение с
 * макетом на iOS — не баг, а следствие выбора.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, Image, Platform, PanResponder, Animated } from 'react-native';
import * as Haptics from 'expo-haptics';
import MapView, { Marker, PROVIDER_GOOGLE } from 'react-native-maps';
import { color, shadow, type } from '../theme';
import { mediaUrl } from '../api';
import { categoryIcon, iconNameFor } from './category-icons';
import type { ExplorePin } from '../explore';
import { centerOf, pinKey } from '../explore';

const FALLBACK = { lat: 41.3874, lon: 2.1686 };   // Барселона: тот же запасной центр, что в мастере

/** Наклон. Выше 60° системные карты всё равно не дают, а на 50° дома читаются лучше всего. */
const PITCH = 50;

/**
 * ПОЛЗУНОК МАСШТАБА — левый край карты.
 *
 * Зачем: свести и развести двумя пальцами можно только двумя руками, а карту чаще смотрят одной,
 * держа телефон. Полоса вдоль левого края даёт масштаб большим пальцем той же руки.
 *
 * ПОЧЕМУ ОН ПОЛУПРОЗРАЧНЫЙ, А НЕ ЯРКИЙ. На кадре его нет вовсе, и спорить с пинами за внимание он
 * не должен: в покое это едва заметный след, подсказка «здесь что-то есть». Под пальцем он
 * проявляется — становится видно, где стоит масштаб и куда он едет. Гасить его совсем оказалось
 * плохо: жест, о котором нельзя догадаться глазом, находят только те, кому о нём рассказали.
 */
const ZOOM_MIN = 3;
const ZOOM_MAX = 19;
/** Сколько пикселей пути даёт один шаг масштаба. Меньше — дёргается, больше — вязнет. */
const PX_PER_ZOOM = 64;
/** Ширина полосы. Уже — не попасть большим пальцем, шире — начинает отбирать жесты у карты. */
const RAIL_W = 30;

/** Насколько виден в покое и под пальцем. Разница должна читаться, но не мигать в глаза. */
const REST = 0.22;
const HELD = 1;
/** Высота бегунка. */
const THUMB_H = 44;
/** Масштаб, с которого открывается карта. Одно число на камеру и на положение бегунка, чтобы не разошлись. */
const ZOOM_START = 13.5;
const fracOf = (z: number) => Math.max(0, Math.min(1, (z - ZOOM_MIN) / (ZOOM_MAX - ZOOM_MIN)));

const canBuzz = Platform.OS !== 'web';
/** Короткий отклик на каждом целом шаге масштаба — как щелчок колеса, а не долгая вибрация. */
const tick = () => { if (canBuzz) Haptics.selectionAsync().catch(() => {}); };

/**
 * Светло-серая подложка макета — для Google (Android). Точки интереса и транспорт спрятаны:
 * на кадре их нет, а бросаться в глаза должны пины людей, а не станции метро.
 */
const GREY: any[] = [
  { elementType: 'geometry', stylers: [{ color: '#f2f3f5' }] },
  { elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#7b8190' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#ffffff' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#ffffff' }] },
  { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#fbfbfc' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#e4e7ec' }] },
  { featureType: 'landscape.man_made', elementType: 'geometry', stylers: [{ color: '#eceef2' }] },
];

export function ExploreMap({
  pins,
  center,
  pitch = PITCH,
  onPick,
  stacks,
  showMe = false,
  recenter = 0,
  selectedId = null,
}: {
  pins: ExplorePin[];
  center?: { lat: number; lon: number } | null;
  pitch?: number;
  onPick?: (pin: ExplorePin) => void;
  stacks?: Map<string, number>;
  showMe?: boolean;
  recenter?: number;
  selectedId?: string | null;
}) {
  const ref = useRef<MapView>(null);
  const start = center || centerOf(pins) || FALLBACK;

  /**
   * Кучка на одной координате показывается ОДНИМ пином с подписью «ещё N».
   * Иначе интенты, стоящие в одной точке, рисуются друг поверх друга и выглядят как один —
   * человек видит на карте меньше, чем есть, и не знает об этом.
   */
  const shown = useMemo(() => {
    const seen = new Set<string>();
    const out: ExplorePin[] = [];
    for (const p of pins) {
      const k = pinKey(p);
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(p);
    }
    return out;
  }, [pins]);

  /**
   * Состояние жеста живёт в ref, а не в state: PanResponder создаётся один раз, и через замыкание
   * он видел бы только первые значения. Плюс перерисовка на каждый пиксель здесь не нужна —
   * карту двигает камера, а не React.
   */
  const zoomRef = useRef({ start: 0, alt: 0, step: 0 });

  /**
   * Вид ползунка живёт на Animated, а не на state: под пальцем значение меняется каждый кадр, и
   * перерисовывать на это всю карту с пинами нельзя — жест начал бы заикаться.
   * `railH` — единственное, что попадает в state, и только один раз, после замера.
   */
  const [railH, setRailH] = useState(0);
  const glow = useRef(new Animated.Value(REST)).current;
  /** Доля 0..1 по полосе: 0 — самый мелкий масштаб внизу, 1 — самый крупный вверху. */
  const frac = useRef(new Animated.Value(fracOf(ZOOM_START))).current;

  const showZoom = (z: number) => { frac.setValue(fracOf(z)); };

  const fade = (to: number) => {
    Animated.timing(glow, { toValue: to, duration: to === HELD ? 120 : 420, useNativeDriver: true }).start();
  };

  const rail = useRef(
    PanResponder.create({
      // Касание не перехватываем: тап по этой полосе должен доставаться карте.
      onStartShouldSetPanResponder: () => false,
      // Забираем жест только на ВЕРТИКАЛЬНОМ движении — иначе полоса съедала бы у карты
      // горизонтальную прокрутку у самого края.
      onMoveShouldSetPanResponder: (_e, g) =>
        Math.abs(g.dy) > 6 && Math.abs(g.dy) > Math.abs(g.dx) * 1.5,
      onPanResponderGrant: () => {
        fade(HELD);
        ref.current?.getCamera().then((c: any) => {
          const z0 = typeof c?.zoom === 'number' ? c.zoom : 14;
          zoomRef.current = {
            start: z0,
            alt: typeof c?.altitude === 'number' ? c.altitude : 0,
            // Отсчёт щелчков начинается с ТЕКУЩЕГО шага, а не с нуля: иначе первый же пиксель
            // движения давал бы отклик на пустом месте, до того как масштаб реально сменился.
            step: Math.round(z0),
          };
          showZoom(z0);
        }).catch(() => {});
      },
      onPanResponderMove: (_e, g) => {
        const z0 = zoomRef.current.start;
        if (!z0) return;
        // Палец вверх — ближе. Экранный y растёт вниз, отсюда минус.
        const dz = -g.dy / PX_PER_ZOOM;
        const z = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z0 + dz));
        const step = Math.round(z);
        if (step !== zoomRef.current.step) {
          zoomRef.current.step = step;
          tick();                       // щелчок на каждом целом шаге, а не на каждом пикселе
        }
        // У Apple масштаб — это ВЫСОТА камеры, у Google — zoom. Шлём оба: платформа возьмёт своё.
        // Высота меняется вдвое на шаг масштаба, отсюда степень двойки.
        const patch: any = { zoom: z };
        if (zoomRef.current.alt) patch.altitude = zoomRef.current.alt / Math.pow(2, z - z0);
        // setCamera, а не animateCamera: анимация тянулась бы за пальцем с задержкой.
        ref.current?.setCamera(patch);
        showZoom(z);
      },
      onPanResponderRelease: () => { zoomRef.current.start = 0; fade(REST); },
      onPanResponderTerminate: () => { zoomRef.current.start = 0; fade(REST); },
    })
  ).current;

  useEffect(() => {
    if (!recenter) return;
    ref.current?.animateCamera(
      { center: { latitude: start.lat, longitude: start.lon }, pitch, zoom: 14 },
      { duration: 600 }
    );
    // start пересчитывается на каждом рендере, поэтому его нет в зависимостях намеренно:
    // камера должна ехать по команде, а не сама при любом обновлении списка.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recenter]);

  return (
    <View style={StyleSheet.absoluteFill}>
      <MapView
        ref={ref}
        style={StyleSheet.absoluteFill}
        // Свой стиль умеет только Google, поэтому на Android провайдер задан явно, а на iOS
        // остаётся системный: подсовывать туда Google значило бы тащить ключ и терять Expo Go.
        provider={Platform.OS === 'android' ? PROVIDER_GOOGLE : undefined}
        customMapStyle={Platform.OS === 'android' ? GREY : undefined}
        initialCamera={{
          center: { latitude: start.lat, longitude: start.lon },
          pitch,
          heading: 0,
          zoom: ZOOM_START,
          altitude: 2500,
        }}
        // Ради наклона всё и затевалось: в RadiusMap он выключен намеренно, здесь обязателен.
        pitchEnabled
        rotateEnabled
        showsBuildings
        showsUserLocation={showMe}
        showsMyLocationButton={false}
        showsPointsOfInterest={false}
        toolbarEnabled={false}
      >
        {shown.map((p) => {
          const n = stacks?.get(pinKey(p)) || 1;
          const on = !!selectedId && p.id === selectedId;
          return (
            <Marker
              key={p.id}
              coordinate={{ latitude: p.lat, longitude: p.lon }}
              anchor={{ x: 0.5, y: 1 }}
              // Метка своя, поэтому системную булавку гасим — иначе она проступает снизу
              // и пин двоится. tracksViewChanges=false ещё и снимает перерисовку каждого кадра.
              tracksViewChanges={false}
              onPress={onPick ? () => onPick(p) : undefined}
            >
              <View
                accessibilityRole="button"
                accessibilityState={{ selected: on }}
                accessibilityLabel={`${p.who || p.title} — ${p.area}`}
                style={[s.pin, on && s.pinOn]}
              >
                <View style={[s.head, on && s.headOn]}>
                  {p.photo ? (
                    <Image source={{ uri: mediaUrl(p.photo) }} style={[s.photo, on && s.photoOn]} />
                  ) : (
                    <View style={[s.photo, on && s.photoOn, s.photoEmpty]}>
                      <Text style={s.initial}>{(p.who || p.title || '?').slice(0, 1).toUpperCase()}</Text>
                    </View>
                  )}
                  <View style={[s.badge, on && s.badgeOn]}>
                    {categoryIcon(iconNameFor(p.topics[0] || ''), '#fff')}
                  </View>
                  {n > 1 ? (
                    <View style={s.stack}>
                      <Text style={s.stackText}>+{n - 1}</Text>
                    </View>
                  ) : null}
                </View>
                {/* Хвостик и точка привязки: без них пин висит над местом, а не указывает на него. */}
                <View style={[s.tail, on && s.tailOn]} />
                <View style={s.anchor} />
              </View>
            </Marker>
          );
        })}
      </MapView>

      {/*
        Полоса. Ловит жест на всю свою ширину, а рисует тонкий след — попасть пальцем надо
        в удобную зону, а видеть достаточно намёк. Сверху и снизу оставлены поля, чтобы не
        перехватывать плашку «сколько рядом», карточку пина и панель сегментов.
      */}
      <View
        style={s.rail}
        onLayout={(e) => setRailH(e.nativeEvent.layout.height)}
        {...rail.panHandlers}
      >
        <Animated.View style={[s.track, { opacity: glow }]} pointerEvents="none" />
        {railH ? (
          <Animated.View
            pointerEvents="none"
            style={[
              s.thumb,
              {
                opacity: glow,
                transform: [{
                  // Доля 1 — вверху: экранный y растёт вниз, поэтому шкала перевёрнута.
                  translateY: frac.interpolate({
                    inputRange: [0, 1],
                    outputRange: [railH - THUMB_H, 0],
                  }),
                }],
              },
            ]}
          />
        ) : null}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  rail: { position: 'absolute', left: 0, top: 120, bottom: 220, width: RAIL_W },
  /** След полосы: тоньше зоны касания и прижат к краю — он подсказка, а не орган управления. */
  track: {
    position: 'absolute', left: 10, top: 0, bottom: 0, width: 3,
    borderRadius: 2, backgroundColor: color.neutral400,
  },
  thumb: {
    position: 'absolute', left: 7, width: 9, height: THUMB_H,
    borderRadius: 5, backgroundColor: color.fg,
  },
  pin: { width: 52, alignItems: 'center' },
  pinOn: { width: 62 },
  head: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: color.card,
    borderWidth: 2, borderColor: color.card, ...shadow.card,
  },
  photo: { width: 40, height: 40, borderRadius: 20 },
  photoOn: { width: 50, height: 50, borderRadius: 25 },
  photoEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  initial: { ...type.labelMedium, color: color.muted } as any,
  // Выбранный: кольцо и хвост красные — на кадре «Pin selected» именно этим он и отличается.
  headOn: { width: 54, height: 54, borderRadius: 27, borderColor: color.primary, borderWidth: 3 },
  badgeOn: { width: 24, height: 24, borderRadius: 12, right: -8 },
  tailOn: { borderTopColor: color.primary, borderLeftWidth: 7, borderRightWidth: 7, borderTopWidth: 11 },
  badge: {
    position: 'absolute', right: -6, bottom: -2, width: 20, height: 20, borderRadius: 10,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1.5, borderColor: color.card,
  },
  stack: {
    position: 'absolute', left: -8, top: -4, minWidth: 20, height: 20, borderRadius: 10,
    paddingHorizontal: 5, backgroundColor: color.fg, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1.5, borderColor: color.card,
  },
  stackText: { ...type.labelSmall, color: color.onPrimary } as any,
  tail: {
    width: 0, height: 0, marginTop: -2,
    borderLeftWidth: 6, borderRightWidth: 6, borderTopWidth: 9,
    borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: color.card,
  },
  anchor: {
    width: 6, height: 6, borderRadius: 3, marginTop: 1,
    backgroundColor: color.primary,
  },
});
