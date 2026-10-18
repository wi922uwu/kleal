/**
 * Изменить план — лист борда «GR · Offline — new layout» (GR.26b «Change the plan», GR.27b «Edit the
 * change», GR.32b «Edit the update») и его второй шаг — место (GR.26c / GR.32c «Change the place»).
 *
 * ЛИСТ, А НЕ СТРАНИЦА-ФОРМА. Раньше изменение открывалось формой вместо страницы плана: пропадали
 * состав и раунды, а менял человек одно-два поля. На борде это шторка над той же страницей: сверху
 * «Instead of Thu 23 July, 19:00» — что именно меняешь, ниже четыре дня и четыре времени рядом с
 * нынешними, «or set your time» — своё время полями, потом место и три кнопки.
 *
 * Чипы — рядом с нынешним, а не с сегодняшним: меняют обычно «на день позже» или «на полчаса
 * раньше», и такие варианты должны быть под пальцем, а не в прокрутке.
 */
import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { T, useLang, dateLocale } from '../i18n';
import { color, font, labelFamily } from '../theme';
import { planWhenLabel } from '../intent';
import { Sheet } from './Sheet';
import { GlassPill } from './Glass';
import { AddressField } from './AddressField';
import { IconCheck, IconPin, IconRefresh, IconVideo } from './icons';
import type { WhenValue } from './WhenPicker';

const pad = (n: number) => String(n).padStart(2, '0');
/** Ключ дня по местным частям даты — как у чипов мастера (см. dayKey в src/intent.ts). */
const dayKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const hhmm = (m: number) => `${pad(Math.floor(m / 60) % 24)}:${pad(m % 60)}`;

/** Четыре дня, начиная с дня нынешнего плана (не раньше сегодня). */
function nearDays(fromKey: string): { key: string; label: string }[] {
  const today = new Date(); today.setHours(12, 0, 0, 0);
  let start = fromKey ? new Date(fromKey + 'T12:00:00') : today;
  if (isNaN(start.getTime()) || start < today) start = today;
  const loc = dateLocale();
  return Array.from({ length: 4 }, (_, i) => {
    const d = new Date(start); d.setDate(d.getDate() + i);
    return { key: dayKey(d), label: d.toLocaleDateString(loc, { weekday: 'short', day: 'numeric' }) };
  });
}

/** Четыре времени вокруг нынешнего: само, +30, +60, +90 минут (как 19:00 · 19:30 · 20:00 · 20:30). */
function nearTimes(m: number): number[] {
  const base = Math.floor(m / 30) * 30;
  return [0, 30, 60, 90].map((d) => (base + d) % (24 * 60));
}

