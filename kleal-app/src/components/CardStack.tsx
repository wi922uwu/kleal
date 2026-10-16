/**
 * Стопка карточек — колода «Home Card» на главной (кадр «GR.01 · Home · Kleal prompt»).
 *
 * ЗАЧЕМ СТОПКА, А НЕ СПИСОК. Продукт обещает 2–4 объяснённых варианта, а не бесконечную ленту
 * людей: список из восьми карточек подряд — это ровно та лента, от которой Kleal отказывается.
 * Стопка показывает ОДНОГО человека и говорит, сколько ещё за ним.
 *
 * ЛИСТАНИЕ — НЕ СВАЙП-КОЛОДА, и разница здесь смысловая, а не техническая. Свайпы названы врагом
 * продукта («социальное трение: свайпы, холодные сообщения, мёртвые чаты»), но запрещён там
 * конкретный жест — ОТБРОСИТЬ человека вбок, то есть принять решение броском. Здесь жест ничего
 * не решает и никого не выбрасывает: он перелистывает, и назад тоже. Карточка остаётся в колоде,
 * решение по ней принимают, открыв её.
 *
 * Поэтому листание в обе стороны обязательно, а на краях колода упирается, а не уезжает в пустоту.
 *
 * Геометрия с борда, не на глаз (GR.01, секция «Test 260930»): верхняя «Home Card · plan» 350×126,
 * под ней три края — такие же карточки, но 64 в высоту и прижатые к её низу:
 *   край 1   326×64   — на 12 уже с каждой стороны, выглядывает на 3
 *   край 2   290×64   — на 30 уже, выглядывает на 6
 *   край 3   247×64   — на 51,5 уже, выглядывает на 9
 * Углы у всех 20 сверху и 32 снизу; стекло у краёв белое 20%, у верхней 50%. Колода целиком
 * 126 + 9 = 135 (STACK_H), поля 20 по бокам. Точек под колодой больше нет: на кадре их нет, а «за
 * этой есть ещё» говорят сами края. Краёв рисуется столько, сколько карточек реально за верхней,
 * но не больше трёх, — края остаются счётчиком, а не украшением.
 *
 * ЧТО БЫЛО НЕ ТАК И ПОЧЕМУ ПЕРЕПИСАНО (10 сентября 2026, с телефона: «багованное пролистывание и
 * анимация, белое пятно сзади»). Три причины, и все в геометрии, а не в жесте:
 *   • Слои под верхней были полосками в 26 пунктов шириной от КОНТЕЙНЕРА, а сама карточка стояла в
 *     нём с полями 20 (marginHorizontal и у карточки, и у контейнера). Полоски выглядывали из-за
 *     карточки по бокам на 15 и 6 пунктов — это и есть «белое пятно».
 *   • Новая карточка проявлялась из нуля (170 мс), а уехавшая гасилась. Эти 170 мс на её месте не
 *     было ничего — кремовый фон и две белые полоски. То же на первом кадре: эффект запускался уже
 *     после отрисовки, и карточка мигала при каждом заходе на главную.
 *   • По завершении жеста сдвиг сбрасывался в ноль ДО смены индекса: слой, подтянувшийся на место
 *     верхней, на один кадр падал обратно, и только потом появлялась новая. Плюс лента забирала жест
 *     на Android — запрос на перехват не отклонялся, и карточка отпрыгивала посреди движения.
 *
 * ПОДЛОЖКИ БОЛЬШЕ НЕТ (30 сентября 2026, карточки стали стеклом). После первой переделки под
 * верхней всегда лежала белая НЕПРОЗРАЧНАЯ подложка её размера, а края были такими же подложками в
 * полный рост: на подложке проступало новое содержимое, и фону негде было показаться. Верхняя теперь
 * стеклянная и наполовину прозрачная — непрозрачная подложка под ней сделала бы её сплошь белой, а
 * края в полный рост просвечивали бы сквозь неё тремя рамками. Под верхней остались только края,
 * полоски в 64, какими их рисует кадр.
 *
 * С подложкой ушёл и прежний способ смены — погасить содержимое и проявить новое. Прозрачность здесь
 * запрещена вовсе: системное стекло (UIVisualEffectView) не рисуется, если у него или у ЛЮБОГО предка
 * непрозрачность меньше 1. Всё движение — сдвигом, поворотом и обрезкой:
 *   • Вперёд: верхняя уходит влево, а следующая открывается ПОД ней — не целиком, а на ту полосу,
 *     которую уходящая уже освободила (плюс нахлёст в нижний радиус, см. `motion`). Целиком под
 *     прозрачной верхней она просвечивала бы вторым текстом поверх первого.
 *   • Назад: предыдущая въезжает слева ПОВЕРХ, а текущая срезается по её кромке — по той же причине.
 *   • Смена индекса без кадра «не на месте»: открытая карточка остаётся нарисованной, пока новая
 *     верхняя не встанет на её место одним сдвигом, — см. эффект на `index`.
 * Края при этом стоят: они одинаковые, и после шага колода выглядит так же, как до него. Движется
 * только край, которого после шага станет меньше (уезжает под карточку) или больше (выезжает из-под
 * неё): счёт меняется плавно, а не скачком.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated, Easing, PanResponder } from 'react-native';
import { hTick } from '../haptics';
import { color, type } from '../theme';
import { GlassSurface, LIQUID } from './LiquidGlass';

/** Рост верхней, пока она не измерена: «Home Card» 350×126 (см. HOME_CARD_H в HomeCards.tsx). */
const CARD_H = 126;
/** Края под верхней — три «Home Card» по 64 в высоту, прижатые к её низу. */
const EDGE_H = 64;
/** Насколько край уже карточки с каждой стороны: 350 → 326 / 290 / 247. Нулевой — сама карточка. */
const INSET = [0, 12, 30, 51.5];
/** Насколько край выглядывает из-под нижней кромки верхней. */
const PEEK = [0, 3, 6, 9];
const EDGES = 3;
/** Рост колоды целиком — карточка и самый глубокий край. Экран держит под колоду ровно столько. */
export const STACK_H = CARD_H + PEEK[EDGES];
/** Углы — те же, что у карточки: сверху 20, снизу 32. */
const R_TOP = 20;
const R_BOTTOM = 32;
/** Нахлёст открываемой карточки под уходящую — на нижний радиус, см. `motion`. */
const LAP = R_BOTTOM;
/** Въезжающая назад стоит за левым краем экрана с запасом: поле колоды 20 и ещё 20. */
const OFF = 40;

