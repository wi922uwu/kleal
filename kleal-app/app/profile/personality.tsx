/**
 * Профиль → «Твоя личность».
 *
 * Три вещи, и ни одна из них не зависит от того, успел ли Kleal что-то про тебя понять: фото, тест
 * и история своими словами. Поэтому экран осмыслен и у совсем нового профиля.
 *
 * `personality` и `summary` — ДВА разных текста с двумя владельцами. Первый пишет тест, второй —
 * сводка на хабе. Сливать их нельзя: в вебе это уже пробовали, и тест молча съедал сводку.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, Image, TextInput, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card } from '../../src/components/ProfileShell';
import { IconPerson } from '../../src/components/icons';
import { useLang, replyLang } from '../../src/i18n';
import { useOnb, set, getState } from '../../src/state';
import { mediaUrl, profile as profileApi, buddy } from '../../src/api';
import {
  PERSONALITY as C, STORY_MAX, fmtUpdated, adaptSummary,
  AXIS_LABEL, AXIS_VALUE, AXIS_ORDER, addInterests, explicitInterests,
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
  const [suggest, setSuggest] = useState<{ key: string; label: string; why: string }[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [addedNote, setAddedNote] = useState(false);
  const [asking, setAsking] = useState(false);

  const askStory = async (text: string) => {
    if (!text.trim()) return;
    setAsking(true);
    setAddedNote(false);
    try {
      const r: any = await buddy.storyInterests(text, explicitInterests(p), replyLang());
      const list = (r?.interests || []) as { key: string; label: string; why: string }[];
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
    const keys = suggest.filter((x) => picked[x.key]).map((x) => x.key);
    if (!keys.length) return;
    await addInterests(keys);
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

  return (
    <ProfileShell
      title={C.title()}
      onBack={() => { saveStory(); router.back(); }}
      footer={
        <Pressable
          accessibilityRole="button"
          style={s.cta}
          onPress={async () => { await saveStory(); router.back(); }}
        >
          <Text style={s.ctaText}>{C.confirm()}</Text>
        </Pressable>
      }
    >
      <View style={s.photoWrap}>
        {p.photo ? (
          <Image source={{ uri: mediaUrl(String(p.photo)) }} style={s.photo} />
        ) : (
          <View style={[s.photo, s.photoEmpty]}><IconPerson /></View>
        )}
      </View>

      <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.push('/profile/test')}>
        <Text style={s.ctaText}>{C.takeTest()}</Text>
      </Pressable>

      {/* Свои слова — ВЫШЕ сводки: человек сначала пишет о себе, а абзац Kleal — уже следствие.
          Обратный порядок читался как «вот наш вердикт, а теперь можешь дополнить». */}
      <Text style={s.cap}>{C.storyCap()}</Text>
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
        {saved ? <Text style={s.savedNote}>{C.saved()}</Text> : null}
      </View>

      {/*
        Две кнопки прямо под полем. Раньше история сохранялась молча — по уходу с поля и по
        кнопке в самом низу экрана, за 180 пикселями текстового поля: человек писал абзац о себе
        и не видел ни подтверждения, ни последствия. Теперь «Сохранить» говорит, что применилось,
        а «Пересобрать» показывает, что из этого вышло.
      */}
      {/* Что из истории годится для поиска. Показывается ПОСЛЕ сохранения — предлагать по
          недописанному тексту значит предлагать по половине фразы. */}
      {asking ? <ActivityIndicator style={{ marginVertical: space.sm }} color={color.primary} /> : null}
      {suggest.length ? (
        <View style={s.fromStory}>
          <Text style={s.fromStoryTitle}>{C.fromStoryTitle()}</Text>
          <Text style={s.fromStoryNote}>{C.fromStoryNote()}</Text>
          {suggest.map((x) => (
            <Pressable key={x.key} accessibilityRole="checkbox"
                       accessibilityState={{ checked: !!picked[x.key] }}
                       style={[s.pick, picked[x.key] && s.pickOn]}
                       onPress={() => setPicked((v) => ({ ...v, [x.key]: !v[x.key] }))}>
              <Text style={[s.pickLabel, picked[x.key] && { color: color.onPrimary }]}>{x.label}</Text>
              {/* Цитата из истории — чтобы предложение можно было проверить, а не принять на веру. */}
              <Text style={[s.pickWhy, picked[x.key] && { color: color.onPrimary }]} numberOfLines={2}>
                «{x.why}»
              </Text>
            </Pressable>
          ))}
          <Pressable accessibilityRole="button" style={s.applyBtn} onPress={applyPicked}>
            <Text style={s.applyText}>
              {C.fromStoryAdd(suggest.filter((x) => picked[x.key]).length)}
            </Text>
          </Pressable>
        </View>
      ) : null}
      {addedNote ? <Text style={s.savedNote}>{C.fromStoryAdded()}</Text> : null}

      <Pressable
        accessibilityRole="button"
        disabled={!dirty}
        accessibilityState={{ disabled: !dirty }}
        style={[s.applyBtn, !dirty && { opacity: 0.45 }]}
        onPress={saveStory}
      >
        {/* «История сохранена» — только когда она правда есть. У пустого поля это была бы
            неправда про несуществующий текст. */}
        <Text style={s.applyText}>{!dirty && p.story ? C.applied() : C.apply()}</Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        accessibilityState={{ busy: rebuilding }}
        style={[s.dark, rebuilding && { opacity: 0.7 }]}
        onPress={rebuilding ? undefined : rebuild}
      >
        {rebuilding
          ? <ActivityIndicator color="#fff" />
          : <Text style={s.darkText}>{C.rebuild()}</Text>}
      </Pressable>
      <Text style={s.cap}>{C.rebuildNote()}</Text>

      {rebuildErr ? <Text style={s.errNote}>{rebuildErr}</Text> : null}
      {rebuilt ? (
        <View style={s.rebuiltBox}>
          <Text style={s.rebuiltLabel}>{C.rebuiltLabel()}</Text>
          <Text style={s.rebuiltText}>{rebuilt}</Text>
        </View>
      ) : null}

      <Card>
        <View style={s.head}>
          <Text style={s.label}>{C.title()}</Text>
          {updated ? <Text style={s.updated}>{updated}</Text> : null}
        </View>
        <Text style={s.body}>{text || C.empty()}</Text>
        <Pressable accessibilityRole="button" style={s.dark} onPress={() => router.push('/profile/test')}>
          <Text style={s.darkText}>{C.editWith()}</Text>
        </Pressable>
      </Card>

      {answered.length ? (
        <Card>
          <Text style={s.label}>{C.axesTitle()}</Text>
          {answered.map((k) => (
            <View key={k} style={s.axisRow}>
              <Text style={s.axisKey}>{AXIS_LABEL[k]()}</Text>
              <Text style={s.axisVal}>{AXIS_VALUE[persona[k]]()}</Text>
            </View>
          ))}
          <Pressable accessibilityRole="button" onPress={() => router.push('/profile/test')}>
            <Text style={s.retake}>{C.retake()}</Text>
          </Pressable>
        </Card>
      ) : null}

    </ProfileShell>
  );
}

