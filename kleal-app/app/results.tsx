/**
 * Выдача кандидатов — кадр O.12, окно приглашения — O.14.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор полей — в src/candidates.ts и src/intent.ts.
 *
 * Карточка по кадру: фото, имя с бейджем («Best match» у первой, «Match» у остальных), подзаголовок,
 * расстояние, чипы интересов, «Сводка Kleal» и кнопка «Пригласить». Чего на кадре есть, а в данных
 * нет — занятие и город — карточка не выдумывает: вместо занятия вайб или интересы, вместо города
 * километры (см. src/candidates.ts).
 *
 * Два места, где экран намеренно расходится с бордом, — из-за того, как отвечает матчинг:
 *
 *  1. Пустой выдачи почти не бывает. Когда по теме не совпал никто, сервер присылает ближайших
 *     людей с пометкой `fallback: "alternative"`. Заголовок «Лучшее совпадение» над такой пачкой —
 *     прямая неправда, поэтому шапка смотрит на пометки карточек, а не на их количество; бейджи
 *     мэтча на таких карточках не рисуются.
 *  2. Расширение — лестница §12, ступень за ступенью, каждая называется вслух. Какую ось расширять
 *     — решает клиент: только он помнит, что уже пробовали.
 *
 * Приглашение (O.14) — ЕДИНСТВЕННОЕ место, где выдача что-то отправляет. Окно называет последствия
 * словами с кадра: человек увидит интент и профиль. Отправка идёт в /api/agent/propose; сервер
 * держит одно открытое приглашение на пару — повторная отправка обновляет его, а не плодит копии.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, Modal, Alert,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { RESULTS, EXPAND_LADDER, ExpandAxis, axisExplain } from '../src/intent';
import { CANDS, PREFS, CAP, Cand, candSubtitle, candWhere, candSummary, isHidden } from '../src/candidates';
import { CHAT, ReqStatus, activeChatWith } from '../src/chat';
import { useInvites, inviteTo, openInvites, sendInvite, withdrawInvite } from '../src/invites';
import { isGroupIntent, groupTitleOf, GROUP } from '../src/groups';
import {
  useGroupSession, groupStatusFor, groupCounters, groupPending, groupId,
  sendGroupInvite, cancelGroupInvite,
} from '../src/ginvites';
import { useLang, T, getLang } from '../src/i18n';
import { takeResults, patchResults, setCandidate } from '../src/results-store';
import { mediaUrl, agent } from '../src/api';
import { IconPerson, IconPin, IconCalendar } from '../src/components/icons';
import { AgeRange } from '../src/components/AgeRange';
import Slider from '@react-native-community/slider';
import { SEXES, sexLabel } from '../src/onboarding';
import { BottomNav } from '../src/components/BottomNav';
import { Sheet } from '../src/components/Sheet';
import { color, radius as rad, space, type } from '../src/theme';
import { interestLabels } from '../src/interest-label';

const ru = () => getLang() === 'ru';

/** Черновик условий листа O.11a. Живёт отдельно от интента: «Отмена» не должна ничего менять. */
type Prefs = { sex: string; anyAge: boolean; minAge: number; maxAge: number; radiusKm: number };

/**
 * Условия из интента — как они есть СЕЙЧАС.
 *
 * `anyAge` считается по факту наличия рамки, а не по её значению. Мастер интента кладёт 18–28
 * всегда (кадр O.08 нарисован с этими числами), а сервер трактует любое minAge как жёсткий гейт:
 * «до 28» — и никого старше, включая тех, у кого возраст просто не указан. Проверено на стенде —
 * тот же запрос с рамкой отдаёт 7 человек, без рамки 8, и первым идёт тот, кого рамка отсекала.
 * Поэтому у возраста есть «Любой», и он снимает поля из интента, а не расставляет их пошире.
 */
function prefsFromIntent(it: any): Prefs {
  const mn = Number(it?.minAge) || 0;
  const mx = Number(it?.maxAge) || 0;
  return {
    sex: String(it?.gender || it?.sex || 'Any'),
    anyAge: !(mn || mx),
    minAge: mn || 18,
    maxAge: mx || 45,
    radiusKm: Number(it?.radiusKm) || 15,
  };
}

