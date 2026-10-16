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
import { Dimensions, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useSheetKeyboard } from '../keyboard';
import { T, useLang } from '../i18n';
import { color, font, heading, labelFamily, space, type } from '../theme';
import { BlurView } from 'expo-blur';
import { GlassIconButton } from './LiquidGlass';
import { IconChevronRight, IconClose } from './icons';

/**
 * ВИД ИЗ БОРДА «GR · Offline — new layout» (листы GR.18a–GR.53). Лист — сливочное стекло со
 * скруглением 28 сверху, ручка 36×4 над заголовком, заголовок гарнитурой шапок, крестик — в том же
 * стеклянном круге 44, что «назад» в шапке. Стекло кладётся ниже края экрана на `UNDER`: у
 * системного стекла скругление одно на все углы, и нижние углы уводятся за край, а не срезаются.
 */
const UNDER = 40;

export function Sheet({
  visible, onClose, title, children, bottomInset, grip = true,
}: {
  visible: boolean;
  onClose: () => void;
  /** Строка — почти всегда; разметка — когда в названии есть цветная часть («Kleal Plus+», GR.15). */
  title?: React.ReactNode;
  children: React.ReactNode;
  /**
   * Свой нижний отступ В ПОКОЕ. Клавиатуру прибавляет САМ лист (см. ниже) — передавать её сюда
   * не нужно и нельзя: подъём сложится вдвое.
   */
  bottomInset?: number;
  /**
   * Полоска-ручка сверху. Когда-то была у двух листов из одиннадцати, и решать, нужна ли она
   * всем, оставили тому, кто рисует. Нарисовали: в борде «GR · Offline — new layout» она у
   * КАЖДОГО листа, поэтому теперь включена по умолчанию.
   */
  grip?: boolean;
}) {
  const insets = useSafeAreaInsets();
  const lang = useLang();
  /*
    КЛАВИАТУРА — ЗАБОТА ЛИСТА, А НЕ ЭКРАНА.
    Лист прижат к низу окна, и открытая клавиатура ложится прямо на него: у листа языков и
    локации от всего содержимого оставался один заголовок, а поле поиска, ради которого лист и
    открывали, уезжало под клавиши. Раньше подъём считал каждый вызывающий сам — и считал только
    на Android, потому что брал `useKeyboardInset`, который на iOS молчит намеренно. Теперь это
    одно место на все одиннадцать листов.

    ПОТОЛОК ВЫСОТЫ — из той же беды. Лист растёт вверх по содержимому, и поднятый на высоту
    клавиатуры длинный список ушёл бы верхом за экран вместе с кнопкой «Применить». Потолок
    оставляет ему ровно свободную часть окна; прокрутка внутри у листов своя.
  */
  const kb = useSheetKeyboard();
  /*
    ЛИСТ ВСТАЁТ НАД КЛАВИАТУРОЙ, А НЕ ОТРАЩИВАЕТ ОТСТУП ПОД НЕЁ.
    Прибавлять высоту клавиатуры к `paddingBottom` — ошибка, и она сразу себя показала: лист
    становится выше ровно на клавиатуру, а потолок высоты на неё же уменьшен, и содержимому
    остаётся `окно − две клавиатуры`. Лист прижат к низу, поэтому лишнее уходит ВВЕРХ за его
    край: у «Языков» срезало поле поиска и весь список, у сводки — само поле правки.
    Правильно — подвинуть сам лист: `bottom` равен высоте клавиатуры. Высота при этом свободна,
    и потолок считается от того, что осталось на экране.
  */
  const pad = kb > 0 ? 12 : (bottomInset ?? Math.max(insets.bottom, 18));
  const room = Math.max(240, Dimensions.get('window').height - kb - insets.top - 12);
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel={T('Закрыть', 'Close', 'Cerrar')} />
      <View style={[s.sheet, { bottom: kb - UNDER, paddingBottom: pad + UNDER, maxHeight: room + UNDER }]}>
        {/*
          ПОДЛОЖКА ЛИСТА — БЕЛОЕ 80% С РАЗМЫТИЕМ 40 (борд «0 · Create the intent», все 17 листов:
          «Sheet · …» fill #FFFFFF·80%, Background blur 40, поверх затемнения 40%). Сквозь неё
          затемнение проступает, и лист выходит светло-серым, как на кадрах. Прежняя сливочная
          подложка #F5F1EC с системным стеклом была видом борда «GR · Offline» — новый борд её сменил.
          Размытие — BlurView, а не системное стекло: стекло над затемнением преломляло его пятнами.
          На Android expo-blur не размывает, но под листом ровное затемнение — плёнка 80% даёт тот же цвет.
        */}
        <View pointerEvents="none" style={[StyleSheet.absoluteFill, s.skin]}>
          <BlurView intensity={40} tint="light" style={StyleSheet.absoluteFill} />
          <View style={[StyleSheet.absoluteFill, s.film]} />
        </View>
        {grip ? <View style={s.grip} /> : null}
        {title ? (
          <View style={s.head}>
            <Text style={[s.title, heading(lang, type.headingSm)]} numberOfLines={2}>{title}</Text>
            <GlassIconButton label={T('Закрыть', 'Close', 'Cerrar')} onPress={onClose}>
              <IconClose size={22} />
            </GlassIconButton>
          </View>
        ) : null}
        {children}
      </View>
    </Modal>
  );
}

