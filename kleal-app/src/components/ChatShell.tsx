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
import React, { forwardRef, useState } from 'react';
import { mediaUrl } from '../api';
import {
  View, Text, StyleSheet, ScrollView, Image,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { BlurView } from 'expo-blur';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Composer } from './Composer';
import { Ambient, GLOW_FORM } from './Ambient';
import { LogoFace } from './Logo';
import Markdown from './Markdown';
import { Thinking } from './Thinking';
import { color, displayFamily, radius as rad, space, type } from '../theme';
import { useLang } from '../i18n';

export type Bubble = { who: 'bot' | 'me'; text: string; at: string; photo?: string;
  /** Текст ещё пишется — под ним мигает курсор. */ live?: boolean };

/**
 * Пузырь агента: белое стекло на 65% с размытием подложки и срезанным нижним левым углом.
 *
 * СРЕЗАННЫЙ УГОЛ — ЭТО ХВОСТ. В борде у пузырей три угла по 20 и один по 4: у агента срезан левый
 * нижний, у человека — правый нижний. Одного этого хватает, чтобы читалось, кто говорит, — поэтому
 * ни аватарок у реплик, ни стрелок-хвостиков в кадрах нет.
 */
function BotBubble({ children }: { children: React.ReactNode }) {
  return (
    <View style={s.bubBot}>
      <BlurView intensity={16} tint="light" style={StyleSheet.absoluteFill} />
      <View style={[StyleSheet.absoluteFill, { backgroundColor: color.glassLight, opacity: 0.65 }]} />
      {children}
    </View>
  );
}

/**
 * Пузырь человека: фирменный градиент из светло-красного в красный.
 *
 * ГРАДИЕНТ НАРИСОВАН SVG, А НЕ expo-linear-gradient — последнего в проекте нет вовсе, а
 * `react-native-svg` уже стоит (им сделан фон и мордочка). Ставить зависимость ради одной заливки
 * значит увеличить сборку и список того, что придётся чинить при переезде на новый SDK.
 *
 * РАЗМЕР БЕРЁТСЯ ЗАМЕРОМ, А НЕ ПРОЦЕНТАМИ. Первая версия задавала прямоугольнику `height="100%"` —
 * и он закрашивал ровно верхнюю половину пузыря, обрывая заливку резкой горизонталью посередине
 * фразы. Проценты внутри SVG считаются от области просмотра, а у слоя без `viewBox` она берётся по
 * ширине, не по высоте. Поэтому здесь честные точки из `onLayout`.
 *
 * ПОДЛОЖКА ФИРМЕННОГО ЦВЕТА ОБЯЗАТЕЛЬНА. Первый кадр пузырь живёт без замера, и без сплошной
 * заливки под градиентом белая подпись оказалась бы на прозрачном — на один кадр, но заметно.
 */
