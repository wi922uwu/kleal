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

/** Замок — подсказка «потяни вверх, чтобы закрепить запись» над кнопкой микрофона. */
export const IconLock = ({ size = 14, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <Rect x={4.5} y={10.5} width={15} height={10.5} rx={2.6} />
    <Path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
  </Svg>
);

/** Шеврон вверх — стрелка над замком, показывает направление протяжки. */
export const IconChevronUp = ({ size = 12, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M5 15l7-7 7 7" />
  </Svg>
);

/** Корзина — отмена записи: и на пороге протяжки влево, и кнопкой у закреплённой. */
export const IconTrash = ({ size = 18, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M4 7h16" />
    <Path d="M9.5 7V5.2A1.2 1.2 0 0 1 10.7 4h2.6a1.2 1.2 0 0 1 1.2 1.2V7" />
    <Path d="M6.5 7l.9 12.1A1.9 1.9 0 0 0 9.3 21h5.4a1.9 1.9 0 0 0 1.9-1.9L17.5 7" />
  </Svg>
);

export const IconChevronLeft = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M15 5l-7 7 7 7" />
  </Svg>
);

/** Стрелка вправо — «здесь можно пройти дальше». Кадр GR.18 ставит её в карточку затеи. */
export const IconChevronRight = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M9 5l7 7-7 7" />
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

/** Колокольчик перечёркнутый — чат без уведомлений (MSG.03/MSG.04). */
export const IconBellOff = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M8.7 3.7A6 6 0 0 1 18 8.5c0 2.6.5 4.3 1.1 5.3" />
    <Path d="M17 17H4s2-1.5 2-6.5c0-.8.1-1.5.4-2.2" />
    <Path d="M13.7 19a2 2 0 0 1-3.4 0" />
    <Line x1={3} y1={3} x2={21} y2={21} />
  </Svg>
);

/** Коробка архива — строка «Archive · N chats» и пункт листа (MSG.03/MSG.04). */
export const IconArchive = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Rect x={3} y={4} width={18} height={5} rx={1} />
    <Path d="M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9" />
    <Path d="M10 13h4" />
  </Svg>
);

