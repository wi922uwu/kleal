/**
 * Карусель настроений — стеклянные карточки на главной (борд «GR.01 · Home · Kleal prompt», слой
 * «Feed V2 · events»).
 *
 * Одна карточка по центру: стекло 299×288, в нём вырезанный предмет и заголовок-оклик. Соседние
 * выглядывают из-за обоих краёв экрана — ПОЗАДИ центральной и чуть КРУПНЕЕ её (323/299): в борде
 * соседка не уменьшается, как в обычной карусели, а лежит глубже и просвечивает сквозь кромку
 * центральной. Листается пальцем и защёлкивается на ближайшей.
 *
 * КАРТОЧКИ ИДУТ ПО ДУГЕ, А НЕ ПО ПРЯМОЙ (просьба владельца 30.09.2026). Лента — обод колеса,
 * центр которого глубоко под экраном: уходя от центра, карточка опускается и наклоняется по
 * касательной к ободу, как спица, — левая клонится влево, правая вправо. Путь, пройденный
 * пальцем, — это длина дуги, поэтому скорость под пальцем та же, что у плоской ленты.
 *
 * ПОЧЕМУ ЭТО ScrollView, А НЕ СВОЙ ЖЕСТ. Магнит, инерция, отскок и подхват на лету в `ScrollView`
 * уже есть и сделаны системой: `snapToInterval` вместе с `decelerationRate fast` дают то самое
 * «щёлкает на место», которое в iOS ощущается родным. Своя физика на PanResponder повторяла бы
 * это приблизительно, и разница чувствуется сразу. Приём тот же, что у прежнего колеса
 * (ArcCarousel.tsx).
 *
 * ВСЯ ГЕОМЕТРИЯ — ИНТЕРПОЛЯЦИЯ ОДНОГО ЗНАЧЕНИЯ. Масштаб, спуск и проявление предметов вокруг
 * карточки — функции общего сдвига ленты, у каждой карточки свой диапазон с вершиной в момент,
 * когда она по центру. Всё живёт на нативном драйвере, JS во время движения не участвует.
 *
 * КАРУСЕЛЬ БЕСКОНЕЧНАЯ, И ЭТО СДЕЛАНО ПОВТОРОМ. Набор выложен трижды, лента стартует со средней
 * копии, а на подходе к краю сдвиг перекидывается на длину набора без анимации — на экране в этот
 * момент стоит точно такая же карточка, подмены не видно.
 *
 * ПОЧЕМУ ВСЁ ЛЕЖИТ ПЛОСКО, А НЕ В ЯЧЕЙКАХ. Предметы вокруг карточки бывают двух слоёв: одни под
 * ВСЕМИ карточками (их размывает стекло и центральной, и соседней), другие поверх всего. `zIndex`
 * упорядочивает только соседей по родителю, поэтому у каждой позиции ленты три отдельных
 * абсолютных вида прямо в содержимом прокрутки — нижние предметы, карточка, верхние предметы, —
 * а не одна обёртка на ячейку: из обёртки нижний предмет не смог бы уйти под чужую карточку.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Image,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { GlassSurface, GlassTone } from './LiquidGlass';
import { hStrong, hTick } from '../haptics';
import { color, heading } from '../theme';
import { useLang } from '../i18n';
import type { Decor, MoodItem } from '../wheel';

// ===== эталон борда (экран 390, масштаб 1)
/** Карточка по центру: 299×288, из них 244 — место под предмет и 44 — полоса заголовка. */
const REF_W = 299;
const REF_H = 288;
const COVER_H = 244;
const BAND_H = 44;
/**
 * Шаг между центрами карточек. В борде 292 слева и 290 справа — это округление слоёв, взято
 * среднее. Соседка при этом на 20 точек заходит под центральную: так видна её кромка сквозь стекло.
 */
const REF_PITCH = 291;
/**
 * Сколько соседки видно из-за края экрана, на каждой стороне: (390 − 299) / 2.
 *
 * ЭТО ЧИСЛО ДЕРЖИТСЯ, А НЕ ШИРИНА КАРТОЧКИ. На узком телефоне карточка ужимается, чтобы соседки
 * всё равно выглядывали: одна карточка во весь экран не говорит, что тут что-то листается.
 */
