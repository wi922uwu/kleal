/**
 * Групповой план — ОДИН экран на всю его жизнь: GR.25 → GR.26/28/29 → GR.30/31 → GR.34, плюс
 * голосование GR.35–38, правка организатором GR.32/33 и онлайновая ссылка GRO.25a.
 *
 * UX-КАРКАС: вид натянется поверх; копия и разбор состояний — в src/gplan.ts.
 *
 * ПОЧЕМУ ОДИН ЭКРАН. На борде это пятнадцать кадров, но у всех одна и та же раскладка: заголовок,
 * карточка плана, индикатор раундов, состав, пара кнопок внизу. Меняются слова и то, что делают
 * кнопки. Разложить это по маршрутам значило бы, что человек, открывая свой же план, каждый раз
 * попадает в новое место, и что «назад» ведёт в историю согласования, а не к группе. Ровно так же
 * устроен план 1:1 (app/plan.tsx) — и по той же причине.
 *
 * Что экран НЕ решает сам, потому что это решает сервер:
 *  — можно ли ещё предложить своё (раунды), можно ли закрепить, чей сейчас ход — приходит флагами
 *    (`rounds_used_up`, `can_fix`, `stay_or_leave`, `accept_or_leave`);
 *  — сколько ещё подтверждений нужно (`needs`) — считается от ВСЕГО состава, а не от тройки;
 *  — жив ли план (`state`) и заперт ли он двухчасовым окном (`locked`).
 * Дублировать эти проверки здесь значило бы завести второй источник правды, который разойдётся
 * с первым при первой же правке правил.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image,
  ActivityIndicator, Modal, KeyboardAvoidingView, Platform, Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { group as gapi, mediaUrl, newIdem, type GroupInfo } from '../src/api';
import { GPLAN, venue, hoursLeft, memberState, type GPlan, type GVote } from '../src/gplan';
import { ROOM } from '../src/groups';
import { WhenPicker, whenLabel, whenStartsAt, whenFromStartsAt, type WhenValue } from '../src/components/WhenPicker';
import { dateChips, deviceTz } from '../src/intent';
import {
  IconChevronLeft, IconPerson, IconCalendar, IconPin, IconVideo, IconLink, IconCheckCircle, IconClock,
} from '../src/components/icons';
import { Sheet } from '../src/components/Sheet';
import { color, radius as rad, space, type } from '../src/theme';

/** Локальные режимы, которых у сервера нет: это формы, а не состояния плана. */
type Mode = 'view' | 'create' | 'suggest' | 'update' | 'link';

