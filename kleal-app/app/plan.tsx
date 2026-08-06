/**
 * Встреча — кадры O.20–O.25, от предложения до отзыва.
 *
 * UX-КАРКАС: вид натянется поверх; копия, состояния и разбор — в src/chat.ts.
 *
 * Один экран на всю жизнь плана, а не шесть маршрутов. Так задумано: «Поправить план» и «Открыть
 * ссылку» — это одно и то же место в разное время, и разводить их значило бы, что человек, глядя
 * на встречу, каждый раз оказывается где-то ещё. Состояние считает planPhase:
 *
 *   форма      — плана ещё нет, выбираем время и место (O.20, первая половина);
 *   waiting    — отправлено, ждём ответа (O.20);
 *   confirmed  — оба подтвердили; ссылка придёт позже (O.21);
 *   soon       — за десять минут ссылка открывается (O.22);
 *   now        — время пришло (O.23);
 *   after      — «состоялось ли» и отзыв (O.24, O.25);
 *   cancelled  — кто-то отказался.
 *
 * Правила, которые держит СЕРВЕР, а не экран: ссылку он отдаёт только подтвердившим (OF.C3);
 * контрпредложение не отменяет встречу, старое время держится, пока второй не ответит; «состоялось
 * ли» и оценка пишутся одной записью, чтобы оценка не стёрла ответ про сам факт встречи.
 *
 * Правило, которое держит ЭКРАН: ссылка становится кнопкой за десять минут, не раньше. Она уже
 * пришла с сервера — это не защита, а фокус, и в этом разница с адресом, который сервер прячет
 * по-настоящему.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput, Image, ActivityIndicator,
  KeyboardAvoidingView, Platform, Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import {
  CHAT, PLAN, RATINGS, planWhen, personStatus, planPhase, minutesToStart, linkOpensAt,
} from '../src/chat';
import { DETAILS, dateChips, hhmm, deviceTz, tzOffsetLabel, looksLikeUrl } from '../src/intent';
import { TimeDial } from '../src/components/Dials';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { agent } from '../src/api';
import {
  IconChevronLeft, IconCalendar, IconClock, IconPin, IconLink, IconPerson, IconImagePlaceholder,
} from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

export default function Plan() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();

  const params = useLocalSearchParams<{ who?: string; title?: string; photo?: string; link?: string; id?: string }>();
  const other = String(params.who || '').trim();
  const intentTitle = String(params.title || '').trim();
  const photo = String(params.photo || '');
  const linkFromIntent = String(params.link || '').trim();
  const planId = String(params.id || '').trim();

  const me = String(st.profile.name || '');
  const ru = getLang() === 'ru';

  const [date, setDate] = useState(() => dateChips(1)[0].key);
  const [minutes, setMinutes] = useState(20 * 60);
  const [district, setDistrict] = useState(String(st.profile.city || ''));
  const [link, setLink] = useState(linkFromIntent);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [plan, setPlan] = useState<any>(null);
  /** Часы идут — экран сам переходит из «подтверждено» в «через десять минут» и дальше. */
  const [tick, setTick] = useState(Date.now());
  /** Ответы O.24/O.25, пока не отправлены. */
  const [rating, setRating] = useState('');
  const [thanks, setThanks] = useState('');
  /** O.20a: ссылка, которую доносят в уже согласованный план, и флаг «уже попросил(а) хостить». */
  const [linkDraft, setLinkDraft] = useState('');
  const [hostAsked, setHostAsked] = useState(false);
  /** O.21b: форма встречного времени. НЕ новая встреча — план живёт, изменение ложится рядом. */
  const [countering, setCountering] = useState(false);
  const dates = useMemo(() => dateChips(), []);

  const load = useCallback(async () => {
    if (!me) return;
    try {
      const r: any = await agent.plans(me);
      const all = [...(r?.plans || []), ...(r?.history || [])];
      const mine = planId
        ? all.find((p: any) => p.id === planId)
        : all.find((p: any) => (p.participants || []).some((x: any) => String(x.name || '') === other));
      if (mine) setPlan(mine);
    } catch {
      /* тихо: фоновая дотяжка */
    }
  }, [me, other, planId]);

  // Открытый по ссылке экран должен найти свой план сам — иначе «Открыть» из уведомления показывал
  // бы пустую форму поверх уже существующей встречи.
  useEffect(() => { if (planId || other) load(); }, [planId, other]);

  useEffect(() => {
    const id = setInterval(() => { setTick(Date.now()); load(); }, 15000);
    return () => clearInterval(id);
  }, [load]);

  const phase = plan ? planPhase(plan, tick) : null;
  const mine = plan ? myAnswer(plan) : undefined;
  const bothAnswered = !!plan?.their_feedback && mine !== undefined;
  /** O.21b: встречное время лежит РЯДОМ с планом (pending), сама встреча не тронута. */
  const pendingChange = plan?.pending || null;
  const cancelledByMe =
    !!plan?.cancelled_by
    && String(plan.cancelled_by).trim().toLowerCase() === me.trim().toLowerCase();
  /** O.20a: согласованный онлайн-план без ссылки — добавить может любой из двоих. */
  const needsLink = !!plan && plan.mode === 'online' && !plan.address_set
    && (phase === 'confirmed' || phase === 'soon' || phase === 'now');

  const propose = async () => {
    if (busy || !me || !other) return;
    setBusy(true);
    setErr('');
    try {
      const d = new Date(date + 'T00:00:00');
      d.setMinutes(minutes);
      const r: any = await agent.planPropose(me, other, {
        title: intentTitle || T('Встреча', 'Meetup'),
        mode: link ? 'online' : 'offline',
        starts_at: Math.floor(d.getTime() / 1000),
        when: planWhenLabel(date, minutes, ru),
        district: link ? '' : district,
        // Ссылка живёт в поле адреса: сервер открывает адрес только подтвердившим, и для звонка
        // это ровно то поведение, которое нужно.
        address: link,
      });
      if (!r?.ok) {
        if (r?.error === 'NOT_MATCHED') throw new Error(CHAT.notMatched());
        if (r?.error === 'IN_THE_PAST') throw new Error(CHAT.inThePast());
        if (r?.error === 'PLAN_EXISTS') throw new Error(CHAT.planExists());
        throw new Error(CHAT.planFailed());
      }
      // Сервер вернул план целиком — берём его сразу, не дожидаясь опроса.
      if (r.plan) setPlan(r.plan); else await load();
    } catch (e: any) {
      setErr(String(e?.message || CHAT.planFailed()));
    } finally {
      setBusy(false);
    }
  };

  const respond = async (action: string, extra: any = {}) => {
    if (!plan?.id) return;
    setErr('');
    try {
      const r: any = await agent.planRespond(plan.id, me, action, { version: plan.version, ...extra });
      if (!r?.ok) {
        if (r?.error === 'IN_THE_PAST') throw new Error(CHAT.inThePast());
        throw new Error(r?.error || 'failed');
      }
      await load();
    } catch (e: any) {
      setErr(e?.message === CHAT.inThePast() ? CHAT.inThePast() : CHAT.planFailed());
    }
  };

  /** O.21b: встречное время. Сервер паркует его рядом с планом; старое время держится до ответа. */
  const sendCounter = async () => {
    const d = new Date(date + 'T00:00:00');
    d.setMinutes(minutes);
    await respond('counter', {
      starts_at: Math.floor(d.getTime() / 1000),
      when: planWhenLabel(date, minutes, ru),
    });
    setCountering(false);
  };

  /** O.20a: донести ссылку в согласованный план. Сервер отдаст её обоим по правилу OF.C3. */
  const saveLink = async () => {
    const v = linkDraft.trim();
    if (!plan?.id || !looksLikeUrl(v)) return;
    setErr('');
    try {
      const r: any = await agent.planAddress(plan.id, me, v);
      if (!r?.ok) throw new Error(r?.error || 'failed');
      setLinkDraft('');
      await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  /** O.20a: «пусть хостит он(а)» — настоящее сообщение в чат, а не нажатая в пустоту кнопка. */
  const askHost = async () => {
    if (!plan?.id || hostAsked) return;
    setErr('');
    try {
      const r: any = await agent.message(me, other, PLAN.askHostMsg());
      if (!r?.ok) throw new Error('failed');
      setHostAsked(true);
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  const answerHappened = async (happened: boolean) => {
    if (!plan?.id) return;
    try {
      await agent.planFeedback(plan.id, me, { happened });
      await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  const sendRating = async () => {
    if (!plan?.id) return;
    try {
      const value = RATINGS.find(([k]) => k === rating)?.[2];
      await agent.planFeedback(plan.id, me, { rating: value });
      setThanks(PLAN.thanks());
      await load();
    } catch {
      setErr(CHAT.planFailed());
    }
  };

  const openChat = () =>
    router.push({ pathname: '/conversation', params: { who: other, title: intentTitle, photo } });

  /** Ссылка, как её отдал сервер: до подтверждения её просто нет в ответе. */
  const serverLink = String(plan?.address || '');
  const linkReady = phase === 'soon' || phase === 'now';

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={() => router.back()}>
            <IconChevronLeft />
          </Pressable>
          <Text style={s.headTitle} numberOfLines={1}>{intentTitle || T('Встреча', 'Meetup')}</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView contentContainerStyle={[s.body, { paddingBottom: 130 }]} keyboardShouldPersistTaps="handled" scrollEnabled={!dragging}>
          {!plan ? (
            <PlanForm
              dates={dates} date={date} setDate={setDate}
              minutes={minutes} setMinutes={setMinutes} setDragging={setDragging}
              district={district} setDistrict={setDistrict}
              link={link} setLink={setLink}
              busy={busy} err={err} onPropose={propose}
            />
          ) : (
            <>
              <Text style={s.title}>{headline(phase!, other, plan, me)}</Text>
              <Text style={s.note}>{subline(phase!, other, plan, ru, me)}</Text>

              <View style={s.card}>
                <View style={s.cover}><IconImagePlaceholder size={40} /></View>
                <View style={s.metaRow}>
                  <IconCalendar />
                  <Text style={s.metaText}>{planWhen(plan, ru)} {tzOffsetLabel(deviceTz())}</Text>
                </View>
                {/* O.21b: предложенное время стоит РЯДОМ со старым — обе строки видны разом. */}
                {pendingChange ? (
                  <View style={s.metaRow}>
                    <IconClock size={16} c={color.primary} />
                    <Text style={[s.metaText, { color: color.primary }]}>
                      {PLAN.newPrefix(planWhen(pendingChange, ru))}
                    </Text>
                  </View>
                ) : null}
                {plan.district ? (
                  <View style={s.metaRow}>
                    <IconPin size={16} c={color.muted} />
                    <Text style={s.metaText}>{plan.district}</Text>
                  </View>
                ) : null}
                {plan.mode === 'online' || serverLink ? (
                  <View style={s.metaRow}>
                    <IconLink size={16} c={color.muted} />
                    {/* Когда ссылка открыта, об этом говорит зелёная карточка ниже — здесь только факт
                        формата, иначе одна и та же фраза стоит на экране дважды. */}
                    <Text style={s.metaText}>
                      {phase === 'after' || phase === 'cancelled'
                        // Встреча позади — обещать, что ссылка «откроется в 18:14», уже неправда.
                        ? PLAN.modeOnline()
                        // O.20a: ссылки ещё нет — врать «откроется в …» нечем.
                        : !plan.address_set ? PLAN.noLinkYet()
                        : linkReady ? PLAN.linkSaved() : PLAN.linkOpensLabel(linkOpensAt(plan, ru))}
                    </Text>
                  </View>
                ) : null}
              </View>

              {/* O.22/O.23: ссылка становится кнопкой только теперь — см. шапку файла. */}
              {linkReady && serverLink ? (
                <View style={s.linkCard}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.linkTitle}>{PLAN.linkOpenNow()}</Text>
                    <Text style={s.linkSub}>{PLAN.leavesKleal()}</Text>
                  </View>
                  <Pressable
                    accessibilityRole="button"
                    style={s.linkBtn}
                    onPress={() => Linking.openURL(serverLink).catch(() => setErr(CHAT.planFailed()))}
                  >
                    <Text style={s.linkBtnText}>{PLAN.openLink()}</Text>
                  </Pressable>
                </View>
              ) : null}

              {/* O.23a: короткая строка факта — что, когда и кто отменил — и сразу выход в новое время. */}
              {phase === 'cancelled' ? (
                <View style={s.pillRow}>
                  <View style={s.pill}>
                    <Text style={s.pillText} numberOfLines={2}>
                      {(plan.mode === 'online' ? PLAN.modeOnline() : (plan.district || T('Встреча', 'Meetup')))}
                      {' · '}{planWhen(plan, ru)}
                      {' · '}{cancelledByMe ? PLAN.calledOffByYou() : PLAN.calledOffBy(other)}
                    </Text>
                  </View>
                  <Pressable accessibilityRole="button" style={s.pillBtn} onPress={() => setPlan(null)}>
                    <Text style={s.pillBtnText}>{PLAN.anotherTime()}</Text>
                  </Pressable>
                </View>
              ) : null}

              {(plan.participants || []).map((p: any, i: number) => (
                <View key={(p.name || '') + i} style={s.person}>
                  {p.photo ? (
                    <Image source={{ uri: p.photo }} style={s.personAva} />
                  ) : (
                    <View style={[s.personAva, s.personAvaEmpty]}><IconPerson size={18} /></View>
                  )}
                  <View style={{ flex: 1 }}>
                    <Text style={s.personName}>{p.name}{p.age ? `, ${p.age}` : ''}</Text>
                    <Text style={s.personStatus}>{statusFor(p, plan, phase!, pendingChange)}</Text>
                  </View>
                  <IconClock size={18} c={color.neutral400} />
                </View>
              ))}

              {phase === 'soon' || phase === 'now' ? (
                <View style={s.infoBox}><Text style={s.infoText}>{PLAN.outsideNote()}</Text></View>
              ) : null}

              {err ? <Text style={s.err}>{err}</Text> : null}

              {/* O.24: спрашиваем оба факта до оценки — оценка без ответа про сам факт бессмысленна. */}
              {phase === 'after' && mine === undefined ? (
                <>
                  <View style={s.infoBox}><Text style={s.infoText}>{PLAN.didItNote(other)}</Text></View>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={() => answerHappened(true)}>
                    <Text style={s.ctaText}>{PLAN.yesWeTalked()}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => answerHappened(false)}>
                    <Text style={s.ctaDarkText}>{PLAN.noItDidnt()}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* O.25: отзыв — только после того, как сам ответил про факт встречи. */}
              {phase === 'after' && mine === true ? (
                thanks || myRated(plan) ? (
                  // «Спасибо» уже стоит в заголовке — здесь остаётся только то, чего там нет.
                  !bothAnswered ? <Text style={s.note}>{PLAN.waitingBoth()}</Text> : null
                ) : (
                  <>
                    <Text style={s.note}>{PLAN.optional()}</Text>
                    <View style={s.chipRowWrap}>
                      {RATINGS.map(([k, label]) => (
                        <Pressable
                          key={k}
                          accessibilityRole="button"
                          accessibilityState={{ selected: rating === k }}
                          onPress={() => setRating(k)}
                          style={[s.chip, rating === k && s.chipOn]}
                        >
                          <Text style={[s.chipText, rating === k && { color: color.onPrimary }]}>{label()}</Text>
                        </Pressable>
                      ))}
                    </View>
                    <Pressable accessibilityRole="button" style={s.cta} onPress={sendRating}>
                      <Text style={s.ctaText}>{PLAN.send()}</Text>
                    </Pressable>
                    <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => router.push('/profile/safety')}>
                      <Text style={s.ctaDarkText}>{PLAN.reportProblem()}</Text>
                    </Pressable>
                  </>
                )
              ) : null}

              {phase === 'after' && mine === false ? (
                <Text style={s.note}>{bothAnswered ? PLAN.thanks() : PLAN.waitingBoth()}</Text>
              ) : null}

              {/* O.20a: поле и две кнопки — ссылка или просьба хостить. Пока висит перенос, не показываем:
                  сперва договориться о времени, потом нести ссылку. */}
              {needsLink && !pendingChange && !countering ? (
                <>
                  <TextInput
                    style={s.input}
                    value={linkDraft}
                    onChangeText={setLinkDraft}
                    placeholder={PLAN.pasteLink()}
                    placeholderTextColor={color.neutral400}
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="url"
                    accessibilityLabel={PLAN.pasteLink()}
                  />
                  <Pressable
                    accessibilityRole="button"
                    disabled={!looksLikeUrl(linkDraft.trim())}
                    accessibilityState={{ disabled: !looksLikeUrl(linkDraft.trim()) }}
                    style={[s.cta, !looksLikeUrl(linkDraft.trim()) && { opacity: 0.45 }]}
                    onPress={saveLink}
                  >
                    <Text style={s.ctaText}>{PLAN.saveLink()}</Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    disabled={hostAsked}
                    accessibilityState={{ disabled: hostAsked }}
                    style={[s.ctaDark, hostAsked && { opacity: 0.45 }]}
                    onPress={askHost}
                  >
                    <Text style={s.ctaDarkText}>{hostAsked ? PLAN.hostAskedNote() : PLAN.askHost(other)}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* Форма встречного времени: та же дата и циферблат, но уходит counter-ом — план живёт. */}
              {countering ? (
                <View style={s.card}>
                  <View style={s.labelRow}>
                    <IconCalendar />
                    <Text style={s.label}>{DETAILS.date()}</Text>
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
                    {dates.map((d: any) => (
                      <Pressable
                        key={d.key}
                        accessibilityRole="button"
                        accessibilityState={{ selected: date === d.key }}
                        onPress={() => setDate(d.key)}
                        style={[s.chip, date === d.key && s.chipOn]}
                      >
                        <Text style={[s.chipText, date === d.key && { color: color.onPrimary }]}>{d.label}</Text>
                      </Pressable>
                    ))}
                  </ScrollView>
                  <View style={s.labelRow}>
                    <IconClock />
                    <Text style={s.label}>{DETAILS.time()}</Text>
                  </View>
                  <TimeDial minutes={minutes} onChange={setMinutes} onDragChange={setDragging} />
                  <Text style={s.tz}>{hhmm(minutes)} {tzOffsetLabel(deviceTz())}</Text>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={sendCounter}>
                    <Text style={s.ctaText}>{PLAN.sendNewTime()}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setCountering(false)}>
                    <Text style={s.ctaDarkText}>{DETAILS.cancel()}</Text>
                  </Pressable>
                </View>
              ) : null}

              {/* Действия до встречи. «Другое время» — это counter (O.21b), а не новая встреча:
                  propose на живом плане честно бьётся об PLAN_EXISTS. Пока экран просит ссылку
                  (O.20a), на кадре стоят только её две кнопки — эти прячутся. */}
              {(phase === 'waiting' || phase === 'confirmed') && !pendingChange && !countering && !needsLink ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{CHAT.openChat()}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => setCountering(true)}>
                    <Text style={s.ctaDarkText}>
                      {phase === 'confirmed' ? PLAN.suggestAnother() : CHAT.changePlan()}
                    </Text>
                  </Pressable>
                </>
              ) : null}

              {/* O.21b: моё встречное время ждёт ответа — можно забрать, пока второй не ответил. */}
              {(phase === 'waiting' || phase === 'confirmed') && pendingChange?.mine ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{CHAT.openChat()}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => respond('reject_change')}>
                    <Text style={s.ctaDarkText}>{PLAN.takeItBack()}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* Встречное время, пришедшее МНЕ. Кадра этой стороны в пачке нет — кнопки строго по
                  контракту сервера (accept_change / reject_change), придёт кадр — уточним вид. */}
              {(phase === 'waiting' || phase === 'confirmed') && pendingChange && !pendingChange.mine ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={() => respond('accept_change')}>
                    <Text style={s.ctaText}>{PLAN.acceptNewTime()}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => respond('reject_change')}>
                    <Text style={s.ctaDarkText}>{PLAN.keepOldTime()}</Text>
                  </Pressable>
                </>
              ) : null}

              {phase === 'soon' || phase === 'now' ? (
                <>
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{PLAN.messageThem(other)}</Text>
                  </Pressable>
                  <Pressable accessibilityRole="button" style={s.ctaDark} onPress={() => respond('decline')}>
                    <Text style={s.ctaDarkText}>{PLAN.cantMakeIt()}</Text>
                  </Pressable>
                </>
              ) : null}

              {/* O.23a: никого не оставили ждать; чат живёт — новое время договаривается там. */}
              {phase === 'cancelled' ? (
                <>
                  {cancelledByMe ? (
                    <View style={s.infoBox}><Text style={s.infoText}>{PLAN.nobodyWaiting(other)}</Text></View>
                  ) : null}
                  <Pressable accessibilityRole="button" style={s.cta} onPress={openChat}>
                    <Text style={s.ctaText}>{CHAT.openChat()}</Text>
                  </Pressable>
                </>
              ) : null}

              {phase === 'confirmed' && !myConfirmed(plan, me) ? (
                <Pressable accessibilityRole="button" style={s.cta} onPress={() => respond('confirm')}>
                  <Text style={s.ctaText}>{PLAN.confirmed()}</Text>
                </Pressable>
              ) : null}
            </>
          )}
        </ScrollView>

        <View style={s.navFloat} pointerEvents="box-none">
          <BottomNav />
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

