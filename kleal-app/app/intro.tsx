/** A.02: one photo, an ephemeral text pager, and the final pull-to-start wave. */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AccessibilityInfo, Image, PanResponder, Pressable, ScrollView,
  StyleSheet, Text, View, useWindowDimensions,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  cancelAnimation, interpolate, runOnJS, useAnimatedStyle, useReducedMotion,
  useSharedValue, withSpring, withTiming,
} from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';
import { SLIDES, INTRO_CTA } from '../src/onboarding';
import { useLang } from '../src/i18n';
import { getState } from '../src/state';
import { color, displayFamily, font, radius, space, type } from '../src/theme';
import { makePull } from '../src/haptics';
import {
  createWelcomeSession, WELCOME_LAST, WAVE_CURVE, welcomeAxis,
  welcomeTarget, welcomePull, welcomePullComplete, type WelcomeAxis,
} from '../src/welcome';

export default function Intro() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width, height, fontScale } = useWindowDimensions();
  const systemReducedMotion = useReducedMotion();
  const [reducedMotion, setReducedMotion] = useState(systemReducedMotion);
  const [index, setIndex] = useState(0);
  const [starting, setStarting] = useState(false);
  const [measurements, setMeasurements] = useState<Record<string, number>>({});
  const session = useRef(createWelcomeSession()).current;
  const axis = useRef<WelcomeAxis>(null);
  const pull = useRef(makePull()).current;
  const slides = SLIDES();
  const progress = useSharedValue(0);
  const lift = useSharedValue(0);
  const last = index === WELCOME_LAST;
  const restH = Math.max(WAVE_CURVE, height * 0.24, insets.bottom + 100);
  const restY = height - restH;
  const travel = restY + WAVE_CURVE;
  const baseBottom = space.xl + insets.bottom;
  const measurementKey = [lang, width, fontScale].join(':');
  const measuredHeight = Math.max(0, ...slides.map((_, n) => measurements[measurementKey + ':' + n] || 0));
  // All pages share the largest measured text viewport; oversized Dynamic Type can scroll.
  const maxTextHeight = Math.max(100, height - insets.top - 48 - 40 - 60 - restH);
  const textHeight = Math.min(measuredHeight || 180, maxTextHeight);
  const baseHeight = 40 + textHeight + 60 + baseBottom;

  useEffect(() => {
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReducedMotion);
    return () => sub.remove();
  }, []);

  const reset = useRef(() => {});
  reset.current = () => {
    session.focus();
    cancelAnimation(progress);
    cancelAnimation(lift);
    progress.value = 0;
    lift.value = 0;
    axis.current = null;
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
    };
  }, [session, progress, lift]));

  useEffect(() => {
    session.interrupt();
    cancelAnimation(progress);
    cancelAnimation(lift);
    progress.value = session.index;
    lift.value = 0;
    axis.current = null;
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

  const gestures = useMemo(() => PanResponder.create({
    // A tap stays with the CTA; a move is claimed only after its axis is unambiguous.
    onStartShouldSetPanResponder: () => false,
    onMoveShouldSetPanResponderCapture: (_e, g) => {
      if (!session.available) return false;
      const direction = welcomeAxis(g.dx, g.dy, session.index === WELCOME_LAST && g.y0 >= restY);
      if (!direction) return false;
      axis.current = direction;
      return true;
    },
    onPanResponderGrant: () => {
      if (axis.current === 'vertical') {
        cancelAnimation(lift);
        pull.grab();
      }
    },
    onPanResponderMove: (_e, g) => {
      if (axis.current === 'horizontal') {
        const p = session.index - g.dx / width;
        progress.value = reducedMotion ? session.index : Math.max(0, Math.min(WELCOME_LAST, p));
      } else if (axis.current === 'vertical') {
        lift.value = reducedMotion ? 0 : welcomePull(g.dy, travel);
        pull.move(Math.max(0, -g.dy), welcomePullComplete(g.dy));
      }
    },
    onPanResponderRelease: (_e, g) => {
      if (axis.current === 'horizontal') goSlide(welcomeTarget(session.index, g.dx, g.vx));
      else if (axis.current === 'vertical') {
        if (welcomePullComplete(g.dy)) {
          pull.release(true);
          start();
        } else returnWave();
      }
      axis.current = null;
    },
    onPanResponderTerminate: () => {
      if (axis.current === 'horizontal') goSlide(session.index);
      else if (axis.current === 'vertical') returnWave();
      axis.current = null;
    },
  }), [width, restY, travel, reducedMotion, session, progress, lift, pull]);

  const sheetStyle = useAnimatedStyle(() => ({
    height: baseHeight + Math.max(0, progress.value - 1) * (restH - baseBottom),
  }));
  const pagesStyle = useAnimatedStyle(() => ({ transform: [{ translateX: -progress.value * width }] }));
  const indicatorStyle = useAnimatedStyle(() => ({ transform: [{ translateX: progress.value * 34 }] }));
  const waveStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: restY - lift.value + (1 - Math.max(0, progress.value - 1)) * restH }],
  }));
  const ctaStyle = useAnimatedStyle(() => ({
    opacity: Math.max(0, progress.value - 1) * interpolate(lift.value, [0, 120], [1, 0], 'clamp'),
  }));

  return (
    <View style={s.wrap} {...gestures.panHandlers} testID="welcome-intro">
      <Image accessible={false} accessibilityIgnoresInvertColors
        source={require('../assets/art/usp-friends-v2.jpg')} style={s.photo} resizeMode="cover" />
      <Animated.View style={[s.sheet, sheetStyle]}>
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
                  <Text accessibilityRole="header" style={[s.h, { fontFamily: displayFamily(lang) }]}>{slide.title}</Text>
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
      <Animated.View pointerEvents="none" style={[s.wave, { height: height + WAVE_CURVE }, waveStyle]}>
        <Svg width={width} height={WAVE_CURVE} viewBox="0 0 390 160" preserveAspectRatio="none">
          <Path d="M0 132 C 78 132 120 20 195 20 C 270 20 312 132 390 132 L390 160 L0 160 Z" fill={color.ink} />
        </Svg>
        <View style={s.waveFill} />
      </Animated.View>
      {last && <Animated.View style={[s.cta, { bottom: Math.max(insets.bottom, space.lg) }, ctaStyle]}>
        <Pressable testID="welcome-start" onPress={start} disabled={starting}
          accessibilityRole="button" accessibilityLabel={INTRO_CTA.start()} accessibilityHint={INTRO_CTA.hint()}
          accessibilityState={{ disabled: starting, busy: starting }}
          accessibilityActions={[{ name: 'activate' }]} onAccessibilityAction={(e) => { if (e.nativeEvent.actionName === 'activate') start(); }}
          style={s.startTouch}>
          <Text style={s.btnText}>{INTRO_CTA.start()}</Text>
        </Pressable>
      </Animated.View>}
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ink, justifyContent: 'flex-end', overflow: 'hidden' },
  photo: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, width: undefined, height: undefined },
  sheet: { backgroundColor: color.card, borderTopLeftRadius: radius.xxl, borderTopRightRadius: radius.xxl, paddingTop: 40, overflow: 'hidden' },
  pages: { flexDirection: 'row' },
  copy: { paddingHorizontal: space.xl },
  h: { ...type.display, letterSpacing: 0, color: color.fg, textAlign: 'center' },
  sub: { ...type.displaySub, color: color.muted, textAlign: 'center', marginTop: space.lg },
  pagination: { height: 60, alignItems: 'center', justifyContent: 'flex-end' },
  bars: { flexDirection: 'row', height: 44, alignItems: 'center' },
  barTouch: { width: 34, height: 44, alignItems: 'center', justifyContent: 'center' },
  bar: { width: 28, height: 2, borderRadius: radius.full, backgroundColor: color.neutral300 },
  barOn: { position: 'absolute', left: 3, top: 21, backgroundColor: color.primary },
  wave: { position: 'absolute', left: 0, right: 0, top: 0 },
  waveFill: { flex: 1, backgroundColor: color.ink },
  cta: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  startTouch: { minHeight: 44, minWidth: 120, paddingHorizontal: space.xl, justifyContent: 'center', alignItems: 'center' },
  btnText: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.onPrimary, textAlign: 'center' },
});
