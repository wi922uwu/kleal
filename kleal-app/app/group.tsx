/**
 * Комната группы — кадры GR.18 (двое, набор идёт) и GR.21 (трое, план доступен), плюс лист
 * состава GR.24.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор — в src/groups.ts.
 *
 * ОДИН экран на оба состояния борда. На GR.18 и GR.21 это буквально один и тот же чат: меняются
 * подпись в шапке и кнопка внизу. Разводить их по маршрутам значило бы, что человек, глядя на свою
 * же группу, попадает то в одно место, то в другое — та же ошибка, от которой в 1:1 спасает один
 * экран плана на всю его жизнь.
 *
 * Чем комната отличается от переписки 1:1 (app/conversation.tsx), кроме числа людей:
 *  — членство И ЕСТЬ доступ: не участник не получает ни истории, ни права писать (NOT_A_MEMBER
 *    от сервера), и это проверка сервера, а не вежливость экрана;
 *  — новичок видит историю ДО своего прихода — комната одна с первого «да», лобби нет;
 *  — системные строки («X joined») — часть той же ленты, а не отдельный канал: иначе следующий
 *    вошедший не увидел бы, как группа собиралась;
 *  — «прочитано» нет вовсе: у сервера нет отметок на группу, и рисовать галочки было бы враньём.
 *
 * Один запрос отдаёт и ленту, и состав (gi_thread возвращает `group` рядом с `messages`), поэтому
 * опрос здесь один, а не два.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image,
  ActivityIndicator, Modal, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { group as gapi, agent, mediaUrl, newIdem, type GroupInfo, type GroupRemovalReason,
  type VoicePayload, type VideoPayload } from '../src/api';
import { ROOM, GROUP, groupSysLine, roomMsg, type GroupSys } from '../src/groups';
import { adoptGroup } from '../src/ginvites';
import { setResults } from '../src/results-store';
import { openResults } from '../src/results-navigation';
import { IconChevronLeft, IconChevronRight, IconPerson, IconSend, IconDots } from '../src/components/icons';
import { interestLabels } from '../src/interest-label';
import { Sheet, SheetItem } from '../src/components/Sheet';
import { MessageFeed } from '../src/components/MessageFeed';
import { CHAT, Msg, REACTIONS } from '../src/chat';
import { usePolling } from '../src/polling';
import * as Clipboard from 'expo-clipboard';
import { color, radius as rad, space, type } from '../src/theme';
import { useVoiceMessage, VoiceMessageControl } from '../src/voice';
import { VideoNoteButton } from '../src/videonote';

type GMsg = { id?: string; frm?: string; text?: string; t?: number; kind?: string; voice?: VoicePayload;
  /** Событие ленты кодом и фактами — по нему строка собирается на языке читающего. */
  sys?: GroupSys };

/** Лента комнаты и лента переписки — один компонент; форма приводится на входе (см. roomMsg). */
type Row = Msg;

