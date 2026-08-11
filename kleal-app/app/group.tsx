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
import { group as gapi, agent, mediaUrl, newIdem, type GroupInfo } from '../src/api';
import { ROOM, GROUP, groupSysLine } from '../src/groups';
import { adoptGroup } from '../src/ginvites';
import { setResults } from '../src/results-store';
import { msgTime } from '../src/chat';
import { IconChevronLeft, IconPerson, IconSend, IconDots } from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

type GMsg = { id?: string; frm?: string; text?: string; t?: number; kind?: string };

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
  const [msgs, setMsgs] = useState<GMsg[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [fatal, setFatal] = useState('');
  const [info, setInfo] = useState(false);
  const [leaveAsk, setLeaveAsk] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [adopting, setAdopting] = useState(false);
  /** Время последнего известного сообщения — по нему сервер отдаёт только новые. */
  const since = useRef(0);

  const load = useCallback(async () => {
    if (!gid || !me) return;
    try {
      const r: any = await gapi.thread(gid, me, since.current);
      if (r?.error === 'NOT_A_MEMBER') { setFatal(ROOM.notMember()); return; }
      if (r?.error === 'NO_SUCH_GROUP') { setFatal(ROOM.gone()); return; }
      if (r?.group) setG(r.group);
      const list: GMsg[] = r?.messages || [];
      if (list.length) {
        setMsgs((prev) => {
          // Склейка по id: опрос приносит и мою собственную реплику, показанную оптимистично.
          const seen = new Set(prev.map((m) => m.id).filter(Boolean));
          const add = list.filter((m) => !m.id || !seen.has(m.id));
          return [...prev.filter((m) => m.id || !add.some((a) => a.text === m.text)), ...add];
        });
        since.current = Math.max(since.current, ...list.map((m) => Number(m.t || 0)));
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
  useEffect(() => {
    if (fatal) return;
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, [load, fatal]);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [msgs.length]);

  const send = async () => {
    const text = draft.trim();
    if (!text || !me || !gid) return;
    setDraft('');
    // Показываем сразу: опрос принесёт серверную версию этой же реплики и склеит по id.
    setMsgs((prev) => [...prev, { frm: me, text, t: Date.now() / 1000 }]);
    try {
      const r: any = await gapi.post(gid, me, text);
      if (!r?.ok) throw new Error(r?.error || 'post failed');
      setErr('');
    } catch {
      setErr(ROOM.offline());
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
      router.push('/results');
    } catch {
      setErr(GROUP.sendFailed());
    } finally {
      setAdopting(false);
    }
  };

  const leave = async () => {
    if (leaving || !gid) return;
    setLeaving(true);
    try {
      await gapi.leave(gid, me, newIdem('gl'));
      // Вышел — комнаты больше нет: возвращаемся туда, откуда пришли, а не остаёмся смотреть
      // на чат, который сервер уже перестал отдавать.
      if (router.canGoBack()) router.back(); else router.replace('/home');
    } finally {
      setLeaving(false);
    }
  };

  const members = (g?.members || []) as { name?: string; photo?: string }[];
  const others = members.map((m) => String(m.name || '')).filter((n) => n && n !== me);
  const n = Number(g?.joined_count || members.length || 0);
  const min = Number(g?.min_total || 3);
  const canPlan = !!g?.planning_allowed;

  if (fatal) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back}
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
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back}
                     onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
            <IconChevronLeft />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={s.headTitle} numberOfLines={1}>{g?.title || ''}</Text>
            {/* GR.21: при полном составе подзаголовок сам зовёт делать план. */}
            <Text style={[s.headSub, canPlan && { color: color.successText }]} numberOfLines={1}>
              {ROOM.headCount(n, min)}
            </Text>
          </View>
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
          {msgs.map((m, i) => {
            const sys = !String(m.frm || '').trim();
            if (sys) {
              return (
                <Text key={m.id || i} style={s.sys}>
                  {groupSysLine(String(m.text || ''))}
                  {m.t ? ` · ${msgTime(Number(m.t))}` : ''}
                </Text>
              );
            }
            const mine = String(m.frm || '').trim().toLowerCase() === me.toLowerCase();
            return (
              <View key={m.id || i} style={{ alignItems: mine ? 'flex-end' : 'flex-start' }}>
                {/* Имя автора — только у чужих: в группе больше двух человек, и без подписи
                    реплики сливаются в один голос. У своих оно избыточно. */}
                {!mine ? <Text style={s.author}>{m.frm}</Text> : null}
                <View style={[s.bub, mine ? s.bubMe : s.bubThem]}>
                  <Text style={[s.bubText, mine && { color: color.onPrimary }]}>{m.text}</Text>
                </View>
                {m.t ? <Text style={s.time}>{msgTime(Number(m.t))}</Text> : null}
              </View>
            );
          })}
          {err ? <Text style={s.err}>{err}</Text> : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          <View style={s.field}>
            <TextInput
              style={s.input}
              value={draft}
              onChangeText={setDraft}
              placeholder={ROOM.composer()}
              placeholderTextColor={color.neutral400}
              onSubmitEditing={send}
              returnKeyType="send"
            />
            <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send')} onPress={send}>
              <IconSend />
            </Pressable>
          </View>

          {/*
            Нижнее действие — ровно то, что на кадре для этого состава:
              трое и больше (GR.21) — «Создать план»;
              меньше (GR.18)        — «Перейти в один на один», и он ВЫКЛЮЧЕН: конверсии на
                                      сервере нет (слой 3), а кнопка, которая молча ничего не
                                      делает, хуже честно выключенной.
          */}
          {canPlan ? (
            /* GR.21 → GR.25: полный состав ведёт на экран плана. Подпись под кнопкой меняется,
               когда план уже есть: «Создать» тогда врало бы — второго плана у группы не бывает
               (сервер ответит PLAN_EXISTS), и вести туда надо к существующему. */
            <Pressable accessibilityRole="button" style={s.cta}
                       onPress={() => router.push({ pathname: '/gplan', params: { gid } })}>
              <Text style={s.ctaText}>
                {(g as any)?.plan ? ROOM.openPlan() : ROOM.createPlan()}
              </Text>
            </Pressable>
          ) : (
            <View style={s.ctaOffWrap}>
              <View style={[s.cta, s.ctaOff]}>
                <Text style={s.ctaText}>{ROOM.switchTo1to1()}</Text>
              </View>
              <Text style={s.ctaNote}>{ROOM.switchSoon()}</Text>
            </View>
          )}
        </View>

        {/* GR.24 — состав. Лист, а не отдельный маршрут: это справка о той же комнате. */}
        <Modal visible={info} transparent animationType="slide" onRequestClose={() => setInfo(false)}>
          <Pressable style={s.scrim} onPress={() => setInfo(false)} accessibilityLabel={T('Закрыть', 'Close')} />
          <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 18) }]}>
            <View style={s.sheetHead}>
              <Text style={s.sheetTitle}>{ROOM.infoTitle()}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')}
                         onPress={() => setInfo(false)} hitSlop={10}>
                <Text style={s.sheetX}>✕</Text>
              </Pressable>
            </View>
            <Text style={s.sheetBody}>
              {ROOM.infoNote(n, Number(g?.max_total || 5), (g?.invites || []).length)}
            </Text>

            {members.map((m, i) => {
              const nm = String(m.name || '');
              const owner = nm.trim().toLowerCase() === String(g?.owner || '').trim().toLowerCase();
              return (
                <View key={nm + i} style={s.memberRow}>
                  {/* Заглушка снизу, фото сверху — см. тот же приём в app/gplan.tsx: пока фото
                      едет (а через туннель это тридцать секунд), на месте человека должен быть
                      кружок, а не дыра. */}
                  <View style={[s.memberAv, s.memberAvEmpty]}>
                    <IconPerson size={18} />
                    {m.photo ? (
                      <Image source={{ uri: mediaUrl(String(m.photo)) }}
                             style={[s.memberAv, StyleSheet.absoluteFillObject]} />
                    ) : null}
                  </View>
                  <Text style={s.memberName} numberOfLines={1}>
                    {nm === me ? T('Ты', 'You') : nm}
                  </Text>
                  <Text style={s.memberRole}>
                    {owner ? ROOM.roleOrganiser() : ROOM.roleMember()}
                  </Text>
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
            <Pressable accessibilityRole="button" style={s.sheetNot}
                       onPress={() => { setInfo(false); setTimeout(() => setLeaveAsk(true), 250); }}>
              <Text style={s.sheetNotText}>{ROOM.leave()}</Text>
            </Pressable>
          </View>
        </Modal>

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
    <Modal visible={open} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel={T('Закрыть', 'Close')} />
      <View style={[s.sheet, { paddingBottom: Math.max(bottomInset, 18) }]}>
        <View style={s.sheetHead}>
          <Text style={s.sheetTitle}>{ROOM.leaveAsk()}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={onClose} hitSlop={10}>
            <Text style={s.sheetX}>✕</Text>
          </Pressable>
        </View>
        <Text style={s.sheetBody}>{ROOM.leaveBody()}</Text>
        <Pressable accessibilityRole="button" style={s.sheetSend} onPress={busy ? undefined : onYes}
                   accessibilityState={{ busy }}>
          {busy ? <ActivityIndicator color={color.onPrimary} />
                : <Text style={s.sheetSendText}>{ROOM.leaveYes()}</Text>}
        </Pressable>
        <Pressable accessibilityRole="button" style={s.sheetNot} onPress={onClose}>
          <Text style={s.sheetNotText}>{ROOM.cancelBtn()}</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  headTitle: { ...type.title, color: color.fg, fontWeight: '700' } as any,
  headSub: { ...type.bodySmall, color: color.muted } as any,

  whoRow: { paddingHorizontal: 20, paddingBottom: space.sm, gap: 2 },
  who: { ...type.bodySmall, color: color.fg } as any,
  need: { ...type.caption, color: color.muted } as any,

  thread: { paddingHorizontal: 20, paddingTop: space.sm, paddingBottom: space.lg, gap: 4 },
  sys: { ...type.caption, color: color.muted, textAlign: 'center', marginVertical: 6 } as any,
  author: { ...type.caption, color: color.muted, marginLeft: 6, marginTop: space.sm } as any,
  bub: { maxWidth: '86%', paddingVertical: 10, paddingHorizontal: 14, marginTop: 2 },
  bubThem: { alignSelf: 'flex-start', backgroundColor: color.neutral100, borderRadius: 16 },
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary, borderRadius: 16, marginTop: space.sm },
  bubText: { ...type.body, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,
  err: { ...type.bodySmall, color: color.primary, textAlign: 'center', marginTop: space.sm } as any,
  fatal: { ...type.body, color: color.muted, paddingHorizontal: 20, paddingTop: space.lg } as any,

  dock: { paddingHorizontal: 16, paddingTop: space.sm, gap: space.sm, backgroundColor: color.bg },
  field: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  ctaOffWrap: { gap: 4 },
  ctaOff: { opacity: 0.4 },
  ctaNote: { ...type.caption, color: color.muted, textAlign: 'center' } as any,

  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#0006' },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: color.card, borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 20, paddingTop: 14, gap: space.md,
  },
  sheetHead: { flexDirection: 'row', alignItems: 'center' },
  sheetTitle: { flex: 1, fontSize: 20, fontWeight: '700', color: color.fg },
  sheetX: { fontSize: 20, color: color.muted },
  sheetBody: { ...type.bodySmall, color: color.muted } as any,
  sheetSend: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  sheetSendText: { ...type.button, color: color.onPrimary } as any,
  sheetNot: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  sheetNotText: { ...type.button, color: color.fg } as any,

  memberRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  memberAv: { width: 36, height: 36, borderRadius: rad.full },
  memberAvEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  memberName: { flex: 1, ...type.body, color: color.fg } as any,
  memberRole: { ...type.caption, color: color.muted } as any,
});
