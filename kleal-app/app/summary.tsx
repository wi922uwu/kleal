/**
 * Сводка профиля — кадр A.14.
 *
 * Шапка меняет заголовок на «What Kleal knows about you» и показывает 100 %: онбординг закончен,
 * дальше речь уже не о заполнении, а о том, что из этого понято.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Alert, View, Text, StyleSheet, ScrollView, Image } from 'react-native';
import Animated, { Easing, useAnimatedProps, useReducedMotion, useSharedValue, withTiming } from 'react-native-reanimated';
import Svg, { Circle } from 'react-native-svg';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useLang, T, replyLang } from '../src/i18n';
import { useOnb, patch, set, get, getState, profileForRegister, profileForAttach } from '../src/state';
import { mediaUrl, onboarding } from '../src/api';
import { SUMMARY, SUMMARY_TITLE, hobbyPlain, langPlain } from '../src/onboarding';
import { Composer } from '../src/components/Composer';
import { IconPerson, IconVerified } from '../src/components/icons';
import { GlassPill } from '../src/components/Glass';
import { Blob } from '../src/components/Blob';
import { GlassBack, GlassSurface, riseIn } from '../src/components/LiquidGlass';
import { color, font, heading, space, type } from '../src/theme';

/** Дуга кольца уверенности анимируется свойством strokeDashoffset — нужен анимированный Circle. */
const ARing = Animated.createAnimatedComponent(Circle);
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { interestLabels } from '../src/interest-label';

export default function Summary() {
  const lang = useLang();
  const reduced = useReducedMotion();
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
      h.length ? T('Интересы: ' + h.join(', '), 'Into ' + h.join(', '), 'Le gusta ' + h.join(', ')) : '',
      l.length ? T('Языки: ' + l.join(', '), 'speaks ' + l.join(', '), 'habla ' + l.join(', ')) : '',
      p.city ? T('Обычно бывает: ' + p.city, 'usually around ' + p.city, 'suele estar por ' + p.city) : '',
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
      const attached: any = await onboarding.attach(st.login || '', p.name || '', profileForAttach());
      // register owns the user row, but attach persists the restorable account profile. A
      // rejected or lost attach is not completed onboarding: retain the draft for retry.
      if (!attached?.ok) {
        const why = String(attached?.error || '');
        if (/sign\s*in\s*required|no session/i.test(why)) {
          setNeedsSignIn(true);
          setErr(SUMMARY.saveNeedsSignIn());
        } else setErr(SUMMARY.saveRejected(why || '—'));
        return false;
      }
      // Отметка ставится ТОЛЬКО после успешной записи: иначе следующий запуск пустил бы человека
      // в приложение с профилем, которого на сервере нет.
      patch({ done: true });
      return true;
    } catch (e: any) {
      // HTTP 401 requires sign-in; network failures keep the draft available for retry.
      if (e?.status === 401) {
        setNeedsSignIn(true);
        setErr(SUMMARY.saveNeedsSignIn());
      } else setErr(SUMMARY.saveOffline());
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
    Alert.alert(T('Профиль не сохранился', 'Your profile didn’t save', 'Tu perfil no se guardó'), err || SUMMARY.saveOffline());
  };

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 8 }]}>
      {/* Фирменный фон «Ambient · glass pilot» — тот же слой, что на входных экранах. */}
      <Ambient glows={GLOW_FORM} />
      {/* Шапка — та же, что у разговора (кадр A.14): «назад», заголовок по центру, 100% и капля. */}
      <View style={s.head}>
        <View style={s.headSide}>
          <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={() => router.back()} />
        </View>
        {/* По-русски заголовок длинный («Что Kleal знает о тебе») — ужимается по ширине, а не режется. */}
        <Text style={[s.headTitle, heading(lang, type.headingSm)]} numberOfLines={1}
              adjustsFontSizeToFit minimumFontScale={0.7}>{SUMMARY_TITLE()}</Text>
        <View style={[s.headSide, s.headRight]}>
          <Text style={s.headPct}>100%</Text>
          <Blob size={30} float={false} />
        </View>
      </View>
      <View style={s.track}><View style={[s.trackFill, { width: '100%' }]} /></View>

      <ScrollView contentContainerStyle={s.scroll}>
        {/* Карточка человека: аватар в кольце уверенности, имя, «70% PROFILE CONFIDENCE». */}
        <View style={s.cardShadow}>
          <GlassSurface tone="light" radius={16} style={s.card}>
            <View style={s.idRow}>
              <ConfidenceRing pct={confidence}>
                {p.photo ? (
                  <Image source={{ uri: mediaUrl(String(p.photo)) }} style={s.idAvatar} />
                ) : (
                  <View style={[s.idAvatar, s.idAvatarEmpty]}>
                    <IconPerson />
                  </View>
                )}
              </ConfidenceRing>
              <View style={{ flex: 1, gap: 8 }}>
                <View style={s.nameRow}>
                  <Text style={[s.name, heading(lang, type.headingSm)]} numberOfLines={1}>{p.name || '—'}</Text>
                  <IconVerified size={18} />
                </View>
                {/* Процент и подпись — читаемым шрифтом на любом языке (точечный не читался). */}
                <Text style={s.conf} numberOfLines={1}>
                  <Text style={s.confNum}>{confidence}% </Text>
                  <Text style={s.confLabel}>{SUMMARY.confidence()}</Text>
                </Text>
              </View>
            </View>
          </GlassSurface>
        </View>

        <View style={s.cardShadow}>
          <GlassSurface tone="light" radius={16} style={s.card}>
            <View style={s.cardHead}>
              <Text style={[s.cardTitle, heading(lang, type.headingSm)]}>{SUMMARY.klealSummary()}</Text>
              <Text style={s.cardMeta}>{SUMMARY.updatedToday()}</Text>
            </View>
            <Text style={[s.para, !text && loading && s.paraWait]}>
              {text || (loading ? SUMMARY.composing() : fallback)}
            </Text>
            <GlassPill tone="brand" label={SUMMARY.viewAll()} busy={sending} onPress={toProfile} style={s.cardCta} />
          </GlassSurface>
        </View>

        {/*
          Плашки «План обновлён» больше нет (владелец, 26.09): голубая карточка с общими словами
          спорила с кнопкой «Готово» и ничего не сообщала о самом человеке.
        */}

        {err ? <Text style={s.err}>{err}</Text> : null}
        {/*
          Кнопка появляется ТОЛЬКО когда сервер назвал конкретные интересы. При обрыве связи её нет:
          там убирать нечего, там надо повторить.
        */}
        {rejected.length ? (
          <GlassPill tone="dark" label={SUMMARY.dropRejected()} disabled={sending} onPress={dropRejected} style={s.drop} />
        ) : null}
        {/*
          Дорога ко входу вместо тупика. Собранное никуда не девается: оно лежит в памяти телефона,
          и возобновление анкеты приведёт человека обратно сюда — на сводку, раз всё заполнено.
        */}
        {badName ? (
          <GlassPill tone="dark" label={SUMMARY.saveFixName()} onPress={() => router.navigate('/chat')} style={s.drop} />
        ) : null}
        {needsSignIn ? (
          <GlassPill tone="dark" label={SUMMARY.saveGoSignIn()} onPress={() => router.navigate('/auth')} style={s.drop} />
        ) : null}

        <View>
          <GlassPill tone="brand" label={SUMMARY.done()} busy={sending} onPress={finish} style={s.done} />
        </View>
      </ScrollView>

      {/* Композер здесь есть на кадре A.14: разговор не заканчивается на последнем шаге анкеты. */}
      <Composer bottomInset={insets.bottom} />
    </View>
  );
}

