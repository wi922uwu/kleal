/**
 * Входящее ГРУППОВОЕ приглашение — сторона гостя.
 *
 * UX-КАРКАС: вид натянется поверх; копия — в src/groups.ts (GINVITE).
 *
 * Своего кадра у борда нет, и это не пропуск: GR.16 описывает этот экран словами, от лица
 * отправителя — «She sees the intent and who is already in. If she accepts she joins the shared
 * group chat straight away — there is no private chat with you». Экран построен ровно по этому
 * обещанию, а раскладка взята у 1:1-приглашения (O.C1, app/invite.tsx): задача та же.
 *
 * Три ответа сервера, и каждый показывается своим текстом, а не общим «не получилось»:
 *   ok                         — вошёл, сразу в комнату;
 *   awaiting_approval: true    — план уже обсуждают, вход подтверждает организатор;
 *   GROUP_FULL                 — места кончились, пока человек думал (GR.22, «Nothing you did»).
 */
import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Image, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useLang, T, dateLocale } from '../src/i18n';
import { useOnb } from '../src/state';
import { group as gapi, mediaUrl, newIdem, pidOf, myId, ensureMe, type GroupInfo } from '../src/api';
import { GINVITE, ROOM, groupCallLine, isOnlineGroup } from '../src/groups';
import { IconPerson, IconCalendar, IconPin, IconClock, IconShieldCheck, IconVideo } from '../src/components/icons';
import { color, font, heading, labelFamily, space, type } from '../src/theme';
import { Cover } from '../src/components/Cover';
import { GlassPill } from '../src/components/Glass';
import { GlassBack, GlassSurface } from '../src/components/LiquidGlass';
import { BottomNav } from '../src/components/BottomNav';
import { useNavCollapse } from '../src/navScroll';

