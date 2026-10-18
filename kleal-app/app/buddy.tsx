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
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams, useIsFocused } from 'expo-router';
import { IconClock } from '../src/components/icons';
import { HOME } from '../src/home';
import { GlassSurface, GlassBack, GlassIconButton, usePress } from '../src/components/LiquidGlass';
import Animated, { cancelAnimation, Easing as REasing, useAnimatedStyle, useReducedMotion, useSharedValue, withRepeat, withTiming, type SharedValue } from 'react-native-reanimated';
import Svg, { Circle as SvgCircle, Defs as SvgDefs, RadialGradient as SvgRadial, Stop as SvgStop } from 'react-native-svg';
import { GlassPill } from '../src/components/Glass';
import { LogoFace } from '../src/components/Logo';
import { SendArrow } from '../src/components/SendArrow';
import { BubbleIn } from '../src/components/ChatMotion';
import { useLang, T, dateLocale, use12h } from '../src/i18n';
import { useOnb } from '../src/state';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { buddy as buddyApi, VoicePayload } from '../src/api';
import { BUDDY, SHEET, looksLikeIntent, intentPhrase, intentTitle, intentDesc, sheetKept, packHistory, needsSignIn, Turn } from '../src/buddy';
import { safeCut } from '../src/reveal';
import { Sheet, SheetText } from '../src/components/Sheet';
import { color, font, space, type, heading } from '../src/theme';
import { useVoiceMessage, VoiceBubble, VoiceMessageControl } from '../src/voice';
import Markdown from '../src/components/Markdown';
import { Thinking } from '../src/components/Thinking';
import { makeReveal } from '../src/reveal';
import { saveConversation, getConversation, turnsOf } from '../src/history';

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
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх дока — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  /** Текст с главного экрана: человек уже сказал, что хочет, — повторять вопрос незачем. */
  const qp = useLocalSearchParams<{ q?: string; resume?: string }>();
  const seed = String(qp.q || '').trim();
  /** Продолжить разговор из истории (app/history.tsx): id записи. */
  const resume = String(qp.resume || '').trim();

  const [thread, setThread] = useState<Msg[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  /** Ответ ещё идёт: точки могли погаснуть, но история пока не дописана. */
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState(false);
  /** Сервер ответил 401 — под репликой Kleal кнопка входа (см. BUDDY.signIn). */
  const [signIn, setSignIn] = useState(false);
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
  // Продолжаем запись из истории под ТЕМ ЖЕ id — разговор не двоится, а дописывается.
  const convId = useRef(resume || String(Date.now())).current;
  const startedAt = useRef(Number(resume) || Number(convId) || Date.now());
  const createdRef = useRef(false);
  /*
    СОХРАНЕНИЕ ПО ХОДУ, А НЕ ТОЛЬКО ПРИ УХОДЕ (18.10.2026). Раньше запись делалась при размонтировании —
    закрыл приложение посреди разговора, и его не было в истории. И хранился только текст: восстановить
    разговор было нечем. Теперь вместе с репликами — ходы для модели и окно затеи (src/history.ts).
  */
  const snapshot = useRef<() => void>(() => {});
  snapshot.current = () => saveConversation({
    id: convId,
    startedAt: startedAt.current,
    updatedAt: Date.now(),
    topic: BUDDY.title(),
    lines: threadRef.current.map((m) => ({ who: m.who, text: m.text, at: m.at, ...(m.hello ? { hello: true } : {}) })),
    turns,
    intent: { what, seen, topic, sheet },
    created: createdRef.current,
    source: 'buddy',
  });
  useEffect(() => {
    const id = setTimeout(() => snapshot.current(), 500);
    return () => clearTimeout(id);
  }, [thread, turns, what, seen, topic, sheet]);
  useEffect(() => () => snapshot.current(), []);

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
      // Сервер на явную просьбу молчит — на экране это была пауза и выезжающий лист. По кадру GR.02
      // Kleal сначала отвечает «Great idea! Let’s create an intent…». В историю модели не идёт.
      else say('bot', BUDDY.letsCreate());
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
      error: async (why: string) => {
        // Нет входа — вторая попытка тем же токеном получит тот же отказ. Сразу ведём ко входу.
        if (needsSignIn(why)) {
          if (opened) rev.stop();
          setTyping(false); setBusy(false); setSignIn(true); say('bot', BUDDY.signIn()); resolve(); return;
        }
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
        } catch (e) {
          setTyping(false);
          if (needsSignIn(e)) { setSignIn(true); say('bot', BUDDY.signIn()); }
          else say('bot', BUDDY.offline());
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
    if (resume) {
      // Восстановление: та же лента, тот же контекст для модели, окно затеи там, где было.
      getConversation(resume).then((it) => {
        if (!it) return;
        setThread(it.lines.map((l) => ({ who: l.who, text: l.text, at: l.at, hello: !!l.hello })));
        setTurns(turnsOf(it));
        createdRef.current = !!it.created;
        if (it.intent) {
          setWhat(it.intent.what || '');
          setSeen(it.intent.seen || null);
          setTopic(it.intent.topic || '');
          if (it.intent.sheet) setSheet(true);
        }
      }).catch(() => {});
      return;
    }
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
    createdRef.current = true;           // в истории — «затея создана»
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
        {/*
          ШАПКА GR.02 («App Bar · Fixed»): три слота по 111 — слева «назад», по центру «Kleal»
          гарнитурой шапок 20/24, справа стеклянная «Create» с маскотом. Боковые слоты равной ширины
          держат заголовок ровно по центру экрана.
          ИСТОРИЯ РАЗГОВОРОВ — в левом слоте рядом с «назад». На кадре её нет, но входа к прошлым
          разговорам больше нигде нет (главная GR.01 его тоже не рисует), а осиротить экран истории
          нельзя. Слот 111 вмещает два круга 44 с промежутком 8, центр заголовка не сдвигается.
        */}
        <View style={s.head}>
          <View style={s.slot}>
            <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))} />
            <GlassIconButton label={HOME.history()} onPress={() => router.navigate('/history')}>
              <IconClock size={20} c={color.fg} />
            </GlassIconButton>
          </View>
          <Text style={[s.title, heading(lang, type.headingSm)]} numberOfLines={1}>{BUDDY.title()}</Text>
          <View style={[s.slot, s.slotRight]}>
            <CreatePill
              label={BUDDY.create()}
              onPress={() => { setTopic(''); setWhat(''); setSeen(null); setSheet(true); }}
            />
          </View>
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
            // Разговор с Kleal живёт только на этом экране — каждая реплика в нём новая (ChatMotion).
            if (mine) {
              return (
                <BubbleIn key={i} mine fresh style={s.rowMe}>
                  <View style={s.shadowMe}>
                    <GlassSurface tone="brand" radius={20} style={[s.bub, s.bubMe]}>
                      <Text style={[s.bubText, { color: color.onPrimary }]}>{m.text}</Text>
                    </GlassSurface>
                  </View>
                  <Text style={[s.time, s.timeMe]}>{m.at}</Text>
                </BubbleIn>
              );
            }
            /*
              ОТВЕТ KLEAL — ПУЗЫРЬ, КАК НА КАДРЕ GR.02: светлое стекло 20/20/20/4, ширина до 260 из 358.
              Раньше ответ шёл страницей во всю ширину, без подложки, а приветствие — заголовком. Борд
              «0 · Create the intent» рисует разговор с Kleal обычной перепиской, поэтому и приветствие,
              и ответы — пузыри. Разметка внутри пузыря рисуется той же Markdown: длинный разбор с
              пунктами по-прежнему читается, просто в своей рамке.
            */
            return (
              <BubbleIn key={i} mine={false} fresh style={s.rowThem}>
                <View style={s.shadowThem}>
                  <GlassSurface tone="light" radius={20} style={[s.bub, s.bubThem]}>
                    {m.hello ? <Text style={s.bubText}>{m.text}</Text> : <Markdown text={m.text} />}
                  </GlassSurface>
                </View>
                <Text style={s.time}>{m.at}</Text>
              </BubbleIn>
            );
          })}
          {/* Ожидание — не вертушка, а живая строка: см. src/components/Thinking.tsx. */}
          {typing ? <BubbleIn mine={false} fresh><Thinking /></BubbleIn> : null}
          {signIn ? (
            <View style={{ alignItems: 'flex-start' }}>
              <GlassPill tone="dark" small style={{ height: 40 }} label={BUDDY.signInBtn()} onPress={() => router.navigate('/auth')} />
            </View>
          ) : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          {/* Поле — «Chat/Composer» (💣 UI, 6164:19536): стекло 48, отправка стеклянным кругом 44. */}
          <GlassSurface tone="light" radius={999}
            style={[s.field, voice.phase === 'idle' && draft.trim() ? s.fieldSending : null]}>
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
              <SendArrow onPress={submit} disabled={busy} />
            ) : (
              <VoiceMessageControl voice={voice} />
            )}
          </GlassSurface>
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
  /*
    ЛИСТ GR.03 ПО ВИДУ, НО С ЗАТЕЕЙ ВНУТРИ — решение владельца 04.10.2026: «поп-ап, и там есть
    предположительное название интента, как это было раньше».
    В волне 1 борда (03.10) лист повторял кадр дословно: общий вопрос «Turn this into an intent?»
    без названия. Это отняло у человека главное — увидеть, ЧТО Kleal понял, до того как соглашаться.
    Человек соглашается на затею, а не на «интент», поэтому вопрос листа — её название (как на
    карточке: «Поговорить про кофе», «Падел»), а пояснение — что Kleal предлагает сделать.
    Лист открыт кнопкой «Create» без распознанной затеи — тогда вопрос и пояснение с кадра.
  */
  return (
    <Sheet visible={open} onClose={onKeep} title={SHEET.title()} bottomInset={Math.max(bottomInset, 18)} grip>
      {title
        ? <SheetText lead={title} note={what || SHEET.note()} />
        : <SheetText lead={SHEET.ask()} note={SHEET.note()} />}
      <GlassPill tone="brand" style={sh.btn} label={SHEET.create()} onPress={onCreate} />
      <GlassPill tone="dark" style={sh.btn} label={SHEET.keep()} onPress={onKeep} />
    </Sheet>
  );
}

