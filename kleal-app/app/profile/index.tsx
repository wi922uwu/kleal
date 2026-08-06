/**
 * Профиль, главный экран — «Мой профиль Kleal».
 *
 * Хаб: кто ты (имя, фото, наполненность), что Kleal о тебе написал, и три раздела вглубь. Ровно та
 * же раскладка, что в вебе, потому что это одна и та же вещь для одного и того же человека.
 *
 * Наполненность считается, а не показывается красивым числом: шесть признаков, доля заполненных.
 * Полоса, которая всегда одна и та же, ничего не сообщает.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, Pressable, Image, TextInput, ActivityIndicator, Alert, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, Segments, EditSheet } from '../../src/components/ProfileShell';
import { BottomNav } from '../../src/components/BottomNav';
import {
  IconPerson, IconVerified, IconStar, IconFaceScan, IconUserLock, IconTranslate, IconPin, IconPencil, IconGear,
} from '../../src/components/icons';
import { useLang, T, getLang, setLang } from '../../src/i18n';
import { useOnb, set, reset } from '../../src/state';
import { profile as profileApi } from '../../src/api';
import {
  PROFILE_TITLE, HUB, AVAIL, SIGNOUT, HUB_ROWS, SHEETS, profileData, fmtUpdated, adaptSummary,
} from '../../src/profile';
import { langName, searchLangs } from '../../src/languages';
import { writeFact, patchFor } from '../../src/fields';
import { SETTINGS } from '../../src/settings';
import { AreaPicker, Area } from '../../src/components/AreaPicker';
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
  /** Какой лист правки открыт. Пусто — ни один. */
  const [sheet, setSheet] = useState<'languages' | 'location' | null>(null);

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

  /**
   * Пересобрать сводку. Одна и та же дверь и для кнопки «Пересобрать», и для правок профиля —
   * защиты от затирания живут внутри adaptSummary, и обходить их отдельным путём нельзя.
   */
  const rewrite = async () => {
    setBusy(true);
    try { await adaptSummary(); } finally { setBusy(false); }
  };

  /**
   * Сохранение из листов правки.
   *
   * Пишется и в состояние устройства, и в строку на сервере: профиль на сервере — это то, по чему
   * человека находят другие, и правка, оставшаяся только в телефоне, означала бы, что поиск видит
   * старое. Имена полей на сервере свои (`langs`, `area`, `radiusKm`) — они из его белого списка,
   * всё остальное он молча выбрасывает.
   */
  const saveLanguages = async (list: string[]) => {
    writeFact('languages', list);
    setSheet(null);
    // Имена и форма серверных полей — из реестра (src/fields.ts), не отсюда.
    if (p.name) await profileApi.update(p.name, patchFor(['languages'])).catch(() => {});
    rewrite();                    // сводка называет языки вслух — она обязана догнать
  };

  const saveLocation = async (a: Area) => {
    writeFact('location.area', a.label);
    writeFact('location.lat', a.lat);
    writeFact('location.lon', a.lon);
    writeFact('location.radiusKm', a.km);
    setSheet(null);
    if (p.name) {
      await profileApi.update(
        p.name,
        patchFor(['location.area', 'location.lat', 'location.lon', 'location.radiusKm'])
      ).catch(() => {});
    }
    rewrite();                    // «живёт в Барселоне» после переезда в Италию — неправда
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

  /**
   * Сводки нет — составить её самому, один раз.
   *
   * Так же устроен веб (ensureSummary): пустая карточка на главном экране профиля означала бы, что
   * Kleal ничего о человеке не понял, хотя профиль заполнен. Условие «есть что описывать» тоже
   * оттуда: пока в профиле меньше двух содержательных вещей, описывать нечего, и просить у модели
   * текст про пустоту — значит получить выдумку.
   */
  const autoTried = useRef(false);
  useEffect(() => {
    if (autoTried.current || busy || summary) return;
    if (d.interests.length + d.basics.length < 2) return;
    autoTried.current = true;
    rewrite();
  }, [summary, d.interests.length, d.basics.length, busy]);

  return (
    <ProfileShell
      title={PROFILE_TITLE()}
      onBack={() => router.back()}
      nav={<BottomNav active="profile" />}
      right={
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={SETTINGS.title()}
          style={s.gear}
          onPress={() => router.push('/settings')}
        >
          <IconGear />
        </Pressable>
      }
    >
      <Card>
        <View style={s.idRow}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Фото профиля', 'Profile photo')}>
            {p.photo ? (
              <Image source={{ uri: p.photo }} style={s.ava} />
            ) : (
              <View style={[s.ava, s.avaEmpty]}><IconPerson /></View>
            )}
          </Pressable>
          <Text style={s.name} numberOfLines={1}>{d.name}</Text>
          {/* Печать показывается только по-настоящему подтверждённым: нарисовать её всем значило
              бы сообщить о человеке то, чего никто не проверял. */}
          {d.verified ? <IconVerified /> : null}
        </View>
        <View style={s.confRow}>
          <Text style={s.confLabel}>{HUB.confidence()}</Text>
          <Text style={s.confPct}>{d.confidence}%</Text>
        </View>
        <View style={s.track}><View style={[s.trackFill, { width: `${d.confidence}%` }]} /></View>
      </Card>

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
            <Text style={s.sumText}>
              {summary || (busy ? HUB.writing() : HUB.empty())}
            </Text>
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

        {/*
          Ведёт в разговор создания интента, а не в мастер: мастер начинается с формата и времени,
          то есть с того, что ставится руками ПОСЛЕ того, как тема собрана. Открывать его первым —
          значит просить человека выбрать «онлайн или офлайн» раньше, чем он сказал, для чего.
        */}
        <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.push('/create')}>
          <Text style={s.ctaText}>{HUB.createIntent()}</Text>
        </Pressable>
      </Card>

      {/*
        Пять строк одним списком — так на кадре. Первые три ведут вглубь, две последние открывают
        лист правки поверх профиля. Выглядят одинаково, потому что для человека это одно и то же
        действие: «поправить вот это».
      */}
      {HUB_ROWS.map((row) => (
        <HubRowView
          key={row.id}
          title={row.title()}
          sub={row.sub(p)}
          Icon={ROW_ICON[row.id]}
          onPress={() => (row.kind === 'screen'
            ? router.push(`/profile/${row.id}` as any)
            : setSheet(row.id as 'languages' | 'location'))}
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
      <LanguagesSheet
        open={sheet === 'languages'}
        value={p.languages?.comfortable || []}
        onClose={() => setSheet(null)}
        onAccept={saveLanguages}
      />
      <LocationSheet
        open={sheet === 'location'}
        p={p}
        onClose={() => setSheet(null)}
        onAccept={saveLocation}
      />

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

  gear: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16,
    borderRadius: rad.xl, backgroundColor: color.card,
  },
  rowIcon: {
    width: 46, height: 46, borderRadius: 23, borderWidth: 1, borderColor: color.border,
    alignItems: 'center', justifyContent: 'center',
  },
  rowTitle: { fontSize: 18, fontWeight: '700', color: color.fg },
  rowSub: { ...type.bodySmall, color: color.muted, marginTop: 2 } as any,

  search: {
    height: 46, borderRadius: rad.full, backgroundColor: color.neutral100,
    paddingHorizontal: 18, color: color.fg, fontSize: 15,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    height: 44, paddingHorizontal: 16, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,

  cta: { height: 48, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  ctaText: { ...type.button, color: color.onPrimary } as any,

  signout: {
    height: 46, borderRadius: rad.full, borderWidth: 1, borderColor: color.border,
    alignItems: 'center', justifyContent: 'center', marginTop: space.sm,
  },
  signoutText: { ...type.button, color: color.danger } as any,
});

/** Строка хаба — круглая иконка, заголовок, подпись, карандаш. Один вид на все пять. */
function HubRowView({
  title, sub, Icon, onPress,
}: {
  title: string;
  sub: string;
  Icon: (p: any) => React.ReactElement;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [s.row, pressed && { opacity: 0.9 }]}
    >
      <View style={s.rowIcon}><Icon size={22} /></View>
      <View style={{ flex: 1 }}>
        <Text style={s.rowTitle} numberOfLines={1}>{title}</Text>
        <Text style={s.rowSub} numberOfLines={1}>{sub}</Text>
      </View>
      <IconPencil />
    </Pressable>
  );
}

const ROW_ICON: Record<string, (p: any) => React.ReactElement> = {
  interests: IconStar,
  personality: IconFaceScan,
  safety: IconUserLock,
  languages: IconTranslate,
  location: IconPin,
};

/**
 * Языки — полный список с поиском.
 *
 * Выбранные всегда сверху и видны сразу: иначе, набрав в поиске «швед», человек перестаёт видеть,
 * что у него уже отмечено, и снимает нужное вслепую. Правка идёт по черновику — крестик не
 * сохраняет.
 */
function LanguagesSheet({
  open, value, onClose, onAccept,
}: {
  open: boolean;
  value: string[];
  onClose: () => void;
  onAccept: (list: string[]) => void;
}) {
  const ru = getLang() === 'ru';
  const [sel, setSel] = useState<string[]>(value);
  const [q, setQ] = useState('');
  useEffect(() => { if (open) { setSel(value); setQ(''); } }, [open]);

  const toggle = (k: string) => setSel((x) => (x.includes(k) ? x.filter((y) => y !== k) : [...x, k]));
  const found = searchLangs(q).filter((l) => !sel.includes(l[0]));

  return (
    <EditSheet
      open={open}
      title={SHEETS.languages()}
      onClose={onClose}
      onAccept={() => onAccept(sel)}
      acceptLabel={SHEETS.accept()}
    >
      <TextInput
        style={s.search}
        value={q}
        onChangeText={setQ}
        placeholder={SHEETS.search()}
        placeholderTextColor={color.neutral400}
        autoCorrect={false}
        accessibilityLabel={SHEETS.search()}
      />

      {sel.length ? (
        <View style={s.chips}>
          {sel.map((k) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              accessibilityState={{ selected: true }}
              onPress={() => toggle(k)}
              style={[s.chip, s.chipOn]}
            >
              <Text style={[s.chipText, { color: color.onPrimary }]}>{langName(k, ru)}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {found.length ? (
        <View style={s.chips}>
          {found.map((l) => (
            <Pressable
              key={l[1]}
              accessibilityRole="button"
              accessibilityState={{ selected: false }}
              onPress={() => toggle(l[0])}
              style={s.chip}
            >
              <Text style={s.chipText}>{langName(l[0], ru)}</Text>
            </Pressable>
          ))}
        </View>
      ) : (
        <Text style={s.basicValue}>{SHEETS.nothing()}</Text>
      )}
    </EditSheet>
  );
}

/** Локация — страна, радиус и карта. Тот же AreaPicker, что в онбординге: это одна и та же вещь. */
function LocationSheet({
  open, p, onClose, onAccept,
}: {
  open: boolean;
  p: any;
  onClose: () => void;
  onAccept: (a: Area) => void;
}) {
  const current = (): Area => ({
    label: String(p.city || 'Spain'),
    lat: p.geo?.coarseLat ?? 41.3874,
    lon: p.geo?.coarseLon ?? 2.1686,
    km: p.geo?.maxDistanceKm ?? 15,
  });
  const [area, setArea] = useState<Area>(current);
  useEffect(() => { if (open) setArea(current()); }, [open]);
  return (
    <EditSheet
      open={open}
      title={SHEETS.location()}
      onClose={onClose}
      onAccept={() => onAccept(area)}
      acceptLabel={SHEETS.accept()}
    >
      <AreaPicker value={area} onChange={setArea} />
    </EditSheet>
  );
}