/** Ответил ли я сам про факт встречи. undefined — ещё нет.
 *  Читаем `my_feedback`: сервер отдаёт наружу только МОЮ строку отзыва, чужая не покидает сервер. */
function myAnswer(plan: any): boolean | undefined {
  const row = plan?.my_feedback;
  if (!row || row.happened === undefined || row.happened === null) return undefined;
  return !!row.happened;
}

/** Оценку я уже отправил. Держим это по серверу, а не по локальному флагу: иначе после обновления
 *  экрана форма оценки просилась бы во второй раз, хотя оценка уже записана. */
function myRated(plan: any): boolean {
  const row = plan?.my_feedback;
  return !!(row && (row.rating || row.text));
}

function myConfirmed(plan: any, me: string): boolean {
  return (plan?.participants || []).some(
    (p: any) => String(p.name || '').toLowerCase() === String(me).toLowerCase() && p.confirmed
  );
}

function headline(phase: string, other: string, plan: any, me: string): string {
  // O.21b важнее всего остального в шапке: пока висит встречное время, экран говорит о нём.
  if ((phase === 'waiting' || phase === 'confirmed') && plan?.pending) {
    return plan.pending.mine ? PLAN.newTimeSent(other) : PLAN.newTimeToYou(other);
  }
  // O.20a: согласовано, а звонку негде пройти — экран первым делом просит ссылку.
  if (phase === 'confirmed' && plan?.mode === 'online' && !plan?.address_set) {
    return PLAN.addLinkTitle();
  }
  switch (phase) {
    case 'waiting': return CHAT.sentTo(other);
    case 'confirmed': return PLAN.confirmed();
    case 'soon': return PLAN.startsIn(minutesToStart(plan));
    case 'now': return PLAN.startsNow();
    // O.24 и O.25 — это один экран в двух состояниях, и заголовок должен показывать, на каком
    // вопросе мы стоим: сперва «состоялась ли», потом «как прошло», потом благодарность.
    case 'after': {
      const mine = myAnswer(plan);
      if (mine === undefined) return PLAN.didItHappen();
      if (mine === true && !myRated(plan)) return PLAN.howWasIt();
      return PLAN.thanks();
    }
    // O.23a: у отмены есть автор, и заголовок называет его. Старые планы без cancelled_by
    // остаются с безличной строкой — выдумывать автора не из чего.
    case 'cancelled': {
      const by = String(plan?.cancelled_by || '').trim().toLowerCase();
      if (!by) return T('Встреча отменена', 'The meetup is off');
      return by === String(me).trim().toLowerCase()
        ? PLAN.youToldCantMake(other)
        : PLAN.theyCantMake(other);
    }
    default: return '';
  }
}

