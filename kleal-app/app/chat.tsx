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
import * as ImageManipulator from 'expo-image-manipulator';
import {
  STEP_PROGRESS, HEADER_TITLE, STEP_START, STEP_BASICS, SEXES, sexLabel,
  STEP_AREA, STEP_LANGUAGES, LANGS, langLabel, langPlain, STEP_HOBBIES, HOBBIES, hobbyLabel,
  hobbyPlain, STEP_PHOTO, StepId, resumeStep, hasProgress, RESUME, FUNNEL, FUNNEL_OUT_RE, FUNNEL_MORE_RE,
  OWN_INPUT,
} from '../src/onboarding';
import { useLang, T, getLang , replyLang } from '../src/i18n';
import { useOnb, set, get, patch, reset, profileForAttach, mergeProfile, getState } from '../src/state';
import { onboarding, agent } from '../src/api';
import { AgeDial } from '../src/components/AgeDial';
import { AreaPicker, Area, DEFAULT_AREA } from '../src/components/AreaPicker';
import { ChatShell, BotLine, chatStyles as cs } from '../src/components/ChatShell';
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
  const [funnel, setFunnel] = useState<Msg2[]>([]);
  const [funnelOpts, setFunnelOpts] = useState<string[]>([]);
  const [funnelTurns, setFunnelTurns] = useState(0);
  const [funnelCap, setFunnelCap] = useState(10);
  const [funnelDone, setFunnelDone] = useState(false);
  // Лента стоит, пока крутят кольцо возраста: иначе один и тот же жест двигает и то, и другое.
  const [dragging, setDragging] = useState(false);
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
        say('bot',
          entry === 'hobbies' ? STEP_HOBBIES.bot()
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
      setFunnel([]);
      setStep('start');
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
   * Ход разговора про интересы.
   *
   * Ведёт модель: она задаёт по одному вопросу, сама дописывает профиль и сама предлагает варианты
   * ответа. Здесь только два решения. Первое — когда разговор закончен: агент перестал спрашивать
   * (в реплике нет вопроса и нет вариантов) И сервер сказал funnelComplete. Второе — предохранитель:
   * счётчик ходов, чтобы человек не остался в бесконечном опросе, если модель заладит спрашивать.
   *
   * Бессмыслицу («фцыпфцп») сервер распознаёт и переспрашивает — такой ход НЕ засчитывается, иначе
   * набором мусора можно было бы «доспамить» до кнопки «Продолжить».
   */
  const funnelTurn = async (text?: string, hist?: Msg2[]) => {
    const base = hist || funnel;
    const next = text ? [...base, { role: 'user', content: text }] : base;
    if (text) setFunnel(next);
    setTyping(true);
    try {
      // Профиль уходит БЕЗ фото: это data-URL на сотни килобайт, и на каждом ходу разговора он
      // гонялся бы туда и обратно без всякой пользы — модель его всё равно не видит.
      const r: any = await onboarding.chat({
        messages: next, profile: profileForAttach(), lang: replyLang(),
      });
      setTyping(false);
      const reply = String(r?.reply || '');
      if (reply) {
        say('bot', reply);
        setFunnel([...next, { role: 'assistant', content: reply }]);
      } else {
        setFunnel(next);
      }
      // Слияние, а не замена: подробности в mergeProfile. Замена стирала всё, о чём в ЭТОМ
      // разговоре не заходила речь.
      if (r?.profile && typeof r.profile === 'object') {
        patch({ profile: mergeProfile(getState().profile, r.profile) });
      }
      const opts: string[] = Array.isArray(r?.options) ? r.options.map(String) : [];
      setFunnelOpts(opts);
      const turns = text && !r?.gibberish ? funnelTurns + 1 : funnelTurns;
      setFunnelTurns(turns);
      const asks = reply.includes('?') || opts.length > 0;
      setFunnelDone((!!r?.funnelComplete && !asks) || turns >= funnelCap);
    } catch {
      setTyping(false);
      say('bot', T('Связь на секунду пропала. Повторишь?', 'I lost the connection for a second. Say that again?'));
    }
  };

  /** Разговор начинается сразу после выбора чипов и с той же затравки, что в веб-версии. */
  /**
   * Обогащать интересы по репликам разговора ПЫТАЛИСЬ — и откатили, потому что фильтрация
   * возвращает тему всегда, даже когда её нет. На «Привет, давно этим занимаюсь, мне нравится»
   * она уверенно ответила [hiking, outdoor, leisure], и в профиль живого человека приехали
   * интересы, которых он не заводил: «hello», «enjoy», «long time», «walking». Отсеять это
   * стоп-словами нельзя — выдуманные темы выглядят как настоящие.
   *
   * Правильное место для такой работы — извлечение на сервере (EXTRACT_V2), где модель видит весь
   * разговор и понимает, что «мне нравится» не увлечение. Здесь оставлена только эта запись, чтобы
   * следующий не начал с той же идеи.
   */

  const startFunnel = (picks: string[]) => {
    const seed: Msg2[] = [
      { role: 'assistant', content: FUNNEL.seedBot },
      { role: 'user', content: FUNNEL.seedUser(picks) },
    ];
    setFunnel(seed);
    setFunnelTurns(0);
    setFunnelCap(FUNNEL.cap(picks.length));
    setFunnelOpts([]);
    setFunnelDone(false);
    setStep('funnel');
    funnelTurn(undefined, seed);
  };

  /** Из разговора обратно к чипам — за следующим интересом. */
  const moreInterests = () => {
    setFunnelOpts([]);
    setFunnelDone(false);
    setStep('hobbies');
    botAfter(FUNNEL.back());
  };

  const leaveFunnel = () => {
    setFunnelOpts([]);
    // Пришли из профиля — туда и возвращаемся. replace, а не push: разговор закончен, и «назад»
    // из профиля не должно приводить обратно в него.
    if (back) { router.replace(back as any); return; }
    setStep('photo');
    botAfter(STEP_PHOTO.greet(st.profile.name || ''));
    setTimeout(() => say('bot', STEP_PHOTO.ask()), 1900);
  };

  /** Свободный текст — сюда отвечает модель, а не сценарий. Поле ввода живёт в Composer. */
  const send = async (text: string) => {
    say('me', text);

    // Шаг увлечений: написанное словами — это НОВЫЙ интерес, а не реплика в разговоре. Пока текст
    // уходил в /api/onboarding/chat прямо отсюда, шаг не менялся, и сетка чипов с кнопкой «Дальше»
    // оставалась висеть под каждым вопросом агента. Теперь интерес просто добавляется и загорается
    // рядом с остальными, а разговор начинается по «Дальше».
    if (step === 'hobbies') {
      const key = text.trim();
      const cur: string[] = get('interests.explicit') || [];
      if (key && !cur.includes(key)) set('interests.explicit', [...cur, key]);
      return;
    }

    // На шаге имени ответ разбирать не нужно: что написали, то и имя.
    if (step === 'start' && !st.profile.name) {
      set('name', text);
      goto('basics', STEP_BASICS.bot());
      return;
    }

    setFunnelOpts([]);
    funnelTurn(text);
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
      composerPlaceholder={step === 'funnel' ? FUNNEL.compose() : undefined}
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
          onDone={() => router.push('/summary')}
          startFunnel={startFunnel}
          funnel={{ opts: funnelOpts, done: funnelDone, ask: funnelTurn, leave: leaveFunnel, more: moreInterests }}
        />
      }
    />
  );
}

