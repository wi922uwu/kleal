/**
 * Выдача кандидатов — кадр O.12, окно приглашения — O.14.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор полей — в src/candidates.ts и src/intent.ts.
 *
 * Карточка по кадру: фото, имя с бейджем («Best match» у первой, «Match» у остальных), подзаголовок,
 * расстояние, чипы интересов, «Сводка Kleal» и кнопка «Пригласить». Чего на кадре есть, а в данных
 * нет — занятие и город — карточка не выдумывает: вместо занятия вайб или интересы, вместо города
 * километры (см. src/candidates.ts).
 *
 * Два места, где экран намеренно расходится с бордом, — из-за того, как отвечает матчинг:
 *
 *  1. Пустой выдачи почти не бывает. Когда по теме не совпал никто, сервер присылает ближайших
 *     людей с пометкой `fallback: "alternative"`. Заголовок «Лучшее совпадение» над такой пачкой —
 *     прямая неправда, поэтому шапка смотрит на пометки карточек, а не на их количество; бейджи
 *     мэтча на таких карточках не рисуются.
 *  2. Расширение — лестница §12, ступень за ступенью, каждая называется вслух. Какую ось расширять
 *     — решает клиент: только он помнит, что уже пробовали.
 *
 * Групповой режим — борд «0 · Create the intent» (Figma 6864:119674): шапка с названием затеи и «···»
 * (GR.14f), «Best fit for your group» и полоса набора (GR.14a), карточка со стеклом и блоком исхода
 * (GR.14a–14e), листы GR.16 / GR.14b / GR.15 и обзор «Invites sent» (GR.17 / GR.17a), когда
 * приглашены все. Детали — src/components/GroupInvite.tsx, копия — GR14 в src/groups.ts.
 *
 * Приглашение (O.14) — ЕДИНСТВЕННОЕ место, где выдача что-то отправляет. Окно называет последствия
 * словами с кадра: человек увидит интент и профиль. Отправка идёт в /api/agent/propose; сервер
 * держит одно открытое приглашение на пару — повторная отправка обновляет его, а не плодит копии.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, Modal, Alert,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation, useRouter } from 'expo-router';
import { usePreventRemove } from 'expo-router/react-navigation';
import { RESULTS, EXPAND_LADDER, ExpandAxis, axisExplain, WIZ, AGE_PRESETS, agePresetLabel } from '../src/intent';
import { CANDS, PREFS, CAP, Cand, candSubtitle, candWhere, candSummary, candReadiness, isHidden, interestEmoji } from '../src/candidates';
import { CHAT, ReqStatus, activeChatWith } from '../src/chat';
import { useInvites, inviteTo, openInvites, sendInvite, withdrawInvite, pickInvite, invitesFor } from '../src/invites';
import { isGroupIntent, groupTitleOf, GROUP, GR14, OFP, ROOM, pronOf, namesList, shortTitle } from '../src/groups';
import {
  useGroupSession, groupStatusFor, groupStatusAt, groupClosedOf, groupCounters, groupEndsAt, groupId,
  sendGroupInvite, cancelGroupInvite, type GStatus,
} from '../src/ginvites';
import { useLang, T, getLang } from '../src/i18n';
import { takeResults, patchResults, setCandidate } from '../src/results-store';
import { mediaUrl, agent, myId, group as gapi, newIdem, type Peer } from '../src/api';
import { IconPerson, IconPin, IconCalendar, IconDots, IconPencil, IconBan } from '../src/components/icons';
import { GlassPill } from '../src/components/Glass';
import { GlassBack, GlassIconButton } from '../src/components/LiquidGlass';
import { RoundIndicator, StatusBlock, MemberRow, PlanCard, type StatusKind } from '../src/components/GroupInvite';
import { GROUP_FREE_MAX_TOTAL } from '../src/intent';
import { AgeRange } from '../src/components/AgeRange';
import Slider from '@react-native-community/slider';
import { SEXES, sexLabel } from '../src/onboarding';
import { BottomNav } from '../src/components/BottomNav';
import { Sheet, SheetText, SheetItem } from '../src/components/Sheet';
import { color, font, heading, labelFamily, radius as rad, space, type } from '../src/theme';
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { interestLabels } from '../src/interest-label';
import { useNavCollapse } from '../src/navScroll';

const ru = () => getLang() === 'ru';
/** Человек с карточки выдачи — подписью и id: по одной подписи тёзок не различить. */
/** Состояние приглашения один на один на карточке выдачи (OF.12a–12e). */
type SoloState = { st: 'sent' | 'yes' | 'picked' | 'closed' | 'declined'; at?: number; note: string };

const peerOfCard = (c: Cand): Peer => ({ name: String(c.name || ''), id: String(c.id || '') });

/** Черновик условий листа O.11a. Живёт отдельно от интента: «Отмена» не должна ничего менять. */
type Prefs = { sex: string; anyAge: boolean; minAge: number; maxAge: number; radiusKm: number };

/**
 * Условия из интента — как они есть СЕЙЧАС.
 *
 * `anyAge` считается по факту наличия рамки, а не по её значению. Мастер интента кладёт 18–28
 * всегда (кадр O.08 нарисован с этими числами), а сервер трактует любое minAge как жёсткий гейт:
 * «до 28» — и никого старше, включая тех, у кого возраст просто не указан. Проверено на стенде —
 * тот же запрос с рамкой отдаёт 7 человек, без рамки 8, и первым идёт тот, кого рамка отсекала.
 * Поэтому у возраста есть «Любой», и он снимает поля из интента, а не расставляет их пошире.
 */
function prefsFromIntent(it: any): Prefs {
  const mn = Number(it?.minAge) || 0;
  const mx = Number(it?.maxAge) || 0;
  return {
    sex: String(it?.gender || it?.sex || 'Any'),
    anyAge: !(mn || mx),
    minAge: mn || 18,
    maxAge: mx || 45,
    radiusKm: Number(it?.radiusKm) || 15,
  };
}

