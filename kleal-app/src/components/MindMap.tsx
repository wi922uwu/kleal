/**
 * Карта интересов: восемь кустов, в которые ЗАХОДЯТ.
 *
 * ПОЧЕМУ НЕ ОДНО ПЛОТНОЕ ПОЛЕ. Раньше все девяносто занятий лежали разом. Арифметика этого не
 * прощает: на поле 330×430 при девяноста восьми кружках на каждый приходится квадрат 38×38 точек,
 * а палец накрывает 44×44 — касание физически перекрывает больше одной цели, и средний спутник в
 * двадцать точек вдвое меньше минимума, который рекомендуют и Apple, и Google (48). Отсюда обе
 * жалобы сразу: «за малейшее движение пролистывает десяток» и «палец закрывает то, куда жмёшь».
 * Лупа этого не лечит — она показывает, что под пальцем, уже ПОСЛЕ того, как ты туда попал.
 *
 * Поэтому шагов два. Сверху — восемь категорий по семьдесят шесть точек: промахнуться нельзя.
 * Нажал — заходишь внутрь, и то же поле занимает один куст: два десятка занятий по сорок-шестьдесят
 * точек каждое. Целей стало меньше, а каждая — крупнее пальца.
 *
 * ЗАЩЁЛКИ ВМЕСТО СКОЛЬЖЕНИЯ. Внутри куста выделенное держится за пузырь и не перескакивает на
 * соседа, пока тот не окажется заметно ближе (гистерезис). Палец дрожит — выделение стоит; повёл
 * осознанно — щёлкнуло и перешло. Так устроен барабан выбора в iOS, и по той же причине: чтобы
 * движение считалось шагами, а не сантиметрами.
 *
 * ЛУПА ОСТАЛАСЬ, НО СТАЛА ПОДТВЕРЖДЕНИЕМ, А НЕ СПОСОБОМ ПРОЧИТАТЬ. Цели теперь и так читаются;
 * увеличение говорит «вот это ты сейчас возьмёшь». Отсюда скромный пик.
 *
 * ДВИЖОК ТОТ ЖЕ, ЧТО БЫЛ, и он взят у двух работ. Раскладка кустов — Gates Foundation bubbles
 * (vlandham): притяжение к центру группы и отталкивание по площади. Отрисовка и ход кадров —
 * JS Interactive Canvas Bubbles (codepen aashish2058): всё поле в ОДИН холст, а размеры и места в
 * каждом кадре догоняют цель. Поэтому здесь один <Svg> на всё, а кружки внутри получают новые
 * cx/cy/r напрямую через setNativeProps, минуя React.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { PanResponder, Pressable, StyleSheet, Text, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { buildMap, ROOT_TONE, type Bubble } from '../mindmap';
import { color, deckTone, font, radius as rad } from '../theme';
import { T, useLang } from '../i18n';
import { hTap, hCommit } from '../haptics';

/** Во сколько раз вырастает то, что под пальцем. Скромно: это подтверждение, а не чтение. */
const PEAK = 1.55;
/** Докуда достаёт увеличение. Соразмерно пузырю: растёт то, на чём палец. */
const REACH_ZOOM = 46;
/** Насколько сосед должен быть ближе, чтобы выделение к нему перескочило. Это и есть защёлка. */
const HOLD = 16;
/** Насколько кадр приближает значение к цели. */
const EASE = 0.3;
/** Тихое дыхание поля. */
const DRIFT = 0.5;
/** Короткий прирост в момент выбора. */
const POP = 0.45;
/** Насколько палец может сползти, и это всё ещё тап. */
const TAP_SLOP = 6;
/** Высота шапки в раскрытом кусте. */
const HEAD_H = 34;

type Node = {
  key: string;
  label: string;
  root: string;
  kind: 'root' | 'leaf';
  hx: number; hy: number; hr: number;
  x: number; y: number; r: number;
  ph: number; pop: number;
};

/** Золотой угол: раскладывает N точек по полю без рядов и без сгущений. */
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

