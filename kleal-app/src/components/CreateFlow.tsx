/**
 * Детали мастера «Creating intent» — борд «0 · Create the intent» (Figma 6864:119674, GR.04–GR.12).
 *
 * Мастер живёт на двух экранах (app/create.tsx — «что делаем», app/intent.tsx — всё остальное), но
 * на борде это ОДИН экран: та же шапка с процентами, тот же вопрос пузырём Kleal, те же строки и
 * чипы. Поэтому всё общее лежит здесь — разойдись копии, и между шагом 10% и шагом 30% поменялся бы
 * вид шапки, а человек увидел бы смену экрана там, где её нет.
 *
 * Числа — с кадров:
 *   шапка «App Bar · Fixed» 56: поля 6/16/4/16, ряд 44, полоса прогресса 100×2 под заголовком;
 *   вопрос — «Agent Message»: пузырь светлого стекла 20/20/20/4, поля 12/16, Geist 15/22, под ним
 *     подпись Geist 12/16 #5A616E через 12;
 *   строка выбора — «Option»: 54 высотой, поля 16, скругление 16, белое 16% (выбранная 36%),
 *     значок 22 коралловой линией, подпись Geist 600 13/20, пояснение в бледных скобках;
 *   чип — 36, скругление 999, стекло; выбранный — коралл с белой подписью Geist 500 12/16;
 *   «Step N of 3» — стекло 45%, скругление 20, три полосы 3 высотой через 6.
 */
import React, { useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, Pressable, ScrollView, TextInput, Platform, StyleProp, ViewStyle,
} from 'react-native';
import Animated from 'react-native-reanimated';
import { color, font, heading } from '../theme';
import { T, useLang } from '../i18n';
import { GlassBack, GlassSurface, usePress } from './LiquidGlass';
import { LogoFace } from './Logo';
import { IconCheck, IconMic } from './icons';
import Markdown from './Markdown';
import { BubbleIn } from './ChatMotion';

/** Подпись пояснения в скобках и сами скобки — #AFAFAF с кадра («[in person]»). */
const BRACKET = '#AFAFAF';
const MUTED = '#5A616E';
const TIME = '#8A8F96';

// ===================================================================== шапка

export function CreatingHeader({
  pct, onBack, title,
}: {
  /** 10 / 30 / 40 / 60 / 70 / 90 / 100 — проценты кадров GR.04–GR.12. */
  pct: number;
  onBack: () => void;
  /** «Creating intent» по умолчанию; «Change the intent» — правка с GR.14g. */
  title?: string;
}) {
  const lang = useLang();
  const p = Math.max(0, Math.min(100, Math.round(pct)));
  return (
    <View style={s.head}>
      <View style={s.headRow}>
        <View style={s.slot}>
          <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={onBack} />
        </View>
        <Text style={[s.headTitle, heading(lang, { fontSize: 20, lineHeight: 24, letterSpacing: -0.2 })]} numberOfLines={1}>
          {title || CREATING.title()}
        </Text>
        <View style={[s.slot, s.slotRight]}>
          {/* Цифры шапки — TASA, не точечный LED борда: точки на телефоне читались как сбой
              (тестировщик 26.09), и это решение уже стоит на шаге возраста и проценте анкеты. */}
          <Text style={s.pct} accessibilityLabel={CREATING.done(p)}>{p}%</Text>
          <LogoFace size={30} />
        </View>
      </View>
      <View style={s.track} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
        <View style={[s.fill, { width: `${p}%` }]} />
      </View>
    </View>
  );
}

export const CREATING = {
  title: () => T('Создание интента', 'Creating intent', 'Creando propuesta'),
  done: (p: number) => T(`Готово на ${p}%`, `${p}% done`, `${p}% hecho`),
};

// ===================================================================== реплики

/** Вопрос шага: пузырь Kleal и подпись под ним («Agent Message» + «Caption»). */
export function StepAsk({ text, caption }: { text: string; caption?: string }) {
  return (
    <View style={s.ask}>
      <View style={s.shadowThem}>
        <GlassSurface tone="light" radius={20} style={[s.bub, s.bubThem]}>
          <Text style={s.bubText}>{text}</Text>
        </GlassSurface>
      </View>
      {caption ? <Text style={s.caption}>{caption}</Text> : null}
    </View>
  );
}

