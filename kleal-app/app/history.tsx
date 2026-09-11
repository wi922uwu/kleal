/**
 * История разговоров с Kleal — модальное окно.
 *
 * ПОЧЕМУ МОДАЛЬНОЕ, А НЕ ВКЛАДКА. История — это «загляну и вернусь», а не место, где живут:
 * человек пришёл перечитать, о чём договорились, и уходит обратно туда, откуда пришёл. Вкладка
 * заняла бы постоянное место в навигации под то, что открывают раз в неделю.
 *
 * ДВА СОСТОЯНИЯ ОДНОГО ЭКРАНА: список разговоров и один открытый. Разговор открывается ЗДЕСЬ ЖЕ,
 * а не отдельным маршрутом: иначе закрытие модального окна из глубины возвращало бы не туда,
 * откуда пришли, а на список внутри модалки — и «Закрыть» переставало бы закрывать.
 *
 * Данные — с устройства, разбор в src/history.ts. Оговорка про это стоит на самом экране: человек
 * не должен считать список резервной копией.
 */
import React, { useCallback, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Alert } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { HISTORY } from '../src/home';
import { useLang, dateLocale } from '../src/i18n';
import { loadHistory, clearHistory, type HistoryItem } from '../src/history';
import { color, displayFamily, radius as rad, space, type } from '../src/theme';

export default function History() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [open, setOpen] = useState<HistoryItem | null>(null);

  // Перечитываем на КАЖДОМ появлении: разговор мог закончиться минуту назад, и открывать список,
  // в котором его ещё нет, значит показывать неправду.
  useFocusEffect(
    useCallback(() => {
      let alive = true;
      loadHistory().then((h) => alive && setItems(h));
      return () => { alive = false; };
    }, [])
  );

  const when = (ms: number) => {
    const d = new Date(ms);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const time = d.toLocaleTimeString(dateLocale(lang === 'ru', 'en-GB'),
                                      { hour: '2-digit', minute: '2-digit' });
    return sameDay ? time
      : d.toLocaleDateString(dateLocale(lang === 'ru', 'en-GB'),
                             { day: 'numeric', month: 'short' }) + ' · ' + time;
  };

  const wipe = () =>
    Alert.alert(HISTORY.clearAsk(), undefined, [
      { text: HISTORY.close(), style: 'cancel' },
      { text: HISTORY.clear(), style: 'destructive',
        onPress: () => clearHistory().then(() => { setItems([]); setOpen(null); }) },
    ]);

  return (
    <View style={[s.wrap, { paddingTop: insets.top + space.md }]}>
      <View style={s.head}>
        <Text style={[s.title, { fontFamily: displayFamily(lang) }]} numberOfLines={1}>
          {open ? open.topic : HISTORY.title()}
        </Text>
        <Pressable accessibilityRole="button" hitSlop={10}
                   onPress={() => (open ? setOpen(null) : router.back())}>
          <Text style={s.close}>{HISTORY.close()}</Text>
        </Pressable>
      </View>

      {open ? (
        <ScrollView contentContainerStyle={s.body}>
          {open.lines.map((l, n) => (
            <View key={n} style={[s.bubble, l.who === 'me' ? s.mine : s.theirs]}>
              <Text style={[s.text, l.who === 'me' && s.textMine]}>{l.text}</Text>
              <Text style={[s.at, l.who === 'me' && s.atMine]}>{l.at}</Text>
            </View>
          ))}
        </ScrollView>
      ) : items.length ? (
        <ScrollView contentContainerStyle={s.body}>
          <Text style={s.local}>{HISTORY.local()}</Text>
          {items.map((it) => (
            <Pressable key={it.id} accessibilityRole="button" onPress={() => setOpen(it)}
                       style={({ pressed }) => [s.row, pressed && { opacity: 0.85 }]}>
              <Text style={s.rowTitle} numberOfLines={1}>{it.topic}</Text>
              <Text style={s.rowMeta}>{when(it.startedAt)} · {HISTORY.lines(it.lines.length)}</Text>
            </Pressable>
          ))}
          <Pressable accessibilityRole="button" onPress={wipe} style={s.clear}>
            <Text style={s.clearText}>{HISTORY.clear()}</Text>
          </Pressable>
        </ScrollView>
      ) : (
        <View style={s.empty}>
          <Text style={s.emptyTitle}>{HISTORY.empty()}</Text>
          <Text style={s.emptyHint}>{HISTORY.emptyHint()}</Text>
        </View>
      )}
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
    gap: space.md,
  },
  title: { ...type.display, color: color.fg, flexShrink: 1 } as any,
  close: { ...type.fieldLabel, color: color.primary } as any,
  body: { paddingHorizontal: space.lg, paddingBottom: space.xl * 2, gap: space.sm },
  /** Оговорка стоит НАД списком: её надо прочитать до того, как на список положились. */
  local: { ...type.caption, color: color.muted, marginBottom: space.sm } as any,
  row: {
    backgroundColor: color.card,
    borderRadius: rad.lg,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    gap: space.xs,
  },
  rowTitle: { ...type.labelMedium, color: color.fg } as any,
  rowMeta: { ...type.caption, color: color.muted } as any,
  /** Пузыри повторяют ленту разговора: история должна выглядеть тем, чем она была. */
  bubble: { maxWidth: '86%', borderRadius: rad.lg, paddingHorizontal: space.md, paddingVertical: space.sm },
  theirs: { alignSelf: 'flex-start', backgroundColor: color.card },
  mine: { alignSelf: 'flex-end', backgroundColor: color.primary },
  text: { ...type.body, color: color.fg } as any,
  textMine: { color: color.onPrimary },
  at: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  atMine: { color: color.onCoverSoft },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.xl, gap: space.sm },
  emptyTitle: { ...type.labelMedium, color: color.fg } as any,
  emptyHint: { ...type.caption, color: color.muted, textAlign: 'center' } as any,
  clear: { alignSelf: 'center', marginTop: space.lg, padding: space.md },
  clearText: { ...type.caption, color: color.muted } as any,
});
