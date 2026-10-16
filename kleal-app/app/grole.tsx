/**
 * Смена организатора — кадры GR.42–GR.44 борда «GR · Offline — new layout» (5828:9353).
 *
 * ОДИН ЭКРАН НА ВСЕ СТОРОНЫ. Раскладка у всех кадров общая (как у плана и «Who's in»): название
 * затеи в шапке, заголовок и пояснение, карточка затеи, полоса «Vote 0 of 1 · Ends in 6h» или
 * «Offer 0 of 1 · Ends in 24h», состав со статусами, кнопки под составом. Меняются слова, статусы
 * и кнопки — какой кадр, решает `roleView` (src/roles.ts) по данным сервера и тому, кто смотрит.
 *
 * Итоги (прошло, не прошло, организатор вернулся) приходят листом поверх страницы — один раз на
 * исход, как на борде (GR.43c/i/f, 43l/n/p, 44k).
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Image, Pressable, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams, useIsFocused } from 'expo-router';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { group as gapi, mediaUrl, ensureMe, myId, isMe, pidOf, newIdem, type GroupInfo } from '../src/api';
import { ROOM, GINVITE, groupPlace, groupCallLine, isOnlineGroup } from '../src/groups';
import { ROLE, roleView, type RoleView } from '../src/roles';
import { elapsed, hoursLeft } from '../src/gplan';
import { usePolling } from '../src/polling';
import { IconCalendar, IconCheck, IconClock, IconMoon, IconPerson, IconPin, IconShieldCheck, IconVideo } from '../src/components/icons';
import { color, font, heading, labelFamily, space, type } from '../src/theme';
import { Cover } from '../src/components/Cover';
import { GlassPill } from '../src/components/Glass';
import { GlassBack, GlassSurface } from '../src/components/LiquidGlass';
import { BottomNav } from '../src/components/BottomNav';
import { Sheet, SheetText } from '../src/components/Sheet';
import { useNavCollapse } from '../src/navScroll';

const INK = '#181B22';
const eq = (a?: string, b?: string) => !!String(a || '').trim() && String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();

/** «6h», «3h 31m», «45m». */
function span(sec: number): string {
  const m = Math.max(0, Math.round(sec / 60));
  const h = Math.floor(m / 60);
  if (h >= 1) return m % 60 ? `${h}${T('ч', 'h', 'h')} ${m % 60}${T('м', 'm', 'm')}` : `${h}${T('ч', 'h', 'h')}`;
  return `${m}${T('м', 'm', 'm')}`;
}

