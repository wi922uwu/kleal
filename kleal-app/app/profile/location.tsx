/**
 * Профиль → «Location» (борд «Profile — new layout», B.07).
 *
 * Был листом поверх профиля; на борде — свой экран: страна, карта с радиусом, «Detect my location» и
 * коралловая «Save changes». Сам выбор — тот же AreaPicker, что в онбординге (First run A.06): это
 * одна и та же вещь, и два разных выбиральщика однажды разошлись бы.
 */
import { useState } from 'react';
import { Pressable, Text, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, SectionHead } from '../../src/components/ProfileShell';
import { AreaPicker, Area, DEFAULT_AREA, PLACES } from '../../src/components/AreaPicker';
import { useLang } from '../../src/i18n';
import { useOnb } from '../../src/state';
import { profile as profileApi } from '../../src/api';
import { writeFact, patchFor } from '../../src/fields';
import { PRO, SHEETS, adaptSummary } from '../../src/profile';
import { color, radius as rad, type } from '../../src/theme';

/**
 * ЭКРАН ОТКРЫВАЕТСЯ НА СВОЁМ МЕСТЕ, А НЕ В БАРСЕЛОНЕ: страна — сохранённая, иначе выведенная по
 * городу; точка — своя, иначе точка своего города из списка. Подробности — в истории LocationSheet
 * (app/profile/index.tsx до 17.10.2026): каждая подстановка по умолчанию врала своему человеку.
 */
function current(p: any): Area {
  const city = String(p.city || '').trim() || DEFAULT_AREA.city;
  const home = PLACES.find((x) => x.cities.some((c) => c[0] === city));
  const saved = String(p.country || '').trim();
  const country = saved || home?.country || DEFAULT_AREA.country;
  const list = PLACES.find((x) => x.country === country);
  const row = list?.cities.find((c) => c[0] === city) || list?.cities[0];
  const lat = Number(p.geo?.coarseLat);
  const lon = Number(p.geo?.coarseLon);
  const mine = Number.isFinite(lat) && Number.isFinite(lon) && !(lat === 0 && lon === 0);
  return {
    country,
    city,
    pinCity: home || !list ? city : row![0],
    lat: mine ? lat : (row?.[1] ?? DEFAULT_AREA.lat),
    lon: mine ? lon : (row?.[2] ?? DEFAULT_AREA.lon),
    km: p.geo?.maxDistanceKm ?? 15,
    moved: !home && mine,
  };
}

export default function Location() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const p = st.profile;
  const [area, setArea] = useState<Area>(() => current(p));
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    // location.area ложится в profile.city — это ГОРОД; страна — отдельным фактом.
    writeFact('location.area', area.city);
    writeFact('location.country', area.country);
    writeFact('location.lat', area.lat);
    writeFact('location.lon', area.lon);
    writeFact('location.radiusKm', area.km);
    setBusy(true);
    if (p.name) {
      await profileApi.update(
        p.name,
        patchFor(['location.area', 'location.country', 'location.lat', 'location.lon', 'location.radiusKm'])
      ).catch(() => {});
    }
    setBusy(false);
    adaptSummary();               // «живёт в Барселоне» после переезда в Италию — неправда
    router.back();
  };

  return (
    <ProfileShell
      title={SHEETS.location()}
      onBack={() => router.back()}
      scrollEnabled={!dragging}
      footer={
        <Pressable accessibilityRole="button" accessibilityState={{ busy }} style={[s.cta, busy && { opacity: 0.7 }]}
                   onPress={busy ? undefined : save}>
          <Text style={s.ctaText}>{PRO.saveChanges()}</Text>
        </Pressable>
      }
    >
      <SectionHead title={PRO.whereLooks()} note={PRO.whereNote()} />
      <AreaPicker value={area} onChange={setArea} onDragChange={setDragging} />
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
});
