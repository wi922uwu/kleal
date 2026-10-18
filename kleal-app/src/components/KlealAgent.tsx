/**
 * Kleal в нижней панели — живой: глаза отдельным слоем поверх тела (артефакт «Kleal Agent States»).
 *
 * Тело — та же картинка, что и знак (assets/art/logo-mark.png), но без глаз (logo-mark-body.png:
 * глаза закрашены по соседним пикселям, фон там — гладкий градиент). Глаза — два чёрных эллипса
 * в тех же местах и тех же размерах, что на знаке: в покое Kleal выглядит ровно как раньше.
 *
 * ДУМАЕТ (`thinking`): оглядывается влево-вправо, слегка наклоняет голову, вокруг медленно ходит
 * звёздочка, коралловое свечение тихо дышит. По кругу, пока поиск не закончится.
 *
 * НОВОЕ (`announce(dir)`): смотрит и поворачивается к вкладке (−1 — влево, к Intents; +1 — вправо,
 * к Messages) и подпрыгивает. Звёздочку к иконке запускает панель — она знает, где иконка.
 *
 * ВИХРЬ (`whirl()`, нажатие на Kleal на главной) — переделан 17.10.2026 по слову владельца: раньше
 * Kleal крутился колесом в плоскости экрана («по кругу вертикально»), а должен «чуть подпрыгивать
 * и как вихрь крутиться по своей оси, и во время оборота глаза тоже уходят». Теперь:
 *   прыжок — присел (сплющился), вытянулся в полёте, приземлился с отскоком; тень под ним
 *            сжимается, пока он в воздухе — так прыжок читается, а не просто сдвиг вверх;
 *   вихрь  — два оборота вокруг ВЕРТИКАЛЬНОЙ оси, как волчок. Тело — шар, поэтому само не
 *            сужается; вращение показывают глаза и блики: это точки на поверхности шара, они
 *            бегут по кругу x = R·sin(φ+θ), на краю сжимаются (cos) и уходят за спину, потом
 *            выходят с другой стороны.
 * Всё считается из одного счётчика 0→1 таблицами точек (нативный драйвер не умеет sin/cos).
 *
 * «Уменьшить движение» (`still`): ничего не движется; панель всё равно ставит точку «новое».
 */
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { Animated, Easing, Image, StyleSheet, View } from 'react-native';
import Svg, { Defs, Path, RadialGradient, Stop, Circle } from 'react-native-svg';

/** Размеры исходной картинки и глаз на ней (замер по logo-mark.png, 558×501). */
const SRC_W = 558;
const SRC_H = 501;
const EYE_W = 63;
const EYE_H = 75;
const EYES = [178.15, 308.1];
const EYE_Y = 151.3;

export type KlealAgentHandle = { announce: (dir: -1 | 1) => Promise<void>; whirl: () => void };

/** Шар тела на картинке: центр по горизонтали и радиус (замер по logo-mark.png). */
const BODY_CX = 279;
const BODY_R = 235;
/** Длина вихря. Панель уходит на другой экран к приземлению (BottomNav, WHIRL_NAV_MS). */
const WHIRL_MS = 780;
/** Сколько оборотов делает вихрь. */
const TURNS = 2;
/** Таблица значений счётчика: по ней строятся все кривые вихря. */
const N = 64;
const TS = Array.from({ length: N + 1 }, (_, i) => i / N);
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const easeInOut = (v: number) => (v < 0.5 ? 4 * v * v * v : 1 - Math.pow(-2 * v + 2, 3) / 2);
const easeOut = (v: number) => 1 - Math.pow(1 - v, 3);
const easeIn = (v: number) => v * v * v;
/** Угол поворота (рад) в момент t: вращение — от 10 до 90 % времени, разгон и торможение. */
const angleAt = (t: number) => easeInOut(clamp01((t - 0.1) / 0.8)) * TURNS * 2 * Math.PI;
/** Огибающая «идёт вращение»: 0 в покое, 1 в середине — для бликов. */
const spinEnv = (t: number) => Math.sin(Math.PI * clamp01((t - 0.1) / 0.8));
/** Высота прыжка в долях от наибольшей: присед, взлёт, падение, маленький отскок. */
function hopAt(t: number) {
  if (t < 0.12) return -0.15 * Math.sin((Math.PI / 2) * (t / 0.12));          // присел
  if (t < 0.5) return -0.15 + 1.15 * easeOut((t - 0.12) / 0.38);               // вверх
  if (t < 0.84) return 1 - easeIn((t - 0.5) / 0.34);                            // вниз
  return 0.14 * Math.sin(Math.PI * ((t - 0.84) / 0.16));                        // отскок
}
/** Сжатие тела: присел — шире и ниже, в полёте — уже и выше, удар о землю — снова шире. */
function squashAt(t: number): [number, number] {
  if (t < 0.12) { const p = Math.sin((Math.PI / 2) * (t / 0.12)); return [1 + 0.1 * p, 1 - 0.12 * p]; }
  if (t < 0.84) { const p = Math.sin(Math.PI * clamp01((t - 0.12) / 0.72)); return [1 - 0.05 * p, 1 + 0.07 * p]; }
  const p = Math.sin(Math.PI * ((t - 0.84) / 0.16)); return [1 + 0.09 * p, 1 - 0.1 * p];
}

