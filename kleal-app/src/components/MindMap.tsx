/**
 * Карта интересов (шаг анкеты после языков): восемь тем, в которые ЗАХОДЯТ, и занятия внутри.
 *
 * СМЫСЛ ПРЕЖНИЙ, ВИД НОВЫЙ (26 сентября 2026, «сделай красиво, качественно и удобно»):
 *   • ОБЗОР — настоящая карта: в центре капля Kleal, от неё тонкие нити к восьми темам по кругу.
 *     Нить темы, в которой уже что-то выбрано, становится коралловой — видно, куда ты уже ходил.
 *     Над темой пять точек-спутников — счётчик выбранного внутри, как и было.
 *   • ТЕМА — она встаёт в центр, занятия раскрываются вокруг неё облаком. Пузырь занятия теперь
 *     РАЗМЕРОМ ПО ПОДПИСИ: «Предпринимательство» и «Языковой обмен» помещаются целиком, а не
 *     режутся многоточием в круге одного размера на всех. Выбранное заливается кораллом, и к нему
 *     от центра тянется коралловая нить.
 *   • ЦВЕТ СДЕРЖАННЫЙ. Эмодзи заменены контурными знаками одного веса (TopicIcon), у каждой темы —
 *     едва заметный свой оттенок стекла; яркий цвет на карте один — коралл выбора.
 *   • ДВИЖЕНИЕ СПОКОЙНОЕ: только плавное замедление, без пружин и «дыхания». Вход в тему — нажатая
 *     тема мягко переезжает в центр, остальные гаснут, занятия расходятся от неё; «Все темы» —
 *     обратно. Выбор — короткое перетекание цвета. Всё на нативном драйвере.
 *
 * Стекло здесь нарисовано видом (белая плёнка, кромка, тень), а не системным UIGlassEffect:
 * пузыри появляются и гаснут прозрачностью, а системное стекло под прозрачностью не рисуется
 * вовсе (см. LiquidGlass.tsx). К тому же тридцать системных стёкол на одном поле — дорого.
 *
 * Геометрия — в src/mindmapLayout.ts: там же её проверка на всех темах и языках.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { useReducedMotion } from 'react-native-reanimated';
import { mapPools } from '../mindmap';
import { HUB_D, NODE_D, NODE_LABEL_H, LEAF_PAD, PAGE, leafSpots, nextPage, threadPath, topicSpots } from '../mindmapLayout';
import { STEP_HOBBIES } from '../onboarding';
import { color, font, labelFamily } from '../theme';
import { useLang } from '../i18n';
import { hTap, hCommit } from '../haptics';
import { Blob } from './Blob';
import { TopicIcon } from './TopicIcon';
import { IconChevronLeft, IconRefresh } from './icons';

/** Строка над полем одной высоты в обоих состояниях: поле не прыгает при входе в тему. */
const HEAD_H = 44;
/** Спутники-счётчик над темой. */
const SAT = 5;
const SAT_D = 6;
/** Запас пула значений: занятий в теме до трёх десятков. */
const POOL = 40;

const INK = '#181B22';
const ICON = '#3B404B';
const CORAL = '#FF385C';

/**
 * Оттенок стекла темы. Все восемь — светлые и приглушённые, отличаются тоном, а не яркостью:
 * тему узнают, но поле не становится пёстрым.
 */
const TINT: Record<string, string> = {
  sports: '#E4EEDF', social: '#F3E7DA', culture: '#E7E4F1', outdoors: '#DDEBE7',
  music: '#F2E1E5', games: '#E0E5F1', learning: '#EFE9DC', tech: '#E3E6EB',
};
const tintOf = (key: string | null) => TINT[key || ''] || '#E9E7E3';

