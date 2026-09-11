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
  STEP_PHOTO, StepId, resumeStep, hasProgress, onbComplete, RESUME,
  OWN_INPUT, parseName, isName, CONFIRM_INTEREST } from '../src/onboarding';
import { interestLabel, registerInterestLabels } from '../src/interest-label';
import { isKnownInterest } from '../src/interests-known';
import { saveConversation } from '../src/history';
import { addConfirmedInterest, pushInterests } from '../src/profile';
import { profile as profileApi } from '../src/api';
import { useLang, T, getLang, replyLang, noticeWritten, dateLocale, use12h } from '../src/i18n';
import { useOnb, set, get, patch, resetProfile, profileForAttach, mergeProfile, getState } from '../src/state';
import { onboarding, agent, buddy as buddyApi } from '../src/api';
import { AgeDial } from '../src/components/AgeDial';
import { clampAge } from '../src/age-ruler';
import { AreaPicker, Area, DEFAULT_AREA } from '../src/components/AreaPicker';
import { ChatShell, BotLine, chatStyles as cs } from '../src/components/ChatShell';
import { MindMap } from '../src/components/MindMap';
import { InterestMapActions } from '../src/components/InterestMapActions';
import { GlassChip, GlassPill } from '../src/components/Glass';
import { IconCheckCircle } from '../src/components/icons';
import { color, radius as rad, type } from '../src/theme';

/**
 * Слово, которого нет в колесе, и то, что о нём ответил сервер.
 *
 * `options` появляются только у неоднозначного слова: сервер уже выдал квитанцию на КАЖДОЕ
 * прочтение, и человеку остаётся выбрать своё. Однозначное записывается без вопроса.
 */
type NovelOption = { canonical: string; label: string; token: string };
type Novel = { text: string; label: string; question?: string; options?: NovelOption[] };

type Msg = { who: 'bot' | 'me'; text: string; at: string; photo?: string };
/** Реплика в истории, которая уходит модели. Отличается от Msg: у неё роль, а не сторона экрана. */
type Msg2 = { role: string; content: string };

/** Порядок шагов — он же список допустимых значений для входа по ссылке. */
const ORDER: StepId[] = ['start', 'basics', 'area', 'languages', 'hobbies', 'photo'];

