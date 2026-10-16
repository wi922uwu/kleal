/**
 * Групповой план — ОДИН экран на всю его жизнь: GR.25 → GR.26/28/29 → GR.30/31 → GR.34, плюс
 * голосование GR.35–38, правка организатором GR.32/33 и онлайновая ссылка GRO.25a.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор состояний — в src/gplan.ts.
 *
 * ПОЧЕМУ ОДИН ЭКРАН. На борде это пятнадцать кадров, но у всех одна и та же раскладка: заголовок,
 * карточка плана, индикатор раундов, состав, пара кнопок внизу. Меняются слова и то, что делают
 * кнопки. Разложить это по маршрутам значило бы, что человек, открывая свой же план, каждый раз
 * попадает в новое место, и что «назад» ведёт в историю согласования, а не к группе. Ровно так же
 * устроен план 1:1 (app/plan.tsx) — и по той же причине.
 *
 * Что экран НЕ решает сам, потому что это решает сервер:
 *  — можно ли ещё предложить своё (раунды), можно ли закрепить, чей сейчас ход — приходит флагами
 *    (`rounds_used_up`, `can_fix`, `stay_or_leave`, `accept_or_leave`);
 *  — сколько ещё подтверждений нужно (`needs`) — считается от ВСЕГО состава, а не от тройки;
 *  — жив ли план (`state`) и заперт ли он двухчасовым окном (`locked`).
 * Дублировать эти проверки здесь значило бы завести второй источник правды, который разойдётся
 * с первым при первой же правке правил.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image,
  ActivityIndicator, Modal, KeyboardAvoidingView, Platform, Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Stack, useRouter, useLocalSearchParams, useIsFocused } from 'expo-router';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { group as gapi, mediaUrl, newIdem, isMe, pidOf, type GroupInfo } from '../src/api';
import { GPLAN, venue, callVenue, callService, hoursLeft, memberState, elapsed, type GPlan, type GVote, leftAgo} from '../src/gplan';
import { ROOM } from '../src/groups';
import { WhenPicker, whenLabel, whenStartsAt, whenFromStartsAt, type WhenValue } from '../src/components/WhenPicker';
import { dateChips, deviceTz, withScheme } from '../src/intent';
import Animated, {
  Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withTiming,
} from 'react-native-reanimated';
import {
  IconPerson, IconCalendar, IconCalendarCheck, IconPin, IconVideo, IconLink, IconClock,
  IconDots, IconExit, IconCheck, IconInfo, IconLock, IconCalendarX, IconTimer,
} from '../src/components/icons';
import { Sheet, SheetItem, SheetText } from '../src/components/Sheet';
import { PlanChangeSheet } from '../src/components/PlanChangeSheet';
import { AddressField } from '../src/components/AddressField';
import { color, font, heading, labelFamily, space, type } from '../src/theme';
import { Cover } from '../src/components/Cover';
import { GlassPill } from '../src/components/Glass';
import { GlassBack, GlassIconButton, GlassSurface, riseIn } from '../src/components/LiquidGlass';
import { BottomNav } from '../src/components/BottomNav';
import { useNavCollapse } from '../src/navScroll';

/** Локальные режимы, которых у сервера нет: это формы, а не состояния плана. */
type Mode = 'view' | 'create' | 'suggest' | 'update' | 'link' | 'details';

