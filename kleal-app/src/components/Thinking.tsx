/**
 * Ожидание ответа агента: три дышащие точки и строка о том, что сейчас происходит.
 *
 * ЗАЧЕМ ВМЕСТО ВЕРТУШКИ. Вертушка говорит «идёт работа» и больше ничего: она одинаковая и на
 * полсекунды, и на двадцать. А ждать тут приходится именно долго — модель собирает затею целиком,
 * — и всё это время экран пуст. Пустая пауза читается как «зависло», и человек начинает нажимать
 * заново.
 *
 * ТОЧКИ ДЫШАТ ВРАЗНОБОЙ. Три одинаково мигающих точки — тот же метроном, что и вертушка. Здесь у
 * каждой своя задержка, поэтому волна идёт слева направо: движение с направлением читается как
 * работа, а не как индикатор.
 *
 * СТРОКА МЕНЯЕТСЯ ДВАЖДЫ И ОСТАНАВЛИВАЕТСЯ. «Слушаю» — «Собираю» — «Почти». Дальше она не
 * крутится по кругу: вернувшееся начало означало бы, что всё началось заново, а это неправда.
 * Последняя фраза намеренно без обещания срока — обещать секунду и не уложиться хуже, чем молчать.
 *
 * Дыхание — на нативном драйвере; в JS остаются только два таймера на смену слова, по одному
 * срабатыванию каждый.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { THINKING } from '../buddy';
import { color, space, type } from '../theme';

/** Через сколько сменяется фраза. Вторая позже первой: к этому времени короткие ответы уже пришли. */
const STEP_MS = [2400, 6000];
/** Сдвиг фазы между точками — из него и получается бегущая волна. */
const SHIFT = 150;

export function Thinking() {
  const dots = useRef([0, 1, 2].map(() => new Animated.Value(0))).current;
  const fade = useRef(new Animated.Value(1)).current;
  const [step, setStep] = useState(0);

  useEffect(() => {
    const loops = dots.map((v, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * SHIFT),
          Animated.timing(v, { toValue: 1, duration: 360, useNativeDriver: true }),
          Animated.timing(v, { toValue: 0, duration: 360, useNativeDriver: true }),
          // Хвост паузы дополняет задержку до общей длины: иначе точки постепенно разъезжаются.
          Animated.delay((dots.length - 1 - i) * SHIFT),
        ])
      )
    );
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, [dots]);

  useEffect(() => {
    const timers = STEP_MS.map((ms, i) =>
      setTimeout(() => {
        // Слово не подменяется резко: гаснет, меняется, проявляется.
        Animated.sequence([
          Animated.timing(fade, { toValue: 0, duration: 160, useNativeDriver: true }),
          Animated.timing(fade, { toValue: 1, duration: 220, useNativeDriver: true }),
        ]).start();
        setTimeout(() => setStep(i + 1), 160);
      }, ms)
    );
    return () => timers.forEach(clearTimeout);
  }, [fade]);

  const words = THINKING();
  return (
    <View style={s.wrap} accessibilityRole="progressbar" accessibilityLabel={words[step]}>
      <View style={s.dots}>
        {dots.map((v, i) => (
          <Animated.View
            key={i}
            style={[
              s.dot,
              {
                opacity: v.interpolate({ inputRange: [0, 1], outputRange: [0.3, 1] }),
                transform: [
                  { translateY: v.interpolate({ inputRange: [0, 1], outputRange: [0, -5] }) },
                ],
              },
            ]}
          />
        ))}
      </View>
      <Animated.Text style={[s.word, { opacity: fade }]}>{words[step]}</Animated.Text>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'center', gap: space.md, marginTop: space.md },
  dots: { flexDirection: 'row', alignItems: 'center', gap: 6, height: 16 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: color.primary },
  word: { ...type.bodySmall, color: color.muted } as any,
});