export default function GroupInvite() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();

  const params = useLocalSearchParams<{ id?: string; gid?: string }>();
  const id = String(params.id || '').trim();
  const gid = String(params.gid || '').trim();
  const me = String(st.profile.name || '');

  const [g, setG] = useState<GroupInfo | null>(null);
  const [groupId, setGroupId] = useState(gid);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  /** Итог ответа — им же экран и заканчивается: показать результат честнее, чем молча уйти. */
  const [outcome, setOutcome] = useState<'' | 'declined' | 'awaiting' | 'full' | 'gone' | 'ineligible' | 'error'>('');
  /** GR.56a: приглашение закрылось само — почему (full / converted / closed / expired). */
  const [closed, setClosed] = useState('');
  /** Кто позвал — из самого приглашения: состав закрытой группы постороннему не отдаётся. */
  const [inviter, setInviter] = useState<{ name: string; photo: string; age?: number } | null>(null);
  const [, setMeKnown] = useState('');
  useEffect(() => { ensureMe().then(setMeKnown); }, []);

  /**
   * Карточку группы читаем ДО согласия. Не участнику сервер не отдаст ни чат, ни состав
   * (NOT_A_MEMBER) — а вот сама группа читается: именно из неё берутся «кто уже внутри» и число
   * мест, которые GR.16 обещает показать приглашённому.
   */
  const load = useCallback(async () => {
    if (!me || (!id && !gid)) { setLoading(false); return; }
    try {
      const r: any = id ? await gapi.inviteDetail(id, me) : await gapi.get(gid, me);
      if (r?.group) {
        setG(r.group);
        setGroupId(String(r.group.gid || r.invite?.gid || gid));
        setClosed(String(r.invite?.closed || ''));
        // Уже сказал «да», ждёт организатора (state awaiting_approval) — при повторном заходе экран
        // говорит это сразу, а не предлагает ответить ещё раз.
        if (!r.invite?.closed && String(r.invite?.state || '') === 'awaiting_approval') setOutcome('awaiting');
        if (r.invite?.from) setInviter({ name: String(r.invite.from), photo: String(r.invite.from_photo || ''),
                                         age: r.invite.from_age || undefined });
      } else {
        setOutcome('gone');
      }
    } catch {
      // Compatibility fallback while older matching instances are rolling over.
      if (gid) {
        try {
          const r: any = await gapi.get(gid, me);
          if (r?.group) {
            setG(r.group);
            setGroupId(gid);
            return;
          }
        } catch { /* closed invitation */ }
      }
      setOutcome('gone');
    } finally {
      setLoading(false);
    }
  }, [gid, id, me]);

  useEffect(() => { load(); }, [load]);

  const answer = async (accept: boolean) => {
    if (busy || !id) return;
    setBusy(true);
    try {
      const r: any = await gapi.respondInvite(id, me, accept, newIdem('gir'));
      if (!accept) { setOutcome('declined'); return; }
      if (r?.awaiting_approval) { setOutcome('awaiting'); return; }
      if (r?.error === 'GROUP_FULL') { setOutcome('full'); return; }
      /*
        ОСТАЛЬНЫЕ КОДЫ — СВОИМИ СЛОВАМИ (сверка п. 16). Раньше разбирались только GROUP_FULL и
        NO_SUCH_INVITE, а всё прочее шло в «Попробуй ещё раз» — и по кругу, потому что сервер на
        закрытое приглашение будет отвечать тем же. Уже вступил — в чат; закрылось — перечитываем
        карточку и показываем «Приглашение закрыто» с причиной; правила не пускают — так и пишем.
      */
      if (r?.error === 'ACCEPTED') { router.replace({ pathname: '/group', params: { gid: groupId } }); return; }
      if (r?.error === 'NOT_ELIGIBLE') { setOutcome('ineligible'); return; }
      const CLOSED_WHY: Record<string, string> = {
        EXPIRED: 'expired', WITHDRAWN: 'withdrawn', GROUP_CLOSED: 'closed', CLOSED: 'closed', POLICY_REVOKED: 'closed',
      };
      if (r?.error && CLOSED_WHY[r.error]) {
        const d: any = await gapi.inviteDetail(id, me).catch(() => null);
        if (d?.group) setG(d.group);
        setClosed(String(d?.invite?.closed || CLOSED_WHY[r.error]));
        return;
      }
      if (!r?.ok) { setOutcome(r?.error === 'NO_SUCH_INVITE' ? 'gone' : 'error'); return; }
      // Вошёл — сразу в общий чат, как и обещано на GR.16. replace, а не push: приглашения
      // больше нет, и «назад» не должно возвращать к нему.
      router.replace({ pathname: '/group', params: { gid: groupId } });
    } catch {
      setOutcome('error');
    } finally {
      setBusy(false);
    }
  };

  const members = (g?.members || []) as { name?: string; photo?: string }[];
  const joined = Number(g?.joined_count || members.length || 0);
  const max = Number(g?.max_total || 5);
  const owner = String(g?.owner || inviter?.name || '');
  const ownerId = String((g as any)?.owner_id || '');
  /** «Thu 23 July, 19:00» → дата и время раздельно, у каждого свой знак. */
  const whenParts = ((): [string, string] => {
    const w = String(g?.when || '');
    const m = w.match(/^(.*?)\s*(?:·|,)\s*(\d{1,2}[:.]\d{2}(?:\s*[AaPp][Mm])?)$/);
    return m ? [m[1], m[2]] : [w, ''];
  })();

  const inside = members.map((m) => String(m.name || '')).filter(Boolean);
  /** «on Thursday» (GR.56) — день недели из даты затеи; нет даты — без дня, не выдумываем. */
  const weekday = (() => {
    const k = String((g as any)?.date_key || (g as any)?.intent?.dateKey || '');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(k)) return '';
    return new Date(k + 'T12:00:00').toLocaleDateString(dateLocale(), { weekday: 'long' });
  })();

  const back = () => (router.canGoBack() ? router.back() : router.replace('/messages'));

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      {/* Фон — ровный «Ambient · glass pilot» #F5F1EC (s.wrap), без пятен: так на новом борде раздела A (6864:115809), как и в мастере создания. */}
      {/* Кадр GR.56: стеклянная «назад» и название затеи слева гарнитурой шапок. */}
      <View style={s.head}>
        <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={back} />
        <Text style={[s.headTitle, heading(lang, type.headingSm)]} numberOfLines={1}>
          {g?.title || T('Приглашение', 'Invite', 'Invitar')}
        </Text>
      </View>

      <ScrollView onScroll={navCollapse} scrollEventThrottle={16} contentContainerStyle={s.scroll}>
        {loading ? <ActivityIndicator style={{ marginTop: 40 }} color={color.primary} /> : null}

        {!loading && outcome ? (
          <Text style={s.outcome}>
            {outcome === 'declined' ? GINVITE.declined()
              : outcome === 'awaiting' ? GINVITE.awaiting()
              : outcome === 'full' ? GINVITE.full(String(g?.title || ''), max)
              : outcome === 'gone' ? GINVITE.gone()
              : outcome === 'ineligible' ? GINVITE.notEligible()
              : GINVITE.failed()}
          </Text>
        ) : null}

        {!loading && !outcome && g ? (
          <>
            {/* GR.56: кто позвал и что это; GR.56a: приглашение закрылось и почему — без вины. */}
            <View style={s.status}>
              <Text style={[s.title, { fontFamily: labelFamily(lang) }]}>
                {closed ? GINVITE.closedTitle() : GINVITE.invitedYou(owner)}
              </Text>
              <Text style={s.note}>
                {closed
                  ? GINVITE.closedNote(closed, String(g.title || ''), owner)
                  : GINVITE.inviteNote2(
                      isOnlineGroup(g) ? GINVITE.inviteWhatCall(String(g.title || ''), weekday, max)
                        : GINVITE.inviteWhat(String(g.title || ''), String(g.area || ''), weekday, max),
                      // Кто внутри — по составу; если сервер постороннему состав не отдал, внутри
                      // как минимум тот, кто позвал (иначе выходило «. is in» без имени).
                      ROOM.andList(inside.length ? inside : (owner ? [owner] : [])),
                      Math.max(0, max - Math.max(joined, inside.length || (owner ? 1 : 0))))}
              </Text>
            </View>

            {/* Карточка затеи — «Plan Card · forming»: обложка, дата и время раздельно, место и
                зелёная строка «Exact spot after everyone confirms»: точный адрес откроется позже. */}
            <View style={s.cardShadow}>
              <GlassSurface tone="light" radius={20} style={s.card}>
                <Cover intent={g} style={s.cover} />
                <View style={s.cardBody}>
                  {g.when ? (
                    <View style={s.metaRow}>
                      <IconCalendar size={18} c={color.primary} />
                      <Text style={s.meta} numberOfLines={1}>{whenParts[0]}</Text>
                      {whenParts[1] ? (
                        <>
                          <IconClock size={18} c={color.primary} />
                          <Text style={s.meta}>{whenParts[1]}</Text>
                        </>
                      ) : null}
                    </View>
                  ) : null}
                  {isOnlineGroup(g) ? (
                    <View style={s.metaRow}>
                      <IconVideo size={18} c={color.primary} />
                      <Text style={s.meta} numberOfLines={1}>{groupCallLine(g)}</Text>
                    </View>
                  ) : g.area ? (
                    <View style={s.metaRow}>
                      <IconPin size={18} c={color.primary} />
                      <Text style={s.meta} numberOfLines={1}>{String(g.area)}</Text>
                    </View>
                  ) : null}
                  <View style={s.metaRow}>
                    <IconShieldCheck size={18} c="#238C62" />
                    <Text style={[s.meta, { color: '#238C62' }]} numberOfLines={1}>
                      {isOnlineGroup(g) ? GINVITE.linkOpens() : GINVITE.exactSpot()}
                    </Text>
                  </View>
                </View>
              </GlassSurface>
            </View>

            {/* Люди: организатор «Invited you», остальные «In the group», ты — последним. */}
            <View>
              {(members.length ? members
                : inviter ? [{ name: inviter.name, photo: inviter.photo, age: inviter.age } as any] : []).map((m, i) => {
                const nm = String(m.name || '');
                const isOwner = ownerId && pidOf(m, 'name') ? pidOf(m, 'name') === ownerId : nm.trim().toLowerCase() === owner.trim().toLowerCase();
                return (
                  <View key={nm + i} style={s.memberRow}>
                    <View style={[s.memberAv, s.memberAvEmpty]}>
                      <IconPerson size={18} />
                      {m.photo ? (
                        <Image source={{ uri: mediaUrl(String(m.photo)) }}
                               style={[s.memberAv, StyleSheet.absoluteFill]} />
                      ) : null}
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={s.nameRow}>
                        <Text style={s.memberName} numberOfLines={1}>{ROOM.nameAge(nm, (m as any).age)}</Text>
                        {isOwner ? (
                          <View style={s.orgBadge}><Text style={s.orgText}>{ROOM.roleOrganiser().toLowerCase()}</Text></View>
                        ) : null}
                      </View>
                      <Text style={s.memberRole}>{isOwner ? GINVITE.stInvitedYou() : ROOM.roleMember()}</Text>
                    </View>
                  </View>
                );
              })}
              <View style={s.memberRow}>
                <View style={[s.memberAv, s.memberAvEmpty]}>
                  <IconPerson size={18} />
                  {myId() ? <Image source={{ uri: mediaUrl(`/api/onboarding/photo/${encodeURIComponent(myId())}.jpg`) }} style={[s.memberAv, StyleSheet.absoluteFill]} /> : null}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.memberName}>{T('Ты', 'You', 'Tú')}</Text>
                  <Text style={s.memberRole}>{closed ? GINVITE.stDidntAnswer() : GINVITE.stAnswerNeeded()}</Text>
                </View>
              </View>
            </View>
          </>
        ) : null}
        {/* Кнопки — сразу под составом, как на кадрах GR.56/56a. */}
        {!loading && !outcome && g && closed ? (
          <View style={s.foot}>
            <GlassPill tone="brand" style={s.pill} label={GINVITE.gotIt()} onPress={() => router.dismissTo('/home')} />
          </View>
        ) : !loading && !outcome && g ? (
          <View style={s.foot}>
            <GlassPill tone="brand" style={s.pill} busy={busy} label={GINVITE.join()}
                       onPress={busy ? undefined : () => answer(true)} />
            <GlassPill style={s.pill} label={GINVITE.notThisTime()}
                       onPress={busy ? undefined : () => answer(false)} />
          </View>
        ) : !loading && outcome ? (
          <View style={s.foot}>
            <GlassPill tone="brand" style={s.pill} label={T('Понятно', 'Got it', 'Entendido')} onPress={back} />
          </View>
        ) : null}
      </ScrollView>

      {/* Панель внизу — как на кадре GR.56. */}
      <BottomNav active="intents" />
    </View>
  );
}

