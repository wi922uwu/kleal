/**
 * Нижняя панель приложения — кадр A.15.
 *
 * Раньше жила прямо в финале онбординга и была картинкой: четыре подписи, ни одна никуда не ведёт.
 * Здесь она общая и настоящая.
 *
 * ВИД: не полоса во всю ширину, а стеклянная пилюля 350×48 (по 20 от краёв при ширине 390),
 * приподнятая над краем экрана. Внутри — пять равных ячеек по 66 точек, как в кадре GR.01 борда
 * «Test 260930»: два знака, капля Kleal, два знака. Капля занимает среднюю ячейку наравне со
 * знаками, поэтому стоит ровно посередине без отдельного расчёта.
 *
 * ПОДПИСЕЙ ПОД ЗНАКАМИ НЕТ, и это не упрощение: в кадре их нет вовсе. На пилюле высотой 48 подпись
 * физически не помещается рядом со знаком 24×24, а прежние 9,5 пункта были на грани читаемости. Имя
 * вкладки осталось там, где оно действительно нужно, — в `accessibilityLabel`.
 *
 * ВЫБИРАЮТ ВЕДЕНИЕМ, А НЕ ТЫКОМ — см. большой комментарий к жесту ниже.
 *
 * Непере­несённые вкладки приглушены и не выбираются. Кнопка, которая выглядит рабочей и молча
 * ничего не делает, хуже честно выключенной — человек нажимает её второй и третий раз, думая, что
 * не попал. Осталась одна такая: «Поиск».
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Dimensions, Easing, PanResponder, Platform, Pressable, StyleSheet, View } from 'react-native';
import Svg, { Defs, Ellipse, RadialGradient, Stop } from 'react-native-svg';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { usePathname, useRouter, useIsFocused } from 'expo-router';
import { IconLayers, IconSearch, IconMessages, IconProfile } from './icons';
import { NAV } from '../onboarding';
import { T } from '../i18n';
import { hCommit, hTick } from '../haptics';
import { color, space } from '../theme';
import { GlassSurface } from './LiquidGlass';
import { navMin, isNavMinimized, setNavMinimized } from '../navScroll';
import { KlealAgent, Sparkle, type KlealAgentHandle } from './KlealAgent';
import { isThinking, onThinking, getNews, onNews, onAnnounce, markSeen, watchNews, type NewsTab } from '../agentState';
import { useOnb } from '../state';

export type Tab = 'intents' | 'search' | 'messages' | 'profile';

/** Что уже есть в приложении. Остальное — приглушено. */
const ROUTE: Partial<Record<Tab, string>> = {
  profile: '/profile', messages: '/messages', intents: '/activity',
  search: '/map',        // поиск на карте — app/map.tsx
};

/** Пятая цель — капля посередине. Она не вкладка, поэтому у неё свой ключ. */
type Target = Tab | 'home';

/**
 * Насколько далеко от центра знака касание ещё считается «по нему».
 *
 * Знаки стоят в 66 точках друг от друга (ряд 334 делится на пять ячеек), поэтому 30 — это чуть
 * меньше половины промежутка: зоны не смыкаются, и между ними остаётся полоска, где ничего не
 * выбирается. Так и задумано: панель отвечает на касание по знаку, а не на любое касание внизу
 * экрана. На узком экране ячейки сжимаются, зоны сходятся встык — но выбор всё равно достаётся
 * ближайшему, так что двух целей под одним пальцем не бывает.
 */
const REACH = 30;

/**
 * `dark` — вариант для тёмных экранов (планета во вкладке «Онлайн»): та же пилюля, но из
 * тёмного стекла темы, знаки светлые, выбранный — фирменный. Геометрия и жест не меняются.
 */
type NavProps = { active?: Tab; dark?: boolean };

/**
 * НАВБАР НА ANDROID ЖИВЁТ НАД ВСЕМИ ЭКРАНАМИ, а не внутри каждого.
 *
 * Размытие на Android (expo-blur) видит только содержимое `BlurTargetView`, и стекло обязано лежать
 * снаружи цели. Корневой макет оборачивает в цель весь стек экранов и рядом рисует `NavHost` — один
 * навбар на приложение. Экран, на котором навбар нужен, лишь сообщает, какая вкладка активна, пока
 * он в фокусе. На iOS всё как раньше: навбар внутри экрана, системное стекло размывает само.
 */
/**
 * Вкладка, к которой только что ушли с панели. На iOS у нового экрана своя панель, и выпрыгнуть
 * знак может только там — поэтому уходящая панель оставляет записку, а пришедшая её читает.
 */
let pendingPop: Tab | null = null;

type HostNav = { key: object; props: NavProps };
let hostNav: HostNav | null = null;
const hostSubs = new Set<() => void>();
const hostEmit = () => hostSubs.forEach((f) => f());

function NavPortal(props: NavProps) {
  const focused = useIsFocused();
  useEffect(() => {
    if (!focused) return;
    const key = {};
    hostNav = { key, props };
    hostEmit();
    return () => {
      if (hostNav?.key === key) { hostNav = null; hostEmit(); }
    };
  }, [focused, props.active, props.dark]); // eslint-disable-line react-hooks/exhaustive-deps
  // Место навбара в разметке экрана остаётся: на главной поле ввода стоит НАД панелью, и без
  // распорки оно съезжало под общий навбар. Распорка невидима и касаний не ловит.
  const insets = useSafeAreaInsets();
  return <View pointerEvents="none" style={{ height: NAV_BAR_H + Math.max(insets.bottom, space.md) }} />;
}