export default function GroupRoom() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх композера — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  const params = useLocalSearchParams<{ gid?: string }>();
  const gid = String(params.gid || '').trim();
  const me = String(st.profile.name || '');

  const [g, setG] = useState<GroupInfo | null>(null);
  const [msgs, setMsgs] = useState<Row[]>([]);
  const [picked, setPicked] = useState<Row | null>(null);
  const [replyTo, setReplyTo] = useState<Row | null>(null);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [fatal, setFatal] = useState('');
  const [info, setInfo] = useState(false);
  const [leaveAsk, setLeaveAsk] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [endAsk, setEndAsk] = useState(false);
  const [ending, setEnding] = useState(false);
  /** GR.51: member, selected closed-list reason, and the one in-flight destructive request. */
  const [removeWho, setRemoveWho] = useState('');
  const [removeReason, setRemoveReason] = useState<GroupRemovalReason | ''>('');
  const [removing, setRemoving] = useState(false);
  /** GR.19/GR.20: спрашиваю я или спрашивают меня — два листа поверх одного экрана. */
  const [ask1to1, setAsk1to1] = useState(false);
  const leftForOneOnOne = useRef(false);
  const [busy1to1, setBusy1to1] = useState(false);
  const [adopting, setAdopting] = useState(false);
  const readOnly = !!g?.read_only;
  /** Время последнего известного сообщения — по нему сервер отдаёт только новые. */
  const since = useRef(0);

  /** Голосовое уходит той же ручкой, что и текст: расшифровка в `text`, файл рядом в `voice`. */
  const deliverVoice = useCallback(async (payload: VoicePayload) => {
    if (!me || !gid) throw new Error('MISSING_GROUP');
    const r: any = await gapi.post(gid, me, payload.transcript, payload);
    if (!r?.ok) throw new Error(r?.error || 'post failed');
    const local: Row = roomMsg(r?.message) || null;
    setMsgs((prev) => [...prev, local || {
      from: me, text: payload.transcript, voice: payload, t: Date.now() / 1000,
    }]);
    setErr('');
  }, [gid, me]);
  const voice = useVoiceMessage(deliverVoice, !me || !gid || !!fatal || readOnly);

  /** Кружок в комнате — тем же путём, что и текст: ключ, состояние, повтор. */
  const canSend = !!me && !!gid && !fatal && !readOnly;
  const sendCircle = (payload: VideoPayload) => {
    if (!canSend) return;
    const local: Row = {
      from: me, text: '', video: payload, t: Date.now() / 1000, cid: newIdem('c'), state: 'sending',
    };
    setMsgs((prev) => [...prev, local]);
    deliver(local);
  };

  const load = useCallback(async () => {
    if (!gid || !me) return;
    try {
      const r: any = await gapi.thread(gid, me, since.current);
      if (r?.error === 'NOT_A_MEMBER') { setFatal(ROOM.notMember()); return; }
      if (r?.error === 'NO_SUCH_GROUP') { setFatal(ROOM.gone()); return; }
      if (r?.group) setG(r.group);
      // Спрашивавшая сторона ждёт здесь, и ответ приходит опросом. Как только группа стала
      // один-на-один — уводим и её: иначе организатор остаётся в комнате, которой уже нет, и
      // «согласился» выглядит как «ничего не ответил».
      //
      // Один раз и только на ПЕРЕХОД, а не на состояние: сторожок нужен потому, что опрос идёт
      // дальше, и без него replace повторялся бы каждые несколько секунд, забивая переписку.
      if (!r?.group?.read_only && r?.group?.state === 'converted_1to1' && !leftForOneOnOne.current) {
        const peer = (r.group.members || [])
          .map((x: any) => String(x?.name || ''))
          .find((x: string) => x && x.toLowerCase() !== me.toLowerCase());
        if (peer) {
          leftForOneOnOne.current = true;
          const m = (r.group.members || []).find(
            (x: any) => String(x?.name || '').toLowerCase() === peer.toLowerCase());
          router.replace({ pathname: '/conversation', params: { who: peer, photo: String(m?.photo || '') } });
          return;
        }
      }
      const list: GMsg[] = r?.messages || [];
      if (list.length) {
        const rows = list.map(roomMsg);
        setMsgs((prev) => {
          // Склейка по КЛЮЧУ ОТПРАВИТЕЛЯ, потом по id — ровно как в переписке. Реакция и правка
          // приходят на СТАРУЮ строку, поэтому пришедшее не добавляется, а заменяет свою.
          const out = [...prev];
          for (const m of rows) {
            const byCid = m.cid ? out.findIndex((x) => x.cid && x.cid === m.cid) : -1;
            const at = byCid >= 0 ? byCid : (m.id ? out.findIndex((x) => x.id && x.id === m.id) : -1);
            if (at >= 0) out[at] = m; else out.push(m);
          }
          return out.sort((a, b) => (a.t || 0) - (b.t || 0));
        });
        // Отсечка по «когда трогали»: иначе изменённая строка приедет ещё раз на каждом опросе.
        since.current = Math.max(since.current, ...list.map((m: any) => Math.max(Number(m.t || 0), Number(m.u || 0))));
      }
      setErr('');
    } catch {
      /* фоновый опрос — молча; ругаться на каждую неудачу незачем */
    } finally {
      setLoading(false);
    }
  }, [gid, me]);

  useEffect(() => { load(); }, [load]);

  // Лёгкий опрос: в группе пишут не мгновенно, а сокет ради нескольких реплик избыточен.
  // Спит, пока экран не виден: раньше тикал и из свёрнутого приложения.
  usePolling(load, 4000, !fatal && !readOnly);

  /** Прижимать ленту к низу — только если человек и так внизу, иначе чужая реплика выдёргивает
   *  читающего старое сообщение обратно вниз каждые четыре секунды. */
  const atBottom = useRef(true);
  useEffect(() => {
    if (!atBottom.current) return;
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [msgs.length]);

  /**
   * Отправка одной реплики — и первая, и повторная. Всё то же, что в переписке: пузырь виден
   * сразу, но честно говорит о себе часиками; ключ переживает повтор, поэтому у остальных не
   * появляется вторая копия.
   */
  const deliver = useCallback(async (m: Row) => {
    if (!gid || !me) return;
    setMsgs((prev) => prev.map((x) => (x.cid === m.cid ? { ...x, state: 'sending' } : x)));
    try {
      const r: any = await gapi.post(gid, me, String(m.text || ''), m.voice, m.cid, m.rt?.id, m.video);
      if (!r?.ok) throw new Error(String(r?.error || 'post failed'));
      setMsgs((prev) => prev.map((x) => (x.cid === m.cid ? { ...x, state: undefined } : x)));
      setErr('');
    } catch {
      setMsgs((prev) => prev.map((x) => (x.cid === m.cid ? { ...x, state: 'failed' } : x)));
      setErr(ROOM.offline());
    }
  }, [gid, me]);

  const send = () => {
    const text = draft.trim();
    if (!text || !me || !gid || readOnly) return;
    setDraft('');
    atBottom.current = true;
    const local: Row = {
      from: me, text, t: Date.now() / 1000, cid: newIdem('g'), state: 'sending',
      rt: replyTo ? { id: replyTo.id, from: replyTo.from, text: replyTo.text } : undefined,
    };
    setReplyTo(null);
    setMsgs((prev) => [...prev, local]);
    deliver(local);
  };

  /** Реакция ставится сразу и откатывается, если не прошла: ждать ответа ради своего же нажатия
   *  незачем, а объяснять неудачу нечем — человек нажмёт ещё раз. */
  const react = useCallback(async (m: Row, emoji: string) => {
    if (!m.id || !gid || readOnly) return;
    const mine = String(me).trim().toLowerCase();
    const flip = (r?: Record<string, string[]>) => {
      const next = { ...(r || {}) };
      const has = (next[emoji] || []).includes(mine);
      const list = has ? (next[emoji] || []).filter((n) => n !== mine) : [...(next[emoji] || []), mine];
      if (list.length) next[emoji] = list; else delete next[emoji];
      return next;
    };
    setMsgs((prev) => prev.map((x) => (x.id === m.id ? { ...x, r: flip(x.r) } : x)));
    try {
      const r: any = await gapi.react(gid, me, m.id, emoji);
      if (!r?.ok) throw new Error();
      setMsgs((prev) => prev.map((x) => (x.id === m.id ? { ...x, r: r.r } : x)));
    } catch {
      setMsgs((prev) => prev.map((x) => (x.id === m.id ? { ...x, r: flip(x.r) } : x)));
    }
  }, [gid, me, readOnly]);

  const removeMsg = useCallback(async (m: Row) => {
    if (!m.id || !gid || readOnly) return;
    setPicked(null);
    setMsgs((prev) => prev.map((x) => (x.id === m.id ? { ...x, text: '', deleted: true, r: undefined } : x)));
    try {
      await gapi.deleteMessage(gid, me, m.id);
    } catch {
      setErr(ROOM.offline());
    }
  }, [gid, me, readOnly]);

  /** GR.51: no free text reaches the server; the chosen code is the complete decision record. */
  const removeMember = async () => {
    if (!gid || !removeWho || !removeReason || removing) return;
    setRemoving(true);
    try {
      const r: any = await gapi.remove(gid, me, removeWho, removeReason, newIdem('grm'));
      if (!r?.ok) { setErr(ROOM.removeFailed()); return; }
      setRemoveWho('');
      setRemoveReason('');
      if (r?.group) setG(r.group);
      await load();
    } catch {
      setErr(ROOM.removeFailed());
    } finally {
      setRemoving(false);
    }
  };

  /**
   * «Позвать ещё людей» — новый поиск по интенту ЭТОЙ группы, и приглашения из него уходят в неё
   * же, а не в новую. Отсюда adoptGroup: без привязки первое приглашение с выдачи завело бы
   * вторую группу с тем же названием, и позванные оказались бы не там, где остальные.
   */
  const inviteMore = async () => {
    if (adopting || !gid) return;
    setAdopting(true);
    try {
      const intent = {
        topics: (g as any)?.topics || [],
        mode: (g as any)?.mode || 'offline',
        format: 'group',
        time: (g as any)?.when || '',
        place: (g as any)?.area || '',
        title: g?.title || '',
      };
      const ok = await adoptGroup(me, gid);
      if (!ok) { setErr(ROOM.gone()); return; }
      const prof = {
        name: me, age: st.profile.age, gender: st.profile.gender, city: st.profile.city,
        lat: st.profile.geo?.coarseLat, lon: st.profile.geo?.coarseLon,
        // Языки уходят ОБЪЕКТОМ, как их хранит профиль и как их читает сервер
        // (`prof['languages']['comfortable']`). Здесь стоял плоский список — и ранжирование
        // падало на первой же строке с «'list' object has no attribute 'get'», а экран показывал
        // это как «никого не нашлось». Поиск людей в группу не находил вообще ничего.
        languages: st.profile.languages || {},
      };
      const r: any = await agent.match(intent, prof, { self: me, uid: me, city: st.profile.city });
      setResults({
        intent: r?.intent || intent,
        candidates: r?.candidates || [],
        profile: prof,
        query: '',
      });
      setInfo(false);
      openResults(router);
    } catch {
      setErr(GROUP.sendFailed());
    } finally {
      setAdopting(false);
    }
  };

  /** GR.19 — организатор просит. Решает не он: группа принадлежит обоим. */
  const askSwitch = async () => {
    if (busy1to1 || !gid) return;
    setBusy1to1(true);
    try {
      const r: any = await gapi.convertAsk(gid, me, newIdem('gcv'));
      if (!r?.ok) { setErr(ROOM.switchFailed()); return; }
      setAsk1to1(false);
      load();
    } finally {
      setBusy1to1(false);
    }
  };

  /** GR.20 — отвечает тот, кого спросили. Отказ не закрывает вопрос: спросить можно снова. */
  const answerSwitch = async (agree: boolean) => {
    if (busy1to1 || !gid) return;
    setBusy1to1(true);
    try {
      const r: any = await gapi.convertRespond(gid, me, agree, newIdem('gcr'));
      if (!r?.ok) { setErr(ROOM.switchFailed()); return; }
      // Согласился — значит один-на-один уже существует, и оставаться в комнате мёртвой группы
      // незачем. Раньше здесь был только load(): состояние менялось, а экран оставался прежним,
      // и человек видел ровно то же, что до нажатия («ничего не произошло»).
      if (agree && r?.with) { toOneOnOne(String(r.with)); return; }
      load();
    } finally {
      setBusy1to1(false);
    }
  };

  /**
   * Уйти в личную переписку — replace, а не push: группы больше нет, и возвращаться в её комнату
   * кнопкой «назад» человеку некуда. Фото берётся из состава: без него переписка открылась бы
   * с пустым кружком вместо лица того, с кем только что говорили.
   */
  const toOneOnOne = (who: string) => {
    const m = ((g as any)?.members || []).find(
      (x: any) => String(x?.name || '').toLowerCase() === who.toLowerCase());
    router.replace({ pathname: '/conversation', params: { who, photo: String(m?.photo || '') } });
  };

  /** Второй в группе — тот, кого спрашивают. Их двое, иначе кнопки перехода не бывает. */
  const otherName = ((g as any)?.members || [])
    .map((m: any) => String(m?.name || ''))
    .find((n: string) => n && n.toLowerCase() !== me.toLowerCase()) || '';
  /** Спросили МЕНЯ — лист GR.20 открывается сам: это вопрос, а не уведомление. */
  const askedMe = !readOnly
    && String((g as any)?.pending_1to1?.to || '').toLowerCase() === me.toLowerCase();

  const leave = async () => {
    if (leaving || !gid) return;
    setLeaving(true);
    try {
      // Ответ ПРОВЕРЯЕТСЯ. Раньше экран уходил назад в любом случае — и неудачный выход выглядел
      // ровно как удачный: человек «вышел», возвращался в список и находил группу на месте.
      const r: any = await gapi.leave(gid, me, newIdem('gl'));
      if (!r?.ok) { setErr(ROOM.leaveFailed()); return; }
      // Вышел — комнаты больше нет: возвращаемся туда, откуда пришли, а не остаёмся смотреть
      // на чат, который сервер уже перестал отдавать.
      if (router.canGoBack()) router.back(); else router.replace('/home');
    } finally {
      setLeaving(false);
    }
  };

  const endGroup = async () => {
    if (ending || !gid) return;
    setEnding(true);
    try {
      const r: any = await gapi.close(gid, me, newIdem('gclose'));
      if (!r?.ok) { setErr(ROOM.endFailed()); return; }
      if (r?.group) setG(r.group);
      setEndAsk(false);
      setInfo(false);
      await load();
    } catch {
      setErr(ROOM.endFailed());
    } finally {
      setEnding(false);
    }
  };

  const members = (g?.members || []) as { name?: string; photo?: string }[];
  const others = members.map((m) => String(m.name || '')).filter((n) => n && n !== me);
  const n = Number(g?.joined_count || members.length || 0);
  const min = Number(g?.min_total || 3);
  const groupPlan = (g as any)?.plan || null;
  const hybridPlan = String(groupPlan?.mode || g?.mode || '') === 'hybrid' ? groupPlan : null;
  const sideCounts = hybridPlan?.side_counts || {};
  const headCount = hybridPlan
    ? ROOM.hybridHead(n, Number(sideCounts.in_person || 0), Number(sideCounts.call || 0))
    : ROOM.headCount(n, min);
  const canPlan = !readOnly && !!g?.planning_allowed;
  // За стрелкой должно что-то БЫТЬ: либо план уже есть, либо состав дорос и его можно создать.
  const planReachable = !readOnly && (canPlan || !!(g as any)?.plan);

  if (fatal) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} style={s.back}
                     onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
            <IconChevronLeft />
          </Pressable>
          <Text style={s.headTitle}>{ROOM.gone()}</Text>
        </View>
        <Text style={s.fatal}>{fatal}</Text>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/*
          Верхняя карточка затеи — на кадре GR.18 их ДВЕ шапки, и эта была пропущена целиком.
          Её стрелка вправо ведёт к плану: из чата туда попадали только нижней кнопкой, а она
          видна лишь при полном составе — то есть с GR.18, где людей двое, к плану не было хода
          вовсе, хотя стрелка на кадре есть.

          Живой она делается ТОЛЬКО когда за ней что-то есть: план уже создан или состав дорос до
          планирования. Иначе стрелка обещала бы переход, за которым пусто, — а это хуже, чем её
          отсутствие: человек жмёт и решает, что приложение сломано.
        */}
        {planReachable ? (
          <Pressable accessibilityRole="button" style={s.intentBar}
                     accessibilityLabel={(g as any)?.plan ? ROOM.openPlan() : ROOM.createPlan()}
                     onPress={() => router.navigate({ pathname: '/gplan', params: { gid } })}>
            <View style={{ flex: 1 }}>
              <Text style={s.intentTitle} numberOfLines={1}>{g?.title || ''}</Text>
              <Text style={[s.intentSub, canPlan && { color: color.successText }]} numberOfLines={1}>
                {headCount}
              </Text>
            </View>
            <IconChevronRight size={20} c={color.muted} />
          </Pressable>
        ) : null}

        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} style={s.back}
                     onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
            <IconChevronLeft />
          </Pressable>
          {/* Заголовок — не подпись, а вход: за названием стоит затея, ради которой всё
              собралось, и посмотреть её больше негде. До этого нажатие не делало ничего, а
              единственным входом в сведения были три точки справа — их ещё надо заметить. */}
          <Pressable style={{ flex: 1 }} accessibilityRole="button"
                     accessibilityLabel={ROOM.aboutTitle()} onPress={() => setInfo(true)}>
            <Text style={s.headTitle} numberOfLines={1}>{g?.title || ''}</Text>
            {/* GR.21: при полном составе подзаголовок сам зовёт делать план. */}
            <Text style={[s.headSub, canPlan && { color: color.successText }]} numberOfLines={1}>
              {headCount}
            </Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={ROOM.infoTitle()} style={s.back}
                     onPress={() => setInfo(true)}>
            <IconDots />
          </Pressable>
        </View>

        {/* Состав строкой — GR.18: имена, потом счётчик. */}
        <View style={s.whoRow}>
          <Text style={s.who} numberOfLines={1}>{ROOM.who(others)}</Text>
          <Text style={s.need}>{ROOM.need(n, min)}</Text>
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
          {loading && !msgs.length ? <ActivityIndicator style={{ marginTop: 24 }} color={color.primary} /> : null}
          {readOnly ? (
            <View style={s.removedNotice} accessibilityRole="alert">
              <Text style={s.removedNoticeText}>
                {g?.read_only_reason === 'group_closed'
                  ? ROOM.closedNotice(String(g?.closure_notice?.owner || g?.owner || ''),
                                      String(g?.closure_notice?.title || g?.title || T('эта группа', 'this group', 'este grupo')))
                  : ROOM.removedNotice(String(g?.removal_notice?.title || g?.title || T('эта группа', 'this group', 'este grupo')))}
              </Text>
              <Text style={s.removedNoticeSub}>{ROOM.readOnlyHistory()}</Text>
            </View>
          ) : null}
          <MessageFeed
            msgs={msgs}
            me={me}
            ru={getLang() === 'ru'}
            showAuthor
            sysText={(m) => groupSysLine(String(m.text || ''), (m as any).sys)}
            onReply={readOnly ? () => {} : setReplyTo}
            onReact={react}
            onPick={readOnly ? () => {} : setPicked}
            onRetry={readOnly ? () => {} : deliver}
          />
          {err ? <Text style={s.err}>{err}</Text> : null}
        </ScrollView>

        {/* Действия над сообщением — тот же лист, что в переписке, и та же строка реакций. */}
        {/*
          GR.19 — организатор спрашивает. GR.20 — тот, кого спросили, отвечает. Два листа поверх
          ОДНОГО экрана: это один разговор, и разводить его по маршрутам значило бы, что человек,
          обсуждая свою же группу, каждый раз оказывается где-то ещё.
        */}
        <Sheet visible={ask1to1} onClose={() => setAsk1to1(false)}>
          <Text style={s.sheetTitle}>{ROOM.askTitle(otherName)}</Text>
          <Text style={s.sheetNote}>{ROOM.askNote(otherName)}</Text>
          <Pressable accessibilityRole="button" style={[s.cta, busy1to1 && { opacity: 0.6 }]}
                     disabled={busy1to1} onPress={askSwitch}>
            <Text style={s.ctaText}>{ROOM.askSend(otherName)}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setAsk1to1(false)}>
            <Text style={s.ctaText}>{ROOM.keepGroup()}</Text>
          </Pressable>
        </Sheet>

        <Sheet visible={askedMe} onClose={() => answerSwitch(false)}>
          <Text style={s.sheetTitle}>{ROOM.answerTitle(String((g as any)?.pending_1to1?.by || ''))}</Text>
          <Text style={s.sheetNote}>{ROOM.answerNote()}</Text>
          <Pressable accessibilityRole="button" style={[s.cta, busy1to1 && { opacity: 0.6 }]}
                     disabled={busy1to1} onPress={() => answerSwitch(true)}>
            <Text style={s.ctaText}>{ROOM.agree()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.ctaDark}
                     disabled={busy1to1} onPress={() => answerSwitch(false)}>
            <Text style={s.ctaText}>{ROOM.keepGroup()}</Text>
          </Pressable>
        </Sheet>

        <Sheet visible={!!picked && !readOnly} onClose={() => setPicked(null)}>
          <View style={s.reactRow}>
            {REACTIONS.map((e) => (
              <Pressable
                key={e}
                accessibilityRole="button"
                accessibilityLabel={e}
                style={s.reactPick}
                onPress={() => { if (picked) react(picked, e); setPicked(null); }}
              >
                <Text style={s.reactPickText}>{e}</Text>
              </Pressable>
            ))}
          </View>
          {picked?.text ? (
            <SheetItem
              label={CHAT.copy()}
              onPress={async () => {
                await Clipboard.setStringAsync(String(picked?.text || ''));
                setPicked(null);
              }}
            />
          ) : null}
          <SheetItem label={CHAT.reply()} onPress={() => { setReplyTo(picked); setPicked(null); }} />
          {picked && String(picked.from || '').trim().toLowerCase() === me.toLowerCase() ? (
            <SheetItem label={CHAT.deleteMsg()} note={CHAT.deleteNote()} danger
                       onPress={() => picked && removeMsg(picked)} />
          ) : null}
        </Sheet>

        {/* На что отвечаем — видно ДО отправки, иначе цитата становится сюрпризом. */}
        {!readOnly && replyTo ? (
          <View style={s.replyBar}>
            <View style={s.replyStripe} />
            <View style={{ flex: 1 }}>
              <Text style={s.replyWho} numberOfLines={1}>{CHAT.replyTo(String(replyTo.from || ''))}</Text>
              <Text style={s.replyText} numberOfLines={1}>{replyTo.text || CHAT.deleted()}</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Убрать', 'Remove', 'Eliminar')} onPress={() => setReplyTo(null)} hitSlop={10}>
              <Text style={s.replyX}>✕</Text>
            </Pressable>
          </View>
        ) : null}

        {readOnly ? (
          <View style={[s.readOnlyDock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
            <Text style={s.readOnlyDockText}>{ROOM.readOnlyHistory()}</Text>
          </View>
        ) : (
        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          <View style={s.field}>
            {/*
              Во время записи поля нет — полоса записи занимает его место. Именно `null`, а не
              перестроенная разметка: соседняя кнопка обязана остаться на СВОЁМ месте в дереве,
              иначе React пересоберёт её ровно в миг старта записи и жест удержания оборвётся.
            */}
            {voice.phase === 'idle' ? (
              <TextInput
                style={s.input}
                value={draft}
                onChangeText={setDraft}
                placeholder={ROOM.composer()}
                placeholderTextColor={color.neutral400}
                onSubmitEditing={send}
                returnKeyType="send"
              />
            ) : null}
            {voice.phase === 'idle' && draft.trim() ? (
              <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send', 'Enviar')} onPress={send}>
                <IconSend />
              </Pressable>
            ) : (
              <>
                {/* Кружок отдельной кнопкой, а не переключателем на микрофоне: у микрофона свой
                    жест удержания, и делить его на два смысла значит ломать оба. */}
                <VideoNoteButton onSend={sendCircle} disabled={!canSend} hidden={voice.phase !== 'idle'} />
                <VoiceMessageControl voice={voice} />
              </>
            )}
          </View>

          {/*
            Нижнее действие — ровно то, что на кадре для этого состава:
              трое и больше (GR.21) — «Создать план»;
              их двое (GR.18)       — «Перейти в один на один», и теперь она РАБОТАЕТ.
            Показывать её или нет, решает сервер флагом `can_convert` (их двое, плана нет, группа
            жива), а не экран: разойдись условия — кнопка обещала бы то, на что придёт отказ.
          */}
          {canPlan ? (
            /* GR.21 → GR.25: полный состав ведёт на экран плана. Подпись под кнопкой меняется,
               когда план уже есть: «Создать» тогда врало бы — второго плана у группы не бывает
               (сервер ответит PLAN_EXISTS), и вести туда надо к существующему. */
            <Pressable accessibilityRole="button" style={s.cta}
                       onPress={() => router.navigate({ pathname: '/gplan', params: { gid } })}>
              <Text style={s.ctaText}>
                {(g as any)?.plan ? ROOM.openPlan() : ROOM.createPlan()}
              </Text>
            </Pressable>
          ) : (g as any)?.can_convert ? (
            <View style={s.ctaOffWrap}>
              <Pressable accessibilityRole="button" style={s.cta} onPress={() => setAsk1to1(true)}>
                <Text style={s.ctaText}>{ROOM.switchTo1to1()}</Text>
              </Pressable>
              <Text style={s.ctaNote}>{ROOM.switchWhy()}</Text>
            </View>
          ) : null}
        </View>
        )}

        {/* GR.24 — состав. Лист, а не отдельный маршрут: это справка о той же комнате. */}
        <Sheet visible={info} onClose={() => setInfo(false)} title={ROOM.infoTitle()}>
          {/* СНАЧАЛА про затею, потом про людей. Лист открывался сразу составом, и человек,
              зашедший в группу по приглашению, нигде не мог прочесть, ради чего она вообще:
              название в шапке — это одна строка, а тема, формат и размер жили только на
              экране создания, куда приглашённый не попадает никогда. */}
          <Text style={s.aboutHead}>{ROOM.aboutTitle()}</Text>
          <View style={s.aboutBox}>
            <AboutRow label={ROOM.aboutTopics()}
                      value={interestLabels(g?.topics || []).join(' · ') || ROOM.aboutUnset()} />
            <AboutRow label={ROOM.aboutWhen()} value={String(g?.when || '') || ROOM.aboutUnset()} />
            <AboutRow label={ROOM.aboutWhere()}
                      value={[String(g?.area || ''), ROOM.aboutMode(String(g?.mode || 'offline'))]
                        .filter(Boolean).join(' · ')} />
            <AboutRow label={ROOM.aboutSize(Number(g?.min_total || 3), Number(g?.max_total || 5))}
                      value={ROOM.aboutOwner(String(g?.owner || ''))} />
          </View>

          <Text style={s.aboutHead}>{ROOM.infoTitle()}</Text>
          <Text style={s.sheetBody}>
            {ROOM.infoNote(n, Number(g?.max_total || 5), (g?.invites || []).length)}
          </Text>

          {members.map((m, i) => {
            const nm = String(m.name || '');
            const owner = nm.trim().toLowerCase() === String(g?.owner || '').trim().toLowerCase();
            const memberSide = hybridPlan?.sides?.[nm.trim().toLowerCase()]?.side;
            return (
              <View key={nm + i} style={s.memberRow}>
                {/* Заглушка снизу, фото сверху — см. тот же приём в app/gplan.tsx: пока фото
                    едет (а через туннель это тридцать секунд), на месте человека должен быть
                    кружок, а не дыра. */}
                <View style={[s.memberAv, s.memberAvEmpty]}>
                  <IconPerson size={18} />
                  {m.photo ? (
                    <Image source={{ uri: mediaUrl(String(m.photo)) }}
                           style={[s.memberAv, StyleSheet.absoluteFill]} />
                  ) : null}
                </View>
                <Text style={s.memberName} numberOfLines={1}>
                  {nm === me ? T('Ты', 'You', 'Tú') : nm}
                </Text>
                <Text style={s.memberRole}>
                  {owner ? ROOM.roleOrganiser() : ROOM.roleMember()}
                  {memberSide ? ` · ${ROOM.sideLabel(memberSide)}` : ''}
                </Text>
                {g?.can_remove && !owner ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`${ROOM.removeMember()} ${nm}`}
                    hitSlop={8}
                    onPress={() => {
                      setInfo(false);
                      setRemoveReason('');
                      setTimeout(() => setRemoveWho(nm), 250);
                    }}
                  >
                    <Text style={s.memberRemove}>{ROOM.removeMember()}</Text>
                  </Pressable>
                ) : null}
              </View>
            );
          })}

          {/* «Позвать ещё» — только организатору и только пока есть места: у остальных этой
              кнопки на кадре нет, и приглашать они не могут (сервер ответит NOT_ORGANIZER). */}
          {g?.i_am_owner && !g?.full ? (
            <Pressable accessibilityRole="button" style={[s.sheetSend, adopting && { opacity: 0.6 }]}
                       accessibilityState={{ busy: adopting }}
                       onPress={adopting ? undefined : inviteMore}>
              {adopting ? <ActivityIndicator color={color.onPrimary} />
                        : <Text style={s.sheetSendText}>{ROOM.inviteMore()}</Text>}
            </Pressable>
          ) : null}

          {!readOnly ? (
            <Pressable accessibilityRole="button" style={s.sheetNot}
                       onPress={() => {
                         setInfo(false);
                         setTimeout(() => router.navigate({
                           pathname: '/group-report',
                           params: { gid, title: String(g?.title || '') },
                         }), 250);
                       }}>
              <Text style={s.sheetReportText}>{T('Сообщить о проблеме', 'Report a problem', 'Reportar un problema')}</Text>
            </Pressable>
          ) : null}

          {g?.can_end ? (
            <Pressable accessibilityRole="button" style={s.sheetNot}
                       onPress={() => { setInfo(false); setTimeout(() => setEndAsk(true), 250); }}>
              <Text style={s.sheetNotText}>{ROOM.endGroup()}</Text>
            </Pressable>
          ) : null}

          {/*
            Выход доступен ВСЕМ, включая организатора, — и это расхождение с бордом, сделанное
            осознанно. GR.24 пишет: «participants can leave, and you can't: as organiser you
            either cancel the plan or the group votes you out». Но выход, который борд оставляет
            организатору, — это перевыборы GR.42–44, и их собственная спека помечена «не решено,
            поэтому не реализовано». Убрать кнопку сейчас значило бы запереть человека в группе
            без единого способа выйти. Сервер это уже решил разумнее: организатор выходит, роль
            переходит к тому, кто в группе дольше всех. Когда перевыборы появятся — вернуть по борду.

            Удаление участника организатором — отдельный флоу с причиной (GR.51), не эта кнопка.
          */}
          {!readOnly ? <Pressable accessibilityRole="button" style={s.sheetNot}
                     onPress={() => { setInfo(false); setTimeout(() => setLeaveAsk(true), 250); }}>
            <Text style={s.sheetNotText}>{ROOM.leave()}</Text>
          </Pressable> : null}
        </Sheet>

        {/* S10 / GR.53: ending is only offered before a group plan exists. */}
        <Sheet visible={endAsk} onClose={() => setEndAsk(false)}>
          <Text style={s.sheetTitle}>{ROOM.endTitle(String(g?.title || ''))}</Text>
          <Text style={s.sheetBody}>{ROOM.endBody(others.join(' and '))}</Text>
          <Pressable accessibilityRole="button" style={s.sheetSend}
                     disabled={ending} accessibilityState={{ busy: ending }}
                     onPress={ending ? undefined : () => setEndAsk(false)}>
            <Text style={s.sheetSendText}>{ROOM.keepGoing()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.ctaDark}
                     disabled={ending} accessibilityState={{ busy: ending }}
                     onPress={ending ? undefined : endGroup}>
            {ending ? <ActivityIndicator color={color.onPrimary} />
                    : <Text style={s.ctaText}>{ROOM.endConfirm()}</Text>}
          </Pressable>
        </Sheet>

        {/* GR.51 — exact closed list from the board. No text field by design. */}
        <Sheet visible={!!removeWho} onClose={() => { setRemoveWho(''); setRemoveReason(''); }}>
          <Text style={s.sheetTitle}>{ROOM.removeTitle(removeWho)}</Text>
          <View style={s.reasonList}>
            {ROOM.removalReasons().map((r) => {
              const selected = removeReason === r.code;
              return (
                <Pressable
                  key={r.code}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  style={s.reasonRow}
                  onPress={() => setRemoveReason(r.code)}
                >
                  <View style={[s.radio, selected && s.radioOn]}>
                    {selected ? <View style={s.radioDot} /> : null}
                  </View>
                  <Text style={s.reasonText}>{r.label}</Text>
                </Pressable>
              );
            })}
          </View>
          <Pressable
            accessibilityRole="button"
            disabled={!removeReason || removing}
            accessibilityState={{ disabled: !removeReason, busy: removing }}
            style={[s.sheetSend, (!removeReason || removing) && { opacity: 0.45 }]}
            onPress={removeMember}
          >
            {removing ? <ActivityIndicator color={color.onPrimary} />
                      : <Text style={s.sheetSendText}>{ROOM.removeConfirm(removeWho)}</Text>}
          </Pressable>
          <Pressable accessibilityRole="button" style={s.sheetNot}
                     onPress={() => { setRemoveWho(''); setRemoveReason(''); }}>
            <Text style={s.sheetNotText}>{ROOM.cancelBtn()}</Text>
          </Pressable>
        </Sheet>

        <LeaveSheet
          open={leaveAsk}
          busy={leaving}
          onYes={leave}
          onClose={() => setLeaveAsk(false)}
          bottomInset={insets.bottom}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

