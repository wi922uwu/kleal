/**
 * «Сообщения» — кадры MSG.01–MSG.05.
 *
 * UX-КАРКАС: вид натянется поверх; копия и сборка строк — в src/messages.ts.
 *
 * Это точка, куда ведут все остальные секции: переписки, заявки и то, что остаётся после
 * встречи. Список собирается на каждый заход из настоящих источников (планы, приглашения,
 * переписки) и НИГДЕ не хранится — хранятся только локальные пометки (без уведомлений, архив,
 * «покинул», когда тред открывали) в MsgPrefs.
 *
 * Долгое нажатие по строке — лист MSG.04. «Пожаловаться» — настоящий /api/agent/report;
 * отзыв своего приглашения — настоящий /api/agent/withdraw; остальное — локальные пометки.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image, ActivityIndicator, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { MSG, Row, intentRows, threadRows, searchRows, bucketOf, isUnread, rowTime } from '../src/messages';
import { planWhen } from '../src/chat';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, msgPrefs, setMsgPrefs } from '../src/state';
import { agent } from '../src/api';
import { IconChevronLeft, IconSearch, IconPerson, IconSpark, IconCalendar } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

export default function Messages() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const ru = getLang() === 'ru';
  const me = String(st.profile.name || '');

  const [tab, setTab] = useState<'intents' | 'private'>('intents');
  const [searching, setSearching] = useState(false);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{ plans: any[]; history: any[]; inbox: any[]; outbox: any[]; threads: any[] }>(
    { plans: [], history: [], inbox: [], outbox: [], threads: [] }
  );
  /** Лист MSG.04 — по какой строке вызван. */
  const [menuRow, setMenuRow] = useState<Row | null>(null);
  const [menuNote, setMenuNote] = useState('');

  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    try {
      const [pl, inb, out, th] = await Promise.all([
        agent.plans(me), agent.inbox(me), agent.outbox(me), agent.threads(me),
      ]);
      const arr = (r: any, k: string) => (Array.isArray(r) ? r : r?.[k] || []);
      setData({
        plans: (pl as any)?.plans || [],
        history: (pl as any)?.history || [],
        inbox: arr(inb, 'requests'),
        outbox: arr(out, 'requests'),
        threads: arr(th, 'threads'),
      });
    } catch {
      /* тихо: фоновая дотяжка */
    } finally {
      setLoading(false);
    }
  }, [me]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  const prefs = st.msg || {};
  const sections = useMemo(
    () => intentRows(me, data.plans, data.history, data.inbox, data.outbox, ru, planWhen),
    [me, data, ru]
  );
  const privateRows = useMemo(() => threadRows(data.threads), [data.threads]);

  // Раскладка по локальным пометкам: покинутые исчезают, архив и «без уведомлений» — вниз.
  const split = (rows: Row[]) => {
    const normal: Row[] = [], muted: Row[] = [], archived: Row[] = [];
    for (const r of rows) {
      const b = bucketOf(r, prefs);
      if (b === 'left') continue;
      if (b === 'archived') archived.push(r);
      else if (b === 'muted') muted.push(r);
      else normal.push(r);
    }
    return { normal, muted, archived };
  };

  const intentsAll = [...sections.upcoming, ...sections.forming, ...sections.past];
  const iUp = split(sections.upcoming), iForm = split(sections.forming), iPast = split(sections.past);
  const iMuted = [...iUp.muted, ...iForm.muted, ...iPast.muted];
  const iArch = [...iUp.archived, ...iForm.archived, ...iPast.archived];
  const pv = split(privateRows);

  const empty = !loading
    && intentsAll.length === 0 && privateRows.length === 0;

  const found = useMemo(
    () => searchRows(tab === 'intents' ? intentsAll : privateRows, q),
    [q, tab, data] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const open = (r: Row) => {
    if (r.kind === 'invite-in') { router.push({ pathname: '/invite', params: { id: r.id } }); return; }
    if (r.kind === 'plan') {
      router.push({ pathname: '/plan', params: { id: r.id, who: r.who, title: r.title, photo: r.photo || '' } });
      return;
    }
    if (r.kind === 'thread') {
      router.push({ pathname: '/conversation', params: { who: r.who, photo: r.photo || '' } });
      return;
    }
    // invite-out: открывать нечего — ответ ещё не случился; действия живут в долгом нажатии.
  };

  const toggle = (list: 'muted' | 'archived' | 'left', r: Row) => {
    setMsgPrefs((m) => {
      const cur = new Set(m[list] || []);
      if (cur.has(r.key)) cur.delete(r.key); else cur.add(r.key);
      return { ...m, [list]: [...cur] };
    });
  };

  const report = async (r: Row) => {
    try {
      const res: any = await agent.report(me, String(r.who || r.title), 'chat', '');
      if (!res?.ok) throw new Error();
      setMenuNote(MSG.reportSent());
    } catch {
      setMenuNote(T('Не получилось. Попробуй ещё раз.', 'Something went wrong. Try again.'));
    }
  };

  const withdraw = async (r: Row) => {
    try {
      await agent.withdraw(String(r.id), me);
      setMenuRow(null);
      await load();
    } catch {
      setMenuNote(T('Не получилось. Попробуй ещё раз.', 'Something went wrong. Try again.'));
    }
  };

  const rowView = (r: Row) => {
    const unread = isUnread(r, prefs) && bucketOf(r, prefs) === 'normal';
    return (
      <Pressable
        key={r.key}
        accessibilityRole="button"
        style={s.row}
        onPress={() => open(r)}
        onLongPress={() => { setMenuNote(''); setMenuRow(r); }}
        delayLongPress={350}
      >
        {r.photo ? (
          <Image source={{ uri: r.photo }} style={s.ava} />
        ) : (
          <View style={[s.ava, s.avaEmpty]}><IconPerson size={18} /></View>
        )}
        <View style={{ flex: 1 }}>
          <Text style={s.rowTitle} numberOfLines={1}>{r.title}</Text>
          {r.sub ? <Text style={s.rowSub} numberOfLines={1}>{r.sub}</Text> : null}
          {r.teaser ? <Text style={s.rowTeaser} numberOfLines={1}>{r.teaser}</Text> : null}
        </View>
        <View style={s.rowRight}>
          <Text style={s.rowTime}>{rowTime(r.t)}</Text>
          {unread ? <View style={s.badge} /> : null}
        </View>
      </Pressable>
    );
  };

  const section = (label: string, rows: Row[]) =>
    rows.length ? (
      <View key={label}>
        <Text style={s.section}>{label}</Text>
        {rows.map(rowView)}
      </View>
    ) : null;

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
          <IconChevronLeft />
        </Pressable>
        <Text style={s.headTitle}>{MSG.title()}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={MSG.searchPlaceholder()}
          accessibilityState={{ selected: searching }}
          style={s.back}
          onPress={() => { setSearching((v) => !v); setQ(''); }}
        >
          <IconSearch size={20} c={color.fg} />
        </Pressable>
      </View>

      {searching ? (
        <View style={s.searchBox}>
          <IconSearch size={16} c={color.neutral400} />
          <TextInput
            style={s.searchInput}
            value={q}
            onChangeText={setQ}
            placeholder={MSG.searchPlaceholder()}
            placeholderTextColor={color.neutral400}
            autoFocus
          />
        </View>
      ) : (
        <View style={s.tabs}>
          {([['intents', MSG.tabIntents()], ['private', MSG.tabPrivate()]] as const).map(([k, label]) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              accessibilityState={{ selected: tab === k }}
              style={[s.tab, tab === k && s.tabOn]}
              onPress={() => setTab(k)}
            >
              <Text style={[s.tabText, tab === k && { color: color.onPrimary }]}>{label}</Text>
            </Pressable>
          ))}
        </View>
      )}

      <ScrollView contentContainerStyle={[s.body, { paddingBottom: 130 }]} keyboardShouldPersistTaps="handled">
        {/* Kleal закреплён сверху в любом состоянии — так обещает пустой экран MSG.01. */}
        {!searching ? (
          <Pressable accessibilityRole="button" style={[s.row, s.klealRow]} onPress={() => router.push('/buddy')}>
            <View style={s.klealAva}><IconSpark size={20} c={color.onPrimary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.rowTitle}>{MSG.kleal()}</Text>
              <Text style={s.rowSub}>{MSG.klealSub()}</Text>
              <Text style={s.rowTeaser}>{MSG.klealTeaser()}</Text>
            </View>
          </Pressable>
        ) : null}

        {loading ? <ActivityIndicator color={color.muted} style={{ marginTop: space.lg }} /> : null}

        {searching ? (
          <>
            <Text style={s.note}>{MSG.searchNote()}</Text>
            {q && !found.chats.length && !found.messages.length ? (
              <Text style={s.note}>{MSG.nothingFound()}</Text>
            ) : null}
            {section(MSG.chats(), found.chats)}
            {section(MSG.messages(), found.messages)}
          </>
        ) : empty ? (
          // MSG.01 — пустое состояние.
          <View style={s.empty}>
            <View style={s.emptyIcon}><IconCalendar /></View>
            <Text style={s.emptyTitle}>{MSG.emptyTitle()}</Text>
            <Text style={s.emptyNote}>{MSG.emptyNote()}</Text>
            <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.push('/create')}>
              <Text style={s.ctaText}>{MSG.createIntent()}</Text>
            </Pressable>
          </View>
        ) : tab === 'intents' ? (
          <>
            {section(MSG.upcoming(), iUp.normal)}
            {section(MSG.forming(), iForm.normal)}
            {section(MSG.past(), iPast.normal)}
            {section(MSG.muted(), iMuted)}
            {section(MSG.archived(), iArch.map((r) => ({ ...r, teaser: MSG.readOnly() })))}
          </>
        ) : (
          <>
            {pv.normal.map(rowView)}
            {section(MSG.muted(), pv.muted)}
            {section(MSG.archived(), pv.archived.map((r) => ({ ...r, teaser: MSG.readOnly() })))}
          </>
        )}
      </ScrollView>

      {/* MSG.04 — лист по долгому нажатию. */}
      <Modal visible={!!menuRow} transparent animationType="slide" onRequestClose={() => setMenuRow(null)}>
        <Pressable style={s.scrim} onPress={() => setMenuRow(null)} accessibilityLabel={T('Закрыть', 'Close')} />
        <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 18) }]}>
          <View style={s.sheetHead}>
            <Text style={s.sheetTitle} numberOfLines={1}>{menuRow?.title}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={() => setMenuRow(null)} hitSlop={10}>
              <Text style={s.sheetX}>✕</Text>
            </Pressable>
          </View>

          {menuRow?.kind === 'invite-out' ? (
            <MenuItem
              label={MSG.withdrawAction()}
              note={MSG.withdrawNote()}
              onPress={() => menuRow && withdraw(menuRow)}
            />
          ) : (
            <>
              <MenuItem
                label={bucketOf(menuRow || ({} as Row), prefs) === 'muted' ? MSG.unmuteAction() : MSG.muteAction()}
                note={MSG.muteNote()}
                onPress={() => { if (menuRow) { toggle('muted', menuRow); setMenuRow(null); } }}
              />
              <MenuItem
                label={bucketOf(menuRow || ({} as Row), prefs) === 'archived' ? MSG.unarchiveAction() : MSG.archiveAction()}
                note={MSG.archiveNote()}
                onPress={() => { if (menuRow) { toggle('archived', menuRow); setMenuRow(null); } }}
              />
              <MenuItem
                label={MSG.leaveAction()}
                note={MSG.leaveNote()}
                onPress={() => { if (menuRow) { toggle('left', menuRow); setMenuRow(null); } }}
              />
              <MenuItem label={MSG.reportAction()} note={MSG.reportNote()} onPress={() => menuRow && report(menuRow)} />
            </>
          )}

          {menuNote ? <Text style={s.note}>{menuNote}</Text> : null}
        </View>
      </Modal>

      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav active="messages" />
      </View>
    </View>
  );
}

