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
  ActivityIndicator, Modal, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { CHAT, THREAD, INVITE, UNDO_BAR, Msg, msgTime, msgDayLabel, planWhen } from '../src/chat';
import { inviteHoursLeft } from '../src/messages';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, markSeen, setMsgPrefs } from '../src/state';
import { agent } from '../src/api';
import {
  IconChevronLeft, IconSpark, IconPerson, IconCalendar, IconSend, IconDots, IconCheckCircle,
} from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

export default function Conversation() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
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
   */
  const merge = useCallback((incoming: Msg[]) => {
    if (!incoming.length) return;
    since.current = Math.max(since.current, ...incoming.map((m) => m.t || 0));
    setMsgs((prev) => {
      const out = [...prev];
      for (const m of incoming) {
        const dupe = out.findIndex(
          (x) => x.text === m.text
            && String(x.from || '').toLowerCase() === String(m.from || '').toLowerCase()
            && Math.abs((x.t || 0) - (m.t || 0)) < 30
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
      setErr('');
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
  useEffect(() => {
    const id = setInterval(loadSide, 15000);
    return () => clearInterval(id);
  }, [loadSide]);

  // «Прочитано» отправляется, когда на экране появились новые ЧУЖИЕ сообщения, а не на каждый опрос.
  useEffect(() => {
    const theirs = msgs.filter((m) => String(m.from || '').toLowerCase() !== me.toLowerCase()).length;
    if (theirs > readStamped.current) {
      readStamped.current = theirs;
      markSeen(other);
      agent.threadRead(me, other).catch(() => {});
    }
  }, [msgs.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Лёгкий опрос: собеседник отвечает не мгновенно, а держать сокет ради двух реплик избыточно.
  useEffect(() => {
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [msgs.length]);

  const send = async () => {
    const text = draft.trim();
    if (!text || !me || !other) return;
    setDraft('');
    // Показываем сразу, не дожидаясь сервера: опрос всё равно принесёт эту же строку, а ждать
    // секунду на собственном сообщении — значит выглядеть сломанным.
    const local: Msg = { from: me, to: other, text, t: Date.now() / 1000 };
    setMsgs((prev) => [...prev, local]);
    // `since` НЕ двигаем: пусть опрос принесёт серверную версию этой же реплики — merge её склеит
    // и заодно поправит время на настоящее. Сдвинуть здесь значило бы навсегда её пропустить.
    try {
      const r: any = await agent.message(me, other, text);
      if (!r?.ok) throw new Error(r?.error || 'send failed');
      setErr('');
    } catch {
      setErr(CHAT.offline());
    }
  };

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
        router.push({ pathname: '/plan', params: { who: other, title: intentTitle, photo } });
      } else {
        // Конец разговора: у сервера нет понятия «закрытый тред», поэтому завершение — это уход
        // с экрана. Полоса и была последним шансом остаться. Открытому по прямой ссылке экрану
        // некуда «назад» — тогда домой, иначе кнопка тихо не делала бы ничего.
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

  /** MSG.18–MSG.21: входящая заявка от этого человека, если её не скрывали. */
  const inviteIn = request && norm(request.from) === norm(other) ? request : null;
  const inviteHidden = (st.msg?.hiddenInvites || []).includes(String(inviteIn?.id || ''));
  const noNudge = (st.msg?.noNudge || []).includes(norm(other));
  const requestTitle = String(request?.intent?.title || (request?.intent?.topics || []).join(', ') || '');

  const hideInvite = () =>
    setMsgPrefs((m) => ({ ...m, hiddenInvites: [...(m.hiddenInvites || []), String(inviteIn?.id || '')] }));
  const muteNudge = () =>
    setMsgPrefs((m) => ({ ...m, noNudge: [...(m.noNudge || []), norm(other)] }));
  const toPlan = () =>
    router.push({ pathname: '/plan', params: { who: other, title: requestTitle || intentTitle, photo } });

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
            <Image source={{ uri: photo }} style={s.ava} />
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
            </View>
            {/* Пара участников, как на MSG.07: собеседник и я, внахлёст. */}
            <View style={s.pairWrap}>
              {photo ? (
                <Image source={{ uri: photo }} style={s.pairAva} />
              ) : (
                <View style={[s.pairAva, s.avaEmpty]}><IconPerson size={13} /></View>
              )}
              {st.profile.photo ? (
                <Image source={{ uri: st.profile.photo }} style={[s.pairAva, s.pairAvaOverlap]} />
              ) : (
                <View style={[s.pairAva, s.pairAvaOverlap, s.avaEmpty]}><IconPerson size={13} /></View>
              )}
            </View>
          </Pressable>
        ) : null}

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
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
              {requestTitle || inviteIn.intent?.time ? (
                <Text style={s.invMeta} numberOfLines={1}>
                  {[requestTitle, inviteIn.intent?.time].filter(Boolean).join(' · ')}
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

          {!loading && msgs.length === 0 ? <Text style={s.empty}>{CHAT.empty(other)}</Text> : null}

          {msgs.map((m, i) => {
            const mine = String(m.from || '').trim().toLowerCase() === me.trim().toLowerCase();
            const prev = msgs[i - 1];
            const newDay = !!m.t && (!prev
              || new Date((prev.t || 0) * 1000).toDateString() !== new Date(m.t * 1000).toDateString());
            const read = peerRead >= (m.t || 0);
            return (
              <React.Fragment key={i}>
                {/* MSG.06: «Сегодня» над первой репликой дня. */}
                {newDay ? <Text style={s.day}>{msgDayLabel(m.t!, ru)}</Text> : null}
                <View style={{ alignItems: mine ? 'flex-end' : 'flex-start' }}>
                  <View style={[s.bub, mine ? s.bubMe : s.bubThem]}>
                    <Text style={[s.bubText, mine && { color: color.onPrimary }]}>{m.text}</Text>
                  </View>
                  <Text style={s.time}>
                    {msgTime(m.t, ru)}
                    {/* MSG.11: две галочки — собеседник открывал переписку после этого сообщения. */}
                    {mine ? <Text style={read ? s.tickRead : s.tick}>{read ? '  ✓✓' : '  ✓'}</Text> : null}
                  </Text>
                </View>
              </React.Fragment>
            );
          })}

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
          {!livePlan && msgs.length >= 8 && !noNudge ? (
            <View style={s.nudge}>
              <Text style={s.nudgeLabel}>Kleal</Text>
              <Text style={s.nudgeText}>{THREAD.nudge(msgs.length, other)}</Text>
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

        <View style={[s.dock, { paddingBottom: Math.max(insets.bottom, 10) }]}>
          {/* Искра слева — вход в действия разговора (O.19). На кадре в этом слоте скрепка,
              но вложений в продукте нет — мёртвую кнопку не рисуем. */}
          <Pressable accessibilityRole="button" accessibilityLabel={CHAT.actionsTitle()} style={s.sparkBtn} onPress={() => setActions(true)}>
            <IconSpark size={20} c={color.primary} />
          </Pressable>
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
          {/* MSG.06: отправка — красный круг с самолётиком, а не микрофон-обманка. */}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={T('Отправить', 'Send')}
            disabled={!draft.trim()}
            accessibilityState={{ disabled: !draft.trim() }}
            style={[s.sendBtn, !draft.trim() && { opacity: 0.45 }]}
            onPress={send}
          >
            <IconSend size={18} />
          </Pressable>
        </View>

        {/* Лист O.19. */}
        <Modal visible={actions} transparent animationType="slide" onRequestClose={() => setActions(false)}>
          <Pressable style={s.scrim} onPress={() => setActions(false)} accessibilityLabel={T('Закрыть', 'Close')} />
          <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 18) }]}>
            <View style={s.sheetHead}>
              <Text style={s.sheetTitle}>{CHAT.actionsTitle()}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={() => setActions(false)} hitSlop={10}>
                <Text style={s.sheetX}>✕</Text>
              </Pressable>
            </View>

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
          </View>
        </Modal>

        {/* MSG.10 — интент как лист фактов. Только то, что заявка знает на самом деле: где именно
            пройдёт встреча, не обещаем — «после подтверждения обоих», это и есть правило OF.C3. */}
        <Modal visible={intentOpen} transparent animationType="slide" onRequestClose={() => setIntentOpen(false)}>
          <Pressable style={s.scrim} onPress={() => setIntentOpen(false)} accessibilityLabel={T('Закрыть', 'Close')} />
          <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 18) }]}>
            <View style={s.sheetHead}>
              <Text style={s.sheetTitle} numberOfLines={1}>{requestTitle || intentTitle || T('Интент', 'Intent')}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={() => setIntentOpen(false)} hitSlop={10}>
                <Text style={s.sheetX}>✕</Text>
              </Pressable>
            </View>
            {([
              [THREAD.intentMode(), request?.intent?.mode === 'offline' ? THREAD.offlineInPerson() : THREAD.onlineMode()],
              [THREAD.intentWhen(), String(request?.intent?.time || '—')],
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
          </View>
        </Modal>
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

  thread: { paddingHorizontal: 20, paddingBottom: space.lg, gap: 4 },
  empty: { ...type.bodySmall, color: color.muted, textAlign: 'center', marginTop: space.lg } as any,
  /** MSG.06: «Сегодня» — маленькая серая метка по центру над первой репликой дня. */
  day: { fontSize: 12, color: color.neutral400, textAlign: 'center', marginTop: space.md } as any,
  bub: { maxWidth: '80%', paddingVertical: 12, paddingHorizontal: 16, marginTop: space.sm, borderRadius: 18 },
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary, borderBottomRightRadius: 6 },
  bubThem: { alignSelf: 'flex-start', backgroundColor: color.neutral100, borderBottomLeftRadius: 6 },
  bubText: { fontSize: 15, lineHeight: 21, color: color.fg } as any,
  time: { fontSize: 11, color: color.neutral400, marginTop: 3 } as any,
  /** MSG.11: одна галочка серая, две — красные, прочитано. */
  tick: { fontSize: 11, color: color.neutral400 } as any,
  tickRead: { fontSize: 11, color: color.primary, fontWeight: '700' } as any,
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

  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#0006' },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: color.card, borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 20, paddingTop: 18, gap: space.md,
  },
  sheetHead: { flexDirection: 'row', alignItems: 'center' },
  sheetTitle: { flex: 1, fontSize: 20, fontWeight: '700', color: color.fg },
  sheetX: { fontSize: 20, color: color.fg },
  actPri: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  actPriText: { ...type.button, color: color.onPrimary } as any,
  actDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  actDarkText: { ...type.button, color: '#fff' } as any,
  actSoft: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  actSoftText: { ...type.button, color: color.fg } as any,
  actPlain: { height: 44, alignItems: 'center', justifyContent: 'center' },
  actPlainText: { ...type.button, color: color.fg } as any,
});
