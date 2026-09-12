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
  KeyboardAvoidingView, Platform, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { IconChevronLeft, IconSend } from '../src/components/icons';
import { useLang, getLang, T, dateLocale, use12h } from '../src/i18n';
import { useOnb } from '../src/state';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { buddy as buddyApi, VoicePayload } from '../src/api';
import { BUDDY, SHEET, looksLikeIntent, intentPhrase, intentTitle, intentDesc, sheetKept, packHistory, Turn } from '../src/buddy';
import { safeCut } from '../src/reveal';
import { Sheet } from '../src/components/Sheet';
import { color, radius as rad, space, type } from '../src/theme';
import { useVoiceMessage, VoiceBubble, VoiceMessageControl } from '../src/voice';
import Markdown from '../src/components/Markdown';
import { Thinking } from '../src/components/Thinking';
import { makeReveal } from '../src/reveal';
import { saveConversation } from '../src/history';

/**
 * `hello` — первая реплика экрана. Это не ответ модели, а обращение к человеку, и выглядеть оно
 * должно как заголовок страницы, а не как первая строчка переписки: с него разговор начинается.
 * Признак хранится ОТДЕЛЬНО, а не «# » в тексте: тот же текст уходит модели в историю, и решётка
 * попала бы к ней в контекст.
 */
type Msg = { who: 'bot' | 'me'; text: string; at: string; voice?: VoicePayload; hello?: boolean;
  /** Текст ещё пишется — под ним мигает курсор. */ live?: boolean };

const now = () =>
  new Date().toLocaleTimeString(dateLocale(), {
    hour: '2-digit', minute: '2-digit', hour12: use12h(),
  });