/**
 * «Create» в шапке GR.02: стеклянная пилюля 44 с переливом — зелёное, мятное и голубое пятна под
 * стеклом («Mesh · blurred blobs»). Пятна — готовая картинка, собранная из их координат, цветов и
 * размытия на кадре: размытие слоя кодом на Android не повторить (expo-blur там не размывает).
 */
/**
 * ПЕРЕЛИВ «Create» (просьба владельца 09.10): три мягких пятна — мятное, голубое, розово-сиреневое —
 * медленно ходят по кругу под стеклом с разной скоростью, и кнопка переливается, как мыльный пузырь.
 * Один таймер на все три (фазы разные), UI-поток reanimated. «Уменьшить движение» — пятна стоят.
 */
/*
  КОРАЛЛОВЫЙ ПЕРЕЛИВ (Иван, 18.10.2026: «сделай больше кораллового переливания»). Основа — коралл бренда
  и его светлые родственники (розовый, персиковый); мята и голубой остались маленькими бликами, а не
  основой. Тона светлые: тёмный текст «Создать» должен читаться поверх любого из них.
*/
const BLOBS = [
  { c: '#FF9DB1', x: 24, y: 16, r: 36, ax: 26, ay: 8, k: 1, ph: 0, o: 0.8 },
  { c: '#FFC6A8', x: 82, y: 28, r: 36, ax: 24, ay: 9, k: 1, ph: 2.1, o: 0.8 },
  { c: '#FF7A94', x: 55, y: 24, r: 28, ax: 34, ay: 10, k: 2, ph: 4.2, o: 0.55 },
  { c: '#BDF2DA', x: 40, y: 8, r: 14, ax: 30, ay: 6, k: 1, ph: 1.0, o: 0.6 },
  { c: '#CDE7FF', x: 92, y: 36, r: 12, ax: 22, ay: 6, k: 2, ph: 3.3, o: 0.55 },
];

