/**
 * Онбординг — кадры A.04–A.13.
 *
 * Устройство экрана взято с борда и отличается от того, как это было сделано в вебе:
 *
 *  — Шапка «Creating Profile» с процентом справа и тонкой полосой прогресса под ней.
 *  — Реплики — пузыри со временем; свои справа красным, агента слева серым.
 *  — Виджеты (чипы, кольцо возраста, карта) живут ВНУТРИ ленты, под репликой агента, а не в
 *    отдельном доке снизу. Лента прокручивается вместе с ними.
 *  — Внизу композер «Message…» с микрофоном. Это не украшение: на любом шаге можно ответить
 *    словами вместо нажатия, текст уходит в /api/onboarding/chat, и агент сам разбирает ответ и
 *    правит профиль. Виджет — быстрый путь, разговор — основной.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Alert, Platform, ActivityIndicator, Image, TextInput,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { squarePhoto } from '../src/photo';
import {
  STEP_PROGRESS, HEADER_TITLE, STEP_START, STEP_BASICS, SEXES, sexLabel,
  STEP_AREA, STEP_LANGUAGES, LANGS, langLabel, langPlain, STEP_HOBBIES,
  STEP_PHOTO, StepId, resumeStep, hasProgress, RESUME,
  OWN_INPUT, parseName } from '../src/onboarding';
import { interestLabel, registerInterestLabels } from '../src/interest-label';
import { useLang, T, getLang , replyLang } from '../src/i18n';
import { useOnb, set, get, patch, reset, profileForAttach, mergeProfile, getState } from '../src/state';
import { onboarding, agent, buddy as buddyApi } from '../src/api';
import { AgeDial } from '../src/components/AgeDial';
import { AreaPicker, Area, DEFAULT_AREA } from '../src/components/AreaPicker';
import { ChatShell, BotLine, chatStyles as cs } from '../src/components/ChatShell';
import { InterestDeck } from '../src/components/InterestDeck';
import { deckFor } from '../src/interests-deck';
import { GlassChip, GlassPill } from '../src/components/Glass';
import { IconCheckCircle } from '../src/components/icons';
import { color, radius as rad, type } from '../src/theme';

type Msg = { who: 'bot' | 'me'; text: string; at: string; photo?: string };
/** Реплика в истории, которая уходит модели. Отличается от Msg: у неё роль, а не сторона экрана. */
type Msg2 = { role: string; content: string };

/** Порядок шагов — он же список допустимых значений для входа по ссылке. */
const ORDER: StepId[] = ['start', 'basics', 'area', 'languages', 'hobbies', 'photo'];

const now = () =>
  new Date().toLocaleTimeString(getLang() === 'ru' ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: getLang() !== 'ru',
  });