export default function Results() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const nav = useNavigation();
  const insets = useSafeAreaInsets();
  const win = useWindowDimensions();
  // Читаем один раз: последующие render'ы не должны затирать уже расширенную выдачу исходной.
  const initial = useMemo(() => takeResults(), []);

  /**
   * Выдача относится к уже запущенному интенту, поэтому назад из неё всегда означает «домой».
   * Перехват нужен не только экранной стрелке: Android Back и iOS swipe иначе снимают маршрут
   * нативно и могут открыть старый стек, если экран попал сюда по устаревшей точке входа.
   */
  const leaveResults = useCallback(() => router.dismissTo('/home'), [router]);
  usePreventRemove(true, (e) => {
    const action = e.data.action;
    if (action.type !== 'GO_BACK' && action.type !== 'POP') { nav.dispatch(action); return; }
    leaveResults();
  });

  const [intent, setIntent] = useState<any>(initial?.intent || {});
  const [cands, setCands] = useState<Cand[]>(initial?.candidates || []);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  /** Следующая непройденная ступень лестницы. */
  const [rung, setRung] = useState(0);
  /**
   * Сколько человек показано и есть ли продолжение.
   *
   * Восемь — первая страница, а не весь ответ. `hasMore` приходит с сервера: без него кнопка
   * жила бы вечно и однажды снова нажималась бы впустую — ровно то, из-за чего это и правится.
   * Изначально `undefined`: выдача пришла со старого вызова, без `limit`, и про продолжение мы
   * ещё ничего не знаем — но раз пришло ровно восемь, спросить стоит.
   */
  const [limit, setLimit] = useState((initial?.candidates || []).length || 8);
  const [hasMore, setHasMore] = useState<boolean | undefined>(undefined);
  /** Кандидат, для которого открыто окно O.14. null — окна нет. */
  const [asking, setAsking] = useState<Cand | null>(null);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState('');
  /** Окно бесплатного тарифа (O.17): с кем уже идёт переписка, когда пробуешь открыть вторую. */
  const [busyWith, setBusyWith] = useState('');
  /** Завершение идёт на сервер — на это время кнопка гаснет, чтобы не нажали дважды. */
  const [ending, setEnding] = useState(false);
  /** С кем реально идёт переписка — по сообщениям, а не по принятым приглашениям (см. activeChatWith). */
  const [chatting, setChatting] = useState('');
  /**
   * Лист O.11a «Изменить условия поиска». Открывается сам, когда точных совпадений нет: борд
   * предлагает расширение сразу, а не прячет его за кнопкой. Черновик условий живёт отдельно от
   * интента — «Отмена» не должна оставлять полурасширенный запрос.
   */
  const [prefsOpen, setPrefsOpen] = useState(() => {
    const cs = initial?.candidates || [];
    // «Точных совпадений нет» на этом сервере выглядит не как ноль карточек, а как пачка замен
    // с пометкой fallback: он почти никогда не возвращает пусто. Лист предлагается в обоих случаях.
    return cs.length === 0 || cs.every((c: any) => !!c.fallback);
  });
  const [prefs, setPrefs] = useState<Prefs>(() => prefsFromIntent(initial?.intent));
  const [reSearching, setReSearching] = useState(false);

  /**
   * Открыть лист — всегда с ЖИВОГО интента.
   *
   * Черновик читался один раз при монтировании экрана. Значит «Отмена» и повторное открытие
   * возвращали брошенные значения, а ступени лестницы §12 (удвоенный радиус) лист вовсе не видел
   * и молча откатывал бы их обратно первым же «Начать поиск».
   */
  const openPrefs = () => { setPrefs(prefsFromIntent(intent)); setPrefsOpen(true); };

  const profile = initial?.profile || {};
  const self = String(profile?.name || '');
  /**
   * Групповой режим той же выдачи — кадры GR.14–GR.17. Экран один, потому что на борде это один
   * и тот же список карточек; меняются шапка, строка регламента и что делает «Пригласить».
   */
  const gmode = isGroupIntent(initial?.intent);
  /**
   * Состояние приглашений — общее с карточкой кандидата (src/invites.ts). Здесь только подписка:
   * отправка, отзыв и потолок живут там, потому что кнопка «Пригласить» есть на обоих экранах.
   * В групповом режиме то же самое делает сессия набора (src/ginvites.ts).
   */
  useInvites(self);
  useGroupSession(self, gmode);

  // Радиус нечего удваивать, когда встреча онлайн, — эта ступень для такого интента бессмысленна.
  const ladder: ExpandAxis[] = useMemo(
    () => EXPAND_LADDER.filter((a) => !(a === 'radius' && intent?.mode === 'online')),
    [intent?.mode]
  );

  /** Карточки-заменители: тема не совпала ни у кого, показаны просто ближайшие подходящие люди. */
  const onlyFallback = cands.length > 0 && cands.every((c) => !!(c as any).fallback);
  const canWiden = rung < ladder.length && (cands.length === 0 || onlyFallback);

  /**
   * Показать ещё — ПРОДОЛЖЕНИЕ того же ранжирования, а не другой запрос.
   *
   * Список запрашивается целиком с бо́льшим пределом, а не дозагружается кусками: ранжирование
   * детерминировано, первые люди остаются на своих местах (проверено на живом сервере), а
   * склейка страниц дала бы дубликаты при малейшем изменении хранилища между запросами.
   */
  const showMore = async () => {
    if (busy) return;
    const next = limit + 8;
    setBusy(true);
    setNote('');
    try {
      // Имя смотрящего — из переданного профиля: сервер по нему исключает человека из его же
      // выдачи, и без `self` он нашёл бы сам себя.
      const self = String((profile as any)?.name || '');
      const r: any = await agent.match(intent, profile, { self, uid: self }, undefined, next);
      const found: Cand[] = (r && r.candidates) || [];
      if (found.length > cands.length) {
        setCands(found);
        setLimit(next);
        patchResults({ candidates: found });
      }
      // Ответ сервера, а не догадка экрана: он один знает, остался ли кто-то за срезом.
      setHasMore(r?.has_more === true);
      if (found.length <= cands.length) setNote(RESULTS.allShown(cands.length));
    } catch {
      setNote(T('Не получилось загрузить ещё. Попробуй ещё раз.', 'Could not load more. Try again.', 'No se pudieron cargar más. Inténtalo de nuevo.'));
    } finally {
      setBusy(false);
    }
  };

  const widen = async () => {
    const axis = ladder[rung];
    if (!axis) return;
    setBusy(true);
    setNote('');
    try {
      const r: any = await agent.expand(intent, profile, axis);
      const next: Cand[] = (r && r.candidates) || [];
      const km = axis === 'radius' ? (intent?.radiusKm || 15) * 2 : undefined;
      setRung(rung + 1);
      if (next.length) {
        setCands(next);
        // Интент двигаем сами: сервер возвращает только карточки, а следующая ступень должна
        // считаться от уже расширенного запроса, иначе радиус удваивался бы от исходного вечно.
        setIntent((prev: any) => {
          const next = {
            ...prev,
            ...(axis === 'adjacent' ? { adjacentAllowed: true } : {}),
            ...(axis === 'parent' ? { broadAllowed: true } : {}),
            ...(axis === 'exactness' ? { exactMatchRequired: false } : {}),
            ...(axis === 'radius' ? { radiusKm: km } : {}),
          };
          // Карточка кандидата берёт интент из того же хранилища — приглашение с неё должно уехать
          // с расширенным запросом, а не с исходным (см. patchResults).
          patchResults({ intent: next });
          return next;
        });
        setNote(`${axisExplain(axis, km)} ${RESULTS.found(next.length)}`);
      } else {
        setNote(`${axisExplain(axis, km)} ${RESULTS.empty()}`);
      }
    } catch {
      setNote(T('Не получилось расширить. Попробуй ещё раз.', 'Could not widen. Try again.', 'No se pudo ampliar. Inténtalo de nuevo.'));
    } finally {
      setBusy(false);
    }
  };

  /** MSG.22: открытые приглашения прямо сейчас — по серверному outbox, а не по памяти экрана. */
  const pendingOut = openInvites();
  const [capOpen, setCapOpen] = useState(false);
  /** GR.14b: кого спрашиваем «отменить приглашение?». Отмена в группе — только через лист. */
  const [cancelAsk, setCancelAsk] = useState<Cand | null>(null);
  const [cancelling, setCancelling] = useState(false);
  /** GR.14f: меню «···» и его второй шаг — подтверждение закрытия (внутри того же листа). */
  const [menuOpen, setMenuOpen] = useState(false);
  const [closeAsk, setCloseAsk] = useState(false);
  const [closing, setClosing] = useState(false);
  /**
   * Обзор GR.17 показывается сам, когда приглашены все; «Invite more people» возвращает к списку
   * (заметка к GR.14c), а следующее приглашение — снова к обзору (заметка к GR.14a).
   */
  const [pickMore, setPickMore] = useState(false);

  /** Отправка приглашения — только из окна O.14/GR.16, никогда прямо с кнопки карточки. */
  const send = async () => {
    const to = String(asking?.name || '');
    // Человек — подписью И id карточки: в выдаче бывают тёзки (kleal-ms/docs/IDENTITY.md).
    const toPeer = { name: to, id: String(asking?.id || '') };
    if (!to || sending) return;
    setSending(true);
    setSendErr('');
    try {
      if (gmode) {
        // GR.16: первое приглашение по пути создаёт группу (лениво — см. шапку ginvites.ts).
        const r = await sendGroupInvite(self, toPeer, intent, groupTitleOf(intent, initial?.query));
        // GR.15. Второй RN-модал поверх закрывающегося на iOS не открывается — ждём, пока уйдёт первый.
        if (r.capped) { setAsking(null); setTimeout(() => setCapOpen(true), 450); return; }
        if (r.full) { setSendErr(GROUP.full()); return; }
        if (!r.ok) throw new Error(r.error || 'invite failed');
        setAsking(null);
        setPickMore(false);
        return;
      }
      const r = await sendInvite(self, toPeer, intent);
      // MSG.22: потолок открытых приглашений. Правило клиентское — см. CAP в candidates.ts.
      if (r.capped) { setAsking(null); setCapOpen(true); return; }
      if (!r.ok) throw new Error(r.error || 'propose failed');
      setAsking(null);
    } catch {
      setSendErr(gmode ? GROUP.sendFailed() : CANDS.inviteFailed());
    } finally {
      setSending(false);
    }
  };

  /** O.15/GR.17 «Cancel»: отозвать НЕотвеченное приглашение. Ответившее — скажет сервер. */
  const cancelInvite = async (to: Peer) => {
    if (gmode) {
      if (!(await cancelGroupInvite(self, to))) setNote(CANDS.cancelFailed());
      return;
    }
    // Исход называется своим именем: «поздно» — не то же самое, что «не получилось».
    const r = await withdrawInvite(self, to);
    if (!r.ok) setNote(r.resolved ? CANDS.cancelTooLate() : CANDS.cancelFailed());
  };

  /** GR.14b «Cancel the invite»: отзыв идёт только отсюда, кнопка карточки лишь спрашивает. */
  const confirmCancel = async () => {
    const c = cancelAsk;
    if (!c || cancelling) return;
    setCancelling(true);
    try {
      await cancelInvite(peerOfCard(c));
    } finally {
      setCancelling(false);
      setCancelAsk(null);
    }
  };

  /**
   * GR.14f «Close the intent»: открытые приглашения закрывает сервер вместе с группой (и шлёт
   * пуши), затея уходит из «Моих». Группы ещё нет — закрывать на сервере нечего, кроме затеи.
   */
  const closeIntent = async () => {
    if (closing) return;
    setClosing(true);
    try {
      const gid = groupId();
      if (gid) {
        const r: any = await gapi.close(gid, self, newIdem('gclose'));
        if (!r?.ok) throw new Error('close failed');
      }
      const iid = String(intent?.id || '');
      if (iid) await agent.intentDelete(self, iid).catch(() => null);
      setMenuOpen(false);
      leaveResults();
    } catch {
      setMenuOpen(false);
      setNote(groupCounters().joined > 1 ? ROOM.endFailed() : GR14.closeFailed());
    } finally {
      setClosing(false);
    }
  };

  /**
   * GR.14f «Change it» — правка затеи на её странице, пока приглашений нет. После первого
   * приглашения правка обязана дойти до приглашённых (обновить их инвайт и прислать пуш, GR.14i/k) —
   * это сервер, и пока его нет, пункт выключен, а не врёт.
   */
  const changeIt = () => {
    const iid = String(intent?.id || '');
    if (!iid) return;
    setMenuOpen(false);
    setTimeout(() => router.navigate({ pathname: '/myintent', params: { id: iid, edit: '1' } }), 350);
  };

  /** «Начать поиск» из листа O.11a: тот же /api/agent/match, но с условиями, которые человек ослабил сам. */
  const reSearch = async () => {
    if (reSearching) return;
    setReSearching(true);
    setNote('');
    try {
      const next: any = { ...intent };
      // «Любой» — это отсутствие ключей, а не 18–80: сервер и на 18 отсекает всех, у кого возраст
      // не заполнен («age unknown»), так что раздвинуть рамку до упора и снять её — разные вещи.
      if (prefs.anyAge) { delete next.minAge; delete next.maxAge; }
      else { next.minAge = prefs.minAge; next.maxAge = prefs.maxAge; }
      // Оба ключа: гейт читает `gender || sex`, и убрать один — значит не убрать ничего.
      if (prefs.sex && prefs.sex !== 'Any') { next.sex = prefs.sex; next.gender = prefs.sex; }
      else { delete next.sex; delete next.gender; }
      if (intent?.mode !== 'online') next.radiusKm = prefs.radiusKm;
      const r: any = await agent.match(next, profile, {
        self, uid: self, city: profile?.city,
      });
      setIntent(r?.intent || next);
      patchResults({ intent: r?.intent || next });
      const found: Cand[] = (r?.candidates || []) as Cand[];
      setCands(found);
      setRung(0);                      // условия сменились — лестница §12 начинается заново
      setPrefsOpen(false);
      // Лист закрывается, список меняется — и раньше нигде не говорилось, ОТ ЧЕГО он изменился.
      // Ступени лестницы называют себя вслух; этот путь должен вести себя так же.
      const conds = [
        prefs.sex && prefs.sex !== 'Any' ? sexLabel(prefs.sex).toLowerCase() : PREFS.anySex(),
        prefs.anyAge ? PREFS.ageAny() : PREFS.ageBand(prefs.minAge, prefs.maxAge),
        ...(intent?.mode !== 'online' ? [PREFS.distVal(prefs.radiusKm)] : []),
      ].join(', ');
      setNote(`${PREFS.applied(conds)} ${found.length ? RESULTS.found(found.length) : RESULTS.empty()}`);
    } catch {
      setNote(T('Не получилось поискать. Попробуй ещё раз.', 'The search failed. Try again.', 'La búsqueda falló. Inténtalo de nuevo.'));
    } finally {
      setReSearching(false);
    }
  };

  /** С кем реально идёт переписка — правило одного чата (O.17) считается по сообщениям. */
  const loadChats = useCallback(async () => {
    if (!self) return;
    try {
      const th: any = await agent.threads(self).catch(() => ({ threads: [] }));
      setChatting(activeChatWith((th?.threads || []) as any[]));
      // Заодно блокировки: возвращаясь в выдачу после перезапуска, человек не должен снова
      // видеть того, кого заблокировал.
      const sf: any = await agent.safety(self).catch(() => ({ blocked: [] }));
      setBlocked(((sf?.blocked || []) as any[]).map((x) => String(x).trim().toLowerCase()));
    } catch {
      /* тихо: фоновая дотяжка состояний */
    }
  }, [self]);

  useEffect(() => { loadChats(); }, [loadChats]);
  useEffect(() => {
    const id = setInterval(loadChats, 6000);
    return () => clearInterval(id);
  }, [loadChats]);

  /**
   * Открыть переписку. Правило бесплатного тарифа с кадра O.17 — один живой чат за раз — живёт
   * ЗДЕСЬ, потому что на сервере его нет: он позволяет писать любому, кто принял приглашение.
   * Когда тариф появится на сервере, проверку надо перенести туда — иначе она обходится любым
   * другим клиентом.
   */
  const openChat = (name: string, photo?: string, id?: string) => {
    // В группе личной переписки с человеком НЕТ — это обещано ещё в шите приглашения (GR.16).
    // Открывается общая комната: она и есть разговор. Потолок «один чат за раз» сюда тоже не
    // относится — он про 1:1.
    if (gmode) {
      const gid = groupId();
      if (gid) router.navigate({ pathname: '/group', params: { gid } });
      return;
    }
    const active = chatting;
    if (active && active.toLowerCase() !== name.toLowerCase()) {
      setBusyWith(active);
      return;
    }
    router.navigate({
      pathname: '/conversation',
      params: { who: name, who_id: id || '', title: String(intent?.title || (intent?.topics || []).join(', ') || ''), photo: photo || '' },
    });
  };

  /**
   * Кого в этой выдаче показывать нельзя.
   *
   * Два источника, и оба нужны. `isHidden` — «не интересно» и только что нажатая блокировка: она
   * действует сразу, не дожидаясь ответа сервера. `blocked` — список с сервера: он переживает
   * перезапуск приложения, а память экрана — нет.
   */
  const [blocked, setBlocked] = useState<string[]>([]);
  const visible = useMemo(
    () => cands.filter((c) => {
      const n = String(c.name || '');
      return n && !isHidden(n) && !blocked.includes(n.trim().toLowerCase());
    }),
    [cands, blocked],
  );

  /** O.16 «Убрать»: карточка уходит с экрана. Отклонённое приглашение сервер уже закрыл сам. */
  const removeCard = (name: string) => {
    setCands((prev) => prev.filter((c) => String(c.name || '') !== name));
  };

  const openProfile = (c: Cand) => {
    setCandidate(c);
    router.navigate('/candidate');
  };

  // Экран открыт напрямую — обновлением страницы или по ссылке. Выдача живёт один переход, и
  // выдумывать её задним числом нечем; честнее сказать это и предложить поискать заново.
  if (!initial) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/* Фирменный фон — тот же бледный слой, что у разговора с Бадди (ChatShell). */}
        <Ambient glows={GLOW_FORM} />
        <View style={s.head}>
          <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={leaveResults} />
          <Text style={s.headTitle}>{T('Выдача устарела', 'These results are gone', 'Estos resultados ya no están')}</Text>
        </View>
        <View style={s.scroll}>
          <Text style={s.lead}>
            {T('Результаты поиска живут до перезагрузки. Давай поищем заново.',
               'Search results only live until the page reloads. Let’s search again.', 'Los resultados de búsqueda solo duran hasta que se recarga la página. Busquemos de nuevo.')}
          </Text>
          {/* Новый поиск начинается там же, где и любой другой: с темы, а не с формата. */}
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => { router.dismissTo('/home'); router.navigate('/create'); }}>
            <Text style={s.ctaText}>{T('Новый поиск', 'New search', 'Nueva búsqueda')}</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const title = cands.length === 0 ? RESULTS.empty()
              : onlyFallback ? T('Прямых совпадений нет', 'No direct matches', 'No hay coincidencias directas')
              : RESULTS.best();

  // ---------------------------------------------------------------- групповой режим (GR.14–GR.17a)
  const gc = groupCounters();
  const gid = groupId();
  const gTitle = groupTitleOf(intent, initial?.query);
  const short = shortTitle(gTitle);
  /** Сколько мест под приглашённых: «The first two who say yes» — группа минус организатор. */
  const total = gid ? gc.max : (Number(intent?.groupSize) || gc.max);
  const take = Math.max(1, total - 1);
  const joinedOthers = Math.max(0, gc.joined - 1);
  const gstat = (c: Cand): GStatus | undefined => (gmode ? groupStatusFor(peerOfCard(c)) : undefined);
  const named = (c: Cand) => String(c.name || '');
  const byStat = (st: GStatus) => visible.filter((c) => gstat(c) === st);
  const yesNames = byStat('joined').map(named);
  const waitNames = byStat('pending').map(named);
  const noCands = byStat('declined');
  const shutNames = byStat('closed').map(named);
  const allInvited = gmode && !!gid && visible.length > 0 && visible.every((c) => !!gstat(c));
  const overview = allInvited && !pickMore && !gc.full;
  /** Последний отказ — им озаглавлен GR.17a («Elly can’t make it»). */
  const lastNo = noCands.length
    ? noCands.reduce((a, b) => ((groupStatusAt(peerOfCard(b)) || 0) > (groupStatusAt(peerOfCard(a)) || 0) ? b : a))
    : null;
  /** «Invite more people» обзора: свободный слот — к списку (GR.14c), кап — лист Plus (GR.15). */
  const inviteMore = () => {
    if (gc.open >= gc.cap) { setCapOpen(true); return; }
    setPickMore(true);
  };
  /** Пояснение под исходом на карточке — по исходу и по тому, сколько мест ещё ждут «да». */
  const gNote = (c: Cand, st?: GStatus): string => {
    const n = named(c);
    if (st === 'joined') return GR14.joinedNote(n, take - joinedOthers);
    if (st === 'declined') return GR14.declinedNote(n);
    if (st === 'closed') {
      const why = groupClosedOf(peerOfCard(c))?.why;
      return why === 'expired' ? GR14.closedExpiredNote(n) : why === 'other' ? GR14.closedOtherNote(n) : GR14.closedNote(n, pronOf(c));
    }
    return GR14.sentNote(n, pronOf(c));
  };
  /**
   * OF.12a–12e — «выбор из ответивших» у приглашений один на один. Состояние заявки показывается
   * тем же блоком, что у группы; истёкшее и отозванное остаются в прежнем виде (O.14a).
   */
  /** O.12: у звонка в текстах «for your call», а не короткое название затеи. */
  const soloOnline = !gmode && intent?.mode === 'online';
  const soloShort = soloOnline ? OFP.callWord() : (short || T('затеи', 'intent', 'plan'));
  const soloRows = gmode ? [] : invitesFor(intent);
  const pickedRow = soloRows.find((r) => r.status === 'accepted');
  const soloLive = soloRows.filter((r) => r.status === 'pending' || r.status === 'answered' || r.status === 'declined');
  const soloAnswered = soloLive.filter((r) => r.status !== 'pending').length;
  const soloEnds = (() => {
    const wait = soloLive.filter((r) => r.status === 'pending' && r.expiresAt).map((r) => Number(r.expiresAt));
    const pickBy = soloLive.filter((r) => r.status === 'answered' && r.pickBy).map((r) => Number(r.pickBy));
    const t = wait.length ? Math.min(...wait) : pickBy.length ? Math.min(...pickBy) : 0;
    return t ? t * 1000 : undefined;
  })();
  const soloOf = (c: Cand): SoloState | undefined => {
    if (gmode) return undefined;
    const row = inviteTo(peerOfCard(c), intent);
    if (!row) return undefined;
    const n = named(c);
    const p = pronOf(c);
    const at = row.updated ? row.updated * 1000 : undefined;
    if (row.status === 'pending') return { st: 'sent', at, note: OFP.sentNote(n, p) };
    if (row.status === 'answered') return { st: 'yes', at: row.answeredAt ? row.answeredAt * 1000 : at, note: OFP.yesNote(n, p) };
    if (row.status === 'accepted') return { st: 'picked', at, note: OFP.pickedNote(n) };
    if (row.status === 'not_picked') {
      return { st: 'closed', at, note: pickedRow ? OFP.closedNote(pickedRow.to, n, p) : OFP.closedPlain(n, p) };
    }
    if (row.status === 'declined') return { st: 'declined', at, note: GR14.declinedNote(n) };
    return undefined;
  };
  /**
   * OF.14b / 15 / 16 / 14a — обзор вместо списка, когда приглашены все из выдачи (то же правило,
   * что у группы, GR.17). «Invite more people» возвращает к списку.
   */
  const soloRowOf = (c: Cand) => inviteTo(peerOfCard(c), intent);
  const soloAll = !gmode && !pickedRow && visible.length > 0 && visible.every((c) => {
    const st = soloRowOf(c)?.status;
    return st === 'pending' || st === 'answered' || st === 'declined' || st === 'expired';
  });
  const soloOverview = soloAll && !pickMore;
  const soloBy = (st: string) => visible.filter((c) => soloRowOf(c)?.status === st);
  const soloYes = soloBy('answered');
  const soloWait = soloBy('pending');
  const soloNo = soloBy('declined');
  const soloGone = soloBy('expired');
  const soloLastNo = soloNo.length
    ? soloNo.reduce((a, b) => ((soloRowOf(b)?.updated || 0) > (soloRowOf(a)?.updated || 0) ? b : a))
    : null;
  const soloView: 'pick' | 'expired' | 'declined' | 'sent' = soloYes.length ? 'pick'
    : soloGone.length === visible.length ? 'expired' : soloLastNo ? 'declined' : 'sent';
  const soloInviteMore = () => {
    if (openInvites(String((intent as any)?.id || '')).length >= CAP.limit) { setCapOpen(true); return; }
    setPickMore(true);
  };
  const [picking, setPicking] = useState('');
  /** OF.12d «Pick Marta» → OF.12e: список остаётся, у выбранного — «Open the chat». */
  const pick = async (c: Cand) => {
    if (picking) return;
    setPicking(String(c.id || c.name || ''));
    setNote('');
    const r = await pickInvite(self, peerOfCard(c));
    setPicking('');
    if (!r.ok) setNote(OFP.pickFailed());
  };
  const selfPhoto = myId() ? mediaUrl(`/api/onboarding/photo/${encodeURIComponent(myId())}.jpg`) : undefined;

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      {/* Шапка в общем ряду с остальными экранами (insets.top + 6). Кадры борда нарисованы на
          телефоне с верхним отступом 47, у iPhone 17 Pro он 62 — «ниже на 12» там честно. */}
      <View style={s.head}>
        <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={leaveResults} />
        {/* Красная точка + заголовок — шапка кадра O.12; в группе — название затеи (GR.14). */}
        {gmode || soloOverview ? null : <View style={s.dot} />}
        <Text
          style={[s.headTitle, (gmode || soloOverview) && heading(lang, { fontSize: 20, lineHeight: 24, letterSpacing: 0 })]}
          numberOfLines={1}
        >
          {/* OF.14b–16: в обзоре шапка — название затеи, как у группы. */}
          {gmode || soloOverview ? gTitle : title}
        </Text>
        {gmode && !overview ? (
          <GlassIconButton label={T('Ещё', 'More', 'Más')} onPress={() => { setCloseAsk(false); setMenuOpen(true); }}>
            <IconDots size={22} c={color.fg} />
          </GlassIconButton>
        ) : null}
      </View>

      {/* Список и обзор — разные виды: ключ сменой вида возвращает прокрутку наверх, иначе заголовок
          обзора оставался под шапкой там, где кончился список (снимок стенда GR.17). */}
      <ScrollView onScroll={navCollapse} scrollEventThrottle={16} key={overview || soloOverview ? 'overview' : 'list'} contentContainerStyle={[s.scroll, { paddingBottom: 120 }]}>
        {overview ? (
          /* GR.17 / GR.17a: приглашены все — обзор вместо списка карточек. */
          <>
            <View style={s.gHead}>
              <Text style={[s.gTitle, { fontFamily: labelFamily(lang) }]}>
                {lastNo ? GR14.declinedTitle(named(lastNo)) : GR14.sentTitle()}
              </Text>
              <Text style={s.gLead}>
                {lastNo
                  ? GR14.declinedLead(namesList(yesNames), namesList(waitNames), named(lastNo))
                  : yesNames.length && waitNames.length
                  ? GR14.sentLeadIn(namesList(yesNames), namesList(waitNames), take - joinedOthers)
                  : GR14.sentLead(namesList(waitNames.length ? waitNames : visible.map(named)), take)}
              </Text>
            </View>
            <View style={{ gap: 8 }}>
              <PlanCard intent={intent} />
              <RoundIndicator joined={joinedOthers} total={take} endsAt={groupEndsAt()} />
            </View>
            <View>
              {visible.map((c, i) => {
                const st = gstat(c);
                return (
                  <MemberRow
                    key={(c.id || c.name || '') + i}
                    photo={c.photo ? mediaUrl(String(c.photo)) : undefined}
                    name={`${c.name}${c.age ? `, ${c.age}` : ''}`}
                    status={st === 'joined' ? GR14.joinedTitle() : st === 'declined' ? GR14.declined()
                          : st === 'closed' ? GR14.closed() : GR14.rowPending()}
                    kind={st === 'pending' ? 'sent' : st}
                  />
                );
              })}
              <MemberRow photo={selfPhoto} name={GR14.you()} status={GR14.created()} kind="you" organiser />
            </View>
            <GlassPill tone="light" style={s.btn48} label={lastNo ? GR14.inviteElse() : GR14.inviteMore()} onPress={inviteMore} />
            {note ? <Text style={s.note}>{note}</Text> : null}
          </>
        ) : soloOverview ? (
          /* OF.14b «Invites sent» · OF.16 «… can’t make it» · OF.14a «Nobody answered in time» · OF.15 «Pick who you’ll meet». */
          <>
            <View style={s.gHead}>
              <Text style={[s.gTitle, { fontFamily: labelFamily(lang) }]}>
                {soloView === 'pick' ? (soloOnline ? OFP.pickTitleCall() : OFP.pickTitle()) : soloView === 'expired' ? OFP.expiredTitle()
                  : soloView === 'declined' ? GR14.declinedTitle(named(soloLastNo || {})) : GR14.sentTitle()}
              </Text>
              <Text style={s.gLead}>
                {soloView === 'pick' ? OFP.pickLead(namesList(soloYes.map(named)), soloYes.length > 1)
                  : soloView === 'expired' ? OFP.expiredLead(namesList(visible.map(named)), soloShort)
                  : soloView === 'declined' ? OFP.declinedLead(namesList(soloWait.map(named)), named(soloLastNo || {}))
                  : OFP.sentLead(namesList(visible.map(named)))}
              </Text>
            </View>
            <View style={{ gap: 8 }}>
              {soloView === 'pick' ? null : <PlanCard intent={intent} callLine={soloOnline ? OFP.callLine() : undefined} />}
              {soloView === 'expired' ? null : (
                <RoundIndicator label={OFP.answered()} joined={soloAnswered} total={soloLive.length} endsAt={soloEnds} />
              )}
            </View>
            {soloView === 'pick' ? (
              <View style={s.cards}>
                {soloYes.map((c, i) => (
                  <CandCard
                    key={(c.id || c.name || '') + i}
                    c={c}
                    badge={visible.indexOf(c) === 0 ? CANDS.bestBadge() : CANDS.matchBadge()}
                    best={visible.indexOf(c) === 0}
                    solo={soloOf(c)}
                    picking={picking === String(c.id || c.name || '')}
                    onPick={() => pick(c)}
                    onOpen={() => openProfile(c)}
                    onInvite={() => {}}
                    onCancel={() => {}}
                    onOpenChat={() => openChat(String(c.name || ''), c.photo, String(c.id || ''))}
                    onRemove={() => {}}
                  />
                ))}
              </View>
            ) : null}
            <View>
              {visible.filter((c) => soloView !== 'pick' || soloRowOf(c)?.status !== 'answered').map((c, i) => {
                const st = soloRowOf(c)?.status;
                return (
                  <MemberRow
                    key={(c.id || c.name || '') + i}
                    photo={c.photo ? mediaUrl(String(c.photo)) : undefined}
                    name={`${c.name}${c.age ? `, ${c.age}` : ''}`}
                    status={st === 'answered' ? OFP.yes() : st === 'declined' ? GR14.declined()
                          : st === 'expired' ? OFP.didntAnswer() : GR14.rowPending()}
                    kind={st === 'answered' ? 'joined' : st === 'declined' ? 'declined' : st === 'expired' ? 'closed' : 'sent'}
                  />
                );
              })}
              {soloView === 'pick' ? null : (
                <MemberRow photo={selfPhoto} name={GR14.you()} status={GR14.created()} kind="you" organiser />
              )}
            </View>
            {soloView === 'expired' ? (
              <>
                <GlassPill tone="brand" style={s.btn48} busy={busy} label={GR14.seeNew()} onPress={showMore} />
                <GlassPill tone="light" style={s.btn48} label={PREFS.title()} onPress={openPrefs} />
              </>
            ) : soloView === 'pick' ? null : (
              <GlassPill tone="light" style={s.btn48}
                         label={soloView === 'declined' ? GR14.inviteElse() : GR14.inviteMore()} onPress={soloInviteMore} />
            )}
            {note ? <Text style={s.note}>{note}</Text> : null}
          </>
        ) : (
        <>
        {gmode ? (
          /* GR.14: заголовок и правило набора; полоса — с первым приглашением (GR.14a), у полной группы её нет (GR.14e). */
          <>
            <View style={s.gHead}>
              <Text style={[s.gTitle, { fontFamily: labelFamily(lang) }]}>{GR14.title()}</Text>
              <Text style={s.gLead}>
                {gc.full
                  ? GR14.leadFull(namesList(yesNames), namesList(shutNames), shutNames.length > 1)
                  : onlyFallback
                  ? T('Никто не занимается ровно этим. Вот кто рядом и с кем это может получиться.',
                      'Nobody is doing exactly that. Here are people nearby it could work with.', 'Nadie está haciendo exactamente eso. Aquí hay personas cercanas con las que podría funcionar.')
                  : GR14.lead(visible.length, short, gc.cap, take)}
              </Text>
            </View>
            {gid && !gc.full ? <RoundIndicator joined={joinedOthers} total={take} endsAt={groupEndsAt()} /> : null}
            {onlyFallback ? (
              <Pressable accessibilityRole="button" style={s.prefsBtn} onPress={openPrefs}>
                <Text style={s.prefsBtnText}>{PREFS.title()}</Text>
              </Pressable>
            ) : null}
          </>
        ) : onlyFallback ? (
          <View style={{ gap: space.sm }}>
            <Text style={s.lead}>
              {T('Никто не занимается ровно этим. Вот кто рядом и с кем это может получиться.',
                 'Nobody is doing exactly that. Here are people nearby it could work with.', 'Nadie está haciendo exactamente eso. Aquí hay personas cercanas con las que podría funcionar.')}
            </Text>
            <Pressable accessibilityRole="button" style={s.prefsBtn} onPress={openPrefs}>
              <Text style={s.prefsBtnText}>{PREFS.title()}</Text>
            </Pressable>
          </View>
        ) : cands.length > 0 ? (
          /* OF.12 / OF.12e: правило выбора словами; с первым приглашением — счётчик ответов (OF.12a). */
          <>
            <Text style={s.lead}>
              {pickedRow
                ? OFP.leadPicked(pickedRow.to, namesList(soloRows.filter((r) => r.status === 'not_picked').map((r) => r.to)))
                : OFP.lead(visible.length, soloShort, CAP.limit)}
            </Text>
            {soloLive.length && !pickedRow ? (
              <RoundIndicator label={OFP.answered()} joined={soloAnswered} total={soloLive.length} endsAt={soloEnds} />
            ) : null}
          </>
        ) : null}

        {/* GR.14e: группа набрана — «показать ещё» и его итог («That's everyone») больше ни к чему. */}
        {note && !(gmode && gc.full) ? <Text style={s.note}>{note}</Text> : null}

        {cands.length === 0 ? (
          <View style={s.noMatch}>
            <View style={s.noMatchArt}><IconPerson size={34} /></View>
            <Text style={s.noMatchTitle}>{PREFS.noMatches()}</Text>
            <Text style={s.lead}>{PREFS.noFitNote()}</Text>
            {/* На всю ширину: в узкой пилюле подпись вылезала за края. */}
            <Pressable accessibilityRole="button" style={[s.cta, { alignSelf: 'stretch' }]} onPress={openPrefs}>
              <Text style={s.ctaText}>{PREFS.title()}</Text>
            </Pressable>
          </View>
        ) : null}

        <View style={s.cards}>
          {visible.map((c, i) => {
            const st = gstat(c);
            return (
              <CandCard
                key={(c.name || '') + i}
                c={c}
                badge={(c as any).fallback ? '' : i === 0 ? CANDS.bestBadge() : CANDS.matchBadge()}
                best={i === 0}
                /* ПРО ЭТУ ЗАТЕЮ, а не про человека вообще: с тем, с кем уже виделись по другой,
                   карточка обязана снова предлагать «Пригласить». */
                status={gmode ? undefined : inviteTo(peerOfCard(c), intent)?.status}
                group={gmode ? { st, at: groupStatusAt(peerOfCard(c)), note: gNote(c, st) } : undefined}
                solo={soloOf(c)}
                picking={picking === String(c.id || c.name || '')}
                onPick={() => pick(c)}
                onOpen={() => openProfile(c)}
                onInvite={() => { setSendErr(''); setAsking(c); }}
                /* OF.12b: и один на один отзыв идёт через вопрос — человеку уйдёт пуш. Истёкшее и
                   старое «принято» отзываются сразу, как раньше: спрашивать там не о чем. */
                onCancel={() => (gmode || inviteTo(peerOfCard(c), intent)?.status === 'pending'
                  ? setCancelAsk(c) : cancelInvite(peerOfCard(c)))}
                onOpenChat={() => openChat(String(c.name || ''), c.photo, String(c.id || ''))}
                onRemove={() => removeCard(String(c.name || ''))}
              />
            );
          })}
        </View>

        {/* «Ещё» показывается, пока сервер не сказал, что это все. Оно НЕ заменяет расширение:
            то ослабляет запрос и объясняется словами, это просто продолжает список. В группе, когда
            звать из списка уже некого, та же кнопка зовётся «See new candidates» (GR.14d). */}
        {cands.length > 0 && hasMore !== false && !(gmode && gc.full) ? (
          <GlassPill
            tone="light"
            style={s.btn48}
            busy={busy}
            label={gmode && (allInvited || noCands.length > 0) ? GR14.seeNew() : RESULTS.more()}
            onPress={showMore}
          />
        ) : null}

        {canWiden ? (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy }}
            style={[s.cta, busy && { opacity: 0.6 }]}
            onPress={busy ? undefined : widen}
          >
            {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{RESULTS.widen()}</Text>}
          </Pressable>
        ) : null}

        {rung >= ladder.length && (cands.length === 0 || onlyFallback) ? (
          <Text style={s.note}>{RESULTS.exhausted()}</Text>
        ) : null}
        </>
        )}
      </ScrollView>

      {/* Панель на выдаче есть на кадре O.12. */}
      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav active="intents" />
      </View>

      <PrefsSheet
        open={prefsOpen}
        prefs={prefs}
        setPrefs={setPrefs}
        offline={intent?.mode !== 'online'}
        busy={reSearching}
        onStart={reSearch}
        onClose={() => setPrefsOpen(false)}
        bottomInset={insets.bottom}
        // Тело листа не выше половины экрана: остальное — шапка, две кнопки и вырез снизу.
        maxBody={Math.round(win.height * 0.46)}
      />

      {/* Окно бесплатного тарифа — кадр O.17. Текст с кадра; ограничение клиентское, см. openChat. */}
      <Sheet visible={!!busyWith} onClose={() => setBusyWith('')} title={CHAT.busyTitle(busyWith)}>
        <Text style={s.sheetBody}>{CHAT.busyBody()}</Text>
        {/* Тарифа в продукте нет — кнопка честно выключена, как везде в каркасе. */}
        <View style={[s.sheetSend, { opacity: 0.45 }]}>
          <Text style={s.sheetSendText}>{CHAT.getPlus()}</Text>
        </View>
        <Text style={s.plusPrice}>{CHAT.plusPrice()}</Text>
        {/*
          Кнопка называется «Закончить разговор с N» — и заканчивает его.
          Раньше она просто открывала переписку с этим человеком: слово «закончить» вело туда, где
          завершение спрятано за ⋮, и передать намерение туда было нечем. Человек нажимал
          «закончить» и оказывался в том же чате, из которого хотел выйти.

          Спрашиваем перед этим: разговор закрывается для ДВОИХ, и второму об этом скажут.
        */}
        <Pressable
          accessibilityRole="button"
          style={[s.sheetNot, ending && { opacity: 0.6 }]}
          disabled={ending}
          onPress={() => {
            const who = busyWith;
            const go = async () => {
              setEnding(true);
              try {
                await agent.threadEnd(self, who);
                // Список тредов перечитываем сразу: слот освобождает не наше намерение, а
                // системная строка на сервере, и до неё окно продолжало бы висеть.
                await loadChats();
                setBusyWith('');
              } catch {
                setSendErr(CHAT.endFailed());
              } finally {
                setEnding(false);
              }
            };
            Alert.alert(CHAT.endAskTitle(who), CHAT.endAskBody(), [
              { text: CHAT.endAskNo(), style: 'cancel' },
              { text: CHAT.endAskYes(), style: 'destructive', onPress: go },
            ]);
          }}
        >
          <Text style={s.sheetNotText}>{CHAT.endChatWith(busyWith)}</Text>
        </Pressable>
      </Sheet>

      {/* Потолок открытых приглашений — кадр MSG.22, в групповом режиме GR.15. Отзыв по id сервера. */}
      <Sheet
        visible={capOpen}
        onClose={() => setCapOpen(false)}
        title={gmode
          ? <>Kleal <Text style={{ color: color.primary }}>Plus+</Text></>
          : 'Kleal Plus'}
      >
        {gmode ? (
          /* GR.15: лимит словами и два выхода. Plus в продукте нет — кнопка честно выключена. */
          <>
            <SheetText lead={GR14.capLead(gc.open)} note={GR14.capNote(gc.cap, GROUP_FREE_MAX_TOTAL)} />
            <GlassPill tone="brand" style={s.btn48} disabled label={GR14.getPlus()} />
            <GlassPill tone="dark" style={s.btn48} label={GR14.notNow()} onPress={() => setCapOpen(false)} />
          </>
        ) : (
          /* OF.17: тот же лист у приглашений один на один — лимит словами и два выхода. Plus в
             продукте нет, кнопка честно выключена; отозвать приглашение можно с карточки человека. */
          <>
            <SheetText lead={CAP.plusLead(pendingOut.length)} note={CAP.plusNote(CAP.limit)} />
            <GlassPill tone="brand" style={s.btn48} disabled label={GR14.getPlus()} />
            <GlassPill tone="dark" style={s.btn48} label={GR14.notNow()} onPress={() => setCapOpen(false)} />
          </>
        )}
      </Sheet>

      {/* GR.14b «Cancel invite»: отзыв — только после вопроса. Человеку уйдёт пуш, место освободится. */}
      <Sheet visible={!!cancelAsk} onClose={() => setCancelAsk(null)} title={GR14.cancelTitle()}>
        <SheetText lead={GR14.cancelLead(named(cancelAsk || {}))} note={GR14.cancelNote(pronOf(cancelAsk))} />
        <GlassPill tone="brand" style={s.btn48} busy={cancelling} label={GR14.cancelYes()} onPress={confirmCancel} />
        <GlassPill tone="dark" style={s.btn48} label={GR14.keep()} onPress={() => setCancelAsk(null)} />
      </Sheet>

      {/* GR.14f — меню затеи. Подтверждение закрытия рисуется ВНУТРИ листа: второй модал поверх не откроется. */}
      <Sheet visible={menuOpen} onClose={() => setMenuOpen(false)} title={gTitle}>
        {closeAsk ? (
          /* Вступившие уже есть — это закрытие ГРУППЫ, и говорить о нём надо словами комнаты (GR.24b). */
          joinedOthers > 0 ? (
            <>
              <SheetText lead={ROOM.endTitle(gTitle)} note={ROOM.endBody(namesList(yesNames))} />
              <GlassPill tone="brand" style={s.btn48} busy={closing} label={ROOM.endConfirm()} onPress={closeIntent} />
              <GlassPill tone="dark" style={s.btn48} label={ROOM.keepGoing()} onPress={() => setCloseAsk(false)} />
            </>
          ) : (
            <>
              <SheetText lead={GR14.closeLead()} note={GR14.closeNote()} />
              <GlassPill tone="brand" style={s.btn48} busy={closing} label={GR14.menuClose()} onPress={closeIntent} />
              <GlassPill tone="dark" style={s.btn48} label={GR14.keep()} onPress={() => setCloseAsk(false)} />
            </>
          )
        ) : (
          <View style={{ gap: 4 }}>
            <SheetItem
              icon={<IconPencil size={20} />}
              label={GR14.menuChange()}
              note={GR14.menuChangeNote()}
              disabled={!!gid || !intent?.id}
              onPress={changeIt}
            />
            <SheetItem
              danger
              icon={<IconBan size={20} />}
              label={joinedOthers > 0 ? ROOM.endGroup() : GR14.menuClose()}
              note={joinedOthers > 0 ? GR14.menuEndNote(namesList(yesNames)) : GR14.menuCloseNote()}
              onPress={() => setCloseAsk(true)}
            />
          </View>
        )}
      </Sheet>

      <InviteSheet
        cand={asking}
        sending={sending}
        err={sendErr}
        group={gmode}
        short={short}
        online={intent?.mode === 'online'}
        hybrid={intent?.mode === 'hybrid'}
        onSend={send}
        onClose={() => setAsking(null)}
        bottomInset={insets.bottom}
      />
    </View>
  );
}

