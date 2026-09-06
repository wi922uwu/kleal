/**
 * Бегущие строки эмодзи с «рыбьим глазом» — фон экрана входа (A.03).
 *
 * ЭФФЕКТ ЛИНЗЫ БЕЗ ШЕЙДЕРА. Настоящее искажение картинки требует шейдера, которого в Expo Go нет:
 * любой такой модуль — нативный код, а он закрывает возможность открывать приложение по QR (см.
 * AGENTS.md). Поэтому линза собрана из самих символов: каждый эмодзи масштабируется по тому,
 * НАСКОЛЬКО ОН СЕЙЧАС БЛИЗОК К ЦЕНТРУ ЭКРАНА. В центре крупнее и чуть приподнят, к краям мельче и
 * бледнее. На ряду отдельных знаков это читается ровно как выпуклое стекло, а стоит столько же,
 * сколько обычный перенос.
 *
 * ПОЧЕМУ МАСШТАБ СЧИТАЕТСЯ ОТ СДВИГА ЛЕНТЫ, А НЕ ОТ ПОЗИЦИИ. Позицию во время анимации знает
 * только UI-поток; спрашивать её из JS значило бы гнать кадры через мост и потерять плавность.
 * Но положение каждого знака — это его место в ленте плюс общий сдвиг, то есть линейная функция
 * одного и того же значения. Поэтому масштаб выражен интерполяцией ТОГО ЖЕ сдвига: у каждого
 * знака свой диапазон, вершина которого приходится на момент, когда он оказывается по центру.
 * Всё живёт на нативном драйвере, JS во время движения не участвует вовсе.
 *
 * ЛЕНТА ЗАКОЛЬЦОВАНА ДУБЛИРОВАНИЕМ. Содержимое строки выложено дважды подряд, а сдвиг идёт ровно
 * на длину одной копии — в момент возврата на экране стоит точно такая же картинка, и шва не
 * видно. Одной копии не хватило бы: на возврате лента прыгала бы с пустого края.
 */
import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

/** Шаг между знаками и их базовый размер — от них зависит, сколько знаков влезает в экран. */
const STEP = 52;
const SIZE = 32;
/** Насколько знак вырастает в центре и ужимается у края. */
const SCALE_MID = 1.34;
const SCALE_EDGE = 0.52;
/** Подъём в центре — линза не только увеличивает, но и «выдавливает» середину вперёд. */
const LIFT = 7;
/** Секунд на полный оборот одной строки. Соседние строки идут вразнобой, см. `speeds`. */
const PERIOD_S = 26;

function Row({
  chars,
  reverse,
  seconds,
  offset,
}: {
  chars: string[];
  /** Строка едет вправо, а не влево — соседние строки должны расходиться. */
  reverse?: boolean;
  seconds: number;
  /** Сдвиг стартовой фазы, чтобы строки не выстраивались столбиками. */
  offset: number;
}) {
  const { width } = useWindowDimensions();
  const t = useRef(new Animated.Value(0)).current;

  // Одна копия — столько знаков, чтобы с запасом перекрыть экран: иначе на возврате виден край.
  const per = Math.max(chars.length, Math.ceil(width / STEP) + 2);
  const one = useMemo(
    () => Array.from({ length: per }, (_, k) => chars[k % chars.length]),
    [chars, per]
  );
  const period = per * STEP;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.timing(t, {
        toValue: 1,
        duration: seconds * 1000,
        easing: Easing.linear,       // бегущая строка не разгоняется и не тормозит
        useNativeDriver: true,
      })
    );
    loop.start();
    return () => loop.stop();
  }, [t, seconds]);

  // Сдвиг ленты: влево — от 0 до -period, вправо — наоборот.
  const shift = t.interpolate({
    inputRange: [0, 1],
    outputRange: reverse ? [-period, 0] : [0, -period],
  });

  return (
    <View style={s.row} pointerEvents="none">
      {/* Отступ фазы — НАСТОЯЩИЙ отступ разметки: он же участвует в расчёте вершины ниже. */}
      <Animated.View style={[s.strip, { paddingLeft: offset, transform: [{ translateX: shift }] }]}>
        {[...one, ...one].map((ch, j) => {
          /*
            Середина знака на экране = отступ + его место в ленте + половина шага + общий сдвиг.
            Вершина линзы — тот сдвиг, при котором эта середина совпадает с серединой экрана.
            Первая версия вычитала отсюда ещё половину разницы длины ленты и экрана — величину,
            которой в разметке нет вовсе; из-за неё горб уезжал вправо от центра.
          */
          const peak = width / 2 - offset - j * STEP - STEP / 2;
          const range = [peak - width / 2, peak, peak + width / 2];
          const scale = shift.interpolate({
            inputRange: range,
            outputRange: [SCALE_EDGE, SCALE_MID, SCALE_EDGE],
            extrapolate: 'clamp',
          });
          const lift = shift.interpolate({
            inputRange: range,
            outputRange: [0, -LIFT, 0],
            extrapolate: 'clamp',
          });
          const opacity = shift.interpolate({
            inputRange: range,
            outputRange: [0.45, 1, 0.45],
            extrapolate: 'clamp',
          });
          return (
            <Animated.Text
              key={j}
              style={[s.ch, { opacity, transform: [{ translateY: lift }, { scale }] }]}
            >
              {ch}
            </Animated.Text>
          );
        })}
      </Animated.View>
    </View>
  );
}

export function EmojiTicker({ rows }: { rows: string[] }) {
  /**
   * Скорости и направления НЕ одинаковые: одинаковые строки едут строем, и вместо живого поля
   * получается одна широкая полоса. Числа простые и не кратные друг другу — рисунок не повторяется
   * заметно долго.
   */
  const speeds = [1, 1.32, 0.86, 1.18, 0.94];
  return (
    <View style={s.wrap} pointerEvents="none">
      {rows.map((row, n) => (
        <Row
          key={n}
          chars={row.split(/\s+/).filter(Boolean)}
          reverse={n % 2 === 1}
          seconds={PERIOD_S * speeds[n % speeds.length]}
          offset={n * 17}
        />
      ))}
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { ...StyleSheet.absoluteFill, justifyContent: 'center', gap: 10 },
  row: { height: SIZE + 10, justifyContent: 'center', overflow: 'visible' },
  strip: { flexDirection: 'row', alignItems: 'center' },
  ch: { width: STEP, fontSize: SIZE, lineHeight: SIZE + 6, textAlign: 'center' },
});
