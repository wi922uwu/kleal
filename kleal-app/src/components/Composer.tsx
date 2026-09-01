/**
 * Нижняя строка «Message…» с кнопкой назад и микрофоном.
 *
 * Вынесена в компонент, потому что на борде она есть НЕ только в чате: кадр A.14 («Profile
 * summary») показывает её под кнопкой «Done». Это осмысленно — разговор с агентом не заканчивается
 * на последнем шаге анкеты, сводку тоже можно поправить словами.
 */
import React, { useEffect, useRef, useState } from 'react';
import { View, TextInput, Pressable, StyleSheet, Platform } from 'react-native';
import { BlurView } from 'expo-blur';
import { COMPOSER_PLACEHOLDER } from '../onboarding';
import { useKeyboardInset, dockBottom } from '../keyboard';
import { T } from '../i18n';
import { IconChevronLeft, IconMic } from './icons';
import { color, glass, radius as rad, space, type } from '../theme';
import { hTap } from '../haptics';

export function Composer({
  onBack,
  onSend,
  placeholder,
  focusSignal,
  disabled = false,
  bottomInset = 0,
}: {
  onBack?: () => void;
  onSend?: (text: string) => void;
  /** Своя подсказка в поле. На шаге разговора про интересы это «Расскажи Kleal больше…». */
  placeholder?: string;
  /**
   * Счётчик, по изменению которого поле получает фокус. Число, а не булево: «поставь курсор» —
   * это событие, оно повторяется, и второе нажатие на ту же кнопку тоже должно сработать.
   */
  focusSignal?: number;
  /**
   * Поле недоступно, и это ВИДНО.
   *
   * Раньше недоступность выражалась только через `editable={!!onSend}`: поле выглядело обычным,
   * приглашало «Сообщение…», а на касание не отзывалось ничем. На первом шаге онбординга, где
   * агент ещё только представился и ждёт «Поехали!», человек тыкал в живое на вид поле и не
   * понимал, почему оно молчит. Отключение обязано быть заметным.
   */
  disabled?: boolean;
  bottomInset?: number;
}) {
  const [draft, setDraft] = useState('');
  const input = useRef<TextInput>(null);

  useEffect(() => {
    if (focusSignal) input.current?.focus();
  }, [focusSignal]);
  const send = () => {
    const t = draft.trim();
    if (!t || !onSend) return;
    setDraft('');
    onSend(t);
  };

  /**
   * На Android клавиатура ложится ПОВЕРХ композера: окно под неё больше не ужимается (edge-to-edge
   * в SDK 54), а KeyboardAvoidingView там ничего не делает. Поднимаем сами — см. src/keyboard.ts,
   * там же про то, почему это не ломает случаи, где система справляется сама.
   */
  const kb = useKeyboardInset();

  return (
    <View style={[s.dock, { paddingBottom: dockBottom(bottomInset, kb) }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={T('Назад', 'Back')}
        style={s.back}
        onPress={() => {
          hTap();
          onBack?.();
        }}
      >
        <BlurView intensity={glass.blur} tint="light" style={StyleSheet.absoluteFill} />
        <View
          style={[StyleSheet.absoluteFill, { backgroundColor: color.glassLight, opacity: glass.lightAlpha }]}
        />
        <IconChevronLeft />
      </Pressable>
      <View style={[s.field, disabled && s.fieldOff]} pointerEvents={disabled ? 'none' : 'auto'}>
        {/*
          Поле — стекло, а не серая плашка: под ним фирменный фон, и сплошная заливка вырезала бы
          в нём прямоугольник. Плотность 72% (в борде именно она) — выше, чем у кнопок: сюда пишут,
          и текст обязан читаться на любом месте фона.
        */}
        <BlurView intensity={glass.blur} tint="light" style={StyleSheet.absoluteFill} />
        <View style={[StyleSheet.absoluteFill, { backgroundColor: color.glassLight, opacity: 0.72 }]} />
        <TextInput
          ref={input}
          style={s.input}
          value={draft}
          onChangeText={setDraft}
          placeholder={placeholder || COMPOSER_PLACEHOLDER()}
          placeholderTextColor={color.muted}
          onSubmitEditing={send}
          returnKeyType="send"
          editable={!disabled && !!onSend}
        />
        <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send')} onPress={send}>
          <IconMic />
        </Pressable>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  /*
    ДОК ПРОЗРАЧЕН. В борде у композера стоит заливка `#F7F8FA` — но это цвет фона ОБЫЧНЫХ экранов,
    доставшийся компоненту по умолчанию: сам кадр стоит на фирменном кремовом. Непрозрачная полоса
    поверх него отрезала бы низ экрана серым прямоугольником, поэтому здесь фона нет вовсе, а
    держат строку стеклянные кнопка и поле.
  */
  /** Приглушение недоступного поля. Кнопка «назад» остаётся живой: уйти можно всегда. */
  fieldOff: { opacity: 0.45 },
  dock: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
  },
  back: {
    width: 44,
    height: 44,
    borderRadius: 22,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF88',
  },
  field: {
    flex: 1,
    // Высота выросла с 36 из борда: там она посчитана под кегль подсказки, а строка набирается
    // репликой — 22 пункта межстрочного в 36 не помещаются, текст обрезался бы сверху и снизу.
    height: 44,
    borderRadius: rad.full,
    overflow: 'hidden',
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: space.lg,
    paddingRight: 14,
    gap: space.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF88',
    ...Platform.select({
      ios: { shadowColor: color.ink, shadowOpacity: 0.1, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 3 },
    }),
  },
  /*
    КЕГЛЬ ПОЛЯ — КАК У РЕПЛИКИ, А НЕ КАК У ПОДСКАЗКИ. В борде надпись «Message…» набрана 11-м, и
    первая версия взяла этот кегль на само поле — но 11 пунктов это размер ПОДСКАЗКИ, серой и
    неподвижной. В поле по нему набирают живой текст, иногда длинный, и на телефоне он читался
    мелко до неудобства. Здесь тот же кегль, что в пузырях: набранное и отправленное выглядят
    одинаково, и это правильнее, чем совпасть с борда подписью.
  */
  input: { flex: 1, color: color.fg, ...type.bubble, paddingVertical: 0 } as any,
});