export default function GroupPlan() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const kb = useKeyboardInset();

  const params = useLocalSearchParams<{ gid?: string }>();
  const gid = String(params.gid || '').trim();
  const me = String(st.profile.name || '');

  const [g, setG] = useState<GroupInfo | null>(null);
  const [plan, setPlan] = useState<GPlan | null>(null);
  const [vote, setVote] = useState<GVote | null>(null);
  const [mode, setMode] = useState<Mode>('view');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [fatal, setFatal] = useState('');
  const [askVote, setAskVote] = useState(false);
  const [voteSheet, setVoteSheet] = useState(false);
  const [decideSheet, setDecideSheet] = useState(false);

  /**
   * Поля форм. Одни и те же на создание, предложение и правку — предлагают всегда одно и то же.
   *
   * Время — НЕ строка. Здесь стояло текстовое поле «например: чт 24 июля, 20:30», и у плана из-за
   * этого не было настоящего момента: сервер считает двухчасовой замок и отказ TOO_LATE по
   * `starts_at`, а он не отправлялся вовсе. Теперь дата и время выбираются как на кадре GR.09 и
   * уходят вдвоём — подписью и unix-секундами.
   */
  const [when, setWhen] = useState<WhenValue>(() => ({
    date: dateChips(1)[0].key,
    minutes: 20 * 60,
    tz: deviceTz(),
  }));
  const [dragging, setDragging] = useState(false);
  const [place, setPlace] = useState('');
  const [link, setLink] = useState('');

  const owner = String(g?.owner || '');
  const isOwner = !!g?.i_am_owner;
  const members = (g?.members || []) as { name?: string; photo?: string }[];
  const online = (plan?.mode || (g as any)?.mode || 'offline') === 'online';

  const load = useCallback(async () => {
    if (!gid || !me) return;
    try {
      const r: any = await gapi.get(gid, me);
      if (r?.error === 'NO_SUCH_GROUP') { setFatal(ROOM.gone()); return; }
      const grp = r?.group;
      if (!grp) return;
      setG(grp);
      setPlan(grp.plan || null);
      // Голосование живёт не на группе, а на человеке: сервер отдаёт его в списке планов вместе
      // с закрытыми-но-нерешёнными, и именно они рисуют GR.37/38. Второй запрос — только когда
      // план есть: без плана голосовать не о чем, и опрашивать нечего.
      const pid = String(grp.plan?.id || '');
      if (pid) {
        const pl: any = await gapi.plans(me);
        setVote(((pl?.votes || []) as GVote[]).find((v) => String(v.plan_id || '') === pid) || null);
      } else {
        setVote(null);
      }
      setErr('');
    } catch {
      /* фоновый опрос молчит: ругаться на каждую неудачу сети незачем */
    } finally {
      setLoading(false);
    }
  }, [gid, me]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (fatal) return;
    // План согласовывают несколько человек одновременно; без опроса экран показывал бы вчерашний
    // состав подтверждений. Реже, чем чат: тут события редкие.
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, [load, fatal]);

  /** Общая обёртка действий: одна занятость, один разбор ошибки, один перезапрос. */
  const act = async (fn: () => Promise<any>, after?: (r: any) => void) => {
    if (busy) return;
    setBusy(true);
    setErr('');
    try {
      const r = await fn();
      if (r?.ok === false) { setErr(explain(r?.error)); return; }
      if (r?.plan) setPlan(r.plan);
      after?.(r);
      await load();
    } catch {
      setErr(GPLAN.failed());
    } finally {
      setBusy(false);
    }
  };

  const explain = (e?: string) => {
    switch (String(e || '')) {
      case 'NEED_THREE': return GPLAN.needThree(Number(g?.need_more || 1));
      case 'TOO_LATE': return GPLAN.tooLate();
      case 'PLAN_EXISTS': return GPLAN.planExists();
      case 'NOT_ORGANIZER': return GPLAN.notOrganiser();
      case 'ROUNDS_USED_UP': return GPLAN.roundsUsedUp();
      case 'ROUNDS_LEFT': return GPLAN.roundsUsedUp();
      case 'VOTE_IN_PROGRESS': return GPLAN.voteExists();
      case 'LOCKED': return GPLAN.locked();
      case 'BAD_LINK': return GPLAN.badLink();
      case 'NO_SUCH_PLAN': return GPLAN.gone();
      default: return GPLAN.failed();
    }
  };

  // ---- действия ---------------------------------------------------------

  /**
   * Время уходит ПАРОЙ: `when` — подпись, которую читают люди, `starts_at` — момент, по которому
   * сервер считает двухчасовой замок и отказывает в плане на прошлое. Отправить одну подпись —
   * значит завести план, который никогда не замрёт перед встречей.
   */
  const timeArgs = () => ({ when: whenLabel(when), starts_at: whenStartsAt(when) });

  const create = () =>
    act(() => gapi.planBegin(gid, me, { ...timeArgs(), place: place.trim() }, newIdem('gpb')),
        () => { setMode('view'); setPlace(''); });

  const confirm = () =>
    act(() => gapi.planRespond(String(plan?.id), me, 'confirm', newIdem('gpc')));

  const counter = () =>
    act(() => gapi.planRespond(String(plan?.id), me, 'counter', newIdem('gpn'),
                               { ...timeArgs(), place: place.trim() || plan?.place || '' }),
        () => { setMode('view'); setPlace(''); });

  const fix = () => act(() => gapi.planFix(String(plan?.id), me, newIdem('gpf')));

  /** GR.40: организатор закрывает план, вставший на паузу. Группа остаётся — уходит только план. */
  const cancelPlan = () => act(() => gapi.planCancel(String(plan?.id), me, newIdem('gpc')));

  const update = () =>
    act(() => gapi.planUpdate(String(plan?.id), me,
                              { ...timeArgs(), place: place.trim() || undefined }, newIdem('gpu')),
        () => { setMode('view'); setPlace(''); });

  const saveLink = () =>
    act(() => gapi.planLink(String(plan?.id), me, link.trim(), newIdem('gpl')),
        () => { setMode('view'); setLink(''); });

  /** «Ask the group to host instead» (GRO.25a) — это реплика в общий чат, а не своя сущность. */
  const askHost = async () => {
    await gapi.post(gid, me, GPLAN.askHostMsg());
    setMode('view');
    router.push({ pathname: '/group', params: { gid } });
  };

  const startVote = (kind: 'edit' | 'cancel') =>
    act(() => gapi.voteOpen(String(plan?.id), me, kind, newIdem('gvo'),
                            kind === 'edit' ? timeArgs() : {}),
        () => setAskVote(false));

  const castVote = (yes: boolean) =>
    act(() => gapi.vote(String(vote?.id), me, yes, newIdem('gv')), () => setVoteSheet(false));

  const decide = (apply: boolean) =>
    act(() => gapi.voteDecide(String(vote?.id), me, apply, newIdem('gvd')),
        () => setDecideSheet(false));

  /** «Выйти из плана» (GR.31) и «Выйти из группы» (GR.33) — на сервере это одно: выход из группы.
   *  Группового плана без группы не бывает, и делать вид, что можно выйти из одного, оставшись в
   *  другом, значило бы обещать несуществующее состояние. */
  const leave = () =>
    act(() => gapi.leave(gid, me, newIdem('gpx')),
        () => (router.canGoBack() ? router.back() : router.replace('/home')));

  // ---- какой это кадр ---------------------------------------------------

  const view = useMemo(() => frameOf({ plan, vote, isOwner, owner, me }), [plan, vote, isOwner, owner, me]);

  /**
   * Кто внёс нынешнее предложение — ФАКТОМ с сервера (`proposed_by`).
   *
   * Раньше это выводилось: встречное предложение обнуляет подтверждения и ставит одно, своё, —
   * значит единственный подтвердивший и есть предложивший. Догадка рассыпалась ровно там, где
   * кадр GR.29 и нарисован: стоило второму подтвердить, как подтвердивших становилось двое,
   * заголовок срывался в «ждём всех», а пояснение рядом продолжало называть имя. Один экран
   * говорил две разные вещи.
   *
   * Старый вывод оставлен запасным: у планов, предложенных до появления поля, его нет.
   */
  const proposer = useMemo(() => {
    const said = String(plan?.proposed_by || '').trim();
    if (said) return said;
    const conf = plan?.confirmed || [];
    return Number(plan?.round || 1) > 1 && conf.length === 1 ? String(conf[0]) : '';
  }, [plan]);

  if (fatal) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <Head title={ROOM.gone()} onBack={() => router.replace('/home')} />
        <Text style={s.fatal}>{fatal}</Text>
      </View>
    );
  }

  const formMode = mode !== 'view';

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <Head
          title={g?.title || ''}
          onBack={() => {
            if (formMode) { setMode('view'); setErr(''); return; }
            router.canGoBack() ? router.back() : router.replace('/home');
          }}
        />

        {/* scrollEnabled выключается на время вращения циферблата: иначе жест по кругу
            перехватывает список, и стрелка прыгает. Та же пара, что в мастере интента. */}
        <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled"
                    scrollEnabled={!dragging}>
          {loading && !g ? <ActivityIndicator style={{ marginTop: 24 }} color={color.primary} /> : null}

          {/* Заголовок и пояснение — они и есть кадр: на борде меняются только эти две строки. */}
          <Text style={s.title}>{formTitle(mode, view, { plan, vote, owner, online, proposer, isOwner })}</Text>
          <Text style={s.note}>{formNote(mode, view, { plan, vote, owner, online, g, isOwner })}</Text>

          {/* Карточка плана — общая для всех кадров. В форме показывает то, что человек вводит
              прямо сейчас: иначе он правит вслепую и сверяет с памятью. */}
          {plan || formMode ? (
            <PlanCard
              title={g?.title || ''}
              when={formMode ? whenLabel(when) : String(plan?.when || '')}
              was={mode === 'update' ? String(plan?.when || '') : String(plan?.update?.was?.when || '')}
              venueLine={
                formMode && !online
                  ? (place || plan?.place || GPLAN.placePh())
                  : venue({ ...(plan || {}), place: place || plan?.place, mode: online ? 'online' : 'offline' })
              }
              online={online}
              placeUnchanged={mode === 'update' && !place.trim()}
            />
          ) : null}

          {/* Индикатор раундов — только пока согласовывают. На утверждённом плане его нет и на борде. */}
          {/* Виден и в форме: раунд тратится ровно в ней, и «Round 2 of 3» нужно перед отправкой,
              а не после. Скрытый на время формы, он пропадал в самый нужный момент. */}
          {plan?.state === 'proposed' ? (
            <RoundBar round={Number(plan.round || 1)} max={Number(plan.max_rounds || 3)} />
          ) : null}

          {/* Голосование идёт — плашка со сроком (GR.36). */}
          {vote?.state === 'open' ? (
            <Pressable style={s.badge} onPress={() => setVoteSheet(true)} accessibilityRole="button">
              <IconClock size={14} c={color.infoText} />
              <Text style={s.badgeText}>{GPLAN.voteBadge(hoursLeft(vote.closes_at))}</Text>
            </Pressable>
          ) : null}

          {/* Онлайн без ссылки — группа видит «ссылка будет», организатор её ставит (GRO.25a). */}
          {plan?.needs_link && mode === 'view' ? (
            <View style={s.warn}>
              <Text style={s.warnText}>{GPLAN.linkComing()}</Text>
            </View>
          ) : null}

          {/* Формы. Поля одни и те же, потому что предлагают всегда одно и то же — время и место. */}
          {mode === 'create' || mode === 'suggest' || mode === 'update' ? (
            <View style={s.form}>
              {/* Кадр GR.09: чипы дат, циферблат, часы и минуты — тот же компонент, что в мастере
                  интента. Место остаётся полем: у него нет готового списка, а район приезжает
                  из интента группы. */}
              <WhenPicker value={when} onChange={setWhen} onDragChange={setDragging} />
              {!online ? (
                <TextInput
                  style={s.input} value={place} onChangeText={setPlace}
                  placeholder={GPLAN.placePh()} placeholderTextColor={color.neutral400}
                />
              ) : null}
            </View>
          ) : null}

          {mode === 'link' ? (
            <View style={s.form}>
              <TextInput
                style={s.input} value={link} onChangeText={setLink}
                placeholder={GPLAN.linkPh()} placeholderTextColor={color.neutral400}
                autoCapitalize="none" autoCorrect={false} keyboardType="url"
              />
            </View>
          ) : null}

          {/* Состав со статусами — колонка, которая на борде есть на каждом кадре. */}
          {members.length ? (
            <View style={s.roster}>
              {members.map((m, i) => {
                const nm = String(m.name || '');
                const stt = memberState(nm, plan || {}, { owner, me, proposer });
                return (
                  <View key={nm + i} style={s.memberRow}>
                    {/*
                      Заглушка рисуется ВСЕГДА, фото ложится поверх. Так у строки есть кружок с
                      человечком, пока фото едет, — и остаётся, если оно не доедет вовсе. Замерено
                      на проде: /api/onboarding/photo отдаёт 51 КБ за тридцать секунд через
                      туннель, и всё это время на месте человека была дыра.
                    */}
                    <View style={[s.av, s.avEmpty]}>
                      <IconPerson size={18} />
                      {m.photo ? (
                        <Image source={{ uri: mediaUrl(String(m.photo)) }}
                               style={[s.av, StyleSheet.absoluteFillObject]} />
                      ) : null}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.memberName} numberOfLines={1}>
                        {nm.toLowerCase() === me.toLowerCase() ? GPLAN.you() : nm}
                      </Text>
                      <Text style={s.memberState} numberOfLines={1}>
                        {plan ? stt.text : (nm === owner ? GPLAN.roleOrganiser() : GPLAN.stInGroup())}
                      </Text>
                    </View>
                    {plan && stt.done ? <IconCheckCircle size={18} /> : null}
                  </View>
                );
              })}
            </View>
          ) : null}

          {/* Ссылка на звонок — кнопкой, а не текстом: её открывают, а не переписывают. */}
          {online && plan?.link && mode === 'view' ? (
            <Pressable style={s.linkRow} accessibilityRole="link"
                       onPress={() => Linking.openURL(String(plan.link)).catch(() => setErr(GPLAN.failed()))}>
              <IconLink size={16} c={color.infoText} />
              <Text style={s.linkText}>{GPLAN.openLink()}</Text>
            </Pressable>
          ) : null}

          {err ? <Text style={s.err}>{err}</Text> : null}
        </ScrollView>

        {/* Нижние кнопки: ровно та пара, что на кадре для этого состояния. */}
        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          <Actions
            mode={mode}
            view={view}
            busy={busy}
            plan={plan}
            vote={vote}
            online={online}
            leftForConfirm={Number(plan?.needs || 0)}
            isOwner={isOwner}
            onCreateOpen={() => { setPlace(''); setMode('create'); }}
            onCreate={create}
            onConfirm={confirm}
            onSuggestOpen={() => { setWhen(whenFromStartsAt(plan?.starts_at, when.tz) || when); setPlace(String(plan?.place || '')); setMode('suggest'); }}
            onSuggestSend={counter}
            onFix={fix}
            onInviteMore={() => router.push({ pathname: '/group', params: { gid } })}
            onCancelPlan={cancelPlan}
            onMoreTime={() => {}}
            onStay={confirm}
            onLeave={leave}
            onOpenChat={() => router.push({ pathname: '/group', params: { gid } })}
            onAskVote={() => setAskVote(true)}
            onOpenVote={() => setVoteSheet(true)}
            onDecide={() => setDecideSheet(true)}
            onUpdateOpen={() => { setWhen(whenFromStartsAt(plan?.starts_at, when.tz) || when); setPlace(''); setMode('update'); }}
            onUpdateSend={update}
            onAccept={confirm}
            onLinkOpen={() => setMode('link')}
            onLinkSave={saveLink}
            onAskHost={askHost}
            onCancelForm={() => { setMode('view'); setErr(''); }}
          />
        </View>

        {/* GR.35 — попросить группу. Лист, потому что это вопрос, а не экран. */}
        <PlanSheet open={askVote} onClose={() => setAskVote(false)}
               title={GPLAN.askTitle()}
               body={isOwner ? GPLAN.askNoteMine() : GPLAN.askNote(owner || GPLAN.roleOrganiser())}>
          {/* Просят перенос НА КОНКРЕТНОЕ время: «давайте перенесём» без времени — не предложение,
              а вопрос, и голосовать по нему не о чем. */}
          <WhenPicker value={when} onChange={setWhen} />
          <Pressable accessibilityRole="button" style={s.primary} onPress={() => startVote('edit')}
                     accessibilityState={{ busy }}>
            {busy ? <ActivityIndicator color={color.onPrimary} />
                  : <Text style={s.primaryText}>{GPLAN.startVote()}</Text>}
          </Pressable>
          <Pressable accessibilityRole="button" style={s.secondary} onPress={() => startVote('cancel')}>
            <Text style={s.secondaryText}>{GPLAN.askCancel()}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.quiet} onPress={() => setAskVote(false)}>
            <Text style={s.quietText}>{GPLAN.notNow()}</Text>
          </Pressable>
        </PlanSheet>

        {/* GR.36 — голос. Совещательность повторена здесь же: человек читает это в момент выбора. */}
        <PlanSheet open={voteSheet} onClose={() => setVoteSheet(false)}
               title={GPLAN.voteSheetTitle(hoursLeft(vote?.closes_at), String(vote?.kind || 'edit'))}
               body={isOwner
                 ? GPLAN.voteOpenNoteMine(hoursLeft(vote?.closes_at))
                 : GPLAN.voteSheetNote(
                     String(vote?.by || ''),
                     String(vote?.proposal?.when || GPLAN.applyCancel()),
                     owner || GPLAN.roleOrganiser()
                   )}>
          {vote?.my_vote === undefined || vote?.my_vote === null ? (
            <>
              <Pressable accessibilityRole="button" style={s.primary} onPress={() => castVote(true)}
                         accessibilityState={{ busy }}>
                {busy ? <ActivityIndicator color={color.onPrimary} />
                      : <Text style={s.primaryText}>{GPLAN.voteYes(String(vote?.kind || 'edit'))}</Text>}
              </Pressable>
              <Pressable accessibilityRole="button" style={s.secondary} onPress={() => castVote(false)}>
                <Text style={s.secondaryText}>{GPLAN.voteNo()}</Text>
              </Pressable>
            </>
          ) : (
            <Text style={s.note}>{GPLAN.voted()}</Text>
          )}
        </PlanSheet>

        {/* GR.37 — числа и решение. Только организатору: у остальных этой кнопки на кадре нет. */}
        <PlanSheet open={decideSheet} onClose={() => setDecideSheet(false)}
               title={GPLAN.tally(Number(vote?.yes || 0), Number(vote?.no || 0),
                                  (vote?.waiting || []).length)}
               body={GPLAN.decideNote()}>
          <Pressable accessibilityRole="button" style={s.primary} onPress={() => decide(true)}
                     accessibilityState={{ busy }}>
            {busy ? <ActivityIndicator color={color.onPrimary} />
                  : <Text style={s.primaryText}>
                      {vote?.kind === 'cancel' ? GPLAN.applyCancel() : GPLAN.applyChange()}
                    </Text>}
          </Pressable>
          <Pressable accessibilityRole="button" style={s.secondary} onPress={() => decide(false)}>
            <Text style={s.secondaryText}>{GPLAN.keepIt()}</Text>
          </Pressable>
        </PlanSheet>
      </View>
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------- кадры

