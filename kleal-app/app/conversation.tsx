/**
 * Переписка с мэтчем — кадры O.18 и O.19.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор — в src/chat.ts.
 *
 * Устройство по кадрам: шапка с названием интента и стрелкой вправо (открыть интент), под ней имя
 * собеседника с фото, лента сообщений, композер. Слева от поля — искра: она открывает лист
 * действий (O.19), где создаётся план, заканчивается разговор или открывается интент.
 *
 * Сообщения настоящие: /api/agent/message доставляет их собеседнику, /api/agent/thread отдаёт
 * переписку. Лента дотягивается по `since` — забирать все двести сообщений каждые три секунды
 * значило бы гонять килобайты ради одной новой строки.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image,
  ActivityIndicator, Modal, KeyboardAvoidingView, Platform, Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { CHAT, Msg, msgTime } from '../src/chat';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { agent } from '../src/api';
import { IconChevronLeft, IconMic, IconSpark, IconPerson } from '../src/components/icons';
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
  /** Время последнего известного сообщения — по нему сервер отдаёт только новые. */
  const since = useRef(0);

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
      setErr('');
    } catch {
      /* тихо: это фоновая дотяжка, и ругаться на каждый неудавшийся опрос незачем */
    } finally {
      setLoading(false);
    }
  }, [me, other, merge]);

  useEffect(() => { load(); }, [me, other]);

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

  const endConversation = () => {
    const go = () => { setActions(false); router.back(); };
    const ask = CHAT.endAsk(other);
    if (Platform.OS === 'web') {
      // eslint-disable-next-line no-alert
      if (typeof confirm === 'function' && confirm(ask)) go();
      return;
    }
    Alert.alert(ask, undefined, [
      { text: T('Отмена', 'Cancel'), style: 'cancel' },
      { text: CHAT.endConversation(), style: 'destructive', onPress: go },
    ]);
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        {/* Шапка интента: по стрелке — сам интент, ради которого этот разговор и существует. */}
        <Pressable accessibilityRole="button" style={s.intentBar} onPress={() => setActions(true)}>
          <View style={s.intentArt} />
          <Text style={s.intentTitle} numberOfLines={1}>{intentTitle || T('Интент', 'Intent')}</Text>
          <Text style={s.chev}>›</Text>
        </Pressable>

        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
            <IconChevronLeft />
          </Pressable>
          <Text style={s.name} numberOfLines={1}>{other}</Text>
          {photo ? (
            <Image source={{ uri: photo }} style={s.ava} />
          ) : (
            <View style={[s.ava, s.avaEmpty]}><IconPerson size={20} /></View>
          )}
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
          {loading ? <ActivityIndicator color={color.muted} style={{ marginTop: space.lg }} /> : null}
          {!loading && msgs.length === 0 ? <Text style={s.empty}>{CHAT.empty(other)}</Text> : null}

          {msgs.map((m, i) => {
            const mine = String(m.from || '').trim().toLowerCase() === me.trim().toLowerCase();
            return (
              <View key={i} style={{ alignItems: mine ? 'flex-end' : 'flex-start' }}>
                <View style={[s.bub, mine ? s.bubMe : s.bubThem]}>
                  <Text style={[s.bubText, mine && { color: color.onPrimary }]}>{m.text}</Text>
                </View>
                <Text style={s.time}>{msgTime(m.t, getLang() === 'ru')}</Text>
              </View>
            );
          })}

          {err ? <Text style={s.err}>{err}</Text> : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: Math.max(insets.bottom, 10) }]}>
          {/* Искра слева — вход в действия разговора (O.19), как на кадре. */}
          <Pressable accessibilityRole="button" accessibilityLabel={CHAT.actionsTitle()} style={s.sparkBtn} onPress={() => setActions(true)}>
            <IconSpark size={20} c={color.primary} />
          </Pressable>
          <View style={s.field}>
            <TextInput
              style={s.input}
              value={draft}
              onChangeText={setDraft}
              placeholder={CHAT.placeholder()}
              placeholderTextColor={color.neutral400}
              onSubmitEditing={send}
              returnKeyType="send"
            />
            <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send')} onPress={send}>
              <IconMic />
            </Pressable>
          </View>
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

            <Pressable
              accessibilityRole="button"
              style={s.actPri}
              onPress={() => {
                setActions(false);
                router.push({ pathname: '/plan', params: { who: other, title: intentTitle, photo } });
              }}
            >
              <Text style={s.actPriText}>{CHAT.createPlan()}</Text>
            </Pressable>

            <Pressable accessibilityRole="button" style={s.actDark} onPress={endConversation}>
              <Text style={s.actDarkText}>{CHAT.endConversation()}</Text>
            </Pressable>

            <Pressable accessibilityRole="button" style={s.actSoft} onPress={() => { setActions(false); router.push('/create'); }}>
              <Text style={s.actSoftText}>{CHAT.viewIntent()}</Text>
            </Pressable>

            <Pressable accessibilityRole="button" style={s.actPlain} onPress={() => setActions(false)}>
              <Text style={s.actPlainText}>{CHAT.keepChatting()}</Text>
            </Pressable>
          </View>
        </Modal>
      </View>
    </KeyboardAvoidingView>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  intentBar: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: 16,
    padding: 10, borderRadius: rad.lg, backgroundColor: color.card,
  },
  intentArt: { width: 40, height: 34, borderRadius: 8, backgroundColor: color.primary },
  intentTitle: { flex: 1, ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  chev: { fontSize: 20, color: color.neutral400 },

  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingVertical: space.sm },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  name: { flex: 1, ...type.title, color: color.fg, textAlign: 'center' } as any,
  ava: { width: 40, height: 40, borderRadius: 20 },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },

  thread: { paddingHorizontal: 20, paddingBottom: space.lg, gap: 4 },
  empty: { ...type.bodySmall, color: color.muted, textAlign: 'center', marginTop: space.lg } as any,
  bub: { maxWidth: '86%', paddingVertical: 12, paddingHorizontal: 14, marginTop: space.sm, borderRadius: 16 },
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary },
  bubThem: { alignSelf: 'flex-start', backgroundColor: color.neutral100 },
  bubText: { ...type.body, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,
  err: { ...type.bodySmall, color: color.primary, marginTop: space.sm } as any,

  dock: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.bg },
  sparkBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: color.card,
    borderWidth: 1, borderColor: color.border, alignItems: 'center', justifyContent: 'center',
  },
  field: {
    flex: 1, height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },

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
