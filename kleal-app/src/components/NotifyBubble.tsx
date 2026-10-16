/**
 * Колокольчик на главной и пузырь уведомлений под ним.
 *
 * КОЛОКОЛЬЧИК ДО СИХ ПОР НИЧЕГО НЕ ДЕЛАЛ. Он стоял в шапке с точкой «есть новое» и не открывался —
 * то есть обещал больше, чем умел: точка говорит «посмотри», а смотреть было некуда.
 *
 * ПОЧЕМУ ПУЗЫРЬ, А НЕ ЭКРАН. Приглашений два-три, и каждое — одна строка. Ради них уводить человека
 * с главной значит заставить его вернуться; а всё, что нужно, помещается в окно размером с треть
 * экрана. Пузырь ещё и не теряет контекст: главная остаётся видна под ним.
 *
 * РАСТЁТ ИЗ КОЛОКОЛЬЧИКА, А НЕ ИЗ СЕРЕДИНЫ. В React Native любое преобразование считается от центра
 * вида, поэтому пузырь, просто уменьшенный до нуля, «схлопывался» бы в свою середину — то есть в
 * пустое место посреди экрана, где ничего не нажимали. Сдвиг, который компенсирует изменение
 * размера, возвращает верхний правый угол на место: угол стоит, а пузырь из него разворачивается.
 * Это единственный способ задать точку роста, пока в RN нет `transformOrigin`.
 *
 * ПРУЖИНА С ЛЁГКИМ ПЕРЕЛЁТОМ. Затухание нарочно небольшое: окно чуть проскакивает размер и
 * возвращается — на этом и держится ощущение «выпрыгнуло», а не «появилось». Закрывается без
 * пружины: возврат с колебанием читается как «передумало закрываться».
 *
 * КНОПКА — СТЕКЛО ИЗ ШАПКИ GR.01. Круг 40 (не 42: в борде «Button/Icon Button» ровно 40) из того
 * же светлого стекла, что и прочие кнопки-знаки, вместо плоского белого кружка. Точка «есть новое»
 * — как «Bell Dot» борда: зелёная, 6×6 и в разрыве контура, а не коралловое пятно поверх него
 * (см. IconBellDot).
 */
