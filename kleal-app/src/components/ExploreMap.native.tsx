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
import { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, Image, Platform, PanResponder, Animated } from 'react-native';
import * as Haptics from 'expo-haptics';
import Svg, { Path, Defs, LinearGradient as SvgGrad, Stop } from 'react-native-svg';
import MapView, { Marker, PROVIDER_GOOGLE } from 'react-native-maps';
import { color, shadow, type } from '../theme';
import { mediaUrl } from '../api';
import { CategoryGlyph, iconNameFor } from './category-icons';
import type { ExplorePin } from '../explore';
import { centerOf, pinKey, MORPH } from '../explore';
import { GlMap, GL_MAPS, type GlMapHandle, type GlPin, type GlCountry } from './GlMap';

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
/**
 * Карту интентов рисует MapLibre на ОБЕИХ платформах: только она умеет свернуться в планету на
 * переходе к «Онлайн» (глобус-проекция). Нативная карта Apple оставлена ниже запасным вариантом —
 * без морфа, с простым отъездом камеры.
 */
const NATIVE_EXPLORE = false;
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

type ExploreProps = {
  pins: ExplorePin[];
  center?: { lat: number; lon: number } | null;
  pitch?: number;
  onPick?: (pin: ExplorePin) => void;
  stacks?: Map<string, number>;
  showMe?: boolean;
  recenter?: number;
  selectedId?: string | null;
  /**
   * «Город» — обычный вид; «планета» — камера отъезжает далеко и без наклона. Так карта
   * сама уменьшается в момент перехода на вкладку «Онлайн»: приложение ужимает её слой,
   * а её собственная камера в это же время отдаляется — вместе это читается как одно движение.
   */
  mode?: 'city' | 'planet';
  /** Страны с интентами — плашки на планете (вкладка «Онлайн»). */
  countries?: GlCountry[] | null;
  scanning?: boolean;
  selectedCountry?: string | null;
  onPickCountry?: (code: string) => void;
  /** Сколько пикселей снизу закрыто листом: планета уходит в верхнюю часть окна и ужимается. */
  reserveBottom?: number;
  /** Подвезти камеру к этому пину: меняется счётчик — камера едет. */
  focusPin?: { lat: number; lon: number; n: number } | null;
};

/**
 * На Android карту рисует MapLibre (у Expo Go протух ключ Google — см. GlMap), на iOS остаётся
 * Apple. Наклон, объёмные дома и пины с фотографиями есть в обоих случаях.
 */
export function ExploreMap(props: ExploreProps) {
  return NATIVE_EXPLORE && !GL_MAPS ? <ExploreNative {...props} /> : <ExploreGl {...props} />;
}

