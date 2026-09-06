import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, AppState, Modal, Pressable, StyleSheet, Text, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { agent, group, newIdem } from '../api';
import { CHAT, PLAN, RATINGS, planPhase } from '../chat';
import { T, useLang } from '../i18n';
import { useOnb } from '../state';
import { color, radius as rad, space, type } from '../theme';

type Stage = 'happened' | 'reason' | 'rating';

/**
 * O.24 -> O.25 as an app-level post-call prompt.
 *
 * The plan screen remains the source of truth and fallback. This component only makes the same
 * server-backed lifecycle visible without requiring somebody to reopen that screen after a call.
 */
export function PostCallPrompt() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const state = useOnb();
  const me = String(state.profile.name || '').trim();
  const loadingRef = useRef(false);

  const [plan, setPlan] = useState<any>(null);
  const [dismissedId, setDismissedId] = useState('');
  const [stage, setStage] = useState<Stage>('happened');
  const [rating, setRating] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!me || loadingRef.current) return;
    loadingRef.current = true;
    try {
      const [oneResult, groupResult] = await Promise.allSettled([agent.plans(me), group.plans(me)]);
      const one: any = oneResult.status === 'fulfilled' ? oneResult.value : {};
      const groups: any = groupResult.status === 'fulfilled' ? groupResult.value : {};
      const all = [
        ...(one?.plans || []), ...(one?.history || []),
        ...(groups?.plans || []).map((item: any) => ({ ...item, feedback_kind: 'group' })),
        ...(groups?.history || []).map((item: any) => ({ ...item, feedback_kind: 'group' })),
      ] as any[];
      const pending = all
        .filter((item) => feedbackStage(item) !== null && String(item.id || '') !== dismissedId)
        .sort((a, b) => Number(b.starts_at || b.updated || 0) - Number(a.starts_at || a.updated || 0))[0];

      if (!pending) {
        setPlan(null);
        return;
      }
      setPlan(pending);
      setStage(feedbackStage(pending) || 'happened');
      setRating('');
      setReason('');
      setError('');
    } catch {
      // A post-call reminder must never replace the current screen with a loading error.
    } finally {
      loadingRef.current = false;
    }
  }, [dismissedId, me]);

  useEffect(() => {
    if (!me) {
      setPlan(null);
      return;
    }
    load();
    const timer = setInterval(load, 15000);
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'active') load();
    });
    return () => {
      clearInterval(timer);
      sub.remove();
    };
  }, [load, me]);

  const other = useMemo(() => otherParticipant(plan, me), [me, plan]);

  const close = () => {
    setDismissedId(String(plan?.id || ''));
    setPlan(null);
  };

  const save = async (payload: Record<string, unknown>) => {
    if (!plan?.id || busy) return null;
    setBusy(true);
    setError('');
    try {
      const response: any = plan.feedback_kind === 'group'
        ? await group.planFeedback(plan.id, me, payload, newIdem('gplan-feedback'))
        : await agent.planFeedback(plan.id, me, payload);
      if (!response?.ok) throw new Error(String(response?.error || 'failed'));
      return response;
    } catch {
      setError(CHAT.planFailed());
      return null;
    } finally {
      setBusy(false);
    }
  };

  const answerYes = async () => {
    const response = await save({ happened: true });
    if (!response) return;
    setPlan((current: any) => ({
      ...current,
      ...(response.plan || {}),
      my_feedback: { ...(current?.my_feedback || {}), happened: true },
    }));
    setStage('rating');
  };

  const answerNo = () => {
    setReason('');
    setStage('reason');
  };

  const sendNo = async (includeReason: boolean) => {
    const response = await save({
      happened: false,
      ...(includeReason && reason ? { reason } : {}),
    });
    if (response) close();
  };

  const sendRating = async () => {
    const value = RATINGS.find(([key]) => key === rating)?.[2];
    if (!value) return;
    const response = await save({ rating: value });
    if (response) close();
  };

  const reportGroupProblem = () => {
    if (!plan?.gid) return;
    const gid = String(plan.gid);
    const title = String(plan.title || '');
    close();
    router.navigate({ pathname: '/group-report', params: { gid, title } } as any);
  };

  if (!plan) return null;

  return (
    <Modal visible transparent animationType="fade" onRequestClose={close} statusBarTranslucent>
      <View style={s.layer}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={T('Ответить позже', 'Answer later')}
          style={s.scrim}
          onPress={close}
        />
        <View style={[s.card, { paddingBottom: Math.max(insets.bottom, 20) }]}>
          <View style={s.handle} />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={T('Ответить позже', 'Answer later')}
            hitSlop={12}
            style={s.close}
            onPress={close}
          >
            <Text style={s.closeText}>x</Text>
          </Pressable>

          <Text style={s.eyebrow}>{T('После звонка', 'After the call')}</Text>
          <Text style={s.title}>
            {stage === 'happened' ? PLAN.didItHappen()
              : stage === 'rating' ? PLAN.howWasIt()
              : PLAN.whatHappened()}
          </Text>
          <Text style={s.meta} numberOfLines={2}>
            {[plan.title, plan.feedback_kind === 'group' ? '' : other].filter(Boolean).join(' · ')}
          </Text>

          {stage === 'happened' ? (
            <>
              <Text style={s.note}>
                {plan.feedback_kind === 'group'
                  ? T('Этот вопрос получат все участники. Ответы не записываются, пока каждый не ответит.',
                      'Everyone gets this question. Nothing is recorded until people answer.')
                  : PLAN.didItNote(other)}
              </Text>
              <Pressable accessibilityRole="button" disabled={busy} style={s.primary} onPress={answerYes}>
                {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.primaryText}>{PLAN.yesWeTalked()}</Text>}
              </Pressable>
              <Pressable accessibilityRole="button" disabled={busy} style={s.secondary} onPress={answerNo}>
                <Text style={s.secondaryText}>{PLAN.noItDidnt()}</Text>
              </Pressable>
            </>
          ) : null}

          {stage === 'rating' ? (
            <>
              <Text style={s.note}>
                {plan.feedback_kind === 'group'
                  ? groupRatingNote(plan)
                  : PLAN.optional()}
              </Text>
              <View style={s.ratings}>
                {RATINGS.map(([key, label]) => (
                  <Pressable
                    key={key}
                    accessibilityRole="button"
                    accessibilityState={{ selected: rating === key }}
                    style={[s.rating, rating === key && s.ratingSelected]}
                    onPress={() => setRating(key)}
                  >
                    <Text style={[s.ratingText, rating === key && s.ratingTextSelected]}>{label()}</Text>
                  </Pressable>
                ))}
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: !rating || busy }}
                disabled={!rating || busy}
                style={[s.primary, (!rating || busy) && s.disabled]}
                onPress={sendRating}
              >
                {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.primaryText}>{PLAN.send()}</Text>}
              </Pressable>
              {plan.feedback_kind === 'group' ? (
                <Pressable accessibilityRole="button" disabled={busy} style={s.secondary} onPress={reportGroupProblem}>
                  <Text style={s.secondaryText}>{T('Сообщить о проблеме', 'Report a problem')}</Text>
                </Pressable>
              ) : null}
            </>
          ) : null}

          {stage === 'reason' ? (
            <>
              <Text style={s.note}>
                {plan.feedback_kind === 'group'
                  ? T('Причина останется приватной и не будет показана другим участникам.',
                      'Your reason stays private and is not shown to other participants.')
                  : PLAN.whatHappenedNote()}
              </Text>
              {(plan.feedback_kind === 'group' ? groupReasons(String(plan.mode || '')) : [
                ['no_show', PLAN.reasonNoShow(other)],
                ['couldnt_make', PLAN.reasonCouldnt()],
                ['place_closed', PLAN.reasonClosed()],
                ['moved', PLAN.reasonMoved()],
                ['other', PLAN.reasonOther()],
              ] as [string, string][]).map(([key, label]) => (
                <Pressable key={key} accessibilityRole="button" style={s.reason} onPress={() => setReason(key)}>
                  <View style={[s.radio, reason === key && s.radioSelected]} />
                  <Text style={s.reasonText}>{label}</Text>
                </Pressable>
              ))}
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: !reason || busy }}
                disabled={!reason || busy}
                style={[s.primary, (!reason || busy) && s.disabled]}
                onPress={() => sendNo(true)}
              >
                {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.primaryText}>{PLAN.send()}</Text>}
              </Pressable>
              <Pressable accessibilityRole="button" disabled={busy} style={s.secondary} onPress={() => sendNo(false)}>
                <Text style={s.secondaryText}>{PLAN.skip()}</Text>
              </Pressable>
            </>
          ) : null}

          {error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null}
        </View>
      </View>
    </Modal>
  );
}

