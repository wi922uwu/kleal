import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { agent, mediaUrl } from '../src/api';
import { MAP } from '../src/explore';
import { buildOfflineIntentMapModel } from '../src/offline-map-feed';
import { buildOnlineIntentGlobeModel } from '../src/online-intent-globe';
import { confirmedOnlineCountryRows } from '../src/online-map-feed';
import { useLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { IconChevronLeft } from '../src/components/icons';
import { color, radius, shadow, space, type } from '../src/theme';

type IntentDetailItem = {
  id: string;
  title: string;
  who: string;
  photo?: string;
  mode: 'offline' | 'online' | 'hybrid';
  kind: 'one_to_one' | 'group';
  count?: number;
  area?: string;
};

/** Privacy-safe detail for an item opened from Map/List. It reloads by id instead of passing PII in route params. */
export default function MapIntentDetail() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ id?: string; view?: string }>();
  const id = String(params.id || '').trim();
  const feedView = params.view === 'online' ? 'online' : 'offline';
  const lang = useLang();
  const st = useOnb();
  const me = String(st.profile?.name || '').trim();
  const [pin, setPin] = useState<IntentDetailItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (!id || !me) throw new Error('missing identity or intent id');
      const response = await agent.mapFeed(me, feedView);
      let found: IntentDetailItem | null = null;
      if (feedView === 'online') {
        const model = buildOnlineIntentGlobeModel(
          confirmedOnlineCountryRows((response as any)?.items || []),
          { locale: lang },
        );
        for (const country of model.countries) {
          const item = country.intents.find((candidate) => candidate.id === id);
          if (item) {
            found = {
              id: item.id, title: item.title, who: item.who, mode: item.mode,
              kind: item.format === 'group' ? 'group' : 'one_to_one',
              count: item.participantCount, area: country.name,
            };
            break;
          }
        }
        if (!found) {
          const item = model.unknown.find((candidate) => candidate.id === id);
          if (item) found = {
            id: item.id, title: item.title, who: item.who, mode: item.mode,
            kind: item.format === 'group' ? 'group' : 'one_to_one', count: item.participantCount,
          };
        }
      } else {
        const item = buildOfflineIntentMapModel(response).pins.find((candidate) => candidate.id === id);
        if (item) found = {
          id: item.id, title: item.title, who: item.who, photo: item.photo,
          mode: item.mode || 'offline', kind: item.kind || 'one_to_one', count: item.count, area: item.area,
        };
      }
      if (!found) throw new Error('intent is no longer visible');
      setPin(found);
      setFailed(false);
    } catch {
      setPin(null);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [feedView, id, lang, me]);

  useEffect(() => { load(); }, [load]);

  return (
    <View style={s.root}>
      <View style={[s.head, { paddingTop: insets.top + space.sm }]}>
        <Pressable accessibilityRole="button" accessibilityLabel={MAP.back()} onPress={() => router.back()} style={s.back}>
          <IconChevronLeft size={22} c={color.fg} />
        </Pressable>
        <Text style={s.headTitle}>{MAP.intentDetails()}</Text>
        <View style={s.back} />
      </View>

      {loading ? <ActivityIndicator style={s.center} color={color.primary} /> : null}
      {!loading && failed ? (
        <View style={s.centerCard}>
          <Text style={s.title}>{MAP.detailUnavailable()}</Text>
          <Text style={s.note}>{MAP.detailUnavailableNote()}</Text>
          <Pressable accessibilityRole="button" onPress={load} style={s.retry}><Text style={s.retryText}>{MAP.retry()}</Text></Pressable>
        </View>
      ) : null}

      {!loading && pin ? (
        <ScrollView contentContainerStyle={[s.content, { paddingBottom: insets.bottom + space.xl * 2 }]}>
          <View style={s.owner}>
            {pin.photo ? <Image source={{ uri: mediaUrl(pin.photo) }} style={s.avatar} /> : (
              <View style={[s.avatar, s.avatarEmpty]}><Text style={s.avatarInitial}>{(pin.who || '?').slice(0, 1).toUpperCase()}</Text></View>
            )}
            <View style={s.ownerText}>
              <Text style={s.ownerName}>{pin.who || MAP.someone()}</Text>
              <Text style={s.mode}>{pin.mode === 'hybrid' ? MAP.hybrid() : MAP.offline()} · {pin.kind === 'group' ? MAP.group(pin.count || 1) : MAP.oneToOne()}</Text>
            </View>
          </View>
          <View style={s.card}>
            <Text style={s.title}>{pin.title}</Text>
            {pin.area ? <><Text style={s.label}>{feedView === 'online' ? MAP.country() : MAP.meetingPlace()}</Text><Text style={s.address}>{pin.area}</Text></> : null}
          </View>
        </ScrollView>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  head: { paddingHorizontal: space.xl, paddingBottom: space.md, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: color.card },
  headTitle: { ...type.title, color: color.fg } as any,
  center: { flex: 1 },
  centerCard: { margin: space.xl, padding: space.xl, borderRadius: radius.xl, backgroundColor: color.card, gap: space.sm, ...shadow.card },
  content: { padding: space.xl, gap: space.lg },
  owner: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  avatar: { width: 56, height: 56, borderRadius: 28 },
  avatarEmpty: { alignItems: 'center', justifyContent: 'center', backgroundColor: color.neutral100 },
  avatarInitial: { ...type.title, color: color.muted } as any,
  ownerText: { flex: 1, gap: 2 },
  ownerName: { ...type.title, color: color.fg } as any,
  mode: { ...type.bodySmall, color: color.muted } as any,
  card: { padding: space.xl, borderRadius: radius.xxl, backgroundColor: color.card, gap: space.md, ...shadow.card },
  title: { ...type.title, color: color.fg } as any,
  note: { ...type.body, color: color.muted } as any,
  label: { ...type.labelSmall, color: color.muted, textTransform: 'uppercase' } as any,
  address: { ...type.body, color: color.fg } as any,
  retry: { alignSelf: 'flex-start', height: 44, paddingHorizontal: space.lg, borderRadius: radius.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  retryText: { ...type.button, color: color.onPrimary } as any,
});
