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
 *
 * ЧТО БЫЛО НЕ ТАК И ПОЧЕМУ ПЕРЕПИСАНО (10 сентября 2026, с телефона: «багованное пролистывание и
 * анимация, белое пятно сзади»). Три причины, и все в геометрии, а не в жесте:
 *   • Слои под верхней были полосками в 26 пунктов шириной от КОНТЕЙНЕРА, а сама карточка стояла в
 *     нём с полями 20 (marginHorizontal и у карточки, и у контейнера). Полоски выглядывали из-за
 *     карточки по бокам на 15 и 6 пунктов — это и есть «белое пятно».
 *   • Новая карточка проявлялась из нуля (170 мс), а уехавшая гасилась. Эти 170 мс на её месте не
 *     было ничего — кремовый фон и две белые полоски. То же на первом кадре: эффект запускался уже
 *     после отрисовки, и карточка мигала при каждом заходе на главную.
 *   • По завершении жеста сдвиг сбрасывался в ноль ДО смены индекса: слой, подтянувшийся на место
 *     верхней, на один кадр падал обратно, и только потом появлялась новая. Плюс лента забирала жест
 *     на Android — запрос на перехват не отклонялся, и карточка отпрыгивала посреди движения.
 *
 * ТЕПЕРЬ. Под верхней всегда лежит белая подложка её размера, а слои — такие же подложки в полный
 * размер, уменьшенные и опущенные (масштаб вместо ширины: пропорции с борда те же, 350→340→322).
 * Вперёд: верхняя уезжает влево, ближний слой поднимается на её место; в момент смены индекса
 * старое содержимое уже невидимо, подложка на месте, новое проступает НА ней — пятну быть не из
 * чего. Назад: предыдущая карточка въезжает слева ПОВЕРХ текущей — движение говорит «возвращаю»,
 * а не «выбрасываю». Один Animated.Value на всё, и отказ отдавать жест ленте.
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

