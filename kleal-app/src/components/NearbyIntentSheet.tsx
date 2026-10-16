/**
 * Список интентов рядом — лист над картой города по нажатию лупы.
 *
 * Тот же лист, что и у планеты («Онлайн»), только светлый: над бежевой картой тёмное стекло
 * читалось бы дырой. Геометрия, жест смахивания и тайминги общие с ним (420/300 мс — планета
 * и лист там едут вместе, здесь просто та же рука). Карточка повторяет карточку пина на карте:
 * кружок с фотографией или буквой, значок темы, название, имя и время, район, шеврон.
 * Нажатие открывает интент — как у пина.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated, Easing, FlatList, Image, PanResponder, Pressable, StyleSheet, Text, View,
} from 'react-native';
import { mediaUrl } from '../api';
import { MAP, type ExplorePin } from '../explore';
import { CategoryGlyph, iconNameFor } from './category-icons';
import { IconChevronLeft, IconClock, IconLocate } from './icons';
import { color, radius as rad, shadow, space, type } from '../theme';

const SHEET_SHARE = 0.58;
const OPEN_MS = 420;
const CLOSE_MS = 300;
const EASE = Easing.bezier(0.45, 0, 0.55, 1);

export function NearbyIntentSheet({
  pins, open, onClose, onOpen, navClear, onSheet,
}: {
  pins: ExplorePin[];
  open: boolean;
  onClose: () => void;
  onOpen: (pin: ExplorePin) => void;
  /** Сколько снизу занимает нижняя навигация: лист заканчивается над ней. */
  navClear: number;
  /** Сколько пикселей снизу закрыл лист — экран прячет свою панель. */
  onSheet?: (bottom: number) => void;
}) {
  const [layoutH, setLayoutH] = useState(0);
  const slide = useRef(new Animated.Value(0)).current;
  const sheetH = Math.max(300, Math.round(layoutH * SHEET_SHARE));

  useEffect(() => {
    Animated.timing(slide, { toValue: open ? 1 : 0, duration: open ? OPEN_MS : CLOSE_MS, easing: EASE, useNativeDriver: true }).start();
    onSheet?.(open ? sheetH : 0);
  }, [open, sheetH, slide, onSheet]);

  const sheetHRef = useRef(sheetH); sheetHRef.current = sheetH;
  const closeRef = useRef(onClose); closeRef.current = onClose;
  const dragFrom = useRef(1);
  const settle = useCallback(() => {
    Animated.timing(slide, { toValue: 1, duration: 220, easing: EASE, useNativeDriver: true }).start();
  }, [slide]);
  const pan = useRef(PanResponder.create({
    onMoveShouldSetPanResponder: (_, g) => g.dy > 6 && Math.abs(g.dy) > Math.abs(g.dx) * 1.4,
    onPanResponderGrant: () => { slide.stopAnimation((v: number) => { dragFrom.current = v; }); },
    onPanResponderMove: (_, g) => {
      slide.setValue(Math.max(0, Math.min(1, dragFrom.current - g.dy / Math.max(1, sheetHRef.current))));
    },
    onPanResponderRelease: (_, g) => {
      if (g.dy > sheetHRef.current * 0.25 || g.vy > 0.6) closeRef.current(); else settle();
    },
    onPanResponderTerminate: () => settle(),
  })).current;

  return (
    <View style={s.root} pointerEvents="box-none" onLayout={(e) => setLayoutH(e.nativeEvent.layout.height)}>
      <Animated.View
        pointerEvents={open ? 'auto' : 'none'}
        style={[s.sheet, { height: sheetH, paddingBottom: navClear, transform: [{ translateY: slide.interpolate({ inputRange: [0, 1], outputRange: [sheetH, 0] }) }] }]}
      >
        <View {...pan.panHandlers}>
          <View style={s.grip} />
          <View style={s.head}>
            <View style={{ flex: 1 }}>
              <Text style={s.title} numberOfLines={1}>{MAP.nearbyList()}</Text>
              <Text style={s.sub} numberOfLines={1}>{MAP.nearby(pins.length)}</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel={MAP.close()} onPress={onClose} hitSlop={10} style={s.close}>
              <Text style={s.x}>✕</Text>
            </Pressable>
          </View>
        </View>

        <FlatList
          data={pins}
          keyExtractor={(p) => p.id}
          contentContainerStyle={{ paddingBottom: space.md }}
          showsVerticalScrollIndicator={false}
          renderItem={({ item }) => {
            const who = [item.who, item.age ? String(item.age) : ''].filter(Boolean).join(', ');
            return (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={MAP.openIntent()}
                onPress={() => onOpen(item)}
                style={({ pressed }) => [s.card, pressed && s.cardPressed]}
              >
                <View style={s.avatarWrap}>
                  {item.photo ? (
                    <Image source={{ uri: mediaUrl(item.photo) }} style={s.avatar} />
                  ) : (
                    <View style={[s.avatar, s.avatarEmpty]}>
                      <Text style={s.avatarInitial}>{(item.who || '?').slice(0, 1).toUpperCase()}</Text>
                    </View>
                  )}
                  <View style={s.avatarBadge}><CategoryGlyph name={iconNameFor(item.topics[0] || '')} size={10} /></View>
                </View>
                <View style={s.cardText}>
                  <Text style={s.cardTitle} numberOfLines={1}>{item.title}</Text>
                  <Text style={s.cardWho} numberOfLines={1}>{who}</Text>
                  <View style={s.metaRow}>
                    {item.when ? (<><IconClock size={13} c={color.muted} /><Text style={s.meta} numberOfLines={1}>{item.when}</Text></>) : null}
                    {item.area ? (<><IconLocate size={13} c={color.muted} /><Text style={[s.meta, { flexShrink: 1 }]} numberOfLines={1}>{item.area}</Text></>) : null}
                  </View>
                </View>
                <View style={s.chev}><IconChevronLeft size={18} c={color.neutral400} /></View>
              </Pressable>
            );
          }}
        />
      </Animated.View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0 },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: color.card,
    borderTopLeftRadius: rad.xxl, borderTopRightRadius: rad.xxl,
    paddingTop: 12, ...shadow.card,
  },
  grip: { width: 40, height: 4, borderRadius: 2, backgroundColor: color.neutral400, opacity: 0.5, alignSelf: 'center', marginBottom: 6 },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, marginBottom: 8 },
  title: { fontSize: 18, fontWeight: '700', color: color.fg } as any,
  sub: { ...type.caption, color: color.muted } as any,
  close: { width: 30, height: 30, borderRadius: 15, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  x: { fontSize: 14, color: color.fg },

  card: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    marginHorizontal: 12, marginBottom: 6, paddingVertical: 8, paddingLeft: 10, paddingRight: 6,
    borderRadius: rad.lg, backgroundColor: color.neutral100,
  },
  cardPressed: { opacity: 0.75 },
  avatarWrap: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  avatar: { width: 38, height: 38, borderRadius: 19 },
  avatarEmpty: { backgroundColor: color.card, alignItems: 'center', justifyContent: 'center' },
  avatarInitial: { ...type.labelMedium, fontSize: 15, color: color.muted } as any,
  avatarBadge: {
    position: 'absolute', right: -2, bottom: -2, width: 16, height: 16, borderRadius: 8,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1.5, borderColor: color.neutral100,
  },
  cardText: { flex: 1, gap: 1 },
  cardTitle: { ...type.body, fontWeight: '600', lineHeight: 20, color: color.fg } as any,
  cardWho: { ...type.caption, color: color.muted } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 1 },
  meta: { ...type.caption, color: color.fg, marginRight: 6 } as any,
  chev: { transform: [{ rotate: '180deg' }] },
});
