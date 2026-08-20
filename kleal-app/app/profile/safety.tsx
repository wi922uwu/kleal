/**
 * Профиль → «Безопасность и приватность».
 *
 * Шесть групп переключателей, и у каждой группы своя подпись про то, что означает «включено». Это
 * не многословие: в одной группе включённое = безопаснее, в другой = шире охват, и по виду тумблера
 * их не отличить. Человек должен понимать, в какую сторону он двигает ползунок.
 *
 * Записывается всё через SAFETY_PATH, потому что экранные флаги и поля профиля не один в один:
 * «учиться на моих оценках» и «делать выводы обо мне» оба живут в permissions.rememberPreferences,
 * а «подбирать по интересам и району» — в useProfileForMatching. Без этой таблицы переключатель
 * менял бы своё, а профиль — своё.
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, ToggleRow, Segments, Divider } from '../../src/components/ProfileShell';
import { useLang } from '../../src/i18n';
import { useOnb, set, profileForAttach } from '../../src/state';
import { profile as profileApi } from '../../src/api';
import { profileData, SAFETY_GROUPS, SAFETY_LEAD, SAFETY_PATH, SECTIONS } from '../../src/profile';
import { BLOCKED } from '../../src/settings';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Safety() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const flags = useMemo(() => profileData(st.profile).safety, [st.profile, lang]);

  /** safety уезжает на сервер целиком: это одно из полей белого списка profile-update. */
  const push = () => {
    const name = st.profile.name;
    if (name) profileApi.update(name, { safety: (profileForAttach() as any).safety || {} }).catch(() => {});
  };

  const setFlag = (flag: string, v: boolean) => {
    const path = SAFETY_PATH[flag];
    if (!path) return;
    set(path, v);
    push();
  };

  return (
    <ProfileShell title={SECTIONS[2].title()} onBack={() => router.back()}>
      <Card>
        <Text style={s.leadTitle}>{SAFETY_LEAD.title()}</Text>
        <Text style={s.leadBody}>{SAFETY_LEAD.body()}</Text>
      </Card>

      {/* Кадр B.11: заблокированные — первая строка экрана, до всех переключателей. */}
      <Pressable
        accessibilityRole="button"
        onPress={() => router.navigate('/settings/blocked')}
        style={({ pressed }: { pressed: boolean }) => [s.blocked, pressed && { opacity: 0.9 }]}
      >
        <View style={{ flex: 1 }}>
          <Text style={s.blockedTitle}>{BLOCKED.title()}</Text>
          <Text style={s.blockedSub}>{BLOCKED.lead()}</Text>
        </View>
        <Text style={s.blockedChev}>›</Text>
      </Pressable>

      {SAFETY_GROUPS.map((g, gi) => (
        <View key={gi} style={{ gap: space.sm }}>
          <Text style={s.groupTitle}>{g.t()}</Text>
          <Text style={s.groupCap}>{g.c()}</Text>
          <Card style={{ gap: 0 }}>
            {g.items.map((it, ii) => {
              const prev = g.items[ii - 1];
              const rule = ii > 0 && it.k !== 'sub' && prev.k !== 'sub';
              if (it.k === 'sub') {
                return <Text key={ii} style={s.sub}>{it.label()}</Text>;
              }
              if (it.k === 'choice') {
                return (
                  <View key={ii}>
                    {rule ? <Divider /> : null}
                    <View style={s.choice}>
                      <Text style={s.rowLabel}>{it.label()}</Text>
                      <Text style={s.rowDesc}>{it.desc()}</Text>
                      <Segments
                        options={it.options.map((o, n) => [n === 1 ? 'auto' : 'ask', o()] as [string, string])}
                        value={flags.autonomy}
                        onChange={(v) => { set('safety.autonomy', v); push(); }}
                      />
                    </View>
                  </View>
                );
              }
              return (
                <View key={ii}>
                  {rule ? <Divider /> : null}
                  <ToggleRow
                    label={it.label()}
                    desc={it.desc()}
                    value={!!(flags as any)[it.flag]}
                    onChange={(v) => setFlag(it.flag, v)}
                  />
                </View>
              );
            })}
          </Card>
        </View>
      ))}
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  blocked: {
    flexDirection: 'row', alignItems: 'center', gap: space.md, padding: space.lg,
    borderRadius: rad.xl, backgroundColor: color.card,
  },
  blockedTitle: { ...type.title, color: color.fg } as any,
  blockedSub: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  blockedChev: { fontSize: 22, color: color.neutral400 },
  leadTitle: { ...type.title, color: color.primary } as any,
  leadBody: { ...type.bodySmall, color: color.muted } as any,
  groupTitle: { ...type.title, color: color.fg, marginTop: space.sm, paddingHorizontal: 4 } as any,
  groupCap: { ...type.bodySmall, color: color.muted, paddingHorizontal: 4 } as any,
  sub: { ...type.labelMedium, color: color.muted, paddingTop: space.md, paddingBottom: 2 } as any,
  choice: { paddingVertical: 10, gap: space.sm },
  rowLabel: { ...type.body, color: color.fg, fontWeight: '500' } as any,
  rowDesc: { ...type.bodySmall, color: color.muted, marginTop: 2 } as any,
});
