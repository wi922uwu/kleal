/**
 * Мастер интента — борд «1:1 Online», кадры O.05–O.09, затем поиск OF.11 и выдача.
 *
 * UX-КАРКАС: вид натянется поверх. Копия и правила — в src/intent.ts; оформление — одним блоком
 * внизу файла, только на токенах темы.
 *
 * Устройство по кадрам, и оно ДРУГОЕ, чем у прежнего мастера:
 *
 *  — Шапка как у создания интента: круглая «назад» слева, красная пилюля «All intents» справа.
 *    Полосы прогресса с процентами нет.
 *  — O.05/O.06 — списки с галочкой. Кнопки «Дальше» на них нет: выбор строки сам ведёт дальше,
 *    агент коротко отвечает «Awesome!» и печатает следующий вопрос.
 *  — O.07–O.09 — три шага деталей под степпером 1–2–3, каждый в белой карточке со своей кнопкой
 *    Next: когда (чипы дат, круглый циферблат времени, часовой пояс) → кого (аудитория, кольцо
 *    возраста-диапазона) → ссылка на звонок для онлайна и гибрида, район и радиус для офлайна.
 *  — Внизу всегда композер «Message…»: сказанное словами уходит в /api/agent/plan целиком и ведёт
 *    сразу к выдаче — человек, описавший затею фразой, не должен проходить шаги, на которые уже
 *    ответил.
 *
 * Тема приходит готовой из разговора создания (?topic=…): вопрос «что хочешь сделать?» здесь не
 * задаётся. Открытый без темы (старые пути) мастер всё равно работает — интент уходит без topics,
 * и матчинг ищет широко.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import Slider from '@react-native-community/slider';
import {
  INTENT, IntentStepId, STEP_HOW, FORMATS, formatLabel, formatSub,
  NATURE_TRAITS, NATURE_MAX,
  STEP_SIZE, SIZES, sizeLabel, sizeSub, GROUP_MIN_TOTAL,
  DETAILS, EDIT_SHEET, dateChips, timeQueryFromDate, deviceTz, tzDisplay, tzOptions, tzCity, looksLikeUrl,
  SEARCHING,
  SUMMARY_O10, summaryDate, tzOffsetLabel, intentSummaryText, hhmm, planWhenLabel,
} from '../src/intent';
import { SEXES, sexLabel, COMPOSER_PLACEHOLDER } from '../src/onboarding';
import { TimeDial, RangeDial } from '../src/components/Dials';
import { RadiusMap } from '../src/components/RadiusMap';
import {
  IconChevronLeft, IconMic, IconPin, IconVideo, IconPlusRound, IconPerson, IconGroups,
  IconCalendar, IconClock, IconGlobe, IconLink, IconPlay, IconImagePlaceholder, IconPencil, IconStar,
} from '../src/components/icons';
import { EditSheet } from '../src/components/ProfileShell';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { resetGroupSession } from '../src/ginvites';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { setResults } from '../src/results-store';
import { agent, isAbort } from '../src/api';
import { color, radius as rad, space, type } from '../src/theme';

type Draft = {
  mode?: string;
  size?: string;
  date: string;
  /** Минуты от полуночи. 1200 = 20:00 — значение с кадра O.07. */
  minutes: number;
  tz: string;
  sex?: string;
  minAge: number;
  maxAge: number;
  /** Черты, которые попросили в другом человеке: ось → токен. Пусто — «не принципиально». */
  nature: Record<string, string>;
  district?: string;
  radiusKm: number;
  link: string;
  /** OF.09: точное место, названное на создании. В выдачу не уходит — только район. */
  address?: string;
  /** OF.09: центр поиска. Пусто — берётся из профиля; заполняется, когда булавку передвинули. */
  lat?: number;
  lon?: number;
};

