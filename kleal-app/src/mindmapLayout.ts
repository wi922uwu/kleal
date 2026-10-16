/**
 * РАСКЛАДКА КАРТЫ ИНТЕРЕСОВ — чистая геометрия, без React. Вынесена отдельно, чтобы её можно было
 * проверить на всех темах разом: пузыри не налезают друг на друга, на центр и за край поля.
 *
 * Обзор: восемь тем по эллипсу вокруг центра (там капля Kleal), первая — сверху, дальше по часовой.
 * Тема: сама тема в центре, её занятия — облаком вокруг. Размер пузыря занятия считается по
 * подписи: подпись обязана поместиться целиком, в одну-две строки. Раньше все пузыри темы были
 * одного размера, и «Предпринимательство» в круге 58 точек обрезалось многоточием.
 */

export type Pt = { x: number; y: number };
/**
 * `text` — подпись с переносом, уже поставленным между словами (`\n`), `lines` — сколько в ней
 * строк. Перенос ставится здесь, а не отдаётся тексту: получив две строки, iOS рвёт длинное
 * слово по буквам («Коктей / ли»), вместо того чтобы уменьшить кегль.
 */
export type LeafSpot = {
  key: string; label: string; text: string; lines: 1 | 2; x: number; y: number; d: number; font: number;
};

/** Пузырь темы и её подпись под ним. */
export const NODE_D = 64;
export const NODE_LABEL_H = 18;
/** Центр обзора — капля Kleal в стеклянном круге. */
export const HUB_D = 60;
/** Занятия: не меньше пальца с запасом, не больше, чем нужно самой длинной подписи. */
const LEAF_MIN = 58;
const LEAF_MAX = 92;
const LEAF_FLOOR = 52;
/** Внутренний отступ подписи от края пузыря — тот же, что в вёрстке (MindMap.tsx). */
export const LEAF_PAD = 6;
const GAP = 8;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));
/**
 * Ширина знака Geist Medium в долях кегля — с запасом на широкую кириллицу («Ш», «Ж», «М»).
 * По ней кегль подписи считается ЗДЕСЬ, а не подбирается текстом на телефоне: `adjustsFontSizeToFit`
 * в React Native на iOS при заданной высоте строки ненадёжен — то рвёт слово по буквам
 * («Программн / ое»), то ужимает подпись вдвое сильнее нужного.
 */
const EM = 0.62;
const CHAR_W = 12 * EM;
/** Мельче этого подпись не читается; если не влезает — растёт пузырь, а не мельчает текст. */
export const FONT_MIN = 10;
const FONT_MAX = 12;

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Восемь тем по эллипсу: запас по краям — под подпись снизу и спутники сверху. */
export function topicSpots(n: number, W: number, H: number): Pt[] {
  const cx = W / 2, cy = H / 2;
  const rx = W / 2 - 52;
  const ry = H / 2 - (NODE_D / 2 + NODE_LABEL_H + 10);
  return Array.from({ length: n }, (_, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return { x: cx + Math.cos(a) * rx, y: cy + Math.sin(a) * ry };
  });
}

const VOWELS = 'аеёиоуыэюяaeiouyáéíóúü';
const isVowel = (ch: string) => VOWELS.includes(ch.toLowerCase());
/** С этих букв строка не начинается: «ь», «ъ», «й» в начале переноса читаются ошибкой. */
const NO_START = 'ьъй';

/**
 * Перенос одного длинного слова по слогам: ближайшее к середине место вида «гласная | согласная +
 * гласная» (пред-при-ни|ма-тель-ство, entre-pre|neur-ship). Обе части не короче четырёх букв.
 * Не нашлось — слово остаётся целым, и его ужмёт кегль.
 */