/**
 * Какой сейчас кадр борда. Один расчёт на весь экран: заголовок, пояснение и кнопки обязаны
 * говорить об одном и том же, а разложенные по трём условиям они разъезжаются — на GR.30 текст
 * про закрепление уже стоит, а кнопки ещё старые.
 *
 * Порядок проверок — от самого узкого к общему, и он же порядок приоритетов: личный выбор
 * («тебя зафиксировали», «прими или выйди») важнее общего состояния плана, потому что это
 * единственное, чего ждут именно от тебя.
 */
type Frame =
  | 'none' | 'proposed' | 'confirmed' | 'fix' | 'stayOrLeave' | 'acceptOrLeave'
  | 'voteOpen' | 'voteDecide' | 'voteWait' | 'locked' | 'below' | 'closed';

function frameOf(a: { plan: GPlan | null; vote: GVote | null; isOwner: boolean; owner: string; me: string }): Frame {
  const { plan, vote, isOwner } = a;
  if (!plan) return 'none';
  if (plan.state === 'cancelled' || plan.state === 'done') return 'closed';
  if (plan.state === 'locked') return 'locked';
  if (plan.state === 'below_quorum') return 'below';
  if (plan.stay_or_leave) return 'stayOrLeave';
  if (plan.accept_or_leave) return 'acceptOrLeave';
  if (vote?.state === 'open') return 'voteOpen';
  if (vote?.state === 'closed' && !vote?.decided) return isOwner ? 'voteDecide' : 'voteWait';
  if (plan.state === 'proposed') return plan.can_fix ? 'fix' : 'proposed';
  return 'confirmed';
}

