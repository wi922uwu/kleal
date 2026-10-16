/**
 * Интересы v2 — двойная спираль, которую листают (владелец, 27.09). v1 — карта MindMap — не
 * тронута и включается переключателем на шаге; спираль принимает ровно те же входы (выбранное и
 * выбор по тапу), поэтому корзина, кнопки и «Добавить своё» под ней работают без изменений.
 *
 * Геометрия — src/helix.ts, под тестом tools/helix_test.js (все 412 занятий, ни одного наложения
 * при любом повороте, ни одного выхода за край при ширине 320–430).
 *
 * ПЯТАЯ РЕДАКЦИЯ — ВРАЩАЕТСЯ И НЕ ЛАГАЕТ. История требований владельца:
 *   «убери соединения между трубками; трубка целая, без анимации того, что она заполняется; это
 *   лагает» → «но она должна крутиться по оси».
 * Как сделано:
 *   • перекладин и бусин нет; трубка ЦЕЛАЯ — одна толщина и цвет по всей длине (передняя и задняя
 *     половины витка различаются только порядком отрисовки, чтобы на пересечении сверху была
 *     ближняя нить);
 *   • НИТИ НАРИСОВАНЫ ОДИН РАЗ. Поворот спирали вокруг оси на φ — это сдвиг её рисунка вдоль оси
 *     на φ/K, поэтому вращение — нативный сдвиг слоя нитей по вертикали (по модулю витка).
 *     Кривые на кадр не пересчитываются вовсе — прошлая «вращающаяся» редакция пересобирала 13
 *     путей SVG каждый кадр, отсюда и был лаг;
 *   • на кадр двигаются только пузыри (~25 у окна) — вбок вслед за своей нитью, с размером и тоном
 *     подписи по глубине: это простые сдвиги на нативном потоке;
 *   • крутится сама (виток за 30 с) и быстрее при листании; ЗАМИРАЕТ под пальцем в момент
 *     касания, чтобы пузырь не уехал из-под него, и трогается через 1,5 с после.
 *
 * Цвета — только наши: нить A — коралл главных кнопок, нить B — светлый конец нашего кораллового
 * градиента (brandSoft); блик — непрозрачный светлый коралл. Пузыри непрозрачные: через
 * полупрозрачные трубка «перечёркивала» подпись.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import Animated, {
  Easing, cancelAnimation, interpolateColor, runOnJS, useAnimatedRef, useAnimatedScrollHandler,
  useAnimatedStyle, useReducedMotion, useSharedValue, withRepeat, withTiming, type SharedValue,
} from 'react-native-reanimated';
import Svg, { Defs, LinearGradient, Path, Rect, Stop } from 'react-native-svg';
import MaskedView from '@react-native-masked-view/masked-view';
import { mapPools } from '../mindmap';
import { useLang } from '../i18n';
import { hTap, hTick } from '../haptics';
import { color, displayFamily, font } from '../theme';
import {
  K, PILL_H, PILL_MAX_W, TURN, TWIST, amplitude, angle, depth, layoutHelix, scaleAt, type HelixItem,
} from '../helix';

const CORAL = '#FF385C';
const SOFT = color.brandSoft;
const INK = '#181B22';
const MUTED = '#5A616E';
/** Толщина стеклянной трубки. */
const GLASS_W = 11;
/** Окно ленты, в котором живут пузыри: видимое поле ± запас. Пересчитывается раз в BUCKET точек. */
const BUCKET = 240;
const MARGIN = 420;
const TABS_H = 44;
/** Виток в покое — 30 секунд. */
const IDLE_MS = 30000;
/** Пауза после касания, прежде чем спираль снова поплывёт. */
const RESUME_MS = 1500;

