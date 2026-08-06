/**
 * План встречи — кадр O.20.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор — в src/chat.ts.
 *
 * Экран живёт в двух состояниях, и это одно и то же место намеренно: пока плана нет — форма
 * (когда и где), как только он отправлен — карточка ожидания с кадра O.20. Разводить их по двум
 * маршрутам значило бы, что «Поправить план» ведёт куда-то ещё, а он ведёт сюда же.
 *
 * Правила плана — серверные, и оба называются словами:
 *   NOT_MATCHED — план можно отправить только тому, кто принял приглашение;
 *   IN_THE_PAST — время в прошлом сервер не принимает.
 *
 * Адрес после отправки виден не всегда: сервер отдаёт его только тому, кто подтвердил встречу, и
 * всегда — тому, кто его вписал (OF.C3). Экран показывает то, что пришло, и не достраивает.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image, ActivityIndicator,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { CHAT, planWhen, personStatus } from '../src/chat';
import { DETAILS, dateChips, hhmm, deviceTz, tzOffsetLabel } from '../src/intent';
import { TimeDial } from '../src/components/Dials';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { agent } from '../src/api';
import {
  IconChevronLeft, IconCalendar, IconClock, IconPin, IconLink, IconPerson, IconImagePlaceholder,
} from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

export default function Plan() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();

  const params = useLocalSearchParams<{ who?: string; title?: string; photo?: string; link?: string }>();
  const other = String(params.who || '').trim();
  const intentTitle = String(params.title || '').trim();
  const photo = String(params.photo || '');
  const link = String(params.link || '').trim();

  const me = String(st.profile.name || '');
  const ru = getLang() === 'ru';

  const [date, setDate] = useState(() => dateChips(1)[0].key);
  const [minutes, setMinutes] = useState(20 * 60);
  const [district, setDistrict] = useState(String(st.profile.city || ''));
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  /** Отправленный план в виде, в котором его отдаёт сервер. null — ещё форма. */
  const [plan, setPlan] = useState<any>(null);
  const polling = useRef<any>(null);

  const dates = useMemo(() => dateChips(), []);

  /** Ответ собеседника приходит не мгновенно — экран ожидания подтягивает состояние сам. */
  useEffect(() => {
    if (!plan || !me) return;
    polling.current = setInterval(async () => {
      try {
        const r: any = await agent.plans(me);
        const mine = (r?.plans || []).find((p: any) => p.id === plan.id);
        if (mine) setPlan(mine);
      } catch {
        /* тихо: фоновая дотяжка */
      }
    }, 5000);
    return () => clearInterval(polling.current);
  }, [plan?.id, me]);

  const propose = async () => {
    if (busy || !me || !other) return;
    setBusy(true);
    setErr('');
    try {
      const d = new Date(date + 'T00:00:00');
      d.setMinutes(minutes);
      const r: any = await agent.planPropose(me, other, {
        title: intentTitle || T('Встреча', 'Meetup'),
        mode: link ? 'online' : 'offline',
        starts_at: Math.floor(d.getTime() / 1000),
        when: `${planWhenLabel(date, minutes, ru)}`,
        district,
      });
      if (!r?.ok) {
        if (r?.error === 'NOT_MATCHED') throw new Error(CHAT.notMatched());
        if (r?.error === 'IN_THE_PAST') throw new Error(CHAT.inThePast());
        throw new Error(CHAT.planFailed());
      }
      // Сервер отдаёт план целиком; если нет — тянем его списком, чтобы показать настоящие статусы.
      if (r.plan) setPlan(r.plan);
      else {
        const list: any = await agent.plans(me);
        setPlan((list?.plans || []).find((p: any) => p.id === r.id) || { id: r.id });
      }
    } catch (e: any) {
      setErr(String(e?.message || CHAT.planFailed()));
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
            <IconChevronLeft />
          </Pressable>
          <Text style={s.headTitle} numberOfLines={1}>{intentTitle || T('Встреча', 'Meetup')}</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView contentContainerStyle={[s.body, { paddingBottom: 130 }]} keyboardShouldPersistTaps="handled" scrollEnabled={!dragging}>
          {plan ? (
            <>
              <Text style={s.sentTo}>{CHAT.sentTo(other)}</Text>
              <Text style={s.sentNote}>{CHAT.sentNote(other)}</Text>

              <View style={s.card}>
                <View style={s.cover}><IconImagePlaceholder size={40} /></View>
                <View style={s.metaRow}>
                  <IconCalendar />
                  <Text style={s.metaText}>{planWhen(plan, ru) || planWhenLabel(date, minutes, ru)}</Text>
                </View>
                {plan.district || district ? (
                  <View style={s.metaRow}>
                    <IconPin size={16} c={color.muted} />
                    <Text style={s.metaText}>{plan.district || district}</Text>
                  </View>
                ) : null}
                {/* Адрес виден только тому, кому его открыл сервер (OF.C3) — не достраиваем. */}
                {plan.address_visible_to_me && plan.address ? (
                  <View style={s.metaRow}>
                    <IconPin size={16} c={color.muted} />
                    <Text style={s.metaText}>{plan.address}</Text>
                  </View>
                ) : null}
                {link ? (
                  <View style={s.metaRow}>
                    <IconLink size={16} c={color.muted} />
                    <Text style={s.metaText}>{CHAT.videoCall()}</Text>
                  </View>
                ) : null}
              </View>

              {(plan.participants || []).map((p: any, i: number) => (
                <View key={(p.name || '') + i} style={s.person}>
                  {p.photo ? (
                    <Image source={{ uri: p.photo }} style={s.personAva} />
                  ) : (
                    <View style={[s.personAva, s.personAvaEmpty]}><IconPerson size={18} /></View>
                  )}
                  <View style={{ flex: 1 }}>
                    <Text style={s.personName}>{p.name}{p.age ? `, ${p.age}` : ''}</Text>
                    <Text style={s.personStatus}>{personStatus(p)}</Text>
                  </View>
                  <IconClock size={18} c={color.neutral400} />
                </View>
              ))}

              <Pressable
                accessibilityRole="button"
                style={s.cta}
                onPress={() => router.push({ pathname: '/conversation', params: { who: other, title: intentTitle, photo } })}
              >
                <Text style={s.ctaText}>{CHAT.openChat()}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setPlan(null)}>
                <Text style={s.ctaDarkText}>{CHAT.changePlan()}</Text>
              </Pressable>
            </>
          ) : (
            <>
              <View style={s.card}>
                <View style={s.labelRow}>
                  <IconCalendar />
                  <Text style={s.label}>{DETAILS.date()}</Text>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
                  {dates.map((d) => (
                    <Pressable
                      key={d.key}
                      accessibilityRole="button"
                      accessibilityState={{ selected: date === d.key }}
                      onPress={() => setDate(d.key)}
                      style={[s.chip, date === d.key && s.chipOn]}
                    >
                      <Text style={[s.chipText, date === d.key && { color: color.onPrimary }]}>{d.label}</Text>
                    </Pressable>
                  ))}
                </ScrollView>

                <View style={s.labelRow}>
                  <IconClock />
                  <Text style={s.label}>{DETAILS.time()}</Text>
                </View>
                <TimeDial minutes={minutes} onChange={setMinutes} onDragChange={setDragging} />
                <Text style={s.tz}>{hhmm(minutes)} {tzOffsetLabel(deviceTz())}</Text>

                {!link ? (
                  <>
                    <View style={s.labelRow}>
                      <IconPin size={18} c={color.fg} />
                      <Text style={s.label}>{DETAILS.district()}</Text>
                    </View>
                    <TextInput
                      style={s.input}
                      value={district}
                      onChangeText={setDistrict}
                      placeholder={String(st.profile.city || 'Barcelona')}
                      placeholderTextColor={color.neutral400}
                      accessibilityLabel={DETAILS.district()}
                    />
                  </>
                ) : (
                  <View style={s.metaRow}>
                    <IconLink size={16} c={color.muted} />
                    <Text style={s.metaText}>{CHAT.videoCall()}</Text>
                  </View>
                )}

                {err ? <Text style={s.err}>{err}</Text> : null}

                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ busy }}
                  style={s.cta}
                  onPress={busy ? undefined : propose}
                >
                  {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{CHAT.createPlan()}</Text>}
                </Pressable>
              </View>
            </>
          )}
        </ScrollView>

        <View style={s.navFloat} pointerEvents="box-none">
          <BottomNav />
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

