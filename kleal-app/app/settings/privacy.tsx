/**
 * Настройки → «Данные и приватность».
 *
 * Своим текстом и по делу. Прежде строка «Приватность и безопасность» вела на экран переключателей,
 * а собственно политики в продукте не было ни строчки — при том что приложение спрашивает возраст,
 * район, интересы и переписки.
 *
 * Здесь написано только то, что правда и что можно сверить с кодом: какие поля лежат в строке
 * человека, что видит второй, куда уходит текст разговора и что человек может со всем этим сделать.
 * Ни одного обещания, которого продукт не выполняет, — поэтому нет ни слова про шифрование
 * переписки, про удаление по запросу в поддержку и про «мы не передаём данные третьим лицам»:
 * первого нет, второго некому исполнить, третье требует договора, а не абзаца.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card } from '../../src/components/ProfileShell';
import { useLang } from '../../src/i18n';
import { PRIVACY } from '../../src/settings';
import { color, space, type } from '../../src/theme';

export default function Privacy() {
  useLang();
  const router = useRouter();

  return (
    <ProfileShell title={PRIVACY.title()} onBack={() => router.back()}>
      {PRIVACY.sections.map((sec, i) => (
        <Card key={i}>
          <Text style={s.h}>{sec.h()}</Text>
          <Text style={s.b}>{sec.b()}</Text>
        </Card>
      ))}
      <View style={{ paddingHorizontal: space.lg }}>
        <Text style={s.updated}>{PRIVACY.updated()}</Text>
      </View>
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  h: { ...type.title, color: color.fg } as any,
  b: { ...type.body, color: color.muted, marginTop: space.sm } as any,
  updated: { ...type.caption, color: color.neutral400, textAlign: 'center' } as any,
});
