/**
 * Токены дизайна Kleal.
 *
 * Значения взяты из переменных Figma (борд «💫 Kleal»), а не подобраны на глаз — те же самые,
 * что уже живут в вебовом прототипе. Один источник на оба клиента: пока они существуют
 * параллельно, расхождение в цвете или радиусе читается как баг, а не как редизайн.
 */

export const color = {
  bg: '#F7F8FA',            // --background
  card: '#FFFFFF',          // --card
  fg: '#181B22',            // --foreground
  muted: '#5A616E',         // --muted-foreground
  border: '#E2E5EC',        // --border
  neutral100: '#EEF0F4',    // --secondary / --neutral-100
  neutral300: '#CDD2DC',
  neutral400: '#A9B0BE',
  primary: '#F13A59',       // --primary-solid
  onPrimary: '#FFFFFF',     // --neutral-0
  successText: '#0F7340',
  successBg: '#E8F7EE',
  infoText: '#1F58BE',
  infoBg: '#E8F1FD',
  warnText: '#9A5400',
  warnBg: '#FFF4E5',
  danger: '#E5484D',
  ink: '#181B22',
  line: '#ECEEF2',
  /**
   * Подложка обложки там, где своей картинки нет: карточки мероприятий и приглашений на главной.
   * Лежала сырым литералом `#e2604f` в трёх местах app/home.tsx — а правило проекта прямо
   * запрещает свои цвета в экранах: «перекрасить приложение значит поменять токены, а не искать
   * литералы по экранам» (AGENTS.md).
   */
  coverFallback: '#E2604F',
  /** Полупрозрачное белое поверх обложки — кружки поверх цветной подложки. */
  onCoverSoft: '#FFFFFFCC',
  /**
   * Затемнение под нижним листом. Стояло литералом `'#0006'` в девяти экранах — ровно тот случай,
   * который правило «своих цветов нет» и запрещает: поменять глубину затемнения значило бы найти
   * девять мест и не забыть ни одного.
   */
  scrim: '#00000066',
} as const;

export const radius = {
  none: 0,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 28,
  full: 999,
} as const;

export const space = {
  none: 0,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
} as const;

/**
 * Типографика. В Figma это Geist; шрифт пока не подключён, поэтому используется системный —
 * размеры, высоты строк и насыщенность при этом точные. Подключение Geist через expo-font
 * поменяет только начертание, а не метрики.
 */
export const type = {
  h2: { fontSize: 24, lineHeight: 32, fontWeight: '600' },
  title: { fontSize: 17, lineHeight: 24, fontWeight: '600' },
  body: { fontSize: 15, lineHeight: 22, fontWeight: '400' },
  bodySmall: { fontSize: 13, lineHeight: 18, fontWeight: '400' },
  labelMedium: { fontSize: 13, lineHeight: 16, fontWeight: '500' },
  labelSmall: { fontSize: 11, lineHeight: 16, fontWeight: '500' },
  button: { fontSize: 15, lineHeight: 20, fontWeight: '600' },
  caption: { fontSize: 12, lineHeight: 16, fontWeight: '400' },
} as const;

export const shadow = {
  card: {
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 4,
  },
  fab: {
    shadowColor: '#F5455C',
    shadowOpacity: 0.45,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
} as const;
