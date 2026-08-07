/**
 * Создание интента — кадр O.04.
 *
 * UX-КАРКАС: вид натянется поверх. Оформление — одним блоком внизу файла, на токенах темы; копия —
 * в src/buddy.ts. Логика выше не зависит ни от одного размера.
 *
 * Отдельный разговор, не тот, что с Бадди. Начинается с вариантов, собранных ПО ПРОФИЛЮ
 * (/api/buddy/intent-suggest): человеку, который открыл пустой экран, проще выбрать, чем
 * придумывать. «Ещё варианты» перевыбирает их заново.
 *
 * Дальше агент уточняет ТОЛЬКО тему — два-три вопроса про суть затеи. Про время, место, пол и
 * размер компании он не спрашивает намеренно: это ставится руками на следующем экране, и
 * переспрашивать значило бы заставить отвечать дважды. Правило живёт в системном промпте сервера
 * (INTENT_BUILD_PROMPT), а не здесь, — иначе клиент и сервер разошлись бы.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { IconChevronLeft, IconMic, IconSpark } from '../src/components/icons';
import { useLang, getLang, T , replyLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { buddy as buddyApi } from '../src/api';
import { CREATE, topicsOf, titleOf, unpackHistory, Turn } from '../src/buddy';
import { color, radius as rad, space, type } from '../src/theme';

type Msg = { who: 'bot' | 'me'; text: string; at: string };

const now = () =>
  new Date().toLocaleTimeString(getLang() === 'ru' ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: getLang() !== 'ru',
  });

export default function Create() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const scroller = useRef<ScrollView>(null);

  /**
   * Что пришло из разговора с Бадди: тема и сам разговор.
   *
   * История не показывается в ленте — экран начинается с того, ради чего сюда пришли, — но уходит
   * СЕРВЕРУ. Иначе фраза вроде «поговорить с кем-то об этом» приезжает без «этого», и построитель
   * переспрашивает то, что человек уже рассказал в предыдущем чате.
   */
  const params = useLocalSearchParams<{ seed?: string; history?: string }>();
  const seed = String(params.seed || '').trim();
  const history = unpackHistory(params.history);

  const [thread, setThread] = useState<Msg[]>([]);
  const [turns, setTurns] = useState<Turn[]>(history);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loadingSug, setLoadingSug] = useState(!seed);
  const [hints, setHints] = useState<string[]>([]);
  /**
   * Что повторить, если запрос сорвался. Раньше разговор на этом просто заканчивался: агент
   * говорил «связь пропала», а дальше человеку оставалось только писать всё заново — и он читал
   * это как «флоу завис». Теперь сорвавшаяся реплика ждёт одной кнопки.
   */
  const [retry, setRetry] = useState<{ text: string; hist: Turn[] } | null>(null);
  /**
   * Тема собрана. Хранится ДВУМЯ полями: ключи для поиска и подпись для человека — см. topicsOf
   * и titleOf. Одной строкой это уже было, и поиск уходил с заголовком вместо ключей.
   */
  const [ready, setReady] = useState<{ topics: string[]; title: string } | null>(null);
  const started = useRef(false);
  const rolls = useRef(0);

  const say = useCallback((who: 'bot' | 'me', text: string) => {
    setThread((t) => [...t, { who, text, at: now() }]);
  }, []);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [thread.length, typing, suggestions.length]);

  const profile = () => ({
    name: st.profile.name, age: st.profile.age, city: st.profile.city,
    interests: st.profile.interests?.explicit || [],
    languages: st.profile.languages || {},
  });

  /** Варианты по профилю. Пустой ответ оставляет ряд пустым — выдумывать за модель нечего. */
  const loadSuggestions = useCallback(async () => {
    setLoadingSug(true);
    try {
      rolls.current += 1;
      const r: any = await buddyApi.intentSuggest(profile(), replyLang(), String(rolls.current));
      setSuggestions(Array.isArray(r?.suggestions) ? r.suggestions.map(String) : []);
    } catch {
      setSuggestions([]);
    } finally {
      setLoadingSug(false);
    }
  }, [st.profile]);

  const ask = useCallback(async (text: string, hist: Turn[]) => {
    const next: Turn[] = [...hist, { role: 'user', content: text }];
    setTurns(next);
    setTyping(true);
    setHints([]);
    setRetry(null);
    try {
      const r: any = await buddyApi.intentBuild(next, profile());
      setTyping(false);
      const reply = String(r?.reply || '');
      if (reply) {
        say('bot', reply);
        setTurns([...next, { role: 'assistant', content: reply }]);
      }
      setHints(Array.isArray(r?.hints) ? r.hints.map(String).slice(0, 3) : []);
      if (r?.ready) {
        const topics = topicsOf(r);
        // Ключей нет — построитель ничего не извлёк. Отправлять в поиск сказанное человеком
        // как «тему» нельзя: русская фраза не совпадёт ни с кем. Пусть уточнит.
        setReady({ topics, title: titleOf(r, text) });
      }
    } catch {
      setTyping(false);
      // Реплику человека НЕ теряем: её вернёт кнопка «Попробовать снова», и разговор продолжится
      // с того же места, а не с чистого листа.
      setTurns(hist);
      setRetry({ text, hist });
      say('bot', T('Связь пропала — я не дослушал. Попробуем ещё раз?',
                   'I lost the connection mid-thought. Shall we try again?'));
    }
  }, [say, st.profile]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (seed) {
      say('me', seed);
      ask(seed, history);
    } else {
      loadSuggestions();
    }
  }, []);

  const pick = (text: string) => {
    setSuggestions([]);
    say('me', text);
    ask(text, turns);
  };

  const submit = () => {
    const t = draft.trim();
    if (!t || typing) return;
    setDraft('');
    pick(t);
  };

  /**
   * Тема готова — дальше вручную. Мастер открывается сразу на формате, а не на «что хочешь
   * сделать?»: на этот вопрос человек только что ответил, и спрашивать снова было бы издевательством.
   */
  const next = () => router.push({
    pathname: '/intent',
    params: {
      // Ключи едут списком через запятую — их читает поиск; заголовок отдельно, он только для глаз.
      topics: (ready?.topics || []).join(','),
      title: ready?.title || '',
    },
  });

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" style={s.back} onPress={() => router.back()}>
            <IconChevronLeft />
          </Pressable>
          <View style={{ flex: 1 }} />
          <Pressable accessibilityRole="button" style={s.allBtn} onPress={() => router.replace('/home')}>
            <Text style={s.allText}>{CREATE.title()}</Text>
          </Pressable>
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
          {/* Заголовок показывается, пока разговор не начался: потом его место занимает лента. */}
          {thread.length === 0 ? (
            <>
              <View style={s.askRow}>
                <View style={s.dot} />
                <Text style={s.ask}>{CREATE.ask()}</Text>
              </View>
              <Text style={s.sub}>{CREATE.sub()}</Text>
            </>
          ) : null}

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

          {/* Варианты по профилю — только на пустом экране, до первого ответа. */}
          {thread.length === 0 ? (
            <View style={s.sugBlock}>
              <View style={s.sugHead}>
                <Text style={s.sugHeadText}>{CREATE.suggestions()}</Text>
              </View>
              <Text style={s.choose}>{CREATE.choose()}</Text>
              {loadingSug ? (
                <ActivityIndicator style={{ marginVertical: space.lg }} color={color.primary} />
              ) : suggestions.length ? (
                <View style={s.sugList}>
                  {suggestions.map((sg) => (
                    <Pressable key={sg} accessibilityRole="button" style={s.sug} onPress={() => pick(sg)}>
                      <Text style={s.sugText}>{sg}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : (
                <Text style={s.empty}>{CREATE.empty()}</Text>
              )}
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ busy: loadingSug }}
                style={s.regen}
                onPress={loadingSug ? undefined : loadSuggestions}
              >
                <IconSpark size={18} />
                <Text style={s.regenText}>{CREATE.regenerate()}</Text>
              </Pressable>
            </View>
          ) : null}

          {/* Сорвавшийся запрос — не конец разговора: одна кнопка возвращает последнюю реплику. */}
          {retry ? (
            <View style={s.hints}>
              <Pressable
                accessibilityRole="button"
                style={s.hint}
                onPress={() => { const r = retry; setRetry(null); ask(r.text, r.hist); }}
              >
                <Text style={s.hintText}>{T('Попробовать снова', 'Try again')}</Text>
              </Pressable>
            </View>
          ) : null}

          {/* Подсказки построителя — это ответы на его же вопрос, поэтому живут под ним. */}
          {hints.length && !ready ? (
            <View style={s.hints}>
              {hints.map((h) => (
                <Pressable key={h} accessibilityRole="button" style={s.hint} onPress={() => pick(h)}>
                  <Text style={s.hintText}>{h}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}

          {ready ? (
            <View style={s.readyBlock}>
              <Text style={s.readyNote}>{CREATE.readyNote()}</Text>
              <Pressable accessibilityRole="button" style={s.readyBtn} onPress={next}>
                <Text style={s.readyBtnText}>{CREATE.ready()}</Text>
              </Pressable>
            </View>
          ) : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: Math.max(insets.bottom, 10) }]}>
          <View style={s.field}>
            <TextInput
              style={s.input}
              value={draft}
              onChangeText={setDraft}
              placeholder={T('Сообщение…', 'Message…')}
              placeholderTextColor={color.neutral400}
              onSubmitEditing={submit}
              returnKeyType="send"
            />
            <Pressable accessibilityRole="button" onPress={submit}>
              <IconMic />
            </Pressable>
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

// ============================================================ вид
// Оформление UX-каркаса. Все значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  allBtn: { height: 40, paddingHorizontal: 16, borderRadius: rad.full, backgroundColor: color.primary, justifyContent: 'center' },
  allText: { ...type.labelMedium, color: color.onPrimary } as any,

  body: { paddingHorizontal: 20, paddingBottom: space.lg, gap: 4 },
  askRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: space.sm },
  dot: { width: 26, height: 26, borderRadius: 13, backgroundColor: color.primary },
  ask: { flex: 1, fontSize: 21, fontWeight: '700', color: color.fg },
  sub: { ...type.bodySmall, color: color.muted, marginTop: 6 } as any,

  bub: { maxWidth: '86%', paddingVertical: 12, paddingHorizontal: 14, marginTop: space.sm },
  bubBot: { alignSelf: 'flex-start', backgroundColor: color.neutral100, borderRadius: 16 },
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary, borderRadius: 16 },
  bubText: { ...type.body, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,

  sugBlock: { marginTop: space.lg, gap: space.sm },
  sugHead: { height: 44, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  sugHeadText: { ...type.button, color: color.onPrimary } as any,
  choose: { ...type.caption, color: color.muted, marginTop: 4 } as any,
  sugList: { borderRadius: rad.lg, backgroundColor: color.card, borderWidth: 1, borderColor: color.border, overflow: 'hidden' },
  sug: { minHeight: 52, paddingHorizontal: 16, paddingVertical: 12, justifyContent: 'center', borderTopWidth: 1, borderTopColor: color.neutral100 },
  sugText: { ...type.body, color: color.fg, textAlign: 'center' } as any,
  empty: { ...type.bodySmall, color: color.muted } as any,
  regen: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    height: 46, borderRadius: rad.full, backgroundColor: color.primary, marginTop: space.sm,
  },
  regenText: { ...type.button, color: color.onPrimary } as any,

  hints: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  hint: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  hintText: { ...type.labelMedium, color: color.fg } as any,

  readyBlock: { marginTop: space.lg, gap: space.sm },
  readyNote: { ...type.bodySmall, color: color.muted } as any,
  readyBtn: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  readyBtnText: { ...type.button, color: color.onPrimary } as any,

  dock: { paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.bg },
  field: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
});
