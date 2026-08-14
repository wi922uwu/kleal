/**
 * ОТВЕТ МОДЕЛИ — ДОКУМЕНТОМ, А НЕ РЕПЛИКОЙ В ПУЗЫРЕ.
 *
 * Зачем это вообще. Ответ Бадди рисовался одним `<Text>` внутри пузыря — тем же, в котором
 * человек пишет «привет». Пока модель отвечала одной фразой, это работало. Но она отвечает
 * разбором: заголовки, списки, таблица, сравнение вариантов. В пузыре всё это схлопывалось в
 * сплошной абзац со звёздочками и решётками, которые человек читал как мусор, — то есть разметка
 * не просто не рисовалась, она МЕШАЛА.
 *
 * АСИММЕТРИЯ — ЭТО СОДЕРЖАНИЕ, А НЕ УКРАШЕНИЕ. Реплика человека остаётся пузырём справа, ответ
 * модели становится страницей во всю ширину. Так устроены все большие модели, и не из моды:
 * пузырь означает «сказал», страница — «написал». Уравняв их, экран сообщает, что ответ такая же
 * проходная реплика, как «ок», — и человек читает его так же бегло.
 *
 * ПОЧЕМУ СВОЙ РАЗБОР, А НЕ БИБЛИОТЕКА. Проект живёт на SDK 54 ради Expo Go (см. AGENTS.md), и
 * каждая зависимость — риск уронить его. Здесь нужен НЕ полный markdown, а тот его кусок, который
 * модель действительно печатает: заголовки, списки, врезки, таблицы, жирный, код. Сотня строк
 * своего разбора дешевле и предсказуемее, чем чужой парсер со своими краевыми случаями.
 *
 * ГЛАВНАЯ ЛОВУШКА — ТАБЛИЦА НА 390 ТОЧКАХ. Широкая таблица обязана прокручиваться ВНУТРИ себя;
 * иначе она растягивает страницу, и горизонтально начинает ездить весь разговор. Это ломает не
 * таблицу, а экран — и ломает молча: на коротких таблицах не заметно.
 *
 * ЧЕГО ЗДЕСЬ НАМЕРЕННО НЕТ. Вложенных списков глубже одного уровня, картинок, HTML. Модель их
 * почти не печатает, а поддержка каждого — это ещё один способ отрисовать мусор вместо текста.
 * Неузнанная строка становится обычным абзацем: показать текст как есть всегда лучше, чем съесть.
 */
import React from 'react';
import { View, Text, ScrollView, StyleSheet, Animated } from 'react-native';
import { color, radius as rad, space, type } from '../theme';

// ---------------------------------------------------------------- разбор

type Inline = { text: string; bold?: boolean; italic?: boolean; code?: boolean };

type Block =
  | { kind: 'h'; level: 1 | 2 | 3; text: string }
  | { kind: 'p'; text: string }
  | { kind: 'quote'; lines: string[] }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'table'; head: string[]; rows: string[][] }
  | { kind: 'code'; text: string }
  | { kind: 'hr' };

const RE_H = /^(#{1,6})\s+(.*)$/;
const RE_UL = /^[-*•]\s+(.*)$/;
const RE_OL = /^\d+[.)]\s+(.*)$/;
const RE_QUOTE = /^>\s?(.*)$/;
const RE_HR = /^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/;
const RE_ROW = /^\s*\|(.+)\|\s*$/;
const RE_SEP = /^\s*\|?[\s:|-]+\|[\s:|-]*$/;

function cells(line: string): string[] {
  const m = line.match(RE_ROW);
  return (m ? m[1] : line).split('|').map((c) => c.trim());
}