export default function GroupPlan() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const reduced = useReducedMotion();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const kb = useKeyboardInset();

  const params = useLocalSearchParams<{ gid?: string; edit?: string }>();
  const gid = String(params.gid || '').trim();
  const me = String(st.profile.name || '');

  const [g, setG] = useState<GroupInfo | null>(null);
  const [plan, setPlan] = useState<GPlan | null>(null);
  const [vote, setVote] = useState<GVote | null>(null);
  const [mode, setMode] = useState<Mode>('view');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [fatal, setFatal] = useState('');
  const [askVote, setAskVote] = useState(false);
  const [ask1to1, setAsk1to1] = useState(false);
  const [voteSheet, setVoteSheet] = useState(false);
  const [decideSheet, setDecideSheet] = useState(false);
  const [actions, setActions] = useState(false);
  const [lateSheet, setLateSheet] = useState(false);
  const [cantMakeSheet, setCantMakeSheet] = useState(false);
  /** Раздел E: «How was it?» (GR.49), «What happened?» (GR.48a); GR.41 — выйти из плана. */
  const [howOpen, setHowOpen] = useState(false);
  const [whatOpen, setWhatOpen] = useState(false);
  const [rating, setRating] = useState(0);
  const [reason, setReason] = useState('');
  const [leaveAsk, setLeaveAsk] = useState(false);
  const [findThird, setFindThird] = useState(false);
  // GR.29a: выбранная версия в листе «Pick the final version»; null — лист закрыт.
  const [pickRound, setPickRound] = useState<number | null>(null);
  /** GR.26b / 27b / 32b — изменить план листом над страницей, а не формой вместо неё. */
  const [changeSheet, setChangeSheet] = useState<'' | 'suggest' | 'update'>('');
  /** GR.38a: какое решённое «оставить как есть» уже показано — на голосование один раз. */
  const [keptSeen, setKeptSeen] = useState<Set<string>>(new Set());

  /**
   * Поля форм. Одни и те же на создание, предложение и правку — предлагают всегда одно и то же.
   *
   * Время — НЕ строка. Здесь стояло текстовое поле «например: чт 24 июля, 20:30», и у плана из-за
   * этого не было настоящего момента: сервер считает двухчасовой замок и отказ TOO_LATE по
   * `starts_at`, а он не отправлялся вовсе. Теперь дата и время выбираются как на кадре GR.09 и
   * уходят вдвоём — подписью и unix-секундами.
   */
  const [when, setWhen] = useState<WhenValue>(() => ({
    date: dateChips(1)[0].key,
    minutes: 20 * 60,
    tz: deviceTz(),
  }));
  const [dragging, setDragging] = useState(false);
  const [place, setPlace] = useState('');
  const [link, setLink] = useState('');

  const owner = String(g?.owner || '');
  const isOwner = !!g?.i_am_owner;
  const members = (g?.members || []) as { name?: string; photo?: string }[];
  // Второй из двоих — тот, чьё согласие нужно на переход. Берётся из ЖИВОГО состава, а не из
  // истории плана: ушедший в списке плана остаётся (кадр показывает «Left · 20 minutes ago»), и
  // спросить его было бы не у кого.
  // «Не я» — по id (kleal-ms/docs/IDENTITY.md): в группе двух тёзок подписи равны.
  const otherName = String((members.find((m) => String(m.name || '') && !isMe(m.name, pidOf(m, 'name'), me)) || {}).name || '');
  /**
   * GR.39. Вышедшие идут В ТОТ ЖЕ состав, строкой «Вышел(а) · 20 минут назад», а не исчезают.
   * Состав, который забывает людей, не может объяснить, почему их стало меньше, — а это первый
   * вопрос у того, кто открыл экран после чужого ухода.
   */
  const departed = (g?.departed || []) as { name?: string; photo?: string; left?: number }[];
  // Порядок строк — как на кадрах: сначала остальные по приходу, ты последним, ушедшие ниже.
  // Ушедший остаётся на СВОЁМ месте по времени прихода (GR.39/40: Jane, Marc · Left, You).
  const roster: { name?: string; photo?: string; left?: number; age?: number; joined?: number; gone: boolean }[] = [
    ...[...members.filter((m) => !isMe(m.name, pidOf(m, 'name'), me)).map((m) => ({ ...m, gone: false })),
        ...departed.map((d) => ({ ...d, gone: true }))]
      .map((x, i) => ({ x, i }))
      .sort((a, b) => (Number((a.x as any).joined || 0) - Number((b.x as any).joined || 0)) || a.i - b.i)
      .map((r) => r.x),
    ...members.filter((m) => isMe(m.name, pidOf(m, 'name'), me)).map((m) => ({ ...m, gone: false })),
  ];
  /** Ушли недавно — значит на экране ещё уместно сказать, что встреча в силе. */
  const freshLeave = departed.some((d) => (Date.now() / 1000) - Number(d.left || 0) < 24 * 3600);
  const online = (plan?.mode || (g as any)?.mode || 'offline') === 'online';
  const hybrid = (plan?.mode || (g as any)?.mode || 'offline') === 'hybrid';

  const load = useCallback(async () => {
    if (!gid || !me) return;
    try {
      const r: any = await gapi.get(gid, me);
      if (r?.error === 'NO_SUCH_GROUP') { setFatal(ROOM.gone()); return; }
      const grp = r?.group;
      if (!grp) return;
      // Группа стала один на один (GR.19b, в том числе из паузы GR.40a/40d) — плана группы больше
      // нет. Чат группы сам уводит в переписку двоих; экран плана с «Set the time and place» врал бы.
      if (grp.state === 'converted_1to1' && !grp.read_only) {
        router.dismissTo({ pathname: '/group', params: { gid } });
        return;
      }
      setG(grp);
      // GR.40b / 40e: план закрыт с паузы — сервер сутки отдаёт его отдельным полем.
      setPlan(grp.plan || grp.closed_plan || null);
      // Голосование живёт не на группе, а на человеке: сервер отдаёт его в списке планов вместе
      // с закрытыми-но-нерешёнными, и именно они рисуют GR.37/38. Второй запрос — только когда
      // план есть: без плана голосовать не о чем, и опрашивать нечего.
      const pid = String(grp.plan?.id || '');
      if (pid) {
        const pl: any = await gapi.plans(me);
        setVote(((pl?.votes || []) as GVote[]).find((v) => String(v.plan_id || '') === pid) || null);
      } else {
        setVote(null);
      }
      setErr('');
    } catch {
      /* фоновый опрос молчит: ругаться на каждую неудачу сети незачем */
    } finally {
      setLoading(false);
    }
  }, [gid, me]);

  /**
   * ДРУГАЯ ГРУППА — ЧИСТЫЙ ЭКРАН. Маршрут единственный (`dangerouslySingular`), и переход к плану
   * другой группы (пуш, карточка на главной) приходит в ТОТ ЖЕ экран с новым `gid`. Без сброса
   * открытый лист голосования переезжал на чужой план и показывал «0 hours left» без имени.
   */
  const editAsked = useRef(false);
  const shownGid = useRef(gid);
  useEffect(() => {
    if (shownGid.current === gid) return;
    shownGid.current = gid;
    setG(null); setPlan(null); setVote(null); setMode('view'); setErr(''); setFatal(''); setLoading(true);
    setAskVote(false); setAsk1to1(false); setVoteSheet(false); setDecideSheet(false); setActions(false);
    setLateSheet(false); setCantMakeSheet(false); setHowOpen(false); setWhatOpen(false); setLeaveAsk(false);
    setChangeSheet('');
    editAsked.current = false;
  }, [gid]);

  useEffect(() => { load(); }, [load]);

  /**
   * Пришли из листа «Send the plan?» кнопкой «Change» (GR.25): сразу форма плана, заполненная
   * временем и местом затеи — человек правит предложенное, а не набирает с нуля.
   */
  useEffect(() => {
    if (params.edit !== '1' || editAsked.current || !g || plan || !g.i_am_owner) return;
    editAsked.current = true;
    const dk = String((g as any).date_key || '');
    const mins = Number((g as any).minutes);
    if (dk && Number.isFinite(mins)) setWhen({ date: dk, minutes: mins, tz: deviceTz() });
    setPlace(String(g.area || ''));
    setMode('create');
  }, [params.edit, g, plan]);

  useEffect(() => {
    if (fatal) return;
    // План согласовывают несколько человек одновременно; без опроса экран показывал бы вчерашний
    // состав подтверждений. Реже, чем чат: тут события редкие.
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, [load, fatal]);

  /** Общая обёртка действий: одна занятость, один разбор ошибки, один перезапрос. */
  const act = async (fn: () => Promise<any>, after?: (r: any) => void) => {
    if (busy) return;
    setBusy(true);
    setErr('');
    try {
      const r = await fn();
      if (r?.ok === false) { setErr(explain(r?.error)); return; }
      if (r?.plan) setPlan(r.plan);
      after?.(r);
      await load();
    } catch {
      setErr(GPLAN.failed());
    } finally {
      setBusy(false);
    }
  };

  const explain = (e?: string) => {
    switch (String(e || '')) {
      case 'NEED_THREE': return GPLAN.needThree(Number(g?.need_more || 1));
      case 'TOO_LATE': return GPLAN.tooLate();
      case 'PLAN_EXISTS': return GPLAN.planExists();
      case 'NOT_ORGANIZER': return GPLAN.notOrganiser();
      case 'ROUNDS_USED_UP': return GPLAN.roundsUsedUp();
      case 'ROUNDS_LEFT': return GPLAN.roundsUsedUp();
      case 'VOTE_IN_PROGRESS': return GPLAN.voteExists();
      case 'LOCKED': return GPLAN.locked();
      case 'BAD_LINK': return GPLAN.badLink();
      case 'PLAN_INCOMPLETE': return GPLAN.hybridIncomplete();
      case 'NO_LINK': return GPLAN.hybridMissingLink();
      case 'NO_PLACE': return GPLAN.hybridMissingPlace();
      case 'NO_SUCH_PLAN': return GPLAN.gone();
      case 'ALONE': return GPLAN.aloneVersion();
      default: return GPLAN.failed();
    }
  };

  // ---- действия ---------------------------------------------------------

  /**
   * Время уходит ПАРОЙ: `when` — подпись, которую читают люди, `starts_at` — момент, по которому
   * сервер считает двухчасовой замок и отказывает в плане на прошлое. Отправить одну подпись —
   * значит завести план, который никогда не замрёт перед встречей.
   */
  const timeArgs = () => ({ when: whenLabel(when), starts_at: whenStartsAt(when) });

  const create = () =>
    act(() => gapi.planBegin(gid, me, { ...timeArgs(), place: place.trim(), link: link.trim() }, newIdem('gpb')),
        () => { setMode('view'); setPlace(''); setLink(''); });

  const confirm = () =>
    act(() => gapi.planRespond(String(plan?.id), me, 'confirm', newIdem('gpc')));

  const counter = () =>
    act(() => gapi.planRespond(String(plan?.id), me, 'counter', newIdem('gpn'),
                               { ...timeArgs(), place: place.trim() || plan?.place || '',
                                 link: link.trim() || plan?.link || '' }),
        () => { setMode('view'); setChangeSheet(''); setPlace(''); setLink(''); });

  const fix = () => act(() => gapi.planFix(String(plan?.id), me, newIdem('gpf')));
  // Версии для листа: журнал сервера, новые сверху; нет журнала (старый план) — одна текущая.
  const versions = (plan?.rounds_log && plan.rounds_log.length ? [...plan.rounds_log]
    : [{ round: Number(plan?.round || 1), by: String(plan?.proposed_by || g?.owner || ''), when: plan?.when, place: plan?.place }])
    .sort((a, b) => Number(b.round || 0) - Number(a.round || 0));
  const openFix = () => { setErr(''); setPickRound(Number(versions[0]?.round || plan?.round || 1)); };
  const fixPicked = () => {
    const rn = pickRound || 0;
    act(() => gapi.planFix(String(plan?.id), me, newIdem('gpf'), rn === Number(plan?.round || 0) ? undefined : rn),
        () => setPickRound(null));
  };

  /** GR.40: организатор закрывает план, вставший на паузу. Группа остаётся — уходит только план. */
  const cancelPlan = () => act(() => gapi.planCancel(String(plan?.id), me, newIdem('gpc')));
  const holdAnswer = (choice: 'one_on_one' | 'let_go') =>
    act(() => gapi.planHoldAnswer(String(plan?.id), me, choice, newIdem('gph')));

  /**
   * GR.40, третий выход: продолжить вдвоём.
   *
   * Это ПРОСЬБА, а не действие. Группа принадлежит обоим, и организатор, закрывающий её
   * единолично, отнимает у второго то, на что тот согласился, — поэтому здесь только вопрос,
   * а отвечает второй (GR.20, в чате группы).
   */
  /**
   * GR.45a «Я опаздываю» — и об этом узнаёт ВСЯ группа.
   *
   * Ничего не отменяет и ничего не меняет в плане: встреча в силе, просто остальные не ждут в
   * неведении. Поэтому строка уходит и в чат — человек, который смотрит переписку, а не план,
   * иначе не узнал бы вовсе.
   */
  const sayLate = () =>
    act(() => gapi.planStatus(String(plan?.id), me, 'late', newIdem('gps')),
        () => setLateSheet(false));

  const sayCantMakeIt = () =>
    act(() => gapi.planStatus(String(plan?.id), me, 'cant_make_it', newIdem('gps')),
        () => setCantMakeSheet(false));

  const askSwitch = () =>
    act(() => gapi.convertAsk(String(gid), me, newIdem('gcv')), () => setAsk1to1(false));

  const update = () =>
    act(() => gapi.planUpdate(String(plan?.id), me,
                              { ...timeArgs(), place: place.trim() || undefined,
                                link: link.trim() || undefined }, newIdem('gpu')),
        () => { setMode('view'); setChangeSheet(''); setPlace(''); setLink(''); });

  const saveLink = () =>
    act(() => gapi.planLink(String(plan?.id), me, link.trim(), newIdem('gpl')),
        () => { setMode('view'); setLink(''); });

  const saveDetails = () =>
    act(() => gapi.planDetails(String(plan?.id), me,
                               { ...(place.trim() ? { place: place.trim() } : {}),
                                 ...(link.trim() ? { link: link.trim() } : {}) }, newIdem('gpd')),
        () => { setMode('view'); setPlace(''); setLink(''); });

  const useSingleMode = (next: 'offline' | 'online') =>
    act(() => gapi.planMode(String(plan?.id), me, next, newIdem('gpmode')),
        () => { setMode('view'); setPlace(''); setLink(''); });

  const setSide = (side: 'in_person' | 'call') =>
    act(() => gapi.planSide(String(plan?.id), me, side, newIdem('gpside')));

  const openCall = () => {
    const href = String(plan?.link || '');
    if (!href) { setErr(GPLAN.hybridMissingLink()); return; }
    Linking.openURL(withScheme(href)).catch(() => setErr(GPLAN.failed()));
  };

  const switchToCall = () =>
    act(() => gapi.planSide(String(plan?.id), me, 'call', newIdem('gpside')),
        () => { setLateSheet(false); openCall(); });

  /** «Ask the group to host instead» (GRO.25a) — это реплика в общий чат, а не своя сущность. */
  const askHost = async () => {
    await gapi.post(gid, me, GPLAN.askHostMsg());
    setMode('view');
    // Группа и её план — соседи, как чат и план один на один: возвращаемся к группе, а не кладём
    // её поверх плана, из которого пришли.
    router.dismissTo({ pathname: '/group', params: { gid } });
  };

  const startVote = (kind: 'edit' | 'cancel') =>
    act(() => gapi.voteOpen(String(plan?.id), me, kind, newIdem('gvo'),
                            kind === 'edit' ? timeArgs() : {}),
        () => setAskVote(false));

  /** Раздел E: ответ «состоялось?» — одна запись, её дополняют оценкой или причиной. */
  const sendFeedback = (v: { happened: boolean; rating?: number; reason?: string }) =>
    act(() => gapi.planFeedback(String(plan?.id), me, v, newIdem('gpfb')),
        () => { setHowOpen(false); setWhatOpen(false); });

  const castVote = (yes: boolean) =>
    act(() => gapi.vote(String(vote?.id), me, yes, newIdem('gv')), () => setVoteSheet(false));

  const decide = (apply: boolean) =>
    act(() => gapi.voteDecide(String(vote?.id), me, apply, newIdem('gvd')),
        () => setDecideSheet(false));

  /** «Выйти из плана» (GR.31) и «Выйти из группы» (GR.33) — на сервере это одно: выход из группы.
   *  Группового плана без группы не бывает, и делать вид, что можно выйти из одного, оставшись в
   *  другом, значило бы обещать несуществующее состояние. */
  const leave = () =>
    act(() => gapi.leave(gid, me, newIdem('gpx')),
        () => (router.canGoBack() ? router.back() : router.replace('/home')));

  // Сами открывающиеся листы — только на виду (см. тот же приём в app/group.tsx).
  const focused = useIsFocused();
  const keptOpen = focused && !!vote && vote.decided === 'kept' && !isOwner && !keptSeen.has(String(vote.id || ''));
  /** GR.39: организатору — кто вышел и что людей стало двое. Один раз на уход. */
  const lastLeft = [...departed].sort((a, b) => Number(b.left || 0) - Number(a.left || 0))[0];
  const leftKey = lastLeft ? `${lastLeft.name}@${lastLeft.left}` : '';
  // Лист «X left the plan» — только в начале паузы; 12 часов прошли (GR.40a) — уже вопрос обоим.
  const leftOpen = focused && isOwner && plan?.state === 'below_quorum' && !plan?.hold?.ask && !!lastLeft && freshLeave && !keptSeen.has(leftKey);
  const closeLeft = () => setKeptSeen((x) => new Set(x).add(leftKey));
  const closeKept = () => setKeptSeen((x) => new Set(x).add(String(vote?.id || '')));

  // ---- какой это кадр ---------------------------------------------------

  const view = useMemo(() => frameOf({ plan, vote, isOwner, owner, me }), [plan, vote, isOwner, owner, me]);

  /**
   * Кто внёс нынешнее предложение — ФАКТОМ с сервера (`proposed_by`).
   *
   * Раньше это выводилось: встречное предложение обнуляет подтверждения и ставит одно, своё, —
   * значит единственный подтвердивший и есть предложивший. Догадка рассыпалась ровно там, где
   * кадр GR.29 и нарисован: стоило второму подтвердить, как подтвердивших становилось двое,
   * заголовок срывался в «ждём всех», а пояснение рядом продолжало называть имя. Один экран
   * говорил две разные вещи.
   *
   * Старый вывод оставлен запасным: у планов, предложенных до появления поля, его нет.
   */
  const proposer = useMemo(() => {
    const said = String(plan?.proposed_by || '').trim();
    if (said) return said;
    const conf = plan?.confirmed || [];
    return Number(plan?.round || 1) > 1 && conf.length === 1 ? String(conf[0]) : '';
  }, [plan]);

  /** Полоса-счётчик под карточкой: что считаем, из скольких и сколько осталось времени. */
  const meter = useMemo(() => {
    if (!plan) return null;
    const n = members.length;
    const now = Date.now() / 1000;
    if (vote?.state === 'open') {
      // Голосуют все, кроме организатора: решение за ним, его голос — не совет, а решение.
      const end = Number(vote.closes_at || 0);
      return { label: GPLAN.meterVote(), now: Number(vote.yes || 0) + Number(vote.no || 0), of: Math.max(1, n - 1),
               right: end ? GPLAN.endsIn(span(end - now)) : '', share: elapsed(end - VOTE_WINDOW, end, now),
               onPress: () => setVoteSheet(true) };
    }
    if (plan.fixed_by && (plan.waiting || []).length && !plan.locked) {
      const lockAt = Number(plan.starts_at || 0) - 2 * 3600;
      return { label: GPLAN.meterStaying(), now: (plan.confirmed || []).length, of: n,
               right: lockAt > now ? GPLAN.locksIn(span(lockAt - now)) : '',
               share: elapsed(Number(plan.fixed_at || 0), lockAt, now) };
    }
    if (plan.feedback_due && !plan.my_feedback) {
      // GR.47: «Answered 0 of 3 · Reply by Mon 20:30».
      const exp = Number(plan.feedback_expires_at || 0);
      const d = exp ? new Date(exp * 1000) : null;
      const by = d ? `${d.toLocaleDateString(getLang() === 'ru' ? 'ru-RU' : getLang() === 'es' ? 'es-ES' : 'en-GB', { weekday: 'short' })} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` : '';
      return { label: GPLAN.meterAnswered(), now: Number(plan.feedback_outcome?.answered || 0),
               of: Number(plan.feedback_outcome?.of || n), right: by ? GPLAN.replyBy(by) : '',
               // Спрашивают через час после начала встречи (сервер: GP_FEEDBACK_DELAY).
               share: elapsed(Number(plan.starts_at || 0) + 3600, exp, now) };
    }
    if (plan.state === 'below_quorum') {
      const h = plan.hold;
      // GR.40a / 40d: 12 часов прошли — «Answered 0 of 2 · Reply by 18:30».
      if (h?.ask && h.until) {
        return { label: GPLAN.meterAnswered(), now: Number(h.answered || 0), of: Number(h.of || n),
                 right: GPLAN.replyBy(clockOf(Number(h.until))), share: elapsed(Number(h.ask_at || 0), Number(h.until), now) };
      }
      // GR.40: «On hold 2 of 3 · Ends in 11h 40m».
      const end = Number(h?.ends_at || 0);
      return { label: GPLAN.meterOnHold(), now: n, of: Math.max(n + 1, Number(g?.min_total || 3)),
               right: end > now ? GPLAN.endsIn(span(end - now)) : '', share: elapsed(Number(h?.since || 0), end, now) };
    }
    if (plan.update && (plan.waiting || []).length) {
      return { label: GPLAN.meterAccepted(), now: Math.max(0, (plan.confirmed || []).length - 1), of: Math.max(1, n - 1), right: '' };
    }
    return null;
  }, [plan, vote, members.length, g?.min_total]);

  if (fatal) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/* Не `replace`: тот подменял бы только этот экран, оставляя под ним всю дорогу до
            группы, которой уже нет. `dismissTo` возвращает к главной, снимая её целиком. */}
        <Head title={ROOM.gone()} onBack={() => router.dismissTo('/home')} />
        <Text style={s.fatal}>{fatal}</Text>
      </View>
    );
  }

  const formMode = mode !== 'view';
  /** Карточка адреса вместо обложки — день встречи и «после»; сказавшему «не приду» — обложка (GR.46). */
  const iCant = String(plan?.my_live?.status || '') === 'cant_make_it';
  // Онлайн (GRO.45–47): та же карточка, но про ссылку — «Zoom · Mateo’s link» и «Open link».
  const addrView = (!online || !!plan?.link) && !iCant && (view === 'locked' || view === 'now' || view === 'feedback');
  const svc = callService(plan?.link);
  /** Хвост строки состава по борду: день встречи (D) и «после» (E) — свои знаки. */
  const dayView = view === 'locked' || view === 'now';
  const afterView = view === 'feedback' || view === 'answered';
  const termsForm = mode === 'create' || mode === 'suggest' || mode === 'update';
  const actionsEl = (
            <Actions
              mode={mode}
              view={view}
              busy={busy}
              plan={plan}
              vote={vote}
              online={online}
              hybrid={hybrid}
              leftForConfirm={Number(plan?.needs || 0)}
              isOwner={isOwner}
              proposer={proposer}
              owner={owner}
              onMet={() => { setRating(0); setHowOpen(true); }}
              onNotMet={(didntGo) => { setReason(didntGo ? 'couldnt_make' : ''); setWhatOpen(true); }}
              onCreateOpen={() => { setPlace(''); setLink(''); setMode('create'); }}
              onCreate={create}
              onConfirm={confirm}
              onSuggestOpen={() => { setWhen(whenFromStartsAt(plan?.starts_at, when.tz) || when); setPlace(String(plan?.place || '')); setLink(String(plan?.link || '')); setErr(''); setChangeSheet('suggest'); }}
              onSuggestSend={counter}
              onFix={openFix}
              onInviteMore={() => setFindThird(true)}
              onCancelPlan={cancelPlan}
              canConvert={!!(g as any)?.can_convert}
              onSwitch1to1={() => setAsk1to1(true)}
              onHold={holdAnswer}
              imLateSent={String((plan as any)?.my_live?.status || '') === 'late'}
              onLate={() => setLateSheet(true)}
              onCantMakeIt={() => setCantMakeSheet(true)}
              onOpenCall={openCall}
              onMoreTime={() => {}}
              onStay={confirm}
              onLeave={() => setLeaveAsk(true)}
              onOpenChat={() => router.dismissTo({ pathname: '/group', params: { gid } })}
              onAskVote={() => setAskVote(true)}
              onOpenVote={() => setVoteSheet(true)}
              onDecide={() => setDecideSheet(true)}
              onUpdateOpen={() => { setWhen(whenFromStartsAt(plan?.starts_at, when.tz) || when); setPlace(String(plan?.place || '')); setLink(''); setErr(''); setChangeSheet('update'); }}
              onUpdateSend={update}
              onAccept={confirm}
              onLinkOpen={() => setMode('link')}
              onLinkSave={saveLink}
              onDetailsOpen={() => { setPlace(''); setLink(''); setMode('details'); }}
              onDetailsSave={saveDetails}
              onUseSingleMode={useSingleMode}
              onAskHost={askHost}
              onCancelForm={() => { setMode('view'); setErr(''); }}
            />
  );

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/* В форме — циферблат времени, который крутят пальцем; протяжка «назад» на iOS 26 идёт от
            любого места и закрыла бы экран вместе с недописанной формой. Выход из формы — стрелкой. */}
        <Stack.Screen options={{ gestureEnabled: !formMode && !dragging }} />
        {/* Фон — ровный «Ambient · glass pilot» #F5F1EC (s.wrap), без пятен: так на всех разделах
            борда «GR · Offline — new layout» (A–E), как и на экране группы. */}
        <Head
          title={g?.title || ''}
          onActions={() => setActions(true)}
          onBack={() => {
            if (formMode) { setMode('view'); setErr(''); return; }
            router.canGoBack() ? router.back() : router.replace('/home');
          }}
        />

        {/* scrollEnabled выключается на время вращения циферблата: иначе жест по кругу
            перехватывает список, и стрелка прыгает. Та же пара, что в мастере интента. */}
        <ScrollView onScroll={navCollapse} scrollEventThrottle={16} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled"
                    scrollEnabled={!dragging}>
          {loading && !g ? <ActivityIndicator style={{ marginTop: 24 }} color={color.primary} /> : null}

          {/* Заголовок и пояснение — они и есть кадр: на борде меняются только эти две строки. */}
          {/* Кадр GR.26: состояние гарнитурой шапок 15/20, пояснение Geist 13/18. */}
          {view === 'feedback' && mode === 'view' ? (
            /* GR.47: вопрос стоит голубой плашкой вместо заголовка. */
            <InfoBox title={formTitle(mode, view, { plan, vote, owner, online, hybrid, proposer, isOwner, me, g })}
                     note={formNote(mode, view, { plan, vote, owner, online, hybrid, g, isOwner, me })} question />
          ) : (
          <View style={s.status}>
            <Text style={[s.title, { fontFamily: labelFamily(lang) }]}>
              {formTitle(mode, view, { plan, vote, owner, online, hybrid, proposer, isOwner, me, g })}
            </Text>
            <Text style={s.note}>{formNote(mode, view, { plan, vote, owner, online, hybrid, g, isOwner, me })}</Text>
          </View>
          )}

          {/*
            День встречи и после (GR.45–50): вместо обложки — карточка адреса с маршрутом. Сейчас
            важно, КУДА идти, а не как выглядела затея: адрес крупно, под ним «Starts now» /
            «Happening now», кнопка «Open the route». После встречи — адрес и когда это было.
          */}
          {plan && mode === 'view' && addrView ? (
            <AddressCard
              place={online ? (view === 'feedback' ? GPLAN.callPast(svc) : GPLAN.linkWhose(svc, owner, isOwner)) : venue(plan)}
              sub={view === 'feedback' ? (pastWhen(Number(plan.starts_at || 0)) || String(plan.when || ''))
                : view === 'now' ? (cantOthers(plan, me).length ? GPLAN.happeningNow() : GPLAN.startsNow())
                : online ? GPLAN.linkLeaves(svc)
                : String(plan.when || '')}
              past={view === 'feedback'}
              link={online ? String(plan.link || '') : ''}
            />
          ) : null}

          {/* Карточка плана — общая для всех кадров. В форме показывает то, что человек вводит
              прямо сейчас: иначе он правит вслепую и сверяет с памятью. */}
          {(plan || formMode) && !(mode === 'view' && addrView) ? (
            <PlanCard
              title={g?.title || ''}
              when={termsForm ? whenLabel(when) : String(plan?.when || '')}
              /* «было …» — только в форме правки: на кадрах GR.32a/33 прежнее время названо в пояснении. */
              was={mode === 'update' ? String(plan?.when || '') : ''}
              venueLine={
                termsForm && !online
                  ? (place || plan?.place || GPLAN.placePh())
                  : online && mode === 'view' && plan?.link && (view === 'now' || view === 'locked')
                    ? GPLAN.linkWhose(svc, owner, isOwner)          // GRO.46 «Zoom · Mateo’s link»
                  : online && mode === 'view' && plan?.link && view === 'answered'
                    ? GPLAN.callPast(svc)                           // GRO.48 «Video call · Zoom»
                  : online && plan?.link && !termsForm
                    ? GPLAN.linkWhose('', owner, isOwner)           // GRO.26–38 «Video call · your link»
                  : venue({ ...(plan || {}), place: place || plan?.place, mode: online ? 'online' : 'offline' })
              }
              online={online}
              hybrid={hybrid}
              callLine={hybrid ? callVenue({ ...(plan || {}), link: link || plan?.link }) : ''}
              placeUnchanged={mode === 'update' && !place.trim()}
              lockedLine={mode === 'view' && iCant ? GPLAN.lockedLine() : ''}
            />
          ) : null}

          {/* Индикатор раундов — только пока согласовывают. На утверждённом плане его нет и на борде. */}
          {/* Виден и в форме: раунд тратится ровно в ней, и «Round 2 of 3» нужно перед отправкой,
              а не после. Скрытый на время формы, он пропадал в самый нужный момент. */}
          {plan?.state === 'proposed' && mode === 'view' ? (
            <RoundBar round={Number(plan.round || 1)} max={Number(plan.max_rounds || 3)} />
          ) : null}

          {/* Полосы-счётчики борда: «Staying 2 of 3 · Locks in 2h» после закрепления (GR.30/31),
              «Accepted 0 of 2» после правки (GR.32a/33), «Vote 1 of 2 · Ends in 4h» (GR.36). */}
          {mode === 'view' && meter ? (
            <Pressable disabled={!meter.onPress} onPress={meter.onPress} accessibilityRole={meter.onPress ? 'button' : undefined}>
              <MeterBar label={meter.label} now={meter.now} of={meter.of} right={meter.right} share={(meter as any).share} />
            </Pressable>
          ) : null}

          {/* Онлайн без ссылки — группа видит «ссылка будет», организатор её ставит (GRO.25a). */}
          {(plan?.needs_link || plan?.needs_place) && mode === 'view' ? (
            <View style={s.warn}>
              <Text style={s.warnText}>
                {plan?.needs_place ? GPLAN.hybridMissingPlace()
                  : hybrid ? GPLAN.hybridMissingLink() : GPLAN.linkComing()}
              </Text>
            </View>
          ) : null}

          {/* Формы. Поля одни и те же, потому что предлагают всегда одно и то же — время и место. */}
          {mode === 'create' || mode === 'suggest' || mode === 'update' ? (
            <View style={s.form}>
              {/* Кадр GR.09: чипы дат, циферблат, часы и минуты — тот же компонент, что в мастере
                  интента. Место остаётся полем: у него нет готового списка, а район приезжает
                  из интента группы. */}
              <WhenPicker value={when} onChange={setWhen} onDragChange={setDragging} />
              {!online ? (
                <AddressField
                  style={s.input} value={place} onChange={setPlace} onPick={(h) => setPlace(h.label)}
                  placeholder={GPLAN.placePh()}
                />
              ) : null}
              {hybrid ? (
                <TextInput
                  style={s.input} value={link} onChangeText={setLink}
                  placeholder={GPLAN.linkPh()} placeholderTextColor={color.neutral400}
                  autoCapitalize="none" autoCorrect={false} keyboardType="url"
                />
              ) : null}
            </View>
          ) : null}

          {mode === 'details' ? (
            <View style={s.form}>
              {plan?.needs_place ? (
                <AddressField style={s.input} value={place} onChange={setPlace} onPick={(h) => setPlace(h.label)}
                              placeholder={GPLAN.placePh()} />
              ) : null}
              {plan?.needs_link ? (
                <TextInput style={s.input} value={link} onChangeText={setLink}
                           placeholder={GPLAN.linkPh()} placeholderTextColor={color.neutral400}
                           autoCapitalize="none" autoCorrect={false} keyboardType="url" />
              ) : null}
            </View>
          ) : null}

          {mode === 'link' ? (
            <View style={s.form}>
              <TextInput
                style={s.input} value={link} onChangeText={setLink}
                placeholder={GPLAN.linkPh()} placeholderTextColor={color.neutral400}
                autoCapitalize="none" autoCorrect={false} keyboardType="url"
              />
            </View>
          ) : null}

          {/* Состав со статусами — колонка, которая на борде есть на каждом кадре. */}
          {/* GR.39: кто-то вышел, но людей хватает — экран говорит об этом раньше, чем спросят. */}
          {freshLeave && plan && plan.state !== 'below_quorum' && plan.state !== 'cancelled' ? (
            <Text style={s.stillOn}>{GPLAN.stillOn(members.length)}</Text>
          ) : null}

          {roster.length ? (
            <View style={s.roster}>
              {roster.map((m, i) => {
                const nm = String(m.name || '');
                const org = !!owner && nm.toLowerCase() === owner.toLowerCase();
                const stt = m.gone
                  ? { text: view === 'holdClosed' ? GPLAN.stLeftPlan() : GPLAN.stLeft(leftAgo(m.left)), tone: 'warn' as const, done: false }
                  : boardState(nm, plan || {}, vote, { proposer, mine: isMe(nm, pidOf(m, 'name'), me), org });
                const line = plan ? stt.text : (org ? GPLAN.roleOrganiser() : GPLAN.stInGroup());
                /*
                  ЦВЕТ СТАТУСА — ИЗ БОРДА: зелёный «подтвердил / предложил / остаётся», коралловый
                  «нужен твой ответ», янтарный «вышел / опаздывает / не сможет», серый — «ждём».
                */
                const tone = !plan ? s.stMuted
                  : stt.tone === 'ok' ? s.stOk : stt.tone === 'turn' ? s.stTurn : stt.tone === 'warn' ? s.stWarn : s.stMuted;
                return (
                  <View key={nm + i} style={s.memberRow}>
                    {/*
                      Заглушка рисуется ВСЕГДА, фото ложится поверх. Так у строки есть кружок с
                      человечком, пока фото едет, — и остаётся, если оно не доедет вовсе. Замерено
                      на проде: /api/onboarding/photo отдаёт 51 КБ за тридцать секунд через
                      туннель, и всё это время на месте человека была дыра.
                    */}
                    <View style={[s.av, s.avEmpty]}>
                      <IconPerson size={18} />
                      {m.photo ? (
                        <Image source={{ uri: mediaUrl(String(m.photo)) }}
                               style={[s.av, StyleSheet.absoluteFill]} />
                      ) : null}
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={s.nameRow}>
                        <Text style={s.memberName} numberOfLines={1}>
                          {isMe(nm, pidOf(m, 'name'), me) ? GPLAN.you() : ROOM.nameAge(nm, (m as any).age)}
                        </Text>
                        {org ? (
                          <View style={s.orgBadge}>
                            <Text style={s.orgText}>{GPLAN.roleOrganiser().toLowerCase()}</Text>
                          </View>
                        ) : null}
                      </View>
                      <Text style={[s.memberState, tone]} numberOfLines={1}>{line}</Text>
                    </View>
                    {plan ? (
                      // Хвост строки — чернилами, как на борде (Trailing icon: foreground #181B22).
                      // День встречи (GR.45–46b): метка места, «опаздывает» — часы, «не придёт» —
                      // таймер. После (GR.47–50): часы только у того, кто ещё не ответил.
                      afterView ? (stt.tone === 'muted' ? <IconClock size={18} c={INK} /> : null)
                        : dayView && !m.gone ? (
                          liveOf(plan, nm) === 'late' ? <IconClock size={18} c={INK} />
                            : liveOf(plan, nm) === 'cant_make_it' ? <IconTimer size={18} c={INK} />
                            : <IconPin size={18} c={INK} />)
                        : m.gone ? <IconExit size={18} c={INK} />
                        : view === 'holdClosed' && stt.tone === 'warn' ? <IconCalendarX size={18} c={INK} />
                        : stt.done ? <IconCalendarCheck size={18} c={INK} />
                        : <IconClock size={18} c={INK} />
                    ) : null}
                  </View>
                );
              })}
            </View>
          ) : null}

          {/* GR.45a: встреча идёт — Kleal её не видит и ничего не записывает; спросит потом. */}
          {view === 'now' && mode === 'view' && !cantOthers(plan || {}, me).length
            && String(plan?.my_live?.status || '') !== 'cant_make_it' ? (
            <InfoBox title={online ? GPLAN.kleaBlindCall(svc) : GPLAN.kleaBlind()}
                     note={online ? GPLAN.kleaBlindNoteCall(members.length) : GPLAN.kleaBlindNote(members.length)} />
          ) : null}

          {hybrid && plan?.details_ready && mode === 'view' ? (
            <View style={s.sideBox}>
              <Text style={s.sideTitle}>{GPLAN.chooseSide()}</Text>
              <View style={s.sideTabs}>
                <Pressable accessibilityRole="button" onPress={() => setSide('in_person')}
                           style={[s.sideTab, plan?.my_side === 'in_person' && s.sideTabOn]}>
                  <IconPin size={16} c={plan?.my_side === 'in_person' ? color.onPrimary : color.muted} />
                  <Text style={[s.sideText, plan?.my_side === 'in_person' && s.sideTextOn]}>{GPLAN.inPerson()}</Text>
                </Pressable>
                <Pressable accessibilityRole="button" onPress={() => setSide('call')}
                           style={[s.sideTab, plan?.my_side === 'call' && s.sideTabOn]}>
                  <IconVideo size={16} c={plan?.my_side === 'call' ? color.onPrimary : color.muted} />
                  <Text style={[s.sideText, plan?.my_side === 'call' && s.sideTextOn]}>{GPLAN.onCall()}</Text>
                </Pressable>
              </View>
              <Text style={s.sideCount}>
                {GPLAN.sideCounts(Number(plan?.side_counts?.in_person || 0), Number(plan?.side_counts?.call || 0))}
              </Text>
            </View>
          ) : null}

          {/* Ссылка на звонок — кнопкой, а не текстом: её открывают, а не переписывают. */}
          {/* Онлайн-план (борд «GR · Online»): ссылку открывают из карточки в день звонка (GRO.45),
              до того строки нет — ссылка открывается за 10 минут до начала. Гибрид — как был. */}
          {hybrid && plan?.link && mode === 'view' ? (
            <Pressable style={s.linkRow} accessibilityRole="link"
                       onPress={openCall}>
              <IconLink size={16} c={color.infoText} />
              <Text style={s.linkText}>{GPLAN.openLink()}</Text>
            </Pressable>
          ) : null}

          {err ? <Text style={s.err}>{err}</Text> : null}

          {/* Кнопки кадра — СРАЗУ под содержимым, как на каждом кадре борда (GR.26, GR.45…), а не
              прижатыми к низу экрана: на коротком плане между составом и кнопками была пустота. */}
          {formMode ? null : <View style={s.inlineActions}>{actionsEl}</View>}
        </ScrollView>

        {/* В форме кнопки прижаты к клавиатуре; в просмотре они идут сразу под составом (борд). */}
        {formMode ? (
          <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>{actionsEl}</View>
        ) : null}
        {formMode ? null : <BottomNav active="intents" />}

        <PlanChangeSheet
          visible={!!changeSheet}
          title={changeSheet === 'update'
            ? (plan?.update ? GPLAN.editTheUpdate() : online ? GPLAN.changeTimeOrLink() : GPLAN.changeTimeOrPlace())
            : isOwner ? (proposer && eqName(proposer, owner) ? GPLAN.editTheChange() : GPLAN.changeThePlan()) : GPLAN.suggest()}
          sendLabel={changeSheet === 'update' ? GPLAN.sendUpdate() : GPLAN.sendChange()}
          was={String(plan?.when || '')}
          value={when}
          onChange={setWhen}
          place={place}
          onPlace={setPlace}
          placeNote={changeSheet === 'update'
            ? GPLAN.placeNoteUpdate(GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me)))
            : GPLAN.placeNoteSuggest(GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me)))}
          busy={busy}
          error={changeSheet ? err : ''}
          online={online}
          link={link}
          currentLink={String(plan?.link || '')}
          onLink={setLink}
          linkWhose={GPLAN.linkWhose('', owner, isOwner)}
          linkCurrentTitle={isOwner
            ? T(`Твоя ссылка${svc ? ' ' + svc : ''}`, `Your ${svc ? svc + ' ' : ''}link`, `Tu enlace${svc ? ' de ' + svc : ''}`)
            : T(`Ссылка ${owner}${svc ? ' в ' + svc : ''}`, `${owner}’s ${svc ? svc + ' ' : ''}link`, `Enlace${svc ? ' de ' + svc : ''} de ${owner}`)}
          linkNote={changeSheet === 'update'
            ? T(`${GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me))} получат новую ссылку вместе с изменением.`,
                `${GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me))} get the new link together with the update.`,
                `${GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me))} reciben el nuevo enlace junto con el cambio.`)
            : T(`${GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me))} получат ссылку вместе с планом. Она откроется за 10 минут до звонка.`,
                `${GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me))} get your link with the plan. It opens 10 minutes before the call.`,
                `${GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me))} reciben tu enlace con el plan. Se abre 10 minutos antes de la llamada.`)}
          onSend={changeSheet === 'update' ? update : counter}
          onClose={() => { setChangeSheet(''); setErr(''); }}
        />

        {/* GR.35 — попросить группу. Лист, потому что это вопрос, а не экран. */}
        {/* GR.35a — попросить группу. Время, на которое просят перенести, выбирается здесь же:
            «давайте перенесём» без времени — не предложение, и голосовать по нему не о чем. */}
        <Sheet visible={askVote} onClose={() => setAskVote(false)} title={GPLAN.askSheetTitle()}>
          <SheetText lead={GPLAN.askTitle()}
                     note={isOwner ? GPLAN.askNoteMine() : GPLAN.askNote(owner || GPLAN.roleOrganiser())}>
            <WhenPicker value={when} onChange={setWhen} />
          </SheetText>
          <GlassPill tone="brand" label={GPLAN.startVote()} busy={busy} onPress={() => startVote('edit')} style={s.sheetBtn} />
          <GlassPill tone="dark" label={GPLAN.notNow()} onPress={() => setAskVote(false)} style={s.sheetBtn} />
        </Sheet>

        {/* GR.40, средний выход. Лист повторяет тот, что в чате группы, дословно по смыслу: решение
            принимают ДВОЕ, и человек читает это ровно в момент, когда нажимает. */}
        <PlanSheet open={ask1to1} onClose={() => setAsk1to1(false)}
               title={GPLAN.switchAskTitle(otherName)}
               body={GPLAN.switchAskNote(otherName)}>
          <GlassPill tone="brand" label={GPLAN.switchAskSend(otherName)} busy={busy} onPress={askSwitch} style={s.sheetBtn} />
          <GlassPill tone="dark" label={GPLAN.switchKeep()} onPress={() => setAsk1to1(false)} style={s.sheetBtn} />
        </PlanSheet>

        <Sheet visible={actions} onClose={() => setActions(false)} title={T('Действия', 'Actions', 'Acciones')}>
          <SheetItem
            danger
            label={T('Сообщить о проблеме', 'Report a problem', 'Reportar un problema')}
            onPress={() => {
              setActions(false);
              setTimeout(() => router.navigate({
                pathname: '/group-report', params: { gid, title: String(g?.title || '') },
              }), 250);
            }}
          />
          <GlassPill tone="dark" label={T('Отмена', 'Cancel', 'Cancelar')} onPress={() => setActions(false)} style={s.sheetBtn} />
        </Sheet>

        <Sheet visible={lateSheet} onClose={() => setLateSheet(false)} title={online ? GPLAN.tellLateTitleCall() : GPLAN.tellLateTitle2()}>
          {/* GR.45d: сколько осталось, кто увидит и что ничего не отменяется. */}
          <SheetText lead={formTitle('view', 'locked', { plan, vote, owner, online, hybrid, proposer, isOwner, me: '', g })}
                     note={GPLAN.tellLateNote2(GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me)))} />
          {hybrid && plan?.link ? (
            <GlassPill tone="brand" label={GPLAN.switchToCall()} busy={busy} onPress={switchToCall} style={s.sheetBtn} />
          ) : null}
          <GlassPill tone={hybrid && plan?.link ? 'light' : 'brand'} label={online ? GPLAN.imLateCall() : GPLAN.imLate()}
                     disabled={busy} onPress={sayLate} style={s.sheetBtn} />
          <GlassPill tone="dark" label={GPLAN.neverMind()} onPress={() => setLateSheet(false)} style={s.sheetBtn} />
        </Sheet>

        <Sheet visible={cantMakeSheet} onClose={() => setCantMakeSheet(false)} title={online ? GPLAN.cantMakeTitleCall() : GPLAN.cantMakeTitle2()}>
          {/* GR.46b: «It's happening now» и что встреча для остальных в силе. */}
          <SheetText lead={GPLAN.nowTitle()} note={(online ? GPLAN.cantMakeNoteCall : GPLAN.cantMakeNote2)(GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me)))} />
          <GlassPill tone="brand" label={GPLAN.cantMakeConfirm()} busy={busy} onPress={sayCantMakeIt} style={s.sheetBtn} />
          <GlassPill tone="dark" label={GPLAN.neverMind()} onPress={() => setCantMakeSheet(false)} style={s.sheetBtn} />
        </Sheet>

        {/* GR.49 — «How was it?»: оценка необязательна, видит её только Kleal. */}
        <Sheet visible={howOpen} onClose={() => setHowOpen(false)} title={GPLAN.howWas()}>
          <SheetText lead={GPLAN.howWasLead()}>
            <View style={s.rateRow}>
              {[{ v: 5, l: GPLAN.rateGreat() }, { v: 3, l: GPLAN.rateFine() }, { v: 1, l: GPLAN.rateBad() }].map((r) => (
                <Pressable key={r.v} accessibilityRole="radio" accessibilityState={{ selected: rating === r.v }}
                           onPress={() => setRating(rating === r.v ? 0 : r.v)}
                           style={[s.rateChip, rating === r.v && s.rateChipOn]}>
                  <Text style={[s.rateText, rating === r.v && s.rateTextOn]} numberOfLines={1}>{r.l}</Text>
                </Pressable>
              ))}
            </View>
          </SheetText>
          <SheetText note={GPLAN.howWasNote()} />
          <GlassPill tone="brand" label={GPLAN.sendAnswer()} busy={busy} style={s.sheetBtn}
                     onPress={() => sendFeedback({ happened: true, ...(rating ? { rating } : {}) })} />
          <GlassPill tone="dark" label={GPLAN.reportProblem()} style={s.sheetBtn}
                     onPress={() => { setHowOpen(false); setTimeout(() => router.navigate({ pathname: '/group-report', params: { gid, title: String(g?.title || '') } }), 250); }} />
        </Sheet>

        {/* GR.48a — «What happened?»: причина из закрытого списка, остальным не показывается. */}
        <Sheet visible={whatOpen} onClose={() => setWhatOpen(false)} title={GPLAN.whatHappened()}>
          <SheetText lead={GPLAN.whatHappenedLead()}>
            <View style={s.reasonList}>
              {(online ? GPLAN.reasonsCall() : GPLAN.reasons()).map((r) => (
                <Pressable key={r.code} accessibilityRole="radio" accessibilityState={{ selected: reason === r.code }}
                           onPress={() => setReason(r.code)} style={[s.reasonRow, reason === r.code && s.reasonRowOn]}>
                  <Text style={s.reasonText}>{r.label}</Text>
                  {reason === r.code ? <IconCheck /> : null}
                </Pressable>
              ))}
            </View>
          </SheetText>
          <SheetText note={GPLAN.whatHappenedNote()} />
          <GlassPill tone="brand" label={GPLAN.sendAnswer()} busy={busy} disabled={!reason} style={s.sheetBtn}
                     onPress={() => sendFeedback({ happened: false, reason })} />
          <GlassPill tone="dark" label={GPLAN.skip()} style={s.sheetBtn} onPress={() => setWhatOpen(false)} />
        </Sheet>

        {/* GR.29a — выбрать финальную версию из трёх раундов и закрепить её. */}
        <Sheet visible={pickRound !== null} onClose={() => setPickRound(null)} title={GPLAN.fix()}>
          <View style={s.pickWrap}>
            <Text style={[s.pickHead, { fontFamily: labelFamily(lang) }]}>{GPLAN.pickFinal()}</Text>
            <View style={s.pickList}>
              {versions.map((v) => {
                const on = Number(v.round) === pickRound;
                const line = [String(v.when || '').replace(/,\s*(\d)/, ' · $1'), String(v.place || '')].filter(Boolean).join(' · ');
                return (
                  <Pressable key={String(v.round)} accessibilityRole="radio" accessibilityState={{ selected: on }}
                             onPress={() => { setErr(''); setPickRound(Number(v.round)); }}
                             style={[s.pickRow, on && s.pickRowOn]}>
                    <IconCalendar size={18} c={color.primary} />
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={s.pickLine} numberOfLines={1}>{line}</Text>
                      <Text style={s.pickMeta} numberOfLines={1}>
                        {GPLAN.versionMeta(String(v.by || ''), Number(v.round || 1), isMe(v.by, (v as any).by_id, me), Number(v.round) === 1)}
                      </Text>
                    </View>
                    {on ? <IconCheck size={20} c={color.primary} /> : <View style={{ width: 20 }} />}
                  </Pressable>
                );
              })}
            </View>
            <Text style={s.pickNote}>{GPLAN.pickFinalNote()}</Text>
            {err ? <Text style={s.pickErr}>{err}</Text> : null}
          </View>
          <GlassPill tone="brand" label={GPLAN.fixThis()} busy={busy} style={s.sheetBtn} onPress={fixPicked} />
          <GlassPill tone="dark" label={GPLAN.back()} style={s.sheetBtn} onPress={() => setPickRound(null)} />
        </Sheet>

        {/* GR.40f — найти третьего: место открыто, пока план на паузе; ищет поиск группы в чате. */}
        <Sheet visible={findThird} onClose={() => setFindThird(false)} title={GPLAN.findThirdTitle()}>
          <SheetText lead={GPLAN.findThirdLead()}
                     note={GPLAN.findThirdNote(String(lastLeft?.name || ''),
                       String((members.find((m) => !isMe(m.name, pidOf(m, 'name'), me)) || {}).name || ''))} />
          <GlassPill tone="brand" label={GPLAN.openSpot()} style={s.sheetBtn}
                     onPress={() => { setFindThird(false); router.dismissTo({ pathname: '/group', params: { gid, act: 'invite' } }); }} />
          <GlassPill tone="dark" label={GPLAN.notNow()} style={s.sheetBtn} onPress={() => setFindThird(false)} />
        </Sheet>

        {/* GR.41 — выйти из плана: необратимо, и остальных надо предупредить, что будет с планом. */}
        <Sheet visible={leaveAsk} onClose={() => setLeaveAsk(false)} title={GPLAN.leaveAskTitle(String(g?.title || ''))}>
          <SheetText lead={GPLAN.leaveLead()}
                     note={GPLAN.leaveNote(GPLAN.names(othersOf(members.map((m) => String(m.name || '')), me)), owner,
                                           members.length - 1 < Number(g?.min_total || 3))} />
          <GlassPill tone="brand" label={GPLAN.leavePlan()} busy={busy} style={s.sheetBtn}
                     onPress={() => { setLeaveAsk(false); leave(); }} />
          <GlassPill tone="dark" label={GPLAN.stayBtn()} style={s.sheetBtn} onPress={() => setLeaveAsk(false)} />
        </Sheet>

        {/* GR.36 — голос. Совещательность повторена здесь же: человек читает это в момент выбора. */}
        {/* GR.36a — голос: «Change the plan?», сколько осталось, что предлагают и что это совет. */}
        <Sheet visible={voteSheet && vote?.state === 'open'} onClose={() => setVoteSheet(false)} title={GPLAN.voteSheetTitle2(String(vote?.kind || 'edit'))}>
          <SheetText lead={GPLAN.hoursLeftLead(hoursLeft(vote?.closes_at))}
                     note={vote?.kind === 'cancel'
                       ? GPLAN.suggestsCancel(String(vote?.by || ''), owner || GPLAN.roleOrganiser())
                       : GPLAN.suggestsInstead(String(vote?.by || ''), String(vote?.proposal?.when || ''), owner || GPLAN.roleOrganiser())} />
          {vote?.my_vote === undefined || vote?.my_vote === null ? (
            <>
              <GlassPill tone="brand" label={GPLAN.voteYes(String(vote?.kind || 'edit'))} busy={busy}
                         onPress={() => castVote(true)} style={s.sheetBtn} />
              <GlassPill tone="dark" label={GPLAN.voteNo()} onPress={() => castVote(false)} style={s.sheetBtn} />
            </>
          ) : (
            <GlassPill tone="dark" label={GPLAN.gotIt()} onPress={() => setVoteSheet(false)} style={s.sheetBtn} />
          )}
        </Sheet>

        {/* GR.37a — числа и решение. Только организатору: у остальных этой кнопки на кадре нет. */}
        <Sheet visible={decideSheet && !!vote && !vote.decided} onClose={() => setDecideSheet(false)} title={GPLAN.closedTitle()}>
          <SheetText lead={GPLAN.tally2(Number(vote?.yes || 0), Number(vote?.no || 0))} note={GPLAN.decideNote()} />
          <GlassPill tone="brand" busy={busy} onPress={() => decide(true)} style={s.sheetBtn}
                     label={vote?.kind === 'cancel' ? GPLAN.applyCancel() : GPLAN.applyChange()} />
          <GlassPill tone="dark" label={GPLAN.keepIt()} onPress={() => decide(false)} style={s.sheetBtn} />
        </Sheet>

        <Sheet visible={leftOpen && !keptOpen} onClose={closeLeft} title={GPLAN.leftSheetTitle(String(lastLeft?.name || ''))}>
          <SheetText lead={GPLAN.downToTwo()} note={GPLAN.downToTwoNote()} />
          <GlassPill tone="brand" label={GPLAN.seeOptions()} style={s.sheetBtn} onPress={closeLeft} />
          <GlassPill tone="dark" label={GPLAN.openChat()} style={s.sheetBtn}
                     onPress={() => { closeLeft(); router.dismissTo({ pathname: '/group', params: { gid } }); }} />
        </Sheet>

        {/* GR.38a — итог участнику: организатор оставил план. Показывается один раз на голосование. */}
        <Sheet visible={keptOpen} onClose={closeKept} title={GPLAN.keptTitle(owner)}>
          <SheetText lead={GPLAN.keptLead(String(plan?.when || ''))}
                     note={GPLAN.keptSheetNote(Number(vote?.yes || 0), Number(vote?.no || 0))} />
          <GlassPill tone="brand" label={GPLAN.openChat()} style={s.sheetBtn}
                     onPress={() => { closeKept(); router.dismissTo({ pathname: '/group', params: { gid } }); }} />
          <GlassPill tone="dark" label={GPLAN.gotIt()} style={s.sheetBtn} onPress={closeKept} />
        </Sheet>
      </View>
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------- кадры

