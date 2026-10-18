/**
 * Детали выдачи в групповом режиме — борд «0 · Create the intent» (Figma 6864:119674), GR.14–GR.17a.
 *
 * Числа — с кадров:
 *   полоса набора «Round Indicator» — стекло 45%, скругление 20, поля 16/16/18/16; три ячейки:
 *     «Joined» TASA 600 13/20, «1» коралл + «of 2» #AFAFAF той же гарнитурой, «Ends in 12h» Geist 13/18
 *     справа; под ними дорожка 3 #ECECEC с коралловым заполнением;
 *   блок состояния на карточке — белое 56%, скругление 12, поля 12, между строками 8: значок 16,
 *     подпись Geist 600 13/20 (цвет — по исходу), время Geist 11/22 #5A616E справа, пояснение 13/18;
 *   строка участника обзора GR.17 — 56 высотой: фото 40, имя Geist 600 14/20, статус Geist 13/22,
 *     значок 18 справа; у организатора голубой бейдж «organiser» (#CFE3FF / #1F58BE);
 *   карточка затеи обзора — «Plan Card · forming»: обложка 128 со скруглением 20 сверху, под ней
 *     белое 45% с полями 16 и строками дня, времени и места (значки 18 кораллом, Geist 13/22).
 */
import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, Image } from 'react-native';
import { color, font } from '../theme';
import { useLang } from '../i18n';
import { GlassSurface } from './LiquidGlass';
import { Cover } from './Cover';
import { GR14 } from '../groups';
import { cardDate, hhmm } from '../intent';
import {
  IconCalendar, IconCalendarCheck, IconCalendarX, IconClock, IconLink, IconPerson, IconPin,
 IconVideo } from './icons';

const MUTED = '#5A616E';
const FAINT = '#AFAFAF';

/** «14:25» — время события на блоке состояния; 24-часовое, как везде (см. use12h). */
export function clockOf(at?: number): string {
  if (!at) return '';
  const d = new Date(at);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// ===================================================================== полоса набора

/**
 * «Joined · 1 of 2 · Ends in 11h 54m» — GR.14a. Срок тикает сам раз в полминуты: экран открыт
 * часами, и застывшее «12h» через час уже неправда. Срока нет — правая ячейка пустая.
 */
export function RoundIndicator({ joined, total, endsAt, label }: { joined: number; total: number; endsAt?: number;
  /** Своя подпись счётчика: у приглашений один на один — «Answered» (OF.12a). */
  label?: string }) {
  useLang();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!endsAt) return;
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, [endsAt]);
  const pct = total > 0 ? Math.min(1, joined / total) : 0;
  return (
    <GlassSurface tone="light" radius={20} style={s.round}>
      <View style={s.roundHead}>
        <Text style={[s.roundCell, s.roundTitle]}>{label || GR14.joined()}</Text>
        <Text style={[s.roundCell, s.roundCount]}>
          <Text style={{ color: color.primary }}>{joined}</Text>
          <Text style={{ color: FAINT }}> {GR14.of(total)}</Text>
        </Text>
        <Text style={[s.roundCell, s.roundTime]} numberOfLines={1}>
          {endsAt ? GR14.endsIn(endsAt - now) : ''}
        </Text>
      </View>
      {/* Пока никто не вступил, на кадре всё равно видна коралловая точка — ход набора начался. */}
      <View style={s.track}>
        <View style={[s.progress, { width: pct > 0 ? `${pct * 100}%` : 6 }]} />
      </View>
    </GlassSurface>
  );
}

// ===================================================================== блок состояния

export type StatusKind = 'sent' | 'joined' | 'declined' | 'closed';

const KIND: Record<StatusKind, { label: () => string; tone: string; Icon: typeof IconClock }> = {
  sent: { label: GR14.sent, tone: color.fg, Icon: IconClock },
  joined: { label: GR14.joinedTitle, tone: color.successText, Icon: IconCalendarCheck },
  declined: { label: GR14.declined, tone: MUTED, Icon: IconCalendarX },
  closed: { label: GR14.closed, tone: MUTED, Icon: IconCalendarX },
};

/** Исход приглашения на карточке — GR.14a «Invite sent», 14c «Joined», 14d «Can’t make it», 14e «Invite closed». */
export function StatusBlock({ kind, at, text, label }: { kind: StatusKind; at?: number; text: string;
  /** Своя подпись при том же знаке и цвете: «Said yes», «Picked» (OF.12d / 12e). */
  label?: string }) {
  useLang();
  const k = KIND[kind];
  return (
    <View style={s.status}>
      <View style={s.statusHead}>
        <k.Icon size={16} c={k.tone} />
        <Text style={[s.statusLabel, { color: k.tone }]} numberOfLines={1}>{label || k.label()}</Text>
        {at ? <Text style={s.statusTime}>{clockOf(at)}</Text> : null}
      </View>
      <Text style={s.statusText}>{text}</Text>
    </View>
  );
}

// ===================================================================== строка участника

