/**
 * Страна, город, радиус и карта — кадр A.06.
 *
 * Карта здесь не украшение: круг показывает, что именно человек соглашается считать «рядом», и
 * без него «19 км» — абстракция. Радиус уходит в матчинг жёстким фильтром, поэтому важно, чтобы
 * человек видел, что выбирает.
 *
 * ГОРОД, а не только страна. Раньше список был один и состоял из стран, и выбранное значение
 * уезжало в профиль полем `city`: у человека в Барселоне в карточке стояло «Spain». Это не
 * косметика — §5.3 матчинга читает город из ctx.city, то есть поиск шёл по стране целиком, а на
 * экране кандидата вместо города стояло название государства.
 *
 * ТОЧКУ МОЖНО ДВИГАТЬ. Список городов короткий намеренно: он покрывает частые случаи, а всё
 * остальное — посёлок, район, «я сейчас у родителей» — человек ставит булавкой сам. Без этого
 * список пришлось бы делать справочником мира, и он всё равно бы кого-то не покрыл.
 *
 * Сама карта вынесена в RadiusMap с суффиксами .native/.web — react-native-maps нативный, и
 * условный require ломал веб-сборку целиком.
 */
import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator, ScrollView } from 'react-native';
import Slider from '@react-native-community/slider';
import * as Location from 'expo-location';
import { RadiusMap } from './RadiusMap';
import { AddressField } from './AddressField';
import { STEP_AREA } from '../onboarding';
import { reverseGeocode } from '../geocode';
import { T, getLang } from '../i18n';
import { color, radius as rad, space, type } from '../theme';

export type Area = {
  /** Страна — как её называет список. Уходит в профиль отдельным полем. */
  country: string;
  /** Город. ИМЕННО он уезжает в profile.city и в ctx.city поиска. */
  city: string;
  lat: number;
  lon: number;
  km: number;
  /** Булавку двигали руками: город в подписи больше не обязан совпадать с точкой. */
  moved?: boolean;
  /**
   * Адрес точки словами — «Carrer de Verdi 12, Gràcia». Появляется, когда карту подвинули, и
   * заменяет собой строку города: пока там стояла «Barcelona», а булавка была в Жироне, экран врал.
   */
  address?: string;
  /**
   * Город, ВЫБРАННЫЙ В СПИСКЕ, — якорь для «Вернуть к …».
   *
   * Отдельно от `city`, потому что после переезда точки `city` — это уже настоящий город из
   * геокодера («Алелья»), и кнопка возврата, называя его, обещала вернуть туда, где человек и так
   * стоит. Возвращает она к тому, что он выбирал руками.
   */
  pinCity?: string;
};

/**
 * Страны и города. Список короткий намеренно — см. шапку: чего в нём нет, человек ставит булавкой.
 * Координаты — центры городов, огрублять их не нужно: это не местоположение человека, а якорь карты.
 */
/**
 * Подпись страны на языке интерфейса. КЛЮЧ остаётся английским: по нему ищет сервер и он лежит
 * в профиле; 'Spain' показывалось человеку как есть — и русскому, и испанцу.
 */
const COUNTRY_LABEL: Record<string, [string, string]> = {
  Spain: ['Испания', 'España'], Portugal: ['Португалия', 'Portugal'], Italy: ['Италия', 'Italia'],
  Germany: ['Германия', 'Alemania'], France: ['Франция', 'Francia'],
};
export const countryLabel = (k: string): string => {
  const r = COUNTRY_LABEL[k];
  return r ? T(r[0], k, r[1]) : k;
};

