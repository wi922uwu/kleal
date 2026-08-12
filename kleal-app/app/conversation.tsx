/**
 * Переписка с мэтчем — кадры O.18/O.19 и MSG.06–MSG.11, MSG.18–MSG.21.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор — в src/chat.ts.
 *
 * Устройство по кадрам: шапка с названием интента, под ней имя собеседника, подзаголовок из
 * настоящих состояний (план назначен / предложение отправлено / общаетесь с …), закреплённая
 * карточка живого плана, лента, карточка входящего приглашения, подсказка Kleal, композер.
 *
 * Сообщения настоящие: /api/agent/message доставляет, /api/agent/thread отдаёт по `since`.
 * «Прочитано» — одна отметка на пару (/api/agent/thread-read): двойная галочка появляется на
 * моих пузырях не новее момента, когда собеседник в последний раз открывал переписку.
 * Чего у сервера нет — здесь не рисуется: ни «online now», ни «печатает…».
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { CHAT, THREAD, INVITE, UNDO_BAR, Msg, REACTIONS, planWhen, planPinned, sysLine } from '../src/chat';
import { inviteHoursLeft } from '../src/messages';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, markSeen, setMsgPrefs } from '../src/state';
import { mediaUrl, agent, newIdem } from '../src/api';
import { usePolling } from '../src/polling';
import { Sheet, SheetItem } from '../src/components/Sheet';
import * as Clipboard from 'expo-clipboard';
import { MessageFeed } from '../src/components/MessageFeed';
import { useVoiceMessage, VoiceMessageControl } from '../src/voice';
import { useVideoNote, VideoNoteControl, VideoNoteStage } from '../src/videonote';
import {
  IconChevronLeft, IconSpark, IconPerson, IconCalendar, IconSend, IconDots, IconCheckCircle,
} from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

export default function Conversation() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх композера — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  const params = useLocalSearchParams<{ who?: string; title?: string; photo?: string }>();
  const other = String(params.who || '').trim();
  const intentTitle = String(params.title || '').trim();
  const photo = String(params.photo || '');

  const me = String(st.profile.name || '');
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [actions, setActions] = useState(false);
  /**
   * O.19a/O.19b: «Создать план» и «Завершить чат» не срабатывают мгновенно — внизу чата тикает
   * полоса Undo · 4…0, и только по нулю действие случается. Отменить — просто снять pending,
   * никуда ничего не уходит. Рецепт тот же, что у «Не интересно» на O.13b.
   */
  const [pending, setPending] = useState<{ kind: 'plan' | 'end'; n: number } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  /** Время последнего известного сообщения — по нему сервер отдаёт только новые. */
  const since = useRef(0);
  /** MSG.06–MSG.11: живой план с этим человеком, заявка между нами, отметка чтения второй стороны. */
  const [livePlan, setLivePlan] = useState<any>(null);
  const [request, setRequest] = useState<any>(null);
  const [peerRead, setPeerRead] = useState(0);
  const [intentOpen, setIntentOpen] = useState(false);
  /** Реплика, по которой держали палец: под неё открыт лист действий. */
  const [picked, setPicked] = useState<Msg | null>(null);
  /** Кому отвечаем — цитата стоит над композером, пока не отправишь или не снимешь. */
  const [replyTo, setReplyTo] = useState<Msg | null>(null);
  /** Сколько сообщений уже отмечено прочитанными мной — чтобы не стучать thread-read на каждый опрос. */
  const readStamped = useRef(0);

  /**
   * Слить пришедшее с сервера с тем, что уже на экране.
   *
   * Своя реплика показывается сразу, не дожидаясь ответа сервера, — ждать секунду на собственном
   * сообщении значит выглядеть сломанным. Но опрос приносит её же обратно, и без этой склейки она
   * появлялась ДВАЖДЫ. Проверено: одно отправленное сообщение — два пузыря на экране.
   *
   * Склеиваем по отправителю и тексту в окне полминуты: собственных часов у клиента и сервера
   * достаточно разных, чтобы сравнивать одни только метки времени было нельзя.
   *
   * Сначала — по id, и это не оптимизация. У событий плана текст ПУСТОЙ (строка собирается из кода
   * на экране), поэтому склейка по тексту схлопывала «план предложен» и «место назначено», пришедшие
   * в одну минуту, в одну строку: экран терял половину истории встречи.
   */
  const merge = useCallback((incoming: Msg[]) => {
    if (!incoming.length) return;
    since.current = Math.max(since.current, ...incoming.map((m) => m.t || 0));
    setMsgs((prev) => {
      const out = [...prev];
      for (const m of incoming) {
        // По КЛЮЧУ ОТПРАВИТЕЛЯ — он один и тот же у показанной сразу реплики и у серверной.
        // Прежний путь искал совпадение по тексту, и у голосового не работал вовсе: локально
        // текст пустой, а сервер кладёт туда расшифровку — голосовое двоилось в ленте.
        const byCid = m.cid ? out.findIndex((x) => x.cid && x.cid === m.cid) : -1;
        const byId = byCid >= 0 ? byCid : (m.id ? out.findIndex((x) => x.id && x.id === m.id) : -1);
        const dupe = byId >= 0 ? byId : (
          !m.text ? -1 : out.findIndex(
            (x) => !x.id && x.text === m.text
              && String(x.from || '').toLowerCase() === String(m.from || '').toLowerCase()
              && Math.abs((x.t || 0) - (m.t || 0)) < 30
          )
        );
        if (dupe >= 0) out[dupe] = m;      // серверная версия точнее: у неё настоящее время
        else out.push(m);
      }
      return out.sort((a, b) => (a.t || 0) - (b.t || 0));
    });
  }, []);

  const load = useCallback(async () => {
    if (!me || !other) { setLoading(false); return; }
    try {
      const r: any = await agent.thread(me, other, since.current);
      merge((r?.messages || []) as Msg[]);
      if (typeof r?.peer_read_at === 'number') setPeerRead(r.peer_read_at);
      // Ошибку отправки здесь НЕ гасим: опрос и отправка — разные события, и удачный опрос ничего
      // не говорит об уехавшей реплике. Раньше «Сообщение не ушло» стиралось через четыре
      // секунды, экран выглядел здоровым, а пузырь так и оставался недоставленным.
    } catch {
      /* тихо: это фоновая дотяжка, и ругаться на каждый неудавшийся опрос незачем */
    } finally {
      setLoading(false);
    }
  }, [me, other, merge]);

  /** План и заявка между нами — для шапки, закреплённой карточки и карточек приглашения. */
  const loadSide = useCallback(async () => {
    if (!me || !other) return;
    try {
      const [pl, inb, out] = await Promise.all([agent.plans(me), agent.inbox(me), agent.outbox(me)]);
      const norm = (v: any) => String(v || '').trim().toLowerCase();
      const all = [...((pl as any)?.plans || [])];
      setLivePlan(all.find((p: any) =>
        (p.participants || []).some((x: any) => norm(x.name) === norm(other))
        && (p.state === 'proposed' || p.state === 'confirmed')) || null);
      const rows = [
        ...(Array.isArray(inb) ? inb : (inb as any)?.requests || []),
        ...(Array.isArray(out) ? out : (out as any)?.requests || []),
      ].filter((x: any) => norm(x.from) === norm(other) || norm(x.to) === norm(other));
      rows.sort((a: any, b: any) => (b.updated || 0) - (a.updated || 0));
      setRequest(rows[0] || null);
    } catch {
      /* тихо */
    }
  }, [me, other]);

  useEffect(() => { load(); loadSide(); markSeen(other); }, [me, other]);
  // План и заявка меняются редко — свой ритм, но спит так же, как и лента.
  usePolling(loadSide, 15000);

  /** Только настоящие реплики. События плана — не разговор: они не считаются ни в «прочитано»,
   *  ни в счётчике подсказки MSG.08 («вы обменялись N сообщениями»). */
  const talk = useMemo(() => msgs.filter((m) => !m.sys), [msgs]);


  // «Прочитано» отправляется, когда на экране появились новые ЧУЖИЕ сообщения, а не на каждый опрос.
  useEffect(() => {
    const theirs = talk.filter((m) => String(m.from || '').toLowerCase() !== me.toLowerCase()).length;
    if (theirs > readStamped.current) {
      readStamped.current = theirs;
      markSeen(other);
      agent.threadRead(me, other).catch(() => {});
    }
  }, [msgs.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Лёгкий опрос: собеседник отвечает не мгновенно, а держать сокет ради двух реплик избыточно.
  // Спит, пока экран не виден: раньше он тикал каждые четыре секунды и из свёрнутого приложения.
  usePolling(load, 4000);

  /**
   * Прижимать ленту к низу — только если человек и так внизу.
   *
   * Раньше прокрутка срабатывала на ЛЮБОЕ изменение длины, не спрашивая, где он находится: при
   * опросе раз в четыре секунды чужая реплика выбрасывала читающего старое сообщение обратно
   * вниз, и дочитать переписку было физически нельзя.
   */
  const atBottom = useRef(true);
  useEffect(() => {
    if (!atBottom.current) return;
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [msgs.length]);

  /**
   * Отправка одной реплики — и текстовой, и повторной.
   *
   * Пузырь показывается сразу, ещё до ответа сервера, но теперь честно говорит о себе: часики,
   * пока ответа нет, восклицательный знак, если отказали. Раньше серая галочка рисовалась
   * безусловно, не глядя на результат, — неотправленное выглядело ровно как доставленное.
   *
   * `cid` один на реплику и переживает повтор: сервер по нему узнаёт, что это та же самая, и
   * возвращает прежний ответ вместо второй копии у собеседника.
   */
  const deliver = useCallback(async (m: Msg) => {
    setMsgs((prev) => prev.map((x) => (x.cid === m.cid ? { ...x, state: 'sending' } : x)));
    try {
      const r: any = await agent.message(me, other, String(m.text || ''), m.voice, m.cid,
                                         m.rt?.id, m.video);
      if (!r?.ok) throw new Error(String(r?.error || 'SEND_FAILED'));
      setMsgs((prev) => prev.map((x) => (x.cid === m.cid ? { ...x, state: undefined, id: r.id, t: r.t || x.t } : x)));
      setErr('');
    } catch (e) {
      // Причина называется своя: заблокированному «проверь связь» — ложь, он будет
      // переподключаться и писать снова.
      const code = String((e as any)?.body?.error || (e as any)?.message || '');
      setMsgs((prev) => prev.map((x) => (x.cid === m.cid ? { ...x, state: 'failed' } : x)));
      setErr(code === 'BLOCKED' ? CHAT.blocked() : CHAT.offline());
    }
  }, [me, other]);

  /**
   * Реакция ставится СРАЗУ на экране и только потом уходит на сервер: ждать ответа, чтобы увидеть
   * своё же нажатие, — то же самое, что ждать секунду на собственном сообщении. Не прошло —
   * возвращаем как было, молча: тут нечего объяснять, человек нажмёт ещё раз.
   */
  const react = useCallback(async (m: Msg, emoji: string) => {
    if (!m.id) return;
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
      const r: any = await agent.react(me, m.id, emoji);
      if (!r?.ok) throw new Error();
      setMsgs((prev) => prev.map((x) => (x.id === m.id ? { ...x, r: r.r } : x)));
    } catch {
      setMsgs((prev) => prev.map((x) => (x.id === m.id ? { ...x, r: flip(x.r) } : x)));
    }
  }, [me]);

  const removeMsg = useCallback(async (m: Msg) => {
    if (!m.id) return;
    setPicked(null);
    setMsgs((prev) => prev.map((x) => (x.id === m.id ? { ...x, text: '', deleted: true, r: undefined } : x)));
    try {
      await agent.deleteMessage(me, m.id);
    } catch {
      setErr(CHAT.offline());
    }
  }, [me]);

  const send = () => {
    const text = draft.trim();
    if (!text || !me || !other) return;
    setDraft('');
    atBottom.current = true;
    // `since` НЕ двигаем: пусть опрос принесёт серверную версию этой же реплики — merge её склеит
    // по ключу и заодно поправит время на настоящее.
    const local: Msg = {
      from: me, to: other, text, t: Date.now() / 1000, cid: newIdem('m'), state: 'sending',
      // Цитата показывается сразу вместе со своим пузырём: ждать серверную версию, чтобы увидеть,
      // на что ответил, — значит смотреть полсекунды на ответ без вопроса.
      rt: replyTo ? { id: replyTo.id, from: replyTo.from, text: replyTo.text } : undefined,
    };
    setReplyTo(null);
    setMsgs((prev) => [...prev, local]);
    deliver(local);
  };

  /**
   * Голосовое уходит ТЕМ ЖЕ путём, что и текст: /api/agent/message принимает `voice` рядом с
   * `text`. Поэтому и показывается оно сразу, как своя реплика, — опрос принесёт серверную
   * версию и склеит по id.
   */
  /** Кружок уходит тем же путём, что текст и голосовое: тот же ключ, то же состояние, тот же повтор. */
  const note = useVideoNote((payload) => {
    if (!me || !other) return;
    const local: Msg = {
      from: me, to: other, text: '', video: payload,
      t: Date.now() / 1000, cid: newIdem('c'), state: 'sending',
    };
    setMsgs((prev) => [...prev, local]);
    deliver(local);
  }, !me || !other);

  const voice = useVoiceMessage((payload) => {
    if (!me || !other) return;
    // Тем же путём, что и текст: тот же ключ, то же состояние, тот же повтор при сбое. Своего
    // пути у голосового быть не должно — иначе половина работы над отправкой обходит его стороной.
    const local: Msg = {
      from: me, to: other, text: payload.transcript, voice: payload,
      t: Date.now() / 1000, cid: newIdem('v'), state: 'sending',
    };
    setMsgs((prev) => [...prev, local]);
    deliver(local);
  }, !me || !other);

  const startPending = (kind: 'plan' | 'end') => {
    if (pending) return;
    setActions(false);
    setPending({ kind, n: 4 });
  };

  useEffect(() => {
    if (!pending) return;
    timer.current = setTimeout(() => {
      if (pending.n > 1) {
        setPending({ ...pending, n: pending.n - 1 });
        return;
      }
      setPending(null);
      if (pending.kind === 'plan') {
        router.push({ pathname: '/plan', params: planParams() });
      } else {
        // КОНЕЦ РАЗГОВОРА ЗАПИСЫВАЕТСЯ, а не только уводит с экрана.
        //
        // У сервера понятия «закрытый тред» действительно нет, и раньше отсюда следовал вывод:
        // завершение — это просто уход назад. Но тогда «Закончить разговор» ничего не меняло:
        // человек возвращался в «Сообщения» и находил ту же переписку на прежнем месте, во вкладке
        // «Собирается». Кнопка обещала «переписка закроется» и не закрывала ничего.
        //
        // Пометка ЛОКАЛЬНАЯ — и это ровно та механика, что уже есть у «В архив» (MSG.04): отношение
        // человека к списку живёт на устройстве, а не на сервере. Архив, а не «покинул»: разговор
        // остаётся читаемым и находится поиском, он лишь уходит из активных — это и обещано словами
        // «переписка закроется, а место освободится для другого мэтча».
        //
        // Ключ — имя собеседника в том же виде, в каком его кладёт `threadRows` (нижний регистр):
        // `bucketOf` сверяет и по `r.key`, и по `norm(r.who)`, так что этого достаточно и для строки
        // переписки, и для строки интента с тем же человеком.
        const key = other.trim().toLowerCase();
        if (key) {
          setMsgPrefs((m) => {
            const cur = new Set(m.archived || []);
            cur.add(key);
            return { ...m, archived: [...cur] };
          });
        }
        if (router.canGoBack()) router.back(); else router.replace('/home');
      }
    }, 1000);
    return () => clearTimeout(timer.current);
  }, [pending]);

  const undoPending = () => {
    clearTimeout(timer.current);
    setPending(null);
  };

  const ru = getLang() === 'ru';
  const norm = (v: any) => String(v || '').trim().toLowerCase();

  /** Подзаголовок шапки — только из того, что есть на самом деле. Присутствия и «печатает…» нет. */
  const subtitle = useMemo(() => {
    if (livePlan?.state === 'confirmed') return THREAD.planSet(planWhen(livePlan, ru));
    if (livePlan?.state === 'proposed') {
      return norm(livePlan.host) === norm(me) ? THREAD.proposalSent() : THREAD.planFromThem();
    }
    if (msgs.length) {
      const first = new Date((msgs[0].t || 0) * 1000);
      // Разговор начался сегодня — «с субботы» про сегодняшний день читается как «давно уже».
      if (first.toDateString() === new Date().toDateString()) return THREAD.talkingToday();
      // Русскому нужен родительный: «с четверга». Английскому — просто имя дня.
      const day = ru ? THREAD.weekdayGen(first.getDay()) : first.toLocaleDateString('en-US', { weekday: 'long' });
      return THREAD.talkingSince(day);
    }
    if (request?.status === 'accepted') {
      const title = String(request?.intent?.title || (request?.intent?.topics || []).join(', ') || '');
      if (title) return THREAD.matchedOn(title);
    }
    return '';
  }, [livePlan, msgs, request, ru, me]);

  /** В каком состоянии знакомство, когда сказать ещё нечего. См. CHAT.empty. */
  const emptyState: 'they-accepted' | 'i-accepted' | 'sent' | 'invited-me' | 'none' =
    !request ? 'none'
    : request.status === 'accepted' ? (norm(request.to) === norm(other) ? 'they-accepted' : 'i-accepted')
    : request.status === 'pending' ? (norm(request.to) === norm(other) ? 'sent' : 'invited-me')
    : 'none';

  /** MSG.18–MSG.21: входящая заявка от этого человека, если её не скрывали. */
  const inviteIn = request && norm(request.from) === norm(other) ? request : null;
  const inviteHidden = (st.msg?.hiddenInvites || []).includes(String(inviteIn?.id || ''));
  const noNudge = (st.msg?.noNudge || []).includes(norm(other));
  const requestTitle = String(request?.intent?.title || (request?.intent?.topics || []).join(', ') || '');

  const hideInvite = () =>
    setMsgPrefs((m) => ({ ...m, hiddenInvites: [...(m.hiddenInvites || []), String(inviteIn?.id || '')] }));
  const muteNudge = () =>
    setMsgPrefs((m) => ({ ...m, noNudge: [...(m.noNudge || []), norm(other)] }));
  /**
   * Что форма плана обязана знать про интент, по которому вы совпали, — иначе она это выдумывает.
   *
   *   mode    — офлайн/онлайн/гибрид. Без него форма угадывала режим по наличию ссылки: у встречи
   *             вживую спрашивала ссылку на звонок, а звонок без вставленной ссылки уезжал на
   *             сервер как встреча вживую.
   *   address — точное место с OF.09: не спрашивать дважды то, что человек уже назвал.
   *   link    — то же самое для звонка.
   */
  const planParams = () => ({
    who: other,
    title: requestTitle || intentTitle,
    photo,
    mode: String(request?.intent?.mode || ''),
    address: String(request?.intent?.address || ''),
    link: String(request?.intent?.link || ''),
  });

  const toPlan = () => router.push({ pathname: '/plan', params: planParams() });

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/* MSG.06: шапка одним рядом — назад, аватар, имя со статусом, многоточие. Отдельной
            полосы интента больше нет: интент живёт в закреплённом плане и в листе за «•••». */}
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
            <IconChevronLeft />
          </Pressable>
          {photo ? (
            <Image source={{ uri: mediaUrl(String(photo)) }} style={s.ava} />
          ) : (
            <View style={[s.ava, s.avaEmpty]}><IconPerson size={20} /></View>
          )}
          <View style={{ flex: 1 }}>
            <Text style={s.name} numberOfLines={1}>{other}</Text>
            {subtitle ? <Text style={s.sub} numberOfLines={1}>{subtitle}</Text> : null}
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel={CHAT.actionsTitle()} style={s.dots} onPress={() => setActions(true)}>
            <IconDots />
          </Pressable>
        </View>

        {/* MSG.07 — живой план закреплён над лентой; тап открывает его экран. */}
        {livePlan ? (
          <Pressable
            accessibilityRole="button"
            style={s.planCard}
            onPress={() => router.push({ pathname: '/plan', params: { id: livePlan.id, who: other, title: livePlan.title || intentTitle, photo } })}
          >
            <View style={s.planIcon}><IconCalendar size={20} c={color.onPrimary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.planTitle} numberOfLines={1}>{livePlan.title || intentTitle}</Text>
              <Text style={s.planSub} numberOfLines={1}>
                {planWhen(livePlan, ru)}{livePlan.district ? ` · ${livePlan.district}` : ''}
              </Text>
              {/* Состояние встречи — прямо на карточке. Раньше она молчала, и «подтверждено» или
                  «ждёт тебя» узнавалось только после перехода на экран плана. */}
              <Text style={[s.planState, planPinned(livePlan, me).warn && { color: color.primary }]} numberOfLines={1}>
                {planPinned(livePlan, me).label}
              </Text>
            </View>
            {/* Пара участников, как на MSG.07: собеседник и я, внахлёст. */}
            <View style={s.pairWrap}>
              {photo ? (
                <Image source={{ uri: mediaUrl(String(photo)) }} style={s.pairAva} />
              ) : (
                <View style={[s.pairAva, s.avaEmpty]}><IconPerson size={13} /></View>
              )}
              {st.profile.photo ? (
                <Image source={{ uri: mediaUrl(String(st.profile.photo)) }} style={[s.pairAva, s.pairAvaOverlap]} />
              ) : (
                <View style={[s.pairAva, s.pairAvaOverlap, s.avaEmpty]}><IconPerson size={13} /></View>
              )}
            </View>
          </Pressable>
        ) : requestTitle ? (
          /*
            Встречи ещё нет — закреплён ИНТЕНТ, по которому вы совпали. Он и есть то, ради чего
            этот разговор начался, и провалиться в него надо из чата, а не из меню за «•••»:
            «Сообщения» теперь ведут только сюда, и другого пути к карточке интента не остаётся.
          */
          <Pressable accessibilityRole="button" style={s.planCard} onPress={() => setIntentOpen(true)}>
            <View style={[s.planIcon, s.intentIcon]}><IconSpark size={20} c={color.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.planTitle} numberOfLines={1}>{requestTitle}</Text>
              <Text style={s.planSub} numberOfLines={1}>
                {[request?.intent?.when || request?.intent?.time,
                  request?.intent?.mode === 'offline' ? THREAD.offlineInPerson() : THREAD.onlineMode()]
                  .filter(Boolean).join(' · ')}
              </Text>
              <Text style={s.planState} numberOfLines={1}>{THREAD.openIntent()}</Text>
            </View>
            <Text style={s.planChev}>›</Text>
          </Pressable>
        ) : null}

        <ScrollView
          ref={scroller}
          contentContainerStyle={s.thread}
          keyboardShouldPersistTaps="handled"
          scrollEventThrottle={200}
          onScroll={(e) => {
            const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
            atBottom.current = contentOffset.y + layoutMeasurement.height >= contentSize.height - 80;
          }}
        >
          {loading ? <ActivityIndicator color={color.muted} style={{ marginTop: space.lg }} /> : null}

          {/* MSG.18/20/21 — заявка от собеседника живёт в ленте карточкой, а не отдельным миром. */}
          {inviteIn && !inviteHidden && inviteIn.status !== 'accepted' ? (
            <View style={s.invCard}>
              <Text style={s.invTitle}>{INVITE.title(other)}</Text>
              <Text style={s.invState}>
                {inviteIn.status === 'pending' ? THREAD.hoursToAnswer(inviteHoursLeft(inviteIn))
                  : inviteIn.status === 'declined' ? THREAD.youDeclined()
                  : THREAD.inviteExpired()}
              </Text>
              {requestTitle || inviteIn.intent?.when || inviteIn.intent?.time ? (
                <Text style={s.invMeta} numberOfLines={1}>
                  {[requestTitle, inviteIn.intent?.when || inviteIn.intent?.time].filter(Boolean).join(' · ')}
                </Text>
              ) : null}
              {inviteIn.status === 'pending' ? (
                <Pressable
                  accessibilityRole="button"
                  style={s.invBtn}
                  onPress={() => router.push({ pathname: '/invite', params: { id: inviteIn.id } })}
                >
                  <Text style={s.invBtnText}>{THREAD.reviewInvite()}</Text>
                </Pressable>
              ) : (
                <Pressable accessibilityRole="button" style={s.invBtnDark} onPress={hideInvite}>
                  <Text style={s.invBtnDarkText}>{THREAD.dismiss()}</Text>
                </Pressable>
              )}
            </View>
          ) : null}
          {inviteIn && inviteIn.status === 'declined' && !inviteHidden ? (
            <View style={s.noteBox}><Text style={s.noteText}>{THREAD.declinedClear(other)}</Text></View>
          ) : null}
          {inviteIn && inviteIn.status === 'expired' && !inviteHidden ? (
            <View style={s.noteBox}>
              <Text style={s.noteText}>
                {THREAD.expiredNote(Math.max(1, Math.round(((inviteIn.expires_at || 0) - (inviteIn.created || 0)) / 3600)))}
              </Text>
            </View>
          ) : null}
          {request && request.status === 'accepted' && requestTitle ? (
            <Text style={s.sysLine}>{THREAD.joined(requestTitle)}</Text>
          ) : null}

          {/* Кто кого позвал и ответили ли уже — четыре разных факта, четыре разных строки. */}
          {!loading && talk.length === 0 ? (
            <Text style={s.empty}>{CHAT.empty(other, emptyState)}</Text>
          ) : null}

          <MessageFeed
            msgs={msgs}
            me={me}
            ru={ru}
            sysText={(m) => sysLine(m.sys, me, ru)}
            peerRead={peerRead}
            onReply={setReplyTo}
            onReact={react}
            onPick={setPicked}
            onRetry={deliver}
          />

          {/* MSG.09 — предложение ушло; ничего не забронировано до «да». */}
          {livePlan?.state === 'proposed' && norm(livePlan.host) === norm(me) ? (
            <View style={s.sysNote}>
              <View style={{ flex: 1 }}>
                <Text style={s.sysTitle}>{THREAD.sentAsProposal(other)}</Text>
                <Text style={s.sysSub}>{THREAD.nothingBooked(other)}</Text>
              </View>
              <IconCheckCircle size={26} />
            </View>
          ) : null}

          {/* MSG.08 — подсказка Kleal: счёт сообщений настоящий, план по кнопке, «пока нет» помнит. */}
          {!livePlan && talk.length >= 8 && !noNudge ? (
            <View style={s.nudge}>
              <Text style={s.nudgeLabel}>Kleal</Text>
              <Text style={s.nudgeText}>{THREAD.nudge(talk.length, other)}</Text>
              <View style={s.nudgeRow}>
                <Pressable accessibilityRole="button" style={s.chip} onPress={toPlan}>
                  <Text style={s.chipText}>{THREAD.nudgeYes()}</Text>
                </Pressable>
                <Pressable accessibilityRole="button" style={s.chip} onPress={toPlan}>
                  <Text style={s.chipText}>{THREAD.nudgeOther()}</Text>
                </Pressable>
                <Pressable accessibilityRole="button" style={s.chip} onPress={muteNudge}>
                  <Text style={s.chipText}>{THREAD.nudgeNot()}</Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          {err ? <Text style={s.err}>{err}</Text> : null}
        </ScrollView>

        {/* O.19a/O.19b — полоса отсчёта над композером: создание плана красное, конец чата тёмный. */}
        {pending ? (
          <View style={[s.undoBar, pending.kind === 'end' && s.undoBarDark]}>
            <Text style={s.undoText} numberOfLines={1}>
              {pending.kind === 'plan' ? UNDO_BAR.creating(other) : UNDO_BAR.ending()}
            </Text>
            <Pressable accessibilityRole="button" onPress={undoPending} hitSlop={8}>
              <Text style={s.undoAction}>{UNDO_BAR.undo(pending.n)}</Text>
            </Pressable>
          </View>
        ) : null}

        {/* На что отвечаем — видно ДО отправки, иначе цитата становится сюрпризом. */}
        {replyTo ? (
          <View style={s.replyBar}>
            <View style={s.replyStripe} />
            <View style={{ flex: 1 }}>
              <Text style={s.replyWho} numberOfLines={1}>{CHAT.replyTo(String(replyTo.from || ''))}</Text>
              <Text style={s.replyText} numberOfLines={1}>{replyTo.text || CHAT.deleted()}</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Убрать', 'Remove')} onPress={() => setReplyTo(null)} hitSlop={10}>
              <Text style={s.replyX}>✕</Text>
            </Pressable>
          </View>
        ) : null}

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          {/* Искра слева — вход в действия разговора (O.19). На кадре в этом слоте скрепка,
              но вложений в продукте нет — мёртвую кнопку не рисуем. */}
          <Pressable accessibilityRole="button" accessibilityLabel={CHAT.actionsTitle()} style={s.sparkBtn} onPress={() => setActions(true)}>
            <IconSpark size={20} c={color.primary} />
          </Pressable>
          {/*
            Во время записи поля нет: полоса записи занимает его место целиком, как в мессенджерах.
            Именно `null`, а не другая разметка — соседняя кнопка обязана остаться на СВОЁМ месте
            в дереве, иначе React пересоберёт её заново ровно в тот миг, когда запись начинается,
            и жест удержания оборвётся на старте.
          */}
          {voice.phase === 'idle' ? (
            <View style={s.field}>
              <TextInput
                style={s.input}
                value={draft}
                onChangeText={setDraft}
                placeholder={CHAT.placeholderTo(other)}
                placeholderTextColor={color.neutral400}
                onSubmitEditing={send}
                returnKeyType="send"
              />
            </View>
          ) : null}
          {/*
            Одна кнопка на два действия, как в мессенджерах: пусто в поле — микрофон (удержание
            записывает голосовое), есть текст — самолётик. Держать обе рядом значит отдать место
            кнопке, которая в этот момент заведомо не нужна.
          */}
          {voice.phase === 'idle' && draft.trim() ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={T('Отправить', 'Send')}
              style={s.sendBtn}
              onPress={send}
            >
              <IconSend size={18} />
            </Pressable>
          ) : (
            <>
              {/* Кружок отдельной кнопкой, а не переключателем на микрофоне: у микрофона свой
                  жест удержания, и делить его на два смысла значит ломать оба. */}
              {voice.phase === 'idle' ? <VideoNoteControl note={note} /> : null}
              {note.phase === 'idle' ? <VoiceMessageControl voice={voice} /> : null}
            </>
          )}
        </View>

        {/* Лист O.19. */}
        {/*
          Действия над сообщением. Жест уже воспитан этим же приложением: в списке «Сообщений»
          долгое нажатие открывает такой же лист. Реакции стоят строкой сверху — до них два
          касания вместо трёх, а это самое частое действие из четырёх.
        */}
        <Sheet visible={!!picked} onClose={() => setPicked(null)}>
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
          {picked && String(picked.from || '').trim().toLowerCase() === me.trim().toLowerCase() ? (
            <SheetItem
              label={CHAT.deleteMsg()}
              note={CHAT.deleteNote()}
              danger
              onPress={() => picked && removeMsg(picked)}
            />
          ) : null}
        </Sheet>

        <Sheet visible={actions} onClose={() => setActions(false)} title={CHAT.actionsTitle()}>

            <Pressable accessibilityRole="button" style={s.actPri} onPress={() => startPending('plan')}>
              <Text style={s.actPriText}>{CHAT.createPlan()}</Text>
            </Pressable>

            <Pressable accessibilityRole="button" style={s.actDark} onPress={() => startPending('end')}>
              <Text style={s.actDarkText}>{CHAT.endConversation()}</Text>
            </Pressable>

            {/* MSG.10: интент показывается листом фактов, а не уводит в мастер создания. */}
            <Pressable accessibilityRole="button" style={s.actSoft} onPress={() => { setActions(false); setIntentOpen(true); }}>
              <Text style={s.actSoftText}>{CHAT.viewIntent()}</Text>
            </Pressable>

            <Pressable accessibilityRole="button" style={s.actPlain} onPress={() => setActions(false)}>
              <Text style={s.actPlainText}>{CHAT.keepChatting()}</Text>
            </Pressable>
        </Sheet>

        {/* MSG.10 — интент как лист фактов. Только то, что заявка знает на самом деле: где именно
            пройдёт встреча, не обещаем — «после подтверждения обоих», это и есть правило OF.C3. */}
        <Sheet
          visible={intentOpen}
          onClose={() => setIntentOpen(false)}
          title={requestTitle || intentTitle || T('Интент', 'Intent')}
        >
            {([
              [THREAD.intentMode(), request?.intent?.mode === 'offline' ? THREAD.offlineInPerson() : THREAD.onlineMode()],
              [THREAD.intentWhen(), String(request?.intent?.when || request?.intent?.time || '—')],
              [THREAD.intentWhere(), request?.intent?.mode === 'offline' ? THREAD.whereAfterConfirm() : THREAD.whereLink()],
              [THREAD.intentWho(), String(request?.intent?.format || '1:1')],
              [THREAD.intentStatus(),
                request?.status === 'accepted'
                  ? THREAD.matchedAgo(other, Math.floor((Date.now() / 1000 - (request?.updated || 0)) / 86400))
                  : request?.status === 'pending' ? THREAD.statusWaiting()
                  : request?.status === 'declined' ? THREAD.youDeclined()
                  : request?.status === 'expired' ? THREAD.inviteExpired()
                  : '—'],
            ] as [string, string][]).map(([k, v]) => (
              <View key={k} style={s.factRow}>
                <Text style={s.factKey}>{k}</Text>
                <Text style={s.factVal}>{v}</Text>
              </View>
            ))}
        </Sheet>
        {/* Окно записи кружка — у корня экрана: только здесь его границы во весь экран,
            и только здесь нажимаются кнопки «отправить» и «отмена». */}
        <VideoNoteStage note={note} />
      </View>
    </KeyboardAvoidingView>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

// Дизайн-проход по кадрам MSG.06–MSG.11: шапка одним рядом, пузыри 18 с хвостовым скруглением,
// разделители дней, красный круг отправки. Цвета и шрифты — только из токенов темы.

/** Тень карточек — та же константа, что в «Сообщениях»: одна глубина на всё приложение. */
const cardShadow = {
  shadowColor: '#0F172A', shadowOpacity: 0.06, shadowRadius: 12,
  shadowOffset: { width: 0, height: 4 }, elevation: 2,
} as const;

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },

  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: space.sm },
  back: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  dots: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  name: { fontSize: 17, fontWeight: '700', color: color.fg } as any,
  sub: { fontSize: 13, color: color.muted, marginTop: 1 } as any,
  ava: { width: 40, height: 40, borderRadius: 20 },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },

  // MSG.07 — закреплённый план: карточка с тенью, красная плитка-иконка, пара участников справа.
  planCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: 16, marginBottom: space.sm, paddingVertical: 12, paddingHorizontal: 14,
    borderRadius: 18, backgroundColor: color.card, ...cardShadow,
  },
  planIcon: {
    width: 44, height: 44, borderRadius: 14, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  planTitle: { fontSize: 16, fontWeight: '700', color: color.fg } as any,
  planSub: { fontSize: 13, color: color.muted, marginTop: 1 } as any,
  planState: { fontSize: 12, color: color.muted, marginTop: 2, fontWeight: '600' } as any,
  /** Интент — не встреча: плитка светлая, чтобы красный остался за назначенным временем. */
  intentIcon: { backgroundColor: color.infoBg },
  planChev: { fontSize: 22, color: color.neutral400, marginLeft: 2 },
  pairWrap: { flexDirection: 'row', alignItems: 'center' },
  pairAva: { width: 28, height: 28, borderRadius: 14, borderWidth: 2, borderColor: color.card },
  pairAvaOverlap: { marginLeft: -10 },

  // MSG.18–MSG.21 — карточка приглашения в ленте.
  invCard: {
    backgroundColor: color.card, borderRadius: rad.lg, padding: space.md,
    gap: 6, marginTop: space.sm, borderWidth: 1, borderColor: color.border,
  },
  invTitle: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  invState: { ...type.caption, color: color.primary, fontWeight: '600' } as any,
  invMeta: { ...type.caption, color: color.muted } as any,
  invBtn: {
    height: 44, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: 6,
  },
  invBtnText: { ...type.labelMedium, color: color.onPrimary, fontWeight: '700' } as any,
  invBtnDark: {
    height: 44, borderRadius: rad.full, backgroundColor: color.ink,
    alignItems: 'center', justifyContent: 'center', marginTop: 6,
  },
  invBtnDarkText: { ...type.labelMedium, color: '#fff', fontWeight: '700' } as any,
  noteBox: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md, marginTop: space.sm },
  noteText: { ...type.caption, color: color.infoText } as any,
  sysLine: { ...type.caption, color: color.muted, textAlign: 'center', marginTop: space.sm } as any,

  // MSG.09 — записка «отправлено как предложение»: белая карточка с красной галкой-кружком.
  sysNote: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    alignSelf: 'flex-start', backgroundColor: color.card, borderRadius: 18,
    padding: space.md, marginTop: space.md, maxWidth: '90%', ...cardShadow,
  },
  sysTitle: { fontSize: 15, color: color.fg, fontWeight: '700' } as any,
  sysSub: { fontSize: 13, color: color.muted, marginTop: 2 } as any,

  // MSG.08 — подсказка Kleal.
  nudge: {
    backgroundColor: color.neutral100, borderRadius: rad.lg, padding: space.md,
    gap: 8, marginTop: space.md,
  },
  nudgeLabel: { ...type.caption, color: color.primary, fontWeight: '700' } as any,
  nudgeText: { ...type.bodySmall, color: color.fg } as any,
  nudgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    height: 34, paddingHorizontal: 12, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipText: { ...type.caption, color: color.fg, fontWeight: '600' } as any,

  // MSG.10 — лист интента.
  factRow: { flexDirection: 'row', gap: 16, paddingVertical: 8 },
  factKey: { width: 82, ...type.bodySmall, color: color.muted } as any,
  factVal: { flex: 1, ...type.bodySmall, color: color.fg, textAlign: 'right' } as any,

  // События плана: плашка по центру ленты — заметная, но тише реплики.
  eventText: { flexShrink: 1, fontSize: 12.5, lineHeight: 17, color: color.muted, textAlign: 'center' } as any,
  eventTime: { fontSize: 11, color: color.neutral400 } as any,

  thread: { paddingHorizontal: 20, paddingBottom: space.lg, gap: 4 },
  empty: { ...type.bodySmall, color: color.muted, textAlign: 'center', marginTop: space.lg } as any,
  /** MSG.06: «Сегодня» — маленькая серая метка по центру над первой репликой дня. */
  day: { fontSize: 12, color: color.neutral400, textAlign: 'center', marginTop: space.md } as any,

  quoteWho: { fontSize: 12, fontWeight: '700', color: color.primary } as any,
  quoteText: { fontSize: 12, color: color.muted } as any,

  reactionText: { fontSize: 13, color: color.fg } as any,
  link: { color: color.primary, textDecorationLine: 'underline' } as any,
  linkMine: { color: color.onPrimary } as any,
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
  bubText: { fontSize: 15, lineHeight: 21, color: color.fg } as any,
  time: { fontSize: 11, color: color.neutral400, marginTop: 3 } as any,
  /** MSG.11: одна галочка серая, две — красные, прочитано. */
  tick: { fontSize: 11, color: color.neutral400 } as any,
  tickRead: { fontSize: 11, color: color.primary, fontWeight: '700' } as any,
  tickFail: { fontSize: 11, color: color.primary, fontWeight: '600' } as any,
  err: { ...type.bodySmall, color: color.primary, marginTop: space.sm } as any,

  undoBar: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    marginHorizontal: 16, paddingVertical: 12, paddingHorizontal: 16,
    borderRadius: rad.full, backgroundColor: color.primary,
  },
  undoBarDark: { backgroundColor: color.ink },
  undoText: { flex: 1, ...type.labelMedium, color: color.onPrimary, fontWeight: '600' } as any,
  undoAction: { ...type.labelMedium, color: color.onPrimary, fontWeight: '700' } as any,

  dock: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.bg },
  sparkBtn: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  field: {
    flex: 1, height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
  /** MSG.06: отправка — красный круг с самолётиком. */
  sendBtn: {
    width: 48, height: 48, borderRadius: 24, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', ...cardShadow,
  },

  actPri: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  actPriText: { ...type.button, color: color.onPrimary } as any,
  actDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  actDarkText: { ...type.button, color: '#fff' } as any,
  actSoft: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  actSoftText: { ...type.button, color: color.fg } as any,
  actPlain: { height: 44, alignItems: 'center', justifyContent: 'center' },
  actPlainText: { ...type.button, color: color.fg } as any,
});
