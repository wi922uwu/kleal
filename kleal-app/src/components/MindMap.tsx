/**
 * Карта интересов: восемь цветных кустов и лупа под пальцем.
 *
 * ЗАЧЕМ ЛУПА. На поле полсотни пузырей; мелкие — двадцать два пикселя, и подпись в них не
 * помещается физически. Лупа не украшение, а единственный способ их прочитать: то, что под
 * пальцем, вырастает и показывает название. Карта при этом НЕ ездит — палец только приближает.
 *
 * ПОЧЕМУ ВСТРОЕННЫЙ Animated. Так сделаны все живые жесты проекта; вторая система анимации ради
 * одного экрана значит держать обе. Ограничение у встроенной одно, и оно здесь важно: она умеет
 * складывать, умножать и интерполировать, но НЕ умеет квадратный корень — честное расстояние до
 * пальца не посчитать. Поэтому масштаб — ПРОИЗВЕДЕНИЕ ДВУХ СПАДОВ: scale = fx(|dx|) × fy(|dy|).
 * Зона выходит скруглённо-квадратной, и это единственная неточность, которую человек не увидит.
 * Зато весь счёт уходит на нативный поток.
 *
 * ЖЕСТ КАРТА ЗАБИРАЕТ НА КАСАНИИ, А ТАП РАЗБИРАЕТ САМА. Сначала было наоборот, и проверка на
 * симуляторе показала: так лупа не включается ВООБЩЕ — лента чата уводит жест к себе с первого
 * касания, и вместо приближения экран прокручивался.
 *
 * ВИД. Первая версия была плоской: два цвета, белая подпись в семь пикселей, никакой глубины.
 *  — ЦВЕТ ЗНАЧИТ ТЕМУ (`ROOT_TONE`), спутник наследует тон категории — куст виден кустом, не
 *    приближая. Красный на невыбранном не появляется НИ РАЗУ: он занят состоянием «выбрано».
 *  — ГЛУБИНА ТА ЖЕ, ЧТО У КАРТОЧКИ КОЛОДЫ: заливка `wash`, два свечения по кривой BLOOM, светлая
 *    волосяная кромка и тень ЦВЕТОМ СВОЕГО ТОНА.
 *  — ПОДПИСЬ ТЁМНАЯ ПО БЛЕДНОМУ: белым по красному давало 3.83:1 при норме 4.5, тёмным по `wash`
 *    выходит больше 10:1. И тем же Geist, что весь экран, — у `type.caption` гарнитуры нет.
 */
import React, { useMemo, useRef } from 'react';
import { Animated, PanResponder, StyleSheet, Text, View } from 'react-native';
import Svg, { Defs, RadialGradient, Rect, Stop } from 'react-native-svg';
import { buildMap, ROOT_TONE, type Bubble } from '../mindmap';
import { color, deckTone, font, radius as rad, type } from '../theme';
import { useLang } from '../i18n';

/** Насколько вырастает пузырь ровно под пальцем. */
const PEAK = 2;
/**
 * Пик ОДНОЙ оси. Масштаб — произведение двух спадов, поэтому под пальцем перемножаются оба пика:
 * поставить сюда PEAK значит получить PEAK² на деле. Проверено на симуляторе — при 2.6 по оси
 * пузыри раздувались в шесть с лишним раз и слипались в пятно на пол-экрана.
 */
const AXIS_PEAK = Math.sqrt(PEAK);
/** Радиус действия лупы. Заметно меньше половины поля — иначе растёт сразу всё. */
const REACH = 78;
/** Насколько палец может сползти, и это всё ещё тап, а не ведение. */
const TAP_SLOP = 6;
/**
 * Запас при попадании. Считается от УВЕЛИЧЕННОГО размера: человек целится в тот круг, который
 * видит под лупой. Раньше запас брался от покоя, и вокруг видимого пузыря оставалось кольцо,
 * которое выглядело нажимаемым, а доставалось соседу.
 */
const TAP_SLACK = 8;

