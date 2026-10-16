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
  ActivityIndicator, KeyboardAvoidingView, Platform, Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import {
  CHAT, CHATMENU, THREAD, INVITE, UNDO_BAR, Msg, REACTIONS, SYS_ACT, planWhen, planPhase, sysLine, msgTime,
  KLEAL_SENDER } from '../src/chat';
import { inviteHoursLeft } from '../src/messages';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { useLang, T, getLang, dateLocale, use12h } from '../src/i18n';
import { useOnb, markSeen, setMsgPrefs } from '../src/state';
import { mediaUrl, agent, newIdem, ensureMe, isMe, pidOf, type VideoPayload } from '../src/api';
import { usePolling } from '../src/polling';
import { Sheet, SheetItem } from '../src/components/Sheet';
import * as Clipboard from 'expo-clipboard';
import { MessageFeed, type SysAct } from '../src/components/MessageFeed';
import { useVoiceMessage, VoiceMessageControl } from '../src/voice';
import { VideoNoteButton } from '../src/videonote';
import {
  IconChevronLeft, IconSpark, IconPerson, IconCalendar, IconCheckCircle, IconEllipsisV,
  IconClock, IconPin, IconInfo, IconBan,
} from '../src/components/icons';
import { Cover } from '../src/components/Cover';
import { GlassIconButton, GlassSurface } from '../src/components/LiquidGlass';
import { SendArrow } from '../src/components/SendArrow';
import { color, font, radius as rad, space, type } from '../src/theme';
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { withScheme } from '../src/intent';

