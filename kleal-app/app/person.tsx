/**
 * Профиль собеседника из разговора — ЗАГРУЗЧИК, а не ещё один экран карточки.
 *
 * Сначала здесь была своя вёрстка, и это была ошибка: в продукте уже есть карточка человека —
 * кадр O.13, `app/candidate.tsx`, с большим фото, именем и возрастом, чипами интересов, сводкой
 * Kleal и припиской приватности. Вторая карточка рядом с ней означала бы два места, где один и
 * тот же человек выглядит по-разному, и расходиться они начали бы с первой же правки дизайна.
 *
 * Поэтому экран делает ровно одно: спрашивает карточку у сервера, кладёт её в ту же передачу,
 * которой пользуется выдача (`setCandidate`), и заменяет себя настоящей карточкой. `replace`, а не
 * `navigate`: назад человек должен вернуться в разговор, а не на пустой загрузчик.
 *
 * Ждать здесь, а не в шапке разговора, — сознательно: запрос идёт до сервера, и нажатие, которое
 * молчит секунду, читается как несработавшее.
 */
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { agent } from '../src/api';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { setCandidate } from '../src/results-store';
import { PERSON } from '../src/person';
import { color, radius as rad, space, type } from '../src/theme';

export default function Person() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const st = useOnb();
  const params = useLocalSearchParams<{ who?: string; photo?: string }>();
  const who = String(params.who || '');
  const me = String(st.profile?.name || '');

  const [err, setErr] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!who) { setErr(PERSON.failed()); return; }
      try {
        const r: any = await agent.person(me, who);
        if (!alive) return;
        if (r?.ok && r.person) {
          // Фото из параметра — запасное: оно уже было в шапке разговора, и если сервер его не
          // прислал (у человека его нет в строке), карточка всё равно откроется не пустой.
          setCandidate({ ...r.person, photo: r.person.photo || String(params.photo || '') });
          // `from: 'chat'` — не украшение: карточка по нему убирает «Пригласить». Признак идёт
          // параметром, а не полем карточки: карточка описывает ЧЕЛОВЕКА, а откуда её открыли —
          // свойство перехода, и мешать эти две вещи значит однажды показать «Пригласить» в чате
          // просто потому, что объект приехал из кэша.
          router.replace({ pathname: '/candidate', params: { from: 'chat' } });
          return;
        }
        // Причину называем словами человека, а не кодом сервера: «NOT_MATCHED» ему ни о чём.
        setErr(r?.error === 'NOT_MATCHED' ? PERSON.notMatched(who) : PERSON.failed());
      } catch {
        if (alive) setErr(PERSON.offline());
      }
    })();
    return () => { alive = false; };
  }, [who, me]);

  return (
    <View style={[s.wrap, { paddingTop: insets.top }]}>
      {err ? (
        <View style={s.box}>
          <Text style={s.err}>{err}</Text>
          <Pressable
            accessibilityRole="button"
            style={s.cta}
            onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}
          >
            <Text style={s.ctaText}>{T('Назад', 'Back', 'Atrás')}</Text>
          </Pressable>
        </View>
      ) : (
        <ActivityIndicator color={color.primary} />
      )}
    </View>
  );
}

// ===== вид

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase, alignItems: 'center', justifyContent: 'center', padding: space.lg },
  box: { gap: space.lg, alignItems: 'center' },
  err: { ...type.body, color: color.fg, textAlign: 'center' } as any,
  cta: {
    height: 48, paddingHorizontal: space.xl, borderRadius: rad.full,
    backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center',
  },
  ctaText: { ...type.button, color: '#fff' } as any,
});
