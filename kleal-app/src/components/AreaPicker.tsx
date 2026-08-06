/**
 * Страна, радиус и карта — кадр A.06.
 *
 * Карта здесь не украшение: круг показывает, что именно человек соглашается считать «рядом», и
 * без него «19 км» — абстракция. Радиус уходит в матчинг жёстким фильтром, поэтому важно, чтобы
 * человек видел, что выбирает.
 *
 * Сама карта вынесена в RadiusMap с суффиксами .native/.web — react-native-maps нативный, и
 * условный require ломал веб-сборку целиком.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import Slider from '@react-native-community/slider';
import * as Location from 'expo-location';
import { RadiusMap } from './RadiusMap';
import { STEP_AREA } from '../onboarding';
import { T } from '../i18n';
import { color, radius as rad, space, type } from '../theme';

export type Area = { label: string; lat: number; lon: number; km: number };

/** Небольшой список — то, что не в нём, человек пишет в композер, и разбирает агент. */
const PLACES: [string, number, number][] = [
  ['Spain', 41.3874, 2.1686],
  ['Portugal', 38.7223, -9.1393],
  ['Italy', 41.9028, 12.4964],
  ['Germany', 52.52, 13.405],
  ['France', 48.8566, 2.3522],
];

export function AreaPicker({ value, onChange }: { value: Area; onChange: (a: Area) => void }) {
  const [open, setOpen] = useState(false);
  const [locating, setLocating] = useState(false);

  const detect = async () => {
    setLocating(true);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) return;
      const pos = await Location.getCurrentPositionAsync({});
      // Координаты огрубляются до двух знаков (~1 км): точная точка человека не нужна ни поиску,
      // ни тем более чужому экрану, а огрубление здесь — единственное место, где это дёшево.
      const lat = Math.round(pos.coords.latitude * 100) / 100;
      const lon = Math.round(pos.coords.longitude * 100) / 100;
      onChange({ ...value, lat, lon, label: T('Моё местоположение', 'My location') });
    } catch {
      /* отказ в доступе — просто остаёмся на выбранной стране */
    } finally {
      setLocating(false);
    }
  };

  return (
    <View style={{ gap: space.md }}>
      {/* Роль обязательна: без неё Pressable на вебе остаётся <div> — не кнопка ни для скринридера,
          ни для клавиатуры. Здесь это ещё и единственный способ сменить страну. */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={value.label}
        accessibilityState={{ expanded: open }}
        style={s.select}
        onPress={() => setOpen((o) => !o)}
      >
        <Text style={s.selectText}>{value.label}</Text>
        <Text style={s.chev}>{open ? '⌃' : '⌄'}</Text>
      </Pressable>

      {open ? (
        <View style={s.options}>
          {PLACES.map(([name, lat, lon]) => (
            <Pressable
              key={name}
              accessibilityRole="button"
              style={s.option}
              onPress={() => {
                onChange({ ...value, label: name, lat, lon });
                setOpen(false);
              }}
            >
              <Text style={s.optionText}>{name}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      <View style={s.radiusRow}>
        <Text style={s.radiusLabel}>{STEP_AREA.radiusLabel()}</Text>
        <Text style={s.radiusValue}>{value.km} km</Text>
      </View>
      <Slider
        minimumValue={1}
        maximumValue={50}
        step={1}
        value={value.km}
        onValueChange={(km) => onChange({ ...value, km: Math.round(km) })}
        minimumTrackTintColor={color.primary}
        maximumTrackTintColor={color.neutral100}
        thumbTintColor={color.primary}
      />

      <Pressable
        accessibilityRole="button"
        accessibilityState={{ busy: locating }}
        style={s.detect}
        onPress={detect}
      >
        {locating ? (
          <ActivityIndicator color={color.onPrimary} />
        ) : (
          <Text style={s.detectText}>◎  {STEP_AREA.detect()}</Text>
        )}
      </Pressable>

      <View style={s.map}>
        <RadiusMap lat={value.lat} lon={value.lon} km={value.km} />
        <View style={s.kmBadge}>
          <Text style={s.kmBadgeText}>{value.km}{'\n'}km</Text>
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  select: {
    height: 52,
    borderRadius: rad.md,
    backgroundColor: color.neutral100,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  selectText: { ...type.body, color: color.muted } as any,
  chev: { fontSize: 18, color: color.muted },
  options: { backgroundColor: color.card, borderRadius: rad.md, borderWidth: 1, borderColor: color.border },
  option: { paddingVertical: 12, paddingHorizontal: 16 },
  optionText: { ...type.body, color: color.fg } as any,
  radiusRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  radiusLabel: { ...type.body, color: color.fg } as any,
  radiusValue: { ...type.body, color: color.primary, fontWeight: '600' } as any,
  detect: {
    height: 52,
    borderRadius: rad.md,
    backgroundColor: color.ink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  detectText: { ...type.button, color: color.onPrimary } as any,
  map: { height: 250, borderRadius: rad.md, overflow: 'hidden', backgroundColor: color.neutral100 },
  kmBadge: {
    position: 'absolute',
    left: '50%',
    top: '50%',
    marginLeft: -26,
    marginTop: -26,
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: color.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  kmBadgeText: { color: color.onPrimary, fontSize: 13, fontWeight: '700', textAlign: 'center', lineHeight: 15 },
});
