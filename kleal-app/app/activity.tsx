/**
 * «Моя активность» — кадр C.02, вкладка «Интенты» нижней панели.
 *
 * UX-КАРКАС: вид натянется поверх. Копия и вывод состояний — в src/activity.ts; оформление одним
 * блоком внизу файла, только на токенах темы.
 *
 * Четыре сегмента с кадра — это ЧЕТЫРЕ СТАДИИ одной затеи, а не четыре разных списка:
 *
 *   Интенты      — то, что ищет людей прямо сейчас;
 *   Планы        — то, о чём уже договорились (парные и групповые вместе);
 *   Приглашения  — то, что ждёт ответа от МЕНЯ;
 *   История      — то, что закончилось.
 *
 * Списки собираются теми же функциями, что и «Сообщения» (src/messages.ts): данные под вкладками
 * общие, и вторая их сборка разошлась бы с первой на первой же правке. Разное — куда ведёт строка.
 * В «Сообщениях» она открывает РАЗГОВОР, здесь — САМУ ЗАТЕЮ: план, приглашение, интент.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter, useLocalSearchParams } from 'expo-router';
import { useLang, T, getLang } from '../src/i18n';
import { splitWhen } from '../src/home';
import { useOnb } from '../src/state';
import { agent, group as gapi, mediaUrl } from '../src/api';
import { searchProfile } from '../src/intent';
import { type Row } from '../src/messages';
import { setResults } from '../src/results-store';
import { openResults } from '../src/results-navigation';
import {
  ACT, CHIP_TONE, INTENT_ID_KEY, PLAN_STATE, chipLabel, ctaLabel, intentState, intentTitle,
  intentWhen, intentWhere, planCard,
  type IntentRow, type PlanCard,
} from '../src/activity';
import { BottomNav } from '../src/components/BottomNav';
import {
  IconCalendar, IconClock, IconPin, IconPencil, IconPerson, IconGlobe, IconWand,
} from '../src/components/icons';
import { color, radius as rad, space, type, heading } from '../src/theme';
import { GlassBack, GlassSurface } from '../src/components/LiquidGlass';
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { Cover } from '../src/components/Cover';
import { useNavCollapse } from '../src/navScroll';

type Seg = 'intents' | 'plans' | 'invites' | 'history';

const EMPTY = {
  intents: [] as IntentRow[], outbox: [] as any[],
  plans: [] as any[], history: [] as any[], gplans: [] as any[], ghistory: [] as any[],
  invites: [] as any[],
};

export default function Activity() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const me = String(st.profile.name || '');

  /**
   * Сегмент можно открыть сразу — `/activity?seg=history`. Иначе кнопка «Открыть историю» с
   * главной приводила бы на экран и просила человека самому найти нужную вкладку: обещание в
   * названии кнопки и то, что он видит, обязаны совпадать.
   */
  const params = useLocalSearchParams<{ seg?: string }>();
  const asked = String(params.seg || '') as Seg;
  const [seg, setSeg] = useState<Seg>(
    ['intents', 'plans', 'invites', 'history'].includes(asked) ? asked : 'intents'
  );
  const [data, setData] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');

  /**
   * Одно чтение на все четыре сегмента. Переключение вкладки не ходит на сервер: человек
   * щёлкает по ним подряд, и четыре запроса на четыре щелчка — это ожидание там, где его быть
   * не должно.
   *
   * Групповые ручки со своим `catch`: групповой слой новее остальных, и его неудача не должна
   * уносить список, который работает. Тот же приём, что в «Сообщениях».
   */
  /** Номер чтения: пересчёт, догнавший экран после следующего чтения, не должен его перебить. */
  const loadSeq = useRef(0);
  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    const seq = ++loadSeq.current;
    try {
      /*
        СНАЧАЛА ПОКАЗАТЬ, ПОТОМ ДОСЧИТАТЬ. Список интентов с `live` ранжирует каждый заново — по две
        секунды на штуку, и вкладка стояла за вертушкой 10 секунд при пяти затеях, при каждом
        заходе (замерено). Остальные четыре ручки отвечают за десятки миллисекунд, но ждали его.
        Теперь первым идёт мгновенный снимок последнего пересчёта (сервер помнит его), экран
        рисуется сразу, а свежий пересчёт приезжает вторым запросом и подменяет строки.
      */
      const [ints, out, pl, gpl, inv] = await Promise.all([
        agent.intents(me, searchProfile(st.profile), false),
        agent.outbox(me),
        agent.plans(me),
        gapi.plans(me).catch(() => null),
        agent.homeInvites(me).catch(() => null),
      ]);
      const arr = (r: any, k: string) => (Array.isArray(r) ? r : r?.[k] || []);
      setData({
        intents: ((ints as any)?.intents || []) as IntentRow[],
        outbox: arr(out, 'requests'),
        plans: (pl as any)?.plans || [],
        history: (pl as any)?.history || [],
        gplans: (gpl as any)?.plans || [],
        ghistory: (gpl as any)?.history || [],
        invites: (inv as any)?.invites || [],
      });
      setErr('');
      setLoading(false);
      // Второй проход — живой пересчёт. Строки подменяются только если это всё ещё то же чтение.
      agent.intents(me, searchProfile(st.profile), true).then((live: any) => {
        if (seq !== loadSeq.current) return;
        const rows = (live?.intents || []) as IntentRow[];
        if (rows.length) setData((d) => ({ ...d, intents: rows }));
      }).catch(() => { /* снимок уже на экране — тихо */ });
    } catch {
      setErr(ACT.loadFailed());
    } finally {
      setLoading(false);
    }
  }, [me, st.profile]);

  // Возврат на вкладку — повод перечитать: пока человек отвечал на приглашение, список устарел.
  useFocusEffect(useCallback(() => { load(); }, [load]));

  /**
   * Планы — КАРТОЧКАМИ, теми же, что затеи. Строкой с аватаркой план выглядел как переписка, а
   * ведёт он в саму встречу: одинаковый вид у разных вещей обманывает ожидание вернее, чем
   * неточное слово. Разбор общий для парных и групповых — для человека это одна встреча.
   */
  const plans = useMemo(() => ({
    live: [...data.plans, ...data.gplans].map((p: any) => planCard(p, me)),
    // Признак «это история» — здесь, а не в ответе сервера: в историю план уходит и по
    // возрасту, оставаясь «подтверждённым», и карточка иначе светит зелёным про прошедшее.
    past: [...data.history, ...data.ghistory].map((p: any) => planCard(p, me, true)),
  }), [data, me]);

  /**
   * Кнопка карточки. Выдача НЕ передаётся параметрами маршрута — она большая, и на вебе это 431;
   * поэтому поиск повторяется по сохранённому интенту, кладётся в общий склад и экран выдачи
   * забирает её оттуда. Открытый напрямую он честно скажет «выдача устарела».
   */
  const openSearch = useCallback(async (row: IntentRow) => {
    if (busy) return;
    setBusy(row.id);
    try {
      /**
       * Затея едет в выдачу ПОМЕЧЕННОЙ своим id. Дальше метка идёт сама: выдача отдаёт этот же
       * объект отправке приглашения, отправка кладёт его в заявку, и по нему карточка потом
       * находит свои неотвеченные — «ждём 2 ответа». Иначе связать заявку с затеей нечем:
       * сервер хранит в заявке копию объекта, но не ссылку на интент.
       */
      const stamped = { ...(row.intent || {}), [INTENT_ID_KEY]: row.id };
      const prof = searchProfile(st.profile);
      const r: any = await agent.match(stamped, prof, { self: me });
      /**
       * Склад заполняется ПОЛЕМ ЗА ПОЛЕМ, а не россыпью ответа сервера. Россыпью я и ошибся:
       * `{...r, intent}` выглядит полным, но профиля в ответе матчинга нет — а выдача берёт из
       * склада именно его, и из него имя отправителя. Пустое имя обрывало отправку приглашения
       * на первой же проверке, и человек видел «не отправилось», хотя связь была в порядке.
       * Проверить это типами нельзя: расплывание `any` в литерал прячет недостающие поля.
       */
      setResults({
        intent: stamped,
        candidates: r?.candidates || [],
        profile: prof,
        query: intentTitle(row),
      });
      openResults(router);
    } catch {
      setErr(ACT.loadFailed());
    } finally {
      setBusy('');
    }
  }, [busy, me, router, st.profile]);

  const openPlan = (c: PlanCard) => {
    if (c.gid) return router.navigate({ pathname: '/gplan', params: { gid: c.gid } });
    router.navigate({ pathname: '/plan', params: { id: c.id || '', who: c.who || '', who_id: c.whoId || '', title: c.title } });
  };

  /** Из карточки истории — прямо в переписку с тем, с кем встречались. У группы это комната. */
  const openChat = (c: PlanCard) => {
    if (c.gid) return router.navigate({ pathname: '/group', params: { gid: c.gid } });
    router.navigate({ pathname: '/conversation', params: { who: c.who || '', who_id: c.whoId || '', title: c.title } });
  };

  const openInvite = (v: any) =>
    v?.type === 'group'
      ? router.navigate({ pathname: '/ginvite', params: { id: String(v.id || ''), gid: String(v.group?.gid || '') } })
      : router.navigate({ pathname: '/invite', params: { id: String(v.id || '') } });

  const segments: [Seg, string, number][] = [
    ['intents', ACT.tabIntents(), 0],
    ['plans', ACT.tabPlans(), 0],
    ['invites', ACT.tabInvites(), data.invites.length],
    ['history', ACT.tabHistory(), 0],
  ];

  /** C.01a–C.04a: пусто — заголовок и пояснение слева, у затей ещё «Talk to Kleal». */
  const empty = (title: string, note: string, cta?: () => void) => (
    <View style={s.empty}>
      <Text style={s.emptyTitle}>{title}</Text>
      <Text style={s.emptyNote}>{note}</Text>
      {cta ? (
        <Pressable accessibilityRole="button" style={s.emptyCta} onPress={cta}>
          <Text style={s.ctaText}>{ACT.talkToKleal()}</Text>
        </Pressable>
      ) : null}
    </View>
  );

  return (
    <View style={s.wrap}>
      {/* Фирменный фон «Ambient · glass pilot» — тот же слой, что на входных экранах. */}
      <Ambient glows={GLOW_FORM} />
      {/* C.01: стеклянная «назад» и название слева, как у остальных экранов нового вида. */}
      <View style={[s.top, { paddingTop: insets.top + 6 }]}>
        <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))} />
        <Text style={[s.title, heading(lang, type.headingSm)]} numberOfLines={1}>{ACT.titleNew()}</Text>
      </View>

      {/* Четыре отдельные пилюли, а не одна дорожка: так на кадре, и длинный перевод не режется. */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.segsWrap} contentContainerStyle={s.segs}>
        {segments.map(([k, label, badge]) => {
          const on = seg === k;
          const inner = (
            <>
              <Text style={[s.segText, on && s.segTextOn]} numberOfLines={1}>{label}</Text>
              {badge > 0 ? (
                <View style={[s.badge, on && s.badgeOn]}><Text style={[s.badgeText, on && s.badgeTextOn]}>{badge}</Text></View>
              ) : null}
            </>
          );
          return (
            <Pressable key={k} style={{ flexGrow: 1 }} accessibilityRole="button" accessibilityState={{ selected: on }} onPress={() => setSeg(k)}>
              {on ? <View style={[s.seg, s.segOn]}>{inner}</View>
                : <GlassSurface tone="light" radius={999} style={s.seg}>{inner}</GlassSurface>}
            </Pressable>
          );
        })}
      </ScrollView>

      <ScrollView onScroll={navCollapse} scrollEventThrottle={16}
        contentContainerStyle={[s.list, { paddingBottom: insets.bottom + 120 }]}
        refreshControl={<RefreshControl refreshing={false} onRefresh={load} tintColor={color.muted} />}
      >
        {loading ? <ActivityIndicator color={color.muted} style={{ marginTop: space.xl }} /> : null}
        {err ? (
          <Pressable accessibilityRole="button" style={s.err} onPress={load}>
            <Text style={s.errText}>{err} {ACT.retry()}</Text>
          </Pressable>
        ) : null}

        {!loading && seg === 'intents' ? (
          data.intents.length
            ? data.intents.map((row) => {
                const state = intentState(row, data.outbox);
                const when = intentWhen(row);
                const faces = (row.candidates || []).map((c: any) => String(c?.photo || '')).filter(Boolean);
                return (
                  <ActCard
                    key={row.id}
                    cover={{ intent: row?.intent || row }}
                    chip={{ label: chipLabel(state, row, data.outbox), tone: CHIP_TONE[state] }}
                    title={intentTitle(row)}
                    date={when.date} time={when.time}
                    place={intentWhere(row)} call={String(row?.intent?.mode || '') === 'online'}
                    status={{ photo: faces[0], text: row.error ? ACT.rankFailed() : ACT.lookingNearby() }}
                    primary={{ label: ctaLabel(state), onPress: () => openSearch(row), busy: busy === row.id }}
                    extra={{ label: ACT.edit(), onPress: () => router.navigate({ pathname: '/myintent', params: { id: row.id, edit: '1' } }) }}
                    onPress={() => router.navigate({ pathname: '/myintent', params: { id: row.id } })}
                  />
                );
              })
            : empty(ACT.emptyIntentsTitle(), ACT.emptyIntentsBoard(), () => router.navigate('/buddy'))
        ) : null}

        {!loading && seg === 'plans' ? (
          plans.live.length
            ? plans.live.map((c) => (
                <ActCard
                  key={c.key}
                  cover={{ sub: c.sub }}
                  chip={{ label: c.chip, tone: c.tone }}
                  title={c.title} date={c.date} time={c.time}
                  place={c.mode === 'online' ? ACT.onCall() : c.where} call={c.mode === 'online'}
                  status={{ text: c.state === 'confirmed' || c.state === 'locked'
                    ? (c.mode === 'online' || c.mode === 'hybrid' ? ACT.planFixedCall() : ACT.planFixed())
                    : ACT.planAgreeing(), plain: true }}
                  primary={{ label: ACT.goToPlan(), onPress: () => openPlan(c) }}
                  onPress={() => openPlan(c)}
                />
              ))
            : empty(ACT.emptyPlans(), ACT.emptyPlansNote())
        ) : null}

        {!loading && seg === 'invites' ? (
          data.invites.length
            ? data.invites.map((v: any) => {
                const who = [v.from?.name, v.from?.age].filter(Boolean).join(', ');
                const when = splitWhen(String(v.intent?.when || ''));
                const online = String(v.intent?.mode || '') === 'online';
                return (
                  <ActCard
                    key={String(v.id)}
                    cover={{ intent: v.intent || {} }}
                    chip={{ label: ACT.chipNew(), tone: 'info' }}
                    title={ACT.invitedYou(who || String(v.intent?.title || ''))}
                    date={v.intent?.when ? when.date : ''} time={v.intent?.when ? when.time : ''}
                    place={online ? ACT.onCall() : ACT.afterAccept(String(v.intent?.area || v.intent?.district || ''))}
                    call={online}
                    status={{ photo: v.from?.photo, text: ACT.pickedYou() }}
                    primary={{ label: ACT.reviewInvite(), onPress: () => openInvite(v) }}
                    onPress={() => openInvite(v)}
                  />
                );
              })
            : empty(ACT.emptyInvitesTitle(), ACT.emptyInvitesNote())
        ) : null}

        {!loading && seg === 'history' ? (
          plans.past.length
            ? plans.past.map((c) => {
                const off = c.state === 'cancelled' || c.state === 'below_quorum';
                /* C.04: у встречи один на один без моего ответа — «Leave feedback»; у группы, что не
                   собралась, — «Plan it again with Kleal»; иначе — к записи плана. */
                const text = off ? (c.gid ? ACT.didntStart(Math.max(0, c.count), c.need) : ACT.cancelledNote())
                  : c.gid ? '' : c.answered ? ACT.oneToOne() : ACT.oneToOneNoFeedback();
                const soft = off ? { label: ACT.planAgain(), onPress: () => router.navigate('/buddy'), wand: true }
                  : !c.gid && !c.answered ? { label: ACT.leaveFeedback(), onPress: () => openPlan(c) }
                  : c.who ? { label: PLAN_STATE.openChat(), onPress: () => openChat(c) }
                  : { label: PLAN_STATE.open(), onPress: () => openPlan(c) };
                return (
                  <ActCard
                    key={c.key}
                    cover={{ sub: c.sub }}
                    chip={{ label: off ? ACT.chipClosed() : ACT.chipDone(), tone: off ? 'muted' : 'success' }}
                    title={c.title} date={c.date} time={c.time}
                    place={c.mode === 'online' ? ACT.onCall() : c.where} call={c.mode === 'online'}
                    status={text ? { text, plain: true } : undefined}
                    soft={soft}
                    onPress={() => openPlan(c)}
                  />
                );
              })
            : empty(ACT.emptyHistoryTitle(), ACT.emptyHistoryNote())
        ) : null}
      </ScrollView>

      <View style={s.nav}><BottomNav active="intents" /></View>
    </View>
  );
}

