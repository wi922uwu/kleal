/**
 * Главный экран.
 *
 * Порт Agent Home из веба. Три ленты, и все три — с сервера:
 *
 *  — групповые мероприятия (/api/agent/groups) — то, к чему можно присоединиться;
 *  — подходящие люди (POST /api/agent/explore) — этот вход строже обычного обзора, он отбирает по
 *    профилю, а не отдаёт всех подряд;
 *  — приглашение (/api/agent/inbox) — первое непросмотренное, остальные за ним.
 *
 * Придуманных карточек здесь нет: по каждой человек нажимает и попадает к живому человеку. Когда
 * сервер ничего не вернул, показывается пустое состояние, а не заглушка, похожая на данные.
 *
 * Фон. На кадре Figma это фотография неба; в вебе она подключена как assets/clouds.jpg, но такого
 * файла на сервере нет — он отдаёт 404, и живой веб показывает голубую заливку. Здесь градиент по
 * тем же цветам: рисовать фотографию, которой нет, не из чего.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, TextInput,
  ActivityIndicator, RefreshControl, KeyboardAvoidingView, Platform, Keyboard,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Svg, { Defs, LinearGradient, Stop, Rect } from 'react-native-svg';
import { BottomNav } from '../src/components/BottomNav';
import {
  IconBell, IconCalendar, IconClock, IconPin, IconBookmark, IconMic, IconPerson,
  IconChat, IconGroups, IconImagePlaceholder,
} from '../src/components/icons';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { agent } from '../src/api';
import {
  HOME, splitWhen, planWhere, joinableGroups, forYouPeople, pendingInvites,
  Group, Person, Invite,
} from '../src/home';
import { color, radius as rad, space, type } from '../src/theme';

export default function Home() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const me = st.profile.name || '';

  const [groups, setGroups] = useState<Group[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [ask, setAsk] = useState('');
  /**
   * Высота нижней панели. Меряется, а не задаётся числом: она складывается из своей полосы и
   * безопасной зоны, которая на разных телефонах разная.
   */
  const [navH, setNavH] = useState(96);
  /**
   * Открыта ли клавиатура.
   *
   * Док отступает снизу на высоту панели, чтобы не налезать на неё. Но когда клавиатура поднимает
   * док, панель уже под клавиатурой — и этот отступ становится пустым зазором, на который ввод
   * улетает выше клавиатуры. Пока клавиатура открыта, отступа нет.
   */
  const [kb, setKb] = useState(false);
  useEffect(() => {
    const ios = Platform.OS === 'ios';
    const show = Keyboard.addListener(ios ? 'keyboardWillShow' : 'keyboardDidShow', () => setKb(true));
    const hide = Keyboard.addListener(ios ? 'keyboardWillHide' : 'keyboardDidHide', () => setKb(false));
    return () => { show.remove(); hide.remove(); };
  }, []);

  /**
   * Три запроса разом, и каждый со своим catch: одна упавшая лента не должна уносить остальные.
   * Пустой ответ и упавший запрос выглядят на экране одинаково — и это правда, потому что в обоих
   * случаях показывать нечего.
   */
  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    const prof = {
      name: me, age: st.profile.age, city: st.profile.city,
      lat: st.profile.geo?.coarseLat, lon: st.profile.geo?.coarseLon,
      interests: st.profile.interests?.explicit || [],
      languages: st.profile.languages || {},
    };
    const [g, f, i] = await Promise.all([
      agent.groups(me).catch(() => null),
      agent.forYou(me, prof).catch(() => null),
      agent.inbox(me).catch(() => null),
    ]);
    setGroups(joinableGroups((g as any)?.groups || []));
    setPeople(forYouPeople((f as any)?.plans || []));
    setInvites(pendingInvites((i as any)?.requests || []));
    setLoading(false);
  }, [me, st.profile]);

  useEffect(() => { load(); }, [me]);

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  /** Свободный текст с главного экрана — тот же вход, что и мастер интента, только сразу словами. */
  const send = () => {
    const q = ask.trim();
    if (!q) return;
    setAsk('');
    router.push({ pathname: '/intent', params: { q } });
  };

  const myArea = st.profile.city || '';
  const inv = invites[0];

  return (
    <View style={s.wrap}>
      <Sky />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={[s.head, { paddingTop: insets.top + 6 }]}>
          <Text style={s.hello}>{HOME.hello(me.split(' ')[0] || T('друг', 'there'))}</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={T('Уведомления', 'Notifications')}
            style={s.bell}
          >
            <IconBell />
            {invites.length ? <View style={s.bellDot} /> : null}
          </Pressable>
        </View>

        <ScrollView
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={color.primary} />}
        >
          {loading ? (
            <ActivityIndicator style={{ marginTop: 40 }} color={color.primary} />
          ) : (
            <>
              <Section icon={<IconGroups />} title={HOME.groups()} />
              {groups.length ? (
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={s.carousel}
                  snapToInterval={CARD_W + space.md}
                  decelerationRate="fast"
                >
                  {groups.map((g) => <GroupCard key={g.gid} g={g} myArea={myArea} />)}
                </ScrollView>
              ) : (
                <Text style={s.empty}>{HOME.noGroups()}</Text>
              )}

              <Section icon={<IconPerson size={18} />} title={HOME.people()} />
              {people.length ? (
                people.map((p, i) => <PersonCard key={(p.intentId || p.who) + i} p={p} myArea={myArea} />)
              ) : (
                <Text style={s.empty}>{HOME.noPeople()}</Text>
              )}

              {inv ? <InviteCard inv={inv} /> : null}
            </>
          )}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: kb ? 6 : navH + 6 }]}>
          <View style={s.askRow}>
            <View style={s.askAvatar}>
              <IconImagePlaceholder size={22} />
            </View>
            <View style={s.askField}>
              <TextInput
                style={s.askInput}
                value={ask}
                onChangeText={setAsk}
                placeholder={HOME.ask()}
                placeholderTextColor={color.neutral400}
                onSubmitEditing={send}
                returnKeyType="send"
              />
              <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send')} onPress={send}>
                <IconMic />
              </Pressable>
            </View>
          </View>
          <Pressable accessibilityRole="button" style={s.hist} onPress={() => router.push('/chat')}>
            <IconChat />
            <Text style={s.histText}>{HOME.history()}</Text>
            <Text style={s.histArrow}>›</Text>
          </Pressable>
        </View>

      </KeyboardAvoidingView>

      {/*
        Панель ВНЕ KeyboardAvoidingView и прибита к низу экрана. Пока она была внутри, клавиатура
        поднимала её вместе с полем ввода — а ей место внизу, под клавиатурой: наверх едет только то,
        что человек в этот момент заполняет.
      */}
      <View
        style={s.navFloat}
        onLayout={(e) => setNavH(e.nativeEvent.layout.height)}
        pointerEvents="box-none"
      >
        <BottomNav />
      </View>
    </View>
  );
}

