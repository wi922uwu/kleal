/**
 * Настройки → «Аккаунт».
 *
 * Вход и удаление. Строки «Сменить пароль» здесь нет и не будет: вход устроен по коду на почту,
 * пароля у человека не существует, и пункт меню про его смену был обещанием несуществующего.
 *
 * ПОЧЕМУ СПРАШИВАЕМ ДВАЖДЫ. Первый вопрос — о намерении, второй — о необратимости, и это разные
 * вопросы. Удаление здесь настоящее: строка стирается и из файла, и из базы (`db.delete_user`), а
 * не помечается флагом. Пометка означала бы, что данные лежат дальше, а человек об этом не знает, —
 * и первый же читатель популяции, забывший про флаг, вернул бы удалённого в выдачу.
 *
 * ПОСЛЕ УДАЛЕНИЯ гасим всё то же, что и при выходе, и в том же порядке: историю — до сессии, иначе
 * стирать было бы нечем, а переписка осталась бы на диске.
 */
import React, { useState } from 'react';
import { View, Text, StyleSheet, Pressable, Alert, Platform, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card } from '../../src/components/ProfileShell';
import { useLang } from '../../src/i18n';
import { useOnb, reset } from '../../src/state';
import { forgetOwner } from '../../src/history';
import { auth, setSession } from '../../src/api';
import { ACCOUNT } from '../../src/settings';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Account() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const login = String(st.login || '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const wipeLocal = () => {
    forgetOwner();
    setSession('');
    reset();
    router.replace('/');
  };

  const doDelete = async () => {
    setBusy(true);
    setErr('');
    try {
      const r: any = await auth.deleteAccount();
      if (!r?.ok) {
        setErr(ACCOUNT.failed());
        setBusy(false);
        return;
      }
      wipeLocal();
    } catch {
      setErr(ACCOUNT.failed());
      setBusy(false);
    }
  };

  /** Две ступени. На вебе — два confirm подряд, на телефоне — два Alert. */
  const ask = () => {
    if (!login) {
      setErr(ACCOUNT.needSignIn());
      return;
    }
    if (Platform.OS === 'web') {
      // eslint-disable-next-line no-alert
      if (typeof confirm === 'function'
          && confirm(`${ACCOUNT.ask1()}\n\n${ACCOUNT.ask1Body()}`)
          // eslint-disable-next-line no-alert
          && confirm(`${ACCOUNT.ask2()}\n\n${ACCOUNT.ask2Body()}`)) doDelete();
      return;
    }
    Alert.alert(ACCOUNT.ask1(), ACCOUNT.ask1Body(), [
      { text: ACCOUNT.cancel(), style: 'cancel' },
      {
        text: ACCOUNT.confirm(),
        style: 'destructive',
        onPress: () =>
          Alert.alert(ACCOUNT.ask2(), ACCOUNT.ask2Body(), [
            { text: ACCOUNT.cancel(), style: 'cancel' },
            { text: ACCOUNT.confirm(), style: 'destructive', onPress: doDelete },
          ]),
      },
    ]);
  };

  return (
    <ProfileShell title={ACCOUNT.title()} onBack={() => router.back()}>
      <Card>
        <Text style={s.h}>{login ? ACCOUNT.signedAs(login) : ACCOUNT.noLogin()}</Text>
        {login ? null : <Text style={s.b}>{ACCOUNT.noLoginWhy()}</Text>}
      </Card>

      <Card>
        <Text style={s.h}>{ACCOUNT.deleteTitle()}</Text>
        <Text style={s.b}>{ACCOUNT.deleteDesc()}</Text>
        <Pressable
          accessibilityRole="button"
          disabled={busy}
          style={({ pressed }) => [s.danger, (pressed || busy) && { opacity: 0.85 }]}
          onPress={ask}
        >
          {busy
            ? <ActivityIndicator color="#fff" />
            : <Text style={s.dangerText}>{ACCOUNT.deleteTitle()}</Text>}
        </Pressable>
        {err ? <Text style={s.err}>{err}</Text> : null}
      </Card>
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  h: { ...type.title, color: color.fg } as any,
  b: { ...type.body, color: color.muted, marginTop: space.sm } as any,
  danger: {
    height: 52, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: space.lg,
  },
  dangerText: { ...type.button, color: '#fff' } as any,
  err: { ...type.caption, color: color.primary, marginTop: space.sm } as any,
});
