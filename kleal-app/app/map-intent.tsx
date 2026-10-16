/**
 * Карточка чужого интента — то, что открывается нажатием на пин на карте или на строку в листе.
 *
 * ПОЧЕМУ ЭТОТ ЭКРАН ПЕРЕПИСАН. До этого он показывал три строки: имя, название и район. Всё
 * остальное было нечем показать — лента карты отдавала только их. Выглядело как заглушка, хотя
 * у интента есть и время, и темы, и состав, и то, что автор задумал. Теперь лента везёт рядом с
 * элементом ОТКРЫТУЮ ЧАСТЬ самого интента (см. kleal-ms .../intent_map_feed.py, public_intent),
 * и карточка собирается теми же помощниками, что страница своего интента: `intentTitle`,
 * `intentWhen`, `planWhenLabel`, обложка по теме — один язык на оба экрана, а не вторая,
 * похожая вёрстка.
 *
 * ЧЕГО ЗДЕСЬ НЕТ. Ссылки на онлайн-встречу и собственных слов автора: первое присылают после
 * согласия, второе — разговор с Бадди, а не объявление. Сервер их и не отдаёт.
 *
 * ДЕЙСТВИЕ ОДНО — откликнуться. Это то же приглашение, что с карточки пина на карте
 * (`sendInvite`), поэтому и правило одно: пока ответа нет, второй раз не отправить, а когда
 * переписка уже открыта — кнопка ведёт в неё.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { agent, mediaUrl, ensureMe, isMe } from '../src/api';
import { MAP } from '../src/explore';
import { intentTitle, intentWhen } from '../src/activity';
import { planWhenLabel } from '../src/intent';
import { CategoryGlyph, iconNameFor } from '../src/components/category-icons';
import { sendInvite, inviteTo, useInvites } from '../src/invites';
import { useLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { Cover } from '../src/components/Cover';
import { IconChevronLeft, IconCalendar, IconClock, IconPin, IconGlobe } from '../src/components/icons';
import { color, radius as rad, shadow, space, type } from '../src/theme';

/** Элемент ленты карты: то, что отдаёт /api/agent/map-feed. */
type FeedRow = {
  id: string;
  title?: string;
  mode?: string;
  kind?: string;
  count?: number;
  seatsLeft?: number;
  address?: string;
  country?: string;
  owner?: { id?: string; displayName?: string; photo?: string };
  intent?: any;
};

const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();

