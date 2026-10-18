/**
 * Оболочка экранов профиля: строка приложения с кнопкой назад и заголовком, под ней — прокрутка.
 *
 * Отдельно от ChatShell намеренно: там разговор с процентом и композером, здесь обычный экран с
 * настройками. Общее у них только то, что оба чем-то заняты сверху, и объединять их ради этого
 * значило бы получить компонент с двумя несвязанными половинами.
 */
import React from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Switch, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useKeyboardInset, dockBottom } from '../keyboard';
import { T, useLang } from '../i18n';
import { Sheet } from './Sheet';
import { GlassBack, GlassSurface } from './LiquidGlass';
import { Ambient, GLOW_FORM } from './Ambient';
import { IconChevronRight, IconCheck, IconWand } from './icons';
import { color, radius as rad, space, type, heading } from '../theme';

export function ProfileShell({
  title, onBack, right, children, footer, nav, scrollEnabled = true,
}: {
  title: string;
  /** Карта внутри (B.07): пока её двигают пальцем, прокрутка экрана выключена. */
  scrollEnabled?: boolean;
  onBack?: () => void;
  right?: React.ReactNode;
  children: React.ReactNode;
  /** Прибитая книзу кнопка, когда экран что-то сохраняет. */
  footer?: React.ReactNode;
  /**
   * Нижняя панель приложения. Есть у профиля, потому что это вкладка, и её нет у разделов внутри
   * него: туда заходят кнопкой «назад», и у части из них снизу своя кнопка сохранения — две
   * прибитые полосы одна под другой спорили бы за одно и то же место.
   */
  nav?: React.ReactNode;
}) {
  const lang = useLang();
  const insets = useSafeAreaInsets();
  /** Android: подвал с кнопкой уезжает под клавиатуру, когда на экране есть поле. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  // Борд «Profile — new layout»: стеклянная «назад», заголовок слева шрифтом заголовков, фирменный
  // кремовый слой под всем экраном — как у «Сообщений» и «My activity».
  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <Ambient glows={GLOW_FORM} />
      <View style={s.bar}>
        {onBack ? <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={onBack} /> : null}
        <Text style={[s.title, heading(lang, type.headingSm)]} numberOfLines={1}>{title}</Text>
        {right || null}
      </View>
      <ScrollView
        // Клавиатура входит в отступ прокрутки: без этого поле внутри страницы (история, тест)
        // оставалось под ней — прокручивать было некуда.
        contentContainerStyle={[s.scroll, { paddingBottom: (footer ? 96 : 28) + (nav ? 84 : 0) + insets.bottom + kb }]}
        keyboardShouldPersistTaps="handled"
        scrollEnabled={scrollEnabled}
      >
        {children}
      </ScrollView>
      {footer ? <View style={[s.footer, { paddingBottom: dockBottom(insets.bottom, kb, 12) }]}>{footer}</View> : null}
      {nav}
    </View>
  );
}

/** Карточка-контейнер. Всё на экранах профиля живёт в них, как в вебе. */
export function Card({ children, style }: { children: React.ReactNode; style?: any }) {
  return <View style={[s.card, style]}>{children}</View>;
}

/**
 * Строка с переключателем. Родной Switch, а не свой: он один умеет объявлять себя экранному
 * диктору переключателем с состоянием, и жест у него уже привычный по всей системе.
 */
export function ToggleRow({
  label, desc, value, onChange,
}: {
  label: string;
  desc?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <View style={s.row}>
      <View style={{ flex: 1 }}>
        <Text style={s.rowLabel}>{label}</Text>
        {desc ? <Text style={s.rowDesc}>{desc}</Text> : null}
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        accessibilityLabel={label}
        trackColor={{ false: color.neutral300, true: color.primary }}
        thumbColor={color.card}
        ios_backgroundColor={color.neutral300}
      />
    </View>
  );
}

/** Строка-переход в другой экран. */
export function NavRow({
  title, sub, onPress,
}: {
  title: string;
  sub?: string;
  onPress?: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [s.card, s.navRow, pressed && { opacity: 0.9 }]}
    >
      <View style={{ flex: 1 }}>
        <Text style={s.navTitle}>{title}</Text>
        {sub ? <Text style={s.rowDesc}>{sub}</Text> : null}
      </View>
      <Text style={s.chev}>›</Text>
    </Pressable>
  );
}

