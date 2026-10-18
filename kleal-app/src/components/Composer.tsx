/**
 * Нижняя строка «Message…» с кнопкой назад и микрофоном.
 *
 * Вынесена в компонент, потому что на борде она есть НЕ только в чате: кадр A.14 («Profile
 * summary») показывает её под кнопкой «Done». Это осмысленно — разговор с агентом не заканчивается
 * на последнем шаге анкеты, сводку тоже можно поправить словами.
 */
import { useEffect, useRef, useState } from 'react';
import { View, TextInput, StyleSheet, Platform } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withSpring, withTiming } from 'react-native-reanimated';
import { COMPOSER_PLACEHOLDER } from '../onboarding';
import { useKeyboardInset, dockBottom } from '../keyboard';
import { SendArrow } from './SendArrow';
import { GlassSurface } from './LiquidGlass';
import { color, space, type } from '../theme';

/**
 * «НАЗАД» УШЛА В ШАПКУ. В макете «First run» композер — одно стеклянное поле во всю ширину с
 * коралловой кнопкой отправки, а круглая «назад» стоит слева в шапке разговора. `onBack` остался в
 * подписи ради старых вызовов: экран, который его передаёт, получит «назад» в шапке ChatShell.
 */
export function Composer({
  onSend,
  placeholder,
  focusSignal,
  disabled = false,
  bottomInset = 0,
}: {
  onBack?: () => void;
  onSend?: (text: string) => void;
  placeholder?: string;
  focusSignal?: number;
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

  /*
    КНОПКА ОТПРАВКИ ОЖИВАЕТ ВМЕСТЕ С ТЕКСТОМ. Пустое поле — кнопка чуть меньше, стрелка серая; первая
    буква — она спокойно встаёт в полный размер, стрелка коралловая. Так видно, что отправить есть что.
  */
  const has = !!draft.trim();
  const k = useSharedValue(has ? 1 : 0);
  useEffect(() => {
    // Появление — упругое, как у стрелки в чатах (ChatMotion): «можно отправлять» должно быть видно.
    k.value = has ? withSpring(1, { damping: 10, stiffness: 380, mass: 0.6 })
      : withTiming(0, { duration: 180, easing: Easing.out(Easing.cubic) });
  }, [has, k]);
  const btn = useAnimatedStyle(() => ({
    transform: [{ scale: 0.86 + k.value * 0.14 }],
  }));

  const kb = useKeyboardInset();

  return (
    <View style={[s.dock, { paddingBottom: dockBottom(bottomInset, kb) }]}>
      <View style={s.shadow} pointerEvents={disabled ? 'none' : 'auto'}>
        {/*
          Поле — жидкое стекло (белое 56% в макете): под ним фирменный фон, и сплошная заливка
          вырезала бы в нём прямоугольник.
        */}
        <GlassSurface tone="light" radius={999} style={s.field}>
          <TextInput
            ref={input}
            style={[s.input, disabled && s.inputOff]}
            value={draft}
            onChangeText={setDraft}
            placeholder={placeholder || COMPOSER_PLACEHOLDER()}
            placeholderTextColor={color.muted}
            onSubmitEditing={send}
            returnKeyType="send"
            editable={!disabled && !!onSend}
          />
          {/* Отправка «Chat/Composer»: стеклянный круг 44 с коралловой стрелкой (см. SendArrow). */}
          <Animated.View style={btn}>
            <SendArrow onPress={send} disabled={!has} />
          </Animated.View>
        </GlassSurface>
      </View>
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  /** Выключенное поле бледнеет подписью, а не прозрачностью: стекло под прозрачностью не рисуется. */
  inputOff: { color: color.muted },
  /*
    ДОК ПРОЗРАЧЕН: кадр стоит на фирменном кремовом, и непрозрачная полоса поверх него отрезала бы
    низ экрана. Держит строку само стеклянное поле.
  */
  dock: { paddingHorizontal: space.xl, paddingTop: space.sm },
  shadow: {
    borderRadius: 999,
    ...Platform.select({
      ios: { shadowColor: '#0A0A14', shadowOpacity: 0.08, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } },
      default: {},
    }),
  },
  /** Поле «Chat/Composer»: 48, слева 16, справа 2 — круг отправки 44 стоит почти вплотную к краю. */
  field: {
    height: 48,
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: space.lg,
    paddingRight: 2,
    gap: space.sm,
  },
  /** Кегль поля — как у реплики: набранное и отправленное выглядят одинаково. */
  input: { flex: 1, color: color.fg, ...type.bubble, paddingVertical: 0 } as any,
});
