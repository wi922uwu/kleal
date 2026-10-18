/**
 * Профиль, главный экран — «Мой профиль Kleal».
 *
 * Хаб: кто ты (имя, фото, наполненность), что Kleal о тебе написал, и три раздела вглубь. Ровно та
 * же раскладка, что в вебе, потому что это одна и та же вещь для одного и того же человека.
 *
 * Наполненность считается, а не показывается красивым числом: шесть признаков, доля заполненных.
 * Полоса, которая всегда одна и та же, ничего не сообщает.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, Image, TextInput, ActivityIndicator, useWindowDimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, EditSheet, LinkRow, OptionRow, KlealPill, SectionHead } from '../../src/components/ProfileShell';
import * as ImagePicker from 'expo-image-picker';
import { squarePhoto } from '../../src/photo';
import { BottomNav } from '../../src/components/BottomNav';
import {
  IconPerson, IconVerified, IconStar, IconFaceScan, IconUserLock, IconTranslate, IconPin, IconGear, IconUsers,
} from '../../src/components/icons';
import { useLang, getLang } from '../../src/i18n';
import { useOnb, set } from '../../src/state';
import { mediaUrl, profile as profileApi } from '../../src/api';
import {
  PROFILE_TITLE, HUB, HUB_ROWS, SHEETS, WHOAMI, profileData, fmtUpdated, adaptSummary,
  onSummaryBusy, syncInterestLabels, PRO, FORMATS, FORMAT_SHORT, formatsForServer } from '../../src/profile';
import { langPlainName, searchLangs } from '../../src/languages';
import { isName, SUMMARY } from '../../src/onboarding';
import { writeFact, patchFor } from '../../src/fields';
import { color, radius as rad, space, type } from '../../src/theme';
import { useAgeVerified } from '../../src/components/VerifyCard';

export default function ProfileHub() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const ageOk = useAgeVerified();
  const p = st.profile;
  const d = useMemo(() => profileData(p), [p, lang]);

  const { height: winH } = useWindowDimensions();
  /** Пересборка идёт — своя или чужая. Сводку теперь обновляет сторож (startSummaryWatch), и
   *  «Kleal составляет описание…» должно загораться и тогда, когда правку сделали на другом
   *  экране, а сюда человек вернулся посреди запроса. */
  const [busy, setBusy] = useState(false);
  useEffect(() => onSummaryBusy(setBusy), []);
  /** Какой лист правки открыт. Пусто — ни один. */
  const [sheet, setSheet] = useState<'languages' | 'formats' | 'whoami' | 'summary' | null>(null);

  /**
   * Пересобрать сводку. Одна и та же дверь и для кнопки «Пересобрать», и для правок профиля —
   * защиты от затирания живут внутри adaptSummary, и обходить их отдельным путём нельзя.
   */
  const rewrite = async (extra = '') => {
    setBusy(true);
    try { return await adaptSummary(extra); } finally { setBusy(false); }
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
   * Сохранить «кто ты». Возраст, фото (с 17.10.2026) и имя (с 18.10.2026, шаг 4 «личность по id»)
   * сервер принимает патчем; строка ключуется id, имя — подпись. См. WHOAMI в src/profile.ts.
   */
  const saveWhoAmI = async (v: { name: string; surname: string; age: number; photo?: string }) => {
    const oldName = String(p.name || '').trim();
    const newName = v.name.trim();
    // Лист сюда с непригодным именем уже не пускает; проверка остаётся вторым рубежом.
    const renamed = isName(newName) && newName !== oldName;
    if (isName(newName)) set('name', newName);
    // Пустую фамилию записываем тоже — иначе стереть её было бы нельзя.
    set('surname', v.surname.trim());
    if (v.age) set('age', v.age);
    setSheet(null);
    /*
      ФОТО ТЕПЕРЬ ДОХОДИТ ДО СЕРВЕРА (сверка 17.10, п. 22; сервер выложен логикой 17.10). Раньше уходил
      только возраст: человек менял или убирал фото, а другие видели старое лицо. Новое фото едет
      data-URL'ом, сервер отвечает ссылкой с меткой ?v= — её и храним, чтобы кэш у других обновился.
      Убрать — пустая строка.

      ИМЯ ТОЖЕ ДОХОДИТ ДО СЕРВЕРА (шаг 4 плана «личность по id», 18.10.2026). Строка ключуется id, имя —
      только подпись: заявки, переписка, планы и группы остаются за человеком. Сервер пишет по порядку
      фото → имя → остальное и на первом отказе останавливается, поэтому при любом отказе имя на
      телефоне возвращается к прежнему — иначе телефон показывал бы имя, которого на сервере нет.
    */
    const prev = String(p.photo || '');
    const next = String(v.photo || '');
    const patch: Record<string, any> = {};
    if (v.age) patch.age = v.age;
    if (next !== prev) patch.photo = next;
    if (renamed) patch.name = newName;
    if (!('photo' in patch)) set('photo', next);
    if (oldName && Object.keys(patch).length) {
      const r: any = await profileApi.update(oldName, patch).catch(() => null);
      if ('photo' in patch) {
        if (r?.ok) set('photo', String(r.photo ?? next));
        else setPhotoNote(r?.error === 'bad photo' ? WHOAMI.photoRejected()
          : r?.error === 'sign in required' ? WHOAMI.photoSignIn() : WHOAMI.photoNotSaved());
      }
      if ('name' in patch) {
        if (r?.ok) set('name', String(r.name || newName));
        else {
          set('name', oldName);
          if (!('photo' in patch) || r?.error !== 'bad photo') {
            setPhotoNote(r?.error === 'bad name' ? WHOAMI.nameRejected()
              : r?.error === 'sign in required' ? WHOAMI.nameSignIn() : WHOAMI.nameNotSaved());
          }
        }
      }
    } else if ('photo' in patch) set('photo', next);
    rewrite();                     // сводка называет возраст вслух
  };
  /** Что не так с фото после сохранения листа — строкой под шапкой профиля. */
  const [photoNote, setPhotoNote] = useState('');

  const saveLanguages = async (list: string[]) => {
    writeFact('languages', list);
    setSheet(null);
    // Имена и форма серверных полей — из реестра (src/fields.ts), не отсюда.
    if (p.name) await profileApi.update(p.name, patchFor(['languages'])).catch(() => {});
    rewrite();                    // сводка называет языки вслух — она обязана догнать
  };

  /** B.03: форматы встреч. Подбор читает их полем `formats` (см. formatsForServer). */
  const formats: string[] = Array.isArray((p as any).formats)
    ? (p as any).formats.filter((x: string) => FORMATS.some((f) => f.id === x)) : [];
  const saveFormats = async (list: string[]) => {
    set('formats', list);
    setSheet(null);
    if (p.name) await profileApi.update(p.name, { formats: formatsForServer(list) }).catch(() => {});
    rewrite();                    // сводка говорит «один на один или небольшие группы» — пусть догонит
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
  // Подписи интересов на языке интерфейса: в строке лежат английские ключи, переводы приезжают
  // с сервера. Главный экран профиля показывает те же чипы, что и «Интересы», — значит и здесь.
  useEffect(() => { syncInterestLabels(); }, [lang, d.interests.length]);

  const autoTried = useRef(false);
  useEffect(() => {
    if (autoTried.current || busy || summary) return;
    if (d.interests.length + d.basics.length < 2) return;
    autoTried.current = true;
    rewrite();
  }, [summary, d.interests.length, d.basics.length, busy]);

  const city = String(p.city || '').trim();
  const km = p.geo?.maxDistanceKm;
  const personality = String((p as any).personality || '').trim();
  const rowSub = (id: string) => HUB_ROWS.find((r) => r.id === id)?.sub(p) || '';

  return (
    <ProfileShell title={PROFILE_TITLE()} onBack={() => router.back()} nav={<BottomNav active="profile" />}>
      {/*
        ПОДПИСЬ, КОТОРАЯ ИМЕНЕМ НЕ ЯВЛЯЕТСЯ, ЗДЕСЬ И ЛОВИТСЯ. У живого человека профиль назывался его
        собственным адресом почты; починка живёт в анкете, а сюда ставится дорога к ней. Строка
        появляется только у испорченного имени.
      */}
      {!isName(p.name) ? (
        <Card>
          <Text style={s.badNameText}>{WHOAMI.nameBad()}</Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.navigate('/chat')}
            style={({ pressed }) => [s.badNameBtn, pressed && { opacity: 0.85 }]}
          >
            <Text style={s.badNameBtnText}>{SUMMARY.saveFixName()}</Text>
          </Pressable>
        </Card>
      ) : null}

      {/* B.01 — кто ты: фото 88, имя с печатью, возраст и город, заполненность. Тап — лист «Кто ты»
          (имя, возраст и фото менять больше негде). */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={WHOAMI.title()}
        onPress={() => setSheet('whoami')}
        style={({ pressed }) => [s.idRow, pressed && { opacity: 0.9 }]}
      >
        {p.photo ? (
          <Image source={{ uri: mediaUrl(String(p.photo)) }} style={s.ava} />
        ) : (
          <View style={[s.ava, s.avaEmpty]}><IconPerson size={32} /></View>
        )}
        <View style={{ flex: 1, gap: 2 }}>
          <View style={s.nameRow}>
            <Text style={s.name} numberOfLines={1}>{d.name}</Text>
            {/* Печать — только прошедшим проверку возраста по документу (статус сервера, 18.10.2026). */}
            {ageOk ? <IconVerified /> : null}
          </View>
          {[p.age, city].filter(Boolean).length ? (
            <Text style={s.meta}>{[p.age, city].filter(Boolean).join(' · ')}</Text>
          ) : null}
          <Text style={s.metaSmall}>{PRO.complete(d.confidence)}</Text>
          {photoNote ? <Text style={[s.metaSmall, { color: color.primary }]}>{photoNote}</Text> : null}
        </View>
      </Pressable>

      <Card>
        <View style={s.sumHead}>
          <Text style={s.sumLabel}>{HUB.summaryLabel()}</Text>
          {updated ? <Text style={s.updated}>{updated}</Text> : null}
        </View>
        <Text style={s.sumText}>{summary || (busy ? HUB.writing() : HUB.empty())}</Text>
        {/* «Change it with Kleal» — тот же лист, где человек говорит Kleal, что учесть, и модель
            переписывает абзац. Руками абзац не правится: у него один хозяин. */}
        {busy ? <ActivityIndicator style={{ alignSelf: 'flex-start' }} color={color.primary} />
          : <KlealPill label={PRO.changeWithKleal()} onPress={() => setSheet('summary')} />}
      </Card>

      {/* Строка «What Kleal remembers» (B.02) появится вместе с памятью на сервере. */}
      <LinkRow Icon={IconUsers} title={PRO.formats()}
               sub={formats.length ? formats.map((f) => FORMAT_SHORT[f]?.() || f).join(' · ') : PRO.notSet()}
               onPress={() => setSheet('formats')} />
      <LinkRow Icon={IconStar} title={HUB_ROWS[0].title()} sub={rowSub('interests')}
               onPress={() => router.navigate('/profile/interests')} />
      <LinkRow Icon={IconFaceScan} title={HUB_ROWS[1].title()}
               sub={personality ? personality.split(/(?<=[.!?])\s/)[0] : PRO.personalityNotSet()}
               onPress={() => router.navigate('/profile/personality')} />
      <LinkRow Icon={IconTranslate} title={HUB_ROWS[3].title()} sub={rowSub('languages')}
               onPress={() => setSheet('languages')} />
      <LinkRow Icon={IconPin} title={HUB_ROWS[4].title()}
               sub={[city, km ? PRO.within(km) : ''].filter(Boolean).join(' · ') || PRO.notSet()}
               onPress={() => router.navigate('/profile/location')} />
      <LinkRow Icon={IconUserLock} title={HUB_ROWS[2].title()} sub={PRO.safetySub()}
               onPress={() => router.navigate('/profile/safety')} />
      <LinkRow Icon={IconGear} title={PRO.settings()} sub={PRO.settingsSub()}
               onPress={() => router.navigate('/settings')} />

      <SummarySheet
        open={sheet === 'summary'}
        summary={summary}
        maxHeight={Math.round(winH * 0.42)}
        onClose={() => setSheet(null)}
        onRebuild={rewrite}
      />
      <WhoAmISheet
        open={sheet === 'whoami'}
        p={p}
        onClose={() => setSheet(null)}
        onAccept={saveWhoAmI}
      />
      <FormatsSheet
        open={sheet === 'formats'}
        value={formats}
        onClose={() => setSheet(null)}
        onAccept={saveFormats}
      />
      <LanguagesSheet
        open={sheet === 'languages'}
        value={p.languages?.comfortable || []}
        onClose={() => setSheet(null)}
        onAccept={saveLanguages}
      />
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  idRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.sm },
  ava: { width: 88, height: 88, borderRadius: 44 },
  avaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  name: { fontSize: 20, lineHeight: 26, fontWeight: '700', color: color.fg, flexShrink: 1 } as any,
  meta: { ...type.bodySmall, color: color.fg } as any,
  metaSmall: { ...type.caption, color: color.fg } as any,

  basicTitle: { ...type.labelMedium, color: color.muted } as any,
  basicValue: { ...type.body, color: color.fg, marginTop: 2 } as any,

  sumHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  sumLabel: { fontSize: 15, fontWeight: '600', color: color.fg } as any,
  updated: { ...type.caption, color: color.muted } as any,
  sumText: { ...type.bodySmall, color: color.fg } as any,
  sheetNote: { ...type.bodySmall, color: color.fg } as any,

  whoPhotoRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  whoPhoto: { width: 84, height: 84, borderRadius: 42 },
  whoPhotoBtn: {
    height: 42, borderRadius: rad.full, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16,
  },
  whoPhotoBtnText: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  whoRemove: { ...type.caption, color: color.primary, textAlign: 'center' } as any,
  whoPhotoErr: { ...type.caption, color: color.danger, textAlign: 'center' } as any,

  // Карточка про испорченное имя. Тон предупреждения, а не ошибки: человек ничего не ломал.
  badNameText: { ...type.body, color: color.fg } as any,
  badNameBtn: {
    height: 44, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: space.sm,
  },
  badNameBtnText: { ...type.labelMedium, color: color.onPrimary, fontWeight: '700' } as any,
  whoInput: {
    height: 48, borderRadius: rad.md, backgroundColor: color.neutral100,
    paddingHorizontal: 14, color: color.fg, fontSize: 16,
  },
  whoNote: { ...type.caption, color: color.muted } as any,

  /** Лист правки сводки. Нынешний текст — плашкой: его читают, а не правят. */
  sumSheetNow: {
    borderRadius: rad.md, backgroundColor: color.neutral100, padding: 14,
  },
  sumSheetNowText: { ...type.body, color: color.fg } as any,
  sumSheetInput: {
    minHeight: 92, borderRadius: rad.md, backgroundColor: color.neutral100,
    padding: 12, color: color.fg, fontSize: 16, lineHeight: 22,
  },
  sumSheetWait: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  sumSheetWaitText: { ...type.bodySmall, color: color.muted, flex: 1 } as any,
  sumSheetErr: { ...type.caption, color: color.danger } as any,
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

/**
 * Кто ты: имя, возраст, фото. Правка идёт по черновику — крестик не сохраняет.
 *
 * Фото берётся из галереи и сжимается перед сохранением: в состоянии оно лежит data-URL'ом, и
 * несжатый снимок с телефона — это мегабайты в AsyncStorage на каждой записи профиля.
 */
/**
 * Лист правки сводки: нынешний текст, поле «что добавить», коралловая «Пересобрать».
 *
 * ТЕКСТ СВЕРХУ НЕ ПРАВИТСЯ РУКАМИ, и это осознанно: сводку пишет модель, а человек говорит ей,
 * что учесть. Иначе получались два хозяина у одного абзаца — человек правил слово, сторож
 * пересобирал абзац, и правка исчезала без следа. Так уже было.
 *
 * ЛИСТ НЕ ЗАКРЫВАЕТСЯ ПО НАЖАТИЮ. Он ждёт модель и показывает это; закроется сам, когда
 * абзац перепишется. Не получилось — остаётся открытым вместе с набранным текстом: терять
 * написанное человеком из-за отвалившейся сети нельзя.
 */
function SummarySheet({
  open, summary, maxHeight, onClose, onRebuild,
}: {
  open: boolean;
  summary: string;
  maxHeight: number;
  onClose: () => void;
  onRebuild: (extra: string) => Promise<boolean>;
}) {
  const [extra, setExtra] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    setExtra('');
    setBusy(false);
    setFailed(false);
  }, [open]);

  const go = async () => {
    setBusy(true);
    setFailed(false);
    const ok = await onRebuild(extra.trim());
    setBusy(false);
    if (ok) onClose();
    else setFailed(true);
  };

  return (
    <EditSheet
      open={open}
      title={HUB.summaryLabel()}
      onClose={busy ? () => {} : onClose}
      onAccept={go}
      acceptLabel={HUB.rewrite()}
      busy={busy}
      maxHeight={maxHeight}
    >
      <Text style={s.basicTitle}>{HUB.sumNow()}</Text>
      <View style={s.sumSheetNow}>
        <Text style={s.sumSheetNowText}>{summary || HUB.empty()}</Text>
      </View>

      <Text style={s.basicTitle}>{HUB.sumAdd()}</Text>
      <TextInput
        style={s.sumSheetInput}
        value={extra}
        onChangeText={setExtra}
        editable={!busy}
        multiline
        textAlignVertical="top"
        placeholder={HUB.sumAddHint()}
        placeholderTextColor={color.neutral400}
        accessibilityLabel={HUB.sumAdd()}
      />

      {busy ? (
        <View style={s.sumSheetWait}>
          <ActivityIndicator size="small" color={color.primary} />
          <Text style={s.sumSheetWaitText}>{HUB.writing()}</Text>
        </View>
      ) : null}
      {failed ? <Text style={s.sumSheetErr}>{HUB.sumFailed()}</Text> : null}
    </EditSheet>
  );
}