const now = () =>
  new Date().toLocaleTimeString(dateLocale(), {
    hour: '2-digit', minute: '2-digit', hour12: use12h(),
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
   * КАРТА ПЕРЕД РАЗГОВОРОМ — ТОЛЬКО В ОНБОРДИНГЕ. Человек, пришедший сюда впервые, ещё не знает,
   * что от него хотят, и поле готовых пузырей отвечает на это быстрее любого вопроса. Из профиля
   * («Добавить интерес») заходят с другим настроением: список уже есть, человек пришёл дописать
   * одно — там остаётся развилка «Знаю, чем / Помоги разобраться».
   */
  const [mapOpen, setMapOpen] = useState(false);
  const [mapPicked, setMapPicked] = useState<string[]>([]);
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
    ПО ТОЙ ЖЕ ПРИЧИНЕ, ЧТО И КОЛОДА, — см. разбор выше. Обе подсказки первого шага жили внутри
    самого виджета, и ответ агента их воскрешал: человек отвечал «Поехали!», агент спрашивал имя,
    а под вопросом об имени снова висели «Зачем это нужно?» и «Поехали!» — подсказки к реплике,
    которой на экране уже две штуки назад. Нажатое должно уходить насовсем, поэтому хранится здесь.
  */
  /*
    ПРИДУМАННЫЕ ИНТЕРЕСЫ ЖДУТ ЗДЕСЬ, А НЕ ПИШУТСЯ СРАЗУ.

    Сервер разбирает реплику и возвращает `added` — то, что он расслышал интересом. Раньше всё это
    падало в профиль без разговора. Но с 27.08 `register` отклоняет ВЕСЬ профиль, если хоть один
    ключ неизвестен общей таксономии: человек проходил анкету до конца и упирался в «Профиль не
    сохранился», не понимая, из-за чего.

    Ключ из своего словаря (дерево или колода) пишем сразу — их сервер принимает все, это проверено.
    Придуманное словами кладём сюда и спрашиваем. Так же устроен экран личности: модель предлагает,
    записывает человек.
  */
  const [pending, setPending] = useState<Novel[]>([]);
  const [startAsked, setStartAsked] = useState(false);
  const [startGone, setStartGone] = useState(false);
  // Номер прохода. Меняется при «Начать заново» и служит ключом виджетам, чтобы те начинали с
  // чистого листа. Иначе внутри них остаётся своё состояние: спрятанные кнопки первого кадра,
  // выбранные увлечения, набранный возраст — всё от предыдущей попытки, которой уже нет.
  const [runId, setRunId] = useState(0);
  const started = useRef(false);
  /*
    ВИДЖЕТ ПРЯЧЕТ ОЧЕРЕДЬ, А НЕ ТОЧКИ. Прятать его по «печатает» почти хватало, но между репликами
    есть вдох в 280 мс, когда точек уже нет, а следующей реплики ещё нет, — и кнопки на это время
    выскакивали. Поймано на снимке: «Зачем это нужно?» и «Поехали!» стояли под приветствием за
    секунду до вопроса, на который отвечают. Признак «очередь идёт» держится от первой реплики до
    последней и вдохов не знает.
  */
  const [queue, setQueue] = useState(false);
  /** Экран ещё на месте? Очередь реплик длинная, и уйти с него успевают раньше, чем она кончится. */
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  /*
    ОНБОРДИНГ В ИСТОРИЮ НЕ ПИШЕТСЯ, И ЭТО НЕ ЭКОНОМИЯ.

    Анкету человек проходит ОДИН раз. Строка «Знакомство с Kleal» навсегда первой и единственной в
    списке — это не история разговоров, а памятник регистрации: искать в ней нечего, перечитывать
    незачем, а место в списке она займёт у всего остального.

    Заход СЮДА ЖЕ из профиля («Интересы → Добавить») — другое дело: он повторяется сколько угодно
    раз и является настоящим разговором с Kleal. Его и пишем — по признаку `entry`.
  */
  const threadRef = useRef<Msg[]>([]);
  threadRef.current = thread;
  const convId = useRef(String(Date.now())).current;
  useEffect(() => () => {
    if (!entry) return;
    saveConversation({
      id: convId,
      startedAt: Number(convId),
      topic: STEP_HOBBIES.mapTitle(),
      lines: threadRef.current.map((m) => ({ who: m.who, text: m.text, at: m.at })),
    });
  }, [convId, entry]);

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
    /*
      ЗАПОЛНИЛ ВСЁ, НО НЕ НАЖАЛ «ГОТОВО» — это не шаг анкеты, это сводка. Раньше такой человек
      получал от `resumeStep` последнюю оставшуюся ступень, 'photo', и снова видел просьбу про
      фото, которое уже добавил или уже пропустил. Отметка `done` ставится только на сводке, и
      добраться до неё повторно было нечем.
    */
    if (!entry && onbComplete(st.profile) && isName(st.profile.name)) { router.replace('/summary'); return; }
    started.current = true;
    /*
      ИМЯ, КОТОРОЕ ИМЕНЕМ НЕ ЯВЛЯЕТСЯ, СНИМАЕТСЯ ЗДЕСЬ — иначе оно бессмертно.

      Живой случай: человек ответил на «Как тебя зовут?» своим адресом почты, разбор пропустил его
      дословно, привязка увезла в аккаунт, и с тех пор вход возвращал адрес обратно в профиль. Сам
      он выйти оттуда не мог: анкета видела заполненное имя и на шаг имени больше не заходила, а
      с экрана сводки любая дорога начинается с записи, которую сервер теперь и не примет.

      Снимаем на входе в анкету: дальше по этой же функции пустое имя означает «спросить заново», и
      человек отвечает один раз. Остальное собранное остаётся на месте — стирать город и интересы
      из-за имени было бы наказанием за чужую ошибку.
    */
    const bad = !!st.profile.name && !isName(st.profile.name);
    if (bad) set('name', '');
    const prof = bad ? { ...st.profile, name: '' } : st.profile;
    // Явный вход не «продолжает с того места»: человек пришёл за конкретной вещью.
    const resumed = !entry && hasProgress(prof);
    const at = entry || resumeStep(prof);
    setStep(at);
    if (resumed) {
      // Вернувшийся на шаг увлечений видит ТУ ЖЕ карту, что и дошедший до него сразу: возобновление
      // — это всё ещё онбординг, и правило «шаг начинается с карты» живёт в обоих входах, иначе
      // порядок экранов зависит от того, закрывал человек приложение или нет.
      if (at === 'hobbies') setMapOpen(true);
      botLines([RESUME.line(prof.name || ''), stepBot(at)], 500);
    } else if (entry) {
      // Вход с экрана интересов — единственное место, где человек уже сказал «хочу добавить»,
      // но ещё не сказал ЧТО. Здесь и стоит развилка: первой репликой предлагаем обе дороги.
      if (entry === 'hobbies') setFork(true);
      botLines([
        entry === 'hobbies' ? STEP_HOBBIES.forkBot()
        : entry === 'languages' ? STEP_LANGUAGES.bot()
        : entry === 'area' ? STEP_AREA.bot()
        : entry === 'basics' ? STEP_BASICS.bot()
        : STEP_START.ask(),
      ], 500);
    } else {
      // Знакомство идёт первым: человек должен понять, куда попал, прежде чем его о чём-то просят.
      botLines([STEP_START.intro(), STEP_START.ask()], 500);
    }
  }, [say]);

  /** Начать онбординг заново. Спрашиваем: это стирает всё, что человек уже ввёл. */
  /**
   * Начать анкету заново. Стирает СОБРАННОЕ, но не вход: см. разбор у `resetProfile` в state.ts.
   * Спрашиваем всегда — это единственное необратимое действие на экране.
   */
  const restart = () => {
    const wipe = () => {
      resetProfile();
      setThread([]);
      setStep('start');
      setStartAsked(false);
      setStartGone(false);
      setRunId((n) => n + 1);
      started.current = true;
      botLines([STEP_START.intro(), STEP_START.ask()], 400);
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

  /**
   * РЕПЛИКИ АГЕНТА ПРИХОДЯТ ПО ОДНОЙ, С «ПЕЧАТАЕТ» МЕЖДУ НИМИ.
   *
   * Раньше вторая реплика ставилась голым `setTimeout` через 600–1400 мс, и получалось два изъяна
   * сразу.
   *
   * ПЕРВЫЙ — ДВА ПУЗЫРЯ РАЗОМ. Полторы секунды без единого признака работы читаются как «оба
   * пришли вместе»: между ними нечего ждать, и человек видит не разговор, а выгруженный текст.
   * Пауза теперь по длине строки, и на ней стоят те же три точки, что и на ответе модели, —
   * ожидание становится видимым, а с ним и то, что реплики две.
   *
   * ВТОРОЙ, ХУДШИЙ — ОТВЕТ ОБГОНЯЛ ВОПРОС. Виджет шага показывается, только пока агент не
   * печатает; между двумя `say` он был виден — то есть кнопки «Зачем?» и «Поехали!» стояли под
   * ПЕРВОЙ репликой, за секунду до вопроса, на который они отвечают. Кто успевал нажать, получал
   * свой ответ, а следом — обогнавший его вопрос «Расскажешь пару деталей о себе?». Пока очередь
   * не кончилась, агент считается печатающим, и нажимать не на что.
   */
  const beat = (text: string) => Math.min(2200, 620 + text.length * 18);

  const botLines = (lines: string[], lead?: number) => {
    const ls = lines.filter(Boolean);
    if (!ls.length) return;
    setQueue(true);
    const step = (i: number, wait: number) => {
      setTyping(true);
      setTimeout(() => {
        if (!alive.current) return;
        setTyping(false);
        say('bot', ls[i]);
        // Короткий вдох между «сказал» и «снова печатает»: без него точки появляются в тот же
        // кадр, что и пузырь, и выглядят частью его.
        if (i + 1 < ls.length) setTimeout(() => alive.current && step(i + 1, beat(ls[i + 1])), 280);
        else setQueue(false);
      }, wait);
    };
    step(0, lead ?? beat(ls[0]));
  };

  const botAfter = (text: string, ms?: number) => botLines([text], ms);

  /** Чем шаг здоровается. Одна таблица на возобновление и на возврат после починки имени. */
  const stepBot = (at: StepId) =>
    at === 'basics' ? STEP_BASICS.bot()
    : at === 'area' ? STEP_AREA.bot()
    : at === 'languages' ? STEP_LANGUAGES.bot()
    : at === 'hobbies' ? ''            // карта уже спрашивает собой
    : STEP_PHOTO.ask();

  const goto = (next: StepId, botLine: string) => {
    setStep(next);
    // Шаг увлечений в онбординге начинается с карты. Реплику агента при этом не показываем:
    // она спрашивает, а карта уже отвечает на тот же вопрос собой.
    if (next === 'hobbies' && !entry) { setMapOpen(true); return; }
    botAfter(botLine);
  };

  /**
   * Карта закрыта. Выбранное уходит ТЕМ ЖЕ путём, что и всё остальное на этом шаге — ключами в
   * `interests.explicit`, — а разговор начинается уже поверх выбранного: агент видит его в
   * `recorded` и не предлагает того, что человек только что отметил.
   */
  /*
   * БЕЗ useCallback НАМЕРЕННО. `botAfter` пересоздаётся каждый рендер, и замороженный обработчик
   * увёл бы за собой реплику агента из самого первого рендера — на этом уже обжигались с `onFork`
   * (тап уходил по ветке онбординга и до API не доходил).
   */
  const onMapDone = ((keys: string[], own?: boolean) => {
    const cur: string[] = get('interests.explicit') || [];
    const merged = [...cur, ...keys.filter((k) => !cur.includes(k))];
    set('interests.explicit', merged);
    /*
      НА СЕРВЕР — СРАЗУ, А НЕ ПРИ СЛЕДУЮЩЕМ ЗАХОДЕ НА ЭКРАН ИНТЕРЕСОВ. Матчинг читает строку в
      базе, а не состояние телефона. Отправка жила только в фокусе app/profile/interests.tsx:
      человек, добавивший интересы здесь и ушедший по нижней панели, оставался для поиска
      прежним, пока когда-нибудь не откроет тот экран. Во время анкеты вызов пустой — там всё
      уедет одним register(); после неё это тот же patchFor(['interests']), что и везде.
    */
    pushInterests();
    setJustAdded((p) => [...p, ...keys.filter((k) => !p.includes(k))]);
    setMapOpen(false);
    /*
      ВЫБРАННОЕ УХОДИТ РЕПЛИКОЙ, И РАЗГОВОР НАЧИНАЕТ АГЕНТ, А НЕ ЧЕЛОВЕК.

      Раньше здесь была одна статичная строка «Отметил. Расскажи про что-нибудь подробнее» — и
      всё останавливалось: агент ждал, человек не знал, что писать, и шаг заканчивался списком
      голых ключей. Между тем расспрос УЖЕ описан в промпте на сервере, и там он назван главным
      правилом: «TWO QUESTIONS PER INTEREST, THEN MOVE ON». Модель просто никогда не получала хода.

      Отправляем то же, что отправляет шаг языков и что отправляла колода, — выбранное списком.
      Промпт разбирает список как список интересов («A LIST IS A LIST»), а `recorded` не даёт ему
      записать их заново. Дальше он ведёт расспрос сам: два вопроса на интерес, потом следующий.
    */
    /*
      «ДОБАВИТЬ СВОЁ» — второй выход с карты, в разговор. Выбранное уже записано выше; репликой его
      не отправляем: ответ модели про выбранное занял бы ход, который человек хотел отдать своему
      слову. Агент просит назвать занятие словами — ключ ему подберёт сервер (см. подтверждение
      придуманного интереса ниже), в карте своих ключей быть не может: регистрация принимает только
      известные таксономии.
    */
    if (own) { botAfter(STEP_HOBBIES.ownAsk()); return; }
    const labels = merged.map((k) => interestLabel(k)).filter(Boolean);
    if (labels.length) send(labels.join(', '));
    else botAfter(STEP_HOBBIES.afterMap());
  });


  /**
   * ПОДТВЕРДИТЬ ПРИДУМАННЫЙ ИНТЕРЕС — та же граница, что на экране личности.
   *
   * Два запроса, и второй существует именно ради человека: первый просит у модели каноническую
   * формулировку, второй записывает её ТОЛЬКО после нажатия. Сервер иначе и не примет — он держит
   * эту границу сам (`validate_confirmations`), и обойти её запросом нельзя.
   *
   * Имя передаём пустым НАМЕРЕННО. В анкете строки человека в базе ещё нет, и сервер это
   * предусмотрел: «During onboarding no user row exists yet. The receipt travels only in device
   * state and is validated again by register_profile before the first database write». Квитанция
   * (`token`) уезжает в `interests.confirmations` и предъявляется при регистрации.
   */
  /**
   * ЧУЖОЕ СЛОВО ЗАПИСЫВАЕТСЯ САМО. Спрашиваем только там, где сервер сам не уверен.
   *
   * Раньше КАЖДЫЙ интерес вне колеса требовал нажатия: модель отдаёт английский ключ из своей
   * таксономии, а приложение знает только колесо — список заметно меньше, — и всё, чего в колесе
   * нет, уезжало в вопрос. Вопрос показывался по одному и не снимался сам, так что «Записать
   * пуэр?» висело над разговором про Малевича, а интересы, набранные следом, стояли в очереди за
   * ним и не записывались вовсе. Поймано на живом телефоне.
   *
   * Нажатие тут ничего и не проверяло: слово взято из реплики САМОГО человека — сервер не примет
   * добавленное без цитаты из неё (`interests_chat`), — а квитанцию всё равно запрашивает клиент.
   * Значит, спрашивать надо не «записать ли», а только тогда, когда сервер вернул выбор.
   *
   * Идёт ПОСЛЕ реплики и молча: два запроса на интерес не должны задерживать ответ агента, а
   * извиняться за слово, которого человек не просил записывать, незачем.
   */
  const absorbNovel = async (items: { text: string; label: string }[]) => {
    for (const item of items) {
      try {
        const cur: string[] = get('interests.explicit') || [];
        const r = await profileApi.normalizeInterest(item.text, cur, replyLang());
        if (r.status === 'duplicate') continue;
        const opts = r.status === 'ready' ? r.options || [] : [];
        if (opts.length !== 1) {
          // Сервер предложил несколько прочтений — это и есть тот случай, когда решает человек.
          const choice = r.status === 'clarify' ? r.options || [] : [];
          if (choice.length) {
            const q = { ...item, question: String(r.question || ''), options: choice };
            setPending((p) => (p.some((x) => x.text === item.text) ? p : [...p, q]));
          }
          continue;
        }
        const ok = await profileApi.confirmInterest('', opts[0].token);
        if (ok.ok && ok.canonical && ok.token) {
          addConfirmedInterest(ok.canonical, ok.label || opts[0].label || item.label, ok.token);
          setJustAdded((p) => (p.includes(ok.canonical!) ? p : [...p, ok.canonical!]));
        }
      } catch {
        // Связь. Слово не потеряно: следующий ход отдаёт его снова вместе с той же цитатой.
      }
    }
  };

  const confirmPending = async (item: Novel, opt?: NovelOption) => {
    setPending((p) => p.filter((x) => x.text !== item.text));
    // Вариант сервера уже несёт квитанцию — нормализовать второй раз нечего.
    if (opt) {
      try {
        const ok = await profileApi.confirmInterest('', opt.token);
        if (ok.ok && ok.canonical && ok.token) {
          addConfirmedInterest(ok.canonical, ok.label || opt.label, ok.token);
          setJustAdded((p) => (p.includes(ok.canonical!) ? p : [...p, ok.canonical!]));
        } else botAfter(CONFIRM_INTEREST.unclear());
      } catch {
        botAfter(CONFIRM_INTEREST.unclear());
      }
      return;
    }
    try {
      const cur: string[] = get('interests.explicit') || [];
      const r = await profileApi.normalizeInterest(item.text, cur, replyLang());
      const opt = r.status === 'ready' && r.options?.length ? r.options[0] : null;
      if (!opt) {
        // Дубль — молча: интерес уже записан, говорить «не смог» было бы неправдой.
        if (r.status !== 'duplicate') botAfter(CONFIRM_INTEREST.unclear());
        return;
      }
      const ok = await profileApi.confirmInterest('', opt.token);
      if (ok.ok && ok.canonical && ok.token) {
        addConfirmedInterest(ok.canonical, ok.label || opt.label, ok.token);
        setJustAdded((p) => (p.includes(ok.canonical!) ? p : [...p, ok.canonical!]));
      } else {
        botAfter(CONFIRM_INTEREST.unclear());
      }
    } catch {
      botAfter(CONFIRM_INTEREST.unclear());
    }
  };

  const skipPending = (item: Novel) =>
    setPending((p) => p.filter((x) => x.text !== item.text));

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

  /**
   * «Готово» на шаге увлечений: сначала сказать, что запись закончена, потом уйти.
   *
   * Реплика обязательна, а не вежливость. Шаг обрывался молча — нажал и оказался на фото, — и
   * человек не знал ни что интересы сохранены, ни что по ним теперь будут искать, ни что их можно
   * поправить. Про число говорим прямо: оно и есть итог разговора.
   */
  const finishHobbies = () => {
    const n = (get('interests.explicit') || []).length;
    botAfter(STEP_HOBBIES.done(n));
    // Уходим ПОСЛЕ реплики, а не вместе с ней: иначе строка появляется на экране, который в тот
    // же кадр снимают, и человек её не читает. Задержка равна вдоху между репликами агента.
    setTimeout(() => alive.current && leaveFunnel(), 900);
  };

  const leaveFunnel = () => {
    // Пришли из профиля — туда и возвращаемся. Не `replace`: тот подменял только верхний экран,
    // а приславший ОСТАВАЛСЯ в стопке под разговором — и человек получал ДВЕ копии «Интересов»
    // подряд, из которых надо было выходить дважды. `dismissTo` снимает разговор и возвращает к
    // тому экрану, который уже открыт.
    if (back) { router.dismissTo(back as any); return; }
    setStep('photo');
    botLines([STEP_PHOTO.greet(st.profile.name || ''), STEP_PHOTO.ask()]);
  };

  /** Свободный текст — сюда отвечает модель, а не сценарий. Поле ввода живёт в Composer. */
  const send = async (text: string) => {
    say('me', text);
    // Человек пишет по-русски на английском телефоне — интерфейс идёт за ним, а не за системой.
    noticeWritten(text);

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
      // Вопрос про прошлый интерес тоже снимаем. Он относился к прошлому ходу: висеть над
      // новым разговором значит спрашивать про пуэр, когда речь давно про Малевича.
      setPending([]);
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
          || T('Что-то я замолчал. Повтори, пожалуйста?', 'I went quiet there. Say that again?', 'Me quedé en silencio. ¿Lo repites?');
        say('bot', reply);
        hobbyThread.current = [...next, { role: 'assistant', content: reply }];
        setChips(Array.isArray((r as any)?.chips) ? (r as any).chips.map(String) : []);
        const added = Array.isArray(r?.added) ? r!.added! : [];
        if (added.length) {
          // УТОЧНЕНИЕ ЗАМЕНЯЕТ, А НЕ ДОБАВЛЯЕТ. «рыбалка» -> «рыбалка на море» это один интерес,
          // ставший точнее; без этого на экране копились три чипа про одно и то же.
          let cur: string[] = get('interests.explicit') || [];
          const ask: { text: string; label: string }[] = [];
          for (const a of added) {
            const key = String(a.key || '').trim();
            if (!key) continue;
            const old = String(a.replaces || '').trim();
            if (old) cur = cur.filter((x) => x !== old);
            // РАЗВИЛКА: своё пишем сразу, чужое слово уносим на нормализацию. Разбор — `absorbNovel`.
            if (isKnownInterest(key)) {
              if (!cur.includes(key)) cur = [...cur, key];
            } else if (!cur.includes(key) && !ask.some((x) => x.text === key)) {
              ask.push({ text: key, label: String(a.label || key) });
            }
          }
          set('interests.explicit', cur);
          pushInterests();                       // см. onMapDone: строка в базе, а не память телефона
          if (ask.length) absorbNovel(ask);
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
        say('bot', T('Связь на секунду пропала. Повторишь?', 'I lost the connection for a second. Say that again?', 'Perdí la conexión un momento. ¿Lo repites?'));
      }
      return;
    }

    // На шаге имени ответ РАЗБИРАЕТСЯ. Раньше здесь стояло «что написали, то и имя» — и человек,
    // ответивший «называй меня Иван», становился «называй меня иван»: под этим именем его видели
    // в поиске и к нему обращался агент. Заодно из «Иван Петров» достаётся фамилия.
    if (step === 'start' && !st.profile.name) {
      const parsed = parseName(text);
      /*
        БЕЗ ИМЕНИ ДАЛЬШЕ НЕ ИДЁМ, и это второй живой случай на том же шаге. Раньше `goto` стоял
        безусловно: разбор не понял ответ — имя оставалось пустым, анкета всё равно уезжала на
        возраст, а сервер подписывал строку «New user». Под этим именем человека и видели в чужой
        переписке. Теперь спрашиваем ещё раз и говорим, почему это важно.
      */
      if (!parsed.name) { botAfter(STEP_START.notAName()); return; }
      set('name', parsed.name);
      if (parsed.surname) set('surname', parsed.surname);
      /*
        ДАЛЬШЕ — ТУДА, ГДЕ ОСТАНОВИЛИСЬ, а не всегда на возраст. У того, кто пришёл сюда чинить
        подпись, остальное уже собрано: гнать его по всей анкете заново значит наказывать за
        ошибку, которую сделала анкета. Новичку это ничего не меняет: без возраста ступень и есть
        'basics'.
      */
      const p2 = { ...st.profile, name: parsed.name };
      if (onbComplete(p2)) { router.replace('/summary'); return; }
      const at = resumeStep(p2);
      goto(at, stepBot(at));
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
      /* Анкета — единственное место с живой подложкой: так она и на кадрах борда. */
      ambientVideo
      title={HEADER_TITLE()}
      pct={pct}
      thread={thread}
      typing={typing}
      onBack={() => router.back()}
      onSend={send}
      scrollEnabled={!dragging}
      footer={step === 'hobbies' && mapOpen && !queue && !typing ? (
        <InterestMapActions selected={mapPicked} onDone={onMapDone} />
      ) : null}
      /*
        ПОКА АГЕНТ ТОЛЬКО ПРЕДСТАВИЛСЯ, ПИСАТЬ НЕЧЕГО. На первом шаге он здоровается и ждёт
        «Поехали!» — а поле ввода выглядело обычным, приглашало «Сообщение…» и молчало в ответ на
        касание (`editable={!!onSend}` отключал ввод, но не вид). Сообщено с телефона. Поле
        оживает ровно тогда, когда появляется, что в него писать: после нажатия или если имя уже
        известно — то есть на возобновлении, где разговор уже идёт.
      */
      composerDisabled={step === 'start' && !startGone && !st.profile.name}
      /*
        КНОПКА «ГОТОВО» ЖИВЁТ ПОД ШАПКОЙ, А НЕ В ЛЕНТЕ.

        В ленте она ехала вместе с виджетом и повторялась под каждой репликой агента: чтобы
        закончить разговор, надо было доскроллить до низа, а по дороге прочитать список
        записанного столько раз, сколько было ходов. Здесь она одна и неподвижна.

        Показываем только на шаге увлечений и только когда карта закрыта: пока выбирают пузыри,
        у поля своя кнопка с порогом в три интереса, и две кнопки выхода разом — это выбор между
        выходами.
      */
      brow={step === 'hobbies' && !mapOpen && !queue ? (
        <View style={s.browWrap}>
          <Cta
            label={STEP_HOBBIES.cta()}
            disabled={!(st.profile.interests?.explicit || []).length}
            onPress={finishHobbies}
          />
        </View>
      ) : null}
      headerExtra={
        hasProgress(st.profile) ? (
          <Pressable accessibilityRole="button" onPress={restart} hitSlop={10}>
            <Text style={s.restart}>{RESUME.restart()}</Text>
          </Pressable>
        ) : null
      }
      widget={queue ? null : (
        <StepWidget
          key={runId}
          step={step}
          say={say}
          goto={goto}
          bot={botLines}
          onDrag={setDragging}
          onDone={() => router.navigate('/summary')}
          leave={leaveFunnel}
          fork={fork}
          chips={chips}
          added={justAdded}
          pending={pending}
          onConfirmPending={confirmPending}
          onSkipPending={skipPending}
          startAsked={startAsked}
          startGone={startGone}
          onStartAsked={() => setStartAsked(true)}
          onStartGone={() => setStartGone(true)}
          mapOpen={mapOpen}
          mapPicked={mapPicked}
          onMapPick={(k: string) => setMapPicked((p) =>
            p.includes(k) ? p.filter((x) => x !== k) : [...p, k])}
          onMapDone={onMapDone}
          onFork={onFork}
          onChip={send}
          onDrop={(k: string) => setJustAdded((p) => p.filter((x) => x !== k))}
        />
      )}
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
  bot,
  mapOpen, mapPicked, onMapPick, onMapDone,
  pending, onConfirmPending, onSkipPending,
  startAsked, startGone, onStartAsked, onStartGone,
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
  /** Карта интересов вместо разговора — первый проход онбординга. */
  mapOpen?: boolean;
  mapPicked?: string[];
  onMapPick?: (key: string) => void;
  onMapDone?: (keys: string[], own?: boolean) => void;
  /** Придуманные интересы, ждущие подтверждения. Живут в экране — см. там почему. */
  pending?: Novel[];
  onConfirmPending?: (item: Novel, opt?: NovelOption) => void;
  onSkipPending?: (item: Novel) => void;
  /** Подсказки первого шага: что уже нажато. Живёт в экране — см. там почему. */
  startAsked: boolean;
  startGone: boolean;
  onStartAsked: () => void;
  onStartGone: () => void;
  /** Очередь реплик агента: по одной, с «печатает» между ними. */
  bot: (lines: string[], lead?: number) => void;
}) {
  const st = useOnb();

  if (step === 'start') return (
    <StartW say={say} bot={bot}
            asked={startAsked} gone={startGone}
            onAsked={onStartAsked} onGone={onStartGone} />
  );
  if (step === 'basics') return <BasicsW say={say} goto={goto} onDrag={onDrag} />;
  // onDrag — не косметика: пока палец тащит булавку по карте, лента анкеты обязана молчать,
  // иначе ScrollView забирает вертикальный жест себе и точка дёргается на месте.
  if (step === 'area') return <AreaW say={say} goto={goto} onDrag={onDrag} />;
  if (step === 'languages') return <LangW say={say} goto={goto} />;
  if (step === 'hobbies') return (
    <HobbyW say={say} leaveFunnel={leave} fork={fork} chips={chips} added={added}
            onFork={onFork} onChip={onChip} onDrop={onDrop} onDrag={onDrag}
            mapOpen={mapOpen} mapPicked={mapPicked} onMapPick={onMapPick} onMapDone={onMapDone}
            pending={pending} onConfirmPending={onConfirmPending} onSkipPending={onSkipPending} />
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
function StartW({ say, bot, asked, gone, onAsked, onGone }: any) {
  const st = useOnb();

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
              onAsked();
              say('me', STEP_START.why());
              bot([STEP_START.whyAnswer()]);
            }}
          />
        )}
        <Chip
          label={STEP_START.go()}
          on
          onPress={() => {
            onGone();
            say('me', STEP_START.go());
            bot([STEP_START.askName()]);
          }}
        />
      </View>
    </View>
  );
}

