/**
 * Настройки → «Когда меня можно звать».
 *
 * Три ограничения, и все три подбор исполняет: во что тебя зовут, в какие часы молчать и до какой
 * даты не трогать вовсе.
 *
 * ПОЧЕМУ НЕЛЬЗЯ СНЯТЬ ПОСЛЕДНИЙ ВИД ВСТРЕЧ. Сервер принимает список белым списком и ПУСТОЙ молча
 * игнорирует (`if keep:` в update_receiving) — то есть, сняв всё, человек увидел бы пустые галочки,
 * а политика осталась бы прежней: экран показывал бы одно, подбор делал другое. Поэтому последний
 * снять нельзя, и сказано об этом до нажатия. Уйти совсем — это «Пауза» на соседнем экране, и она
 * честная.
 *
 * ЧАСЫ ТИШИНЫ — готовыми значениями, а не колесом времени. Точность до минуты здесь никому не
 * нужна: человек выбирает «не раньше девяти», а не «не раньше 9:07». Смещение пояса берём с самого
 * устройства — сервер хранит его отдельным полем, потому что «22:00» без пояса означает разное
 * время в Барселоне и Токио.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, ToggleRow, Segments, Divider } from '../../src/components/ProfileShell';
import { useLang, T, dateLocale } from '../../src/i18n';
import { useOnb } from '../../src/state';
import { profile as profileApi } from '../../src/api';
import { AVAILABILITY, RECV_DOMAINS, VISIBILITY } from '../../src/settings';
import { color, radius as rad, space, type } from '../../src/theme';

type Recv = {
  status?: string;
  allowed_domains?: string[];
  quiet_hours?: { start?: string; end?: string; tz_offset_min?: number };
  paused_until?: string | number | null;
};

const START_HOURS = ['20:00', '21:00', '22:00', '23:00'];
const END_HOURS = ['07:00', '08:00', '09:00', '10:00'];

/** 'YYYY-MM-DDTHH:MM' — один из двух видов, которые принимает сервер (`_valid_ts`). */
function inDays(n: number): string {
  const d = new Date(Date.now() + n * 864e5);
  const p = (x: number) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function human(v: string | number | null | undefined): string {
  if (!v) return '';
  const d = typeof v === 'number' ? new Date(v * 1000) : new Date(String(v));
  if (isNaN(d.getTime())) return '';
  return d.toLocaleDateString(dateLocale(), { day: 'numeric', month: 'long' });
}

export default function Availability() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const name = st.profile?.name || '';

  const [recv, setRecv] = useState<Recv | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!name) return;
    try {
      const r: any = await profileApi.receiving(name);
      if (r?.ok && r.receiving) setRecv(r.receiving);
      else setErr(VISIBILITY.failed());
    } catch {
      setErr(VISIBILITY.failed());
    }
  }, [name]);

  useEffect(() => { load(); }, [load]);

  const patch = async (p: Recv) => {
    if (!name || busy) return;
    setBusy(true);
    setErr('');
    try {
      const r: any = await profileApi.receiving(name, p as any);
      if (r?.ok && r.receiving) setRecv(r.receiving);
      else setErr(VISIBILITY.failed());
    } catch {
      setErr(VISIBILITY.failed());
    } finally {
      setBusy(false);
    }
  };

  const doms: string[] = Array.isArray(recv?.allowed_domains) ? recv!.allowed_domains! : [];
  const only = doms.length <= 1;
  const qh = recv?.quiet_hours || {};
  const until = recv?.paused_until;

  const toggleDomain = (id: string, on: boolean) => {
    if (!on && only && doms.includes(id)) return;      // последний не снимаем: сервер это проглотит молча
    const next = on ? Array.from(new Set([...doms, id])) : doms.filter((d) => d !== id);
    if (!next.length) return;
    patch({ allowed_domains: next });
  };

  const setQuiet = (field: 'start' | 'end', v: string) =>
    patch({ quiet_hours: { ...qh, [field]: v, tz_offset_min: -new Date().getTimezoneOffset() } });

  return (
    <ProfileShell title={AVAILABILITY.title()} onBack={() => router.back()}>
      <Card>
        <Text style={s.h}>{AVAILABILITY.domainsTitle()}</Text>
        <Text style={s.lead}>{AVAILABILITY.domainsLead()}</Text>
        <View style={{ height: space.sm }} />
        {RECV_DOMAINS.map((d, i) => (
          <View key={d.id}>
            {i ? <Divider /> : null}
            <ToggleRow
              label={d.label()}
              value={doms.includes(d.id)}
              onChange={(v) => toggleDomain(d.id, v)}
            />
          </View>
        ))}
        {only ? <Text style={s.note}>{AVAILABILITY.domainsEmpty()}</Text> : null}
      </Card>

      <Card>
        <Text style={s.h}>{AVAILABILITY.quietTitle()}</Text>
        <Text style={s.lead}>{AVAILABILITY.quietLead()}</Text>
        <View style={{ height: space.md }} />
        <Text style={s.small}>{AVAILABILITY.quietFrom()}</Text>
        <Segments
          options={START_HOURS.map((h) => [h, h] as [string, string])}
          value={String(qh.start || '22:00')}
          onChange={(v) => setQuiet('start', v)}
        />
        <View style={{ height: space.sm }} />
        <Text style={s.small}>{AVAILABILITY.quietTo()}</Text>
        <Segments
          options={END_HOURS.map((h) => [h, h] as [string, string])}
          value={String(qh.end || '09:00')}
          onChange={(v) => setQuiet('end', v)}
        />
      </Card>

      <Card>
        <Text style={s.h}>{AVAILABILITY.untilTitle()}</Text>
        <Text style={s.lead}>{AVAILABILITY.untilLead()}</Text>
        <View style={{ height: space.md }} />
        {until ? (
          <Text style={s.what}>{AVAILABILITY.untilSet(human(until))}</Text>
        ) : (
          <Text style={s.what}>{AVAILABILITY.untilNone()}</Text>
        )}
        <View style={s.btnRow}>
          <Pressable accessibilityRole="button" style={s.btn} onPress={() => patch({ paused_until: inDays(7) })}>
            <Text style={s.btnText}>{T('На неделю', 'For a week', 'Para una semana')}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" style={s.btn} onPress={() => patch({ paused_until: inDays(30) })}>
            <Text style={s.btnText}>{T('На месяц', 'For a month', 'Para un mes')}</Text>
          </Pressable>
          {until ? (
            <Pressable accessibilityRole="button" style={s.btn} onPress={() => patch({ paused_until: null })}>
              <Text style={s.btnText}>{AVAILABILITY.untilClear()}</Text>
            </Pressable>
          ) : null}
        </View>
      </Card>

      {err ? <Card><Text style={s.err}>{err}</Text></Card> : null}
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  h: { ...type.title, color: color.fg } as any,
  lead: { ...type.caption, color: color.muted, marginTop: 4 } as any,
  small: { ...type.caption, color: color.muted, marginBottom: 6 } as any,
  what: { ...type.body, color: color.fg } as any,
  note: { ...type.caption, color: color.muted, marginTop: space.sm } as any,
  err: { ...type.caption, color: color.primary } as any,
  btnRow: { flexDirection: 'row', gap: space.sm, marginTop: space.md, flexWrap: 'wrap' },
  btn: {
    paddingHorizontal: space.lg, height: 40, borderRadius: rad.full,
    backgroundColor: color.ambientBase, alignItems: 'center', justifyContent: 'center',
  },
  btnText: { ...type.button, color: color.fg } as any,
});
