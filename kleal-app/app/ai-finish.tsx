/**
 * «ОСТАЛОСЬ НЕМНОГО» — короткий путь после ChatGPT (18.10.2026).
 *
 * Иван после живой проверки: «ChatGPT уже заполнил мой профиль — зачем мне ещё раз проходить этот
 * онбординг». Поэтому после листа черновика (app/ai-fill.tsx) человек попадает не в шаги анкеты, а
 * сюда: один экран только с тем, чего в анкете нет, и оттуда — в обычный конец анкеты (/summary:
 * сводку пишет модель, регистрация, главная). Обычный путь «Поехали!» не меняется.
 *
 * Что спрашивается:
 *   • имя — подставлено из аккаунта (Google/Apple/почта), человек только проверяет;
 *   • возраст и пол — одним блоком;
 *   • фото — как в анкете; можно «позже», как и там;
 *   • город, языки, интересы — только если ChatGPT их не прислал;
 *   • настройки (радиус, публичные места, подбор по профилю, похожие люди) — НЕ вопросы: значения по
 *     умолчанию видны и меняются одним касанием, «Готово» принимает их как есть.
 *
 * Готовность — то же правило, что у обычной анкеты (onbComplete). Подтверждение возраста по
 * документу здесь не ставится и не подделывается: его спрашивает свой экран после анкеты.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Keyboard, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View, Image } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { useLang, T, replyLang } from '../src/i18n';
import { useOnb, set, applyDefaults, getState, profileForAttach } from '../src/state';
import { api } from '../src/api';
import { hOk, hTap } from '../src/haptics';
import { squarePhoto } from '../src/photo';
import { isName, SEXES, sexLabel, LANGS, langLabel, onbComplete } from '../src/onboarding';
import { AgeDial } from '../src/components/AgeDial';
import { clampAge } from '../src/age-ruler';
import { PLACES } from '../src/components/AreaPicker';
import { interestLabel } from '../src/interest-label';
import { GlassChip, GlassPill } from '../src/components/Glass';
import { GlassSurface } from '../src/components/LiquidGlass';
import { Ambient } from '../src/components/Ambient';
import { IconCamera, IconChevronLeft, IconUpload } from '../src/components/icons';
import { color, font, space } from '../src/theme';

const RADII = [5, 10, 25, 50];
/** Подпись интереса; ключ без подписи в реестре — словами («board_games» → «Board games»). */
const niceInterest = (k: string) => {
  const l = interestLabel(k);
  if (l && l !== k) return l;
  const t = String(k).replace(/_/g, ' ').trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

export default function AiFinish() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const st = useOnb();
  const p: any = st.profile || {};
  const params = useLocalSearchParams<{ name?: string }>();

  // Что спрашивать — решается один раз при открытии: иначе блок исчезал бы прямо под пальцем, пока
  // человек его заполняет.
  const need = useMemo(() => ({
    name: !isName(p.name),
    basics: !p.age || !p.gender,
    photo: (!p.photo && p.photoStatus !== 'skipped'),
    area: !p.city,
    langs: !(p.languages?.comfortable || []).length,
  }), []); // eslint-disable-line react-hooks/exhaustive-deps
  const interests: string[] = p.interests?.explicit || [];

  const [name, setName] = useState(String(p.name || params.name || '').trim());
  const [age, setAge] = useState(() => clampAge(p.age));
  const [sex, setSex] = useState<string | null>(p.gender || null);
  const [city, setCity] = useState<[string, number, number, string] | null>(null);
  const [langs, setLangs] = useState<string[]>([]);
  const [km, setKm] = useState<number>(Number(p.geo?.maxDistanceKm) || 10);
  const [publicOnly, setPublicOnly] = useState<boolean>(p.safety?.publicPlacesOnly !== false);
  const [useProfile, setUseProfile] = useState<boolean>(p.permissions?.useProfileForMatching !== false);
  const [adjacent, setAdjacent] = useState<boolean>(p.permissions?.allowAdjacentMatches !== false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [drag, setDrag] = useState(false);

  // Имя из аккаунта: сервер отдаёт его рядом с черновиком (account_name), экран листа передаёт сюда.
  useEffect(() => { if (!name && params.name) setName(String(params.name)); }, [params.name]); // eslint-disable-line react-hooks/exhaustive-deps

  const pickPhoto = async (camera: boolean) => {
    try {
      if (camera) { const pm = await ImagePicker.requestCameraPermissionsAsync(); if (!pm.granted) return; }
      const r = camera
        ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.8 })
        : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.8 });
      if (r.canceled || !r.assets?.[0]) return;
      const shot = await squarePhoto(r.assets[0]);
      set('photo', shot.dataUrl);
      set('photoStatus', 'set');
      hOk();
    } catch { /* пикер закрыт или нет доступа — оставляем как есть */ }
  };

  const okName = !need.name || isName(name);
  const okBasics = !need.basics || !!sex;
  const okArea = !need.area || !!city;
  const okLangs = !need.langs || langs.length > 0;
  const okInterests = interests.length > 0;
  const ready = okName && okBasics && okArea && okLangs && okInterests;

  const done = async () => {
    if (!ready || busy) return;
    Keyboard.dismiss();
    setBusy(true);
    setErr('');
    if (need.name) set('name', name.trim());
    if (need.basics) { set('age', age); if (sex && sex !== 'Any') set('gender', sex); }
    if (need.area && city) {
      set('city', city[0]); set('country', city[3]);
      set('geo.comfortableAreas', [city[0]]); set('geo.located', true);
      set('geo.coarseLat', city[1]); set('geo.coarseLon', city[2]);
    }
    if (need.langs) set('languages.comfortable', langs);
    // Настройки — те же поля и значения по умолчанию, что ставит обычная анкета (applyDefaults),
    // с поправками человека из блока ниже.
    applyDefaults();
    set('geo.maxDistanceKm', km);
    set('safety.publicPlacesOnly', publicOnly);
    set('permissions.useProfileForMatching', useProfile);
    set('permissions.allowAdjacentMatches', adjacent);
    if (!getState().profile.photo && getState().profile.photoStatus !== 'set') set('photoStatus', 'skipped');
    // Сверка с сервером — для журнала: критично то же правило, что у обычной анкеты.
    api.post('/api/onboarding/state', { profile: profileForAttach() }).catch(() => {});
    if (!onbComplete(getState().profile)) { setBusy(false); setErr(FIN.notReady()); return; }
    hOk();
    router.replace('/summary');
  };

  const country = String(p.country || PLACES[0].country);
  const cities = (PLACES.find((x) => x.country === country) || PLACES[0]);

  return (
    <View style={s.wrap}>
      <Ambient />
      <View style={[s.head, { paddingTop: insets.top + 6 }]}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} hitSlop={10}
                   onPress={() => router.back()} style={s.back}>
          <IconChevronLeft size={22} c={color.fg} />
        </Pressable>
        <Text style={s.headTitle} numberOfLines={1}>{FIN.title()}</Text>
        <View style={s.back} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView scrollEnabled={!drag} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}
                    contentContainerStyle={[s.body, { paddingBottom: insets.bottom + space.xl }]}>
          <Text style={s.lead}>{FIN.lead()}</Text>

          {need.name ? (
            <Block title={FIN.name()} note={params.name ? FIN.nameNote() : undefined}>
              <GlassSurface tone="light" radius={16} style={s.field}>
                <TextInput value={name} onChangeText={setName} placeholder={FIN.namePh()} placeholderTextColor={color.muted}
                           style={s.input} autoCapitalize="words" maxLength={40} />
              </GlassSurface>
            </Block>
          ) : null}

          {need.basics ? (
            <Block title={FIN.basics()}>
              <AgeDial value={age} onChange={setAge} locale={replyLang()} onDragChange={setDrag} />
              <View style={s.row}>
                {SEXES.map(([k]) => (
                  <GlassChip key={k} grow label={sexLabel(k)} on={sex === k} onPress={() => setSex(k)} />
                ))}
              </View>
            </Block>
          ) : null}

          {need.photo ? (
            <Block title={FIN.photo()} note={FIN.photoNote()}>
              <View style={s.photoRow}>
                {p.photo ? <Image source={{ uri: p.photo }} style={s.photo} /> : <View style={[s.photo, s.photoEmpty]} />}
                <View style={{ flex: 1, gap: 8 }}>
                  <GlassPill tone="light" small label={FIN.camera()} icon={<IconCamera size={16} c={color.fg} />} onPress={() => pickPhoto(true)} style={s.btn40} />
                  <GlassPill tone="light" small label={FIN.gallery()} icon={<IconUpload size={16} c={color.fg} />} onPress={() => pickPhoto(false)} style={s.btn40} />
                </View>
              </View>
            </Block>
          ) : null}

          {need.area ? (
            <Block title={FIN.area()}>
              <View style={s.wrapRow}>
                {cities.cities.slice(0, 12).map((c) => (
                  <GlassChip key={c[0]} label={c[0]} on={city?.[0] === c[0]} onPress={() => setCity([c[0], c[1], c[2], cities.country])} />
                ))}
              </View>
            </Block>
          ) : null}

          {need.langs ? (
            <Block title={FIN.langs()}>
              <View style={s.wrapRow}>
                {LANGS.map(([k]) => (
                  <GlassChip key={k} label={langLabel(k)} on={langs.includes(k)}
                             onPress={() => setLangs((x) => (x.includes(k) ? x.filter((y) => y !== k) : [...x, k]))} />
                ))}
              </View>
            </Block>
          ) : null}

          {!okInterests ? (
            <Block title={FIN.interests()} note={FIN.interestsNote()}>
              <GlassPill tone="light" small label={FIN.pickInterests()}
                         onPress={() => router.navigate({ pathname: '/chat', params: { step: 'hobbies', map: '1', back: '/ai-finish' } })}
                         style={s.btn40} />
            </Block>
          ) : (
            <Text style={s.got}>{FIN.gotInterests(interests.slice(0, 6).map(niceInterest).join(', '), interests.length)}</Text>
          )}

          <Block title={FIN.settings()} note={FIN.settingsNote()}>
            <Text style={s.setLabel}>{FIN.radius()}</Text>
            <View style={s.row}>
              {RADII.map((r) => <GlassChip key={r} grow label={`${r} km`} on={km === r} onPress={() => { hTap(); setKm(r); }} />)}
            </View>
            <SwitchRow label={FIN.publicOnly()} value={publicOnly} onChange={setPublicOnly} />
            <SwitchRow label={FIN.useProfile()} value={useProfile} onChange={setUseProfile} />
            <SwitchRow label={FIN.adjacent()} value={adjacent} onChange={setAdjacent} />
          </Block>

          {err ? <Text style={s.err}>{err}</Text> : null}
          <GlassPill tone="brand" label={FIN.done()} disabled={!ready} busy={busy} onPress={done} style={s.cta} />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function Block({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <View style={s.block}>
      <Text style={s.blockTitle}>{title}</Text>
      {note ? <Text style={s.note}>{note}</Text> : null}
      {children}
    </View>
  );
}

