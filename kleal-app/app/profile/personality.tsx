/**
 * Профиль → «Твоя личность».
 *
 * Две вещи, и ни одна не зависит от того, успел ли Kleal что-то про тебя понять: тест и история
 * своими словами. Поэтому экран осмыслен и у совсем нового профиля.
 *
 * ЧТО ЗДЕСЬ БЫЛО И ПОЧЕМУ ПЕРЕЛОЖЕНО (10 сентября 2026, с телефона: «неразбериха, много лишнего»).
 * Сверху стояло фото на 132 пункта — то же, что на хабе профиля, и к личности не относящееся.
 * Под ним красная «Пройти тест», ниже поле истории, под ним кнопка «Сохранить историю», под ней
 * тёмная «Пересобрать», затем карточка с ЕЩЁ ОДНОЙ тёмной кнопкой на тот же тест и ссылка «Пройти
 * заново», а внизу вторая красная «Сохранить и закрыть». Три входа в один тест, две красные
 * кнопки, два сохранения — экран, у которого нет главного.
 *
 * ТЕПЕРЬ. Порядок — по смыслу заголовка: сначала сама личность (ради неё экран и назван), потом
 * история своими словами, потом что из неё годится в интересы, потом сводка. У теста один вход —
 * внутри карточки личности: у новичка это единственная красная кнопка на экране, у прошедшего —
 * тихая ссылка «пройти заново». История сохраняется сама, по уходу с поля и по «назад», и говорит
 * об этом строкой «Сохранено» прямо под полем — отдельные кнопки сохранения убраны как повтор.
 * Фото убрано: ему место на хабе, а здесь оно занимало самое дорогое место на экране.
 *
 * `personality` и `summary` — ДВА разных текста с двумя владельцами. Первый пишет тест, второй —
 * сводка на хабе. Сливать их нельзя: в вебе это уже пробовали, и тест молча съедал сводку.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, Divider } from '../../src/components/ProfileShell';
import { useLang, replyLang } from '../../src/i18n';
import { useOnb, set, getState } from '../../src/state';
import { profile as profileApi, buddy } from '../../src/api';
import {
  PERSONALITY as C, STORY_MAX, fmtUpdated, adaptSummary,
  AXIS_LABEL, AXIS_VALUE, AXIS_ORDER, addConfirmedInterest, explicitInterests,
} from '../../src/profile';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Personality() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const p: any = st.profile;

  const [story, setStory] = useState<string>(String(p.story || ''));
  const [saved, setSaved] = useState(false);
  /** Пересборка сводки: идёт / что получилось. Пусто — ещё не нажимали. */
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuilt, setRebuilt] = useState('');
  const [rebuildErr, setRebuildErr] = useState('');
  /**
   * Что история говорит о занятиях человека — предложением, а не правкой.
   *
   * История уходила в сводку и никуда больше, а матчинг читает `interests`, не прозу: человек мог
   * написать абзац про горы, хлеб и испанский и остаться в поиске «кофе, падел, книги». Со
   * стороны это ровно «написал — и ничего не произошло».
   *
   * Само ничего не добавляется. Интересы, проставленные за человека, это ярлыки, которых он не
   * выбирал, и найдут его по ним не те люди.
   */
  const [suggest, setSuggest] = useState<{ key: string; label: string; why: string; token: string }[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [addedNote, setAddedNote] = useState(false);
  const [asking, setAsking] = useState(false);

  const askStory = async (text: string) => {
    if (!text.trim()) return;
    setAsking(true);
    setAddedNote(false);
    try {
      const r: any = await buddy.storyInterests(text, explicitInterests(p), replyLang());
      const raw = (r?.interests || []) as { key: string; label: string; why: string }[];
      // Story extraction remains a proposal. Each key crosses the same schema-validated
      // normalization boundary as the free-text popup before it can be shown for confirmation.
      const list = (await Promise.all(raw.map(async (item) => {
        try {
          const nr = await profileApi.normalizeInterest(item.key, explicitInterests(p), replyLang());
          const option = nr.status === 'ready' && nr.options?.length === 1 ? nr.options[0] : null;
          return option ? { key: option.canonical, label: option.label || item.label,
                            why: item.why, token: option.token } : null;
        } catch { return null; }
      }))).filter(Boolean) as { key: string; label: string; why: string; token: string }[];
      setSuggest(list);
      // Отмечено всё сразу: человек уже написал это про себя, и заставлять его отмечать заново
      // — лишний шаг. Снять галочку с лишнего дешевле, чем проставить четыре.
      setPicked(Object.fromEntries(list.map((x) => [x.key, true])));
    } catch {
      setSuggest([]);
    } finally {
      setAsking(false);
    }
  };

  const applyPicked = async () => {
    const chosen = suggest.filter((x) => picked[x.key]);
    if (!chosen.length) return;
    for (const item of chosen) {
      try {
        const r = await profileApi.confirmInterest(String(p.name || ''), item.token);
        if (r.ok && r.canonical && r.token && (!getState().done || r.persisted === true)) {
          addConfirmedInterest(r.canonical, r.label || item.label, r.token);
        }
      } catch { /* an expired proposal is not written locally or remotely */ }
    }
    setSuggest([]);
    setPicked({});
    setAddedNote(true);
  };

  /** Текст в поле отличается от сохранённого — значит есть что применять. */
  const dirty = story.slice(0, STORY_MAX) !== String(p.story || '');

  /**
   * История сохраняется по уходу с поля и по кнопке. Проверка на «не изменилось» здесь не ради
   * экономии запроса: без неё уход с поля и нажатие кнопки отправляют один и тот же текст дважды.
   */
  const saveStory = async () => {
    const text = story.slice(0, STORY_MAX);
    if (text === String(p.story || '')) return false;
    set('story', text);
    if (p.name) await profileApi.update(p.name, { story: text }).catch(() => {});
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
    askStory(text);
    return true;
  };

  /**
   * «Пересобрать сводку». История уходит в профиль и оттуда — в сводку Kleal, но сама собой она
   * туда не попадала: пересборка запускается правкой полей на хабе, а на этом экране кнопки не
   * было вовсе. Человек писал абзац о себе, и ничего не происходило — по делу так и было.
   *
   * Сперва сохраняем историю (иначе пересобирали бы по вчерашнему тексту), потом просим модель.
   * Результат показываем ЗДЕСЬ же: кнопка, которая тихо меняет текст на другом экране, — это то
   * же самое «ничего не произошло».
   */
  const rebuild = async () => {
    if (rebuilding) return;
    setRebuilding(true);
    setRebuildErr('');
    setRebuilt('');
    try {
      await saveStory();
      const ok = await adaptSummary();
      const now = String((getState().profile as any).summary || '');
      if (ok && now) setRebuilt(now);
      else setRebuildErr(C.rebuildFailed());
    } catch {
      setRebuildErr(C.rebuildFailed());
    } finally {
      setRebuilding(false);
    }
  };

  const text = String(p.personality || '');
  const updated = fmtUpdated(p.personalityUpdated);
  // Оси лежат плоско ({energy:'drained'}) — так их шлёт тест. Из старых записей приходит обёртка
  // {v:1,axes:{…}}; читаем обе, чтобы человек, проходивший тест раньше, тоже видел свои ответы.
  const persona: Record<string, string> = (p.persona && p.persona.axes) || p.persona || {};
  const answered = AXIS_ORDER.filter((k) => persona[k] && AXIS_VALUE[persona[k]]);

  const hasTest = !!text || answered.length > 0;

  return (
    <ProfileShell title={C.title()} onBack={() => { saveStory(); router.back(); }}>
      {/*
        1. ЛИЧНОСТЬ — ПЕРВОЙ. Экран так и называется, и человек открывает его за этим.
        У новичка карточка — приглашение с единственной красной кнопкой на экране. У прошедшего —
        абзац Kleal, дата и ответы по осям компактной таблицей; тест здесь можно только пройти
        заново, и это ссылка, а не кнопка: повтор — не то действие, ради которого сюда приходят.
      */}
      <Card>
        {hasTest ? (
          <>
            <View style={s.head}>
              <Text style={s.label}>{C.title()}</Text>
              {updated ? <Text style={s.updated}>{updated}</Text> : null}
            </View>
            {text ? <Text style={s.body}>{text}</Text> : null}
            {answered.length ? (
              <>
                <Divider />
                <Text style={s.axesTitle}>{C.axesTitle()}</Text>
                {answered.map((k) => (
                  <View key={k} style={s.axisRow}>
                    <Text style={s.axisKey}>{AXIS_LABEL[k]()}</Text>
                    <Text style={s.axisVal}>{AXIS_VALUE[persona[k]]()}</Text>
                  </View>
                ))}
              </>
            ) : null}
            <Pressable accessibilityRole="button" onPress={() => router.navigate('/profile/test')} style={s.retakeWrap}>
              <Text style={s.retake}>{C.retake()}</Text>
            </Pressable>
          </>
        ) : (
          <>
            <Text style={s.label}>{C.title()}</Text>
            <Text style={s.body}>{C.empty()}</Text>
            <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.navigate('/profile/test')}>
              <Text style={s.ctaText}>{C.takeTest()}</Text>
            </Pressable>
          </>
        )}
      </Card>

      {/*
        2. СВОИМИ СЛОВАМИ. Сохраняется само — по уходу с поля и по «назад» — и говорит об этом
        строкой под полем. Раньше под ним стояли две кнопки сохранения и третья внизу экрана: три
        способа сделать одно и то же, ни один из которых не был нужен.
      */}
      <Card>
        <Text style={s.label}>{C.storyCap()}</Text>
        <TextInput
          style={s.story}
          value={story}
          onChangeText={(v) => setStory(v.slice(0, STORY_MAX))}
          onBlur={saveStory}
          multiline
          textAlignVertical="top"
          maxLength={STORY_MAX}
          placeholder={C.storyPlaceholder()}
          placeholderTextColor={color.neutral400}
          accessibilityLabel={C.storyCap()}
        />
        <View style={s.storyFoot}>
          <Text style={s.count}>{story.length} / {STORY_MAX}</Text>
          {saved ? <Text style={s.savedNote}>{C.saved()}</Text> : dirty ? <Text style={s.count}>…</Text> : null}
        </View>
      </Card>

      {/* 3. ЧТО ИЗ ИСТОРИИ ГОДИТСЯ В ПОИСК. Появляется после сохранения — по недописанному тексту
          предлагать нечего. Подтверждает человек, а не приложение. */}
      {asking ? <ActivityIndicator style={{ marginVertical: space.sm }} color={color.primary} /> : null}
      {suggest.length ? (
        <Card>
          <Text style={s.label}>{C.fromStoryTitle()}</Text>
          <Text style={s.note}>{C.fromStoryNote()}</Text>
          {suggest.map((x) => (
            <Pressable key={x.key} accessibilityRole="checkbox"
                       accessibilityState={{ checked: !!picked[x.key] }}
                       style={[s.pick, picked[x.key] && s.pickOn]}
                       onPress={() => setPicked((v) => ({ ...v, [x.key]: !v[x.key] }))}>
              <Text style={[s.pickLabel, picked[x.key] && { color: color.onPrimary }]}>{x.label}</Text>
              <Text style={[s.pickWhy, picked[x.key] && { color: color.onPrimary }]} numberOfLines={2}>
                «{x.why}»
              </Text>
            </Pressable>
          ))}
          <Pressable accessibilityRole="button" style={s.soft} onPress={applyPicked}>
            <Text style={s.softText}>{C.fromStoryAdd(suggest.filter((x) => picked[x.key]).length)}</Text>
          </Pressable>
        </Card>
      ) : null}
      {addedNote ? <Text style={s.savedNoteOut}>{C.fromStoryAdded()}</Text> : null}

      {/*
        4. СВОДКА KLEAL. Она живёт на хабе, но собирается из этой истории — поэтому её кнопка здесь,
        последней: сначала пишешь, потом смотришь, что из этого вышло. Кнопка мягкая, а не тёмная:
        главное действие экрана — тест, второго тёмного пятна ему не нужно. Результат показывается
        тут же — кнопка, тихо меняющая текст на другом экране, это то же «ничего не произошло».
      */}
      <Card>
        <Text style={s.label}>{C.rebuiltLabel()}</Text>
        <Text style={s.note}>{C.rebuildNote()}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ busy: rebuilding }}
          style={[s.soft, rebuilding && { opacity: 0.7 }]}
          onPress={rebuilding ? undefined : rebuild}
        >
          {rebuilding ? <ActivityIndicator color={color.primary} /> : <Text style={s.softText}>{C.rebuild()}</Text>}
        </Pressable>
        {rebuildErr ? <Text style={s.errNote}>{rebuildErr}</Text> : null}
        {rebuilt ? (
          <View style={s.rebuiltBox}>
            <Text style={s.rebuiltText}>{rebuilt}</Text>
          </View>
        ) : null}
      </Card>
    </ProfileShell>
  );
}