/** Строки -> блоки. Ничего не выбрасывается: непонятое становится абзацем. */
export function parseBlocks(src: string): Block[] {
  const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n');
  const out: Block[] = [];
  let para: string[] = [];

  const flush = () => {
    if (para.length) {
      out.push({ kind: 'p', text: para.join(' ').trim() });
      para = [];
    }
  };

  // Маркер блока ищется по строке БЕЗ ведущих пробелов.
  //
  // Модель печатает «\n > Фьючерс — это…» — с пробелом перед «>», и это не сбой, а обычное
  // markdown-оформление (спецификация разрешает до трёх пробелов отступа). Разбор требовал маркер
  // с нулевой позиции, поэтому такая строка становилась обычным абзацем и приклеивалась к
  // предыдущему — человек видел «…определённой цене. > Фьючерс — это контракт…», то есть
  // палку посреди предложения. Снято с телефона 14 августа.
  const at = (k: number) => (lines[k] ?? '').trim();

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trim();

    if (!line) { flush(); continue; }

    // Код — первым: внутри него разметки нет вовсе, иначе решётка станет заголовком.
    if (/^\s*```/.test(line)) {
      flush();
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) { body.push(lines[i]); i++; }
      out.push({ kind: 'code', text: body.join('\n') });
      continue;
    }

    if (RE_HR.test(line)) { flush(); out.push({ kind: 'hr' }); continue; }

    const h = line.match(RE_H);
    if (h) {
      flush();
      // Глубже третьего уровня на телефоне неразличимо — всё сводится к третьему.
      out.push({ kind: 'h', level: Math.min(3, h[1].length) as 1 | 2 | 3, text: h[2].trim() });
      continue;
    }

    // Таблица опознаётся ТОЛЬКО по строке-разделителю под шапкой. Без неё «|» — это просто
    // палка в тексте, и одна такая строка превращала абзац в однорядную таблицу.
    if (RE_ROW.test(line) && i + 1 < lines.length && RE_SEP.test(at(i + 1))) {
      flush();
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && RE_ROW.test(at(i))) { rows.push(cells(at(i))); i++; }
      i--;
      out.push({ kind: 'table', head, rows });
      continue;
    }

    const q = line.match(RE_QUOTE);
    if (q) {
      flush();
      const body = [q[1]];
      while (i + 1 < lines.length && RE_QUOTE.test(at(i + 1))) {
        body.push((at(i + 1).match(RE_QUOTE) as RegExpMatchArray)[1]);
        i++;
      }
      out.push({ kind: 'quote', lines: body });
      continue;
    }

    const ul = line.match(RE_UL);
    if (ul) {
      flush();
      const items = [ul[1]];
      while (i + 1 < lines.length && RE_UL.test(at(i + 1))) {
        items.push((at(i + 1).match(RE_UL) as RegExpMatchArray)[1]);
        i++;
      }
      out.push({ kind: 'ul', items });
      continue;
    }

    const ol = line.match(RE_OL);
    if (ol) {
      flush();
      const items = [ol[1]];
      while (i + 1 < lines.length && RE_OL.test(at(i + 1))) {
        items.push((at(i + 1).match(RE_OL) as RegExpMatchArray)[1]);
        i++;
      }
      out.push({ kind: 'ol', items });
      continue;
    }

    para.push(line);
  }
  flush();
  return out;
}

/**
 * Строчная разметка: **жирный**, *курсив*, `код`.
 *
 * Разбор идёт по САМОМУ РАННЕМУ совпадению, а не по очереди правил: иначе `**a** *b*` находило
 * бы курсив внутри жирного и рвало строку пополам. Незакрытая звёздочка остаётся звёздочкой —
 * съесть её значило бы потерять символ, который человек, возможно, и написал.
 */
export function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  let rest = String(src || '');
  const RULES: [RegExp, Partial<Inline>][] = [
    [/\*\*([^*]+)\*\*/, { bold: true }],
    [/__([^_]+)__/, { bold: true }],
    [/`([^`]+)`/, { code: true }],
    // Без ретроспективных проверок (?<!...) намеренно: Hermes на них спотыкался, а падение
    // регулярки — это падение всего модуля при загрузке, а не кривой курсив.
    // Их роль берёт на себя порядок: жирный проверяется РАНЬШЕ и на «**a**» совпадает с нулевой
    // позиции, тогда как курсив там же совпасть не может и находится только правее.
    [/\*([^*\n]+)\*/, { italic: true }],
    [/_([^_\n]+)_/, { italic: true }],
    // Ссылка показывается ТЕКСТОМ: адрес в разговоре — это шум, а нажимать в ответе модели пока
    // некуда, и подчёркнутый нерабочий текст обманывал бы сильнее, чем его отсутствие.
    [/\[([^\]]+)\]\((?:[^)]*)\)/, {}],
  ];

  let guard = 0;
  while (rest && guard++ < 400) {
    let bestAt = -1;
    let bestM: RegExpMatchArray | null = null;
    let bestStyle: Partial<Inline> = {};
    for (const [re, style] of RULES) {
      const m = rest.match(re);
      if (m && m.index !== undefined && (bestAt < 0 || m.index < bestAt)) {
        bestAt = m.index; bestM = m; bestStyle = style;
      }
    }
    if (!bestM || bestAt < 0) break;
    if (bestAt > 0) out.push({ text: rest.slice(0, bestAt) });
    out.push({ text: bestM[1], ...bestStyle });
    rest = rest.slice(bestAt + bestM[0].length);
  }
  if (rest) out.push({ text: rest });
  return out.length ? out : [{ text: String(src || '') }];
}

