/**
 * Ступенчатое колесо интересов — коралловый диск. Кадр A.08, замена сетке чипов.
 *
 * ВИДНО ОДНО КОЛЬЦО, И В НЁМ ВОСЕМЬ СЕКЦИЙ. Каждая — скруглённая коралловая пилюля с контурной
 * иконкой; та, что стоит под стрелкой, залита кораллом целиком. Подписей на кольце нет: как
 * называется выбранное, написано ПОД диском и меняется на лету.
 *
 * ПОЧЕМУ ВОСЕМЬ, А НЕ ТРИДЦАТЬ СЕМЬ. Широкое первое кольцо пробовали (2026-08-10): тридцать семь
 * секций дают сегмент в десять градусов, значок в нём — тринадцать пикселей, и ряд читается как
 * рябь. Подробности никуда не делись — их больше трёхсот, они раскрываются уровнями.
 *
 * КАК ХОДЯТ ВГЛУБЬ — ТРИ ПУТИ, И ВСЕ ВИДНЫЕ.
 *
 * Самая первая версия прятала это в жест «палец к центру, не отрывая». Жест не сработал ни разу:
 * скрытый, узкий по радиусу и ничем не обозначенный. Теперь наоборот:
 *
 *   1. нажать на сердцевину — она показывает выбранное, подписана «Уточнить» и дышит, пока есть
 *      куда углубляться;
 *   2. нажать на секцию, которая УЖЕ под стрелкой — «да, вот эта, дальше»;
 *   3. кнопка «Уточнить ›» под колесом.
 *
 * Нажатие на любую другую секцию подкручивает её к стрелке — промах никогда не делает ничего
 * неожиданного, он просто выбирает.
 *
 * ЧТО ДЕЛАЕТ ЭТО ПЛАВНЫМ.
 *
 *   — Поворот живёт в Animated.Value с нативным драйвером: во время жеста через мост не идёт
 *     ничего, кроме setValue, и React не перерисовывается вовсе.
 *   — ПОДМАГНИЧИВАНИЕ: палец тянет кольцо не один в один, а с лёгким притяжением к центру
 *     ближайшей секции. Диск чуть «липнет» к делениям — на ощупь это и отличает механизм от
 *     картинки, и заодно почти убирает промахи у границы.
 *   — Отпускание — не телепорт, а пружина, и бросок летит по инерции: угол проецируется вперёд по
 *     скорости пальца.
 *   — Смена уровня — «пролёт насквозь»: старое кольцо разъезжается и растворяется, новое
 *     раскрывается из глубины ему навстречу. Назад — то же самое задом наперёд.
 *   — Каждое деление отзывается тактильно и импульсом линзы.
 *
 * ИКОНКА ВСЕГДА СТОИТ ПРЯМО. Ставить её внутрь вращающегося <Svg> и доворачивать по радиусу
 * пробовали: под стрелкой верно, сбоку иконка лежит на боку, снизу — вверх ногами. Поэтому иконки
 * живут отдельными слоями поверх кольца, и каждая доворачивается на минус тот же угол. Обе
 * анимации — один Animated.Value с нативным драйвером, компенсация не стоит ничего.
 *
 * Жест забирается у ленты тем же набором, что в AgeDial (capture + запрет termination + блок
 * нативного ответчика + onDragChange наружу), координаты ТОЛЬКО относительные — см. там же, почему.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, Animated, Easing, Platform,
  PanResponder, GestureResponderEvent,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import Svg, { Path, Circle } from 'react-native-svg';
import { WHEEL_TREE, WheelNode, nodeLabel, WHEEL_COPY } from '../interests-wheel';
import { categoryIcon, iconNameFor } from './category-icons';
import { color, radius as rad, type } from '../theme';

const TAU = 360;
const MAX_DEPTH = 3;

/** Доли радиуса. Кольцо тонкое: толстая полоса превращает пилюлю в подкову. */
const RING: [number, number] = [0.72, 0.96];
const HUB = 0.44;
const TRACE = 0.055;
/** Насколько палец «липнет» к делениям. Больше — колесо ощущается вязким, меньше — эффекта нет. */
const MAGNET = 0.24;

