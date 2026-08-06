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
  View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { RESULTS, EXPAND_LADDER, ExpandAxis, axisExplain } from '../src/intent';
import { CANDS, PREFS, Cand, candSubtitle, candWhere, candSummary } from '../src/candidates';
import { CHAT, Req, ReqStatus, byPerson, activeChatWith } from '../src/chat';
import { useLang, T, getLang } from '../src/i18n';
import { takeResults, setCandidate } from '../src/results-store';
import { agent } from '../src/api';
import { IconPerson, IconPin, IconClock } from '../src/components/icons';
import { AgeRange } from '../src/components/AgeRange';
import Slider from '@react-native-community/slider';
import { SEXES, sexLabel } from '../src/onboarding';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

const ru = () => getLang() === 'ru';

export default function Results() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  // Читаем один раз: последующие render'ы не должны затирать уже расширенную выдачу исходной.
  const initial = useMemo(() => takeResults(), []);

  const [intent, setIntent] = useState<any>(initial?.intent || {});
  const [cands, setCands] = useState<Cand[]>(initial?.candidates || []);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  /** Следующая непройденная ступень лестницы. */
  const [rung, setRung] = useState(0);
  /**
   * Кому уже отправлено: имя → id заявки. Id нужен не для красоты — «Отменить» на кадре O.15
   * отзывает приглашение, а отзыв на сервере ходит по id, и потерять его значит оставить кнопку,
   * которая ничего не может отменить.
   */
  const [sent, setSent] = useState<Record<string, string>>({});
  /** Кандидат, для которого открыто окно O.14. null — окна нет. */
  const [asking, setAsking] = useState<Cand | null>(null);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState('');
  /**
   * Что стало с уже отправленными приглашениями. Тянется с сервера: ответ приходит не на этом
   * экране, и без опроса карточка навсегда осталась бы в состоянии «Отправлено».
   */
  const [reqs, setReqs] = useState<Record<string, Req>>({});
  /** Окно бесплатного тарифа (O.17): с кем уже идёт переписка, когда пробуешь открыть вторую. */
  const [busyWith, setBusyWith] = useState('');
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
  const [prefs, setPrefs] = useState(() => ({
    sex: String(initial?.intent?.sex || 'Any'),
    minAge: Number(initial?.intent?.minAge || 18),
    maxAge: Number(initial?.intent?.maxAge || 28),
    flexH: 2,
  }));
  const [reSearching, setReSearching] = useState(false);

  const profile = initial?.profile || {};
  const self = String(profile?.name || '');

  // Радиус нечего удваивать, когда встреча онлайн, — эта ступень для такого интента бессмысленна.
  const ladder: ExpandAxis[] = useMemo(
    () => EXPAND_LADDER.filter((a) => !(a === 'radius' && intent?.mode === 'online')),
    [intent?.mode]
  );

  /** Карточки-заменители: тема не совпала ни у кого, показаны просто ближайшие подходящие люди. */
  const onlyFallback = cands.length > 0 && cands.every((c) => !!(c as any).fallback);
  const canWiden = rung < ladder.length && (cands.length === 0 || onlyFallback);

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
        setIntent((prev: any) => ({
          ...prev,
          ...(axis === 'adjacent' ? { adjacentAllowed: true } : {}),
          ...(axis === 'parent' ? { broadAllowed: true } : {}),
          ...(axis === 'exactness' ? { exactMatchRequired: false } : {}),
          ...(axis === 'radius' ? { radiusKm: km } : {}),
        }));
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

  /** Отправка приглашения — только из окна O.14, никогда прямо с кнопки карточки. */
  const sendInvite = async () => {
    const to = String(asking?.name || '');
    if (!to || sending) return;
    setSending(true);
    setSendErr('');
    try {
      const r: any = await agent.propose(self, to, intent);
      if (!r?.ok) throw new Error(r?.error || 'propose failed');
      setSent((prev) => ({ ...prev, [to]: String(r.id || '') }));
      setAsking(null);
    } catch {
      setSendErr(CANDS.inviteFailed());
    } finally {
      setSending(false);
    }
  };

  /** O.15 «Cancel»: отозвать НЕотвеченное приглашение. Ответившее отозвать нельзя — скажет сервер. */
  const cancelInvite = async (to: string) => {
    const id = sent[to];
    if (!id) return;
    try {
      const r: any = await agent.withdraw(id, self);
      // ALREADY_RESOLVED — человек уже ответил, пока мы смотрели на экран. Кнопку всё равно
      // убираем: отменять больше нечего, а правда живёт в списке интентов.
      if (!r?.ok && r?.error !== 'ALREADY_RESOLVED') throw new Error(r?.error || 'withdraw failed');
      setSent((prev) => {
        const next = { ...prev };
        delete next[to];
        return next;
      });
    } catch {
      setNote(CANDS.cancelFailed());
    }
  };

  /** «Начать поиск» из листа O.11a: тот же /api/agent/match, но с условиями, которые человек ослабил сам. */
  const reSearch = async () => {
    if (reSearching) return;
    setReSearching(true);
    setNote('');
    try {
      const next: any = { ...intent, minAge: prefs.minAge, maxAge: prefs.maxAge };
      if (prefs.sex && prefs.sex !== 'Any') next.sex = prefs.sex;
      else delete next.sex;
      // Гибкость по времени сервер сегодня НЕ читает — поле едет в интент честно помеченным
      // ожиданием: когда матчинг научится, клиент уже отправляет. Врать «± 2 часа применены»
      // мы не можем, поэтому в подписи ступени это и не утверждается.
      next.timeFlexHours = prefs.flexH;
      const r: any = await agent.match(next, profile, {
        self, uid: self, city: profile?.city,
      });
      setIntent(r?.intent || next);
      setCands((r?.candidates || []) as Cand[]);
      setRung(0);                      // условия сменились — лестница §12 начинается заново
      setPrefsOpen(false);
    } catch {
      setNote(T('Не получилось поискать. Попробуй ещё раз.', 'The search failed. Try again.'));
    } finally {
      setReSearching(false);
    }
  };

  /** Состояния приглашений живут на сервере — забираем их и обновляем, пока экран открыт. */
  const loadReqs = useCallback(async () => {
    if (!self) return;
    try {
      const [o, th]: any[] = await Promise.all([
        agent.outbox(self),
        agent.threads(self).catch(() => ({ threads: [] })),
      ]);
      setReqs(byPerson((o?.requests || []) as Req[]));
      setChatting(activeChatWith((th?.threads || []) as any[]));
    } catch {
      /* тихо: фоновая дотяжка состояний */
    }
  }, [self]);

  useEffect(() => { loadReqs(); }, [loadReqs]);
  useEffect(() => {
    const id = setInterval(loadReqs, 6000);
    return () => clearInterval(id);
  }, [loadReqs]);

  /**
   * Открыть переписку. Правило бесплатного тарифа с кадра O.17 — один живой чат за раз — живёт
   * ЗДЕСЬ, потому что на сервере его нет: он позволяет писать любому, кто принял приглашение.
   * Когда тариф появится на сервере, проверку надо перенести туда — иначе она обходится любым
   * другим клиентом.
   */
  const openChat = (name: string, photo?: string) => {
    const active = chatting;
    if (active && active.toLowerCase() !== name.toLowerCase()) {
      setBusyWith(active);
      return;
    }
    router.push({
      pathname: '/conversation',
      params: { who: name, title: String(intent?.title || (intent?.topics || []).join(', ') || ''), photo: photo || '' },
    });
  };

  /** O.16 «Убрать»: карточка уходит с экрана. Отклонённое приглашение сервер уже закрыл сам. */
  const removeCard = (name: string) => {
    setCands((prev) => prev.filter((c) => String(c.name || '') !== name));
  };

  const openProfile = (c: Cand) => {
    setCandidate(c);
    router.push('/candidate');
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
          <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.replace('/create')}>
            <Text style={s.ctaText}>{T('Новый поиск', 'New search')}</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const title = cands.length === 0 ? RESULTS.empty()
              : onlyFallback ? T('Прямых совпадений нет', 'No direct matches')
              : RESULTS.best();

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
        {onlyFallback ? (
          <View style={{ gap: space.sm }}>
            <Text style={s.lead}>
              {T('Никто не занимается ровно этим. Вот кто рядом и с кем это может получиться.',
                 'Nobody is doing exactly that. Here are people nearby it could work with.')}
            </Text>
            <Pressable accessibilityRole="button" style={s.prefsBtn} onPress={() => setPrefsOpen(true)}>
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
            <Pressable accessibilityRole="button" style={s.cta} onPress={() => setPrefsOpen(true)}>
              <Text style={s.ctaText}>{PREFS.title()}</Text>
            </Pressable>
          </View>
        ) : null}

        {cands.map((c, i) => (
          <CandCard
            key={(c.name || '') + i}
            c={c}
            badge={(c as any).fallback ? '' : i === 0 ? CANDS.bestBadge() : CANDS.matchBadge()}
            invited={!!sent[String(c.name || '')]}
            status={reqs[String(c.name || '')]?.status}
            onOpen={() => openProfile(c)}
            onInvite={() => { setSendErr(''); setAsking(c); }}
            onCancel={() => cancelInvite(String(c.name || ''))}
            onOpenChat={() => openChat(String(c.name || ''), c.photo)}
            onRemove={() => removeCard(String(c.name || ''))}
          />
        ))}

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
        busy={reSearching}
        onStart={reSearch}
        onClose={() => setPrefsOpen(false)}
        bottomInset={insets.bottom}
      />

      {/* Окно бесплатного тарифа — кадр O.17. Текст с кадра; ограничение клиентское, см. openChat. */}
      <Modal visible={!!busyWith} transparent animationType="slide" onRequestClose={() => setBusyWith('')}>
        <Pressable style={s.scrim} onPress={() => setBusyWith('')} accessibilityLabel={T('Закрыть', 'Close')} />
        <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 18) }]}>
          <View style={s.sheetHead}>
            <Text style={s.sheetTitle}>{CHAT.busyTitle(busyWith)}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={() => setBusyWith('')} hitSlop={10}>
              <Text style={s.sheetX}>✕</Text>
            </Pressable>
          </View>
          <Text style={s.sheetBody}>{CHAT.busyBody()}</Text>
          {/* Тарифа в продукте нет — кнопка честно выключена, как везде в каркасе. */}
          <View style={[s.sheetSend, { opacity: 0.45 }]}>
            <Text style={s.sheetSendText}>{CHAT.getPlus()}</Text>
          </View>
          <Text style={s.plusPrice}>{CHAT.plusPrice()}</Text>
          <Pressable
            accessibilityRole="button"
            style={s.sheetNot}
            onPress={() => {
              const who = busyWith;
              setBusyWith('');
              router.push({ pathname: '/conversation', params: { who } });
            }}
          >
            <Text style={s.sheetNotText}>{CHAT.endChatWith(busyWith)}</Text>
          </Pressable>
        </View>
      </Modal>

      <InviteSheet
        cand={asking}
        sending={sending}
        err={sendErr}
        onSend={sendInvite}
        onClose={() => setAsking(null)}
        bottomInset={insets.bottom}
      />
    </View>
  );
}

