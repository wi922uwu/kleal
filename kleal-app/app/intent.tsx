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
  KeyboardAvoidingView, Platform, useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Stack, useRouter, useLocalSearchParams, useNavigation } from 'expo-router';
// Свайп от края (iOS) и аппаратная «назад» (Android) снимают экран мимо любого обработчика
// кнопки. Единственный способ вклиниться — usePreventRemove; expo-router его не реэкспортирует,
// поэтому берём из навигатора, на котором он и построен.
import { usePreventRemove } from 'expo-router/react-navigation';
import {
  INTENT, IntentStepId, FORMATS, formatLabel, SIZES, sizeLabel, GROUP_MIN_TOTAL, GROUP_FREE_MAX_TOTAL, normalizeIntentSize, initialGroupSize, DETAILS, EDIT_SHEET, dateChips, timeQueryFromDate, deviceTz, looksLikeUrl, withScheme, categoryLabel, SEARCHING, SUMMARY_O10, tzOffsetLabel, hhmm, planWhenLabel, rollIntentName, intentNameOptions, WIZ, AGE_PRESETS, agePresetLabel, dayChips, TIME_SLOTS, cardDate, tzPlace, tzChoices, wizSummary,
} from '../src/intent';
import { COMPOSER_PLACEHOLDER, COMPOSER_LOCKED } from '../src/onboarding';
import { RadiusMap } from '../src/components/RadiusMap';
import {
  IconPin, IconVideo, IconPerson, IconCalendar, IconClock, IconLink, IconPencil, IconStar, IconDice, IconGlobe, IconPinPlus, IconUsers, IconUserPlus, IconChevronDown, IconMaximize, IconMinimize, IconPinSolid, IconCrosshair, IconHelp, IconLock, IconChevronUp, IconWand,
} from '../src/components/icons';
import {
  CreatingHeader, StepAsk, AgentLine, MyLine, Caption, PrefLabel, ChoiceRow, Check, GlassChip, ChipRow,
  ChipScroller, StepIndicator, CreateComposer, RadiusSlider,
} from '../src/components/CreateFlow';
import { GlassPill } from '../src/components/Glass';
import { GlassIconButton, GlassSurface } from '../src/components/LiquidGlass';
import { SheetText } from '../src/components/Sheet';
import { Sheet } from '../src/components/Sheet';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { resetGroupSession } from '../src/ginvites';
import { useLang, T, replyLang } from '../src/i18n';
import { AddressField } from '../src/components/AddressField';
import { useOnb } from '../src/state';
import { setResults, patchResults } from '../src/results-store';
import { openResults } from '../src/results-navigation';
import { beginIntentEdit, IntentEditTarget } from '../src/intent-edit';
import { agent, isAbort, buddy as buddyApi } from '../src/api';
import { CREATE } from '../src/buddy';
import { color, font, heading, radius as rad, space, type } from '../src/theme';
import { reverseGeocode } from '../src/geocode';
import * as Location from 'expo-location';
import { Cover } from '../src/components/Cover';
import { IntentPlate } from '../src/components/IntentChips';
import { KlealMood } from '../src/components/KlealMood';
import { parseIntentChange } from '../src/intent-talk';

type Draft = {
  mode?: string;
  size?: '1:1' | 'group';
  /** Полный состав, включая организатора. Отдельное видимое решение внутри единого Group-flow. */
  groupSize?: number;
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
  /**
   * Координаты пришли ОТ АДРЕСА, а не от перетаскивания булавки. Разница решает, можно ли ставить
   * их на общую карту точно.
   *
   * Булавка на карте радиуса — это «ищи вокруг вон той точки», то есть место, где человек
   * находится. Такое публиковать нельзя: контракт geo_privacy держит домашнюю точку огрублённой,
   * и это правильно. Адрес же он называет сам и именно для того, чтобы туда пришли, — площадка не
   * его дом, и прятать её незачем (`can_be_first_meeting_place` в том же контракте прямо отделяет
   * место встречи от домашнего и рабочего).
   */
  venue?: boolean;
};

/**
 * Ближайшее время ряда GR.09, которое ещё не прошло: следующий получасовой слот через час от
 * «сейчас», но не раньше 19:00 — на кадре вечер, и большинство затей вечерние. После 22:30 —
 * 19:00 следующего дня считать нечем (дата на шаге «сегодня»), поэтому просто 23:30.
 */
function firstFreeSlot(now = new Date()): number {
  const m = now.getHours() * 60 + now.getMinutes() + 60;
  const slot = Math.ceil(m / 30) * 30;
  return Math.min(23 * 60 + 30, Math.max(19 * 60, slot));
}

