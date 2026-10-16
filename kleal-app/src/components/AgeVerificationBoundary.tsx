import React, { useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { API_BASE, getSession } from '../api';
import { getState, subscribe, useOnb } from '../state';
import { AgeVerificationGate } from './AgeVerificationGate';

/** Production canary enrollment, not an admission/security decision.
 * Existing users must not acquire a blocking KYC modal on a failed rollout probe.
 * The server independently rejects every enrolled/unverified product request.
 * A known enrolled account keeps its gate across probe failures, including401.
 */
export function AgeVerificationBoundary({ children }: { children: React.ReactNode }) {
  const { session } = useOnb();
  const [choice, setChoice] = useState<{ session: string; required: boolean } | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    let live = true;
    let previous: string | null | undefined;
    let flight: AbortController | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const cancelRetry = () => { if (retry !== null) clearTimeout(retry); retry = null; };
    const check = async () => {
      const token = getState().session;
      if (!live || !token || token !== getSession() || flight) return;
      cancelRetry();
      const epoch = generation.current;
      const isCurrent = () => live && generation.current === epoch
        && getState().session === token && getSession() === token;
      const request = new AbortController(); flight = request;
      const timer = setTimeout(() => request.abort(), 15000);
      let failed = true;
      try {
        const response = await fetch(`${API_BASE}/api/onboarding/age-verification/enrollment`, {
          method: 'GET', signal: request.signal,
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) return;
        const data = await response.json();
        if (isCurrent() && data?.ok === true && typeof data.required === 'boolean') {
          failed = false;
          setChoice({ session: token, required: data.required });
        }
      } catch { /* probe failure cannot enroll everyone or erase known enrollment */ }
      finally {
        clearTimeout(timer); if (flight === request) flight = null;
        // The initial rollout probe may fail before a Gate exists. Retry only
        // this read-only probe, at most once every 30s, while the app is active.
        // A successful noncohort response stops retries; errors never enroll it.
        if (failed && isCurrent() && AppState.currentState === 'active') {
          retry = setTimeout(() => {
            retry = null;
            if (isCurrent() && AppState.currentState === 'active') void check();
          }, 30000);
        }
      }
    };
    const sync = () => {
      const token = getState().session;
      if (previous === token) return;
      previous = token; generation.current += 1;
      cancelRetry(); flight?.abort(); flight = null; setChoice(null);
      void check();
    };
    const unsubscribe = subscribe(sync); sync();
    const active = AppState.addEventListener('change', state => { if (state === 'active') void check(); });
    const focus = AppState.addEventListener('focus', () => { void check(); });
    return () => {
      live = false; generation.current += 1; cancelRetry(); flight?.abort();
      unsubscribe(); active.remove(); focus.remove();
    };
  }, []);
  // Keep children at the same reconciliation position before/after enrollment.
  // Wrapping them in a newly mounted Gate would reset navigation and drafts.
  return <>{children}{choice !== null && choice.session === session && choice.required
    ? <AgeVerificationGate>{null}</AgeVerificationGate> : null}</>;
}