/** Четырёхлучевая звёздочка ✦ — та же, что в артефакте. */
export function Sparkle({ size = 9, c = '#FFFFFF' }: { size?: number; c?: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 10 10">
      <Path d="M5 0 C5.4 3.2 6.8 4.6 10 5 C6.8 5.4 5.4 6.8 5 10 C4.6 6.8 3.2 5.4 0 5 C3.2 4.6 4.6 3.2 5 0 Z" fill={c} />
    </Svg>
  );
}

export const KlealAgent = forwardRef<KlealAgentHandle, { width: number; thinking: boolean; still: boolean }>(
  function KlealAgent({ width, thinking, still }, ref) {
    const k = width / SRC_W;
    const height = SRC_H * k;
    /** Взгляд: −1 влево … +1 вправо. Наклон и поворот головы идут за ним. */
    const gaze = useRef(new Animated.Value(0)).current;
    const hop = useRef(new Animated.Value(0)).current;
    const think = useRef(new Animated.Value(0)).current;   // 0..1 — видимость свечения и звёздочки
    const breathe = useRef(new Animated.Value(0)).current;
    const orbit = useRef(new Animated.Value(0)).current;
    /** «Вихрь» при нажатии: 0→1 — полный оборот с поджатием и россыпью звёздочек. */
    const spinV = useRef(new Animated.Value(0)).current;
    /**
     * Картинка тела ещё не показана. Каждый экран рисует свою панель, и картинка у новой панели
     * появляется не сразу (в Expo Go — до ~0,5 с с Metro): маскот стоял одними глазами. Пока её нет,
     * под ней — нарисованный шар того же градиента; показалась — шар убираем.
     */
    const [bodyReady, setBodyReady] = useState(false);

    // ---- ДУМАЕТ: петли, пока идёт поиск
    useEffect(() => {
      if (!thinking || still) {
        Animated.parallel([
          Animated.timing(think, { toValue: 0, duration: 260, useNativeDriver: true }),
          Animated.timing(gaze, { toValue: 0, duration: 260, useNativeDriver: true }),
        ]).start();
        return;
      }
      Animated.timing(think, { toValue: 1, duration: 260, useNativeDriver: true }).start();
      const look = (to: number, ms: number) =>
        Animated.timing(gaze, { toValue: to, duration: ms, easing: Easing.inOut(Easing.cubic), useNativeDriver: true });
      // Оглядывается: влево, задержался, вправо, задержался, прямо — и снова. ~3,2 с на круг.
      const scan = Animated.loop(Animated.sequence([
        look(-1, 380), Animated.delay(520), look(1, 520), Animated.delay(520), look(0, 380), Animated.delay(880),
      ]));
      const breath = Animated.loop(Animated.sequence([
        Animated.timing(breathe, { toValue: 1, duration: 1100, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
        Animated.timing(breathe, { toValue: 0, duration: 1100, easing: Easing.inOut(Easing.sin), useNativeDriver: true }),
      ]));
      orbit.setValue(0);
      const spin = Animated.loop(Animated.timing(orbit, { toValue: 1, duration: 3400, easing: Easing.linear, useNativeDriver: true }));
      scan.start(); breath.start(); spin.start();
      return () => { scan.stop(); breath.stop(); spin.stop(); };
    }, [thinking, still, gaze, think, breathe, orbit]);

    // ---- НОВОЕ: повернуться к вкладке и подпрыгнуть
    useImperativeHandle(ref, () => ({
      whirl: () => {
        if (still) return;
        spinV.setValue(0);
        // Счётчик линейный: форма движения — в таблицах (hopAt, angleAt, squashAt).
        Animated.timing(spinV, { toValue: 1, duration: WHIRL_MS, easing: Easing.linear, useNativeDriver: true }).start();
      },
      announce: (dir) => new Promise<void>((resolve) => {
        if (still) { resolve(); return; }
        Animated.sequence([
          Animated.timing(gaze, { toValue: dir, duration: 200, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
          Animated.timing(hop, { toValue: 1, duration: 170, easing: Easing.out(Easing.quad), useNativeDriver: true }),
          Animated.spring(hop, { toValue: 0, damping: 9, stiffness: 260, mass: 0.6, useNativeDriver: true }),
        ]).start(() => {
          resolve();
          // Ещё мгновение смотрит туда, куда показал, и возвращает взгляд.
          Animated.sequence([
            Animated.delay(700),
            Animated.timing(gaze, { toValue: 0, duration: 320, easing: Easing.inOut(Easing.cubic), useNativeDriver: true }),
          ]).start();
        });
      }),
    }), [still, gaze, hop, spinV]);

    const eyeShift = gaze.interpolate({ inputRange: [-1, 1], outputRange: [-2.2 * width / 48, 2.2 * width / 48] });
    const tilt = gaze.interpolate({ inputRange: [-1, 1], outputRange: ['-7deg', '7deg'] });
    const lift = hop.interpolate({ inputRange: [0, 1], outputRange: [0, -9] });
    const glowOpacity = Animated.multiply(think, breathe.interpolate({ inputRange: [0, 1], outputRange: [0.45, 0.85] }));
    const glowScale = breathe.interpolate({ inputRange: [0, 1], outputRange: [0.92, 1.1] });
    const turn = orbit.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
    const R = width * 0.62;
    /** Радиус шара тела на экране — по нему бегут глаза и блики вихря. */
    const RB = BODY_R * k;
    // ---- ВИХРЬ: кривые из таблиц (см. шапку файла). Один раз на размер: панель перерисовывается
    // часто, а это ~650 точек интерполяции.
    const { whirlLift, whirlSX, whirlSY, eyes, streaks, shadowS, shadowO } = useMemo(() => {
      const HOP = width * 0.3;            // высота прыжка — ~треть роста, «чуть подпрыгнуть»
      const tbl = (f: (t: number) => number) => spinV.interpolate({ inputRange: TS, outputRange: TS.map(f) });
      const whirlLift = tbl((t) => -HOP * hopAt(t));
      const whirlSX = tbl((t) => squashAt(t)[0]);
      const whirlSY = tbl((t) => squashAt(t)[1]);
      /** Точка на шаре с долготой φ: сдвиг от исходного места, сжатие и видимость (спереди или за спиной). */
      const onSphere = (phi: number) => ({
        dx: tbl((t) => RB * (Math.sin(phi + angleAt(t)) - Math.sin(phi))),
        sx: tbl((t) => Math.max(0.02, Math.cos(phi + angleAt(t)))),
        op: tbl((t) => clamp01(Math.cos(phi + angleAt(t)) * 5)),
      });
      const eyes = EYES.map((cx) => onSphere(Math.asin((cx - BODY_CX) / BODY_R)));
      /** Блики-полосы на поверхности: видны только во время вращения и только спереди. */
      const streaks = [
        { phi: Math.PI, y: 0.36, w: 0.34 },
        { phi: Math.PI * 0.35, y: 0.6, w: 0.42 },
        { phi: -Math.PI * 0.6, y: 0.8, w: 0.26 },
      ].map((st) => ({
        ...st,
        dx: tbl((t) => RB * Math.sin(st.phi + angleAt(t))),
        sx: tbl((t) => Math.max(0.02, Math.cos(st.phi + angleAt(t)))),
        op: tbl((t) => 0.55 * spinEnv(t) * clamp01(Math.cos(st.phi + angleAt(t)) * 3)),
      }));
      /** Тень под Kleal: в воздухе меньше и бледнее, при ударе о землю — шире. */
      const shadowS = tbl((t) => 1 - 0.45 * Math.max(0, hopAt(t)));
      const shadowO = tbl((t) => (t <= 0 || t >= 1 ? 0 : 0.28 * (1 - 0.6 * Math.max(0, hopAt(t)))));

      return { whirlLift, whirlSX, whirlSY, eyes, streaks, shadowS, shadowO };
    }, [width, spinV, k, height]);

    return (
      <View style={{ width, height, alignItems: 'center', justifyContent: 'center' }} pointerEvents="box-none">
        {/* Коралловое свечение — под телом, только пока думает. */}
        <Animated.View pointerEvents="none"
          style={[st.glow, { width: width * 2, height: width * 2, opacity: glowOpacity, transform: [{ scale: glowScale }] }]}>
          <Svg width="100%" height="100%" viewBox="0 0 100 100">
            <Defs>
              <RadialGradient id="kg" cx="50%" cy="50%" rx="50%" ry="50%">
                {/* Тело закрывает середину — видимое кольцо от ~0,5 радиуса, там свечение и должно быть заметно. */}
                <Stop offset="0" stopColor="#FF385C" stopOpacity={0.6} />
                <Stop offset="0.5" stopColor="#FF385C" stopOpacity={0.42} />
                <Stop offset="0.75" stopColor="#FF385C" stopOpacity={0.14} />
                <Stop offset="1" stopColor="#FF385C" stopOpacity={0} />
              </RadialGradient>
            </Defs>
            <Circle cx={50} cy={50} r={50} fill="url(#kg)" />
          </Svg>
        </Animated.View>

        {/* Тень под Kleal — видна только в прыжке. */}
        {/* Мягкое пятно с размытым краем: сплошной овал читался серой полоской под панелью. */}
        <Animated.View pointerEvents="none" style={[st.shadow, {
          width: width * 0.8, height: width * 0.2, top: height - width * 0.12,
          opacity: shadowO, transform: [{ scaleX: shadowS }],
        }]}>
          <Svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
            <Defs>
              <RadialGradient id="ksh" cx="50%" cy="50%" rx="50%" ry="50%">
                <Stop offset="0" stopColor="#5A2A3A" stopOpacity={1} />
                <Stop offset="0.6" stopColor="#5A2A3A" stopOpacity={0.45} />
                <Stop offset="1" stopColor="#5A2A3A" stopOpacity={0} />
              </RadialGradient>
            </Defs>
            <Circle cx={50} cy={50} r={50} fill="url(#ksh)" />
          </Svg>
        </Animated.View>
        <Animated.View style={{ width, height, transform: [
          { translateY: Animated.add(lift, whirlLift) }, { rotate: tilt },
          // Точка сжатия — низ: присед и удар о землю идут от земли, а не от середины.
          { translateY: height / 2 }, { scaleX: whirlSX }, { scaleY: whirlSY }, { translateY: -height / 2 },
        ] }}>
          {!bodyReady ? (
            <Svg width={width} height={height} viewBox={`0 0 ${SRC_W} ${SRC_H}`} style={StyleSheet.absoluteFill} pointerEvents="none">
              <Defs>
                <RadialGradient id="kbody" cx="38%" cy="30%" rx="75%" ry="80%">
                  <Stop offset="0" stopColor="#F7838F" />
                  <Stop offset="0.6" stopColor="#F27FA6" />
                  <Stop offset="1" stopColor="#EC8BD6" />
                </RadialGradient>
              </Defs>
              <Circle cx={BODY_CX} cy={232} r={BODY_R * 0.97} fill="url(#kbody)" />
            </Svg>
          ) : null}
          <Image accessibilityIgnoresInvertColors source={require('../../assets/art/logo-mark-body.png')}
                 style={{ width, height }} resizeMode="contain"
                 onLoad={() => setBodyReady(true)} onError={() => setBodyReady(false)} />
          {/* Блики вращения — короткие светлые полосы по шару. */}
          {streaks.map((sk) => (
            <Animated.View key={sk.phi} pointerEvents="none" style={{
              position: 'absolute', left: BODY_CX * k - (sk.w * RB) / 2, top: sk.y * height,
              width: sk.w * RB, height: Math.max(2, width * 0.045), borderRadius: width,
              backgroundColor: '#FFFFFF', opacity: sk.op,
              transform: [{ translateX: sk.dx }, { scaleX: sk.sx }],
            }} />
          ))}
          {EYES.map((cx, i) => (
            <Animated.View key={cx} pointerEvents="none" style={{
              position: 'absolute',
              left: (cx - EYE_W / 2) * k, top: (EYE_Y - EYE_H / 2) * k,
              width: EYE_W * k, height: EYE_H * k, borderRadius: EYE_W * k,
              backgroundColor: '#000', opacity: eyes[i].op,
              // Взгляд (думает/новое) + бег по шару при вихре; на краю глаз сжимается и уходит за спину.
              transform: [{ translateX: Animated.add(eyeShift, eyes[i].dx) }, { scaleX: eyes[i].sx }],
            }} />
          ))}
        </Animated.View>

        {/* Звёздочка по кругу — пока думает. Круг сплющен: ходит «вокруг», а не над головой. */}
        <Animated.View pointerEvents="none" style={[st.orbit, { opacity: think, transform: [{ scaleY: 0.55 }, { rotate: turn }] }]}>
          <View style={{ transform: [{ translateX: R }] }}>
            <Animated.View style={{ transform: [{ rotate: Animated.multiply(orbit, -360).interpolate({ inputRange: [-360, 0], outputRange: ['-360deg', '0deg'] }) }, { scaleY: 1 / 0.55 }] }}>
              {/* На кремовой панели белая звёздочка демо не видна — коралловая. */}
              <Sparkle size={10} c="#FF385C" />
            </Animated.View>
          </View>
        </Animated.View>
      </View>
    );
  }
);

const st = StyleSheet.create({
  glow: { position: 'absolute' },
  shadow: { position: 'absolute' },
  orbit: { position: 'absolute', width: 0, height: 0, alignItems: 'center', justifyContent: 'center' },
});