export default function Intent() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх композера — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  /**
   * Из разговора создания приходят ДВЕ вещи, и это не дублирование.
   *
   *   topics — английские ключи для поиска: coffee, work. По ним матчинг сравнивает БУКВАЛЬНО.
   *   title  — подпись для человека на его языке: «Кофе — разговор». В поиск не идёт никогда.
   *
   * Раньше сюда ехала одна строка — заголовок, — и она уходила в topics. Русская фраза не
   * совпадает ни с кем: запрос возвращал не людей, а восемь «замен». Проверено на стенде.
   *
   * `topic` (единственное число) поддержан для старых ссылок: он трактуется и как ключ, и как
   * подпись, — так вело себя приложение до разделения.
   */
  const params = useLocalSearchParams<{ topics?: string; title?: string; topic?: string }>();
  const legacy = String(params.topic || '').trim();
  const topics = String(params.topics || legacy || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  const title = String(params.title || legacy || '').trim();

  const [step, setStep] = useState<IntentStepId>('how');
  const [draft, setDraft] = useState<Draft>(() => ({
    date: dateChips(1)[0].key,
    minutes: 20 * 60,
    tz: deviceTz(),
    minAge: 18,
    maxAge: 28,               // диапазон с кадра O.08
    nature: {},
    radiusKm: 15,
    link: '',
  }));
  /** Между шагом и шагом агент отвечает «Awesome!» и печатает — как на кадрах. */
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  /** Живой запрос поиска — чтобы кнопка «Отменить» рвала именно его. */
  const abortRef = useRef<AbortController | null>(null);
  const [err, setErr] = useState('');
  const [dragging, setDragging] = useState(false);
  /** O.07a: лист пояса держит выбор у себя и отдаёт его в черновик только по «Применить». */
  const [tzOpen, setTzOpen] = useState(false);
  const [tzPick, setTzPick] = useState('');
  /** O.10a: лист «что поменять» над сводкой; editPick — подсвеченная строка. */
  const [editOpen, setEditOpen] = useState(false);
  const [editPick, setEditPick] = useState('');
  const [free, setFree] = useState('');
  /** Категория для строки сводки O.10. Приходит от агента фильтрации; пусто — строка не рисуется. */
  const [category, setCategory] = useState('');

  /**
   * Профиль, как он уезжает в поиск. Координаты — из черновика, когда булавку на OF.09 передвинули:
   * расстояние до кандидатов считается от них, и «ищи вокруг вон той точки» иначе было бы просто
   * картинкой. Не трогали булавку — едут координаты профиля, как раньше.
   */
  const profile = () => ({
    name: st.profile.name,
    age: st.profile.age,
    gender: st.profile.gender,
    city: st.profile.city,
    lat: draft.lat ?? st.profile.geo?.coarseLat,
    lon: draft.lon ?? st.profile.geo?.coarseLon,
    // Объектом, а не списком: сервер читает `languages.comfortable`, и на плоском списке
    // ранжирование падало целиком — см. тот же комментарий в app/group.tsx.
    languages: st.profile.languages || {},
  });

  /**
   * ctx нужен не для порядка: §5.3 считает город только отсюда (location_block.city ← ctx.city).
   * Без него ответ приходит с minimally_sufficient.ok = false, и поиск идёт по интенту, который
   * сам сервер считает недосказанным. tz — из мастера: человек мог выбрать не пояс устройства.
   */
  /**
   * Центр карты OF.09 — координаты профиля. Булавка стоит там, где человек живёт, а круг радиуса
   * рисует, куда он готов доехать. Барселона запасным значением: без координат карта показала бы
   * океан у нулевого меридиана, а это выглядит как поломка, а не как «мы не знаем, где ты».
   */
  const where = String(st.profile.city || '').trim();
  const homeLat = Number(st.profile.geo?.coarseLat ?? 41.3874);
  const homeLon = Number(st.profile.geo?.coarseLon ?? 2.1686);
  const mapLat = draft.lat ?? homeLat;
  const mapLon = draft.lon ?? homeLon;
  /** Булавку увели от дома — говорим об этом словами и даём вернуть одним нажатием. */
  const moved = draft.lat != null || draft.lon != null;

  const ctx = () => ({
    self: st.profile.name,
    uid: st.profile.name,
    city: st.profile.city,
    tz: draft.tz,
  });

  const toResults = (r: any, fallbackIntent: any, query?: string) => {
    // Новый поиск — новая сессия группового набора: прошлая группа живёт на сервере, но выдача
    // другого запроса ей не принадлежит (см. resetGroupSession в src/ginvites.ts).
    resetGroupSession();
    setResults({
      intent: r?.intent || fallbackIntent,
      candidates: r?.candidates || [],
      profile: profile(),
      query: query || '',
    });
    router.push('/results');
  };

  /** Выбор строки на O.05/O.06: галочка, «Awesome!», и через паузу следующий вопрос. */
  const choose = (patch: Partial<Draft>, next: IntentStepId) => {
    if (ack) return;
    setDraft((d) => ({ ...d, ...patch }));
    setAck(true);
    setTimeout(() => {
      setAck(false);
      setStep(next);
      scroller.current?.scrollTo({ y: 0, animated: false });
    }, 900);
  };

  /**
   * Свободный текст. Человек, описавший затею словами, не проходит шаги, на которые уже ответил:
   * текст уходит модели целиком (/api/agent/plan) и ведёт сразу к выдаче.
   */
  const send = async () => {
    const text = free.trim();
    if (!text || busy) return;
    setFree('');
    setErr('');
    setBusy(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r: any = await agent.plan(text, profile(), ctx(), undefined, ctrl.signal);
      toResults(r, {}, text);
    } catch (e) {
      setErr(isAbort(e) ? SEARCHING.cancelled()
                        : T('Связь пропала. Повторишь?', 'I lost the connection. Say that again?'));
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  };

  /** Собранный по шагам интент — структурный, без разбора текста. */
  const finish = async () => {
    setErr('');
    setBusy(true);
    const intent: any = {
      topics,
      /**
       * Подпись для ЛЮДЕЙ. Её тут не было, и это видел не автор интента, а приглашённый: у него
       * на экране приглашения, в списке «Сообщений», в шапке чата и в заголовке плана стояло
       * «coffee, casual» — служебные английские ключи поиска. Заголовок собран в разговоре
       * создания («Кофе — встреча») и обязан ехать вместе с ключами.
       */
      ...(title ? { title } : {}),
      mode: draft.mode || 'online',
      // Английская строка намеренно: срочность на той стороне ищется по словам, и только английским.
      time: timeQueryFromDate(draft.date, draft.minutes),
      /**
       * И сам выбор — днём и минутами. Поиску они не нужны (ему хватает `time`), но затея живёт
       * дольше поиска: её страница открывает лист правки времени, и без этих двух чисел лист
       * вставал бы на «сегодня, 20:00» вместо того, что человек выбрал. Из них же собирается
       * сводка, когда своей ещё нет.
       */
      dateKey: draft.date,
      minutes: draft.minutes,
      // ...и человеческая подпись того же времени рядом: «today 20:00» на экране приглашения
      // читалось как недоперевод. Ключ отдельно для поиска, строка отдельно для глаз.
      when: planWhenLabel(draft.date, draft.minutes),
      // format, а не groupSize. §5.3 признаёт интент описанным только когда есть и mode, и format;
      // groupSize же увёл бы запрос в групповую ветку, где 1:1 просто нечего делать.
      format: draft.size === 'group' ? 'group' : '1:1',
    };
    if (draft.size === 'group') intent.groupSize = GROUP_MIN_TOTAL;
    if (draft.sex && draft.sex !== 'Any') intent.sex = draft.sex;
    if (draft.minAge) intent.minAge = draft.minAge;
    if (draft.maxAge) intent.maxAge = draft.maxAge;
    // Характер — ПОЖЕЛАНИЕ, не гейт: ранжирование поднимает совпавших выше, но никого не
    // отсекает. Отсекать по нему нельзя — тест прошли единицы, и фильтр оставил бы пустую выдачу.
    if (Object.keys(draft.nature).length) intent.wantPersona = draft.nature;
    // Гибрид кладёт И место, И ссылку — HY.09. Это не «оба на всякий случай»: без места некуда
    // прийти живьём, без ссылки нечем подключиться, и борд формулирует это в обе стороны
    // (HY.20a / HY.20b). Раньше гибрид шёл целиком по ветке онлайна и приезжал в поиск без места.
    const wantsPlace = draft.mode === 'offline' || draft.mode === 'hybrid';
    const wantsLink = draft.mode !== 'offline';
    if (wantsPlace) {
      // Район на OF.09 задаёт карта вокруг координат профиля, а не список чипов, — в запрос
      // едет город профиля: именно его §5.3 читает как location_block.city.
      const place = String(st.profile.city || '').trim();
      if (place) intent.place = place;
      if (draft.radiusKm != null) intent.radiusKm = draft.radiusKm;
      // OF.09: точное место ранжирование не читает — оно нужно ПОЗЖЕ, когда из мэтча собирается
      // план: форма плана подхватит его, чтобы не спрашивать дважды. В выдачу уходит только район.
      if (draft.address?.trim()) intent.address = draft.address.trim();
    }
    if (wantsLink) {
      // Иначе §5.3 требует город, которого у онлайн-встречи нет по определению. Гибриду это тоже
      // нужно, и по той же причине: половина его встречи — звонок, и радиус не должен НИКОГО
      // отсекать (кто далеко — подключится). Жёсткий гейт радиуса на сервере включён только для
      // mode == 'offline', так что гибрид получает радиус как предпочтение, а не как забор.
      intent.allowOnlineFallback = true;
      // Ссылку ранжирование не читает — она нужна ПОЗЖЕ, когда из мэтча собирается план встречи.
      // Кладётся в интент, чтобы уехать вместе с ним в выдачу, а не потеряться на этом экране.
      if (draft.link.trim()) intent.link = draft.link.trim();
    }
    /**
     * ЗАТЕЯ ЗАПОМИНАЕТСЯ — иначе она живёт ровно столько, сколько открыт этот экран.
     *
     * Хранилище интентов на сервере было с самого начала, но не звал его никто: человек описывал
     * затею, уходил в выдачу, закрывал приложение — и назавтра от неё не оставалось ничего.
     * Поэтому вкладка «Моя активность» и была пуста: показывать было нечего, а не некому.
     *
     * `launched: true` ставится здесь же, вместе с запуском поиска: с этой секунды затея не
     * черновик. Сбой записи поиск не отменяет — человек шёл искать людей, а не сохранять карточку,
     * и ронять его дорогу из-за не доехавшей записи было бы наказанием не за то.
     */
    agent.intentSave(String(st.profile.name || ''), intent, title || topics.join(', '), undefined, true)
      .catch(() => {});

    // Отмена принадлежит человеку: экран поиска даёт кнопку, и она рвёт именно этот запрос.
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r: any = await agent.match(intent, profile(), ctx(), ctrl.signal);
      toResults(r, intent);
    } catch (e) {
      // Отменил сам — это не сбой связи. Называть это ошибкой значит врать о том, что произошло.
      setErr(isAbort(e) ? SEARCHING.cancelled() : SEARCHING.failed());
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  };

  /** Отмена поиска по кнопке на вуали. */
  const cancelSearch = () => abortRef.current?.abort();

  /**
   * O.10: перед поиском — сводка. Категория для её строки спрашивается у агента фильтрации в
   * фоне; сводка её не ждёт — строка появляется, когда ответ пришёл, и не появляется вовсе, если
   * агент промолчал. Держать человека на «Дальше» ради одной строки таблицы нельзя.
   */
  const toSummary = () => {
    setStep('summary');
    // Категорию спрашиваем по КЛЮЧАМ: агент фильтрации, как и матчинг, понимает английский.
    const text = topics.join(' ') || title;
    if (!text || category) return;
    agent.categorize(text)
      .then((r: any) => {
        const c = String(r?.category || '').trim();
        if (c) setCategory(c.charAt(0).toUpperCase() + c.slice(1));
      })
      .catch(() => {});
  };

  /**
   * Место и ссылка вынесены в блоки: у гибрида они стоят на ОДНОМ шаге (HY.09), у офлайна и
   * онлайна — каждый на своём. Копия и поведение обязаны быть теми же; две копии одного блока
   * разошлись бы на первой правке, и разошлись бы именно у гибрида, которого меньше видно.
   */
  const linkBroken = !!draft.link.trim() && !looksLikeUrl(draft.link);

  const linkBlock = (
    <>
      <LabelRow Icon={IconLink} text={DETAILS.link()} />
      <TextInput
        style={s.linkInput}
        value={draft.link}
        onChangeText={(t) => setDraft((x) => ({ ...x, link: t }))}
        placeholder={DETAILS.linkPlaceholder()}
        placeholderTextColor={color.neutral400}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        accessibilityLabel={DETAILS.link()}
      />
      <View style={s.noteRow}>
        <IconLink size={16} c={color.muted} />
        <Text style={s.note}>{DETAILS.linkNote()}</Text>
      </View>
    </>
  );

  /* OF.09 — район картой, а не списком: круг показывает, что человек считает «рядом».
     Порядок с кадра: карта → точный адрес → радиус → записка о приватности. */
  const placeBlock = (
    <>
      <LabelRow Icon={IconPin} text={DETAILS.district()} />
      <View style={s.map}>
        <RadiusMap
          lat={mapLat}
          lon={mapLon}
          km={draft.radiusKm}
          onMove={(la, lo) => setDraft((x) => ({ ...x, lat: la, lon: lo }))}
          onDragChange={setDragging}
        />
      </View>
      <View style={s.mapHintRow}>
        <Text style={s.mapHint}>{moved ? DETAILS.centerMoved() : DETAILS.dragPin()}</Text>
        {moved ? (
          <Pressable
            accessibilityRole="button"
            hitSlop={8}
            onPress={() => setDraft((x) => ({ ...x, lat: undefined, lon: undefined }))}
          >
            <Text style={s.mapReset}>{DETAILS.backHome()}</Text>
          </Pressable>
        ) : null}
      </View>

      {/* Точное место можно назвать сразу — но чужим оно не показывается: его выдаёт
          только план после взаимного подтверждения (OF.C3). */}
      <TextInput
        style={s.linkInput}
        value={draft.address || ''}
        onChangeText={(t) => setDraft((x) => ({ ...x, address: t }))}
        placeholder={DETAILS.exactAddress()}
        placeholderTextColor={color.neutral400}
        accessibilityLabel={DETAILS.exactAddress()}
      />

      <View style={s.radiusRow}>
        <Text style={s.tzLabel}>{DETAILS.radius()}</Text>
        <Text style={s.radiusValue}>{draft.radiusKm} km</Text>
      </View>
      <Slider
        minimumValue={1}
        maximumValue={50}
        step={1}
        value={draft.radiusKm}
        onValueChange={(km) => setDraft((x) => ({ ...x, radiusKm: Math.round(km) }))}
        minimumTrackTintColor={color.primary}
        maximumTrackTintColor={color.neutral100}
        thumbTintColor={color.primary}
      />
      <Text style={s.privacyNote}>{DETAILS.exactAddressNote()}</Text>
    </>
  );

  /** Отмеченные черты одной строкой — для сводки O.10 и листа правки. */
  const natureSummary = NATURE_TRAITS.filter((t) => draft.nature[t.axis] === t.token)
    .map((t) => t.label()).join(', ');

  /** Последний шаг деталей зависит от типа встречи — см. шапку src/intent.ts. */
  const lastStep: IntentStepId =
    draft.mode === 'offline' ? 'place' : draft.mode === 'hybrid' ? 'both' : 'link';
  const detailIndex = step === 'when' ? 0 : step === 'who' ? 1 : step === 'nature' ? 2 : 3;

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
            <IconChevronLeft />
          </Pressable>
          <View style={{ flex: 1 }} />
          {/* Кнопка называется «Все интенты» — значит ведёт к ним, а не на главную. Раньше она
              делала replace('/home'), и человек, искавший список своих затей, оказывался на
              ленте (поймано 14 августа). Список живёт во вкладке «Интенты» — это /activity. */}
          <Pressable accessibilityRole="button" style={s.allBtn} onPress={() => router.replace('/activity')}>
            <Text style={s.allText}>{INTENT.allIntents()}</Text>
          </Pressable>
        </View>

        <ScrollView
          ref={scroller}
          contentContainerStyle={s.body}
          keyboardShouldPersistTaps="handled"
          scrollEnabled={!dragging}
        >
          {step === 'how' || step === 'size' ? (
            <>
              <QuestionHead title={step === 'how' ? STEP_HOW.ask() : STEP_SIZE.ask()} />
              {step === 'how'
                ? FORMATS.map(([k]) => (
                    <OptionRow
                      key={k}
                      Icon={k === 'offline' ? IconPin : k === 'online' ? IconVideo : IconPlusRound}
                      title={formatLabel(k)}
                      sub={formatSub(k)}
                      on={draft.mode === k}
                      onPress={() => choose({ mode: k }, 'size')}
                    />
                  ))
                : SIZES.map(([k]) => (
                    <OptionRow
                      key={k}
                      Icon={k === 'group' ? IconGroups : IconPerson}
                      title={sizeLabel(k)}
                      sub={sizeSub(k)}
                      on={draft.size === k}
                      onPress={() => choose({ size: k }, 'when')}
                    />
                  ))}
              {ack ? <Ack /> : null}
            </>
          ) : (
            <>
              {step === 'summary' ? (
                <>
                  <QuestionHead title={SUMMARY_O10.title()} />
                  {/* Пузырь-примечание с кадра: сверить и поправить можно что угодно. */}
                  <View style={s.ackBub}><Text style={s.ackText}>{SUMMARY_O10.note()}</Text></View>
                </>
              ) : (
                <>
                  <QuestionHead
                    title={DETAILS.title()}
                    sub={
                      step === 'when' ? DETAILS.subWhen()
                      : step === 'who' ? DETAILS.subWho()
                      : step === 'nature' ? DETAILS.subNature()
                      : step === 'link' ? DETAILS.subLink()
                      : step === 'both' ? DETAILS.subBoth()
                      : DETAILS.subPlace()
                    }
                  />
                  <Stepper current={detailIndex} />
                </>
              )}

              {step === 'when' ? (
                <View style={s.card}>
                  <LabelRow Icon={IconCalendar} text={DETAILS.date()} />
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
                    {dateChips().map((d) => (
                      <Chip key={d.key} label={d.label} on={draft.date === d.key} onPress={() => setDraft((x) => ({ ...x, date: d.key }))} />
                    ))}
                  </ScrollView>

                  <LabelRow Icon={IconClock} text={DETAILS.time()} />
                  <TimeDial
                    minutes={draft.minutes}
                    onChange={(m) => setDraft((x) => ({ ...x, minutes: m }))}
                    onDragChange={setDragging}
                  />
                  <View style={s.boxRow}>
                    <NumBox
                      value={String(Math.floor(draft.minutes / 60)).padStart(2, '0')}
                      onChange={(t) => {
                        const h = Math.max(0, Math.min(23, parseInt(t || '0', 10) || 0));
                        setDraft((x) => ({ ...x, minutes: h * 60 + (x.minutes % 60) }));
                      }}
                    />
                    <Text style={s.boxColon}>:</Text>
                    <NumBox
                      value={String(draft.minutes % 60).padStart(2, '0')}
                      onChange={(t) => {
                        const m = Math.max(0, Math.min(59, parseInt(t || '0', 10) || 0));
                        setDraft((x) => ({ ...x, minutes: Math.floor(x.minutes / 60) * 60 + m }));
                      }}
                    />
                  </View>

                  {/* O.07a: строка открывает лист выбора, а не аккордеон — выбор применяется только по «Применить». */}
                  <Pressable
                    accessibilityRole="button"
                    style={s.tzRow}
                    onPress={() => { setTzPick(draft.tz); setTzOpen(true); }}
                  >
                    <IconGlobe />
                    <View style={{ flex: 1 }}>
                      <Text style={s.tzLabel}>{DETAILS.timeZone()}</Text>
                      <Text style={s.tzValue}>{tzDisplay(draft.tz)}</Text>
                    </View>
                    <Text style={s.chev}>⌄</Text>
                  </Pressable>

                  <Cta label={INTENT.next()} onPress={() => setStep('who')} />
                </View>
              ) : null}

              {step === 'who' ? (
                <View style={s.card}>
                  <LabelRow Icon={IconPlay} text={DETAILS.audience()} />
                  <View style={s.chipRowWrap}>
                    {SEXES.map(([k]) => (
                      <Chip key={k} label={sexLabel(k)} on={draft.sex === k} onPress={() => setDraft((x) => ({ ...x, sex: k }))} />
                    ))}
                  </View>

                  <LabelRow Icon={IconPerson} text={DETAILS.age()} />
                  <RangeDial
                    lo={draft.minAge}
                    hi={draft.maxAge}
                    onChange={(lo, hi) => setDraft((x) => ({ ...x, minAge: lo, maxAge: hi }))}
                    onDragChange={setDragging}
                  />
                  <View style={s.boxRow}>
                    <NumBox
                      value={String(draft.minAge)}
                      onChange={(t) => {
                        const v = Math.max(18, Math.min(draft.maxAge, parseInt(t || '18', 10) || 18));
                        setDraft((x) => ({ ...x, minAge: v }));
                      }}
                    />
                    <Text style={s.boxColon}>–</Text>
                    <NumBox
                      value={String(draft.maxAge)}
                      onChange={(t) => {
                        const v = Math.min(80, Math.max(draft.minAge, parseInt(t || '80', 10) || 80));
                        setDraft((x) => ({ ...x, maxAge: v }));
                      }}
                    />
                  </View>

                  <Cta label={INTENT.next()} onPress={() => setStep('nature')} />
                </View>
              ) : null}

              {/*
                Четвёртый шаг: характер. Оси те же, что заполняет тест личности, — просить можно
                только то, что у кандидата в профиле есть. Ничего не отметив, человек не сужает
                поиск: подсказка говорит это прямо, потому что молчащий фильтр люди трактуют как
                «значит, ищет всех подряд».
              */}
              {step === 'nature' ? (
                <View style={s.card}>
                  <LabelRow Icon={IconPerson} text={DETAILS.nature()} />
                  <Text style={s.natureHint}>{DETAILS.natureHint()}</Text>
                  <View style={s.chipRowWrap}>
                    {NATURE_TRAITS.map((t) => {
                      const on = draft.nature[t.axis] === t.token;
                      const full = Object.keys(draft.nature).length >= NATURE_MAX;
                      // Забита ли ось — видно по тому, что в ней уже стоит другой токен: тогда
                      // нажатие ЗАМЕНЯЕТ, а не добавляет, и потолок не мешает.
                      const busyAxis = !!draft.nature[t.axis];
                      const blocked = !on && !busyAxis && full;
                      return (
                        <Chip
                          key={t.axis + t.token}
                          label={t.label()}
                          on={on}
                          dim={blocked}
                          onPress={() =>
                            setDraft((x) => {
                              const next = { ...x.nature };
                              if (on) delete next[t.axis];
                              else if (blocked) return x;
                              else next[t.axis] = t.token;
                              return { ...x, nature: next };
                            })
                          }
                        />
                      );
                    })}
                  </View>
                  {Object.keys(draft.nature).length >= NATURE_MAX ? (
                    <Text style={s.natureHint}>{DETAILS.natureLimit()}</Text>
                  ) : null}

                  <Cta label={INTENT.next()} onPress={() => setStep(lastStep)} />
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => { setDraft((x) => ({ ...x, nature: {} })); setStep(lastStep); }}
                  >
                    <Text style={s.natureSkip}>{DETAILS.natureSkip()}</Text>
                  </Pressable>
                </View>
              ) : null}

              {step === 'link' ? (
                <View style={s.card}>
                  {linkBlock}
                  <Cta label={INTENT.next()} disabled={linkBroken} onPress={toSummary} />
                </View>
              ) : null}

              {/*
                HY.09 — «3 of 3 · place and link». У гибрида шаг ОДИН, но в нём оба блока: борд
                говорит это прямо на HY.20a/20b — «hybrid needs both». Раньше гибрид шёл по ветке
                ссылки, то есть места у него не было вовсе: тому, кто хотел прийти живьём, приходить
                было некуда, а радиус поиска не задавался ничем.
              */}
              {step === 'both' ? (
                <View style={s.card}>
                  {placeBlock}
                  <View style={s.bothSplit} />
                  {linkBlock}
                  <Cta label={INTENT.next()} disabled={linkBroken} onPress={toSummary} />
                </View>
              ) : null}

              {step === 'place' ? (
                <View style={s.card}>
                  {placeBlock}
                  <Cta label={INTENT.next()} onPress={toSummary} />
                </View>
              ) : null}

              {step === 'summary' ? (
                <SummaryCard
                  topic={title}
                  where={where}
                  nature={natureSummary}
                  draft={draft}
                  category={category}
                  busy={busy}
                  onStart={finish}
                  // O.10a: «Поправить» спрашивает, ЧТО менять, а не гонит через весь мастер заново.
                  onEdit={() => { setEditPick(''); setEditOpen(true); }}
                />
              ) : null}
            </>
          )}

          {err ? <Text style={s.err}>{err}</Text> : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          <View style={s.field}>
            <TextInput
              style={s.input}
              value={free}
              onChangeText={setFree}
              placeholder={COMPOSER_PLACEHOLDER()}
              placeholderTextColor={color.neutral400}
              onSubmitEditing={send}
              returnKeyType="send"
              editable={!busy}
            />
            <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send')} onPress={send}>
              <IconMic />
            </Pressable>
          </View>
        </View>

        {/* O.07a — часовой пояс. Выбор живёт в tzPick и попадает в черновик только по «Применить». */}
        <EditSheet
          open={tzOpen}
          title={DETAILS.tzSheetTitle()}
          onClose={() => setTzOpen(false)}
          onAccept={() => { if (tzPick) setDraft((x) => ({ ...x, tz: tzPick })); setTzOpen(false); }}
          acceptLabel={DETAILS.apply()}
          cancelLabel={DETAILS.cancel()}
        >
          {tzOptions().map((z) => (
            <Pressable
              key={z}
              accessibilityRole="button"
              accessibilityState={{ selected: z === tzPick }}
              style={[s.pickRow, z === tzPick && s.pickRowOn]}
              onPress={() => setTzPick(z)}
            >
              <Text style={s.pickText}>{tzCity(z)}</Text>
              {z === tzPick ? <Text style={s.pickCheck}>✓</Text> : null}
            </Pressable>
          ))}
        </EditSheet>

        {/* O.10a — что менять в собранном интенте. «Изменить» ведёт на шаг подсвеченной строки. */}
        <EditSheet
          open={editOpen}
          title={EDIT_SHEET.title()}
          onClose={() => setEditOpen(false)}
          onAccept={() => {
            if (!editPick) return;
            setEditOpen(false);
            // Тема выбирается в разговоре создания, у мастера такого шага нет — «Изменить» по ней
            // честно возвращает в тот разговор.
            if (editPick === 'theme') { router.back(); return; }
            setStep(editPick as IntentStepId);
          }}
          acceptLabel={EDIT_SHEET.edit()}
          cancelLabel={DETAILS.cancel()}
        >
          {([
            ['theme', IconPencil, EDIT_SHEET.theme(), title || '—'],
            ['how', IconVideo, EDIT_SHEET.mode(), draft.mode ? formatLabel(draft.mode) : '—'],
            ['size', IconGroups, EDIT_SHEET.format(), draft.size ? sizeLabel(draft.size) : '—'],
            ['when', IconClock, EDIT_SHEET.datetime(), `${summaryDate(draft.date)}, ${hhmm(draft.minutes)}`],
            ['who', IconPerson, EDIT_SHEET.audience(),
              `${draft.sex && draft.sex !== 'Any' ? sexLabel(draft.sex) + ', ' : ''}${draft.minAge}–${draft.maxAge}`],
            ['nature', IconStar, DETAILS.nature(), natureSummary || EDIT_SHEET.noData()],
            draft.mode === 'hybrid'
              ? ['both', IconPlusRound, DETAILS.bothRow(),
                  [draft.address?.trim() || where, draft.link.trim()].filter(Boolean).join(' · ')
                    || EDIT_SHEET.noData()]
              : draft.mode === 'offline'
                ? ['place', IconPin, DETAILS.district(),
                    draft.address?.trim() || where || EDIT_SHEET.noData()]
                : ['link', IconLink, EDIT_SHEET.link(), draft.link.trim() || EDIT_SHEET.noData()],
          ] as [string, any, string, string][]).map(([k, Icon, label, value]) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              accessibilityState={{ selected: editPick === k }}
              style={[s.pickRow, editPick === k && s.pickRowOn]}
              onPress={() => setEditPick(k)}
            >
              <Icon size={20} c={color.fg} />
              <View style={{ flex: 1 }}>
                <Text style={s.pickText}>{label}</Text>
                <Text style={s.pickSub} numberOfLines={1}>{value}</Text>
              </View>
              {editPick === k ? <Text style={s.pickCheck}>✓</Text> : null}
            </Pressable>
          ))}
        </EditSheet>

        {busy ? <Searching onCancel={cancelSearch} /> : null}
      </View>
    </KeyboardAvoidingView>
  );
}

