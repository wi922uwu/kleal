/**
 * «ЗАПОЛНИТЬ ЧЕРЕЗ ChatGPT» — дизайн-система фичи (18.10.2026; слова и данные — src/ai-fill.ts).
 *
 * Компоненты ничего не сохраняют и в сеть не ходят: только показывают и зовут колбэки. Встраивание в
 * онбординг, опрос черновика и слияние с анкетой — у экрана (сессия ДИЗАЙН).
 *
 *   AiFillCard     — карточка рядом с «Поехали!» на приветствии: не перебивает главную кнопку —
 *                    светлое стекло, а не коралл; коралловый здесь только значок.
 *   AiConnectGuide — подключение в четыре шага. Каждый шаг — маленький рисованный кодом макет экрана
 *                    ChatGPT с подсвеченным местом нажатия (без чужих логотипов: это схема, а не копия
 *                    их интерфейса). Ссылка и фраза копируются одной кнопкой каждая.
 *   AiPasteBox     — запасной путь для всех: вставить ответ ChatGPT и разобрать.
 *   AiDraftView    — «Вот что прислал ChatGPT»: группы, чипы, у каждого пункта «убрать»; AiDraftSheet —
 *                    то же в нашем Sheet.
 *   AiFillStatus   — плашка состояния: ждём / пришёл / ошибка / истекла / «на телефоне нельзя».
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Easing, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import RAnimated from 'react-native-reanimated';
import {
  AI, PASTE_MAX, draftItems, itemId, keepOnly, type AiDraft, type AiGroup, type AiItem, type AiProfile,
} from '../ai-fill';
import { hOk, hTap } from '../haptics';
import { GlassPill } from './Glass';
import { GlassSurface, usePress } from './LiquidGlass';
import { Sheet } from './Sheet';
import {
  IconAlertTriangle, IconChat, IconCheck, IconChevronRight, IconClock, IconClose, IconCopy, IconLink,
  IconPlusRound, IconSpark,
} from './icons';
import { color, font, space, type } from '../theme';

// ===== карточка

export function AiFillCard({ onPress, compact = false }: { onPress: () => void; compact?: boolean }) {
  const p = usePress(0.97);
  return (
    <RAnimated.View style={p.style}>
      <Pressable accessibilityRole="button" accessibilityLabel={AI.cardTitle()} onPress={() => { hTap(); onPress(); }}
        onPressIn={p.onPressIn} onPressOut={p.onPressOut} style={[s.card, compact && s.cardCompact]}>
        <GlassSurface tone="light" radius={compact ? 18 : 22} style={s.fill} pointerEvents="none" />
        <AiMark size={compact ? 36 : 44} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={s.cardHead}>
            <Text style={s.cardTitle} numberOfLines={1}>{AI.cardTitle()}</Text>
            {!compact ? <View style={s.badge}><Text style={s.badgeText}>{AI.cardBadge()}</Text></View> : null}
          </View>
          {!compact ? <Text style={s.cardSub} numberOfLines={2}>{AI.cardSub()}</Text> : null}
        </View>
        <IconChevronRight size={18} c={color.muted} />
      </Pressable>
    </RAnimated.View>
  );
}

/** Знак фичи: пузырь чата с искрой Kleal — без логотипа OpenAI. */
export function AiMark({ size = 44 }: { size?: number }) {
  return (
    <View style={[s.mark, { width: size, height: size, borderRadius: size * 0.32 }]}>
      <IconChat size={size * 0.5} c={'#fff'} />
      <View style={[s.markSpark, { width: size * 0.42, height: size * 0.42, borderRadius: size * 0.21 }]}>
        <IconSpark size={size * 0.26} c={'#fff'} />
      </View>
    </View>
  );
}

// ===== инструкция