export default function Chat() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const scroller = useRef<ScrollView>(null);
  /**
   * Вход с конкретного шага — из профиля («Добавить интересы»). Без него кнопка вела просто в
   * /chat, онбординг продолжал с того места, где человек остановился, и предложение добавить
   * интересы заканчивалось просьбой сделать фото.
   *
   * `back` — куда вернуться, когда с этим шагом закончено. Пусто = обычный онбординг, дальше по
   * сценарию.
   */
  const params = useLocalSearchParams<{ step?: string; back?: string }>();
  const entry = ORDER.includes(String(params.step) as StepId) ? (String(params.step) as StepId) : null;
  const back = params.back ? String(params.back) : '';

  const [thread, setThread] = useState<Msg[]>([]);
  const [step, setStep] = useState<StepId>('start');
  const [typing, setTyping] = useState(false);
  /** Нить разговора об увлечениях. Ref, а не состояние: её читает и дописывает обработчик
   *  отправки, перерисовка ей не нужна — на экране живёт общая лента. */
  const hobbyThread = useRef<Msg2[]>([]);
  /**
   * ПОДСКАЗКИ-ОТВЕТЫ к вопросу, который агент только что задал. Тап по подсказке — то же самое,
   * что напечатать её руками: composer остаётся живым, подсказки только избавляют от набора.
   * `fork` — первый ход на входе с профиля: две дороги, пока человек не сказал ничего.
   */
  const [chips, setChips] = useState<string[]>([]);
  const [fork, setFork] = useState(false);
  /**
   * Записанное ЗА ЭТОТ разговор. Раньше под «Записал» показывался весь профиль целиком, и человек,
   * пришедший добавить один интерес, видел ряд из пяти старых — где именно среди них появился
   * новый, было не разобрать. Здесь только то, что агент записал сейчас; всё остальное человек
   * и так видит на экране «Интересы», откуда пришёл.
   */
  const [justAdded, setJustAdded] = useState<string[]>([]);
  // Лента стоит, пока крутят кольцо возраста: иначе один и тот же жест двигает и то, и другое.
  const [dragging, setDragging] = useState(false);
  /*
    СОСТОЯНИЕ КОЛОДЫ ЖИВЁТ ЗДЕСЬ, А НЕ В ВИДЖЕТЕ ШАГА, И ЭТО НЕ ВКУСОВЩИНА.

    ChatShell рисует виджет как `{!typing ? widget : null}` — то есть на каждый ход агента виджет
    СНИМАЕТСЯ и ставится заново. Всё, что он хранил у себя, при этом пропадает. Ровно поэтому здесь
    же лежат `chips`, `justAdded` и `fork`.

    Колода на это наступила: пройденные карточки и признак «заход кончен» были внутри виджета, и
    ответ агента их стирал — карточки возвращались сами и начинали снова с «Бега», по которому
    только что свайпнули. Со стороны это выглядело так, будто кнопка «Записать» не сработала.
  */
  const [deckSeen, setDeckSeen] = useState<string[]>([]);
  const [deckOn, setDeckOn] = useState(true);
  // Номер прохода. Меняется при «Начать заново» и служит ключом виджетам, чтобы те начинали с
  // чистого листа. Иначе внутри них остаётся своё состояние: спрятанные кнопки первого кадра,
  // выбранные увлечения, набранный возраст — всё от предыдущей попытки, которой уже нет.
  const [runId, setRunId] = useState(0);
  const started = useRef(false);

  const say = useCallback((who: 'bot' | 'me', text: string, photo?: string) => {
    setThread((t) => [...t, { who, text, at: now(), photo }]);
  }, []);

  // Первая реплика. Ref, а не состояние: в строгом режиме эффект выполняется дважды, и без
  // защиты приветствие приходит два раза — это видно.
  //
  // Если онбординг уже начинали — продолжаем с нужного шага, а не с первого вопроса. Раньше здесь
  // всегда задавался вопрос из A.04, а виджет под ним прятался, потому что имя уже было: человек
  // возвращался и получал вопрос без единой кнопки под ним.
  useEffect(() => {
    if (started.current) return;
    // Онбординг уже пройден, а сюда попали не за конкретным шагом — значит это перезапуск
    // приложения, а не продолжение анкеты. Expo Go после обновления открывает последний маршрут,
    // и человек, давно закончивший, каждый раз оказывался на шаге фото.
    if (st.done && !entry) { router.replace('/home'); return; }
    started.current = true;
    // Явный вход не «продолжает с того места»: человек пришёл за конкретной вещью.
    const resumed = !entry && hasProgress(st.profile);
    const at = entry || resumeStep(st.profile);
    setStep(at);
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      if (resumed) {
        say('bot', RESUME.line(st.profile.name || ''));
        const line =
          at === 'basics' ? STEP_BASICS.bot()
          : at === 'area' ? STEP_AREA.bot()
          : at === 'languages' ? STEP_LANGUAGES.bot()
          : at === 'hobbies' ? STEP_HOBBIES.bot()
          : STEP_PHOTO.ask();
        setTimeout(() => say('bot', line), 700);
      } else if (entry) {
        // Вход с экрана интересов — единственное место, где человек уже сказал «хочу добавить»,
        // но ещё не сказал ЧТО. Здесь и стоит развилка: первой репликой предлагаем обе дороги.
        if (entry === 'hobbies') setFork(true);
        say('bot',
          entry === 'hobbies' ? STEP_HOBBIES.forkBot()
          : entry === 'languages' ? STEP_LANGUAGES.bot()
          : entry === 'area' ? STEP_AREA.bot()
          : entry === 'basics' ? STEP_BASICS.bot()
          : STEP_START.ask());
      } else {
        // Знакомство идёт первым: человек должен понять, куда попал, прежде чем его о чём-то просят.
        say('bot', STEP_START.intro());
        setTimeout(() => say('bot', STEP_START.ask()), 1400);
      }
    }, 500);
  }, [say]);

  /** Начать онбординг заново. Спрашиваем: это стирает всё, что человек уже ввёл. */
  const restart = () => {
    const wipe = () => {
      reset();
      setThread([]);
      setStep('start');
      setDeckSeen([]);
      setDeckOn(true);
      setRunId((n) => n + 1);
      started.current = false;
      setTyping(true);
      setTimeout(() => {
        setTyping(false);
        say('bot', STEP_START.intro());
        setTimeout(() => say('bot', STEP_START.ask()), 1400);
        started.current = true;
      }, 400);
    };
    if (Platform.OS === 'web') {
      // Alert.alert на вебе не показывает кнопок — там это window.confirm.
      // eslint-disable-next-line no-alert
      if (typeof confirm === 'function' && confirm(RESUME.restartAsk())) wipe();
      return;
    }
    Alert.alert(RESUME.restartAsk(), undefined, [
      { text: RESUME.restartNo(), style: 'cancel' },
      { text: RESUME.restartYes(), style: 'destructive', onPress: wipe },
    ]);
  };

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [thread.length, typing, step]);

  const botAfter = (text: string, ms = 650) => {
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      say('bot', text);
    }, ms);
  };

  const goto = (next: StepId, botLine: string) => {
    setStep(next);
    botAfter(botLine);
  };


  /**
   * ВЫХОД С ШАГА УВЛЕЧЕНИЙ. Имя историческое: раньше отсюда выходили из воронки-расспроса,
   * которая шла после сетки чипов. Сетки и воронки больше нет — запись происходит в самом
   * разговоре, — а выход остался тем же и по тем же причинам.
   */
  /**
   * Развилка на входе с экрана интересов. «Знаю, чем» реплики не оставляет — человек ничего не
   * сказал, и пузырь с текстом кнопки потом читался бы как его слова; оно просто убирает кнопки
   * и оставляет композер. «Помоги разобраться» отправляет обычную реплику: дальше работает тот
   * же разговор, только начатый с честного «не знаю».
   */
  //
  // БЕЗ useCallback, И ЭТО ВАЖНО. Обёрнутый с пустыми зависимостями, он захватывал `send` из
  // ПЕРВОГО рендера — а там `step` ещё 'start', потому что setStep('hobbies') происходит в
  // эффекте уже после. Тап уводил в ветку онбординга: реплика человека появлялась, а до ручки
  // интересов дело не доходило, и человек оставался перед своим же сообщением без ответа.
  // Экономить здесь нечего: функция дешёвая, а устаревшее замыкание стоило трёх кругов проверок.
  const onFork = (which: 'know' | 'help') => {
    setFork(false);
    if (which === 'help') send(STEP_HOBBIES.forkHelpSaid());
  };

  const leaveFunnel = () => {
    // Пришли из профиля — туда и возвращаемся. Не `replace`: тот подменял только верхний экран,
    // а приславший ОСТАВАЛСЯ в стопке под разговором — и человек получал ДВЕ копии «Интересов»
    // подряд, из которых надо было выходить дважды. `dismissTo` снимает разговор и возвращает к
    // тому экрану, который уже открыт.
    if (back) { router.dismissTo(back as any); return; }
    setStep('photo');
    botAfter(STEP_PHOTO.greet(st.profile.name || ''));
    setTimeout(() => say('bot', STEP_PHOTO.ask()), 1900);
  };

  /** Свободный текст — сюда отвечает модель, а не сценарий. Поле ввода живёт в Composer. */
  const send = async (text: string) => {
    say('me', text);

    // ШАГ УВЛЕЧЕНИЙ: сказанное разбирает сервер, а не клиент.
    //
    // Раньше написанное падало в профиль КАК ЕСТЬ — сырой строкой на языке ввода, потому что
    // разбирать было нечем. Теперь один вызов на ход отдаёт и реплику, и записанное: ключ уже
    // английский (им ищет матчинг), подпись — слова человека, и каждый интерес подтверждён
    // цитатой из его же реплики.
    if (step === 'hobbies') {
      const next: Msg2[] = [...hobbyThread.current, { role: 'user', content: text }];
      hobbyThread.current = next;
      setChips([]);            // подсказка к прошлому вопросу поверх нового — обман
      setTyping(true);
      try {
        // Записанное уходит на сервер: по нему он опознаёт уточнение (и просит заменить, а не
        // добавить второй чип) и не предлагает то, что уже отмечено.
        const cur0: string[] = get('interests.explicit') || [];
        const recorded = cur0.map((k) => ({ key: k, label: interestLabel(k) }));
        const r = await buddyApi.interestsChat(next as any, profileForAttach(), replyLang(), recorded);
        setTyping(false);
        // ПУСТОЙ ОТВЕТ ТОЖЕ НАДО ОЗВУЧИТЬ. Раньше пустая реплика молча не показывалась ничем, и
        // человек оставался перед собственным сообщением: ни ответа, ни ошибки, ни признака
        // работы. Поймано на скриншоте живого экрана. Сервер почти всегда что-то отвечает —
        // значит сюда доехал сбой связи или чужой ответ, и об этом надо сказать вслух.
        const reply = String(r?.reply || '')
          || T('Что-то я замолчал. Повтори, пожалуйста?', 'I went quiet there. Say that again?');
        say('bot', reply);
        hobbyThread.current = [...next, { role: 'assistant', content: reply }];
        setChips(Array.isArray((r as any)?.chips) ? (r as any).chips.map(String) : []);
        const added = Array.isArray(r?.added) ? r!.added! : [];
        if (added.length) {
          // УТОЧНЕНИЕ ЗАМЕНЯЕТ, А НЕ ДОБАВЛЯЕТ. «рыбалка» -> «рыбалка на море» это один интерес,
          // ставший точнее; без этого на экране копились три чипа про одно и то же.
          let cur: string[] = get('interests.explicit') || [];
          for (const a of added) {
            const key = String(a.key || '').trim();
            if (!key) continue;
            const old = String(a.replaces || '').trim();
            if (old) cur = cur.filter((x) => x !== old);
            if (!cur.includes(key)) cur = [...cur, key];
          }
          set('interests.explicit', cur);
          setJustAdded((p) => {
            const keys = added.map((a) => String(a.key || '').trim()).filter(Boolean);
            const gone = added.map((a) => String(a.replaces || '').trim()).filter(Boolean);
            const kept = p.filter((k) => !gone.includes(k) && !keys.includes(k));
            return [...kept, ...keys];
          });
          // Подпись — слова человека. Кладём в тот же реестр, куда сгружаются словари сервера,
          // иначе до следующего чтения профиля чип показывал бы английский ключ.
          const lang = getLang();
          registerInterestLabels(
            Object.fromEntries(added.map((a) => [String(a.key), String(a.label || a.key)])), lang
          );
        }
      } catch {
        setTyping(false);
        say('bot', T('Связь на секунду пропала. Повторишь?', 'I lost the connection for a second. Say that again?'));
      }
      return;
    }

    // На шаге имени ответ РАЗБИРАЕТСЯ. Раньше здесь стояло «что написали, то и имя» — и человек,
    // ответивший «называй меня Иван», становился «называй меня иван»: под этим именем его видели
    // в поиске и к нему обращался агент. Заодно из «Иван Петров» достаётся фамилия.
    if (step === 'start' && !st.profile.name) {
      const parsed = parseName(text);
      if (parsed.name) set('name', parsed.name);
      if (parsed.surname) set('surname', parsed.surname);
      goto('basics', STEP_BASICS.bot());
      return;
    }

    // Шаги, у которых свой разбор, вернулись выше. Сюда доходит текст на шагах, где ответа от
    // модели не ждут (возраст, область, языки, фото): там ведёт виджет, а написанное — мимо.
  };

  // Процент — это «сколько пройдено онбординга». Для того, кто зашёл из профиля дополнить одну
  // вещь, число не значит ничего, поэтому полосы там просто нет.
  const pct = entry ? null : (STEP_PROGRESS[step] ?? 0);

  return (
    <ChatShell
      ref={scroller}
      title={HEADER_TITLE()}
      pct={pct}
      thread={thread}
      typing={typing}
      onBack={() => router.back()}
      onSend={send}
      scrollEnabled={!dragging}
      headerExtra={
        hasProgress(st.profile) ? (
          <Pressable accessibilityRole="button" onPress={restart} hitSlop={10}>
            <Text style={s.restart}>{RESUME.restart()}</Text>
          </Pressable>
        ) : null
      }
      widget={
        <StepWidget
          key={runId}
          step={step}
          say={say}
          goto={goto}
          onDrag={setDragging}
          onDone={() => router.navigate('/summary')}
          leave={leaveFunnel}
          fork={fork}
          chips={chips}
          added={justAdded}
          onFork={onFork}
          onChip={send}
          deckSeen={deckSeen}
          deckOn={deckOn}
          onDeckMore={() => setDeckOn(true)}
          onDeckPass={(picked: string[], seen: string[]) => {
            setDeckSeen((p) => [...p, ...seen]);
            setDeckOn(false);
            // В разговор уходит ОДНА реплика на весь заход — так агент отвечает один раз и по
            // всему списку сразу, а не вопросом на каждую карту.
            if (picked.length) send(picked.join(', '));
          }}
          onDrop={(k: string) => setJustAdded((p) => p.filter((x) => x !== k))}
        />
      }
    />
  );
}