// ===== вид

const s = StyleSheet.create({
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: space.sm },
  label: { ...type.title, color: color.fg } as any,
  updated: { ...type.caption, color: color.muted } as any,
  body: { ...type.body, color: color.fg } as any,
  note: { ...type.bodySmall, color: color.muted } as any,

  axesTitle: { ...type.labelMedium, color: color.muted, marginTop: space.xs } as any,
  axisRow: {
    flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between',
    gap: space.md, paddingVertical: 6,
  },
  axisKey: { ...type.bodySmall, color: color.muted, flexShrink: 0 } as any,
  axisVal: { ...type.bodySmall, color: color.fg, fontWeight: '600', flex: 1, textAlign: 'right' } as any,
  retakeWrap: { paddingTop: space.xs, alignSelf: 'flex-start' },
  retake: { ...type.labelMedium, color: color.primary, fontWeight: '600' } as any,

  story: {
    minHeight: 132, borderRadius: rad.md, backgroundColor: color.bg,
    padding: 14, color: color.fg, fontSize: 15, lineHeight: 22,
  },
  storyFoot: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 4 },
  count: { ...type.caption, color: color.neutral400 } as any,
  savedNote: { ...type.caption, color: color.successText, fontWeight: '600' } as any,
  savedNoteOut: { ...type.caption, color: color.successText, paddingHorizontal: 4 } as any,

  pick: {
    borderRadius: rad.lg, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, paddingHorizontal: 14, paddingVertical: 10, gap: 2,
  },
  pickOn: { backgroundColor: color.primary, borderColor: color.primary },
  pickLabel: { ...type.body, color: color.fg, fontWeight: '700' } as any,
  pickWhy: { ...type.bodySmall, color: color.muted } as any,

  /** Единственная красная кнопка экрана — и только у того, кто тест ещё не проходил. */
  cta: { height: 48, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center', marginTop: space.xs },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  /** Мягкая кнопка второстепенных действий: добавить интересы, обновить сводку. */
  soft: { height: 44, borderRadius: rad.full, backgroundColor: color.infoBg, alignItems: 'center', justifyContent: 'center', marginTop: space.xs },
  softText: { ...type.button, color: color.primary } as any,

  errNote: { ...type.bodySmall, color: color.primary } as any,
  rebuiltBox: { backgroundColor: color.successBg, borderRadius: rad.lg, padding: space.md },
  rebuiltText: { ...type.bodySmall, color: color.successText } as any,
});
