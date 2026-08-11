/**
 * Стопка карточек — компонент борда «Invite Stack» (GR.01).
 *
 * ЗАЧЕМ СТОПКА, А НЕ СПИСОК. Продукт обещает 2–4 объяснённых варианта, а не бесконечную ленту
 * людей: список из восьми карточек подряд — это ровно та лента, от которой Kleal отказывается.
 * Стопка показывает ОДНОГО человека и говорит, сколько ещё за ним.
 *
 * Это НЕ свайп-колода. Свайпы — названный враг продукта («социальное трение: свайпы, холодные
 * сообщения, мёртвые чаты»), и жест «отбросить человека вбок» здесь означал бы ровно то, чего
 * продукт избегает. Верхняя карточка живёт, пока по ней не приняли решение; «дальше» — тихая
 * кнопка, а не бросок.
 *
 * Геометрия с борда, не на глаз (Invite Stack 350×131 при карточке 350×110):
 *   Layer · 3rd   322×100   — на 28 уже и на 10 ниже
 *   Layer · 2nd   340×106   — на 10 уже и на 4 ниже
 *   Home Card     350×110   — верхняя, полная
 * Отсюда PEEK: сумма выступающих краёв = 131 − 110 = 21, по 10–11 на слой.
 */
import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Pressable, Animated, Easing } from 'react-native';
import { T } from '../i18n';
import { color, radius as rad, space, type } from '../theme';

/** Насколько каждый следующий слой уже и ниже. С борда: 350→340→322 и 110→106→100. */
const INSET = [0, 5, 14];     // по горизонтали, с каждой стороны
const DROP = [0, 11, 21];     // насколько слой выглядывает снизу
const LAYERS = 3;             // верхняя + два края: борд рисует ровно столько

export function CardStack<T_ extends { key: string }>({
  items,
  index,
  onNext,
  render,
  emptyHint,
}: {
  items: T_[];
  /** Какая карточка сверху. Хранится СНАРУЖИ: экран знает, по кому уже приняли решение. */
  index: number;
  onNext: () => void;
  render: (item: T_) => React.ReactNode;
  /** Что сказать, когда стопка кончилась. Пусто — не рисовать ничего. */
  emptyHint?: string;
}) {
  const left = items.length - index;

  /**
   * Смена карточки — короткое проявление, а не подмена без предупреждения. Пружины нет
   * намеренно: карточка не «прилетает», она проступает на месте предыдущей, и взгляд остаётся
   * там же, где был.
   */
  const fade = useRef(new Animated.Value(1)).current;
  const rise = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    fade.setValue(0);
    rise.setValue(6);
    Animated.parallel([
      Animated.timing(fade, { toValue: 1, duration: 180, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      Animated.timing(rise, { toValue: 0, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
    ]).start();
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!items.length || index >= items.length) {
    return emptyHint ? <Text style={s.empty}>{emptyHint}</Text> : null;
  }

  const top = items[index];
  /** Сколько слоёв-краёв рисовать: только столько, сколько карточек реально осталось за верхней. */
  const behind = Math.min(LAYERS - 1, Math.max(0, left - 1));

  return (
    <View style={s.wrap}>
      <View style={s.stack}>
        {/*
          Края карточек снизу — не картинка «для красоты», а счётчик: видно, что за этой есть ещё.
          Рисуются ПЕРВЫМИ, чтобы верхняя легла поверх без возни с zIndex.
        */}
        {Array.from({ length: behind }, (_, i) => {
          const n = i + 1;                        // 1 — ближний край, 2 — дальний
          return (
            <View
              key={n}
              pointerEvents="none"
              style={[
                s.layer,
                {
                  left: INSET[n],
                  right: INSET[n],
                  bottom: -DROP[n],
                  opacity: 1 - n * 0.28,
                },
              ]}
            />
          );
        })}

        <Animated.View style={{ opacity: fade, transform: [{ translateY: rise }] }}>
          {render(top)}
        </Animated.View>
      </View>

      {/*
        Строка под стопкой: сколько осталось и как перейти к следующему. «Дальше» — тихая
        кнопка, а не жест: отбрасывать человека взмахом здесь нельзя по смыслу продукта.
      */}
      {left > 1 ? (
        <View style={s.foot}>
          <Text style={s.left}>{T(`Ещё ${left - 1}`, `${left - 1} more`)}</Text>
          <Pressable accessibilityRole="button" hitSlop={8} onPress={onNext} style={s.next}>
            <Text style={s.nextText}>{T('Дальше', 'Next')} ›</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { gap: space.sm },
  // Запас снизу ровно под выступающие края (21 с борда) — иначе они обрежутся родителем.
  stack: { marginHorizontal: 20, marginBottom: DROP[LAYERS - 1] },
  layer: {
    position: 'absolute',
    height: 26,                     // видно только верх слоя; ниже он уходит под следующий
    borderRadius: rad.xl,
    backgroundColor: color.card,
    shadowColor: '#000', shadowOpacity: 0.07, shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 }, elevation: 2,
  },
  foot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 24 },
  left: { ...type.caption, color: color.ink, opacity: 0.6 } as any,
  next: { paddingVertical: 4, paddingHorizontal: 6 },
  nextText: { ...type.labelMedium, color: color.primary, fontWeight: '600' } as any,
  empty: { ...type.bodySmall, color: color.ink, opacity: 0.65, paddingHorizontal: 20 } as any,
});