function subline(phase: string, other: string, plan: any, ru: boolean, me: string): string {
  if ((phase === 'waiting' || phase === 'confirmed') && plan?.pending) {
    // O.21b обеим сторонам объясняет одно и то же правило, каждой со своей стороны.
    return plan.pending.mine ? PLAN.newTimeNote(other) : PLAN.oldTimeHolds();
  }
  if (phase === 'confirmed' && plan?.mode === 'online' && !plan?.address_set) {
    return PLAN.addLinkNote(planWhen(plan, ru), other);
  }
  switch (phase) {
    case 'waiting': return CHAT.sentNote(other);
    case 'confirmed': return PLAN.linkOpensAt(linkOpensAt(plan, ru));
    case 'soon':
    case 'now': return PLAN.linkNote();
    case 'after': return '';
    case 'cancelled': {
      const by = String(plan?.cancelled_by || '').trim().toLowerCase();
      // Отменил я — записка «никто не ждёт» стоит ниже, в рамке; дублировать её здесь незачем.
      if (by && by === String(me).trim().toLowerCase()) return '';
      return T('Время освободилось. Можно предложить другое.', 'The slot is free. You can suggest another time.');
    }
    default: return '';
  }
}

/**
 * Статус строки участника. Поверх обычного personStatus живут два особых случая:
 * O.21b — пока висит встречное время, у предложившего «ждёшь», у второго «не ответил(а)»;
 * O.23a — в отменённом плане у автора отмены «не сможет», у второго «узнал(а) только что».
 */
