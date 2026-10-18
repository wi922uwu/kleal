/**
 * Кнопка отправки у поля ввода — компонент «Chat/Composer» (Figma, страница «💣 UI», 6164:19536).
 *
 * Прозрачный стеклянный круг 44 внутри поля и коралловая стрелка вверх. Раньше в каждом чате была
 * своя: сплошной коралловый круг с самолётиком (анкета, переписка), голый самолётик без круга
 * (группа), самолётик в сером поле (Kleal). Теперь одна на все четыре разговора.
 *
 * СТЕКЛО ЗДЕСЬ НАРИСОВАНО, А НЕ СИСТЕМНОЕ. Кнопка лежит внутри стеклянного поля, а системное стекло
 * в стекле iOS рисует мутным двойным слоем; на Android размытия нет вовсе.
 *
 * НЕ БЕЛЫЙ КРУГ, А ВЫЕМКА. Сначала была белая заливка — на iPhone поле само почти белое, и круг
 * пропал совсем (проверено на симуляторе 27.09). По картинке макета круг темнее поля сверху на ~3%
 * (243 против 251), к низу тень сходит на нет. Ровно это и нарисовано: градиент тени сверху вниз.
 *
 * ЖИДКОЕ СТЕКЛО (17.10.2026, решение владельца — направление «жидкость», см. LiquidDrop). Стрелка
 * теперь стоит на коралловой капле нарисованного стекла: блик, светлая кромка, тёплое свечение снизу.
 * Чаты показывают её, только когда в поле есть текст, — капля вытекает из поля желе (dropIn).
 * Нажатие сжимает её, отправка вытягивает её вверх, и пузырь реплики надувается (BubbleIn).
 * Поле опустело — капля растекается обратно (dropOut). Отлетающую каплю владелец убрал 17.10.2026.
 */
import { useRef } from 'react';
import { Pressable, StyleSheet } from 'react-native';
import Animated, { useAnimatedStyle, useReducedMotion, useSharedValue, withSequence, withSpring, withTiming } from 'react-native-reanimated';
import { T } from '../i18n';
import { hTap } from '../haptics';
import { IconArrowUp } from './icons';
import { DropGlass, dropIn, dropOut } from './LiquidDrop';

const SIZE = 38;
let uid = 0;

export function SendArrow({ onPress, disabled = false }: { onPress: () => void; disabled?: boolean }) {
  const reduced = useReducedMotion();
  const id = useRef(`send${++uid}`).current;
  const sx = useSharedValue(1);
  const sy = useSharedValue(1);
  const lift = useSharedValue(0);
  const jelly = useAnimatedStyle(() => ({ transform: [{ translateY: lift.value }, { scaleX: sx.value }, { scaleY: sy.value }] }));
  const soft = { damping: 8, stiffness: 300, mass: 0.6 };

  const send = () => {
    if (disabled) return;
    hTap();
    if (!reduced) {
      // Отправка — капля вытягивается вверх и отпружинивает (отлетающую каплю владелец убрал 17.10).
      sx.value = withSequence(withTiming(0.82, { duration: 90 }), withSpring(1, soft));
      sy.value = withSequence(withTiming(1.22, { duration: 90 }), withSpring(1, soft));
      lift.value = withSequence(withTiming(-4, { duration: 90 }), withSpring(0, soft));
    }
    onPress();
  };

  return (
    <Animated.View entering={reduced ? undefined : dropIn()} exiting={reduced ? undefined : dropOut()} style={s.slot}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={T('Отправить', 'Send', 'Enviar')}
        accessibilityState={{ disabled }}
        onPressIn={() => {
          if (disabled || reduced) return;
          sx.value = withSpring(1.08, { damping: 14, stiffness: 420 });
          sy.value = withSpring(0.9, { damping: 14, stiffness: 420 });
        }}
        onPressOut={() => {
          sx.value = withSpring(1, soft);
          sy.value = withSpring(1, soft);
        }}
        onPress={send}
        hitSlop={6}
      >
        <Animated.View style={[s.btn, jelly]}>
          <DropGlass size={SIZE} id={id} dim={disabled} />
          <IconArrowUp size={22} c="#FFFFFF" />
        </Animated.View>
      </Pressable>
    </Animated.View>
  );
}

const s = StyleSheet.create({
  /** Место под кнопку — прежние 44, чтобы поле не прыгало; сама капля 38 и с тенью цвета коралла. */
  slot: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  btn: {
    width: SIZE, height: SIZE, borderRadius: SIZE / 2, alignItems: 'center', justifyContent: 'center',
    shadowColor: '#FF385C', shadowOpacity: 0.35, shadowRadius: 8, shadowOffset: { width: 0, height: 3 },
  },

});
