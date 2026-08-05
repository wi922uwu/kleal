/**
 * Разговор с Бадди — кадры O.02 и O.03.
 *
 * UX-КАРКАС: вид натянется поверх. Оформление держится на токенах темы и вынесено вниз файла одним
 * блоком; вся копия — в src/buddy.ts. Менять внешность можно, не притрагиваясь к логике.
 *
 * Бадди тут просто собеседник. Написанное ему НЕ становится интентом само собой: сервер только
 * сообщает, что распознал в сказанном план, и тогда появляется окно выбора — создавать или
 * продолжать разговор. Та же кнопка «Создать» в шапке открывает то же окно.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  ActivityIndicator, KeyboardAvoidingView, Platform, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { IconChevronLeft, IconMic } from '../src/components/icons';
import { useLang, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { buddy as buddyApi } from '../src/api';
import { BUDDY, SHEET, looksLikeIntent, Turn } from '../src/buddy';
import { color, radius as rad, space, type } from '../src/theme';

type Msg = { who: 'bot' | 'me'; text: string; at: string };

const now = () =>
  new Date().toLocaleTimeString(getLang() === 'ru' ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: getLang() !== 'ru',
  });

export default function Buddy() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const scroller = useRef<ScrollView>(null);

  /** Текст с главного экрана: человек уже сказал, что хочет, — повторять вопрос незачем. */
  const seed = String(useLocalSearchParams<{ q?: string }>().q || '').trim();

  const [thread, setThread] = useState<Msg[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  const [sheet, setSheet] = useState(false);
  /** Тема, с которой откроется создание интента, если человек его выберет. */
  const [topic, setTopic] = useState('');
  const started = useRef(false);

  const say = useCallback((who: 'bot' | 'me', text: string) => {
    setThread((t) => [...t, { who, text, at: now() }]);
  }, []);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [thread.length, typing]);

  const profile = () => ({
    name: st.profile.name, age: st.profile.age, city: st.profile.city,
    interests: st.profile.interests?.explicit || [],
    languages: st.profile.languages || {},
  });

  const send = useCallback(async (text: string, hist: Turn[]) => {
    const next: Turn[] = [...hist, { role: 'user', content: text }];
    setTurns(next);
    setTyping(true);
    try {
      const r: any = await buddyApi.chat(next, profile());
      setTyping(false);
      const reply = String(r?.reply || '');
      if (reply) {
        say('bot', reply);
        setTurns([...next, { role: 'assistant', content: reply }]);
      }
      // Распознанный план НЕ создаёт интент сам — он открывает окно выбора. Решает человек.
      if (looksLikeIntent(r)) {
        setTopic(text);
        setSheet(true);
      }
    } catch {
      setTyping(false);
      say('bot', BUDDY.offline());
    }
  }, [say, st.profile]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (seed) {
      say('me', seed);
      send(seed, []);
      return;
    }
    setTyping(true);
    setTimeout(() => { setTyping(false); say('bot', BUDDY.hello(st.profile.name || '')); }, 450);
  }, []);

  const submit = () => {
    const t = draft.trim();
    if (!t || typing) return;
    setDraft('');
    say('me', t);
    send(t, turns);
  };

  const toCreate = () => {
    setSheet(false);
    router.push({ pathname: '/create', params: topic ? { seed: topic } : {} });
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" style={s.back} onPress={() => router.back()}>
            <IconChevronLeft />
          </Pressable>
          <View style={{ flex: 1 }} />
          <Pressable
            accessibilityRole="button"
            style={s.createBtn}
            onPress={() => { setTopic(''); setSheet(true); }}
          >
            <Text style={s.createPlus}>+</Text>
            <Text style={s.createText}>{BUDDY.create()}</Text>
          </Pressable>
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
          {thread.map((m, i) => (
            <View key={i} style={{ alignItems: m.who === 'me' ? 'flex-end' : 'flex-start' }}>
              <View style={[s.bub, m.who === 'me' ? s.bubMe : s.bubBot]}>
                <Text style={[s.bubText, m.who === 'me' && { color: color.onPrimary }]}>{m.text}</Text>
              </View>
              <Text style={s.time}>{m.at}</Text>
            </View>
          ))}
          {typing ? (
            <View style={[s.bub, s.bubBot, { alignSelf: 'flex-start' }]}>
              <ActivityIndicator size="small" color={color.muted} />
            </View>
          ) : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: Math.max(insets.bottom, 10) }]}>
          <View style={s.field}>
            <TextInput
              style={s.input}
              value={draft}
              onChangeText={setDraft}
              placeholder={BUDDY.placeholder()}
              placeholderTextColor={color.neutral400}
              onSubmitEditing={submit}
              returnKeyType="send"
            />
            <Pressable accessibilityRole="button" onPress={submit}>
              <IconMic />
            </Pressable>
          </View>
        </View>

        <GetStarted
          open={sheet}
          onCreate={toCreate}
          onKeep={() => setSheet(false)}
          bottomInset={insets.bottom}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