export function feedbackStage(plan: any, nowMs = Date.now()): Stage | null {
  if (plan?.feedback_kind === 'group') {
    if (!plan?.feedback_due || plan?.state === 'cancelled') return null;
    const mine = plan?.my_feedback;
    if (!mine || mine.happened === undefined || mine.happened === null) return 'happened';
    if (mine.happened === true && !mine.rating && !mine.text) return 'rating';
    return null;
  }
  const mode = String(plan?.mode || '').toLowerCase();
  if (mode !== 'online' && mode !== 'hybrid') return null;
  if (planPhase(plan, nowMs) !== 'after') return null;
  const mine = plan?.my_feedback;
  if (!mine || mine.happened === undefined || mine.happened === null) return 'happened';
  if (mine.happened === true && !mine.rating && !mine.text) return 'rating';
  return null;
}

export function groupReasons(mode: string): [string, string][] {
  if (mode === 'hybrid') {
    return [
      ['nobody_came_or_joined', T('Никто не пришёл и не подключился', 'Nobody came or joined')],
      ['couldnt_make', T('Я не смог прийти или подключиться', 'I couldn’t make it')],
      ['others_didnt_come_or_join', T('Другие не пришли или не подключились', 'Others didn’t come or join')],
      ['place_closed', T('Место было закрыто', 'The place was closed')],
      ['other', T('Другое', 'Something else')],
    ];
  }
  if (mode === 'offline') {
    return [
      ['nobody_came', T('Никто не пришёл', 'Nobody came')],
      ['couldnt_make', T('Я не смог прийти', 'I couldn’t make it')],
      ['others_didnt_come', T('Другие не пришли', 'Others didn’t come')],
      ['place_closed', T('Место было закрыто', 'The place was closed')],
      ['other', T('Другое', 'Something else')],
    ];
  }
  return [
    ['nobody_joined', T('Никто не подключился', 'Nobody joined')],
    ['couldnt_make', T('Я не смог подключиться', 'I couldn’t make it')],
    ['others_didnt_join', T('Другие не подключились', 'Others didn’t join')],
    ['link_failed', T('Ссылка не работала', 'The link didn’t work')],
    ['other', T('Другое', 'Something else')],
  ];
}

