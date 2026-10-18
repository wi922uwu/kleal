/**
 * «Сообщения» — борд «Messages — new layout» (Figma 6873:170006), раздел A: MSG.01–MSG.05.
 *
 * Список собирается на каждый заход из настоящих источников (планы 1:1 и групповые, принятые
 * приглашения, переписки, комнаты групп с их лентами) и НИГДЕ не хранится. Хранятся только
 * локальные пометки (без уведомлений, архив, когда группу открывали) в MsgPrefs.
 *
 * Вкладки три (слово владельца 17.10.2026: «интенты, планы, личные»): «Intents» — чаты затей, где
 * время и место ещё обсуждают (раздел Planning); «Plans» — чаты с назначенной встречей, разделы
 * Upcoming / Ended; «Private» — личные переписки вне затей (MSG.22; личных запросов на сервере ещё
 * нет — вкладка пока пустая). Приглашения сюда не попадают: им место в «My activity» и на главной.
 *
 * Долгое нажатие по строке — лист MSG.03 / MSG.03a. Выход, передача роли и закрытие группы — те же
 * настоящие шаги, что в комнате (лист подтверждения открывается там); жалоба — экран жалобы.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image, ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import {
  MSG, Row, GMsg, inboxRows, searchInbox, bucketOf, isUnread, rowTime, newestFirst, threadRows, shortDay, migrateLegacyMsgPrefs, archiveTeaser, personKey,
} from '../src/messages';
import { mediaUrl, group as gapi, agent, isMe, getSession } from '../src/api';
import { CHAT, planWhen, sysLine } from '../src/chat';
import { groupSysLine } from '../src/groups';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, setMsgPrefs, syncChatLifecycles } from '../src/state';
import {
  IconSearch, IconPerson, IconClose, IconBellOff, IconBell, IconArchive, IconFlag, IconExit, IconCrown, IconBan,
  IconChevronRight, IconImagePlaceholder,
} from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { Sheet, SheetItem } from '../src/components/Sheet';
import { chatLifecycle } from '../src/chat-lifecycle';
import { usePolling } from '../src/polling';
import { color, radius as rad, space, type, heading } from '../src/theme';
import { GlassBack, GlassSurface } from '../src/components/LiquidGlass';
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { useNavCollapse } from '../src/navScroll';
import { blurReturnAction, navigateReturnAction, recoveryAction, returnActionRoute } from '../src/monetization-actions';
import { MONETIZATION } from '../src/monetization';

/** Сколько комнат дотягивать лентой за раз: превью, счётчик и поиск по репликам. */
const GROUP_FEEDS = 12;
/** Чат после встречи держится открытым 30 дней (MSG.05). */
const OPEN_DAYS = 30;

export default function Messages() {
  const st = useOnb();
  return <MessagesContent key={String(st.session || '')} />;
}