export const PLACES: { country: string; cities: [string, number, number][] }[] = [
  { country: 'Spain', cities: [
    ['Barcelona', 41.3874, 2.1686], ['Madrid', 40.4168, -3.7038], ['Valencia', 39.4699, -0.3763],
    ['Sevilla', 37.3891, -5.9845], ['Málaga', 36.7213, -4.4214], ['Bilbao', 43.2630, -2.9350],
    ['Palma', 39.5696, 2.6502], ['Zaragoza', 41.6488, -0.8891],
  ] },
  { country: 'Portugal', cities: [
    ['Lisboa', 38.7223, -9.1393], ['Porto', 41.1579, -8.6291], ['Faro', 37.0194, -7.9304],
    ['Coimbra', 40.2033, -8.4103], ['Braga', 41.5454, -8.4265], ['Funchal', 32.6669, -16.9241],
  ] },
  { country: 'Italy', cities: [
    ['Roma', 41.9028, 12.4964], ['Milano', 45.4642, 9.1900], ['Napoli', 40.8518, 14.2681],
    ['Torino', 45.0703, 7.6869], ['Firenze', 43.7696, 11.2558], ['Bologna', 44.4949, 11.3426],
    ['Venezia', 45.4408, 12.3155], ['Palermo', 38.1157, 13.3615],
  ] },
  { country: 'Germany', cities: [
    ['Berlin', 52.5200, 13.4050], ['München', 48.1351, 11.5820], ['Hamburg', 53.5511, 9.9937],
    ['Köln', 50.9375, 6.9603], ['Frankfurt', 50.1109, 8.6821], ['Stuttgart', 48.7758, 9.1829],
    ['Düsseldorf', 51.2277, 6.7735], ['Leipzig', 51.3397, 12.3731],
  ] },
  { country: 'France', cities: [
    ['Paris', 48.8566, 2.3522], ['Lyon', 45.7640, 4.8357], ['Marseille', 43.2965, 5.3698],
    ['Toulouse', 43.6047, 1.4442], ['Nice', 43.7102, 7.2620], ['Bordeaux', 44.8378, -0.5792],
    ['Nantes', 47.2184, -1.5536], ['Lille', 50.6292, 3.0573],
  ] },
];

/**
 * СПИСОК СТРАН ВМЕСТЕ СО СВОЕЙ.
 *
 * `PLACES` — сорок городов на пять стран, и это правильно: запуск идёт по Испании, а справочник
 * мира здесь не нужен (см. шапку). Но человек, чьей страны в списке нет, видел ЧУЖУЮ: строка
 * страны говорила «Испания» москвичу и лондонцу, а «Вернуть к …» звало в Барселону. В базе таких
 * сто сорок четыре профиля из восьмисот.
 *
 * Поэтому страна из профиля, если её в списке нет, добавляется первой строкой — со своим
 * единственным городом и своей точкой. Ничего не выдумывается: и страна, и город, и координаты
 * взяты у самого человека.
 */
function placesFor(a: { country?: string; city?: string; lat?: number; lon?: number }) {
  const own = String(a?.country || '').trim();
  if (!own || PLACES.some((p) => p.country === own)) return PLACES;
  const city = String(a?.city || '').trim() || own;
  const lat = Number.isFinite(Number(a?.lat)) ? Number(a?.lat) : DEFAULT_AREA.lat;
  const lon = Number.isFinite(Number(a?.lon)) ? Number(a?.lon) : DEFAULT_AREA.lon;
  return [{ country: own, cities: [[city, lat, lon] as [string, number, number]] }, ...PLACES];
}

const citiesOf = (country: string, list = PLACES) =>
  (list.find((p) => p.country === country) || list[0]).cities;

/** Значение по умолчанию — первая строка списка. Одно место, чтобы экран и компонент не разошлись. */
export const DEFAULT_AREA: Area = {
  country: PLACES[0].country,
  city: PLACES[0].cities[0][0],
  pinCity: PLACES[0].cities[0][0],
  lat: PLACES[0].cities[0][1],
  lon: PLACES[0].cities[0][2],
  km: 19,
};

