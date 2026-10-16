import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import {
  onlineIntentGlobeCopy,
  type OnlineIntentGlobeProps,
} from '../online-intent-globe';
import { color, shadow, type } from '../theme';
import { OnlineIntentGlobeOverlay, type OnlineIntentGlobeSelection } from './OnlineIntentGlobeOverlay';

const UNKNOWN = '__location_unknown__';

export function OnlineIntentGlobe({
  model,
  status,
  onRetry,
  onOpenIntent,
  contentInsets,
  testID = 'online-intent-globe',
}: OnlineIntentGlobeProps) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const copy = onlineIntentGlobeCopy(model.locale);
  const selectedCountry = selectedKey && selectedKey !== UNKNOWN
    ? model.countries.find((country) => country.code === selectedKey) || null
    : null;
  const selection: OnlineIntentGlobeSelection | null = selectedKey === UNKNOWN && model.unknown.length
    ? { key: UNKNOWN, name: copy.unknownTitle, note: copy.unknownNote, intents: model.unknown }
    : selectedCountry
      ? { key: selectedCountry.code, name: selectedCountry.name, intents: selectedCountry.intents }
      : null;

  useEffect(() => {
    if (status !== 'ready' || (selectedKey && !selection)) setSelectedKey(null);
  }, [selection, selectedKey, status]);

  return (
    <View style={s.root} testID={testID}>
      <View accessibilityLabel={model.locale === 'ru' ? 'Схема онлайн-интентов по странам'
        : model.locale === 'es' ? 'Esquema de propuestas online por país' : 'Online intents by country overview'} style={s.world}>
        <View pointerEvents="none" style={[s.grid, s.equator]} />
        <View pointerEvents="none" style={[s.grid, s.meridian]} />
        {status === 'ready' ? model.countries.map((country) => {
          const selected = selectedKey === country.code;
          const left = `${4 + ((country.longitude + 180) / 360) * 92}%`;
          const top = `${5 + ((90 - country.latitude) / 180) * 84}%`;
          return (
            <Pressable
              key={country.code}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              accessibilityLabel={copy.countryMarker(country.name, country.count)}
              accessibilityHint={copy.countryHint}
              onPress={() => setSelectedKey(country.code)}
              testID={`online-globe-country-${country.code}`}
              style={[s.marker, { left, top } as any, selected && s.markerOn]}
            >
              <Text style={[s.markerCode, selected && s.markerCodeOn]}>{country.code}</Text>
              <Text style={s.markerCount}>{country.count > 999 ? '999+' : country.count}</Text>
            </Pressable>
          );
        }) : null}
        <Text style={s.note}>{copy.webNote}</Text>
      </View>
      <OnlineIntentGlobeOverlay
        model={model}
        status={status}
        contentInsets={contentInsets}
        selection={selection}
        onRetry={onRetry}
        onResetWorld={() => setSelectedKey(null)}
        onOpenUnknown={() => setSelectedKey(UNKNOWN)}
        onCloseSelection={() => setSelectedKey(null)}
        onOpenIntent={onOpenIntent}
      />
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, minHeight: 280, padding: 18, backgroundColor: color.neutral100 },
  world: {
    flex: 1, minHeight: 260, position: 'relative', overflow: 'hidden',
    borderRadius: 999, borderWidth: 1, borderColor: color.neutral300,
    backgroundColor: color.neutral300,
  },
  grid: { position: 'absolute', backgroundColor: color.card, opacity: 0.55 },
  equator: { left: 0, right: 0, top: '50%', height: 1 },
  meridian: { top: 0, bottom: 0, left: '50%', width: 1 },
  marker: {
    position: 'absolute', transform: [{ translateX: -24 }, { translateY: -18 }],
    minWidth: 48, height: 36, paddingHorizontal: 8, borderRadius: 18,
    borderWidth: 2, borderColor: color.card, backgroundColor: color.fg,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
    ...shadow.card,
  },
  markerOn: { borderColor: color.primary, backgroundColor: color.card },
  markerCode: { ...type.labelMedium, color: color.onPrimary } as any,
  markerCodeOn: { color: color.fg },
  markerCount: {
    ...type.labelSmall, color: color.onPrimary, backgroundColor: color.primary,
    borderRadius: 10, paddingHorizontal: 5, overflow: 'hidden',
  } as any,
  note: {
    position: 'absolute', bottom: 8, alignSelf: 'center',
    ...type.caption, color: color.muted, backgroundColor: color.card,
    borderRadius: 10, paddingHorizontal: 8,
  } as any,
});
