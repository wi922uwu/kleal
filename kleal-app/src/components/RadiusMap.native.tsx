/**
 * Карта с кругом радиуса — нативная половина.
 *
 * Разделено по платформам суффиксом файла, а не проверкой Platform.OS внутри одного модуля:
 * условный require всё равно попадает в веб-бандл, и Metro падает на нативном модуле
 * («Importing native-only module … codegenNativeCommands on web»). Суффикс решает это на уровне
 * разрешения путей — веб про этот файл просто не узнаёт.
 */
import React, { useEffect, useRef } from 'react';
import { StyleSheet } from 'react-native';
import MapView, { Circle, Marker } from 'react-native-maps';

export function RadiusMap({ lat, lon, km }: { lat: number; lon: number; km: number }) {
  const ref = useRef<MapView>(null);
  const delta = Math.max(0.05, (km / 111) * 2.6);   // ~110 км в градусе, плюс поля вокруг круга
  const region = { latitude: lat, longitude: lon, latitudeDelta: delta, longitudeDelta: delta };

  useEffect(() => {
    ref.current?.animateToRegion(region, 350);
  }, [lat, lon, km]);

  return (
    <MapView ref={ref} style={StyleSheet.absoluteFill} initialRegion={region} pointerEvents="none">
      <Circle
        center={{ latitude: lat, longitude: lon }}
        radius={km * 1000}
        strokeColor="rgba(241,58,89,0.55)"
        fillColor="rgba(241,58,89,0.18)"
      />
      <Marker coordinate={{ latitude: lat, longitude: lon }} />
    </MapView>
  );
}