/** Карточка кандидата — кадр O.12. Нажатие на тело карточки открывает полный профиль (O.13). */
function CandCard({
  c, badge, invited, status, onOpen, onInvite, onCancel, onOpenChat, onRemove,
}: {
  c: Cand;
  badge: string;
  invited: boolean;
  /** Ответ на приглашение, как его называет сервер. Пусто — ответа ещё нет. */
  status?: ReqStatus;
  onOpen: () => void;
  onInvite: () => void;
  onCancel: () => void;
  onOpenChat: () => void;
  onRemove: () => void;
}) {
  const readiness = (ru() ? c.readiness_ru : c.readiness_en) || '';
  const where = candWhere(c);
  const summary = candSummary(c, ru());

  return (
    <View style={s.card}>
      <Pressable accessibilityRole="button" onPress={onOpen} style={({ pressed }) => [pressed && { opacity: 0.92 }]}>
        <View style={s.cardTop}>
          {c.photo ? (
            <Image source={{ uri: c.photo }} style={s.av} />
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
            {(c.interests || []).slice(0, 3).map((t, i) => (
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
      {status === 'declined' ? (
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
      ) : invited || status === 'pending' ? (
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
 * Лист O.11a «Изменить условия поиска»: пол, возраст линейным диапазоном (на этом кадре — слайдер,
 * не кольцо) и гибкость по времени. «Начать поиск» перезапускает матчинг с ослабленными условиями.
 */
function PrefsSheet({
  open, prefs, setPrefs, busy, onStart, onClose, bottomInset,
}: {
  open: boolean;
  prefs: { sex: string; minAge: number; maxAge: number; flexH: number };
  setPrefs: React.Dispatch<React.SetStateAction<{ sex: string; minAge: number; maxAge: number; flexH: number }>>;
  busy: boolean;
  onStart: () => void;
  onClose: () => void;
  bottomInset: number;
}) {
  return (
    <Modal visible={open} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel={T('Закрыть', 'Close')} />
      <View style={[s.sheet, { paddingBottom: Math.max(bottomInset, 18) }]}>
        <View style={s.sheetHead}>
          <Text style={s.sheetTitle}>{PREFS.title()}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={onClose} hitSlop={10}>
            <Text style={s.sheetX}>✕</Text>
          </Pressable>
        </View>

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

        <View style={s.prefLabelRow}>
          <IconClock size={16} c={color.fg} />
          <Text style={s.prefLabel}>{PREFS.age()}</Text>
        </View>
        <AgeRange
          min={prefs.minAge}
          max={prefs.maxAge}
          onChange={(lo, hi) => setPrefs((p) => ({ ...p, minAge: lo, maxAge: hi }))}
        />

        <View style={s.prefFlexRow}>
          <Text style={s.prefLabel}>{PREFS.flex()}</Text>
          <Text style={s.prefFlexVal}>{PREFS.flexVal(prefs.flexH)}</Text>
        </View>
        <Slider
          minimumValue={0}
          maximumValue={6}
          step={1}
          value={prefs.flexH}
          onValueChange={(h) => setPrefs((p) => ({ ...p, flexH: Math.round(h) }))}
          minimumTrackTintColor={color.primary}
          maximumTrackTintColor={color.neutral100}
          thumbTintColor={color.primary}
        />

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ busy }}
          style={s.sheetSend}
          onPress={busy ? undefined : onStart}
        >
          {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.sheetSendText}>{PREFS.start()}</Text>}
        </Pressable>
        <Pressable accessibilityRole="button" style={s.sheetNot} onPress={onClose}>
          <Text style={s.sheetNotText}>{PREFS.cancel()}</Text>
        </Pressable>
      </View>
    </Modal>
  );
}

/** Окно O.14: последствия названы словами, отправка — только отсюда. */
function InviteSheet({
  cand, sending, err, onSend, onClose, bottomInset,
}: {
  cand: Cand | null;
  sending: boolean;
  err: string;
  onSend: () => void;
  onClose: () => void;
  bottomInset: number;
}) {
  const name = String(cand?.name || '');
  return (
    <Modal visible={!!cand} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel={T('Закрыть', 'Close')} />
      <View style={[s.sheet, { paddingBottom: Math.max(bottomInset, 18) }]}>
        <View style={s.sheetHead}>
          <Text style={s.sheetTitle}>{CANDS.sheetTitle(name)}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Закрыть', 'Close')} onPress={onClose} hitSlop={10}>
            <Text style={s.sheetX}>✕</Text>
          </Pressable>
        </View>
        <Text style={s.sheetBody}>{CANDS.sheetBody(name)}</Text>
        {err ? <Text style={s.note}>{err}</Text> : null}
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ busy: sending }}
          style={s.sheetSend}
          onPress={sending ? undefined : onSend}
        >
          {sending ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.sheetSendText}>{CANDS.send()}</Text>}
        </Pressable>
        <Pressable accessibilityRole="button" style={s.sheetNot} onPress={onClose}>
          <Text style={s.sheetNotText}>{CANDS.notYet()}</Text>
        </Pressable>
      </View>
    </Modal>
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
  inviteText: { ...type.button, color: color.onPrimary } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
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
  prefFlexRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  prefFlexVal: { ...type.bodySmall, color: color.primary, fontWeight: '600' } as any,

  plusPrice: { ...type.caption, color: color.muted, textAlign: 'center' } as any,
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: '#0006' },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: color.card, borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 20, paddingTop: 18, gap: space.md,
  },
  sheetHead: { flexDirection: 'row', alignItems: 'center' },
  sheetTitle: { flex: 1, fontSize: 20, fontWeight: '700', color: color.fg },
  sheetX: { fontSize: 20, color: color.fg },
  sheetBody: { ...type.bodySmall, color: color.muted } as any,
  sheetSend: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  sheetSendText: { ...type.button, color: color.onPrimary } as any,
  sheetNot: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  sheetNotText: { ...type.button, color: '#fff' } as any,
});