function MeBubble({ children }: { children: React.ReactNode }) {
  const [box, setBox] = useState({ w: 0, h: 0 });
  return (
    <View
      style={s.bubMe}
      onLayout={(e) => {
        const { width, height } = e.nativeEvent.layout;
        setBox((p) => (p.w === width && p.h === height ? p : { w: width, h: height }));
      }}
    >
      {box.w > 0 ? (
        <Svg width={box.w} height={box.h} style={StyleSheet.absoluteFill}>
          <Defs>
            {/* Ручки градиента из борда: он идёт по диагонали, а не сверху вниз. */}
            <LinearGradient id="me" x1="0.15" y1="0.15" x2="0.85" y2="0.85">
              <Stop offset="0" stopColor={color.brandSoft} />
              <Stop offset="1" stopColor={color.primary} />
            </LinearGradient>
          </Defs>
          <Rect x={0} y={0} width={box.w} height={box.h} fill="url(#me)" />
        </Svg>
      ) : null}
      {children}
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
  /** Правый угол шапки до процента: например «Начать заново». */
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
  /** Поставить курсор в поле ввода — по кнопке «написать своё». */
  focusSignal?: number;
  onBack?: () => void;
  onSend?: (text: string) => void;
}>(function ChatShell(
  { title, pct, thread, typing, widget, headerExtra, brow, scrollEnabled = true, composerPlaceholder, composerDisabled, focusSignal, onBack, onSend },
  scroller
) {
  const lang = useLang();
  const insets = useSafeAreaInsets();
  return (
    <View style={s.root}>
      <Ambient glows={GLOW_FORM} />
      <KeyboardAvoidingView style={s.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={[s.wrap, { paddingTop: insets.top + 8 }]}>
          <View style={s.head}>
            <LogoFace size={44} />
            <Text style={[s.headTitle, { fontFamily: displayFamily(lang) }]} numberOfLines={1}>
              {title}
            </Text>
            {headerExtra}
            {pct == null ? null : <Text style={s.headPct}>{pct}%</Text>}
          </View>
          {/*
            Полоса всегда на месте, даже на нуле: она обещает, что у разговора есть конец. Дорожка
            белая и непрозрачная — на кремовом фоне серая читалась бы как заполненная часть.
          */}
          {pct == null ? null : (
            <View style={s.track}>
              <View style={[s.trackFill, { width: `${pct}%` }]} />
            </View>
          )}
          {brow}

          <ScrollView
            ref={scroller as any}
            contentContainerStyle={s.thread}
            keyboardShouldPersistTaps="handled"
            scrollEnabled={scrollEnabled}
            showsVerticalScrollIndicator={false}
          >
            {/*
              РАЗМЕТКА В ОТВЕТЕ АГЕНТА РАЗБИРАЕТСЯ, А НЕ ПОКАЗЫВАЕТСЯ СЫРОЙ. Когда-то пузырь агента
              был обычным `Text`, и «## Что такое фьючерс» приезжало строкой с решётками. Лечили это
              тем, что вынесли ответ из пузыря целиком и стали верстать страницей — но в кадрах
              борда вопросы агента всё-таки в пузыре, и на коротком «Как тебя зовут?» страница во всю
              ширину выглядит пусто.
              Поэтому пузырь вернулся, а `Markdown` внутри него остался: заголовки, списки и таблицы
              разбираются как раньше, длинный ответ просто растёт вниз в тех же 86% ширины.
            */}
            {thread.map((m, i) => (
              <View key={i} style={m.who === 'me' ? s.rowMe : s.rowBot}>
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
              </View>
            ))}

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

            {!typing ? widget : null}
          </ScrollView>

          <Composer onBack={onBack} onSend={onSend} placeholder={composerPlaceholder}
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
  hint: { ...type.caption, color: color.muted } as any,
  /** Заголовок виджета: что человек сейчас делает. Стоит НАД подсказкой к жесту. */
  mapTitle: { ...type.labelMedium, color: color.fg } as any,
  label: { ...type.bodySmall, color: color.muted } as any,
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  rowSplit: { flexDirection: 'row', gap: space.sm },
});

// ===== вид
const s = StyleSheet.create({
  root: { flex: 1 },
  wrap: { flex: 1 },
  head: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingHorizontal: space.lg, paddingBottom: space.sm },
  headTitle: { flex: 1, ...type.chatTitle, color: color.fg } as any,
  headPct: { ...type.fieldLabel, color: color.muted } as any,
  /** Два пикселя — из борда. Толще полоса начинает спорить с заголовком над ней. */
  track: { height: 2, backgroundColor: color.card, marginHorizontal: space.lg, borderRadius: rad.full, overflow: 'hidden' },
  trackFill: { height: 2, backgroundColor: color.primary, borderRadius: rad.full },
  thread: { paddingHorizontal: space.lg, paddingTop: space.lg, paddingBottom: space.lg },
  rowBot: { alignItems: 'flex-start', marginTop: space.md },
  /** Вертушка встаёт там же, где начнётся пузырь, — чтобы появление реплики не сдвигало ленту. */
  typing: { paddingHorizontal: space.lg, paddingVertical: space.sm },
  rowMe: { alignItems: 'flex-end', marginTop: space.md },
  bubBot: {
    maxWidth: '86%',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: 20,
    borderBottomLeftRadius: 4,
    overflow: 'hidden',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF88',
    ...Platform.select({
      ios: { shadowColor: color.ink, shadowOpacity: 0.08, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 3 },
    }),
  },
  bubMe: {
    maxWidth: '86%',
    backgroundColor: color.primary,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: 20,
    borderBottomRightRadius: 4,
    overflow: 'hidden',
    ...Platform.select({
      ios: { shadowColor: color.primary, shadowOpacity: 0.28, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 5 },
    }),
  },
  bubText: { ...type.bubble, color: color.fg } as any,
  bubTextMe: { color: color.onPrimary },
  hintUnder: { ...type.chatHint, color: color.muted, marginTop: 6, marginLeft: 2 } as any,
  time: { ...type.fine, color: color.muted, marginTop: 4, marginHorizontal: 2 } as any,
  threadPhoto: { width: 178, height: 218, borderRadius: 20, marginTop: space.sm },
});
