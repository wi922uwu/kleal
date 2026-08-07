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
import { View, Text, StyleSheet, Pressable, Image, TextInput } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card } from '../../src/components/ProfileShell';
import { IconPerson } from '../../src/components/icons';
import { useLang } from '../../src/i18n';
import { useOnb, set } from '../../src/state';
import { profile as profileApi } from '../../src/api';
import { PERSONALITY as C, STORY_MAX, fmtUpdated } from '../../src/profile';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Personality() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const p: any = st.profile;

  const [story, setStory] = useState<string>(String(p.story || ''));
  const [saved, setSaved] = useState(false);

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
    return true;
  };

  const text = String(p.personality || '');
  const updated = fmtUpdated(p.personalityUpdated);

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
          <Image source={{ uri: p.photo }} style={s.photo} />
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

  cap: { ...type.bodySmall, color: color.muted, paddingHorizontal: 4 } as any,
  story: {
    minHeight: 180, borderRadius: rad.md, backgroundColor: color.card,
    borderWidth: 1, borderColor: color.border,
    padding: 14, color: color.fg, fontSize: 15, lineHeight: 22,
  },
  storyFoot: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 4 },
  count: { ...type.caption, color: color.neutral400 } as any,
  savedNote: { ...type.caption, color: color.successText } as any,

  cta: { height: 48, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  dark: { height: 44, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  darkText: { ...type.button, color: color.onPrimary } as any,
});