/** Красная точка + вопрос — так на всех кадрах мастера. У деталей под ним серый подвопрос. */
function QuestionHead({ title, sub }: { title: string; sub?: string }) {
  return (
    <View style={s.qhead}>
      <View style={s.qrow}>
        <View style={s.qdot} />
        <Text style={s.qtitle}>{title}</Text>
      </View>
      {sub ? <Text style={s.qsub}>{sub}</Text> : null}
    </View>
  );
}

/** Строка O.05/O.06: иконка, заголовок с подписью, красная галочка на выбранной. */
function OptionRow({
  Icon, title, sub, on, onPress,
}: {
  Icon: (p: any) => React.ReactElement;
  title: string;
  sub: string;
  on?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      onPress={onPress}
      style={({ pressed }) => [s.opt, on && s.optOn, pressed && { opacity: 0.9 }]}
    >
      <Icon size={22} c={color.fg} />
      <View style={{ flex: 1 }}>
        <Text style={s.optTitle}>{title}</Text>
        <Text style={s.optSub}>{sub}</Text>
      </View>
      {on ? <Text style={s.tick}>✓</Text> : null}
    </Pressable>
  );
}

/** «Awesome!» и точки печати — пауза между выбором и следующим вопросом, как на кадрах. */
function Ack() {
  return (
    <View style={{ gap: 6, marginTop: space.md }}>
      <View style={s.ackBub}><Text style={s.ackText}>{INTENT.awesome()}</Text></View>
      <View style={[s.ackBub, { width: 64 }]}><ActivityIndicator size="small" color={color.muted} /></View>
    </View>
  );
}