export default function Conversation() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх композера — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  const params = useLocalSearchParams<{ who?: string; who_id?: string; title?: string; photo?: string }>();
  const other = String(params.who || '').trim();
  const intentTitle = String(params.title || '').trim();
  const photo = String(params.photo || '');

  const me = String(st.profile.name || '');
  /*
   * СОБЕСЕДНИК — ПОДПИСЬ И ID (kleal-ms/docs/IDENTITY.md). `who_id` едет параметром перехода; если
   * экран открыли без него (место вызова, куда id ещё не проведён), id берётся из первого ответа
   * сервера — тот кладёт `from_id`/`to_id` к каждой реплике. По одной подписи у тёзок сливались
   * переписки, а «моими» считались все сообщения переписки двух «Иванов».
   */
  const [learnedId, setLearnedId] = useState('');
  const otherId = String(params.who_id || '') || learnedId;
  const peer = useMemo(() => ({ name: other, id: otherId }), [other, otherId]);
  const isOther = useCallback((name: unknown, id: unknown) => {
    const i = String(id || '');
    if (otherId && i) return i === otherId;
    return String(name || '').trim().toLowerCase() === other.toLowerCase();
  }, [other, otherId]);
  // Свой id — чтобы «моё» решалось по нему. Пришёл — перерисовать то, что уже решено по имени.
  const [, setMeKnown] = useState('');
  useEffect(() => { ensureMe().then(setMeKnown); }, []);
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
  const [pending, setPending] = useState<{ kind: 'plan' | 'end' | 'send'; n: number } | null>(null);
  /** OF.19d: лист «Send the plan?» — план из самой затеи (день, час, место), отправка через OF.19a. */
  const [sendOpen, setSendOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  /** Время последнего известного сообщения — по нему сервер отдаёт только новые. */
  const since = useRef(0);
  /** MSG.06–MSG.11: живой план с этим человеком, заявка между нами, отметка чтения второй стороны. */
  const [livePlan, setLivePlan] = useState<any>(null);
  /**
   * Встреча с этим же человеком, которая уже прошла, — отдельно от живого плана.
   *
   * Подсказка MSG.08 утверждает «время так и не назначено». Сутки спустя сервер перекладывает
   * план из plans в history (mp_for), livePlan обнуляется — и подсказка звала создать план пару,
   * которая УЖЕ виделась. Живой план на её вопрос не отвечает: он про «есть ли план сейчас»,
   * а подсказка — про «назначалось ли время вообще».
   */
  const [pastPlan, setPastPlan] = useState<any>(null);
  const [request, setRequest] = useState<any>(null);
  /**
   * СОГЛАСИЕ — ОТДЕЛЬНО ОТ СВЕЖЕЙ ЗАЯВКИ, и это не мелочь.
   *
   * `request` — самая свежая заявка пары: она решает, ЧЬЮ затею показывать в карточке. А право
   * писать и назначать встречу даёт не она, а САМО ЗНАКОМСТВО — любая принятая заявка между вами.
   * Пока и то и другое читалось из одной `request`, вторая затея к тому, с кем уже переписываешься,
   * запирала работающий чат: новая заявка приходит `pending`, и поле ввода становилось
   * нередактируемым с подписью «написать можно после согласия», а «Создать план» гасла — у двоих,
   * которые уже виделись и переписываются.
   */
  const [accepted, setAccepted] = useState<any>(null);
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
      const r: any = await agent.thread(me, peer, since.current);
      merge((r?.messages || []) as Msg[]);
      if (!params.who_id) {
        for (const x of (r?.messages || []) as any[]) {
          const id = String((isMe(x.from, x.from_id, me) ? x.to_id : x.from_id) || '');
          if (id) { setLearnedId(id); break; }
        }
      }
      if (typeof r?.peer_read_at === 'number') setPeerRead(r.peer_read_at);
      // Ошибку отправки здесь НЕ гасим: опрос и отправка — разные события, и удачный опрос ничего
      // не говорит об уехавшей реплике. Раньше «Сообщение не ушло» стиралось через четыре
      // секунды, экран выглядел здоровым, а пузырь так и оставался недоставленным.
    } catch {
      /* тихо: это фоновая дотяжка, и ругаться на каждый неудавшийся опрос незачем */
    } finally {
      setLoading(false);
    }
  }, [me, peer, merge]);

  /** План и заявка между нами — для шапки, закреплённой карточки и карточек приглашения. */
  const loadSide = useCallback(async () => {
    if (!me || !other) return;
    try {
      const [pl, inb, out] = await Promise.all([agent.plans(me), agent.inbox(me), agent.outbox(me)]);
      const norm = (v: any) => String(v || '').trim().toLowerCase();
      const all = [...((pl as any)?.plans || [])];
      setLivePlan(all.find((p: any) =>
        (p.participants || []).some((x: any) => isOther(x.name, pidOf(x, 'name')))
        && (p.state === 'proposed' || p.state === 'confirmed')) || null);
      // История нужна ОДНОЙ подсказке и берётся отдельной выборкой. Слить её в `all` нельзя:
      // сервер меняет корзину, а не state, — протухший `confirmed` тут же вернулся бы в шапку и
      // в закреплённую карточку как живой план недельной давности.
      // `|| []` обязателен: старый бокс history не отдаёт вовсе, а один общий catch на весь
      // loadSide проглотил бы падение вместе с заявкой.
      const seen = [...((pl as any)?.plans || []), ...((pl as any)?.history || [])]
        .filter((p: any) =>
          (p.participants || []).some((x: any) => isOther(x.name, pidOf(x, 'name')))
          && planPhase(p) === 'after')
        .sort((a: any, b: any) => (b.starts_at || 0) - (a.starts_at || 0));
      // 'cancelled' сюда не попадает намеренно: отменённая встреча — как раз повод предложить новую.
      setPastPlan(seen[0] || null);
      const rows = [
        ...(Array.isArray(inb) ? inb : (inb as any)?.requests || []),
        ...(Array.isArray(out) ? out : (out as any)?.requests || []),
      ].filter((x: any) => isOther(x.from, x.from_id) || isOther(x.to, x.to_id));
      rows.sort((a: any, b: any) => (b.updated || 0) - (a.updated || 0));
      setRequest(rows[0] || null);
      // Знакомство — это ЛЮБАЯ принятая заявка пары, не обязательно самая свежая: вторая затея
      // приходит неотвеченной и права писать не отменяет.
      setAccepted(rows.find((x: any) => x.status === 'accepted') || null);
    } catch {
      /* тихо */
    }
  }, [me, other, isOther]);

  useEffect(() => { load(); loadSide(); markSeen(other); }, [me, other]);
  // План и заявка меняются редко — свой ритм, но спит так же, как и лента.
  usePolling(loadSide, 15000);

  /** Только настоящие реплики. События плана — не разговор: они не считаются ни в «прочитано»,
   *  ни в счётчике подсказки MSG.08 («вы обменялись N сообщениями»). */
  const talk = useMemo(() => msgs.filter((m) => !m.sys), [msgs]);


  // «Прочитано» отправляется, когда на экране появились новые ЧУЖИЕ сообщения, а не на каждый опрос.
  useEffect(() => {
    const theirs = talk.filter((m) => !isMe(m.from, (m as any).from_id, me)).length;
    if (theirs > readStamped.current) {
      readStamped.current = theirs;
      markSeen(other);
      agent.threadRead(me, peer).catch(() => {});
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
      const r: any = await agent.message(me, peer, String(m.text || ''), m.voice, m.cid,
                                         m.rt?.id, m.video);
      if (!r?.ok) throw new Error(String(r?.error || 'SEND_FAILED'));
      setMsgs((prev) => prev.map((x) => (x.cid === m.cid ? { ...x, state: undefined, id: r.id, t: r.t || x.t } : x)));
      setErr('');
    } catch (e) {
      // Причина называется своя: заблокированному «проверь связь» — ложь, он будет
      // переподключаться и писать снова.
      const code = String((e as any)?.body?.error || (e as any)?.message || '');
      setMsgs((prev) => prev.map((x) => (x.cid === m.cid ? { ...x, state: 'failed' } : x)));
      setErr(code === 'BLOCKED' ? CHAT.blocked()
             : code === 'NOT_MATCHED' ? CHAT.writeNotMatched()
             : CHAT.offline());
    }
  }, [me, peer]);

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
    // Не только кнопкой: по «отправить» с клавиатуры сюда приходят мимо неактивного поля.
    if (!canWrite) return;
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
  /**
   * ПИСАТЬ МОЖНО ТОЛЬКО ТОМУ, КТО СОГЛАСИЛСЯ — и знать это экран обязан ДО отправки.
   *
   * Сервер правило держит (`_mp_matched` -> NOT_MATCHED), плану оно уже объяснено выше (`canPlan`),
   * а переписка оставалась открытой: человек писал, пузырь появлялся с галочкой, и только потом
   * приходил отказ. Пузырь при этом оставался в ленте навсегда.
   *
   * Здесь правило МЯГЧЕ, чем у плана, и это намеренно. `canPlan` требует явного `accepted`; для
   * письма достаточно, чтобы не было ИЗВЕСТНО обратное. Заявку экран берёт из входящих и исходящих,
   * и если список не догрузился, `request` пуст — запереть на этом основании работающую переписку
   * хуже, чем пропустить запрос, который сервер всё равно отобьёт.
   */
  /* Переписка с Kleal — односторонняя. Строка сюда уходила бы в ошибку «вы не знакомы»:
     отправка требует принятой заявки, а её с продуктом не бывает. Честнее сказать это словами,
     чем дать написать и показать сбой. */
  // Сравнение своей строкой, а не общим `norm`: он объявлен ниже по файлу, и до него здесь
  // ещё нельзя дотянуться.
  const isKleal = String(other || '').trim().toLowerCase() === KLEAL_SENDER.toLowerCase();
  const canWrite = !isKleal && !(request && !accepted);

  /** Кружок уходит тем же путём, что текст и голосовое: тот же ключ, то же состояние, тот же повтор. */
  const canSend = !!me && !!other && canWrite;
  const sendCircle = (payload: VideoPayload) => {
    if (!canSend) return;
    const local: Msg = {
      from: me, to: other, text: '', video: payload,
      t: Date.now() / 1000, cid: newIdem('c'), state: 'sending',
    };
    setMsgs((prev) => [...prev, local]);
    deliver(local);
  };

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
  // Между людьми голосовое уходит и без расшифровки: сообщение — это звук, текст лишь подсказка.
  }, !me || !other, { requireTranscript: false });

  /**
   * План — тому, кто уже принял приглашение, и никому больше.
   *
   * Сервер это правило держит сам (`NOT_MATCHED`), а лист действий его не знал: на экране, где
   * даже написать нельзя — «приглашение не принято», — «Создать план» открывалась как обычно,
   * человек заполнял форму, выбирал время и получал отказ уже на отправке. Поймано на живом
   * телефоне. Причину называем ДО формы, а не после заполненной.
   */
  const canPlan = !!accepted;

  const startPending = (kind: 'plan' | 'end') => {
    if (pending) return;
    if (kind === 'plan' && !canPlan) {
      setActions(false);
      setErr(CHAT.notMatched());
      return;
    }
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
      if (pending.kind === 'send') {
        sendDraftPlan();
      } else if (pending.kind === 'plan') {
        router.navigate({ pathname: '/plan', params: planParams() });
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
        // Сначала СЕРВЕРУ: разговор закрывают для двоих, а не только у себя в телефоне.
        // Локальная отметка ниже — про свой список, она не заменяет сообщения второму.
        agent.threadEnd(me, peer).catch(() => {});
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
    /*
      ПОКА ПЛАН ЗАКРЕПЛЁН СВЕРХУ — ПОДПИСИ НЕТ.
      Здесь она говорила «План: Ср, 9 сент. · 23:25», а ровно та же дата стояла строкой выше, в
      закреплённой полосе. Две строки об одном на расстоянии сорока точек друг от друга — это не
      забота, а шум; на борде под именем нет ничего.
      Без плана подпись остаётся: «Общаетесь сегодня» и «совпали на …» ничего не повторяют.
    */
    if (livePlan) return '';
    if (msgs.length) {
      const first = new Date((msgs[0].t || 0) * 1000);
      // Разговор начался сегодня — «с субботы» про сегодняшний день читается как «давно уже».
      if (first.toDateString() === new Date().toDateString()) return THREAD.talkingToday();
      // Русскому нужен родительный: «с четверга». Английскому — просто имя дня.
      const day = ru ? THREAD.weekdayGen(first.getDay()) : first.toLocaleDateString(dateLocale(), { weekday: 'long' });
      return THREAD.talkingSince(day);
    }
    if (accepted) {
      // Подпись называет затею, НА КОТОРОЙ ВЫ СОВПАЛИ, — то есть принятую. Свежая неотвеченная
      // заявка её не переписывает: совпадения по ней ещё нет.
      const title = String(accepted?.intent?.title || (accepted?.intent?.topics || []).join(', ') || '');
      if (title) return THREAD.matchedOn(title);
    }
    return '';
  }, [livePlan, msgs, request, ru, me]);

  /** В каком состоянии знакомство, когда сказать ещё нечего. См. CHAT.empty. */
  const emptyState: 'they-accepted' | 'i-accepted' | 'sent' | 'invited-me' | 'none' =
    accepted ? (isOther(accepted.to, accepted.to_id) ? 'they-accepted' : 'i-accepted')
    : !request ? 'none'
    : request.status === 'pending' ? (isOther(request.to, request.to_id) ? 'sent' : 'invited-me')
    : 'none';

  /** MSG.18–MSG.21: входящая заявка от этого человека, если её не скрывали. */
  const inviteIn = request && isOther(request.from, request.from_id) ? request : null;
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
    who_id: otherId,
    title: requestTitle || intentTitle,
    photo,
    mode: String(request?.intent?.mode || ''),
    address: String(request?.intent?.address || ''),
    link: String(request?.intent?.link || ''),
  });


  const toPlan = () => router.navigate({ pathname: '/plan', params: planParams() });

  /**
   * OF.19d: план, собранный из ЗАТЕИ — её день, час и место. Только встреча вживую и только если в
   * затее есть день и час в будущем; иначе «Make the plan» ведёт в форму плана, как раньше.
   */
  const draftPlan = useMemo(() => {
    const it: any = request?.intent || {};
    if (String(it.mode || 'offline') !== 'offline') return null;
    const key = String(it.dateKey || it.date_key || '');
    const mins = Number(it.minutes);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(key) || !Number.isFinite(mins)) return null;
    const d = new Date(key + 'T00:00:00');
    d.setMinutes(mins);
    const at = Math.floor(d.getTime() / 1000);
    if (!(at * 1000 > Date.now() + 15 * 60 * 1000)) return null;
    return {
      starts_at: at,
      when: String(it.when || ''),
      district: String(it.district || it.place || ''),
      address: String(it.address || ''),
    };
  }, [request]);

  const sendDraftPlan = async () => {
    if (!draftPlan) return;
    try {
      const r: any = await agent.planPropose(me, peer, {
        title: requestTitle || intentTitle || T('Встреча', 'Meetup', 'Quedada'),
        mode: 'offline', ...draftPlan,
      });
      if (!r?.ok) {
        setErr(r?.error === 'NOT_MATCHED' ? CHAT.notMatched()
          : r?.error === 'IN_THE_PAST' ? CHAT.inThePast()
          : r?.error === 'PLAN_EXISTS' ? CHAT.planExists()
          : CHAT.planFailed());
        return;
      }
      if (r.plan) setLivePlan(r.plan);
      loadSide();
      load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  const makePlan = () => {
    setActions(false);
    if (!canPlan) { setErr(CHAT.notMatched()); return; }
    if (draftPlan) setSendOpen(true); else toPlan();
  };
  /** Открыть УЖЕ существующий план. Один переход на закреплённую карточку и лист действий. */
  const openLivePlan = () => {
    if (!livePlan) return;
    router.navigate({ pathname: '/plan',
      params: { id: livePlan.id, who: other, who_id: otherId, title: livePlan.title || intentTitle, photo } });
  };

  /**
   * Ответ на план прямо из переписки — тот же запрос, что и с экрана плана.
   *
   * `version` обязателен: он и есть защита от гонки. Двое могут нажать одновременно — один
   * «подтвердить», другой «перенести», — и сервер отвергнет тот ответ, который отвечал на
   * устаревшее состояние. Кнопка в ленте живёт дольше экрана плана, так что без версии она
   * однажды подтвердила бы не то, что человек прочитал.
   */
  const respondPlan = useCallback(async (action: string) => {
    if (!livePlan?.id) return;
    try {
      const r: any = await agent.planRespond(livePlan.id, me, action, { version: livePlan.version });
      if (r?.plan) setLivePlan(r.plan);
      else await loadSide();
      since.current = 0;
      await load();
    } catch {
      /* Молчим намеренно: строка события останется с кнопкой, и человек нажмёт ещё раз.
         Сообщать об ошибке в ленте некуда — она не его реплика. */
    }
  }, [livePlan, me, load, loadSide]);

  /**
   * ЧТО МОЖНО СДЕЛАТЬ ПРЯМО ИЗ СОБЫТИЯ.
   *
   * Решает экран, а не сервер, и это главное в устройстве. Строка «план предложен» остаётся в
   * ленте навсегда, а подтверждать план можно ровно пока он не подтверждён, не отменён и не
   * перенесён ещё раз. Сервер, записав кнопку в строку один раз, соврал бы уже через минуту;
   * экран же смотрит на ЖИВОЙ план при каждой отрисовке, и кнопка исчезает сама.
   *
   * Второе правило: кнопку видит только тот, от кого ждут ответа. Своё же событие («ты предложил
   * план») кнопки не получает — подтверждать самому себе нечего.
   *
   * Третье: кнопка живёт только на ПОСЛЕДНЕМ событии своего вида. Иначе три переноса подряд дают
   * три «подтвердить», и человек нажимает не тот.
   */
  const lastSysOf = useCallback((code: string) => {
    for (let i = msgs.length - 1; i >= 0; i--) if (msgs[i].sys?.code === code) return msgs[i].id;
    return '';
  }, [msgs]);

  const sysAction = useCallback((m: Msg): SysAct[] | null => {
    const sys = m.sys;
    if (!sys?.code) return null;
    /*
     * НОВАЯ ЗАТЕЯ — ЕДИНСТВЕННОЕ СОБЫТИЕ, КОТОРОМУ ПЛАН НЕ НУЖЕН. Все остальные события здесь про
     * встречу, и без живого плана у них нет ни смысла, ни кнопки. Это — наоборот: оно про то, что
     * встречи по новой затее ЕЩЁ НЕТ. И нужнее всего оно ровно тогда, когда полоса сверху занята
     * планом по прежней затее: другого входа в карточку новой с этого экрана не существует.
     * Кнопка живёт только на ПОСЛЕДНЕМ таком событии — по тому же правилу, что и у событий плана:
     * три строки подряд с тремя кнопками ведут в одну и ту же карточку, и человек жмёт не ту.
     */
    if (sys.code === 'intent_new') {
      return m.id === lastSysOf('intent_new')
        ? [{ key: 'intent', label: SYS_ACT.openIntent(), onPress: () => setIntentOpen(true) }]
        : null;
    }
    if (!livePlan) return null;
    /*
     * СТРОКА ОТ ПРОШЛОГО ПЛАНА КНОПКИ НЕ ПОЛУЧАЕТ. План отменили и завели новый — просьба
     * «выбери место» от первого так и осталась в ленте, а `place_set` у второго пуст, и под
     * недельной строкой рисовалась живая кнопка, ведущая в другой план. Событий, которые новый
     * план не переиздаёт (plan_ask, moved_to_call), это касается в первую очередь.
     */
    if (livePlan.created && (m.t || 0) < livePlan.created) return null;
    const mine = isMe(sys.by, (sys as any).by_id, me);
    /*
     * ЧТО МОЖНО — ГОВОРИТ СЕРВЕР. Раньше кнопка выводилась здесь из восьми полей проекции
     * (`locked`, `pending`, `waiting_on`, `state`, …) — второй правдой о тех же правилах, и она
     * расходилась с первой: в заморозке за два часа лента прятала всё, хотя сервер и спека
     * подтверждение разрешают («в заморозке живут только ответы»). Теперь `actions` считается той
     * же таблицей, по которой ручки отказывают (mplan_rules): что в списке — то и кнопка.
     */
    const acts: string[] | null = Array.isArray(livePlan.actions) ? livePlan.actions : null;
    // Ответ без `actions` не значит «ничего нельзя»: до правки лента пряталась по `locked`, так и
    // ведём себя, пока сервер не сказал иначе.
    const serverOffers = (a: string) => (acts ? acts.includes(a) : !livePlan.locked);
    const act = (key: string, label: string, onPress: () => void, soft = false): SysAct =>
      ({ key, label, onPress, soft });

    if (sys.code === 'plan_proposed' && m.id === lastSysOf('plan_proposed')) {
      // Отвечает тот, кому предложили, и только пока план ещё ждёт ответа.
      // Пока висит предложенный перенос, подтверждать старые условия нельзя — сервер отвечает
      // на такое PENDING_CHANGE. Отвечать надо на перенос, и кнопки для этого ниже.
      if (mine || !serverOffers('confirm')) return null;
      return [act('confirm', SYS_ACT.confirmPlan(), () => respondPlan('confirm'))];
    }
    if (sys.code === 'plan_counter' && m.id === lastSysOf('plan_counter')) {
      const pend = livePlan.pending;
      if (!pend || pend.mine || !serverOffers('accept_change')) return null;      // своё же предложение подтверждать нечего
      const newHour = msgTime(pend.starts_at, ru);
      const oldHour = msgTime(livePlan.starts_at, ru);
      return [
        act('yes', SYS_ACT.acceptTime(newHour), () => respondPlan('accept_change')),
        act('no', SYS_ACT.keepTime(oldHour), () => respondPlan('reject_change'), true),
      ];
    }
    if (sys.code === 'plan_ask' && m.id === lastSysOf('plan_ask')) {
      // Просьба адресована ВТОРОМУ, и снимается она, когда он её выполнил.
      if (mine) return null;
      // Те же признаки, что и на экране плана (plan.tsx:264): у гибрида вход два, и каждый
      // закрывается своим. Запасной `address_set` — для старых планов, где поля были одним.
      if (sys.kind === 'link') {
        const has = livePlan.link_set ?? !!livePlan.address_set;
        return has || !serverOffers('address') ? null : [act('link', SYS_ACT.addLink(), openLivePlan)];
      }
      const hasPlace = livePlan.place_set ?? !!livePlan.address_set;
      return hasPlace || !serverOffers('address') ? null : [act('place', SYS_ACT.pickPlace(), openLivePlan)];
    }
    if (sys.code === 'moved_to_call' && m.id === lastSysOf('moved_to_call')) {
      const link = String(livePlan.link || '').trim();
      if (!link) return null;
      return [act('call', SYS_ACT.openCall(), () => { Linking.openURL(withScheme(link)).catch(() => {}); })];
    }
    return null;
  }, [livePlan, me, msgs, ru, lastSysOf, openLivePlan, respondPlan]);

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/* Фирменный фон — тот же бледный слой, что у разговора с Бадди (ChatShell). */}
        <Ambient glows={GLOW_FORM} />
        {/*
          ЗАКРЕПЛЁННОЕ — ПОЛОСА ВО ВСЮ ШИРИНУ (борд, node 3642-221266).

          Была карточка с полями по бокам, тенью и цветной плиткой-значком. На борде иначе: белая
          полоса от края до края, круглая миниатюра у левого края и шеврон в белом круге у правого.
          Оба круга стоят на той же вертикали, что кнопка «назад» и аватар в шапке под ними, —
          отсюда одинаковый отступ 18 у всех четырёх. Это и держит верх экрана в порядке: два ряда,
          и по краям у них общая колонка.
        */}
        {livePlan ? (
          <Pressable
            accessibilityRole="button"
            style={s.pinRow}
            onPress={openLivePlan}
          >
            <View style={s.pinBarWhite} />
            {photo ? (
              <Image source={{ uri: mediaUrl(String(photo)) }} style={s.pinThumb} />
            ) : (
              <View style={[s.pinThumb, s.avaEmpty]}><IconCalendar size={18} c={color.primary} /></View>
            )}
            {/*
              ОДНА СТРОКА, КАК НА БОРДЕ. Здесь стояли три: заголовок, «когда · где» и состояние
              встречи. Вместе с подписью под именем ниже дата и время повторялись на одном экране
              ТРИЖДЫ — снято с телефона: «Ср, 9 сент. · 23:25» в полосе, «Подтверждено обоими» под
              ним и «План: Ср, 9 сент. · 23:25» под именем.
              Полоса — это ВХОД в затею, а не её пересказ: и «когда», и «где», и состояние живут на
              экране плана, куда ведёт шеврон справа. Повторять их поверх ленты значит забивать верх
              экрана тем, что сказано на один тап дальше.
            */}
            <View style={s.pinMid}>
              <Text style={s.pinTitle} numberOfLines={1}>{livePlan.title || intentTitle}</Text>
            </View>
            <View style={s.pinChev}><Text style={s.pinChevText}>›</Text></View>
          </Pressable>
        ) : requestTitle ? (
          /*
            Встречи ещё нет — закреплён ИНТЕНТ, по которому вы совпали. Он и есть то, ради чего
            этот разговор начался, и провалиться в него надо из чата, а не из меню за «•••»:
            «Сообщения» теперь ведут только сюда, и другого пути к карточке интента не остаётся.
          */
          <Pressable accessibilityRole="button" style={s.pinRow} onPress={() => setIntentOpen(true)}>
            <View style={s.pinBarWhite} />
            {photo ? (
              <Image source={{ uri: mediaUrl(String(photo)) }} style={s.pinThumb} />
            ) : (
              <View style={[s.pinThumb, s.avaEmpty]}><IconSpark size={18} c={color.primary} /></View>
            )}
            <View style={s.pinMid}>
              <Text style={s.pinTitle} numberOfLines={1}>{requestTitle}</Text>
              {/*
                Подписей под заголовком на макете нет, и это верно: карточка здесь — вход в затею,
                а не её пересказ. Время и формат живут на самом экране интента, за шевроном справа,
                и повторять их поверх ленты значит забивать шапку тем, что уже сказано ниже.
                У ЖИВОГО ПЛАНА иначе — там подпись осталась: встреча уже назначена, и «когда» с
                «подтверждено» человек обязан видеть, не открывая ничего.
              */}
            </View>
            <View style={s.pinChev}><Text style={s.pinChevText}>›</Text></View>
          </Pressable>
        ) : null}

        {/*
          ШАПКА ПО МАКЕТУ: назад · имя по центру · аватар справа.

          Было иначе: аватар и имя стояли слева одной группой, а справа висело «•••». Три точки
          отсюда убраны — тот же лист действий открывается кнопкой у поля ввода, где рука и так
          лежит во время разговора, и два входа в одно меню на одном экране только делили внимание.

          Аватар справа — вход в профиль. Он остался нажимаемым, просто переехал на своё место по
          макету: имя посередине читается как заголовок экрана, а не как строка списка.
        */}
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} style={s.back} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
            <IconChevronLeft />
          </Pressable>
          <View style={s.headMid}>
            <Text style={s.name} numberOfLines={1}>{other}</Text>
            {subtitle ? <Text style={s.sub} numberOfLines={1}>{subtitle}</Text> : null}
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={T('Профиль', 'Profile', 'Perfil')}
            onPress={() => router.navigate({ pathname: '/person',
                                             params: { who: other, who_id: otherId, photo: String(photo || '') } })}
            style={({ pressed }) => pressed && { opacity: 0.85 }}
          >
            {photo ? (
              <Image source={{ uri: mediaUrl(String(photo)) }} style={s.ava} />
            ) : (
              <View style={[s.ava, s.avaEmpty]}><IconPerson size={20} /></View>
            )}
          </Pressable>
        </View>

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
                  onPress={() => router.navigate({ pathname: '/invite', params: { id: inviteIn.id } })}
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
            sysAction={sysAction}
            peerRead={peerRead}
            onReply={setReplyTo}
            onReact={react}
            onPick={setPicked}
            onRetry={deliver}
          />

          {/* MSG.09 — предложение ушло; ничего не забронировано до «да». */}
          {livePlan?.state === 'proposed' && isMe(livePlan.host, livePlan.host_id, me) ? (
            <View style={s.sysNote}>
              <View style={{ flex: 1 }}>
                <Text style={s.sysTitle}>{THREAD.sentAsProposal(other)}</Text>
                <Text style={s.sysSub}>{THREAD.nothingBooked(other)}</Text>
              </View>
              <IconCheckCircle size={26} />
            </View>
          ) : null}

          {/* MSG.08 — подсказка Kleal: счёт сообщений настоящий, план по кнопке, «пока нет» помнит.
              Прошедшая встреча гасит её так же, как живой план: звать назначить время тем, кто уже
              виделся, — врать про их же историю. */}
          {!livePlan && !pastPlan && talk.length >= 8 && !noNudge ? (
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
              {pending.kind === 'send' ? UNDO_BAR.sending() : pending.kind === 'plan' ? UNDO_BAR.creating(other) : UNDO_BAR.ending()}
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
            <Pressable accessibilityRole="button" accessibilityLabel={T('Убрать', 'Remove', 'Eliminar')} onPress={() => setReplyTo(null)} hitSlop={10}>
              <Text style={s.replyX}>✕</Text>
            </Pressable>
          </View>
        ) : null}

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          {/*
            ВХОД В ДЕЙСТВИЯ РАЗГОВОРА (O.19). На кадре в этом слоте скрепка, но вложений в продукте
            нет, и рисовать что-либо ПОХОЖЕЕ на вложение нельзя. Плюс у поля ввода во всех
            мессенджерах означает «прикрепить файл» — он обещал бы то же самое. Три точки в этом
            приложении уже означают ровно этот лист: ими открыт он же из шапки разговора.

            ЧТО БЫЛО НЕ ТАК. Стояла искра, и у кнопки НЕ БЫЛО ПОВЕРХНОСТИ вовсе: розовый значок в
            двадцать пунктов на фоне страницы, тогда как поле рядом налито серым, а отправка —
            красный круг с тенью. Единственный элемент дока без фона читался как украшение, и
            человек её попросту не видел. Сообщено с телефона.

            И сам значок сбивал: искра в этом приложении — это САМ KLEAL, его аватар в
            «Сообщениях» (messages.tsx). Рядом с полем ввода она обещала «спросить у агента», а за
            ней открываются действия над встречей.

            Поверхность взята у поля ввода — тот же `neutral100`: кнопка входит в ту же семью, а
            не заводит третий вид элемента. Значок нейтральный, не красный: отправка здесь главная,
            и два красных пятна по краям дока спорили бы за внимание.

            ДА, ТОЧКИ ЕСТЬ И В ШАПКЕ, и это осознанное повторение, а не недосмотр: там они у имени
            собеседника, здесь — у поля ввода, куда рука тянется во время разговора. Один и тот же
            значок для одного и того же листа честнее двух разных.
          */}
          {/*
            Вид — компонент «Chat/Composer» (💣 UI, 6164:19536): «⋮» в стеклянном круге 48, рядом
            стеклянное поле 48. Значок теперь совпадает с тем, что обещает этот комментарий: точки,
            а не плюс (плюс у поля ввода везде значит «прикрепить файл»).
          */}
          <GlassIconButton size={48} label={CHAT.actionsTitle()} onPress={() => setActions(true)}>
            <IconEllipsisV size={30} />
          </GlassIconButton>
          {/*
            Поле — стекло 48, и отправка, голосовое и кружок стоят ВНУТРИ него, как на GR.18 и в
            «Chat/Composer». Само поле остаётся в дереве всегда; во время записи внутри него нет
            только ввода — полоса записи занимает его место. Кнопки записи не переезжают по дереву в
            миг старта, иначе React пересоберёт их и жест удержания оборвётся.
          */}
          <View style={s.fieldBox}>
            <GlassSurface tone="light" radius={999}
              style={[s.field, voice.phase === 'idle' && draft.trim() ? s.fieldSending : null]}>
              {voice.phase === 'idle' ? (
                <TextInput
                  style={s.input}
                  value={draft}
                  onChangeText={setDraft}
                  editable={canWrite}
                  placeholder={canWrite ? CHAT.placeholderTo(other)
                               : isKleal ? CHAT.klealNoReply() : CHAT.lockedTo(other)}
                  placeholderTextColor={color.muted}
                  onSubmitEditing={send}
                  returnKeyType="send"
                />
              ) : null}
              {/*
                Одна кнопка на два действия, как в мессенджерах: пусто в поле — микрофон (удержание
                записывает голосовое), есть текст — стрелка отправки.
              */}
              {voice.phase === 'idle' && draft.trim() ? (
                <SendArrow onPress={send} />
              ) : (
                <>
                  {/* Кружок отдельной кнопкой, а не переключателем на микрофоне: у микрофона свой
                      жест удержания, и делить его на два смысла значит ломать оба. */}
                  <VideoNoteButton onSend={sendCircle} disabled={!canSend} hidden={voice.phase !== 'idle'} />
                  <VoiceMessageControl voice={voice} />
                </>
              )}
            </GlassSurface>
          </View>
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
          {picked && isMe(picked.from, (picked as any).from_id, me) ? (
            <SheetItem
              label={CHAT.deleteMsg()}
              note={CHAT.deleteNote()}
              danger
              onPress={() => picked && removeMsg(picked)}
            />
          ) : null}
        </Sheet>

        {/* OF.19 «Chat options»: пункты меню с пояснениями, как у меню группы. План у пары один —
            пока он живой, первый пункт ведёт к нему, а не заводит второй. */}
        <Sheet visible={actions} onClose={() => setActions(false)} title={CHATMENU.title()}>
          {livePlan ? (
            <SheetItem icon={<IconCalendar size={20} c={color.primary} />} label={CHATMENU.openPlan()}
              note={CHATMENU.openPlanNote(other)} onPress={() => { setActions(false); openLivePlan(); }} />
          ) : (
            <SheetItem icon={<IconCalendar size={20} c={color.primary} />} label={CHATMENU.makePlan()}
              note={CHATMENU.makePlanNote(other)} disabled={!canPlan} onPress={makePlan} />
          )}
          <SheetItem icon={<IconInfo size={20} c={color.primary} />} label={CHATMENU.intentInfo()}
            note={CHATMENU.intentInfoNote()} onPress={() => { setActions(false); setIntentOpen(true); }} />
          <SheetItem icon={<IconBan size={20} c={color.danger} />} label={CHATMENU.endChat()} danger
            note={CHATMENU.endChatNote()} onPress={() => startPending('end')} />
        </Sheet>

        {/* OF.19d «Send the plan?»: план из затеи — день, час, место. «Change» ведёт в форму плана. */}
        <Sheet visible={sendOpen} onClose={() => setSendOpen(false)} title={CHATMENU.sendTitle()}>
          {draftPlan ? (
            <>
              <View style={s.sendCard}>
                <Cover intent={{ title: requestTitle || intentTitle, topics: request?.intent?.topics, mode: 'offline' }} style={s.sendCover} />
                <View style={s.sendBody}>
                  <View style={s.sendRow}>
                    <IconCalendar size={18} c={color.primary} />
                    <Text style={s.sendText}>{dayLabel(draftPlan.starts_at)}</Text>
                    <IconClock size={18} c={color.primary} />
                    <Text style={s.sendText}>{new Date(draftPlan.starts_at * 1000).toLocaleTimeString(dateLocale(), { hour: '2-digit', minute: '2-digit', hour12: use12h(ru) })}</Text>
                  </View>
                  {draftPlan.address || draftPlan.district ? (
                    <View style={s.sendRow}>
                      <IconPin size={18} c={color.primary} />
                      <Text style={s.sendText} numberOfLines={1}>{draftPlan.address || draftPlan.district}</Text>
                    </View>
                  ) : null}
                </View>
              </View>
              <Text style={s.sendNote}>{CHATMENU.sendNote(other)}</Text>
              <Pressable accessibilityRole="button" style={s.sendCta}
                onPress={() => { setSendOpen(false); if (!pending) setPending({ kind: 'send', n: 4 }); }}>
                <Text style={s.sendCtaText}>{CHATMENU.sendTo(other)}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={s.sendInk} onPress={() => { setSendOpen(false); toPlan(); }}>
                <Text style={s.sendInkText}>{CHATMENU.change()}</Text>
              </Pressable>
            </>
          ) : null}
        </Sheet>

        {/* MSG.10 — интент как лист фактов. Только то, что заявка знает на самом деле: где именно
            пройдёт встреча, не обещаем — «после подтверждения обоих», это и есть правило OF.C3. */}
        <Sheet
          visible={intentOpen}
          onClose={() => setIntentOpen(false)}
          title={requestTitle || intentTitle || T('Интент', 'Intent', 'Propuesta')}
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

