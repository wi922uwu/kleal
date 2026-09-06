/**
 * A.05 age ruler. The track moves continuously under one fixed coral selection line and settles
 * only on whole years. User-driven integer changes emit feedback; hydration and prop sync do not.
 */
import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Animated,
  AppState,
  PanResponder,
  StyleSheet,
  View,
  useWindowDimensions,
  type AccessibilityActionEvent,
} from 'react-native';
import Svg, { Defs, G, LinearGradient, Line, Mask, Rect, Stop } from 'react-native-svg';
import { createAudioPlayer, type AudioPlayer } from 'expo-audio';
import {
  AGE_FEEDBACK_INTERVAL_MS,
  AGE_MAX,
  AGE_MIN,
  AGE_STEP_PX,
  ageRulerCopy,
  ageToOffset,
  clampAge,
  offsetToAge,
  shouldEmitAgeFeedback,
  snapAgeOffset,
} from '../age-ruler';
import { hTick } from '../haptics';
import type { ReplyLang } from '../i18n';
import { color, font } from '../theme';

const AnimatedGroup = Animated.createAnimatedComponent(G);
const VALUES = Array.from({ length: AGE_MAX - AGE_MIN + 1 }, (_, index) => AGE_MIN + index);
const TICK_HEIGHT = 23;
const LONG_TICK_HEIGHT = 34;
const CENTER_HEIGHT = 48;
const BAND_HEIGHT = 54;
const FRICTION = 0.992;

export type AgeDialProps = Readonly<{
  value: number;
  onChange: (value: number) => void;
  locale?: ReplyLang;
  /** While the ruler owns the gesture, the surrounding chat feed must stay still. */
  onDragChange?: (dragging: boolean) => void;
}>;