export default function MapIntentDetail() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ id?: string; view?: string }>();
  const id = String(params.id || '').trim();
  const feedView = params.view === 'online' ? 'online' : 'offline';
  useLang();
  const st = useOnb();
  const me = String(st.profile?.name || '').trim();
  // Список отправленных приглашений — чтобы не предлагать откликнуться второй раз.
  useInvites(me);

  const [row, setRow] = useState<FeedRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (!id || !me) throw new Error('missing identity or intent id');
      const response: any = await agent.mapFeed(me, feedView);
      const items: FeedRow[] = Array.isArray(response?.items) ? response.items : [];
      const found = items.find((item) => String(item?.id || '') === id) || null;
      if (!found) throw new Error('intent is no longer visible');
      setRow(found);
      setFailed(false);
    } catch {
      setRow(null);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [feedView, id, me]);

  useEffect(() => { load(); }, [load]);
  // Свой id — «моя ли это затея» решается по нему: у тёзок подписи равны. Пришёл — перерисовать.
  const [meKnown, setMeKnown] = useState('');
  useEffect(() => { ensureMe().then(setMeKnown); }, []);

  /**
   * Строка интента в том виде, в каком её читают общие помощники приложения.
   */
  const view = useMemo(() => {
    if (!row) return null;
    const raw = (row.intent && typeof row.intent === 'object' ? row.intent : {}) as any;
    /*
     * У части интентов заполнено только `time` («сб 10:00»), а разбор времени в приложении
     * смотрит в `when`. Подставляем одно вместо другого здесь, а не в разборе: у своей затеи
     * поле всегда своё, и менять общий помощник ради чужой ленты нельзя.
     */
    const intent = { ...raw, when: String(raw.when || raw.time || '') };
    const who = String(row.owner?.displayName || '').trim();
    const whoId = String(row.owner?.id || '').trim();
    const group = String(row.kind || intent.format || '') === 'group';
    const mode = String(row.mode || intent.mode || 'offline');
    /*
     * Место — ТОЛЬКО названный автором адрес встречи. Поля `place`/`area` сюда не годятся: мастер
     * пишет в них ГОРОД ПРОФИЛЯ автора, и под подписью «место встречи» карточка назвала бы его
     * домашний город местом свидания. Сервер их теперь и не присылает. У онлайна место — страна.
     */
    const place = feedView === 'online'
      ? String(row.country || '').trim()
      : String(row.address || intent.address || '').trim();
    return {
      who,
      whoId,
      photo: String(row.owner?.photo || '').trim(),
      group,
      mode,
      count: Math.max(1, Number(row.count) || 1),
      seatsLeft: row.seatsLeft,
      place,
      topics: (Array.isArray(intent.topics) ? intent.topics : []).filter(Boolean).map((t: unknown) => String(t)),
      irow: { id: row.id, title: String(row.title || intent.title || ''), intent },
      mine: !!who && isMe(who, whoId, me),
    };
  }, [row, feedView, me, meKnown]);

  const answered = !!(view && inviteTo({ name: view.who, id: view.whoId }));

  /** Отклик — то же приглашение, что с карточки пина: одно правило на всё приложение. */
  const respond = useCallback(async () => {
    if (!view || sending || view.mine) return;
    setSending(true);
    setErr('');
    try {
      /*
       * Уезжает НАСТОЯЩИЙ интент автора, а не огрызок из двух полей: сервер кладёт его в заявку
       * дословно, и в «Активности» потом видно, на что именно человек откликнулся.
       * `id` НЕ подставляем: по нему считается потолок открытых приглашений (три на СВОЮ затею).
       * Чужой id превратил бы потолок в «три на чужую затею» — правило тихо поменяло бы смысл.
       */
      const r = await sendInvite(me, { name: view.who, id: view.whoId }, {
        ...(view.irow.intent || {}),
        targetIntentId: view.irow.id,
        topics: view.topics,
        place: view.place,
      });
      if (r.ok) setSent(true);
      else setErr(r.capped ? MAP.respondCapped() : MAP.respondFailed());
    } catch {
      setErr(MAP.respondFailed());
    } finally {
      setSending(false);
    }
  }, [me, sending, view]);

  /*
   * Время собирается ИЗ ДАТЫ И МИНУТ тем же кодом, что подписывает свои затеи, — тогда оно на
   * языке смотрящего. Строка `when` идёт в дело, только если разобранного времени нет: у части
   * записей она английская («tomorrow 11:55»), и показывать её всем подряд нельзя.
   */
  const when = useMemo(() => {
    if (!view) return { date: '', time: '' };
    const i = view.irow.intent || {};
    const key = String(i.dateKey || '');
    const minutes = Number(i.minutes);
    if (key && Number.isFinite(minutes)) {
      const label = planWhenLabel(key, minutes);
      const parts = label.split(' · ');
      return { date: parts[0] || label, time: parts[1] || '' };
    }
    return intentWhen(view.irow as any);
  }, [view]);
  const where = view ? view.place : '';
  /*
   * Паспорт собирается здесь, а не общим `intentFacts`: тот показывает ещё и «Аудиторию» — пол
   * и возраст тех, кого автор ищет. Это про поиск и про людей, а не про встречу, и наружу такое
   * не отдаётся вовсе (сервер их и не присылает). Показать вместо настоящего значения «Любой»
   * было бы хуже, чем не показывать строку совсем.
   */
  const facts = useMemo(() => {
    if (!view) return [] as { label: string; value: string }[];
    const i = view.irow.intent || {};
    const out: { label: string; value: string }[] = [];
    out.push({ label: MAP.formatLabel(), value: view.mode === 'online' ? MAP.online()
      : view.mode === 'hybrid' ? MAP.hybrid() : MAP.offline() });
    out.push({ label: MAP.sizeLabel(), value: view.group ? MAP.groupWord() : MAP.oneToOne() });
    if (view.group) {
      const seats = Number(view.seatsLeft);
      const max = Number(i.maxTotal) || Number(i.groupSize) || 0;
      if (max > 0) {
        out.push({ label: MAP.seatsLabel(), value: Number.isFinite(seats) && seats >= 0
          ? MAP.seatsValue(seats, max) : MAP.seatsTotal(max) });
      }
    }
    return out;
  }, [view]);
  const modeLabel = view?.mode === 'online' ? MAP.online()
    : view?.mode === 'hybrid' ? MAP.hybrid() : MAP.offline();

  return (
    <View style={s.root}>
      <View style={[s.head, { paddingTop: insets.top + space.sm }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={MAP.back()}
          onPress={() => (router.canGoBack() ? router.back() : router.replace('/map'))}
          style={s.back}
        >
          <IconChevronLeft size={22} c={color.fg} />
        </Pressable>
        <Text style={s.headTitle}>{MAP.intentDetails()}</Text>
        <View style={s.back} />
      </View>

      {loading ? <ActivityIndicator style={s.center} color={color.primary} /> : null}

      {!loading && failed ? (
        <View style={s.centerCard}>
          <Text style={s.cardTitle}>{MAP.detailUnavailable()}</Text>
          <Text style={s.note}>{MAP.detailUnavailableNote()}</Text>
          <Pressable accessibilityRole="button" onPress={load} style={s.retry}>
            <Text style={s.retryText}>{MAP.retry()}</Text>
          </Pressable>
        </View>
      ) : null}

      {!loading && view ? (
        <>
          <ScrollView contentContainerStyle={[s.body, { paddingBottom: insets.bottom + 132 }]}>
            {/* Обложка по теме — та же, что у затеи в ленте и на своей странице. */}
            <Cover intent={view.irow.intent} style={s.cover} />

            <Text style={s.title}>{intentTitle(view.irow as any)}</Text>

            {/* Автор: лицо и имя вперёд — на встречу идут к человеку, а не к строке. */}
            <View style={s.owner}>
              <View style={s.avatarWrap}>
              {view.photo ? (
                <Image source={{ uri: mediaUrl(view.photo) }} style={s.avatar} />
              ) : (
                <View style={[s.avatar, s.avatarEmpty]}>
                  <Text style={s.avatarInitial}>{(view.who || '?').slice(0, 1).toUpperCase()}</Text>
                </View>
              )}
              {/* Значок темы — как на пине карты: один и тот же знак у одной и той же затеи. */}
              <View style={s.avatarBadge}>
                <CategoryGlyph name={iconNameFor(view.topics[0] || '')} size={12} />
              </View>
              </View>
              <View style={s.ownerText}>
                <Text style={s.ownerName} numberOfLines={1}>{view.who || MAP.someone()}</Text>
                <Text style={s.ownerMeta} numberOfLines={1}>
                  {modeLabel} · {view.group ? MAP.group(view.count) : MAP.oneToOne()}
                </Text>
              </View>
            </View>

            {when.date || when.time ? (
              <View style={s.metaRow}>
                <IconCalendar size={18} c={color.muted} />
                <Text style={s.metaText} numberOfLines={1}>{when.date || when.time}</Text>
                {when.date && when.time ? <IconClock size={18} c={color.muted} /> : null}
                {when.date && when.time ? <Text style={s.metaText} numberOfLines={1}>{when.time}</Text> : null}
              </View>
            ) : null}

            {where ? (
              <View style={s.metaRow}>
                {feedView === 'online'
                  ? <IconGlobe size={18} c={color.muted} />
                  : <IconPin size={18} c={color.muted} />}
                <Text style={s.metaText} numberOfLines={2}>{where}</Text>
              </View>
            ) : null}

            {/* Честная приписка: адрес на карте — место встречи, а не дом; ссылки до согласия нет. */}
            <Text style={s.placeNote}>
              {feedView === 'online' ? MAP.linkAfterYes() : MAP.placeNote()}
            </Text>

            {view.topics.length ? (
              <View style={s.chips}>
                {view.topics.slice(0, 3).map((topic: string) => (
                  <View key={topic} style={s.chip}><Text style={s.chipText}>{topic}</Text></View>
                ))}
              </View>
            ) : null}

            {facts.length ? (
              <View style={s.facts}>
                {facts.map((f) => (
                  <View key={f.label} style={s.fact}>
                    <Text style={s.factLabel}>{f.label}</Text>
                    <Text style={s.factValue} numberOfLines={2}>{f.value}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {err ? <Text style={s.err}>{err}</Text> : null}
          </ScrollView>

          {/* Док внизу — как на странице своей затеи: одно главное действие. */}
          <View style={[s.dock, { paddingBottom: Math.max(insets.bottom, space.md) }]}>
            {view.mine ? (
              <>
                <Text style={s.dockNote}>{MAP.yours()}</Text>
                <Text style={s.dockNote}>{MAP.yoursNote()}</Text>
              </>
            ) : sent || answered ? (
              /*
               * Кнопки «открыть переписку» здесь намеренно нет. Живой разговор в приложении ровно
               * один, и вход в него идёт через проверку занятости (см. results.tsx): вторая дверь
               * в обход этой проверки отменила бы само правило. Отсюда — только честное
               * состояние, а переписка ждёт в «Сообщениях».
               */
              <Text style={s.dockNote}>{MAP.sentWaiting()}</Text>
            ) : (
              <>
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ disabled: sending }}
                  onPress={respond}
                  style={[s.cta, sending && { opacity: 0.6 }]}
                >
                  {sending
                    ? <ActivityIndicator size="small" color={color.onPrimary} />
                    : <Text style={s.ctaText}>{view.group ? MAP.respondToAuthor() : MAP.respond()}</Text>}
                </Pressable>
                {/*
                  У группы это ЗАЯВКА АВТОРУ, а не вход: собрать людей в комнату может только
                  тот, кто её завёл, — иного пути на сервере нет. Обещать кнопкой «вступить»
                  значило бы соврать о том, что произойдёт после нажатия.
                */}
                {view.group ? <Text style={s.dockNote}>{MAP.respondToAuthorNote()}</Text> : null}
              </>
            )}
          </View>
        </>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.bg },
  head: {
    paddingHorizontal: space.lg, paddingBottom: space.xs,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
  },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  headTitle: { ...type.title, color: color.fg } as any,

  center: { marginTop: space.xl },
  centerCard: { margin: space.xl, padding: space.xl, borderRadius: rad.xl, backgroundColor: color.card, gap: space.sm, ...shadow.card },
  cardTitle: { ...type.title, color: color.fg } as any,
  note: { ...type.body, color: color.muted } as any,
  retry: { alignSelf: 'flex-start', height: 44, paddingHorizontal: space.lg, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  retryText: { ...type.button, color: color.onPrimary } as any,

  body: { paddingHorizontal: space.lg, gap: space.sm },
  /*
    Запасной цвет обязателен: если картинка не дошла (российские сети режут чужие адреса),
    компонент снимает и снимок, и затемнение — и без цвета на этом месте осталась бы дыра.
    `overflow` — ради Android: картинка внутри лежит абсолютом и иначе вылезает за скругление.
  */
  cover: { height: 180, borderRadius: rad.lg, backgroundColor: color.coverFallback, overflow: 'hidden' },
  title: { ...type.h2, color: color.fg, marginTop: space.sm } as any,

  owner: { flexDirection: 'row', alignItems: 'center', gap: space.md, marginTop: space.xs },
  avatarWrap: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center' },
  avatarBadge: {
    position: 'absolute', right: -2, bottom: -2, width: 20, height: 20, borderRadius: 10,
    backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: color.bg,
  },
  avatar: { width: 48, height: 48, borderRadius: 24 },
  avatarEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  avatarInitial: { ...type.title, color: color.muted } as any,
  ownerText: { flex: 1, gap: 2 },
  ownerName: { ...type.title, color: color.fg } as any,
  ownerMeta: { ...type.bodySmall, color: color.muted } as any,

  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  metaText: { ...type.body, color: color.muted, flexShrink: 1 } as any,

  placeNote: { ...type.caption, color: color.neutral400, marginTop: 2 } as any,
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.xs },
  chip: { height: 32, paddingHorizontal: space.md, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  chipText: { ...type.labelMedium, color: color.fg } as any,

  facts: { marginTop: space.sm, gap: 2 },
  fact: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 8 },
  factLabel: { width: 104, ...type.bodySmall, color: color.muted } as any,
  factValue: { flex: 1, ...type.bodySmall, color: color.fg } as any,

  err: { marginTop: space.md, ...type.bodySmall, color: color.warnText } as any,

  dock: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    paddingHorizontal: space.lg, paddingTop: space.sm, gap: space.sm, backgroundColor: color.bg,
  },
  dockNote: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,
  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  ctaDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  ctaDarkText: { ...type.button, color: color.onPrimary } as any,
});
