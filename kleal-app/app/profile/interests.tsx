/**
 * Профиль → «Интересы».
 *
 * Переключатель у каждого интереса — не украшение: выключенный интерес перестаёт участвовать в
 * подборе. Поэтому под списком прямо написано, что делает включённое положение, а сам список
 * показывает не только название, но и то, ЧТО Kleal про этот интерес знает — роль, опыт, уровень.
 * Разговор из онбординга собирает ровно это, и здесь оно наконец видно.
 *
 * Выключенные хранятся отдельным списком `interests.unused`, а не удалением из `explicit`: человек
 * сказал, что увлекается этим, и «не искать по этому» — не то же самое, что «я этим не увлекаюсь».
 */
import { useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, Pressable, Alert, Platform } from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { ProfileShell, Card, SectionHead, SwitchCard, KlealPill } from '../../src/components/ProfileShell';
import { useLang, T } from '../../src/i18n';
import { useOnb, set, get } from '../../src/state';
import { profileData, INTERESTS_SCREEN as C, SECTIONS, adaptSummary, pushInterests,
         syncInterestLabels, HUB, PRO, fmtUpdated } from '../../src/profile';
import { color, type } from '../../src/theme';

export default function Interests() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const d = useMemo(() => profileData(st.profile), [st.profile, lang]);

  /**
   * Записать интересы на сервер и подтянуть за ними сводку: она перечисляет интересы вслух, и после
   * удаления одного из них продолжала бы про него рассказывать. Так же устроен веб.
   */
  const push = () => {
    // pushInterests шлёт ПЛОСКИЙ список без выключенных — форму, которую ждёт строка. Раньше отсюда
    // уходил вложенный объект целиком, а сервер делает слепой row.update(): строка получала вместо
    // списка словарь, и матчинг для этого человека ломался молча.
    pushInterests();
    adaptSummary();
  };

  /**
   * Интересы, добавленные в разговоре, отправляются при ВОЗВРАЩЕНИИ на этот экран.
   *
   * «Добавить» уводит в `/chat?step=hobbies&back=/profile/interests`, и оттуда интересы приходят
   * только в состояние на устройстве: разговорная ручка в стор не пишет, а выход из разговора
   * просто переключает экран. Записывали их лишь тумблер и удаление — то есть человек, который
   * ничего больше не трогал, оставался невидим по тому, что сам про себя рассказал.
   *
   * Именно фокус, а не выход из разговора: вернуться сюда можно и системным «назад», и жестом, и
   * кнопкой, а фокус ловит все три. Повторов бояться не нужно — pushInterests сверяет отпечаток.
   */
  useFocusEffect(
    useCallback(() => {
      pushInterests();
      // И подписи: интересы в строке — английские ключи, переводы приезжают с сервера. Вызывать
      // ручку профиля было некому, поэтому среди своих же чипов светились `podcasts` и `dancing`.
      syncInterestLabels();
    }, [])
  );

  const toggleUsed = (nm: string, on: boolean) => {
    const unused: string[] = get('interests.unused') || [];
    set('interests.unused', on ? unused.filter((x) => x !== nm) : [...unused, nm]);
    push();
  };

  const remove = (nm: string, label: string) => {
    const wipe = () => {
      set('interests.explicit', (get('interests.explicit') || []).filter((x: string) => x !== nm));
      set('interests.unused', (get('interests.unused') || []).filter((x: string) => x !== nm));
      push();
    };
    const ask = T(`Убрать «${label}» из профиля?`, `Remove “${label}” from your profile?`, `¿Eliminar «${label}» de tu perfil?`);
    if (Platform.OS === 'web') {
      // Alert.alert на вебе рисуется без кнопок — там это window.confirm.
      // eslint-disable-next-line no-alert
      if (typeof confirm === 'function' && confirm(ask)) wipe();
      return;
    }
    Alert.alert(ask, undefined, [
      { text: T('Отмена', 'Cancel', 'Cancelar'), style: 'cancel' },
      { text: C.remove(), style: 'destructive', onPress: wipe },
    ]);
  };

  const summary = String((st.profile as any).summary || '');
  const updated = fmtUpdated((st.profile as any).summaryUpdated);

  return (
    <ProfileShell title={SECTIONS[0].title()} onBack={() => router.back()}>
      {/* B.04 — сверху сводка Kleal: она и перечисляет интересы вслух. Правка — разговором. */}
      {summary ? (
        <Card>
          <View style={s.head}>
            <Text style={s.label}>{HUB.summaryLabel()}</Text>
            {updated ? <Text style={s.updated}>{updated}</Text> : null}
          </View>
          <Text style={s.body}>{summary}</Text>
          <KlealPill label={PRO.changeWithKleal()} onPress={() => router.navigate('/chat?step=hobbies&back=/profile/interests')} />
        </Card>
      ) : null}

      {d.interests.length === 0 ? (
        <SectionHead title={C.emptyTitle()} note={C.emptySub()} />
      ) : (
        <>
          <SectionHead title={C.yours()} note={C.yoursNote()} />
          {/*
            Тумблер — настоящий: выключенный интерес уходит в `interests.unused` и не едет в подбор.
            Удаления на кадре нет; оно осталось долгим нажатием по строке — терять его нельзя.
          */}
          {d.interests.map((it) => (
            <Pressable key={it.name} onLongPress={() => remove(it.name, it.label)} delayLongPress={400}
                       accessibilityHint={T('Долгое нажатие — убрать из профиля', 'Long press to remove from your profile', 'Mantén pulsado para quitarlo del perfil')}>
              <SwitchCard label={it.label} value={it.used} onChange={(v) => toggleUsed(it.name, v)} />
            </Pressable>
          ))}
        </>
      )}
      <View style={{ height: 8 }} />
      <KlealPill wide label={C.addOne()} onPress={() => router.navigate('/chat?step=hobbies&back=/profile/interests')} />
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 },
  label: { fontSize: 15, fontWeight: '600', color: color.fg } as any,
  updated: { ...type.caption, color: color.muted } as any,
  body: { ...type.bodySmall, color: color.fg } as any,
});
