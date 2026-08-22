/**
 * Выбор даты и времени — кадр GR.09 «Create · 1 of 3 · when» и он же в мастере интента.
 *
 * ЧТО НА КАДРЕ, дословно: строка «Date» и горизонтальные чипы дат («Wed Jul 22», «Thu Jul 23»,
 * «Fri Jul 24», «Sat Jul 25»); строка «Time», крупное «20:00», под ним два числовых поля — часы
 * и минуты; строка «Time Zone» со значением «Barcelona, Spain (GMT+2)».
 *
 * ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ. Ровно это уже было построено внутри app/intent.tsx, а экран группового
 * плана просил время ОДНИМ ТЕКСТОВЫМ ПОЛЕМ — «например: чт 24 июля, 20:30». Человек писал дату
 * словами, и это давало две беды сразу:
 *
 *  1. вид не тот, что на борде, и не тот, что в соседнем экране того же приложения;
 *  2. и, что хуже, у плана не было НАСТОЯЩЕГО времени — только подпись. Сервер считает
 *     двухчасовой замок и отказ TOO_LATE по `starts_at`, а он не отправлялся вовсе: групповой
 *     план нельзя было ни заморозить перед встречей, ни отклонить как назначенный на прошлое.
 *
 * Компонент отдаёт наружу и подпись, и момент времени — чтобы второе больше нельзя было забыть.
 * Копию делать нельзя: этот проект уже терял день на разъехавшиеся копии подготовки фото и на
 * два разных представления `languages`. См. kleal-app/AGENTS.md.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ScrollView } from 'react-native';
import { TimeDial } from './Dials';
import { DETAILS, dateChips, planWhenLabel, tzDisplay } from '../intent';
import { IconCalendar, IconClock, IconGlobe } from './icons';
import { color, radius as rad, space, type } from '../theme';

export type WhenValue = {
  /** Локальный ключ даты «2026-08-24». Локальный, а не UTC: см. комментарий у dateChips. */
  date: string;
  /** Минуты от полуночи, 0..1439. */
  minutes: number;
  /** IANA-имя пояса. */
  tz: string;
};

/**
 * Момент начала в unix-секундах — то, по чему сервер считает замок и «уже поздно».
 *
 * Считается от ЛОКАЛЬНЫХ частей даты, а не через Date.parse строки с поясом: пояс из `tz` — это
 * то, что человек выбрал показывать, а сама встреча назначается по часам его устройства. Ошибка
 * здесь стоит дорого и незаметна: план уезжает на сутки или на несколько часов, и виден это
 * только на чужом экране.
 */
export function whenStartsAt(v: WhenValue): number {
  const [y, m, d] = String(v.date || '').split('-').map((x) => parseInt(x, 10));
  if (!y || !m || !d) return 0;
  const dt = new Date(y, m - 1, d, Math.floor(v.minutes / 60), v.minutes % 60, 0, 0);
  return Math.floor(dt.getTime() / 1000);
}

/**
 * Обратно из момента в выбор — чтобы форма правки открывалась НА НЫНЕШНЕМ времени плана, а не на
 * умолчании. Иначе «предложить другое» начинается с чужого вечера, и человек меняет то, что менять
 * не собирался.
 *
 * Плану, заведённому до появления `starts_at`, вернём умолчание: восстановить момент из подписи
 * «чт 24 июля · 20:30» нельзя — в ней нет года, а угадывать его значит промахнуться на год.
 */