/**
 * Карточка кандидата — кадр O.12, вид — GR.14 борда «0 · Create the intent»: стекло со скруглением 16,
 * бейдж справа сверху («Best match» зелёный, «Match» серый), фото 64, имя 15/22, строка «занятие ·
 * место», чипы интересов со значками в ленту, «Kleal summary» на белом 56% и кнопка 40.
 * Нажатие на верх карточки открывает полный профиль (O.13).
 *
 * В группе вместо сводки встаёт блок исхода (GR.14a–14e), и кнопка следует за ним: «Invite Jane» →
 * «Cancel invite» → «Open the group chat»; у отказа и закрытого кнопки нет — позвать снова нельзя.
 */
function CandCard({
  c, badge, best, status, group, solo, picking, onPick, onOpen, onInvite, onCancel, onOpenChat, onRemove,
}: {
  c: Cand;
  badge: string;
  /** Первая карточка — «Best match»: зелёный бейдж вместо серого. */
  best?: boolean;
  /** Состояние приглашения 1:1 из общего стора (src/invites.ts). */
  status?: ReqStatus;
  /** Групповой режим: исход приглашения, когда он наступил, и пояснение под ним. */
  group?: { st?: GStatus; at?: number; note: string };
  /** Один на один, «выбор из ответивших» (OF.12a–12e). */
  solo?: SoloState;
  picking?: boolean;
  onPick?: () => void;
  onOpen: () => void;
  onInvite: () => void;
  onCancel: () => void;
  onOpenChat: () => void;
  onRemove: () => void;
}) {
  const readiness = candReadiness(c);
  /** Занятия и города в данных может не быть — тогда вайб/интересы и километры (см. src/candidates.ts). */
  const role = String((c as any).occupation || '').trim() || candSubtitle(c, ru());
  const where = String((c as any).city || '').trim() || candWhere(c);
  const summary = candSummary(c, ru());
  /** Ссылка на фото есть, а файла нет: <Image> рисует пустоту — не кружок, а дыру в карточке. */
  const [broken, setBroken] = useState(false);
  const name = String(c.name || '');
  const st = group?.st;
  const kind: StatusKind | undefined = st === 'pending' ? 'sent' : st;

  return (
    /*
      ПЛЁНКА, А НЕ СИСТЕМНОЕ СТЕКЛО. На кадре карточка — белое 67% с размытием 24 поверх кремовой
      подложки, то есть тёплая, чуть темнее белого. Системное стекло iOS 26 тонирует её почти в чистый
      белый, и белые чипы и сводка на ней пропадали (снимок стенда 03.10).
    */
    <View style={s.card}>
      <Pressable accessibilityRole="button" onPress={onOpen} style={({ pressed }) => [s.cardTop, pressed && { opacity: 0.92 }]}>
        {c.photo && !broken ? (
          <Image source={{ uri: mediaUrl(String(c.photo)) }} style={s.av} onError={() => setBroken(true)} />
        ) : (
          <View style={[s.av, s.avEmpty]}><IconPerson /></View>
        )}
        <View style={s.identity}>
          <Text style={[s.name, badge ? { paddingRight: 72 } : null]} numberOfLines={1}>
            {c.name}{c.age ? `, ${c.age}` : ''}
          </Text>
          <View style={s.metaRow}>
            {role ? <Text style={[s.meta, { flexShrink: 1 }]} numberOfLines={1}>{role}</Text> : null}
            {where ? (
              <View style={s.whereRow}>
                <IconPin size={14} c={color.primary} />
                <Text style={s.meta} numberOfLines={1}>{where}</Text>
              </View>
            ) : null}
          </View>
        </View>
      </Pressable>

      {/* Чипы — лентой до края карточки, как на кадре: пятый уходит за кромку и докручивается. */}
      {(c.interests || []).length ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.tagsOuter} contentContainerStyle={s.tags}>
          {interestLabels(c.interests).slice(0, 8).map((t, i) => {
            const label = t.charAt(0).toUpperCase() + t.slice(1);
            const e = interestEmoji(t);
            return (
              <View key={t + i} style={s.tag}><Text style={s.tagText}>{e ? `${e} ${label}` : label}</Text></View>
            );
          })}
        </ScrollView>
      ) : null}

      {group && kind ? (
        <StatusBlock kind={kind} at={group.at} text={group.note} />
      ) : solo ? (
        <StatusBlock
          kind={solo.st === 'sent' ? 'sent' : solo.st === 'closed' ? 'closed' : solo.st === 'declined' ? 'declined' : 'joined'}
          label={solo.st === 'yes' ? OFP.yes() : solo.st === 'picked' ? OFP.picked() : undefined}
          at={solo.at} text={solo.note}
        />
      ) : summary ? (
        /* Сводку обрезали до трёх строк — нажатие на неё открывает профиль целиком (просьба тестировщиков 09.10). */
        <Pressable accessibilityRole="button" onPress={onOpen}
                   style={({ pressed }) => [s.sumBox, pressed && { opacity: 0.85 }]}>
          <Text style={s.sumLabel}>{CANDS.summaryLabel().replace(/[:：]\s*$/, '')}</Text>
          {/* В списке — абзац целиком не нужен: три строки, полностью он на карточке человека. */}
          <Text style={s.sumText} numberOfLines={3}>{summary}</Text>
        </Pressable>
      ) : null}

      {/*
        Доступность — не украшение: человек «в тихих часах» не ответит сейчас, и лучше знать
        заранее. Слово «связаться» разводит два разных факта — его намерение встречаться и то,
        дойдёт ли сообщение прямо сейчас, — которые иначе читаются как противоречие.
        В группе строки нет: на GR.14 её нет, а ответ приходит пушем («You’ll get a push»).
      */}
      {!group && !solo && readiness ? (
        <Text style={s.readiness}>{T('Связаться: ', 'Reach out: ', 'Contacta: ')}{readiness}</Text>
      ) : null}

      {group ? (
        /* GR.14–14e. Отменить вступившего нельзя: выход — его решение, удаление — отдельный флоу (GR.51). */
        !st ? (
          <GlassPill tone="brand" small style={s.btn40} label={GR14.invite(name)} onPress={onInvite} />
        ) : st === 'pending' ? (
          <GlassPill tone="light" small style={s.btn40} label={GR14.cancelInvite()} onPress={onCancel} />
        ) : st === 'joined' ? (
          <GlassPill tone="light" small style={s.btn40} label={GR14.openChat()} onPress={onOpenChat} />
        ) : null
      ) : solo ? (
        /* OF.12a–12e: отозвать — пока ждём; выбрать — когда ответил «да»; чат — у выбранного. */
        solo.st === 'sent' ? (
          <GlassPill tone="light" small style={s.btn40} label={GR14.cancelInvite()} onPress={onCancel} />
        ) : solo.st === 'yes' ? (
          <GlassPill tone="brand" small style={s.btn40} busy={picking} label={OFP.pick(name)} onPress={onPick} />
        ) : solo.st === 'picked' ? (
          <GlassPill tone="light" small style={s.btn40} label={CHAT.openChat()} onPress={onOpenChat} />
        ) : (
          <GlassPill tone="brand" small style={s.btn40} label={GR14.invite(name)} onPress={onInvite} />
        )
      ) : status === 'expired' || status === 'withdrawn' ? (
        /* O.14a: приглашение простояло весь срок и не дождалось ответа — это НЕ отказ, и говорить
           о нём надо иначе. Раньше CandCard разбирала только joined/declined/accepted/pending, и
           на истёкшем молча рисовала обычное «Пригласить»: человек не понимал, ушло ли его
           приглашение вообще. `withdrawn` сюда же — так закрываются соседи после чужого «да». */
        <View style={s.invitedRow}>
          <View style={s.statePill}>
            <Text style={[s.stateText, { color: color.muted }]}>⏳  {CHAT.expired()}</Text>
          </View>
          {/*
            Кадр O.14a даёт здесь «Invite again», а не «Убрать». И это разные вещи: молчание —
            не отказ, человек мог просто не открыть приложение. «Убрать» уносило карточку с
            экрана, и позвать снова становилось нечем — из выдачи человек исчезал совсем.
            Сервер повторное приглашение принимает: истёкшая заявка не мешает завести новую.
          */}
          <GlassPill tone="light" small style={s.btn40Flex} label={CHAT.inviteAgain()} onPress={onInvite} />
        </View>
      ) : status === 'declined' ? (
        <View style={s.invitedRow}>
          <View style={s.statePill}>
            <Text style={[s.stateText, { color: color.muted }]}>⊘  {CHAT.declined()}</Text>
          </View>
          <GlassPill tone="light" small style={s.btn40Flex} label={CHAT.remove()} onPress={onRemove} />
        </View>
      ) : status === 'accepted' ? (
        <View style={s.invitedRow}>
          <GlassPill tone="brand" small style={s.btn40Flex} label={CHAT.openChat()} onPress={onOpenChat} />
          <GlassPill tone="light" small style={s.btn40Flex} label={CANDS.cancel()} onPress={onCancel} />
        </View>
      ) : status === 'pending' ? (
        <View style={s.invitedRow}>
          <View style={s.statePill}>
            <Text style={s.stateText}>{CANDS.invitedShort()}</Text>
          </View>
          <GlassPill tone="light" small style={s.btn40Flex} label={CANDS.cancel()} onPress={onCancel} />
        </View>
      ) : (
        <GlassPill tone="brand" small style={s.btn40} label={GR14.invite(name)} onPress={onInvite} />
      )}

      {badge ? (
        <View pointerEvents="none" style={[s.badge, best ? s.badgeBest : s.badgeMatch]}>
          <Text style={[s.badgeText, { color: best ? '#1FAE5E' : '#5A616E' }]}>{badge}</Text>
        </View>
      ) : null}
    </View>
  );
}

