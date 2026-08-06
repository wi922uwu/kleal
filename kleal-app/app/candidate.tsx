/**
 * Полная карточка кандидата — кадр O.13.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор полей — в src/candidates.ts.
 *
 * Показывается ТОЛЬКО то, что реально пришло из ранжирования: большое фото (или честная заглушка),
 * имя с возрастом, чипы интересов, расстояние, «Сводка Kleal» из причин совпадения и приписка
 * приватности с кадра. Занятия и города в данных нет — их строки не рисуются, а не заполняются
 * выдумкой (см. src/candidates.ts, шапка).
 *
 * «Пригласить» на кадре — пилюля с галочкой и стрелками, похожая на слайдер. Здесь это обычная
 * кнопка, открывающая то же окно O.14, что и в списке: жест «потяни, чтобы пригласить» — украшение
 * поверх того же действия, и городить свой слайдер в каркасе значило бы тестировать жест вместо
 * потока. Помечено как упрощение против кадра.
 *
 * Кандидат приходит через results-store, как и выдача: карточка большая, в параметры маршрута её
 * класть нельзя. Открытый напрямую (обновлением страницы) экран честно говорит, что данных больше
 * нет, и ведёт назад к поиску.
 */
import React, { useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { CANDS, Cand, candSubtitle, candWhere, candSummary } from '../src/candidates';
import { useLang, T, getLang } from '../src/i18n';
import { takeResults, takeCandidate } from '../src/results-store';
import { agent } from '../src/api';
import { IconPerson, IconPin, IconUserLock } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

const ru = () => getLang() === 'ru';

export default function Candidate() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const c: Cand | null = useMemo(() => takeCandidate(), []);
  const handoff = useMemo(() => takeResults(), []);

  const [asking, setAsking] = useState(false);
  const [sending, setSending] = useState(false);
  /** Id отправленной заявки. По нему работает «Отменить» (O.15); пусто — не отправляли. */
  const [sentId, setSentId] = useState('');
  const [err, setErr] = useState('');

  if (!c) {
    return (
      <View style={[s.wrap, s.center, { paddingTop: insets.top }]}>
        <Text style={s.lead}>
          {T('Карточка живёт один переход из выдачи. Поищем заново?',
             'This card lives one hop from the results. Search again?')}
        </Text>
        <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.replace('/create')}>
          <Text style={s.ctaText}>{T('Новый поиск', 'New search')}</Text>
        </Pressable>
      </View>
    );
  }

  const name = String(c.name || '');
  const where = candWhere(c);
  const summary = candSummary(c, ru());
  const readiness = (ru() ? c.readiness_ru : c.readiness_en) || '';

  const send = async () => {
    if (sending) return;
    setSending(true);
    setErr('');
    try {
      const self = String(handoff?.profile?.name || '');
      const r: any = await agent.propose(self, name, handoff?.intent || {});
      if (!r?.ok) throw new Error(r?.error || 'propose failed');
      setSentId(String(r.id || ''));
      setAsking(false);
    } catch {
      setErr(CANDS.inviteFailed());
    } finally {
      setSending(false);
    }
  };

  /** O.15 «Отменить»: отзыв НЕотвеченного приглашения. Уже отвеченное отзывать нечем. */
  const cancel = async () => {
    if (!sentId) return;
    setErr('');
    try {
      const self = String(handoff?.profile?.name || '');
      const r: any = await agent.withdraw(sentId, self);
      if (!r?.ok && r?.error !== 'ALREADY_RESOLVED') throw new Error(r?.error || 'withdraw failed');
      setSentId('');
    } catch {
      setErr(CANDS.cancelFailed());
    }
  };

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
          <Text style={s.backIcon}>‹</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        {c.photo ? (
          <Image source={{ uri: c.photo }} style={s.photo} />
        ) : (
          <View style={[s.photo, s.photoEmpty]}><IconPerson size={54} /></View>
        )}

        <View style={s.nameRow}>
          <Text style={s.name}>{name}{c.age ? `, ${c.age}` : ''}</Text>
          {c.verified ? <Text style={s.verified}>✓</Text> : null}
        </View>
        <Text style={s.subtitle}>{candSubtitle(c, ru())}</Text>

        {(c.interests || []).length ? (
          <View style={s.tags}>
            {(c.interests || []).slice(0, 6).map((t, i) => (
              <View key={t + i} style={s.tag}><Text style={s.tagText}>{t}</Text></View>
            ))}
          </View>
        ) : null}

        {where ? (
          <View style={s.whereRow}>
            <IconPin size={14} c={color.muted} />
            <Text style={s.meta}>{where}</Text>
          </View>
        ) : null}
        {readiness ? (
          <Text style={s.meta}>{T('Связаться: ', 'Reach out: ')}{readiness}</Text>
        ) : null}

        {summary ? (
          <View style={s.sumBox}>
            <Text style={s.sumLabel}>{CANDS.summaryLabel()}</Text>
            <Text style={s.sumText}>{summary}</Text>
          </View>
        ) : null}

        {/* Приписка приватности с кадра — она объясняет, почему этот профиль вообще видно. */}
        <View style={s.privRow}>
          <IconUserLock size={16} c={color.muted} />
          <Text style={s.priv}>{CANDS.privacyNote()}</Text>
        </View>

        {err ? <Text style={s.err}>{err}</Text> : null}

        {sentId ? (
          // O.15: приглашение ушло — слева спокойное состояние, справа настоящая «Отменить».
          <View style={s.invitedRow}>
            <View style={[s.invite, s.invitedPill]}>
              <Text style={[s.inviteText, { color: color.fg }]}>{CANDS.invitedShort()}</Text>
            </View>
            <Pressable accessibilityRole="button" style={[s.invite, s.cancelPill]} onPress={cancel}>
              <Text style={s.inviteText}>{CANDS.cancel()}</Text>
            </Pressable>
          </View>
        ) : (
          <Pressable accessibilityRole="button" style={s.invite} onPress={() => setAsking(true)}>
            <Text style={s.inviteText}>{`✓  ${CANDS.invite()}`}</Text>
          </Pressable>
        )}
      </ScrollView>

      {/* Панель есть и на карточке кандидата — кадр O.13. */}
      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav />
      </View>

      {/* То же окно O.14, что и в списке: последствия приглашения называются всегда одинаково. */}
      <Modal visible={asking} transparent animationType="slide" onRequestClose={() => setAsking(false)}>
        <Pressable style={s.scrim} onPress={() => setAsking(false)} accessibilityLabel={T('Закрыть', 'Close')} />
        <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 18) }]}>
          <View style={s.sheetHead}>
            <Text style={s.sheetTitle}>{CANDS.sheetTitle(name)}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={() => setAsking(false)} hitSlop={10}>
              <Text style={s.sheetX}>✕</Text>
            </Pressable>
          </View>
          <Text style={s.sheetBody}>{CANDS.sheetBody(name)}</Text>
          {err ? <Text style={s.err}>{err}</Text> : null}
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy: sending }}
            style={s.sheetSend}
            onPress={sending ? undefined : send}
          >
            {sending ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.sheetSendText}>{CANDS.send()}</Text>}
          </Pressable>
          <Pressable accessibilityRole="button" style={s.sheetNot} onPress={() => setAsking(false)}>
            <Text style={s.sheetNotText}>{CANDS.notYet()}</Text>
          </Pressable>
        </View>
      </Modal>
    </View>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  center: { alignItems: 'center', justifyContent: 'center', gap: space.lg, paddingHorizontal: 28 },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  backIcon: { fontSize: 24, color: color.fg, marginTop: -3 },

  scroll: { paddingHorizontal: 20, paddingBottom: 130, gap: space.sm, alignItems: 'center' },
  photo: { width: 132, height: 132, borderRadius: 66 },
  photoEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: space.sm },
  name: { fontSize: 22, fontWeight: '700', color: color.fg },
  verified: { color: color.primary, fontSize: 18, fontWeight: '700' },
  subtitle: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,

  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, justifyContent: 'center', marginTop: space.sm },
  tag: { paddingHorizontal: 10, height: 28, borderRadius: rad.full, backgroundColor: color.neutral100, justifyContent: 'center' },
  tagText: { ...type.labelSmall, color: color.muted } as any,

  whereRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  meta: { ...type.bodySmall, color: color.muted } as any,

  sumBox: { alignSelf: 'stretch', backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md, gap: 4, marginTop: space.sm },
  sumLabel: { ...type.labelSmall, color: color.primary, fontWeight: '700' } as any,
  sumText: { ...type.bodySmall, color: color.fg } as any,

  privRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', marginTop: space.sm, alignSelf: 'stretch' },
  priv: { flex: 1, ...type.caption, color: color.muted } as any,

  invite: {
    alignSelf: 'stretch', height: 52, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: space.md,
  },
  invitedRow: { alignSelf: 'stretch', flexDirection: 'row', gap: space.sm },
  invitedPill: { flex: 1, backgroundColor: color.neutral100 },
  cancelPill: { flex: 1, backgroundColor: color.ink },
  inviteText: { ...type.button, color: color.onPrimary } as any,
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },

  lead: { ...type.body, color: color.muted, textAlign: 'center' } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  cta: {
    alignSelf: 'stretch', height: 52, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  ctaText: { ...type.button, color: color.onPrimary } as any,

  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#0006' },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: color.card, borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 20, paddingTop: 18, gap: space.md,
  },
  sheetHead: { flexDirection: 'row', alignItems: 'center' },
  sheetTitle: { flex: 1, fontSize: 20, fontWeight: '700', color: color.fg },
  sheetX: { fontSize: 20, color: color.fg },
  sheetBody: { ...type.bodySmall, color: color.muted } as any,
  sheetSend: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  sheetSendText: { ...type.button, color: color.onPrimary } as any,
  sheetNot: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  sheetNotText: { ...type.button, color: '#fff' } as any,
});
