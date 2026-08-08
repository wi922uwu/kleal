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
  /**
   * ВСЕ версии собранного интента, по порядку. Нужны не для истории ради истории: разговор
   * уточняющий, и после каждого ответа сводка пересобирается — человек должен видеть, ЧТО именно
   * от его слов изменилось, а не гадать, стало лучше или хуже. Последняя версия и есть `ready`.
   */
  const [versions, setVersions] = useState<{ topics: string[]; title: string }[]>([]);
  /** Закреплённая сводка развёрнута. Свёрнута по умолчанию — она не должна съедать половину чата. */
  const [sumOpen, setSumOpen] = useState(false);
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
        const v = { topics, title: titleOf(r, text) };
        setReady(v);
        // Пишем в историю только НАСТОЯЩЕЕ изменение: тот же самый интент второй раз подряд —
        // это не правка, и строка «что изменилось» о нём молчит.
        setVersions((all) => {
          const last = all[all.length - 1];
          const same = last && last.title === v.title && last.topics.join('|') === v.topics.join('|');
          return same ? all : [...all, v];
        });
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

        {ready ? (
          <PinnedSummary
            cur={ready}
            versions={versions}
            open={sumOpen}
            onToggle={() => setSumOpen((o) => !o)}
            onCreate={next}
          />
        ) : null}

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

          {/*
            Круг замыкается там же, где начался: сводка по затее и кнопка «Создать интент» — та
            самая, что была в окне Бадди. Кнопки «Дальше» здесь нет намеренно: она обещала
            следующий шаг, а человек уже ответил на всё, что у него спрашивали. Уточнил ещё раз —
            сводка пересобирается, и кнопка снова та же.
          */}
          {/* Сводка больше не живёт в ленте — она закреплена под шапкой (см. PinnedSummary):
              разговор уточняющий, и карточка уезжала вверх ровно тогда, когда её и надо смотреть. */}
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


/**
 * Закреплённая сводка интента — полоса под шапкой, а не карточка в ленте.
 *
 * Разговор здесь уточняющий: человек отвечает, сводка пересобирается, отвечает снова. Пока она
 * стояла в ленте, её уносило вверх ровно тогда, когда на неё и надо смотреть, а «Создать интент»
 * приходилось искать прокруткой.
 *
 * Свёрнута по умолчанию: одна строка с темой. Развёрнутая показывает ключи поиска и — главное —
 * ЧТО ИЗМЕНИЛОСЬ от последнего ответа. Без этого уточнение вслепую: человек говорит «не бег, а
 * плавание» и не видит, услышали его или нет.
 */
function PinnedSummary({
  cur, versions, open, onToggle, onCreate,
}: {
  cur: { topics: string[]; title: string };
  versions: { topics: string[]; title: string }[];
  open: boolean;
  onToggle: () => void;
  onCreate: () => void;
}) {
  const prev = versions.length > 1 ? versions[versions.length - 2] : null;
  const added = prev ? cur.topics.filter((t) => !prev.topics.includes(t)) : [];
  const gone = prev ? prev.topics.filter((t) => !cur.topics.includes(t)) : [];
  const renamed = prev && prev.title !== cur.title ? prev.title : '';
  const changed = added.length || gone.length || renamed;

  return (
    <View style={s.pin}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} style={s.pinHead} onPress={onToggle}>
        <View style={{ flex: 1 }}>
          <Text style={s.pinLabel}>{CREATE.summaryLabel()}</Text>
          <Text style={s.pinTitle} numberOfLines={1}>{cur.title}</Text>
        </View>
        {/* Точка у свёрнутой строки — единственный намёк, что после ответа что-то поменялось. */}
        {!open && changed ? <View style={s.pinDot} /> : null}
        <Text style={s.pinChev}>{open ? '⌃' : '⌄'}</Text>
      </Pressable>

      {open ? (
        <>
          {cur.topics.length ? (
            <View style={s.sumChips}>
              {cur.topics.map((t) => (
                <View key={t} style={[s.sumChip, added.includes(t) && s.sumChipNew]}>
                  <Text style={[s.sumChipText, added.includes(t) && { color: color.onPrimary }]}>{t}</Text>
                </View>
              ))}
            </View>
          ) : null}

          {changed ? (
            <View style={s.diff}>
              <Text style={s.diffLabel}>{CREATE.changed()}</Text>
              {renamed ? <Text style={s.diffLine}>{CREATE.wasCalled(renamed)}</Text> : null}
              {added.length ? <Text style={s.diffLine}>{CREATE.added(added.join(', '))}</Text> : null}
              {gone.length ? <Text style={s.diffLine}>{CREATE.dropped(gone.join(', '))}</Text> : null}
            </View>
          ) : (
            <Text style={s.readyNote}>{CREATE.readyNote()}</Text>
          )}

          <Pressable accessibilityRole="button" style={s.readyBtn} onPress={onCreate}>
            <Text style={s.readyBtnText}>{CREATE.ready()}</Text>
          </Pressable>
        </>
      ) : null}
    </View>
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

  // Закреплённая сводка: живёт под шапкой, поэтому со своими полями и тенью, а не в ленте.
  pin: {
    marginHorizontal: 20, marginBottom: space.sm, padding: space.md, gap: space.sm,
    borderRadius: rad.lg, backgroundColor: color.card,
    shadowColor: '#0F172A', shadowOpacity: 0.06, shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 }, elevation: 2,
  },
  pinHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  pinLabel: { ...type.caption, color: color.primary, fontWeight: '700' } as any,
  pinTitle: { ...type.title, color: color.fg } as any,
  pinDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.primary },
  pinChev: { fontSize: 18, color: color.muted },
  diff: { backgroundColor: color.infoBg, borderRadius: rad.md, padding: space.md, gap: 3 },
  diffLabel: { ...type.caption, color: color.primary, fontWeight: '700' } as any,
  diffLine: { ...type.bodySmall, color: color.infoText } as any,
  sumChipNew: { backgroundColor: color.primary },

  readyBlock: { marginTop: space.lg, gap: space.sm },
  /** Сводка по затее перед созданием — та же карточка, что человек увидит на экране интента. */
  sumCard: { backgroundColor: color.card, borderRadius: rad.lg, padding: space.md, gap: 8 },
  sumLabel: { ...type.caption, color: color.primary, fontWeight: '700' } as any,
  sumTitle: { fontSize: 17, fontWeight: '700', color: color.fg } as any,
  sumChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  sumChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: rad.full, backgroundColor: color.neutral100 },
  sumChipText: { ...type.caption, color: color.fg } as any,
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
