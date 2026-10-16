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
import { View, Text, StyleSheet, Pressable, Image, TextInput, ActivityIndicator, Alert, Platform,
         useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, Segments, EditSheet } from '../../src/components/ProfileShell';
import * as ImagePicker from 'expo-image-picker';
import { squarePhoto } from '../../src/photo';
import { BottomNav } from '../../src/components/BottomNav';
import {
  IconPerson, IconVerified, IconStar, IconFaceScan, IconUserLock, IconTranslate, IconPin, IconPencil, IconGear,
} from '../../src/components/icons';
import { useLang, getLang, setLang } from '../../src/i18n';
import { useOnb, set, reset } from '../../src/state';
import { forgetOwner } from '../../src/history';
import { mediaUrl, profile as profileApi } from '../../src/api';
import {
  PROFILE_TITLE, HUB, SIGNOUT, HUB_ROWS, SHEETS, WHOAMI, profileData, fmtUpdated, adaptSummary,
  onSummaryBusy, syncInterestLabels } from '../../src/profile';
import { langName, searchLangs } from '../../src/languages';
import { isName, SUMMARY } from '../../src/onboarding';
import { writeFact, patchFor } from '../../src/fields';
import { SETTINGS } from '../../src/settings';
import { AreaPicker, Area, DEFAULT_AREA, PLACES } from '../../src/components/AreaPicker';
import { color, radius as rad, space, type } from '../../src/theme';

