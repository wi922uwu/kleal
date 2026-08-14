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
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter, useLocalSearchParams } from 'expo-router';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { agent, group as gapi, mediaUrl } from '../src/api';
import { searchProfile } from '../src/intent';
import { type Row } from '../src/messages';
import { setResults } from '../src/results-store';
import {
  ACT, CHIP_TONE, INTENT_ID_KEY, PLAN_STATE, chipLabel, ctaLabel, intentState, intentTitle,
  intentWhen, intentWhere, planCard,
  type IntentRow, type PlanCard,
} from '../src/activity';
import { BottomNav } from '../src/components/BottomNav';
import {
  IconChevronLeft, IconCalendar, IconClock, IconPin, IconPencil, IconImagePlaceholder, IconPerson,
  IconSearch, IconCheckCircle,
} from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

type Seg = 'intents' | 'plans' | 'invites' | 'history';

const EMPTY = {
  intents: [] as IntentRow[], outbox: [] as any[],
  plans: [] as any[], history: [] as any[], gplans: [] as any[], ghistory: [] as any[],
  invites: [] as any[],
};

export default function Activity() {
  useLang();
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
  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    try {
      const [ints, out, pl, gpl, inv] = await Promise.all([
        agent.intents(me, searchProfile(st.profile)),
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
    past: [...data.history, ...data.ghistory].map((p: any) => planCard(p, me)),
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
      router.push('/results');
    } catch {
      setErr(ACT.loadFailed());
    } finally {
      setBusy('');
    }
  }, [busy, me, router, st.profile]);

  const openPlan = (c: PlanCard) => {
    if (c.gid) return router.push({ pathname: '/gplan', params: { gid: c.gid } });
    router.push({ pathname: '/plan', params: { id: c.id || '', who: c.who || '', title: c.title } });
  };

  const openInvite = (v: any) =>
    v?.type === 'group'
      ? router.push({ pathname: '/ginvite', params: { id: String(v.id || ''), gid: String(v.group?.gid || '') } })
      : router.push({ pathname: '/invite', params: { id: String(v.id || '') } });

  const segments: [Seg, string, number][] = [
    ['intents', ACT.tabIntents(), 0],
    ['plans', ACT.tabPlans(), 0],
    ['invites', ACT.tabInvites(), data.invites.length],
    ['history', ACT.tabHistory(), 0],
  ];

  const empty = (title: string, note?: string, cta?: () => void) => (
    <View style={s.empty}>
      <Text style={s.emptyTitle}>{title}</Text>
      {note ? <Text style={s.emptyNote}>{note}</Text> : null}
      {cta ? (
        <Pressable accessibilityRole="button" style={s.emptyCta} onPress={cta}>
          <Text style={s.emptyCtaText}>{ACT.create()}</Text>
        </Pressable>
      ) : null}
    </View>
  );

  return (
    <View style={s.wrap}>
      <View style={[s.top, { paddingTop: insets.top + space.sm }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={T('Назад', 'Back')}
          style={s.back}
          onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}
        >
          <IconChevronLeft />
        </Pressable>
        <Text style={s.title} numberOfLines={1}>{ACT.title()}</Text>
        <View style={s.back} />
      </View>

      {/*
        Сегменты по СОДЕРЖИМОМУ, а не равными четвертями. Четвертями «Приглашения» не помещались
        и обрезались в «Приглашен…» — обрезанное слово читается как поломка вёрстки. Полоса при
        этом прокручивается: перевод длиннее уедет вбок, но целым.
      */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={s.segsWrap}
        contentContainerStyle={s.segs}
      >
        {segments.map(([k, label, badge]) => {
          const on = seg === k;
          return (
            <Pressable
              key={k}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              style={[s.seg, on && s.segOn]}
              onPress={() => setSeg(k)}
            >
              <Text style={[s.segText, on && s.segTextOn]} numberOfLines={1}>{label}</Text>
              {badge > 0 ? <View style={s.badge}><Text style={s.badgeText}>{badge}</Text></View> : null}
            </Pressable>
          );
        })}
      </ScrollView>

      <ScrollView
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
            ? data.intents.map((row) => (
                <IntentCard
                  key={row.id}
                  row={row}
                  outbox={data.outbox}
                  busy={busy === row.id}
                  onOpen={() => openSearch(row)}
                  onOpenPage={() => router.push({ pathname: '/myintent', params: { id: row.id } })}
                  onEdit={() => router.push({ pathname: '/myintent', params: { id: row.id, edit: '1' } })}
                />
              ))
            : empty(ACT.emptyIntents(), ACT.emptyIntentsNote(), () => router.push('/create'))
        ) : null}

        {!loading && seg === 'plans' ? (
          plans.live.length
            ? plans.live.map((c) => <PlanBlock key={c.key} card={c} onPress={() => openPlan(c)} />)
            : empty(ACT.emptyPlans())
        ) : null}

        {!loading && seg === 'invites' ? (
          data.invites.length
            ? data.invites.map((v: any) => (
                <PlainRow
                  key={String(v.id)}
                  row={{
                    key: String(v.id), kind: 'invite-in',
                    title: String(v.intent?.title || v.from?.name || ''),
                    sub: [v.from?.name, v.intent?.when].filter(Boolean).join(' · '),
                    photo: v.from?.photo,
                  }}
                  onPress={() => openInvite(v)}
                />
              ))
            : empty(ACT.emptyInvites())
        ) : null}

        {!loading && seg === 'history' ? (
          plans.past.length
            ? plans.past.map((c) => <PlanBlock key={c.key} card={c} onPress={() => openPlan(c)} />)
            : empty(ACT.emptyHistory())
        ) : null}
      </ScrollView>

      <View style={s.nav}><BottomNav active="intents" /></View>
    </View>
  );
}