/**
 * Окно O.03. Одно на оба входа — и на кнопку, и на распознанный триггер, — потому что вопрос в
 * обоих случаях один и тот же: создавать интент или продолжать разговор.
 */
export function GetStarted({
  open, onCreate, onKeep, bottomInset = 0,
}: {
  open: boolean;
  onCreate: () => void;
  onKeep: () => void;
  bottomInset?: number;
}) {
  return (
    <Modal visible={open} transparent animationType="slide" onRequestClose={onKeep}>
      <Pressable style={sh.scrim} onPress={onKeep} accessibilityLabel={SHEET.close()} />
      <View style={[sh.sheet, { paddingBottom: Math.max(bottomInset, 18) }]}>
        <View style={sh.grip} />
        <View style={sh.headRow}>
          <Text style={sh.title}>{SHEET.title()}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel={SHEET.close()} onPress={onKeep} hitSlop={10}>
            <Text style={sh.x}>✕</Text>
          </Pressable>
        </View>
        <Pressable accessibilityRole="button" style={[sh.btn, sh.btnPri]} onPress={onCreate}>
          <Text style={sh.btnPriText}>{SHEET.create()}</Text>
        </Pressable>
        <Pressable accessibilityRole="button" style={[sh.btn, sh.btnSec]} onPress={onKeep}>
          <Text style={sh.btnSecText}>{SHEET.keep()}</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

// ============================================================ вид
// Всё ниже — оформление UX-каркаса: цвета и размеры берутся из токенов темы, своих значений тут
// нет. При натягивании UI меняется этот блок, логика выше остаётся.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  createBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, height: 40, paddingHorizontal: 16,
    borderRadius: rad.full, backgroundColor: color.card, borderWidth: 1, borderColor: color.border,
  },
  createPlus: { fontSize: 18, color: color.fg, marginTop: -2 },
  createText: { ...type.labelMedium, color: color.fg } as any,

  thread: { paddingHorizontal: 20, paddingTop: space.md, paddingBottom: space.lg, gap: 4 },
  bub: { maxWidth: '86%', paddingVertical: 12, paddingHorizontal: 14, marginTop: space.sm },
  bubBot: { alignSelf: 'flex-start', backgroundColor: color.neutral100, borderRadius: 16 },
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary, borderRadius: 16 },
  bubText: { ...type.body, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,

  dock: { paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.bg },
  field: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
});

const sh = StyleSheet.create({
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#0006' },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: color.card, borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 20, paddingTop: 10, gap: space.md,
  },
  grip: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: color.neutral300 },
  headRow: { flexDirection: 'row', alignItems: 'center', marginTop: space.sm },
  title: { flex: 1, fontSize: 20, fontWeight: '700', color: color.fg },
  x: { fontSize: 20, color: color.muted },
  btn: { height: 54, borderRadius: rad.full, alignItems: 'center', justifyContent: 'center' },
  btnPri: { backgroundColor: color.primary },
  btnPriText: { ...type.button, color: color.onPrimary } as any,
  btnSec: { backgroundColor: color.neutral100 },
  btnSecText: { ...type.button, color: color.fg } as any,
});
