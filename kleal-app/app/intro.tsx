/** A.02: one photo, an ephemeral text pager, and the final pull-to-start wave. */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AccessibilityInfo, Image, PanResponder, Pressable, ScrollView,
  StyleSheet, Text, View, useWindowDimensions, type GestureResponderEvent,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  Easing,
  cancelAnimation, interpolate, runOnJS, useAnimatedStyle, useReducedMotion,
  useSharedValue, withSpring, withTiming,
} from 'react-native-reanimated';
import Svg, { Defs, Ellipse, Path, RadialGradient, Stop } from 'react-native-svg';
import { GlassSurface } from '../src/components/LiquidGlass';
import { SLIDES, INTRO_CTA } from '../src/onboarding';
import { useLang } from '../src/i18n';
import { getState } from '../src/state';
import { color, font, heading, radius, space, type } from '../src/theme';
import { makePull } from '../src/haptics';
import {
  createWelcomeSession, WELCOME_LAST, WAVE_CURVE, WELCOME_WAVE_PATH, welcomeWaveContains, welcomeAxis,
  welcomeTarget, welcomePull, welcomePullComplete, type WelcomeAxis,
} from '../src/welcome';

export default function Intro() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width, height: winH, fontScale } = useWindowDimensions();
  const systemReducedMotion = useReducedMotion();
  const [reducedMotion, setReducedMotion] = useState(systemReducedMotion);
  const [index, setIndex] = useState(0);
  const [starting, setStarting] = useState(false);
  const [measurements, setMeasurements] = useState<Record<string, number>>({});
  const session = useRef(createWelcomeSession()).current;
  const axis = useRef<WelcomeAxis>(null);
  const root = useRef<View>(null);
  const rootPosition = useRef({ x: 0, y: 0 });
  const touch = useRef<{ x: number; y: number; canPull: boolean; lift: number; distance: number } | null>(null);
  const pull = useRef(makePull()).current;
  const slides = SLIDES();
  const progress = useSharedValue(0);
  const lift = useSharedValue(0);
  /** Лист выезжает снизу на пружине при первом показе — стекло «всплывает» над фотографией. */
  const rise = useSharedValue(1);
  const last = index === WELCOME_LAST;
  /*
    ВЫСОТА — ИЗМЕРЕННАЯ, А НЕ «ОКНА». На части Android окно (`useWindowDimensions`) меньше того, что
    экран на самом деле занимает: приложение рисуется и под строкой состояния, а окно её вычитает.
    Горб считался от окна, лист — от настоящего низа, и горб поднимался на эту разницу (~43 точки),
    закрывая полоски листания (снимок тестировщика, 26.09). До первого замера — окно, как раньше.
  */
  const [boxH, setBoxH] = useState(0);
  const height = boxH || winH;
  // Коробка вкладки прижата низом к краю экрана: горб «Let’s Start» стоит на самом низу, как в макете.
  const restH = WAVE_CURVE;
  const restY = height - restH;
  // Место под листом, которое занимают точки листания и вкладка.
  const reserve = Math.max(88, insets.bottom + 64);
  const travel = restY + WAVE_CURVE;
  const measurementKey = [lang, width, fontScale].join(':');
  const measuredHeight = Math.max(0, ...slides.map((_, n) => measurements[measurementKey + ':' + n] || 0));
  // All pages share the largest measured text viewport; oversized Dynamic Type can scroll.
  const maxTextHeight = Math.max(100, height - insets.top - 48 - 40 - 60 - reserve);
  const textHeight = Math.min(measuredHeight || 180, maxTextHeight);
  // Reserve the final wave on every page; paging never moves the white panel's top.
  const sheetHeight = 40 + textHeight + 60 + reserve;

  useEffect(() => {
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReducedMotion);
    return () => sub.remove();
  }, []);
  useEffect(() => {
    if (reducedMotion) { rise.value = 0; return; }
    rise.value = withTiming(0, { duration: 520, easing: Easing.out(Easing.cubic) });
  }, []);

  const reset = useRef(() => {});
  reset.current = () => {
    session.focus();
    cancelAnimation(progress);
    cancelAnimation(lift);
    progress.value = 0;
    lift.value = 0;
    axis.current = null;
    touch.current = null;
    setIndex(0);
    setStarting(false);
    const account = getState();
    if (account.login && account.done) router.replace('/home');
  };
  useFocusEffect(useCallback(() => {
    reset.current();
    return () => {
      session.blur();
      cancelAnimation(progress);
      cancelAnimation(lift);
      axis.current = null;
      touch.current = null;
    };
  }, [session, progress, lift]));

  useEffect(() => {
    session.interrupt();
    cancelAnimation(progress);
    cancelAnimation(lift);
    progress.value = session.index;
    lift.value = 0;
    axis.current = null;
    touch.current = null;
    setStarting(false);
  }, [width, height, fontScale, lang, reducedMotion, session, progress, lift]);

  const finishSlide = (token: number, to: number) => {
    if (session.settle(token, to)) setIndex(to);
  };
  const goSlide = (to: number) => {
    const target = Math.max(0, Math.min(WELCOME_LAST, to));
    const token = session.begin();
    if (token === null) return;
    if (reducedMotion) {
      progress.value = target;
      finishSlide(token, target);
      return;
    }
    progress.value = withTiming(target, { duration: 240 }, (finished) => {
      if (finished) runOnJS(finishSlide)(token, target);
    });
  };
  const openOnboarding = (token: number) => {
    if (session.complete(token)) router.navigate('/auth');
  };
  const start = () => {
    if (session.index !== WELCOME_LAST) return;
    const token = session.begin();
    if (token === null) return;
    setStarting(true);
    if (reducedMotion) {
      openOnboarding(token);
      return;
    }
    lift.value = withTiming(travel, { duration: 380 }, (finished) => {
      if (finished) runOnJS(openOnboarding)(token);
    });
  };
  const returnWave = () => {
    pull.release(false);
    lift.value = reducedMotion ? 0 : withSpring(0, { damping: 24, stiffness: 190, mass: 0.9 });
  };

  const gestures = useMemo(() => {
    const sample = (e: GestureResponderEvent) => {
      const origin = touch.current;
      if (!origin) return null;
      // PanResponder resets dx/dy on grant; native page coordinates preserve the full drag.
      const dx = e.nativeEvent.pageX - origin.x, dy = e.nativeEvent.pageY - origin.y;
      origin.distance = Math.max(origin.distance, Math.hypot(dx, dy));
      axis.current ||= welcomeAxis(dx, dy, origin.canPull);
      return { dx, dy, origin };
    };
    const move = (e: GestureResponderEvent) => {
      const point = sample(e);
      if (!point) return;
      if (axis.current === 'horizontal') {
        const p = session.index - point.dx / width;
        progress.value = reducedMotion ? session.index : Math.max(0, Math.min(WELCOME_LAST, p));
      } else if (axis.current === 'vertical') {
        const dy = point.dy - point.origin.lift;
        lift.value = reducedMotion ? 0 : welcomePull(dy, travel);
        pull.move(Math.max(0, -dy), welcomePullComplete(dy));
      }
    };
    const cancel = () => {
      if (axis.current === 'horizontal') goSlide(session.index);
      if (touch.current?.canPull) returnWave();
      touch.current = null;
      axis.current = null;
    };
    return PanResponder.create({
      // Own the entire black surface immediately, including curve/edges and the CTA text.
      // y0 is still zero before grant; never use it to decide who receives a gesture.
      onStartShouldSetPanResponderCapture: (e) => {
        if (e.nativeEvent.touches.length !== 1) { cancel(); return false; }
        touch.current = null;
        axis.current = null;
        if (!session.available) return false;
        const { pageX: x, pageY: y } = e.nativeEvent;
        const canPull = session.index === WELCOME_LAST && welcomeWaveContains(
          x - rootPosition.current.x, y - rootPosition.current.y, width, restY, height, lift.value,
        );
        touch.current = { x, y, canPull, lift: lift.value, distance: 0 };
        if (canPull) { cancelAnimation(lift); pull.grab(); }
        return canPull;
      },
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponderCapture: (e) => {
        if (!session.available || e.nativeEvent.touches.length !== 1) return false;
        return Boolean(sample(e) && axis.current);
      },
      onPanResponderGrant: move,
      onPanResponderStart: (e) => {
        if (e.nativeEvent.touches.length !== 1) cancel();
      },
      onPanResponderMove: (e) => {
        if (e.nativeEvent.touches.length !== 1) cancel();
        else move(e);
      },
      onPanResponderRelease: (e, g) => {
        const point = sample(e);
        if (!point) return;
        touch.current = null;
        if (axis.current === 'horizontal') {
          if (point.origin.canPull) returnWave();
          goSlide(welcomeTarget(session.index, point.dx, g.vx));
        } else if (axis.current === 'vertical') {
          if (welcomePullComplete(point.dy - point.origin.lift)) {
            pull.release(true);
            start();
          } else returnWave();
        } else if (point.origin.canPull && point.origin.distance < 8) { pull.release(true); start(); }
        else if (point.origin.canPull) returnWave();
        axis.current = null;
      },
      onPanResponderTerminationRequest: () => true,
      onPanResponderTerminate: cancel,
    });
  }, [width, height, restY, travel, reducedMotion, session, progress, lift, pull]);

  const pagesStyle = useAnimatedStyle(() => ({ transform: [{ translateX: -progress.value * width }] }));
  const indicatorStyle = useAnimatedStyle(() => ({ transform: [{ translateX: progress.value * 34 }] }));
  const waveStyle = useAnimatedStyle(() => ({
    // Keep the same black silhouette on every page; only the last page can lift it.
    transform: [{ translateY: restY - lift.value }],
  }));
  // Только сдвиг: у листа внутри стекло, а стекло под прозрачностью < 1 не рисуется.
  const sheetRise = useAnimatedStyle(() => ({
    transform: [{ translateY: rise.value * 120 }],
  }));
  const ctaStyle = useAnimatedStyle(() => ({
    opacity: Math.max(0, progress.value - 1) * interpolate(lift.value, [0, 120], [1, 0], 'clamp'),
  }));

  return (
    <View ref={root} style={s.wrap} {...gestures.panHandlers} testID="welcome-intro"
      onLayout={(e) => {
        const h = Math.round(e?.nativeEvent?.layout?.height || 0);
        if (h > 0 && Math.abs(h - boxH) > 1) setBoxH(h);
        root.current?.measureInWindow((x, y) => { rootPosition.current = { x, y }; });
      }}>
      <Image accessible={false} accessibilityIgnoresInvertColors
        source={require('../assets/art/usp-friends-v2.jpg')} style={s.photo} resizeMode="cover" />
      {/* Розовое свечение из-под листа (rb_112211 в макете: #FF6A83 с размытием 248). */}
      <Svg pointerEvents="none" style={StyleSheet.absoluteFill} width={width} height={height}>
        <Defs>
          <RadialGradient id="introGlow">
            <Stop offset="0" stopColor="#FF6A83" stopOpacity={0.85} />
            <Stop offset="1" stopColor="#FF6A83" stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Ellipse cx={width * 0.95} cy={height * 0.8} rx={width * 0.75} ry={height * 0.38} fill="url(#introGlow)" />
      </Svg>
      <Animated.View style={[s.sheet, { height: sheetHeight }, sheetRise]} testID="welcome-sheet">
        {/*
          Лист — жидкое стекло ПЛОТНОЕ («прозрачность белого нужно убавить, нечитаемый текст»,
          тестировщик 27.09): фото лишь угадывается, текст читается на любом месте снимка.
        */}
        <GlassSurface tone="veil" radius={40} style={s.sheetGlass} pointerEvents="none" />
        <View style={{ height: textHeight, overflow: 'hidden' }}>
          <Animated.View style={[s.pages, { width: width * slides.length }, pagesStyle]}>
            {slides.map((slide, n) => (
              <ScrollView key={slide.art} style={{ width, height: textHeight, flexGrow: 0, flexShrink: 0 }}
                bounces={false} showsVerticalScrollIndicator={measuredHeight > maxTextHeight}
                accessibilityElementsHidden={n !== index} importantForAccessibility={n !== index ? 'no-hide-descendants' : 'auto'}>
                <View key={measurementKey} style={s.copy} onLayout={(e) => {
                  const h = Math.ceil(e.nativeEvent.layout.height);
                  const key = measurementKey + ':' + n;
                  setMeasurements((old) => old[key] === h ? old : { ...old, [key]: h });
                }}>
                  <Text accessibilityRole="header" style={[s.h, heading(lang, type.heading)]}>{slide.title}</Text>
                  <Text style={s.sub}>{slide.sub}</Text>
                </View>
              </ScrollView>
            ))}
          </Animated.View>
        </View>
        <View style={s.pagination}>
          <View style={s.bars} accessible accessibilityRole="adjustable"
            accessibilityLabel={INTRO_CTA.slide(index + 1, slides.length)}
            accessibilityValue={{ text: INTRO_CTA.slide(index + 1, slides.length) }}
            accessibilityActions={[{ name: 'increment', label: INTRO_CTA.next() }, { name: 'decrement', label: INTRO_CTA.previous() }]}
            onAccessibilityAction={(e) => {
              if (e.nativeEvent.actionName === 'increment') goSlide(index + 1);
              if (e.nativeEvent.actionName === 'decrement') goSlide(index - 1);
            }}>
            {slides.map((slide, n) => (
              <Pressable key={slide.art} testID={'welcome-page-' + n} onPress={() => goSlide(n)}
                accessible={false} style={s.barTouch}><View style={s.bar} /></Pressable>
            ))}
            <Animated.View pointerEvents="none" style={[s.bar, s.barOn, indicatorStyle]} />
          </View>
        </View>
      </Animated.View>
      <Animated.View testID="welcome-wave" pointerEvents="none" accessible={false} style={[s.wave, { height: height + WAVE_CURVE }, waveStyle]}>
        <Svg width={width} height={WAVE_CURVE} viewBox="0 0 390 160" preserveAspectRatio="none">
          <Path d={WELCOME_WAVE_PATH} fill={color.ink} />
        </Svg>
        <View style={s.waveFill} />
      </Animated.View>
      {/*
        ПОДПИСЬ ЖИВЁТ ВНУТРИ ВКЛАДКИ. Вкладка — горб 60 точек у самого края (кадр A.02: 218×60,
        текст на 23 ниже вершины и на 17 выше края экрана). Раньше подпись ставилась от безопасного
        отступа (34) и центровалась в касании 44 — её верх выходил на 6 точек выше горба, «Начать»
        висело над тёмной областью. Теперь низ текста — 17 от края, как в макете; касание 44
        остаётся, просто уходит поверх домашней полосы.
      */}
      {last && <Animated.View style={[s.cta, { bottom: CTA_TEXT_BOTTOM - (44 - 20) / 2 }, ctaStyle]}>
        <Pressable testID="welcome-start" onPress={start} disabled={starting}
          accessibilityRole="button" accessibilityLabel={INTRO_CTA.start()} accessibilityHint={INTRO_CTA.hint()}
          accessibilityState={{ disabled: starting, busy: starting }}
          accessibilityActions={[{ name: 'activate' }]} onAccessibilityAction={(e) => { if (e.nativeEvent.actionName === 'activate') start(); }}
          style={s.startTouch}>
          <Text style={s.btnText} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.8}>{INTRO_CTA.start()}</Text>
        </Pressable>
      </Animated.View>}
    </View>
  );
}