/**
 * Какой сейчас кадр борда. Один расчёт на весь экран: заголовок, пояснение и кнопки обязаны
 * говорить об одном и том же, а разложенные по трём условиям они разъезжаются — на GR.30 текст
 * про закрепление уже стоит, а кнопки ещё старые.
 *
 * Порядок проверок — от самого узкого к общему, и он же порядок приоритетов: личный выбор
 * («тебя зафиксировали», «прими или выйди») важнее общего состояния плана, потому что это
 * единственное, чего ждут именно от тебя.
 */
type Frame =
  | 'none' | 'proposed' | 'confirmed' | 'stayOrLeave' | 'acceptOrLeave'
  | 'voteOpen' | 'voteDecide' | 'voteWait' | 'locked' | 'now' | 'below' | 'closed'
  | 'feedback' | 'answered' | 'holdAsk' | 'holdClosed';

function frameOf(a: { plan: GPlan | null; vote: GVote | null; isOwner: boolean; owner: string; me: string }): Frame {
  const { plan, vote, isOwner } = a;
  if (!plan) return 'none';
  // GR.40b / GR.40e: план закрылся с паузы — свой кадр, а не общий «отменён».
  if (plan.state === 'cancelled') return plan.hold?.closed ? 'holdClosed' : 'closed';
  // Раздел E: после встречи — «Did you meet?» (GR.47/50), ответил — «Your answer is saved» (GR.48).
  if (plan.feedback_due) return plan.my_feedback ? 'answered' : 'feedback';
  if (plan.state === 'done') return plan.my_feedback ? 'answered' : 'closed';
  if ((plan as any).started) return 'now';
  if (plan.state === 'locked') return 'locked';
  if (plan.state === 'below_quorum') return plan.hold?.ask ? 'holdAsk' : 'below';
  if (plan.stay_or_leave) return 'stayOrLeave';
  if (plan.accept_or_leave) return 'acceptOrLeave';
  if (vote?.state === 'open') return 'voteOpen';
  if (vote?.state === 'closed' && !vote?.decided) return isOwner ? 'voteDecide' : 'voteWait';
  // Последний раунд — тот же кадр «proposed» (GR.29: «Confirm» и «Fix the plan»). Отдельного кадра
  // «1 confirmed, 2 didn't» на борде нет: фиксация — это лист выбора версии (GR.29a).
  if (plan.state === 'proposed') return 'proposed';
  return 'confirmed';
}

