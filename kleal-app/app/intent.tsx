/**
 * Создание интента — кадры OF.04–OF.10, затем поиск OF.11 и выдача OF.12.
 *
 * Тот же разговор, что в онбординге: вопрос агента, виджет под ним, строка «Message…» внизу.
 * Свободный текст здесь ценнее, чем в анкете, — «хочу посмотреть футбол вечером» описывает интент
 * целиком, и разбирать его должна модель (/api/agent/plan), а не шесть экранов подряд. Поэтому
 * первый же шаг принимает текст и, если он содержательный, пропускает остаток мастера.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { ChatShell, Bubble, chatStyles as cs } from '../src/components/ChatShell';
import { AgeRange } from '../src/components/AgeRange';
import {
  INTENT_TITLE, INTENT_PROGRESS, IntentStepId,
  STEP_WHAT, WHAT_SUGGESTIONS, whatLabel, whatPlain,
  STEP_HOW, FORMATS, formatLabel, formatSub,
  STEP_SIZE, SIZES, sizeLabel, sizeSub, GROUP_MIN_TOTAL,
  STEP_DETAIL, STEP_WHEN, DAYS, dayLabel, PARTS, partLabel, timeQuery,
  STEP_WHO, STEP_WHERE, DISTRICTS, districtLabel, districtQuery,
  STEP_SUMMARY, SEARCHING,
} from '../src/intent';
import { SEXES, sexLabel } from '../src/onboarding';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { setResults } from '../src/results-store';
import { agent } from '../src/api';
import { color, radius as rad, space, type } from '../src/theme';

const now = () =>
  new Date().toLocaleTimeString(getLang() === 'ru' ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: getLang() !== 'ru',
  });

/** Что собирается по шагам. Всё необязательно, кроме темы: агент дополнит остальное сам. */
type Draft = {
  topics: string[];
  free?: string;
  mode?: string;
  size?: string;
  day?: string;
  part?: string;
  sex?: string;
  minAge?: number;
  maxAge?: number;
  district?: string;
  radiusKm?: number;
};

