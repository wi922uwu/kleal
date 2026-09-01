/**
 * Страница затеи — кадры C.02a (режим правки) и «States of My Intent page» (searching / options).
 *
 * UX-КАРКАС: вид натянется поверх. Копия — в src/activity.ts и src/intent.ts; оформление одним
 * блоком внизу файла, только на токенах темы.
 *
 * ОДИН ЭКРАН НА ВСЕ СОСТОЯНИЯ, а не три маршрута. На борде это три разных кадра, но человек
 * смотрит на одну и ту же затею — меняется только строка под названием и надпись на кнопке.
 * Разводить их значило бы, что, глядя на свою затею, он каждый раз оказывается где-то ещё.
 *
 * Правки — листы поверх этой же страницы (C.02b/C.02d/C.02e), а не отдельные экраны: так на
 * борде, и так честнее — из правки видно, что именно правишь.
 *
 * Чего здесь НЕТ и почему:
 *   — обложки: ни в API, ни в проекте картинок затеи не существует, стоит та же заглушка, что
 *     на карточке в списке;
 *   — блока «Option 1 / Option 2 · N people ready to go» с кадра: сгруппированных вариантов
 *     времени и места не отдаёт ни одна ручка — ни у пары, ни у группы план ровно один. Кнопка
 *     ведёт в выдачу кандидатов, где выбор настоящий;
 *   — правки района: её блок (карта, радиус, адрес) живёт внутри мастера и наружу не вынесен;
 *     вторая копия разошлась бы с первой на первой же правке. Район здесь показан, но не правится.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { agent } from '../src/api';
import {
  DETAILS, EDIT_SHEET, SUMMARY_O10, dateChips, hhmm, planWhenLabel, timeQueryFromDate,
  searchProfile,
} from '../src/intent';
import { setResults } from '../src/results-store';
import { openResults } from '../src/results-navigation';
import {
  ACT, INTENT_ID_KEY, ctaLabel, intentFacts, intentState, intentSummary, intentTitle, intentWhen,
  intentWhere, stateLine,
  type IntentRow,
} from '../src/activity';
import { EditSheet } from '../src/components/ProfileShell';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { TimeDial, RangeDial } from '../src/components/Dials';
import { IconChevronLeft, IconCalendar, IconClock, IconPin, IconPencil, IconImagePlaceholder } from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

type Sheet = 'none' | 'when' | 'who' | 'summary';

/**
 * ДВА РЕЖИМА ОДНОЙ СТРАНИЦЫ, а не один экран на всё. На борде это разные кадры, и разница не
 * косметическая:
 *   просмотр (C.07) — карандашей НЕТ, зато есть состав и «идут N»; внизу «Групповой чат»
 *                     и круглый карандаш, который и включает правку;
 *   правка  (C.02a) — карандаши у четырёх строк, состава нет; внизу «Открыть поиск» и «Отмена».
 *
 * «Отмена» выходит ИЗ ПРАВКИ, а не со страницы: каждый лист применяет своё сразу, поэтому
 * отменять ей нечего — она возвращает страницу в спокойный вид.
 */
type Mode = 'view' | 'edit';

const SUMMARY_MAX = 300;