/** Флажок жалобы (MSG.03). */
export const IconFlag = ({ size = 22, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M4 21V4" />
    <Path d="M4 4h12l-2 4 2 4H4" />
  </Svg>
);

/*
  Колокольчик шапки главной — «Bell Dot» борда GR.01: контур в 1 точку, точка 6×6 на правом плече.
  ОТДЕЛЬНО ОТ IconBell, потому что точка на борде стоит не поверх контура, а в его РАЗРЫВЕ: плечо
  обрывается перед ней и продолжается ниже. Точка поверх целой линии читается как пятно на ней.
  Без точки рисуется тот же силуэт целиком — иначе, прочитав приглашения, человек увидел бы, что
  колокольчик сменил форму, а не просто погас.
*/
export const IconBellDot = ({ size = 24, c = color.fg, dot }: P & { dot?: string }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
    {dot ? (
      <>
        <Path d="M19.4 14.9C20.2 16.4 21 17 21 17H3s3-2 3-9c0-3.3 2.7-6 6-6 .7 0 1.3.1 1.9.3" />
        <Circle cx={18} cy={8} r={3} fill={dot} stroke="none" />
      </>
    ) : (
      <Path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
    )}
    <Path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
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

// Таймер — «не сможет прийти» в день встречи (борд GR.46 / GR.46a, хвост строки).
export const IconTimer = ({ size = 18, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 18 18" fill="none" stroke={c} strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M7.5 1.5h3M9 10.5l2.25-2.25" />
    <Circle cx={9} cy={10.5} r={6} />
  </Svg>
);

// Молчит: луна со звездой — борд GR.42, хвост строки молчащего организатора.
export const IconMoon = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M19.6 14.2A7.8 7.8 0 1 1 10 4.5a6.2 6.2 0 0 0 9.6 9.7z" />
    <Path d="M18 3.6v3.2M16.4 5.2h3.2" />
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

/** Отправить — бумажный самолётик с композера MSG.06. */
export const IconSend = ({ size = 20, c = '#fff' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M21 3.5L3.5 10.2l6.9 2.9L13.3 20 21 3.5z" />
    <Path d="M10.4 13.1L21 3.5" />
  </Svg>
);

/** Камера — «Take photo» в кадре A.09. */
export const IconCamera = ({ size = 20, c = '#fff' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.6l1.4-2h5l1.4 2h1.6A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5z" />
    <Circle cx={12} cy={12.5} r={3.4} />
  </Svg>
);

/** Загрузка — «Upload photo» в кадре A.09: стрелка вверх в круге. */
export const IconUpload = ({ size = 20, c = '#fff' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={12} cy={12} r={9} />
    <Path d="M12 16.5v-9M8.5 11 12 7.5 15.5 11" />
  </Svg>
);

/** Скрепка — слот вложений в композере MSG.06. */
export const IconClip = ({ size = 20, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M20 11.5l-7.8 7.8a5 5 0 0 1-7.1-7.1l8.1-8.1a3.4 3.4 0 0 1 4.8 4.8l-8 8a1.8 1.8 0 0 1-2.5-2.5l7.4-7.4" />
  </Svg>
);

/** Многоточие — кнопка меню в шапке треда MSG.06. */
export const IconDots = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill={c}>
    <Circle cx={5} cy={12} r={1.7} />
    <Circle cx={12} cy={12} r={1.7} />
    <Circle cx={19} cy={12} r={1.7} />
  </Svg>
);

/**
 * Вертикальное многоточие — кнопка меню у поля ввода, компонент «Chat/Composer» (💣 UI, 6164:19536).
 * В макете три КОЛЕЧКА в коробке 30, а не залитые точки: так значок легче поля рядом.
 */
export const IconEllipsisV = ({ size = 30, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 30 30" fill="none" stroke={c} strokeWidth={1.2}>
    <Circle cx={15} cy={6.5} r={1.2} />
    <Circle cx={15} cy={15} r={1.2} />
    <Circle cx={15} cy={23.5} r={1.2} />
  </Svg>
);

/** Стрелка вверх — отправка в «Chat/Composer»: коралловый штрих 2 в коробке 30. */
export const IconArrowUp = ({ size = 30, c = '#FF385C' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 30 30" fill="none" stroke={c} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M6 15l9-9 9 9" />
    <Path d="M15 6v18" />
  </Svg>
);

/** Треугольник с восклицательным знаком — метка ошибки на плашке (кадр A.03.2c). */
export const IconAlertTriangle = ({ size = 18, c = '#fff' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0z" />
    <Line x1={12} y1={9} x2={12} y2={13} />
    <Line x1={12} y1={17} x2={12.01} y2={17} />
  </Svg>
);

/**
 * Стопка слоёв — первая вкладка новой панели («Layers 2» в борде).
 *
 * Прежний знак был кругом с тремя линиями, то есть «списком». Стопка говорит другое: интентов
 * много и они лежат друг на друге — это ближе к тому, чем вкладка на самом деле является.
 */
export const IconLayers = ({ size = 24, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M12 2.7 2.6 7.4 12 12.1l9.4-4.7L12 2.7z" />
    <Path d="M2.6 13.1 12 17.8l9.4-4.7" />
  </Svg>
);

/** Ползунки фильтра — правая кнопка на панели поиска (кадр «Search · Map»). */
export const IconSliders = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round">
    <Line x1={4} y1={7} x2={20} y2={7} />
    <Line x1={4} y1={12} x2={20} y2={12} />
    <Line x1={4} y1={17} x2={20} y2={17} />
    <Circle cx={9} cy={7} r={2.2} fill={color.card} />
    <Circle cx={15} cy={12} r={2.2} fill={color.card} />
    <Circle cx={8} cy={17} r={2.2} fill={color.card} />
  </Svg>
);

/** Стрелка «где я» — круглая кнопка над картой. */
export const IconLocate = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinejoin="round">
    <Path d="M21 3 3 10.2l7.5 3.3L13.8 21 21 3z" />
  </Svg>
);

/** Сегмент «Карта». Развёрнутый лист, а не булавка: рядом стоит «Список», и пара читается. */
export const IconMap = ({ size = 18, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinejoin="round">
    <Path d="M9 4 3 6.4v13.2L9 17.2l6 2.4 6-2.4V4l-6 2.4L9 4z" />
    <Line x1={9} y1={4} x2={9} y2={17.2} strokeLinecap="round" />
    <Line x1={15} y1={6.4} x2={15} y2={19.6} strokeLinecap="round" />
  </Svg>
);

/** Сегмент «Список». */
export const IconList = ({ size = 18, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round">
    <Line x1={9} y1={6.5} x2={20} y2={6.5} />
    <Line x1={9} y1={12} x2={20} y2={12} />
    <Line x1={9} y1={17.5} x2={20} y2={17.5} />
    <Circle cx={4.6} cy={6.5} r={1.3} fill={c} stroke="none" />
    <Circle cx={4.6} cy={12} r={1.3} fill={c} stroke="none" />
    <Circle cx={4.6} cy={17.5} r={1.3} fill={c} stroke="none" />
  </Svg>
);

/**
 * Кости — «подобрать другое название». Квадрат со скруглением и пять точек: грань «пять».
 *
 * Пять, а не шесть и не одна: на шестёрке в двадцати пикселях точки сливаются в две полосы, а
 * единица читается кнопкой записи. Пятёрка узнаётся костью даже мелко — по диагонали из трёх.
 * Точки залиты, а не обведены: контурная точка в 1.6 пикселя на этом размере пропадает.
 */
export const IconDice = ({ size = 20, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinejoin="round">
    <Rect x={3.5} y={3.5} width={17} height={17} rx={4} />
    <Circle cx={8.5} cy={8.5} r={1.15} fill={c} stroke="none" />
    <Circle cx={15.5} cy={8.5} r={1.15} fill={c} stroke="none" />
    <Circle cx={12} cy={12} r={1.15} fill={c} stroke="none" />
    <Circle cx={8.5} cy={15.5} r={1.15} fill={c} stroke="none" />
    <Circle cx={15.5} cy={15.5} r={1.15} fill={c} stroke="none" />
  </Svg>
);

/** Крестик — закрыть лист (кадры GR.18a–GR.53: «X» в стеклянном круге). */
export const IconClose = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.7} strokeLinecap="round">
    <Line x1={6} y1={6} x2={18} y2={18} />
    <Line x1={18} y1={6} x2={6} y2={18} />
  </Svg>
);

/** Дверь со стрелкой — «вышел(а) из плана», строка состава GR.39/GR.40. */
export const IconExit = ({ size = 18, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    {/* Борд (GR.40 «Left», меню «Leave the group»): скобка слева, стрелка уходит вправо — «вышел». */}
    <Path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3" />
    <Path d="M16 8l4 4-4 4" />
    <Line x1={9} y1={12} x2={20} y2={12} />
  </Svg>
);

/** Календарь с крестиком — «не ответил(а)» на закрытом с паузы плане (GR.40b / 40e). */
export const IconCalendarX = ({ size = 18, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <Rect x={3.5} y={5} width={17} height={16} rx={3} />
    <Line x1={3.5} y1={10} x2={20.5} y2={10} />
    <Line x1={8} y1={3} x2={8} y2={6} />
    <Line x1={16} y1={3} x2={16} y2={6} />
    <Path d="M10 13.5l4 4M14 13.5l-4 4" />
  </Svg>
);

/** Календарь с галочкой — «подтвердил(а)» в строке состава (Calendar Check в борде). */
export const IconCalendarCheck = ({ size = 18, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <Rect x={3.5} y={5} width={17} height={16} rx={3} />
    <Line x1={3.5} y1={10} x2={20.5} y2={10} />
    <Line x1={8} y1={3} x2={8} y2={6} />
    <Line x1={16} y1={3} x2={16} y2={6} />
    <Path d="M9 15.2l2 2 4-4" />
  </Svg>
);

/** Две стрелки по кругу — «показать другие» на знаке темы в карте интересов. */
export const IconRefresh = ({ size = 14, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M20 11a8 8 0 0 0-14.3-4.9L4 8" />
    <Path d="M4 3.5V8h4.5" />
    <Path d="M4 13a8 8 0 0 0 14.3 4.9L20 16" />
    <Path d="M20 20.5V16h-4.5" />
  </Svg>
);

// ---------------------------------------------------------------- меню группы (GR.18a / GR.21a)
// Значки пунктов «Group options»: 20 кораллом, у «End the group» — красным. Контуры Lucide, как
// во всей библиотеке борда (🎨 Icons · Library).

/** Круг с «i» — «Group info». */
export const IconInfo = ({ size = 20, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={12} cy={12} r={10} />
    <Path d="M12 16v-4" />
    <Path d="M12 8h.01" />
  </Svg>
);

/** Человек с плюсом — «Invite more people». */
export const IconUserPlus = ({ size = 20, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <Circle cx={9} cy={7} r={4} />
    <Line x1={19} y1={8} x2={19} y2={14} />
    <Line x1={22} y1={11} x2={16} y2={11} />
  </Svg>
);

/** Человек с галочкой — «Confirmed» в строке участника плана (OF.21). */
export const IconUserCheck = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <Circle cx={9} cy={7} r={4} />
    <Path d="M16 11l2 2 4-4" />
  </Svg>
);

/** Человек с крестиком — «Remove someone». */
export const IconUserX = ({ size = 20, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <Circle cx={9} cy={7} r={4} />
    <Line x1={17} y1={8} x2={22} y2={13} />
    <Line x1={22} y1={8} x2={17} y2={13} />
  </Svg>
);

/** Корона — «Hand the role over». */
export const IconCrown = ({ size = 20, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M11.56 3.27a.5.5 0 0 1 .88 0l2.95 5.6a1 1 0 0 0 1.52.3l4.27-3.67a.5.5 0 0 1 .8.52l-2.83 10.25a1 1 0 0 1-.96.73H5.81a1 1 0 0 1-.96-.73L2.02 6.02a.5.5 0 0 1 .8-.52l4.27 3.67a1 1 0 0 0 1.52-.3z" />
    <Path d="M5 21h14" />
  </Svg>
);

/** Перечёркнутый круг — «End the group». */
export const IconBan = ({ size = 20, c = color.danger }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={12} cy={12} r={10} />
    <Path d="M4.93 4.93l14.14 14.14" />
  </Svg>
);

/** Галочка — выбранная строка в листах выбора (GR.24a, GR.51, GR.30a). */
export const IconCheck = ({ size = 20, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M20 6L9 17l-5-5" />
  </Svg>
);

/** Щит с галочкой — «Exact spot after everyone confirms» на карточке приглашения (GR.56). */
export const IconShieldCheck = ({ size = 18, c = '#238C62' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
    <Path d="M9 12l2 2 4-4" />
  </Svg>
);

/** Пустой щит — мера защиты до отправки жалобы (борд GR.55 «When you send this»). */
export const IconShield = ({ size = 16, c = color.infoText }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
  </Svg>
);

/** Файл с плюсом — «Attach evidence» (борд GR.55). */
export const IconFilePlus = ({ size = 24, c = color.muted }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z" />
    <Path d="M14 2v4a2 2 0 0 0 2 2h4M9 15h6M12 18v-6" />
  </Svg>
);

/** Картотека — «We received your report» (борд GR.55a, круг 104). Рисована в координатах круга. */
export const IconCaseTray = ({ size = 104, c = '#1FAE5E' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 104 104" fill="none" stroke={c} strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M36.25 35.75 29 56.25M67.5 35.75 75 56.25" />
    <Path d="M29 56.25h17.25a5.9 5.9 0 0 0 11.5 0H75V72H29z" />
    <Path d="M43 35v-3.25h17.75V35M41 43v-4h21.75v4M38.5 52.75v-6h27v6" />
  </Svg>
);

/** Спиннер-лучи — «Under review» (борд GR.55a). */
export const IconLoader = ({ size = 16, c = '#FC8F00' }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M12 2v4M16.2 7.8l2.9-2.9M18 12h4M16.2 16.2l2.9 2.9M12 18v4M4.9 19.1l2.9-2.9M2 12h4M4.9 4.9l2.9 2.9" />
  </Svg>
);

/** Два листа — скопировать номер обращения (борд GR.55a). */
export const IconCopy = ({ size = 24, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M15 2a2 2 0 0 1 1.41.59l4 4A2 2 0 0 1 21 8v7a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
    <Path d="M15 2v4a2 2 0 0 0 2 2h4M5 7a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h8a2 2 0 0 0 1.73-1" />
  </Svg>
);

/** Трубка — «Emergency · Call 112» (борд GR.55a). */
export const IconPhone = ({ size = 24, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M13.83 16.57a1 1 0 0 0 1.21-.3l.36-.47A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.47.35a1 1 0 0 0-.29 1.23 14 14 0 0 0 6.39 6.38" />
  </Svg>
);

/** Гарнитура — «Contact support» (борд GR.55a). */
export const IconHeadset = ({ size = 24, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M3 11h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zm0 0a9 9 0 1 1 18 0m0 0v5a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2z" />
    <Path d="M21 16v2a4 4 0 0 1-4 4h-5" />
  </Svg>
);

/** Спасательный круг — «Safety tips» (борд GR.55a). */
export const IconLifeBuoy = ({ size = 24, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={12} cy={12} r={10} />
    <Circle cx={12} cy={12} r={4} />
    <Path d="m4.93 4.93 4.24 4.24M14.83 9.17l4.24-4.24M14.83 14.83l4.24 4.24M9.17 14.83l-4.24 4.24" />
  </Svg>
);

/** Облачко с восклицанием — «Harassment or threats» (борд GR.55). */
export const IconChatWarning = ({ size = 18, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M2.99 16.34a2 2 0 0 1 .1 1.17l-1.07 3.29a1 1 0 0 0 1.24 1.17l3.41-1a2 2 0 0 1 1.1.08A10 10 0 1 0 2.99 16.34" />
    <Path d="M12 8v4M12 16h.01" />
  </Svg>
);

/** Щит с восклицанием — «Unsafe behaviour at the meetup» (борд GR.55). */
export const IconShieldAlert = ({ size = 18, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
    <Path d="M12 8v4M12 16h.01" />
  </Svg>
);

// ---------------------------------------------------------------- мастер «Creating intent»
// Знаки борда «0 · Create the intent» (Figma 6864:119674) — Lucide, линия 1 коралловым на кадрах.

/** «Map Pin Plus» — Hybrid на GR.05: место и звонок разом. */
export const IconPinPlus = ({ size = 22, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M19.9 12.4C19 16.1 12 22 12 22s-8-6.6-8-12a8 8 0 0 1 14.1-5.2" />
    <Circle cx={12} cy={10} r={3} />
    <Line x1={19} y1={3} x2={19} y2={9} />
    <Line x1={16} y1={6} x2={22} y2={6} />
  </Svg>
);

/** «Users» — 1:1 на GR.07: двое. */
export const IconUsers = ({ size = 22, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <Circle cx={9} cy={7} r={4} />
    <Path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
  </Svg>
);

/** «Wand Sparkles» — Regenerate на GR.04. */
export const IconWand = ({ size = 16, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M21.6 2.4 2.4 21.6M14 5l5 5" />
    <Path d="M18 2v3M19.5 3.5h-3M6 5v2M7 6H5M18 17v2M19 18h-2" />
  </Svg>
);

/** «Maximize 2» — развернуть карту на GR.11. */
export const IconMaximize = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
  </Svg>
);

/** «Minimize 2» — свернуть карту на GR.11a. */
export const IconMinimize = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" />
  </Svg>
);

/** «Chevron Down» — выпадающий выбор (город, пояс). */
export const IconChevronDown = ({ size = 20, c = color.fg }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Path d="M6 9l6 6 6-6" />
  </Svg>
);

/** Сплошная булавка листа GR.11a: острие — точка, которая уйдёт в интент. */
export const IconPinSolid = ({ size = 52, c = color.primary }: P) => (
  <Svg width={size} height={size * 56 / 48} viewBox="0 0 48 56">
    <Path d="M24 56C24 56 4 37.5 4 22.5 4 10.1 13 0 24 0s20 10.1 20 22.5C44 37.5 24 56 24 56z" fill={c} />
  </Svg>
);

/** «Locate» — прицел, «найти меня» на карте GR.11a. */
export const IconCrosshair = ({ size = 20, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round">
    <Circle cx={12} cy={12} r={7} />
    <Circle cx={12} cy={12} r={2.5} />
    <Line x1={12} y1={2} x2={12} y2={5} />
    <Line x1={12} y1={19} x2={12} y2={22} />
    <Line x1={2} y1={12} x2={5} y2={12} />
    <Line x1={19} y1={12} x2={22} y2={12} />
  </Svg>
);

/** «Circle Question Mark» — строка «How you meet» в листе правки GR.12b. */
export const IconHelp = ({ size = 20, c = color.primary }: P) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
    <Circle cx={12} cy={12} r={9.5} />
    <Path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3" />
    <Line x1={12} y1={17} x2={12.01} y2={17} />
  </Svg>
);
