/**
 * Заблокированные — кадр B.12.
 *
 * UX-каркас: вид натянется поверх, копия в src/settings.ts.
 *
 * Список приходит с сервера (/api/agent/safety) и там же снимается (/api/agent/block с on:false).
 * Локальной копии нет намеренно: блокировка — это то, что меняет поведение поиска и переписки для
 * ДВОИХ, и список, живущий в телефоне, однажды разошёлся бы с тем, что на самом деле применено.
 *
 * Даты «Blocked 24 July» с кадра здесь не будет: сервер хранит блокировки именами и ничем больше.
 * Написать сюда любую дату значило бы показать человеку выдуманный факт о его собственном решении.
 */
import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { ProfileShell, Card, SectionHead } from '../../src/components/ProfileShell';
import { GlassSurface } from '../../src/components/LiquidGlass';
import { IconPerson } from '../../src/components/icons';
import { useLang, T } from '../../src/i18n';
import { useOnb } from '../../src/state';
import { agent } from '../../src/api';
import { BLOCKED } from '../../src/settings';
import { color, radius as rad, space, type } from '../../src/theme';

export default function Blocked() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const me = st.profile.name || '';

  const [list, setList] = useState<string[]>([]);
  /** id заблокированных по тем же местам, что и подписи: снимается блок с человека, а не с имени. */
  const [ids, setIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState(false);

  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    try {
      const r: any = await agent.safety(me);
      setList(Array.isArray(r?.blocked) ? r.blocked.map(String) : []);
      setIds(Array.isArray(r?.blocked_ids) ? r.blocked_ids.map(String) : []);
      setErr(false);
    } catch {
      setErr(true);
    } finally {
      setLoading(false);
    }
  }, [me]);

  // На каждый приход, а не один раз: экран остаётся в стопке, а блокируют из чата и профиля.
  useFocusEffect(useCallback(() => { load(); }, [load]));

  /** Снятие идёт на сервере, и список берётся из ЕГО ответа, а не правится на месте. */
  const unblock = async (name: string, i: number) => {
    setBusy(name);
    try {
      const r: any = await agent.block(me, { name, id: ids[i] || '' }, false);
      if (Array.isArray(r?.blocked)) {
        setList(r.blocked.map(String));
        setIds(Array.isArray(r?.blocked_ids) ? r.blocked_ids.map(String) : []);
      } else await load();
    } catch {
      setErr(true);
    } finally {
      setBusy(null);
    }
  };

  return (
    <ProfileShell title={BLOCKED.title()} onBack={() => router.back()}>
      {loading ? (
        <ActivityIndicator style={{ marginTop: space.lg }} color={color.primary} />
      ) : err ? (
        <Text style={s.empty}>{T('Не удалось получить список.', 'Could not load the list.', 'No se pudo cargar la lista.')}</Text>
      ) : list.length === 0 ? (
        // B.09a — пусто.
        <SectionHead title={BLOCKED.noneTitle()} note={BLOCKED.noneNote()} />
      ) : (
        <>
          {/* B.09 — «They can’t reach you»; строка — лицо, имя и «Unblock» стеклянной пилюлей. */}
          <SectionHead title={BLOCKED.cantReach()} note={BLOCKED.lead()} />
          {list.map((name, i) => (
            <Card key={ids[i] || name} style={s.row}>
              <View style={s.ava}><IconPerson size={22} /></View>
              <Text style={s.name} numberOfLines={1}>{name}</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ busy: busy === name }}
                onPress={busy ? undefined : () => unblock(name, i)}
              >
                <GlassSurface tone="light" radius={999} style={s.btn} pointerEvents="none">
                  {busy === name
                    ? <ActivityIndicator size="small" color={color.fg} />
                    : <Text style={s.btnText}>{BLOCKED.unblock()}</Text>}
                </GlassSurface>
              </Pressable>
            </Card>
          ))}
        </>
      )}
    </ProfileShell>
  );
}

// ============================================================ вид

const s = StyleSheet.create({
  lead: { backgroundColor: color.infoBg, borderRadius: rad.lg, padding: space.md },
  leadText: { ...type.bodySmall, color: color.infoText } as any,
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 12 },
  ava: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center',
  },
  name: { flex: 1, fontSize: 16, fontWeight: '600', color: color.fg },
  btn: { height: 40, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' },
  btnText: { ...type.bodySmall, color: color.fg, fontWeight: '600' } as any,
  empty: { ...type.body, color: color.muted, paddingHorizontal: 4 } as any,
});
