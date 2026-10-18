/**
 * Нити «жидкое стекло, сдержанно» для карты интересов (18.10.2026, выбор Ивана: «давай Б, только
 * чуть сдержаннее»; мокапы — design/threads-2026-10-18, вариант B2).
 *
 * КАК УСТРОЕНО И ПОЧЕМУ ДЁШЕВО.
 *   • Спокойные нити (к невыбранному) — тонкая почти прозрачная стеклянная линия: белая кромка и
 *     едва розовое тело под ней. Без капель на стыках — нить просто уходит под край пузыря.
 *   • Активная ветка (к теме, где что-то выбрано, и к выбранной карточке) — полнее и розовее:
 *     стеклянная трубка в три слоя (мягкое тело, розовый сердечник, белый блик) и «жидкие» стыки —
 *     радиальное пятно у капли и у пузыря вместо дорогого слияния фильтром (на Android размытие и
 *     порог в SVG — главная причина просадок).
 *   • Живое только у активной ветки и только в ответ на действие: она один раз мягко вспыхивает
 *     (~320 мс), когда тему открыли или выбрали карточку, и замирает. Остальное — статичный слой SVG.
 * Кривизна у каждой нити своя (от индекса) — поле не выглядит начерченным циркулем.
 */
import React, { useEffect, useRef } from 'react';
import { Animated, Easing } from 'react-native';
import Svg, { Defs, Ellipse, Path, RadialGradient, Stop } from 'react-native-svg';
import { threadPath } from '../mindmapLayout';

type Pt = { x: number; y: number };
export type ThreadTarget = Pt & { r: number; active: boolean; key: string };

const APath = Animated.createAnimatedComponent(Path);

export function GlassThreads({ width, height, hub, hubR, targets, live: liveProp = true, pulse }: {
  width: number; height: number; hub: Pt; hubR: number; targets: ThreadTarget[]; live?: boolean;
  /** Сменилось — блик один раз пробегает по активным веткам (открыли тему, выбрали карточку). */
  pulse?: string;
}) {
  /*
    БЕГУЩЕГО БЛИКА НЕТ (Иван, 18.10: «да» на «B2a без бегущего блика»). Замер на эмуляторе Android:
    бегущий блик по SVG давал 75–83% рывков. Вместо него — разовая мягкая вспышка активной ветки при
    открытии темы или выборе карточки: ~320 мс, и нить замирает. Разовая анимация дёшева везде.
  */
  const live = liveProp;
  const flash = useRef(new Animated.Value(0)).current;
  const anyActive = targets.some((t) => t.active);
  useEffect(() => {
    // Вспышка — один раз в ответ на действие: разгорелась и погасла за ~320 мс. Без действия — нет.
    if (!live || !anyActive || !pulse) { flash.setValue(0); return; }
    flash.setValue(0);
    const run = Animated.sequence([
      Animated.timing(flash, { toValue: 1, duration: 110, easing: Easing.out(Easing.quad), useNativeDriver: false }),
      Animated.timing(flash, { toValue: 0, duration: 210, easing: Easing.in(Easing.quad), useNativeDriver: false }),
    ]);
    run.start();
    return () => run.stop();
  }, [live, anyActive, pulse, flash]);

  const lines = targets.map((t, i) => {
    const bend = ((i % 3) - 1) * 0.07 + 0.06;
    // Нить заходит под пузырь и под каплю на 8 точек: темы парят (±4), а подложка статична — без
    // захода у краёв мигали бы щели. Стык при этом рисуется ровно на краю.
    const d = threadPath(hub, Math.max(0, hubR - 8), t, Math.max(0, t.r - 8), bend);
    const len = Math.hypot(t.x - hub.x, t.y - hub.y) * 1.06;
    // Конец нити у пузыря — для «жидкого» стыка.
    const L = Math.hypot(t.x - hub.x, t.y - hub.y) || 1;
    const ux = (t.x - hub.x) / L, uy = (t.y - hub.y) / L;
    const end = { x: t.x - ux * t.r, y: t.y - uy * t.r };
    const start = { x: hub.x + ux * hubR, y: hub.y + uy * hubR };
    return { ...t, d, len, end, start };
  });

  return (
    <Svg width={width} height={height} pointerEvents="none">
      <Defs>
        <RadialGradient id="gt-neck" cx="50%" cy="50%" rx="50%" ry="50%">
          <Stop offset="0" stopColor="#FF8FA8" stopOpacity={0.55} />
          <Stop offset="0.6" stopColor="#FF8FA8" stopOpacity={0.18} />
          <Stop offset="1" stopColor="#FF8FA8" stopOpacity={0} />
        </RadialGradient>
      </Defs>
      {/* Сначала спокойные — активные ложатся поверх. */}
      {lines.filter((l) => !l.active).map((l) => (
        <React.Fragment key={l.key}>
          <Path d={l.d} fill="none" stroke="#FF385C" strokeOpacity={0.08} strokeWidth={4} strokeLinecap="round" />
          <Path d={l.d} fill="none" stroke="#FFFFFF" strokeOpacity={0.55} strokeWidth={1.3} strokeLinecap="round" />
        </React.Fragment>
      ))}
      {lines.filter((l) => l.active).map((l) => (
        <React.Fragment key={l.key}>
          <Ellipse cx={l.start.x} cy={l.start.y} rx={9} ry={9} fill="url(#gt-neck)" />
          <Ellipse cx={l.end.x} cy={l.end.y} rx={9} ry={9} fill="url(#gt-neck)" />
          <Path d={l.d} fill="none" stroke="#FF385C" strokeOpacity={0.12} strokeWidth={9} strokeLinecap="round" />
          <Path d={l.d} fill="none" stroke="#FF7E9A" strokeOpacity={0.5} strokeWidth={4.5} strokeLinecap="round" />
          <Path d={l.d} fill="none" stroke="#FFFFFF" strokeOpacity={0.75} strokeWidth={1.1} strokeLinecap="round" />
          {live ? (
            <APath d={l.d} fill="none" stroke="#FF8FA8" strokeWidth={10} strokeLinecap="round"
                   strokeOpacity={flash.interpolate({ inputRange: [0, 1], outputRange: [0, 0.45] }) as any} />
          ) : null}
        </React.Fragment>
      ))}
    </Svg>
  );
}
