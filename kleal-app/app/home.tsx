/**
 * Главный экран.
 *
 * Порт Agent Home из веба. Обе ленты приходят с сервера:
 *
 *  — групповые мероприятия (/api/agent/groups) — то, к чему можно присоединиться;
 *  — адресованные пользователю 1:1 и групповые приглашения (/api/agent/home-invites).
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
  View, Text, StyleSheet, ScrollView, Pressable, Image,
  ActivityIndicator, RefreshControl, KeyboardAvoidingView, Platform, Keyboard,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import Svg, { Defs, LinearGradient, Stop, Rect } from 'react-native-svg';
import { BottomNav } from '../src/components/BottomNav';
import { CardStack } from '../src/components/CardStack';
import {
  IconBell, IconCalendar, IconClock, IconPin, IconBookmark, IconMic,
  IconChat, IconGroups, IconImagePlaceholder,
} from '../src/components/icons';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { mediaUrl, agent } from '../src/api';
import {
  HOME, splitWhen, planWhere, joinableGroups, homeInvites,
  Group, HomeInvite,
} from '../src/home';
import { color, radius as rad, space, type } from '../src/theme';

export default function Home() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const me = st.profile.name || '';

  const [groups, setGroups] = useState<Group[]>([]);
  const [invites, setInvites] = useState<HomeInvite[]>([]);
  const [inviteError, setInviteError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  /**
   * Высота нижней панели. Меряется, а не задаётся числом: она складывается из своей полосы и
   * безопасной зоны, которая на разных телефонах разная.
   */
  const [navH, setNavH] = useState(96);
  /** Какое приглашение сверху стопки. Живёт в экране: он знает, какие уже разобрали. */
  const [invIdx, setInvIdx] = useState(0);
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

  /** Открытые группы и личные приглашения грузятся независимо друг от друга. */
  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    const [g, i] = await Promise.all([
      agent.groups(me).catch(() => null),
      agent.homeInvites(me).catch(() => null),
    ]);
    setGroups(joinableGroups((g as any)?.groups || []));
    if (i) {
      const next = homeInvites((i as any)?.invites || []);
      setInvites((prev) => {
        // Индекс стопки только РОС и не сбрасывался никогда. `load()` дёргается при каждом
        // возвращении на экран, и после ответа на приглашение список приходит короче — а индекс
        // остаётся прежним: человек видел пустое место там, где лежало новое приглашение.
        // Сбрасываем, когда СОСТАВ изменился; при том же составе позиция сохраняется — иначе
        // возврат с экрана приглашения отбрасывал бы стопку в начало.
        const same = prev.length === next.length
          && prev.every((p, k) => String(p.id) === String(next[k]?.id));
        if (!same) setInvIdx(0);
        return next;
      });
      setInviteError(false);
    } else {
      setInviteError(true);
    }
    setLoading(false);
  }, [me]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  /**
   * Поле на главной — не поле, а кнопка.
   *
   * Печатать тут негде: разговор идёт в чате с Бадди, и набирать первую фразу на одном экране,
   * чтобы дочитать ответ на другом, незачем. Нажатие сразу открывает чат, клавиатура поднимается
   * уже там — под лентой, в которую человек и смотрит.
   */
  const toBuddy = () => router.push('/buddy');

  const myArea = st.profile.city || '';

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
              {groups.length ? (
                <>
                  <Section icon={<IconGroups />} title={HOME.groups()} />
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={s.carousel}
                    snapToInterval={CARD_W + space.md}
                    decelerationRate="fast"
                  >
                    {groups.map((g) => <GroupCard key={g.gid} g={g} myArea={myArea} />)}
                  </ScrollView>
                </>
              ) : null}

              {invites.length || inviteError ? (
                <>
                  <Section icon={<IconBell size={18} />} title={HOME.invites()} />
                  {inviteError ? (
                    <View style={s.inviteError}>
                      <Text style={s.empty}>{HOME.inviteLoadFailed()}</Text>
                      <Pressable accessibilityRole="button" onPress={load} style={s.retryBtn}>
                        <Text style={s.retryText}>{HOME.retry()}</Text>
                      </Pressable>
                    </View>
                  ) : (
                    /*
                      Стопка, а не список — компонент борда «Invite Stack» (GR.01, 350×131 при
                      карточке 350×110). Сверху одно приглашение, за ним видны края остальных.
                      Так и задумано продуктом: 2–4 объяснённых варианта, а не лента, по которой
                      скроллят. Разбирать приглашения по одному — ещё и честнее: решение по
                      каждому человеку принимается отдельно, а не сравнением витрины.
                    */
                    <CardStack
                      items={invites.map((inv) => ({ ...inv, key: String(inv.id) }))}
                      index={invIdx}
                      onNext={() => setInvIdx((n) => n + 1)}
                      emptyHint={invites.length ? HOME.invitesAllSeen() : ''}
                      render={(inv) => (inv.type === 'group'
                        ? <GroupInviteCard inv={inv} />
                        : <DirectInviteCard inv={inv} />
                      )}
                    />
                  )}
                </>
              ) : null}
            </>
          )}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: kb ? 6 : navH + 6 }]}>
          <View style={s.askRow}>
            <View style={s.askAvatar}>
              <IconImagePlaceholder size={22} />
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={HOME.ask()}
              style={({ pressed }) => [s.askField, pressed && { opacity: 0.85 }]}
              onPress={toBuddy}
            >
              <Text style={s.askText}>{HOME.ask()}</Text>
              <IconMic />
            </Pressable>
          </View>
          <Pressable accessibilityRole="button" style={s.hist} onPress={() => router.push('/buddy')}>
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