export default function ProfileHub() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const p = st.profile;
  const d = useMemo(() => profileData(p), [p, lang]);

  const { height: winH } = useWindowDimensions();
  /** Пересборка идёт — своя или чужая. Сводку теперь обновляет сторож (startSummaryWatch), и
   *  «Kleal составляет описание…» должно загораться и тогда, когда правку сделали на другом
   *  экране, а сюда человек вернулся посреди запроса. */
  const [busy, setBusy] = useState(false);
  useEffect(() => onSummaryBusy(setBusy), []);
  /** Какой лист правки открыт. Пусто — ни один. */
  const [sheet, setSheet] = useState<'languages' | 'location' | 'whoami' | 'summary' | null>(null);

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
   * Сохранить «кто ты». Возраст сервер принимает патчем; имя и фото — нет: строка пользователя
   * ключуется именем, а фото едет отдельным путём при регистрации. См. WHOAMI в src/profile.ts —
   * там записано, почему переименование не создаёт вторую строку молча.
   */
  const saveWhoAmI = async (v: { name: string; surname: string; age: number; photo?: string }) => {
    // Лист сюда с непригодным именем уже не пускает; проверка остаётся вторым рубежом.
    if (isName(v.name)) set('name', v.name.trim());
    // Пустую фамилию записываем тоже — иначе стереть её было бы нельзя.
    set('surname', v.surname.trim());
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
    // location.area ложится в profile.city — значит это ГОРОД. Раньше сюда приезжало название
    // страны, и человек из Барселоны хранился как живущий в «Spain».
    writeFact('location.area', a.city);
    /*
      СТРАНА ТОЖЕ СОХРАНЯЕТСЯ. Лист давал её выбрать, показывал выбранной — и терял: факта
      «location.country» в реестре не было вовсе, а экран не имеет права писать имя поля строкой.
      Поэтому у человека из Лондона страна каждый раз возвращалась к «Испании» — не потому что
      экран так решил, а потому что сохранять её было нечем. Теперь факт заведён (shared/fields.json).
    */
    writeFact('location.country', a.country);
    writeFact('location.lat', a.lat);
    writeFact('location.lon', a.lon);
    writeFact('location.radiusKm', a.km);
    setSheet(null);
    if (p.name) {
      await profileApi.update(
        p.name,
        patchFor(['location.area', 'location.country', 'location.lat', 'location.lon', 'location.radiusKm'])
      ).catch(() => {});
    }
    rewrite();                    // «живёт в Барселоне» после переезда в Италию — неправда
  };

  const signOut = () => {
    const has = !!st.login;
    const go = () => { forgetOwner();   // выход из аккаунта уносит и переписку — см. src/history.ts
      reset(); router.replace('/'); };
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
          onPress={() => router.navigate('/settings')}
        >
          <IconGear />
        </Pressable>
      }
    >
      {/*
        ПОДПИСЬ, КОТОРАЯ ИМЕНЕМ НЕ ЯВЛЯЕТСЯ, ЗДЕСЬ И ЛОВИТСЯ.

        У живого человека профиль назывался его собственным адресом почты, и адрес читал каждый,
        кому он писал. Сам он это починить не мог: анкета с заполненным именем на шаг имени не
        заходит, а правка в листе «Кто ты» до сервера не доезжает — имя туда уходит только вместе
        с регистрацией. Значит починка живёт в анкете, а сюда ставится дорога к ней: анкета снимет
        непригодную подпись, спросит имя и на заполненном профиле сама выведет на сводку, где
        «Готово» и перепишет строку.

        Строка появляется только у испорченного имени: у всех остальных её нет вовсе.
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
              <Image source={{ uri: mediaUrl(String(p.photo)) }} style={s.ava} />
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

        {/*
          ОДНА ДВЕРЬ. Раньше здесь стояли две ссылки: «Изменить» открывала поле правки прямо в
          карточке, «Пересобрать» молча звала модель — и что именно она сделает, по кнопке было
          не понять. Теперь дверь одна, а выбор — внутри листа, рядом с текстом, который меняют.
        */}
        <Text style={s.sumText}>
          {summary || (busy ? HUB.writing() : HUB.empty())}
        </Text>
        <View style={s.linkRow}>
          <Pressable accessibilityRole="button" accessibilityState={{ busy }}
                     onPress={busy ? undefined : () => setSheet('summary')}>
            {busy ? <ActivityIndicator size="small" color={color.primary} />
                  : <Text style={s.link}>{HUB.edit()}</Text>}
          </Pressable>
        </View>

        {/*
          Ведёт в разговор создания интента, а не в мастер: мастер начинается с формата и времени,
          то есть с того, что ставится руками ПОСЛЕ того, как тема собрана. Открывать его первым —
          значит просить человека выбрать «онлайн или офлайн» раньше, чем он сказал, для чего.
        */}
        <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.navigate('/create')}>
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
            ? router.navigate(`/profile/${row.id}` as any)
            : setSheet(row.id as 'languages' | 'location'))}
        />
      ))}


      <Card>
        <Text style={s.basicTitle}>{HUB.lang()}</Text>
        <Segments
          options={[['ru', 'RU'], ['en', 'EN'], ['es', 'ES']]}
          value={lang}
          onChange={(v) => setLang(v as any)}
        />
      </Card>

      {/*
        Выход стирает состояние на устройстве целиком — и профиль тоже. Оставить его лежать значило
        бы показать его следующему, кто возьмёт этот телефон. Карточка показывается всегда: см.
        SIGNOUT — привязка к логину прятала кнопку от тех, у кого логина нет.
      */}
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
  linkRow: { flexDirection: 'row', gap: space.lg, marginTop: 2 },
  link: { ...type.labelMedium, color: color.primary } as any,

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
  /*
    ВОСЕМЬДЕСЯТ ЧЕТЫРЕ ЧИПА СРАЗУ — ЭТО НЕ ВЫБОР, А СТЕНА.

    `searchLangs('')` отдаёт ВЕСЬ список, и лист открывался простынёй на десяток экранов прокрутки:
    свои языки терялись сверху, найти нужный глазами быстрее, чем напечатать, было нельзя.
    Показываем первые двенадцать — список курирован, и в начале стоят самые ходовые, — а под ними
    честно говорим, сколько осталось и как их достать. Начал печатать — ищется по всему списку.
  */
  const all = searchLangs(q).filter((l) => !sel.includes(l[0]));
  const short = !q.trim();
  const found = short ? all.slice(0, 12) : all;
  const hidden = short ? all.length - found.length : 0;

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

      {hidden > 0 ? <Text style={s.basicValue}>{SHEETS.moreLangs(hidden)}</Text> : null}
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
  /**
   * ЛИСТ ОТКРЫВАЕТСЯ НА СВОЁМ МЕСТЕ, А НЕ В БАРСЕЛОНЕ.
   *
   * Было три подстановки по умолчанию, и каждая врала своему человеку. Страна бралась ТОЛЬКО из
   * короткого списка городов (сорок штук на пять стран), поэтому у живущего в Лондоне, Бадалоне
   * или Матаро — а это две сотни людей в базе — открывалась «Испания» и якорь «Вернуть к
   * Barcelona». Координаты при их отсутствии (двести с лишним профилей) ставились барселонскими:
   * строка города говорила «London», а карта показывала Испанию.
   *
   * Теперь порядок такой: страна — та, что сохранена в профиле, и только если её там нет,
   * выводится по городу; точка — своя, а без неё берётся точка своего города из списка, и лишь
   * в последнюю очередь — первый город страны. Якорь «Вернуть к …» называет свой город, если он
   * в списке, иначе первый город своей страны — но никогда чужую Барселону.
   */
  const current = (): Area => {
    const city = String(p.city || '').trim() || DEFAULT_AREA.city;
    const home = PLACES.find((x) => x.cities.some((c) => c[0] === city));
    // Страна своя, даже если её нет в коротком списке: AreaPicker добавит её первой строкой
    // (см. placesFor). Подменять «Россию» «Испанией» только потому, что список короткий, нельзя.
    const saved = String(p.country || '').trim();
    const country = saved || home?.country || DEFAULT_AREA.country;
    const list = PLACES.find((x) => x.country === country);
    const row = list?.cities.find((c) => c[0] === city) || list?.cities[0];
    const lat = Number(p.geo?.coarseLat);
    const lon = Number(p.geo?.coarseLon);
    // Ноль на обеих осях сервер и сам считает отсутствием координат, а не точкой в Атлантике.
    const mine = Number.isFinite(lat) && Number.isFinite(lon) && !(lat === 0 && lon === 0);
    return {
      country,
      city,
      // Якорь «Вернуть к …»: свой город, если он в списке; страна не из списка — тоже свой город.
      pinCity: home || !list ? city : row![0],
      lat: mine ? lat : (row?.[1] ?? DEFAULT_AREA.lat),
      lon: mine ? lon : (row?.[2] ?? DEFAULT_AREA.lon),
      km: p.geo?.maxDistanceKm ?? 15,
      // Точка «своя», когда города нет в списке: подпись тогда показывает адрес, а не город.
      moved: !home && mine,
    };
  };
  const [area, setArea] = useState<Area>(current);
  /**
   * Пока карту двигают или сводят пальцами, прокрутка листа выключена.
   *
   * Жест у карты и у прокрутки общий, и без этого прокрутка забирала вертикальное движение себе:
   * карту в профиле нельзя было ни подвинуть, ни приблизить — она только уезжала вместе с листом.
   * В онбординге ровно то же место решено так же, здесь этого просто не было.
   */
  const [dragging, setDragging] = useState(false);
  useEffect(() => { if (open) setArea(current()); }, [open]);
  return (
    <EditSheet
      open={open}
      title={SHEETS.location()}
      onClose={onClose}
      onAccept={() => onAccept(area)}
      acceptLabel={SHEETS.accept()}
      scrollEnabled={!dragging}
    >
      <AreaPicker value={area} onChange={setArea} onDragChange={setDragging} />
    </EditSheet>
  );
}