function ExploreGl({
  pins, center, pitch = PITCH, onPick, stacks, recenter = 0, selectedId = null, mode = 'city',
  countries = null, selectedCountry = null, onPickCountry, reserveBottom = 0, focusPin = null, scanning = false,
}: ExploreProps) {
  const map = useRef<GlMapHandle>(null);
  const start = center || centerOf(pins) || FALLBACK;
  /** Масштаб держим у себя: полоса слева спрашивает его на каждом касании. */
  const zoom = useRef(ZOOM_START);
  /** Где камера стоит сейчас — по последнему `moveend` с городским масштабом. */
  const cam = useRef({ lat: start.lat, lon: start.lon, zoom: ZOOM_START, pitch, bearing: 0 });
  /** Камера ГОРОДА на момент ухода к планете — сюда и возвращаемся, а не в «центр пинов». */
  const cityCam = useRef(cam.current);

  // Кучка на одной координате — один пин с подписью «+N», как и на нативной карте.
  const shown = useMemo(() => {
    const seen = new Set<string>();
    const out: GlPin[] = [];
    for (const p of pins) {
      const k = pinKey(p);
      if (seen.has(k)) continue;
      seen.add(k);
      out.push({
        id: p.id, lat: p.lat, lon: p.lon,
        who: p.who, title: p.title,
        photo: p.photo ? mediaUrl(p.photo) : undefined,
        icon: iconNameFor(p.topics[0] || ''),
        stack: stacks?.get(k) || 1,
      });
    }
    return out;
  }, [pins, stacks]);

  useEffect(() => {
    if (!recenter) return;
    zoom.current = 14;
    map.current?.fly({ lat: start.lat, lon: start.lon, zoom: 14, pitch, duration: 600 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recenter]);

  /*
   * ПЕРЕХОД К ПЛАНЕТЕ И ОБРАТНО — ОДНА КАМЕРА И ОДИН ШАР.
   * Туда: камера из города отъезжает к нулевому масштабу, и в глобус-проекции карта сама
   * сворачивается в планету, перекрашиваясь в ночную палитру. Обратно: планета разворачивается
   * в ту камеру города, какая была ПЕРЕД уходом — а не в «центр всех пинов»: при пинах в Испании
   * и в Центральной Африке это была середина Сахары.
   */
  const firstMode = useRef(true);
  useEffect(() => {
    if (firstMode.current) { firstMode.current = false; return; }
    if (mode === 'planet') {
      cityCam.current = { ...cam.current };
      map.current?.planet({ on: true, lat: cityCam.current.lat, lon: cityCam.current.lon, duration: MORPH.total });
    } else {
      const home = cityCam.current;
      zoom.current = home.zoom;
      map.current?.planet({ on: false, ...home, duration: MORPH.total, minZoomAfter: ZOOM_MIN });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  /*
   * ПЕРЕЛЁТ К ПИНУ ИЗ СПИСКА. Масштаб берётся не меньше того, на котором пины перестают
   * скучиваться на странице карты, — иначе камера прилетит к кучке, и выбранного пина на
   * месте не окажется.
   */
  useEffect(() => {
    if (!focusPin || mode !== 'city') return;
    const z = Math.max(16.2, zoom.current);
    zoom.current = z;
    map.current?.fly({ lat: focusPin.lat, lon: focusPin.lon, zoom: z, pitch, duration: 760, ease: 'inout' });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusPin?.n]);

  const byId = (id: string) => pins.find((x) => x.id === id);

  return (
    <View style={StyleSheet.absoluteFill}>
      <GlMap
        ref={map}
        mode="explore"
        lat={start.lat} lon={start.lon}
        zoom={ZOOM_START}
        pitch={pitch}
        minZoom={ZOOM_MIN} maxZoom={ZOOM_MAX}
        rotate
        pins={shown}
        selectedId={selectedId}
        countries={countries || undefined}
        scanning={scanning}
        selectedCountry={selectedCountry}
        onPickCountry={onPickCountry}
        reserveBottom={reserveBottom}
        onMoveEnd={(la, lo, z, pt, br) => {
          zoom.current = z;
          // Планета — не городская камера: в память города попадает только вид с городским масштабом.
          if (mode === 'city' && z >= ZOOM_MIN) cam.current = { lat: la, lon: lo, zoom: z, pitch: pt, bearing: br };
        }}
        onPick={(id) => { const p = byId(id); if (p) onPick?.(p); }}
      />
      {/* Полоса масштаба — только у города: планету не приближают. */}
      {mode === 'city' ? (
        <ZoomRail
          get={() => zoom.current}
          set={(z) => { zoom.current = z; map.current?.followZoom(z); }}
        />
      ) : null}
    </View>
  );
}

/** Сколько пикселей пути пальца — один уровень масштаба. Масштаб непрерывный, без шагов. */
const EDGE_PX_PER_ZOOM = 90;
/** Вздутие края у пальца: насколько выпирает и как широко растекается по высоте. */
const EDGE_BULGE = 18;
const EDGE_SPREAD = 96;
const EDGE_BASE = 5;

/**
 * МАСШТАБ — НЕВИДИМЫМ КРАЕМ ЭКРАНА (владелец 17.10.2026, по референсу: край «переплывает», когда
 * тянут пальцем; зум кратный).
 *
 * В покое на краю ничего нет. Палец лёг и повёл — вдоль левого края проступает тонкая стеклянная
 * полоса, и возле пальца край мягко вздувается, как жидкость; вздутие плывёт за пальцем с лёгким
 * отставанием. Отпустили — край опадает и гаснет.
 *
 * Масштаб НЕПРЕРЫВНЫЙ (владелец 17.10 вечером: целые шаги «багаются и магнитятся противно, убери
 * стопы»): палец задаёт цель плавно, страница догоняет её по кадрам (команда zoom с follow), без
 * округления, без доводки к целому при касании и без щелчков отдачи.
 */
function ZoomRail({ get, set }: { get: () => number; set: (z: number) => void }) {
  const [box, setBox] = useState({ w: RAIL_W, h: 0 });
  const [shape, setShape] = useState({ y: 0, a: 0 });          // где вздутие и насколько проявлен край
  const target = useRef({ y: 0, a: 0 });
  const live = useRef({ y: 0, a: 0 });
  const raf = useRef<number | null>(null);
  const grab = useRef({ base: 0, cur: 0, on: false });

  // Плавание: вздутие догоняет палец, проявление нарастает и опадает — по кадрам, мягкой кривой.
  const loop = () => {
    const L = live.current, T = target.current;
    L.y += (T.y - L.y) * 0.22;
    L.a += (T.a - L.a) * (T.a > L.a ? 0.2 : 0.12);
    setShape({ y: L.y, a: L.a });
    if (Math.abs(T.y - L.y) < 0.3 && Math.abs(T.a - L.a) < 0.005) { raf.current = null; if (T.a === 0) setShape({ y: L.y, a: 0 }); return; }
    raf.current = requestAnimationFrame(loop);
  };
  const kick = () => { if (raf.current == null) raf.current = requestAnimationFrame(loop); };
  useEffect(() => () => { if (raf.current != null) cancelAnimationFrame(raf.current); }, []);

  const rail = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_e, g) =>
        Math.abs(g.dy) > 6 && Math.abs(g.dy) > Math.abs(g.dx) * 1.5,
      onPanResponderGrant: (e) => {
        // Отсчёт от того масштаба, где карта стоит: касание само ничего не двигает.
        const z0 = get();
        grab.current = { base: z0, cur: z0, on: true };
        live.current.y = target.current.y = e.nativeEvent.locationY;
        target.current.a = 1; kick();
      },
      onPanResponderMove: (e, g) => {
        if (!grab.current.on) return;
        target.current.y = e.nativeEvent.locationY; kick();
        const z = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, grab.current.base - g.dy / EDGE_PX_PER_ZOOM));
        if (Math.abs(z - grab.current.cur) > 0.004) { grab.current.cur = z; set(z); }
      },
      onPanResponderRelease: () => { grab.current.on = false; target.current.a = 0; kick(); },
      onPanResponderTerminate: () => { grab.current.on = false; target.current.a = 0; kick(); },
    })
  ).current;

  // Контур края: тонкая полоса во всю высоту, у пальца — гауссово вздутие; к концам сходит на нет.
  const { h } = box, a = shape.a;
  let d = '';
  if (h > 0 && a > 0.01) {
    const pts: string[] = [];
    for (let yy = 0; yy <= h; yy += 6) {
      const ends = Math.min(1, yy / 60) * Math.min(1, (h - yy) / 60);
      const bulge = EDGE_BULGE * Math.exp(-Math.pow((yy - shape.y) / EDGE_SPREAD, 2));
      pts.push(`${((EDGE_BASE + bulge) * a * ends).toFixed(1)},${yy}`);
    }
    d = `M0,0 L${pts.join(' L')} L0,${h} Z`;
  }
  return (
    <View style={s.rail} {...rail.panHandlers} onLayout={(e) => setBox({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })}>
      {d ? (
        <Svg width={EDGE_BASE + EDGE_BULGE + 4} height={h} style={StyleSheet.absoluteFill} pointerEvents="none">
          <Defs>
            <SvgGrad id="edge" x1="0" y1="0" x2="1" y2="0">
              <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.55 * a} />
              <Stop offset="1" stopColor="#C9CDD4" stopOpacity={0.9 * a} />
            </SvgGrad>
          </Defs>
          <Path d={d} fill="url(#edge)" stroke="rgba(24,27,34,0.10)" strokeWidth={1} />
        </Svg>
      ) : null}
    </View>
  );
}