/**
 * Текст листа — два яруса под заголовком (борд GR.19, GR.24b, GR.51): вопрос гарнитурой шапок
 * 15/20 и пояснение Geist 13/18. Между шапкой, вопросом, пояснением и кнопками — 24, как во
 * «content» листа на борде; лист сам кладёт 8 между детьми, поэтому здесь добираем остальное.
 */
export function SheetText({ lead, note, children }: { lead?: string; note?: string; children?: React.ReactNode }) {
  const lang = useLang();
  return (
    <View style={s.text}>
      {lead ? <Text style={[s.lead, { fontFamily: labelFamily(lang) }]}>{lead}</Text> : null}
      {children}
      {note ? <Text style={s.body}>{note}</Text> : null}
    </View>
  );
}

/**
 * Пункт листа: что делает — крупно, что при этом случится — мелко под ним (меню группы GR.18a:
 * стеклянная строка со скруглением 16 и стрелкой справа). Выключенный пункт бледнеет ТЕКСТОМ, а
 * не прозрачностью строки: полупрозрачный предок гасит системное стекло целиком.
 */
export function SheetItem({
  label, note, onPress, danger = false, disabled = false, icon,
}: {
  label: string; note?: string; onPress: () => void; danger?: boolean; disabled?: boolean;
  /** Знак слева, как у пунктов меню группы. */
  icon?: React.ReactNode;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [s.item, pressed && s.itemPressed]}
    >
      {/* Пункт меню борда (Menu Item, GR.21a): белое стекло 24% без кромки, поля 12/16,
          скругление 16; подпись 15/22, пояснение 13/18, стрелка 20. Прежнее плотное стекло
          72% спорило с листом — на борде пункты едва светлее самого листа. */}
      {icon ? <View style={s.itemIcon}>{icon}</View> : null}
      <View style={{ flex: 1 }}>
        <Text style={[s.label, danger && s.danger, disabled && s.off]}>{label}</Text>
        {note ? <Text style={[s.note, disabled && s.off]}>{note}</Text> : null}
      </View>
      <IconChevronRight size={20} c={disabled ? color.neutral300 : color.muted} />
    </Pressable>
  );
}

// ===== вид

const s = StyleSheet.create({
  scrim: { ...StyleSheet.absoluteFill, backgroundColor: color.scrim },
  /*
    Под стеклом — сплошная сливочная подложка (#F5F1EC, как в борде). Без неё системное стекло
    честно преломляло затемнение под листом, и лист выходил бежево-серым вместо сливочного.
  */
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 20, paddingTop: 12, gap: space.sm,
    shadowColor: '#0A0A14', shadowOpacity: 0.12, shadowRadius: 32, shadowOffset: { width: 0, height: -4 },
  },
  skin: { borderTopLeftRadius: 28, borderTopRightRadius: 28, overflow: 'hidden' },
  film: { backgroundColor: 'rgba(255,255,255,0.8)' },
  grip: {
    width: 36, height: 4, borderRadius: 2, backgroundColor: color.fg,
    alignSelf: 'center', marginBottom: space.sm,
  },
  /** От шапки до содержимого 24 (8 листа + 16), как в «content» листов борда. */
  head: { flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: 44, marginBottom: 16 },
  title: { flex: 1, color: color.fg } as any,
  item: {
    flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12,
    borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.24)', marginBottom: -4,
  },
  itemPressed: { backgroundColor: 'rgba(255,255,255,0.5)' },
  itemIcon: { width: 20, alignItems: 'center' },
  label: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 22, color: color.fg } as any,
  /** «End the group» — destructive палитры борда (#D92D2D). */
  danger: { color: '#D92D2D' },
  note: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.muted } as any,
  off: { color: color.neutral400 },
  text: { gap: 24, marginBottom: 24 },
  lead: { fontSize: 15, lineHeight: 20, color: color.fg } as any,
  body: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,
});
