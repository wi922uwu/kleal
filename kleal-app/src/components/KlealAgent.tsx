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
 * «Уменьшить движение» (`still`): ничего не движется; панель всё равно ставит точку «новое».
 */
import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
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
        Animated.timing(spinV, { toValue: 1, duration: 620, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
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
    const whirlTurn = spinV.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
    const whirlScale = spinV.interpolate({ inputRange: [0, 0.35, 1], outputRange: [1, 0.82, 1] });
    const whirlLift = spinV.interpolate({ inputRange: [0, 0.35, 1], outputRange: [0, -6, 0] });
    const burst = spinV.interpolate({ inputRange: [0, 0.25, 1], outputRange: [0, 1, 0] });
    const burstR = spinV.interpolate({ inputRange: [0, 1], outputRange: [width * 0.3, width * 0.85] });

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

        {/* Россыпь звёздочек «Вихря» — четыре луча от центра, гаснут к концу оборота. */}
        {[0, 90, 180, 270].map((a) => (
          <Animated.View key={a} pointerEvents="none" style={[st.orbit, { opacity: burst, transform: [{ rotate: `${a + 45}deg` }] }]}>
            <Animated.View style={{ transform: [{ translateX: burstR }, { rotate: `${-(a + 45)}deg` }] }}>
              <Sparkle size={8} c="#FF385C" />
            </Animated.View>
          </Animated.View>
        ))}
        <Animated.View style={{ width, height, transform: [
          { translateY: Animated.add(lift, whirlLift) }, { rotate: tilt }, { rotate: whirlTurn }, { scale: whirlScale },
        ] }}>
          <Image accessibilityIgnoresInvertColors source={require('../../assets/art/logo-mark-body.png')}
                 style={{ width, height }} resizeMode="contain" />
          {EYES.map((cx) => (
            <Animated.View key={cx} pointerEvents="none" style={{
              position: 'absolute',
              left: (cx - EYE_W / 2) * k, top: (EYE_Y - EYE_H / 2) * k,
              width: EYE_W * k, height: EYE_H * k, borderRadius: EYE_W * k,
              backgroundColor: '#000', transform: [{ translateX: eyeShift }],
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
  orbit: { position: 'absolute', width: 0, height: 0, alignItems: 'center', justifyContent: 'center' },
});
