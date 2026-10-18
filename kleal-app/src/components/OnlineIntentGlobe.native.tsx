/**
 * Вкладка «Онлайн»: список интентов по странам НАД планетой.
 *
 * ЗДЕСЬ БОЛЬШЕ НЕТ СВОЕГО ШАРА. Планета — это сама карта интентов, свёрнутая камерой (см.
 * ExploreMap/GlMap): одна модель мира вместо двух, одна сцена, никакого стыка между ними.
 * Этот файл рисует только то, что лежит ПОВЕРХ неё: кнопку со счётчиком и лист со списком.
 *
 * ПРАВИЛА ВЛАДЕЛЬЦА.
 *   1. Сначала на экране только планета, в полный размер.
 *   2. Список выезжает снизу по кнопке — и пока он открыт, планета видна целиком: экран
 *      сообщает карте, сколько пикселей закрыто, и та уходит в верхнюю часть окна.
 *   3. Лист — в языке приложения: карточка человека как на карте (кружок с буквой, значок темы,
 *      название, время с часами, шеврон), ленты-чипы стран, те же скругления и шрифты.
 *      Поверхность тёмная (`color.glassDark`): над космосом белый лист читался как чужой.
 *
 * 17.10.2026 ЛИСТ ПЕРЕДЕЛАН С НУЛЯ (владелец: «попап на глобусе выглядит ужасно»). Тёмное стекло
 * с коралловым светом у кромки, как свечения карусели главной; страны — плитки с флагом,
 * названием и коралловым счётчиком (те же, что плашки на шаре); разделы — флаг в квадрате и
 * имя страны; строка — плитка темы вместо безликой буквы (фото у онлайн-интента нет), мета
 * коралловыми значками и метки «онлайн» с зелёной точкой. Строки поднимаются лесенкой (riseIn).
 *
 * СВЯЗЬ СПИСКА И ПЛАНЕТЫ — одна выбранная страна в обе стороны: тап по плашке на планете
 * открывает лист и подвозит его к разделу; прокрутка списка доворачивает планету к стране,
 * чей раздел сейчас вверху. Кольцо «тап → прокрутка → новый поворот» гасится таймером `driving`.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, Animated, Easing, PanResponder, Pressable, ScrollView, SectionList, StyleSheet, Text, View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import RAnimated from 'react-native-reanimated';
import Svg, { Defs, RadialGradient, Rect, Stop } from 'react-native-svg';
import {
  onlineIntentGlobeCopy,
  type OnlineIntentCountryCluster,
  type OnlineIntentGlobeProps,
  type OnlineIntentItem,
} from '../online-intent-globe';
import { CategoryGlyph, iconNameFor } from './category-icons';
import { IconChevronLeft, IconClock, IconPerson, IconUsers } from './icons';
import { GlassSurface, riseIn } from './LiquidGlass';
import { topicIcon } from '../online-ask';
import { color, radius as rad, shadow, space, type } from '../theme';

/** Раздел «страна не указана» — отдельный ключ, на планете его нет. */
const UNKNOWN = '__location_unknown__';
/** Доля экрана под лист. Остальное — планете, и она обязана поместиться туда целиком. */
const SHEET_SHARE = 0.58;
/*
 * ЛИСТ И ПЛАНЕТА ДВИЖУТСЯ ВМЕСТЕ. Лист выезжает — планета уходит вверх; лист уходит — планета
 * возвращается. Чтобы это читалось как одно движение, обе стороны используют одну длительность
 * и одну кривую: здесь — плавный вход-выход, на странице карты — smootherstep (те же 420/300 мс,
 * см. GlMap → `view`). Убрать быстрее, чем показать.
 */
const OPEN_MS = 420;
const CLOSE_MS = 300;
const EASE = Easing.bezier(0.45, 0, 0.55, 1);

/** Флаг из кода страны: две буквы → два региональных символа, без картинок. */
function flagOf(code: string): string {
  const c = String(code || '').toUpperCase();
  if (!/^[A-Z]{2}$/.test(c)) return '';
  return String.fromCodePoint(0x1f1e6 + (c.charCodeAt(0) - 65), 0x1f1e6 + (c.charCodeAt(1) - 65));
}

