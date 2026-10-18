/**
 * Чип интереса и плашка собранной затеи — одни на сборщик (app/create.tsx) и мастер (app/intent.tsx).
 *
 * Чип — ТОТ ЖЕ, что в выдаче людей (app/results.tsx `tag`): белая пилюля 36 со значком и подписью.
 * По этим темам идёт поиск, и человек должен узнать их потом на карточках людей. Новый после
 * уточнения — коралловый.
 *
 * Плашка затеи стоит над шагами мастера (тестировщики 17.10.2026: «на этом экране ещё раз показать
 * созданный интент»). После сборщика человек уходил на «Как хочешь встретиться?» и больше не видел,
 * ЧТО он создаёт, до самой сводки.
 */
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { interestLabel } from '../interest-label';
import { interestEmoji } from '../candidates';
import { color, font } from '../theme';
import { GlassSurface } from './LiquidGlass';
import { IconWand } from './icons';

export function InterestChip({ k, isNew = false }: { k: string; isNew?: boolean }) {
  const t = interestLabel(k);
  const label = t.charAt(0).toUpperCase() + t.slice(1);
  const e = interestEmoji(t) || interestEmoji(k);
  return (
    <View style={[s.tag, isNew && s.tagNew]}>
      <Text style={[s.tagText, isNew && { color: color.onPrimary }]}>{e ? `${e} ${label}` : label}</Text>
    </View>
  );
}

/** Лента чипов до кромок родителя: `inset` — его боковое поле, оно снимается с обеих сторон. */
export function InterestChipRow({ topics, added = [], inset = 16 }: { topics: string[]; added?: string[]; inset?: number }) {
  if (!topics.length) return null;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -inset, flexGrow: 0 }}
                contentContainerStyle={{ gap: 4, paddingHorizontal: inset }} keyboardShouldPersistTaps="handled">
      {topics.map((x) => <InterestChip key={x} k={x} isNew={added.includes(x)} />)}
    </ScrollView>
  );
}

/** Плашка «что создаём» над шагом мастера: значок, название, лента чипов. Не нажимается. */
export function IntentPlate({ title, topics }: { title: string; topics: string[] }) {
  if (!title && !topics.length) return null;
  return (
    <GlassSurface tone="light" radius={20} style={s.plate}>
      {title ? (
        <View style={s.head}>
          <IconWand size={16} c={color.primary} />
          <Text style={s.title} numberOfLines={1}>{title}</Text>
        </View>
      ) : null}
      <InterestChipRow topics={topics} />
    </GlassSurface>
  );
}

const s = StyleSheet.create({
  /** Чип выдачи (results.tsx `tag`): белое 86% с лёгкой тенью — на белом стекле его держит тень. */
  tag: {
    height: 36, paddingHorizontal: 14, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.86)',
    justifyContent: 'center', marginVertical: 4,
    shadowColor: '#5A4A3A', shadowOpacity: 0.1, shadowRadius: 6, shadowOffset: { width: 0, height: 2 },
  },
  tagNew: { backgroundColor: color.primary },
  tagText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.fg } as any,
  plate: { paddingTop: 10, paddingBottom: 6, paddingHorizontal: 16, gap: 4 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 24 },
  title: { flex: 1, fontFamily: font.textSemibold, fontSize: 15, lineHeight: 22, color: color.fg } as any,
});
