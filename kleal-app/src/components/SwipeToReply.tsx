/**
 * Потянул реплику вправо — отвечаешь ей.
 *
 * Привычный жест: так отвечают в WhatsApp и Telegram, и рука уже знает. Без него путь к цитате
 * один — долгое нажатие, лист, «Ответить»: три действия там, где привычка требует одного.
 *
 * ЧЕМ ЭТО ОПАСНО и как обойдено. Лента прокручивается вертикально, и жест обязан не отбирать
 * прокрутку у пальца, который просто листает. Поэтому мы claim'им его только когда движение
 * ЯВНО горизонтальное: вдвое длиннее вертикального и не короче десяти пунктов. Промах в эту
 * сторону дороже, чем в другую: не сработавший ответ — досада, а залипшая лента — поломка.
 *
 * Тянуть можно ТОЛЬКО вправо. Влево в этой ленте ничего не значит, а свободный ход в обе стороны
 * читается как «тут что-то есть» и обещает то, чего нет.
 */
import React, { useRef } from 'react';
import { Animated, PanResponder, Platform, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { color } from '../theme';
import { IconChevronLeft } from './icons';

/** Дальше этого не тянется, и на этом же пороге ответ засчитывается. */
const TRIGGER = 56;
const MAX = 72;

export function SwipeToReply({
  onReply, enabled = true, children,
}: {
  onReply: () => void;
  enabled?: boolean;
  children: React.ReactNode;
}) {
  const dx = useRef(new Animated.Value(0)).current;
  /** Отклик даётся ОДИН раз за жест — на пороге, а не на каждом кадре за ним. */
  const buzzed = useRef(false);
  const on = useRef(enabled);
  on.current = enabled;

  const back = () => Animated.spring(dx, {
    toValue: 0, friction: 7, tension: 140, useNativeDriver: true,
  }).start();

  const responder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_e, g) =>
        on.current && g.dx > 10 && Math.abs(g.dx) > Math.abs(g.dy) * 2,
      onPanResponderGrant: () => { buzzed.current = false; },
      onPanResponderMove: (_e, g) => {
        const x = Math.max(0, Math.min(MAX, g.dx));
        dx.setValue(x);
        if (!buzzed.current && x >= TRIGGER) {
          buzzed.current = true;
          if (Platform.OS !== 'web') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        }
      },
      onPanResponderRelease: (_e, g) => {
        if (g.dx >= TRIGGER) onReply();
        back();
      },
      onPanResponderTerminate: back,
    })
  ).current;

  return (
    <View {...responder.panHandlers}>
      {/* Стрелка проявляется по ходу жеста: до порога она бледная, на пороге — в полную силу. */}
      <Animated.View
        style={[s.hint, { opacity: dx.interpolate({ inputRange: [0, TRIGGER], outputRange: [0, 1], extrapolate: 'clamp' }) }]}
        pointerEvents="none"
      >
        <IconChevronLeft size={16} c={color.primary} />
      </Animated.View>
      <Animated.View style={{ transform: [{ translateX: dx }] }}>{children}</Animated.View>
    </View>
  );
}

// ===== вид

const s = {
  hint: {
    position: 'absolute' as const,
    left: 8,
    top: 0,
    bottom: 0,
    justifyContent: 'center' as const,
  },
};