function groupRatingNote(plan: any): string {
  const outcome = plan?.feedback_outcome || {};
  if (outcome.state === 'held') {
    return T(
      `${Number(outcome.yes || 0)} из ${Number(outcome.of || 0)} участников подтвердили звонок. Оценка необязательна.`,
      `${Number(outcome.yes || 0)} of ${Number(outcome.of || 0)} said it happened, so it counts as held. Rating is optional.`
    );
  }
  return T('Оценка необязательна и видна только Kleal.', 'Rating is optional and is only visible to Kleal.');
}

function otherParticipant(plan: any, me: string): string {
  const mine = me.trim().toLowerCase();
  const participant = (plan?.participants || []).find(
    (item: any) => String(item?.name || '').trim().toLowerCase() !== mine
  );
  return String(participant?.name || plan?.other || '').trim();
}

const s = StyleSheet.create({
  layer: { flex: 1, justifyContent: 'flex-end' },
  scrim: { ...StyleSheet.absoluteFill, backgroundColor: color.scrim },
  card: {
    backgroundColor: color.card,
    borderTopLeftRadius: rad.xxl,
    borderTopRightRadius: rad.xxl,
    paddingHorizontal: 20,
    paddingTop: 12,
    gap: space.md,
  },
  handle: { alignSelf: 'center', width: 44, height: 4, borderRadius: 2, backgroundColor: color.neutral300 },
  /**
   * КРЕСТИК ЛЕЖИТ ПОВЕРХ СОДЕРЖИМОГО, а не под ним.
   *
   * Он объявлен в разметке ПЕРВЫМ, до надписей, а в React Native соседи, отрисованные позже,
   * ложатся сверху. Надпись «После звонка» занимает ту же полосу по высоте и накрывала его
   * целиком: нажатие уходило в текст, окно не закрывалось, и человек оставался в нём заперт —
   * оно всплывает поверх главной при каждом запуске. Проверено на симуляторе: по фону окно
   * закрывается, по крестику нет.
   *
   * `zIndex` вместо переноса в конец разметки — правка на одну строку, порядок JSX не трогаем.
   * `elevation` — то же самое для Android.
   */
  close: { position: 'absolute', right: 18, top: 18, width: 32, height: 32, alignItems: 'center', justifyContent: 'center', zIndex: 2, elevation: 2 },
  closeText: { fontSize: 22, lineHeight: 24, color: color.muted },
  eyebrow: { ...type.caption, color: color.primary, fontWeight: '700', textTransform: 'uppercase' } as any,
  title: { fontSize: 26, lineHeight: 32, fontWeight: '700', color: color.fg, paddingRight: 36 } as any,
  meta: { ...type.bodySmall, color: color.muted } as any,
  note: { ...type.bodySmall, color: color.muted } as any,
  primary: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  primaryText: { ...type.button, color: color.onPrimary } as any,
  secondary: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { ...type.button, color: color.fg } as any,
  disabled: { opacity: 0.45 },
  ratings: { flexDirection: 'row', gap: space.sm },
  rating: { flex: 1, minHeight: 48, borderRadius: rad.full, borderWidth: 1, borderColor: color.border, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8 },
  ratingSelected: { backgroundColor: color.primary, borderColor: color.primary },
  ratingText: { ...type.labelMedium, color: color.fg, textAlign: 'center' } as any,
  ratingTextSelected: { color: color.onPrimary },
  reason: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 42 },
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: color.neutral300 },
  radioSelected: { borderColor: color.primary, backgroundColor: color.primary },
  reasonText: { ...type.bodySmall, color: color.fg, flex: 1 } as any,
  error: { ...type.bodySmall, color: color.primary, textAlign: 'center' } as any,
});
