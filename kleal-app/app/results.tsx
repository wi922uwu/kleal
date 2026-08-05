/**
 * Выдача — кадры OF.12 «Best fit for your request» и OF.11a «Searching · no matches».
 *
 * Два места, где экран намеренно расходится с борда, и оба — из-за того, как отвечает матчинг:
 *
 *  1. Пустой выдачи почти не бывает. Когда по теме не совпал никто, сервер не возвращает ноль — он
 *     присылает ближайших людей, помеченных `fallback: "alternative"` и полосой «Нужно уточнение».
 *     Заголовок «Лучшее совпадение по запросу» над такой пачкой — прямая неправда, поэтому шапка
 *     смотрит на пометки карточек, а не на их количество.
 *  2. Расширение — лестница §12, ступень за ступенью, и каждая называется вслух. Сервер расширяет
 *     ровно одну ось за раз; какую именно — решает клиент, потому что только он помнит, что уже
 *     пробовали. Молчаливое расширение подменяло бы запрос человека своим.
 *
 * Поля карточки — те, что реально приходят (reasons_ru/en, band_ru/en, readiness_ru/en, km), а не
 * те, которых хотелось бы: `why` и `langs` в ответе матчинга нет.
 */
import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { RESULTS, EXPAND_LADDER, ExpandAxis, axisExplain } from '../src/intent';
import { useLang, T, getLang } from '../src/i18n';
import { takeResults } from '../src/results-store';
import { agent } from '../src/api';
import { IconPerson } from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

type Cand = {
  name?: string;
  age?: number;
  km?: number | null;
  photo?: string;
  verified?: boolean;
  band?: string;
  band_ru?: string;
  band_en?: string;
  reasons_ru?: string[];
  reasons_en?: string[];
  readiness_ru?: string;
  readiness_en?: string;
  fallback?: string;
  interests?: string[];
};

const ru = () => getLang() === 'ru';

export default function Results() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  // Читаем один раз: последующие render'ы не должны затирать уже расширенную выдачу исходной.
  const initial = useMemo(() => takeResults(), []);

  const [intent, setIntent] = useState<any>(initial?.intent || {});
  const [cands, setCands] = useState<Cand[]>(initial?.candidates || []);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  /** Следующая непройденная ступень лестницы. */
  const [rung, setRung] = useState(0);

  const profile = initial?.profile || {};

  // Радиус нечего удваивать, когда встреча онлайн, — эта ступень для такого интента бессмысленна.
  const ladder: ExpandAxis[] = useMemo(
    () => EXPAND_LADDER.filter((a) => !(a === 'radius' && intent?.mode === 'online')),
    [intent?.mode]
  );

  /** Карточки-заменители: тема не совпала ни у кого, показаны просто ближайшие подходящие люди. */
  const onlyFallback = cands.length > 0 && cands.every((c) => !!c.fallback);
  const canWiden = rung < ladder.length && (cands.length === 0 || onlyFallback);

  const widen = async () => {
    const axis = ladder[rung];
    if (!axis) return;
    setBusy(true);
    setNote('');
    try {
      const r: any = await agent.expand(intent, profile, axis);
      const next: Cand[] = (r && r.candidates) || [];
      const km = axis === 'radius' ? (intent?.radiusKm || 15) * 2 : undefined;
      setRung(rung + 1);
      if (next.length) {
        setCands(next);
        // Интент двигаем сами: сервер возвращает только карточки, а следующая ступень должна
        // считаться от уже расширенного запроса, иначе радиус удваивался бы от исходного вечно.
        setIntent((prev: any) => ({
          ...prev,
          ...(axis === 'adjacent' ? { adjacentAllowed: true } : {}),
          ...(axis === 'parent' ? { broadAllowed: true } : {}),
          ...(axis === 'exactness' ? { exactMatchRequired: false } : {}),
          ...(axis === 'radius' ? { radiusKm: km } : {}),
        }));
        setNote(`${axisExplain(axis, km)} ${RESULTS.found(next.length)}`);
      } else {
        setNote(`${axisExplain(axis, km)} ${RESULTS.empty()}`);
      }
    } catch {
      setNote(T('Не получилось расширить. Попробуй ещё раз.', 'Could not widen. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  // Экран открыт напрямую — обновлением страницы или по ссылке. Выдача живёт один переход, и
  // выдумывать её задним числом нечем; честнее сказать это и предложить поискать заново.
  if (!initial) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
            <Text style={s.backIcon}>‹</Text>
          </Pressable>
          <Text style={s.headTitle}>{T('Выдача устарела', 'These results are gone')}</Text>
        </View>
        <View style={s.scroll}>
          <Text style={s.lead}>
            {T('Результаты поиска живут до перезагрузки. Давай поищем заново.',
               'Search results only live until the page reloads. Let’s search again.')}
          </Text>
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.replace('/intent')}>
            <Text style={s.ctaText}>{T('Новый поиск', 'New search')}</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const title = cands.length === 0 ? RESULTS.empty()
              : onlyFallback ? T('Прямых совпадений нет', 'No direct matches')
              : RESULTS.best();

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
          <Text style={s.backIcon}>‹</Text>
        </Pressable>
        <View style={s.avatar} />
        <Text style={s.headTitle}>{title}</Text>
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        {onlyFallback ? (
          <Text style={s.lead}>
            {T('Никто не занимается ровно этим. Вот кто рядом и с кем это может получиться.',
               'Nobody is doing exactly that. Here are people nearby it could work with.')}
          </Text>
        ) : null}

        {note ? <Text style={s.note}>{note}</Text> : null}

        {cands.length === 0 ? <Text style={s.lead}>{RESULTS.emptyNote()}</Text> : null}

        {cands.map((c, i) => <CandCard key={(c.name || '') + i} c={c} />)}

        {canWiden ? (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy }}
            style={[s.cta, busy && { opacity: 0.6 }]}
            onPress={busy ? undefined : widen}
          >
            {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{RESULTS.widen()}</Text>}
          </Pressable>
        ) : null}

        {rung >= ladder.length && (cands.length === 0 || onlyFallback) ? (
          <Text style={s.note}>{RESULTS.exhausted()}</Text>
        ) : null}
      </ScrollView>
    </View>
  );
}

