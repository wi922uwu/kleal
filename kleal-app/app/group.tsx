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
import { useRouter, useLocalSearchParams, useIsFocused } from 'expo-router';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, markSeen, setMsgPrefs } from '../src/state';
import { MSG, joinNames } from '../src/messages';
import { group as gapi, agent, mediaUrl, newIdem, ensureMe, isMe, pidOf, type GroupInfo, type GroupRemovalReason,
  type VoicePayload, type VideoPayload } from '../src/api';
import { ROOM, GROUP, groupSysLine, roomMsg, type GroupSys } from '../src/groups';
import { GPLAN } from '../src/gplan';
import { ROLE } from '../src/roles';
import { IconCrown } from '../src/components/icons';
import { adoptGroup } from '../src/ginvites';
import { setResults } from '../src/results-store';
import { openResults } from '../src/results-navigation';
import { IconChevronRight, IconClose, IconPerson, IconEllipsisV, IconInfo, IconUserPlus, IconUserX, IconBan,
  IconGroups, IconExit, IconAlertTriangle, IconClock, IconCheck, IconBellOff, IconBell, IconFlag, IconCopy, IconTrash } from '../src/components/icons';
import { SendArrow } from '../src/components/SendArrow';
import { interestLabels } from '../src/interest-label';
import { Sheet, SheetItem, SheetText } from '../src/components/Sheet';
import { MessageFeed } from '../src/components/MessageFeed';
import { CHAT, Msg, REACTIONS, msgTime } from '../src/chat';
import { usePolling } from '../src/polling';
import * as Clipboard from 'expo-clipboard';
import { color, font, labelFamily, radius as rad, space, type } from '../src/theme';
import { GlassPill } from '../src/components/Glass';
import { GlassBack, GlassIconButton, GlassSurface } from '../src/components/LiquidGlass';
import { Cover } from '../src/components/Cover';
import { whenLabel, whenStartsAt } from '../src/components/WhenPicker';
import { IconCalendar, IconPin } from '../src/components/icons';
import { deviceTz } from '../src/intent';
import { DockAction } from '../src/components/DockAction';
import { useVoiceMessage, VoiceMessageControl } from '../src/voice';
import { VideoNoteButton } from '../src/videonote';

/**
 * Цвета имён — роли author/1..3 палитры борда (фиолетовый, оранжевый, малиновый). Цвет держится
 * за человеком по порядку прихода в группу, организатор — третьим: так на борде у всех сторон
 * Jane фиолетовая, Marc оранжевый, Mateo малиновый, кто бы ни смотрел.
 */
const AUTHOR = ['#5F32DC', '#DC7032', '#DC32A3'];
/** Серый системных строк и «You» в них — muted-foreground палитры. */
const MUTED_INK = '#5A616E';

type GMsg = { id?: string; frm?: string; text?: string; t?: number; kind?: string; voice?: VoicePayload;
  /** Событие ленты кодом и фактами — по нему строка собирается на языке читающего. */
  sys?: GroupSys };

/** Лента комнаты и лента переписки — один компонент; форма приводится на входе (см. roomMsg). */
type Row = Msg;