/** A.05 — линейка возраста и пол. */
function BasicsW({ say, goto, onDrag }: any) {
  const st = useOnb();
  const [age, setAge] = useState(() => clampAge(st.profile.age));
  const [sex, setSex] = useState<string | null>(null);
  return (
    <View style={cs.widget}>
      <Text maxFontSizeMultiplier={1.6} style={[cs.label, s.basicsLabel]}>{STEP_BASICS.ageLabel()}</Text>
      <AgeDial value={age} onChange={setAge} locale={replyLang()} onDragChange={onDrag} />
      <Text maxFontSizeMultiplier={1.6} style={[cs.label, s.basicsLabel]}>{STEP_BASICS.sexLabel()}</Text>
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
function HobbyW({ mapOpen, mapPicked, onMapPick, onMapDone,
                 pending, onConfirmPending, onSkipPending,
                 say, leaveFunnel, fork, chips, added, onFork, onChip, onDrop, onDrag,
                 }: any) {
  const st = useOnb();
  const [busy, setBusy] = useState(false);
  // Показываем записанное ЗА ЭТОТ разговор. Всё, что было в профиле раньше, человек видит на
  // экране «Интересы», откуда пришёл; повторять его здесь значит прятать новое среди старого.
  const explicit: string[] = added || [];
  const hasAny: boolean = !!(st.profile.interests?.explicit || []).length;

  /*
   * КАРТА ЗАНИМАЕТ ВЕСЬ ВИДЖЕТ и стоит первой веткой: пока она открыта, ни развилки, ни подсказок,
   * ни списка записанного — они про разговор, которого ещё не было. Порог в три интереса взят с
   * борда («Choose at least 3 interests»); ниже него «Дальше» не нажимается, и это единственное
   * место, где экран человека ограничивает.
   */
  if (mapOpen) {
    const picked: string[] = mapPicked || [];
    return (
      <View style={cs.widget}>
        {/*
          ЗАГОЛОВОК НАД КАРТОЙ. Была одна подсказка — «Веди пальцем, то что под ним приблизится», —
          то есть инструкция к жесту, а не ответ на вопрос «что это вообще». Человек видел поле
          цветных кружков и не понимал, что от него хотят: сообщено с телефона. Сначала — ЧТО
          выбираем, и только потом — как.
        */}
        <Text style={cs.mapTitle}>{STEP_HOBBIES.mapTitle()}</Text>
        <Text style={cs.hint}>{STEP_HOBBIES.mapHint()}</Text>
        {/* Ширину карта берёт по экрану сама; высота — под поле из восьми тем с подписями. */}
        <MindMap height={440} selected={picked} onToggle={(k) => onMapPick?.(k)} />
        {/* Всё выбранное, а не последние шесть: чипы — это и есть корзина, нажатие снимает. */}
        {picked.length ? (
          <View style={cs.row}>
            {picked.map((k: string) => (
              <GlassChip key={k} label={interestLabel(k)} on wrapLabel onPress={() => onMapPick?.(k)} />
            ))}
          </View>
        ) : null}
      </View>
    );
  }

  /*
    ВОПРОС ПРО ПРИДУМАННЫЙ ИНТЕРЕС стоит ПЕРЕД остальным виджетом и вместо подсказок к реплике.
    Причина простая: пока он висит, всё прочее — не то, что сейчас требует ответа. Подсказки к
    вопросу агента вернутся сами, как только на этот ответят.

    Кнопок ровно две, и отказ такая же кнопка, как согласие: молча проигнорированный вопрос
    оставил бы интерес в подвешенном состоянии до конца анкеты, где он и уронил бы регистрацию.
  */
  if (pending && pending.length) {
    const item = pending[0];
    const opts = item.options || [];
    return (
      <View style={cs.widget}>
        <Hint>{opts.length ? item.question || CONFIRM_INTEREST.ask() : CONFIRM_INTEREST.ask()}</Hint>
        <View style={cs.row}>
          {opts.length
            ? opts.map((o: NovelOption) => (
                <Chip key={o.token} label={o.label || o.canonical} on onPress={() => onConfirmPending?.(item, o)} />
              ))
            : <Chip label={CONFIRM_INTEREST.yes(item.label)} on onPress={() => onConfirmPending?.(item)} />}
          <Chip label={CONFIRM_INTEREST.no()} onPress={() => onSkipPending?.(item)} />
        </View>
      </View>
    );
  }

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
      {/*
        КОЛОДЫ КАРТОЧЕК ЗДЕСЬ БОЛЬШЕ НЕТ.

        Она решала ту же задачу, что и карта интересов: дать выбор тем, кто не знает, с чего
        начать. Две витрины одного и того же на одном шаге — это выбор между выборами: человек
        свайпал «Бег» влево-вправо, не понимая, чем это отличается от поля пузырей, которое он
        видел минуту назад. Карта показывает полторы сотни занятий разом и своими кустами, а
        колода — по одному и вслепую.

        Остальное на шаге осталось: разговор, подсказки к реплике, записанное и выход.
      */}
      {/*
        СПИСКА «ЗАПИСАЛ» ЗДЕСЬ БОЛЬШЕ НЕТ, И КНОПКИ ВЫХОДА ТОЖЕ.

        Оба уехали вверх, под шапку. Внизу они стояли под каждой репликой агента и росли вместе с
        разговором: к пятому вопросу лента наполовину состояла из повторяющегося списка того, что
        человек и так только что назвал. А сам список он всё равно увидит в профиле — там ему и
        место, там его можно править спокойно.

        Кнопка «Готово» под шапкой стоит НЕПОДВИЖНО и видна всегда: раньше её выносило вниз вместе
        с лентой, и чтобы закончить, приходилось доскроллить до конца разговора.
      */}
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
  /** Fits the 1.6x Dynamic Type cap even though the shared label token has a fixed line height. */
  basicsLabel: { lineHeight: 24 },
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
  /** Полоса под шапкой: та же ширина полей, что у ленты, чтобы кнопка стояла по её краю. */
  browWrap: { paddingHorizontal: 16, paddingBottom: 8 },
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