/** Карточка затеи — «Event Hero Card v2» с кадра: обложка с чипом, название, когда и где, кнопка. */
function IntentCard({
  row, outbox, busy, onOpen, onOpenPage, onEdit,
}: {
  row: IntentRow; outbox: any[]; busy: boolean;
  onOpen: () => void; onOpenPage: () => void; onEdit: () => void;
}) {
  const state = intentState(row, outbox);
  const tone = CHIP_TONE[state];
  const when = intentWhen(row);
  const faces = (row.candidates || []).map((c: any) => String(c?.photo || '')).filter(Boolean).slice(0, 3);
  return (
    /*
      Нажимается ВСЯ карточка, а не только кнопка. На борде стрелка идёт от самой карточки к
      странице затеи, и это единственный разумный жест: человек тычет в название и обложку,
      а не выцеливает кнопку. Кнопка и карандаш внутри остаются своими — вложенное нажатие
      выигрывает у внешнего, и «посмотреть варианты» по-прежнему ведёт в выдачу, а не на страницу.
    */
    /*
      Три разных нажатия — три разных места, как на борде:
        тело карточки → страница затеи в ПРОСМОТРЕ,
        карандаш      → она же сразу в ПРАВКЕ,
        кнопка        → выдача.
      Тело и карандаш вели в одно и то же: карандаш переставал что-либо значить.
    */
    <Pressable style={s.card} accessibilityRole="button" onPress={onOpenPage}>
      <View style={s.cover}>
        <IconImagePlaceholder size={40} c={color.onCoverSoft} />
        {/* Чип цветом называет состояние раньше, чем словом: карточки лежат стопкой. */}
        <View style={[s.chip, s[`chip_${tone}` as 'chip_warn']]}>
          {state === 'options' ? <IconCheckCircle size={13} /> : <IconSearch size={13} c={s[`chipText_${tone}` as 'chipText_warn'].color} />}
          <Text style={[s.chipText, s[`chipText_${tone}` as 'chipText_warn']]}>{chipLabel(state, row, outbox)}</Text>
        </View>
      </View>
      <View style={s.cardBody}>
        <Text style={s.cardTitle} numberOfLines={1}>{intentTitle(row)}</Text>
        <View style={s.meta}>
          <IconCalendar size={16} />
          <Text style={s.metaText} numberOfLines={1}>{when.date}</Text>
          {when.time ? <IconClock size={16} /> : null}
          {when.time ? <Text style={s.metaText} numberOfLines={1}>{when.time}</Text> : null}
        </View>
        <View style={s.meta}>
          <IconPin size={16} c={color.muted} />
          <Text style={s.metaText} numberOfLines={1}>{intentWhere(row)}</Text>
        </View>
        {/*
          Лица с кадра — НАСТОЯЩИЕ: это те, кого поиск уже нашёл по этой затее. Пока не нашёл
          никого, ряд просто не рисуется: три серых кружка означали бы людей, которых нет.
        */}
        <View style={s.foot}>
          {faces.length ? (
            <View style={s.faces}>
              {faces.map((ph, i) => (
                <Image key={i} source={{ uri: mediaUrl(ph) }} style={[s.face, i > 0 && s.faceNext]} />
              ))}
            </View>
          ) : null}
          <Text style={s.footNote} numberOfLines={1}>
            {row.error ? ACT.rankFailed() : ACT.lookingNearby()}
          </Text>
        </View>
        <View style={s.actions}>
          <Pressable
            accessibilityRole="button"
            style={[s.cta, busy && { opacity: 0.6 }]}
            disabled={busy}
            onPress={onOpen}
          >
            {busy ? <ActivityIndicator size="small" color={color.onPrimary} />
              : <Text style={s.ctaText}>{ctaLabel(state)}</Text>}
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel={ACT.edit()} style={s.pencil} onPress={onEdit}>
            <IconPencil size={18} c={color.onPrimary} />
          </Pressable>
        </View>
      </View>
    </Pressable>
  );
}

