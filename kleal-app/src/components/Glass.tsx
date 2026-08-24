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
import {
  ActivityIndicator, Platform, Pressable, StyleSheet, Text, View, ViewStyle,
} from 'react-native';
import { BlurView } from 'expo-blur';
import { color, glass, radius, space, type } from '../theme';

export function GlassPill({
  label,
  onPress,
  tone = 'light',
  icon,
  style,
  disabled,
  busy,
}: {
  label: string;
  onPress?: () => void;
  /** `dark` — Apple; `light` — Google и почта; `brand` — главное действие экрана. */
  tone?: 'dark' | 'light' | 'brand';
  /** Иконка слева от подписи. Пара «иконка + текст» центрируется целиком, как в борде. */
  icon?: React.ReactNode;
  style?: ViewStyle;
  /** Действие сейчас недоступно: кнопка бледнеет и перестаёт нажиматься. */
  disabled?: boolean;
  /** Действие идёт: вместо подписи вертушка, повторное нажатие не проходит. */
  busy?: boolean;
}) {
  const dark = tone === 'dark';
  const brand = tone === 'brand';
  const off = !!disabled || !!busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off, busy: !!busy }}
      disabled={off}
      onPress={onPress}
      style={({ pressed }) => [
        s.wrap,
        brand && s.brandGlow,
        style,
        // Выключенная кнопка теряет свечение: горящая, но не нажимающаяся читается как сбой.
        disabled && s.off,
        pressed && s.pressed,
      ]}
    >
      {/*
        Подложка выключенной кнопки — СВЕТЛАЯ, даже у тёмных тонов. Сквозь поредевшую заливку
        тёмное размытие давало грязно-серый оттенок: кнопка выглядела не «пока нельзя», а
        испачканной. Светлая подложка оставляет её просто бледной.
      */}
      <BlurView
        intensity={glass.blur}
        tint={(dark || brand) && !disabled ? 'dark' : 'light'}
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
            backgroundColor: brand ? color.primary : dark ? color.glassDark : color.glassLight,
            opacity:
              (brand ? glass.brandAlpha : dark ? glass.darkAlpha : glass.lightAlpha) *
              (disabled ? glass.offAlpha : 1),
          },
        ]}
      />
      <View style={s.row}>
        {busy ? (
          <ActivityIndicator color={dark || brand ? color.onPrimary : color.fg} />
        ) : (
          <>
            {icon}
            {/*
              У ВЫКЛЮЧЕННОЙ КНОПКИ ГАСНЕТ ЗАЛИВКА, А НЕ ПОДПИСЬ. Гасить кнопку целиком проще, но
              белая подпись на побледневшем красном теряет контраст и читается хуже, чем сам
              выключенный вид требует. Поэтому бледнеет фон, а подпись переходит в серый — на
              светлой заливке он контрастнее белого.
            */}
            <Text
              style={[
                s.label,
                dark || brand ? s.labelDark : s.labelLight,
                disabled && s.labelOff,
              ]}
              numberOfLines={1}
            >
              {label}
            </Text>
          </>
        )}
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
  /**
   * Свечение под главной кнопкой — из борда: у неё падающая тень не серая, а фирменного цвета,
   * и именно она делает кнопку «горящей», а не просто цветной.
   */
  brandGlow: {
    borderColor: '#FFFFFF33',
    ...Platform.select({
      ios: {
        shadowColor: color.primary,
        shadowOpacity: 0.45,
        shadowRadius: 20,
        shadowOffset: { width: 0, height: 8 },
      },
      android: { elevation: 10 },
    }),
  },
  off: { shadowOpacity: 0, elevation: 0, borderColor: '#FFFFFF33' },
  labelOff: { color: color.muted },
  pressed: { opacity: 0.85 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.sm },
  label: { ...type.glassLabel } as any,
  labelDark: { color: color.onPrimary },
  labelLight: { color: color.fg },
});
