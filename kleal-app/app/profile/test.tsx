/**
 * Тест от Kleal — вопросы на клиенте и РОВНО один вызов модели в конце.
 *
 * По обращению к модели на каждый вопрос — это столько же шансов повиснуть на цепочке без отмены,
 * ради вопросов, которые в тесте и так заданы заранее. Поэтому вся лестница на клиенте, а
 * /api/buddy/persona зовётся один раз, когда отвечено всё.
 *
 * Пропустить можно любой вопрос: тест, из которого нельзя выйти, — это не тест, а форма. Пропуск
 * честно не пишет в профиль ничего, а не подставляет значение по умолчанию: подставленное значение
 * было бы утверждением, которого человек не делал.
 *
 * ТЕСТ ЗАКАНЧИВАЕТСЯ РЕЗУЛЬТАТОМ, а не закрытием экрана. Раньше последний ответ уводил обратно в
 * профиль, где где-то ниже менялся абзац, — человек отвечал на одиннадцать вопросов и не видел, что
 * из них вышло. Теперь виден и абзац, и то, что записано по осям: эти токены и так лежат в профиле,
 * прятать их от того, про кого они, незачем.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card } from '../../src/components/ProfileShell';
import { IconCheckCircle } from '../../src/components/icons';
import { useLang, getLang } from '../../src/i18n';
import { useOnb, set, profileForAttach } from '../../src/state';
import { buddy, profile as profileApi } from '../../src/api';
import { TEST_Q, TEST as C, AXIS_LABEL, AXIS_VALUE, AXIS_ORDER, adaptSummary } from '../../src/profile';
import { color, radius as rad, space, type } from '../../src/theme';

type Answer = { k: string; q: string; a: string; token: string | null };

export default function PersonalityTest() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const p: any = st.profile;

  const [i, setI] = useState(0);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [free, setFree] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  /** Готовый результат: абзац и оси. Пусто — тест ещё идёт. */
  const [result, setResult] = useState<{ text: string; axes: Record<string, string> } | null>(null);

  const q = TEST_Q[i];
  const last = i === TEST_Q.length - 1;

  const finish = async (all: Answer[]) => {
    setBusy(true);
    setFailed(false);
    // Токены осей пишем в профиль СРАЗУ, до вызова модели: они получены из нажатых вариантов и
    // ценны сами по себе. Если текст не соберётся, ответы всё равно не потеряются.
    const axes: Record<string, string> = {};
    all.forEach((a) => { if (a.token) axes[a.k] = a.token; });
    set('persona', { ...axes, takenAt: Date.now() });
    try {
      const r: any = await buddy.persona({
        profile: profileForAttach(),
        story: String(p.story || ''),
        answers: all.map((a) => ({ q: a.q, a: a.a })),
        current: String(p.summary || ''),
        // Токены осей отдельно от текста вопросов: по тексту модель пересказывала нажатый вариант,
        // по токенам она видит координаты и замечает, когда две оси тянут в разные стороны.
        axes,
        lang: getLang(),
      });
      const text = String(r?.personality || '').trim();
      if (!text) { setFailed(true); setResult({ text: '', axes }); return; }
      set('personality', text);
      set('personalityUpdated', Date.now());
      if (p.name) {
        await profileApi.update(p.name, {
          personality: text, persona: { ...axes, takenAt: Date.now() },
        }).catch(() => {});
      }
      setResult({ text, axes });
      // Сводка следует за личностью, а не наоборот: adaptSummary отвергнет ответ, который окажется
      // просто текстом личности, — иначе тест съел бы сводку. Не ждём: человек уже читает результат.
      adaptSummary();
    } catch {
      // Оси записались до вызова модели — показываем то, что есть, а не пустой экран с ошибкой.
      setFailed(true);
      setResult({ text: '', axes });
    } finally {
      setBusy(false);
    }
  };

  /** Пройти заново — с чистого листа, но уже записанное в профиле остаётся до нового результата. */
  const restart = () => {
    setResult(null); setFailed(false); setAnswers([]); setFree(''); setI(0);
  };

  const answer = (text: string, token: string | null) => {
    const next = [...answers, { k: q.k, q: q.q(), a: text, token }];
    setAnswers(next);
    setFree('');
    if (last) finish(next);
    else setI(i + 1);
  };

  const skip = () => {
    setFree('');
    if (last) finish(answers);
    else setI(i + 1);
  };

  if (busy) {
    return (
      <ProfileShell title={C.title()}>
        <View style={s.center}>
          <ActivityIndicator color={color.primary} />
          <Text style={s.working}>{C.working()}</Text>
        </View>
      </ProfileShell>
    );
  }

  if (result) {
    return (
      <ProfileShell
        title={C.title()}
        onBack={() => router.back()}
        footer={
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.back()}>
            <Text style={s.ctaText}>{C.keep()}</Text>
          </Pressable>
        }
      >
        <View style={s.done}><IconCheckCircle size={34} /></View>
        <Text style={s.resultTitle}>{C.resultTitle()}</Text>

        {result.text ? (
          <Card><Text style={s.resultText}>{result.text}</Text></Card>
        ) : (
          <Text style={s.failed}>{failed ? C.failed() : C.axesOnly()}</Text>
        )}

        <Text style={s.axesTitle}>{C.axesTitle()}</Text>
        <Card>
          {AXIS_ORDER.map((k) => {
            const tok = result.axes[k];
            const label = AXIS_LABEL[k];
            if (!label) return null;
            return (
              <View key={k} style={s.axisRow}>
                <Text style={s.axisKey}>{label()}</Text>
                <Text style={[s.axisVal, !tok && s.axisSkipped]}>
                  {tok && AXIS_VALUE[tok] ? AXIS_VALUE[tok]() : C.skipped()}
                </Text>
              </View>
            );
          })}
        </Card>
        <Text style={s.axesNote}>{C.axesNote()}</Text>

        <Pressable accessibilityRole="button" onPress={restart}>
          <Text style={s.skip}>{C.again()}</Text>
        </Pressable>
      </ProfileShell>
    );
  }

  return (
    <ProfileShell title={C.title()} onBack={() => router.back()}>
      <Text style={s.of}>{C.of(i + 1, TEST_Q.length)}</Text>
      <View style={s.track}>
        <View style={[s.trackFill, { width: `${Math.round((i / TEST_Q.length) * 100)}%` }]} />
      </View>

      <Card>
        {/* Сцена — обстановка одной строкой. Из-за неё ответ становится припоминанием, а не
            самооценкой: «полчаса как познакомились» человек вспоминает, а «какой разговор тебе
            ближе» примеряет. */}
        {q.scene ? <Text style={s.scene}>{q.scene()}</Text> : null}
        <Text style={s.q}>{q.q()}</Text>

        {q.free ? (
          <>
            {q.stem ? <Text style={s.stem}>{q.stem()}</Text> : null}
            <TextInput
              style={s.input}
              value={free}
              onChangeText={setFree}
              multiline
              textAlignVertical="top"
              placeholder={C.placeholder()}
              placeholderTextColor={color.neutral400}
              accessibilityLabel={q.q()}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: !free.trim() }}
              style={[s.cta, !free.trim() && { opacity: 0.45 }]}
              onPress={free.trim() ? () => answer(free.trim(), null) : undefined}
            >
              <Text style={s.ctaText}>{C.finish()}</Text>
            </Pressable>
          </>
        ) : (
          q.o.map((label, n) => (
            <Pressable
              key={n}
              accessibilityRole="button"
              style={({ pressed }) => [s.opt, pressed && { borderColor: color.primary }]}
              onPress={() => answer(label(), q.m[n])}
            >
              <Text style={s.optText}>{label()}</Text>
            </Pressable>
          ))
        )}
      </Card>

      {failed ? <Text style={s.failed}>{C.failed()}</Text> : null}

      <Pressable accessibilityRole="button" onPress={skip}>
        <Text style={s.skip}>{C.skip()}</Text>
      </Pressable>
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  of: { ...type.caption, color: color.muted, paddingHorizontal: 4 } as any,
  track: { height: 4, backgroundColor: color.neutral100, borderRadius: 2, marginHorizontal: 4 },
  trackFill: { height: 4, backgroundColor: color.primary, borderRadius: 2 },
  q: { fontSize: 19, lineHeight: 26, fontWeight: '600', color: color.fg, marginBottom: space.sm },
  opt: {
    minHeight: 52, borderRadius: rad.md, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.bg, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 14,
  },
  optText: { ...type.body, color: color.fg, textAlign: 'center' } as any,
  input: {
    minHeight: 130, borderRadius: rad.md, backgroundColor: color.neutral100,
    padding: 12, color: color.fg, fontSize: 15, lineHeight: 22,
  },
  cta: { height: 48, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  skip: { ...type.labelMedium, color: color.muted, textAlign: 'center', paddingVertical: space.md } as any,
  failed: { ...type.bodySmall, color: color.primary, paddingHorizontal: 4 } as any,
  scene: { ...type.bodySmall, color: color.muted, marginBottom: 6 } as any,
  stem: { ...type.body, color: color.fg, fontWeight: '600', marginBottom: 8 } as any,
  done: { alignItems: 'center', paddingTop: space.sm },
  resultTitle: { fontSize: 22, lineHeight: 28, fontWeight: '700', color: color.fg, textAlign: 'center' },
  resultText: { ...type.body, color: color.fg } as any,
  axesTitle: { ...type.labelMedium, color: color.fg, fontWeight: '600', paddingHorizontal: 4, marginTop: space.sm } as any,
  axesNote: { ...type.caption, color: color.muted, paddingHorizontal: 4 } as any,
  axisRow: {
    flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between',
    gap: space.md, paddingVertical: 7,
  },
  axisKey: { ...type.bodySmall, color: color.muted, flexShrink: 0 } as any,
  axisVal: { ...type.bodySmall, color: color.fg, fontWeight: '600', flex: 1, textAlign: 'right' } as any,
  axisSkipped: { color: color.neutral400, fontWeight: '400' },
  center: { alignItems: 'center', justifyContent: 'center', paddingTop: 90, gap: space.md },
  working: { ...type.body, color: color.muted } as any,
});