const PEEK_SIDE = 45.5;
/** Во сколько раз соседняя крупнее центральной — 323/299 по борду. */
const SIDE = 323 / 299;
/**
 * Радиус обода — в точках эталона. Соседка (на шаг от центра) при нём наклонена на 12° и опущена
 * на 30: наклон читается на тех 45 точках, что видны из-за края, а карточка на полпути ещё не
 * заваливается набок. Меньше радиус — круче дуга и сильнее спуск.
 */
const ARC_R = 1400;
/** Точек выборки дуги на шаг: синус и косинус нативный драйвер не считает, кривая собрана ломаной. */
const ARC_STEPS = 6;
/**
 * Коробка предмета: 236×178, по центру карточки, верх на 47 от её верха (центр — на 136).
 * Предмет вписывается целиком (`contain`); для зеркального шара это даёт ровно шар борда 174×178.
 */
const OBJ_W = 236;
const OBJ_H = 178;
const OBJ_TOP = 47;
const RADIUS = 20;
/**
 * Запас над карточкой и под ней ВНУТРИ самой карусели.
 *
 * ПРОКРУТКА ОБРЕЗАЕТ ВСЁ, ЧТО ВЫШЛО ЗА ЕЁ РАМКУ, и `overflow: visible` на ней не работает. А за
 * карточку выходит многое: бокал над шаром поднимается на 65 точек выше её верха, соседние
 * карточки (крупнее на 8% и опущенные дугой) уходят ниже её низа. Без запаса бокал срезался бы по
 * верхней кромке карточки, а соседки — по нижней.
 */
const TOP_PAD = 70;
/*
  Снизу запас больше, чем сверху требует сама карточка: на полпути к краю уходящая карточка
  наклонена на 6°, и её внешний нижний угол опускается на ~16 точек ниже спуска по дуге — без
  запаса прокрутка срезала бы этот угол прямо на экране.
*/
const BOTTOM_PAD = 44;
/** Сколько копий набора выложено подряд. Три — минимум, при котором края не видно. */
const COPIES = 3;
/** На сколько лента качнётся при входе на главную — чтобы было видно, что она листается. */
const PEEK = 44;
/**
 * Тон стекла. В борде у карточки эффект GLASS БЕЗ ЗАЛИВКИ — это `frost`: тонкий системный материал
 * размытия, который почти не белит. Почему не системное жидкое стекло — см. `GlassSurface`.
 */
const CARD_TONE: GlassTone = 'frost';
/** Заголовок карточки: TASA Orbiter 700, 18/24, разрядка −0,09. Русский ужимает `heading()`. */
const TITLE = { fontSize: 18, lineHeight: 24, letterSpacing: -0.09 };

/** Эталонные размеры (экран от 390, масштаб 1) — для раскладки экрана. Точные — `moodGeometry`. */
export const MOOD_CARD_W = REF_W;
export const MOOD_CARD_H = REF_H;
export const MOOD_PITCH = REF_PITCH;
/** Верх карточки внутри карусели: столько карусель занимает над ней. */
export const MOOD_TOP_PAD = TOP_PAD;
export const MOOD_BOTTOM_PAD = BOTTOM_PAD;
/** Вся высота карусели: запас сверху + карточка + запас снизу. */
export const MOOD_HEIGHT = TOP_PAD + REF_H + BOTTOM_PAD;

/**
 * Размеры карусели на конкретном экране.
 *
 * ПРАВИЛО ОДНО: карточка = min(299·scale, ширина − 91·scale), всё остальное — шаг, высоты,
 * коробка предмета, предметы вокруг, запасы — умножается на u = карточка / 299. То есть по бокам
 * всегда выглядывает по 45,5·scale соседки, а карточка берёт остальное, но не больше эталона.
 * Кегль заголовка НЕ ужимается: полоса 44·u вмещает строку 24 до u ≈ 0,55, а мельче 18 оклик
 * перестаёт читаться с руки.
 */