/**
 * КОЛЬЦО УВЕРЕННОСТИ вокруг аватара (кадр A.14: две окружности 64 — бежевая дорожка и коралловая
 * дуга). Дуга заполняется до процента уверенности при появлении.
 */
function ConfidenceRing({ pct, children }: { pct: number; children: React.ReactNode }) {
  const R = 31;
  const C = 2 * Math.PI * R;
  const reduced = useReducedMotion();
  const k = useSharedValue(0);
  useEffect(() => {
    const to = Math.max(0, Math.min(100, pct)) / 100;
    k.value = reduced ? to : withTiming(to, { duration: 700, easing: Easing.out(Easing.cubic) });
  }, [pct, k, reduced]);
  const arc = useAnimatedProps(() => ({ strokeDashoffset: C * (1 - k.value) }));
  return (
    <View style={s.ring}>
      <Svg width={64} height={64} style={StyleSheet.absoluteFill}>
        <Circle cx={32} cy={32} r={R} stroke="#E5DED4" strokeWidth={2} fill="none" />
        <ARing
          cx={32} cy={32} r={R} stroke="#F45D77" strokeWidth={2} fill="none" strokeLinecap="round"
          strokeDasharray={`${C} ${C}`} animatedProps={arc} transform="rotate(-90 32 32)"
        />
      </Svg>
      {children}
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.lg, height: 44 },
  headSide: { width: 84, flexDirection: 'row', alignItems: 'center' },
  headRight: { justifyContent: 'flex-end', gap: space.sm },
  headTitle: { flex: 1, textAlign: 'center', color: color.fg } as any,
  headPct: { ...type.num, color: color.muted } as any,
  track: {
    alignSelf: 'center', width: 100, height: 2, marginTop: 10,
    backgroundColor: 'rgba(255,255,255,0.67)', borderRadius: 999, overflow: 'hidden',
  },
  trackFill: { height: 2, backgroundColor: '#FF385C', borderRadius: 999 },

  // Запас снизу, чтобы последний блок не уезжал под композер.
  scroll: { paddingHorizontal: 20, paddingTop: space.lg, paddingBottom: 40, gap: space.md },
  cardShadow: {
    borderRadius: 16,
    shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 5 },
  },
  card: { padding: space.lg, gap: 14 },
  idRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  ring: { width: 64, height: 64, alignItems: 'center', justifyContent: 'center' },
  idAvatar: { width: 56, height: 56, borderRadius: 28 },
  idAvatarEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  name: { color: color.fg, flexShrink: 1 } as any,
  conf: { lineHeight: 16 } as any,
  confNum: { fontFamily: font.textSemibold, fontSize: 13, lineHeight: 16, color: color.fg, fontVariant: ['tabular-nums'] } as any,
  confLabel: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 16, color: color.muted, textTransform: 'uppercase', letterSpacing: 0.6 } as any,

  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: space.sm },
  cardTitle: { color: color.fg, flexShrink: 1 } as any,
  cardMeta: { fontFamily: font.text, fontSize: 11, lineHeight: 16, color: '#B4ABA0' } as any,
  para: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.muted } as any,
  /** Ожидание — бледнее: это ещё не описание, и путать его с описанием нельзя. */
  paraWait: { color: color.neutral400 } as any,
  cardCta: { height: 40, marginTop: 10 },


  err: { ...type.bodySmall, color: color.primary } as any,
  /** Единственное действие, которое на этом экране имеет смысл при отказе, — потому и заметное. */
  drop: { marginTop: space.xs },
  done: { height: 48, marginTop: space.xs },
});