function CandCard({ c }: { c: Cand }) {
  const reasons = (ru() ? c.reasons_ru : c.reasons_en) || [];
  const band = (ru() ? c.band_ru : c.band_en) || '';
  const readiness = (ru() ? c.readiness_ru : c.readiness_en) || '';
  const meta = [c.km != null ? `${c.km} km` : '', band].filter(Boolean).join(' · ');

  return (
    <View style={s.card}>
      <View style={s.cardTop}>
        {c.photo ? (
          <Image source={{ uri: c.photo }} style={s.av} />
        ) : (
          <View style={[s.av, s.avEmpty]}><IconPerson /></View>
        )}
        <View style={{ flex: 1 }}>
          <View style={s.nameRow}>
            <Text style={s.name}>{c.name}{c.age ? `, ${c.age}` : ''}</Text>
            {c.verified ? <Text style={s.verified}>✓</Text> : null}
          </View>
          {meta ? <Text style={s.meta}>{meta}</Text> : null}
        </View>
      </View>

      {reasons.length ? (
        <View style={s.reasons}>
          {reasons.slice(0, 3).map((r, i) => (
            <Text key={i} style={s.reason}>· {r}</Text>
          ))}
        </View>
      ) : null}

      {/*
        Доступность — не украшение: человек «в тихих часах» не ответит сейчас, и лучше знать заранее.
        Подписана словом «связаться» намеренно. Без него на карточке стоят подряд две строки от
        сервера — «открыт(а) к встрече сейчас» и «не сейчас — тихие часы», — и они читаются как
        прямое противоречие. На деле речь о разном: первое про его намерение, вторая про то, дойдёт
        ли до него сообщение прямо сейчас. Одно слово разводит эти два факта.
      */}
      {readiness ? (
        <Text style={s.readiness}>{T('Связаться: ', 'Reach out: ')}{readiness}</Text>
      ) : null}

      {(c.interests || []).length ? (
        <View style={s.tags}>
          {(c.interests || []).slice(0, 4).map((t, i) => (
            <View key={t + i} style={s.tag}><Text style={s.tagText}>{t}</Text></View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: space.md },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  backIcon: { fontSize: 24, color: color.fg, marginTop: -3 },
  avatar: { width: 30, height: 30, borderRadius: 15, backgroundColor: color.primary },
  headTitle: { flex: 1, ...type.title, color: color.fg } as any,

  scroll: { padding: 20, paddingTop: 0, gap: space.md },
  lead: { ...type.body, color: color.muted } as any,
  note: { ...type.bodySmall, color: color.primary } as any,

  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.sm },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  av: { width: 56, height: 56, borderRadius: rad.full },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  name: { ...type.title, color: color.fg } as any,
  verified: { color: color.primary, fontWeight: '700' },
  meta: { ...type.bodySmall, color: color.muted } as any,
  reasons: { gap: 2 },
  reason: { ...type.bodySmall, color: color.fg } as any,
  readiness: { ...type.caption, color: color.muted } as any,
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  tag: { paddingHorizontal: 10, height: 28, borderRadius: rad.full, backgroundColor: color.neutral100, justifyContent: 'center' },
  tagText: { ...type.labelSmall, color: color.muted } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
});