export default function Intent() {
  useLang();
  const router = useRouter();
  /** Нужен ровно для одного: пропустить дальше действие, которое перехват задержал по ошибке. */
  const nav = useNavigation();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const win = useWindowDimensions();
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
  const params = useLocalSearchParams<{
    topics?: string; title?: string; topic?: string;
    size?: string; format?: string; groupSize?: string;
    type?: string;
    /** Только для стенда сверки с бордом (EXPO_PUBLIC_HARNESS=1): открыть мастер сразу на шаге. */
    step?: string;
  }>();
  /**
   * Свидание — ТИП затеи из разговора создания, а не ключ темы. Терялся здесь: мастер слал в поиск
   * темы и заголовок, и свидание искалось как обычная встреча — без ворот `datingOk` у кандидата.
   */
  const dating = String(params.type || '').trim().toLowerCase() === 'dating';
  const legacy = String(params.topic || '').trim();
  const paramTopics = String(params.topics || legacy || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  /*
    ТЕМЫ ПОИСКА ИДУТ ЗА НАЗВАНИЕМ (GR.12c). Темы приходят из разговора создания вместе с
    названием. Раньше правка «What» на сводке меняла только надпись: карточка называлась «Book
    club», а искали по `bbq, beach`. Теперь новое название разбирает агент фильтрации
    (/api/filter/categorize — он и даёт ключи, понимает и русский), и поиск идёт по новым темам.
  */
  const [topics, setTopics] = useState<string[]>(paramTopics);
  /** Пока темы нового названия едут, «Start search» ждёт: иначе поиск ушёл бы по старым. */
  const [retopic, setRetopic] = useState(false);
  const paramTitle = String(params.title || legacy || '').trim();
  /*
    НАЗВАНИЕ ЖИВЁТ В СОСТОЯНИИ, А НЕ В ПАРАМЕТРЕ МАРШРУТА, потому что его теперь можно менять
    костями на сводке. Параметр остаётся начальным значением: он пришёл из разговора создания и
    правильно быть первым предложением.
  */
  const [title, setTitle] = useState(paramTitle);

  const [step, setStep] = useState<IntentStepId>('how');
  const legacySize = params.size ?? params.format;
  const normalizedSize = normalizeIntentSize(legacySize, params.groupSize);
  /** Plus в продукте ещё не подключён, но диапазон 6–20 остаётся видимой частью Group-flow. */
  const [groupSizeOpen, setGroupSizeOpen] = useState(false);
  const [groupSizeTarget, setGroupSizeTarget] = useState<'draft' | 'edit'>('draft');
  const [draft, setDraft] = useState<Draft>(() => ({
    size: normalizedSize,
    groupSize: normalizedSize === 'group' ? initialGroupSize(legacySize, params.groupSize) : undefined,
    date: dateChips(1)[0].key,
    minutes: firstFreeSlot(),
    tz: deviceTz(),
    /*
      ВОЗРАСТ ПО УМОЛЧАНИЮ — «Any age» ([0, 0], без рамки). Раньше стояли 18–28 с кадра O.08, а
      сервер читает любой minAge как жёсткий гейт: «до 28» отсекал и тех, у кого возраст просто не
      указан (см. prefsFromIntent в app/results.tsx). На GR.10 возраст — чипы, и «любой» среди них
      есть; выбирает его человек, а не мы за него.
    */
    minAge: 0,
    maxAge: 0,
    nature: {},
    radiusKm: 15,
    link: '',
  }));
  /*
    СТЕНД СВЕРКИ С БОРДОМ. Локальный Metro стенда задаёт EXPO_PUBLIC_HARNESS=1, и тогда ссылка
    `/intent?step=summary` открывает мастер сразу на нужном шаге с ответами кадров (Offline, группа
    из трёх, 25–35). На боксе переменной нет — Metro подставляет undefined, и ветка мертва.
  */
  useEffect(() => {
    if (process.env.EXPO_PUBLIC_HARNESS !== '1' || !params.step) return;
    const hm = String((params as any).mode || 'offline');
    const hs = (params as any).size === '1:1' ? '1:1' : 'group';
    setDraft((d) => ({ ...d, mode: hm, size: hs, groupSize: hs === 'group' ? 3 : undefined, minAge: 25, maxAge: 35 }));
    // `change` — режим GR.12a, `edit` — сразу лист GR.12b (снимать кадры листа без пяти нажатий).
    const st = String(params.step);
    setStep((st === 'change' || st === 'edit' ? 'summary' : st) as IntentStepId);
    if (st === 'change') setChanging(true);
    if (st === 'edit') setTimeout(() => {
      setDraft((d) => { setEdraft(beginIntentEdit(d)); return d; });
      setEtitle(paramTitle);
      setEditOpen(true);
    }, 400);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Между шагом и шагом агент отвечает «Awesome!» и печатает — как на кадрах. */
  const [ack, setAck] = useState(false);
  /**
   * Пауза «Awesome!» держит таймер, и его идентификатор нигде не хранился. «Назад», нажатая в
   * эти 900 мс, отступала на шаг — а потом таймер всё равно доводил движение ВПЕРЁД, и человек
   * возвращался туда, откуда только что ушёл.
   */
  const ackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [busy, setBusy] = useState(false);
  /** Живой запрос поиска — чтобы кнопка «Отменить» рвала именно его. */
  const abortRef = useRef<AbortController | null>(null);
  const [err, setErr] = useState('');
  const [dragging, setDragging] = useState(false);
  /** O.07a: лист пояса держит выбор у себя и отдаёт его в черновик только по «Применить». */
  const [tzOpen, setTzOpen] = useState(false);
  const [tzPick, setTzPick] = useState('');
  /**
   * O.10a: лист правки над сводкой. editPick — РАСКРЫТАЯ строка (одна за раз: лист растёт вверх
   * по содержимому, и двух крупных полей разом он не выдерживает).
   *
   * edraft — черновик самого листа. Контролы шагов пишут в состояние немедленно, и если пустить
   * их прямо в draft, «Отмена» станет враньём: лист закроется, а правки останутся. Правило листа
   * записано в src/components/ProfileShell.tsx и здесь соблюдается так же, как в листе пояса.
   */
  const [editOpen, setEditOpen] = useState(false);
  /** Выбранный параметр — одновременно режим листа и белый список полей для commit. */
  const [editPick, setEditPick] = useState<IntentEditTarget | ''>('');
  const [edraft, setEdraft] = useState<Draft | null>(null);
  const [free, setFree] = useState('');
  /** Категория для строки сводки O.10. Приходит от агента фильтрации; пусто — строка не рисуется. */
  const [category, setCategory] = useState('');
  /**
   * GR.12a: после «Change it» шаг сводки показывает два пути правки — «Edit it myself» и «скажи
   * Kleal». Это режим того же шага (100%), а не новый экран: на кадре шапка и проценты те же.
   */
  const [changing, setChanging] = useState(false);
  /**
   * GR.11a: лист с картой. Держит СВОЙ черновик точки — «Back» ничего не меняет, «Use this spot»
   * отдаёт точку и адрес тому черновику, из которого лист открыли (шаг мастера или лист правки).
   */
  const [spotOpen, setSpotOpen] = useState(false);
  const [spot, setSpot] = useState<{ lat: number; lon: number; address: string; area: string }>({ lat: 0, lon: 0, address: '', area: '' });
  const spotSet = useRef<SetDraft | null>(null);
  /** Лист точки открыт ИЗ листа правки — тогда он рисуется внутри него, а не вторым модалом. */
  const spotInEdit = useRef(false);

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
    openResults(router);
  };

  /**
   * Свободный текст. Человек, описавший затею словами, не проходит шаги, на которые уже ответил:
   * текст уходит модели целиком (/api/agent/plan) и ведёт сразу к выдаче.
   */
  const send = async () => {
    const text = free.trim();
    if (!text || busy) return;
    if (step !== 'summary') return;            // шаги с выбором: поле закрыто (см. CreateComposer locked)
    // GR.12a: на сводке текст — это правка сводки, а не новый запрос (заметка к кадру).
    if (step === 'summary' && changing) { setFree(''); talkChange(text); return; }
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
                        : T('Связь пропала. Повторишь?', 'I lost the connection. Say that again?', 'Perdí la conexión. ¿Lo repites?'));
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
      /**
       * Та же подпись, но для МОСТА ТЕМ на сервере, а не для глаз. В `topics` её класть нельзя и
       * никогда было нельзя: русская фраза буквально не совпадает ни с кем, и запрос возвращал
       * восемь «замен» вместо людей. Но фильтрации нужен именно контекст: измерено — «поговорить
       * про опционы» она разбирает как [options, trading, finance, investing], а голое «options»
       * как [choice, selection, alternatives]. То есть без фразы мост строится к «вариантам
       * выбора», а не к финансам. Отдельным полем: сравнения по нему нет, только разбор.
       */
      ...(title ? { phrase: title } : {}),
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
      // Сохраняется вместе с затеей: повторный поиск из «Моей активности» и выдачи берёт её целиком.
      ...(dating ? { type: 'dating' } : {}),
    };
    if (draft.size === 'group') intent.groupSize = draft.groupSize || GROUP_MIN_TOTAL;
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
      /*
        КООРДИНАТЫ ЕДУТ В САМУ ЗАТЕЮ, а не только в профиль поиска.

        В профиль они клались и раньше — оттуда считается расстояние до кандидатов. Но карта
        рисует пины по координатам ЗАТЕИ, и без них она ставила встречу туда, где живёт автор:
        назначил в Грасии, а на карте пин у дома в Побленоу.

        На карту они уходят ОГРУБЛЁННЫМИ до зоны ~500 м — снапит сервер (`_zone_point` в
        services/matching). Точный адрес остаётся в `address` и открывается только плану после
        взаимного подтверждения, как и было.
      */
      // ТОЛЬКО КООРДИНАТЫ ПЛОЩАДКИ. Булавка карты радиуса сюда НЕ попадает: она означает «ищи
      // вокруг вон той точки», то есть где человек находится, и уезжает в профиль поиска, где и
      // нужна. На общую карту идёт только то, что человек назвал адресом встречи.
      if (draft.venue && draft.lat != null && draft.lon != null) {
        intent.lat = draft.lat;
        intent.lon = draft.lon;
      }
    }
    if (wantsLink) {
      // Иначе §5.3 требует город, которого у онлайн-встречи нет по определению. Гибриду это тоже
      // нужно, и по той же причине: половина его встречи — звонок, и радиус не должен НИКОГО
      // отсекать (кто далеко — подключится). Жёсткий гейт радиуса на сервере включён только для
      // mode == 'offline', так что гибрид получает радиус как предпочтение, а не как забор.
      intent.allowOnlineFallback = true;
      // Ссылку ранжирование не читает — она нужна ПОЗЖЕ, когда из мэтча собирается план встречи.
      // Кладётся в интент, чтобы уехать вместе с ним в выдачу, а не потеряться на этом экране.
      if (draft.link.trim()) intent.link = withScheme(draft.link);
    }
    // Публикация и запуск — одна durable-команда: результат содержит стабильный search ID.
    // Отдельной фоновой записи нет; ошибка не должна показывать успешный пустой поиск.
    // Отмена принадлежит человеку: экран поиска даёт кнопку, и она рвёт именно этот запрос.
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r: any = await agent.match(intent, profile(), ctx(), ctrl.signal);
      // СБОЙ ПОДБОРА — НЕ «НИКОГО НЕТ» (сверка п. 28). Сервер при ошибке отвечает 200 с пустым списком
      // и полем error; экран выдачи показывал «никого не нашлось», и человек уходил ни с чем.
      if (r?.error && !(r?.candidates || []).length) { setErr(SEARCHING.failed()); return; }
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
        if (c) setCategory(categoryLabel(c));
      })
      .catch(() => {});
  };

  /**
   * ПОЛЯ МАСТЕРА — ФУНКЦИИ ОТ ЧЕРНОВИКА, А НЕ ГОТОВЫЙ JSX.
   *
   * Каждое из них живёт теперь в двух местах: на своём шаге мастера (пишет прямо в draft) и в
   * листе правки со сводки (пишет в черновик листа, чтобы «Отмена» и правда отменяла). Скопировать
   * разметку в лист значило бы завести вторую копию — этот проект уже терял день на разъехавшихся
   * копиях подготовки фото и `languages`, см. AGENTS.md.
   *
   * Место и ссылка вдобавок стоят у гибрида на ОДНОМ шаге (HY.09), а у офлайна и онлайна — каждое
   * на своём: разойдись копии, разошлись бы именно у гибрида, которого меньше видно.
   */
  type SetDraft = (fn: (d: Draft) => Draft) => void;

  /** Битая ссылка не пускает ни «Дальше» на шаге, ни «Применить» в листе — правило одно на оба. */
  const linkBroken = (v: Draft) => !!v.link.trim() && !looksLikeUrl(v.link);
  /** В Group Online ссылка — третий обязательный шаг: без неё приглашённые придут в пустой звонок. */
  const groupOnline = draft.mode === 'online' && draft.size === 'group';
  const groupLinkBlocked = (v: Draft) =>
    // Ссылка не обязательна ни у кого (решение владельца 14.10): пустую добавляют позже, в плане. Битую — нет.
    linkBroken(v);

  /**
   * GR.07: строки «1:1» и «Group» с галочкой, а под выбранной группой — «How many, you included»
   * чипами 3 / 4 / 5 / 6+. Размер — часть того же шага, а не отдельный экран: на кадре это один вопрос.
   */
  const sizeBlockOf = (v: Draft, set: SetDraft) => (
    <View style={s.options}>
      {SIZES.map(([k]) => (
        <ChoiceRow
          key={k}
          Icon={k === '1:1' ? IconUsers : IconUserPlus}
          label={sizeLabel(k)}
          sub={WIZ.sizeSub(k)}
          on={v.size === k}
          onPress={() => set((x) => ({
            ...x,
            size: k as Draft['size'],
            groupSize: k === 'group' ? (x.groupSize || GROUP_MIN_TOTAL) : undefined,
          }))}
        />
      ))}
    </View>
  );

  /** GR.05: три формата строками с галочкой — тот же вид, что у размера. */
  const modeBlockOf = (v: Draft, set: SetDraft, locked = false) => (
    <View style={s.options}>
      {FORMATS.map(([k]) => (
        <ChoiceRow
          key={k}
          Icon={k === 'offline' ? IconPin : k === 'online' ? IconGlobe : IconPinPlus}
          label={formatLabel(k)}
          sub={WIZ.formatSub(k)}
          on={v.mode === k}
          disabled={locked && v.mode !== k}
          onPress={() => set((x) => ({ ...x, mode: k }))}
        />
      ))}
    </View>
  );

  /**
   * «How many, you included»: 3 / 4 / 5 / 6+. «6+» открывает лист Plus (GR.08) и сам размер не
   * ставит: на бесплатном тарифе группа до пяти, и выбор, которого нельзя получить, не должен
   * выглядеть выбранным.
   */
  const groupSizeBlockOf = (v: Draft, set: SetDraft, target: 'draft' | 'edit') => {
    const total = v.groupSize || GROUP_MIN_TOTAL;
    return (
      <View style={s.pref}>
        <PrefLabel text={WIZ.howMany()} />
        <ChipRow>
          {[3, 4, 5].map((n) => (
            <GlassChip key={n} label={String(n)} on={total === n}
              onPress={() => set((x) => ({ ...x, size: 'group', groupSize: n }))} />
          ))}
          <GlassChip label="6+" on={total > GROUP_FREE_MAX_TOTAL}
            onPress={() => { setGroupSizeTarget(target); setGroupSizeOpen(true); }} />
        </ChipRow>
      </View>
    );
  };

  /**
   * GR.09: «Day» — 14 дней рядом, «Time» — каждые 30 минут рядом, оба листаются вбок, и выбранный
   * чип при открытии докручен в поле зрения. «Time zone» — строка-выбор, лист GR.09a.
   *
   * Прошедшее время сегодняшнего дня выключено: план на 08:00, когда уже 14:00, сервер всё равно не
   * примет, и лучше не дать его выбрать, чем отказать после «Start search». Выбрал «Today», а
   * стоявшее время уже прошло — оно само сдвигается на ближайшее.
   */
  const whenBlockOf = (
    v: Draft,
    set: SetDraft,
    onPressTz?: () => void,
    only?: 'date' | 'time',
  ) => {
    const days = dayChips(14);
    const today = days[0].key;
    const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
    const past = (m: number) => v.date === today && m <= nowMin;
    return (
      <>
        {only !== 'time' ? (
          <View style={s.pref}>
            <PrefLabel text={WIZ.day()} />
            <ChipScroller
              items={days}
              selected={v.date}
              chipWidth={66}
              onPick={(k) => set((x) => {
                const nm = new Date().getHours() * 60 + new Date().getMinutes();
                const bump = k === today && x.minutes <= nm ? firstFreeSlot() : x.minutes;
                return { ...x, date: k, minutes: bump };
              })}
            />
          </View>
        ) : null}
        {only !== 'date' ? (
          <View style={s.pref}>
            <PrefLabel text={WIZ.time()} />
            <ChipScroller
              items={TIME_SLOTS.map((m) => ({ key: String(m), label: hhmm(m), disabled: past(m) }))}
              selected={String(v.minutes)}
              chipWidth={63}
              onPick={(k) => set((x) => ({ ...x, minutes: Number(k) }))}
            />
          </View>
        ) : null}
        {onPressTz ? (
          <View style={s.pref}>
            <PrefLabel text={WIZ.timeZone()} />
            <SelectField value={tzPlace(v.tz)} onPress={onPressTz} />
          </View>
        ) : null}
      </>
    );
  };

  /** «Use this spot»: точка, адрес и район уходят тому черновику, из которого лист открыли. */
  const useSpot = () => {
    const fn = spotSet.current;
    if (fn) fn((x) => ({
      ...x, lat: spot.lat, lon: spot.lon, venue: !!spot.address,
      address: spot.address || x.address,
      // В записку «Others see …» — только район, без города: на кадре «Barceloneta».
      district: (spot.area.split(',')[0] || '').trim() || x.district,
    }));
    setSpotOpen(false);
  };

  /** Открыть GR.11a: точка и адрес — из того черновика, который потом и получит выбор. */
  const openSpot = (set: SetDraft, v: Draft) => {
    spotSet.current = set;
    spotInEdit.current = editOpen;
    setSpot({ lat: v.lat ?? homeLat, lon: v.lon ?? homeLon, address: v.address || '', area: v.district || '' });
    setSpotOpen(true);
  };


  /** Чип возраста горит, когда его диапазон целиком внутри выбранной рамки. «Любой» — когда рамки нет. */
  const ageOn = (v: Draft, i: number) => {
    const [lo, hi] = AGE_PRESETS[i];
    const min = v.minAge || 0, max = v.maxAge || 0;
    if (!lo && !hi) return !min && !max;
    return !!(min || max) && lo >= min && hi <= max;
  };
  /** Нажатие: добавить или убрать диапазон и склеить выбранные в одну рамку. */
  const ageToggle = (v: Draft, i: number): { minAge: number; maxAge: number } => {
    const [lo, hi] = AGE_PRESETS[i];
    if (!lo && !hi) return { minAge: 0, maxAge: 0 };
    const ranges = AGE_PRESETS.map((r, k) => ({ r, k })).filter(({ r }) => r[0] || r[1]);
    let picked = ranges.filter(({ k }) => ageOn(v, k)).map(({ k }) => k);
    if (picked.includes(i)) {
      picked = picked.filter((k) => k !== i);
      // Убрали средний — рамка не может быть с дырой: оставляем часть выше него.
      if (picked.some((k) => k < i) && picked.some((k) => k > i)) picked = picked.filter((k) => k > i);
    } else {
      picked = [...picked, i];
      // Добавили через промежуток — промежуток входит в рамку и тоже загорается.
    }
    if (!picked.length) return { minAge: 0, maxAge: 0 };
    const sel = picked.map((k) => AGE_PRESETS[k]);
    return { minAge: Math.min(...sel.map((r) => r[0])), maxAge: Math.max(...sel.map((r) => r[1])) };
  };

  /** GR.10: «Who you’d like to meet» — Women / Men / Anyone, «Age» — три диапазона и «Any age». */
  const whoBlockOf = (v: Draft, set: SetDraft) => (
    <>
      <View style={s.pref}>
        <PrefLabel text={WIZ.whoPref()} />
        <ChipRow>
          {(['Female', 'Male', 'Any'] as const).map((k) => (
            <GlassChip key={k} label={WIZ.sexChip(k)} on={(v.sex || 'Any') === k}
              onPress={() => set((x) => ({ ...x, sex: k }))} />
          ))}
        </ChipRow>
      </View>
      <View style={s.pref}>
        <PrefLabel text={WIZ.age()} />
        <ChipRow>
          {/* Несколько диапазонов сразу (просьба тестировщиков 09.10): соседние чипы стыкуются,
              выбранные склеиваются в одну рамку minAge–maxAge. «Любой» снимает остальные. */}
          {AGE_PRESETS.map((r, i) => (
            <GlassChip key={i} label={agePresetLabel(r)} on={ageOn(v, i)}
              onPress={() => set((x) => ({ ...x, ...ageToggle(x, i) }))} />
          ))}
        </ChipRow>
      </View>
    </>
  );

  /** Ссылка на звонок (онлайн и гибрид): стеклянное поле 48 и записка с кадра O.09. */
  const linkBlockOf = (v: Draft, set: SetDraft) => (
    <View style={s.pref}>
      {/* GRO.11: у онлайн-группы над полем подписи нет — вопрос уже сказал, что вставлять. */}
      {v.mode === 'online' && v.size === 'group' ? null : <PrefLabel text={DETAILS.link()} />}
      <GlassSurface tone="light" radius={999} style={s.input48}>
        <TextInput
          style={s.inputText}
          value={v.link}
          onChangeText={(t) => set((x) => ({ ...x, link: t }))}
          placeholder={v.mode === 'online' ? WIZ.linkPhGroup() : DETAILS.linkPlaceholder()}
          placeholderTextColor={color.muted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          accessibilityLabel={DETAILS.link()}
        />
      </GlassSurface>
      {/* O.09: у звонка один на один ссылку получит только выбранный человек. */}
      <Caption text={v.mode !== 'online' ? DETAILS.linkNote() : v.size === 'group' ? WIZ.linkHintGroup() : WIZ.linkHintSolo()} />
      {/* Звонок и гибрид: пустое поле — не ошибка, ссылку добавят в плане. */}
      {v.mode === 'online' || v.mode === 'hybrid' ? <Caption text={WIZ.linkLater()} /> : null}
    </View>
  );

  /**
   * GR.11: город строкой-выбором, карта карточкой 134 с кругом радиуса, «How far can people come
   * from?» с числом и ползунком, поле точного места и записка о приватности.
   *
   * Карта здесь — ПРЕВЬЮ: двигают её в листе GR.11a, который открывается касанием карты или кнопкой
   * «развернуть». В карточке на 134 точки жест «подвинь карту» дрался бы с прокруткой шага, а
   * прицелиться булавкой в улицу на такой полосе нельзя.
   */
  const placeBlockOf = (v: Draft, set: SetDraft) => {
    const la = v.lat ?? homeLat;
    const lo = v.lon ?? homeLon;
    const area = (v.district || '').trim() || where;
    return (
      <>
        <View style={s.placeTop}>
          <SelectField value={where || T('Город', 'City', 'Ciudad')} onPress={() => openSpot(set, v)} muted />
          <Pressable accessibilityRole="button" accessibilityLabel={WIZ.expandMap()} onPress={() => openSpot(set, v)} style={s.mapCard}>
            <View pointerEvents="none" style={StyleSheet.absoluteFill}>
              <RadiusMap lat={la} lon={lo} km={v.radiusKm} />
            </View>
            <View style={s.mapExpand} pointerEvents="none">
              <GlassSurface tone="light" radius={15} style={s.mapExpandBtn}>
                <IconMaximize size={16} c={color.fg} />
              </GlassSurface>
            </View>
          </Pressable>
        </View>

        <View style={s.radiusBox}>
          <View style={s.radiusRow}>
            <Text style={s.radiusAsk}>{WIZ.radius()}</Text>
            <Text style={s.radiusKm}>{v.radiusKm} km</Text>
          </View>
          <RadiusSlider
            value={v.radiusKm}
            onChange={(km) => set((x) => ({ ...x, radiusKm: km }))}
            onDrag={setDragging}
          />
        </View>

        {/* Точное место можно назвать сразу — но чужим оно не показывается: его выдаёт только план
            после взаимного подтверждения (OF.C3). */}
        <View style={s.addressBox}>
          <AddressField
            style={s.addressInput}
            placeholder={WIZ.exactPlaceholder()}
            value={v.address || ''}
            onChange={(t) => set((x) => ({ ...x, address: t }))}
            onPick={(hit) => set((x) => ({ ...x, address: hit.label, lat: hit.lat, lon: hit.lon, venue: true }))}
          />
          <Caption text={WIZ.exactNote(area)} />
        </View>
      </>
    );
  };

  const linkBlock = linkBlockOf(draft, setDraft);
  const placeBlock = placeBlockOf(draft, setDraft);

  /** Отмеченные черты одной строкой — для сводки O.10 и строк листа правки. */

  /** Полная карта параметр → точный контрол.
   *
   *  ЧЕГО ЗДЕСЬ НЕТ. Тема и категория — это исходная фраза и вычисленная подпись, а не параметры
   *  мастера, и правки они не знают.
   *
   *  Тип встречи и формат тоже не строки листа, и это решение продукта, а не упущение: они
   *  задаются на своих шагах мастера, где рядом стоит всё, что от них зависит — место и ссылка от
   *  типа, размер группы от формата. Поменять их отсюда значит одним движением обнулить соседние
   *  строки: выбрал «онлайн» — и адрес, который человек только что вписал, молча перестаёт
   *  существовать. Размер группы остаётся: он ничего за собой не тянет.
   */
  /**
   * ЛИСТ «EDIT IT YOURSELF» (GR.12b–GR.12i): аккордеон по шагам мастера — What · How you meet ·
   * How many · When · Time zone · Who · Where. Открыта одна строка; внутри тот же контрол, что на
   * шаге. Правки копятся в черновике листа (edraft, etitle): «Cancel» и крестик ничего не меняют,
   * «Apply» неактивна, пока ничего не изменено, и применяет всё изменённое разом.
   *
   * «How you meet» с замком: другой формат — это другой интент (заметка к GR.12b), у офлайна
   * спрашивают место, у онлайна — ссылку, и правка отсюда тихо обнулила бы соседние ответы.
   * Группу на 1:1 здесь тоже не поменять (заметка к GR.12d) — только число людей.
   */
  type EditKey = 'what' | 'how' | 'size' | 'when' | 'tz' | 'who' | 'where';
  const accRef = useRef<ScrollView>(null);
  /** Где в списке стоит каждая строка — чтобы докрутить к открытой. */
  const accY = useRef<Record<string, number>>({});
  // Вернулись с карты или из Plus внутри листа — аккордеон смонтирован заново и стоит в начале;
  // открытая строка обязана остаться перед глазами, иначе человек не видит, что точка применилась.
  useEffect(() => {
    if (!editOpen || spotOpen || groupSizeOpen || !editPick) return;
    const id = setTimeout(() => accRef.current?.scrollTo({ y: Math.max(0, (accY.current[editPick] || 0) - 8), animated: false }), 80);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spotOpen, groupSizeOpen]);
  const [etitle, setEtitle] = useState('');
  const [esug, setEsug] = useState<string[]>([]);
  const [esugBusy, setEsugBusy] = useState(false);
  /** GR.12j: что ответил Kleal после «Apply» — встаёт над сводкой вместо вопроса шага. */
  const [updated, setUpdated] = useState('');
  /** GR.12a словами: реплики человека и ответы Kleal, пока правка не удалась. */
  const [talk, setTalk] = useState<{ me: string; kleal: string }[]>([]);

  /**
   * «Просто скажи мне, что изменить» (GR.12a). Понял и применил — сводка обновлена, и Kleal
   * называет, ЧТО поменялось (GR.12j). Не понял или нельзя — остаёмся на GR.12a и объясняем.
   */
  const talkChange = (text: string) => {
    const r = parseIntentChange(text, draft, new Date(), GROUP_FREE_MAX_TOTAL);
    const say = (kleal: string) => {
      setChanging(true);
      setTalk((x) => [...x, { me: text, kleal }]);
      setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 60);
    };
    if (!r) { say(WIZ.talkUnclear()); return; }
    if (r.problem) { say(r.problem === 'past' ? WIZ.talkPast() : r.problem === 'plus' ? WIZ.talkPlus(GROUP_FREE_MAX_TOTAL) : WIZ.talkFormat()); return; }
    const p = r.patch;
    const titleChanged = !!r.title && r.title !== title;
    if (!Object.keys(p).length && !titleChanged) { say(WIZ.talkSame()); return; }
    const v: Draft = { ...draft, ...p };
    const parts: string[] = [];
    if (titleChanged) parts.push(`«${r.title}»`);
    if (p.date || p.minutes != null) {
      parts.push([p.date ? cardDate(v.date) : '', p.minutes != null ? hhmm(v.minutes) : ''].filter(Boolean).join(', '));
    }
    if (p.sex || p.minAge != null || p.maxAge != null) parts.push(audienceOf(v));
    if (p.groupSize) parts.push(WIZ.groupOf(p.groupSize));
    if (p.radiusKm) parts.push(`${p.radiusKm} km`);
    setDraft(v);
    if (titleChanged) setTitle(r.title!);
    setTalk([]);
    setChanging(false);
    setUpdated(WIZ.updatedTalk(parts.join(' · ')));
    scroller.current?.scrollTo({ y: 0, animated: false });
  };

  const audienceOf = (v: Draft) => `${WIZ.sexChip(v.sex || 'Any')}, ${
    v.minAge || v.maxAge ? `${v.minAge}–${v.maxAge}` : WIZ.anyAge().toLowerCase()}`;
  const whereOf = (v: Draft) => v.mode === 'online'
    ? (v.link.trim() || EDIT_SHEET.noData())
    : (v.address?.trim() || (where ? `${where} · ${v.radiusKm} km` : EDIT_SHEET.noData()));

  const loadIdeas = () => {
    if (esugBusy) return;
    setEsugBusy(true);
    buddyApi.intentSuggest({ name: st.profile.name, city: st.profile.city,
                             interests: st.profile.interests?.explicit || [], languages: st.profile.languages || {} },
                           replyLang(), String(Date.now() % 1000))
      .then((r: any) => setEsug(Array.isArray(r?.suggestions) ? r.suggestions.map(String).slice(0, 3) : []))
      .catch(() => setEsug([]))
      .finally(() => setEsugBusy(false));
  };

  const openEdit = (target: IntentEditTarget | '' = '') => {
    void target;
    setEdraft(beginIntentEdit(draft));
    setEtitle(title);
    setEditPick('');
    setEditOpen(true);
  };

  /** Что изменено в листе — для «Apply» и для ответа Kleal на GR.12j. */
  const editChanges = (v: Draft | null): EditKey[] => {
    if (!v) return [];
    const out: EditKey[] = [];
    if (etitle.trim() !== title.trim()) out.push('what');
    if ((v.groupSize || 0) !== (draft.groupSize || 0)) out.push('size');
    if (v.date !== draft.date || v.minutes !== draft.minutes) out.push('when');
    if (v.tz !== draft.tz) out.push('tz');
    if ((v.sex || 'Any') !== (draft.sex || 'Any') || v.minAge !== draft.minAge || v.maxAge !== draft.maxAge) out.push('who');
    if (v.radiusKm !== draft.radiusKm || (v.address || '') !== (draft.address || '') || v.lat !== draft.lat
        || v.lon !== draft.lon || v.link !== draft.link) out.push('where');
    return out;
  };

  const applyEdit = () => {
    const v = edraft;
    const changed = editChanges(v);
    if (!v || !changed.length || linkBroken(v)) return;
    // Формат и состав (1:1 / группа) не правятся отсюда — берём их из живого черновика.
    setDraft({ ...v, mode: draft.mode, size: draft.size });
    if (changed.includes('what') && etitle.trim()) {
      const name = etitle.trim();
      setTitle(name);
      setRetopic(true);
      agent.categorize(name)
        .then((r: any) => {
          const next = ((r?.topics || []) as string[]).map((t) => String(t).trim()).filter(Boolean);
          if (next.length) setTopics(next);
          const c = String(r?.category || '').trim();
          if (c) setCategory(categoryLabel(c));
        })
        .catch(() => {})   // не ответил — остаются прежние темы, поиск всё равно идёт
        .finally(() => setRetopic(false));
    }
    setEditOpen(false);
    setChanging(false);
    const when = changed.includes('when')
      ? (v.date !== draft.date ? cardDate(v.date) : '') + (v.date !== draft.date && v.minutes !== draft.minutes ? ', ' : '')
        + (v.minutes !== draft.minutes ? hhmm(v.minutes) : '')
      : '';
    setUpdated(when ? WIZ.updatedWhen(when) : WIZ.updatedOther());
    scroller.current?.scrollTo({ y: 0, animated: false });
  };

  const editValue = (k: EditKey, v: Draft): string =>
    k === 'what' ? (etitle || '—')
    : k === 'how' ? `${draft.mode ? formatLabel(draft.mode) : '—'} · ${WIZ.formatSub(draft.mode || 'offline')}`
    : k === 'size' ? (draft.size === 'group' ? WIZ.groupOf(v.groupSize || GROUP_MIN_TOTAL) : WIZ.oneToOne())
    : k === 'when' ? `${cardDate(v.date)} · ${hhmm(v.minutes)}`
    : k === 'tz' ? tzPlace(v.tz)
    : k === 'who' ? audienceOf(v)
    : whereOf(v);

  const editPanel = (k: EditKey, v: Draft) => {
    const set: SetDraft = (fn) => setEdraft((x) => (x ? fn(x) : x));
    if (k === 'what') {
      return (
        <>
          <GlassSurface tone="light" radius={999} style={s.input48}>
            <TextInput style={s.inputText} value={etitle} onChangeText={setEtitle}
              placeholder={WIZ.whatPlaceholder()} placeholderTextColor={color.muted} />
            {intentNameOptions(topics, { size: draft.size, minutes: v.minutes }, etitle).length ? (
              <Pressable accessibilityRole="button" accessibilityLabel={SUMMARY_O10.roll()} hitSlop={8}
                onPress={() => { const n = rollIntentName(topics, { size: draft.size, minutes: v.minutes }, etitle); if (n) setEtitle(n); }}>
                <IconDice size={20} c={color.primary} />
              </Pressable>
            ) : null}
          </GlassSurface>
          <Caption text={WIZ.ideas()} />
          {esugBusy && !esug.length ? <ActivityIndicator color={color.primary} /> : (
            <View style={s.options}>
              {esug.map((o) => (
                <ChoiceRow key={o} label={o} on={etitle === o} onPress={() => setEtitle(o)} />
              ))}
            </View>
          )}
          <GlassPill tone="light" small icon={<IconWand size={16} c={color.fg} />} label={CREATE.regenerate()}
            busy={esugBusy} onPress={loadIdeas} style={{ height: 40 }} />
        </>
      );
    }
    if (k === 'size') {
      return draft.size === 'group' ? (
        <>
          {groupSizeBlockOf(v, set, 'edit')}
          <Caption text={WIZ.freeNote()} />
        </>
      ) : <Caption text={WIZ.oneToOneLocked()} />;
    }
    if (k === 'when') return whenBlockOf(v, set);
    if (k === 'tz') {
      return (
        <View style={s.tzList}>
          {tzChoices().map((z) => (
            <Pressable key={z} accessibilityRole="radio" accessibilityState={{ selected: z === v.tz }}
              style={[s.tzRow, z === v.tz && s.tzRowOn]} onPress={() => set((x) => ({ ...x, tz: z }))}>
              <Text style={s.tzText}>{tzPlace(z)}</Text>
              {z === v.tz ? <Check /> : null}
            </Pressable>
          ))}
        </View>
      );
    }
    if (k === 'who') return whoBlockOf(v, set);
    if (k === 'where') {
      return draft.mode === 'online' ? linkBlockOf(v, set)
        : draft.mode === 'hybrid' ? (<>{placeBlockOf(v, set)}{linkBlockOf(v, set)}</>)
        : placeBlockOf(v, set);
    }
    return null;
  };

  const EDIT_ROWS: [EditKey, (p: { size?: number; c?: string }) => React.ReactElement, () => string][] = [
    ['what', IconStar, WIZ.rowWhat],
    ['how', IconHelp, WIZ.rowHow],
    ['size', IconUsers, WIZ.rowHowMany],
    ['when', IconCalendar, WIZ.rowWhen],
    ['tz', IconGlobe, WIZ.timeZone],
    ['who', IconPerson, WIZ.rowWho],
    ['where', IconPin, WIZ.rowWhere],
  ];


  /** Последний шаг деталей зависит от типа встречи — см. шапку src/intent.ts. */
  const lastStep: IntentStepId =
    draft.mode === 'offline' ? 'place' : draft.mode === 'hybrid' ? 'both' : 'link';

  /**
   * ЕДИНСТВЕННОЕ МЕСТО, ГДЕ ЗАПИСАН ПОРЯДОК ШАГОВ НАЗАД.
   *
   * Вперёд шаги переключаются девятью разными setStep по всему JSX, а маршрут у мастера ОДИН:
   * шаг живёт в состоянии экрана, в историю навигации он не пишется. Поэтому «назад» снимала
   * весь маршрут /intent — а под ним лежит разговор создания (app/create.tsx открывает мастер
   * поверх себя), и человек, поправлявший один шаг, оказывался у Бадди.
   *
   * Третий шаг ветвится по типу встречи, поэтому со сводки отступаем на lastStep, а не на
   * фиксированное имя: иначе офлайн и гибрид уехали бы на чужой шаг.
   */
  const prevStep = (from: IntentStepId, grouped = false): IntentStepId | null =>
    // GR.05 → GR.07 → GR.09 → GR.10 → GR.11 → GR.12. Размер группы стоит на шаге «сколько»
    // (GR.07), шага «характер» в этом потоке нет: на борде детали — ровно «Step N of 3».
    from === 'size' ? 'how'
    : from === 'capacity' ? 'size'
    : from === 'when' ? 'size'
    : from === 'who' ? 'when'
    : from === 'nature' ? 'who'
    : from === 'link' || from === 'both' || from === 'place' ? 'who'
    : from === 'summary' ? lastStep
    : null;

  /**
   * Один выход назад на оба входа — кнопку в шапке и системный жест.
   *
   * Порядок проверок идёт от верхнего слоя к нижнему. Иначе на Android «назад» при открытом
   * листе срабатывает дважды: лист закрывается по onRequestClose И экран отступает на шаг.
   */
  const goBack = () => {
    if (spotOpen) { setSpotOpen(false); return; }
    if (changing) { setChanging(false); setTalk([]); return; }
    if (groupSizeOpen) { setGroupSizeOpen(false); return; }
    if (tzOpen || editOpen) { setTzOpen(false); setEditOpen(false); return; }
    if (busy) { cancelSearch(); return; }
    if (ackTimer.current) { clearTimeout(ackTimer.current); ackTimer.current = null; setAck(false); }
    // GO.07–GO.09 содержит ровно три шага: у Group Online link идёт сразу после audience.
    // Остальные флоу сохраняют свой шаг характера и общий prevStep без изменений.
    const prev = groupOnline && step === 'link' ? 'who' : prevStep(step, draft.size === 'group');
    if (!prev) { router.back(); return; }
    setStep(prev);
    // Шаг назад обязан открыться сверху — иначе он показывается серединой карточки, которую уже
    // листали. Тот же сброс делает choose() при движении вперёд.
    scroller.current?.scrollTo({ y: 0, animated: false });
  };

  /**
   * Системный жест назад снимает экран НАТИВНО, не спрашивая JS: обработчик кнопки для него не
   * выполняется вовсе, и правка одной кнопки его не лечила. Пока есть что закрыть или куда
   * отступить — держим экран и отдаём событие тому же goBack(); на первом шаге предотвращение
   * снимается само, и жест честно уводит в разговор создания.
   */
  usePreventRemove(step !== 'how' || groupSizeOpen || tzOpen || editOpen || busy || spotOpen || changing, (e) => {
    // Перехват висит на СНЯТИИ ЭКРАНА, а не на жесте, и под него попадает всё, что уводит с
    // маршрута, — включая «Все интенты» (dismissTo → POP_TO). Эта кнопка обязана остаться
    // сквозным выходом: без неё из мастера стало бы некуда деться, кроме как назад по шагам.
    // Поэтому задерживаем только «назад» (жест и кнопка дают GO_BACK либо POP), а всё остальное
    // отправляем ещё раз — повторно перехвачено оно не будет: маршрут в этом действии уже
    // помечен пройденным (VISITED_ROUTE_KEYS в @react-navigation/core).
    const a = e.data.action;
    if (a.type !== 'GO_BACK' && a.type !== 'POP') { nav.dispatch(a); return; }
    goBack();
  });

  /** Проценты шапки — с кадров: 30 / 40 / 60 / 70 / 90 / 100. */
  const pct = step === 'how' ? 30 : step === 'size' || step === 'capacity' ? 40
    : step === 'when' ? 60 : step === 'who' || step === 'nature' ? 70
    : step === 'summary' ? 100 : 90;

  /** «Next» шага: выключен, пока на шаге не выбрано то, без чего дальше идти нельзя. */
  const nextOf = (): { on: boolean; go: () => void } => {
    if (step === 'how') return { on: !!draft.mode, go: () => setStep('size') };
    if (step === 'size' || step === 'capacity') {
      return {
        on: !!draft.size,
        go: () => (draft.size === 'group' && (draft.groupSize || 0) > GROUP_FREE_MAX_TOTAL
          ? (setGroupSizeTarget('draft'), setGroupSizeOpen(true))
          : setStep('when')),
      };
    }
    if (step === 'when') return { on: true, go: () => setStep('who') };
    if (step === 'who' || step === 'nature') return { on: true, go: () => setStep(lastStep) };
    if (step === 'link') return { on: !groupLinkBlocked(draft), go: toSummary };
    if (step === 'both') return { on: !linkBroken(draft), go: toSummary };
    return { on: true, go: toSummary };
  };
  const nx = nextOf();

  const detailN = step === 'when' ? 1 : step === 'who' || step === 'nature' ? 2 : 3;
  const detailLabel = step === 'when' ? WIZ.whenStep() : step === 'who' || step === 'nature' ? WIZ.whoStep()
    : step === 'link' ? (draft.mode === 'online' ? WIZ.whereStep() : WIZ.linkStep()) : step === 'both' ? WIZ.bothStep() : WIZ.whereStep();

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {/* «Назад» — только от левого края (app/_layout.tsx); пока палец на ползунке радиуса — и он выключен. */}
      <Stack.Screen options={{ gestureEnabled: !dragging }} />
      <View style={[s.wrap, { paddingTop: insets.top }]}>
        {/*
          ШАПКА — ТА ЖЕ, ЧТО НА «ЧТО ДЕЛАЕМ» (app/create.tsx): «Creating intent», проценты шага и
          маскот. Прежняя красная «All intents» справа ушла: на кадрах её нет, а вкладка «Интенты»
          и так в нижней панели. «Назад» отступает на шаг, а не снимает весь мастер (goBack).
        */}
        <CreatingHeader pct={pct} onBack={goBack} />

        <ScrollView
          ref={scroller}
          contentContainerStyle={s.body}
          keyboardShouldPersistTaps="handled"
          scrollEnabled={!dragging}
        >
          {/* Что создаём — над каждым шагом до сводки (см. IntentPlate). На сводке своя карточка. */}
          {step !== 'summary' ? <IntentPlate title={title} topics={topics} /> : null}
          {step === 'how' ? (
            <>
              <StepAsk text={WIZ.howAsk()} caption={WIZ.howCaption()} />
              {modeBlockOf(draft, setDraft)}
            </>
          ) : step === 'size' || step === 'capacity' ? (
            <>
              <StepAsk text={WIZ.sizeAsk()} caption={draft.size === '1:1' ? WIZ.sizeCaptionSolo() : WIZ.sizeCaption()} />
              {sizeBlockOf(draft, setDraft)}
              {draft.size === 'group' ? (
                <>
                  {groupSizeBlockOf(draft, setDraft, 'draft')}
                  <Caption text={WIZ.freeNote()} />
                </>
              ) : null}
            </>
          ) : step === 'summary' ? (
            changing ? (
              /* GR.12a: два пути правки — сам (лист GR.12b) или словами Kleal. */
              <>
                <StepAsk text={draft.mode === 'online' ? WIZ.changeAskOnline() : WIZ.changeAsk()} caption={WIZ.changeCaption()} />
                <View style={s.editMyself}>
                  <GlassPill tone="light" small icon={<IconPencil size={16} c={color.fg} />}
                    label={WIZ.editMyself()} onPress={() => openEdit()} style={s.editMyselfBtn} />
                </View>
                {talk.map((l, i) => (
                  <React.Fragment key={i}>
                    <MyLine text={l.me} />
                    <AgentLine text={l.kleal} />
                  </React.Fragment>
                ))}
              </>
            ) : (
              <>
                <StepAsk text={updated || WIZ.sumAsk()} caption={WIZ.sumCaption()} />
                <SummaryCard
                  topic={title}
                  /*
                    Костей НЕТ, если предлагать нечего: темы могут прийти такими, что словарь их
                    не знает ни одной, и тогда любое нажатие ничего не изменит. Кнопка, которая
                    заведомо не сработает, хуже её отсутствия.
                  */
                  onRollTopic={
                    intentNameOptions(topics, { size: draft.size, minutes: draft.minutes }, title).length
                      ? () => {
                          const next = rollIntentName(topics, { size: draft.size, minutes: draft.minutes }, title);
                          if (next) setTitle(next);
                        }
                      : undefined
                  }
                  topics={topics}
                  where={where}
                  draft={draft}
                  category={category}
                />
                <View style={s.sumButtons}>
                  <GlassPill tone="brand" style={s.btn48} busy={busy || retopic} label={WIZ.start()} onPress={finish} />
                  <GlassPill tone="dark" style={s.btn48} disabled={busy} label={WIZ.changeIt()} onPress={() => setChanging(true)} />
                </View>
              </>
            )
          ) : (
            <>
              <StepAsk
                text={step === 'when' ? WIZ.whenAsk() : step === 'who' || step === 'nature' ? WIZ.whoAsk()
                  : step === 'link' ? (draft.mode === 'online' ? WIZ.linkAskGroup() : WIZ.linkAsk()) : step === 'both' ? (draft.size === 'group' ? WIZ.bothAskGroup() : WIZ.bothAskSolo()) : WIZ.whereAsk()}
                caption={step === 'when' ? WIZ.whenCaption() : step === 'who' || step === 'nature' ? WIZ.whoCaption() : undefined}
              />
              <StepIndicator n={detailN} label={detailLabel} />
              {step === 'when'
                ? whenBlockOf(draft, setDraft, () => { setTzPick(draft.tz); setTzOpen(true); })
                : null}
              {step === 'who' || step === 'nature' ? whoBlockOf(draft, setDraft) : null}
              {step === 'link' ? linkBlock : null}
              {/*
                HY.09 — у гибрида шаг ОДИН, но в нём оба блока: борд говорит это прямо на HY.20a/20b —
                «hybrid needs both». Без места тому, кто хотел прийти живьём, приходить было некуда.
              */}
              {step === 'both' ? (<>{placeBlock}{linkBlock}</>) : null}
              {step === 'place' ? placeBlock : null}
            </>
          )}

          {err ? <Text style={s.err}>{err}</Text> : null}
        </ScrollView>

        {step !== 'summary' ? (
          <View style={s.nextDock}>
            <GlassPill tone="brand" style={s.btn48} disabled={!nx.on} label={INTENT.next()} onPress={nx.go} />
          </View>
        ) : null}

        {/*
          На сводке GR.12 / GR.12j поля нет — внизу две кнопки, и поле их выталкивало за край. Писать
          Kleal, что поменять, — путь GR.12a («Change it»): там поле и появляется.
        */}
        {step === 'summary' && !changing ? (
          <View style={{ height: Math.max(insets.bottom, 12) }} />
        ) : (
          <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
            {/*
              На шагах с выбором (как, сколько, когда, где, кто) поле закрыто — 18.10.2026 по слову
              Ивана: написанное здесь уходило в agent.plan в обход шагов и ломало поток. Писать
              Kleal можно на сводке, в «Изменить» (GR.12a).
            */}
            <CreateComposer
              value={free}
              onChange={setFree}
              onSubmit={send}
              placeholder={step === 'summary' ? COMPOSER_PLACEHOLDER() : COMPOSER_LOCKED()}
              editable={!busy}
              locked={step !== 'summary'}
            />
          </View>
        )}

        {/* GR.08 — одинаковая для всех тарифов вместимость после «6+». */}
        <Sheet visible={groupSizeOpen && !editOpen} onClose={() => setGroupSizeOpen(false)} title={WIZ.plusTitle()}>
          <SheetText lead={WIZ.plusLead()} note={WIZ.plusNote()} />
          <GlassPill tone="brand" style={s.btn48} label={WIZ.cancel()} onPress={() => setGroupSizeOpen(false)} />
          <GlassPill
            tone="dark"
            style={s.btn48}
            label={WIZ.keepFive()}
            onPress={() => {
              setGroupSizeOpen(false);
              if (groupSizeTarget === 'edit') {
                setEdraft((x) => x ? ({ ...x, size: 'group', groupSize: GROUP_FREE_MAX_TOTAL }) : x);
              } else {
                setDraft((x) => ({ ...x, size: 'group', groupSize: GROUP_FREE_MAX_TOTAL }));
              }
            }}
          />
        </Sheet>

        {/* GR.09a — часовой пояс. Выбор живёт в tzPick и попадает в черновик только по «Done». */}
        <Sheet visible={tzOpen} onClose={() => setTzOpen(false)} title={WIZ.tzTitle()}>
          <Text style={s.sheetLead}>{WIZ.tzLead()}</Text>
          <ScrollView style={{ maxHeight: Math.max(220, win.height * 0.42) }} contentContainerStyle={s.tzList}>
            {tzChoices().map((z) => (
              <Pressable
                key={z}
                accessibilityRole="radio"
                accessibilityState={{ selected: z === tzPick }}
                style={[s.tzRow, z === tzPick && s.tzRowOn]}
                onPress={() => setTzPick(z)}
              >
                <Text style={s.tzText}>{tzPlace(z)}</Text>
                {z === tzPick ? <Check /> : null}
              </Pressable>
            ))}
          </ScrollView>
          <GlassPill tone="brand" style={s.btn48} label={WIZ.done()}
            onPress={() => { if (tzPick) setDraft((x) => ({ ...x, tz: tzPick })); setTzOpen(false); }} />
          <GlassPill tone="dark" style={s.btn48} label={WIZ.cancel()} onPress={() => setTzOpen(false)} />
        </Sheet>

        {/* GR.12b–GR.12i — «Edit it yourself». Тот же лист открывается со страницы интента (GR.14h). */}
        <Sheet
          visible={editOpen}
          onClose={() => (spotOpen ? setSpotOpen(false) : groupSizeOpen ? setGroupSizeOpen(false) : setEditOpen(false))}
          title={spotOpen || groupSizeOpen ? (groupSizeOpen ? WIZ.plusTitle() : undefined) : EDIT_SHEET.title()}
        >
          {/*
            ВТОРОЙ ЛИСТ ВНУТРИ ПЕРВОГО. Карта GR.12i и Plus GR.08 открываются из листа правки, а второй
            RN-модал поверх открытого на iOS не показывается (проверено на симуляторе). Поэтому они
            встают внутрь этого листа вместо аккордеона; «Back» / «Keep it at 5» возвращают аккордеон.
          */}
          {spotOpen ? (
            <SpotPanel open={spotOpen} value={spot} onChange={setSpot} onClose={() => setSpotOpen(false)} onUse={useSpot} />
          ) : groupSizeOpen ? (
            <>
              <SheetText lead={WIZ.plusLead()} note={WIZ.plusNote()} />
              <GlassPill tone="brand" style={s.btn48} label={WIZ.cancel()} onPress={() => setGroupSizeOpen(false)} />
              <GlassPill tone="dark" style={s.btn48} label={WIZ.keepFive()} onPress={() => {
                setGroupSizeOpen(false);
                setEdraft((x) => x ? ({ ...x, size: 'group', groupSize: GROUP_FREE_MAX_TOTAL }) : x);
              }} />
            </>
          ) : (<>
          <ScrollView
            ref={accRef}
            style={{ maxHeight: Math.max(260, win.height - 330) }}
            contentContainerStyle={s.accordion}
            keyboardShouldPersistTaps="handled"
            scrollEnabled={!dragging}
          >
            {edraft ? EDIT_ROWS.map(([k, Icon, label]) => {
              const open = editPick === k;
              const locked = k === 'how';
              return (
                <View key={k} style={open ? s.accOpen : null}
                  onLayout={(e) => { accY.current[k] = e.nativeEvent.layout.y; }}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ expanded: open, disabled: locked }}
                    disabled={locked}
                    onPress={() => {
                      if (k === 'what' && !open && !esug.length) loadIdeas();
                      setEditPick(open ? '' : (k as any));
                      // Открытая строка встаёт к верху списка (заметки к GR.12g/GR.12h): иначе
                      // раскрытое у нижних строк уходит под кнопки и его не видно.
                      if (!open) setTimeout(() => accRef.current?.scrollTo({ y: Math.max(0, (accY.current[k] || 0) - 8), animated: true }), 60);
                    }}
                    style={[s.accRow, open && s.accRowOn]}
                  >
                    <Icon size={20} c={color.primary} />
                    <View style={{ flex: 1, gap: 4 }}>
                      <Text style={s.accTitle}>{label()}</Text>
                      <Text style={s.accValue} numberOfLines={1}>{editValue(k, edraft)}</Text>
                    </View>
                    {locked ? <IconLock size={20} c={color.muted} />
                      : open ? <IconChevronUp size={20} c={color.fg} /> : <IconChevronDown size={20} c={color.fg} />}
                  </Pressable>
                  {open ? <View style={s.accPanel}>{editPanel(k, edraft)}</View> : null}
                </View>
              );
            }) : null}
          </ScrollView>
          {edraft && linkBroken(edraft) ? <Text style={s.err}>{DETAILS.linkBad()}</Text> : null}
          <GlassPill tone="brand" style={s.btn48} disabled={!editChanges(edraft).length || (!!edraft && linkBroken(edraft))}
            label={DETAILS.apply()} onPress={applyEdit} />
          <GlassPill tone="dark" style={s.btn48} label={DETAILS.cancel()} onPress={() => setEditOpen(false)} />
          </>)}
        </Sheet>

        {busy ? <Searching onCancel={cancelSearch} dateKey={draft.date} /> : null}

        {/* GR.11a — точное место на карте: карта двигается под булавкой, адрес под ней меняется. */}
        <SpotSheet
          open={spotOpen && !spotInEdit.current}
          value={spot}
          onChange={setSpot}
          onClose={() => setSpotOpen(false)}
          onUse={useSpot}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

