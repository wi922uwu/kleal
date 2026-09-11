/**
 * Профиль → «Безопасность и приватность».
 *
 * ЧТО ЗДЕСЬ БЫЛО. Пятнадцать переключателей в пяти группах: «не встречаться поздно вечером»,
 * «избегать баров», «делиться планом с доверенным контактом», «никогда не делать выводов о
 * чувствительном», «не сводить меня с теми, кого я могу знать» и так далее. Сверка с боевым кодом
 * показала, что девять из них не читает НИКТО и НИГДЕ, ещё три пишет онбординг, но подбор их не
 * смотрит. Даже «поставить Kleal на паузу» уходила в поле `safety.paused`, которого не читает ни
 * одна служба, — а подбор смотрит на `receiving.status`. Человек двигал ползунок, и не менялось
 * ничего.
 *
 * Обещание безопасности, которое ничего не делает, хуже отсутствия обещания: на него полагаются.
 *
 * ЧТО ВМЕСТО. Осталось ровно то, что исполняется: список заблокированных (жёсткий фильтр подбора,
 * в обе стороны) и два экрана настроек над политикой приёма, которую подбор читает по-настоящему.
 * Экран стал коротким — потому что правды оказалось ровно на столько.
 */
import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card } from '../../src/components/ProfileShell';
import { useLang, T } from '../../src/i18n';
import { SECTIONS } from '../../src/profile';
import { BLOCKED, VISIBILITY, AVAILABILITY } from '../../src/settings';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Safety() {
  useLang();
  const router = useRouter();

  const rows: { title: string; sub: string; to: string }[] = [
    { title: BLOCKED.title(), sub: BLOCKED.lead(), to: '/settings/blocked' },
    { title: VISIBILITY.title(), sub: VISIBILITY.statusLead(), to: '/settings/visibility' },
    { title: AVAILABILITY.title(), sub: AVAILABILITY.domainsLead(), to: '/settings/availability' },
  ];

  return (
    <ProfileShell title={SECTIONS[2].title()} onBack={() => router.back()}>
      <Card>
        <Text style={s.leadTitle}>{T('Всё под твоим контролем', 'You’re in control', 'Tú mandas')}</Text>
        <Text style={s.leadBody}>
          {T(
            'Kleal показывает район города, а не точное место. Уйти из поиска можно одним тапом, и это подействует сразу: на паузе тебя не находит никто.',
            'Kleal shares your city area, never your exact spot. You can leave search with one tap, and it takes effect at once: while paused, nobody can find you.',
          )}
        </Text>
      </Card>

      {rows.map((r) => (
        <Pressable
          key={r.to}
          accessibilityRole="button"
          onPress={() => router.navigate(r.to as any)}
          style={({ pressed }) => [s.row, pressed && { opacity: 0.9 }]}
        >
          <View style={{ flex: 1 }}>
            <Text style={s.rowTitle}>{r.title}</Text>
            <Text style={s.rowSub}>{r.sub}</Text>
          </View>
          <Text style={s.chev}>›</Text>
        </Pressable>
      ))}
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  leadTitle: { ...type.title, color: color.fg } as any,
  leadBody: { ...type.body, color: color.muted, marginTop: space.sm } as any,
  row: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg,
  },
  rowTitle: { ...type.body, color: color.fg } as any,
  rowSub: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  chev: { fontSize: 22, color: color.neutral400 },
});
