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
import React, { useCallback, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image, ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { MSG, Row, intentRows, planRows, gplanRows, threadRows, groupRows, searchRows, bucketOf, isUnread, rowTime, newestFirst, unreadByPerson } from '../src/messages';
import { mediaUrl, group as gapi } from '../src/api';
import { planWhen, sysLine } from '../src/chat';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, setMsgPrefs } from '../src/state';
import { agent } from '../src/api';
import { IconChevronLeft, IconSearch, IconPerson, IconSpark, IconCalendar } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { Sheet, SheetItem } from '../src/components/Sheet';
import { usePolling } from '../src/polling';
import { color, radius as rad, space, type } from '../src/theme';

export default function Messages() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const ru = getLang() === 'ru';
  const me = String(st.profile.name || '');

  const [tab, setTab] = useState<'intents' | 'plans' | 'private'>('intents');
  const [searching, setSearching] = useState(false);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{
    plans: any[]; history: any[]; inbox: any[]; outbox: any[]; threads: any[];
    groups: any[]; ginvites: any[]; gplans: any[]; ghistory: any[];
  }>({ plans: [], history: [], inbox: [], outbox: [], threads: [], groups: [], ginvites: [],
       gplans: [], ghistory: [] });
  /** Лист MSG.04 — по какой строке вызван. */
  const [menuRow, setMenuRow] = useState<Row | null>(null);
  const [menuNote, setMenuNote] = useState('');

  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    try {
      // Группы — своим запросом и со своим catch: групповой слой новее остальных, и его
      // неудача не должна уносить список переписок, который работал годами.
      // Планов у человека ДВА рода, и живут они на разных ручках: `mplans` — один на один,
      // `gplans` — групповые. Здесь запрашивали только первую, поэтому созданный групповой план
      // во вкладку «Планы» не попадал вообще: человек его делал, видел в группе — и не находил
      // там, где приложение обещает показывать все планы.
      const [pl, inb, out, th, gr, gpl] = await Promise.all([
        agent.plans(me), agent.inbox(me), agent.outbox(me), agent.threads(me),
        gapi.mine(me).catch(() => null),
        gapi.plans(me).catch(() => null),
      ]);
      const arr = (r: any, k: string) => (Array.isArray(r) ? r : r?.[k] || []);
      const threads = arr(th, 'threads');
      setData({
        plans: (pl as any)?.plans || [],
        history: (pl as any)?.history || [],
        inbox: arr(inb, 'requests'),
        outbox: arr(out, 'requests'),
        threads,
        groups: (gr as any)?.groups || [],
        ginvites: (gr as any)?.invites || [],
        gplans: (gpl as any)?.plans || [],
        ghistory: (gpl as any)?.history || [],
      });
    } catch {
      /* тихо: фоновая дотяжка */
    } finally {
      setLoading(false);
    }
  }, [me]);

  // Спит, пока экран не виден: раньше таймер тикал и из стека, и из свёрнутого приложения.
  usePolling(load, 15000);

  const prefs = st.msg || {};
  const sections = useMemo(
    () => intentRows(me, data.plans, data.inbox, data.outbox),
    [me, data.plans, data.inbox, data.outbox]
  );
  /**
   * Договорились о времени и месте — живут здесь, а не среди намерений. И парные, и групповые:
   * для человека «план» это встреча, на которую он идёт, а сколько там людей — вопрос второй.
   * Групповые сюда не попадали вовсе, пока экран не спрашивал `gplans`.
   */
  const plansSec = useMemo(() => {
    const one = planRows(me, data.plans, data.history, ru, planWhen);
    // Групповой план приходит с сервера уже с подписью времени (`when`), собранной пикером, —
    // пересобирать её из starts_at незачем и вредно: разойдётся с тем, что видно в самой группе.
    const many = gplanRows(data.gplans, data.ghistory, ru, (p: any) => String(p.when || ''));
    return {
      upcoming: [...one.upcoming, ...many.upcoming].sort(newestFirst),
      forming: [...one.forming, ...many.forming].sort(newestFirst),
      past: [...one.past, ...many.past].sort(newestFirst),
    };
  }, [me, data, ru]);
  const privateRows = useMemo(() => threadRows(data.threads, me, ru, sysLine), [data.threads, me, ru]);

  /**
   * Непрочитанное приклеивается в ОДНОМ месте — иначе одна и та же переписка показывает разную
   * правду в двух вкладках: в «Интентах» она стоит как пара, которая договаривается, в «Личных»
   * как переписка, и раньше число доставалось только вторым.
   */
  const unread = useMemo(() => unreadByPerson(data.threads), [data.threads]);
  const withUnread = useCallback((rows: Row[]) => rows.map((r) => {
    const n = r.who ? unread[String(r.who).trim().toLowerCase()] || 0 : 0;
    return n ? { ...r, unread: true, count: n } : r;
  }), [unread]);

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

  /** Группы стоят рядом с одиночными интентами: для человека это одна затея, просто людей больше. */
  const gRows = useMemo(() => groupRows(data.groups, data.ginvites, ru), [data.groups, data.ginvites, ru]);
  const formingWithGroups = useMemo(
    () => withUnread([...gRows, ...sections.forming].sort(newestFirst)),
    [gRows, sections.forming, withUnread]
  );

  const intentsAll = formingWithGroups;
  const iForm = split(formingWithGroups);
  const plansAll = [...plansSec.upcoming, ...plansSec.forming, ...plansSec.past];
  const pUp = split(withUnread(plansSec.upcoming)), pForm = split(withUnread(plansSec.forming)),
        pPast = split(withUnread(plansSec.past));
  const pMuted = [...pUp.muted, ...pForm.muted, ...pPast.muted];
  const pArch = [...pUp.archived, ...pForm.archived, ...pPast.archived];
  const pv = split(withUnread(privateRows));

  const empty = !loading
    && intentsAll.length === 0 && plansAll.length === 0 && privateRows.length === 0;

  const found = useMemo(
    () => searchRows(tab === 'intents' ? intentsAll : tab === 'plans' ? plansAll : privateRows, q),
    [q, tab, data] // eslint-disable-line react-hooks/exhaustive-deps
  );

  /**
   * ЛЮБАЯ строка «Сообщений» открывает ПЕРЕПИСКУ — и «Интенты», и «Планы», и «Личные».
   *
   * Раньше каждая вкладка вела в своё: интент — на экран приглашения, план — сразу на экран
   * встречи, и только «Личные» в чат. Экран называется «Сообщения», строки выглядят как чаты, а
   * тап уводил куда угодно, кроме чата, — человек терял разговор, который у него с этим человеком
   * уже есть.
   *
   * Вглубь ведёт сама переписка: закреплённая карточка сверху открывает план или интент, а
   * приглашение, на которое ещё не ответили, стоит карточкой прямо в ленте (MSG.18–MSG.21).
   * Один вход, дальше по одному шагу — вместо трёх разных дверей с одинаковыми ручками.
   */
  const open = (r: Row) => {
    // У групп собеседника нет — вместо переписки открывается комната по gid. Правило «любая
    // строка ведёт в разговор» при этом соблюдено: комната и ЕСТЬ разговор группы.
    if (r.kind === 'group' || r.kind === 'ginvite-in') {
      if (!r.gid) return;
      if (r.kind === 'ginvite-in') {
        router.push({ pathname: '/ginvite', params: { id: r.id || '', gid: r.gid } });
        return;
      }
      router.push({ pathname: '/group', params: { gid: r.gid } });
      return;
    }
    if (!r.who) return;              // строка без собеседника — открывать нечего
    router.push({
      pathname: '/conversation',
      params: { who: r.who, title: r.title || '', photo: r.photo || '' },
    });
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

  /** asMessage — режим раздела «Сообщения» в поиске (MSG.03): под заголовком время реплики. */
  const rowView = (r: Row, asMessage = false) => {
    const unread = isUnread(r, prefs) && bucketOf(r, prefs) === 'normal';
    return (
      <Pressable
        key={(asMessage ? 'm:' : '') + r.key}
        accessibilityRole="button"
        style={s.row}
        onPress={() => open(r)}
        onLongPress={() => { setMenuNote(''); setMenuRow(r); }}
        delayLongPress={350}
      >
        {r.photo ? (
          <Image source={{ uri: mediaUrl(String(r.photo)) }} style={s.ava} />
        ) : (
          <View style={[s.ava, s.avaEmpty]}><IconPerson size={22} /></View>
        )}
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={s.rowTitle} numberOfLines={1}>{r.title}</Text>
          {(asMessage ? rowTime(r.t) : r.sub) ? (
            <Text style={s.rowSub} numberOfLines={1}>{asMessage ? rowTime(r.t) : r.sub}</Text>
          ) : null}
          {r.teaser ? <Text style={s.rowTeaser} numberOfLines={1}>{r.teaser}</Text> : null}
        </View>
        <View style={s.rowRight}>
          <Text style={s.rowTime}>{rowTime(r.t)}</Text>
          {r.count && unread ? (
            <View style={s.badge}><Text style={s.badgeText}>{r.count > 9 ? '9+' : r.count}</Text></View>
          ) : unread ? (
            <View style={s.badgeDot} />
          ) : null}
        </View>
      </Pressable>
    );
  };

  const section = (label: string, rows: Row[]) =>
    rows.length ? (
      <View key={label}>
        <Text style={s.section}>{label}</Text>
        {rows.map((r) => rowView(r))}
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
        // MSG.02: два сегмента в одной белой обойме, активный — красная пилюля.
        <View style={s.tabsWrap}>
          <View style={s.tabs}>
            {([['intents', MSG.tabIntents()], ['plans', MSG.tabPlans()], ['private', MSG.tabPrivate()]] as const).map(([k, label]) => (
              <Pressable
                key={k}
                accessibilityRole="button"
                accessibilityState={{ selected: tab === k }}
                style={[s.tab, tab === k && s.tabOn]}
                onPress={() => setTab(k)}
              >
                <Text style={[s.tabText, tab === k && s.tabTextOn]}>{label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      )}

      <ScrollView contentContainerStyle={[s.body, { paddingBottom: 130 }]} keyboardShouldPersistTaps="handled">
        {/* Kleal закреплён сверху в любом состоянии — так обещает пустой экран MSG.01. */}
        {!searching ? (
          <Pressable accessibilityRole="button" style={s.row} onPress={() => router.push('/buddy')}>
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
            {/* MSG.03: в разделе «Сообщения» под заголовком — время найденной реплики. */}
            {found.messages.length ? (
              <View>
                <Text style={s.section}>{MSG.messages()}</Text>
                {found.messages.map((r) => rowView(r, true))}
              </View>
            ) : null}
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
            {section(MSG.forming(), iForm.normal)}
            {section(MSG.muted(), iForm.muted)}
            {section(MSG.archived(), iForm.archived.map((r) => ({ ...r, teaser: MSG.readOnly() })))}
          </>
        ) : tab === 'plans' ? (
          <>
            {section(MSG.upcoming(), pUp.normal)}
            {section(MSG.forming(), pForm.normal)}
            {section(MSG.past(), pPast.normal)}
            {section(MSG.muted(), pMuted)}
            {section(MSG.archived(), pArch.map((r) => ({ ...r, teaser: MSG.readOnly() })))}
          </>
        ) : (
          <>
            {pv.normal.map((r) => rowView(r))}
            {section(MSG.muted(), pv.muted)}
            {section(MSG.archived(), pv.archived.map((r) => ({ ...r, teaser: MSG.readOnly() })))}
          </>
        )}
      </ScrollView>

      {/* MSG.04 — лист по долгому нажатию. */}
      <Sheet visible={!!menuRow} onClose={() => setMenuRow(null)} title={menuRow?.title}>
        {menuRow?.kind === 'invite-out' ? (
          <SheetItem
            label={MSG.withdrawAction()}
            note={MSG.withdrawNote()}
            onPress={() => menuRow && withdraw(menuRow)}
          />
        ) : (
          <>
            <SheetItem
              label={bucketOf(menuRow || ({} as Row), prefs) === 'muted' ? MSG.unmuteAction() : MSG.muteAction()}
              note={MSG.muteNote()}
              onPress={() => { if (menuRow) { toggle('muted', menuRow); setMenuRow(null); } }}
            />
            <SheetItem
              label={bucketOf(menuRow || ({} as Row), prefs) === 'archived' ? MSG.unarchiveAction() : MSG.archiveAction()}
              note={MSG.archiveNote()}
              onPress={() => { if (menuRow) { toggle('archived', menuRow); setMenuRow(null); } }}
            />
            <SheetItem
              label={MSG.leaveAction()}
              note={MSG.leaveNote()}
              onPress={() => { if (menuRow) { toggle('left', menuRow); setMenuRow(null); } }}
            />
            <SheetItem label={MSG.reportAction()} note={MSG.reportNote()} onPress={() => menuRow && report(menuRow)} />
          </>
        )}
        {menuNote ? <Text style={s.note}>{menuNote}</Text> : null}
      </Sheet>

      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav active="messages" />
      </View>
    </View>
  );
}

// ============================================================ вид
// Дизайн-проход по кадрам MSG.02/MSG.03: карточки с мягкой тенью, крупный аватар, сегменты в
// белой обойме, красный счётчик под временем. Цвета и шрифты — только из токенов темы.

/** Тень карточек списка — одна на все, чтобы список не «мигал» разными глубинами. */
const cardShadow = {
  shadowColor: '#0F172A', shadowOpacity: 0.06, shadowRadius: 12,
  shadowOffset: { width: 0, height: 4 }, elevation: 2,
} as const;

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  headTitle: { flex: 1, fontSize: 22, fontWeight: '700', color: color.fg, textAlign: 'center' } as any,

  // Сегменты MSG.02: белая обойма, активная пилюля красная.
  tabsWrap: { paddingHorizontal: 16, paddingBottom: space.md, alignItems: 'center' },
  tabs: {
    flexDirection: 'row', backgroundColor: color.card, borderRadius: rad.full, padding: 4,
    ...cardShadow,
  },
  tab: {
    height: 40, paddingHorizontal: 26, borderRadius: rad.full,
    alignItems: 'center', justifyContent: 'center',
  },
  tabOn: { backgroundColor: color.primary },
  tabText: { fontSize: 15, fontWeight: '600', color: color.fg } as any,
  tabTextOn: { color: color.onPrimary } as any,

  searchBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: 16, marginBottom: space.md,
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100, paddingHorizontal: 16,
  },
  searchInput: { flex: 1, color: color.fg, fontSize: 16 },

  body: { paddingHorizontal: 16, gap: 0 },
  section: { fontSize: 19, fontWeight: '700', color: color.fg, marginTop: space.lg, marginBottom: 4 } as any,
  note: { ...type.caption, color: color.muted, marginTop: 6 } as any,

  row: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: color.card, borderRadius: 20, paddingVertical: 14, paddingHorizontal: 14,
    marginTop: 10, ...cardShadow,
  },
  klealAva: {
    width: 52, height: 52, borderRadius: 26, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  ava: { width: 52, height: 52, borderRadius: 26 },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  rowTitle: { fontSize: 17, fontWeight: '700', color: color.fg } as any,
  rowSub: { fontSize: 13, color: color.muted } as any,
  rowTeaser: { fontSize: 14, color: color.fg, opacity: 0.75 } as any,
  rowRight: { alignItems: 'flex-end', justifyContent: 'space-between', alignSelf: 'stretch', paddingVertical: 2 },
  rowTime: { fontSize: 12, color: color.neutral400 } as any,
  badge: {
    minWidth: 22, height: 22, borderRadius: 11, paddingHorizontal: 6,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
  },
  badgeText: { fontSize: 12, fontWeight: '700', color: color.onPrimary } as any,
  badgeDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.primary, marginBottom: 4 },

  empty: { alignItems: 'center', gap: space.md, marginTop: 80, paddingHorizontal: 24 },
  emptyIcon: {
    width: 64, height: 64, borderRadius: 32, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  emptyTitle: { fontSize: 19, fontWeight: '700', color: color.fg } as any,
  emptyNote: { ...type.bodySmall, color: color.muted, textAlign: 'center', lineHeight: 20 } as any,
  cta: {
    height: 52, paddingHorizontal: 32, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: space.sm, ...cardShadow,
  },
  ctaText: { ...type.button, color: color.onPrimary } as any,

  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