export function AiConnectGuide({
  url, prompt, expiresAt, onPaste, now = Date.now(),
}: {
  url: string;
  prompt: string;
  /** мс; 0 — без срока. */
  expiresAt?: number;
  /** Показать запасной путь (AiPasteBox) — экран решает, где. */
  onPaste?: () => void;
  now?: number;
}) {
  const steps = AI.steps();
  const left = expiresAt ? Math.max(0, Math.round((expiresAt - now) / 60000)) : 0;
  return (
    <View style={s.guide}>
      <View style={s.guideHead}>
        <AiMark size={40} />
        <View style={{ flex: 1 }}>
          <Text style={s.guideTitle}>{AI.guideTitle()}</Text>
          <Text style={s.guideSub}>{AI.guideSub()}</Text>
        </View>
      </View>

      {steps.map((st, i) => (
        <View key={i} style={s.step}>
          <View style={s.stepRail}>
            <View style={s.stepNum}><Text style={s.stepNumText}>{i + 1}</Text></View>
            {i < steps.length - 1 ? <View style={s.stepLine} /> : null}
          </View>
          <View style={{ flex: 1, paddingBottom: space.lg }}>
            <Text style={s.stepTitle}>{st.t}</Text>
            <Text style={s.stepSub}>{st.d}</Text>
            <StepArt n={i} url={url} />
            {i === 2 ? <CopyRow label={AI.link()} value={url} action={AI.copyLink()} mono icon={<IconLink size={16} c={color.primary} />} /> : null}
            {i === 3 ? <CopyRow label={AI.phrase()} value={prompt} action={AI.copyPhrase()} icon={<IconChat size={16} c={color.primary} />} /> : null}
          </View>
        </View>
      ))}

      <View style={s.guideFoot}>
        {left ? <Text style={s.footNote}><IconClock size={12} c={color.muted} /> {AI.expiresIn(left)}</Text> : null}
        <Text style={s.footNote}>{AI.personal()}</Text>
      </View>
      {onPaste ? (
        <Pressable onPress={onPaste} style={({ pressed }) => [s.pasteLink, pressed && { opacity: 0.6 }]}>
          <Text style={s.pasteLinkText}>{AI.pasteTitle()}</Text>
          <IconChevronRight size={16} c={color.primary} />
        </Pressable>
      ) : null}
    </View>
  );
}

function CopyRow({ label, value, action, mono, icon }: { label: string; value: string; action: string; mono?: boolean; icon: React.ReactNode }) {
  const [done, setDone] = useState(false);
  const t = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (t.current) clearTimeout(t.current); }, []);
  const copy = async () => {
    try { await Clipboard.setStringAsync(value); hOk(); setDone(true); } catch { /* буфер недоступен — молчим */ }
    if (t.current) clearTimeout(t.current);
    t.current = setTimeout(() => setDone(false), 1800);
  };
  return (
    <View style={s.copy}>
      <View style={s.copyHead}>{icon}<Text style={s.copyLabel}>{label}</Text></View>
      <Text style={[s.copyValue, mono && s.mono]} numberOfLines={mono ? 1 : 3} ellipsizeMode="middle" selectable>{value || '—'}</Text>
      <GlassPill tone={done ? 'light' : 'brand'} small disabled={!value}
        icon={done ? <IconCheck size={16} c={color.fg} /> : <IconCopy size={16} c={'#fff'} />}
        label={done ? AI.copied() : action} onPress={copy} style={{ height: 40, marginTop: 8 }} />
    </View>
  );
}

/*
 * Схемы шагов — рисованные кодом мини-экраны: серые полосы вместо текста, коралловое кольцо там,
 * куда нажать. Нейтральные, без цветов и знаков ChatGPT — человек узнаёт место, а не копию.
 */
