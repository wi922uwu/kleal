/**
 * Сводка профиля перед отправкой. Порт «goSummary».
 *
 * Текст про человека пишет агент (/api/onboarding/summary) — но экран не должен зависеть от того,
 * ответила ли модель: если она молчит или упала, сводка собирается из уже введённых полей. Пустой
 * экран на последнем шаге онбординга стоит дороже, чем неидеальная формулировка.
 */
import React, { useEffect, useState } from 'react';
import { View, StyleSheet, Text, ScrollView, Image } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, profileForRegister, profileForAttach } from '../src/state';
import { onboarding } from '../src/api';
import { genderLabel, langLabel, intLabel } from '../src/onboarding';
import { Btn } from '../src/components/ui';
import { color, radius, space, type } from '../src/theme';

export default function Summary() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const p = st.profile;
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    let alive = true;
    onboarding
      .summary(profileForAttach())
      .then((r: any) => alive && setText(String(r?.summary || '')))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const rows: [string, string][] = [
    [T('Имя', 'Name'), p.name || '—'],
    [T('О себе', 'About'), [p.gender ? genderLabel(p.gender) : '', p.age ? String(p.age) : ''].filter(Boolean).join(', ') || '—'],
    [T('Где', 'Where'), p.city || '—'],
    [T('Языки', 'Languages'), (p.languages?.comfortable || []).map(langLabel).join(', ') || '—'],
    [T('Интересы', 'Interests'), (p.interests?.explicit || []).map(intLabel).join(', ') || '—'],
  ];

  const finish = async () => {
    setSending(true);
    setErr('');
    try {
      const r: any = await onboarding.register(profileForRegister());
      if (!r?.ok) throw new Error(r?.error || 'register failed');
      // Привязываем к логину, чтобы следующий вход вёл в приложение, а не сюда же.
      if (st.login) {
        await onboarding.attach(st.login, p.name || '', profileForAttach()).catch(() => {});
      }
      router.replace('/done');
    } catch {
      // Молча «завершить» нельзя: профиль не доехал, и человек будет думать, что он в системе.
      setErr(T('Профиль не сохранился. Проверь связь и попробуй ещё раз.',
               "Your profile didn't save. Check your connection and try again."));
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 16 }]}>
      <ScrollView contentContainerStyle={s.scroll}>
        <Text style={s.h}>{T('Вот что получилось', "Here's what I got")}</Text>

        <View style={s.card}>
          <View style={s.idRow}>
            {p.photo ? (
              <Image source={{ uri: p.photo }} style={s.av} />
            ) : (
              <View style={[s.av, s.avEmpty]}>
                <Text style={s.avLetter}>{(p.name || '?').slice(0, 1).toUpperCase()}</Text>
              </View>
            )}
            <View style={{ flex: 1 }}>
              <Text style={s.name}>{p.name || '—'}</Text>
              <Text style={s.sub}>{[p.city, p.age ? String(p.age) : ''].filter(Boolean).join(' · ')}</Text>
            </View>
          </View>
        </View>

        {text ? (
          <View style={s.card}>
            <Text style={s.blockTitle}>{T('Как тебя понял Kleal', 'How Kleal understood you')}</Text>
            <Text style={s.para}>{text}</Text>
          </View>
        ) : null}

        <View style={s.card}>
          {rows.map(([k, v]) => (
            <View key={k} style={s.row}>
              <Text style={s.rowKey}>{k}</Text>
              <Text style={s.rowVal} numberOfLines={2}>{v}</Text>
            </View>
          ))}
        </View>

        {err ? <Text style={s.err}>{err}</Text> : null}
      </ScrollView>

      <View style={[s.foot, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        <Btn label={T('Всё верно', 'Looks right')} busy={sending} onPress={finish} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  scroll: { paddingHorizontal: 20, paddingBottom: 24, gap: space.md },
  h: { ...type.h2, color: color.fg, marginBottom: space.sm } as any,
  card: { backgroundColor: color.card, borderRadius: radius.xl, padding: space.lg, gap: space.md, ...({} as any) },
  idRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  av: { width: 52, height: 52, borderRadius: radius.full },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  avLetter: { ...type.title, color: color.muted } as any,
  name: { ...type.title, color: color.fg } as any,
  sub: { ...type.bodySmall, color: color.muted } as any,
  blockTitle: { ...type.labelMedium, color: color.muted } as any,
  para: { ...type.body, color: color.fg } as any,
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
  rowKey: { ...type.bodySmall, color: color.muted } as any,
  rowVal: { ...type.bodySmall, color: color.fg, flex: 1, textAlign: 'right' } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  foot: { paddingHorizontal: 20, paddingTop: space.md },
});