export function moodGeometry(width: number, scale = 1) {
  const cardW = Math.max(120, Math.min(REF_W * scale, width - PEEK_SIDE * 2 * scale));
  const u = cardW / REF_W;
  return {
    u,
    cardW,
    cardH: REF_H * u,
    pitch: REF_PITCH * u,
    /** Верх карточки от верха карусели. */
    cardTop: TOP_PAD * u,
    height: (TOP_PAD + REF_H + BOTTOM_PAD) * u,
  };
}

export function MoodCarousel({ items, onPick, hint, scale = 1 }: {
  items: MoodItem[];
  /** Нажали по ТОЙ, что сейчас по центру. По соседней жест означает «подвинь её сюда». */
  onPick?: (it: MoodItem) => void;
  /**
   * Счётчик заходов на главную. При каждом изменении лента коротко качается вправо и назад:
   * соседние карточки показываются из-за краёв, и понятно, что их можно листать.
   */
  hint?: number;
  /**
   * Во сколько раз ужать всё целиком — для низких экранов, считает экран. Ширину экрана карусель
   * учитывает сама (см. `moodGeometry`), сюда она не входит.
   */
  scale?: number;
}) {
  const lang = useLang();
  const { width } = useWindowDimensions();
  const n = items.length;
  const g = moodGeometry(width, scale);
  const { u, pitch } = g;
  /** Левый край карточки при нулевом сдвиге: центральная стоит ровно посередине экрана. */
  const side = (width - g.cardW) / 2;
  const radius = RADIUS * u;
  /**
   * СДВИГ НАЧИНАЕТСЯ СО СТАРТОВОГО, А НЕ С НУЛЯ. `contentOffset` ставит ленту на середину набора
   * без события прокрутки, и значение, начатое с нуля, рисовало бы первый кадр так, будто по
   * центру самая первая карточка: центральная стояла бы увеличенной и опущенной, как соседка.
   */
  const start = n * pitch;
  const x = useRef(new Animated.Value(start)).current;
  const list = useRef<ScrollView>(null);
  const [at, setAt] = useState(n);
  /**
   * Номер центральной — ещё и в ссылке. Обработчик прокрутки собирается один раз на шаг (см.
   * `onScroll`), и состояние в его замыкании устарело бы с первого же щелчка.
   */
  const atRef = useRef(n);
  /** Где лента сейчас — для покачивания: качаемся от текущего места и возвращаемся на него же. */
  const lastX = useRef(start);

  useEffect(() => {
    if (!hint) return;
    /*
      Качание — два программных прокрута, вправо и обратно. Через ScrollView, а не своим Animated:
      тогда двигается всё, что и при пальце, и выглядит это как начало настоящего листания. Пауза
      до старта: экран ещё выезжает, и качание в этот момент сливается с переходом.
    */
    let from = 0;
    const t1 = setTimeout(() => {
      from = lastX.current;
      list.current?.scrollTo({ x: from + PEEK * u, animated: true });
    }, 450);
    const t2 = setTimeout(() => list.current?.scrollTo({ x: from, animated: true }), 450 + 360);
    return () => { clearTimeout(t1); clearTimeout(t2); };
    // Качание — только на новый заход, а не на смену размеров.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hint]);

  /*
    ШАГ СМЕНИЛСЯ — ЦЕНТРАЛЬНАЯ ОСТАЁТСЯ ЦЕНТРАЛЬНОЙ. Экран пересчитал масштаб (или повернулся), и
    все карточки встали на новые места, а сдвиг прокрутки остался старым, в точках: по центру
    оказалась бы щель между карточками. Ставим ленту на ту же карточку по новому шагу.
  */
  const prevPitch = useRef(pitch);
  useEffect(() => {
    if (prevPitch.current === pitch) return;
    prevPitch.current = pitch;
    const cx = atRef.current * pitch;
    x.setValue(cx);
    lastX.current = cx;
    list.current?.scrollTo({ x: cx, animated: false });
  }, [pitch, x]);

  /** Лента: набор, повторённый трижды. Ключи разные — иначе React сочтёт копии одним элементом. */
  const strip = useMemo(
    () =>
      Array.from({ length: n * COPIES }, (_, i) => ({
        ...items[i % n],
        key: `${items[i % n].key}#${Math.floor(i / n)}`,
      })),
    [items, n]
  );

  /*
    Превращения собраны один раз на шаг, а не на каждой отрисовке: номер центральной меняется на
    каждом щелчке, и пересобирать на нём полсотни интерполяций значило бы зря гонять JS посреди
    жеста. Зависят они не от самих предметов, а только от того, у кого есть что проявлять: экран
    отдаёт свежий массив на каждой своей отрисовке (`WHEEL()`), и завязка на него пересобирала бы
    всё по любому поводу.
  */
  const decorMask = items.map((it) => (it.decor?.length ? '1' : '0')).join('');
  const anim = useMemo(
    () =>
      Array.from({ length: n * COPIES }, (_, i) => {
        const mid = i * pitch;
        const range = [mid - pitch, mid, mid + pitch];
        /*
          ДУГА. d — на сколько лента ушла от положения, где эта карточка в центре; на плоской
          ленте карточка сдвинулась бы на −d. На ободе радиуса R она стоит под углом θ = −d/R:
          по горизонтали R·sin θ (поправка к плоскому сдвигу — d − R·sin(d/R)), вниз
          R·(1 − cos θ), и повёрнута на θ. Выборка на ±2 шага: дальше карточка за экраном.
        */
        const R = ARC_R * u;
        const ds = Array.from({ length: 4 * ARC_STEPS + 1 }, (_, k) => ((k - 2 * ARC_STEPS) / ARC_STEPS) * pitch);
        const inputRange = ds.map((d) => mid + d);
        const arcX = x.interpolate({ inputRange, outputRange: ds.map((d) => d - R * Math.sin(d / R)), extrapolate: 'clamp' });
        const arcY = x.interpolate({ inputRange, outputRange: ds.map((d) => R * (1 - Math.cos(d / R))), extrapolate: 'clamp' });
        const tilt = x.interpolate({ inputRange, outputRange: ds.map((d) => `${(-d / R) * (180 / Math.PI)}deg`), extrapolate: 'clamp' });
        const grow = x.interpolate({ inputRange: range, outputRange: [SIDE, 1, SIDE], extrapolate: 'clamp' });
        return {
          /* Сначала на обод, потом наклон и масштаб вокруг центра карточки — не вокруг точки ленты. */
          move: [{ translateX: arcX }, { translateY: arcY }, { rotate: tilt }, { scale: grow }],
          /*
            Предметы вокруг гаснут к соседнему положению: они про ЦЕНТРАЛЬНУЮ карточку, и
            бокал, висящий над уехавшей вбок соседкой, выглядел бы потерянным. Прозрачность тут
            можно — в предметах нет стекла (см. riseIn в LiquidGlass.tsx).
          */
          /*
            Подпись гаснет к соседнему положению: соседка наклонена и опущена дугой, и конец её
            длинного оклика («…side by side?») торчал из-за края экрана обрывком. На кадре подписей
            соседок не видно. Прозрачность — только у полосы с текстом: стекло карточки лежит
            рядом с ней, а не внутри, и гаснуть ему не приходится.
          */
          label: x.interpolate({ inputRange: [mid - pitch * 0.7, mid, mid + pitch * 0.7], outputRange: [0, 1, 0], extrapolate: 'clamp' }),
          fade: decorMask[i % n] === '1'
            ? x.interpolate({ inputRange: range, outputRange: [0, 1, 0], extrapolate: 'clamp' })
            : null,
        };
      }),
    [n, decorMask, x, pitch, u]
  );

  const onScroll = useMemo(
    () =>
      Animated.event([{ nativeEvent: { contentOffset: { x } } }], {
        useNativeDriver: true,
        /*
          Щелчок при смене центральной. Номер считается ЦЕЛЫМ ДЕЛЕНИЕМ и сравнением с прошлым — на
          кадр это одно деление, поэтому обработчик можно держать на каждом кадре прокрутки.
          ПЕРЕСКОК НА ДРУГУЮ КОПИЮ НЕ ЩЁЛКАЕТ: номер меняется ровно на длину набора, а под пальцем
          та же карточка — щелчок без движения ощущался бы как сбой.
        */
        listener: (e: NativeSyntheticEvent<NativeScrollEvent>) => {
          const cx = e.nativeEvent.contentOffset.x;
          lastX.current = cx;
          const i = Math.round(cx / pitch);
          const prev = atRef.current;
          if (i === prev) return;
          atRef.current = i;
          setAt(i);
          if ((((i - prev) % n) + n) % n !== 0) hTick();
        },
      }),
    [x, pitch, n]
  );

  /*
    МАГНИТ НА ANDROID — СПИСКОМ ТОЧЕК, А НЕ ШАГОМ. Android переводит `snapToInterval` в физические
    пиксели и отбрасывает дробь, а карточки стоят по точному шагу: при плотности 2,625 шаг 291 —
    это 763 пикселя вместо 763,875, и к середине ленты (шестая карточка, откуда она стартует)
    центральная вставала бы на 5 пикселей мимо центра, к концу — на 10. Точки списка округляются
    каждая сама по себе, и ошибка не копится. iOS берёт шаг как есть — там родной магнит.
  */
  const snap = useMemo(
    () =>
      Platform.OS === 'android'
        ? { snapToOffsets: Array.from({ length: n * COPIES }, (_, i) => i * pitch) }
        : { snapToInterval: pitch },
    [n, pitch]
  );

  /** Перекидываем ленту на копию назад или вперёд, когда подошли к краю. */
  const wrap = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const cur = e.nativeEvent.contentOffset.x;
    const span = n * pitch;
    if (cur < span * 0.5) list.current?.scrollTo({ x: cur + span, animated: false });
    else if (cur > span * 2.5) list.current?.scrollTo({ x: cur - span, animated: false });
  };

  if (!n) return null;
  const title = heading(lang, TITLE);
  const obj = { left: (g.cardW - OBJ_W * u) / 2, top: OBJ_TOP * u, width: OBJ_W * u, height: OBJ_H * u };
  const band = { top: COVER_H * u, height: BAND_H * u, paddingHorizontal: 16 * u };

  return (
    <View style={{ width, height: g.height }} pointerEvents="box-none">
      <Animated.ScrollView
        ref={list as any}
        horizontal
        style={{ height: g.height }}
        showsHorizontalScrollIndicator={false}
        // Магнит: лента останавливается только на шаге, а не там, где кончилась инерция.
        {...snap}
        decelerationRate="fast"
        contentOffset={{ x: start, y: 0 }}
        /*
          ШИРИНА СОДЕРЖИМОГО ЗАДАНА ЯВНО: все дети абсолютные и размера ему не дают. Последняя
          карточка должна вставать по центру — отсюда экран плюс шаги до неё.
        */
        contentContainerStyle={{ width: width + (strip.length - 1) * pitch, height: g.height }}
        onScroll={onScroll}
        onMomentumScrollEnd={wrap}
        scrollEventThrottle={16}
      >
        {strip.map((it, i) => {
          const frame = { left: side + i * pitch, top: g.cardTop, width: g.cardW, height: g.cardH };
          const { move, fade, label } = anim[i];
          const back = it.decor?.filter((d) => !d.front);
          const front = it.decor?.filter((d) => d.front);
          /*
            Стекло — только у ближних к центру. Остальные за краем экрана, а системное стекло у
            каждой из восемнадцати карточек — это восемнадцать слоёв размытия на каждом кадре.
            Запас в две карточки: номер центральной приходит из JS с опозданием на кадр-другой, и
            на быстром броске ближняя должна успеть стать стеклянной до того, как въедет в экран.
          */
          const near = Math.abs(i - at) <= 2;
          return (
            <React.Fragment key={it.key}>
              {back?.length && fade ? (
                <DecorLayer list={back} u={u} frame={frame} fade={fade} move={move} z={0} />
              ) : null}
              <Animated.View
                // Центральная поверх соседок: они крупнее и заходят под её кромку.
                style={[s.abs, frame, { zIndex: i === at ? 2 : 1, transform: move }]}
              >
                {/*
                  ДВА РАЗНЫХ ЖЕСТА ОДНИМ НАЖАТИЕМ, и различает их положение карточки.
                  По соседней — «подвинь её сюда»: она почти вся за краем, и нажатие по ней очевидно
                  означает выбор, а не запуск. По центральной — «поехали»: разговор открывается с
                  уже сказанной фразой, отклик тяжёлый — экран меняется целиком.
                */}
                <Pressable
                  style={StyleSheet.absoluteFill}
                  accessibilityRole="button"
                  accessibilityLabel={it.label}
                  onPress={() => {
                    if (i === atRef.current) {
                      if (onPick) {
                        hStrong();
                        // Отдаём исходный предмет, а не копию ленты с приписанным к ключу номером.
                        onPick(items[i % n]);
                      }
                      return;
                    }
                    list.current?.scrollTo({ x: i * pitch, animated: true });
                  }}
                >
                  {/*
                    Стекло — отдельным нижним слоем, а не обёрткой содержимого: при смене «ближняя —
                    дальняя» меняется только оно, а предмет и заголовок не пересоздаются. Внутри
                    нажимаемого — без касаний: интерактивное стекло перехватывает палец.
                  */}
                  {near ? (
                    // Кромку — ровную белую линию, как в борде, — иней рисует сам (см. GlassSurface).
                    <GlassSurface tone={CARD_TONE} radius={radius} pointerEvents="none" style={StyleSheet.absoluteFill} />
                  ) : null}
                  <Image
                    accessibilityIgnoresInvertColors
                    source={it.source}
                    resizeMode="contain"
                    style={[s.abs, obj]}
                  />
                  <Animated.View style={[s.band, band, { opacity: label }]}>
                    {/*
                      ОДНА СТРОКА С УЖИМОМ, а не две: полоса в борде 44 точки, вторая строка 24
                      вылезла бы за низ карточки. Длинные испанские оклики («¿Quieres coger algo
                      de fruta?») не влезают в 267 точек и слегка мельчают, а не режутся.
                    */}
                    <Text
                      style={[s.title, title]}
                      numberOfLines={1}
                      adjustsFontSizeToFit
                      minimumFontScale={0.7}
                      maxFontSizeMultiplier={1.3}
                    >
                      {it.label}
                    </Text>
                  </Animated.View>
                </Pressable>
              </Animated.View>
              {front?.length && fade ? (
                <DecorLayer list={front} u={u} frame={frame} fade={fade} move={move} z={3} />
              ) : null}
            </React.Fragment>
          );
        })}
      </Animated.ScrollView>
    </View>
  );
}

/**
 * Предметы вокруг одной карточки — один слой (нижний или верхний).
 *
 * СЛОЙ ЕДЕТ КАК КАРТОЧКА: та же рамка, тот же спуск и масштаб. Поэтому координаты предметов
 * остаются в точках карточки, а у соседнего положения они вместе с ней крупнеют и опускаются, не
 * съезжая с неё. Касаний слой не ловит: нота лежит поверх карточки, и нажатие по ней должно
 * доставаться карточке.
 */
function DecorLayer({ list, u, frame, fade, move, z }: {
  list: Decor[];
  u: number;
  frame: { left: number; top: number; width: number; height: number };
  fade: Animated.AnimatedInterpolation<number>;
  move: any[];
  z: number;
}) {
  return (
    <Animated.View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[s.abs, frame, { zIndex: z, opacity: fade, transform: move }]}
    >
      {list.map((d, j) => (
        <Image
          key={j}
          accessibilityIgnoresInvertColors
          source={d.source}
          resizeMode="contain"
          style={[s.abs, { left: d.x * u, top: d.y * u, width: d.w * u, height: d.h * u }]}
        />
      ))}
    </Animated.View>
  );
}

// ===== вид
const s = StyleSheet.create({
  abs: { position: 'absolute' },
  /** Кромка карточки: белая линия в точку, ~55% — снята с рендера кадра GR.01. */
  band: { position: 'absolute', left: 0, right: 0, justifyContent: 'center' },
  title: { color: color.fg, textAlign: 'center' },
});