export default function Results() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const win = useWindowDimensions();
  // Читаем один раз: последующие render'ы не должны затирать уже расширенную выдачу исходной.
  const initial = useMemo(() => takeResults(), []);

  const [intent, setIntent] = useState<any>(initial?.intent || {});
  const [cands, setCands] = useState<Cand[]>(initial?.candidates || []);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  /** Следующая непройденная ступень лестницы. */
  const [rung, setRung] = useState(0);
  /**
   * Сколько человек показано и есть ли продолжение.
   *
   * Восемь — первая страница, а не весь ответ. `hasMore` приходит с сервера: без него кнопка
   * жила бы вечно и однажды снова нажималась бы впустую — ровно то, из-за чего это и правится.
   * Изначально `undefined`: выдача пришла со старого вызова, без `limit`, и про продолжение мы
   * ещё ничего не знаем — но раз пришло ровно восемь, спросить стоит.
   */
  const [limit, setLimit] = useState((initial?.candidates || []).length || 8);
  const [hasMore, setHasMore] = useState<boolean | undefined>(undefined);
  /** Кандидат, для которого открыто окно O.14. null — окна нет. */
  const [asking, setAsking] = useState<Cand | null>(null);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState('');
  /** Окно бесплатного тарифа (O.17): с кем уже идёт переписка, когда пробуешь открыть вторую. */
  const [busyWith, setBusyWith] = useState('');
  /** Завершение идёт на сервер — на это время кнопка гаснет, чтобы не нажали дважды. */
  const [ending, setEnding] = useState(false);
  /** С кем реально идёт переписка — по сообщениям, а не по принятым приглашениям (см. activeChatWith). */
  const [chatting, setChatting] = useState('');
  /**
   * Лист O.11a «Изменить условия поиска». Открывается сам, когда точных совпадений нет: борд
   * предлагает расширение сразу, а не прячет его за кнопкой. Черновик условий живёт отдельно от
   * интента — «Отмена» не должна оставлять полурасширенный запрос.
   */
  const [prefsOpen, setPrefsOpen] = useState(() => {
    const cs = initial?.candidates || [];
    // «Точных совпадений нет» на этом сервере выглядит не как ноль карточек, а как пачка замен
    // с пометкой fallback: он почти никогда не возвращает пусто. Лист предлагается в обоих случаях.
    return cs.length === 0 || cs.every((c: any) => !!c.fallback);
  });
  const [prefs, setPrefs] = useState<Prefs>(() => prefsFromIntent(initial?.intent));
  const [reSearching, setReSearching] = useState(false);

  /**
   * Открыть лист — всегда с ЖИВОГО интента.
   *
   * Черновик читался один раз при монтировании экрана. Значит «Отмена» и повторное открытие
   * возвращали брошенные значения, а ступени лестницы §12 (удвоенный радиус) лист вовсе не видел
   * и молча откатывал бы их обратно первым же «Начать поиск».
   */
  const openPrefs = () => { setPrefs(prefsFromIntent(intent)); setPrefsOpen(true); };

  const profile = initial?.profile || {};
  const self = String(profile?.name || '');
  /**
   * Групповой режим той же выдачи — кадры GR.14–GR.17. Экран один, потому что на борде это один
   * и тот же список карточек; меняются шапка, строка регламента и что делает «Пригласить».
   */
  const gmode = isGroupIntent(initial?.intent);
  /**
   * Состояние приглашений — общее с карточкой кандидата (src/invites.ts). Здесь только подписка:
   * отправка, отзыв и потолок живут там, потому что кнопка «Пригласить» есть на обоих экранах.
   * В групповом режиме то же самое делает сессия набора (src/ginvites.ts).
   */
  useInvites(self);
  useGroupSession(self, gmode);

  // Радиус нечего удваивать, когда встреча онлайн, — эта ступень для такого интента бессмысленна.
  const ladder: ExpandAxis[] = useMemo(
    () => EXPAND_LADDER.filter((a) => !(a === 'radius' && intent?.mode === 'online')),
    [intent?.mode]
  );

  /** Карточки-заменители: тема не совпала ни у кого, показаны просто ближайшие подходящие люди. */
  const onlyFallback = cands.length > 0 && cands.every((c) => !!(c as any).fallback);
  const canWiden = rung < ladder.length && (cands.length === 0 || onlyFallback);

  /**
   * Показать ещё — ПРОДОЛЖЕНИЕ того же ранжирования, а не другой запрос.
   *
   * Список запрашивается целиком с бо́льшим пределом, а не дозагружается кусками: ранжирование
   * детерминировано, первые люди остаются на своих местах (проверено на живом сервере), а
   * склейка страниц дала бы дубликаты при малейшем изменении хранилища между запросами.
   */
  const showMore = async () => {
    if (busy) return;
    const next = limit + 8;
    setBusy(true);
    setNote('');
    try {
      // Имя смотрящего — из переданного профиля: сервер по нему исключает человека из его же
      // выдачи, и без `self` он нашёл бы сам себя.
      const self = String((profile as any)?.name || '');
      const r: any = await agent.match(intent, profile, { self, uid: self }, undefined, next);
      const found: Cand[] = (r && r.candidates) || [];
      if (found.length > cands.length) {
        setCands(found);
        setLimit(next);
        patchResults({ candidates: found });
      }
      // Ответ сервера, а не догадка экрана: он один знает, остался ли кто-то за срезом.
      setHasMore(r?.has_more === true);
      if (found.length <= cands.length) setNote(RESULTS.allShown(cands.length));
    } catch {
      setNote(T('Не получилось загрузить ещё. Попробуй ещё раз.', 'Could not load more. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  const widen = async () => {
    const axis = ladder[rung];
    if (!axis) return;
    setBusy(true);
    setNote('');
    try {
      const r: any = await agent.expand(intent, profile, axis);
      const next: Cand[] = (r && r.candidates) || [];
      const km = axis === 'radius' ? (intent?.radiusKm || 15) * 2 : undefined;
      setRung(rung + 1);
      if (next.length) {
        setCands(next);
        // Интент двигаем сами: сервер возвращает только карточки, а следующая ступень должна
        // считаться от уже расширенного запроса, иначе радиус удваивался бы от исходного вечно.
        setIntent((prev: any) => {
          const next = {
            ...prev,
            ...(axis === 'adjacent' ? { adjacentAllowed: true } : {}),
            ...(axis === 'parent' ? { broadAllowed: true } : {}),
            ...(axis === 'exactness' ? { exactMatchRequired: false } : {}),
            ...(axis === 'radius' ? { radiusKm: km } : {}),
          };
          // Карточка кандидата берёт интент из того же хранилища — приглашение с неё должно уехать
          // с расширенным запросом, а не с исходным (см. patchResults).
          patchResults({ intent: next });
          return next;
        });
        setNote(`${axisExplain(axis, km)} ${RESULTS.found(next.length)}`);
      } else {
        setNote(`${axisExplain(axis, km)} ${RESULTS.empty()}`);
      }
    } catch {
      setNote(T('Не получилось расширить. Попробуй ещё раз.', 'Could not widen. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  /** MSG.22: открытые приглашения прямо сейчас — по серверному outbox, а не по памяти экрана. */
  const pendingOut = openInvites();
  const [capOpen, setCapOpen] = useState(false);

  /** Отправка приглашения — только из окна O.14/GR.16, никогда прямо с кнопки карточки. */
  const send = async () => {
    const to = String(asking?.name || '');
    if (!to || sending) return;
    setSending(true);
    setSendErr('');
    try {
      if (gmode) {
        // GR.16: первое приглашение по пути создаёт группу (лениво — см. шапку ginvites.ts).
        const r = await sendGroupInvite(self, to, intent, groupTitleOf(intent, initial?.query));
        if (r.capped) { setAsking(null); setCapOpen(true); return; }   // GR.15
        if (r.full) { setSendErr(GROUP.full()); return; }
        if (!r.ok) throw new Error(r.error || 'invite failed');
        setAsking(null);
        return;
      }
      const r = await sendInvite(self, to, intent);
      // MSG.22: потолок открытых приглашений. Правило клиентское — см. CAP в candidates.ts.
      if (r.capped) { setAsking(null); setCapOpen(true); return; }
      if (!r.ok) throw new Error(r.error || 'propose failed');
      setAsking(null);
    } catch {
      setSendErr(gmode ? GROUP.sendFailed() : CANDS.inviteFailed());
    } finally {
      setSending(false);
    }
  };

  /** O.15/GR.17 «Cancel»: отозвать НЕотвеченное приглашение. Ответившее — скажет сервер. */
  const cancelInvite = async (to: string) => {
    if (gmode) {
      if (!(await cancelGroupInvite(self, to))) setNote(CANDS.cancelFailed());
      return;
    }
    // Исход называется своим именем: «поздно» — не то же самое, что «не получилось».
    const r = await withdrawInvite(self, to);
    if (!r.ok) setNote(r.resolved ? CANDS.cancelTooLate() : CANDS.cancelFailed());
  };

  /** «Начать поиск» из листа O.11a: тот же /api/agent/match, но с условиями, которые человек ослабил сам. */
  const reSearch = async () => {
    if (reSearching) return;
    setReSearching(true);
    setNote('');
    try {
      const next: any = { ...intent };
      // «Любой» — это отсутствие ключей, а не 18–80: сервер и на 18 отсекает всех, у кого возраст
      // не заполнен («age unknown»), так что раздвинуть рамку до упора и снять её — разные вещи.
      if (prefs.anyAge) { delete next.minAge; delete next.maxAge; }
      else { next.minAge = prefs.minAge; next.maxAge = prefs.maxAge; }
      // Оба ключа: гейт читает `gender || sex`, и убрать один — значит не убрать ничего.
      if (prefs.sex && prefs.sex !== 'Any') { next.sex = prefs.sex; next.gender = prefs.sex; }
      else { delete next.sex; delete next.gender; }
      if (intent?.mode !== 'online') next.radiusKm = prefs.radiusKm;
      const r: any = await agent.match(next, profile, {
        self, uid: self, city: profile?.city,
      });
      setIntent(r?.intent || next);
      patchResults({ intent: r?.intent || next });
      const found: Cand[] = (r?.candidates || []) as Cand[];
      setCands(found);
      setRung(0);                      // условия сменились — лестница §12 начинается заново
      setPrefsOpen(false);
      // Лист закрывается, список меняется — и раньше нигде не говорилось, ОТ ЧЕГО он изменился.
      // Ступени лестницы называют себя вслух; этот путь должен вести себя так же.
      const conds = [
        prefs.sex && prefs.sex !== 'Any' ? sexLabel(prefs.sex).toLowerCase() : PREFS.anySex(),
        prefs.anyAge ? PREFS.ageAny() : PREFS.ageBand(prefs.minAge, prefs.maxAge),
        ...(intent?.mode !== 'online' ? [PREFS.distVal(prefs.radiusKm)] : []),
      ].join(', ');
      setNote(`${PREFS.applied(conds)} ${found.length ? RESULTS.found(found.length) : RESULTS.empty()}`);
    } catch {
      setNote(T('Не получилось поискать. Попробуй ещё раз.', 'The search failed. Try again.'));
    } finally {
      setReSearching(false);
    }
  };

  /** С кем реально идёт переписка — правило одного чата (O.17) считается по сообщениям. */
  const loadChats = useCallback(async () => {
    if (!self) return;
    try {
      const th: any = await agent.threads(self).catch(() => ({ threads: [] }));
      setChatting(activeChatWith((th?.threads || []) as any[]));
      // Заодно блокировки: возвращаясь в выдачу после перезапуска, человек не должен снова
      // видеть того, кого заблокировал.
      const sf: any = await agent.safety(self).catch(() => ({ blocked: [] }));
      setBlocked(((sf?.blocked || []) as any[]).map((x) => String(x).trim().toLowerCase()));
    } catch {
      /* тихо: фоновая дотяжка состояний */
    }
  }, [self]);

  useEffect(() => { loadChats(); }, [loadChats]);
  useEffect(() => {
    const id = setInterval(loadChats, 6000);
    return () => clearInterval(id);
  }, [loadChats]);

  /**
   * Открыть переписку. Правило бесплатного тарифа с кадра O.17 — один живой чат за раз — живёт
   * ЗДЕСЬ, потому что на сервере его нет: он позволяет писать любому, кто принял приглашение.
   * Когда тариф появится на сервере, проверку надо перенести туда — иначе она обходится любым
   * другим клиентом.
   */
  const openChat = (name: string, photo?: string) => {
    // В группе личной переписки с человеком НЕТ — это обещано ещё в шите приглашения (GR.16).
    // Открывается общая комната: она и есть разговор. Потолок «один чат за раз» сюда тоже не
    // относится — он про 1:1.
    if (gmode) {
      const gid = groupId();
      if (gid) router.navigate({ pathname: '/group', params: { gid } });
      return;
    }
    const active = chatting;
    if (active && active.toLowerCase() !== name.toLowerCase()) {
      setBusyWith(active);
      return;
    }
    router.navigate({
      pathname: '/conversation',
      params: { who: name, title: String(intent?.title || (intent?.topics || []).join(', ') || ''), photo: photo || '' },
    });
  };

  /**
   * Кого в этой выдаче показывать нельзя.
   *
   * Два источника, и оба нужны. `isHidden` — «не интересно» и только что нажатая блокировка: она
   * действует сразу, не дожидаясь ответа сервера. `blocked` — список с сервера: он переживает
   * перезапуск приложения, а память экрана — нет.
   */
  const [blocked, setBlocked] = useState<string[]>([]);
  const visible = useMemo(
    () => cands.filter((c) => {
      const n = String(c.name || '');
      return n && !isHidden(n) && !blocked.includes(n.trim().toLowerCase());
    }),
    [cands, blocked],
  );

  /** O.16 «Убрать»: карточка уходит с экрана. Отклонённое приглашение сервер уже закрыл сам. */
  const removeCard = (name: string) => {
    setCands((prev) => prev.filter((c) => String(c.name || '') !== name));
  };

  const openProfile = (c: Cand) => {
    setCandidate(c);
    router.navigate('/candidate');
  };

  // Экран открыт напрямую — обновлением страницы или по ссылке. Выдача живёт один переход, и
  // выдумывать её задним числом нечем; честнее сказать это и предложить поискать заново.
  if (!initial) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
            <Text style={s.backIcon}>‹</Text>
          </Pressable>
          <Text style={s.headTitle}>{T('Выдача устарела', 'These results are gone')}</Text>
        </View>
        <View style={s.scroll}>
          <Text style={s.lead}>
            {T('Результаты поиска живут до перезагрузки. Давай поищем заново.',
               'Search results only live until the page reloads. Let’s search again.')}
          </Text>
          {/* Новый поиск начинается там же, где и любой другой: с темы, а не с формата. */}
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => { router.dismissTo('/home'); router.navigate('/create'); }}>
            <Text style={s.ctaText}>{T('Новый поиск', 'New search')}</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const title = gmode ? (groupId() ? GROUP.invitesSent() : GROUP.header())
              : cands.length === 0 ? RESULTS.empty()
              : onlyFallback ? T('Прямых совпадений нет', 'No direct matches')
              : RESULTS.best();
  /** Групповые строки под шапкой: регламент до первого приглашения (GR.14), счётчик после (GR.17). */
  const gc = groupCounters();
  const gline = !gmode ? ''
    : groupId() ? GROUP.counter(gc.joined, gc.max, gc.open, gc.min)
    : GROUP.regime(gc.min, gc.max, gc.cap);

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
          <Text style={s.backIcon}>‹</Text>
        </Pressable>
        {/* Красная точка + заголовок — шапка кадра O.12. */}
        <View style={s.dot} />
        <Text style={s.headTitle}>{title}</Text>
      </View>

      <ScrollView contentContainerStyle={[s.scroll, { paddingBottom: 120 }]}>
        {gline ? <Text style={s.gline}>{gline}</Text> : null}
        {onlyFallback ? (
          <View style={{ gap: space.sm }}>
            <Text style={s.lead}>
              {T('Никто не занимается ровно этим. Вот кто рядом и с кем это может получиться.',
                 'Nobody is doing exactly that. Here are people nearby it could work with.')}
            </Text>
            <Pressable accessibilityRole="button" style={s.prefsBtn} onPress={openPrefs}>
              <Text style={s.prefsBtnText}>{PREFS.title()}</Text>
            </Pressable>
          </View>
        ) : null}

        {note ? <Text style={s.note}>{note}</Text> : null}

        {cands.length === 0 ? (
          <View style={s.noMatch}>
            <View style={s.noMatchArt}><IconPerson size={34} /></View>
            <Text style={s.noMatchTitle}>{PREFS.noMatches()}</Text>
            <Text style={s.lead}>{RESULTS.emptyNote()}</Text>
            <Pressable accessibilityRole="button" style={s.cta} onPress={openPrefs}>
              <Text style={s.ctaText}>{PREFS.title()}</Text>
            </Pressable>
          </View>
        ) : null}

        {visible.map((c, i) => (
          <CandCard
            key={(c.name || '') + i}
            c={c}
            badge={(c as any).fallback ? '' : i === 0 ? CANDS.bestBadge() : CANDS.matchBadge()}
            status={gmode ? groupStatusFor(String(c.name || '')) : inviteTo(String(c.name || ''))?.status}
            onOpen={() => openProfile(c)}
            onInvite={() => { setSendErr(''); setAsking(c); }}
            onCancel={() => cancelInvite(String(c.name || ''))}
            onOpenChat={() => openChat(String(c.name || ''), c.photo)}
            onRemove={() => removeCard(String(c.name || ''))}
          />
        ))}

        {/* «Ещё» показывается, пока сервер не сказал, что это все. Оно НЕ заменяет расширение:
            то ослабляет запрос и объясняется словами, это просто продолжает список. */}
        {cands.length > 0 && hasMore !== false ? (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy }}
            style={[s.moreBtn, busy && { opacity: 0.6 }]}
            onPress={busy ? undefined : showMore}
          >
            {busy ? <ActivityIndicator color={color.fg} />
                  : <Text style={s.moreText}>{RESULTS.more()}</Text>}
          </Pressable>
        ) : null}

        {canWiden ? (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ busy }}
            style={[s.cta, busy && { opacity: 0.6 }]}
            onPress={busy ? undefined : widen}
          >
            {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{RESULTS.widen()}</Text>}
          </Pressable>
        ) : null}

        {rung >= ladder.length && (cands.length === 0 || onlyFallback) ? (
          <Text style={s.note}>{RESULTS.exhausted()}</Text>
        ) : null}
      </ScrollView>

      {/* Панель на выдаче есть на кадре O.12. */}
      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav />
      </View>

      <PrefsSheet
        open={prefsOpen}
        prefs={prefs}
        setPrefs={setPrefs}
        offline={intent?.mode !== 'online'}
        busy={reSearching}
        onStart={reSearch}
        onClose={() => setPrefsOpen(false)}
        bottomInset={insets.bottom}
        // Тело листа не выше половины экрана: остальное — шапка, две кнопки и вырез снизу.
        maxBody={Math.round(win.height * 0.46)}
      />

      {/* Окно бесплатного тарифа — кадр O.17. Текст с кадра; ограничение клиентское, см. openChat. */}
      <Sheet visible={!!busyWith} onClose={() => setBusyWith('')} title={CHAT.busyTitle(busyWith)}>
        <Text style={s.sheetBody}>{CHAT.busyBody()}</Text>
        {/* Тарифа в продукте нет — кнопка честно выключена, как везде в каркасе. */}
        <View style={[s.sheetSend, { opacity: 0.45 }]}>
          <Text style={s.sheetSendText}>{CHAT.getPlus()}</Text>
        </View>
        <Text style={s.plusPrice}>{CHAT.plusPrice()}</Text>
        {/*
          Кнопка называется «Закончить разговор с N» — и заканчивает его.
          Раньше она просто открывала переписку с этим человеком: слово «закончить» вело туда, где
          завершение спрятано за ⋮, и передать намерение туда было нечем. Человек нажимал
          «закончить» и оказывался в том же чате, из которого хотел выйти.

          Спрашиваем перед этим: разговор закрывается для ДВОИХ, и второму об этом скажут.
        */}
        <Pressable
          accessibilityRole="button"
          style={[s.sheetNot, ending && { opacity: 0.6 }]}
          disabled={ending}
          onPress={() => {
            const who = busyWith;
            const go = async () => {
              setEnding(true);
              try {
                await agent.threadEnd(self, who);
                // Список тредов перечитываем сразу: слот освобождает не наше намерение, а
                // системная строка на сервере, и до неё окно продолжало бы висеть.
                await loadChats();
                setBusyWith('');
              } catch {
                setSendErr(CHAT.endFailed());
              } finally {
                setEnding(false);
              }
            };
            Alert.alert(CHAT.endAskTitle(who), CHAT.endAskBody(), [
              { text: CHAT.endAskNo(), style: 'cancel' },
              { text: CHAT.endAskYes(), style: 'destructive', onPress: go },
            ]);
          }}
        >
          <Text style={s.sheetNotText}>{CHAT.endChatWith(busyWith)}</Text>
        </Pressable>
      </Sheet>

      {/* Потолок открытых приглашений — кадр MSG.22, в групповом режиме GR.15. Отзыв по id сервера. */}
      <Sheet visible={capOpen} onClose={() => setCapOpen(false)} title={gmode ? GROUP.capTitle() : CAP.title(pendingOut.length)}>
        <Text style={s.sheetBody}>{gmode ? GROUP.capBody() : CAP.note()}</Text>
        {/* Тарифа в продукте нет — кнопка честно выключена, как в O.17. GR.15 предлагает Plus
            тем же местом, и он выключен по той же причине. */}
        <View style={[s.sheetSend, { opacity: 0.45 }]}>
          <Text style={s.sheetSendText}>{CHAT.getPlus()}</Text>
        </View>
        {/* На GR.15 цены нет: canvas только объясняет лимит и даёт два выхода. */}
        {!gmode ? <Text style={s.plusPrice}>{CHAT.plusPrice()}</Text> : null}
        {gmode ? (
          /* GR.15 возвращает к списку: у каждой открытой строки там уже есть своя Cancel. */
          <Pressable accessibilityRole="button" style={s.sheetNot} onPress={() => setCapOpen(false)}>
            <Text style={s.sheetNotText}>{CAP.cancelOne()}</Text>
          </Pressable>
        ) : (
          /* В 1:1 MSG.22 сохраняет быстрый отзыв прямо из листа. */
          pendingOut.map((r) => (
            <View key={r.id || r.to} style={s.capRow}>
              <Text style={s.capName} numberOfLines={1}>{r.to}</Text>
              <Pressable
                accessibilityRole="button"
                style={s.capBtn}
                onPress={() => withdrawInvite(self, r.to)}
              >
                <Text style={s.capBtnText}>{CAP.withdraw()}</Text>
              </Pressable>
            </View>
          ))
        )}
      </Sheet>

      <InviteSheet
        cand={asking}
        sending={sending}
        err={sendErr}
        group={gmode}
        onSend={send}
        onClose={() => setAsking(null)}
        bottomInset={insets.bottom}
      />
    </View>
  );
}