// ============================================================ виджеты шагов

type FunnelBits = {
  opts: string[];
  done: boolean;
  ask: (text: string) => void;
  leave: () => void;
  more: () => void;
};

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
  step, say, goto, onDone, onDrag, startFunnel, funnel,
}: {
  step: StepId;
  say: (who: 'bot' | 'me', text: string, photo?: string) => void;
  goto: (s: StepId, line: string) => void;
  onDone: () => void;
  onDrag: (dragging: boolean) => void;
  startFunnel: (picks: string[]) => void;
  funnel: FunnelBits;
}) {
  const st = useOnb();

  if (step === 'start') return <StartW say={say} goto={goto} />;
  if (step === 'basics') return <BasicsW say={say} goto={goto} onDrag={onDrag} />;
  // onDrag — не косметика: пока палец тащит булавку по карте, лента анкеты обязана молчать,
  // иначе ScrollView забирает вертикальный жест себе и точка дёргается на месте.
  if (step === 'area') return <AreaW say={say} goto={goto} onDrag={onDrag} />;
  if (step === 'languages') return <LangW say={say} goto={goto} />;
  if (step === 'hobbies') return <HobbyW say={say} startFunnel={startFunnel} leaveFunnel={funnel.leave} />;
  if (step === 'funnel') return <FunnelW {...funnel} say={say} />;
  if (step === 'photo') return <PhotoW say={say} onDone={onDone} name={st.profile.name || ''} />;
  return null;
}

function Hint({ children }: { children: React.ReactNode }) {
  return <Text style={cs.hint}>{children}</Text>;
}

function Chip({ label, on, onPress }: { label: string; on?: boolean; onPress?: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      style={({ pressed }) => [s.chip, on && s.chipOn, pressed && { opacity: 0.85 }]}
    >
      <Text style={[s.chipText, on && { color: color.onPrimary }]}>{label}</Text>
    </Pressable>
  );
}