/** Порог листания: четверть карточки, но не меньше этого — на узком экране четверть слишком мала. */
const MIN_TURN = 56;
/** Бросок засчитывается по скорости, даже если палец не дошёл до порога: так листают на самом деле. */
const FLICK = 0.32;
/** Сопротивление на краю: карточка идёт за пальцем втрое медленнее и никуда не уходит. */
const RUBBER = 0.32;

const SPRING = { toValue: 0, useNativeDriver: true, speed: 18, bounciness: 5 } as const;

/**
 * Всё движение колоды — производные ОДНОГО сдвига жеста. Считаются один раз на ширину: при
 * перерисовке во время жеста новые узлы пришлось бы заново цеплять к нативному драйверу.
 *
 * НАХЛЁСТ ВМЕСТО СТЫКА. Открываемая карточка режется прямой линией, а у уходящей правые углы
 * скруглены (20 и 32). Срез ровно по её кромке оставлял бы у углов две щели, сквозь которые виден
 * фон, — будто карточки разорваны. Поэтому срез идёт на 32 левее кромки: под скруглением всегда есть
 * открытая карточка, а прямой срез спрятан под уходящей. Нахлёст набирается за первые 40 пунктов
 * хода — иначе на первом касании под верхней выскакивала бы полоса чужого текста.
 */