/**
 * Голубая плашка борда (GR.45a «Kleal can't see the meetup», GR.47 «Did you meet?»): стекло
 * info, знак слева от заголовка, заголовок и пояснение цветом info-text.
 */
function InfoBox({ title, note, question }: { title: string; note: string; question?: boolean }) {
  return (
    <View style={s.infoShadow}>
      <GlassSurface tone="info" radius={20} style={s.infoBox}>
        <View style={s.infoHead}>
          {question ? <Text style={s.infoQ}>?</Text> : <IconInfo size={16} c={color.infoText} />}
          <Text style={s.infoTitle}>{title}</Text>
        </View>
        <Text style={s.infoNote}>{note}</Text>
      </GlassSurface>
    </View>
  );
}

/**
 * Карточка адреса дня встречи (GR.45/45a/46a): знак места, адрес крупно, под ним «Starts now»,
 * ниже коралловая «Open the route». После встречи (GR.47) — без кнопки: адрес и когда это было.
 */
function AddressCard({ place, sub, past, link }: { place: string; sub: string; past?: boolean; link?: string }) {
  // Онлайн (GRO.45–47): вместо адреса — ссылка на звонок, вместо маршрута — «Open link».
  const route = () => {
    if (link) {
      Linking.openURL(withScheme(link)).catch(() => {});
      return;
    }
    const q = encodeURIComponent(place);
    Linking.openURL(Platform.OS === 'ios' ? `http://maps.apple.com/?q=${q}` : `geo:0,0?q=${q}`).catch(() => {});
  };
  const Mark = link ? IconVideo : IconPin;
  return (
    <View style={s.cardShadow}>
      <GlassSurface tone="light" radius={20} style={s.addr}>
        <View style={s.addrRow}>
          {past ? null : <Mark size={30} c={color.primary} />}
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={s.addrPlace} numberOfLines={2}>{place}</Text>
            <View style={s.addrSubRow}>
              {past ? <IconClock size={14} c={INK} /> : null}
              <Text style={[s.addrSub, past && { color: INK }]} numberOfLines={1}>{sub}</Text>
            </View>
          </View>
          {past ? <Mark size={30} c={color.primary} /> : null}
        </View>
        {past ? null : (
          <GlassPill tone="brand" small label={link ? GPLAN.openLink2() : GPLAN.openRoute()} onPress={route} style={s.addrBtn} />
        )}
      </GlassSurface>
    </View>
  );
}