// ============================================================ виджеты шагов

/**
 * Поле «своё» рядом с чипами. Отдельный компонент, потому что нужен и увлечениям, и языкам, и в
 * обоих местах правило одно: пустое не добавляем, повтор не добавляем, после добавления поле
 * закрывается — иначе непонятно, сработало ли.
 */
function OwnField({ placeholder, onAdd }: { placeholder: string; onAdd: (v: string) => void }) {
  const [v, setV] = useState('');
  const add = () => {
    const t = v.trim();
    if (!t) return;
    setV('');
    onAdd(t);
  };
  return (
    <View style={s.ownRow}>
      <TextInput
        style={s.ownInput}
        value={v}
        onChangeText={setV}
        placeholder={placeholder}
        placeholderTextColor={color.neutral400}
        onSubmitEditing={add}
        returnKeyType="done"
        autoFocus
        accessibilityLabel={placeholder}
      />
      <Pressable accessibilityRole="button" style={s.ownAdd} onPress={add}>
        <Text style={s.ownAddText}>{OWN_INPUT.add()}</Text>
      </Pressable>
    </View>
  );
}

function StepWidget({
  step, say, goto, onDone, onDrag, leave, fork, chips, added, onFork, onChip, onDrop,
  deckSeen, deckOn, onDeckMore, onDeckPass,
}: {
  step: StepId;
  say: (who: 'bot' | 'me', text: string, photo?: string) => void;
  goto: (s: StepId, line: string) => void;
  onDone: () => void;
  onDrag: (dragging: boolean) => void;
  /** Выход с шага увлечений: в профиль, откуда пришли, или дальше по онбордингу. */
  leave: () => void;
  /** Развилка первым ходом: две дороги, пока человек ничего не сказал. */
  fork?: boolean;
  /** Подсказки-ответы к последнему вопросу агента. Тап равен набору руками. */
  chips?: string[];
  /** Записанное за ЭТОТ разговор — не весь профиль. */
  added?: string[];
  onFork?: (which: 'know' | 'help') => void;
  onChip?: (text: string) => void;
  onDrop?: (key: string) => void;
  /** Карточки, по которым уже провели пальцем за этот разговор. Живёт в экране — см. там почему. */
  deckSeen: string[];
  deckOn: boolean;
  onDeckMore: () => void;
  onDeckPass: (picked: string[], seen: string[]) => void;
}) {
  const st = useOnb();

  if (step === 'start') return <StartW say={say} goto={goto} />;
  if (step === 'basics') return <BasicsW say={say} goto={goto} onDrag={onDrag} />;
  // onDrag — не косметика: пока палец тащит булавку по карте, лента анкеты обязана молчать,
  // иначе ScrollView забирает вертикальный жест себе и точка дёргается на месте.
  if (step === 'area') return <AreaW say={say} goto={goto} onDrag={onDrag} />;
  if (step === 'languages') return <LangW say={say} goto={goto} />;
  if (step === 'hobbies') return (
    <HobbyW say={say} leaveFunnel={leave} fork={fork} chips={chips} added={added}
            onFork={onFork} onChip={onChip} onDrop={onDrop} onDrag={onDrag}
            deckSeen={deckSeen} deckOn={deckOn} onDeckMore={onDeckMore} onDeckPass={onDeckPass} />
  );
  if (step === 'photo') return <PhotoW say={say} onDone={onDone} name={st.profile.name || ''} />;
  return null;
}