/** Реплика Kleal в ленте шага — со временем под ней. Длинное рисуется разметкой. */
export function AgentLine({ text, at, markdown = false, fresh = false }: { text: string; at?: string; markdown?: boolean; fresh?: boolean }) {
  return (
    <BubbleIn mine={false} fresh={fresh} style={s.rowThem}>
      <View style={s.shadowThem}>
        <GlassSurface tone="light" radius={20} style={[s.bub, s.bubThem]}>
          {/* Разметка — только если она в тексте есть: у Markdown свои поля абзаца, и однострочное
              «Great — … it is!» становилось выше пузыря кадра. */}
          {markdown && /[*_`#|]|\n/.test(text) ? <Markdown text={text} /> : <Text style={s.bubText}>{text}</Text>}
        </GlassSurface>
      </View>
      {at ? <Text style={s.time}>{at}</Text> : null}
    </BubbleIn>
  );
}

/** Своя реплика — коралловое стекло 20/20/4/20 со свечением. */
export function MyLine({ text, at, fresh = false }: { text: string; at?: string; fresh?: boolean }) {
  return (
    <BubbleIn mine fresh={fresh} style={s.rowMe}>
      <View style={s.shadowMe}>
        <GlassSurface tone="brand" radius={20} style={[s.bub, s.bubMe]}>
          <Text style={[s.bubText, { color: color.onPrimary }]}>{text}</Text>
        </GlassSurface>
      </View>
      {at ? <Text style={[s.time, { textAlign: 'right' }]}>{at}</Text> : null}
    </BubbleIn>
  );
}

export function Caption({ text, style }: { text: string; style?: StyleProp<any> }) {
  return <Text style={[s.caption, style]}>{text}</Text>;
}

/** Подпись группы контролов: «Day», «How many, you included» — TASA 600 15/20. */
export function PrefLabel({ text, right }: { text: string; right?: React.ReactNode }) {
  const lang = useLang();
  return (
    <View style={s.prefRow}>
      <Text style={[s.pref, lang === 'ru' && { fontFamily: font.textSemibold }]}>{text}</Text>
      {right}
    </View>
  );
}

// ===================================================================== выбор

/**
 * Строка выбора с галочкой. Выбранная плотнее (белое 36% против 16%) и с коралловой галочкой
 * справа — на кадре это единственное, чем выбранная отличается. Пояснение в скобках: скобки
 * бледные, слово обычным весом.
 */
export function ChoiceRow({
  Icon, label, sub, on, onPress, disabled,
}: {
  Icon?: (p: { size?: number; c?: string }) => React.ReactElement;
  label: string;
  sub?: string;
  on: boolean;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected: on, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [s.option, on && s.optionOn, pressed && s.optionPressed]}
    >
      {Icon ? <Icon size={22} c={color.primary} /> : null}
      <Text style={[s.optLabel, !sub && { flex: 1 }]}>{label}</Text>
      {sub ? (
        <Text style={s.optSub} numberOfLines={1}>
          <Text style={{ color: BRACKET }}>[</Text>{sub}<Text style={{ color: BRACKET }}>]</Text>
        </Text>
      ) : null}
      {on ? <Check /> : <View style={{ width: 20 }} />}
    </Pressable>
  );
}

/** Галочка 20 — коралловая линия, как «Check» на кадре. */
export function Check({ c = color.primary }: { c?: string }) {
  return <IconCheck size={20} c={c} />;
}

/**
 * Чип 36: стекло с кромкой; выбранный — сплошной коралл. Внутри Pressable стекло без касаний
 * (см. LiquidGlass): его распознаватели иначе отменяют нажатие.
 */
export function GlassChip({
  label, on, onPress, style, disabled,
}: {
  label: string; on: boolean; onPress: () => void; style?: StyleProp<ViewStyle>; disabled?: boolean;
}) {
  const p = usePress(0.97);
  return (
    <Animated.View style={[p.style, style]}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ selected: on, disabled }}
        disabled={disabled}
        onPress={onPress}
        onPressIn={p.onPressIn}
        onPressOut={p.onPressOut}
      >
        {on ? (
          <View style={[s.chip, s.chipOn]}>
            <Text style={[s.chipText, { color: color.onPrimary }]} numberOfLines={1}>{label}</Text>
          </View>
        ) : (
          <GlassSurface tone="light" radius={18} pointerEvents="none" style={s.chip}>
            <Text style={[s.chipText, disabled && { color: color.neutral400 }]} numberOfLines={1}>{label}</Text>
          </GlassSurface>
        )}
      </Pressable>
    </Animated.View>
  );
}

/**
 * Ряд чипов, который листается вбок (Day, Time на GR.09): выбранный чип при открытии прокручен в
 * поле зрения — иначе «19:00» стоял бы за краем, а на экране светилось бы «00:00».
 */
export function ChipScroller({
  items, selected, onPick, chipWidth = 66,
}: {
  items: { key: string; label: string; disabled?: boolean }[];
  selected: string;
  onPick: (key: string) => void;
  /** Средняя ширина чипа — только для того, чтобы докрутить выбранный к центру. */
  chipWidth?: number;
}) {
  const ref = useRef<ScrollView>(null);
  const idx = items.findIndex((x) => x.key === selected);
  useEffect(() => {
    if (idx < 0) return;
    const x = Math.max(0, idx * (chipWidth + 8) - 120);
    const id = setTimeout(() => ref.current?.scrollTo({ x, animated: false }), 0);
    return () => clearTimeout(id);
    // Докручиваем один раз на открытии ряда, а не на каждом выборе: под пальцем ряд не прыгает.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <ScrollView
      ref={ref}
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={s.chipScroll}
      style={s.chipScrollOuter}
    >
      {items.map((it) => (
        <GlassChip key={it.key} label={it.label} on={it.key === selected} disabled={it.disabled}
          onPress={() => onPick(it.key)} />
      ))}
    </ScrollView>
  );
}

/** Ряд чипов равной ширины (How many, Who, Age). */
export function ChipRow({ children }: { children: React.ReactNode }) {
  return (
    <View style={s.chipRow}>
      {React.Children.map(children, (c) => (c ? <View style={{ flex: 1 }}>{c}</View> : null))}
    </View>
  );
}

// ===================================================================== «Step N of 3»

export function StepIndicator({ n, of = 3, label }: { n: number; of?: number; label: string }) {
  const lang = useLang();
  const fam = lang === 'ru' ? font.textSemibold : font.displaySemi;
  return (
    <GlassSurface tone="light" radius={20} style={s.stepBox}>
      <View style={s.stepRow}>
        <Text style={[s.stepWord, { fontFamily: fam }]}>{T('Шаг', 'Step', 'Paso')}</Text>
        <Text style={[s.stepWord, { fontFamily: fam }]}>
          <Text style={{ color: color.primary }}>{n}</Text>
          <Text style={{ color: BRACKET }}>{T(` из ${of}`, ` of ${of}`, ` de ${of}`)}</Text>
        </Text>
        <Text style={s.stepLabel}>{label}</Text>
      </View>
      <View style={s.bars}>
        {Array.from({ length: of }).map((_, i) => (
          <View key={i} style={[s.bar, i < n && s.barOn]} />
        ))}
      </View>
    </GlassSurface>
  );
}

// ===================================================================== поле ввода

/**
 * «Chat/Composer» мастера: стекло 48 во всю ширину, справа микрофон. Сказанное словами уходит тем
 * же путём, что и раньше, — поле только выглядит по-новому.
 */
export function CreateComposer({
  value, onChange, onSubmit, placeholder, editable = true, locked = false,
}: {
  value: string; onChange: (t: string) => void; onSubmit: () => void; placeholder: string; editable?: boolean;
  /**
   * Поле закрыто совсем (шаги мастера с выбором, 18.10.2026): текст здесь уводил затею в обход
   * шагов и ломал поток. Видно, что писать нельзя: подсказка вместо «Сообщение…», микрофон бледный,
   * касания не принимаются. Гасим содержимое, а не стекло — у стекла и его предков opacity не трогаем.
   */
  locked?: boolean;
}) {
  return (
    <GlassSurface tone="light" radius={999} style={s.field} pointerEvents={locked ? 'none' : 'auto'}>
      <TextInput
        style={[s.input, locked && s.inputLocked]}
        value={locked ? '' : value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={MUTED}
        onSubmitEditing={locked ? undefined : onSubmit}
        returnKeyType="send"
        editable={editable && !locked}
        accessibilityState={{ disabled: locked }}
      />
      <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send', 'Enviar')}
                 onPress={locked ? undefined : onSubmit} disabled={locked} hitSlop={8} style={locked && s.micLocked}>
        <IconMic c={MUTED} />
      </Pressable>
    </GlassSurface>
  );
}

// ===================================================================== вид

const s = StyleSheet.create({
  inputLocked: { opacity: 0.7 },
  micLocked: { opacity: 0.35 },
  head: { paddingHorizontal: 16, paddingTop: 6, paddingBottom: 4, alignItems: 'center' },
  headRow: { flexDirection: 'row', alignItems: 'center', height: 44, alignSelf: 'stretch', gap: 8 },
  slot: { width: 72, flexDirection: 'row', alignItems: 'center', gap: 8 },
  slotRight: { justifyContent: 'flex-end' },
  headTitle: { flex: 1, textAlign: 'center', color: color.fg } as any,
  pct: { fontFamily: font.displaySemi, fontSize: 15, lineHeight: 16, color: MUTED, fontVariant: ['tabular-nums'] } as any,
  /** Полоса 100×2 под заголовком: дорожка — белое 67%, заполнение — коралл. */
  track: { width: 100, height: 2, borderRadius: 1, backgroundColor: 'rgba(255,255,255,0.67)', overflow: 'hidden' },
  fill: { height: 2, borderRadius: 1, backgroundColor: color.primary },

  ask: { gap: 12 },
  rowMe: { alignItems: 'flex-end', gap: 4 },
  rowThem: { alignItems: 'flex-start', gap: 4 },
  bub: { paddingVertical: 12, paddingHorizontal: 16 },
  bubMe: { borderBottomRightRadius: 4 },
  bubThem: { borderBottomLeftRadius: 4 },
  shadowMe: {
    maxWidth: '73%', alignSelf: 'flex-end',
    shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 16, shadowOffset: { width: 0, height: 6 },
  },
  shadowThem: {
    maxWidth: '73%', alignSelf: 'flex-start',
    shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 2, shadowOffset: { width: 0, height: 1 },
  },
  bubText: { fontFamily: font.text, fontSize: 15, lineHeight: 22, color: color.fg } as any,
  caption: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: MUTED } as any,
  time: { fontFamily: font.text, fontSize: 11, lineHeight: 16, color: TIME, marginTop: 3 } as any,

  prefRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  pref: { fontFamily: font.displaySemi, fontSize: 15, lineHeight: 20, color: color.fg } as any,

  option: {
    minHeight: 54, flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 16, paddingVertical: 16, borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.16)',
  },
  optionOn: { backgroundColor: 'rgba(255,255,255,0.36)' },
  optionPressed: { backgroundColor: 'rgba(255,255,255,0.5)' },
  optLabel: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.fg, minWidth: 43 } as any,
  optSub: { flex: 1, fontFamily: font.text, fontSize: 13, lineHeight: 20, color: color.fg } as any,


  chip: { height: 36, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center', borderRadius: 18 },
  chipOn: {
    backgroundColor: color.primary,
    ...Platform.select({
      ios: { shadowColor: color.primary, shadowOpacity: 0.25, shadowRadius: 8, shadowOffset: { width: 0, height: 3 } },
      default: {},
    }),
  },
  chipText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.fg } as any,
  chipRow: { flexDirection: 'row', gap: 8 },
  chipScrollOuter: { marginHorizontal: -16 },
  chipScroll: { gap: 8, paddingHorizontal: 16 },

  stepBox: { paddingTop: 16, paddingHorizontal: 16, paddingBottom: 18, gap: 4 },
  stepRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stepWord: { fontSize: 13, lineHeight: 20, color: color.fg, minWidth: 60 } as any,
  stepLabel: { fontFamily: font.text, fontSize: 13, lineHeight: 13, color: color.fg, minWidth: 60, textAlign: 'right' } as any,
  bars: { flexDirection: 'row', gap: 6, marginTop: 4 },
  bar: { flex: 1, height: 3, borderRadius: 2, backgroundColor: '#ECECEC' },
  barOn: { backgroundColor: color.primary },

  field: { height: 48, flexDirection: 'row', alignItems: 'center', paddingLeft: 16, paddingRight: 12, gap: 8 },
  /** Поле касания 24 — полоса 2 по центру, бегунок 16 (кадр: «fill» 87×16). */
  slider: { height: 24, justifyContent: 'center' },
  sliderTrack: { height: 2, borderRadius: 1, backgroundColor: '#D3CAC0', overflow: 'hidden' },
  sliderFill: { height: 2, backgroundColor: 'rgba(255,56,92,0.82)' },
  sliderThumb: {
    position: 'absolute', top: 4, width: 16, height: 16, marginLeft: -8, borderRadius: 8,
    backgroundColor: color.primary, borderWidth: 2, borderColor: '#FFFFFF',
    shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 4, shadowOffset: { width: 0, height: 2 },
  },
  input: { flex: 1, color: color.fg, fontFamily: font.text, fontSize: 15, paddingVertical: 0 } as any,
});

// ===================================================================== ползунок радиуса

/**
 * Ползунок «How far can people come from?» (GR.11): полоса 2, пройденное — коралл 82%, остаток —
 * тёплый #D3CAC0, бегунок — коралловая точка 16 с белой каймой.
 *
 * Свой, а не @react-native-community/slider: на iOS 26 системный рисует бегунок стеклянной
 * капсулой 40×24 — на кадре такой нет, и рядом с тонкой полосой она читалась как отдельная кнопка.
 * Касание по полосе ставит значение сразу, движение пальца ведёт его дальше.
 */
export function RadiusSlider({
  value, min = 1, max = 50, onChange, onDrag,
}: {
  value: number; min?: number; max?: number;
  onChange: (v: number) => void;
  /** Палец на полосе — экран выключает свою прокрутку, иначе она забирает жест. */
  onDrag?: (on: boolean) => void;
}) {
  const w = useRef(0);
  const set = (x: number) => {
    if (!w.current) return;
    const t = Math.max(0, Math.min(1, x / w.current));
    onChange(Math.round(min + t * (max - min)));
  };
  const t = (Math.max(min, Math.min(max, value)) - min) / (max - min);
  return (
    <View
      style={s.slider}
      onLayout={(e) => { w.current = e.nativeEvent.layout.width; }}
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderTerminationRequest={() => false}
      onResponderGrant={(e) => { onDrag?.(true); set(e.nativeEvent.locationX); }}
      onResponderMove={(e) => set(e.nativeEvent.locationX)}
      onResponderRelease={() => onDrag?.(false)}
      onResponderTerminate={() => onDrag?.(false)}
      accessible
      accessibilityRole="adjustable"
      accessibilityValue={{ min, max, now: value, text: `${value} km` }}
      accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
      onAccessibilityAction={(e) => {
        if (e.nativeEvent.actionName === 'increment') onChange(Math.min(max, value + 1));
        if (e.nativeEvent.actionName === 'decrement') onChange(Math.max(min, value - 1));
      }}
    >
      <View pointerEvents="none" style={s.sliderTrack}>
        <View style={[s.sliderFill, { width: `${t * 100}%` }]} />
      </View>
      <View pointerEvents="none" style={[s.sliderThumb, { left: `${t * 100}%` }]} />
    </View>
  );
}