export default function GroupRoom() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх композера — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  const params = useLocalSearchParams<{ gid?: string; act?: string }>();
  const gid = String(params.gid || '').trim();
  const me = String(st.profile.name || '');

  const [g, setG] = useState<GroupInfo | null>(null);
  const [msgs, setMsgs] = useState<Row[]>([]);
  const [picked, setPicked] = useState<Row | null>(null);
  /** MSG.13a/14: кого я заблокировал — их реплики скрыты у меня во всех группах. */
  const [blocked, setBlocked] = useState<string[]>([]);
  const [blockAsk, setBlockAsk] = useState<{ name: string; id: string } | null>(null);
  /** MSG.10a/12: чат без уведомлений — та же локальная пометка, что ставит лист «Сообщений». */
  const mutedKey = 'g:' + gid;
  const muted = (st.msg?.muted || []).includes(mutedKey);
  const toggleMute = () => setMsgPrefs((m) => {
    const cur = new Set(m.muted || []);
    if (cur.has(mutedKey)) cur.delete(mutedKey); else cur.add(mutedKey);
    return { ...m, muted: [...cur] };
  });
  const [replyTo, setReplyTo] = useState<Row | null>(null);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [fatal, setFatal] = useState('');
  const [info, setInfo] = useState(false);
  /** «⋮» — меню группы (GR.18a/GR.21a); «Remove someone» — выбор человека (GR.24a). */
  const [menu, setMenu] = useState(false);
  const [removePick, setRemovePick] = useState(false);
  const [reasonOpen, setReasonOpen] = useState(false);
  /** GR.25 — «Send the plan?»: лист, отправка и её ошибка. */
  const [sendOpen, setSendOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState('');
  const [leaveAsk, setLeaveAsk] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [endAsk, setEndAsk] = useState(false);
  const [ending, setEnding] = useState(false);
  /** GR.51: member, selected closed-list reason, and the one in-flight destructive request. */
  const [removeWho, setRemoveWho] = useState('');
  /** id удаляемого: по подписи из двух «Иванов» в группе убрался бы не тот (docs/IDENTITY.md). */
  const [removeWhoId, setRemoveWhoId] = useState('');
  // Свой id — «я ли это» в составе и ленте решается по нему. Пришёл — перерисовать.
  const [, setMeKnown] = useState('');
  useEffect(() => { ensureMe().then(setMeKnown); }, []);
  const [removeReason, setRemoveReason] = useState<GroupRemovalReason | ''>('');
  const [removing, setRemoving] = useState(false);
  /** GR.19/GR.20: спрашиваю я или спрашивают меня — два листа поверх одного экрана. */
  const [ask1to1, setAsk1to1] = useState(false);
  const leftForOneOnOne = useRef(false);
  const [busy1to1, setBusy1to1] = useState(false);
  const [adopting, setAdopting] = useState(false);
  /** Крестик у нижнего действия (GR.18/GR.21): убрать подсказку до следующего входа в чат. */
  const [ctaHidden, setCtaHidden] = useState(false);
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
  // Между людьми голосовое уходит и без расшифровки: сообщение — это звук, текст лишь подсказка.
  const voice = useVoiceMessage(deliverVoice, !me || !gid || !!fatal || readOnly, { requireTranscript: false });

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
      // Группа открыта — счётчик её строки в «Сообщениях» гаснет (MSG.01).
      markSeen('g:' + gid);
      // Спрашивавшая сторона ждёт здесь, и ответ приходит опросом. Как только группа стала
      // один-на-один — уводим и её: иначе организатор остаётся в комнате, которой уже нет, и
      // «согласился» выглядит как «ничего не ответил».
      //
      // Один раз и только на ПЕРЕХОД, а не на состояние: сторожок нужен потому, что опрос идёт
      // дальше, и без него replace повторялся бы каждые несколько секунд, забивая переписку.
      if (!r?.group?.read_only && r?.group?.state === 'converted_1to1' && !leftForOneOnOne.current) {
        const m = (r.group.members || []).find(
          (x: any) => String(x?.name || '') && !isMe(x?.name, pidOf(x, 'name'), me));
        const peer = String(m?.name || '');
        if (peer) {
          leftForOneOnOne.current = true;
          router.replace({ pathname: '/conversation',
                           params: { who: peer, who_id: pidOf(m, 'name'), photo: String(m?.photo || '') } });
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

  /**
   * ДРУГАЯ ГРУППА — ЧИСТЫЙ ЭКРАН. Маршрут единственный (`dangerouslySingular` в _layout): переход
   * из одной группы в другую, например по пушу, приходит в ТОТ ЖЕ экран с новым `gid`. Раньше
   * лента, отсечка опроса и даже «группы больше нет» оставались от прежней — и новые сообщения
   * подклеивались к чужой переписке.
   */
  const shownGid = useRef(gid);
  useEffect(() => {
    if (shownGid.current === gid) return;
    shownGid.current = gid;
    since.current = 0;
    setMsgs([]); setG(null); setFatal(''); setErr(''); setLoading(true);
    setPicked(null); setReplyTo(null); setCtaHidden(false);
    leftForOneOnOne.current = false;
  }, [gid]);

  useEffect(() => { load(); }, [load]);

  /**
   * Вернулись со страницы «Who's in» (GR.24) за действием — открыть его лист: удаление (GR.24a),
   * закрытие (GR.24b) или выход. Один раз на приход: параметр снимается, иначе лист открывался бы
   * заново при каждой перерисовке.
   */
  useEffect(() => {
    const act = String(params.act || '');
    if (!act) return;
    // Без отмены по смене параметра: снятие `act` ниже само перезапускает эффект, и отмена в
    // очистке гасила открытие листа раньше, чем оно успевало случиться.
    setTimeout(() => {
      if (act === 'remove') { setRemoveWho(''); setRemoveWhoId(''); setRemovePick(true); }
      else if (act === 'end') setEndAsk(true);
      else if (act === 'leave') setLeaveAsk(true);
      // GR.40f «Open the spot»: поиск людей в эту группу — когда группа уже загружена (интент нужен).
      else if (act === 'invite') setWantInvite(true);
    }, 350);
    router.setParams({ act: '' } as any);
  }, [params.act]);
  const [wantInvite, setWantInvite] = useState(false);

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
      const r: any = await gapi.remove(gid, me, { name: removeWho, id: removeWhoId }, removeReason, newIdem('grm'));
      if (!r?.ok) { setErr(ROOM.removeFailed()); return; }
      setReasonOpen(false);
      setRemoveWho('');
      setRemoveWhoId('');
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
      if (agree && r?.with) { toOneOnOne(String(r.with), String(r.with_id || '')); return; }
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
  const toOneOnOne = (who: string, whoId = '') => {
    const m = ((g as any)?.members || []).find((x: any) => (whoId && pidOf(x, 'name')
      ? pidOf(x, 'name') === whoId
      : String(x?.name || '').toLowerCase() === who.toLowerCase()));
    router.replace({ pathname: '/conversation',
                     params: { who, who_id: whoId || pidOf(m, 'name'), photo: String(m?.photo || '') } });
  };

  /** Второй в группе — тот, кого спрашивают. Их двое, иначе кнопки перехода не бывает. */
  const otherName = String((((g as any)?.members || [])
    .find((m: any) => String(m?.name || '') && !isMe(m?.name, pidOf(m, 'name'), me)) || {}).name || '');
  /**
   * Спросили МЕНЯ — лист GR.20 открывается сам: это вопрос, а не уведомление.
   * Адресат обязан быть НЕПУСТЫМ: пока имя профиля не подгрузилось, `me` — пустая строка, и без
   * этой проверки «никого не спрашивали» совпадало с «спросили тебя» ('' === ''). Лист «___
   * предлагает перейти в один на один» с пустым именем открывался сам на любой группе.
   */
  /**
   * Листы, которые открываются САМИ (GR.20), — только пока экран на виду. Системное окно рисуется
   * поверх всего приложения, и экран группы, оставшийся в стопке под планом, выставлял свой лист
   * поверх чужого экрана.
   */
  const focused = useIsFocused();
  // GR.40f «Open the spot» из плана: поиск людей в эту группу, как только она загружена.
  useEffect(() => {
    if (!wantInvite || !g || !focused) return;
    setWantInvite(false);
    inviteMore();
  }, [wantInvite, g, focused]);
  const askTo = String((g as any)?.pending_1to1?.to || '').trim().toLowerCase();
  const askedMe = focused && !readOnly && !!askTo && isMe(askTo, (g as any)?.pending_1to1?.to_id, me);

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
  const others = members.filter((m) => String(m.name || '') && !isMe(m.name, pidOf(m, 'name'), me))
    .map((m) => String(m.name || ''));
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
  const max = Number(g?.max_total || min);
  const iOwnRaw = !!g?.i_am_owner;
  const ended = g?.read_only_reason === 'group_closed';
  /**
   * Строка под названием в карточке затеи — два куска, как на борде: серый счёт «2/3 in the
   * group» и рядом зелёный призыв «Make the plan now», когда план можно составлять (GR.21).
   * Закрытая группа — «Group ended» (GR.24c).
   */
  const barCount = hybridPlan ? headCount : ROOM.barCount(n, min, max);
  /**
   * СМЕНА ОРГАНИЗАТОРА (GR.21b/21c): когда организатор молчит 12 ч, над полем — «Offer to take
   * over»; когда тебе предложили роль — «See the offer»; идёт голосование за перехват — к нему.
   * Ведёт на страницу роли (app/grole.tsx). Важнее кнопки плана: без организатора плана не будет.
   */
  const gx: any = g || {};
  const roleCta = readOnly ? '' : gx.role_offer?.state === 'open' && isMe(gx.role_offer.to, gx.role_offer.to_id, me) ? ROLE.seeOffer()
    : gx.takeover?.state === 'open' && (iOwnRaw || gx.takeover.i_vote || isMe(gx.takeover.by, gx.takeover.by_id, me)) ? ROLE.seeVote()
    : gx.can_take_over ? ROLE.offerTakeOver() : '';
  const openRole = (pick = false) => router.navigate({ pathname: '/grole', params: pick ? { gid, pick: '1' } : { gid } });
  const planSet = !roleCta && !!groupPlan && ['confirmed', 'locked', 'done'].includes(String(groupPlan.state || ''));
  const barCall = ended ? ''
    // Полоса затеи зовёт к тому же, что кнопка над полем (GR.21b «Offer to take over», GR.21c «See
    // the offer»): пока роль в движении, «Make the plan now» — не то, что человеку сейчас делать.
    : roleCta ? roleCta
    : canPlan && !groupPlan ? ROOM.barMakePlan()
    // GR.57: план назначен — рядом со счётом его время; пока согласуют — «Plan in progress».
    : groupPlan && ['confirmed', 'locked', 'done'].includes(String(groupPlan.state || '')) ? String(groupPlan.when || '')
    : groupPlan ? ROOM.barPlanOn() : '';
  /** Содержимое карточки затеи: обложка кружком, название, счётчик состава. */
  const intentBody = (
    <>
      <View style={s.intentCover}>
        <Cover intent={g || {}} style={StyleSheet.absoluteFill} />
      </View>
      <View style={s.intentText}>
        <Text style={[s.intentTitle, { fontFamily: labelFamily(lang) }]} numberOfLines={1}>{g?.title || ''}</Text>
        <View style={s.intentMeta}>
          {/* GR.57: план назначен — зелёным счёт состава («3/3 in the group»), время серым; иначе
              счёт серый, а зелёный — призыв («Make the plan now», GR.21). */}
          <Text style={[s.intentSub, planSet && !ended && s.intentSet]} numberOfLines={1}>{ended ? ROOM.barEnded() : barCount}</Text>
          {barCall ? <Text style={[s.intentSub, !planSet && s.intentCall]} numberOfLines={1}>{barCall}</Text> : null}
        </View>
      </View>
    </>
  );

  /**
   * Люди комнаты по порядку прихода, вместе с ушедшими: цвет имени держится за человеком, а
   * реплики ушедшего остаются в ленте.
   */
  const everyone = useMemo(() => {
    const all = [...members, ...(((g as any)?.departed || []) as { name?: string; photo?: string }[])];
    // По времени прихода, а не «сначала оставшиеся»: иначе после удаления Jane её цвет уезжал к Marc.
    return all.map((x, i) => ({ x, i })).sort((a, b) =>
      (Number((a.x as any).joined || 0) - Number((b.x as any).joined || 0)) || a.i - b.i).map((r) => r.x);
  }, [g]);
  const idxOf = (name?: string, id?: string) => everyone.findIndex((x) => (id && pidOf(x, 'name')
    ? pidOf(x, 'name') === id
    : String(x.name || '').trim().toLowerCase() === String(name || '').trim().toLowerCase()));
  const inkOf = (name?: string, id?: string) => AUTHOR[(Math.max(0, idxOf(name, id)) + 2) % AUTHOR.length];
  const authorOf = (m: Row) => {
    const i = idxOf(m.from, (m as any).from_id);
    return { color: inkOf(m.from, (m as any).from_id), photo: i >= 0 ? String(everyone[i].photo || '') : '' };
  };
  const owner = String(g?.owner || '');
  const iOwn = !!g?.i_am_owner;
  const sysNames = [
    ...everyone.filter((x) => String(x.name || '') && !isMe(x.name, pidOf(x, 'name'), me))
      .map((x) => ({ name: String(x.name), color: inkOf(x.name, pidOf(x, 'name')) })),
    { name: ROOM.youWord(), color: MUTED_INK },
  ];
  /** Кто спрашивал про один на один — нужно строке «Jane agreed», у сервера она без имён. */
  const asker = useMemo(() => {
    const last = [...msgs].reverse().find((m) => (m as any).sys?.code === 'convert_asked');
    return String((last as any)?.sys?.who || '');
  }, [msgs]);
  /**
   * Строка события — по коду и с тем, кто на неё смотрит: «You asked Jane to switch…» у
   * спросившего, «Mateo removed Jane» у третьего. Сервер пишет факты, лица расставляет экран.
   */
  const sysLine = (m: Row): string => {
    const f = ((m as any).sys || {}) as any;
    const who = String(f.who || '');
    const mine = !!who && isMe(who, f.who_id, me);
    const other = (x: string) => String((members.find((y) => String(y.name || '') && String(y.name) !== x) || {}).name || '');
    switch (f.code) {
      case 'created': return ROOM.sysCreated(owner, String(g?.title || ''), iOwn, String((g as any)?.mode || '') === 'online');
      case 'read_only_now': return ROOM.sysReadOnly();
      case 'quorum_reached': case 'group_full': return '';
      case 'joined': return mine ? ROOM.sysJoinedMe() : ROOM.sysJoined(who);
      case 'convert_asked': {
        const whom = other(who);
        return ROOM.sysAsked(who, whom, mine, !mine && isMe(whom, '', me));
      }
      case 'converted': {
        const agreed = other(asker);
        return ROOM.sysAgreed(agreed, !!agreed && isMe(agreed, '', me));
      }
      case 'convert_declined': return mine ? ROOM.sysKeepMe() : ROOM.sysConvertDeclined(who);
      case 'removed': return ROOM.sysRemovedBy(owner, who, iOwn);
      case 'group_closed': return ROOM.sysEnded(who || owner, mine || (!who && iOwn));
      // Смена организатора (GR.42–44).
      case 'organiser_silent': return ROLE.sysSilent(who, Number(f.hours || 12));
      case 'takeover_offered': return ROLE.sysOffered(who, mine);
      case 'takeover_passed': case 'role_taken': return ROLE.sysPassed(who, mine);
      case 'takeover_failed': return ROLE.sysFailed(String(f.owner || owner));
      case 'takeover_stopped': return ROLE.sysStopped(who);
      case 'takeover_withdrawn': return ROLE.sysWithdrawn(who);
      case 'role_offered': return ROLE.sysRoleOffered(who, String(f.to || ''), isMe(f.to, f.to_id, me));
      // Конец паузы «вас двое» (GR.40a–40e).
      case 'hold_ask': return GPLAN.sysHoldAsk();
      case 'hold_one_on_one': return GPLAN.sysHoldOneOnOne(who, mine);
      case 'hold_let_go': return GPLAN.sysHoldLetGo(who, mine);
      case 'hold_expired': return GPLAN.sysHoldExpired();
      case 'role_declined': return ROLE.sysRoleDeclined(who, String(f.owner || owner), mine, iOwn);
      default: return groupSysLine(String(m.text || ''), f);
    }
  };
  /**
   * Лента для показа. Две строки сервера борд не рисует («enough people», «group is full»: об этом
   * уже говорит карточка затеи), двух не хватает: «You created … meetup» в начале (GR.18) и «The
   * chat is read-only now» сразу за закрытием (GR.24c).
   */
  useEffect(() => {
    if (!me) return;
    agent.safety(me).then((r: any) => setBlocked(((r?.blocked || []) as string[]).map((x) => String(x).trim().toLowerCase())))
      .catch(() => {});
  }, [me]);
  const isBlocked = (name?: string) => !!name && blocked.includes(String(name).trim().toLowerCase());
  const doBlock = async () => {
    const who = blockAsk;
    setBlockAsk(null);
    if (!who) return;
    try {
      const r: any = await agent.block(me, { name: who.name, id: who.id } as any, true);
      if (!r?.ok) throw new Error();
      setBlocked((b) => [...b, who.name.trim().toLowerCase()]);
    } catch {
      setErr(ROOM.offline());
    }
  };

  const feed = useMemo(() => {
    const out: Row[] = [];
    const created = Number((g as any)?.created || 0);
    if (created && g?.title) out.push({ id: 'sys-created', from: '', text: '', t: created, sys: { code: 'created' } as any });
    for (const m of msgs) {
      // MSG.14b: реплика заблокированного — строкой «X’s message is hidden».
      out.push(!m.sys && !isMe(m.from, (m as any).from_id, me) && isBlocked(m.from) ? { ...m, text: '', hidden: true } : m);
      if ((m as any).sys?.code === 'group_closed') {
        out.push({ id: `${m.id || m.t}-ro`, from: '', text: '', t: m.t, sys: { code: 'read_only_now' } as any });
      }
    }
    return out;
  }, [msgs, (g as any)?.created, g?.title, blocked, me]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Дата и время затеи, как их выбрали в мастере, — из них GR.25 предлагает план. */
  const planWhen = (g as any)?.date_key && Number.isFinite(Number((g as any)?.minutes))
    ? { date: String((g as any).date_key), minutes: Number((g as any).minutes), tz: deviceTz() } : null;
  const sendWhen = ((): [string, string] => {
    const label = planWhen ? whenLabel(planWhen) : String(g?.when || '');
    const m = label.match(/^(.*?)\s*(?:·|,)\s*(\d{1,2}[:.]\d{2}(?:\s*[AaPp][Mm])?)$/);
    return m ? [m[1], m[2]] : [label, ''];
  })();
  const sendPlan = async () => {
    if (!planWhen || sending) return;
    setSending(true); setSendErr('');
    try {
      const r: any = await gapi.planBegin(gid, me, {
        when: whenLabel(planWhen), starts_at: whenStartsAt(planWhen), place: String(g?.area || ''),
      }, newIdem('gpb'));
      if (!r?.ok) {
        setSendErr(r?.error === 'TOO_LATE' ? GPLAN.tooLate() : r?.error === 'PLAN_EXISTS' ? GPLAN.planExists() : GPLAN.createFailed());
        return;
      }
      setSendOpen(false);
      await load();
      router.navigate({ pathname: '/gplan', params: { gid } });
    } catch {
      setSendErr(GPLAN.createFailed());
    } finally {
      setSending(false);
    }
  };

  /** «Group info» и нажатие на шапку — страница состава GR.24 (Who's in), а не лист. */
  const openInfo = () => router.navigate({ pathname: '/gmembers', params: { gid } });

  if (fatal) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/* Фон — ровный «Ambient · glass pilot» #F5F1EC (s.wrap), без пятен: так на новом борде раздела A (6864:115809), как и в мастере создания. */}
        <View style={s.head}>
          <GlassBack label={T('Назад', 'Back', 'Atrás')}
                     onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))} />
          <Text style={[s.headTitle, s.headTitleLeft, { fontFamily: labelFamily(lang) }]}>{ROOM.gone()}</Text>
        </View>
        <Text style={s.fatal}>{fatal}</Text>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/* Фон — ровный «Ambient · glass pilot» #F5F1EC (s.wrap), без пятен: так на новом борде раздела A (6864:115809), как и в мастере создания. */}
        {/*
          Верхняя карточка затеи — на кадре GR.18 их ДВЕ шапки, и эта была пропущена целиком.
          Её стрелка вправо ведёт к плану: из чата туда попадали только нижней кнопкой, а она
          видна лишь при полном составе — то есть с GR.18, где людей двое, к плану не было хода
          вовсе, хотя стрелка на кадре есть.

          Живой она делается ТОЛЬКО когда за ней что-то есть: план уже создан или состав дорос до
          планирования. Иначе стрелка обещала бы переход, за которым пусто, — а это хуже, чем её
          отсутствие: человек жмёт и решает, что приложение сломано.
        */}
        {planReachable || ended ? (
          <Pressable accessibilityRole="button" style={s.intentBar}
                     accessibilityLabel={ended ? ROOM.closedPageTitle() : (g as any)?.plan ? ROOM.openPlan() : ROOM.createPlan()}
                     /* Закрытая группа ведёт на свою страницу (GR.54), живая — к плану. */
                     onPress={() => (ended ? openInfo() : router.navigate({ pathname: '/gplan', params: { gid } }))}>
            <GlassSurface tone="light" radius={999} pointerEvents="none" style={s.intentGlass}>
              {intentBody}
              <IconChevronRight size={22} c={color.fg} />
            </GlassSurface>
          </Pressable>
        ) : (
          /* Та же карточка, но БЕЗ стрелки: за ней пока ничего нет, и обещать переход нельзя. */
          <View style={s.intentBar}>
            <GlassSurface tone="light" radius={999} style={s.intentGlass}>{intentBody}</GlassSurface>
          </View>
        )}

        {/*
          ШАПКА КОМНАТЫ (GR.18): стеклянная «назад», по центру — с кем ты («Jane and you») и
          янтарная метка «нужен ещё один», справа — стопка лиц. Название затеи живёт в карточке
          над шапкой, поэтому здесь его нет: две строки одного и того же спорили бы друг с другом.
        */}
        <View style={s.head}>
          <View style={s.headSide}>
            <GlassBack label={T('Назад', 'Back', 'Atrás')}
                       onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))} />
          </View>
          {/* Заголовок — не подпись, а вход: за ним стоит затея, ради которой всё собралось,
              и посмотреть её больше негде. */}
          <Pressable style={s.headMid} accessibilityRole="button"
                     accessibilityLabel={ROOM.infoTitle()} onPress={() => openInfo()}>
            <Text style={[s.headTitle, { fontFamily: labelFamily(lang) }]} numberOfLines={1}>{ROOM.who(others)}</Text>
            {/* Янтарная метка — только пока не хватает людей (GR.18). Собранная группа
                обходится без метки: об этом уже говорит «3/3» в карточке сверху (GR.21). */}
            {!readOnly && n < min ? (
              <View style={s.needPill}>
                <Text style={s.needText} numberOfLines={1}>{ROOM.needMore(min - n)}</Text>
              </View>
            ) : null}
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={ROOM.infoTitle()}
                     style={[s.headSide, s.headRight]} onPress={() => openInfo()}>
            {/* Стопка лиц — все, кто в комнате, ты последним (GR.21: Jane, Marc, ты). */}
            {[...members.filter((m) => !isMe(m.name, pidOf(m, 'name'), me)),
              ...members.filter((m) => isMe(m.name, pidOf(m, 'name'), me))].slice(0, 4).map((m, i) => (
              <View key={String(m.name || '') + i} style={[s.stackAv, i > 0 && { marginLeft: -8 }]}>
                <IconPerson size={14} />
                {m.photo ? (
                  <Image source={{ uri: mediaUrl(String(m.photo)) }} style={[s.stackAvImg, StyleSheet.absoluteFill]} />
                ) : null}
              </View>
            ))}
          </Pressable>
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
          {loading && !msgs.length ? <ActivityIndicator style={{ marginTop: 24 }} color={color.primary} /> : null}
          {readOnly && !ended ? (
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
          {/* MSG.12 — чат без уведомлений: плашка над лентой. */}
          {muted && !readOnly ? (
            <View style={[s.removedNotice, s.mutedNotice]}>
              <IconBellOff size={20} c={color.muted} />
              <View style={{ flex: 1 }}>
                <Text style={s.mutedTitle}>{MSG.mutedBanner()}</Text>
                <Text style={s.removedNoticeSub}>{MSG.mutedBannerNote()}</Text>
              </View>
            </View>
          ) : null}
          <MessageFeed
            msgs={feed}
            me={me}
            ru={getLang() === 'ru'}
            showAuthor
            authorOf={authorOf}
            sysNames={sysNames}
            sysText={sysLine}
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
        <Sheet visible={ask1to1} onClose={() => setAsk1to1(false)} title={ROOM.switchTitle()}>
          <SheetText lead={ROOM.askTitle(otherName)} note={ROOM.switchNote(otherName, (g?.invites || []).length)} />
          <GlassPill tone="brand" style={s.sheetBtn} busy={busy1to1} label={ROOM.askSend(otherName)} onPress={askSwitch} />
          <GlassPill tone="dark" style={s.sheetBtn} label={ROOM.keepGroup()} onPress={() => setAsk1to1(false)} />
        </Sheet>

        <Sheet visible={askedMe} onClose={() => answerSwitch(false)} title={ROOM.switchTitle()}>
          <SheetText lead={ROOM.answerTitle(String((g as any)?.pending_1to1?.by || ''))} note={ROOM.answerNote2()} />
          <GlassPill tone="brand" style={s.sheetBtn} busy={busy1to1} label={ROOM.agree()} onPress={() => answerSwitch(true)} />
          <GlassPill tone="dark" style={s.sheetBtn} disabled={busy1to1} label={ROOM.keepGroup()} onPress={() => answerSwitch(false)} />
        </Sheet>

        {/* MSG.08 / MSG.13a — лист реплики: чья и когда, затем действия. */}
        <Sheet visible={!!picked && !readOnly} onClose={() => setPicked(null)}
               title={picked ? (isMe(picked.from, (picked as any).from_id, me)
                 ? CHAT.yourMsgAt(msgTime(picked.t, getLang() === 'ru'))
                 : CHAT.theirMsgAt(String(picked.from || ''), msgTime(picked.t, getLang() === 'ru'))) : undefined}>
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
              icon={<IconCopy size={20} c={color.primary} />}
              label={CHAT.copyText()}
              onPress={async () => {
                await Clipboard.setStringAsync(String(picked?.text || ''));
                setPicked(null);
              }}
            />
          ) : null}
          <SheetItem label={CHAT.reply()} onPress={() => { setReplyTo(picked); setPicked(null); }} />
          {picked && isMe(picked.from, (picked as any).from_id, me) ? (
            <SheetItem icon={<IconTrash size={20} c={color.danger} />} label={CHAT.deleteMsg()} danger
                       note={CHAT.deleteSeenBy(joinNames(others.filter(Boolean), T('и', 'and', 'y')))}
                       onPress={() => picked && removeMsg(picked)} />
          ) : picked && picked.from ? (
            <>
              <SheetItem icon={<IconFlag size={20} c={color.primary} />} label={CHAT.reportMsg()} note={CHAT.reportMsgNote()}
                         onPress={() => {
                           const m = picked;
                           setPicked(null);
                           setTimeout(() => router.navigate({ pathname: '/group-report', params: {
                             gid, title: String(g?.title || ''), about: String(m.from || ''), about_id: String((m as any).from_id || ''),
                             quote: String(m.text || '').slice(0, 300), quote_at: String(m.t || ''),
                           } }), 250);
                         }} />
              <SheetItem icon={<IconBan />} danger label={CHAT.blockWho(String(picked.from))} note={CHAT.blockWhoNote()}
                         onPress={() => {
                           const m = picked;
                           setPicked(null);
                           setTimeout(() => setBlockAsk({ name: String(m.from || ''), id: String((m as any).from_id || '') }), 250);
                         }} />
            </>
          ) : null}
        </Sheet>

        {/* MSG.14 — блокировка из группы: подтверждение. */}
        <Sheet visible={!!blockAsk} onClose={() => setBlockAsk(null)} title={blockAsk ? CHAT.blockAsk(blockAsk.name) : undefined}>
          <SheetText lead={CHAT.blockAskLead()} note={CHAT.blockAskNote(String(g?.title || ''))} />
          <GlassPill tone="brand" style={s.sheetBtn} label={blockAsk ? CHAT.blockWho(blockAsk.name) : ''} onPress={doBlock} />
          <GlassPill tone="dark" style={s.sheetBtn} label={CHAT.notNow()} onPress={() => setBlockAsk(null)} />
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
          /* Закрытая группа — без поля ввода, кнопки плана и «⋮» (GR.24c): что чат только для
             чтения, говорит последняя строка ленты. Удалённому — прежняя подпись внизу. */
          ended ? <View style={{ height: dockBottom(insets.bottom, kb) }} /> : (
            <View style={[s.readOnlyDock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
              <Text style={s.readOnlyDockText}>{ROOM.readOnlyHistory()}</Text>
            </View>
          )
        ) : (
        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          {/*
            Нижнее действие — ровно то, что на кадре для этого состава, и стоит оно НАД полем
            ввода, с крестиком слева (GR.18/GR.21):
              трое и больше (GR.21) — «Создать план», коралловая;
              их двое (GR.18)       — «Перейти в один на один», стеклянная.
            Показывать её или нет, решает сервер флагом `can_convert` (их двое, плана нет, группа
            жива), а не экран: разойдись условия — кнопка обещала бы то, на что придёт отказ.
            Крестик убирает подсказку до следующего входа: к плану ведёт и карточка сверху.
          */}
          {!ctaHidden && roleCta ? (
            <DockAction compact tone="brand" label={roleCta} onPress={() => openRole()}
                        onDismiss={() => setCtaHidden(true)} dismissLabel={T('Скрыть', 'Hide', 'Ocultar')} />
          ) : !ctaHidden && ((canPlan && (iOwn || groupPlan)) || (g as any)?.can_convert) ? (
            <DockAction
              compact
              tone={canPlan ? 'brand' : 'light'}
              /* GR.21 → GR.25: полный состав ведёт на экран плана. Подпись меняется, когда план уже
                 есть: «Создать» тогда врало бы — второго плана у группы не бывает. */
              label={canPlan ? ((g as any)?.plan ? ROOM.openPlan() : ROOM.createPlan()) : ROOM.switchTo1to1()}
              onPress={canPlan
                ? (groupPlan ? () => router.navigate({ pathname: '/gplan', params: { gid } }) : () => { setSendErr(''); setSendOpen(true); })
                : () => setAsk1to1(true)}
              onDismiss={() => setCtaHidden(true)}
              dismissLabel={T('Скрыть', 'Hide', 'Ocultar')}
            />
          ) : null}

          {/*
            Композер — компонент «Chat/Composer» (💣 UI, 6164:19536), он же на GR.18: «⋮» в стеклянном
            круге 48 — меню группы, рядом стеклянное поле 48, в нём отправка стеклянным кругом 44.
          */}
          <View style={s.composerRow}>
            <GlassIconButton size={48} label={ROOM.optionsTitle()} onPress={() => setMenu(true)}>
              <IconEllipsisV size={30} />
            </GlassIconButton>
            <View style={s.fieldBox}>
              <GlassSurface tone="light" radius={999}
                style={[s.field, voice.phase === 'idle' && draft.trim() ? s.fieldSending : null]}>
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
        </View>
        )}

        {/* GR.25 — «Send the plan?»: план из времени и места затеи, одним нажатием. «Change» ведёт в
            форму плана, уже заполненную этими же значениями. */}
        <Sheet visible={sendOpen} onClose={() => setSendOpen(false)} title={ROOM.sendTitle()}>
          <View style={s.sendCard}>
            <GlassSurface tone="light" radius={20} style={{ overflow: 'hidden' }}>
              <Cover intent={g || {}} style={s.sendCover} />
              <View style={s.sendBody}>
                {/* Дата и время раздельно, у каждого свой знак — как на карточке плана. */}
                <View style={s.sendRow}>
                  <IconCalendar size={18} c={color.primary} />
                  <Text style={[s.sendLine, { flex: 0 }]} numberOfLines={1}>{sendWhen[0] || '—'}</Text>
                  {sendWhen[1] ? (
                    <>
                      <IconClock size={18} c={color.primary} />
                      <Text style={s.sendLine} numberOfLines={1}>{sendWhen[1]}</Text>
                    </>
                  ) : null}
                </View>
                <View style={s.sendRow}>
                  <IconPin size={18} c={color.primary} />
                  <Text style={s.sendLine} numberOfLines={1}>{String(g?.area || '') || ROOM.aboutUnset()}</Text>
                </View>
              </View>
            </GlassSurface>
          </View>
          <SheetText note={sendErr || (planWhen ? ROOM.sendNote(ROOM.andList(others)) : ROOM.sendNoTime())} />
          {planWhen ? (
            <GlassPill tone="brand" style={s.sheetBtn} busy={sending} label={ROOM.sendGo()} onPress={sendPlan} />
          ) : null}
          <GlassPill tone="dark" style={s.sheetBtn} disabled={sending} label={ROOM.sendChange()}
                     onPress={() => { setSendOpen(false); router.navigate({ pathname: '/gplan', params: { gid, edit: '1' } }); }} />
        </Sheet>

        {/*
          «⋮» — МЕНЮ ГРУППЫ (GR.18a двое, GR.21a трое). Пункты — ровно те, что сейчас можно
          сделать: «Invite more» — пока есть места, «Switch to one-on-one» — когда сервер разрешает
          переход (их двое, плана нет), «Remove someone» — пока плана нет, «End the group» — тоже.
          «Hand the role over» с борда здесь НЕ показан: передачи роли на сервере пока нет, а пункт,
          который ничего не делает, хуже отсутствующего.
        */}
        <Sheet visible={menu} onClose={() => setMenu(false)} title={ROOM.optionsTitle()}>
          <SheetItem icon={<IconInfo />} label={ROOM.optInfo()}
                     note={groupPlan && !iOwn ? MSG.whoAndPlan() : ROOM.optInfoNote(iOwn && !g?.full)}
                     onPress={() => { setMenu(false); setTimeout(openInfo, 250); }} />
          {/* MSG.10a — без уведомлений. */}
          {!readOnly ? (
            <SheetItem icon={muted ? <IconBell size={20} c={color.primary} /> : <IconBellOff size={20} c={color.primary} />}
                       label={muted ? MSG.unmuteNew() : MSG.muteAction()}
                       note={muted ? MSG.unmuteNote() : MSG.muteNoteNew()}
                       onPress={() => { setMenu(false); toggleMute(); }} />
          ) : null}
          {iOwn && !g?.full && !readOnly ? (
            <SheetItem icon={<IconUserPlus />} label={ROOM.inviteMore()}
                       note={ROOM.optInviteNote(Math.max(1, Number(g?.max_total || 3) - n))}
                       disabled={adopting}
                       onPress={() => { setMenu(false); inviteMore(); }} />
          ) : null}
          {(g as any)?.can_convert ? (
            <SheetItem icon={<IconGroups size={20} c={color.primary} />} label={ROOM.switchTo1to1()}
                       note={ROOM.optSwitchNote(otherName)}
                       onPress={() => { setMenu(false); setTimeout(() => setAsk1to1(true), 250); }} />
          ) : null}
          {/* Удаление — только в собранной группе (GR.21a). Когда их двое (GR.18a), вместо него
              переход в один на один: удалить второго значило бы остаться одному. */}
          {g?.can_remove || (iOwn && !groupPlan && !readOnly && n >= min && others.length > 0) ? (
            <SheetItem icon={<IconUserX />} label={ROOM.optRemove()} note={ROOM.optRemoveNote()}
                       onPress={() => { setMenu(false); setRemoveWho(''); setRemoveWhoId(''); setTimeout(() => setRemovePick(true), 250); }} />
          ) : null}
          {/* GR.21a «Hand the role over» — пока плана нет и есть кому отдать. */}
          {gx.can_hand_over && n >= min ? (
            <SheetItem icon={<IconCrown />} label={ROLE.optHandOver()} note={ROLE.optHandOverNote()}
                       onPress={() => { setMenu(false); setTimeout(() => openRole(true), 250); }} />
          ) : null}
          {!readOnly ? (
            <SheetItem icon={<IconAlertTriangle size={20} c={color.primary} />} label={iOwn ? ROOM.optReport() : MSG.reportGroup()}
                       note={iOwn ? ROOM.optReportNote() : MSG.reportNoteNew()}
                       onPress={() => {
                         setMenu(false);
                         setTimeout(() => router.navigate({
                           pathname: '/group-report', params: { gid, title: String(g?.title || '') },
                         }), 250);
                       }} />
          ) : null}
          {/* MSG.10a — выход последним и красным: кто узнает, видно сразу. */}
          {!readOnly && !iOwn ? (
            <SheetItem icon={<IconExit size={20} c={color.danger} />} danger label={MSG.leaveGroup()}
                       note={MSG.leaveGroupNote(others)}
                       onPress={() => { setMenu(false); setTimeout(() => setLeaveAsk(true), 250); }} />
          ) : null}
          {g?.can_end ? (
            <SheetItem icon={<IconBan />} danger label={ROOM.endGroup()} note={ROOM.optEndNote()}
                       onPress={() => { setMenu(false); setTimeout(() => setEndAsk(true), 250); }} />
          ) : null}
        </Sheet>

        {/* GR.24a — кого убрать: строки состава с галочкой у выбранного, потом причина (GR.51). */}
        <Sheet visible={removePick} onClose={() => { setRemovePick(false); setRemoveWho(''); setRemoveWhoId(''); }}
               title={ROOM.removeWhoTitle()}>
          <SheetText lead={ROOM.removeWhoLead()}>
            <View style={s.pickList}>
              {members.filter((m) => String(m.name || '') && !isMe(m.name, pidOf(m, 'name'), me)).map((m, i) => {
                const nm = String(m.name || '');
                const mid = pidOf(m, 'name');
                const on = removeWhoId ? removeWhoId === mid : removeWho === nm;
                const since = Number((m as any).joined || 0);
                return (
                  <Pressable key={nm + i} accessibilityRole="radio" accessibilityState={{ selected: on }}
                             style={[s.pickRow, on && s.rowOn]} onPress={() => { setRemoveWho(nm); setRemoveWhoId(mid); }}>
                    <View style={s.pickAv}>
                      <IconPerson size={18} />
                      {m.photo ? <Image source={{ uri: mediaUrl(String(m.photo)) }} style={[s.pickAv, StyleSheet.absoluteFill]} /> : null}
                    </View>
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={s.pickName} numberOfLines={1}>{ROOM.nameAge(nm, (m as any).age)}</Text>
                      {since ? (
                        <View style={s.sinceRow}>
                          <Text style={s.pickSub}>{ROOM.memberSince()}</Text>
                          <IconClock size={14} c={color.fg} />
                          <Text style={s.pickSub}>{clock(since)}</Text>
                        </View>
                      ) : null}
                    </View>
                    {on ? <IconCheck /> : null}
                  </Pressable>
                );
              })}
            </View>
          </SheetText>
          <SheetText note={ROOM.removeWhoNote()} />
          <GlassPill tone="brand" style={s.sheetBtn} disabled={!removeWho} label={ROOM.removeGo()}
                     onPress={() => { setRemovePick(false); setRemoveReason(''); setTimeout(() => setReasonOpen(true), 250); }} />
          <GlassPill tone="dark" style={s.sheetBtn} label={ROOM.cancelBtn()}
                     onPress={() => { setRemovePick(false); setRemoveWho(''); setRemoveWhoId(''); }} />
        </Sheet>

        {/* GR.51 — причина из закрытого списка. Свободного текста нет по замыслу: причину видит
            только модерация, и удалённый её не узнаёт. */}
        <Sheet visible={reasonOpen && !!removeWho}
               onClose={() => { setReasonOpen(false); setRemoveWho(''); setRemoveWhoId(''); setRemoveReason(''); }}
               title={ROOM.removeTitle(removeWho)}>
          <SheetText lead={ROOM.removeReasonLead()}>
            <View style={s.pickList}>
              {ROOM.removalReasons().map((r) => {
                const selected = removeReason === r.code;
                return (
                  <Pressable key={r.code} accessibilityRole="radio" accessibilityState={{ selected }}
                             style={[s.reasonRow, selected && s.rowOn]} onPress={() => setRemoveReason(r.code)}>
                    <Text style={s.reasonText}>{r.label}</Text>
                    {selected ? <IconCheck /> : null}
                  </Pressable>
                );
              })}
            </View>
          </SheetText>
          <SheetText note={ROOM.removeReasonNote(removeWho)} />
          <GlassPill tone="brand" style={s.sheetBtn} disabled={!removeReason} busy={removing}
                     label={ROOM.removeConfirm(removeWho)} onPress={removeMember} />
          <GlassPill tone="dark" style={s.sheetBtn} label={ROOM.cancelBtn()}
                     onPress={() => { setReasonOpen(false); setRemoveWho(''); setRemoveWhoId(''); setRemoveReason(''); }} />
        </Sheet>

        {/* GR.24b / GR.53 — закрыть группу. Главная кнопка — само действие, «Cancel» тёмная, как
            на борде; прежде было наоборот, и коралловым светилось «продолжить». */}
        <Sheet visible={endAsk} onClose={() => setEndAsk(false)} title={ROOM.endGroup()}>
          <SheetText lead={ROOM.endLead(String(g?.title || ''))} note={ROOM.endNote(ROOM.andList(others))} />
          <GlassPill tone="brand" style={s.sheetBtn} busy={ending} label={ROOM.endConfirm()}
                     onPress={ending ? undefined : endGroup} />
          <GlassPill tone="dark" style={s.sheetBtn} disabled={ending} label={ROOM.cancelBtn()}
                     onPress={ending ? undefined : () => setEndAsk(false)} />
        </Sheet>

        <LeaveSheet
          open={leaveAsk}
          busy={leaving}
          onYes={leave}
          onClose={() => setLeaveAsk(false)}
          bottomInset={insets.bottom}
          title={String(g?.title || '')}
          note={MSG.leaveGroupNote(others) + '.' + (groupPlan && n - 1 < min && !iOwn
            ? MSG.leaveDrops(n - 1, String(g?.owner || '')) : '')}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

