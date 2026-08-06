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
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import { BottomNav } from '../../src/components/BottomNav';
import {
  IconPerson, IconVerified, IconStar, IconFaceScan, IconUserLock, IconTranslate, IconPin, IconPencil, IconGear,
} from '../../src/components/icons';
import { useLang, getLang, setLang } from '../../src/i18n';
import { useOnb, set, reset } from '../../src/state';
import { profile as profileApi } from '../../src/api';
import {
  PROFILE_TITLE, HUB, SIGNOUT, HUB_ROWS, SHEETS, WHOAMI, profileData, fmtUpdated, adaptSummary,
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
  /** Какой лист правки открыт. Пусто — ни один. */
  const [sheet, setSheet] = useState<'languages' | 'location' | 'whoami' | null>(null);

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
  /**
   * Сохранить «кто ты». Возраст сервер принимает патчем; имя и фото — нет: строка пользователя
   * ключуется именем, а фото едет отдельным путём при регистрации. См. WHOAMI в src/profile.ts —
   * там записано, почему переименование не создаёт вторую строку молча.
   */
  const saveWhoAmI = async (v: { name: string; age: number; photo?: string }) => {
    if (v.name.trim()) set('name', v.name.trim());
    if (v.age) set('age', v.age);
    set('photo', v.photo || '');
    setSheet(null);
    if (p.name && v.age) await profileApi.update(p.name, { age: v.age }).catch(() => {});
    rewrite();                     // сводка называет возраст вслух
  };

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
      {/* Верхняя карточка — кнопка: за ней имя, возраст и фото (кадр B.01 их не редактирует, но
          менять их больше негде — «Основного» в списке ниже нет). */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={WHOAMI.title()}
        onPress={() => setSheet('whoami')}
        style={({ pressed }) => [pressed && { opacity: 0.92 }]}
      >
      <Card>
        <View style={s.idRow}>
          <View>
            {p.photo ? (
              <Image source={{ uri: p.photo }} style={s.ava} />
            ) : (
              <View style={[s.ava, s.avaEmpty]}><IconPerson /></View>
            )}
          </View>
          <Text style={s.name} numberOfLines={1}>{d.name}{p.age ? `, ${p.age}` : ''}</Text>
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
      </Pressable>

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
      <WhoAmISheet
        open={sheet === 'whoami'}
        p={p}
        onClose={() => setSheet(null)}
        onAccept={saveWhoAmI}
      />
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

  whoPhotoRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  whoPhoto: { width: 84, height: 84, borderRadius: 42 },
  whoPhotoBtn: {
    height: 42, borderRadius: rad.full, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16,
  },
  whoPhotoBtnText: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  whoRemove: { ...type.caption, color: color.primary, textAlign: 'center' } as any,
  whoInput: {
    height: 48, borderRadius: rad.md, backgroundColor: color.neutral100,
    paddingHorizontal: 14, color: color.fg, fontSize: 16,
  },
  whoNote: { ...type.caption, color: color.muted } as any,
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
 * Кто ты: имя, возраст, фото. Правка идёт по черновику — крестик не сохраняет.
 *
 * Фото берётся из галереи и сжимается перед сохранением: в состоянии оно лежит data-URL'ом, и
 * несжатый снимок с телефона — это мегабайты в AsyncStorage на каждой записи профиля.
 */
function WhoAmISheet({
  open, p, onClose, onAccept,
}: {
  open: boolean;
  p: any;
  onClose: () => void;
  onAccept: (v: { name: string; age: number; photo?: string }) => void;
}) {
  const [name, setName] = useState(String(p.name || ''));
  const [age, setAge] = useState(String(p.age || ''));
  const [photo, setPhoto] = useState<string>(String(p.photo || ''));

  useEffect(() => {
    if (!open) return;
    setName(String(p.name || ''));
    setAge(String(p.age || ''));
    setPhoto(String(p.photo || ''));
  }, [open]);

  const pick = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'], allowsEditing: true, aspect: [1, 1], quality: 0.9,
    });
    if (res.canceled || !res.assets?.length) return;
    const out = await ImageManipulator.manipulate(res.assets[0].uri)
      .resize({ width: 512 })
      .renderAsync();
    const saved = await out.saveAsync({ compress: 0.7, format: ImageManipulator.SaveFormat.JPEG, base64: true });
    setPhoto(saved.base64 ? `data:image/jpeg;base64,${saved.base64}` : saved.uri);
  };

  return (
    <EditSheet
      open={open}
      title={WHOAMI.title()}
      onClose={onClose}
      onAccept={() => onAccept({ name, age: parseInt(age, 10) || 0, photo })}
      acceptLabel={SHEETS.accept()}
    >
      <View style={s.whoPhotoRow}>
        {photo ? (
          <Image source={{ uri: photo }} style={s.whoPhoto} />
        ) : (
          <View style={[s.whoPhoto, s.avaEmpty]}><IconPerson size={30} /></View>
        )}
        <View style={{ flex: 1, gap: space.sm }}>
          <Pressable accessibilityRole="button" style={s.whoPhotoBtn} onPress={pick}>
            <Text style={s.whoPhotoBtnText}>{WHOAMI.changePhoto()}</Text>
          </Pressable>
          {photo ? (
            <Pressable accessibilityRole="button" onPress={() => setPhoto('')}>
              <Text style={s.whoRemove}>{WHOAMI.removePhoto()}</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      <Text style={s.basicTitle}>{WHOAMI.name()}</Text>
      <TextInput
        style={s.whoInput}
        value={name}
        onChangeText={setName}
        placeholder={WHOAMI.name()}
        placeholderTextColor={color.neutral400}
        accessibilityLabel={WHOAMI.name()}
      />
      <Text style={s.whoNote}>{WHOAMI.nameNote()}</Text>

      <Text style={s.basicTitle}>{WHOAMI.age()}</Text>
      <TextInput
        style={s.whoInput}
        value={age}
        onChangeText={(t) => setAge(t.replace(/[^0-9]/g, '').slice(0, 3))}
        keyboardType="number-pad"
        placeholder="30"
        placeholderTextColor={color.neutral400}
        accessibilityLabel={WHOAMI.age()}
      />
    </EditSheet>
  );
}

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