/** Степпер 1–2–3 с кадров O.07–O.09: пройденное и текущее — красным, дальше — серым. */
function Stepper({ current }: { current: number }) {
  return (
    <View style={s.stepper}>
      {[0, 1, 2, 3].map((i) => (
        <React.Fragment key={i}>
          {i > 0 ? <View style={[s.stepLine, i <= current && s.stepLineOn]} /> : null}
          <View style={[s.stepDot, i <= current && s.stepDotOn, i === current && s.stepDotNow]}>
            <Text style={[s.stepNum, i <= current && s.stepNumOn]}>{i + 1}</Text>
          </View>
        </React.Fragment>
      ))}
    </View>
  );
}

function LabelRow({ Icon, text }: { Icon: (p: any) => React.ReactElement; text: string }) {
  return (
    <View style={s.labelRow}>
      <Icon size={18} c={color.fg} />
      <Text style={s.label}>{text}</Text>
    </View>
  );
}

function Chip({
  label, on, dim, onPress,
}: { label: string; on?: boolean; dim?: boolean; onPress?: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on, disabled: !!dim }}
      onPress={onPress}
      style={({ pressed }) => [s.chip, on && s.chipOn, dim && { opacity: 0.4 }, pressed && { opacity: 0.85 }]}
    >
      <Text style={[s.chipText, on && { color: color.onPrimary }]}>{label}</Text>
    </Pressable>
  );
}

