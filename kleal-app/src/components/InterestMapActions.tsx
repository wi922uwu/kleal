/**
 * Низ карты интересов: корзина выбранного и два выхода.
 *
 * КОРЗИНА ВСЕГДА НА ВИДУ. Выбранное раньше стояло чипами в ленте ПОД картой — за краем экрана:
 * отметил в «Общении», ушёл в «Спорт» и уже не видишь, что набрал. Теперь это лента коралловых
 * меток над кнопками; крестик на метке снимает выбор. Лента листается вбок и не растёт в высоту —
 * кнопки под ней не уезжают (ради этого действия и вынесены из ленты чата, см. тест раскладки).
 *
 * ДВЕ КНОПКИ В РЯД, а не стопкой во всю ширину: «Добавить своё» — светлое стекло, главная —
 * коралловая и ведёт счёт до порога («Отметь ещё 2» → «Дальше · 5»). Подписи переносятся при
 * крупном системном шрифте, высота кнопок растёт вместе с ними.
 *
 * «ДОБАВИТЬ СВОЁ» НЕ УВОДИТ С КАРТЫ (владелец, 26.09). Кнопка ставит курсор в поле ввода; написанное
 * разбирает сервер, и оно ложится меткой в ту же корзину. Пока разбирается — бледная метка с
 * вертушкой; если слово читается по-разному — короткий вопрос с вариантами прямо над корзиной.
 */
import React, { useEffect, useRef } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { STEP_HOBBIES } from '../onboarding';
import { interestLabel } from '../interest-label';
import { font, space } from '../theme';
import { hTap } from '../haptics';
import { GlassPill } from './Glass';
import { IconClose } from './icons';

const CORAL = '#FF385C';
const INK = '#181B22';
const MUTED = '#5A616E';

type Option = { canonical: string; label: string; token: string };

export function InterestMapActions({
  selected, onDone, onRemove, onOwn, busy = [], note = '', ask = null, onAskPick, onAskSkip,
}: {
  selected: string[];
  onDone: (keys: string[]) => void;
  /** Снять выбор с метки в корзине. */
  onRemove?: (key: string) => void;
  /** «Добавить своё» — поставить курсор в поле ввода. */
  onOwn?: () => void;
  /** Свои слова, которые сейчас разбирает сервер. */
  busy?: string[];
  /** Короткое сообщение над корзиной: «уже выбрано», «не разобрал». */
  note?: string;
  /** Слово читается по-разному — выбрать прочтение. */
  ask?: { text: string; question: string; options: Option[] } | null;
  onAskPick?: (o: Option) => void;
  onAskSkip?: () => void;
}) {
  const need = 3;
  const left = need - selected.length;
  const tray = useRef<ScrollView>(null);
  // Новая метка встаёт в конец ленты — лента доезжает до неё, чтобы выбор был виден сразу.
  useEffect(() => { tray.current?.scrollToEnd?.({ animated: true }); }, [selected.length, busy.length]);
  return (
    <View style={styles.wrap} testID="interest-map-actions">
      {ask ? (
        <View style={styles.ask} testID="interest-map-ask">
          <Text style={styles.askQ} numberOfLines={2}>{ask.question || STEP_HOBBIES.ownWhich()}</Text>
          <View style={styles.askRow}>
            {ask.options.map((o) => (
              <Pressable key={o.token} accessibilityRole="button" onPress={() => { hTap(); onAskPick?.(o); }}
                         style={({ pressed }) => [styles.askOpt, pressed && styles.pressed]}>
                <Text style={styles.askOptText} numberOfLines={1}>{o.label || o.canonical}</Text>
              </Pressable>
            ))}
            <Pressable accessibilityRole="button" onPress={() => { hTap(); onAskSkip?.(); }} hitSlop={6}
                       style={({ pressed }) => [styles.askSkip, pressed && styles.pressed]}>
              <Text style={styles.askSkipText}>{STEP_HOBBIES.ownNone()}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
      {note ? <Text style={styles.note} numberOfLines={2} accessibilityLiveRegion="polite">{note}</Text> : null}
      {selected.length || busy.length ? (
        <ScrollView
          ref={tray}
          horizontal
          showsHorizontalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.tray}
          testID="interest-map-tray"
        >
          {selected.map((k) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              accessibilityLabel={`${STEP_HOBBIES.mapRemove()}: ${interestLabel(k)}`}
              onPress={() => { hTap(); onRemove?.(k); }}
              hitSlop={4}
              style={({ pressed }) => [styles.tag, pressed && styles.pressed]}
            >
              <Text style={styles.tagText} numberOfLines={1}>{interestLabel(k)}</Text>
              <IconClose size={12} c={CORAL} />
            </Pressable>
          ))}
          {busy.map((text) => (
            <View key={'busy:' + text} style={[styles.tag, styles.tagBusy]}>
              <Text style={[styles.tagText, styles.tagTextBusy]} numberOfLines={1}>{text}</Text>
              <ActivityIndicator size="small" color={MUTED} style={styles.spin} />
            </View>
          ))}
        </ScrollView>
      ) : null}
      <View style={styles.row}>
        <GlassPill label={STEP_HOBBIES.mapOwn()} labelLines={3} style={styles.action}
          onPress={() => onOwn?.()} />
        <GlassPill
          label={left > 0 ? STEP_HOBBIES.mapLeft(left) : STEP_HOBBIES.mapNext(selected.length)}
          labelLines={3}
          tone="brand"
          style={styles.action}
          disabled={left > 0}
          onPress={() => { if (left <= 0) onDone(selected); }}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  tray: { gap: 6, paddingVertical: 2, paddingHorizontal: 2 },
  /** Метка выбранного: коралл едва заметной заливкой, подпись и крестик — фирменным цветом. */
  tag: {
    height: 32, flexDirection: 'row', alignItems: 'center', gap: 6, paddingLeft: 12, paddingRight: 10,
    borderRadius: 16, backgroundColor: 'rgba(255,56,92,0.10)', borderWidth: 1, borderColor: 'rgba(255,56,92,0.22)',
  },
  tagText: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: CORAL, maxWidth: 180 } as any,
  /** Своё слово, пока сервер его разбирает: нейтральная метка — ещё не выбор. */
  tagBusy: { backgroundColor: 'rgba(255,255,255,0.6)', borderColor: '#FFFFFF' },
  tagTextBusy: { color: MUTED },
  spin: { transform: [{ scale: 0.7 }], marginRight: -4 },
  note: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: MUTED, paddingHorizontal: 4 } as any,
  /** Вопрос «что именно?»: светлая плашка над корзиной, варианты — метками. */
  ask: {
    gap: 8, padding: 10, borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.78)', borderWidth: 1, borderColor: '#FFFFFF',
  },
  askQ: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: INK } as any,
  askRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, alignItems: 'center' },
  askOpt: {
    height: 32, paddingHorizontal: 12, borderRadius: 16, justifyContent: 'center',
    backgroundColor: 'rgba(255,56,92,0.10)', borderWidth: 1, borderColor: 'rgba(255,56,92,0.28)',
  },
  askOptText: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: CORAL, maxWidth: 200 } as any,
  askSkip: { height: 32, paddingHorizontal: 8, justifyContent: 'center' },
  askSkipText: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: MUTED } as any,
  pressed: { transform: [{ scale: 0.96 }] },
  row: { flexDirection: 'row', gap: space.sm },
  action: { flex: 1, height: 'auto', minHeight: 48, paddingVertical: space.sm, paddingHorizontal: space.sm },
});