function Hint({ children }: { children: React.ReactNode }) {
  return <Text style={cs.hint}>{children}</Text>;
}

/*
  Чип и главная кнопка шага — из общего стеклянного набора, а не свои. Своих было ровно два вида на
  весь онбординг, и оба разошлись бы с экранами входа при первой же правке: там уже стекло, здесь
  ещё плоские плашки. Обёртки оставлены, чтобы не править полсотни мест вызова.
*/
function Chip({ label, on, onPress }: { label: string; on?: boolean; onPress?: () => void }) {
  return <GlassChip label={label} on={on} onPress={onPress} />;
}

function Cta({ label, onPress, disabled, kind = 'primary' }: {
  label: string; onPress?: () => void; disabled?: boolean; kind?: 'primary' | 'dark' | 'muted';
}) {
  return (
    <GlassPill
      label={label}
      onPress={onPress}
      disabled={disabled}
      tone={kind === 'primary' ? 'brand' : kind === 'dark' ? 'dark' : 'light'}
      style={s.cta}
    />
  );
}

/** A.04 — согласие, потом имя. Имя человек пишет в композер: так на борде. */
function StartW({ say }: any) {
  const st = useOnb();
  const [asked, setAsked] = useState(false);
  const [gone, setGone] = useState(false);

  // Нажатая кнопка должна исчезать — как на всех остальных шагах, где виджет уступает место
  // следующему вопросу. Здесь шаг не меняется (имя человек пишет в композер), поэтому прятать
  // приходится вручную: «Зачем это нужно?» уходит, как только на него ответили, а «Поехали!»
  // забирает с собой весь виджет. Без этого «Поехали!» жалось повторно, и агент каждый раз заново
  // спрашивал имя, будто не услышал.
  if (gone || st.profile.name) return null;

  return (
    <View style={cs.widget}>
      <Hint>{STEP_START.hint()}</Hint>
      <View style={cs.row}>
        {asked ? null : (
          <Chip
            label={STEP_START.why()}
            onPress={() => {
              setAsked(true);
              say('me', STEP_START.why());
              setTimeout(() => say('bot', STEP_START.whyAnswer()), 600);
            }}
          />
        )}
        <Chip
          label={STEP_START.go()}
          on
          onPress={() => {
            setGone(true);
            say('me', STEP_START.go());
            setTimeout(() => say('bot', STEP_START.askName()), 600);
          }}
        />
      </View>
    </View>
  );
}

