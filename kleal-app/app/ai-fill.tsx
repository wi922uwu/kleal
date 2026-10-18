/**
 * «ЗАПОЛНИТЬ ЧЕРЕЗ ChatGPT» — экран подключения и черновика (18.10.2026, поручение Ивана через ЛОГИКУ).
 *
 * Открывается кнопкой на приветствии анкеты (StartW в app/chat.tsx). Два пути к одному черновику:
 *   • КОННЕКТОР — личная ссылка (MCP) добавляется в ChatGPT на компьютере; человек пишет там «заполни
 *     мой профиль в Kleal», ChatGPT кладёт черновик. Экран спрашивает сервер раз в 3,5 с и показывает
 *     «Черновик пришёл», как только он лёг;
 *   • ВСТАВКА — для всех остальных: спросить ChatGPT обычным чатом, скопировать ответ, вставить сюда.
 *
 * Черновик ничего не сохраняет сам: лист «Вот что прислал ChatGPT» (AiDraftView), человек убирает
 * лишнее и подтверждает. С 18.10.2026 — короткий путь: всё оставленное сразу в анкету
 * (applyAiDraftFull), затем «Осталось немного» (app/ai-finish.tsx) и конец анкеты. Компоненты и слова — сессия «ДИЗАЙН (fork)»: src/components/AiFill.tsx,
 * src/ai-fill.ts.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useIsFocused, useRouter } from 'expo-router';
import { useLang, T, replyLang } from '../src/i18n';
import { hOk } from '../src/haptics';
import { AI, aiDraft, aiLink, aiPaste, PASTE_MAX, type AiDraft, type AiLink, type AiProfile } from '../src/ai-fill';
import { applyAiDraftFull } from '../src/ai-suggest';
import { api, profile as profileApi } from '../src/api';
import { addConfirmedInterest } from '../src/profile';
import { get } from '../src/state';
import { GlassChip } from '../src/components/Glass';
import { GlassSurface } from '../src/components/LiquidGlass';
import { AiDraftView, AiFillStatus, AiPasteBox, AiSpinner } from '../src/components/AiFill';
import { AiConnectFlow } from '../src/components/AiConnectFlow';
import { IconChevronLeft } from '../src/components/icons';
import { Ambient } from '../src/components/Ambient';
import { color, font, space } from '../src/theme';

/** Как часто спрашивать черновик, пока ждём ChatGPT (контракт: раз в 3–4 с). */
const POLL_MS = 3500;

type Mode = 'connect' | 'paste' | 'review';

