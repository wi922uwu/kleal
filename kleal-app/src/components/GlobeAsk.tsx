/**
 * «СПРОСИ ШАР» — поверх планеты «Онлайна» (владелец 17.10.2026: «подвязать с ИИшкой, инновационно и
 * интерактивно»; сценарий «спросить шар → шар отвечает → карточка с объяснением и первым сообщением»).
 *
 * Три состояния:
 *   1. ВОПРОС. Над нижней панелью — тёмная стеклянная строка с искрой Буди; над ней подсказки из
 *      своих интересов: тап — и вопрос задан. Пока Буди думает, ореолы стран бегут волной (scan).
 *   2. ШАР ОТВЕЧАЕТ. Ответ — это свет: экран отдаёт карте веса стран, совпадения горят коралловым,
 *      прочие притушены, шар доворачивает к лучшей. Сверху — короткая реплика Буди.
 *   3. КАРТОЧКИ. Снизу лента до трёх совпадений: тема, название, кто и откуда; «почему вам по
 *      пути»; первое сообщение на языке собеседника и перевод под ним. «Откликнуться» шлёт то же
 *      приглашение, что и везде, а сообщение ждёт в чате до ответа (src/online-ask.ts). «Иначе» —
 *      другой вариант сообщения. Листнули карточку — шар повернулся к её стране.
 *
 * Крестик у реплики Буди возвращает обычный шар.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View, useWindowDimensions,
} from 'react-native';
import RAnimated, { FadeOut } from 'react-native-reanimated';
import { T } from '../i18n';
import { useSheetKeyboard } from '../keyboard';
import { interestLabel } from '../interest-label';
import { sendInvite } from '../invites';
import { askGlobe, rerollOpener, topicIcon, type AskMatch, type AskResult } from '../online-ask';
import type { OnlineIntentItem } from '../online-intent-globe';
import { CategoryGlyph, iconNameFor } from './category-icons';
import { GlassPill } from './Glass';
import { IconArrowUp, IconChevronRight, IconClose, IconSpark } from './icons';
import { GlassSurface, riseIn } from './LiquidGlass';
import { color, radius as rad } from '../theme';

const INK = color.glassLight;
const DIM = 'rgba(255,255,255,0.62)';
const LINE = 'rgba(255,255,255,0.12)';
const RAISED = 'rgba(255,255,255,0.07)';
const ROSE = '#FFB4C2';
const CARD_H = 252;

const ASK = {
  placeholder: () => T('Спроси шар — с кем и чем заняться', 'Ask the globe who to do what with', 'Pregunta al globo con quién y qué hacer'),
  buddy: () => T('Буди', 'Buddy', 'Buddy'),
  thinking: () => T('Смотрю, где совпадает…', 'Looking where it fits…', 'Buscando dónde encaja…'),
  failed: () => T('Не вышло спросить. Попробуй ещё раз.', "Couldn't ask. Try again.", 'No se pudo preguntar. Inténtalo otra vez.'),
  none: () => T('Сейчас на шаре такого нет. Попробуй спросить шире.', 'Nothing like that on the globe right now. Try asking wider.', 'Ahora no hay nada así en el globo. Prueba más amplio.'),
  why: () => T('Вам по пути', 'Why you two', 'Por qué vosotros'),
  opener: () => T('Буди предлагает начать так', 'Buddy suggests starting with', 'Buddy sugiere empezar así'),
  respond: () => T('Откликнуться', 'Respond', 'Responder'),
  other: () => T('Иначе', 'Another', 'Otra'),
  sent: () => T('Отправлено вместе с сообщением', 'Sent with your message', 'Enviado con tu mensaje'),
  capped: () => T('Уже три открытых отклика', 'Three open responses already', 'Ya hay tres respuestas abiertas'),
  sendFailed: () => T('Не отправилось', "Didn't send", 'No se envió'),
  close: () => T('Закрыть', 'Close', 'Cerrar'),
  writing: () => T('Пишу сообщение…', 'Writing a message…', 'Escribiendo un mensaje…'),
  seeds: () => [
    T('С кем поиграть сегодня вечером?', 'Who can I play with tonight?', '¿Con quién juego esta noche?'),
    T('Хочу попрактиковать язык', 'I want to practise a language', 'Quiero practicar un idioma'),
  ],
  about: (topic: string) => T(`${topic}: с кем онлайн?`, `${topic} online — with whom?`, `${topic}: ¿con quién online?`),
};

const flagOf = (code: string) => /^[A-Z]{2}$/.test(code)
  ? String.fromCodePoint(0x1f1e6 + code.charCodeAt(0) - 65, 0x1f1e6 + code.charCodeAt(1) - 65) : '🌐';

type Sent = 'ok' | 'capped' | 'fail';

export function GlobeAsk({
  active, items, profile, me, bottom, topInset, onLight, onFocus, onScan, onReserve, onOpen,
}: {
  /** Вкладка «Онлайн» открыта и лист со списком закрыт. */
  active: boolean;
  items: OnlineIntentItem[];
  profile: { interests?: string[]; city?: string; languages?: unknown };
  me: string;
  /** Отступ снизу: над нижней панелью поиска. */
  bottom: number;
  topInset: number;
  /** Веса стран для шара; null — обычный вид. */
  onLight: (w: Record<string, number> | null) => void;
  /** Повернуть шар к стране. */
  onFocus: (code: string | null) => void;
  onScan: (on: boolean) => void;
  /** Сколько снизу закрыто карточками — шар поднимается над ними. */
  onReserve: (px: number) => void;
  onOpen: (item: OnlineIntentItem) => void;
}) {
  const { width } = useWindowDimensions();
  const kb = useSheetKeyboard();
  const [q, setQ] = useState('');
  const [asked, setAsked] = useState('');
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<AskResult | null>(null);
  const [err, setErr] = useState('');
  const [at, setAt] = useState(0);
  const [openers, setOpeners] = useState<Record<string, Partial<AskMatch> & { busy?: boolean }>>({});
  const [sent, setSent] = useState<Record<string, Sent>>({});
  const [sending, setSending] = useState('');
  const seq = useRef(0);

  const byId = useMemo(() => new Map(items.map((it) => [it.id, it])), [items]);
  const matches = useMemo(() => (res?.matches || []).filter((m) => byId.has(m.id)), [res, byId]);
  const cardW = width - 32;

  const reset = useCallback(() => {
    seq.current++;
    setRes(null); setErr(''); setBusy(false); setAt(0); setOpeners({}); setSent({});
    onLight(null); onScan(false); onReserve(0);
  }, [onLight, onScan, onReserve]);

  // Ушли с «Онлайна» — шар возвращается в обычный вид.
  useEffect(() => { if (!active && (res || busy)) reset(); }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  const ask = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    const my = ++seq.current;
    setAsked(question); setQ(''); setBusy(true); setErr(''); setRes(null); setOpeners({}); setSent({}); setAt(0);
    onLight(null); onScan(true);
    try {
      const r = await askGlobe(question, items, profile as any);
      if (my !== seq.current) return;
      setRes(r);
      const w = r.countries || {};
      const any = Object.keys(w).length > 0;
      onLight(any ? w : null);
      const first = r.matches.find((m) => byId.has(m.id));
      if (first?.countryCode) onFocus(first.countryCode);
      onReserve(first ? CARD_H + 16 : 0);
    } catch {
      if (my === seq.current) setErr(ASK.failed());
    } finally {
      if (my === seq.current) { setBusy(false); onScan(false); }
    }
  }, [busy, items, profile, byId, onLight, onScan, onFocus, onReserve]);

  /** Сообщение для карточки: своё из ответа, иначе дозапрос (сервер отбросил смешанное по языкам). */
  const openerOf = (m: AskMatch) => {
    const o = openers[m.id];
    return { opener: o?.opener ?? m.opener, openerTr: o?.openerTr ?? m.openerTr, busy: !!o?.busy };
  };
  const reroll = useCallback(async (m: AskMatch) => {
    const it = byId.get(m.id);
    if (!it) return;
    const prev = openerOf(m).opener;
    setOpeners((s) => ({ ...s, [m.id]: { ...(s[m.id] || {}), busy: true } }));
    try {
      const r = await rerollOpener(asked, it, profile as any, prev);
      setOpeners((s) => ({ ...s, [m.id]: { opener: r.opener || prev, openerTr: r.opener ? r.openerTr : (s[m.id]?.openerTr ?? m.openerTr), busy: false } }));
    } catch {
      setOpeners((s) => ({ ...s, [m.id]: { ...(s[m.id] || {}), busy: false } }));
    }
  }, [asked, byId, profile, openers]); // eslint-disable-line react-hooks/exhaustive-deps

  // Пустое сообщение у карточки на экране — дописать его сразу, без нажатия.
  useEffect(() => {
    const m = matches[at];
    if (m && !openerOf(m).opener && !openers[m.id]) reroll(m);
  }, [matches, at]); // eslint-disable-line react-hooks/exhaustive-deps

  const respond = useCallback(async (m: AskMatch) => {
    const it = byId.get(m.id);
    if (!it || sending) return;
    setSending(m.id);
    try {
      // Первое сообщение едет В САМОМ приглашении (поле note заявки, ЛОГИКА 17.10): получатель видит
      // его на экране приглашения. Черновик в чат больше не кладём — иначе оно ушло бы дважды.
      const r = await sendInvite(me, { name: it.who, id: it.whoId }, { title: it.title, topics: it.topics, targetIntentId: it.id }, openerOf(m).opener);
      setSent((s) => ({ ...s, [m.id]: r.ok ? 'ok' : r.capped ? 'capped' : 'fail' }));
    } catch {
      setSent((s) => ({ ...s, [m.id]: 'fail' }));
    } finally {
      setSending('');
    }
  }, [byId, me, sending, openers]); // eslint-disable-line react-hooks/exhaustive-deps

  const seeds = useMemo(() => {
    const own = (profile.interests || []).slice(0, 2).map((k) => interestLabel(k)).filter(Boolean)
      .map((t) => ASK.about(t.charAt(0).toUpperCase() + t.slice(1)));
    return [...own, ...ASK.seeds()].slice(0, 4);
  }, [profile.interests]);

  if (!active) return null;
  const answered = !!res || !!err;
  const empty = !!res && !matches.length && !res.refused;

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      {/* Реплика Буди — сверху, над шаром. */}
      {busy || answered ? (
        <RAnimated.View entering={riseIn(0, -8)} exiting={FadeOut.duration(160)} style={[s.bubbleWrap, { top: topInset }]}>
          <GlassSurface tone="dark" radius={20} style={s.fill} pointerEvents="none" />
          <View style={s.bubble}>
            <View style={s.spark}><IconSpark size={16} c={color.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.bubbleWho}>{ASK.buddy()} · <Text style={s.bubbleQ} numberOfLines={1}>{asked}</Text></Text>
              <Text style={s.bubbleText} numberOfLines={3}>
                {busy ? ASK.thinking() : err || res?.reply || (empty ? ASK.none() : '')}
              </Text>
            </View>
            {!busy ? (
              <Pressable accessibilityRole="button" accessibilityLabel={ASK.close()} onPress={reset} hitSlop={10} style={s.x}>
                <IconClose size={14} c={INK} />
              </Pressable>
            ) : <ActivityIndicator color={color.primary} />}
          </View>
        </RAnimated.View>
      ) : null}

      {/* Карточки совпадений. */}
      {matches.length && !busy ? (
        <RAnimated.View entering={riseIn(80, 14)} exiting={FadeOut.duration(160)} style={[s.cardsWrap, { bottom }]}>
          <FlatList
            data={matches}
            keyExtractor={(m) => m.id}
            horizontal
            showsHorizontalScrollIndicator={false}
            snapToInterval={cardW + 10}
            decelerationRate="fast"
            contentContainerStyle={{ paddingHorizontal: 16, gap: 10 }}
            onMomentumScrollEnd={(e) => {
              const k = Math.max(0, Math.min(matches.length - 1, Math.round(e.nativeEvent.contentOffset.x / (cardW + 10))));
              if (k !== at) { setAt(k); if (matches[k]?.countryCode) onFocus(matches[k].countryCode); }
            }}
            renderItem={({ item: m }) => {
              const it = byId.get(m.id)!;
              const o = openerOf(m);
              const st = sent[m.id];
              return (
                <View style={[s.card, { width: cardW }]}>
                  <GlassSurface tone="dark" radius={24} style={s.fill} pointerEvents="none" />
                  <Pressable accessibilityRole="button" onPress={() => onOpen(it)} style={s.head}>
                    <View style={s.topic}><CategoryGlyph name={topicIcon(it.topics, iconNameFor)} size={22} c={ROSE} /></View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.title} numberOfLines={1}>{it.title}</Text>
                      <Text style={s.who} numberOfLines={1}>{flagOf(m.countryCode)}  {it.who}{it.when ? ` · ${it.when}` : ''}</Text>
                    </View>
                    <IconChevronRight size={18} c={'rgba(255,255,255,0.4)'} />
                  </Pressable>

                  {m.why ? (
                    <View style={s.why}>
                      <IconSpark size={13} c={color.primary} />
                      <Text style={s.whyText} numberOfLines={2}><Text style={s.whyLabel}>{ASK.why()}: </Text>{m.why}</Text>
                    </View>
                  ) : null}

                  <View style={s.opener}>
                    <Text style={s.openerLabel}>{ASK.opener()}</Text>
                    {o.opener ? (
                      <>
                        <Text style={s.openerText} numberOfLines={2}>«{o.opener}»</Text>
                        {o.openerTr ? <Text style={s.openerTr} numberOfLines={1}>{o.openerTr}</Text> : null}
                      </>
                    ) : (
                      <Text style={s.openerTr}>{ASK.writing()}</Text>
                    )}
                  </View>

                  <View style={s.btns}>
                    {st === 'ok' ? (
                      <View style={s.sent}><Text style={s.sentText} numberOfLines={1}>{ASK.sent()}</Text></View>
                    ) : (
                      <GlassPill
                        tone="brand" small
                        label={st === 'capped' ? ASK.capped() : st === 'fail' ? ASK.sendFailed() : ASK.respond()}
                        busy={sending === m.id}
                        disabled={st === 'capped' || !it.who}
                        onPress={() => respond(m)}
                        style={{ flex: 1, height: 40 }}
                      />
                    )}
                    {st !== 'ok' ? (
                      <Pressable accessibilityRole="button" onPress={() => reroll(m)} disabled={o.busy} style={({ pressed }) => [s.other, pressed && { opacity: 0.7 }]}>
                        {o.busy ? <ActivityIndicator color={INK} size="small" /> : <Text style={s.otherText}>{ASK.other()}</Text>}
                      </Pressable>
                    ) : null}
                  </View>
                </View>
              );
            }}
          />
          {matches.length > 1 ? (
            <View style={s.dots} pointerEvents="none">
              {matches.map((m, i) => <View key={m.id} style={[s.dotI, i === at && s.dotOn]} />)}
            </View>
          ) : null}
        </RAnimated.View>
      ) : null}

      {/* Строка вопроса и подсказки — когда ответа нет. */}
      {!answered && !busy ? (
        <View style={[s.askWrap, { bottom: kb > 0 ? kb + 10 : bottom }]} pointerEvents="box-none">
          <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={s.seeds}>
            {seeds.map((t, i) => (
              <RAnimated.View key={t} entering={riseIn(i * 50, 6)}>
                <Pressable onPress={() => ask(t)} style={({ pressed }) => [s.seed, pressed && { transform: [{ scale: 0.96 }] }]}>
                  <Text style={s.seedText} numberOfLines={1}>{t}</Text>
                </Pressable>
              </RAnimated.View>
            ))}
          </ScrollView>
          <View style={s.bar}>
            <GlassSurface tone="dark" radius={rad.full} style={s.fill} pointerEvents="none" />
            <View style={s.barSpark}><IconSpark size={16} c={color.primary} /></View>
            <TextInput
              value={q}
              onChangeText={setQ}
              placeholder={ASK.placeholder()}
              placeholderTextColor={'rgba(255,255,255,0.5)'}
              style={s.input}
              returnKeyType="send"
              onSubmitEditing={() => ask(q)}
              maxLength={300}
            />
            <Pressable
              accessibilityRole="button"
              onPress={() => ask(q)}
              disabled={!q.trim()}
              style={[s.go, !q.trim() && { opacity: 0.4 }]}
            >
              <IconArrowUp size={18} c={'#fff'} />
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  fill: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, backgroundColor: 'rgba(26,28,33,0.9)' },

  bubbleWrap: { position: 'absolute', left: 16, right: 16, borderRadius: 20, overflow: 'hidden', borderWidth: 1, borderColor: LINE },
  bubble: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, padding: 12 },
  spark: { width: 30, height: 30, borderRadius: 10, backgroundColor: 'rgba(255,56,92,0.16)', alignItems: 'center', justifyContent: 'center' },
  bubbleWho: { fontSize: 12, fontWeight: '700', color: color.primary },
  bubbleQ: { fontWeight: '500', color: DIM },
  bubbleText: { marginTop: 2, fontSize: 13.5, lineHeight: 18, color: INK },
  x: { width: 26, height: 26, borderRadius: 13, backgroundColor: RAISED, alignItems: 'center', justifyContent: 'center' },

  askWrap: { position: 'absolute', left: 0, right: 0, gap: 8 },
  seeds: { paddingHorizontal: 16, gap: 6 },
  seed: { height: 30, paddingHorizontal: 12, borderRadius: rad.full, justifyContent: 'center', backgroundColor: 'rgba(26,28,33,0.78)', borderWidth: 1, borderColor: 'rgba(255,56,92,0.35)' },
  seedText: { fontSize: 12.5, fontWeight: '600', color: ROSE, maxWidth: 240 },
  bar: { marginHorizontal: 16, height: 48, borderRadius: 24, overflow: 'hidden', flexDirection: 'row', alignItems: 'center', paddingLeft: 8, paddingRight: 5, borderWidth: 1, borderColor: 'rgba(255,255,255,0.16)' },
  barSpark: { width: 32, height: 32, borderRadius: 16, backgroundColor: 'rgba(255,56,92,0.16)', alignItems: 'center', justifyContent: 'center' },
  input: { flex: 1, height: 46, paddingHorizontal: 10, fontSize: 15, color: INK },
  go: { width: 38, height: 38, borderRadius: 19, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },

  cardsWrap: { position: 'absolute', left: 0, right: 0 },
  card: { height: CARD_H, borderRadius: 24, overflow: 'hidden', padding: 14, gap: 10, borderWidth: 1, borderColor: 'rgba(255,56,92,0.28)' },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  topic: { width: 44, height: 44, borderRadius: 14, backgroundColor: 'rgba(255,56,92,0.16)', borderWidth: 1, borderColor: 'rgba(255,56,92,0.32)', alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 16, fontWeight: '700', color: INK },
  who: { marginTop: 1, fontSize: 12.5, color: DIM },
  why: { flexDirection: 'row', gap: 6, alignItems: 'flex-start', paddingHorizontal: 2 },
  whyLabel: { fontWeight: '700', color: ROSE },
  whyText: { flex: 1, fontSize: 13, lineHeight: 18, color: INK },
  opener: { borderRadius: 16, padding: 10, backgroundColor: RAISED, borderWidth: 1, borderColor: LINE, gap: 3 },
  openerLabel: { fontSize: 11, fontWeight: '600', color: DIM },
  openerText: { fontSize: 14, lineHeight: 19, color: INK, fontStyle: 'italic' },
  openerTr: { fontSize: 12, lineHeight: 16, color: DIM },
  btns: { flexDirection: 'row', gap: 8, marginTop: 'auto' },
  other: { height: 40, paddingHorizontal: 16, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderColor: LINE, alignItems: 'center', justifyContent: 'center', minWidth: 84 },
  otherText: { fontSize: 14, fontWeight: '600', color: INK },
  sent: { flex: 1, height: 40, borderRadius: 20, backgroundColor: 'rgba(61,220,151,0.14)', borderWidth: 1, borderColor: 'rgba(61,220,151,0.4)', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  sentText: { fontSize: 13, fontWeight: '600', color: '#9BF0C8' },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: 5, marginTop: 8 },
  dotI: { width: 5, height: 5, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.3)' },
  dotOn: { width: 16, backgroundColor: color.primary },
});
