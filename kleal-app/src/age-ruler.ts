import type { ReplyLang } from './i18n';

/** Existing onboarding rule: adults only, with the same supported upper bound as production. */
export const AGE_MIN = 18;
export const AGE_MAX = 80;
export const AGE_DEFAULT = 28;
export const AGE_STEP_PX = 18;
export const AGE_FEEDBACK_INTERVAL_MS = 55;

/*
  'worklet' у трёх функций ниже: линейка возраста считает год на нативном потоке (Reanimated), в
  том же кадре, что и сдвиг делений, — иначе число отставало от делений (владелец, 27.09). Вне
  Reanimated директива — просто строка и ничего не меняет.
*/
export function clampAge(value: unknown, fallback = AGE_DEFAULT): number {
  'worklet';
  const parsed = typeof value === 'number' ? value : Number(value);
  const safeFallback = Math.max(AGE_MIN, Math.min(AGE_MAX, Math.round(fallback)));
  if (!Number.isFinite(parsed)) return safeFallback;
  return Math.max(AGE_MIN, Math.min(AGE_MAX, Math.round(parsed)));
}

export function ageToOffset(age: unknown, step = AGE_STEP_PX): number {
  'worklet';
  return -(clampAge(age) - AGE_MIN) * step;
}

export function offsetToAge(offset: number, step = AGE_STEP_PX): number {
  'worklet';
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
      hint: `Проведи по линейке. Свайп влево увеличивает возраст, вправо — уменьшает. Диапазон от ${AGE_MIN} до ${AGE_MAX}.`,
      increment: 'Увеличить возраст',
      decrement: 'Уменьшить возраст',
    };
  }
  if (locale === 'es') {
    return {
      label: 'Edad',
      value: `${age} años`,
      hint: `Desliza la regla. Hacia la izquierda aumenta la edad y hacia la derecha la reduce. De ${AGE_MIN} a ${AGE_MAX}.`,
      increment: 'Aumentar la edad',
      decrement: 'Reducir la edad',
    };
  }
  return {
    label: 'Age',
    value: `${age} years`,
    hint: `Swipe along the ruler. Swipe left to increase and right to decrease. Range ${AGE_MIN} to ${AGE_MAX}.`,
    increment: 'Increase age',
    decrement: 'Decrease age',
  };
}
