import { useEffect, useState } from 'react';
import { getLang, T } from './i18n';
import { addInterests, explicitInterests, pushInterests } from './profile';
import { getState } from './state';
import { interestLabel } from './interest-label';

export type InterestSuggestion = {
  id: string;
  canonical_id: string;
  profile_key: string;
  labels?: { ru?: string; en?: string; es?: string };
  evidence_count: number;
};

let current: InterestSuggestion | null = null;
const listeners = new Set<(value: InterestSuggestion | null) => void>();

export function offerInterestSuggestion(value: any): void {
  if (!value?.id || !value?.profile_key) return;
  current = value as InterestSuggestion;
  listeners.forEach((fn) => fn(current));
}

export function clearInterestSuggestion(): void {
  current = null;
  listeners.forEach((fn) => fn(null));
}

export function useInterestSuggestion(): InterestSuggestion | null {
  const [value, setValue] = useState(current);
  useEffect(() => {
    listeners.add(setValue);
    return () => { listeners.delete(setValue); };
  }, []);
  return value;
}

/**
 * Integration seam for the parallel shared interest-normalization/confirmation flow.
 *
 * Today the common confirmed writer is addInterests(): it updates device state and the canonical
 * onboarding profile endpoint.  When fork 1 replaces that writer, this is the single call site to
 * adapt; the prompt and evidence tracker do not get their own normalizer or profile writer.
 */
export async function confirmSuggestedInterest(key: string): Promise<boolean> {
  const have = explicitInterests(getState().profile);
  if (have.some((value) => value.trim().toLowerCase() === key.trim().toLowerCase())) {
    return pushInterests();
  }
  return addInterests([key]);
}

export function suggestedInterestLabel(value: InterestSuggestion): string {
  const lang = getLang();
  const backend = String(value.labels?.[lang] || '').trim();
  if (backend && backend.toLowerCase() !== value.profile_key.toLowerCase()) return backend;
  return interestLabel(value.profile_key) || String(value.labels?.en || value.profile_key);
}

export const INTEREST_SUGGESTION_COPY = {
  eyebrow: () => T('Новое в твоих интересах', 'A recurring interest'),
  title: (label: string) => T(`Добавить «${label}» в интересы?`, `Add “${label}” to your interests?`),
  note: (n: number) => T(
    `Ты выбирал(а) это уже ${n} раз. Добавим только после твоего подтверждения.`,
    `You have chosen this ${n} times. It is added only with your confirmation.`,
  ),
  confirm: () => T('Добавить в профиль', 'Add to profile'),
  dismiss: () => T('Не сейчас', 'Not now'),
  failed: () => T('Не удалось сохранить. Попробуй ещё раз.', 'Could not save it. Try again.'),
};