export function MindMap({ width, height, selected, onToggle, onDrag }: {
  width: number;
  height: number;
  selected: string[];
  onToggle: (key: string) => void;
  /** Остановить ленту чата на время жеста: иначе она едет под пальцем. */
  onDrag?: (dragging: boolean) => void;
}) {
  const lang = useLang();
  const all = useMemo(() => buildMap(width, height), [width, height, lang]);
  /** В какой куст зашли. null — обзор из восьми категорий. */
  const [open, setOpen] = useState<string | null>(null);

  const roots = useMemo(() => all.filter((b) => b.kind === 'root'), [all]);
  const openRoot = useMemo(() => roots.find((r) => r.key === open) || null, [roots, open]);
  const leaves = useMemo(
    () => (open ? all.filter((b) => b.kind === 'leaf' && b.root === open) : []),
    [all, open]
  );

  /** Сколько занятий уже отмечено в каждом кусте — это и есть подпись на категории. */
  const picked = useMemo(() => {
    const m: Record<string, number> = {};
    for (const b of all) if (b.kind === 'leaf' && selected.includes(b.key)) m[b.root] = (m[b.root] || 0) + 1;
    return m;
  }, [all, selected]);

  const canvasH = open ? height - HEAD_H : height;

  /*
    РАСКЛАДКА. В обзоре берём центры категорий как есть — они уже разложены по спирали Фибоначчи в
    mindmap.ts — и увеличиваем сами кружки. В кусте раскладываем его занятия по золотому углу на
    всё поле, а радиус считаем от их числа: чем меньше занятий, тем крупнее каждое, и наоборот.
    Нижний предел — двадцать точек радиуса, то есть сорок диаметра: это уже палец.
  */
  const view = useMemo<Node[]>(() => {
    const mk = (b: Bubble, hx: number, hy: number, hr: number, i: number): Node => ({
      key: b.key, label: b.label, root: b.root, kind: b.kind,
      hx, hy, hr, x: hx, y: hy, r: 0, ph: (i % 17) * 0.37 + (i % 5) * 1.1, pop: 0,
    });
    if (!open) return roots.map((b, i) => mk(b, b.x * width, b.y * canvasH, 38, i));
    const n = leaves.length || 1;
    const r = Math.max(20, Math.min(30, Math.sqrt((width * canvasH * 0.3) / (n * Math.PI))));
    const cx = width / 2;
    const cy = canvasH / 2;
    const span = Math.min(width, canvasH) / 2 - r - 6;
    return leaves.map((b, i) => {
      const a = i * GOLDEN;
      const d = span * Math.sqrt((i + 0.5) / n);
      return mk(b, cx + d * Math.cos(a), cy + d * Math.sin(a), r, i);
    });
  }, [open, roots, leaves, width, canvasH]);

  const nodes = useRef<Node[]>([]);
  const circles = useRef<any[]>([]);
  useMemo(() => { nodes.current = view.map((n) => ({ ...n })); circles.current = []; }, [view]);

  const finger = useRef({ x: -1, y: -1, on: false });
  const frame = useRef<number | null>(null);
  const beat = useRef(0);
  const lastBuzz = useRef(0);
  /** Что сейчас выделено. Держится защёлкой, а не пересчитывается заново каждый кадр. */
  const held = useRef<string>('');
  const [hot, setHot] = useState<Node | null>(null);

  const tick = () => {
    const f = finger.current;
    const t = (beat.current += 0.018);
    const list = nodes.current;

    /*
      ЗАЩЁЛКА. Ближайший к пальцу считается честно, но выделение переходит к нему, только если он
      ближе удерживаемого на HOLD точек. Без этого запаса на границе двух пузырей выделение
      трепещет между ними, и каждое дрожание пальца отзывается щелчком.
    */
    if (f.on) {
      let bestKey = '';
      let bestD = Infinity;
      let heldD = Infinity;
      for (const n of list) {
        const d = Math.hypot(f.x - n.hx, f.y - n.hy);
        if (n.key === held.current) heldD = d;
        if (d < bestD) { bestD = d; bestKey = n.key; }
      }
      if (bestKey && bestKey !== held.current && bestD + HOLD < heldD) {
        held.current = bestKey;
        const now = Date.now();
        if (now - lastBuzz.current > 45) { lastBuzz.current = now; hTap(); }
        setHot(list.find((n) => n.key === bestKey) || null);
      }
    }

    for (let i = 0; i < list.length; i++) {
      const n = list[i];
      let zm = 0;
      if (f.on) {
        const d = Math.hypot(f.x - n.x, f.y - n.y);
        if (d < REACH_ZOOM) { const k = 1 - d / REACH_ZOOM; zm = k * k * k; }
        // Выделенное поднято до полного увеличения, даже если палец сполз: защёлка держит и вид.
        if (n.key === held.current) zm = Math.max(zm, 1);
      }
      if (n.pop > 0.01) n.pop *= 0.82; else n.pop = 0;
      const tr = n.hr * (1 + zm * (PEAK - 1) + n.pop * POP);
      const tx = n.hx + Math.cos(t + n.ph) * DRIFT;
      const ty = n.hy + Math.sin(t * 0.9 + n.ph * 1.3) * DRIFT;
      const dr = tr - n.r, dx = tx - n.x, dy = ty - n.y;
      if (Math.abs(dr) < 0.05 && Math.abs(dx) < 0.05 && Math.abs(dy) < 0.05) continue;
      n.r += dr * EASE; n.x += dx * EASE; n.y += dy * EASE;
      circles.current[i]?.setNativeProps({ cx: n.x, cy: n.y, r: n.r });
    }
    frame.current = requestAnimationFrame(tick);
  };
  const wake = () => { if (frame.current == null) frame.current = requestAnimationFrame(tick); };
  useEffect(() => {
    wake();
    return () => { if (frame.current != null) cancelAnimationFrame(frame.current); };
  }, []);

  const openRef = useRef(open); openRef.current = open;
  const toggle = useRef(onToggle); toggle.current = onToggle;
  const drag = useRef(onDrag); drag.current = onDrag;
  const from = useRef({ x: 0, y: 0 });
  const enter = useRef((k: string) => { setOpen(k); });

  /** Что под пальцем — по ВИДИМОМУ месту и размеру. */
  const at = (x: number, y: number): Node | null => {
    let best: Node | null = null;
    let bestD = Infinity;
    for (const n of nodes.current) {
      const d = Math.hypot(x - n.x, y - n.y);
      if (d <= n.r + 10 && d < bestD) { bestD = d; best = n; }
    }
    return best;
  };

  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: (e) => {
        const { locationX: x, locationY: y } = e.nativeEvent;
        from.current = { x, y };
        finger.current = { x, y, on: true };
        const n = at(x, y);
        held.current = n ? n.key : '';
        setHot(n);
        drag.current?.(true);
        wake();
      },
      onPanResponderMove: (e) => {
        finger.current = { x: e.nativeEvent.locationX, y: e.nativeEvent.locationY, on: true };
        wake();
      },
      onPanResponderRelease: () => {
        /*
          БЕРЁМ ТО, ЧТО ВЫДЕЛЕНО, А НЕ ТО, ЧТО ПОД ПАЛЬЦЕМ. Это и есть ответ на «палец закрывает
          то, куда жмёшь»: выделенное видно рядом с пальцем и подписано, и именно оно и запишется.
        */
        const k = held.current;
        const n = k ? nodes.current.find((x) => x.key === k) : null;
        if (n) {
          n.pop = 1;
          hCommit();
          if (n.kind === 'root') enter.current(n.key); else toggle.current(n.key);
        }
        held.current = '';
        setHot(null);
        finger.current = { x: -1, y: -1, on: false };
        drag.current?.(false);
        wake();
      },
      onPanResponderTerminate: () => {
        held.current = '';
        setHot(null);
        finger.current = { x: -1, y: -1, on: false };
        drag.current?.(false);
        wake();
      },
    })
  ).current;

  return (
    <View style={{ width, alignSelf: 'center' }}>
      {open ? (
        <View style={s.head}>
          <Pressable accessibilityRole="button" onPress={() => { hTap(); setOpen(null); }} style={s.back}>
            <Text style={s.backText}>‹  {T('Все темы', 'All topics')}</Text>
          </Pressable>
          <Text style={s.headName} numberOfLines={1}>{openRoot?.label || ''}</Text>
        </View>
      ) : null}

      <View style={{ width, height: canvasH }} {...pan.panHandlers}>
        <Svg width={width} height={canvasH}>
          {view.map((n, i) => {
            const t = deckTone[ROOT_TONE[n.root] || 'slate'];
            const on = selected.includes(n.key);
            return (
              <Circle
                key={n.key}
                ref={(el: any) => { circles.current[i] = el; }}
                cx={n.hx} cy={n.hy} r={0}
                fill={on ? color.primary : t.wash}
                stroke={on ? color.primary : t.halo}
                strokeWidth={n.kind === 'root' ? 2 : 1.5}
              />
            );
          })}
        </Svg>

        {/* Категории подписаны всегда, и рядом — сколько из них уже отмечено. */}
        {!open && view.map((n) => (
          <View key={`l-${n.key}`} pointerEvents="none"
                style={[s.rootWrap, { left: n.hx - 48, top: n.hy + n.hr + 4 }]}>
            <Text numberOfLines={1} style={s.rootLabel}>{n.label}</Text>
            {picked[n.key] ? <Text style={s.rootCount}>{picked[n.key]}</Text> : null}
          </View>
        ))}

        {/*
          ИМЯ ВЫДЕЛЕННОГО ВСТАЁТ НАД ТОЧКОЙ КАСАНИЯ. Палец закрывает ровно то, что увеличивает, —
          лечится так же, как в iOS у выделения текста: нужное выносят выше пальца.
        */}
        {hot ? (
          <View pointerEvents="none"
                style={[s.plate, { left: Math.max(4, Math.min(width - 116, hot.hx - 56)),
                                   top: Math.max(2, hot.hy - hot.hr * PEAK - 26) }]}>
            <Text numberOfLines={1} style={s.plateText}>{hot.label}</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  head: { height: HEAD_H, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 2 },
  back: { paddingVertical: 4, paddingRight: 6 },
  backText: { fontFamily: font.textMedium, fontSize: 13, color: color.primary } as any,
  headName: { flex: 1, fontFamily: font.textMedium, fontSize: 15, color: color.fg } as any,
  rootWrap: { position: 'absolute', width: 96, alignItems: 'center' },
  rootLabel: {
    width: 96, textAlign: 'center',
    fontFamily: font.textMedium, fontSize: 12, lineHeight: 15, color: color.fg,
  } as any,
  rootCount: {
    marginTop: 1, fontFamily: font.textMedium, fontSize: 11, lineHeight: 13, color: color.primary,
  } as any,
  plate: {
    position: 'absolute', width: 112, height: 22, borderRadius: rad.full,
    backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8,
  },
  plateText: {
    fontFamily: font.textMedium, fontSize: 12, lineHeight: 14,
    color: color.onPrimary, textAlign: 'center',
  } as any,
});