function formTitle(
  mode: Mode, f: Frame,
  a: { plan: GPlan | null; vote: GVote | null; owner: string; online: boolean; proposer: string;
       isOwner: boolean }
): string {
  if (mode === 'create') return GPLAN.createTitle(a.online);
  if (mode === 'suggest') return GPLAN.suggestTitle();
  if (mode === 'update') return GPLAN.updateTitle();
  if (mode === 'link') return GPLAN.linkTitle();
  const p = a.plan || {};
  switch (f) {
    case 'none': return GPLAN.createTitle(a.online);
    case 'fix': {
      const yes = Number(p.confirmed_count || 0);
      return GPLAN.fixTitle(yes, Math.max(0, Number(p.needs || 0)));
    }
    case 'stayOrLeave': return GPLAN.fixedTitle(String(p.fixed_by || a.owner));
    case 'acceptOrLeave': return GPLAN.changedTitle(String(p.update?.by || a.owner));
    case 'voteOpen': return GPLAN.voteOpenTitle(String(a.vote?.by || ''), String(a.vote?.kind || 'edit'));
    case 'voteDecide': return GPLAN.closedTitle();
    case 'voteWait': return GPLAN.closedTitle();
    case 'proposed':
      // Первый раунд — это ещё «ждём всех»; со второго на борде заголовок называет предложившего.
      return a.proposer ? GPLAN.counteredTitle(a.proposer) : GPLAN.waitingTitle();
    case 'confirmed':
      // GRO.25a: для организатора отсутствие ссылки — это и есть заголовок. Для остальных нет:
      // они ничего с этим сделать не могут, им хватает плашки «ссылка будет» у карточки.
      return p.needs_link && a.isOwner ? GPLAN.linkTitle() : GPLAN.setTitle();
    // «План назначен» на плане, который упал ниже трёх, — прямая неправда: рядом на том же
    // экране написано, что осталось меньше трёх.
    case 'below': return GPLAN.belowTitle();
    case 'locked':
    case 'closed':
    default: return GPLAN.setTitle();
  }
}

