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
import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, Pressable, Switch, Alert, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card } from '../../src/components/ProfileShell';
import { useLang, T } from '../../src/i18n';
import { useOnb, set, get, profileForAttach } from '../../src/state';
import { profile as profileApi } from '../../src/api';
import { profileData, INTERESTS_SCREEN as C, SECTIONS } from '../../src/profile';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Interests() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const d = useMemo(() => profileData(st.profile), [st.profile, lang]);
  const [open, setOpen] = useState<string | null>(d.interests[0]?.name || null);

  const push = () => {
    const name = st.profile.name;
    if (name) profileApi.update(name, { interests: profileForAttach().interests }).catch(() => {});
  };

  const toggleUsed = (nm: string, on: boolean) => {
    const unused: string[] = get('interests.unused') || [];
    set('interests.unused', on ? unused.filter((x) => x !== nm) : [...unused, nm]);
    push();
  };

  const remove = (nm: string, label: string) => {
    const wipe = () => {
      set('interests.explicit', (get('interests.explicit') || []).filter((x: string) => x !== nm));
      set('interests.unused', (get('interests.unused') || []).filter((x: string) => x !== nm));
      if (open === nm) setOpen(null);
      push();
    };
    const ask = T(`Убрать «${label}» из профиля?`, `Remove “${label}” from your profile?`);
    if (Platform.OS === 'web') {
      // Alert.alert на вебе рисуется без кнопок — там это window.confirm.
      // eslint-disable-next-line no-alert
      if (typeof confirm === 'function' && confirm(ask)) wipe();
      return;
    }
    Alert.alert(ask, undefined, [
      { text: T('Отмена', 'Cancel'), style: 'cancel' },
      { text: C.remove(), style: 'destructive', onPress: wipe },
    ]);
  };

  return (
    <ProfileShell title={SECTIONS[0].title()} onBack={() => router.back()}>
      {d.interests.length === 0 ? (
        <Card>
          <Text style={s.emptyTitle}>{C.emptyTitle()}</Text>
          <Text style={s.emptySub}>{C.emptySub()}</Text>
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.push('/chat')}>
            <Text style={s.ctaText}>{C.add()}</Text>
          </Pressable>
        </Card>
      ) : (
        <>
          <Text style={s.hint}>{C.hint()}</Text>

          {d.interests.map((it) => {
            const expanded = open === it.name;
            return (
              <Card key={it.name} style={{ gap: 0 }}>
                <View style={s.row}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ expanded }}
                    style={{ flex: 1 }}
                    onPress={() => setOpen(expanded ? null : it.name)}
                  >
                    <Text style={s.name}>{it.label}</Text>
                    <Text style={s.conf}>
                      {T('уверенность: ', 'confidence: ')}{C.confLabel(it.conf)}
                    </Text>
                  </Pressable>
                  <Switch
                    value={it.used}
                    onValueChange={(v) => toggleUsed(it.name, v)}
                    accessibilityLabel={T(`Учитывать «${it.label}» при подборе`, `Use “${it.label}” for matching`)}
                    trackColor={{ false: color.neutral300, true: color.primary }}
                    thumbColor={color.card}
                    ios_backgroundColor={color.neutral300}
                  />
                </View>

                {expanded ? (
                  <View style={s.exp}>
                    {it.kv.length ? (
                      it.kv.map(([k, v]) => (
                        <View key={k} style={s.kv}>
                          <Text style={s.k}>{k}</Text>
                          <Text style={s.v}>{v}</Text>
                        </View>
                      ))
                    ) : (
                      <Text style={s.emptySub}>{C.summary(it.label)}</Text>
                    )}
                    <Pressable accessibilityRole="button" onPress={() => remove(it.name, it.label)}>
                      <Text style={s.remove}>{C.remove()}</Text>
                    </Pressable>
                  </View>
                ) : null}
              </Card>
            );
          })}

          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.push('/chat')}>
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