/** A.05 — кольцо возраста и пол. */
function BasicsW({ say, goto, onDrag }: any) {
  const [age, setAge] = useState(28);
  const [sex, setSex] = useState<string | null>(null);
  return (
    <View style={cs.widget}>
      <Text style={cs.label}>{STEP_BASICS.ageLabel()}</Text>
      <AgeDial value={age} onChange={setAge} onDragChange={onDrag} />
      <Text style={cs.label}>{STEP_BASICS.sexLabel()}</Text>
      <View style={cs.row}>
        {SEXES.map(([k]) => (
          <Chip key={k} label={sexLabel(k)} on={sex === k} onPress={() => setSex(k)} />
        ))}
      </View>
      <Cta
        label={STEP_BASICS.cta()}
        disabled={!sex}
        onPress={() => {
          set('age', age);
          // «Any is fine» — это не пол, а отсутствие предпочтения. В профиль он не пишется,
          // иначе матчинг получит «Any» как значение и станет искать людей с таким полом.
          if (sex && sex !== 'Any') set('gender', sex);
          say('me', `${age}, ${sexLabel(sex!)}`);
          goto('area', STEP_AREA.bot());
        }}
      />
    </View>
  );
}

/** A.06 — страна, город, радиус, карта. */
function AreaW({ say, goto, onDrag }: any) {
  const [area, setArea] = useState<Area>(DEFAULT_AREA);
  return (
    <View style={cs.widget}>
      <AreaPicker value={area} onChange={setArea} onDragChange={onDrag} />
      <Cta
        label={STEP_AREA.cta()}
        onPress={() => {
          // В профиль уезжает ГОРОД, а не страна: §5.3 матчинга читает ctx.city, и «Spain» там
          // означало поиск по стране целиком, а в карточке кандидата вместо города стояло
          // название государства. Страна лежит отдельным полем — сервер знает `country`.
          set('city', area.city);
          set('country', area.country);
          // Точку двигали — «свой район» это адрес с карты, а не название города из списка.
          set('geo.comfortableAreas', [area.address || area.city]);
          set('geo.located', true);
          set('geo.coarseLat', area.lat);
          set('geo.coarseLon', area.lon);
          set('geo.maxDistanceKm', area.km);
          say('me', `${area.address || area.city}, ${area.country} · ${area.km} km`);
          goto('languages', STEP_LANGUAGES.bot());
        }}
      />
    </View>
  );
}

