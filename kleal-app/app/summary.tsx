/**
 * Сводка профиля — кадр A.14.
 *
 * Шапка меняет заголовок на «What Kleal knows about you» и показывает 100 %: онбординг закончен,
 * дальше речь уже не о заполнении, а о том, что из этого понято.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Alert, View, Text, StyleSheet, ScrollView, Pressable, Image } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useLang, T, replyLang } from '../src/i18n';
import { useOnb, patch, set, get, getState, profileForRegister, profileForAttach } from '../src/state';
import { mediaUrl, onboarding } from '../src/api';
import { SUMMARY, SUMMARY_TITLE, hobbyPlain, langPlain } from '../src/onboarding';
import { Composer } from '../src/components/Composer';
import { IconPerson } from '../src/components/icons';
import { color, radius as rad, space, type } from '../src/theme';
import { interestLabels } from '../src/interest-label';

export default function Summary() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const p = st.profile;

  /*
    СВОДКА НАЧИНАЕТСЯ С СОХРАНЁННОЙ, А НЕ С ПУСТОТЫ, и рядом живёт признак «ещё идёт».

    Раньше `text` был пуст, а рисовалось `text || fallback` — и запасной перечень («Интересы: …
    Языки: … Обычно бывает: …») показывался ВСЕГДА, пока не ответит модель. Человек успевал
    прочитать машинное перечисление, и оно на глазах подменялось живой фразой: выглядело так,
    будто экран сам себя переписывает (сообщено с телефона со скриншотом).

    Запасной вариант заводился на случай «модель молчит или упала» — вот пусть только для него и
    остаётся. Пока ответ в пути, показываем, что он в пути; у вернувшегося на экран показываем
    его прошлую сводку, и мигания нет вовсе.
  */
  const [text, setText] = useState(String((st.profile as any)?.summary || '').trim());
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState('');
  /*
    НАЗВАННЫЕ СЕРВЕРОМ ИНТЕРЕСЫ ДЕРЖИМ ОТДЕЛЬНО ОТ ТЕКСТА ОШИБКИ.

    Текст говорит «убери их» — а убирать было нечем: на сводке нет редактора интересов, назад
    ведёт в анкету, которая при заполненном профиле возвращает обратно сюда. Человек оказывался в
    петле: ни вперёд, ни назад (сообщено с телефона со скриншотом). Список нужен, чтобы предложить
    единственное действие, которое здесь имеет смысл, — убрать и сохранить.
  */
  const [rejected, setRejected] = useState<string[]>([]);
  /** Сервер попросил войти. Держим отдельно от текста ошибки: под ним появляется кнопка входа. */
  const [needsSignIn, setNeedsSignIn] = useState(false);
  /**
   * Сервер не принял имя. Отдельно от прочих отказов, потому что чинится он не здесь: под ним
   * появляется дорога в анкету, которая снимет непригодную подпись и спросит имя заново.
   */
  const [badName, setBadName] = useState(false);

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
      .summary(profileForAttach(), replyLang())
      .then((r: any) => {
        if (!alive) return;
        const next = String(r?.summary || '').trim();
        setText(next);
        // Сводку надо СОХРАНИТЬ, а не только показать. Раньше она жила в состоянии этого экрана и
        // пропадала при уходе с него: профиль потом навсегда показывал «Kleal опишет тебя здесь»,
        // хотя описание уже было составлено минуту назад.
        if (next) { set('summary', next); set('summaryUpdated', Date.now()); }
      })
      .catch(() => {})
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  // Если модель молчит или упала — собираем фразу из того, что известно. Пустая карточка на
  // последнем шаге онбординга хуже, чем неидеальная формулировка.
  // Русский собирается ТОЛЬКО через двоеточия: названия языков и городов приходят готовыми
  // строками, склонять их нечем, и «говорит на Английский» — сломанный русский. Английский
  // при этом строится нормальной фразой, ему падежи не нужны.
  const fallback = useMemo(() => {
    const h = interestLabels(p.interests?.explicit);
    const l = (p.languages?.comfortable || []).map(langPlain);
    const bits = [
      h.length ? T('Интересы: ' + h.join(', '), 'Into ' + h.join(', ')) : '',
      l.length ? T('Языки: ' + l.join(', '), 'speaks ' + l.join(', ')) : '',
      p.city ? T('Обычно бывает: ' + p.city, 'usually around ' + p.city) : '',
    ].filter(Boolean);
    return bits.join('. ') + (bits.length ? '.' : '');
  }, [p]);

  /**
   * Записать профиль на сервер — ЕДИНСТВЕННОЕ место, где это происходит.
   *
   * Через него обязаны проходить ОБА выхода с экрана. «Все настройки профиля» уводила отсюда
   * простым переходом, и человек получал поздравление, не существуя на сервере: в users.json его
   * не было, поиск не мог его найти, а `done` не ставился — следующий запуск снова открывал интро.
   *
   * Возвращает true, только когда профиль действительно записан: не записался — никуда не уходим,
   * а показываем ошибку. Уйти с непрописанным профилем нельзя ни одной кнопкой.
   */
  /**
   * Убрать названные сервером интересы и сохранить снова.
   *
   * Сравнение по нижнему регистру: сервер называет их канонической ручкой (`bowling`), а в профиле
   * лежит ровно она же — но регистр по дороге терять нельзя, иначе не совпадёт и кнопка сделает
   * вид, что сработала. Заодно чистим подпись и квитанцию: оставленная квитанция к выброшенному
   * интересу — мусор, который переживёт анкету.
   */
  const dropRejected = async () => {
    const off = new Set(rejected.map((x) => x.trim().toLowerCase()));
    const cur: string[] = get('interests.explicit') || [];
    set('interests.explicit', cur.filter((k) => !off.has(String(k).trim().toLowerCase())));
    const prof: any = getState().profile || {};
    const strip = (o: any) => Object.fromEntries(
      Object.entries(o || {}).filter(([k]) => !off.has(String(k).trim().toLowerCase())));
    set('interests.labels', strip((prof.interests || {}).labels));
    set('interests.confirmations', strip((prof.interests || {}).confirmations));
    setRejected([]);
    if (await register()) router.replace('/done');
  };

  const register = async (): Promise<boolean> => {
    setSending(true);
    setErr('');
    try {
      const r: any = await onboarding.register(profileForRegister());
      if (!r?.ok) {
        // Сервер ОТВЕТИЛ и отказал — это не обрыв связи. Самая частая причина: интерес, которого
        // нет в каталоге; сервер называет его прямо, и человеку надо показать именно это.
        // Пока здесь стояло «проверь связь», люди чинили интернет вместо интереса.
        const why = String(r?.error || '');
        /*
          НЕТ СЕССИИ — НЕ ОШИБКА, А РАЗВИЛКА. Профиль пишется только своему аккаунту, и человек без
          сессии на этом устройстве не сохранит его никогда, сколько бы раз ни нажал. Такое бывает
          у тех, кто заводил профиль до появления сессий или вышел из аккаунта.
          Показываем не «не сохранилось», а дорогу ко входу: после него анкета сама вернёт сюда —
          профиль лежит в памяти телефона, а возобновление ведёт на сводку, когда всё заполнено.
        */
        if (/sign\s*in\s*required/i.test(why)) {
          setNeedsSignIn(true);
          setErr(SUMMARY.saveNeedsSignIn());
          return false;
        }
        /*
          ИМЯ, КОТОРОЕ ИМЕНЕМ НЕ ЯВЛЯЕТСЯ. Раньше такое имя сервер принимал молча, и человек ходил
          по приложению под собственным адресом почты — его читали все, кому он писал. Теперь
          сервер отказывает, и отказ обязан вести к починке: без кнопки это был бы тупик, потому
          что и «Готово», и «Все настройки профиля» начинаются с той же самой записи.
        */
        if (/invalid name/i.test(why)) {
          setBadName(true);
          setErr(SUMMARY.saveBadName());
          return false;
        }
        const m = why.match(/unconfirmed interests:\s*(.+)/i);
        // Сервер отдаёт их и списком (`interests`), и строкой в тексте ошибки. Берём список, если
        // он есть: разбирать строку обратно — терять то, что уже разобрано.
        const named: string[] = Array.isArray(r?.interests) && r.interests.length
          ? r.interests.map(String)
          : (m ? m[1].split(',').map((x: string) => x.trim()).filter(Boolean) : []);
        setRejected(named);
        setErr(m ? SUMMARY.saveRejectedInterests(m[1].trim()) : SUMMARY.saveRejected(why || '—'));
        return false;
      }
      // ПРИВЯЗКА БЕЗУСЛОВНА. Раньше здесь стояло `if (st.login)`, а `login` выставлял единственный
      // экран «Логин и пароль»: всякий, кто входил иначе, доходил до конца анкеты без него, и
      // профиль не привязывался ни к чему — он оставался в памяти телефона и строкой в users.json
      // по имени. Переустановил приложение и войти обратно некуда. Теперь личность сервер берёт из
      // сессии; `login` едет рядом только ради старых сборок, которые про сессии не знают.
      await onboarding.attach(st.login || '', p.name || '', profileForAttach()).catch(() => {});
      // Отметка ставится ТОЛЬКО после успешной записи: иначе следующий запуск пустил бы человека
      // в приложение с профилем, которого на сервере нет.
      patch({ done: true });
      return true;
    } catch {
      // Сюда попадает только настоящий обрыв: запрос не дошёл или ответ не разобрался.
      setErr(SUMMARY.saveOffline());
      return false;
    } finally {
      setSending(false);
    }
  };

  const finish = async () => {
    if (await register()) router.replace('/done');
  };

  /**
   * Кнопка обещает настройки профиля — туда и ведёт. Запись идёт первой, как и у «Готово»:
   * уйти в приложение с профилем, которого нет на сервере, нельзя.
   *
   * Но НЕУДАЧА ЗАПИСИ БОЛЬШЕ НЕ ДЕЛАЕТ КНОПКУ МЁРТВОЙ. Раньше при сбое здесь просто ничего не
   * происходило: сообщение об ошибке рисуется в самом низу прокрутки, за краем экрана, и со
   * стороны это выглядело как «нажимаю — и ничего» (сообщено 14 августа с телефона). Теперь
   * причина всплывает поверх экрана, и человек видит, что произошло.
   */
  const toProfile = async () => {
    // Финал онбординга: `replace` подменил бы только этот экран, оставив под ним всю анкету —
    // и «назад» из профиля вело бы обратно в неё. Онбординг закончен, возвращаться некуда:
    // сворачиваем стопку до главной и открываем профиль поверх неё.
    if (await register()) { router.dismissAll(); router.navigate('/home'); router.navigate('/profile'); return; }
    // Причина уже разобрана в register() и лежит в err — Alert обязан говорить то же самое,
    // иначе на одном экране два разных объяснения одной неудачи.
    Alert.alert(T('Профиль не сохранился', 'Your profile didn’t save'), err || SUMMARY.saveOffline());
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
              <Image source={{ uri: mediaUrl(String(p.photo)) }} style={s.idAvatar} />
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
          <Text style={[s.para, !text && loading && s.paraWait]}>
            {text || (loading ? SUMMARY.composing() : fallback)}
          </Text>
          <Pressable
            accessibilityRole="button"
            style={[s.cta, sending && { opacity: 0.6 }]}
            onPress={sending ? undefined : toProfile}
            accessibilityState={{ busy: sending }}
          >
            <Text style={s.ctaText}>{SUMMARY.viewAll()}</Text>
          </Pressable>
        </View>

        <View style={s.info}>
          <Text style={s.infoTitle}>✦  {SUMMARY.planTitle()}</Text>
          <Text style={s.infoBody}>{SUMMARY.planBody()}</Text>
        </View>

        {err ? <Text style={s.err}>{err}</Text> : null}
        {/*
          Кнопка появляется ТОЛЬКО когда сервер назвал конкретные интересы. При обрыве связи её нет:
          там убирать нечего, там надо повторить.
        */}
        {rejected.length ? (
          <Pressable accessibilityRole="button" onPress={dropRejected} disabled={sending}
                     style={({ pressed }) => [s.drop, pressed && { opacity: 0.85 }]}>
            <Text style={s.dropText}>{SUMMARY.dropRejected()}</Text>
          </Pressable>
        ) : null}
        {/*
          Дорога ко входу вместо тупика. Собранное никуда не девается: оно лежит в памяти телефона,
          и возобновление анкеты приведёт человека обратно сюда — на сводку, раз всё заполнено.
        */}
        {badName ? (
          <Pressable accessibilityRole="button" onPress={() => router.navigate('/chat')}
                     style={({ pressed }) => [s.drop, pressed && { opacity: 0.85 }]}>
            <Text style={s.dropText}>{SUMMARY.saveFixName()}</Text>
          </Pressable>
        ) : null}
        {needsSignIn ? (
          <Pressable accessibilityRole="button" onPress={() => router.navigate('/auth')}
                     style={({ pressed }) => [s.drop, pressed && { opacity: 0.85 }]}>
            <Text style={s.dropText}>{SUMMARY.saveGoSignIn()}</Text>
          </Pressable>
        ) : null}
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
  /** Ожидание — приглушённым: это ещё не описание, и путать его с описанием нельзя. */
  paraWait: { color: color.muted } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  /** Единственное действие, которое на этом экране имеет смысл при отказе, — потому и заметное. */
  drop: {
    marginTop: space.md,
    alignSelf: 'flex-start',
    paddingHorizontal: space.lg,
    height: 44,
    borderRadius: rad.full,
    backgroundColor: color.ink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dropText: { ...type.button, color: color.onPrimary } as any,
  foot: { paddingHorizontal: 20, paddingTop: space.md },
});