function statusFor(p: any, plan: any, phase: string, pendingChange: any): string {
  const name = String(p?.name || '').trim().toLowerCase();
  if (phase === 'cancelled') {
    const by = String(plan?.cancelled_by || '').trim().toLowerCase();
    if (by) return name === by ? PLAN.cantMakeStatus() : PLAN.toldJustNow();
    return personStatus(p);
  }
  if (pendingChange) {
    const by = String(pendingChange.by || '').trim().toLowerCase();
    return name === by ? PLAN.waitingOldTime() : PLAN.notAnsweredNewTime();
  }
  return personStatus(p);
}

/** Форма плана — первая половина кадра O.20. */
function PlanForm({
  dates, date, setDate, minutes, setMinutes, setDragging,
  district, setDistrict, link, setLink, busy, err, onPropose,
}: any) {
  return (
    <View style={s.card}>
      <View style={s.labelRow}>
        <IconCalendar />
        <Text style={s.label}>{DETAILS.date()}</Text>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
        {dates.map((d: any) => (
          <Pressable
            key={d.key}
            accessibilityRole="button"
            accessibilityState={{ selected: date === d.key }}
            onPress={() => setDate(d.key)}
            style={[s.chip, date === d.key && s.chipOn]}
          >
            <Text style={[s.chipText, date === d.key && { color: color.onPrimary }]}>{d.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <View style={s.labelRow}>
        <IconClock />
        <Text style={s.label}>{DETAILS.time()}</Text>
      </View>
      <TimeDial minutes={minutes} onChange={setMinutes} onDragChange={setDragging} />
      <Text style={s.tz}>{hhmm(minutes)} {tzOffsetLabel(deviceTz())}</Text>

      <View style={s.labelRow}>
        <IconLink size={18} c={color.fg} />
        <Text style={s.label}>{DETAILS.link()}</Text>
      </View>
      <TextInput
        style={s.input}
        value={link}
        onChangeText={setLink}
        placeholder={DETAILS.linkPlaceholder()}
        placeholderTextColor={color.neutral400}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        accessibilityLabel={DETAILS.link()}
      />

      {/* Место спрашиваем только у встречи вживую: у звонка его нет. */}
      {!link ? (
        <>
          <View style={s.labelRow}>
            <IconPin size={18} c={color.fg} />
            <Text style={s.label}>{DETAILS.district()}</Text>
          </View>
          <TextInput
            style={s.input}
            value={district}
            onChangeText={setDistrict}
            placeholder="Gràcia"
            placeholderTextColor={color.neutral400}
            accessibilityLabel={DETAILS.district()}
          />
        </>
      ) : null}

      {err ? <Text style={s.err}>{err}</Text> : null}

      <Pressable
        accessibilityRole="button"
        accessibilityState={{ busy, disabled: !!link && !looksLikeUrl(link) }}
        disabled={!!link && !looksLikeUrl(link)}
        style={[s.cta, !!link && !looksLikeUrl(link) && { opacity: 0.45 }]}
        onPress={busy ? undefined : onPropose}
      >
        {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{CHAT.createPlan()}</Text>}
      </Pressable>
    </View>
  );
}

/** Человеческая подпись времени для поля `when` — сервер хранит её как есть и показывает обоим. */
function planWhenLabel(dateKey: string, minutes: number, ru: boolean): string {
  const d = new Date(dateKey + 'T12:00:00');
  const day = d.toLocaleDateString(ru ? 'ru-RU' : 'en-US', { weekday: 'short', day: 'numeric', month: 'short' });
  return `${day} · ${hhmm(minutes)}`;
}

// ============================================================ вид

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 16, paddingBottom: space.sm },
  back: {
    width: 40, height: 40, borderRadius: 20, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  headTitle: { flex: 1, ...type.title, color: color.fg, textAlign: 'center' } as any,

  body: { paddingHorizontal: 20, gap: space.md },
  title: { fontSize: 20, fontWeight: '700', color: color.fg, marginTop: space.sm },
  note: { ...type.bodySmall, color: color.muted } as any,

  card: { backgroundColor: color.card, borderRadius: rad.xl, padding: space.lg, gap: space.md },
  cover: { height: 110, borderRadius: rad.lg, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  labelRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { ...type.labelMedium, color: color.fg, fontWeight: '600' } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  metaText: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  tz: { ...type.bodySmall, color: color.muted, textAlign: 'center' } as any,

  linkCard: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: color.successBg, borderRadius: rad.lg, padding: space.md,
  },
  linkTitle: { ...type.labelMedium, color: color.successText, fontWeight: '700' } as any,
  linkSub: { ...type.caption, color: color.successText } as any,
  linkBtn: { height: 40, paddingHorizontal: 18, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  linkBtnText: { ...type.labelMedium, color: color.onPrimary, fontWeight: '700' } as any,

  infoBox: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md },
  infoText: { ...type.bodySmall, color: color.infoText } as any,

  // O.23a: зелёная строка факта отмены и кнопка «Другое время» рядом.
  pillRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  pill: {
    flex: 1, backgroundColor: color.successBg, borderRadius: rad.full,
    paddingVertical: 10, paddingHorizontal: 14,
  },
  pillText: { ...type.caption, color: color.successText, fontWeight: '600' } as any,
  pillBtn: {
    height: 40, paddingHorizontal: 14, borderRadius: rad.full,
    backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center',
  },
  pillBtnText: { ...type.labelMedium, color: '#fff', fontWeight: '600' } as any,

  chipRow: { gap: space.sm, paddingVertical: 2 },
  chipRowWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  input: {
    height: 46, borderRadius: rad.md, backgroundColor: color.neutral100,
    paddingHorizontal: 14, color: color.fg, fontSize: 15,
  },

  person: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    backgroundColor: color.card, borderRadius: rad.lg, padding: space.md,
  },
  personAva: { width: 40, height: 40, borderRadius: 20 },
  personAvaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  personName: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  personStatus: { ...type.caption, color: color.muted } as any,

  cta: { height: 52, borderRadius: rad.full, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button, color: color.onPrimary } as any,
  ctaDark: { height: 52, borderRadius: rad.full, backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  ctaDarkText: { ...type.button, color: '#fff' } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