const SPRING = { toValue: 0, useNativeDriver: true, speed: 18, bounciness: 5 } as const;

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
    ВСЕ ХУКИ ДО ЕДИНОГО ВЫЗЫВАЮТСЯ ДО ЛЮБОГО ВЫХОДА. Колода пустеет на ходу — приглашение разобрали,
    встреча ушла в прошлое, `index` перерос список, — и разное число хуков между отрисовками ломает
    жест (значения достаются из чужих ячеек) или роняет экран.
  */
  const [w, setW] = useState(0);
  const [h, setH] = useState(0);
  /** Тянут назад: въезжающая карточка рисуется только тогда — иначе она без дела лежала бы за краем. */
  const [back, setBack] = useState(false);

  /** Смещение жеста. Один источник для всего: верхняя, слои под ней и въезжающая читают его. */
  const shift = useRef(new Animated.Value(0)).current;
  /** Упор на краю колоды — отдельно от сдвига, чтобы край не двигал слои и не звал въезжающую. */
  const nudge = useRef(new Animated.Value(0)).current;
  /** Видимость содержимого верхней: после ухода вперёд новое проступает на подложке. */
  const show = useRef(new Animated.Value(1)).current;

  const idxRef = useRef(index);
  idxRef.current = index;
  const lenRef = useRef(items.length);
  lenRef.current = items.length;
  const goRef = useRef(onIndex);
  goRef.current = onIndex;
  const wRef = useRef(320);
  wRef.current = w || 320;
  /** Пока карточка едет, новый жест не принимаем: иначе индекс перескакивает через один. */
  const busy = useRef(false);
  const backRef = useRef(false);
  /** Смена индекса, при которой проявлять нечего: назад карточка уже въехала целиком. */
  const keep = useRef(false);
  const first = useRef(true);

  useEffect(() => {
    /*
      Первую отрисовку не трогаем: карточка уже на экране в полной яркости, и гасить её ради
      проявления значило бы мигнуть — ровно то, что здесь было и что видели с телефона.
    */
    if (first.current) { first.current = false; return; }
    shift.setValue(0);
    if (keep.current) { keep.current = false; show.setValue(1); return; }
    Animated.timing(show, { toValue: 1, duration: 150, easing: Easing.out(Easing.quad), useNativeDriver: true }).start();
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  /*
    ЖЕСТ.

    ПЕРЕХВАТ, А НЕ ПРОСЬБА. Колода живёт внутри прокручиваемой главной, и по обычному
    `onMoveShouldSetPanResponder` лента успевала забрать движение первой: палец вёл вбок, а экран
    уезжал вверх. Захватываем сами, но только явную горизонталь — вертикаль по-прежнему достаётся
    ленте, иначе палец, начавший скроллить с карточки, не прокрутил бы экран.

    И НЕ ОТДАЁМ. Взяв жест, на просьбу ленты вернуть его отвечаем «нет»: на Android она спрашивает
    при любом вертикальном отклонении пальца, и карточка отпрыгивала на середине движения.

    КРАЙ УПИРАЕТСЯ, А НЕ ПУСКАЕТ В ПУСТОТУ. На первой карточке вправо и на последней влево движение
    идёт втрое медленнее и обрывается: рука чувствует границу колоды раньше, чем глаз успевает
    решить, что приложение сломалось.
  */
  const settle = () => {
    Animated.spring(nudge, SPRING).start();
    Animated.spring(shift, SPRING).start(() => {
      if (backRef.current) { backRef.current = false; setBack(false); }
    });
  };
  const settleRef = useRef(settle);
  settleRef.current = settle;

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponderCapture: (_e, g) =>
        !busy.current && Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy) * 1.4,
      onMoveShouldSetPanResponder: (_e, g) =>
        !busy.current && Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy) * 1.4,
      onPanResponderTerminationRequest: () => false,
      onPanResponderMove: (_e, g) => {
        const i = idxRef.current;
        const edge = (g.dx > 0 && i === 0) || (g.dx < 0 && i >= lenRef.current - 1);
        if (edge) {
          shift.setValue(0);
          nudge.setValue(g.dx * RUBBER);
          return;
        }
        nudge.setValue(0);
        if (g.dx > 0 && !backRef.current) { backRef.current = true; setBack(true); }
        shift.setValue(g.dx);
      },
      onPanResponderRelease: (_e, g) => {
        const i = idxRef.current;
        const last = lenRef.current - 1;
        const width = wRef.current;
        const far = Math.max(MIN_TURN, width * 0.25);
        const next = (g.dx < -far || g.vx < -FLICK) && i < last;
        const prev = (g.dx > far || g.vx > FLICK) && i > 0;
        if (!next && !prev) {
          // Не дотянули — возвращается пружиной. Возврат обязан быть виден: он и объясняет, что
          // жест засчитан не был.
          settleRef.current();
          return;
        }
        busy.current = true;
        hTick();
        if (next) {
          Animated.timing(shift, {
            toValue: -width * 1.1, duration: 190, easing: Easing.out(Easing.cubic), useNativeDriver: true,
          }).start(() => {
            /*
              ПОРЯДОК ВАЖЕН. Сначала гасим содержимое, потом возвращаем сдвиг, потом меняем индекс.
              Кадр между сбросом и новой отрисовкой: старое содержимое невидимо, слой опустился на
              место, подложка на месте — на экране просто белая карточка. Затем на ней проступает
              новое. Ни кремового фона, ни скачка.
            */
            show.setValue(0);
            shift.setValue(0);
            busy.current = false;
            if (backRef.current) { backRef.current = false; setBack(false); }
            goRef.current(i + 1);
          });
        } else {
          Animated.timing(shift, {
            toValue: width, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: true,
          }).start(() => {
            /*
              Назад сдвиг НЕ сбрасываем до смены индекса — сбросит эффект после неё. Пока он равен
              ширине, новая верхняя стоит ровно на месте (вправо она не смещается по построению),
              а въезжавшая снимается тем же коммитом. Ни одного кадра, где что-то не на месте.
            */
            keep.current = true;
            busy.current = false;
            backRef.current = false;
            setBack(false);
            goRef.current(i - 1);
          });
        }
      },
      onPanResponderTerminate: () => settleRef.current(),
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
    ВЕРХНЯЯ ЕДЕТ ТОЛЬКО ВЛЕВО. Вправо она стоит: назад возвращается не она, а предыдущая — въезжает
    поверх. Это же даёт бесплатную гарантию при смене индекса назад (см. выше): при любом
    положительном сдвиге новая верхняя на месте.
  */
  const topX = Animated.add(
    shift.interpolate({ inputRange: [-1, 0, 1], outputRange: [-1, 0, 0] }),
    nudge
  );
  /** Ход жеста вперёд, 0…1: от него подтягиваются слои. Назад слои стоят — им некуда. */
  const reveal = (from: number, to: number) =>
    shift.interpolate({ inputRange: [-far, 0], outputRange: [to, from], extrapolate: 'clamp' });
  /** Масштаб слоя и его спуск так, чтобы снизу выглядывало ровно DROP — как на борде. */
  const scaleOf = (n: number) => (width - INSET[n] * 2) / width;
  const dropOf = (n: number) => DROP[n] + (h * (1 - scaleOf(n))) / 2;

  return (
    <View style={s.wrap}>
      <View
        style={s.stack}
        onLayout={(e) => { setW(e.nativeEvent.layout.width); setH(e.nativeEvent.layout.height); }}
      >
        {/* Подложка размером с верхнюю: на ней проступает новое содержимое, и она же не даёт
            кремовому фону показаться в кадр между уходом одной карточки и приходом другой. */}
        <Animated.View pointerEvents="none" style={[s.plate, { transform: [{ translateX: nudge }] }]} />

        {/*
          Края карточек снизу — не картинка «для красоты», а счётчик: видно, что за этой есть ещё.
          Дальний рисуется первым, верхняя ляжет поверх без возни с zIndex. Пока верхняя уходит,
          ближний слой поднимается и вырастает до её места, дальний — до места ближнего.
        */}
        {Array.from({ length: behind }, (_, k) => {
          const n = behind - k;                    // 2 — дальний, 1 — ближний
          return (
            <Animated.View
              key={n}
              pointerEvents="none"
              style={[
                s.layer,
                {
                  opacity: n === 1 ? 1 : reveal(0.7, 1),
                  transform: [
                    { translateY: reveal(dropOf(n), dropOf(n - 1)) },
                    { scale: reveal(scaleOf(n), scaleOf(n - 1)) },
                  ],
                },
              ]}
            />
          );
        })}

        <Animated.View
          {...pan.panHandlers}
          style={{
            opacity: show,
            transform: [
              { translateX: topX },
              /*
                Наклон и уменьшение — обратная связь пальцу, а не украшение: карточка ведёт себя
                как предмет, который тянут за угол, и по ней видно, засчитается жест или нет.
                Величины намеренно маленькие: это листание, а не бросок.
              */
              { rotate: shift.interpolate({ inputRange: [-width, 0], outputRange: ['-4deg', '0deg'], extrapolate: 'clamp' }) },
              { scale: shift.interpolate({ inputRange: [-far, 0], outputRange: [0.97, 1], extrapolate: 'clamp' }) },
            ],
          }}
        >
          {render(top)}
        </Animated.View>

        {/* Назад: предыдущая въезжает слева поверх текущей и в конце хода встаёт точно на её место. */}
        {back && index > 0 ? (
          <Animated.View
            pointerEvents="none"
            style={[
              StyleSheet.absoluteFill,
              { transform: [{ translateX: shift.interpolate({ inputRange: [0, width], outputRange: [-width, 0], extrapolate: 'clamp' }) }] },
            ]}
          >
            {render(items[index - 1])}
          </Animated.View>
        ) : null}
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
                show.setValue(0);          // новая проступит на подложке, как и при листании
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
  /*
    ПОЛЯ ЗДЕСЬ, И ТОЛЬКО ЗДЕСЬ. Карточки внутри колоды идут без своих полей — иначе слои считались
    бы от одной ширины, а карточка стояла бы в другой (так и было). Запас снизу — ровно под
    выступающие края (21 с борда), иначе их обрежет родитель.
  */
  stack: { marginHorizontal: 20, marginBottom: DROP[LAYERS - 1] },
  // Координаты явно: в RN 0.86 `StyleSheet.absoluteFillObject` больше нет (есть только absoluteFill).
  plate: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, borderRadius: rad.xl, backgroundColor: color.card },
  layer: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
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