export function InterestHelix({ width: widthProp, height, selected, onToggle, onDrag }: {
  width?: number;
  /** Высота всего виджета вместе со строкой тем. */
  height: number;
  selected: string[];
  onToggle: (key: string) => void;
  /** Пока палец листает спираль, лента чата стоит (иначе на Android её забирает внешний скролл). */
  onDrag?: (dragging: boolean) => void;
  /** Входы карты v1, которых у спирали нет: вложенных тем здесь нет, «назад» не нужен. */
  backSignal?: number;
  onTopicChange?: (open: boolean) => void;
}) {
  const lang = useLang();
  const reduced = useReducedMotion();
  const { width: winW } = useWindowDimensions();
  const [boxW, setBoxW] = useState(0);
  const w = widthProp || boxW || winW - 40;
  const fieldH = height - TABS_H;
  const R = amplitude(w);
  const cx = w / 2;

  const pools = useMemo(() => mapPools(), [lang]); // eslint-disable-line react-hooks/exhaustive-deps
  const { items, height: contentH, topicY } = useMemo(() => layoutHelix(pools.roots, pools.leaves), [pools]);
  const topics = pools.roots;
  const starts = useMemo(() => topics.map((t) => topicY[t.key]), [topics, topicY]);
  const picked = useMemo(() => new Set(selected), [selected]);
  const pickedIn = useMemo(() => {
    const m: Record<string, number> = {};
    for (const it of items) if (it.kind === 'leaf' && picked.has(it.key)) m[it.topic] = (m[it.topic] || 0) + 1;
    return m;
  }, [items, picked]);

  // ===== вращение: само в покое, быстрее при листании, стоп под пальцем
  const scroll = useSharedValue(0);
  const spin = useSharedValue(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idle = useCallback(() => {
    if (reduced) return;
    const c = spin.value;
    // withRepeat начинает каждый круг заново с `c`: угол периодичен, скачка не видно.
    spin.value = withRepeat(withTiming(c + 2 * Math.PI, { duration: IDLE_MS, easing: Easing.linear }), -1, false);
  }, [reduced, spin]);
  const hold = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    cancelAnimation(spin);
  }, [spin]);
  const release = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(idle, RESUME_MS);
  }, [idle]);
  useEffect(() => {
    idle();
    return () => { if (timer.current) clearTimeout(timer.current); cancelAnimation(spin); };
  }, [idle, spin]);

  // ===== окно ленты и текущая тема: JS узнаёт только о смене окна или темы
  const [bucket, setBucket] = useState(0);
  const [topic, setTopic] = useState(0);
  const bucketSV = useSharedValue(0);
  const topicSV = useSharedValue(0);
  const dragJS = (on: boolean) => { onDrag?.(on); if (on) hold(); else release(); };
  const topicJS = (t: number) => { setTopic(t); hTick(); };
  const onScroll = useAnimatedScrollHandler({
    onScroll: (e) => {
      const y = e.contentOffset.y;
      scroll.value = y;
      const b = Math.floor(y / BUCKET);
      if (b !== bucketSV.value) { bucketSV.value = b; runOnJS(setBucket)(b); }
      // Текущая тема — последняя, чьё начало выше трети поля.
      let t = 0;
      for (let i = 0; i < starts.length; i++) if (starts[i] <= y + fieldH / 3) t = i;
      if (t !== topicSV.value) { topicSV.value = t; runOnJS(topicJS)(t); }
    },
    onBeginDrag: () => { runOnJS(dragJS)(true); },
    onEndDrag: () => { runOnJS(dragJS)(false); },
  }, [starts, fieldH]);

  const lo = bucket * BUCKET - MARGIN;
  const hi = bucket * BUCKET + fieldH + MARGIN;
  const visible = useMemo(() => items.filter((it) => it.y >= lo && it.y <= hi), [items, lo, hi]);

  /*
    СЛОЙ НИТЕЙ. Верх выровнен по витку (кратен TURN), поэтому фаза рисунка совпадает с фазой ленты,
    и один и тот же нарисованный слой годится для любого окна — переставляется только его `top`.
    Высота покрывает окно, запас окна и один виток на сдвиг.
  */
  const layerTop = Math.floor((bucket * BUCKET - TURN) / TURN) * TURN;
  const layerH = BUCKET + fieldH + 2 * TURN + 16;
  const layerStyle = useAnimatedStyle(() => {
    const phi = spin.value + scroll.value * K * TWIST;
    let t = (-phi / K) % TURN;
    if (t < 0) t += TURN;
    return { transform: [{ translateY: t }] };
  });

  const listRef = useAnimatedRef<Animated.ScrollView>();
  const atStart = useRef(false);
  const jump = (i: number) => {
    hTap();
    (listRef.current as any)?.scrollTo?.({ y: Math.max(0, starts[i] - 8), animated: true });
  };
  const tabsRef = useRef<ScrollView>(null);
  const tabX = useRef<number[]>([]);
  // Строка тем доезжает до текущей: при листании спирали видно, в какой теме ты сейчас.
  useEffect(() => {
    const x = tabX.current[topic];
    if (x != null) tabsRef.current?.scrollTo?.({ x: Math.max(0, x - 24), animated: true });
  }, [topic]);

  return (
    <View style={{ height }} onLayout={(e) => { const v = Math.round(e.nativeEvent.layout.width); if (v && v !== boxW) setBoxW(v); }}>
      {/*
        СТРОКА ТЕМ — текстом, без плашек и цветных значков: активная темнее и с коралловой чертой
        снизу, как полоски листания на вступлении.
      */}
      <ScrollView
        ref={tabsRef}
        horizontal
        showsHorizontalScrollIndicator={false}
        style={s.tabs}
        contentContainerStyle={s.tabsRow}
        testID="helix-topics"
      >
        {topics.map((t, i) => {
          const on = i === topic;
          const n = pickedIn[t.key] || 0;
          return (
            <Pressable key={t.key} accessibilityRole="tab" accessibilityState={{ selected: on }}
                       onLayout={(e) => { tabX.current[i] = e.nativeEvent.layout.x; }}
                       onPress={() => jump(i)} hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
                       style={s.tab}>
              <View style={s.tabLine}>
                <Text style={[s.tabText, on && s.tabTextOn]} numberOfLines={1}>{t.label}</Text>
                {n ? <Text style={s.tabCount}>{n}</Text> : null}
              </View>
              <View style={[s.tabBar, on && s.tabBarOn]} />
            </Pressable>
          );
        })}
      </ScrollView>

      {/*
        КРАЯ — ПРОЗРАЧНОСТЬЮ, А НЕ КРАСКОЙ (владелец, 28.09, снимок с телефона). Цвет подложки,
        наплывавший сверху и снизу, на телефоне читался светлыми плашками: фон там — живое розовое
        видео, а кремовый я подбирал на симуляторе, где видео не играло. Теперь всё поле спирали
        под маской: у краёв оно само становится прозрачным, и сквозь него виден настоящий фон.
      */}
      <MaskedView
        style={[s.field, { height: fieldH }]}
        maskElement={<FadeMask w={w} h={fieldH} />}
        onTouchStart={hold} onTouchEnd={release} onTouchCancel={release}
      >
        <Animated.ScrollView
          ref={listRef}
          /*
            ЛЕНТА ОТКРЫВАЕТСЯ С НАЧАЛА. Открывалась с середины «Спорта» (симулятор и телефон):
            iOS переиспользует уже созданную прокручиваемую область вместе с её старой позицией.
            Начальная позиция задана явно и повторена прокруткой в начало при первом замере.
          */
          contentOffset={{ x: 0, y: 0 }}
          onLayout={() => {
            if (atStart.current) return;
            atStart.current = true;
            (listRef.current as any)?.scrollTo?.({ y: 0, animated: false });
          }}
          onScroll={onScroll}
          scrollEventThrottle={16}
          showsVerticalScrollIndicator={false}
          nestedScrollEnabled
          onMomentumScrollEnd={() => dragJS(false)}
          style={StyleSheet.absoluteFill}
          contentContainerStyle={{ height: contentH }}
          testID="helix-list"
        >
          <Animated.View pointerEvents="none" style={[{ position: 'absolute', left: 0, top: layerTop, width: w, height: layerH }, layerStyle]}>
            <Pattern w={w} h={layerH} cx={cx} R={R} />
          </Animated.View>
          {visible.map((it) => it.kind === 'head'
            ? <Head key={'h:' + it.topic} item={it} w={w} lang={lang} />
            : <Pill key={it.key} item={it} w={w} R={R} scroll={scroll} spin={spin}
                    on={picked.has(it.key)} onToggle={onToggle} />)}
        </Animated.ScrollView>
      </MaskedView>
    </View>
  );
}