function formNote(
  mode: Mode, f: Frame,
  a: { plan: GPlan | null; vote: GVote | null; owner: string; online: boolean; g: GroupInfo | null;
       isOwner: boolean }
): string {
  const p = a.plan || {};
  if (mode === 'create') return GPLAN.createNote();
  if (mode === 'suggest') {
    return GPLAN.suggestNote(Math.max(0, Number(p.max_rounds || 3) - Number(p.round || 1)));
  }
  if (mode === 'update') return GPLAN.updateNote(String(p.when || ''), T('новое время', 'the new time'));
  if (mode === 'link') return GPLAN.linkNote(String(p.when || ''));
  const total = Number(a.g?.joined_count || (a.g?.members || []).length || 0);
  switch (f) {
    case 'none': return GPLAN.createNote();
    case 'proposed':
      if (Number(p.round || 1) >= Number(p.max_rounds || 3)) return GPLAN.lastRoundNote(a.owner);
      if (Number(p.round || 1) > 1) return GPLAN.counteredNote(String(p.when || ''));
      return GPLAN.waitingNote(total);
    case 'fix': return GPLAN.fixNote(String(p.when || ''), (p.waiting || []).join(', '));
    case 'stayOrLeave': return GPLAN.fixedNote(String(p.when || ''), venue(p));
    case 'acceptOrLeave':
      return GPLAN.changedNote(String(p.update?.was?.when || ''), String(p.when || ''));
    case 'voteOpen':
      return a.isOwner
        ? GPLAN.voteOpenNoteMine(hoursLeft(a.vote?.closes_at))
        : GPLAN.voteOpenNote(hoursLeft(a.vote?.closes_at), a.owner);
    case 'voteDecide':
      return GPLAN.closedNoteOwner(Number(a.vote?.yes || 0), Number(a.vote?.no || 0),
                                   (a.vote?.waiting || []).length);
    case 'voteWait': return GPLAN.waitingDecision(a.owner);
    case 'locked': return GPLAN.locked();
    // Борд открывает вопрос («на паузе, решай»), а прежняя строка его закрывала («групповым
    // быть перестал»). Обещать человеку выбор и тут же говорить, что всё кончено, нельзя.
    case 'below': return GPLAN.belowNote();
    case 'closed': return GPLAN.cancelled();
    case 'confirmed':
      return p.needs_link && a.isOwner ? GPLAN.linkNote(String(p.when || '')) : GPLAN.setNote();
    default: return GPLAN.setNote();
  }
}

