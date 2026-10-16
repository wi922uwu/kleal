/**
 * ЖИДКОЕ СТЕКЛО — поверхность из макета «First run» (эффект `GLASS` в Figma, 88 слоёв секции).
 *
 * На iOS 26+ это настоящий Liquid Glass системы (`expo-glass-effect` → `UIGlassEffect`): стекло
 * преломляет то, что под ним, ловит блик по кромке и откликается на палец. Модуль входит в набор
 * Expo Go SDK 57, отдельной сборки не нужно.
 *
 * ЗАПАСНОЙ ПУТЬ ОБЯЗАТЕЛЕН. Android и iOS до 26 жидкого стекла не умеют — там поверхность
 * собирается как раньше: размытие подложки, плёнка цвета и светлая кромка. Экран не должен знать,
 * какой из двух путей сработал, поэтому оба живут за одним компонентом.
 */
import React from 'react';
import { Platform, Pressable, StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import { BlurView } from 'expo-blur';
import { GlassView, isLiquidGlassAvailable } from 'expo-glass-effect';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withDelay, withTiming } from 'react-native-reanimated';
import { color, glass } from '../theme';
import { hTap } from '../haptics';
import { IconChevronLeft } from './icons';

/** Есть ли системное жидкое стекло. Проверка один раз: ответ не меняется за время жизни процесса. */
export const LIQUID: boolean = (() => {
  if (Platform.OS !== 'ios') return false;
  try { return isLiquidGlassAvailable(); } catch { return false; }
})();

export type GlassTone = 'light' | 'veil' | 'clear' | 'frost' | 'dark' | 'brand' | 'info' | 'sheet';

/**
 * Оттенок стекла. У системного стекла он ложится поверх преломления, поэтому светлое берёт
 * полупрозрачный белый (на кремовой подложке чистое стекло почти невидимо), фирменное — полный
 * коралловый: главная кнопка обязана гореть, а не просвечивать.
 */
const TINT: Record<GlassTone, string | undefined> = {
  light: 'rgba(255,255,255,0.46)',
  /**
   * Вуаль: светлое стекло ПОВЕРХ ФОТОГРАФИИ, на нём текст. Плотная, а не прозрачная: на пёстром
   * фото тонкая плёнка оставляла тексту контраст 1,7–2,5 при норме 4,5 («нечитаемый текст»,
   * тестировщик 27.09). 0,72 здесь + собственный материал стекла ≈ 80% белого.
   */
  veil: 'rgba(255,255,255,0.72)',
  clear: undefined,
  /** Иней рисуется не системным стеклом, а размытием — см. `GlassSurface`. */
  frost: undefined,
  dark: 'rgba(26,28,33,0.92)',
  brand: 'rgba(255,56,92,0.94)',
  info: 'rgba(120,160,255,0.22)',
  /** Нижний лист: почти молочное стекло — под ним затемнение, и чтение важнее преломления. */
  sheet: 'rgba(245,241,236,0.97)',
};

/** Плёнка запасного пути — плотность из борда (белое 42%, коралл 82%, тёмное 78%). */
const FILM: Record<GlassTone, { c: string; a: number }> = {
  light: { c: color.glassLight, a: glass.lightAlpha },
  /*
    Вуаль без системного стекла. На Android expo-blur НЕ размывает (без blurMethod он кладёт только
    белую подложку 0,24 × 0,78 ≈ 19%), так что читаемость держит одна плёнка: 0,76 поверх подложки
    = 80% белого. По фото вступления это контраст подзаголовка не ниже 6,2, заголовка не ниже 11.
  */
  veil: { c: color.glassLight, a: 0.76 },
  clear: { c: color.glassLight, a: 0.18 },
  frost: { c: color.glassLight, a: 0.06 },
  dark: { c: color.glassDark, a: glass.darkAlpha },
  brand: { c: color.primary, a: glass.brandAlpha },
  info: { c: '#DCE7FF', a: 0.7 },
  sheet: { c: '#F5F1EC', a: 0.98 },
};

