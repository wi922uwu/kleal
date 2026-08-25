export type TimePart = 'hours' | 'minutes';

export type ClockParts = {
  hours: number;
  minutes: number;
};

const LIMIT: Record<TimePart, number> = { hours: 23, minutes: 59 };

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, Math.trunc(value)));
}

/** Text that may stay in a focused HH/MM field without forcing it back to two digits. */
export function sanitizeTimePartInput(text: string): string {
  return String(text ?? '').replace(/\D/g, '').slice(0, 2);
}

/** A partial edit updates the dial only when it already represents an in-range number. */
export function editableTimePartValue(text: string, part: TimePart): number | null {
  const clean = sanitizeTimePartInput(text);
  if (!clean) return null;
  const value = Number(clean);
  return value <= LIMIT[part] ? value : null;
}

/** Blur/submit finishes a partial edit, restoring the current part for an empty field. */
export function normalizeTimePart(
  text: string,
  part: TimePart,
  fallback: number,
): { text: string; value: number } {
  const clean = sanitizeTimePartInput(text);
  const value = clamp(clean ? Number(clean) : fallback, 0, LIMIT[part]);
  return { text: String(value).padStart(2, '0'), value };
}

/** Pasting a complete clock into either field updates both fields atomically. */
export function parseClockPaste(text: string): ClockParts | null {
  const match = String(text ?? '').match(/^\s*(\d{1,2})\s*:\s*(\d{1,2})\s*$/);
  if (!match) return null;
  return {
    hours: clamp(Number(match[1]), 0, LIMIT.hours),
    minutes: clamp(Number(match[2]), 0, LIMIT.minutes),
  };
}

export function splitClock(totalMinutes: number): ClockParts {
  const total = ((Math.round(totalMinutes) % 1440) + 1440) % 1440;
  return { hours: Math.floor(total / 60), minutes: total % 60 };
}

export function replaceTimePart(totalMinutes: number, part: TimePart, value: number): number {
  const clock = splitClock(totalMinutes);
  if (part === 'hours') clock.hours = clamp(value, 0, LIMIT.hours);
  else clock.minutes = clamp(value, 0, LIMIT.minutes);
  return clock.hours * 60 + clock.minutes;
}

export function formatTimePart(value: number): string {
  return String(Math.max(0, Math.trunc(value))).padStart(2, '0');
}