/** Сегменты: язык, доступность, автономность агента. */
export function Segments({
  options, value, onChange,
}: {
  options: [string, string][];
  value: string | null;
  onChange: (v: string) => void;
}) {
  return (
    <View style={s.segs}>
      {options.map(([k, label]) => {
        const on = value === k;
        return (
          <Pressable
            key={k}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            onPress={() => onChange(k)}
            style={[s.seg, on && { backgroundColor: color.primary }]}
          >
            <Text style={[s.segText, on && { color: color.onPrimary }]} numberOfLines={1}>{label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export const Divider = () => <View style={s.divider} />;

/** Заголовок раздела и подпись под ним: «When you meet / Kleal applies these to every plan». */
export function SectionHead({ title, note }: { title: string; note?: string }) {
  return (
    <View style={s.secHead}>
      <Text style={s.secTitle}>{title}</Text>
      {note ? <Text style={s.secNote}>{note}</Text> : null}
    </View>
  );
}

/** Строка-переход нового вида (B.01): коралловый знак, заголовок, подпись, стрелка. */
export function LinkRow({
  title, sub, Icon, onPress,
}: {
  title: string; sub?: string; Icon?: (p: any) => React.ReactElement; onPress: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress}
               style={({ pressed }) => [s.card, s.linkRow, pressed && { opacity: 0.85 }]}>
      {Icon ? <Icon size={22} c={color.primary} /> : null}
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={s.linkTitle} numberOfLines={1}>{title}</Text>
        {sub ? <Text style={s.linkSub} numberOfLines={1}>{sub}</Text> : null}
      </View>
      <IconChevronRight size={20} c={color.muted} />
    </Pressable>
  );
}

/** Переключатель отдельной карточкой (B.04, B.08): заголовок, пояснение, тумблер. */
export function SwitchCard({
  label, desc, value, onChange, disabled = false,
}: {
  label: string; desc?: string; value: boolean; onChange: (v: boolean) => void; disabled?: boolean;
}) {
  return (
    <View style={[s.card, s.switchCard]}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={s.linkTitle}>{label}</Text>
        {desc ? <Text style={s.linkSub}>{desc}</Text> : null}
      </View>
      <Switch
        value={value}
        disabled={disabled}
        onValueChange={onChange}
        accessibilityLabel={label}
        trackColor={{ false: color.neutral300, true: color.primary }}
        thumbColor={color.card}
        ios_backgroundColor={color.neutral300}
      />
    </View>
  );
}

/** Строка выбора в листе (B.03, B.06): подпись и коралловая галочка у выбранного. */
export function OptionRow({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: on }} onPress={onPress}
               style={({ pressed }) => [s.option, pressed && { opacity: 0.85 }]}>
      <Text style={s.optionText}>{label}</Text>
      {on ? <IconCheck size={20} c={color.primary} /> : null}
    </Pressable>
  );
}

/** «Change it with Kleal» — стеклянная пилюля со знаком Kleal. */
export function KlealPill({ label, onPress, wide = false }: { label: string; onPress: () => void; wide?: boolean }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress}
               style={({ pressed }) => [wide ? { alignSelf: 'stretch' } : { alignSelf: 'flex-start' }, pressed && { opacity: 0.85 }]}>
      <GlassSurface tone="light" radius={999} style={[s.pill, wide && s.pillWide]} pointerEvents="none">
        <IconWand size={18} c={color.fg} />
        <Text style={s.pillText}>{label}</Text>
      </GlassSurface>
    </Pressable>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  bar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: space.md },
  title: { flex: 1, color: color.fg } as any,
  scroll: { paddingHorizontal: 16, gap: 8 },

  /** Карточка борда: светлое стекло на кремовом фоне, скругление 16, без рамки. */
  card: { backgroundColor: color.glassCard, borderRadius: 16, padding: 16, gap: space.sm },
  secHead: { gap: 2, marginTop: space.sm, marginBottom: 2 },
  secTitle: { ...type.body, color: color.fg, fontWeight: '600' } as any,
  secNote: { ...type.bodySmall, color: color.fg } as any,
  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 14 },
  linkTitle: { fontSize: 15, lineHeight: 20, fontWeight: '600', color: color.fg } as any,
  linkSub: { ...type.bodySmall, color: color.muted } as any,
  switchCard: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 12 },
  option: {
    minHeight: 48, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.6)', paddingHorizontal: 16,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
  },
  optionText: { ...type.bodySmall, color: color.fg, fontWeight: '500' } as any,
  pill: { height: 40, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 8 },
  pillWide: { height: 52, justifyContent: 'center' },
  pillText: { ...type.bodySmall, color: color.fg, fontWeight: '600' } as any,
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 10 },
  rowLabel: { ...type.body, color: color.fg, fontWeight: '500' } as any,
  rowDesc: { ...type.bodySmall, color: color.muted, marginTop: 2 } as any,
  navRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  navTitle: { ...type.title, color: color.fg } as any,
  chev: { fontSize: 22, color: color.neutral400 },
  divider: { height: 1, backgroundColor: color.line },

  segs: { flexDirection: 'row', gap: 4, backgroundColor: color.neutral100, borderRadius: rad.full, padding: 3 },
  seg: { flex: 1, height: 34, borderRadius: rad.full, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8 },
  segText: { ...type.labelMedium, color: color.fg } as any,

  footer: {
    paddingHorizontal: 16, paddingTop: space.md,
    backgroundColor: 'transparent',
  },
});