export function PlanChangeSheet({
  visible, title, sendLabel, was, value, onChange, place, onPlace, placeNote, busy, error, onSend, onClose,
  online = false, link = '', currentLink = '', onLink, linkWhose = '', linkCurrentTitle = '', linkNote = '',
}: {
  visible: boolean;
  /** «Change the plan» / «Edit the change» / «Edit the update». */
  title: string;
  /** «Send the change» / «Send the update». */
  sendLabel: string;
  /** Что меняют: «Thu 23 July, 19:00» — строка «Instead of …». */
  was: string;
  value: WhenValue;
  onChange: (v: WhenValue) => void;
  place: string;
  onPlace: (p: string) => void;
  /** Подпись под списком мест (GR.26c / GR.32c) — кто и когда увидит новое место. */
  placeNote: string;
  busy?: boolean;
  error?: string;
  onSend: () => void;
  onClose: () => void;
  /** Онлайн-план (борд «GR · Online», GRO.26b/26c, 32b/32c): вместо места — ссылка на звонок. */
  online?: boolean;
  link?: string;
  /** Ссылка, что стоит в плане сейчас. */
  currentLink?: string;
  onLink?: (l: string) => void;
  /** «Video call · your link» / «Video call · Mateo’s link». */
  linkWhose?: string;
  /** «Your Zoom link» / «Mateo’s Zoom link» — строка нынешней ссылки во втором шаге. */
  linkCurrentTitle?: string;
  /** Кто и когда получит ссылку (GRO.26c / GRO.32c). */
  linkNote?: string;
}) {
  const lang = useLang();
  const [step, setStep] = useState<'when' | 'place' | 'link'>('when');
  const [draft, setDraft] = useState(place);
  const [ldraft, setLdraft] = useState(link || currentLink);
  const [hh, setHh] = useState(pad(Math.floor(value.minutes / 60)));
  const [mm, setMm] = useState(pad(value.minutes % 60));
  useEffect(() => { if (visible) { setStep('when'); setDraft(place); setLdraft(link || currentLink); } }, [visible]);
  useEffect(() => { setHh(pad(Math.floor(value.minutes / 60))); setMm(pad(value.minutes % 60)); }, [value.minutes]);

  const days = useMemo(() => nearDays(value.date), [visible]);
  const times = useMemo(() => nearTimes(value.minutes), [visible]);
  const setTime = (h: string, m: string) => {
    const H = Math.min(23, Math.max(0, parseInt(h || '0', 10) || 0));
    const M = Math.min(59, Math.max(0, parseInt(m || '0', 10) || 0));
    onChange({ ...value, minutes: H * 60 + M });
  };

  if (step === 'link') {
    const cur = !ldraft.trim() || ldraft.trim() === currentLink;
    return (
      <Sheet visible={visible} onClose={() => setStep('when')} title={T('Сменить ссылку', 'Change the link', 'Cambiar el enlace')}>
        <TextInput
          style={s.search} value={cur ? '' : ldraft} onChangeText={setLdraft}
          placeholder={T('Вставь ссылку Zoom, Meet или любую другую', 'Paste a Zoom, Meet or any link', 'Pega un enlace de Zoom, Meet o cualquiera')}
          placeholderTextColor="#A6ADBB" autoCapitalize="none" autoCorrect={false} keyboardType="url"
        />
        {currentLink ? (
          <View style={s.block}>
            <Text style={[s.lead, { fontFamily: labelFamily(lang) }]}>{T('Нынешняя ссылка', 'Current link', 'Enlace actual')}</Text>
            <Pressable accessibilityRole="radio" accessibilityState={{ selected: cur }}
                       onPress={() => setLdraft(currentLink)} style={[s.row, cur && s.rowOn]}>
              <IconVideo size={20} c={color.primary} />
              <View style={{ flex: 1 }}>
                <Text style={s.rowTitle} numberOfLines={1}>{linkCurrentTitle}</Text>
                <Text style={s.rowSub}>{T('Сейчас · откроется за 10 минут до звонка', 'Current · opens 10 minutes before the call', 'Actual · se abre 10 minutos antes de la llamada')}</Text>
              </View>
              {cur ? <IconCheck /> : null}
            </Pressable>
          </View>
        ) : null}
        <Text style={s.note}>{linkNote}</Text>
        <GlassPill tone="brand" label={T('Выбрать эту ссылку', 'Use this link', 'Usar este enlace')} style={s.btn}
                   disabled={!ldraft.trim()} onPress={() => { onLink?.(cur ? '' : ldraft.trim()); setStep('when'); }} />
        <GlassPill tone="dark" label={T('Назад', 'Back', 'Atrás')} style={s.btn} onPress={() => setStep('when')} />
      </Sheet>
    );
  }

  if (step === 'place') {
    return (
      <Sheet visible={visible} onClose={() => setStep('when')} title={T('Сменить место', 'Change the place', 'Cambiar el lugar')}>
        <AddressField
          value={draft}
          onChange={setDraft}
          onPick={(h) => setDraft(h.label)}
          placeholder={T('Найти место', 'Search for a spot', 'Buscar un sitio')}
          style={s.search}
        />
        {place ? (
          <Pressable accessibilityRole="radio" accessibilityState={{ selected: draft === place }}
                     onPress={() => setDraft(place)} style={[s.row, draft === place && s.rowOn]}>
            <View style={{ flex: 1 }}>
              <Text style={s.rowTitle} numberOfLines={1}>{place}</Text>
              <Text style={s.rowSub}>{T('Сейчас', 'Current', 'Actual')}</Text>
            </View>
            {draft === place ? <IconCheck /> : null}
          </Pressable>
        ) : null}
        <Text style={s.note}>{placeNote}</Text>
        <GlassPill tone="brand" label={T('Выбрать это место', 'Use this place', 'Usar este lugar')} style={s.btn}
                   disabled={!draft.trim()} onPress={() => { onPlace(draft.trim()); setStep('when'); }} />
        <GlassPill tone="dark" label={T('Назад', 'Back', 'Atrás')} style={s.btn} onPress={() => setStep('when')} />
      </Sheet>
    );
  }

  return (
    <Sheet visible={visible} onClose={onClose} title={title}>
      <View style={s.body}>
        {was ? (
          <View style={s.wasRow}>
            <IconRefresh size={16} c={color.primary} />
            <Text style={[s.lead, { fontFamily: labelFamily(lang) }]} numberOfLines={1}>
              {T(`Вместо ${was}`, `Instead of ${was}`, `En lugar de ${was}`)}
            </Text>
          </View>
        ) : null}

        <View style={s.block}>
          <Text style={[s.lead, { fontFamily: labelFamily(lang) }]}>{T('Дата', 'Date', 'Fecha')}</Text>
          <View style={s.chips}>
            {days.map((d) => {
              const on = value.date === d.key;
              return (
                <Pressable key={d.key} accessibilityRole="button" accessibilityState={{ selected: on }}
                           onPress={() => onChange({ ...value, date: d.key })} style={[s.chip, on && s.chipOn]}>
                  <Text style={[s.chipText, on && s.chipTextOn]} numberOfLines={1}>{d.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={s.block}>
          <Text style={[s.lead, { fontFamily: labelFamily(lang) }]}>{T('Время', 'Time', 'Hora')}</Text>
          <View style={s.chips}>
            {times.map((m) => {
              const on = value.minutes === m;
              return (
                <Pressable key={m} accessibilityRole="button" accessibilityState={{ selected: on }}
                           onPress={() => onChange({ ...value, minutes: m })} style={[s.chip, on && s.chipOn]}>
                  <Text style={[s.chipText, on && s.chipTextOn]}>{hhmm(m)}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={[s.block, { alignItems: 'center' }]}>
          <Text style={s.own}>{T('или своё время', 'or set your time', 'o elige tu hora')}</Text>
          <View style={s.timeRow}>
            <TextInput style={s.timeBox} value={hh} keyboardType="number-pad" maxLength={2} selectTextOnFocus
                       accessibilityLabel={T('часы', 'hours', 'horas')}
                       onChangeText={(t) => { const v = t.replace(/\D/g, ''); setHh(v); if (v.length === 2) setTime(v, mm); }}
                       onBlur={() => setTime(hh, mm)} />
            <View style={s.colon}><View style={s.dot} /><View style={s.dot} /></View>
            <TextInput style={s.timeBox} value={mm} keyboardType="number-pad" maxLength={2} selectTextOnFocus
                       accessibilityLabel={T('минуты', 'minutes', 'minutos')}
                       onChangeText={(t) => { const v = t.replace(/\D/g, ''); setMm(v); if (v.length === 2) setTime(hh, v); }}
                       onBlur={() => setTime(hh, mm)} />
          </View>
        </View>

        {!online ? (
          <View style={s.block}>
            <Text style={[s.lead, { fontFamily: labelFamily(lang) }]}>{T('Место', 'Place', 'Lugar')}</Text>
            <View style={s.placeRow}>
              <IconPin size={18} c={color.primary} />
              <Text style={s.placeText} numberOfLines={1}>{place || T('Место не указано', 'No place yet', 'Sin lugar')}</Text>
            </View>
          </View>
        ) : (
          /* GRO.26b: «Link · Video call · your link». */
          <View style={s.block}>
            <Text style={[s.lead, { fontFamily: labelFamily(lang) }]}>{T('Ссылка', 'Link', 'Enlace')}</Text>
            <View style={s.placeRow}>
              <IconVideo size={18} c={color.primary} />
              <Text style={s.placeText} numberOfLines={1}>
                {link && link !== currentLink ? link : (linkWhose || T('Звонок', 'Video call', 'Videollamada'))}
              </Text>
            </View>
          </View>
        )}

        {error ? <Text style={s.err}>{error}</Text> : null}
      </View>

      <GlassPill tone="brand" label={sendLabel} busy={busy} style={s.btn} onPress={onSend} />
      {!online ? (
        <GlassPill label={T('Сменить место', 'Change place', 'Cambiar lugar')} style={s.btn} onPress={() => setStep('place')} />
      ) : onLink ? (
        <GlassPill label={T('Сменить ссылку', 'Change link', 'Cambiar enlace')} style={s.btn} onPress={() => setStep('link')} />
      ) : null}
      <GlassPill tone="dark" label={T('Отмена', 'Cancel', 'Cancelar')} style={s.btn} onPress={onClose} />
    </Sheet>
  );
}

/** Строка «Instead of …» — подпись плана как её видят люди. */
export const planWas = (dateKey: string, minutes: number) => planWhenLabel(dateKey, minutes);

const INK = '#181B22';

const s = StyleSheet.create({
  body: { gap: 20, marginBottom: 16 },
  wasRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  block: { gap: 12 },
  lead: { fontSize: 15, lineHeight: 20, color: INK } as any,
  chips: { flexDirection: 'row', gap: 8 },
  /** Чип 36 со стеклянной кромкой; выбранный — коралл (Chip/Chip борда). */
  chip: {
    flex: 1, height: 36, borderRadius: 999, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8,
    backgroundColor: 'rgba(255,255,255,0.42)', borderWidth: 0.5, borderColor: 'rgba(255,255,255,0.9)',
  },
  chipOn: { backgroundColor: '#FF385C' },
  chipText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: INK } as any,
  chipTextOn: { color: '#FFFFFF' },
  own: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: INK } as any,
  timeRow: { flexDirection: 'row', alignItems: 'center' },
  timeBox: {
    width: 74, height: 44, borderRadius: 999, textAlign: 'center', backgroundColor: 'rgba(255,255,255,0.56)',
    fontFamily: font.num, fontSize: 22, color: '#404652',
  },
  colon: { width: 24, height: 12, alignItems: 'center', justifyContent: 'space-between' },
  dot: { width: 3, height: 3, borderRadius: 2, backgroundColor: INK },
  placeRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  placeText: { flex: 1, fontFamily: font.text, fontSize: 15, lineHeight: 20, color: INK } as any,
  err: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#D92D2D' } as any,
  btn: { height: 48 },
  search: {
    height: 48, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.56)', paddingHorizontal: 16,
    fontFamily: font.text, fontSize: 15, color: INK,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.16)' },
  rowOn: { backgroundColor: 'rgba(255,255,255,0.36)' },
  rowTitle: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: INK } as any,
  rowSub: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: '#5A616E' } as any,
  note: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: INK, marginTop: 8, marginBottom: 8 } as any,
});
