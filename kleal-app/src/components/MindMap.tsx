/**
 * Карта интересов: восемь тем, в которые ЗАХОДЯТ, и занятия внутри каждой.
 *
 * ПОЧЕМУ НЕ ОДНО ПЛОТНОЕ ПОЛЕ. Раньше все занятия лежали разом: на поле 330×430 при девяноста
 * кружках на каждый приходится квадрат 38×38, а палец накрывает 44×44 — касание перекрывает больше
 * одной цели. Поэтому шагов два: сверху восемь тем, промахнуться нельзя; нажал — то же поле занимает
 * одна тема, и два десятка её занятий лежат крупно, каждое с подписью ВНУТРИ.
 *
 * ЧТО ПЕРЕДЕЛАНО 10 сентября 2026 («переработай дизайн, анимации и UX»):
 *   • Был холст SVG с лупой: подпись читалась только под пальцем, кружки без текста, выбор —
 *     отпустить палец над выделенным. Теперь каждое занятие — пузырь с подписью, и его просто
 *     нажимают. Лупа и защёлка ушли вместе с причиной: целей меньше пальца больше нет.
 *   • Темы в обзоре — как на борде (кадр «Pick what feels like you»): крупный пузырь со спутниками.
 *     Спутники не украшение, а счётчик: сколько занятий в теме уже отмечено, столько спутников
 *     залито фирменным. Цвет темы — свой на каждую (см. ROOT_TONE): красный означает «выбрано» и
 *     только это, как везде в приложении.
 *   • Движение: темы всплывают одна за другой и тихо дышат; выбранная тема раскрывается — занятия
 *     разлетаются из её пузыря по своим местам пружиной; нажатое занятие подпрыгивает; «Все темы»
 *     собирает занятия обратно и возвращает обзор. Всё на нативном драйвере: JS в кадре не
 *     участвует, и бросок пальца по ленте чата ничего не ломает.
 *   • Раскладка тем — фиксированная сотовая сетка 3–2–3 с малым сдвигом, а не спираль: при восьми
 *     элементах спираль читалась как случайная россыпь, сетка — как карта.
 *
 * Раскладка занятий внутри темы считается, а не забита руками: спираль по золотому углу, потом
 * расталкивание перекрывшихся пар (то же, что в src/mindmap.ts). Без случайности: человек,
 * вернувшийся на шаг назад, ищет пузырь глазами там, где видел.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { buildMap, ROOT_TONE } from '../mindmap';
import { STEP_HOBBIES } from '../onboarding';
import { color, deckTone, font, radius as rad } from '../theme';
import { useLang } from '../i18n';
import { hTap, hCommit } from '../haptics';

/** Строка над полем: в обзоре — сколько тем и выбрано, в теме — «‹ Все темы», имя, счётчик. */
const HEAD_H = 36;
/** Диаметр пузыря темы при опорном поле; множится на масштаб поля. */
const ROOT_D = 60;
/** Спутников у темы. Пять — сколько на борде и сколько читается как «несколько», а не как узор. */
const SAT = 5;
const SAT_D = [9, 12, 8, 11, 9];
/** Занятие: не меньше пальца с запасом и не крупнее, чем нужно двум строкам подписи. */
const LEAF_MIN = 54;
const LEAF_MAX = 74;
const GAP = 6;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));
/** Запас пула анимаций: занятий в теме до трёх десятков. */
const POOL = 40;
const ROOTS_N = 8;

const EMOJI: Record<string, string> = {
  sports: '⚽️', social: '🍸', culture: '🎭', outdoors: '🏕️',
  music: '🎵', games: '🎮', learning: '📚', tech: '💻',
};

/** Сотовая сетка 3–2–3 в долях поля. Сдвиги — чтобы сетка не читалась линейкой. */
const GRID: Array<[number, number]> = [
  [0.19, 0.17], [0.50, 0.15], [0.81, 0.18],
  [0.33, 0.50], [0.67, 0.49],
  [0.19, 0.82], [0.50, 0.84], [0.81, 0.81],
];

