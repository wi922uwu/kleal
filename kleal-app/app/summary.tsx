/**
 * Сводка профиля — кадр A.14.
 *
 * Шапка меняет заголовок на «What Kleal knows about you» и показывает 100 %: онбординг закончен,
 * дальше речь уже не о заполнении, а о том, что из этого понято.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Image } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, profileForRegister, profileForAttach } from '../src/state';
import { onboarding } from '../src/api';
import { SUMMARY, SUMMARY_TITLE, hobbyPlain, langPlain } from '../src/onboarding';
import { Composer } from '../src/components/Composer';
import { IconPerson } from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';

export default function Summary() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const p = st.profile;

  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState('');

  /**
   * «Profile confidence» на борде — 74 %, без объяснения, откуда. Считаю по тому, что реально
   * заполнено, а не показываю красивое число: полоса, которая всегда 74 %, ничего не сообщает.
   */
  const confidence = useMemo(() => {
    const have = [
      !!p.name, !!p.age, !!p.gender, !!p.city,
      !!(p.languages?.comfortable || []).length,
      !!(p.interests?.explicit || []).length,
      !!p.photo,
    ];
    return Math.round((have.filter(Boolean).length / have.length) * 100);
  }, [p]);

  useEffect(() => {
    let alive = true;
    onboarding
      .summary(profileForAttach())
      .then((r: any) => alive && setText(String(r?.summary || '')))
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  // Если модель молчит или упала — собираем фразу из того, что известно. Пустая карточка на
  // последнем шаге онбординга хуже, чем неидеальная формулировка.
  // Русский собирается ТОЛЬКО через двоеточия: названия языков и городов приходят готовыми
  // строками, склонять их нечем, и «говорит на Английский» — сломанный русский. Английский
  // при этом строится нормальной фразой, ему падежи не нужны.
  const fallback = useMemo(() => {
    const h = (p.interests?.explicit || []).map(hobbyPlain);
    const l = (p.languages?.comfortable || []).map(langPlain);
    const bits = [
      h.length ? T('Интересы: ' + h.join(', '), 'Into ' + h.join(', ')) : '',
      l.length ? T('Языки: ' + l.join(', '), 'speaks ' + l.join(', ')) : '',
      p.city ? T('Обычно бывает: ' + p.city, 'usually around ' + p.city) : '',
    ].filter(Boolean);
    return bits.join('. ') + (bits.length ? '.' : '');
  }, [p]);

  const finish = async () => {
    setSending(true);
    setErr('');
    try {
      const r: any = await onboarding.register(profileForRegister());
      if (!r?.ok) throw new Error(r?.error || 'register failed');
      if (st.login) await onboarding.attach(st.login, p.name || '', profileForAttach()).catch(() => {});
      router.replace('/done');
    } catch {
      setErr(T('Профиль не сохранился. Проверь связь и попробуй ещё раз.',
               'Your profile didn’t save. Check your connection and try again.'));
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <View style={s.avatar} />
        <Text style={s.headTitle}>{SUMMARY_TITLE()}</Text>
        <Text style={s.headPct}>100%</Text>
      </View>
      <View style={s.track}><View style={[s.trackFill, { width: '100%' }]} /></View>

      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.card}>
          <View style={s.idRow}>
            {p.photo ? (
              <Image source={{ uri: p.photo }} style={s.idAvatar} />
            ) : (
              <View style={[s.idAvatar, s.idAvatarEmpty]}>
                <IconPerson />
              </View>
            )}
            <View style={{ flex: 1 }}>
              <View style={s.nameRow}>
                <Text style={s.name}>{p.name || '—'}</Text>
                <Text style={s.verified}>✓</Text>
              </View>
              <View style={s.confRow}>
                <Text style={s.confLabel}>{SUMMARY.confidence()}</Text>
                <Text style={s.confPct}>{confidence}%</Text>
              </View>
              <View style={s.confTrack}>
                <View style={[s.confFill, { width: `${confidence}%` }]} />
              </View>
            </View>
          </View>
        </View>

        <View style={s.card}>
          <View style={s.cardHead}>
            <Text style={s.cardTitle}>{SUMMARY.klealSummary()}</Text>
            <Text style={s.cardMeta}>{SUMMARY.updatedToday()}</Text>
          </View>
          <Text style={s.para}>{text || fallback}</Text>
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.push('/done')}>
            <Text style={s.ctaText}>{SUMMARY.viewAll()}</Text>
          </Pressable>
        </View>

        <View style={s.info}>
          <Text style={s.infoTitle}>✦  {SUMMARY.planTitle()}</Text>
          <Text style={s.infoBody}>{SUMMARY.planBody()}</Text>
        </View>

        {err ? <Text style={s.err}>{err}</Text> : null}
      </ScrollView>

      <View style={s.foot}>
        <Pressable accessibilityRole="button"
          style={[s.cta, sending && { opacity: 0.6 }]}
          onPress={sending ? undefined : finish}
          accessibilityState={{ busy: sending }}
        >
          <Text style={s.ctaText}>{SUMMARY.done()}</Text>
        </Pressable>
      </View>
      {/* Композер здесь есть на кадре A.14: разговор не заканчивается на последнем шаге анкеты. */}
      <Composer onBack={() => router.back()} bottomInset={insets.bottom} />
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingBottom: 10 },
  avatar: { width: 34, height: 34, borderRadius: 17, backgroundColor: color.primary },
  headTitle: { flex: 1, ...type.title, color: color.fg, fontWeight: '700' } as any,
  headPct: { ...type.labelMedium, color: color.muted } as any,
  track: { height: 3, backgroundColor: color.neutral100, marginHorizontal: 20, borderRadius: 2 },
  trackFill: { height: 3, backgroundColor: color.primary, borderRadius: 2 },

  // Запас снизу, чтобы последний блок не уезжал под кнопку «Готово» и композер.
  scroll: { padding: 20, paddingBottom: 130, gap: space.md },
  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.md },
  idRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  idAvatar: { width: 52, height: 52, borderRadius: rad.full },
  idAvatarEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  idLetter: { ...type.title, color: color.muted } as any,
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  name: { fontSize: 20, fontWeight: '700', color: color.fg },
  verified: { color: color.primary, fontWeight: '700' },
  confRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 },
  confLabel: { ...type.bodySmall, color: color.muted } as any,
  confPct: { ...type.bodySmall, color: color.muted } as any,
  confTrack: { height: 4, backgroundColor: color.neutral100, borderRadius: 2, marginTop: 5 },
  confFill: { height: 4, backgroundColor: color.primary, borderRadius: 2 },

  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  cardTitle: { fontSize: 18, fontWeight: '700', color: color.fg },
  cardMeta: { ...type.caption, color: color.muted } as any,
  para: { ...type.body, color: color.fg } as any,

  info: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.lg, gap: 6 },
  infoTitle: { ...type.title, color: color.infoText } as any,
  infoBody: { ...type.bodySmall, color: color.infoText } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  foot: { paddingHorizontal: 20, paddingTop: space.md },
});