// ---------------------------------------------------------------- части

function Head({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <View style={s.head}>
      <Pressable accessibilityRole="button" accessibilityLabel={GPLAN.back()} style={s.back} onPress={onBack}>
        <IconChevronLeft />
      </Pressable>
      <Text style={s.headTitle} numberOfLines={1}>{title}</Text>
      {/* Противовес кнопке «назад», чтобы название стояло по центру. Именно пустое место, а не
          копия кнопки: круг с рамкой справа читается как действие, которого там нет. */}
      <View style={s.headSpacer} />
    </View>
  );
}

/** Карточка плана — «Plan Card» с борда: обложка, название, строка времени, строка места. */
function PlanCard({
  title, when, was, venueLine, online, placeUnchanged,
}: {
  title: string; when: string; was: string; venueLine: string; online: boolean; placeUnchanged: boolean;
}) {
  return (
    <View style={s.card}>
      <View style={s.cover} />
      <View style={s.cardBody}>
        <Text style={s.cardTitle} numberOfLines={1}>{title}</Text>
        <View style={s.cardRow}>
          <IconCalendar size={16} />
          <Text style={s.cardLine} numberOfLines={1}>
            {when || '—'}
            {was && was !== when ? <Text style={s.was}>{`  ·  ${GPLAN.wasLine(was)}`}</Text> : null}
          </Text>
        </View>
        <View style={s.cardRow}>
          {online ? <IconVideo size={16} c={color.muted} /> : <IconPin size={16} c={color.muted} />}
          <Text style={s.cardLine} numberOfLines={1}>
            {venueLine}
            {placeUnchanged ? <Text style={s.was}>{`  ·  ${GPLAN.unchanged()}`}</Text> : null}
          </Text>
        </View>
      </View>
    </View>
  );
}

