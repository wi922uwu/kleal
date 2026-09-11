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
import { useRouter, useLocalSearchParams, useNavigation } from 'expo-router';
// Свайп от края (iOS) и аппаратная «назад» (Android) снимают экран мимо любого обработчика
// кнопки. Единственный способ вклиниться — usePreventRemove; expo-router его не реэкспортирует,
// поэтому берём из навигатора, на котором он и построен.
import { usePreventRemove } from 'expo-router/react-navigation';
import Slider from '@react-native-community/slider';
import {
  INTENT, IntentStepId, STEP_HOW, FORMATS, formatLabel, formatSub,
  NATURE_TRAITS, NATURE_MAX,
  STEP_SIZE, SIZES, sizeLabel, sizeSub, GROUP_MIN_TOTAL, GROUP_FREE_MAX_TOTAL,
  GROUP_PLUS_MAX_TOTAL, GROUP_SIZE, normalizeIntentSize, initialGroupSize,
  DETAILS, EDIT_SHEET, dateChips, timeQueryFromDate, deviceTz, tzOptions, tzCity, looksLikeUrl,
  SEARCHING,
  SUMMARY_O10, summaryDate, tzOffsetLabel, intentSummaryText, hhmm, planWhenLabel,
  rollIntentName, intentNameOptions,
} from '../src/intent';
import { SEXES, sexLabel, COMPOSER_PLACEHOLDER } from '../src/onboarding';
import { RangeDial } from '../src/components/Dials';
import { WhenPicker } from '../src/components/WhenPicker';
import { RadiusMap } from '../src/components/RadiusMap';
import {
  IconChevronLeft, IconMic, IconPin, IconVideo, IconPlusRound, IconPerson, IconGroups,
  IconCalendar, IconClock, IconLink, IconPlay, IconImagePlaceholder, IconPencil, IconStar, IconDice,
} from '../src/components/icons';
import { EditSheet } from '../src/components/ProfileShell';
import { Sheet } from '../src/components/Sheet';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { resetGroupSession } from '../src/ginvites';
import { useLang, T } from '../src/i18n';
import { AddressField } from '../src/components/AddressField';
import { useOnb } from '../src/state';
import { setResults, patchResults } from '../src/results-store';
import { openResults } from '../src/results-navigation';
import {
  applyIntentEdit, beginIntentEdit, IntentEditTarget,
} from '../src/intent-edit';
import { agent, isAbort } from '../src/api';
import { color, radius as rad, space, type } from '../src/theme';

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
  }>();
  const legacy = String(params.topic || '').trim();
  const topics = String(params.topics || legacy || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
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

  /** Выбор строки на O.05/O.06: галочка, «Awesome!», и через паузу следующий вопрос. */
  const choose = (patch: Partial<Draft>, next: IntentStepId) => {
    if (ack) return;
    setDraft((d) => ({ ...d, ...patch }));
    setAck(true);
    ackTimer.current = setTimeout(() => {
      ackTimer.current = null;
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
    //
    // Ответ ЗАПОМИНАЕМ: сервер возвращает id затеи, и без него потом нечем отличить одно
    // приглашение от другого. Спека говорит «Открытых инвайтов НА ИНТЕНТ — 3», а считалось по
    // всем затеям сразу — просто потому, что заявка не знала, по какой из них её отправили
    // (проверено по живому хранилищу: из 32 заявок с затеей id не было ни у одной).
    //
    // Ждать ответа мы при этом не начинаем: человек шёл искать людей, а не сохранять карточку.
    // Не доехал id — приглашение уйдёт как раньше, без привязки, и это хуже, но не поломка.
    const savedId = agent.intentSave(String(st.profile.name || ''), intent, title || topics.join(', '), undefined, true)
      .then((r: any) => String(r?.id || ''))
      .catch(() => '');

    // Отмена принадлежит человеку: экран поиска даёт кнопку, и она рвёт именно этот запрос.
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r: any = await agent.match(intent, profile(), ctx(), ctrl.signal);
      toResults(r, intent);
      // Опознаватель затеи приезжает своим темпом и дописывается к ней уже в выдаче. Ждать его
      // до показа кандидатов незачем: без него всё работает как раньше, с ним — приглашения
      // считаются по своей затее, как требует спека («Открытых инвайтов НА ИНТЕНТ — 3»).
      savedId.then((id) => { if (id) patchResults({ intent: { ...(r?.intent || intent), id } }); });
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
    linkBroken(v) || (v.mode === 'online' && v.size === 'group' && !v.link.trim());

  const sizeBlockOf = (v: Draft, set: SetDraft) => (
    <View style={s.chipRowWrap}>
      {SIZES.map(([k]) => (
        <Chip
          key={k}
          label={sizeLabel(k)}
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

  /** Режим в листе не двигает мастер: выбранное значение коммитится обратно прямо в summary. */
  const modeBlockOf = (v: Draft, set: SetDraft) => (
    <View style={s.chipRowWrap}>
      {FORMATS.map(([k]) => (
        <Chip
          key={k}
          label={formatLabel(k)}
          on={v.mode === k}
          onPress={() => set((x) => ({ ...x, mode: k }))}
        />
      ))}
    </View>
  );

  /** Один числовой контрол вместо двух пользовательских типов группы. */
  const groupSizeBlockOf = (v: Draft, set: SetDraft, target: 'draft' | 'edit') => {
    const total = v.groupSize || GROUP_MIN_TOTAL;
    const change = (next: number) => {
      if (next > GROUP_FREE_MAX_TOTAL) {
        setGroupSizeTarget(target);
        setGroupSizeOpen(true);
        return;
      }
      set((x) => ({ ...x, size: 'group', groupSize: Math.max(GROUP_MIN_TOTAL, next) }));
    };
    return (
      <View>
        <View style={s.capacityControl}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={T('Уменьшить размер группы', 'Decrease group size', 'Disminuir el tamaño del grupo')}
            accessibilityState={{ disabled: total <= GROUP_MIN_TOTAL }}
            disabled={total <= GROUP_MIN_TOTAL}
            style={[s.capacityButton, total <= GROUP_MIN_TOTAL && s.capacityButtonOff]}
            onPress={() => change(total - 1)}
          >
            <Text style={s.capacityButtonText}>−</Text>
          </Pressable>
          <View style={s.capacityValue}>
            <Text style={s.capacityNumber}>{total}</Text>
            <Text style={s.capacityPeople}>{GROUP_SIZE.people(total)}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={T('Увеличить размер группы', 'Increase group size', 'Aumentar el tamaño del grupo')}
            accessibilityHint={total >= GROUP_FREE_MAX_TOTAL ? GROUP_SIZE.plusLimit() : undefined}
            style={s.capacityButton}
            onPress={() => change(Math.min(GROUP_PLUS_MAX_TOTAL, total + 1))}
          >
            <Text style={s.capacityButtonText}>+</Text>
          </Pressable>
        </View>
        <Text style={s.capacityFree}>{GROUP_SIZE.freeLimit()}</Text>
        <Text style={s.capacityPlus}>{GROUP_SIZE.plusLimit()}</Text>
      </View>
    );
  };

  /* O.07 — дата, круглый циферблат и пояс. Тот же WhenPicker, что у группового плана: разметка
     здесь была своя и слово в слово такая же, а копии в этом проекте расходятся. */
  const whenBlockOf = (
    v: Draft,
    set: SetDraft,
    onPressTz?: () => void,
    only?: 'date' | 'time',
  ) => (
    <WhenPicker
      value={{ date: v.date, minutes: v.minutes, tz: v.tz }}
      // В точечной правке общий контрол остаётся единым, но соседнее значение не меняется даже
      // внутри edraft. Поэтому дата и время сохраняются независимо, без копии WhenPicker.
      onChange={(w) => set((x) => ({
        ...x,
        date: only === 'time' ? x.date : w.date,
        minutes: only === 'date' ? x.minutes : w.minutes,
        tz: w.tz,
      }))}
      onDragChange={setDragging}
      onPressTz={onPressTz}
    />
  );

  const whoBlockOf = (v: Draft, set: SetDraft) => (
    <>
      <LabelRow Icon={IconPlay} text={DETAILS.audience()} />
      <View style={s.chipRowWrap}>
        {SEXES.map(([k]) => (
          <Chip key={k} label={sexLabel(k)} on={v.sex === k} onPress={() => set((x) => ({ ...x, sex: k }))} />
        ))}
      </View>

      <LabelRow Icon={IconPerson} text={DETAILS.age()} />
      <RangeDial
        lo={v.minAge}
        hi={v.maxAge}
        onChange={(lo, hi) => set((x) => ({ ...x, minAge: lo, maxAge: hi }))}
        onDragChange={setDragging}
      />
      <View style={s.boxRow}>
        <NumBox
          value={String(v.minAge)}
          onChange={(t) => {
            const n = Math.max(18, Math.min(v.maxAge, parseInt(t || '18', 10) || 18));
            set((x) => ({ ...x, minAge: n }));
          }}
        />
        <Text style={s.boxColon}>–</Text>
        <NumBox
          value={String(v.maxAge)}
          onChange={(t) => {
            const n = Math.min(80, Math.max(v.minAge, parseInt(t || '80', 10) || 80));
            set((x) => ({ ...x, maxAge: n }));
          }}
        />
      </View>
    </>
  );

  /*
    Характер. Оси те же, что заполняет тест личности, — просить можно только то, что у кандидата
    в профиле есть. Ничего не отметив, человек не сужает поиск: подсказка говорит это прямо,
    потому что молчащий фильтр люди трактуют как «значит, ищет всех подряд».
  */
  const natureBlockOf = (v: Draft, set: SetDraft) => (
    <>
      <LabelRow Icon={IconPerson} text={DETAILS.nature()} />
      <Text style={s.natureHint}>{DETAILS.natureHint()}</Text>
      <View style={s.chipRowWrap}>
        {NATURE_TRAITS.map((t) => {
          const on = v.nature[t.axis] === t.token;
          const full = Object.keys(v.nature).length >= NATURE_MAX;
          // Забита ли ось — видно по тому, что в ней уже стоит другой токен: тогда нажатие
          // ЗАМЕНЯЕТ, а не добавляет, и потолок не мешает.
          const busyAxis = !!v.nature[t.axis];
          const blocked = !on && !busyAxis && full;
          return (
            <Chip
              key={t.axis + t.token}
              label={t.label()}
              on={on}
              dim={blocked}
              onPress={() =>
                set((x) => {
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
      {Object.keys(v.nature).length >= NATURE_MAX ? (
        <Text style={s.natureHint}>{DETAILS.natureLimit()}</Text>
      ) : null}
    </>
  );

  const linkBlockOf = (v: Draft, set: SetDraft) => (
    <>
      <LabelRow Icon={IconLink} text={DETAILS.link()} />
      <TextInput
        style={s.linkInput}
        value={v.link}
        onChangeText={(t) => set((x) => ({ ...x, link: t }))}
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
  const placeBlockOf = (v: Draft, set: SetDraft) => {
    // Центр и признак «булавку увели от дома» считаются от ТОГО ЖЕ черновика, что правится:
    // иначе лист правки рисовал бы карту по draft, а двигал бы edraft.
    const la = v.lat ?? homeLat;
    const lo = v.lon ?? homeLon;
    const away = v.lat != null || v.lon != null;
    return (
      <>
        <LabelRow Icon={IconPin} text={DETAILS.district()} />
        <View style={s.map}>
          <RadiusMap
            lat={la}
            lon={lo}
            km={v.radiusKm}
            onMove={(la, lo) => set((x) => ({ ...x, lat: la, lon: lo, venue: false }))}
            onDragChange={setDragging}
          />
        </View>
        <View style={s.mapHintRow}>
          <Text style={s.mapHint}>{away ? DETAILS.centerMoved() : DETAILS.dragPin()}</Text>
          {away ? (
            <Pressable
              accessibilityRole="button"
              hitSlop={8}
              onPress={() => set((x) => ({ ...x, lat: undefined, lon: undefined, venue: false }))}
            >
              <Text style={s.mapReset}>{DETAILS.backHome()}</Text>
            </Pressable>
          ) : null}
        </View>

        {/* Точное место можно назвать сразу — но чужим оно не показывается: его выдаёт
            только план после взаимного подтверждения (OF.C3). */}
        <AddressField
          style={s.linkInput}
          placeholder={DETAILS.exactAddress()}
          value={v.address || ''}
          onChange={(t) => set((x) => ({ ...x, address: t }))}
          onPick={(hit) => set((x) => ({ ...x, address: hit.label,
                                         lat: hit.lat, lon: hit.lon, venue: true }))}
        />

        <View style={s.radiusRow}>
          <Text style={s.tzLabel}>{DETAILS.radius()}</Text>
          <Text style={s.radiusValue}>{v.radiusKm} km</Text>
        </View>
        <Slider
          minimumValue={1}
          maximumValue={50}
          step={1}
          value={v.radiusKm}
          onValueChange={(km) => set((x) => ({ ...x, radiusKm: Math.round(km) }))}
          minimumTrackTintColor={color.primary}
          maximumTrackTintColor={color.neutral100}
          thumbTintColor={color.primary}
        />
        <Text style={s.privacyNote}>{DETAILS.exactAddressNote()}</Text>
      </>
    );
  };

  const linkBlock = linkBlockOf(draft, setDraft);
  const placeBlock = placeBlockOf(draft, setDraft);

  /** Отмеченные черты одной строкой — для сводки O.10 и строк листа правки. */
  const natureOf = (v: Draft) => NATURE_TRAITS.filter((t) => v.nature[t.axis] === t.token)
    .map((t) => t.label()).join(', ');
  const natureSummary = natureOf(draft);

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
  const editRows = (v: Draft): [IntentEditTarget, any, string, string][] => ([
    ...(v.size === 'group'
      ? ([['groupSize', IconPerson, GROUP_SIZE.row(), GROUP_SIZE.people(v.groupSize || GROUP_MIN_TOTAL)]] as [IntentEditTarget, any, string, string][])
      : []),
    ['date', IconCalendar, EDIT_SHEET.date(), summaryDate(v.date)],
    ['time', IconClock, EDIT_SHEET.time(), hhmm(v.minutes)],
    ['timezone', IconClock, EDIT_SHEET.timezone(), tzCity(v.tz)],
    ['audience', IconPerson, EDIT_SHEET.audience(),
      `${v.sex && v.sex !== 'Any' ? sexLabel(v.sex) + ', ' : ''}${v.minAge}–${v.maxAge}`],
    ['nature', IconStar, DETAILS.nature(), natureOf(v) || EDIT_SHEET.noData()],
    ...(v.mode !== 'online'
      ? ([['place', IconPin, DETAILS.district(), v.address?.trim() || where || EDIT_SHEET.noData()]] as [IntentEditTarget, any, string, string][])
      : []),
    ...(v.mode !== 'offline'
      ? ([['link', IconLink, EDIT_SHEET.link(), v.link.trim() || EDIT_SHEET.noData()]] as [IntentEditTarget, any, string, string][])
      : []),
  ]);

  /** Контрол раскрытой строки — тот же, что на шаге мастера, только пишет в черновик листа. */
  const editField = (k: IntentEditTarget, v: Draft) => {
    const set: SetDraft = (fn) => setEdraft((x) => (x ? fn(x) : x));
    if (k === 'mode') {
      return (
        <>
          {modeBlockOf(v, set)}
          {v.mode === 'online' && v.size === 'group' && !v.link.trim() ? (
            <>
              <Text style={s.natureHint}>{EDIT_SHEET.groupOnlineLinkNeeded()}</Text>
              {linkBlockOf(v, set)}
            </>
          ) : null}
        </>
      );
    }
    if (k === 'size') {
      return (
        <>
          {sizeBlockOf(v, set)}
          {v.size === 'group' ? (
            <>
              <Text style={s.natureHint}>{EDIT_SHEET.groupSizeNeeded()}</Text>
              {groupSizeBlockOf(v, set, 'edit')}
            </>
          ) : null}
          {v.mode === 'online' && v.size === 'group' && !v.link.trim() ? (
            <>
              <Text style={s.natureHint}>{EDIT_SHEET.groupOnlineLinkNeeded()}</Text>
              {linkBlockOf(v, set)}
            </>
          ) : null}
        </>
      );
    }
    if (k === 'groupSize') return groupSizeBlockOf(v, set, 'edit');
    if (k === 'date') return whenBlockOf(v, set, undefined, 'date');
    if (k === 'time') return whenBlockOf(v, set, undefined, 'time');
    if (k === 'timezone') {
      return tzOptions().map((z) => (
        <Pressable
          key={z}
          accessibilityRole="button"
          accessibilityState={{ selected: z === v.tz }}
          style={[s.pickRow, z === v.tz && s.pickRowOn]}
          onPress={() => set((x) => ({ ...x, tz: z }))}
        >
          <Text style={s.pickText}>{tzCity(z)}</Text>
          {z === v.tz ? <Text style={s.pickCheck}>✓</Text> : null}
        </Pressable>
      ));
    }
    if (k === 'audience') return whoBlockOf(v, set);
    if (k === 'nature') return natureBlockOf(v, set);
    if (k === 'place') return placeBlockOf(v, set);
    if (k === 'link') return linkBlockOf(v, set);
    if (k === 'both') {
      return (
        <>
          {placeBlockOf(v, set)}
          <View style={s.bothSplit} />
          {linkBlockOf(v, set)}
        </>
      );
    }
    return null;
  };

  const openEdit = (target: IntentEditTarget | '' = '') => {
    setEditPick(target);
    setEdraft(beginIntentEdit(draft));
    setEditOpen(true);
  };

  const chooseEditTarget = (target: IntentEditTarget) => {
    // Переключение строки отменяет незавершённую правку предыдущей: один лист — один параметр.
    setEdraft(beginIntentEdit(draft));
    setEditPick(target);
  };

  const editBlocked = (v: Draft, target: IntentEditTarget | '') => {
    if (!target) return false;
    const touchesLink = target === 'link' || target === 'both' || target === 'mode' || target === 'size';
    return (touchesLink && linkBroken(v))
      || ((target === 'link' || target === 'mode' || target === 'size')
        && v.mode === 'online' && v.size === 'group' && !v.link.trim());
  };

  /**
   * Потолок высоты листа правки. 300 — это шапка, две кнопки и безопасные отступы, которые лист
   * занимает ВНЕ прокрутки; ниже 240 не опускаемся, иначе на маленьком экране в лист не влезает
   * даже одно поле.
   */
  const sheetMax = Math.max(240, Math.round(win.height - 300));

  /** Последний шаг деталей зависит от типа встречи — см. шапку src/intent.ts. */
  const lastStep: IntentStepId =
    draft.mode === 'offline' ? 'place' : draft.mode === 'hybrid' ? 'both' : 'link';
  const compactThreeStep = groupOnline || draft.mode === 'offline';
  const detailIndex = step === 'when' ? 0 : step === 'who' ? 1
    : draft.mode === 'offline' && step === 'nature' ? 1
    : compactThreeStep ? 2 : step === 'nature' ? 2 : 3;

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
    from === 'size' ? 'how'
    : from === 'capacity' ? 'size'
    : from === 'when' ? (grouped ? 'capacity' : 'size')
    : from === 'who' ? 'when'
    : from === 'nature' ? 'who'
    : from === 'link' || from === 'both' || from === 'place' ? 'nature'
    : from === 'summary' ? lastStep
    : null;

  /**
   * Один выход назад на оба входа — кнопку в шапке и системный жест.
   *
   * Порядок проверок идёт от верхнего слоя к нижнему. Иначе на Android «назад» при открытом
   * листе срабатывает дважды: лист закрывается по onRequestClose И экран отступает на шаг.
   */
  const goBack = () => {
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
  usePreventRemove(step !== 'how' || groupSizeOpen || tzOpen || editOpen || busy, (e) => {
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

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} style={s.back} onPress={goBack}>
            <IconChevronLeft />
          </Pressable>
          <View style={{ flex: 1 }} />
          {/* Кнопка называется «Все интенты» — значит ведёт к ним, а не на главную. Раньше она
              делала replace('/home'), и человек, искавший список своих затей, оказывался на
              ленте (поймано 14 августа). Список живёт во вкладке «Интенты» — это /activity. */}
          <Pressable accessibilityRole="button" style={s.allBtn} onPress={() => { router.dismissTo('/home'); router.navigate('/activity'); }}>
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
                      Icon={k === '1:1' ? IconPerson : IconGroups}
                      title={sizeLabel(k)}
                      sub={sizeSub(k)}
                      on={draft.size === k}
                      onPress={() => choose(
                        {
                          size: k as Draft['size'],
                          groupSize: k === 'group' ? (draft.groupSize || GROUP_MIN_TOTAL) : undefined,
                        },
                        k === 'group' ? 'capacity' : 'when'
                      )}
                    />
                  ))}
              {ack ? <Ack /> : null}
            </>
          ) : step === 'capacity' ? (
            <>
              <QuestionHead title={GROUP_SIZE.ask()} sub={GROUP_SIZE.sub()} />
              <View style={s.card}>
                {groupSizeBlockOf(draft, setDraft, 'draft')}
                <Cta
                  label={INTENT.next()}
                  onPress={() => draft.groupSize && draft.groupSize > GROUP_FREE_MAX_TOTAL
                    ? (setGroupSizeTarget('draft'), setGroupSizeOpen(true))
                    : setStep('when')}
                />
              </View>
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
                  <Stepper current={detailIndex} count={compactThreeStep ? 3 : 4} />
                </>
              )}

              {step === 'when' ? (
                <View style={s.card}>
                  {/* O.07a: строка пояса открывает лист выбора — выбор применяется по «Применить». */}
                  {whenBlockOf(draft, setDraft, () => { setTzPick(draft.tz); setTzOpen(true); })}
                  <Cta label={INTENT.next()} onPress={() => setStep('who')} />
                </View>
              ) : null}

              {step === 'who' ? (
                <View style={s.card}>
                  {whoBlockOf(draft, setDraft)}
                  <Cta label={INTENT.next()} onPress={() => setStep(groupOnline ? 'link' : 'nature')} />
                </View>
              ) : null}

              {step === 'nature' ? (
                <View style={s.card}>
                  {natureBlockOf(draft, setDraft)}
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
                  <Cta label={INTENT.next()} disabled={groupLinkBlocked(draft)} onPress={toSummary} />
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
                  <Cta label={INTENT.next()} disabled={linkBroken(draft)} onPress={toSummary} />
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
                  where={where}
                  nature={natureSummary}
                  draft={draft}
                  category={category}
                  busy={busy}
                  onStart={finish}
                  onEdit={() => openEdit()}
                  onEditField={openEdit}
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
            <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send', 'Enviar')} onPress={send}>
              <IconMic />
            </Pressable>
          </View>
        </View>

        {/* Покупки Plus ещё нет: предел 20 виден внутри Group-flow, но недоступное действие честно выключено. */}
        <Sheet visible={groupSizeOpen} onClose={() => setGroupSizeOpen(false)} title={GROUP_SIZE.plusTitle()}>
          <Text style={s.plusBody}>{GROUP_SIZE.plusBody()}</Text>
          <View style={[s.cta, { opacity: 0.45 }]} accessibilityRole="button" accessibilityState={{ disabled: true }}>
            <Text style={s.ctaText}>{GROUP_SIZE.getPlus()}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            style={s.plusKeep}
            onPress={() => {
              setGroupSizeOpen(false);
              if (groupSizeTarget === 'edit') {
                setEdraft((x) => x ? ({ ...x, size: 'group', groupSize: GROUP_FREE_MAX_TOTAL }) : x);
              } else {
                setDraft((x) => ({ ...x, size: 'group', groupSize: GROUP_FREE_MAX_TOTAL }));
                setStep('when');
              }
            }}
          >
            <Text style={s.plusKeepText}>{GROUP_SIZE.keepAtFive()}</Text>
          </Pressable>
        </Sheet>

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

        {/*
          O.10a — правка собранного интента.

          Лист был УКАЗАТЕЛЕМ: строка только подсвечивалась, а «Изменить» уводило на шаг мастера —
          и там стояла кнопка «Дальше», ведущая ДАЛЬШЕ по цепочке, а не обратно в сводку. Поправить
          одну дату стоило четырёх экранов, и сводка на выходе заново дёргала agent.categorize.
          Теперь строка раскрывается и поле правится тут же, тем же контролом, что на шаге.

          Правки идут в edraft: «Отмена» и крестик обязаны отменять — правило листа записано в
          src/components/ProfileShell.tsx. editPick — белый список commit: даже общий WhenPicker
          не может случайно поменять дату вместе со временем. Режим/формат доступны здесь же;
          обязательный размер или Group Online-ссылка показываются внутри выбранного параметра.
        */}
        <EditSheet
          open={editOpen}
          title={EDIT_SHEET.title()}
          onClose={() => setEditOpen(false)}
          onAccept={() => {
            if (!edraft || editBlocked(edraft, editPick)) return;
            // Пустой target означает, что человек открыл общий список и ничего не выбрал.
            // В остальных случаях коммитится только белый список выбранного параметра.
            if (editPick) setDraft((current) => applyIntentEdit(current, edraft, editPick));
            setEditOpen(false);
          }}
          acceptLabel={DETAILS.apply()}
          cancelLabel={DETAILS.cancel()}
          // Циферблат и карта живут внутри прокрутки листа, и жест у них общий: пока прокрутка
          // включена, она забирает вертикальное движение себе. То же место уже решено так в профиле.
          scrollEnabled={!dragging}
          // Своей высоты у листа нет — он растёт вверх по содержимому. С раскрытым полем «Применить»
          // уезжала бы за верх экрана, и нажать её было бы нечем.
          maxHeight={sheetMax}
        >
          {edraft ? editRows(edraft).map(([k, Icon, label, value]) => (
            <View key={k}>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ expanded: editPick === k }}
                style={[s.pickRow, editPick === k && s.pickRowOn]}
                // Раскрыто РОВНО одно поле: два крупных разом (карта плюс циферблат) лист не держит.
                onPress={() => editPick === k ? setEditPick('') : chooseEditTarget(k)}
              >
                <Icon size={20} c={color.fg} />
                <View style={{ flex: 1 }}>
                  <Text style={s.pickText}>{label}</Text>
                  <Text style={s.pickSub} numberOfLines={1}>{value}</Text>
                </View>
                <Text style={s.chev}>{editPick === k ? '⌃' : '⌄'}</Text>
              </Pressable>
              {editPick === k ? <View style={s.editBody}>{editField(k, edraft)}</View> : null}
            </View>
          )) : null}
          {edraft && editPick && editBlocked(edraft, editPick) && linkBroken(edraft) ? (
            <Text style={s.err}>{DETAILS.linkBad()}</Text>
          ) : null}
          {edraft && editPick && (editPick === 'link' || editPick === 'mode' || editPick === 'size')
            && edraft.mode === 'online' && edraft.size === 'group' && !edraft.link.trim() ? (
            <Text style={s.err}>{DETAILS.groupLinkRequired()}</Text>
          ) : null}
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
function Stepper({ current, count = 4 }: { current: number; count?: number }) {
  return (
    <View style={s.stepper}>
      {Array.from({ length: count }, (_, i) => i).map((i) => (
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
  topic, onRollTopic, draft, category, where, nature, busy, onStart, onEdit, onEditField,
}: {
  topic: string;
  /** Кости у названия: подобрать другое. Пусто — костей нет (нечего предлагать). */
  onRollTopic?: () => void;
  draft: Draft;
  /** Отмеченные черты одной строкой. Собраны на экране — здесь только показываются. */
  nature: string;
  category: string;
  /** Подпись места в сводке: город профиля — район на OF.09 задаёт карта, а не список. */
  where: string;
  busy: boolean;
  onStart: () => void;
  onEdit: () => void;
  onEditField: (target: IntentEditTarget) => void;
}) {
  const facts: [string, string, IntentEditTarget?][] = [
    /*
      ТИП И ФОРМАТ БЕЗ СТРЕЛКИ И БЕЗ НАЖАТИЯ. Это первые два решения всего создания, и от них
      зависит остальное: у офлайна спрашивают место и радиус, у онлайна — ссылку; у группы есть
      размер, у 1:1 его нет. Правка отсюда означала бы возврат в начало цепочки с уже собранными
      ответами на вопросы, которых при другом выборе не задают. Менять их надо через «Поправить»,
      проходя цепочку заново, — а стрелка обещала правку на месте.
    */
    [SUMMARY_O10.mode(), draft.mode ? formatLabel(draft.mode) : '—'],
    [SUMMARY_O10.format(), draft.size ? sizeLabel(draft.size) : '—'],
    ...(draft.size === 'group'
      ? ([[GROUP_SIZE.row(), GROUP_SIZE.people(draft.groupSize || GROUP_MIN_TOTAL), 'groupSize']] as [string, string, IntentEditTarget][])
      : []),
    ...(category ? ([[SUMMARY_O10.category(), category]] as [string, string][]) : []),
    [DETAILS.nature(), nature || EDIT_SHEET.noData(), 'nature'],
    [SUMMARY_O10.audience(),
      `${draft.sex && draft.sex !== 'Any' ? sexLabel(draft.sex) + ', ' : ''}${draft.minAge}–${draft.maxAge}`, 'audience'],
  ];
  return (
    <View style={s.card}>
      <View style={s.cover}><IconImagePlaceholder size={44} /></View>
      {topic ? (
        <View style={s.sumTopicRow}>
          <Text style={s.sumTopic} numberOfLines={2}>{topic}</Text>
          {onRollTopic ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={SUMMARY_O10.roll()}
              onPress={onRollTopic}
              hitSlop={12}
              style={({ pressed }) => [s.sumRoll, pressed && { opacity: 0.6 }]}
            >
              <IconDice size={20} c={color.muted} />
            </Pressable>
          ) : null}
        </View>
      ) : null}

      <View style={s.sumMeta}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={EDIT_SHEET.change(EDIT_SHEET.date())}
          style={s.sumMetaAction}
          onPress={() => onEditField('date')}
        >
          <IconCalendar />
          <Text style={s.sumMetaText}>{summaryDate(draft.date)}</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={EDIT_SHEET.change(EDIT_SHEET.time())}
          style={s.sumMetaAction}
          onPress={() => onEditField('time')}
        >
          <IconClock />
          {/* Пояс показывается только при расхождении с поясом устройства. */}
          <Text style={s.sumMetaText}>
            {hhmm(draft.minutes)}{draft.tz && draft.tz !== deviceTz() ? ` ${tzOffsetLabel(draft.tz)} ${tzCity(draft.tz)}` : ''}
          </Text>
        </Pressable>
      </View>
      {/* Гибрид показывает ОБЕ строки: у него и место, и ссылка (HY.09). Раньше условие места
          было привязано к офлайну, и гибрид уезжал в поиск, показав человеку только ссылку. */}
      {draft.mode !== 'offline' ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={EDIT_SHEET.change(EDIT_SHEET.link())}
          style={s.sumMeta}
          onPress={() => onEditField('link')}
        >
          <IconLink size={16} c={color.muted} />
          <Text style={s.sumMetaText} numberOfLines={1}>{draft.link.trim() || EDIT_SHEET.noData()}</Text>
        </Pressable>
      ) : null}
      {draft.mode !== 'online' ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={EDIT_SHEET.change(DETAILS.district())}
          style={s.sumMeta}
          onPress={() => onEditField('place')}
        >
          <IconPin size={16} c={color.muted} />
          <Text style={s.sumMetaText}>
            {where ? `${where} · ${draft.radiusKm} km` : EDIT_SHEET.noData()}
          </Text>
        </Pressable>
      ) : null}

      {facts.map(([k, v, target]) => (
        <Pressable
          key={k}
          accessibilityRole={target ? 'button' : undefined}
          accessibilityLabel={target ? EDIT_SHEET.change(k) : undefined}
          style={({ pressed }) => [s.sumRow, target && pressed && { opacity: 0.7 }]}
          onPress={target ? () => onEditField(target) : undefined}
        >
          <Text style={s.sumKey}>{k}</Text>
          <Text style={s.sumVal}>{v}</Text>
          {target ? <Text style={s.sumRowEdit}>›</Text> : null}
        </Pressable>
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
            topic, size: draft.size, groupSize: draft.groupSize, sex: draft.sex,
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
  plusBody: { ...type.body, color: color.muted, marginBottom: space.sm } as any,

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
  sumRow: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
  sumKey: { ...type.bodySmall, color: color.muted } as any,
  sumVal: { ...type.bodySmall, color: color.fg, flex: 1, textAlign: 'right' } as any,
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

  veil: {
    ...StyleSheet.absoluteFill, backgroundColor: color.bg, alignItems: 'center',
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
