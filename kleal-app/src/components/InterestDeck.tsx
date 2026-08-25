/**
 * Колода интересов — то, что человек выбирает на шаге увлечений.
 *
 * ПОЧЕМУ КОЛОДА, А НЕ РЯД ЧИПОВ. Чипы просят выбрать: человек читает шесть подписей разом,
 * сравнивает и решает, какие «правильные». Карта спрашивает про одну вещь и требует одного
 * движения — да или нет, — и на неё отвечают не выбирая, а вспоминая: «бег? да, бегаю». Разница
 * между витриной и разговором.
 *
 * ВЛЕВО — ДОБАВИТЬ, ВПРАВО — ПРОПУСТИТЬ. Направления заданы продуктом и намеренно обратны
 * привычным по знакомствам: там вправо значит «нравится человек», а здесь колода не про людей, и
 * заимствовать чужой рефлекс не за чем.
 *
 * СНАЧАЛА ЗАХОД, ПОТОМ РАЗГОВОР. Колода НЕ отправляет реплику на каждый свайп. Раньше отправляла —
 * и агент отвечал вопросом на каждую карту, так что проход превращался в допрос: карта, вопрос,
 * карта, вопрос, и колода уезжала вниз за ответом. Теперь пальцем проходят сколько хочется, а
 * наверх уходит один список по кнопке «Готово» — или сам собой, когда карты кончились.
 *
 * ЖЕСТ ТОЛЬКО У ВЕРХНЕЙ КАРТЫ. Нижние — картинка глубины: они не ловят касания вовсе, иначе палец,
 * соскользнувший с верхней, начал бы тащить вторую.
 *
 * ЛЕНТА ПОД КОЛОДОЙ ЗАМИРАЕТ НА ВРЕМЯ ЖЕСТА. Без этого экран уезжал прямо во время свайпа: у
 * прокрутки свой порог, и на диагональном движении она успевала забрать жест себе. Три меры сразу,
 * потому что по одной не хватало: порог захвата прощает диагональ, `onPanResponderTerminationRequest`
 * не отдаёт жест обратно, а `onDragChange` гасит саму прокрутку — так же, как на возрасте и карте.
 *
 * ВСЁ ДВИЖЕНИЕ НА НАТИВНОМ ДРАЙВЕРЕ: сдвиг, поворот, прозрачность, масштаб. JS участвует ровно
 * дважды за карту — на щелчке при переходе порога и на решении при отпускании.
 */
