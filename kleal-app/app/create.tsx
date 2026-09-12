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
  Animated, Easing,
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { hOk, hTick } from '../src/haptics';
import { IconChevronLeft, IconMic, IconSpark } from '../src/components/icons';
import { useLang, getLang, T, replyLang, dateLocale, use12h } from '../src/i18n';
import { useOnb } from '../src/state';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { buddy as buddyApi } from '../src/api';
import { CREATE, topicsOf, titleOf, unpackHistory, looksLikeIntent, Turn } from '../src/buddy';
import { color, radius as rad, space, type } from '../src/theme';
import Markdown from '../src/components/Markdown';
import { Thinking } from '../src/components/Thinking';
import { makeReveal } from '../src/reveal';

type Msg = { who: 'bot' | 'me'; text: string; at: string ;
  /** Текст ещё пишется — под ним мигает курсор. */ live?: boolean };

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
  /**
   * ПЕРВОЕ ПОЯВЛЕНИЕ СВОДКИ РАСКРЫВАЕТ ЕЁ САМО.
   *
   * Свёрнутой она была задумана нарочно: одна строка не закрывает разговор. Но именно в момент,
   * когда она появляется впервые, показывать одну строку неправильно — это единственный кадр, ради
   * которого весь разговор и шёл, а он проскакивал незамеченным. Дальше человек сворачивает её
   * сам, и его выбор больше не трогаем: раскрытие однократное.
   */
  const shown = useRef(false);
  useEffect(() => {
    if (!ready || shown.current) return;
    shown.current = true;
    setSumOpen(true);
  }, [ready]);
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
   * Что сделать с готовым ответом построителя. Вынесено отдельно, потому что теперь срабатывает
   * в `done`, а не сразу после запроса.
   *
   * `shown` — показался ли текст потоком: от него зависит, печатать ли реплику ещё раз.
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
  }, [say]);

  /**
   * ОТВЕТ ПОЯВЛЯЕТСЯ ПО МЕРЕ НАПИСАНИЯ — то же, что на экране Бадди.
   *
   * Измерено на живом сервере: обычный путь 5,2 с. Это дольше разговора с Бадди, потому что
   * построитель не только отвечает, но и разбирает сказанное в тему и заголовок. Генерацию не
   * ускорить, но ждать её конца незачем: первые слова приходят почти сразу.
   *
   * Серверная ручка это умела с самого начала — просто никто не просил.
   */
  const ask = useCallback((text: string, hist: Turn[]) => {
    const next: Turn[] = [...hist, { role: 'user', content: text }];
    setTurns(next);
    setTyping(true);
    setHints([]);
    setRetry(null);

    let acc = '';
    let opened = false;
    // Ровный показ — тот же, что на экране Бадди. См. src/reveal.ts.
    const rev = makeReveal((shown: string) => {
      /*
        ОЖИДАНИЕ ГАСНЕТ В `done`, А НЕ ЗДЕСЬ, И ЭТО ИСПРАВЛЕНИЕ.

        Раньше точки убирались на первой же показанной букве — казалось логичным: раз пошёл текст,
        ждать больше нечего. Но на этом экране ответ — только половина работы: после реплики
        построитель ещё разбирает сказанное в тему и ключи, и приходит это в `done`, через две-три
        секунды после того, как текст дочитан. Всё это время экран стоял пустой: реплика есть,
        сводки нет, признаков работы никаких. Ровно на этой паузе и возникает ощущение, что
        приложение зависло.

        Теперь точки живут до `done` — то есть до момента, когда падает карточка. Пока текст
        приезжает, они стоят под ним и не мешают: подпись к этому времени как раз меняется на
        «Собираю затею», и это правда.
      */
      setThread((prev) => {
        if (!opened) { opened = true; return [...prev, { who: 'bot', text: shown, at: now(), live: true }]; }
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
        rev.finish();
        const reply = String(r?.reply || acc);
        if (opened) {
          rev.stop();
          setThread((prev) => {
            const out = prev.slice();
            const cur = out[out.length - 1];
            out[out.length - 1] = { ...cur, text: r?.replaced ? reply : cur.text, live: false };
            return out;
          });
        }
        settle(r, reply, text, next, opened);
      },
      error: async () => {
        // Как и в чате Бадди: поток — способ доставки, а не ответ. Сначала вторая попытка обычным
        // запросом, и только если и она не прошла — «попробуем ещё раз».
        if (opened) { rev.stop(); setThread((prev) => prev.slice(0, -1)); }
        try {
          const r: any = await buddyApi.intentBuild(next, profile());
          setTyping(false);
          const reply = String(r?.reply || '');
          if (reply) { settle(r, reply, text, next, false); return; }
        } catch {
          /* и обычный запрос не прошёл — значит связи правда нет */
        }
        setTyping(false);
        setTurns(hist);
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
  const next = () => router.navigate({
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
          {/*
            У «НАЗАД» ОБЯЗАН БЫТЬ ЗАПАСНОЙ ПУТЬ. Голый `router.back()` молча ничего не делает, когда
            возвращаться некуда, — навигатор отвечает «GO_BACK was not handled», и кнопка выглядит
            сломанной. А некуда бывает чаще, чем кажется: экран открыт по ссылке снаружи, или он
            оказался первым после холодного старта. Поймано ровно здесь, на создании интента,
            открытом по ссылке.
            `replace` на корень — единственная законная его форма (см. правило в наборе проверок):
            он подменяет ТЕКУЩИЙ экран, а не кладёт вторую главную поверх первой.
          */}
          <Pressable accessibilityRole="button" style={s.back} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
            <IconChevronLeft />
          </Pressable>
          <View style={{ flex: 1 }} />
          <Pressable accessibilityRole="button" style={s.allBtn} onPress={() => router.dismissTo('/home')}>
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

          {/* То же правило, что на Бадди и в онбординге: человек говорит пузырём, модель пишет
              страницей. См. src/components/Markdown.tsx. */}
          {thread.map((m, i) => (
            <View key={i} style={m.who === 'me' ? { alignItems: 'flex-end' } : s.answer}>
              {m.who === 'me' ? (
                <View style={[s.bub, s.bubMe]}>
                  <Text style={[s.bubText, { color: color.onPrimary }]}>{m.text}</Text>
                </View>
              ) : (
                <Markdown text={m.text} />
              )}
              <Text style={[s.time, m.who !== 'me' && s.timeAnswer]}>{m.at}</Text>
            </View>
          ))}

          {/* Ожидание — не вертушка, а живая строка: см. src/components/Thinking.tsx. */}
          {typing ? <Thinking /> : null}

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
                <Text style={s.hintText}>{T('Попробовать снова', 'Try again', 'Reintentar')}</Text>
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
            Круг замыкается там же, где начался: сводка по затее и кнопка под ней — та
            самая, что была в окне Бадди. Кнопки «Дальше» здесь нет намеренно: она обещала
            следующий шаг, а человек уже ответил на всё, что у него спрашивали. Уточнил ещё раз —
            сводка пересобирается, и кнопка снова та же.
          */}
          {/* Сводка больше не живёт в ленте — она закреплена под шапкой (см. PinnedSummary):
              разговор уточняющий, и карточка уезжала вверх ровно тогда, когда её и надо смотреть. */}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          <View style={s.field}>
            <TextInput
              style={s.input}
              value={draft}
              onChangeText={setDraft}
              placeholder={T('Сообщение…', 'Message…', 'Mensaje…')}
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
 * стояла в ленте, её уносило вверх ровно тогда, когда на неё и надо смотреть, а кнопку под ней
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
  /**
   * СВОДКА ОБЪЯВЛЯЕТ О СЕБЕ, А НЕ ПРОСТО ВОЗНИКАЕТ.
   *
   * Она появляется под шапкой мгновенно и без единого признака движения — глазу не за что
   * зацепиться, и самый важный кадр разговора человек попросту не замечает. Здесь два разных
   * события и два разных отклика на них:
   *
   *   ПОЯВИЛАСЬ ВПЕРВЫЕ — съезжает сверху и проявляется, с системным «получилось». Это итог
   *     разговора, и отклик тут тот же, что у принятого кода: не «нажал», а «вышло».
   *   ПЕРЕСОБРАЛАСЬ ПОСЛЕ ОТВЕТА — короткий толчок и щелчок. Полное появление на каждом уточнении
   *     читалось бы как «сводка пропала и пришла новая», а она та же самая, просто другая внутри.
   *
   * Обе анимации на нативном драйвере: сдвиг, прозрачность и масштаб. Ни одна не трогает разметку,
   * поэтому лента под сводкой не дёргается.
   */
  const drop = useRef(new Animated.Value(0)).current;
  const squash = useRef(new Animated.Value(0)).current;
  const pulse = useRef(new Animated.Value(0)).current;
  const seen = useRef(versions.length);

  /**
   * ПОЯВЛЕНИЕ СОБРАНО ИЗ ТРЁХ ДВИЖЕНИЙ, А НЕ ИЗ ОДНОГО.
   *
   * Обычная пружина «сверху вниз» даёт въезд, а не падение: карточка приезжает и замирает. Каплю
   * узнают по другому — по тому, что она РАСПЛЮЩИВАЕТСЯ при ударе и потом отыгрывает обратно.
   * Поэтому здесь:
   *   падение   — ускоряющееся (`Easing.in`), а не ровное: ровное читается как «переместили»;
   *   удар      — короткое сжатие по высоте и растяжение по ширине, 90 мс, на пределе заметности;
   *   отдача    — пружина с малым затуханием, та самая «бамбл»: пара затухающих колебаний.
   *
   * Объём сохраняется: насколько сжали по высоте, настолько растянули по ширине. Без этого
   * карточка не расплющивается, а просто дёргается в размере — глаз читает это как сбой.
   *
   * Всё на нативном драйвере: сдвиг и масштаб. Разметку не трогает ни одно из трёх, поэтому лента
   * под сводкой стоит на месте.
   */
  useEffect(() => {
    hOk();
    Animated.sequence([
      Animated.timing(drop, {
        toValue: 1,
        duration: 240,
        easing: Easing.in(Easing.quad),
        useNativeDriver: true,
      }),
      Animated.timing(squash, {
        toValue: 1,
        duration: 90,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      }),
      Animated.spring(squash, {
        toValue: 0,
        useNativeDriver: true,
        damping: 9,
        stiffness: 260,
        mass: 0.7,
      }),
    ]).start();
  }, [drop, squash]);

  useEffect(() => {
    if (versions.length === seen.current) return;
    seen.current = versions.length;
    hTick();
    Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 130, useNativeDriver: true }),
      Animated.spring(pulse, { toValue: 0, useNativeDriver: true, damping: 11, stiffness: 240 }),
    ]).start();
  }, [pulse, versions.length]);

  const prev = versions.length > 1 ? versions[versions.length - 2] : null;
  const added = prev ? cur.topics.filter((t) => !prev.topics.includes(t)) : [];
  const gone = prev ? prev.topics.filter((t) => !cur.topics.includes(t)) : [];
  const renamed = prev && prev.title !== cur.title ? prev.title : '';
  const changed = added.length || gone.length || renamed;

  return (
    <Animated.View
      style={[
        s.pin,
        {
          opacity: drop,
          transform: [
            { translateY: drop.interpolate({ inputRange: [0, 1], outputRange: [-34, 0] }) },
            // Удар: шире и ниже. Отдача возвращает обе стороны к единице с парой колебаний.
            { scaleX: squash.interpolate({ inputRange: [0, 1], outputRange: [1, 1.07] }) },
            { scaleY: squash.interpolate({ inputRange: [0, 1], outputRange: [1, 0.91] }) },
            { scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.03] }) },
          ],
        },
      ]}
    >
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
    </Animated.View>
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
  answer: { alignSelf: 'stretch', marginTop: space.lg, marginBottom: space.xs },
  timeAnswer: { color: color.neutral300, marginTop: space.xs } as any,
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