/** «Round 2 of 3» — три полосы и подпись. На последнем раунде подпись говорит, что будет дальше. */
function RoundBar({ round, max }: { round: number; max: number }) {
  return (
    <View style={s.rounds}>
      <View style={s.bars}>
        {Array.from({ length: max }, (_, i) => (
          <View key={i} style={[s.bar, i < round && s.barOn]} />
        ))}
      </View>
      <Text style={s.roundText}>
        {round >= max ? GPLAN.lastRound() : GPLAN.round(round, max)}
      </Text>
    </View>
  );
}

/** Пара кнопок внизу. Ровно та, что на кадре: на борде их всегда две, и вторая всегда «мягкая». */
function Actions(a: {
  mode: Mode; view: Frame; busy: boolean; plan: GPlan | null; vote: GVote | null;
  online: boolean; leftForConfirm: number; isOwner: boolean;
  onCreateOpen: () => void;
  onCreate: () => void; onConfirm: () => void; onSuggestOpen: () => void; onSuggestSend: () => void;
  onFix: () => void; onStay: () => void; onLeave: () => void; onOpenChat: () => void;
  onAskVote: () => void; onOpenVote: () => void; onDecide: () => void;
  onInviteMore: () => void; onCancelPlan: () => void; onMoreTime: () => void;
  onUpdateOpen: () => void; onUpdateSend: () => void; onAccept: () => void;
  onLinkOpen: () => void; onLinkSave: () => void; onAskHost: () => void; onCancelForm: () => void;
}) {
  const P = ({ label, onPress }: { label: string; onPress: () => void }) => (
    <Pressable accessibilityRole="button" style={[s.primary, a.busy && { opacity: 0.6 }]}
               accessibilityState={{ busy: a.busy }} onPress={a.busy ? undefined : onPress}>
      {a.busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.primaryText}>{label}</Text>}
    </Pressable>
  );
  const S = ({ label, onPress }: { label: string; onPress: () => void }) => (
    <Pressable accessibilityRole="button" style={s.secondary} onPress={onPress}>
      <Text style={s.secondaryText}>{label}</Text>
    </Pressable>
  );

  if (a.mode === 'create') return <><P label={GPLAN.send()} onPress={a.onCreate} /><S label={GPLAN.back()} onPress={a.onCancelForm} /></>;
  if (a.mode === 'suggest') return <><P label={GPLAN.suggestSend()} onPress={a.onSuggestSend} /><S label={GPLAN.cancel()} onPress={a.onCancelForm} /></>;
  if (a.mode === 'update') return <><P label={GPLAN.sendUpdate()} onPress={a.onUpdateSend} /><S label={GPLAN.keepTerms()} onPress={a.onCancelForm} /></>;
  if (a.mode === 'link') return <><P label={GPLAN.saveLink()} onPress={a.onLinkSave} /><S label={GPLAN.askHost()} onPress={a.onAskHost} /></>;

  const p = a.plan;
  const mineDone = String(p?.my_response || '') === 'confirmed';

  switch (a.view) {
    case 'none':
      // Создать план может только организатор (сервер ответит NOT_ORGANIZER) — у остальных этой
      // кнопки на кадре и нет: они ждут, а не «не могут нажать».
      return a.isOwner
        ? <><P label={GPLAN.createTitle(a.online)} onPress={a.onCreateOpen} />
             <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>
        : <S label={GPLAN.openChat()} onPress={a.onOpenChat} />;
    case 'proposed':
      // На последнем раунде предлагать уже нечего: сервер откажет ROUNDS_USED_UP. Кнопка,
      // которая заведомо получит отказ, — обещание, которого приложение не выполнит.
      return mineDone
        ? <><Text style={s.dockNote}>{GPLAN.youConfirmed(a.leftForConfirm)}</Text>
            {p?.rounds_used_up ? null : <S label={GPLAN.suggest()} onPress={a.onSuggestOpen} />}</>
        : <><P label={GPLAN.confirm()} onPress={a.onConfirm} />
            {p?.rounds_used_up ? null : <S label={GPLAN.suggest()} onPress={a.onSuggestOpen} />}</>;
    case 'fix':
      // «Дать ещё время» — это «ничего не делать», а не «уйти в чат»: экран решения нужен здесь.
      return <><P label={GPLAN.fix()} onPress={a.onFix} />
               <S label={GPLAN.moreTime()} onPress={a.onMoreTime} /></>;
    case 'stayOrLeave':
      return <><P label={GPLAN.stay()} onPress={a.onStay} />
               <S label={GPLAN.leavePlan()} onPress={a.onLeave} /></>;
    case 'acceptOrLeave':
      return <><P label={GPLAN.accept()} onPress={a.onAccept} />
               <S label={GPLAN.leaveGroup()} onPress={a.onLeave} /></>;
    case 'voteOpen':
      return <><P label={GPLAN.openVote()} onPress={a.onOpenVote} />
               <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>;
    case 'voteDecide':
      return <><P label={GPLAN.decide()} onPress={a.onDecide} />
               <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>;
    case 'voteWait':
      return <S label={GPLAN.openChat()} onPress={a.onOpenChat} />;
    case 'confirmed':
      // GRO.25a: пока ссылки нет, главное действие организатора — вставить её, а не «открыть чат».
      if (p?.needs_link) {
        return <><P label={GPLAN.saveLink()} onPress={a.onLinkOpen} />
                 <S label={GPLAN.openChat()} onPress={a.onOpenChat} /></>;
      }
      return <><P label={GPLAN.openChat()} onPress={a.onOpenChat} />
               <S label={GPLAN.changeOrCancel()} onPress={a.onAskVote} /></>;
    // GR.40: три выхода с кадра. Раньше здесь была одна «открыть чат» — то есть выхода не было
    // ни одного, и план оставался на паузе навсегда.
    case 'below':
      return a.isOwner
        ? <><P label={GPLAN.inviteMore()} onPress={a.onInviteMore} />
             <S label={GPLAN.cancelPlan()} onPress={a.onCancelPlan} /></>
        : <S label={GPLAN.openChat()} onPress={a.onOpenChat} />;
    case 'locked':
    case 'closed':
    default:
      return <S label={GPLAN.openChat()} onPress={a.onOpenChat} />;
  }
}