import React, { useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import Svg, { Defs, RadialGradient, Rect, Stop } from 'react-native-svg';
import { DeckCard } from '../interests-deck';
import { STEP_HOBBIES } from '../onboarding';
import { useLang } from '../i18n';
import { hCommit, hOk, hTap, hTick } from '../haptics';
import { color, deckTone, displayFamily, radius as rad, space, type } from '../theme';

/** С какого сдвига отпускание считается решением, а не промахом. */
const DECIDE = 92;
/** Сколько карт видно в стопке. Больше трёх — просто шум по краям. */
const DEPTH = 3;
/** На сколько уходит вниз и мельчает каждая следующая. */
const STEP_Y = 14;
const STEP_S = 0.055;
/** Сила белой плёнки на одну ступень глубины. */
const VEIL = 0.16;
const CARD_H = 176;
const CARD_R = 34;
/** Где кончается стопка и начинается подвал. Место под кнопку отведено всегда — см. подвал. */
const FOOT_TOP = CARD_H + (DEPTH - 1) * STEP_Y + 12;

/**
 * Ступени затухания свечения.
 *
 * ПЯТЬ, А НЕ ДВЕ. Две ступени дают круг с различимым краем — заливка читается как пятно, наклеенное
 * поверх подложки. Кривая с плавно падающей непрозрачностью убирает край вовсе: у свечения нет
 * границы, оно просто кончается.
 */
const BLOOM: [string, number][] = [
  ['0', 1],
  ['0.3', 0.88],
  ['0.55', 0.58],
  ['0.78', 0.24],
  ['1', 0],
];

/**
 * Лицо карточки: свечение своего тона и подпись поверх ядра.
 *
 * ГРАДИЕНТ НАРИСОВАН SVG, А НЕ expo-linear-gradient — последнего в проекте нет, а
 * `react-native-svg` уже стоит. Ставить зависимость ради заливки значит увеличить сборку и список
 * того, что придётся чинить при переезде на новый SDK.
 *
 * КООРДИНАТЫ — ЧЕСТНЫЕ ТОЧКИ, А НЕ ПРОЦЕНТЫ. `gradientUnits="userSpaceOnUse"` считает центр и
 * радиусы в тех же точках, что и сама карта. С процентами это зависело бы от области просмотра
 * слоя — тот самый случай, из-за которого заливка пузыря реплики однажды закрасила только верх.
 */
function Face({ item, w }: { item: DeckCard; w: number }) {
  const lang = useLang();
  const t = deckTone[item.tone];
  const core = `core-${item.key}`;
  const side = `side-${item.key}`;
  return (
    <>
      <Svg width={w} height={CARD_H} style={StyleSheet.absoluteFill}>
        <Defs>
          {/* Ядро стоит там же, где подпись: белый текст держится только на насыщенном. */}
          <RadialGradient
            id={core}
            gradientUnits="userSpaceOnUse"
            cx={w * 0.5}
            cy={CARD_H * 0.54}
            rx={w * 0.6}
            ry={CARD_H * 0.66}
          >
            {BLOOM.map(([o, a]) => <Stop key={o} offset={o} stopColor={t.glow} stopOpacity={a} />)}
          </RadialGradient>
          {/* Второй отсвет смещён в угол — он и ломает симметрию, из-за которой ядро выглядело бы
              нарисованным циркулем. */}
          <RadialGradient
            id={side}
            gradientUnits="userSpaceOnUse"
            cx={w * 0.18}
            cy={CARD_H * 0.14}
            rx={w * 0.55}
            ry={CARD_H * 0.8}
          >
            {BLOOM.map(([o, a]) => <Stop key={o} offset={o} stopColor={t.halo} stopOpacity={a} />)}
          </RadialGradient>
        </Defs>
        <Rect x={0} y={0} width={w} height={CARD_H} fill={t.wash} />
        <Rect x={0} y={0} width={w} height={CARD_H} fill={`url(#${side})`} />
        <Rect x={0} y={0} width={w} height={CARD_H} fill={`url(#${core})`} />
      </Svg>
      {/*
        Светлая полоса по верхней кромке — та же внутренняя тень, что у стеклянных кнопок. Без неё
        карта выглядит наклейкой: у настоящей поверхности верх всегда светлее, потому что свет
        падает сверху.
      */}
      <View style={s.sheen} pointerEvents="none" />
      <Text style={[s.label, { fontFamily: displayFamily(lang) }]} numberOfLines={3}>
        {item.label}
      </Text>
    </>
  );
}

export function InterestDeck({ items, onPass, onDragChange }: {
  items: DeckCard[];
  /** Итог захода: что добавили и что вообще прошли. Зовётся ОДИН раз, а не на каждую карту. */
  onPass: (added: string[], seen: string[]) => void;
  /** Пока палец на карте, лента разговора обязана стоять. */
  onDragChange?: (dragging: boolean) => void;
}) {
  const { width } = useWindowDimensions();
  const [at, setAt] = useState(0);
  const [picked, setPicked] = useState<string[]>([]);
  /*
    СДВИГ — СВЕЖЕЕ ЗНАЧЕНИЕ НА КАЖДУЮ КАРТУ, А НЕ ОДНО ОБЩЕЕ.
    Общее приходилось сбрасывать в ноль после вылета — и на кадр между сбросом и перерисовкой
    улетевшая карта возвращалась в середину. Это и был «на секунду показывается другая»: сброс
    значения бьёт по нативному виду немедленно, а новый список React показывает своим тактом
    позже. Новое значение рождается вместе с новым разворотом стопки, сбрасывать нечего, и кадра
    с чужой картой не существует.
  */
  const [x, setX] = useState(() => new Animated.Value(0));
  /** Подъём карты под пальцем: она отрывается от стопки, пока её держат. */
  const grab = useRef(new Animated.Value(0)).current;
  /** Толчок счётчика на кнопке — по нему видно, что карта засчиталась. */
  const pop = useRef(new Animated.Value(0)).current;
  /** Прошёл ли порог сейчас — чтобы щёлкнуть один раз, а не на каждом кадре. */
  const armed = useRef(0);
  const kept = useRef<string[]>([]);
  const seen = useRef<string[]>([]);
  /** Заход отдаётся один раз: кнопкой ИЛИ по концу колоды, но не обоими. */
  const sent = useRef(false);

  const CARD_W = Math.min(320, width - 88);
  const FLY = width + CARD_W;

  const flush = () => {
    if (sent.current) return;
    sent.current = true;
    onDragChange?.(false);
    onPass(kept.current, seen.current);
  };

  /** Убрать верхнюю карту в сторону и показать следующую. */
  const decide = (dir: -1 | 1, item: DeckCard, vx: number) => {
    if (dir < 0) hCommit();
    else hTap();
    /*
      Длительность зависит от размаха: карта, которую отшвырнули, обязана улететь быстрее той,
      которую довели до порога и отпустили. Фиксированные 220 мс делали резкий бросок вязким —
      палец уже остановился, а карта всё ещё ползла.
    */
    const dur = Math.max(170, Math.min(300, 300 - Math.abs(vx) * 80));
    Animated.timing(x, {
      toValue: dir * FLY,
      duration: dur,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (!finished) return;
      seen.current = [...seen.current, item.label];
      if (dir < 0) {
        kept.current = [...kept.current, item.label];
        setPicked(kept.current);
        pop.setValue(0);
        Animated.spring(pop, { toValue: 1, useNativeDriver: true, damping: 9, stiffness: 320, mass: 0.7 }).start();
      }
      const next = at + 1;
      armed.current = 0;
      // Обе правки одним тактом: новый разворот стопки и новое нулевое значение сдвига.
      setAt(next);
      setX(new Animated.Value(0));
      if (next >= items.length) flush();
    });
  };

  const pan = useMemo(
    () =>
      PanResponder.create({
        /*
          Порог прощает диагональ: строгое `|dx| > |dy|` проигрывало прокрутке на быстром броске —
          первые замеры у резкого движения почти всегда с вертикальной составляющей, и лента
          успевала забрать жест.
        */
        onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dx) > 3 && Math.abs(g.dx) > Math.abs(g.dy) * 0.6,
        onPanResponderGrant: () => {
          onDragChange?.(true);
          Animated.spring(grab, { toValue: 1, useNativeDriver: true, damping: 16, stiffness: 300, mass: 0.7 }).start();
        },
        onPanResponderMove: (_e, g) => {
          x.setValue(g.dx);
          const side = g.dx <= -DECIDE ? -1 : g.dx >= DECIDE ? 1 : 0;
          if (side !== armed.current) {
            armed.current = side;
            // Щелчок ровно на пересечении порога: рука узнаёт, что решение засчитано, ещё до
            // отпускания — и палец можно убирать, не гадая, хватило ли размаха.
            if (side) hTick();
          }
        },
        // Жест не отдаётся обратно ленте: без этого прокрутка отбирала его на середине свайпа, и
        // карта замирала под пальцем, а экран уезжал.
        onPanResponderTerminationRequest: () => false,
        onShouldBlockNativeResponder: () => true,
        onPanResponderRelease: (_e, g) => {
          onDragChange?.(false);
          Animated.spring(grab, { toValue: 0, useNativeDriver: true, damping: 18, stiffness: 260 }).start();
          const item = items[at];
          const far = Math.abs(g.dx) > DECIDE;
          const flung = Math.abs(g.vx) > 0.6;
          if (item && (far || flung)) {
            decide(g.dx < 0 ? -1 : 1, item, g.vx);
            return;
          }
          armed.current = 0;
          Animated.spring(x, {
            toValue: 0,
            useNativeDriver: true,
            damping: 20,
            stiffness: 260,
            mass: 0.7,
          }).start();
        },
        onPanResponderTerminate: () => {
          onDragChange?.(false);
          armed.current = 0;
          Animated.spring(grab, { toValue: 0, useNativeDriver: true, damping: 18, stiffness: 260 }).start();
          Animated.spring(x, { toValue: 0, useNativeDriver: true, damping: 20, stiffness: 260 }).start();
        },
      }),
    [at, items, x]
  );

  const top = items[at];
  if (!top) return null;

  /*
    Поворот вокруг дальнего края, а не центра: карта не крутится волчком, а заваливается — так же,
    как настоящая, если тянуть её за угол. Величина маленькая, восемь градусов на полном сдвиге:
    больше начинает читаться как трюк.
  */
  const rotate = x.interpolate({
    inputRange: [-FLY, 0, FLY],
    outputRange: ['-8deg', '0deg', '8deg'],
    extrapolate: 'clamp',
  });
  /*
    СКОЛЬКО ПРОЙДЕНО ДО РЕШЕНИЯ, БЕЗ ЗНАКА. Из этого числа растёт вся стопка: пока верхнюю тянут,
    вторая поднимается на её место, третья — на место второй, четвёртая проявляется из ничего. К
    моменту, когда карту меняют, каждая уже стоит ровно там, где ей быть с новой глубиной, — и
    подмена не видна ни одним кадром. Раньше стопка стояла неподвижно и подпрыгивала после.
  */
  const prog = x.interpolate({ inputRange: [-DECIDE, 0, DECIDE], outputRange: [1, 0, 1], extrapolate: 'clamp' });
  const addOn = x.interpolate({ inputRange: [-DECIDE, -20, 0], outputRange: [1, 0, 0], extrapolate: 'clamp' });
  const skipOn = x.interpolate({ inputRange: [0, 20, DECIDE], outputRange: [0, 0, 1], extrapolate: 'clamp' });
  const addPop = x.interpolate({ inputRange: [-DECIDE, -20, 0], outputRange: [1, 0.72, 0.72], extrapolate: 'clamp' });
  const skipPop = x.interpolate({ inputRange: [0, 20, DECIDE], outputRange: [0.72, 0.72, 1], extrapolate: 'clamp' });

  return (
    <View style={[s.wrap, { width: CARD_W }]}>
      {/*
        Стопка рисуется от дальней карты к ближней: React кладёт написанное позже поверх, поэтому
        верхняя (d = 0) идёт последней.
      */}
      {Array.from({ length: DEPTH }, (_, d) => DEPTH - 1 - d)
        .filter((d) => items[at + d])
        .map((d) =>
          d === 0 ? (
            <Animated.View
              key={top.key + at}
              {...pan.panHandlers}
              style={[
                s.card,
                {
                  width: CARD_W,
                  shadowColor: deckTone[top.tone].glow,
                  transform: [
                    { translateX: x },
                    // Карта чуть приподнимается по мере ухода — не плоско едет, а снимается со стопки.
                    { translateY: Animated.multiply(prog, -8) },
                    { rotate },
                    { scale: Animated.add(1, Animated.multiply(grab, 0.02)) },
                  ],
                },
              ]}
            >
              <Face item={top} w={CARD_W} />

              {/* Метки решения проявляются по ходу движения — до отпускания видно, что случится. */}
              <Animated.View
                style={[s.mark, s.markAdd, { opacity: addOn, transform: [{ scale: addPop }] }]}
              >
                <Text style={s.markAddText}>{STEP_HOBBIES.deckAdd()}</Text>
              </Animated.View>
              <Animated.View
                style={[s.mark, s.markSkip, { opacity: skipOn, transform: [{ scale: skipPop }] }]}
              >
                <Text style={s.markSkipText}>{STEP_HOBBIES.deckSkip()}</Text>
              </Animated.View>
            </Animated.View>
          ) : (
            <Animated.View
              key={items[at + d].key + (at + d)}
              pointerEvents="none"
              style={[
                s.card,
                {
                  width: CARD_W,
                  shadowColor: deckTone[items[at + d].tone].glow,
                  // Самая дальняя проявляется по ходу жеста: иначе она возникала бы разом в тот
                  // кадр, когда верхняя улетела.
                  opacity: d === DEPTH - 1 ? prog : 1,
                  transform: [
                    { translateY: Animated.add(d * STEP_Y, Animated.multiply(prog, -STEP_Y)) },
                    { scale: Animated.add(1 - d * STEP_S, Animated.multiply(prog, STEP_S)) },
                  ],
                },
              ]}
            >
              <Face item={items[at + d]} w={CARD_W} />
              {/*
                Нижние приглушены белой плёнкой, а не своим бледным свечением: так у них остаётся
                собственный цвет — видно, что следующая карта про другое, — но спорить с верхней он
                уже не может.

                ПЛЁНКА ГАСНЕТ ПО ХОДУ ЖЕСТА, А НЕ СКАЧКОМ. Раньше она держала свою силу всё время,
                пока верхнюю тянут, и слетала разом в кадр подмены — карта в этот миг заметно
                светлела, и это читалось как мигнувшая чужая. Теперь сила плёнки считается от той
                же глубины, что и положение: у второй карты к моменту подмены она уже ноль, у
                третьей — ровно столько, сколько положено второй.
              */}
              <Animated.View
                style={[s.veil, { opacity: Animated.add(VEIL * d, Animated.multiply(prog, -VEIL)) }]}
                pointerEvents="none"
              />
            </Animated.View>
          )
        )}

      <View style={s.foot} pointerEvents="box-none">
        {/*
          Подсказка НЕ уступает место кнопке. Раньше уступала — и тот, кто уже добавил одну
          карточку, терял единственное постоянное напоминание, куда что тянуть: метки на карте
          видно только во время самого жеста. Место под кнопку отведено всегда, поэтому её
          появление ничего не двигает.
        */}
        <Text style={s.hint}>{STEP_HOBBIES.deckHint()}</Text>
        {picked.length ? (
          <Animated.View
            style={{
              opacity: pop.interpolate({ inputRange: [0, 1], outputRange: [0.65, 1] }),
              transform: [{ scale: pop.interpolate({ inputRange: [0, 1], outputRange: [0.86, 1] }) }],
            }}
          >
            <Pressable
              accessibilityRole="button"
              onPress={() => {
                hOk();
                flush();
              }}
              style={({ pressed }) => [s.done, pressed && s.doneOn]}
            >
              <Text style={s.doneText}>{STEP_HOBBIES.deckSave(picked.length)}</Text>
            </Pressable>
          </Animated.View>
        ) : null}
      </View>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  /** Высота с запасом: под стопкой ещё кнопка захода, а сами карты уходят вниз на DEPTH шагов. */
  wrap: { height: FOOT_TOP + 64, alignSelf: 'center', marginTop: space.sm },
  card: {
    position: 'absolute',
    height: CARD_H,
    borderRadius: CARD_R,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
    // Тень окрашена тоном карты, а не чёрным: под карточкой остаётся отсвет её же свечения — то,
    // из-за чего она выглядит подсвеченной, а не лежащей на бумаге.
    shadowOpacity: 0.3,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 10 },
    elevation: 5,
  },
  sheen: {
    ...StyleSheet.absoluteFillObject,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFFA6',
    borderRadius: CARD_R,
  },
  veil: { ...StyleSheet.absoluteFillObject, backgroundColor: color.card },
  label: {
    ...type.display,
    fontSize: 22,
    lineHeight: 30,
    color: color.onPrimary,
    textAlign: 'center',
    // Тонкая тень под буквами: подпись стоит на цвете, и без неё края букв растворяются в свечении.
    textShadowColor: '#00000026',
    textShadowRadius: 10,
    textShadowOffset: { width: 0, height: 1 },
  } as any,
  mark: {
    position: 'absolute',
    top: space.md,
    paddingHorizontal: 12,
    height: 28,
    borderRadius: rad.full,
    justifyContent: 'center',
  },
  markAdd: { left: space.md, backgroundColor: '#FFFFFFF2' },
  markAddText: { ...type.labelSmall, color: color.primary } as any,
  markSkip: { right: space.md, backgroundColor: '#FFFFFFF2' },
  markSkipText: { ...type.labelSmall, color: color.muted } as any,
  foot: { position: 'absolute', top: FOOT_TOP, left: 0, right: 0, alignItems: 'center', gap: space.sm },
  hint: { ...type.fine, color: color.muted, textAlign: 'center' } as any,
  done: {
    height: 40,
    paddingHorizontal: space.lg,
    borderRadius: rad.full,
    backgroundColor: color.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  doneOn: { opacity: 0.86 },
  doneText: { ...type.labelMedium, color: color.onPrimary } as any,
});
