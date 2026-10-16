/**
 * Интересы v2 — двойная спираль (владелец, 27.09: «спираль по типу ДНК, которую можно листать»).
 * v1 — карта пузырей MindMap — остаётся как есть и включается переключателем на шаге.
 *
 * ГЕОМЕТРИЯ ОТДЕЛЬНО ОТ ЭКРАНА, чтобы её можно было проверить без телефона (tools/helix_test.js):
 * пузыри не налезают друг на друга ни при каком повороте и не выходят за край поля.
 *
 * КАК УСТРОЕНО. Две нити крутятся вокруг вертикальной оси. Занятия нанизаны по очереди на обе:
 * чётное — на нить A, нечётное — на нить B на полшага ниже. Полшага — это и есть «малая бороздка»
 * настоящей ДНК, и ровно она разводит пузыри по высоте там, где нити пересекаются: без неё два
 * пузыря в точке пересечения ложились бы один на другой.
 *
 * Угол точки — её высота в ленте плюс поворот спирали φ. Глубина — косинус угла: задний пузырь
 * меньше и с приглушённой подписью, передний крупный.
 *
 * ВРАЩЕНИЕ БЕЗ ПЕРЕСЧЁТА НИТЕЙ (владелец, 27.09: «это лагает», потом «она должна крутиться по
 * оси»). Поворот спирали вокруг её оси на φ — это ровно сдвиг её рисунка вдоль оси на φ/K:
 * sin(yK + φ) = sin((y + φ/K)K). Поэтому нити нарисованы ОДИН раз, а вращение — нативный сдвиг
 * этого слоя по вертикали (по модулю витка TURN). Кривые на кадр не пересчитываются вовсе; на
 * кадр двигаются только пузыри — вбок, вслед за своей нитью.
 */

/**
 * Шаг ступени: пузырь нити A, через полшага — нити B. 76 — с воздухом: в поле ~400 десять
 * пузырей, а не тринадцать («очень тесно», владелец 27.09); между соседями по высоте 38.
 */
export const STEP = 76;
/** Место под заголовок темы в ленте. */
export const HEAD = 84;
/** Высота пузыря и предел его ширины: «Сходить на матч» и «Настольный теннис» влезают целиком. */
export const PILL_H = 34;
export const PILL_MAX_W = 180;
/**
 * Полный оборот нити — 380 точек ленты, это пять ступеней, десять пузырей: у настоящей ДНК
 * на виток приходится 10,5 пары оснований. В поле ~400 виден ровно виток.
 */
export const TURN = 380;
export const K = (2 * Math.PI) / TURN;
/** Доля прокрутки, которая идёт в поворот: листаешь — спираль ещё и проворачивается. */
export const TWIST = 0.6;
/** Крайний пузырь сзади: во столько раз меньше. */
export const BACK_SCALE = 0.84;
export const TOP_PAD = 24;

export type HelixItem =
  | { kind: 'head'; topic: string; label: string; y: number }
  | { kind: 'leaf'; key: string; label: string; topic: string; strand: 0 | 1; y: number };

/**
 * Лента: тема за темой, в каждой — заголовок и её занятия парами на две нити. `y` — центр
 * элемента в координатах ленты. Возвращает ещё высоту ленты и начало каждой темы (для перехода
 * по ряду тем).
 */
export function layoutHelix(
  roots: Array<{ key: string; label: string }>,
  leaves: Record<string, Array<{ key: string; label: string }>>,
): { items: HelixItem[]; height: number; topicY: Record<string, number> } {
  const items: HelixItem[] = [];
  const topicY: Record<string, number> = {};
  const seen = new Set<string>();
  let y = TOP_PAD;
  for (const r of roots) {
    topicY[r.key] = y;
    items.push({ kind: 'head', topic: r.key, label: r.label, y: y + HEAD / 2 });
    y += HEAD;
    let j = 0;
    for (const l of leaves[r.key] || []) {
      if (seen.has(l.key)) continue; // одно занятие — один пузырь, даже если дерево повторяет ключ
      seen.add(l.key);
      const strand = (j % 2) as 0 | 1;
      const rung = Math.floor(j / 2);
      items.push({ kind: 'leaf', key: l.key, label: l.label, topic: r.key, strand, y: y + rung * STEP + strand * (STEP / 2) + STEP / 4 });
      j++;
    }
    y += Math.ceil(j / 2) * STEP + STEP / 2;
  }
  return { items, height: y + TOP_PAD, topicY };
}

/** Угол точки ленты на высоте `y` при прокрутке `scroll` и нити `strand`. */
export function angle(y: number, scroll: number, strand: number, spin = 0): number {
  'worklet';
  return y * K + scroll * K * TWIST + strand * Math.PI + spin;
}

/** Размах не «дышит» (0): дыхание читалось как эффект ради эффекта. Оставлено для теста. */
export const BREATH = 0;

/** Размах нити: пузырь шириной до PILL_MAX_W не выходит за край поля шириной `w` даже на вдохе. */
export function amplitude(w: number): number {
  'worklet';
  return Math.max(40, Math.min(96, (w / 2 - PILL_MAX_W / 2 - 6) / (1 + BREATH)));
}

/** Глубина 0..1: 1 — пузырь спереди, 0 — сзади. */
export function depth(theta: number): number {
  'worklet';
  return (Math.cos(theta) + 1) / 2;
}

export function scaleAt(theta: number): number {
  'worklet';
  return BACK_SCALE + (1 - BACK_SCALE) * depth(theta);
}

/** Задний пузырь бледнее, но читается: при 0,38 серая подпись на светлом почти пропадала. */
export function opacityAt(theta: number): number {
  'worklet';
  return 0.55 + 0.45 * depth(theta);
}

/** Ширина пузыря по подписи (Geist 500, 14; у выбранного слева галочка) — оценка для проверки. */
export function pillWidth(label: string): number {
  return Math.min(PILL_MAX_W, 50 + label.length * 8);
}