/** «Thu 23 July» — день плана для листа OF.19d, тем же видом, что на карточке плана. */
function dayLabel(sa: number): string {
  const d = new Date(sa * 1000);
  const wd = d.toLocaleDateString(dateLocale(), { weekday: 'short' }).replace(/\.$/, '');
  return `${wd.charAt(0).toUpperCase() + wd.slice(1)} ${d.getDate()} ${d.toLocaleDateString(dateLocale(), { month: 'long' })}`;
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  sendCard: { borderRadius: 20, overflow: 'hidden', backgroundColor: 'rgba(255,255,255,0.6)' },
  sendCover: { height: 128, width: '100%' },
  sendBody: { padding: 16, gap: 12 },
  sendRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sendText: { fontFamily: font.text, fontSize: 15, lineHeight: 22, color: color.fg, marginRight: 8, flexShrink: 1 } as any,
  sendNote: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,
  sendCta: {
    height: 48, borderRadius: 99, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
    shadowColor: color.primary, shadowOpacity: 0.25, shadowRadius: 12, shadowOffset: { width: 0, height: 4 },
  },
  sendCtaText: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: '#fff' } as any,
  sendInk: { height: 48, borderRadius: 99, backgroundColor: color.fg, alignItems: 'center', justifyContent: 'center' },
  sendInkText: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: '#fff' } as any,

  /** Ряд 56 и поля 16 — как оба App Bar на борде; кнопки по краям 44×44. */
  head: { flexDirection: 'row', alignItems: 'center', height: 56, paddingHorizontal: 16 },
  headMid: { flex: 1, alignItems: 'center' },
  /** Белый круг без обводки — на борде у кнопки только заливка #FFFFFF. */
  back: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  /*
    ИМЯ И НАЗВАНИЕ ЗАТЕИ — РАЗНЫЕ ПО РАЗМЕРУ И ПО НАЧЕРТАНИЮ.

    Оба стояли 15/600 и оттого сливались в один блок: два ряда одинаковым текстом читаются как
    сплошная шапка без верха и низа. На борде они действительно одного кегля, но там и рядов
    ровно два, а у нас над ними ещё полоса состояния и под ними лента — иерархия нужнее.

    Имя — заголовок ЭКРАНА: с кем говоришь. Оно крупнее и плотнее (Geist-600, 17).
    Название затеи — закреплённая подсказка о том, ПРО ЧТО разговор: мельче и легче (Geist-500, 15).

    И главное: семейство здесь указано явно. Раньше стоял только `fontWeight`, а в проекте вес на
    подключённых шрифтах НЕ РАБОТАЕТ — каждое начертание отдельное семейство (см. шапку src/theme.ts).
    Обе строки рисовались системным шрифтом вместо Geist, и это было заметно рядом с остальным
    приложением.
  */
  name: { fontFamily: font.textSemibold, fontSize: 17, lineHeight: 24, color: color.fg, textAlign: 'center' } as any,
  sub: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted, marginTop: 1, textAlign: 'center' } as any,
  ava: { width: 44, height: 44, borderRadius: 22 },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },

  /*
    ЗАКРЕПЛЁННОЕ — ПО ЧИСЛАМ БОРДА (OF.C2, node 3642-221266), а не на глаз.

    Устроено так: белый ПРЯМОУГОЛЬНИК лежит НЕ во всю ширину, а от x=38 до x=353 при экране 390,
    и по его краям стоят два круга 44×44 — миниатюра на x=16 и шеврон на x=330. Круги перекрывают
    концы прямоугольника, и вместе это читается пилюлей, хотя скруглений у самого прямоугольника
    нет ни одного.

    Отсюда числа: строка с полями 16 по краям, прямоугольник отступает внутри неё ещё на 22 слева
    и 21 справа (38−16 и 374−353), круги прижаты к краям строки. Ровно те же 16 и те же 44 у
    кнопок шапки под ней — потому оба ряда и стоят одной колонкой.

    Прежняя моя версия была полосой во всю ширину с отступом 18 — это выглядело совсем иначе.
  */
  pinRow: {
    flexDirection: 'row', alignItems: 'center',
    marginHorizontal: 16, marginBottom: 6, minHeight: 44,
  },
  /** Прямоугольник ПОД кругами. Скруглений нет — их роль играют сами круги на концах. */
  pinBarWhite: {
    position: 'absolute', left: 22, right: 21, top: 0, bottom: 0,
    backgroundColor: color.card,
  },
  pinThumb: { width: 44, height: 44, borderRadius: 22, backgroundColor: color.neutral100 },
  /** Отступы по 8 от кругов, чтобы длинный заголовок не залезал под них. */
  pinMid: { flex: 1, alignItems: 'center', paddingHorizontal: 8 },
  pinTitle: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.fg, textAlign: 'center' } as any,
  pinChev: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: color.card,
    alignItems: 'center', justifyContent: 'center',
  },
  pinChevText: { fontSize: 20, color: color.fg, marginTop: -2 } as any,

  // MSG.18–MSG.21 — карточка приглашения в ленте.
  invCard: {
    backgroundColor: color.glassCard, borderRadius: rad.lg, padding: space.md,
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

  /** Ряд ввода «Chat/Composer»: поля 20, промежуток 8, всё ростом 48. */
  dock: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 20, paddingTop: space.sm, backgroundColor: color.ambientBase },
  fieldBox: { flex: 1 },
  /** Поле — стекло 48 (белое 56% в макете); внутри ввод, голосовое и кружок либо отправка. */
  field: { height: 48, flexDirection: 'row', alignItems: 'center', paddingLeft: 16, paddingRight: 12, gap: space.sm },
  /** С текстом справа 2: круг отправки 44 стоит почти у края поля. */
  fieldSending: { paddingRight: 2 },
  /** Набор — Geist 400 15/20, как в «Chat/Composer». Семейство явно: вес на этих шрифтах не работает. */
  input: { flex: 1, color: color.fg, fontFamily: font.text, fontSize: 15, paddingVertical: 0 } as any,

  actPri: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  actPriText: { ...type.button, color: color.onPrimary } as any,
  actDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  actDarkText: { ...type.button, color: '#fff' } as any,
  actSoft: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  actSoftText: { ...type.button, color: color.fg } as any,
  actPlain: { height: 44, alignItems: 'center', justifyContent: 'center' },
  actPlainText: { ...type.button, color: color.fg } as any,
});
