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
import Animated from 'react-native-reanimated';
import { color, font, radius, space, type } from '../theme';
import { GlassSurface, usePress } from './LiquidGlass';
import { hCommit, hTap } from '../haptics';
import { IconAlertTriangle } from './icons';

/** Стиль в один объект — массивы любой вложенности, пустые места пропускаются. */
const flatStyle = (st: any): any =>
  Array.isArray(st) ? Object.assign({}, ...st.map(flatStyle)) : st && typeof st === 'object' ? st : {};

export function GlassPill({
  label,
  onPress,
  tone = 'light',
  icon,
  style,
  disabled,
  busy,
  labelLines = 1,
  small = false,
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
  /** Кнопка 40 над полем ввода (GR.21 «Make the plan»): подпись 14/20, поля 16. */
  small?: boolean;
}) {
  const dark = tone === 'dark';
  const brand = tone === 'brand';
  const off = !!disabled || !!busy;
  const p = usePress(0.965);
  /*
    ВЫСОТА. Фирменная кнопка в макете выше стеклянных: 56 против 52. Экран может задать свою
    высоту стилем — она уходит и на само стекло, иначе обёртка росла бы, а стекло оставалось прежним.
    Размеры и тень живут на нажимаемой обёртке (её стиль видят тесты доступности), масштаб и стекло —
    внутри неё: пружина сжимает стекло, а область касания остаётся прежней.
  */
  const flat = flatStyle(style);
  const h = (flat.height as any) || (brand ? 56 : 52);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off, busy: !!busy }}
      disabled={off}
      onPressIn={p.onPressIn}
      onPressOut={p.onPressOut}
      /*
        ОТКЛИК ЗДЕСЬ, А НЕ В ЭКРАНАХ. Кнопок этого вида уже с десяток, и вызов вибрации рядом с
        каждым `onPress` означал бы, что однажды одна кнопка окажется молчаливой. Фирменная бьёт
        весомее прочих: за ней что-то происходит, за остальными — просто переход.
      */
      onPress={
        onPress &&
        (() => {
          if (brand) hCommit();
          else hTap();
          onPress();
        })
      }
      style={() => [s.shadow, tone === 'light' && s.flatAndroid, brand && !disabled && s.brandGlow, disabled && s.off, style]}
    >
      <Animated.View style={[s.fillUp, p.style]}>
        {/*
          ВЫКЛЮЧЕННАЯ ФИРМЕННАЯ — светлое стекло: горящий коралл, который не нажимается, читается как
          сбой. Выключенная ТЁМНАЯ остаётся тёмной (Apple «скоро» в A.03): на светлом стекле пропадал
          белый значок. Приглушение — цветом подписи, не прозрачностью (стекло под ней не рисуется).
        */}
        {/*
          ВЫКЛЮЧЕННАЯ ФИРМЕННАЯ — бледный коралл (борд «0 · Create the intent», Apply на GR.12b и Next на
          шагах мастера: та же кнопка со слоем 40%). Прежде она становилась светлым стеклом — на новом
          борде такой кнопки нет. Бледность — цветом заливки и подписи, а не прозрачностью предка:
          полупрозрачный предок гасит системное стекло целиком, поэтому здесь и не стекло, а плёнка.
        */}
        {disabled && brand ? (
          <View pointerEvents="none" style={[s.wrap, small && s.wrapSmall, { height: h, minHeight: flat.minHeight as any }, s.brandOff]}>
            <View style={s.row}>
              {busy ? <ActivityIndicator size="small" color={color.onPrimary} /> : icon}
              <Text style={[s.label, small && s.labelSmall, s.labelDark, s.labelOffBrand]} numberOfLines={labelLines}>
                {label}
              </Text>
            </View>
          </View>
        ) : (
        <GlassSurface
          tone={tone}
          radius={radius.xxl}
          pointerEvents="none"
          style={[s.wrap, small && s.wrapSmall, { height: h, minHeight: flat.minHeight as any }]}
        >
          <View style={s.row}>
            {/*
              ВЕРТУШКА СТОИТ РЯДОМ С ПОДПИСЬЮ, А НЕ ВМЕСТО НЕЁ — так в кадре A.03.2d: подмена подписи
              кружком стирает единственное, что говорит, какое действие сейчас идёт.
            */}
            {busy ? <ActivityIndicator size="small" color={dark || brand ? color.onPrimary : color.fg} /> : icon}
            <Text
              style={[s.label, small && s.labelSmall, dark || brand ? s.labelDark : s.labelLight,
                disabled && (dark ? s.labelOffDark : brand ? s.labelOffBrand : s.labelOff),
                labelLines > 1 && { flexShrink: 1, textAlign: 'center', lineHeight: undefined }]}
              numberOfLines={labelLines}
            >
              {label}
            </Text>
          </View>
        </GlassSurface>
        )}
      </Animated.View>
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
    <View accessibilityRole="alert" style={[s.toastShadow, style]}>
      <GlassSurface tone="brand" radius={radius.lg} style={s.toast}>
        <View style={s.toastIcon}>
          <IconAlertTriangle size={18} />
        </View>
        <Text style={s.toastText}>
          <Text style={s.toastTitle}>{title}</Text>
          {note ? ' ' + note : ''}
        </Text>
      </GlassSurface>
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
  grow = false,
}: {
  label: string;
  /** Выбран: заливается фирменным, подпись становится белой. */
  on?: boolean;
  onPress?: () => void;
  icon?: React.ReactNode;
  /** Selected-interest lists must remain readable/removable with accessibility text sizes. */
  wrapLabel?: boolean;
  /** Чипы ряда делят ширину поровну — выбор пола в A.05: три чипа по 111 точек. */
  grow?: boolean;
}) {
  const p = usePress(0.93);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      onPressIn={p.onPressIn}
      onPressOut={p.onPressOut}
      onPress={
        onPress &&
        (() => {
          hTap();
          onPress();
        })
      }
      style={() => [s.chipBox, wrapLabel && s.chipWrap, grow && s.chipGrow, on && s.chipOn]}
    >
      <Animated.View style={[s.fillUp, p.style]}>
        <GlassSurface tone={on ? 'brand' : 'light'} radius={radius.full} pointerEvents="none" style={[s.chip, wrapLabel && s.chipWrapInner, grow && s.chipCenter]}>
          {icon}
          <Text style={[s.chipText, on && s.chipTextOn, wrapLabel && { flexShrink: 1, lineHeight: undefined }]}
            numberOfLines={wrapLabel ? undefined : 1}>
            {label}
          </Text>
        </GlassSurface>
      </Animated.View>
    </Pressable>
  );
}