export default function AiFill() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const focused = useIsFocused();
  const [mode, setMode] = useState<Mode>('connect');
  const [link, setLink] = useState<AiLink | null>(null);
  const [linkErr, setLinkErr] = useState(false);
  const [draft, setDraft] = useState<AiDraft | null>(null);
  const [now, setNow] = useState(Date.now());
  const [pasteBusy, setPasteBusy] = useState(false);
  const [pasteErr, setPasteErr] = useState('');
  const [saving, setSaving] = useState(false);

  /** Новая ссылка (она гасит прежнюю). */
  const makeLink = useCallback(async () => {
    setLinkErr(false);
    try {
      const l = await aiLink();
      if (!l.url) throw new Error('no url');
      setLink(l);
    } catch { setLinkErr(true); }
  }, []);

  // Открыли экран: черновик мог уже лежать (ChatGPT заполнил раньше) — тогда сразу лист.
  useEffect(() => {
    let alive = true;
    aiDraft('get').then((d) => { if (alive && d) { setDraft(d); setMode('review'); } }).catch(() => {});
    makeLink();
    return () => { alive = false; };
  }, [makeLink]);

  // Ждём ChatGPT: опрос, пока открыт путь «коннектор» и экран в фокусе.
  const draftRef = useRef(draft);
  draftRef.current = draft;
  useEffect(() => {
    if (mode !== 'connect' || !focused) return;
    const id = setInterval(() => {
      setNow(Date.now());
      if (draftRef.current) return;
      aiDraft('get').then((d) => { if (d) { hOk(); setDraft(d); } }).catch(() => {});
    }, POLL_MS);
    return () => clearInterval(id);
  }, [mode, focused]);

  const expired = !!link?.expiresAt && link.expiresAt <= now;

  /** Вставленный ответ ChatGPT → черновик. Свои слова отказа — у каждой причины свои. */
  const submitPaste = async (text: string) => {
    const t = String(text || '').trim();
    if (!t) return;
    if (t.length > PASTE_MAX) { setPasteErr(AI.pasteError('too_long')); return; }
    setPasteBusy(true);
    setPasteErr('');
    try {
      const r = await aiPaste(t);
      if (r.draft) { hOk(); setDraft(r.draft); setMode('review'); }
      else setPasteErr(AI.pasteError(String(r.error || '')));
    } catch { setPasteErr(AI.pasteError('network')); }
    finally { setPasteBusy(false); }
  };

  /**
   * «Добавить в профиль» — КОРОТКИЙ ПУТЬ (18.10.2026, Иван: «зачем мне ещё раз проходить онбординг»).
   * Оставленное на листе подтверждено здесь и пишется в анкету целиком; дальше — один экран
   * «Осталось немного» (app/ai-finish.tsx) с недостающим, и оттуда в конец анкеты. Имя аккаунта
   * сервер отдаёт рядом с черновиком (account_name) — его подставит экран.
   */
  const confirm = async (p: AiProfile) => {
    setSaving(true);
    let accountName = '';
    try {
      const r: any = await api.post('/api/onboarding/ai-draft', { action: 'get' });
      accountName = String(r?.account_name || '').trim();
    } catch { /* без имени аккаунта — человек впишет сам */ }
    applyAiDraftFull(p);
    aiDraft('discard').catch(() => {});
    hOk();
    router.replace({ pathname: '/ai-finish', params: accountName ? { name: accountName } : {} });
  };
  const discard = () => {
    aiDraft('discard').catch(() => {});
    setDraft(null);
    setMode('connect');
  };

  return (
    <View style={s.wrap}>
      <Ambient />
      <View style={[s.head, { paddingTop: insets.top + 6 }]}>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back', 'Atrás')} hitSlop={10}
                   onPress={() => (mode === 'paste' || (mode === 'review' && !saving) ? setMode('connect') : router.back())}
                   style={s.back}>
          <IconChevronLeft size={22} c={color.fg} />
        </Pressable>
        <Text style={s.headTitle} numberOfLines={1}>{mode === 'review' ? AI.draftTitle() : AI.cardTitle()}</Text>
        <View style={s.spacer} />
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={[s.body, { paddingBottom: insets.bottom + space.xl }]}
                    keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
          {mode === 'review' && draft ? (
            <>
              {/* Нераспознанные интересы — вопросом до «Добавить в профиль» (18.10.2026). */}
              <InterestReview items={Array.isArray((draft as any).review) ? (draft as any).review : []} />
              <AiDraftView draft={draft} onConfirm={confirm} onDiscard={discard} busy={saving} />
            </>
          ) : mode === 'paste' ? (
            <AiPasteBox onSubmit={submitPaste} busy={pasteBusy} error={pasteErr} prompt={link?.pastePrompt} />
          ) : (
            <>
              {/* Подключение — три шага и одна главная кнопка (18.10.2026, src/components/AiConnectFlow.tsx). */}
              {link ? (
                <AiConnectFlow url={link.url} prompt={link.prompt} expired={expired} arrived={!!draft}
                               onReview={() => setMode('review')} onNewLink={makeLink} onPaste={() => setMode('paste')} />
              ) : linkErr ? (
                <AiFillStatus state="error" onAction={makeLink} />
              ) : <AiSpinner color={color.primary} style={{ marginTop: space.lg }} />}
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

/**
 * «ЧТО ТЫ ИМЕЛ В ВИДУ?» — интересы черновика, которые сервер не свёл к реестру однозначно (draft.review,
 * ЛОГИКА 18.10.2026). Известное сервер уже положил ключами в interests.explicit; здесь — остальное:
 *   confirm    — один вариант: «Kleal понял так: «автомобили» → «Cars». Верно?» [Да] [Убрать];
 *   clarify    — вопрос и 2–3 варианта: человек выбирает один;
 *   unresolved — вариантов нет: «Назови иначе» → interest-normalize, дальше как в анкете.
 * Подтверждение — тем же путём, что в разговоре анкеты: interest-confirm → квитанция → addConfirmedInterest.
 * Неотвеченное просто не попадает в профиль — «Добавить в профиль» не ждёт.
 */
type ReviewOpt = { canonical: string; label: string; token: string };
type ReviewItem = { raw: string; status: 'confirm' | 'clarify' | 'unresolved'; question?: string; options?: ReviewOpt[] };
type ReviewState = { done?: string; gone?: boolean; busy?: boolean; err?: boolean; opts?: ReviewOpt[]; text?: string };

function InterestReview({ items }: { items: ReviewItem[] }) {
  const [state, setState] = useState<Record<string, ReviewState>>({});
  if (!items.length) return null;
  const upd = (raw: string, v: ReviewState) => setState((m) => ({ ...m, [raw]: { ...(m[raw] || {}), ...v } }));
  const pick = async (raw: string, o: ReviewOpt) => {
    upd(raw, { busy: true, err: false });
    try {
      const r = await profileApi.confirmInterest('', o.token);
      if (r.ok && r.canonical && r.token) {
        addConfirmedInterest(r.canonical, r.label || o.label, r.token);
        hOk();
        upd(raw, { busy: false, done: r.label || o.label });
      } else upd(raw, { busy: false, err: true });
    } catch { upd(raw, { busy: false, err: true }); }
  };
  const rename = async (raw: string) => {
    const text = String(state[raw]?.text || '').trim();
    if (!text) return;
    upd(raw, { busy: true, err: false });
    try {
      const r = await profileApi.normalizeInterest(text, get('interests.explicit') || [], replyLang());
      if (r.status === 'duplicate') { upd(raw, { busy: false, done: text }); return; }
      const opts = r.options || [];
      if (opts.length === 1 && r.status === 'ready') { await pick(raw, opts[0]); return; }
      if (opts.length) { upd(raw, { busy: false, opts }); return; }
      upd(raw, { busy: false, err: true });
    } catch { upd(raw, { busy: false, err: true }); }
  };
  const open = items.filter((it) => !state[it.raw]?.gone);
  if (!open.length) return null;
  return (
    <View style={s.review}>
      <Text style={s.reviewTitle}>{REVIEW.title()}</Text>
      {open.map((it) => {
        const st = state[it.raw] || {};
        const opts = st.opts || it.options || [];
        const single = it.status === 'confirm' && !!opts[0] && !st.opts;
        return (
          <GlassSurface key={it.raw} tone="light" radius={18} style={s.reviewCard}>
            {st.done ? (
              <Text style={s.reviewText}>{REVIEW.added(it.raw, st.done)}</Text>
            ) : (
              <>
                <Text style={s.reviewText}>
                  {single ? REVIEW.confirm(it.raw, opts[0].label || opts[0].canonical)
                    : opts.length ? (it.question || REVIEW.which(it.raw)) : REVIEW.unknown(it.raw)}
                </Text>
                {single ? (
                  <View style={s.reviewRow}>
                    <GlassChip label={REVIEW.yes()} on onPress={() => pick(it.raw, opts[0])} />
                    <GlassChip label={REVIEW.remove()} onPress={() => upd(it.raw, { gone: true })} />
                  </View>
                ) : opts.length ? (
                  <View style={s.reviewRow}>
                    {opts.map((o) => <GlassChip key={o.token} label={o.label || o.canonical} onPress={() => pick(it.raw, o)} />)}
                    <GlassChip label={REVIEW.remove()} onPress={() => upd(it.raw, { gone: true })} />
                  </View>
                ) : (
                  <View style={s.reviewRow}>
                    <View style={s.reviewInput}>
                      <TextInput value={st.text || ''} onChangeText={(t) => upd(it.raw, { text: t })} placeholder={REVIEW.renamePh()}
                                 placeholderTextColor={color.muted} style={s.reviewInputText} onSubmitEditing={() => rename(it.raw)} returnKeyType="done" />
                    </View>
                    <GlassChip label={REVIEW.ok()} on onPress={() => rename(it.raw)} />
                    <GlassChip label={REVIEW.remove()} onPress={() => upd(it.raw, { gone: true })} />
                  </View>
                )}
                {st.busy ? <AiSpinner color={color.primary} /> : null}
                {st.err ? <Text style={s.reviewErr}>{REVIEW.failed()}</Text> : null}
              </>
            )}
          </GlassSurface>
        );
      })}
    </View>
  );
}

const REVIEW = {
  title: () => T('Kleal не узнал пару интересов', 'Kleal didn’t recognise a couple of interests', 'Kleal no reconoció un par de intereses'),
  confirm: (raw: string, label: string) => T(`Kleal понял так: «${raw}» → «${label}». Верно?`, `Kleal took “${raw}” as “${label}”. Right?`, `Kleal entendió «${raw}» como «${label}». ¿Correcto?`),
  which: (raw: string) => T(`Что ты имел в виду под «${raw}»?`, `What did you mean by “${raw}”?`, `¿Qué querías decir con «${raw}»?`),
  unknown: (raw: string) => T(`«${raw}» Kleal не знает. Назови иначе?`, `Kleal doesn’t know “${raw}”. Call it something else?`, `Kleal no conoce «${raw}». ¿Lo llamas de otra forma?`),
  added: (raw: string, label: string) => T(`✓ «${raw}» — добавлено как «${label}»`, `✓ “${raw}” — added as “${label}”`, `✓ «${raw}» — añadido como «${label}»`),
  yes: () => T('Да', 'Yes', 'Sí'),
  remove: () => T('Убрать', 'Remove', 'Quitar'),
  ok: () => T('Готово', 'Done', 'Listo'),
  renamePh: () => T('Например, автоспорт', 'E.g. motorsport', 'P. ej., automovilismo'),
  failed: () => T('Не получилось — попробуй другое слово или убери.', 'That didn’t work — try another word or remove it.', 'No ha funcionado: prueba otra palabra o quítalo.'),
};

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: 8, gap: 8 },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.85)' },
  spacer: { width: 44, height: 44 },
  review: { gap: 10, marginBottom: space.md },
  reviewTitle: { fontFamily: font.displaySemi, fontSize: 17, lineHeight: 22, color: color.fg } as any,
  reviewCard: { padding: 14, gap: 10 },
  reviewText: { fontFamily: font.text, fontSize: 15, lineHeight: 21, color: color.fg } as any,
  reviewRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  reviewInput: { flexGrow: 1, minWidth: 140, height: 40, borderRadius: 20, paddingHorizontal: 14, justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.85)' },
  reviewInputText: { fontFamily: font.text, fontSize: 15, color: color.fg } as any,
  reviewErr: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.primary } as any,
  headTitle: { flex: 1, textAlign: 'center', fontFamily: font.displaySemi, fontSize: 17, lineHeight: 22, color: color.fg } as any,
  body: { paddingHorizontal: 16, paddingTop: 8, gap: space.md },
});
