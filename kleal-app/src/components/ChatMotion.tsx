/**
 * ДВИЖЕНИЕ ПЕРЕПИСКИ — одно на все чаты: 1:1, комната группы, разговор с Kleal, сборщик затеи.
 *
 * Просьба владельца 17.10.2026: «красивые анимации отправки сообщений… и кнопку отправки —
 * плавную бамбл-анимацию появления». Раньше реплика просто возникала в ленте, а стрелка — у поля.
 *
 * ЯЗЫК ДВИЖЕНИЯ (один на приложение, менять здесь):
 *   ЖИДКОСТЬ (решение владельца 17.10.2026 из трёх прототипов: «из поля», «желе», «жидкость»).
 *   кнопка        — коралловая капля жидкого стекла, вытекает из поля желе (src/components/LiquidDrop).
 *   своя реплика  — НАДУВАЕТСЯ из правого нижнего угла, ширина и высота пружинят в противофазе.
 *   чужая и Kleal — поднимается каплей из левого угла, спокойнее: входящее не спорит с тем, что
 *                   человек сделал сам.
 *   событие плана — «щелчок» карточки по центру: короткий рост без сдвига.
 *
 * ТОЛЬКО СДВИГ И МАСШТАБ. Пузыри — системное стекло (GlassSurface), а оно не рисуется, если у
 * него или у предка непрозрачность меньше 1 (см. riseIn в LiquidGlass). Прозрачность меняет только
 * кнопка: она сама нарисована и лежит ВНУТРИ стекла поля, а не над ним.
 *
 * ТОЛЬКО НОВОЕ. История, открытая с экраном, не анимируется: десятки пузырей, взлетающих разом, —
 * это шум, а не отклик. «Уменьшение движения» в системе выключает всё это целиком.
 */
import React from 'react';
import { type StyleProp, type ViewStyle } from 'react-native';
import Animated, { Easing, useReducedMotion, withDelay, withSequence, withSpring, withTiming } from 'react-native-reanimated';

/** Входящая: мягче и без перелёта. */
const IN = { damping: 20, stiffness: 200, mass: 1 };

function bubbleIn(mine: boolean) {
  if (mine) {
    // СВОЯ — НАДУВАЕТСЯ (направление «жидкость», 17.10.2026): из правого нижнего угла, как мыльный
    // пузырь — ширина и высота пружинят в противофазе. Сразу, без задержки: отлетающую от кнопки
    // каплю, под полёт которой была задержка 210 мс, владелец убрал.
    return () => {
      'worklet';
      const k = (to: number, ms: number) => withTiming(to, { duration: ms, easing: Easing.out(Easing.quad) });
      const d = 0;
      return {
        initialValues: { transform: [{ scaleX: 0.08 }, { scaleY: 0.08 }] },
        animations: {
          transform: [
            { scaleX: withDelay(d, withSequence(k(1.07, 170), k(0.97, 110), withSpring(1, IN))) },
            { scaleY: withDelay(d, withSequence(k(0.9, 170), k(1.04, 110), withSpring(1, IN))) },
          ],
        },
      };
    };
  }
  // ЧУЖАЯ И KLEAL — тоже жидкая, но спокойнее: поднимается каплей из левого угла, без желе.
  return () => {
    'worklet';
    return {
      initialValues: { transform: [{ translateY: 14 }, { scale: 0.55 }] },
      animations: {
        transform: [
          { translateY: withSpring(0, IN) },
          { scale: withSpring(1, { damping: 13, stiffness: 220, mass: 0.9 }) },
        ],
      },
    };
  };
}

function eventIn() {
  return () => {
    'worklet';
    return {
      initialValues: { transform: [{ scale: 0.9 }] },
      animations: { transform: [{ scale: withSpring(1, { damping: 13, stiffness: 300, mass: 0.8 }) }] },
    };
  };
}

/**
 * Обёртка реплики. `fresh` — реплика пришла или ушла при открытом экране (решает лента).
 * Точка роста — угол со стороны автора: своя растёт оттуда, где стрелка.
 */
export function BubbleIn({ mine, fresh, style, children }: {
  mine: boolean; fresh: boolean; style?: StyleProp<ViewStyle>; children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  return (
    <Animated.View
      entering={fresh && !reduced ? bubbleIn(mine) : undefined}
      style={[{ transformOrigin: mine ? 'right bottom' : 'left bottom' } as ViewStyle, style]}
    >
      {children}
    </Animated.View>
  );
}

/** Обёртка события плана (карточка по центру ленты). */
export function EventIn({ fresh, children }: { fresh: boolean; children: React.ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <Animated.View entering={fresh && !reduced ? eventIn() : undefined} style={{ transformOrigin: 'center' } as ViewStyle}>
      {children}
    </Animated.View>
  );
}