function MessagesContent() {
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const ru = getLang() === 'ru';
  const me = String(st.profile.name || '');
  const screenSession = String(st.session || '');
  const recovery = recoveryAction(screenSession,'messages');
  useFocusEffect(useCallback(()=>()=>blurReturnAction(screenSession,'messages'),[screenSession]));

  const [tab, setTab] = useState<'intents' | 'plans' | 'private'>('intents');
  const [arch, setArch] = useState(false);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{
    plans: any[]; history: any[]; inbox: any[]; outbox: any[]; threads: any[];
    groups: any[]; gplans: any[]; ghistory: any[]; gmsgs: Record<string, GMsg[]>;
  }>({ plans: [], history: [], inbox: [], outbox: [], threads: [], groups: [], gplans: [], ghistory: [], gmsgs: {} });
  const [menuRow, setMenuRow] = useState<Row | null>(null);

  const mounted = useRef(true);
  const loadVersion = useRef(0);
  const appliedVersion = useRef(0);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const prefs = st.msg || {};
  const menuChat = menuRow?.whoId ? prefs.chats?.[menuRow.whoId] : undefined;
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;

  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    const session = screenSession, version = ++loadVersion.current;
    const current = () => mounted.current && session === getSession() && version >= appliedVersion.current;
    if (!session || !current()) return;
    try {
      // Группы — своим catch: их неудача не должна уносить переписки один на один.
      const [pl, inb, out, th, gr, gpl, saf] = await Promise.all([
        agent.plans(me), agent.inbox(me), agent.outbox(me), agent.threads(me),
        gapi.mine(me).catch(() => null),
        gapi.plans(me).catch(() => null),
        agent.safety(me).catch(() => null),
      ]);
      // Реплики заблокированных не всплывают и превью строки (MSG.14b — у меня они скрыты).
      const blocked = new Set((((saf as any)?.blocked || []) as string[]).map((x) => String(x).trim().toLowerCase()));
      const arr = (r: any, k: string) => (Array.isArray(r) ? r : r?.[k] || []);
      const groups: any[] = (gr as any)?.groups || [];
      // Ленты комнат: в списке групп последней реплики нет, а строка на борде её показывает.
      const gids = [...groups].sort((a, b) => Number(b.updated || b.created || 0) - Number(a.updated || a.created || 0))
        .slice(0, GROUP_FEEDS).map((g) => String(g.gid || '')).filter(Boolean);
      const feeds = await Promise.all(gids.map((gid) => gapi.thread(gid, me, 0).catch(() => null)));
      const gmsgs: Record<string, GMsg[]> = {};
      gids.forEach((gid, i) => {
        gmsgs[gid] = (((feeds[i] as any)?.messages || []) as GMsg[])
          .filter((m) => !m.frm || !blocked.has(String(m.frm).trim().toLowerCase())).slice(-50);
      });
      // Группа, которую ни разу не открывали с этого телефона, начинает счёт с этой минуты —
      // иначе первый заход зажёг бы счётчик на всю историю каждой комнаты.
      if (!current()) return;
      appliedVersion.current=version;
      // Partial lists can disprove an old name binding, never prove uniqueness.
      const peers = arr(th,'threads').map((r:any)=>({name:String(r.who || ''),id:String(r.who_id || '')}));
      for (const r of [...arr(inb,'requests'),...arr(out,'requests')]) {
        const mine=isMe(r.from,r.from_id,me);
        peers.push({name:String((mine ? r.to : r.from) || ''),id:String((mine ? r.to_id : r.from_id) || '')});
      }
      for (const r of [...((pl as any)?.plans || []),...((pl as any)?.history || [])]) {
        if (r.other) peers.push({name:String(r.other),id:String(r.other_id || '')});
        for (const p of r.participants || []) if (!isMe(p.name,p.name_id || p.id,me))
          peers.push({name:String(p.name || ''),id:String(p.name_id || p.id || '')});
      }
      const chats=arr(th,'threads').flatMap((row:any)=>{
        const chat=chatLifecycle(row.chat,row.who_id);return chat?[chat]:[];
      });
      syncChatLifecycles(chats,session,false,prefs=>{
        const migrated=migrateLegacyMsgPrefs(prefs,peers);
        const fresh=gids.filter(gid=>!migrated.seen?.['g:'+gid]);
        if (!fresh.length) return migrated;
        const now = Date.now() / 1000;
        return {...migrated,seen:{...migrated.seen,...Object.fromEntries(fresh.map(g=>['g:'+g,now]))}};
      });
      setData({
        plans: (pl as any)?.plans || [], history: (pl as any)?.history || [],
        // Заявки с заблокированным в списке не всплывают: сервер убрал его переписку из threads, а
        // строку пары давали inbox/outbox (сверка п. 4).
        inbox: arr(inb, 'requests').filter((r: any) => !blocked.has(String(r?.from || '').trim().toLowerCase())),
        outbox: arr(out, 'requests').filter((r: any) => !blocked.has(String(r?.to || '').trim().toLowerCase())),
        threads: arr(th, 'threads'),
        groups, gplans: (gpl as any)?.plans || [], ghistory: (gpl as any)?.history || [], gmsgs,
      });
    } catch {
      /* тихо: фоновая дотяжка */
    } finally {
      if (current()) setLoading(false);
    }
  }, [me, screenSession]);

  usePolling(load, 15000);

  const rows = useMemo(() => inboxRows({
    me, ru, ...data, seen: prefs.seen || {}, planWhen, sysLine,
    gSysLine: (m) => groupSysLine(String(m.text || ''), m.sys),
  }), [me, ru, data, prefs.seen]);

  /** «Private» — переписки, у которых нет строки в «Intents» (сейчас таких почти не бывает). */
  const privRows = useMemo(() => {
    const peerKey = (r: Row) => r.whoId ? 'id:' + r.whoId : String(r.who || '').trim().toLowerCase();
    const taken = new Set(rows.map(peerKey).filter(Boolean));
    const accepted = new Set<string>();
    for (const r of [...data.inbox, ...data.outbox]) {
      if (r?.status !== 'accepted') continue;
      const mine = isMe(r.from, r.from_id, me);
      const id = String((mine ? r.to_id : r.from_id) || '');
      if (id) accepted.add('id:' + id);
      accepted.add(String((mine ? r.to : r.from) || '').trim().toLowerCase());
    }
    return threadRows(data.threads, me, ru, sysLine, accepted)
      .filter((r) => !taken.has(peerKey(r)));
  }, [rows, data.threads, data.inbox, data.outbox, me, ru]);

  const live = (list: Row[]) => list.filter((r) => bucketOf(r, prefs) === 'normal' || bucketOf(r, prefs) === 'muted');
  const archived = [...rows, ...privRows].filter((r) => { const b = bucketOf(r, prefs); return b === 'archived' || b === 'left'; })
    .sort(newestFirst);
  const intents = live(rows);
  const priv = live(privRows);
  const isMuted = (r: Row) => bucketOf(r, prefs) === 'muted';
  const hot = (r: Row) => isUnread(r, prefs) && !isMuted(r);
  /** Встреча назначена (Upcoming) или прошла (Ended) — вкладка «Plans»; остальное — «Intents». */
  const planned = intents.filter((r) => r.sec === 'upcoming' || r.sec === 'ended');
  const openRows = intents.filter((r) => r.sec !== 'upcoming' && r.sec !== 'ended');
  const intentsBadge = openRows.filter(hot).length;
  const plansBadge = planned.filter(hot).length;
  const privBadge = priv.filter(hot).length;

  const searching = q.trim().length > 0;
  const found = useMemo(
    () => searchInbox([...intents, ...priv], data.gmsgs, data.threads, me, q),
    [q, intents, priv, data, me] // eslint-disable-line react-hooks/exhaustive-deps
  );
  const nothing = !loading && rows.length === 0 && privRows.length === 0;

  /** Любая строка открывает разговор: группа — комнату, пара — переписку. */
  const open = (r: Row) => {
    if (r.kind === 'group') {
      if (r.gid) router.navigate({ pathname: '/group', params: { gid: r.gid } });
      return;
    }
    if (!r.who) return;
    const recoveryRoute=recovery ? returnActionRoute(screenSession,'conversation') : null;
    if (recoveryRoute) navigateReturnAction(screenSession,'messages','conversation');
    router.navigate({
      pathname: '/conversation',
      params: { ...recoveryRoute?.params, who: r.who, who_id: r.whoId || '', title: r.title || '', photo: r.photo || '' },
    });
  };

  const toggle = (list: 'muted' | 'archived', r: Row) => {
    setMsgPrefs((m) => {
      const cur = new Set(m[list] || []);
      const keys = [r.key, r.whoId ? 'id:' + r.whoId : String(r.who || '').trim().toLowerCase()].filter(Boolean);
      const on = keys.some((k) => cur.has(k));
      for (const k of keys) { if (on) cur.delete(k); else if (k === r.key) cur.add(k); }
      // Вернуть из архива — снять и старую пометку «покинул», она жила той же полкой.
      const left = list === 'archived' && on ? (m.left || []).filter((k) => !keys.includes(k)) : m.left;
      return { ...m, [list]: [...cur], left };
    });
  };

  /** Шаг листа: закрыть лист, затем перейти — иначе переход ловит закрывающуюся модалку. */
  const go = (fn: () => void) => { setMenuRow(null); setTimeout(fn, 250); };

  const report = (r: Row) => go(() => router.navigate(r.kind === 'group'
    ? { pathname: '/group-report', params: { gid: r.gid || '', title: r.title || '' } }
    : { pathname: '/group-report', params: { who: r.who || '', who_id: r.whoId || '', photo: r.photo || '' } }));

  // ===== строка

  const rowView = (r: Row, opts: { search?: boolean; arch?: boolean; chat?: boolean } = {}) => {
    const muted = isMuted(r);
    const unread = isUnread(r, prefs) && !opts.search;
    // «open until …» — только пока срок впереди: прошедшая дата читалась бы как обещание.
    const ended = r.sec === 'ended' && r.meetAt && Number(r.meetAt) + OPEN_DAYS * 86400 > Date.now() / 1000;
    // В найденных чатах под названием — кто в чате (MSG.02 «Jane, Marc and you»).
    const sub = ended
      ? `${r.sub} · ${MSG.openUntil(shortDay(Number(r.meetAt) + OPEN_DAYS * 86400))}`
      : opts.chat && r.kind === 'group' ? (r.people || r.sub) : r.sub;
    return (
      <Pressable
        key={r.key}
        accessibilityRole="button"
        style={({ pressed }) => [s.row, pressed && { opacity: 0.85 }]}
        onPress={() => open(r)}
        onLongPress={opts.search ? undefined : () => setMenuRow(r)}
        delayLongPress={350}
      >
        {r.photo ? (
          <Image source={{ uri: mediaUrl(String(r.photo)) }} style={s.ava} />
        ) : (
          <View style={[s.ava, s.avaEmpty]}>
            {r.kind === 'group' ? <IconImagePlaceholder size={18} c={color.muted} /> : <IconPerson size={20} />}
          </View>
        )}
        <View style={{ flex: 1, gap: 2 }}>
          <View style={s.line}>
            <Text style={s.rowTitle} numberOfLines={1}>{r.title}</Text>
            {muted ? <IconBellOff size={16} c={color.muted} /> : null}
            <Text style={s.rowTime}>{rowTime(r.t)}</Text>
          </View>
          <View style={s.line}>
            <View style={{ flex: 1, gap: 2 }}>
              {sub ? <Hl style={s.rowSub} text={sub} q={opts.search ? q : ''} /> : null}
              {archiveTeaser(r,prefs) ? <Hl style={s.rowTeaser} text={archiveTeaser(r,prefs)!} q={opts.search ? q : ''} /> : null}
            </View>
            {r.count && unread ? (
              <View style={[s.badge, muted && s.badgeMuted]}><Text style={s.badgeText}>{r.count > 9 ? '9+' : r.count}</Text></View>
            ) : unread && !muted ? <View style={s.dot} /> : null}
          </View>
        </View>
      </Pressable>
    );
  };

  const section = (label: string, list: Row[], opts: { search?: boolean; arch?: boolean; chat?: boolean } = {}, note?: string) =>
    list.length ? (
      <View key={label} style={{ gap: 8 }}>
        <View style={{ gap: 2, marginTop: space.sm }}>
          <Text style={s.section}>{label}</Text>
          {note ? <Text style={s.sectionNote}>{note}</Text> : null}
        </View>
        {list.map((r) => rowView(r, opts))}
      </View>
    ) : null;

  const back = () => {
    if (arch) { setArch(false); return; }
    router.canGoBack() ? router.back() : router.replace('/home');
  };

  // ===== лист MSG.03 / MSG.03a

  const m = menuRow;
  const mMuted = m ? isMuted(m) : false;
  const mArch = m ? ['archived', 'left'].includes(bucketOf(m, prefs)) : false;
  const sheet = m ? (
    <>
      <SheetItem
        icon={mMuted ? <IconBell size={20} c={color.primary} /> : <IconBellOff size={20} c={color.primary} />}
        label={mMuted ? MSG.unmuteNew() : MSG.muteAction()}
        note={mMuted ? MSG.unmuteNote() : MSG.muteNoteNew()}
        onPress={() => { toggle('muted', m); setMenuRow(null); }}
      />
      <SheetItem
        icon={<IconArchive size={20} c={color.primary} />}
        label={menuChat?.state === 'closed' ? (menuChat.blocked ? CHAT.openHistory() : CHAT.resumeChat()) : mArch ? MSG.unarchiveNew() : MSG.archiveAction()}
        note={menuChat?.state === 'closed' ? (menuChat.blocked ? CHAT.chatBlocked() : CHAT.resumeNote()) : mArch ? MSG.unarchiveNote() : MSG.archiveNoteNew()}
        onPress={() => { if (menuChat?.state === 'closed') open(m); else toggle('archived', m); setMenuRow(null); }}
      />
      {m.kind === 'group' && m.owner && !m.readOnly ? (
        <>
          {m.canHandOver ? (
            <SheetItem icon={<IconCrown />} label={MSG.handOver()} note={MSG.handOverNote()}
              onPress={() => go(() => router.navigate({ pathname: '/grole', params: { gid: m.gid || '', pick: '1' } }))} />
          ) : null}
          {m.canEnd ? (
            <SheetItem icon={<IconBan />} danger label={MSG.endGroup()} note={MSG.endGroupNote()}
              onPress={() => go(() => router.navigate({ pathname: '/group', params: { gid: m.gid || '', act: 'end' } }))} />
          ) : null}
        </>
      ) : (
        <>
          <SheetItem icon={<IconFlag size={20} c={color.primary} />} label={MSG.report()} note={MSG.reportNoteNew()}
            onPress={() => report(m)} />
          {m.kind === 'group' && !m.readOnly ? (
            <SheetItem icon={<IconExit size={20} c={color.danger} />} danger label={MSG.leaveGroup()}
              note={MSG.leaveGroupNote(m.others || [])}
              onPress={() => go(() => router.navigate({ pathname: '/group', params: { gid: m.gid || '', act: 'leave' } }))} />
          ) : null}
        </>
      )}
    </>
  ) : null;

  // ===== экран

  const bySec = (sec: Row['sec']) => intents.filter((r) => r.sec === sec);

  return (
    <View style={s.wrap}>
      <Ambient glows={GLOW_FORM} />
      <View style={[s.top, { paddingTop: insets.top + 6 }]}>
        <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={back} />
        <Text style={[s.title, heading(lang, type.headingSm)]} numberOfLines={1}>{arch ? MSG.archiveRow() : MSG.title()}</Text>
      </View>

      {recovery ? <Pressable accessibilityRole="button" onPress={() => {
        const route=returnActionRoute(screenSession,'plus');
        if (route && navigateReturnAction(screenSession,'messages','plus')) router.dismissTo(route);
      }}><Text style={s.rowTitle}>{MONETIZATION.returnToAction()}</Text></Pressable> : null}

      {!arch && !nothing ? (
        // MSG.01: поиск всегда на виду — стеклянная пилюля.
        <GlassSurface tone="light" radius={999} style={s.search}>
          <IconSearch size={20} c={color.fg} />
          <TextInput
            style={s.searchInput}
            value={q}
            onChangeText={setQ}
            placeholder={MSG.searchChats()}
            placeholderTextColor={color.muted}
            returnKeyType="search"
            autoCorrect={false}
          />
          {q ? (
            <Pressable accessibilityRole="button" accessibilityLabel={T('Очистить', 'Clear', 'Borrar')} hitSlop={10} onPress={() => setQ('')}>
              <IconClose size={18} c={color.fg} />
            </Pressable>
          ) : null}
        </GlassSurface>
      ) : null}

      {!arch && !searching ? (
        <View style={s.segs}>
          {([['intents', MSG.tabIntents(), intentsBadge], ['plans', MSG.tabPlans(), plansBadge], ['private', MSG.tabPrivate(), privBadge]] as const).map(([k, label, badge]) => {
            const on = tab === k;
            const inner = (
              <>
                <Text style={[s.segText, on && s.segTextOn]} numberOfLines={1}>{label}</Text>
                {badge > 0 ? (
                  <View style={[s.segBadge, on && s.segBadgeOn]}><Text style={[s.segBadgeText, on && s.segBadgeTextOn]}>{badge}</Text></View>
                ) : null}
              </>
            );
            return (
              <Pressable key={k} style={{ flex: 1 }} accessibilityRole="button" accessibilityState={{ selected: on }} onPress={() => setTab(k)}>
                {on ? <View style={[s.seg, s.segOn]}>{inner}</View>
                  : <GlassSurface tone="light" radius={999} style={s.seg}>{inner}</GlassSurface>}
              </Pressable>
            );
          })}
        </View>
      ) : null}

      <ScrollView
        onScroll={navCollapse}
        scrollEventThrottle={16}
        contentContainerStyle={[s.body, { paddingBottom: insets.bottom + 120 }]}
        keyboardShouldPersistTaps="handled"
      >
        {loading ? <ActivityIndicator color={color.muted} style={{ marginTop: space.lg }} /> : null}

        {arch ? (
          // MSG.05 — архив.
          <>
            {section(MSG.archivedByYou(), archived, { arch: true }, MSG.archivedByYouNote())}
          </>
        ) : searching ? (
          // MSG.02 / MSG.02a — поиск.
          found.chats.length || found.messages.length ? (
            <>
              {section(MSG.chats(), found.chats, { search: true, chat: true })}
              {section(MSG.messages(), found.messages, { search: true })}
            </>
          ) : (
            <View style={s.empty}>
              <Text style={s.emptyTitle}>{MSG.nothingFoundFor(q.trim())}</Text>
              <Text style={s.emptyNote}>{MSG.searchHint()}</Text>
            </View>
          )
        ) : tab === 'intents' || tab === 'plans' ? (
          !loading && intents.length === 0 && archived.length === 0 ? (
            // MSG.01a — пусто.
            <View style={s.empty}>
              <Text style={s.emptyTitle}>{MSG.noChats()}</Text>
              <Text style={s.emptyNote}>{MSG.noChatsNote()}</Text>
              <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.navigate('/buddy')}>
                <Text style={s.ctaText}>{MSG.talkToKleal()}</Text>
              </Pressable>
            </View>
          ) : (
            <>
              {tab === 'intents' ? (
                openRows.length ? section(MSG.planning(), openRows) : !loading ? (
                  <View style={s.empty}>
                    <Text style={s.emptyTitle}>{MSG.noIntentsOpen()}</Text>
                    <Text style={s.emptyNote}>{MSG.noIntentsOpenNote()}</Text>
                  </View>
                ) : null
              ) : planned.length ? (
                <>
                  {section(MSG.upcomingNew(), bySec('upcoming'))}
                  {section(MSG.endedSec(), bySec('ended'))}
                </>
              ) : !loading ? (
                <View style={s.empty}>
                  <Text style={s.emptyTitle}>{MSG.noPlansYet()}</Text>
                  <Text style={s.emptyNote}>{MSG.noPlansNote()}</Text>
                </View>
              ) : null}
              {archived.length ? (
                // MSG.04 — архив строкой внизу.
                <Pressable accessibilityRole="button" style={[s.row, s.archRow]} onPress={() => setArch(true)}>
                  <IconArchive size={22} c={color.primary} />
                  <View style={{ flex: 1 }}>
                    <Text style={s.rowTitle}>{MSG.archiveRow()}</Text>
                    <Text style={s.rowSub}>{MSG.chatsCount(archived.length)}</Text>
                  </View>
                  <IconChevronRight size={20} c={color.muted} />
                </Pressable>
              ) : null}
            </>
          )
        ) : priv.length ? (
          <View style={{ gap: 8, marginTop: space.sm }}>{priv.map((r) => rowView(r))}</View>
        ) : !loading ? (
          // MSG.22a — личных пока нет.
          <View style={s.empty}>
            <Text style={s.emptyTitle}>{MSG.noPrivate()}</Text>
            <Text style={s.emptyNote}>{MSG.noPrivateNote()}</Text>
          </View>
        ) : null}
      </ScrollView>

      <Sheet visible={!!menuRow} onClose={() => setMenuRow(null)} title={menuRow?.title}>
        {sheet}
      </Sheet>

      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav active="messages" />
      </View>
    </View>
  );
}