/**
 * ПЛАШКА С ИМЕНЕМ ВСТАЁТ НАД ПАЛЬЦЕМ, И ЭТО НЕ УКРАШЕНИЕ.
 *
 * У любого увеличения под пальцем есть врождённая беда: палец закрывает ровно то, что увеличивает.
 * Сообщено с телефона — «навожусь на интерес, он перекрывается пальцем». Увеличить сильнее не
 * помогает: чем крупнее круг, тем больше его закрыто.
 *
 * Лечится тем же способом, что в iOS у выделения текста: то, что нужно прочитать, выносят ВЫШЕ
 * точки касания. Поэтому имя того, что под пальцем, всплывает над ним отдельной плашкой, а сам
 * круг продолжает расти на месте — рост показывает, ГДЕ ты, плашка говорит, ЧТО это.
 */
/**
 * ПОДПИСЬ СПУТНИКА ЖИВЁТ НАД КРУГОМ, А НЕ В НЁМ.
 *
 * Сначала она стояла внутри — и приём сломался о собственную природу: палец закрывает ровно то,
 * что увеличивает. Сообщено с телефона: «навожусь на интерес, он перекрывается пальцем». Увеличить
 * сильнее не помогает — чем крупнее круг, тем больше его закрыто.
 *
 * Лечится так же, как в iOS у выделения текста: то, что нужно прочитать, выносят ВЫШЕ точки
 * касания. Круг растёт на месте и показывает, ГДЕ ты; имя всплывает над ним и говорит, ЧТО это.
 *
 * ПОЧЕМУ НЕ ОДНА ПЛАШКА, ЕДУЩАЯ ЗА ПАЛЬЦЕМ. Пробовал — так и было сделано, и это УБИЛО лупу.
 * Единственный способ узнать имя под пальцем — считать его в JS и класть в состояние, а `setState`
 * посреди жеста пересобирает поле, которое этим жестом владеет: касание есть, увеличения нет.
 * Здесь подписи у каждого своя, прозрачность берётся из того же нативного графа, что и масштаб, и
 * JS во время ведения по-прежнему молчит.
 *
 * Отступ и кегль заданы в размерах ПОКОЯ: плашка лежит внутри слота и растёт вместе с ним, значит
 * под лупой и поднимается выше, и читается крупнее — ровно тогда, когда это нужно.
 */
const PLATE_GAP = 5;
const PLATE_H = 11;

/** Ступени затухания свечения — те же пять, что у карточки колоды; разбор там же. */
const BLOOM: [string, number][] = [['0', 1], ['0.3', 0.88], ['0.55', 0.58], ['0.78', 0.24], ['1', 0]];