/**
 * O.10 — сводка перед поиском: обложка, тема, факты строками, сводка Kleal, «Начать поиск» и
 * «Поправить». Обложки-фотографии в данных нет — цветное поле со значком, как везде в каркасе:
 * рисовать фотографию, которой нет, не из чего.
 */
/**
 * Карточка сводки GR.12 («Intent Summary Card»): обложка 128, под ней белое стекло 45% с полями
 * 16 — название 17/22 и кости справа, строка «когда» (дата и время), строка «где», четыре строки
 * Mode / Format / Category / Audience (подпись 60%, значение 500) и «Kleal summary» коралловым.
 *
 * Строки не нажимаются: на кадре правка — кнопкой «Change it» под карточкой (GR.12a → GR.12b), и
 * точечные стрелки на строках обещали бы второй вход в тот же лист.
 */
function SummaryCard({
  topic, topics, onRollTopic, draft, category, where,
}: {
  topic: string;
  topics: string[];
  /** Кости у названия: подобрать другое. Пусто — костей нет (нечего предлагать). */
  onRollTopic?: () => void;
  draft: Draft;
  category: string;
  /** Город профиля — когда точного места не назвали. */
  where: string;
}) {
  const audience = `${WIZ.sexChip(draft.sex || 'Any')}, ${
    draft.minAge || draft.maxAge ? `${draft.minAge}–${draft.maxAge}` : WIZ.anyAge().toLowerCase()}`;
  const rows: [string, string][] = [
    // GRO.12: онлайн — «Online · video call»; офлайн (GR.12) — просто «Offline».
    [WIZ.mode(), draft.mode === 'online' ? T('Онлайн · видеозвонок', 'Online · video call', 'Online · videollamada')
      // HY.10 / GRH.12: «Hybrid · in person or on a call».
      : draft.mode === 'hybrid' ? WIZ.modeHybrid()
      : draft.mode ? formatLabel(draft.mode) : '—'],
    [WIZ.format(), draft.size === 'group' ? WIZ.groupOf(draft.groupSize || GROUP_MIN_TOTAL) : WIZ.oneToOne()],
    ...(category ? ([[WIZ.category(), category]] as [string, string][]) : []),
    [WIZ.audience(), audience],
  ];
  const place = draft.mode === 'online'
    ? (draft.link.trim() || EDIT_SHEET.noData())
    : (draft.address?.trim() || (where ? `${where} · ${draft.radiusKm} km` : EDIT_SHEET.noData()));
  return (
    <GlassSurface tone="light" radius={20} style={s.sumCard}>
      {/*
        Категория ЗДЕСЬ ЖЕ, и она важнее названия: название человек пишет на своём языке
        («Консоли»), а категорию присылает фильтратор английским ключом. Без неё обложка у
        русского названия падала в общую — что и было видно на экране.
      */}
      <Cover intent={{ title: topic, category, mode: draft.mode, topics }} style={s.sumCover} />
      <View style={s.sumBody}>
        <View style={s.sumTitleRow}>
          <Text style={s.sumTitle} numberOfLines={2}>{topic || '—'}</Text>
          {onRollTopic ? (
            // Кости 44 на кадре заходят в поле карточки: строка названия остаётся ростом 22.
            <GlassIconButton label={SUMMARY_O10.roll()} onPress={onRollTopic} style={{ marginTop: -11, marginRight: -6, marginBottom: -11 }}>
              <IconDice size={20} c={color.fg} />
            </GlassIconButton>
          ) : null}
        </View>
        <View style={s.sumLine}>
          <View style={s.sumPart}>
            <IconCalendar size={18} c={color.primary} />
            <Text style={s.sumLineText}>{cardDate(draft.date)}</Text>
          </View>
          <View style={s.sumPart}>
            <IconClock size={18} c={color.primary} />
            {/* Пояс показывается только при расхождении с поясом устройства. */}
            <Text style={s.sumLineText}>
              {hhmm(draft.minutes)}{draft.tz && draft.tz !== deviceTz() ? ` ${tzOffsetLabel(draft.tz)}` : ''}
            </Text>
          </View>
        </View>
        <View style={s.sumLine}>
          <View style={[s.sumPart, { flex: 1 }]}>
            {draft.mode === 'online' ? <IconVideo size={18} c={color.primary} /> : <IconPin size={18} c={color.primary} />}
            <Text style={[s.sumLineText, { flex: 1 }]} numberOfLines={1}>
              {/* GRO.12: «Video call · your link» — саму ссылку на карточке не показываем. */}
              {draft.mode === 'online'
                ? (draft.link.trim() ? T('Звонок · твоя ссылка', 'Video call · your link', 'Videollamada · tu enlace') : WIZ.linkLaterLine())
                : place}
            </Text>
          </View>
        </View>
        {/* Гибрид показывает ОБЕ строки: у него и место, и ссылка (HY.09). */}
        {draft.mode === 'hybrid' ? (
          <View style={s.sumLine}>
            <View style={[s.sumPart, { flex: 1 }]}>
              <IconLink size={18} c={color.primary} />
              <Text style={[s.sumLineText, { flex: 1 }]} numberOfLines={1}>{draft.link.trim() || WIZ.linkLaterLine()}</Text>
            </View>
          </View>
        ) : null}

        <View style={s.sumRows}>
          {rows.map(([k, v]) => (
            <View key={k} style={s.sumRow}>
              <Text style={s.sumKey}>{k}</Text>
              <Text style={s.sumVal}>{v}</Text>
            </View>
          ))}
        </View>

        <View style={s.sumKleal}>
          <Text style={s.sumKlealLabel}>{WIZ.kleal()}</Text>
          <Text style={s.sumKlealText}>
            {wizSummary({ size: draft.size, groupSize: draft.groupSize, online: draft.mode === 'online', hybrid: draft.mode === 'hybrid', when: `${cardDate(draft.date)} ${hhmm(draft.minutes)}` })}
          </Text>
        </View>
      </View>
    </GlassSurface>
  );
}

