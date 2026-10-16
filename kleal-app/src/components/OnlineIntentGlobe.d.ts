import type React from 'react';
import type { OnlineIntentGlobeProps } from '../online-intent-globe';

/**
 * Whole-world Online + Hybrid country overview.
 * Platform implementations are selected by Metro via .native.tsx / .web.tsx.
 */
export declare function OnlineIntentGlobe(props: OnlineIntentGlobeProps & {
  /** Выбранная страна: подсвечена в ленте и на планете. */
  selected?: string | null;
  /** Список прокрутили к стране — планета доворачивается к ней. */
  onSelect?: (code: string | null) => void;
  /** Сколько пикселей снизу закрыл лист: планета уходит в оставшееся окно. */
  onSheet?: (bottom: number) => void;
  /** Счётчик тапов по плашке страны на планете: лист открывается и подвозит раздел. */
  pickSignal?: number;
  /** Счётчик нажатий лупы в панели экрана: лист открывается. */
  openSignal?: number;
}): React.ReactElement;
