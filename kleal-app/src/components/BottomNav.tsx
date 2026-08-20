/**
 * Нижняя панель приложения.
 *
 * Раньше жила прямо в финале онбординга и была картинкой: четыре подписи, ни одна никуда не ведёт.
 * Здесь она общая и настоящая.
 *
 * Непере­несённые вкладки приглушены и не нажимаются. Кнопка, которая выглядит рабочей и молча
 * ничего не делает, хуже честно выключенной — человек нажимает её второй и третий раз, думая,
 * что не попал. Осталась одна такая: «Поиск».
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { IconIntents, IconSearch, IconMessages, IconProfile, IconSpark } from './icons';
import { NAV } from '../onboarding';
import { T } from '../i18n';
import { color } from '../theme';

export type Tab = 'intents' | 'search' | 'messages' | 'profile';

/** Что уже есть в приложении. Остальное — приглушено. */
const ROUTE: Partial<Record<Tab, string>> = {
  profile: '/profile', messages: '/messages', intents: '/activity',
};

export function BottomNav({ active }: { active?: Tab }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const nav = NAV();

  const item = (tab: Tab, label: string, Icon: (p: any) => React.ReactElement) => {
    const to = ROUTE[tab];
    const on = active === tab;
    return (
      <Pressable
        key={tab}
        accessibilityRole="button"
        accessibilityState={{ selected: on, disabled: !to }}
        accessibilityLabel={label}
        /*
          ВКЛАДКА НЕ КЛАДЁТСЯ СТОПКОЙ.
          
          Было `push`: каждое нажатие добавляло ЕЩЁ ОДИН экран поверх — хоть двадцать профилей
          подряд, — и потом столько же раз надо было нажать «назад». Панель видна на девяти
          экранах, так что набрать стопку можно было не заметив.
          
          `navigate` вместо `push`: если такой экран в стопке уже есть, он возвращает к нему, а не
          заводит второй. А если я УЖЕ на этой вкладке, не делаем ничего: нажатие на текущую
          вкладку — это промах или привычка, и открывать по нему нечего.
        */
        onPress={to && !on ? () => router.navigate(to as any) : undefined}
        style={[s.item, !to && s.off]}
      >
        <Icon size={24} c={on ? color.primary : color.muted} />
        <Text style={[s.label, on && { color: color.primary }]} numberOfLines={1}>{label}</Text>
      </Pressable>
    );
  };

  return (
    <View style={[s.wrap, { paddingBottom: Math.max(insets.bottom, 12) }]}>
      <View style={s.bar}>
        {item('intents', nav[0], IconIntents)}
        {item('search', nav[1], IconSearch)}
        <View style={{ width: 56 }} />
        {item('messages', nav[2], IconMessages)}
        {item('profile', nav[3], IconProfile)}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={NAV_FAB()}
        style={s.fab}
        /*
          Тоже не `replace`. Тот подменял ВЕРХНИЙ экран главной, оставляя всё, что под ним: из
          [главная, профиль] получалось [главная, главная], и «назад» вело на главную же. `navigate`
          возвращает к той главной, что уже открыта, и стопка не растёт.
        */
        onPress={() => router.navigate('/home')}
      >
        <IconSpark size={28} />
      </Pressable>
    </View>
  );
}

/**
 * Центральная кнопка — это «домой», а не «создать интент». Интент заводится текстом на главной
 * («Чем хочешь заняться?») или карточкой, а самая крупная кнопка панели нужна, чтобы одним
 * нажатием вернуться из любого места приложения.
 */
const NAV_FAB = () => T('Главная', 'Home');

const s = StyleSheet.create({
  wrap: { paddingHorizontal: 14 },
  bar: {
    height: 68, borderRadius: 34, backgroundColor: color.card,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around',
    shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 3,
  },
  // 66, а не 58: «Сообщения» в русском длиннее английского Messages и обрезалось в «Сообщен…».
  item: { alignItems: 'center', gap: 3, width: 66 },
  off: { opacity: 0.38 },
  label: { fontSize: 9.5, lineHeight: 13, color: color.muted, fontWeight: '500' },
  fab: {
    position: 'absolute', alignSelf: 'center', top: -14,
    width: 62, height: 62, borderRadius: 31, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: color.primary, shadowOpacity: 0.45, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 8,
  },
});
