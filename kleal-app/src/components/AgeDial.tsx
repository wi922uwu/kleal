/**
 * Возраст выбирают ЛИНЕЙКОЙ, а не кольцом — кадр A.05 борда (4555:123063).
 *
 * ЗДЕСЬ БЫЛО КОЛЬЦО, И ЭТО БЫЛА ЧЕСТНО ПОМЕЧЕННАЯ ДОГАДКА. В прошлой версии стояла приписка:
 * «какому диапазону соответствует такая дуга, из статичного кадра не выводится… это место надо
 * сверить с бордом, когда вернётся квота Figma». Доступ к борду вернулся (REST вместо Dev Mode),
 * и на кадре не кольцо: горизонтальная линейка во всю ширину экрана, двадцать пять делений, у
 * центрального свой цвет и высота, число крупно над ним. Догадка заменена на дизайн.
 *
 * ЧТО ВЗЯТО С КАДРА ДОСЛОВНО:
 *   — полоса делений во всю ширину, НЕ по полям содержимого: на кадре она уходит за оба края;
 *   — деление 32 точки высотой, центральное 48 и цветом действия;
 *   — число над центром, крупное и жирное;
 *   — растушёвка у обоих краёв (на кадре это два прямоугольника 132x35 поверх полосы).
 *
 * ПОЧЕМУ ВСТРОЕННЫЙ Animated И PanResponder. Так сделаны все живые жесты проекта; вторая система
 * анимации ради одного экрана значит держать обе. Лента едет нативным драйвером, а значение
 * пересчитывается в JS только при переходе через деление — то есть несколько раз за жест, а не
 * каждый кадр.
 *
 * ЗВУК И ОТКЛИК. На каждом новом значении — щелчок в палец и щелчок в динамик. Порог по времени
 * обязателен: при быстром ведении значение успевает смениться несколько раз за кадр, и без него
 * вместо щелчков вышел бы треск. Звук — assets/sounds/tick.wav.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, PanResponder, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';
import { createAudioPlayer, type AudioPlayer } from 'expo-audio';
import { color, font } from '../theme';
import { hTap } from '../haptics';

const MIN = 18;
const MAX = 80;
/** Шаг между делениями. На кадре 25 делений укладываются в 440 точек ширины. */
const STEP = 18;
const TICK_H = 32;
const CENTER_H = 48;
/** Ширина растушёвки у края — с кадра (прямоугольник 132 поверх полосы). */
const FADE = 132;
/** Реже этого щёлкать нельзя: на быстром ведении вышел бы треск вместо щелчков. */
const CLICK_MS = 45;

const VALUES = Array.from({ length: MAX - MIN + 1 }, (_, i) => MIN + i);

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

  /** Сдвиг ленты в точках. Ведёт нативный драйвер, значение считает JS. */
  const dx = useRef(new Animated.Value(0)).current;
  /** Значение на момент касания: от него отсчитывается сдвиг за жест. */
  const from = useRef(value);
  const shown = useRef(value);
  const lastClick = useRef(0);

  const change = useRef(onChange); change.current = onChange;
  const drag = useRef(onDragChange); drag.current = onDragChange;

  /*
    Игрок создаётся один раз и живёт со звуком внутри. Пересоздавать его на каждый щелчок значит
    заново открывать файл — на быстром ведении это заметно даже на слух.
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

  const click = () => {
    const now = Date.now();
    if (now - lastClick.current < CLICK_MS) return;
    lastClick.current = now;
    hTap();
    try {
      const p = player.current;
      if (p) { p.seekTo(0); p.play(); }
    } catch {}
  };

  const settle = (v: number) => {
    const c = Math.max(MIN, Math.min(MAX, v));
    if (c !== shown.current) {
      shown.current = c;
      click();
      change.current(c);
    }
    return c;
  };

  const pan = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dx) > 2,
    // Лента чата попросит жест себе, как только палец поедет вертикально. Отказываем.
    onPanResponderTerminationRequest: () => false,
    onPanResponderGrant: () => {
      from.current = shown.current;
      drag.current?.(true);
    },
    onPanResponderMove: (_e, g) => {
      // Влево — старше: линейка едет под пальцем, как настоящая лента.
      const v = settle(Math.round(from.current - g.dx / STEP));
      dx.setValue(-(v - MIN) * STEP);
    },
    onPanResponderRelease: () => drag.current?.(false),
    onPanResponderTerminate: () => drag.current?.(false),
  }), []);

  /** Значение поменяли снаружи — линейка обязана доехать сама. */
  useEffect(() => {
    shown.current = value;
    Animated.timing(dx, {
      toValue: -(value - MIN) * STEP,
      duration: 160,
      useNativeDriver: true,
    }).start();
  }, [value]);

  return (
    <View style={s.wrap}>
      <Text style={s.value}>{value}</Text>

      <View style={[s.band, { width }]} {...pan.panHandlers}>
        <Animated.View
          style={[s.rail, { left: half, transform: [{ translateX: dx }] }]}
          pointerEvents="none"
        >
          {VALUES.map((v) => (
            <View key={v} style={[s.tick, { left: (v - MIN) * STEP }]} />
          ))}
        </Animated.View>

        {/* Центральное деление стоит НА МЕСТЕ, а лента едет под ним — так же, как у настоящей линейки. */}
        <View style={[s.center, { left: half - 1 }]} pointerEvents="none" />

        {/*
          Растушёвка у краёв. На кадре это два прямоугольника поверх полосы: деления не обрываются
          ножом, а тают. Рисуем SVG — линейного градиента в стилях RN нет, а react-native-svg стоит.
        */}
        <Svg width={width} height={CENTER_H} style={StyleSheet.absoluteFill} pointerEvents="none">
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
          <Rect x={0} y={0} width={FADE} height={CENTER_H} fill="url(#fadeL)" />
          <Rect x={width - FADE} y={0} width={FADE} height={CENTER_H} fill="url(#fadeR)" />
        </Svg>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { alignItems: 'center' },
  /** Число над центром — на кадре крупное и жирное, той же гарнитурой, что заголовки. */
  value: {
    fontFamily: font.textSemibold,
    fontSize: 26,
    lineHeight: 32,
    color: color.fg,
    marginBottom: 6,
  } as any,
  /**
   * Полоса уходит за края содержимого — так на кадре. Отрицательные поля вытаскивают её из
   * колонки с отступами: иначе линейка обрывалась бы там, где кончается текст, и читалась бы
   * коробкой, а не лентой.
   */
  band: {
    height: CENTER_H,
    marginHorizontal: -20,
    alignSelf: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  rail: { position: 'absolute', top: (CENTER_H - TICK_H) / 2, height: TICK_H },
  tick: {
    position: 'absolute',
    width: 1,
    height: TICK_H,
    backgroundColor: color.line,
  },
  center: {
    position: 'absolute',
    width: 2,
    height: CENTER_H,
    borderRadius: 1,
    backgroundColor: color.primary,
  },
});