/** Строка-выбор («Form/Dropdown Select» кадра): стекло 48, значение и шеврон вниз. */
function SelectField({ value, onPress, muted = false }: { value: string; onPress: () => void; muted?: boolean }) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={value} onPress={onPress}>
      <GlassSurface tone="light" radius={999} pointerEvents="none" style={s.select}>
        <Text style={[s.selectText, muted && { color: color.muted }]} numberOfLines={1}>{value}</Text>
        <IconChevronDown size={20} c={color.fg} />
      </GlassSurface>
    </Pressable>
  );
}

/**
 * GR.11a — «Pick the exact spot». Лист почти во весь экран: заголовок с пояснением, карта крупно
 * (её двигают пальцем, булавка стоит в центре и показывает точку), поиск места поверх карты,
 * под картой — адрес под булавкой, он меняется, когда карту сдвинули. «Use this spot» отдаёт
 * точку и адрес, «Back» ничего не меняет.
 *
 * Адрес под булавкой — обратное геокодирование с паузой: карту двигают непрерывно, а у геокодера
 * жёсткий лимит (src/geocode.ts). Ответа нет — остаются координаты, «Use this spot» работает и так.
 */
type Spot = { lat: number; lon: number; address: string; area: string };

/**
 * Лист GR.11a — обёртка над панелью. Со шага мастера он открывается отдельным листом; из листа
 * правки (GR.12i) — НЕ открывается: второй RN-модал поверх открытого на iOS не показывается вовсе
 * (проверено на симуляторе iOS 27 — нажатие по карте не давало ничего). Там панель встаёт внутрь
 * листа правки вместо аккордеона — на экране это тот же лист с картой поверх.
 */