export function whenFromStartsAt(starts_at?: number, fallbackTz?: string): WhenValue | null {
  const t = Number(starts_at || 0);
  if (!t) return null;
  const d = new Date(t * 1000);
  return {
    date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`,
    minutes: d.getHours() * 60 + d.getMinutes(),
    tz: fallbackTz || 'UTC',
  };
}

/**
 * Подпись для карточки плана: «чт, 24 июля · 20:30». Её видят люди, её же хранит сервер в `when`.
 *
 * Обёртка над `planWhenLabel` из src/intent.ts, а не своя реализация — намеренно. Своя тут уже
 * была, и она брала локаль УСТРОЙСТВА: чипы дат рисовались «Ср, 12 авг.», а строка в карточке над
 * ними — «Wed, 12 Aug», в одном экране и про один день. Язык интерфейса в этом проекте свой
 * (`getLang()`), и системный ему не указ.
 */
export function whenLabel(v: WhenValue): string {
  return planWhenLabel(v.date, v.minutes);
}

export function WhenPicker({
  value, onChange, onDragChange, onPressTz, days = 8,
}: {
  value: WhenValue;
  onChange: (v: WhenValue) => void;
  /** Пока крутят циферблат — родитель может отключить прокрутку, иначе жест уезжает списку. */
  onDragChange?: (dragging: boolean) => void;
  /** Не передан — строка пояса не показывается: менять его есть где не на каждом экране. */
  onPressTz?: () => void;
  days?: number;
}) {
  const set = (patch: Partial<WhenValue>) => onChange({ ...value, ...patch });

  return (
    <View style={s.wrap}>
      <View style={s.labelRow}>
        <IconCalendar size={18} c={color.fg} />
        <Text style={s.label}>{DETAILS.date()}</Text>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
        {dateChips(days).map((d) => {
          const on = value.date === d.key;
          return (
            <Pressable
              key={d.key}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              onPress={() => set({ date: d.key })}
              style={({ pressed }) => [s.chip, on && s.chipOn, pressed && { opacity: 0.85 }]}
            >
              <Text style={[s.chipText, on && { color: color.onPrimary }]}>{d.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <View style={s.labelRow}>
        <IconClock size={18} c={color.fg} />
        <Text style={s.label}>{DETAILS.time()}</Text>
      </View>
      <TimeDial
        minutes={value.minutes}
        onChange={(m) => set({ minutes: m })}
        onDragChange={onDragChange}
      />
      <View style={s.boxRow}>
        <NumBox
          value={String(Math.floor(value.minutes / 60)).padStart(2, '0')}
          onChange={(t) => {
            const h = Math.max(0, Math.min(23, parseInt(t || '0', 10) || 0));
            set({ minutes: h * 60 + (value.minutes % 60) });
          }}
        />
        <Text style={s.boxColon}>:</Text>
        <NumBox
          value={String(value.minutes % 60).padStart(2, '0')}
          onChange={(t) => {
            const m = Math.max(0, Math.min(59, parseInt(t || '0', 10) || 0));
            set({ minutes: Math.floor(value.minutes / 60) * 60 + m });
          }}
        />
      </View>

      {onPressTz ? (
        <Pressable accessibilityRole="button" style={s.tzRow} onPress={onPressTz}>
          <IconGlobe />
          <View style={{ flex: 1 }}>
            <Text style={s.tzLabel}>{DETAILS.timeZone()}</Text>
            <Text style={s.tzValue}>{tzDisplay(value.tz)}</Text>
          </View>
          <Text style={s.chev}>⌄</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

/** Маленькое числовое поле под циферблатом — «20 : 00» с кадра. */
function NumBox({ value, onChange }: { value: string; onChange: (t: string) => void }) {
  return (
    <TextInput
      style={s.numBox}
      value={value}
      onChangeText={onChange}
      keyboardType="number-pad"
      maxLength={2}
      selectTextOnFocus
      accessibilityLabel={value}
    />
  );
}

// ============================================================ вид
// Значения перенесены из app/intent.tsx один в один: это тот же кадр, и расходиться им нельзя.

const s = StyleSheet.create({
  wrap: { gap: space.md },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  chipRow: { gap: space.sm, paddingVertical: 2 },
  chip: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  boxRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  numBox: {
    width: 56, height: 40, borderRadius: rad.md, backgroundColor: color.neutral100,
    textAlign: 'center', color: color.fg, fontSize: 16, fontWeight: '600',
  },
  boxColon: { fontSize: 18, color: color.muted },
  tzRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6 },
  tzLabel: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  tzValue: { ...type.bodySmall, color: color.muted } as any,
  chev: { fontSize: 16, color: color.muted },
});