/** Один навбар на всё приложение (только Android) — стоит в корневом макете рядом с целью размытия. */
export function NavHost() {
  const [, bump] = useState(0);
  useEffect(() => {
    const f = () => bump((n) => n + 1);
    hostSubs.add(f);
    // Экраны монтируются РАНЬШЕ хоста (они внутри цели размытия, хост — после неё), и их эффект
    // успевает сообщить вкладку до этой подписки. Перечитываем то, что уже лежит.
    f();
    return () => { hostSubs.delete(f); };
  }, []);
  if (!hostNav) return null;
  return (
    <View pointerEvents="box-none" style={s.host}>
      <BottomNavView {...hostNav.props} />
    </View>
  );
}

export function BottomNav(props: NavProps) {
  return Platform.OS === 'android' ? <NavPortal {...props} /> : <BottomNavView {...props} />;
}

function BottomNavView({ active, dark = false }: NavProps) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  /** Где стоим — через ref: жесты панели собраны один раз (useMemo) и иначе видели бы старый путь. */
  const pathname = usePathname();
  const pathRef = useRef(pathname);
  pathRef.current = pathname;
  const nav = NAV();

  /**
   * ВЕДЕНИЕ ПАЛЬЦЕМ ВМЕСТО ЖЁСТКОГО НАЖАТИЯ.
   *
   * Знак 24×24 в пилюле высотой 48 — маленькая цель, и промахнуться по ней легко: панель у самого
   * низа экрана, где палец держат под углом. Обычное нажатие в такой ситуации либо промахивается,
   * либо требует целиться, а целиться в нижнюю панель никто не должен.
   *
   * Поэтому жест один на всю панель: коснулся где угодно, ведёшь — под пальцем поднимается тот
   * знак, к которому ты ближе всего, отпустил — он и выбран. Промахнуться становится невозможно:
   * ближайший всегда есть, и до отпускания выбор всегда видно. Это же снимает и «нажал и не понял,
   * попал ли»: ответ приходит РАНЬШЕ отпускания.
   *
   * ЖЕСТ ЖИВЁТ НА ВСЕЙ ПАНЕЛИ, А НЕ НА КАЖДОМ ЗНАКЕ. Пять отдельных обработчиков не дали бы вести:
   * палец, начавший на одном, до другого бы не дошёл — тот бы его не получил.
   *
   * КООРДИНАТЫ ЦЕЛЕЙ ЗАМЕРЯЮТСЯ, А НЕ СЧИТАЮТСЯ. Разметка гибкая (ячейки делят ширину пилюли, а
   * она — ширину экрана), и любое вычисленное «где должен быть третий знак» разошлось бы с
   * действительностью на первом же нестандартном экране. `measureInWindow` даёт настоящие центры в
   * тех же координатах, в которых приходит палец.
   */
  const [spots, setSpots] = useState<Record<string, number>>({});
  /** Вертикальные границы пилюли: за ними жест не наш. Замеряются вместе с центрами знаков. */
  const band = useRef<{ top: number; bottom: number; left: number } | null>(null);
  /** Что сейчас подсвечено. Состояние, а не ссылка: от него зависит цвет знака. */
  const [lit, setLit] = useState<Target | null>(null);
  /**
   * ГДЕ СЕЙЧАС «ПОДНЯТО» — И ЭТО НЕ ПАЛЕЦ.
   *
   * Первая версия считала увеличение прямо от координаты пальца: знак рос по мере приближения и
   * между двумя знаками оказывался наполовину поднятым обоими. Выглядело это как размазанная волна
   * — красиво в движении и бесполезно по смыслу: непонятно, что выбрано.
   *
   * Здесь значение ПРИТЯГИВАЕТСЯ к центру ближайшего знака пружиной. Палец где угодно — подъём
   * всегда ровно на знаке; перешёл границу — подъём перескочил и осел на новом. Отсюда и ощущение
   * магнита: выбор не следует за пальцем, а защёлкивается.
   *
   * Пружина жёсткая и почти без раскачки: «аккуратно магнитится» — это быстрый переход и чистая
   * остановка, а не пролёт мимо с возвратом.
   */
  const snap = useRef(new Animated.Value(-9999)).current;
  /** Держат ли панель. Пока не держат, увеличение выключено целиком. */
  const press = useRef(new Animated.Value(0)).current;
  const hot = useRef<Target | null>(null);

  const ORDER: Target[] = ['intents', 'search', 'home', 'messages', 'profile'];
  /** Новый экран открывается с развёрнутой панелью — как NAV.S1 «top». */
  useEffect(() => { setNavMinimized(false); }, []);

  /*
    «ПАРИТ» — состояние покоя агента (артефакт «Kleal Agent States», 09.10): Kleal медленно
    поднимается и опускается над своей «землёй», тень при подъёме чуть сжимается и бледнеет.
    Замер с демо: размах ~3 точки, полный цикл ~3,6 с, синус без пауз. Нативный драйвер — цикл
    идёт мимо JS и не мешает прокрутке. «Уменьшить движение» в системе — стоит на месте.
  */
  const float = useRef(new Animated.Value(0)).current;
  const [still, setStill] = useState(false);
  useEffect(() => {
    let loop: Animated.CompositeAnimation | null = null;
    let alive = true;
    const start = (reduce: boolean) => {
      setStill(reduce);
      loop?.stop();
      float.setValue(0);
      if (reduce || !alive) return;
      const half = (to: number) => Animated.timing(float, {
        toValue: to, duration: FLOAT_MS / 2, easing: Easing.inOut(Easing.sin), useNativeDriver: true,
      });
      loop = Animated.loop(Animated.sequence([half(1), half(0)]));
      loop.start();
    };
    AccessibilityInfo.isReduceMotionEnabled().then(start).catch(() => start(false));
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', start);
    return () => { alive = false; loop?.stop(); sub.remove(); };
  }, [float]);
  const floatY = float.interpolate({ inputRange: [0, 1], outputRange: [0, -FLOAT_RISE] });

  /*
    ДУМАЕТ и НОВОЕ (артефакт «Kleal Agent States»). Думает — пока идёт поиск (src/agentState.ts).
    Новое — непрочитанное в Messages и приглашения в Intents: Kleal поворачивается к вкладке и
    подпрыгивает, звёздочка летит к иконке, иконка вздрагивает, в её контуре открывается вырез с
    зелёной точкой (как у колокольчика на главной). Точка гаснет, когда раздел открыли.
  */
  const onb = useOnb();
  const meName = String(onb.profile?.name || '').trim();
  const [thinking, setThinking] = useState(isThinking());
  const [news, setNews] = useState(getNews());
  /** Точка ставится, когда звёздочка долетела; без движения — сразу. */
  const [dots, setDots] = useState<Record<NewsTab, boolean>>({ messages: getNews().messages, intents: getNews().intents });
  const agentRef = useRef<KlealAgentHandle>(null);
  const shake = useRef({ messages: new Animated.Value(0), intents: new Animated.Value(0) }).current;
  const fly = useRef(new Animated.Value(0)).current;
  const [flight, setFlight] = useState<NewsTab | null>(null);
  const stillRef = useRef(still);
  stillRef.current = still;
  const spotsRef = useRef(spots);
  spotsRef.current = spots;

  useEffect(() => onThinking(setThinking), []);
  useEffect(() => { if (meName) watchNews(meName); }, [meName]);
  useEffect(() => onNews((n) => {
    setNews(n);
    // Погасло — гасим сразу; загорелось — ждём звёздочку (см. onAnnounce).
    setDots((d) => ({ messages: n.messages && d.messages, intents: n.intents && d.intents }));
  }), []);
  useEffect(() => onAnnounce(async (tab) => {
    if (stillRef.current || spotsRef.current[tab] == null || spotsRef.current.home == null) {
      setDots((d) => ({ ...d, [tab]: true }));
      return;
    }
    await agentRef.current?.announce(tab === 'messages' ? 1 : -1);
    setFlight(tab);
    fly.setValue(0);
    Animated.timing(fly, { toValue: 1, duration: 560, easing: Easing.inOut(Easing.cubic), useNativeDriver: true }).start(() => {
      setFlight(null);
      setDots((d) => ({ ...d, [tab]: true }));
      const v = shake[tab];
      v.setValue(0);
      Animated.sequence([
        Animated.timing(v, { toValue: 1, duration: 70, useNativeDriver: true }),
        Animated.timing(v, { toValue: -1, duration: 110, useNativeDriver: true }),
        Animated.timing(v, { toValue: 0.6, duration: 100, useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: 120, useNativeDriver: true }),
      ]).start();
    });
  }), [fly, shake]);
  // Открыли раздел — увидели, что в нём.
  useEffect(() => {
    if (active === 'messages') markSeen('messages');
    if (active === 'intents') markSeen('intents');
  }, [active, news.messages, news.intents]);
  /*
    ПРУЖИННЫЙ ЗНАК (выбран Иваном 18.10.2026 из трёх живых образцов).

    Под пальцем знак СПЛЮЩИВАЕТСЯ — как кнопка из желе, которую придавили: шире и ниже. Это
    отказ от прежнего правила «знак не двигается»: панель отвечает касанию телом, а не только
    цветом. Отпустил — знак отпружинивает, а на новом экране выбранный ВЫПРЫГИВАЕТ: вытягивается
    вверх, приземляется со шлепком и оседает двумя затухающими колебаниями, уже коралловым.

    Всё на нативном драйвере. «Уменьшить движение» — ни сплющивания, ни прыжка, только цвет.
  */
  const TABS: Tab[] = ['intents', 'search', 'messages', 'profile'];
  const squash = useRef(Object.fromEntries(TABS.map((t) => [t, new Animated.Value(0)])) as Record<Tab, Animated.Value>).current;
  const pop = useRef(Object.fromEntries(TABS.map((t) => [t, new Animated.Value(1)])) as Record<Tab, Animated.Value>).current;
  useEffect(() => {
    if (stillRef.current) return;
    TABS.forEach((t) => Animated.spring(squash[t], {
      toValue: lit === t ? 1 : 0, useNativeDriver: true, damping: 11, stiffness: 520, mass: 0.5,
    }).start());
  }, [lit]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!active || pendingPop !== active) return;
    pendingPop = null;
    if (stillRef.current) return;
    const v = pop[active];
    v.setValue(0);
    // Небольшая задержка: новый экран ещё въезжает, и прыжок на полпути терялся бы в движении.
    Animated.timing(v, { toValue: 1, duration: 620, delay: 140, easing: Easing.linear, useNativeDriver: true }).start();
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps
  const jelly = (t: Tab) => {
    const q = squash[t];
    const p = pop[t];
    const IN = [0, 0.16, 0.4, 0.6, 0.8, 1];
    return [
      { translateY: Animated.add(
        q.interpolate({ inputRange: [0, 1], outputRange: [0, 1.5] }),
        p.interpolate({ inputRange: IN, outputRange: [0, 1, -7, 0, -1.2, 0] }),
      ) },
      { scaleX: Animated.multiply(
        q.interpolate({ inputRange: [0, 1], outputRange: [1, 1.16] }),
        p.interpolate({ inputRange: IN, outputRange: [1, 1.14, 0.84, 1.1, 0.97, 1] }),
      ) },
      { scaleY: Animated.multiply(
        q.interpolate({ inputRange: [0, 1], outputRange: [1, 0.82] }),
        p.interpolate({ inputRange: IN, outputRange: [1, 0.84, 1.2, 0.92, 1.03, 1] }),
      ) },
    ];
  };

  const groundScale = float.interpolate({ inputRange: [0, 1], outputRange: [1, 0.88] });
  const groundFade = float.interpolate({ inputRange: [0, 1], outputRange: [1, 0.75] });
  const canPick = (t: Target) => (t === 'home' ? true : !!ROUTE[t as Tab] && active !== t);

  /** Притянуть подсветку к цели. Расстояние всегда небольшое — соседние знаки в 66 точках друг от друга. */
  const pull = (t: Target | null) => {
    const c = t ? spots[t] : null;
    if (c == null) return;
    Animated.spring(snap, {
      toValue: c,
      useNativeDriver: true,
      damping: 20,
      stiffness: 300,
      mass: 0.6,
    }).start();
  };

  /**
   * Цель под точкой — или ничего.
   *
   * ПУСТОЕ МЕСТО ОСТАЁТСЯ ПУСТЫМ. Сначала бралась просто ближайшая цель: касание у самого края
   * экрана, в сорока точках от пилюли, выбирало крайний знак и щёлкало. Панель ловила всю полосу
   * внизу экрана и отвечала на то, что человек в неё не адресовал.
   *
   * Теперь у каждого знака своя зона в `REACH` точек, и между зонами есть промежутки, где не
   * происходит ничего. Плюс вертикальная проверка: ниже пилюли идёт отступ под домашнюю черту, и
   * касания там тоже не наши.
   */
  const nearest = (x: number, y?: number): Target | null => {
    /*
      СВЁРНУТАЯ ПАНЕЛЬ (NAV.S2) — та же разметка, уменьшенная к нижнему центру. Центры знаков
      замерены у развёрнутой, поэтому здесь их сдвигаем к середине экрана тем же множителем, а
      верх полосы опускаем на 8: иначе палец попадал бы туда, где знака уже нет.
    */
    const k = isNavMinimized() ? MIN_SCALE : 1;
    const mid = Dimensions.get('window').width / 2;
    const b = band.current;
    const top = b ? b.top + (k < 1 ? NAV_BAR_H * (1 - k) : 0) : 0;
    if (y != null && b && (y < top - 8 || y > b.bottom + 8)) return null;
    let best: Target | null = null;
    let bestD = Infinity;
    for (const t of ORDER) {
      const c0 = spots[t];
      if (c0 == null || !canPick(t)) continue;
      const c = mid + (c0 - mid) * k;
      const d = Math.abs(x - c);
      if (d <= REACH * k && d < bestD) { bestD = d; best = t; }
    }
    return best;
  };

  /**
   * «Вихрь» на Kleal, потом переход. Переход — к приземлению (~560 из 780 мс): раньше он шёл через
   * 320 мс, и прыжок с оборотом (переделан 17.10.2026) почти целиком проходил на уходящем экране.
   */
  const go = (t: Target) => {
    if (t === 'home' && !stillRef.current && agentRef.current) {
      agentRef.current.whirl();
      setTimeout(() => goNow(t), 560);
      return;
    }
    goNow(t);
  };

  const goNow = (t: Target) => {
    /*
      GR.01 «Home · Kleal prompt»: «Вход в создание: поле … или маскот в таб-баре → GR.02». На главной
      капле возвращаться некуда — она открывает разговор с Kleal. С любого другого экрана капля
      по-прежнему ведёт домой: путь «домой» в панели один, и отнимать его нельзя.
    */
    if (t === 'home' && pathRef.current === '/home') {
      router.navigate('/buddy');
      return;
    }
    if (t === 'home') {
      /*
        Не `replace`. Тот подменял ВЕРХНИЙ экран главной, оставляя всё, что под ним: из
        [главная, профиль] получалось [главная, главная], и «назад» вело на главную же.
        `dismissTo` возвращает к той главной, что уже открыта, снимая всё, что над ней.
      */
      router.dismissTo('/home');
      return;
    }
    /*
      ВКЛАДКА ВСЕГДА НА ОДНОЙ ГЛУБИНЕ, А НЕ СТОПКОЙ.

      Было `push`: каждое нажатие добавляло ЕЩЁ ОДИН экран поверх — хоть двадцать профилей подряд,
      — и потом столько же раз надо было нажать «назад». Панель видна на девяти экранах, так что
      набрать стопку можно было не заметив.

      Одного `navigate` мало, и это проверено на устройстве: он не кладёт второй ТАКОЙ ЖЕ экран, но
      чередование вкладок стопку всё равно растит. «Сообщения → профиль → сообщения» давало три
      экрана, и «назад» из сообщений вело в профиль, а не домой.

      Поэтому переход сначала СВОРАЧИВАЕТ стопку до главной, а потом открывает вкладку. Глубина
      всегда одна и та же: [главная, вкладка]. «Назад» из любой вкладки ведёт на главную.

      `dismissTo`, а не `dismissAll`: корень стопки — не главная, а вступительные слайды
      (app/index.tsx остаётся смонтированным), и «свернуть всё» выбросило бы человека туда.
    */
    pendingPop = t as Tab;
    router.dismissTo('/home');
    router.navigate(ROUTE[t as Tab] as any);
  };

  const pan = useMemo(
    () =>
      PanResponder.create({
        // Жест берётся, только если под пальцем ДЕЙСТВИТЕЛЬНО есть цель. Иначе касание проходит
        // мимо панели и достаётся тому, что под ней, — как и должно быть с пустым местом.
        onStartShouldSetPanResponder: (e) => !!nearest(e.nativeEvent.pageX, e.nativeEvent.pageY),
        onMoveShouldSetPanResponder: (e) => !!nearest(e.nativeEvent.pageX, e.nativeEvent.pageY),
        onPanResponderGrant: (e) => {
          const t = nearest(e.nativeEvent.pageX, e.nativeEvent.pageY);
          hot.current = t;
          setLit(t);
          // Первая подсветка БЕЗ пружины: иначе она летела бы через полпанели от того места, где
          // палец лежал в прошлый раз, — и это читалось бы как чужое движение.
          if (t && spots[t] != null) snap.setValue(spots[t]);
          press.setValue(1);
          /*
            ЩЕЛЧКА ПРИ КАСАНИИ НЕТ, И ЭТО ИСПРАВЛЕНИЕ. Он тут был — «взял цель». Но на обычном
            нажатии, которым панелью и пользуются в девяти случаях из десяти, получалось два
            ощущения подряд: щелчок на касании и удар на отпускании. Одно действие — один отклик.
            Щелчок остался там, где он что-то сообщает: на СМЕНЕ цели во время ведения.
          */
        },
        onPanResponderMove: (_e, g) => {
          const t = nearest(g.moveX);
          // Щелчок только на СМЕНЕ цели: щёлкать на каждом движении пальца — та же каша, что и
          // дробь без нижней границы интервала (см. src/haptics.ts).
          if (t !== hot.current) {
            hot.current = t;
            setLit(t);
            pull(t);
            if (t) hTick();
          }
        },
        onPanResponderRelease: (_e, g) => {
          const t = hot.current;
          hot.current = null;
          setLit(null);
          Animated.timing(press, { toValue: 0, duration: 160, useNativeDriver: true }).start();
          /*
            УВЕДЁННЫЙ ВНИЗ ПАЛЕЦ ОТМЕНЯЕТ ВЫБОР. Панель у самого края экрана, и «передумал» здесь
            выражается единственным доступным движением — вниз, за её пределы. Вверх не считается
            отменой: там экран, и увести туда палец легко случайно.
          */
          const away = g.dy > 44;
          if (t && !away) {
            hCommit();
            go(t);
          }
        },
        onPanResponderTerminate: () => {
          hot.current = null;
          setLit(null);
          Animated.timing(press, { toValue: 0, duration: 160, useNativeDriver: true }).start();
        },
      }),
    [spots, active]
  );

  /**
   * ПОДСВЕТКА ПОД ПАЛЬЦЕМ. (С 18.10.2026 знак под пальцем ещё и сплющивается — см. `jelly`.)
   *
   * Сначала знак под пальцем всплывал: поднимался и увеличивался. На пилюле высотой 48 это
   * читалось как прыжок из плоскости — эффектно и лишне, потому что панель не должна на себя
   * смотреть. Осталось тихое: под знаком проступает подложка, сам знак меняет цвет на фирменный.
   * Ничего не двигается, а «куда попадёшь» видно так же ясно.
   *
   * Подложка ПРИТЯНУТА к центру ближайшего знака (см. `snap`), поэтому при ведении она не
   * размазывается между двумя, а перескакивает и оседает — тот самый магнит.
   *
   * Считается интерполяцией одного значения, живёт на нативном драйвере. Множитель `press`
   * выключает подсветку целиком, когда панель не держат: без него она застыла бы там, где палец
   * оторвался.
   */
  const magnify = (cx: number | undefined, out: [number, number, number]) => {
    if (cx == null) return out[2];
    const at = snap.interpolate({
      // Узкий диапазон: горит РОВНО один знак. Подложка, растянутая на соседей, снова превратила бы
      // подсказку в размазанное пятно, от которого и уходили.
      inputRange: [cx - 40, cx - 26, cx, cx + 26, cx + 40],
      outputRange: [out[2], out[1], out[0], out[1], out[2]],
      extrapolate: 'clamp',
    });
    // rest + press × (at − rest): пока не держат, остаётся ровно `rest`.
    return Animated.add(out[2], Animated.multiply(press, Animated.add(at, -out[2])));
  };

  const spot = (key: Target) => (ref: View | null) => {
    if (!ref || spots[key] != null) return;
    ref.measureInWindow((x, _y, w) => {
      const c = x + w / 2;
      setSpots((all) => (all[key] === c ? all : { ...all, [key]: c }));
    });
  };

  const item = (tab: Tab, label: string, Icon: (p: any) => React.ReactElement) => {
    const to = ROUTE[tab];
    const on = active === tab;
    const cx = spots[tab];
    const live = canPick(tab);
    return (
      <Animated.View
        key={tab}
        ref={spot(tab) as any}
        collapsable={false}
        style={[s.slot, !to && s.off]}
      >
        {/*
          Кружок под знаком — тот самый «пузырь». Появляется вместе с подъёмом и гаснет вместе с
          ним; у выключенной вкладки его нет вовсе, и это единственный внятный способ показать, что
          вести туда некуда: волна просто обходит её стороной.
        */}
        {live ? (
          <Animated.View
            pointerEvents="none"
            style={[s.bubble, dark && s.bubbleDark, { opacity: magnify(cx, [1, 0, 0]) as any }]}
          />
        ) : null}
        {/*
          Нажатие оставлено ради читающих экраном: их «активировать» приходит отдельным событием и
          жеста панели не касается. Пальцем сюда не попадают — жест перехватывает касание раньше.
        */}
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ selected: on, disabled: !to }}
          accessibilityLabel={label}
          onPress={live ? () => go(tab) : undefined}
        >
          <Animated.View style={{
            transform: [
              ...jelly(tab),
              ...((tab === 'messages' || tab === 'intents')
                ? [{ rotate: shake[tab].interpolate({ inputRange: [-1, 1], outputRange: ['-14deg', '14deg'] }) }]
                : []),
            ] as any,
          }}>
            <Icon size={24} c={on || lit === tab ? color.primary : (dark ? 'rgba(255,255,255,0.62)' : color.muted)} />
            {(tab === 'messages' || tab === 'intents') && dots[tab] && !on ? (
              /* Вырез в линии иконки — кольцо цвета капсулы вокруг зелёной точки. */
              <View pointerEvents="none" style={[s.newDot, dark && s.newDotDark]} />
            ) : null}
          </Animated.View>
        </Pressable>
      </Animated.View>
    );
  };

  /*
    СВОРАЧИВАНИЕ (NAV.S2) — масштаб 0,833 к нижнему центру: на борде свёрнутая панель — ровно
    развёрнутая в этом масштабе (капсулы 135→112, высота 48→40, Kleal 56→46), низ остаётся на
    месте. Масштаб и сдвиг на нативном драйвере, разметка не пересчитывается.
  */
  const scale = navMin.interpolate({ inputRange: [0, 1], outputRange: [1, MIN_SCALE] });
  const lift = navMin.interpolate({ inputRange: [0, 1], outputRange: [0, (NAV_BAR_H * (1 - MIN_SCALE)) / 2] });

  return (
    <View style={[s.wrap, { paddingBottom: Math.max(insets.bottom, space.md) }]} {...pan.panHandlers}>
      <Animated.View
        style={[s.row, { transform: [{ translateY: lift }, { scale }] }]}
        // Границы панели по вертикали — чтобы касание ниже неё, в отступе под домашнюю черту, не
        // считалось нажатием по панели.
        ref={(r: any) => {
          if (!r || band.current) return;
          r.measureInWindow?.((_x: number, y: number, _w: number, h: number) => {
            band.current = { top: y, bottom: y + h, left: _x };
          });
        }}
        collapsable={false}
      >
        {/*
          NAVIGATION V2 (борд «Navigation V2 · Scroll», 7145:124875): две стеклянные капсулы по два
          знака, между ними Kleal на своей тени. Стекло — подложкой под рядом, а не обёрткой ряда
          (почему — в комментарии к `pill`). `pointerEvents="none"`: касания достаются жесту панели.
        */}
        <View style={s.pill} collapsable={false}>
          <GlassSurface tone={dark ? 'dark' : 'light'} radius={999} pointerEvents="none" backdrop style={StyleSheet.absoluteFill} />
          {item('intents', nav[0], IconLayers)}
          {item('search', nav[1], IconSearch)}
        </View>

        {/*
          KLEAL — НЕ В КАПСУЛЕ, А МЕЖДУ НИМИ, стоит на «земле»: три размытых эллипса под ним
          (свет кораллом, полутень, контактная тень) — как на борде. Персонаж выше ячейки и поровну
          выходит вверх; ячейка 56×48 с отступом 8 снизу, как слой «kleal».
        */}
        <View ref={spot('home') as any} collapsable={false} style={s.kleal}>
          <Animated.View pointerEvents="none" style={[s.ground, { opacity: groundFade, transform: [{ scale: groundScale }] }]}>
          <Svg width={GROUND_W + 12} height={GROUND_H + 12}>
            <Defs>
              <RadialGradient id="gl" cx="50%" cy="50%" rx="50%" ry="50%">
                <Stop offset="0" stopColor="#FF385C" stopOpacity={0.26} />
                <Stop offset="0.6" stopColor="#FF385C" stopOpacity={0.1} />
                <Stop offset="1" stopColor="#FF385C" stopOpacity={0} />
              </RadialGradient>
              <RadialGradient id="gp" cx="50%" cy="50%" rx="50%" ry="50%">
                <Stop offset="0" stopColor="#702E5C" stopOpacity={0.15} />
                <Stop offset="1" stopColor="#702E5C" stopOpacity={0} />
              </RadialGradient>
              <RadialGradient id="gc" cx="50%" cy="50%" rx="50%" ry="50%">
                <Stop offset="0" stopColor="#5C223E" stopOpacity={0.34} />
                <Stop offset="1" stopColor="#5C223E" stopOpacity={0} />
              </RadialGradient>
            </Defs>
            {/* Размытие слоёв на борде (6/5/4) — здесь шире самих эллипсов с мягким краем градиента. */}
            <Ellipse cx={(GROUND_W + 12) / 2} cy={(GROUND_H + 12) / 2} rx={GROUND_W / 2 + 6} ry={GROUND_H / 2 + 6}
                     fill="url(#gl)" opacity={0.4 * 0.73} />
            <Ellipse cx={(GROUND_W + 12) / 2} cy={(GROUND_H + 12) / 2} rx={20 + 5} ry={5 + 5} fill="url(#gp)" opacity={0.73} />
            <Ellipse cx={(GROUND_W + 12) / 2} cy={(GROUND_H + 12) / 2 + 0.5} rx={9 + 4} ry={2 + 3} fill="url(#gc)" opacity={0.73} />
          </Svg>
          </Animated.View>
          <Animated.View
            pointerEvents="none"
            style={[s.dropLit, dark && s.bubbleDark, { opacity: magnify(spots.home, [1, 0, 0]) as any }]}
          />
          <Animated.View style={{ transform: [{ translateY: floatY }] }}>
            <Pressable accessibilityRole="button" accessibilityLabel={NAV_FAB()} onPress={() => go('home')}>
              <KlealAgent ref={agentRef} width={DROP} thinking={thinking} still={still} />
            </Pressable>
          </Animated.View>
        </View>

        <View style={s.pill} collapsable={false}>
          <GlassSurface tone={dark ? 'dark' : 'light'} radius={999} pointerEvents="none" backdrop style={StyleSheet.absoluteFill} />
          {item('messages', nav[2], IconMessages)}
          {item('profile', nav[3], IconProfile)}
        </View>

        {/* Звёздочка летит от Kleal к иконке, где появилось новое. Дугой, сверху. */}
        {flight && band.current && spots.home != null && spots[flight] != null ? (() => {
          const x0 = spots.home - band.current.left - 4.5;
          const x1 = (spots[flight] as number) - band.current.left + 6;
          return (
            <Animated.View pointerEvents="none" style={[s.flyer, {
              opacity: fly.interpolate({ inputRange: [0, 0.12, 0.85, 1], outputRange: [0, 1, 1, 0] }),
              transform: [
                { translateX: fly.interpolate({ inputRange: [0, 1], outputRange: [x0, x1] }) },
                { translateY: fly.interpolate({ inputRange: [0, 0.5, 1], outputRange: [-2, -20, 6] }) },
                { scale: fly.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0.8, 1.25, 0.7] }) },
              ],
            }]}>
              <Sparkle size={10} c={color.primary} />
            </Animated.View>
          );
        })() : null}
      </Animated.View>
    </View>
  );
}