export default function Buddy() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх дока — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  /** Текст с главного экрана: человек уже сказал, что хочет, — повторять вопрос незачем. */
  const seed = String(useLocalSearchParams<{ q?: string }>().q || '').trim();

  const [thread, setThread] = useState<Msg[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  /** Ответ ещё идёт: точки могли погаснуть, но история пока не дописана. */
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState(false);
  /** Что распознал Kleal: фраза для реплики «а я думал…», заголовок и описание для окна. */
  const [what, setWhat] = useState('');
  const [seen, setSeen] = useState<{ title: string; desc: string } | null>(null);
  /** Тема, с которой откроется создание интента, если человек его выберет. */
  const [topic, setTopic] = useState('');
  const started = useRef(false);

  /*
    РАЗГОВОР С KLEAL ПОПАДАЕТ В ИСТОРИЮ — тем же способом, что и разговор в анкете.

    Сначала запись повесили только на онбординговый чат, и это была половина работы: человек
    поговорил здесь, вышел — и в истории пусто, хотя кнопка на главной обещает «историю
    разговоров», а разговор с Kleal живёт именно тут. Сообщено сразу после выкладки.

    Лента лежит в ref, а не читается из замыкания: эффект размонтирования собирается один раз, и
    `thread` в нём остался бы пустым. Ключ — момент открытия экрана; он же делает запись
    заменяемой, если сохранение случится дважды.
  */
  const threadRef = useRef<Msg[]>([]);
  threadRef.current = thread;
  const convId = useRef(String(Date.now())).current;
  useEffect(() => () => {
    saveConversation({
      id: convId,
      startedAt: Number(convId),
      topic: BUDDY.title(),
      lines: threadRef.current.map((m) => ({ who: m.who, text: m.text, at: m.at })),
    });
  }, [convId]);

  const say = useCallback((who: 'bot' | 'me', text: string, hello = false) => {
    setThread((t) => [...t, { who, text, at: now(), hello }]);
  }, []);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [thread.length, typing]);

  // Лист выехал — ждать больше нечего, точки гаснут. Не в тот же такт, что `setSheet(true)`:
  // им надо продержаться ровно ту долю секунды, пока идёт выезд.
  useEffect(() => {
    if (!sheet) return;
    const id = setTimeout(() => setTyping(false), 260);
    return () => clearTimeout(id);
  }, [sheet]);

  const profile = () => ({
    name: st.profile.name, age: st.profile.age, city: st.profile.city,
    interests: st.profile.interests?.explicit || [],
    languages: st.profile.languages || {},
  });

  /**
   * Что сделать с готовым ответом. Развилка та же, что была до потока, — вынесена отдельно,
   * потому что теперь она срабатывает в `done`, а не сразу после запроса.
   *
   * `shown` — НОМЕР записи, показанной потоком, или −1, если потоком не приходило. Раньше это
   * был просто «да/нет», и снималась «последняя» запись ленты; последней же могла оказаться
   * реплика человека, отправленная посреди ответа.
   */
  /**
   * Заменить показанную потоком реплику на окончательную.
   *
   * ЗАЧЕМ. Поток печатает СЫРОЙ текст модели, а чистка живёт на сервере и срабатывает уже после:
   * там разводят слипшиеся алфавиты, выбрасывают слова-гибриды и приводят в порядок пробелы и
   * переносы. Клиент же готовый текст никуда не девал — он клал его только в историю, а на экране
   * оставалась сырая версия. Ровно поэтому на живом экране осталось «могут бытьhourными часами»,
   * хотя сторож этот гибрид на сервере уже вырезал.
   *
   * Меняем ТОЛЬКО если текст отличается: одинаковая замена — лишняя перерисовка ленты на каждый
   * ответ, а он приходит на каждый ход.
   */
  const replaceShown = useCallback((at: number, text: string) => {
    setThread((prev) => {
      if (at < 0 || at >= prev.length || prev[at].text === text) return prev;
      const out = [...prev];
      out[at] = { ...out[at], text, live: false };
      return out;
    });
  }, []);

  const finish = useCallback((r: any, reply: string, text: string, next: Turn[], shown: number) => {
    if (r?.refused) {
      setSheet(false);
      setTopic('');
      setWhat('');
      setSeen(null);
    }
    if (looksLikeIntent(r)) {
      /*
        ОКНО НЕ ПЕРЕБИВАЕТ ВОПРОС АГЕНТА.

        Здесь окно выезжало ВСЕГДА, как только план распознан, а показанную реплику снимали с
        экрана. На потоке это выглядело так: агент на глазах пишет ответ, не дописывает — и вместо
        него выезжает лист. Сообщено с телефона: «начал писать сообщение, которое не успел
        дописать, потому что вылез попап».

        Хуже, что снимали ровно то, чего человеку не хватило. На «дота» агент ответил «Ты давно
        играешь? Хочешь обсудить последние обновления или стратегии?» — то есть уточнял, ЧТО
        именно обсуждать. Вопрос стёрли, окно предложило создать интент про «доту» вообще, и
        второй претензией пришло «он не уточнил, что именно я хочу обсудить».

        Поэтому: реплика ОСТАЁТСЯ на экране всегда, а окно выезжает только если агент ничего не
        спросил. Спросил — значит замысел ещё не собран, и перебивать уточнение окном рано:
        человек отвечает, а окно придёт следующим ходом, когда спрашивать будет нечего.
      */
      const asks = /[?？]\s*$/.test(String(reply || '').trim());
      if (asks) {
        if (shown < 0 && reply) say('bot', reply);
        else if (reply) replaceShown(shown, reply);
        setTurns(reply ? [...next, { role: 'assistant', content: reply }] : next);
        setTopic(text);
        setWhat(intentPhrase(r));
        setSeen({ title: intentTitle(r), desc: intentDesc(r) });
        return;
      }
      /*
        ЯВНАЯ ПРОСЬБА ПРИХОДИТ БЕЗ РЕПЛИКИ (см. buddy_chat на сервере): текста нет, окно — и есть
        ответ. Мягкая зацепка приходит с текстом, и он остаётся на экране; окно в этом случае
        выезжает после последней напечатанной буквы (см. `done`), а не поверх неё.
      */
      if (shown < 0 && reply) say('bot', reply);   // потоком не приходило — печатаем целиком
      else if (reply) replaceShown(shown, reply);
      setTurns(reply ? [...next, { role: 'assistant', content: reply }] : next);
      setTopic(text);
      setWhat(intentPhrase(r));
      setSeen({ title: intentTitle(r), desc: intentDesc(r) });
      /*
        ТОЧЕК ЗДЕСЬ БОЛЬШЕ НЕТ. Они горели, пока лист выезжает, потому что реплику в этот момент
        снимали с экрана и оставалась пустота. Реплика теперь остаётся — заполнять нечего, а точки
        поверх готового ответа означали бы, что придёт ещё один, и он не придёт.
      */
      setSheet(true);
      return;
    }
    if (reply) {
      if (shown < 0) say('bot', reply);    // потоком не приходило — печатаем целиком
      else replaceShown(shown, reply);     // потоком пришло сырое — подменяем очищенным
      setTurns([...next, { role: 'assistant', content: reply }]);
    }
  }, [say, replaceShown]);

  /**
   * ОТВЕТ ПОЯВЛЯЕТСЯ ПО МЕРЕ НАПИСАНИЯ.
   *
   * Измерено на живом сервере: модель начинает писать через 0,24 с, а весь ответ выходит за 15
   * секунд — токен за токеном. Ускорить генерацию нельзя; можно перестать ждать её конца. Первые
   * слова теперь на экране через ~1,9 с вместо 7,5 — это разница между «приложение думает» и
   * «приложение отвечает».
   *
   * Текст растёт ПРЯМО В ЛЕНТЕ, а не в отдельном состоянии: иначе пришлось бы держать две копии
   * и склеивать их в конце, а расхождение между ними человек увидел бы как мигание.
   */
  const send = useCallback((text: string, hist: Turn[]) => new Promise<void>((resolve) => {
    const next: Turn[] = [...hist, { role: 'user', content: text }];
    setTurns(next);
    setTyping(true);
    /*
      ОТВЕТ ЗАНЯТ ДО КОНЦА, А НЕ ДО ПЕРВОГО СЛОВА.

      `typing` гаснет на первом же куске — иначе точки висели бы поверх начавшего появляться
      текста. Но занятость на этом не кончается: реплика, отправленная посреди ответа, уходила со
      СТАРОЙ историей (своего ответа модель в ней ещё не видела), а `done` следом переписывал
      историю целиком — и эта реплика пропадала из неё вовсе. Модель отвечала так, будто её и не
      было: повторяла сказанное про ту же доту.

      Поэтому занятость держится до `done`/`error` и отдельно от точек.
    */
    setBusy(true);

    let acc = '';
    let opened = false;
    /*
      НОМЕР СВОЕГО ПУЗЫРЯ, А НЕ «ПОСЛЕДНИЙ В ЛЕНТЕ».

      Поток дописывал ответ в последнюю запись ленты — и пока это был его собственный пузырь, всё
      сходилось. Но `setTyping(false)` срабатывает на ПЕРВОМ куске, а не в конце: с этого момента
      композер снова живой, и человек может отправить свою реплику прямо посреди ответа. Она
      ложится в ленту последней — и следующий кусок потока переписывал ЕЁ ТЕКСТ, оставив `who:
      'me'`. На экране получался красный пузырь «от человека» с ответом агента целиком, вместе с
      сырой разметкой. Именно это и было на присланных снимках.

      Запоминаем место своей записи один раз, при создании, и правим только его — да и то лишь
      если там по-прежнему стоит реплика агента.
    */
    let at = -1;
    /** Что сейчас на экране — чтобы понять, допечатала ли машинка всё (см. `done`). */
    let lastShown = '';
    /** Окно ждёт последней буквы: зовётся из `show`, когда показано всё принятое. */
    let afterTyped: null | (() => void) = null;

    /**
     * Показ развязан с приходом: буквы приезжают рывками (201 кусок на 656 символов, между ними
     * то 10 мс, то 400), а на экран выдаются ровным темпом. См. src/reveal.ts — там же объяснено,
     * почему хвост с незакрытой разметкой придерживается.
     */
    const show = (shown: string) => {
      setTyping(false);
      lastShown = shown;
      if (afterTyped && shown === safeCut(acc)) { const f = afterTyped; afterTyped = null; f(); }
      setThread((prev) => {
        if (!opened) {
          opened = true;
          at = prev.length;
          return [...prev, { who: 'bot', text: shown, at: now(), live: true }];
        }
        const out = prev.slice();
        if (out[at]?.who !== 'bot') return out;   // чужой пузырь не трогаем
        out[at] = { ...out[at], text: shown, live: true };
        return out;
      });
    };
    const rev = makeReveal(show);
    const grow = (t: string) => { acc += t; rev.push(t); };

    buddyApi.chatStream(next, profile(), {
      delta: grow,
      error: async () => {
        /**
         * ПОТОК ОБОРВАЛСЯ — ЭТО НЕ ПОВОД ТЕРЯТЬ ОТВЕТ.
         *
         * Поток — способ доставки, а не сам ответ. Сообщено с телефона: «Связь пропала.
         * Повторишь?» приходило на каждое сообщение подряд, хотя сервер отвечал исправно —
         * рвался именно поток, и вместе с ним выбрасывался готовый ответ. Человек видел
         * приложение, которое перестало работать.
         *
         * Поэтому здесь не извинение, а ВТОРАЯ ПОПЫТКА обычным запросом. Извиняемся только если
         * и она не прошла: тогда связи действительно нет.
         */
        if (opened) { rev.stop(); setTyping(false); setBusy(false); resolve(); return; }   // половина уже на экране
        try {
          const r: any = await buddyApi.chat(next, profile());
          setTyping(false);
          const reply = String(r?.reply || '');
          // Явная просьба приходит без текста, но с затеей — это ответ, а не обрыв связи.
          if (reply || looksLikeIntent(r)) finish(r, reply, text, next, -1);
          else say('bot', BUDDY.offline());
        } catch {
          setTyping(false);
          say('bot', BUDDY.offline());
        }
        setBusy(false);
        resolve();
      },
      done: (r: any) => {
        setTyping(false);
        const reply = String(r?.reply || acc);
        const settle = () => {
          // Итог разошёлся с показанным (вторая попытка, обрезка по границе, заготовка при
          // отказе) — переписываем. Иначе над настоящим ответом висела бы оборванная половина.
          if (opened) {
            setThread((prev) => {
              const out = prev.slice();
              const cur = out[at];
              if (cur?.who !== 'bot') return out;
              out[at] = { ...cur, text: r?.replaced ? reply : cur.text, live: false };
              return out;
            });
          }
          finish(r, reply, text, next, opened ? at : -1);
          setBusy(false);
          resolve();
        };
        /*
          ОКНО — ПОСЛЕ ПОСЛЕДНЕЙ БУКВЫ, А НЕ ПОВЕРХ НЕЁ. Раньше `done` останавливал машинку,
          вбрасывал текст целиком и в тот же такт выдвигал окно: человек видел, как реплика ещё
          печатается — и поверх неё выезжает лист. Явная просьба теперь приходит вовсе без текста
          (сервер), а здесь — второй случай, мягкая зацепка с текстом: даём машинке допечатать
          и открываем окно, когда показано всё принятое. Страховка по времени — если машинке
          мешает что-то непредвиденное, окно всё равно выедет.
        */
        if (opened && looksLikeIntent(r) && !r?.replaced) {
          let fired = false;
          let guard: ReturnType<typeof setTimeout> | null = null;
          const once = () => {
            if (fired) return;
            fired = true;
            if (guard) clearTimeout(guard);
            afterTyped = null;
            rev.stop();
            settle();
          };
          rev.finish();
          if (lastShown === safeCut(acc)) { once(); return; }   // уже всё показано
          afterTyped = once;
          guard = setTimeout(once, 4000);
          return;
        }
        rev.finish();
        // Дописываем итог и гасим курсор. Ждать, пока машинка домотает сама, нельзя: она
        // допечатывает уже принятый текст, а `done` может нести ДРУГОЙ (вторая попытка,
        // обрезка по границе) — тогда курсор мигал бы под старым текстом.
        if (opened) rev.stop();
        settle();
      },
    });
  }), [say, finish, st.profile]);

  /** Голосовое ложится в ленту своим пузырём, а модели уходит расшифровка — ей слушать нечем. */
  const deliverVoice = useCallback(async (payload: VoicePayload) => {
    setThread((t) => [...t, { who: 'me', text: payload.transcript, voice: payload, at: now() }]);
    await send(payload.transcript, turns);
  }, [send, turns]);
  const voice = useVoiceMessage(deliverVoice, typing);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (seed) {
      say('me', seed);
      send(seed, []);
      return;
    }
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      const hello = BUDDY.hello(st.profile.name || '');
      say('bot', hello, true);
      /**
       * Приветствие идёт и В ИСТОРИЮ, а не только на экран.
       *
       * `say()` рисует пузырь, `turns` — то, что видит модель. Пока приветствие жило только в
       * первом, модель получала первую реплику человека как самую первую в разговоре, сервер
       * помечал её «[FIRST MESSAGE] … greet them as a new acquaintance», и модель здоровалась
       * ВТОРОЙ раз: «Привет, Иван. О чём поговорим?» — «привет» — «Привет, Иван! …».
       *
       * Она и не могла поступить иначе: поздороваться было нечем — в её истории приветствия не
       * было. Кладём его туда, и правило промпта «do NOT greet again» наконец применимо.
       */
      setTurns((t) => (t.length ? t : [{ role: 'assistant', content: hello }]));
    }, 450);
  }, []);

  const submit = () => {
    const t = draft.trim();
    if (!t || typing || busy) return;
    setDraft('');
    say('me', t);
    send(t, turns);
  };

  /**
   * В создание уезжает не только последняя фраза, но и весь разговор до неё. «Поговорить с кем-то
   * ОБ ЭТОМ» без истории не значит ничего — построитель переспрашивал «о чём?», хотя человек
   * рассказывал ему это минуту назад.
   */
  /**
   * «Продолжим общаться»: окно закрывается, и Kleal вслух называет, что он понял. Молчаливое
   * закрытие оставляло человека с догадкой — распознал агент что-то или нет.
   */
  const keepChatting = () => {
    setSheet(false);
    if (!what) return;
    const line = sheetKept(what);
    say('bot', line);
    setTurns((t) => [...t, { role: 'assistant', content: line }]);
  };

  const toCreate = () => {
    setSheet(false);
    const params: Record<string, string> = {};
    if (topic) params.seed = topic;
    // Затравка уже лежит последней в turns — в историю для сервера она попадёт оттуда, поэтому
    // здесь отрезаем её, чтобы не уехала дважды.
    const hist = topic ? turns.filter((t) => t.content !== topic) : turns;
    const packed = packHistory(hist);
    if (packed) params.history = packed;
    router.navigate({ pathname: '/create', params });
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" style={s.back} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
            <IconChevronLeft />
          </Pressable>
          <View style={{ flex: 1 }} />
          <Pressable
            accessibilityRole="button"
            style={s.createBtn}
            onPress={() => { setTopic(''); setWhat(''); setSeen(null); setSheet(true); }}
          >
            <Text style={s.createPlus}>+</Text>
            <Text style={s.createText}>{BUDDY.create()}</Text>
          </Pressable>
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
          {/*
            РЕПЛИКА И ОТВЕТ ВЫГЛЯДЯТ ПО-РАЗНОМУ, и это не украшение.

            Человек говорит — его слова остаются пузырём справа. Модель пишет — её ответ идёт
            страницей во всю ширину, без подложки и без рамки. Пока оба были пузырями, экран
            сообщал, что разбор на восемь абзацев — такая же проходная реплика, как «ок», и
            читался он так же бегло. Плюс разметка внутри пузыря схлопывалась в кашу из звёздочек
            и решёток: она не просто не рисовалась, она МЕШАЛА.
          */}
          {thread.map((m, i) => {
            const mine = m.who === 'me';
            if (m.voice) {
              return (
                <View key={i} style={{ alignItems: mine ? 'flex-end' : 'flex-start' }}>
                  <VoiceBubble voice={m.voice} mine={mine} />
                  <Text style={s.time}>{m.at}</Text>
                </View>
              );
            }
            if (mine) {
              return (
                <View key={i} style={{ alignItems: 'flex-end' }}>
                  <View style={[s.bub, s.bubMe]}>
                    <Text style={[s.bubText, { color: color.onPrimary }]}>{m.text}</Text>
                  </View>
                  <Text style={s.time}>{m.at}</Text>
                </View>
              );
            }
            if (m.hello) {
              return (
                <View key={i} style={s.answer}>
                  <Text style={s.hello}>{m.text}</Text>
                  <Text style={[s.time, s.timeAnswer]}>{m.at}</Text>
                </View>
              );
            }
            return (
              <View key={i} style={s.answer}>
                <Markdown text={m.text} />
                {/* Время под ответом приглушено сильнее, чем под репликой: у страницы оно
                    служебная пометка, а не часть разговора. */}
                <Text style={[s.time, s.timeAnswer]}>{m.at}</Text>
              </View>
            );
          })}
          {/* Ожидание — не вертушка, а живая строка: см. src/components/Thinking.tsx. */}
          {typing ? <Thinking /> : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          <View style={s.field}>
            {/*
              Во время записи поля нет — полоса записи занимает его место. Именно `null`, а не
              перестроенная разметка: соседняя кнопка обязана остаться на СВОЁМ месте в дереве,
              иначе React пересоберёт её ровно в миг старта записи и жест удержания оборвётся.
            */}
            {voice.phase === 'idle' ? (
              <TextInput
                style={s.input}
                value={draft}
                onChangeText={setDraft}
                placeholder={BUDDY.placeholder()}
                placeholderTextColor={color.neutral400}
                onSubmitEditing={submit}
                returnKeyType="send"
              />
            ) : null}
            {voice.phase === 'idle' && draft.trim() ? (
              // Пока ответ идёт, кнопка ГАСНЕТ, а не молчит: нажатие без ответа читается как
              // сломанное приложение, а бледная кнопка — как «сейчас нельзя».
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={T('Отправить', 'Send', 'Enviar')}
                onPress={submit}
                disabled={busy}
                hitSlop={8}
              >
                <IconSend size={18} c={busy ? color.neutral400 : color.primary} />
              </Pressable>
            ) : (
              <VoiceMessageControl voice={voice} />
            )}
          </View>
        </View>

        <GetStarted
          open={sheet}
          title={seen?.title}
          what={seen?.desc}
          onCreate={toCreate}
          onKeep={keepChatting}
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
  open, title, what, onCreate, onKeep, bottomInset = 0,
}: {
  open: boolean;
  /** Заголовок затеи, как на карточке: «Поговорить про кофе», «Падел». */
  title?: string;
  /** Что именно Kleal предлагает сделать — одним предложением. Человек соглашается на затею, а не на «интент». */
  what?: string;
  onCreate: () => void;
  onKeep: () => void;
  bottomInset?: number;
}) {
  return (
    <Sheet visible={open} onClose={onKeep} title={SHEET.title()} bottomInset={Math.max(bottomInset, 18)} grip>
        {/* Заголовок и описание — как карточка затеи, а не «Похоже, ты хочешь …» с подставленной
            подписью: в кавычки попадал то ярлык, то вся реплика человека целиком. */}
        {title ? <Text style={sh.title}>{title}</Text> : null}
        {what ? <Text style={sh.what}>{what}</Text> : null}
        <Pressable accessibilityRole="button" style={[sh.btn, sh.btnPri]} onPress={onCreate}>
          <Text style={sh.btnPriText}>{SHEET.create()}</Text>
        </Pressable>
        <Pressable accessibilityRole="button" style={[sh.btn, sh.btnSec]} onPress={onKeep}>
          <Text style={sh.btnSecText}>{SHEET.keep()}</Text>
        </Pressable>
    </Sheet>
  );
}