/** Строка обзора GR.17 / GR.17a: кто, что с ним, значок исхода справа. */
export function MemberRow({
  photo, name, status, kind, organiser,
}: {
  photo?: string;
  name: string;
  status: string;
  kind?: StatusKind | 'you';
  organiser?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const tone = kind === 'joined' ? color.successText
    : kind === 'declined' ? color.warnText
    : kind === 'you' ? color.fg
    : MUTED;
  const Icon = kind === 'joined' ? IconCalendarCheck
    : kind === 'declined' || kind === 'closed' ? IconCalendarX
    : kind === 'sent' ? IconClock
    : null;
  return (
    <View style={s.member}>
      {photo && !broken ? (
        <Image source={{ uri: photo }} style={s.memberAv} onError={() => setBroken(true)} />
      ) : (
        <View style={[s.memberAv, s.memberAvEmpty]}><IconPerson size={20} /></View>
      )}
      <View style={{ flex: 1 }}>
        <View style={s.memberNameRow}>
          <Text style={s.memberName} numberOfLines={1}>{name}</Text>
          {organiser ? (
            <View style={s.orgBadge}><Text style={s.orgText}>{GR14.organiser()}</Text></View>
          ) : null}
        </View>
        <Text style={[s.memberStatus, { color: tone }]} numberOfLines={1}>{status}</Text>
      </View>
      {Icon ? <Icon size={18} c={color.fg} /> : null}
    </View>
  );
}

// ===================================================================== карточка затеи

/**
 * «Plan Card · forming» обзора GR.17: обложка и строки когда/где. Затея берётся такой, какой ушла в
 * поиск: день и минуты лежат в ней с мастера (dateKey/minutes), место — адрес, иначе район.
 */
export function PlanCard({ intent, callLine }: { intent: any;
  /** O.14b: у звонка один на один вместо самой ссылки — «Video call · link comes with the plan». */
  callLine?: string }) {
  useLang();
  const dateKey = String(intent?.dateKey || '');
  const minutes = Number(intent?.minutes);
  const online = intent?.mode === 'online';
  const place = callLine ? callLine : online
    ? String(intent?.link || '').trim()
    : String(intent?.address || intent?.area || intent?.place || '').trim();
  return (
    <GlassSurface tone="light" radius={20} style={s.plan}>
      <Cover intent={intent} style={s.planCover} />
      <View style={s.planBody}>
        {dateKey || Number.isFinite(minutes) ? (
          <View style={s.planLine}>
            {dateKey ? (
              <View style={s.planPart}>
                <IconCalendar size={18} c={color.primary} />
                <Text style={s.planText}>{cardDate(dateKey)}</Text>
              </View>
            ) : null}
            {Number.isFinite(minutes) ? (
              <View style={s.planPart}>
                <IconClock size={18} c={color.primary} />
                <Text style={s.planText}>{hhmm(minutes)}</Text>
              </View>
            ) : null}
          </View>
        ) : null}
        {place ? (
          <View style={s.planLine}>
            <View style={[s.planPart, { flex: 1 }]}>
              {callLine ? <IconVideo size={18} c={color.primary} /> : online ? <IconLink size={18} c={color.primary} /> : <IconPin size={18} c={color.primary} />}
              <Text style={[s.planText, { flex: 1 }]} numberOfLines={1}>{place}</Text>
            </View>
          </View>
        ) : null}
      </View>
    </GlassSurface>
  );
}

const s = StyleSheet.create({
  round: { paddingTop: 16, paddingHorizontal: 16, paddingBottom: 18, gap: 4 },
  roundHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  roundCell: { flex: 1 },
  roundTitle: { fontFamily: font.displaySemi, fontSize: 13, lineHeight: 20, color: color.fg } as any,
  roundCount: { fontFamily: font.displaySemi, fontSize: 13, lineHeight: 20, textAlign: 'center', fontVariant: ['tabular-nums'] } as any,
  roundTime: { fontFamily: font.text, fontSize: 13, lineHeight: 20, color: color.fg, textAlign: 'right' } as any,
  track: { height: 3, borderRadius: 2, backgroundColor: '#ECECEC', overflow: 'hidden', marginTop: 4 },
  progress: { height: 3, borderRadius: 2, backgroundColor: color.primary },

  status: {
    backgroundColor: 'rgba(255,255,255,0.56)', borderRadius: 12, padding: 12, gap: 8,
    shadowColor: '#5A4A3A', shadowOpacity: 0.05, shadowRadius: 8, shadowOffset: { width: 0, height: 2 },
  },
  statusHead: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  statusLabel: { flex: 1, fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20 } as any,
  statusTime: { fontFamily: font.text, fontSize: 11, lineHeight: 22, color: MUTED, fontVariant: ['tabular-nums'] } as any,
  statusText: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.fg } as any,

  member: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: 12 },
  memberAv: { width: 40, height: 40, borderRadius: 20 },
  memberAvEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  memberNameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  memberName: { flexShrink: 1, fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  memberStatus: { fontFamily: font.text, fontSize: 13, lineHeight: 22 } as any,
  orgBadge: { height: 16, paddingHorizontal: 8, paddingBottom: 1, borderRadius: 99, backgroundColor: '#CFE3FF', justifyContent: 'center' },
  orgText: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 16, color: color.infoText } as any,

  plan: { overflow: 'hidden' },
  planCover: { height: 128, borderTopLeftRadius: 20, borderTopRightRadius: 20, overflow: 'hidden' },
  planBody: { padding: 16, gap: 8, backgroundColor: 'rgba(255,255,255,0.45)' },
  planLine: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  planPart: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  planText: { fontFamily: font.text, fontSize: 13, lineHeight: 22, color: color.fg } as any,
});