/**
 * Лист O.11a «Изменить условия поиска»: пол, возраст диапазоном и — у офлайн-интента — расстояние.
 * «Начать поиск» перезапускает матчинг с условиями, которые человек ослабил сам.
 *
 * Три вещи, которых тут раньше не хватало и без которых лист не делал того, ради чего открывается:
 *
 *  — «Любой» у возраста. Единственный способ СНЯТЬ рамку, а не подвинуть (см. prefsFromIntent).
 *  — Расстояние. Экран за листом обещает расширение «по расстоянию», а в самом листе этой ручки
 *    не было — только в лестнице, которая удваивает радиус вслепую.
 *  — Прокрутка. Лист прибит к низу и растёт вверх; на невысоком экране заголовок и «✕» уезжали
 *    за верхнюю кромку, и закрыть его можно было только по затемнению.
 *
 * Ползунка «гибко по времени» больше нет: матчинг `timeFlexHours` не читает — ни в гейтах, ни в
 * ранжировании, ни в лестнице §12. Ручка, которая ничего не меняет, хуже отсутствующей.
 */
function PrefsSheet({
  open, prefs, setPrefs, offline, busy, onStart, onClose, bottomInset, maxBody,
}: {
  open: boolean;
  prefs: Prefs;
  setPrefs: React.Dispatch<React.SetStateAction<Prefs>>;
  /** Офлайн-интент — только у него расстояние что-то значит. */
  offline: boolean;
  busy: boolean;
  onStart: () => void;
  onClose: () => void;
  bottomInset: number;
  maxBody: number;
}) {
  return (
    /* OF.11a «Search preferences»: кого и какого возраста — чипами, как в мастере (GR.10). Возраст —
       несколько диапазонов сразу, они склеиваются в одну рамку. «How flexible is the time» с кадра
       нет: сервер не умеет искать «±1 час» (OPEN_TASKS). Расстояния на кадре нет, но это рабочий
       способ расширить поиск — оставлено. */
    <Sheet visible={open} onClose={onClose} title={PREFS.sheetTitle()}>
      <ScrollView
        style={{ maxHeight: maxBody }}
        contentContainerStyle={s.prefsBody}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={s.prefLabel}>{PREFS.who()}</Text>
        <View style={s.prefChips}>
          {(['Female', 'Male', 'Any'] as const).map((k) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              accessibilityState={{ selected: (prefs.sex || 'Any') === k }}
              onPress={() => setPrefs((p) => ({ ...p, sex: k }))}
              style={[s.prefChip, (prefs.sex || 'Any') === k && s.prefChipOn]}
            >
              <Text style={[s.prefChipText, (prefs.sex || 'Any') === k && { color: color.onPrimary }]}>{WIZ.sexChip(k)}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={s.prefLabel}>{PREFS.age()}</Text>
        <View style={s.prefChips}>
          {AGE_PRESETS.map((r, i) => {
            const any = !r[0] && !r[1];
            const on = any ? prefs.anyAge : !prefs.anyAge && r[0] >= prefs.minAge && r[1] <= prefs.maxAge;
            return (
              <Pressable
                key={i}
                accessibilityRole="button"
                accessibilityState={{ selected: on }}
                onPress={() => setPrefs((p) => {
                  if (any) return { ...p, anyAge: true };
                  const lit = AGE_PRESETS.filter((x) => (x[0] || x[1]) && !p.anyAge && x[0] >= p.minAge && x[1] <= p.maxAge);
                  let next = on ? lit.filter((x) => x !== r) : [...lit, r];
                  // Убрали средний — рамка не бывает с дырой: остаётся часть выше него.
                  if (on && next.some((x) => x[0] < r[0]) && next.some((x) => x[0] > r[0])) next = next.filter((x) => x[0] > r[0]);
                  if (!next.length) return { ...p, anyAge: true };
                  return { ...p, anyAge: false, minAge: Math.min(...next.map((x) => x[0])), maxAge: Math.max(...next.map((x) => x[1])) };
                })}
                style={[s.prefChip, on && s.prefChipOn]}
              >
                <Text style={[s.prefChipText, on && { color: color.onPrimary }]}>{agePresetLabel(r)}</Text>
              </Pressable>
            );
          })}
        </View>

        {offline ? (
          <>
            <View style={s.prefHeadRow}>
              <View style={s.prefLabelRow}>
                <IconPin size={16} c={color.fg} />
                <Text style={s.prefLabel}>{PREFS.dist()}</Text>
              </View>
              <Text style={s.prefVal}>{PREFS.distVal(prefs.radiusKm)}</Text>
            </View>
            <Slider
              minimumValue={1}
              maximumValue={100}
              step={1}
              value={prefs.radiusKm}
              onValueChange={(v) => setPrefs((p) => ({ ...p, radiusKm: Math.round(v) }))}
              minimumTrackTintColor={color.primary}
              maximumTrackTintColor={color.neutral100}
              thumbTintColor={color.primary}
              accessibilityLabel={PREFS.dist()}
            />
          </>
        ) : null}
      </ScrollView>

      {/* OF.11a: «Start search» кораллом, «Cancel» тёмной — та же пара, что у остальных листов борда. */}
      <GlassPill tone="brand" style={s.btn48} busy={busy} label={PREFS.start()} onPress={onStart} />
      <GlassPill tone="dark" style={s.btn48} label={PREFS.cancel()} onPress={onClose} />
    </Sheet>
  );
}

/**
 * Окно O.14 / GR.16: последствия названы словами, отправка — только отсюда. В группе — копия GR.16:
 * «Invite Jane to your BBQ?» и что увидит человек (район, а не точное место).
 */
function InviteSheet({
  cand, sending, err, group, short, online, onSend, onClose, bottomInset, hybrid,
}: {
  cand: Cand | null;
  sending: boolean;
  err: string;
  /** Групповой режим: та же механика, копия кадра GR.16 вместо O.14. */
  group?: boolean;
  /** Короткое имя затеи — «your BBQ». */
  short: string;
  /** Онлайн-затея (GRO.16): про ссылку, а не про район. */
  online?: boolean;
  /** Гибрид (HY.14 / GRH.16): человек может прийти или подключиться. */
  hybrid?: boolean;
  onSend: () => void;
  onClose: () => void;
  bottomInset: number;
}) {
  const name = String(cand?.name || '');
  return (
    <Sheet visible={!!cand} onClose={onClose} title={GR14.askTitle(name)}>
      {group
        ? <SheetText lead={GR14.askLead(name, short)}
                     note={online ? GR14.askNoteCall(pronOf(cand)) : hybrid ? GR14.askNoteHybrid(pronOf(cand)) : GR14.askNote(pronOf(cand))} />
        /* OF.14: «да» ещё не чат — организатор выбирает одного из ответивших. */
        : <SheetText lead={OFP.askLead(name, online ? OFP.callWord() : (short || T('затею', 'intent', 'plan')))}
                     note={online ? OFP.askNoteCall(pronOf(cand)) : hybrid ? OFP.askNoteHybrid(pronOf(cand)) : OFP.askNote(pronOf(cand))} />}
      {err ? <Text style={s.note}>{err}</Text> : null}
      <GlassPill tone="brand" style={s.btn48} busy={sending} label={group ? GR14.askSend() : CANDS.send()} onPress={onSend} />
      <GlassPill tone="dark" style={s.btn48} label={group ? GR14.askNot() : CANDS.notYet()} onPress={onClose} />
    </Sheet>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  /** Шапка GR.14 «App Bar» 56: «назад» 44, название затеи слева, «···» 44 справа. */
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56, paddingHorizontal: 16 },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  backIcon: { fontSize: 24, color: color.fg, marginTop: -3 },
  dot: { width: 26, height: 26, borderRadius: 13, backgroundColor: color.primary },
  headTitle: { flex: 1, fontSize: 19, fontWeight: '700', color: color.fg },

  /*
    Отступы кадра даны по ОБРЕЗАННЫМ строкам (у текста в Figma снят интерлиньяж: заголовок 15/20
    числится высотой 10). Поэтому «gap 14» между заголовком и пояснением на экране — это 4.
  */
  scroll: { paddingHorizontal: 16, paddingTop: 12, gap: 12 },
  /** «Best fit for your group» TASA 600 15/20 и пояснение Geist 13/18 — Frame 500 кадра. */
  gHead: { gap: 4 },
  gTitle: { fontSize: 15, lineHeight: 20, color: color.fg } as any,
  gLead: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,
  cards: { gap: 16 },
  btn48: { height: 48 },
  btn40: { height: 40 },
  btn40Flex: { height: 40, flex: 1 },
  lead: { ...type.body, color: color.muted } as any,
  note: { ...type.bodySmall, color: color.primary } as any,

  /** «Candidate Card» GR.14: поля 16/16/16/12, между блоками 12. */
  card: {
    paddingTop: 16, paddingRight: 16, paddingBottom: 16, paddingLeft: 12, gap: 12,
    borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.67)', overflow: 'hidden',
    borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(255,255,255,0.9)',
  },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  av: { width: 64, height: 64, borderRadius: 32 },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  identity: { flex: 1, gap: 8 },
  name: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 22, color: color.fg } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  /** Бейдж 16 высотой в правом верхнем углу: «Best match» #D4F0DF/#1FAE5E, «Match» #E8E8E8/#5A616E. */
  badge: {
    position: 'absolute', top: 16, right: 16, height: 16, paddingHorizontal: 8, paddingBottom: 1,
    borderRadius: 99, justifyContent: 'center',
  },
  badgeBest: { backgroundColor: '#D4F0DF' },
  badgeMatch: { backgroundColor: '#E8E8E8' },
  badgeText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 16 } as any,
  whereRow: { flexDirection: 'row', alignItems: 'center', gap: 4, flexShrink: 1 },
  meta: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,

  /** Лента чипов уходит до правой кромки карточки (поле 16 справа снимается). */
  tagsOuter: { marginRight: -16, marginVertical: -4, flexGrow: 0 },
  tags: { gap: 4, paddingRight: 16 },
  /** Чип — белое со стеклянной кромкой: на кадре он светлее карточки и чуть приподнят тенью. */
  tag: {
    height: 36, paddingHorizontal: 14, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.86)',
    justifyContent: 'center', marginVertical: 4,
    shadowColor: '#5A4A3A', shadowOpacity: 0.06, shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
  },
  tagText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.fg } as any,

  sumBox: {
    backgroundColor: 'rgba(255,255,255,0.56)', borderRadius: 12, padding: 12, gap: 8,
    shadowColor: '#5A4A3A', shadowOpacity: 0.05, shadowRadius: 8, shadowOffset: { width: 0, height: 2 },
  },
  sumLabel: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.primary } as any,
  sumText: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,
  readiness: { ...type.caption, color: color.muted } as any,

  invitedRow: { flexDirection: 'row', gap: space.sm },
  /** Состояние 1:1 рядом с кнопкой: не кнопка, нажимать тут нечего. */
  statePill: {
    flex: 1, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.56)',
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12,
  },
  stateText: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  /* «Ещё» — вторичная кнопка: продолжение списка не должно спорить за внимание с приглашением,
     ради которого экран и открыт. */
  moreBtn: {
    height: 48, borderRadius: rad.full, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  moreText: { ...type.button, color: color.fg } as any,
  ctaText: { ...type.button, color: color.onPrimary } as any,

  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },

  noMatch: { alignItems: 'center', gap: space.md, paddingTop: space.xl },
  noMatchArt: {
    width: 96, height: 96, borderRadius: 48, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  noMatchTitle: { fontSize: 20, fontWeight: '700', color: color.fg, textAlign: 'center' },

  prefsBtn: {
    height: 44, borderRadius: rad.full, borderWidth: 1, borderColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  prefsBtnText: { ...type.labelMedium, color: color.primary, fontWeight: '600' } as any,
  prefLabelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  prefLabel: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  prefChips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  prefChip: {
    height: 38, paddingHorizontal: 16, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  prefChipOn: { backgroundColor: color.primary, borderColor: color.primary },
  prefChipText: { ...type.labelMedium, color: color.fg } as any,
  prefHeadRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  prefVal: { ...type.bodySmall, color: color.primary, fontWeight: '600' } as any,
  prefsBody: { gap: space.md, paddingBottom: space.sm },
  miniChip: {
    height: 30, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, alignItems: 'center', justifyContent: 'center',
  },
  miniChipText: { ...type.caption, color: color.muted, fontWeight: '600' } as any,

  plusPrice: { ...type.caption, color: color.muted, textAlign: 'center' } as any,
  capRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 6 },
  capName: { flex: 1, ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  capBtn: {
    height: 36, paddingHorizontal: 14, borderRadius: rad.full, backgroundColor: color.ink,
    alignItems: 'center', justifyContent: 'center',
  },
  capBtnText: { ...type.labelMedium, color: '#fff', fontWeight: '600' } as any,
  sheetBody: { ...type.bodySmall, color: color.muted } as any,
  sheetSend: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  sheetSendText: { ...type.button, color: color.onPrimary } as any,
  sheetNot: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  sheetGhost: { height: 48, alignItems: 'center', justifyContent: 'center' },
  sheetGhostText: { ...type.button, color: color.muted } as any,
  grabber: {
    width: 40, height: 4, borderRadius: 2, backgroundColor: color.neutral100,
    alignSelf: 'center', marginTop: -6,
  },
  sheetNotText: { ...type.button, color: '#fff' } as any,
});