export default function MyIntent() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх экрана — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const me = String(st.profile.name || '');
  const params = useLocalSearchParams<{ id?: string; edit?: string }>();
  const id = String(params.id || '').trim();

  const [row, setRow] = useState<IntentRow | null>(null);
  const [outbox, setOutbox] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [sheet, setSheet] = useState<Sheet>('none');
  /** Карандаш на карточке открывает страницу СРАЗУ в правке — так на борде идёт стрелка. */
  const [mode, setMode] = useState<Mode>(params.edit === '1' ? 'edit' : 'view');
  const [asking, setAsking] = useState(false);

  /** Черновик листа. Заводится при открытии и до «Применить» никуда не уходит. */
  const [dateKey, setDateKey] = useState('');
  const [minutes, setMinutes] = useState(20 * 60);
  const [sex, setSex] = useState('Any');
  const [minAge, setMinAge] = useState(18);
  const [maxAge, setMaxAge] = useState(35);
  const [summary, setSummary] = useState('');

  /**
   * Отдельной ручки «один интент» на сервере нет — берём список и находим свой. Дороже, чем
   * хотелось бы (сервер пересчитывает кандидатов по каждой затее), но это единственный путь, а
   * кандидаты нужны и здесь: из них считается состояние.
   */
  const load = useCallback(async () => {
    if (!me || !id) { setLoading(false); return; }
    try {
      const [ints, out] = await Promise.all([
        agent.intents(me, searchProfile(st.profile)),
        agent.outbox(me),
      ]);
      const found = (((ints as any)?.intents || []) as IntentRow[]).find((r) => r.id === id) || null;
      setRow(found);
      setOutbox(Array.isArray(out) ? out : (out as any)?.requests || []);
      setErr(found ? '' : ACT.loadFailed());
    } catch {
      setErr(ACT.loadFailed());
    } finally {
      setLoading(false);
    }
  }, [id, me, st.profile]);

  useEffect(() => { load(); }, [load]);

  const state = useMemo(() => (row ? intentState(row, outbox) : 'searching'), [row, outbox]);
  const facts = useMemo(() => (row ? intentFacts(row) : []), [row]);
  const when = row ? intentWhen(row) : { date: '', time: '' };

  /** Записать изменённый интент целиком: частичной правки на сервере нет, id обязателен. */
  const save = useCallback(async (patch: Record<string, any>) => {
    if (!row) return;
    const next = { ...(row.intent || {}), ...patch };
    setRow({ ...row, intent: next });          // на экране — сразу, ждать сервер незачем
    setSheet('none');
    try {
      await agent.intentSave(me, next, String(row.title || ''), row.id);
      load();                                   // перечитать: состояние могло поменяться вместе с полями
    } catch {
      setErr(ACT.loadFailed());
    }
  }, [load, me, row]);

  const openSearch = useCallback(async () => {
    if (!row || busy) return;
    setBusy(true);
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
      setBusy(false);
    }
  }, [busy, me, row, router, st.profile]);

  /**
   * Уйти из своей затеи можно только совсем: она твоя, «выходить» из неё не из чего. Спрашиваем
   * подтверждение — удаление необратимо, мягкого архива у интентов на сервере нет.
   */
  const removeIntent = useCallback(async () => {
    if (!row) return;
    setAsking(false);
    try {
      const r: any = await agent.intentDelete(me, row.id);
      if (!r?.ok) throw new Error('delete failed');
      router.dismissTo('/home'); router.navigate('/activity');
    } catch {
      setErr(ACT.removeFailed());
    }
  }, [me, row, router]);

  const openWhen = () => {
    const i = row?.intent || {};
    setDateKey(String(i.dateKey || dateChips(8)[0]?.key || ''));
    setMinutes(Number(i.minutes) || 20 * 60);
    setSheet('when');
  };
  const openWho = () => {
    const i = row?.intent || {};
    setSex(String(i.sex || 'Any'));
    setMinAge(Number(i.minAge) || 18);
    setMaxAge(Number(i.maxAge) || 35);
    setSheet('who');
  };
  /**
   * Лист правки открывается ЗАПОЛНЕННЫМ — своей сводкой, а если её ещё нет, той, что собралась
   * сама. Пустое поле здесь означало бы «напиши сам», а Kleal везде сначала пишет за человека,
   * и правка идёт поверх написанного.
   */
  const openSummary = () => {
    setSummary(row ? intentSummary(row) : '');
    setSheet('summary');
  };

  const chips = useMemo(() => dateChips(8), []);

  return (
    <View style={s.wrap}>
      <View style={[s.top, { paddingTop: insets.top + space.sm }]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={T('Назад', 'Back')}
          style={s.back}
          onPress={() => (router.canGoBack() ? router.back() : router.replace('/activity'))}
        >
          <IconChevronLeft />
        </Pressable>
        <View style={s.back} />
      </View>

      {loading ? <ActivityIndicator color={color.muted} style={{ marginTop: space.xl }} /> : null}

      {!loading && !row ? (
        <View style={s.empty}>
          <Text style={s.emptyTitle}>{err || ACT.loadFailed()}</Text>
          <Pressable accessibilityRole="button" style={s.emptyCta} onPress={() => { router.dismissTo('/home'); router.navigate('/activity'); }}>
            <Text style={s.emptyCtaText}>{ACT.title()}</Text>
          </Pressable>
        </View>
      ) : null}

      {row ? (
        <>
          {/* Двухкнопочный док выше однокнопочного — запас считаем от него, иначе сводка уезжает под него. */}
          <ScrollView contentContainerStyle={[s.body, { paddingBottom: insets.bottom + 200 }]}>
            <View style={s.cover}><IconImagePlaceholder size={56} /></View>

            <Text style={s.title}>{intentTitle(row)}</Text>
            <Text style={s.stateLine}>{stateLine(state)}</Text>

            <Pressable
              accessibilityRole="button"
              style={s.metaRow}
              onPress={mode === 'edit' ? openWhen : undefined}
            >
              <IconCalendar size={18} />
              <Text style={s.metaText} numberOfLines={1}>{when.date}</Text>
              {when.time ? <IconClock size={18} /> : null}
              {when.time ? <Text style={s.metaText} numberOfLines={1}>{when.time}</Text> : null}
              <View style={{ flex: 1 }} />
              {mode === 'edit' ? <IconPencil size={16} /> : null}
            </Pressable>

            <View style={s.metaRow}>
              <IconPin size={18} c={color.muted} />
              <Text style={s.metaText} numberOfLines={1}>{intentWhere(row)}</Text>
            </View>

            <View style={s.facts}>
              {facts.map((f) => (
                <Pressable
                  key={f.label}
                  accessibilityRole={mode === 'edit' && f.label === DETAILS.audience() ? 'button' : undefined}
                  style={s.fact}
                  onPress={mode === 'edit' && f.label === DETAILS.audience() ? openWho : undefined}
                >
                  <Text style={s.factLabel}>{f.label}</Text>
                  <Text style={s.factValue} numberOfLines={1}>{f.value}</Text>
                  {mode === 'edit' && f.label === DETAILS.audience() ? <IconPencil size={14} /> : null}
                </Pressable>
              ))}
            </View>

            {/* На кадре это подпись и текст, а не карточка с подложкой. */}
            <Pressable
              accessibilityRole="button"
              style={s.summary}
              onPress={mode === 'edit' ? openSummary : undefined}
            >
              <View style={s.summaryHead}>
                <Text style={s.summaryLabel}>{SUMMARY_O10.summaryLabel()}</Text>
                {mode === 'edit' ? <IconPencil size={16} /> : null}
              </View>
              <Text style={s.summaryText}>{intentSummary(row)}</Text>
            </Pressable>

            {err ? <Text style={s.err}>{err}</Text> : null}
          </ScrollView>

          <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb, space.md) }]}>
            {/* Просмотр: главное действие и круглый карандаш рядом — он включает правку. */}
            {mode === 'view' ? (
              <View style={s.dockRow}>
                <Pressable
                  accessibilityRole="button"
                  style={[s.cta, { flex: 1 }, busy && { opacity: 0.6 }]}
                  disabled={busy}
                  onPress={openSearch}
                >
                  {busy ? <ActivityIndicator size="small" color={color.onPrimary} />
                    : <Text style={s.ctaText}>{ctaLabel(state)}</Text>}
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={ACT.edit()}
                  style={s.fab}
                  onPress={() => setMode('edit')}
                >
                  <IconPencil size={20} c={color.onPrimary} />
                </Pressable>
              </View>
            ) : null}

            {mode === 'edit' ? (
            <Pressable
              accessibilityRole="button"
              style={[s.cta, busy && { opacity: 0.6 }]}
              disabled={busy}
              onPress={openSearch}
            >
              {busy ? <ActivityIndicator size="small" color={color.onPrimary} />
                : <Text style={s.ctaText}>{ctaLabel(state)}</Text>}
            </Pressable>
            ) : null}
            {/*
              «Отмена» выходит ИЗ ПРАВКИ, а не со страницы: листы применяют своё сразу, отменять
              к этому моменту нечего. Она возвращает страницу в спокойный вид — без карандашей.
            */}
            {mode === 'edit' ? (
              <>
                <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setMode('view')}>
                  <Text style={s.ctaDarkText}>{DETAILS.cancel()}</Text>
                </Pressable>
                {/* Единственный выход из своей затеи — убрать её совсем. Стоит в правке, не на виду. */}
                <Pressable accessibilityRole="button" style={s.removeBtn} onPress={() => setAsking(true)}>
                  <Text style={s.removeText}>{ACT.remove()}</Text>
                </Pressable>
              </>
            ) : null}
          </View>
        </>
      ) : null}

      <EditSheet
        open={asking}
        title={ACT.removeTitle()}
        onClose={() => setAsking(false)}
        onAccept={removeIntent}
        acceptLabel={ACT.remove()}
        cancelLabel={ACT.keep()}
      >
        <Text style={s.summaryText}>{ACT.removeNote()}</Text>
      </EditSheet>

      {/* C.02b — дата и время. Часового пояса на кадре нет: у уже заведённой затеи он не меняется. */}
      <EditSheet
        open={sheet === 'when'}
        title={EDIT_SHEET.datetime()}
        onClose={() => setSheet('none')}
        onAccept={() => save({
          dateKey, minutes,
          time: timeQueryFromDate(dateKey, minutes),
          when: planWhenLabel(dateKey, minutes),
        })}
        acceptLabel={DETAILS.apply()}
      >
        <View style={s.chips}>
          {chips.map((c) => (
            <Pressable
              key={c.key}
              accessibilityRole="button"
              accessibilityState={{ selected: dateKey === c.key }}
              style={[s.chip, dateKey === c.key && s.chipOn]}
              onPress={() => setDateKey(c.key)}
            >
              <Text style={[s.chipText, dateKey === c.key && s.chipTextOn]}>{c.label}</Text>
            </Pressable>
          ))}
        </View>
        <TimeDial minutes={minutes} onChange={setMinutes} />
        {/* Числа под кругом — не украшение: на циферблате минуты читаются приблизительно. */}
        <View style={s.boxes}>
          <View style={s.box}><Text style={s.boxText}>{hhmm(minutes).slice(0, 2)}</Text></View>
          <Text style={s.boxSep}>:</Text>
          <View style={s.box}><Text style={s.boxText}>{hhmm(minutes).slice(3)}</Text></View>
        </View>
      </EditSheet>

      {/* C.02d — аудитория и возраст. */}
      <EditSheet
        open={sheet === 'who'}
        title={EDIT_SHEET.audience()}
        onClose={() => setSheet('none')}
        onAccept={() => save({
          sex: sex === 'Any' ? undefined : sex,
          minAge, maxAge,
        })}
        acceptLabel={DETAILS.apply()}
      >
        <View style={s.chips}>
          {/* Значения — как в SEXES (src/onboarding.ts): их читает и матчинг, и паспорт затеи. */}
          {([['Any', T('Любой', 'Any is fine')], ['Female', T('Женщины', 'Female')], ['Male', T('Мужчины', 'Male')]] as const)
            .map(([k, label]) => (
              <Pressable
                key={k}
                accessibilityRole="button"
                accessibilityState={{ selected: sex === k }}
                style={[s.chip, sex === k && s.chipOn]}
                onPress={() => setSex(k)}
              >
                <Text style={[s.chipText, sex === k && s.chipTextOn]}>{label}</Text>
              </Pressable>
            ))}
        </View>
        <RangeDial lo={minAge} hi={maxAge} onChange={(lo, hi) => { setMinAge(lo); setMaxAge(hi); }} />
        <View style={s.boxes}>
          <View style={s.box}><Text style={s.boxText}>{minAge}</Text></View>
          <Text style={s.boxSep}>–</Text>
          <View style={s.box}><Text style={s.boxText}>{maxAge}</Text></View>
        </View>
      </EditSheet>

      {/* C.02e — сводка Kleal. Хранится внутри самого интента: отдельного поля под неё сервер
          не заводит, а объект интента он хранит дословно. */}
      <EditSheet
        open={sheet === 'summary'}
        title={SUMMARY_O10.summaryLabel()}
        onClose={() => setSheet('none')}
        onAccept={() => save({ summary: summary.trim() })}
        acceptLabel={DETAILS.apply()}
        cancelLabel={DETAILS.cancel()}
      >
        <TextInput
          style={s.area}
          value={summary}
          onChangeText={(t) => setSummary(t.slice(0, SUMMARY_MAX))}
          multiline
          textAlignVertical="top"
          placeholder={SUMMARY_O10.summaryLabel()}
          placeholderTextColor={color.neutral400}
        />
        <Text style={s.counter}>{summary.length}/{SUMMARY_MAX}</Text>
      </EditSheet>
    </View>
  );
}

