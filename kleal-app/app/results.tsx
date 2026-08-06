/**
 * Выдача кандидатов — кадр O.12, окно приглашения — O.14.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор полей — в src/candidates.ts и src/intent.ts.
 *
 * Карточка по кадру: фото, имя с бейджем («Best match» у первой, «Match» у остальных), подзаголовок,
 * расстояние, чипы интересов, «Сводка Kleal» и кнопка «Пригласить». Чего на кадре есть, а в данных
 * нет — занятие и город — карточка не выдумывает: вместо занятия вайб или интересы, вместо города
 * километры (см. src/candidates.ts).
 *
 * Два места, где экран намеренно расходится с бордом, — из-за того, как отвечает матчинг:
 *
 *  1. Пустой выдачи почти не бывает. Когда по теме не совпал никто, сервер присылает ближайших
 *     людей с пометкой `fallback: "alternative"`. Заголовок «Лучшее совпадение» над такой пачкой —
 *     прямая неправда, поэтому шапка смотрит на пометки карточек, а не на их количество; бейджи
 *     мэтча на таких карточках не рисуются.
 *  2. Расширение — лестница §12, ступень за ступенью, каждая называется вслух. Какую ось расширять
 *     — решает клиент: только он помнит, что уже пробовали.
 *
 * Приглашение (O.14) — ЕДИНСТВЕННОЕ место, где выдача что-то отправляет. Окно называет последствия
 * словами с кадра: человек увидит интент и профиль. Отправка идёт в /api/agent/propose; сервер
 * держит одно открытое приглашение на пару — повторная отправка обновляет его, а не плодит копии.
 */
