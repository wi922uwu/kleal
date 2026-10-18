/**
 * A.05 age ruler. The track moves continuously under one fixed coral selection line and settles
 * only on whole years. User-driven integer changes emit feedback; hydration and prop sync do not.
 *
 * ВСЁ ДВИЖЕНИЕ — НА НАТИВНОМ ПОТОКЕ (26.09, «лагает выбор возраста» с Android). Раньше каждое из 63
 * делений двигалось своим сдвигом и своей прозрачностью через JS-поток (`useNativeDriver: false`):
 * на каждый кадр жеста — 126 обновлений через мост, а на каждый новый год ещё и перерисовка всей
 * линейки с новыми выражениями анимации. Теперь деления стоят в одном слое, его сдвигает нативный
 * драйвер, слой собран один раз (useMemo), а число меняется без «подпрыгивания».
 */
import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Animated,
  AppState,
  Easing,
  PanResponder,
  StyleSheet,
  View,
  useWindowDimensions,
  type AccessibilityActionEvent,
} from 'react-native';
import Svg, { Line } from 'react-native-svg';
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

const EASE = Easing.out(Easing.cubic);

const VALUES = Array.from({ length: AGE_MAX - AGE_MIN + 1 }, (_, index) => AGE_MIN + index);
const TICK_HEIGHT = 23;
const LONG_TICK_HEIGHT = 34;
const CENTER_HEIGHT = 48;
const BAND_HEIGHT = 54;
const FRICTION = 0.992;
/** Насколько линейку можно оттянуть за край шкалы пальцем. */
const OVERSCROLL = 24;
/** Доводка до целого года — спокойное замедление без перелёта. */
const SETTLE_MS = 220;

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
  }, [playClick]);

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
      Animated.timing(offset, {
        toValue: ageToOffset(next),
        duration: SETTLE_MS,
        easing: EASE,
        useNativeDriver: true,
      }).start(() => finishUserMotion(token));
    });
  }, [emitUserAge, finishUserMotion, offset]);

  /*
    ГРАНИЦЫ — ДО АНИМАЦИИ, А НЕ ВО ВРЕМЯ (владелец, 27.09: «линейку можно умотать влево или вправо,
    она выйдет за границы»). Инерция идёт на нативном потоке, а слушатель позиции живёт в JS и
    узнаёт её с опозданием: сильный взмах успевал улететь за 18 или 80, прежде чем JS его ловил.
    Теперь конечная точка инерции считается заранее — той же формулой, что у Animated.decay
    (путь = v / (1 − трение)), прижимается к краям и к целому году, и линейка доезжает туда одной
    нативной анимацией с замедлением. За край ехать нечему. Слушатель только пишет число.
  */
  const lowest = ageToOffset(AGE_MAX);
  const highest = ageToOffset(AGE_MIN);
  useEffect(() => {
    const listener = offset.addListener(({ value: currentOffset }) => {
      if (!userMotion.current) return;
      emitUserAge(offsetToAge(Math.max(lowest, Math.min(highest, currentOffset))));
    });
    return () => offset.removeListener(listener);
  }, [emitUserAge, offset, lowest, highest]);

  const release = useCallback((velocity: number) => {
    const token = motionToken.current;
    offset.stopAnimation((from: number) => {
      if (motionToken.current !== token) return;
      const inside = Math.max(lowest, Math.min(highest, from));
      // Слабое отпускание внутри шкалы — просто доводка до ближайшего года.
      if (Math.abs(velocity) < 0.08 && inside === from) { settle(token); return; }
      const glide = Math.abs(velocity) < 0.08 ? 0 : velocity / (1 - FRICTION);
      const next = offsetToAge(Math.max(lowest, Math.min(highest, from + glide)));
      const to = ageToOffset(next);
      emitUserAge(next);
      Animated.timing(offset, {
        toValue: to,
        // Длина пути задаёт время: короткий доезд — быстро, через всю шкалу — до 0,9 с.
        duration: Math.max(SETTLE_MS, Math.min(900, 180 + Math.abs(to - from) * 0.9)),
        easing: EASE,
        useNativeDriver: true,
      }).start(() => finishUserMotion(token));
    });
  }, [emitUserAge, finishUserMotion, offset, settle, lowest, highest]);

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
      // За краем шкалы — «резинка»: треть хода пальца и не дальше OVERSCROLL, потом отпускание
      // возвращает к краю (release). Раньше протяжка уводила линейку за 18 и 80 без предела.
      const raw = gestureStart.current + gesture.dx;
      const over = raw > highest ? raw - highest : raw < lowest ? raw - lowest : 0;
      const band = Math.sign(over) * Math.min(OVERSCROLL, Math.abs(over) / 3);
      offset.setValue(over ? (over > 0 ? highest : lowest) + band : raw);
    },
    onPanResponderRelease: (_event, gesture) => {
      drag.current?.(false);
      release(gesture.vx);
    },
    onPanResponderTerminate: () => {
      drag.current?.(false);
      settle();
    },
  }), [offset, release, settle, lowest, highest]);

  const adjust = useCallback((delta: number) => {
    const next = clampAge(shownAge.current + delta);
    if (next === shownAge.current) return;
    motionToken.current += 1;
    userMotion.current = false;
    fixingEdge.current = false;
    emitUserAge(next);
    offset.stopAnimation();
    Animated.timing(offset, {
      toValue: ageToOffset(next),
      duration: SETTLE_MS,
      easing: EASE,
      useNativeDriver: true,
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
    Animated.timing(offset, {
      toValue: ageToOffset(next),
      duration: SETTLE_MS,
      easing: EASE,
      useNativeDriver: true,
    }).start();
  }, [offset, value]);

  /*
    ДЕЛЕНИЯ — ОДИН СЛОЙ, СОБРАННЫЙ ОДИН РАЗ. Слой едет целиком (один сдвиг вместо 63), у каждого
    деления остаётся только гашение к краям. От числа на экране слой не зависит, поэтому смена года
    его не перерисовывает.
  */
  const track = useMemo(() => (
    <Animated.View
      pointerEvents="none"
      importantForAccessibility="no-hide-descendants"
      style={[StyleSheet.absoluteFill, { transform: [{ translateX: offset }] }]}
    >
      {VALUES.map((age) => {
        const long = age % 5 === 0;
        const x = half + (age - AGE_MIN) * AGE_STEP_PX;
        const thickness = long ? 2 : 1.5;
        return (
          <Animated.View
            key={age}
            testID={`age-ruler-tick-${age}`}
            style={[
              styles.tick,
              {
                left: x - thickness / 2,
                width: thickness,
                height: long ? LONG_TICK_HEIGHT : TICK_HEIGHT,
                backgroundColor: long ? color.fg : color.muted,
                opacity: offset.interpolate({
                  inputRange: [-x, bandWidth * 0.22 - x, bandWidth * 0.78 - x, bandWidth - x],
                  outputRange: [0, 1, 1, 0],
                  extrapolate: 'clamp',
                }),
              },
            ]}
          />
        );
      })}
    </Animated.View>
  ), [offset, half, bandWidth]);

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
        style={styles.value}
      >
        {selected}
      </Animated.Text>

      <View accessible={false} style={[styles.band, { width: bandWidth }]}>
        {/* Native ticks avoid the Android SVG group/mask offscreen-compositing path. */}
        {track}
        <Svg accessible={false} pointerEvents="none" width={bandWidth} height={BAND_HEIGHT}>
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
  root: { alignItems: 'center', minHeight: 150 },
  /**
   * ВОЗРАСТ — КРУПНО И ЧИТАЕМО. В макете точечные цифры (LED-матрица, у нас был Doto); на телефоне
   * они не читались («дотинг нужно убрать»). Теперь TASA Orbiter — тот же шрифт, что у заголовков, —
   * с моноширинными цифрами: «29» и «30» одной ширины, число не качается, пока крутят линейку.
   */
  value: {
    fontFamily: font.display,
    fontSize: 88,
    lineHeight: 100,
    letterSpacing: -1.8,
    fontVariant: ['tabular-nums'],
    color: color.fg,
    marginBottom: 0,
  } as any,
  band: {
    height: BAND_HEIGHT,
    marginHorizontal: -20,
    alignSelf: 'center',
    overflow: 'hidden',
  },
  tick: { position: 'absolute', top: 8, borderRadius: 1 },
});
