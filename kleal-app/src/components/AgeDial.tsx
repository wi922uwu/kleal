/**
 * Возраст выбирают ЛИНЕЙКОЙ — кадр A.05 борда (4555:123063).
 *
 * ЗДЕСЬ БЫЛО КОЛЬЦО, И ЭТО БЫЛА ЧЕСТНО ПОМЕЧЕННАЯ ДОГАДКА: в прошлой версии стояла приписка, что
 * дугу из статичного кадра не вывести и место надо сверить с бордом. Сверили — там линейка.
 *
 * ЛЕНТА ЕДЕТ ЗА ПАЛЬЦЕМ, А НЕ ПРЫГАЕТ ПО ДЕЛЕНИЯМ. Первая версия считала сдвиг от ОКРУГЛЁННОГО
 * значения, поэтому лента дёргалась шагами по восемнадцать точек и выглядела неподвижной. Теперь
 * сдвиг берётся прямо из жеста, а значение — из сдвига.
 *
 * ВЫБЕГ НАСТОЯЩИЙ, А НЕ ПЕРЕНОС НА НЕСКОЛЬКО ДЕЛЕНИЙ. Сначала на отпускании лента просто прыгала
 * пружиной на пять делений вперёд — это читалось как рывок, а не как раскрутка. Теперь бросок
 * катится с трением (`Animated.decay`), по дороге щёлкая на каждом делении, сам замедляется и в
 * конце мягко доезжает до ближайшего. Долетев до края диапазона, лента упирается и отскакивает
 * обратно, а не застревает за пределом.
 *
 * ДРАЙВЕР У СДВИГА — JS, И ЭТО НАМЕРЕННО. Значение нужно знать НА КАЖДОМ КАДРЕ: по нему щёлкает
 * звук и меняется число. Нативный драйвер отдаёт его в JS с задержкой и пачками, отчего щелчки
 * отстают от картинки. Здесь это ничего не стоит: едет ОДИН вид, а не сотня.
 *
 * ДЕЛЕНИЯ ВИДНО. Были цветом волосяной линии на светлом фоне — то есть почти никак. Теперь как у
 * настоящей линейки: обычные деления серо-синие, каждое пятое выше и темнее, каждое десятое
 * подписано числом. Глазу есть за что зацепиться, и видно, куда едешь.
 *
 * ЗВУК И ОТКЛИК на каждом новом значении — щелчок в палец и tick.wav в динамик. Порог по времени
 * обязателен: на быстром ведении значение меняется несколько раз за кадр, и без него вместо
 * щелчков выходит треск.
 *
 * ВСТРОЕННЫЙ Animated И PanResponder — как во всех живых жестах проекта; вторая система анимации
 * ради одного экрана значит держать обе.
 */
import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, PanResponder, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';
import { createAudioPlayer, type AudioPlayer } from 'expo-audio';
import { color, font } from '../theme';
import { hTap } from '../haptics';

const MIN = 18;
const MAX = 80;
/** Шаг между делениями: на кадре 25 делений укладываются в 440 точек ширины. */
const STEP = 18;
const TICK_H = 26;
const BIG_H = 36;
const CENTER_H = 52;
const BAND_H = 78;               // деления + подписи под ними
/** Ширина растушёвки у края — с кадра (прямоугольник 132 поверх полосы). */
const FADE = 120;
/** Реже этого щёлкать нельзя: иначе на быстром ведении треск вместо щелчков. */
const CLICK_MS = 45;
/**
 * Трение выбега. Меньше — короче катится. У RN по умолчанию 0.998, и с ним линейка едет секунды
 * три: для выбора возраста это долго, человек ждёт, пока она успокоится.
 */
const FRICTION = 0.992;

const VALUES = Array.from({ length: MAX - MIN + 1 }, (_, i) => MIN + i);
const clamp = (v: number) => Math.max(MIN, Math.min(MAX, v));
const offsetOf = (v: number) => -(v - MIN) * STEP;

