import type { ReplyLang } from './i18n';

/** Existing onboarding rule: adults only, with the same supported upper bound as production. */
export const AGE_MIN = 18;
export const AGE_MAX = 80;
export const AGE_DEFAULT = 28;
export const AGE_STEP_PX = 18;
export const AGE_FEEDBACK_INTERVAL_MS = 55;

export function clampAge(value: unknown, fallback = AGE_DEFAULT): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  const safeFallback = Math.max(AGE_MIN, Math.min(AGE_MAX, Math.round(fallback)));
  if (!Number.isFinite(parsed)) return safeFallback;
  return Math.max(AGE_MIN, Math.min(AGE_MAX, Math.round(parsed)));
}

export function ageToOffset(age: unknown, step = AGE_STEP_PX): number {
  return -(clampAge(age) - AGE_MIN) * step;
}

export function offsetToAge(offset: number, step = AGE_STEP_PX): number {
  if (!Number.isFinite(offset) || !Number.isFinite(step) || step <= 0) return AGE_DEFAULT;
  return clampAge(AGE_MIN + Math.round(-offset / step));
}

export function snapAgeOffset(offset: number, step = AGE_STEP_PX): number {
  return ageToOffset(offsetToAge(offset, step), step);
}

export function shouldEmitAgeFeedback({
  previousAge,
  nextAge,
  now,
  lastFeedbackAt,
  userInitiated,
  appActive,
  interval = AGE_FEEDBACK_INTERVAL_MS,
}: {
  previousAge: number;
  nextAge: number;
  now: number;
  lastFeedbackAt: number;
  userInitiated: boolean;
  appActive: boolean;
  interval?: number;
}): boolean {
  return userInitiated
    && appActive
    && nextAge !== previousAge
    && now - lastFeedbackAt >= interval;
}

function ruYears(age: number): string {
  const tens = age % 100;
  const ones = age % 10;
  if (tens >= 11 && tens <= 14) return 'лет';
  if (ones === 1) return 'год';
  if (ones >= 2 && ones <= 4) return 'года';
  return 'лет';
}

export function ageRulerCopy(locale: ReplyLang, age: number) {
  if (locale === 'ru') {
    return {
      label: 'Возраст',
      value: `${age} ${ruYears(age)}`,
      hint: `Проведи по линейке. Свайп вверх увеличивает возраст, вниз — уменьшает. Диапазон от ${AGE_MIN} до ${AGE_MAX}.`,
      increment: 'Увеличить возраст',
      decrement: 'Уменьшить возраст',
    };
  }
  if (locale === 'es') {
    return {
      label: 'Edad',
      value: `${age} años`,
      hint: `Desliza la regla. Hacia arriba aumenta la edad y hacia abajo la reduce. De ${AGE_MIN} a ${AGE_MAX}.`,
      increment: 'Aumentar la edad',
      decrement: 'Reducir la edad',
    };
  }
  return {
    label: 'Age',
    value: `${age} years`,
    hint: `Swipe along the ruler. Swipe up to increase and down to decrease. Range ${AGE_MIN} to ${AGE_MAX}.`,
    increment: 'Increase age',
    decrement: 'Decrease age',
  };
}
