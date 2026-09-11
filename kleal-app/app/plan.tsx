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
import { useRouter, useLocalSearchParams } from 'expo-router';
import {
  CHAT, PLAN, RATINGS, planWhen, personStatus, planPhase, minutesToStart, linkOpensAt,
} from '../src/chat';
import { DETAILS, dateChips, hhmm, peerLocalTime, looksLikeUrl } from '../src/intent';
import { TimeDial } from '../src/components/Dials';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { normalizeTimePart } from '../src/timeInput';
import { useLang, T, getLang, dateLocale, use12h } from '../src/i18n';
import { useOnb } from '../src/state';
import { mediaUrl, agent } from '../src/api';
import {
  IconChevronLeft, IconCalendar, IconClock, IconPin, IconLink, IconPerson,
} from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { Sheet } from '../src/components/Sheet';
import { AddressField } from '../src/components/AddressField';
import { color, radius as rad, space, type } from '../src/theme';

export default function Plan() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Листы с полями ввода: на Android клавиатура ложится поверх них. См. src/keyboard.ts. */
  const kb = useKeyboardInset();

  const params = useLocalSearchParams<{
    who?: string; title?: string; photo?: string; link?: string; id?: string;
    address?: string; mode?: string;
  }>();
  /**
  * Имя собеседника. С ГЛАВНОЙ план открывается только по `id` (app/home.tsx: «К плану»), и
  * параметра `who` там нет. А на нём висит вся копия с именем — «Sofia тоже её увидит»,
  * «Ждём ответа: Sofia», «Скажи Sofia, что не сможешь». Без него в тексте оставалась дырка:
  * «откроется за 10 минут до начала —  тоже её увидит». Сервер отдаёт `other` в самом плане,
  * поэтому берём оттуда, а параметр остаётся ведущим: он известен до первой загрузки.
  */
  const otherParam = String(params.who || '').trim();
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
  const [plan, setPlan] = useState<any>(null);
  const other = otherParam || String((plan as any)?.other || '').trim();
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
  /** OF.21a: выбранный сдвиг (минуты от текущего начала) или своё время часами-минутами. */
  const [sugDelta, setSugDelta] = useState<number | null>(60);
  const [sugH, setSugH] = useState('');
  const [sugM, setSugM] = useState('');
  /** OF.20a: место, которое доносят в согласованный план. */
  const [placeDraft, setPlaceDraft] = useState('');
  /** OF.24a: лист причины «не состоялась». */
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reasonPick, setReasonPick] = useState('');
  /** Подтверждение отмены: на сервере отменённая встреча терминальна, вернуть её нельзя. */
  const [dropping, setDropping] = useState(false);
  /** HY.25 — каким входом встреча в итоге состоялась. Только у гибрида. */
  const [howMet, setHowMet] = useState<'' | 'in_person' | 'call' | 'both'>('');
  /** «Другое время» после отмены: составляем новую встречу, опрос не должен возвращать старую. */
  const composing = useRef(false);
  const startNewPlan = () => { composing.current = true; setPlan(null); };
  const dates = useMemo(() => dateChips(), []);

  const load = useCallback(async () => {
    if (!me) return;
    try {
      const r: any = await agent.plans(me, other);
      const live = (r?.plans || []) as any[];
      const past = (r?.history || []) as any[];
      const withOther = (list: any[]) => list.filter((p: any) =>
        (p.participants || []).some((x: any) =>
          String(x.name || '').trim().toLowerCase() === other.trim().toLowerCase()));
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
  }, [me, other, planId]);

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
   * Кого ждём. Если я уже ответил — ждём только второго, и говорить надо это: «ждём обоих» после
   * собственного ответа читается как «твой ответ не записался».
   */
  const waitingLine = () =>
    mine !== undefined && !plan?.their_feedback ? PLAN.waitingThem(other) : PLAN.waitingBoth();
  /** O.21b: встречное время лежит РЯДОМ с планом (pending), сама встреча не тронута. */
  const pendingChange = plan?.pending || null;
  const cancelledByMe =
    !!plan?.cancelled_by
    && String(plan.cancelled_by).trim().toLowerCase() === me.trim().toLowerCase();
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
  const askedThemPlace = !!placeAskedBy && placeAskedBy === norm(me);
  const askedMePlace = !!placeAskedBy && placeAskedBy !== norm(me);
  const askedThemLink = !!linkAskedBy && linkAskedBy === norm(me);
  const askedMeLink = !!linkAskedBy && linkAskedBy !== norm(me);
  /** Внутри замка сервер не принимает ни место, ни ссылку — поля не рисуем, а говорим почему. */
  const whereLocked = locked && (needsPlace || needsLink);
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
  /** Человеческое имя места: «Nømad · Carrer de Verdi 12». Видно только подтвердившим (OF.C3). */
  const placeLabel = wantsPlace
    ? [plan?.venue, (plan as any)?.place ?? (offline ? plan?.address : '')].filter(Boolean).join(' · ')
    : '';

  /** Место уже стоит зелёной плашкой: встреча на носу и адрес открыт. */
  const placeReady = wantsPlace && (phase === 'soon' || phase === 'now') && !!placeLabel
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
      const r: any = await agent.planPropose(me, other, {
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
    let ts: number;
    if (sugDelta != null) {
      ts = Math.floor(plan.starts_at + sugDelta * 60);
    } else {
      // Пустые поля — это «человек начал набирать и передумал», а не «полночь»: раньше
      // незаполненные часы давали 00:00, и сервер честно отвечал «время уже прошло».
      if (!sugH.trim() && !sugM.trim()) { setErr(CHAT.inThePast()); return; }
      // Зажимаем и здесь — на случай отправки без ухода из поля (клавиатура закрыта кнопкой).
      // Поле к этому моменту уже нормализовано, так что зажим ничего не меняет; он остаётся
      // последней защитой, а не тихой правкой за спиной.
      const h = Math.max(0, Math.min(23, parseInt(sugH || '0', 10) || 0));
      const m = Math.max(0, Math.min(59, parseInt(sugM || '0', 10) || 0));
      const d = new Date(plan.starts_at * 1000);
      d.setHours(h, m, 0, 0);
      // Названный час уже прошёл — человек имеет в виду завтра, а не вчера. Сервер отказал бы.
      if (d.getTime() <= Date.now()) d.setDate(d.getDate() + 1);
      ts = Math.floor(d.getTime() / 1000);
    }
    // Подпись — от НОВОГО момента целиком. Раньше бралась дата текущего плана плюс новый час: если
    // названный час уже прошёл и время ушло на завтра, подпись показывала вчерашнюю дату с
    // завтрашним часом.
    await respond('counter', { starts_at: ts, when: planWhen({ starts_at: ts }, ru) });
    setCountering(false);
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
  const sendLive = async (status: 'otw' | 'late' | 'here') => {
    if (!plan?.id) return;
    setErr('');
    try {
      const r: any = await agent.planStatus(plan.id, me, status);
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
  const openChat = () =>
    router.dismissTo({ pathname: '/conversation', params: { who: other, title: intentTitle, photo } });

  /** Ссылка, как её отдал сервер: до подтверждения её просто нет в ответе. */
  const serverLink = String((plan as any)?.link ?? (mode === 'online' ? plan?.address : '') ?? '');
  const linkReady = phase === 'soon' || phase === 'now';

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} style={s.back} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
            <IconChevronLeft />
          </Pressable>
          <Text style={s.headTitle} numberOfLines={1}>{intentTitle || T('Встреча', 'Meetup', 'Quedada')}</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView contentContainerStyle={[s.body, { paddingBottom: 130 }]} keyboardShouldPersistTaps="handled" scrollEnabled={!dragging}>
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
          ) : (
            <>
              <Text style={s.title}>{headline(phase!, other, plan, me, ru)}</Text>
              {subline(phase!, other, plan, ru, me) ? (
                <Text style={s.note}>{subline(phase!, other, plan, ru, me)}</Text>
              ) : null}

              <View style={s.card}>
                {/* Обложки у встречи нет и взяться ей неоткуда. Красный прямоугольник со значком
                    «нет картинки» читался не как заглушка, а как не загрузившееся фото. */}
                <View style={s.metaRow}>
                  <IconCalendar />
                  <Text style={s.metaText}>{planWhen(plan, ru)}{peerTime ? ` · ${peerTime}` : ''}</Text>
                </View>
                {/* O.21b: предложенное время стоит РЯДОМ со старым — обе строки видны разом. */}
                {pendingChange ? (
                  <View style={s.metaRow}>
                    <IconClock size={16} c={color.primary} />
                    <Text style={[s.metaText, { color: color.primary }]}>
                      {PLAN.newPrefix(planWhen(pendingChange, ru))}
                    </Text>
                  </View>
                ) : null}
                {plan.district ? (
                  <View style={s.metaRow}>
                    <IconPin size={16} c={color.muted} />
                    <Text style={s.metaText}>{plan.district}</Text>
                  </View>
                ) : null}
                {/* OF.20/OF.21: строка места. До подтверждения — честное «после подтверждения»,
                    после — само место; пока не выбрано — «пока нет». Когда место уже стоит зелёной
                    плашкой ниже (OF.22/OF.23), здесь его не повторяем — один адрес, одно место. */}
                {/* У отменённой встречи адрес не обещают: «откроется после твоего подтверждения»
                    было прямой неправдой — подтверждать больше нечего, а сервер закрывает адрес
                    отказавшемуся автоматически (его ответ перестал быть «подтвердил»). */}
                {wantsPlace && phase !== 'cancelled'
                  && !(placeReady && placeLabel) && !(allSet && placeLabel) ? (
                  <View style={s.metaRow}>
                    <IconPin size={16} c={color.muted} />
                    <Text style={s.metaText}>
                      {!placeSet ? PLAN.noPlaceYet()
                        : placeLabel ? placeLabel
                        : PLAN.addressAfterConfirm()}
                    </Text>
                  </View>
                ) : null}
                {/* Строка ссылки. Стояла на «режим == online», а строка места — на «offline»:
                    гибрид не тот и не другой, и на его экране не было НИ ОДНОЙ из двух — при том
                    что у гибрида как раз оба входа и есть суть (HY.21 «both ways open»). */}
                {wantsLink ? (
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

              {/*
                Договорились обо всём — и это сказано вслух, зелёным, один раз.
                Не хватало именно этого: план подтверждался, место называлось, а экран продолжал
                выглядеть как незаконченное дело — человек не понимал, надо ли ещё что-то нажать.
                Плашка живёт только в «подтверждено»: у «скоро» и «сейчас» ниже своя, с маршрутом.
              */}
              {allSet ? (
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
              {!offline && linkReady && serverLink ? (
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
                      Linking.openURL(serverLink).catch(() => setErr(CHAT.planFailed()));
                    }}
                  >
                    <Text style={s.linkBtnText}>{PLAN.openLink()}</Text>
                  </Pressable>
                </View>
              ) : null}

              {/* O.23a: короткая строка факта — что, когда и кто отменил — и сразу выход в новое
                  время. Только у автора отмены: на кадре второй стороны (O.C4) плашки нет. */}
              {phase === 'cancelled' && cancelledByMe ? (
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

              {(plan.participants || []).map((p: any, i: number) => (
                <View key={(p.name || '') + i} style={s.person}>
                  {p.photo ? (
                    <Image source={{ uri: mediaUrl(String(p.photo)) }} style={s.personAva} />
                  ) : (
                    <View style={[s.personAva, s.personAvaEmpty]}><IconPerson size={18} /></View>
                  )}
                  <View style={{ flex: 1 }}>
                    <Text style={s.personName}>{p.name}{p.age ? `, ${p.age}` : ''}</Text>
                    <Text style={s.personStatus}>{statusFor(p, plan, phase!, pendingChange, ru)}</Text>
                  </View>
                  <IconClock size={18} c={color.neutral400} />
                </View>
              ))}

              {phase === 'soon' || phase === 'now' ? (
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
              {phase === 'after' && mine === undefined ? (
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
              {phase === 'after' && mine === true ? (
                thanks || myRated(plan) ? (
                  // «Спасибо» уже стоит в заголовке — здесь остаётся только то, чего там нет.
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
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => router.navigate('/profile/safety')}>
                      <Text style={s.ctaDarkText}>{PLAN.reportProblem()}</Text>
                    </Pressable>
                  </>
                )
              ) : null}

              {/* O.24b: оба сказали «не состоялась» — это отдельный конец, а не общее «спасибо».
                  Если ответы разошлись (я «нет», второй «да»), сервер считает встречу
                  состоявшейся, и говорить «не состоялась» было бы неправдой — там остаётся
                  благодарность за ответ. */}
              {phase === 'after' && mine === false ? (
                !bothAnswered ? (
                  <Text style={s.note}>{waitingLine()}</Text>
                ) : plan?.outcome?.happened === false ? (
                  <>
                    <Text style={s.closedTitle}>{PLAN.didntHappenTitle()}</Text>
                    <Text style={s.note}>{PLAN.didntHappenNote(other)}</Text>
                    <Pressable
                      accessibilityRole="button"
                      style={s.cta}
                      onPress={() => router.dismissTo('/home')}
                    >
                      <Text style={s.ctaText}>{PLAN.findElse()}</Text>
                    </Pressable>
                  </>
                ) : (
                  <Text style={s.note}>{PLAN.thanks()}</Text>
                )
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
              {needsPlace && !pendingChange && !countering && !locked ? (
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
              {needsLink && !pendingChange && !countering && !locked ? (
                <>
                  {askedMeLink ? (
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
                  {askedMeLink ? null : (
                    <Pressable
                      accessibilityRole="button"
                      disabled={askedThemLink}
                      accessibilityState={{ disabled: askedThemLink }}
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
                  {locked ? null : (
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setCountering(true)}>
                      <Text style={s.ctaDarkText}>{PLAN.suggestAnother()}</Text>
                    </Pressable>
                  )}
                </>
              ) : null}

              {/* O.C3: план прислали мне — подтвердить или предложить своё время. */}
              {phase === 'waiting' && !pendingChange && !countering && !myConfirmed(plan, me) ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={() => respond('confirm')}>
                    <Text style={s.ctaText}>{PLAN.confirmAction()}</Text>
                  </Pressable>
                  {locked ? null : (
                    <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setCountering(true)}>
                      <Text style={s.ctaSoftText}>{PLAN.suggestAnother()}</Text>
                    </Pressable>
                  )}
                </>
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
              {(phase === 'waiting' || phase === 'confirmed') && !pendingChange && !countering
                && myLive !== 'cant_make_it' ? (
                <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setDropping(true)}>
                  <Text style={s.ctaSoftText}>{locked ? PLAN.cantMakeIt() : PLAN.callOff()}</Text>
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
                  {locked ? (
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
                  {locked ? (
                    <Text style={s.lockNote}>{PLAN.lockedNote()}</Text>
                  ) : (
                    <>
                      <Pressable accessibilityRole="button" style={s.cta} onPress={() => respond('accept_change')}>
                        <Text style={s.ctaText}>{PLAN.confirmTime(tOf(pendingChange.starts_at, ru))}</Text>
                      </Pressable>
                      <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => respond('reject_change')}>
                        <Text style={s.ctaSoftText}>{PLAN.keepTime(tOf(plan.starts_at, ru))}</Text>
                      </Pressable>
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
              {phase === 'soon' || phase === 'now' ? (
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
                  {hybrid && !movedToCall && myLive === 'here' && theirLive === 'here' ? (
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
                  {comingInPerson && myLive !== 'late' && myLive !== 'here' && myLive !== 'cant_make_it' ? (
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => sendLive('late')}>
                      <Text style={s.ctaDarkText}>{PLAN.imLate()}</Text>
                    </Pressable>
                  ) : null}

                  {comingInPerson && myLive !== 'here' && myLive !== 'cant_make_it' ? (
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
              {phase === 'cancelled' && cancelledByMe ? (
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
              {phase === 'cancelled' && !cancelledByMe ? (
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
          title={PLAN.suggestSheetTitle()}
          bottomInset={dockBottom(insets.bottom, kb, 18)}
        >
            <Text style={s.note}>{PLAN.insteadOf(tOf(plan?.starts_at, ru))}</Text>
            <View style={s.chipRowWrap}>
              {[60, 90, 120, 150].map((d) => {
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
                    onPress={() => setSugDelta(d)}
                  >
                    <Text style={[s.chipText, on && { color: color.onPrimary }]}>{label}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={s.note}>{PLAN.orSetYour()}</Text>
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
            <Text style={s.note}>{PLAN.suggestSheetNote(other)}</Text>
            <Pressable accessibilityRole="button" style={s.cta} onPress={sendCounter}>
              <Text style={s.ctaText}>{PLAN.sendNewTime()}</Text>
            </Pressable>
            <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setCountering(false)}>
              <Text style={s.ctaDarkText}>{DETAILS.cancel()}</Text>
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
        <Sheet visible={dropping} onClose={() => setDropping(false)}
               title={locked ? PLAN.cantMakeAsk(other) : PLAN.callOffAsk(other)}>
          {/* HY.23b: у гибрида рядом стоит «уйду в звонок», и «не смогу» легко прочесть как
              смену стороны. Кадр требует сказать разницу вслух — иначе человек отменяет встречу,
              думая, что просто меняет вход. */}
          <Text style={s.note}>
            {locked ? PLAN.cantMakeNote(other) : hybrid ? PLAN.callOffNoteHybrid(other) : PLAN.callOffNote(other)}
          </Text>
          <Pressable
            accessibilityRole="button"
            style={s.ctaDark}
            onPress={() => { setDropping(false); respond('decline'); }}
          >
            <Text style={s.ctaDarkText}>{locked ? PLAN.cantMakeYes() : PLAN.callOffYes()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => setDropping(false)}>
            <Text style={s.ctaSoftText}>{PLAN.callOffNo()}</Text>
          </Pressable>
        </Sheet>

        {/* OF.24a — «не состоялась»: что случилось. Ответ другим не показывается; «Пропустить»
            отправляет «нет» без причины, крестик не отправляет ничего. */}
        <Sheet visible={reasonOpen} onClose={() => setReasonOpen(false)} title={PLAN.whatHappened()}>
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

        <View style={s.navFloat} pointerEvents="box-none">
          <BottomNav />
        </View>
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
    (p: any) => String(p.name || '').toLowerCase() === String(me).toLowerCase() && p.confirmed
  );
}

function headline(phase: string, other: string, plan: any, me: string, ru: boolean): string {
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
    if (!hasPlace) return PLAN.pickPlaceTitle();
  }
  // HY.22a/HY.22b/HY.C4: смена стороны — новость этого экрана, и она важнее счётчика: она
  // отвечает на вопрос «где меня ждать». Своя смена и чужая читаются по-разному, поэтому это две
  // разные строки, а не одна про «кто-то ушёл в звонок».
  if (plan?.mode === 'hybrid' && (phase === 'confirmed' || phase === 'soon' || phase === 'now')) {
    // Сначала общий случай: если в звонке ОБА, ни «ты ушёл», ни «она ушла» уже не правда.
    if (plan?.my_side === 'call' && plan?.their_side === 'call') return PLAN.sideBothCallTitle();
    if (plan?.my_side === 'call') return PLAN.sideSwitchedTitle();
    if (plan?.their_side === 'call') return PLAN.theySwitchedTitle(other);
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
      return PLAN.thanks();
    }
    // O.23a: у отмены есть автор, и заголовок называет его. Старые планы без cancelled_by
    // остаются с безличной строкой — выдумывать автора не из чего.
    case 'cancelled': {
      const by = String(plan?.cancelled_by || '').trim().toLowerCase();
      if (!by) return T('Встреча отменена', 'The meetup is off', 'La quedada está cancelada');
      return by === String(me).trim().toLowerCase()
        ? PLAN.youToldCantMake(other)
        : PLAN.theyCantMake(other);
    }
    default: return '';
  }
}

function subline(phase: string, other: string, plan: any, ru: boolean, me: string): string {
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
      if (by && by === String(me).trim().toLowerCase()) return '';
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
      if (name === by) return PLAN.cantMakeStatus();
      return p?.is_me ? PLAN.nothingToAnswer() : PLAN.toldJustNow();
    }
    return personStatus(p);
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
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  headTitle: { flex: 1, ...type.title, color: color.fg, textAlign: 'center' } as any,

  body: { paddingHorizontal: 20, gap: space.md },
  title: { fontSize: 20, fontWeight: '700', color: color.fg, marginTop: space.sm },
  note: { ...type.bodySmall, color: color.muted } as any,

  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.md },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  // Шапка формы: чем эта встреча будет — сказано до первого поля.
  modeRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md,
  },
  modeText: { flex: 1, ...type.bodySmall, color: color.infoText, fontWeight: '600' } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  metaText: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
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
    width: 74, height: 48, borderRadius: rad.md, backgroundColor: color.neutral100,
    textAlign: 'center', color: color.fg, fontSize: 18,
  },
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
  chip: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  input: {
    height: 46, borderRadius: rad.md, backgroundColor: color.neutral100,
    paddingHorizontal: 14, color: color.fg, fontSize: 15,
  },

  person: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: color.card, borderRadius: rad.lg, padding: space.md,
  },
  personAva: { width: 40, height: 40, borderRadius: 20 },
  personAvaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  personName: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  personStatus: { ...type.caption, color: color.muted } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  ctaDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  ctaDarkText: { ...type.button, color: '#fff' } as any,
  // Вторая кнопка кадров O.C3/O.C4/O.C5 — серая, не тёмная: отказ там не «опасное» действие.
  ctaSoft: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  ctaSoftText: { ...type.button, color: color.fg } as any,
  /** Пояснение вместо кнопок, которые сервер уже не примет. */
  lockNote: { ...type.bodySmall, color: color.muted, textAlign: 'center', paddingHorizontal: space.sm } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