export default function Intent() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const scroller = useRef<ScrollView>(null);

  const [thread, setThread] = useState<Bubble[]>([]);
  const [step, setStep] = useState<IntentStepId>('what');
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState<Draft>({ topics: [], radiusKm: 15 });
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  const say = useCallback((who: 'bot' | 'me', text: string) => {
    setThread((t) => [...t, { who, text, at: now() }]);
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    setTyping(true);
    setTimeout(() => { setTyping(false); say('bot', STEP_WHAT.bot()); }, 450);
  }, [say]);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [thread.length, typing, step]);

  const goto = (next: IntentStepId, line?: string) => {
    setStep(next);
    if (!line) return;
    setTyping(true);
    setTimeout(() => { setTyping(false); say('bot', line); }, 600);
  };

  /**
   * Профиль, который уходит вместе с запросом: матчинг гейтит по возрасту, языкам и месту.
   *
   * `interests` — ПЛОСКИЙ список, а не `{explicit: […]}`, в котором его хранит онбординг. Форма
   * здесь не вкусовщина: замерено на стенде по одному и тому же запросу — плоский список даёт
   * встречную релевантность 0.55, вложенный 0.27, то есть ХУЖЕ, чем не прислать интересы вовсе
   * (0.32). Вложенный объект просто не разбирается, и человек со своими увлечениями оказывается
   * менее интересен системе, чем человек без единого.
   */
  const profile = () => ({
    name: st.profile.name,
    age: st.profile.age,
    gender: st.profile.gender,
    city: st.profile.city,
    lat: st.profile.geo?.coarseLat,
    lon: st.profile.geo?.coarseLon,
    languages: { comfortable: st.profile.languages?.comfortable || [] },
    interests: st.profile.interests?.explicit || [],
  });

  /**
   * ctx нужен не для порядка: §5.3 считает город только отсюда (location_block.city ← ctx.city).
   * Без него ответ приходит с minimally_sufficient.ok = false, и поиск идёт по интенту, который
   * сам сервер считает недосказанным.
   */
  const ctx = () => ({
    self: st.profile.name,
    uid: st.profile.name,
    city: st.profile.city,
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Madrid',
  });

  const toResults = (r: any, fallbackIntent: any, query?: string) => {
    setResults({
      intent: r?.intent || fallbackIntent,
      candidates: r?.candidates || [],
      profile: profile(),
      query: query || '',
    });
    router.push('/results');
  };

  /**
   * Свободный текст. Если человек описал затею словами — отдаём модели целиком и идём сразу к
   * выдаче: гонять его после этого по шести экранам значило бы переспрашивать то, что он уже сказал.
   */
  const send = async (text: string) => {
    say('me', text);
    setBusy(true);
    try {
      const r: any = await agent.plan(text, profile(), ctx());
      toResults(r, {}, text);
    } catch {
      say('bot', T('Связь пропала. Повторишь?', 'I lost the connection. Say that again?'));
    } finally {
      setBusy(false);
    }
  };

  /** Собранный по шагам интент — уже структурный, без разбора текста. */
  const finish = async () => {
    setBusy(true);
    const intent: any = {
      topics: draft.topics.length ? draft.topics : (draft.free ? [draft.free] : []),
      mode: draft.mode || 'offline',
      // Английская строка намеренно: срочность на той стороне ищется по словам, и только английским.
      time: timeQuery(draft.day, draft.part),
      // format, а не groupSize. §5.3 признаёт интент описанным только когда есть и mode, и format;
      // groupSize же увёл бы запрос в групповую ветку, где 1:1 просто нечего делать.
      format: draft.size === 'group' ? 'group' : '1:1',
    };
    if (draft.size === 'group') intent.groupSize = GROUP_MIN_TOTAL;
    if (draft.sex && draft.sex !== 'Any') intent.sex = draft.sex;
    if (draft.minAge) intent.minAge = draft.minAge;
    if (draft.maxAge) intent.maxAge = draft.maxAge;
    if (intent.mode === 'online') {
      // Иначе §5.3 требует город, которого у онлайн-встречи нет по определению.
      intent.allowOnlineFallback = true;
    } else {
      if (draft.district) intent.place = districtQuery(draft.district);
      if (draft.radiusKm != null) intent.radiusKm = draft.radiusKm;
    }
    try {
      const r: any = await agent.match(intent, profile(), ctx());
      toResults(r, intent);
    } catch {
      say('bot', T('Не получилось поискать. Попробуй ещё раз.', 'The search failed. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <ChatShell
        ref={scroller}
        title={INTENT_TITLE()}
        pct={INTENT_PROGRESS[step]}
        thread={thread}
        typing={typing}
        onBack={() => router.back()}
        onSend={busy ? undefined : send}
        widget={
          <Widget
            step={step}
            draft={draft}
            setDraft={setDraft}
            say={say}
            goto={goto}
            finish={finish}
            busy={busy}
          />
        }
      />
      {busy ? <Searching /> : null}
    </>
  );
}

/**
 * OF.11 — пока идёт поиск.
 *
 * Накладкой поверх мастера, а не отдельным маршрутом: экран живёт секунды и не должен оставаться
 * в истории — иначе «назад» из выдачи возвращало бы человека в бесконечное ожидание того, что уже
 * нашлось. Запрос к модели идёт заметное время, и точки «печатает» в ленте — слишком тихий ответ
 * на нажатие «Искать людей».
 */
function Searching() {
  return (
    <View style={w.veil}>
      <ActivityIndicator size="large" color={color.primary} />
      <Text style={w.veilTitle}>{SEARCHING.title()}</Text>
      <Text style={w.veilStep}>{SEARCHING.step()}</Text>
      <Text style={w.veilNote}>{SEARCHING.note()}</Text>
    </View>
  );
}

// ============================================================ виджеты шагов

type WProps = {
  step: IntentStepId;
  draft: Draft;
  setDraft: React.Dispatch<React.SetStateAction<Draft>>;
  say: (who: 'bot' | 'me', text: string) => void;
  goto: (s: IntentStepId, line?: string) => void;
  finish: () => void;
  busy: boolean;
};

function Widget(p: WProps) {
  switch (p.step) {
    case 'what': return <WhatW {...p} />;
    case 'how': return <HowW {...p} />;
    case 'size': return <SizeW {...p} />;
    case 'when': return <WhenW {...p} />;
    case 'who': return <WhoW {...p} />;
    case 'where': return <WhereW {...p} />;
    case 'summary': return <SummaryW {...p} />;
    default: return null;
  }
}

function Chip({ label, on, onPress }: { label: string; on?: boolean; onPress?: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      onPress={onPress}
      style={({ pressed }) => [w.chip, on && w.chipOn, pressed && { opacity: 0.85 }]}
    >
      <Text style={[w.chipText, on && { color: color.onPrimary }]}>{label}</Text>
    </Pressable>
  );
}

function Row({ label, sub, on, onPress }: { label: string; sub?: string; on?: boolean; onPress?: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      onPress={onPress}
      style={({ pressed }) => [w.row, on && w.rowOn, pressed && { opacity: 0.9 }]}
    >
      <View style={{ flex: 1 }}>
        <Text style={[w.rowTitle, on && { color: color.primary }]}>{label}</Text>
        {sub ? <Text style={w.rowSub}>{sub}</Text> : null}
      </View>
      {on ? <Text style={w.tick}>✓</Text> : null}
    </Pressable>
  );
}

function Cta({ label, onPress, disabled, kind = 'primary', busy }: {
  label: string; onPress?: () => void; disabled?: boolean; kind?: 'primary' | 'muted'; busy?: boolean;
}) {
  const off = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      onPress={off ? undefined : onPress}
      style={({ pressed }) => [
        w.cta,
        { backgroundColor: kind === 'primary' ? color.primary : color.neutral100, opacity: off ? 0.45 : pressed ? 0.9 : 1 },
      ]}
    >
      {busy ? <ActivityIndicator color={color.onPrimary} />
            : <Text style={[w.ctaText, kind === 'muted' && { color: color.fg }]}>{label}</Text>}
    </Pressable>
  );
}

/** OF.04 — тема. Можно нажать вариант, можно написать словами в композер. */
function WhatW({ draft, setDraft, say, goto }: WProps) {
  const toggle = (k: string) =>
    setDraft((d) => ({ ...d, topics: d.topics.includes(k) ? d.topics.filter((x) => x !== k) : [...d.topics, k] }));
  return (
    <View style={cs.widget}>
      <Text style={cs.hint}>{STEP_WHAT.hint()}</Text>
      <Text style={cs.label}>{STEP_WHAT.pick()}</Text>
      <View style={cs.row}>
        {WHAT_SUGGESTIONS.map(([k]) => (
          <Chip key={k} label={whatLabel(k)} on={draft.topics.includes(k)} onPress={() => toggle(k)} />
        ))}
      </View>
      <Cta
        label={T('Дальше', 'Next')}
        disabled={!draft.topics.length}
        onPress={() => {
          say('me', draft.topics.map(whatPlain).join(', '));
          goto('how', STEP_HOW.bot());
        }}
      />
    </View>
  );
}

/** OF.05 — формат. */
function HowW({ draft, setDraft, say, goto }: WProps) {
  return (
    <View style={cs.widget}>
      {FORMATS.map(([k]) => (
        <Row
          key={k}
          label={formatLabel(k)}
          sub={formatSub(k)}
          on={draft.mode === k}
          onPress={() => setDraft((d) => ({ ...d, mode: k }))}
        />
      ))}
      <Cta
        label={T('Дальше', 'Next')}
        disabled={!draft.mode}
        onPress={() => { say('me', formatLabel(draft.mode!)); goto('size', STEP_SIZE.bot()); }}
      />
    </View>
  );
}

/** OF.06 — сколько людей. */
function SizeW({ draft, setDraft, say, goto }: WProps) {
  return (
    <View style={cs.widget}>
      {SIZES.map(([k]) => (
        <Row
          key={k}
          label={sizeLabel(k)}
          sub={sizeSub(k)}
          on={draft.size === k}
          onPress={() => setDraft((d) => ({ ...d, size: k }))}
        />
      ))}
      <Cta
        label={T('Дальше', 'Next')}
        disabled={!draft.size}
        onPress={() => { say('me', sizeLabel(draft.size!)); goto('when', STEP_DETAIL.bot()); }}
      />
    </View>
  );
}

/** OF.07 — когда. */
function WhenW({ draft, setDraft, say, goto }: WProps) {
  return (
    <View style={cs.widget}>
      <Text style={cs.label}>{STEP_WHEN.label()}</Text>
      <View style={cs.row}>
        {DAYS.map(([k]) => (
          <Chip key={k} label={dayLabel(k)} on={draft.day === k} onPress={() => setDraft((d) => ({ ...d, day: k }))} />
        ))}
      </View>
      <Text style={cs.label}>{STEP_WHEN.timeLabel()}</Text>
      <View style={cs.row}>
        {PARTS.map(([k]) => (
          <Chip key={k} label={partLabel(k)} on={draft.part === k} onPress={() => setDraft((d) => ({ ...d, part: k }))} />
        ))}
      </View>
      <Cta
        label={T('Дальше', 'Next')}
        disabled={!draft.day}
        onPress={() => {
          say('me', [dayLabel(draft.day!), draft.part && partLabel(draft.part)].filter(Boolean).join(', '));
          goto('who', STEP_DETAIL.who());
        }}
      />
    </View>
  );
}

/** OF.08 — кого искать. Возраст и пол — жёсткие фильтры на той стороне, не украшение. */
function WhoW({ draft, setDraft, say, goto }: WProps) {
  return (
    <View style={cs.widget}>
      <Text style={cs.label}>{STEP_WHO.sexLabel()}</Text>
      <View style={cs.row}>
        {SEXES.map(([k]) => (
          <Chip key={k} label={sexLabel(k)} on={draft.sex === k} onPress={() => setDraft((d) => ({ ...d, sex: k }))} />
        ))}
      </View>
      <Text style={cs.label}>{STEP_WHO.ageLabel()}</Text>
      <AgeRange
        min={draft.minAge ?? 18}
        max={draft.maxAge ?? 45}
        onChange={(lo, hi) => setDraft((d) => ({ ...d, minAge: lo, maxAge: hi }))}
      />
      <Cta
        label={T('Дальше', 'Next')}
        onPress={() => {
          const bits = [draft.sex && sexLabel(draft.sex), `${draft.minAge ?? 18}–${draft.maxAge ?? 45}`].filter(Boolean);
          say('me', bits.join(', '));
          goto('where', STEP_DETAIL.where());
        }}
      />
    </View>
  );
}

/** OF.09 — район и радиус. Для онлайна ни того, ни другого не спрашиваем. */
function WhereW({ draft, setDraft, say, goto }: WProps) {
  if (draft.mode === 'online') {
    return (
      <View style={cs.widget}>
        <Text style={cs.hint}>{T('Онлайн — место не нужно.', 'Online — no place needed.')}</Text>
        <Cta label={T('Дальше', 'Next')} onPress={() => goto('summary', STEP_SUMMARY.bot())} />
      </View>
    );
  }
  return (
    <View style={cs.widget}>
      <Text style={cs.label}>{STEP_WHERE.districtLabel()}</Text>
      <View style={cs.row}>
        {DISTRICTS.map(([k]) => (
          <Chip
            key={k}
            label={districtLabel(k)}
            on={draft.district === k}
            onPress={() => setDraft((d) => ({ ...d, district: k }))}
          />
        ))}
      </View>
      <View style={w.radiusRow}>
        <Text style={cs.label}>{STEP_WHERE.radiusLabel()}</Text>
        <Text style={w.radiusValue}>{draft.radiusKm} km</Text>
      </View>
      <View style={cs.row}>
        {[3, 5, 10, 15, 25, 40].map((km) => (
          <Chip key={km} label={`${km} km`} on={draft.radiusKm === km} onPress={() => setDraft((d) => ({ ...d, radiusKm: km }))} />
        ))}
      </View>
      <Cta
        label={T('Дальше', 'Next')}
        onPress={() => {
          say('me', [draft.district && districtLabel(draft.district), `${draft.radiusKm} km`].filter(Boolean).join(', '));
          goto('summary', STEP_SUMMARY.bot());
        }}
      />
    </View>
  );
}

/** OF.10 — сводка запроса перед поиском. */
function SummaryW({ draft, goto, finish, busy }: WProps) {
  const rows: [string, string][] = [
    [T('Что', 'What'), draft.topics.map(whatPlain).join(', ') || '—'],
    [T('Как', 'How'), draft.mode ? formatLabel(draft.mode) : '—'],
    [T('Сколько', 'Size'), draft.size ? sizeLabel(draft.size) : '—'],
    [T('Когда', 'When'), [draft.day && dayLabel(draft.day), draft.part && partLabel(draft.part)].filter(Boolean).join(', ') || '—'],
    [T('Кто', 'Who'), [draft.sex && sexLabel(draft.sex), `${draft.minAge ?? 18}–${draft.maxAge ?? 45}`].filter(Boolean).join(', ')],
    ...(draft.mode === 'online'
      ? []
      : ([[T('Где', 'Where'), [draft.district && districtLabel(draft.district), `${draft.radiusKm} km`].filter(Boolean).join(', ')]] as [string, string][])),
  ];
  return (
    <View style={cs.widget}>
      <View style={w.card}>
        {rows.map(([k, v]) => (
          <View key={k} style={w.sumRow}>
            <Text style={w.sumKey}>{k}</Text>
            <Text style={w.sumVal} numberOfLines={2}>{v}</Text>
          </View>
        ))}
      </View>
      <Cta label={STEP_SUMMARY.send()} onPress={finish} busy={busy} />
      <Cta label={STEP_SUMMARY.edit()} kind="muted" onPress={() => goto('what')} />
    </View>
  );
}

const w = StyleSheet.create({
  chip: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  row: {
    flexDirection: 'row', alignItems: 'center', gap: space.md, padding: 14,
    borderRadius: rad.lg, backgroundColor: color.card, borderWidth: 1, borderColor: color.border,
  },
  rowOn: { borderColor: color.primary },
  rowTitle: { ...type.title, color: color.fg } as any,
  rowSub: { ...type.bodySmall, color: color.muted } as any,
  tick: { color: color.primary, fontSize: 18, fontWeight: '700' },
  cta: { height: 52, borderRadius: rad.full, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  radiusRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  radiusValue: { ...type.body, color: color.primary, fontWeight: '600' } as any,
  veil: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: color.bg, alignItems: 'center', justifyContent: 'center',
    gap: space.md, paddingHorizontal: 32,
  },
  veilTitle: { fontSize: 24, lineHeight: 32, fontWeight: '700', color: color.fg, textAlign: 'center', marginTop: space.lg },
  veilStep: { ...type.body, color: color.primary, textAlign: 'center' } as any,
  veilNote: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,

  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.sm },
  sumRow: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
  sumKey: { ...type.bodySmall, color: color.muted } as any,
  sumVal: { ...type.bodySmall, color: color.fg, flex: 1, textAlign: 'right' } as any,
});