export function MindMap({ width, height, selected, onToggle, onDrag }: {
  width: number;
  height: number;
  selected: string[];
  onToggle: (key: string) => void;
  /** Остановить ленту чата на время жеста: иначе она едет под пальцем вместе с лупой. */
  onDrag?: (dragging: boolean) => void;
}) {
  // Раскладку считаем В ТЕХ ЖЕ ТОЧКАХ, в которых рисуем, — почему это важно, написано в mindmap.ts.
  /*
    ЯЗЫК В ЗАВИСИМОСТЯХ ОБЯЗАТЕЛЕН. Подписи собираются внутри `buildMap` через `T()`, то есть
    зависят от языка — а `useMemo` о нём не знал бы, и после переключения RU/EN поле осталось бы
    подписанным по-старому до перезахода на экран.
  */
  const lang = useLang();
  const bubbles = useMemo(() => buildMap(width, height), [width, height, lang]);
  const finger = useRef(new Animated.ValueXY({ x: -9999, y: -9999 })).current;
  /** 1 — палец на поле, 0 — отпущен. Гасит лупу целиком, не трогая её геометрию. */
  const live = useRef(new Animated.Value(0)).current;

  /*
   * Кого выбрали, решается ЗДЕСЬ, а не нажатием на пузырь: жест целиком принадлежит полю.
   * Ссылки держим в ref, потому что PanResponder создаётся один раз и замыкает первые значения.
   */
  const hit = useRef<(x: number, y: number) => string | null>(() => null);
  hit.current = (x, y) => {
    let best: string | null = null;
    let bestD = Infinity;
    for (const b of bubbles) {
      const dx = x - b.x * width;
      const dy = y - b.y * height;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d <= (b.size * PEAK) / 2 + TAP_SLACK && d < bestD) { bestD = d; best = b.key; }
    }
    return best;
  };
  const from = useRef({ x: 0, y: 0 });
  const moved = useRef(false);
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
        moved.current = false;
        finger.setValue({ x, y });
        drag.current?.(true);
        Animated.timing(live, { toValue: 1, duration: 90, useNativeDriver: true }).start();
      },
      onPanResponderMove: (e) => {
        const { locationX: x, locationY: y } = e.nativeEvent;
        if (Math.abs(x - from.current.x) > TAP_SLOP || Math.abs(y - from.current.y) > TAP_SLOP) {
          moved.current = true;
        }
        finger.setValue({ x, y });
      },
      onPanResponderRelease: (e) => {
        if (!moved.current) {
          const k = hit.current(e.nativeEvent.locationX, e.nativeEvent.locationY);
          if (k) toggle.current(k);
        }
        drag.current?.(false);
        Animated.timing(live, { toValue: 0, duration: 200, useNativeDriver: true }).start();
      },
      onPanResponderTerminate: () => {
        drag.current?.(false);
        Animated.timing(live, { toValue: 0, duration: 200, useNativeDriver: true }).start();
      },
    })
  ).current;

  /*
    ГРАФЫ АНИМАЦИИ СЧИТАЮТСЯ ЗДЕСЬ, А НЕ В КАЖДОМ ПУЗЫРЕ, потому что их нужно ДВУМ слоям: кругам и
    подписям. Строить их дважды значит держать вдвое больше узлов ради одного и того же числа.
  */
  const graph = useMemo(() => bubbles.map((b) => {
    const cx = b.x * width;
    const cy = b.y * height;
    // Две линейные интерполяции, перемноженные, дают мягкий колокол одним выражением на нативной
    // стороне; возведения в степень тут нет намеренно.
    const fall = (v: Animated.Value, c: number) =>
      Animated.subtract(v, new Animated.Value(c)).interpolate({
        inputRange: [-REACH, -REACH / 2, 0, REACH / 2, REACH],
        outputRange: [1, 1 + (AXIS_PEAK - 1) * 0.45, AXIS_PEAK, 1 + (AXIS_PEAK - 1) * 0.45, 1],
        extrapolate: 'clamp',
      });
    const lens = Animated.multiply(fall(finger.x as Animated.Value, cx),
                                   fall(finger.y as Animated.Value, cy));
    const scale = Animated.add(
      new Animated.Value(1),
      Animated.multiply(Animated.subtract(lens, new Animated.Value(1)), live)
    );
    // Категория подписана всегда — по ней и ведут палец. Спутник проявляется вместе с увеличением:
    // полторы сотни подписей разом — каша, ради ухода от которой лупа и заведена.
    //
    // ПОРОГ ПОДНИМАЛИ ДВАЖДЫ, и второй раз — когда занятий стало полтораста. При сорока четырёх
    // хватало 0.62: до него доходил один сосед. В густом поле до той же высоты успевают трое, и
    // над пальцем вставали три тёмные плашки внахлёст — «Готовка», «Бранчи», «Матча» разом.
    // Подпись достаётся тому, кто вырос почти целиком.
    const labelOpacity = b.kind === 'root' ? new Animated.Value(1) : scale.interpolate({
      inputRange: [1, 1 + (PEAK - 1) * 0.84, PEAK],
      outputRange: [0, 0, 1],
      extrapolate: 'clamp',
    });
    return { b, cx, cy, scale, labelOpacity };
  }), [bubbles, width, height, finger, live]);

  return (
    <View style={[s.field, { width, height }]} {...pan.panHandlers}>
      {graph.map((g) => (
        <BubbleView key={g.b.key} g={g} on={selected.includes(g.b.key)} />
      ))}
      {/*
        ПОДПИСИ СПУТНИКОВ — ОТДЕЛЬНЫМ СЛОЕМ ПОВЕРХ ВСЕГО. Когда они лежали внутри своего пузыря,
        их закрывала соседняя категория: у корней `zIndex` выше, и увеличенная подпись пряталась за
        соседним кругом. Поднять сам спутник нельзя — тогда под соседей уходила бы увеличенная
        категория. Слой решает оба случая разом: круги спорят между собой за порядок, подписи
        всегда сверху.
      */}
      <View style={s.plateLayer} pointerEvents="none">
        {graph.filter((g) => g.b.kind === 'leaf').map((g) => (
          <PlateView key={`p-${g.b.key}`} g={g} />
        ))}
      </View>
    </View>
  );
}