/** Совпадение с запросом — красным, как на кадре MSG.02. */
function Hl({ text, q, style }: { text: string; q: string; style: any }) {
  const needle = q.trim().toLowerCase();
  if (!needle) return <Text style={style} numberOfLines={1}>{text}</Text>;
  const parts: { t: string; on: boolean }[] = [];
  const low = text.toLowerCase();
  let i = 0;
  while (i < text.length) {
    const j = low.indexOf(needle, i);
    if (j < 0) { parts.push({ t: text.slice(i), on: false }); break; }
    if (j > i) parts.push({ t: text.slice(i, j), on: false });
    parts.push({ t: text.slice(j, j + needle.length), on: true });
    i = j + needle.length;
  }
  return (
    <Text style={style} numberOfLines={1}>
      {parts.map((p, k) => <Text key={k} style={p.on ? { color: color.primary } : undefined}>{p.t}</Text>)}
    </Text>
  );
}

// ============================================================ вид

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  top: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: space.lg, paddingBottom: space.md },
  title: { flex: 1, color: color.fg } as any,

  search: {
    flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: space.lg, marginBottom: space.md,
    height: 48, paddingHorizontal: 16,
  },
  searchInput: { flex: 1, color: color.fg, fontSize: 16, paddingVertical: 0 },

  segs: { flexDirection: 'row', gap: 8, paddingHorizontal: space.lg, paddingBottom: space.xs },
  seg: {
    height: 36, paddingHorizontal: 16, borderRadius: rad.full,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
  },
  segOn: { backgroundColor: color.primary },
  segText: { ...type.labelSmall, color: color.fg } as any,
  segTextOn: { color: color.onPrimary, fontWeight: '700' },
  segBadge: { minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 5, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  segBadgeOn: { backgroundColor: color.onPrimary },
  segBadgeText: { fontSize: 10, fontWeight: '700', color: color.onPrimary },
  segBadgeTextOn: { color: color.primary },

  body: { paddingHorizontal: space.lg, gap: 4 },
  section: { ...type.title, color: color.fg } as any,
  sectionNote: { ...type.caption, color: color.fg } as any,

  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: color.glassCard, borderRadius: rad.lg, padding: 12,
  },
  archRow: { marginTop: space.md, paddingVertical: 16 },
  line: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  ava: { width: 48, height: 48, borderRadius: 24, backgroundColor: color.neutral100 },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  rowTitle: { flex: 1, fontSize: 16, fontWeight: '700', color: color.fg } as any,
  rowTime: { fontSize: 12, color: color.muted } as any,
  rowSub: { fontSize: 11, color: color.muted } as any,
  rowTeaser: { fontSize: 13, color: color.fg } as any,
  badge: {
    minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 5,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
  },
  badgeMuted: { backgroundColor: color.neutral400 },
  badgeText: { fontSize: 10, fontWeight: '700', color: color.onPrimary } as any,
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.primary },

  /** MSG.01a / 02a / 22a — пустое состояние слева, сразу под вкладками. */
  empty: { gap: 4, paddingTop: space.md },
  emptyTitle: { ...type.title, color: color.fg } as any,
  emptyNote: { ...type.bodySmall, color: color.fg } as any,
  cta: {
    marginTop: space.md, height: 48, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  ctaText: { ...type.button, color: color.onPrimary } as any,

  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