/** Маленькое числовое поле под циферблатом — «20 : 00» и «18 – 28» с кадров. */
function NumBox({ value, onChange }: { value: string; onChange: (t: string) => void }) {
  return (
    <TextInput
      style={s.numBox}
      value={value}
      onChangeText={onChange}
      keyboardType="number-pad"
      maxLength={2}
      selectTextOnFocus
      accessibilityLabel={value}
    />
  );
}

function Cta({ label, onPress, disabled, busy }: {
  label: string; onPress?: () => void; disabled?: boolean; busy?: boolean;
}) {
  const off = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      // И проп, и состояние: на вебе только disabled превращается в одноимённый атрибут кнопки —
      // accessibilityState до aria-disabled в нашей версии react-native-web не доезжает.
      disabled={!!off}
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      onPress={off ? undefined : onPress}
      style={({ pressed }) => [s.cta, { opacity: off ? 0.45 : pressed ? 0.9 : 1 }]}
    >
      {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{label}</Text>}
    </Pressable>
  );
}

/**
 * O.10 — сводка перед поиском: обложка, тема, факты строками, сводка Kleal, «Начать поиск» и
 * «Поправить». Обложки-фотографии в данных нет — цветное поле со значком, как везде в каркасе:
 * рисовать фотографию, которой нет, не из чего.
 */