function motion(shift: Animated.Value, nudge: Animated.Value, w: number, far: number) {
  // Правая кромка уходящей: сдвиг плюс усадка до 0,97 (по 1,5% ширины с каждой стороны).
  const k = 1 + (0.015 * w) / far;
  const edgeAt = (x: number) => (x >= -far ? w + x * k : w + x - 0.015 * w);
  const reveal = shift.interpolate({
    inputRange: [-2 * w, -far, -40, 0],
    outputRange: [edgeAt(-2 * w) - LAP, edgeAt(-far) - LAP, edgeAt(-40) - LAP, w],
    extrapolate: 'clamp',
  });
  // Назад: правая кромка въезжающей и срез текущей по ней, с тем же нахлёстом. К концу хода нахлёст
  // сходит на нет: в миг смены индекса от текущей не должно оставаться ни полоски.
  const prevRight = (x: number) => (x * (w + OFF)) / w - OFF;
  const lapStart = ((OFF + LAP) * w) / (w + OFF);
  const cut = shift.interpolate({
    inputRange: [0, lapStart, w - 40, w],
    outputRange: [0, 0, prevRight(w - 40) - LAP, w],
    extrapolate: 'clamp',
  });
  return {
    reveal,
    revealBack: Animated.multiply(reveal, -1),
    cut,
    cutBack: Animated.multiply(cut, -1),
    prevX: shift.interpolate({ inputRange: [0, w], outputRange: [-(w + OFF), 0], extrapolate: 'clamp' }),
    /*
      ВЕРХНЯЯ ЕДЕТ ТОЛЬКО ВЛЕВО. Вправо она стоит: назад возвращается не она, а предыдущая — въезжает
      поверх. Сдвиг её рамки вправо на `cut` — это не движение, а срез: содержимое внутри рамки
      сдвинуто обратно на столько же и стоит на месте.
    */
    topX: Animated.add(
      Animated.add(shift.interpolate({ inputRange: [-1, 0, 1], outputRange: [-1, 0, 0] }), nudge),
      cut
    ),
    /*
      Наклон и уменьшение — обратная связь пальцу, а не украшение: карточка ведёт себя как предмет,
      который тянут за угол, и по ней видно, засчитается жест или нет. Величины намеренно маленькие:
      это листание, а не бросок.
    */
    rotate: shift.interpolate({ inputRange: [-w, 0], outputRange: ['-4deg', '0deg'], extrapolate: 'clamp' }),
    scale: shift.interpolate({ inputRange: [-far, 0], outputRange: [0.97, 1], extrapolate: 'clamp' }),
  };
}