function DirectInviteCard({ inv }: { inv: HomeInvite }) {
  const router = useRouter();
  const w = splitWhen(inv.intent.when || '');
  const where = inv.intent.area || '';
  const open = () => router.push({ pathname: '/invite', params: { id: inv.id } });
  return (
    <Pressable accessibilityRole="button" onPress={open} style={s.meet}>
      {inv.from.photo ? (
        <Image source={{ uri: mediaUrl(String(inv.from.photo)) }} style={s.meetAva} />
      ) : (
        <View style={[s.meetAva, s.meetAvaEmpty]}>
          <Text style={s.meetInit}>{(inv.from.name || '?').slice(0, 1).toUpperCase()}</Text>
        </View>
      )}
      <View style={{ flex: 1 }}>
        <View style={s.meetTop}>
          <Text style={s.meetName} numberOfLines={1}>
            {inv.from.name}{inv.from.age ? `, ${inv.from.age}` : ''}
          </Text>
          <View style={s.badge}><Text style={s.badgeText}>{HOME.match()}</Text></View>
        </View>
        {inv.intent.title ? <Text style={s.meetIntent} numberOfLines={1}>{inv.intent.title}</Text> : null}
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
        <View style={s.meetBtn}>
          <Text style={s.meetBtnText}>{HOME.review()}</Text>
        </View>
      </View>
    </Pressable>
  );
}

