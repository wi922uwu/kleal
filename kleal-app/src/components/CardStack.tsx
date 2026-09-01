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
 * Поэтому листание в обе стороны обязательно, а на краях колода упирается, а не уезжает в пустоту.
 *
 * Геометрия с борда, не на глаз (Invite Stack 350×131 при карточке 350×110):
 *   Layer · 3rd   322×100   — на 28 уже и на 10 ниже
 *   Layer · 2nd   340×106   — на 10 уже и на 4 ниже
 *   Home Card     350×110   — верхняя, полная
 * Отсюда DROP: сумма выступающих краёв = 131 − 110 = 21, по 10–11 на слой.
 */
import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated, Easing, PanResponder, Pressable } from 'react-native';
import { hTick } from '../haptics';
import { color, radius as rad, space, type } from '../theme';

/** Насколько каждый следующий слой уже и ниже. С борда: 350→340→322 и 110→106→100. */
const INSET = [0, 5, 14];     // по горизонтали, с каждой стороны
const DROP = [0, 11, 21];     // насколько слой выглядывает снизу
const LAYERS = 3;             // верхняя + два края: борд рисует ровно столько

/** Порог листания: четверть карточки, но не меньше этого — на узком экране четверть слишком мала. */
const MIN_TURN = 56;
/** Бросок засчитывается по скорости, даже если палец не дошёл до порога: так листают на самом деле. */
const FLICK = 0.32;
/** Сопротивление на краю: карточка идёт за пальцем втрое медленнее и никуда не уходит. */
const RUBBER = 0.32;

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
  /*
    ВСЕ ХУКИ ДО ЕДИНОГО ВЫЗЫВАЮТСЯ ДО ЛЮБОГО ВЫХОДА. Раньше проверка «колода пуста» стояла выше
    жеста, а жест держит пять ссылок: на пустой колоде компонент звал три хука, на непустой
    восемь. Колода пустеет на ходу — приглашение разобрали, встреча ушла в прошлое, `index`
    перерос список, — и React упирается в разное число хуков между отрисовками: ломается жест
    (значения достаются из чужих ячеек) или падает экран.
  */
  const [w, setW] = useState(0);

  /** Смещение верхней карточки. Один источник для всего: и её движение, и отклик слоёв под ней. */
  const shift = useRef(new Animated.Value(0)).current;
  /** Появление новой карточки: она проступает на месте, а не прилетает. */
  const fade = useRef(new Animated.Value(1)).current;
  const rise = useRef(new Animated.Value(0)).current;

  const idxRef = useRef(index);
  idxRef.current = index;
  const lenRef = useRef(items.length);
  lenRef.current = items.length;
  const goRef = useRef(onIndex);
  goRef.current = onIndex;
  const wRef = useRef(320);
  wRef.current = w || 320;
  /** Пока карточка уезжает, новый жест не принимаем: иначе индекс перескакивает через один. */
  const busy = useRef(false);

  useEffect(() => {
    fade.setValue(0);
    rise.setValue(6);
    Animated.parallel([
      Animated.timing(fade, { toValue: 1, duration: 170, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      Animated.timing(rise, { toValue: 0, duration: 210, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
    ]).start();
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  /*
    ЖЕСТ.

    ПЕРЕХВАТ, А НЕ ПРОСЬБА. Колода живёт внутри прокручиваемой главной, и по обычному
    `onMoveShouldSetPanResponder` лента успевала забрать движение первой: палец вёл вбок, а экран
    уезжал вверх. Захватываем сами, но только явную горизонталь — вертикаль по-прежнему достаётся
    ленте, иначе палец, начавший скроллить с карточки, не прокрутил бы экран.

    КРАЙ УПИРАЕТСЯ, А НЕ ПУСКАЕТ В ПУСТОТУ. На первой карточке вправо и на последней влево движение
    идёт втрое медленнее и обрывается: рука чувствует границу колоды раньше, чем глаз успевает
    решить, что приложение сломалось.
  */
  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponderCapture: (_e, g) =>
        !busy.current && Math.abs(g.dx) > 6 && Math.abs(g.dx) > Math.abs(g.dy) * 1.6,
      onMoveShouldSetPanResponder: (_e, g) =>
        !busy.current && Math.abs(g.dx) > 6 && Math.abs(g.dx) > Math.abs(g.dy) * 1.6,
      onPanResponderMove: (_e, g) => {
        const i = idxRef.current;
        const edge = (g.dx > 0 && i === 0) || (g.dx < 0 && i >= lenRef.current - 1);
        shift.setValue(edge ? g.dx * RUBBER : g.dx);
      },
      onPanResponderRelease: (_e, g) => {
        const i = idxRef.current;
        const last = lenRef.current - 1;
        const far = Math.max(MIN_TURN, wRef.current * 0.25);
        const next = (g.dx < -far || g.vx < -FLICK) && i < last;
        const prev = (g.dx > far || g.vx > FLICK) && i > 0;
        if (!next && !prev) {
          // Не дотянули — карточка возвращается пружиной. Возврат обязан быть виден: он и
          // объясняет, что жест засчитан не был.
          Animated.spring(shift, { toValue: 0, useNativeDriver: true, speed: 18, bounciness: 5 }).start();
          return;
        }
        busy.current = true;
        hTick();
        Animated.timing(shift, {
          toValue: (next ? -1 : 1) * wRef.current * 1.1,
          duration: 190,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        }).start(() => {
          /*
            ПОРЯДОК ЗДЕСЬ ВАЖЕН И СТОИЛ ОТДЕЛЬНОГО РАЗБОРА. Сначала гасим, потом возвращаем
            смещение, и только потом меняем индекс. Если вернуть смещение раньше, уехавшая
            карточка на один кадр окажется на месте в полной яркости — и переход читается как
            мигание. Гашение снимает этот кадр: что бы ни оказалось под ним, оно уже невидимо и
            проявится своей анимацией.
          */
          fade.setValue(0);
          shift.setValue(0);
          busy.current = false;
          goRef.current(next ? i + 1 : i - 1);
        });
      },
      onPanResponderTerminate: () => {
        Animated.spring(shift, { toValue: 0, useNativeDriver: true, speed: 18, bounciness: 5 }).start();
      },
    })
  ).current;

  if (!items.length || index >= items.length) {
    return emptyHint ? <Text style={s.empty}>{emptyHint}</Text> : null;
  }

  const width = w || 320;
  const far = Math.max(MIN_TURN, width * 0.25);
  const top = items[index];
  const left = items.length - index;
  /** Сколько слоёв-краёв рисовать: только столько, сколько карточек реально осталось за верхней. */
  const behind = Math.min(LAYERS - 1, Math.max(0, left - 1));

  /*
    ОТКЛИК ВСЕЙ КОЛОДЫ, А НЕ ОДНОЙ КАРТОЧКИ. Раньше двигалась только верхняя, а края под ней
    стояли неподвижно — со стороны это читалось как одна карточка, съезжающая по неподвижному
    фону, а не как колода. Теперь пока верхняя уходит, нижние подтягиваются на её место: ближний
    край поднимается и расширяется до полной ширины, дальний занимает место ближнего.

    Только ВПЕРЁД (палец влево): при возврате назад карточка не уходит из колоды, и подтягиваться
    нижним некуда — движение там было бы враньём о том, что происходит.
  */
  const reveal = (from: number, to: number) =>
    shift.interpolate({ inputRange: [-far, 0], outputRange: [to, from], extrapolate: 'clamp' });

  return (
    <View style={s.wrap}>
      <View style={s.stack} onLayout={(e) => setW(e.nativeEvent.layout.width)}>
        {/*
          Края карточек снизу — не картинка «для красоты», а счётчик: видно, что за этой есть ещё.
          Рисуются ПЕРВЫМИ, чтобы верхняя легла поверх без возни с zIndex.
        */}
        {Array.from({ length: behind }, (_, i) => {
          const n = i + 1;                        // 1 — ближний край, 2 — дальний
          const base = Math.max(1, width - INSET[n] * 2);
          const grown = Math.max(1, width - INSET[n - 1] * 2);
          return (
            <Animated.View
              key={n}
              pointerEvents="none"
              style={[
                s.layer,
                {
                  left: INSET[n],
                  right: INSET[n],
                  bottom: -DROP[n],
                  opacity: reveal(1 - n * 0.28, 1 - (n - 1) * 0.28),
                  transform: [
                    // Знак минусовой: слой лежит НИЖЕ на DROP[n] и поднимается на место верхнего.
                    { translateY: reveal(0, -(DROP[n] - DROP[n - 1])) },
                    { scaleX: reveal(1, grown / base) },
                  ],
                },
              ]}
            />
          );
        })}

        <Animated.View
          {...pan.panHandlers}
          style={{
            opacity: fade,
            transform: [
              { translateY: rise },
              { translateX: shift },
              /*
                Наклон и уменьшение — обратная связь пальцу, а не украшение: карточка ведёт себя
                как предмет, который тянут за угол, и по ней видно, засчитается жест или нет.
                Величины намеренно маленькие: это листание, а не бросок.
              */
              {
                rotate: shift.interpolate({
                  inputRange: [-width, 0, width],
                  outputRange: ['-4deg', '0deg', '4deg'],
                  extrapolate: 'clamp',
                }),
              },
              {
                scale: shift.interpolate({
                  inputRange: [-far, 0, far],
                  outputRange: [0.97, 1, 0.97],
                  extrapolate: 'clamp',
                }),
              },
            ],
          }}
        >
          {render(top)}
        </Animated.View>
      </View>

      {/*
        Точки вместо кнопки: они говорят, сколько карточек и где мы, но ничего не обещают нажать.
        И всё же нажимаются — на них целятся, когда карточек три-четыре и нужна конкретная. Промах
        по шеститочечной цели неизбежен, поэтому область нажатия расширена, а сама точка осталась
        того же размера, что на борде.
      */}
      {items.length > 1 ? (
        <View style={s.dots}>
          {items.map((it, i) => (
            <Pressable
              key={it.key}
              accessibilityRole="button"
              hitSlop={10}
              onPress={() => {
                if (i === index || busy.current) return;
                hTick();
                shift.setValue(0);
                onIndex(i);
              }}
            >
              <View style={[s.dot, i === index && s.dotOn]} />
            </Pressable>
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
