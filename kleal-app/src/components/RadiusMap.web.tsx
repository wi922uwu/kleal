/**
 * Веб-половина карты. Настоящей карты здесь нет: react-native-maps нативный, а веб-цель нужна
 * только для проверки экранов в браузере. Круг рисуется схематично, чтобы масштаб радиуса всё же
 * читался и экран не разваливался — но выдавать это за карту нельзя, поэтому и подписано.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { color, type } from '../theme';

export function RadiusMap({ km }: { lat: number; lon: number; km: number }) {
  // Диаметр круга пропорционален радиусу, чтобы «5 км» и «40 км» отличались на глаз.
  const size = Math.max(70, Math.min(210, 60 + km * 3));
  return (
    <View style={s.wrap}>
      <View style={[s.circle, { width: size, height: size, borderRadius: size / 2 }]} />
      <Text style={s.note}>карта — только на устройстве</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
  circle: {
    backgroundColor: 'rgba(241,58,89,0.18)',
    borderWidth: 1,
    borderColor: 'rgba(241,58,89,0.55)',
  },
  note: { ...type.caption, color: color.neutral400, position: 'absolute', bottom: 8 } as any,
});
