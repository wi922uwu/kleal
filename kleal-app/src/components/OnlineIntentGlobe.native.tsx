import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import MapView, { Marker, PROVIDER_GOOGLE, type Camera } from 'react-native-maps';
import {
  onlineIntentGlobeCopy,
  type OnlineIntentCountryCluster,
  type OnlineIntentGlobeProps,
} from '../online-intent-globe';
import { color, shadow, type } from '../theme';
import { OnlineIntentGlobeOverlay, type OnlineIntentGlobeSelection } from './OnlineIntentGlobeOverlay';

const WORLD: Camera = {
  center: { latitude: 10, longitude: 0 },
  pitch: 0,
  heading: 0,
  // MapKit clamps very large longitudeDelta values. Altitude is the reliable iOS world view;
  // zoom is the corresponding Google/Android value. Supplying both lets each provider use its own.
  altitude: 50_000_000,
  zoom: 0.55,
};

const WORLD_STYLE: any[] = [
  { elementType: 'geometry', stylers: [{ color: color.neutral100 }] },
  { elementType: 'labels.icon', stylers: [{ visibility: 'off' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: color.muted }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: color.card }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', stylers: [{ visibility: 'off' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: color.neutral300 }] },
];

const UNKNOWN = '__location_unknown__';

export function OnlineIntentGlobe({
  model,
  status,
  onRetry,
  onOpenIntent,
  contentInsets,
  testID = 'online-intent-globe',
}: OnlineIntentGlobeProps) {
  const map = useRef<MapView>(null);
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

  const showWorld = () => {
    setSelectedKey(null);
    map.current?.animateCamera(WORLD, { duration: 500 });
  };

  const selectCountry = (country: OnlineIntentCountryCluster) => {
    setSelectedKey(country.code);
    map.current?.animateCamera(
      {
        center: { latitude: country.latitude, longitude: country.longitude },
        pitch: 0,
        heading: 0,
        altitude: 8_000_000,
        zoom: 3.2,
      },
      { duration: 450 },
    );
  };

  const markers = useMemo(() => status === 'ready' ? model.countries : [], [model.countries, status]);

  return (
    <View style={s.root} testID={testID}>
      <MapView
        ref={map}
        accessibilityLabel={model.locale === 'ru' ? 'Карта онлайн-интентов по странам' : 'Online intents by country map'}
        provider={Platform.OS === 'android' ? PROVIDER_GOOGLE : undefined}
        customMapStyle={Platform.OS === 'android' ? WORLD_STYLE : undefined}
        initialCamera={WORLD}
        minZoomLevel={0}
        maxZoomLevel={6}
        pitchEnabled={false}
        rotateEnabled
        scrollEnabled
        zoomEnabled
        moveOnMarkerPress={false}
        showsBuildings={false}
        showsCompass
        showsIndoors={false}
        showsMyLocationButton={false}
        showsPointsOfInterests={false}
        showsScale={false}
        showsTraffic={false}
        showsUserLocation={false}
        toolbarEnabled={false}
        testID="online-globe-map"
        style={StyleSheet.absoluteFill}
      >
        {markers.map((country) => {
          const selected = selectedKey === country.code;
          return (
            <Marker
              key={`${model.locale}-${country.code}-${country.count}-${selected ? 'on' : 'off'}`}
              coordinate={{ latitude: country.latitude, longitude: country.longitude }}
              anchor={{ x: 0.5, y: 0.5 }}
              tracksViewChanges={false}
              onPress={() => selectCountry(country)}
              accessibilityRole="button"
              accessibilityLabel={copy.countryMarker(country.name, country.count)}
              accessibilityHint={copy.countryHint}
              testID={`online-globe-country-${country.code}`}
            >
              <View style={[s.marker, selected && s.markerOn]}>
                <Text style={[s.markerCode, selected && s.markerCodeOn]}>{country.code}</Text>
                <View style={[s.markerCount, selected && s.markerCountOn]}>
                  <Text style={s.markerCountText}>{country.count > 999 ? '999+' : country.count}</Text>
                </View>
              </View>
            </Marker>
          );
        })}
      </MapView>
      <OnlineIntentGlobeOverlay
        model={model}
        status={status}
        contentInsets={contentInsets}
        selection={selection}
        onRetry={onRetry}
        onResetWorld={showWorld}
        onOpenUnknown={() => setSelectedKey(UNKNOWN)}
        onCloseSelection={() => setSelectedKey(null)}
        onOpenIntent={onOpenIntent}
      />
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, minHeight: 280, backgroundColor: color.neutral100 },
  marker: {
    minWidth: 50, height: 38, paddingLeft: 10, paddingRight: 20,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    borderRadius: 19, borderWidth: 2, borderColor: color.card,
    backgroundColor: color.fg, ...shadow.card,
  },
  markerOn: { borderColor: color.primary, backgroundColor: color.card },
  markerCode: { ...type.labelMedium, color: color.onPrimary } as any,
  markerCodeOn: { color: color.fg },
  markerCount: {
    position: 'absolute', right: -7, top: -7, minWidth: 24, height: 24,
    paddingHorizontal: 5, borderRadius: 12, borderWidth: 2, borderColor: color.card,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
  },
  markerCountOn: { borderColor: color.primary, backgroundColor: color.fg },
  markerCountText: { ...type.labelSmall, color: color.onPrimary } as any,
});
