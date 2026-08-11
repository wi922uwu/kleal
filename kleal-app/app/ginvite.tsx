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
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { group as gapi, mediaUrl, newIdem, type GroupInfo } from '../src/api';
import { GINVITE, ROOM } from '../src/groups';
import { IconChevronLeft, IconPerson, IconCalendar, IconPin } from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

export default function GroupInvite() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();

  const params = useLocalSearchParams<{ id?: string; gid?: string }>();
  const id = String(params.id || '').trim();
  const gid = String(params.gid || '').trim();
  const me = String(st.profile.name || '');

  const [g, setG] = useState<GroupInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  /** Итог ответа — им же экран и заканчивается: показать результат честнее, чем молча уйти. */
  const [outcome, setOutcome] = useState<'' | 'declined' | 'awaiting' | 'full' | 'gone' | 'error'>('');

  /**
   * Карточку группы читаем ДО согласия. Не участнику сервер не отдаст ни чат, ни состав
   * (NOT_A_MEMBER) — а вот сама группа читается: именно из неё берутся «кто уже внутри» и число
   * мест, которые GR.16 обещает показать приглашённому.
   */
  const load = useCallback(async () => {
    if (!gid || !me) { setLoading(false); return; }
    try {
      const r: any = await gapi.get(gid, me);
      if (r?.group) setG(r.group);
      else setOutcome('gone');
    } catch {
      setOutcome('gone');
    } finally {
      setLoading(false);
    }
  }, [gid, me]);

  useEffect(() => { load(); }, [load]);

  const answer = async (accept: boolean) => {
    if (busy || !id) return;
    setBusy(true);
    try {
      const r: any = await gapi.respondInvite(id, me, accept, newIdem('gir'));
      if (!accept) { setOutcome('declined'); return; }
      if (r?.awaiting_approval) { setOutcome('awaiting'); return; }
      if (r?.error === 'GROUP_FULL') { setOutcome('full'); return; }
      if (!r?.ok) { setOutcome(r?.error === 'NO_SUCH_INVITE' ? 'gone' : 'error'); return; }
      // Вошёл — сразу в общий чат, как и обещано на GR.16. replace, а не push: приглашения
      // больше нет, и «назад» не должно возвращать к нему.
      router.replace({ pathname: '/group', params: { gid } });
    } catch {
      setOutcome('error');
    } finally {
      setBusy(false);
    }
  };

  const members = (g?.members || []) as { name?: string; photo?: string }[];
  const joined = Number(g?.joined_count || members.length || 0);
  const max = Number(g?.max_total || 5);
  const min = Number(g?.min_total || 3);
  const owner = String(g?.owner || '');

  const back = () => (router.canGoBack() ? router.back() : router.replace('/messages'));

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={back}>
          <IconChevronLeft />
        </Pressable>
        <Text style={s.headTitle} numberOfLines={1}>
          {g?.title || T('Приглашение', 'Invite')}
        </Text>
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        {loading ? <ActivityIndicator style={{ marginTop: 40 }} color={color.primary} /> : null}

        {!loading && outcome ? (
          <Text style={s.outcome}>
            {outcome === 'declined' ? GINVITE.declined()
              : outcome === 'awaiting' ? GINVITE.awaiting()
              : outcome === 'full' ? GINVITE.full(String(g?.title || ''), max)
              : outcome === 'gone' ? GINVITE.gone()
              : GINVITE.failed()}
          </Text>
        ) : null}

        {!loading && !outcome && g ? (
          <>
            <Text style={s.title}>{GINVITE.title(owner, String(g.title || ''))}</Text>
            <Text style={s.note}>{GINVITE.note()}</Text>

            {/* Карточка интента — когда и где, если группа это назвала. Ссылки на звонок здесь
                нет и быть не может: её приносит план позже, уже подтвердившим. */}
            <View style={s.card}>
              <Text style={s.cardTitle} numberOfLines={2}>{g.title}</Text>
              {g.when ? (
                <View style={s.metaRow}>
                  <IconCalendar />
                  <Text style={s.meta}>{String(g.when)}</Text>
                </View>
              ) : null}
              {g.area ? (
                <View style={s.metaRow}>
                  <IconPin size={15} c={color.muted} />
                  <Text style={s.meta} numberOfLines={1}>{String(g.area)}</Text>
                </View>
              ) : null}
              <Text style={s.seats}>{GINVITE.seats(joined, max, min)}</Text>
            </View>

            <Text style={s.section}>{GINVITE.whosIn()}</Text>
            {members.map((m, i) => {
              const nm = String(m.name || '');
              const isOwner = nm.trim().toLowerCase() === owner.trim().toLowerCase();
              return (
                <View key={nm + i} style={s.memberRow}>
                  {/* Заглушка снизу, фото сверху — как в app/gplan.tsx. */}
                  <View style={[s.memberAv, s.memberAvEmpty]}>
                    <IconPerson size={18} />
                    {m.photo ? (
                      <Image source={{ uri: mediaUrl(String(m.photo)) }}
                             style={[s.memberAv, StyleSheet.absoluteFillObject]} />
                    ) : null}
                  </View>
                  <Text style={s.memberName} numberOfLines={1}>{nm}</Text>
                  <Text style={s.memberRole}>
                    {isOwner ? ROOM.roleOrganiser() : ROOM.roleMember()}
                  </Text>
                </View>
              );
            })}
          </>
        ) : null}
      </ScrollView>

      {!loading && !outcome && g ? (
        <View style={[s.foot, { paddingBottom: Math.max(insets.bottom, 16) }]}>
          <Pressable accessibilityRole="button" accessibilityState={{ busy }} style={s.cta}
                     onPress={busy ? undefined : () => answer(true)}>
            {busy ? <ActivityIndicator color={color.onPrimary} />
                  : <Text style={s.ctaText}>{GINVITE.join()}</Text>}
          </Pressable>
          <Pressable accessibilityRole="button" style={s.ghost}
                     onPress={busy ? undefined : () => answer(false)}>
            <Text style={s.ghostText}>{GINVITE.notThisTime()}</Text>
          </Pressable>
        </View>
      ) : !loading && outcome ? (
        <View style={[s.foot, { paddingBottom: Math.max(insets.bottom, 16) }]}>
          <Pressable accessibilityRole="button" style={s.cta} onPress={back}>
            <Text style={s.ctaText}>{T('Понятно', 'Got it')}</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

// ============================================================ вид

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  headTitle: { flex: 1, ...type.title, color: color.fg, fontWeight: '700' } as any,

  scroll: { paddingHorizontal: 20, paddingBottom: space.xl, gap: space.md },
  title: { fontSize: 22, lineHeight: 30, fontWeight: '700', color: color.fg },
  note: { ...type.bodySmall, color: color.muted } as any,
  outcome: { ...type.body, color: color.fg, marginTop: space.lg } as any,

  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: 8 },
  cardTitle: { ...type.title, color: color.fg, fontWeight: '700' } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  meta: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  seats: { ...type.caption, color: color.muted, marginTop: 4 } as any,

  section: { ...type.labelMedium, color: color.fg, fontWeight: '700', marginTop: space.sm } as any,
  memberRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  memberAv: { width: 36, height: 36, borderRadius: rad.full },
  memberAvEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  memberName: { flex: 1, ...type.body, color: color.fg } as any,
  memberRole: { ...type.caption, color: color.muted } as any,

  foot: { paddingHorizontal: 20, paddingTop: space.md, gap: space.sm },
  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  ghost: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  ghostText: { ...type.button, color: color.fg } as any,
});