const rad_ = (deg: number) => ((deg - 90) * Math.PI) / 180;
const px = (cx: number, r: number, deg: number) => cx + r * Math.cos(rad_(deg));
const py = (cy: number, r: number, deg: number) => cy + r * Math.sin(rad_(deg));
const mod = (a: number) => ((a % TAU) + TAU) % TAU;

/** Угол «сверху и по часовой», 0..360. Ноль — под стрелкой. */
function topAngle(dx: number, dy: number) {
  let a = (Math.atan2(dy, dx) * 180) / Math.PI + 90;
  if (a < 0) a += TAU;
  return a;
}

/** Дуга по средней линии кольца — рисуется толстым штрихом с круглыми концами, отсюда пилюля. */
function arc(cx: number, cy: number, r: number, a0: number, a1: number) {
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M ${px(cx, r, a0)} ${py(cy, r, a0)} A ${r} ${r} 0 ${large} 1 ${px(cx, r, a1)} ${py(cy, r, a1)}`;
}

const idxAtTop = (rot: number, n: number) => Math.floor(mod(-rot) / (TAU / n)) % n;

/** Ближайший к `from` угол, ставящий секцию i под стрелку. */
function snapTarget(from: number, i: number, n: number) {
  const seg = TAU / n;
  const base = -(i * seg + seg / 2);
  const diff = mod(from - base + 180) - 180;
  return from - diff;
}

const canBuzz = Platform.OS !== 'web';
const tick = () => { if (canBuzz) Haptics.selectionAsync().catch(() => {}); };
const thud = () => {
  if (canBuzz) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
};

export function CipherWheel({
  size = 320,
  onAdd,
  onDragChange,
}: {
  size?: number;
  /** «Добавить»: ключи выбранной цепочки (родители + лист) и её подписи. */
  onAdd: (keys: string[], labels: string[]) => void;
  onDragChange?: (dragging: boolean) => void;
}) {
  const R = size / 2;
  const cx = R;
  const cy = R;
  const r0 = RING[0] * R;
  const r1 = RING[1] * R;
  const rm = (r0 + r1) / 2;
  const band = r1 - r0;
  const hubR = HUB * R;
  /** Круглый конец штриха съедает полбанда дуги с каждой стороны — отсюда и зазор между пилюлями. */
  const capDeg = ((band / 2 / rm) * 180) / Math.PI;

  const [path, setPath] = useState<number[]>([]);
  const [sel, setSel] = useState(0);

  const { chain, items } = useMemo(() => {
    const chain: WheelNode[] = [];
    let list: WheelNode[] = WHEEL_TREE;
    for (const i of path) {
      const node = list[i];
      if (!node) break;
      chain.push(node);
      list = node.kids || [];
    }
    return { chain, items: list };
  }, [path]);

  const n = items.length;
  const seg = TAU / Math.max(1, n);
  const depth = path.length;
  const current = items[sel];
  const drillable = !!current?.kids?.length && depth < MAX_DEPTH;
  /** Иконка ветки: на первом уровне — своя у каждой секции, глубже — та, из которой пришли. */
  const branchIcon = iconNameFor(current?.key || '', current?.icon)
    || iconNameFor(chain[chain.length - 1]?.key || '', chain[chain.length - 1]?.icon)
    || iconNameFor(chain[0]?.key || '', chain[0]?.icon);

  // ---------------------------------------------------------------- анимации
  const rot = useRef(new Animated.Value(0)).current;
  const rotNow = useRef(0);
  const selRef = useRef(0);
  const lens = useRef(new Animated.Value(1)).current;
  const hubSc = useRef(new Animated.Value(1)).current;
  const breathe = useRef(new Animated.Value(0)).current;
  const morph = useRef(new Animated.Value(1)).current;
  const [dir, setDir] = useState(1);
  const [ghost, setGhost] = useState<{ items: WheelNode[]; depth: number; rot: number } | null>(null);
  const busy = useRef(false);

  useEffect(() => {
    const id = rot.addListener(({ value }) => {
      rotNow.current = value;
      const i = idxAtTop(value, Math.max(1, n));
      if (i !== selRef.current) {
        selRef.current = i;
        setSel(i);
        tick();
        lens.setValue(1.06);
        Animated.spring(lens, { toValue: 1, friction: 5, tension: 220, useNativeDriver: true }).start();
      }
    });
    return () => rot.removeListener(id);
  }, [n, rot, lens]);

  // Дыхание сердцевины: пока есть куда углубляться, она мягко пульсирует. Единственная подсказка,
  // что уровень не последний, — и стоит она ровно там, куда надо нажать.
  useEffect(() => {
    breathe.stopAnimation();
    breathe.setValue(0);
    if (!drillable) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(breathe, { toValue: 1, duration: 1150, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
        Animated.timing(breathe, { toValue: 0, duration: 1150, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [drillable, breathe]);

  const goto = (nextPath: number[], forward: boolean) => {
    if (busy.current) return;
    busy.current = true;
    thud();
    setDir(forward ? 1 : -1);
    setGhost({ items, depth, rot: rotNow.current });
    rot.setValue(0);
    rotNow.current = 0;
    selRef.current = 0;
    setSel(0);
    setPath(nextPath);
    morph.setValue(0);
    hubSc.setValue(0.86);
    Animated.parallel([
      Animated.timing(morph, {
        toValue: 1, duration: 460, easing: Easing.bezier(0.22, 1, 0.36, 1), useNativeDriver: true,
      }),
      Animated.spring(hubSc, { toValue: 1, friction: 6, tension: 90, useNativeDriver: true }),
    ]).start(() => {
      setGhost(null);
      busy.current = false;
    });
  };

  const drill = () => {
    if (busy.current) return;
    const node = items[selRef.current];
    if (!node?.kids?.length || path.length >= MAX_DEPTH) return;
    goto([...path, selRef.current], true);
  };

  const backTo = (d: number) => {
    if (busy.current || d >= path.length) return;
    goto(path.slice(0, d), false);
  };

  // ---------------------------------------------------------------- жест
  const grip = useRef({ on: false, a0: 0, rot0: 0, r0: 0, moved: 0, drilled: false });
  const vel = useRef({ t: 0, v: 0, a: 0 });

  const at = (e: GestureResponderEvent) => {
    const { locationX, locationY } = e.nativeEvent;
    if (typeof locationX !== 'number' || typeof locationY !== 'number') return null;
    const dx = locationX - cx;
    const dy = locationY - cy;
    return { a: topAngle(dx, dy), r: Math.hypot(dx, dy) };
  };

  const onGrant = (e: GestureResponderEvent) => {
    onDragChange?.(true);
    const p = at(e);
    if (!p) return;
    grip.current = { on: true, a0: p.a, rot0: rotNow.current, r0: p.r, moved: 0, drilled: false };
    vel.current = { t: Date.now(), v: 0, a: p.a };
    if (p.r <= hubR) {
      Animated.spring(hubSc, { toValue: 0.93, friction: 7, tension: 200, useNativeDriver: true }).start();
    }
  };

  const onMove = (e: GestureResponderEvent) => {
    const g = grip.current;
    if (!g.on || busy.current) return;
    const p = at(e);
    if (!p) return;

    // Протяжка к центру — третий, необязательный путь вглубь. Требует, чтобы жест НАЧАЛСЯ на
    // кольце: иначе обычное кручение с дрожью радиуса проваливалось бы сюда само.
    if (!g.drilled && drillable && g.r0 > r0 && p.r < r0 - band * 0.5) {
      g.drilled = true;
      g.on = false;
      onDragChange?.(false);
      drill();
      return;
    }

    let da = p.a - g.a0;
    if (da > 180) da -= TAU;
    if (da < -180) da += TAU;

    const now = Date.now();
    const dt = Math.max(1, now - vel.current.t);
    let step = p.a - vel.current.a;
    if (step > 180) step -= TAU;
    if (step < -180) step += TAU;
    vel.current = { t: now, v: (step / dt) * 1000, a: p.a };
    g.moved += Math.abs(step);

    // Подмагничивание: кольцо идёт за пальцем, но подтягивается к центру ближайшей секции.
    const raw = g.rot0 + da;
    const pull = snapTarget(raw, idxAtTop(raw, Math.max(1, n)), Math.max(1, n)) - raw;
    rot.setValue(raw + pull * MAGNET);
  };

  const onRelease = (e: GestureResponderEvent) => {
    const g = grip.current;
    grip.current = { ...g, on: false };
    onDragChange?.(false);
    Animated.spring(hubSc, { toValue: 1, friction: 6, tension: 160, useNativeDriver: true }).start();
    if (busy.current || g.drilled || !n) return;

    const p = at(e);

    if (g.moved < 5) {
      if (!p) return;
      if (p.r <= hubR) { drill(); return; }                       // сердцевина = «вглубь»
      if (p.r >= r0 * 0.86 && p.r <= R) {
        const i = Math.floor(mod(p.a - rotNow.current) / seg) % n;
        if (i === selRef.current) { drill(); return; }            // повторное по выбранной = «вглубь»
        Animated.spring(rot, {
          toValue: snapTarget(rotNow.current, i, n),
          friction: 8, tension: 70, useNativeDriver: true,
        }).start();
      }
      return;
    }

    // Бросок летит по инерции: угол проецируется вперёд по скорости, и колесо докручивается туда.
    const carry = Math.max(-180, Math.min(180, vel.current.v * 0.14));
    const projected = rotNow.current + carry;
    const i = idxAtTop(projected, n);
    Animated.spring(rot, {
      toValue: snapTarget(projected, i, n),
      velocity: vel.current.v / 60,
      friction: 8, tension: 55, useNativeDriver: true,
    }).start();
  };

  const pan = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onStartShouldSetPanResponderCapture: () => true,
        onMoveShouldSetPanResponderCapture: () => true,
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
        onPanResponderGrant: onGrant,
        onPanResponderMove: onMove,
        onPanResponderRelease: onRelease,
        onPanResponderTerminate: onRelease,
      }),
    [n, seg, drillable, r0, band, hubR] // eslint-disable-line react-hooks/exhaustive-deps
  );

  // ---------------------------------------------------------------- вид
  const spin = rot.interpolate({ inputRange: [0, 360], outputRange: ['0deg', '360deg'] });
  const counter = rot.interpolate({ inputRange: [0, 360], outputRange: ['0deg', '-360deg'] });
  const ghostSc = morph.interpolate({ inputRange: [0, 1], outputRange: [1, dir > 0 ? 1.42 : 0.6] });
  const ghostOp = morph.interpolate({ inputRange: [0, 1], outputRange: [1, 0] });
  const liveSc = morph.interpolate({ inputRange: [0, 1], outputRange: [dir > 0 ? 0.6 : 1.42, 1] });
  const liveOp = morph.interpolate({ inputRange: [0, 0.45, 1], outputRange: [0, 0.55, 1] });
  const breatheSc = breathe.interpolate({ inputRange: [0, 1], outputRange: [1, 1.06] });
  const breatheOp = breathe.interpolate({ inputRange: [0, 1], outputRange: [0.3, 0] });

  /** Скруглённые коралловые пилюли — по одной на секцию. */
  const pills = (list: WheelNode[]) => {
    const s = TAU / Math.max(1, list.length);
    const pad = capDeg + 1.6;
    const sweep = s - pad * 2;
    return list.map((node, i) =>
      sweep > 0.6 ? (
        <Path key={node.key} d={arc(cx, cy, rm, i * s + pad, i * s + s - pad)}
              stroke={color.primary} strokeOpacity={0.15} strokeWidth={band}
              strokeLinecap="round" fill="none" />
      ) : (
        <Circle key={node.key} cx={px(cx, rm, i * s + s / 2)} cy={py(cy, rm, i * s + s / 2)}
                r={band * 0.3} fill={color.primary} fillOpacity={0.18} />
      )
    );
  };

  /**
   * Иконки колец — отдельными слоями, каждый доворачивается против вращения кольца.
   *
   * Рисуются на ПЕРВЫХ ДВУХ уровнях: и корни, и подкатегории — это категории, и значок помогает
   * узнать их не читая. Глубже лежат уже конкретные вещи («Падел», «Джаз»), их называет подпись под
   * колесом, а на кольце остаётся точка. Размер считается от толщины кольца, чтобы узкие секции
   * глубоких уровней не получали значок больше себя.
   */
  const icons = (list: WheelNode[], d: number) => {
    if (d > 1) return null;
    const s = TAU / Math.max(1, list.length);
    const arcW = ((s * Math.PI) / 180) * rm;
    const ip = Math.max(15, Math.min(30, Math.min(band * 0.62, arcW * 0.8)));
    return list.map((node, i) => {
      const name = iconNameFor(node.key, node.icon);
      if (!name) return null;
      const am = i * s + s / 2;
      return (
        <Animated.View key={node.key}
                       style={{ position: 'absolute', width: ip, height: ip,
                                left: px(cx, rm, am) - ip / 2, top: py(cy, rm, am) - ip / 2,
                                transform: [{ rotate: counter }] }}>
          <Svg width={ip} height={ip} viewBox="0 0 24 24">{categoryIcon(name, color.primary)}</Svg>
        </Animated.View>
      );
    });
  };

  /**
   * Кольцо перерисовывается ТОЛЬКО при смене уровня — ни щелчок, ни поворот его не трогают.
   * Что именно выбрано, показывает неподвижная линза сверху: она залита кораллом и накрывает ту
   * секцию, что стоит под стрелкой.
   */
  const livePills = useMemo(() => pills(items), [items, rm, band, capDeg]); // eslint-disable-line react-hooks/exhaustive-deps
  const liveIcons = useMemo(() => icons(items, depth), [items, depth, rm, band]); // eslint-disable-line react-hooks/exhaustive-deps
  const ghostPills = useMemo(() => (ghost ? pills(ghost.items) : null), [ghost, rm, band, capDeg]); // eslint-disable-line react-hooks/exhaustive-deps
  const ghostIcons = useMemo(() => (ghost ? icons(ghost.items, ghost.depth) : null), [ghost, rm, band]); // eslint-disable-line react-hooks/exhaustive-deps

  const lensPad = capDeg + 1.6;
  const iconPx = Math.max(18, Math.min(30, band * 0.62));

  return (
    <View style={s.wrap}>
      <View style={{ width: size, height: size }} {...pan.panHandlers}>
        {/* Неподвижное: дорожка кольца и следы пройденных уровней. */}
        <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
          <Circle cx={cx} cy={cy} r={rm} stroke={color.primary} strokeOpacity={0.05}
                  strokeWidth={band} fill="none" />
          {chain.map((node, k) => {
            const tr = hubR + 10 + k * TRACE * R;
            return (
              <React.Fragment key={node.key}>
                <Circle cx={cx} cy={cy} r={tr} stroke={color.primary} strokeOpacity={0.09}
                        strokeWidth={TRACE * R - 4} fill="none" />
                <Path d={arc(cx, cy, tr, -7, 7)} stroke={color.primary} strokeWidth={TRACE * R - 4}
                      strokeLinecap="round" fill="none" />
              </React.Fragment>
            );
          })}
        </Svg>

        {/* Уходящее кольцо — только на время перехода. */}
        {ghost ? (
          <Animated.View pointerEvents="none"
                         style={[StyleSheet.absoluteFill,
                                 { opacity: ghostOp, transform: [{ rotate: `${ghost.rot}deg` }, { scale: ghostSc }] }]}>
            <Svg width={size} height={size} style={StyleSheet.absoluteFill}>{ghostPills}</Svg>
            {ghostIcons}
          </Animated.View>
        ) : null}

        {/* Активное кольцо. */}
        <Animated.View pointerEvents="none"
                       style={[StyleSheet.absoluteFill,
                               { opacity: liveOp, transform: [{ rotate: spin }, { scale: liveSc }] }]}>
          <Svg width={size} height={size} style={StyleSheet.absoluteFill}>{livePills}</Svg>
          {liveIcons}
        </Animated.View>

        {/* Линза: залитая кораллом секция под стрелкой. Неподвижна, кольцо едет под ней. */}
        <Animated.View pointerEvents="none"
                       style={[StyleSheet.absoluteFill, { transform: [{ scale: lens }] }]}>
          <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
            {n ? (
              <Path d={arc(cx, cy, rm, -seg / 2 + lensPad, seg / 2 - lensPad)}
                    stroke={color.primary} strokeWidth={band} strokeLinecap="round" fill="none" />
            ) : null}
          </Svg>
          {depth <= 1 && iconNameFor(current?.key || '', current?.icon) ? (
            <View style={{ position: 'absolute', width: iconPx, height: iconPx,
                           left: cx - iconPx / 2, top: py(cy, rm, 0) - iconPx / 2 }}>
              <Svg width={iconPx} height={iconPx} viewBox="0 0 24 24">
                {categoryIcon(iconNameFor(current!.key, current!.icon), color.onPrimary)}
              </Svg>
            </View>
          ) : null}
        </Animated.View>

        {/* Сердцевина — она же кнопка «вглубь». */}
        <View style={s.hubWrap} pointerEvents="none">
          <Animated.View style={{ transform: [{ scale: hubSc }] }}>
            {drillable ? (
              <Animated.View
                style={[s.halo, { width: hubR * 2, height: hubR * 2, borderRadius: hubR,
                                  opacity: breatheOp, transform: [{ scale: breatheSc }] }]}
              />
            ) : null}
            <View style={[s.hub, { width: hubR * 2, height: hubR * 2, borderRadius: hubR }]}>
              <Svg width={34} height={34} viewBox="0 0 24 24">
                {categoryIcon(branchIcon, color.fg)}
              </Svg>
              {drillable ? <Text style={s.hubCta}>{WHEEL_COPY.refine()}</Text> : null}
            </View>
          </Animated.View>
        </View>
      </View>

      {/* Дорожка пройденного: крошка возвращает на свой уровень. */}
      {depth ? (
        <View style={s.crumbs}>
          {chain.map((node, k) => (
            <Pressable key={node.key} accessibilityRole="button" style={s.crumb} onPress={() => backTo(k)}>
              <Text style={s.crumbText}>‹ {nodeLabel(node)}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {/* Единственное место, где написано, что выбрано. */}
      <Text style={s.picked} numberOfLines={2}>{current ? nodeLabel(current) : ''}</Text>

      <View style={s.btns}>
        {drillable ? (
          <Pressable accessibilityRole="button" style={s.refine} onPress={drill}>
            <Text style={s.refineText}>{WHEEL_COPY.refine()} ›</Text>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityRole="button"
          style={s.add}
          onPress={() => {
            if (!current) return;
            thud();
            const full = [...chain, current];
            onAdd(full.map((x) => x.key), full.map(nodeLabel));
            if (depth) goto([], false);
          }}
        >
          <Text style={s.addText}>{WHEEL_COPY.add()}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { alignItems: 'center', gap: 10 },
  hubWrap: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
  halo: { position: 'absolute', backgroundColor: color.primary },
  hub: {
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center', gap: 2,
    shadowColor: '#000', shadowOpacity: 0.07, shadowRadius: 12, shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  hubCta: { ...type.labelSmall, color: color.muted } as any,
  crumbs: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, justifyContent: 'center' },
  crumb: {
    height: 28, paddingHorizontal: 12, borderRadius: rad.full,
    backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center',
  },
  crumbText: { ...type.labelMedium, color: color.fg } as any,
  picked: { ...type.h2, color: color.fg, textAlign: 'center' } as any,
  btns: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  refine: {
    height: 46, paddingHorizontal: 18, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card,
    alignItems: 'center', justifyContent: 'center',
  },
  refineText: { ...type.button, color: color.fg } as any,
  add: {
    height: 46, paddingHorizontal: 28, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  addText: { ...type.button, color: color.onPrimary } as any,
});