/**
 * Центральная кнопка — это «домой», а не «создать интент». Интент заводится текстом на главной
 * («Чем хочешь заняться?») или карточкой, а самая крупная кнопка панели нужна, чтобы одним
 * движением вернуться из любого места приложения.
 */
const NAV_FAB = () => T('Главная', 'Home', 'Inicio');

// ===== вид
/**
 * Размеры пилюли из борда (кадр GR.01 «Test 260930», слой «Navigation Bar»): 350×48 при ширине
 * экрана 390, то есть по 20 с каждой стороны. Наружу отданы для экранов, которые ставят что-то над
 * панелью: высота всей панели = `NAV_BAR_H` + max(нижняя безопасная зона, 12).
 */
export const NAV_BAR_H = 48;
/** NAV.S1: по 16 от краёв, 16 между капсулами и Kleal (390 = 16+135+16+56+16+135+16). */
export const NAV_SIDE = space.lg;
/** NAV.S2 «Minimized» ÷ NAV.S1 «Expanded»: 112/135, 40/48, 46/56. */
const MIN_SCALE = 40 / 48;
/** «Парит»: полный цикл подъёма и спуска и высота подъёма (замер с демо артефакта). */
const FLOAT_MS = 3600;
const FLOAT_RISE = 3;
/** «Земля» под Kleal — слой «ground · light» 44×14. */
const GROUND_W = 44;
const GROUND_H = 14;
/**
 * Ширина капли.
 *
 * В кадре её слой 42×44, но это РАМКА слоя, а не видимое пятно: у выгруженной картинки по краям
 * прозрачные поля, и при ширине 42 розовое пятно выходило 28 точек против 33 в кадре. Число
 * подобрано замером: сняли панель с экрана, положили рядом с кадром в одном масштабе и сравнили
 * границы пятна, а не рамки.
 */