/** «18:30» — срок сегодня; другой день — «Fri 18:30» (GR.40a «Reply by 18:30»). */
function clockOf(sec: number): string {
  const d = new Date(sec * 1000);
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  if (d.toDateString() === new Date().toDateString()) return hm;
  const loc = getLang() === 'ru' ? 'ru-RU' : getLang() === 'es' ? 'es-ES' : 'en-GB';
  return `${d.toLocaleDateString(loc, { weekday: 'short' })} ${hm}`;
}

/** «2h», «1h 37m», «45m» — сколько осталось до срока. */
function span(sec: number): string {
  const m = Math.max(0, Math.round(sec / 60));
  const h = Math.floor(m / 60);
  if (h >= 1) return m % 60 ? `${h}${T('ч', 'h', 'h')} ${m % 60}${T('м', 'm', 'm')}` : `${h}${T('ч', 'h', 'h')}`;
  return `${m}${T('м', 'm', 'm')}`;
}

/**
 * Подпись человека в составе — по кадрам «GR · Offline — new layout»: «Proposed this»,
 * «Confirmed · Suggested this», «Your answer needed», «Staying», «Deciding», «Your call»,
 * «Changed it», «Accepted», «Asked to change it», «Your vote needed», «Voted». Тон — цвет строки.
 */
