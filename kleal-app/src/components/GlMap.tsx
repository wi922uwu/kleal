/**
 * Карта MapLibre внутри WebView — то, чем на Android рисуются ВСЕ карты приложения.
 *
 * ПОЧЕМУ НЕ НАТИВНАЯ КАРТА. На Android react-native-maps умеет только карты Google, а ключ,
 * зашитый в сам Expo Go, у Google протух: любой запрос к нему отвечает «The provided API key is
 * expired» (expo/expo#49323, ключ AIzaSyBihTqA0p77LDOPzKNcrjIqAPKwV3OeMyE). Поэтому на всех
 * Android-телефонах — и Samsung, и Huawei — вместо карты оставался серый прямоугольник: сервисы
 * Google на месте, подложка не приходит. Своим ключом это не лечится: ключ читается из манифеста
 * ПРИЛОЖЕНИЯ, а приложение здесь — сам Expo Go, а не мы.
 *
 * ЧТО ВЗАМЕН. Страница /map/ на нашем сервере: MapLibre GL JS и векторные тайлы OpenFreeMap,
 * прокинутые через наш же nginx. Она даёт ровно то, ради чего карта и затевалась, — наклон
 * камеры, объёмные дома и нашу серую схему, — и работает в Expo Go без сборки. Нативная карта
 * при этом никуда не делась: на iOS по-прежнему рисует Apple, там всё в порядке.
 *
 * ГРАНИЦА ОТВЕТСТВЕННОСТИ. Пины живут ВНУТРИ страницы: MapLibre двигает их вместе с картой, и при
 * перетаскивании через мост не идёт ни одного сообщения. Наружу приезжает только то, что нужно
 * экрану: тап по пину, отпущенная карта, готовность. Поверх карты экран волен класть свои вещи —
 * булавку в центре, полосу масштаба, панели, — это обычные View над WebView.
 */
import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Animated, Easing, Platform, StyleSheet, Text, View } from 'react-native';
import { MAP } from '../explore';
import { LogoMark } from './Logo';
import { color, type } from '../theme';
import { WebView } from 'react-native-webview';
import { API_BASE } from '../api';
import { getLang } from '../i18n';

/**
 * Карты рисует MapLibre там, где нативная не работает. На iOS остаётся системная.
 * Глобус — исключение: он на three.js на ОБЕИХ платформах, потому что системные карты шара
 * не умеют вовсе (MapKit показывает плоский мир), а вкладка «Онлайн» обещает именно шар.
 */
export const GL_MAPS = Platform.OS === 'android';
/** Цвет подложки страниц: земля карты и небо шара — то же, что в их CSS. */
const LAND = '#f2f3f5';
const SPACE = '#05070f';

export type GlPin = {
  id: string;
  lat: number; lon: number;
  who?: string; title?: string;
  /** Полный адрес картинки: страница грузит её сама, относительных путей не понимает. */
  photo?: string;
  /** Имя значка категории — то же, что у нативных пинов (см. category-icons). */
  icon?: string;
  /** Сколько интентов стоит в этой точке: подпись «+N» на пине. */
  stack?: number;
};

export type GlCountry = { code: string; lat: number; lon: number; count: number };

export type GlMapHandle = {
  /** Плавно переехать. */
  fly: (o: {
    lat: number; lon: number; zoom?: number; pitch?: number; bearing?: number; duration?: number;
    ease?: 'inout';
  }) => void;
  /** Переставить камеру мгновенно — для жестов, где задержка читается как залипание. */
  jump: (o: { lat: number; lon: number; zoom?: number; pitch?: number; bearing?: number }) => void;
  setZoom: (zoom: number) => void;
  /**
   * СВЕРНУТЬСЯ В ПЛАНЕТУ И ОБРАТНО. Это одна и та же карта: `on: true` — камера отъезжает к
   * нулевому масштабу, и в глобус-проекции плоскость сама становится шаром, а схема
   * перекрашивается в ночную; `on: false` — разворачивается обратно в город. Второго шара нет.
   */
  planet: (o: {
    on: boolean; lat: number; lon: number; zoom?: number; pitch?: number; bearing?: number;
    duration?: number; minZoomAfter?: number;
  }) => void;
  /** Довернуть планету к стране (масштаб пересчитывает страница — у полюсов он другой). */
  country: (code: string | null, duration?: number) => void;
};