function MenuItem({ label, note, onPress }: { label: string; note: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" style={s.menuItem} onPress={onPress}>
      <Text style={s.menuLabel}>{label}</Text>
      <Text style={s.menuNote}>{note}</Text>
    </Pressable>
  );
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

  tabs: { flexDirection: 'row', gap: space.sm, paddingHorizontal: 16, paddingBottom: space.sm },
  tab: {
    height: 36, paddingHorizontal: 18, borderRadius: rad.full, backgroundColor: color.card,
    borderWidth: 1, borderColor: color.border, alignItems: 'center', justifyContent: 'center',
  },
  tabOn: { backgroundColor: color.primary, borderColor: color.primary },
  tabText: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,

  searchBox: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 16, marginBottom: space.sm,
    height: 42, borderRadius: rad.full, backgroundColor: color.neutral100, paddingHorizontal: 14,
  },
  searchInput: { flex: 1, color: color.fg, fontSize: 15 },

  body: { paddingHorizontal: 16, gap: 6 },
  section: { ...type.labelMedium, color: color.fg, fontWeight: '700', marginTop: space.md, marginBottom: 4 } as any,
  note: { ...type.caption, color: color.muted, marginTop: 6 } as any,

  row: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: color.card, borderRadius: rad.lg, padding: space.md, marginTop: 6,
  },
  klealRow: { borderWidth: 1, borderColor: color.border },
  klealAva: { width: 40, height: 40, borderRadius: 20, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ava: { width: 40, height: 40, borderRadius: 20 },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  rowTitle: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  rowSub: { ...type.caption, color: color.muted } as any,
  rowTeaser: { ...type.caption, color: color.fg } as any,
  rowRight: { alignItems: 'flex-end', gap: 6 },
  rowTime: { ...type.caption, color: color.neutral400 } as any,
  badge: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.primary },

  empty: { alignItems: 'center', gap: space.md, marginTop: 80, paddingHorizontal: 24 },
  emptyIcon: {
    width: 56, height: 56, borderRadius: 28, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  emptyTitle: { ...type.title, color: color.fg } as any,
  emptyNote: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,
  cta: {
    height: 48, paddingHorizontal: 28, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: space.sm,
  },
  ctaText: { ...type.button, color: color.onPrimary } as any,

  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#0006' },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: color.card, borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 20, paddingTop: 18, gap: space.sm,
  },
  sheetHead: { flexDirection: 'row', alignItems: 'center', marginBottom: space.sm },
  sheetTitle: { flex: 1, fontSize: 20, fontWeight: '700', color: color.fg },
  sheetX: { fontSize: 20, color: color.fg },
  menuItem: { paddingVertical: 10 },
  menuLabel: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  menuNote: { ...type.caption, color: color.muted, marginTop: 2 } as any,

  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