/** Низ подписи «Начать» от края экрана — из кадра A.02 (844 − 827). */
const CTA_TEXT_BOTTOM = 17;

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ink, justifyContent: 'flex-end', overflow: 'hidden' },
  photo: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, width: undefined, height: undefined },
  /** Лист в макете отступает от краёв на 8 и скруглён сверху — стекло лежит на фото, а не режет его. */
  sheet: { marginHorizontal: 8, paddingTop: 40, borderTopLeftRadius: 40, borderTopRightRadius: 40, overflow: 'hidden' },
  sheetGlass: { position: 'absolute', left: 0, right: 0, top: 0, bottom: -40 },
  pages: { flexDirection: 'row' },
  copy: { paddingHorizontal: space.xl + 3 },
  h: { color: color.fg, textAlign: 'center' },
  sub: { ...type.displaySub, color: '#404652', textAlign: 'center', marginTop: space.xl },
  pagination: { height: 60, alignItems: 'center', justifyContent: 'flex-end' },
  bars: { flexDirection: 'row', height: 44, alignItems: 'center' },
  barTouch: { width: 34, height: 44, alignItems: 'center', justifyContent: 'center' },
  // Неактивные полоски — серые: лист теперь плотный белый, и белые полоски на нём пропадали.
  bar: { width: 28, height: 2, borderRadius: radius.full, backgroundColor: 'rgba(24,27,34,0.18)' },
  barOn: { position: 'absolute', left: 3, top: 21, backgroundColor: '#FF385C' },
  wave: { position: 'absolute', left: 0, right: 0, top: 0 },
  waveFill: { flex: 1, backgroundColor: color.ink },
  cta: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  /** Ширина касания не больше вкладки у её вершины: длинная подпись ужимается, а не вылезает. */
  startTouch: { minHeight: 44, minWidth: 140, maxWidth: 170, paddingHorizontal: space.md, justifyContent: 'center', alignItems: 'center' },
  btnText: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.onPrimary, textAlign: 'center' },
});
