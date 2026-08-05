/**
 * Возрастной диапазон — кадр OF.08 («Age», 18-28).
 *
 * Два обычных ползунка, а не один с двумя ручками: две ручки на одной дорожке требуют своей
 * жестовой обработки и на ощупь путаются, когда сходятся вплотную. Здесь же граница всегда ясна.
 *
 * Диапазон не даёт перевернуться: минимум не заходит за максимум и наоборот. Перевёрнутый
 * диапазон матчинг принял бы молча и вернул пустую выдачу без единого объяснения.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Slider from '@react-native-community/slider';
import { T } from '../i18n';
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
    <View style={{ gap: space.sm }}>
      <View style={s.head}>
        <Text style={s.label}>{T('от', 'from')} {min}</Text>
        <Text style={s.value}>{min}–{max}</Text>
        <Text style={s.label}>{T('до', 'to')} {max}</Text>
      </View>
      <Slider
        minimumValue={FLOOR}
        maximumValue={CEIL}
        step={1}
        value={min}
        onValueChange={(v) => onChange(Math.min(Math.round(v), max), max)}
        minimumTrackTintColor={color.neutral100}
        maximumTrackTintColor={color.primary}
        thumbTintColor={color.primary}
      />
      <Slider
        minimumValue={FLOOR}
        maximumValue={CEIL}
        step={1}
        value={max}
        onValueChange={(v) => onChange(min, Math.max(Math.round(v), min))}
        minimumTrackTintColor={color.primary}
        maximumTrackTintColor={color.neutral100}
        thumbTintColor={color.primary}
      />
    </View>
  );
}

const s = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  label: { ...type.caption, color: color.muted } as any,
  value: { ...type.body, color: color.primary, fontWeight: '600' } as any,
});
