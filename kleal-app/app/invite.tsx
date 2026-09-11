/**
 * Входящее приглашение — кадр O.C1, сторона гостя.
 *
 * UX-КАРКАС: вид натянется поверх; копия — в src/chat.ts (INVITE).
 *
 * Устройство по кадру: заголовок «X приглашает тебя», записка о том, что согласие открывает чат,
 * карточка интента (когда · формат), двое участников со статусами, «Присоединиться» и «Не в этот
 * раз». Ссылки на звонок здесь НЕТ и не должно быть: её приносит план позже, и сервер отдаёт её
 * только подтвердившим (OF.C3) — поэтому карточка честно пишет «ссылка у {хоста}».
 *
 * Данные настоящие: /api/agent/inbox отдаёт заявку, /api/agent/respond решает её. Сервер при
 * согласии пере-проверяет политику (§14.2) — между отправкой и ответом человек мог, например,
 * заблокировать отправителя; на это есть отдельный текст.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { CHAT, INVITE } from '../src/chat';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { mediaUrl, agent } from '../src/api';
import {
  IconChevronLeft, IconCalendar, IconPerson, IconGroups, IconImagePlaceholder, IconPin,
} from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

export default function Invite() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();

  const params = useLocalSearchParams<{ id?: string }>();
  const wantedId = String(params.id || '').trim();

  const me = String(st.profile.name || '');
  const [row, setRow] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    try {
      const r: any = await agent.inbox(me);
      const rows: any[] = Array.isArray(r) ? r : r?.requests || [];
      // Без id открываем свежайшее нерешённое: экран зовут из уведомления, где id есть,
      // и из списка, где сортировка сервера уже «новые сверху».
      const mine = wantedId
        ? rows.find((x) => x.id === wantedId)
        : rows.find((x) => x.status === 'pending') || rows[0];
      setRow(mine || null);
    } catch {
      /* тихо: фоновая дотяжка */
    } finally {
      setLoading(false);
    }
  }, [me, wantedId]);

  useEffect(() => { load(); }, [load]);

  const answer = async (decision: 'accept' | 'decline') => {
    if (!row?.id || busy) return;
    setBusy(true);
    setErr('');
    try {
      const r: any = await agent.respondInvite(row.id, me, decision, row.version);
      if (!r?.ok) {
        // O.C7: пока экран был открыт, приглашение закрылось — второй ответил раньше, отправитель
        // забрал его, или оно сгорело. Одной красной строки мало: под ней оставались живые кнопки
        // «Присоединиться» и «Не в этот раз», и следующее нажатие давало ту же ошибку. Перечитываем
        // строку — экран сам уйдёт в нужное состояние и покажет выход.
        if (r?.error === 'EXPIRED' || r?.error === 'ALREADY_RESOLVED') {
          await load();
          throw new Error(INVITE.goneNote());
        }
        throw new Error(CHAT.planFailed());
      }
      if (decision === 'accept') {
        // Записка на кадре и есть контракт: согласие открывает чат с пригласившим.
        router.replace({ pathname: '/conversation', params: { who: row.from, title: titleOf(row), photo: row.photo || '' } });
        return;
      }
      await load();
    } catch (e: any) {
      setErr(String(e?.message || CHAT.planFailed()));
    } finally {
      setBusy(false);
    }
  };

  const from = String(row?.from || '');
  const intent = row?.intent || {};
  const online = String(intent.mode || '') !== 'offline';
  const what = [titleOf(row), whenOf(intent)].filter(Boolean).join(', ');

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} style={s.back} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
          <IconChevronLeft />
        </Pressable>
        <Text style={s.headTitle} numberOfLines={1}>{titleOf(row) || T('Приглашение', 'Invite', 'Invitar')}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[s.body, { paddingBottom: 130 }]}>
        {loading ? <ActivityIndicator color={color.muted} style={{ marginTop: space.lg }} /> : null}

        {!loading && !row ? <Text style={s.note}>{INVITE.goneNote()}</Text> : null}

        {row ? (
          <>
            <Text style={s.title}>{INVITE.title(from)}</Text>
            <Text style={s.note}>{INVITE.note(what, from)}</Text>

            <View style={s.card}>
              <View style={s.cover}><IconImagePlaceholder size={40} /></View>
              {titleOf(row) ? <Text style={s.cardTitle}>{titleOf(row)}</Text> : null}
              {whenOf(intent) ? (
                <View style={s.metaRow}>
                  <IconCalendar />
                  <Text style={s.metaText}>{whenOf(intent)}</Text>
                </View>
              ) : null}
              <View style={s.metaRow}>
                {online ? <IconGroups size={16} c={color.muted} /> : <IconPin size={16} c={color.muted} />}
                <Text style={s.metaText}>{online ? INVITE.linkFrom(from) : INVITE.inPerson()}</Text>
              </View>
            </View>

            <View style={s.person}>
              {row.photo ? (
                <Image source={{ uri: mediaUrl(String(row.photo)) }} style={s.personAva} />
              ) : (
                <View style={[s.personAva, s.personAvaEmpty]}><IconPerson size={18} /></View>
              )}
              <View style={{ flex: 1 }}>
                <Text style={s.personName}>{from}</Text>
                <Text style={[s.personStatus, { color: color.successText }]}>{INVITE.invitedYou()}</Text>
              </View>
            </View>
            <View style={s.person}>
              <View style={[s.personAva, s.personAvaEmpty]}><IconPerson size={18} /></View>
              <View style={{ flex: 1 }}>
                <Text style={s.personName}>{T('Ты', 'You', 'Tú')}</Text>
                {/*
                  Истёкшее и отозванное разбираются ОТДЕЛЬНО. Раньше обе ветки проваливались в
                  «Подтвердил(а)»: экран говорил ровно противоположное правде — приглашение
                  сгорело, а человек читал, что он согласился.
                */}
                <Text style={s.personStatus}>
                  {row.status === 'pending' ? CHAT.notAnswered()
                    : row.status === 'declined' ? CHAT.declinedPlan()
                    : row.status === 'expired' ? INVITE.expiredStatus()
                    : row.status === 'withdrawn' ? INVITE.withdrawnStatus()
                    : row.status === 'accepted' ? CHAT.confirmed()
                    // Остальное (например `policy_revoked`) — закрыто, но не согласие. Ветка
                    // «иначе подтвердил(а)» врала ровно так же, как раньше врала на сгоревшем.
                    : INVITE.closedStatus()}
                </Text>
              </View>
            </View>

            {err ? <Text style={s.err}>{err}</Text> : null}

            {row.status === 'pending' ? (
              <>
                <Pressable accessibilityRole="button" accessibilityState={{ busy }} style={s.cta} onPress={() => answer('accept')}>
                  {busy ? <ActivityIndicator color={color.onPrimary} /> : <Text style={s.ctaText}>{INVITE.join()}</Text>}
                </Pressable>
                <Pressable accessibilityRole="button" style={s.ctaSoft} onPress={() => answer('decline')}>
                  <Text style={s.ctaSoftText}>{INVITE.notThisTime()}</Text>
                </Pressable>
              </>
            ) : null}

            {row.status === 'declined' ? <Text style={s.note}>{INVITE.declinedNote()}</Text> : null}

            {/* Молчание — не вина: у истёкшего есть объяснение и выход, как у отказа. */}
            {row.status !== 'pending' && row.status !== 'declined' && row.status !== 'accepted' ? (
              <>
                <Text style={s.note}>
                  {row.status === 'expired' ? INVITE.expiredNote()
                    : row.status === 'withdrawn' ? INVITE.withdrawnNote()
                    : INVITE.closedNote()}
                </Text>
                <Pressable accessibilityRole="button" style={s.cta} onPress={() => router.dismissTo('/home')}>
                  <Text style={s.ctaText}>{INVITE.lookElse()}</Text>
                </Pressable>
              </>
            ) : null}

            {row.status === 'accepted' ? (
              <Pressable
                accessibilityRole="button"
                style={s.cta}
                /* Тот же случай, что в карточке кандидата: приглашение разобрано, чат встаёт на
                   его место. Соседний путь (принять прямо здесь) уже делает `replace`. */
                onPress={() => router.dismissTo({ pathname: '/conversation', params: { who: from, title: titleOf(row), photo: row.photo || '' } })}
              >
                <Text style={s.ctaText}>{CHAT.openChat()}</Text>
              </Pressable>
            ) : null}
          </>
        ) : null}
      </ScrollView>

      <View style={s.navFloat} pointerEvents="box-none">
        <BottomNav />
      </View>
    </View>
  );
}

/**
 * Время интента ГЛАЗАМИ, а не ключом поиска. `intent.time` — английская строка («today 20:00»),
 * она нужна серверу для определения срочности и на экране читается как недоперевод. Мастер кладёт
 * рядом `when` на языке интерфейса; у старых заявок его нет — тогда честнее показать что есть.
 */
function whenOf(intent: any): string {
  return String(intent?.when || intent?.time || '').trim();
}

/** Подпись интента: заголовок, а без него — темы. Приглашение без слов не показать. */
function titleOf(row: any): string {
  const t = String(row?.intent?.title || '').trim();
  if (t) return t;
  const topics = row?.intent?.topics;
  return Array.isArray(topics) ? topics.join(', ') : '';
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
  cardTitle: { ...type.title, color: color.fg } as any,
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  metaText: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,

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
  ctaSoft: { height: 52, borderRadius: rad.full, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  ctaSoftText: { ...type.button, color: color.fg } as any,
  err: { ...type.bodySmall, color: color.primary } as any,
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