/** A.07 — языки с флагами. */
function LangW({ say, goto }: any) {
  const [ownOpen, setOwnOpen] = useState(false);
  const [sel, setSel] = useState<string[]>([]);
  const toggle = (k: string) => setSel((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));

  // Свой язык — тот, которого нет в готовом списке. Показывается отдельным чипом и зажжённым,
  // ровно как свой интерес шагом ниже: без этого человек писал «каталанский», чип не появлялся,
  // и добавление выглядело как несработавшее — при том что язык уже был в выборе.
  const own = sel.filter((k) => !LANGS.some(([l]) => l === k));

  return (
    <View style={cs.widget}>
      <Hint>{STEP_LANGUAGES.hint()}</Hint>
      <View style={cs.row}>
        {LANGS.map(([k]) => (
          <Chip key={k} label={langLabel(k)} on={sel.includes(k)} onPress={() => toggle(k)} />
        ))}
        {own.map((k) => (
          <Chip key={k} label={k} on onPress={() => toggle(k)} />
        ))}
        <Chip label={'+ ' + STEP_LANGUAGES.own()} onPress={() => setOwnOpen((o) => !o)} />
      </View>

      {/* Своё поле — та же причина, что и у увлечений: курсор в композере снизу на телефоне не виден. */}
      {ownOpen ? (
        <OwnField
          placeholder={OWN_INPUT.langPlaceholder()}
          onAdd={(v) => {
            setSel((p) => (p.includes(v) ? p : [...p, v]));
            setOwnOpen(false);
          }}
        />
      ) : null}
      <Cta
        label={STEP_LANGUAGES.cta()}
        disabled={!sel.length}
        onPress={() => {
          set('languages.comfortable', sel);
          say('me', sel.map(langPlain).join(', '));
          goto('hobbies', STEP_HOBBIES.bot());
        }}
      />
    </View>
  );
}