/**
 * Рисунок двух нитей высотой h с фазой 0 у верхнего края. Строится ОДИН раз (memo) — вращение
 * делает сдвиг слоя, а не перерисовка.
 *
 * НИТИ — ЖИДКОЕ СТЕКЛО (владелец, 28.09, вариант 1 из шести). Трубка — это стекло нашей системы
 * (как у стеклянных кнопок): полупрозрачное белое тело с тонкой тёмной кромкой, внутри светится
 * коралловая сердцевина (у второй нити — светлый коралл), сверху-слева — яркий блик. Каждая нить —
 * ОДИН непрерывный путь на слой: у стекла нет «передней и задней половины» с разной толщиной, и на
 * пересечении задняя нить честно просвечивает сквозь переднюю, как сквозь стекло.
 */
const Pattern = React.memo(function Pattern({ w, h, cx, R }: { w: number; h: number; cx: number; R: number }) {
  const d = useMemo(() => [0, 1].map((st) => {
    let out = '';
    for (let y = 0; y <= h; y += 4) {
      const x = cx + R * Math.sin(y * K + st * Math.PI);
      out += (y ? 'L' : 'M') + x.toFixed(1) + ' ' + y + ' ';
    }
    return out;
  }), [h, cx, R]);
  const glass = (path: string, core: string, k: string) => (
    <React.Fragment key={k}>
      {/* кромка — чтобы стекло читалось на светлом фоне */}
      <Path d={path} stroke="#181B22" strokeOpacity={0.07} strokeWidth={GLASS_W + 2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {/* тело: полупрозрачное белое стекло */}
      <Path d={path} stroke="#FFFFFF" strokeOpacity={0.62} strokeWidth={GLASS_W} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {/* сердцевина, которая светится сквозь стекло */}
      <Path d={path} stroke={core} strokeOpacity={0.9} strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {/* блик сверху-слева */}
      <Path d={path} stroke="#FFFFFF" strokeOpacity={0.95} strokeWidth={1.6} fill="none" strokeLinecap="round" strokeLinejoin="round"
            transform="translate(-2.6,-1.8)" />
    </React.Fragment>
  );
  return (
    <Svg width={w} height={h}>
      {glass(d[1], SOFT, 'b')}
      {glass(d[0], CORAL, 'a')}
    </Svg>
  );
});

/**
 * Маска поля: непрозрачная середина, у верхнего и нижнего края — плавный уход в прозрачность на
 * EDGE точек. Маска смотрит только на прозрачность: цвет — любой.
 */
const EDGE = 56;
function FadeMask({ w, h }: { w: number; h: number }) {
  const a = Math.min(0.45, EDGE / Math.max(1, h));
  return (
    <Svg width={w} height={h}>
      <Defs>
        <LinearGradient id="helixMask" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#000" stopOpacity={0} />
          <Stop offset={String(a)} stopColor="#000" stopOpacity={1} />
          <Stop offset={String(1 - a)} stopColor="#000" stopOpacity={1} />
          <Stop offset="1" stopColor="#000" stopOpacity={0} />
        </LinearGradient>
      </Defs>
      <Rect x={0} y={0} width={w} height={h} fill="url(#helixMask)" />
    </Svg>
  );
}

/** Заголовок темы на оси: неподвижная тихая метка, спираль проходит за ней. */
function Head({ item, w, lang }: { item: Extract<HelixItem, { kind: 'head' }>; w: number; lang: string }) {
  return (
    <View pointerEvents="none" style={[s.row, { top: item.y - 16, width: w, height: 32 }]}>
      <View style={s.head}>
        <Text style={[s.headText, { fontFamily: displayFamily(lang) }]} numberOfLines={1}>{item.label}</Text>
      </View>
    </View>
  );
}

/**
 * Пузырь занятия на нити: белый, непрозрачный; выбранный — коралловый с галочкой. На кадр
 * меняется только сдвиг вбок, размер и тон подписи по глубине — на нативном потоке.
 */
function Pill({ item, w, R, scroll, spin, on, onToggle }: {
  item: Extract<HelixItem, { kind: 'leaf' }>; w: number; R: number;
  scroll: SharedValue<number>; spin: SharedValue<number>; on: boolean; onToggle: (k: string) => void;
}) {
  const box = useAnimatedStyle(() => {
    const th = angle(item.y, scroll.value, item.strand, spin.value);
    return { transform: [{ translateX: R * Math.sin(th) }, { scale: scaleAt(th) }] };
  }, [item.y, item.strand, R]);
  const ink = useAnimatedStyle(() => {
    if (on) return { color: '#FFFFFF' };
    const d = depth(angle(item.y, scroll.value, item.strand, spin.value));
    return { color: interpolateColor(d, [0.25, 0.75], [MUTED, INK]) };
  }, [item.y, item.strand, on]);
  return (
    <Animated.View pointerEvents="box-none" style={[s.row, { top: item.y - PILL_H / 2, width: w, height: PILL_H }, box]}>
      <Pressable
        accessibilityRole="checkbox"
        accessibilityState={{ checked: on }}
        accessibilityLabel={item.label}
        onPress={() => { hTap(); onToggle(item.key); }}
        hitSlop={{ top: 6, bottom: 6, left: 4, right: 4 }}
        style={({ pressed }) => [s.pill, on ? s.pillOn : s.pillOff, pressed && s.pressed]}
      >
        {on ? <Check /> : null}
        <Animated.Text style={[s.pillText, on && s.pillTextOn, ink]} numberOfLines={1}>{item.label}</Animated.Text>
      </Pressable>
    </Animated.View>
  );
}

function Check() {
  return (
    <Svg width={14} height={14} viewBox="0 0 24 24">
      <Path d="M5 12.5l4.5 4.5L19 7.5" stroke="#FFFFFF" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </Svg>
  );
}

const s = StyleSheet.create({
  tabs: { height: TABS_H, flexGrow: 0 },
  tabsRow: { gap: 20, alignItems: 'stretch', paddingHorizontal: 4 },
  tab: { justifyContent: 'center', gap: 6 },
  tabLine: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  tabText: { fontFamily: font.textMedium, fontSize: 14, lineHeight: 18, color: MUTED } as any,
  tabTextOn: { fontFamily: font.textSemibold, color: INK } as any,
  tabCount: { fontFamily: font.textSemibold, fontSize: 12, lineHeight: 16, color: CORAL } as any,
  /** Черта под темой — как полоски листания вступления: 2 точки, у активной коралловая. */
  tabBar: { height: 2, borderRadius: 1, backgroundColor: 'transparent' },
  tabBarOn: { backgroundColor: CORAL },
  /** Поле обрезает слой нитей по краям (он выше окна на виток). */
  field: { marginTop: 4, overflow: 'hidden' },
  row: { position: 'absolute', left: 0, alignItems: 'center', justifyContent: 'center' },
  head: {
    height: 28, paddingHorizontal: 14, borderRadius: 14, justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.9)',
  },
  headText: { fontSize: 12, lineHeight: 16, color: CORAL, textTransform: 'uppercase', letterSpacing: 1.4 } as any,
  pill: {
    height: PILL_H, maxWidth: PILL_MAX_W, flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 16, borderRadius: PILL_H / 2,
  },
  pillOff: {
    backgroundColor: '#FFFFFF', borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(24,27,34,0.06)',
    ...Platform.select({
      ios: { shadowColor: '#0A0A14', shadowOpacity: 0.07, shadowRadius: 10, shadowOffset: { width: 0, height: 3 } },
      default: {},
    }),
  },
  /** Выбранное — фирменный коралл с тем же свечением, что у главных кнопок и выбранных пузырей v1. */
  pillOn: {
    paddingLeft: 12, backgroundColor: CORAL,
    ...Platform.select({
      ios: { shadowColor: CORAL, shadowOpacity: 0.35, shadowRadius: 12, shadowOffset: { width: 0, height: 5 } },
      default: {},
    }),
  },
  pillText: { flexShrink: 1, fontFamily: font.textMedium, fontSize: 14, lineHeight: 18, color: INK } as any,
  pillTextOn: { fontFamily: font.textSemibold, color: '#FFFFFF' } as any,
  pressed: { transform: [{ scale: 0.95 }] },
});