function Iridescence() {
  const reduce = useReducedMotion();
  // Чат с Kleal остаётся в стопке под другими экранами, и вечный перелив продолжал там крутиться: замер
  // 17.10 — +12 пунктов процессора на всех экранах после захода в чат. Не в фокусе — стоит.
  const focused = useIsFocused();
  const t = useSharedValue(0);
  useEffect(() => {
    if (reduce || !focused) { cancelAnimation(t); return; }
    t.value = withRepeat(withTiming(t.value + 1, { duration: 7000, easing: REasing.linear }), -1, false);
    return () => cancelAnimation(t);
  }, [reduce, focused, t]);
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { overflow: 'hidden', borderRadius: 22 }]}>
      {BLOBS.map((b, i) => <Blob key={i} b={b} t={t} />)}
    </View>
  );
}

function Blob({ b, t }: { b: (typeof BLOBS)[number]; t: SharedValue<number> }) {
  const st = useAnimatedStyle(() => {
    const a = t.value * Math.PI * 2 * b.k + b.ph;
    return { transform: [{ translateX: Math.sin(a) * b.ax }, { translateY: Math.cos(a) * b.ay }] };
  });
  const d = b.r * 2;
  return (
    <Animated.View style={[{ position: 'absolute', left: b.x - b.r, top: b.y - b.r, width: d, height: d, opacity: b.o }, st]}>
      <Svg width={d} height={d}>
        <SvgDefs>
          <SvgRadial id={`ir${b.c}`} cx="50%" cy="50%" rx="50%" ry="50%">
            <SvgStop offset="0" stopColor={b.c} stopOpacity={0.95} />
            <SvgStop offset="1" stopColor={b.c} stopOpacity={0} />
          </SvgRadial>
        </SvgDefs>
        <SvgCircle cx={b.r} cy={b.r} r={b.r} fill={`url(#ir${b.c})`} />
      </Svg>
    </Animated.View>
  );
}