// ===== вид
const s = StyleSheet.create({
  /** Падающая тень снаружи стекла: у самого стекла `overflow: hidden`, и тень внутри него срезалась бы. */
  shadow: {
    borderRadius: radius.xxl,
    ...Platform.select({
      ios: { shadowColor: '#0A0A14', shadowOpacity: 0.1, shadowRadius: 18, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 6 },
    }),
  },
  wrap: { height: 52, justifyContent: 'center', paddingHorizontal: space.xl },
  /**
   * Свечение под главной кнопкой — из борда: падающая тень фирменного цвета (#FF385C · 30%, y 8,
   * размытие 20). Именно она делает кнопку «горящей», а не просто цветной.
   */
  brandGlow: {
    ...Platform.select({
      ios: { shadowColor: color.primary, shadowOpacity: 0.42, shadowRadius: 20, shadowOffset: { width: 0, height: 8 } },
      android: { elevation: 10 },
    }),
  },
  off: { shadowOpacity: 0, elevation: 0 },
  /**
   * СВЕТЛОЕ СТЕКЛО НА ANDROID — БЕЗ ТЕНИ. `elevation` рисует тень под всем контуром, а плёнка светлого
   * стекла полупрозрачная: тень просвечивает сквозь неё, и кнопка становится грязно-серой (снимки с
   * телефона: «Мужской / Женский», «Добавить своё», пузырь агента). Коралловому и тёмному стеклу
   * тень не мешает — плёнка у них плотная.
   */
  flatAndroid: Platform.select({ android: { elevation: 0 }, default: {} }) as any,
  labelOff: { color: color.muted },
  labelOffBrand: { color: 'rgba(255,255,255,0.8)' },
  /** Плёнка выключенной фирменной: коралл 82% × слой 40% ≈ 33%, поверх неё — без стекла. */
  brandOff: { backgroundColor: 'rgba(255,56,92,0.36)', overflow: 'hidden', borderRadius: radius.xxl },
  labelOffDark: { color: 'rgba(255,255,255,0.55)' },
  /** Слой пружины растягивается на всю обёртку: у обёртки может быть только минимальная высота. */
  fillUp: { flexGrow: 1 },
  chipBox: {
    height: 36,
    borderRadius: radius.full,
    ...Platform.select({
      ios: { shadowColor: color.ink, shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
      default: {},
    }),
  },
  chip: {
    flexGrow: 1,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  chipOn: {
    ...Platform.select({
      ios: { shadowColor: color.primary, shadowOpacity: 0.32, shadowRadius: 14, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 5 },
    }),
  },
  chipWrap: { height: 'auto', minHeight: 44, maxWidth: '100%' },
  chipWrapInner: { paddingVertical: space.sm },
  chipGrow: { flex: 1 },
  chipCenter: { justifyContent: 'center' },
  chipText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.fg } as any,
  chipTextOn: { color: color.onPrimary },
  toastShadow: {
    borderRadius: radius.lg,
    ...Platform.select({
      ios: { shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 20, shadowOffset: { width: 0, height: 8 } },
      android: { elevation: 8 },
    }),
  },
  toast: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  // Треугольник стоит по первой строке текста, а не по центру плашки: на двух строках центр уезжает.
  toastIcon: { paddingTop: 1 },
  toastText: { ...type.fine, fontSize: 13, lineHeight: 18, color: color.onPrimary, flex: 1 } as any,
  toastTitle: { fontFamily: font.textSemibold } as any,
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.sm },
  label: { ...type.glassLabel } as any,
  labelSmall: { fontSize: 14, lineHeight: 20 },
  wrapSmall: { paddingHorizontal: 16 },
  labelDark: { color: color.onPrimary },
  labelLight: { color: color.fg },
});
