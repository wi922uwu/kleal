/**
 * Стеклянная пилюля — кнопки входа и всё, что в борде помечено «glass».
 *
 * В Figma у них размытие подложки 24, радиус 28 и три тени: падающая, внутренняя светлая по
 * верхней кромке и мягкая — именно эта тройка и читается как стекло. Ни одну из трёх нельзя
 * выбросить: без внутренней светлой кромка выглядит вырезанной, без падающей пилюля лежит
 * плоско на фоне.
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ КОМПОНЕНТ. Таких кнопок на экране входа три, а на будущих экранах борда их
 * ещё больше. Держать размытие и тройку теней копиями в экранах — значит однажды получить три
 * разных стекла на одном экране.
 *
 * ЗАПАСНОЙ ПУТЬ ОБЯЗАТЕЛЕН. `expo-blur` на Android до сих пор умеет не всё, и если размытия нет,
 * кнопка не должна исчезать: подложка тогда просто плотнее, и надпись остаётся читаемой.
 */
import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View, ViewStyle } from 'react-native';
import { BlurView } from 'expo-blur';
import { color, glass, radius, space, type } from '../theme';

export function GlassPill({
  label,
  onPress,
  tone = 'light',
  icon,
  style,
}: {
  label: string;
  onPress?: () => void;
  /** `dark` — кнопка Apple; `light` — Google и почта. */
  tone?: 'dark' | 'light';
  /** Иконка слева от подписи. Пара «иконка + текст» центрируется целиком, как в борде. */
  icon?: React.ReactNode;
  style?: ViewStyle;
}) {
  const dark = tone === 'dark';
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [s.wrap, style, pressed && s.pressed]}
    >
      <BlurView
        intensity={glass.blur}
        tint={dark ? 'dark' : 'light'}
        style={StyleSheet.absoluteFill}
      />
      {/*
        Плёнка цвета поверх размытия. Android без неё выходит заметно светлее iOS: там `intensity`
        считается иначе, и одно только размытие не даёт нужной плотности.
      */}
      <View
        style={[
          StyleSheet.absoluteFill,
          {
            backgroundColor: dark ? color.glassDark : color.glassLight,
            opacity: dark ? glass.darkAlpha : glass.lightAlpha,
          },
        ]}
      />
      <View style={s.row}>
        {icon}
        <Text style={[s.label, dark ? s.labelDark : s.labelLight]} numberOfLines={1}>
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: {
    height: 52,
    borderRadius: radius.xxl,
    overflow: 'hidden',
    justifyContent: 'center',
    // Светлая кромка сверху — та самая внутренняя тень из борда. В RN внутренних теней нет,
    // поэтому она рисуется рамкой: результат неотличим, а слоёв на один меньше.
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF55',
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOpacity: 0.12,
        shadowRadius: 18,
        shadowOffset: { width: 0, height: 8 },
      },
      android: { elevation: 6 },
    }),
  },
  pressed: { opacity: 0.85 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.sm },
  label: { ...type.glassLabel } as any,
  labelDark: { color: color.onPrimary },
  labelLight: { color: color.fg },
});
