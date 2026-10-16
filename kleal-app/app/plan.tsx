/**
 * Встреча — кадры O.20–O.25, от предложения до отзыва.
 *
 * UX-КАРКАС: вид натянется поверх; копия, состояния и разбор — в src/chat.ts.
 *
 * Один экран на всю жизнь плана, а не шесть маршрутов. Так задумано: «Поправить план» и «Открыть
 * ссылку» — это одно и то же место в разное время, и разводить их значило бы, что человек, глядя
 * на встречу, каждый раз оказывается где-то ещё. Состояние считает planPhase:
 *
 *   форма      — плана ещё нет, выбираем время и место (O.20, первая половина);
 *   waiting    — отправлено, ждём ответа (O.20);
 *   confirmed  — оба подтвердили; ссылка придёт позже (O.21);
 *   soon       — за десять минут ссылка открывается (O.22);
 *   now        — время пришло (O.23);
 *   after      — «состоялось ли» и отзыв (O.24, O.25);
 *   cancelled  — кто-то отказался.
 *
 * Правила, которые держит СЕРВЕР, а не экран: ссылку он отдаёт только подтвердившим (OF.C3);
 * контрпредложение не отменяет встречу, старое время держится, пока второй не ответит; «состоялось
 * ли» и оценка пишутся одной записью, чтобы оценка не стёрла ответ про сам факт встречи.
 *
 * Правило, которое держит ЭКРАН: ссылка становится кнопкой за десять минут, не раньше. Она уже
 * пришла с сервера — это не защита, а фокус, и в этом разница с адресом, который сервер прячет
 * по-настоящему.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image, ActivityIndicator,
  KeyboardAvoidingView, Platform, Linking, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams, useFocusEffect } from 'expo-router';
import {
  CHAT, PLAN, OFB, OFD, ONB, OND, HYB, RATINGS, LINK_LEAD_MIN, planWhen, personStatus, planPhase, minutesToStart, linkOpensAt,
} from '../src/chat';
import { DETAILS, dateChips, hhmm, peerLocalTime, looksLikeUrl, withScheme } from '../src/intent';
import { callService } from '../src/gplan';
import { TimeDial } from '../src/components/Dials';
import { useKeyboardInset, dockBottom, useSheetKeyboard } from '../src/keyboard';
import { normalizeTimePart } from '../src/timeInput';
import { useLang, T, getLang, dateLocale, use12h } from '../src/i18n';
import { useOnb } from '../src/state';
import { mediaUrl, agent, ensureMe, isMe, pidOf } from '../src/api';
import { planChatCopy, planChatPeerRef, preparePlanChat } from '../src/plan-chat';
import {
  IconChevronLeft, IconCalendar, IconClock, IconPin, IconLink, IconPerson, IconExit, IconCheck, IconCalendarCheck, IconInfo, IconUserCheck, IconTimer, IconVideo } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { Sheet } from '../src/components/Sheet';
import { AddressField } from '../src/components/AddressField';
import { color, font, heading, labelFamily, radius as rad, space, type } from '../src/theme';
import { GlassBack, GlassSurface } from '../src/components/LiquidGlass';
import { Cover } from '../src/components/Cover';
import { openResults } from '../src/results-navigation';
import { interestEmoji } from '../src/candidates';
import { useNavCollapse } from '../src/navScroll';

export default function Plan() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Листы с полями ввода: на Android клавиатура ложится поверх них. См. src/keyboard.ts. */
  const kb = useKeyboardInset();

  const params = useLocalSearchParams<{
    who?: string; who_id?: string; title?: string; photo?: string; link?: string; id?: string;
    address?: string; mode?: string;
  }>();
  /**
  * Имя собеседника. С ГЛАВНОЙ план открывается только по `id` (app/home.tsx: «К плану»), и
  * параметра `who` там нет. А на нём висит вся копия с именем — «Sofia тоже её увидит»,
  * «Ждём ответа: Sofia», «Скажи Sofia, что не сможешь». Без него в тексте оставалась дырка:
  * «откроется за 10 минут до начала —  тоже её увидит». Сервер отдаёт `other` в самом плане,
  * поэтому после загрузки собеседник определяется по плану; параметр нужен только до загрузки.
  */
  const otherParam = String(params.who || '').trim();
  const otherIdParam = String(params.who_id || '').trim();
  const intentTitle = String(params.title || '').trim();
  const photo = String(params.photo || '');
  const linkFromIntent = String(params.link || '').trim();
  const planId = String(params.id || '').trim();
  /**
   * Режим встречи. Приходит ИЗ ИНТЕНТА, по которому вы совпали, — а не угадывается по тому, есть
   * ли в форме ссылка.
   *
   * Так было раньше и это ломалось в обе стороны: у офлайн-интента форма спрашивала ссылку на
   * звонок (её там быть не должно вовсе), а у онлайн-интента план молча уезжал на сервер как
   * offline, если человек не успел вставить ссылку прямо сейчас, — и второй получал встречу
   * вживую вместо звонка. Пустой параметр (старые ссылки) читается по старому правилу.
   */
  const modeFromIntent = String(params.mode || '').trim().toLowerCase();

  const me = String(st.profile.name || '');
  const ru = getLang() === 'ru';

  const [date, setDate] = useState(() => dateChips(1)[0].key);
  const [minutes, setMinutes] = useState(20 * 60);
  const [district, setDistrict] = useState(String(st.profile.city || ''));
  const [link, setLink] = useState(linkFromIntent);
  /** OF.09 → OF.20: точное место из интента подхватывается, чтобы не спрашивать дважды. */
  const [address, setAddress] = useState(String(params.address || '').trim());
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [openingChat, setOpeningChat] = useState(false);
  const [chatError, setChatError] = useState('');
  const chatRequest = useRef(false);
  const chatContext = useRef<symbol | null>(null);
  const chatCopy = planChatCopy(getLang());
  const [plan, setPlan] = useState<any>(null);
  // Собеседник — подписью И id (kleal-ms/docs/IDENTITY.md): по подписи тёзок не различить.
  const otherRef = plan ? planChatPeerRef(plan, me) : { name: otherParam, id: otherIdParam };
  const other = otherRef.name;
  const otherId = otherRef.id;
  const otherPeer = useMemo(() => ({ name: other, id: otherId }), [other, otherId]);
  const [, setMeKnown] = useState('');
  useEffect(() => { ensureMe().then(setMeKnown); }, []);
  const chatContextKey = `${me}\n${planId}\n${plan?.id || ''}`;
  // A slow preflight must not navigate after Back/another tab, even if the user reopens this plan.
  useFocusEffect(useCallback(() => {
    chatContext.current = Symbol(chatContextKey);
    return () => { chatContext.current = null; };
  }, [chatContextKey]));
  const [peerTz, setPeerTz] = useState('');
  /** Часы идут — экран сам переходит из «подтверждено» в «через десять минут» и дальше. */
  const [tick, setTick] = useState(Date.now());
  /** Ответы O.24/O.25, пока не отправлены. */
  const [rating, setRating] = useState('');
  const [thanks, setThanks] = useState('');
  /** O.20a: ссылка, которую доносят в уже согласованный план. */
  const [linkDraft, setLinkDraft] = useState('');
  /** O.21b/OF.21a: лист встречного времени. НЕ новая встреча — план живёт, изменение ложится рядом. */
  const [countering, setCountering] = useState(false);
  /** OF.20c: лист «Fix the plan» и выбранный в нём раунд. */
  const [fixing, setFixing] = useState(false);
  const [fixRound, setFixRound] = useState<number | null>(null);
  /** OF.19e: «Pick someone else» — тот же экран, другое тело; люди с сервера (mplan-alternatives). */
  const [picking, setPicking] = useState(false);
  const [alts, setAlts] = useState<any[] | null>(null);
  // Экран живёт между планами (переход по ссылке на другой план) — выбор другого человека относится к одному.
  useEffect(() => { setPicking(false); setFixing(false); }, [planId]);
  /** OF.21a: выбранный сдвиг (минуты от текущего начала) или своё время часами-минутами. */
  const [sugDelta, setSugDelta] = useState<number | null>(60);
  /** Тронул ли человек время в листе правки: у звонка смена одной ссылки не должна слать встречное время. */
  const timeTouched = useRef(false);
  const kbUp = useSheetKeyboard() > 0;
  const [askCool, setAskCool] = useState(false);
  /** OF.C3a: день встречного времени (сдвиг в днях от дня плана) и место (район), если его меняют. */
  const [sugDay, setSugDay] = useState(0);
  const [sugPlaceOpen, setSugPlaceOpen] = useState(false);
  const [sugPlace, setSugPlace] = useState('');
  const [sugH, setSugH] = useState('');
  const [sugM, setSugM] = useState('');
  /** OF.20a: место, которое доносят в согласованный план. */
  const [placeDraft, setPlaceDraft] = useState('');
  /** OF.24a: лист причины «не состоялась». */
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reasonPick, setReasonPick] = useState('');
  /** Подтверждение отмены: на сервере отменённая встреча терминальна, вернуть её нельзя. */
  const [dropping, setDropping] = useState(false);
  /** OF.22c — лист «опаздываю»: на сколько. OF.23c — «место закрыто» (отмечает сам человек). */
  const [lateOpen, setLateOpen] = useState(false);
  const [lateMin, setLateMin] = useState(20);
  const [spotClosed, setSpotClosed] = useState(false);
  /** OF.25 — лист «How was it?» после «Yes, we met». */
  const [rateOpen, setRateOpen] = useState(false);
  /** HY.25 — каким входом встреча в итоге состоялась. Только у гибрида. */
  const [howMet, setHowMet] = useState<'' | 'in_person' | 'call' | 'both'>('');
  /** «Другое время» после отмены: составляем новую встречу, опрос не должен возвращать старую. */
  const composing = useRef(false);
  const startNewPlan = () => { composing.current = true; setPlan(null); };
  const dates = useMemo(() => dateChips(), []);

  const load = useCallback(async () => {
    if (!me) return;
    try {
      const r: any = await agent.plans(me, otherPeer);
      const live = (r?.plans || []) as any[];
      const past = (r?.history || []) as any[];
      const withOther = (list: any[]) => list.filter((p: any) =>
        (p.participants || []).some((x: any) => (otherId && pidOf(x, 'name')
          ? pidOf(x, 'name') === otherId
          : String(x.name || '').trim().toLowerCase() === other.trim().toLowerCase())));
      // Живая встреча важнее прошлой, а из нескольких прошлых показываем свежайшую. Раньше брался
      // ПЕРВЫЙ совпавший план из склеенного списка: одна отменённая встреча месячной давности
      // закрывала собой сегодняшнюю договорённость.
      const newest = (list: any[]) =>
        list.slice().sort((a, b) => (b.updated || b.created || 0) - (a.updated || a.created || 0))[0];
      const mine = planId
        ? [...live, ...past].find((p: any) => p.id === planId)
        : (newest(withOther(live)) || newest(withOther(past)));
      // Пока человек сознательно составляет НОВУЮ встречу («Другое время» после отмены), фоновый
      // опрос не имеет права вернуть на экран старый план — иначе форма исчезает из-под рук.
      if (mine && !composing.current) setPlan(mine);
      // Пояс собеседника нужен и когда плана ещё нет — форма показывает выбранный час его глазами.
      if (typeof r?.peer_tz === 'string') setPeerTz(r.peer_tz);
    } catch {
      /* тихо: фоновая дотяжка */
    }
  }, [me, otherPeer, planId]);

  // Открытый по ссылке экран должен найти свой план сам — иначе «Открыть» из уведомления показывал
  // бы пустую форму поверх уже существующей встречи.
  useEffect(() => { if (planId || other) load(); }, [planId, other]);

  useEffect(() => {
    const id = setInterval(() => { setTick(Date.now()); load(); }, 15000);
    return () => clearInterval(id);
  }, [load]);

  /**
   * Режим этой встречи. У живого плана его знает сервер; у ещё не созданного — интент, по которому
   * совпали. Совсем без подсказок (старая ссылка на экран) — по наличию ссылки, как было раньше.
   */
  const mode: 'offline' | 'online' | 'hybrid' =
    (plan?.mode as any)
    || (modeFromIntent === 'online' || modeFromIntent === 'hybrid' || modeFromIntent === 'offline'
        ? (modeFromIntent as any)
        : (linkFromIntent ? 'online' : 'offline'));
  const wantsLink = mode === 'online' || mode === 'hybrid';
  const wantsPlace = mode === 'offline' || mode === 'hybrid';

  const phase = plan ? planPhase(plan, tick) : null;
  /**
   * ЗАМОК ЗА ДВА ЧАСА. Признак приходит с сервера фактом (`locked`), а не считается здесь: свой
   * счёт времени разошёлся бы с серверным на минуту, и в эту минуту кнопка снова обещала бы то,
   * на что придёт отказ. Сервер закрывает встречное время, ответ на него и правку ссылки —
   * значит и кнопок этих быть не должно.
   */
  const locked = !!(plan as any)?.locked;
  /**
   * ЧТО МОЖНО — ГОВОРИТ СЕРВЕР. `actions` считается той же таблицей, по которой ручки отказывают
   * (mplan_rules). Раньше экран выводил это сам из `locked`, `phase`, `pending` и «я подтвердил» —
   * второй правдой о тех же правилах; в заморозке он прятал «Подтвердить», хотя сервер и спека
   * его разрешают. `locked` остаётся только для подписей («не смогу» вместо «отменить», записка).
   */
  const planActs: string[] | null =
    Array.isArray((plan as any)?.actions) ? (plan as any).actions : null;
  // Ответ без `actions` (старый сервер, ответ из кеша) не должен означать «ничего нельзя»: тогда
  // экран гаснет целиком. Без списка ведём себя как до правки — по замку, а сервер объяснит сам.
  const offeredByServer = (a: string) => (planActs ? planActs.includes(a) : !locked);
  // Местное время собеседника — и только если оно расходится с моим. Раньше здесь безусловно
  // печаталось СВОЁ смещение «(GMT+2)»: сведений о чужом поясе не было нигде, поэтому строка
  // ничего не сообщала — человек и так знает, в каком он поясе.
  const peerTime = peerLocalTime(plan?.starts_at, plan?.their_tz || peerTz, ru);
  /** То же самое для ПРЕДЛОЖЕННОГО часа — см. O.21b у кнопок выбора. */
  const peerPendingTime = peerLocalTime(
    (plan?.pending as any)?.starts_at, plan?.their_tz || peerTz, ru
  );
  const mine = plan ? myAnswer(plan) : undefined;
  const bothAnswered = !!plan?.their_feedback && mine !== undefined;
  /**
   * ГДЕ БЫЛИ — прошедшим временем и по формату встречи. У звонка нет ни места, ни района, и
   * прежняя строка места молчала: человек видел карточку без единого слова о том, где всё было.
   */
  const pastWhere = () =>
    mode === 'online' ? PLAN.pastOnCall()
    : placeLabel ? PLAN.pastAtPlace(placeLabel)
    : mode === 'hybrid' ? PLAN.pastBothWays()
    : plan?.district ? PLAN.pastAtPlace(String(plan.district))
    : PLAN.pastPlaceNever();
  /** Подпись оценки по её числу: на сервере оценка — int 1–5, а на экране три слова. */
  const ratingLabel = () => {
    const n = Number(plan?.my_feedback?.rating || 0);
    const row = RATINGS.find(([, , v]) => v === n);
    return row ? row[1]() : '';
  };
  /** Подпись причины «не состоялась» по её ключу — тот же список, что в листе выбора. */
  const reasonLabel = () => {
    const k = String(plan?.my_feedback?.reason || '');
    return k === 'no_show' ? PLAN.reasonNoShow(other)
      : k === 'couldnt_make' ? PLAN.reasonCouldnt()
      : k === 'link_failed' ? PLAN.reasonLink()
      : k === 'place_closed' ? PLAN.reasonClosed()
      : k === 'moved' ? PLAN.reasonMoved()
      : k === 'other' ? PLAN.reasonOther()
      : '';
  };
  /** «Как встретились» у гибрида — сервер это хранит с самого начала, а показать было негде. */
  const howLabel = () => {
    const k = String(plan?.my_feedback?.how || '');
    return k === 'in_person' ? PLAN.howInPerson()
      : k === 'call' ? PLAN.howCall()
      : k === 'both' ? PLAN.howBoth() : '';
  };
  /** Запись показываем, когда она есть: ответ дан, и опрос уже позади. */
  const recorded = mine !== undefined && (mine === false || myRated(plan));
  /**
   * Кого ждём. Если я уже ответил — ждём только второго, и говорить надо это: «ждём обоих» после
   * собственного ответа читается как «твой ответ не записался».
   */
  const waitingLine = () =>
    mine !== undefined && !plan?.their_feedback ? PLAN.waitingThem(other) : PLAN.waitingBoth();
  /** O.21b: встречное время лежит РЯДОМ с планом (pending), сама встреча не тронута. */
  const pendingChange = plan?.pending || null;
  const cancelledByMe =
    !!plan?.cancelled_by && isMe(plan.cancelled_by, plan.cancelled_by_id, me);
  /**
   * РАУНДЫ (OF.20c / OF.C3d / OF.19c). После трёх раундов хозяин закрепляет одну из версий
   * (`can_fix` → `fix`), гость отвечает «остаюсь / выхожу» (`final_by_host` → `stay` / `leave`),
   * выход — `cancel_kind: left_final`, без последствий. Старый сервер этих полей не отдаёт —
   * тогда ни одна из веток ниже не включается.
   */
  const iHost = hostIsMe(plan, me);
  const finalOpen = !!plan?.final_by_host && phase === 'waiting';
  // Закреплённый план второй раз не закрепляют: сервер 06.10 ещё отдаёт can_fix после `fix`.
  const canFix = !!plan?.can_fix && !plan?.fixed && phase === 'waiting' && offeredByServer('fix');
  // Гость вышел — из закреплённого плана (left_final) или из любого офлайн-плана: OF.19c у хозяина.
  const leftFinal = guestLeft(plan, phase);
  // OF.C6: план отменил организатор — вид гостя.
  const hostOff = hostCancelled(plan, phase) && !iHost;
  /** Я организатор и сам отменил офлайн-план: затея снова открыта, как в OF.19c. */
  const iCancelled = hostCancelled(plan, phase) && iHost;
  /** Молчание закрыло план: хозяин выбирает другого, гость — своя затея. */
  const silentOff = silentClosed(plan, phase);
  const roundsLog: any[] = Array.isArray(plan?.rounds_log)
    ? [...plan.rounds_log].filter((r: any) => Number(r?.round) > 0).sort((a: any, b: any) => Number(b.round) - Number(a.round))
    : [];
  /** Единственный вызов отмены — из листа подтверждения (отмена на сервере необратима). */
  const confirmDrop = () => { setDropping(false); respond('decline'); };
  const openFix = () => { setFixRound(roundsLog[0] ? Number(roundsLog[0].round) : null); setFixing(true); };
  const doFix = async () => {
    if (fixRound == null) return;
    setFixing(false);
    await respond('fix', { round: fixRound });
  };
  /** OF.19e: кто уже сказал «да» на эту затею. Ошибка сервера — пустой список, а не выдуманные люди. */
  const openPicking = async () => {
    setPicking(true);
    setAlts(null);
    try {
      const r: any = await agent.planAlternatives(me, String(intentTitle || plan?.title || ''), otherRef);
      setAlts(Array.isArray(r?.people) ? r.people : []);
    } catch {
      setAlts([]);
    }
  };
  /**
   * ДВА ВХОДА СЧИТАЮТСЯ ПОРОЗНЬ.
   *
   * Раньше был один признак «адрес задан», и у гибрида он значил «задано хоть что-то одно»: экран
   * успокаивался, показав ссылку, и молчал о том, что места нет. Борд HY.20a/20b/20c — это три
   * РАЗНЫХ кадра ровно потому, что не хватать может каждого по отдельности.
   *
   * `?? ` — на случай, если телефон держит старый бандл против нового сервера или наоборот: без
   * новых полей считаем по-старому, а не показываем «места нет» там, где оно есть.
   */
  const placeSet = (plan as any)?.place_set ?? (wantsPlace && !!plan?.address_set);
  const linkSet = (plan as any)?.link_set ?? (wantsLink && !!plan?.address_set);
  const settling = phase === 'confirmed' || phase === 'soon' || phase === 'now';
  const needsWhere = !!plan && settling && ((wantsPlace && !placeSet) || (wantsLink && !linkSet));
  /** O.20a: согласованный план без ссылки — у звонка и у гибрида. */
  const needsLink = !!plan && settling && wantsLink && !linkSet;
  /** Офлайн-ветка борда. */
  const offline = mode === 'offline';
  /**
   * O.23c — «к звонку никто не подключился».
   *
   * Знание тут ровно одно: открывал ли кто-нибудь ссылку из приложения (см. кнопку «Открыть
   * ссылку»). Поэтому признак ТОЛЬКО у чистого звонка: у встречи вживую отметка «я на месте»
   * ставится руками, и её отсутствие не значит ничего, а у гибрида нетронутая ссылка совместима
   * с тем, что люди просто встретились.
   */
  const nobodyJoined =
    mode === 'online'                       // именно звонок: у гибрида могли просто встретиться
    && !!linkSet
    && (plan?.my_live as any)?.status !== 'here'
    && (plan?.their_live as any)?.status !== 'here';
  /** OF.20a/HY.20b: согласовано, а точного места нет — у встречи вживую и у гибрида. */
  const needsPlace = !!plan && settling && wantsPlace && !placeSet;
  /**
   * КТО КОГО ПОПРОСИЛ — С СЕРВЕРА. Флаг «уже попросил(а)» жил здесь в useState: сбрасывался при
   * каждом открытии экрана (и просьбу слали снова), не различал место и ссылку (одна кнопка гасила
   * обе) и второму не показывался вовсе — тот видел то же поле с теми же двумя кнопками и мог
   * попросить в ответ. Теперь просьба — факт плана (`place_asked_by` / `link_asked_by`).
   */
  const norm = (x: any) => String(x || '').trim().toLowerCase();
  const placeAskedBy = norm((plan as any)?.place_asked_by);
  const linkAskedBy = norm((plan as any)?.link_asked_by);
  // «Попросил я» — по id просившего (`*_asked_by_id`), подпись только без него.
  const placeAskedMine = !!placeAskedBy && isMe(placeAskedBy, (plan as any)?.place_asked_by_id, me);
  const linkAskedMine = !!linkAskedBy && isMe(linkAskedBy, (plan as any)?.link_asked_by_id, me);
  const askedThemPlace = placeAskedMine;
  const askedMePlace = !!placeAskedBy && !placeAskedMine;
  const askedThemLink = linkAskedMine;
  const askedMeLink = !!linkAskedBy && !linkAskedMine;
  /** Внутри замка сервер не принимает ни место, ни ссылку — поля не рисуем, а говорим почему. */
  const whereLocked = !offeredByServer('address') && (needsPlace || needsLink);
  /** O.21e / O.C3e / O.22d: звонок согласован, а ссылки нет. Добавляет организатор — или тот, кого попросили. */
  const linkGap = mode === 'online' && !!plan && !linkSet && !pendingChange
    && (phase === 'confirmed' || phase === 'soon' || phase === 'now');
  const linkOnMe = askedMeLink || (!askedThemLink && hostIsMe(plan, me));
  /** HY.21e / 21f / 21g: у гибрида не хватать может каждого входа по отдельности. */
  const hyGap = mode === 'hybrid' && !!plan && (!linkSet || !placeSet) && !pendingChange
    && (phase === 'confirmed' || phase === 'soon' || phase === 'now');
  const placeOnMe = askedMePlace || (!askedThemPlace && hostIsMe(plan, me));
  const myNeedLink = hyGap && !linkSet && linkOnMe;
  const myNeedPlace = hyGap && !placeSet && placeOnMe;
  /** Свои заголовки только там, где старые говорят не то: просьба провести (O.C3e) и «всё ещё нет» перед началом (O.22d). */
  const gapTitle = !linkGap ? '' : askedMeLink ? ONB.asksHostTitle(other)
    : !linkOnMe ? ONB.waitLinkTitle()
    : phase === 'soon' ? ONB.missingTitle() : '';
  const gapNote = !linkGap ? '' : askedMeLink ? ONB.asksHostNote(other)
    : !linkOnMe ? ONB.waitLinkNote(other)
    : phase === 'soon' ? ONB.missingNote(other, minutesToStart(plan)) : '';
  /**
   * HY.22 — сторона встречи. Есть только у гибрида: у звонка приходить некуда, у встречи вживую
   * уходить некуда. По умолчанию человек считается идущим живьём — так стоит на кадре HY.21,
   * где оба «Confirmed · in person», пока никто ничего не менял.
   */
  const hybrid = mode === 'hybrid';
  /** HY.23c: оба уже переведены в звонок — кнопку больше не предлагаем. */
  const movedToCall = !!(plan as any)?.moved_to_call;
  const mySide = String((plan as any)?.my_side || (hybrid ? 'in_person' : ''));
  const theirSide = String((plan as any)?.their_side || (hybrid ? 'in_person' : ''));
  /**
   * Иду ли я живьём. У встречи вживую — всегда; у гибрида — пока не ушёл в звонок; у звонка —
   * никогда. От этого зависят «опаздываю» и «я на месте»: они про дорогу к месту.
   */
  const comingInPerson = wantsPlace && mySide !== 'call';
  const theirComingInPerson = wantsPlace && theirSide !== 'call';
  /** OF.22/OF.22a/OF.23: живые статусы — «в пути», «опаздываю», «на месте». */
  const myLive = String(plan?.my_live?.status || '');
  const theirLive = String(plan?.their_live?.status || '');
  /*
    ДЕНЬ ВСТРЕЧИ ОДИН НА ОДИН — СВОЙ ЭКРАН (борд «1:1 · Offline — new layout», раздел D, OF.22–OF.23d):
    карточка адреса с маршрутом вместо обложки, двое со статусами и метками, кнопки по кадру.
    «Не смогу» в 1:1 — это «встречи не будет» (OF.23b/23d/C9): сервер держит это живым статусом,
    экран говорит об этом как об отмене, в том числе после часа встречи — спрашивать «состоялась
    ли» там не о чем.
  */
  const iCant = myLive === 'cant_make_it';
  const theyCant = theirLive === 'cant_make_it';
  /*
    ЗВОНОК ОДИН НА ОДИН — ТОТ ЖЕ ЭКРАН ДНЯ (борд «1:1 · Online — new layout», раздел D, O.22–O.23d):
    вместо адреса карточка со ссылкой и «Open link». Без ссылки новый вид не включается — там ещё
    идёт разговор «добавь ссылку» (O.22d), он живёт в старой ветке. Гибрид остаётся как был.
  */
  const onlineCall = mode === 'online';
  /** Новый вид плана (раунды, фиксация, правка) — у всех трёх форматов: вживую, звонок, гибрид. */
  const nl = offline || onlineCall || hybrid;
  /** Карточка говорит о месте как у встречи вживую — и у гибрида тоже (HY.20: адрес и ссылка двумя строками). */
  const placeLike = offline || hybrid;
  const callLink = String((plan as any)?.link ?? (onlineCall ? plan?.address : '') ?? '');
  const svc = callService(callLink);
  /** Чья ссылка. Сервер автора ссылки не отдаёт (`link_by` наружу не идёт) — считаем, что организатора. */
  const linkBy = String((plan as any)?.link_by || '');
  // Сервер отдаёт автора ссылки с 11.10 (`link_by`); у старых планов его нет — тогда считаем, что организатора.
  const linkMine = linkBy ? isMe(linkBy, (plan as any)?.link_by_id, me) : hostIsMe(plan, me);
  /*
    ГИБРИД В ДЕНЬ ВСТРЕЧИ (борд «1:1 · Hybrid — new layout», раздел D, HY.22–HY.23d): карточка с двумя
    входами — место и ссылка, — сторона у каждого своя и меняется без отмены. Новый вид включается,
    когда названы оба входа; пока не хватает одного, экран просит его (HY.21e–21g).
  */
  const soloDay = offline || (onlineCall && !!(plan as any)?.link_set) || (hybrid && !!placeSet && !!linkSet);
  const dayOff = soloDay && (iCant || theyCant) && (phase === 'soon' || phase === 'now' || phase === 'after');
  const dayView = soloDay && (phase === 'soon' || phase === 'now' || dayOff);
  const bothHere = myLive === 'here' && theirLive === 'here';
  /** O.23c: звонок идёт, ссылка была открыта 15 минут, никто не вошёл. Пометка сервера, план не меняется. */
  const nobody = onlineCall && phase === 'now' && !dayOff && !!(plan as any)?.nobody_joined;
  // После «Move to the call» (HY.23c) место уже не тема: оба в звонке, и экран говорит об этом.
  const closedNow = dayView && !dayOff && spotClosed && bothHere && !movedToCall;
  const hyDay = hybrid && dayView;
  /** Я в звонке: сам сменил сторону или обоих перевели после закрытого места (HY.23c). */
  const iOnCall = hybrid && (mySide === 'call' || movedToCall);
  const theyOnCall = hybrid && (theirSide === 'call' || movedToCall);
  const opensAt = linkOpensAt(plan, ru);
  /** Ссылка открывается за десять минут до начала — а «на носу» гибрид уже за полчаса. */
  const linkOpen = !!plan && minutesToStart(plan) <= LINK_LEAD_MIN;
  /** Короткое имя места для текстов: «at Pg. del Born or on the call». */
  const placeShort = String(plan?.venue || plan?.district || (plan as any)?.place || '').trim()
    || T('месте', 'the place', 'el lugar');
  const theirEta = Number((plan as any)?.their_live?.eta_min || 0);
  /** Пол собеседника из плана (сервер отдаёт `participants[].gender` с 10.10) — для «she / he» в текстах. */
  const otherG = String(((plan?.participants || []) as any[]).find((x) => !x?.is_me)?.gender || '');
  const dayTitle = !dayView ? ''
    : hyDay && !iCant && !theyCant ? (
        closedNow ? HYB.closedTitle()
        : movedToCall ? PLAN.sideBothCallTitle()
        : myLive === 'late' ? PLAN.lateKnows(other) : theirLive === 'late' ? PLAN.theyLate(other)
        : phase === 'now' ? PLAN.meetupNow()
        : iOnCall && theyOnCall ? PLAN.sideBothCallTitle()
        : iOnCall ? HYB.youCallTitle() : theyOnCall ? HYB.theyCallTitle(other)
        : PLAN.startsIn(minutesToStart(plan)))
    : iCant ? (onlineCall ? OND.youCantTitle(other) : OFD.youCantTitle(other))
    : theyCant ? (onlineCall ? OND.theyCantTitle(other) : OFD.theyCantTitle(other))
    : closedNow ? OFD.spotClosedTitle()
    : nobody ? OND.nobodyTitle()
    : myLive === 'late' ? PLAN.lateKnows(other) : theirLive === 'late' ? PLAN.theyLate(other)
    : phase === 'now' ? (onlineCall ? OND.nowTitle() : PLAN.meetupNow()) : PLAN.startsIn(minutesToStart(plan));
  const dayNote = !dayView ? ''
    : hyDay && !iCant && !theyCant ? (
        closedNow ? HYB.closedNote()
        : movedToCall ? HYB.movedNote()
        : myLive === 'late' ? HYB.lateToldNote(otherG) : theirLive === 'late' ? HYB.theyLateNote(theirEta, otherG)
        : phase === 'now' ? HYB.nowNote(placeShort, other, otherG)
        : iOnCall && theyOnCall ? HYB.bothCallNote(opensAt)
        : iOnCall ? HYB.youCallNote(other, opensAt, otherG) : theyOnCall ? HYB.theyCallNote(placeShort, opensAt, otherG)
        : HYB.soonNote(opensAt))
    : iCant ? (onlineCall ? OND.youCantNote() : OFD.youCantNote())
    : theyCant ? (onlineCall
        ? (hostIsMe(plan, me) ? OND.theyCantNoteHost(otherG) : OND.theyCantNoteGuest(otherG))
        : (hostIsMe(plan, me) ? OFD.theyCantNoteHost(otherG) : OFD.theyCantNoteGuest(otherG)))
    : closedNow ? OFD.spotClosedNote()
    : nobody ? OND.nobodyNote()
    : myLive === 'late' ? OFD.lateToldNote(otherG)
    : theirLive === 'late' ? (onlineCall ? OND.theyLateNote(theirEta) : OFD.theyLateNote(theirEta))
    : phase === 'now' ? OFD.nowNote(other, otherG)
    : onlineCall ? OND.soonNote(linkMine, other, svc) : OFD.lateHint(other, otherG);
  /** «Состоялась ли» спрашиваем, только если встреча не была отменена словом «не смогу». */
  const asking = phase === 'after' && !dayOff;
  /*
    ПОСЛЕ ВСТРЕЧИ ОДИН НА ОДИН (раздел E, OF.24–OF.24c, OF.C10): вопрос голубой плашкой, карточка
    адреса «когда это было», счётчик «Answered N of 2», у каждого только факт ответа. Чужой ответ
    не виден никому — сервер отдаёт о втором одно «ответил».
  */
  /** O.24–O.24c: у звонка «после» тот же вид; карточка — «Video call · Zoom», вопрос — про звонок. */
  const afterOff = nl && asking;
  const afterNew = afterOff && mine === undefined;
  const bothNo = afterOff && bothAnswered && plan?.outcome?.happened === false;
  const afterTitle = bothNo ? OFD.bothNoTitle() : OFD.savedTitle();
  const afterNote = bothNo ? (hostIsMe(plan, me) ? (onlineCall ? OND.bothNoNoteHost() : OFD.bothNoNoteHost()) : OFD.bothNoNote())
    : bothAnswered ? OFD.bothDoneNote() : OFD.savedNote(other, otherG);
  /** Человеческое имя места: «Nømad · Carrer de Verdi 12». Видно только подтвердившим (OF.C3). */
  const placeLabel = wantsPlace
    ? [plan?.venue, (plan as any)?.place ?? (offline ? plan?.address : '')].filter(Boolean).join(' · ')
    : '';

  /** Место уже стоит зелёной плашкой: встреча на носу и адрес открыт. */
  const placeReady = wantsPlace && !dayView && (phase === 'soon' || phase === 'now') && !!placeLabel
    // После HY.23c звать «Открыть маршрут» значит отправить человека к запертой двери, из-за
    // которой все и ушли в звонок. Карточка места уходит вместе с этим решением.
    && !movedToCall;
  /**
   * Договорились обо всём — зелёная плашка «Всё готово» ниже. Она называет и время, и место, и
   * час открытия ссылки, поэтому строки выше про то же самое не рисуются: одна новость, одно место
   * на экране. Раньше адрес стоял дважды, а про ссылку было сказано трижды.
   */
  const allSet = phase === 'confirmed' && !plan?.pending
    && (!wantsPlace || placeSet) && (!wantsLink || linkSet);

  /** OF.22 «Открыть маршрут» — обычная карта по адресу; своей навигации у Kleal нет. */
  /** O.22 «Open link». Открыть ссылку = выйти на связь: отметка «на месте» уходит фоном, как раньше. */
  const openCall = () => {
    if (!plan?.id || !callLink) return;
    agent.planStatus(plan.id, me, 'here').then((r: any) => { if (r?.plan) setPlan(r.plan); }).catch(() => {});
    Linking.openURL(withScheme(callLink)).catch(() => setErr(CHAT.planFailed()));
  };
  const openRoute = () => {
    const q = placeLabel || String(plan?.district || '');
    if (!q) return;
    Linking.openURL('https://maps.google.com/?q=' + encodeURIComponent(q)).catch(() => setErr(CHAT.planFailed()));
  };

  const propose = async () => {
    if (busy || !me || !other) return;
    setBusy(true);
    setErr('');
    try {
      const d = dayStart(date);
      d.setMinutes(minutes);
      const r: any = await agent.planPropose(me, otherPeer, {
        title: intentTitle || T('Встреча', 'Meetup', 'Quedada'),
        // Режим — из интента, а не «есть ли ссылка в поле». См. modeFromIntent выше.
        mode,
        starts_at: Math.floor(d.getTime() / 1000),
        when: planWhenLabel(date, minutes, ru),
        district: wantsPlace ? district : '',
        // ДВА ВХОДА, А НЕ ОДИН. Раньше здесь стояло «ссылка, а если её нет — место», и у
        // гибрида набранное в форме место просто не уезжало на сервер: человек его вводил, видел,
        // как оно исчезает, и приходить было некуда. Теперь каждый вход едет в своё поле, а
        // сервер и экран показывают их порознь (HY.20a/20b/20c).
        address: wantsPlace ? address.trim() : '',
        link: wantsLink ? link.trim() : '',
      });
      if (!r?.ok) {
        if (r?.error === 'NOT_MATCHED') throw new Error(CHAT.notMatched());
        if (r?.error === 'IN_THE_PAST') throw new Error(CHAT.inThePast());
        if (r?.error === 'PLAN_EXISTS') throw new Error(CHAT.planExists());
        throw new Error(CHAT.planFailed());
      }
      // Сервер вернул план целиком — берём его сразу, не дожидаясь опроса.
      composing.current = false;                 // новая встреча создана — опросу снова можно всё
      if (r.plan) setPlan(r.plan); else await load();
    } catch (e: any) {
      setErr(String(e?.message || CHAT.planFailed()));
    } finally {
      setBusy(false);
    }
  };

  const respond = async (action: string, extra: any = {}) => {
    if (!plan?.id) return;
    setErr('');
    try {
      const r: any = await agent.planRespond(plan.id, me, action, { version: plan.version, ...extra });
      if (!r?.ok) {
        if (r?.error === 'IN_THE_PAST') throw new Error(CHAT.inThePast());
        // Ответили на устаревшую версию (второй успел принять перенос): перечитать и сказать,
        // что случилось, — а не «не удалось» поверх экрана, который врёт на 15 секунд опроса.
        if (r?.error === 'VERSION_CONFLICT') { await load(); throw new Error(PLAN.changedMeanwhile()); }
        throw new Error(r?.error || 'failed');
      }
      await load();
    } catch (e: any) {
      const m = String(e?.message || '');
      setErr(m === CHAT.inThePast() || m === PLAN.changedMeanwhile() ? m : CHAT.planFailed());
    }
  };

  /**
   * OF.21a/O.21b: встречное время из листа — быстрый сдвиг или своё «чч:мм» в тот же день.
   * Сервер паркует его рядом с планом; старое время держится до ответа.
   */
  const sendCounter = async () => {
    if (!plan?.starts_at) return;
    // O.21a «Change the link» / O.C3a «Host the call myself»: в поле листа у звонка — новая ссылка.
    // Она сохраняется сразу; время уходит встречным, только если его тронули.
    if (mode === 'online' && sugPlaceOpen) {
      const v = sugPlace.trim();
      if (!looksLikeUrl(v)) { setErr(CHAT.planFailed()); return; }
      try {
        const r: any = await agent.planAddress(plan.id, me, '', undefined, withScheme(v));
        if (!r?.ok) throw new Error(r?.error || 'failed');
      } catch { setErr(CHAT.planFailed()); return; }
      if (sugDay === 0 && sugDelta === 60 && !sugH.trim() && !sugM.trim() && !timeTouched.current) {
        setCountering(false); setSugPlaceOpen(false); await load(); return;
      }
    }
    let ts: number;
    // День из ряда дней (OF.C3a) — сдвиг от дня плана; время — сдвиг из ряда или своё «чч:мм».
    const dayShift = (nl ? sugDay : 0) * 86400;
    if (sugDelta != null) {
      ts = Math.floor(plan.starts_at + dayShift + sugDelta * 60);
    } else {
      // Пустые поля — это «человек начал набирать и передумал», а не «полночь»: раньше
      // незаполненные часы давали 00:00, и сервер честно отвечал «время уже прошло».
      if (!sugH.trim() && !sugM.trim()) { setErr(CHAT.inThePast()); return; }
      // Зажимаем и здесь — на случай отправки без ухода из поля (клавиатура закрыта кнопкой).
      // Поле к этому моменту уже нормализовано, так что зажим ничего не меняет; он остаётся
      // последней защитой, а не тихой правкой за спиной.
      const h = Math.max(0, Math.min(23, parseInt(sugH || '0', 10) || 0));
      const m = Math.max(0, Math.min(59, parseInt(sugM || '0', 10) || 0));
      const d = new Date((plan.starts_at + dayShift) * 1000);
      d.setHours(h, m, 0, 0);
      // Названный час уже прошёл — человек имеет в виду завтра, а не вчера. Сервер отказал бы.
      if (d.getTime() <= Date.now()) d.setDate(d.getDate() + 1);
      ts = Math.floor(d.getTime() / 1000);
    }
    // Подпись — от НОВОГО момента целиком. Раньше бралась дата текущего плана плюс новый час: если
    // названный час уже прошёл и время ушло на завтра, подпись показывала вчерашнюю дату с
    // завтрашним часом.
    const district = mode !== 'online' && sugPlaceOpen && sugPlace.trim() ? { district: sugPlace.trim() } : {};
    await respond('counter', { starts_at: ts, when: planWhen({ starts_at: ts }, ru), ...district });
    timeTouched.current = false;
    setCountering(false);
    setSugPlaceOpen(false);
  };

  /** OF.20a: донести точное место в согласованный план — сервер отдаст его обоим по OF.C3. */
  const savePlace = async () => {
    const v = placeDraft.trim();
    if (!plan?.id || !v) return;
    setErr('');
    try {
      const r: any = await agent.planAddress(plan.id, me, v);
      if (!r?.ok) throw new Error(r?.error || 'failed');
      setPlaceDraft('');
      await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /** OF.20a: «пусть выберет он(а)» — просьба записывается в план (и строкой в ленту) для обоих. */
  const askPlace = async () => {
    if (!plan?.id || askedThemPlace) return;
    setErr('');
    try {
      const r: any = await agent.planAsk(plan.id, me, 'place');
      if (!r?.ok) throw new Error(r?.error || 'failed');
      if (r.plan) setPlan(r.plan); else await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /**
   * HY.22 — сменить сторону встречи. Обратимо, и это не отмена: встреча остаётся, меняется вход.
   *
   * Отказы сервера называются словами, а не «не получилось»: «уйти в звонок» при отсутствующей
   * ссылке — не сбой связи, а недостающая половина плана, и человеку надо сказать именно это.
   */
  /** HY.C3: «I’ll come in person» / «I’ll join the call» — подтвердить план и сразу назвать сторону. */
  const confirmSide = async (side: 'in_person' | 'call') => {
    if (!plan?.id) return;
    setErr('');
    try {
      const r: any = await agent.planRespond(plan.id, me, 'confirm', { version: plan.version });
      if (!r?.ok) {
        if (r?.error === 'VERSION_CONFLICT') { await load(); throw new Error(PLAN.changedMeanwhile()); }
        throw new Error(CHAT.planFailed());
      }
      // Сторона — отдельным вызовом: подтверждение уже записано, и его неудача стороны не отменяет.
      const sd: any = await agent.planSide(plan.id, me, side).catch(() => null);
      if (sd?.plan) setPlan(sd.plan); else await load();
    } catch (e: any) {
      setErr(String(e?.message || CHAT.planFailed()));
    }
  };

  const sendSide = async (side: 'in_person' | 'call') => {
    if (!plan?.id) return;
    setErr('');
    try {
      const r: any = await agent.planSide(plan.id, me, side);
      if (!r?.ok) {
        if (r?.error === 'NO_LINK') throw new Error(PLAN.sideNoLink());
        if (r?.error === 'NO_PLACE') throw new Error(PLAN.sideNoPlace());
        throw new Error(CHAT.planFailed());
      }
      if (r.plan) setPlan(r.plan); else await load();
    } catch (e: any) {
      setErr(String(e?.message || CHAT.planFailed()));
    }
  };

  /** HY.23c: место закрыто — переводим ОБОИХ в звонок. Не отмена: встреча остаётся. */
  const moveToCall = async () => {
    if (!plan?.id) return;
    setErr('');
    try {
      const r: any = await agent.planMoveToCall(plan.id, me);
      if (!r?.ok) {
        if (r?.error === 'NO_LINK') throw new Error(PLAN.sideNoLink());
        throw new Error(CHAT.planFailed());
      }
      if (r.plan) setPlan(r.plan); else await load();
    } catch (e: any) {
      setErr(String(e?.message || CHAT.planFailed()));
    }
  };

  /** OF.22/OF.22a/OF.23: «уже иду» / «опаздываю» / «на месте». Видит только собеседник. */
  const sendLive = async (status: 'otw' | 'late' | 'here', etaMin?: number) => {
    if (!plan?.id) return;
    setErr('');
    try {
      const r: any = await agent.planStatus(plan.id, me, status, etaMin);
      if (!r?.ok) throw new Error(r?.error || 'failed');
      if (r.plan) setPlan(r.plan); else await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /** O.20a: донести ссылку в согласованный план. Сервер отдаст её обоим по правилу OF.C3. */
  const saveLink = async () => {
    const v = linkDraft.trim();
    if (!plan?.id || !looksLikeUrl(v)) return;
    setErr('');
    try {
      // Пустой адрес и ссылка отдельным полем: у гибрида место уже названо, и слать ссылку
      // в поле адреса значило бы затереть его.
      const r: any = await agent.planAddress(plan.id, me, '', undefined, v);
      if (!r?.ok) throw new Error(r?.error || 'failed');
      setLinkDraft('');
      await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /** O.20a: «пусть хостит он(а)» — та же просьба, про ссылку. */
  const askHost = async () => {
    if (!plan?.id || askedThemLink) return;
    setErr('');
    try {
      const r: any = await agent.planAsk(plan.id, me, 'link');
      if (!r?.ok) throw new Error(r?.error || 'failed');
      if (r.plan) setPlan(r.plan); else await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /** O.C3e «I can’t host»: снять просьбу провести звонок. */
  const declineHost = async () => {
    if (!plan?.id) return;
    setErr('');
    try {
      const r: any = await agent.planAsk(plan.id, me, 'link', undefined, true);
      if (!r?.ok && r?.error !== 'NO_ASK') throw new Error(r?.error || 'failed');
      // «Ask … to host» встаёт ровно на место «I can’t host»: второе касание двойного тапа тут же
      // просило бы в ответ (стенд, 11.10). Секунду после отказа кнопка не нажимается.
      setAskCool(true);
      setTimeout(() => setAskCool(false), 1200);
      if (r.plan) setPlan(r.plan); else await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  const answerHappened = async (happened: boolean) => {
    if (!plan?.id) return;
    // OF.24a: «нет» сперва спрашивает, что случилось, — и только лист отправляет ответ.
    if (!happened) {
      setReasonPick('');
      setReasonOpen(true);
      return;
    }
    try {
      await agent.planFeedback(plan.id, me, { happened });
      await load();
      // OF.25: «да» записано сразу — лист оценки необязателен, и закрыть его значит пропустить.
      setRating(''); setHowMet(''); setRateOpen(true);
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /** OF.24a: «не состоялась» с причиной (или без — «Пропустить»). Причину другим не показывают. */
  const sendDidnt = async (withReason: boolean) => {
    if (!plan?.id) return;
    try {
      await agent.planFeedback(plan.id, me, {
        happened: false,
        ...(withReason && reasonPick ? { reason: reasonPick } : {}),
      });
      setReasonOpen(false);
      await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /** OF.26: жалоба после встречи — тот же экран, что у группы, с одним человеком. */
  const openReport = () => {
    const row: any = (plan?.participants || []).find((x: any) => !x?.is_me) || {};
    router.navigate({ pathname: '/group-report', params: {
      who: other, who_id: otherId, photo: String(row.photo || photo || ''), age: row.age ? String(row.age) : '',
      call: mode === 'online' ? '1' : mode === 'hybrid' ? 'hy' : '',
    } });
  };

  const sendRating = async () => {
    if (!plan?.id) return;
    try {
      const value = RATINGS.find(([k]) => k === rating)?.[2];
      // HY.25: «как встретились» уезжает тем же вызовом, что и оценка, — сервер дописывает в ту же
      // строку отзыва, а не заводит вторую. Пусто, если человек не выбрал: это необязательный
      // вопрос, и молчание тут значит «не сказал», а не «никак».
      await agent.planFeedback(plan.id, me, howMet ? { rating: value, how: howMet } : { rating: value });
      setThanks(PLAN.thanks());
      await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /*
    ЧАТ И ПЛАН — СОСЕДИ, А НЕ ЭТАЖИ. Отсюда `dismissTo`, а не `navigate`: если чат уже открыт
    ниже (а чаще всего так и есть — план открывают из чата), возвращаемся к нему и снимаем план
    сверху; если чата в стопке нет, он встаёт НА МЕСТО плана. В обоих случаях «назад» из чата
    ведёт туда, откуда человек пришёл, а не обратно в план, из которого он только что вышел.
  */
  const openChat = async () => {
    if (chatRequest.current || !chatContext.current) return;
    chatRequest.current = true;
    const context = chatContext.current;
    setOpeningChat(true);
    setChatError('');
    try {
      const target = await preparePlanChat(plan, me, agent.thread);
      if (context === chatContext.current) router.dismissTo(target);
    } catch {
      if (context === chatContext.current) setChatError(planChatCopy(getLang()).unavailable);
    } finally {
      chatRequest.current = false;
      if (chatContext.current) setOpeningChat(false);
    }
  };

  /** Ссылка, как её отдал сервер: до подтверждения её просто нет в ответе. */
  const serverLink = String((plan as any)?.link ?? (mode === 'online' ? plan?.address : '') ?? '');
  const linkReady = phase === 'soon' || phase === 'now';

  /**
   * Полоса под карточкой (OF.20 / OF.21b). Раунды — если сервер их отдаёт (`round`, `max_rounds`,
   * `round_ends_at`); перенос — «Accepted 0 of 1» с его сроком (`pending.expires_at`). Сроков сервер
   * не прислал — правой ячейки нет: часы не выдумываем.
   */
  const endsIn = (at: any) => {
    const sec = Number(at || 0) - Date.now() / 1000;
    if (!(sec > 0)) return '';
    const m = Math.round(sec / 60), h = Math.floor(m / 60), mm = m % 60;
    const span = h ? (mm ? `${h}${T('ч', 'h', 'h')} ${mm}${T('м', 'm', 'm')}` : `${h}${T('ч', 'h', 'h')}`) : `${mm}${T('м', 'm', 'm')}`;
    return T(`Осталось ${span}`, `Ends in ${span}`, `Termina en ${span}`);
  };
  const meter: null | { label: string; now: number; sep: string; of: number; right: string; segments: boolean[] } =
    plan && afterNew ? { label: OFD.answered(), now: plan.their_feedback ? 1 : 0, sep: ` ${T('из', 'of', 'de')} `, of: 2,
                         // OF.24 / O.24: «Reply by Sun 20:00» — срок показа с сервера, сам он ничего не засчитывает.
                         right: (plan as any).feedback_expires_at ? OND.replyBy(replyWhen(Number((plan as any).feedback_expires_at), ru)) : '',
                         segments: [!!plan.their_feedback, false] }
    : !plan || phase === 'cancelled' || phase === 'after' ? null
    : pendingChange && phase === 'confirmed' ? { label: T('Принято', 'Accepted', 'Aceptado'), now: 0, sep: ` ${T('из', 'of', 'de')} `, of: 1,
                        right: endsIn((pendingChange as any).expires_at), segments: [false] }
    : phase === 'waiting' && Number((plan as any).max_rounds) > 0 ? (() => {
        const r = Math.max(1, Number((plan as any).round) || 1), mx = Number((plan as any).max_rounds);
        return { label: T('Раунд', 'Round', 'Ronda'), now: r, sep: ' / ', of: mx,
                 right: endsIn((plan as any).round_ends_at), segments: Array.from({ length: mx }, (_, i) => i < r) };
      })()
    : null;

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/*
          ШАПКА И ФОН ПО ДОСКЕ «1:1 · Offline — new layout» (разделы B/C, 6873:146474 / 146885): ровная
          подложка #F5F1EC без пятен, стеклянная «назад» 44 и название затеи слева гарнитурой шапок 20/24 —
          та же раскладка, что у страниц группы (app/grole.tsx), потому что на досках это один экран.
        */}
        <View style={s.head}>
          <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={() => (picking ? setPicking(false) : router.canGoBack() ? router.back() : router.replace('/home'))} />
          <Text style={[s.headTitle, heading(lang, type.headingSm)]} numberOfLines={1}>{intentTitle || plan?.title || T('Встреча', 'Meetup', 'Quedada')}</Text>
        </View>

        <ScrollView onScroll={navCollapse} scrollEventThrottle={16} contentContainerStyle={[s.body, { paddingBottom: 130 }]} keyboardShouldPersistTaps="handled" scrollEnabled={!dragging}>
          {!plan ? (
            <PlanForm
              dates={dates} date={date} setDate={setDate}
              minutes={minutes} setMinutes={setMinutes} setDragging={setDragging}
              district={district} setDistrict={setDistrict}
              address={address} setAddress={setAddress}
              link={link} setLink={setLink}
              wantsLink={wantsLink} wantsPlace={wantsPlace} other={other} otherTz={peerTz} ru={ru}
              busy={busy} err={err} onPropose={propose}
            />
          ) : picking ? (
            /* OF.19e «Pick someone else»: кто уже принял приглашение на эту затею — «Pick» сразу в чат;
               новых людей Kleal показывает в выдаче затеи (там «Invite»). Список — только с сервера. */
            <>
              <Text style={[s.title, { fontFamily: labelFamily(lang) }]}>{OFB.pickElse()}</Text>
              {alts == null ? <ActivityIndicator color={color.primary} style={{ marginTop: 24 }} /> : (
                <>
                  <Text style={s.note}>{OFB.pickNote(alts.filter((a: any) => a?.free).map((a: any) => String(a.name || '')).filter(Boolean))}</Text>
                  {alts.map((a: any, i: number) => {
                    const nm = String(a?.name || '');
                    // Интересы: список строк; анкета хранит их как {explicit: [...]} — читаем оба вида.
                    const ints: string[] = (Array.isArray(a?.interests) ? a.interests
                      : Array.isArray(a?.interests?.explicit) ? a.interests.explicit : [])
                      .map((x: any) => String(x?.label || x || '')).filter((x: string) => x && x !== 'explicit').slice(0, 6);
                    return (
                      <View key={nm + i} style={s.cardShadow}>
                        <GlassSurface tone="light" radius={20} style={s.altCard}>
                          <View style={s.altHead}>
                            {a.photo ? <Image source={{ uri: mediaUrl(String(a.photo)) }} style={s.altAva} />
                              : <View style={[s.altAva, s.personAvaEmpty]}><IconPerson size={26} /></View>}
                            <View style={{ flex: 1, gap: 4 }}>
                              <Text style={[s.altName, { fontFamily: labelFamily(lang) }]} numberOfLines={1}>{nm}{a.age ? `, ${a.age}` : ''}</Text>
                              {a.area ? (
                                <View style={s.metaRow}>
                                  <IconPin size={16} c={color.primary} />
                                  <Text style={s.metaText} numberOfLines={1}>{String(a.area)}</Text>
                                </View>
                              ) : null}
                            </View>
                          </View>
                          {/* Интересы — те же чипы со значками, что в выдаче (сервер ≥ 06.10: до 6 строк). */}
                          {ints.length ? (
                            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                              {ints.map((x: string) => (
                                <View key={x} style={s.altChip}><Text style={s.altChipText}>{`${interestEmoji(x)} ${x.charAt(0).toUpperCase() + x.slice(1)}`.trim()}</Text></View>
                              ))}
                            </ScrollView>
                          ) : null}
                          <View style={s.altBox}>
                            <View style={s.altBoxHead}>
                              <View style={s.metaRow}>
                                <IconCalendarCheck size={18} c="#0F7340" />
                                <Text style={[s.altSaid, { fontFamily: labelFamily(lang) }]}>{OFB.saidYes()}</Text>
                              </View>
                              {a.at ? <Text style={s.altWhen}>{dOf(a.at)}</Text> : null}
                            </View>
                            <Text style={s.metaText}>{a.free ? OFB.stillFree(nm) : OFB.busyNow(nm)}</Text>
                          </View>
                          {a.free ? (
                            <Pressable accessibilityRole="button" style={s.cta}
                              onPress={() => router.navigate({ pathname: '/conversation', params: { who: nm, who_id: String(a.name_id || a.id || ''), title: String(intentTitle || plan?.title || '') } })}>
                              <Text style={s.ctaText}>{OFB.pickName(nm)}</Text>
                            </Pressable>
                          ) : null}
                        </GlassSurface>
                      </View>
                    );
                  })}
                  <Pressable accessibilityRole="button" style={alts.some((a: any) => a?.free) ? s.ctaSoft : s.cta} onPress={() => openResults(router)}>
                    <Text style={alts.some((a: any) => a?.free) ? s.ctaSoftText : s.ctaText}>{OFB.seeOthers()}</Text>
                  </Pressable>
                </>
              )}
            </>
          ) : (
            <>
              {afterNew ? (
                /* OF.24: вопрос стоит голубой плашкой вместо заголовка. */
                <View style={s.infoBox}>
                  <Text style={[s.infoText, s.infoTitle]}>{onlineCall ? OND.didHappen() : OFD.didYouMeet()}</Text>
                  <Text style={s.infoText}>{onlineCall ? OND.didNote(other, svc) : hybrid ? HYB.didNote(other) : OFD.didYouMeetNote(other)}</Text>
                </View>
              ) : (
                <Text style={[s.title, { fontFamily: labelFamily(lang) }]}>
                  {dayView ? dayTitle : afterOff ? afterTitle : gapTitle || headline(phase!, other, plan, me, ru)}
                </Text>
              )}
              {chatError ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={s.err}>{chatError}</Text> : null}
              {afterNew ? null : (dayView ? dayNote : afterOff ? afterNote : gapNote || subline(phase!, other, plan, ru, me)) ? (
                <Text style={s.note}>{dayView ? dayNote : afterOff ? afterNote : gapNote || subline(phase!, other, plan, ru, me)}</Text>
              ) : null}

              {/* OF.22–OF.23d: в день встречи вместо обложки — карточка адреса. Сейчас важно, КУДА идти:
                  адрес крупно, под ним когда, кнопка маршрута; встречи не будет или место закрыто — чат. */}
              {dayView ? (
                <View style={s.cardShadow}>
                  <GlassSurface tone="light" radius={20} style={s.dayCard}>
                    {hybrid ? (
                      /* HY.22–HY.23d: два входа двумя строками. Под каждым — что с ним сейчас; когда кто-то
                         сменил сторону, под строкой стоит, кто этим входом пользуется (HY.22e / 22f). */
                      <>
                        <View style={s.dayRow}>
                          <IconPin size={30} c={color.primary} />
                          <View style={{ flex: 1, gap: 2 }}>
                            <Text style={s.dayPlace} numberOfLines={2}>{placeLabel || String(plan.district || '')}</Text>
                            <Text style={s.daySub} numberOfLines={1}>
                              {dayOff ? HYB.cancelled() : closedNow || movedToCall ? HYB.closedRightNow()
                                : phase === 'now' ? OFD.startsNow()
                                : iOnCall && !theyOnCall ? HYB.whoInPerson(other)
                                : theyOnCall && !iOnCall ? HYB.whoInPerson(T('Ты', 'You', 'Tú'))
                                : `${dOf(plan.starts_at)} · ${tOf(plan.starts_at, ru)}`}
                            </Text>
                          </View>
                        </View>
                        <View style={s.dayRow}>
                          <IconVideo size={30} c={color.primary} />
                          <View style={{ flex: 1, gap: 2 }}>
                            <Text style={s.dayPlace} numberOfLines={1}>{HYB.cardCallLink()}</Text>
                            <Text style={s.daySub} numberOfLines={1}>
                              {dayOff ? HYB.cancelled() : linkOpen ? HYB.openNow()
                                : iOnCall && !theyOnCall ? HYB.whoOpens(T('Ты', 'You', 'Tú'), opensAt)
                                : theyOnCall && !iOnCall ? HYB.whoOpens(other, opensAt)
                                : HYB.opensAt(opensAt)}
                            </Text>
                          </View>
                        </View>
                      </>
                    ) : onlineCall ? (
                      /* O.22 / O.23 / O.23d: чья ссылка и куда она ведёт; когда идёт или отменён — час в обоих поясах. */
                      <View style={s.dayRow}>
                        <IconVideo size={30} c={color.primary} />
                        <View style={{ flex: 1, gap: 2 }}>
                          <Text style={s.dayPlace} numberOfLines={2}>
                            {dayOff ? OND.cardOff(svc) : nobody ? OND.cardNobody(svc, tOf(plan.starts_at, ru))
                              : phase === 'now' ? OND.cardNow(svc) : OND.cardLink(linkMine, other, svc)}
                          </Text>
                          <Text style={s.daySub} numberOfLines={1}>
                            {nobody ? OND.nobodySub() : dayOff || phase === 'now'
                              ? `${tOf(plan.starts_at, ru)}${peerTime ? ` · ${peerTime}` : ''}`
                              : OND.leaves(svc)}
                          </Text>
                        </View>
                      </View>
                    ) : (
                    <View style={s.dayRow}>
                      <IconPin size={30} c={color.primary} />
                      <View style={{ flex: 1, gap: 2 }}>
                        <Text style={s.dayPlace} numberOfLines={2}>{placeLabel || String(plan.district || '')}</Text>
                        <Text style={s.daySub} numberOfLines={1}>
                          {phase === 'now' ? OFD.startsNow() : `${dOf(plan.starts_at)} · ${tOf(plan.starts_at, ru)}`}
                        </Text>
                      </View>
                    </View>
                    )}
                    {hyDay && !dayOff && closedNow ? (
                      /* HY.23c: место закрыто — у гибрида есть выход, ссылка уже открыта. Переводит обоих. */
                      <Pressable accessibilityRole="button" style={s.dayBtn} onPress={moveToCall}>
                        <Text style={s.ctaText}>{PLAN.moveToCall()}</Text>
                      </Pressable>
                    ) : hyDay && !dayOff && iOnCall ? (
                      /* HY.22e: я в звонке — кнопка ведёт в звонок; до открытия ссылки она говорит, когда. */
                      <Pressable accessibilityRole="button" disabled={!linkOpen} accessibilityState={{ disabled: !linkOpen }}
                                 style={[s.dayBtn, !linkOpen && { opacity: 0.45 }]} onPress={openCall}>
                        <Text style={s.ctaText}>{linkOpen ? OND.openLink() : HYB.linkOpensBtn(opensAt)}</Text>
                      </Pressable>
                    ) : (
                    <Pressable accessibilityRole="button" style={s.dayBtn}
                               onPress={dayOff || closedNow || nobody ? openChat : onlineCall ? openCall : openRoute}>
                      <Text style={s.ctaText}>
                        {dayOff || closedNow || nobody ? OFD.openChat() : onlineCall ? OND.openLink() : PLAN.openRoute()}
                      </Text>
                    </Pressable>
                    )}
                  </GlassSurface>
                </View>
              ) : afterNew ? (
                /* OF.24: адрес и когда это было — без кнопки, идти уже некуда. */
                <View style={s.cardShadow}>
                  <GlassSurface tone="light" radius={20} style={s.dayCard}>
                    <View style={s.dayRow}>
                      <View style={{ flex: 1, gap: 4 }}>
                        <Text style={s.dayPlace} numberOfLines={2}>
                          {onlineCall ? OND.afterCard(svc) : hybrid ? HYB.afterCard(placeLabel || String(plan.district || ''))
                            : (placeLabel || String(plan.district || ''))}
                        </Text>
                        <View style={s.pastRow}>
                          <IconClock size={14} c={color.fg} />
                          <Text style={[s.daySub, { color: color.fg }]} numberOfLines={1}>{pastDay(plan.starts_at, ru)}</Text>
                        </View>
                      </View>
                      {onlineCall ? <IconVideo size={30} c={color.primary} /> : <IconPin size={30} c={color.primary} />}
                    </View>
                  </GlassSurface>
                </View>
              ) : (
              <View style={s.cardShadow}>
              <GlassSurface tone="light" radius={20} style={s.card}>
                {/* Обложка — по теме затеи (src/covers.ts), как у карточки затеи и у страниц группы (OF.20). */}
                <Cover intent={{ title: intentTitle || plan.title, topics: plan.topics, mode: plan.mode }} style={s.cover} />
                <View style={s.cardBody}>
                <View style={s.metaRow}>
                  {nl ? (
                    /* OF.20–OF.C5: дата и время раздельно, каждое со своим знаком. Пока висит перенос,
                       карточка показывает ПРЕДЛОЖЕННОЕ время (OF.21b, OF.C5), а старое названо в пояснении. */
                    <>
                      <View style={s.metaPair}>
                        <IconCalendar size={18} c={color.primary} />
                        <Text style={s.metaText}>{dOf((pendingChange || plan).starts_at)}</Text>
                      </View>
                      <View style={s.metaPair}>
                        <IconClock size={18} c={color.primary} />
                        <Text style={s.metaText}>{tOf((pendingChange || plan).starts_at, ru)}{peerTime && !pendingChange ? ` · ${peerTime}` : ''}</Text>
                      </View>
                    </>
                  ) : (
                    <>
                      <IconCalendar size={18} c={color.primary} />
                      <Text style={s.metaText}>{planWhen(plan, ru)}{peerTime ? ` · ${peerTime}` : ''}</Text>
                    </>
                  )}
                </View>
                {/* O.21b: предложенное время стоит РЯДОМ со старым — обе строки видны разом. */}
                {pendingChange && !nl ? (
                  <View style={s.metaRow}>
                    <IconClock size={16} c={color.primary} />
                    <Text style={[s.metaText, { color: color.primary }]}>
                      {PLAN.newPrefix(planWhen(pendingChange, ru))}
                    </Text>
                  </View>
                ) : null}
                {/* Район — когда точного места этот человек ещё не видит (OF.C3: «Barceloneta»). Видит —
                    одна строка адреса, как на OF.20/OF.21; два места подряд читались как два адреса. */}
                {/* HY.21f / 21g: согласованный гибрид без места говорит «No place yet» одной строкой — район рядом читался как место. */}
                {plan.district && !(placeLike && placeLabel) && !(hybrid && !placeSet && phase !== 'waiting') ? (
                  <View style={s.metaRow}>
                    <IconPin size={18} c={color.primary} />
                    <Text style={s.metaText}>{plan.district}</Text>
                  </View>
                ) : null}
                {/* OF.20/OF.21: строка места. До подтверждения — честное «после подтверждения»,
                    после — само место; пока не выбрано — «пока нет». Когда место уже стоит зелёной
                    плашкой ниже (OF.22/OF.23), здесь его не повторяем — один адрес, одно место. */}
                {/* У отменённой встречи адрес не обещают: «откроется после твоего подтверждения»
                    было прямой неправдой — подтверждать больше нечего, а сервер закрывает адрес
                    отказавшемуся автоматически (его ответ перестал быть «подтвердил»). */}
                {/* Отменённой встрече адрес не обещаем, но уже открытый — показываем (OF.19c, OF.C6):
                    сервер отдаёт его тем, кому он был открыт до отмены. */}
                {phase === 'cancelled' && placeLike && placeLabel ? (
                  <View style={s.metaRow}>
                    <IconPin size={18} c={color.primary} />
                    <Text style={s.metaText}>{placeLabel}</Text>
                  </View>
                ) : null}
                {wantsPlace && phase !== 'cancelled'
                  && !(placeReady && placeLabel) && !(allSet && placeLabel && !placeLike)
                  && !(placeLike && placeSet && !placeLabel && plan.district) ? (
                  <View style={s.metaRow}>
                    <IconPin size={18} c={color.primary} />
                    <Text style={s.metaText}>
                      {!placeSet ? (hybrid ? HYB.placeNone() : PLAN.noPlaceYet())
                        : placeLabel ? placeLabel
                        : PLAN.addressAfterConfirm()}
                    </Text>
                  </View>
                ) : null}
                {/* Строка ссылки. Стояла на «режим == online», а строка места — на «offline»:
                    гибрид не тот и не другой, и на его экране не было НИ ОДНОЙ из двух — при том
                    что у гибрида как раз оба входа и есть суть (HY.21 «both ways open»). */}
                {onlineCall ? (
                  /* O.20–O.21e, O.C3–O.C6, O.24b–O.24c: одна строка про ссылку — что с ней сейчас. */
                  <View style={s.metaRow}>
                    <IconVideo size={18} c={color.primary} />
                    <Text style={s.metaText}>
                      {phase === 'cancelled' ? ONB.cardCancelled()
                        : phase === 'after' ? (bothNo ? ONB.cardDidnt() : OND.afterCard(svc))
                        : !linkSet ? ONB.cardNoLink()
                        : pendingChange && phase === 'confirmed' ? ONB.cardSame()
                        : phase === 'confirmed' ? ONB.cardOpens(linkOpensAt(plan, ru))
                        : linkMine ? ONB.cardSaved() : ONB.cardTheirs(other)}
                    </Text>
                  </View>
                ) : hybrid ? (
                  /* HY.20–HY.24c: вторая строка карточки — что со ссылкой на звонок. */
                  <View style={s.metaRow}>
                    <IconVideo size={18} c={color.primary} />
                    <Text style={s.metaText}>
                      {phase === 'cancelled' ? HYB.linkCancelled()
                        : phase === 'after' ? HYB.linkClosed()
                        : !linkSet ? HYB.linkNone()
                        : pendingChange && phase === 'confirmed' ? HYB.linkSame()
                        : phase === 'confirmed' ? HYB.linkOpens(linkOpensAt(plan, ru))
                        : linkMine ? HYB.linkSaved() : HYB.linkFrom(other)}
                    </Text>
                  </View>
                ) : wantsLink ? (
                  <View style={s.metaRow}>
                    <IconLink size={16} c={color.muted} />
                    {/* Когда ссылка открыта, об этом говорит зелёная карточка ниже — здесь только факт
                        формата, иначе одна и та же фраза стоит на экране дважды. */}
                    <Text style={s.metaText}>
                      {phase === 'cancelled'
                        // O.C4: формат + факт отмены одной строкой.
                        ? PLAN.calledOff()
                        // Встреча позади — обещать, что ссылка «откроется в 18:14», уже неправда.
                        : phase === 'after' ? (hybrid ? PLAN.modeHybrid() : PLAN.modeOnline())
                        // O.20a: ссылки ещё нет — врать «откроется в …» нечем.
                        : !linkSet ? PLAN.noLinkYet()
                        // Когда ниже стоит «Всё готово», час открытия ссылки назван там — здесь
                        // остаётся только формат встречи.
                        : allSet ? (hybrid ? PLAN.modeHybrid() : PLAN.modeOnline())
                        : linkReady ? PLAN.linkSaved() : PLAN.linkOpensLabel(linkOpensAt(plan, ru))}
                    </Text>
                  </View>
                ) : null}
                </View>
              </GlassSurface>
              </View>
              )}

              {/*
                ПОЛОСА РАУНДА / СРОКА (OF.20, OF.21b, OF.C3b, OF.C5): «Round 1 / 3 · Ends in 6h» пока план
                согласуют, «Accepted 0 of 1 · Ends in 6h» пока ждёт перенос. Числа — только с сервера:
                нет поля — нет полосы (раунды для 1:1 делает агент логики, 06.10.2026).
              */}
              {meter ? (
                <View style={s.cardShadow}>
                  <GlassSurface tone="light" radius={20} style={s.meter}>
                    <View style={s.meterHead}>
                      <Text style={[s.meterWord, { flex: 1 }]}>{meter.label}</Text>
                      <Text style={s.meterNum}><Text style={s.meterNow}>{meter.now}</Text>{meter.sep}{meter.of}</Text>
                      <Text style={[s.meterTime, { flex: 1, textAlign: 'right' }]} numberOfLines={1}>{meter.right}</Text>
                    </View>
                    <View style={s.bars}>
                      {meter.segments.map((on, i) => (
                        <View key={i} style={s.bar}><View style={[s.barFill, { width: `${Math.max(on ? 100 : 0, 0)}%` }]} /></View>
                      ))}
                    </View>
                  </GlassSurface>
                </View>
              ) : null}

              {/*
                Договорились обо всём — и это сказано вслух, зелёным, один раз.
                Не хватало именно этого: план подтверждался, место называлось, а экран продолжал
                выглядеть как незаконченное дело — человек не понимал, надо ли ещё что-то нажать.
                Плашка живёт только в «подтверждено»: у «скоро» и «сейчас» ниже своя, с маршрутом.
              */}
              {needsWhere && mode === 'offline' ? (
                <Pressable accessibilityRole="button" accessibilityLabel={chatCopy.open}
                  accessibilityState={{ disabled: openingChat, busy: openingChat }} disabled={openingChat}
                  style={[s.ctaSoft, openingChat && { opacity: 0.5 }]} onPress={openChat}>
                  <Text style={s.ctaSoftText}>{openingChat ? chatCopy.loading : chatCopy.open}</Text>
                </Pressable>
              ) : null}

              {/* OF.21 / OF.C3c: у встречи вживую адрес стоит в самой карточке, зелёной плашки нет. */}
              {allSet && !nl ? (
                <View style={s.doneCard}>
                  <Text style={s.doneTitle}>{PLAN.allSetTitle()}</Text>
                  {/*
                    Время и место — ОТДЕЛЬНЫМИ СТРОКАМИ, как и всюду выше по экрану: та же
                    `metaRow`, те же иконки. Ради этого плашку и открывают, а прежде они лежали
                    в середине фразы тринадцатым кеглем и ничем не отличались от слов вокруг.
                  */}
                  <View style={s.doneRow}>
                    <IconCalendar size={16} c={color.successText} />
                    <Text style={s.doneFact}>{planWhen(plan, ru)}</Text>
                  </View>
                  {wantsPlace && placeLabel ? (
                    <View style={s.doneRow}>
                      <IconPin size={16} c={color.successText} />
                      <Text style={s.doneFact} numberOfLines={2}>{placeLabel}</Text>
                    </View>
                  ) : null}
                  <Text style={s.doneSub}>{PLAN.allSetTail(mode, other)}</Text>
                </View>
              ) : null}

              {/* OF.22/OF.23: место и маршрут — зелёной плашкой, когда встреча на носу. */}
              {placeReady && placeLabel ? (
                <View style={s.linkCard}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.linkTitle} numberOfLines={2}>{placeLabel}</Text>
                    <Text style={s.linkSub}>
                      {phase === 'now' ? PLAN.meetupNow() : PLAN.startsIn(minutesToStart(plan))}
                    </Text>
                  </View>
                  <Pressable accessibilityRole="button" style={s.linkBtn} onPress={openRoute}>
                    <Text style={s.linkBtnText}>{PLAN.openRoute()}</Text>
                  </Pressable>
                </View>
              ) : null}

              {/* O.22/O.23: ссылка становится кнопкой только теперь — см. шапку файла. */}
              {!offline && !dayView && linkReady && serverLink ? (
                <View style={s.linkCard}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.linkTitle}>{PLAN.linkOpenNow()}</Text>
                    <Text style={s.linkSub}>{PLAN.leavesKleal()}</Text>
                  </View>
                  <Pressable
                    accessibilityRole="button"
                    style={s.linkBtn}
                    /* Открыть ссылку = выйти на связь. Другого признака у звонка нет: «я на
                       месте» — кнопка офлайновая, и без этой отметки после звонка невозможно
                       отличить «поговорили» от «никто не пришёл» (O.23c). Отметка идёт ФОНОМ:
                       ссылка должна открыться даже если сервер не ответил. */
                    onPress={() => {
                      /* Не через sendLive: тот на неудаче пишет «не удалось» на экран, а здесь
                         неудача незаметна и неважна — ссылка всё равно открылась. */
                      agent.planStatus(plan.id, me, 'here').then((r: any) => {
                        if (r?.plan) setPlan(r.plan);
                      }).catch(() => {});
                      Linking.openURL(withScheme(serverLink)).catch(() => setErr(CHAT.planFailed()));
                    }}
                  >
                    <Text style={s.linkBtnText}>{PLAN.openLink()}</Text>
                  </Pressable>
                </View>
              ) : null}

              {/* O.23a: короткая строка факта — что, когда и кто отменил — и сразу выход в новое
                  время. Только у автора отмены: на кадре второй стороны (O.C4) плашки нет. */}
              {phase === 'cancelled' && cancelledByMe && !leftFinal && !iCancelled ? (
                <View style={s.pillRow}>
                  <View style={s.pill}>
                    <Text style={s.pillText} numberOfLines={2}>
                      {(plan.mode === 'online' ? PLAN.modeOnline() : (plan.district || T('Встреча', 'Meetup', 'Quedada')))}
                      {' · '}{planWhen(plan, ru)}
                      {' · '}{cancelledByMe ? PLAN.calledOffByYou() : PLAN.calledOffBy(other)}
                    </Text>
                  </View>
                  <Pressable accessibilityRole="button" style={s.pillBtn} onPress={startNewPlan}>
                    <Text style={s.pillBtnText}>{PLAN.anotherTime()}</Text>
                  </Pressable>
                </View>
              ) : null}

              {/* Участники по доске: другой — сверху, «Ты» — снизу; у организатора голубой «organiser»;
                  статус зелёным, когда человек своё сказал, кораллом — когда ждут тебя, серым — когда его. */}
              {[...(plan.participants || [])].sort((a: any, b: any) => Number(!!a.is_me) - Number(!!b.is_me)).map((p: any, i: number) => {
                const liveSt = String(p?.live?.status || '');
                const liveEta = Number(p?.live?.eta_min || 0);
                // OF.22–23d: в день встречи статус — живой («Running late · 20 min», «At the place»), иначе «Confirmed».
                const fbDone = p.is_me ? mine !== undefined : !!plan?.their_feedback;
                const st = afterOff ? (fbDone ? OFD.stAnswered() : p.is_me ? OFD.stNeeded() : OFD.stHasnt())
                  // O.21e / O.C3e: согласовано, ссылки нет — в строках видно, кто её добавляет и кто ждёт.
                  : hyGap ? (p.is_me
                      ? (myNeedPlace && myNeedLink ? HYB.stAddBoth() : myNeedLink ? ONB.stAddLink() : myNeedPlace ? HYB.stAddPlace()
                        : !placeSet && !linkSet ? HYB.stWaitDetails() : !linkSet ? ONB.stWaitLink() : HYB.stWaitPlace())
                      : (myNeedPlace || myNeedLink
                        ? (!placeSet && !linkSet ? HYB.stWaitDetails() : !linkSet ? ONB.stWaitLink() : HYB.stWaitPlace())
                        : (!placeSet && !linkSet ? HYB.stTheyAddBoth() : !linkSet ? ONB.stTheyAdd() : HYB.stTheyAddPlace())))
                  : linkGap ? (p.is_me ? (linkOnMe ? ONB.stAddLink() : ONB.stWaitLink())
                                       : linkOnMe ? (askedMeLink ? ONB.stAskedYou() : ONB.stWaitLink())
                                       : (askedThemLink ? ONB.stAskedToHost() : ONB.stTheyAdd()))
                  : dayView
                  ? (nobody ? OND.stDidntJoin()
                    : liveSt === 'cant_make_it' ? (p.is_me ? OFD.stCantTold(otherG) : OFD.stCantJustNow())
                    : liveSt === 'late' ? OFD.stLate(liveEta)
                    // Оба переведены в звонок — «на месте» уже неправда.
                    : hybrid && movedToCall ? HYB.stOnCall()
                    : liveSt === 'here' ? PLAN.liveHere()
                    // HY.22–HY.22f: у гибрида рядом с «Confirmed» — сторона; по умолчанию человек идёт вживую.
                    : hybrid ? ((p.is_me ? iOnCall : theyOnCall) ? HYB.stOnCall() : HYB.stInPerson())
                    : T('Подтвердил(а)', 'Confirmed', 'Confirmado'))
                  : statusFor(p, plan, phase!, pendingChange, ru);
                // Тон статуса: сказал своё — зелёный, ждут меня — коралл, ждут его — серый.
                const proposer = pendingChange ? (p.is_me ? !!pendingChange.mine : !pendingChange.mine) : false;
                const leaver = leftFinal && (pidOf(p, 'name') && plan?.cancelled_by_id
                  ? pidOf(p, 'name') === plan.cancelled_by_id
                  : String(p?.name || '').trim().toLowerCase() === String(plan?.cancelled_by || '').trim().toLowerCase());
                const canceller = (hostOff || iCancelled) && p.role === 'host';
                const quiet = silentOff && isSilent(plan, p);
                const tone = afterOff ? (fbDone ? s.stOk : p.is_me ? s.stTurn : s.stMuted)
                  : hyGap ? (p.is_me && (myNeedPlace || myNeedLink) ? s.stTurn : s.stMuted)
                  : linkGap ? (p.is_me && linkOnMe ? s.stTurn : s.stMuted)
                  : dayView ? (nobody || liveSt === 'late' || liveSt === 'cant_make_it' ? s.stLeft : s.stOk)
                  : silentOff ? (quiet ? s.stLeft : s.stPlain)
                  : hostOff || iCancelled ? (canceller ? s.stLeft : s.stOk)
                  : leftFinal ? (leaver ? s.stLeft : s.stPlain)
                  : pendingChange
                  ? (proposer ? s.stOk : p.is_me ? s.stTurn : s.stMuted)
                  : p.is_me && !p.confirmed && phase === 'waiting' ? s.stTurn
                  : p.confirmed ? s.stOk : s.stMuted;
                return (
                  <View key={(p.name || '') + i} style={s.person}>
                    {/* Заглушка рисуется всегда, фото ложится поверх: пока оно едет (или не доехало вовсе),
                        на месте человека кружок, а не дыра. Так же сделано в составе группы. */}
                    <View style={[s.personAva, s.personAvaEmpty]}>
                      <IconPerson size={18} />
                      {p.photo ? (
                        <Image source={{ uri: mediaUrl(String(p.photo)) }} style={[s.personAva, StyleSheet.absoluteFill]} />
                      ) : null}
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={s.nameRow}>
                        <Text style={s.personName} numberOfLines={1}>{p.is_me ? T('Ты', 'You', 'Tú') : `${p.name}${p.age ? `, ${p.age}` : ''}`}</Text>
                        {p.role === 'host' ? <View style={s.orgBadge}><Text style={s.orgText}>{T('организатор', 'organiser', 'organizador')}</Text></View> : null}
                      </View>
                      {st ? <Text style={[s.personStatus, tone]}>{st}</Text> : null}
                    </View>
                    {afterOff ? (!fbDone && !p.is_me ? <IconClock size={20} c={color.fg} /> : null)
                      : linkGap || hyGap ? <IconClock size={20} c={color.fg} />
                      : dayView ? (nobody ? <IconTimer size={20} c={color.fg} />
                        : liveSt === 'late' ? <IconClock size={20} c={color.fg} />
                        : liveSt === 'cant_make_it' ? <IconTimer size={20} c={color.fg} />
                        : <IconPin size={20} c={color.fg} />)
                      : silentOff ? (quiet ? <IconClock size={20} c={color.fg} /> : null)
                      : hostOff || iCancelled ? (canceller ? <IconInfo size={20} c={color.fg} /> : <IconCalendar size={20} c={color.fg} />)
                      : leftFinal ? (leaver ? <IconExit size={20} c={color.fg} /> : null)
                      : nl && phase === 'confirmed' && !pendingChange && p.confirmed ? <IconUserCheck size={22} c={color.fg} />
                      : (pendingChange ? proposer : p.confirmed) ? <IconCalendar size={20} c={color.fg} /> : <IconClock size={20} c={color.fg} />}
                  </View>
                );
              })}

              {dayView ? (
                /* OF.23: «Kleal can't see the meetup» — только когда встреча идёт; за полчаса и после
                   «не смогу» плашки на кадрах нет. */
                phase === 'now' && !dayOff ? (
                  <View style={s.infoBox}>
                    <Text style={[s.infoText, s.infoTitle]}>{onlineCall ? OND.blindTitle(svc) : hybrid ? HYB.twoWaysTitle() : OFD.blindTitle()}</Text>
                    <Text style={s.infoText}>{onlineCall ? OND.blindNote() : hybrid ? HYB.twoWaysNote(placeShort) : OFD.blindNote()}</Text>
                  </View>
                ) : null
              ) : phase === 'soon' || phase === 'now' ? (
                <View style={s.infoBox}>
                  {/* Kleal не видит ни звонок, ни встречу — но говорит об этом их словами. */}
                  {/* У гибрида, пока никуда не ушли, оба входа живы — и говорить надо про оба.
                      После HY.23c остаётся ровно «звонок вне Kleal»: он и есть правда. */}
                  <Text style={s.infoText}>
                    {offline ? PLAN.meetupBlindNote()
                      : hybrid && !movedToCall ? PLAN.outsideNoteHybrid()
                      : PLAN.outsideNote()}
                  </Text>
                </View>
              ) : null}

              {err ? <Text style={s.err}>{err}</Text> : null}

              {/* O.24: спрашиваем оба факта до оценки — оценка без ответа про сам факт бессмысленна. */}
              {/* OF.24–OF.24c: кнопки «после встречи» один на один. «I didn't go» здесь нет: в 1:1 без тебя
                  встреча не состоялась — это причина в листе OF.24a. */}
              {afterOff ? (
                afterNew ? (
                  <>
                    <Pressable accessibilityRole="button" style={s.cta} onPress={() => answerHappened(true)}>
                      <Text style={s.ctaText}>{onlineCall ? OND.yesTalked() : OFD.yesMet()}</Text>
                    </Pressable>
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => answerHappened(false)}>
                      <Text style={s.ctaSoftText}>{OFD.didntHappen()}</Text>
                    </Pressable>
                  </>
                ) : bothNo ? (
                  <>
                    {hostIsMe(plan, me) ? (
                      <Pressable accessibilityRole="button" style={s.cta} onPress={openPicking}>
                        <Text style={s.ctaText}>{OFD.reopenIntent()}</Text>
                      </Pressable>
                    ) : (
                      <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.navigate('/buddy')}>
                        <Text style={s.ctaText}>{OFB.createIntent()}</Text>
                      </Pressable>
                    )}
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={openChat}>
                      <Text style={s.ctaSoftText}>{PLAN.messageThem(other)}</Text>
                    </Pressable>
                  </>
                ) : (
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{OFD.openChat()}</Text>
                  </Pressable>
                )
              ) : null}

              {asking && !afterOff && mine === undefined ? (
                <>
                  {/* O.23c: звонок прошёл, а ссылку не открыл никто. Вопрос «состоялось ли»
                      остаётся — мы знаем только про ссылку, а созвониться могли и мимо неё, — но
                      молчать про это нельзя: чаще всего именно это и случилось. */}
                  {nobodyJoined ? (
                    <View style={s.infoBox}><Text style={s.infoText}>{PLAN.nobodyJoined()}</Text></View>
                  ) : null}
                  <View style={s.infoBox}><Text style={s.infoText}>{PLAN.didItNote(other)}</Text></View>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={() => answerHappened(true)}>
                    <Text style={s.ctaText}>{PLAN.yesWeTalked()}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => answerHappened(false)}>
                    <Text style={s.ctaDarkText}>{PLAN.noItDidnt()}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* O.25: отзыв — только после того, как сам ответил про факт встречи. */}
              {asking && !afterOff && mine === true ? (
                thanks || myRated(plan) ? (
                  // Ответ записан. Сама запись — блоком ниже, здесь остаётся только то, чего в
                  // ней нет: кого ещё ждём. Благодарность живёт мгновение и в заголовке.
                  !bothAnswered ? <Text style={s.note}>{waitingLine()}</Text> : null
                ) : (
                  <>
                    {/*
                      HY.25 — «как встретились». Вопрос ТОЛЬКО у гибрида и только у того, кто
                      сказал «состоялась»: у него было два входа, и какой сработал — это не оценка
                      встречи, а подсказка агенту на следующий раз. «И так и так» стоит намеренно:
                      обычный исход, когда один пришёл, второй подключился, а потом поменялись.
                    */}
                    {hybrid ? (
                      <>
                        <Text style={s.doneTitle}>{PLAN.howMetTitle()}</Text>
                        <Text style={s.note}>{PLAN.howMetNote()}</Text>
                        <View style={s.chipRowWrap}>
                          {([
                            ['in_person', PLAN.howInPerson()],
                            ['call', PLAN.howCall()],
                            ['both', PLAN.howBoth()],
                          ] as ['in_person' | 'call' | 'both', string][]).map(([k, label]) => (
                            <Pressable
                              key={k}
                              accessibilityRole="button"
                              accessibilityState={{ selected: howMet === k }}
                              onPress={() => setHowMet(k)}
                              style={[s.chip, howMet === k && s.chipOn]}
                            >
                              <Text style={[s.chipText, howMet === k && { color: color.onPrimary }]}>
                                {label}
                              </Text>
                            </Pressable>
                          ))}
                        </View>
                      </>
                    ) : null}
                    <Text style={s.note}>{PLAN.optional()}</Text>
                    <View style={s.chipRowWrap}>
                      {RATINGS.map(([k, label]) => (
                        <Pressable
                          key={k}
                          accessibilityRole="button"
                          accessibilityState={{ selected: rating === k }}
                          onPress={() => setRating(k)}
                          style={[s.chip, rating === k && s.chipOn]}
                        >
                          <Text style={[s.chipText, rating === k && { color: color.onPrimary }]}>{label()}</Text>
                        </Pressable>
                      ))}
                    </View>
                    <Pressable accessibilityRole="button" style={s.cta} onPress={sendRating}>
                      <Text style={s.ctaText}>{PLAN.send()}</Text>
                    </Pressable>
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={openReport}>
                      <Text style={s.ctaDarkText}>{PLAN.reportProblem()}</Text>
                    </Pressable>
                  </>
                )
              ) : null}

              {/* O.24b: оба сказали «не состоялась» — это отдельный конец, а не общее «спасибо».
                  Если ответы разошлись (я «нет», второй «да»), сервер считает встречу
                  состоявшейся, и говорить «не состоялась» было бы неправдой — там остаётся
                  благодарность за ответ. */}
              {asking && !afterOff && mine === false ? (
                !bothAnswered ? (
                  <Text style={s.note}>{waitingLine()}</Text>
                ) : plan?.outcome?.happened === false ? (
                  <>
                    {/* Название этого исхода уже стоит заголовком экрана — здесь остаётся то,
                        чего в заголовке нет: что делать дальше. */}
                    <Text style={s.note}>{PLAN.didntHappenNote(other)}</Text>
                    <Pressable
                      accessibilityRole="button"
                      style={s.cta}
                      onPress={() => router.dismissTo('/home')}
                    >
                      <Text style={s.ctaText}>{PLAN.findElse()}</Text>
                    </Pressable>
                  </>
                ) : null
              ) : null}

              {/*
                ЗАПИСЬ О ПРОШЕДШЕЙ ВСТРЕЧЕ. Ради неё всё и переделано: план, упавший в историю,
                открывался благодарностью за анкету — «Спасибо, это поможет подбирать точнее», — и
                человек не находил ни где встречались, ни что он сам ответил. Всё это лежит на
                сервере с самого начала (`my_feedback`, `outcome`, место и формат) и до сих пор
                просто выбрасывалось.
                Чужой оценки здесь нет и не будет: её видит только тот, кто её поставил.
              */}
              {asking && !afterOff && recorded ? (
                <>
                  <Text style={s.doneTitle}>{PLAN.pastWhereTitle()}</Text>
                  <Text style={s.note}>{pastWhere()}</Text>

                  <Text style={s.doneTitle}>{PLAN.pastRecordTitle()}</Text>
                  <Text style={s.note}>{mine ? PLAN.pastYouSaidYes() : PLAN.pastYouSaidNo()}</Text>
                  {mine ? (
                    ratingLabel()
                      ? <Text style={s.note}>{PLAN.pastRated(ratingLabel())}</Text>
                      : <Text style={s.note}>{PLAN.pastNotRated()}</Text>
                  ) : null}
                  {reasonLabel() ? <Text style={s.note}>{PLAN.pastReason(reasonLabel())}</Text> : null}
                  {howLabel() ? <Text style={s.note}>{PLAN.pastHowMet(howLabel())}</Text> : null}
                  {String(plan?.my_feedback?.text || '').trim()
                    ? <Text style={s.note}>{String(plan.my_feedback.text).trim()}</Text> : null}
                  <Text style={s.note}>{PLAN.pastOnlyYou(other)}</Text>
                  {!plan?.their_feedback ? <Text style={s.note}>{PLAN.pastTheyNever(other)}</Text> : null}

                  {/*
                    ВЕРНУТЬСЯ В РАЗГОВОР. Кнопка чата есть у каждого состояния плана — у
                    ожидания, у подтверждённого, у «скоро», у отменённого, — и не было ровно у
                    прошедшего. Из-за этого история оказывалась тупиком: человек открывал
                    состоявшуюся встречу и не мог написать тому, с кем встречался. А переписка
                    жива: сервер её не закрывает, и писать в неё можно.
                  */}
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ disabled: openingChat, busy: openingChat }}
                    disabled={openingChat}
                    style={[s.cta, openingChat && { opacity: 0.5 }]}
                    onPress={openChat}
                  >
                    <Text style={s.ctaText}>{CHAT.openChat()}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* O.20a: поле и две кнопки — ссылка или просьба хостить. Пока висит перенос, не показываем:
                  сперва договориться о времени, потом нести ссылку. */}
              {/* HY.20c говорит прямо: «Start with the place, then the link». Место идёт
                  первым, потому что от него зависит, кому вообще есть смысл идти живьём;
                  ссылку можно донести и позже. Раньше блоки стояли наоборот, и у гибрида,
                  где не задано ни одного входа, первым спрашивалась ссылка. */}
              {/* Замок: поля места и ссылки сервер уже не примет — вместо серого «не удалось» одна
                  честная строка. Человек в это время едет, и договариваться ему в чате. */}
              {whereLocked ? (
                <View style={s.infoBox}><Text style={s.infoText}>{PLAN.whereLockedNote()}</Text></View>
              ) : null}
              {needsPlace && !pendingChange && !countering && offeredByServer('address') ? (
                <>
                  {/* Второй передал выбор мне — экран говорит это первым, поле идёт следом. */}
                  {askedMePlace ? (
                    <View style={s.infoBox}><Text style={s.infoText}>{PLAN.askedMePlace(other)}</Text></View>
                  ) : null}
                  {/* Место — с подсказками и «где я», как везде: см. src/components/AddressField. */}
                  <AddressField
                    style={s.input}
                    value={placeDraft}
                    onChange={setPlaceDraft}
                    onPick={(h) => setPlaceDraft(h.label)}
                    placeholder={PLAN.placePlaceholder()}
                  />
                  <Pressable
                    accessibilityRole="button"
                    disabled={!placeDraft.trim()}
                    accessibilityState={{ disabled: !placeDraft.trim() }}
                    style={[s.cta, !placeDraft.trim() && { opacity: 0.45 }]}
                    onPress={savePlace}
                  >
                    <Text style={s.ctaText}>{PLAN.savePlace()}</Text>
                  </Pressable>
                  {/* Меня уже попросили — просить в ответ нечего: кнопки нет. Попросил я — ждём. */}
                  {askedMePlace ? null : (
                    <Pressable
                      accessibilityRole="button"
                      disabled={askedThemPlace}
                      accessibilityState={{ disabled: askedThemPlace }}
                      style={[s.ctaDark, askedThemPlace && { opacity: 0.45 }]}
                      onPress={askPlace}
                    >
                      <Text style={s.ctaDarkText}>{askedThemPlace ? PLAN.askedThemPlace(other) : PLAN.askChoose(other)}</Text>
                    </Pressable>
                  )}
                </>
              ) : null}
              {needsLink && !pendingChange && !countering && offeredByServer('address') ? (
                <>
                  {/* У звонка о просьбе уже сказал заголовок (O.C3e) — вторая плашка её только повторяла. */}
                  {askedMeLink && mode !== 'online' ? (
                    <View style={s.infoBox}><Text style={s.infoText}>{PLAN.askedMeLink(other)}</Text></View>
                  ) : null}
                  <TextInput
                    style={s.input}
                    value={linkDraft}
                    onChangeText={setLinkDraft}
                    placeholder={PLAN.pasteLink()}
                    placeholderTextColor={color.neutral400}
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="url"
                    accessibilityLabel={PLAN.pasteLink()}
                  />
                  <Pressable
                    accessibilityRole="button"
                    disabled={!looksLikeUrl(linkDraft.trim())}
                    accessibilityState={{ disabled: !looksLikeUrl(linkDraft.trim()) }}
                    style={[s.cta, !looksLikeUrl(linkDraft.trim()) && { opacity: 0.45 }]}
                    onPress={saveLink}
                  >
                    <Text style={s.ctaText}>{PLAN.saveLink()}</Text>
                  </Pressable>
                  {askedMeLink ? (
                    /* O.C3e «I can’t host»: отказ снимает просьбу — ссылку снова ждут от того, кто просил. */
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={declineHost}>
                      <Text style={s.ctaDarkText}>{ONB.cantHost()}</Text>
                    </Pressable>
                  ) : (
                    <Pressable
                      accessibilityRole="button"
                      disabled={askedThemLink || askCool}
                      accessibilityState={{ disabled: askedThemLink || askCool }}
                      style={[s.ctaDark, askedThemLink && { opacity: 0.45 }]}
                      onPress={askHost}
                    >
                      <Text style={s.ctaDarkText}>{askedThemLink ? PLAN.askedThemLink(other) : PLAN.askHost(other)}</Text>
                    </Pressable>
                  )}
                </>
              ) : null}

              {/* OF.20a: согласовано, а точного места нет — поле и две кнопки, как у ссылки. */}

              {/* Действия до встречи. «Другое время» — это counter (O.21b), а не новая встреча:
                  propose на живом плане честно бьётся об PLAN_EXISTS. Пока экран просит ссылку
                  (O.20a), на кадре стоят только её две кнопки — эти прячутся. Получателю
                  неподтверждённого плана здесь делать нечего — у него свой блок O.C3 ниже. */}
              {(phase === 'waiting' || phase === 'confirmed') && !pendingChange && !countering
                && !needsLink && !needsPlace
                && !(phase === 'waiting' && !myConfirmed(plan, me)) ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{CHAT.openChat()}</Text>
                  </Pressable>
                  {/* «Поправить план» обещало больше, чем делает: меняется только время. */}
                  {nl && canFix ? (
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={openFix}>
                      <Text style={s.ctaDarkText}>{OFB.fixPlan()}</Text>
                    </Pressable>
                  ) : !offeredByServer('counter') ? null : (
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setCountering(true)}>
                      <Text style={s.ctaDarkText}>{
                        nl && phase === 'waiting' ? OFB.changePlan()
                        : nl && phase === 'confirmed' ? (plan?.host && isMe(plan.host, plan.host_id, me)
                            ? (hybrid ? HYB.changeAll() : onlineCall ? ONB.changeTimeOrLink() : OFB.changeTimeOrPlace()) : OFB.askToChange())
                        : PLAN.suggestAnother()}</Text>
                    </Pressable>
                  )}
                </>
              ) : null}

              {/* O.C3: план прислали мне — подтвердить или предложить своё время. */}
              {offeredByServer('confirm') && !countering && !(finalOpen && !iHost) ? (
                <>
                  {hybrid && (placeSet || linkSet) ? (
                    /* HY.C3: подтверждение и есть выбор стороны — «приду вживую» или «буду в звонке».
                       Сторону предлагаем только ту, у которой есть вход: без места некуда идти, без ссылки не подключиться. */
                    <>
                      {placeSet ? (
                        <Pressable accessibilityRole="button" style={s.cta} onPress={() => confirmSide('in_person')}>
                          <Text style={s.ctaText}>{HYB.comeInPerson()}</Text>
                        </Pressable>
                      ) : null}
                      {linkSet ? (
                        <Pressable accessibilityRole="button" style={placeSet ? s.ctaSoft : s.cta} onPress={() => confirmSide('call')}>
                          <Text style={placeSet ? s.ctaSoftText : s.ctaText}>{HYB.joinCall()}</Text>
                        </Pressable>
                      ) : null}
                    </>
                  ) : (
                  <Pressable accessibilityRole="button" style={s.cta} onPress={() => respond('confirm')}>
                    <Text style={s.ctaText}>{PLAN.confirmAction()}</Text>
                  </Pressable>
                  )}
                  {!offeredByServer('counter') ? null : (
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setCountering(true)}>
                      <Text style={s.ctaSoftText}>{PLAN.suggestAnother()}</Text>
                    </Pressable>
                  )}
                </>
              ) : null}

              {/* OF.C3d: хозяин закрепил план — гость остаётся или выходит, без последствий. */}
              {finalOpen && !iHost && !countering ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={() => respond('stay')}>
                    <Text style={s.ctaText}>{OFB.stayIn()}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => respond('leave')}>
                    <Text style={s.ctaSoftText}>{OFB.leavePlan()}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* OF.19c: гость вышел из закреплённого плана — у хозяина затея снова открыта, у гостя — только чат. */}
              {leftFinal || iCancelled || (silentOff && iHost) ? (
                iHost ? (
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openPicking}>
                    <Text style={s.ctaText}>{OFB.pickElse()}</Text>
                  </Pressable>
                ) : (
                  <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={openChat}>
                    <Text style={s.ctaSoftText}>{CHAT.openChat()}</Text>
                  </Pressable>
                )
              ) : null}

              {/*
                Отменить встречу можно было ТОЛЬКО за десять минут до неё: до этого кнопки не было
                ни у автора плана, ни у того, кому его прислали. Человек, понявший в понедельник,
                что в субботу не сможет, не имел способа это сказать — и второй узнавал бы об этом,
                уже стоя у кафе.

                Стоит последней и мягкой, а не тёмной: рядом «Подтвердить» и «Другое время», и
                промах пальцем не должен необратимо гасить вечер. Поэтому же — подтверждение
                листом: отменённая встреча на сервере терминальна, вернуть её нельзя.
              */}
              {/* ФАЗА РЕШАЕТ, ГДЕ КНОПКЕ СТОЯТЬ, СЕРВЕР — МОЖНО ЛИ ЕЁ НАЖАТЬ. Сняв фазу, я поставил
                  «Отменить встречу» под вопрос «состоялась ли»: сервер разрешает decline любому
                  открытому плану, а `confirmed` держится, пока об исходе не ответят оба, — и
                  прошедшую встречу можно было необратимо отменить. У «скоро» и «сейчас» своя
                  кнопка ниже, поэтому здесь ровно те же две фазы, что были. */}
              {(phase === 'waiting' || phase === 'confirmed')
                && offeredByServer('decline') && !pendingChange && !countering
                && myLive !== 'cant_make_it' && !(finalOpen && !iHost) ? (
                <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setDropping(true)}>
                  <Text style={s.ctaSoftText}>{locked ? PLAN.cantMakeIt() : nl ? (iHost ? OFB.cancelPlan() : OFB.leavePlan()) : PLAN.callOff()}</Text>
                </Pressable>
              ) : null}

              {/* O.21b: моё встречное время ждёт ответа — можно забрать, пока второй не ответил. */}
              {(phase === 'waiting' || phase === 'confirmed') && pendingChange?.mine ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{CHAT.openChat()}</Text>
                  </Pressable>
                  {/* Забрать своё встречное время под замком уже нельзя — сервер его не примет. */}
                  {/* O.21b: у самого плана чужое местное время показано, а у ПРЕДЛОЖЕННОГО не было —
                      хотя решают именно про него. Через часовой пояс «давай в 20:00» может значить
                      у второго и полночь; согласиться на такое вслепую — обычный способ сорвать
                      встречу. Строка появляется только когда пояса разные (см. peerLocalTime). */}
                  {peerPendingTime ? (
                    <Text style={s.note}>{PLAN.theirTimeNote(other, peerPendingTime)}</Text>
                  ) : null}
                  {nl && canFix ? (
                    /* OF.20c: раунды кончились — своё предложение уже не правят, хозяин закрепляет версию. */
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={openFix}>
                      <Text style={s.ctaDarkText}>{OFB.fixPlan()}</Text>
                    </Pressable>
                  ) : nl && phase === 'waiting' && offeredByServer('counter') ? (
                    /* OF.C3b: до подтверждения своё предложение правят, а не забирают — новый раунд. */
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setCountering(true)}>
                      <Text style={s.ctaDarkText}>{OFB.editSuggestion()}</Text>
                    </Pressable>
                  ) : !offeredByServer('reject_change') ? (
                    <Text style={s.lockNote}>{PLAN.lockedNote()}</Text>
                  ) : (
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => respond('reject_change')}>
                      <Text style={s.ctaDarkText}>{PLAN.takeItBack()}</Text>
                    </Pressable>
                  )}
                </>
              ) : null}

              {/* O.C5: встречное время пришло мне — кнопки называют оба часа, решение очевидно. */}
              {(phase === 'waiting' || phase === 'confirmed') && pendingChange && !pendingChange.mine ? (
                <>
                  {/* O.C5 обещает выбор «подтвердить 20:00 / оставить 19:00». Внутри заморозки
                      сервер закрывает оба ответа, и рисовать их значит обещать несуществующее:
                      нажатие давало безымянную ошибку, а встречное время так и висело. */}
                  {!offeredByServer('accept_change') ? (
                    <Text style={s.lockNote}>{PLAN.lockedNote()}</Text>
                  ) : (
                    <>
                      <Pressable accessibilityRole="button" style={s.cta} onPress={() => respond('accept_change')}>
                        <Text style={s.ctaText}>{nl && phase === 'waiting' ? PLAN.confirmAction() : nl ? OFB.accept(tOf(pendingChange.starts_at, ru)) : PLAN.confirmTime(tOf(pendingChange.starts_at, ru))}</Text>
                      </Pressable>
                      {nl && phase === 'waiting' ? (
                        /* OF.20b: до подтверждения ответ на встречное — «Confirm» или новый раунд «Change the plan»;
                           в последнем раунде у хозяина вместо него «Fix the plan» (OF.20c), у гостя — ничего. */
                        canFix ? (
                          <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={openFix}>
                            <Text style={s.ctaSoftText}>{OFB.fixPlan()}</Text>
                          </Pressable>
                        ) : offeredByServer('counter') ? (
                          <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setCountering(true)}>
                            <Text style={s.ctaSoftText}>{OFB.changePlan()}</Text>
                          </Pressable>
                        ) : null
                      ) : (
                        <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => respond('reject_change')}>
                          <Text style={s.ctaSoftText}>{PLAN.keepTime(tOf(plan.starts_at, ru))}</Text>
                        </Pressable>
                      )}
                    </>
                  )}
                </>
              ) : null}

              {/*
                OF.22/OF.23/OF.C4 — действия у встречи на носу. Состав кнопок НЕ меняется при
                переходе «скоро» → «сейчас», и это сознательное отступление от борда: там в «скоро»
                на втором месте «Я опаздываю», а в «сейчас» — «Не смогу». Фаза переключается сама,
                по часам, раз в пятнадцать секунд. Человек, целившийся в «опаздываю», нажал бы
                отмену встречи — и отменил бы её по-настоящему, необратимо. Поэтому:

                  красная  — написать собеседнику (одна и та же во всех состояниях);
                  тёмная   — «Я опаздываю», пока я не отметился (самое частое действие);
                  мягкая   — выход: «Не могу ждать», когда опаздывает второй, иначе «Не смогу».

                «Я на месте» на кадрах кнопкой не нарисована, но статус «At the place» на них есть —
                без кнопки он недостижим, поэтому стоит мягкой строкой.
              */}
              {/* OF.22–OF.23d: кнопки дня встречи один на один — ровно по кадрам. */}
              {dayView ? (
                dayOff ? (
                  iCant ? null : hostIsMe(plan, me) ? (
                    /* OF.23d: затея снова открыта — ведём к тем, кто ещё свободен. */
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={openPicking}>
                      <Text style={s.ctaSoftText}>{OFD.reopenIntent()}</Text>
                    </Pressable>
                  ) : (
                    /* OF.C9: у гостя своей затеи не было — «Create your intent». */
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => router.navigate('/buddy')}>
                      <Text style={s.ctaSoftText}>{OFB.createIntent()}</Text>
                    </Pressable>
                  )
                ) : nobody ? (
                  /* O.23c: никто не вошёл — «It didn't happen» открывает вопрос о причине (O.24a). */
                  <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => { setReasonPick('no_show'); setReasonOpen(true); }}>
                    <Text style={s.ctaSoftText}>{OFD.didntHappen()}</Text>
                  </Pressable>
                ) : closedNow ? (
                  /* OF.23c / HY.23c: место закрыто — «It didn't happen» открывает вопрос о причине (OF.24a). */
                  <>
                    {hybrid ? (
                      <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={openChat}>
                        <Text style={s.ctaSoftText}>{OFD.openChat()}</Text>
                      </Pressable>
                    ) : null}
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => { setReasonPick('place_closed'); setReasonOpen(true); }}>
                      <Text style={s.ctaSoftText}>{OFD.didntHappen()}</Text>
                    </Pressable>
                  </>
                ) : phase === 'soon' ? (
                  myLive === 'late' ? (
                    <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                      <Text style={s.ctaText}>{OFD.openChat()}</Text>
                    </Pressable>
                  ) : (
                    <>
                      <Pressable accessibilityRole="button" style={hyDay && iOnCall ? s.cta : s.ctaSoft} onPress={openChat}>
                        <Text style={hyDay && iOnCall ? s.ctaText : s.ctaSoftText}>{OFD.openChat()}</Text>
                      </Pressable>
                      {/* HY.22 «Join the call instead» / HY.22e «Go in person after all»: сторона меняется без отмены. */}
                      {hyDay && !movedToCall ? (
                        <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => sendSide(iOnCall ? 'in_person' : 'call')}>
                          <Text style={s.ctaSoftText}>{iOnCall ? PLAN.goInPersonAfterAll() : PLAN.joinCallInstead()}</Text>
                        </Pressable>
                      ) : null}
                      {theirLive === 'late' || !offeredByServer('status') || (hyDay && iOnCall) ? null : (
                        <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setLateOpen(true)}>
                          <Text style={s.ctaSoftText}>{onlineCall ? OND.illBeLate() : PLAN.imLate()}</Text>
                        </Pressable>
                      )}
                    </>
                  )
                ) : (
                  <>
                    {/* HY.23: идёт сейчас — не успеваешь дойти, подключись; отменять не нужно. */}
                    {hyDay && !iOnCall ? (
                      <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => sendSide('call')}>
                        <Text style={s.ctaSoftText}>{PLAN.joinCallInstead()}</Text>
                      </Pressable>
                    ) : null}
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setDropping(true)}>
                      <Text style={s.ctaSoftText}>{PLAN.cantMakeIt()}</Text>
                    </Pressable>
                    {/* «Я на месте» на кадре OF.23 нет, но без неё недостижим OF.23c («At the place» у обоих).
                        Оставлена тихой кнопкой; решение — за владельцем (OPEN_TASKS). */}
                    {!onlineCall && !iOnCall && offeredByServer('status') && myLive !== 'here' ? (
                      <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => sendLive('here')}>
                        <Text style={s.ctaSoftText}>{PLAN.imHere()}</Text>
                      </Pressable>
                    ) : null}
                    {bothHere && !onlineCall && !movedToCall ? (
                      <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setSpotClosed(true)}>
                        <Text style={s.ctaSoftText}>{OFD.spotClosedBtn()}</Text>
                      </Pressable>
                    ) : null}
                  </>
                )
              ) : phase === 'soon' || phase === 'now' ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{PLAN.messageThem(other)}</Text>
                  </Pressable>

                  {/*
                    HY.23c — оба отметились «на месте», а место закрыто. Кадр описывает именно этот
                    момент: два человека у запертой двери, и у гибрида в отличие от встречи вживую
                    есть куда деться — ссылка уже открыта.

                    Кнопка появляется только когда оба и правда на месте: предлагать «уходим в
                    звонок» тому, кто ещё в дороге, значило бы звать его отменить свою же дорогу.
                    После перехода она исчезает — сервер отдаёт признак фактом.
                  */}
                  {hybrid && offeredByServer('move_to_call') && !movedToCall && myLive === 'here' && theirLive === 'here' ? (
                    <View style={s.infoBox}>
                      <Text style={s.closedTitle}>{PLAN.placeClosedTitle()}</Text>
                      <Text style={s.infoText}>{PLAN.placeClosedNote()}</Text>
                      <Pressable accessibilityRole="button" style={s.cta} onPress={moveToCall}>
                        <Text style={s.ctaText}>{PLAN.moveToCall()}</Text>
                      </Pressable>
                    </View>
                  ) : null}

                  {hybrid && movedToCall ? (
                    <View style={s.doneCard}>
                      <Text style={s.doneTitle}>{PLAN.movedToCallTitle()}</Text>
                      <Text style={s.doneSub}>{PLAN.movedToCallNote()}</Text>
                    </View>
                  ) : null}

                  {/* HY.22: за полчаса до начала гибрид даёт то, чего не даёт ни звонок, ни
                      встреча вживую, — уйти на другую сторону, не отменяя встречу. Кнопка
                      переключает в обе стороны: на кадре 22a рядом с «ушёл в звонок» стоит
                      «всё-таки приду живьём». */}
                  {/* После «уходим в звонок» кнопку не показываем: звать обратно к запертой
                      двери — единственное, чего в этот момент делать точно не надо. */}
                  {/* Без места сервер откажет NO_PLACE, и экран скажет об этом словами
                      (PLAN.sideNoPlace). Спрятать кнопку значит промолчать — у гибрида, где место
                      ещё не названо, «всё-таки приду живьём» не появилась бы вовсе. */}
                  {hybrid && !movedToCall ? (
                    <Pressable
                      accessibilityRole="button"
                      style={s.ctaDark}
                      onPress={() => sendSide(mySide === 'call' ? 'in_person' : 'call')}
                    >
                      <Text style={s.ctaDarkText}>
                        {mySide === 'call' ? PLAN.goInPersonAfterAll() : PLAN.joinCallInstead()}
                      </Text>
                    </Pressable>
                  ) : null}

                  {/* «Опаздываю» и «я на месте» — про ДОРОГУ, а не про режим встречи. Стояли на
                      «режим == offline», поэтому у гибрида их не было ни у кого: человек шёл к
                      столику и не мог ни предупредить об опоздании, ни отметиться на месте. А без
                      «на месте» недостижим и весь кадр HY.23c, который на этом и держится.
                      Показываем тому, кто идёт живьём: ушедшему в звонок отмечаться негде. */}
                  {offeredByServer('status') && comingInPerson && myLive !== 'late' && myLive !== 'here' && myLive !== 'cant_make_it' ? (
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => sendLive('late')}>
                      <Text style={s.ctaDarkText}>{PLAN.imLate()}</Text>
                    </Pressable>
                  ) : null}

                  {offeredByServer('status') && comingInPerson && myLive !== 'here' && myLive !== 'cant_make_it' ? (
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => sendLive('here')}>
                      <Text style={s.ctaSoftText}>{PLAN.imHere()}</Text>
                    </Pressable>
                  ) : null}

                  {/*
                    Через лист подтверждения, а не сразу. Отмена на сервере ТЕРМИНАЛЬНА: план уходит
                    в отменённые, и вернуть его нельзя — пара заводит новый. Здесь же кнопка стоит в
                    фазе звонка, когда человек торопится и жмёт не глядя, и один промах пальцем гасил
                    вечер необратимо. Сам лист был написан (кадр O.23b), но открывался только из
                    других фаз — сюда его просто не подключили.
                  */}
                  {myLive === 'cant_make_it' ? null : (
                    <Pressable
                      accessibilityRole="button"
                      style={offline ? s.ctaSoft : s.ctaDark}
                      onPress={() => setDropping(true)}
                    >
                      <Text style={offline ? s.ctaSoftText : s.ctaDarkText}>
                        {theirComingInPerson && theirLive === 'late' ? PLAN.cantWait() : PLAN.cantMakeIt()}
                      </Text>
                    </Pressable>
                  )}
                </>
              ) : null}

              {/* O.23a: моя отмена — записка «никто не ждёт» и чат. */}
              {phase === 'cancelled' && cancelledByMe && !leftFinal && !iCancelled ? (
                <>
                  <View style={s.infoBox}>
                    <Text style={s.infoText}>
                      {offline ? PLAN.nobodyWaitingOffline(other) : PLAN.nobodyWaiting(other)}
                    </Text>
                  </View>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{CHAT.openChat()}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* O.C4: отменили мне — объяснение уже стоит под заголовком, здесь только выходы. */}
              {/* OF.C6: организатор отменил — у гостя один выход: своя затея. */}
              {hostOff || (silentOff && !iHost) ? (
                <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.navigate('/buddy')}>
                  <Text style={s.ctaText}>{OFB.createIntent()}</Text>
                </Pressable>
              ) : null}

              {phase === 'cancelled' && !cancelledByMe && !leftFinal && !hostOff && !silentOff ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={startNewPlan}>
                    <Text style={s.ctaText}>{PLAN.suggestAnother()}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={openChat}>
                    <Text style={s.ctaSoftText}>{CHAT.openChat()}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* Кнопка ДЕЙСТВИЯ и должна называться действием: здесь стояло «Подтверждено» —
                  состояние, а не то, что случится по нажатию. */}
              {phase === 'confirmed' && !myConfirmed(plan, me) ? (
                <Pressable accessibilityRole="button" style={s.cta} onPress={() => respond('confirm')}>
                  <Text style={s.ctaText}>{PLAN.confirmAction()}</Text>
                </Pressable>
              ) : null}
            </>
          )}
        </ScrollView>

        {/* OF.21a — «предложить другое время» листом: быстрые сдвиги и своё «чч:мм» в тот же день. */}
        {/* Единственный лист с полями ввода — цифровая клавиатура закрывала «Отправить новое время». */}
        <Sheet
          visible={countering}
          onClose={() => setCountering(false)}
          title={nl && phase === 'confirmed' && plan?.host && isMe(plan.host, plan.host_id, me) ? OFB.changeTimeTitle() : PLAN.suggestSheetTitle()}
          bottomInset={Math.max(insets.bottom, 18)}   /* клавиатуру прибавляет сам лист */
        >
            {nl ? (
              /* OF.C3a / OF.21a / OF.C5a: «Instead of Thu 23 July,» — дни вокруг дня плана, время вокруг его часа. */
              <>
                <Text style={[s.sheetLead, { fontFamily: labelFamily(lang) }]}>{OFB.insteadOfDay(dOf(plan?.starts_at))}</Text>
                <Text style={s.sheetLabel}>{OFB.date()}</Text>
                <View style={s.chipRowWrap}>
                  {[-1, 0, 1, 2].filter((k) => plan?.starts_at && (plan.starts_at + k * 86400) * 1000 > Date.now() - 86400000).map((k) => {
                    const on = sugDay === k;
                    const d = new Date((plan.starts_at + k * 86400) * 1000);
                    const wd = d.toLocaleDateString(dateLocale(), { weekday: 'short' }).replace(/\.$/, '');
                    return (
                      <Pressable key={k} accessibilityRole="button" accessibilityState={{ selected: on }}
                                 style={[s.chip, on && s.chipOn]} onPress={() => setSugDay(k)}>
                        <Text style={[s.chipText, on && { color: color.onPrimary }]}>{`${wd.charAt(0).toUpperCase() + wd.slice(1)} ${d.getDate()}`}</Text>
                      </Pressable>
                    );
                  })}
                </View>
                <Text style={s.sheetLabel}>{OFB.time()}</Text>
              </>
            ) : (
              <Text style={s.note}>{PLAN.insteadOf(tOf(plan?.starts_at, ru))}</Text>
            )}
            <View style={s.chipRowWrap}>
              {(nl ? [-30, 30, 60] : [60, 90, 120, 150]).map((d) => {
                const on = sugDelta === d;
                const label = plan?.starts_at
                  ? tOf(plan.starts_at + d * 60, ru)
                  : `+${d}`;
                return (
                  <Pressable
                    key={d}
                    accessibilityRole="button"
                    accessibilityState={{ selected: on }}
                    style={[s.chip, on && s.chipOn]}
                    onPress={() => { timeTouched.current = true; setSugDelta(d); }}
                  >
                    <Text style={[s.chipText, on && { color: color.onPrimary }]}>{label}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={s.note}>{nl ? OFB.orSetYour() : PLAN.orSetYour()}</Text>
            <View style={s.hmRow}>
              {/*
                ПОЛЕ ОБЯЗАНО ПОКАЗЫВАТЬ ТО, ЧТО УЙДЁТ. Здесь стояла только чистка от нецифр и обрез
                до двух знаков, а диапазон не проверялся вовсе — «68» спокойно вводилось и
                оставалось на экране. При отправке `sendCounter` тихо зажимал его в 23
                (`Math.min(23, …)`), и человек отправлял 23:02, глядя на 68:02. Снято с телефона
                7 сентября 2026.
                Молчаливая правка хуже отказа: о ней не узнают. Нормализуем при уходе из поля тем
                же `normalizeTimePart`, которым живёт WhenPicker, и ПЕРЕПИСЫВАЕМ текст — на экране
                сразу видно принятое значение.
              */}
              <TextInput
                style={s.hmBox}
                value={sugH}
                onChangeText={(t) => { setSugH(t.replace(/\D/g, '').slice(0, 2)); setSugDelta(null); }}
                onBlur={() => setSugH((t) => (t.trim() ? normalizeTimePart(t, 'hours', 0).text : t))}
                placeholder="19"
                placeholderTextColor={color.neutral400}
                keyboardType="number-pad"
                accessibilityLabel={T('Часы', 'Hours', 'Horas')}
              />
              <Text style={s.hmColon}>:</Text>
              <TextInput
                style={s.hmBox}
                value={sugM}
                onChangeText={(t) => { setSugM(t.replace(/\D/g, '').slice(0, 2)); setSugDelta(null); }}
                onBlur={() => setSugM((t) => (t.trim() ? normalizeTimePart(t, 'minutes', 0).text : t))}
                placeholder="45"
                placeholderTextColor={color.neutral400}
                keyboardType="number-pad"
                accessibilityLabel={T('Минуты', 'Minutes', 'Minutos')}
              />
            </View>
            {placeLike ? (
              /* Место: район плана; «Change place» открывает поле — сервер принимает район во встречном. */
              <>
                <Text style={s.sheetLabel}>{OFB.place()}</Text>
                {sugPlaceOpen ? (
                  <TextInput style={s.input} value={sugPlace} onChangeText={setSugPlace} placeholder={OFB.placePh()}
                             placeholderTextColor={color.neutral400} autoFocus />
                ) : (
                  <View style={s.metaRow}>
                    <IconPin size={18} c={color.primary} />
                    <Text style={s.metaText}>{plan?.district || placeLabel || '—'}</Text>
                  </View>
                )}
              </>
            ) : onlineCall ? (
              /* O.C3a / O.21a / O.C5a: «Link» — чья ссылка; поле открывают «Change the link» и «Host the call myself». */
              <>
                <Text style={s.sheetLabel}>{ONB.link()}</Text>
                {sugPlaceOpen ? (
                  <TextInput style={s.input} value={sugPlace} onChangeText={setSugPlace} placeholder={ONB.linkPh()}
                             placeholderTextColor={color.neutral400} autoCapitalize="none" autoCorrect={false}
                             keyboardType="url" autoFocus />
                ) : (
                  <View style={s.metaRow}>
                    <IconVideo size={18} c={color.primary} />
                    <Text style={s.metaText}>{linkMine ? ONB.yourLink(svc) : ONB.theirLink(other)}</Text>
                  </View>
                )}
              </>
            ) : (
              <Text style={s.note}>{PLAN.suggestSheetNote(other)}</Text>
            )}
            <Pressable accessibilityRole="button" style={s.cta} onPress={sendCounter}>
              <Text style={s.ctaText}>{
                !nl ? PLAN.sendNewTime()
                : phase === 'confirmed' && plan?.host && isMe(plan.host, plan.host_id, me) ? OFB.sendUpdate()
                : OFB.sendTo(other)}</Text>
            </Pressable>
            {placeLike && !sugPlaceOpen ? (
              <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => { setSugPlace(String(plan?.district || '')); setSugPlaceOpen(true); }}>
                <Text style={s.ctaDarkText}>{hybrid ? HYB.changePlaceOrLink() : OFB.changePlace()}</Text>
              </Pressable>
            ) : onlineCall && !sugPlaceOpen && !locked ? (
              <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => { setSugPlace(''); setSugPlaceOpen(true); }}>
                <Text style={s.ctaDarkText}>{linkMine ? ONB.changeLink() : ONB.hostMyself()}</Text>
              </Pressable>
            ) : null}
            <Pressable accessibilityRole="button" style={nl ? s.sheetGhost : s.ctaDark} onPress={() => { setCountering(false); setSugPlaceOpen(false); }}>
              <Text style={nl ? s.sheetGhostText : s.ctaDarkText}>{DETAILS.cancel()}</Text>
            </Pressable>
        </Sheet>

        {/* Подтверждение отмены. Называет последствие словами: встреча гаснет для обоих и
            восстановить её нельзя — только назначить новую. */}
        {/*
          ДВА РАЗНЫХ ЛИСТА НА ОДНУ КНОПКУ, потому что сервер делает два разных дела. До замка
          «не смогу» — отмена: план гаснет для обоих, вернуть нельзя. Внутри двух часов до встречи
          сервер встречу НЕ отменяет (спека OF: «остаётся только „I can't make it“ — оно встречу
          не отменяет») и лишь ставит живой статус «не придёт». Лист при этом обещал отмену и
          «вернуть нельзя» — то есть врал ровно тому, кто уже едет.
        */}
        {/* OF.20c «Fix the plan»: все версии из журнала раундов, новые сверху; выбранная — с галочкой. */}
        <Sheet visible={fixing} onClose={() => setFixing(false)} title={OFB.fixPlan()}>
          <Text style={s.sheetLabel}>{OFB.pickFinal()}</Text>
          {roundsLog.map((r: any) => {
            const n = Number(r.round);
            const on = fixRound === n;
            const mineR = isMe(String(r.by || ''), r.by_id, me);
            return (
              <Pressable key={n} accessibilityRole="radio" accessibilityState={{ selected: on }}
                         style={[s.fixRow, on && s.fixRowOn]} onPress={() => setFixRound(n)}>
                <View style={s.fixWhen}>
                  <Text style={s.fixTime}>{tOf(r.starts_at, ru)}</Text>
                  <Text style={s.fixDate}>{dOf(r.starts_at)}</Text>
                </View>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={s.fixWho} numberOfLines={1}>{mineR ? OFB.yourPlan() : OFB.theirSuggestion(String(r.by || other))}</Text>
                  {r.district ? (
                    <View style={s.metaRow}>
                      <IconPin size={16} c={color.primary} />
                      <Text style={s.metaText} numberOfLines={1}>{r.district}</Text>
                    </View>
                  ) : null}
                </View>
                <View style={{ alignItems: 'flex-end', gap: 6 }}>
                  <View style={s.fixBadge}><Text style={s.fixBadgeText}>{OFB.roundLabel(n)}</Text></View>
                  {on ? <IconCheck size={20} c={color.primary} /> : null}
                </View>
              </Pressable>
            );
          })}
          <Text style={s.note}>{OFB.fixNote(other)}</Text>
          <Pressable accessibilityRole="button" style={[s.cta, fixRound == null && { opacity: 0.5 }]} disabled={fixRound == null} onPress={doFix}>
            <Text style={s.ctaText}>{OFB.fixThis()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.sheetInk} onPress={() => setFixing(false)}>
            <Text style={s.sheetInkText}>{OFB.back()}</Text>
          </Pressable>
        </Sheet>

        {/* OF.22c — «Tell Marta you're running late?»: на сколько. Ничего не отменяется. */}
        <Sheet visible={lateOpen} onClose={() => setLateOpen(false)} title={onlineCall ? OND.lateAsk(other) : OFD.lateAsk(other)}>
          <Text style={[s.sheetLead, { fontFamily: labelFamily(lang) }]}>{PLAN.startsIn(minutesToStart(plan))}</Text>
          <Text style={s.note}>{hybrid ? HYB.lateAskNote(other) : OFD.lateAskNote(other)}</Text>
          <Text style={[s.sheetLead, { fontFamily: labelFamily(lang) }]}>{OFD.howLate()}</Text>
          <View style={s.lateChips}>
            {(onlineCall ? [5, 10, 15, 20] : [10, 20, 30, 45]).map((m) => (
              <Pressable key={m} accessibilityRole="radio" accessibilityState={{ selected: lateMin === m }}
                         onPress={() => setLateMin(m)} style={[s.lateChip, lateMin === m && s.lateChipOn]}>
                <Text style={[s.lateChipText, lateMin === m && s.lateChipTextOn]}>{OFD.mins(m)}</Text>
              </Pressable>
            ))}
          </View>
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => { setLateOpen(false); sendLive('late', lateMin); }}>
            <Text style={s.ctaText}>{OFD.tell(other)}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.sheetInk} onPress={() => setLateOpen(false)}>
            <Text style={s.sheetInkText}>{OFD.neverMind()}</Text>
          </Pressable>
        </Sheet>

        <Sheet visible={dropping} onClose={() => setDropping(false)}
               title={locked ? (nl ? OFD.cantAsk(other) : PLAN.cantMakeAsk(other)) : nl ? (iHost ? OFB.cancelPlan() : onlineCall ? ONB.leaveAsk() : OFB.leaveAsk()) : PLAN.callOffAsk(other)}>
          {nl && locked ? (
            /* OF.23b / O.23b — «не смогу» в день встречи: один на один это отмена, и вернуть её нельзя. */
            <>
              <Text style={[s.sheetLead, { fontFamily: labelFamily(lang) }]}>
                {phase === 'now' ? (onlineCall ? OND.cantLead() : OFD.cantLead()) : OFD.cantLeadSoon(minutesToStart(plan))}
              </Text>
              <Text style={s.note}>{onlineCall ? OND.cantNote(other) : hybrid ? HYB.cantNote(other) : OFD.cantNote(other)}</Text>
              <Pressable accessibilityRole="button" style={s.cta} onPress={confirmDrop}>
                <Text style={s.ctaText}>{OFD.cantYes()}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={s.sheetInk} onPress={() => setDropping(false)}>
                <Text style={s.sheetInkText}>{OFD.neverMind()}</Text>
              </Pressable>
            </>
          ) : nl && !locked ? (
            /* OF.21d — организатор отменяет; OF.C5b — гость выходит. Оба без последствий. */
            <>
              <Text style={[s.sheetLead, { fontFamily: labelFamily(lang) }]}>{iHost ? (onlineCall ? ONB.cancelAsk() : OFB.cancelAsk()) : OFB.cantUndo()}</Text>
              <Text style={s.note}>{iHost ? OFB.cancelNote(other) : OFB.leaveNote(other)}</Text>
              <Pressable accessibilityRole="button" style={s.cta} onPress={confirmDrop}>
                <Text style={s.ctaText}>{iHost ? OFB.cancelPlan() : OFB.leavePlan()}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={s.sheetInk} onPress={() => setDropping(false)}>
                <Text style={s.sheetInkText}>{iHost ? OFB.keepIt() : OFB.stay()}</Text>
              </Pressable>
            </>
          ) : (
            <>
              {/* HY.23b: у гибрида рядом стоит «уйду в звонок», и «не смогу» легко прочесть как
                  смену стороны. Кадр требует сказать разницу вслух — иначе человек отменяет встречу,
                  думая, что просто меняет вход. */}
              <Text style={s.note}>
                {locked ? PLAN.cantMakeNote(other) : hybrid ? PLAN.callOffNoteHybrid(other) : PLAN.callOffNote(other)}
              </Text>
              <Pressable
                accessibilityRole="button"
                style={s.ctaDark}
                onPress={confirmDrop}
              >
                <Text style={s.ctaDarkText}>{locked ? PLAN.cantMakeYes() : PLAN.callOffYes()}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setDropping(false)}>
                <Text style={s.ctaSoftText}>{PLAN.callOffNo()}</Text>
              </Pressable>
            </>
          )}
        </Sheet>

        {/* OF.24a — «не состоялась»: что случилось. Ответ другим не показывается; «Пропустить»
            отправляет «нет» без причины, крестик не отправляет ничего. */}
        {/* OF.24a — причина у встречи вживую один на один: строки с галочкой, как на кадре. */}
        <Sheet visible={reasonOpen && nl} onClose={() => setReasonOpen(false)} title={PLAN.whatHappened()}>
          <Text style={[s.sheetLead, { fontFamily: labelFamily(lang) }]}>{OFD.reasonLead(other)}</Text>
          <View style={s.whyList}>
            {([
              ['no_show', onlineCall ? OND.reasonNoJoin(other) : hybrid ? HYB.reasonNoShow(other) : PLAN.reasonNoShow(other)],
              ['couldnt_make', PLAN.reasonCouldnt()],
              ['moved', PLAN.reasonMoved()],
              onlineCall ? ['link_broken', OND.reasonLink()] : hybrid ? ['place_closed', HYB.reasonBroken()] : ['place_closed', OFD.reasonSpot()],
              ['other', PLAN.reasonOther()],
            ] as [string, string][]).map(([k, label]) => (
              <Pressable key={k} accessibilityRole="radio" accessibilityState={{ selected: reasonPick === k }}
                         onPress={() => setReasonPick(k)} style={[s.whyRow, reasonPick === k && s.whyRowOn]}>
                <Text style={s.whyText}>{label}</Text>
                {reasonPick === k ? <IconCheck /> : null}
              </Pressable>
            ))}
          </View>
          <Text style={s.note}>{OFD.reasonCaption()}</Text>
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => sendDidnt(true)}>
            <Text style={s.ctaText}>{PLAN.send()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.sheetInk} onPress={() => sendDidnt(false)}>
            <Text style={s.sheetInkText}>{OFD.skip()}</Text>
          </Pressable>
        </Sheet>

        {/* OF.25 — «How was it?»: оценка необязательна, видит её только Kleal. */}
        <Sheet visible={rateOpen} onClose={() => setRateOpen(false)} title={OFD.howWas()}>
          <Text style={[s.sheetLead, { fontFamily: labelFamily(lang) }]}>{OFD.howWasLead()}</Text>
          <View style={s.lateChips}>
            {RATINGS.map(([k, label]) => (
              <Pressable key={k} accessibilityRole="radio" accessibilityState={{ selected: rating === k }}
                         onPress={() => setRating(rating === k ? '' : k)} style={[s.lateChip, { flex: 1, paddingHorizontal: 6 }, rating === k && s.lateChipOn]}>
                <Text style={[s.lateChipText, rating === k && s.lateChipTextOn]} numberOfLines={1}>
                  {k === 'great' ? '😄 ' : k === 'fine' ? '🙂 ' : '😕 '}{label()}
                </Text>
              </Pressable>
            ))}
          </View>
          {hybrid ? (
            /* HY.25: у гибрида два входа — какой сработал, это подсказка агенту на следующий раз, не оценка. */
            <>
              <Text style={[s.sheetLead, { fontFamily: labelFamily(lang) }]}>{HYB.howMet()}</Text>
              <View style={s.lateChips}>
                {([['in_person', HYB.howInPerson()], ['call', HYB.howCall()], ['both', HYB.howBoth()]] as ['in_person' | 'call' | 'both', string][]).map(([k, label]) => (
                  <Pressable key={k} accessibilityRole="radio" accessibilityState={{ selected: howMet === k }}
                             onPress={() => setHowMet(howMet === k ? '' : k)}
                             style={[s.lateChip, { flex: 1, paddingHorizontal: 6 }, howMet === k && s.lateChipOn]}>
                    <Text style={[s.lateChipText, howMet === k && s.lateChipTextOn]} numberOfLines={1}>{label}</Text>
                  </Pressable>
                ))}
              </View>
            </>
          ) : null}
          <Text style={s.note}>{hybrid ? HYB.howNote() : OFD.howWasNote()}</Text>
          <Pressable accessibilityRole="button" style={s.cta}
                     onPress={() => { setRateOpen(false); if (rating || howMet) sendRating(); }}>
            <Text style={s.ctaText}>{PLAN.send()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.sheetInk}
                     onPress={() => { setRateOpen(false); setTimeout(openReport, 250); }}>
            <Text style={s.sheetInkText}>{PLAN.reportProblem()}</Text>
          </Pressable>
        </Sheet>

        <Sheet visible={reasonOpen && !nl} onClose={() => setReasonOpen(false)} title={PLAN.whatHappened()}>
          <Text style={s.note}>{PLAN.whatHappenedNote()}</Text>
          {/* Список зависит от РЕЖИМА встречи: у звонка не бывает закрытого места, а у встречи
              вживую — несработавшей ссылки. Раньше он был жёстко офлайновым, и человеку после
              сорвавшегося звонка предлагали сослаться на «закрытое место». */}
          {([
            ['no_show', PLAN.reasonNoShow(other)],
            ['couldnt_make', PLAN.reasonCouldnt()],
            ...(wantsLink ? [['link_failed', PLAN.reasonLink()]] : []),
            ...(wantsPlace ? [['place_closed', PLAN.reasonClosed()]] : []),
            ['moved', PLAN.reasonMoved()],
            ['other', PLAN.reasonOther()],
          ] as [string, string][]).map(([k, label]) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              accessibilityState={{ selected: reasonPick === k }}
              style={s.reasonRow}
              onPress={() => setReasonPick(k)}
            >
              <View style={[s.radio, reasonPick === k && s.radioOn]} />
              <Text style={s.reasonText}>{label}</Text>
            </Pressable>
          ))}
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => sendDidnt(true)}>
            <Text style={s.ctaText}>{PLAN.send()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => sendDidnt(false)}>
            <Text style={s.ctaDarkText}>{PLAN.skip()}</Text>
          </Pressable>
        </Sheet>

        {/* С открытой клавиатурой панель не нужна: она всплывала над клавишами и закрывала поле ссылки
            и строку участника (стенд, 11.10). */}
        {kbUp ? null : (
          <View style={s.navFloat} pointerEvents="box-none">
            <BottomNav />
          </View>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

/** Ответил ли я сам про факт встречи. undefined — ещё нет.
 *  Читаем `my_feedback`: сервер отдаёт наружу только МОЮ строку отзыва, чужая не покидает сервер. */
function myAnswer(plan: any): boolean | undefined {
  const row = plan?.my_feedback;
  if (!row || row.happened === undefined || row.happened === null) return undefined;
  return !!row.happened;
}

/** Оценку я уже отправил. Держим это по серверу, а не по локальному флагу: иначе после обновления
 *  экрана форма оценки просилась бы во второй раз, хотя оценка уже записана. */
function myRated(plan: any): boolean {
  const row = plan?.my_feedback;
  return !!(row && (row.rating || row.text));
}

function myConfirmed(plan: any, me: string): boolean {
  return (plan?.participants || []).some(
    (p: any) => isMe(p.name, pidOf(p, 'name'), me) && p.confirmed
  );
}

/** «Sun 20:00» — день недели и час для срока ответа. */
function replyWhen(at: number, ru: boolean): string {
  const d = new Date(at * 1000);
  const wd = new Intl.DateTimeFormat(dateLocale(), { weekday: 'short' }).format(d);
  return `${wd.charAt(0).toUpperCase()}${wd.slice(1)} ${tOf(at, ru)}`;
}

/** Встреча вживую по доске «1:1 · Offline — new layout» (разделы B/C): ожидание, перенос, подтверждено. */
const offlineBoard = (plan: any, phase: string) =>
  // Звонок один на один идёт по тем же раундам (борд «1:1 · Online — new layout», разделы B/C).
  // …и гибрид (борд «1:1 · Hybrid — new layout»): место и ссылка сразу, сторону каждый выбирает сам.
  (plan?.mode === 'offline' || plan?.mode === 'online' || plan?.mode === 'hybrid') && (phase === 'waiting' || phase === 'confirmed');

/** Роль того, кто отменил план: по id участника, без него — по подписи. */
function cancellerRole(plan: any): string {
  const by = String(plan?.cancelled_by || '').trim().toLowerCase();
  const byId = String(plan?.cancelled_by_id || '');
  const row = (plan?.participants || []).find((x: any) =>
    byId && pidOf(x, 'name') ? pidOf(x, 'name') === byId : String(x?.name || '').trim().toLowerCase() === by);
  return String(row?.role || '');
}
/** Гость вышел: из закреплённого плана (left_final) или отказался от офлайн-плана (OF.C5b). */
function guestLeft(plan: any, phase: string | null): boolean {
  if (phase !== 'cancelled') return false;
  if (plan?.cancel_kind === 'left_final') return true;
  return !!plan?.mode && cancellerRole(plan) === 'guest';
}
/** План закрыло молчание до подтверждения (6 ч на ход): `cancel_kind: expired_no_answer`. */
function silentClosed(plan: any, phase: string | null): boolean {
  return phase === 'cancelled' && plan?.cancel_kind === 'expired_no_answer';
}
/** Промолчал ли этот участник: по id, без него — по подписи. */
function isSilent(plan: any, p: any): boolean {
  const id = String(plan?.expired_silent_id || ''), pid = pidOf(p, 'name');
  if (id && pid) return id === pid;
  return String(p?.name || '').trim().toLowerCase() === String(plan?.expired_silent || '').trim().toLowerCase();
}
function iWasSilent(plan: any): boolean {
  const meRow = (plan?.participants || []).find((x: any) => x?.is_me);
  return !!meRow && isSilent(plan, meRow);
}

/** OF.21d → OF.C6: офлайн-план отменил организатор. */
function hostCancelled(plan: any, phase: string | null): boolean {
  return phase === 'cancelled' && !!plan?.mode && plan?.cancel_kind !== 'left_final' && cancellerRole(plan) === 'host';
}

/** Хозяин плана — я? По роли в участниках; старые ответы без ролей — по `host`. */
function hostIsMe(plan: any, me: string): boolean {
  const parts = Array.isArray(plan?.participants) ? plan.participants : [];
  if (parts.some((x: any) => x?.role)) return parts.some((x: any) => x?.is_me && x?.role === 'host');
  return !!plan?.host && isMe(plan.host, plan.host_id, me);
}

function headline(phase: string, other: string, plan: any, me: string, ru: boolean): string {
  if (silentClosed(plan, phase)) return iWasSilent(plan) ? OFB.youSilentTitle() : OFB.silentTitle(other);
  if (hostCancelled(plan, phase)) return hostIsMe(plan, me) ? OFB.youCancelledTitle() : OFB.hostCancelledTitle();
  if (guestLeft(plan, phase)) {
    return isMe(String(plan?.cancelled_by || ''), plan?.cancelled_by_id, me) ? OFB.youLeftTitle() : OFB.leftTitle(other);
  }
  if (offlineBoard(plan, phase)) {
    if (plan?.final_by_host && phase === 'waiting') return hostIsMe(plan, me) ? OFB.fixedWaitTitle(other) : OFB.fixedTitle(other);
    // До подтверждения встречное время — это раунд (OF.20b/OF.C3b), после — перенос (OF.21b/OF.C5).
    if (plan?.pending && phase === 'waiting') return plan.pending.mine ? OFB.youSuggested(tOf(plan.pending.starts_at, ru)) : OFB.suggestedChange(other);
    if (plan?.pending) return plan.pending.mine ? OFB.updateSentTitle() : PLAN.suggestsTime(other, tOf(plan.pending.starts_at, ru));
    if (phase === 'waiting') return myConfirmed(plan, me) ? OFB.waitingTitle(other) : OFB.proposedTitle(other);
    if (plan?.mode === 'hybrid') {
      // HY.21 / HY.C3c: оба входа названы и никто не менял сторону. Смена стороны и недостающий вход —
      // свои заголовки ниже (HY.22e / 22f, HY.21e–21g).
      if (plan?.place_set && plan?.link_set && plan?.my_side !== 'call' && plan?.their_side !== 'call') {
        return hostIsMe(plan, me) ? HYB.confirmedBoth() : OFB.confirmedTitle();
      }
    } else if (plan?.mode === 'online' ? plan?.link_set : plan?.address_set) return OFB.confirmedTitle();
  }
  // O.21b/O.C5 важнее всего остального в шапке: пока висит встречное время, экран говорит о нём.
  if ((phase === 'waiting' || phase === 'confirmed') && plan?.pending) {
    return plan.pending.mine
      ? PLAN.newTimeSent(other)
      : PLAN.suggestsTime(other, tOf(plan.pending.starts_at, ru));
  }
  // O.C3: план прислали мне — экран зовёт подтвердить, а не сообщает «отправлено».
  if (phase === 'waiting' && !myConfirmed(plan, me)) return PLAN.sentPlan(other);
  // O.20a: согласовано, а звонку негде пройти — экран первым делом просит ссылку.
  if (phase === 'confirmed' && plan?.mode === 'online' && !plan?.link_set && !plan?.address_set) {
    return PLAN.addLinkTitle();
  }
  // OF.20a: то же для офлайна — согласовано, а места нет.
  if (phase === 'confirmed' && plan?.mode === 'offline' && !plan?.place_set && !plan?.address_set) {
    return PLAN.pickPlaceTitle();
  }
  // HY.20a/20b/20c: у гибрида не хватать может каждого входа ПО ОТДЕЛЬНОСТИ, и это три разных
  // кадра. Раньше сюда не попадала ни одна ветка — гибрид не «online» и не «offline», — поэтому
  // экран согласованного гибрида без места и без ссылки говорил просто «Подтверждено».
  if (phase === 'confirmed' && plan?.mode === 'hybrid') {
    const hasPlace = !!plan?.place_set, hasLink = !!plan?.link_set;
    if (!hasPlace && !hasLink) return PLAN.addBothTitle();
    if (!hasLink) return PLAN.addLinkTitle();
    if (!hasPlace) return HYB.needPlaceTitle();
  }
  // HY.22a/HY.22b/HY.C4: смена стороны — новость этого экрана, и она важнее счётчика: она
  // отвечает на вопрос «где меня ждать». Своя смена и чужая читаются по-разному, поэтому это две
  // разные строки, а не одна про «кто-то ушёл в звонок».
  if (plan?.mode === 'hybrid' && (phase === 'confirmed' || phase === 'soon' || phase === 'now')) {
    // Сначала общий случай: если в звонке ОБА, ни «ты ушёл», ни «она ушла» уже не правда.
    if (plan?.my_side === 'call' && plan?.their_side === 'call') return PLAN.sideBothCallTitle();
    if (plan?.my_side === 'call') return HYB.youCallTitle();
    if (plan?.their_side === 'call') return HYB.theyCallTitle(other);
  }
  // OF.22a/OF.C4: опоздание перекрывает счётчик — оно и есть новость этого экрана. Но только
  // когда встреча на носу: за восемь часов до неё «опаздывает» ничего не значит.
  if (phase === 'soon' || phase === 'now') {
    // «Не смогу» внутри замка — живой статус, не отмена: план стоит, и это главная новость экрана.
    if (String(plan?.my_live?.status || '') === 'cant_make_it') return PLAN.youToldCantMake(other);
    if (String(plan?.their_live?.status || '') === 'cant_make_it') return PLAN.theyCantMake(other);
    if (String(plan?.my_live?.status || '') === 'late') return PLAN.lateKnows(other);
    if (String(plan?.their_live?.status || '') === 'late') return PLAN.theyLate(other);
  }
  // OF.23: у офлайна «сейчас» — это встреча, а не звонок.
  if (phase === 'now' && plan?.mode === 'offline') return PLAN.meetupNow();
  switch (phase) {
    case 'waiting': return CHAT.sentTo(other);
    case 'confirmed': return PLAN.confirmed();
    case 'soon': return PLAN.startsIn(minutesToStart(plan));
    case 'now': return PLAN.startsNow();
    // O.24 и O.25 — это один экран в двух состояниях, и заголовок должен показывать, на каком
    // вопросе мы стоим: сперва «состоялась ли», потом «как прошло», потом благодарность.
    case 'after': {
      const mine = myAnswer(plan);
      if (mine === undefined) return PLAN.didItHappen();
      if (mine === true && !myRated(plan)) return PLAN.howWasIt();
      // Ответ записан — дальше это уже не опрос, а запись о прошедшей встрече, и заголовок
      // называет ЕЁ, а не благодарность за анкету. «Спасибо» остаётся мгновением сразу после
      // отправки (состояние `thanks`), но не заголовком того, что человек открыл из истории.
      if (plan?.outcome?.happened === false) return PLAN.didntHappenTitle();
      // Ответы разошлись — утверждать «состоялась» нельзя, но встреча всё равно позади.
      if (mine === false) return PLAN.pastOver();
      return PLAN.pastHappened();
    }
    // O.23a: у отмены есть автор, и заголовок называет его. Старые планы без cancelled_by
    // остаются с безличной строкой — выдумывать автора не из чего.
    case 'cancelled': {
      const by = String(plan?.cancelled_by || '').trim().toLowerCase();
      if (!by) return T('Встреча отменена', 'The meetup is off', 'La quedada está cancelada');
      return isMe(by, plan?.cancelled_by_id, me)
        ? PLAN.youToldCantMake(other)
        : PLAN.theyCantMake(other);
    }
    default: return '';
  }
}

function subline(phase: string, other: string, plan: any, ru: boolean, me: string): string {
  if (silentClosed(plan, phase)) return iWasSilent(plan) ? OFB.youSilentNote() : hostIsMe(plan, me) ? OFB.silentHostNote() : OFB.silentGuestNote();
  if (hostCancelled(plan, phase)) {
    return hostIsMe(plan, me) ? OFB.youCancelledNote()
      : plan?.mode === 'online' ? ONB.hostCancelledNote(other) : OFB.hostCancelledNote(other);
  }
  if (guestLeft(plan, phase)) {
    return isMe(String(plan?.cancelled_by || ''), plan?.cancelled_by_id, me) ? OFB.youLeftNote(other) : OFB.leftNote();
  }
  if (offlineBoard(plan, phase)) {
    if (plan?.final_by_host && phase === 'waiting') return hostIsMe(plan, me) ? OFB.fixedWaitNote(other) : OFB.fixedNote();
    if (plan?.pending && phase === 'waiting') {
      const r = Number(plan.round) || 0, mx = Number(plan.max_rounds) || 0;
      return plan.pending.mine
        ? (mx && r >= mx ? OFB.youSuggestedLastNote(other, r, hostIsMe(plan, me)) : OFB.youSuggestedNote(other, r || undefined))
        : OFB.suggestedChangeNote(dOf(plan.pending.starts_at), tOf(plan.pending.starts_at, ru), tOf(plan.starts_at, ru), !!mx && r >= mx, plan?.mode === 'online', plan?.mode === 'hybrid');
    }
    if (plan?.pending) return plan.pending.mine ? OFB.updateSentNote(other, tOf(plan.starts_at, ru)) : OFB.suggestsNote(tOf(plan.starts_at, ru));
    if (phase === 'waiting') {
      return myConfirmed(plan, me) ? OFB.waitingNote(other)
        : plan?.mode === 'online' ? ONB.proposedNote() : plan?.mode === 'hybrid' ? HYB.proposedNote() : OFB.proposedNote();
    }
    if (plan?.mode === 'hybrid') {
      const g = String(((plan?.participants || []) as any[]).find((x) => !x?.is_me)?.gender || '');
      const opens = linkOpensAt(plan, ru);
      const place = String(plan?.place || plan?.address || plan?.district || '');
      const mine = String(plan?.my_side || ''), theirs = String(plan?.their_side || '');
      if (plan?.place_set && plan?.link_set) {
        if (mine === 'call' && theirs === 'call') return HYB.bothCallNote(opens);
        if (mine === 'call') return hostIsMe(plan, me) ? HYB.youCallNote(other, opens, g) : HYB.guestCallNote(other, tOf(plan.starts_at, ru), opens);
        if (theirs === 'call') return hostIsMe(plan, me) ? HYB.hostBothCallNote(other, opens) : HYB.theyCallNote(place, opens, g);
        return hostIsMe(plan, me) ? HYB.hostBothNote(other, g) : HYB.guestInPersonNote(other, tOf(plan.starts_at, ru), place);
      }
      // HY.21e / 21f / 21g: не хватает входа — что именно и почему это важно.
      const when = `${dOf(plan.starts_at)} ${tOf(plan.starts_at, ru)}`;
      if (!plan?.place_set && !plan?.link_set) return HYB.needBothNote();
      if (!plan?.link_set) return HYB.needLinkNote(when, place);
      return HYB.needPlaceNote(when);
    }
    // O.21 / O.C3c: у звонка вместо адреса — когда откроется ссылка.
    if (plan?.mode === 'online' && plan?.link_set) {
      const opens = linkOpensAt(plan, ru);
      return hostIsMe(plan, me) ? ONB.hostLinkNote(other, opens) : ONB.guestLinkNote(other, tOf(plan.starts_at, ru), opens);
    }
    if (plan?.address_set && plan?.address_visible_to_me) {
      const addr = String(plan.address || plan.place || '');
      const meHost = (plan.participants || []).some((x: any) => x?.is_me && x?.role === 'host');
      return meHost ? OFB.hostSpotNote(other, addr) : OFB.guestSpotNote(other, tOf(plan.starts_at, ru), addr);
    }
  }
  // Договорились обо всём — об этом ниже говорит зелёная плашка «Всё готово», и повторять её
  // подзаголовком незачем: одна и та же новость трижды на одном экране читается как шум.
  if (phase === 'confirmed' && plan?.address_set && !plan?.pending) return '';
  if ((phase === 'waiting' || phase === 'confirmed') && plan?.pending) {
    // O.21b и O.C5 объясняют одно правило, каждой стороне со своей стороны.
    return plan.pending.mine ? PLAN.newTimeNote(other) : PLAN.moveNote(other);
  }
  if (phase === 'waiting' && !myConfirmed(plan, me)) {
    return plan?.mode === 'offline' ? PLAN.sentPlanNoteOffline() : PLAN.sentPlanNote();
  }
  if (phase === 'confirmed' && plan?.mode === 'online' && !plan?.link_set && !plan?.address_set) {
    return PLAN.addLinkNote(planWhen(plan, ru), other);
  }
  if (plan?.mode === 'hybrid' && (phase === 'confirmed' || phase === 'soon' || phase === 'now')) {
    if (plan?.my_side === 'call' && plan?.their_side === 'call') return PLAN.sideBothCallNote(other);
    if (plan?.my_side === 'call') return PLAN.sideSwitchedNote(other);
    if (plan?.their_side === 'call') return PLAN.theySwitchedNote(other);
  }
  // HY.20a/20b/20c — подпись под заголовком гибрида. Она объясняет ровно то, чего не хватает, и
  // почему это важно: у гибрида недостающий вход отрезает не «часть удобства», а половину людей.
  if (phase === 'confirmed' && plan?.mode === 'hybrid') {
    const hasPlace = !!plan?.place_set, hasLink = !!plan?.link_set;
    if (!hasPlace && !hasLink) return PLAN.addBothNote();
    if (!hasLink) return PLAN.addLinkNote(planWhen(plan, ru), other);
    if (!hasPlace) return PLAN.pickPlaceNote(planWhen(plan, ru), other);
  }
  // Офлайн говорит про адрес и дорогу, онлайн — про ссылку.
  if (plan?.mode === 'offline') {
    if (phase === 'soon' || phase === 'now') {
      if (String(plan?.my_live?.status || '') === 'late') return PLAN.lateSentNote(other);
      if (String(plan?.their_live?.status || '') === 'late') return PLAN.theyLateNote(other);
    }
    // OF.20, вид отправителя: обещать «видит место и ссылку» у встречи вживую нельзя — второй
    // видит только район, пока не подтвердит (OF.C3).
    if (phase === 'waiting') return PLAN.sentNoteOffline(other);
    if (phase === 'confirmed' && !plan?.address_set) return PLAN.pickPlaceNote(planWhen(plan, ru), other);
    if (phase === 'confirmed') {
      return plan?.address_visible_to_me ? PLAN.addressOpenNote(other) : PLAN.addressAfterConfirm();
    }
    if (phase === 'soon') return PLAN.lateHint(other);
    if (phase === 'now') return '';
  }
  switch (phase) {
    case 'waiting': return CHAT.sentNote(other);
    case 'confirmed': return PLAN.linkOpensAt(linkOpensAt(plan, ru));
    case 'soon':
    // Подпись «сейчас». У гибрида она про оба входа, а не только про ссылку.
    case 'now': return plan?.mode === 'hybrid' && !plan?.moved_to_call
      ? PLAN.hybridNote() : PLAN.linkNote();
    case 'after': return '';
    case 'cancelled': {
      const by = String(plan?.cancelled_by || '').trim().toLowerCase();
      // Отменил я — записка «никто не ждёт» стоит ниже, в рамке; дублировать её здесь незачем.
      if (by && isMe(by, plan?.cancelled_by_id, me)) return '';
      // O.C4: отменили мне — объяснение стоит прямо под заголовком, как на кадре.
      if (by) return plan?.mode === 'offline' ? PLAN.toldYouNoteOffline(other) : PLAN.toldYouNote(other);
      return T('Время освободилось. Можно предложить другое.', 'The slot is free. You can suggest another time.', 'El hueco está libre. Puedes sugerir otra hora.');
    }
    default: return '';
  }
}

/**
 * Статус строки участника. Поверх обычного personStatus живут особые случаи:
 * O.21b/O.C5 — встречное время: у отправителя «ждёшь», у получателя «твой ход»;
 * O.C3      — план прислали мне: у подтвердившего «подтвердил · час», у меня «твой ход»;
 * O.23a/O.C4 — отмена: у автора «не сможет», у второго «узнал(а) только что» / «отвечать нечего».
 */
function statusFor(p: any, plan: any, phase: string, pendingChange: any, ru: boolean): string {
  const name = String(p?.name || '').trim().toLowerCase();
  // OF.20 / OF.C3 / OF.21b / OF.C5: статус строки по доске; у подтверждённого плана строк статуса нет (OF.21).
  if (silentClosed(plan, phase)) {
    if (isSilent(plan, p)) return OFB.stNoAnswer();
    return p?.role === 'host' && p?.is_me ? OFB.stIntentOpen() : '';
  }
  if (hostCancelled(plan, phase)) {
    if (p?.role === 'host') return OFB.stCancelled();
    return p?.confirmed ? OFB.stWasGoing() : '';
  }
  if (guestLeft(plan, phase)) {
    const pid = pidOf(p, 'name');
    const left = pid && plan?.cancelled_by_id ? pid === plan.cancelled_by_id : name === String(plan?.cancelled_by || '').trim().toLowerCase();
    if (left) return OFB.stLeft();
    return p?.role === 'host' && p?.is_me ? OFB.stIntentOpen() : '';
  }
  if (offlineBoard(plan, phase)) {
    if (plan?.final_by_host && phase === 'waiting') {
      if (p?.role === 'host') return OFB.stFixed();
      return p?.is_me ? OFB.stYourAnswer() : OFB.stNotAnswered();
    }
    if (pendingChange) {
      const byMe = !!pendingChange.mine;
      const isProposer = p?.is_me ? byMe : !byMe;
      if (phase === 'waiting') {
        // OF.20b: Marta «Confirmed · Suggested this», я «Your turn»; OF.C3b: я «Suggested this», он ещё не ответил.
        if (isProposer) return p?.is_me ? OFB.stSuggested() : OFB.stConfirmedSuggested();
        return p?.is_me ? OFB.stYourTurn() : OFB.stNotAnswered();
      }
      return isProposer ? OFB.stChanged() : p?.is_me ? OFB.stYourAnswer() : OFB.stNotAnswered();
    }
    if (phase === 'waiting') {
      if (p?.role === 'host') return OFB.stProposed();
      return p?.confirmed ? CHAT.confirmed() : p?.is_me ? OFB.stYourAnswer() : OFB.stNotAnswered();
    }
    // HY.21 / HY.C3c: у гибрида рядом с «Confirmed» стоит сторона, если человек её назвал.
    if (plan?.mode === 'hybrid' && p?.confirmed) {
      return p?.side === 'call' ? HYB.stOnCall() : p?.side === 'in_person' ? HYB.stInPerson() : CHAT.confirmed();
    }
    // OF.21 / OF.C3c: у подтверждённого плана оба — «Confirmed».
    return p?.confirmed ? CHAT.confirmed() : '';
  }
  // HY.21/HY.22a/HY.22b: у гибрида в строке участника стоит СТОРОНА — «придёт живьём» или
  // «будет на звонке». Без неё оба показывались одинаково «подтвердил(а)», и понять, кого ждать
  // за столиком, а кого в звонке, было неоткуда.
  const side = String(p?.side || '');
  if (plan?.mode === 'hybrid' && side && phase !== 'cancelled' && phase !== 'after') {
    if (side === 'call') return p?.is_me ? PLAN.sideCallMine() : PLAN.sideCall();
    if (side === 'in_person') return p?.is_me ? PLAN.sideInPersonMine() : PLAN.sideInPerson();
  }
  // OF.22/OF.22a/OF.23: живой статус — свежайшая правда об этом человеке, он перекрывает
  // «подтвердил(а)». Сервер кладёт его прямо в строку участника.
  const live = String(p?.live?.status || '');
  if (live && (phase === 'soon' || phase === 'now')) {
    if (live === 'late') return p?.is_me ? PLAN.liveLateMine() : PLAN.liveLate();
    if (live === 'otw') return PLAN.liveOtw();
    if (live === 'here') return PLAN.liveHere();
    if (live === 'cant_make_it') return p?.is_me ? PLAN.cantMakeMine() : PLAN.cantMakeStatus();
  }
  if (phase === 'cancelled') {
    const by = String(plan?.cancelled_by || '').trim().toLowerCase();
    if (by) {
      const pid = pidOf(p, 'name');
      if (pid && plan?.cancelled_by_id ? pid === plan.cancelled_by_id : name === by) return PLAN.cantMakeStatus();
      return p?.is_me ? PLAN.nothingToAnswer() : PLAN.toldJustNow();
    }
    return personStatus(p);
  }
  /*
   * ВСТРЕЧА ПОЗАДИ. «Подтвердил(а) · твой план» — это про сговор до встречи; на прошедшей она
   * читается как незакрытое дело и прямо вводит в заблуждение. После встречи важно другое: кто
   * сказал, состоялась ли она. Свой ответ показываем словами, чужой — только фактом ответа:
   * чужую оценку не видит никто, кроме её автора.
   */
  if (phase === 'after') {
    if (p?.is_me) {
      const a = myAnswer(plan);
      return a === undefined ? PLAN.pastNoAnswer() : a ? PLAN.pastYouSaidYes() : PLAN.pastYouSaidNo();
    }
    return plan?.their_feedback ? PLAN.pastAnswered() : PLAN.pastNotAnswered();
  }
  if (pendingChange) {
    const by = String(pendingChange.by || '').trim().toLowerCase();
    if (pendingChange.mine) {
      // O.21b, вид отправителя: я жду, второй не ответил.
      return name === by ? PLAN.waitingOldTime() : PLAN.notAnsweredNewTime();
    }
    // O.C5, вид получателя: предложивший подписан предложившим, мой ход — мой.
    return name === by ? PLAN.suggestedNewTime() : PLAN.yourTurn();
  }
  // O.C3: план ещё не подтверждён мной — «твой ход» против «подтвердил · час».
  const meRow = (plan?.participants || []).find((x: any) => x?.is_me);
  if (phase === 'waiting' && meRow && !meRow.confirmed) {
    return p?.confirmed ? PLAN.confirmedAt(tOf(plan?.starts_at, ru)) : PLAN.yourTurn();
  }
  return personStatus(p);
}

/** «Thu 23 July» — дата встречи для карточки (OF.20). */
/** OF.24: когда это было — «Yesterday, 20:00», на этой неделе — день недели, раньше — дата. */
function pastDay(sa: any, ru: boolean): string {
  const at = Number(sa || 0);
  if (!at) return '';
  const d = new Date(at * 1000);
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 86400000);
  const day = days === 0 ? T('Сегодня', 'Today', 'Hoy') : days === 1 ? T('Вчера', 'Yesterday', 'Ayer')
    : days > 1 && days < 7 ? d.toLocaleDateString(dateLocale(ru), { weekday: 'long' }).replace(/^./, (c) => c.toUpperCase())
    : dOf(sa);
  return OFD.pastDay(day, tOf(sa, ru));
}

function dOf(sa: any): string {
  const n = Number(sa);
  if (!Number.isFinite(n) || n <= 0) return '';
  const d = new Date(n * 1000);
  const loc = dateLocale();
  const wd = d.toLocaleDateString(loc, { weekday: 'short' }).replace(/\.$/, '');
  const mon = d.toLocaleDateString(loc, { month: 'long' });
  return `${wd.charAt(0).toUpperCase() + wd.slice(1)} ${d.getDate()} ${mon}`;
}

/** Полночь выбранного дня в поясе устройства. Момент встречи = она плюс minutes. */
function dayStart(dateKey: string): Date {
  return new Date(String(dateKey || '') + 'T00:00:00');
}

/** Час встречи в поясе устройства: «20:00». Для заголовка O.C5 и кнопок «Подтвердить/Оставить». */
function tOf(sa: any, ru: boolean): string {
  if (typeof sa !== 'number' || !isFinite(sa)) return '';
  return new Date(sa * 1000).toLocaleTimeString(dateLocale(ru), {
    hour: '2-digit', minute: '2-digit', hour12: use12h(ru),
  });
}

/**
 * Форма плана — первая половина кадра O.20.
 *
 * Поля СПРАШИВАЮТСЯ ПО РЕЖИМУ интента, а не все сразу. Встрече вживую поле «Ссылка» не нужно —
 * его там и не было на борде, а стояло оно здесь только потому, что режим угадывался по наличию
 * ссылки. Звонку, наоборот, не нужны район и адрес.
 */
function PlanForm({
  dates, date, setDate, minutes, setMinutes, setDragging,
  district, setDistrict, address, setAddress, link, setLink,
  wantsLink, wantsPlace, other, otherTz, ru, busy, err, onPropose,
}: any) {
  // Выбранный час глазами собеседника. Здесь это нужнее, чем где-либо: время НАЗНАЧАЮТ, и «20:00»
  // может оказаться у него шестью часами позже. Пусто, если пояса совпали или чужой неизвестен.
  const theirs = peerLocalTime(Math.floor(dayStart(date).getTime() / 1000) + minutes * 60, otherTz, ru);
  return (
    <View style={s.card}>
      {/* Что за встреча — сказано словами до первого поля: человек должен видеть, во что
          превратится «Создать план», а не догадываться по набору полей. */}
      <View style={s.modeRow}>
        {wantsLink ? <IconLink size={16} c={color.primary} /> : <IconPin size={16} c={color.primary} />}
        <Text style={s.modeText}>{PLAN.formMode(wantsLink && wantsPlace ? 'hybrid' : wantsLink ? 'online' : 'offline', other)}</Text>
      </View>

      <View style={s.labelRow}>
        <IconCalendar />
        <Text style={s.label}>{DETAILS.date()}</Text>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
        {dates.map((d: any) => (
          <Pressable
            key={d.key}
            accessibilityRole="button"
            accessibilityState={{ selected: date === d.key }}
            onPress={() => setDate(d.key)}
            style={[s.chip, date === d.key && s.chipOn]}
          >
            <Text style={[s.chipText, date === d.key && { color: color.onPrimary }]}>{d.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <View style={s.labelRow}>
        <IconClock />
        <Text style={s.label}>{DETAILS.time()}</Text>
      </View>
      <TimeDial minutes={minutes} onChange={setMinutes} onDragChange={setDragging} />
      <Text style={s.tz}>{hhmm(minutes)}{theirs ? ` · ${theirs}` : ''}</Text>

      {/* Ссылка — только у звонка и гибрида. У встречи вживую этого поля нет вовсе. */}
      {wantsLink ? (
        <>
          <View style={s.labelRow}>
            <IconLink size={18} c={color.fg} />
            <Text style={s.label}>{DETAILS.link()}</Text>
          </View>
          <TextInput
            style={s.input}
            value={link}
            onChangeText={setLink}
            placeholder={DETAILS.linkPlaceholder()}
            placeholderTextColor={color.neutral400}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            accessibilityLabel={DETAILS.link()}
          />
          {/* Пустая ссылка допустима: её доносят в согласованный план (O.20a). Врать о том, что
              без неё нельзя, не нужно — но и молчать о последствии тоже. */}
          <Text style={s.note}>{PLAN.linkLaterNote(other)}</Text>
        </>
      ) : null}

      {/* Место — только у встречи вживую и гибрида: у звонка его нет. */}
      {wantsPlace ? (
        <>
          <View style={s.labelRow}>
            <IconPin size={18} c={color.fg} />
            <Text style={s.label}>{DETAILS.district()}</Text>
          </View>
          <AddressField
            mode="district"
            style={s.input}
            value={district}
            onChange={setDistrict}
            onPick={(h) => setDistrict(h.label)}
            placeholder="Gràcia"
            accessibilityLabel={DETAILS.district()}
          />
          {/* OF.20: точное место — опционально; собеседник увидит его только после «да» (OF.C3). */}
          <View style={s.labelRow}>
            <IconPin size={18} c={color.fg} />
            <Text style={s.label}>{DETAILS.exactAddress()}</Text>
          </View>
          <AddressField
            style={s.input}
            value={address}
            onChange={setAddress}
            onPick={(h) => setAddress(h.label)}
            placeholder={PLAN.placePlaceholder()}
            accessibilityLabel={DETAILS.exactAddress()}
          />
          <Text style={s.note}>{DETAILS.exactAddressNote()}</Text>
        </>
      ) : null}

      {err ? <Text style={s.err}>{err}</Text> : null}

      {/* Непустая ссылка обязана быть ссылкой: молча отправить «встретимся в зуме» как url нельзя. */}
      {(() => {
        const bad = wantsLink && !!link.trim() && !looksLikeUrl(link.trim());
        return (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy, disabled: bad }}
            disabled={bad}
            style={[s.cta, bad && { opacity: 0.45 }]}
            onPress={busy ? undefined : onPropose}
          >
            {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{CHAT.createPlan()}</Text>}
          </Pressable>
        );
      })()}
      {/* Что произойдёт по нажатию — до нажатия, а не после: план уходит человеку предложением. */}
      <Text style={s.note}>{PLAN.formSendNote(other)}</Text>
    </View>
  );
}

/** Человеческая подпись времени для поля `when` — сервер хранит её как есть и показывает обоим. */
function planWhenLabel(dateKey: string, minutes: number, ru: boolean): string {
  const d = new Date(dateKey + 'T12:00:00');
  const day = d.toLocaleDateString(dateLocale(ru), { weekday: 'short', day: 'numeric', month: 'short' });
  return `${day} · ${hhmm(minutes)}`;
}

// ============================================================ вид

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, height: 56 },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  headTitle: { flex: 1, color: color.fg } as any,

  body: { paddingHorizontal: 20, gap: space.md },
  /** Заголовок состояния — гарнитура подписей 15/20 (OF.20 «Waiting for Marta»), пояснение Geist 13/18. */
  title: { fontSize: 15, lineHeight: 20, color: color.fg, marginTop: 4, marginBottom: -10 } as any,
  note: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,

  /** Карточка адреса дня встречи (OF.22): знак 30, адрес 15/20 полужирным, под ним когда, кнопка 40. */
  dayCard: { padding: 16, gap: 12 },
  dayRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  dayPlace: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: color.fg } as any,
  daySub: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.muted } as any,
  dayBtn: { height: 40, borderRadius: 99, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  infoTitle: { fontFamily: font.textSemibold, marginBottom: 4 } as any,
  pastRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  /** Строки причины (OF.24a): белое стекло 16%, выбранная 36%, галочка кораллом. */
  whyList: { gap: 8 },
  whyRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.16)' },
  whyRowOn: { backgroundColor: 'rgba(255,255,255,0.36)' },
  whyText: { flex: 1, fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.fg } as any,
  lateChips: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  lateChip: {
    height: 36, paddingHorizontal: 14, borderRadius: 99, alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.42)', borderWidth: 0.5, borderColor: 'rgba(255,255,255,0.9)',
  },
  lateChipOn: { backgroundColor: color.primary },
  lateChipText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.fg } as any,
  lateChipTextOn: { color: '#FFFFFF' },
  cardShadow: { borderRadius: 20, shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 5 } },
  card: { overflow: 'hidden' },
  cover: { height: 128, backgroundColor: color.neutral100 },
  cardBody: { padding: 16, gap: 8 },
  meter: { paddingHorizontal: 16, paddingVertical: 16, gap: 8 },
  meterHead: { flexDirection: 'row', alignItems: 'center' },
  meterWord: { fontFamily: font.displaySemi, fontSize: 13, lineHeight: 16, color: color.fg } as any,
  meterNum: { fontFamily: font.displaySemi, fontSize: 13, lineHeight: 16, color: '#AFAFAF', textAlign: 'center' } as any,
  meterNow: { color: '#FF385C' },
  meterTime: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,
  bars: { flexDirection: 'row', gap: 6 },
  bar: { flex: 1, height: 3, borderRadius: 999, backgroundColor: '#EBEBEB', overflow: 'hidden' },
  barFill: { height: 3, borderRadius: 999, backgroundColor: '#FF385C' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  orgBadge: { height: 16, paddingHorizontal: 8, borderRadius: 99, backgroundColor: '#CFE3FF', justifyContent: 'center' },
  orgText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#1F58BE' } as any,
  stOk: { color: '#0F7340' },
  stLeft: { color: '#A15C00' },
  sheetInk: { height: 48, borderRadius: 99, backgroundColor: color.fg, alignItems: 'center', justifyContent: 'center' },
  sheetInkText: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: '#fff' } as any,
  fixRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12, padding: 6, paddingRight: 14,
    borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.45)',
  },
  fixRowOn: { backgroundColor: 'rgba(255,255,255,0.85)' },
  fixWhen: { width: 92, paddingVertical: 6, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.8)', alignItems: 'flex-end', paddingRight: 8 },
  fixTime: { fontFamily: font.textSemibold, fontSize: 17, lineHeight: 22, color: color.fg } as any,
  fixDate: { fontSize: 12, lineHeight: 16, color: color.muted } as any,
  fixWho: { fontSize: 13, lineHeight: 18, color: color.muted } as any,
  fixBadge: { height: 18, paddingHorizontal: 8, borderRadius: 99, backgroundColor: 'rgba(0,0,0,0.06)', justifyContent: 'center' },
  fixBadgeText: { fontSize: 11, lineHeight: 14, color: color.muted } as any,
  altCard: { padding: 14, gap: 12 },
  altHead: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  altAva: { width: 64, height: 64, borderRadius: 32 },
  altName: { fontSize: 17, lineHeight: 22, color: color.fg } as any,
  altChip: { height: 36, paddingHorizontal: 14, borderRadius: 99, backgroundColor: color.ambientBase, justifyContent: 'center' },
  altChipText: { fontFamily: font.text, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  altBox: { borderRadius: 16, padding: 12, gap: 4, backgroundColor: 'rgba(255,255,255,0.7)' },
  altBoxHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  altSaid: { fontSize: 15, lineHeight: 20, color: '#0F7340' } as any,
  altWhen: { fontSize: 12, lineHeight: 16, color: color.muted } as any,
  stPlain: { color: color.fg },
  stMuted: { color: '#5A616E' },
  stTurn: { color: '#FF385C' },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  // Шапка формы: чем эта встреча будет — сказано до первого поля.
  modeRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md,
  },
  modeText: { flex: 1, ...type.bodySmall, color: color.infoText, fontWeight: '600' } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  metaPair: { flexDirection: 'row', alignItems: 'center', gap: 4, marginRight: 4 },
  /** Лист OF.C3a: «Instead of Thu 23 July,» подписью 15/20, подписи рядов Geist 600 13/20. */
  sheetLead: { fontSize: 15, lineHeight: 20, color: color.fg } as any,
  sheetLabel: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.fg, marginTop: 4 } as any,
  sheetGhost: { height: 40, alignItems: 'center', justifyContent: 'center' },
  sheetGhostText: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  metaText: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: color.fg, flexShrink: 1 } as any,
  tz: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,

  linkCard: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: color.successBg, borderRadius: rad.lg, padding: space.md,
  },
  // «Всё готово»: та же зелёная семья, но без кнопки — это не действие, а точка в переговорах.
  //
  // РАЗМЕРЫ ЗДЕСЬ И ЕСТЬ ЧИТАЕМОСТЬ. Было так: заголовок и текст одним кеглем — 13, самым мелким
  // в приложении, — и всё одним зелёным. Иерархии не возникало вовсе, и плашка читалась сплошным
  // пятном. Теперь заголовок — `title` (17), факты — `body` (15) с весом, проза — `bodySmall` (13)
  // приглушённее: три ступени вместо одной. Цвета прежние, зелёная семья не тронута.
  doneCard: { backgroundColor: color.successBg, borderRadius: rad.lg, padding: space.lg, gap: space.sm },
  doneTitle: { ...type.title, color: color.successText, fontWeight: '700' } as any,
  doneRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  doneFact: { ...type.body, color: color.successText, fontWeight: '600', flexShrink: 1 } as any,
  // «Не состоялась» — тоже итог, но не удача: зелёная семья здесь читалась бы как поздравление.
  closedTitle: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  doneSub: { ...type.bodySmall, color: color.successText, opacity: 0.85 } as any,
  linkTitle: { ...type.labelMedium, color: color.successText, fontWeight: '700' } as any,
  linkSub: { ...type.caption, color: color.successText } as any,
  linkBtn: { height: 40, paddingHorizontal: 18, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  linkBtnText: { ...type.labelMedium, color: color.onPrimary, fontWeight: '700' } as any,

  infoBox: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md },
  infoText: { ...type.bodySmall, color: color.infoText } as any,

  // Листы OF.21a/OF.24a.
  hmRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  hmBox: {
    width: 74, height: 48, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.7)',
    textAlign: 'center', color: color.fg, fontSize: 18, fontFamily: font.textSemibold,
  } as any,
  hmColon: { fontSize: 18, color: color.muted },
  reasonRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 9 },
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: color.neutral300 },
  radioOn: { borderColor: color.primary, backgroundColor: color.primary },
  reasonText: { ...type.bodySmall, color: color.fg } as any,

  // O.23a: зелёная строка факта отмены и кнопка «Другое время» рядом.
  pillRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  pill: {
    flex: 1, backgroundColor: color.successBg, borderRadius: rad.full,
    paddingVertical: 10, paddingHorizontal: 14,
  },
  pillText: { ...type.caption, color: color.successText, fontWeight: '600' } as any,
  pillBtn: {
    height: 40, paddingHorizontal: 14, borderRadius: rad.full,
    backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center',
  },
  pillBtnText: { ...type.labelMedium, color: '#fff', fontWeight: '600' } as any,

  chipRow: { gap: space.sm, paddingVertical: 2 },
  chipRowWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  /** Чип дня и времени — как в мастере (GlassChip): 36, белое 70% со светлой кромкой, выбранный — коралл. */
  chip: {
    height: 36, paddingHorizontal: 14, borderRadius: 18, borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,255,255,0.9)', backgroundColor: 'rgba(255,255,255,0.7)', alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  input: {
    height: 48, borderRadius: 24, backgroundColor: 'rgba(255,255,255,0.7)',
    paddingHorizontal: 16, color: color.fg, fontSize: 15, fontFamily: font.text,
  } as any,

  /** Строка участника 56: фото 40, без своей подложки — как «Who's in» групп (OF.20). */
  person: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56 },
  personAva: { width: 40, height: 40, borderRadius: 20 },
  personAvaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  personName: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg, flexShrink: 1 } as any,
  personStatus: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: '#5A616E' } as any,

  /** Кнопки досок B/C — 40 высотой: коралл 82% с тенью и стеклянная светлая (OF.20 «Open chat» / «Change the plan»). */
  cta: {
    height: 40, borderRadius: 20, backgroundColor: 'rgba(255,56,92,0.82)', alignItems: 'center', justifyContent: 'center',
    shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 12, shadowOffset: { width: 0, height: 4 },
  },
  ctaText: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: '#fff' } as any,
  ctaDark: {
    height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.62)', alignItems: 'center', justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(255,255,255,0.9)',
  },
  ctaDarkText: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  // Вторая кнопка кадров O.C3/O.C4/O.C5 — серая, не тёмная: отказ там не «опасное» действие.
  ctaSoft: {
    height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.62)', alignItems: 'center', justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(255,255,255,0.9)',
  },
  ctaSoftText: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  /** Пояснение вместо кнопок, которые сервер уже не примет. */
  lockNote: { ...type.bodySmall, color: color.muted, textAlign: 'center', paddingHorizontal: space.sm } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