const s = StyleSheet.create({
  photoWrap: { alignItems: 'center', marginTop: space.sm },
  photo: { width: 132, height: 132, borderRadius: rad.full },
  photoEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },

  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  label: { fontSize: 17, fontWeight: '700', color: color.fg },
  updated: { ...type.caption, color: color.muted } as any,
  body: { ...type.body, color: color.fg } as any,
  axisRow: {
    flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between',
    gap: space.md, paddingVertical: 7,
  },
  axisKey: { ...type.bodySmall, color: color.muted, flexShrink: 0 } as any,
  axisVal: { ...type.bodySmall, color: color.fg, fontWeight: '600', flex: 1, textAlign: 'right' } as any,
  retake: { ...type.labelMedium, color: color.primary, fontWeight: '600', paddingTop: space.sm } as any,

  cap: { ...type.bodySmall, color: color.muted, paddingHorizontal: 4 } as any,
  story: {
    minHeight: 180, borderRadius: rad.md, backgroundColor: color.card,
    borderWidth: 1, borderColor: color.border,
    padding: 14, color: color.fg, fontSize: 15, lineHeight: 22,
  },
  storyFoot: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 4 },

  // Предложение из истории. Токены, своих чисел и цветов нет.
  fromStory: { gap: space.xs, marginTop: space.sm },
  fromStoryTitle: { ...type.body, color: color.fg, fontWeight: '700' } as any,
  fromStoryNote: { ...type.bodySmall, color: color.muted, marginBottom: space.xs } as any,
  pick: {
    borderRadius: rad.lg, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, paddingHorizontal: 14, paddingVertical: 10, gap: 2,
  },
  pickOn: { backgroundColor: color.primary, borderColor: color.primary },
  pickLabel: { ...type.body, color: color.fg, fontWeight: '700' } as any,
  pickWhy: { ...type.bodySmall, color: color.muted } as any,
  count: { ...type.caption, color: color.neutral400 } as any,
  savedNote: { ...type.caption, color: color.successText } as any,

  cta: { height: 48, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  dark: { height: 44, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  darkText: { ...type.button, color: color.onPrimary } as any,

  // «Сохранить историю» — не главное действие экрана (главное внизу, «Сохранить и закрыть»),
  // поэтому мягкая кнопка, а не красная: две красные подряд спорят друг с другом.
  applyBtn: {
    height: 44, borderRadius: rad.full, backgroundColor: color.infoBg,
    alignItems: 'center', justifyContent: 'center', marginTop: space.sm,
  },
  applyText: { ...type.button, color: color.primary } as any,
  errNote: { ...type.bodySmall, color: color.primary, paddingHorizontal: 4 } as any,
  rebuiltBox: { backgroundColor: color.successBg, borderRadius: rad.lg, padding: space.md, gap: 4 },
  rebuiltLabel: { ...type.labelSmall, color: color.successText, fontWeight: '700' } as any,
  rebuiltText: { ...type.bodySmall, color: color.successText } as any,
});