/** Человеческая подпись времени для поля `when` — сервер хранит её как есть и показывает обоим. */
function planWhenLabel(dateKey: string, minutes: number, ru: boolean): string {
  const d = new Date(dateKey + 'T12:00:00');
  const day = d.toLocaleDateString(ru ? 'ru-RU' : 'en-US', { weekday: 'short', day: 'numeric', month: 'short' });
  return `${day} · ${hhmm(minutes)}`;
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

  body: { paddingHorizontal: 20, gap: space.md },
  sentTo: { fontSize: 20, fontWeight: '700', color: color.fg, marginTop: space.sm },
  sentNote: { ...type.bodySmall, color: color.muted } as any,

  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.md },
  cover: { height: 110, borderRadius: rad.lg, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  metaText: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  tz: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,

  chipRow: { gap: space.sm, paddingVertical: 2 },
  chip: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  input: {
    height: 46, borderRadius: rad.md, backgroundColor: color.neutral100,
    paddingHorizontal: 14, color: color.fg, fontSize: 15,
  },

  person: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: color.card, borderRadius: rad.lg, padding: space.md,
  },
  personAva: { width: 40, height: 40, borderRadius: 20 },
  personAvaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  personName: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  personStatus: { ...type.caption, color: color.muted } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  ctaDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  ctaDarkText: { ...type.button, color: '#fff' } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
