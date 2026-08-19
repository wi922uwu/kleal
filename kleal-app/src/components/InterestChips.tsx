/**
 * ВЫБОР ИНТЕРЕСОВ ЧИПАМИ.
 *
 * Заменяет колесо (src/components/CipherWheel.tsx) на обоих экранах сразу: онбординг рисует этот
 * виджет, а профиль по кнопке «Добавить» уходит в тот же шаг онбординга — то есть места два, а
 * правка одна.
 *
 * ДЕРЕВО, А НЕ ОБЛАКО. Ключей 312, и высыпать их разом нельзя: человек не читает облако из
 * трёхсот слов, он его пролистывает мимо. Поэтому чипы показывают ОДИН уровень за раз —
 * восемь категорий, внутри каждой семьи, внутри семей занятия. Уровень меняется по нажатию,
 * и глубина видна по строке пути над чипами.
 *
 * ВЗЯТЬ УРОВЕНЬ ЦЕЛИКОМ. У колеса это называлось «остановиться можно на любом уровне», и это
 * нужное свойство: человеку, который просто «занимается спортом», незачем выбирать между паделом
 * и сквошем. Поэтому внутри категории первым стоит чип «Всё: Спорт» — явный, а не угаданный из
 * долгого нажатия.
 *
 * В НАБОР УХОДИТ ВСЯ ЦЕПОЧКА. «Спорт → Ракетки → Падел» кладёт три ключа, а не один. Матчинг
 * сравнивает интересы БУКВАЛЬНО, и без родителей человека не найдёт тот, кто искал шире — он
 * искал «спорт», а у нас записан только «падел». Это правило пришло из колеса и осталось
 * единственным, что здесь по-настоящему важно не сломать.
 */
import React, { useState } from 'react';
import { View, Text, Pressable, ScrollView, StyleSheet } from 'react-native';
import { WHEEL_TREE, WheelNode, nodeLabel, CHIPS_COPY } from '../interests-wheel';
import { categoryIcon } from './category-icons';
import { color, radius as rad, space, type } from '../theme';

/** Ключи от корня до узла — то, что уйдёт в набор. */
const chainOf = (path: WheelNode[], node: WheelNode) => [...path, node].map((n) => n.key);

export function InterestChips({
  selected, onAdd, onRemove,
}: {
  selected: string[];
  onAdd: (keys: string[]) => void;
  onRemove?: (key: string) => void;
}) {
  /** Путь от корня до текущего уровня. Пустой — показываем категории. */
  const [path, setPath] = useState<WheelNode[]>([]);
  const level = path.length ? (path[path.length - 1].kids || []) : WHEEL_TREE;
  const here = path[path.length - 1];
  const has = (k: string) => selected.includes(k);

  return (
    <View style={s.wrap}>
      <Text style={s.hint}>{CHIPS_COPY.hint()}</Text>

      {/* Путь виден строкой, а не только по памяти: иначе на третьем уровне непонятно, где ты. */}
      {path.length ? (
        <View style={s.row}>
          <Pressable accessibilityRole="button" style={[s.chip, s.chipBack]}
                     onPress={() => setPath((p) => p.slice(0, -1))}>
            <Text style={s.chipBackText}>‹ {CHIPS_COPY.back()}</Text>
          </Pressable>
          {/* Взять уровень целиком — явным чипом. */}
          <Pressable accessibilityRole="button"
                     style={[s.chip, has(here.key) && s.chipOn]}
                     onPress={() => onAdd(chainOf(path.slice(0, -1), here))}>
            <Text style={[s.chipText, has(here.key) && s.chipTextOn]}>
              {CHIPS_COPY.whole(nodeLabel(here))}
            </Text>
          </Pressable>
        </View>
      ) : null}

      <ScrollView style={s.list} contentContainerStyle={s.row} keyboardShouldPersistTaps="handled">
        {level.map((n) => {
          const leaf = !n.kids || !n.kids.length;
          const on = has(n.key);
          return (
            <Pressable
              key={n.key}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              style={[s.chip, on && s.chipOn]}
              onPress={() => {
                // Лист — выбор. Ветка — вход внутрь: взять её целиком можно чипом «Всё: …».
                if (leaf) {
                  if (on) onRemove?.(n.key); else onAdd(chainOf(path, n));
                } else {
                  setPath((p) => [...p, n]);
                }
              }}
            >
              {/* Иконка только у категорий: глубже она была бы украшением, а не подсказкой. */}
              {n.icon ? categoryIcon(n.icon, on ? color.onPrimary : color.muted) : null}
              <Text style={[s.chipText, on && s.chipTextOn]}>{nodeLabel(n)}</Text>
              {leaf ? null : <Text style={[s.more, on && s.chipTextOn]}>›</Text>}
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { gap: space.sm },
  hint: { ...type.bodySmall, color: color.muted } as any,
  // Высота ограничена: список живёт в ленте разговора, и без предела длинная категория
  // выталкивала бы композер за экран.
  list: { maxHeight: 260 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 14, paddingVertical: 9,
    borderRadius: rad.full, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card,
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.body, color: color.fg } as any,
  chipTextOn: { color: color.onPrimary },
  chipBack: { backgroundColor: color.neutral100, borderColor: color.neutral100 },
  chipBackText: { ...type.body, color: color.muted } as any,
  more: { ...type.body, color: color.neutral400 } as any,
});