export function hyphenate(word: string): [string, string] | null {
  const n = word.length;
  let best = -1;
  for (let i = 4; i <= n - 4; i++) {
    const a = word[i - 1], b = word[i], c = word[i + 1] || '';
    // После двух гласных подряд не рвём: «mountai-neering» читается ошибкой.
    if (isVowel(a) && !isVowel(word[i - 2]) && !isVowel(b) && !NO_START.includes(b.toLowerCase()) && isVowel(c)) {
      if (best < 0 || Math.abs(i - n / 2) < Math.abs(best - n / 2)) best = i;
    }
  }
  return best < 0 ? null : [word.slice(0, best), word.slice(best)];
}

/** Слово длиннее этого в одну строку пузыря не помещается читаемым кеглем. */
const LONG_WORD = 11;

/** Лучшая разбивка подписи на две строки: самая длинная строка — как можно короче. */
export function splitLabel(label: string): { longest: number; lines: 1 | 2; text: string } {
  const clean = label.trim();
  if (!/\s/.test(clean) && clean.length > LONG_WORD) {
    const h = hyphenate(clean);
    if (h) return { longest: Math.max(h[0].length + 1, h[1].length), lines: 2, text: `${h[0]}-\n${h[1]}` };
  }
  const words = clean.split(/\s+/);
  let longest = clean.length;
  let text = clean;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const m = Math.max(a.length, b.length);
    if (m < longest) { longest = m; text = `${a}\n${b}`; }
  }
  return { longest, lines: text === clean ? 1 : 2, text };
}

/** Диаметр, в который вписывается прямоугольник подписи при кегле `font`. */
function fitD(label: string, font: number): number {
  const { longest, lines } = splitLabel(label);
  const w = longest * font * EM + 2 * LEAF_PAD + 2;
  const h = lines * Math.round(font * 1.22) + 8;
  return Math.max(LEAF_MIN, Math.ceil(Math.sqrt(w * w + h * h)));
}

/** Расталкивание: пары пузырей, центр и края поля. Без случайности — раскладка всегда та же. */
function relax(pts: LeafSpot[], W: number, H: number, hub: Pt, hubR: number) {
  for (let pass = 0; pass < 400; pass++) {
    let moved = false;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i], b = pts[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d = Math.hypot(dx, dy);
        const need = (a.d + b.d) / 2 + GAP;
        if (d >= need) continue;
        if (d < 0.001) { dx = 1; dy = 0; d = 1; }
        const push = (need - d) / 2;
        a.x -= (dx / d) * push; a.y -= (dy / d) * push;
        b.x += (dx / d) * push; b.y += (dy / d) * push;
        moved = true;
      }
    }
    for (const p of pts) {
      // Центр неподвижен: тема стоит на месте, занятия его обходят.
      let dx = p.x - hub.x, dy = p.y - hub.y;
      let d = Math.hypot(dx, dy);
      const need = hubR + p.d / 2 + GAP;
      if (d < need) {
        if (d < 0.001) { dx = 0; dy = -1; d = 1; }
        p.x = hub.x + (dx / d) * need; p.y = hub.y + (dy / d) * need;
        moved = true;
      }
      p.x = clamp(p.x, p.d / 2 + 2, W - p.d / 2 - 2);
      p.y = clamp(p.y, p.d / 2 + 2, H - p.d / 2 - 2);
    }
    if (!moved) break;
  }
}

/**
 * Занятия темы вокруг центра. Порядок данных сохраняется (сначала самое частое — ближе к центру),
 * размеры — по подписям; если всё вместе не помещается в поле, все пузыри уменьшаются в одной
 * пропорции, а кегль подписи — вместе с ними.
 */
/** Наибольшее перекрытие пар после раскладки (в точках); ≤ 0.5 — пузыри не налезают. */
function worstOverlap(pts: LeafSpot[]): number {
  let worst = 0;
  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      const o = (pts[i].d + pts[j].d) / 2 - Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y);
      if (o > worst) worst = o;
    }
  }
  return worst;
}

