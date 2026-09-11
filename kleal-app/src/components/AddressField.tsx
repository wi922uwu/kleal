/**
 * Поле адреса с подсказками и автоопределением — одно на все экраны, где спрашивают место:
 * точный адрес интента, место и район в плане, место в групповом плане.
 *
 * ЗАЧЕМ ПОДСКАЗКИ, А НЕ ПРОСТО СТРОКА. Строку человек пишет как помнит — «Верди 12», «бар у
 * gracia», — и она остаётся строкой: у затеи так и оставались координаты ДОМА автора, потому что
 * взять настоящие было неоткуда. На карте встреча оказывалась не там, где её назначили; узнавал
 * об этом тот, кто приходил не по адресу. Выбранная подсказка приносит И подпись, И координаты.
 * Написанное руками по-прежнему принимается: подсказка это помощь, а не пропуск.
 *
 * АВТООПРЕДЕЛЕНИЕ. Булавка справа от поля и первая строка списка «Моё местоположение»: телефон
 * даёт координаты, обратное геокодирование — адрес, и он встаёт в поле уже с точкой. Чаще всего
 * место встречи называют, стоя в нём или рядом, — и печатать адрес, который телефон знает сам,
 * незачем. Разрешение спрашивается только по нажатию: просить геолокацию при открытии формы —
 * верный способ получить отказ, после которого не будет и подсказок рядом.
 *
 * ПОДСКАЗКИ РЯДОМ, А НЕ ГДЕ-ТО. Поиск смещён к точке: к живой, если её только что определили,
 * иначе к координатам профиля (город из онбординга). «Gran Via» есть в пяти странах, и без
 * смещения первой шла не та.
 *
 * ПОЧЕМУ ЗАПРОС НЕ НА КАЖДУЮ БУКВУ. У геокодера жёсткий лимит (см. src/geocode.ts), и печатающий
 * человек выдал бы десяток запросов на одно слово. Ждём паузу в наборе: перестал печатать — ищем.
 *
 * До 10 сентября 2026 это поле жило внутри app/intent.tsx, а план и групповой план спрашивали
 * место голой строкой — без подсказок и без точки. Вынесено сюда, чтобы место везде спрашивалось
 * одинаково.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TextInput, Pressable, StyleSheet, ActivityIndicator,
  type StyleProp, type TextStyle,
} from 'react-native';
import * as Location from 'expo-location';
import { IconPin } from './icons';
import { suggestAddress, reverseGeocode, type AddressHit } from '../geocode';
import { ADDRESS } from '../address';
import { useLang } from '../i18n';
import { useOnb } from '../state';
import { color, radius as rad, type } from '../theme';

type Near = { lat: number; lon: number };

export function AddressField({
  value, onChange, onPick, placeholder, accessibilityLabel, style, near, mode = 'address',
}: {
  value: string;
  onChange: (t: string) => void;
  /**
   * Выбрали подсказку или определили место. Текст в поле НЕ меняется сам — его ставит экран из
   * `hit.label`: у интента вместе с адресом уезжают координаты и флаг `venue`, у плана — только
   * строка, и решать, что из этого сохранить, должен экран, а не поле.
   */
  onPick: (hit: AddressHit) => void;
  placeholder?: string;
  accessibilityLabel?: string;
  /** Вид самого поля — с экрана, чтобы оно не отличалось от соседних строк той же формы. */
  style?: StyleProp<TextStyle>;
  /** Куда смещать поиск. Не задано — живая точка, если определяли, иначе координаты профиля. */
  near?: Near | null;
  /**
   * `district` — спрашивают район, а не адрес: в подсказках и при автоопределении отдаётся
   * название района («Gràcia»), а не улица с домом.
   */
  mode?: 'address' | 'district';
}) {
  const lang = useLang();
  const st = useOnb();
  const [hits, setHits] = useState<AddressHit[]>([]);
  const [focus, setFocus] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  /** Что уже выбрано: по этой строке не ищем снова, иначе список лезет поверх выбранного. */
  const picked = useRef('');
  /** Живая точка после автоопределения: следующие подсказки ищутся вокруг неё. */
  const live = useRef<Near | null>(null);
  const blurT = useRef<ReturnType<typeof setTimeout> | null>(null);

  const plat = Number((st.profile as any)?.lat);
  const plon = Number((st.profile as any)?.lon);
  const bias: Near | null =
    near ?? live.current ?? (Number.isFinite(plat) && Number.isFinite(plon) ? { lat: plat, lon: plon } : null);

  useEffect(() => {
    const q = value.trim();
    if (!q || q === picked.current) { setHits([]); return; }
    let alive = true;
    const id = setTimeout(() => {
      suggestAddress(q, lang, bias).then((r) => {
        if (!alive) return;
        // Район — первая часть подписи («Gràcia, Barcelona» → «Gràcia»); одинаковые схлопываем.
        if (mode === 'district') {
          const seen = new Set<string>();
          const out: AddressHit[] = [];
          for (const h of r) {
            const label = h.label.split(',')[0].trim();
            if (!label || seen.has(label.toLowerCase())) continue;
            seen.add(label.toLowerCase());
            out.push({ ...h, label });
          }
          setHits(out);
        } else {
          setHits(r);
        }
      });
    }, 450);
    return () => { alive = false; clearTimeout(id); };
  }, [value, lang]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { if (blurT.current) clearTimeout(blurT.current); }, []);

  const pick = (h: AddressHit) => {
    picked.current = h.label;
    setHits([]);
    setNote('');
    onPick(h);
  };

  /**
   * Определить место телефоном. Разрешение — по нажатию, см. шапку. Отказ и сбой различаются в
   * подписи: после отказа человек знает, что дело в настройках, после сбоя — что можно повторить.
   */
  const locate = async () => {
    if (busy) return;
    setBusy(true);
    setNote('');
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== 'granted') { setNote(ADDRESS.denied()); return; }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      live.current = { lat, lon };
      const place = await reverseGeocode(lat, lon, lang);
      if (!place) { setNote(ADDRESS.failed()); return; }
      const label = mode === 'district' ? (place.district || place.city || place.label) : place.label;
      if (!label) { setNote(ADDRESS.failed()); return; }
      pick({ label, city: place.city, lat, lon });
    } catch {
      setNote(ADDRESS.failed());
    } finally {
      setBusy(false);
    }
  };

  /*
    Список закрывается с задержкой: нажатие по строке списка сначала снимает фокус с поля, и без
    паузы строка исчезла бы под пальцем раньше, чем нажатие дошло.
  */
  const onBlur = () => {
    if (blurT.current) clearTimeout(blurT.current);
    blurT.current = setTimeout(() => setFocus(false), 220);
  };
  const onFocus = () => {
    if (blurT.current) clearTimeout(blurT.current);
    setFocus(true);
  };

  const offerLocate = focus && !value.trim() && !busy;

  return (
    <View>
      <View style={s.row}>
        <TextInput
          style={[style, s.input]}
          value={value}
          onChangeText={onChange}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder={placeholder}
          placeholderTextColor={color.neutral400}
          accessibilityLabel={accessibilityLabel || placeholder}
        />
        {/* Булавка в поле — «подставить, где я». Фирменным цветом: это действие, а не украшение. */}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={ADDRESS.myLocation()}
          accessibilityState={{ busy }}
          hitSlop={8}
          style={({ pressed }) => [s.pin, pressed && { opacity: 0.7 }]}
          onPress={locate}
        >
          {busy ? <ActivityIndicator size="small" color={color.primary} /> : <IconPin size={18} c={color.primary} />}
        </Pressable>
      </View>

      {offerLocate || hits.length ? (
        <View style={s.list}>
          {offerLocate ? (
            <Pressable
              accessibilityRole="button"
              onPress={locate}
              style={({ pressed }) => [s.item, s.itemLocate, pressed && { opacity: 0.85 }]}
            >
              <IconPin size={16} c={color.primary} />
              <Text style={s.itemLocateText}>{ADDRESS.myLocation()}</Text>
            </Pressable>
          ) : null}
          {hits.map((h, i) => (
            <Pressable
              key={h.label + i}
              accessibilityRole="button"
              onPress={() => pick(h)}
              style={({ pressed }) => [s.item, pressed && { opacity: 0.85 }]}
            >
              <Text style={s.itemText} numberOfLines={2}>{h.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {busy ? <Text style={s.note}>{ADDRESS.locating()}</Text> : note ? <Text style={s.note}>{note}</Text> : null}
    </View>
  );
}

const s = StyleSheet.create({
  row: { position: 'relative' },
  /** Место под булавку справа; остальное — стиль экрана. */
  input: { paddingRight: 44 },
  pin: {
    position: 'absolute', right: 4, top: 0, bottom: 0, width: 40,
    alignItems: 'center', justifyContent: 'center',
  },
  list: {
    marginTop: 6, borderRadius: rad.md, backgroundColor: color.card,
    borderWidth: StyleSheet.hairlineWidth, borderColor: color.border, overflow: 'hidden',
  },
  item: {
    paddingHorizontal: 14, paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: color.line,
  },
  itemLocate: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  itemLocateText: { ...type.bodySmall, color: color.primary, fontWeight: '600' } as any,
  itemText: { ...type.bodySmall, color: color.fg } as any,
  note: { ...type.caption, color: color.muted, marginTop: 6, paddingHorizontal: 4 } as any,
});
