/**
 * Создание интента, шаг «что делаем» — кадр GR.04 борда «0 · Create the intent» (Figma 6864:119674).
 *
 * Вид из src/components/CreateFlow.tsx: шапка «Creating intent» с процентами (здесь 10%), вопрос
 * пузырём Kleal, варианты строками с галочкой, Regenerate стеклом, поле ввода снизу. Дальше мастер
 * идёт на app/intent.tsx той же шапкой — на борде это один экран, и переход сделан проявлением,
 * а не сдвигом (app/_layout.tsx).
 *
 * ПОРЯДОК ШАГА: Kleal спрашивает «What do you want to do?» (GR.04) и предлагает варианты по профилю,
 * человек выбирает или пишет своё — это уходит построителю, и он отвечает в ленте как есть.
 *
 * ЗАТЕЯ СОБРАНА — ПОД ШАПКОЙ ЗАКРЕПЛЁННАЯ КАРТОЧКА С КНОПКОЙ (PinnedSummary), а не автопереход.
 * Решение владельца 04.10.2026: «если Бади создаёт интент, то сверху появляется мини-окошко и кнопка
 * „Нажми“, как это было раньше». В волне 1 борда (03.10) здесь стояло «Great — … it is!» и мастер
 * уезжал сам через 0,9 с: человек не успевал увидеть, что собрано, и не мог уточнить. Разговор здесь
 * уточняющий — карточка пересобирается на каждый ответ и показывает, что изменилось.
 *
 * ПРИШЁЛ ИЗ ЧАТА С KLEAL (`seed`, попап «Создать») — фраза идёт построителю видимой репликой вместе
 * с хвостом разговора, как раньше: ровно этот путь меряет мерка нейросети (чат → попап → сборщик →
 * карточка). Вариантов по профилю тогда нет — человек уже сказал, чего хочет.
 *
 * Построитель уточняет ТОЛЬКО тему. Про время, место, пол и размер компании он не спрашивает: это
 * ставится на следующих шагах (правило живёт в промпте сервера, INTENT_BUILD_PROMPT).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { hOk, hTick } from '../src/haptics';
import { IconWand, IconChevronDown, IconChevronUp } from '../src/components/icons';
import { interestLabel } from '../src/interest-label';
import Animated, { Easing as REasing, useAnimatedStyle, useSharedValue, withSequence, withTiming } from 'react-native-reanimated';
import { useLang, T, replyLang, dateLocale, use12h } from '../src/i18n';
import { useOnb } from '../src/state';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { buddy as buddyApi } from '../src/api';
import { BUDDY, CREATE, topicsOf, titleOf, datingOf, unpackHistory, looksLikeIntent, needsSignIn, Turn } from '../src/buddy';
import { color, font } from '../src/theme';
import { GlassSurface, riseIn } from '../src/components/LiquidGlass';
import { Thinking } from '../src/components/Thinking';
import { makeReveal } from '../src/reveal';
import { GlassPill } from '../src/components/Glass';
import {
  CreatingHeader, StepAsk, AgentLine, MyLine, Caption, ChoiceRow, GlassChip, CreateComposer,
} from '../src/components/CreateFlow';

type Msg = { who: 'bot' | 'me'; text: string; at: string ;
  /** Текст ещё пишется — под ним мигает курсор. */ live?: boolean };

/** Затея, собранная построителем: ключи для поиска и подпись для человека — см. topicsOf/titleOf. */
type Ready = { topics: string[]; title: string; dating?: boolean };

const now = () =>
  new Date().toLocaleTimeString(dateLocale(), {
    hour: '2-digit', minute: '2-digit', hour12: use12h(),
  });