/** Подтверждение выхода. Отдельным листом, потому что это единственное необратимое действие экрана. */
function LeaveSheet({
  open, busy, onYes, onClose, bottomInset,
}: {
  open: boolean; busy: boolean; onYes: () => void; onClose: () => void; bottomInset: number;
}) {
  return (
    <Sheet visible={open} onClose={onClose} title={ROOM.leaveAsk()}>
      <Text style={s.sheetBody}>{ROOM.leaveBody()}</Text>
      <Pressable accessibilityRole="button" style={s.sheetSend} onPress={busy ? undefined : onYes}
                 accessibilityState={{ busy }}>
        {busy ? <ActivityIndicator color={color.onPrimary} />
              : <Text style={s.sheetSendText}>{ROOM.leaveYes()}</Text>}
      </Pressable>
      <Pressable accessibilityRole="button" style={s.sheetNot} onPress={onClose}>
        <Text style={s.sheetNotText}>{ROOM.cancelBtn()}</Text>
      </Pressable>
    </Sheet>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

/** Строка «подпись — значение» в сведениях о затее. Пустое значение не рисуется вовсе: пустая
 *  строка на экране читается как «здесь ничего нет», а не как «мы не спросили». */
function AboutRow({ label, value }: { label: string; value: string }) {
  if (!String(value || '').trim()) return null;
  return (
    <View style={s.aboutRow}>
      <Text style={s.aboutLabel}>{label}</Text>
      <Text style={s.aboutValue}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  reactRow: { flexDirection: 'row', justifyContent: 'space-between', paddingBottom: space.sm },
  reactPick: {
    width: 46, height: 46, borderRadius: 23, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  reactPickText: { fontSize: 24 } as any,
  replyBar: {
    flexDirection: 'row', alignItems: 'center', gap: space.sm,
    marginHorizontal: 16, marginBottom: 6, paddingVertical: 8, paddingHorizontal: 10,
    borderRadius: rad.md, backgroundColor: color.neutral100,
  },
  replyStripe: { width: 2, alignSelf: 'stretch', borderRadius: 1, backgroundColor: color.primary },
  replyWho: { fontSize: 12, fontWeight: '700', color: color.primary } as any,
  replyText: { fontSize: 13, color: color.muted } as any,
  replyX: { fontSize: 16, color: color.muted },
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  headTitle: { ...type.title, color: color.fg, fontWeight: '700' } as any,
  headSub: { ...type.bodySmall, color: color.muted } as any,

  aboutHead: { ...type.bodySmall, color: color.muted, fontWeight: '700', marginTop: space.sm } as any,
  aboutBox: {
    borderRadius: rad.lg, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, paddingHorizontal: 14, paddingVertical: 4, gap: 2,
  },
  aboutRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 8 },
  aboutLabel: { ...type.bodySmall, color: color.muted, width: 96 } as any,
  aboutValue: { ...type.body, color: color.fg, flex: 1 } as any,

  // Карточка затеи над шапкой комнаты (GR.18). Своих цветов и размеров нет — только токены.
  intentBar: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    marginHorizontal: 16, marginBottom: space.sm,
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: rad.lg, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card,
  },
  intentTitle: { ...type.body, color: color.fg, fontWeight: '700' } as any,
  intentSub: { ...type.bodySmall, color: color.muted } as any,

  whoRow: { paddingHorizontal: 20, paddingBottom: space.sm, gap: 2 },
  who: { ...type.bodySmall, color: color.fg } as any,
  need: { ...type.caption, color: color.muted } as any,

  thread: { paddingHorizontal: 20, paddingTop: space.sm, paddingBottom: space.lg, gap: 4 },
  sys: { ...type.caption, color: color.muted, textAlign: 'center', marginVertical: 6 } as any,
  author: { ...type.caption, color: color.muted, marginLeft: 6, marginTop: space.sm } as any,
  bubText: { ...type.body, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,
  err: { ...type.bodySmall, color: color.primary, textAlign: 'center', marginTop: space.sm } as any,
  fatal: { ...type.body, color: color.muted, paddingHorizontal: 20, paddingTop: space.lg } as any,
  removedNotice: {
    marginHorizontal: 2, marginBottom: space.md, padding: 14,
    borderRadius: rad.lg, backgroundColor: color.card, borderWidth: 1, borderColor: color.border,
  },
  removedNoticeText: { ...type.body, color: color.fg } as any,
  removedNoticeSub: { ...type.caption, color: color.muted, marginTop: 6 } as any,

  dock: { paddingHorizontal: 16, paddingTop: space.sm, gap: space.sm, backgroundColor: color.bg },
  readOnlyDock: { paddingHorizontal: 20, paddingTop: 14, backgroundColor: color.bg },
  readOnlyDockText: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,
  field: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  ctaOffWrap: { gap: 4 },
  ctaOff: { opacity: 0.4 },
  /** Листы GR.19/GR.20: заголовок, объяснение последствий и две кнопки — согласие и отказ. */
  sheetTitle: { ...type.title, color: color.fg, paddingBottom: space.xs } as any,
  sheetNote: { ...type.bodySmall, color: color.muted, paddingBottom: space.md } as any,
  ctaDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  ctaNote: { ...type.caption, color: color.muted, textAlign: 'center' } as any,

  sheetBody: { ...type.bodySmall, color: color.muted } as any,
  sheetSend: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  sheetSendText: { ...type.button, color: color.onPrimary } as any,
  sheetNot: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  sheetNotText: { ...type.button, color: color.fg } as any,
  sheetReportText: { ...type.button, color: color.danger } as any,

  memberRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  memberAv: { width: 36, height: 36, borderRadius: rad.full },
  memberAvEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  memberName: { flex: 1, ...type.body, color: color.fg } as any,
  memberRole: { ...type.caption, color: color.muted } as any,
  memberRemove: { ...type.caption, color: color.primary, fontWeight: '700' } as any,
  reasonList: { gap: 2, paddingBottom: space.sm },
  reasonRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
  radio: {
    width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: color.neutral300,
    alignItems: 'center', justifyContent: 'center',
  },
  radioOn: { borderColor: color.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.primary },
  reasonText: { flex: 1, ...type.body, color: color.fg } as any,
});
