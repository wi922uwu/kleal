/** Welcome is ephemeral UI state. Never persist it with the account/profile. */
export const WELCOME_LAST = 2;
export const WAVE_THRESHOLD = 70;
export const WAVE_CURVE = 160;
/**
 * ВКЛАДКА «Let’s Start» (макет «First run», A.02): тёмный горб 218×60 по центру низа вместо волны
 * на всю ширину. Коробка та же, 390×160: горб занимает её нижние 60 точек, а под коробкой лежит
 * тёмная заливка — при подъёме вкладка тянет за собой занавес на весь экран.
 */
export const TAB_TOP = 100;
export const TAB_L = 86;
export const TAB_R = 304;
export const WELCOME_WAVE_PATH =
  'M0 160 L86 160 C132.18 160 153.51 100 195 100 C236.49 100 257.83 160 304 160 L390 160 Z';

/**
 * Куда палец может взяться. Вкладка ловит касание своим прямоугольником с запасом в 12 точек: сама
 * она 60 точек высотой, и требовать попадания в изгиб горба — значит промахиваться по краям. Всё,
 * что ниже коробки, — занавес, он виден только когда поднят.
 */
export function welcomeWaveContains(x: number, y: number, width: number, restY: number, height: number, lift = 0) {
  if (![x, y, width, restY, height, lift].every(Number.isFinite)
    || width <= 0 || x < 0 || x > width || y < 0 || y > height) return false;
  const localY = y - restY + lift;
  if (localY >= WAVE_CURVE) return true;
  const px = x * 390 / width;
  return localY >= TAB_TOP - 12 && px >= TAB_L - 12 && px <= TAB_R + 12;
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