/**
 * Лист правки поверх профиля — кадры «Languages» и «Location» со «Accept changes».
 *
 * Одна оболочка на оба, потому что на кадрах они устроены одинаково: ручка, заголовок с крестиком,
 * содержимое и одна кнопка внизу. Отличается только содержимое, поэтому оно приходит детьми.
 *
 * Закрытие крестиком и по фону НЕ сохраняет: «Принять изменения» — единственная дверь наружу с
 * изменениями, и это видно по экрану.
 */
export function EditSheet({
  open, title, onClose, onAccept, acceptLabel, cancelLabel, children, scrollEnabled = true, maxHeight,
  busy = false,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  onAccept: () => void;
  acceptLabel: string;
  /**
   * Отдать жест содержимому листа.
   *
   * Нужно ровно одному листу — с картой. Карта живёт внутри этой прокрутки, и жест у них общий:
   * пока прокрутка включена, она забирает вертикальное движение себе, и карту нельзя ни
   * подвинуть, ни свести пальцами. В онбординге то же место уже решено так же; здесь этого
   * просто не было, и карта в профиле не двигалась вовсе.
   */
  scrollEnabled?: boolean;
  /**
   * Потолок высоты содержимого.
   *
   * Своей высоты у листа нет: он прижат к низу и растёт ВВЕРХ по содержимому, а прокрутить его
   * нечем — внутренняя прокрутка без потолка просто разворачивается во всю длину. Пока внутри
   * стоял список строк, это никому не мешало; лист с раскрытым полем (карта, циферблат) выносит
   * кнопку «Применить» за верх экрана, и нажать её становится нечем. Просит потолок ровно один
   * лист — правка интента со сводки; остальным десяти он не нужен и по умолчанию его нет.
   */
  maxHeight?: number;
  /** Кадры O.07a/O.10a: под главной кнопкой стоит тёмная «Cancel». Профильные листы её не просят —
   *  поэтому кнопка появляется только там, где подпись передана. Делает то же, что крестик. */
  cancelLabel?: string;
  /**
   * Работа идёт — кнопка показывает вертушку и не нажимается.
   *
   * Нужен листу, который не закрывается по нажатию, а ЖДЁТ ответа модели (пересборка сводки).
   * Без этого человек видит неизменную кнопку, жмёт её второй раз и получает второй запрос.
   * Остальным десяти листам ждать нечего, поэтому по умолчанию `false` и ничего не меняется.
   */
  busy?: boolean;
  children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  // Клавиатуру прибавляет сам `Sheet` — здесь только покой, иначе подъём сложится вдвое.
  return (
    <Sheet visible={open} onClose={onClose} title={title} bottomInset={Math.max(insets.bottom, 18)} grip>
        {/* flexShrink: прокрутка обязана УМЕТЬ сжаться. По умолчанию в RN она этого не делает и
            занимает всю высоту содержимого — с потолком у листа лишнее уезжает за верхний край
            вместе с первыми строками. Сжимаясь, она вместо этого прокручивается внутри себя, а
            заголовок и кнопка остаются на виду. */}
        <ScrollView contentContainerStyle={e.body} keyboardShouldPersistTaps="handled"
                    style={[{ flexShrink: 1 }, maxHeight ? { maxHeight } : null]}
                    scrollEnabled={scrollEnabled}>
          {children}
        </ScrollView>
        <Pressable accessibilityRole="button" accessibilityState={{ busy, disabled: busy }}
                   style={[e.accept, busy && e.acceptBusy]} onPress={busy ? undefined : onAccept}>
          {busy ? <ActivityIndicator color={color.onPrimary} />
                : <Text style={e.acceptText}>{acceptLabel}</Text>}
        </Pressable>
        {cancelLabel ? (
          <Pressable accessibilityRole="button" style={e.cancel} onPress={onClose}>
            <Text style={e.cancelText}>{cancelLabel}</Text>
          </Pressable>
        ) : null}
    </Sheet>
  );
}

const e = StyleSheet.create({
  body: { paddingVertical: space.sm, gap: space.md },
  accept: { height: 56, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  // Приглушаем, а не прячем: кнопка остаётся на месте, и видно, что ждут именно её.
  acceptBusy: { opacity: 0.7 },
  acceptText: { ...type.button, color: color.onPrimary } as any,
  cancel: { height: 56, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  cancelText: { ...type.button, color: '#fff' } as any,
});