function SwitchRow({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={s.switchRow}>
      <Text style={s.switchLabel}>{label}</Text>
      <Switch value={value} onValueChange={(v) => { hTap(); onChange(v); }}
              trackColor={{ true: color.primary, false: 'rgba(24,27,34,0.15)' }} thumbColor="#FFFFFF" />
    </View>
  );
}

const FIN = {
  title: () => T('Осталось немного', 'Almost there', 'Ya casi está'),
  lead: () => T('ChatGPT заполнил главное. Здесь только то, чего не хватает, — и сразу в приложение.',
    'ChatGPT filled in the main part. Here’s only what’s missing — then straight into the app.',
    'ChatGPT ha rellenado lo principal. Aquí solo lo que falta, y directo a la app.'),
  name: () => T('Как тебя зовут', 'Your name', 'Tu nombre'),
  nameNote: () => T('Взяли из аккаунта — поправь, если надо.', 'Taken from your account — edit if needed.', 'Tomado de tu cuenta: cámbialo si hace falta.'),
  namePh: () => T('Имя', 'Name', 'Nombre'),
  basics: () => T('Возраст и пол', 'Age and gender', 'Edad y género'),
  photo: () => T('Фото', 'Photo', 'Foto'),
  photoNote: () => T('С фото тебя узнают на встрече. Можно и позже — из профиля.', 'A photo helps people recognise you. You can add it later from your profile.', 'Con foto te reconocen en el encuentro. También puedes añadirla luego desde el perfil.'),
  camera: () => T('Сделать фото', 'Take a photo', 'Hacer foto'),
  gallery: () => T('Из галереи', 'From gallery', 'De la galería'),
  area: () => T('Где ты', 'Where you are', 'Dónde estás'),
  langs: () => T('Языки', 'Languages', 'Idiomas'),
  interests: () => T('Интересы', 'Interests', 'Intereses'),
  interestsNote: () => T('ChatGPT не прислал интересов — выбери хотя бы три.', 'ChatGPT sent no interests — pick at least three.', 'ChatGPT no envió intereses: elige al menos tres.'),
  pickInterests: () => T('Выбрать интересы', 'Pick interests', 'Elegir intereses'),
  gotInterests: (list: string, n: number) => T(`Интересы: ${list}${n > 6 ? ` и ещё ${n - 6}` : ''}`, `Interests: ${list}${n > 6 ? ` and ${n - 6} more` : ''}`, `Intereses: ${list}${n > 6 ? ` y ${n - 6} más` : ''}`),
  settings: () => T('Настройки', 'Settings', 'Ajustes'),
  settingsNote: () => T('Уже выставлены как лучше по умолчанию — поменять можно и потом.', 'Already set to sensible defaults — you can change them later.', 'Ya están en los valores recomendados; puedes cambiarlos luego.'),
  radius: () => T('Искать в радиусе', 'Search radius', 'Radio de búsqueda'),
  publicOnly: () => T('Встречи в публичных местах', 'Meet in public places', 'Quedar en sitios públicos'),
  useProfile: () => T('Подбирать людей по моему профилю', 'Use my profile for matching', 'Usar mi perfil para emparejar'),
  adjacent: () => T('Показывать похожих людей', 'Show similar people too', 'Mostrar también gente parecida'),
  done: () => T('Готово', 'Done', 'Listo'),
  notReady: () => T('Чего-то ещё не хватает — проверь блоки выше.', 'Something’s still missing — check the blocks above.', 'Aún falta algo: revisa los bloques de arriba.'),
};

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: 8, gap: 8 },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.85)' },
  headTitle: { flex: 1, textAlign: 'center', fontFamily: font.displaySemi, fontSize: 17, lineHeight: 22, color: color.fg } as any,
  body: { paddingHorizontal: 16, paddingTop: 8, gap: space.lg },
  lead: { fontFamily: font.text, fontSize: 15, lineHeight: 21, color: '#5A616E' } as any,
  block: { gap: 10 },
  blockTitle: { fontFamily: font.displaySemi, fontSize: 18, lineHeight: 24, color: color.fg } as any,
  note: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#5A616E', marginTop: -4 } as any,
  field: { height: 52, paddingHorizontal: 16, justifyContent: 'center' },
  input: { fontFamily: font.text, fontSize: 16, color: color.fg } as any,
  row: { flexDirection: 'row', gap: 8 },
  wrapRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  photoRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  photo: { width: 88, height: 88, borderRadius: 44 },
  photoEmpty: { backgroundColor: 'rgba(255,255,255,0.7)', borderWidth: 1, borderColor: '#FFFFFF' },
  btn40: { height: 40 },
  got: { fontFamily: font.text, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  setLabel: { fontFamily: font.textMedium, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, paddingVertical: 4 },
  switchLabel: { flex: 1, fontFamily: font.text, fontSize: 15, lineHeight: 20, color: color.fg } as any,
  err: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.primary } as any,
  cta: { height: 52, marginTop: space.sm },
});
