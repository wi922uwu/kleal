/**
 * Иконки. Отрисованы контурами, а не набраны символами вроде «≡» или «☺»: типографские знаки
 * выглядят на каждой платформе по-своему, не выравниваются по сетке и на борде их нет.
 */
import React from 'react';
import Svg, { Path, Circle, Rect, Line } from 'react-native-svg';
import { color } from '../theme';

type P = { size?: number; c?: string };

export const IconIntents = ({ size = 24, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round">
    <Circle cx={12} cy={12} r={9.2} />
    <Line x1={8} y1={9.5} x2={16} y2={9.5} />
    <Line x1={8} y1={12} x2={16} y2={12} />
    <Line x1={8} y1={14.5} x2={13} y2={14.5} />
  </Svg>
);

export const IconSearch = ({ size = 24, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round">
    <Circle cx={11} cy={11} r={7} />
    <Line x1={16.2} y1={16.2} x2={21} y2={21} />
  </Svg>
);

export const IconMessages = ({ size = 24, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round">
    <Path d="M21 11.5c0 4-4 7.2-9 7.2-1 0-2-.13-2.9-.37L4 20l1.2-3.3C3.8 15.4 3 13.6 3 11.5c0-4 4-7.2 9-7.2s9 3.2 9 7.2z" />
    <Circle cx={8.5} cy={11.5} r={0.9} fill={c} stroke="none" />
    <Circle cx={12} cy={11.5} r={0.9} fill={c} stroke="none" />
    <Circle cx={15.5} cy={11.5} r={0.9} fill={c} stroke="none" />
  </Svg>
);

export const IconProfile = ({ size = 24, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round">
    <Circle cx={12} cy={12} r={9.2} />
    <Circle cx={12} cy={10} r={3} />
    <Path d="M6.4 18.4a6.2 6.2 0 0 1 11.2 0" />
  </Svg>
);

/** Четырёхлучевая искра на центральной кнопке. */
export const IconSpark = ({ size = 28, c = '#fff' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill={c}>
    <Path d="M12 2.6l1.9 5.6 5.6 1.9-5.6 1.9L12 17.6l-1.9-5.6L4.5 10l5.6-1.9L12 2.6z" />
    <Path d="M18.6 15.4l.9 2.5 2.5.9-2.5.9-.9 2.5-.9-2.5-2.5-.9 2.5-.9.9-2.5z" opacity={0.9} />
  </Svg>
);

/** Белая галочка в залитом зелёном круге — карточка «Profile photo set», кадр A.13. */
export const IconCheckCircle = ({ size = 28 }: { size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24">
    <Circle cx={12} cy={12} r={11} fill={color.successText} />
    <Path d="M7 12.4l3.2 3.2L17 8.8" fill="none" stroke="#fff" strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

export const IconMic = ({ size = 20, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round">
    <Rect x={9} y={3} width={6} height={11} rx={3} />
    <Path d="M5.5 11.5a6.5 6.5 0 0 0 13 0" />
    <Line x1={12} y1={18} x2={12} y2={21} />
  </Svg>
);

export const IconChevronLeft = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M15 5l-7 7 7 7" />
  </Svg>
);

export const IconPin = ({ size = 18, c = '#fff' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round">
    <Path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" />
    <Circle cx={12} cy={10} r={2.6} />
  </Svg>
);

export const IconImagePlaceholder = ({ size = 64, c = color.neutral400 }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round">
    <Rect x={3} y={4} width={18} height={16} rx={3} />
    <Circle cx={9} cy={10} r={2} />
    <Path d="M4 18l5.5-5 4 3.5L17 13l3 3" />
  </Svg>
);

export const IconPerson = ({ size = 26, c = color.neutral400 }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round">
    <Circle cx={12} cy={8.5} r={3.6} />
    <Path d="M5 19.5a7 7 0 0 1 14 0" />
  </Svg>
);

// ---------------------------------------------------------------- главный экран

export const IconBell = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M18 8.5a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16s-2-1.5-2-6.5z" />
    <Path d="M13.7 19a2 2 0 0 1-3.4 0" />
  </Svg>
);

export const IconCalendar = ({ size = 16, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round">
    <Rect x={3.5} y={5} width={17} height={16} rx={3} />
    <Line x1={3.5} y1={10} x2={20.5} y2={10} />
    <Line x1={8} y1={3} x2={8} y2={6} />
    <Line x1={16} y1={3} x2={16} y2={6} />
  </Svg>
);

export const IconClock = ({ size = 16, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={12} cy={12} r={8.6} />
    <Path d="M12 7.4V12l3.1 1.9" />
  </Svg>
);

export const IconBookmark = ({ size = 20, c = color.fg, filled = false }: P & { filled?: boolean }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? c : 'none'} stroke={c} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M6.5 4.5h11a1 1 0 0 1 1 1V20l-6.5-4-6.5 4V5.5a1 1 0 0 1 1-1z" />
  </Svg>
);

export const IconChat = ({ size = 18, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M20.5 11.4c0 3.9-3.8 7-8.5 7-1 0-1.9-.13-2.8-.37L4 20l1.2-3.2A6.9 6.9 0 0 1 3.5 11.4c0-3.9 3.8-7 8.5-7s8.5 3.1 8.5 7z" />
  </Svg>
);

export const IconGroups = ({ size = 18, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={9} cy={9} r={3.2} />
    <Path d="M3.5 18.5a5.6 5.6 0 0 1 11 0" />
    <Path d="M16 6.4a3.2 3.2 0 0 1 0 6.2M17.2 14.4a5.6 5.6 0 0 1 3.3 4.1" />
  </Svg>
);

// ---------------------------------------------------------------- строки профиля
// Круглая обводка вокруг иконки рисуется самой строкой, не иконкой: так один и тот же значок
// годится и для строки, и для любого другого места.

export const IconStar = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinejoin="round">
    <Path d="M12 3.6l2.6 5.5 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6L3.4 9.9l6-.8L12 3.6z" />
  </Svg>
);

export const IconFaceScan = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M4 8.5V6a2 2 0 0 1 2-2h2.5M15.5 4H18a2 2 0 0 1 2 2v2.5M20 15.5V18a2 2 0 0 1-2 2h-2.5M8.5 20H6a2 2 0 0 1-2-2v-2.5" />
    <Circle cx={9.4} cy={10.6} r={0.9} fill={c} stroke="none" />
    <Circle cx={14.6} cy={10.6} r={0.9} fill={c} stroke="none" />
    <Path d="M9.4 14.6c1.6 1.3 3.6 1.3 5.2 0" />
  </Svg>
);

export const IconUserLock = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={10} cy={7.6} r={3.2} />
    <Path d="M3.8 19.2a6.4 6.4 0 0 1 8.4-6" />
    <Rect x={14.5} y={14} width={6.5} height={5.6} rx={1.4} />
    <Path d="M16.2 14v-1.5a1.6 1.6 0 0 1 3.2 0V14" />
  </Svg>
);

/** Языки. Знак перевода: иероглиф и латинская буква — тот же смысл, что на кадре. */
export const IconTranslate = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M3.5 6h7M7 4.4V6M9 6c0 3.4-2.4 6.2-5.5 7M5 9.6c.9 2 2.7 3.4 4.8 3.9" />
    <Path d="M12.6 20l3.6-8.6 3.6 8.6M14.1 17h4.2" />
  </Svg>
);

/** Карандаш в рамке — правый край строки профиля. */
export const IconPencil = ({ size = 22, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M4 20h4.2L19 9.2a2 2 0 0 0 0-2.8l-1.4-1.4a2 2 0 0 0-2.8 0L4 15.8V20z" />
    <Path d="M14.2 6.6l3.2 3.2" />
  </Svg>
);

/** Шестерёнка в правом углу шапки профиля — кадр B.01. */
export const IconGear = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={12} cy={12} r={3.2} />
    <Path d="M19.4 14.6a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.2a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1h.2a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </Svg>
);

/** Красная галочка-печать рядом с именем — кадр B.01. */
export const IconVerified = ({ size = 20 }: { size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24">
    <Path
      d="M12 2.2l2.3 1.7 2.8-.2.9 2.7 2.4 1.5-1 2.7 1 2.7-2.4 1.5-.9 2.7-2.8-.2L12 21.8l-2.3-1.7-2.8.2-.9-2.7-2.4-1.5 1-2.7-1-2.7 2.4-1.5.9-2.7 2.8.2L12 2.2z"
      fill={color.primary}
    />
    <Path d="M8.2 12.2l2.6 2.6 5-5.2" fill="none" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

// ---------------------------------------------------------------- мастер интента (O.05–O.09)

/** Онлайн — видеокамера: подпись строки на борде «Video / voice». */
export const IconVideo = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Rect x={3} y={6.5} width={12.5} height={11} rx={2.5} />
    <Path d="M15.5 10.5l5-2.8v8.6l-5-2.8" />
  </Svg>
);

/** Гибрид — плюс, как на кадре O.05. */
export const IconPlusRound = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round">
    <Line x1={12} y1={5} x2={12} y2={19} />
    <Line x1={5} y1={12} x2={19} y2={12} />
  </Svg>
);

export const IconGlobe = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.5} strokeLinecap="round">
    <Circle cx={12} cy={12} r={8.6} />
    <Path d="M3.4 12h17.2M12 3.4c2.5 2.3 3.8 5.2 3.8 8.6s-1.3 6.3-3.8 8.6c-2.5-2.3-3.8-5.2-3.8-8.6s1.3-6.3 3.8-8.6z" />
  </Svg>
);

/** Ссылка — два звена, кадр O.09. */
export const IconLink = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M10 13.5a4.2 4.2 0 0 0 6 0l3-3a4.24 4.24 0 0 0-6-6l-1.6 1.6" />
    <Path d="M14 10.5a4.2 4.2 0 0 0-6 0l-3 3a4.24 4.24 0 0 0 6 6l1.6-1.6" />
  </Svg>
);

/** Аудитория — треугольник-указатель, как метка «Audience» на кадре O.08. */
export const IconPlay = ({ size = 18, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinejoin="round">
    <Path d="M8 5.5l11 6.5-11 6.5V5.5z" />
  </Svg>
);