/** Блок плана — та же карточка, что у затеи: обложка с чипом, название, когда и где, действие. */
function PlanBlock({ card, onPress }: { card: PlanCard; onPress: () => void }) {
  return (
    <Pressable style={s.card} accessibilityRole="button" onPress={onPress}>
      <View style={s.cover}>
        <IconImagePlaceholder size={40} c={color.onCoverSoft} />
        <View style={[s.chip, s[`chip_${card.tone}` as 'chip_warn']]}>
          <Text style={[s.chipText, s[`chipText_${card.tone}` as 'chipText_warn']]}>{card.chip}</Text>
        </View>
      </View>
      <View style={s.cardBody}>
        <Text style={s.cardTitle} numberOfLines={1}>{card.title}</Text>
        <View style={s.meta}>
          <IconCalendar size={16} />
          <Text style={s.metaText} numberOfLines={1}>{card.date}</Text>
          {card.time ? <IconClock size={16} /> : null}
          {card.time ? <Text style={s.metaText} numberOfLines={1}>{card.time}</Text> : null}
        </View>
        <View style={s.meta}>
          <IconPin size={16} c={color.muted} />
          <Text style={s.metaText} numberOfLines={1}>{card.where}</Text>
        </View>
        <View style={s.actions}>
          <Pressable accessibilityRole="button" style={s.cta} onPress={onPress}>
            <Text style={s.ctaText}>{PLAN_STATE.open()}</Text>
          </Pressable>
        </View>
      </View>
    </Pressable>
  );
}

/** Строка для приглашений: там это человек, а не встреча, и карточка была бы не о том. */
function PlainRow({ row, onPress }: { row: Row; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" style={s.row} onPress={onPress}>
      {row.photo
        ? <Image source={{ uri: mediaUrl(row.photo) }} style={s.avatar} />
        : <View style={[s.avatar, s.avatarEmpty]}><IconPerson size={22} /></View>}
      <View style={{ flex: 1 }}>
        <Text style={s.rowTitle} numberOfLines={1}>{row.title}</Text>
        <Text style={s.rowSub} numberOfLines={1}>{row.teaser || row.sub}</Text>
      </View>
    </Pressable>
  );
}

// ===== вид

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  top: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.lg, paddingBottom: space.sm },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, textAlign: 'center', ...type.title, color: color.fg } as any,

  segsWrap: { flexGrow: 0, marginHorizontal: space.lg },
  segs: { padding: 4, borderRadius: rad.full, backgroundColor: color.card, flexDirection: 'row', gap: 2 },
  seg: {
    height: 36, paddingHorizontal: space.md, borderRadius: rad.full,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
  },
  segOn: { backgroundColor: color.primary },
  segText: { ...type.labelSmall, color: color.muted } as any,
  segTextOn: { color: color.onPrimary, fontWeight: '700' },
  badge: { minWidth: 16, height: 16, borderRadius: 8, paddingHorizontal: 4, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  badgeText: { fontSize: 9, fontWeight: '700', color: color.onPrimary },

  list: { paddingHorizontal: space.lg, paddingTop: space.md, gap: space.md },

  card: { borderRadius: rad.lg, backgroundColor: color.card, overflow: 'hidden', ...({} as any) },
  /** Обложек у затей нет ни в API, ни в проекте — та же подложка, что у карточек на главной. */
  cover: { height: 100, backgroundColor: color.coverFallback, alignItems: 'center', justifyContent: 'center' },
  chip: {
    position: 'absolute', left: space.md, top: space.md,
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 10, height: 24, borderRadius: 12,
  },
  chip_warn: { backgroundColor: color.warnBg },
  chip_success: { backgroundColor: color.successBg },
  chip_info: { backgroundColor: color.infoBg },
  chipText: { ...type.labelSmall, fontWeight: '700' } as any,
  chipText_warn: { color: color.warnText },
  chipText_success: { color: color.successText },
  chipText_info: { color: color.infoText },
  cardBody: { padding: space.md, gap: 6 },
  cardTitle: { ...type.title, color: color.fg } as any,
  meta: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  metaText: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  foot: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  faces: { flexDirection: 'row' },
  face: { width: 24, height: 24, borderRadius: 12, backgroundColor: color.neutral100, borderWidth: 2, borderColor: color.card },
  /** Внахлёст, как на кадре: ряд лиц читается как «люди», а не как три отдельных значка. */
  faceNext: { marginLeft: -8 },
  footNote: { ...type.labelSmall, color: color.muted, flexShrink: 1 } as any,
  actions: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginTop: 4 },
  cta: { flex: 1, height: 40, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  /** Тёмный круг, как на кадре: карандаш стоит рядом с красной кнопкой и не должен с ней спорить. */
  pencil: { width: 40, height: 40, borderRadius: 20, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },

  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.md, borderRadius: rad.lg, backgroundColor: color.card },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: color.neutral100 },
  avatarEmpty: { alignItems: 'center', justifyContent: 'center' },
  rowTitle: { ...type.body, color: color.fg, fontWeight: '600' } as any,
  rowSub: { ...type.bodySmall, color: color.muted } as any,

  empty: { alignItems: 'center', gap: space.sm, paddingTop: space.xl * 2, paddingHorizontal: space.lg },
  emptyTitle: { ...type.title, color: color.fg } as any,
  emptyNote: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,
  emptyCta: { marginTop: space.sm, height: 44, paddingHorizontal: space.xl, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  emptyCtaText: { ...type.button, color: color.onPrimary } as any,

  err: { padding: space.md, borderRadius: rad.md, backgroundColor: color.warnBg },
  errText: { ...type.bodySmall, color: color.warnText } as any,

  nav: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
