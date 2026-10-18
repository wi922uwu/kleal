/**
 * Кто в группе — кадр GR.24 борда «GR · Offline — new layout» (5828:9794).
 *
 * СТРАНИЦА, А НЕ ЛИСТ. Раньше состав открывался листом поверх чата, и на нём же жили «О затее»,
 * удаление и выход. На борде это отдельная страница того же вида, что план (GR.26): шапка с
 * названием, «Who's in» и пояснение, карточка затеи с обложкой, строки людей с временем прихода и
 * три кнопки. Такая страница открывается из меню «⋮ → Group info» и по нажатию на шапку чата.
 *
 * Удаление и закрытие живут в чате (листы GR.24a/GR.51 и GR.24b): кнопки здесь возвращают туда
 * и открывают нужный лист. Второй экземпляр тех же листов разошёлся бы с первым при первой правке.
 */
import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Image, ActivityIndicator, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { group as gapi, mediaUrl, ensureMe, isMe, pidOf, type GroupInfo } from '../src/api';
import { ROOM, GINVITE, groupPlace, groupCallLine, isOnlineGroup } from '../src/groups';
import { msgTime } from '../src/chat';
import { usePolling } from '../src/polling';
import { IconCalendar, IconClock, IconPerson, IconPin, IconShieldCheck, IconVideo } from '../src/components/icons';
import { color, font, heading, labelFamily, space, type } from '../src/theme';
import { Cover } from '../src/components/Cover';
import { GlassPill } from '../src/components/Glass';
import { GlassBack, GlassSurface } from '../src/components/LiquidGlass';
import { BottomNav } from '../src/components/BottomNav';
import { useNavCollapse } from '../src/navScroll';

const INK = '#181B22';

/** «Thu 23 July, 19:00» / «Чт, 23 июл. · 19:00» → дата и время отдельно: у каждого свой знак. */
function splitWhen(when: string): [string, string] {
  const m = when.match(/^(.*?)(?:\s*[·,]\s*)(\d{1,2}[:.]\d{2}(?:\s*[AaPp][Mm])?)$/);
  return m ? [m[1], m[2]] : [when, ''];
}

