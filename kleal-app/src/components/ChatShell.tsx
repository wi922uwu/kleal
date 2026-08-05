/**
 * Общая оболочка чат-экранов: шапка с процентом, лента пузырей, слот под виджет, композер.
 *
 * Онбординг и создание интента устроены на борде одинаково — вопрос агента, виджет под ним,
 * строка «Message…» внизу. Пока это было написано дважды, любая правка ритма или отступов
 * расходилась между экранами; здесь одно место.
 */
import React, { forwardRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, Image,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Composer } from './Composer';
import { color, space, type } from '../theme';

export type Bubble = { who: 'bot' | 'me'; text: string; at: string; photo?: string };

export const ChatShell = forwardRef<ScrollView, {
  title: string;
  /** null — полосы и процента нет вовсе: шаг открыт не в рамках онбординга. */
  pct: number | null;
  thread: Bubble[];
  typing?: boolean;
  /** Виджет текущего шага — живёт ВНУТРИ ленты, под последней репликой. */
  widget?: React.ReactNode;
  /** Правый угол шапки до процента: например «Начать заново». */
  headerExtra?: React.ReactNode;
  /**
   * Выключает прокрутку ленты. Нужно виджетам, которые сами ловят движение пальца: кольцо возраста
   * крутится ровно в том же жесте, каким лента прокручивается, и без этого едет и то, и другое.
   */
  scrollEnabled?: boolean;
  /** Подсказка в поле ввода, когда она зависит от шага. */
  composerPlaceholder?: string;
  /** Поставить курсор в поле ввода — по кнопке «написать своё». */
  focusSignal?: number;
  onBack?: () => void;
  onSend?: (text: string) => void;
}>(function ChatShell(
  { title, pct, thread, typing, widget, headerExtra, scrollEnabled = true, composerPlaceholder, focusSignal, onBack, onSend },
  scroller
) {
  const insets = useSafeAreaInsets();
  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <View style={s.avatar} />
          <Text style={s.headTitle}>{title}</Text>
          {headerExtra}
          {pct == null ? null : <Text style={s.headPct}>{pct}%</Text>}
        </View>
        {pct == null ? null : (
          <View style={s.track}>
            <View style={[s.trackFill, { width: `${pct}%` }]} />
          </View>
        )}

        <ScrollView
          ref={scroller as any}
          contentContainerStyle={s.thread}
          keyboardShouldPersistTaps="handled"
          scrollEnabled={scrollEnabled}
        >
          {thread.map((m, i) => (
            <View key={i} style={{ alignItems: m.who === 'me' ? 'flex-end' : 'flex-start' }}>
              {m.photo ? (
                <Image source={{ uri: m.photo }} style={s.threadPhoto} />
              ) : (
                <View style={[s.bub, m.who === 'me' ? s.bubMe : s.bubBot]}>
                  <Text style={[s.bubText, m.who === 'me' && { color: color.onPrimary }]}>{m.text}</Text>
                </View>
              )}
              <Text style={s.time}>{m.at}</Text>
            </View>
          ))}

          {typing ? (
            <View style={[s.bub, s.bubBot, { alignSelf: 'flex-start' }]}>
              <ActivityIndicator size="small" color={color.muted} />
            </View>
          ) : null}

          {!typing ? widget : null}
        </ScrollView>

        <Composer onBack={onBack} onSend={onSend} placeholder={composerPlaceholder} focusSignal={focusSignal} bottomInset={insets.bottom} />
      </View>
    </KeyboardAvoidingView>
  );
});

/**
 * Реплика агента, нарисованная ВНУТРИ виджета, а не в ленте.
 *
 * Так на борде: после снимка агент хвалит фото прямо над кнопками «Оставить / Переснять», и это
 * тот же пузырь, что в ленте. Отдельный компонент, чтобы он не разъехался с лентой по скруглению
 * и цвету — расходиться начинают именно такие мелочи.
 */
export function BotLine({ children }: { children: React.ReactNode }) {
  return (
    <View style={s.bubBot}>
      <Text style={s.bubText}>{children}</Text>
    </View>
  );
}

export const chatStyles = StyleSheet.create({
  widget: { gap: space.md, marginTop: space.md, width: '100%' },
  hint: { ...type.caption, color: color.muted } as any,
  label: { ...type.bodySmall, color: color.muted } as any,
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  rowSplit: { flexDirection: 'row', gap: space.sm },
});

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingBottom: 10 },
  avatar: { width: 34, height: 34, borderRadius: 17, backgroundColor: color.primary },
  headTitle: { flex: 1, ...type.title, color: color.fg, fontWeight: '700' } as any,
  headPct: { ...type.labelMedium, color: color.muted } as any,
  track: { height: 3, backgroundColor: color.neutral100, marginHorizontal: 20, borderRadius: 2 },
  trackFill: { height: 3, backgroundColor: color.primary, borderRadius: 2 },
  thread: { paddingHorizontal: 20, paddingTop: space.lg, paddingBottom: space.lg, gap: 4 },
  bub: { maxWidth: '86%', paddingVertical: 12, paddingHorizontal: 14, marginTop: space.sm },
  bubBot: { alignSelf: 'flex-start', backgroundColor: color.neutral100, borderRadius: 16 },
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary, borderRadius: 16 },
  bubText: { ...type.body, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,
  threadPhoto: { width: 178, height: 218, borderRadius: 16, marginTop: space.sm },
});