/** Карточка кандидата — кадр O.12. Нажатие на тело карточки открывает полный профиль (O.13). */
function CandCard({
  c, badge, status, onOpen, onInvite, onCancel, onOpenChat, onRemove,
}: {
  c: Cand;
  badge: string;
  /** Состояние приглашения из общего стора; в групповом режиме добавляется 'joined'. */
  status?: ReqStatus | 'joined';
  onOpen: () => void;
  onInvite: () => void;
  onCancel: () => void;
  onOpenChat: () => void;
  onRemove: () => void;
}) {
  const readiness = (ru() ? c.readiness_ru : c.readiness_en) || '';
  const where = candWhere(c);
  const summary = candSummary(c, ru());
  /** Ссылка на фото есть, а файла нет: <Image> рисует пустоту — не кружок, а дыру в карточке. */
  const [broken, setBroken] = useState(false);

  return (
    <View style={s.card}>
      <Pressable accessibilityRole="button" onPress={onOpen} style={({ pressed }) => [pressed && { opacity: 0.92 }]}>
        <View style={s.cardTop}>
          {c.photo && !broken ? (
            <Image source={{ uri: mediaUrl(String(c.photo)) }} style={s.av} onError={() => setBroken(true)} />
          ) : (
            <View style={[s.av, s.avEmpty]}><IconPerson /></View>
          )}
          <View style={{ flex: 1 }}>
            <View style={s.nameRow}>
              <Text style={s.name} numberOfLines={1}>{c.name}{c.age ? `, ${c.age}` : ''}</Text>
              {badge ? (
                <View style={s.badge}><Text style={s.badgeText}>{badge}</Text></View>
              ) : null}
            </View>
            <Text style={s.subtitle} numberOfLines={1}>{candSubtitle(c, ru())}</Text>
            {where ? (
              <View style={s.whereRow}>
                <IconPin size={13} c={color.muted} />
                <Text style={s.meta}>{where}</Text>
              </View>
            ) : null}
          </View>
        </View>

        {(c.interests || []).length ? (
          <View style={s.tags}>
            {interestLabels(c.interests).slice(0, 3).map((t, i) => (
              <View key={t + i} style={s.tag}><Text style={s.tagText}>{t}</Text></View>
            ))}
          </View>
        ) : null}

        {summary ? (
          <View style={s.sumBox}>
            <Text style={s.sumLabel}>{CANDS.summaryLabel()}</Text>
            <Text style={s.sumText}>{summary}</Text>
          </View>
        ) : null}

        {/*
          Доступность — не украшение: человек «в тихих часах» не ответит сейчас, и лучше знать
          заранее. Слово «связаться» разводит два разных факта — его намерение встречаться и то,
          дойдёт ли сообщение прямо сейчас, — которые иначе читаются как противоречие.
        */}
        {readiness ? (
          <Text style={s.readiness}>{T('Связаться: ', 'Reach out: ')}{readiness}</Text>
        ) : null}
      </Pressable>

      {/*
        Четыре состояния приглашения, и каждое видно на своём кадре:
          отклонили (O.16)  — «Отклонено» и «Убрать»;
          приняли   (O.17)  — «Открыть чат» и «Отменить»;
          отправлено (O.15) — «Отправлено» и «Отменить»;
          ничего            — просто «Пригласить».
      */}
      {status === 'joined' ? (
        /* GR.17: человек уже в группе. Отменить нечего — выход из состава это его решение,
           а удаление организатором — отдельный флоу с причиной (GR.51), не кнопка на карточке.
           Зато отсюда открывается сама комната: она и есть разговор с этим человеком. */
        <View style={s.invitedRow}>
          <View style={[s.invite, s.joinedPill]}>
            <Text style={[s.inviteText, { color: color.successText }]}>✓  {GROUP.joined()}</Text>
          </View>
          <Pressable accessibilityRole="button" style={[s.invite, s.cancelPill]} onPress={onOpenChat}>
            <Text style={s.inviteText}>{CHAT.openChat()}</Text>
          </Pressable>
        </View>
      ) : status === 'expired' || status === 'withdrawn' ? (
        /* O.14a: приглашение простояло весь срок и не дождалось ответа — это НЕ отказ, и говорить
           о нём надо иначе. Раньше CandCard разбирала только joined/declined/accepted/pending, и
           на истёкшем молча рисовала обычное «Пригласить»: человек не понимал, ушло ли его
           приглашение вообще. `withdrawn` сюда же — так закрываются соседи после чужого «да». */
        <View style={s.invitedRow}>
          <View style={[s.invite, s.invitedPill]}>
            <Text style={[s.inviteText, { color: color.muted }]}>⏳  {CHAT.expired()}</Text>
          </View>
          {/*
            Кадр O.14a даёт здесь «Invite again», а не «Убрать». И это разные вещи: молчание —
            не отказ, человек мог просто не открыть приложение. «Убрать» уносило карточку с
            экрана, и позвать снова становилось нечем — из выдачи человек исчезал совсем.
            Сервер повторное приглашение принимает: истёкшая заявка не мешает завести новую.
          */}
          <Pressable accessibilityRole="button" style={[s.invite, s.cancelPill]} onPress={onInvite}>
            <Text style={s.inviteText}>{CHAT.inviteAgain()}</Text>
          </Pressable>
        </View>
      ) : status === 'declined' ? (
        <View style={s.invitedRow}>
          <View style={[s.invite, s.invitedPill]}>
            <Text style={[s.inviteText, { color: color.muted }]}>⊘  {CHAT.declined()}</Text>
          </View>
          <Pressable accessibilityRole="button" style={[s.invite, s.cancelPill]} onPress={onRemove}>
            <Text style={s.inviteText}>{CHAT.remove()}</Text>
          </Pressable>
        </View>
      ) : status === 'accepted' ? (
        <View style={s.invitedRow}>
          <Pressable accessibilityRole="button" style={[s.invite, { flex: 1 }]} onPress={onOpenChat}>
            <Text style={s.inviteText}>{CHAT.openChat()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={[s.invite, s.cancelPill]} onPress={onCancel}>
            <Text style={s.inviteText}>{CANDS.cancel()}</Text>
          </Pressable>
        </View>
      ) : status === 'pending' ? (
        <View style={s.invitedRow}>
          <View style={[s.invite, s.invitedPill]}>
            <Text style={[s.inviteText, { color: color.fg }]}>{CANDS.invitedShort()}</Text>
          </View>
          <Pressable accessibilityRole="button" style={[s.invite, s.cancelPill]} onPress={onCancel}>
            <Text style={s.inviteText}>{CANDS.cancel()}</Text>
          </Pressable>
        </View>
      ) : (
        <Pressable accessibilityRole="button" style={s.invite} onPress={onInvite}>
          <Text style={s.inviteText}>{CANDS.invite()}</Text>
        </Pressable>
      )}
    </View>
  );
}

/**
 * Лист O.11a «Изменить условия поиска»: пол, возраст диапазоном и — у офлайн-интента — расстояние.
 * «Начать поиск» перезапускает матчинг с условиями, которые человек ослабил сам.
 *
 * Три вещи, которых тут раньше не хватало и без которых лист не делал того, ради чего открывается:
 *
 *  — «Любой» у возраста. Единственный способ СНЯТЬ рамку, а не подвинуть (см. prefsFromIntent).
 *  — Расстояние. Экран за листом обещает расширение «по расстоянию», а в самом листе этой ручки
 *    не было — только в лестнице, которая удваивает радиус вслепую.
 *  — Прокрутка. Лист прибит к низу и растёт вверх; на невысоком экране заголовок и «✕» уезжали
 *    за верхнюю кромку, и закрыть его можно было только по затемнению.
 *
 * Ползунка «гибко по времени» больше нет: матчинг `timeFlexHours` не читает — ни в гейтах, ни в
 * ранжировании, ни в лестнице §12. Ручка, которая ничего не меняет, хуже отсутствующей.
 */
function PrefsSheet({
  open, prefs, setPrefs, offline, busy, onStart, onClose, bottomInset, maxBody,
}: {
  open: boolean;
  prefs: Prefs;
  setPrefs: React.Dispatch<React.SetStateAction<Prefs>>;
  /** Офлайн-интент — только у него расстояние что-то значит. */
  offline: boolean;
  busy: boolean;
  onStart: () => void;
  onClose: () => void;
  bottomInset: number;
  maxBody: number;
}) {
  return (
    <Sheet visible={open} onClose={onClose} title={PREFS.title()}>
      <View style={s.grabber} />
      <Text style={s.sheetBody}>{PREFS.lead()}</Text>

      <ScrollView
        style={{ maxHeight: maxBody }}
        contentContainerStyle={s.prefsBody}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <View style={s.prefLabelRow}>
          <IconPerson size={16} c={color.fg} />
          <Text style={s.prefLabel}>{PREFS.sex()}</Text>
        </View>
        <View style={s.prefChips}>
          {SEXES.map(([k]) => (
            <Pressable
              key={k}
              accessibilityRole="button"
              accessibilityState={{ selected: prefs.sex === k }}
              onPress={() => setPrefs((p) => ({ ...p, sex: k }))}
              style={[s.prefChip, prefs.sex === k && s.prefChipOn]}
            >
              <Text style={[s.prefChipText, prefs.sex === k && { color: color.onPrimary }]}>{sexLabel(k)}</Text>
            </Pressable>
          ))}
        </View>

        <View style={s.prefHeadRow}>
          <View style={s.prefLabelRow}>
            <IconCalendar size={16} c={color.fg} />
            <Text style={s.prefLabel}>{PREFS.age()}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: prefs.anyAge }}
            onPress={() => setPrefs((p) => ({ ...p, anyAge: !p.anyAge }))}
            style={[s.miniChip, prefs.anyAge && s.prefChipOn]}
            hitSlop={6}
          >
            <Text style={[s.miniChipText, prefs.anyAge && { color: color.onPrimary }]}>{PREFS.anyAge()}</Text>
          </Pressable>
        </View>
        {prefs.anyAge ? null : (
          <AgeRange
            min={prefs.minAge}
            max={prefs.maxAge}
            onChange={(lo, hi) => setPrefs((p) => ({ ...p, minAge: lo, maxAge: hi }))}
          />
        )}

        {offline ? (
          <>
            <View style={s.prefHeadRow}>
              <View style={s.prefLabelRow}>
                <IconPin size={16} c={color.fg} />
                <Text style={s.prefLabel}>{PREFS.dist()}</Text>
              </View>
              <Text style={s.prefVal}>{PREFS.distVal(prefs.radiusKm)}</Text>
            </View>
            <Slider
              minimumValue={1}
              maximumValue={100}
              step={1}
              value={prefs.radiusKm}
              onValueChange={(v) => setPrefs((p) => ({ ...p, radiusKm: Math.round(v) }))}
              minimumTrackTintColor={color.primary}
              maximumTrackTintColor={color.neutral100}
              thumbTintColor={color.primary}
              accessibilityLabel={PREFS.dist()}
            />
          </>
        ) : null}
      </ScrollView>

      <Pressable
        accessibilityRole="button"
        accessibilityState={{ busy }}
        style={[s.sheetSend, busy && { opacity: 0.7 }]}
        onPress={busy ? undefined : onStart}
      >
        {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.sheetSendText}>{PREFS.start()}</Text>}
      </Pressable>
      {/* «Отмена» тише «Начать поиск»: чёрной заливкой она перевешивала главное действие. */}
      <Pressable accessibilityRole="button" style={s.sheetGhost} onPress={onClose}>
        <Text style={s.sheetGhostText}>{PREFS.cancel()}</Text>
      </Pressable>
    </Sheet>
  );
}