function WhoAmISheet({
  open, p, onClose, onAccept,
}: {
  open: boolean;
  p: any;
  onClose: () => void;
  onAccept: (v: { name: string; surname: string; age: number; photo?: string }) => void;
}) {
  const [name, setName] = useState(String(p.name || ''));
  const [surname, setSurname] = useState(String(p.surname || ''));
  const [age, setAge] = useState(String(p.age || ''));
  const [photo, setPhoto] = useState<string>(String(p.photo || ''));
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoErr, setPhotoErr] = useState('');
  /** Отказ по имени. Держим рядом с полем, а не в общем месте: чинится он прямо здесь. */
  const [nameErr, setNameErr] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(String(p.name || ''));
    setSurname(String(p.surname || ''));
    setAge(String(p.age || ''));
    setPhoto(String(p.photo || ''));
    setPhotoErr('');
    setNameErr(false);
  }, [open]);

  const pick = async () => {
    setPhotoErr('');
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    // Без allowsEditing — экран «ОБРЕЗАТЬ» между выбором и профилем не нужен: квадрат вырезаем
    // сами, по размерам, которые пикер отдаёт вместе с файлом (то же, что в онбординге).
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.9 });
    if (res.canceled || !res.assets?.length) return;
    const a = res.assets[0];
    // Подготовка — общая с онбордингом (src/photo.ts). Своя копия здесь однажды разъехалась с той
    // на одну строку, и смена фото молча перестала работать.
    setPhotoBusy(true);
    try {
      const shot = await squarePhoto(a);
      setPhoto(shot.dataUrl);
    } catch {
      // Молчать нельзя: человек уже выбрал снимок и ждёт его на экране.
      setPhotoErr(WHOAMI.photoFailed());
    } finally {
      setPhotoBusy(false);
    }
  };

  return (
    <EditSheet
      open={open}
      title={WHOAMI.title()}
      onClose={onClose}
      onAccept={() => {
        // Пустое имя лист принимал и раньше — оно просто не записывалось. Адрес записывался.
        if (!isName(name)) { setNameErr(true); return; }
        setNameErr(false);
        onAccept({ name, surname, age: parseInt(age, 10) || 0, photo });
      }}
      acceptLabel={SHEETS.accept()}
    >
      <View style={s.whoPhotoRow}>
        {photo ? (
          <Image source={{ uri: mediaUrl(String(photo)) }} style={s.whoPhoto} />
        ) : (
          <View style={[s.whoPhoto, s.avaEmpty]}><IconPerson size={30} /></View>
        )}
        <View style={{ flex: 1, gap: space.sm }}>
          <Pressable
            accessibilityRole="button"
            style={[s.whoPhotoBtn, photoBusy && { opacity: 0.6 }]}
            onPress={photoBusy ? undefined : pick}
            accessibilityState={{ busy: photoBusy }}
          >
            {photoBusy ? (
              <ActivityIndicator size="small" color={color.fg} />
            ) : (
              <Text style={s.whoPhotoBtnText}>{WHOAMI.changePhoto()}</Text>
            )}
          </Pressable>
          {photo && !photoBusy ? (
            <Pressable accessibilityRole="button" onPress={() => setPhoto('')}>
              <Text style={s.whoRemove}>{WHOAMI.removePhoto()}</Text>
            </Pressable>
          ) : null}
          {photoErr ? <Text style={s.whoPhotoErr}>{photoErr}</Text> : null}
        </View>
      </View>

      <Text style={s.basicTitle}>{WHOAMI.name()}</Text>
      <TextInput
        style={s.whoInput}
        value={name}
        onChangeText={(v) => { setName(v); if (nameErr) setNameErr(false); }}
        placeholder={WHOAMI.name()}
        placeholderTextColor={color.neutral400}
        accessibilityLabel={WHOAMI.name()}
      />
      {nameErr ? <Text style={s.whoPhotoErr}>{WHOAMI.nameBad()}</Text> : null}
      <Text style={s.whoNote}>{WHOAMI.nameNote()}</Text>

      <Text style={s.basicTitle}>{WHOAMI.surname()}</Text>
      <TextInput
        style={s.whoInput}
        value={surname}
        onChangeText={setSurname}
        placeholder={WHOAMI.surname()}
        placeholderTextColor={color.neutral400}
        accessibilityLabel={WHOAMI.surname()}
      />
      <Text style={s.whoNote}>{WHOAMI.surnameNote()}</Text>

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

/** B.03 — форматы встреч: строки с галочкой, «Save» и «Cancel». Правка по черновику. */
function FormatsSheet({
  open, value, onClose, onAccept,
}: {
  open: boolean;
  value: string[];
  onClose: () => void;
  onAccept: (list: string[]) => void;
}) {
  const [sel, setSel] = useState<string[]>(value);
  useEffect(() => { if (open) setSel(value); }, [open]);
  const toggle = (k: string) => setSel((x) => (x.includes(k) ? x.filter((y) => y !== k) : [...x, k]));
  return (
    <EditSheet open={open} title={PRO.formats()} onClose={onClose} onAccept={() => onAccept(sel)}
               acceptLabel={PRO.save()} cancelLabel={PRO.cancel()}>
      <SectionHead title={PRO.formatsHow()} />
      {FORMATS.map((f) => <OptionRow key={f.id} label={f.label()} on={sel.includes(f.id)} onPress={() => toggle(f.id)} />)}
      <Text style={s.sheetNote}>{PRO.formatsNote()}</Text>
    </EditSheet>
  );
}

/** Ходовые языки — первыми строками листа (B.06), как в «First run» A.07. */
const COMMON_LANGS = ['Italian', 'English', 'Spanish', 'Catalan', 'French'];

/**
 * B.06 — языки строками с галочкой. Свои — всегда сверху, затем ходовые; редкий язык находится
 * полем поиска под списком (на кадре его добавляют в разговоре с Kleal — здесь короче и без чата).
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
  const base = [...new Set([...value, ...COMMON_LANGS])];
  const extra = [...sel.filter((k) => !base.includes(k))];
  const found = q.trim() ? searchLangs(q).map((l) => l[0]).filter((k) => !base.includes(k) && !extra.includes(k)).slice(0, 8) : [];
  return (
    <EditSheet open={open} title={SHEETS.languages()} onClose={onClose} onAccept={() => onAccept(sel)}
               acceptLabel={PRO.save()} cancelLabel={PRO.cancel()}>
      <SectionHead title={PRO.langsYouSpeak()} />
      {[...base, ...extra, ...found].map((k) => (
        <OptionRow key={k} label={langPlainName(k, ru)} on={sel.includes(k)} onPress={() => toggle(k)} />
      ))}
      <TextInput
        style={s.search}
        value={q}
        onChangeText={setQ}
        placeholder={PRO.findLang()}
        placeholderTextColor={color.neutral400}
        autoCorrect={false}
        accessibilityLabel={PRO.findLang()}
      />
      {q.trim() && !found.length ? <Text style={s.sheetNote}>{SHEETS.nothing()}</Text> : null}
      <Text style={s.sheetNote}>{PRO.langsNote()}</Text>
    </EditSheet>
  );
}