/** «14:28» — время так же, как под пузырями ленты (формат часов — по языку устройства). */
const clock = (t: number) => msgTime(t, getLang() === 'ru');

/** Подтверждение выхода. Отдельным листом, потому что это единственное необратимое действие экрана. */
function LeaveSheet({
  open, busy, onYes, onClose, bottomInset, title, note,
}: {
  open: boolean; busy: boolean; onYes: () => void; onClose: () => void; bottomInset: number;
  title: string; note: string;
}) {
  // MSG.10b: кто узнает и что станет с планом — до нажатия, а не после.
  return (
    <Sheet visible={open} onClose={onClose} title={MSG.leaveAskTitle(title)}>
      <SheetText lead={MSG.cantUndo()} note={note} />
      <GlassPill tone="brand" style={s.sheetBtn} busy={busy} label={MSG.leaveGroup()} onPress={busy ? undefined : onYes} />
      <GlassPill tone="dark" style={s.sheetBtn} label={MSG.stay()} onPress={onClose} />
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
    marginHorizontal: 20, marginBottom: 6, paddingVertical: 8, paddingHorizontal: 12,
    borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.62)', borderWidth: 1, borderColor: '#FFFFFF',
  },
  replyStripe: { width: 2, alignSelf: 'stretch', borderRadius: 1, backgroundColor: color.primary },
  replyWho: { fontSize: 12, fontWeight: '700', color: color.primary } as any,
  replyText: { fontSize: 13, color: color.muted } as any,
  replyX: { fontSize: 16, color: color.muted },
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  /*
    ШАПКА GR.18: боковины одной ширины, чтобы «Jane and you» стояло точно по центру; справа
    стопка лиц 32 с белой кромкой, каждое следующее заходит на предыдущее.
  */
  head: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, height: 56 },
  headSide: { width: 84, flexDirection: 'row', alignItems: 'center' },
  headRight: { justifyContent: 'flex-end' },
  headMid: { flex: 1, alignItems: 'center', gap: 4 },
  headTitle: { fontSize: 15, lineHeight: 20, color: color.fg, textAlign: 'center' } as any,
  headTitleLeft: { flex: 1, textAlign: 'left' } as any,
  /** «need one more» — warning-subtle #FFE396, текст warning #FC8F00 (палитра борда). */
  needPill: { height: 16, paddingHorizontal: 8, borderRadius: 99, backgroundColor: '#FFE396', justifyContent: 'center', maxWidth: '100%' },
  needText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#FC8F00' } as any,
  stackAv: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: color.neutral100, overflow: 'hidden',
    borderWidth: 1.5, borderColor: 'rgba(255,255,255,0.67)', alignItems: 'center', justifyContent: 'center',
  },
  stackAvImg: { width: 32, height: 32, borderRadius: 16 },

  aboutHead: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 18, color: color.muted, marginTop: space.sm } as any,
  aboutBox: {
    borderRadius: 16, borderWidth: 1, borderColor: '#FFFFFF',
    backgroundColor: 'rgba(255,255,255,0.62)', paddingHorizontal: 14, paddingVertical: 4, gap: 2,
  },
  aboutRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 8 },
  aboutLabel: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.muted, width: 96 } as any,
  aboutValue: { fontFamily: font.text, fontSize: 14, lineHeight: 20, color: color.fg, flex: 1 } as any,

  // Карточка затеи над шапкой комнаты (GR.18): стеклянная пилюля 49 с обложкой-кружком 44.
  intentBar: { marginHorizontal: 16, marginBottom: 4, borderRadius: 999,
               shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } },
  intentGlass: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingLeft: 2, paddingRight: 10, height: 49 },
  intentCover: { width: 44, height: 44, borderRadius: 22, overflow: 'hidden', backgroundColor: 'rgba(255,255,255,0.42)' },
  intentTitle: { fontSize: 15, lineHeight: 18, color: color.fg } as any,
  intentText: { flex: 1, gap: 2 },
  /** Счёт и призыв — рядом через 8, оба Geist 500 11 (GR.21 «meta-row»). */
  intentMeta: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  intentSub: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 16, color: '#5A616E', flexShrink: 1 } as any,
  /** «Make the plan now» — success-accent #238C62. */
  intentCall: { color: '#238C62' },
  /** Назначенный план — счёт состава success-text #0F7340 (GR.57). */
  intentSet: { color: '#0F7340' },


  thread: { paddingHorizontal: 20, paddingTop: space.sm, paddingBottom: space.lg, gap: 4 },
  err: { ...type.bodySmall, color: color.primary, textAlign: 'center', marginTop: space.sm } as any,
  fatal: { ...type.body, color: color.muted, paddingHorizontal: 20, paddingTop: space.lg } as any,
  removedNotice: {
    marginHorizontal: 2, marginBottom: space.md, padding: 14,
    borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.62)', borderWidth: 1, borderColor: '#FFFFFF',
  },
  removedNoticeText: { ...type.body, color: color.fg } as any,
  removedNoticeSub: { ...type.caption, color: color.muted, marginTop: 6 } as any,
  mutedNotice: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  mutedTitle: { ...type.labelSmall, color: color.fg, fontWeight: '700' } as any,

  dock: { paddingHorizontal: 20, paddingTop: space.sm, gap: space.sm },
  readOnlyDock: { paddingHorizontal: 20, paddingTop: 14 },
  readOnlyDockText: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,
  ctaNote: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted, textAlign: 'center' } as any,
  composerRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  fieldBox: { flex: 1 },
  /** Поле — стекло 48 со скруглением во всю высоту; внутри ввод, голосовое и кружок. */
  field: { height: 48, flexDirection: 'row', alignItems: 'center', paddingLeft: 16, paddingRight: 12, gap: space.sm },
  /** С текстом справа 2: круг отправки 44 стоит почти у края поля, как в «Chat/Composer». */
  fieldSending: { paddingRight: 2 },
  input: { flex: 1, color: color.fg, fontFamily: font.text, fontSize: 15 },
  sheetNote: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#404652', paddingBottom: space.sm } as any,
  sheetBody: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#404652' } as any,
  sheetBtn: { height: 48 },

  memberRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 52 },
  memberAv: { width: 40, height: 40, borderRadius: rad.full },
  memberAvEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  memberNameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  memberName: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg, flexShrink: 1 } as any,
  orgBadge: { height: 16, paddingHorizontal: 8, borderRadius: 99, backgroundColor: '#CFE3FF', justifyContent: 'center' },
  orgText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#1F58BE' } as any,
  memberRole: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#5A616E' } as any,
  memberRemove: { ...type.caption, color: color.primary, fontWeight: '700' } as any,
  /** Карточка плана в листе GR.25: обложка 128 и под ней когда и где — как на странице плана. */
  sendCard: { borderRadius: 20, marginBottom: 16,
              shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 5 } },
  sendCover: { height: 128, backgroundColor: color.neutral100 },
  sendBody: { padding: 16, gap: 8 },
  sendRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  sendLine: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: color.fg, flex: 1 } as any,
  /** Списки выбора в листах (GR.24a, GR.51): строки через 4, от вопроса 12. */
  pickList: { gap: 4, marginTop: -12 },
  /** Строка человека: белое стекло 16%, поля 16/16/16/8, скругление 16; выбранная — 36%. */
  pickRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 16,
    paddingTop: 16, paddingBottom: 16, paddingRight: 16, paddingLeft: 8, backgroundColor: 'rgba(255,255,255,0.16)',
  },
  rowOn: { backgroundColor: 'rgba(255,255,255,0.36)' },
  pickAv: { width: 40, height: 40, borderRadius: 20, overflow: 'hidden', backgroundColor: color.neutral100,
            alignItems: 'center', justifyContent: 'center' },
  pickName: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  pickSub: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: color.fg } as any,
  sinceRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  /** Причина: поля 16, текст 13/20 Geist 600. */
  reasonRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 16,
               backgroundColor: 'rgba(255,255,255,0.16)' },
  reasonText: { flex: 1, fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.fg } as any,
});
