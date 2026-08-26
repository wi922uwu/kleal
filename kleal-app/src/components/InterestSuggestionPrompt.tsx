import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, AppState, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { agent } from '../api';
import {
  clearInterestSuggestion, confirmSuggestedInterest, INTEREST_SUGGESTION_COPY as C,
  offerInterestSuggestion, suggestedInterestLabel, useInterestSuggestion,
} from '../interest-suggestions';
import { useLang } from '../i18n';
import { explicitInterests } from '../profile';
import { useOnb } from '../state';
import { color, radius as rad, space, type } from '../theme';

export function InterestSuggestionPrompt() {
  useLang();
  const insets = useSafeAreaInsets();
  const state = useOnb();
  const suggestion = useInterestSuggestion();
  const me = String(state.profile.name || '').trim();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!me) return;
    try {
      const response: any = await agent.interestSuggestion(me, explicitInterests(state.profile));
      if (response?.suggestion) offerInterestSuggestion(response.suggestion);
    } catch {
      // A background suggestion must never replace the current screen with a network error.
    }
  }, [me, state.profile]);

  useEffect(() => {
    load();
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'active') load();
    });
    return () => sub.remove();
  }, [load]);

  const dismiss = async () => {
    if (!suggestion || busy) return;
    clearInterestSuggestion();
    try {
      await agent.interestSuggestionAction(me, suggestion.id, 'dismiss');
    } catch {
      // It may reappear after restart if the cooldown acknowledgement did not reach the server.
    }
  };

  const confirm = async () => {
    if (!suggestion || busy) return;
    setBusy(true);
    setError('');
    try {
      const saved = await confirmSuggestedInterest(suggestion.profile_key);
      if (!saved) throw new Error('profile write failed');
      // Order matters: matching marks it confirmed only after the shared profile writer succeeds.
      await agent.interestSuggestionAction(me, suggestion.id, 'confirm').catch(() => null);
      clearInterestSuggestion();
    } catch {
      setError(C.failed());
    } finally {
      setBusy(false);
    }
  };

  if (!suggestion) return null;
  const label = suggestedInterestLabel(suggestion);
  return (
    <Modal visible transparent animationType="fade" onRequestClose={dismiss} statusBarTranslucent>
      <View style={s.layer}>
        <Pressable accessibilityRole="button" accessibilityLabel={C.dismiss()} style={s.scrim} onPress={dismiss} />
        <View style={[s.card, { paddingBottom: Math.max(insets.bottom, 20) }]}>
          <View style={s.handle} />
          <Text style={s.eyebrow}>{C.eyebrow()}</Text>
          <Text style={s.title}>{C.title(label)}</Text>
          <Text style={s.note}>{C.note(suggestion.evidence_count)}</Text>
          {error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null}
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: busy }}
            disabled={busy}
            style={[s.primary, busy && s.disabled]}
            onPress={confirm}
          >
            {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.primaryText}>{C.confirm()}</Text>}
          </Pressable>
          <Pressable accessibilityRole="button" disabled={busy} style={s.secondary} onPress={dismiss}>
            <Text style={s.secondaryText}>{C.dismiss()}</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  layer: { flex: 1, justifyContent: 'flex-end' },
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: color.scrim },
  card: {
    backgroundColor: color.card, borderTopLeftRadius: rad.xxl, borderTopRightRadius: rad.xxl,
    paddingHorizontal: 20, paddingTop: 12, gap: space.md,
  },
  handle: { width: 44, height: 4, borderRadius: 2, backgroundColor: color.neutral300, alignSelf: 'center' },
  eyebrow: { ...type.labelMedium, color: color.primary, fontWeight: '700' } as any,
  title: { ...type.h2, color: color.fg } as any,
  note: { ...type.body, color: color.muted } as any,
  error: { ...type.bodySmall, color: color.danger } as any,
  primary: {
    minHeight: 52, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18,
  },
  primaryText: { ...type.button, color: color.onPrimary } as any,
  secondary: {
    minHeight: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18,
  },
  secondaryText: { ...type.button, color: color.fg } as any,
  disabled: { opacity: 0.5 },
});