import React, { useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { RESULTS, EXPAND_LADDER, ExpandAxis, axisExplain } from '../src/intent';
import { CANDS, Cand, candSubtitle, candWhere, candSummary } from '../src/candidates';
import { useLang, T, getLang } from '../src/i18n';
import { takeResults, setCandidate } from '../src/results-store';
import { agent } from '../src/api';
import { IconPerson, IconPin } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

const ru = () => getLang() === 'ru';

export default function Results() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  // Читаем один раз: последующие render'ы не должны затирать уже расширенную выдачу исходной.
  const initial = useMemo(() => takeResults(), []);

  const [intent, setIntent] = useState<any>(initial?.intent || {});
  const [cands, setCands] = useState<Cand[]>(initial?.candidates || []);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  /** Следующая непройденная ступень лестницы. */
  const [rung, setRung] = useState(0);
  /** Кому уже отправлено — кнопка на карточке гаснет, чтобы не слать дважды с одного экрана. */
  const [sent, setSent] = useState<Set<string>>(new Set());
  /** Кандидат, для которого открыто окно O.14. null — окна нет. */
  const [asking, setAsking] = useState<Cand | null>(null);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState('');

  const profile = initial?.profile || {};
  const self = String(profile?.name || '');

  // Радиус нечего удваивать, когда встреча онлайн, — эта ступень для такого интента бессмысленна.
  const ladder: ExpandAxis[] = useMemo(
    () => EXPAND_LADDER.filter((a) => !(a === 'radius' && intent?.mode === 'online')),
    [intent?.mode]
  );

  /** Карточки-заменители: тема не совпала ни у кого, показаны просто ближайшие подходящие люди. */
  const onlyFallback = cands.length > 0 && cands.every((c) => !!(c as any).fallback);
  const canWiden = rung < ladder.length && (cands.length === 0 || onlyFallback);

  const widen = async () => {
    const axis = ladder[rung];
    if (!axis) return;
    setBusy(true);
    setNote('');
    try {
      const r: any = await agent.expand(intent, profile, axis);
      const next: Cand[] = (r && r.candidates) || [];
      const km = axis === 'radius' ? (intent?.radiusKm || 15) * 2 : undefined;
      setRung(rung + 1);
      if (next.length) {
        setCands(next);
        // Интент двигаем сами: сервер возвращает только карточки, а следующая ступень должна
        // считаться от уже расширенного запроса, иначе радиус удваивался бы от исходного вечно.
        setIntent((prev: any) => ({
          ...prev,
          ...(axis === 'adjacent' ? { adjacentAllowed: true } : {}),
          ...(axis === 'parent' ? { broadAllowed: true } : {}),
          ...(axis === 'exactness' ? { exactMatchRequired: false } : {}),
          ...(axis === 'radius' ? { radiusKm: km } : {}),
        }));
        setNote(`${axisExplain(axis, km)} ${RESULTS.found(next.length)}`);
      } else {
        setNote(`${axisExplain(axis, km)} ${RESULTS.empty()}`);
      }
    } catch {
      setNote(T('Не получилось расширить. Попробуй ещё раз.', 'Could not widen. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  /** Отправка приглашения — только из окна O.14, никогда прямо с кнопки карточки. */
  const sendInvite = async () => {
    const to = String(asking?.name || '');
    if (!to || sending) return;
    setSending(true);
    setSendErr('');
    try {
      const r: any = await agent.propose(self, to, intent);
      if (!r?.ok) throw new Error(r?.error || 'propose failed');
      setSent((prev) => new Set(prev).add(to));
      setAsking(null);
    } catch {
      setSendErr(CANDS.inviteFailed());
    } finally {
      setSending(false);
    }
  };

  const openProfile = (c: Cand) => {
    setCandidate(c);
    router.push('/candidate');
  };

  // Экран открыт напрямую — обновлением страницы или по ссылке. Выдача живёт один переход, и
  // выдумывать её задним числом нечем; честнее сказать это и предложить поискать заново.
  if (!initial) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
            <Text style={s.backIcon}>‹</Text>
          </Pressable>
          <Text style={s.headTitle}>{T('Выдача устарела', 'These results are gone')}</Text>
        </View>
        <View style={s.scroll}>
          <Text style={s.lead}>
            {T('Результаты поиска живут до перезагрузки. Давай поищем заново.',
               'Search results only live until the page reloads. Let’s search again.')}
          </Text>
          {/* Новый поиск начинается там же, где и любой другой: с темы, а не с формата. */}
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.replace('/create')}>
            <Text style={s.ctaText}>{T('Новый поиск', 'New search')}</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const title = cands.length === 0 ? RESULTS.empty()
              : onlyFallback ? T('Прямых совпадений нет', 'No direct matches')
              : RESULTS.best();

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
          <Text style={s.backIcon}>‹</Text>
        </Pressable>
        {/* Красная точка + заголовок — шапка кадра O.12. */}
        <View style={s.dot} />
        <Text style={s.headTitle}>{title}</Text>
      </View>

      <ScrollView contentContainerStyle={[s.scroll, { paddingBottom: 120 }]}>
        {onlyFallback ? (
          <Text style={s.lead}>
            {T('Никто не занимается ровно этим. Вот кто рядом и с кем это может получиться.',
               'Nobody is doing exactly that. Here are people nearby it could work with.')}
          </Text>
        ) : null}

        {note ? <Text style={s.note}>{note}</Text> : null}

        {cands.length === 0 ? <Text style={s.lead}>{RESULTS.emptyNote()}</Text> : null}

        {cands.map((c, i) => (
          <CandCard
            key={(c.name || '') + i}
            c={c}
            badge={(c as any).fallback ? '' : i === 0 ? CANDS.bestBadge() : CANDS.matchBadge()}
            invited={sent.has(String(c.name || ''))}
            onOpen={() => openProfile(c)}
            onInvite={() => { setSendErr(''); setAsking(c); }}
          />
        ))}

        {canWiden ? (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy }}
            style={[s.cta, busy && { opacity: 0.6 }]}
            onPress={busy ? undefined : widen}
          >
            {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{RESULTS.widen()}</Text>}
          </Pressable>
        ) : null}

        {rung >= ladder.length && (cands.length === 0 || onlyFallback) ? (
          <Text style={s.note}>{RESULTS.exhausted()}</Text>
        ) : null}
      </ScrollView>

      {/* Панель на выдаче есть на кадре O.12. */}
      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav />
      </View>

      <InviteSheet
        cand={asking}
        sending={sending}
        err={sendErr}
        onSend={sendInvite}
        onClose={() => setAsking(null)}
        bottomInset={insets.bottom}
      />
    </View>
  );
}

