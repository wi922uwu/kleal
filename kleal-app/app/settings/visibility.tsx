/**
 * Настройки → «Кто меня видит».
 *
 * Здесь ровно один рычаг, и он настоящий: статус приёма. Подбор читает его жёстким фильтром — на
 * паузе человека не находит НИКТО, ни в поиске, ни в предложениях агента.
 *
 * Почему не переключатель «скрыть меня», а три состояния. Скрытность в продукте не двоичная:
 * «занят» оставляет тебя находимым, но реже предлагает другим, и это середина, за которой люди
 * возвращаются. Один тумблер её бы не выразил, а два тумблера рядом («скрыть» и «реже») человек
 * читал бы как противоречие.
 *
 * ВАЖНО ПРО СОХРАНЕНИЕ. Экран показывает то, что вернул СЕРВЕР, а не то, что нажали. Политику
 * сервер принимает белым списком и часть значений молча выбрасывает; рисовать нажатое как принятое
 * значило бы показывать настройку, которой нет. Поэтому после каждой правки перерисовываемся
 * ответом, а при отказе возвращаем прежнее состояние и говорим об этом.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card, ToggleRow, Segments } from '../../src/components/ProfileShell';
import { useLang } from '../../src/i18n';
import { useOnb } from '../../src/state';
import { profile as profileApi } from '../../src/api';
import { VISIBILITY, RECV_STATUS } from '../../src/settings';
import { color, radius as rad, space, type } from '../../src/theme';

type Recv = {
  status?: string;
  passive_outreach?: boolean;
  allowed_domains?: string[];
  quiet_hours?: { start?: string; end?: string; tz_offset_min?: number };
  paused_until?: string | number | null;
};

export default function Visibility() {
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

  /** Одна правка политики: показываем ответ сервера, а не собственную догадку о нём. */
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

  const status = String(recv?.status || 'active');
  const chosen = RECV_STATUS.find((x) => x.id === status) || RECV_STATUS[0];

  return (
    <ProfileShell title={VISIBILITY.title()} onBack={() => router.back()}>
      <Card>
        <Text style={s.h}>{VISIBILITY.statusTitle()}</Text>
        <Text style={s.lead}>{VISIBILITY.statusLead()}</Text>
        <View style={{ height: space.md }} />
        <Segments
          options={RECV_STATUS.map((x) => [x.id, x.label()] as [string, string])}
          value={status}
          onChange={(v) => patch({ status: v })}
        />
        {/* Подпись меняется вместе с выбором: человек должен видеть последствие, а не название. */}
        <Text style={s.what}>{chosen.what()}</Text>
        {status === 'paused' ? <Text style={s.note}>{VISIBILITY.pausedNote()}</Text> : null}
      </Card>

      <Card>
        <ToggleRow
          label={VISIBILITY.outreachTitle()}
          desc={VISIBILITY.outreachDesc()}
          value={recv?.passive_outreach !== false}
          onChange={(v) => patch({ passive_outreach: v })}
        />
      </Card>

      {err ? (
        <Card>
          <Text style={s.err}>{err}</Text>
        </Card>
      ) : null}
    </ProfileShell>
  );
}

const s = StyleSheet.create({
  h: { ...type.title, color: color.fg } as any,
  lead: { ...type.caption, color: color.muted, marginTop: 4 } as any,
  what: { ...type.caption, color: color.fg, marginTop: space.md } as any,
  note: { ...type.caption, color: color.muted, marginTop: space.sm } as any,
  err: { ...type.caption, color: color.primary } as any,
});
