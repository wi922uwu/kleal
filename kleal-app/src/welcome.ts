/** Welcome is ephemeral UI state. Never persist it with the account/profile. */
export const WELCOME_LAST = 2;
export const WAVE_THRESHOLD = 70;
export const WAVE_CURVE = 160;
export const WELCOME_WAVE_PATH = 'M0 132 C 78 132 120 20 195 20 C 270 20 312 132 390 132 L390 160 L0 160 Z';

/** Hit-test the visible SVG fill, not its transparent rectangular bounding box. */
export function welcomeWaveContains(x: number, y: number, width: number, restY: number, height: number, lift = 0) {
  if (![x, y, width, restY, height, lift].every(Number.isFinite)
    || width <= 0 || x < 0 || x > width || y < 0 || y > height) return false;
  const localY = y - restY + lift;
  if (localY >= 132) return true;
  if (localY < 20) return false;
  // The path is symmetric. Invert the left cubic's monotone x to find its y.
  const px = Math.min(x, width - x) * 390 / width;
  let lo = 0, hi = 1;
  for (let n = 0; n < 20; n++) {
    const t = (lo + hi) / 2, u = 1 - t;
    const curveX = 3 * u * u * t * 78 + 3 * u * t * t * 120 + t * t * t * 195;
    if (curveX < px) lo = t; else hi = t;
  }
  const t = (lo + hi) / 2;
  const curveY = 132 - 112 * (3 * t * t - 2 * t * t * t);
  return localY >= curveY;
}

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