export function AgeDial({
  value, onChange, onDragChange,
}: {
  value: number;
  onChange: (v: number) => void;
  /** Пока ведут линейку, лента чата под ней должна стоять — иначе едут обе. */
  onDragChange?: (dragging: boolean) => void;
}) {
  const { width } = useWindowDimensions();
  const half = width / 2;

  /** Сдвиг ленты в точках. Непрерывный: идёт прямо из жеста. */
  const dx = useRef(new Animated.Value(offsetOf(value))).current;
  /** Пульс числа в момент смены — короткий, чтобы было видно, что значение поменялось. */
  const pop = useRef(new Animated.Value(0)).current;

  const from = useRef(offsetOf(value));
  const shown = useRef(value);
  const lastClick = useRef(0);
  /** Идёт ли сейчас возврат от края. Без этого слушатель и stopAnimation зовут друг друга. */
  const fixing = useRef(false);
  const change = useRef(onChange); change.current = onChange;
  const drag = useRef(onDragChange); drag.current = onDragChange;

  /*
    Игрок создаётся один раз и живёт со звуком внутри: пересоздавать его на каждый щелчок значит
    заново открывать файл, и на быстром ведении это слышно.
  */
  const player = useRef<AudioPlayer | null>(null);
  useEffect(() => {
    try {
      player.current = createAudioPlayer(require('../../assets/sounds/tick.wav'));
    } catch {
      player.current = null;               // без звука линейка обязана работать
    }
    return () => { try { player.current?.remove(); } catch {} };
  }, []);

  /*
    Значение считается ИЗ СДВИГА на каждом кадре — и во время ведения, и во время выбега. Поэтому
    щелчки идут ровно тогда, когда деление проходит под меткой, а не когда JS об этом узнал.
  */
  useEffect(() => {
    const id = dx.addListener(({ value: cur }) => {
      const lim = offsetOf(MAX);
      /*
        ЗАЩЁЛКА ОТ ПОВТОРНОГО ВХОДА, И БЕЗ НЕЁ ЭКРАН ПАДАЛ. Слушатель, поймав выход за край, звал
        stopAnimation; тот сам двигает значение и снова будит слушателя, который всё ещё видит
        выход за край — и так до переполнения стека. Ловится это только на телефоне: «Maximum call
        stack size exceeded», а стек — чередование addListener и stopAnimation.

        Пока возврат идёт, второй раз его не запускаем. Значение при этом продолжает считаться:
        число и щелчки не должны замирать на время отскока.
      */
      if (!fixing.current && (cur > STEP || cur < lim - STEP)) {
        fixing.current = true;
        const edge = cur > 0 ? MIN : MAX;
        dx.stopAnimation(() => {
          tick(edge);
          Animated.spring(dx, { toValue: offsetOf(edge), useNativeDriver: false, speed: 12, bounciness: 8 })
            .start(() => { fixing.current = false; });
        });
        return;
      }
      tick(clamp(Math.round(-cur / STEP) + MIN));
    });
    return () => dx.removeListener(id);
  }, []);

  const tick = (v: number) => {
    if (v === shown.current) return;
    shown.current = v;
    change.current(v);
    Animated.sequence([
      Animated.timing(pop, { toValue: 1, duration: 70, useNativeDriver: true }),
      Animated.timing(pop, { toValue: 0, duration: 130, useNativeDriver: true }),
    ]).start();
    const now = Date.now();
    if (now - lastClick.current < CLICK_MS) return;
    lastClick.current = now;
    hTap();
    try {
      const p = player.current;
      if (p) { p.seekTo(0); p.play(); }
    } catch {}
  };

  /** Доехать до ближайшего деления — тем, что осталось после выбега. */
  const settle = () => {
    dx.stopAnimation((cur: number) => {
      const v = clamp(Math.round(-cur / STEP) + MIN);
      tick(v);
      Animated.spring(dx, {
        toValue: offsetOf(v),
        useNativeDriver: false,
        speed: 16,
        bounciness: 4,
      }).start();
    });
  };

  /**
   * Отпустили — лента катится дальше сама и замедляется трением. Слабый жест не бросок: катить
   * от него нечего, доводим сразу, иначе линейка ползёт после каждого касания.
   */
  const release = (vx: number) => {
    if (Math.abs(vx) < 0.08) { settle(); return; }
    Animated.decay(dx, { velocity: vx, deceleration: FRICTION, useNativeDriver: false })
      .start(({ finished }) => { if (finished) settle(); });
  };

  const pan = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dx) > 2,
    // Лента чата попросит жест себе, как только палец поедет вертикально. Отказываем.
    onPanResponderTerminationRequest: () => false,
    onPanResponderGrant: () => {
      fixing.current = false;              // новый жест отменяет незаконченный отскок
      dx.stopAnimation((cur: number) => { from.current = cur; });
      drag.current?.(true);
    },
    onPanResponderMove: (_e, g) => {
      // Влево — старше: лента идёт под пальцем один в один, без округления.
      // Предел и пересчёт значения держит слушатель выше — здесь только сдвиг.
      dx.setValue(from.current + g.dx);
    },
    onPanResponderRelease: (_e, g) => {
      drag.current?.(false);
      release(g.vx);
    },
    onPanResponderTerminate: () => {
      drag.current?.(false);
      settle();
    },
  }), []);

  /** Значение поменяли снаружи — линейка обязана доехать сама. */
  useEffect(() => {
    if (value === shown.current) return;
    shown.current = value;
    Animated.spring(dx, { toValue: offsetOf(value), useNativeDriver: false, speed: 14, bounciness: 6 }).start();
  }, [value]);

  const scale = pop.interpolate({ inputRange: [0, 1], outputRange: [1, 1.12] });

  return (
    <View style={s.wrap}>
      <Animated.Text style={[s.value, { transform: [{ scale }] }]}>{value}</Animated.Text>

      <View style={[s.band, { width }]} {...pan.panHandlers}>
        <Animated.View
          style={[s.rail, { left: half, transform: [{ translateX: dx }] }]}
          pointerEvents="none"
        >
          {VALUES.map((v) => {
            const big = v % 5 === 0;
            const named = v % 10 === 0;
            return (
              <View key={v} style={[s.slot, { left: (v - MIN) * STEP - STEP / 2 }]}>
                <View style={[s.tick, big && s.tickBig, { height: big ? BIG_H : TICK_H }]} />
                {named ? <Text style={s.tickLabel}>{v}</Text> : null}
              </View>
            );
          })}
        </Animated.View>

        {/* Центральное деление стоит НА МЕСТЕ, лента едет под ним — как у настоящей линейки. */}
        <View style={[s.center, { left: half - 1.5 }]} pointerEvents="none" />

        {/*
          Растушёвка у краёв: на кадре деления не обрываются ножом, а тают. Рисуем SVG — линейного
          градиента в стилях RN нет, а react-native-svg в проекте стоит.
        */}
        <Svg width={width} height={BAND_H} style={StyleSheet.absoluteFill} pointerEvents="none">
          <Defs>
            <LinearGradient id="fadeL" x1="0" y1="0" x2="1" y2="0">
              <Stop offset="0" stopColor={color.ambientBase} stopOpacity="1" />
              <Stop offset="1" stopColor={color.ambientBase} stopOpacity="0" />
            </LinearGradient>
            <LinearGradient id="fadeR" x1="0" y1="0" x2="1" y2="0">
              <Stop offset="0" stopColor={color.ambientBase} stopOpacity="0" />
              <Stop offset="1" stopColor={color.ambientBase} stopOpacity="1" />
            </LinearGradient>
          </Defs>
          <Rect x={0} y={0} width={FADE} height={BAND_H} fill="url(#fadeL)" />
          <Rect x={width - FADE} y={0} width={FADE} height={BAND_H} fill="url(#fadeR)" />
        </Svg>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { alignItems: 'center' },
  /** Число над центром — крупное, той же гарнитурой, что заголовки. */
  value: {
    fontFamily: font.textSemibold,
    fontSize: 30,
    lineHeight: 36,
    color: color.fg,
    marginBottom: 4,
  } as any,
  /**
   * Полоса уходит за края содержимого — так на кадре. Отрицательные поля вытаскивают её из колонки
   * с отступами: иначе линейка обрывалась бы там, где кончается текст, и читалась коробкой.
   */
  band: {
    height: BAND_H,
    marginHorizontal: -20,
    alignSelf: 'center',
    overflow: 'hidden',
  },
  rail: { position: 'absolute', top: 0, height: BAND_H },
  slot: { position: 'absolute', top: 0, width: STEP, alignItems: 'center' },
  tick: { width: 1, borderRadius: 1, backgroundColor: color.neutral300 },
  /** Каждое пятое — выше и темнее: по ним и читают, где находишься. */
  tickBig: { width: 1.5, backgroundColor: color.neutral400 },
  tickLabel: {
    marginTop: 4,
    fontFamily: font.text,
    fontSize: 10,
    lineHeight: 12,
    color: color.muted,
  } as any,
  center: {
    position: 'absolute',
    top: 0,
    width: 3,
    height: CENTER_H,
    borderRadius: 1.5,
    backgroundColor: color.primary,
  },
});