// ===== вид

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  top: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.lg, paddingBottom: space.xs },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },

  body: { paddingHorizontal: space.lg, gap: space.sm },
  cover: { height: 180, borderRadius: rad.lg, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  title: { ...type.h2, color: color.fg, marginTop: space.sm } as any,
  stateLine: { ...type.bodySmall, color: color.primary } as any,

  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  metaText: { ...type.body, color: color.muted, flexShrink: 1 } as any,

  facts: { marginTop: space.sm, gap: 2 },
  fact: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8 },
  factLabel: { width: 96, ...type.bodySmall, color: color.muted } as any,
  factValue: { flex: 1, ...type.bodySmall, color: color.fg } as any,

  summary: { marginTop: space.md, gap: 6 },
  summaryHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  summaryLabel: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  summaryText: { ...type.bodySmall, color: color.muted } as any,

  err: { marginTop: space.md, ...type.bodySmall, color: color.warnText } as any,

  dock: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: space.lg, paddingTop: space.sm, backgroundColor: color.bg },
  dockRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  fab: { width: 52, height: 52, borderRadius: 26, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  removeBtn: { height: 44, alignItems: 'center', justifyContent: 'center', marginTop: space.xs },
  removeText: { ...type.button, color: color.danger } as any,
  ctaDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  ctaDarkText: { ...type.button, color: color.onPrimary } as any,

  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: { paddingHorizontal: space.md, height: 36, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  chipOn: { backgroundColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  chipTextOn: { color: color.onPrimary, fontWeight: '700' },
  boxes: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.sm, marginTop: space.md },
  box: {
    minWidth: 56, height: 40, borderRadius: rad.md, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  boxText: { ...type.title, color: color.fg, fontVariant: ['tabular-nums'] } as any,
  boxSep: { ...type.title, color: color.muted } as any,

  area: {
    minHeight: 120, borderRadius: rad.md, backgroundColor: color.neutral100,
    padding: space.md, ...type.body, color: color.fg,
  } as any,
  counter: { alignSelf: 'flex-end', ...type.labelSmall, color: color.muted } as any,

  empty: { alignItems: 'center', gap: space.md, paddingTop: space.xl * 2 },
  emptyTitle: { ...type.title, color: color.fg } as any,
  emptyCta: { height: 44, paddingHorizontal: space.xl, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  emptyCtaText: { ...type.button, color: color.onPrimary } as any,
});