function GroupInviteCard({ inv }: { inv: HomeInvite }) {
  const router = useRouter();
  const group = inv.group;
  const w = splitWhen(inv.intent.when || '');
  // Маршрут называется /ginvite — файл app/ginvite.tsx. Стояло `/group-invite`, которого нет:
  // expo-router на несуществующий путь молча ничего не делает, и карточка приглашения не
  // открывалась вовсе. Заметить это было нельзя, пока лента приглашений сама отдавала 404.
  const open = () => router.push({ pathname: '/ginvite', params: { id: inv.id } });
  const participants = (group?.participants || []).slice(0, 5);
  const hidden = Math.max(0, (group?.participant_count || 0) - participants.length);

  return (
    <Pressable accessibilityRole="button" onPress={open} style={s.groupInvite}>
      <View style={s.groupHero}>
        {group?.cover ? (
          <Image source={{ uri: mediaUrl(String(group.cover)) }} style={StyleSheet.absoluteFillObject} resizeMode="cover" />
        ) : (
          <IconImagePlaceholder size={48} c="#ffffff99" />
        )}
        <View style={s.avatarStack}>
          {participants.map((person, index) => (
            person.photo ? (
              <Image
                key={`${person.name}-${index}`}
                source={{ uri: mediaUrl(String(person.photo)) }}
                style={[s.stackAvatar, { marginLeft: index ? -12 : 0, zIndex: participants.length - index }]}
              />
            ) : (
              <View
                key={`${person.name}-${index}`}
                style={[s.stackAvatar, s.stackAvatarEmpty, { marginLeft: index ? -12 : 0, zIndex: participants.length - index }]}
              >
                <Text style={s.stackInitial}>{(person.name || '?').slice(0, 1).toUpperCase()}</Text>
              </View>
            )
          ))}
          {hidden > 0 ? (
            <View style={[s.stackAvatar, s.stackMore, { marginLeft: participants.length ? -12 : 0 }]}>
              <Text style={s.stackMoreText}>+{hidden}</Text>
            </View>
          ) : null}
        </View>
      </View>

      <View style={s.groupInviteBody}>
        <Text style={s.groupInviteTitle} numberOfLines={2}>
          {inv.intent.title || inv.from.name}
        </Text>
        {/*
          КТО ЗОВЁТ. Имя приглашающего стояло только запасным вариантом заголовка — то есть у
          группы с названием («Книжный клуб») не показывалось нигде. Приглашение при этом
          персональное: человека зовёт человек, и первое, что он хочет знать, — кто.
          Фото и имя сервер присылает в `inv.from`, они просто не доходили до экрана.
        */}
        {inv.from?.name ? (
          <View style={s.inviterRow}>
            <View style={[s.inviterAva, s.inviterAvaEmpty]}>
              <Text style={s.inviterInitial}>{String(inv.from.name).slice(0, 1).toUpperCase()}</Text>
              {inv.from.photo ? (
                <Image source={{ uri: mediaUrl(String(inv.from.photo)) }}
                       style={[s.inviterAva, StyleSheet.absoluteFillObject]} />
              ) : null}
            </View>
            <Text style={s.inviterText} numberOfLines={1}>{HOME.hosting(String(inv.from.name))}</Text>
          </View>
        ) : null}
        <View style={s.inviteBadge}>
          <IconGroups size={16} c={color.successText} />
          <Text style={s.inviteBadgeText}>{HOME.inviteStatus()}</Text>
        </View>
        <View style={s.groupMetaRow}>
          <IconCalendar />
          <Text style={s.groupMeta}>{w.date}</Text>
          {w.time ? <><IconClock /><Text style={s.groupMeta}>{w.time}</Text></> : null}
        </View>
        {inv.intent.area ? (
          <View style={s.groupMetaRow}>
            <IconPin size={18} c={color.muted} />
            <Text style={s.groupMeta} numberOfLines={1}>{inv.intent.area}</Text>
          </View>
        ) : null}
        <Text style={s.groupCount}>
          {HOME.peopleCount(group?.participant_count || 0, group?.max_size)}
        </Text>
        <View style={s.groupInviteBtn}>
          <Text style={s.meetBtnText}>{HOME.review()}</Text>
        </View>
      </View>
    </Pressable>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: '#dcebfa' },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingBottom: space.md },
  hello: { flex: 1, fontSize: 26, lineHeight: 32, fontWeight: '700', color: color.fg },
  bell: {
    width: 42, height: 42, borderRadius: 21, backgroundColor: color.onCoverSoft,
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
  inviteError: { gap: space.sm, alignItems: 'flex-start' },
  retryBtn: { marginLeft: 20, paddingVertical: 8, paddingHorizontal: 14, borderRadius: rad.full, backgroundColor: color.card },
  retryText: { ...type.labelSmall, color: color.primary, fontWeight: '700' } as any,

  carousel: { paddingHorizontal: 20, gap: space.md, paddingVertical: 4 },
  card: {
    width: CARD_W, borderRadius: rad.xl, backgroundColor: color.card, overflow: 'hidden',
    shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 3,
  },
  cover: { height: 128, backgroundColor: color.coverFallback, alignItems: 'center', justifyContent: 'center' },
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

  groupInvite: {
    marginHorizontal: 20, borderRadius: rad.xl, backgroundColor: color.card, overflow: 'hidden',
    shadowColor: '#000', shadowOpacity: 0.09, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 3,
  },
  /**
   * Обложка. 142 пункта пустоты: своей картинки у группового интента нет вовсе (сервер отдаёт
   * `cover` пустой строкой), так что здесь всегда заглушка и ряд аватарок. Из-за её высоты низ
   * карточки — кнопка «Посмотреть приглашение» и строка «Ещё N» — уходил за сгиб экрана: снято
   * на симуляторе. Аватаркам хватает 96; они и есть единственное содержимое этой полосы.
   */
  groupHero: {
    height: 96, backgroundColor: color.coverFallback, alignItems: 'center', justifyContent: 'center',
  },
  /** Кто зовёт — строка под названием. Фото ложится поверх буквы, чтобы медленное фото не оставляло дыру. */
  inviterRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  inviterAva: { width: 24, height: 24, borderRadius: 12, overflow: 'hidden' },
  inviterAvaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  inviterInitial: { fontSize: 11, fontWeight: '700', color: color.muted },
  inviterText: { flex: 1, ...type.bodySmall, color: color.muted } as any,
  avatarStack: {
    position: 'absolute', left: 24, bottom: 14, flexDirection: 'row', alignItems: 'center', minHeight: 58,
  },
  stackAvatar: {
    width: 58, height: 58, borderRadius: 29, borderWidth: 2, borderColor: color.card,
  },
  stackAvatarEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  stackInitial: { fontSize: 19, fontWeight: '700', color: color.muted },
  stackMore: { backgroundColor: color.card, alignItems: 'center', justifyContent: 'center' },
  stackMoreText: { fontSize: 18, fontWeight: '700', color: color.muted },
  groupInviteBody: { padding: 18, gap: 10 },
  groupInviteTitle: { fontSize: 22, lineHeight: 27, fontWeight: '700', color: color.fg },
  inviteBadge: {
    alignSelf: 'flex-start', minHeight: 30, borderRadius: rad.full, paddingHorizontal: 12,
    backgroundColor: color.successBg, flexDirection: 'row', alignItems: 'center', gap: 6,
  },
  inviteBadgeText: { ...type.labelSmall, color: color.successText, fontWeight: '700' } as any,
  groupMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 22 },
  groupMeta: { ...type.body, color: color.muted, flexShrink: 1 } as any,
  groupCount: { ...type.bodySmall, color: color.muted } as any,
  groupInviteBtn: {
    height: 50, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: 2,
  },

  dock: { paddingHorizontal: 16, gap: 8, paddingBottom: 6 },
  askRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  askAvatar: {
    width: 46, height: 46, borderRadius: 23, backgroundColor: color.onCoverSoft,
    alignItems: 'center', justifyContent: 'center',
  },
  askField: {
    flex: 1, height: 50, borderRadius: rad.full, backgroundColor: color.card,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  askText: { flex: 1, color: color.neutral400, fontSize: 15 },
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  hist: {
    alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 8,
    height: 36, paddingHorizontal: 16, borderRadius: rad.full, backgroundColor: color.card,
  },
  histText: { ...type.bodySmall, color: color.fg } as any,
  histArrow: { color: color.primary, fontSize: 18, fontWeight: '700' },
});