// ============================================================ вид

const INK = '#181B22';
const GREY = '#5A616E';

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, height: 56 },
  headTitle: { flex: 1, color: INK } as any,

  scroll: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: space.xl, gap: 12 },
  status: { gap: 4 },
  title: { fontSize: 15, lineHeight: 20, color: INK } as any,
  note: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: INK } as any,
  outcome: { fontFamily: font.text, fontSize: 15, lineHeight: 22, color: INK, marginTop: space.lg } as any,

  cardShadow: {
    borderRadius: 20,
    shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 5 },
  },
  card: { overflow: 'hidden' },
  cover: { height: 128, backgroundColor: color.neutral100 },
  cardBody: { padding: 16, gap: 8 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  meta: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: INK, flexShrink: 1 } as any,
  seats: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: GREY } as any,

  section: { fontSize: 15, lineHeight: 20, color: INK, marginTop: space.sm } as any,
  memberRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56 },
  memberAv: { width: 40, height: 40, borderRadius: 999 },
  memberAvEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  memberName: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: INK, flexShrink: 1 } as any,
  orgBadge: { height: 16, paddingHorizontal: 8, borderRadius: 99, backgroundColor: '#CFE3FF', justifyContent: 'center' },
  orgText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#1F58BE' } as any,
  /** Статус строки — чернилами, как на GR.56 («Invited you», «Your answer needed»). */
  memberRole: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: INK } as any,

  foot: { paddingTop: 2, gap: 8 },
  /** Кнопки GR.56 — 40 высотой. */
  pill: { height: 40 },
});