/** Подпись спутника: едет и растёт вместе со своим кругом, но живёт в верхнем слое. */
function PlateView({ g }: { g: Graph }) {
  const { b, cx, cy, scale, labelOpacity } = g;
  const d = b.size;
  return (
    <Animated.View
      pointerEvents="none"
      style={[
        s.plateSlot,
        { left: cx - d / 2, top: cy - d / 2, width: d, height: d, transform: [{ scale }] },
      ]}
    >
      <Animated.View style={[s.plate, { bottom: d + PLATE_GAP, opacity: labelOpacity }]}>
        <Text numberOfLines={1} style={s.plateText}>{b.label}</Text>
      </Animated.View>
    </Animated.View>
  );
}

/**
 * Готовый граф одного пузыря. Типы значений `Animated` в RN не сводятся к одному имени
 * (сложение, произведение и интерполяция — разные классы), поэтому здесь `any`: сузить его
 * можно только перечислением внутренних типов библиотеки, которых она не экспортирует.
 */
type Graph = { b: Bubble; cx: number; cy: number; scale: any; labelOpacity: any };

function BubbleView({ g, on }: { g: Graph; on: boolean }) {
  const { b, cx, cy, scale, labelOpacity } = g;
  const d = b.size;
  const root = b.kind === 'root';
  const t = deckTone[ROOT_TONE[b.root] || 'slate'];

  /*
    НАЖАТИЕ СЮДА НЕ ПРИХОДИТ — его разбирает поле, поэтому View, а не Pressable: кнопка, которая
    никогда не срабатывает, врёт и глазу, и озвучке.

    zIndex ОТ ВИДА, И ЭТО НЕ УКРАШЕНИЕ. Порядок отрисовки был порядком массива — «категория, её
    спутники, следующая категория», — значит первая категория лежала в самом низу стопки и под
    лупой уходила ПОД четырнадцать соседей. Увеличение, которое прячется за соседями, работает
    наоборот: палец наводят, а нужное исчезает.
  */
  return (
    <Animated.View
      pointerEvents="none"
      accessible
      accessibilityRole="button"
      accessibilityLabel={b.label}
      accessibilityState={{ selected: on }}
      style={[
        s.slot,
        { left: cx - d / 2, top: cy - d / 2, width: d, height: d,
          zIndex: root ? 2 : 1, transform: [{ scale }] },
        on ? { ...s.onShadow, shadowColor: color.primary }
           : { ...s.toneShadow, shadowColor: t.glow },
      ]}
    >
      <View style={[s.dot, { width: d, height: d, borderRadius: d / 2 }]}>
        {/*
          Свечение рисуется SVG: `expo-linear-gradient` в проекте нет, а `react-native-svg` стоит.
          Координаты — честные точки (`userSpaceOnUse`), не проценты: на процентах радиус считается
          по ширине области просмотра, и однажды заливка пузыря реплики закрасила только верх.
        */}
        {on ? (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: color.primary }]} />
        ) : (
          <Svg width={d} height={d} style={StyleSheet.absoluteFill}>
            <Defs>
              <RadialGradient id={`h-${b.key}`} gradientUnits="userSpaceOnUse"
                              cx={d * 0.3} cy={d * 0.24} rx={d * 0.72} ry={d * 0.72}>
                {BLOOM.map(([o, a]) => <Stop key={o} offset={o} stopColor={t.halo} stopOpacity={a} />)}
              </RadialGradient>
              <RadialGradient id={`g-${b.key}`} gradientUnits="userSpaceOnUse"
                              cx={d * 0.62} cy={d * 0.78} rx={d * 0.6} ry={d * 0.6}>
                {BLOOM.map(([o, a]) => (
                  <Stop key={o} offset={o} stopColor={t.glow} stopOpacity={a * 0.42} />
                ))}
              </RadialGradient>
            </Defs>
            <Rect x={0} y={0} width={d} height={d} fill={t.wash} />
            <Rect x={0} y={0} width={d} height={d} fill={`url(#h-${b.key})`} />
            <Rect x={0} y={0} width={d} height={d} fill={`url(#g-${b.key})`} />
          </Svg>
        )}
        {/* Светлая кромка сверху — та же, что у стеклянных кнопок: у настоящей поверхности верх
            всегда светлее, без неё круг выглядит наклейкой. */}
        <View style={[s.sheen, { borderRadius: d / 2 }]} pointerEvents="none" />
      </View>
      {/*
        ПОДПИСЬ КАТЕГОРИИ — ПОД КРУГОМ, А НЕ В НЁМ. Пока категорий было восемь по шестьдесят четыре
        пикселя, слово помещалось внутрь. Когда занятий стало полтораста, круги пришлось ужать до
        сорока шести — и слова стали рваться посреди слога: «Приро да», «Музык а», «Культу ра».
        Расширять круг ради букв значит вернуть ту густоту, от которой уходили.

        Поэтому имя вынесено вниз, ровно как в библиотеке ассетов борда: там под каждым круглым
        кропом стоит подпись 180x18 тёмным цветом. Место под словом бесплатное — там фон, а не
        соседний пузырь.
      */}
      {root && (
        <Animated.Text
          numberOfLines={1}
          style={[s.rootLabel, { top: d + PLATE_GAP, opacity: labelOpacity }]}
        >
          {b.label}
        </Animated.Text>
      )}
    </Animated.View>
  );
}