export function AreaPicker({
  value, onChange, onDragChange,
}: {
  value: Area;
  onChange: (a: Area) => void;
  /** Палец на карте. Экран-родитель обязан на это время выключить свою прокрутку — иначе
   *  ScrollView забирает вертикальный жест себе, и булавка дёргается на месте. */
  onDragChange?: (dragging: boolean) => void;
}) {
  const [open, setOpen] = useState<'' | 'country' | 'city'>('');
  const [locating, setLocating] = useState(false);
  /** Идёт запрос адреса по координатам. Строка не должна молча показывать старое место. */
  const [naming, setNaming] = useState(false);
  /** Строка поиска места — для тех, чьего города в списке нет. */
  const [query, setQuery] = useState('');

  /**
   * Подвинули точку — спрашиваем, что там на самом деле, и подменяем строку города адресом.
   *
   * Запрос уходит ПОСЛЕ того, как карту отпустили (onMove зовётся из onRegionChangeComplete), и
   * только если точка правда уехала. Гонка снята счётчиком: пока летит ответ, человек успевает
   * подвинуть карту ещё раз, и старый ответ не имеет права перезаписать новый.
   *
   * Город из ответа кладётся в area.city — это он уезжает в поиск (§5.3, ctx.city). Раньше туда
   * попадал город из списка, и человек, поставивший точку в Жироне, искался по Барселоне.
   */
  const req = useRef(0);
  useEffect(() => {
    if (!value.moved || !onChange) return;
    const mine = ++req.current;
    setNaming(true);
    reverseGeocode(value.lat, value.lon, getLang())
      .then((p) => {
        if (mine !== req.current) return;          // пришёл ответ на позапрошлую точку — выбрасываем
        setNaming(false);
        if (!p) return;                            // не узнали — строка останется прежней, врать нечем
        onChange({ ...value, address: p.label, city: p.city || value.city });
      })
      .catch(() => { if (mine === req.current) setNaming(false); });
    // Только координаты: перерисовка от смены радиуса не должна дёргать геокодер.
  }, [value.moved, value.lat, value.lon]);   // eslint-disable-line react-hooks/exhaustive-deps

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
      onChange({ ...value, lat, lon, moved: true });
    } catch {
      /* отказ в доступе — просто остаёмся на выбранном городе */
    } finally {
      setLocating(false);
    }
  };

  const pickCountry = (country: string) => {
    const [city, lat, lon] = citiesOf(country, places)[0];
    onChange({ ...value, country, city, pinCity: city, lat, lon, moved: false, address: undefined });
    setOpen('');
  };

  const pickCity = ([city, lat, lon]: [string, number, number]) => {
    onChange({ ...value, city, pinCity: city, lat, lon, moved: false, address: undefined });
    setOpen('');
  };

  /** Страны, среди которых выбирают: короткий список плюс своя, если её там нет. */
  const places = placesFor(value);

  return (
    <View style={{ gap: space.md }}>
      {/* Роль обязательна: без неё Pressable на вебе остаётся <div> — не кнопка ни для скринридера,
          ни для клавиатуры. Здесь это ещё и единственный способ сменить страну. */}
      <Row
        label={STEP_AREA.country()}
        value={countryLabel(value.country)}
        open={open === 'country'}
        onPress={() => setOpen((o) => (o === 'country' ? '' : 'country'))}
      />
      {open === 'country' ? (
        <Options>
          {places.map((p) => (
            <Option key={p.country} label={countryLabel(p.country)} on={p.country === value.country} onPress={() => pickCountry(p.country)} />
          ))}
        </Options>
      ) : null}

      {/* Одна строка на две роли: город из списка — или адрес точки, если карту двигали.
          Нажатие в обоих случаях открывает список городов, то есть даёт вернуться к списку. */}
      <Row
        label={value.moved ? STEP_AREA.address() : STEP_AREA.city()}
        value={value.moved ? (naming ? STEP_AREA.naming() : value.address || value.city) : value.city}
        open={open === 'city'}
        onPress={() => setOpen((o) => (o === 'city' ? '' : 'city'))}
      />
      {open === 'city' ? (
        <Options>
          {citiesOf(value.country, places).map((c) => (
            <Option key={c[0]} label={c[0]} on={c[0] === value.city && !value.moved} onPress={() => pickCity(c)} />
          ))}
        </Options>
      ) : null}

      {/*
        НЕТ ГОРОДА В СПИСКЕ — НАЙДИ. Список короткий намеренно (см. шапку), а двигать карту до
        Жироны из Барселоны долго. Поле то же, что везде, где спрашивают место: подсказки смещены к
        выбранному городу, булавка справа ставит точку туда, где человек стоит. Выбор ведёт себя как
        сдвиг карты: точка встаёт на место, город берётся из ответа геокодера.
      */}
      <AddressField
        style={s.search}
        value={query}
        onChange={setQuery}
        placeholder={STEP_AREA.search()}
        near={{ lat: value.lat, lon: value.lon }}
        onPick={(h) => {
          setQuery(h.label);
          onChange({ ...value, lat: h.lat, lon: h.lon, moved: true, city: h.city || value.city, address: h.label });
        }}
      />

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

      {/* Значка «19 km» посреди карты больше нет: то же число стоит строкой выше, а в центре
          теперь живая булавка — два кружка друг на друге читались как одно и не двигались. */}
      <View style={s.map}>
        <RadiusMap
          lat={value.lat}
          lon={value.lon}
          km={value.km}
          onMove={(lat, lon) => onChange({ ...value, lat, lon, moved: true })}
          onDragChange={onDragChange}
        />
      </View>
      <View style={s.hintRow}>
        <Text style={s.hint}>{value.moved ? STEP_AREA.pinMoved() : STEP_AREA.pinHint()}</Text>
        {value.moved ? (
          <Pressable
            accessibilityRole="button"
            hitSlop={8}
            onPress={() => {
              const anchor = value.pinCity || DEFAULT_AREA.city;
              const c = citiesOf(value.country, places).find((x) => x[0] === anchor) || citiesOf(value.country, places)[0];
              onChange({ ...value, city: c[0], pinCity: c[0], lat: c[1], lon: c[2], moved: false, address: undefined });
            }}
          >
            <Text style={s.hintAction}>{STEP_AREA.pinReset(value.pinCity || DEFAULT_AREA.city)}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

/** Строка «подпись — значение — шеврон». Две одинаковые, чтобы страна и город читались как пара. */
function Row({ label, value, open, onPress }: { label: string; value: string; open: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${label}: ${value}`}
      accessibilityState={{ expanded: open }}
      style={s.select}
      onPress={onPress}
    >
      <Text style={s.selectLabel}>{label}</Text>
      <Text style={s.selectText}>{value}</Text>
      <Text style={s.chev}>{open ? '⌃' : '⌄'}</Text>
    </Pressable>
  );
}

function Options({ children }: { children: React.ReactNode }) {
  // Городов до восьми — список прокручивается, а не растягивает шаг анкеты на два экрана.
  return <ScrollView style={s.options} nestedScrollEnabled>{children}</ScrollView>;
}

function Option({ label, on, onPress }: { label: string; on?: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      style={s.option}
      onPress={onPress}
    >
      <Text style={[s.optionText, on && { color: color.primary, fontWeight: '700' }]}>{label}</Text>
      {on ? <Text style={s.tick}>✓</Text> : null}
    </Pressable>
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
    gap: space.sm,
  },
  selectLabel: { ...type.bodySmall, color: color.muted } as any,
  selectText: { flex: 1, ...type.body, color: color.fg, textAlign: 'right' } as any,
  chev: { fontSize: 18, color: color.muted },
  options: {
    maxHeight: 216, backgroundColor: color.card, borderRadius: rad.md,
    borderWidth: 1, borderColor: color.border,
  },
  option: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, paddingHorizontal: 16 },
  optionText: { flex: 1, ...type.body, color: color.fg } as any,
  tick: { fontSize: 16, color: color.primary, fontWeight: '700' },
  /** Поле поиска — того же роста и тона, что строки страны и города над ним. */
  search: { height: 52, borderRadius: rad.md, backgroundColor: color.neutral100, paddingHorizontal: 16, color: color.fg, fontSize: 15 },
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
  hintRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginTop: -space.sm },
  hint: { flex: 1, ...type.caption, color: color.muted } as any,
  hintAction: { ...type.caption, color: color.primary, fontWeight: '700' } as any,
});