type Tone = 'warn' | 'success' | 'info' | 'muted';

/**
 * Карточка вкладок C.01–C.04 — одна на всё: обложка с чипом справа, название, когда, где,
 * строка состояния (лицо и текст) и кнопки. Разные вкладки отличаются только тем, что в неё кладут.
 */
function ActCard({
  cover, chip, title, date, time, place, call, status, primary, soft, extra, onPress,
}: {
  cover: { intent?: any; sub?: string };
  chip: { label: string; tone: Tone };
  title: string; date: string; time: string; place: string; call?: boolean;
  status?: { photo?: string; text: string; plain?: boolean };
  primary?: { label: string; onPress: () => void; busy?: boolean };
  soft?: { label: string; onPress: () => void; wand?: boolean };
  extra?: { label: string; onPress: () => void };
  onPress: () => void;
}) {
  return (
    <Pressable style={s.card} accessibilityRole="button" onPress={onPress}>
      <Cover intent={cover.intent} sub={cover.sub} style={s.cover}>
        <View style={[s.chip, s[`chip_${chip.tone}` as 'chip_warn']]}>
          <Text style={[s.chipText, s[`chipText_${chip.tone}` as 'chipText_warn']]} numberOfLines={1}>{chip.label}</Text>
        </View>
      </Cover>
      <View style={s.cardBody}>
        <Text style={s.cardTitle} numberOfLines={1}>{title}</Text>
        {date || time ? (
          <View style={s.meta}>
            {date ? <IconCalendar size={16} c={color.primary} /> : null}
            {date ? <Text style={s.metaText} numberOfLines={1}>{date}</Text> : null}
            {time ? <IconClock size={16} c={color.primary} /> : null}
            {time ? <Text style={s.metaText} numberOfLines={1}>{time}</Text> : null}
          </View>
        ) : null}
        {place ? (
          <View style={s.meta}>
            {call ? <IconGlobe size={16} c={color.primary} /> : <IconPin size={16} c={color.primary} />}
            <Text style={s.metaText} numberOfLines={1}>{place}</Text>
          </View>
        ) : null}
        {status ? (
          <View style={s.meta}>
            {status.plain ? null : status.photo
              ? <Image source={{ uri: mediaUrl(status.photo) }} style={s.face} />
              : <View style={[s.face, s.faceEmpty]}><IconPerson size={12} /></View>}
            <Text style={s.metaText} numberOfLines={1}>{status.text}</Text>
          </View>
        ) : null}
        {primary || soft || extra ? (
          <View style={s.actions}>
            {primary ? (
              <Pressable accessibilityRole="button" style={[s.cta, primary.busy && { opacity: 0.6 }]}
                         disabled={primary.busy} onPress={primary.onPress}>
                {primary.busy ? <ActivityIndicator size="small" color={color.onPrimary} />
                  : <Text style={s.ctaText}>{primary.label}</Text>}
              </Pressable>
            ) : null}
            {soft ? (
              <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={soft.onPress}>
                {soft.wand ? <IconWand size={16} c={color.fg} /> : null}
                <Text style={s.ctaSoftText}>{soft.label}</Text>
              </Pressable>
            ) : null}
            {extra ? (
              <Pressable accessibilityRole="button" accessibilityLabel={extra.label} style={s.pencil} onPress={extra.onPress}>
                <IconPencil size={18} c={color.onPrimary} />
              </Pressable>
            ) : null}
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

// ===== вид

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  top: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: space.lg, paddingBottom: space.sm },
  title: { flex: 1, color: color.fg } as any,

  segsWrap: { flexGrow: 0 },
  /** Пилюли тянутся на всю ширину, как на кадре; не влезает перевод — полоса прокручивается. */
  segs: { flexGrow: 1, paddingHorizontal: space.lg, paddingVertical: 4, gap: 8, flexDirection: 'row' },
  seg: {
    height: 36, paddingHorizontal: 16, borderRadius: rad.full,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
  },
  segOn: { backgroundColor: color.primary },
  segText: { ...type.labelSmall, color: color.fg } as any,
  segTextOn: { color: color.onPrimary, fontWeight: '700' },
  badge: { minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 5, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  badgeOn: { backgroundColor: color.onPrimary },
  badgeText: { fontSize: 10, fontWeight: '700', color: color.onPrimary },
  badgeTextOn: { color: color.primary },

  list: { paddingHorizontal: space.lg, paddingTop: space.md, gap: space.md },

  card: { borderRadius: rad.lg, backgroundColor: color.glassCard, overflow: 'hidden' },
  cover: { height: 128, backgroundColor: color.coverFallback },
  /** Чип справа сверху, как на кадре C.01–C.04. */
  chip: {
    position: 'absolute', right: space.md, top: space.md,
    paddingHorizontal: 10, height: 22, borderRadius: 11, justifyContent: 'center',
  },
  chip_warn: { backgroundColor: color.warnBg },
  chip_success: { backgroundColor: color.successBg },
  chip_info: { backgroundColor: color.infoBg },
  chip_muted: { backgroundColor: color.neutral100 },
  chipText: { ...type.labelSmall, fontWeight: '600' } as any,
  chipText_warn: { color: color.warnText },
  chipText_success: { color: color.successText },
  chipText_info: { color: color.infoText },
  chipText_muted: { color: color.muted },
  cardBody: { padding: space.md, gap: 8 },
  cardTitle: { ...type.title, color: color.fg } as any,
  meta: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  metaText: { ...type.bodySmall, color: color.fg, flexShrink: 1 } as any,
  face: { width: 24, height: 24, borderRadius: 12, backgroundColor: color.neutral100 },
  faceEmpty: { alignItems: 'center', justifyContent: 'center' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginTop: 4 },
  cta: { flex: 1, height: 40, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  ctaSoft: {
    flex: 1, height: 40, borderRadius: rad.full, backgroundColor: color.card, flexDirection: 'row', gap: 6,
    borderWidth: 1, borderColor: color.border, alignItems: 'center', justifyContent: 'center',
  },
  ctaSoftText: { ...type.button, color: color.fg } as any,
  pencil: { width: 40, height: 40, borderRadius: 20, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },

  /** C.01a–C.04a: пустое состояние слева, сразу под вкладками. */
  empty: { gap: 4, paddingTop: space.xs },
  emptyTitle: { ...type.title, color: color.fg } as any,
  emptyNote: { ...type.bodySmall, color: color.fg } as any,
  emptyCta: { marginTop: space.md, height: 48, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },

  err: { padding: space.md, borderRadius: rad.md, backgroundColor: color.warnBg },
  errText: { ...type.bodySmall, color: color.warnText } as any,

  nav: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
