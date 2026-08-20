/**
 * Настройки — кадр B.10.
 *
 * UX-каркас: вид натянется поверх, копия и правила в src/settings.ts.
 *
 * Строки, за которыми в продукте ничего нет (оплата, смена пароля, уведомления, тёмная тема),
 * показаны приглушёнными и не нажимаются. Это то же правило, что и на нижней панели: строка,
 * которая выглядит рабочей и молча ничего не делает, хуже честно выключенной — человек жмёт её
 * второй и третий раз, думая, что промахнулся.
 */
import React from 'react';
import { Text, StyleSheet, Pressable, Alert, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, Segments } from '../../src/components/ProfileShell';
import { useLang, setLang, getLang } from '../../src/i18n';
import { useOnb, reset } from '../../src/state';
import { SETTINGS, SETTING_ROWS, SettingRow } from '../../src/settings';
import { SIGNOUT } from '../../src/profile';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Settings() {
  useLang();                       // перерисовка при смене языка интерфейса
  const router = useRouter();
  const st = useOnb();

  const signOut = () => {
    const has = !!st.login;
    const go = () => { reset(); router.replace('/'); };
    if (Platform.OS === 'web') {
      // eslint-disable-next-line no-alert
      if (typeof confirm === 'function' && confirm(SIGNOUT.ask(has))) go();
      return;
    }
    Alert.alert(SIGNOUT.ask(has), undefined, [
      { text: SIGNOUT.no(), style: 'cancel' },
      { text: SIGNOUT.yes(), style: 'destructive', onPress: go },
    ]);
  };

  return (
    <ProfileShell
      title={SETTINGS.title()}
      onBack={() => router.back()}
      footer={
        <Pressable accessibilityRole="button" style={s.logout} onPress={signOut}>
          <Text style={s.logoutText}>{SETTINGS.logout()}</Text>
        </Pressable>
      }
    >
      {SETTING_ROWS.map((row) => (
        <Row key={row.id} row={row} onGo={(to) => router.navigate(to as any)} />
      ))}
    </ProfileShell>
  );
}

function Row({ row, onGo }: { row: SettingRow; onGo: (to: string) => void }) {
  // Переключатель языка живёт прямо в строке: он мгновенный, и отдельный экран ради двух кнопок
  // был бы лишним шагом.
  if (row.control === 'lang') {
    return (
      <Card style={s.row}>
        <Text style={s.title}>{row.title()}</Text>
        <Segments
          options={[['ru', 'RU'], ['en', 'EN']]}
          value={getLang()}
          onChange={(v) => setLang(v as any)}
        />
      </Card>
    );
  }

  // Тёмной темы в приложении нет — ни одного тёмного токена. Рисовать выключатель, который
  // ничего не переключает, значит обещать то, чего не существует.
  if (row.control === 'dark') {
    return (
      <Card style={[s.row, s.off]}>
        <Text style={s.title}>{row.title()}</Text>
        <Text style={s.soon}>{SETTINGS.soon()}</Text>
      </Card>
    );
  }

  const live = !!row.to;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !live }}
      onPress={live ? () => onGo(row.to!) : undefined}
      style={({ pressed }) => [s.card, s.row, !live && s.off, pressed && live && { opacity: 0.9 }]}
    >
      <Text style={s.title}>{row.title()}</Text>
      {live ? <Text style={s.chev}>›</Text> : <Text style={s.soon}>{SETTINGS.soon()}</Text>}
    </Pressable>
  );
}

// ============================================================ вид

const s = StyleSheet.create({
  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.md },
  off: { opacity: 0.45 },
  title: { flex: 1, ...type.body, color: color.fg } as any,
  chev: { fontSize: 22, color: color.neutral400 },
  soon: { ...type.caption, color: color.muted } as any,
  logout: { height: 54, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  logoutText: { ...type.button, color: '#fff' } as any,
});
