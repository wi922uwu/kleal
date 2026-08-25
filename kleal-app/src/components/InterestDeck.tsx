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
 * ЖЕСТ ТОЛЬКО У ВЕРХНЕЙ КАРТЫ. Нижние — картинка глубины: они не ловят касания вовсе, иначе палец,
 * соскользнувший с верхней, начал бы тащить вторую.
 *
 * ВСЁ ДВИЖЕНИЕ НА НАТИВНОМ ДРАЙВЕРЕ: сдвиг, поворот, прозрачность. JS участвует ровно дважды за
 * карту — на щелчке при переходе порога и на решении при отпускании.
 */
import React, { useMemo, useRef, useState } from 'react';
import {
  Animated,
  PanResponder,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';
import { DeckCard } from '../interests-deck';
import { STEP_HOBBIES } from '../onboarding';
import { useLang } from '../i18n';
import { hCommit, hTap, hTick } from '../haptics';
import { color, deckTone, displayFamily, radius as rad, space, type } from '../theme';

/** С какого сдвига отпускание считается решением, а не промахом. */
const DECIDE = 96;
/** Сколько карт видно в стопке. Больше трёх — просто шум по краям. */
const DEPTH = 3;
/** На сколько уходит вниз и мельчает каждая следующая. */
const STEP_Y = 12;
const STEP_S = 0.05;
const CARD_H = 208;

/**
 * Лицо карточки: градиент своего тона, знак и подпись.
 *
 * ГРАДИЕНТ НАРИСОВАН SVG, А НЕ expo-linear-gradient — последнего в проекте нет, а
 * `react-native-svg` уже стоит. Ставить зависимость ради заливки значит увеличить сборку и список
 * того, что придётся чинить при переезде на новый SDK.
 *
 * РАЗМЕР ЗАЛИВКИ — ЧЕСТНЫЕ ТОЧКИ, А НЕ ПРОЦЕНТЫ. Проценты внутри SVG считаются от области
 * просмотра, и у слоя без `viewBox` она берётся по ширине: заливка закрашивала бы верхнюю часть
 * карты и обрывалась резкой горизонталью. Тот же случай уже был на пузыре реплики.
 */
function Face({ item, w }: { item: DeckCard; w: number }) {
  const lang = useLang();
  const [from, to] = deckTone[item.tone];
  const id = `t-${item.tone}`;
  return (
    <>
      <Svg width={w} height={CARD_H} style={StyleSheet.absoluteFill}>
        <Defs>
          <LinearGradient id={id} x1="0" y1="0" x2="0.7" y2="1">
            <Stop offset="0" stopColor={from} />
            <Stop offset="1" stopColor={to} />
          </LinearGradient>
        </Defs>
        <Rect x={0} y={0} width={w} height={CARD_H} fill={`url(#${id})`} />
      </Svg>
      {/*
        Светлая полоса по верхней кромке — та же внутренняя тень, что у стеклянных кнопок. Без неё
        карта выглядит наклейкой: у настоящей поверхности верх всегда светлее, потому что свет
        падает сверху.
      */}
      <View style={s.sheen} pointerEvents="none" />
      <Text style={s.emoji}>{item.emoji}</Text>
      <Text style={[s.label, { fontFamily: displayFamily(lang) }]} numberOfLines={2}>
        {item.label}
      </Text>
    </>
  );
}

export function InterestDeck({ items, onAdd, onSkip }: {
  items: DeckCard[];
  onAdd: (item: DeckCard) => void;
  onSkip?: (item: DeckCard) => void;
}) {
  const { width } = useWindowDimensions();
  const [at, setAt] = useState(0);
  const x = useRef(new Animated.Value(0)).current;
  /** Прошёл ли порог сейчас — чтобы щёлкнуть один раз, а не на каждом кадре. */
  const armed = useRef(0);

  const CARD_W = Math.min(320, width - 88);
  const FLY = width + CARD_W;

  /** Убрать верхнюю карту в сторону и показать следующую. */
  const decide = (dir: -1 | 1, item: DeckCard) => {
    if (dir < 0) hCommit();
    else hTap();
    Animated.timing(x, {
      toValue: dir * FLY,
      duration: 220,
      useNativeDriver: true,
    }).start(() => {
      // Позиция сбрасывается ПОСЛЕ смены карты: иначе улетевшая на миг вернулась бы в центр.
      x.setValue(0);
      armed.current = 0;
      if (dir < 0) onAdd(item);
      else onSkip?.(item);
      setAt((n) => n + 1);
    });
  };

  const pan = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dx) > 4 && Math.abs(g.dx) > Math.abs(g.dy),
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
        onPanResponderRelease: (_e, g) => {
          const item = items[at];
          const far = Math.abs(g.dx) > DECIDE;
          const flung = Math.abs(g.vx) > 0.6;
          if (item && (far || flung)) {
            decide(g.dx < 0 ? -1 : 1, item);
            return;
          }
          armed.current = 0;
          Animated.spring(x, {
            toValue: 0,
            useNativeDriver: true,
            damping: 18,
            stiffness: 220,
            mass: 0.8,
          }).start();
        },
        onPanResponderTerminate: () => {
          armed.current = 0;
          Animated.spring(x, { toValue: 0, useNativeDriver: true, damping: 18, stiffness: 220 }).start();
        },
      }),
    [at, items]
  );

  if (!items[at]) return null;

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
  const addOn = x.interpolate({ inputRange: [-DECIDE, -24, 0], outputRange: [1, 0, 0], extrapolate: 'clamp' });
  const skipOn = x.interpolate({ inputRange: [0, 24, DECIDE], outputRange: [0, 0, 1], extrapolate: 'clamp' });

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
              key={items[at].key + at}
              {...pan.panHandlers}
              style={[s.card, { width: CARD_W, transform: [{ translateX: x }, { rotate }] }]}
            >
              <Face item={items[at]} w={CARD_W} />

              {/* Метки решения проявляются по ходу движения — до отпускания видно, что случится. */}
              <Animated.View style={[s.mark, s.markAdd, { opacity: addOn }]}>
                <Text style={s.markAddText}>{STEP_HOBBIES.deckAdd()}</Text>
              </Animated.View>
              <Animated.View style={[s.mark, s.markSkip, { opacity: skipOn }]}>
                <Text style={s.markSkipText}>{STEP_HOBBIES.deckSkip()}</Text>
              </Animated.View>
            </Animated.View>
          ) : (
            <View
              key={items[at + d].key + (at + d)}
              pointerEvents="none"
              style={[
                s.card,
                {
                  width: CARD_W,
                  transform: [{ translateY: d * STEP_Y }, { scale: 1 - d * STEP_S }],
                },
              ]}
            >
              <Face item={items[at + d]} w={CARD_W} />
              {/*
                Нижние приглушены белой плёнкой, а не своим бледным градиентом: так у них остаётся
                собственный цвет — видно, что следующая карта про другое, — но спорить с верхней он
                уже не может.
              */}
              <View style={[s.veil, { opacity: 0.35 + d * 0.2 }]} pointerEvents="none" />
            </View>
          )
        )}

      <Text style={s.hint}>{STEP_HOBBIES.deckHint()}</Text>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  /** Высота с запасом: под стопкой ещё подсказка, а сами карты уходят вниз на DEPTH шагов. */
  wrap: { height: CARD_H + (DEPTH - 1) * STEP_Y + 40, alignSelf: 'center', marginTop: space.sm },
  card: {
    position: 'absolute',
    height: CARD_H,
    borderRadius: 28,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
    shadowColor: color.ink,
    shadowOpacity: 0.12,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 5,
  },
  sheen: {
    ...StyleSheet.absoluteFillObject,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF99',
    borderRadius: 28,
  },
  veil: { ...StyleSheet.absoluteFillObject, backgroundColor: color.card },
  emoji: { fontSize: 52, lineHeight: 60, marginBottom: space.sm },
  label: { ...type.display, fontSize: 21, lineHeight: 28, color: color.fg, textAlign: 'center' } as any,
  mark: {
    position: 'absolute',
    top: space.md,
    paddingHorizontal: 12,
    height: 28,
    borderRadius: rad.full,
    justifyContent: 'center',
  },
  markAdd: { left: space.md, backgroundColor: color.primary },
  markAddText: { ...type.labelSmall, color: color.onPrimary } as any,
  markSkip: { right: space.md, backgroundColor: '#FFFFFFE6' },
  markSkipText: { ...type.labelSmall, color: color.muted } as any,
  hint: {
    position: 'absolute',
    bottom: 0,
    alignSelf: 'center',
    ...type.fine,
    color: color.muted,
    textAlign: 'center',
  } as any,
});