export function CardStack<T_ extends { key: string }>({
  items,
  index,
  onIndex,
  render,
  emptyHint,
}: {
  items: T_[];
  /** Какая карточка сверху. Хранится СНАРУЖИ: экран знает, по кому уже приняли решение. */
  index: number;
  /** Куда перешли. Двусторонний: листают и вперёд, и назад. */
  onIndex: (i: number) => void;
  render: (item: T_) => React.ReactNode;
  /** Что сказать, когда стопка кончилась. Пусто — не рисовать ничего. */
  emptyHint?: string;
}) {
  /*
    ВСЕ ХУКИ ДО ЕДИНОГО ВЫЗЫВАЮТСЯ ДО ЛЮБОГО ВЫХОДА. Колода пустеет на ходу — приглашение разобрали,
    встреча ушла в прошлое, `index` перерос список, — и разное число хуков между отрисовками ломает
    жест (значения достаются из чужих ячеек) или роняет экран.
  */
  const [w, setW] = useState(0);
  const [h, setH] = useState(CARD_H);
  /**
   * Какую карточку открывает жест вперёд и какую возвращает назад. По КЛЮЧУ, а не по индексу: в миг
   * смены индекса «следующая» становится верхней, а открытая обязана остаться той же, что была, —
   * иначе на её месте на кадр мелькнула бы та, что за ней.
   */
  const [fwdKey, setFwdKey] = useState<string | null>(null);
  const [backKey, setBackKey] = useState<string | null>(null);

  /** Смещение жеста. Один источник для всего: верхняя, открытая под ней и въезжающая читают его. */
  const shift = useRef(new Animated.Value(0)).current;
  /** Упор на краю колоды — отдельно от сдвига, чтобы край не двигал соседей и не звал въезжающую. */
  const nudge = useRef(new Animated.Value(0)).current;

  const idxRef = useRef(index);
  idxRef.current = index;
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const goRef = useRef(onIndex);
  goRef.current = onIndex;
  const wRef = useRef(320);
  wRef.current = w || 320;
  /** Пока карточка едет и пока меняется индекс, новый жест не принимаем: индекс перескочил бы через один. */
  const busy = useRef(false);
  const fwdRef = useRef<string | null>(null);
  const backRef = useRef<string | null>(null);

  const width = w || 320;
  const far = Math.max(MIN_TURN, width * 0.25);
  const m = useMemo(() => motion(shift, nudge, width, far), [shift, nudge, width, far]);

  /** Открыть под верхней следующую / слева предыдущую. Из жеста — поэтому только через рефы. */
  const openFwd = (key?: string) => {
    if (key != null && fwdRef.current !== key) { fwdRef.current = key; setFwdKey(key); }
  };
  const openBack = (key?: string) => {
    if (key != null && backRef.current !== key) { backRef.current = key; setBackKey(key); }
  };
  const closeBoth = () => {
    fwdRef.current = null;
    backRef.current = null;
    setFwdKey(null);
    setBackKey(null);
  };
  const helpers = useRef({ openFwd, openBack, closeBoth });
  helpers.current = { openFwd, openBack, closeBoth };

  /*
    СМЕНА ИНДЕКСА — ПОСЛЕ ТОГО, КАК НОВАЯ ВЕРХНЯЯ УЖЕ НАРИСОВАНА. Порядок здесь обратный прежнему, и
    в этом весь смысл. Жест доезжает до конца и сразу отдаёт новый индекс, сдвиг НЕ сбрасывая: новая
    верхняя рисуется в рамке, которая ещё стоит за краем (вперёд) или срезана целиком (назад), а на
    её законном месте в это время видна открытая карточка — та же самая. И только теперь, после
    отрисовки, сдвиг встаёт в ноль: рамка верхней возвращается на место, а открытая в тот же миг
    уходит за срез — оба читают один сдвиг и меняются в одном кадре. Ни кадра без карточки, ни кадра
    со старой.

    Открытую снимаем через два кадра, а не сразу: снятие идёт через перерисовку, сдвиг — через
    нативный драйвер, и порядок их прихода не обещан. До снятия она уже невидима, а новый жест до
    тех пор не принимается (`busy`), поэтому чужая карточка под пальцем не мелькнёт.
  */
  useEffect(() => {
    shift.setValue(0);
    let alive = true;
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => {
        if (!alive) return;
        helpers.current.closeBoth();
        busy.current = false;
      });
    });
    return () => { alive = false; cancelAnimationFrame(raf1); cancelAnimationFrame(raf2); };
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  /*
    ЖЕСТ.

    ПЕРЕХВАТ, А НЕ ПРОСЬБА. Колода живёт внутри прокручиваемой главной, и по обычному
    `onMoveShouldSetPanResponder` лента успевала забрать движение первой: палец вёл вбок, а экран
    уезжал вверх. Захватываем сами, но только явную горизонталь — вертикаль по-прежнему достаётся
    ленте, иначе палец, начавший скроллить с карточки, не прокрутил бы экран.

    И НЕ ОТДАЁМ. Взяв жест, на просьбу ленты вернуть его отвечаем «нет»: на Android она спрашивает
    при любом вертикальном отклонении пальца, и карточка отпрыгивала на середине движения.

    КРАЙ УПИРАЕТСЯ, А НЕ ПУСКАЕТ В ПУСТОТУ. На первой карточке вправо и на последней влево движение
    идёт втрое медленнее и обрывается: рука чувствует границу колоды раньше, чем глаз успевает
    решить, что приложение сломалось.
  */
  const settle = () => {
    Animated.spring(nudge, SPRING).start();
    Animated.spring(shift, SPRING).start(({ finished }) => {
      // Новый жест остановил пружину — открытые карточки ему ещё нужны.
      if (finished && !busy.current) helpers.current.closeBoth();
    });
  };
  const settleRef = useRef(settle);
  settleRef.current = settle;

  /**
   * Отдать новый индекс. Экран обязан его принять; если не принял (колода пересобралась под пальцем),
   * колода не должна застрять с уехавшей верхней — возвращаем всё на место сами.
   */
  const turn = (from: number, to: number) => {
    goRef.current(to);
    setTimeout(() => {
      if (idxRef.current !== from) return;
      shift.setValue(0);
      helpers.current.closeBoth();
      busy.current = false;
    }, 400);
  };
  const turnRef = useRef(turn);
  turnRef.current = turn;

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponderCapture: (_e, g) =>
        !busy.current && Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy) * 1.4,
      onMoveShouldSetPanResponder: (_e, g) =>
        !busy.current && Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy) * 1.4,
      onPanResponderTerminationRequest: () => false,
      onPanResponderMove: (_e, g) => {
        const i = idxRef.current;
        const list = itemsRef.current;
        const edge = (g.dx > 0 && i === 0) || (g.dx < 0 && i >= list.length - 1);
        if (edge) {
          shift.setValue(0);
          nudge.setValue(g.dx * RUBBER);
          return;
        }
        nudge.setValue(0);
        // Карточку под уходящей (или слева) заводим с первым движением: к моменту, когда её станет
        // видно, она уже нарисована.
        if (g.dx < 0) helpers.current.openFwd(list[i + 1]?.key);
        else if (g.dx > 0) helpers.current.openBack(list[i - 1]?.key);
        shift.setValue(g.dx);
      },
      onPanResponderRelease: (_e, g) => {
        const i = idxRef.current;
        const list = itemsRef.current;
        const last = list.length - 1;
        const width = wRef.current;
        const far = Math.max(MIN_TURN, width * 0.25);
        const next = (g.dx < -far || g.vx < -FLICK) && i < last;
        const prev = (g.dx > far || g.vx > FLICK) && i > 0;
        if (!next && !prev) {
          // Не дотянули — возвращается пружиной. Возврат обязан быть виден: он и объясняет, что
          // жест засчитан не был.
          settleRef.current();
          return;
        }
        busy.current = true;
        hTick();
        Animated.spring(nudge, SPRING).start();
        if (next) {
          // Бросок мог прийти с пальца, который до того вёл вправо: открытой снизу тогда ещё нет.
          helpers.current.openFwd(list[i + 1]?.key);
          Animated.timing(shift, {
            toValue: -width * 1.1, duration: 190, easing: Easing.out(Easing.cubic), useNativeDriver: true,
          }).start(({ finished }) => (finished ? turnRef.current(i, i + 1) : settleRef.current()));
        } else {
          helpers.current.openBack(list[i - 1]?.key);
          Animated.timing(shift, {
            toValue: width, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: true,
          }).start(({ finished }) => (finished ? turnRef.current(i, i - 1) : settleRef.current()));
        }
      },
      onPanResponderTerminate: () => settleRef.current(),
    })
  ).current;

  if (!items.length || index >= items.length) {
    return emptyHint ? <Text style={s.empty}>{emptyHint}</Text> : null;
  }

  const top = items[index];
  const left = items.length - index;
  /** Сколько краёв рисовать: только столько, сколько карточек реально осталось за верхней. */
  const behind = Math.min(EDGES, Math.max(0, left - 1));
  const fwdItem = fwdKey != null ? items.find((it) => it.key === fwdKey) : undefined;
  const backItem = backKey != null ? items.find((it) => it.key === backKey) : undefined;
  /*
    Идёт ли шаг прямо сейчас — открытая совпадает с соседней. После смены индекса совпадать перестаёт
    (открытая стала верхней), и края сразу стоят как положено новой верхней.
  */
  const going = fwdKey != null && fwdKey === items[index + 1]?.key;
  const coming = backKey != null && index > 0 && backKey === items[index - 1]?.key;
  /** Вперёд: краёв станет на один меньше — дальний уезжает под карточку. */
  const fading = going && left - 1 <= EDGES ? behind : 0;
  /** Назад: станет на один больше — новый дальний выезжает из-под карточки. */
  const arriving = coming && left <= EDGES ? behind + 1 : 0;
  const count = Math.max(behind, arriving);
  /**
   * Край под карточкой: нижняя кромка поднята на пункт выше кромки верхней. Уезжающий приходит сюда к
   * порогу хода вперёд, выезжающий отсюда стартует и к порогу хода назад стоит на своём месте.
   */
  const tuck = (k: number, dir: -1 | 1) =>
    shift.interpolate({
      inputRange: dir < 0 ? [-far, 0] : [0, far],
      outputRange: [-(PEEK[k] + 1), 0],
      extrapolate: 'clamp',
    });

  return (
    <View style={s.stack} onLayout={(e) => setW(e.nativeEvent.layout.width)}>
      {/*
        Края — не картинка «для красоты», а счётчик: видно, что за этой есть ещё. Дальний рисуется
        первым, верхняя ляжет поверх без возни с zIndex.
      */}
      {Array.from({ length: count }, (_, j) => {
        const k = count - j;                     // 3 — дальний, 1 — ближний
        const move = k === fading ? tuck(k, -1) : k === arriving ? tuck(k, 1) : null;
        return (
          <Animated.View
            key={k}
            pointerEvents="none"
            style={[
              s.edge,
              { left: INSET[k], right: INSET[k], top: h + PEEK[k] - EDGE_H },
              move ? { transform: [{ translateY: move }] } : null,
            ]}
          >
            {/*
              Белое 20% со стеклом, как на кадре. Чистое системное стекло без оттенка на кремовом
              почти невидимо, светлый тон (46%) делал бы края сплошными белыми полосами — поэтому
              «clear» и плёнка 20% поверх. У запасного пути своя плёнка у «clear» уже 18%, вторую не
              кладём.
            */}
            <GlassSurface tone="clear" radius={R_TOP} pointerEvents="none" style={[StyleSheet.absoluteFill, s.edgeGlass]}>
              {LIQUID ? <View style={[StyleSheet.absoluteFill, s.edgeFilm]} /> : null}
            </GlassSurface>
          </Animated.View>
        );
      })}

      {/* Вперёд: следующая под уходящей — открыта ровно на освобождённую полосу (см. `motion`). */}
      {fwdItem ? (
        <Animated.View pointerEvents="none" style={[s.over, s.clip, { height: h, transform: [{ translateX: m.reveal }] }]}>
          <Animated.View style={{ transform: [{ translateX: m.revealBack }] }}>{render(fwdItem)}</Animated.View>
        </Animated.View>
      ) : null}

      <Animated.View
        {...pan.panHandlers}
        onLayout={(e) => setH(e.nativeEvent.layout.height)}
        // Обрезка нужна, только пока въезжает предыдущая: без неё свечение кнопки не срезалось бы
        // зря. Обрезка прямоугольная, без радиусов, — стеклу внутри она не мешает.
        style={[backItem ? s.clip : null, { transform: [{ translateX: m.topX }, { rotate: m.rotate }, { scale: m.scale }] }]}
      >
        <Animated.View style={{ transform: [{ translateX: m.cutBack }] }}>{render(top)}</Animated.View>
      </Animated.View>

      {/* Назад: предыдущая въезжает слева поверх текущей и в конце хода встаёт точно на её место. */}
      {backItem ? (
        <Animated.View pointerEvents="none" style={[s.over, { height: h, transform: [{ translateX: m.prevX }] }]}>
          {render(backItem)}
        </Animated.View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  /*
    ПОЛЯ ЗДЕСЬ, И ТОЛЬКО ЗДЕСЬ. Карточки внутри колоды идут без своих полей — иначе края считались
    бы от одной ширины, а карточка стояла бы в другой (так и было). Запас снизу — ровно под самый
    глубокий край (9 с борда), иначе его обрежет родитель.
  */
  stack: { marginHorizontal: 20, marginBottom: PEEK[EDGES] },
  // Координаты явно: в RN 0.86 `StyleSheet.absoluteFillObject` больше нет (есть только absoluteFill).
  over: { position: 'absolute', top: 0, left: 0, right: 0 },
  clip: { overflow: 'hidden' },
  edge: { position: 'absolute', height: EDGE_H },
  /*
    Углы по кадру. Обрезки у жидкого стекла нет: при разных радиусах RN обрезает маской, а под
    маскированным предком системное стекло не рисуется; форму ему даёт само стекло (радиусы по углам
    уходят в cornerConfiguration). Запасной путь обрезается видом.
  */
  edgeGlass: {
    borderTopLeftRadius: R_TOP,
    borderTopRightRadius: R_TOP,
    borderBottomLeftRadius: R_BOTTOM,
    borderBottomRightRadius: R_BOTTOM,
    overflow: LIQUID ? 'visible' : 'hidden',
  },
  edgeFilm: {
    borderTopLeftRadius: R_TOP,
    borderTopRightRadius: R_TOP,
    borderBottomLeftRadius: R_BOTTOM,
    borderBottomRightRadius: R_BOTTOM,
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
  empty: { ...type.bodySmall, color: color.ink, opacity: 0.65, paddingHorizontal: 20 } as any,
});
