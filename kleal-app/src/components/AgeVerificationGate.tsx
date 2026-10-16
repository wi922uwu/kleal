import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Linking, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { getState, patch, subscribe, useOnb } from '../state';
import { getSession, setSession } from '../api';
import { useRouter } from 'expo-router';
import { useLang } from '../i18n';
import { AGE_COPY, AgeResult, AgeRequestError, AgeSessionRequiredError, ageRequest, isHostedVerificationURL } from '../age-verification';
import { color, radius, space, type } from '../theme';
import { SafeAreaView } from 'react-native-safe-area-context';

export function AgeVerificationPanel({ result, busy, starting = false, retrySeconds = 0, error, onCheck, onStart, onSignIn }: {
  result: AgeResult | null; busy: boolean; starting?: boolean; retrySeconds?: number; error: string; onCheck: () => void; onStart: () => void; onSignIn?: () => void;
}) {
  useLang();
  const expired = error === 'sign_in_required';
  // The provider may have accepted creation before its response was lost.
  // Without a bound SID, only reconcile status; never promise a resumable URL.
  const startUnconfirmed = result?.status === 'pending' && result.sessionId === null && !result.canStart;
  const startDisabled = busy || retrySeconds > 0;
  return <SafeAreaView style={s.root}><ScrollView contentContainerStyle={s.content}>
    <Text style={s.badge}>18+</Text>
    <Text accessibilityRole="header" style={s.title}>{AGE_COPY.title()}</Text>
    {result?.developmentDemo === true && <Text testID="age-dev-demo-warning" accessibilityRole="alert" style={s.error}>{AGE_COPY.developmentDemo()}</Text>}
    <Text style={s.body}>{AGE_COPY.privacy()}</Text>
    <View style={s.card} accessibilityLiveRegion="polite">
      {busy && !expired && <ActivityIndicator color={color.primary} />}
      <Text style={s.body}>{expired ? AGE_COPY.sessionExpired() : busy ? (starting ? AGE_COPY.opening() : AGE_COPY.waiting())
        : startUnconfirmed ? AGE_COPY.startUnconfirmed() : result ? AGE_COPY.status(result.status) : AGE_COPY.notChecked()}</Text>
      {!!error && <Text style={s.error} accessibilityRole="alert">{AGE_COPY.error(error)}</Text>}
    </View>
    {!expired && !startUnconfirmed && <Text style={s.body}>{AGE_COPY.camera()}</Text>}
    {!expired && result?.canStart && <Pressable testID="age-start" disabled={startDisabled} accessibilityRole="button"
      accessibilityState={{ disabled: startDisabled, busy }} onPress={onStart} style={[s.button, startDisabled && s.disabled]}>
      <Text style={s.buttonText}>{result.status === 'pending' ? AGE_COPY.resume() : AGE_COPY.start()}</Text>
    </Pressable>}
    {!expired && retrySeconds > 0 && <Text style={s.body}>{AGE_COPY.retryIn(retrySeconds)}</Text>}
    {!expired && <Pressable testID="age-refresh" disabled={busy} accessibilityRole="button" accessibilityState={{ disabled: busy }}
      onPress={onCheck} style={[s.secondary, busy && s.disabled]}><Text style={s.body}>{AGE_COPY.check()}</Text></Pressable>}
    {expired && onSignIn && <Pressable testID="age-sign-in" accessibilityRole="button" onPress={onSignIn}
      style={s.button}><Text style={s.buttonText}>{AGE_COPY.signIn()}</Text></Pressable>}
  </ScrollView></SafeAreaView>;
}

