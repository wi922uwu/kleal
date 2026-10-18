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
 * ЗАТЕЯ СОБРАНА — СВОДКА С КНОПКОЙ ЖИВЁТ В ПОЛЕ ВВОДА (ReadyComposer), а не автопереход.
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
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform, TextInput,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { hOk, hTick } from '../src/haptics';
import { IconWand, IconChevronDown, IconChevronUp, IconMic } from '../src/components/icons';
import { InterestChipRow } from '../src/components/IntentChips';
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
              ? <MyLine key={i} text={m.text} at={m.at} fresh />
              : <AgentLine key={i} text={m.text} at={m.live ? undefined : m.at} markdown fresh />
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
          {/* Затея собрана — сводка становится частью поля ввода (см. ReadyComposer). */}
          {ready ? (
            <ReadyComposer
              cur={ready}
              versions={versions}
              open={sumOpen}
              onToggle={() => setSumOpen((o) => !o)}
              onCreate={next}
              value={draft}
              onChange={setDraft}
              onSubmit={submit}
              placeholder={T('Сообщение…', 'Message…', 'Mensaje…')}
              editable={!typing}
            />
          ) : (
            <CreateComposer
              value={draft}
              onChange={setDraft}
              onSubmit={submit}
              placeholder={T('Сообщение…', 'Message…', 'Mensaje…')}
              editable={!typing}
            />
          )}
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

/**
 * Сводка затеи В ПОЛЕ ВВОДА — название, лента чипов интересов и кнопка «Дальше →» (CREATE.nextStep).
 *
 * Решение владельца 17.10.2026 (вариант «Е»): как цитата при ответе в мессенджере — сводка
 * пристёгнута к полю, а не висит отдельным окном под шапкой. Под шапкой она закрывала разговор и
 * выглядела чужой среди пузырей; у поля она всегда под большим пальцем и не уезжает, пока человек
 * уточняет (ради этого её и закрепили 04.10).
 *
 * Чипы — ТЕ ЖЕ, что в выдаче людей (results.tsx): белая пилюля 36 со значком и подписью, лентой
 * до края. По ним идёт поиск, и человек должен узнать их потом на карточках. Чип, добавленный
 * последним ответом, — коралловый: так видно, что изменило уточнение. Остальное «что изменилось»
 * (переименование, убранные темы) — под стрелкой.
 *
 * Пока поле пустое, справа «Дальше →»; начал писать — значок отправки, как у обычного поля.
 */
function ReadyComposer({
  cur, versions, open, onToggle, onCreate, value, onChange, onSubmit, placeholder, editable,
}: {
  cur: Ready;
  versions: Ready[];
  open: boolean;
  onToggle: () => void;
  onCreate: () => void;
  value: string;
  onChange: (t: string) => void;
  onSubmit: () => void;
  placeholder: string;
  editable: boolean;
}) {
  /*
    СВОДКА ОБЪЯВЛЯЕТ О СЕБЕ. Появилась впервые — поднимается снизу (итог разговора). Пересобралась
    после ответа — короткий вдох и щелчок: полное появление на каждом уточнении читалось бы как
    «сводка пропала и пришла новая».
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
  const empty = !value.trim();

  return (
    <Animated.View entering={riseIn(0, 8)} style={[s.rcWrap, pulseStyle]}>
      <GlassSurface tone="light" radius={24} style={s.rc}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: open }}
          accessibilityLabel={`${CREATE.summaryLabel()}: ${cur.title}`}
          style={s.rcHead}
          onPress={onToggle}
          hitSlop={6}
        >
          <IconWand size={16} c={color.primary} />
          <Text style={s.rcTitle} numberOfLines={open ? 2 : 1}>{cur.title}</Text>
          {/* Точка у свёрнутой строки — намёк, что под стрелкой есть «что изменилось». */}
          {!open && (gone.length || renamed) ? <View style={s.pinDot} /> : null}
          {open ? <IconChevronDown size={18} c={color.fg} /> : <IconChevronUp size={18} c={color.fg} />}
        </Pressable>

        <InterestChipRow topics={cur.topics} added={added} />

        {open ? (
          changed ? (
            <View style={s.diff}>
              <Text style={s.diffLabel}>{CREATE.changed()}</Text>
              {renamed ? <Text style={s.diffLine}>{CREATE.wasCalled(renamed)}</Text> : null}
              {added.length ? <Text style={s.diffLine}>{CREATE.added(added.map(interestLabel).join(', '))}</Text> : null}
              {gone.length ? <Text style={s.diffLine}>{CREATE.dropped(gone.map(interestLabel).join(', '))}</Text> : null}
            </View>
          ) : (
            <Text style={s.pinNote}>{CREATE.readyNote()}</Text>
          )
        ) : null}

        <View style={s.rcField}>
          <TextInput
            style={s.rcInput}
            value={value}
            onChangeText={onChange}
            placeholder={placeholder}
            placeholderTextColor="#5A616E"
            onSubmitEditing={onSubmit}
            returnKeyType="send"
            editable={editable}
          />
          {empty ? (
            <GlassPill tone="brand" small style={s.rcBtn} label={CREATE.nextStep()} onPress={onCreate} />
          ) : (
            <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send', 'Enviar')} onPress={onSubmit} hitSlop={8}>
              <IconMic c="#5A616E" />
            </Pressable>
          )}
        </View>
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

  /** Сводка в поле ввода: стекло со скруглением 24, внутри те же поля 16, что у поля. */
  rcWrap: {
    borderRadius: 24,
    ...Platform.select({
      ios: { shadowColor: '#0A0A14', shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
      default: {},
    }),
  },
  rc: { paddingTop: 10, paddingBottom: 4, paddingHorizontal: 16, gap: 8 },
  rcHead: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 28 },
  rcTitle: { flex: 1, fontFamily: font.textSemibold, fontSize: 15, lineHeight: 22, color: color.fg } as any,
  /** Само поле — под чертой, высота 48, как у обычного поля мастера. */
  rcField: {
    height: 48, flexDirection: 'row', alignItems: 'center', gap: 8,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: 'rgba(24,27,34,0.12)',
  },
  rcInput: { flex: 1, color: color.fg, fontFamily: font.text, fontSize: 15, paddingVertical: 0 } as any,
  rcBtn: { height: 36 },
  pinDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.primary },
  diff: { gap: 2 },
  diffLabel: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.primary } as any,
  diffLine: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,
  pinNote: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#5A616E' } as any,
});

