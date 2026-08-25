/**
 * Нижняя панель приложения — кадр A.15.
 *
 * Раньше жила прямо в финале онбординга и была картинкой: четыре подписи, ни одна никуда не ведёт.
 * Здесь она общая и настоящая.
 *
 * НОВЫЙ ВИД: не полоса во всю ширину, а стеклянная пилюля 310×48, приподнятая над краем экрана, с
 * каплей Kleal посередине. Четыре знака стоят парами по бокам от неё — по борду, с промежутком в
 * 72 точки, куда капля и садится.
 *
 * ПОДПИСЕЙ ПОД ЗНАКАМИ БОЛЬШЕ НЕТ, и это не упрощение: в кадре их нет вовсе. На пилюле высотой 48
 * подпись физически не помещается рядом со знаком 24×24, а прежние 9,5 пункта были на грани
 * читаемости. Имя вкладки осталось там, где оно действительно нужно, — в `accessibilityLabel`, то
 * есть для читающих экраном.
 *
 * Непере­несённые вкладки приглушены и не нажимаются. Кнопка, которая выглядит рабочей и молча
 * ничего не делает, хуже честно выключенной — человек нажимает её второй и третий раз, думая,
 * что не попал. Осталась одна такая: «Поиск».
 */
import React from 'react';
import { View, StyleSheet, Platform, Pressable } from 'react-native';
import { BlurView } from 'expo-blur';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { IconLayers, IconSearch, IconMessages, IconProfile } from './icons';
import { LogoMark } from './Logo';
import { NAV } from '../onboarding';
import { T } from '../i18n';
import { hTap } from '../haptics';
import { color, space } from '../theme';

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
        hitSlop={8}
        /*
          ВКЛАДКА ВСЕГДА НА ОДНОЙ ГЛУБИНЕ, А НЕ СТОПКОЙ.

          Было `push`: каждое нажатие добавляло ЕЩЁ ОДИН экран поверх — хоть двадцать профилей
          подряд, — и потом столько же раз надо было нажать «назад». Панель видна на девяти
          экранах, так что набрать стопку можно было не заметив.

          Одного `navigate` мало, и это проверено на устройстве: он не кладёт второй ТАКОЙ ЖЕ
          экран, но чередование вкладок стопку всё равно растит. «Сообщения → профиль → сообщения»
          давало три экрана, и «назад» из сообщений вело в профиль, а не домой.

          Поэтому переход сначала СВОРАЧИВАЕТ стопку до главной, а потом открывает вкладку. Глубина
          всегда одна и та же: [главная, вкладка]. «Назад» из любой вкладки ведёт на главную — то,
          чего человек и ждёт от нижней панели.

          `dismissTo`, а не `dismissAll`: корень стопки — не главная, а вступительные слайды
          (app/index.tsx остаётся смонтированным), и «свернуть всё» выбросило бы человека туда.
          Если главной в стопке нет вовсе, `dismissTo` заменит ею текущий экран — тоже разумно.

          На ТЕКУЩЕЙ вкладке не делаем ничего: нажатие по ней — промах или привычка.
        */
        onPress={to && !on ? () => { hTap(); router.dismissTo('/home'); router.navigate(to as any); } : undefined}
        style={[s.item, !to && s.off]}
      >
        <Icon size={24} c={on ? color.primary : color.muted} />
      </Pressable>
    );
  };

  return (
    <View style={[s.wrap, { paddingBottom: Math.max(insets.bottom, space.md) }]}>
      <View style={s.bar}>
        {/*
          Стекло панели плотнее кнопочного (72% против 42%): под ней проезжает содержимое экрана, и
          на просвет сквозь редкую плёнку знаки терялись бы ровно тогда, когда под панелью что-то
          пёстрое — то есть на ленте карточек, где панель и нужна.
        */}
        <BlurView intensity={32} tint="light" style={StyleSheet.absoluteFill} />
        <View style={[StyleSheet.absoluteFill, { backgroundColor: color.glassLight, opacity: 0.72 }]} />

        <View style={s.side}>
          {item('intents', nav[0], IconLayers)}
          {item('search', nav[1], IconSearch)}
        </View>
        {/* Место под каплю. Она лежит ОТДЕЛЬНО и поверх — иначе её тень обрезалась бы пилюлей. */}
        <View style={s.gap} />
        <View style={s.side}>
          {item('messages', nav[2], IconMessages)}
          {item('profile', nav[3], IconProfile)}
        </View>
      </View>

      {/*
        КАПЛЯ ПОВЕРХ ПИЛЮЛИ, А НЕ ВНУТРИ НЕЁ. В кадре она чуть выше панели и выходит за её верхнюю
        кромку; ребёнком пилюли с `overflow: hidden` (а он нужен, чтобы скруглить размытие) её
        просто срезало бы сверху.
      */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={NAV_FAB()}
        style={s.drop}
        /*
          Тоже не `replace`. Тот подменял ВЕРХНИЙ экран главной, оставляя всё, что под ним: из
          [главная, профиль] получалось [главная, главная], и «назад» вело на главную же.
          `dismissTo` возвращает к той главной, что уже открыта, снимая всё, что над ней.
        */
        onPress={() => {
          hTap();
          router.dismissTo('/home');
        }}
      >
        <LogoMark width={42} />
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

// ===== вид
/** Размеры пилюли из борда: 310×48 при ширине экрана 390, то есть по 40 с каждой стороны. */
const BAR_H = 48;

const s = StyleSheet.create({
  wrap: { paddingHorizontal: 40, alignItems: 'center' },
  bar: {
    width: '100%',
    height: BAR_H,
    borderRadius: 40,
    overflow: 'hidden',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: space.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#FFFFFF88',
    ...Platform.select({
      ios: { shadowColor: color.ink, shadowOpacity: 0.12, shadowRadius: 24, shadowOffset: { width: 0, height: 8 } },
      android: { elevation: 8 },
    }),
  },
  /** Пара знаков с зазором 16 — как в кадре. */
  side: { flexDirection: 'row', alignItems: 'center', gap: space.lg },
  /** Промежуток под каплю: 72 точки из борда. */
  gap: { flex: 1, minWidth: 72 },
  item: { width: 40, height: 32, alignItems: 'center', justifyContent: 'center' },
  off: { opacity: 0.38 },
  drop: {
    position: 'absolute',
    alignSelf: 'center',
    // Капля выше пилюли на пару точек — ровно как в кадре, где она выходит за верхнюю кромку.
    top: -2,
    width: 42,
    alignItems: 'center',
    justifyContent: 'center',
    ...Platform.select({
      ios: { shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 12, shadowOffset: { width: 0, height: 6 } },
      android: { elevation: 10 },
    }),
  },
});
