/**
 * Возрастной диапазон — кадр OF.08 («Age», 18-28).
 *
 * Два обычных ползунка, а не один с двумя ручками: две ручки на одной дорожке требуют своей
 * жестовой обработки и на ощупь путаются, когда сходятся вплотную. Здесь же граница всегда ясна.
 *
 * ГРАНИЦА НЕ ОТТАЛКИВАЕТ ПАЛЕЦ. Раньше нижний ползунок, доведённый выше верхнего, обрезался
 * (`Math.min(v, max)`) — и это выглядело сломанным: ручка возвращалась под палец обратно на каждом
 * кадре, пока его не отпустишь. Теперь тот, кого двигают, идёт куда ведут, а второй уступает
 * дорогу. Так ведёт себя любой парный диапазон, и снапбека не возникает вовсе.
 *
 * Обе дорожки закрашены СЛЕВА, как у любого ползунка. У прежней пары заливки были встречными
 * (у верхнего — справа), и две одинаковые полосы читались как противоречащие друг другу.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Slider from '@react-native-community/slider';
import { PREFS } from '../candidates';
import { color, space, type } from '../theme';

const FLOOR = 18;   // ниже — жёсткий гейт матчинга, спрашивать бессмысленно
const CEIL = 80;

export function AgeRange({
  min, max, onChange,
}: {
  min: number;
  max: number;
  onChange: (lo: number, hi: number) => void;
}) {
  return (
    <View style={{ gap: space.xs }}>
      <View style={s.head}>
        <Text style={s.label}>{PREFS.ageFrom()}</Text>
        <Text style={s.value}>{min}</Text>
      </View>
      <Slider
        minimumValue={FLOOR}
        maximumValue={CEIL}
        step={1}
        value={min}
        onValueChange={(v) => {
          const lo = Math.round(v);
          onChange(lo, Math.max(max, lo));      // верхний уступает, а не отталкивает нижний назад
        }}
        minimumTrackTintColor={color.primary}
        maximumTrackTintColor={color.neutral100}
        thumbTintColor={color.primary}
        accessibilityLabel={PREFS.ageFrom()}
      />

      <View style={s.head}>
        <Text style={s.label}>{PREFS.ageTo()}</Text>
        <Text style={s.value}>{max}</Text>
      </View>
      <Slider
        minimumValue={FLOOR}
        maximumValue={CEIL}
        step={1}
        value={max}
        onValueChange={(v) => {
          const hi = Math.round(v);
          onChange(Math.min(min, hi), hi);
        }}
        minimumTrackTintColor={color.primary}
        maximumTrackTintColor={color.neutral100}
        thumbTintColor={color.primary}
        accessibilityLabel={PREFS.ageTo()}
      />
    </View>
  );
}

const s = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  label: { ...type.caption, color: color.muted } as any,
  value: { ...type.body, color: color.fg, fontWeight: '600' } as any,
});