export default function Create() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх дока — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  /**
   * Что пришло из разговора с Kleal: фраза и сам разговор.
   *
   * История не показывается в ленте — экран начинается с вопроса шага, — но уходит СЕРВЕРУ. Иначе
   * фраза вроде «поговорить с кем-то об этом» приезжает без «этого», и построитель переспрашивает
   * то, что человек уже рассказал в предыдущем чате.
   */
  const params = useLocalSearchParams<{ seed?: string; history?: string }>();
  const seed = String(params.seed || '').trim();
  const history = unpackHistory(params.history);

  const [thread, setThread] = useState<Msg[]>([]);
  const [turns, setTurns] = useState<Turn[]>(history);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loadingSug, setLoadingSug] = useState(true);
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
  const [ready, setReady] = useState<Ready | null>(null);
  /**
   * ВСЕ версии собранного интента, по порядку. Разговор уточняющий, и после каждого ответа сводка
   * пересобирается — человек должен видеть, ЧТО именно от его слов изменилось. Последняя — `ready`.
   */
  const [versions, setVersions] = useState<Ready[]>([]);
  /** Закреплённая сводка развёрнута. Свёрнута по умолчанию — она не должна съедать половину чата. */
  const [sumOpen, setSumOpen] = useState(false);
  /**
   * ПЕРВОЕ ПОЯВЛЕНИЕ СВОДКИ РАСКРЫВАЕТ ЕЁ САМО: это единственный кадр, ради которого шёл весь
   * разговор. Дальше человек сворачивает её сам, и его выбор больше не трогаем.
   */
  const firstShown = useRef(false);
  useEffect(() => {
    if (!ready || firstShown.current) return;
    firstShown.current = true;
    setSumOpen(true);
  }, [ready]);
  /** Сервер ответил 401 — под репликой кнопка входа (см. BUDDY.signIn). */
  const [signIn, setSignIn] = useState(false);
  /** Выбранный вариант — у него галочка. */
  const [picked, setPicked] = useState('');
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

  /**
   * Что сделать с готовым ответом построителя.
   *
   * `shown` — показался ли текст потоком: от него зависит, печатать ли реплику ещё раз.
   *
   * ОТВЕТ ПОСТРОИТЕЛЯ ПОКАЗЫВАЕТСЯ КАК ЕСТЬ, и при собранной затее тоже: в нём похвала затее и
   * «Понял — …», которые меряет нейросеть. Подменять его своей строкой значит прятать её работу.
   */
  const settle = useCallback((r: any, reply: string, text: string, next: Turn[], shown: boolean) => {
    if (r?.refused || r?.valid === false) {
      setReady(null);
      setSumOpen(false);
    }
    if (reply) {
      if (!shown) say('bot', reply);
      setTurns([...next, { role: 'assistant', content: reply }]);
    }
    setHints(Array.isArray(r?.hints) ? r.hints.map(String).slice(0, 3) : []);
    if (r?.ready && looksLikeIntent(r)) {
      const topics = topicsOf(r);
      // Свидание — тип затеи: без него поиск идёт как обычный, мимо ворот `datingOk`.
      const v: Ready = { topics, title: titleOf(r, text), dating: datingOf(r) };
      setReady(v);
      // В историю — только НАСТОЯЩЕЕ изменение: та же затея второй раз подряд — не правка.
      setVersions((all) => {
        const last = all[all.length - 1];
        const same = last && last.title === v.title && last.topics.join('|') === v.topics.join('|')
          && !!last.dating === !!v.dating;
        return same ? all : [...all, v];
      });
    }
  }, [say]);

  /**
   * ОТВЕТ ПОЯВЛЯЕТСЯ ПО МЕРЕ НАПИСАНИЯ — то же, что на экране Kleal.
   *
   * Измерено на живом сервере: обычный путь 5,2 с. Это дольше разговора с Kleal, потому что
   * построитель не только отвечает, но и разбирает сказанное в тему и заголовок. Генерацию не
   * ускорить, но ждать её конца незачем: первые слова приходят почти сразу.
   */
  const ask = useCallback((text: string, hist: Turn[]) => {
    const next: Turn[] = [...hist, { role: 'user', content: text }];
    setTurns(next);
    setTyping(true);
    setHints([]);
    setRetry(null);

    let acc = '';
    let opened = false;
    // Ровный показ — тот же, что на экране Kleal. См. src/reveal.ts.
    /*
      ФЛАГ «РЕПЛИКА ОТКРЫТА» СТАВИТСЯ СРАЗУ, А НЕ ВНУТРИ setThread. Функция обновления состояния
      выполняется позже, на отрисовке, — и `done`, пришедший в тот же такт, видел `opened === false`
      и печатал реплику второй раз (два одинаковых пузыря на быстром ответе, стенд 04.10).
    */
    const rev = makeReveal((shown: string) => {
      if (!opened) {
        opened = true;
        setThread((prev) => [...prev, { who: 'bot', text: shown, at: now(), live: true }]);
        return;
      }
      setThread((prev) => {
        const out = prev.slice();
        out[out.length - 1] = { ...out[out.length - 1], text: shown, live: true };
        return out;
      });
    });
    const grow = (t: string) => { acc += t; rev.push(t); };

    buddyApi.intentBuildStream(next, profile(), {
      delta: grow,
      done: (r: any) => {
        setTyping(false);
        const reply = String(r?.reply || acc);
        /*
          МАШИНКА ОСТАНАВЛИВАЕТСЯ ВСЕГДА, А РЕПЛИКА ВСТАЁТ ЦЕЛИКОМ. Было две гонки (видны на быстром
          ответе, 04.10): (1) конверт пришёл раньше первого кадра печати — реплику печатал `settle`,
          а через такт машинка открывала вторую такую же; (2) конверт пришёл посреди печати —
          машинку останавливали и оставляли показанную половину. Теперь: печать гасится, а в ленте
          оказывается итоговый текст сервера (он же чищеный).
        */
        rev.stop();
        if (opened) {
          setThread((prev) => {
            const out = prev.slice();
            const cur = out[out.length - 1];
            out[out.length - 1] = { ...cur, text: reply || cur.text, live: false };
            return out;
          });
        }
        settle(r, reply, text, next, opened);
      },
      error: async (why: string) => {
        // Как и в чате Kleal: поток — способ доставки, а не ответ. Сначала вторая попытка обычным
        // запросом, и только если и она не прошла — «попробуем ещё раз».
        if (opened) { rev.stop(); setThread((prev) => prev.slice(0, -1)); }
        let locked = needsSignIn(why);
        if (!locked) {
          try {
            const r: any = await buddyApi.intentBuild(next, profile());
            setTyping(false);
            const reply = String(r?.reply || '');
            if (reply) { settle(r, reply, text, next, false); return; }
          } catch (e) {
            /* и обычный запрос не прошёл — значит связи правда нет, или нет входа */
            locked = needsSignIn(e);
          }
        }
        setTyping(false);
        setTurns(hist);
        // Нет входа — «попробуем ещё раз» не поможет: реплика человека ждёт, а под ней кнопка входа.
        if (locked) { setRetry({ text, hist }); setSignIn(true); say('bot', BUDDY.signIn()); return; }
        setRetry({ text, hist });
        say('bot', T('Связь пропала — я не дослушал. Попробуем ещё раз?',
                     'I lost the connection mid-thought. Shall we try again?', 'Perdí la conexión a mitad de pensamiento. ¿Lo intentamos de nuevo?'));
      },
    });
  }, [say, settle, st.profile]);

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

  /** Варианты по профилю, всего три (кадр GR.04). */
  const options = suggestions.slice(0, 3);

  const pick = (text: string) => {
    if (typing) return;
    setPicked(text);
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
  const next = () => router.navigate({
    pathname: '/intent',
    params: {
      // Ключи едут списком через запятую — их читает поиск; заголовок отдельно, он только для глаз.
      topics: (ready?.topics || []).join(','),
      title: ready?.title || '',
      // Тип едет отдельно от ключей: свидание — не тема, а контур поиска со своими воротами.
      ...(ready?.dating ? { type: 'dating' } : {}),
    },
  });


  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top }]}>
        {/*
          У «НАЗАД» ОБЯЗАН БЫТЬ ЗАПАСНОЙ ПУТЬ. Голый `router.back()` молча ничего не делает, когда
          возвращаться некуда (экран открыт по ссылке или первым после холодного старта) — поэтому
          `replace` на корень: он подменяет ТЕКУЩИЙ экран, а не кладёт вторую главную поверх первой.
        */}
        <CreatingHeader pct={10} onBack={() => (router.canGoBack() ? router.back() : router.replace('/home'))} />

        {/* Затея собрана — карточка закреплена под шапкой, а не уезжает с лентой (см. PinnedSummary). */}
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
          <StepAsk text={CREATE.ask()} caption={CREATE.sub()} />

          {/* Варианты по профилю — когда пришли без фразы. Пришли из чата — человек уже сказал своё. */}
          {!seed ? (
            <>
              <Caption text={CREATE.choose()} />
              {loadingSug && !options.length ? (
                <ActivityIndicator style={{ marginVertical: 12 }} color={color.primary} />
              ) : options.length ? (
                <View style={s.list}>
                  {options.map((o) => (
                    <ChoiceRow key={o} label={o} on={picked === o} disabled={typing} onPress={() => pick(o)} />
                  ))}
                </View>
              ) : (
                <Caption text={CREATE.empty()} />
              )}
              <GlassPill
                tone="light"
                small
                icon={<IconWand size={16} c={color.fg} />}
                label={CREATE.regenerate()}
                busy={loadingSug}
                onPress={loadSuggestions}
                style={s.regen}
              />
            </>
          ) : null}

          {/* Человек говорит пузырём, Kleal отвечает пузырём — как на кадре GR.04. */}
          {thread.map((m, i) => (
            m.who === 'me'
              ? <MyLine key={i} text={m.text} at={m.at} />
              : <AgentLine key={i} text={m.text} at={m.live ? undefined : m.at} markdown />
          ))}

          {/* Ожидание — не вертушка, а живая строка: см. src/components/Thinking.tsx. */}
          {typing && thread.length ? <Thinking /> : null}

          {signIn ? (
            <View style={{ alignItems: 'flex-start' }}>
              <GlassPill tone="dark" small style={s.regen} label={BUDDY.signInBtn()} onPress={() => router.navigate('/auth')} />
            </View>
          ) : null}

          {/* Сорвавшийся запрос — не конец разговора: одна кнопка возвращает последнюю реплику. */}
          {retry && !signIn ? (
            <View style={s.hints}>
              <GlassChip
                label={T('Попробовать снова', 'Try again', 'Reintentar')}
                on={false}
                onPress={() => { const r = retry; setRetry(null); ask(r.text, r.hist); }}
              />
            </View>
          ) : null}

          {/* Подсказки построителя — это ответы на его же вопрос, поэтому живут под ним. */}
          {hints.length && !ready ? (
            <View style={s.hints}>
              {hints.map((h) => (
                <GlassChip key={h} label={h} on={false} onPress={() => pick(h)} />
              ))}
            </View>
          ) : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          <CreateComposer
            value={draft}
            onChange={setDraft}
            onSubmit={submit}
            placeholder={T('Сообщение…', 'Message…', 'Mensaje…')}
            editable={!typing}
          />
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

/**
 * Закреплённая сводка затеи — «мини-окошко» над разговором с кнопкой «Нажми» (CREATE.ready).
 *
 * Разговор здесь уточняющий: человек отвечает, сводка пересобирается, отвечает снова. Пока она
 * стояла в ленте, её уносило вверх ровно тогда, когда на неё и надо смотреть, а кнопку приходилось
 * искать прокруткой. Свёрнута — одна строка с названием; развёрнута — темы поиска и, главное, ЧТО
 * ИЗМЕНИЛОСЬ от последнего ответа: «не бег, а плавание» без обратной связи — уточнение вслепую.
 *
 * Вид — стекло нового борда (как пузыри и строки мастера). Появление и пересборка — сдвигом и
 * масштабом, без прозрачности: полупрозрачный предок гасит системное стекло целиком.
 */
function PinnedSummary({
  cur, versions, open, onToggle, onCreate,
}: {
  cur: Ready;
  versions: Ready[];
  open: boolean;
  onToggle: () => void;
  onCreate: () => void;
}) {
  /*
    СВОДКА ОБЪЯВЛЯЕТ О СЕБЕ. Появилась впервые — съезжает сверху с системным «получилось» (итог
    разговора). Пересобралась после ответа — короткий вдох и щелчок: полное появление на каждом
    уточнении читалось бы как «сводка пропала и пришла новая».
  */
  const pulse = useSharedValue(1);
  const seen = useRef(versions.length);
  useEffect(() => { hOk(); }, []);
  useEffect(() => {
    if (versions.length === seen.current) return;
    seen.current = versions.length;
    hTick();
    pulse.value = withSequence(
      withTiming(1.015, { duration: 120, easing: REasing.out(REasing.quad) }),
      withTiming(1, { duration: 220, easing: REasing.out(REasing.cubic) }),
    );
  }, [versions.length]);
  const pulseStyle = useAnimatedStyle(() => ({ transform: [{ scale: pulse.value }] }));

  const prev = versions.length > 1 ? versions[versions.length - 2] : null;
  const added = prev ? cur.topics.filter((x) => !prev.topics.includes(x)) : [];
  const gone = prev ? prev.topics.filter((x) => !cur.topics.includes(x)) : [];
  const renamed = prev && prev.title !== cur.title ? prev.title : '';
  const changed = !!(added.length || gone.length || renamed);

  return (
    <Animated.View entering={riseIn(0, 8)} style={[s.pinWrap, pulseStyle]}>
      <GlassSurface tone="light" radius={20} style={s.pin}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: open }}
          style={s.pinHead}
          onPress={onToggle}
          hitSlop={6}
        >
          <View style={{ flex: 1 }}>
            <Text style={s.pinLabel}>{CREATE.summaryLabel()}</Text>
            <Text style={s.pinTitle} numberOfLines={open ? 2 : 1}>{cur.title}</Text>
          </View>
          {/* Точка у свёрнутой строки — единственный намёк, что после ответа что-то поменялось. */}
          {!open && changed ? <View style={s.pinDot} /> : null}
          {open ? <IconChevronUp size={20} c={color.fg} /> : <IconChevronDown size={20} c={color.fg} />}
        </Pressable>

        {open ? (
          <View style={s.pinBody}>
            {cur.topics.length ? (
              <View style={s.pinChips}>
                {cur.topics.map((x) => (
                  <View key={x} style={[s.pinChip, added.includes(x) && s.pinChipNew]}>
                    <Text style={[s.pinChipText, added.includes(x) && { color: color.onPrimary }]}>{interestLabel(x)}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {changed ? (
              <View style={s.diff}>
                <Text style={s.diffLabel}>{CREATE.changed()}</Text>
                {renamed ? <Text style={s.diffLine}>{CREATE.wasCalled(renamed)}</Text> : null}
                {added.length ? <Text style={s.diffLine}>{CREATE.added(added.map(interestLabel).join(', '))}</Text> : null}
                {gone.length ? <Text style={s.diffLine}>{CREATE.dropped(gone.map(interestLabel).join(', '))}</Text> : null}
              </View>
            ) : (
              <Text style={s.pinNote}>{CREATE.readyNote()}</Text>
            )}

            <GlassPill tone="brand" style={s.pinBtn} label={CREATE.ready()} onPress={onCreate} />
          </View>
        ) : null}
      </GlassSurface>
    </Animated.View>
  );
}

// ============================================================ вид
// Числа — с кадра GR.04 («Step Content»: поля 12/16/24/16, между блоками вопроса 16).

const s = StyleSheet.create({
  /** Подложка кадра — ровный «Ambient · glass pilot» #F5F1EC, без цветных пятен. */
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  body: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 24, gap: 16 },
  /** «Suggestions»: строки через 4. */
  list: { gap: 4 },
  regen: { height: 40 },
  hints: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  dock: { paddingHorizontal: 16, paddingTop: 8, backgroundColor: color.ambientBase },

  /** Сводка под шапкой: те же поля 16, что у ленты, стекло со скруглением 20, как у карточек мастера. */
  pinWrap: {
    marginHorizontal: 16, marginTop: 8, marginBottom: 4, borderRadius: 20,
    ...Platform.select({
      ios: { shadowColor: '#0A0A14', shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
      default: {},
    }),
  },
  pin: { paddingHorizontal: 16, paddingVertical: 12 },
  pinHead: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 40 },
  pinLabel: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: '#5A616E' } as any,
  pinTitle: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 22, color: color.fg } as any,
  pinDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.primary },
  pinBody: { gap: 12, paddingTop: 10 },
  pinChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  pinChip: {
    height: 28, paddingHorizontal: 12, borderRadius: 14, justifyContent: 'center',
    // На белом стекле белый чип пропадал (снимок стенда 04.10) — лёгкая тёмная плёнка.
    backgroundColor: 'rgba(24,27,34,0.06)',
  },
  pinChipNew: { backgroundColor: color.primary },
  pinChipText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.fg } as any,
  diff: { gap: 2 },
  diffLabel: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.primary } as any,
  diffLine: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,
  pinNote: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#5A616E' } as any,
  pinBtn: { height: 48 },
});