/** A.08 — увлечения с эмодзи. */
function HobbyW({ say, leaveFunnel, fork, chips, added, onFork, onChip, onDrop, onDrag,
                 deckSeen, deckOn, onDeckMore, onDeckPass }: any) {
  const st = useOnb();
  const [busy, setBusy] = useState(false);
  /*
    ПРОЙДЕННОЕ И ПРИЗНАК «ЗАХОД КОНЧЕН» ПРИХОДЯТ СВЕРХУ, А НЕ ХРАНЯТСЯ ЗДЕСЬ. Этот виджет снимают
    с экрана на каждый ход агента (`{!typing ? widget : null}` в ChatShell), и всё своё он теряет.
    Разбор — в комментарии к `deckSeen` в самом экране.
  */
  const done: string[] = deckSeen || [];
  // Показываем записанное ЗА ЭТОТ разговор. Всё, что было в профиле раньше, человек видит на
  // экране «Интересы», откуда пришёл; повторять его здесь значит прятать новое среди старого.
  const explicit: string[] = added || [];
  const hasAny: boolean = !!(st.profile.interests?.explicit || []).length;

  // РАЗВИЛКА ПЕРВЫМ ХОДОМ. Пока человек не выбрал и ничего не рассказал — две кнопки. Дальше
  // работает обычный разговор: он пишет сам, а подсказки только избавляют от набора.
  if (fork) {
    return (
      <View style={cs.widget}>
        <View style={cs.row}>
          <Chip label={STEP_HOBBIES.forkKnow()} onPress={() => onFork('know')} />
          <Chip label={STEP_HOBBIES.forkHelp()} on onPress={() => onFork('help')} />
        </View>
      </View>
    );
  }

  // Снятие чипа убирает интерес И из профиля, И из показанного за этот разговор: списка теперь
  // два, и обновить один — значит оставить чип висеть после нажатия.
  const drop = (k: string) => {
    const cur: string[] = get('interests.explicit') || [];
    set('interests.explicit', cur.filter((x) => x !== k));
    onDrop?.(k);
  };

  return (
    <View style={cs.widget}>
      {/* ПОДСКАЗКИ ВЫШЕ ЗАПИСАННОГО. Это ответ на вопрос, который человек читает прямо сейчас,
          а записанное — итог прошлых ходов; порядок на экране повторяет порядок разговора.
          Тап равен набору руками: композер живой, подсказки только избавляют от печати. */}
      {/*
        ПРЕДЛОЖЕННОЕ ИДЁТ КОЛОДОЙ, А НЕ РЯДОМ ЧИПОВ. Чипы просили выбрать: человек читал шесть
        подписей разом, сравнивал и решал, какие «правильные». Карта спрашивает про одну вещь и
        требует одного движения — и на неё отвечают не выбирая, а вспоминая.
        Свайп влево НЕ уходит репликой сразу. Заход набирается молча, и в разговор попадает один
        список по кнопке «Записать» — иначе агент отвечал вопросом на каждую карту и колода уезжала
        вниз за ответом. Пропуск не отправляется вовсе — он местный, просто следующая карта.
        После захода колода уходит с экрана и возвращается только по просьбе: место занимает ответ
        агента, ради которого заход и затевался.

        Колода СТОИТ ВСЕГДА, а не только когда агент что-то предложил: подсказок бывает три-четыре
        за ход, а иногда ни одной, и на пустом шаге человеку было бы не с чем работать. Личные
        подсказки идут первыми, за ними каталог — см. src/interests-deck.ts.
      */}
      {deckOn ? (
        <InterestDeck
          // Ключ по числу пройденных: новый заход собирается заново, с начала нового списка. Без
          // ключа колода осталась бы стоять на старом месте в укоротившемся списке.
          key={done.length}
          items={deckFor(chips, done)}
          onDragChange={onDrag}
          onPass={onDeckPass}
        />
      ) : deckFor(chips, done).length ? (
        // Карточки кончились совсем — звать их обратно не за чем, и кнопки нет.
        <View style={cs.row}>
          <Chip label={STEP_HOBBIES.deckMore()} onPress={onDeckMore} />
        </View>
      ) : null}
      {explicit.length ? (
        <>
          <Text style={cs.hint}>{STEP_HOBBIES.saved()}</Text>
          <View style={cs.row}>
            {explicit.map((k) => (
              <Chip key={k} label={interestLabel(k)} on onPress={() => drop(k)} />
            ))}
          </View>
        </>
      ) : (
        <Text style={cs.hint}>{STEP_HOBBIES.empty()}</Text>
      )}
      <Cta
        label={STEP_HOBBIES.cta()}
        disabled={(!explicit.length && !hasAny) || busy}
        onPress={() => {
          setBusy(true);
          // Запись уже произошла — на каждом ходу разговора. Здесь только выход: в профиль,
          // откуда пришли, или дальше по онбордингу.
          leaveFunnel();
        }}
      />
    </View>
  );
}
function PhotoW({ say, onDone, name }: any) {
  const [uri, setUri] = useState<string | null>(null);
  const [stage, setStage] = useState<'ask' | 'result' | 'confirmed'>('ask');
  const [busy, setBusy] = useState(false);

  /**
   * Фото готовится БЕЗ экрана обрезки.
   *
   * Раньше и камера, и галерея открывались с `allowsEditing: true` — и человек, выбрав снимок,
   * попадал в системный редактор с рамкой и кнопкой «ОБРЕЗАТЬ», без которой фото не принималось.
   * Лишний экран ради квадрата, который мы и сами умеем вырезать: берём центральный квадрат по
   * размерам, которые пикер и так отдал вместе с файлом.
   */
  const shrink = async (a: { uri: string; width?: number; height?: number }) => {
    // Обрезка и сжатие — в src/photo.ts, общие с экраном профиля. Здесь была вторая копия того же
    // кода, и профильная от неё отстала на одну строку: смена фото там молча перестала работать.
    const shot = await squarePhoto(a);
    set('photo', shot.dataUrl);
    set('photoStatus', 'set');
    return shot.uri;
  };

  const take = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return;
    // Без allowsEditing: системный редактор с «ОБРЕЗАТЬ» больше не встаёт между снимком и профилем.
    const r = await ImagePicker.launchCameraAsync({ cameraType: ImagePicker.CameraType.front, quality: 0.9 });
    if (r.canceled || !r.assets?.length) return;
    setBusy(true);
    try { const u = await shrink(r.assets[0]); setUri(u); say('me', '', u); setStage('result'); } finally { setBusy(false); }
  };

  const upload = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.9 });
    if (r.canceled || !r.assets?.length) return;
    setBusy(true);
    try { const u = await shrink(r.assets[0]); setUri(u); say('me', '', u); setStage('result'); } finally { setBusy(false); }
  };

  if (stage === 'ask') {
    return (
      <View style={cs.widget}>
        <Hint>{STEP_PHOTO.hint()}</Hint>
        <Cta label={STEP_PHOTO.take()} onPress={take} />
        <Cta label={STEP_PHOTO.upload()} kind="dark" onPress={upload} />
        <Cta
          label={STEP_PHOTO.skip()}
          kind="muted"
          onPress={() => {
            set('photoStatus', 'skipped');
            onDone();
          }}
        />
        {busy ? <ActivityIndicator color={color.primary} /> : null}
      </View>
    );
  }

  if (stage === 'result') {
    return (
      <View style={cs.widget}>
        {uri ? <Image source={{ uri }} style={s.resultPhoto} /> : null}
        <BotLine>{STEP_PHOTO.praise()}</BotLine>
        <Hint>{STEP_PHOTO.pickHint()}</Hint>
        <View style={cs.rowSplit}>
          <View style={{ flex: 1 }}>
            <Cta label={STEP_PHOTO.use()} onPress={() => { say('bot', STEP_PHOTO.confirmed()); setStage('confirmed'); }} />
          </View>
          <View style={{ flex: 1 }}>
            <Cta label={STEP_PHOTO.retake()} kind="muted" onPress={() => { setUri(null); setStage('ask'); }} />
          </View>
        </View>
      </View>
    );
  }

  return (
    <View style={cs.widget}>
      <View style={s.doneCard}>
        {uri ? <Image source={{ uri }} style={s.doneAvatar} /> : <View style={[s.doneAvatar, { backgroundColor: color.neutral100 }]} />}
        <View style={{ flex: 1 }}>
          <Text style={s.doneTitle}>{STEP_PHOTO.cardTitle()}</Text>
          <Text style={s.doneSub}>{STEP_PHOTO.cardSub(name)}</Text>
        </View>
        <IconCheckCircle />
      </View>
      <BotLine>{STEP_PHOTO.next()}</BotLine>
      <Cta label={STEP_PHOTO.cta()} onPress={onDone} />
    </View>
  );
}