/**
 * Лист группового плана: общий нижний лист плюс строка пояснения под заголовком — она есть у всех
 * листов этого экрана и у одного только этого экрана.
 */
function PlanSheet({
  open, onClose, title, body, children,
}: {
  open: boolean; onClose: () => void; title: string; body: string; children: React.ReactNode;
}) {
  return (
    <Sheet visible={open} onClose={onClose} title={title}>
      <Text style={s.sheetBody}>{body}</Text>
      {children}
    </Sheet>
  );
}

// ============================================================ вид
// Оформление UX-каркаса: значения — из токенов темы; при натягивании UI меняется этот блок.

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  headSpacer: { width: 40, height: 40 },
  headTitle: { flex: 1, ...type.title, color: color.fg, fontWeight: '700', textAlign: 'center' } as any,

  body: { paddingHorizontal: 20, paddingTop: space.sm, paddingBottom: space.xl, gap: space.md },
  title: { ...type.h2, color: color.fg } as any,
  note: { ...type.bodySmall, color: color.muted } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  fatal: { ...type.body, color: color.muted, paddingHorizontal: 20, paddingTop: space.lg } as any,

  card: { borderRadius: rad.xl, backgroundColor: color.card, borderWidth: 1, borderColor: color.border, overflow: 'hidden' },
  cover: { height: 72, backgroundColor: color.neutral100 },
  cardBody: { padding: space.lg, gap: space.sm },
  cardTitle: { ...type.title, color: color.fg } as any,
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  cardLine: { flex: 1, ...type.bodySmall, color: color.fg } as any,
  was: { color: color.muted },

  rounds: { gap: 6 },
  bars: { flexDirection: 'row', gap: 6 },
  bar: { flex: 1, height: 4, borderRadius: 2, backgroundColor: color.neutral100 },
  barOn: { backgroundColor: color.primary },
  roundText: { ...type.caption, color: color.muted } as any,

  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    paddingVertical: 6, paddingHorizontal: 12, borderRadius: rad.full, backgroundColor: color.infoBg,
  },
  badgeText: { ...type.caption, color: color.infoText } as any,
  warn: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: rad.md, backgroundColor: color.warnBg, alignSelf: 'flex-start' },
  warnText: { ...type.caption, color: color.warnText } as any,

  form: { gap: space.sm },
  input: {
    height: 48, borderRadius: rad.md, backgroundColor: color.card, borderWidth: 1,
    borderColor: color.border, paddingHorizontal: 14, color: color.fg, fontSize: 15,
  },

  roster: { gap: space.md, paddingTop: space.xs },
  memberRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  av: { width: 40, height: 40, borderRadius: rad.full },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  memberName: { ...type.body, color: color.fg } as any,
  memberState: { ...type.caption, color: color.muted } as any,

  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start' },
  linkText: { ...type.bodySmall, color: color.infoText } as any,

  dock: { paddingHorizontal: 16, paddingTop: space.sm, gap: space.sm, backgroundColor: color.bg },
  dockNote: { ...type.bodySmall, color: color.successText, textAlign: 'center' } as any,
  primary: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  primaryText: { ...type.button, color: color.onPrimary } as any,
  secondary: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { ...type.button, color: color.fg } as any,
  quiet: { height: 44, alignItems: 'center', justifyContent: 'center' },
  quietText: { ...type.bodySmall, color: color.muted } as any,

  sheetBody: { ...type.bodySmall, color: color.muted } as any,
});