export function AgeVerificationGate({ children }: { children: React.ReactNode }) {
  const st = useOnb();
  const router = useRouter();
  const [resolved, setResolved] = useState<{ session: string; done: boolean; result: AgeResult; receivedAt: number } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const mounted = useRef(false);
  const epoch = useRef(0);
  const inFlight = useRef<{ action: string; returned: number } | null>(null);
  const returnEpoch = useRef(0);
  const queuedRefresh = useRef(false);
  const startAfter = useRef(0);
  const [, tick] = useState(0);
  const needsSignIn = useRef(false);
  const session = st.session;
  // Never render another account's admission, even before effects have run.
  const result = resolved?.session === session && resolved?.done === !!st.done ? resolved.result : null;
  const retrySeconds = result && result.canStart && result.status !== 'pending' && resolved
    ? Math.max(0, Math.ceil((resolved.receivedAt + result.retryAfter * 1000 - Date.now()) / 1000)) : 0;
  const run = useCallback(async (action: 'status' | 'refresh' | 'session', expectedSession?: string | null): Promise<void> => {
    const current = getState();
    const session = current.session;
    const done = !!current.done;
    if (!mounted.current || !session || (expectedSession !== undefined && expectedSession !== session)
      || getSession() !== session || needsSignIn.current) return;
    if (action === 'session' && Date.now() < startAfter.current) return;
    if (inFlight.current) {
      // Join the current refresh unless a real background/blur boundary happened
      // after it started. Creation must always be followed by the queued recheck.
      if (action === 'refresh' && (inFlight.current.action !== 'refresh'
        || inFlight.current.returned < returnEpoch.current)) queuedRefresh.current = true;
      return;
    }
    inFlight.current = { action, returned: returnEpoch.current };
    const generation = epoch.current;
    const isCurrent = () => generation === epoch.current && getState().session === session
      && !!getState().done === done && getSession() === session;
    setBusy(true); setStarting(action === 'session'); setError('');
    try {
      const next = await ageRequest(action);
      if (generation !== epoch.current || !isCurrent()) return;
      const receivedAt = Date.now();
      startAfter.current = next.status === 'pending' ? 0 : receivedAt + next.retryAfter * 1000;
      setResolved({ session, done, result: next, receivedAt });
      if (action === 'session' && next.status === 'pending' && next.canStart && !next.url) {
        throw new AgeRequestError('provider_response');
      }
      if (action === 'session' && next.url) {
        if (!isHostedVerificationURL(next.url)) throw new Error('service');
        // Browser owns camera and consent. Never infer approval from this promise.
        try { await Linking.openURL(next.url); }
        catch { throw new AgeRequestError('browser_open'); }
      }
    } catch (e: any) {
      if (!isCurrent()) return;
      if (e instanceof AgeSessionRequiredError) {
        needsSignIn.current = true;
        setResolved(null);
        setError('sign_in_required');
      } else {
        if (e instanceof AgeRequestError && e.status === 409 && e.message === 'onboarding_required') setResolved(null);
        // A transient outage must not erase server-confirmed admission. Only a
        // real 401 revokes it; once revoked, retries cannot resurrect old state.
        const code = String(e?.message || 'service');
        setError(code === 'sign_in_required' ? 'service' : code);
      }
    }
    finally {
      if (generation === epoch.current) {
        setBusy(false); setStarting(false); inFlight.current = null;
        const refresh = queuedRefresh.current; queuedRefresh.current = false;
        // A return received during creation is not approval, but must not be lost.
        if (refresh && !needsSignIn.current) void run('refresh', session);
      }
    }
  }, []);
  useEffect(() => {
    mounted.current = true;
    let previousSession: string | null | undefined;
    let previousDone: boolean | undefined;
    const syncSession = () => {
      const current = getState();
      if (current.session === previousSession && !!current.done === previousDone) return;
      if (current.session !== previousSession) needsSignIn.current = false;
      previousSession = current.session; previousDone = !!current.done;
      // Subscribe synchronously: React may batch A -> logout -> A into a single
      // render. Effect dependencies alone cannot detect that identity boundary.
      epoch.current += 1; inFlight.current = null; queuedRefresh.current = false; startAfter.current = 0;
      setResolved(null); setError(needsSignIn.current ? 'sign_in_required' : ''); setBusy(false); setStarting(false);
      // Cold Expo Go restart has no custom-scheme callback. Reconcile an existing
      // bound session immediately; refresh never creates a provider session.
      void run('refresh');
    };
    const unsubscribe = subscribe(syncSession);
    syncSession();
    return () => { mounted.current = false; unsubscribe(); epoch.current += 1; queuedRefresh.current = false; };
  }, [run]);
  useEffect(() => {
    if (!retrySeconds) return;
    const timer = setInterval(() => tick((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [retrySeconds > 0]);
  useEffect(() => {
    if (((result && !result.onboarded) || error === 'onboarding_required') && st.done) {
      // A local done flag is not a saved server profile. Preserve every answer
      // and return to registration rather than treating the local flag as proof.
      patch({ done: false }); router.replace('/summary');
    }
  }, [result?.onboarded, error, st.done, router]);
  useEffect(() => {
    let previous = AppState.currentState;
    let blurred = false;
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        if (previous !== 'active') returnEpoch.current += 1;
        previous = state; blurred = false; void run('refresh');
      } else previous = state;
    });
    // Android focus can change without an AppState change (e.g. notification
    // shade). iOS manual browser return uses the active transition above.
    const blur = AppState.addEventListener('blur', () => { blurred = true; });
    const focus = AppState.addEventListener('focus', () => {
      if (blurred) returnEpoch.current += 1;
      blurred = false; void run('refresh');
    });
    // The callback's session/status/user parameters are intentionally never read.
    const link = Linking.addEventListener('url', () => { void run('refresh'); });
    return () => { sub.remove(); blur.remove(); focus.remove(); link.remove(); };
  }, [run]);
  useEffect(() => {
    if (!result || !['pending', 'review'].includes(result.status)) return;
    const timer = setInterval(() => { if (AppState.currentState === 'active') void run('refresh'); }, 30000);
    return () => clearInterval(timer);
  }, [result?.status, run]);
  const blocked = !!session && (!result || (result.onboarded && !result.admitted));
  // Keep the root navigator mounted during async checks. A full-screen modal
  // prevents taps/back escape; direct API access is independently server-gated.
  return <>{children}<Modal visible={blocked} animationType="none" presentationStyle="fullScreen" onRequestClose={() => {}}>
    <AgeVerificationPanel result={result} busy={busy} starting={starting} retrySeconds={retrySeconds} error={error}
      onCheck={() => { void run('refresh', session); }} onStart={() => { void run('session', session); }}
      onSignIn={() => {
        if (!mounted.current || !session || getState().session !== session || !needsSignIn.current) return;
        // Invalidate before changing auth or navigating; a late promise cannot
        // set admission/open Didit during the logout render/effect boundary.
        epoch.current += 1; inFlight.current = null; queuedRefresh.current = false;
        setResolved(null); setBusy(false); setStarting(false);
        setSession(''); patch({ session: null, login: null }); router.replace('/auth');
      }} />
  </Modal></>;
}

// ===== вид
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.ambientBase },
  content: { flexGrow: 1, padding: space.xl, gap: space.lg, justifyContent: 'center' },
  badge: { ...type.h2, color: color.primary }, title: { ...type.h2, color: color.fg },
  body: { ...type.body, color: color.fg }, error: { ...type.body, color: color.danger },
  card: { backgroundColor: color.card, borderRadius: radius.lg, padding: space.lg, gap: space.md },
  button: { backgroundColor: color.primary, borderRadius: radius.lg, padding: space.lg, alignItems: 'center' },
  buttonText: { ...type.button, color: color.onPrimary },
  secondary: { padding: space.lg, alignItems: 'center' }, disabled: { opacity: 0.5 },
});