/** Небо за экраном. Заливка снизу вверх по тем же цветам, что в вебе. */
function Sky() {
  return (
    <Svg style={StyleSheet.absoluteFill} width="100%" height="100%">
      <Defs>
        <LinearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#b9d3ea" />
          <Stop offset="0.45" stopColor="#cfe1f2" />
          <Stop offset="1" stopColor="#dcebfa" />
        </LinearGradient>
      </Defs>
      <Rect x="0" y="0" width="100%" height="100%" fill="url(#sky)" />
    </Svg>
  );
}

function Section({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <View style={s.sec}>
      {icon}
      <Text style={s.secText}>{title}</Text>
    </View>
  );
}

const CARD_W = 300;

function GroupCard({ g, myArea }: { g: Group; myArea: string }) {
  const w = splitWhen(g.when);
  const where = planWhere(g.area, '', myArea);
  return (
    <Pressable accessibilityRole="button" style={s.card}>
      {/* Обложка. Фотографий у планов нет, поэтому цветное поле, а не серый прямоугольник. */}
      <View style={s.cover}>
        <IconImagePlaceholder size={44} c="#ffffff88" />
        <View style={s.bm}><IconBookmark size={18} c={color.fg} /></View>
      </View>
      <View style={s.cardBody}>
        <Text style={s.cardTitle} numberOfLines={1}>{g.title}</Text>
        <View style={s.metaRow}>
          <IconCalendar />
          <Text style={s.meta}>{w.date}</Text>
          {w.time ? <><IconClock /><Text style={s.meta}>{w.time}</Text></> : null}
        </View>
        <View style={s.metaRow}>
          <IconPin size={16} c={color.muted} />
          <Text style={s.meta} numberOfLines={1}>{where}</Text>
        </View>
        <View style={s.foot}>
          {g.size > 0 ? (
            <Text style={s.footText}>{HOME.going(g.size)}</Text>
          ) : (
            <Text style={s.footText}>{HOME.hosting(g.host)}</Text>
          )}
        </View>
      </View>
    </Pressable>
  );
}