type Leaf = { key: string; label: string; x: number; y: number; d: number };

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Расталкивание перекрывшихся пузырей, без случайности. В пикселях поля. */
function relax(pts: Leaf[], W: number, H: number) {
  for (let pass = 0; pass < 50; pass++) {
    let moved = false;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i], b = pts[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d = Math.hypot(dx, dy);
        const need = (a.d + b.d) / 2 + GAP;
        if (d >= need) continue;
        if (d < 0.001) { dx = 1; dy = 0; d = 1; }
        const push = (need - d) / 2;
        a.x -= (dx / d) * push; a.y -= (dy / d) * push;
        b.x += (dx / d) * push; b.y += (dy / d) * push;
        moved = true;
      }
    }
    for (const p of pts) {
      p.x = clamp(p.x, p.d / 2 + 2, W - p.d / 2 - 2);
      p.y = clamp(p.y, p.d / 2 + 2, H - p.d / 2 - 2);
    }
    if (!moved) break;
  }
}

export function MindMap({ width: widthProp, height, selected, onToggle }: {
  /** Ширина поля. Не задана — по экрану: ширина окна минус поля виджета чата. */
  width?: number;
  height: number;
  selected: string[];
  onToggle: (key: string) => void;
  /** Оставлен для совместимости вызова: жеста-перетаскивания у карты больше нет. */
  onDrag?: (dragging: boolean) => void;
}) {
  const lang = useLang();
  const win = useWindowDimensions();
  const width = widthProp ?? Math.min(win.width - 32, 380);
  const canvasH = height - HEAD_H;
  const all = useMemo(() => buildMap(width, canvasH), [width, canvasH, lang]);
  const roots = useMemo(() => all.filter((b) => b.kind === 'root'), [all]);
  const [open, setOpen] = useState<string | null>(null);
  const openRoot = roots.find((r) => r.key === open) || null;

  const k = clamp(Math.sqrt((width * canvasH) / (330 * 394)), 0.85, 1.2);
  const R = Math.round((ROOT_D * k) / 2);
  /** Коробка темы: пузырь, поля под спутники и строка подписи. */
  const PAD = 20;
  const BOX = 2 * R + 2 * PAD;
  const LABEL_H = 18;

  /** Сколько занятий отмечено в каждой теме — это и спутники, и цифра на пузыре. */
  const pickedIn = useMemo(() => {
    const m: Record<string, number> = {};
    for (const b of all) if (b.kind === 'leaf' && selected.includes(b.key)) m[b.root] = (m[b.root] || 0) + 1;
    return m;
  }, [all, selected]);

  const leaves = useMemo<Leaf[]>(() => {
    if (!open) return [];
    const list = all.filter((b) => b.kind === 'leaf' && b.root === open);
    const n = list.length || 1;
    const d = Math.round(clamp(Math.sqrt((width * canvasH * 0.52) / n), LEAF_MIN, LEAF_MAX));
    const cx = width / 2, cy = canvasH / 2;
    const spanX = width / 2 - d / 2 - 4, spanY = canvasH / 2 - d / 2 - 4;
    const pts: Leaf[] = list.map((b, i) => {
      const a = i * GOLDEN;
      const t = Math.sqrt((i + 0.5) / n);
      return { key: b.key, label: b.label, x: cx + Math.cos(a) * t * spanX, y: cy + Math.sin(a) * t * spanY, d };
    });
    relax(pts, width, canvasH);
    return pts;
  }, [open, all, width, canvasH]);

  // ---------------------------------------------------------------- движение
  /** Появление тем: 0 → 1 пружиной, одна за другой. */
  const enter = useRef(Array.from({ length: ROOTS_N }, () => new Animated.Value(0))).current;
  /** Дыхание тем: 0 ↔ 1 по кругу, у каждой своя длительность — фазы расходятся сами. */
  const breath = useRef(Array.from({ length: ROOTS_N }, () => new Animated.Value(0))).current;
  /** Подпрыгивание нажатой темы. */
  const rootPop = useRef(Array.from({ length: ROOTS_N }, () => new Animated.Value(1))).current;
  /** Разлёт занятий из пузыря темы: 0 — все в её центре, 1 — на местах. */
  const bloom = useRef(Array.from({ length: POOL }, () => new Animated.Value(0))).current;
  /** Подпрыгивание нажатого занятия. */
  const pop = useRef(Array.from({ length: POOL }, () => new Animated.Value(1))).current;
  /** Откуда разлетаются: центр нажатой темы. */
  const from = useRef({ x: width / 2, y: canvasH / 2 });
  const busy = useRef(false);

  const showRoots = () => {
    enter.forEach((v) => v.setValue(0));
    Animated.stagger(40, enter.map((v) =>
      Animated.spring(v, { toValue: 1, useNativeDriver: true, friction: 6, tension: 70 }),
    )).start();
  };

  useEffect(() => {
    showRoots();
    const loops = breath.map((v, i) => Animated.loop(Animated.sequence([
      Animated.timing(v, { toValue: 1, duration: 2300 + i * 190, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      Animated.timing(v, { toValue: 0, duration: 2300 + i * 190, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
    ])));
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    bloom.forEach((v) => v.setValue(0));
    Animated.stagger(16, leaves.map((_, i) =>
      Animated.spring(bloom[i], { toValue: 1, useNativeDriver: true, friction: 7, tension: 60 }),
    )).start(() => { busy.current = false; });
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const enterRoot = (key: string, i: number, x: number, y: number) => {
    if (busy.current) return;
    busy.current = true;
    hCommit();
    from.current = { x, y };
    Animated.sequence([
      Animated.timing(rootPop[i], { toValue: 1.12, duration: 90, useNativeDriver: true }),
      Animated.timing(rootPop[i], { toValue: 1, duration: 120, useNativeDriver: true }),
    ]).start();
    // Остальные темы гаснут, нажатая — последней: из неё и разлетится содержимое.
    Animated.parallel(enter.map((v, j) =>
      Animated.timing(v, { toValue: 0, duration: j === i ? 220 : 140, easing: Easing.in(Easing.quad), useNativeDriver: true }),
    )).start(() => setOpen(key));
  };

  const back = () => {
    if (busy.current) return;
    busy.current = true;
    hTap();
    Animated.parallel(leaves.map((_, i) =>
      Animated.timing(bloom[i], { toValue: 0, duration: 160, easing: Easing.in(Easing.quad), useNativeDriver: true }),
    )).start(() => {
      setOpen(null);
      busy.current = false;
      showRoots();
    });
  };

  const toggle = (leaf: Leaf, i: number) => {
    hTap();
    Animated.sequence([
      Animated.timing(pop[i], { toValue: 1.14, duration: 80, useNativeDriver: true }),
      Animated.spring(pop[i], { toValue: 1, useNativeDriver: true, friction: 4, tension: 120 }),
    ]).start();
    onToggle(leaf.key);
  };

  const total = selected.length;

  return (
    <View style={{ width, alignSelf: 'center' }}>
      {/* Строка над полем одной высоты в обоих состояниях: поле не прыгает при входе в тему. */}
      <View style={s.head}>
        {open ? (
          <Pressable accessibilityRole="button" onPress={back} hitSlop={8} style={s.back}>
            <Text style={s.backText}>‹  {STEP_HOBBIES.mapAll()}</Text>
          </Pressable>
        ) : (
          <Text style={s.headMuted}>{STEP_HOBBIES.mapTopics(roots.length)}</Text>
        )}
        <Text style={s.headName} numberOfLines={1}>{openRoot ? `${EMOJI[openRoot.key] || ''}  ${openRoot.label}` : ''}</Text>
        <Text style={[s.headCount, total ? { color: color.primary } : null]}>
          {open ? (pickedIn[open] || 0) : STEP_HOBBIES.mapPickedShort(total)}
        </Text>
      </View>

      <View style={{ width, height: canvasH }}>
        {!open ? roots.map((root, i) => {
          const t = deckTone[ROOT_TONE[root.key] || 'slate'];
          const [gx, gy] = GRID[i % GRID.length];
          const cx = gx * width, cy = gy * canvasH;
          const n = pickedIn[root.key] || 0;
          const scale = Animated.multiply(
            enter[i].interpolate({ inputRange: [0, 1], outputRange: [0.55, 1] }),
            rootPop[i],
          );
          const float = breath[i].interpolate({ inputRange: [0, 1], outputRange: [-3, 3] });
          return (
            <Animated.View
              key={root.key}
              style={[s.abs, {
                left: cx - BOX / 2, top: cy - BOX / 2, width: BOX, height: BOX + LABEL_H,
                opacity: enter[i], transform: [{ translateY: float }, { scale }],
              }]}
            >
              {/* Спутники: столько залито фирменным, сколько занятий отмечено внутри. */}
              {Array.from({ length: SAT }, (_, j) => {
                const a = i * 0.8 + j * ((Math.PI * 2) / SAT) + 0.4;
                const rr = R + 13;
                const sd = SAT_D[j];
                return (
                  <View
                    key={j}
                    style={[s.sat, {
                      width: sd, height: sd, borderRadius: sd / 2,
                      left: PAD + R + Math.cos(a) * rr - sd / 2, top: PAD + R + Math.sin(a) * rr - sd / 2,
                      backgroundColor: j < n ? color.primary : t.halo,
                    }]}
                  />
                );
              })}
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={root.label}
                onPress={() => enterRoot(root.key, i, cx, cy)}
                style={({ pressed }) => [s.root, {
                  left: PAD, top: PAD, width: 2 * R, height: 2 * R, borderRadius: R,
                  backgroundColor: t.wash, borderColor: t.halo,
                }, pressed && { transform: [{ scale: 0.94 }] }]}
              >
                <Text style={[s.emoji, { fontSize: Math.round(R * 0.8) }]}>{EMOJI[root.key] || '•'}</Text>
                {n ? (
                  <View style={s.badge}><Text style={s.badgeText}>{n}</Text></View>
                ) : null}
              </Pressable>
              <Text style={[s.rootLabel, { top: BOX - 4, width: BOX }]} numberOfLines={1}>{root.label}</Text>
            </Animated.View>
          );
        }) : leaves.map((leaf, i) => {
          const t = deckTone[ROOT_TONE[open] || 'slate'];
          const on = selected.includes(leaf.key);
          const b = bloom[i];
          const scale = Animated.multiply(b.interpolate({ inputRange: [0, 1], outputRange: [0.3, 1] }), pop[i]);
          return (
            <Animated.View
              key={leaf.key}
              style={[s.abs, {
                left: leaf.x - leaf.d / 2, top: leaf.y - leaf.d / 2, width: leaf.d, height: leaf.d,
                opacity: b,
                transform: [
                  { translateX: b.interpolate({ inputRange: [0, 1], outputRange: [from.current.x - leaf.x, 0] }) },
                  { translateY: b.interpolate({ inputRange: [0, 1], outputRange: [from.current.y - leaf.y, 0] }) },
                  { scale },
                ],
              }]}
            >
              <Pressable
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                accessibilityLabel={leaf.label}
                onPress={() => toggle(leaf, i)}
                style={({ pressed }) => [s.leaf, {
                  borderRadius: leaf.d / 2,
                  backgroundColor: on ? color.primary : t.wash,
                  borderColor: on ? color.primary : t.halo,
                }, on && s.leafOn, pressed && { transform: [{ scale: 0.94 }] }]}
              >
                <Text
                  style={[s.leafText, {
                    fontSize: leaf.d >= 66 ? 12 : leaf.d >= 60 ? 11 : 10,
                    lineHeight: leaf.d >= 66 ? 15 : leaf.d >= 60 ? 14 : 12,
                    color: on ? color.onPrimary : color.fg,
                  }]}
                  numberOfLines={2}
                >
                  {leaf.label}
                </Text>
              </Pressable>
            </Animated.View>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  head: { height: HEAD_H, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 2 },
  back: { paddingVertical: 4, paddingRight: 2 },
  backText: { fontFamily: font.textMedium, fontSize: 13, color: color.primary } as any,
  headMuted: { fontFamily: font.textMedium, fontSize: 13, color: color.muted } as any,
  headName: { flex: 1, fontFamily: font.textSemibold, fontSize: 15, color: color.fg } as any,
  headCount: { fontFamily: font.textMedium, fontSize: 13, color: color.muted, minWidth: 18, textAlign: 'right' } as any,

  abs: { position: 'absolute' },
  sat: { position: 'absolute' },
  root: {
    position: 'absolute', borderWidth: 1.5, alignItems: 'center', justifyContent: 'center',
    shadowColor: '#0B1220', shadowOpacity: 0.08, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 2,
  },
  emoji: { textAlign: 'center' },
  badge: {
    position: 'absolute', top: -4, right: -4, minWidth: 20, height: 20, borderRadius: 10, paddingHorizontal: 5,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: color.card,
  },
  badgeText: { fontFamily: font.textSemibold, fontSize: 11, lineHeight: 13, color: color.onPrimary } as any,
  rootLabel: {
    position: 'absolute', left: 0, textAlign: 'center',
    fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.fg,
  } as any,

  leaf: {
    flex: 1, borderWidth: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6,
  },
  /** Выбранное приподнято розовым свечением — тем же, что у главных кнопок. */
  leafOn: {
    shadowColor: color.primary, shadowOpacity: 0.32, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 4,
  },
  leafText: { fontFamily: font.textMedium, textAlign: 'center' } as any,
});
