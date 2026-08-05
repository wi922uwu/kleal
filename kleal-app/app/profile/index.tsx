/**
 * Профиль, главный экран — «Мой профиль Kleal».
 *
 * Хаб: кто ты (имя, фото, наполненность), что Kleal о тебе написал, и три раздела вглубь. Ровно та
 * же раскладка, что в вебе, потому что это одна и та же вещь для одного и того же человека.
 *
 * Наполненность считается, а не показывается красивым числом: шесть признаков, доля заполненных.
 * Полоса, которая всегда одна и та же, ничего не сообщает.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, Pressable, Image, TextInput, ActivityIndicator, Alert, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, NavRow, Segments } from '../../src/components/ProfileShell';
import { IconPerson } from '../../src/components/icons';
import { useLang, T, getLang, setLang } from '../../src/i18n';
import { useOnb, set, reset, profileForAttach } from '../../src/state';
import { profile as profileApi, buddy } from '../../src/api';
import { PROFILE_TITLE, SECTIONS, HUB, AVAIL, SIGNOUT, profileData, fmtUpdated } from '../../src/profile';
import { color, radius as rad, space, type } from '../../src/theme';

export default function ProfileHub() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const p = st.profile;
  const d = useMemo(() => profileData(p), [p, lang]);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [avail, setAvail] = useState<string | null>(null);
  const [availErr, setAvailErr] = useState(false);

  // Текущий статус приёма читается с сервера, а не хранится локально: его меняет не только этот
  // экран (пауза приходит и из безопасности, и со стороны агента), и локальная копия разошлась бы.
  useEffect(() => {
    if (!p.name) return;
    let alive = true;
    profileApi
      .receiving(p.name)
      .then((r: any) => { if (alive) setAvail(r?.status || r?.receiving?.status || null); })
      .catch(() => { if (alive) setAvailErr(true); });
    return () => { alive = false; };
  }, [p.name]);

  const setAvailability = async (v: string) => {
    const prev = avail;
    setAvail(v);                                    // отклик сразу, откат по ошибке
    try {
      const r: any = await profileApi.receiving(p.name || '', { status: v });
      if (r && r.ok === false) throw new Error(r.error || 'failed');
    } catch {
      setAvail(prev);
      setAvailErr(true);
    }
  };

  const saveSummary = async (text: string) => {
    set('summary', text);
    set('summaryUpdated', Date.now());
    setEditing(false);
    if (p.name) await profileApi.update(p.name, { summary: text }).catch(() => {});
  };

  /** Пересобрать сводку моделью. Пустой ответ НЕ затирает текст — старый остаётся на экране. */
  const rewrite = async () => {
    setBusy(true);
    try {
      const r: any = await buddy.resummary(
        profileForAttach(), String((p as any).summary || ''), String((p as any).personality || ''), getLang()
      );
      const next = String(r?.summary || '').trim();
      if (next) await saveSummary(next);
    } catch {
      /* молча: сводка на экране остаётся прежней, и это лучше пустой карточки */
    } finally {
      setBusy(false);
    }
  };

  const signOut = () => {
    const has = !!st.login;
    const go = () => { reset(); router.replace('/'); };
    if (Platform.OS === 'web') {
      // Alert.alert на вебе рисуется без кнопок — там это window.confirm.
      // eslint-disable-next-line no-alert
      if (typeof confirm === 'function' && confirm(SIGNOUT.ask(has))) go();
      return;
    }
    Alert.alert(SIGNOUT.ask(has), undefined, [
      { text: SIGNOUT.no(), style: 'cancel' },
      { text: SIGNOUT.yes(), style: 'destructive', onPress: go },
    ]);
  };

  const summary = String((p as any).summary || '');
  const updated = fmtUpdated((p as any).summaryUpdated);

  return (
    <ProfileShell title={PROFILE_TITLE()} onBack={() => router.back()}>
      <Card>
        <View style={s.idRow}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Фото профиля', 'Profile photo')}>
            {p.photo ? (
              <Image source={{ uri: p.photo }} style={s.ava} />
            ) : (
              <View style={[s.ava, s.avaEmpty]}><IconPerson /></View>
            )}
          </Pressable>
          <Text style={s.name}>{d.name}</Text>
        </View>
        <View style={s.confRow}>
          <Text style={s.confLabel}>{HUB.confidence()}</Text>
          <Text style={s.confPct}>{d.confidence}%</Text>
        </View>
        <View style={s.track}><View style={[s.trackFill, { width: `${d.confidence}%` }]} /></View>
      </Card>

      {d.basics.map((r) => (
        <Card key={r.title} style={s.basicRow}>
          <View style={{ flex: 1 }}>
            <Text style={s.basicTitle}>{r.title}</Text>
            <Text style={s.basicValue}>{r.value}</Text>
          </View>
        </Card>
      ))}

      <Card>
        <View style={s.sumHead}>
          <Text style={s.sumLabel}>{HUB.summaryLabel()}</Text>
          {updated ? <Text style={s.updated}>{updated}</Text> : null}
        </View>

        {editing ? (
          <>
            <TextInput
              style={s.sumInput}
              value={draft}
              onChangeText={setDraft}
              multiline
              textAlignVertical="top"
              accessibilityLabel={HUB.summaryLabel()}
            />
            <View style={s.linkRow}>
              <Pressable accessibilityRole="button" onPress={() => saveSummary(draft.trim())}>
                <Text style={s.link}>{HUB.save()}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" onPress={() => setEditing(false)}>
                <Text style={s.linkMuted}>{HUB.cancel()}</Text>
              </Pressable>
            </View>
          </>
        ) : (
          <>
            <Text style={s.sumText}>{summary || HUB.empty()}</Text>
            <View style={s.linkRow}>
              <Pressable accessibilityRole="button" onPress={() => { setDraft(summary); setEditing(true); }}>
                <Text style={s.link}>{HUB.edit()}</Text>
              </Pressable>
              <Pressable accessibilityRole="button" accessibilityState={{ busy }} onPress={busy ? undefined : rewrite}>
                {busy ? <ActivityIndicator size="small" color={color.primary} /> : <Text style={s.link}>{HUB.rewrite()}</Text>}
              </Pressable>
            </View>
          </>
        )}

        <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.push('/intent')}>
          <Text style={s.ctaText}>{HUB.createIntent()}</Text>
        </Pressable>
      </Card>

      {SECTIONS.map((sec) => (
        <NavRow
          key={sec.id}
          title={sec.title()}
          sub={sec.sub()}
          onPress={() => router.push(`/profile/${sec.id}` as any)}
        />
      ))}

      <Card>
        <Text style={s.basicTitle}>{HUB.avail()}</Text>
        {availErr ? (
          <Text style={s.basicValue}>
            {T('Доступно после регистрации профиля', 'Available once your profile is registered')}
          </Text>
        ) : (
          <Segments
            options={AVAIL.map(([k, l]) => [k, l()] as [string, string])}
            value={avail}
            onChange={setAvailability}
          />
        )}
      </Card>

      <Card>
        <Text style={s.basicTitle}>{HUB.lang()}</Text>
        <Segments
          options={[['ru', 'RU'], ['en', 'EN']]}
          value={lang}
          onChange={(v) => setLang(v as any)}
        />
      </Card>

      {/*
        Выход стирает состояние на устройстве целиком — и профиль тоже. Оставить его лежать значило
        бы показать его следующему, кто возьмёт этот телефон. Карточка показывается всегда: см.
        SIGNOUT — привязка к логину прятала кнопку от тех, у кого логина нет.
      */}
      <Card>
        <Text style={s.basicTitle}>{SIGNOUT.who(st.login)}</Text>
        <Pressable accessibilityRole="button" style={s.signout} onPress={signOut}>
          <Text style={s.signoutText}>{SIGNOUT.label(!!st.login)}</Text>
        </Pressable>
      </Card>
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  idRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  ava: { width: 60, height: 60, borderRadius: rad.full },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  name: { fontSize: 20, fontWeight: '700', color: color.fg, flex: 1 },
  confRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: space.sm },
  confLabel: { ...type.bodySmall, color: color.muted } as any,
  confPct: { ...type.bodySmall, color: color.muted } as any,
  track: { height: 4, backgroundColor: color.neutral100, borderRadius: 2 },
  trackFill: { height: 4, backgroundColor: color.primary, borderRadius: 2 },

  basicRow: { flexDirection: 'row', alignItems: 'center' },
  basicTitle: { ...type.labelMedium, color: color.muted } as any,
  basicValue: { ...type.body, color: color.fg, marginTop: 2 } as any,

  sumHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  sumLabel: { fontSize: 17, fontWeight: '700', color: color.fg },
  updated: { ...type.caption, color: color.muted } as any,
  sumText: { ...type.body, color: color.fg } as any,
  sumInput: {
    minHeight: 120, borderRadius: rad.md, backgroundColor: color.neutral100,
    padding: 12, color: color.fg, fontSize: 15, lineHeight: 22,
  },
  linkRow: { flexDirection: 'row', gap: space.lg, marginTop: 2 },
  link: { ...type.labelMedium, color: color.primary } as any,
  linkMuted: { ...type.labelMedium, color: color.muted } as any,

  cta: { height: 48, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  ctaText: { ...type.button, color: color.onPrimary } as any,

  signout: {
    height: 46, borderRadius: rad.full, borderWidth: 1, borderColor: color.border,
    alignItems: 'center', justifyContent: 'center', marginTop: space.sm,
  },
  signoutText: { ...type.button, color: color.danger } as any,
});