import React, { useEffect, useRef } from 'react';
import {
  Animated,
  Easing,
  Image,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import Reanimated from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { mediaUrl } from '../api';
import { HOME, HomeInvite } from '../home';
import { T } from '../i18n';
import { hCommit, hTap } from '../haptics';
import { IconBellDot } from './icons';
import { GlassSurface, usePress } from './LiquidGlass';
import { color, radius as rad, space, type } from '../theme';

/** Отступ пузыря от краёв экрана — тот же, что у карточек главной. */
const EDGE = 16;
/** Потолок высоты: выше пузырь начинает спорить с экраном, ради которого он и не стал экраном. */
const MAX_H = 420;
/**
 * Пол высоты.
 *
 * ПУСТОЙ ПУЗЫРЬ — ТОЖЕ ОКНО. Первая версия сжималась по содержимому, и на пустых уведомлениях
 * получалась полоска в две строки: она читалась не как ответ, а как обрезок, и нажатие по
 * колокольчику выглядело неудачным. Окно одного роста и с содержимым, и без него: пустота внутри
 * него — это сообщение, а не отсутствие окна.
 */
const MIN_H = 236;

/** Кнопка колокольчика — круг 40 из шапки GR.01 («Button/Icon Button»). */
export const BELL_SIZE = 40;
/**
 * Верхнее поле шапки над кнопкой — pad 8 у «Greeting Header» в GR.01. Пузырь открывается под
 * колокольчиком, а колокольчик стоит на этом поле, поэтому шапка главной обязана держать тот же
 * отступ: разойдутся — пузырь либо наедет на кнопку, либо повиснет в воздухе под ней.
 */
export const BELL_HEAD_PAD = 8;
/** Зазор между низом колокольчика и верхом пузыря. */
const BUBBLE_GAP = 6;
/**
 * Точка «есть новое» — зелёная «Bell Dot» из GR.01. Своего токена у этого зелёного нет:
 * `successText` — цвет ТЕКСТА, он заметно темнее и на светлом стекле был бы тёмным пятном, а не
 * огоньком.
 */
const UNREAD = '#1FAE5E';

export function NotifyBubble({ invites, onPick }: {
  invites: HomeInvite[];
  onPick: (inv: HomeInvite) => void;
}) {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [open, setOpen] = React.useState(false);
  const grow = useRef(new Animated.Value(0)).current;
  const press = usePress();

  const W = width - EDGE * 2;
  const H = Math.max(MIN_H, Math.min(MAX_H, 92 + invites.length * 64));

  useEffect(() => {
    if (open) {
      // Раскрытие — плавное замедление без отскока: пузырь не «выпрыгивает», а разворачивается.
      Animated.timing(grow, {
        toValue: 1,
        duration: 260,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start();
    } else {
      grow.setValue(0);
    }
  }, [grow, open]);

  const scale = grow.interpolate({ inputRange: [0, 1], outputRange: [0.55, 1] });
  /** (1 − scale) — насколько пузырь сейчас меньше своего размера. Из этого и считается сдвиг. */
  const short = Animated.add(1, Animated.multiply(scale, -1));

  const shut = () => setOpen(false);

  return (
    <>
      {/*
        Отклик — масштабом на обёртке, а не прозрачностью: системное стекло не рисуется, если у
        него или у любого предка непрозрачность меньше 1. Стекло внутри Pressable — с
        pointerEvents="none": живое стекло забирает касание себе, и кнопка перестаёт нажиматься.
        Касание шире круга (hitSlop): 40 меньше пальцевых 44, а рисовать круг больше борда нельзя.
      */}
      <Reanimated.View style={[s.bell, press.style]}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={T('Уведомления', 'Notifications', 'Notificaciones')}
          hitSlop={8}
          onPressIn={press.onPressIn}
          onPressOut={press.onPressOut}
          onPress={() => {
            hTap();
            setOpen(true);
          }}
        >
          <GlassSurface tone="light" radius={BELL_SIZE / 2} pointerEvents="none" style={s.bellGlass}>
            <IconBellDot size={24} c={color.fg} dot={invites.length ? UNREAD : undefined} />
          </GlassSurface>
        </Pressable>
      </Reanimated.View>

      <Modal visible={open} transparent animationType="none" onRequestClose={shut}>
        {/*
          Затемнение закрывает пузырь по нажатию мимо него. Оно же не даёт нажать на то, что под
          ним: пока окно открыто, главная — фон, а не рабочая поверхность.
        */}
        <Pressable style={s.scrim} onPress={shut} />
        <Animated.View
          style={[
            s.bubble,
            {
              top: insets.top + BELL_HEAD_PAD + BELL_SIZE + BUBBLE_GAP,
              right: EDGE,
              width: W,
              // ВЫСОТА, А НЕ ПОТОЛОК. С `maxHeight` окно сжималось по содержимому, и пустое
              // состояние не могло растянуться до своего роста: `flex` внутри нечего было делить.
              height: H,
              opacity: grow,
              transform: [
                { translateX: Animated.multiply(short, W / 2) },
                { translateY: Animated.multiply(short, -H / 2) },
                { scale },
              ],
            },
          ]}
        >
          <Text style={s.title}>{HOME.invites()}</Text>

          {invites.length ? (
            <ScrollView showsVerticalScrollIndicator={false}>
              {invites.map((inv) => (
                <Pressable
                  key={inv.id}
                  accessibilityRole="button"
                  style={({ pressed }) => [s.row, pressed && s.rowOn]}
                  onPress={() => {
                    hCommit();
                    shut();
                    onPick(inv);
                  }}
                >
                  {inv.from.photo ? (
                    <Image source={{ uri: mediaUrl(String(inv.from.photo)) }} style={s.ava} />
                  ) : (
                    <View style={[s.ava, s.avaEmpty]}>
                      <Text style={s.init}>{(inv.from.name || '?').slice(0, 1).toUpperCase()}</Text>
                    </View>
                  )}
                  <View style={{ flex: 1 }}>
                    <Text style={s.name} numberOfLines={1}>{inv.from.name}</Text>
                    <Text style={s.sub} numberOfLines={1}>
                      {String(inv.intent.title || '').trim() || inv.note || HOME.wantsToMeet()}
                    </Text>
                  </View>
                  <Text style={s.go}>›</Text>
                </Pressable>
              ))}
            </ScrollView>
          ) : (
            /* Пустой пузырь честнее закрытого: точки на колокольчике нет, но нажать по нему можно
               всегда, и «уведомлений пока не было» — тоже ответ. Заодно вторая строка объясняет,
               ЧТО сюда придёт, — иначе окно сообщает только об отсутствии. */
            <View style={s.empty}>
              <Text style={s.emptyTitle}>{HOME.bellQuiet()}</Text>
              <Text style={s.emptyNote}>{HOME.bellQuietNote()}</Text>
            </View>
          )}
        </Animated.View>
      </Modal>
    </>
  );
}

// ===== вид
const s = StyleSheet.create({
  /*
    ОБЁРТКА РОВНО 40×40. Без размера строка шапки растягивала бы её, и масштаб отклика считался бы от
    чужого центра. Тени нет: у кнопки в GR.01 из эффектов только стекло.
  */
  bell: { width: BELL_SIZE, height: BELL_SIZE, borderRadius: BELL_SIZE / 2 },
  bellGlass: { width: BELL_SIZE, height: BELL_SIZE, alignItems: 'center', justifyContent: 'center' },
  scrim: { ...StyleSheet.absoluteFill, backgroundColor: color.scrim },
  bubble: {
    position: 'absolute',
    backgroundColor: color.card,
    borderRadius: rad.xxl,
    padding: space.lg,
    gap: space.sm,
  },
  title: { ...type.labelMedium, color: color.muted } as any,
  row: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    paddingVertical: 10, borderRadius: rad.lg,
  },
  rowOn: { backgroundColor: color.neutral100 },
  ava: { width: 40, height: 40, borderRadius: 20 },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  init: { ...type.title, color: color.muted } as any,
  name: { ...type.title, color: color.fg } as any,
  sub: { ...type.bodySmall, color: color.muted } as any,
  go: { ...type.h2, color: color.neutral400 } as any,
  /** Пустой текст стоит по центру окна, а не липнет к заголовку: иначе низ выглядит отрезанным. */
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.sm, paddingHorizontal: space.md },
  emptyTitle: { ...type.title, color: color.fg, textAlign: 'center' } as any,
  emptyNote: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,
});
