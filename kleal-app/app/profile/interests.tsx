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
import React, { useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, Pressable, Switch, Alert, Platform } from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { ProfileShell, Card } from '../../src/components/ProfileShell';
import { useLang, T } from '../../src/i18n';
import { useOnb, set, get } from '../../src/state';
import { profileData, INTERESTS_SCREEN as C, SECTIONS, adaptSummary, pushInterests,
         syncInterestLabels } from '../../src/profile';
import { color, radius as rad, space, type } from '../../src/theme';

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

  return (
    <ProfileShell title={SECTIONS[0].title()} onBack={() => router.back()}>
      {d.interests.length === 0 ? (
        <Card>
          <Text style={s.emptyTitle}>{C.emptyTitle()}</Text>
          <Text style={s.emptySub}>{C.emptySub()}</Text>
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.navigate('/chat?step=hobbies&back=/profile/interests')}>
            <Text style={s.ctaText}>{C.add()}</Text>
          </Pressable>
        </Card>
      ) : (
        <>
          <Text style={s.hint}>{C.hint()}</Text>

          {/*
            Карточка НЕ раскрывается. Раньше тап показывал внутренности — «Роль», «Опыт», а когда их
            не было, заглушку «Kleal ещё разбирается…». Человек приходит сюда за одним: решить, что
            учитывать при подборе. Строка с тумблером отвечает на это целиком, а раскрытие лишь
            прятало удаление за лишним касанием и показывало то, чего он не спрашивал.

            «Уверенность» убрана раньше и по той же причине: это была внутренняя оценка
            derive-функции, а не факт о человеке.
          */}
          {d.interests.map((it) => (
            <Card key={it.name} style={{ gap: 0 }}>
              <View style={s.row}>
                <Text style={[s.name, { flex: 1 }]}>{it.label}</Text>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={T(`Удалить «${it.label}»`, `Remove “${it.label}”`, `Eliminar «${it.label}»`)}
                  hitSlop={10}
                  style={s.del}
                  onPress={() => remove(it.name, it.label)}
                >
                  <Text style={s.delText}>✕</Text>
                </Pressable>
                <Switch
                  value={it.used}
                  onValueChange={(v) => toggleUsed(it.name, v)}
                  accessibilityLabel={T(`Учитывать «${it.label}» при подборе`, `Use “${it.label}” for matching`, `Usa “${it.label}” para coincidir`)}
                  trackColor={{ false: color.neutral300, true: color.primary }}
                  thumbColor={color.card}
                  ios_backgroundColor={color.neutral300}
                />
              </View>
            </Card>
          ))}

          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.navigate('/chat?step=hobbies&back=/profile/interests')}>
            <Text style={s.ctaText}>{C.add()}</Text>
          </Pressable>
        </>
      )}
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  hint: { ...type.bodySmall, color: color.muted, paddingHorizontal: 4 } as any,
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  /** Крестик удаления: тихий, слева от тумблера — не спорит с ним за внимание. */
  del: { paddingHorizontal: 10, paddingVertical: 4 },
  delText: { fontSize: 17, color: color.neutral400 },
  name: { ...type.title, color: color.fg } as any,
  conf: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  exp: { marginTop: space.md, paddingTop: space.md, borderTopWidth: 1, borderTopColor: color.line, gap: space.sm },
  kv: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
  k: { ...type.bodySmall, color: color.muted } as any,
  v: { ...type.bodySmall, color: color.fg, flex: 1, textAlign: 'right' } as any,
  remove: { ...type.labelMedium, color: color.danger, marginTop: space.sm } as any,

  emptyTitle: { ...type.title, color: color.fg } as any,
  emptySub: { ...type.bodySmall, color: color.muted } as any,
  cta: { height: 48, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  ctaText: { ...type.button, color: color.onPrimary } as any,
});