/** GR.47 / GR.50: когда это было — «Yesterday, 20:30», «Friday, 20:30»; раньше недели — дата. */
function pastWhen(at: number, nowMs = Date.now()): string {
  if (!at) return '';
  const d = new Date(at * 1000);
  const loc = getLang() === 'ru' ? 'ru-RU' : getLang() === 'es' ? 'es-ES' : 'en-GB';
  const days = Math.round((new Date(nowMs).setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 86400000);
  const day = days === 0 ? T('Сегодня', 'Today', 'Hoy') : days === 1 ? T('Вчера', 'Yesterday', 'Ayer')
    : days > 1 && days < 7 ? d.toLocaleDateString(loc, { weekday: 'long' }).replace(/^./, (c) => c.toUpperCase())
    : d.toLocaleDateString(loc, { weekday: 'short', day: 'numeric', month: 'long' });
  return `${day}, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** Живой статус человека в день встречи: 'late' | 'cant_make_it' | ''. */
function liveOf(p: GPlan, nm: string): string {
  const key = Object.keys(p.live || {}).find((k) => k.trim().toLowerCase() === nm.trim().toLowerCase());
  return key ? String((p.live as any)[key]?.status || '') : '';
}

function boardState(
  nm: string, p: GPlan, v: GVote | null,
  c: { proposer: string; mine: boolean; org: boolean },
): { text: string; tone: 'ok' | 'turn' | 'warn' | 'muted'; done: boolean } {
  const eq = (a?: string, b?: string) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  const confirmed = (p.confirmed || []).some((x) => eq(x, nm));
  const live = Object.entries(p.live || {}).find(([k]) => eq(k, nm))?.[1];
  const ok = (text: string) => ({ text, tone: 'ok' as const, done: true });
  const turn = (text: string) => ({ text, tone: 'turn' as const, done: false });
  const wait = (text: string) => ({ text, tone: 'muted' as const, done: false });
  // Раздел E: у каждого только факт ответа — «Answered» / «Hasn't answered» (GR.47–50).
  if (p.feedback_due || (p.state === 'done' && p.my_feedback)) {
    if (c.mine) return p.my_feedback ? ok(GPLAN.stAnswered()) : turn(GPLAN.stAnswerNeeded());
    return (p.feedback_answered || []).some((x) => eq(x, nm)) ? ok(GPLAN.stAnswered()) : wait(GPLAN.stHasntAnswered());
  }
  if (live?.status === 'cant_make_it') {
    const fresh = Date.now() / 1000 - Number(live.t || 0) < 30 * 60;
    return { text: c.mine ? GPLAN.stCantTold() : fresh ? GPLAN.stCantJustNow() : GPLAN.stCantMakeIt(), tone: 'warn', done: false };
  }
  // GR.40a / 40d: 12 часов прошли — отвечают оба; GR.40b / 40e: закрыто — кто что сказал.
  if (p.hold?.ask || p.hold?.closed) {
    const said = (xs?: string[]) => (xs || []).some((x) => eq(x, nm));
    // Борд: «Hasn't answered yet» и «Didn't answer» — янтарём (warning-text), свой ответ — кораллом.
    const amber = (text: string) => ({ text, tone: 'warn' as const, done: false });
    if (p.hold?.closed) return said(p.hold.let_go_by) ? amber(GPLAN.stLetItGo())
      : said(p.hold.one_on_one_by) ? ok(GPLAN.stWantsOneOnOne()) : amber(GPLAN.stDidntAnswer());
    if (said(p.hold?.one_on_one_by)) return ok(GPLAN.stWantsOneOnOne());
    return c.mine ? turn(GPLAN.stYourAnswerNeeded()) : amber(GPLAN.stHasntAnsweredYet());
  }
  // GR.40 / GR.40c: план на паузе — решает организатор.
  // Борд GR.40c: на паузе «Deciding» организатора — янтарём (warning-text), не серым, как в GR.30.
  if (p.state === 'below_quorum' && c.org) return c.mine ? turn(GPLAN.stYourCall()) : { text: GPLAN.stDeciding(), tone: 'warn', done: false };
  if (live?.status === 'late') return { text: c.mine ? GPLAN.stLateTold() : GPLAN.stLate(), tone: 'warn', done: false };
  if (v && v.state === 'open') {
    if (eq(v.by, nm)) return ok(GPLAN.stAskedToChange());
    if (c.org) return ok(GPLAN.stConfirmed());
    if (c.mine) return v.my_vote === undefined || v.my_vote === null ? turn(GPLAN.stVoteNeeded()) : ok(GPLAN.stVoted());
    return ok(GPLAN.stConfirmed());
  }
  if (v && v.state === 'closed' && !v.decided) return c.org ? ok(GPLAN.stConfirmed()) : ok(GPLAN.stVoted());
  if (p.fixed_by) {
    if (eq(p.fixed_by, nm)) return ok(GPLAN.stFixedThePlan());
    if (confirmed) return ok(GPLAN.stStaying());
    return c.mine ? turn(GPLAN.stYourCall()) : wait(GPLAN.stDeciding());
  }
  if (p.update) {
    if (eq(p.update.by, nm)) return ok(GPLAN.stChangedIt());
    if (confirmed) return ok(GPLAN.stAccepted());
    return c.mine ? turn(GPLAN.stAnswerNeeded()) : wait(GPLAN.stWaiting());
  }
  if (p.state === 'proposed') {
    const round = Number(p.round || 1);
    if (c.proposer ? eq(c.proposer, nm) : c.org) {
      return c.org ? ok(round > 1 ? GPLAN.stChangedIt() : GPLAN.stProposedThis()) : ok(GPLAN.stConfirmedSuggested());
    }
    if (confirmed) return ok(GPLAN.stConfirmed());
    if (c.mine) return turn(round > 1 ? GPLAN.stYourTurn() : GPLAN.stAnswerNeeded());
    // GR.29: и на последнем раунде «Hasn't answered yet» — «не подтвердил» появляется только после закрепления.
    return wait(GPLAN.stWaiting());
  }
  if (confirmed) return ok(GPLAN.stConfirmed());
  return c.mine ? turn(GPLAN.stAnswerNeeded()) : wait(GPLAN.stWaiting());
}

/** Окно голосования по плану — сервер: GP_VOTE_WINDOW. */
const VOTE_WINDOW = 6 * 3600;

/**
 * Полоса-счётчик борда (GR.30 «Staying», GR.32a «Accepted», GR.36 «Vote»): слово слева, «2 of 3»
 * по центру (число кораллом), срок справа, под ними тонкая дорожка. Дорожка — ВРЕМЯ окна, а не
 * доля ответивших: на борде «1 of 1» с таймером идёт почти пустой полосой (GR.43k), «2 of 3» — тоже
 * (GR.30), а до конца доходит только «Ended» (GR.38a). Окно неизвестно — короткая заглушка.
 */
function MeterBar({ label, now, of, right, share }: { label: string; now: number; of: number; right: string; share?: number }) {
  const k = share ?? 0;
  return (
    <View style={s.cardShadow}>
      <GlassSurface tone="light" radius={20} style={s.rounds}>
        <View style={s.roundHead}>
          <Text style={[s.roundWord, s.roundSide]}>{label}</Text>
          <Text style={s.roundNum}><Text style={s.roundNow}>{now}</Text>{` ${GPLAN.meterOf(of)}`}</Text>
          <Text style={[s.roundTime, s.roundSide, { textAlign: 'right' }]} numberOfLines={1}>{right}</Text>
        </View>
        <View style={s.bar}>
          <View style={[s.barFill, { width: `${Math.max(2, k * 100)}%` }]} />
        </View>
      </GlassSurface>
    </View>
  );
}

function formTitle(
  mode: Mode, f: Frame,
  a: { plan: GPlan | null; vote: GVote | null; owner: string; online: boolean; hybrid: boolean; proposer: string;
       isOwner: boolean; me?: string; g?: GroupInfo | null }
): string {
  if (mode === 'create') return GPLAN.createTitle(a.online, a.hybrid);
  if (mode === 'suggest') return GPLAN.suggestTitle();
  if (mode === 'update') return a.online ? GPLAN.changeTimeOrLink() : GPLAN.updateTitle();
  if (mode === 'link') return GPLAN.linkTitle();
  if (mode === 'details') return a.plan?.needs_place ? GPLAN.hybridMissingPlace() : GPLAN.hybridMissingLink();
  const p = a.plan || {};
  if (a.hybrid && p.details_ready === false) {
    return p.needs_place ? GPLAN.hybridMissingPlace() : GPLAN.hybridMissingLink();
  }
  switch (f) {
    case 'none': return GPLAN.createTitle(a.online, a.hybrid);
    case 'stayOrLeave': return GPLAN.fixedTitle2();
    case 'acceptOrLeave': {
      // GR.33: «The time changed» — если поменялось время; место — «The place changed».
      const was = p.update?.was || {};
      if (was.when && was.when !== p.when) return GPLAN.timeChangedTitle();
      if (was.place && was.place !== p.place) return GPLAN.placeChangedTitle();
      return GPLAN.changedTitle(String(p.update?.by || a.owner));
    }
    case 'voteOpen': return GPLAN.askedChangeTitle(String(a.vote?.by || ''), String(a.vote?.kind || 'edit'));
    case 'voteDecide': return GPLAN.closedTitle();
    case 'voteWait': return GPLAN.closedTitle();
    case 'proposed': {
      const waiting = othersOf(p.waiting, a.me);
      // GR.28/GR.29: со второго раунда заголовок называет предложившего; своё — «You changed the plan».
      if (a.proposer) {
        if (eqName(a.proposer, a.me)) return GPLAN.youChangedTitle();
        return GPLAN.counteredTitle(a.proposer);
      }
      // GR.26 у организатора — кого ждём по именам; GR.26d у участника — «Mateo proposed a plan».
      if (a.isOwner) return waiting.length ? GPLAN.waitingFor(GPLAN.names(waiting)) : GPLAN.waitingTitle();
      return String(p.my_response || '') === 'confirmed' && waiting.length
        ? GPLAN.waitingFor(GPLAN.names(waiting)) : GPLAN.proposedTitle(a.owner);
    }
    case 'confirmed':
      // GRO.25a: для организатора отсутствие ссылки — это и есть заголовок. Для остальных нет:
      // они ничего с этим сделать не могут, им хватает плашки «ссылка будет» у карточки.
      if (p.needs_link && a.isOwner) return GPLAN.linkTitle();
      if (a.isOwner && p.fixed_by && (p.waiting || []).length) return GPLAN.fixedMineTitle();
      if (a.isOwner && p.update && (p.waiting || []).length) return GPLAN.updateSentTitle();
      if (a.vote?.decided === 'kept' && !a.isOwner) return GPLAN.keptTitle(a.owner);
      return a.isOwner ? GPLAN.confirmedTitle() : GPLAN.setTitle();
    // «План назначен» на плане, который упал ниже трёх, — прямая неправда: рядом на том же
    // экране написано, что осталось меньше трёх.
    case 'below': return a.isOwner ? GPLAN.belowTitle() : GPLAN.onHoldTitle();
    case 'holdAsk': return GPLAN.holdAskTitle();
    case 'holdClosed': return GPLAN.holdClosedTitle();
    case 'now': {
      // GR.46 / GR.46a / GR.45a: сказал «не приду» сам, сказал кто-то другой, или просто идёт.
      if (String(p.my_live?.status || '') === 'cant_make_it') return a.online ? GPLAN.cantToldTitleCall() : GPLAN.cantToldTitle();
      const other = cantOthers(p, a.me)[0];
      if (a.online) return other ? GPLAN.cantComeTitleCall(other) : GPLAN.nowTitleCall();
      return other ? GPLAN.cantComeTitle(other) : GPLAN.nowTitle2();
    }
    case 'feedback': return a.online ? GPLAN.didCallHappen() : GPLAN.didYouMeet();
    case 'answered': return GPLAN.savedTitle();
    case 'locked': {
      // GR.45 / GR.45b: за два часа до начала — сколько осталось; сказал «опаздываю» — что группа знает.
      if (String(p.my_live?.status || '') === 'late') return GPLAN.lateToldTitle();
      const min = Math.max(0, Math.round((Number(p.starts_at || 0) - Date.now() / 1000) / 60));
      return p.starts_at ? GPLAN.startsIn(min) : GPLAN.setTitle();
    }
    case 'closed':
    default: return GPLAN.setTitle();
  }
}

/** Кто, кроме смотрящего, сказал «не приду» — по свежести. */
function cantOthers(p: GPlan, me?: string): string[] {
  return Object.entries(p.live || {})
    .filter(([k, v]) => v?.status === 'cant_make_it' && !eqName(k, me))
    .sort((x, y) => Number(y[1]?.t || 0) - Number(x[1]?.t || 0))
    .map(([k]) => k.charAt(0).toUpperCase() + k.slice(1));
}

function formNote(
  mode: Mode, f: Frame,
  a: { plan: GPlan | null; vote: GVote | null; owner: string; online: boolean; hybrid: boolean; g: GroupInfo | null;
       isOwner: boolean; me: string }
): string {
  const p = a.plan || {};
  if (mode === 'create') return GPLAN.createNote();
  if (mode === 'suggest') {
    return GPLAN.suggestNote(Math.max(0, Number(p.max_rounds || 3) - Number(p.round || 1)));
  }
  if (mode === 'update') return GPLAN.updateNote(String(p.when || ''), T('новое время', 'the new time', 'la nueva hora'));
  if (mode === 'link') return GPLAN.linkNote(String(p.when || ''));
  if (mode === 'details') return GPLAN.hybridMissingNote(!!p.needs_place);
  if (a.hybrid && p.details_ready === false) return GPLAN.hybridMissingNote(!!p.needs_place);
  const total = Number(a.g?.joined_count || (a.g?.members || []).length || 0);
  switch (f) {
    case 'none': return GPLAN.createNote();
    case 'proposed': {
      const waiting = othersOf(p.waiting, a.me);
      const done = othersOf(p.confirmed, a.me).filter((x) => !eqName(x, a.owner));
      const last = Number(p.round || 1) >= Number(p.max_rounds || 3);
      const tail = last ? (a.isOwner ? GPLAN.lastRoundMine() : GPLAN.lastRoundOf(a.owner)) : '';
      if (p.proposed_by && eqName(p.proposed_by, a.me)) {
        return GPLAN.youChangedNote(Number(p.round || 1), GPLAN.names(waiting)) + tail;
      }
      if (p.proposed_by) return GPLAN.suggestedNote(String(p.when || '')) + tail;
      if (!a.isOwner && String(p.my_response || '') !== 'confirmed') {
        return GPLAN.proposedNote(GPLAN.names(waiting.filter((x) => !eqName(x, a.me))));
      }
      if (done.length && waiting.length === 1) return GPLAN.waitingForNote2(GPLAN.names(done), waiting[0]);
      return waiting.length ? GPLAN.waitingForNote(GPLAN.names(waiting), waiting.length > 1) : GPLAN.waitingNote(total);
    }
    case 'stayOrLeave': return a.online ? GPLAN.fixedNoteCall(String(p.when || '')) : GPLAN.fixedNote(String(p.when || ''), venue(p));
    case 'acceptOrLeave': {
      const was = p.update?.was || {};
      // «From 20:30 to 21:30» — если день тот же, называем только часы (GR.33).
      const [d0, t0] = splitWhen(String(was.when || ''));
      const [d1, t1] = splitWhen(String(p.when || ''));
      const same = !!t0 && !!t1 && d0 === d1;
      return GPLAN.changedNote2(same ? t0 : String(was.when || ''), same ? t1 : String(p.when || ''),
                                a.hybrid ? ((!was.link || was.link === p.link) && (!was.place || was.place === p.place))
                                  : a.online ? (!was.link || was.link === p.link) : (!was.place || was.place === p.place),
                                a.online, a.hybrid);
    }
    case 'voteOpen':
      return a.isOwner ? GPLAN.voteAdviceMine() : GPLAN.voteAdvice(a.owner);
    case 'voteDecide':
      return GPLAN.voteClosedNote(Number(a.vote?.yes || 0) > Number(a.vote?.no || 0));
    case 'voteWait': return GPLAN.waitingDecision(a.owner);
    case 'now': {
      if (a.hybrid) return GPLAN.hybridNowNote(Number(p.side_counts?.in_person || 0), Number(p.side_counts?.call || 0));
      const others = othersOf(((a.g?.members || []) as { name?: string }[]).map((m) => String(m.name || '')), a.me);
      if (String(p.my_live?.status || '') === 'cant_make_it') return (a.online ? GPLAN.cantToldNoteCall : GPLAN.cantToldNote)(GPLAN.names(others));
      const gone = cantOthers(p, a.me)[0];
      if (gone) return (a.online ? GPLAN.cantComeNoteCall : GPLAN.cantComeNote)(GPLAN.names(others.filter((x) => !eqName(x, gone))));
      return (a.online ? GPLAN.nowNoteCall : GPLAN.nowNote2)(GPLAN.names(others));
    }
    case 'locked': {
      const others = othersOf(((a.g?.members || []) as { name?: string }[]).map((m) => String(m.name || '')), a.me);
      if (String(p.my_live?.status || '') === 'late') return (a.online ? GPLAN.lateToldNoteCall : GPLAN.lateToldNote)(GPLAN.names(others));
      if (a.online && p.starts_at && p.link) {
        // GRO.45: ссылка открывается за 10 минут до звонка — до того говорим, когда откроется.
        const open = Number(p.starts_at) - Date.now() / 1000 <= 10 * 60;
        return GPLAN.lateHintCall(a.owner, a.isOwner, callService(p.link), GPLAN.names(others), open);
      }
      return p.starts_at ? GPLAN.lateHint(GPLAN.names(others)) : GPLAN.locked();
    }
    case 'feedback': {
      const others = othersOf(((a.g?.members || []) as { name?: string }[]).map((m) => String(m.name || '')), a.me);
      const done = othersOf(p.feedback_answered, a.me);
      return others.length && done.length >= others.length
        ? GPLAN.othersAnsweredNote(GPLAN.names(others))
        : a.online ? GPLAN.didCallNote(callService(p.link), GPLAN.names(others)) : GPLAN.didYouMeetNote(GPLAN.names(others));
    }
    case 'answered': return GPLAN.savedNote();
    // Борд открывает вопрос («на паузе, решай»), а прежняя строка его закрывала («групповым
    // быть перестал»). Обещать человеку выбор и тут же говорить, что всё кончено, нельзя.
    case 'below': {
      // Про согласие второго говорим, только если переход и правда возможен: иначе строка
      // обещала бы выход, которого на кадре нет.
      const peer = ((a.g?.members || []) as { name?: string }[])
        .map((m) => String(m.name || '')).filter((x) => x && x !== a.me)[0] || '';
      return a.isOwner ? GPLAN.belowNote2() : GPLAN.onHoldNote(a.owner) || GPLAN.belowNote((a.g as any)?.can_convert ? peer : '');
    }
    case 'closed': return GPLAN.cancelled();
    case 'holdAsk': {
      const other = ((a.g?.members || []) as { name?: string }[]).map((m) => String(m.name || ''))
        .filter((x) => x && !eqName(x, a.me))[0] || '';
      if (p.hold?.my_answer === 'one_on_one') return GPLAN.holdWaitNote(other);
      return GPLAN.holdAskNote(a.isOwner ? '' : a.owner);
    }
    case 'holdClosed': {
      const by = (p.hold?.let_go_by || [])[0];
      return p.hold?.why === 'let_go' && by ? GPLAN.holdLetGoNote(eqName(by, a.me) ? GPLAN.you() : by) : GPLAN.holdClosedNote();
    }
    case 'confirmed': {
      if (p.needs_link && a.isOwner) return GPLAN.linkNote(String(p.when || ''));
      const waiting = othersOf(p.waiting, a.me);
      if (a.isOwner && p.fixed_by && waiting.length) return GPLAN.fixedMineNote(String(p.when || ''), GPLAN.names(waiting));
      if (a.isOwner && p.update && waiting.length) return GPLAN.updateSentNote(GPLAN.names(waiting));
      if (a.vote?.decided === 'kept' && !a.isOwner) return GPLAN.keptNote2(String(p.when || ''));
      if (a.isOwner) {
        const others = ((a.g?.members || []) as { name?: string }[]).map((m) => String(m.name || ''))
          .filter((x) => x && !eqName(x, a.me));
        if (a.online && p.starts_at) {
          // GRO.34: ссылка открывается за 10 минут до звонка — называем это время.
          const d = new Date((Number(p.starts_at) - 600) * 1000);
          return GPLAN.confirmedNoteCall(GPLAN.names(others), `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`);
        }
        return GPLAN.confirmedNote(GPLAN.names(others), venue(p));
      }
      return GPLAN.setNote();
    }
    default: return GPLAN.setNote();
  }
}

// ---------------------------------------------------------------- части

function Head({ title, onBack, onActions }: { title: string; onBack: () => void; onActions?: () => void }) {
  const lang = useLang();
  /* Кадр GR.26: стеклянная «назад», название затеи слева гарнитурой шапок 20/24, «ещё» справа. */
  return (
    <View style={s.head}>
      <GlassBack label={GPLAN.back()} onPress={onBack} />
      <Text style={[s.headTitle, heading(lang, type.headingSm)]} numberOfLines={1}>{title}</Text>
      {onActions ? (
        <GlassIconButton label={T('Действия', 'Actions', 'Acciones')} onPress={onActions}>
          <IconDots />
        </GlassIconButton>
      ) : null}
    </View>
  );
}

/**
 * «Чт, 23 июл. · 19:00» → дата и время отдельно: на карточке борда у каждого свой знак
 * (календарь и часы). Подпись собирает planWhenLabel, и разделитель у неё один — « · ». Строка
 * другого вида (старый план, набранный руками) остаётся целиком в поле даты.
 */
function splitWhen(when: string): [string, string] {
  // « · » — подпись WhenPicker; «, » — время из затеи («Thu 23 July, 19:00»).
  const m = when.match(/^(.*?)\s*(?:·|,)\s*(\d{1,2}[:.]\d{2}(?:\s*[AaPp][Mm])?)$/);
  return m ? [m[1], m[2]] : [when, ''];
}

const eqName = (a?: string, b?: string) =>
  !!String(a || '').trim() && String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
/** Люди списка сервера без себя — «Waiting for Jane and Marc» не называет смотрящего. */
const othersOf = (list?: string[], me?: string) => (list || []).map(String).filter((x) => x && !eqName(x, me));

/**
 * Карточка плана — «Plan Card · forming» с борда: светлое стекло со скруглением 20, сверху обложка
 * во всю ширину (128), под ней дата и время в одну строку и место. Название затеи на карточке не
 * повторяется — оно в шапке.
 */
function PlanCard({
  title, when, was, venueLine, callLine, online, hybrid, placeUnchanged, lockedLine = '',
}: {
  title: string; when: string; was: string; venueLine: string; callLine: string;
  online: boolean; hybrid: boolean; placeUnchanged: boolean;
  /** GR.46: «Locked · nothing can change now» зелёным под местом. */
  lockedLine?: string;
}) {
  const [date, time] = splitWhen(when);
  return (
    <View style={s.cardShadow}>
      <GlassSurface tone="light" radius={20} style={s.card}>
        <Cover intent={{ title }} style={s.cover} />
        <View style={s.cardBody}>
          <View style={s.cardRow}>
            <View style={s.cardPair}>
              <IconCalendar size={18} c={color.primary} />
              <Text style={s.cardLine} numberOfLines={1}>{date || '—'}</Text>
            </View>
            {time ? (
              <View style={s.cardPair}>
                <IconClock size={18} c={color.primary} />
                <Text style={s.cardLine}>{time}</Text>
              </View>
            ) : null}
          </View>
          {was && was !== when ? <Text style={s.was}>{GPLAN.wasLine(was)}</Text> : null}
          <View style={s.cardRow}>
            {online ? <IconVideo size={18} c={color.primary} /> : <IconPin size={18} c={color.primary} />}
            <Text style={[s.cardLine, { flex: 1 }]} numberOfLines={1}>
              {venueLine}
              {placeUnchanged ? <Text style={s.wasInline}>{`  ·  ${GPLAN.unchanged()}`}</Text> : null}
            </Text>
          </View>
          {hybrid ? (
            <View style={s.cardRow}>
              <IconVideo size={18} c={color.primary} />
              <Text style={[s.cardLine, { flex: 1 }]} numberOfLines={1}>{callLine}</Text>
            </View>
          ) : null}
          {lockedLine ? (
            <View style={s.cardRow}>
              <IconLock size={18} c="#238C62" />
              <Text style={[s.cardLine, { flex: 1, color: '#238C62' }]} numberOfLines={1}>{lockedLine}</Text>
            </View>
          ) : null}
        </View>
      </GlassSurface>
    </View>
  );
}

/**
 * «Round 1 / 3» — стеклянная полоса с борда: слово слева, номер кораллом по центру, под ними три
 * тонкие дорожки. Дорожка плавно заполняется, когда начинается новый раунд, — это единственное
 * движение на экране, и оно сообщает, что раунды расходуются.
 *
 * Справа на борде «Ends in 12h», но срока раунда сервер не отдаёт — выдумывать его экран не
 * будет. На последнем раунде под дорожками объяснение, что дальше.
 */
function RoundBar({ round, max }: { round: number; max: number }) {
  const reduced = useReducedMotion();
  return (
    <View style={s.cardShadow}>
      <GlassSurface tone="light" radius={20} style={s.rounds}>
        <View style={s.roundHead}>
          <Text style={[s.roundWord, s.roundSide]}>{GPLAN.roundWord()}</Text>
          <Text style={s.roundNum}>
            <Text style={s.roundNow}>{round}</Text>{` / ${max}`}
          </Text>
          <View style={s.roundSide} />
        </View>
        <View style={s.bars}>
          {Array.from({ length: max }, (_, i) => (
            <RoundTrack key={i} on={i < round} instant={reduced} />
          ))}
        </View>
        {/* О последнем раунде говорит пояснение над карточкой (GR.29) — второй строки здесь нет. */}
      </GlassSurface>
    </View>
  );
}

function RoundTrack({ on, instant }: { on: boolean; instant: boolean }) {
  // С первого кадра дорожка стоит как есть; плавно меняется только при СМЕНЕ раунда.
  const k = useSharedValue(on ? 1 : 0);
  useEffect(() => {
    k.value = instant ? (on ? 1 : 0) : withTiming(on ? 1 : 0, { duration: 420, easing: Easing.out(Easing.cubic) });
  }, [on, instant, k]);
  const fill = useAnimatedStyle(() => ({ width: `${k.value * 100}%` }));
  return (
    <View style={s.bar}>
      <Animated.View style={[s.barFill, fill]} />
    </View>
  );
}

/**
 * Кнопки дока — модульные компоненты, а не функции внутри Actions: вложенная функция-компонент
 * каждый рендер получала бы новый тип, и React пересоздавал бы кнопку вместе с её стеклом при
 * каждом фоновом опросе плана. «Занято» приходит через контекст — его знает только Actions.
 */
const DockBusy = React.createContext(false);
function P({ label, onPress }: { label: string; onPress: () => void }) {
  const busy = React.useContext(DockBusy);
  return <GlassPill tone="brand" label={label} busy={busy} onPress={busy ? undefined : onPress} style={s.pill} />;
}
function S({ label, onPress }: { label: string; onPress: () => void }) {
  return <GlassPill label={label} onPress={onPress} style={s.pill} />;
}
function D({ label, onPress }: { label: string; onPress: () => void }) {
  return <GlassPill tone="dark" label={label} onPress={onPress} style={s.pill} />;
}

/** Пара кнопок внизу. Ровно та, что на кадре: на борде их всегда две, и вторая всегда «мягкая». */
function Actions(a: Parameters<typeof ActionsFor>[0]) {
  return <DockBusy.Provider value={a.busy}>{ActionsFor(a)}</DockBusy.Provider>;
}

function ActionsFor(a: {
  mode: Mode; view: Frame; busy: boolean; plan: GPlan | null; vote: GVote | null;
  online: boolean; hybrid: boolean; leftForConfirm: number; isOwner: boolean;
  proposer: string; owner: string;
  onMet: () => void; onNotMet: (didntGo: boolean) => void;
  onCreateOpen: () => void;
  onCreate: () => void; onConfirm: () => void; onSuggestOpen: () => void; onSuggestSend: () => void;
  onFix: () => void; onStay: () => void; onLeave: () => void; onOpenChat: () => void;
  onAskVote: () => void; onOpenVote: () => void; onDecide: () => void;
  onInviteMore: () => void; onCancelPlan: () => void; onMoreTime: () => void;
  canConvert: boolean; onSwitch1to1: () => void; onHold: (choice: 'one_on_one' | 'let_go') => void;
  imLateSent: boolean; onLate: () => void; onCantMakeIt: () => void;
  onOpenCall: () => void;
  onUpdateOpen: () => void; onUpdateSend: () => void; onAccept: () => void;
  onLinkOpen: () => void; onLinkSave: () => void; onAskHost: () => void; onCancelForm: () => void;
  onDetailsOpen: () => void; onDetailsSave: () => void;
  onUseSingleMode: (mode: 'offline' | 'online') => void;
}) {
  if (a.mode === 'create') return <><P label={GPLAN.send()} onPress={a.onCreate} /><S label={GPLAN.back()} onPress={a.onCancelForm} /></>;
  if (a.mode === 'suggest') return <><P label={GPLAN.suggestSend()} onPress={a.onSuggestSend} /><S label={GPLAN.cancel()} onPress={a.onCancelForm} /></>;
  if (a.mode === 'update') return <><P label={GPLAN.sendUpdate()} onPress={a.onUpdateSend} /><S label={GPLAN.keepTerms()} onPress={a.onCancelForm} /></>;
  if (a.mode === 'link') return <><P label={GPLAN.saveLink()} onPress={a.onLinkSave} /><S label={GPLAN.askHost()} onPress={a.onAskHost} /></>;
  if (a.mode === 'details') return <>
    <P label={a.plan?.needs_place ? GPLAN.savePlace() : GPLAN.saveLink()} onPress={a.onDetailsSave} />
    <S label={a.plan?.needs_place ? GPLAN.makeOnline() : GPLAN.makeOffline()}
       onPress={() => a.onUseSingleMode(a.plan?.needs_place ? 'online' : 'offline')} />
  </>;

  const p = a.plan;
  const mineDone = String(p?.my_response || '') === 'confirmed';

  if (a.hybrid && p?.details_ready === false) {
    return a.isOwner
      ? <><P label={p?.needs_place ? GPLAN.savePlace() : GPLAN.saveLink()} onPress={a.onDetailsOpen} />
           <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>
      : <><Text style={s.dockNote}>{GPLAN.hybridMissingNote(!!p.needs_place)}</Text>
           <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>;
  }

  switch (a.view) {
    case 'none':
      // Создать план может только организатор (сервер ответит NOT_ORGANIZER) — у остальных этой
      // кнопки на кадре и нет: они ждут, а не «не могут нажать».
      return a.isOwner
        ? <><P label={GPLAN.createTitle(a.online, a.hybrid)} onPress={a.onCreateOpen} />
             <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>
        : <S label={GPLAN.openChat()} onPress={a.onOpenChat} />;
    case 'proposed': {
      /*
        Кнопки по кадрам: подтвердивший ждёт — «Open group chat» и изменить (GR.26/26a/27a);
        не подтвердивший — «Confirm» и изменить (GR.26d/28). Организатор меняет свой план
        («Change the plan»), участник — предлагает («Suggest a change»); своё уже внесённое
        организатор правит «Edit the change». На последнем раунде вместо изменения — «Fix the plan»
        (GR.29), а если закреплять нельзя — ничего: сервер ответил бы ROUNDS_USED_UP.
      */
      const mineChange = !!a.proposer && a.proposer.trim().toLowerCase() === a.owner.trim().toLowerCase();
      const change = p?.rounds_used_up
        ? (a.isOwner && p?.can_fix ? <S label={GPLAN.fix()} onPress={a.onFix} /> : null)
        : <S label={a.isOwner ? (mineChange ? GPLAN.editTheChange() : GPLAN.changeThePlan()) : GPLAN.suggest()}
             onPress={a.onSuggestOpen} />;
      return mineDone
        ? <><P label={GPLAN.openChat()} onPress={a.onOpenChat} />{change}</>
        : <><P label={GPLAN.confirm()} onPress={a.onConfirm} />{change}</>;
    }
    case 'stayOrLeave':
      return <><P label={GPLAN.stay()} onPress={a.onStay} />
               <S label={GPLAN.leavePlan()} onPress={a.onLeave} /></>;
    case 'acceptOrLeave':
      return <><P label={GPLAN.accept()} onPress={a.onAccept} />
               <S label={GPLAN.leavePlan()} onPress={a.onLeave} /></>;
    case 'voteOpen':
      // GR.36: голосующему — «Open the vote»; проголосовавшему и организатору — чат.
      return !a.isOwner && (a.vote?.my_vote === undefined || a.vote?.my_vote === null)
        ? <P label={GPLAN.openVote()} onPress={a.onOpenVote} />
        : <P label={GPLAN.openChat()} onPress={a.onOpenChat} />;
    case 'voteDecide':
      return <><P label={GPLAN.decide()} onPress={a.onDecide} />
               <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>;
    case 'voteWait':
      return <S label={GPLAN.openChat()} onPress={a.onOpenChat} />;
    case 'confirmed':
      // GRO.25a: пока ссылки нет, главное действие организатора — вставить её, а не «открыть чат».
      if (p?.needs_link) {
        return <><P label={GPLAN.saveLink()} onPress={a.onLinkOpen} />
                 <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>;
      }
      // GR.32a: правка ушла — организатор может её поправить. GR.30: закрепил и ждёт — только чат.
      if (a.isOwner && p?.update && (p?.waiting || []).length) {
        return <><P label={GPLAN.openChat()} onPress={a.onOpenChat} />
                 <S label={GPLAN.editTheUpdate()} onPress={a.onUpdateOpen} /></>;
      }
      if (a.isOwner && p?.fixed_by && (p?.waiting || []).length) return <P label={GPLAN.openChat()} onPress={a.onOpenChat} />;
      // GR.34: организатор меняет время или место сам (GR.32). GR.35: участник просит группу
      // (голосование) или выходит из плана.
      return a.isOwner
        ? <><P label={GPLAN.openChat()} onPress={a.onOpenChat} />
             <S label={a.online ? GPLAN.changeTimeOrLink() : GPLAN.changeTimeOrPlace()} onPress={a.onUpdateOpen} /></>
        : <><P label={GPLAN.openChat()} onPress={a.onOpenChat} />
             <S label={GPLAN.askToChange()} onPress={a.onAskVote} />
             <S label={GPLAN.leavePlan()} onPress={a.onLeave} /></>;
    // GR.40: три выхода с кадра. Раньше здесь была одна «открыть чат» — то есть выхода не было
    // ни одного, и план оставался на паузе навсегда.
    // GR.40a / GR.40d: обоим — один на один или отпустить; сказал «да» — ждём второго.
    case 'holdAsk':
      return p?.hold?.my_answer === 'one_on_one'
        ? <><P label={GPLAN.openChat()} onPress={a.onOpenChat} /><S label={GPLAN.letPlanGo()} onPress={() => a.onHold('let_go')} /></>
        : <><P label={GPLAN.switchTo1to1()} onPress={() => a.onHold('one_on_one')} /><S label={GPLAN.letPlanGo()} onPress={() => a.onHold('let_go')} /></>;
    case 'holdClosed': return <P label={GPLAN.openChat()} onPress={a.onOpenChat} />;
    case 'below':
      // Средний выход показывается только когда он ВОЗМОЖЕН: сервер отдаёт can_convert, и он же
      // отказал бы, если бы кнопка обещала лишнего (уже спросили, второго нет, план ожил).
      // GR.40: у организатора три выхода, все светлые кроме первого; GR.40c: участник — чат или выйти.
      return a.isOwner
        ? <><P label={GPLAN.inviteMore()} onPress={a.onInviteMore} />
             {a.canConvert ? <S label={GPLAN.switchTo1to1()} onPress={a.onSwitch1to1} /> : null}
             <S label={GPLAN.cancelPlan()} onPress={a.onCancelPlan} /></>
        : <><P label={GPLAN.openChat()} onPress={a.onOpenChat} />
             <S label={GPLAN.leavePlan()} onPress={a.onLeave} /></>;
    // GR.45: заперто — менять нельзя ничего, но сказать «не смогу» можно и нужно; иначе
    // единственным честным действием остаётся молча не прийти.
    case 'locked':
      // GR.45: до начала — чат и «I'm running late», обе светлые; сказал — только чат (GR.45b).
      if (a.imLateSent) return <P label={GPLAN.openChat()} onPress={a.onOpenChat} />;
      return <><S label={GPLAN.openChat()} onPress={a.onOpenChat} />
               <S label={a.online ? GPLAN.imLateCall() : GPLAN.imLate()} onPress={a.onLate} /></>;
    // GR.45a: встреча идёт. «Опаздываю» видит вся группа — тем и отличается от один-на-один,
    // где это личное сообщение одному человеку.
    case 'now': {
      // GR.45a: встреча идёт — «I can't make it»; кто-то уже сказал (GR.46a) или сказал ты (GR.46) —
      // только чат. Онлайн-встрече главное — ссылка на звонок.
      // Онлайн (GRO.45a): «Open link» уже в карточке ссылки — внизу, как у встречи, «I can't make it».
      if (a.hybrid && p?.link) {
        return <><P label={GPLAN.openLink()} onPress={a.onOpenCall} /><S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>;
      }
      const someoneCant = Object.values(p?.live || {}).some((v: any) => v?.status === 'cant_make_it');
      return someoneCant || String(p?.my_live?.status || '') === 'cant_make_it'
        ? <P label={GPLAN.openChat()} onPress={a.onOpenChat} />
        : <S label={GPLAN.cantMakeIt()} onPress={a.onCantMakeIt} />;
    }
    case 'feedback':
      return <><P label={a.online ? GPLAN.yesTalked() : GPLAN.yesMet()} onPress={a.onMet} />
               <S label={GPLAN.didntHappen()} onPress={() => a.onNotMet(false)} />
               <S label={a.online ? GPLAN.iDidntJoin() : a.hybrid ? GPLAN.iDidntComeOrJoin() : GPLAN.iDidntGo()} onPress={() => a.onNotMet(true)} /></>;
    case 'answered':
      return <P label={GPLAN.openChat()} onPress={a.onOpenChat} />;
    case 'closed':
    default:
      return <S label={GPLAN.openChat()} onPress={a.onOpenChat} />;
  }
}

/**
 * Лист группового плана: общий нижний лист плюс строка пояснения под заголовком — она есть у всех
 * листов этого экрана и у одного только этого экрана.
 */
function PlanSheet({
  open, onClose, title, body, children,
}: {
  open: boolean; onClose: () => void; title: string; body: string; children: React.ReactNode;
}) {
  return (
    <Sheet visible={open} onClose={onClose} title={title}>
      <Text style={s.sheetBody}>{body}</Text>
      {children}
    </Sheet>
  );
}

// ============================================================ вид
// Борд «GR · Offline — new layout» (кадры GR.26–GR.50): сливочный фон, светлое стекло карточек со
// скруглением 20, текст Geist, заголовки гарнитурой шапок. Числа сняты с кадра GR.26.

const INK = '#181B22';
const GREY = '#5A616E';

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, height: 56 },
  headTitle: { flex: 1, color: INK } as any,

  body: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: space.xl, gap: 12 },
  status: { gap: 4 },
  title: { fontSize: 15, lineHeight: 20, color: INK } as any,
  note: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: INK } as any,
  err: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.primary } as any,
  fatal: { fontFamily: font.text, fontSize: 15, lineHeight: 22, color: color.muted, paddingHorizontal: 20, paddingTop: space.lg } as any,

  cardShadow: {
    borderRadius: 20,
    shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 5 },
  },
  card: { overflow: 'hidden' },
  cover: { height: 128, backgroundColor: color.neutral100 },
  cardBody: { paddingHorizontal: 16, paddingVertical: 16, gap: 8 },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardPair: { flexDirection: 'row', alignItems: 'center', gap: 4, marginRight: 8, flexShrink: 1 },
  cardLine: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: INK } as any,
  was: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: GREY, marginLeft: 22 } as any,
  wasInline: { color: GREY },

  rounds: { paddingHorizontal: 16, paddingVertical: 16, gap: 8 },
  roundHead: { flexDirection: 'row', alignItems: 'center' },
  roundSide: { flex: 1 },
  // Срок справа — Geist 400 13/18, не заголовочный шрифт (борд: text 'time' во всех полосах).
  roundTime: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: INK } as any,
  roundWord: { fontFamily: font.displaySemi, fontSize: 13, lineHeight: 16, color: INK } as any,
  roundNum: { fontFamily: font.displaySemi, fontSize: 13, lineHeight: 16, color: '#AFAFAF', textAlign: 'center' } as any,
  roundNow: { color: '#FF385C' },
  bars: { flexDirection: 'row', gap: 6 },
  bar: { flex: 1, height: 3, borderRadius: 999, backgroundColor: '#EBEBEB', overflow: 'hidden' },
  barFill: { height: 3, borderRadius: 999, backgroundColor: '#FF385C' },
  roundText: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: GREY } as any,

  badgeBox: { alignSelf: 'flex-start', borderRadius: 999 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 7, paddingHorizontal: 12 },
  badgeText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.infoText } as any,
  warn: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 14, backgroundColor: color.warnBg, alignSelf: 'flex-start' },
  warnText: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.warnText } as any,
  sideBox: { gap: space.sm, paddingVertical: space.sm },
  sideTitle: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: INK } as any,
  sideTabs: { flexDirection: 'row', gap: space.sm },
  sideTab: { flex: 1, minHeight: 44, borderRadius: 999, borderWidth: 1, borderColor: '#FFFFFF',
             flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
             backgroundColor: 'rgba(255,255,255,0.6)' },
  sideTabOn: { backgroundColor: color.primary, borderColor: color.primary },
  sideText: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: INK } as any,
  sideTextOn: { color: color.onPrimary },
  sideCount: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: GREY } as any,

  form: { gap: space.sm },
  /** Поле на стекле: белое 62% с белой кромкой, скругление 16 — как GlassInput. */
  input: {
    height: 48, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.62)', borderWidth: 1,
    borderColor: '#FFFFFF', paddingHorizontal: 14, color: INK, fontFamily: font.text, fontSize: 15,
  },

  roster: { paddingTop: 4 },
  stillOn: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.successText, paddingTop: 4 } as any,
  memberRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56 },
  av: { width: 40, height: 40, borderRadius: 999 },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  memberName: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: INK, flexShrink: 1 } as any,
  /** Метка организатора — голубая пилюля из борда (#CFE3FF, текст #1F58BE). */
  orgBadge: { height: 16, paddingHorizontal: 8, borderRadius: 99, backgroundColor: '#CFE3FF', justifyContent: 'center' },
  orgText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#1F58BE' } as any,
  memberState: { fontFamily: font.text, fontSize: 13, lineHeight: 22 } as any,
  stMuted: { color: GREY },
  stOk: { color: '#0F7340' },
  stTurn: { color: '#FF385C' },
  stWarn: { color: '#D46A00' },

  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start' },
  linkText: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: color.infoText } as any,

  dock: { paddingHorizontal: 20, paddingTop: space.sm, gap: 8 },
  /** Кнопки в просмотре — в ленте страницы, через 8, от состава 14 (как «Content» кадра). */
  inlineActions: { gap: 8, paddingTop: 2 },
  dockNote: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.successText, textAlign: 'center' } as any,
  /** Кнопки дока 44: в кадре 40, но меньше 44 палец промахивается — это ниже порога HIG. */
  pill: { height: 44 },
  sheetBtn: { height: 48 },
  // GR.29a: заголовок списка 15/20, строки-варианты — стекло 16 (выбранная светлее), 16/16/16/8.
  pickWrap: { gap: 12, marginBottom: 16 },
  pickHead: { fontSize: 15, lineHeight: 20, color: INK },
  pickList: { gap: 4 },
  pickRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 16, paddingLeft: 16, paddingRight: 8,
             borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.16)' },
  pickRowOn: { backgroundColor: 'rgba(255,255,255,0.36)' },
  pickLine: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 16, color: INK } as any,
  pickMeta: { fontFamily: font.text, fontSize: 13, lineHeight: 16, color: INK } as any,
  pickNote: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: INK } as any,
  pickErr: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#C23A2B' } as any,

  sheetBody: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#404652', marginBottom: 8 } as any,

  infoShadow: { borderRadius: 20, shadowColor: '#3CAEFF', shadowOpacity: 0.3, shadowRadius: 20, shadowOffset: { width: 0, height: 8 } },
  infoBox: { padding: 16, gap: 8 },
  infoHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  infoQ: { width: 16, height: 16, borderRadius: 8, borderWidth: 1.4, borderColor: color.infoText, textAlign: 'center',
           fontFamily: font.textSemibold, fontSize: 11, lineHeight: 13, color: color.infoText, overflow: 'hidden' } as any,
  infoTitle: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.infoText, flex: 1 } as any,
  infoNote: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.infoText } as any,
  addr: { padding: 16, gap: 12 },
  addrRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  addrPlace: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: INK } as any,
  addrSubRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  addrSub: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: GREY } as any,
  addrBtn: { height: 40 },
  rateRow: { flexDirection: 'row', gap: 8, marginTop: -12 },
  rateChip: { flex: 1, height: 36, borderRadius: 999, alignItems: 'center', justifyContent: 'center',
              backgroundColor: 'rgba(255,255,255,0.42)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.75)' },
  rateChipOn: { backgroundColor: 'rgba(255,56,92,0.82)', borderColor: 'rgba(255,255,255,0.4)' },
  rateText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: INK } as any,
  rateTextOn: { color: '#FFFFFF' },
  reasonList: { gap: 4, marginTop: -12 },
  reasonRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 16,
               backgroundColor: 'rgba(255,255,255,0.16)' },
  reasonRowOn: { backgroundColor: 'rgba(255,255,255,0.36)' },
  reasonText: { flex: 1, fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: INK } as any,
});
