/**
 * Нижний лист — один на всё приложение.
 *
 * Их было девять: в переписке, в списке сообщений, в группе, в плане, у Бадди, в кандидате, в
 * выдаче, в оболочке профиля. Разметка совпадала до строчки, а числа успели разъехаться —
 * `paddingTop` 18 против 14, `gap` то `md`, то `sm`. Никто этого не решал: копии просто пожили
 * порознь. Затемнение во всех девяти стояло литералом `'#0006'` при живом файле токенов.
 *
 * Что лист делает сам и о чём экрану больше думать не надо:
 *   — закрывается по касанию вне себя и по системному «назад» (Android);
 *   — не залезает под домашнюю полосу — сам спрашивает безопасные отступы;
 *   — шапка с названием и крестиком появляется, только если название дали.
 *
 * Содержимое остаётся за экраном: у каждого листа оно своё, и общего в нём — ничего.
 */
import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { T } from '../i18n';
import { color, radius as rad, space, type } from '../theme';

export function Sheet({
  visible, onClose, title, children, bottomInset, grip = false,
}: {
  visible: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  /**
   * Свой нижний отступ — ровно для листа с полями ввода: там его считает клавиатура, иначе она
   * закрывает кнопку под формой. Единственный такой лист в приложении — «предложить другое время».
   */
  bottomInset?: number;
  /**
   * Полоска-ручка сверху. Есть у двух листов из одиннадцати — окна выбора у Бадди и правки
   * профиля. Оставлена признаком, а не додумана до общего вида: решать, нужна ли она всем,
   * должен тот, кто рисует, а не тот, кто сводил копии.
   */
  grip?: boolean;
}) {
  const insets = useSafeAreaInsets();
  const pad = bottomInset ?? Math.max(insets.bottom, 18);
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel={T('Закрыть', 'Close')} />
      <View style={[s.sheet, { paddingBottom: pad }]}>
        {grip ? <View style={s.grip} /> : null}
        {title ? (
          <View style={s.head}>
            <Text style={s.title} numberOfLines={1}>{title}</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={T('Закрыть', 'Close')}
              onPress={onClose}
              hitSlop={10}
            >
              <Text style={s.x}>✕</Text>
            </Pressable>
          </View>
        ) : null}
        {children}
      </View>
    </Modal>
  );
}

/** Пункт листа: что делает — крупно, что при этом случится — мелко под ним. */
export function SheetItem({
  label, note, onPress, danger = false, disabled = false,
}: {
  label: string; note?: string; onPress: () => void; danger?: boolean; disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[s.item, disabled && { opacity: 0.45 }]}
    >
      <Text style={[s.label, danger && { color: color.primary }]}>{label}</Text>
      {note ? <Text style={s.note}>{note}</Text> : null}
    </Pressable>
  );
}

// ===== вид

const s = StyleSheet.create({
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: color.scrim },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: color.card,
    borderTopLeftRadius: rad.xxl, borderTopRightRadius: rad.xxl,
    paddingHorizontal: 20, paddingTop: 18, gap: space.sm,
  },
  grip: {
    width: 44, height: 4, borderRadius: 2, backgroundColor: color.neutral300,
    alignSelf: 'center', marginBottom: space.sm,
  },
  head: { flexDirection: 'row', alignItems: 'center', marginBottom: space.sm },
  title: { flex: 1, fontSize: 20, fontWeight: '700', color: color.fg } as any,
  x: { fontSize: 20, color: color.fg },
  item: { paddingVertical: 10 },
  label: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  note: { ...type.caption, color: color.muted, marginTop: 2 } as any,
});
