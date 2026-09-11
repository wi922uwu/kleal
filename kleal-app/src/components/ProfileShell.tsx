/**
 * Оболочка экранов профиля: строка приложения с кнопкой назад и заголовком, под ней — прокрутка.
 *
 * Отдельно от ChatShell намеренно: там разговор с процентом и композером, здесь обычный экран с
 * настройками. Общее у них только то, что оба чем-то заняты сверху, и объединять их ради этого
 * значило бы получить компонент с двумя несвязанными половинами.
 */
import React from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Switch, Modal, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useKeyboardInset, dockBottom } from '../keyboard';
import { T } from '../i18n';
import { Sheet } from './Sheet';
import { color, radius as rad, space, type } from '../theme';

export function ProfileShell({
  title, onBack, right, children, footer, nav,
}: {
  title: string;
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
  const insets = useSafeAreaInsets();
  /** Android: подвал с кнопкой уезжает под клавиатуру, когда на экране есть поле. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.bar}>
        {onBack ? (
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} style={s.back} onPress={onBack}>
            <Text style={s.backIcon}>‹</Text>
          </Pressable>
        ) : <View style={{ width: 40 }} />}
        <Text style={s.title} numberOfLines={1}>{title}</Text>
        {right || <View style={{ width: 40 }} />}
      </View>
      <ScrollView
        // Клавиатура входит в отступ прокрутки: без этого поле внутри страницы (история, тест)
        // оставалось под ней — прокручивать было некуда.
        contentContainerStyle={[s.scroll, { paddingBottom: (footer ? 96 : 28) + (nav ? 84 : 0) + insets.bottom + kb }]}
        keyboardShouldPersistTaps="handled"
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

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  bar: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: space.md },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  backIcon: { fontSize: 24, color: color.fg, marginTop: -3 },
  title: { flex: 1, ...type.title, color: color.fg, fontWeight: '700' } as any,
  scroll: { paddingHorizontal: 16, gap: space.md },

  card: { backgroundColor: color.card, borderRadius: rad.lg, padding: space.lg, gap: space.sm },
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
    backgroundColor: color.bg, borderTopWidth: 1, borderTopColor: color.line,
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
  const kb = useKeyboardInset();
  return (
    <Sheet visible={open} onClose={onClose} title={title} bottomInset={dockBottom(insets.bottom, kb, 18)} grip>
        <ScrollView contentContainerStyle={e.body} keyboardShouldPersistTaps="handled"
                    style={maxHeight ? { maxHeight } : undefined}
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
