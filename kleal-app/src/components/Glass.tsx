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
import { color, font, glass, radius, space, type } from '../theme';
import { hCommit, hTap } from '../haptics';
import { IconAlertTriangle } from './icons';

export function GlassPill({
  label,
  onPress,
  tone = 'light',
  icon,
  style,
  disabled,
  busy,
  labelLines = 1,
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
  /** Opt-in wrapping for step actions at large accessibility text sizes. */
  labelLines?: number;
}) {
  const dark = tone === 'dark';
  const brand = tone === 'brand';
  const off = !!disabled || !!busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off, busy: !!busy }}
      disabled={off}
      /*
        ОТКЛИК ЗДЕСЬ, А НЕ В ЭКРАНАХ. Кнопок этого вида уже с десяток, и вызов вибрации рядом с
        каждым `onPress` означал бы, что однажды одна кнопка окажется молчаливой — а молчит она
        ровно там, где про неё забыли, то есть в самом новом месте. Фирменная бьёт весомее прочих:
        за ней что-то происходит, за остальными — просто переход.
      */
      onPress={
        onPress &&
        (() => {
          if (brand) hCommit();
          else hTap();
          onPress();
        })
      }
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
        {/*
          ВЕРТУШКА СТОИТ РЯДОМ С ПОДПИСЬЮ, А НЕ ВМЕСТО НЕЁ — так в кадре A.03.2d. Подмена подписи
          кружком стирает единственное, что говорит, какое действие сейчас идёт: человек нажал
          «Подтвердить» и смотрит на безымянный кружок. Иконка на время работы уступает место
          вертушке — две картинки слева от подписи превратили бы кнопку в панель.
        */}
        {busy ? <ActivityIndicator size="small" color={dark || brand ? color.onPrimary : color.fg} /> : icon}
        <Text
          style={[s.label, dark || brand ? s.labelDark : s.labelLight, disabled && s.labelOff,
            labelLines > 1 && { flexShrink: 1, textAlign: 'center', lineHeight: undefined }]}
          numberOfLines={labelLines}
        >
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

/**
 * Плашка ошибки — кадр A.03.2c.
 *
 * Это то же стекло, что у главной кнопки: фирменный цвет на 82%, размытие подложки, светлая кромка
 * и цветное свечение под ней. Разница только в форме (радиус 8 вместо 28) и в том, что слева стоит
 * треугольник. Так и задумано: плашка — «кнопка, которая случилась», и родство с ней читается сразу.
 *
 * ПОЧЕМУ НЕ КРАСНЫЙ ТЕКСТ НА ФОНЕ. На кремовой подложке красная строка сливается с фирменным
 * красным кнопки под ней: два красных на одном экране, и оба означают разное. Плашка отделяет
 * сообщение от действия физически — у неё есть край.
 *
 * ЗАГОЛОВОК И ПОЯСНЕНИЕ — ОДИН АБЗАЦ, а не две строки: в борде это единый текстовый прогон 13/18,
 * и разбивать его на два блока значит получить лишний вертикальный ритм там, где его нет.
 */
export function GlassToast({ title, note, style }: { title: string; note?: string; style?: ViewStyle }) {
  return (
    <View accessibilityRole="alert" style={[s.toast, style]}>
      <BlurView intensity={glass.blur} tint="dark" style={StyleSheet.absoluteFill} />
      <View
        style={[
          StyleSheet.absoluteFill,
          { backgroundColor: color.primary, opacity: glass.brandAlpha },
        ]}
      />
      <View style={s.toastIcon}>
        <IconAlertTriangle size={18} />
      </View>
      <Text style={s.toastText}>
        <Text style={s.toastTitle}>{title}</Text>
        {note ? ' ' + note : ''}
      </Text>
    </View>
  );
}

/**
 * Стеклянный чип — быстрый ответ в разговоре (кадры A.04 и A.08).
 *
 * ЭТО НЕ МАЛЕНЬКАЯ КНОПКА, а ответ, который уже написан за человека. Отсюда и вид: невыбранный
 * почти прозрачен и не спорит с репликой над ним, выбранный заливается фирменным на 82% — ровно
 * тем же, чем главная кнопка. Общая заливка это не совпадение: нажатый чип и есть отправленный
 * ответ, и он обязан выглядеть как действие, а не как пометка.
 *
 * КЕГЛЬ САМЫЙ МЕЛКИЙ В ПРИЛОЖЕНИИ (11/16, из борда). Чипов на шаге увлечений одиннадцать, они
 * должны укладываться в три строки и оставлять место ленте; крупнее — и виджет съедает экран.
 */
export function GlassChip({
  label,
  on,
  onPress,
  icon,
  wrapLabel = false,
}: {
  label: string;
  /** Выбран: заливается фирменным, подпись становится белой. */
  on?: boolean;
  onPress?: () => void;
  icon?: React.ReactNode;
  /** Selected-interest lists must remain readable/removable with accessibility text sizes. */
  wrapLabel?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      onPress={
        onPress &&
        (() => {
          hTap();
          onPress();
        })
      }
      style={({ pressed }) => [s.chip, wrapLabel && s.chipWrap, on && s.chipOn, pressed && s.pressed]}
    >
      <BlurView intensity={glass.blur} tint={on ? 'dark' : 'light'} style={StyleSheet.absoluteFill} />
      <View
        style={[
          StyleSheet.absoluteFill,
          {
            backgroundColor: on ? color.primary : color.glassLight,
            opacity: on ? glass.brandAlpha : glass.lightAlpha,
          },
        ]}
      />
      {icon}
      <Text style={[s.chipText, on && s.chipTextOn, wrapLabel && { flexShrink: 1, lineHeight: undefined }]}
        numberOfLines={wrapLabel ? undefined : 1}>
        {label}
      </Text>
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
  chip: {
    height: 36,
    borderRadius: radius.full,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    overflow: 'hidden',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF88',
    ...Platform.select({
      ios: { shadowColor: color.ink, shadowOpacity: 0.1, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
      android: { elevation: 2 },
    }),
  },
  chipOn: {
    borderColor: '#FFFFFF55',
    ...Platform.select({
      ios: { shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 14, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 5 },
    }),
  },
  chipWrap: { height: 'auto', minHeight: 44, maxWidth: '100%', paddingVertical: space.sm },
  chipText: { ...type.chatHint, color: color.fg } as any,
  chipTextOn: { color: color.onPrimary },
  toast: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.sm,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#FFFFFF55',
    ...Platform.select({
      ios: {
        // Тень фирменного цвета, а не серая: плашка светится тем же, чем горит кнопка.
        shadowColor: color.primary,
        shadowOpacity: 0.3,
        shadowRadius: 20,
        shadowOffset: { width: 0, height: 8 },
      },
      android: { elevation: 8 },
    }),
  },
  // Треугольник стоит по первой строке текста, а не по центру плашки: на двух строках центр уезжает.
  toastIcon: { paddingTop: 1 },
  toastText: { ...type.fine, fontSize: 13, lineHeight: 18, color: color.onPrimary, flex: 1 } as any,
  toastTitle: { fontFamily: font.textSemibold } as any,
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.sm },
  label: { ...type.glassLabel } as any,
  labelDark: { color: color.onPrimary },
  labelLight: { color: color.fg },
});