/** Карточка кандидата — кадр O.12. Нажатие на тело карточки открывает полный профиль (O.13). */
function CandCard({
  c, badge, invited, onOpen, onInvite,
}: {
  c: Cand;
  badge: string;
  invited: boolean;
  onOpen: () => void;
  onInvite: () => void;
}) {
  const readiness = (ru() ? c.readiness_ru : c.readiness_en) || '';
  const where = candWhere(c);
  const summary = candSummary(c, ru());

  return (
    <View style={s.card}>
      <Pressable accessibilityRole="button" onPress={onOpen} style={({ pressed }) => [pressed && { opacity: 0.92 }]}>
        <View style={s.cardTop}>
          {c.photo ? (
            <Image source={{ uri: c.photo }} style={s.av} />
          ) : (
            <View style={[s.av, s.avEmpty]}><IconPerson /></View>
          )}
          <View style={{ flex: 1 }}>
            <View style={s.nameRow}>
              <Text style={s.name} numberOfLines={1}>{c.name}{c.age ? `, ${c.age}` : ''}</Text>
              {badge ? (
                <View style={s.badge}><Text style={s.badgeText}>{badge}</Text></View>
              ) : null}
            </View>
            <Text style={s.subtitle} numberOfLines={1}>{candSubtitle(c, ru())}</Text>
            {where ? (
              <View style={s.whereRow}>
                <IconPin size={13} c={color.muted} />
                <Text style={s.meta}>{where}</Text>
              </View>
            ) : null}
          </View>
        </View>

        {(c.interests || []).length ? (
          <View style={s.tags}>
            {(c.interests || []).slice(0, 3).map((t, i) => (
              <View key={t + i} style={s.tag}><Text style={s.tagText}>{t}</Text></View>
            ))}
          </View>
        ) : null}

        {summary ? (
          <View style={s.sumBox}>
            <Text style={s.sumLabel}>{CANDS.summaryLabel()}</Text>
            <Text style={s.sumText}>{summary}</Text>
          </View>
        ) : null}

        {/*
          Доступность — не украшение: человек «в тихих часах» не ответит сейчас, и лучше знать
          заранее. Слово «связаться» разводит два разных факта — его намерение встречаться и то,
          дойдёт ли сообщение прямо сейчас, — которые иначе читаются как противоречие.
        */}
        {readiness ? (
          <Text style={s.readiness}>{T('Связаться: ', 'Reach out: ')}{readiness}</Text>
        ) : null}
      </Pressable>

      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: invited }}
        disabled={invited}
        style={[s.invite, invited && s.invited]}
        onPress={onInvite}
      >
        <Text style={[s.inviteText, invited && { color: color.muted }]}>
          {invited ? CANDS.invited() : CANDS.invite()}
        </Text>
      </Pressable>
    </View>
  );
}

/** Окно O.14: последствия названы словами, отправка — только отсюда. */
function InviteSheet({
  cand, sending, err, onSend, onClose, bottomInset,
}: {
  cand: Cand | null;
  sending: boolean;
  err: string;
  onSend: () => void;
  onClose: () => void;
  bottomInset: number;
}) {
  const name = String(cand?.name || '');
  return (
    <Modal visible={!!cand} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel={T('Закрыть', 'Close')} />
      <View style={[s.sheet, { paddingBottom: Math.max(bottomInset, 18) }]}>
        <View style={s.sheetHead}>
          <Text style={s.sheetTitle}>{CANDS.sheetTitle(name)}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={onClose} hitSlop={10}>
            <Text style={s.sheetX}>✕</Text>
          </Pressable>
        </View>
        <Text style={s.sheetBody}>{CANDS.sheetBody(name)}</Text>
        {err ? <Text style={s.note}>{err}</Text> : null}
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ busy: sending }}
          style={s.sheetSend}
          onPress={sending ? undefined : onSend}
        >
          {sending ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.sheetSendText}>{CANDS.send()}</Text>}
        </Pressable>
        <Pressable accessibilityRole="button" style={s.sheetNot} onPress={onClose}>
          <Text style={s.sheetNotText}>{CANDS.notYet()}</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: space.md },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  backIcon: { fontSize: 24, color: color.fg, marginTop: -3 },
  dot: { width: 26, height: 26, borderRadius: 13, backgroundColor: color.primary },
  headTitle: { flex: 1, fontSize: 19, fontWeight: '700', color: color.fg },

  scroll: { padding: 20, paddingTop: 0, gap: space.md },
  lead: { ...type.body, color: color.muted } as any,
  note: { ...type.bodySmall, color: color.primary } as any,

  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.sm },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  av: { width: 56, height: 56, borderRadius: rad.full },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  name: { ...type.title, color: color.fg, flexShrink: 1 } as any,
  badge: { paddingHorizontal: 9, height: 22, borderRadius: rad.full, backgroundColor: color.primary, justifyContent: 'center' },
  badgeText: { fontSize: 10.5, fontWeight: '700', color: color.onPrimary },
  subtitle: { ...type.bodySmall, color: color.muted, marginTop: 1 } as any,
  whereRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  meta: { ...type.bodySmall, color: color.muted } as any,

  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  tag: { paddingHorizontal: 10, height: 28, borderRadius: rad.full, backgroundColor: color.neutral100, justifyContent: 'center' },
  tagText: { ...type.labelSmall, color: color.muted } as any,

  sumBox: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md, gap: 4 },
  sumLabel: { ...type.labelSmall, color: color.primary, fontWeight: '700' } as any,
  sumText: { ...type.bodySmall, color: color.fg } as any,
  readiness: { ...type.caption, color: color.muted } as any,

  invite: { height: 46, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  invited: { backgroundColor: color.neutral100 },
  inviteText: { ...type.button, color: color.onPrimary } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,

  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },

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