function PersonCard({ p, myArea }: { p: Person; myArea: string }) {
  const w = splitWhen(p.when);
  const where = planWhere(p.area, p.dist, myArea);
  return (
    <View style={s.meet}>
      {p.photo ? (
        <Image source={{ uri: p.photo }} style={s.meetAva} />
      ) : (
        <View style={[s.meetAva, s.meetAvaEmpty]}>
          <Text style={s.meetInit}>{(p.who || '?').slice(0, 1).toUpperCase()}</Text>
        </View>
      )}
      <View style={{ flex: 1 }}>
        <View style={s.meetTop}>
          <Text style={s.meetName} numberOfLines={1}>{p.who}{p.age ? `, ${p.age}` : ''}</Text>
          <View style={s.badge}><Text style={s.badgeText}>{HOME.fits()}</Text></View>
        </View>
        {p.title ? <Text style={s.meetIntent} numberOfLines={1}>{p.title}</Text> : null}
        <View style={s.meetMeta}>
          <IconClock />
          <Text style={s.meta}>{w.date}{w.time ? ` · ${w.time}` : ''}</Text>
          <IconPin size={16} c={color.muted} />
          <Text style={s.meta} numberOfLines={1}>{where}</Text>
        </View>
        <Pressable accessibilityRole="button" style={s.meetBtn}>
          <Text style={s.meetBtnText}>{HOME.respond()}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function InviteCard({ inv }: { inv: Invite }) {
  const io = inv.intent || {};
  const w = splitWhen(String(io.when || io.time || ''));
  const where = String(io.area || io.place || '');
  return (
    <View style={s.meet}>
      {inv.photo ? (
        <Image source={{ uri: inv.photo }} style={s.meetAva} />
      ) : (
        <View style={[s.meetAva, s.meetAvaEmpty]}>
          <Text style={s.meetInit}>{(inv.from || '?').slice(0, 1).toUpperCase()}</Text>
        </View>
      )}
      <View style={{ flex: 1 }}>
        <View style={s.meetTop}>
          <Text style={s.meetName} numberOfLines={1}>{inv.from}{inv.age ? `, ${inv.age}` : ''}</Text>
          <View style={s.badge}><Text style={s.badgeText}>{HOME.match()}</Text></View>
        </View>
        <View style={s.meetMeta}>
          {w.date || where ? (
            <>
              <IconClock />
              <Text style={s.meta}>{w.date}{w.time ? ` · ${w.time}` : ''}</Text>
              {where ? <><IconPin size={16} c={color.muted} /><Text style={s.meta} numberOfLines={1}>{where}</Text></> : null}
            </>
          ) : (
            <Text style={s.meta} numberOfLines={1}>{inv.note || HOME.wantsToMeet()}</Text>
          )}
        </View>
        <Pressable accessibilityRole="button" style={s.meetBtn}>
          <Text style={s.meetBtnText}>{HOME.review()}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: '#dcebfa' },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingBottom: space.md },
  hello: { flex: 1, fontSize: 26, lineHeight: 32, fontWeight: '700', color: color.fg },
  bell: {
    width: 42, height: 42, borderRadius: 21, backgroundColor: '#ffffffcc',
    alignItems: 'center', justifyContent: 'center',
  },
  bellDot: {
    position: 'absolute', top: 10, right: 11, width: 8, height: 8,
    borderRadius: 4, backgroundColor: color.primary,
  },

  scroll: { paddingBottom: space.lg, gap: space.sm },
  sec: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 20, marginTop: space.md },
  secText: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  empty: { ...type.bodySmall, color: color.ink, opacity: 0.65, paddingHorizontal: 20 } as any,

  carousel: { paddingHorizontal: 20, gap: space.md, paddingVertical: 4 },
  card: {
    width: CARD_W, borderRadius: rad.xl, backgroundColor: color.card, overflow: 'hidden',
    shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 3,
  },
  cover: { height: 128, backgroundColor: '#e2604f', alignItems: 'center', justifyContent: 'center' },
  bm: {
    position: 'absolute', top: 12, right: 12, width: 30, height: 30, borderRadius: 15,
    backgroundColor: '#ffffffe6', alignItems: 'center', justifyContent: 'center',
  },
  cardBody: { padding: 14, gap: 6 },
  cardTitle: { fontSize: 17, fontWeight: '700', color: color.fg },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  meta: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  foot: { marginTop: 4, paddingTop: 10, borderTopWidth: 1, borderTopColor: color.neutral100 },
  footText: { ...type.bodySmall, color: color.muted } as any,

  meet: {
    flexDirection: 'row', gap: space.md, marginHorizontal: 20, padding: 14,
    borderRadius: rad.xl, backgroundColor: color.card,
    shadowColor: '#000', shadowOpacity: 0.09, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 3,
  },
  meetAva: { width: 62, height: 62, borderRadius: rad.full },
  meetAvaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  meetInit: { fontSize: 22, fontWeight: '700', color: color.muted },
  meetTop: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  meetName: { flex: 1, fontSize: 17, fontWeight: '700', color: color.fg },
  badge: { paddingHorizontal: 10, height: 24, borderRadius: rad.full, backgroundColor: color.successBg, justifyContent: 'center' },
  badgeText: { ...type.labelSmall, color: color.successText, fontWeight: '600' } as any,
  meetIntent: { ...type.bodySmall, color: color.fg, marginTop: 2 } as any,
  meetMeta: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6, flexWrap: 'wrap' },
  meetBtn: {
    height: 44, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: 12,
  },
  meetBtnText: { ...type.button, color: color.onPrimary } as any,

  dock: { paddingHorizontal: 16, gap: 8, paddingBottom: 6 },
  askRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  askAvatar: {
    width: 46, height: 46, borderRadius: 23, backgroundColor: '#ffffffcc',
    alignItems: 'center', justifyContent: 'center',
  },
  askField: {
    flex: 1, height: 50, borderRadius: rad.full, backgroundColor: color.card,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  askInput: { flex: 1, color: color.fg, fontSize: 15 },
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  hist: {
    alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 8,
    height: 36, paddingHorizontal: 16, borderRadius: rad.full, backgroundColor: color.card,
  },
  histText: { ...type.bodySmall, color: color.fg } as any,
  histArrow: { color: color.primary, fontSize: 18, fontWeight: '700' },
});
