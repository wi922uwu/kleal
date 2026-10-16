/**
 * Знаки восьми тем карты интересов — контуром, одного веса и одного цвета.
 *
 * Раньше темы были эмодзи: восемь разноцветных картинок разной плотности, и поле читалось пёстрым.
 * Контурный знак держит тот же смысл (мяч, чашка, хлопушка, гора…), но звучит тихо и одинаково, а
 * цвет в карте остаётся одному событию — выбору.
 */
import React from 'react';
import Svg, { Circle, Line, Path, Rect } from 'react-native-svg';

export function TopicIcon({ topic, size = 24, c = '#3B404B' }: { topic: string; size?: number; c?: string }) {
  const p = { fill: 'none', stroke: c, strokeWidth: 1.6, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {topic === 'sports' ? (
        <>
          <Circle cx={12} cy={12} r={8.5} {...p} />
          {/* Мяч со швами по бокам — с меридианами он читался глобусом. */}
          <Path d="M6 6c2.6 3.2 2.6 8.8 0 12M18 6c-2.6 3.2-2.6 8.8 0 12" {...p} />
        </>
      ) : topic === 'social' ? (
        <>
          <Path d="M5 9.5h11v4.5a4.5 4.5 0 0 1-4.5 4.5h-2A4.5 4.5 0 0 1 5 14V9.5z" {...p} />
          <Path d="M16 11h1.4a2.4 2.4 0 0 1 0 4.8H16M8.6 3.8c-.8 1 .8 2 0 3M12.2 3.8c-.8 1 .8 2 0 3" {...p} />
        </>
      ) : topic === 'culture' ? (
        <>
          <Rect x={3.5} y={9} width={17} height={11} rx={2.2} {...p} />
          <Path d="M3.9 9 18.6 4.6l.9 3.1M8.2 7.7l1.9 2.2M12.9 6.3l1.9 2.2" {...p} />
        </>
      ) : topic === 'outdoors' ? (
        <>
          <Path d="M3 19.5 9.3 10l3.6 5.3 2.3-3.2 5.8 7.4H3z" {...p} />
          <Circle cx={16.8} cy={6.2} r={1.9} {...p} />
        </>
      ) : topic === 'music' ? (
        <>
          <Path d="M9 17.5V6.3l10-2.1v11.2" {...p} />
          <Circle cx={6.8} cy={17.5} r={2.3} {...p} />
          <Circle cx={16.8} cy={15.4} r={2.3} {...p} />
        </>
      ) : topic === 'games' ? (
        <>
          <Path d="M7.6 8.5h8.8a4 4 0 0 1 3.9 4.9l-.8 3.4a2.3 2.3 0 0 1-3.9 1l-1.9-2.1h-3.4l-1.9 2.1a2.3 2.3 0 0 1-3.9-1l-.8-3.4a4 4 0 0 1 3.9-4.9z" {...p} />
          <Path d="M8.6 11.3v3M7.1 12.8h3" {...p} />
          <Circle cx={15.4} cy={12} r={0.9} fill={c} />
          <Circle cx={17} cy={13.7} r={0.9} fill={c} />
        </>
      ) : topic === 'learning' ? (
        <>
          <Path d="M4.5 5.5a2 2 0 0 1 2-2h12v14h-12a2 2 0 0 0-2 2v-14z" {...p} />
          <Path d="M4.5 19.5a2 2 0 0 0 2 2h12v-4M8.5 7.5h6" {...p} />
        </>
      ) : topic === 'tech' ? (
        <>
          <Rect x={5} y={5} width={14} height={10} rx={1.8} {...p} />
          <Line x1={3} y1={18.5} x2={21} y2={18.5} {...p} />
        </>
      ) : (
        <Circle cx={12} cy={12} r={3} fill={c} />
      )}
    </Svg>
  );
}
