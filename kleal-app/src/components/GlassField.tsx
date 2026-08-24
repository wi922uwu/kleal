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
import React from 'react';
import {
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from 'react-native';
import { BlurView } from 'expo-blur';
import { color, glass, space, type } from '../theme';

/**
 * Стеклянная подложка: размытие того, что под ней, плюс белая плёнка.
 *
 * Экспортируется, потому что ячейки кода на A.03.2 — то же самое стекло другой формы, и рисовать
 * их своей парой слоёв значило бы завести второе стекло в приложении.
 */
export function GlassPane({ radius: r }: { radius: number }) {
  return (
    <>
      <BlurView intensity={glass.blur} tint="light" style={[StyleSheet.absoluteFill, { borderRadius: r }]} />
      <View
        style={[
          StyleSheet.absoluteFill,
          { backgroundColor: color.glassLight, opacity: glass.lightAlpha, borderRadius: r },
        ]}
      />
    </>
  );
}

/** Круглая кнопка «назад» в левом верхнем углу. */
export function GlassBack({ onPress, label }: { onPress: () => void; label: string }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={10}
      style={({ pressed }) => [s.back, pressed && s.pressed]}
    >
      <GlassPane radius={22} />
      {/*
        Шеврон — символ, а не картинка: это не фирменный знак, а стандартная стрелка «назад»,
        и рисовать её файлом значило бы держать ассет ради одного глифа.
      */}
      <Text style={s.chevron}>‹</Text>
    </Pressable>
  );
}

/** Поле ввода с подписью над ним. */
export function GlassInput({
  label,
  style,
  bad,
  ...input
}: TextInputProps & {
  label?: string;
  style?: ViewStyle;
  /** Введено не то: кромка становится красной. Сам текст ошибки живёт под полем, в экране. */
  bad?: boolean;
}) {
  return (
    <View style={style}>
      {!!label && <Text style={s.label}>{label}</Text>}
      <View style={[s.field, bad && s.fieldBad]}>
        <GlassPane radius={20} />
        <TextInput
          {...input}
          style={s.input}
          placeholderTextColor={color.muted}
          selectionColor={color.primary}
        />
      </View>
    </View>
  );
}

// ===== вид
const PANE = Platform.select({
  ios: {
    shadowColor: '#000',
    shadowOpacity: 0.1,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
  },
  android: { elevation: 5 },
});

const s = StyleSheet.create({
  back: {
    width: 44,
    height: 44,
    borderRadius: 22,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF55',
    ...PANE,
  },
  pressed: { opacity: 0.85 },
  // Шеврон крупнее кегля и поднят: у символа «‹» большая нижняя пазуха, по центру он висит низко.
  chevron: { fontSize: 30, lineHeight: 32, color: color.fg, marginTop: -3, marginLeft: -2 },
  label: { ...type.fieldLabel, color: color.muted, marginBottom: space.sm } as any,
  field: {
    height: 56,
    borderRadius: 20,
    overflow: 'hidden',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF55',
    ...PANE,
  },
  // Кромка ошибки заметно плотнее светлой: полупрозрачную красную на кремовом фоне не видно.
  fieldBad: { borderWidth: 1, borderColor: color.danger },
  input: {
    ...type.displaySub,
    color: color.fg,
    paddingHorizontal: space.lg,
    // Высота задана контейнером; своя убирает вертикальное дрожание курсора на Android.
    height: '100%',
  } as any,
});