// ---------------------------------------------------------------- вид

function Rich({ src, style, tail, fade }: {
  src: string; style?: any; tail?: React.ReactNode; fade?: boolean;
}) {
  const parts = parseInline(src);
  return (
    <Text style={style}>
      {parts.map((t, i) => (
        <Text
          key={i}
          style={[
            t.bold ? s.bold : null,
            t.italic ? s.italic : null,
            t.code ? s.codeInline : null,
          ]}
        >
          {/* Гаснет только САМЫЙ конец последнего куска — там, где сейчас пишут. */}
          {fade && i === parts.length - 1 && !t.code
            ? fadeTail(t.text, true).map((p, j) => (
                <Text key={j} style={p.o < 1 ? { opacity: p.o } : null}>{p.t}</Text>
              ))
            : t.text}
        </Text>
      ))}
      {/* Курсор — ВНУТРИ той же строки, а не под ней. Отдельной строкой он читался как
          посторонний элемент, а не как место, где сейчас пишут (сообщено с телефона). */}
      {tail}
    </Text>
  );
}

/**
 * ГАСНУЩИЙ ХВОСТ — «размытие» на конце строки, пока идёт печать.
 *
 * Настоящее размытие текста в React Native стоит нативного модуля и маски; здесь оно не нужно.
 * Тот же эффект даёт градиент прозрачности по последним символам: буквы не выскакивают, а
 * проявляются, и граница написанного перестаёт быть резкой.
 *
 * Ступеней три и они короткие: длинный градиент читается как «текст выцвел», а не как «текст
 * ещё пишется».
 */
const FADE = [0.72, 0.42, 0.18];