type Section = { key: string; title: string; count: number; note?: string; data: OnlineIntentItem[] };

export function OnlineIntentGlobe({
  model,
  status,
  onRetry,
  onOpenIntent,
  contentInsets,
  testID = 'online-intent-globe',
  selected = null,
  onSelect,
  onSheet,
  pickSignal = 0,
  openSignal = 0,
}: OnlineIntentGlobeProps & {
  selected?: string | null;
  onSelect?: (code: string | null) => void;
  onSheet?: (bottom: number) => void;
  pickSignal?: number;
  openSignal?: number;
}) {
  const insets = useSafeAreaInsets();
  const copy = onlineIntentGlobeCopy(model.locale);
  const [layoutH, setLayoutH] = useState(0);
  const [open, setOpen] = useState(false);
  const list = useRef<SectionList<OnlineIntentItem, Section>>(null);
  /** Список едет по команде планеты — его прокрутка в это время не выбор человека. */
  const driving = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** 0 — лист спрятан за нижним краем, 1 — выехал. */
  const slide = useRef(new Animated.Value(0)).current;

  const sheetH = Math.max(300, Math.round(layoutH * SHEET_SHARE));
  const topPad = contentInsets?.top ?? insets.top + space.md;
  /*
   * Снизу лист заканчивается НАД нижней навигацией: экран говорит, сколько она занимает, и
   * ровно столько лист оставляет пустым под списком. Иначе навигация лежала поверх карточек,
   * а прокрутка уводила их под неё.
   */
  const navClear = contentInsets?.bottom ?? insets.bottom + space.md;

  const sections = useMemo<Section[]>(() => {
    const out: Section[] = model.countries.map((c: OnlineIntentCountryCluster) => ({
      key: c.code, title: c.name, count: c.count, data: c.intents,
    }));
    if (model.unknown.length) {
      out.push({ key: UNKNOWN, title: copy.unknownTitle, count: model.unknown.length, note: copy.unknownNote, data: model.unknown });
    }
    return out;
  }, [model, copy]);

  const show = useCallback(() => {
    setOpen(true);
    Animated.timing(slide, { toValue: 1, duration: OPEN_MS, easing: EASE, useNativeDriver: true }).start();
  }, [slide]);
  // `open` гаснет сразу: планета должна тронуться обратно в ту же секунду, что и лист.
  const hide = useCallback(() => {
    setOpen(false);
    Animated.timing(slide, { toValue: 0, duration: CLOSE_MS, easing: EASE, useNativeDriver: true }).start();
  }, [slide]);

  /*
   * СМАХНУТЬ РУКОЙ. Верх листа (ручка, заголовок, лента стран) тянется вниз и ведёт лист за
   * пальцем; отпустили дальше четверти высоты или с размахом — лист уходит, иначе садится
   * обратно. Список ниже прокручивается сам, поэтому жест живёт только на «шапке».
   */
  const sheetHRef = useRef(sheetH); sheetHRef.current = sheetH;
  const hideRef = useRef(hide); hideRef.current = hide;
  const dragFrom = useRef(1);
  const pan = useRef(PanResponder.create({
    onMoveShouldSetPanResponder: (_, g) => g.dy > 6 && Math.abs(g.dy) > Math.abs(g.dx) * 1.4,
    onPanResponderGrant: () => { slide.stopAnimation((v: number) => { dragFrom.current = v; }); },
    onPanResponderMove: (_, g) => {
      slide.setValue(Math.max(0, Math.min(1, dragFrom.current - g.dy / Math.max(1, sheetHRef.current))));
    },
    onPanResponderRelease: (_, g) => {
      if (g.dy > sheetHRef.current * 0.25 || g.vy > 0.6) hideRef.current();
      else Animated.timing(slide, { toValue: 1, duration: 220, easing: EASE, useNativeDriver: true }).start();
    },
    onPanResponderTerminate: () => {
      Animated.timing(slide, { toValue: 1, duration: 220, easing: EASE, useNativeDriver: true }).start();
    },
  })).current;

  // Планета обязана остаться видна целиком: экран сообщает карте высоту листа.
  useEffect(() => { onSheet?.(open ? sheetH : 0); }, [open, sheetH, onSheet]);
  useEffect(() => {
    if (status !== 'ready') { setOpen(false); slide.setValue(0); }
  }, [status, slide]);

  /** Подвезти список к разделу страны. */
  const scrollTo = useCallback((code: string, justOpened: boolean) => {
    const i = sections.findIndex((s) => s.key === code);
    if (i < 0) return;
    if (driving.current) clearTimeout(driving.current);
    driving.current = setTimeout(() => { driving.current = null; }, 900);
    // Свежеоткрытый список ещё не измерил разделы — даём ему кадр-другой.
    setTimeout(() => {
      try { list.current?.scrollToLocation({ sectionIndex: i, itemIndex: 0, viewPosition: 0, animated: true }); }
      catch { /* не измерен — доедет при следующем событии */ }
    }, justOpened ? 380 : 0);
  }, [sections]);

  /** Лупа в нижней панели экрана: открыть список. Своей кнопки сверху у листа больше нет. */
  useEffect(() => {
    if (openSignal && !open && status === 'ready' && model.stats.total > 0) show();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSignal]);

  /** Тап по плашке страны на планете: открыть лист и подвезти к её разделу. */
  useEffect(() => {
    if (!pickSignal || !selected) return;
    const justOpened = !open;
    if (!open) show();
    scrollTo(selected, justOpened);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickSignal]);

  /** Выбор страны в ленте чипов: и планета, и список едут к ней. */
  const pickCountry = useCallback((code: string) => {
    onSelect?.(code);
    scrollTo(code, false);
  }, [onSelect, scrollTo]);

  /** Прокрутка списка: страна первого видимого элемента становится выбранной — планета едет к ней. */
  const onViewable = useRef(({ viewableItems }: { viewableItems: any[] }) => {
    if (driving.current) return;
    const first = viewableItems.find((v) => v.isViewable && v.section);
    const key = first?.section?.key;
    if (!key || key === UNKNOWN) return;
    onSelectRef.current?.(key);
  }).current;
  const onSelectRef = useRef(onSelect);
  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

  const ready = status === 'ready';
  const total = model.stats.total;

  return (
    <View style={s.root} pointerEvents="box-none" testID={testID} onLayout={(e) => setLayoutH(e.nativeEvent.layout.height)}>
      {/* Над планетой — только состояние, когда списка нет: грузим, ошибка, пусто. Открывает
          список лупа в нижней панели экрана (со счётчиком), своей кнопки у листа нет. */}
      {!open && status !== 'ready' ? (
        <View pointerEvents="box-none" style={[s.top, { top: topPad }]}>
          {status === 'loading' ? (
            <View style={s.pill}><ActivityIndicator color={INK} /><Text style={s.pillText}>{copy.loading}</Text></View>
          ) : (
            <Pressable accessibilityRole="button" onPress={onRetry} style={s.pill}>
              <Text style={s.pillText}>{copy.errorTitle} · {copy.retry}</Text>
            </Pressable>
          )}
        </View>
      ) : null}
      {!open && status === 'ready' && total === 0 ? (
        <View pointerEvents="box-none" style={[s.top, { top: topPad }]}>
          <View style={s.pill}><Text style={s.pillText}>{copy.emptyTitle}</Text></View>
        </View>
      ) : null}

      {/* Лист — как все листы приложения, только не модальный: планета над ним живая. */}
      {ready && total > 0 ? (
        <Animated.View
          pointerEvents={open ? 'auto' : 'none'}
          style={[s.sheet, { height: sheetH, paddingBottom: navClear, transform: [{ translateY: slide.interpolate({ inputRange: [0, 1], outputRange: [sheetH, 0] }) }] }]}
        >
          {/* Стекло и коралловый свет у верхней кромки — тот же тёплый ореол, что за карточками главной. */}
          <GlassSurface tone="dark" radius={rad.xxl} style={s.glass} pointerEvents="none" />
          <View style={s.glow} pointerEvents="none">
            <Svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
              <Defs>
                <RadialGradient id="og_glow" cx="50%" cy="0%" r="70%">
                  <Stop offset="0" stopColor={color.primary} stopOpacity={0.32} />
                  <Stop offset="0.6" stopColor="#8E5CFF" stopOpacity={0.08} />
                  <Stop offset="1" stopColor="#8E5CFF" stopOpacity={0} />
                </RadialGradient>
              </Defs>
              <Rect x="0" y="0" width="100" height="100" fill="url(#og_glow)" />
            </Svg>
          </View>
          <View style={s.edge} pointerEvents="none" />
          <View {...pan.panHandlers}>
          <View style={s.grip} />
          <View style={s.head}>
            <View style={{ flex: 1 }}>
              <Text style={s.title} numberOfLines={1}>{copy.listHeading}</Text>
              <Text style={s.sub} numberOfLines={1}>{copy.worldSummary(total, model.stats.countries)}</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel={copy.close} onPress={hide} hitSlop={10} style={s.close}>
              <Text style={s.x}>✕</Text>
            </Pressable>
          </View>

          {/* Лента стран: быстрый переход и заодно видно, где вообще есть люди. */}
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={s.rail}
            keyboardShouldPersistTaps="handled"
          >
            {sections.map((sec) => {
              const on = sec.key === selected;
              return (
                <Pressable
                  key={sec.key}
                  accessibilityRole="button"
                  onPress={() => (sec.key === UNKNOWN ? scrollTo(sec.key, false) : pickCountry(sec.key))}
                  style={({ pressed }) => [s.tile, on && s.tileOn, pressed && { transform: [{ scale: 0.96 }] }]}
                >
                  <Text style={s.tileFlag}>{sec.key === UNKNOWN ? '🌐' : flagOf(sec.key)}</Text>
                  <Text style={[s.tileName, on && s.tileNameOn]} numberOfLines={1}>{sec.title}</Text>
                  <View style={[s.tileCount, on && s.tileCountOn]}><Text style={s.tileCountText}>{sec.count}</Text></View>
                </Pressable>
              );
            })}
          </ScrollView>
          </View>

          <SectionList
            ref={list}
            sections={sections}
            keyExtractor={(item) => item.id}
            stickySectionHeadersEnabled
            onViewableItemsChanged={onViewable}
            viewabilityConfig={{ itemVisiblePercentThreshold: 40, minimumViewTime: 80 }}
            onScrollToIndexFailed={() => { /* разделы ещё не измерены — ничего не ломаем */ }}
            contentContainerStyle={{ paddingBottom: space.md }}
            showsVerticalScrollIndicator={false}
            renderSectionHeader={({ section }) => (
              <View style={s.section}>
                <View style={s.sectionFlagBox}><Text style={s.sectionFlag}>{section.key === UNKNOWN ? '🌐' : flagOf(section.key)}</Text></View>
                <Text style={s.sectionTitle} numberOfLines={1}>{section.title}</Text>
                <Text style={s.sectionCountText}>{section.count}</Text>
              </View>
            )}
            renderItem={({ item, index }) => (
              <RAnimated.View entering={riseIn(Math.min(index, 6) * 40, 8)}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={copy.openIntent}
                  onPress={() => onOpenIntent?.(item)}
                  style={({ pressed }) => [s.card, pressed && s.cardPressed]}
                >
                  {/* Фото у онлайн-интента нет — вместо безликой буквы плитка его темы. */}
                  <View style={s.topic}><CategoryGlyph name={topicIcon(item.topics, iconNameFor)} size={22} c={'#FFB4C2'} /></View>
                  <View style={s.cardText}>
                    <Text style={s.cardTitle} numberOfLines={1}>{item.title}</Text>
                    <View style={s.metaRow}>
                      {item.who ? <DarkChunk icon={<IconPerson size={14} c={color.primary} />} text={item.who} shrink /> : null}
                      {item.when ? <DarkChunk icon={<IconClock size={14} c={color.primary} />} text={item.when} /> : null}
                    </View>
                    <View style={s.tags}>
                      <View style={[s.tag, item.mode === 'hybrid' && s.tagAccent]}>
                        <View style={[s.dot, item.mode === 'hybrid' && { backgroundColor: color.primary }]} />
                        <Text style={[s.tagText, item.mode === 'hybrid' && s.tagTextAccent]}>
                          {item.mode === 'hybrid' ? copy.hybrid : copy.online}
                        </Text>
                      </View>
                      <View style={s.tag}>
                        <IconUsers size={11} c={DIM} />
                        <Text style={s.tagText}>{item.format === 'group' ? copy.group : copy.oneToOne}</Text>
                      </View>
                    </View>
                  </View>
                  {/* Шеврон смотрит вправо: та же иконка, повёрнутая, — своей в наборе нет. */}
                  <View style={s.chev}><IconChevronLeft size={18} c={'rgba(255,255,255,0.38)'} /></View>
                </Pressable>
              </RAnimated.View>
            )}
            renderSectionFooter={({ section }) => section.note ? <Text style={s.note}>{section.note}</Text> : null}
          />
        </Animated.View>
      ) : null}
    </View>
  );
}