/**
 * Здесь остались только стили ВИДЖЕТОВ. Шапка, лента, пузыри и композер живут в ChatShell —
 * ровно один раз на оба чат-экрана, онбординг и создание интента.
 */
const s = StyleSheet.create({
  /** Бровка «Это всё»: тонкая строка под шапкой. Тише ответов в ленте — это выход, а не ответ. */
  brow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    marginHorizontal: 20, marginTop: 10,
    height: 32, borderRadius: rad.full, backgroundColor: color.neutral100,
  },
  browText: { ...type.caption, color: color.muted, fontWeight: '600' } as any,
  browChev: { fontSize: 13, color: color.muted, marginTop: -1 },

  ownRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ownInput: {
    flex: 1, height: 44, borderRadius: rad.full, backgroundColor: color.neutral100,
    paddingHorizontal: 16, color: color.fg, fontSize: 15,
  },
  ownAdd: {
    height: 44, paddingHorizontal: 18, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  ownAddText: { ...type.button, color: color.onPrimary } as any,
  restart: { ...type.caption, color: color.primary } as any,
  /** Высота из борда: главная кнопка шага ниже входной — 48 против 56. */
  cta: { height: 48 },

  resultPhoto: { width: '100%', height: 260, borderRadius: rad.md },
  doneCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: color.card,
    borderRadius: rad.lg, padding: 12,
  },
  doneAvatar: { width: 40, height: 40, borderRadius: 20 },
  doneTitle: { ...type.title, color: color.fg } as any,
  doneSub: { ...type.bodySmall, color: color.muted } as any,
});