function SpotSheet({ open, value, onChange, onClose, onUse }: {
  open: boolean; value: Spot; onChange: (v: Spot) => void; onClose: () => void; onUse: () => void;
}) {
  return (
    <Sheet visible={open} onClose={onClose}>
      <SpotPanel open={open} value={value} onChange={onChange} onClose={onClose} onUse={onUse} />
    </Sheet>
  );
}

function SpotPanel({
  open, value, onChange, onClose, onUse,
}: {
  open: boolean;
  value: Spot;
  onChange: (v: Spot) => void;
  onClose: () => void;
  onUse: () => void;
}) {
  const lang = useLang();
  const win = useWindowDimensions();
  const [q, setQ] = useState('');
  const [dragging, setDragging] = useState(false);
  const [locating, setLocating] = useState(false);
  const seq = useRef(0);
  /** Адрес под булавкой — с паузой: карту двигают непрерывно, а у геокодера жёсткий лимит. */
  const lookup = (lat: number, lon: number, wait = 600) => {
    const my = ++seq.current;
    setTimeout(() => {
      if (my !== seq.current) return;
      reverseGeocode(lat, lon, lang).then((p) => {
        if (!p || my !== seq.current) return;
        onChange({ lat, lon, address: p.label || '', area: [p.district, p.city].filter(Boolean).join(', ') });
      });
    }, wait);
  };
  // Открыли без названного места — сразу подписать точку под булавкой, а не показывать цифры.
  useEffect(() => {
    if (!open) return;
    setQ('');
    if (!value.address) lookup(value.lat, value.lon, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  const moved = (lat: number, lon: number) => {
    onChange({ ...value, lat, lon });
    lookup(lat, lon);
  };
  /** «Найти меня»: разрешение — по нажатию, как в поле адреса (src/components/AddressField.tsx). */
  const findMe = async () => {
    if (locating) return;
    setLocating(true);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== 'granted') return;
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      moved(pos.coords.latitude, pos.coords.longitude);
    } catch { /* нет точки — карта остаётся, где была */ }
    finally { setLocating(false); }
  };
  // Лист от статус-бара до низа: на экране другой высоты меняется только высота карты (заметка к GR.11a).
  const mapH = Math.max(260, Math.round(win.height - 430));
  return (
    <>
      <Text style={s.spotTitle}>{WIZ.spotTitle()}</Text>
      <Text style={s.spotSub}>{WIZ.spotSub()}</Text>
      <View style={[s.spotMap, { height: mapH }]}>
        <RadiusMap lat={value.lat} lon={value.lon} km={0} onMove={moved} onDragChange={setDragging} />
        {/* Булавка в центре: карту двигают под ней, острие — точка, которая уйдёт в интент. */}
        <View pointerEvents="none" style={[s.spotPin, { top: mapH / 2 - 52 * 56 / 48 }]}>
          <IconPinSolid size={52} c={color.primary} />
        </View>
        <View style={s.spotSearch} pointerEvents={dragging ? 'none' : 'box-none'}>
          <AddressField
            style={s.spotSearchInput}
            placeholder={WIZ.spotSearch()}
            value={q}
            onChange={setQ}
            onPick={(hit) => {
              setQ(hit.label);
              seq.current++;
              onChange({ lat: hit.lat, lon: hit.lon, address: hit.label, area: '' });
            }}
          />
        </View>
        <View style={[s.spotCorner, { left: 12 }]}>
          <GlassIconButton label={WIZ.findMe()} onPress={findMe}>
            {locating ? <ActivityIndicator color={color.primary} /> : <IconCrosshair size={20} c={color.primary} />}
          </GlassIconButton>
        </View>
        <View style={[s.spotCorner, { right: 12 }]}>
          <GlassIconButton label={WIZ.collapse()} onPress={onClose}>
            <IconMinimize size={20} c={color.primary} />
          </GlassIconButton>
        </View>
      </View>
      <GlassSurface tone="light" radius={16} style={s.spotAddr}>
        <IconPin size={20} c={color.primary} />
        <View style={{ flex: 1 }}>
          <Text style={s.spotAddrText} numberOfLines={1}>
            {value.address || `${value.lat.toFixed(5)}, ${value.lon.toFixed(5)}`}
          </Text>
          {value.area ? <Text style={s.spotAddrSub} numberOfLines={1}>{value.area}</Text> : null}
        </View>
      </GlassSurface>
      <GlassPill tone="brand" style={s.btn48} label={WIZ.useSpot()} onPress={onUse} />
      <GlassPill tone="dark" style={s.btn48} label={WIZ.back()} onPress={onClose} />
    </>
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
function Searching({ onCancel, dateKey }: { onCancel?: () => void; dateKey?: string }) {
  const lang = useLang();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setSlow(true), 6000);
    return () => clearTimeout(id);
  }, []);
  return (
    <View style={s.veil}>
      {/* GR.13: капля Kleal 96 и слово под ней, через 40 — заголовок, строка хода и подпись. */}
      <View style={s.veilMark}>
        <KlealMood width={118} slow={slow} />
        <Text style={[s.veilBrand, heading(lang, { fontSize: 32, lineHeight: 38, letterSpacing: 0 })]}>Kleal</Text>
      </View>
      <View style={s.veilText}>
        <Text style={[s.veilTitle, heading(lang, { fontSize: 28, lineHeight: 32, letterSpacing: 0 })]}>{SEARCHING.title()}</Text>
        <View style={s.veilRow}>
          <ActivityIndicator size="small" color={color.fg} style={{ transform: [{ scale: 0.75 }] }} />
          <Text style={s.veilStep}>{SEARCHING.step(dateKey)}</Text>
        </View>
        <Text style={s.veilNote}>{slow ? SEARCHING.slow() : SEARCHING.note()}</Text>
      </View>
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
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  allBtn: { height: 40, paddingHorizontal: 16, borderRadius: rad.full, backgroundColor: color.primary, justifyContent: 'center' },
  allText: { ...type.labelMedium, color: color.onPrimary } as any,

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
    backgroundColor: color.glassCard, borderRadius: rad.xl, padding: space.lg, gap: space.md,
    // Без elevation: фон полупрозрачный, и на Android тень просвечивает сквозь него — карточка сереет,
    // а под содержимым проступает светлая плашка (известная беда RN: react-native#32385).
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 12, shadowOffset: { width: 0, height: 6 },
  },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
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
  capacityControl: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.lg,
  },
  capacityButton: {
    width: 52, height: 52, borderRadius: rad.full, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  capacityButtonOff: { opacity: 0.4 },
  capacityButtonText: { fontSize: 28, lineHeight: 30, color: color.fg } as any,
  capacityValue: { minWidth: 96, alignItems: 'center' },
  capacityNumber: { fontSize: 34, lineHeight: 38, fontWeight: '700', color: color.fg } as any,
  capacityPeople: { ...type.caption, color: color.muted } as any,
  capacityFree: { ...type.bodySmall, color: color.fg, textAlign: 'center' } as any,
  capacityPlus: { ...type.caption, color: color.muted, textAlign: 'center' } as any,

  boxRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  numBox: {
    width: 56, height: 40, borderRadius: rad.md, backgroundColor: color.neutral100,
    textAlign: 'center', color: color.fg, fontSize: 16, fontWeight: '600',
  },
  boxColon: { fontSize: 18, color: color.muted },

  /** Подпись слева от значения радиуса на OF.09. Строка пояса и её значения — в WhenPicker. */
  tzLabel: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,

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
  /** O.10a: раскрытое поле стоит под своей строкой и с ней же выровнено по левому краю. */
  editBody: { paddingHorizontal: 14, paddingTop: space.sm, paddingBottom: space.md, gap: space.md },
  chev: { fontSize: 16, color: color.muted },

  linkInput: {
    height: 48, borderRadius: rad.md, backgroundColor: color.neutral100,
    paddingHorizontal: 14, color: color.fg, fontSize: 15,
  },
  noteRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  note: { flex: 1, ...type.caption, color: color.muted } as any,

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
  plusBody: { ...type.body, color: color.muted, marginBottom: space.sm } as any,

  field: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },

  cover: {
    height: 128, borderRadius: rad.lg, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  /*
    Название и кости в одной строке. `flex: 1` у самого текста, а не у строки: длинное название
    переносится на вторую строку и упирается в кости, а не уезжает под них. Кости прижаты к верху
    (`alignItems: 'flex-start'`) — при двух строках значок, стоящий по центру, выглядит съехавшим.
  */
  sumTopicRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  sumTopic: { fontSize: 19, fontWeight: '700', color: color.fg, flex: 1 },
  /** Отступ сверху равен разнице кегля и значка — так значок стоит на одной линии с первой строкой. */
  sumRoll: { paddingTop: 2 },
  sumMeta: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sumMetaAction: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  sumMetaText: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  sumRowEdit: { ...type.bodySmall, color: color.primary } as any,
  sumSummaryBox: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md, gap: 6 },
  sumSummaryHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sumSummaryLabel: { ...type.labelMedium, color: color.primary, fontWeight: '700' } as any,
  sumSummaryText: { ...type.bodySmall, color: color.fg } as any,
  sumEditBtn: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  sumEditText: { ...type.button, color: color.fg } as any,
  plusKeep: {
    height: 52, borderRadius: rad.full, backgroundColor: color.ink,
    alignItems: 'center', justifyContent: 'center',
  },
  plusKeepText: { ...type.button, color: color.onPrimary } as any,

  /** GR.13 «Searching»: ровная подложка, всё по центру, между знаком и текстом 40. */
  veil: {
    ...StyleSheet.absoluteFill, backgroundColor: color.ambientBase, alignItems: 'center',
    justifyContent: 'center', gap: 40, paddingHorizontal: 32,
  },
  veilMark: { alignItems: 'center', gap: 8 },
  veilBrand: { color: color.fg, textAlign: 'center', marginTop: -14 } as any,
  veilText: { alignItems: 'center', gap: 24, alignSelf: 'stretch' },
  veilRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  veilTitle: { color: color.fg, textAlign: 'center' } as any,
  veilStep: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: color.fg, textAlign: 'center' } as any,
  veilNote: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: '#5A616E', textAlign: 'center' } as any,
  /** Выход есть всегда, но тихий: на кадре его нет, и главным он быть не должен. */
  veilCancel: { height: 44, paddingHorizontal: 24, alignItems: 'center', justifyContent: 'center', marginTop: -16 },
  veilCancelText: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: '#5A616E' } as any,
  /** Подложка кадра — ровный «Ambient · glass pilot» #F5F1EC, без цветных пятен. */
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  /** «Step Content»: поля 12/16/24/16, между блоками шага 24. */
  body: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 24, gap: 24 },
  options: { gap: 4 },
  /** «Pref»: подпись и ряд контролов через 12. */
  pref: { gap: 12 },
  btn48: { height: 48 },
  /** «Next» стоит над полем ввода, через 22 (кадр GR.05: кнопка 676–724, поле с 746). */
  /** Без подложки: коралловое свечение под Next ложится на поле ввода, как на кадре. */
  nextDock: { paddingHorizontal: 16, paddingTop: 8, zIndex: 1 },
  dock: { paddingHorizontal: 16, paddingTop: 22 },
  input48: { height: 48, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16 },
  inputText: { flex: 1, color: color.fg, fontFamily: font.text, fontSize: 15, paddingVertical: 0 } as any,
  select: { height: 48, flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16 },
  selectText: { flex: 1, color: color.fg, fontFamily: font.text, fontSize: 15, lineHeight: 20 } as any,

  placeTop: { gap: 12 },
  /** Карта карточкой 358×134, скругление 20; «развернуть» — стеклянный круг 30 в правом нижнем. */
  mapCard: { height: 134, borderRadius: 20, overflow: 'hidden', backgroundColor: color.neutral100 },
  mapExpand: { position: 'absolute', right: 15, bottom: 15 },
  mapExpandBtn: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  /** «How far can people come from?» — поля 16, число справа, ползунок под ним. */
  radiusBox: { paddingHorizontal: 16, gap: 18 },
  radiusRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  radiusAsk: { flex: 1, fontFamily: font.text, fontSize: 15, lineHeight: 22, color: color.fg } as any,
  radiusKm: { fontFamily: font.num, fontSize: 15, lineHeight: 16, color: color.muted, fontVariant: ['tabular-nums'] } as any,
  addressBox: { gap: 12 },
  addressInput: {
    height: 48, borderRadius: 999, paddingHorizontal: 16, backgroundColor: 'rgba(255,255,255,0.56)',
    color: color.fg, fontFamily: font.text, fontSize: 15,
  } as any,

  sheetLead: { fontFamily: font.displaySemi, fontSize: 15, lineHeight: 20, color: color.fg, marginBottom: 8 } as any,
  tzList: { gap: 4, paddingBottom: 8 },
  tzRow: {
    minHeight: 52, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.24)',
  },
  tzRowOn: { backgroundColor: 'rgba(255,255,255,0.6)' },
  tzText: { flex: 1, fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.fg } as any,

  /** «Edit it myself» — пилюля 40 по ширине подписи, у левого края, через 16 под подписью. */
  editMyself: { flexDirection: 'row', alignItems: 'flex-start', marginTop: -8 },
  editMyselfBtn: { height: 40 },
  sumButtons: { gap: 8 },

  /** «Intent Summary Card»: скругление 20, обложка 128, под ней белое 45% с полями 16. */
  sumCard: { overflow: 'hidden' },
  sumCover: { height: 128, borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  sumBody: { padding: 16, gap: 8, backgroundColor: 'rgba(255,255,255,0.45)' },
  sumTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  sumTitle: { flex: 1, fontFamily: font.textSemibold, fontSize: 17, lineHeight: 22, color: color.fg } as any,
  sumLine: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sumPart: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  sumLineText: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: color.fg } as any,
  sumRows: { gap: 6, paddingTop: 4 },
  sumRow: { flexDirection: 'row', gap: 12 },
  sumKey: { width: 88, fontFamily: font.text, fontSize: 13, lineHeight: 22, color: 'rgba(24,27,34,0.6)' } as any,
  sumVal: { flex: 1, fontFamily: font.textMedium, fontSize: 13, lineHeight: 22, color: color.fg } as any,
  sumKleal: { gap: 4, paddingTop: 4 },
  sumKlealLabel: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 22, color: color.primary } as any,
  sumKlealText: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: color.fg } as any,

  spotTitle: { fontFamily: font.display, fontSize: 20, lineHeight: 24, color: color.fg } as any,
  spotSub: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted, marginBottom: 8 } as any,
  spotMap: { borderRadius: 20, overflow: 'hidden', backgroundColor: color.neutral100 },
  spotSearch: { position: 'absolute', left: 12, right: 12, top: 12 },
  spotSearchInput: {
    height: 44, borderRadius: 999, paddingHorizontal: 16, backgroundColor: 'rgba(255,255,255,0.9)',
    color: color.fg, fontFamily: font.text, fontSize: 15,
  } as any,
  /** Аккордеон GR.12b: строки 64 через 8, белое 24%, скругление 16; открытая — коралловая кромка. */
  accordion: { gap: 8, paddingBottom: 8 },
  accOpen: { gap: 16 },
  accRow: {
    minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12,
    borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.24)', borderWidth: 1, borderColor: 'transparent',
  },
  accRowOn: { borderColor: color.primary },
  accTitle: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 16, color: color.fg } as any,
  accValue: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.muted } as any,
  /** Содержимое открытой строки: поля 0/16/8/16, между блоками 16. */
  accPanel: { paddingHorizontal: 16, paddingBottom: 8, gap: 16 },
  spotPin: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  spotCorner: { position: 'absolute', bottom: 12 },
  /** Адрес под булавкой — стеклянная карточка 64: адрес полужирным, ниже район и город. */
  spotAddr: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: 12, marginVertical: 8 },
  spotAddrText: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.fg } as any,
  spotAddrSub: { fontFamily: font.text, fontSize: 13, lineHeight: 20, color: color.fg } as any,
});