type Props = {
  mode: 'explore' | 'radius';
  lat: number; lon: number;
  zoom?: number;
  pitch?: number;
  minZoom?: number; maxZoom?: number;
  /** Можно ли вращать и наклонять пальцами. На карте радиуса — нет. */
  rotate?: boolean;
  /** Полностью выключить жесты: карта как картинка. */
  interactive?: boolean;
  pins?: GlPin[];
  countries?: GlCountry[];
  selectedId?: string | null;
  /** Радиус круга в километрах — только для mode="radius". */
  km?: number;
  onMoveEnd?: (lat: number, lon: number, zoom: number, pitch: number, bearing: number) => void;
  /** Только глобус: куда сейчас смотрит шар (точка в центре), пока он крутится и после остановки. */
  onFacing?: (lat: number, lon: number) => void;
  onDragChange?: (dragging: boolean) => void;
  onPick?: (id: string) => void;
  onPress?: (lat: number, lon: number) => void;
  /** Тайлы дорисованы — экран может убирать заглушку. */
  onLoad?: () => void;
  onError?: (message: string) => void;
  /** Сколько пикселей снизу закрыто листом: планета уходит в оставшееся окно и ужимается. */
  reserveBottom?: number;
  /** Выбранная страна на планете — её плашка подсвечена. */
  selectedCountry?: string | null;
  /** Нажали на плашку страны. */
  onPickCountry?: (code: string) => void;
  testID?: string;
};