/** Окно O.14: последствия названы словами, отправка — только отсюда. */
function InviteSheet({
  cand, sending, err, group, onSend, onClose, bottomInset,
}: {
  cand: Cand | null;
  sending: boolean;
  err: string;
  /** Групповой режим: та же механика, копия кадра GR.16 вместо O.14. */
  group?: boolean;
  onSend: () => void;
  onClose: () => void;
  bottomInset: number;
}) {
  const name = String(cand?.name || '');
  return (
    <Sheet visible={!!cand} onClose={onClose} title={group ? GROUP.askTitle(name) : CANDS.sheetTitle(name)}>
      <Text style={s.sheetBody}>{group ? GROUP.askBody(name) : CANDS.sheetBody(name)}</Text>
      {err ? <Text style={s.note}>{err}</Text> : null}
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ busy: sending }}
        style={s.sheetSend}
        onPress={sending ? undefined : onSend}
      >
        {sending ? <ActivityIndicator color={color.onPrimary} />
                 : <Text style={s.sheetSendText}>{group ? GROUP.askSend() : CANDS.send()}</Text>}
      </Pressable>
      <Pressable accessibilityRole="button" style={s.sheetNot} onPress={onClose}>
        <Text style={s.sheetNotText}>{group ? GROUP.askNot() : CANDS.notYet()}</Text>
      </Pressable>
    </Sheet>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: space.md },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  backIcon: { fontSize: 24, color: color.fg, marginTop: -3 },
  dot: { width: 26, height: 26, borderRadius: 13, backgroundColor: color.primary },
  headTitle: { flex: 1, fontSize: 19, fontWeight: '700', color: color.fg },

  scroll: { padding: 20, paddingTop: 0, gap: space.md },
  lead: { ...type.body, color: color.muted } as any,
  note: { ...type.bodySmall, color: color.primary } as any,

  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.sm },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  av: { width: 56, height: 56, borderRadius: rad.full },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  name: { ...type.title, color: color.fg, flexShrink: 1 } as any,
  badge: { paddingHorizontal: 9, height: 22, borderRadius: rad.full, backgroundColor: color.primary, justifyContent: 'center' },
  badgeText: { fontSize: 10.5, fontWeight: '700', color: color.onPrimary },
  subtitle: { ...type.bodySmall, color: color.muted, marginTop: 1 } as any,
  whereRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  meta: { ...type.bodySmall, color: color.muted } as any,

  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  tag: { paddingHorizontal: 10, height: 28, borderRadius: rad.full, backgroundColor: color.neutral100, justifyContent: 'center' },
  tagText: { ...type.labelSmall, color: color.muted } as any,

  sumBox: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md, gap: 4 },
  sumLabel: { ...type.labelSmall, color: color.primary, fontWeight: '700' } as any,
  sumText: { ...type.bodySmall, color: color.fg } as any,
  readiness: { ...type.caption, color: color.muted } as any,

  invite: { height: 46, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  invitedRow: { flexDirection: 'row', gap: space.sm },
  invitedPill: { flex: 1, backgroundColor: color.neutral100 },
  cancelPill: { flex: 1, backgroundColor: color.ink },
  /** GR.17 «Joined»: спокойная зелёная пилюля, не кнопка — нажимать тут нечего. */
  joinedPill: { backgroundColor: color.successBg },
  /** Строка регламента/счётчика набора — GR.14/GR.17, под шапкой над карточками. */
  gline: { ...type.bodySmall, color: color.muted } as any,
  inviteText: { ...type.button, color: color.onPrimary } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  /* «Ещё» — вторичная кнопка: продолжение списка не должно спорить за внимание с приглашением,
     ради которого экран и открыт. */
  moreBtn: {
    height: 48, borderRadius: rad.full, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  moreText: { ...type.button, color: color.fg } as any,
  ctaText: { ...type.button, color: color.onPrimary } as any,

  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },

  noMatch: { alignItems: 'center', gap: space.md, paddingTop: space.xl },
  noMatchArt: {
    width: 96, height: 96, borderRadius: 48, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  noMatchTitle: { fontSize: 20, fontWeight: '700', color: color.fg, textAlign: 'center' },

  prefsBtn: {
    height: 44, borderRadius: rad.full, borderWidth: 1, borderColor: color.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  prefsBtnText: { ...type.labelMedium, color: color.primary, fontWeight: '600' } as any,
  prefLabelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  prefLabel: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  prefChips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  prefChip: {
    height: 38, paddingHorizontal: 16, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  prefChipOn: { backgroundColor: color.primary, borderColor: color.primary },
  prefChipText: { ...type.labelMedium, color: color.fg } as any,
  prefHeadRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  prefVal: { ...type.bodySmall, color: color.primary, fontWeight: '600' } as any,
  prefsBody: { gap: space.md, paddingBottom: space.sm },
  miniChip: {
    height: 30, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, alignItems: 'center', justifyContent: 'center',
  },
  miniChipText: { ...type.caption, color: color.muted, fontWeight: '600' } as any,

  plusPrice: { ...type.caption, color: color.muted, textAlign: 'center' } as any,
  capRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 6 },
  capName: { flex: 1, ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  capBtn: {
    height: 36, paddingHorizontal: 14, borderRadius: rad.full, backgroundColor: color.ink,
    alignItems: 'center', justifyContent: 'center',
  },
  capBtnText: { ...type.labelMedium, color: '#fff', fontWeight: '600' } as any,
  sheetBody: { ...type.bodySmall, color: color.muted } as any,
  sheetSend: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  sheetSendText: { ...type.button, color: color.onPrimary } as any,
  sheetNot: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  sheetGhost: { height: 48, alignItems: 'center', justifyContent: 'center' },
  sheetGhostText: { ...type.button, color: color.muted } as any,
  grabber: {
    width: 40, height: 4, borderRadius: 2, backgroundColor: color.neutral100,
    alignSelf: 'center', marginTop: -6,
  },
  sheetNotText: { ...type.button, color: '#fff' } as any,
});