export function MindMap({ width: widthProp, height, selected, onToggle, backSignal, onTopicChange }: {
  /** Ширина поля. Не задана — по экрану: ширина окна минус поля виджета чата. */
  width?: number;
  height: number;
  selected: string[];
  onToggle: (key: string) => void;
  /** Оставлен для совместимости вызова: жеста-перетаскивания у карты нет. */
  onDrag?: (dragging: boolean) => void;
  /**
   * «Назад» снаружи: стрелка шапки экрана, жест и кнопка Android. Каждое новое значение — вернуться
   * из темы ко всем темам. Экран узнаёт, открыта ли тема, через `onTopicChange`.
   */
  backSignal?: number;
  onTopicChange?: (open: boolean) => void;
}) {
  const lang = useLang();
  const reduced = useReducedMotion();
  const win = useWindowDimensions();
  const width = widthProp ?? Math.min(win.width - 32, 380);
  const H = height - HEAD_H;
  const hub = { x: width / 2, y: H / 2 };

  // Темы и ВСЕ их занятия (без раскладки старого поля — она тут не нужна и дорога).
  const pools = useMemo(() => mapPools(), [lang]);
  const roots = pools.roots;
  const spots = useMemo(() => topicSpots(roots.length, width, H), [roots.length, width, H]);
  const [open, setOpen] = useState<string | null>(null);
  const openRoot = roots.find((r) => r.key === open) || null;

  /**
   * Занятия темы БЕЗ ПОВТОРОВ ПОДПИСИ. В реестре бывает два ключа с одной подписью (security и
   * cybersecurity — оба «Безопасность»); на карте это два одинаковых пузыря. Показывается один,
   * выбор записывает первый ключ, а снятие снимает любой из них.
   */
  type Item = { key: string; keys: string[]; label: string };
  const itemsOf = useMemo(() => {
    const cache: Record<string, Item[]> = {};
    return (topic: string): Item[] => {
      if (cache[topic]) return cache[topic];
      const byLabel = new Map<string, Item>();
      for (const b of pools.leaves[topic] || []) {
        const id = b.label.trim().toLowerCase();
        const it = byLabel.get(id);
        if (it) { if (!it.keys.includes(b.key)) it.keys.push(b.key); }
        else byLabel.set(id, { key: b.key, keys: [b.key], label: b.label });
      }
      cache[topic] = [...byLabel.values()];
      return cache[topic];
    };
  }, [pools]);
  const isOn = (it: Item) => it.keys.some((k) => selected.includes(k));

  const pickedIn = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of roots) m[r.key] = itemsOf(r.key).filter((it) => it.keys.some((k) => selected.includes(k))).length;
    return m;
  }, [roots, itemsOf, selected]);

  /*
    ПОДБОРКА ВМЕСТО ВСЕГО ОБЛАКА. В теме до двух сотен занятий; разом видно около десятка, а знак
    темы в центре показывает следующие. Выбранные при этом остаются. Где начиналась подборка,
    помнится по теме: вернувшись в неё, человек видит ту же подборку, а не случайно другую.
  */
  const [page, setPage] = useState<string[]>([]);
  const pageStart = useRef<Record<string, number>>({});
  const pageNext = useRef<Record<string, number>>({});
  const pageOf = (topic: string): string[] => {
    const items = itemsOf(topic);
    const keep = items.filter(isOn).map((it) => it.key);
    const r = nextPage(items.map((it) => it.key), keep, pageStart.current[topic] ?? 0);
    pageNext.current[topic] = r.next;
    return r.keys;
  };

  const leaves = useMemo(() => {
    if (!open) return [];
    const byKey = new Map(itemsOf(open).map((it) => [it.key, it]));
    const list = page.map((k) => byKey.get(k)).filter(Boolean).map((it) => ({ key: it!.key, label: it!.label }));
    return leafSpots(list, width, H);
  }, [open, page, itemsOf, width, H]);
  const itemOf = (key: string) => (open ? itemsOf(open).find((it) => it.key === key) : undefined);
  const leafOn = (key: string) => { const it = itemOf(key); return it ? isOn(it) : selected.includes(key); };
  const toggleLeaf = (key: string) => {
    const it = itemOf(key);
    if (!it) { onToggle(key); return; }
    if (isOn(it)) it.keys.filter((k) => selected.includes(k)).forEach(onToggle);
    else onToggle(it.key);
  };
  const canShuffle = !!open && itemsOf(open).length > PAGE;

  // ---------------------------------------------------------------- движение
  const ease = Easing.out(Easing.cubic);
  const run = (v: Animated.Value, to: number, ms: number, e = ease, delay = 0) =>
    Animated.timing(v, { toValue: to, duration: reduced ? 0 : ms, easing: e, delay: reduced ? 0 : delay, useNativeDriver: true });

  /** Обзор виден (всё, кроме темы, которая сейчас едет). */
  const shown = useRef(new Animated.Value(0)).current;
  /** Нажатая тема едет в центр: 0 — на своём месте, 1 — в центре. */
  const glide = useRef(new Animated.Value(0)).current;
  const [gliding, setGliding] = useState(-1);
  /** Занятия темы: 0 — собраны у центра и не видны, 1 — на местах. */
  const bloom = useRef(new Animated.Value(0)).current;
  /** Заливка выбранного: у каждого занятия своё значение, чтобы цвет перетекал только у нажатого. */
  const onV = useRef(Array.from({ length: POOL }, () => new Animated.Value(0))).current;
  const busy = useRef(false);
  /** Смена подборки: уходящие гаснут (`swap` → 0), новые проявляются (`arrive` → 1). */
  const swap = useRef(new Animated.Value(1)).current;
  const arrive = useRef(new Animated.Value(1)).current;
  /** Поворот значка «другие» на пузыре темы. */
  const spin = useRef(new Animated.Value(0)).current;
  /** Кто уходит, кто остаётся и где остающиеся стояли — на время одной смены подборки. */
  const leaving = useRef<Set<string>>(new Set());
  const kept = useRef<Set<string> | null>(null);
  const prevPos = useRef<Record<string, { x: number; y: number }>>({});
  const arriving = useRef(false);
  /** Постоянные множители для сборки выражений анимации — чтобы не плодить узлы на каждую отрисовку. */
  const ONE = useRef(new Animated.Value(1)).current;
  const ZERO = useRef(new Animated.Value(0)).current;

  useEffect(() => { run(shown, 1, 360).start(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Новая подборка — заливка ставится сразу; нажатие в той же подборке — перетекает.
  const lastLeaves = useRef<typeof leaves | null>(null);
  useEffect(() => {
    const fresh = lastLeaves.current !== leaves;
    lastLeaves.current = leaves;
    leaves.forEach((leaf, i) => {
      if (i >= POOL) return;
      const to = leafOn(leaf.key) ? 1 : 0;
      if (fresh) onV[i].setValue(to);
      else run(onV[i], to, 180).start();
    });
  }, [leaves, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    bloom.setValue(0);
    run(bloom, 1, 340).start(() => { busy.current = false; });
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const enter = (i: number) => {
    if (busy.current) return;
    busy.current = true;
    hCommit();
    setGliding(i);
    glide.setValue(0);
    Animated.parallel([run(shown, 0, 180, Easing.out(Easing.quad)), run(glide, 1, 320)]).start(() => {
      setPage(pageOf(roots[i].key));
      setOpen(roots[i].key);
    });
  };

  const back = () => {
    if (busy.current || !open) return;
    busy.current = true;
    hTap();
    const i = roots.findIndex((r) => r.key === open);
    run(bloom, 0, 180, Easing.in(Easing.quad)).start(() => {
      setGliding(i);
      glide.setValue(1);
      shown.setValue(0);
      setOpen(null);
      Animated.parallel([run(glide, 0, 300), run(shown, 1, 260, ease, 80)]).start(() => {
        setGliding(-1);
        busy.current = false;
      });
    });
  };

  /**
   * «ПОКАЗАТЬ ДРУГИЕ» — нажатие на знак темы в центре. Выбранные остаются и плавно доезжают на новые
   * места, невыбранные тихо гаснут, на их месте проявляются следующие из очереди темы.
   */
  const shuffle = () => {
    if (busy.current || !open || !canShuffle) return;
    busy.current = true;
    hTap();
    const keep = page.filter((k) => leafOn(k));
    const avoid = page.filter((k) => !keep.includes(k));
    const from = pageNext.current[open] ?? 0;
    const items = itemsOf(open);
    const r = nextPage(items.map((it) => it.key), keep, from, avoid);
    pageStart.current[open] = from;
    pageNext.current[open] = r.next;
    spin.setValue(0);
    run(spin, 1, 560).start();
    prevPos.current = Object.fromEntries(leaves.map((l) => [l.key, { x: l.x, y: l.y }]));
    leaving.current = new Set(avoid);
    run(swap, 0, 170, Easing.in(Easing.quad)).start(() => {
      kept.current = new Set(keep);
      arrive.setValue(0);
      arriving.current = true;
      setPage(r.keys);
    });
  };

  // Подборка сменилась по «другим» — проявить новые и довезти оставшиеся.
  useEffect(() => {
    if (!arriving.current) return;
    arriving.current = false;
    leaving.current = new Set();
    swap.setValue(1);
    run(arrive, 1, 340).start(() => {
      kept.current = null;
      prevPos.current = {};
      busy.current = false;
    });
  }, [page]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { onTopicChange?.(!!open); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onTopicChange?.(false), []); // eslint-disable-line react-hooks/exhaustive-deps
  const lastBack = useRef(backSignal);
  useEffect(() => {
    if (backSignal === lastBack.current) return;
    lastBack.current = backSignal;
    back();
  }, [backSignal]); // eslint-disable-line react-hooks/exhaustive-deps

  const total = selected.length;
  const here = open ? pickedIn[open] || 0 : total;

  return (
    <View style={{ width, alignSelf: 'center' }}>
      <View style={s.head}>
        <View style={s.headSide}>
          {open ? (
            <Pressable accessibilityRole="button" accessibilityLabel={STEP_HOBBIES.mapAll()} onPress={back} hitSlop={10}
                       testID="mindmap-back"
                       style={({ pressed }) => [s.backPill, pressed && s.pressed]}>
              <IconChevronLeft size={18} c={INK} />
              <Text style={s.backText} numberOfLines={1}>{STEP_HOBBIES.mapAll()}</Text>
            </Pressable>
          ) : (
            <Text style={s.headMuted}>{STEP_HOBBIES.mapTopics(roots.length)}</Text>
          )}
        </View>
        <Text style={[s.headName, { fontFamily: labelFamily(lang) }]} numberOfLines={1}>
          {openRoot ? openRoot.label : ''}
        </Text>
        <View style={[s.headSide, s.headRight]}>
          <View style={[s.count, here ? s.countOn : null]}>
            <Text style={[s.countText, here ? s.countTextOn : null]} numberOfLines={1}>
              {STEP_HOBBIES.mapPickedShort(here)}
            </Text>
          </View>
        </View>
      </View>

      <View style={{ width, height: H }}>
        {!open ? (
          <>
            {/* Нити от центра к темам. Коралловая — в теме уже что-то выбрано. */}
            <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, { opacity: shown }]}>
              <Svg width={width} height={H}>
                {spots.map((p, i) => {
                  const on = (pickedIn[roots[i]?.key] || 0) > 0;
                  return (
                    <Path key={i} d={threadPath(hub, HUB_D / 2 + 4, p, NODE_D / 2 + 4)} fill="none"
                          stroke={on ? 'rgba(255,56,92,0.55)' : 'rgba(24,27,34,0.10)'} strokeWidth={on ? 1.4 : 1} />
                  );
                })}
              </Svg>
            </Animated.View>

            {/* Центр — капля Kleal: карту собирает агент, и начинается она от него. */}
            <Animated.View pointerEvents="none"
              style={[s.hub, { left: hub.x - HUB_D / 2, top: hub.y - HUB_D / 2, opacity: shown }]}>
              <Blob size={30} />
            </Animated.View>

            {roots.map((root, i) => {
              const p = spots[i];
              if (!p) return null;
              const n = pickedIn[root.key] || 0;
              const moving = i === gliding;
              const box = NODE_D + 40;
              return (
                <Animated.View
                  key={root.key}
                  style={[s.abs, {
                    left: p.x - box / 2, top: p.y - NODE_D / 2 - 20, width: box, height: NODE_D + 20 + NODE_LABEL_H + 6,
                    opacity: moving ? 1 : shown,
                    transform: moving
                      ? [
                          { translateX: glide.interpolate({ inputRange: [0, 1], outputRange: [0, hub.x - p.x] }) },
                          { translateY: glide.interpolate({ inputRange: [0, 1], outputRange: [0, hub.y - p.y] }) },
                        ]
                      : [
                          // Появление — лёгкое стягивание к своему месту со стороны центра.
                          { translateX: shown.interpolate({ inputRange: [0, 1], outputRange: [(hub.x - p.x) * 0.06, 0] }) },
                          { translateY: shown.interpolate({ inputRange: [0, 1], outputRange: [(hub.y - p.y) * 0.06, 0] }) },
                        ],
                  }]}
                >
                  {/* Спутники и подпись гаснут у едущей темы: в центре её имя уже в шапке. */}
                  <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, { opacity: moving ? shown : 1 }]}>
                    {Array.from({ length: SAT }, (_, j) => {
                      const a = ((-140 + j * 25) * Math.PI) / 180;
                      const rr = NODE_D / 2 + 9;
                      return (
                        <View key={j} style={[s.sat, j < n ? s.satOn : null, {
                          left: box / 2 + Math.cos(a) * rr - SAT_D / 2,
                          top: 20 + NODE_D / 2 + Math.sin(a) * rr - SAT_D / 2,
                        }]} />
                      );
                    })}
                    <Text style={[s.nodeLabel, { top: 20 + NODE_D + 6, width: box }]} numberOfLines={1}
                          adjustsFontSizeToFit minimumFontScale={0.85}>
                      {root.label}
                    </Text>
                    {n > SAT ? <View style={[s.more, { left: box / 2 + 22, top: 12 }]}><Text style={s.moreText}>{n}</Text></View> : null}
                  </Animated.View>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={n ? `${root.label}, ${STEP_HOBBIES.mapPickedShort(n)}` : root.label}
                    onPress={() => enter(i)}
                    style={({ pressed }) => [s.abs, { left: 20, top: 20 }, pressed && s.pressed]}
                  >
                    <TopicBubble topic={root.key} d={NODE_D} />
                  </Pressable>
                </Animated.View>
              );
            })}
          </>
        ) : (
          <>
            {/* Нити к выбранному — от темы в центре. */}
            <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, { opacity: bloom }]}>
              <Svg width={width} height={H}>
                {leaves.map((leaf) => leafOn(leaf.key) ? (
                  <Path key={leaf.key} d={threadPath(hub, NODE_D / 2 + 3, leaf, leaf.d / 2 + 3, 0.08)} fill="none"
                        stroke="rgba(255,56,92,0.38)" strokeWidth={1.2} />
                ) : null)}
              </Svg>
            </Animated.View>

            {/*
              Тема в центре — кнопка «показать другие» (значок со стрелками в углу). Назад ко всем
              темам — пилюлей «Все темы» в шапке. В теме, где всё и так видно, центр ничего не делает.
            */}
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={canShuffle ? STEP_HOBBIES.mapShuffle() : openRoot?.label || ''}
              accessibilityState={{ disabled: !canShuffle }}
              disabled={!canShuffle}
              onPress={shuffle}
              style={({ pressed }) => [s.abs, { left: hub.x - NODE_D / 2, top: hub.y - NODE_D / 2 }, pressed && s.pressed]}
            >
              <TopicBubble topic={open} d={NODE_D} />
              {canShuffle ? (
                <View style={s.shuffleBadge} pointerEvents="none">
                  <Animated.View style={{ transform: [{ rotate: spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] }) }] }}>
                    <IconRefresh size={13} c={INK} />
                  </Animated.View>
                </View>
              ) : null}
            </Pressable>

            {leaves.map((leaf, i) => {
              const v = onV[Math.min(i, POOL - 1)];
              const on = leafOn(leaf.key);
              // Смена подборки: уходящий гаснет, новый проявляется, оставшийся доезжает с прежнего места.
              const goes = leaving.current.has(leaf.key);
              const stays = !!kept.current && kept.current.has(leaf.key);
              const comes = !!kept.current && !stays;
              const was = stays ? prevPos.current[leaf.key] : undefined;
              const fade = Animated.multiply(Animated.multiply(bloom, goes ? swap : ONE), comes ? arrive : ONE);
              const size = Animated.multiply(
                Animated.multiply(
                  bloom.interpolate({ inputRange: [0, 1], outputRange: [0.9, 1] }),
                  v.interpolate({ inputRange: [0, 1], outputRange: [1, 1.04] }),
                ),
                comes ? arrive.interpolate({ inputRange: [0, 1], outputRange: [0.9, 1] })
                  : goes ? swap.interpolate({ inputRange: [0, 1], outputRange: [0.9, 1] }) : ONE,
              );
              const dx = Animated.add(
                bloom.interpolate({ inputRange: [0, 1], outputRange: [(hub.x - leaf.x) * 0.45, 0] }),
                was ? arrive.interpolate({ inputRange: [0, 1], outputRange: [was.x - leaf.x, 0] }) : ZERO,
              );
              const dy = Animated.add(
                bloom.interpolate({ inputRange: [0, 1], outputRange: [(hub.y - leaf.y) * 0.45, 0] }),
                was ? arrive.interpolate({ inputRange: [0, 1], outputRange: [was.y - leaf.y, 0] }) : ZERO,
              );
              // Кегль посчитан раскладкой так, чтобы строка точно помещалась: текст ничего не подбирает сам.
              const text = { fontSize: leaf.font, lineHeight: Math.round(leaf.font * 1.22) };
              return (
                <Animated.View
                  key={leaf.key}
                  style={[s.abs, {
                    left: leaf.x - leaf.d / 2, top: leaf.y - leaf.d / 2, width: leaf.d, height: leaf.d,
                    opacity: fade,
                    transform: [{ translateX: dx }, { translateY: dy }, { scale: size }],
                  }]}
                >
                  <Pressable
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: on }}
                    accessibilityLabel={leaf.label}
                    onPress={() => { hTap(); toggleLeaf(leaf.key); }}
                    style={({ pressed }) => [{ flex: 1 }, pressed && s.pressed]}
                  >
                    {/* Спокойное состояние: светлое стекло с оттенком темы. */}
                    <View style={[s.leaf, { borderRadius: leaf.d / 2 }]}>
                      <View style={[StyleSheet.absoluteFill, { borderRadius: leaf.d / 2, backgroundColor: tintOf(open), opacity: 0.5 }]} />
                      <Text style={[s.leafText, text]} numberOfLines={leaf.lines}>
                        {leaf.text}
                      </Text>
                    </View>
                    {/* Выбранное: коралл поверх, перетекает прозрачностью. */}
                    <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, s.leafOn, { borderRadius: leaf.d / 2, opacity: v }]}>
                      <Text style={[s.leafText, s.leafTextOn, text]} numberOfLines={leaf.lines}>
                        {leaf.text}
                      </Text>
                    </Animated.View>
                  </Pressable>
                </Animated.View>
              );
            })}
          </>
        )}
      </View>
    </View>
  );
}

