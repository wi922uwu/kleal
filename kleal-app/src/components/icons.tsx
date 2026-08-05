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
