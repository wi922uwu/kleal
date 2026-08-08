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
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { CANDS, CAP, OPTIONS, REPORT_REASONS, Cand, candSubtitle, candWhere, candSummary } from '../src/candidates';
import { CHAT } from '../src/chat';
import { useInvites, inviteTo, sendInvite, withdrawInvite } from '../src/invites';
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
  const self = String(handoff?.profile?.name || '');
  const name = String(c?.name || '');
  /**
   * Приглашение — общее состояние со списком выдачи (src/invites.ts). Своего у карточки больше
   * нет: пока оно было, приглашённый из списка человек открывался здесь с кнопкой «Пригласить»,
   * и заявка уходила во второй раз.
   */
  useInvites(self);
  const invite = inviteTo(name);

  const [asking, setAsking] = useState(false);
  /** MSG.22: потолок открытых приглашений сработал — окно живёт и здесь, не только в выдаче. */
  const [capOpen, setCapOpen] = useState(false);
  /** Лист O.13b и его отсчёт. pending — действие, которое случится через n секунд, если не отменить. */
  const [options, setOptions] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [pending, setPending] = useState<{ kind: 'reject' | 'block'; n: number } | null>(null);
  const [optNote, setOptNote] = useState('');
  const timer = useRef<any>(null);
  const [sending, setSending] = useState(false);
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

  const where = candWhere(c);
  const summary = candSummary(c, ru());
  const readiness = (ru() ? c.readiness_ru : c.readiness_en) || '';

  const send = async () => {
    if (sending) return;
    setSending(true);
    setErr('');
    try {
      const r = await sendInvite(self, name, handoff?.intent || {});
      if (r.capped) { setAsking(false); setCapOpen(true); return; }
      if (!r.ok) throw new Error(r.error || 'propose failed');
      setAsking(false);
    } catch {
      setErr(CANDS.inviteFailed());
    } finally {
      setSending(false);
    }
  };

  /** O.15 «Отменить»: отзыв НЕотвеченного приглашения. Уже отвеченное отзывать нечем. */
  const cancel = async () => {
    setErr('');
    if (!(await withdrawInvite(self, name))) setErr(CANDS.cancelFailed());
  };

  /**
   * O.13b: «Не интересно» и «Заблокировать» срабатывают через 4 секунды — отсчёт на борде, не
   * выдумка. Обе вещи меняют, кого человек увидит, и случайное нажатие должно быть обратимым,
   * пока не поздно. «Отменить» просто останавливает таймер — на сервер ничего не уходит.
   */
  const startPending = (kind: 'reject' | 'block') => {
    if (pending) return;
    setOptNote('');
    setPending({ kind, n: 4 });
  };

  useEffect(() => {
    if (!pending) return;
    timer.current = setTimeout(async () => {
      if (pending.n > 1) {
        setPending({ ...pending, n: pending.n - 1 });
        return;
      }
      try {
        if (pending.kind === 'block') {
          const r: any = await agent.block(self, name, true);
          if (!r?.ok) throw new Error(r?.error || 'block failed');
        } else {
          await agent.feedback(name, 'reject', self);
        }
        setPending(null);
        setOptions(false);
        // Человека из этой выдачи больше показывать нельзя — карточка закрывается.
        router.back();
      } catch {
        setPending(null);
        setOptNote(OPTIONS.failed());
      }
    }, 1000);
    return () => clearTimeout(timer.current);
  }, [pending]);

  const undoPending = () => {
    clearTimeout(timer.current);
    setPending(null);
  };

  const sendReport = async (reason: string) => {
    setOptNote('');
    try {
      const r: any = await agent.report(self, name, reason);
      if (!r?.ok) throw new Error(r?.error || 'report failed');
      setReporting(false);
      setOptNote(OPTIONS.reportSent());
    } catch {
      setOptNote(OPTIONS.failed());
    }
  };

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
          <Text style={s.backIcon}>‹</Text>
        </Pressable>
        <View style={{ flex: 1 }} />
        {/* Кадр O.13b: за тремя точками — «Не интересно», жалоба и блокировка. */}
        <Pressable accessibilityRole="button" accessibilityLabel={OPTIONS.title()} style={s.back} onPress={() => setOptions(true)}>
          <Text style={s.dots}>⋮</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        {/*
          Кадр O.13a: фото — большим блоком на всю ширину, а не кружком. Точки-пейджер на кадре
          подразумевают несколько фотографий; в данных фото ровно одно (или ни одного), и рисовать
          пейджер на одну страницу значит обещать пролистывание, которого нет.
        */}
        {c.photo ? (
          <Image source={{ uri: c.photo }} style={s.photoBig} resizeMode="cover" />
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

        {/* Те же четыре состояния, что и на карточке в списке (O.15/O.16/O.17) — они читаются из
            общего стора, поэтому «Пригласить» здесь не может появиться у уже приглашённого. */}
        {invite?.status === 'declined' ? (
          <View style={s.invitedRow}>
            <View style={[s.invite, s.invitedPill]}>
              <Text style={[s.inviteText, { color: color.muted }]}>⊘  {CHAT.declined()}</Text>
            </View>
          </View>
        ) : invite?.status === 'accepted' ? (
          <View style={s.invitedRow}>
            <Pressable
              accessibilityRole="button"
              style={[s.invite, { flex: 1 }]}
              onPress={() => router.push({ pathname: '/conversation', params: { who: name, photo: c.photo || '' } })}
            >
              <Text style={s.inviteText}>{CHAT.openChat()}</Text>
            </Pressable>
          </View>
        ) : invite?.status === 'pending' ? (
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

      {/* MSG.22 — потолок открытых приглашений. Раньше жил только в выдаче, и отправка отсюда
          его обходила: карточка молча слала четвёртое приглашение. */}
      <Modal visible={capOpen} transparent animationType="slide" onRequestClose={() => setCapOpen(false)}>
        <Pressable style={s.scrim} onPress={() => setCapOpen(false)} accessibilityLabel={T('Закрыть', 'Close')} />
        <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 18) }]}>
          <View style={s.sheetHead}>
            <Text style={s.sheetTitle}>{CAP.title(CAP.limit)}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={() => setCapOpen(false)} hitSlop={10}>
              <Text style={s.sheetX}>✕</Text>
            </Pressable>
          </View>
          <Text style={s.sheetBody}>{CAP.note()}</Text>
          <Pressable accessibilityRole="button" style={s.sheetNot} onPress={() => { setCapOpen(false); router.back(); }}>
            <Text style={s.sheetNotText}>{CAP.cancelOne()}</Text>
          </Pressable>
        </View>
      </Modal>

      {/* Лист O.13b. Пока идёт отсчёт, лист закрыть нельзя — иначе отмена потеряется вместе с ним. */}
      <Modal visible={options} transparent animationType="slide" onRequestClose={() => !pending && setOptions(false)}>
        <Pressable style={s.scrim} onPress={() => !pending && setOptions(false)} accessibilityLabel={T('Закрыть', 'Close')} />
        <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 18) }]}>
          <View style={s.sheetHead}>
            <Text style={s.sheetTitle}>{OPTIONS.title()}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={() => !pending && setOptions(false)} hitSlop={10}>
              <Text style={s.sheetX}>✕</Text>
            </Pressable>
          </View>

          {optNote ? <Text style={s.optNote}>{optNote}</Text> : null}

          {pending ? (
            <View style={s.pendingRow}>
              <Text style={s.pendingText}>
                {OPTIONS.pending(pending.kind === 'block' ? OPTIONS.block(name) : OPTIONS.notInterested(), pending.n)}
              </Text>
              <Pressable accessibilityRole="button" style={s.undoBtn} onPress={undoPending}>
                <Text style={s.undoText}>{OPTIONS.undo()}</Text>
              </Pressable>
            </View>
          ) : reporting ? (
            <>
              {REPORT_REASONS.map(([k, ruL, enL]) => (
                <Pressable key={k} accessibilityRole="button" style={s.reasonBtn} onPress={() => sendReport(k)}>
                  <Text style={s.reasonText}>{T(ruL, enL)}</Text>
                </Pressable>
              ))}
              <Pressable accessibilityRole="button" style={s.optCancel} onPress={() => setReporting(false)}>
                <Text style={s.optCancelText}>{OPTIONS.cancel()}</Text>
              </Pressable>
            </>
          ) : (
            <>
              <Pressable accessibilityRole="button" style={s.optDark} onPress={() => startPending('reject')}>
                <Text style={s.optDarkText}>⊗  {OPTIONS.notInterested()}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={s.optSoft} onPress={() => { setOptNote(''); setReporting(true); }}>
                <Text style={s.optSoftText}>{OPTIONS.report()}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={s.optSoft} onPress={() => startPending('block')}>
                <Text style={s.optSoftText}>{OPTIONS.block(name)}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" style={s.optCancel} onPress={() => setOptions(false)}>
                <Text style={s.optCancelText}>{OPTIONS.cancel()}</Text>
              </Pressable>
            </>
          )}
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

  dots: { fontSize: 20, color: color.fg, fontWeight: '700' },
  photoBig: { alignSelf: 'stretch', height: 340, borderRadius: rad.xl, backgroundColor: color.neutral100 },
  optNote: { ...type.bodySmall, color: color.primary } as any,
  optDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  optDarkText: { ...type.button, color: '#fff' } as any,
  optSoft: { height: 52, borderRadius: rad.full, backgroundColor: color.infoBg, alignItems: 'center', justifyContent: 'center' },
  optSoftText: { ...type.button, color: color.primary } as any,
  optCancel: { height: 44, alignItems: 'center', justifyContent: 'center' },
  optCancelText: { ...type.button, color: color.fg } as any,
  reasonBtn: {
    height: 48, borderRadius: rad.lg, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  reasonText: { ...type.body, color: color.fg } as any,
  pendingRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  pendingText: { flex: 1, ...type.body, color: color.fg } as any,
  undoBtn: { height: 44, paddingHorizontal: 18, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  undoText: { ...type.button, color: color.onPrimary } as any,

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
