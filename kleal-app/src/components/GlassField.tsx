/**
 * Стеклянные элементы формы: круглая кнопка «назад» и поле ввода.
 *
 * Оба из того же набора, что `GlassPill`: белая плёнка на 42%, размытие подложки 24, светлая
 * кромка и мягкая падающая тень. Отличаются только формой — круг 44×44 и пилюля 56 в высоту с
 * радиусом 20.
 *
 * ЗАЧЕМ РЯДОМ С GlassPill, А НЕ ВНУТРИ. У кнопки и поля разная механика: одна нажимается, другое
 * держит фокус, курсор и клавиатуру. Общий у них только вид, и общее вынесено в токены (`glass`
 * в theme.ts), а не в один компонент с полудюжиной взаимоисключающих свойств.
 */
import React, { useState } from 'react';
import {
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from 'react-native';
import { color, space, type } from '../theme';
import { GlassSurface } from './LiquidGlass';

/**
 * Стеклянная подложка под любым содержимым: жидкое стекло на iOS 26+, размытие на остальных.
 * Кладётся первым ребёнком и растягивается на весь контейнер.
 */
export function GlassPane({ radius: r }: { radius: number }) {
  return <GlassSurface tone="light" radius={r} style={StyleSheet.absoluteFill} pointerEvents="none" />;
}

/** Круглая «назад» — одна на всё приложение, живёт рядом со стеклом. */
export { GlassBack } from './LiquidGlass';

export const GlassInput = React.forwardRef<TextInput, TextInputProps & {
  label?: string;
  style?: ViewStyle;
  /** Введено не то: кромка становится красной. Сам текст ошибки живёт под полем, в экране. */
  bad?: boolean;
}>(function GlassInput({ label, style, bad, onFocus, onBlur, ...input }, ref) {
  /*
    ФОКУС ВИДЕН. В макете активная ячейка кода обведена фирменным (#FF385C, 0.5): так человек
    понимает, куда пойдёт следующий символ. Поле почты держит то же правило.
  */
  const [focus, setFocus] = useState(false);
  return (
    <View style={style}>
      {!!label && <Text style={s.label}>{label}</Text>}
      <View style={[s.field, focus && s.fieldFocus, bad && s.fieldBad]}>
        <GlassPane radius={16} />
        <TextInput
          {...input}
          ref={ref}
          onFocus={(e) => { setFocus(true); onFocus?.(e); }}
          onBlur={(e) => { setFocus(false); onBlur?.(e); }}
          style={s.input}
          placeholderTextColor={color.muted}
          selectionColor={color.primary}
        />
      </View>
    </View>
  );
});

const PANE = Platform.select({
  ios: {
    shadowColor: '#0A0A14',
    shadowOpacity: 0.06,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
  },
  default: {},
});

// ===== вид
const s = StyleSheet.create({
  label: { fontFamily: 'Geist-400', fontSize: 12, lineHeight: 16, color: '#797979', marginBottom: space.sm } as any,
  field: {
    height: 48,
    borderRadius: 16,
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'transparent',
    ...PANE,
  },
  fieldFocus: {
    borderColor: '#FF385C',
    ...Platform.select({
      ios: { shadowColor: '#FF385C', shadowOpacity: 0.18, shadowRadius: 14, shadowOffset: { width: 0, height: 4 } },
      android: {},
    }),
  },
  fieldBad: { borderWidth: 1, borderColor: color.danger },
  input: {
    ...type.displaySub,
    color: color.fg,
    paddingHorizontal: space.lg,
    height: '100%',
  } as any,
});
