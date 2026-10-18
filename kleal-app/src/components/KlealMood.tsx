/**
 * Kleal с эмоциями — для экрана «Ищем» (GR.13). Добавлен 18.10.2026 по слову Ивана: «на экране
 * поиска, когда идёт загрузка, у Kleal должны быть эмоции». Раньше там стояла неподвижная картинка.
 *
 * Тело — та же картинка без глаз, что у живого Kleal в навбаре (logo-mark-body.png), глаза —
 * отдельным слоем в тех же местах. Эмоции читаются глазами и телом, без рта и бровей у самого знака:
 *
 *   оглядывается — глаза уходят влево и вправо, голова наклоняется за взглядом;
 *   моргает      — глаза схлопываются по вертикали;
 *   задумался    — смотрит вверх, прищур, рядом зажигается звёздочка;
 *   «есть идея!» — глаза-дуги ^ ^, подпрыгивает;
 *   переживает   — когда поиск дольше обычного (`slow`): смотрит вниз, глаза грустнеют
 *                  (верх срезан наискосок «бровью» цвета тела), тихо покачивается.
 *
 * Цикл ~7 с, по кругу, пока экран открыт. «Уменьшить движение» — стоит как картинка.
 */
import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Image, StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { Sparkle } from './KlealAgent';
import { color } from '../theme';

/** Замер по logo-mark.png, 558×501 (как в KlealAgent). */
const SRC_W = 558;
const SRC_H = 501;
const EYE_W = 63;
const EYE_H = 75;
const EYES = [178.15, 308.1];
const EYE_Y = 151.3;

