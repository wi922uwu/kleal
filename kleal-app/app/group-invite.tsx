/** Explicit incoming group invitation. Compatible public group intents never reach this screen. */
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { group, newIdem } from '../src/api';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { IconCalendar, IconChevronLeft, IconGroups, IconPin } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

export default function GroupInvite() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const st = useOnb();
  const me = String(st.profile.name || '');
  const { id } = useLocalSearchParams<{ id?: string }>();
  const wantedId = String(id || '');
  const [row, setRow] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [joined, setJoined] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    try {
      const r: any = await group.mine(me);
      const rows: any[] = r?.invites || [];
      setRow(rows.find((x) => String(x?.invite?.id || '') === wantedId) || null);
    } catch {
      setErr(T('Не удалось загрузить приглашение.', 'Could not load the invitation.', 'No se pudo cargar la invitación.'));
    } finally {
      setLoading(false);
    }
  }, [me, wantedId]);

  useEffect(() => { load(); }, [load]);

  const answer = async (accept: boolean) => {
    if (!row?.invite?.id || busy) return;
    setBusy(true);
    setErr('');
    try {
      const r: any = await group.respondInvite(row.invite.id, me, accept, newIdem('group-invite-response'));
      if (!r?.ok) {
        const messages: Record<string, string> = {
          GROUP_FULL: T('В группе уже нет свободных мест.', 'This group is already full.', 'Este grupo ya está lleno.'),
          EXPIRED: T('Срок приглашения истёк.', 'This invitation has expired.', 'Esta invitación ha expirado.'),
          CLOSED: T('Эта группа уже закрыта.', 'This group is already closed.', 'Este grupo ya está cerrado.'),
          NOT_ELIGIBLE: T('Условия участия изменились.', 'Participation requirements have changed.', 'Los requisitos de participación han cambiado.'),
        };
        throw new Error(messages[String(r?.error || '')] || T('Приглашение больше недоступно.', 'This invitation is no longer available.', 'Esta invitación ya no está disponible.'));
      }
      if (accept) {
        setJoined(true);
        setRow((old: any) => ({ ...old, group: r.group || old.group }));
      } else {
        router.dismissTo('/home');
      }
    } catch (e: any) {
      setErr(String(e?.message || T('Не удалось ответить.', 'Could not respond.', 'No se pudo responder.')));
    } finally {
      setBusy(false);
    }
  };

  const inv = row?.invite || {};
  const group = row?.group || {};
  const from = String(inv.from || group.owner || '');
  const members = Number(group.joined_count || 0);
  const capacity = Number(group.max_total || 0);
  const ended = inv.state === 'group_ended' || group.state === 'ended';

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} style={s.back} onPress={() => (router.canGoBack() ? router.back() : router.dismissTo('/home'))}>
          <IconChevronLeft />
        </Pressable>
        <Text style={s.headTitle} numberOfLines={1}>{group.title || T('Приглашение в группу', 'Group invitation', 'Invitación de grupo')}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={s.body}>
        {loading ? <ActivityIndicator color={color.primary} style={{ marginTop: space.xl }} /> : null}
        {!loading && !row ? <Text style={s.note}>{T('Приглашение больше недоступно.', 'This invitation is no longer available.', 'Esta invitación ya no está disponible.')}</Text> : null}

        {row ? (
          <>
            <Text style={s.title}>
              {ended
                ? T('Эта группа завершена', 'This group has ended', 'Este grupo ha terminado')
                : joined
                  ? T('Ты присоединился к группе', 'You joined the group', 'Te uniste al grupo')
                  : T(`${from} приглашает тебя`, `${from} invited you`, `${from} te invitó`)}
            </Text>
            {inv.note ? <Text style={s.note}>{String(inv.note)}</Text> : null}

            <View style={s.card}>
              <View style={s.hero}><IconGroups size={46} c={color.onPrimary} /></View>
              <Text style={s.cardTitle}>{String(group.title || '')}</Text>
              {group.when ? <Meta icon={<IconCalendar />} text={String(group.when)} /> : null}
              {group.area ? <Meta icon={<IconPin size={16} c={color.muted} />} text={String(group.area)} /> : null}
              <Meta
                icon={<IconGroups size={16} c={color.muted} />}
                text={capacity ? T(`${members} из ${capacity} участников`, `${members} of ${capacity} people`, `${members} de ${capacity} personas`) : T(`${members} участников`, `${members} people`, `${members} personas`)}
              />
            </View>

            {err ? <Text style={s.err}>{err}</Text> : null}

            {ended ? (
              <Text style={s.note}>{T('Организатор завершил группу. Приглашение больше не действует.',
                                      'The organiser ended the group. This invite is no longer available.', 'El organizador terminó el grupo. Esta invitación ya no está disponible.')}</Text>
            ) : joined ? (
              <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.dismissTo('/home')}>
                <Text style={s.ctaText}>{T('Готово', 'Done', 'Hecho')}</Text>
              </Pressable>
            ) : (
              <>
                <Pressable accessibilityRole="button" accessibilityState={{ busy }} style={s.cta} onPress={() => answer(true)}>
                  {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{T('Присоединиться', 'Join', 'Únete')}</Text>}
                </Pressable>
                <Pressable accessibilityRole="button" disabled={busy} style={s.soft} onPress={() => answer(false)}>
                  <Text style={s.softText}>{T('Не в этот раз', 'Not this time', 'No esta vez')}</Text>
                </Pressable>
              </>
            )}
          </>
        ) : null}
      </ScrollView>

      <View style={s.nav}><BottomNav /></View>
    </View>
  );
}

function Meta({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <View style={s.meta}><View>{icon}</View><Text style={s.metaText}>{text}</Text></View>;
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: space.sm },
  back: { width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center' },
  headTitle: { flex: 1, ...type.title, color: color.fg, textAlign: 'center' } as any,
  body: { padding: 20, paddingBottom: 130, gap: space.md },
  title: { fontSize: 21, lineHeight: 28, fontWeight: '700', color: color.fg },
  note: { ...type.bodySmall, color: color.muted } as any,
  card: { padding: space.lg, borderRadius: rad.xl, backgroundColor: color.card, gap: space.md },
  hero: { height: 120, borderRadius: rad.lg, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  cardTitle: { ...type.title, color: color.fg } as any,
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  metaText: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  soft: { height: 50, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  softText: { ...type.button, color: color.fg } as any,
  nav: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
