/**
 * Карта интересов: одно полотно, живое поле и лупа под пальцем.
 *
 * УСТРОЙСТВО ВЗЯТО У ДВУХ РАБОТ, И ОБЕ ВЫБРАНЫ ЗА ОДНО И ТО ЖЕ РЕШЕНИЕ.
 *
 *  — «Gates Foundation bubbles» Джима Валландингема (vlandham/gates_bubbles). Там пузыри
 *    притягиваются к центру своей группы и расталкиваются силой, пропорциональной ПЛОЩАДИ
 *    (`charge = -r²/8`), а движение гасится (`damper 0.1`, `friction 0.9`). Отсюда у нас
 *    раскладка кустов — она посчитана заранее в `mindmap.ts`, потому что поле не меняется и
 *    гонять симуляцию в каждом кадре незачем.
 *
 *  — «JS Interactive Canvas Bubbles» (codepen aashish2058/MWydyoe). Там нет ни одного объекта на
 *    пузырь: всё поле рисуется В ОДИН ХОЛСТ, а радиус каждого пузыря в каждом кадре ДОГОНЯЕТ свою
 *    цель — близко к курсору цель больше, далеко меньше. Отсюда у нас всё остальное.
 *
 * ПОЧЕМУ ЭТО ВАЖНО ИМЕННО ЗДЕСЬ. Прошлая версия держала по отдельному `Animated.View` на пузырь,
 * и каждому на каждом кадре меняла сдвиг по двум осям и масштаб — под четыреста нативных свойств
 * в кадре. Телефон это не тянул: поток был занят настолько, что не успевал даже разогнать
 * собственный переключатель анимации. Теперь на всё поле ОДИН вид — `<Svg>`, — а девяносто восемь
 * кружков внутри него получают новые `cx/cy/r` напрямую через `setNativeProps`, минуя React.
 * Ни перерисовки дерева, ни `Animated`-графа, ни состояния во время жеста.
 *
 * ЧТО ДЕЛАЕТ ЛУПА. Под пальцем пузырь вырастает вдвое и подтягивается к нему на треть расстояния;
 * дальше края зоны — ничего. Значения не подставляются рывком, а сглаживаются по кадрам (как
 * радиусы в той работе с холстом), поэтому поле «перетекает» к пальцу, а не прыгает за ним.
 *
 * ВЫБОР — НА ОТПУСКАНИИ. Прижал, повёл, увидел имя, отпустил — записалось. Отпустил над пустым
 * местом — не записалось ничего, и это же способ передумать.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { PanResponder, StyleSheet, Text, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { buildMap, ROOT_TONE, type Bubble } from '../mindmap';
import { color, deckTone, font } from '../theme';
import { useLang } from '../i18n';

/** Во сколько раз вырастает пузырь ровно под пальцем. */
const PEAK = 2;
/** Радиус действия лупы. */
const REACH = 78;
/** Какую долю пути до пальца проходит пузырь в самой сильной точке. */
const PULL = 0.3;
/** Насколько кадр приближает значение к цели. Меньше — плавнее и ленивее. */
const EASE = 0.22;
/** Ниже этого поле считается пришедшим в покой, и цикл кадров останавливается. */
const CALM = 0.35;
/** Насколько палец может сползти, и это всё ещё тап. */
const TAP_SLOP = 6;
/** Запас при попадании — по видимому размеру. */
const TAP_SLACK = 8;

/** Доля близости: 1 под пальцем, 0 за краем зоны. Та же ломаная, что и была. */
function near(v: number): number {
  const a = Math.min(Math.abs(v), REACH);
  const half = REACH / 2;
  return a <= half ? 1 - 0.55 * (a / half) : 0.45 * (1 - (a - half) / half);
}

type Node = {
  b: Bubble;
  /** Дом — место в покое, в пикселях. */
  hx: number;
  hy: number;
  hr: number;
  /** Где и какого размера СЕЙЧАС. */
  x: number;
  y: number;
  r: number;
};