export function GlassSurface({
  tone = 'light',
  radius = 999,
  interactive = false,
  style,
  children,
  pointerEvents,
}: {
  tone?: GlassTone;
  radius?: number;
  /**
   * Стекло откликается на касание (системный «живой» отклик). ВНУТРИ Pressable НЕ ВКЛЮЧАТЬ:
   * интерактивное стекло вешает свои распознаватели жестов, и они отменяют касание для RN —
   * кнопка перестаёт нажиматься (проверено на симуляторе iOS 27). Там стекло кладётся с
   * pointerEvents="none", а отклик даёт пружина usePress.
   */
  interactive?: boolean;
  style?: StyleProp<ViewStyle>;
  children?: React.ReactNode;
  pointerEvents?: 'box-none' | 'none' | 'box-only' | 'auto';
}) {
  /*
    ИНЕЙ — ВСЕГДА РАЗМЫТИЕ, И НА iOS 26+ ТОЖЕ. Это стекло карточек карусели на главной (GR.01,
    «Test 260930»: эффект GLASS без заливки). Системное стекло для него не годится ни в каком виде:
    «чистое» рисовало по левой и правой кромке яркие вертикальные блики во всю высоту карточки, а
    «обычное» даже с плёнкой 14% делало карточку молочной — предметы за ней (смайлик, наушники) почти
    исчезали (снимки симулятора iOS 27, 30.09). Тонкий системный материал размывает и почти не белит:
    за карточкой остаётся фон и размытые предметы, как на кадре.
  */
  if (tone === 'frost') {
    return (
      <View pointerEvents={pointerEvents} style={[{ borderRadius: radius, overflow: 'hidden' }, s.edge, style]}>
        <BlurView intensity={glass.blur} tint="systemUltraThinMaterialLight" style={StyleSheet.absoluteFill} />
        <View style={[StyleSheet.absoluteFill, { backgroundColor: FILM.frost.c, opacity: FILM.frost.a }]} />
        {children}
      </View>
    );
  }
  if (LIQUID) {
    return (
      <GlassView
        glassEffectStyle={tone === 'clear' ? 'clear' : 'regular'}
        tintColor={TINT[tone]}
        isInteractive={interactive}
        colorScheme={tone === 'dark' ? 'dark' : 'light'}
        pointerEvents={pointerEvents}
        style={[{ borderRadius: radius, overflow: 'hidden' }, style]}
      >
        {children}
      </GlassView>
    );
  }
  const film = FILM[tone];
  return (
    <View pointerEvents={pointerEvents} style={[{ borderRadius: radius, overflow: 'hidden' }, s.edge, style]}>
      <BlurView
        intensity={glass.blur}
        tint={tone === 'dark' || tone === 'brand' ? 'dark' : 'light'}
        style={StyleSheet.absoluteFill}
      />
      <View style={[StyleSheet.absoluteFill, { backgroundColor: film.c, opacity: film.a }]} />
      {children}
    </View>
  );
}

/**
 * ДВИЖЕНИЕ СДЕРЖАННОЕ. Одно на всё приложение: плавное замедление без перелёта, 160–320 мс. Пружины
 * с перелётом здесь были — и экран «скакал»: каждая карточка подпрыгивала, кнопка отыгрывала
 * назад. Анимация остаётся только там, где она что-то сообщает: новая реплика, отклик на палец,
 * прогресс, одна главная сцена экрана. Всё остальное просто стоит на месте.
 *
 * ПОЯВЛЕНИЕ БЕЗ ПРОЗРАЧНОСТИ. Системное стекло — это UIVisualEffectView, а у него жёсткое
 * ограничение UIKit: если у него самого или у ЛЮБОГО предка непрозрачность меньше 1, эффект не
 * рисуется вовсе (на экране остаётся только подпись). Поэтому всё, внутри чего есть стекло,
 * появляется сдвигом и масштабом, а не `FadeIn*`. Текст без стекла по-прежнему может таять.
 */