/** Расставить пузыри заданных размеров: золотая спираль вокруг центра, потом расталкивание. */
function place(list: { key: string; label: string }[], ds: number[], font: number, W: number, H: number): LeafSpot[] {
  const hub = { x: W / 2, y: H / 2 };
  const hubR = NODE_D / 2;
  const pts: LeafSpot[] = list.map((b, i) => {
    const sp = splitLabel(b.label);
    const d = ds[i];
    const a = -Math.PI / 2 + i * GOLDEN;
    const t = Math.sqrt((i + 0.5) / list.length);
    const r0 = hubR + d / 2 + GAP;
    const rx = r0 + t * (W / 2 - d / 2 - 2 - r0);
    const ry = r0 + t * (H / 2 - d / 2 - 2 - r0);
    return {
      key: b.key, label: b.label, text: sp.text, lines: sp.lines, d, font,
      x: hub.x + Math.cos(a) * rx, y: hub.y + Math.sin(a) * ry,
    };
  });
  relax(pts, W, H, hub, hubR);
  return pts;
}

/**
 * Занятия темы вокруг центра. ОДИН КЕГЛЬ НА ВСЮ ТЕМУ: подписи разного размера в одном облаке
 * читаются неряшливо. Кегли пробуются от 12 вниз, и для каждого облако расставляется ПО-НАСТОЯЩЕМУ;
 * берётся самый крупный, при котором ни один пузырь не налез на другой. Оценка «по площади» здесь
 * была и ошибалась: в самой плотной теме площадь сходилась, а пузыри — нет.
 */
export function leafSpots(list: { key: string; label: string }[], W: number, H: number): LeafSpot[] {
  if (!list.length) return [];
  let best: LeafSpot[] = [];
  for (let f = FONT_MAX; f >= FONT_MIN; f -= 0.5) {
    best = place(list, list.map((b) => fitD(b.label, f)), f, W, H);
    if (worstOverlap(best) <= 0.5) return best;
  }
  return best;
}

/**
 * Нить от центра к пузырю: от кромки до кромки, с лёгким изгибом по часовой — прямые спицы
 * читались бы схемой, изогнутые — картой.
 */
export function threadPath(from: Pt, fromR: number, to: Pt, toR: number, bend = 0.12): string {
  const dx = to.x - from.x, dy = to.y - from.y;
  const L = Math.hypot(dx, dy) || 1;
  const ux = dx / L, uy = dy / L;
  const sx = from.x + ux * fromR, sy = from.y + uy * fromR;
  const ex = to.x - ux * toR, ey = to.y - uy * toR;
  const mx = (sx + ex) / 2 - uy * L * bend, my = (sy + ey) / 2 + ux * L * bend;
  const f = (v: number) => v.toFixed(1);
  return `M${f(sx)} ${f(sy)} Q${f(mx)} ${f(my)} ${f(ex)} ${f(ey)}`;
}

/** Сколько занятий темы видно разом: облако дышит, а не набито. */
export const PAGE = 10;
/** Выбранных в подборке — не больше этого; остальные выбранные видны в корзине под картой. */
const KEEP_MAX = 21;

/**
 * Следующая подборка темы. ВЫБРАННЫЕ ОСТАЮТСЯ, остальные места занимают следующие по очереди —
 * по кругу, начиная со `start`. `avoid` — то, что только что было на экране: обновление обязано
 * показать другое, если в теме есть из чего выбирать. Свежих — не меньше трёх, даже если выбрано
 * много: иначе кнопка «другие» перестала бы что-либо менять.
 */
export function nextPage(pool: string[], keep: string[], start: number, avoid: string[] = []): { keys: string[]; next: number } {
  const n = pool.length;
  const kept = keep.slice(0, KEEP_MAX);
  const want = Math.min(n, Math.max(PAGE, kept.length + 3));
  const out = [...kept];
  let i = n ? ((start % n) + n) % n : 0;
  for (const allowAvoided of [false, true]) {
    for (let scanned = 0; scanned < n && out.length < want; scanned++) {
      const k = pool[i];
      i = (i + 1) % n;
      if (out.includes(k) || (!allowAvoided && avoid.includes(k))) continue;
      out.push(k);
    }
  }
  return { keys: out, next: i };
}