export default function GroupMembers() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ gid?: string }>();
  const gid = String(params.gid || '').trim();
  const me = String(st.profile.name || '');
  const [g, setG] = useState<GroupInfo | null>(null);
  const [gone, setGone] = useState(false);
  const [, setMeKnown] = useState('');
  useEffect(() => { ensureMe().then(setMeKnown); }, []);

  const load = useCallback(async () => {
    if (!gid || !me) return;
    try {
      const r: any = await gapi.get(gid, me);
      if (r?.group) setG(r.group); else if (r?.error) setGone(true);
    } catch { /* фоновый опрос — молча */ }
  }, [gid, me]);
  useEffect(() => { load(); }, [load]);
  usePolling(load, 8000, !gone);

  const back = () => (router.canGoBack() ? router.back() : router.replace({ pathname: '/group', params: { gid } }));
  /** Вернуться в чат и открыть там лист: удаление (GR.24a) или закрытие (GR.24b). */
  const toChat = (act?: 'remove' | 'end') =>
    router.dismissTo({ pathname: '/group', params: act ? { gid, act } : { gid } });

  const members = ((g?.members || []) as any[]);
  const n = Number(g?.joined_count || members.length || 0);
  const max = Number(g?.max_total || 3);
  const open = (g?.invites || []).length;
  const iOwn = !!g?.i_am_owner;
  const readOnly = !!g?.read_only;
  /** GR.54: группу закрыл организатор — страница говорит об этом, а не показывает кнопки. */
  const closed = g?.read_only_reason === 'group_closed';
  const hasPlan = !!(g as any)?.plan;
  const canRemove = iOwn && !hasPlan && !readOnly && n > 1;
  const [date, time] = splitWhen(String(g?.when || ''));
  const ownerId = String((g as any)?.owner_id || '');
  const ru = getLang() === 'ru';
  // Люди — как на кадре: сначала остальные в порядке прихода, ты — последним.
  const rows = [...members.filter((m) => !isMe(m.name, pidOf(m, 'name'), me)),
                ...members.filter((m) => isMe(m.name, pidOf(m, 'name'), me))];

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      {/* Фон — ровный «Ambient · glass pilot» #F5F1EC (s.wrap), без пятен: так на новом борде раздела A (6864:115809), как и в мастере создания. */}
      {/* Шапка GR.24: стеклянная «назад» и название затеи гарнитурой шапок 20/24. */}
      <View style={s.head}>
        <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={back} />
        <Text style={[s.headTitle, heading(lang, type.headingSm)]} numberOfLines={1}>{g?.title || ''}</Text>
      </View>

      <ScrollView onScroll={navCollapse} scrollEventThrottle={16} contentContainerStyle={s.body}>
        {!g && !gone ? <ActivityIndicator style={{ marginTop: 24 }} color={color.primary} /> : null}
        {gone ? <Text style={s.note}>{ROOM.gone()}</Text> : null}
        {g ? (
          <>
            <View style={s.status}>
              <Text style={[s.title, { fontFamily: labelFamily(lang) }]}>{closed ? ROOM.closedPageTitle() : ROOM.infoTitle()}</Text>
              <Text style={s.note}>
                {closed ? ROOM.closedPageNote(String(g?.closure_notice?.owner || g?.owner || ''), String(g?.title || ''))
                  : ROOM.whoNote(n, max, open, canRemove)}
              </Text>
            </View>

            {/* Карточка затеи — «Plan Card · forming»: обложка 128 и под ней когда и где. */}
            <View style={s.cardShadow}>
              <GlassSurface tone="light" radius={20} style={s.card}>
                <Cover intent={g || {}} style={s.cover} />
                <View style={s.cardBody}>
                  {date || time ? (
                    <View style={s.cardRow}>
                      {date ? (
                        <View style={s.cardPair}>
                          <IconCalendar size={18} c={color.primary} />
                          <Text style={s.cardLine} numberOfLines={1}>{date}</Text>
                        </View>
                      ) : null}
                      {time ? (
                        <View style={s.cardPair}>
                          <IconClock size={18} c={color.primary} />
                          <Text style={s.cardLine}>{time}</Text>
                        </View>
                      ) : null}
                    </View>
                  ) : null}
                  <View style={s.cardRow}>
                    {isOnlineGroup(g) ? <IconVideo size={18} c={color.primary} /> : <IconPin size={18} c={color.primary} />}
                    <Text style={[s.cardLine, { flex: 1 }]} numberOfLines={1}>
                      {isOnlineGroup(g) ? groupCallLine(g, me) : groupPlace(g, me) || ROOM.aboutUnset()}
                    </Text>
                  </View>
                  {closed ? (
                    <View style={s.cardRow}>
                      <IconShieldCheck size={18} c="#238C62" />
                      <Text style={[s.cardLine, { flex: 1, color: '#238C62' }]} numberOfLines={1}>
                        {isOnlineGroup(g) ? GINVITE.linkOpens() : GINVITE.exactSpot()}
                      </Text>
                    </View>
                  ) : null}
                </View>
              </GlassSurface>
            </View>

            {/* Люди: «Jane, 28» и «In the group since ⏱ 14:28»; у организатора — метка и
                «Created the group ⏱ 14:24». */}
            <View>
              {rows.map((m, i) => {
                const nm = String(m.name || '');
                const mid = pidOf(m, 'name');
                const org = ownerId ? mid === ownerId : nm.toLowerCase() === String(g?.owner || '').toLowerCase();
                const mine = isMe(nm, mid, me);
                const at = Number(org ? ((g as any)?.created || m.joined || 0) : (m.joined || 0));
                return (
                  <View key={nm + i} style={s.memberRow}>
                    <View style={[s.av, s.avEmpty]}>
                      <IconPerson size={18} />
                      {m.photo ? <Image source={{ uri: mediaUrl(String(m.photo)) }} style={[s.av, StyleSheet.absoluteFill]} /> : null}
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={s.nameRow}>
                        <Text style={s.memberName} numberOfLines={1}>
                          {mine ? T('Ты', 'You', 'Tú') : ROOM.nameAge(nm, m.age)}
                        </Text>
                        {org ? (
                          <View style={s.orgBadge}><Text style={s.orgText}>{ROOM.roleOrganiser().toLowerCase()}</Text></View>
                        ) : null}
                      </View>
                      <View style={s.sinceRow}>
                        <Text style={s.since}>
                          {closed ? (org ? ROOM.closedTheGroup() : ROOM.wasInGroup()) : org ? ROOM.createdGroup() : ROOM.memberSince()}
                        </Text>
                        {at && !closed ? (
                          <>
                            <IconClock size={14} c={INK} />
                            <Text style={s.since}>{msgTime(at, ru)}</Text>
                          </>
                        ) : null}
                      </View>
                    </View>
                  </View>
                );
              })}
            </View>

            {/* Кнопки GR.24: чат — главная, удалить и закрыть — стеклянные. Участнику, который
                не организатор, вместо них «Выйти из группы». */}
            <View style={s.actions}>
              {closed ? (
                <GlassPill tone="brand" small style={s.pill} label={GINVITE.gotIt()} onPress={() => router.dismissTo('/home')} />
              ) : (
              <GlassPill tone="brand" small style={s.pill} label={T('Открыть чат группы', 'Open group chat', 'Abrir el chat del grupo')}
                         onPress={() => toChat()} />
              )}
              {canRemove ? (
                <GlassPill small style={s.pill} label={ROOM.optRemove()} onPress={() => toChat('remove')} />
              ) : null}
              {/* GR.24: «End the group» — тихая строка без подложки («Button/Button» без заливки, 40):
                  необратимое действие не должно спорить за внимание с «Open group chat». */}
              {/* Закрыть может только организатор и только живую группу: на закрытой (GR.54) кнопки
                  нет ни у кого — даже если сервер по старой памяти прислал can_end. */}
              {g?.can_end && iOwn && !readOnly ? (
                <Pressable accessibilityRole="button" style={s.quiet} onPress={() => toChat('end')} hitSlop={6}>
                  <Text style={s.quietText}>{ROOM.endGroup()}</Text>
                </Pressable>
              ) : null}
              {!iOwn && !readOnly ? (
                <GlassPill small style={s.pill} label={ROOM.leave()} onPress={() => router.dismissTo({ pathname: '/group', params: { gid, act: 'leave' } })} />
              ) : null}
            </View>
          </>
        ) : null}
      </ScrollView>
      <BottomNav active="intents" />
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, height: 56 },
  headTitle: { flex: 1, color: INK } as any,
  body: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: space.xl, gap: 14 },
  status: { gap: 4 },
  title: { fontSize: 15, lineHeight: 20, color: INK } as any,
  note: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: INK } as any,
  cardShadow: {
    borderRadius: 20,
    shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 5 },
  },
  card: { overflow: 'hidden' },
  cover: { height: 128, backgroundColor: color.neutral100 },
  cardBody: { paddingHorizontal: 16, paddingVertical: 16, gap: 8 },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardPair: { flexDirection: 'row', alignItems: 'center', gap: 4, marginRight: 8, flexShrink: 1 },
  cardLine: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: INK } as any,
  memberRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56 },
  av: { width: 40, height: 40, borderRadius: 999 },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  memberName: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: INK, flexShrink: 1 } as any,
  orgBadge: { height: 16, paddingHorizontal: 8, borderRadius: 99, backgroundColor: '#CFE3FF', justifyContent: 'center' },
  orgText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#1F58BE' } as any,
  sinceRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  since: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: INK } as any,
  actions: { gap: 8, paddingTop: 4 },
  /** 44, а не 40 кадра: ниже 44 палец промахивается (HIG) — то же решение, что на плане. */
  /** Кнопки кадра GR.24 — 40 высотой. */
  pill: { height: 40 },
  quiet: { height: 40, alignItems: 'center', justifyContent: 'center' },
  quietText: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg } as any,
});