export function riseIn(delay = 0, dy = 6) {
  // Сдвиг не больше 8 точек: заметный выезд уже читается как прыжок.
  const d = Math.min(dy, 8);
  return () => {
    'worklet';
    return {
      initialValues: { transform: [{ translateY: d }] },
      animations: {
        transform: [
          { translateY: withDelay(delay, withTiming(0, { duration: 320, easing: Easing.out(Easing.cubic) })) },
        ],
      },
    };
  };
}

/**
 * ОТКЛИК НА ПАЛЕЦ. Под пальцем стекло чуть проседает (не глубже 3%) и спокойно возвращается —
 * без отскока. Масштаб, а не прозрачность: погасшая кнопка читается как выключенная.
 */
export function usePress(to = 0.97) {
  const depth = Math.max(to, 0.97);
  const k = useSharedValue(1);
  const style = useAnimatedStyle(() => ({ transform: [{ scale: k.value }] }));
  return {
    style,
    onPressIn: () => { k.value = withTiming(depth, { duration: 90, easing: Easing.out(Easing.quad) }); },
    onPressOut: () => { k.value = withTiming(1, { duration: 180, easing: Easing.out(Easing.cubic) }); },
  };
}

/**
 * Круглая стеклянная кнопка-знак 44×44: «назад», «закрыть», «ещё». Одна на все шапки и листы —
 * иначе у крестика листа и у стрелки шапки разойдутся тень и отклик.
 */
export function GlassIconButton({
  onPress, label, style, children, size = 44,
}: {
  onPress: () => void; label: string; style?: ViewStyle; children: React.ReactNode;
  /** Круг 44 в шапках; 48 — у поля ввода («Chat/Composer»: кнопка ростом с поле). */
  size?: number;
}) {
  const p = usePress(0.9);
  const box = size === 44 ? null : { width: size, height: size, borderRadius: size / 2 };
  return (
    <Animated.View style={[s.backShadow, box, p.style, style]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        hitSlop={8}
        onPressIn={p.onPressIn}
        onPressOut={p.onPressOut}
        onPress={() => { hTap(); onPress(); }}
      >
        <GlassSurface tone="light" radius={size / 2} pointerEvents="none" style={[s.back, box]}>
          {children}
        </GlassSurface>
      </Pressable>
    </Animated.View>
  );
}

/** Круглая стеклянная «назад» 44×44 — шапки кадров A.03.1, A.03.2 и всего разговора. */
export function GlassBack({ onPress, label, style }: { onPress: () => void; label: string; style?: ViewStyle }) {
  return (
    <GlassIconButton onPress={onPress} label={label} style={style}>
      <IconChevronLeft size={22} c={color.fg} />
    </GlassIconButton>
  );
}

// ===== вид
const s = StyleSheet.create({
  /** Кромка запасного пути — светлая внутренняя тень борда, нарисованная волосяной рамкой. */
  edge: { borderWidth: StyleSheet.hairlineWidth, borderColor: '#FFFFFF99' },
  back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  /*
    ОБЁРТКА РОВНО 44×44. Без размера она растягивалась по ширине родителя (колонка шапки тянет детей
    вбок), и на Android тень `elevation` рисовалась по ЕЁ контуру: серая пилюля во всю ширину экрана
    рядом со стрелкой — «странная штука сверху» с телефона тестировщика. На iOS тень строится по
    самому стеклу, поэтому там этого не было видно.
    ТЕНИ НА ANDROID НЕТ вовсе: у полупрозрачного стекла она просвечивает сквозь плёнку и делает его
    грязно-серым (см. GlassSurface).
  */
  backShadow: {
    width: 44,
    height: 44,
    borderRadius: 22,
    ...Platform.select({
      ios: { shadowColor: '#0A0A14', shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
      default: {},
    }),
  },
});