// ===== вид
const s = StyleSheet.create({
  field: { position: 'relative', alignSelf: 'center' },
  /** Верхний слой подписей: не перехватывает касания и лежит поверх всех кругов. */
  plateLayer: { ...StyleSheet.absoluteFillObject, zIndex: 3 },
  plateSlot: { position: 'absolute', alignItems: 'center', justifyContent: 'center' },
  slot: { position: 'absolute', alignItems: 'center', justifyContent: 'center' },
  /** Обрезка кругом обязательна: под ней лежит прямоугольный Svg со свечением. */
  dot: { alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  sheen: {
    ...StyleSheet.absoluteFillObject,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFFA6',
  },
  /** Тень цветом СВОЕГО тона — та же ступень, что у карточки колоды и пузыря реплики. */
  toneShadow: { shadowOpacity: 0.22, shadowRadius: 10, shadowOffset: { width: 0, height: 5 }, elevation: 3 },
  /** Выбранное светится фирменным — как главная кнопка и выбранный чип. */
  onShadow: { shadowOpacity: 0.3, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 6 },
  /**
   * Категорию читают с обычного расстояния, поэтому она крупнее спутника и не ждёт лупы.
   * Отрицательные поля — по той же причине, что у плашки спутника: слот ровно с круг шириной,
   * а «Культура» шире сорока шести пикселей.
   */
  rootLabel: {
    position: 'absolute',
    left: -40,
    right: -40,
    textAlign: 'center',
    fontFamily: font.textMedium,
    fontSize: 10,
    lineHeight: 13,
    color: color.fg,
  } as any,
  /**
   * Тёмная плашка, а не светлая: поле пастельное, и светлая на нём терялась бы.
   * Ширину не задаём — она по содержимому; центрируется отрицательным полем через `alignSelf`,
   * потому что слот ровно с круг шириной, а имя бывает длиннее.
   */
  /*
    ШИРИНА ЗАДАНА ОТРИЦАТЕЛЬНЫМИ ПОЛЯМИ, а не содержимым. Слот ровно с круг шириной — двадцать с
    небольшим пикселей, — и подпись по содержимому в него упиралась: «Настольные игры» показывались
    как «Нас…». Растянув плашку за края слота в обе стороны, получаем и место под слово, и центр
    ровно над кругом.
  */
  plate: {
    position: 'absolute',
    left: -44,
    right: -44,
    height: PLATE_H,
    borderRadius: rad.full,
    backgroundColor: color.ink,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  plateText: {
    fontFamily: font.textMedium,
    fontSize: 7,
    lineHeight: 9,
    color: color.onPrimary,
    textAlign: 'center',
  } as any,
});
