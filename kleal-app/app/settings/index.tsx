/**
 * Настройки — кадр B.10.
 *
 * UX-каркас: вид натянется поверх, копия и правила в src/settings.ts.
 *
 * Приглушённых строк здесь больше нет ни одной. Прежде их было пять — оплата, смена пароля,
 * уведомления, помощь, тёмная тема, — и они честно не нажимались, но всё равно занимали экран и
 * обещали то, чего в продукте не будет: платежей нет, пушей нет (в package.json нет даже
 * expo-notifications), тёмных токенов в теме нет, а пароля у человека не существует — вход по коду
 * на почту. Строку, за которой ничего нет, правильнее убрать, чем аккуратно выключить: список
 * читают сверху вниз, и каждая мёртвая строка — лишний шаг до живой.
 *
 * У каждой оставшейся строки есть подпись: список из одних заголовков заставляет открывать экран,
 * чтобы понять, тот ли он.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable, Alert, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, Segments } from '../../src/components/ProfileShell';
import { useLang, setLang, getLang } from '../../src/i18n';
import { useOnb, reset } from '../../src/state';
import { forgetOwner } from '../../src/history';
import { SETTINGS, SETTING_ROWS, SettingRow } from '../../src/settings';
import { auth, setSession } from '../../src/api';
import { SIGNOUT } from '../../src/profile';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Settings() {
  useLang();                       // перерисовка при смене языка интерфейса
  const router = useRouter();
  const st = useOnb();

  const signOut = () => {
    const has = !!st.login;
    const go = () => {
      // Сессию гасим НА СЕРВЕРЕ, а не только на телефоне. Иначе выданный токен оставался бы
      // рабочим ещё три месяца: «выйти» очищало бы память приложения, а ключ от аккаунта
      // продолжал бы существовать. Не ждём ответа — выход не должен зависеть от связи, — но
      // и не молчим: сервер гасит именно эту сессию, остальные устройства не трогая.
      auth.signOut().catch(() => {});
      // ПОРЯДОК ВАЖЕН: историю стираем ДО того, как гасим сессию. Владелец записи определяется по
      // логину или токену, и после `setSession('')` их может уже не быть — тогда стирать было бы
      // нечего, а переписка осталась бы лежать на диске.
      forgetOwner();
      setSession('');
      reset();
      router.replace('/');
    };
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
        <View style={s.text}>
          <Text style={s.title}>{row.title()}</Text>
          <Text style={s.sub}>{row.sub()}</Text>
        </View>
        <Segments
          options={[['ru', 'RU'], ['en', 'EN']]}
          value={getLang()}
          onChange={(v) => setLang(v as any)}
        />
      </Card>
    );
  }

  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => onGo(row.to!)}
      style={({ pressed }) => [s.card, s.row, pressed && { opacity: 0.9 }]}
    >
      <View style={s.text}>
        <Text style={s.title}>{row.title()}</Text>
        <Text style={s.sub}>{row.sub()}</Text>
      </View>
      <Text style={s.chev}>›</Text>
    </Pressable>
  );
}

// ============================================================ вид

const s = StyleSheet.create({
  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.md },
  text: { flex: 1 },
  title: { ...type.body, color: color.fg } as any,
  sub: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  chev: { fontSize: 22, color: color.neutral400 },
  logout: { height: 54, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  logoutText: { ...type.button, color: '#fff' } as any,
});