function hhmm(sec: number): string {
  const d = new Date(sec * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function splitWhen(when: string): [string, string] {
  const m = when.match(/^(.*?)\s*(?:·|,)\s*(\d{1,2}[:.]\d{2}(?:\s*[AaPp][Mm])?)$/);
  return m ? [m[1], m[2]] : [when, ''];
}

type Tone = 'ink' | 'warn' | 'muted' | 'ok' | 'turn';
const NUM_EN = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];

export default function GroupRole() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const focused = useIsFocused();
  const params = useLocalSearchParams<{ gid?: string; pick?: string }>();
  const gid = String(params.gid || '').trim();
  const me = String(st.profile.name || '');
  const [gRaw, setG] = useState<GroupInfo | null>(null);
  // Данные прежней группы живут ещё кадр после смены gid (сброс — эффектом). По ним экран решал
  // «про роль ничего» и уводил в чат новой группы. Чужую группу не показываем вовсе.
  const gOf = String((gRaw as any)?.gid || (gRaw as any)?.id || '');
  const g = gRaw && (!gOf || gOf === gid) ? gRaw : null;
  const [gone, setGone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [pickedRaw, setPicked] = useState<{ name: string; id: string } | null>(null);
  const [sheet, setSheet] = useState<'' | 'put' | 'withdraw' | 'vote' | 'keepWith' | 'leave' | 'already'>('');
  const [seen, setSeen] = useState<Set<string>>(new Set());
  const [meId, setMeId] = useState(myId());
  // Экран единственный и переживает смену входа — id перечитывается, когда сменился человек.
  useEffect(() => { setMeId(myId()); ensureMe().then(setMeId); }, [me]);

  const load = useCallback(async () => {
    if (!gid || !me) return;
    try {
      const r: any = await gapi.get(gid, me);
      if (r?.group) setG(r.group); else if (r?.error || r?.ok === false) setGone(true);
    } catch { /* фоновый опрос — молча */ }
  }, [gid, me]);
  useEffect(() => { load(); }, [load]);
  usePolling(load, 6000, !gone);

  // Другая группа или другой человек — чистый экран (маршрут единственный, см. app/group.tsx; экран
  // переживает и смену входа — открытый лист Marc'а доставался Mateo).
  const shownKey = useRef(`${gid}|${me}`);
  useEffect(() => {
    if (shownKey.current === `${gid}|${me}`) return;
    shownKey.current = `${gid}|${me}`;
    setG(null); setGone(false); setErr(''); setPicked(null); setSheet('');
  }, [gid, me]);

  const view: RoleView = useMemo(() => roleView(g, me, meId, params.pick === '1'), [g, me, meId, params.pick]);
  const gg: any = g || {};
  const t = gg.takeover || {};
  const o = gg.role_offer || {};
  const rf = gg.role_from || {};
  const owner = String(gg.owner || '');
  const ownerId = String(gg.owner_id || '');
  const cand = String(t.by || '');
  const candId = String(t.by_id || '');
  const members = ((gg.members || []) as any[]);
  const others = members.filter((m) => !isMe(m.name, pidOf(m, 'name'), me));
  const mine = members.filter((m) => isMe(m.name, pidOf(m, 'name'), me));
  const voters = others.filter((m) => !eq(m.name, owner) && !eq(m.name, cand)).map((m) => String(m.name));
  const former = String(rf.who || '');
  const silentH = Math.max(12, Number(gg.organiser_silent_h || t.silent_h || 12));
  const now = Date.now() / 1000;
  // GR.44b: первый из группы уже выбран — «Offer it to Jane» готова сразу, касание меняет выбор.
  const picked = pickedRaw || (others[0] ? { name: String(others[0].name || ''), id: pidOf(others[0], 'name') } : null);
  const nextToOffer = others.filter((m) => !eq(m.name, o.to) && !(o.declined || []).some((d: string) => eq(d, m.name)))[0];

  // Итог голосования приходит листом поверх того, что человек видел до конца (борд GR.43c/i/f/l/n/p):
  // под листом — прежний экран, полоса «Ended»/«Stopped», организатор — прежний. Закрыл лист — итог.
  const resultKey = t.id && t.resolved ? `${t.id}:${t.state}` : '';
  const sheetUp = focused && !!resultKey && !seen.has(resultKey);
  const voteSide: RoleView = t.my_vote === true || t.my_vote === false ? 'voted' : 'voteNeeded';
  const pre: RoleView | '' = !sheetUp ? ''
    : view === 'youOrganiser' ? (rf.how === 'vote' ? 'candidate' : '')
    : view === 'failedCand' || view === 'stoppedCand' ? 'candidate'
    : view === 'otherPassed' || view === 'failedOther' || view === 'stoppedOther' ? voteSide : '';
  const shown: RoleView = pre || view;
  const passedBehind = !!pre && t.state === 'passed';
  const ow = passedBehind ? former : owner;
  const owId = passedBehind ? String(rf.who_id || '') : ownerId;
  // «Exact spot after everyone confirms» — подсказка тем, кто место не ставит. Организатору, бывшему
  // организатору и тому, кому роль сейчас предлагают, её на борде нет (GR.42a, 44–44i, 44k–m).
  const iAmOrg = isMe(ow, owId, me);
  const wasOrg = !passedBehind && !!former && isMe(former, String(rf.who_id || ''), me);
  const showExact = !iAmOrg && !wasOrg && view !== 'offerToMe';

  const act = async (fn: () => Promise<any>, after?: () => void) => {
    if (busy) return;
    setBusy(true); setErr('');
    try {
      const r: any = await fn();
      if (r?.group) setG(r.group);
      if (r?.ok === false) {
        if (r.error === 'OFFER_EXISTS') { setSheet('already'); await load(); return; }
        setErr(T('Не получилось. Попробуй ещё раз.', 'That didn’t work. Try again.', 'No funcionó. Inténtalo de nuevo.'));
        return;
      }
      after?.();
      await load();
    } catch {
      setErr(T('Не получилось. Попробуй ещё раз.', 'That didn’t work. Try again.', 'No funcionó. Inténtalo de nuevo.'));
    } finally {
      setBusy(false);
    }
  };
  const toChat = () => router.dismissTo({ pathname: '/group', params: { gid } });
  const toPlan = () => router.navigate({ pathname: '/gplan', params: { gid } });

  // ---- заголовок и пояснение ---------------------------------------------
  const yesVote = t.my_vote === true;
  const head = ((): [string, string] => {
    const res = t.result || {};
    switch (shown) {
      case 'silent': return [ROLE.silentTitle(owner), ROLE.silentNote(owner, silentH)];
      case 'candidate': return [ROLE.candTitle(), ROLE.candNote(ow, ROOM.andList(pre ? others.filter((m) => !eq(m.name, ow)).map((m) => String(m.name)) : voters))];
      case 'voteNeeded': return [ROLE.offeredTitle(cand), ROLE.voterNote(ow, cand)];
      case 'voted': return [ROLE.votedTitle(yesVote), ROLE.votedNote(ow)];
      case 'ownerBack': return [ROLE.offeredTitle(cand), ROLE.backNote(cand)];
      case 'youOrganiser': return [ROLE.youOrgTitle(), rf.how === 'vote' ? ROLE.youOrgVoteNote(former) : ROLE.youOrgHandNote(former)];
      case 'formerOwner': return [ROLE.isOrgTitle(owner), rf.how === 'vote' ? ROLE.formerVoteNote(owner) : ROLE.formerOfferNote(owner)];
      case 'otherPassed': return [ROLE.isOrgTitle(owner), ROLE.otherPassedNote(owner, former)];
      case 'failedCand': return [ROLE.failedCandTitle(), ROLE.failedCandNote(Number(res.yes || 0), Number(res.no || 0), owner, !res.yes && !res.no)];
      case 'failedOther': return [ROLE.staysTitle(owner), ROLE.failedOtherNote(cand, owner)];
      case 'withdrewOther': return [ROLE.staysTitle(owner), ROLE.withdrewOtherNote(cand, owner)];
      case 'stoppedCand': return [ROLE.keptTitle(owner), ROLE.keptCandNote()];
      case 'stoppedOther': return [ROLE.keptTitle(owner), ROLE.keptOtherNote(cand)];
      case 'withdrewCand': return [ROLE.withdrewTitle(), ROLE.withdrewNote(owner)];
      case 'pick': return [ROLE.pickTitle(), ROLE.pickNote()];
      case 'offerSent': return [ROLE.sentTitle(String(o.to || '')), ROLE.sentNote(String(o.to || ''))];
      case 'offerToMe': return [ROLE.toMeTitle(owner), ROLE.toMeNote()];
      case 'offerDeclined': return [ROLE.saidNoTitle(String(o.to || '')), ROLE.saidNoNote(String(nextToOffer?.name || ''))];
      case 'offerExpired': return [ROLE.expiredTitle(), ROLE.expiredNote(String(o.to || ''))];
      case 'offerPassedMine': return [ROLE.staysTitle(owner), ROLE.passedMineNote()];
      case 'offerClosedMine': return [ROLE.staysTitle(owner), o.state === 'expired' ? ROLE.closedExpiredNote(owner) : ROLE.closedWithdrawnNote(owner)];
      default: return [ROOM.infoTitle(), ''];
    }
  })();

  // ---- полоса ------------------------------------------------------------
  // Дорожка полосы — прошедшее ВРЕМЯ окна (борд: «1 of 1» при идущем таймере — почти пустая, GR.43k).
  const tStart = Number(t.started || 0), tEnd = Number(t.closes_at || 0);
  const meter = ((): { label: string; now: number; of: number; right: string; share?: number } | null => {
    if (pre) {
      return { label: ROLE.meterVote(), now: Number(t.voted || 0), of: Math.max(1, Number(t.voters || 0)),
               right: t.state === 'stopped' ? T('Остановлено', 'Stopped', 'Detenida') : T('Закончено', 'Ended', 'Terminada'),
               share: t.state === 'stopped' ? elapsed(tStart, tEnd, Number(t.resolved || now)) : 1 };
    }
    if (['candidate', 'voteNeeded', 'voted', 'ownerBack'].includes(view)) {
      return { label: ROLE.meterVote(), now: Number(t.voted || 0), of: Math.max(1, Number(t.voters || 0)),
               right: t.closes_at ? T(`Закончится через ${span(Number(t.closes_at) - now)}`, `Ends in ${span(Number(t.closes_at) - now)}`, `Termina en ${span(Number(t.closes_at) - now)}`) : '',
               share: elapsed(tStart, tEnd, now) };
    }
    if (view === 'offerSent' || view === 'offerToMe') {
      return { label: ROLE.meterOffer(), now: 0, of: 1,
               right: o.expires_at ? T(`Закончится через ${span(Number(o.expires_at) - now)}`, `Ends in ${span(Number(o.expires_at) - now)}`, `Termina en ${span(Number(o.expires_at) - now)}`) : '',
               share: elapsed(Number(o.at || 0), Number(o.expires_at || 0), now) };
    }
    return null;
  })();

  // ---- статусы людей -----------------------------------------------------
  const statusOf = (m: any): { text: string; tone: Tone } => {
    const nm = String(m.name || '');
    const isOwner = owId && pidOf(m, 'name') ? pidOf(m, 'name') === owId : eq(nm, ow);
    const isCand = candId && pidOf(m, 'name') ? pidOf(m, 'name') === candId : eq(nm, cand);
    const mineRow = isMe(nm, pidOf(m, 'name'), me);
    const votedRow = !(t.waiting || []).some((w: string) => eq(w, nm));
    const inGroup = { text: ROLE.stInGroup(), tone: 'ink' as Tone };
    const silent = { text: ROLE.stSilent(silentH), tone: 'warn' as Tone };
    switch (shown) {
      case 'silent': return isOwner ? silent : inGroup;
      case 'candidate':
        if (isOwner) return silent;
        if (mineRow) return { text: ROLE.stOffered(), tone: 'ink' };
        return votedRow ? { text: ROLE.stVoted(), tone: 'ink' } : { text: ROLE.stNotVoted(), tone: 'muted' };
      case 'voteNeeded': case 'voted':
        if (isOwner) return silent;
        if (isCand) return { text: ROLE.stOffered(), tone: 'ink' };
        if (mineRow) return view === 'voteNeeded' ? { text: ROLE.stVoteNeeded(), tone: 'turn' }
          : { text: yesVote ? ROLE.stVotedYes() : ROLE.stVotedNo(), tone: 'ink' };
        return votedRow ? { text: ROLE.stVoted(), tone: 'ink' } : { text: ROLE.stNotVoted(), tone: 'muted' };
      case 'ownerBack':
        if (mineRow) return { text: ROLE.stBack(), tone: 'ink' };
        if (isCand) return { text: ROLE.stOffered(), tone: 'ink' };
        return votedRow ? { text: ROLE.stVoted(), tone: 'ink' } : { text: ROLE.stNotVoted(), tone: 'muted' };
      case 'youOrganiser': return mineRow ? { text: ROLE.stTookFrom(former), tone: 'ink' } : inGroup;
      case 'formerOwner':
        if (isOwner) return { text: rf.how === 'vote' ? ROLE.stTookFromYou() : ROLE.stTookRole(), tone: 'ink' };
        if (mineRow && rf.how !== 'vote') return { text: ROLE.stHanded(owner), tone: 'ink' };
        // GR.44k: под листом итога голосовавшие ещё «Voted»; закрыл лист (GR.44l) — «In the group».
        if (rf.how === 'vote' && sheetUp && !mineRow && votedRow) return { text: ROLE.stVoted(), tone: 'ink' };
        return inGroup;
      case 'otherPassed': return isOwner ? { text: ROLE.stTookFrom(former), tone: 'ink' } : inGroup;
      case 'failedCand': case 'failedOther': case 'withdrewCand': case 'withdrewOther': return isOwner ? silent : inGroup;
      case 'stoppedCand': case 'stoppedOther': return isOwner ? { text: ROLE.stBack(), tone: 'ink' } : inGroup;
      case 'pick':
        if (mineRow) return { text: ROLE.stCreated(), tone: 'ink' };
        return picked && eq(picked.name, nm) ? { text: ROLE.stSelected(), tone: 'ok' } : { text: ROLE.stTapToOffer(), tone: 'ink' };
      case 'offerSent':
        if (mineRow) return { text: ROLE.stHanding(), tone: 'ink' };
        return eq(nm, o.to) ? { text: ROLE.stDeciding(), tone: 'muted' } : inGroup;
      case 'offerToMe':
        if (isOwner) return { text: ROLE.stHanding(), tone: 'ink' };
        return mineRow ? { text: ROLE.stYourCall(), tone: 'turn' } : inGroup;
      case 'offerDeclined': case 'offerExpired':
        if (mineRow) return { text: ROLE.stStillYours(), tone: 'ink' };
        if (eq(nm, o.to)) return { text: view === 'offerDeclined' ? ROLE.stSaidNo() : ROLE.stNoAnswer(), tone: 'ink' };
        return inGroup;
      case 'offerPassedMine': case 'offerClosedMine': return isOwner ? { text: ROLE.stKept(), tone: 'ink' } : inGroup;
      default: return inGroup;
    }
  };

  // ---- итог листом, один раз на исход -----------------------------------
  const resultSheet = ((): null | { title: string; lead: string; note: string; primary: string; onPrimary: () => void; counts?: boolean } => {
    if (!sheetUp) return null;
    const res = t.result || {};
    if (view === 'youOrganiser' && rf.how === 'vote') return { title: ROLE.youOrgTitle(), lead: ROLE.youOrgSheetLead(former), note: ROLE.youOrgSheetNote(former), primary: ROLE.makePlan(), onPrimary: toPlan };
    if (view === 'formerOwner' && rf.how === 'vote') return { title: ROLE.isOrgTitle(owner), lead: ROLE.awayLead(), note: ROLE.awayNote(owner), primary: ROLE.openChat(), onPrimary: toChat };
    if (view === 'otherPassed') return { title: ROLE.isOrgTitle(owner), lead: '', counts: true, note: ROLE.passSheetNoteOther(owner, former), primary: ROLE.openChat(), onPrimary: toChat };
    if (view === 'failedCand') return { title: ROLE.failedCandTitle(), lead: '', counts: true, note: ROLE.failSheetNoteCand(owner), primary: ROLE.openChat(), onPrimary: toChat };
    if (view === 'failedOther') return { title: ROLE.failSheetTitleOther(cand), lead: '', counts: true, note: ROLE.failSheetNoteOther(owner), primary: ROLE.openChat(), onPrimary: toChat };
    if (view === 'stoppedCand') return { title: ROLE.backSheetTitle(owner), lead: ROLE.backSheetLeadCand(), note: ROLE.backSheetNoteCand(), primary: ROLE.openChat(), onPrimary: toChat };
    if (view === 'stoppedOther') return { title: ROLE.backSheetTitle(owner), lead: ROLE.backSheetLeadOther(cand), note: ROLE.backSheetNoteOther(), primary: ROLE.openChat(), onPrimary: toChat };
    return null;
  })();
  const closeResult = () => setSeen((x) => new Set(x).add(resultKey));

  // ---- кнопки ------------------------------------------------------------
  const P = (label: string, onPress: () => void, disabled = false) =>
    <GlassPill key={label} tone="brand" small label={label} busy={busy} disabled={disabled} onPress={onPress} style={s.pill} />;
  const S = (label: string, onPress: () => void) =>
    <GlassPill key={label} small label={label} onPress={onPress} style={s.pill} />;
  const actions = ((): React.ReactNode[] => {
    switch (view) {
      case 'silent': return [P(ROLE.offerTakeOver(), () => setSheet('put'))];
      case 'candidate': return [S(ROLE.withdrawMine(), () => setSheet('withdraw'))];
      case 'voteNeeded': return [P(ROLE.vote(), () => setSheet('vote'))];
      case 'ownerBack': return [
        P(ROLE.keepRole(), () => act(() => gapi.takeoverBack(gid, me, false, newIdem('gtb')))),
        S(ROLE.handTo(cand), () => act(() => gapi.takeoverBack(gid, me, true, newIdem('gtb')))),
      ];
      case 'youOrganiser': return [P(ROLE.makePlan(), toPlan)];
      case 'formerOwner': return [P(ROLE.openChat(), toChat), S(ROLE.leaveGroup(), () => setSheet('leave'))];
      case 'pick': return [
        P(picked ? ROLE.offerTo(picked.name) : ROLE.offerTo('…'), () => picked && act(
          () => gapi.roleOffer(gid, me, { name: picked.name, id: picked.id }, newIdem('gro')),
          () => router.setParams({ pick: '' } as any)), !picked),
        S(ROLE.neverMind(), () => (router.canGoBack() ? router.back() : toChat())),
      ];
      case 'offerSent': return [S(ROLE.withdrawOffer(), () => act(() => gapi.roleWithdraw(gid, me, newIdem('grw'))))];
      case 'offerToMe': return [
        P(ROLE.takeRole(), () => act(() => gapi.roleRespond(gid, me, true, newIdem('grr')))),
        S(ROLE.keepWith(owner), () => setSheet('keepWith')),
      ];
      case 'offerDeclined': case 'offerExpired': return [
        ...(nextToOffer ? [P(ROLE.offerTo(String(nextToOffer.name)), () => act(
          () => gapi.roleOffer(gid, me, { name: String(nextToOffer.name), id: pidOf(nextToOffer, 'name') }, newIdem('gro'))))] : []),
        S(ROLE.keepOrganising(), toChat),
      ];
      default: return [P(ROLE.openChat(), toChat)];
    }
  })();

  // Лист «предложить себя» открыт, а кто-то успел раньше (опрос принёс чужое предложение) — сразу
  // говорим об этом листом GR.44a, а не ждём, пока человек нажмёт и получит отказ.
  useEffect(() => {
    if (sheet === 'put' && (view === 'voteNeeded' || view === 'voted')) setSheet('already');
  }, [sheet, view]);

  // Ничего про роль не происходит — это не тот экран: обратно в чат группы.
  useEffect(() => { if (g && view === 'none' && focused) toChat(); }, [g, view, focused]);

  // GR.44m: «…That drops the group to two, and Jane will have to choose…» — только когда после
  // выхода людей меньше порога группы; иначе выбирать организатору нечего.
  const left = members.length - 1;
  const below = left < Math.max(2, Number(gg.min_total || 3));
  const names = ROOM.andList(others.map((m) => String(m.name)));
  const leaveNote = below
    ? T(`${names} узнают, что ты вышел(ла). В группе останется ${left}, и ${owner} решит, что с ней делать.`,
        `${names} are told you left. That drops the group to ${NUM_EN[left] || left}, and ${owner} will have to choose what happens to it.`,
        `A ${names} se les avisa de que saliste. El grupo queda en ${left} y ${owner} decidirá qué hacer.`)
    : T(`${names} узнают, что ты вышел(ла).`, `${names} are told you left.`, `A ${names} se les avisa de que saliste.`);

  const [date, time] = splitWhen(String(gg.when || ''));
  const rows = [...others, ...mine];
  const toneStyle = (tn: Tone) => tn === 'warn' ? s.stWarn : tn === 'muted' ? s.stMuted : tn === 'ok' ? s.stOk : tn === 'turn' ? s.stTurn : null;

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      {/* Фон — ровный «Ambient · glass pilot» #F5F1EC (s.wrap), без пятен: так на новом борде раздела A (6864:115809), как и в мастере создания. */}
      <View style={s.head}>
        <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={() => (router.canGoBack() ? router.back() : toChat())} />
        <Text style={[s.headTitle, heading(lang, type.headingSm)]} numberOfLines={1}>{gg.title || ''}</Text>
      </View>
      <ScrollView onScroll={navCollapse} scrollEventThrottle={16} contentContainerStyle={s.body}>
        {!g && !gone ? <ActivityIndicator style={{ marginTop: 24 }} color={color.primary} /> : null}
        {gone ? <Text style={s.note}>{ROOM.gone()}</Text> : null}
        {g ? (
          <>
            <View style={s.status}>
              <Text style={[s.title, { fontFamily: labelFamily(lang) }]}>{head[0]}</Text>
              {head[1] ? <Text style={s.note}>{head[1]}</Text> : null}
            </View>

            <View style={s.cardShadow}>
              <GlassSurface tone="light" radius={20} style={s.card}>
                <Cover intent={gg} style={s.cover} />
                <View style={s.cardBody}>
                  {date || time ? (
                    <View style={s.cardRow}>
                      {date ? <View style={s.cardPair}><IconCalendar size={18} c={color.primary} /><Text style={s.cardLine} numberOfLines={1}>{date}</Text></View> : null}
                      {time ? <View style={s.cardPair}><IconClock size={18} c={color.primary} /><Text style={s.cardLine}>{time}</Text></View> : null}
                    </View>
                  ) : null}
                  <View style={s.cardRow}>
                    {isOnlineGroup(gg) ? <IconVideo size={18} c={color.primary} /> : <IconPin size={18} c={color.primary} />}
                    <Text style={[s.cardLine, { flex: 1 }]} numberOfLines={1}>
                      {isOnlineGroup(gg) ? groupCallLine(gg, me) : groupPlace(gg, me) || ROOM.aboutUnset()}
                    </Text>
                  </View>
                  {showExact ? (
                    <View style={s.cardRow}>
                      <IconShieldCheck size={18} c="#238C62" />
                      <Text style={[s.cardLine, { flex: 1, color: '#238C62' }]} numberOfLines={1}>
                        {isOnlineGroup(gg) ? GINVITE.linkOpens() : GINVITE.exactSpot()}
                      </Text>
                    </View>
                  ) : null}
                </View>
              </GlassSurface>
            </View>

            {meter ? (
              <View style={s.cardShadow}>
                <GlassSurface tone="light" radius={20} style={s.meter}>
                  <View style={s.meterHead}>
                    <Text style={[s.meterWord, { flex: 1 }]}>{meter.label}</Text>
                    <Text style={s.meterNum}><Text style={s.meterNow}>{meter.now}</Text>{` ${T('из', 'of', 'de')} ${meter.of}`}</Text>
                    <Text style={[s.meterTime, { flex: 1, textAlign: 'right' }]} numberOfLines={1}>{meter.right}</Text>
                  </View>
                  <View style={s.bar}><View style={[s.barFill, { width: `${Math.max(2, (meter.share ?? 0) * 100)}%` }]} /></View>
                </GlassSurface>
              </View>
            ) : null}

            <View>
              {rows.map((m, i) => {
                const nm = String(m.name || '');
                const mid = pidOf(m, 'name');
                const org = owId && mid ? mid === owId : eq(nm, ow);
                const mineRow = isMe(nm, mid, me);
                const stt = statusOf(m);
                const pickable = view === 'pick' && !mineRow;
                const Row: any = pickable ? Pressable : View;
                return (
                  <Row key={nm + i} style={s.memberRow} {...(pickable ? { accessibilityRole: 'radio', onPress: () => setPicked({ name: nm, id: mid }) } : {})}>
                    <View style={[s.av, s.avEmpty, stt.tone === 'ok' && s.avPicked]}>
                      <IconPerson size={18} />
                      {m.photo ? <Image source={{ uri: mediaUrl(String(m.photo)) }} style={[s.av, StyleSheet.absoluteFill]} /> : null}
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={s.nameRow}>
                        <Text style={s.memberName} numberOfLines={1}>{mineRow ? T('Ты', 'You', 'Tú') : ROOM.nameAge(nm, m.age)}</Text>
                        {org ? <View style={s.orgBadge}><Text style={s.orgText}>{ROOM.roleOrganiser().toLowerCase()}</Text></View> : null}
                      </View>
                      {shown === 'pick' && mineRow && gg.created ? (
                        // GR.44b: «Created the group 🕐 14:24» — когда собрал(а) группу.
                        <View style={s.sinceRow}>
                          <Text style={[s.since, toneStyle(stt.tone)]} numberOfLines={1}>{stt.text}</Text>
                          <IconClock size={14} c={INK} />
                          <Text style={s.since}>{hhmm(Number(gg.created))}</Text>
                        </View>
                      ) : (
                        <Text style={[s.since, toneStyle(stt.tone)]} numberOfLines={1}>{stt.text}</Text>
                      )}
                    </View>
                    {/* Хвост строки по борду: луна — молчит, часы — ждём ответа, галочка — выбран. */}
                    {stt.tone === 'warn' ? <IconMoon size={20} c={INK} />
                      : stt.tone === 'turn' || stt.tone === 'muted' || stt.text === ROLE.stDeciding() ? <IconClock size={20} c={INK} />
                      : stt.tone === 'ok' ? <IconCheck size={20} c={color.primary} /> : null}
                  </Row>
                );
              })}
            </View>

            {err ? <Text style={s.err}>{err}</Text> : null}
            <View style={s.actions}>{actions}</View>
          </>
        ) : null}
      </ScrollView>
      <BottomNav active="intents" />

      {/* GR.42b — предложить себя. */}
      <Sheet visible={sheet === 'put'} onClose={() => setSheet('')} title={ROLE.putTitle()}>
        <SheetText lead={ROLE.putLead(owner, silentH)} note={ROLE.putNote(owner)} />
        <GlassPill tone="brand" label={ROLE.putMe()} busy={busy} style={s.sheetBtn}
                   onPress={() => act(() => gapi.takeover(gid, me, newIdem('gto')), () => setSheet(''))} />
        <GlassPill tone="dark" label={ROLE.notNow()} style={s.sheetBtn} onPress={() => setSheet('')} />
      </Sheet>
      {/* GR.44a — кто-то успел раньше: одно предложение за раз. */}
      <Sheet visible={sheet === 'already'} onClose={() => setSheet('')} title={ROLE.alreadyTitle(cand)}>
        <SheetText lead={t.closes_at ? ROLE.hoursLeftLead(hoursLeft(Number(t.closes_at))) : ''}
                   note={ROLE.alreadyNote(cand)} />
        <GlassPill tone="brand" label={ROLE.voteOn(cand)} style={s.sheetBtn} onPress={() => setSheet('vote')} />
        <GlassPill tone="dark" label={ROLE.waitResult()} style={s.sheetBtn} onPress={() => setSheet('')} />
      </Sheet>
      {/* GR.43a — снять своё предложение. */}
      <Sheet visible={sheet === 'withdraw'} onClose={() => setSheet('')} title={ROLE.withdrawTitle()}>
        <SheetText lead={ROLE.withdrawLead()} note={ROLE.withdrawNote(owner)} />
        <GlassPill tone="brand" label={ROLE.withdraw()} busy={busy} style={s.sheetBtn}
                   onPress={() => act(() => gapi.takeoverWithdraw(gid, me, newIdem('gtw')), () => setSheet(''))} />
        <GlassPill tone="dark" label={ROLE.keepMine()} style={s.sheetBtn} onPress={() => setSheet('')} />
      </Sheet>
      {/* GR.43e — голос. */}
      <Sheet visible={sheet === 'vote' && t.state === 'open'} onClose={() => setSheet('')} title={ROLE.voteTitle(cand)}>
        <SheetText lead={ROLE.voteLead(hoursLeft(Number(t.closes_at || 0)))} note={ROLE.voteNote(owner)} />
        <GlassPill tone="brand" label={ROLE.voteYes(cand)} busy={busy} style={s.sheetBtn}
                   onPress={() => act(() => gapi.takeoverVote(gid, me, true, newIdem('gtv')), () => setSheet(''))} />
        <GlassPill tone="dark" label={ROLE.voteNo(owner)} style={s.sheetBtn}
                   onPress={() => act(() => gapi.takeoverVote(gid, me, false, newIdem('gtv')), () => setSheet(''))} />
      </Sheet>
      {/* GR.44i — оставить роль у организатора. */}
      <Sheet visible={sheet === 'keepWith'} onClose={() => setSheet('')} title={ROLE.keepWithTitle(owner)}>
        <SheetText lead={ROLE.keepWithLead()} note={ROLE.keepWithNote(owner)} />
        <GlassPill tone="brand" label={ROLE.keepWithBtn(owner)} busy={busy} style={s.sheetBtn}
                   onPress={() => act(() => gapi.roleRespond(gid, me, false, newIdem('grr')), () => setSheet(''))} />
        <GlassPill tone="dark" label={ROLE.goBack()} style={s.sheetBtn} onPress={() => setSheet('')} />
      </Sheet>
      {/* GR.44m — выйти из группы бывшему организатору. */}
      <Sheet visible={sheet === 'leave'} onClose={() => setSheet('')} title={T(`Выйти из «${gg.title || ''}»?`, `Leave ${gg.title || ''}?`, `¿Salir de ${gg.title || ''}?`)}>
        <SheetText lead={T('Это нельзя отменить', 'You can’t undo this', 'No se puede deshacer')}
                   note={leaveNote} />
        <GlassPill tone="brand" label={ROLE.leaveGroup()} busy={busy} style={s.sheetBtn}
                   onPress={() => act(() => gapi.leave(gid, me, newIdem('gl')), () => { setSheet(''); router.dismissTo('/home'); })} />
        <GlassPill tone="dark" label={T('Остаться', 'Stay', 'Quedarme')} style={s.sheetBtn} onPress={() => setSheet('')} />
      </Sheet>
      {/* Итог листом (GR.43c / 43i / 43f / 43l / 43n / 43p / 44k). */}
      <Sheet visible={!!resultSheet && !sheet} onClose={closeResult} title={resultSheet?.title}>
        <SheetText lead={resultSheet?.lead} note={resultSheet?.note}>
          {/* GR.43i/l/n: счёт голосов — число чернилами, «Yes» зелёным, «No» красным. */}
          {resultSheet?.counts ? (
            <View style={s.counts}>
              <Text style={[s.countNum, { fontFamily: labelFamily(lang) }]}>{Number((t.result || {}).yes || 0)} <Text style={s.countYes}>{T('за', 'Yes', 'sí')}</Text></Text>
              <Text style={[s.countNum, { fontFamily: labelFamily(lang) }]}>{Number((t.result || {}).no || 0)} <Text style={s.countNo}>{T('против', 'No', 'no')}</Text></Text>
            </View>
          ) : null}
        </SheetText>
        <GlassPill tone="brand" label={resultSheet?.primary || ''} style={s.sheetBtn}
                   onPress={() => { closeResult(); resultSheet?.onPrimary(); }} />
        <GlassPill tone="dark" label={ROLE.gotIt()} style={s.sheetBtn} onPress={closeResult} />
      </Sheet>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, height: 56 },
  headTitle: { flex: 1, color: INK } as any,
  body: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: space.xl, gap: 14 },
  status: { gap: 4 },
  title: { fontSize: 15, lineHeight: 20, color: INK } as any,
  note: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: INK } as any,
  err: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#D92D2D' } as any,
  cardShadow: { borderRadius: 20, shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 14, shadowOffset: { width: 0, height: 5 } },
  card: { overflow: 'hidden' },
  cover: { height: 128, backgroundColor: color.neutral100 },
  cardBody: { paddingHorizontal: 16, paddingVertical: 16, gap: 8 },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardPair: { flexDirection: 'row', alignItems: 'center', gap: 4, marginRight: 8, flexShrink: 1 },
  cardLine: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: INK } as any,
  meter: { paddingHorizontal: 16, paddingVertical: 16, gap: 8 },
  meterHead: { flexDirection: 'row', alignItems: 'center' },
  meterWord: { fontFamily: font.displaySemi, fontSize: 13, lineHeight: 16, color: INK } as any,
  meterNum: { fontFamily: font.displaySemi, fontSize: 13, lineHeight: 16, color: '#AFAFAF', textAlign: 'center' } as any,
  meterNow: { color: '#FF385C' },
  meterTime: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: INK } as any,
  bar: { height: 3, borderRadius: 999, backgroundColor: '#EBEBEB', overflow: 'hidden' },
  barFill: { height: 3, borderRadius: 999, backgroundColor: '#FF385C' },
  memberRow: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 56 },
  av: { width: 40, height: 40, borderRadius: 999 },
  avEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  avPicked: { borderWidth: 2, borderColor: color.primary },
  counts: { flexDirection: 'row', gap: 12 },
  countNum: { fontSize: 15, lineHeight: 20, fontWeight: '600', color: INK },
  countYes: { color: '#1FAE5E' },
  countNo: { color: '#EF4444' },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  memberName: { fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: INK, flexShrink: 1 } as any,
  orgBadge: { height: 16, paddingHorizontal: 8, borderRadius: 99, backgroundColor: '#CFE3FF', justifyContent: 'center' },
  orgText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#1F58BE' } as any,
  since: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: INK } as any,
  stWarn: { color: '#9A5400' },
  stMuted: { color: '#5A616E' },
  stOk: { color: '#0F7340' },
  sinceRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  stTurn: { color: '#FF385C' },
  actions: { gap: 8, paddingTop: 2 },
  pill: { height: 44 },
  sheetBtn: { height: 48 },
});