function StepArt({ n, url }: { n: number; url: string }) {
  return (
    <View style={s.art}>
      {n === 0 ? (
        <View style={s.artRow}>
          <View style={s.artSide}>
            <Bar w="80%" /><Bar w="60%" /><Bar w="70%" />
            <View style={{ flex: 1 }} />
            <View style={s.artAvatarRow}>
              <Ring><View style={s.artAvatar} /></Ring>
              <Bar w={36} />
            </View>
          </View>
          <View style={s.artMain}>
            <View style={s.artMenu}>
              <Bar w="70%" />
              <Ring><View style={s.artMenuItem}><Text style={s.artText}>⚙︎ Settings</Text></View></Ring>
              <Bar w="50%" />
            </View>
          </View>
        </View>
      ) : n === 1 ? (
        <View style={s.artRow}>
          <View style={s.artSideNarrow}>
            <Bar w="70%" /><Bar w="80%" />
            <Ring><View style={s.artTab}><Text style={s.artText} numberOfLines={1}>Apps & Connectors</Text></View></Ring>
            <Bar w="60%" />
          </View>
          <View style={s.artMain}>
            <Text style={s.artCaption}>Advanced settings</Text>
            <View style={s.artToggleRow}>
              <Text style={s.artText}>Developer mode</Text>
              <Ring><View style={s.artToggle}><View style={s.artKnob} /></View></Ring>
            </View>
            <Bar w="85%" /><Bar w="55%" />
          </View>
        </View>
      ) : n === 2 ? (
        <View style={[s.artMain, { flex: undefined }]}>
          <Text style={s.artCaption}>Create · MCP Server URL</Text>
          <View style={s.artField}><Text style={s.artText}>Name: Kleal</Text></View>
          <Ring><View style={s.artField}><Text style={[s.artText, s.mono]} numberOfLines={1} ellipsizeMode="middle">{url || 'https://aiopenware.com/mcp/…'}</Text></View></Ring>
          <Ring><View style={[s.artField, s.artSelect]}><Text style={s.artText}>No authentication</Text><Text style={s.artText}>▾</Text></View></Ring>
        </View>
      ) : (
        <View style={[s.artMain, { flex: undefined, gap: 8 }]}>
          <View style={s.artBubble}><Bar w="70%" /><Bar w="40%" /></View>
          <View style={s.artComposer}>
            <Ring><View style={s.artPlus}><IconPlusRound size={16} c={color.fg} /></View></Ring>
            <View style={s.artKleal}><Text style={s.artText}>Developer mode ›</Text></View>
            <View style={s.artKleal}><AiMark size={16} /><Text style={s.artText}>Kleal</Text></View>
            <Text style={[s.artText, { flex: 1, color: color.muted }]} numberOfLines={1}>…</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const Bar = ({ w }: { w: number | `${number}%` }) => <View style={[s.bar, { width: w }]} />;
const Ring = ({ children }: { children: React.ReactNode }) => <View style={s.ring}>{children}</View>;

// ===== запасной путь

export function AiPasteBox({ onSubmit, busy, error, prompt }: {
  onSubmit: (text: string) => void; busy?: boolean;
  /** Текст ошибки (AI.pasteError(code)) или код — покажем словами. */
  error?: string;
  /** Фраза для обычного чата ChatGPT (paste_prompt с сервера) — с кнопкой «Скопировать». */
  prompt?: string;
}) {
  const [text, setText] = useState('');
  const paste = async () => {
    try { const t = await Clipboard.getStringAsync(); if (t) setText(t); } catch { /* ничего */ }
  };
  return (
    <View style={s.paste}>
      <Text style={s.pasteTitle}>{AI.pasteTitle()}</Text>
      <Text style={s.guideSub}>{AI.pasteSub()}</Text>
      {prompt ? <CopyRow label={AI.phrase()} value={prompt} action={AI.copyPhrase()} icon={<IconChat size={16} c={color.primary} />} /> : null}
      <View style={s.pasteField}>
        <GlassSurface tone="light" radius={18} style={s.fill} pointerEvents="none" />
        <TextInput
          value={text} onChangeText={setText} multiline textAlignVertical="top"
          placeholder={AI.pastePlaceholder()} placeholderTextColor={color.muted} style={s.pasteInput} maxLength={PASTE_MAX}
        />
        {!text ? (
          <Pressable onPress={paste} style={s.pasteBtn} hitSlop={8}>
            <IconCopy size={14} c={color.primary} /><Text style={s.pasteBtnText}>{AI.fromClipboard()}</Text>
          </Pressable>
        ) : null}
      </View>
      {error ? <Text style={s.err}>{/^[a-z_ ]+$/.test(error) ? AI.pasteError(error) : error}</Text> : null}
      <GlassPill tone="brand" small label={AI.pasteGo()} busy={busy} disabled={!text.trim()} onPress={() => onSubmit(text)} style={{ height: 44 }} />
    </View>
  );
}

// ===== черновик

const GROUPS: AiGroup[] = ['city', 'languages', 'interests', 'about', 'goals', 'vibe', 'format'];
const CHIPPY = new Set<AiGroup>(['languages', 'interests', 'goals', 'vibe']);

export function AiDraftView({
  draft, onConfirm, onDiscard, busy,
}: {
  draft: AiDraft;
  /** Черновик без убранного — экран сливает его с анкетой. */
  onConfirm: (profile: AiProfile) => void;
  onDiscard: () => void;
  busy?: boolean;
}) {
  const items = useMemo(() => draftItems(draft.profile || {}), [draft]);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const toggle = (it: AiItem) => setRemoved((r) => { const n = new Set(r); const k = itemId(it); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const left = items.filter((it) => !removed.has(itemId(it))).length;
  if (!items.length) {
    return (
      <View style={s.draft}>
        <Text style={s.guideSub}>{AI.nothing()}</Text>
        <GlassPill tone="light" small label={AI.discard()} onPress={onDiscard} style={{ height: 44, marginTop: space.md }} />
      </View>
    );
  }
  return (
    <View style={s.draft}>
      <View style={s.source}><AiMark size={20} /><Text style={s.sourceText}>{draft.source === 'paste' ? AI.fromPaste() : AI.fromMcp()}</Text></View>
      <Text style={s.guideSub}>{AI.draftSub()}</Text>
      {GROUPS.map((g) => {
        const its = items.filter((it) => it.group === g);
        if (!its.length) return null;
        return (
          <View key={g} style={s.group}>
            <Text style={s.groupTitle}>{AI.group(g)}</Text>
            {CHIPPY.has(g) ? (
              <View style={s.chips}>
                {its.map((it) => {
                  const off = removed.has(itemId(it));
                  return (
                    <Pressable key={itemId(it)} accessibilityRole="button" accessibilityLabel={`${off ? AI.restore() : AI.remove()}: ${it.label}`}
                      onPress={() => { hTap(); toggle(it); }} style={[s.chip, off && s.chipOff]}>
                      <Text style={[s.chipText, off && s.chipTextOff]} numberOfLines={1}>{it.label}</Text>
                      {off ? <Text style={s.chipRestore}>↺</Text> : <IconClose size={12} c={color.primary} />}
                    </Pressable>
                  );
                })}
              </View>
            ) : its.map((it) => {
              const off = removed.has(itemId(it));
              return (
                <View key={itemId(it)} style={[s.line, off && s.lineOff]}>
                  <Text style={[s.lineText, off && s.chipTextOff]} numberOfLines={g === 'about' ? 6 : 2}>{it.label}</Text>
                  <Pressable accessibilityRole="button" accessibilityLabel={off ? AI.restore() : AI.remove()} onPress={() => { hTap(); toggle(it); }} hitSlop={8} style={s.lineX}>
                    {off ? <Text style={s.chipRestore}>↺</Text> : <IconClose size={14} c={color.muted} />}
                  </Pressable>
                </View>
              );
            })}
          </View>
        );
      })}
      <View style={s.draftBtns}>
        <GlassPill tone="brand" small label={AI.confirm(left)} busy={busy} disabled={!left}
          onPress={() => onConfirm(keepOnly(draft.profile || {}, removed))} style={{ flex: 1, height: 44 }} />
        <GlassPill tone="light" small label={AI.discard()} onPress={onDiscard} style={{ height: 44, paddingHorizontal: space.md }} />
      </View>
    </View>
  );
}

export function AiDraftSheet({
  visible, onClose, ...rest
}: { visible: boolean; onClose: () => void } & React.ComponentProps<typeof AiDraftView>) {
  return (
    <Sheet visible={visible} onClose={onClose} title={AI.draftTitle()}>
      <AiDraftView {...rest} />
    </Sheet>
  );
}

// ===== состояния

export type AiFillState = 'waiting' | 'arrived' | 'error' | 'expired' | 'mobile';

export function AiFillStatus({
  state, onAction, onSecondary,
}: {
  state: AiFillState;
  /** arrived → «Посмотреть», error → «Ещё раз», expired → «Новая ссылка», mobile → «Вставить ответ». */
  onAction?: () => void;
  onSecondary?: () => void;
}) {
  const v = {
    waiting: { t: AI.waitingTitle(), d: AI.waitingSub(), a: '', tone: 'calm' },
    arrived: { t: AI.arrivedTitle(), d: AI.arrivedSub(), a: AI.review(), tone: 'good' },
    error: { t: AI.errorTitle(), d: AI.errorSub(), a: AI.retry(), tone: 'warn' },
    expired: { t: AI.expiredTitle(), d: AI.expiredSub(), a: AI.newLink(), tone: 'warn' },
    mobile: { t: AI.mobileTitle(), d: AI.mobileSub(), a: AI.pasteInstead(), tone: 'calm' },
  }[state];
  return (
    <View style={s.status}>
      <GlassSurface tone="light" radius={20} style={s.fill} pointerEvents="none" />
      <View style={[s.statusIcon, v.tone === 'good' && s.iconGood, v.tone === 'warn' && s.iconWarn]}>
        {state === 'waiting' ? <Dots />
          : state === 'arrived' ? <IconCheck size={18} c={'#fff'} />
          : state === 'expired' ? <IconClock size={18} c={color.fg} />
          : state === 'mobile' ? <IconLink size={18} c={color.fg} />
          : <IconAlertTriangle size={18} c={color.fg} />}
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={s.statusTitle}>{v.t}</Text>
        <Text style={s.statusSub}>{v.d}</Text>
        {v.a && onAction ? (
          <View style={s.statusBtns}>
            <GlassPill tone={state === 'arrived' ? 'brand' : 'light'} small label={v.a} onPress={onAction} style={{ height: 36 }} />
            {onSecondary && state === 'expired' ? <GlassPill tone="light" small label={AI.pasteInstead()} onPress={onSecondary} style={{ height: 36 }} /> : null}
          </View>
        ) : null}
      </View>
    </View>
  );
}

/** Три точки ожидания — как у «Kleal печатает»: мягкая волна, без вертушки. */
function Dots() {
  const v = useRef([0, 1, 2].map(() => new Animated.Value(0.3))).current;
  useEffect(() => {
    const loops = v.map((a, i) => Animated.loop(Animated.sequence([
      Animated.delay(i * 160),
      Animated.timing(a, { toValue: 1, duration: 360, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      Animated.timing(a, { toValue: 0.3, duration: 360, easing: Easing.in(Easing.quad), useNativeDriver: true }),
      Animated.delay((2 - i) * 160),
    ])));
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, [v]);
  return (
    <View style={{ flexDirection: 'row', gap: 3 }}>
      {v.map((a, i) => <Animated.View key={i} style={[s.dot, { opacity: a, transform: [{ scale: a }] }]} />)}
    </View>
  );
}

export { ActivityIndicator as AiSpinner };

// ===== вид
const ART_BG = '#F6F7F9';
const s = StyleSheet.create({
  fill: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0 },

  card: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, borderRadius: 22, overflow: 'hidden' },
  cardCompact: { paddingVertical: 8, borderRadius: 18 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardTitle: { flexShrink: 1, fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.fg },
  cardSub: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  badge: { paddingHorizontal: 7, height: 20, borderRadius: 10, backgroundColor: 'rgba(255,56,92,0.10)', justifyContent: 'center' },
  badgeText: { fontSize: 11, fontWeight: '600', color: color.primary },

  mark: { backgroundColor: color.ink, alignItems: 'center', justifyContent: 'center' },
  markSpark: { position: 'absolute', right: -4, bottom: -4, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#fff' },

  guide: { gap: space.md },
  guideHead: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: space.sm },
  guideTitle: { fontFamily: font.textMedium, fontSize: 18, lineHeight: 24, color: color.fg },
  guideSub: { ...type.bodySmall, color: color.muted } as any,
  step: { flexDirection: 'row', gap: 12 },
  stepRail: { alignItems: 'center', width: 28 },
  stepNum: { width: 28, height: 28, borderRadius: 14, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  stepNumText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  stepLine: { flex: 1, width: 2, borderRadius: 1, backgroundColor: 'rgba(255,56,92,0.18)', marginTop: 4 },
  stepTitle: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.fg, marginTop: 3 },
  stepSub: { ...type.caption, color: color.muted, marginTop: 1 } as any,
  guideFoot: { gap: 2, alignItems: 'center' },
  footNote: { ...type.caption, color: color.muted, textAlign: 'center' } as any,
  pasteLink: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 8 },
  pasteLinkText: { fontFamily: font.textMedium, fontSize: 14, color: color.primary },

  copy: { marginTop: 10, padding: 12, borderRadius: 16, backgroundColor: '#fff', borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(24,27,34,0.12)' },
  copyHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 },
  copyLabel: { fontSize: 12, fontWeight: '600', color: color.muted },
  copyValue: { fontSize: 14, lineHeight: 19, color: color.fg },
  mono: { fontFamily: 'Menlo', fontSize: 12.5 },

  art: { marginTop: 10, padding: 10, borderRadius: 14, backgroundColor: ART_BG, borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(24,27,34,0.10)' },
  artRow: { flexDirection: 'row', gap: 8, height: 92 },
  artSide: { width: 72, borderRadius: 8, backgroundColor: '#fff', padding: 6, gap: 5 },
  artSideNarrow: { width: 100, borderRadius: 8, backgroundColor: '#fff', padding: 6, gap: 5 },
  artMain: { flex: 1, borderRadius: 8, backgroundColor: '#fff', padding: 8, gap: 6 },
  artAvatarRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  artAvatar: { width: 16, height: 16, borderRadius: 8, backgroundColor: '#C9CED6' },
  artMenu: { gap: 6, marginTop: 'auto' },
  artMenuItem: { paddingHorizontal: 6, paddingVertical: 3, borderRadius: 6, backgroundColor: ART_BG },
  artTab: { paddingHorizontal: 5, paddingVertical: 3, borderRadius: 6, backgroundColor: ART_BG },
  artCaption: { fontSize: 10, fontWeight: '700', color: color.muted, letterSpacing: 0.3 },
  artText: { fontSize: 11, color: color.fg },
  artToggleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  artToggle: { width: 30, height: 18, borderRadius: 9, backgroundColor: color.primary, padding: 2, alignItems: 'flex-end' },
  artKnob: { width: 14, height: 14, borderRadius: 7, backgroundColor: '#fff' },
  artField: { height: 24, borderRadius: 6, borderWidth: 1, borderColor: 'rgba(24,27,34,0.14)', paddingHorizontal: 7, justifyContent: 'center' },
  artSelect: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  artBubble: { alignSelf: 'flex-end', width: '55%', padding: 7, borderRadius: 10, backgroundColor: ART_BG, gap: 4 },
  artComposer: { flexDirection: 'row', alignItems: 'center', gap: 6, height: 34, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(24,27,34,0.14)', paddingHorizontal: 5 },
  artPlus: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  artKleal: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 6, height: 22, borderRadius: 11, backgroundColor: ART_BG },
  bar: { height: 6, borderRadius: 3, backgroundColor: '#E3E6EB' },
  ring: { alignSelf: 'flex-start', borderRadius: 10, borderWidth: 2, borderColor: color.primary, padding: 1.5 },

  paste: { gap: space.sm },
  pasteTitle: { fontFamily: font.textMedium, fontSize: 16, lineHeight: 22, color: color.fg },
  pasteField: { minHeight: 140, borderRadius: 18, overflow: 'hidden', borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(24,27,34,0.12)' },
  pasteInput: { minHeight: 140, padding: 14, paddingTop: 14, fontSize: 15, lineHeight: 21, color: color.fg },
  pasteBtn: { position: 'absolute', right: 10, bottom: 10, flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, height: 30, borderRadius: 15, backgroundColor: 'rgba(255,56,92,0.10)' },
  pasteBtnText: { fontSize: 13, fontWeight: '600', color: color.primary },
  err: { ...type.caption, color: color.primary } as any,

  draft: { gap: space.md },
  source: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sourceText: { fontSize: 12, fontWeight: '600', color: color.muted },
  group: { gap: 8 },
  groupTitle: { fontSize: 12, fontWeight: '700', color: color.muted, letterSpacing: 0.3, textTransform: 'uppercase' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, height: 34, paddingLeft: 12, paddingRight: 10, borderRadius: 17, backgroundColor: 'rgba(255,56,92,0.10)', borderWidth: 1, borderColor: 'rgba(255,56,92,0.28)' },
  chipOff: { backgroundColor: 'transparent', borderColor: 'rgba(24,27,34,0.14)', borderStyle: 'dashed' },
  chipText: { fontSize: 14, fontWeight: '600', color: color.fg, maxWidth: 220 },
  chipTextOff: { color: color.muted, textDecorationLine: 'line-through' },
  chipRestore: { fontSize: 14, color: color.muted },
  line: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, padding: 12, borderRadius: 14, backgroundColor: '#fff', borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(24,27,34,0.12)' },
  lineOff: { backgroundColor: 'transparent', borderStyle: 'dashed' },
  lineText: { flex: 1, fontSize: 15, lineHeight: 21, color: color.fg },
  lineX: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: color.neutral100 },
  draftBtns: { flexDirection: 'row', gap: space.sm, marginTop: space.sm },

  status: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 14, borderRadius: 20, overflow: 'hidden' },
  statusIcon: { width: 36, height: 36, borderRadius: 12, backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  iconGood: { backgroundColor: color.primary },
  iconWarn: { backgroundColor: 'rgba(255,184,0,0.18)' },
  statusTitle: { fontFamily: font.textMedium, fontSize: 15, lineHeight: 20, color: color.fg },
  statusSub: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  statusBtns: { flexDirection: 'row', gap: 8, marginTop: 10 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: color.primary },
});
