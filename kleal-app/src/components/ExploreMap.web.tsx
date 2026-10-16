/**
 * Веб-половина карты интентов.
 *
 * Настоящей карты здесь нет: MapLibre RN — нативный модуль, а веб-цель нужна, чтобы экраны
 * открывались в браузере при проверке. Рисуется схема: точки расставлены по своим НАСТОЯЩИМ
 * координатам, приведённым к прямоугольнику, — так видно и сколько их, и как они разбросаны,
 * и работает ли выбор пина. Подложки и объёмных домов нет, и это подписано: выдавать схему
 * за карту нельзя, иначе на вебе «всё работает», а на устройстве оказывается пусто.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable, Image } from 'react-native';
import { color, shadow, type } from '../theme';
import { mediaUrl } from '../api';
import type { ExplorePin } from '../explore';
import { pinKey } from '../explore';

import { T } from '../i18n';
export function ExploreMap({
  pins,
  onPick,
  stacks,
  selectedId = null,
}: {
  pins: ExplorePin[];
  center?: { lat: number; lon: number } | null;
  pitch?: number;
  onPick?: (pin: ExplorePin) => void;
  stacks?: Map<string, number>;
  showMe?: boolean;
  recenter?: number;
  selectedId?: string | null;
}) {
  // Одна точка на координату — как и на устройстве, иначе счёт пинов на вебе и в приложении разный.
  const seen = new Set<string>();
  const shown = pins.filter((p) => {
    const k = pinKey(p);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });

  // Границы разброса. Если все точки в одном месте — рамка вырождается, поэтому минимум задан.
  const lats = shown.map((p) => p.lat);
  const lons = shown.map((p) => p.lon);
  const minLa = Math.min(...lats, 0);
  const maxLa = Math.max(...lats, 0);
  const minLo = Math.min(...lons, 0);
  const maxLo = Math.max(...lons, 0);
  const spanLa = Math.max(0.01, maxLa - minLa);
  const spanLo = Math.max(0.01, maxLo - minLo);

  return (
    <View style={s.wrap}>
      {shown.map((p) => {
        const n = stacks?.get(pinKey(p)) || 1;
        const on = !!selectedId && p.id === selectedId;
        // Широта растёт вверх, экранный y — вниз, поэтому переворачивается.
        const top = `${8 + (1 - (p.lat - minLa) / spanLa) * 78}%`;
        const left = `${8 + ((p.lon - minLo) / spanLo) * 78}%`;
        return (
          <Pressable
            key={p.id}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            accessibilityLabel={`${p.who || p.title} — ${p.area}`}
            onPress={onPick ? () => onPick(p) : undefined}
            style={[s.pin, { top, left } as any, on && s.pinOn]}
          >
            {p.photo ? (
              <Image source={{ uri: mediaUrl(p.photo) }} style={s.photo} />
            ) : (
              <Text style={s.initial}>{(p.who || p.title || '?').slice(0, 1).toUpperCase()}</Text>
            )}
            {n > 1 ? <Text style={s.stack}>+{n - 1}</Text> : null}
          </Pressable>
        );
      })}
      <Text style={s.note}>{T('схема · настоящая карта только на устройстве', 'sketch · the real map is on the device only', 'esquema · el mapa de verdad solo en el móvil')}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { ...StyleSheet.absoluteFill, backgroundColor: color.neutral100 },
  pin: {
    position: 'absolute', width: 44, height: 44, borderRadius: 22,
    backgroundColor: color.card, borderWidth: 2, borderColor: color.card,
    alignItems: 'center', justifyContent: 'center', ...shadow.card,
  },
  pinOn: { borderColor: color.primary, borderWidth: 3 },
  photo: { width: 40, height: 40, borderRadius: 20 },
  initial: { ...type.labelMedium, color: color.muted } as any,
  stack: {
    position: 'absolute', left: -8, top: -6,
    ...type.labelSmall, color: color.onPrimary, backgroundColor: color.fg,
    borderRadius: 10, paddingHorizontal: 5, overflow: 'hidden',
  } as any,
  note: {
    position: 'absolute', bottom: 8, alignSelf: 'center',
    ...type.caption, color: color.neutral400,
  } as any,
});
