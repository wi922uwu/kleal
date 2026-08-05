/**
 * Нижняя строка «Message…» с кнопкой назад и микрофоном.
 *
 * Вынесена в компонент, потому что на борде она есть НЕ только в чате: кадр A.14 («Profile
 * summary») показывает её под кнопкой «Done». Это осмысленно — разговор с агентом не заканчивается
 * на последнем шаге анкеты, сводку тоже можно поправить словами.
 */
import React, { useState } from 'react';
import { View, TextInput, Pressable, StyleSheet } from 'react-native';
import { COMPOSER_PLACEHOLDER } from '../onboarding';
import { T } from '../i18n';
import { IconChevronLeft, IconMic } from './icons';
import { color, radius as rad, space } from '../theme';

export function Composer({
  onBack,
  onSend,
  placeholder,
  bottomInset = 0,
}: {
  onBack?: () => void;
  onSend?: (text: string) => void;
  /** Своя подсказка в поле. На шаге разговора про интересы это «Расскажи Kleal больше…». */
  placeholder?: string;
  bottomInset?: number;
}) {
  const [draft, setDraft] = useState('');
  const send = () => {
    const t = draft.trim();
    if (!t || !onSend) return;
    setDraft('');
    onSend(t);
  };

  return (
    <View style={[s.dock, { paddingBottom: Math.max(bottomInset, 10) }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={T('Назад', 'Back')}
        style={s.back}
        onPress={onBack}
      >
        <IconChevronLeft />
      </Pressable>
      <View style={s.field}>
        <TextInput
          style={s.input}
          value={draft}
          onChangeText={setDraft}
          placeholder={placeholder || COMPOSER_PLACEHOLDER()}
          placeholderTextColor={color.neutral400}
          onSubmitEditing={send}
          returnKeyType="send"
          editable={!!onSend}
        />
        <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send')} onPress={send}>
          <IconMic />
        </Pressable>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  dock: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: 16,
    paddingTop: space.sm,
    backgroundColor: color.bg,
  },
  back: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: color.border,
    backgroundColor: color.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  field: {
    flex: 1,
    height: 48,
    borderRadius: rad.full,
    backgroundColor: color.neutral100,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 18,
    gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
});
