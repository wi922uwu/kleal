/**
 * Ответ на сцену опросника «помоги разобраться» — три вида в одном компоненте.
 *
 * ПОЧЕМУ НЕ КОЛОДА СО СВАЙПАМИ. Свайп — названный враг продукта («социальное трение: свайпы,
 * холодные сообщения, мёртвые чаты»), и жест «отбросить вариант вбок» здесь означал бы ровно то,
 * от чего Kleal уходит. Все три вида — тапы.
 *
 * ПОЧЕМУ ТРИ, А НЕ ОДИН. Четыре одинаковых вопроса подряд читаются анкетой, а человек пришёл сюда
 * именно потому, что анкета ему не помогла. Вид выбирает агент под сцену:
 *
 *   cards  три продолжения сцены, тап по одному     — рабочая лошадь
 *   pair   два варианта лоб в лоб                   — быстрее, читается как игра
 *   multi  пять-шесть строк, «отметь всё, что узнаёшь» — один ход, много сигнала
 *
 * `multi` — единственный с кнопкой подтверждения: пока человек отмечает, отправлять нечего.
 * Остальные отвечают самим тапом, потому что выбор там единственный и подтверждать его нечем.
 */
import React, { useState } from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import type { Scene, SceneOption } from '../scene';
import { GlassPill } from './Glass';
import { SCENE as C } from '../onboarding';
import { color, radius as rad, space, type } from '../theme';

export function SceneWidget({ scene, onAnswer, busy }: {
  scene: Scene;
  onAnswer: (picked: SceneOption[]) => void;
  busy?: boolean;
}) {
  const [marked, setMarked] = useState<string[]>([]);
  const multi = scene.widget === 'multi';

  const tap = (o: SceneOption) => {
    if (busy) return;
    if (!multi) return onAnswer([o]);
    setMarked((p) => (p.includes(o.id) ? p.filter((x) => x !== o.id) : [...p, o.id]));
  };

  // `pair` кладёт варианты в строку — два коротких помещаются рядом, и противопоставление
  // читается глазом. Остальные идут столбиком: продолжения сцены сравнивают по очереди.
  const row = scene.widget === 'pair';

  return (
    <View style={s.wrap}>
      <View style={[s.list, row && s.rowList]}>
        {scene.options.map((o) => {
          const on = marked.includes(o.id);
          return (
            <Pressable
              key={o.id}
              accessibilityRole="button"
              accessibilityState={{ selected: on, disabled: !!busy }}
              disabled={busy}
              onPress={() => tap(o)}
              style={({ pressed }) => [
                s.card,
                row && s.rowCard,
                on && s.cardOn,
                pressed && !busy && { opacity: 0.86 },
                busy && { opacity: 0.5 },
              ]}
            >
              <Text style={[s.cardText, on && s.cardTextOn]}>{o.label}</Text>
            </Pressable>
          );
        })}
      </View>
      {multi ? (
        <GlassPill
          label={marked.length ? C.multiCta(marked.length) : C.multiEmpty()}
          disabled={!marked.length || !!busy}
          tone="brand"
          style={s.cta}
          onPress={() => onAnswer(scene.options.filter((o) => marked.includes(o.id)))}
        />
      ) : null}
    </View>
  );
}

/**
 * Подборка в конце: интерес, строка «почему» и отметка. Ничего не пишется, пока человек не нажмёт
 * «Добавить» — агент предложил, решает человек. То же правило, что во всём продукте.
 */
export function SuggestPicker({ items, onAdd, busy }: {
  items: { key: string; label: string; why: string }[];
  onAdd: (keys: string[]) => void;
  busy?: boolean;
}) {
  const [marked, setMarked] = useState<string[]>(() => items.map((i) => i.key));

  return (
    <View style={s.wrap}>
      <View style={s.list}>
        {items.map((it) => {
          const on = marked.includes(it.key);
          return (
            <Pressable
              key={it.key}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              disabled={busy}
              onPress={() => setMarked((p) => (on ? p.filter((x) => x !== it.key) : [...p, it.key]))}
              style={({ pressed }) => [s.sug, on && s.cardOn, pressed && !busy && { opacity: 0.86 }]}
            >
              <Text style={[s.sugTitle, on && s.cardTextOn]}>{it.label}</Text>
              <Text style={[s.sugWhy, on && s.sugWhyOn]}>{it.why}</Text>
            </Pressable>
          );
        })}
      </View>
      <GlassPill
        label={marked.length ? C.addCta(marked.length) : C.addEmpty()}
        disabled={!marked.length || !!busy}
        tone="brand"
        style={s.cta}
        onPress={() => onAdd(marked)}
      />
      {/* Выход из подборки. Пустой набор экран читает как «дай ещё круг» — но ровно один:
          бесконечно подбирать нельзя, это правило продукта. */}
      <Pressable accessibilityRole="button" disabled={busy} onPress={() => onAdd([])} style={s.none}>
        <Text style={s.noneText}>{C.none()}</Text>
      </Pressable>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { width: '100%', gap: space.sm },
  list: { gap: space.xs },
  rowList: { flexDirection: 'row', gap: space.xs },
  card: {
    minHeight: 52, justifyContent: 'center', paddingHorizontal: space.md, paddingVertical: space.sm,
    borderRadius: rad.lg, borderWidth: 1, borderColor: color.border, backgroundColor: color.card,
  },
  rowCard: { flex: 1, alignItems: 'center' },
  cardOn: { backgroundColor: color.primary, borderColor: color.primary },
  cardText: { ...type.body, color: color.fg } as any,
  cardTextOn: { color: color.onPrimary },
  sug: {
    gap: 2, paddingHorizontal: space.md, paddingVertical: space.sm,
    borderRadius: rad.lg, borderWidth: 1, borderColor: color.border, backgroundColor: color.card,
  },
  sugTitle: { ...type.button, color: color.fg } as any,
  sugWhy: { ...type.caption, color: color.muted } as any,
  sugWhyOn: { color: color.onPrimary, opacity: 0.9 },
  cta: { marginTop: space.xs },
  none: { alignItems: 'center', paddingVertical: space.sm },
  noneText: { ...type.caption, color: color.muted } as any,
});
