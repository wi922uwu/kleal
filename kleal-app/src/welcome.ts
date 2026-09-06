/** Welcome is ephemeral UI state. Never persist it with the account/profile. */
export const WELCOME_LAST = 2;
export const WAVE_THRESHOLD = 70;
export const WAVE_CURVE = 160;

export type WelcomeAxis = 'horizontal' | 'vertical' | null;
export function welcomeAxis(dx: number, dy: number, canPull: boolean): WelcomeAxis {
  if (Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy) * 1.4) return 'horizontal';
  if (canPull && Math.abs(dy) > 8 && Math.abs(dy) > Math.abs(dx) * 1.4) return 'vertical';
  return null;
}

export function welcomeTarget(index: number, dx: number, vx: number) {
  if (Math.abs(dx) < 8 || (Math.abs(dx) < 40 && Math.abs(vx) < 0.5)) return index;
  return Math.max(0, Math.min(WELCOME_LAST, index + (dx < 0 ? 1 : -1)));
}

export function welcomePull(dy: number, travel: number) {
  return dy > 0 ? -Math.min(dy / 3, 36) : Math.min(-dy, travel);
}

export function welcomePullComplete(dy: number) {
  return -dy >= WAVE_THRESHOLD;
}

/** Tokens invalidate animation completions after blur, resize, or another focus. */
export function createWelcomeSession() {
  let epoch = 0;
  let focused = false;
  let busy = false;
  let launched = false;
  let index = 0;
  return {
    get index() { return index; },
    get available() { return focused && !busy && !launched; },
    focus() { epoch++; focused = true; busy = false; launched = false; index = 0; },
    blur() { epoch++; focused = false; busy = false; },
    interrupt() { epoch++; busy = false; },
    begin() {
      if (!focused || busy || launched) return null;
      busy = true;
      return ++epoch;
    },
    settle(token: number, to: number) {
      if (!focused || token !== epoch || launched) return false;
      index = Math.max(0, Math.min(WELCOME_LAST, to));
      busy = false;
      return true;
    },
    complete(token: number) {
      if (!focused || token !== epoch || launched) return false;
      launched = true;
      return true;
    },
  };
}