function CreatePill({ label, onPress }: { label: string; onPress: () => void }) {
  const p = usePress(0.97);
  return (
    <Animated.View style={[s.createShadow, p.style]}>
      <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress}
        onPressIn={p.onPressIn} onPressOut={p.onPressOut} hitSlop={6}>
        <GlassSurface tone="light" radius={22} pointerEvents="none" style={s.createBtn}>
          {/* Под пятнами — коралловая подложка; прежняя мятно-голубая картинка осталась лёгким отсветом. */}
          <View style={s.createCoral} />
          <Image source={require('../assets/art/buddy/create-mesh.png')} style={[s.createMesh, { opacity: 0.22 }]} resizeMode="stretch" />
          <Iridescence />
          <LogoFace size={24} />
          <Text style={s.createText}>{label}</Text>
        </GlassSurface>
      </Pressable>
    </Animated.View>
  );
}

// ============================================================ вид
// Всё ниже — оформление UX-каркаса: цвета и размеры берутся из токенов темы, своих значений тут
// нет. При натягивании UI меняется этот блок, логика выше остаётся.

const s = StyleSheet.create({
  /** «App Bar · Fixed»: поля 16, ряд 44, под шапкой 6. */
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: 6, gap: 8 },
  /** Подложка кадра — ровный «Ambient · glass pilot» #F5F1EC, без цветных пятен. */
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  slot: { width: 111, flexDirection: 'row', alignItems: 'center', gap: 8 },
  slotRight: { justifyContent: 'flex-end' },
  title: { flex: 1, textAlign: 'center', color: color.fg } as any,
  createShadow: {
    borderRadius: 22,
    ...Platform.select({
      ios: { shadowColor: '#0A0A14', shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
      default: {},
    }),
  },
  createBtn: {
    width: 111, height: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    paddingHorizontal: 16,
  },
  createMesh: { ...StyleSheet.absoluteFill, width: 111, height: 44 } as any,
  createCoral: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(255,170,185,0.35)' } as any,
  /** «Create» — TASA 600 15/18, как подпись кнопки на кадре. */
  createText: { fontFamily: font.displaySemi, fontSize: 15, lineHeight: 18, color: color.fg } as any,

  /** «Chat Content»: поля 12/16/24/16, между репликами 14. */
  thread: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 24, gap: 14 },
  rowMe: { alignItems: 'flex-end', gap: 4 },
  rowThem: { alignItems: 'flex-start', gap: 4 },
  /** Пузырь 260 из 358 (Chat/Message): 73% ленты. Поля 12/16. */
  bub: { paddingVertical: 12, paddingHorizontal: 16 },
  bubMe: { borderBottomRightRadius: 4 },
  bubThem: { borderBottomLeftRadius: 4 },
  /** Тени борда: под своим — коралловое свечение, под ответом — контактная 0/1·2. */
  shadowMe: {
    maxWidth: '73%',
    shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 16, shadowOffset: { width: 0, height: 6 },
  },
  shadowThem: {
    maxWidth: '73%',
    shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 2, shadowOffset: { width: 0, height: 1 },
  },
  bubText: { fontFamily: font.text, fontSize: 15, lineHeight: 22, color: color.fg } as any,
  /** Время под репликой — Geist 11/16 #8A8F96, поля 7 сверху (time-container). */
  time: { fontFamily: font.text, fontSize: 11, lineHeight: 16, color: '#8A8F96', marginTop: 3 } as any,
  timeMe: { textAlign: 'right' } as any,

  /** Док «Chat/Composer»: поля 16. Меню у разговора с Kleal нет, поэтому поле во всю ширину. */
  dock: { paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.ambientBase },
  field: {
    height: 48, flexDirection: 'row', alignItems: 'center', paddingLeft: 16, paddingRight: 12, gap: space.sm,
  },
  /** С текстом справа 4: круг отправки 40 стоит у края поля (send · 40, поля поля 4). */
  fieldSending: { paddingRight: 4 },
  input: { flex: 1, color: color.fg, fontFamily: font.text, fontSize: 15, paddingVertical: 0 } as any,
});

const sh = StyleSheet.create({
  btn: { height: 48 },
});