export const GlMap = forwardRef<GlMapHandle, Props>(function GlMap(p, ref) {
  const web = useRef<WebView>(null);
  const ready = useRef(false);
  /** Что мы сами отдали наружу: с этим сравниваем пришедшие пропсы, чтобы не гонять карту по кругу. */
  const reported = useRef({ lat: p.lat, lon: p.lon });
  const [ok, setOk] = useState(false);
  const [gone, setGone] = useState(false);
  /** Заставка не пропадает щелчком — тает, пока карта под ней усаживается в свой вид. */
  const veilA = useRef(new Animated.Value(1)).current;

  /*
   * Подложка снимается по сигналу «тайлы дорисованы», но ждать его вечно нельзя: если сеть
   * молчит, человек смотрит на ровное пятно — ровно то, чего мы и добивались избежать.
   * Через восемь секунд открываем карту как есть: пусть лучше будет видно, что она грузится.
   */
  useEffect(() => {
    const timer = setTimeout(() => setOk(true), 8000);
    return () => clearTimeout(timer);
  }, []);
  useEffect(() => {
    if (!ok) return;
    Animated.timing(veilA, { toValue: 0, duration: 700, easing: Easing.out(Easing.cubic), useNativeDriver: true })
      .start(({ finished }) => { if (finished) setGone(true); });
  }, [ok, veilA]);

  const cmd = useCallback((m: any) => {
    // Команда до готовности страницы не теряется: там она копится и проигрывается после загрузки.
    web.current?.injectJavaScript(`window.klealCmd && window.klealCmd(${JSON.stringify(m)}); true;`);
  }, []);

  useImperativeHandle(ref, () => ({
    fly: (o) => { reported.current = { lat: o.lat, lon: o.lon }; cmd({ t: 'fly', ...o }); },
    jump: (o) => { reported.current = { lat: o.lat, lon: o.lon }; cmd({ t: 'jump', ...o }); },
    setZoom: (zoom) => cmd({ t: 'zoom', zoom }),
    planet: (o) => { reported.current = { lat: o.lat, lon: o.lon }; cmd({ t: 'planet', ...o }); },
    country: (code, duration) => cmd({ t: 'country', id: code, duration }),
  }), [cmd]);

  /** Настройки, с которыми страница открывается. Дальше всё приезжает командами. */
  const cfg = useRef({
    mode: p.mode,
    lat: p.lat, lon: p.lon,
    zoom: p.zoom, pitch: p.pitch,
    minZoom: p.minZoom, maxZoom: p.maxZoom,
    rotate: !!p.rotate,
    interactive: p.interactive !== false,
    lang: getLang(),
    km: p.km,
    pins: p.pins, countries: p.countries, selectedId: p.selectedId,
    reserveBottom: p.reserveBottom || 0,
    selectedCountry: p.selectedCountry || null,
    /*
     * ПЕРВЫЙ КАДР — ЧУТЬ ДАЛЬШЕ И ПОЛОЖЕ. Карта интентов открывается не в своём виде, а из
     * него: пока заставка тает, страница сама «усаживает» камеру в рабочий наклон и масштаб.
     * Так первый вход читается как приближение к городу, а не как включение картинки.
     */
    settleFrom: p.mode === 'explore'
      ? { zoom: (p.zoom ?? 13.5) - 0.9, pitch: Math.max(0, (p.pitch ?? 50) - 28) }
      : undefined,
  }).current;

  // ── Пропсы → команды. Каждая — отдельным эффектом: список пинов меняется часто, а точка редко.
  const pinsKey = JSON.stringify((p.pins || []).map((x) => [x.id, x.lat, x.lon, x.stack, x.photo]));
  useEffect(() => {
    if (ready.current && p.pins) cmd({ t: 'pins', pins: p.pins, selectedId: p.selectedId });
  }, [pinsKey]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (ready.current) cmd({ t: 'select', id: p.selectedId });
  }, [p.selectedId, cmd]);

  const countriesKey = JSON.stringify((p.countries || []).map((c) => [c.code, c.count]));
  useEffect(() => {
    if (ready.current && p.countries) cmd({ t: 'countries', countries: p.countries, selectedId: p.selectedCountry });
  }, [countriesKey]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (ready.current && p.mode === 'radius' && p.km != null) cmd({ t: 'radius', lat: p.lat, lon: p.lon, km: p.km });
  }, [p.km, p.lat, p.lon, p.mode, cmd]);

  useEffect(() => {
    // Те же 420/300 мс, что у листа в приложении: планета и лист — одно движение.
    if (ready.current) cmd({ t: 'view', bottom: p.reserveBottom || 0, duration: p.reserveBottom ? 420 : 300 });
  }, [p.reserveBottom, cmd]);

  useEffect(() => {
    if (ready.current) cmd({ t: 'country', id: p.selectedCountry || null });
  }, [p.selectedCountry, cmd]);

  /**
   * Точку сменили СНАРУЖИ (выбрали город, нажали «определить», вернули к дому) — едем к ней.
   * Ответ на собственное движение карты сюда не попадает: пришедшие координаты сверяются с тем,
   * что мы сами только что отдали.
   */
  useEffect(() => {
    if (!ready.current) return;
    const moved = Math.abs(p.lat - reported.current.lat) > 0.0004
               || Math.abs(p.lon - reported.current.lon) > 0.0004;
    if (!moved) return;
    reported.current = { lat: p.lat, lon: p.lon };
    cmd({ t: 'fly', lat: p.lat, lon: p.lon, duration: 350 });
  }, [p.lat, p.lon, cmd]);

  const onMessage = useCallback((e: any) => {
    let m: any;
    try { m = JSON.parse(e.nativeEvent.data); } catch { return; }
    if (m.t === 'ready') {
      ready.current = true;
      /*
       * ДОСЫЛАЕМ ВСЁ, ЧТО ПРИШЛО, ПОКА СТРАНИЦА ГРУЗИЛАСЬ. Настройки уходят ей один раз, при
       * создании; а данные с сервера часто приезжают в те секунды, пока WebView тянет скрипт и
       * текстуру. Эффекты ниже до готовности молчат — и без этой досылки страны на глобусе и
       * пины на карте просто не появлялись: список сменился, когда слать было некому.
       */
      if (p.pins) cmd({ t: 'pins', pins: p.pins, selectedId: p.selectedId });
      if (p.countries) cmd({ t: 'countries', countries: p.countries, selectedId: p.selectedCountry });
      if (p.mode === 'radius' && p.km != null) cmd({ t: 'radius', lat: p.lat, lon: p.lon, km: p.km });
      if (p.reserveBottom) cmd({ t: 'view', bottom: p.reserveBottom });
      return;
    }
    if (m.t === 'load')      { setOk(true); p.onLoad?.(); return; }
    // Палец лёг на карту — экран обязан немедленно выключить свою прокрутку, иначе она
    // перехватит жест и карта под пальцем останется стоять.
    if (m.t === 'touch')     { p.onDragChange?.(!!m.on); return; }
    if (m.t === 'dragstart') { p.onDragChange?.(true); return; }
    if (m.t === 'moveend') {
      p.onDragChange?.(false);
      reported.current = { lat: m.lat, lon: m.lon };
      p.onMoveEnd?.(m.lat, m.lon, m.zoom, m.pitch ?? 0, m.bearing ?? 0);
      return;
    }
    if (m.t === 'facing') { reported.current = { lat: m.lat, lon: m.lon }; p.onFacing?.(m.lat, m.lon); return; }
    if (m.t === 'pick')        { p.onPick?.(m.id); return; }
    if (m.t === 'pickCountry') { p.onPickCountry?.(m.id); return; }
    if (m.t === 'press') { p.onPress?.(m.lat, m.lon); return; }
    if (m.t === 'error') { p.onError?.(String(m.message || '')); return; }
  }, [p]);

  // Карта интентов живёт над космосом: во вкладке «Онлайн» она сама становится планетой.
  const bg = p.mode === 'explore' ? SPACE : LAND;
  return (
    <View style={[s.root, { backgroundColor: bg }]} testID={p.testID}>
      <WebView
        ref={web}
        source={{ uri: `${API_BASE}/map/` }}
        // Настройки должны стоять ДО первой строчки скрипта страницы, иначе карта успеет
        // открыться по умолчанию и дёрнется на нужное место уже на глазах.
        injectedJavaScriptBeforeContentLoaded={`window.KLEAL_CFG = ${JSON.stringify(cfg)}; true;`}
        onMessage={onMessage}
        // Уводить страницу куда-то ещё нечему и незачем: всё, что не наша карта, — отклоняем.
        onShouldStartLoadWithRequest={(r) => r.url.startsWith(API_BASE) || r.url === 'about:blank'}
        originWhitelist={['https://*', 'http://*']}
        javaScriptEnabled
        domStorageEnabled
        cacheEnabled
        // Своя прокрутка WebView только мешает: карту двигает MapLibre, а страница не длиннее экрана.
        scrollEnabled={false}
        overScrollMode="never"
        nestedScrollEnabled={false}
        setSupportMultipleWindows={false}
        allowsInlineMediaPlayback
        mediaPlaybackRequiresUserAction
        // Слой с ускорением: без него объёмные дома на Android едут рывками.
        androidLayerType="hardware"
        // Фон под страницей — цвета самой страницы: у карты светлый, у шара космос. Иначе,
        // пока страница не отрисовалась, слой шара светился белым сквозь затухающую карту.
        style={[s.web, { backgroundColor: bg }]}
        containerStyle={[s.web, { backgroundColor: bg }]}
        onError={(e) => p.onError?.(String(e.nativeEvent?.description || 'webview'))}
        onHttpError={(e) => p.onError?.('http ' + e.nativeEvent?.statusCode)}
      />
      {/*
        Пока тайлы не пришли — не серое пятно, а заставка: у карты интентов это ночь с мягким
        свечением и подписью, у карт радиуса — ровная подложка цвета карты. Тает по сигналу
        «дорисовано», пока камера под ней усаживается в рабочий вид.
      */}
      {gone ? null : (
        <Animated.View style={[s.veil, { backgroundColor: bg, opacity: veilA }]} pointerEvents="none">
          {p.mode === 'explore' ? <MapLoader /> : null}
        </Animated.View>
      )}
    </View>
  );
});