// ============================================================ вид
// Всё ниже — оформление UX-каркаса: цвета и размеры берутся из токенов темы, своих значений тут
// нет. При натягивании UI меняется этот блок, логика выше остаётся.

const s = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: space.sm },
  wrap: { flex: 1, backgroundColor: color.bg },
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
  /**
   * Ответ модели. Ни подложки, ни рамки, ни ограничения ширины: это страница, а не реплика.
   * Верхняя отбивка больше нижней — ответ отделяется от предыдущего вопроса сильнее, чем от
   * собственной пометки времени.
   */
  answer: { alignSelf: 'stretch', marginTop: space.lg, marginBottom: space.xs },
  timeAnswer: { color: color.neutral300, marginTop: space.xs } as any,
  /** Приветствие — ступень заголовка документа: разговор им ОТКРЫВАЕТСЯ, а не продолжается. */
  hello: { ...type.mdH1, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,

  dock: { paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.bg },
  field: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
});

const sh = StyleSheet.create({
  /** Затея в окне: заголовок карточки и строка-описание под ним, перед кнопками. */
  title: { ...type.title, color: color.fg } as any,
  what: { ...type.bodySmall, color: color.muted, marginTop: -6, marginBottom: 4 } as any,
  btn: { height: 54, borderRadius: rad.full, alignItems: 'center', justifyContent: 'center' },
  btnPri: { backgroundColor: color.primary },
  btnPriText: { ...type.button, color: color.onPrimary } as any,
  btnSec: { backgroundColor: color.neutral100 },
  btnSecText: { ...type.button, color: color.fg } as any,
});