/** Кусочек меты на тёмном: коралловый значок и светлая подпись (как Chunk «Home Card»). */
function DarkChunk({ icon, text, shrink }: { icon: React.ReactNode; text: string; shrink?: boolean }) {
  return (
    <View style={[s.chunk, shrink && { flexShrink: 1, minWidth: 0 }]}>
      {icon}
      <Text style={s.chunkText} numberOfLines={1}>{text}</Text>
    </View>
  );
}

/**
 * Текст и линии на тёмной поверхности. Токенов «приглушённый на тёмном» в теме нет, поэтому
 * они выводятся из её же белого один раз здесь, а не литералами по всему файлу.
 */
const INK = color.glassLight;
const DIM = 'rgba(255,255,255,0.62)';
const LINE = 'rgba(255,255,255,0.10)';
const RAISED = 'rgba(255,255,255,0.07)';

const s = StyleSheet.create({
  root: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0 },

  // ── Кнопка над планетой: та же пилюля, что у сводки на карте ───────────────────────────
  top: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  // Над планетой всё тёмное: плашка состояния — из того же стекла, что лист.
  pill: {
    flexDirection: 'row', alignItems: 'center', gap: space.sm,
    height: 44, paddingHorizontal: space.md, borderRadius: rad.full,
    backgroundColor: color.glassDark, borderWidth: 1, borderColor: LINE,
  },
  pillText: { ...type.button, color: INK } as any,

  // ── Лист: геометрия Sheet.tsx — карточка, ручка, заголовок 20/700, крестик ─────────────
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    borderTopLeftRadius: rad.xxl, borderTopRightRadius: rad.xxl,
    paddingTop: 12, ...shadow.card,
  },
  glass: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, backgroundColor: color.glassDark, borderBottomLeftRadius: 0, borderBottomRightRadius: 0 },
  glow: { position: 'absolute', left: 0, right: 0, top: 0, height: 160, borderTopLeftRadius: rad.xxl, borderTopRightRadius: rad.xxl, overflow: 'hidden' },
  /** Светлая кромка стекла сверху — как блик на краю пилюль. */
  edge: {
    position: 'absolute', left: 0, right: 0, top: 0, height: 24,
    borderTopLeftRadius: rad.xxl, borderTopRightRadius: rad.xxl,
    borderTopWidth: 1, borderColor: 'rgba(255,255,255,0.16)',
  },
  grip: { width: 40, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.28)', alignSelf: 'center', marginBottom: 8 },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, marginBottom: 10 },
  title: { fontSize: 20, fontWeight: '700', color: INK, letterSpacing: -0.2 } as any,
  sub: { ...type.caption, color: DIM, marginTop: 1 } as any,
  close: { width: 32, height: 32, borderRadius: 16, backgroundColor: RAISED, borderWidth: 1, borderColor: LINE, alignItems: 'center', justifyContent: 'center' },
  x: { fontSize: 14, color: INK },

  // ── Плитки стран: флаг, имя, коралловый счётчик — как плашки на шаре ──────────────────
  rail: { paddingHorizontal: 14, paddingBottom: 10, gap: 8 },
  tile: {
    width: 76, height: 72, borderRadius: 18, paddingTop: 9, alignItems: 'center',
    backgroundColor: RAISED, borderWidth: 1, borderColor: LINE,
  },
  tileOn: {
    backgroundColor: 'rgba(255,56,92,0.16)', borderColor: 'rgba(255,56,92,0.7)',
    shadowColor: color.primary, shadowOpacity: 0.45, shadowRadius: 10, shadowOffset: { width: 0, height: 0 },
  },
  tileFlag: { fontSize: 24, lineHeight: 28 } as any,
  tileName: { ...type.labelSmall, fontSize: 11, color: DIM, marginTop: 4, maxWidth: 68 } as any,
  tileNameOn: { color: INK } as any,
  tileCount: {
    position: 'absolute', top: -1, right: -1, minWidth: 20, height: 20, paddingHorizontal: 5, borderRadius: 10,
    backgroundColor: 'rgba(255,56,92,0.85)', alignItems: 'center', justifyContent: 'center',
  },
  tileCountOn: { backgroundColor: color.primary },
  tileCountText: { fontSize: 11, lineHeight: 13, fontWeight: '700', color: '#fff' } as any,

  // ── Разделы: флаг в квадрате, имя страны, число коралловым ──────────────────────────
  section: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: 18, paddingTop: 10, paddingBottom: 8, backgroundColor: 'rgba(26,28,33,0.96)',
  },
  sectionFlagBox: { width: 28, height: 28, borderRadius: 8, backgroundColor: RAISED, borderWidth: 1, borderColor: LINE, alignItems: 'center', justifyContent: 'center' },
  sectionFlag: { fontSize: 15 } as any,
  sectionTitle: { flex: 1, fontSize: 15, fontWeight: '700', color: INK } as any,
  sectionCountText: { fontSize: 13, fontWeight: '700', color: color.primary } as any,

  // ── Строки ───────────────────────────────────────────────────────────────────────────
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: 12, marginBottom: 8, paddingVertical: 10, paddingLeft: 10, paddingRight: 6,
    borderRadius: 20, backgroundColor: RAISED, borderWidth: 1, borderColor: LINE,
  },
  cardPressed: { backgroundColor: 'rgba(255,255,255,0.12)' },
  topic: {
    width: 48, height: 48, borderRadius: 16,
    backgroundColor: 'rgba(255,56,92,0.16)', borderWidth: 1, borderColor: 'rgba(255,56,92,0.32)',
    alignItems: 'center', justifyContent: 'center',
  },
  cardText: { flex: 1, minWidth: 0, gap: 3 },
  cardTitle: { ...type.body, fontWeight: '600', lineHeight: 20, color: INK } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minWidth: 0 },
  chunk: { flexDirection: 'row', alignItems: 'center', gap: 4, flexShrink: 0 },
  chunkText: { flexShrink: 1, fontSize: 13, lineHeight: 17, color: DIM },
  tags: { flexDirection: 'row', gap: 6 },
  tag: { flexDirection: 'row', alignItems: 'center', gap: 4, height: 20, paddingHorizontal: 7, borderRadius: rad.full, backgroundColor: 'rgba(255,255,255,0.08)' },
  tagAccent: { backgroundColor: 'rgba(255,56,92,0.18)' },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#3DDC97' },
  tagText: { fontSize: 11, lineHeight: 13, fontWeight: '600', color: DIM } as any,
  tagTextAccent: { color: '#ffb4c2' } as any,
  chev: { transform: [{ rotate: '180deg' }] },

  note: { ...type.caption, color: DIM, paddingHorizontal: 18, paddingBottom: space.sm } as any,
});
