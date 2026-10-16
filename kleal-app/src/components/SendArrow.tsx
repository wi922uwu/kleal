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
 */
import React from 'react';
import { Pressable, StyleSheet } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { T } from '../i18n';
import { hTap } from '../haptics';
import { IconArrowUp } from './icons';

export function SendArrow({ onPress, disabled = false }: { onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={T('Отправить', 'Send', 'Enviar')}
      accessibilityState={{ disabled }}
      onPress={() => { if (disabled) return; hTap(); onPress(); }}
      hitSlop={4}
      style={({ pressed }) => [s.btn, pressed && !disabled && s.pressed, disabled && s.off]}
    >
      <Svg width={44} height={44} style={StyleSheet.absoluteFill} pointerEvents="none">
        <Defs>
          <LinearGradient id="sendWell" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor="#181B22" stopOpacity={0.06} />
            <Stop offset="0.6" stopColor="#181B22" stopOpacity={0} />
          </LinearGradient>
        </Defs>
        <Circle cx={22} cy={22} r={22} fill="url(#sendWell)" />
      </Svg>
      <IconArrowUp size={30} c={disabled ? '#A6ADBB' : '#FF385C'} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  btn: {
    width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  },
  pressed: { transform: [{ scale: 0.92 }] },
  /** Пока ответ не пришёл, кнопка бледнеет, а не молчит: бледная читается как «сейчас нельзя». */
  off: { opacity: 0.7 },
});