function ExploreNative({
  pins,
  center,
  pitch = PITCH,
  onPick,
  stacks,
  showMe = false,
  recenter = 0,
  mode = 'city',
  selectedId = null,
}: {
  pins: ExplorePin[];
  center?: { lat: number; lon: number } | null;
  pitch?: number;
  onPick?: (pin: ExplorePin) => void;
  stacks?: Map<string, number>;
  showMe?: boolean;
  recenter?: number;
  mode?: 'city' | 'planet';
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

  const firstMode = useRef(true);
  useEffect(() => {
    if (firstMode.current) { firstMode.current = false; return; }
    ref.current?.animateCamera(
      mode === 'planet'
        ? { center: { latitude: start.lat, longitude: start.lon }, pitch: 0, zoom: 3.2, altitude: 12_000_000 }
        : { center: { latitude: start.lat, longitude: start.lon }, pitch, zoom: ZOOM_START, altitude: 2500 },
      { duration: 700 }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

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
        showsPointsOfInterests={false}
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
              <PinBubble p={p} on={on} n={n} />
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

/** Сам пин: фото, значок категории, «+N» на кучке, хвостик и точка привязки. */
function PinBubble({ p, on, n }: { p: ExplorePin; on: boolean; n: number }) {
  return (
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
            <CategoryGlyph name={iconNameFor(p.topics[0] || '')} size={12} />
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