function SummaryCard({
  topic, draft, category, where, nature, busy, onStart, onEdit,
}: {
  topic: string;
  draft: Draft;
  /** Отмеченные черты одной строкой. Собраны на экране — здесь только показываются. */
  nature: string;
  category: string;
  /** Подпись места в сводке: город профиля — район на OF.09 задаёт карта, а не список. */
  where: string;
  busy: boolean;
  onStart: () => void;
  onEdit: () => void;
}) {
  const facts: [string, string][] = [
    [SUMMARY_O10.mode(), draft.mode ? formatLabel(draft.mode) : '—'],
    [SUMMARY_O10.format(), draft.size ? sizeLabel(draft.size) : '—'],
    ...(category ? ([[SUMMARY_O10.category(), category]] as [string, string][]) : []),
    ...(nature ? ([[DETAILS.nature(), nature]] as [string, string][]) : []),
    [SUMMARY_O10.audience(),
      `${draft.sex && draft.sex !== 'Any' ? sexLabel(draft.sex) + ', ' : ''}${draft.minAge}–${draft.maxAge}`],
  ];
  return (
    <View style={s.card}>
      <View style={s.cover}><IconImagePlaceholder size={44} /></View>
      {topic ? <Text style={s.sumTopic}>{topic}</Text> : null}

      <View style={s.sumMeta}>
        <IconCalendar />
        <Text style={s.sumMetaText}>{summaryDate(draft.date)}</Text>
        <IconClock />
        <Text style={s.sumMetaText}>{hhmm(draft.minutes)} {tzOffsetLabel(draft.tz)}</Text>
      </View>
      {/* Гибрид показывает ОБЕ строки: у него и место, и ссылка (HY.09). Раньше условие места
          было привязано к офлайну, и гибрид уезжал в поиск, показав человеку только ссылку. */}
      {draft.mode !== 'offline' && draft.link.trim() ? (
        <View style={s.sumMeta}>
          <IconLink size={16} c={color.muted} />
          <Text style={s.sumMetaText} numberOfLines={1}>{draft.link.trim()}</Text>
        </View>
      ) : null}
      {draft.mode !== 'online' && where ? (
        <View style={s.sumMeta}>
          <IconPin size={16} c={color.muted} />
          <Text style={s.sumMetaText}>{where} · {draft.radiusKm} km</Text>
        </View>
      ) : null}

      {facts.map(([k, v]) => (
        <View key={k} style={s.sumRow}>
          <Text style={s.sumKey}>{k}</Text>
          <Text style={s.sumVal}>{v}</Text>
        </View>
      ))}

      <View style={s.sumSummaryBox}>
        <View style={s.sumSummaryHead}>
          <Text style={s.sumSummaryLabel}>{SUMMARY_O10.summaryLabel()}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel={SUMMARY_O10.edit()} onPress={onEdit} hitSlop={8}>
            <IconPencil size={18} />
          </Pressable>
        </View>
        <Text style={s.sumSummaryText}>
          {intentSummaryText({
            topic, size: draft.size, sex: draft.sex,
            minAge: draft.minAge, maxAge: draft.maxAge,
            dateKey: draft.date, minutes: draft.minutes,
            nature: nature,
          })}
        </Text>
      </View>

      <Cta label={SUMMARY_O10.start()} busy={busy} onPress={onStart} />
      <Pressable accessibilityRole="button" style={s.sumEditBtn} onPress={onEdit}>
        <Text style={s.sumEditText}>{SUMMARY_O10.edit()}</Text>
      </Pressable>
    </View>
  );
}