function Cta({ label, onPress, disabled, kind = 'primary' }: {
  label: string; onPress?: () => void; disabled?: boolean; kind?: 'primary' | 'dark' | 'muted';
}) {
  const bg = kind === 'primary' ? color.primary : kind === 'dark' ? color.ink : color.neutral100;
  const fg = kind === 'muted' ? color.fg : color.onPrimary;
  return (
    <Pressable
      onPress={disabled ? undefined : onPress}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      style={({ pressed }) => [s.cta, { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.9 : 1 }]}
    >
      <Text style={[s.ctaText, { color: fg }]}>{label}</Text>
    </Pressable>
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
          set('geo.comfortableAreas', [area.city]);
          set('geo.located', true);
          set('geo.coarseLat', area.lat);
          set('geo.coarseLon', area.lon);
          set('geo.maxDistanceKm', area.km);
          say('me', `${area.city}, ${area.country} · ${area.km} km`);
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
/**
 * Разговор про интересы — варианты от модели и всегда доступный выход.
 *
 * Свой «Это всё» дорисовывается ТОЛЬКО когда среди предложенных вариантов выхода ещё нет: на
 * закрывающем ходу модель сама предлагает «Это всё», и без этой проверки чип печатался бы дважды.
 * Проверка — тем же выражением, каким сервер узнаёт этот ответ.
 *
 * Пока модель спрашивает, отвечать можно и словами в композере — чипы это ускорение, а не рельсы.
 */
function FunnelW({ opts, done, ask, leave, more, say }: FunnelBits & { say: any }) {
  /**
   * Выход из разговора спрашивается, а не случается. Это единственный шаг, который наполняет
   * профиль, и уйти с него мимоходом — значит остаться с профилем из одного слова. Kleal говорит,
   * что будет дальше, и ждёт ответа.
   */
  const [ending, setEnding] = useState(false);
  const askEnd = () => {
    if (ending) return;
    setEnding(true);
    say('bot', FUNNEL.endAsk());
  };
  if (ending) {
    return (
      <View style={cs.widget}>
        <Cta label={FUNNEL.endNo()} kind="muted" onPress={() => setEnding(false)} />
        <Cta label={FUNNEL.endYes()} onPress={leave} />
      </View>
    );
  }
  // Разговор про этот интерес окончен. Дальше два честных пути, и оба названы: рассказать про
  // следующий интерес или закончить с интересами вовсе. Одна кнопка «Продолжить» не говорила, куда
  // именно продолжает, и добавить второй интерес после разговора было нечем.
  if (done) {
    return (
      <View style={cs.widget}>
        <Cta label={FUNNEL.more()} kind="muted" onPress={more} />
        <Cta label={FUNNEL.finish()} onPress={askEnd} />
      </View>
    );
  }
  // Выход рисуется ВСЕГДА, а не только когда пришли варианты: по-русски модель их почти не
  // присылает, и без этого закончить разговор можно было только исчерпав счётчик ходов.

  // Вариант делает то, что на нём написано. «Добавить ещё интерес» возвращает к чипам, «это всё»
  // заканчивает разговор — а не отправляет свой же текст обратно агенту, после чего тот
  // переспрашивает словами и никакого выбора интересов не появляется.
  const press = (o: string) => {
    if (FUNNEL_MORE_RE.test(o)) { say('me', o); more(); return; }
    if (FUNNEL_OUT_RE.test(o)) { say('me', o); askEnd(); return; }
    say('me', o);
    ask(o);
  };

  return (
    <View style={cs.widget}>
      <View style={cs.row}>
        {opts.map((o) => (
          <Chip key={o} label={o} onPress={() => press(o)} />
        ))}
      </View>
      {/* Выход — отдельной кнопкой под вариантами, а не чипом в их ряду: он делает не то же, что
          они, и не должен читаться как ещё один ответ на вопрос агента. */}
      <Cta label={FUNNEL.done()} kind="muted" onPress={askEnd} />
    </View>
  );
}

/**
 * A.08 — увлечения.
 *
 * Уже выбранное отмечено с самого начала, и это не удобство, а защита. Виджет писал
 * `set('interests.explicit', sel)` из пустого списка, то есть при повторном заходе на этот шаг
 * СТИРАЛ все интересы и заменял их новым выбором. Пока сюда нельзя было вернуться, это не
 * проявлялось; кнопка «Добавить интересы» в профиле делает вход обычным делом.
 */
function HobbyW({ say, startFunnel, leaveFunnel }: any) {
  const st = useOnb();
  const [ownOpen, setOwnOpen] = useState(false);
  const [had] = useState<string[]>(() => get('interests.explicit') || []);
  const [sel, setSel] = useState<string[]>(had);
  const toggle = (k: string) => setSel((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));

  // Написанное своими словами попадает в профиль из композера и должно тут же появиться среди
  // чипов — зажжённым. Иначе человек написал «прогулки с кофе», а на экране ничего не изменилось.
  const explicit: string[] = st.profile.interests?.explicit || [];
  const key = explicit.join('|');
  useEffect(() => {
    setSel((p) => Array.from(new Set([...p, ...explicit])));
  }, [key]);

  // Свои интересы — те, которых нет в готовой десятке. Показываются отдельным рядом и всегда
  // зажжёнными: сняв такой чип, человек потерял бы то, что сам только что написал.
  const own = sel.filter((k) => !HOBBIES.some(([h]) => h === k));

  return (
    <View style={cs.widget}>
      <Hint>{STEP_HOBBIES.hint()}</Hint>
      <View style={cs.row}>
        {HOBBIES.map(([k]) => (
          <Chip key={k} label={hobbyLabel(k)} on={sel.includes(k)} onPress={() => toggle(k)} />
        ))}
        {own.map((k) => (
          <Chip key={k} label={k} on onPress={() => toggle(k)} />
        ))}
        <Chip label={'+ ' + STEP_HOBBIES.own()} onPress={() => setOwnOpen((o) => !o)} />
      </View>

      {/*
        Поле прямо здесь, а не курсор в композере внизу.
        Раньше кнопка лишь ставила фокус в строку сообщения — на телефоне это незаметно: человек
        жмёт «добавить своё», visibly ничего не происходит, и он делает вывод, что не работает.
        Поле рядом с кнопкой показывает, что от него хотят.
      */}
      {ownOpen ? (
        <OwnField
          placeholder={OWN_INPUT.hobbyPlaceholder()}
          onAdd={(v) => {
            setSel((p) => (p.includes(v) ? p : [...p, v]));
            setOwnOpen(false);
          }}
        />
      ) : null}
      <Cta
        label={STEP_HOBBIES.cta()}
        disabled={!sel.length}
        onPress={() => {
          set('interests.explicit', sel);
          say('me', sel.map(hobbyPlain).join(', '));
          // Расспрашиваем только про НОВОЕ: про то, что уже обсуждали, спрашивать заново — значит
          // показывать, что услышанное не сохранилось.
          const added = sel.filter((k) => !had.includes(k));
          if (!added.length) { leaveFunnel(); return; }
          // Дальше не фото, а разговор: чипы говорят ЧТО выбрано, но не как человек этим занят.
          //
          // В затравку уходят КЛЮЧИ (coffee, photography), а не подписи («Кофе», «Фото»). Разговор
          // ведёт модель, и она же переписывает профиль целиком — с русскими подписями в истории
          // она и в interests.explicit кладёт «Кофе». Матчинг ищет по ключам: «Кофе» не совпадёт
          // с coffee ни у кого. Проверено — так и было, пока сюда уходили подписи.
          startFunnel(added);
        }}
      />
    </View>
  );
}

/** A.09–A.13 — снять, загрузить или пропустить; затем подтверждение. */
function PhotoW({ say, onDone, name }: any) {
  const [uri, setUri] = useState<string | null>(null);
  const [stage, setStage] = useState<'ask' | 'result' | 'confirmed'>('ask');
  const [busy, setBusy] = useState(false);

  const shrink = async (src: string) => {
    // Ужимаем ДО отправки: сервер режет всё тяжелее 600 КБ, и снимок с камеры не пролезает.
    const ctx = ImageManipulator.ImageManipulator.manipulate(src);
    const img = await ctx.resize({ width: 512, height: null }).renderAsync();
    const out = await img.saveAsync({ compress: 0.75, format: ImageManipulator.SaveFormat.JPEG, base64: true });
    set('photo', `data:image/jpeg;base64,${out.base64}`);
    set('photoStatus', 'set');
    return out.uri;
  };

  const take = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return;
    const r = await ImagePicker.launchCameraAsync({ cameraType: ImagePicker.CameraType.front, allowsEditing: true, aspect: [1, 1], quality: 0.9 });
    if (r.canceled || !r.assets?.length) return;
    setBusy(true);
    try { const u = await shrink(r.assets[0].uri); setUri(u); say('me', '', u); setStage('result'); } finally { setBusy(false); }
  };

  const upload = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, aspect: [1, 1], quality: 0.9 });
    if (r.canceled || !r.assets?.length) return;
    setBusy(true);
    try { const u = await shrink(r.assets[0].uri); setUri(u); say('me', '', u); setStage('result'); } finally { setBusy(false); }
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
  chip: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  cta: { height: 52, borderRadius: rad.full, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button } as any,

  resultPhoto: { width: '100%', height: 260, borderRadius: rad.md },
  doneCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: color.card,
    borderRadius: rad.lg, padding: 12,
  },
  doneAvatar: { width: 40, height: 40, borderRadius: 20 },
  doneTitle: { ...type.title, color: color.fg } as any,
  doneSub: { ...type.bodySmall, color: color.muted } as any,
});