export function MindMap({ width, height, selected, onToggle, onDrag }: {
  width: number;
  height: number;
  selected: string[];
  onToggle: (key: string) => void;
  /** Остановить ленту чата на время жеста: иначе она едет под пальцем вместе с лупой. */
  onDrag?: (dragging: boolean) => void;
}) {
  // Язык в зависимостях обязателен: подписи собираются внутри `buildMap` через `T()`.
  const lang = useLang();
  const bubbles = useMemo(() => buildMap(width, height), [width, height, lang]);

  /** Состояние поля живёт в ref, а не в React: во время жеста перерисовки быть не должно. */
  const nodes = useRef<Node[]>([]);
  const circles = useRef<any[]>([]);
  useMemo(() => {
    nodes.current = bubbles.map((b) => {
      const hx = b.x * width;
      const hy = b.y * height;
      const hr = b.size / 2;
      return { b, hx, hy, hr, x: hx, y: hy, r: hr };
    });
    circles.current = [];
  }, [bubbles, width, height]);

  /** Куда указывает палец. -1 значит «пальца нет», и поле возвращается домой. */
  const finger = useRef({ x: -1, y: -1, on: false });
  const frame = useRef<number | null>(null);
  /** Имя под пальцем. Единственное, что идёт через состояние, — и меняется оно редко. */
  const [hot, setHot] = useState<Node | null>(null);
  const hotKey = useRef<string>('');

  /*
    ОДИН ЦИКЛ КАДРОВ НА ВСЁ ПОЛЕ.

    В каждом кадре у каждого пузыря считается цель — размер и место — и текущее значение делает
    к ней один шаг. Это ровно приём той работы с холстом: там радиус увеличивался на единицу за
    кадр, пока курсор рядом, и уменьшался обратно, когда он ушёл. Шаг долей, а не единицей, чтобы
    скорость не зависела от размера пузыря.

    Цикл САМ ОСТАНАВЛИВАЕТСЯ, когда двигаться стало некуда: поле в покое не тратит ни кадра.
  */
  const tick = () => {
    const f = finger.current;
    let moving = 0;
    let best: Node | null = null;
    let bestBell = 0.62;                       // ниже этого имя не показываем: рано
    for (let i = 0; i < nodes.current.length; i++) {
      const n = nodes.current[i];
      let bell = 0;
      if (f.on) {
        bell = near(f.x - n.hx) * near(f.y - n.hy);
        if (bell > bestBell) { bestBell = bell; best = n; }
      }
      const tr = n.hr * (1 + bell * (PEAK - 1));
      const tx = n.hx + (f.on ? (f.x - n.hx) * bell * PULL : 0);
      const ty = n.hy + (f.on ? (f.y - n.hy) * bell * PULL : 0);
      const dr = tr - n.r;
      const dx = tx - n.x;
      const dy = ty - n.y;
      if (Math.abs(dr) < 0.05 && Math.abs(dx) < 0.05 && Math.abs(dy) < 0.05) continue;
      n.r += dr * EASE;
      n.x += dx * EASE;
      n.y += dy * EASE;
      moving += Math.abs(dr) + Math.abs(dx) + Math.abs(dy);
      circles.current[i]?.setNativeProps({ cx: n.x, cy: n.y, r: n.r });
    }
    const key = best ? best.b.key : '';
    if (key !== hotKey.current) { hotKey.current = key; setHot(best); }
    frame.current = moving > CALM || f.on ? requestAnimationFrame(tick) : null;
  };
  const wake = () => { if (frame.current == null) frame.current = requestAnimationFrame(tick); };
  useEffect(() => () => { if (frame.current != null) cancelAnimationFrame(frame.current); }, []);

  /** Что под пальцем — по ВИДИМОМУ размеру и месту, а не по покою. */
  const hit = useRef<(x: number, y: number) => string | null>(() => null);
  hit.current = (x, y) => {
    let key: string | null = null;
    let bestD = Infinity;
    for (const n of nodes.current) {
      const dx = x - n.x;
      const dy = y - n.y;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d <= n.r + TAP_SLACK && d < bestD) { bestD = d; key = n.b.key; }
    }
    return key;
  };
  const from = useRef({ x: 0, y: 0 });
  const toggle = useRef(onToggle); toggle.current = onToggle;
  const drag = useRef(onDrag); drag.current = onDrag;

  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      // Лента чата попросит жест себе, как только палец поедет вертикально. Отказываем.
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: (e) => {
        const { locationX: x, locationY: y } = e.nativeEvent;
        from.current = { x, y };
        finger.current = { x, y, on: true };
        drag.current?.(true);
        wake();
      },
      onPanResponderMove: (e) => {
        const { locationX: x, locationY: y } = e.nativeEvent;
        finger.current = { x, y, on: true };
        wake();
      },
      onPanResponderRelease: (e) => {
        const k = hit.current(e.nativeEvent.locationX, e.nativeEvent.locationY);
        if (k) toggle.current(k);
        finger.current = { x: -1, y: -1, on: false };
        drag.current?.(false);
        wake();
      },
      onPanResponderTerminate: () => {
        finger.current = { x: -1, y: -1, on: false };
        drag.current?.(false);
        wake();
      },
    })
  ).current;

  return (
    <View style={[s.field, { width, height }]} {...pan.panHandlers}>
      {/*
        ВСЁ ПОЛЕ — ОДИН ВИД. Кружки внутри получают новые координаты напрямую, без участия React:
        девяносто восемь `setNativeProps` вместо девяноста восьми перерисованных компонентов.
      */}
      <Svg width={width} height={height}>
        {bubbles.map((b, i) => {
          const t = deckTone[ROOT_TONE[b.root] || 'slate'];
          const on = selected.includes(b.key);
          return (
            <Circle
              key={b.key}
              ref={(el: any) => { circles.current[i] = el; }}
              cx={b.x * width}
              cy={b.y * height}
              r={b.size / 2}
              fill={on ? color.primary : t.wash}
              stroke={on ? color.primary : t.halo}
              strokeWidth={b.kind === 'root' ? 1.5 : 1}
            />
          );
        })}
      </Svg>

      {/* Категории подписаны всегда — по ним и ведут палец. */}
      {bubbles.filter((b) => b.kind === 'root').map((b) => (
        <Text
          key={`r-${b.key}`}
          numberOfLines={1}
          style={[s.rootLabel, { left: b.x * width - 45, top: b.y * height + b.size / 2 + 4 }]}
        >
          {b.label}
        </Text>
      ))}

      {/*
        ИМЯ ПОД ПАЛЬЦЕМ — ОДНА ПЛАШКА НА ВСЁ ПОЛЕ, А НЕ ПО ОДНОЙ НА ПУЗЫРЬ.

        Раньше их было сто пятьдесят, у каждой своя прозрачность в общем графе. Показывается всё
        равно одна — та, что под пальцем; значит и держать надо одну. Встаёт она НАД точкой
        касания: палец закрывает ровно то, что увеличивает, и это лечится так же, как в iOS у
        выделения текста — нужное выносят выше пальца.
      */}
      {hot && hot.b.kind === 'leaf' ? (
        <View pointerEvents="none"
              style={[s.plate, { left: hot.hx - 48, top: hot.hy - hot.hr * PEAK - 22 }]}>
          <Text numberOfLines={1} style={s.plateText}>{hot.b.label}</Text>
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  field: { position: 'relative', alignSelf: 'center' },
  rootLabel: {
    position: 'absolute', width: 90, textAlign: 'center',
    fontFamily: font.textMedium, fontSize: 10, lineHeight: 13, color: color.fg,
  } as any,
  plate: {
    position: 'absolute', width: 96, height: 18, borderRadius: 9,
    backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center',
    paddingHorizontal: 6,
  },
  plateText: {
    fontFamily: font.textMedium, fontSize: 10, lineHeight: 12,
    color: color.onPrimary, textAlign: 'center',
  } as any,
});
