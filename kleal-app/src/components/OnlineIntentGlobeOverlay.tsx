import React from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { IconChevronLeft, IconGlobe } from './icons';
import {
  onlineIntentGlobeCopy,
  type OnlineIntentGlobeInsets,
  type OnlineIntentGlobeModel,
  type OnlineIntentGlobeStatus,
  type OnlineIntentItem,
} from '../online-intent-globe';
import { color, radius, shadow, space, type } from '../theme';

export type OnlineIntentGlobeSelection = Readonly<{
  key: string;
  name: string;
  note?: string;
  intents: OnlineIntentItem[];
}>;

export function OnlineIntentGlobeOverlay({
  model,
  status,
  contentInsets,
  selection,
  onRetry,
  onResetWorld,
  onOpenUnknown,
  onCloseSelection,
  onOpenIntent,
}: {
  model: OnlineIntentGlobeModel;
  status: OnlineIntentGlobeStatus;
  contentInsets?: OnlineIntentGlobeInsets;
  selection: OnlineIntentGlobeSelection | null;
  onRetry?: () => void;
  onResetWorld: () => void;
  onOpenUnknown: () => void;
  onCloseSelection: () => void;
  onOpenIntent?: (intent: OnlineIntentItem) => void;
}) {
  const safe = useSafeAreaInsets();
  const copy = onlineIntentGlobeCopy(model.locale);
  const top = contentInsets?.top ?? safe.top + space.md;
  const right = contentInsets?.right ?? space.xl;
  const bottom = contentInsets?.bottom ?? safe.bottom + space.md;
  const left = contentInsets?.left ?? space.xl;
  const empty = status === 'ready' && model.stats.total === 0;

  return (
    <View pointerEvents="box-none" style={StyleSheet.absoluteFill}>
      {status === 'ready' && model.stats.total > 0 ? (
        <View pointerEvents="box-none" style={[s.topStack, { top, left, right }]}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={copy.worldSummary(model.stats.total, model.stats.countries)}
            accessibilityHint={model.locale === 'ru' ? 'Показать весь мир'
              : model.locale === 'es' ? 'Ver el mundo entero' : 'Show the whole world'}
            onPress={onResetWorld}
            testID="online-globe-summary"
            style={s.summary}
          >
            <IconGlobe size={20} c={color.fg} />
            <Text style={s.summaryText} numberOfLines={1}>
              {copy.worldSummary(model.stats.total, model.stats.countries)}
            </Text>
          </Pressable>
          {model.unknown.length ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={copy.unknown(model.unknown.length)}
              accessibilityHint={copy.countryHint}
              onPress={onOpenUnknown}
              testID="online-globe-unknown"
              style={s.unknown}
            >
              <View style={s.unknownDot} />
              <Text style={s.unknownText} numberOfLines={1}>{copy.unknown(model.unknown.length)}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {status === 'loading' ? (
        <View accessibilityRole="progressbar" accessibilityLabel={copy.loading} style={s.stateCard}>
          <ActivityIndicator color={color.primary} />
          <Text style={s.stateTitle}>{copy.loading}</Text>
        </View>
      ) : null}

      {status === 'error' ? (
        <View accessibilityRole="alert" style={s.stateCard}>
          <Text style={s.stateTitle}>{copy.errorTitle}</Text>
          <Text style={s.stateNote}>{copy.errorNote}</Text>
          {onRetry ? (
            <Pressable accessibilityRole="button" onPress={onRetry} testID="online-globe-retry" style={s.retry}>
              <Text style={s.retryText}>{copy.retry}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {empty ? (
        <View style={s.stateCard} testID="online-globe-empty">
          <Text style={s.stateTitle}>{copy.emptyTitle}</Text>
          <Text style={s.stateNote}>{copy.emptyNote}</Text>
        </View>
      ) : null}

      {status === 'ready' && selection ? (
        <View
          accessibilityViewIsModal
          testID="online-globe-selection"
          style={[s.sheet, { left, right, bottom }]}
        >
          <View style={s.sheetHead}>
            <View style={s.sheetTitleWrap}>
              <Text style={s.sheetTitle} numberOfLines={1}>
                {copy.listTitle(selection.name, selection.intents.length)}
              </Text>
              {selection.note ? <Text style={s.sheetNote}>{selection.note}</Text> : null}
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={copy.close}
              onPress={onCloseSelection}
              hitSlop={10}
              testID="online-globe-close-selection"
              style={s.close}
            >
              <View style={s.closeIcon}><IconChevronLeft size={20} c={color.fg} /></View>
            </Pressable>
          </View>
          <FlatList
            data={selection.intents}
            keyExtractor={(item) => item.id}
            style={s.list}
            contentContainerStyle={s.listContent}
            showsVerticalScrollIndicator={selection.intents.length > 3}
            initialNumToRender={6}
            maxToRenderPerBatch={12}
            windowSize={5}
            renderItem={({ item }) => {
              const mode = item.mode === 'hybrid' ? copy.hybrid : copy.online;
              const format = item.format === 'group' ? copy.group : copy.oneToOne;
              const title = item.title || item.topics[0] || mode;
              return (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`${title}. ${mode}. ${format}`}
                  accessibilityHint={onOpenIntent ? copy.openIntent : undefined}
                  accessibilityState={{ disabled: !onOpenIntent }}
                  disabled={!onOpenIntent}
                  onPress={onOpenIntent ? () => onOpenIntent(item) : undefined}
                  testID={`online-globe-intent-${item.id}`}
                  style={({ pressed }) => [s.intent, pressed && s.intentPressed]}
                >
                  <View style={s.intentAvatar}>
                    <Text style={s.intentInitial}>{(item.who || title).slice(0, 1).toUpperCase()}</Text>
                  </View>
                  <View style={s.intentText}>
                    <Text style={s.intentTitle} numberOfLines={1}>{title}</Text>
                    {item.who ? <Text style={s.intentWho} numberOfLines={1}>{item.who}</Text> : null}
                    <View style={s.tags}>
                      <View style={[s.tag, item.mode === 'hybrid' && s.tagHybrid]}>
                        <Text style={s.tagText}>{mode}</Text>
                      </View>
                      <View style={s.tagNeutral}><Text style={s.tagNeutralText}>{format}</Text></View>
                    </View>
                  </View>
                  {onOpenIntent ? <View style={s.intentChevron}><IconChevronLeft size={19} c={color.neutral400} /></View> : null}
                </Pressable>
              );
            }}
          />
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  topStack: { position: 'absolute', alignItems: 'flex-start', gap: space.sm },
  summary: {
    maxWidth: '100%', minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: space.sm,
    paddingHorizontal: space.lg, borderRadius: radius.full, backgroundColor: color.card, ...shadow.card,
  },
  summaryText: { ...type.body, color: color.fg, flexShrink: 1 } as any,
  unknown: {
    maxWidth: '100%', minHeight: 40, flexDirection: 'row', alignItems: 'center', gap: space.sm,
    paddingHorizontal: space.md, borderRadius: radius.full, backgroundColor: color.card, ...shadow.card,
  },
  unknownDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.neutral400 },
  unknownText: { ...type.bodySmall, color: color.fg, flexShrink: 1 } as any,
  stateCard: {
    position: 'absolute', alignSelf: 'center', top: '38%', width: '82%', maxWidth: 420,
    padding: space.xl, gap: space.sm, alignItems: 'center', borderRadius: radius.xl,
    backgroundColor: color.card, ...shadow.card,
  },
  stateTitle: { ...type.title, color: color.fg, textAlign: 'center' } as any,
  stateNote: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,
  retry: {
    marginTop: space.xs, minHeight: 44, paddingHorizontal: space.xl, borderRadius: radius.full,
    backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center',
  },
  retryText: { ...type.button, color: color.fg } as any,
  sheet: {
    position: 'absolute', maxHeight: 330, paddingTop: space.lg, overflow: 'hidden',
    borderRadius: radius.xxl, backgroundColor: color.card, ...shadow.card,
  },
  sheetHead: {
    flexDirection: 'row', alignItems: 'flex-start', gap: space.md,
    paddingHorizontal: space.lg, paddingBottom: space.md,
  },
  sheetTitleWrap: { flex: 1, gap: 3 },
  sheetTitle: { ...type.title, color: color.fg } as any,
  sheetNote: { ...type.bodySmall, color: color.muted } as any,
  close: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  closeIcon: { transform: [{ rotate: '-90deg' }] },
  list: { flexGrow: 0 },
  listContent: { paddingHorizontal: space.sm, paddingBottom: space.sm },
  intent: {
    minHeight: 76, flexDirection: 'row', alignItems: 'center', gap: space.md,
    paddingHorizontal: space.sm, paddingVertical: space.sm, borderRadius: radius.lg,
  },
  intentPressed: { backgroundColor: color.neutral100 },
  intentAvatar: {
    width: 48, height: 48, borderRadius: 24, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  intentInitial: { ...type.title, color: color.muted } as any,
  intentText: { flex: 1, gap: 2 },
  intentTitle: { ...type.body, color: color.fg } as any,
  intentWho: { ...type.bodySmall, color: color.muted } as any,
  tags: { flexDirection: 'row', alignItems: 'center', gap: space.xs, marginTop: 3 },
  tag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.full, backgroundColor: color.infoBg },
  tagHybrid: { backgroundColor: color.warnBg },
  tagText: { ...type.labelSmall, color: color.fg } as any,
  tagNeutral: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.full, backgroundColor: color.neutral100 },
  tagNeutralText: { ...type.labelSmall, color: color.muted } as any,
  intentChevron: { transform: [{ rotate: '180deg' }] },
});
