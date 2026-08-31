/**
 * Поиск на карте — кадры «Search · Map» (1688-27392) и «Search Map · Pin selected» (1834-52500).
 *
 * ЧТО ЗДЕСЬ ПОКАЗАНО. Пин — не человек, а его ОТКРЫТЫЙ ИНТЕНТ: встреча, место которой он назвал
 * сам. Это единственная причина, по которой карта людей вообще допустима: домашняя точка человека
 * клиенту не отдаётся никогда (Вердикт#22, `matching_core/contracts/geo_privacy.py`), а место
 * встречи публикуется осознанно — иначе на неё нельзя прийти. Если сюда когда-нибудь приедет
 * координата человека, а не встречи, — это не новая возможность, а утечка.
 *
 * ПОЧЕМУ ЭКРАН ЗАБИРАЕТ ВКЛАДКУ «ПОИСК». В нижней панели она была приглушена и никуда не вела.
 * Данные для неё лежали готовые: `/api/agent/explore` отдаёт открытые интенты с координатами, и до
 * сих пор её не звал ни один экран.
 *
 * СЕГМЕНТЫ «КАРТА / СПИСОК». Список — это существующая выдача, а не вторая её копия: переключатель
 * уводит на `/results`, чтобы у двух видов не разошлись ни отбор, ни порядок.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, Pressable, Image, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as Location from 'expo-location';
import { agent, mediaUrl } from '../src/api';
import { useOnb } from '../src/state';
import { MAP, ExplorePin, explorePins, stackedAt, centerOf } from '../src/explore';
import { sendInvite } from '../src/invites';
import { ExploreMap } from '../src/components/ExploreMap';
import { BottomNav } from '../src/components/BottomNav';
import {
  IconSearch, IconSliders, IconLocate, IconMap, IconList, IconClock, IconChevronLeft,
} from '../src/components/icons';
import { categoryIcon, iconNameFor } from '../src/components/category-icons';
import { color, radius, shadow, space, type } from '../src/theme';

export default function MapScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const st = useOnb();
  const me = String(st.profile?.name || '').trim();

  const [pins, setPins] = useState<ExplorePin[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [picked, setPicked] = useState<ExplorePin | null>(null);
  const [sending, setSending] = useState(false);
  /** Скрытые «не сейчас» — только на время сеанса: это не отказ, а «убери с глаз». */
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [showMe, setShowMe] = useState(false);
  const [recenter, setRecenter] = useState(0);
  const home = useRef<{ lat: number; lon: number } | null>(null);

  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    try {
      const r: any = await agent.explore(me);
      setPins(explorePins(r?.plans || []));
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [me]);

  useEffect(() => { load(); }, [load]);

  const visible = useMemo(() => pins.filter((p) => !hidden.has(p.id)), [pins, hidden]);
  const stacks = useMemo(() => stackedAt(visible), [visible]);

  /**
   * «Где я». Разрешение спрашивается ТОЛЬКО по нажатию, а не при открытии экрана: карта полезна и
   * без него, а окно системного запроса на первом же кадре читается как требование.
   */
  const locate = useCallback(async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return;
      const pos = await Location.getCurrentPositionAsync({});
      home.current = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      setShowMe(true);
      setRecenter((n) => n + 1);
    } catch {
      /* геопозиция не обязана быть — молча остаёмся там, где стояли */
    }
  }, []);

  const respond = useCallback(async () => {
    if (!picked || sending) return;
    setSending(true);
    try {
      const r = await sendInvite(me, picked.who, { topics: picked.topics, place: picked.area });
      if (r.ok) setPicked(null);
    } finally {
      setSending(false);
    }
  }, [picked, sending, me]);

  const notNow = useCallback(() => {
    if (!picked) return;
    setHidden((s) => new Set(s).add(picked.id));
    setPicked(null);
  }, [picked]);

  const center = home.current || centerOf(visible);

  return (
    <View style={s.root}>
      {/* Карта на всю площадь: панели лежат поверх неё, как на кадре. */}
      <View style={StyleSheet.absoluteFill}>
        <ExploreMap
          pins={visible}
          center={center}
          onPick={setPicked}
          stacks={stacks}
          showMe={showMe}
          recenter={recenter}
          selectedId={picked?.id || null}
        />
      </View>

      {/* Плашка «сколько рядом» — верх кадра. Прячется, когда показывать нечего. */}
      {visible.length ? (
        <View style={[s.summary, { top: insets.top + 8 }]}>
          <View style={s.faces}>
            {visible.slice(0, 3).map((p, i) => (
              <View key={p.id} style={[s.face, i > 0 && { marginLeft: -10 }]}>
                {p.photo ? (
                  <Image source={{ uri: mediaUrl(p.photo) }} style={s.faceImg} />
                ) : (
                  <Text style={s.faceInitial}>{(p.who || '?').slice(0, 1).toUpperCase()}</Text>
                )}
              </View>
            ))}
            {visible.length > 3 ? (
              <View style={[s.face, s.faceMore, { marginLeft: -10 }]}>
                <Text style={s.faceMoreText}>+{visible.length - 3}</Text>
              </View>
            ) : null}
          </View>
          <Text style={s.summaryText} numberOfLines={1}>{MAP.nearby(visible.length)}</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push('/results')}
            style={s.showAll}
          >
            <Text style={s.showAllText}>{MAP.showAll()}</Text>
          </Pressable>
        </View>
      ) : null}

      {loading ? <ActivityIndicator style={[s.spin, { top: insets.top + 90 }]} color={color.primary} /> : null}

      {/* Пусто и сломано — разные состояния: «никого рядом» это не ошибка связи. */}
      {!loading && !visible.length ? (
        <View style={[s.empty, { top: insets.top + 90 }]}>
          <Text style={s.emptyTitle}>{failed ? MAP.failed() : MAP.empty()}</Text>
          <Text style={s.emptyNote}>{failed ? '' : MAP.emptyNote()}</Text>
          {failed ? (
            <Pressable accessibilityRole="button" onPress={load} style={s.retry}>
              <Text style={s.retryText}>{MAP.retry()}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {/* «Где я» — над карточкой выбранного, чтобы она её не накрывала. */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={MAP.locate()}
        onPress={locate}
        style={[s.locate, { bottom: (picked ? 152 + 24 : 0) + 156 + insets.bottom }]}
      >
        <IconLocate size={20} c={color.fg} />
      </Pressable>

      {picked ? <PinPreview pin={picked} sending={sending} onRespond={respond} onNotNow={notNow}
                            onOpen={() => router.push('/results')} bottom={140 + insets.bottom} /> : null}

      {/* Панель поиска и сегменты — низ кадра, над нижней навигацией. */}
      <View style={[s.bar, { bottom: 84 + insets.bottom }]}>
        <Pressable accessibilityRole="button" accessibilityLabel={MAP.search()} style={s.round}>
          <IconSearch size={20} c={color.fg} />
        </Pressable>
        <View style={s.segments}>
          <View style={[s.segment, s.segmentOn]}>
            <IconMap size={18} c={color.onPrimary} />
            <Text style={[s.segmentText, s.segmentTextOn]}>{MAP.map()}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push('/results')}
            style={s.segment}
          >
            <IconList size={18} c={color.onPrimary} />
            <Text style={s.segmentText}>{MAP.list()}</Text>
          </Pressable>
        </View>
        <Pressable accessibilityRole="button" accessibilityLabel={MAP.filters()} style={s.round}>
          <IconSliders size={20} c={color.fg} />
        </Pressable>
      </View>

      {/* Панель прижата к низу абсолютом — как на главной. Всё остальное на этом экране тоже
          абсолютное (оно лежит поверх карты), и в обычном потоке панель всплывала к верхней
          кромке: кнопки были на месте, но не там, где их ищут. */}
      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav active="search" />
      </View>
    </View>
  );
}

/** Карточка выбранного пина — кадр «Pin selected». */
function PinPreview({
  pin, sending, onRespond, onNotNow, onOpen, bottom,
}: {
  pin: ExplorePin;
  sending: boolean;
  onRespond: () => void;
  onNotNow: () => void;
  onOpen: () => void;
  bottom: number;
}) {
  const who = [pin.who, pin.age ? String(pin.age) : ''].filter(Boolean).join(', ');
  return (
    <View style={[s.card, { bottom }]}>
      <Pressable accessibilityRole="button" onPress={onOpen} style={s.cardHead}>
        <View style={s.avatarWrap}>
          {pin.photo ? (
            <Image source={{ uri: mediaUrl(pin.photo) }} style={s.avatar} />
          ) : (
            <View style={[s.avatar, s.avatarEmpty]}>
              <Text style={s.avatarInitial}>{(pin.who || '?').slice(0, 1).toUpperCase()}</Text>
            </View>
          )}
          <View style={s.avatarBadge}>{categoryIcon(iconNameFor(pin.topics[0] || ''), '#fff')}</View>
        </View>
        <View style={s.cardText}>
          <Text style={s.cardWho} numberOfLines={1}>{who || pin.title}</Text>
          <Text style={s.cardTitle} numberOfLines={1}>{pin.title}</Text>
          {pin.when ? (
            <View style={s.metaRow}>
              <IconClock size={16} c={color.muted} />
              <Text style={s.meta} numberOfLines={1}>{pin.when}</Text>
            </View>
          ) : null}
        </View>
        {/* Шеврон смотрит вправо: та же иконка, повёрнутая, — своей в наборе нет. */}
        <View style={s.chev}><IconChevronLeft size={20} c={color.neutral400} /></View>
      </Pressable>
      <View style={s.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: sending }}
          onPress={onRespond}
          style={[s.primary, sending && { opacity: 0.6 }]}
        >
          <Text style={s.primaryText}>{sending ? '…' : 'Respond'}</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={onNotNow} style={s.secondary}>
          <Text style={s.secondaryText}>Not now</Text>
        </Pressable>
      </View>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },

  summary: {
    position: 'absolute', left: space.xl, right: space.xl, height: 64,
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    paddingHorizontal: space.md, borderRadius: radius.xxl,
    backgroundColor: color.card, ...shadow.card,
  },
  faces: { flexDirection: 'row', alignItems: 'center' },
  face: {
    width: 24, height: 24, borderRadius: 12, backgroundColor: color.neutral100,
    borderWidth: 1.5, borderColor: color.card, alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  },
  faceImg: { width: 21, height: 21, borderRadius: 11 },
  faceInitial: { ...type.labelSmall, color: color.muted } as any,
  faceMore: { backgroundColor: color.neutral100 },
  faceMoreText: { ...type.labelSmall, color: color.muted } as any,
  summaryText: { ...type.body, color: color.fg, flex: 1 } as any,
  showAll: {
    height: 40, paddingHorizontal: space.lg, borderRadius: radius.full,
    backgroundColor: color.fg, alignItems: 'center', justifyContent: 'center',
  },
  showAllText: { ...type.button, color: color.onPrimary } as any,

  spin: { position: 'absolute', alignSelf: 'center' },
  empty: {
    position: 'absolute', left: space.xl, right: space.xl,
    padding: space.lg, borderRadius: radius.xl, backgroundColor: color.card, ...shadow.card,
    gap: space.xs,
  },
  emptyTitle: { ...type.title, color: color.fg } as any,
  emptyNote: { ...type.bodySmall, color: color.muted } as any,
  retry: {
    marginTop: space.sm, alignSelf: 'flex-start',
    paddingHorizontal: space.lg, height: 40, borderRadius: radius.full,
    backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center',
  },
  retryText: { ...type.button, color: color.fg } as any,

  locate: {
    position: 'absolute', right: space.xl, width: 44, height: 44, borderRadius: 22,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center', ...shadow.card,
  },

  card: {
    position: 'absolute', left: space.xl, right: space.xl,
    padding: space.lg, borderRadius: radius.xxl, backgroundColor: color.card, ...shadow.card,
    gap: space.md,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  avatarWrap: { width: 60, height: 60, alignItems: 'center', justifyContent: 'center' },
  avatar: { width: 56, height: 56, borderRadius: 28 },
  avatarEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  avatarInitial: { ...type.title, color: color.muted } as any,
  avatarBadge: {
    position: 'absolute', right: 0, bottom: 0, width: 24, height: 24, borderRadius: 12,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: color.card,
  },
  cardText: { flex: 1, gap: 2 },
  cardWho: { ...type.title, color: color.fg } as any,
  cardTitle: { ...type.bodySmall, color: color.muted } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  meta: { ...type.bodySmall, color: color.fg } as any,
  chev: { transform: [{ rotate: '180deg' }] },

  actions: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  primary: {
    flex: 1, height: 48, borderRadius: radius.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  primaryText: { ...type.button, color: color.onPrimary } as any,
  secondary: { flex: 1, height: 48, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { ...type.button, color: color.fg } as any,

  bar: {
    position: 'absolute', left: space.xl, right: space.xl, height: 44,
    flexDirection: 'row', alignItems: 'center', gap: space.sm,
  },
  round: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: color.card,
    alignItems: 'center', justifyContent: 'center', ...shadow.card,
  },
  segments: {
    flex: 1, height: 44, flexDirection: 'row', alignItems: 'center',
    borderRadius: radius.full, backgroundColor: color.fg, padding: 4,
  },
  segment: {
    flex: 1, height: 36, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, borderRadius: radius.full,
  },
  segmentOn: { backgroundColor: color.primary },
  segmentText: { ...type.button, color: color.onPrimary } as any,
  segmentTextOn: { color: color.onPrimary },
});
