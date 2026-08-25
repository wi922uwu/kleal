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
 */
import React, { useEffect, useRef } from 'react';
import {
  Animated,
  Image,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { mediaUrl } from '../api';
import { HOME, HomeInvite } from '../home';
import { T } from '../i18n';
import { hCommit, hTap } from '../haptics';
import { IconBell } from './icons';
import { color, radius as rad, space, type } from '../theme';

/** Отступ пузыря от краёв экрана — тот же, что у карточек главной. */
const EDGE = 16;
/** Потолок высоты: выше пузырь начинает спорить с экраном, ради которого он и не стал экраном. */
const MAX_H = 340;

export function NotifyBubble({ invites, onPick }: {
  invites: HomeInvite[];
  onPick: (inv: HomeInvite) => void;
}) {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [open, setOpen] = React.useState(false);
  const grow = useRef(new Animated.Value(0)).current;

  const W = width - EDGE * 2;
  const H = Math.min(MAX_H, 92 + invites.length * 64);

  useEffect(() => {
    if (open) {
      Animated.spring(grow, {
        toValue: 1,
        useNativeDriver: true,
        damping: 13,
        stiffness: 220,
        mass: 0.8,
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
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={T('Уведомления', 'Notifications')}
        style={s.bell}
        onPress={() => {
          hTap();
          setOpen(true);
        }}
      >
        <IconBell />
        {invites.length ? <View style={s.dot} /> : null}
      </Pressable>

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
              top: insets.top + 54,
              right: EDGE,
              width: W,
              maxHeight: H,
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
               всегда, и ответ «пока тихо» — тоже ответ. */
            <>
              <Text style={s.emptyTitle}>{HOME.bellQuiet()}</Text>
              <Text style={s.emptyNote}>{HOME.noInvitesNote()}</Text>
            </>
          )}
        </Animated.View>
      </Modal>
    </>
  );
}

// ===== вид
const s = StyleSheet.create({
  bell: {
    width: 42, height: 42, borderRadius: 21, backgroundColor: color.onCoverSoft,
    alignItems: 'center', justifyContent: 'center',
  },
  dot: {
    position: 'absolute', top: 10, right: 11, width: 8, height: 8,
    borderRadius: 4, backgroundColor: color.primary,
  },
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: color.scrim },
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
  emptyTitle: { ...type.title, color: color.fg } as any,
  emptyNote: { ...type.bodySmall, color: color.muted } as any,
});
