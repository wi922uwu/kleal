/**
 * Общая оболочка чат-экранов: шапка с процентом, лента пузырей, слот под виджет, композер.
 *
 * Онбординг и создание интента устроены на борде одинаково — вопрос агента, виджет под ним,
 * строка «Message…» внизу. Пока это было написано дважды, любая правка ритма или отступов
 * расходилась между экранами; здесь одно место.
 *
 * ВИД ИЗ КАДРОВ A.04–A.13. Экран стоит на том же фирменном фоне, что и вход, а всё поверх него —
 * стекло: пузыри, поле ввода, чипы. Шапка не отделена линией и не залита — она просто лежит на
 * фоне, и единственное, что её держит, это полоса прогресса толщиной два пикселя.
 */
import React, { createContext, forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { mediaUrl } from '../api';
import {
  View, Text, StyleSheet, ScrollView, Image,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import Animated, {
  Easing, useAnimatedStyle, useReducedMotion, useSharedValue, withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Composer } from './Composer';
import { Ambient, GLOW_FORM } from './Ambient';
import { Blob } from './Blob';
import { GlassBack, GlassSurface, riseIn } from './LiquidGlass';
import Markdown from './Markdown';
import { Thinking } from './Thinking';
import { color, font, heading, space, type } from '../theme';
import { T, useLang } from '../i18n';

export type Bubble = { who: 'bot' | 'me'; text: string; at: string; photo?: string;
  /** Текст ещё пишется — под ним мигает курсор. */ live?: boolean;
  /** Секция-якорь, к которой относится реплика (этап анкеты). Без неё — первая секция. */
  sec?: string };

/**
 * Секция-якорь анкеты: этап со своим заголовком. Лента делится на такие секции, каждая не ниже
 * окна ленты, и прокрутка к ним примагничивается (см. ChatShell).
 */
export type ChatSection = { key: string; title: string };

/**
 * Высота окна ленты — сколько места у секции на экране. Виджет, который хочет занять секцию
 * целиком (спираль интересов), берёт отсюда свою высоту, а не угадывает её числом.
 */
export const ChatViewport = createContext(0);

/**
 * Пузырь агента — светлое жидкое стекло (макет «First run», A.04): без хвоста, скруглён на 18, с
 * едва заметной падающей тенью (#0A0A14 · 6%). Кто говорит, читается по стороне и цвету: агент
 * слева на стекле, человек справа на коралле.
 */
function BotBubble({ children }: { children: React.ReactNode }) {
  return (
    <View style={s.bubBotShadow}>
      <GlassSurface tone="light" radius={18} style={s.bubBot}>{children}</GlassSurface>
    </View>
  );
}

function MeBubble({ children }: { children: React.ReactNode }) {
  /*
    Реплика человека — коралловое стекло (#FF385C · 82% в макете) с фирменным свечением снизу.
    Градиент прежней версии ушёл: жидкое стекло само даёт перелив по кромке.
  */
  return (
    <View style={s.bubMeShadow}>
      <GlassSurface tone="brand" radius={18} style={s.bubMe}>{children}</GlassSurface>
    </View>
  );
}

export const ChatShell = forwardRef<ScrollView, {
  title: string;
  /** null — полосы и процента нет вовсе: шаг открыт не в рамках онбординга. */
  pct: number | null;
  thread: Bubble[];
  typing?: boolean;
  /** Виджет текущего шага — живёт ВНУТРИ ленты, под последней репликой. */
  widget?: React.ReactNode;
  /** Optional step actions outside the scrolling transcript, above the existing Composer. */
  footer?: React.ReactNode;
  /**
   * Тихое действие при шапке: например «Начать заново». Живёт СТРОКОЙ ПОД шапкой, справа: в угол
   * макета влезают только процент и капля (84 точки), и ссылка там наезжала на заголовок.
   */
  headerExtra?: React.ReactNode;
  /**
   * Бровка — тонкая полоса СРАЗУ под шапкой, над лентой. Для действия, которое доступно всё время
   * шага и не является ответом на текущий вопрос: «Это всё» в разговоре про интересы. Кнопкой в
   * ленте оно росло вместе с прокруткой и уезжало из виду, а по размеру спорило с самими ответами.
   */
  brow?: React.ReactNode;
  /**
   * Выключает прокрутку ленты. Нужно виджетам, которые сами ловят движение пальца: кольцо возраста
   * крутится ровно в том же жесте, каким лента прокручивается, и без этого едет и то, и другое.
   */
  scrollEnabled?: boolean;
  /** Подсказка в поле ввода, когда она зависит от шага. */
  composerPlaceholder?: string;
  /** Поле ввода недоступно: на шаге, где ждут нажатия, писать пока нечего. */
  composerDisabled?: boolean;
  /** Живая подложка вместо нарисованной. Включена в анкете — там она и на кадрах борда. */
  ambientVideo?: boolean;
  /** Поставить курсор в поле ввода — по кнопке «написать своё». */
  focusSignal?: number;
  onBack?: () => void;
  onSend?: (text: string) => void;
  /**
   * Секции-якоря по порядку; последняя — текущий этап, в ней виджет и «печатает». Без секций
   * лента сплошная, как раньше.
   */
  sections?: ChatSection[];
}>(function ChatShell(
  { title, pct, thread, typing, widget, footer, headerExtra, brow, scrollEnabled = true, composerPlaceholder, composerDisabled, focusSignal, onBack, onSend, ambientVideo, sections },
  scroller
) {
  const lang = useLang();
  const insets = useSafeAreaInsets();
  const reduced = useReducedMotion();

  /*
    СЕКЦИИ-ЯКОРЯ (владелец, 27.09). Каждый этап — секция не ниже окна ленты; прокрутка
    примагничивается к началу секции (snapToOffsets + быстрое торможение). У секции выше окна
    вторая точка — её низ: без неё середина и низ длинного разговора были бы недостижимы.
    Автопрокрутку ведёт оболочка, а не экран: только она знает, где лежат секции. Новый этап —
    лента плавно доезжает до его секции целиком; новая реплика в длинной секции — к её низу.
  */
  const ref = useRef<ScrollView>(null);
  useImperativeHandle(scroller, () => ref.current as ScrollView);
  const [vh, setVh] = useState(0);
  const boxes = useRef<Record<string, { y: number; h: number }>>({});
  const [offsets, setOffsets] = useState<number[]>([]);
  const active = sections && sections.length ? sections[sections.length - 1].key : '';
  const recompute = useCallback(() => {
    if (!sections || !vh) return;
    const out: number[] = [];
    for (const sec of sections) {
      const b = boxes.current[sec.key];
      if (!b) continue;
      out.push(Math.round(b.y));
      if (b.h > vh + 8) out.push(Math.round(b.y + b.h - vh));
    }
    out.sort((a, c) => a - c);
    setOffsets((prev) => (prev.length === out.length && prev.every((v, i) => v === out[i]) ? prev : out));
  }, [sections, vh]);
  // Куда встать: к началу текущей секции, а если она выше окна — к её низу (там новое).
  const settle = useCallback((animated: boolean) => {
    const b = active ? boxes.current[active] : null;
    if (!b || !vh) { ref.current?.scrollToEnd({ animated }); return; }
    ref.current?.scrollTo({ y: Math.max(0, b.h > vh + 8 ? b.y + b.h - vh : b.y), animated });
  }, [active, vh]);
  useEffect(() => {
    if (!sections) {
      const id = setTimeout(() => ref.current?.scrollToEnd({ animated: true }), 80);
      return () => clearTimeout(id);
    }
    // Две попытки: секция нового этапа меряется за кадр-два после появления.
    const a = setTimeout(() => settle(true), 90);
    const b = setTimeout(() => settle(true), 380);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, [thread.length, typing, active, vh]); // eslint-disable-line react-hooks/exhaustive-deps

  const bubble = (m: Bubble, i: number) => (
    <Animated.View key={i} style={m.who === 'me' ? s.rowMe : s.rowBot}
      entering={reduced ? undefined : riseIn(0, 6)}>
      {m.photo ? (
        <Image source={{ uri: mediaUrl(String(m.photo)) }} style={s.threadPhoto} />
      ) : m.who === 'me' ? (
        <MeBubble>
          <Text style={[s.bubText, s.bubTextMe]}>{m.text}</Text>
        </MeBubble>
      ) : (
        <BotBubble>
          <Markdown text={m.text} />
        </BotBubble>
      )}
      <Text style={s.time}>{m.at}</Text>
    </Animated.View>
  );
  return (
    <View style={s.root}>
      <Ambient glows={GLOW_FORM} video={ambientVideo} />
      <KeyboardAvoidingView style={s.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={[s.wrap, { paddingTop: insets.top + 8 }]}>
          {/*
            ШАПКА МАКЕТА: стеклянная «назад» слева, «Creating profile» по центру, справа процент
            точечным шрифтом и маленькая капля. Под заголовком — короткая полоса 100×2: она обещает,
            что у разговора есть конец, и не спорит с лентой за внимание.
          */}
          <View style={s.head}>
            <View style={s.headSide}>
              {onBack ? <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={onBack} /> : null}
            </View>
            <Text style={[s.headTitle, heading(lang, type.headingSm)]} numberOfLines={1}>
              {title}
            </Text>
            <View style={[s.headSide, s.headRight]}>
              {pct == null ? null : (
                <Text style={s.headPct}>{String(Math.round(pct)).padStart(2, '0')}%</Text>
              )}
              <Blob size={30} float={false} />
            </View>
          </View>
          {pct == null ? null : <Progress pct={pct} />}
          {headerExtra ? <View style={s.extra}>{headerExtra}</View> : null}
          {brow}

          <ChatViewport.Provider value={vh}>
          <ScrollView
            ref={ref}
            style={footer ? s.boundedThread : undefined}
            contentContainerStyle={sections ? s.threadSections : s.thread}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode={footer ? 'on-drag' : undefined}
            scrollEnabled={scrollEnabled}
            showsVerticalScrollIndicator={false}
            onLayout={(e) => { const h = Math.round(e.nativeEvent.layout.height); if (h && h !== vh) setVh(h); }}
            snapToOffsets={sections && offsets.length > 1 ? offsets : undefined}
            decelerationRate={sections ? 'fast' : 'normal'}
          >
            {sections ? sections.map((sec, si) => {
              const own = thread.filter((m) => (m.sec || sections[0].key) === sec.key);
              const isActive = sec.key === active;
              return (
                <View
                  key={sec.key}
                  style={[s.section, { minHeight: vh || undefined }]}
                  onLayout={(e) => {
                    const { y, height: h } = e.nativeEvent.layout;
                    boxes.current[sec.key] = { y, h };
                    recompute();
                  }}
                >
                  {/*
                    H1 СЕКЦИИ — фирменная ступень «hero» (32/36 TASA, по-русски Unbounded с поправкой
                    ширины): крупнее и тяжелее любой реплики, чтобы начало этапа читалось с одного
                    взгляда, даже если долистал до него снизу.
                  */}
                  <Animated.Text
                    entering={reduced ? undefined : riseIn(si === 0 ? 0 : 60, 8)}
                    style={[s.h1, heading(lang, type.hero)]}
                    accessibilityRole="header"
                    numberOfLines={2}
                  >
                    {sec.title}
                  </Animated.Text>
                  {own.map(bubble)}
                  {isActive && typing ? (
                    <View style={[s.rowBot, s.typing]}>
                      <Thinking />
                    </View>
                  ) : null}
                  {isActive && !typing ? <View style={s.widgetSlot}>{widget}</View> : null}
                </View>
              );
            }) : null}
            {sections ? null : <>
            {/*
              РАЗМЕТКА В ОТВЕТЕ АГЕНТА РАЗБИРАЕТСЯ, А НЕ ПОКАЗЫВАЕТСЯ СЫРОЙ. Когда-то пузырь агента
              был обычным `Text`, и «## Что такое фьючерс» приезжало строкой с решётками. Лечили это
              тем, что вынесли ответ из пузыря целиком и стали верстать страницей — но в кадрах
              борда вопросы агента всё-таки в пузыре, и на коротком «Как тебя зовут?» страница во всю
              ширину выглядит пусто.
              Поэтому пузырь вернулся, а `Markdown` внутри него остался: заголовки, списки и таблицы
              разбираются как раньше, длинный ответ просто растёт вниз в тех же 86% ширины.
            */}
            {thread.map(bubble)}

            {/*
              «ПЕЧАТАЕТ» — БЕЗ ПУЗЫРЯ. Сначала вертушка стояла в том же стеклянном пузыре, что и
              реплики: пустой прямоугольник с размытием, на розовом фоне читавшийся как непонятный
              цветной блок. Пузырь — форма СКАЗАННОГО, а пока агент печатает, сказанного ещё нет:
              рисовать его заранее значит показывать пустую реплику. Осталась одна вертушка на том
              же отступе, на котором через мгновение появится сам пузырь.
            */}
            {typing ? (
              <View style={[s.rowBot, s.typing]}>
                <Thinking />
              </View>
            ) : null}

            {/*
              Слот виджета добирает остаток высоты ленты: так шаг с короткой лентой может прижать
              свою главную кнопку к низу, над полем ввода (кадры A.07 и A.09) — `chatStyles.pin`.
              Длинная лента этого не замечает: места внизу там нет, кнопка просто идёт следом.
            */}
            {!typing ? <View style={s.widgetSlot}>{widget}</View> : null}
            </>}
          </ScrollView>
          </ChatViewport.Provider>

          {footer ? <View style={s.footer}>{footer}</View> : null}
          <Composer onSend={onSend} placeholder={composerPlaceholder}
                    disabled={composerDisabled} focusSignal={focusSignal} bottomInset={insets.bottom} />
        </View>
      </KeyboardAvoidingView>
    </View>
  );
});

/**
 * Реплика агента, нарисованная ВНУТРИ виджета, а не в ленте.
 *
 * Так на борде: после снимка агент хвалит фото прямо над кнопками «Оставить / Переснять», и это
 * тот же пузырь, что в ленте. Отдельный компонент, чтобы он не разъехался с лентой по скруглению
 * и цвету — расходиться начинают именно такие мелочи.
 */
/** Полоса прогресса: заполнение плавно доезжает, когда анкета продвинулась на шаг. */
function Progress({ pct }: { pct: number }) {
  const w = useSharedValue(pct);
  useEffect(() => {
    w.value = withTiming(Math.max(0, Math.min(100, pct)), { duration: 420, easing: Easing.out(Easing.cubic) });
  }, [pct, w]);
  const fill = useAnimatedStyle(() => ({ width: `${w.value}%` }));
  return (
    <View style={s.track}>
      <Animated.View style={[s.trackFill, fill]} />
    </View>
  );
}

export function BotLine({ children }: { children: React.ReactNode }) {
  return (
    <View style={s.rowBot}>
      <BotBubble>
        <Text style={s.bubText}>{children}</Text>
      </BotBubble>
    </View>
  );
}

/**
 * Строка-подсказка под пузырём агента: «Выбери из готового или напиши своё».
 *
 * В борде она стоит ПОД пузырём, а не внутри него, и набрана мельче — потому что это не слова
 * агента, а объяснение, как отвечать. Внутри пузыря она читалась бы как часть вопроса.
 */
export function BotHint({ children }: { children: React.ReactNode }) {
  return <Text style={s.hintUnder}>{children}</Text>;
}

export const chatStyles = StyleSheet.create({
  widget: { gap: space.md, marginTop: space.md, width: '100%' },
  /** Виджет растягивается на остаток ленты — нужен тому, кто прижимает кнопку к низу. */
  fill: { flexGrow: 1 },
  /** Прижать к низу ленты (над композером), если ниже есть место. */
  pin: { marginTop: 'auto', gap: space.md },
  hint: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted } as any,
  /** Заголовок виджета: что человек сейчас делает. Стоит НАД подсказкой к жесту. */
  mapTitle: { ...type.labelMedium, color: color.fg } as any,
  label: { fontFamily: font.displaySemi, fontSize: 12, lineHeight: 16, color: color.fg } as any,
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  rowSplit: { flexDirection: 'row', gap: space.sm },
});

// ===== вид
const s = StyleSheet.create({
  root: { flex: 1 },
  wrap: { flex: 1 },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.lg, height: 44 },
  /** Боковины одной ширины (72) — так заголовок стоит точно по центру, как в макете. */
  headSide: { width: 84, flexDirection: 'row', alignItems: 'center' },
  headRight: { justifyContent: 'flex-end', gap: space.sm },
  headTitle: { flex: 1, textAlign: 'center', color: color.fg } as any,
  headPct: { ...type.num, color: color.muted } as any,
  track: {
    alignSelf: 'center', width: 100, height: 2, marginTop: 10,
    backgroundColor: 'rgba(255,255,255,0.67)', borderRadius: 999, overflow: 'hidden',
  },
  trackFill: { height: 2, backgroundColor: color.primary, borderRadius: 999 },
  thread: { flexGrow: 1, paddingHorizontal: space.lg, paddingTop: space.lg, paddingBottom: space.lg },
  /** Лента секций: отступы у самих секций, чтобы начало секции совпадало с верхом окна. */
  threadSections: { flexGrow: 1, paddingHorizontal: space.lg },
  /** Секция-якорь: не ниже окна ленты (minHeight ставится на месте), виджет прижимается к низу. */
  section: { paddingTop: space.xl, paddingBottom: space.lg },
  /** H1 секции: над первой репликой, с воздухом снизу. */
  h1: { color: color.fg, marginBottom: space.sm } as any,
  widgetSlot: { flexGrow: 1 },
  extra: { flexDirection: 'row', justifyContent: 'flex-end', paddingHorizontal: space.lg, marginTop: 6 },
  boundedThread: { flex: 1, minHeight: 0 },
  footer: { flexShrink: 0, paddingHorizontal: space.lg, paddingTop: space.sm },
  rowBot: { alignItems: 'flex-start', marginTop: space.md },
  /** Вертушка встаёт там же, где начнётся пузырь, — чтобы появление реплики не сдвигало ленту. */
  typing: { paddingHorizontal: space.lg, paddingVertical: space.sm },
  rowMe: { alignItems: 'flex-end', marginTop: space.md },
  bubBotShadow: {
    maxWidth: '86%',
    borderRadius: 18,
    ...Platform.select({
      ios: { shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 4, shadowOffset: { width: 0, height: 1 } },
      default: {},
    }),
  },
  bubBot: { paddingHorizontal: space.lg, paddingVertical: space.md },
  bubMeShadow: {
    maxWidth: '86%',
    borderRadius: 18,
    ...Platform.select({
      ios: { shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 5 },
    }),
  },
  bubMe: { paddingHorizontal: space.lg, paddingVertical: space.md },
  bubText: { ...type.bubble, color: color.fg } as any,
  bubTextMe: { color: color.onPrimary },
  hintUnder: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted, marginTop: 6, marginLeft: 2 } as any,
  time: { fontFamily: font.text, fontSize: 11, lineHeight: 22, color: '#8A8F96', marginHorizontal: 2 } as any,
  threadPhoto: { width: 178, height: 218, borderRadius: 20, marginTop: space.sm },
});
