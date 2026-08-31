/**
 * Стопка карточек — компонент борда «Invite Stack» (GR.01).
 *
 * ЗАЧЕМ СТОПКА, А НЕ СПИСОК. Продукт обещает 2–4 объяснённых варианта, а не бесконечную ленту
 * людей: список из восьми карточек подряд — это ровно та лента, от которой Kleal отказывается.
 * Стопка показывает ОДНОГО человека и говорит, сколько ещё за ним.
 *
 * ЛИСТАНИЕ — НЕ СВАЙП-КОЛОДА, и разница здесь смысловая, а не техническая. Свайпы названы врагом
 * продукта («социальное трение: свайпы, холодные сообщения, мёртвые чаты»), но запрещён там
 * конкретный жест — ОТБРОСИТЬ человека вбок, то есть принять решение броском. Здесь жест ничего
 * не решает и никого не выбрасывает: он перелистывает, и назад тоже. Карточка остаётся в колоде,
 * решение по ней принимают, открыв её.
 *
 * Поэтому листание в обе стороны обязательно. Односторонняя лента была бы тем самым отбрасыванием:
 * пролистнул — потерял. Раньше на этом месте стояла кнопка «Дальше ›», она умела только вперёд.
 *
 * Геометрия с борда, не на глаз (Invite Stack 350×131 при карточке 350×110):
 *   Layer · 3rd   322×100   — на 28 уже и на 10 ниже
 *   Layer · 2nd   340×106   — на 10 уже и на 4 ниже
 *   Home Card     350×110   — верхняя, полная
 * Отсюда PEEK: сумма выступающих краёв = 131 − 110 = 21, по 10–11 на слой.
 */
import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated, Easing, PanResponder } from 'react-native';
import { HOME } from '../home';
import { color, radius as rad, space, type } from '../theme';

/** Насколько каждый следующий слой уже и ниже. С борда: 350→340→322 и 110→106→100. */
const INSET = [0, 5, 14];     // по горизонтали, с каждой стороны
const DROP = [0, 11, 21];     // насколько слой выглядывает снизу
const LAYERS = 3;             // верхняя + два края: борд рисует ровно столько

export function CardStack<T_ extends { key: string }>({
  items,
  index,
  onIndex,
  render,
  emptyHint,
}: {
  items: T_[];
  /** Какая карточка сверху. Хранится СНАРУЖИ: экран знает, по кому уже приняли решение. */
  index: number;
  /** Куда перешли. Двусторонний: листают и вперёд, и назад. */
  onIndex: (i: number) => void;
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

  /*
    ЖЕСТ. Палец ведёт верхнюю карточку за собой, отпускание решает: ушла дальше порога — листаем,
    не ушла — возвращаем на место. Порог в шестьдесят точек взят не на глаз: меньше — и колода
    перелистывается от случайного касания при прокрутке ленты, больше — жест приходится
    «дожимать».

    ВЕРТИКАЛЬ ОТДАЁМ ЛЕНТЕ. Колода живёт внутри прокручиваемой главной, и захват жеста по любому
    движению означал бы, что палец, начавший скроллить с карточки, не прокрутит экран. Поэтому
    берём только те движения, где горизонталь вдвое обгоняет вертикаль.
  */
  const dx = useRef(new Animated.Value(0)).current;
  const idxRef = useRef(index);
  idxRef.current = index;
  const lenRef = useRef(items.length);
  lenRef.current = items.length;
  const goRef = useRef(onIndex);
  goRef.current = onIndex;

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_e, g) =>
        Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy) * 2,
      onPanResponderMove: (_e, g) => dx.setValue(g.dx),
      onPanResponderRelease: (_e, g) => {
        const i = idxRef.current;
        const last = lenRef.current - 1;
        const next = g.dx < -60 && i < last ? i + 1
                   : g.dx > 60 && i > 0 ? i - 1
                   : i;
        // Возврат на место — всегда, даже когда листаем: карточка следующей проявляется своей
        // анимацией с нуля, и оставленное смещение сдвинуло бы её вбок.
        Animated.timing(dx, { toValue: 0, duration: 160, easing: Easing.out(Easing.quad),
                              useNativeDriver: true }).start();
        if (next !== i) goRef.current(next);
      },
      onPanResponderTerminate: () => {
        Animated.timing(dx, { toValue: 0, duration: 160, useNativeDriver: true }).start();
      },
    })
  ).current;

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

        <Animated.View
          {...pan.panHandlers}
          style={{ opacity: fade, transform: [{ translateY: rise }, { translateX: dx }] }}
        >
          {render(top)}
        </Animated.View>
      </View>

      {/*
        Точки вместо кнопки: они говорят, сколько карточек и где мы, но ничего не обещают нажать.
        Кнопка «Дальше ›» стояла здесь, пока листать было нечем; с жестом она стала бы вторым
        способом сделать то же самое, а два способа на одно действие — это выбор там, где его не
        требуется делать.
      */}
      {items.length > 1 ? (
        <View style={s.dots}>
          {items.map((it, i) => (
            <View key={it.key} style={[s.dot, i === index && s.dotOn]} />
          ))}
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
  dots: { flexDirection: 'row', alignSelf: 'center', gap: 6, paddingTop: 2 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: color.ink, opacity: 0.18 },
  /** Текущая — фирменным и без прозрачности: точка-указатель, а не просто «ярче». */
  dotOn: { backgroundColor: color.primary, opacity: 1 },
  empty: { ...type.bodySmall, color: color.ink, opacity: 0.65, paddingHorizontal: 20 } as any,
});
