/**
 * Базовые элементы по токенам борда. Один набор на всё приложение — как только кнопка рисуется
 * в двух местах руками, она в двух местах и расходится.
 */
import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from 'react-native';
import { color, radius, space, type } from '../theme';

export function Btn({
  label,
  onPress,
  kind = 'primary',
  disabled,
  busy,
  style,
}: {
  label: string;
  onPress?: () => void;
  kind?: 'primary' | 'secondary' | 'dark' | 'ghost';
  disabled?: boolean;
  busy?: boolean;
  style?: ViewStyle;
}) {
  const off = disabled || busy;
  const bg =
    kind === 'primary' ? color.primary
    : kind === 'secondary' ? color.neutral100
    : kind === 'dark' ? color.ink
    : 'transparent';
  const fg = kind === 'primary' || kind === 'dark' ? color.onPrimary : color.fg;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      onPress={off ? undefined : onPress}
      style={({ pressed }) => [
        s.btn,
        { backgroundColor: bg, opacity: off ? 0.45 : pressed ? 0.85 : 1 },
        kind === 'ghost' && { borderWidth: 1, borderColor: color.border },
        style,
      ]}
    >
      {busy ? <ActivityIndicator color={fg} /> : <Text style={[s.btnText, { color: fg }]}>{label}</Text>}
    </Pressable>
  );
}

export function Chip({
  label,
  on,
  onPress,
}: {
  label: string;
  on?: boolean;
  onPress?: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      onPress={onPress}
      style={({ pressed }) => [
        s.chip,
        on ? { backgroundColor: color.primary, borderColor: color.primary } : null,
        pressed && { opacity: 0.85 },
      ]}
    >
      <Text style={[s.chipText, on && { color: color.onPrimary }]}>{label}</Text>
    </Pressable>
  );
}

export function Field(props: TextInputProps & { label?: string }) {
  const { label, style, ...rest } = props;
  return (
    <View style={{ width: '100%' }}>
      {label ? <Text style={s.fieldLabel}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={color.neutral400}
        {...rest}
        style={[s.field, style]}
      />
    </View>
  );
}

export function H2({ children, center }: { children: React.ReactNode; center?: boolean }) {
  return <Text style={[s.h2, center && { textAlign: 'center' }]}>{children}</Text>;
}

export function Body({ children, center }: { children: React.ReactNode; center?: boolean }) {
  return <Text style={[s.body, center && { textAlign: 'center' }]}>{children}</Text>;
}

export function Caption({ children, center }: { children: React.ReactNode; center?: boolean }) {
  return <Text style={[s.caption, center && { textAlign: 'center' }]}>{children}</Text>;
}

const s = StyleSheet.create({
  btn: {
    height: 48,
    borderRadius: radius.full,
    paddingHorizontal: space.xl,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: space.sm,
  },
  btnText: { ...type.button } as any,
  chip: {
    height: 36,
    paddingHorizontal: 14,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: color.border,
    backgroundColor: color.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  field: {
    height: 48,
    borderRadius: radius.md,
    backgroundColor: color.neutral100,
    paddingHorizontal: 14,
    color: color.fg,
    fontSize: 15,
  },
  fieldLabel: { ...type.labelMedium, color: color.muted, marginBottom: 6 } as any,
  h2: { ...type.h2, color: color.fg } as any,
  body: { ...type.body, color: color.muted } as any,
  caption: { ...type.caption, color: color.muted } as any,
});