/**
 * OF.11 — пока идёт поиск. Накладкой поверх мастера, а не отдельным маршрутом: экран живёт секунды
 * и не должен оставаться в истории — иначе «назад» из выдачи возвращало бы человека в бесконечное
 * ожидание того, что уже нашлось.
 */
/**
 * Вуаль поиска.
 *
 * Две вещи, которых тут не было и из-за которых экран называли «висит»: через шесть секунд он
 * говорит, что дольше обычного, а выход есть с первой секунды. Подбор занимает полторы секунды —
 * всё, что дольше, уже нештатно, и молчащий кружок в этот момент неотличим от зависания.
 */
function Searching({ onCancel }: { onCancel?: () => void }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setSlow(true), 6000);
    return () => clearTimeout(id);
  }, []);
  return (
    <View style={s.veil}>
      {/* Кадр O.11: два круга-заглушки под иллюстрации и подпись Kleal. Иллюстраций в проекте
          нет — честная заглушка, как везде в каркасе. */}
      <View style={s.veilAva}><IconImagePlaceholder size={28} /></View>
      <Text style={s.veilBrand}>Kleal</Text>
      <View style={s.veilBig}><IconImagePlaceholder size={44} /></View>
      <Text style={s.veilTitle}>{SEARCHING.title()}</Text>
      <View style={s.veilRow}>
        <ActivityIndicator size="small" color={color.primary} />
        <Text style={s.veilStep}>{SEARCHING.step()}</Text>
      </View>
      <Text style={s.veilNote}>{slow ? SEARCHING.slow() : SEARCHING.note()}</Text>
      {onCancel ? (
        <Pressable accessibilityRole="button" style={s.veilCancel} onPress={onCancel} hitSlop={10}>
          <Text style={s.veilCancelText}>{SEARCHING.cancel()}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  allBtn: { height: 40, paddingHorizontal: 16, borderRadius: rad.full, backgroundColor: color.primary, justifyContent: 'center' },
  allText: { ...type.labelMedium, color: color.onPrimary } as any,

  body: { paddingHorizontal: 20, paddingBottom: space.lg, gap: space.sm },
  qhead: { marginTop: space.sm, marginBottom: space.sm, gap: 6 },
  qrow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  qdot: { width: 26, height: 26, borderRadius: 13, backgroundColor: color.primary },
  qtitle: { flex: 1, fontSize: 21, fontWeight: '700', color: color.fg },
  qsub: { ...type.bodySmall, color: color.muted, marginLeft: 36 } as any,

  opt: {
    flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16,
    borderRadius: rad.lg, backgroundColor: color.card, borderWidth: 1, borderColor: color.border,
  },
  optOn: { borderColor: color.primary },
  optTitle: { ...type.title, color: color.fg } as any,
  optSub: { ...type.bodySmall, color: color.muted, marginTop: 2 } as any,
  tick: { color: color.primary, fontSize: 20, fontWeight: '700' },

  ackBub: {
    alignSelf: 'flex-start', backgroundColor: color.neutral100, borderRadius: 16,
    paddingVertical: 12, paddingHorizontal: 14, alignItems: 'center',
  },
  ackText: { ...type.body, color: color.fg } as any,

  stepper: { flexDirection: 'row', alignItems: 'center', marginVertical: space.sm },
  stepDot: {
    width: 26, height: 26, borderRadius: 13, borderWidth: 1.5, borderColor: color.neutral300,
    alignItems: 'center', justifyContent: 'center', backgroundColor: color.card,
  },
  stepDotOn: { borderColor: color.primary },
  stepDotNow: { borderWidth: 2.5 },
  stepNum: { fontSize: 12, fontWeight: '600', color: color.muted },
  stepNumOn: { color: color.primary },
  stepLine: { flex: 1, height: 2, backgroundColor: color.neutral100 },
  stepLineOn: { backgroundColor: color.primary },

  card: {
    backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.md,
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 2,
  },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  chipRow: { gap: space.sm, paddingVertical: 2 },
  natureHint: { ...type.bodySmall, color: color.muted } as any,
  /** Разделитель между «где» и «куда звонить» на шаге гибрида: два блока, а не один длинный. */
  bothSplit: { height: 1, backgroundColor: color.border, marginVertical: space.sm },
  natureSkip: { ...type.labelMedium, color: color.muted, textAlign: 'center', paddingVertical: space.sm } as any,
  chipRowWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,

  boxRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  numBox: {
    width: 56, height: 40, borderRadius: rad.md, backgroundColor: color.neutral100,
    textAlign: 'center', color: color.fg, fontSize: 16, fontWeight: '600',
  },
  boxColon: { fontSize: 18, color: color.muted },

  tzRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6 },
  tzLabel: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  tzValue: { ...type.bodySmall, color: color.muted } as any,

  // Строки листов O.07a/O.10a: выбранная — в рамке с галочкой, как на кадрах.
  pickRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 12, paddingHorizontal: 14,
    borderWidth: 1, borderColor: 'transparent', borderRadius: rad.lg,
  },
  pickRowOn: { borderColor: color.primary },
  pickText: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  pickSub: { ...type.bodySmall, color: color.muted } as any,
  pickCheck: { fontSize: 16, color: color.primary, fontWeight: '700' },
  chev: { fontSize: 16, color: color.muted },

  linkInput: {
    height: 48, borderRadius: rad.md, backgroundColor: color.neutral100,
    paddingHorizontal: 14, color: color.fg, fontSize: 15,
  },
  noteRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  note: { flex: 1, ...type.caption, color: color.muted } as any,

  radiusRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  radiusValue: { ...type.body, color: color.primary, fontWeight: '600' } as any,
  /** OF.09: карта района — та же, что в онбординге и профиле. */
  map: { height: 200, borderRadius: rad.lg, overflow: 'hidden', backgroundColor: color.neutral100 },
  mapHintRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginTop: -space.sm },
  mapHint: { flex: 1, ...type.caption, color: color.muted } as any,
  mapReset: { ...type.caption, color: color.primary, fontWeight: '700' } as any,
  /** OF.09: приватность места — серой строкой под полем, как на кадре. */
  privacyNote: { ...type.caption, color: color.muted } as any,

  cta: {
    height: 52, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: space.sm,
  },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  err: { ...type.bodySmall, color: color.primary, marginTop: space.sm } as any,

  dock: { paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.bg },
  field: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },

  cover: {
    height: 128, borderRadius: rad.lg, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  sumTopic: { fontSize: 19, fontWeight: '700', color: color.fg },
  sumMeta: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sumMetaText: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  sumRow: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
  sumKey: { ...type.bodySmall, color: color.muted } as any,
  sumVal: { ...type.bodySmall, color: color.fg, flex: 1, textAlign: 'right' } as any,
  sumSummaryBox: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md, gap: 6 },
  sumSummaryHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sumSummaryLabel: { ...type.labelMedium, color: color.primary, fontWeight: '700' } as any,
  sumSummaryText: { ...type.bodySmall, color: color.fg } as any,
  sumEditBtn: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  sumEditText: { ...type.button, color: color.fg } as any,

  veil: {
    ...StyleSheet.absoluteFillObject, backgroundColor: color.bg, alignItems: 'center',
    justifyContent: 'center', gap: space.md, paddingHorizontal: 32,
  },
  veilAva: {
    width: 96, height: 96, borderRadius: 48, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  veilBrand: { ...type.title, color: color.fg, fontWeight: '700' } as any,
  veilBig: {
    width: 148, height: 148, borderRadius: 74, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center', marginTop: space.md,
  },
  veilRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  veilTitle: { fontSize: 24, lineHeight: 31, fontWeight: '700', color: color.fg, textAlign: 'center' },
  veilStep: { ...type.body, color: color.primary, textAlign: 'center' } as any,
  veilNote: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,
  veilCancel: {
    marginTop: space.xl, height: 44, paddingHorizontal: 24, borderRadius: rad.full,
    borderWidth: 1, borderColor: color.border, backgroundColor: color.card,
    alignItems: 'center', justifyContent: 'center',
  },
  veilCancelText: { ...type.button, color: color.fg } as any,
});