function fadeTail(text: string, on: boolean) {
  if (!on || text.length < 4) return [{ t: text, o: 1 }];
  const n = Math.min(6, Math.max(3, Math.round(text.length * 0.12)));
  const head = text.slice(0, text.length - n);
  const tailChars = text.slice(text.length - n);
  const per = Math.ceil(n / FADE.length);
  const parts: { t: string; o: number }[] = head ? [{ t: head, o: 1 }] : [];
  for (let i = 0; i < FADE.length; i++) {
    const piece = tailChars.slice(i * per, (i + 1) * per);
    if (piece) parts.push({ t: piece, o: FADE[i] });
  }
  return parts;
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  const n = Math.max(head.length, ...rows.map((r) => r.length), 1);
  const col = (r: string[], i: number) => r[i] ?? '';
  return (
    // Прокрутка ВНУТРИ таблицы. Без неё широкая таблица растягивает страницу, и горизонтально
    // начинает ездить весь разговор — ломается не таблица, а экран.
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.tableWrap}
                contentContainerStyle={s.tableInner}>
      <View>
        <View style={[s.tr, s.trHead]}>
          {Array.from({ length: n }, (_, i) => (
            <Rich key={i} src={col(head, i)} style={[s.td, s.th]} />
          ))}
        </View>
        {rows.map((r, ri) => (
          <View key={ri} style={[s.tr, ri === rows.length - 1 && s.trLast]}>
            {Array.from({ length: n }, (_, i) => (
              <Rich key={i} src={col(r, i)} style={s.td} />
            ))}
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

/**
 * Мигающий курсор — знак «ещё пишется».
 *
 * Стоит ОТДЕЛЬНОЙ строкой под текстом, а не приклеен к последнему слову: приклеенный он ездил бы
 * вместе с переносами строк и прыгал бы на каждом кадре. Здесь он спокойно мигает на месте, и
 * этого достаточно, чтобы отличить «пишет» от «закончил».
 */
function Caret() {
  const a = React.useRef(new Animated.Value(1)).current;
  React.useEffect(() => {
    // Плавно и НЕ до нуля: жёсткое мигание с постоянным шагом — то же механическое ощущение,
    // что и ровная выдача букв. Гаснет до трети, разгорается дольше, чем гаснет: так пульс
    // читается как дыхание, а не как индикатор загрузки.
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(a, { toValue: 0.3, duration: 620, useNativeDriver: true }),
      Animated.timing(a, { toValue: 1, duration: 380, useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [a]);
  // ЗНАК, а не прямоугольник. Прямоугольник — это View, а View внутри строки текста в React
  // Native встать не может: он всегда уезжает на строку ниже. Символ же течёт вместе с текстом
  // и переносится вместе с ним.
  return <Animated.Text style={[s.caret, { opacity: a }]}>▍</Animated.Text>;
}

/** Ответ модели, свёрстанный документом. `text` — то, что она напечатала, как есть. */
export default function Markdown({ text, caret }: { text: string; caret?: boolean }) {
  const blocks = React.useMemo(() => parseBlocks(text), [text]);
  return (
    <View style={s.doc}>
      {blocks.map((b, i) => {
        // Курсор рисуется в последнем блоке — там, где сейчас пишут. Если последний блок не
        // текстовый (таблица, код), внутрь его не поставить, и тогда он идёт отдельной строкой:
        // это редкий случай и он честнее, чем курсор посреди таблицы.
        const tail = caret && i === blocks.length - 1 ? <Caret /> : null;
        const fade = !!tail;
        // Отбивка сверху у заголовка больше, чем снизу: заголовок принадлежит тому, что под ним.
        // Равные отступы — самая частая причина, по которой длинный текст читается кашей.
        const first = i === 0;
        switch (b.kind) {
          case 'h':
            return (
              <Rich key={i} src={b.text} tail={tail} fade={fade}
                    style={[
                      b.level === 1 ? s.h1 : b.level === 2 ? s.h2 : s.h3,
                      first && { marginTop: 0 },
                    ]} />
            );
          case 'p':
            return <Rich key={i} src={b.text} style={s.p} tail={tail} fade={fade} />;
          case 'quote':
            return (
              <View key={i} style={s.quote}>
                {b.lines.map((l, j) => (
                  <Rich key={j} src={l} style={s.quoteText}
                        tail={j === b.lines.length - 1 ? tail : null}
                        fade={fade && j === b.lines.length - 1} />
                ))}
              </View>
            );
          case 'ul':
            return (
              <View key={i} style={s.list}>
                {b.items.map((it, j) => (
                  <View key={j} style={s.li}>
                    <Text style={s.marker}>•</Text>
                    <Rich src={it} style={s.liText} tail={j === b.items.length - 1 ? tail : null}
                          fade={fade && j === b.items.length - 1} />
                  </View>
                ))}
              </View>
            );
          case 'ol':
            return (
              <View key={i} style={s.list}>
                {b.items.map((it, j) => (
                  <View key={j} style={s.li}>
                    <Text style={s.marker}>{j + 1}.</Text>
                    <Rich src={it} style={s.liText} tail={j === b.items.length - 1 ? tail : null}
                          fade={fade && j === b.items.length - 1} />
                  </View>
                ))}
              </View>
            );
          case 'table':
            return <Table key={i} head={b.head} rows={b.rows} />;
          case 'code':
            return (
              <ScrollView key={i} horizontal showsHorizontalScrollIndicator={false} style={s.codeWrap}>
                <Text style={s.code}>{b.text}</Text>
              </ScrollView>
            );
          case 'hr':
            return <View key={i} style={s.hr} />;
          default:
            return null;
        }
      })}
      {caret && blocks.length && ['table', 'code', 'hr'].includes(blocks[blocks.length - 1].kind)
        ? <Caret /> : null}
    </View>
  );
}

const s = StyleSheet.create({
  doc: { width: '100%' },

  h1: { ...type.mdH1, color: color.fg, marginTop: space.lg, marginBottom: space.sm } as any,
  h2: { ...type.mdH2, color: color.fg, marginTop: space.lg, marginBottom: space.xs } as any,
  h3: { ...type.mdH3, color: color.fg, marginTop: space.md, marginBottom: space.xs } as any,
  p: { ...type.body, color: color.fg, marginBottom: space.sm } as any,

  bold: { fontWeight: '700' },
  italic: { fontStyle: 'italic' },
  codeInline: { ...type.mono, color: color.infoText } as any,

  // Врезка — левая линейка и приглушённый текст: то же, что делает любая большая модель, и по
  // той же причине — это ЧУЖОЙ голос внутри ответа, и он не должен спорить с основным.
  quote: {
    borderLeftWidth: 3, borderLeftColor: color.neutral300,
    paddingLeft: space.md, marginBottom: space.sm, gap: 2,
  },
  quoteText: { ...type.body, color: color.muted } as any,

  list: { marginBottom: space.sm, gap: space.xs },
  // Маркер в колонке фиксированной ширины: иначе текст второй строки уезжает под маркер и
  // список перестаёт читаться как список.
  li: { flexDirection: 'row', alignItems: 'flex-start', gap: space.sm },
  marker: { ...type.body, color: color.muted, minWidth: 18, textAlign: 'right' } as any,
  liText: { ...type.body, color: color.fg, flex: 1 } as any,

  tableWrap: { marginBottom: space.md },
  tableInner: { paddingRight: space.lg },
  tr: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: color.line },
  trHead: { borderBottomColor: color.neutral300, borderBottomWidth: 1.5 },
  trLast: { borderBottomWidth: 0 },
  // Минимум и максимум сразу: без минимума колонка с одним словом схлопывается в столбик из
  // букв, без максимума одна длинная ячейка уводит таблицу за горизонт.
  td: {
    ...type.body, color: color.fg,
    minWidth: 108, maxWidth: 260,
    paddingVertical: space.sm, paddingRight: space.lg,
  } as any,
  th: { color: color.muted, fontWeight: '700' },

  codeWrap: {
    backgroundColor: color.neutral100, borderRadius: rad.md,
    paddingHorizontal: space.md, paddingVertical: space.sm, marginBottom: space.sm,
  },
  code: { ...type.mono, color: color.fg } as any,

  hr: { height: 1, backgroundColor: color.border, marginVertical: space.md },
  // Курсор — тонкая полоса высотой в строку. Ширина в два пункта: толще выглядит как опечатка.
  // Знак в строке: цвет и размер от текста, а не свои. Полупрозрачность даёт мигание.
  caret: { color: color.primary, fontSize: 15, lineHeight: 22 } as any,
});