export function AgeDial({
  value,
  onChange,
  locale = 'en',
  onDragChange,
}: AgeDialProps) {
  const selected = clampAge(value);
  const copy = ageRulerCopy(locale, selected);
  const { width } = useWindowDimensions();
  const bandWidth = Math.max(280, width);
  const half = bandWidth / 2;

  const offset = useRef(new Animated.Value(ageToOffset(selected))).current;
  const valuePulse = useRef(new Animated.Value(0)).current;
  const gestureStart = useRef(ageToOffset(selected));
  const shownAge = useRef(selected);
  const lastFeedbackAt = useRef(0);
  const fixingEdge = useRef(false);
  const userMotion = useRef(false);
  const motionToken = useRef(0);
  const appActive = useRef(AppState.currentState === 'active');
  const mounted = useRef(false);
  const audioBusy = useRef(false);
  const audioUnlock = useRef<ReturnType<typeof setTimeout> | null>(null);
  const player = useRef<AudioPlayer | null>(null);
  const change = useRef(onChange);
  const drag = useRef(onDragChange);
  change.current = onChange;
  drag.current = onDragChange;

  useEffect(() => {
    mounted.current = true;
    try {
      player.current = createAudioPlayer(require('../../assets/sounds/click.wav'));
    } catch {
      player.current = null;
    }
    return () => {
      mounted.current = false;
      if (audioUnlock.current) clearTimeout(audioUnlock.current);
      try { player.current?.remove(); } catch {}
      player.current = null;
    };
  }, []);

  const playClick = useCallback(() => {
    const current = player.current;
    if (!current || audioBusy.current || !appActive.current) return;
    audioBusy.current = true;
    try {
      Promise.resolve(current.seekTo(0))
        .then(() => {
          if (mounted.current && appActive.current) current.play();
        })
        .catch(() => {})
        .finally(() => {
          if (!mounted.current) return;
          audioUnlock.current = setTimeout(() => {
            audioBusy.current = false;
            audioUnlock.current = null;
          }, AGE_FEEDBACK_INTERVAL_MS);
        });
    } catch {
      // A missing/invalid native audio resource must never block the ruler itself.
      audioBusy.current = false;
    }
  }, []);

  const emitUserAge = useCallback((nextValue: number) => {
    const next = clampAge(nextValue);
    const previous = shownAge.current;
    if (next === previous) return;
    shownAge.current = next;
    change.current(next);

    valuePulse.stopAnimation();
    valuePulse.setValue(0);
    Animated.sequence([
      Animated.timing(valuePulse, { toValue: 1, duration: 70, useNativeDriver: true }),
      Animated.timing(valuePulse, { toValue: 0, duration: 130, useNativeDriver: true }),
    ]).start();

    const now = Date.now();
    if (!shouldEmitAgeFeedback({
      previousAge: previous,
      nextAge: next,
      now,
      lastFeedbackAt: lastFeedbackAt.current,
      userInitiated: true,
      appActive: appActive.current,
    })) return;
    lastFeedbackAt.current = now;
    hTick();
    playClick();
  }, [playClick, valuePulse]);

  const finishUserMotion = useCallback((token: number) => {
    if (motionToken.current !== token) return;
    userMotion.current = false;
    fixingEdge.current = false;
  }, []);

  const settle = useCallback((token = motionToken.current) => {
    offset.stopAnimation((currentOffset: number) => {
      if (motionToken.current !== token) return;
      const next = offsetToAge(currentOffset);
      emitUserAge(next);
      Animated.spring(offset, {
        toValue: ageToOffset(next),
        useNativeDriver: false,
        speed: 16,
        bounciness: 4,
      }).start(() => finishUserMotion(token));
    });
  }, [emitUserAge, finishUserMotion, offset]);

  useEffect(() => {
    const listener = offset.addListener(({ value: currentOffset }) => {
      if (!userMotion.current) return;
      const minimumOffset = ageToOffset(AGE_MAX);
      if (!fixingEdge.current && (currentOffset > AGE_STEP_PX || currentOffset < minimumOffset - AGE_STEP_PX)) {
        fixingEdge.current = true;
        const edge = currentOffset > 0 ? AGE_MIN : AGE_MAX;
        const token = motionToken.current;
        offset.stopAnimation(() => {
          if (motionToken.current !== token) return;
          emitUserAge(edge);
          Animated.spring(offset, {
            toValue: ageToOffset(edge),
            useNativeDriver: false,
            speed: 12,
            bounciness: 8,
          }).start(() => finishUserMotion(token));
        });
        return;
      }
      emitUserAge(offsetToAge(currentOffset));
    });
    return () => offset.removeListener(listener);
  }, [emitUserAge, finishUserMotion, offset]);

  const release = useCallback((velocity: number) => {
    const token = motionToken.current;
    if (Math.abs(velocity) < 0.08) {
      settle(token);
      return;
    }
    Animated.decay(offset, {
      velocity,
      deceleration: FRICTION,
      useNativeDriver: false,
    }).start(({ finished }) => {
      if (finished && motionToken.current === token) settle(token);
    });
  }, [offset, settle]);

  const pan = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: (_event, gesture) => Math.abs(gesture.dx) > 2,
    onPanResponderTerminationRequest: () => false,
    onPanResponderGrant: () => {
      motionToken.current += 1;
      userMotion.current = true;
      fixingEdge.current = false;
      offset.stopAnimation((currentOffset: number) => { gestureStart.current = currentOffset; });
      drag.current?.(true);
    },
    onPanResponderMove: (_event, gesture) => {
      offset.setValue(gestureStart.current + gesture.dx);
    },
    onPanResponderRelease: (_event, gesture) => {
      drag.current?.(false);
      release(gesture.vx);
    },
    onPanResponderTerminate: () => {
      drag.current?.(false);
      settle();
    },
  }), [offset, release, settle]);

  const adjust = useCallback((delta: number) => {
    const next = clampAge(shownAge.current + delta);
    if (next === shownAge.current) return;
    motionToken.current += 1;
    userMotion.current = false;
    fixingEdge.current = false;
    emitUserAge(next);
    offset.stopAnimation();
    Animated.spring(offset, {
      toValue: ageToOffset(next),
      useNativeDriver: false,
      speed: 16,
      bounciness: 4,
    }).start();
  }, [emitUserAge, offset]);

  const onAccessibilityAction = useCallback((event: AccessibilityActionEvent) => {
    if (event.nativeEvent.actionName === 'increment') adjust(1);
    if (event.nativeEvent.actionName === 'decrement') adjust(-1);
  }, [adjust]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      appActive.current = state === 'active';
      if (appActive.current) return;
      motionToken.current += 1;
      userMotion.current = false;
      fixingEdge.current = false;
      drag.current?.(false);
      offset.stopAnimation((currentOffset: number) => {
        offset.setValue(snapAgeOffset(currentOffset));
      });
    });
    return () => subscription.remove();
  }, [offset]);

  /** External hydration or profile synchronization moves the ruler silently. */
  useEffect(() => {
    const next = clampAge(value);
    if (next === shownAge.current) return;
    motionToken.current += 1;
    userMotion.current = false;
    fixingEdge.current = false;
    shownAge.current = next;
    offset.stopAnimation();
    Animated.spring(offset, {
      toValue: ageToOffset(next),
      useNativeDriver: false,
      speed: 14,
      bounciness: 6,
    }).start();
  }, [offset, value]);

  const scale = valuePulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.1] });

  return (
    <View
      accessible
      accessibilityRole="adjustable"
      accessibilityLabel={copy.label}
      accessibilityValue={{ min: AGE_MIN, max: AGE_MAX, now: selected, text: copy.value }}
      accessibilityHint={copy.hint}
      accessibilityActions={[
        { name: 'increment', label: copy.increment },
        { name: 'decrement', label: copy.decrement },
      ]}
      onAccessibilityAction={onAccessibilityAction}
      testID="age-ruler"
      style={styles.root}
      {...pan.panHandlers}
    >
      <Animated.Text
        accessible={false}
        allowFontScaling
        maxFontSizeMultiplier={1.6}
        style={[styles.value, { transform: [{ scale }] }]}
      >
        {selected}
      </Animated.Text>

      <View accessible={false} style={[styles.band, { width: bandWidth }]}>
        <Svg accessible={false} width={bandWidth} height={BAND_HEIGHT}>
          <Defs>
            <LinearGradient id="age-ruler-edges" x1="0" y1="0" x2="1" y2="0">
              <Stop offset="0" stopColor={color.card} stopOpacity="0" />
              <Stop offset="0.22" stopColor={color.card} stopOpacity="1" />
              <Stop offset="0.78" stopColor={color.card} stopOpacity="1" />
              <Stop offset="1" stopColor={color.card} stopOpacity="0" />
            </LinearGradient>
            <Mask id="age-ruler-fade">
              <Rect x={0} y={0} width={bandWidth} height={BAND_HEIGHT} fill="url(#age-ruler-edges)" />
            </Mask>
          </Defs>

          <G mask="url(#age-ruler-fade)">
            <AnimatedGroup x={offset}>
              {VALUES.map((age) => {
                const long = age % 5 === 0;
                const x = half + (age - AGE_MIN) * AGE_STEP_PX;
                return (
                  <Line
                    key={age}
                    x1={x}
                    y1={8}
                    x2={x}
                    y2={8 + (long ? LONG_TICK_HEIGHT : TICK_HEIGHT)}
                    stroke={long ? color.neutral400 : color.neutral300}
                    strokeWidth={long ? 1.5 : 1}
                    strokeLinecap="round"
                  />
                );
              })}
            </AnimatedGroup>
          </G>

          <Line
            x1={half}
            y1={2}
            x2={half}
            y2={CENTER_HEIGHT}
            stroke={color.primary}
            strokeWidth={3}
            strokeLinecap="round"
          />
        </Svg>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { alignItems: 'center', minHeight: 104 },
  value: {
    fontFamily: font.textSemibold,
    fontSize: 30,
    /** Fixed metrics do not scale with fontSize on native, so reserve the full 1.6x cap. */
    lineHeight: 52,
    color: color.fg,
    marginBottom: 8,
  } as any,
  band: {
    height: BAND_HEIGHT,
    marginHorizontal: -20,
    alignSelf: 'center',
  },
});