export function KlealMood({ width, slow = false }: { width: number; slow?: boolean }) {
  const k = width / SRC_W;
  const height = SRC_H * k;
  const gx = useRef(new Animated.Value(0)).current;     // взгляд −1…1 по горизонтали
  const gy = useRef(new Animated.Value(0)).current;     // −1 вверх … 1 вниз
  const open = useRef(new Animated.Value(1)).current;   // раскрытие глаз
  const happy = useRef(new Animated.Value(0)).current;  // 0 — овалы, 1 — дуги ^ ^
  const hop = useRef(new Animated.Value(0)).current;
  const idea = useRef(new Animated.Value(0)).current;   // звёздочка
  const sad = useRef(new Animated.Value(0)).current;    // грустные «брови»
  const sway = useRef(new Animated.Value(0)).current;
  const [still, setStill] = useState(false);

  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled().then((r) => alive && setStill(r)).catch(() => {});
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    const all = [gx, gy, open, happy, hop, idea, sad, sway];
    all.forEach((v) => v.stopAnimation());
    gx.setValue(0); gy.setValue(0); open.setValue(1); happy.setValue(0);
    hop.setValue(0); idea.setValue(0); sad.setValue(0); sway.setValue(0);
    if (still) return;

    const t = (v: Animated.Value, to: number, ms: number, e = Easing.inOut(Easing.cubic)) =>
      Animated.timing(v, { toValue: to, duration: ms, easing: e, useNativeDriver: true });
    const wait = (ms: number) => Animated.delay(ms);
    const blink = Animated.sequence([t(open, 0.08, 70, Easing.in(Easing.quad)), t(open, 1, 110, Easing.out(Easing.quad))]);

    let loop: Animated.CompositeAnimation;
    if (slow) {
      // Переживает: смотрит вниз, грустные глаза, медленно покачивается, изредка моргает.
      loop = Animated.parallel([
        Animated.sequence([t(sad, 1, 420), t(gy, 0.7, 420)]),
        Animated.loop(Animated.sequence([t(sway, 1, 1300, Easing.inOut(Easing.sin)), t(sway, -1, 1300, Easing.inOut(Easing.sin))])),
        Animated.loop(Animated.sequence([wait(2200), blink, t(gx, -0.5, 500), wait(700), t(gx, 0.5, 700), wait(700), t(gx, 0, 500)])),
      ]);
    } else {
      loop = Animated.loop(Animated.sequence([
        // оглядывается
        t(gx, -1, 360), wait(520), t(gx, 1, 520), wait(520), t(gx, 0, 340),
        blink, wait(300),
        // задумался: вверх, прищур, звёздочка
        Animated.parallel([t(gy, -1, 420), t(gx, 0.5, 420), t(open, 0.6, 420), t(idea, 1, 420)]),
        wait(900),
        // есть идея: дуги и прыжок
        Animated.parallel([t(gy, 0, 200), t(gx, 0, 200), t(open, 1, 160), t(happy, 1, 180), t(idea, 0, 300)]),
        t(hop, 1, 200, Easing.out(Easing.quad)),
        Animated.spring(hop, { toValue: 0, damping: 8, stiffness: 260, mass: 0.6, useNativeDriver: true }),
        wait(500),
        t(happy, 0, 200), wait(500),
        blink, wait(700),
      ]));
    }
    loop.start();
    return () => loop.stop();
  }, [slow, still, gx, gy, open, happy, hop, idea, sad, sway]);

  const ew = EYE_W * k;
  const eh = EYE_H * k;
  const shiftX = gx.interpolate({ inputRange: [-1, 1], outputRange: [-14 * k * 2, 14 * k * 2] });
  const shiftY = gy.interpolate({ inputRange: [-1, 1], outputRange: [-12 * k * 2, 10 * k * 2] });
  const tilt = Animated.add(
    gx.interpolate({ inputRange: [-1, 1], outputRange: [-6, 6] }),
    sway.interpolate({ inputRange: [-1, 1], outputRange: [-4, 4] }),
  ).interpolate({ inputRange: [-10, 10], outputRange: ['-10deg', '10deg'] });
  const lift = hop.interpolate({ inputRange: [0, 1], outputRange: [0, -width * 0.14] });
  const bodySX = hop.interpolate({ inputRange: [0, 1], outputRange: [1, 0.95] });
  const bodySY = hop.interpolate({ inputRange: [0, 1], outputRange: [1, 1.06] });
  const ovalOp = happy.interpolate({ inputRange: [0, 1], outputRange: [1, 0] });

  return (
    <View style={{ width, height }}>
      <Animated.View style={{ width, height, transform: [{ translateY: lift }, { rotate: tilt }, { scaleX: bodySX }, { scaleY: bodySY }] }}>
        <Image accessibilityIgnoresInvertColors source={require('../../assets/art/logo-mark-body.png')}
               style={{ width, height }} resizeMode="contain" />
        {EYES.map((cx, i) => (
          <Animated.View key={i} pointerEvents="none" style={{
            position: 'absolute', left: cx * k - ew / 2, top: EYE_Y * k - eh / 2, width: ew, height: eh,
            transform: [{ translateX: shiftX }, { translateY: shiftY }],
          }}>
            <Animated.View style={[st.eye, { borderRadius: ew, opacity: ovalOp, transform: [{ scaleY: open }] }]} />
            {/* «Бровь» грусти: косой срез верха глаза цветом тела — внешний край опущен. */}
            <Animated.View style={[StyleSheet.absoluteFill, { opacity: sad }]}>
              <Svg width={ew} height={eh} viewBox="0 0 10 12">
                <Path d={i === 0 ? 'M-1 -1 L11 -1 L11 3.2 L-1 6 Z' : 'M-1 -1 L11 -1 L11 6 L-1 3.2 Z'} fill="#F58A97" />
              </Svg>
            </Animated.View>
            <Animated.View style={[StyleSheet.absoluteFill, { opacity: happy }]}>
              <Svg width={ew} height={eh} viewBox="0 0 10 12">
                <Path d="M1 8 Q5 1.5 9 8" stroke={color.ink} strokeWidth={2.4} strokeLinecap="round" fill="none" />
              </Svg>
            </Animated.View>
          </Animated.View>
        ))}
      </Animated.View>
      <Animated.View pointerEvents="none" style={{
        position: 'absolute', right: width * 0.02, top: height * 0.02, opacity: idea,
        transform: [{ scale: idea.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] }) }],
      }}>
        <Sparkle size={width * 0.16} c={color.primary} />
      </Animated.View>
    </View>
  );
}

// ===== вид
const st = StyleSheet.create({
  eye: { width: '100%', height: '100%', backgroundColor: '#000000' },
});