/**
 * Заставка первого входа в карту — капля Кила, как в нижней панели и на входе. Ничего лишнего:
 * капля чуть покачивается, под ней подпись и тонкая линия, по которой ходит короткий штрих.
 * Это тот же знак, что человек уже видел, а не абстрактное свечение.
 */
function MapLoader() {
  const bob = useRef(new Animated.Value(0)).current;
  const run = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const a = Animated.loop(Animated.sequence([
      Animated.timing(bob, { toValue: 1, duration: 1400, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      Animated.timing(bob, { toValue: 0, duration: 1400, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
    ]));
    const b = Animated.loop(Animated.timing(run, { toValue: 1, duration: 1500, easing: Easing.inOut(Easing.cubic), useNativeDriver: true }));
    a.start(); b.start();
    return () => { a.stop(); b.stop(); };
  }, [bob, run]);
  const lift = bob.interpolate({ inputRange: [0, 1], outputRange: [3, -3] });
  const slide = run.interpolate({ inputRange: [0, 1], outputRange: [-44, LINE_W] });
  return (
    <View style={l.root} pointerEvents="none">
      <Animated.View style={{ transform: [{ translateY: lift }] }}>
        <LogoMark width={72} />
      </Animated.View>
      <Text style={l.title}>{MAP.loading()}</Text>
      <Text style={l.note}>{MAP.loadingNote()}</Text>
      <View style={l.track}>
        <Animated.View style={[l.dash, { transform: [{ translateX: slide }] }]} />
      </View>
    </View>
  );
}

const LINE_W = 120;
const l = StyleSheet.create({
  root: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' },
  title: { ...type.title, color: 'rgba(255,255,255,0.92)', marginTop: 18 } as any,
  note: { ...type.caption, color: 'rgba(255,255,255,0.55)', marginTop: 2 } as any,
  track: { width: LINE_W, height: 2, borderRadius: 1, backgroundColor: 'rgba(255,255,255,0.12)', overflow: 'hidden', marginTop: 18 },
  dash: { width: 44, height: 2, borderRadius: 1, backgroundColor: color.primary },
});

const s = StyleSheet.create({
  root: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, overflow: 'hidden', backgroundColor: '#f2f3f5' },
  web: { flex: 1, backgroundColor: '#f2f3f5' },
  veil: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, backgroundColor: '#f2f3f5' },
});