const DROP = 48;

const s = StyleSheet.create({
  wrap: { paddingHorizontal: NAV_SIDE, alignItems: 'center' },
  host: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  row: { width: '100%', height: NAV_BAR_H, flexDirection: 'row', alignItems: 'center', gap: 16 },
  flyer: { position: 'absolute', left: 0, top: 0 },
  /** «Новое» на иконке: зелёная точка #1FAE5E (как у колокольчика на главной) в вырезе цвета капсулы. */
  newDot: {
    position: 'absolute', top: -1, right: -2, width: 9, height: 9, borderRadius: 5,
    backgroundColor: '#1FAE5E', borderWidth: 2, borderColor: '#FBF8F5',
  },
  newDotDark: { borderColor: '#2A2C33' },
  /** Капсула 135×48: отступ 8, два знака по 59,5 (ячейка 12/4/12). Плёнка 49% — в GlassSurface. */
  pill: { flex: 1, height: NAV_BAR_H, flexDirection: 'row', alignItems: 'center', padding: space.sm },
  /** Ячейка Kleal 56×48, отступ 8 снизу — персонаж стоит над «землёй». */
  kleal: { width: 56, height: NAV_BAR_H, paddingBottom: 8, alignItems: 'center', justifyContent: 'center' },
  ground: { position: 'absolute', left: (56 - GROUND_W - 12) / 2, top: 40 - 6 },
  /*
    КАПСУЛЫ — СТЕКЛО, А НЕ БЕЛАЯ КАРТОЧКА (было про одну пилюлю, в V2 их две — правила те же).

    Сплошная белая заливка здесь была по старому кадру A.15: там под белым на 72% лежал второй,
    сплошной белый слой, и вместе они давали просто белое. Оба борда, по которым панель собирается
    теперь, — «GR · Offline — new layout» и GR.01 в «Test 260930», — рисуют её иначе: один слой
    стекла (эффект GLASS) с белой плёнкой на 49%, 350 в ширину, без сплошной подложки. Сквозь неё
    проступает тёплый фон экрана, и панель читается частью сцены, а не наклейкой поверх неё.

    Отсюда `GlassSurface tone="light"`: его оттенок — белое на 46%, на глаз не отличить от 49% борда,
    а светлая кромка у системного стекла своя. На Android и iOS до 26 тот же компонент сам собирает
    запасной путь — размытие подложки, плёнку и волосяную кромку; панели знать об этом не нужно.
    Тёмный вариант — то же стекло тоном `dark`.

    СТЕКЛО — ОТДЕЛЬНЫЙ СЛОЙ ПОД РЯДОМ, А НЕ ЕГО ОБЁРТКА. У стекла `overflow: hidden` (иначе
    скругление не режет эффект), и всё, что лежало бы внутри, срезалось бы по кромке — а подложка
    под каплей (56) выше самой пилюли (48). Ряд лежит над стеклом соседом, и у него `overflow` не
    скрыт намеренно.

    НЕПРОЗРАЧНОСТЬ У ПАНЕЛИ И ЕЁ ПРЕДКОВ НЕ ТРОГАТЬ: системное стекло не рисуется вовсе, если у
    него или у любого предка opacity < 1 (см. LiquidGlass.tsx). Гаснут и загораются только подложки
    под знаками и приглушённые ячейки — стеклу они соседи, а не предки.

    ТЕНИ У ПИЛЮЛИ НЕТ: в обоих кадрах у панели один эффект стекла. На Android `elevation` к тому
    же просвечивает сквозь полупрозрачную плёнку и делает стекло грязно-серым (см. Glass.tsx).
  */
  /** Ячейка знака: капсула делится на два равных места (59,5 в NAV.S1), доли, а не число. */
  slot: { flex: 1, height: 32, alignItems: 'center', justifyContent: 'center' },
  off: { opacity: 0.38 },
  /*
    Подложка под знаком — единственный признак того, что палец здесь. Цвет нейтральный, а не
    фирменный: фирменным становится сам знак, и две красные вещи одна на другой слились бы в пятно.
  */
  bubble: {
    position: 'absolute',
    width: 40,
    height: 32,
    borderRadius: 12,
    backgroundColor: color.neutral100,
  },
  bubbleDark: { backgroundColor: 'rgba(255,255,255,0.10)' },
  /*
    То же под каплей, только круглое и чуть шире её: капля сама по себе не меняет вида.

    СВОЕЙ ТЕНИ У КАПЛИ НЕТ, И ЭТО ИСПРАВЛЕНИЕ. Была фирменная: `shadowColor` красный, радиус 12.
    Под прозрачной картинкой iOS считает тень по её альфе, и на мягком крае капли это давало две
    вещи, которых в кадре нет вовсе, — чёткую светлую обводку по контуру и розовое свечение,
    вытекающее из-под панели вниз. Мягкая тень у капли уже нарисована в самой картинке.
  */
  dropLit: {
    position: 'absolute',
    width: DROP + 8,
    height: DROP + 8,
    borderRadius: (DROP + 8) / 2,
    backgroundColor: color.neutral100,
  },
});