/**
 * Пузырь темы: стекло её оттенка — сверху светлее (блик), книзу чистый тон, — кромка, мягкая
 * тень и знак. Блик нарисован градиентом: белая половина видом дала бы капсулу, а не свет.
 */
function TopicBubble({ topic, d }: { topic: string | null; d: number }) {
  const id = `shine-${topic || 'x'}`;
  return (
    <View style={[s.topic, { width: d, height: d, borderRadius: d / 2 }]}>
      <Svg width={d} height={d} style={StyleSheet.absoluteFill}>
        <Defs>
          <LinearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.7} />
            <Stop offset="0.55" stopColor="#FFFFFF" stopOpacity={0.1} />
            <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
          </LinearGradient>
        </Defs>
        <Circle cx={d / 2} cy={d / 2} r={d / 2} fill={tintOf(topic)} />
        <Circle cx={d / 2} cy={d / 2} r={d / 2} fill={`url(#${id})`} />
        <Circle cx={d / 2} cy={d / 2} r={d / 2 - 0.75} fill="none" stroke="rgba(255,255,255,0.95)" strokeWidth={1.5} />
      </Svg>
      <TopicIcon topic={topic || ''} size={Math.round(d * 0.4)} c={ICON} />
    </View>
  );
}

const s = StyleSheet.create({
  head: { height: HEAD_H, flexDirection: 'row', alignItems: 'center', gap: 8 },
  headSide: { width: 116, flexDirection: 'row', alignItems: 'center' },
  headRight: { justifyContent: 'flex-end' },
  headMuted: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: '#5A616E' } as any,
  headName: { flex: 1, fontSize: 15, lineHeight: 20, color: INK, textAlign: 'center' } as any,
  /**
   * «ВСЕ ТЕМЫ» — ЯВНАЯ КНОПКА, а не подпись (владелец: «кнопочка назад должна быть очень явная»).
   * Белая плотная пилюля 36 в высоту со стрелкой 18: её видно сразу, и попасть в неё легко. Вторая
   * дорога назад — стрелка в шапке экрана и системный «назад»: внутри темы они тоже ведут к темам.
   */
  backPill: {
    height: 36, paddingLeft: 8, paddingRight: 14, borderRadius: 18, flexDirection: 'row', alignItems: 'center', gap: 2,
    backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: 'rgba(24,27,34,0.08)',
    shadowColor: '#0A0A14', shadowOpacity: 0.08, shadowRadius: 10, shadowOffset: { width: 0, height: 3 },
  },
  backText: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 18, color: INK, flexShrink: 1 } as any,
  count: {
    height: 28, paddingHorizontal: 12, borderRadius: 14, justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.6)', borderWidth: 1, borderColor: '#FFFFFF',
  },
  countOn: { backgroundColor: 'rgba(255,56,92,0.10)', borderColor: 'rgba(255,56,92,0.18)' },
  countText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: '#5A616E' } as any,
  countTextOn: { color: CORAL },
  pressed: { transform: [{ scale: 0.96 }] },

  abs: { position: 'absolute' },
  hub: {
    position: 'absolute', width: HUB_D, height: HUB_D, borderRadius: HUB_D / 2,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.9)', borderWidth: 1, borderColor: '#FFFFFF',
    shadowColor: CORAL, shadowOpacity: 0.16, shadowRadius: 18, shadowOffset: { width: 0, height: 6 },
  },
  topic: {
    alignItems: 'center', justifyContent: 'center', overflow: 'visible',
    shadowColor: '#0A0A14', shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 5 },
  },
  /** Пустой спутник — едва заметная точка: корона видна, только когда в ней что-то зажглось. */
  /** Значок «другие» на пузыре темы: белый кружок со стрелками в правом нижнем углу. */
  shuffleBadge: {
    position: 'absolute', right: -4, bottom: -4, width: 24, height: 24, borderRadius: 12,
    backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center',
    shadowColor: '#0A0A14', shadowOpacity: 0.12, shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
  },
  sat: {
    position: 'absolute', width: SAT_D, height: SAT_D, borderRadius: SAT_D / 2,
    backgroundColor: 'rgba(24,27,34,0.10)', transform: [{ scale: 0.75 }],
  },
  satOn: { backgroundColor: CORAL, transform: [{ scale: 1 }] },
  more: {
    position: 'absolute', minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 4,
    backgroundColor: CORAL, alignItems: 'center', justifyContent: 'center',
  },
  moreText: { fontFamily: font.textSemibold, fontSize: 10, lineHeight: 12, color: '#FFFFFF' } as any,
  nodeLabel: {
    position: 'absolute', left: 0, textAlign: 'center',
    fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: INK,
  } as any,

  leaf: {
    flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: LEAF_PAD,
    backgroundColor: 'rgba(255,255,255,0.92)', borderWidth: 1, borderColor: '#FFFFFF',
    shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 4 },
  },
  /** Выбранное — фирменный коралл с тем же свечением, что у главных кнопок. */
  leafOn: {
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: LEAF_PAD,
    backgroundColor: CORAL, borderWidth: 1, borderColor: 'rgba(255,255,255,0.35)',
    shadowColor: CORAL, shadowOpacity: 0.32, shadowRadius: 12, shadowOffset: { width: 0, height: 5 },
  },
  leafText: { fontFamily: font.textMedium, textAlign: 'center', color: INK } as any,
  leafTextOn: { color: '#FFFFFF' },
});
